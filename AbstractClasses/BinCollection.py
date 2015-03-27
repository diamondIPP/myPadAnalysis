import ROOT
import numpy as np
import os
import types as t
from Bin import Bin


class BinCollection(object):
    '''
    A BinCollection Object Contains Bin-objects. It is used to store the data, as well
    as to read the data, make selections or to make Plots related to collection of many bins.

    '''

    def __init__(self, binsx, xmin, xmax, binsy, ymin, ymax):
        '''
        Constructor of a Bincollection. Since the data collection is based on ROOT.TH2D,
        the bins are ordered in a rectangular pattern inside a frame which is 1 bin thick leading
        to a total number of bins of (binsx+2)*(binsy+2)
        :param binsx: Number of bins in x direction of data collection window
        :param xmin: data collection window lower x bound
        :param xmax: data collection window upper x bound
        :param binsy: Number of bins in y direction of data collection window
        :param ymin: data collection window lower y bound
        :param ymax: data collection window upper y bound
        :return: -
        '''
        if type(binsx) is not t.IntType or type(binsy) is not t.IntType:
            "INFO: binsx or binsy not of int type. Changing it to int..."
            binsx = int(binsx)
            binsy = int(binsy)

        self.ListOfBins = [Bin(i,self) for i in xrange((binsx+2)*(binsy+2))] # A list, containing all Bin objects
        self.binnumbers = [i for i in xrange((binsx+2)*(binsy+2))]
        self.Attributes = {
            'binsx': binsx, # bins in x without frame of 1 bin
            'binsy': binsy, # bins in y without frame of 1 bin
            'XMIN': xmin,
            'XMAX': xmax,
            'YMIN': ymin,
            'YMAX': ymax,
            'binwidth_x': 1.*(xmax-xmin)/binsx,
            'binwidth_y': 1.*(ymax-ymin)/binsy
        }

        self.counthisto = ROOT.TH2D('counthisto',
                                    '2D hit distribution',
                                    self.Attributes['binsx'],
                                    self.Attributes['XMIN'],
                                    self.Attributes['XMAX'],
                                    self.Attributes['binsy'],
                                    self.Attributes['YMIN'],
                                    self.Attributes['YMAX']
                                    )
        self.totalsignal = ROOT.TH2D('totalsignal',
                                    '2D total signal distribution',
                                    self.Attributes['binsx'],
                                    self.Attributes['XMIN'],
                                    self.Attributes['XMAX'],
                                    self.Attributes['binsy'],
                                    self.Attributes['YMIN'],
                                    self.Attributes['YMAX']
                                    )

    # !! cannot be inherented to non rectangular
    def Fill(self,x,y,signal):
        '''
        Adds the datapoint into the corresponding bin inside the bincollection as
        well as into the two histograms counthisto and totalsignal inside this bin collection
        :param x:
        :param y:
        :param signal:
        :return:
        '''
        self.counthisto.Fill(x,y)
        self.totalsignal.Fill(x,y,signal)
        self.ListOfBins[self.GetBinNumber(x,y)].AddData(signal)

    def ShowBinXYSignalHisto(self,x,y,saveplot = False):
        '''
        Shows a Histogram of the Signal response distribution inside the bin which
        contains the coordinates (x,y)
        :param x: coordinate x in cm which is contained in the bin of interest
        :param y: coordinate y in cm which is contained in the bin of interest
        :param saveplot: if True save plot as as Results/Bin_X0.123Y-0.123_SignalHisto.png
        :return: -
        '''
        self.ListOfBins[self.GetBinNumber(x,y)].CreateBinSignalHisto(saveplot)

    def CalculateMeanSignalDistribution(self,minimum_bincontent = 1):
        '''

        :param minimum_bincontent:
        :return:
        '''
        assert (minimum_bincontent > 0), "minimum_bincontent has to be a positive integer"
        self.meansignaldistribution = ROOT.TH2D('meansignaldistribution',
                                                "Mean Signal Distribution",
                                                self.Attributes['binsx'],
                                                self.Attributes['XMIN'],
                                                self.Attributes['XMAX'],
                                                self.Attributes['binsy'],
                                                self.Attributes['YMIN'],
                                                self.Attributes['YMAX']
                                                )
        # go through every bin, calculate the average signal strength and fill the main 2D hist
        binwidth_x = self.Attributes['binwidth_x']
        binwidth_y = self.Attributes['binwidth_y']
        x_ = self.Attributes['XMIN'] + 1.*binwidth_x/2.
        for bin_x in xrange(1,self.Attributes['binsx']+1):

            y_ = self.Attributes['YMIN'] + 1.*binwidth_y/2.

            for bin_y in xrange(1,self.Attributes['binsy']+1):

                binsignalsum = abs(self.totalsignal.GetBinContent(bin_x, bin_y))
                binsignalcount = self.counthisto.GetBinContent(bin_x, bin_y)
                if binsignalcount >= minimum_bincontent :
                    self.meansignaldistribution.Fill(x_, y_, abs(binsignalsum/binsignalcount))

                y_ += binwidth_y

            x_ += binwidth_x

    # select Bins in a rectangular region and return list of bins
    def SelectRectangularBins(self, xlow, xhigh, ylow, yhigh, activate = True):
        list_of_bins = []
        lower_left_bin = self.GetBinNumber(xlow,ylow)
        lower_right_bin = self.GetBinNumber(xhigh,ylow)
        upper_left_bin = self.GetBinNumber(xlow,yhigh)
        upper_right_bin = self.GetBinNumber(xhigh,yhigh)
        totalbinsx = self.Attributes['binsx']+2 # binsx plus two frame bins

        while lower_left_bin <= upper_left_bin:
            list_of_bins += [i for i in xrange(lower_left_bin,lower_right_bin+1)]
            lower_left_bin += totalbinsx
            lower_right_bin += totalbinsx
        assert(upper_right_bin == lower_right_bin-totalbinsx), "Bin Mismatch in SelectRectangularBins.\n\tupper right bin: "+str(upper_right_bin)+"\n\tlower right bin: "+str(lower_right_bin)

        # selection
        if activate:
            for binnr in list_of_bins:
                self.ListOfBins[binnr].selected = True
        print len(list_of_bins), " bins selected (Rectangualr region)"
        return list_of_bins

    def UnselectAllBins(self):
        for bin in self.ListOfBins:
            bin.selected = False

    # select bins within a mean signalstrength around the signal of a reference bin
    def SelectSignalStrengthRegion(self,
                                   refBin,
                                   sensitivity = 0.1,
                                   activate = True,
                                   xlow = None,
                                   xhigh = None,
                                   ylow = None,
                                   yhigh = None):
        '''
        Creates and returns a list of all binnumbers in a region with bins that
        have a similar mean signal response as the mean signal response of a
        reference bin inside this region. If activate = True, the bins get selected
        (bin.selection = True). If no region is passed, all bins are considered.
        :param refBin: sets the default value of mean response
        :param sensitivity: bins are picked inside
            refSignal*(1-sensitivity) <= signal <= refSignal*(1+sensitivity)
        :param activate: if True the bins get set to bin.selected = True
        :param xlow: Window to restrict the considered bins
        :param xhigh:
        :param ylow:
        :param yhigh:
        :return:
        '''
        selected_bins = []
        if yhigh == None:
            list_of_bins = self.binnumbers
        else:
            list_of_bins = self.SelectRectangularBins(xlow,xhigh,ylow,yhigh,False)

        binnumber = refBin.GetBinNumber()
        assert(binnumber in list_of_bins), "Bin given is not in selected region."

        bin_avg_signal = self.meansignaldistribution.GetBinContent(binnumber)
        signal_lowerbound = bin_avg_signal*(1-sensitivity)
        signal_upperbound = bin_avg_signal*(1+sensitivity)

        for binnumber in list_of_bins:
            signal = self.meansignaldistribution.GetBinContent(binnumber)
            if self.ListOfBins[binnumber].GetEntries() > 0:
                if signal_lowerbound <= signal <= signal_upperbound:
                    selected_bins.append(binnumber)
                    if activate:
                        self.ListOfBins[binnumber].selected = True
        print len(selected_bins), " bins selected"
        return selected_bins

    # select a single bin with bin number binnumber
    def SelectBin(self,binnumber):
        self.ListOfBins[binnumber].selected = True

    # draw a 2d distribution which shows the selected bins
    def ShowSelectedBins(self,draw = True):
        if draw:
            ROOT.gStyle.SetPalette(51)
            ROOT.gStyle.SetNumberContours(2)
            selection_canvas = ROOT.TCanvas('selection_canvas', 'Selected Bins', 500, 500)
        binsx = self.Attributes['binsx']
        binsy = self.Attributes['binsy']
        xmin = self.Attributes['XMIN']
        xmax = self.Attributes['XMAX']
        ymin = self.Attributes['YMIN']
        ymax = self.Attributes['YMAX']

        selection_pad = ROOT.TH2D('selection_pad', "Selected Bins", binsx, xmin, xmax, binsy, ymin, ymax)
        i = 0
        for bin in self.ListOfBins:
            if bin.selected:
                x_, y_ = bin.GetBinCenter()
                selection_pad.Fill(x_, y_)
                i += 1
        selection_pad.SetTitle(str(i)+" Bins selected")
        selection_pad.SetStats(False)
        selection_pad.GetXaxis().SetTitle('pos x / cm')
        selection_pad.GetYaxis().SetTitle('pos y / cm')
        selection_pad.GetYaxis().SetTitleOffset(1.4)
        if draw:
            selection_canvas.cd()
            selection_pad.Draw("col")
            raw_input("Selected bins shown")
            ROOT.gStyle.SetPalette(53)
            ROOT.gStyle.SetNumberContours(999)
        return selection_pad

    def GetSortedListOfBins(self, attribute='average', ascending = True):
        '''
        Returns list of bins (binnunmbers) in an order with respect to "attribute"
        :return: ordered_list
        '''
        # self.UpdateBinAttributes()
        # SortedListOfBins = sorted(self.ListOfBins, key = lambda bin: bin.Attributes[attribute], reverse = not ascending)
        # ordered_list = [SortedListOfBins[i].Attributes['binnumber'] for i in xrange(len(SortedListOfBins))]
        sortdata = np.ones((3,len(self.ListOfBins))) # sortdata[0,:] numbers, [1,:] means, [3,:] hits
        count = 0
        for i in xrange(len(self.ListOfBins)):
            self.ListOfBins[i].UpdateAttributes()
            if self.ListOfBins[i].Attributes['entries'] >= 5:
                sortdata[0,i] = self.ListOfBins[i].Attributes['binnumber']
                sortdata[1,i] = self.ListOfBins[i].Attributes['average']
                sortdata[2,i] = self.ListOfBins[i].Attributes['entries']
                count += 1
                #print "nr: ",sortdata[0,i]," av.: ", sortdata[1,i]," ent.: ", sortdata[2,i]
        #print "*************************************************************"
        data = list(-sortdata[1][:]) #select data to sort ([1]->by average)
        arg_sorted = np.argsort(data)
        sorted_data = sortdata[:,arg_sorted] # ?! WTF? why does sortdata[:][arg_sorted] not work??!?!
        # for i in xrange(len(sorted_data[0,:count])):
        #     print "nr: ",sorted_data[0,i]," av.: ", sorted_data[1,i]," ent.: ", sorted_data[2,i]
        means = list(sorted_data[1,:])
        ordered_list = list(sorted_data[0,:count])
        #print "ordered list:", ordered_list
        # print "means: ", means
        # print "entries : ", sorted_data[2,:]
        # print "len of sorted_data: ", len(sorted_data)
        return map(int,ordered_list)

    def GetMaximumSignalResponseBinNumber(self):
        return self.GetSortedListOfBins(ascending=False)[0]

    def GetListOfSelectedBins(self):
        selected_bins = []
        for bin in self.ListOfBins:
            if bin.selected:
                selected_bins.append(bin.GetBinNumber())
        return selected_bins

    # show distribution of K_i from SIGMA = K_i * sigma_i / sqrt(n) for selected bins
    def ShowKDistribution(self,draw = True):
        if draw:
            Kcanvas = ROOT.TCanvas('Kcanvas','K Canvas')

        selection = self.GetListOfSelectedBins()
        binmeans = []
        n = []
        sigma = []
        for bin_nr in selection:
            binmeans.append(self.ListOfBins[bin_nr].GetMean())
            sigma.append(self.ListOfBins[bin_nr].GetSigma())
            n.append(self.ListOfBins[bin_nr].GetEntries())
        N = len(selection)
        SIGMA = np.std(binmeans)
        # print "sigmas : ",sorted(sigma)
        # print "means : ",sorted(binmeans)
        # print "n : ",sorted(n)


        sigma = np.array(sigma)
        K = SIGMA * np.sqrt(N) / sigma
        Khisto = ROOT.TH1D('Khisto', 'K Distribution', 50, 0, int(K.max())+1)
        Khisto.GetXaxis().SetTitle('K value')
        for i in xrange(len(K)):
            Khisto.Fill(K[i])
        if draw:
            Kcanvas.cd()
            Khisto.Draw()
            raw_input("K dostribution shown..")
        return Khisto

    def ShowCombinedKDistribution(self, saveplots = False, savename = 'CombinedKDistribution', ending='png', saveDir = 'Results/'):
        ROOT.gStyle.SetPalette(51)
        ROOT.gStyle.SetNumberContours(2)

        canvas = ROOT.TCanvas('canvas', 'combined', 1000,500)
        selection = self.ShowSelectedBins(False)
        Khisto = self.ShowKDistribution(False)
        canvas.Divide(2,1)
        canvas.cd(1)
        selection.Draw('col')
        canvas.cd(2)
        Khisto.Draw()
        if saveplots:
            self.SavePlots(savename, ending, saveDir)
        raw_input('Combined K Distribution Drawn')
        ROOT.gStyle.SetPalette(53)
        ROOT.gStyle.SetNumberContours(999)

    def GenerateTotalMeanDistribution(self):
        pass

    def GetTotalCountDistribution(self):
        return self.totalsignal

    def GetMeanSignalDistribution(self, minimum_bincontent = 1):
        self.CalculateMeanSignalDistribution(minimum_bincontent)
        return self.meansignaldistribution

    # def AddBin(self):
    #     pass

    def GetBinNumber(self,x,y):
        binnumber = self.counthisto.FindBin(x,y)
        return binnumber

    def GetBinByNumber(self, bin_number):
        '''
        Returns the bin object with number "bin_number"
        :param bin_nunmber: the bin number of the bin to return
        :return: bin with bin number bin_number
        '''
        if not(type(bin_number) is t.IntType):
            binnumber = int(bin_number)
        else:
            binnumber = bin_number
        return self.ListOfBins[binnumber]

    def GetBinByCoordinates(self, x, y):
        nr = self.GetBinNumber(x,y)
        return self.ListOfBins[nr]

    def SavePlots(self, savename, ending, saveDir):
        # Results directories:
        #resultsdir = saveDir+'run_'+str(self.run_object.run_number)+'/' # eg. 'Results/run_364/'
        resultsdir = saveDir # eg. 'Results/run_364/'
        if not os.path.exists(resultsdir):
            os.makedirs(resultsdir)

        ROOT.gPad.Print(resultsdir+savename+'.'+ending)

    def UpdateBinAttributes(self):
        for i in xrange(len(self.ListOfBins)):
            self.ListOfBins[i].UpdateAttributes()

