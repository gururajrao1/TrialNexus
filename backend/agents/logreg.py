"""Stdlib logistic regression (batch gradient descent, L2).

Fitting machinery for graduating bootloader points models to fitted
coefficients on user-supplied tabular data (e.g. TrialBench slices after
data-use approval). No data ships here; the fitter is validated on
synthetic blobs in the test suite. Deterministic: zero init, fixed order.
"""

from __future__ import annotations

import math


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def fit_logreg(
    X: list[list[float]],
    y: list[int],
    l2: float = 0.1,
    iters: int = 2000,
    lr: float = 0.1,
) -> tuple[list[float], float]:
    """Fit binary LR; returns (weights, bias). Raises on empty input."""
    if not X or not y or len(X) != len(y):
        raise ValueError("X and y must be non-empty and aligned")
    p = len(X[0])
    w = [0.0] * p
    b = 0.0
    n = len(X)
    for _ in range(iters):
        gw = [0.0] * p
        gb = 0.0
        for xi, yi in zip(X, y):
            pred = _sigmoid(sum(wi * xij for wi, xij in zip(w, xi)) + b)
            err = pred - yi
            for j in range(p):
                gw[j] += err * xi[j]
            gb += err
        for j in range(p):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return w, b


def predict_proba(X: list[list[float]], w: list[float], b: float) -> list[float]:
    """P(y=1) for each row under weights w and bias b."""
    return [_sigmoid(sum(wi * xij for wi, xij in zip(w, xi)) + b) for xi in X]


def auc_score(scores: list[float], labels: list[int]) -> float:
    """Mann-Whitney AUC; ties credit 0.5; single-class returns 0.5."""
    pos = [s for s, lab in zip(scores, labels) if lab == 1]
    neg = [s for s, lab in zip(scores, labels) if lab == 0]
    if not pos or not neg:
        return 0.5
    wins = 0.0
    for ps in pos:
        for ns in neg:
            if ps > ns:
                wins += 1.0
            elif ps == ns:
                wins += 0.5
    return wins / (len(pos) * len(neg))
