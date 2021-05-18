# --------------------------------------------------------
#       PULSER ANALYSIS
# created on June 16th 2016 by M. Reichmann
# --------------------------------------------------------
from src.waveform import Waveform
from src.sub_analysis import PadSubAnalysis
from helpers.save_plots import *


class PulserAnalysis(PadSubAnalysis):

    def __init__(self, pad_analysis):
        super().__init__(pad_analysis, pickle_dir='Pulser')
        self.Cut = self.Ana.Cut.get_pulser()
        self.Polarity = self.Ana.PulserPolarity
        self.SignalName = self.get_signal_name()
        self.SignalRegion = array(self.Run.IntegralRegions[self.Ana.DUT.Number - 1]['pulser']) * self.Ana.DigitiserBinWidth
        self.PedestalName = self.load_pedestal_name()

        self.Type = str(self.Ana.Run.Info['pulser']) if 'pulser' in self.Ana.Run.Info else None

        self.DigitiserBinWidth = self.Ana.DigitiserBinWidth
        self.Waveform = Waveform(self)
        self.Pedestal = self.Ana.Pedestal
        self.PeakName = self.Ana.get_peak_name(type_='pulser')
        self.Peaks = self.Ana.Peaks

    # ----------------------------------------
    # region INIT
    def load_pedestal_name(self, peak_int=None):
        region = self.Config.get_value('BASIC', 'pulser pedestal', default='ac')
        return self.Ana.get_pedestal_name(region, self.Ana.PeakIntegral if None else peak_int)
    # endregion INIT
    # ----------------------------------------

    # ----------------------------------------
    # region GET
    def get_events(self, cut=None, redo=False):  # for Waveform
        return self.Ana.get_events(self.Cut(cut), redo)

    def get_event_cut(self, cut=None, redo=False):
        cut = self.make_event_cut(self.get_events(cut, redo))
        return cut & (self.Peaks.get_npeaks() == (1 if self.Type == 'extern' else 2))

    def get_signal_range(self, lfac=0, rfac=0, t_corr=True):
        return ax_range(self.SignalRegion / (1 if t_corr else self.DigitiserBinWidth), None, lfac, rfac)

    def get_combined_cut(self, n=1000):
        """returns: cut of [n] pulser and [n] signal events."""
        return self.Ana.make_event_cut(concatenate([self.get_events()[:n], self.Ana.get_events()[:n]]))

    def get_signal_indices(self):  # for Waveform
        """ :returns: indices that are smaller then the smallest signals """
        return where(array(self.get_values()) > self.Ana.get_min_signal() - 5)[0]

    def get_min_signal(self, name=None):
        h = self.draw_distribution(name, show=False, save=False)
        return h.GetBinCenter(h.FindFirstBinAbove(h.GetMaximum() * .01))

    def get_rate(self, prnt=True, redo=False):
        def f():
            return calc_eff(values=self.Run.get_tree_vec(dtype=bool, var='pulser', cut=self.Ana.Cut.CutStrings.get('beam stops')))
        r = do_pickle(self.make_simple_pickle_path('Rate'), f, redo=redo)
        self.info(f'pulser rate: {r[0]:.2f}+({r[1]:.2f})-({r[2]:.2f}) %', prnt=prnt)
        return r

    def get_rate_stability(self, bin_size=10, bins=None, show=False):
        return self.Draw.pull(self.draw_rate(bin_size, show=False, cut=self.Ana.Cut['beam stops']), bins, show=show)

    def get_t_bins(self, bin_size=None):
        return make_bins(*ax_range(self.SignalRegion, 0, .5, .5), choose(bin_size, default=self.Waveform.BinWidth))

    def get_pulse_height(self, corr=True, beam_on=True, bin_width=.2, par=1, redo=False):
        return self.draw_distribution_fit(corr, beam_on, bin_width, redo, show=False)[par]

    def get_sigma(self, corr=True, beam_on=True, bin_width=.2, redo=False):
        return self.get_pulse_height(corr, beam_on, bin_width, par=2, redo=redo)

    def get_pedestal(self, sigma=False, beam_on=True, redo=False):
        pickle_path = self.make_simple_pickle_path('Pedestal', str(int(beam_on)))
        fit = do_pickle(pickle_path, partial(self.draw_pedestal_fit, show=False, prnt=False, redo=redo, beam_on=beam_on), redo=redo)
        return fit2u(fit, par=[1, 2][sigma])

    def get_pedestal_mean(self, redo=False):
        return self.get_pedestal(redo=redo)

    def get_pedestal_sigma(self, redo=False):
        return self.get_pedestal(sigma=True, redo=redo)

    def get_values(self, cut=None):
        return self.get_tree_vec(var=self.get_signal_var(cut=self.Cut(cut)), cut=self.Cut(cut), dtype='f4')

    def get_cft(self, ind=None):
        cft = self.Peaks.get_cft(ind=ind)
        tmin, tmax = self.SignalRegion
        cft = array([[t for t in lst if tmin <= t <= tmax] for lst in cft])
        return array([lst[0] if len(lst) else 0 for lst in cft])

    def get_peak_times(self, cut=None):
        t = self.Peaks.get_times(flat=True, fit=True, cut=choose(cut, self.get_event_cut()))
        return t if self.Type == 'extern' else t[::2]

    def get_peak_time(self, sigma=False):
        return mean_sigma(self.get_peak_times())[sigma]

    def get_mean_sigma(self, cut=None, redo=False):
        def f():
            return fit_fwhm(self.Draw.distribution(self.get_values(cut), self.Ana.Bins.get_pad_ph(bin_width=.5), '', show=False))[1:]
        return do_pickle(self.make_simple_pickle_path('MeanSigma', self.Cut(cut).GetName()), f, redo=redo)

    def get_fraction(self, show=False, prnt=True):
        """ :returns the fitted value of the fraction of pulser events with event range and beam interruptions cuts and its fit error. """
        h = self.draw_rate(show=show, cut=self.Ana.Cut.get('beam stops'), prnt=prnt)
        format_statbox(h, fit=True)
        format_histo(h, markersize=None)
        fit = h.Fit('pol0', 'qs')
        return fit2u(FitRes(fit), par=0)

    def get_real_fraction(self):
        """ :returns the real fraction of pulser events compared to signal events. (pulser in rate / flux / area)  """
        in_rate = 40 if self.Ana.get_flux().n < 20 else 100
        return in_rate / (self.Ana.get_flux() * self.DUT.ActiveArea)

    def get_signal_name(self, peak_int=None):
        return self.Ana.get_signal_name('', peak_int, 'pulser')

    def get_all_signal_names(self):
        return self.Ana.get_all_signal_names('pulser')

    def get_short_regint(self, signal=None):
        return self.get_all_signal_names()[choose(signal, self.SignalName)]

    def get_signal_var(self, name=None, event_corr=False, off_corr=True, cut=None):
        return self.Ana.get_signal_var(choose(name, self.SignalName), event_corr, off_corr, self.Cut(cut), sig_type='pulser')
    # endregion GET
    # ----------------------------------------

    # ----------------------------------------
    # region DRAW
    def draw_rate(self, bin_size=10, cut='', rel_t=True, show=True, prnt=True):
        """ Shows the fraction of pulser events as a function of time. Peaks appearing in this graph are most likely beam interruptions. """
        x, y = self.get_tree_vec(var=[self.get_t_var(), 'pulser'], cut=self.Cut(choose(cut, self.Ana.Cut.get('beam stops'))))
        p = self.Draw.profile(x, y * 100, self.Bins.get_raw_time(bin_size), 'Pulser Rate', y_tit='Pulser Fraction [%]', y_off=.8, y_range=[0, 105], markersize=.5, stats=0, lm=.08, draw_opt='bare',
                              w=1.5, h=.75, fill_color=Draw.FillColor, **self.get_t_args(rel_t), show=show)
        self.Draw.save_plots('PulserRate', prnt=prnt, show=show)
        return p

    def draw_pulse_height(self, bin_size=None, cut=None, y_range=None, show=True, redo=False, prnt=True):
        """ Shows the average pulse height of the pulser as a function of time """
        def f():
            x, y = self.get_tree_vec(var=[self.get_t_var(), self.get_signal_var()], cut=self.Cut(cut))
            m, s = self.get_mean_sigma(cut)
            ph_cut = (m - 4 * s < y) & (y < m + 4 * s)
            return self.Draw.profile(x[ph_cut], y[ph_cut], self.Bins.get_time(bin_size, cut), 'Pulser Pulse Height', show=False)
        p = do_pickle(self.make_simple_pickle_path('PHT', '{}{}'.format(self.Cut(cut).GetName(), self.Bins.w(bin_size))), f, redo=redo)
        fit = p.Fit('pol0', 'qs')
        format_histo(p, y_off=1.7, **self.get_t_args(), y_range=choose(y_range, ax_range(get_hist_vec(p), 0, .6, 1)))
        self.Draw(p, 'PulserPulserHeight', show, gridy=True, lm=.14, stats=set_statbox(fit=True, entries=True), prnt=prnt)
        return p, FitRes(fit)

    def draw_distribution(self, name=None, corr=True, beam_on=True, bin_width=.2, redo=False, **kwargs):
        """ Shows the distribution of the pulser integrals. """
        def f():
            cut = self.Ana.Cut.get_pulser(beam_on=beam_on)()
            x = self.Run.get_tree_vec(var=self.get_signal_var(name, event_corr=False, off_corr=corr, cut=cut), cut=cut)
            m, s = mean_sigma(x[x < mean(x) + 10], err=False)
            return self.Draw.distribution(x, make_bins(m - 3 * s, m + 5 * s, bin_width), 'Pulser Pulse Height', x_tit='Pulse Height [mV]', show=False)
        h = do_pickle(self.make_simple_pickle_path('Disto', f'{int(corr)}{int(beam_on)}{self.get_short_regint(name)}'), f, redo=redo)
        return self.Draw.distribution(h, file_name='PulserDistribution', lm=.12, **kwargs, y_off=1.8)

    def get_fit_range(self, h, lsig=3, rsig=.5):
        f0, same_polarity = fit_fwhm(h), self.Polarity == self.Ana.Polarity
        return uarr2n([f0[1] + i * f0[2] for i in ([-lsig, rsig] if same_polarity else [-rsig, lsig])])  # fit left tail if same pol and right tail otherwise

    def draw_distribution_fit(self, corr=True, beam_on=True, bin_width=.2, redo=False, show=True, prnt=True, **kwargs):
        def f():
            h0 = self.draw_distribution(show=False, corr=corr, beam_on=beam_on, bin_width=bin_width, redo=redo, **kwargs)
            return FitRes(h0.Fit('gaus', 'qs0', '', *self.get_fit_range(h0)))
        pickle_path = self.make_simple_pickle_path('HistoFit', f'{corr:d}_{beam_on:d}_{"normalise" in kwargs:d}')
        fit = do_pickle(pickle_path, f, redo=redo)
        if show:
            h = self.draw_distribution(corr=corr, beam_on=beam_on, bin_width=bin_width, redo=redo, show=show, **kwargs)
            self.Draw.make_f('gp0', 'gaus', 0, 500, pars=fit.Pars, npx=100, line_style=7).Draw('same')
            self.Draw.make_f('gp1', 'gaus', *self.get_fit_range(h), pars=fit.Pars, npx=100).Draw('same')
            format_statbox(h, fit=True, entries=True, form='.2f')
            self.Draw.save_plots('PulserDistributionFit', show=show, prnt=prnt)
        SaveDraw.server_pickle(pickle_path, fit)
        return fit

    def draw_pedestal(self, show=True, save=True, prnt=True, redo=False):
        return self.Ana.Pedestal.draw_distribution(name=self.PedestalName, cut=self.Cut(), show=show, save=save, prnt=prnt, redo=redo)

    def draw_pedestal_fit(self, beam_on=True, show=True, save=True, prnt=True, redo=False):
        return self.Ana.Pedestal.draw_disto_fit(name=self.PedestalName, cut=self.Ana.Cut.get_pulser(beam_on=beam_on)(), show=show, save=save, prnt=prnt, redo=redo)

    def compare_pedestal(self, show=True):
        histos = [self.Ana.Pedestal.draw_distribution(show=False), self.draw_pedestal(show=False)]
        self.Draw.stack(histos, 'Comparison of Pulser and Signal Pedestal', ['Signal', 'Pulser'], scale=True, show=show, lw=2, rebin=3)

    def draw_hit_efficiency(self, bin_size=200, show=True):
        from src.pad_alignment import PadAlignment
        return PadAlignment(self.Run.Converter).draw(bin_size=bin_size, show=show)

    def draw_signal_vs_peaktime(self, bin_size=None, x=None, y=None, show=True):
        return self.Ana.draw_ph_peaktime(x=choose(x, self.Peaks.get_from_tree()), y=choose(y, self.get_values()), xbins=self.get_t_bins(bin_size), show=show)

    def draw_peak_times(self, bin_size=None, x_range=None, y_range=None, draw_ph=False):
        ind = self.get_signal_indices()
        return self.Peaks.draw_signal(bin_size, x_range=x_range, y_range=y_range, x=array(self.Peaks.get_from_tree())[ind], y=array(self.get_values())[ind], draw_ph=draw_ph)

    def draw_cft(self, bin_size=None, show=True):
        h = self.Draw.distribution(self.get_cft(self.get_signal_indices()), self.get_t_bins(bin_size), 'Pulser Constant Fraction Times', x_tit='Constant Fraction Time [ns]', show=show)
        h.Fit('gaus')
        format_statbox(h, fit=True, entries=True)
    # endregion DRAW
    # ----------------------------------------
