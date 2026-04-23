"""Promotion, comparison, and champion export CLI handlers."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from .autonomy import policy_for_mode
from .cli_support import _preset_policy_key_for_stage, _resolve_workspace_track
from .editing import edit_plan_from_dict, start_edit_session
from .events import append_workspace_event
from .mutations import (
    _policy_or_override,
    _require_active_workspace_state,
    _resolve_promotion_policy,
    _resolve_track_benchmark_policy,
    _utc_now,
)
from .outputs import _emit_json_output, _write_json
from .stages import evaluate_stage_result, stage_policy_for
from .tracking import (
    create_benchmark_record,
    create_promotion_record,
    iteration_dir_path,
    load_benchmark_record,
    load_champion_manifest,
    load_workspace_state,
    persist_benchmark_record,
    persist_champion_manifest,
    persist_promotion_record,
    update_state_after_promotion,
)


def _copy_artifact(src: Path, dst: Path) -> None:
    if not src.exists():
        raise SystemExit(f"Artifact not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _prepare_export_dir(output_dir: Path, *, force: bool) -> None:
    if output_dir.exists():
        if not output_dir.is_dir():
            raise SystemExit(f"Export output is not a directory: {output_dir}")
        if any(output_dir.iterdir()) and not force:
            raise SystemExit(
                f"Refusing to write into non-empty directory: {output_dir}. Use --force."
            )
    output_dir.mkdir(parents=True, exist_ok=True)


def _record_path(*, root: Path, workspace_id: str, track_id: str, record_id: str) -> Path:
    return root / workspace_id / "tracks" / track_id / "registry" / f"{record_id}.json"


def _record_summary(*, record_path: Path, record) -> dict[str, object]:
    return {
        "record_id": record.record_id,
        "iteration_id": record.iteration_id,
        "adapter_id": record.adapter_id,
        "benchmark_name": record.benchmark_name,
        "stage": record.stage,
        "status": record.status,
        "success": record.success,
        "hypothesis": record.hypothesis,
        "notes": record.notes,
        "record_path": str(record_path),
    }


def _discover_workspace_ids(root: Path) -> list[str]:
    if not root.exists():
        return []
    workspace_ids: list[str] = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and (path / "workspace.json").exists():
            workspace_ids.append(path.name)
    return workspace_ids


def _export_champion_bundle(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    output_dir: Path,
    force: bool,
) -> dict[str, object]:
    try:
        manifest = load_champion_manifest(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    _prepare_export_dir(output_dir, force=force)

    source_champion_path = root / workspace_id / "tracks" / track_id / "champion.json"
    bundle_paths = {
        "source_champion_manifest_path": output_dir / "source_champion.json",
        "benchmark_record_path": output_dir / "benchmark_record.json",
        "promotion_path": output_dir / "promotion.json",
    }
    _copy_artifact(source_champion_path, bundle_paths["source_champion_manifest_path"])
    _copy_artifact(Path(manifest.record_path), bundle_paths["benchmark_record_path"])
    _copy_artifact(Path(manifest.promotion_path), bundle_paths["promotion_path"])

    diff_bundle_name: str | None = None
    if manifest.diff_path:
        diff_bundle_name = "candidate.patch"
        _copy_artifact(Path(manifest.diff_path), output_dir / diff_bundle_name)

    parsed_sources_bundle_name: str | None = None
    if manifest.parsed_artifact_sources_path:
        parsed_sources_bundle_name = "parsed_artifact_sources.json"
        _copy_artifact(
            Path(manifest.parsed_artifact_sources_path),
            output_dir / parsed_sources_bundle_name,
        )

    source_plan_artifact_path: Path | None = None
    source_plan_bundle_name: str | None = None
    if manifest.iteration_id is not None:
        candidate_source_plan_path = iteration_dir_path(
            root=root,
            workspace_id=workspace_id,
            iteration_id=manifest.iteration_id,
        ) / "source_plan.json"
        if candidate_source_plan_path.exists():
            source_plan_artifact_path = candidate_source_plan_path
            source_plan_bundle_name = "source_plan.json"
            _copy_artifact(candidate_source_plan_path, output_dir / source_plan_bundle_name)

    export_manifest = {
        "format_version": "autoharness.champion_export.v1",
        "exported_at": _utc_now(),
        "workspace_id": manifest.workspace_id,
        "track_id": manifest.track_id,
        "record_id": manifest.record_id,
        "promotion_id": manifest.promotion_id,
        "iteration_id": manifest.iteration_id,
        "adapter_id": manifest.adapter_id,
        "benchmark_name": manifest.benchmark_name,
        "stage": manifest.stage,
        "status": manifest.status,
        "success": manifest.success,
        "hypothesis": manifest.hypothesis,
        "notes": manifest.notes,
        "target_root": manifest.target_root,
        "parsed_artifact_sources": manifest.parsed_artifact_sources,
        "bundle_artifacts": {
            "source_champion_manifest_path": bundle_paths[
                "source_champion_manifest_path"
            ].name,
            "benchmark_record_path": bundle_paths["benchmark_record_path"].name,
            "promotion_path": bundle_paths["promotion_path"].name,
            "diff_path": diff_bundle_name,
            "parsed_artifact_sources_path": parsed_sources_bundle_name,
            "source_plan_artifact_path": source_plan_bundle_name,
        },
        "source_artifacts": {
            "source_champion_manifest_path": str(source_champion_path),
            "benchmark_record_path": manifest.record_path,
            "promotion_path": manifest.promotion_path,
            "diff_path": manifest.diff_path,
            "parsed_artifact_sources_path": manifest.parsed_artifact_sources_path,
            "source_plan_artifact_path": (
                str(source_plan_artifact_path)
                if source_plan_artifact_path is not None
                else None
            ),
        },
    }
    export_manifest_path = output_dir / "champion.json"
    _write_json(export_manifest_path, export_manifest)
    return export_manifest


def _build_stage_policy_for_track(
    *,
    workspace,
    track_id: str,
    stage: str,
    min_success_rate: float | None,
    max_regressed_tasks: int | None,
    max_regressed_task_fraction: float | None,
    max_regressed_task_weight: float | None,
    max_regressed_task_weight_fraction: float | None,
    task_regression_margin: float | None,
):
    resolved_min_success_rate = (
        min_success_rate
        if min_success_rate is not None
        else workspace.tracks[track_id].evaluator.min_judge_pass_rate
    )
    resolved_task_regression_margin = (
        task_regression_margin if task_regression_margin is not None else 0.0
    )
    try:
        return stage_policy_for(
            stage,
            min_judge_pass_rate=resolved_min_success_rate,
            max_regressed_tasks=max_regressed_tasks,
            max_regressed_task_fraction=max_regressed_task_fraction,
            max_regressed_task_weight=max_regressed_task_weight,
            max_regressed_task_weight_fraction=max_regressed_task_weight_fraction,
            task_regression_margin=resolved_task_regression_margin,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _compute_champion_comparison(
    *,
    root: Path,
    workspace_id: str,
    requested_track_id: str | None,
    record_id: str,
    stage: str | None,
    min_success_rate: float | None,
    min_improvement: float | None,
    max_regressed_tasks: int | None,
    max_regressed_task_fraction: float | None,
    max_regressed_task_weight: float | None,
    max_regressed_task_weight_fraction: float | None,
    task_regression_margin: float | None,
) -> dict[str, object]:
    workspace, _, track_id = _resolve_workspace_track(
        root=root,
        workspace_id=workspace_id,
        requested_track_id=requested_track_id,
    )
    promotion_policy, promotion_policy_source_path = _resolve_promotion_policy(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )

    try:
        champion_manifest = load_champion_manifest(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
        candidate_record = load_benchmark_record(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            record_id=record_id,
        )
        champion_record = load_benchmark_record(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            record_id=champion_manifest.record_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    comparison_stage = (
        stage
        or (promotion_policy.stage if promotion_policy is not None else None)
        or candidate_record.stage
        or champion_record.stage
        or champion_manifest.stage
        or "screening"
    )
    resolved_min_success_rate = _policy_or_override(
        min_success_rate,
        promotion_policy.min_success_rate if promotion_policy is not None else None,
        None,
    )
    resolved_min_improvement = _policy_or_override(
        min_improvement,
        promotion_policy.min_improvement if promotion_policy is not None else None,
        0.0,
    )
    resolved_max_regressed_tasks = _policy_or_override(
        max_regressed_tasks,
        promotion_policy.max_regressed_tasks if promotion_policy is not None else None,
        None,
    )
    resolved_max_regressed_task_fraction = _policy_or_override(
        max_regressed_task_fraction,
        promotion_policy.max_regressed_task_fraction if promotion_policy is not None else None,
        None,
    )
    resolved_max_regressed_task_weight = _policy_or_override(
        max_regressed_task_weight,
        promotion_policy.max_regressed_task_weight if promotion_policy is not None else None,
        None,
    )
    resolved_max_regressed_task_weight_fraction = _policy_or_override(
        max_regressed_task_weight_fraction,
        promotion_policy.max_regressed_task_weight_fraction
        if promotion_policy is not None
        else None,
        None,
    )
    resolved_task_regression_margin = _policy_or_override(
        task_regression_margin,
        promotion_policy.task_regression_margin if promotion_policy is not None else None,
        0.0,
    )
    stage_policy = _build_stage_policy_for_track(
        workspace=workspace,
        track_id=track_id,
        stage=comparison_stage,
        min_success_rate=resolved_min_success_rate,
        max_regressed_tasks=resolved_max_regressed_tasks,
        max_regressed_task_fraction=resolved_max_regressed_task_fraction,
        max_regressed_task_weight=resolved_max_regressed_task_weight,
        max_regressed_task_weight_fraction=resolved_max_regressed_task_weight_fraction,
        task_regression_margin=resolved_task_regression_margin,
    )
    track_policy, track_policy_source_path = _resolve_track_benchmark_policy(
        root=root,
        workspace=workspace,
        workspace_id=workspace_id,
        track_id=track_id,
    )

    benchmark_target = getattr(track_policy, stage_policy.benchmark_policy_key)
    policy_preset = getattr(track_policy, _preset_policy_key_for_stage(stage_policy))
    stage_evaluation = evaluate_stage_result(
        payload=candidate_record.payload,
        stage_policy=stage_policy,
        benchmark_target=str(benchmark_target) if benchmark_target is not None else None,
        applied_stage_override=False,
        baseline_payload=champion_record.payload,
        baseline_label=champion_record.record_id,
        baseline_stage=champion_record.stage,
        min_improvement=resolved_min_improvement,
    )
    if policy_preset is not None:
        stage_evaluation["benchmark_preset_target"] = policy_preset

    candidate_record_path = _record_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        record_id=candidate_record.record_id,
    )
    champion_record_path = _record_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        record_id=champion_record.record_id,
    )
    rendered = {
        "workspace_id": workspace_id,
        "track_id": track_id,
        "comparison_stage": comparison_stage,
        "track_policy_source_path": track_policy_source_path,
        "track_policy": track_policy.to_dict(),
        "benchmark_preset_target": policy_preset,
        "promotion_policy_source_path": promotion_policy_source_path,
        "promotion_policy": (
            promotion_policy.to_dict() if promotion_policy is not None else None
        ),
        "benchmark_match": candidate_record.benchmark_name == champion_record.benchmark_name,
        "stage_match": candidate_record.stage == champion_record.stage,
        "candidate_is_current_champion": candidate_record.record_id == champion_record.record_id,
        "stage_policy": stage_policy.to_dict(),
        "candidate": _record_summary(
            record_path=candidate_record_path,
            record=candidate_record,
        ),
        "champion": {
            **_record_summary(
                record_path=champion_record_path,
                record=champion_record,
            ),
            "promotion_id": champion_manifest.promotion_id,
            "promotion_path": champion_manifest.promotion_path,
            "diff_path": champion_manifest.diff_path,
            "parsed_artifact_sources_path": champion_manifest.parsed_artifact_sources_path,
        },
        "recorded_stage_evaluation": (
            candidate_record.payload.get("stage_evaluation")
            if isinstance(candidate_record.payload.get("stage_evaluation"), dict)
            else None
        ),
        "stage_evaluation": stage_evaluation,
    }
    return {
        "workspace": workspace,
        "track_id": track_id,
        "candidate_record": candidate_record,
        "champion_record": champion_record,
        "champion_manifest": champion_manifest,
        "rendered": rendered,
    }


def _promote_record(
    *,
    root: Path,
    workspace_id: str,
    state,
    track_id: str,
    record,
    target_root: Path,
    notes: str,
) -> dict[str, object]:
    edit_application = record.payload.get("edit_application")
    if not isinstance(edit_application, dict):
        raise SystemExit(
            f"Record `{record.record_id}` does not contain an edit application payload."
        )

    try:
        edit_plan = edit_plan_from_dict(
            {
                "format_version": "autoharness.edit_plan.v1",
                "summary": edit_application.get("summary", ""),
                "operations": edit_application.get("operations", []),
            }
        )
        edit_session = start_edit_session(
            plan=edit_plan,
            target_root=target_root,
            policy=policy_for_mode("full"),
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    diff_text = edit_session.render_unified_diff()
    edit_restore = edit_session.finalize(keep_applied=True).to_dict()
    promotion = create_promotion_record(
        workspace_id=workspace_id,
        track_id=track_id,
        record=record,
        target_root=target_root,
        notes=notes,
        edit_restore=edit_restore,
    )
    artifacts = persist_promotion_record(
        root=root,
        promotion=promotion,
        diff_text=diff_text,
    )
    champion_manifest_path = persist_champion_manifest(
        root=root,
        record=record,
        promotion=promotion,
        promotion_artifacts=artifacts,
    )
    artifacts["champion_manifest_path"] = str(champion_manifest_path)
    next_state = update_state_after_promotion(
        root=root,
        workspace_id=workspace_id,
        state=state,
        record_id=record.record_id,
    )
    append_workspace_event(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        record_id=record.record_id,
        promotion_id=promotion.promotion_id,
        status="completed",
        event_type="record_promoted",
        adapter_id=record.adapter_id,
        benchmark_name=record.benchmark_name,
        details={
            "stage": record.stage,
            "target_root": str(target_root),
        },
    )
    return {
        "promotion": promotion.to_dict(),
        "artifacts": artifacts,
        "current_champion_experiment_id": next_state.current_champion_experiment_id,
    }


def _clone_record_for_champion_transfer(
    *,
    source_record,
    source_workspace_id: str,
    source_track_id: str,
    source_promotion_id: str,
    source_champion_manifest_path: Path,
    destination_workspace_id: str,
    destination_track_id: str,
):
    payload = dict(source_record.payload)
    transfer_source = {
        "workspace_id": source_workspace_id,
        "track_id": source_track_id,
        "record_id": source_record.record_id,
        "promotion_id": source_promotion_id,
        "champion_manifest_path": str(source_champion_manifest_path),
    }
    existing_transfer_source = payload.get("transfer_source")
    if isinstance(existing_transfer_source, dict):
        transfer_source["previous_transfer_source"] = dict(existing_transfer_source)
    payload["transfer_source"] = transfer_source
    return create_benchmark_record(
        adapter_id=source_record.adapter_id,
        benchmark_name=source_record.benchmark_name,
        config=source_record.config,
        payload=payload,
        dry_run=source_record.dry_run,
        workspace_id=destination_workspace_id,
        track_id=destination_track_id,
        iteration_id=None,
        hypothesis=source_record.hypothesis,
        notes=source_record.notes,
        config_path=source_record.config_path,
        source_plan_path=None,
        source_proposal_id=None,
        source_proposal_path=None,
        stage=source_record.stage,
    )


def _transfer_champion_to_destination(
    *,
    root: Path,
    source_workspace_id: str,
    source_track_id: str | None,
    destination_workspace_id: str,
    destination_track_id: str | None,
    target_root: Path,
    notes: str,
) -> dict[str, object]:
    _, _, resolved_source_track_id = _resolve_workspace_track(
        root=root,
        workspace_id=source_workspace_id,
        requested_track_id=source_track_id,
    )
    _, destination_state, resolved_destination_track_id = _resolve_workspace_track(
        root=root,
        workspace_id=destination_workspace_id,
        requested_track_id=destination_track_id,
    )
    _require_active_workspace_state(
        workspace_id=destination_workspace_id,
        state=destination_state,
    )
    if (
        source_workspace_id == destination_workspace_id
        and resolved_source_track_id == resolved_destination_track_id
    ):
        raise SystemExit("Source and destination workspace track must differ.")

    source_champion_manifest_path = (
        root / source_workspace_id / "tracks" / resolved_source_track_id / "champion.json"
    )
    try:
        source_manifest = load_champion_manifest(
            root=root,
            workspace_id=source_workspace_id,
            track_id=resolved_source_track_id,
        )
        source_record = load_benchmark_record(
            root=root,
            workspace_id=source_workspace_id,
            track_id=resolved_source_track_id,
            record_id=source_manifest.record_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    destination_record = _clone_record_for_champion_transfer(
        source_record=source_record,
        source_workspace_id=source_workspace_id,
        source_track_id=resolved_source_track_id,
        source_promotion_id=source_manifest.promotion_id,
        source_champion_manifest_path=source_champion_manifest_path,
        destination_workspace_id=destination_workspace_id,
        destination_track_id=resolved_destination_track_id,
    )
    destination_record_path = persist_benchmark_record(
        root=root,
        record=destination_record,
    )
    transfer_notes = (
        notes.strip()
        if notes.strip()
        else (
            "Transferred champion from "
            f"{source_workspace_id}/{resolved_source_track_id} "
            f"record {source_record.record_id}"
        )
    )
    promotion_rendered = _promote_record(
        root=root,
        workspace_id=destination_workspace_id,
        state=destination_state,
        track_id=resolved_destination_track_id,
        record=destination_record,
        target_root=target_root,
        notes=transfer_notes,
    )
    refreshed_destination_state = load_workspace_state(root, destination_workspace_id)
    append_workspace_event(
        root=root,
        workspace_id=destination_workspace_id,
        track_id=resolved_destination_track_id,
        record_id=destination_record.record_id,
        promotion_id=str(promotion_rendered["promotion"]["promotion_id"]),
        status="completed",
        event_type="champion_transferred",
        adapter_id=destination_record.adapter_id,
        benchmark_name=destination_record.benchmark_name,
        details={
            "source_workspace_id": source_workspace_id,
            "source_track_id": resolved_source_track_id,
            "source_record_id": source_record.record_id,
            "source_promotion_id": source_manifest.promotion_id,
            "target_root": str(target_root),
        },
    )
    return {
        "format_version": "autoharness.champion_transfer.v1",
        "transferred_at": _utc_now(),
        "source": {
            "workspace_id": source_workspace_id,
            "track_id": resolved_source_track_id,
            "record_id": source_record.record_id,
            "promotion_id": source_manifest.promotion_id,
            "champion_manifest_path": str(source_champion_manifest_path),
            "target_root": source_manifest.target_root,
        },
        "destination": {
            "workspace_id": destination_workspace_id,
            "track_id": resolved_destination_track_id,
            "target_root": str(target_root),
            "record_id": destination_record.record_id,
            "record_path": str(destination_record_path),
            "current_champion_experiment_id": (
                refreshed_destination_state.current_champion_experiment_id
            ),
        },
        "promotion": promotion_rendered["promotion"],
        "artifacts": promotion_rendered["artifacts"],
    }


def _handle_promote(args: argparse.Namespace) -> int:
    _, state, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    _require_active_workspace_state(workspace_id=args.workspace_id, state=state)

    try:
        record = load_benchmark_record(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
            record_id=args.record_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    rendered = _promote_record(
        root=args.root,
        workspace_id=args.workspace_id,
        state=state,
        track_id=track_id,
        record=record,
        target_root=args.target_root,
        notes=args.notes,
    )
    if args.output is not None:
        _write_json(args.output, rendered)
        print(f"Wrote output to {args.output}")

    artifacts = rendered["artifacts"]
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Promoted record: {record.record_id}")
    print(f"Target root: {args.target_root}")
    if "diff_path" in artifacts:
        print(f"Patch path: {artifacts['diff_path']}")
    if "parsed_artifact_sources_path" in artifacts:
        print(f"Parsed artifact sources: {artifacts['parsed_artifact_sources_path']}")
    print(f"Promotion path: {artifacts['promotion_path']}")
    print(f"Champion manifest: {artifacts['champion_manifest_path']}")
    print(f"Current champion: {rendered['current_champion_experiment_id']}")
    return 0


def _handle_export_champion(args: argparse.Namespace) -> int:
    _, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    export_manifest = _export_champion_bundle(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        output_dir=args.output,
        force=args.force,
    )
    export_manifest_path = args.output / "champion.json"

    print(f"Workspace: {export_manifest['workspace_id']}")
    print(f"Track: {export_manifest['track_id']}")
    print(f"Champion record: {export_manifest['record_id']}")
    print(f"Promotion: {export_manifest['promotion_id']}")
    print(f"Export path: {args.output}")
    print(f"Bundle manifest: {export_manifest_path}")
    return 0


def _handle_transfer_champion(args: argparse.Namespace) -> int:
    rendered = _transfer_champion_to_destination(
        root=args.root,
        source_workspace_id=args.source_workspace_id,
        source_track_id=args.source_track_id,
        destination_workspace_id=args.workspace_id,
        destination_track_id=args.track_id,
        target_root=args.target_root,
        notes=args.notes,
    )
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(
        f"Source champion: {rendered['source']['workspace_id']}/"
        f"{rendered['source']['track_id']} {rendered['source']['record_id']}"
    )
    print(
        f"Destination champion: {rendered['destination']['workspace_id']}/"
        f"{rendered['destination']['track_id']} {rendered['destination']['record_id']}"
    )
    print(f"Target root: {args.target_root}")
    print(f"Promotion path: {rendered['artifacts']['promotion_path']}")
    print(
        "Champion manifest: "
        f"{rendered['artifacts']['champion_manifest_path']}"
    )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_transfer_root_champions(args: argparse.Namespace) -> int:
    selected_workspace_ids = (
        list(args.workspace_id)
        if args.workspace_id
        else _discover_workspace_ids(args.root)
    )
    selected_workspace_ids = [
        workspace_id
        for workspace_id in selected_workspace_ids
        if workspace_id != args.source_workspace_id
    ]
    transfers: list[dict[str, object]] = []
    status = "completed"
    stop_reason = "completed"
    for workspace_id in selected_workspace_ids:
        try:
            rendered = _transfer_champion_to_destination(
                root=args.root,
                source_workspace_id=args.source_workspace_id,
                source_track_id=args.source_track_id,
                destination_workspace_id=workspace_id,
                destination_track_id=args.destination_track_id,
                target_root=args.target_root_base / workspace_id,
                notes=args.notes,
            )
            transfers.append(
                {
                    "workspace_id": workspace_id,
                    "status": "completed",
                    "rendered": rendered,
                }
            )
        except SystemExit as exc:
            transfers.append(
                {
                    "workspace_id": workspace_id,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            if not args.continue_on_failure:
                status = "failed"
                stop_reason = "transfer_failed"
                break
            status = "partial"
            stop_reason = "transfer_failed"
    rendered = {
        "format_version": "autoharness.root_champion_transfer.v1",
        "transferred_at": _utc_now(),
        "source_workspace_id": args.source_workspace_id,
        "source_track_id": args.source_track_id,
        "workspace_total": len(selected_workspace_ids),
        "completed_workspace_total": len(transfers),
        "success_workspace_total": sum(
            1 for item in transfers if item["status"] == "completed"
        ),
        "failed_workspace_total": sum(
            1 for item in transfers if item["status"] == "failed"
        ),
        "status": status,
        "stop_reason": stop_reason,
        "target_root_base": str(args.target_root_base.resolve()),
        "transfers": transfers,
    }
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0
    print(f"Root champion transfers: {len(transfers)}/{len(selected_workspace_ids)}")
    print(f"Status: {status}")
    print(f"Stop reason: {stop_reason}")
    for item in transfers:
        if item["status"] == "completed":
            transfer = item["rendered"]
            assert isinstance(transfer, dict)
            print(
                f"- {item['workspace_id']}: completed "
                f"{transfer['destination']['record_id']}"
            )
        else:
            print(f"- {item['workspace_id']}: failed {item['error']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_compare_to_champion(args: argparse.Namespace) -> int:
    comparison = _compute_champion_comparison(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
        record_id=args.record_id,
        stage=args.stage,
        min_success_rate=args.min_success_rate,
        min_improvement=args.min_improvement,
        max_regressed_tasks=args.max_regressed_tasks,
        max_regressed_task_fraction=args.max_regressed_task_fraction,
        max_regressed_task_weight=args.max_regressed_task_weight,
        max_regressed_task_weight_fraction=args.max_regressed_task_weight_fraction,
        task_regression_margin=args.task_regression_margin,
    )
    track_id = comparison["track_id"]
    rendered = comparison["rendered"]
    stage_evaluation = rendered["stage_evaluation"]
    baseline_comparison = stage_evaluation.get("baseline_comparison")

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Candidate record: {rendered['candidate']['record_id']}")
    print(f"Champion record: {rendered['champion']['record_id']}")
    print(f"Comparison stage: {rendered['comparison_stage']}")
    print(f"Benchmark match: {rendered['benchmark_match']}")
    print(f"Stage match: {rendered['stage_match']}")
    print(f"Stage decision: {stage_evaluation.get('decision')}")
    if isinstance(baseline_comparison, dict):
        print(f"Champion comparison: {baseline_comparison.get('decision')}")
        print(f"Comparison mode: {baseline_comparison.get('comparison_mode', 'interval')}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_promote_from_compare(args: argparse.Namespace) -> int:
    _, state, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    _require_active_workspace_state(workspace_id=args.workspace_id, state=state)

    comparison = _compute_champion_comparison(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=track_id,
        record_id=args.record_id,
        stage=args.stage,
        min_success_rate=args.min_success_rate,
        min_improvement=args.min_improvement,
        max_regressed_tasks=args.max_regressed_tasks,
        max_regressed_task_fraction=args.max_regressed_task_fraction,
        max_regressed_task_weight=args.max_regressed_task_weight,
        max_regressed_task_weight_fraction=args.max_regressed_task_weight_fraction,
        task_regression_margin=args.task_regression_margin,
    )
    rendered_comparison = comparison["rendered"]
    candidate_record = comparison["candidate_record"]
    champion_record = comparison["champion_record"]
    stage_evaluation = rendered_comparison["stage_evaluation"]
    baseline_comparison = stage_evaluation.get("baseline_comparison")

    if rendered_comparison["candidate_is_current_champion"]:
        raise SystemExit(f"Record `{args.record_id}` is already the current champion.")
    if stage_evaluation.get("passed") is not True:
        raise SystemExit(
            "Candidate did not pass the comparison stage gate: "
            f"{stage_evaluation.get('decision')}."
        )
    if not isinstance(baseline_comparison, dict) or baseline_comparison.get("passed") is not True:
        raise SystemExit(
            "Candidate did not beat the current champion: "
            f"{baseline_comparison.get('decision') if isinstance(baseline_comparison, dict) else 'unavailable'}."
        )

    promotion_rendered = _promote_record(
        root=args.root,
        workspace_id=args.workspace_id,
        state=state,
        track_id=track_id,
        record=candidate_record,
        target_root=args.target_root,
        notes=args.notes,
    )
    rendered = {
        "comparison": rendered_comparison,
        "promotion": promotion_rendered["promotion"],
        "artifacts": promotion_rendered["artifacts"],
        "previous_champion_record_id": champion_record.record_id,
        "current_champion_experiment_id": promotion_rendered["current_champion_experiment_id"],
    }
    if args.output is not None:
        _write_json(args.output, rendered)
        print(f"Wrote output to {args.output}")

    artifacts = promotion_rendered["artifacts"]
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Candidate record: {candidate_record.record_id}")
    print(f"Previous champion: {champion_record.record_id}")
    print(f"Comparison stage: {rendered_comparison['comparison_stage']}")
    print(f"Stage decision: {stage_evaluation.get('decision')}")
    print(f"Champion comparison: {baseline_comparison.get('decision')}")
    print(f"Promoted record: {candidate_record.record_id}")
    print(f"Target root: {args.target_root}")
    if "diff_path" in artifacts:
        print(f"Patch path: {artifacts['diff_path']}")
    if "parsed_artifact_sources_path" in artifacts:
        print(f"Parsed artifact sources: {artifacts['parsed_artifact_sources_path']}")
    print(f"Promotion path: {artifacts['promotion_path']}")
    print(f"Champion manifest: {artifacts['champion_manifest_path']}")
    print(f"Current champion: {promotion_rendered['current_champion_experiment_id']}")
    return 0
