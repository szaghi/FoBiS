"""stats.py — the statistics of ``fobis assess`` (standard library only: the zipapp has no numpy).

- Ensembles: mean, standard deviation, range; **significant digits** shared by the members, ``-log10(sigma/|mu|)``
  (Stott Parker's estimator for Monte Carlo arithmetic), with a one-sided 95% lower bound from the chi-square upper
  bound of sigma (exact quantiles for 1 and 2 degrees of freedom, Wilson-Hilferty above). The bound assumes
  independent random samples: for deterministic variants (flags, compilers) it is indicative only.
- Agreement of a value with a more accurate one: digits ``-log10(|v - r| / |r|)``.
- Refinement: the observed order of three levels with any ratios (Celik et al., "Procedure for estimation and
  reporting of uncertainty due to discretization in CFD applications", J. Fluids Eng. 130, 2008: fixed-point
  iteration on ``p = |ln|e32/e21| + q(p)| / ln r21``), Richardson extrapolation, Roache's Grid Convergence Index
  (safety factor 1.25), the convergence type (monotonic, oscillatory, divergent).
- Inputs: Pearson correlation, elasticity ``(dq/q) / (dp/p)``.
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist

CONFIDENCE = 0.95
GCI_SAFETY = 1.25


def mean_std(values: list[float]) -> tuple[float, float]:
    """Mean and sample standard deviation (0 for one value)."""
    n = len(values)
    mu = math.fsum(values) / n
    if n < 2:
        return mu, 0.0
    return mu, math.sqrt(math.fsum((v - mu) ** 2 for v in values) / (n - 1))


def chi2_quantile(p: float, k: int) -> float:
    """The *p* quantile of the chi-square distribution with *k* degrees of freedom."""
    if k == 1:
        return NormalDist().inv_cdf((1 + p) / 2) ** 2
    if k == 2:
        return -2.0 * math.log(1 - p)
    z = NormalDist().inv_cdf(p)
    return k * (1 - 2 / (9 * k) + z * math.sqrt(2 / (9 * k))) ** 3


def significant_digits(values: list[float], confidence: float = CONFIDENCE) -> tuple[float, float]:
    """(digits, lower bound) shared by an ensemble: ``inf`` when every member is equal, 0 around a zero mean."""
    if not all(math.isfinite(v) for v in values):
        return 0.0, 0.0
    mu, sigma = mean_std(values)
    if sigma == 0:
        return math.inf, math.inf
    if mu == 0 or len(values) < 2:
        return 0.0, 0.0
    digits = max(0.0, -math.log10(sigma / abs(mu)))
    k = len(values) - 1
    upper = sigma * math.sqrt(k / chi2_quantile(1 - confidence, k))
    return digits, max(0.0, -math.log10(upper / abs(mu)))


def digits_against(value: float, reference: float) -> float:
    """Digits of *value* that agree with *reference*: ``inf`` when equal."""
    if value == reference:
        return math.inf
    if not (math.isfinite(value) and math.isfinite(reference)) or reference == 0:
        return 0.0
    return max(0.0, -math.log10(abs(value - reference) / abs(reference)))


@dataclass
class PointDigits:
    """Digits over the points of a quantity: the fewest (and where), the median."""

    minimum: float
    median: float
    worst: int  # flat index of the fewest digits
    points: int


def over_points(per_point: list[float]) -> PointDigits:
    ordered = sorted(per_point)
    worst = min(range(len(per_point)), key=per_point.__getitem__)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return PointDigits(per_point[worst], median, worst, len(per_point))


# ── refinement ─────────────────────────────────────────────────────────────────


@dataclass
class Order:
    """Three levels (coarse, medium, fine) of a refinement study of one scalar."""

    order: float | None  # None: not defined (no change, divergence, a zero difference)
    convergence: str  # monotonic, oscillatory, divergent, stalled, exact
    extrapolated: float | None = None
    error: float | None = None  # |extrapolated - fine|
    gci: float | None = None  # Roache's grid convergence index of the fine level (relative)
    levels: list[float] = field(default_factory=list)  # the three h, coarse to fine


def observed_order(h: list[float], f: list[float]) -> Order:
    """The observed order of three levels; *h* coarse to fine (decreasing), *f* the values at those levels."""
    h3, h2, h1 = h  # Celik's numbering: 1 is the finest
    f3, f2, f1 = f
    e32, e21 = f3 - f2, f2 - f1
    if e32 == 0 and e21 == 0:
        return Order(None, "exact", f1, 0.0, 0.0, list(h))
    if e32 == 0 or e21 == 0:
        return Order(None, "stalled", None, None, None, list(h))
    ratio = e21 / e32
    if abs(ratio) >= 1:
        return Order(None, "divergent", None, None, None, list(h))
    convergence = "monotonic" if ratio > 0 else "oscillatory"
    r21, r32 = h2 / h1, h3 / h2
    s = 1.0 if ratio > 0 else -1.0
    p = abs(math.log(abs(e32 / e21))) / math.log(r21)
    for _ in range(200):
        try:
            q = math.log((r21**p - s) / (r32**p - s))
        except (ValueError, ZeroDivisionError, OverflowError):
            break
        new = abs(math.log(abs(e32 / e21)) + q) / math.log(r21)
        if abs(new - p) < 1e-12 * max(1.0, abs(p)):
            p = new
            break
        p = new
    factor = r21**p - 1
    if factor <= 0:
        return Order(p, convergence, None, None, None, list(h))
    extrapolated = (r21**p * f1 - f2) / factor
    gci = GCI_SAFETY * abs((f1 - f2) / f1) / factor if f1 else None
    return Order(p, convergence, extrapolated, abs(extrapolated - f1), gci, list(h))


def orders(h: list[float], f: list[float]) -> list[Order]:
    """The order of every consecutive triple of levels (coarse to fine)."""
    return [observed_order(h[i : i + 3], f[i : i + 3]) for i in range(len(h) - 2)]


def asymptotic(found: list[Order], tolerance: float = 0.1) -> bool | None:
    """Whether the last two triples agree on the order within *tolerance* (None with fewer than 4 levels)."""
    last = [o.order for o in found[-2:]]
    if len(last) < 2:
        return None
    if None in last or not last[1]:
        return False
    return abs(last[0] - last[1]) <= tolerance * abs(last[1])


# ── inputs ─────────────────────────────────────────────────────────────────────


def correlation(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation (None when a series is constant)."""
    mx, sx = mean_std(xs)
    my, sy = mean_std(ys)
    if sx == 0 or sy == 0:
        return None
    n = len(xs)
    return math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / ((n - 1) * sx * sy)


def elasticity(p0: float, q0: float, p_low: float, q_low: float, p_high: float, q_high: float) -> float | None:
    """Relative change of the output per relative change of the input, by central difference."""
    if q0 == 0 or p0 == 0 or p_high == p_low:
        return None
    return ((q_high - q_low) / q0) / ((p_high - p_low) / p0)
