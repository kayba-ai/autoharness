"""Lightweight statistical helpers for repeated benchmark evaluation."""

from __future__ import annotations

import math
from statistics import NormalDist


def z_value(confidence_level: float) -> float:
    """Return the two-sided normal critical value for one confidence level."""
    _validate_confidence_level(confidence_level)
    return NormalDist().inv_cdf(0.5 + (confidence_level / 2.0))


def wilson_interval(
    *,
    successes: int,
    trials: int,
    confidence_level: float,
) -> tuple[float, float]:
    """Return the Wilson score interval for a binomial proportion."""
    _validate_confidence_level(confidence_level)
    if trials < 1:
        raise ValueError("`trials` must be at least 1.")
    if successes < 0 or successes > trials:
        raise ValueError("`successes` must be between 0 and `trials`.")

    z = z_value(confidence_level)
    phat = successes / trials
    denom = 1.0 + ((z * z) / trials)
    center = (phat + ((z * z) / (2.0 * trials))) / denom
    margin = (
        z
        * math.sqrt(
            ((phat * (1.0 - phat)) / trials) + ((z * z) / (4.0 * trials * trials))
        )
        / denom
    )
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return lower, upper


def mean_confidence_interval(
    values: list[float],
    *,
    confidence_level: float,
) -> tuple[float, float] | None:
    """Return a normal-approximation confidence interval for the sample mean."""
    _validate_confidence_level(confidence_level)
    if not values:
        return None
    if len(values) == 1:
        return values[0], values[0]

    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    standard_error = math.sqrt(variance) / math.sqrt(len(values))
    z = z_value(confidence_level)
    margin = z * standard_error
    return mean - margin, mean + margin


def paired_mean_confidence_interval(
    candidate_values: list[float],
    baseline_values: list[float],
    *,
    confidence_level: float,
) -> tuple[float, float] | None:
    """Return a confidence interval for the mean paired delta."""
    if len(candidate_values) != len(baseline_values):
        raise ValueError("Paired samples must have the same length.")
    deltas = [
        candidate - baseline
        for candidate, baseline in zip(candidate_values, baseline_values, strict=True)
    ]
    return mean_confidence_interval(deltas, confidence_level=confidence_level)


def _validate_confidence_level(confidence_level: float) -> None:
    if not (0.0 < confidence_level < 1.0):
        raise ValueError("`confidence_level` must be between 0 and 1.")
