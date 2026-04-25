from __future__ import annotations

from autoharness.validation import (
    aggregate_validation_runs,
    classify_validation_payload,
    classify_validation_run,
)


def test_classify_validation_run_distinguishes_timeout_parse_and_process_failures() -> None:
    assert classify_validation_run({"success": False, "timed_out": True}) == "benchmark_timeout"
    assert classify_validation_run(
        {
            "success": False,
            "metadata": {"metrics_parse_error": "bad metrics"},
        }
    ) == "benchmark_metrics_parse_error"
    assert classify_validation_run(
        {
            "success": False,
            "process_error": "missing working directory",
        }
    ) == "benchmark_process_error"


def test_aggregate_validation_runs_tracks_failure_classes() -> None:
    summary = aggregate_validation_runs(
        [
            {
                "success": False,
                "timed_out": True,
                "duration_seconds": 1.0,
            },
            {
                "success": False,
                "metadata": {"metrics_parse_error": "bad metrics"},
                "duration_seconds": 1.0,
            },
            {
                "success": True,
                "metrics": {"pass_rate": 1.0},
                "duration_seconds": 1.0,
            },
        ],
        dry_run=False,
        confidence_level=0.85,
    )

    assert summary["failure_class_counts"] == {
        "benchmark_timeout": 1,
        "benchmark_metrics_parse_error": 1,
    }
    assert set(summary["failure_classes"]) == {
        "benchmark_timeout",
        "benchmark_metrics_parse_error",
    }
    assert summary["stability_summary"]["mixed_failure_classes"] is True
    assert summary["primary_failure_class"] in {
        "benchmark_timeout",
        "benchmark_metrics_parse_error",
    }


def test_classify_validation_payload_prefers_summary_primary_failure_class() -> None:
    assert (
        classify_validation_payload(
            {
                "validation_summary": {
                    "primary_failure_class": "benchmark_signal_error",
                }
            }
        )
        == "benchmark_signal_error"
    )
