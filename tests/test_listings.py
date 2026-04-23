import argparse
import json
from pathlib import Path

from autoharness.listings import (
    _build_iteration_listing_payload,
    _prepare_listing_payload,
)
from autoharness.queries import IterationQuerySpec
from autoharness.workspace import WorkspaceState


def _write_iteration_summary(
    *,
    iterations_dir: Path,
    iteration_id: str,
    created_at: str,
    saved_plan: bool = False,
) -> None:
    iteration_dir = iterations_dir / iteration_id
    iteration_dir.mkdir(parents=True)
    (iteration_dir / "summary.json").write_text(
        json.dumps(
            {
                "iteration_id": iteration_id,
                "track_id": "main",
                "record_id": f"run_{iteration_id}",
                "adapter_id": "generic_command",
                "benchmark_name": "smoke",
                "stage": "holdout",
                "created_at": created_at,
                "hypothesis": "test",
                "notes": "",
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


def test_prepare_listing_payload_threads_resolved_track_id() -> None:
    args = argparse.Namespace(
        root=Path("/tmp/workspaces"),
        workspace_id="demo",
        track_id="requested",
    )

    def resolve_request(*, root: Path, workspace_id: str, requested_track_id: str | None):
        assert root == Path("/tmp/workspaces")
        assert workspace_id == "demo"
        assert requested_track_id == "requested"
        return "context", "main"

    def build_spec(parsed_args: argparse.Namespace, resolved_track_id: str | None):
        assert parsed_args is args
        assert resolved_track_id == "main"
        return "spec"

    def build_payload(context: str, spec: str):
        assert context == "context"
        assert spec == "spec"
        return {"ok": True}

    context, resolved_track_id, spec, rendered = _prepare_listing_payload(
        args=args,
        resolve_request=resolve_request,
        build_spec=build_spec,
        build_payload=build_payload,
    )

    assert context == "context"
    assert resolved_track_id == "main"
    assert spec == "spec"
    assert rendered == {"ok": True}


def test_build_iteration_listing_payload_includes_saved_plan_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspaces"
    iterations_dir = root / "demo" / "iterations"
    _write_iteration_summary(
        iterations_dir=iterations_dir,
        iteration_id="iter_0001",
        created_at="2026-01-01T00:00:00Z",
    )
    _write_iteration_summary(
        iterations_dir=iterations_dir,
        iteration_id="iter_0002",
        created_at="2026-01-02T00:00:00Z",
        saved_plan=True,
    )

    rendered = _build_iteration_listing_payload(
        root=root,
        workspace_id="demo",
        state=WorkspaceState(
            format_version="autoharness.workspace_state.v1",
            workspace_id="demo",
            status="active",
            active_track_id="main",
            last_iteration_id="iter_0002",
        ),
        spec=IterationQuerySpec(sort_by="created_at"),
    )

    assert rendered["workspace_id"] == "demo"
    assert rendered["last_iteration_id"] == "iter_0002"
    assert rendered["saved_plan_iterations_total"] == 1
    assert rendered["iterations_dir"] == str(iterations_dir)
    assert [item["iteration_id"] for item in rendered["iterations"]] == [
        "iter_0001",
        "iter_0002",
    ]
