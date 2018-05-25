#!/usr/bin/env python
# --------------------------------------------------------
#       Class to align the DUT and REF events of the Rate Pixel Analysis
# created on February 13th 2017 by M. Reichmann (remichae@phys.ethz.ch)
# --------------------------------------------------------

from ROOT import TFile, vector, TProfile
from numpy import mean
from Utils import log_message, time, print_elapsed_time, OrderedDict
from progressbar import Bar, ETA, FileTransferSpeed, Percentage, ProgressBar
from sys import argv
from datetime import datetime
from sys import stdout


class PadAlignment:
    def __init__(self, converter, filename=None):
        # main
        self.StartTime = time()
        self.NDutPlanes = 4
        self.Threshold = .4
        # progress bar
        self.Widgets = ['Progress: ', Percentage(), ' ', Bar(marker='>'), ' ', ETA(), ' ', FileTransferSpeed()]
        self.ProgressBar = None
        if filename is None:
            self.Converter = converter
            self.Run = converter.Run
            # files/trees
            self.InFile = TFile(converter.get_root_file_path())
            self.InTree = self.InFile.Get(self.Run.treename)
        else:
            self.Run = self.Run()
            self.InFile = TFile(filename)
            self.InTree = self.InFile.Get('tree')

        self.NewFile = None
        self.NewTree = None
        # alignment
        self.NEntries = int(self.InTree.GetEntries())
        self.AtEntry = 0
        self.IsAligned = self.check_alignment()
        if not self.IsAligned:
            # branches
            self.Branches = self.init_branches()
            self.BranchLists = {name: [] for name in self.Branches}
            # info
            self.ColSize = []
            self.PulserEvents = []
            self.load_variables()
            self.BucketSize = 30

    def __del__(self):
        self.InFile.Close()
        print_elapsed_time(self.StartTime, 'Pad Alignment')

    @staticmethod
    def init_branches():
        dic = OrderedDict()
        dic['plane'] = vector('unsigned short')()
        dic['col'] = vector('unsigned short')()
        dic['row'] = vector('unsigned short')()
        dic['adc'] = vector('short')()
        dic['charge'] = vector('unsigned int')()
        return dic

    def load_variables(self):
        """ get all the telescope branches in vectors"""
        t = self.Run.log_info('Loading information from tree ... ', next_line=False)
        self.InTree.SetEstimate(self.InTree.Draw('plane', '', 'goff'))
        dic = {name: None for name in self.BranchLists}
        n = self.InTree.Draw('plane:row:col', '', 'goff')
        dic['plane'] = [int(self.InTree.GetV1()[i]) for i in xrange(n)]
        dic['row'] = [int(self.InTree.GetV2()[i]) for i in xrange(n)]
        dic['col'] = [int(self.InTree.GetV3()[i]) for i in xrange(n)]
        n = self.InTree.Draw('adc:charge', '', 'goff')
        dic['adc'] = [int(self.InTree.GetV1()[i]) for i in xrange(n)]
        dic['charge'] = [int(self.InTree.GetV2()[i]) for i in xrange(n)]
        n = self.InTree.Draw('@plane.size()', '', 'goff')
        self.ColSize = [int(self.InTree.GetV1()[i]) for i in xrange(n)]
        n = self.InTree.Draw('Entry$', 'pulser', 'goff')
        self.PulserEvents = [int(self.InTree.GetV1()[i]) for i in xrange(n)]
        n_hits = 0
        for size in self.ColSize:
            for name, lst in dic.iteritems():
                self.BranchLists[name].append(lst[n_hits:size + n_hits])
            n_hits += size
        self.Run.add_info(t)

    def check_alignment(self, binning=1000):
        """ just check the zero correlation """
        nbins = self.NEntries / binning
        h = TProfile('h', 'Pulser Rate', nbins, 0, self.NEntries)
        self.InTree.Draw('(@col.size()>1)*100:Entry$>>h', 'pulser', 'goff')
        aligned = all(h.GetBinContent(bin_) < 40 for bin_ in xrange(h.GetNbinsX()))
        if not aligned:
            self.Run.log_info('Fast check found misalignment :-(')
        return aligned

    def find_offset(self, start, offset, n_events=None, n_offsets=5):
        offsets = sorted(range(-n_offsets, n_offsets + 1), key=lambda x: abs(x))
        offsets.pop(offsets.index(0))
        stop = self.BucketSize / 2 if n_events is None else n_events
        means = OrderedDict((i, self.calc_mean_size(start, i + offset, stop)) for i in offsets)
        # if we don't have beam in the beginning we cannot find out the offset
        # print ['{0:2.2f}'.format(i) for i in means.values()]
        if all(value < self.Threshold for value in means.itervalues()):
            return 0
        try:
            return next(key for key, value in means.iteritems() if value < self.Threshold)
        except StopIteration:
            return 0

    def calc_mean_size(self, start, off=0, n=None):
        n = n if n is not None else self.BucketSize
        return mean([self.ColSize[ev + off] > 3 for ev in self.PulserEvents[start:start + n]])

    def find_error_offset(self, i, offset):
        for ev in self.Converter.ErrorEvents:
            if self.PulserEvents[i - self.BucketSize / 2] < ev < self.PulserEvents[i + self.BucketSize / 2]:
                return ev, self.find_offset(self.PulserEvents.index(next(pev for pev in self.PulserEvents if pev > ev)), offset)
        return None, None

    def find_shifting_offsets(self):
        t = self.Run.log_info('Scanning for precise offsets ... ', next_line=False)
        n = self.BucketSize
        offset = self.find_offset(0, 0)
        # add first offset
        offsets = OrderedDict([(0, offset)] if offset else [])
        rates = [self.calc_mean_size(0)]
        # print offsets
        i = 1
        while i < len(self.PulserEvents) - abs(offset) - n:
            rate = self.calc_mean_size(i, offset)
            # print i, '{0:1.2f}'.format(rate)
            if rate > self.Threshold:
                # first check if the event is in the decoding errors
                off_event, this_offset = self.find_error_offset(i, offset)
                if off_event is None:
                    # assume that the rate was good n/2 events before
                    good_rate = rates[-n / 2] if len(rates) > n / 2 else .1
                    for j, r in enumerate(rates[-n / 2:]):
                        if r > good_rate + .1:
                            # i + j - n/2 + n is the first misaligned event
                            off_event = self.PulserEvents[i + j - 1 + n / 2]
                            this_offset = self.find_offset(i + j - 1 + n / 2, offset)
                            if this_offset:
                                i += j - 1 + n / 2
                                break
                if this_offset:
                    print 'Found offset:', off_event, this_offset
                    offsets[off_event] = this_offset
                    offset += this_offset
            rates.append(rate)
            i += 1
            if len(rates) > n:
                del rates[0]

        self.Run.add_info(t)
        log_message('Found {n} offsets'.format(n=len(offsets)))
        return offsets

    # =======================================================
    # region WRITE TREE
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
        macro = self.InFile.Get('region_information')
        if macro:
            macro.Write()
        self.NewFile.Write()

    def clear_vectors(self):
        for vec in self.Branches.itervalues():
            vec.clear()

    def write_aligned_tree(self):
        offsets = self.find_shifting_offsets()
        self.NewFile = TFile(self.Converter.get_root_file_path(), 'RECREATE')
        self.NewTree = self.InTree.CloneTree(0)
        self.set_branch_addresses()
        self.start_pbar(self.NEntries)
        offset = 0
        while self.get_next_event():
            entry = self.AtEntry - 1
            self.ProgressBar.update(self.AtEntry)
            self.clear_vectors()
            if entry in offsets:
                offset += offsets[entry]
            if entry > self.NEntries - offset - 1:
                break
            for name, lst in self.BranchLists.iteritems():
                for value in lst[entry + offset]:
                    self.Branches[name].push_back(value)
            self.NewTree.Fill()
        self.ProgressBar.finish()
        self.save_tree()
    # endregion

    class Run:
        def __init__(self):
            pass

        @staticmethod
        def log_info(msg, next_line=True):
            t1 = time()
            t = datetime.now().strftime('%H:%M:%S')
            print 'INFO: {t} --> {msg}'.format(t=t, msg=msg),
            stdout.flush()
            if next_line:
                print
            return t1

        @staticmethod
        def add_info(t, msg='Done'):
            print '{m} ({t:2.2f} s)'.format(m=msg, t=time() - t)

    def start_pbar(self, n):
        self.ProgressBar = ProgressBar(widgets=self.Widgets, maxval=n)
        self.ProgressBar.start()


if __name__ == '__main__':
    print argv[1]
    z = PadAlignment(None, argv[1])
