from RunClass import Run
from Elementary import Elementary
import json
from copy import deepcopy
from datetime import datetime as dt
from textwrap import fill


class RunSelection(Elementary):
    def __init__(self, verbose=False):
        Elementary.__init__(self, verbose)
        self.run = Run(run_number=None, verbose=verbose)

        self.runplan_path = self.get_program_dir() + self.run.run_config_parser.get('BASIC', 'runplaninfofile')
        self.run_plan = self.load_runplan()
        self.run_numbers = self.load_run_numbers()
        self.run_infos = self.load_run_infos()
        self.logs = {}
        self.selection = {}
        self.channels = {}
        self.selected_runplan = None

        self.init_selection()

    def __str__(self):
        nr = len(self.run_numbers)
        selected_runs = self.get_selected_runs()
        return 'RunSelection Object\n' + str(len(selected_runs)) + ' Out of ' + str(nr) + ' runs selected. Selections made:' + self.get_log_string()

    # ============================================
    # region LOGGING
    def make_log_entry(self, event):
        time_str = dt.now().strftime('%H:%M:%S')
        self.logs[len(self.logs)] = [event, time_str]

    def get_log_string(self):
        string = '\n'
        for key, log in self.logs.iteritems():
            string += '{key}.)\t{log}'.format(key=key, log=log[0])
        return string

    def print_logs(self):
        for key, log in self.logs.iteritems():
            print '{key}.)\t{time}\t{log}'.format(key=key, time=log[1], log=log[0])
    # endregion

    # ============================================
    # region INIT
    def load_run_numbers(self):
        run_numbers = []
        f = open(self.run.runinfofile, 'r')
        data = json.load(f)
        f.close()
        for key in data:
            run_numbers.append(int(key))
        return sorted(run_numbers)

    def load_run_infos(self):
        """ loads all the run infos in a dict with the run numbers as keys """
        run_infos = {}
        for runnumber in self.run_numbers:
            self.run.set_run(runnumber, load_root_file=False)
            run_infos[runnumber] = self.run.RunInfo
        return run_infos

    def init_selection(self):
        self.reset_selection()

    def load_runplan(self):
        f = open(self.runplan_path, 'r')
        runplans = json.load(f)
        f.close()
        try:
            runplan = runplans[self.TESTCAMPAIGN]
        except KeyError:
            print 'No runplan for {tc} available yet, creating an empty one!'.format(tc=self.TESTCAMPAIGN)
            runplan = {}
            self.save_runplan(runplan)
        return runplan
    # endregion

    # ============================================
    # region SELECT FUNCTIONS
    def reset_selection(self):
        """ Creates a dict of bools to store the selection, which is filled with False (no run selected). Resets the logs. """
        self.logs = {}
        for run in self.run_numbers:
            self.selection[run] = False
            self.channels[run] = {}
            for ch in self.run.channels:
                self.channels[run][ch] = False

    def select_all_runs(self, dia1=True, dia2=True):
        for run in self.run_numbers:
            self.selection[run] = True
            self.channels[run][self.run.channels[0]] = dia1
            self.channels[run][self.run.channels[1]] = dia2
        self.make_log_entry('All runs selected')
        self.verbose_print('All runs selected')

    def unselect_all_runs(self):
        self.reset_selection()
        self.verbose_print('All runs unselected')

    def set_channels(self, dia1=True, dia2=True):
        """
        Sets the channels (diamonds) of the selected runs to active or inactive.
        :param dia1:
        :param dia2:
        """
        dias = [dia1, dia2]
        for run_number in self.get_selected_runs():
            for i, ch in enumerate(self.run.channels):
                self.channels[run_number][ch] = dias[i]
        self.make_log_entry('Channels of selected runs set: diamond1 to {dia1}, diamond2 to {dia2}'.format(dia1=dia1, dia2=dia2))

    def reset_channels(self, run):
        for ch in self.run.channels:
            self.channels[run][ch] = False

    def select_runs_of_type(self, run_type, unselect=False, only_selected=False):
        """
        Selects the runs according to the type of run, such as rate_scan, test, voltage_scan etc..
        :param run_type:
        :param unselect:
        :param only_selected:
        """
        types = self.get_runinfo_values('type')
        assert run_type in types, 'wrong data type.\n\t-->Select type from: {types}'.format(types=types)
        runs = self.get_selected_runs() if only_selected else self.run_numbers
        selected_runs = 0
        for run in runs:
            if self.run_infos[run]['type'] == run_type:
                self.select_run(run, False) if not unselect else self.unselect_run(run, False)
                selected_runs += 1
            else:
                if not unselect:
                    self.unselect_run(run, False)
        prefix = 'un' if unselect else ''
        self.make_log_entry('Runs of type {type} {pref}selected ({nr} {pref}selections).'.format(type=run_type, pref=prefix, nr=selected_runs))
        self.verbose_print('Runs of type {type} {pref}selected ({nr} {pref}selections).'.format(type=run_type, pref=prefix, nr=selected_runs))

    def unselect_runs_of_type(self, run_type):
        self.select_runs_of_type(run_type, unselect=True)

    def select_diamond_runs(self, diamondname, only_selected_runs=False):
        """
        Selects all runs, which have the diamond with name 'diamondname' in it. It Furthermore selects also the channels corresponding to this diamondname.
        :param diamondname:
        :param only_selected_runs:
        """
        diamondnames = self.get_diamond_names()
        assert diamondname in diamondnames, 'wrong diamond name. \n\t-->Select diamond name from: {dias}'.format(dias=diamondnames)
        runs = self.get_selected_runs() if only_selected_runs else self.run_numbers
        selected_runs = 0
        unselected_runs = 0
        dia_keys = ['diamond 1', 'diamond 2']
        for run in runs:
            found_dia = False
            for i, ch in enumerate(self.run.channels):
                if self.run_infos[run][dia_keys[i]] == diamondname:
                    self.select_run(run, False)
                    self.channels[run][ch] = True
                    found_dia = True
                    selected_runs += 1
            if not found_dia and self.selection[run]:
                self.unselect_run(run, False)
                unselected_runs += 1
        log = 'Runs and Channels containing {dia} selected ( {nr1} runs selected, {nr2} unselected)'.format(dia=diamondname, nr1=selected_runs, nr2=unselected_runs)
        self.make_log_entry(log)
        self.verbose_print(log)

    def unselect_unless_bias(self, bias):
        """
        Keeps only runs selected which have a diamond with a given bias voltage. Diamonds with a different bias voltage will be un- selected.
        :param bias:
        """
        assert type(bias) is int, 'Bias has to be an integer'
        unselected_runs = 0
        for run in self.get_selected_runs():
            unselect = True
            for i, ch in enumerate(self.run.channels, 1):
                if not self.run_infos[run]['hv dia{nr}'.format(nr=i)] == bias:
                    self.channels[run][ch] = False
                else:
                    unselect = False
            if unselect:
                self.selection[run] = False
                unselected_runs += 1
        log = 'Unselected all runs and channels if bias is not {bias}V (unselected {nr} runs).'.format(bias=bias, nr=unselected_runs)
        self.make_log_entry(log)
        self.verbose_print(log)

    def select_run(self, run_number, do_assert=True, unselect=False):
        if do_assert:
            assert run_number in self.run_numbers, 'run {run} not found in list of run numbers. Check run_log json file!'.format(run=run_number)
        self.selection[run_number] = True if not unselect else False
        if unselect:
            self.reset_channels(run_number)

    def unselect_run(self, run_number, do_assert=True):
        self.select_run(run_number, do_assert, unselect=True)

    def unselect_list_of_runs(self, run_list):
        assert type(run_list) is list, 'argument has to be a list of integers'
        unselected_runs = 0
        selected_runs = self.get_selected_runs()
        for run in run_list:
            if run in selected_runs:
                self.unselect_run(run, do_assert=False)
                unselected_runs += 1
            else:
                print '{run} was not selected'.format(run=run)
        self.make_log_entry('Unselected {n} runs'.format(n=unselected_runs))

    def select_runs_in_range(self, minrun, maxrun):
        for run in self.run_numbers:
            if maxrun >= run >= minrun:
                self.select_run(run, do_assert=False)

    def select_runs(self, run_list, do_assert=False):
        assert type(run_list) is list, 'The run_list has to be a list of integers'
        for run in run_list:
            self.select_run(run, do_assert=do_assert)

    def unselect_unless_in_range(self, minrun, maxrun):
        for run in self.get_selected_runs():
            if not maxrun >= run >= minrun:
                self.unselect_run(run, do_assert=False)

    def master_selection(self):
        self.unselect_all_runs()
        self.show_diamond_names()
        dia = raw_input('Which diamond do you want to select? ')
        self.select_diamond_runs(dia)
        self.show_hv_values(sel=True)
        hv = int(float(raw_input('Which hv do you want to select? ')))
        self.unselect_unless_bias(hv)
        if len(self.get_runinfo_values('type', sel=True)) > 1:
            self.show_run_types(sel=True)
            prompt = raw_input('Do you wish to unselect a run type (y/n)? ')
            if prompt.lower() in ['yes', 'ja', 'y', 'j']:
                run_type = raw_input('Which type to you want to unselect? ')
                self.unselect_runs_of_type(run_type)
        self.show_selected_runs(show_allcomments=True)
        prompt = raw_input('Do you wish to unselect any run (y/n)? ')
        while prompt.lower() in ['yes', 'ja', 'y', 'j']:
            run = raw_input('Which run do you want to unselect? ')
            self.unselect_run(run)
            prompt = raw_input('Do you wish to unselect another run (y/n)? ')
        self.show_run_plan()
        prompt = raw_input('Do you wish to save the selection to a runplan (y/n)? ')
        if prompt.lower() in ['yes', 'ja', 'y', 'j']:
            nr = raw_input('Enter the name/number of the runplan: ')
            self.add_selection_to_runplan(nr)

    def get_selected_runs(self):
        """ :return: list of selected run numbers. """
        selected = []
        for run in self.run_numbers:
            if self.selection[run]:
                selected.append(run)
        if not selected:
            print 'No runs selected!'
        return sorted(selected)

    def get_selected_diamonds(self):
        """
        Returns a list, containing for each selected run an integer according to the diamond selection configuration. (i.e. which diamonds are selected for analysis).
            1 -> Diamond 1, 2 -> Diamond 2, 3 -> Diamond 1 & 2, or no diamond selection (default: both)
        :return: list of diamonds
        """
        selected = []
        for run in self.get_selected_runs():
            dias = [self.channels[run][ch] for ch in self.run.channels]
            diamonds = int(dias[0]) * (1 << 0) + int(dias[1]) * (1 << 1)
            diamonds = 3 if not diamonds else diamonds
            selected.append(diamonds)
        if not selected:
            print 'No runs selected!'
        return selected

    def show_selected_runs(self, show_allcomments=False):
        """
        Prints and overview of all selected runs.
        :param show_allcomments:
        :return:
        """
        selected_runs = self.get_selected_runs()
        print 'The selections contains {n} runs\n'.format(n=len(selected_runs))

        def make_info_string(run, header=False):
            string = str(run).ljust(4)
            string += self.run_infos[run]['type'].ljust(9)
            for i, ch in enumerate(self.run.channels, 1):
                string += '*' if self.channels[run][ch] else ''
                string += self.run_infos[run]['diamond {n}'.format(n=i)].ljust(7)
                string += str(int(self.run_infos[run]['hv dia{n}'.format(n=i)])).ljust(6)
            string += '{flux} kHz '.format(flux=str(int(self.run_infos[run]['measured flux'])).rjust(4))
            if not show_allcomments:
                comments = self.run_infos[run]['user comments'][:20]
                string += comments
                string += '*' if len(comments) >= 20 else ''
            if header:
                spaces = [int(self.channels[run][ch]) * ' ' for ch in self.run.channels]
                string = 'Nr. ' + 'Type'.ljust(9) + 'Dia 1'.ljust(7) + spaces[0] + 'HV 1'.ljust(6) + 'Dia 2'.ljust(7) + spaces[1] + 'HV 2'.ljust(6) + 'Flux'.ljust(9)
                string += 'Comment' if not show_allcomments else ''
            return string

        print make_info_string(selected_runs[0], True)
        for run_nr in selected_runs:
            print make_info_string(run_nr)
            comment = self.run_infos[run_nr]['user comments']
            if show_allcomments and len(comment) > 0:
                print 'COMMENT:\n{comment}\n{delimitor}'.format(comment=fill(comment, 51), delimitor=49 * '-')
    # endregion

    # ============================================
    # region RUN PLAN
    def save_runplan(self, runplan=None):
        f = open(self.runplan_path, 'r+')
        runplans = json.load(f)
        self.rename_runplan_numbers()
        runplans[self.TESTCAMPAIGN] = self.run_plan if runplan is None else runplan
        f.seek(0)
        json.dump(runplans, f, indent=2, sort_keys=True)
        f.truncate()
        f.close()

    def rename_runplan_numbers(self):
        for type_, plan in self.run_plan.iteritems():
            for nr in plan:
                self.run_plan[type_][nr.zfill(2)] = self.run_plan[type_].pop(nr)

    def show_run_plan(self, detailed=False, show_allcomments=False):
        """
        Print a list of all run plans from the current test campaign to the console.
        :param detailed:
        :param show_allcomments:
        :return:
        """
        old_selection = deepcopy(self.selection)
        old_channels = deepcopy(self.channels)
        old_logs = deepcopy(self.logs)
        print 'RUN PLAN FOR TESTCAMPAIGN: {tc}'.format(tc=self.TESTCAMPAIGN)
        for run_type, plan in self.run_plan.iteritems():
            print '{type}:'.format(type=run_type)
            if not detailed:
                print '  Nr. {range} {excl} Diamonds'.format(range='Range'.ljust(17), excl='Excluded'.ljust(15))
            for nr, runs in sorted(plan.iteritems()):
                self.unselect_all_runs()
                self.select_runs_from_runplan(nr, run_type)
                if not detailed:
                    all_runs = [run for run in self.run_numbers if runs[-1] >= run >= runs[0]]
                    missing_runs = []
                    i = 0
                    for run in all_runs:
                        if run != runs[i]:
                            missing_runs.append(run)
                        else:
                            i += 1
                    dias = [str(dia) for dia in self.get_diamond_names(True)]
                    run_string = '[{min}, ... , {max}]'.format(min=str(runs[0]).zfill(3), max=str(runs[-1]).zfill(2))
                    not_string = str(missing_runs) if missing_runs else ''
                    print '  {nr}: {runs}, {miss} {dias}'.format(nr=nr, runs=run_string, miss=not_string[:15].ljust(15), dias=dias)
                else:
                    print '{delim}\n RUN PLAN {nr} ({type})\n{delim}'.format(delim=50 * '-', nr=nr, type=run_type)
                    self.show_selected_runs(show_allcomments=show_allcomments)
                    print '\n'

        self.channels = old_channels
        self.logs = old_logs
        self.selection = old_selection

    def select_runs_from_runplan(self, plan_nr, type_='rate_scan'):
        plan = str(plan_nr).zfill(2) if type(plan_nr) is int else plan_nr.zfill(2)
        self.selected_runplan = plan
        runs = self.run_plan[type_][plan]
        self.select_runs(runs)

    def add_selection_to_runplan(self, plan_nr, run_type='rate_scan'):
        """
        Saves all selected runs as a run plan with name 'plan_nr'.
        :param plan_nr:
        :param run_type:
        """
        assert type(plan_nr) is str, 'The plan number has to be a string!'
        types = ['rate_scan', 'voltage_scan', 'test']
        assert run_type in types, 'This run type does not exist! Types are: {types}'.format(types=types)
        assert self.selection, 'The run selection is completely empty!'

        if run_type in self.run_plan:
            self.run_plan[run_type][plan_nr] = self.get_selected_runs()
        else:
            self.run_plan[run_type] = {}
            self.run_plan[run_type][plan_nr] = self.get_selected_runs()
        self.save_runplan()

    def delete_runplan(self, plan_nr, run_type='rate_scan'):
        plan = str(plan_nr).zfill(2) if type(plan_nr) is int else plan_nr.zfill(2)
        types = ['rate_scan', 'voltage_scan', 'test']
        assert run_type in types, 'This run type does not exist! Types are: {types}'.format(types=types)

        self.run_plan[run_type].pop(plan)
        self.save_runplan()
    # endregion

    def get_diamond_names(self, sel=False):
        names = self.get_runinfo_values('diamond 1', sel)
        for name in self.get_runinfo_values('diamond 2', sel):
            if name not in names:
                names.append(name)
        return sorted(names)

    def show_diamond_names(self, sel=False):
        print 'Diamondnames:'
        for name in self.get_diamond_names(sel=sel):
            print '  ' + name

    def get_hv_values(self, sel=False):
        dias = self.get_selected_diamonds()[0] if sel else 3
        hvs = self.get_runinfo_values('hv dia1', sel) if self.has_bit(dias, 0) else self.get_runinfo_values('hv dia2', sel)
        if dias == 3:
            for hv in self.get_runinfo_values('hv dia2', sel):
                if hv not in hvs:
                    hvs.append(hv)
        return hvs

    def show_hv_values(self, sel=False):
        print 'HV Values:'
        for hv in self.get_hv_values(sel=sel):
            print '  {hv}'.format(hv=hv)

    def show_run_types(self, sel=False):
        print 'Types:'
        for type_ in self.get_runinfo_values('type', sel=sel):
            print '  ' + type_

    def get_runinfo_values(self, key, sel=False):
        """
        :param key: key of run info
        :param sel: False for all runs, True for all in selection
        :return: all different values of the run info dict
        """
        values = []
        run_infos = self.run_infos if not sel else self.get_selection_runinfo()
        for run, info in run_infos.iteritems():
            value = info[key]
            if value not in values:
                values.append(value)
        return sorted(values)

    def get_selection_runinfo(self):
        dic = {}
        for run, info in self.run_infos.iteritems():
            if self.selection[run]:
                dic[run] = info
        return dic

    def change_runinfo_key(self):
        f = open(self.run.runinfofile, 'r+')
        runs = self.get_selected_runs()
        runinfo = json.load(f)
        keys = [str(key) for key in runinfo.values()[0].iterkeys()]
        print keys
        change_key = raw_input('Enter the key you want to change: ')
        assert change_key in keys, 'The entered key does not exist!'
        print 'old values:'
        for run in runs:
            print '{run}:  {value}'.format(run=run, value=runinfo[str(run)][change_key])
        change_value = raw_input('Enter the new value: ')
        for run in runs:
            runinfo[str(run)][change_key] = change_value
        f.seek(0)
        json.dump(runinfo, f, indent=2, sort_keys=True)
        f.truncate()
        f.close()


if __name__ == '__main__':
    z = RunSelection()
