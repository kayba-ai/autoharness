"""Detail-view CLI handlers for champions, iterations, records, and promotions."""

from __future__ import annotations

import argparse

from .cli_support import _load_structured_file, _resolve_workspace_track
from .outputs import _emit_json_output
from .tracking import (
    iteration_dir_path,
    load_benchmark_record,
    load_champion_manifest,
    load_iteration_linked_records,
    load_iteration_summary,
    load_promotion_record,
    promotions_dir_path,
    registry_dir_path,
)


def _handle_show_champion(args: argparse.Namespace) -> int:
    _, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )

    try:
        manifest = load_champion_manifest(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    rendered = manifest.to_dict()
    source_plan_artifact_path = None
    source_plan = None
    if manifest.iteration_id is not None:
        candidate_source_plan_path = (
            iteration_dir_path(
                root=args.root,
                workspace_id=args.workspace_id,
                iteration_id=manifest.iteration_id,
            )
            / "source_plan.json"
        )
        if candidate_source_plan_path.exists():
            source_plan_artifact_path = candidate_source_plan_path
            source_plan = _load_structured_file(candidate_source_plan_path)
    rendered["source_plan_artifact_path"] = (
        str(source_plan_artifact_path) if source_plan_artifact_path is not None else None
    )
    if source_plan is not None:
        rendered["source_plan"] = source_plan
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {manifest.workspace_id}")
    print(f"Track: {manifest.track_id}")
    print(f"Champion record: {manifest.record_id}")
    print(f"Promotion: {manifest.promotion_id}")
    print(f"Adapter: {manifest.adapter_id}")
    print(f"Benchmark: {manifest.benchmark_name}")
    print(f"Stage: {manifest.stage or '(none)'}")
    print(f"Status: {manifest.status}")
    print(f"Success: {manifest.success}")
    print(f"Hypothesis: {manifest.hypothesis or '(none)'}")
    print(f"Target root: {manifest.target_root}")
    print(f"Record path: {manifest.record_path}")
    print(f"Promotion path: {manifest.promotion_path}")
    if source_plan_artifact_path is not None:
        print(f"Source plan artifact: {source_plan_artifact_path}")
    if manifest.diff_path:
        print(f"Patch path: {manifest.diff_path}")
    if manifest.parsed_artifact_sources_path:
        print(f"Parsed artifact sources: {manifest.parsed_artifact_sources_path}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_iteration(args: argparse.Namespace) -> int:
    try:
        summary = load_iteration_summary(
            root=args.root,
            workspace_id=args.workspace_id,
            iteration_id=args.iteration_id,
        )
        linked_records = load_iteration_linked_records(
            root=args.root,
            workspace_id=args.workspace_id,
            iteration_id=args.iteration_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    iteration_dir = iteration_dir_path(
        root=args.root,
        workspace_id=args.workspace_id,
        iteration_id=args.iteration_id,
    )
    source_plan_artifact_path = iteration_dir / "source_plan.json"
    rendered = {
        "summary": summary,
        "linked_records": linked_records,
        "artifacts": {
            "iteration_dir": str(iteration_dir),
            "summary_path": str(iteration_dir / "summary.json"),
            "hypothesis_path": str(iteration_dir / "hypothesis.md"),
            "linked_records_path": str(iteration_dir / "linked_records.json"),
            "source_plan_artifact_path": (
                str(source_plan_artifact_path)
                if source_plan_artifact_path.exists()
                else None
            ),
            "edit_application_path": (
                str(iteration_dir / "edit_application.json")
                if (iteration_dir / "edit_application.json").exists()
                else None
            ),
            "edit_restore_path": (
                str(iteration_dir / "edit_restore.json")
                if (iteration_dir / "edit_restore.json").exists()
                else None
            ),
            "staging_path": (
                str(iteration_dir / "staging.json")
                if (iteration_dir / "staging.json").exists()
                else None
            ),
            "parsed_artifact_sources_path": (
                str(iteration_dir / "parsed_artifact_sources.json")
                if (iteration_dir / "parsed_artifact_sources.json").exists()
                else None
            ),
            "edit_diff_path": (
                str(iteration_dir / "candidate.patch")
                if (iteration_dir / "candidate.patch").exists()
                else None
            ),
        },
    }
    if source_plan_artifact_path.exists():
        rendered["source_plan"] = _load_structured_file(source_plan_artifact_path)

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Iteration: {args.iteration_id}")
    print(f"Track: {summary.get('track_id')}")
    print(f"Record: {summary.get('record_id')}")
    print(f"Adapter: {summary.get('adapter_id')}")
    print(f"Benchmark: {summary.get('benchmark_name')}")
    print(f"Stage: {summary.get('stage') or 'unscoped'}")
    print(f"Status: {summary.get('status')}")
    if isinstance(summary.get("source_plan_path"), str):
        print(f"Source plan: {summary['source_plan_path']}")
    if source_plan_artifact_path.exists():
        print(f"Source plan artifact: {source_plan_artifact_path}")
    print(f"Summary path: {iteration_dir / 'summary.json'}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_record(args: argparse.Namespace) -> int:
    _, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    try:
        record = load_benchmark_record(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
            record_id=args.record_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    record_path = registry_dir_path(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    ) / f"{record.record_id}.json"
    source_plan_artifact_path = None
    source_plan = None
    if record.iteration_id is not None:
        candidate_source_plan_path = (
            iteration_dir_path(
                root=args.root,
                workspace_id=args.workspace_id,
                iteration_id=record.iteration_id,
            )
            / "source_plan.json"
        )
        if candidate_source_plan_path.exists():
            source_plan_artifact_path = candidate_source_plan_path
            source_plan = _load_structured_file(candidate_source_plan_path)
    rendered = record.to_dict()
    rendered["record_path"] = str(record_path)
    rendered["source_plan_artifact_path"] = (
        str(source_plan_artifact_path) if source_plan_artifact_path is not None else None
    )
    if source_plan is not None:
        rendered["source_plan"] = source_plan

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Record: {record.record_id}")
    print(f"Path: {record_path}")
    print(f"Adapter: {record.adapter_id}")
    print(f"Benchmark: {record.benchmark_name}")
    print(f"Stage: {record.stage or 'unscoped'}")
    print(f"Status: {record.status}")
    print(f"Success: {record.success}")
    if record.iteration_id is not None:
        print(f"Iteration: {record.iteration_id}")
    if record.source_plan_path is not None:
        print(f"Source plan: {record.source_plan_path}")
    if source_plan_artifact_path is not None:
        print(f"Source plan artifact: {source_plan_artifact_path}")
    if record.hypothesis:
        print(f"Hypothesis: {record.hypothesis}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_promotion(args: argparse.Namespace) -> int:
    _, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    try:
        promotion = load_promotion_record(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
            promotion_id=args.promotion_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    promotions_dir = promotions_dir_path(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    promotion_path = promotions_dir / f"{promotion.promotion_id}.json"
    parsed_artifact_sources_path = (
        promotions_dir / f"{promotion.promotion_id}.parsed_artifact_sources.json"
    )
    diff_path = promotions_dir / f"{promotion.promotion_id}.patch"
    rendered = promotion.to_dict()
    rendered["promotion_path"] = str(promotion_path)
    if parsed_artifact_sources_path.exists():
        rendered["parsed_artifact_sources_path"] = str(parsed_artifact_sources_path)
    if diff_path.exists():
        rendered["diff_path"] = str(diff_path)

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Promotion: {promotion.promotion_id}")
    print(f"Path: {promotion_path}")
    print(f"Record: {promotion.record_id}")
    print(f"Target root: {promotion.target_root}")
    if promotion.iteration_id is not None:
        print(f"Iteration: {promotion.iteration_id}")
    if diff_path.exists():
        print(f"Patch: {diff_path}")
    if parsed_artifact_sources_path.exists():
        print(f"Parsed artifact sources: {parsed_artifact_sources_path}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0
