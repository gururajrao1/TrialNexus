"""Design calculators: sample size, NI margin, trial budget. Pure math."""

from __future__ import annotations

import math
from typing import Any


def _ndtri(p: float) -> float:
    """Acklam inverse-normal CDF approximation (1e-9 accuracy)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1
        )
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    )


def sample_size_proportions(
    p1: float,
    p2: float,
    alpha: float = 0.05,
    power: float = 0.8,
    dropout: float = 0.0,
) -> dict[str, Any]:
    """Per-group n for two proportions (two-sided normal approximation)."""
    for v, name in ((p1, "p1"), (p2, "p2")):
        if not 0.0 < v < 1.0:
            raise ValueError(f"{name} must be in (0, 1)")
    if abs(p1 - p2) < 1e-12:
        raise ValueError("p1 and p2 must differ")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be in (0, 1)")
    if not 0.0 <= dropout < 1.0:
        raise ValueError("dropout must be in [0, 1)")
    za = _ndtri(1 - alpha / 2)
    zb = _ndtri(power)
    pbar = (p1 + p2) / 2
    n = (
        za * math.sqrt(2 * pbar * (1 - pbar))
        + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    ) ** 2 / (p1 - p2) ** 2
    n = math.ceil(n)
    n_adj = math.ceil(n / (1 - dropout)) if dropout else n
    return {
        "method": "two-proportion z-test, two-sided normal approximation",
        "n_per_group": n,
        "n_per_group_with_dropout": n_adj,
        "total": 2 * n_adj,
        "inputs": {
            "p1": p1,
            "p2": p2,
            "alpha": alpha,
            "power": power,
            "dropout": dropout,
        },
        "basis": f"Z_alpha={za:.3f}, Z_beta={zb:.3f}, effect={abs(p1 - p2):.4f}.",
    }


def sample_size_means(
    delta: float,
    sd: float,
    alpha: float = 0.05,
    power: float = 0.8,
    dropout: float = 0.0,
) -> dict[str, Any]:
    """Per-group n for a two-sample mean difference (known SD)."""
    if delta == 0:
        raise ValueError("delta must be nonzero")
    if sd <= 0:
        raise ValueError("sd must be positive")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if not 0.0 < power < 1.0:
        raise ValueError("power must be in (0, 1)")
    if not 0.0 <= dropout < 1.0:
        raise ValueError("dropout must be in [0, 1)")
    za = _ndtri(1 - alpha / 2)
    zb = _ndtri(power)
    n = math.ceil(2 * sd * sd * (za + zb) ** 2 / (delta * delta))
    n_adj = math.ceil(n / (1 - dropout)) if dropout else n
    return {
        "method": "two-sample mean difference, known SD, two-sided",
        "n_per_group": n,
        "n_per_group_with_dropout": n_adj,
        "total": 2 * n_adj,
        "inputs": {
            "delta": delta,
            "sd": sd,
            "alpha": alpha,
            "power": power,
            "dropout": dropout,
        },
        "basis": f"Z_alpha={za:.3f}, Z_beta={zb:.3f}.",
    }


def ni_margin_check(historical_effect: float, margin: float) -> dict[str, Any]:
    """Preserved-effect fraction for a non-inferiority margin.

    Conventional bar: preserve >= 50% of the historical effect (M1).
    """
    if historical_effect <= 0:
        raise ValueError("historical_effect must be positive")
    if margin < 0:
        raise ValueError("margin must be non-negative")
    preserved = (historical_effect - margin) / historical_effect
    return {
        "preserved_fraction": round(preserved, 4),
        "bar": 0.5,
        "pass": preserved >= 0.5,
        "basis": (
            "Preserved = (M1 - margin) / M1 against the conventional "
            "50% bar. Margin choice itself needs clinical justification."
        ),
    }
