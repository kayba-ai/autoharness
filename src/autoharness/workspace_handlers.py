"""Workspace, track, and settings CLI handlers."""

from __future__ import annotations

import argparse
import shutil
from dataclasses import replace
from pathlib import Path

import yaml

from .autonomy import policy_for_mode
from .campaigns import (
    CampaignEvaluatorPolicy,
    PromotionPolicy,
    TrackBenchmarkPolicy,
    TrackConfig,
)
from .cli_support import _resolve_workspace_track
from .mutations import (
    _apply_track_evaluator_overrides,
    _resolve_campaign_policy_updates,
    _default_promotion_policy,
    _persist_track_bootstrap_artifacts,
    _refresh_workspace_state_track_counts,
    _require_active_workspace_state,
    _resolve_notes_update,
    _resolve_promotion_policy,
    _resolve_routing_policy_updates,
    _resolve_track_benchmark_policy,
    _resolve_update_field,
    _utc_now,
    _validate_promotion_policy,
    _validate_track_benchmark_policy,
    _validate_track_config,
    _validate_workspace_config,
    _workspace_track_count_summary,
)
from .outputs import _emit_json_output, _write_json, _write_yaml
from .provider_profiles import (
    load_provider_profiles,
    persist_provider_profiles,
    provider_profiles_path,
    summarize_provider_profile,
    summarize_provider_profiles,
)
from .queries import IterationQuerySpec, query_workspace_iteration_items
from .retention import (
    load_retention_policy,
    persist_retention_policy,
    prune_workspace_artifacts,
    retention_policy_path,
)
from .tracking import (
    load_champion_manifest,
    list_track_benchmark_records,
    list_track_promotion_records,
    list_workspace_iterations,
    load_workspace,
    load_workspace_state,
    persist_promotion_policy,
    persist_track_config,
    persist_track_policy,
    persist_workspace_track,
    promotion_policy_path,
    save_workspace,
    save_workspace_state,
    track_config_path,
    track_dir_path,
    track_policy_path,
    workspace_config_path,
)
from .workspace import WorkspaceConfig, WorkspaceState


def _rebuild_workspace_state_from_artifacts(
    *,
    root: Path,
    workspace: WorkspaceConfig,
    state: WorkspaceState,
) -> WorkspaceState:
    summary = dict(
        WorkspaceState(
            format_version=state.format_version,
            workspace_id=state.workspace_id,
            status=state.status,
            active_track_id=workspace.active_track_id,
        ).summary
    )
    summary.update(_workspace_track_count_summary(workspace))

    latest_record = None
    latest_champion = None
    active_track_champion = None
    promotions_total = 0

    for track_id in sorted(workspace.tracks):
        records = list_track_benchmark_records(
            root=root,
            workspace_id=workspace.workspace_id,
            track_id=track_id,
        )
        promotions = list_track_promotion_records(
            root=root,
            workspace_id=workspace.workspace_id,
            track_id=track_id,
        )
        promotions_total += len(promotions)

        try:
            champion = load_champion_manifest(
                root=root,
                workspace_id=workspace.workspace_id,
                track_id=track_id,
            )
        except FileNotFoundError:
            champion = None
        if champion is not None:
            if track_id == workspace.active_track_id:
                active_track_champion = champion
            if latest_champion is None or (
                champion.updated_at,
                champion.promotion_id,
            ) > (
                latest_champion.updated_at,
                latest_champion.promotion_id,
            ):
                latest_champion = champion

        for record in records:
            if latest_record is None or (
                record.created_at,
                record.record_id,
            ) > (
                latest_record.created_at,
                latest_record.record_id,
            ):
                latest_record = record

            if record.dry_run:
                summary["proposal_only_candidates"] = int(
                    summary.get("proposal_only_candidates", 0)
                ) + 1
            elif record.success:
                summary["validated_candidates"] = int(
                    summary.get("validated_candidates", 0)
                ) + 1
            else:
                if record.status == "inconclusive":
                    summary["inconclusive_candidates"] = int(
                        summary.get("inconclusive_candidates", 0)
                    ) + 1
                else:
                    summary["rejected_candidates"] = int(
                        summary.get("rejected_candidates", 0)
                    ) + 1

            validation_run_count = record.payload.get("validation_run_count")
            if isinstance(validation_run_count, int) and validation_run_count > 0:
                summary["validation_runs_total"] = int(
                    summary.get("validation_runs_total", 0)
                ) + validation_run_count

            if record.stage:
                summary[f"{record.stage}_iterations_total"] = int(
                    summary.get(f"{record.stage}_iterations_total", 0)
                ) + 1
                if record.dry_run:
                    summary[f"{record.stage}_planned_total"] = int(
                        summary.get(f"{record.stage}_planned_total", 0)
                    ) + 1
                elif record.success:
                    summary[f"{record.stage}_passes_total"] = int(
                        summary.get(f"{record.stage}_passes_total", 0)
                    ) + 1
                else:
                    if record.status == "inconclusive":
                        summary[f"{record.stage}_inconclusive_total"] = int(
                            summary.get(f"{record.stage}_inconclusive_total", 0)
                        ) + 1
                    else:
                        summary[f"{record.stage}_failures_total"] = int(
                            summary.get(f"{record.stage}_failures_total", 0)
                        ) + 1

    iterations, _ = query_workspace_iteration_items(
        root=root,
        workspace_id=workspace.workspace_id,
        last_iteration_id=state.last_iteration_id,
        spec=IterationQuerySpec(),
    )
    summary["iterations_total"] = len(iterations)
    summary["promotions_total"] = promotions_total
    latest_iteration = max(
        iterations,
        key=lambda item: (
            str(item.get("created_at", "")),
            str(item.get("iteration_id", "")),
        ),
        default=None,
    )

    champion_record_id = None
    if active_track_champion is not None:
        champion_record_id = active_track_champion.record_id
    elif latest_champion is not None:
        champion_record_id = latest_champion.record_id

    return WorkspaceState(
        format_version=state.format_version,
        workspace_id=state.workspace_id,
        status=state.status,
        active_track_id=workspace.active_track_id,
        next_iteration_index=state.next_iteration_index,
        last_iteration_id=(
            str(latest_iteration.get("iteration_id"))
            if isinstance(latest_iteration, dict)
            and latest_iteration.get("iteration_id") is not None
            else None
        ),
        last_experiment_id=(latest_record.record_id if latest_record is not None else None),
        current_champion_experiment_id=champion_record_id,
        summary=summary,
    )


def _handle_setup(args: argparse.Namespace) -> int:
    output: Path = args.output
    if output.exists() and not args.force:
        raise SystemExit(
            f"Refusing to overwrite existing settings file: {output}. Use --force."
        )

    policy = policy_for_mode(
        args.autonomy,
        editable_surfaces=tuple(args.editable_surface),
        protected_surfaces=tuple(args.protected_surface),
    )

    payload = {
        "format_version": "autoharness.settings.v1",
        "created_at": _utc_now(),
        "autonomy": policy.to_dict(),
    }
    _write_yaml(output, payload)
    print(f"Wrote settings to {output}")
    print(f"Autonomy mode: {policy.mode} ({policy.label})")
    return 0


def _load_settings(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(
            f"Settings file not found: {path}. Run `autoharness setup` first."
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "autonomy" not in data:
        raise SystemExit(f"Invalid settings file: {path}")
    return data


def _handle_set_promotion_policy(args: argparse.Namespace) -> int:
    _, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    policy_path = promotion_policy_path(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    current_policy, _ = _resolve_promotion_policy(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    policy = current_policy or _default_promotion_policy(track_id=track_id)

    stage_value = policy.stage
    changed_fields: list[str] = []
    if args.stage is not None:
        stage_value = None if args.stage == "none" else args.stage
        changed_fields.append("stage")

    min_success_rate, changed = _resolve_update_field(
        option_name="min-success-rate",
        current_value=policy.min_success_rate,
        value=args.min_success_rate,
        clear=args.clear_min_success_rate,
    )
    if changed:
        changed_fields.append("min_success_rate")
    min_improvement, changed = _resolve_update_field(
        option_name="min-improvement",
        current_value=policy.min_improvement,
        value=args.min_improvement,
        clear=args.clear_min_improvement,
    )
    if changed:
        changed_fields.append("min_improvement")
    max_regressed_tasks, changed = _resolve_update_field(
        option_name="max-regressed-tasks",
        current_value=policy.max_regressed_tasks,
        value=args.max_regressed_tasks,
        clear=args.clear_max_regressed_tasks,
    )
    if changed:
        changed_fields.append("max_regressed_tasks")
    max_regressed_task_fraction, changed = _resolve_update_field(
        option_name="max-regressed-task-fraction",
        current_value=policy.max_regressed_task_fraction,
        value=args.max_regressed_task_fraction,
        clear=args.clear_max_regressed_task_fraction,
    )
    if changed:
        changed_fields.append("max_regressed_task_fraction")
    max_regressed_task_weight, changed = _resolve_update_field(
        option_name="max-regressed-task-weight",
        current_value=policy.max_regressed_task_weight,
        value=args.max_regressed_task_weight,
        clear=args.clear_max_regressed_task_weight,
    )
    if changed:
        changed_fields.append("max_regressed_task_weight")
    max_regressed_task_weight_fraction, changed = _resolve_update_field(
        option_name="max-regressed-task-weight-fraction",
        current_value=policy.max_regressed_task_weight_fraction,
        value=args.max_regressed_task_weight_fraction,
        clear=args.clear_max_regressed_task_weight_fraction,
    )
    if changed:
        changed_fields.append("max_regressed_task_weight_fraction")
    task_regression_margin, changed = _resolve_update_field(
        option_name="task-regression-margin",
        current_value=policy.task_regression_margin,
        value=args.task_regression_margin,
        clear=args.clear_task_regression_margin,
    )
    if changed:
        changed_fields.append("task_regression_margin")
    notes, changed = _resolve_notes_update(
        current_value=policy.notes,
        value=args.notes,
        clear=args.clear_notes,
    )
    if changed:
        changed_fields.append("notes")

    if not changed_fields:
        raise SystemExit("No promotion policy updates were provided.")

    updated_policy = PromotionPolicy(
        format_version=policy.format_version,
        created_at=policy.created_at,
        track_id=track_id,
        stage=stage_value,
        min_success_rate=min_success_rate,
        min_improvement=min_improvement,
        max_regressed_tasks=max_regressed_tasks,
        max_regressed_task_fraction=max_regressed_task_fraction,
        max_regressed_task_weight=max_regressed_task_weight,
        max_regressed_task_weight_fraction=max_regressed_task_weight_fraction,
        task_regression_margin=task_regression_margin,
        notes=notes,
    )
    _validate_promotion_policy(updated_policy)
    persist_promotion_policy(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        policy=updated_policy,
    )
    rendered = updated_policy.to_dict()
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Policy path: {policy_path}")
    print(f"Updated fields: {', '.join(changed_fields)}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_set_track_policy(args: argparse.Namespace) -> int:
    workspace, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    policy_path = track_policy_path(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    current_policy, _ = _resolve_track_benchmark_policy(
        root=args.root,
        workspace=workspace,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )

    updated_fields, changed_fields = _resolve_routing_policy_updates(
        current_values={
            "search_benchmark": current_policy.search_benchmark,
            "promotion_benchmark": current_policy.promotion_benchmark,
            "regression_benchmark": current_policy.regression_benchmark,
            "search_preset": current_policy.search_preset,
            "promotion_preset": current_policy.promotion_preset,
            "regression_preset": current_policy.regression_preset,
        },
        args=args,
        changed_prefix="",
        remove_cleared_presets=False,
    )
    notes, changed = _resolve_notes_update(
        current_value=current_policy.notes,
        value=args.notes,
        clear=False,
    )
    if changed:
        changed_fields.append("notes")

    if not changed_fields:
        raise SystemExit("No track policy updates were provided.")

    updated_policy = TrackBenchmarkPolicy(
        format_version=current_policy.format_version,
        created_at=current_policy.created_at,
        track_id=track_id,
        search_benchmark=str(updated_fields["search_benchmark"]),
        promotion_benchmark=str(updated_fields["promotion_benchmark"]),
        regression_benchmark=str(updated_fields["regression_benchmark"]),
        search_preset=(
            str(updated_fields["search_preset"])
            if updated_fields["search_preset"] is not None
            else None
        ),
        promotion_preset=(
            str(updated_fields["promotion_preset"])
            if updated_fields["promotion_preset"] is not None
            else None
        ),
        regression_preset=(
            str(updated_fields["regression_preset"])
            if updated_fields["regression_preset"] is not None
            else None
        ),
        notes=notes,
    )
    _validate_track_benchmark_policy(updated_policy)
    persist_track_policy(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        policy=updated_policy,
    )

    rendered = updated_policy.to_dict()
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Policy path: {policy_path}")
    print(f"Updated fields: {', '.join(changed_fields)}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_set_workspace(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    _require_active_workspace_state(workspace_id=args.workspace_id, state=state)
    workspace_path = workspace_config_path(root=args.root, workspace_id=args.workspace_id)

    changed_fields: list[str] = []

    objective, changed = _resolve_update_field(
        option_name="objective",
        current_value=workspace.objective,
        value=args.objective,
    )
    if changed:
        changed_fields.append("objective")

    domain, changed = _resolve_update_field(
        option_name="domain",
        current_value=workspace.domain,
        value=args.domain,
    )
    if changed:
        changed_fields.append("domain")

    active_track_id, changed = _resolve_update_field(
        option_name="active-track-id",
        current_value=workspace.active_track_id,
        value=args.active_track_id,
    )
    if changed:
        changed_fields.append("active_track_id")

    benchmark_policy, policy_changed_fields = _resolve_routing_policy_updates(
        current_values=dict(workspace.benchmark_policy),
        args=args,
        changed_prefix="benchmark_policy.",
        remove_cleared_presets=True,
    )
    changed_fields.extend(policy_changed_fields)
    campaign_policy, campaign_policy_changed_fields = _resolve_campaign_policy_updates(
        current_values=dict(workspace.campaign_policy),
        args=args,
        changed_prefix="campaign_policy.",
        remove_cleared=True,
    )
    changed_fields.extend(campaign_policy_changed_fields)

    notes, changed = _resolve_notes_update(
        current_value=workspace.notes,
        value=args.notes,
        clear=args.clear_notes,
    )
    if changed:
        changed_fields.append("notes")

    if not changed_fields:
        raise SystemExit("No workspace updates were provided.")

    state_track_changed = active_track_id != state.active_track_id
    updated_workspace = replace(
        workspace,
        objective=objective,
        domain=domain,
        active_track_id=active_track_id,
        benchmark_policy=benchmark_policy,
        campaign_policy=campaign_policy,
        notes=notes,
    )
    _validate_workspace_config(updated_workspace)
    save_workspace(args.root, updated_workspace)

    if state_track_changed:
        state = replace(state, active_track_id=active_track_id)
        save_workspace_state(args.root, args.workspace_id, state)

    rendered = updated_workspace.to_dict()
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print(f"Workspace path: {workspace_path}")
    print(f"Updated fields: {', '.join(changed_fields)}")
    if state_track_changed:
        print(f"State active track: {active_track_id}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_archive_workspace(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    if state.status == "archived":
        raise SystemExit(f"Workspace `{args.workspace_id}` is already archived.")

    archived_state = replace(state, status="archived")
    save_workspace_state(args.root, args.workspace_id, archived_state)

    rendered = {
        "workspace_id": args.workspace_id,
        "status": archived_state.status,
        "workspace_path": str(workspace_config_path(root=args.root, workspace_id=args.workspace_id)),
        "tracks_total": len(workspace.tracks),
        "active_track_id": workspace.active_track_id,
    }
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print("Status: archived")
    print(f"Tracks: {len(workspace.tracks)}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_purge_workspace(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    if args.confirm_workspace_id != args.workspace_id:
        raise SystemExit("`--confirm-workspace-id` must exactly match `--workspace-id`.")
    if state.status != "archived":
        raise SystemExit(f"Workspace `{args.workspace_id}` must be archived before it can be purged.")

    workspace_dir = args.root / args.workspace_id
    track_ids = sorted(workspace.tracks)
    records_total = 0
    promotions_total = 0
    champion_tracks_total = 0
    for track_id in track_ids:
        records_total += len(
            list_track_benchmark_records(
                root=args.root,
                workspace_id=args.workspace_id,
                track_id=track_id,
            )
        )
        promotions_total += len(
            list_track_promotion_records(
                root=args.root,
                workspace_id=args.workspace_id,
                track_id=track_id,
            )
        )
        try:
            load_champion_manifest(
                root=args.root,
                workspace_id=args.workspace_id,
                track_id=track_id,
            )
        except FileNotFoundError:
            pass
        else:
            champion_tracks_total += 1
    iterations_total = len(
        list_workspace_iterations(
            root=args.root,
            workspace_id=args.workspace_id,
        )
    )

    shutil.rmtree(workspace_dir)

    rendered = {
        "purged_workspace_id": args.workspace_id,
        "workspace_path": str(workspace_dir),
        "removed_tracks_total": len(track_ids),
        "removed_iterations_total": iterations_total,
        "removed_records_total": records_total,
        "removed_promotions_total": promotions_total,
        "removed_champion_tracks_total": champion_tracks_total,
    }
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Purged workspace: {args.workspace_id}")
    print(f"Removed tracks: {len(track_ids)}")
    print(f"Removed iterations: {iterations_total}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_create_track(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    _require_active_workspace_state(workspace_id=args.workspace_id, state=state)
    track_id = args.track_id
    if track_id in workspace.tracks:
        raise SystemExit(f"Track `{track_id}` already exists in workspace `{args.workspace_id}`.")

    source_track_id = args.from_track or state.active_track_id or workspace.active_track_id
    if source_track_id not in workspace.tracks:
        raise SystemExit(
            f"Unknown source track `{source_track_id}` for workspace `{args.workspace_id}`."
        )
    source_track = workspace.tracks[source_track_id]

    benchmark_reference_ids = (
        tuple(args.benchmark_reference_id)
        if args.benchmark_reference_id is not None
        else source_track.benchmark_reference_ids
    )
    evaluator, _ = _apply_track_evaluator_overrides(
        evaluator=source_track.evaluator,
        args=args,
    )

    new_track = TrackConfig(
        track_id=track_id,
        benchmark=args.benchmark or source_track.benchmark,
        objective=args.objective or source_track.objective,
        campaign_id=f"{args.workspace_id}_{track_id}",
        status="active",
        kind=args.kind or source_track.kind,
        benchmark_reference_ids=benchmark_reference_ids,
        notes=(
            args.notes
            if args.notes is not None
            else f"Track scaffold created by autoharness create-track from `{source_track_id}`."
        ),
        campaign_policy=dict(source_track.campaign_policy),
        evaluator=evaluator,
    )
    _validate_track_config(new_track)

    updated_active_track_id = track_id if args.activate else workspace.active_track_id
    updated_workspace = replace(
        workspace,
        active_track_id=updated_active_track_id,
        tracks={**workspace.tracks, track_id: new_track},
    )
    _validate_workspace_config(updated_workspace)

    created_at = _utc_now()

    save_workspace(args.root, updated_workspace)
    _persist_track_bootstrap_artifacts(
        root=args.root,
        workspace_id=args.workspace_id,
        track=new_track,
        created_at=created_at,
    )
    next_state = _refresh_workspace_state_track_counts(
        state=state,
        workspace=updated_workspace,
        active_track_id=(track_id if args.activate else state.active_track_id),
    )
    save_workspace_state(args.root, args.workspace_id, next_state)

    rendered = new_track.to_dict()
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print(f"Created track: {track_id}")
    print(f"Source track: {source_track_id}")
    print(
        "Track path: "
        f"{track_config_path(root=args.root, workspace_id=args.workspace_id, track_id=track_id)}"
    )
    if args.activate:
        print(f"Active track: {track_id}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_switch_track(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    _require_active_workspace_state(workspace_id=args.workspace_id, state=state)
    track_id = args.track_id
    if track_id not in workspace.tracks:
        raise SystemExit(f"Unknown track `{track_id}` for workspace `{args.workspace_id}`.")
    if workspace.tracks[track_id].status != "active":
        raise SystemExit(f"Track `{track_id}` is archived and cannot be made active.")

    previous_track_id = workspace.active_track_id
    if previous_track_id == track_id and state.active_track_id == track_id:
        raise SystemExit(f"Track `{track_id}` is already active.")

    updated_workspace = replace(workspace, active_track_id=track_id)
    _validate_workspace_config(updated_workspace)
    save_workspace(args.root, updated_workspace)

    updated_state = replace(state, active_track_id=track_id)
    save_workspace_state(args.root, args.workspace_id, updated_state)

    rendered = {
        "workspace_id": args.workspace_id,
        "previous_active_track_id": previous_track_id,
        "active_track_id": track_id,
    }
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print(f"Previous active track: {previous_track_id}")
    print(f"Active track: {track_id}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_archive_track(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    _require_active_workspace_state(workspace_id=args.workspace_id, state=state)
    track_id = args.track_id
    if track_id not in workspace.tracks:
        raise SystemExit(f"Unknown track `{track_id}` for workspace `{args.workspace_id}`.")

    current_track = workspace.tracks[track_id]
    if current_track.status == "archived":
        raise SystemExit(f"Track `{track_id}` is already archived.")

    replacement_track_id: str | None = None
    if workspace.active_track_id == track_id or state.active_track_id == track_id:
        requested_replacement = args.activate_track_id
        if requested_replacement is not None:
            if requested_replacement == track_id:
                raise SystemExit("Replacement active track must differ from the archived track.")
            if requested_replacement not in workspace.tracks:
                raise SystemExit(
                    f"Unknown replacement active track `{requested_replacement}` for workspace `{args.workspace_id}`."
                )
            if workspace.tracks[requested_replacement].status != "active":
                raise SystemExit(
                    f"Replacement active track `{requested_replacement}` must have status `active`."
                )
            replacement_track_id = requested_replacement
        else:
            for candidate_track_id in sorted(workspace.tracks):
                if candidate_track_id == track_id:
                    continue
                if workspace.tracks[candidate_track_id].status == "active":
                    replacement_track_id = candidate_track_id
                    break
        if replacement_track_id is None:
            raise SystemExit(
                "Cannot archive the only active track in the workspace. Create or activate another track first."
            )

    archived_track = replace(current_track, status="archived")
    next_active_track_id = replacement_track_id or workspace.active_track_id
    updated_workspace = replace(
        workspace,
        active_track_id=next_active_track_id,
        tracks={**workspace.tracks, track_id: archived_track},
    )
    _validate_track_config(archived_track)
    _validate_workspace_config(updated_workspace)
    save_workspace(args.root, updated_workspace)
    persist_track_config(
        root=args.root,
        workspace_id=args.workspace_id,
        track=archived_track,
    )

    updated_state = _refresh_workspace_state_track_counts(
        state=state,
        workspace=updated_workspace,
        active_track_id=(replacement_track_id or state.active_track_id),
    )
    save_workspace_state(args.root, args.workspace_id, updated_state)

    rendered = {
        "workspace_id": args.workspace_id,
        "track_id": track_id,
        "status": "archived",
        "active_track_id": updated_workspace.active_track_id,
        "replacement_track_id": replacement_track_id,
    }
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print(f"Archived track: {track_id}")
    if replacement_track_id is not None:
        print(f"Active track: {replacement_track_id}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_purge_track(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    _require_active_workspace_state(workspace_id=args.workspace_id, state=state)
    track_id = args.track_id
    if args.confirm_track_id != track_id:
        raise SystemExit("`--confirm-track-id` must exactly match `--track-id`.")
    if track_id not in workspace.tracks:
        raise SystemExit(f"Unknown track `{track_id}` for workspace `{args.workspace_id}`.")
    if workspace.active_track_id == track_id or state.active_track_id == track_id:
        raise SystemExit(f"Track `{track_id}` is active and cannot be purged.")

    current_track = workspace.tracks[track_id]
    if current_track.status != "archived":
        raise SystemExit(f"Track `{track_id}` must be archived before it can be purged.")

    records = list_track_benchmark_records(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    promotions = list_track_promotion_records(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    champion_path = track_dir_path(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    ) / "champion.json"
    champion_exists = champion_path.exists()
    track_iterations, _ = query_workspace_iteration_items(
        root=args.root,
        workspace_id=args.workspace_id,
        last_iteration_id=state.last_iteration_id,
        spec=IterationQuerySpec(track_id=track_id),
    )

    updated_tracks = dict(workspace.tracks)
    del updated_tracks[track_id]
    if not updated_tracks:
        raise SystemExit("Cannot purge the last track in the workspace.")

    updated_workspace = replace(workspace, tracks=updated_tracks)
    _validate_workspace_config(updated_workspace)
    save_workspace(args.root, updated_workspace)

    purged_iteration_ids: list[str] = []
    for item in track_iterations:
        iteration_id = item.get("iteration_id")
        if isinstance(iteration_id, str):
            purged_iteration_ids.append(iteration_id)
        iteration_path = item.get("iteration_path")
        if isinstance(iteration_path, str):
            path = Path(iteration_path)
            if path.exists():
                shutil.rmtree(path)

    track_path = track_dir_path(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    if track_path.exists():
        shutil.rmtree(track_path)

    rebuilt_state = _rebuild_workspace_state_from_artifacts(
        root=args.root,
        workspace=updated_workspace,
        state=state,
    )
    save_workspace_state(args.root, args.workspace_id, rebuilt_state)

    rendered = {
        "workspace_id": args.workspace_id,
        "purged_track_id": track_id,
        "purged_track_path": str(track_path),
        "removed_records_total": len(records),
        "removed_promotions_total": len(promotions),
        "removed_champion_manifest": champion_exists,
        "purged_iteration_ids": sorted(purged_iteration_ids),
        "active_track_id": updated_workspace.active_track_id,
        "remaining_tracks_total": len(updated_workspace.tracks),
    }
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print(f"Purged track: {track_id}")
    print(f"Active track: {updated_workspace.active_track_id}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_set_track(args: argparse.Namespace) -> int:
    workspace, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    workspace_path = workspace_config_path(root=args.root, workspace_id=args.workspace_id)
    campaign_path = track_config_path(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    current_track = workspace.tracks[track_id]
    changed_fields: list[str] = []

    objective, changed = _resolve_update_field(
        option_name="objective",
        current_value=current_track.objective,
        value=args.objective,
    )
    if changed:
        changed_fields.append("objective")

    kind, changed = _resolve_update_field(
        option_name="kind",
        current_value=current_track.kind,
        value=args.kind,
    )
    if changed:
        changed_fields.append("kind")

    if args.clear_benchmark_reference_ids and args.benchmark_reference_id is not None:
        raise SystemExit(
            "Use either `--benchmark-reference-id` or `--clear-benchmark-reference-ids`, not both."
        )
    benchmark_reference_ids = current_track.benchmark_reference_ids
    if args.clear_benchmark_reference_ids:
        benchmark_reference_ids = ()
        changed_fields.append("benchmark_reference_ids")
    elif args.benchmark_reference_id is not None:
        benchmark_reference_ids = tuple(args.benchmark_reference_id)
        changed_fields.append("benchmark_reference_ids")

    notes, changed = _resolve_notes_update(
        current_value=current_track.notes,
        value=args.notes,
        clear=args.clear_notes,
    )
    if changed:
        changed_fields.append("notes")

    evaluator, evaluator_changed_fields = _apply_track_evaluator_overrides(
        evaluator=current_track.evaluator,
        args=args,
    )
    changed_fields.extend(evaluator_changed_fields)
    campaign_policy, campaign_policy_changed_fields = _resolve_campaign_policy_updates(
        current_values=dict(current_track.campaign_policy),
        args=args,
        changed_prefix="campaign_policy.",
        remove_cleared=True,
    )
    changed_fields.extend(campaign_policy_changed_fields)

    if not changed_fields:
        raise SystemExit("No track updates were provided.")

    updated_track = replace(
        current_track,
        objective=objective,
        kind=kind,
        benchmark_reference_ids=benchmark_reference_ids,
        notes=notes,
        campaign_policy=campaign_policy,
        evaluator=evaluator,
    )
    _validate_track_config(updated_track)
    updated_workspace = replace(
        workspace,
        tracks={**workspace.tracks, track_id: updated_track},
    )
    persist_workspace_track(
        root=args.root,
        workspace=updated_workspace,
        track_id=track_id,
    )

    rendered = updated_track.to_dict()
    if args.output is not None:
        _write_json(args.output, rendered)

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Workspace path: {workspace_path}")
    print(f"Track path: {campaign_path}")
    print(f"Updated fields: {', '.join(changed_fields)}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_init_workspace(args: argparse.Namespace) -> int:
    if not isinstance(args.workspace_id, str) or not args.workspace_id.strip():
        raise SystemExit(
            "`--workspace-id` is required unless provided by autoharness project config."
        )
    if not isinstance(args.objective, str) or not args.objective.strip():
        raise SystemExit(
            "`--objective` is required unless provided by autoharness project config."
        )
    if not isinstance(args.benchmark, str) or not args.benchmark.strip():
        raise SystemExit(
            "`--benchmark` is required unless provided by autoharness project config."
        )
    settings = _load_settings(args.settings)
    workspace_root = args.root / args.workspace_id

    if workspace_root.exists() and not args.force:
        raise SystemExit(
            f"Refusing to overwrite existing workspace: {workspace_root}. Use --force."
        )

    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "iterations").mkdir(exist_ok=True)
    (workspace_root / "tracks" / args.track_id / "registry").mkdir(
        parents=True, exist_ok=True
    )

    created_at = _utc_now()
    campaign = TrackConfig(
        track_id=args.track_id,
        benchmark=args.benchmark,
        objective=args.objective,
        campaign_id=f"{args.workspace_id}_{args.track_id}",
        campaign_policy={},
        evaluator=CampaignEvaluatorPolicy(
            evaluator_version=created_at[:10],
            judge_model=args.judge_model,
            diagnostic_model=args.diagnostic_model,
        ),
        notes="Initial track scaffold created by autoharness init-workspace.",
    )

    workspace = WorkspaceConfig(
        format_version="autoharness.workspace.v1",
        workspace_id=args.workspace_id,
        objective=args.objective,
        domain=args.domain,
        active_track_id=args.track_id,
        created_at=created_at,
        autonomy=policy_for_mode(
            settings["autonomy"]["mode"],
            editable_surfaces=tuple(
                settings["autonomy"].get("editable_surfaces", [])
            ),
            protected_surfaces=tuple(
                settings["autonomy"].get("protected_surfaces", [])
            ),
        ),
        benchmark_policy={
            "search_benchmark": args.benchmark,
            "promotion_benchmark": args.benchmark,
            "regression_benchmark": args.benchmark,
        },
        campaign_policy={},
        tracks={args.track_id: campaign},
    )
    state = WorkspaceState(
        format_version="autoharness.workspace_state.v1",
        workspace_id=args.workspace_id,
        status="active",
        active_track_id=args.track_id,
    )

    save_workspace(args.root, workspace)
    _write_json(workspace_root / "state.json", state.to_dict())
    _persist_track_bootstrap_artifacts(
        root=args.root,
        workspace_id=args.workspace_id,
        track=campaign,
        created_at=created_at,
    )
    (workspace_root / "program.md").write_text(
        (
            f"# Workspace Program\n\n"
            f"Objective: {args.objective}\n\n"
            f"- Use one hypothesis per iteration.\n"
            f"- Keep the evaluator policy pinned inside this track.\n"
            f"- Respect autonomy mode `{workspace.autonomy.mode}`.\n"
            f"- Prefer the cheapest decisive evaluation path first.\n"
        ),
        encoding="utf-8",
    )

    print(f"Created workspace at {workspace_root}")
    print(f"Active track: {args.track_id}")
    print(f"Benchmark: {args.benchmark}")
    print(f"Autonomy mode: {workspace.autonomy.mode}")
    return 0


def _parse_key_value_assignments(entries: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for entry in entries:
        if "=" not in entry:
            raise SystemExit(f"Expected KEY=VALUE assignment, got: {entry}")
        key, value = entry.split("=", 1)
        if not key.strip():
            raise SystemExit(f"Expected non-empty KEY in assignment: {entry}")
        parsed[key.strip()] = value.strip()
    return parsed


def _handle_show_provider_profile(args: argparse.Namespace) -> int:
    _, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    profiles = load_provider_profiles(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    profile_path = provider_profiles_path(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    if args.provider_id is not None:
        profile = dict(profiles.get(args.provider_id, {}))
        rendered = {
            "workspace_id": args.workspace_id,
            "track_id": track_id,
            "provider_id": args.provider_id,
            "profile_path": str(profile_path),
            "profile": profile,
            "profile_summary": summarize_provider_profile(
                provider_id=args.provider_id,
                profile=profile,
            ),
        }
    else:
        rendered = {
            "workspace_id": args.workspace_id,
            "track_id": track_id,
            "profile_path": str(profile_path),
            "profile_total": len(profiles),
            "profiles": profiles,
            "profile_summaries": summarize_provider_profiles(profiles),
        }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    if args.provider_id is not None:
        print(f"Provider: {args.provider_id}")
        print(f"Profile keys: {len(rendered['profile'])}")
    else:
        print(f"Profiles: {rendered['profile_total']}")
    print(f"Profile path: {profile_path}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_set_provider_profile(args: argparse.Namespace) -> int:
    _, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    profiles = load_provider_profiles(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    provider_id = args.provider_id
    current_profile = dict(profiles.get(provider_id, {}))
    next_profile = {} if args.clear else dict(current_profile)
    changed_fields: list[str] = []

    for key in args.clear_option:
        if key in next_profile:
            del next_profile[key]
            changed_fields.append(f"clear:{key}")

    option_updates = _parse_key_value_assignments(list(args.option))
    for key, value in option_updates.items():
        if next_profile.get(key) != value:
            next_profile[key] = value
            changed_fields.append(f"set:{key}")

    if args.clear and provider_id in profiles and "clear:profile" not in changed_fields:
        changed_fields.insert(0, "clear:profile")

    if not changed_fields:
        raise SystemExit("No provider profile updates were provided.")

    if next_profile:
        profiles[provider_id] = next_profile
    else:
        profiles.pop(provider_id, None)

    profile_path = persist_provider_profiles(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        profiles=profiles,
    )
    rendered = {
        "workspace_id": args.workspace_id,
        "track_id": track_id,
        "provider_id": provider_id,
        "profile_path": str(profile_path),
        "updated_fields": changed_fields,
        "profile": dict(profiles.get(provider_id, {})),
        "profile_summary": summarize_provider_profile(
            provider_id=provider_id,
            profile=dict(profiles.get(provider_id, {})),
        ),
        "removed": provider_id not in profiles,
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Provider: {provider_id}")
    print(f"Updated fields: {', '.join(changed_fields)}")
    print(f"Profile path: {profile_path}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_retention_policy(args: argparse.Namespace) -> int:
    policy = load_retention_policy(root=args.root, workspace_id=args.workspace_id)
    policy_path = retention_policy_path(root=args.root, workspace_id=args.workspace_id)
    rendered = {
        "workspace_id": args.workspace_id,
        "policy_path": str(policy_path),
        "policy": policy,
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Policy path: {policy_path}")
    print(
        "Keep latest campaign runs: "
        f"{policy.get('keep_latest_campaign_runs')}"
    )
    print(
        "Prune failed candidate patches older than days: "
        f"{policy.get('prune_failed_candidate_patches_older_than_days')}"
    )
    print(
        "Keep champion campaigns forever: "
        f"{'yes' if policy.get('keep_champion_campaigns_forever') else 'no'}"
    )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_set_retention_policy(args: argparse.Namespace) -> int:
    policy = load_retention_policy(root=args.root, workspace_id=args.workspace_id)
    updated_policy = dict(policy)
    changed_fields: list[str] = []

    if args.keep_latest_campaign_runs is not None:
        updated_policy["keep_latest_campaign_runs"] = args.keep_latest_campaign_runs
        changed_fields.append("keep_latest_campaign_runs")
    if args.prune_failed_candidate_patches_older_than_days is not None:
        updated_policy["prune_failed_candidate_patches_older_than_days"] = (
            args.prune_failed_candidate_patches_older_than_days
        )
        changed_fields.append("prune_failed_candidate_patches_older_than_days")
    if args.keep_champion_campaigns_forever is not None:
        updated_policy["keep_champion_campaigns_forever"] = (
            args.keep_champion_campaigns_forever
        )
        changed_fields.append("keep_champion_campaigns_forever")

    if not changed_fields:
        raise SystemExit("No retention policy updates were provided.")

    policy_path = persist_retention_policy(
        root=args.root,
        workspace_id=args.workspace_id,
        policy=updated_policy,
    )
    rendered = {
        "workspace_id": args.workspace_id,
        "policy_path": str(policy_path),
        "updated_fields": changed_fields,
        "policy": load_retention_policy(root=args.root, workspace_id=args.workspace_id),
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Policy path: {policy_path}")
    print(f"Updated fields: {', '.join(changed_fields)}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_prune_artifacts(args: argparse.Namespace) -> int:
    result = prune_workspace_artifacts(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=args.track_id,
        dry_run=args.dry_run,
    )
    if _emit_json_output(rendered=result, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    if args.track_id is not None:
        print(f"Track filter: {args.track_id}")
    print(f"Dry run: {'yes' if args.dry_run else 'no'}")
    print(f"Removed paths: {result['removed_total']}")
    print(f"Kept campaign files: {result['kept_campaign_total']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0
