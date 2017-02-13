#!/usr/bin/env python
# --------------------------------------------------------
#       Class to align the DUT and REF events of the Rate Pixel Analysis
# created on February 13th 2017 by M. Reichmann (remichae@phys.ethz.ch)
# --------------------------------------------------------

from ROOT import TFile, TH1F, vector
from collections import OrderedDict, Counter
from numpy import corrcoef, ceil
from Utils import set_root_output, log_message, print_banner
from progressbar import Bar, ETA, FileTransferSpeed, Percentage, ProgressBar


class PixAlignment:
    def __init__(self, converter):
        # main
        self.Converter = converter
        self.Run = converter.Run
        self.NDutPlanes = 4
        # files/trees
        self.InFile = TFile(converter.get_root_file_path())
        self.InTree = self.InFile.Get(self.Run.treename)
        self.NewFile = None
        self.NewTree = None
        # info
        self.Row1 = None
        self.Row2 = None
        self.load_rows()
        # alignment
        self.NEntries = int(self.InTree.GetEntries())
        self.AtEntry = 0
        # branches
        self.Branches = self.init_branches()
        # progress bar
        self.Widgets = ['Progress: ', Percentage(), ' ', Bar(marker='>'), ' ', ETA(), ' ', FileTransferSpeed()]
        self.ProgressBar = None

    def __del__(self):
        self.InFile.Close()

    def start_pbar(self, n):
        self.ProgressBar = ProgressBar(widgets=self.Widgets, maxval=n)
        self.ProgressBar.start()

    @staticmethod
    def init_branches():
        dic = OrderedDict()
        dic['plane'] = vector('unsigned short')()
        dic['col'] = vector('unsigned short')()
        dic['row'] = vector('unsigned short')()
        dic['adc'] = vector('short')()
        dic['charge'] = vector('unsigned int')()
        return dic

    def load_rows(self):
        self.InTree.SetEstimate(self.InTree.Draw('plane', '', 'goff'))
        x, y = OrderedDict(), OrderedDict()
        p1, p2 = 2, 4
        n = self.InTree.Draw('plane:row:event_number', '', 'goff')
        planes = [int(self.InTree.GetV1()[i]) for i in xrange(n)]
        rows = [int(self.InTree.GetV2()[i]) for i in xrange(n)]
        nrs = Counter([int(self.InTree.GetV3()[i]) for i in xrange(n)])
        n_ev = 0
        for ev, size in sorted(nrs.iteritems()):
            plane = planes[n_ev:size + n_ev]
            row = rows[n_ev:size + n_ev]
            if plane.count(p1) == 1:
                x[ev] = row[plane.index(p1)]
            if plane.count(p2) == 1:
                y[ev] = row[plane.index(p2)]
            n_ev += size
        self.Row1 = x
        self.Row2 = y

    def check_alignment(self):
        xt, yt = [], []
        for ev, row in self.Row1.iteritems():
            if ev in self.Row2:
                xt.append(row)
                yt.append(self.Row2[ev])
        correlations = [corrcoef(xt[i:100 + i], yt[i:100 + i])[0][1] for i in xrange(int(ceil(len(xt) / 100.)))]
        h = TH1F('h_ee', 'Event Alignment', len(correlations) / 2, 0, 1)
        for cor in correlations:
            h.Fill(cor)
        set_root_output(0)
        fit = h.Fit('gaus', 'qs', '', .6, 1)
        self.Run.format_histo(h, x_tit='Correlation Factor', y_tit='Number of Entries', y_off=1.4, stats=0)
        self.Run.save_histo(h, 'EventAlignmentControl', show=True, lm=.13)
        mean, sigma = fit.Parameter(1), fit.Parameter(2)
        low_events = [cor for cor in correlations if cor < mean - 5 * sigma]
        misalignments = len(low_events) / float(len(correlations))
        if misalignments > .02:
            log_message('found {v:5.2f}% misalignet events'.format(v=misalignments * 100))
            return False
        low_events = [cor for cor in correlations if cor < .3]
        misalignments = len(low_events) / float(len(correlations))
        if misalignments > .05:
            log_message('found {v:5.2f}% misalignet events'.format(v=misalignments * 100))
        return misalignments < .05

    def get_next_event(self):
        if self.AtEntry == self.NEntries:
            return False
        self.InTree.GetEntry(self.AtEntry)
        self.AtEntry += 1
        return True

    def set_branch_addresses(self):
        for name, branch in self.Branches.iteritems():
            self.NewTree.SetBranchAddress(name, branch)

    def save_tree(self):
        self.NewFile.cd()
        self.NewTree.Write()
        self.NewFile.Write()

    def clear_vectors(self):
        for vec in self.Branches.itervalues():
            vec.clear()

    def write_aligned_tree(self):
        print_banner('ALIGNING SHIT')
        # self.NewFile = TFile(self.Converter.get_root_file_path(), 'RECREATE')
        self.NewFile = TFile('test.root', 'RECREATE')
        self.NewTree = self.InTree.CloneTree(0)
        # self.NewTree = TTree(self.InTree.GetName, self.InTree.GetTitle())
        self.set_branch_addresses()
        self.start_pbar(self.NEntries)
        while self.get_next_event():
            self.ProgressBar.update(self.AtEntry)
            self.clear_vectors()
            for i in xrange(len(self.InTree.plane)):
                self.Branches['plane'].push_back(i)
                self.Branches['col'].push_back(i)
                self.Branches['row'].push_back(i)
                self.Branches['adc'].push_back(i)
                self.Branches['charge'].push_back(i)
            self.NewTree.Fill()
        self.save_tree()
