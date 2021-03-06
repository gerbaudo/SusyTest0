#!/bin/env python

# Optimize the final selection for [ee,em,mm] x [1j, 2j]
#
# Input: tuples from susy::wh::TupleMaker
#
# davide.gerbaudo@gmail.com
# Jan 2014

import collections
import datetime
import glob
import math
fabs = math.fabs
import optparse
import os
from rootUtils import (importRoot,
                       buildBotTopPads,
                       summedHisto,
                       binContentsWithUoflow,
                       cloneAndFillHisto,
                       cumEffHisto,
                       maxSepVerticalLine,
                       topRightLabel,
                       drawLegendWithDictKeys
                       )
r = importRoot()
r.gStyle.SetPadTickX(1)
r.gStyle.SetPadTickY(1)
#r.TH1.AddDirectory(False)
#from  RootUtils.PyROOTFixes import enable_tree_speedups
#enable_tree_speedups() # not working with these trees...stuck at 1st event...investigate

from kin import (phi_mpi_pi,
                 addTlv,
                 computeMt, computeHt, computeMetRel,
                 getDilepType,
                 computeMt2, computeMt2j,
                 computeMljj, computeMlj,
                 thirdLepZcandidateIsInWindow)
from utils import (getCommandOutput,
                   guessLatestTagFromLatestRootFiles,
                   guessMonthDayTagFromLastRootFile,
                   isMonthDayTag,
                   dictSum,
                   first,
                   rmIfExists,
                   linearTransform,
                   cumsum,
                   mergeOuter,
                   renameDictKey,
                   mkdirIfNeeded,
                   filterWithRegexp
                   )
from SampleUtils import isSigSample, colors
from CutflowTable import CutflowTable

def optimizeSelection() :
    inputdir, options = parseOptions()


    print 'sigreg ',options.sigreg
    tag = pickTag(inputdir, options)
    sigFiles, bkgFiles = getInputFilenames(inputdir, tag, options) # todo: filter with regexp
    sigFiles = dict([(s, k) for s, k in sigFiles.iteritems() if s in filterWithRegexp(sigFiles.keys(), options.sigreg)])
    allSamples = dictSum(sigFiles, bkgFiles)
    vars = variablesToPlot()
    histos = bookHistos(vars, allSamples.keys(), options.ll, options.nj)
    counts = fillHistosAndCount(histos, dictSum(sigFiles, bkgFiles), options.ll, options.nj, options.quicktest)
    bkgHistos = dict((s, h) for s, h in histos.iteritems() if s in bkgFiles.keys())
    sigHistos = dict((s, h) for s, h in histos.iteritems() if s in sigFiles.keys())
    plotHistos(bkgHistos, sigHistos, options.plotdir)
    printSummary(counts, options.summary)

def parseOptions() :
    usage="""%prog [options] dir
    Example:
    %prog -v out/susysel
    """
    lls, njs = ['ee','em','mm'], ['eq1j','ge2j']
    parser = optparse.OptionParser(usage=usage)
    parser.add_option('--ll', help='dilepton (default all)')
    parser.add_option('--nj', help='njet multiplicity (default all)')
    parser.add_option("-s", "--sample-regexp", dest="samples", default='.*', help="consider only matching samples (default '.*')")
    parser.add_option("-S", "--signal-regexp", dest="sigreg", default='.*', help="consider only matching signal samples (default '.*', example 'WH_2Lep_1$')")
    parser.add_option("-e", "--exclude-regexp", dest="exclude", default=None, help="exclude matching samples")
    parser.add_option('-t', '--tag', help='production tag; by default the latest one')
    parser.add_option('--quicktest', action='store_true', help='run only on a fraction of the events')
    parser.add_option('--plotdir', default='./', help="save the plots to this directory")
    parser.add_option('--summary', default=None, help="write the summary txt to this file")
    parser.add_option('-v', '--verbose', action='store_true', help='print details')
    parser.add_option('-d', "--debug", action='store_true', help='print even more details')
    (options, args) = parser.parse_args()
    if len(args) != 1 : parser.error("incorrect number of arguments")
    def validateMultiOpt(o, opts, defaults) :
        v = getattr(opts, o) if hasattr(opts, o) else None
        if v and v not in defaults : parser.error("%s must be in %s (got '%s')"%(o, str(defaults), v))
        setattr(opts, o, defaults if v is None else [v])
    validateMultiOpt('ll', options, lls)
    validateMultiOpt('nj', options, njs)
    inputdir = args[0]
    return inputdir, options

def pickTag(inputdir, options) :
    tag = options.tag if options.tag else guessLatestTagFromLatestRootFiles(inputdir, options.debug)
    tag = tag if tag else guessMonthDayTagFromLastRootFile(inputdir, options.debug) # can get it wrong if from single file
    tag = tag.strip('_') # leading/trailing separators are not part of the tag
    if not isMonthDayTag(tag) : print "warning, non-standard tag might lead to bugs '%s'"%tag
    if options.verbose : print "using tag %s"%tag
    return tag

def getInputFilenames(inputdir, tag, options) :
    sig, bkg = dict(), dict()
    for f in glob.glob(inputdir+'/*'+tag+'.root') :
        sample = os.path.splitext(os.path.basename(f))[0].replace(tag, '').strip('_')
        coll = sig if isSigSample(sample) else bkg
        assert sample not in coll,"%s already found\n%s\n%s"%(sample, f, coll[sample])
        coll[sample] = f
    if options.verbose : print 'input files:\n',sig,'\n',bkg
    assert sig and bkg, "missing signals or backgrounds"
    return sig, bkg

def variablesToPlot() :
    return ['pt0','pt1','mll','mtmin','mtmax','mtllmet','ht','metrel','dphill','detall',
            'mt2j','mljj','dphijj','detajj']

def llnjKey(ll, nj) : return "%s_%s"%(ll, nj)
def histoSuffix(sample, ll, nj) : return "%s_%s_%s"%(sample, ll, nj)

def bookHistos(variables, samples, lls, njs) :
    "book a dict of histograms with keys [sample][ll_nj][var]"
    def histo(variable, suffix) :
        s = suffix
        twopi = +2.0*math.pi
        h = None
        if   v=='pt0'     : h = r.TH1F('h_pt0_'    +s, ';p_{T,l0} [GeV]; entries/bin',          25, 0.0, 250.0)
        elif v=='pt1'     : h = r.TH1F('h_pt1_'    +s, ';p_{T,l1} [GeV]; entries/bin',          25, 0.0, 250.0)
        elif v=='mll'     : h = r.TH1F('h_mll_'    +s, ';m_{l0,l1} [GeV]; entries/bin',         25, 0.0, 250.0)
        elif v=='mtmin'   : h = r.TH1F('h_mtmin_'  +s, ';m_{T,min}(l, MET) [GeV]; entries/bin', 25, 0.0, 400.0)
        elif v=='mtmax'   : h = r.TH1F('h_mtmax_'  +s, ';m_{T,max}(l, MET) [GeV]; entries/bin', 25, 0.0, 400.0)
        elif v=='mtllmet' : h = r.TH1F('h_mtllmet_'+s, ';m_{T}(l+l, MET) [GeV]; entries/bin',   25, 0.0, 600.0)
        elif v=='ht'      : h = r.TH1F('h_ht_'     +s, ';H_{T} [GeV]; entries/bin',             25, 0.0, 800.0)
        elif v=='metrel'  : h = r.TH1F('h_metrel_' +s, ';MET_{rel} [GeV]; entries/bin',         25, 0.0, 300.0)
        elif v=='dphill'  : h = r.TH1F('h_dphill_' +s, ';#Delta#phi(l, l) [rad]; entries/bin',  25, 0.0, twopi)
        elif v=='detall'  : h = r.TH1F('h_detall_' +s, ';#Delta#eta(l, l); entries/bin',        25, 0.0, +3.0 )
        elif v=='mt2j'    : h = r.TH1F('h_mt2j_'   +s, ';m^{J}_{T2} [GeV]; entries/bin',        25, 0.0, 500.0)
        elif v=='mljj'    : h = r.TH1F('h_mljj_'   +s, ';m_{ljj} [GeV]; entries/bin',           25, 0.0, 500.0)
        elif v=='dphijj'  : h = r.TH1F('h_dphijj_' +s, ';#Delta#phi(j, j) [rad]; entries/bin',  25, 0.0, twopi)
        elif v=='detajj'  : h = r.TH1F('h_detajj_' +s, ';#Delta#eta(j, j); entries/bin',        25, 0.0, +3.0 )
        else : print "unknown variable %s"%v
        h.SetDirectory(0)
        return h
    return dict([(s,
                  dict([(llnjKey(ll, nj),
                         dict([(v, histo(v, histoSuffix(s, ll, nj))) for v in variables]))
                         for ll in lls for nj in njs]))
                 for s in samples])

def fillHistosAndCount(histos, files, lls, njs, testRun=False) :
    "Fill the histograms, and provide a dict of event counters[sample][sel] for the summary"
    treename = 'SusySel'
    counts = dict()
    for sample, filename in files.iteritems() :
        countsSample = collections.defaultdict(float)
        histosSample = histos[sample]
        file = r.TFile.Open(filename)
        tree = file.Get(treename)
        nEvents = tree.GetEntries()
        nEventsToProcess = nEvents if not testRun else nEvents/10
        print "processing %s (%d entries %s) %s"%(sample, nEventsToProcess, ", 10% test" if testRun else "", datetime.datetime.now())
        for iEvent, event in enumerate(tree) :
            if iEvent > nEventsToProcess : break
            l0, l1, met, pars = addTlv(event.l0), addTlv(event.l1), addTlv(event.met), event.pars
            jets, lepts = [addTlv(j) for j in event.jets], [addTlv(l) for l in event.lepts]
            ll = getDilepType(l0, l1)
            nJets = len(jets)
            nj = 'eq1j' if nJets==1 else 'ge2j'
            assert nJets>0,"messed something up in the selection upstream"
            if ll not in lls or nj not in njs : continue
            pt0 = l0.p4.Pt()
            pt1 = l1.p4.Pt()
            j0  = jets[0]
            mll  = (l0.p4 + l1.p4).M()
            mtllmet = computeMt(l0.p4 + l1.p4, met.p4)
            ht      = computeHt(met.p4, [l0.p4, l1.p4]+[j.p4 for j in jets])
            metrel  = computeMetRel(met.p4, [l0.p4, l1.p4]+[j.p4 for j in jets])
            mtl0    = computeMt(l0.p4, met.p4)
            mtl1    = computeMt(l1.p4, met.p4)
            mtmin   = min([mtl0, mtl1])
            mtmax   = max([mtl0, mtl1])
            mlj     = computeMlj(l0.p4, l1.p4, j0.p4)
            dphill  = abs(phi_mpi_pi(l0.p4.DeltaPhi(l1.p4)))
            detall  = fabs(l0.p4.Eta() - l1.p4.Eta())
            l3Veto  =  not thirdLepZcandidateIsInWindow(l0, l1, lepts)
            mljj = None
            if nJets >1 :
                j0, j1 = jets[0], jets[1]
                mt2j   = computeMt2j(l0.p4, l1.p4, j0.p4, j1.p4, met.p4)
                mljj   = computeMljj(l0.p4, l1.p4, j0.p4, j1.p4)
                dphijj = fabs(phi_mpi_pi(j0.p4.DeltaPhi(j1.p4)))
                detajj = fabs(j0.p4.Eta() - j1.p4.Eta())
            if passSelection(pt0, pt1, mll, mtllmet, ht, metrel, l3Veto,
                             detall, mtmax, mlj, mljj,
                             ll, nj) :
                llnj = llnjKey(ll, nj)
                weight = pars.weight
                varHistos = histosSample[llnj]
                varValues = dict([(v, eval(v)) for v in variablesToPlot()])
                fillVarHistos(varHistos, varValues, weight, nj)
                countsSample[llnj] += weight
        file.Close()
        file.Delete()
        counts[sample] = countsSample
    return counts

def passSelection(l0pt, l1pt, mll, mtllmet, ht, metrel, l3Veto,
                  detall, mtmax, mlj, mljj,
                  ll, nj) :

    if ll=='mm' and nj=='eq1j':
        return (    l0pt    >  30.0
                and l1pt    >  20.0
                and detall  <   1.5
                and mtmax   > 100.0
                and ht      > 200.0
                and mlj     <  90.0
                and l3Veto
                    )
    elif ll=='mm' and nj=='ge2j':
        return (    l0pt    >  30.0
                and l1pt    >  20.0
                and detall  <   1.5
                and ht      > 220.0
                and mljj    < 120.0
                and l3Veto
                    )
    elif ll=='em' and nj=='eq1j':
        return (    l0pt    >  30.0
                and l1pt    >  30.0
                and detall  <   1.5
                and mtmax   > 110.0
                and mlj     <  90.0
                and mtllmet > 110.0
                and l3Veto
                    )
    elif ll=='em' and nj=='ge2j':
        return (    l0pt    >  30.0
                and l1pt    >  30.0
                and detall  <   1.5
                and mljj    < 120.0
                and mtllmet > 110.0
                and l3Veto
                    )
    elif ll=='ee' and nj=='eq1j':
        return (    l0pt    >  30.0
                and l1pt    >  30.0
                and fabs(mll-91.2) > 10.0
                and mtllmet > 100.0
                and detall  <   1.5
                and mtmax   > 100.0
                and ht      > 200.0
                and mlj     <  90.0
                and l3Veto
                    )
    elif ll=='ee' and nj=='ge2j':
        return (    l0pt    >  30.0
                and l1pt    >  30.0
                and fabs(mll-91.2) > 10.0
                and detall  <   1.5
                and mtllmet > 150.0
                and mljj    < 120.0
                and ht      > 200.0
                and l3Veto
                    )

def fillVarHistos(varHistos, varValues, weight, nj) :
    assert nj in ['eq1j', 'ge2j']
    exclVars = ['mt2j','mljj','dphijj','detajj'] if nj=='eq1j' else ['mlj']
    vars = [v for v in varHistos.keys() if v not in exclVars]
    for v in vars :
        varHistos[v].Fill(varValues[v], weight)

def plotHistos(bkgHistos, sigHistos, plotdir) :
    llnjs = first      (sigHistos).keys()
    vars  = first(first(sigHistos)).keys()
    for llnj in llnjs :
        for var in vars :
            plotVar(dict((s, bkgHistos[s][llnj][var]) for s in bkgHistos.keys()),
                    dict((s, sigHistos[s][llnj][var]) for s in sigHistos.keys()),
                    llnj+'_'+var, plotdir)

def plotVar(bkgHistos, sigHistos, llnjvar, plotdir='./') :
    def preferredSignal(signals):
        pref = 'Herwigpp_sM_wA_noslep_notauhad_WH_2Lep_1'
        return pref if pref in signals else first(sorted(signals))
    signalSample = preferredSignal(sigHistos.keys())
    allHistos = bkgHistos.values() + [sigHistos[signalSample],]
    allHistosEmpty = all([h.GetEntries()==0 for h in allHistos])
    if allHistosEmpty : return
    can = r.TCanvas('can_'+llnjvar, llnjvar, 800, 800)
    botPad, topPad = buildBotTopPads(can, splitFraction=0.75, squeezeMargins=False)
    totBkg = summedHisto(bkgHistos.values())
    totBkg.SetDirectory(0)
    can._totBkg = totBkg
    can._histos = [bkgHistos, sigHistos]
    can.cd()
    botPad.Draw()
    drawBottom(botPad, totBkg, bkgHistos, sigHistos[signalSample], llnjvar)
    can.cd()
    topPad.Draw()
    drawTop(topPad, totBkg, sigHistos[signalSample])
    mkdirIfNeeded(plotdir)
    outFilename = plotdir+'/'+llnjvar+'.png'
    rmIfExists(outFilename) # avoid root warnings
    can.SaveAs(outFilename)

def drawBottom(pad, totBkg, bkgHistos, sigHisto, llnjvar) :
    pad.cd()
    totBkg.SetStats(False)
    totBkg.SetMinimum(0.) # force this to avoid negative fluct due to fake
    totBkg.Draw('axis')
    pad.Update() # necessary to fool root's dumb object ownership
    stack = r.THStack('stack_'+llnjvar,'')
    pad.Update()
    r.SetOwnership(stack, False)
    for s, h in bkgHistos.iteritems() :
        h.SetFillColor(colors[s] if s in colors else r.kOrange)
        h.SetDrawOption('bar')
        h.SetDirectory(0)
        stack.Add(h)
    stack.Draw('hist same')
    pad.Update()
    sigHisto.SetLineColor(r.kRed)
    sigHisto.SetLineWidth(2*sigHisto.GetLineWidth())
    sigHisto.Draw('same')
    pad.Update()
    topRightLabel(pad, llnjvar, xpos=0.125, align=13)
    drawLegendWithDictKeys(pad, dictSum(bkgHistos, {'signal' : sigHisto}), opt='f')
    pad.RedrawAxis()
    pad._stack = stack
    pad._histos = [h for h in stack.GetHists()]
    pad.Update()

def drawTop(pad, hBkg, hSig) :
    nxS, nxB = hSig.GetNbinsX()+1, hBkg.GetNbinsX()+1  # TH1 starts from 1
    assert nxS==nxB,"histos with differen binning (%d!=%d)"%(nxS,nxB)
    pad.SetGridy()
    bcS, bcB = binContentsWithUoflow(hSig), binContentsWithUoflow(hBkg)
    leftToRight = True
    bcLS, bcLB = cumsum(mergeOuter(bcS), leftToRight), cumsum(mergeOuter(bcB), leftToRight),
    leftToRight = False
    bcRS, bcRB = cumsum(mergeOuter(bcS), leftToRight), cumsum(mergeOuter(bcB), leftToRight)
    zn = r.RooStats.NumberCountingUtils.BinomialExpZ
    bkgUnc = 0.3
    znL = [zn(s, b, bkgUnc) if (b>4.0 and s>0.01) else 0.0 for s,b in zip(bcLS, bcLB)]
    znR = [zn(s, b, bkgUnc) if (b>4.0 and s>0.01) else 0.0 for s,b in zip(bcRS, bcRB)]
    leftToRight = max(znL) >= max(znR)
    zn = znL if leftToRight else znR
    hZn = cloneAndFillHisto(hSig, zn, '_zn')
    hCeS = cumEffHisto(hSig, bcLS if leftToRight else bcRS, leftToRight)
    hCeB = cumEffHisto(hBkg, bcLB if leftToRight else bcRB, leftToRight)
    plotCumulativeEfficiencyHisto(pad, hCeS, r.kRed)
    plotCumulativeEfficiencyHisto(pad, hCeB, r.kBlack, False)
    mark = maxSepVerticalLine(hCeS, hCeB)
    mark.SetLineStyle(2)
    mark.Draw()
    gr =  plotZnHisto(pad, hZn, r.kBlue, 0.0, 1.0) # eff go from 0 to 1
    xAx = hSig.GetXaxis()
    x0, x1 = xAx.GetBinLowEdge(xAx.GetFirst()), xAx.GetBinUpEdge(xAx.GetLast())
    midline = r.TLine(x0, 0.5, x1, 0.5)
    midline.SetLineStyle(2)
    midline.SetLineColor(r.kGray)
    midline.Draw()
    pad._obj = [hCeS, hCeB, mark, gr, midline]

def plotCumulativeEfficiencyHisto(pad, h, linecolor=r.kBlack, isPadMaster=True) :
    pad.cd()
    h.SetLineColor(linecolor)
    h.SetLineWidth(2)
    isPadMaster = isPadMaster or 0==len([o for o in pad.GetListOfPrimitives()]) # safety net
    drawOption = 'l' if isPadMaster else 'lsame'
    if isPadMaster :
        xA, yA = h.GetXaxis(), h.GetYaxis()
        xA.SetLabelSize(0)
        xA.SetTitle('')
        yA.SetNdivisions(-201)
        yA.SetTitle('eff')
        yA.SetLabelSize(yA.GetLabelSize()*1.0/pad.GetHNDC())
        yA.SetTitleSize(yA.GetTitleSize()*1.0/pad.GetHNDC())
        yA.SetTitleOffset(yA.GetTitleOffset()*pad.GetHNDC())
        yA.CenterTitle()
    h.Draw(drawOption)
    h.SetStats(0)
    return h

def plotZnHisto(pad, h, linecolor=r.kBlack, minY=0.0, maxY=1.0) :
    pad.cd()
    h.SetLineColor(linecolor)
    h.SetLineWidth(2)
    h.SetLineStyle(2)
    bc = [h.GetBinContent(i+1) for i in range(h.GetNbinsX())]
    minZn, maxZn = min(bc), max(bc)
    invalidRange = not minZn and not maxZn
    bc = linearTransform(bc+[0.], [minY, maxY])[:-1] # add one 0 so that the min is at least 0
    for i,b in enumerate(bc) : h.SetBinContent(i+1, b)
    h.Draw('lsame')
    x = h.GetXaxis().GetXmax()
    ax = r.TGaxis(x, minY, x, maxY, 0.0 if invalidRange else minZn, 1.0 if invalidRange else maxZn, 001, "+L")
    ax.SetTitle('Z_{n}')
    ax.CenterTitle()
    ax.SetLabelSize(ax.GetLabelSize()*1.0/pad.GetHNDC())
    ax.SetTitleSize(ax.GetTitleSize()*1.0/pad.GetHNDC())
    ax.SetTitleOffset(ax.GetTitleOffset()*pad.GetHNDC())
    ax.SetLineColor(linecolor)
    ax.SetTitleColor(linecolor)
    ax.SetLabelColor(linecolor)
    ax.Draw()
    return [h, ax]

def printSummary(counts, outfilename='') :
    samples = counts.keys()
    signal = [s for s in samples if isSigSample(s)][0]
    counts = renameDictKey(counts, signal, 'signal')
    samples = counts.keys()
    selections = sorted(first(counts).keys())
    def isSignal(s) : return isSigSample(s) or s=='signal'
    if 'totbkg' not in counts :
        counts['totbkg'] = dict([(sel, sum(countsSample[sel]
                                           for sam, countsSample in counts.iteritems() if not isSignal(sam)))
                                 for sel in first(counts).keys()])
    bkgUnc = 0.30
    zn = r.RooStats.NumberCountingUtils.BinomialExpZ
    counts['Zn'] = dict([(sel, zn(counts['signal'][sel], counts['totbkg'][sel], bkgUnc)) for sel in selections])
    firstThreeColumns = ['Zn', 'signal', 'totbkg']
    otherSamples = sorted([s for s in samples if s not in firstThreeColumns])
    table = CutflowTable(firstThreeColumns + otherSamples, selections, counts)
    table.nDecimal = 2
    if outfilename :
        with open(outfilename, 'w') as f :
            f.write('\n'+table.latex()+'\n')
    else :
        print
        print table.latex()


if __name__=='__main__' :
    optimizeSelection()
