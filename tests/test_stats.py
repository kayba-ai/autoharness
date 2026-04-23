from autoharness.stats import (
    mean_confidence_interval,
    paired_mean_confidence_interval,
    wilson_interval,
    z_value,
)


def test_z_value_increases_with_confidence_level() -> None:
    assert z_value(0.95) > z_value(0.85)


def test_wilson_interval_handles_perfect_successes() -> None:
    lower, upper = wilson_interval(successes=3, trials=3, confidence_level=0.85)
    assert round(lower, 3) == 0.591
    assert upper == 1.0


def test_mean_confidence_interval_collapses_for_constant_values() -> None:
    lower, upper = mean_confidence_interval([1.0, 1.0, 1.0], confidence_level=0.85)
    assert lower == 1.0
    assert upper == 1.0


def test_paired_mean_confidence_interval_uses_deltas() -> None:
    lower, upper = paired_mean_confidence_interval(
        [1.0, 1.0, 1.0],
        [0.0, 0.0, 0.0],
        confidence_level=0.85,
    )
    assert lower == 1.0
    assert upper == 1.0
