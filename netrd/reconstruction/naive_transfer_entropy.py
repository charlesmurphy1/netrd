"""
naive_transfer_entropy.py
--------------
Graph reconstruction algorithm based on
Schreiber, T. (2000).  Measuring information transfer.
Physical Review Letters, 85(2):461–464
https://journals.aps.org/prl/abstract/10.1103/PhysRevLett.85.461

author: Brennan Klein
email: klein.br@husky.neu.edu
Submitted as part of the 2019 NetSI Collabathon.
"""

from .base import BaseReconstructor
import numpy as np
import networkx as nx
from scipy import stats
from scipy import ndimage


class NaiveTransferEntropyReconstructor(BaseReconstructor):
    def fit(self, TS, delay_max=10, tau=0.5):
        """
        Reconstruct a network by calculating the transfer entropy from i --> j.
        The resulting network is asymmetric, and each element TE_ij represents
        the amount of information contained about the future states of i by 
        knowing the past states of i and past states of j. Presumably, if one 
        time series (i) does not depend on the other (j), knowing all of i 
        does not increase your certainty about the next state of i.

        The reason that this method is referred to as "naive" transfer entropy 
        is because it appears there are much more complicated conditional 
        mutual informations that need to be calculated in order for this 
        method to be true to the notion of information transfer. These are 
        implemented in state of the art algorighms, as in the Java Information 
        Dynamics Toolkit: https://github.com/jlizier/jidt 

        Params
        ------
        TS (np.ndarray): array consisting of $L$ observations from $N$ sensors.
        delay_max (int): the number of timesteps in the past to 
                         aggregate and average in order to get TE_ij

        Returns
        -------
        G (nx.Graph): a reconstructed graph with $N$ nodes.
        """

        N, L = TS.shape # get the shape and length of the time series

        if delay_max >= L:
            delay_max = int(L/2)-1

        TE = np.zeros((N,N)) # initialize an empty time series

        for i in range(N): # for each node, i
            for j in range(N): # and for each node j
                if i!=j: # zeros on the diagnoals
                    te_list = [] 
                    # check several delay values and average them together
                    for delay in range(1, delay_max): 
                        te_list.append(transfer_entropy(TS[i,:],TS[j,:],delay))

                    TE[i,j] = np.mean(te_list) 
                    # this average is naive, but appears to be sufficient in 
                    # some circumstances

        self.results['transfer_entropy_matrix'] = TE

        A = np.array(TE > tau, dtype=int)
        self.results['adjacency_matrix'] = A

        G = nx.from_numpy_matrix(A)
        self.results['G'] = G

        return G


def map_in_array(values):
    '''
    Following https://github.com/notsebastiano/transfer_entropy, this is a 
    function to build arrays with correct shape for np.histogramdd()
    from 2 (or 3) time series of scalars. It is quite similar to np.vstack()
    
    Params
    ------
    values (np.ndarray): this is either a L x 2 or 3 dimensional matrix, which 
                         is the stitched-together matrix of two or three nodes'
                         time series activity.

    Returns
    -------
    data (np.ndarray): this is either a 2 or 3 x L dimensional matrix

    '''
    if len(values)==2:
        X = values[0]
        Y = values[1]
        data = np.array( list(map(lambda x,y: [x,y], X,Y)))
#         data = np.array( map(lambda x,y: [x,y], X,Y))
        return data
    if len(values)==3:
        X = values[0]
        Y = values[1]
        Z = values[2]
        data = np.array( list(map(lambda x,y,z: [x,y,z], X,Y,Z)))
        return data



def transfer_entropy(X, Y, delay=1, gaussian_sigma=None):
    '''
    Following https://github.com/notsebastiano/transfer_entropy, this is a 
    TE implementation: asymmetric statistic measuring the reduction in 
    uncertainty for a future value of X given the history of X and Y. Or the 
    amount of information from Y to X. Calculated through the Kullback-Leibler 
    divergence with conditional probabilities.

    Params
    ------
    X (np.ndarray): time series of scalars from node_i
    Y (np.ndarray): time series of scalars from node_j
    delay (int): step in tuple (x_n, y_n, x_(n - delay))
    gaussian_sigma (int): filter value to be used, default set at None

    Returns
    -------
    TE_ij (float): the transfer entropy between nodes i and j, 
                   given the history of i

    '''

    if len(X)!=len(Y):
        raise ValueError('time series entries need to have same length')

    n = float(len(X[delay:]))

    # number of bins for X and Y using Freeman-Diaconis rule
    # histograms built with np.histogramdd

    binX = int( (max(X)-min(X)) / (2* stats.iqr(X) / (len(X)**(1.0/3))) )
    binY = int( (max(Y)-min(Y)) / (2* stats.iqr(Y) / (len(Y)**(1.0/3))) )

    p3,bin_p3 = np.histogramdd(
        sample = map_in_array( [X[delay:],Y[:-delay],X[:-delay]] ),
        bins = [binX,binY,binX]
        )
    p2,bin_p2 = np.histogramdd(
        sample = map_in_array( [X[delay:],Y[:-delay]] ),
        bins=[binX,binY]
        )
    p2delay,bin_p2delay = np.histogramdd(
        sample = map_in_array( [X[delay:],X[:-delay]] ),
        bins=[binX,binX]
        )
    p1,bin_p1 = np.histogramdd(
        sample = np.array(X[delay:]),
        bins=binX
        )

    # histograms normalized to obtain densities
    p1 = p1/n
    p2 = p2/n
    p2delay = p2delay/n
    p3 = p3/n

    # apply (or not) gaussian filters at given sigma to the distributions
    if gaussian_sigma is not None:
        s = gaussian_sigma
        p1 = ndimage.gaussian_filter(p1, sigma=s)
        p2 = ndimage.gaussian_filter(p2, sigma=s)
        p2delay = ndimage.gaussian_filter(p2delay, sigma=s)
        p3 = ndimage.gaussian_filter(p3, sigma=s)

    # ranges of values in time series
    Xrange = bin_p3[0][:-1]
    Yrange = bin_p3[1][:-1]
    X2range = bin_p3[2][:-1]

    # calculating elements in TE summation
    elements = []
    for i in range(len(Xrange)):
        px = p1[i]
        for j in range(len(Yrange)):
            pxy = p2[i][j]
            for k in range(len(X2range)):
                pxx2 = p2delay[i][k]
                pxyx2 = p3[i][j][k]

                arg1 = float(pxy*pxx2)
                arg2 = float(pxyx2*px)
                #corrections avoding log(0)
                if arg1 == 0.0:
                    arg1 = float(1e-12)
                if arg2 == 0.0:
                    arg2 = float(1e-12)

                term = pxyx2*np.log2(arg2) - pxyx2*np.log2(arg1) 
                elements.append(term)

    TE_ij = sum(elements)
    return TE_ij