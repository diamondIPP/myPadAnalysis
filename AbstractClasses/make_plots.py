#!/usr/bin/python

from AnalysisCollection import AnalysisCollection
from Elementary import Elementary
from RunSelection import RunSelection
from Utils import round_down_to
from screeninfo import get_monitors
from glob import glob
from os import remove
from argparse import ArgumentParser
from collections import OrderedDict


parser = ArgumentParser()
parser.add_argument('tc', nargs='?', default='10')
args = parser.parse_args()

m = get_monitors()
res = round_down_to(m[0].height, 500)

tc = '2015' + args.tc.zfill(2)
a = Elementary(tc, False, res)
a.print_banner('STARTING RATE SCAN PLOT GENERATION')


def load_collection(plan, channel):
    sel = RunSelection(testcampaign=tc)
    sel.select_runs_from_runplan(plan)
    a.print_testcampaign()
    ana = AnalysisCollection(sel, channel)
    ana.save_dir = '{info}_rp{rp}'.format(info=ana.make_info_string().strip('_'), rp=float(ana.RunPlan))
    ana.set_save_directory('PlotsFelix')
    return ana


def del_redundant_plots(res_dir, save_dir):
    for f in glob('{0}{1}/*/*'.format(res_dir, save_dir)):
        name = f.split('/')[-1]
        for start in ['PulseHeightTime', 'PulseHeightZeroTime', 'PulserMean', 'PulseHeightFlu', 'PulseHeightZeroFlu']:
            if name.startswith(start):
                remove(f)


if args.tc == '10':
    runplans = OrderedDict(sorted({3: [1], 5: [1], 8.1: [1, 2], 10.1: [1, 2]}.iteritems()))
    upscans = OrderedDict(sorted({3: [1], 5: [1], 8.2: [1, 2], 10.2: [1, 2]}.iteritems()))

else:
    runplans = OrderedDict(sorted({2: [2], 5.3: [1], 13: [2]}.iteritems()))
    upscans = OrderedDict(sorted({2.1: [2], 5.2: [1], 13.1: [2]}.iteritems()))


for rp, chs in runplans.iteritems():

    for ch in chs:
        a.print_banner('Starting AnalysisCollection for rp {0} and ch {1}'.format(rp, ch), '-')
        z = load_collection(rp, ch)
        z.print_loaded()
        z.draw_ph_with_currents(show=False)
        z.draw_pulse_heights(show=False, save_plots=True)
        z.draw_pulser_info(show=False, do_fit=False)
        z.draw_ph_distributions_below_flux(flux=80, show=False, save_plot=True)
        del_redundant_plots(z.results_directory, z.save_dir)
        z.close_files()
        z.__del__()

for rp, chs in upscans.iteritems():

    for ch in chs:
        a.print_banner('Starting AnalysisCollection for rp {0} and ch {1}'.format(rp, ch), '-')
        z = load_collection(rp, ch)
        z.draw_signal_distributions(show=False, off=200)
        if rp == 3 or rp == 8:
            z.draw_all_chi2s(show=False)
            z.draw_both_angles(show=False)
        z.close_files()
        z.__del__()
