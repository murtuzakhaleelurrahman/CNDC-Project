"""Small dependency-free descriptive statistics used by experiment reports."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, stdev
from typing import Iterable


# Two-sided 95% Student-t critical values. For df > 30 the normal
# approximation is sufficiently close for this descriptive project report.
T_CRITICAL_95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


@dataclass(frozen=True)
class DescriptiveStatistics:
    count: int
    mean: float
    standard_deviation: float
    ci95_low: float
    ci95_high: float
    minimum: float
    maximum: float


def describe_95(values: Iterable[float]) -> DescriptiveStatistics:
    """Return mean, sample SD and a two-sided 95% confidence interval."""
    sample = [float(value) for value in values if value is not None]
    if not sample:
        raise ValueError("At least one numeric observation is required")
    average = mean(sample)
    sample_sd = stdev(sample) if len(sample) > 1 else 0.0
    if len(sample) > 1:
        degrees_of_freedom = len(sample) - 1
        critical = T_CRITICAL_95.get(degrees_of_freedom, 1.96)
        margin = critical * sample_sd / math.sqrt(len(sample))
    else:
        margin = 0.0
    return DescriptiveStatistics(
        count=len(sample),
        mean=average,
        standard_deviation=sample_sd,
        ci95_low=average - margin,
        ci95_high=average + margin,
        minimum=min(sample),
        maximum=max(sample),
    )
