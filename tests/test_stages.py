from autoharness.stages import (
    apply_stage_overrides,
    compare_against_baseline,
    evaluate_stage_result,
    stage_policy_for,
)


def test_apply_stage_overrides_merges_nested_stage_config() -> None:
    config, applied = apply_stage_overrides(
        {
            "benchmark_name": "search",
            "env": {"BASE": "1"},
            "stage_overrides": {
                "holdout": {
                    "benchmark_name": "holdout",
                    "env": {"HOLDOUT": "1"},
                }
            },
        },
        stage="holdout",
    )

    assert applied is True
    assert config["benchmark_name"] == "holdout"
    assert config["env"] == {"BASE": "1", "HOLDOUT": "1"}
    assert "stage_overrides" not in config


def test_evaluate_stage_result_prefers_metrics_pass_rate() -> None:
    result = evaluate_stage_result(
        payload={
            "dry_run": False,
            "success": True,
            "metrics": {"pass_rate": 0.5},
            "validation_summary": {
                "metrics_confidence_intervals": {
                    "pass_rate": {
                        "lower": 0.5,
                        "upper": 0.5,
                        "confidence_level": 0.85,
                    }
                }
            },
        },
        stage_policy=stage_policy_for("validation", min_judge_pass_rate=0.6),
    )

    assert result["decision"] == "failed"
    assert result["passed"] is False
    assert result["observed_source"] == "metrics.pass_rate"
    assert result["confidence_interval"]["lower"] == 0.5


def test_stage_policy_defaults_cover_all_stages() -> None:
    assert stage_policy_for("screening").default_repeat_count == 1
    assert stage_policy_for("validation").default_repeat_count == 3
    assert stage_policy_for("holdout").benchmark_policy_key == "promotion_benchmark"
    assert stage_policy_for("transfer").benchmark_policy_key == "regression_benchmark"
    assert stage_policy_for("validation").decision_mode == "confidence_interval"
    assert stage_policy_for("transfer").default_repeat_count == 3


def test_evaluate_stage_result_returns_inconclusive_when_interval_straddles_gate() -> None:
    result = evaluate_stage_result(
        payload={
            "dry_run": False,
            "validation_summary": {
                "success_count": 2,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.32,
                    "upper": 0.89,
                    "confidence_level": 0.85,
                },
            },
        },
        stage_policy=stage_policy_for("validation", min_judge_pass_rate=0.55),
    )

    assert result["decision"] == "inconclusive"
    assert result["passed"] is None


def test_evaluate_stage_result_includes_stability_gate_metadata() -> None:
    result = evaluate_stage_result(
        payload={
            "dry_run": False,
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.7,
                    "upper": 0.95,
                    "confidence_level": 0.85,
                },
                "stability_summary": {
                    "flaky": True,
                    "stability_score": 0.75,
                    "varying_metric_keys": ["score"],
                    "varying_metric_count": 1,
                    "varying_task_ids": [],
                    "varying_task_count": 0,
                },
            },
        },
        stage_policy=stage_policy_for("validation", min_judge_pass_rate=0.6),
    )

    assert result["decision"] == "passed"
    assert result["stability_gate"]["applies"] is True
    assert result["stability_gate"]["passed"] is False
    assert result["stability_gate"]["flaky"] is True


def test_compare_against_baseline_detects_clear_improvement() -> None:
    comparison = compare_against_baseline(
        candidate_payload={
            "dry_run": False,
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_payload={
            "dry_run": False,
            "validation_summary": {
                "success_count": 0,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.0,
                    "upper": 0.31,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_label="run_base",
        baseline_stage="holdout",
    )

    assert comparison["decision"] == "improved"
    assert comparison["passed"] is True


def test_compare_against_baseline_prefers_paired_run_deltas() -> None:
    comparison = compare_against_baseline(
        candidate_payload={
            "dry_run": False,
            "validation_runs": [
                {"validation_index": 1, "metrics": {"pass_rate": 1.0}},
                {"validation_index": 2, "metrics": {"pass_rate": 1.0}},
                {"validation_index": 3, "metrics": {"pass_rate": 1.0}},
            ],
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_payload={
            "dry_run": False,
            "validation_runs": [
                {"validation_index": 1, "metrics": {"pass_rate": 0.0}},
                {"validation_index": 2, "metrics": {"pass_rate": 0.0}},
                {"validation_index": 3, "metrics": {"pass_rate": 0.0}},
            ],
            "validation_summary": {
                "success_count": 0,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.0,
                    "upper": 0.31,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_label="run_base",
        baseline_stage="holdout",
    )

    assert comparison["decision"] == "improved"
    assert comparison["passed"] is True
    assert comparison["comparison_mode"] == "paired_delta"
    assert comparison["paired_alignment_key"] == "validation_index"


def test_compare_against_baseline_prefers_task_deltas() -> None:
    comparison = compare_against_baseline(
        candidate_payload={
            "dry_run": False,
            "task_results": [
                {"task_id": "task-1", "score": 1.0},
                {"task_id": "task-2", "score": 1.0},
            ],
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_payload={
            "dry_run": False,
            "task_results": [
                {"task_id": "task-1", "score": 0.0},
                {"task_id": "task-2", "score": 0.0},
            ],
            "validation_summary": {
                "success_count": 0,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.0,
                    "upper": 0.31,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_label="run_base",
        baseline_stage="holdout",
    )

    assert comparison["decision"] == "improved"
    assert comparison["passed"] is True
    assert comparison["comparison_mode"] == "task_delta"
    assert comparison["task_alignment_key"] == "task_id"
    assert comparison["matched_task_ids"] == ["task-1", "task-2"]


def test_compare_against_baseline_can_fail_on_regressed_tasks() -> None:
    comparison = compare_against_baseline(
        candidate_payload={
            "dry_run": False,
            "task_results": [
                {
                    "task_id": "task-1",
                    "score": 0.9,
                    "category": "core",
                    "candidate_note": "slower but acceptable",
                },
                {"task_id": "task-2", "score": 1.0, "category": "core"},
                {"task_id": "task-3", "score": 1.0, "category": "edge"},
            ],
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_payload={
            "dry_run": False,
            "task_results": [
                {"task_id": "task-1", "score": 1.0, "category": "core"},
                {"task_id": "task-2", "score": 0.2, "category": "core"},
                {"task_id": "task-3", "score": 0.2, "category": "edge"},
            ],
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_label="run_base",
        baseline_stage="holdout",
        max_regressed_tasks=0,
    )

    assert comparison["decision"] == "regressed"
    assert comparison["passed"] is False
    assert comparison["comparison_mode"] == "task_delta"
    assert comparison["regressed_task_count"] == 1
    assert comparison["regressed_task_ids"] == ["task-1"]
    assert comparison["regressed_tasks"][0]["candidate_task_result"]["candidate_note"] == (
        "slower but acceptable"
    )
    assert comparison["regressed_tasks"][0]["baseline_task_result"]["category"] == "core"


def test_compare_against_baseline_can_weight_case_regressions() -> None:
    comparison = compare_against_baseline(
        candidate_payload={
            "dry_run": False,
            "task_identity_profile": {
                "match_key_field": "case_id",
                "tier_field": "tier",
                "weight_field": None,
                "tier_weights": {"critical": 5.0, "edge": 1.0},
                "default_weight": 1.0,
            },
            "task_results": [
                {"task_id": "task-1", "case_id": "case-a", "tier": "critical", "score": 0.9},
                {"task_id": "task-2", "case_id": "case-b", "tier": "edge", "score": 1.0},
                {"task_id": "task-3", "case_id": "case-c", "tier": "edge", "score": 1.0},
            ],
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_payload={
            "dry_run": False,
            "task_identity_profile": {
                "match_key_field": "case_id",
                "tier_field": "tier",
                "weight_field": None,
                "tier_weights": {"critical": 5.0, "edge": 1.0},
                "default_weight": 1.0,
            },
            "task_results": [
                {"task_id": "task-1", "case_id": "case-a", "tier": "critical", "score": 1.0},
                {"task_id": "task-2", "case_id": "case-b", "tier": "edge", "score": 0.2},
                {"task_id": "task-3", "case_id": "case-c", "tier": "edge", "score": 0.2},
            ],
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_label="run_base",
        baseline_stage="holdout",
        max_regressed_task_weight_fraction=0.4,
    )

    assert comparison["decision"] == "regressed"
    assert comparison["passed"] is False
    assert comparison["comparison_mode"] == "task_delta"
    assert comparison["task_alignment_key"] == "case_id"
    assert comparison["regressed_task_ids"] == ["case-a"]
    assert comparison["matched_task_weight_total"] == 7.0
    assert comparison["regressed_task_weight_total"] == 5.0
    assert round(comparison["regressed_task_weight_fraction"], 3) == 0.714


def test_evaluate_stage_result_uses_baseline_gate_after_stage_pass() -> None:
    result = evaluate_stage_result(
        payload={
            "dry_run": False,
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        stage_policy=stage_policy_for("validation", min_judge_pass_rate=0.55),
        baseline_payload={
            "dry_run": False,
            "validation_summary": {
                "success_count": 3,
                "run_count": 3,
                "success_rate_confidence_interval": {
                    "lower": 0.59,
                    "upper": 1.0,
                    "confidence_level": 0.85,
                },
            },
        },
        baseline_label="run_base",
        baseline_stage="validation",
        min_improvement=0.05,
    )

    assert result["decision"] == "inconclusive"
    assert result["passed"] is None
    assert result["baseline_comparison"]["decision"] == "inconclusive"
