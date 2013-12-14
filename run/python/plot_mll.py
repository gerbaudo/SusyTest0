#!/bin/env python

import array
import glob
import math
import os
import ROOT as r
r.gROOT.SetStyle('Plain')
r.gROOT.SetBatch(True)                     # no windows popping up
r.PyConfig.IgnoreCommandLineOptions = True # don't let root steal our cmd-line options


inputDir = 'out/susyplot/merged'
histoName = 'cr8lpt_mm_ll_M_NOM'
tag = 'Dec_13'
samples = ['diboson', 'heavyflavor', 'ttbar', 'wjets', 'zjets']
colors = {
    'ttbar'       : r.kRed+1,
    'zjets'       : r.kOrange-2,
    'wjets'       : r.kBlue-2,
    'diboson'     : r.kSpring+2,
    'singletop'   : r.kAzure-4,
    'multijet'    : r.kGray,
    'fake'        : r.kGray, # just another name for the same thing
    'heavyflavor' : r.kViolet+1
        }


files = dict([(s, r.TFile.Open(inputDir+'/'+s+'_'+tag+'.root')) for s in samples])
files['data'] = r.TFile.Open(inputDir+'/'+'Muons'+'_'+tag+'.root')
histos = dict([(s, f.Get(histoName)) for s,f in files.iteritems()])

c = r.TCanvas('name','title',800,600)
c.cd()
stack = r.THStack('stack_'+histoName, '')
leg = r.TLegend(0.65, 0.65, 0.9, 0.9)
leg.SetBorderSize(0)
leg.SetFillColor(0)

for s,h in histos.iteritems() :
    isMc, isData = s in samples, s=='data'
    if isMc :
        h.SetDrawOption('bar')
        h.SetMarkerSize(0)
        h.SetFillColor(colors[s])
        h.SetLineColor(colors[s])
        stack.Add(h)
    if isData :
        h.SetMarkerStyle(r.kFullCircle)
    leg.AddEntry(h, "%s : %.1f"%(s, h.GetEntries()), 'f')

hData = histos['data']
padMaster = hData
padMaster.Draw('axis')
stack.Draw('hist')
padMaster.Draw()
stack.Draw('hist same')

# hData.Draw('p same')

# print padMaster.GetMaximum()
leg.Draw()
c.Update()
c.SaveAs(histoName+'.png')
