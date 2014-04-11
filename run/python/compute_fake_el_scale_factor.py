#!/bin/env python


import array
import collections
import glob
import math
import numpy as np
import optparse
import os
import pprint
from utils import (first
                   ,mkdirIfNeeded
                   )
import rootUtils
from rootUtils import (drawLegendWithDictKeys
                       ,getBinContents
                       ,getBinErrors
                       ,getMinMax
                       ,importRoot
                       ,importRootCorePackages
                       ,summedHisto
                       ,topRightLabel)
r = rootUtils.importRoot()
r.gROOT.SetStyle('Plain')
rootUtils.importRootCorePackages()
from datasets import datasets, setSameGroupForAllData
from SampleUtils import (colors
                         ,fastSamplesFromFilenames
                         ,guessSampleFromFilename
                         ,isBkgSample)
from kin import computeMt

usage="""
Example usage:
%prog \\
 --verbose  \\
 --mode bbcc \\
 --tag ${TAG} \\
 --output-dir ./out/conv_el_scale_factor_same_sign_Mar_07
 --tag ${TAG} \\
 --input_dir out/fakerate/merged/data_${TAG}.root \\
 --output_file out/fakerate/merged/FinalFakeHist_${TAG}.root \\
 --output_plot out/fakerate/merged/FinalFakeHist_plots_${TAG} \\
 >& log/fakerate/FinalFakeHist_${TAG}.log
"""
def main():
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-i', '--input-dir', default='./out/fakerate')
    parser.add_option('-o', '--output-dir', default='./out/fake_el_scale_factor', help='dir for plots')
    parser.add_option('-m', '--mode', default='bbcc', help='either bbcc or conv')
    parser.add_option('-t', '--tag', help='tag used to select the input files (e.g. Apr_04)')
    parser.add_option('-f', '--fill-histos', action='store_true', default=False, help='force fill (default only if needed)')
    parser.add_option('-v', '--verbose', action='store_true', default=False)
    (options, args) = parser.parse_args()
    inputDir  = options.input_dir
    outputDir = options.output_dir
    mode      = options.mode
    tag       = options.tag
    verbose   = options.verbose
    if not tag : parser.error('tag is a required option')
    if mode not in ['bbcc', 'conv'] : parser.error("invalid mode '%s'"%mode)
    templateInputFilename = "*_%(mode)s_tuple_%(tag)s.root" % {'tag':tag, 'mode':mode}
    templateOutputFilename =  "%(mode)s_el_scale_histos_%(tag)s.root" % {'tag':tag, 'mode':mode}
    treeName = 'HeavyFlavorControlRegion' if mode=='bbcc' else 'ConversionControlRegion'
    outputFileName = os.path.join(outputDir, templateOutputFilename)
    doFillHistograms = options.fill_histos or not os.path.exists(outputFileName)
    optionsToPrint = ['inputDir', 'outputDir', 'mode', 'tag', 'doFillHistograms']
    if verbose : print "options:\n"+'\n'.join(["%s : %s"%(o, eval(o)) for o in optionsToPrint])
    # collect inputs
    tupleFilenames = glob.glob(os.path.join(inputDir, templateInputFilename))
    samples = setSameGroupForAllData(fastSamplesFromFilenames(tupleFilenames, verbose))
    samplesPerGroup = collections.defaultdict(list)
    filenamesPerGroup = collections.defaultdict(list)
    mkdirIfNeeded(outputDir)
    for s, f in zip(samples, tupleFilenames) :
        samplesPerGroup[s.group].append(s)
        filenamesPerGroup[s.group].append(f)
    vars = ['pt1', 'eta1']
    groups = samplesPerGroup.keys()
    #fill histos
    if doFillHistograms :
        histosPerGroup = bookHistos(vars, groups)
        for group in groups:
            filenames = filenamesPerGroup[group]
            histos = histosPerGroup[group]
            chain = r.TChain(treeName)
            [chain.Add(fn) for fn in filenames]
            print "%s : %d entries"%(group, chain.GetEntries())
            fillHistos(chain, histos, verbose)
        writeHistos(outputFileName, histosPerGroup, verbose)
    # compute scale factors
    histosPerGroup = fetchHistos(outputFileName, histoNames(vars, groups), verbose)
    plotStackedHistos(histosPerGroup, outputDir, verbose)
    sf_el_eta = subtractRealAndComputeScaleFactor(histosPerGroup, 'eta1', 'sf_el_vs_eta', verbose)
    sf_el_pt  = subtractRealAndComputeScaleFactor(histosPerGroup, 'pt1',  'sf_el_vs_pt',  verbose)
    outputFile = r.TFile.Open(outputFileName, 'recreate')
    outputFile.cd()
    sf_el_eta.Write()
    sf_el_pt.Write()
    outputFile.Close()
    if verbose : print "saved scale factors to %s" % outputFileName

#___________________________________________________

leptonTypes = ['tight', 'loose', 'real_tight', 'real_loose', 'fake_tight', 'fake_loose']

def fillHistos(chain, histos, verbose=False):
    nElecLoose, nElecTight = 0, 0
    totWeightLoose, totWeightTight = 0.0, 0.0
    for event in chain :
        pars = event.pars
        weight, evtN, runN = pars.weight, pars.eventNumber, pars.runNumber
        tag, probe, met = event.l0, event.l1, event.met
        isSameSign = tag.charge*probe.charge > 0.
        isEl, isTight = probe.isEl, probe.isTight
        isReal = probe.source==3 # see FakeLeptonSources.h
        isFake = not isReal
        probe4m, met4m = r.TLorentzVector(), r.TLorentzVector()
        probe4m.SetPxPyPzE(probe.px, probe.py, probe.pz, probe.E)
        met4m.SetPxPyPzE(met.px, met.py, met.pz, met.E)
        pt = probe4m.Pt()
        eta = abs(probe4m.Eta())
        mt = computeMt(probe4m, met4m)
        isLowMt = mt < 40.0
        if (isSameSign or isConversion) and isEl  and isLowMt :
            def incrementCounts(counts, weightedCounts) :
                counts +=1
                weightedCounts += weight
            incrementCounts(nElecLoose, totWeightLoose)
            if isTight: incrementCounts(nElecTight, totWeightTight)
            def fill(lepType=''):
                histos['pt1'][lepType].Fill(pt, weight)
                histos['eta1'][lepType].Fill(eta, weight)
            fill('loose')
            if isTight : fill('tight')
            if isReal : fill('real_loose')
            if isFake : fill('fake_loose')
            if isReal and isTight : fill('real_tight')
            if isFake and isTight : fill('fake_tight')
    if verbose:
        counterNames = ['nElecLoose', 'nElecTight', 'totWeightLoose', 'totWeightTight']
        print ', '.join(["%s : %.1f"%(c, eval(c)) for c in counterNames])

def histoName(var, sample, leptonType) : return 'h_'+var+'_'+sample+'_'+leptonType
def bookHistos(variables, samples, leptonTypes=leptonTypes) :
    "book a dict of histograms with keys [sample][var][tight, loose, real_tight, real_loose]"
    def histo(variable, hname):
        h = None
        ptBinEdges = np.array([10.0, 20.0, 35.0, 100.0])
        etaBinEdges = np.array([0.0, 1.37, 2.50])
        if   v=='pt1'     : h = r.TH1F(hname, ';p_{T,l1} [GeV]; entries/bin',   len(ptBinEdges)-1,  ptBinEdges)
        elif v=='eta1'    : h = r.TH1F(hname, ';#eta_{l1}; entries/bin',        len(etaBinEdges)-1, etaBinEdges)
        else : print "unknown variable %s"%v
        h.SetDirectory(0)
        h.Sumw2()
        return h
    return dict([(s,
                  dict([(v,
                         dict([(lt, histo(variable=v, hname=histoName(v, s, lt)))
                               for lt in leptonTypes]))
                        for v in variables]))
                 for s in samples])
def histoNames(variables, samples) :
    def extractName(dictOrHist):
        "input must be either a dict or something with 'GetName'"
        isDict = type(dictOrHist) is dict
        return dict([(k, extractName(v)) for k,v in dictOrHist.iteritems()]) if isDict else dictOrHist.GetName()
    return extractName(bookHistos(variables, samples))
def writeHistos(outputFileName='', histosPerGroup={}, verbose=False):
    outputFile = r.TFile.Open(outputFileName, 'recreate')
    outputFile.cd()
    if verbose : print "writing to %s"%outputFile.GetName()
    def write(dictOrObj):
        isDict = type(dictOrObj) is dict
        if isDict:
            for v in dictOrObj.values():
                write(v)
        else:
            if verbose : print dictOrObj.GetName()
            dictOrObj.Write()
    write(histosPerGroup)
    outputFile.Close()
def fetchHistos(fileName='', histoNames={}, verbose=False):
    "given a dict of input histonames, return the same dict, but with histo instead of histoname"
    inputFile = r.TFile.Open(fileName)
    if verbose : print "fetching histograms from %s"%inputFile.GetName()
    def fetch(dictOrName):
        isDict = type(dictOrName) is dict
        return dict([(k, fetch(v)) for k,v in dictOrName.iteritems()]) if isDict else inputFile.Get(dictOrName)
    histos = fetch(histoNames)
    #if verbose : print "fetched histos:\n%s"%pprint.pformat(histos)
    return histos
def plotStackedHistos(histosPerGroup={}, outputDir='', verbose=False):
    groups = histosPerGroup.keys()
    variables = first(histosPerGroup).keys()
    leptonTypes = first(first(histosPerGroup)).keys()
    histosPerName = dict([(var+'_'+lt, # one canvas for each histo, so key with histoname w/out group
                           dict([(g, histosPerGroup[g][var][lt]) for g in groups]))
                          for var in variables for lt in leptonTypes])
    for histoname, histosPerGroup in histosPerName.iteritems():
        missingGroups = [g for g, h in histosPerGroup.iteritems() if not h]
        if missingGroups:
            if verbose : print "skip %s, missing histos for %s"%(histoname, str(missingGroups))
            continue
        bkgHistos = dict([(g, h) for g, h in histosPerGroup.iteritems() if isBkgSample(g)])
        totBkg = summedHisto(bkgHistos.values())
        emptyBkg = totBkg.Integral()==0
        if emptyBkg:
            if verbose : print "empty backgrounds, skip %s"%histoname
            continue
        can = r.TCanvas('c_'+histoname, histoname, 800, 600)
        can.cd()
        pm = totBkg # pad master
        pm.SetStats(False)
        pm.Draw('axis')
        can.Update() # necessary to fool root's dumb object ownership
        stack = r.THStack('stack_'+histoname,'')
        can.Update()
        r.SetOwnership(stack, False)
        for s, h in bkgHistos.iteritems() :
            h.SetFillColor(colors[s] if s in colors else r.kOrange)
            h.SetDrawOption('bar')
            h.SetDirectory(0)
            stack.Add(h)
        stack.Draw('hist same')
        data = histosPerGroup['data']
        if data and data.GetEntries():
            data.SetMarkerStyle(r.kFullDotLarge)
            data.Draw('p same')
        yMin, yMax = getMinMax([h for h in [totBkg, data] if h is not None])
        pm.SetMinimum(0.0)
        pm.SetMaximum(1.1*yMax)
        can.Update()
        topRightLabel(can, histoname, xpos=0.125, align=13)
        drawLegendWithDictKeys(can, bkgHistos, opt='f')
        can.RedrawAxis()
        can._stack = stack
        can._histos = [h for h in stack.GetHists()]+[data]
        can.Update()
        can.SaveAs(os.path.join(outputDir, histoname+'.png'))
def subtractRealAndComputeScaleFactor(histosPerGroup={}, variable='', outhistoname='', verbose=False):
    "efficiency scale factor"
    groups = histosPerGroup.keys()
    histosPerType = dict([(lt,
                           dict([(g,
                                  histosPerGroup[g][variable][lt])
                                 for g in groups]))
                          for lt in leptonTypes])
    for lt in leptonTypes :
        histosPerType[lt]['totSimBkg'] = summedHisto([histo for group,histo in histosPerType[lt].iteritems() if isBkgSample(group)])

    simuTight = histosPerType['fake_tight']['totSimBkg']
    simuLoose = histosPerType['fake_loose']['totSimBkg']
    dataTight = histosPerType['tight'     ]['data'     ]
    dataLoose = histosPerType['loose'     ]['data'     ]
    # subtract real contribution from data
    # _Note to self_: currently estimating the real contr from MC; in
    # the past also used iterative corr, which might be more
    # appropriate in cases like here, where the normalization is
    # so-so.  Todo: investigate the normalization.
    dataTight.Add(histosPerType['real_tight']['totSimBkg'], -1.0)
    dataLoose.Add(histosPerType['real_loose']['totSimBkg'], -1.0)
    dataTight.Divide(dataLoose)
    simuTight.Divide(simuLoose)
    print "eff(T|L) vs. ",variable
    def formatFloat(floats): return ["%.4f"%f for f in floats]
    print "efficiency data : ",formatFloat(getBinContents(dataTight))
    print "efficiency simu : ",formatFloat(getBinContents(simuTight))
    ratio = dataTight.Clone(outhistoname)
    ratio.SetDirectory(0)
    ratio.Divide(simuTight)
    print "sf    data/simu : ",formatFloat(getBinContents(ratio))
    print "            +/- : ",formatFloat(getBinErrors(ratio))
    return ratio



if __name__=='__main__':
    main()
