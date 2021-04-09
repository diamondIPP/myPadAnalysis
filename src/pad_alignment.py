#!/usr/bin/env python
# --------------------------------------------------------
#       Class to align the DUT and REF events of the Rate Pixel Analysis
# created on February 13th 2017 by M. Reichmann (remichae@phys.ethz.ch)
# --------------------------------------------------------
from numpy import histogram2d, sum, invert
from src.event_alignment import *
from src.binning import make_bins
from helpers.draw import get_hist_vec, get_hist_vecs, ax_range


class PadAlignment(EventAligment):
    def __init__(self, converter):

        # Info
        self.Threshold = .4
        self.Pulser = array([])
        self.PulserEvents = array([])
        self.FirstOffset = None
        self.BinSize = 30
        self.NMaxHits = 3

        EventAligment.__init__(self, converter)

        if not self.IsAligned:
            self.PulserRate = self.get_pulser_rate()
            self.BeamInterruptions = self.get_beam_interruptions()
            self.NMaxHits = mean(self.load_n_hits()) / (1 - self.PulserRate.n)

    # ----------------------------------------
    # region INIT
    def print_start(self):
        print_banner('STARTING PAD EVENT ALIGNMENT OF RUN {}'.format(self.Run.Number))

    @staticmethod
    def init_branches():
        return EventAligment.init_branches() + [('trigger_phase', zeros(1, 'u1'), 'trigger_phase/b')]

    def load_variables(self):
        data = super(PadAlignment, self).load_variables()
        t = self.Run.info('Loading pad information from tree ... ', endl=False)
        self.Pulser = self.get_pulser()
        self.PulserEvents = where(self.Pulser)[0]
        self.FirstOffset = self.find_start_offset()
        tp = get_tree_vec(self.InTree, 'trigger_phase', dtype='u1')
        self.Run.add_to_info(t)
        return data + [tp]

    def get_aligned(self, tree=None, bin_size=1000):
        x, y = get_tree_vec(choose(tree, self.InTree), dtype='u4', var=['Entry$', self.get_hit_var()], cut='pulser')
        bins = histogram2d(x, y >= self.NMaxHits, bins=[self.NEntries // bin_size, [0, .5, 50]])[0]  # histogram the data to not over-count the empty events
        bin_average = bins[:, 1] / sum(bins, axis=1)
        return bin_average < self.Threshold

    def check_alignment_fast(self, bin_size=1000):
        """ just check the zero correlation """
        align = self.get_aligned(bin_size=bin_size)
        self.Run.info(f'{calc_eff(values=invert(align))[0]:.1f}% of the events are misaligned :-(' if not all(align) else f'Run {self.Run.Number} is perfectly aligned :-)')
        return all(align)
    # endregion INIT
    # ----------------------------------------

    def fill_branches(self, ev):
        n = self.NHits[ev]
        hits = sum(self.NHits[:ev])
        self.Branches[0][1][0] = n  # n hits
        for i in range(1, 6):
            self.Branches[i][1][:n] = self.Variables[i - 1][hits:hits + n]
        self.Branches[-1][1][0] = self.Variables[-1][ev]  # trigger phase

    def get_pulser(self):
        return get_tree_vec(self.InTree, 'pulser', dtype='?')

    def get_pulser_rate(self):
        x = self.get_pulser()
        values = get_hist_vec(self.Run.Draw.profile(arange(x.size), x, make_bins(0, x.size, 100), show=False))
        return mean_sigma(values[values < mean(x) + .2])[0]

    def get_beam_interruptions(self, bin_size=100):
        x = self.get_pulser()
        values = array(get_hist_vec(self.Run.Draw.profile(arange(x.size), x, make_bins(0, x.size, bin_size, last=True), show=False)) < mean(x) + .1)
        high = where(values == 0)[0]
        values[high[high > 0] - 1] = False  # set bins left and right also to zero
        values[high[high < high.size - 1] + 1] = False
        return values.repeat(bin_size)[:self.NEntries]

    def set_offset(self, pulser_event, offset):
        errors = self.Converter.DecodingErrors
        event = errors[(self.PulserEvents[pulser_event - 5] < errors) & (self.PulserEvents[pulser_event + 5] > errors)]
        self.Offsets[event[0] if event.size else self.PulserEvents[pulser_event]] = offset

    def get_cut(self, event, n):
        events = where(self.BeamInterruptions[self.Pulser])[0]
        return events[event:event + n] if event >= 0 else events[event * n:(event + 1) * n]

    # ----------------------------------------
    # region OFFSETS
    def find_offset(self, off=-5, event=0, n=None):
        aligned = mean(self.NHits[roll(self.Pulser, off)][self.get_cut(event, choose(n, self.BinSize))] > self.NMaxHits) < .1
        return off if aligned else self.find_offset(off + 1, event, n)

    def find_final_offset(self, off=-500, n_bins=-2):
        """return the offset at the end of the run"""
        try:
            return self.find_offset(off, event=n_bins)
        except RecursionError:
            critical(f'Event alignment seriously fucked up ... remove run {self.Run.Number}')

    def find_start_offset(self, off=-5):
        return self.find_offset(off)

    def find_offsets(self, off=0, delta=1):
        start = self.find_offsets(off - delta, delta) if off != self.FirstOffset else 0
        if start:
            self.set_offset(start, off)
        y = array(self.NHits[roll(self.Pulser, off)][start:] > self.NMaxHits)
        v = mean(y[:y.size // self.BinSize * self.BinSize].reshape(y.size // self.BinSize, self.BinSize), axis=1)
        bad = where(v > self.Threshold)[0]
        if not bad.size:
            return info(f'found all offsets ({len(self.Offsets) + 1}) :-) ')
        n = bad[0]
        y0 = y[n * self.BinSize:(n + 1) * self.BinSize]
        three_consecutive = where(y0 & (roll(y0, -1) == y0) & (roll(y0, -2) == y0))[0]  # find events with three misaligned in a row
        return start if not three_consecutive.size else three_consecutive[0] + n * self.BinSize + start
    # endregion OFFSETS
    # ----------------------------------------

    def draw_pulser(self, bin_size=1000, cut=..., show=True):
        x = arange(self.NEntries)[cut]
        return self.Run.Draw.efficiency(x, self.get_pulser()[cut], make_bins(0, max(x), bin_size), draw_opt='alx', show=show)

    def draw_hits(self, bin_size=1000, cut=..., show=True):
        x = arange(self.NEntries)[cut]
        self.Draw(self.Draw.make_graph_from_profile(self.Draw.profile(x, self.NHits[cut], make_bins(0, max(x), bin_size), show=False)), show=show, draw_opt='alx')

    def draw(self, off=0, bin_size=None, show=True):
        p = roll(self.get_pulser(), off) & self.get_beam_interruptions()
        x, y = arange(self.NEntries)[p], self.load_n_hits()[p]
        x, y = get_hist_vecs(self.Run.Draw.profile(x, y, make_bins(0, max(x), int(choose(bin_size, self.BinSize / self.get_pulser_rate().n))), show=0))
        return self.Draw.graph(x, y, x_tit='Event Number', y_tit='N Hits @ Pulser', w=2, show=show, draw_opt='alx', y_range=ax_range(0, max(max(y).n, 5), .1, .3))


if __name__ == '__main__':

    from pad_run import PadRun
    from converter import Converter

    # examples: 7(201708)
    args = init_argparser(run=7)
    zrun = PadRun(args.run, testcampaign=args.testcampaign, load_tree=False, verbose=True)
    z = PadAlignment(Converter(zrun))
