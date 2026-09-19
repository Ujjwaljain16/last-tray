"""The two statistical methods used by the metrics, written out so the method is explicit and testable.

median            the middle value of the sorted data; for an even count, the mean of the two middle values.
percentile_linear linear interpolation between order statistics (position (n - 1) * q on a 0-based scale). This is the default method
                  of numpy and pandas (`quantile`, "linear"), and R's type 7. It is NOT nearest-rank and NOT the exclusive method.
"""
from __future__ import annotations

import math
from typing import Sequence


class StatsError(ValueError):
    pass


def median(values: Sequence[float]) -> float:
    if not values:
        raise StatsError("median of an empty population is undefined: it is never reported as 0")
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    return float(ordered[mid]) if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def percentile_linear(values: Sequence[float], q: float) -> float:
    if not values:
        raise StatsError("a percentile of an empty population is undefined: it is never reported as 0")
    if not 0 <= q <= 1:
        raise StatsError(f"q must be between 0 and 1, got {q}")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (position - low) * (ordered[high] - ordered[low])
