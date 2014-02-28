from __future__ import print_function
# dict_learning and _update_dic  adapted from sklearn.decomposition
# original authors and license are:
# Author: Vlad Niculae, Gael Varoquaux, Alexandre Gramfort
# License: BSD 3 clause

import sys
import time
import numpy as np

from math import sqrt
from scipy import sparse as sp
from sklearn.utils import check_random_state
from scipy import linalg
from numpy.lib.stride_tricks import as_strided
from scipy.sparse.linalg import lsqr
from scipy.sparse import csc_matrix as sparse

def lasso_cost(X, D, C, gamma):
    """
    Calculate the cost of the lasso function
    """
    norm2 = lambda x: np.dot(x.flatten(1).transpose(), x.flatten(1))
    norm1 = lambda x: np.sum(np.abs(x.flatten(1)))
    the_cost = 0.5 * norm2(X - np.dot(D, C)) + gamma * norm1(C)
    return the_cost


def lasso_admm(X_in, D_in, gamma=1, C=None, double=False, max_rho=5.0, rho=1e-4, max_iter=500):
    """
    Finds the best sparse code for a given dictionary for
    approximating the data matrix X by solving::

        (U^*,) = argmin 0.5 || X - U V ||_2^2 + gamma * || U ||_1
                     (U)

    where V is the dictionary and U is the sparse code.
    """
    dimensions, samples = X_in.shape
    dimensions, components = D_in.shape

    X = X_in.reshape(dimensions * samples).T
    D = sp.kron(sp.eye(samples), sparse(D_in))

    c = len(X)
    r = D.shape[1]

    L = sparse(np.zeros((r, c)))
    I = sp.eye(r)

    #TODO: Assert C has the right shape

    # Initialize C with zeros if it is not passed
    if C is None:
        C = np.zeros((r, c))

    fast_sthresh = lambda x, th: np.sign(x) * np.maximum(np.abs(x) - th, 0)

    cost = []

    for n in range(1, max_iter):
        # Define terms for sub-problem
        F1 = D.T.dot(D)
        F2 = rho * I
        F = F1 + F2
        G1 = D.T.dot(X)
        G2 = rho * C
        G = G1 + G2 - L

        print(F.shape, G.shape)

        B,resid,rank,s = lsqr(F,G)

        # Solve sub-problem to solve C
        C = fast_sthresh(B + L/rho, gamma/rho)
    
        # Update the Lagrangian
        L = L + np.dot(rho, B - C)
    
        rho = min(max_rho, rho*1.1)
    
        # get the current cost
        current_cost = lasso_cost(X, D, B, gamma)
        cost.append(current_cost)
    
    return B.reshape(samples, components), cost


def _update_dict(dictionary, Y, code, verbose=False, return_r2=False,
                 random_state=None):
    """Update the dense dictionary factor in place.

    Parameters
    ----------
    dictionary: array of shape (n_features, n_components)
        Value of the dictionary at the previous iteration.

    Y: array of shape (n_features, n_samples)
        Data matrix.

    code: array of shape (n_components, n_samples)
        Sparse coding of the data against which to optimize the dictionary.

    verbose:
        Degree of output the procedure will print.

    return_r2: bool
        Whether to compute and return the residual sum of squares corresponding
        to the computed solution.

    random_state: int or RandomState
        Pseudo number generator state used for random sampling.

    Returns
    -------
    dictionary: array of shape (n_features, n_components)
        Updated dictionary.

    """
    n_components = len(code)
    n_samples = Y.shape[0]
    random_state = check_random_state(random_state)
    # Residuals, computed 'in-place' for efficiency
    R = -np.dot(dictionary, code)
    R += Y
    R = np.asfortranarray(R)
    ger, = linalg.get_blas_funcs(('ger',), (dictionary, code))
    for k in range(n_components):
        # R <- 1.0 * U_k * V_k^T + R
        R = ger(1.0, dictionary[:, k], code[k, :], a=R, overwrite_a=True)
        dictionary[:, k] = np.dot(R, code[k, :].T)
        # Scale k'th atom
        atom_norm_square = np.dot(dictionary[:, k], dictionary[:, k])
        if atom_norm_square < 1e-20:
            if verbose == 1:
                sys.stdout.write("+")
                sys.stdout.flush()
            elif verbose:
                print("Adding new random atom")
            dictionary[:, k] = random_state.randn(n_samples)
            # Setting corresponding coefs to 0
            code[k, :] = 0.0
            dictionary[:, k] /= sqrt(np.dot(dictionary[:, k],
                                            dictionary[:, k]))
        else:
            dictionary[:, k] /= sqrt(atom_norm_square)
            # R <- -1.0 * U_k * V_k^T + R
            R = ger(-1.0, dictionary[:, k], code[k, :], a=R, overwrite_a=True)
    if return_r2:
        R **= 2
        # R is fortran-ordered. For numpy version < 1.6, sum does not
        # follow the quick striding first, and is thus inefficient on
        # fortran ordered data. We take a flat view of the data with no
        # striding
        R = as_strided(R, shape=(R.size, ), strides=(R.dtype.itemsize,))
        R = np.sum(R)
        return dictionary, R
    return dictionary



def dict_learning(X, n_components, alpha, max_iter=100, tol=1e-8,
                  method='admm', n_jobs=1, dict_init=None, code_init=None,
                  callback=None, verbose=False, random_state=None):
    """Solves a dictionary learning matrix factorization problem.

    Finds the best dictionary and the corresponding sparse code for
    approximating the data matrix X by solving::

        (U^*, V^*) = argmin 0.5 || X - U V ||_2^2 + alpha * || U ||_1
                     (U,V)
                    with || V_k ||_2 = 1 for all  0 <= k < n_components

    where V is the dictionary and U is the sparse code.

    Parameters
    ----------
    X: array of shape (n_samples, n_features)
        Data matrix.

    n_components: int,
        Number of dictionary atoms to extract.

    alpha: int,
        Sparsity controlling parameter.

    max_iter: int,
        Maximum number of iterations to perform.

    tol: float,
        Tolerance for the stopping condition.

    method: {'admm',}
        admm: uses ADMM to compute the lasso solution.

    n_jobs: int,
        Number of parallel jobs to run, or -1 to autodetect.

    dict_init: array of shape (n_components, n_features),
        Initial value for the dictionary for warm restart scenarios.

    code_init: array of shape (n_samples, n_components),
        Initial value for the sparse code for warm restart scenarios.

    callback:
        Callable that gets invoked every five iterations.

    verbose:
        Degree of output the procedure will print.

    random_state: int or RandomState
        Pseudo number generator state used for random sampling.

    Returns
    -------
    code: array of shape (n_samples, n_components)
        The sparse code factor in the matrix factorization.

    dictionary: array of shape (n_components, n_features),
        The dictionary factor in the matrix factorization.

    errors: array
        Vector of errors at each iteration.
    """
    if method not in ('admm'):
        raise ValueError('Coding method %r not supported as a fit algorithm.'
                         % method)

    t0 = time.time()
    # Avoid integer division problems
    alpha = float(alpha)
    random_state = check_random_state(random_state)

    if n_jobs == -1:
        raise NotImplementedError()
    #    n_jobs = cpu_count()

    # Init the code and the dictionary with SVD of Y
    if code_init is not None and dict_init is not None:
        code = np.array(code_init, order='F')
        # Don't copy V, it will happen below
        dictionary = dict_init
    else:
        code, S, dictionary = linalg.svd(X, full_matrices=False)
        dictionary = S[:, np.newaxis] * dictionary
    r = len(dictionary)
    if n_components <= r:  # True even if n_components=None
        code = code[:, :n_components]
        dictionary = dictionary[:n_components, :]
    else:
        code = np.c_[code, np.zeros((len(code), n_components - r))]
        dictionary = np.r_[dictionary,
                           np.zeros((n_components - r, dictionary.shape[1]))]

    # Fortran-order dict, as we are going to access its row vectors
    dictionary = np.array(dictionary, order='F')

    residuals = 0

    errors = []
    current_cost = np.nan

    if verbose == 1:
        print('[dict_learning]', end=' ')

    for ii in range(max_iter):
        dt = (time.time() - t0)
        if verbose == 1:
            sys.stdout.write(".")
            sys.stdout.flush()
        elif verbose:
            print ("Iteration % 3i "
                   "(elapsed time: % 3is, % 4.1fmn, current cost % 7.3f)"
                   % (ii, dt, dt / 60, current_cost))


        # Update code
        code_T, __ = lasso_admm(X.T, dictionary.T, gamma=alpha)

        code = code_T.T

        # Update dictionary
        dictionary, residuals = _update_dict(dictionary.T, X.T, code.T,
                                             verbose=verbose, return_r2=True,
                                             random_state=random_state)
        dictionary = dictionary.T

        # Cost function
        current_cost = 0.5 * residuals + alpha * np.sum(np.abs(code))
        errors.append(current_cost)

        if ii > 0:
            dE = errors[-2] - errors[-1]
            # assert(dE >= -tol * errors[-1])
            if dE < tol * errors[-1]:
                if verbose == 1:
                    # A line return
                    print("")
                elif verbose:
                    print("--- Convergence reached after %d iterations" % ii)
                break
        if ii % 5 == 0 and callback is not None:
            callback(locals())

    return code, dictionary, errors


def init_dictionary(X, n_components):
    """Use SVD to initialize a init_dictionary
       Inputs:
          X: The data
          n_components: The number of components for the dictionary
    """
    code, S, dictionary = linalg.svd(X, full_matrices=False)
    dictionary = S[:, np.newaxis] * dictionary
    r = dictionary.shape[0]
    if n_components <= r:  # True even if n_components=None
        dictionary = dictionary[:n_components, :]
    else:
        dictionary = np.r_[dictionary,
                           np.zeros((n_components - r, dictionary.shape[1]))]

    return dictionary
