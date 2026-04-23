import json
from pathlib import Path

from autoharness.tracking import (
    create_benchmark_record,
    create_promotion_record,
    load_benchmark_record,
    next_iteration_id,
    persist_benchmark_record,
    persist_champion_manifest,
    persist_promotion_record,
    resolve_baseline_record,
    update_state_after_promotion,
    update_state_after_iteration,
)
from autoharness.workspace import WorkspaceState


def test_create_benchmark_record_sets_dry_run_status() -> None:
    record = create_benchmark_record(
        adapter_id="tau2_bench",
        benchmark_name="tau2:airline",
        config={"domain": "airline"},
        payload={"benchmark_name": "tau2:airline", "command": ["tau2", "run"]},
        dry_run=True,
        workspace_id="demo",
        track_id="main",
    )
    assert record.status == "dry_run"
    assert record.success is None


def test_next_iteration_id_uses_zero_padded_counter() -> None:
    state = WorkspaceState(
        format_version="autoharness.workspace_state.v1",
        workspace_id="demo",
        status="active",
        active_track_id="main",
        next_iteration_index=7,
    )
    assert next_iteration_id(state) == "iter_0007"


def test_update_state_after_iteration_increments_summary(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "demo"
    workspace_dir.mkdir()
    state = WorkspaceState(
        format_version="autoharness.workspace_state.v1",
        workspace_id="demo",
        status="active",
        active_track_id="main",
    )
    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "smoke",
            "command": ["python", "-c", "print('ok')"],
            "success": True,
            "validation_run_count": 3,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
    )
    next_state = update_state_after_iteration(
        root=tmp_path,
        workspace_id="demo",
        state=state,
        record=record,
        iteration_id="iter_0001",
    )
    assert next_state.next_iteration_index == 2
    assert next_state.last_iteration_id == "iter_0001"
    assert next_state.summary["validated_candidates"] == 1
    assert next_state.summary["validation_runs_total"] == 3


def test_persist_and_load_benchmark_record_round_trip(tmp_path: Path) -> None:
    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={"benchmark_name": "smoke", "command": ["python", "-c", "print('ok')"]},
        dry_run=True,
        workspace_id="demo",
        track_id="main",
    )
    persist_benchmark_record(root=tmp_path, record=record)

    loaded = load_benchmark_record(
        root=tmp_path,
        workspace_id="demo",
        track_id="main",
        record_id=record.record_id,
    )
    assert loaded.record_id == record.record_id
    assert loaded.benchmark_name == "smoke"


def test_promotion_helpers_update_state_and_write_artifacts(tmp_path: Path) -> None:
    state = WorkspaceState(
        format_version="autoharness.workspace_state.v1",
        workspace_id="demo",
        status="active",
        active_track_id="main",
    )
    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={
            "benchmark_name": "smoke",
            "command": ["python", "-c", "print('ok')"],
            "parsed_artifact_sources": {
                "metrics": [
                    {
                        "origin": "metrics_parser.path",
                        "path": str((tmp_path / "metrics.json").resolve()),
                    }
                ]
            },
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
        iteration_id="iter_0001",
    )
    promotion = create_promotion_record(
        workspace_id="demo",
        track_id="main",
        record=record,
        target_root=tmp_path / "target",
        notes="Promote this candidate",
        edit_restore={"status": "kept"},
    )
    artifacts = persist_promotion_record(
        root=tmp_path,
        promotion=promotion,
        diff_text="--- a/file\n+++ b/file\n",
    )
    assert Path(artifacts["promotion_path"]).exists()
    assert Path(artifacts["diff_path"]).exists()
    assert Path(artifacts["parsed_artifact_sources_path"]).exists()
    assert promotion.parsed_artifact_sources == {
        "metrics": [
            {
                "origin": "metrics_parser.path",
                "path": str((tmp_path / "metrics.json").resolve()),
            }
        ]
    }
    assert json.loads(
        Path(artifacts["parsed_artifact_sources_path"]).read_text(encoding="utf-8")
    ) == promotion.parsed_artifact_sources
    persist_benchmark_record(root=tmp_path, record=record)
    champion_manifest_path = persist_champion_manifest(
        root=tmp_path,
        record=record,
        promotion=promotion,
        promotion_artifacts=artifacts,
    )
    champion_manifest = json.loads(champion_manifest_path.read_text(encoding="utf-8"))
    assert champion_manifest["record_id"] == record.record_id
    assert champion_manifest["promotion_id"] == promotion.promotion_id
    assert champion_manifest["promotion_path"] == artifacts["promotion_path"]
    assert champion_manifest["diff_path"] == artifacts["diff_path"]
    assert (
        champion_manifest["parsed_artifact_sources_path"]
        == artifacts["parsed_artifact_sources_path"]
    )
    assert champion_manifest["parsed_artifact_sources"] == promotion.parsed_artifact_sources

    next_state = update_state_after_promotion(
        root=tmp_path,
        workspace_id="demo",
        state=state,
        record_id=record.record_id,
    )
    assert next_state.current_champion_experiment_id == record.record_id
    assert next_state.summary["promotions_total"] == 1


def test_resolve_baseline_record_uses_current_champion(tmp_path: Path) -> None:
    record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="smoke",
        config={"command": ["python", "-c", "print('ok')"]},
        payload={"benchmark_name": "smoke", "command": ["python", "-c", "print('ok')"]},
        dry_run=False,
        workspace_id="demo",
        track_id="main",
    )
    persist_benchmark_record(root=tmp_path, record=record)
    state = WorkspaceState(
        format_version="autoharness.workspace_state.v1",
        workspace_id="demo",
        status="active",
        active_track_id="main",
        current_champion_experiment_id=record.record_id,
    )

    resolved = resolve_baseline_record(
        root=tmp_path,
        workspace_id="demo",
        track_id="main",
        state=state,
        baseline_source="champion",
    )
    assert resolved.record_id == record.record_id
