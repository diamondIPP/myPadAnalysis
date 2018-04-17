# ====================================
# IMPORTS
# ====================================
from glob import glob
from json import load

from Elementary import Elementary
from RunSelection import RunSelection
from ROOT import TCanvas, TGraph, TProfile, TH1F
from ConfigParser import ConfigParser
from argparse import ArgumentParser

from Utils import *

# ====================================
# CONSTANTS
# ====================================
axis_title_size = 0.06
label_size = .04
title_offset = 0.8
col_vol = 602  # 807
col_cur = 899  # 418
pad_margins = [.065, .09, .15, .1]


# ====================================
# CLASS FOR THE DATA
# ====================================
class Currents(Elementary):
    """reads in information from the keithley log file"""

    def __init__(self, analysis, averaging=False, points=10, dia=None, start_run=None, verbose=False):
        self.Analysis = analysis
        self.IsCollection = hasattr(analysis, 'Runs')
        Elementary.__init__(self, verbose=verbose)

        self.DoAveraging = averaging
        self.Points = points

        # config
        self.ConfigParser = self.load_parser()
        if self.ConfigParser is None:
            return

        # analysis/run info
        if self.IsCollection:
            self.RunPlan = analysis.RunPlan
        self.RunNumber = self.load_run_number()
        self.RunLogs = self.load_runlogs()
        if analysis is not None:
            self.RunInfo = analysis.run.RunInfo if not self.IsCollection else analysis.FirstAnalysis.RunInfo
            self.Channel = analysis.channel
        # todo: add a method to extract the currents for may
        if 'dia1supply' not in self.RunInfo:
            return
        self.DiamondName = self.load_dia_name()
        self.DiamondNumber = self.load_dia_number()
        self.Bias = self.load_bias()
        self.StartRun = start_run
        self.StartTime = self.load_start_time()
        self.StopTime = self.load_stop_time()

        # device info
        self.Number = self.get_device_nr(dia)
        self.Channel = self.get_device_channel(dia)
        self.Brand = self.ConfigParser.get('HV' + self.Number, 'name').split('-')[0].strip('0123456789')
        self.Model = self.ConfigParser.get('HV' + self.Number, 'model')
        self.Name = '{0} {1}'.format(self.Brand, self.Model)

        self.DataPath = self.find_data_path()
        self.OldDataPath = self.find_data_path(old=True)
        self.LogNames = None

        # data
        self.Currents = []
        self.IgnoreJumps = True
        self.Voltages = []
        self.Time = []
        self.MeanCurrent = 0
        self.MeanVoltage = 0

        # plotting
        self.CurrentGraph = None
        self.VoltageGraph = None
        self.Margins = None
        # graph pads
        self.VoltagePad = None
        self.CurrentPad = None
        self.TitlePad = None
        self.Histos = {}
        self.Stuff = []

    # ==========================================================================
    # region INIT
    def load_dia_name(self):
        return self.Analysis.DiamondName if self.Analysis is not None else None

    def load_dia_number(self):
        if self.Analysis is not None:
            return self.Analysis.DiamondNumber if not self.IsCollection else self.Analysis.FirstAnalysis.DiamondNumber

    def load_bias(self):
        if hasattr(self.Analysis, 'Type') and 'voltage' in self.Analysis.Type:
            return ''
        elif self.Analysis is not None:
            return self.Analysis.Bias

    def load_run_number(self):
        nr = None
        if self.Analysis is not None:
            nr = self.Analysis.RunNumber if not self.IsCollection else self.Analysis.RunPlan
        return nr

    def load_runlogs(self):
        filename = self.Analysis.run.runinfofile if not self.IsCollection else self.Analysis.FirstAnalysis.run.runinfofile
        try:
            f = open(filename)
            data = load(f)
            f.close()
        except IOError as err:
            log_warning('{err}\nCould not load default RunInfo!'.format(err=err))
            return None
        run_logs = OrderedDict(sorted(data.iteritems()))
        return run_logs

    def load_parser(self):
        parser = ConfigParser()
        if self.run_config_parser.has_option('BASIC', 'hvconfigfile'):
            file_path = self.run_config_parser.get('BASIC', 'hvconfigfile')
        else:
            file_path = join(self.DataDir, self.generate_tc_directory(), 'HV.cfg')
        if not file_exists(file_path):
            log_warning('HV info file "{f}" does not exist'.format(f=file_path))
            return None
        parser.read(file_path)
        self.log_info('HV Devices: {0}'.format([name for name in parser.sections() if name.startswith('HV')]))
        return parser

    def get_device_nr(self, dia):
        if self.Analysis is None:
            try:
                full_str = self.RunLogs[self.StartRun]['dia{0}supply'.format(dia)]
                return str(full_str.split('-')[0])
            except KeyError:
                return dia
        full_str = self.RunInfo['dia{dia}supply'.format(dia=self.DiamondNumber)]
        return str(full_str.split('-')[0])

    def get_device_channel(self, dia):
        if self.Analysis is None:
            full_str = self.RunLogs[self.StartRun]['dia{dia}supply'.format(dia=dia)]
            return full_str.split('-')[1] if len(full_str) > 1 else '0'
        full_str = self.RunInfo['dia{dia}supply'.format(dia=self.DiamondNumber)]
        return full_str.split('-')[1] if len(full_str) > 1 else '0'

    def find_data_path(self, old=False):
        if self.run_config_parser.has_option('BASIC', 'hvdatapath'):
            hv_datapath = self.run_config_parser.get('BASIC', 'hvdatapath')
        else:
            hv_datapath = join(self.DataDir, self.generate_tc_directory(), 'HVClient')
        if not dir_exists(hv_datapath):
            log_warning('HV data path "{p}" does not exist!'.format(p=hv_datapath))
        hv_datapath = join(hv_datapath, '{dev}_CH{ch}' if not old else '{dev}')
        return hv_datapath.format(dev=self.ConfigParser.get('HV' + self.Number, 'name'), ch=self.Channel)

    def load_start_time(self):
        ana = self.Analysis.FirstAnalysis if self.IsCollection else self.Analysis
        if ana is None:
            return
        t = datetime.fromtimestamp(ana.run.StartTime) if hasattr(ana.run, 'StartTime') else ana.run.LogStart
        return ana.run.LogStart if t.year < 2000 or t.day != ana.run.LogStart.day else t

    def load_stop_time(self):
        ana = self.Analysis.get_last_analysis() if self.IsCollection else self.Analysis
        if ana is None:
            return
        t = datetime.fromtimestamp(ana.run.EndTime) if hasattr(ana.run, 'EndTime') else ana.run.LogEnd
        return ana.run.LogEnd if t.year < 2000 or t.day != ana.run.LogEnd.day else t

    def set_start_stop(self, sta, sto=None):
        if not sta.isdigit():
            start_string = '{y}/{s}'.format(y=self.TESTCAMPAIGN[:4], s=sta)
            stop_string = '{y}/{e}'.format(y=self.TESTCAMPAIGN[:4], e=sto)
            self.StartTime = datetime.strptime(start_string, '%Y/%m/%d-%H:%M:%S')
            self.StopTime = datetime.strptime(stop_string, '%Y/%m/%d-%H:%M:%S')
        elif sto is None:
            self.StartRun = sta
            run = sta
            if not self.run_exists(run):
                return
            log = self.RunLogs[run]
            self.StartTime = datetime.strptime('{d} {t}'.format(d=log['begin date'], t=log['start time']), '%m/%d/%Y %H:%M:%S')
            self.StopTime = datetime.strptime('{d} {t}'.format(d=log['begin date'], t=log['stop time']), '%m/%d/%Y %H:%M:%S')
            if self.StartTime > self.StopTime:
                self.StopTime += timedelta(days=1)
        else:
            self.StartRun = sta
            log1 = self.RunLogs[sta]
            log2 = self.RunLogs[sto]
            try:
                self.StartTime = datetime.strptime('{d} {t}'.format(d=log1['begin date'], t=log1['start time']), '%m/%d/%Y %H:%M:%S')
                self.StopTime = datetime.strptime('{d} {t}'.format(d=log2['begin date'], t=log2['stop time']), '%m/%d/%Y %H:%M:%S')
            except KeyError:
                self.StartTime = datetime.strptime(log1['starttime0'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=1)
                self.StopTime = datetime.strptime(log2['endtime'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=1)

    def set_device(self, nr, dia):
        self.reset_data()
        self.Number = self.get_device_nr(str(nr))
        self.Channel = self.get_device_channel(dia)
        self.Brand = self.ConfigParser.get('HV' + self.Number, 'name').split('-')[0].strip('0123456789')
        self.Model = self.ConfigParser.get('HV' + self.Number, 'model')
        self.Name = '{0} {1}'.format(self.Brand, self.Model)
        self.DataPath = self.find_data_path()

    def reset_data(self):
        self.Currents = []
        self.Voltages = []
        self.Time = []
    # endregion

    # ==========================================================================
    # region DATA ACQUISITION
    def get_logs_from_start(self):
        log_names = sorted([name for name in glob(join(self.DataPath, '*'))] + [name for name in glob(join(self.OldDataPath, '*'))])
        start_log = None
        for i, name in enumerate(log_names):
            log_date = self.get_log_date(name)
            if log_date >= self.StartTime:
                break
            start_log = i
        self.log_info('Starting with log: {0}'.format(basename(log_names[start_log])))
        return log_names[start_log:]

    @staticmethod
    def get_log_date(name):
        log_date = basename(name).split('_')
        log_date = ''.join(log_date[-6:])
        return datetime.strptime(log_date, '%Y%m%d%H%M%S.log')

    def set_start(self, zero=False):
        self.Currents.append(self.Currents[-1] if not zero else 0)
        self.Voltages.append(self.Voltages[-1] if not zero else 0)
        self.Time.append(mktime(self.StartTime.timetuple()))

    def set_stop(self, zero=False):
        self.Currents.append(self.Currents[-1] if not zero else 0)
        self.Voltages.append(self.Voltages[-1] if not zero else 0)
        self.Time.append(mktime(self.StopTime.timetuple()))

    def find_data(self):
        if self.Currents:
            return
        stop = False
        self.LogNames = self.get_logs_from_start()
        for i, name in enumerate(self.LogNames):
            self.MeanCurrent = 0
            self.MeanVoltage = 0
            log_date = self.get_log_date(name)
            data = open(name, 'r')
            # jump to the correct line of the first file
            if not i:
                self.find_start(data, log_date)
            index = 0
            if index == 1:
                self.set_start()
            for line in data:
                # if index < 20:
                #     print line
                info = line.split()
                if isfloat(info[1]) and len(info) > 2:
                    now = datetime.strptime(log_date.strftime('%Y%m%d') + info[0], '%Y%m%d%H:%M:%S')
                    if self.StartTime < now < self.StopTime and float(info[2]) < 1e30:
                        self.save_data(now, info, index)
                        index += 1
                    if self.StopTime < now:
                        stop = True
                        break
            data.close()
            if stop:
                break
        if self.Currents:
            self.set_stop()
        if not self.Currents:
            self.set_start(zero=True)
            self.set_stop(zero=True)

    def save_data(self, now, info, index, shifting=False):
        # total_seconds = (now - datetime(now.year, 1, 1)).total_seconds()
        if self.StartTime < now < self.StopTime and float(info[2]) < 1e30:
            index += 1
            if self.DoAveraging:
                if not shifting:
                    self.MeanCurrent += float(info[2]) * 1e9
                    self.MeanVoltage += float(info[1])
                    if index % self.Points == 0:
                        if mean(self.Currents) < 5 * self.MeanCurrent / self.Points:
                            self.Currents.append(self.MeanCurrent / self.Points)
                            self.Time.append(mktime(now.timetuple()))
                            self.Voltages.append(self.MeanVoltage / self.Points)
                            self.MeanCurrent = 0
                            self.MeanVoltage = 0
                # else:
                #     if index <= self.Points:
                #         self.mean_curr += float(info[2]) * 1e9
                #         dicts[1][key].append(self.mean_curr / index)
                #         if index == self.Points:
                #             self.mean_curr /= self.Points
                #     else:
                #         mean_curr = self.mean_curr * weight + (1 - weight) * float(info[2]) * 1e9
                #         dicts[1][key].append(mean_curr)
                #     dicts[0][key].append(convert_time(now))
                #     dicts[2][key].append(float(info[1]))
            else:
                if self.IgnoreJumps:
                    if len(self.Currents) > 100 and abs(self.Currents[-1] * 100) < abs(float(info[2]) * 1e9):
                        if abs(self.Currents[-1]) > 0.01:
                            return
                self.Currents.append(float(info[2]) * 1e9)
                self.Time.append(mktime(now.timetuple()))
                self.Voltages.append(float(info[1]))

    def find_start(self, data, log_date):
        lines = len(data.readlines())
        data.seek(0)
        if lines < 10000:
            return
        was_lines = 0
        for i in range(6):
            lines /= 2
            for j in xrange(lines):
                data.readline()
            while True:
                info = data.readline().split()
                if not info:
                    break
                if isfloat(info[1]):
                    now = datetime.strptime(log_date.strftime('%Y%m%d') + info[0], '%Y%m%d%H:%M:%S')
                    if now < self.StartTime:
                        was_lines += lines
                        break
                    else:
                        data.seek(0)
                        for k in xrange(was_lines):
                            data.readline()
                        break

    def convert_to_relative_time(self):
        zero = self.Time[0]
        for i in xrange(len(self.Time)):
            self.Time[i] = self.Time[i] - zero

    # endregion

    # ==========================================================================
    # region PLOTTING

    def draw_hist(self, bin_size=1, show=True):
        self.find_data()
        p = TProfile('hpr', 'Leakage Current', int((self.Time[-1] - self.Time[0]) / bin_size), self.Time[0], self.Time[-1])
        for t, c in zip(self.Time, self.Currents):
            p.Fill(t, c)
        self.format_histo(p, x_tit='Time [hh:mm]', y_tit='Current [nA]', y_off=.8, fill_color=self.FillColor, markersize=.7, stats=0, t_ax_off=0)
        self.draw_histo(p, '', show, lm=.08, draw_opt='bare', x=1.5, y=.75)

    def set_graphs(self, averaging=1):
        self.find_data()
        sleep(.1)
        self.make_graphs(averaging)
        self.set_margins()

    def draw_distribution(self, show=True):
        self.find_data()
        m, s = calc_mean(self.Currents)
        set_root_output(False)
        h = TH1F('hcd', 'Current Distribution', 5 * int(sqrt(len(self.Currents))), m - 2 * s, m + 2 * s)
        for current in self.Currents:
            h.Fill(current)
        self.format_histo(h, x_tit='Current [nA]', y_tit='Number of Entries', y_off=1.3, fill_color=self.FillColor)
        self.draw_histo(h, '', show, lm=.13)
        return h

    def get_current(self):
        h = self.draw_distribution(show=False)
        fit = h.Fit('gaus', 'sq0')
        # log_message('Current = {0:5.2f} ({1:5.2f}) nA'.format(fit.Parameter(1), fit.ParError(1)))
        return (fit.Parameter(1), fit.ParError(1)) if fit.Parameter(0) - h.GetMean() < 10 else (h.GetMean(), h.GetMeanError())

    def draw_indep_graphs(self, rel_time=False, ignore_jumps=True, v_range=None, f_range=None, c_range=None, averaging=1, with_flux=False, show=True):
        self.IgnoreJumps = ignore_jumps
        self.set_graphs(averaging)
        set_root_output(show)
        c = TCanvas('c', 'Keithley Currents for Run {0}'.format(self.RunNumber), int(self.Res * 1.5), int(self.Res * .75))
        self.draw_flux_pad(f_range) if with_flux else self.draw_voltage_pad(v_range)
        self.draw_title_pad()
        self.draw_current_pad(rel_time, c_range)

        self.Stuff.append(c)
        self.save_plots('{dia}_{bias}'.format(dia=self.DiamondName, bias=self.Bias), sub_dir='Currents', show=show)

    def zoom_pads(self, low, high):
        self.VoltageGraph.GetXaxis().SetRangeUser(low, high)
        self.CurrentGraph.GetXaxis().SetRangeUser(low, high)

    def draw_current_pad(self, rel_t, c_range):
        self.draw_tpad('p3', gridx=True, margins=pad_margins, transparent=True)
        g = self.CurrentGraph
        self.format_histo(g, x_tit='#font[22]{Time [hh:mm]}', lab_size=label_size, x_off=1.05, tit_size=axis_title_size, t_ax_off=self.Time[0] if rel_t else 0, y_off=.55, yax_col=col_cur,
                          y_tit='#font[22]{Current [nA]}', center_y=True, x_range=[self.Time[0], self.Time[-1]], y_range=c_range, color=col_cur)
        self.CurrentGraph.Draw('apl')

    def draw_voltage_pad(self, v_range):
        self.draw_tpad('p1', gridy=True, margins=pad_margins, transparent=True)
        g = self.VoltageGraph
        v_range = [-1100, 1100] if v_range is None else v_range
        self.format_histo(g, y_range=v_range, y_tit='#font[22]{Voltage [V]}', x_range=[self.Time[0], self.Time[-1]], tit_size=axis_title_size, tick_size=0, x_off=99, l_off_x=99, center_y=True,
                          color=col_vol, y_off=title_offset, markersize=.5, yax_col=col_vol)
        g.Draw('apy+')

    def draw_flux_pad(self, f_range):
        pad = self.draw_tpad('pr', margins=pad_margins, transparent=True, logy=True)
        h = self.Analysis.draw_flux(10000, rel_t=True, show=False)
        pad.cd()
        f_range = [1, h.GetMaximum() * 1.2] if f_range is None else f_range
        self.format_histo(h, title=' ', y_tit='#font[22]{Flux [kHz/cm^{2}]}', fill_color=4000, fill_style=4000, lw=3, y_range=f_range, stats=0, y_off=1.05, x_off=99, l_off_x=99, tick_size=0,
                          center_y=True)
        h.Draw('histy+')

    def draw_title_pad(self):
        self.draw_tpad('p2', transparent=True)
        bias_str = 'at {b} V'.format(b=self.Bias) if self.Bias else ''
        run_str = '{n}'.format(n=self.Analysis.RunNumber) if hasattr(self.Analysis, 'run') else 'Plan {rp}'.format(rp=self.Analysis.RunPlan)
        text = 'Currents of {dia} {b} - Run {r} - {n}'.format(dia=self.DiamondName, b=bias_str, r=run_str, n=self.Name)
        self.draw_tlatex(pad_margins[0], 1.02 - pad_margins[-1], text, align=11, size=.06)

    def find_margins(self):
        x = [min(self.Time), max(self.Time)]
        dx = .05 * (x[1] - x[0])
        y = [min(self.Currents), max(self.Currents)]
        dy = .01 * (y[1] - y[0])
        return {'x': [x[0] - dx, x[1] + dx], 'y': [y[0] - dy, y[1] + dy]}

    def set_margins(self):
        self.Margins = self.find_margins()

    def make_graphs(self, averaging=1):
        tit = ' measured by {0}'.format(self.Name)
        xv = array(self.Time)
        xc = array(average_list(self.Time, averaging))
        # current
        y = array(average_list(self.Currents, averaging))
        g1 = TGraph(len(xc), xc, y)
        self.format_histo(g1, 'Current', '', color=col_cur, markersize=.5)
        g1.SetTitle('')
        # voltage
        y = array(self.Voltages)
        g2 = TGraph(len(xv), xv, y)
        self.format_histo(g2, 'Voltage', 'Voltage' + tit, color=col_vol, markersize=.5)
        self.CurrentGraph = g1
        self.VoltageGraph = g2

    def draw_time_axis(self, y, opt=''):
        x = self.Margins['x']
        a1 = self.draw_x_axis(y, x[0], x[1], 'Time [hh:mm]    ', off=1.2, tit_size=.05, opt=opt, lab_size=.05, tick_size=.3, l_off=.01)
        a1.SetTimeFormat("%H:%M")
        a1.SetTimeOffset(-3600)

    # endregion

    def run_exists(self, run):
        if run in self.RunLogs:
            return True
        else:
            log_warning('Run {run} does not exist in {tc}!'.format(run=run, tc=self.print_testcampaign(pr=False)))
            return False

    def print_run_times(self, run):
        run = str(run)
        if not self.run_exists(run):
            return
        log = self.RunLogs[run]
        out = '{date}: {start}-{stop}'.format(date=log['begin date'], start=log['start time'], stop=log['stop time'])
        print out


if __name__ == "__main__":
    pars = ArgumentParser()
    pars.add_argument('start', nargs='?', default='01/01-00:00:00')
    pars.add_argument('stop', nargs='?', default=None)
    pars.add_argument('-d', '--dia', nargs='?', default='1')
    pars.add_argument('-tc', '--testcampaign', nargs='?', default='')
    pars.add_argument('-v', '--verbose', nargs='?', default=True, type=bool)
    pars.add_argument('-rp', '--runplan', nargs='?', default=None)
    args = pars.parse_args()
    tc = args.testcampaign if args.testcampaign.startswith('201') else None
    a = Elementary(tc)
    print_banner('STARTING CURRENT TOOL')
    a.print_testcampaign()
    start, end = args.start, args.stop
    if args.runplan is not None:
        sel = RunSelection(testcampaign=tc)
        sel.select_runs_from_runplan(args.runplan)
        start = str(sel.get_selected_runs()[0])
        end = str(sel.get_selected_runs()[-1])
    z = Currents(None, dia=args.dia, start_run=start, verbose=args.verbose)
    z.set_start_stop(start, end)
    try:
        z.DiamondName = z.RunLogs[start]['diamond {0}'.format(int(args.dia))] if start.isdigit() else None
        z.Bias = z.RunLogs[start]['hv dia{0}'.format(int(args.dia))] if start.isdigit() else None
    except KeyError:
        z.DiamondName = z.RunLogs[start]['dia{0}'.format(int(args.dia))] if start.isdigit() else None
        z.Bias = z.RunLogs[start]['dia{0}hv'.format(int(args.dia))] if start.isdigit() else None
