#!/bin/env python

# Combine the matrices for the matrix-method fake estimate as a
# weighted sum of the fake composition in each signal region.

# All the elements of the matrix, both p(T|R) and p(T|F), are in fact
# p_T-dependent histograms.
#
# For p(T|R) we simply count for each background the number of real
# leptons in each signal region.
# For p(T|F) we also subdivide the leptons in fake categories. That
# is, heavy-flavor for muons, heavy-flavor or conversion for
# electrons. The categorization as true/fake/hf/conv is based on the
# monte-carlo truth.
# After computing the fractions of leptons due to each background (and
# to each fake categories), a bin-by-bin weighted sum is performed,
# where the bins are now p_T-bins. That is, we perform a weighted sum
# of histograms.
#
# The procedure is described in sec. 6.2 of ATL-COM-PHYS-2012-1808.
# This python implementation is based on the c++ implementation by
# Matt (mrelich6@gmail.com), originally in FinalNewFake.cxx
#
# davide.gerbaudo@gmail.com
# October 2013

from math import sqrt
import operator
import optparse
import os
from rootUtils import importRoot, buildRatioHistogram, drawLegendWithDictKeys, getMinMax, getBinContents, getBinIndices
r = importRoot()
r.gStyle.SetPadTickX(1)
r.gStyle.SetPadTickY(1)
from utils import (enumFromHeader
                   ,first
                   ,mkdirIfNeeded
                   ,json_write
                   ,rmIfExists
                   )
import matplotlib as mpl
mpl.use('Agg') # render plots without X
import matplotlib.pyplot as plt
import numpy as np
import SampleUtils

usage="""
Example usage:
%prog \\
 --tag ${TAG} \\
 --input_dir out/fakerate/merged/data_${TAG}.root \\
 --output_file out/fakerate/merged/FinalFakeHist_${TAG}.root \\
 --output_plot out/fakerate/merged/FinalFakeHist_plots_${TAG} \\
 >& log/fakerate/FinalFakeHist_${TAG}.log
"""

# scale factors from determineFakeScaleFactor.py
# --- paste the lines below in buildWeightedMatrix.py ---
# Feb_12, 2014-02-12 18:20:20.650121
mu_qcdSF, mu_realSF = 0.86, 0.99590
el_convSF, el_qcdSF, el_realSF = 1.09, 0.63, 0.99633

def main() :
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('-t', '--tag')
    parser.add_option('-i', '--input_dir')
    parser.add_option('-s', '--input_sf', help='will toggle bin-by-bin scale factors for conv and qcd')
    parser.add_option('-o', '--output_file')
    parser.add_option('-p', '--output_plot')
    parser.add_option('-v','--verbose', action='store_true', default=False)
    (opts, args) = parser.parse_args()
    requiredOptions = ['tag', 'input_dir', 'output_file', 'output_plot']
    otherOptions = ['input_sf', 'verbose']
    allOptions = requiredOptions + otherOptions
    def optIsNotSpecified(o) : return not hasattr(opts, o) or getattr(opts,o) is None
    if any(optIsNotSpecified(o) for o in requiredOptions) : parser.error('Missing required option')
    tag = opts.tag
    inputDirname  = opts.input_dir
    inputSfFname  = opts.input_sf
    outputFname   = opts.output_file
    outputPlotDir = opts.output_plot
    verbose       = opts.verbose
    if verbose : print '\nUsing the following options:\n'+'\n'.join("%s : %s"%(o, str(getattr(opts, o))) for o in allOptions)

    allInputFiles = getInputFiles(inputDirname, tag, verbose) # includes allBkg, which is used only for sys
    assert all(f for f in allInputFiles.values()), ("missing inputs: \n%s"%'\n'.join(["%s : %s"%kv for kv in allInputFiles.iteritems()]))
    outputPlotDir = outputPlotDir+'/' if not outputPlotDir.endswith('/') else ''
    mkdirIfNeeded(outputPlotDir)
    outputFile = r.TFile.Open(outputFname, 'recreate')
    inputFiles = dict((k, v) for k, v in allInputFiles.iteritems() if k in fakeProcesses())
    inputSfFile = r.TFile.Open(inputSfFname) if inputSfFname else None

    buildMuonRates    (inputFiles, outputFile, outputPlotDir, inputSfFile, verbose)
    buildElectronRates(inputFiles, outputFile, outputPlotDir, inputSfFile, verbose)
    buildSystematics  (allInputFiles['allBkg'], outputFile, verbose)
    outputFile.Close()
    if verbose : print "output saved to \n%s"%'\n'.join([outputFname, outputPlotDir])

def samples() : return ['allBkg', 'ttbar', 'wjets', 'zjets', 'diboson', 'heavyflavor']
def fakeProcesses() : return ['ttbar', 'wjets', 'zjets', 'diboson', 'heavyflavor']
def frac2str(frac) :
    return '\n'.join([''.join("%12s"%s for s in fakeProcesses()),
                      ''.join("%12s"%("%.3f"%frac[s]) for s in fakeProcesses())])
def selectionRegions() :
    print "hardcoded selectionRegions, should match what's in FakeRegions.h; fix DiLeptonMatrixMethod"
    return ['CR_SSInc',
            'CR_SSInc1j',
            'CR_WHSS',
            'CR_CR8lpt',
            'CR_CR8ee',
            'CR_CR8mm',
            'CR_CR8mmMtww',
            'CR_CR8mmHt',
            'CR_CR9lpt',
            'CR_SsEwk',
            'CR_SsEwkLoose',
            'CR_SsEwkLea',
            'CR_WHZVfake1jee',
            'CR_WHZVfake2jee',
            'CR_WHZVfake1jem',
            'CR_WHZVfake2jem',
            'CR_WHfake1jem',
            'CR_WHfake2jem',
            'CR_WHZV1jmm',
            'CR_WHZV2jmm',
            'CR_WHfake1jmm',
            'CR_WHfake2jmm',

            "CR_WHZVfake1j",
            "CR_WHZVfake2j",
            "CR_WHfake1j",
            "CR_WHfake2j",
            "CR_WHZV1j",
            "CR_WHZV2j",

            "CR_SRWH1j",
            "CR_SRWH2j"
            ]
def isRegionToBePlotted(sr) :
    "regions for which we plot the weighted matrices"
    return sr in ['CR_WHZVfake1j', 'CR_WHZVfake2j', 'CR_WHfake1j', 'CR_WHfake2j', 'CR_WHZV1j', 'CR_WHZV2j', 'CR_SRWH1j', 'CR_SRWH2j']

def extractionRegions() :
    return ['qcdMC', 'convMC', 'realMC']

def getInputFiles(inputDirname, tag, verbose=False) :
    inDir = inputDirname
    tag = tag if tag.startswith('_') else '_'+tag
    files = dict(zip(samples(), [r.TFile.Open(inDir+'/'+s+tag+'.root') for s in samples()]))
    if verbose : print "getInputFiles('%s'):\n\t%s"%(inputDirname, '\n\t'.join("%s : %s"%(k, f.GetName()) for k, f in files.iteritems()))
    return files
def buildRatio(inputFile=None, histoBaseName='') :
    num, den = inputFile.Get(histoBaseName+'_num'), inputFile.Get(histoBaseName+'_den')
    return buildRatioHistogram(num, den, histoBaseName +'_rat')
def getRealEff(lepton='electron|muon', inputFile=None, scaleFactor=1.0) :
    histoName = lepton+'_realMC_all_l_pt_coarse'
    effHisto = buildRatio(inputFile, histoName)
    effHisto.Scale(scaleFactor)
    return effHisto
def buildRatioAndScaleIt(histoPrefix='', inputFile=None, scaleFactor=1.0, verbose=False) :
    ratioHisto = buildRatio(inputFile, histoPrefix)

    def lf2s(l) : return ', '.join(["%.3f"%e for e in l])
    if verbose: print ratioHisto.GetName()," before scaling: ",lf2s(getBinContents(ratioHisto))
    if   type(scaleFactor)==float : ratioHisto.Scale(scaleFactor)
    elif type(scaleFactor)==r.TH1F :
        if type(scaleFactor)==r.TH1F and type(ratioHisto)==r.TH2F :
            tmpH = ratioHisto.Clone(scaleFactor.GetName()+'_vs_eta')
            ptBins, etaBins = range(1, 1+ratioHisto.GetNbinsX()), range(1, 1+ratioHisto.GetNbinsY()),
            for p in ptBins :
                for e in etaBins :
                    tmpH.SetBinContent(p, e, scaleFactor.GetBinContent(p))
                    tmpH.SetBinError(p, e, scaleFactor.GetBinError(p))
            scaleFactor = tmpH
        ratioHisto.Multiply(scaleFactor)
    else : raise TypeError("unknown SF type %s"%type(scaleFactor))
    if verbose: print ratioHisto.GetName()," after scaling: ",lf2s(getBinContents(ratioHisto))
    return ratioHisto
def buildPercentages(inputFiles, histoName, binLabel) :
    "build a dictionary (process, fraction of counts) for a given bin"
    histos = dict((p, f.Get(histoName)) for p, f in inputFiles.iteritems())
    assert all(h for h in histos.values()),"missing histo '%s'\n%s"%(histoName, '\n'.join("%s : %s"%(k, str(v)) for k, v in histos.iteritems()))
    bin = first(histos).GetXaxis().FindBin(binLabel)
    counts = dict((p, h.GetBinContent(bin)) for p, h in histos.iteritems())
    norm = sum(counts.values())
    if not norm : print "buildPercentages: warning, all empty histograms for %s[%s]"%(histoName, binLabel)
    counts = dict((p, c/norm if norm else 0.0)for p,c in counts.iteritems())
    return counts
def buildPercentagesTwice(inputFiles, histoName, binLabelA, binLabelB) :
    """
    build two dictionaries (process, fraction of counts) for two given bins.
    Note that we cannot use buildPercentages because we want to
    normalize A and B (i.e. qcd and conv) together.
    Maybe refactor these two buildPercentages* functions?
    """
    histos = dict((p, f.Get(histoName)) for p, f in inputFiles.iteritems())
    assert all(h for h in histos.values()),"missing histo '%s'\n%s"%(histoName, '\n'.join("%s : %s"%(k, str(v)) for k, v in histos.iteritems()))
    binA = first(histos).GetXaxis().FindBin(binLabelA)
    binB = first(histos).GetXaxis().FindBin(binLabelB)
    countsA = dict((p, h.GetBinContent(binA)) for p, h in histos.iteritems())
    countsB = dict((p, h.GetBinContent(binB)) for p, h in histos.iteritems())
    norm = sum(countsA.values() + countsB.values())
    if not norm : print "buildPercentages: warning, all empty histograms for %s[%s,%s]"%(histoName, binLabelA, binLabelB)
    countsA = dict((p, c/norm if norm else 0.0)for p,c in countsA.iteritems())
    countsB = dict((p, c/norm if norm else 0.0)for p,c in countsB.iteritems())
    return countsA, countsB
def binWeightedSum(histos={}, weights={}, bin=1) :
    assert not set(histos)-set(weights), "different keys: histos[%s], weights[%s]"%(str(histos.keys()), str(weights.keys()))
    cews = [(h.GetBinContent(bin), h.GetBinError(bin), w)
            for h, w in [(histos[k], weights[k]) for k in histos.keys()]]
    tot  = sum(c*w     for c, e, w in cews)
    err2 = sum(e*e*w*w for c, e, w in cews)
    return tot, err2
def buildWeightedHisto(histos={}, fractions={}, histoName='', histoTitle='') :
    "was getFinalRate"
    hout = first(histos).Clone(histoName if histoName else 'final_rate') # should pick a better default
    hout.SetTitle(histoTitle)
    hout.Reset()
    for b in getBinIndices(hout) :
        tot, err2 = binWeightedSum(histos, fractions, b)
        hout.SetBinContent(b, tot)
        hout.SetBinError(b, sqrt(err2))
    return hout
def buildWeightedHistoTwice(histosA={}, fractionsA={}, histosB={}, fractionsB={},
                            histoName='', histoTitle='') :
    "was getFinalRate"
    assert not set(histosA)-set(histosB),"different keys A[%s], B[%s]"%(str(histosA.keys()), str(histosB.keys()))
    hout = first(histosA).Clone(histoName if histoName else 'final_rate') # should pick a better default
    hout.SetTitle(histoTitle)
    hout.Reset()
    for b in getBinIndices(hout) :
        totA, errA2 = binWeightedSum(histosA, fractionsA, b)
        totB, errB2 = binWeightedSum(histosB, fractionsB, b)
        hout.SetBinContent(b, totA + totB)
        hout.SetBinError(b, sqrt(errA2 + errB2))
    return hout
def buildMuonRates(inputFiles, outputfile, outplotdir, inputSfFile=None, verbose=False) :
    """
    For each selection region, build the real eff and fake rate
    histo as a weighted sum of the corresponding fractions.
    """
    processes = fakeProcesses()
    brsit, iF, v = buildRatioAndScaleIt, inputFiles, verbose
    mu_qcdSF_pt = inputSfFile.Get('muon_qcdSF_pt') if inputSfFile else mu_qcdSF
    print "buildMuonRates: values to be fixed: ",' '.join(["%s: %s"%(v, eval(v)) for v in ['mu_qcdSF', 'mu_realSF']])
    eff_qcd  = dict((p, brsit('muon_qcdMC_all_l_pt_coarse',  iF[p], mu_qcdSF_pt, v))  for p in processes)
    eff_real = dict((p, brsit('muon_realMC_all_l_pt_coarse', iF[p], mu_realSF, v)) for p in processes)
    eff2d_qcd  = dict((p, brsit('muon_qcdMC_all_l_pt_eta',  iF[p], mu_qcdSF_pt, v))  for p in processes)
    eff2d_real = dict((p, brsit('muon_realMC_all_l_pt_eta', iF[p], mu_realSF, v)) for p in processes)
    lT, lX, lY = '#varepsilon(T|L)', 'p_{T} [GeV]', '#varepsilon(T|L)'
    plot1dEfficiencies(eff_qcd,  'eff_mu_qcd',  outplotdir, lT+' qcd fake #mu'+';'+lX+';'+lY)
    plot1dEfficiencies(eff_real, 'eff_mu_real', outplotdir, lT+' real #mu'    +';'+lX+';'+lY)
    lT, lX, lY = '#varepsilon(T|L)', 'p_{T} [GeV]', '#eta'
    plot2dEfficiencies(eff2d_qcd,  'eff2d_mu_qcd', outplotdir, lT+' qcd fake #mu'+';'+lX+';'+lY)
    plot2dEfficiencies(eff2d_real, 'eff2d_mu_real', outplotdir, lT+' real #mu'   +';'+lX+';'+lY)
    mu_frac = dict()
    for sr in selectionRegions() :
        frac_qcd  = buildPercentages(inputFiles, 'muon_'+sr+'_all_flavor_den', 'qcd')
        frac_real = buildPercentages(inputFiles, 'muon_'+sr+'_all_flavor_den', 'real')
        if verbose : print "mu : sr ",sr,"\n frac_qcd  : ",frac2str(frac_qcd )
        if verbose : print "mu : sr ",sr,"\n frac_real : ",frac2str(frac_real)
        fake1d = buildWeightedHisto(eff_qcd,  frac_qcd, 'mu_fake_rate_'+sr, 'Muon fake rate '+sr)
        real1d = buildWeightedHisto(eff_real, frac_real, 'mu_real_eff_'+sr, 'Muon real eff ' +sr)
        fake2d = buildWeightedHisto(eff2d_qcd,  frac_qcd, 'mu_fake_rate2d_'+sr, 'Muon fake rate #eta vs. p_{T}'+sr)
        real2d = buildWeightedHisto(eff2d_real, frac_real, 'mu_real_eff2d_'+sr, 'Muon real eff  #eta vs. p_{T}'+sr)
        outputfile.cd()
        fake1d.Write()
        real1d.Write()
        fake2d.Write()
        real2d.Write()
        mu_frac[sr] = {'qcd' : frac_qcd, 'real' : frac_real}
        if isRegionToBePlotted(sr) :
            lT, lX, lY = '#varepsilon(T|L)', 'p_{T} [GeV]', '#eta'
            plot2dEfficiencies({sr : fake2d}, 'eff2d_mu_fake', outplotdir, lT+' fake #mu'+';'+lX+';'+lY)
            plot2dEfficiencies({sr : real2d}, 'eff2d_mu_real', outplotdir, lT+' real #mu'+';'+lX+';'+lY)
    #json_write(mu_frac, outplotdir+/outFracFilename)
    plotFractions(mu_frac, outplotdir, 'frac_mu')
def buildElectronRates(inputFiles, outputfile, outplotdir, inputSfFile=None, verbose=False) :
    """
    For each selection region, build the real eff and fake rate
    histo as a weighted sum of the corresponding fractions.
    Note that the fake has two components (conversion and qcd).
    """
    processes = fakeProcesses()
    brsit, iF, v = buildRatioAndScaleIt, inputFiles, verbose
    el_qcdSF_pt  = inputSfFile.Get('elec_qcdSF_pt') if inputSfFile else el_qcdSF
    el_convSF_pt = inputSfFile.Get('elec_convSF_pt') if inputSfFile else el_convSF
    print "buildElectronRates: values to be fixed: ",' '.join(["%s: %s"%(v, eval(v)) for v in ['el_qcdSF', 'el_convSF', 'el_realSF']])
    eff_conv = dict((p, brsit('elec_convMC_all_l_pt_coarse', iF[p], el_convSF_pt, v)) for p in processes)
    eff_qcd  = dict((p, brsit('elec_qcdMC_all_l_pt_coarse',  iF[p], el_qcdSF_pt, v))  for p in processes)
    eff_real = dict((p, brsit('elec_realMC_all_l_pt_coarse', iF[p], el_realSF, v)) for p in processes)
    eff2d_conv = dict((p, brsit('elec_convMC_all_l_pt_eta', iF[p], el_convSF_pt, v)) for p in processes)
    eff2d_qcd  = dict((p, brsit('elec_qcdMC_all_l_pt_eta',  iF[p], el_qcdSF_pt, v))  for p in processes)
    eff2d_real = dict((p, brsit('elec_realMC_all_l_pt_eta', iF[p], el_realSF, v)) for p in processes)
    lT, lX, lY = '#varepsilon(T|L)', 'p_{T} [GeV]', '#varepsilon(T|L)'
    plot1dEfficiencies(eff_conv, 'eff_el_conv', outplotdir, lT+' conv fake el'+';'+lX+';'+lY)
    plot1dEfficiencies(eff_qcd,  'eff_el_qcd',  outplotdir, lT+' qcd fake el' +';'+lX+';'+lY)
    plot1dEfficiencies(eff_real, 'eff_el_real', outplotdir, lT+' real el'     +';'+lX+';'+lY)
    lT, lX, lY = '#varepsilon(T|L)', 'p_{T} [GeV]', '#eta'
    plot2dEfficiencies(eff2d_conv, 'eff2d_el_conv', outplotdir, lT+' conv fake el'+';'+lX+';'+lY)
    plot2dEfficiencies(eff2d_qcd,  'eff2d_el_qcd',  outplotdir, lT+' qcd fake el' +';'+lX+';'+lY)
    plot2dEfficiencies(eff2d_real, 'eff2d_el_real', outplotdir, lT+' real el'     +';'+lX+';'+lY)
    el_frac = dict()
    for sr in selectionRegions() :
        frac_conv, frac_qcd= buildPercentagesTwice(inputFiles, 'elec_'+sr+'_all_flavor_den',
                                                   'conv', 'qcd')
        frac_real = buildPercentages(inputFiles, 'elec_'+sr+'_all_flavor_den', 'real')
        if verbose : print "el : sr ",sr,"\n frac_conv : ",frac2str(frac_conv)
        if verbose : print "el : sr ",sr,"\n frac_qcd  : ",frac2str(frac_qcd )
        if verbose : print "el : sr ",sr,"\n frac_real : ",frac2str(frac_real)
        real1d = buildWeightedHisto     (eff_real, frac_real,                     'el_real_eff_'+sr, 'Electron real eff '+sr)
        fake1d = buildWeightedHistoTwice(eff_conv, frac_conv, eff_qcd,  frac_qcd, 'el_fake_rate_'+sr, 'Electron fake rate '+sr)
        real2d = buildWeightedHisto     (eff2d_real, frac_real,                     'el_real_eff2d_'+sr, 'Electron real eff  #eta vs. p_{T}'+sr)
        fake2d = buildWeightedHistoTwice(eff2d_conv, frac_conv, eff2d_qcd,  frac_qcd, 'el_fake_rate2d_'+sr, 'Electron fake rate  #eta vs. p_{T}'+sr)
        outputfile.cd()
        fake1d.Write()
        real1d.Write()
        fake2d.Write()
        real2d.Write()
        el_frac[sr] = {'conv' : frac_conv, 'qcd' : frac_qcd, 'real' : frac_real}
        if isRegionToBePlotted(sr) :
            lT, lX, lY = '#varepsilon(T|L)', 'p_{T} [GeV]', '#eta'
            plot2dEfficiencies({sr : fake2d}, 'eff2d_el_fake', outplotdir, lT+' fake e'+';'+lX+';'+lY)
            plot2dEfficiencies({sr : real2d}, 'eff2d_el_real', outplotdir, lT+' real e'+';'+lX+';'+lY)
    #json_write(el_frac, outFracFilename)
    plotFractions(el_frac, outplotdir, 'frac_el')
def buildEtaSyst(inputFileTotMc, inputHistoBaseName='(elec|muon)_qcdMC_all', outputHistoName='', verbose=False) :
    """
    Take the eta distribution and normalize it to the average fake
    rate (taken from one bin rate); use the differences from 1 as the
    fractional uncertainty.
    """
    rate = buildRatio(inputFileTotMc, inputHistoBaseName+'_l_eta_coarse').Clone(outputHistoName)
    norm = buildRatio(inputFileTotMc, inputHistoBaseName+'_onebin').GetBinContent(1)
    rate.Scale(1.0/norm if norm else 1.0)
    bins = range(1, 1+rate.GetNbinsX())
    for b in bins : rate.AddBinContent(b, -1.0) # DG there must be a better way to do this
    scaleUpForward, fwFact, maxCentralEta = True, 2.0, 1.5
    if scaleUpForward :
        for b in bins :
            bCon, bCen = rate.GetBinContent(b), rate.GetBinCenter(b)
            rate.SetBinContent(b, bCon*(fwFact if abs(bCen)>maxCentralEta else 1.0))
    if inputHistoBaseName.startswith('mu') : rate.Reset() # mu consistent with 0.
    if verbose : print "eta syst ",inputHistoBaseName," : ",["%.2f"%rate.GetBinContent(b) for b in range(1, 1+rate.GetNbinsX())]
    return rate
def buildSystematics(inputFileTotMc, outputfile, verbose=False) :
    "Hardcoded values from FinalNewFake.h; might not be used at all...ask Matt"
    print "build syst might be droppped...check this with Matt"
    print "rename *_down to *_do"
    el_real_up = r.TParameter('double')('el_real_up', 0.01)
    el_real_dn = r.TParameter('double')('el_real_down', 0.02)
    mu_real_up = r.TParameter('double')('mu_real_up', 0.00)
    mu_real_dn = r.TParameter('double')('mu_real_down', 0.02)
    el_HFLFerr = r.TParameter('double')('el_HFLFerr', 0.05)
    mu_HFLFerr = r.TParameter('double')('mu_HFLFerr', 0.00)
    el_datamc  = r.TParameter('double')('el_datamc',  0.20) #datamc are effectively the sf error.
    mu_datamc  = r.TParameter('double')('mu_datamc',  0.05) #Right now taking the Pt variation into account
    el_region  = r.TParameter('double')('el_region',  0.05)
    mu_region  = r.TParameter('double')('mu_region',  0.10)
    el_eta     = buildEtaSyst(inputFileTotMc, 'elec_qcdMC_all', 'el_eta_sys', verbose)
    mu_eta     = buildEtaSyst(inputFileTotMc, 'muon_qcdMC_all', 'mu_eta_sys', verbose)
    allSys = [el_real_up, el_real_dn, mu_real_up, mu_real_dn,
              el_HFLFerr, mu_HFLFerr, el_datamc , mu_datamc,
              el_region, mu_region, el_eta, mu_eta ]
    outputfile.cd()
    for o in  allSys : o.Write()
def plotFractions(fractDict={}, outplotdir='./', prefix='') :
    """
    input : fractDict[sr][lep_type][sample] = float
    """
    outplotdir = outplotdir if outplotdir.endswith('/') else outplotdir+'/'
    #def isRegionToBePlotted(r) : return r in selectionRegions()+extractionRegions()
    regions  = sorted(filter(isRegionToBePlotted, fractDict.keys()))
    leptypes = sorted(first(fractDict).keys())
    samples  = sorted(first(first(fractDict)).keys())
    ind = np.arange(len(regions))
    width = 0.5
    colors = dict(zip(samples, ['b','g','r','c','m','y']))
    for lt in leptypes :
        fracPerSample = dict((s, np.array([fractDict[r][lt][s] for r in regions])) for s in samples)
        below = np.zeros(len(regions))
        plots = []
        fig, ax = plt.subplots()
        for s, frac in fracPerSample.iteritems() :
            plots.append(plt.bar(ind, frac, width, color=colors[s], bottom=below))
            below = below + frac
        plt.ylabel('fractions')
        plt.title(prefix+' '+lt+' compositions')
        plt.xticks(ind+width/2., regions)
        plt.ylim((0.0, 1.0))
        plt.grid(True)
        plt.yticks(np.arange(0.0, 1.0, 0.2))
        labels = {'heavyflavor' : 'bb/cc', 'diboson' : 'VV', 'ttbar':'tt'}
        labels = [labels[s] if s in labels else s for s in samples]
        leg = plt.legend([p[0] for p in plots], labels, bbox_to_anchor=(1.135, 1.05))
        leg.get_frame().set_alpha(0.5)
        fig.autofmt_xdate(bottom=0.25, rotation=90, ha='center')
        fig.savefig(outplotdir+prefix+'_'+lt+'.png')
        fig.savefig(outplotdir+prefix+'_'+lt+'.eps')

def plot1dEfficiencies(effs={}, canvasName='', outputDir='./', frameTitle='title;p_{T} [GeV]; efficiency', zoomIn=False) :
    can = r.TCanvas(canvasName, '', 800, 600)
    can.cd()
    padMaster = None
    colors, markers = SampleUtils.colors, SampleUtils.markers
    for s,h in effs.iteritems() :
        h.SetLineColor(colors[s] if s in colors else r.kBlack)
        h.SetMarkerColor(h.GetLineColor())
        h.SetMarkerStyle(markers[s] if s in markers else r.kFullCircle)
        drawOpt = 'ep same' if padMaster else 'ep'
        h.Draw(drawOpt)
        if not padMaster : padMaster = h
    minY, maxY = getMinMax(effs.values()) if zoomIn else (0.0, 1.0)
    padMaster.GetYaxis().SetRangeUser(min([0.0, minY]), 1.1*maxY)
    padMaster.SetTitle(frameTitle)
    padMaster.SetStats(False)
    drawLegendWithDictKeys(can, effs)
    can.Update()
    for ext in ['png','eps'] :
        outFilename = outputDir+'/'+canvasName+'.'+ext
        rmIfExists(outFilename)
        can.SaveAs(outFilename)
def plot2dEfficiencies(effs={}, canvasName='', outputDir='./', frameTitle='efficiency; #eta; p_{T} [GeV]', zoomIn=False) :
    can = r.TCanvas(canvasName, '', 800, 600)
    can.cd()
    origTextFormat = r.gStyle.GetPaintTextFormat()
    r.gStyle.SetPaintTextFormat('.2f')
    for s,h in effs.iteritems() :
        can.Clear()
        # todo minZ, maxZ = getMinMax(effs.values()) if zoomIn else (0.0, 1.0)
        minZ, maxZ = (0.0, 1.0)
        h.SetMarkerSize(1.5*h.GetMarkerSize())
        h.Draw('colz')
        h.Draw('text e same')
        h.GetZaxis().SetRangeUser(min([0.0, minZ]), maxZ)
        def dropCrPrefix(sr) : return sr.replace('CR_', '')
        h.SetTitle(dropCrPrefix(s)+' : '+frameTitle)
        h.SetStats(False)
        can.Update()
        for ext in ['png','eps'] :
            outFilename = outputDir+'/'+canvasName+'_'+s+'.'+ext
            rmIfExists(outFilename)
            can.SaveAs(outFilename)
    r.gStyle.SetPaintTextFormat(origTextFormat)



if __name__=='__main__' :
    main()
