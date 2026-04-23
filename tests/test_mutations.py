import argparse

import pytest

from autoharness.autonomy import policy_for_mode
from autoharness.campaigns import CampaignEvaluatorPolicy, TrackConfig
from autoharness.mutations import (
    _apply_track_evaluator_overrides,
    _resolve_notes_update,
    _resolve_routing_policy_updates,
    _workspace_track_count_summary,
)
from autoharness.workspace import WorkspaceConfig


def test_resolve_notes_update_supports_clear_and_conflict() -> None:
    notes, changed = _resolve_notes_update(
        current_value="existing",
        value=None,
        clear=False,
    )
    assert notes == "existing"
    assert changed is False

    cleared_notes, cleared_changed = _resolve_notes_update(
        current_value="existing",
        value=None,
        clear=True,
    )
    assert cleared_notes == ""
    assert cleared_changed is True

    with pytest.raises(SystemExit, match="Use either `--notes` or `--clear-notes`, not both."):
        _resolve_notes_update(
            current_value="existing",
            value="replacement",
            clear=True,
        )


def test_resolve_routing_policy_updates_handles_clear_modes() -> None:
    args = argparse.Namespace(
        benchmark=None,
        preset=None,
        search_benchmark=None,
        promotion_benchmark=None,
        regression_benchmark=None,
        search_preset=None,
        promotion_preset=None,
        regression_preset=None,
        clear_preset=True,
        clear_search_preset=False,
        clear_promotion_preset=False,
        clear_regression_preset=False,
    )
    current = {
        "search_benchmark": "search-a",
        "promotion_benchmark": "promo-a",
        "regression_benchmark": "reg-a",
        "search_preset": "search",
        "promotion_preset": "promotion",
        "regression_preset": "regression",
    }

    removed, removed_fields = _resolve_routing_policy_updates(
        current_values=current,
        args=args,
        changed_prefix="benchmark_policy.",
        remove_cleared_presets=True,
    )
    assert "search_preset" not in removed
    assert "promotion_preset" not in removed
    assert "regression_preset" not in removed
    assert removed_fields == [
        "benchmark_policy.search_preset",
        "benchmark_policy.promotion_preset",
        "benchmark_policy.regression_preset",
    ]

    retained_none, retained_fields = _resolve_routing_policy_updates(
        current_values=current,
        args=args,
        changed_prefix="",
        remove_cleared_presets=False,
    )
    assert retained_none["search_preset"] is None
    assert retained_none["promotion_preset"] is None
    assert retained_none["regression_preset"] is None
    assert retained_fields == [
        "search_preset",
        "promotion_preset",
        "regression_preset",
    ]


def test_resolve_routing_policy_updates_applies_shared_and_specific_values() -> None:
    args = argparse.Namespace(
        benchmark="shared-benchmark",
        preset="shared-preset",
        search_benchmark=None,
        promotion_benchmark="promotion-benchmark",
        regression_benchmark=None,
        search_preset=None,
        promotion_preset=None,
        regression_preset="regression-preset",
        clear_preset=False,
        clear_search_preset=False,
        clear_promotion_preset=False,
        clear_regression_preset=False,
    )

    updated, changed_fields = _resolve_routing_policy_updates(
        current_values={
            "search_benchmark": "old-search",
            "promotion_benchmark": "old-promotion",
            "regression_benchmark": "old-regression",
            "search_preset": "old-search-preset",
            "promotion_preset": "old-promotion-preset",
            "regression_preset": "old-regression-preset",
        },
        args=args,
        changed_prefix="benchmark_policy.",
        remove_cleared_presets=True,
    )

    assert updated == {
        "search_benchmark": "shared-benchmark",
        "promotion_benchmark": "promotion-benchmark",
        "regression_benchmark": "shared-benchmark",
        "search_preset": "shared-preset",
        "promotion_preset": "shared-preset",
        "regression_preset": "regression-preset",
    }
    assert changed_fields == [
        "benchmark_policy.search_benchmark",
        "benchmark_policy.promotion_benchmark",
        "benchmark_policy.regression_benchmark",
        "benchmark_policy.search_preset",
        "benchmark_policy.promotion_preset",
        "benchmark_policy.regression_preset",
    ]


def test_apply_track_evaluator_overrides_updates_requested_fields() -> None:
    evaluator = CampaignEvaluatorPolicy(
        evaluator_version="2026-01-01",
        judge_model="gpt-4.1-mini",
        diagnostic_model="gpt-4.1-mini",
        max_diagnostic_tasks=3,
        min_judge_pass_rate=0.55,
    )
    args = argparse.Namespace(
        evaluator_version=None,
        judge_model="gpt-5-mini",
        diagnostic_model=None,
        max_diagnostic_tasks=7,
        min_judge_pass_rate=None,
    )

    updated, changed_fields = _apply_track_evaluator_overrides(
        evaluator=evaluator,
        args=args,
    )

    assert updated.judge_model == "gpt-5-mini"
    assert updated.max_diagnostic_tasks == 7
    assert updated.evaluator_version == "2026-01-01"
    assert changed_fields == [
        "evaluator.judge_model",
        "evaluator.max_diagnostic_tasks",
    ]


def test_workspace_track_count_summary_counts_active_and_archived_tracks() -> None:
    workspace = WorkspaceConfig(
        format_version="autoharness.workspace.v1",
        workspace_id="demo",
        objective="Improve harness correctness",
        domain="qa",
        active_track_id="main",
        created_at="2026-01-01T00:00:00Z",
        autonomy=policy_for_mode("proposal"),
        benchmark_policy={
            "search_benchmark": "bench-search",
            "promotion_benchmark": "bench-promotion",
            "regression_benchmark": "bench-regression",
        },
        tracks={
            "main": TrackConfig(
                track_id="main",
                benchmark="bench-a",
                objective="Improve bench a",
                campaign_id="demo_main",
                status="active",
            ),
            "alt": TrackConfig(
                track_id="alt",
                benchmark="bench-b",
                objective="Improve bench b",
                campaign_id="demo_alt",
                status="archived",
            ),
        },
    )

    assert _workspace_track_count_summary(workspace) == {
        "tracks_total": 2,
        "active_tracks_total": 1,
        "archived_tracks_total": 1,
    }
