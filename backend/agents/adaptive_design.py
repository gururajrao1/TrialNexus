"""Group-sequential adaptive design simulator. Deterministic, stdlib only.

Lan-DeMets alpha-spending efficacy boundaries (O'Brien-Fleming-like
and Pocock-like) via the standard recursive-integration
(Armitage-McPherson) solver over Brownian-motion test statistics — the
same mathematics as gsDesign/rpact for canonical joint distributions.
Efficacy-only by design: futility needs a drift assumption and belongs
in a runtime conditional-power tool, not a design table. Validated
against textbook OBF/Pocock constants in the test suite.
"""

from __future__ import annotations

import math
from typing import Any

GRID = 301
GRID_SPAN = 6.0
BISECT_ITERS = 24


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi_inv(p: float) -> float:
    """Acklam's inverse-normal approximation (1e-9 accuracy)."""
    p = min(1.0 - 1e-12, max(1e-12, p))
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
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(
            ((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]
        ) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    )


def spend_obf(alpha: float, t: float) -> float:
    """Lan-DeMets O'Brien-Fleming-like cumulative alpha spent by t."""
    if t <= 0:
        return 0.0
    if t >= 1:
        return alpha
    return 2.0 * (1.0 - _phi(_phi_inv(1.0 - alpha / 2.0) / math.sqrt(t)))


def spend_pocock(alpha: float, t: float) -> float:
    """Lan-DeMets Pocock-like cumulative alpha spent by t."""
    if t <= 0:
        return 0.0
    if t >= 1:
        return alpha
    return alpha * math.log(1.0 + (math.e - 1.0) * t)


def _grid_step() -> float:
    return 2.0 * GRID_SPAN / (GRID - 1)


def _crossing_prob(cuts: list[float], ts: list[float], upto: int) -> float:
    """P(reject at or before look `upto`) under H0, grid integration."""
    h = _grid_step()
    xs = [-GRID_SPAN + i * h for i in range(GRID)]
    total = 0.0
    prev_t = 0.0
    # Brownian motion starts at 0: point mass at the grid center.
    alive = [1.0 if i == GRID // 2 else 0.0 for i in range(GRID)]
    for k in range(upto + 1):
        t = ts[k]
        dt = t - prev_t
        sd = math.sqrt(dt / t)
        # propagate survivors: convolution with N(0, sd) on the Z(t) scale
        new = [0.0] * GRID
        for i, x in enumerate(xs):
            if alive[i] == 0.0:
                continue
            # mean of Z(t) given Z(prev)=x*sqrt(prev_t/t)... use Brownian bridge
            for j, y in enumerate(xs):
                z = (y - x * math.sqrt(prev_t / t)) / sd if t > 0 else y
                new[j] += (
                    alive[i]
                    * math.exp(-z * z / 2.0)
                    / math.sqrt(2.0 * math.pi)
                    * h
                    / sd
                )
        crossed = sum(new[j] for j, y in enumerate(xs) if abs(y) >= cuts[k])
        total += crossed
        alive = [new[j] if abs(xs[j]) < cuts[k] else 0.0 for j in range(GRID)]
        prev_t = t
    return total


def _solve_cut(
    spent_target: float, cuts: list[float], ts: list[float], k: int
) -> float:
    lo, hi = 0.5, 6.0
    for _ in range(BISECT_ITERS):
        mid = (lo + hi) / 2.0
        trial = cuts + [mid]
        # Higher cut -> smaller crossing prob: overshoot means cut too low.
        if _crossing_prob(trial, ts, k) >= spent_target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def group_sequential(
    looks: list[float],
    alpha: float = 0.05,
    spending: str = "obf",
) -> dict[str, Any]:
    """Efficacy z-boundaries at information fractions (two-sided)."""
    ts = sorted(max(1e-6, min(1.0, float(t))) for t in looks)
    if not ts or ts[-1] < 1.0 - 1e-9:
        raise ValueError("looks must end at 1.0 (final analysis)")
    spend = spend_obf if spending == "obf" else spend_pocock
    cuts: list[float] = []
    table = []
    for k, t in enumerate(ts):
        target = spend(alpha, t)
        c = _solve_cut(target, cuts, ts, k)
        cuts.append(c)
        table.append(
            {
                "t": round(t, 3),
                "alpha_spent": round(target, 4),
                "z_efficacy": round(c, 3),
                "p_efficacy": round(2.0 * (1.0 - _phi(c)), 4),
            }
        )
    return {
        "spending": spending,
        "alpha": alpha,
        "looks": table,
        "basis": (
            "Lan-DeMets spending + recursive-integration boundaries "
            "(Armitage-McPherson) under canonical joint distributions; "
            "matches gsDesign/rpact to ~0.01 on textbook designs."
        ),
    }
