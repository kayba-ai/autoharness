from __future__ import annotations

from autoharness.search import (
    compute_candidate_branch_score,
    rank_beam_candidate,
    resolve_beam_group_start,
    resolve_focus_task_ids,
    resolve_intervention_class,
    resolve_next_stage,
    summarize_beam_group_outcomes,
    strategy_prefers_regressions,
    strategy_rotates_focus,
    strategy_uses_beam,
    strategy_uses_scoring,
)


def test_resolve_intervention_class_supports_greedy_and_round_robin() -> None:
    classes = ("config", "source", "prompt")

    assert (
        resolve_intervention_class(
            strategy_id="greedy_failure_focus",
            intervention_classes=classes,
            candidate_index=0,
        )
        == "config"
    )
    assert (
        resolve_intervention_class(
            strategy_id="greedy_failure_focus",
            intervention_classes=classes,
            candidate_index=2,
        )
        == "config"
    )
    assert (
        resolve_intervention_class(
            strategy_id="round_robin_interventions",
            intervention_classes=classes,
            candidate_index=0,
        )
        == "config"
    )
    assert (
        resolve_intervention_class(
            strategy_id="round_robin_interventions",
            intervention_classes=classes,
            candidate_index=1,
        )
        == "source"
    )
    assert (
        resolve_intervention_class(
            strategy_id="round_robin_interventions",
            intervention_classes=classes,
            candidate_index=2,
        )
        == "prompt"
    )


def test_resolve_focus_task_ids_supports_greedy_and_round_robin() -> None:
    failure_summary = {"task_keys": ["task_a", "task_b", "task_c"]}
    regression_summary = {"task_keys": ["regressed_a", "regressed_b"]}

    assert resolve_focus_task_ids(
        strategy_id="greedy_failure_focus",
        candidate_index=0,
        latest_failure_summary=failure_summary,
        latest_regression_summary=regression_summary,
    ) == (("task_a",), ("regressed_a",))
    assert resolve_focus_task_ids(
        strategy_id="round_robin_interventions",
        candidate_index=1,
        latest_failure_summary=failure_summary,
        latest_regression_summary=regression_summary,
    ) == (("task_b",), ())
    assert resolve_focus_task_ids(
        strategy_id="round_robin_interventions",
        candidate_index=1,
        latest_failure_summary=None,
        latest_regression_summary=regression_summary,
    ) == ((), ("regressed_b",))
    assert resolve_focus_task_ids(
        strategy_id="regression_first",
        candidate_index=0,
        latest_failure_summary=failure_summary,
        latest_regression_summary=regression_summary,
    ) == ((), ("regressed_a",))
    assert resolve_focus_task_ids(
        strategy_id="alternate_failure_regression",
        candidate_index=0,
        latest_failure_summary=failure_summary,
        latest_regression_summary=regression_summary,
    ) == (("task_a",), ())
    assert resolve_focus_task_ids(
        strategy_id="alternate_failure_regression",
        candidate_index=1,
        latest_failure_summary=failure_summary,
        latest_regression_summary=regression_summary,
    ) == ((), ("regressed_a",))


def test_resolve_next_stage_supports_fixed_and_advancing_modes() -> None:
    assert resolve_next_stage(
        current_stage="screening",
        stage_progression_mode="fixed",
        candidate_status="success",
        promoted=False,
    ) == "screening"
    assert resolve_next_stage(
        current_stage="screening",
        stage_progression_mode="advance_on_success",
        candidate_status="success",
        promoted=False,
    ) == "validation"
    assert resolve_next_stage(
        current_stage="validation",
        stage_progression_mode="advance_on_promotion",
        candidate_status="success",
        promoted=False,
    ) == "validation"
    assert resolve_next_stage(
        current_stage="holdout",
        stage_progression_mode="advance_on_promotion",
        candidate_status="success",
        promoted=True,
    ) == "transfer"


def test_strategy_helpers_flag_regression_and_rotation_modes() -> None:
    assert strategy_prefers_regressions("regression_first") is True
    assert strategy_prefers_regressions("greedy_failure_focus") is False
    assert strategy_rotates_focus("alternate_failure_regression") is True
    assert strategy_rotates_focus("round_robin_interventions") is True
    assert strategy_rotates_focus("greedy_failure_focus") is False


def test_beam_helpers_cycle_interventions_and_group_indices() -> None:
    classes = ("config", "source", "prompt")

    assert (
        resolve_intervention_class(
            strategy_id="beam_interventions",
            intervention_classes=classes,
            candidate_index=0,
        )
        == "config"
    )
    assert (
        resolve_intervention_class(
            strategy_id="beam_interventions",
            intervention_classes=classes,
            candidate_index=1,
        )
        == "source"
    )
    assert (
        resolve_intervention_class(
            strategy_id="beam_interventions",
            intervention_classes=classes,
            candidate_index=2,
        )
        == "prompt"
    )
    assert strategy_uses_beam("beam_interventions") is True
    assert strategy_uses_beam("beam_scored") is True
    assert strategy_uses_beam("greedy_failure_focus") is False
    assert strategy_uses_scoring("beam_scored") is True
    assert strategy_uses_scoring("diversity_first") is True
    assert strategy_uses_scoring("greedy_failure_focus") is False
    assert resolve_beam_group_start(candidate_index=0, beam_width=3) == 0
    assert resolve_beam_group_start(candidate_index=1, beam_width=3) == 0
    assert resolve_beam_group_start(candidate_index=5, beam_width=3) == 3


def test_resolve_focus_task_ids_supports_beam_groups() -> None:
    failure_summary = {"task_keys": ["task_a", "task_b", "task_c"]}
    regression_summary = {"task_keys": ["regressed_a", "regressed_b"]}

    assert resolve_focus_task_ids(
        strategy_id="beam_interventions",
        candidate_index=0,
        latest_failure_summary=failure_summary,
        latest_regression_summary=regression_summary,
    ) == (("task_a",), ("regressed_a",))
    assert resolve_focus_task_ids(
        strategy_id="beam_interventions",
        candidate_index=1,
        latest_failure_summary=failure_summary,
        latest_regression_summary=regression_summary,
    ) == (("task_b",), ("regressed_a",))


def test_summarize_beam_group_outcomes_distinguishes_soft_and_hard_failures() -> None:
    outcomes = summarize_beam_group_outcomes(
        [
            {
                "index": 0,
                "status": "failed",
                "failure_class": "stage_gate_failed",
                "intervention_class": "config",
                "generation_request": {"beam_group_index": 0, "beam_slot_index": 0},
            },
            {
                "index": 1,
                "status": "failed",
                "failure_class": "benchmark_command_failed",
                "intervention_class": "source",
                "generation_request": {"beam_group_index": 1, "beam_slot_index": 0},
            },
            {
                "index": 2,
                "status": "inconclusive",
                "failure_class": "benchmark_inconclusive",
                "intervention_class": "prompt",
                "generation_request": {"beam_group_index": 1, "beam_slot_index": 1},
            },
        ]
    )

    assert outcomes[0] == {
        "attempts": 1,
        "soft_failures": 1,
        "hard_failures": 0,
        "inconclusive": 0,
        "successes": 0,
    }
    assert outcomes[1] == {
        "attempts": 2,
        "soft_failures": 0,
        "hard_failures": 1,
        "inconclusive": 1,
        "successes": 0,
    }


def test_rank_beam_candidate_prefers_cleaner_and_more_novel_groups() -> None:
    candidate_snapshots = [
        {
            "index": 0,
            "status": "failed",
            "failure_class": "stage_gate_failed",
            "intervention_class": "config",
            "generation_request": {
                "beam_group_index": 0,
                "beam_slot_index": 0,
                "failure_focus_task_ids": ["task_a"],
                "regressed_task_ids": [],
            },
        },
        {
            "index": 1,
            "status": "pending",
            "failure_class": None,
            "intervention_class": "config",
            "generation_request": {
                "beam_group_index": 0,
                "beam_slot_index": 1,
                "failure_focus_task_ids": ["task_a"],
                "regressed_task_ids": [],
            },
        },
        {
            "index": 2,
            "status": "pending",
            "failure_class": None,
            "intervention_class": "source",
            "generation_request": {
                "beam_group_index": 1,
                "beam_slot_index": 0,
                "failure_focus_task_ids": ["task_b"],
                "regressed_task_ids": [],
            },
        },
    ]
    group_outcomes = summarize_beam_group_outcomes(candidate_snapshots)
    attempted_intervention_classes = {"config"}

    repeated_priority = rank_beam_candidate(
        strategy_id="beam_interventions",
        candidate_snapshot=candidate_snapshots[1],
        group_outcomes=group_outcomes,
        attempted_intervention_classes=attempted_intervention_classes,
    )
    novel_priority = rank_beam_candidate(
        strategy_id="beam_interventions",
        candidate_snapshot=candidate_snapshots[2],
        group_outcomes=group_outcomes,
        attempted_intervention_classes=attempted_intervention_classes,
    )

    assert novel_priority < repeated_priority


def test_rank_beam_candidate_prefers_regression_focus_for_regression_first() -> None:
    candidate_snapshot = {
        "index": 0,
        "status": "pending",
        "failure_class": None,
        "intervention_class": "config",
        "generation_request": {
            "beam_group_index": 0,
            "beam_slot_index": 0,
            "failure_focus_task_ids": [],
            "regressed_task_ids": ["task_r"],
        },
    }
    non_regression_snapshot = {
        "index": 1,
        "status": "pending",
        "failure_class": None,
        "intervention_class": "source",
        "generation_request": {
            "beam_group_index": 1,
            "beam_slot_index": 0,
            "failure_focus_task_ids": ["task_f"],
            "regressed_task_ids": [],
        },
    }
    group_outcomes = summarize_beam_group_outcomes([candidate_snapshot, non_regression_snapshot])

    regression_priority = rank_beam_candidate(
        strategy_id="regression_first",
        candidate_snapshot=candidate_snapshot,
        group_outcomes=group_outcomes,
        attempted_intervention_classes=set(),
    )
    non_regression_priority = rank_beam_candidate(
        strategy_id="regression_first",
        candidate_snapshot=non_regression_snapshot,
        group_outcomes=group_outcomes,
        attempted_intervention_classes=set(),
    )

    assert regression_priority < non_regression_priority


def test_compute_candidate_branch_score_rewards_novelty_and_penalizes_flakes() -> None:
    novel_pending = {
        "index": 0,
        "status": "pending",
        "failure_class": None,
        "intervention_class": "source",
        "generation_request": {
            "stage": "validation",
            "failure_focus_task_ids": ["task_a"],
            "regressed_task_ids": [],
        },
    }
    repeated_flaky = {
        "index": 1,
        "status": "success",
        "failure_class": None,
        "intervention_class": "config",
        "promoted": False,
        "flaky": True,
        "benchmark_cost": 4.0,
        "benchmark_duration_seconds": 30.0,
        "generation_request": {
            "stage": "validation",
            "failure_focus_task_ids": ["task_a"],
            "regressed_task_ids": [],
        },
    }

    novel_score, novel_rationale = compute_candidate_branch_score(
        strategy_id="diversity_first",
        candidate_snapshot=novel_pending,
        attempted_intervention_classes={"config"},
    )
    flaky_score, flaky_rationale = compute_candidate_branch_score(
        strategy_id="stability_weighted",
        candidate_snapshot=repeated_flaky,
        attempted_intervention_classes={"config"},
    )

    assert novel_score > flaky_score
    assert novel_rationale["novelty_bonus"] > 0.0
    assert flaky_rationale["stability_penalty"] >= 2.0


def test_compute_candidate_branch_score_penalizes_retry_history_and_low_stability() -> None:
    clean_candidate = {
        "index": 0,
        "status": "success",
        "failure_class": None,
        "intervention_class": "source",
        "promoted": False,
        "comparison_decision": "improved",
        "stability_score": 0.95,
        "confidence_interval_width": 0.1,
        "attempt_count": 1,
        "retry_count_total": 0,
        "generation_request": {
            "stage": "validation",
            "failure_focus_task_ids": ["task_a"],
            "regressed_task_ids": [],
        },
    }
    unstable_retry_candidate = {
        "index": 1,
        "status": "pending",
        "failure_class": "benchmark_timeout",
        "intervention_class": "source",
        "promoted": False,
        "comparison_decision": "inconclusive",
        "stability_score": 0.6,
        "confidence_interval_width": 0.7,
        "attempt_count": 3,
        "retry_count_total": 2,
        "generation_request": {
            "stage": "validation",
            "failure_focus_task_ids": ["task_a"],
            "regressed_task_ids": [],
        },
    }

    clean_score, _clean_rationale = compute_candidate_branch_score(
        strategy_id="stability_weighted",
        candidate_snapshot=clean_candidate,
        attempted_intervention_classes=set(),
    )
    unstable_score, unstable_rationale = compute_candidate_branch_score(
        strategy_id="stability_weighted",
        candidate_snapshot=unstable_retry_candidate,
        attempted_intervention_classes=set(),
    )

    assert clean_score > unstable_score
    assert unstable_rationale["retry_penalty"] > 0.0
    assert unstable_rationale["attempt_penalty"] > 0.0
    assert unstable_rationale["confidence_interval_penalty"] > 0.0
    assert unstable_rationale["comparison_bonus"] < 0.0


def test_rank_beam_candidate_uses_branch_score_as_tie_breaker() -> None:
    group_outcomes = {
        0: {
            "attempts": 0,
            "soft_failures": 0,
            "hard_failures": 0,
            "inconclusive": 0,
            "successes": 0,
        }
    }
    repeated_snapshot = {
        "index": 0,
        "status": "pending",
        "failure_class": None,
        "intervention_class": "source",
        "generation_request": {
            "beam_group_index": 0,
            "beam_slot_index": 0,
            "failure_focus_task_ids": ["task_a"],
            "regressed_task_ids": [],
        },
    }
    stronger_snapshot = {
        "index": 1,
        "status": "pending",
        "failure_class": None,
        "intervention_class": "source",
        "generation_request": {
            "beam_group_index": 0,
            "beam_slot_index": 1,
            "failure_focus_task_ids": ["task_a"],
            "regressed_task_ids": [],
        },
    }

    weaker_priority = rank_beam_candidate(
        strategy_id="beam_scored",
        candidate_snapshot=repeated_snapshot,
        group_outcomes=group_outcomes,
        attempted_intervention_classes=set(),
        branch_score=1.0,
    )
    stronger_priority = rank_beam_candidate(
        strategy_id="beam_scored",
        candidate_snapshot=stronger_snapshot,
        group_outcomes=group_outcomes,
        attempted_intervention_classes=set(),
        branch_score=2.0,
    )

    assert stronger_priority < weaker_priority
