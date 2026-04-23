import argparse
import json
from pathlib import Path

import pytest

from autoharness.queries import IterationQuerySpec, query_workspace_iteration_items


def _write_iteration_summary(
    *,
    iterations_dir: Path,
    iteration_id: str,
    track_id: str,
    stage: str,
    created_at: str,
    hypothesis: str,
    notes: str,
    saved_plan: bool = False,
) -> None:
    iteration_dir = iterations_dir / iteration_id
    iteration_dir.mkdir(parents=True)
    (iteration_dir / "summary.json").write_text(
        json.dumps(
            {
                "iteration_id": iteration_id,
                "track_id": track_id,
                "record_id": f"run_{iteration_id}",
                "adapter_id": "generic_command",
                "benchmark_name": "smoke",
                "stage": stage,
                "created_at": created_at,
                "hypothesis": hypothesis,
                "notes": notes,
                "status": "success",
                "success": True,
                "dry_run": False,
                "iteration_path": str(iteration_dir),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if saved_plan:
        (iteration_dir / "source_plan.json").write_text("{}", encoding="utf-8")


def test_iteration_query_spec_from_args_prefers_resolved_track_id() -> None:
    args = argparse.Namespace(
        track_id="ignored",
        stage="holdout",
        status="dry_run",
        benchmark_name="smoke",
        adapter_id="generic_command",
        hypothesis_contains="beta",
        notes_contains="saved plan",
        sort_by="created_at",
        descending=True,
        since="2026-01-02",
        until="2026-01-03",
        saved_plan_only=True,
        limit=5,
    )

    spec = IterationQuerySpec.from_args(args, resolved_track_id="main")

    assert spec == IterationQuerySpec(
        track_id="main",
        stage="holdout",
        status="dry_run",
        benchmark_name="smoke",
        adapter_id="generic_command",
        hypothesis_contains="beta",
        notes_contains="saved plan",
        sort_by="created_at",
        descending=True,
        since="2026-01-02",
        until="2026-01-03",
        saved_plan_only=True,
        limit=5,
    )


def test_query_workspace_iteration_items_filters_saved_plan_runs(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    iterations_dir = root / "demo" / "iterations"
    _write_iteration_summary(
        iterations_dir=iterations_dir,
        iteration_id="iter_0001",
        track_id="main",
        stage="screening",
        created_at="2026-01-01T00:00:00Z",
        hypothesis="first",
        notes="",
    )
    _write_iteration_summary(
        iterations_dir=iterations_dir,
        iteration_id="iter_0002",
        track_id="main",
        stage="validation",
        created_at="2026-01-02T00:00:00Z",
        hypothesis="second",
        notes="saved plan",
        saved_plan=True,
    )

    items, saved_plan_total = query_workspace_iteration_items(
        root=root,
        workspace_id="demo",
        last_iteration_id="iter_0002",
        spec=IterationQuerySpec(
            saved_plan_only=True,
            sort_by="created_at",
        ),
    )

    assert saved_plan_total == 1
    assert len(items) == 1
    assert items[0]["iteration_id"] == "iter_0002"
    assert items[0]["saved_plan_run"] is True
    assert items[0]["last_iteration"] is True


def test_query_workspace_iteration_items_applies_date_sort_and_limit_filters(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    iterations_dir = root / "demo" / "iterations"
    _write_iteration_summary(
        iterations_dir=iterations_dir,
        iteration_id="iter_0001",
        track_id="main",
        stage="screening",
        created_at="2026-01-01T12:00:00Z",
        hypothesis="alpha",
        notes="plain",
    )
    _write_iteration_summary(
        iterations_dir=iterations_dir,
        iteration_id="iter_0002",
        track_id="main",
        stage="holdout",
        created_at="2026-01-02T12:00:00Z",
        hypothesis="beta plan",
        notes="saved plan",
        saved_plan=True,
    )
    _write_iteration_summary(
        iterations_dir=iterations_dir,
        iteration_id="iter_0003",
        track_id="alt",
        stage="holdout",
        created_at="2026-01-02T18:00:00Z",
        hypothesis="beta alt",
        notes="saved plan",
        saved_plan=True,
    )

    items, saved_plan_total = query_workspace_iteration_items(
        root=root,
        workspace_id="demo",
        last_iteration_id="iter_0003",
        spec=IterationQuerySpec(
            track_id="main",
            stage="holdout",
            since="2026-01-02",
            until="2026-01-02",
            sort_by="created_at",
            descending=True,
            limit=1,
        ),
    )

    assert saved_plan_total == 1
    assert [item["iteration_id"] for item in items] == ["iter_0002"]
    assert items[0]["source_plan_artifact_path"] == str(
        iterations_dir / "iter_0002" / "source_plan.json"
    )


def test_query_workspace_iteration_items_rejects_invalid_time_window(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    iterations_dir = root / "demo" / "iterations"
    _write_iteration_summary(
        iterations_dir=iterations_dir,
        iteration_id="iter_0001",
        track_id="main",
        stage="screening",
        created_at="2026-01-01T12:00:00Z",
        hypothesis="alpha",
        notes="plain",
    )

    with pytest.raises(
        SystemExit,
        match="`--since` must be earlier than or equal to `--until`.",
    ):
        query_workspace_iteration_items(
            root=root,
            workspace_id="demo",
            last_iteration_id=None,
            spec=IterationQuerySpec(
                since="2026-01-03",
                until="2026-01-02",
            ),
        )
