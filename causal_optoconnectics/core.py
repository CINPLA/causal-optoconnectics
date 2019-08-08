import numpy as np
import scipy.stats as st
import scipy.integrate as si
from sklearn.linear_model import LogisticRegression # must come before nest import


def raised_cosine(n_bases, bin_size, end_peak_times, offset, stretching='log'):
    '''Raised cosine basis
      ^
     / \
    /   \______
         ^
        / \
    ___/   \___
            ^
           / \
    ______/   \
    Make log or linearly stretched basis consisting of raised cosines.
    Log stretching allows faster changes near the event. Adapted from _[1]

    Parameters
    ----------
    n_bases : int
        Number of basis vectors
    bin_size : float
        time bin size (separation for representing basis
    end_peak_times : array
        [2 x 1] array containg [1st_peak,  last_peak], the peak
             (i.e. center) of the first and the last raised cosine basis vectors
    offset: float
        offset for log stretching of x axis:  y = log(t + offset)
        (larger offset -> more nearly linear stretching)
    stretching : str
        "log" or "linear"

    Returns
    -------
    time : array
        time lattice on which basis is defined
    bases : array
        basis itself
    centers : array
        centers of each basis function

    Example
    -------
    time, bases, centers = log_raised_cosine(10, 1, [0, 500], 2);

    References
    ----------
    _[1] : Pillow, J. W., Paninski, L., Uzzell, V. J., Simoncelli, E. P., &
    Chichilnisky, E. J. (2005). Prediction and decoding of retinal ganglion
    cell responses with a probabilistic spiking model. Journal of Neuroscience,
    25(47), 11003-11013.
    '''
    if stretching == 'log':
        if offset <= 0:
            raise ValueError('offset must be greater than 0')
        #log stretching x axis (and its inverse)
        stretch = lambda x: np.log(x + 1e-20)
        inv_stretch = lambda x: np.exp(x) - 1e-20
    elif stretching == 'linear':
        stretch = lambda x: x
        inv_stretch = lambda x: x
        offset = 0
    else:
        raise ValueError('stretching must be "log" or "linear"')

    x_range = stretch(end_peak_times + offset)

    db = np.diff(x_range) / (n_bases - 1)  # spacing between raised cosine peaks

    centers = np.arange(x_range[0], x_range[1] + db / 2, db)  # centers for basis vectors

    max_time_bin = inv_stretch(x_range[1] + db) - offset  # maximum time bin (originally 2 * db)

    time = np.arange(0, max_time_bin, bin_size)

    centers_tiled = np.tile(centers, (time.size, 1))

    time_stretch_tiled = np.tile(stretch(time + offset)[:, np.newaxis], (1, n_bases))

    def _raised_cosine(time, centers, dc):
        center_adjusted = (time - centers) * np.pi / dc # originally divided by 2
        center_adjusted_min = np.minimum(np.pi, center_adjusted)
        center_adjusted_min_max = np.maximum(-np.pi, center_adjusted_min)
        return (np.cos(center_adjusted_min_max) + 1) / 2

    bases = _raised_cosine(time_stretch_tiled, centers_tiled, db)

    centers = inv_stretch(centers)

    return time, bases, centers


# def calculate_regressors(x, y, stim_times, y_mu, y_sigma):
#     '''Calculate upstream spike time before and after stimulus and downstream
#     count. Responses in are counted within
#     `y >= stim_times + y_mu - y_sigma`
#     and `y < stim_times + y_mu + y_sigma`.
#
#     Parameters
#     ----------
#     x : array
#         Upstream spike times
#     y : array
#         Downstream spike times
#     stim_times : array
#         Stimulation onset times
#     y_mu : float
#         Average stimulus response time for downstream spikes (y)
#     y_sigma : float
#         Standard deviation of stimulus response times.
#
#     Returns
#     -------
#     Z : array
#         Upstream times (< 0) before stimulus (referenced at 0)
#     X : array
#         Upstream times (> 0) after stimulus (referenced at 0)
#     Y : array
#         Downstream counted within stimulus + y_mu ± y_sigma
#     '''
#     stim_times = stim_times.astype(float)
#
#     src_x = np.searchsorted(x, stim_times, side='right')
#
#     remove_idxs, = np.where((src_x==len(x)) | (src_x==0))
#     src_x = np.delete(src_x, remove_idxs)
#     stim_times = np.delete(stim_times, remove_idxs)
#     Z = x[src_x-1] - stim_times
#     X = x[src_x] - stim_times
#
#     stim_win = np.insert(
#         stim_times + y_mu - y_sigma,
#         np.arange(len(stim_times)) + 1,
#         stim_times + y_mu + y_sigma)
#     src_y = np.searchsorted(y, stim_win, side='left')
#     cnt_y = np.diff(src_y.reshape((int(len(src_y) / 2), 2)))
#     Y = cnt_y.flatten()
#     return Z, X, Y


def calculate_regressors(x, y, stim_times):
    '''Calculate upstream spike time before and after stimulus and downstream
    count. Responses in are counted within
    `y >= stim_times + y_mu - y_sigma`
    and `y < stim_times + y_mu + y_sigma`.

    Parameters
    ----------
    x : array
        Upstream spike times
    y : array
        Downstream spike times
    stim_times : array
        Stimulation onset times
    Returns
    -------
    Z : array
        Upstream times (< 0) before stimulus (referenced at 0)
    X : array
        Upstream times (> 0) after stimulus (referenced at 0)
    Y : array
        Downstream times (> 0) after stimulus (referenced at 0)
    '''
    stim_times = stim_times.astype(float)

    src_x = np.searchsorted(x, stim_times, side='right')
    src_y = np.searchsorted(y, stim_times, side='right')

    remove_idxs, = np.where(
        (src_x==len(x)) | (src_x==0) | (src_y==len(y)) | (src_y==0))
    src_x = np.delete(src_x, remove_idxs)
    src_y = np.delete(src_y, remove_idxs)
    stim_times = np.delete(stim_times, remove_idxs)

    X = x[src_x] - stim_times
    Y = y[src_y] - stim_times
    Z = x[src_x-1] - stim_times

    return Z, X, Y, stim_times


def hit_rate(source, stim_times, mu, sigma):
    stim_win = np.insert(
        stim_times + mu - sigma,
        np.arange(len(stim_times)) + 1,
        stim_times + mu + sigma)
    src_y = np.searchsorted(source, stim_win, side='left')
    cnt_y = np.diff(src_y.reshape((int(len(src_y) / 2), 2)))
    Y = cnt_y.flatten()
    return sum(Y) / len(Y)


# def causal_connectivity(
#     x, y, stim_times, x_mu, x_sigma, y_mu, y_sigma,
#     n_bases=20, bin_size=1e-3, offset=1e-2, cutoff=None):
#     '''Estimates causal connectivity between upstream (x) and downstream (y)
#     neurons using a two-stage instrumental variables regression.
#
#     Z --(instrument)--> X --(beta_IV)-->  Y
#
#     Connectivity is calculated using a two stage instrumental variables (IV)
#     regression.
#     First stage uses a logistic regression of the instrument (Z) on
#     the exogenous variable (X).
#     The instrument consists of pre-stimulus spike times of the upstrem neuron
#     (x) represented by a raised cosine bases with logarithmic stretching of
#     time.
#     This gives high fidelity close to stimulus event time and increasingly
#     course fidelity at larger time intervals.
#     The exogenous variable is a binary variable representing weather or not
#     the stimulus response time is within `stim_times + x_mu ± x_sigma`.
#     Second stage is a linear regression of the fitted values of X given by the
#     first stage.
#     The result (beta_IV) is the causal influence of x on y with interpretation:
#
#     `beta_IV = (rate(y) - rate(y')) / (rate(x) + rate(stim_times))`.
#
#     Here `rate(.) = len(.) / stop_time` and the counter factual y' represents
#     y in the (non existing) world where x had not physically been connected to y.
#
#     Parameters
#     ----------
#     x : array
#         Upstream spike times
#     y : array
#         Downstream spike times
#     stim_times : array
#         Stimulation onset times
#     x_mu : float
#         Average stimulus response time for upstream spikes (y)
#     y_sigma : float
#         Standard deviation of upstream stimulus response times.
#     y_mu : float
#         Average stimulus response time for downstream spikes (y)
#     y_sigma : float
#         Standard deviation of downstream stimulus response times.
#     n_bases : int
#         Number of basis vectors for raised cosines.
#     bin_size : float
#         time bin size (separation for representing basis)
#     end_peak_times : array
#         [2 x 1] array containg [1st_peak,  last_peak], the peak
#         (i.e. center) of the first and the last raised cosine basis vectors.
#     offset: float
#         Offset for log stretching of x axis:  y = log(t + offset)
#         (larger offset -> more nearly linear stretching)
#     cutoff: float [optional]
#         Maximal time of interest for spike times preceeding stimulus onset.
#         Representing a cutof where all relative times larger is set to zero.
#         Default is largest difference between stimulus and preceeding spike
#
#     Returns
#     -------
#     beta_IV : float
#         The causal influence of x on y. With rate(y) and the counter factual
#         rate(y') (rate of y if x had not physically been connected to y)
#     '''
#     Z, X, Y = calculate_regressors(x, y, stim_times, y_mu, y_sigma)
#
#     X = ((X > x_mu - x_sigma) & (X < x_mu + x_sigma)).astype(int)
#
#     if not any(np.diff(X)) or not any(np.diff(Y)): # logit solver needs two classes
#         return np.nan
#
#     Z = np.abs(Z)
#     if cutoff is None:
#         cutoff = Z.max()
#
#     time, bases, centers = raised_cosine(
#         n_bases, bin_size, np.array([0, cutoff]), offset)
#     Z_bases = np.zeros((len(Z), n_bases))
#
#     def index(t, bin_size):
#         return np.minimum(np.ceil(t / bin_size).astype(int), len(time)-1)
#
#     idxs = index(Z, bin_size)
#     Z_bases[:, :] = bases[idxs, :]
#     # Z_bases = Z.reshape(-1, 1)
#
#     model1 = LogisticRegression(C=1e5, solver='liblinear')#, penalty='none')
#     model1.fit(Z_bases, X)
#
#     # X_hat = model1.predict_proba(Z_bases)[:,1]
#     X_hat = model1.predict(Z_bases)
#
#     # X_hat = np.vstack((X_hat, np.ones(X_hat.shape[0]))).T
#     # beta_IV, _ = np.linalg.lstsq(X_hat, Y, rcond=None)[0]
#
#     model2 = LogisticRegression(C=1e5, solver='liblinear')#, penalty='none')
#     model2.fit(X_hat.reshape(-1, 1), Y)
#     #
#     logit = lambda x: 1 / (1 + np.exp(-x))
#     beta_IV = logit(model2.coef_) - .5
#
#     # beta_IV = model2.coef_
#
#     # beta_IV = model2.predict([[1]])
#     # beta_IV,_ = model2.predict_proba([[1]])[0]
#     # print(beta_IV)
#
#     return float(beta_IV)


def instrumental_connection_probability(
    x, y, stim_times, x_mu, x_sigma, y_mu, y_sigma,
    n_bases=20, bin_size=1e-3, offset=1e-2, cutoff=None):
    '''
    Parameters
    ----------
    x : array
        Upstream spike times
    y : array
        Downstream spike times
    stim_times : array
        Stimulation onset times
    x_mu : float
        Average stimulus response time for upstream spikes (y)
    y_sigma : float
        Standard deviation of upstream stimulus response times.
    y_mu : float
        Average stimulus response time for downstream spikes (y)
    y_sigma : float
        Standard deviation of downstream stimulus response times.
    n_bases : int
        Number of basis vectors for raised cosines.
    bin_size : float
        time bin size (separation for representing basis)
    end_peak_times : array
        [2 x 1] array containg [1st_peak,  last_peak], the peak
        (i.e. center) of the first and the last raised cosine basis vectors.
    offset: float
        Offset for log stretching of x axis:  y = log(t + offset)
        (larger offset -> more nearly linear stretching)
    cutoff: float [optional]
        Maximal time of interest for spike times preceeding stimulus onset.
        Representing a cutof where all relative times larger is set to zero.
        Default is largest difference between stimulus and preceeding spike

    Returns
    -------
    beta_IV : float
        The causal influence of x on y. Conditional probability of spike in y
        given spike in x relative to stimuls.
    '''
    Z, X, Y, stim_times = calculate_regressors(x, y, stim_times)

    X = ((X > x_mu - x_sigma) & (X < x_mu + x_sigma)).astype(int)
    Y = ((Y > y_mu - y_sigma) & (Y < y_mu + y_sigma)).astype(int)

    # if not any(np.diff(X)) or not any(np.diff(Y)): # logit solver needs two classes
    #     return np.nan

    Z = np.abs(Z)
    if cutoff is None:
        cutoff = Z.max()

    time, bases, centers = raised_cosine(
        n_bases, bin_size, np.array([0, cutoff]), offset)
    Z_bases = np.zeros((len(Z), n_bases))

    def index(t, bin_size):
        return np.minimum(np.ceil(t / bin_size).astype(int), len(time)-1)

    idxs = index(Z, bin_size)
    Z_bases[:, :] = bases[idxs, :]

    model1 = LogisticRegression(C=1e5, solver='liblinear')#, penalty='none')
    model1.fit(Z_bases, X)

    # X_hat = model1.predict_proba(Z_bases)[:,1]
    X_hat = model1.predict(Z_bases)

    # Z_bases = np.vstack((Z, np.ones(Z.shape[0]))).T
    # W = np.linalg.lstsq(Z_bases, X, rcond=None)[0]
    # X_hat = np.dot(Z_bases, W)
    # X_hat = X

    # X_hat = np.vstack((X_hat, np.ones(X_hat.shape[0]))).T
    # beta_IV, _ = np.linalg.lstsq(X_hat, Y, rcond=None)[0]

    model = LogisticRegression(C=1e5, solver='liblinear')#, penalty='none')
    model.fit(X_hat.reshape(-1, 1), Y)
    #
    beta = model.predict_proba([[1], [0]])[:,0]

    return float(np.diff(beta))


def interventional_connection_probability(
    x, y, stim_times, x_mu, x_sigma, y_mu, y_sigma):
    '''Estimates causal connectivity between upstream (x) and downstream (y)
    assuming upstream to be exogenous i.e. decorrelated with network activity.

    Parameters
    ----------
    x : array
        Upstream spike times
    y : array
        Downstream spike times
    stim_times : array
        Stimulation onset times
    x_mu : float
        Average stimulus response time for upstream spikes (y)
    y_sigma : float
        Standard deviation of upstream stimulus response times.
    y_mu : float
        Average stimulus response time for downstream spikes (y)
    y_sigma : float
        Standard deviation of downstream stimulus response times.

    Returns
    -------
    beta : float
        The causal influence of x on y. Conditional probability of spike in y
        given spike in x relative to stimuls.
    '''
    _, X, Y, stim_times = calculate_regressors(x, y, stim_times)

    X = ((X > x_mu - x_sigma) & (X < x_mu + x_sigma)).astype(int)
    Y = ((Y > y_mu - y_sigma) & (Y < y_mu + y_sigma)).astype(int)

    model = LogisticRegression(C=1e5, solver='liblinear')
    model.fit(X.reshape(-1,1), Y)

    prob = model.predict_proba([[1], [0]])[:,0]
    beta = float(np.diff(prob))

    return beta


def instrumental_connection_probability_nonparametric(
    x, y, stim_times, n_bases=20, bin_size=1e-3, offset=1e-2, cutoff=None):
    '''Estimates causal connectivity between upstream (x) and downstream (y)
    assuming upstream to be exogenous i.e. decorrelated with network activity.

    Parameters
    ----------
    x : array
        Upstream spike times
    y : array
        Downstream spike times
    stim_times : array
        Stimulation onset times
    Returns
    -------
    beta : float
        The causal influence of x on y. Conditional probability of spike in y
        given spike in x relative to stimuls.
    '''
    Z, X, Y, stim_times = calculate_regressors(x, y, stim_times)

    Z = np.abs(Z)
    if cutoff is None:
        cutoff = Z.max()

    time, bases, centers = raised_cosine(
        n_bases, bin_size, np.array([0, cutoff]), offset)
    Z_ = np.zeros((len(Z), n_bases))

    def index(t, bin_size):
        return np.minimum(np.ceil(t / bin_size).astype(int), len(time)-1)

    idxs = index(Z, bin_size)
    Z_[:, :] = bases[idxs, :]

    # Z_ = np.vstack((Z_, np.ones(Z.shape[0]))).T

    W = np.linalg.lstsq(Z_, X, rcond=None)[0]
    X_hat = np.dot(Z_, W)

    X_hat_ = np.vstack((X_hat, np.ones(X.shape[0]))).T
    beta, _ = np.linalg.lstsq(X_hat_, Y, rcond=None)[0]


    return beta


def connection_probability_nonparametric(x, y, stim_times):
    '''Estimates causal connectivity between upstream (x) and downstream (y)
    assuming upstream to be exogenous i.e. decorrelated with network activity.

    Parameters
    ----------
    x : array
        Upstream spike times
    y : array
        Downstream spike times
    stim_times : array
        Stimulation onset times
    Returns
    -------
    beta : float
        The causal influence of x on y. Conditional probability of spike in y
        given spike in x relative to stimuls.
    '''
    _, X, Y, stim_times = calculate_regressors(x, y, stim_times)

    X_ = np.vstack((X, np.ones(X.shape[0]))).T

    beta, _ = np.linalg.lstsq(X_, Y, rcond=None)[0]

    return beta
