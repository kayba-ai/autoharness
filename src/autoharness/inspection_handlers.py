"""Inspection-style CLI handlers for workspace, track, and policy views."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .cli_support import (
    _load_structured_file,
    _resolve_workspace_id,
    _resolve_workspace_track,
    _resolved_track_campaign_policy_details,
    _resolved_track_policy_details,
)
from .listings import (
    _build_iteration_listing_payload,
    _build_promotion_listing_payload,
    _build_record_listing_payload,
)
from .mutations import _utc_now
from .outputs import _emit_json_output, _write_structured_payload
from .plugins import (
    plugin_catalog_entries,
    plugin_load_failures,
    plugin_runtime_contract_summary,
)
from .promotion_handlers import _export_champion_bundle, _prepare_export_dir
from .campaign_handlers import (
    _handle_show_campaign_report_file,
    _handle_validate_campaign_report_file,
)
from .execution_handlers import _handle_show_plan_file, _handle_validate_plan_file
from .listing_handlers import _handle_show_listing_file, _handle_validate_listing_file
from .queries import (
    IterationQuerySpec,
    PromotionQuerySpec,
    RecordQuerySpec,
    query_workspace_iteration_items,
)
from .root_memory import build_root_memory, persist_root_memory, root_memory_path
from .tracking import (
    iteration_dir_path,
    load_benchmark_record,
    load_champion_manifest,
    load_promotion_policy,
    load_workspace,
    load_workspace_state,
    list_track_benchmark_records,
    list_track_promotion_records,
    promotion_policy_path,
    promotions_dir_path,
    registry_dir_path,
    track_config_path,
    track_dir_path,
    track_policy_path,
    workspace_config_path,
)
from .events import aggregate_event_metrics, load_workspace_events
from .provider_profiles import (
    load_provider_profiles,
    provider_profiles_path,
    summarize_provider_profiles,
)


def _render_campaign_default_snapshot(
    policy_details: dict[str, object],
) -> dict[str, object]:
    effective_policy = policy_details["effective_policy"]
    assert isinstance(effective_policy, dict)
    effective_sources = policy_details["effective_sources"]
    assert isinstance(effective_sources, dict)
    return {
        "effective_policy": {
            "stage": effective_policy["stage"],
            "generator_id": effective_policy["generator_id"],
            "strategy": effective_policy["strategy"],
            "beam_width": effective_policy.get("beam_width"),
            "beam_group_limit": effective_policy.get("beam_group_limit"),
            "repeat_count": effective_policy.get("repeat_count"),
            "max_generation_total_tokens": effective_policy.get(
                "max_generation_total_tokens"
            ),
            "max_benchmark_total_cost": effective_policy.get(
                "max_benchmark_total_cost"
            ),
            "stage_progression_mode": effective_policy["stage_progression_mode"],
            "intervention_classes": list(
                effective_policy.get("intervention_classes", [])
            ),
            "preflight_checks": list(effective_policy.get("preflight_checks", [])),
            "preflight_check_count": len(
                effective_policy.get("preflight_checks", [])
            ),
            "preflight_commands": list(effective_policy.get("preflight_commands", [])),
            "preflight_command_count": len(
                effective_policy.get("preflight_commands", [])
            ),
            "preflight_timeout_seconds": effective_policy.get(
                "preflight_timeout_seconds"
            ),
            "max_generation_retries": effective_policy.get("max_generation_retries"),
            "max_generation_timeout_retries": effective_policy.get(
                "max_generation_timeout_retries"
            ),
            "max_generation_provider_retries": effective_policy.get(
                "max_generation_provider_retries"
            ),
            "max_generation_provider_transport_retries": effective_policy.get(
                "max_generation_provider_transport_retries"
            ),
            "max_generation_provider_auth_retries": effective_policy.get(
                "max_generation_provider_auth_retries"
            ),
            "max_generation_provider_rate_limit_retries": effective_policy.get(
                "max_generation_provider_rate_limit_retries"
            ),
            "max_generation_process_retries": effective_policy.get(
                "max_generation_process_retries"
            ),
            "max_preflight_retries": effective_policy.get("max_preflight_retries"),
            "max_execution_retries": effective_policy.get("max_execution_retries"),
            "max_benchmark_process_retries": effective_policy.get(
                "max_benchmark_process_retries"
            ),
            "max_benchmark_signal_retries": effective_policy.get(
                "max_benchmark_signal_retries"
            ),
            "max_benchmark_parse_retries": effective_policy.get(
                "max_benchmark_parse_retries"
            ),
            "max_benchmark_adapter_validation_retries": effective_policy.get(
                "max_benchmark_adapter_validation_retries"
            ),
            "max_benchmark_timeout_retries": effective_policy.get(
                "max_benchmark_timeout_retries"
            ),
            "max_benchmark_command_retries": effective_policy.get(
                "max_benchmark_command_retries"
            ),
            "max_inconclusive_retries": effective_policy.get(
                "max_inconclusive_retries"
            ),
            "auto_promote": bool(effective_policy["auto_promote"]),
            "allow_flaky_promotion": bool(
                effective_policy.get("allow_flaky_promotion", False)
            ),
            "auto_promote_min_stage": effective_policy.get("auto_promote_min_stage"),
            "stop_on_first_promotion": bool(
                effective_policy["stop_on_first_promotion"]
            ),
        },
        "effective_sources": {
            "stage": effective_sources["stage"],
            "generator_id": effective_sources["generator_id"],
            "strategy": effective_sources["strategy"],
            "beam_width": effective_sources["beam_width"],
            "beam_group_limit": effective_sources["beam_group_limit"],
            "repeat_count": effective_sources["repeat_count"],
            "max_generation_total_tokens": effective_sources[
                "max_generation_total_tokens"
            ],
            "max_benchmark_total_cost": effective_sources[
                "max_benchmark_total_cost"
            ],
            "stage_progression_mode": effective_sources["stage_progression_mode"],
            "intervention_classes": effective_sources["intervention_classes"],
            "preflight_checks": effective_sources["preflight_checks"],
            "preflight_commands": effective_sources["preflight_commands"],
            "preflight_timeout_seconds": effective_sources[
                "preflight_timeout_seconds"
            ],
            "max_generation_retries": effective_sources["max_generation_retries"],
            "max_generation_timeout_retries": effective_sources[
                "max_generation_timeout_retries"
            ],
            "max_generation_provider_retries": effective_sources[
                "max_generation_provider_retries"
            ],
            "max_generation_provider_transport_retries": effective_sources[
                "max_generation_provider_transport_retries"
            ],
            "max_generation_provider_auth_retries": effective_sources[
                "max_generation_provider_auth_retries"
            ],
            "max_generation_provider_rate_limit_retries": effective_sources[
                "max_generation_provider_rate_limit_retries"
            ],
            "max_generation_process_retries": effective_sources[
                "max_generation_process_retries"
            ],
            "max_preflight_retries": effective_sources["max_preflight_retries"],
            "max_execution_retries": effective_sources["max_execution_retries"],
            "max_benchmark_process_retries": effective_sources[
                "max_benchmark_process_retries"
            ],
            "max_benchmark_signal_retries": effective_sources[
                "max_benchmark_signal_retries"
            ],
            "max_benchmark_parse_retries": effective_sources[
                "max_benchmark_parse_retries"
            ],
            "max_benchmark_adapter_validation_retries": effective_sources[
                "max_benchmark_adapter_validation_retries"
            ],
            "max_benchmark_timeout_retries": effective_sources[
                "max_benchmark_timeout_retries"
            ],
            "max_benchmark_command_retries": effective_sources[
                "max_benchmark_command_retries"
            ],
            "max_inconclusive_retries": effective_sources[
                "max_inconclusive_retries"
            ],
            "auto_promote": effective_sources["auto_promote"],
            "allow_flaky_promotion": effective_sources["allow_flaky_promotion"],
            "auto_promote_min_stage": effective_sources["auto_promote_min_stage"],
            "stop_on_first_promotion": effective_sources["stop_on_first_promotion"],
        },
    }


def _discover_workspace_ids(root: Path) -> list[str]:
    if not root.exists():
        return []
    workspace_ids: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        if (path / "workspace.json").exists():
            workspace_ids.append(path.name)
    return workspace_ids


def _campaign_default_mix_key(value: object) -> str:
    if value is None:
        return "(unset)"
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or "(unset)"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _summarize_campaign_default_mix(
    snapshots: list[dict[str, object]],
) -> dict[str, dict[str, int]]:
    field_names = (
        "stage",
        "stage_progression_mode",
        "generator_id",
        "strategy",
        "beam_width",
        "beam_group_limit",
        "repeat_count",
        "max_generation_total_tokens",
        "max_benchmark_total_cost",
        "preflight_check_count",
        "preflight_command_count",
        "preflight_timeout_seconds",
        "max_generation_retries",
        "max_generation_timeout_retries",
        "max_generation_provider_retries",
        "max_generation_provider_transport_retries",
        "max_generation_provider_auth_retries",
        "max_generation_provider_rate_limit_retries",
        "max_generation_process_retries",
        "max_preflight_retries",
        "max_execution_retries",
        "max_benchmark_process_retries",
        "max_benchmark_signal_retries",
        "max_benchmark_parse_retries",
        "max_benchmark_adapter_validation_retries",
        "max_benchmark_timeout_retries",
        "max_benchmark_command_retries",
        "max_inconclusive_retries",
        "auto_promote",
        "allow_flaky_promotion",
        "auto_promote_min_stage",
        "stop_on_first_promotion",
    )
    mix: dict[str, dict[str, int]] = {
        field_name: {} for field_name in field_names
    }
    preflight_check_id_counts: dict[str, int] = {}
    for snapshot in snapshots:
        preflight_checks = snapshot.get("preflight_checks")
        if isinstance(preflight_checks, list):
            for check_id in preflight_checks:
                if not isinstance(check_id, str) or not check_id:
                    continue
                preflight_check_id_counts[check_id] = (
                    preflight_check_id_counts.get(check_id, 0) + 1
                )
        for field_name in field_names:
            key = _campaign_default_mix_key(snapshot.get(field_name))
            field_counts = mix[field_name]
            field_counts[key] = field_counts.get(key, 0) + 1
    return {
        "by_stage": mix["stage"],
        "by_stage_progression_mode": mix["stage_progression_mode"],
        "by_generator_id": mix["generator_id"],
        "by_strategy": mix["strategy"],
        "by_beam_width": mix["beam_width"],
        "by_beam_group_limit": mix["beam_group_limit"],
        "by_repeat_count": mix["repeat_count"],
        "by_max_generation_total_tokens": mix["max_generation_total_tokens"],
        "by_max_benchmark_total_cost": mix["max_benchmark_total_cost"],
        "by_preflight_check_id": preflight_check_id_counts,
        "by_preflight_check_count": mix["preflight_check_count"],
        "by_preflight_command_count": mix["preflight_command_count"],
        "by_preflight_timeout_seconds": mix["preflight_timeout_seconds"],
        "by_max_generation_retries": mix["max_generation_retries"],
        "by_max_generation_timeout_retries": mix["max_generation_timeout_retries"],
        "by_max_generation_provider_retries": mix["max_generation_provider_retries"],
        "by_max_generation_provider_transport_retries": mix[
            "max_generation_provider_transport_retries"
        ],
        "by_max_generation_provider_auth_retries": mix[
            "max_generation_provider_auth_retries"
        ],
        "by_max_generation_provider_rate_limit_retries": mix[
            "max_generation_provider_rate_limit_retries"
        ],
        "by_max_generation_process_retries": mix["max_generation_process_retries"],
        "by_max_preflight_retries": mix["max_preflight_retries"],
        "by_max_execution_retries": mix["max_execution_retries"],
        "by_max_benchmark_process_retries": mix["max_benchmark_process_retries"],
        "by_max_benchmark_signal_retries": mix["max_benchmark_signal_retries"],
        "by_max_benchmark_parse_retries": mix["max_benchmark_parse_retries"],
        "by_max_benchmark_adapter_validation_retries": mix[
            "max_benchmark_adapter_validation_retries"
        ],
        "by_max_benchmark_timeout_retries": mix["max_benchmark_timeout_retries"],
        "by_max_benchmark_command_retries": mix["max_benchmark_command_retries"],
        "by_max_inconclusive_retries": mix["max_inconclusive_retries"],
        "by_auto_promote": mix["auto_promote"],
        "by_allow_flaky_promotion": mix["allow_flaky_promotion"],
        "by_auto_promote_min_stage": mix["auto_promote_min_stage"],
        "by_stop_on_first_promotion": mix["stop_on_first_promotion"],
    }


def _render_root_summary(
    *,
    root: Path,
    requested_workspace_ids: list[str],
) -> dict[str, object]:
    requested_workspace_id_set = set(requested_workspace_ids)
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not requested_workspace_id_set or workspace_id in requested_workspace_id_set
    ]
    workspace_status_counts: dict[str, int] = {}
    active_track_policy_snapshots: list[dict[str, object]] = []
    workspace_items: list[dict[str, object]] = []
    total_tracks = 0
    total_active_tracks = 0
    total_archived_tracks = 0
    total_iterations = 0
    total_records = 0
    total_source_plan_records = 0
    total_promotions = 0
    total_champion_tracks = 0

    for workspace_id in selected_workspace_ids:
        summary = _render_workspace_summary(root=root, workspace_id=workspace_id)
        counts = summary["counts"]
        assert isinstance(counts, dict)
        status = str(summary["status"])
        workspace_status_counts[status] = workspace_status_counts.get(status, 0) + 1
        total_tracks += int(counts["tracks_total"])
        total_active_tracks += int(counts["active_tracks_total"])
        total_archived_tracks += int(counts["archived_tracks_total"])
        total_iterations += int(counts["iterations_total"])
        total_records += int(counts["records_total"])
        total_source_plan_records += int(counts["source_plan_records_total"])
        total_promotions += int(counts["promotions_total"])
        total_champion_tracks += int(counts["champion_tracks_total"])
        active_track_campaign_policy = summary["active_track_effective_campaign_policy"]
        assert isinstance(active_track_campaign_policy, dict)
        effective_policy = active_track_campaign_policy["effective_policy"]
        assert isinstance(effective_policy, dict)
        active_track_policy_snapshots.append(dict(effective_policy))
        workspace_items.append(
            {
                "workspace_id": summary["workspace_id"],
                "workspace_path": summary["workspace_path"],
                "objective": summary["objective"],
                "domain": summary["domain"],
                "status": summary["status"],
                "autonomy_mode": summary["autonomy_mode"],
                "active_track_id": summary["active_track_id"],
                "counts": counts,
                "active_track_effective_campaign_policy": active_track_campaign_policy,
            }
        )

    return {
        "root_path": str(root),
        "workspace_filter": list(requested_workspace_ids),
        "workspace_total": len(selected_workspace_ids),
        "counts": {
            "workspaces_total": len(selected_workspace_ids),
            "active_workspaces_total": workspace_status_counts.get("active", 0),
            "archived_workspaces_total": workspace_status_counts.get("archived", 0),
            "tracks_total": total_tracks,
            "active_tracks_total": total_active_tracks,
            "archived_tracks_total": total_archived_tracks,
            "iterations_total": total_iterations,
            "records_total": total_records,
            "source_plan_records_total": total_source_plan_records,
            "promotions_total": total_promotions,
            "champion_tracks_total": total_champion_tracks,
        },
        "workspace_status_counts": workspace_status_counts,
        "active_track_campaign_default_mix": _summarize_campaign_default_mix(
            active_track_policy_snapshots
        ),
        "workspaces": workspace_items,
    }


def _render_root_report(
    *,
    root: Path,
    requested_workspace_ids: list[str],
) -> dict[str, object]:
    requested_workspace_id_set = set(requested_workspace_ids)
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not requested_workspace_id_set or workspace_id in requested_workspace_id_set
    ]
    return {
        "root_path": str(root),
        "workspace_filter": list(requested_workspace_ids),
        "root_summary": _render_root_summary(
            root=root,
            requested_workspace_ids=requested_workspace_ids,
        ),
        "root_memory": build_root_memory(
            root=root,
            requested_workspace_ids=requested_workspace_ids or None,
        ),
        "workspace_reports": [
            {
                "workspace_id": workspace_id,
                **_render_workspace_report(root=root, workspace_id=workspace_id),
            }
            for workspace_id in selected_workspace_ids
        ],
    }


def _render_root_champion_report(
    *,
    root: Path,
    requested_workspace_ids: list[str],
    requested_track_ids: list[str],
) -> dict[str, object]:
    requested_workspace_id_set = set(requested_workspace_ids)
    requested_track_id_set = set(requested_track_ids)
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not requested_workspace_id_set or workspace_id in requested_workspace_id_set
    ]
    champions: list[dict[str, object]] = []
    stage_counts: dict[str, int] = {}
    adapter_counts: dict[str, int] = {}
    benchmark_counts: dict[str, int] = {}
    source_workspace_counts: dict[str, int] = {}
    transferred_total = 0

    for workspace_id in selected_workspace_ids:
        workspace = load_workspace(root, workspace_id)
        for track_id in sorted(workspace.tracks):
            if requested_track_id_set and track_id not in requested_track_id_set:
                continue
            try:
                champion = load_champion_manifest(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                )
            except FileNotFoundError:
                continue
            transfer_source = None
            try:
                record = load_benchmark_record(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                    record_id=champion.record_id,
                )
            except FileNotFoundError:
                record = None
            if record is not None and isinstance(
                record.payload.get("transfer_source"),
                dict,
            ):
                transfer_source = dict(record.payload["transfer_source"])
            source_workspace_id = (
                str(transfer_source.get("workspace_id"))
                if isinstance(transfer_source, dict)
                and isinstance(transfer_source.get("workspace_id"), str)
                else None
            )
            if source_workspace_id is not None:
                transferred_total += 1
            stage_key = _campaign_default_mix_key(champion.stage)
            adapter_key = _campaign_default_mix_key(champion.adapter_id)
            benchmark_key = _campaign_default_mix_key(champion.benchmark_name)
            source_workspace_key = (
                source_workspace_id if source_workspace_id is not None else "(native)"
            )
            stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1
            adapter_counts[adapter_key] = adapter_counts.get(adapter_key, 0) + 1
            benchmark_counts[benchmark_key] = benchmark_counts.get(benchmark_key, 0) + 1
            source_workspace_counts[source_workspace_key] = (
                source_workspace_counts.get(source_workspace_key, 0) + 1
            )
            champions.append(
                {
                    "workspace_id": workspace_id,
                    "track_id": track_id,
                    "record_id": champion.record_id,
                    "promotion_id": champion.promotion_id,
                    "adapter_id": champion.adapter_id,
                    "benchmark_name": champion.benchmark_name,
                    "stage": champion.stage,
                    "status": champion.status,
                    "success": champion.success,
                    "updated_at": champion.updated_at,
                    "target_root": champion.target_root,
                    "record_path": champion.record_path,
                    "promotion_path": champion.promotion_path,
                    "diff_path": champion.diff_path,
                    "parsed_artifact_sources_path": champion.parsed_artifact_sources_path,
                    "transfer_source": transfer_source,
                    "is_transferred": transfer_source is not None,
                }
            )

    return {
        "root_path": str(root),
        "workspace_filter": list(requested_workspace_ids),
        "track_filter": list(requested_track_ids),
        "workspace_total": len(selected_workspace_ids),
        "champion_total": len(champions),
        "transferred_champion_total": transferred_total,
        "mix": {
            "by_stage": stage_counts,
            "by_adapter_id": adapter_counts,
            "by_benchmark_name": benchmark_counts,
            "by_source_workspace_id": source_workspace_counts,
        },
        "champions": champions,
    }


def _render_workspace_summary(*, root, workspace_id: str) -> dict[str, object]:
    workspace = load_workspace(root, workspace_id)
    state = load_workspace_state(root, workspace_id)
    active_track_campaign_policy = _resolved_track_campaign_policy_details(
        workspace=workspace,
        track_id=workspace.active_track_id,
    )
    iterations, _ = query_workspace_iteration_items(
        root=root,
        workspace_id=workspace_id,
        last_iteration_id=state.last_iteration_id,
        spec=IterationQuerySpec(),
    )

    record_status_counts: dict[str, int] = {}
    record_stage_counts: dict[str, int] = {}
    source_plan_stage_counts: dict[str, int] = {}
    total_records = 0
    total_promotions = 0
    champion_tracks = 0
    source_plan_records_total = 0
    track_items = []

    for track_id in sorted(workspace.tracks):
        track = workspace.tracks[track_id]
        track_campaign_policy = _resolved_track_campaign_policy_details(
            workspace=workspace,
            track_id=track_id,
        )
        records = list_track_benchmark_records(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
        promotions = list_track_promotion_records(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
        try:
            champion = load_champion_manifest(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
        except FileNotFoundError:
            champion = None

        total_records += len(records)
        total_promotions += len(promotions)
        if champion is not None:
            champion_tracks += 1

        track_status_counts: dict[str, int] = {}
        track_stage_counts: dict[str, int] = {}
        track_source_plan_records_total = 0
        for record in records:
            record_status_counts[record.status] = int(record_status_counts.get(record.status, 0)) + 1
            stage_key = record.stage or "unscoped"
            record_stage_counts[stage_key] = int(record_stage_counts.get(stage_key, 0)) + 1
            track_status_counts[record.status] = int(track_status_counts.get(record.status, 0)) + 1
            track_stage_counts[stage_key] = int(track_stage_counts.get(stage_key, 0)) + 1
            if record.source_plan_path is not None:
                source_plan_records_total += 1
                track_source_plan_records_total += 1
                source_plan_stage_counts[stage_key] = int(
                    source_plan_stage_counts.get(stage_key, 0)
                ) + 1

        latest_record = max(
            records,
            key=lambda record: (record.created_at, record.record_id),
            default=None,
        )
        latest_promotion = max(
            promotions,
            key=lambda promotion: (promotion.created_at, promotion.promotion_id),
            default=None,
        )
        track_iterations = [item for item in iterations if item.get("track_id") == track_id]

        track_items.append(
            {
                "track_id": track_id,
                "active": track_id == workspace.active_track_id,
                "status": track.status,
                "benchmark": track.benchmark,
                "kind": track.kind,
                "records_total": len(records),
                "source_plan_records_total": track_source_plan_records_total,
                "promotions_total": len(promotions),
                "iterations_total": len(track_iterations),
                "record_status_counts": track_status_counts,
                "record_stage_counts": track_stage_counts,
                "latest_record_id": latest_record.record_id if latest_record is not None else None,
                "latest_promotion_id": (
                    latest_promotion.promotion_id if latest_promotion is not None else None
                ),
                "champion_record_id": champion.record_id if champion is not None else None,
                "campaign_defaults": _render_campaign_default_snapshot(
                    track_campaign_policy
                ),
            }
        )

    return {
        "workspace_id": workspace.workspace_id,
        "workspace_path": str(workspace_config_path(root=root, workspace_id=workspace_id)),
        "objective": workspace.objective,
        "domain": workspace.domain,
        "status": state.status,
        "autonomy_mode": workspace.autonomy.mode,
        "active_track_id": workspace.active_track_id,
        "state": {
            "active_track_id": state.active_track_id,
            "next_iteration_index": state.next_iteration_index,
            "last_iteration_id": state.last_iteration_id,
            "last_experiment_id": state.last_experiment_id,
            "current_champion_experiment_id": state.current_champion_experiment_id,
            "summary": state.summary,
        },
        "active_track_effective_campaign_policy": _render_campaign_default_snapshot(
            active_track_campaign_policy
        ),
        "counts": {
            "tracks_total": len(workspace.tracks),
            "active_tracks_total": sum(1 for track in workspace.tracks.values() if track.status == "active"),
            "archived_tracks_total": sum(1 for track in workspace.tracks.values() if track.status == "archived"),
            "iterations_total": len(iterations),
            "records_total": total_records,
            "source_plan_records_total": source_plan_records_total,
            "promotions_total": total_promotions,
            "champion_tracks_total": champion_tracks,
        },
        "records": {
            "by_status": record_status_counts,
            "by_stage": record_stage_counts,
            "source_plan_by_stage": source_plan_stage_counts,
        },
        "tracks": track_items,
    }


def _render_workspace_view(*, root, workspace_id: str) -> dict[str, object]:
    workspace = load_workspace(root, workspace_id)
    state = load_workspace_state(root, workspace_id)
    active_track_policy = _resolved_track_policy_details(
        root=root,
        workspace=workspace,
        workspace_id=workspace_id,
        track_id=workspace.active_track_id,
    )
    active_track_campaign_policy = _resolved_track_campaign_policy_details(
        workspace=workspace,
        track_id=workspace.active_track_id,
    )
    rendered = workspace.to_dict()
    rendered["state"] = {
        "status": state.status,
        "active_track_id": state.active_track_id,
        "next_iteration_index": state.next_iteration_index,
        "last_iteration_id": state.last_iteration_id,
        "last_experiment_id": state.last_experiment_id,
        "current_champion_experiment_id": state.current_champion_experiment_id,
    }
    rendered["active_track_effective_policy"] = active_track_policy
    rendered["active_track_effective_campaign_policy"] = active_track_campaign_policy
    return rendered


def _resolve_bundle_manifest_path(path: Path) -> Path:
    if not path.exists():
        raise SystemExit(f"Bundle path not found: {path}")
    if path.is_file():
        return path

    candidates = (
        path / "bundle_manifest.json",
        path / "bundle_manifest.yaml",
        path / "bundle_manifest.yml",
        path / "champion.json",
        path / "champion.yaml",
        path / "champion.yml",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(f"Bundle manifest not found under: {path}")


def _find_structured_artifact(base_dir: Path, stem: str) -> Path | None:
    for suffix in (".json", ".yaml", ".yml"):
        candidate = base_dir / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _structured_format_for_path(path: Path) -> str:
    return "json" if path.suffix.lower() == ".json" else "yaml"


def _bundle_manifest_filename(bundle_type: str, format_name: str) -> str:
    stem = "champion" if bundle_type == "champion_bundle" else "bundle_manifest"
    suffix = ".json" if format_name == "json" else ".yaml"
    return f"{stem}{suffix}"


def _bundle_manifest_path(bundle_root: Path, bundle_type: str, format_name: str) -> Path:
    return bundle_root / _bundle_manifest_filename(bundle_type, format_name)


def _resolve_import_manifest_path(
    *,
    bundle_root: Path,
    bundle_type: str,
    default_manifest_path: Path,
    target_format: str | None,
) -> Path:
    if target_format is None:
        return default_manifest_path
    return _bundle_manifest_path(bundle_root, bundle_type, target_format)


def _paths_overlap_or_nested(a: Path, b: Path) -> bool:
    resolved_a = a.resolve()
    resolved_b = b.resolve()
    return (
        resolved_a == resolved_b
        or resolved_a in resolved_b.parents
        or resolved_b in resolved_a.parents
    )


def _copy_bundle_contents(src_root: Path, dst_root: Path) -> None:
    for child in src_root.iterdir():
        target = dst_root / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, target)


def _artifact_presence(bundle_root: Path, relative_path: str | None) -> dict[str, object] | None:
    if relative_path is None:
        return None
    artifact_path = bundle_root / relative_path
    return {
        "path": relative_path,
        "exists": artifact_path.exists(),
    }


def _render_bundle_view_from_payload(
    *,
    bundle_root: Path,
    manifest_path: Path,
    payload: dict[str, object],
    rendered_bundle_path: Path | None = None,
) -> dict[str, object]:
    format_version = payload.get("format_version")
    if not isinstance(format_version, str):
        raise SystemExit(f"Bundle manifest missing format_version: {manifest_path}")

    rendered = {
        "manifest_path": str(manifest_path),
        "bundle_path": str(rendered_bundle_path or bundle_root),
        "format_version": format_version,
    }

    if format_version == "autoharness.workspace_bundle.v1":
        artifacts = payload.get("artifacts")
        includes = payload.get("includes") or {}
        if not isinstance(artifacts, dict):
            raise SystemExit(f"Invalid workspace bundle manifest: {manifest_path}")
        track_reports = artifacts.get("track_reports") or []
        champion_bundles = artifacts.get("champion_bundles") or []
        assert isinstance(track_reports, list)
        assert isinstance(champion_bundles, list)

        artifact_status = {
            "workspace_report": _artifact_presence(
                bundle_root,
                artifacts.get("workspace_report_path"),
            ),
            "iterations": _artifact_presence(bundle_root, artifacts.get("iterations_path")),
            "records": _artifact_presence(bundle_root, artifacts.get("records_path")),
            "promotions": _artifact_presence(bundle_root, artifacts.get("promotions_path")),
            "track_reports": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                }
                for item in track_reports
                if isinstance(item, dict) and item.get("path") is not None
            ],
            "champion_bundles": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                }
                for item in champion_bundles
                if isinstance(item, dict) and item.get("path") is not None
            ],
        }
        missing_artifacts = []
        for key in ("workspace_report", "iterations", "records", "promotions"):
            item = artifact_status[key]
            if item is not None and not bool(item["exists"]):
                missing_artifacts.append(str(item["path"]))
        missing_artifacts.extend(
            str(item["path"]) for item in artifact_status["track_reports"] if not bool(item["exists"])
        )
        missing_artifacts.extend(
            str(item["path"])
            for item in artifact_status["champion_bundles"]
            if not bool(item["exists"])
        )
        return {
            **rendered,
            "bundle_type": "workspace_bundle",
            "workspace_id": payload.get("workspace_id"),
            "artifact_format": payload.get("artifact_format"),
            "includes": includes,
            "artifact_status": artifact_status,
            "track_reports_total": len(track_reports),
            "champion_bundles_total": len(champion_bundles),
            "missing_artifacts": missing_artifacts,
            "manifest": payload,
        }

    if format_version == "autoharness.track_bundle.v1":
        artifacts = payload.get("artifacts")
        includes = payload.get("includes") or {}
        if not isinstance(artifacts, dict):
            raise SystemExit(f"Invalid track bundle manifest: {manifest_path}")
        artifact_status = {
            "track_report": _artifact_presence(bundle_root, artifacts.get("track_report_path")),
            "iterations": _artifact_presence(bundle_root, artifacts.get("iterations_path")),
            "records": _artifact_presence(bundle_root, artifacts.get("records_path")),
            "promotions": _artifact_presence(bundle_root, artifacts.get("promotions_path")),
            "champion_bundle": (
                {
                    **artifacts["champion_bundle"],
                    "exists": (bundle_root / str(artifacts["champion_bundle"]["path"])).exists(),
                }
                if isinstance(artifacts.get("champion_bundle"), dict)
                and artifacts["champion_bundle"].get("path") is not None
                else None
            ),
        }
        missing_artifacts = []
        for key in ("track_report", "iterations", "records", "promotions"):
            item = artifact_status[key]
            if item is not None and not bool(item["exists"]):
                missing_artifacts.append(str(item["path"]))
        champion_bundle = artifact_status["champion_bundle"]
        if champion_bundle is not None and not bool(champion_bundle["exists"]):
            missing_artifacts.append(str(champion_bundle["path"]))
        return {
            **rendered,
            "bundle_type": "track_bundle",
            "workspace_id": payload.get("workspace_id"),
            "track_id": payload.get("track_id"),
            "artifact_format": payload.get("artifact_format"),
            "includes": includes,
            "artifact_status": artifact_status,
            "missing_artifacts": missing_artifacts,
            "manifest": payload,
        }

    if format_version == "autoharness.root_bundle.v1":
        artifacts = payload.get("artifacts")
        includes = payload.get("includes") or {}
        if not isinstance(artifacts, dict):
            raise SystemExit(f"Invalid root bundle manifest: {manifest_path}")
        workspace_bundles = artifacts.get("workspace_bundles") or []
        assert isinstance(workspace_bundles, list)
        artifact_status = {
            "root_report": _artifact_presence(
                bundle_root,
                artifacts.get("root_report_path"),
            ),
            "workspace_bundles": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                }
                for item in workspace_bundles
                if isinstance(item, dict) and item.get("path") is not None
            ],
        }
        missing_artifacts = []
        root_report = artifact_status["root_report"]
        if root_report is not None and not bool(root_report["exists"]):
            missing_artifacts.append(str(root_report["path"]))
        missing_artifacts.extend(
            str(item["path"])
            for item in artifact_status["workspace_bundles"]
            if not bool(item["exists"])
        )
        return {
            **rendered,
            "bundle_type": "root_bundle",
            "workspace_filter": payload.get("workspace_filter") or [],
            "artifact_format": payload.get("artifact_format"),
            "includes": includes,
            "artifact_status": artifact_status,
            "workspace_bundle_total": len(workspace_bundles),
            "missing_artifacts": missing_artifacts,
            "manifest": payload,
        }

    if format_version == "autoharness.workspace_campaign_bundle.v1":
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, dict):
            raise SystemExit(f"Invalid workspace campaign bundle manifest: {manifest_path}")
        campaign_bundles = artifacts.get("campaign_bundles") or []
        assert isinstance(campaign_bundles, list)
        artifact_status = {
            "workspace_campaign_report": _artifact_presence(
                bundle_root,
                artifacts.get("workspace_campaign_report_path"),
            ),
            "campaign_bundles": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                }
                for item in campaign_bundles
                if isinstance(item, dict) and item.get("path") is not None
            ],
        }
        missing_artifacts = []
        workspace_campaign_report = artifact_status["workspace_campaign_report"]
        if workspace_campaign_report is not None and not bool(workspace_campaign_report["exists"]):
            missing_artifacts.append(str(workspace_campaign_report["path"]))
        missing_artifacts.extend(
            str(item["path"])
            for item in artifact_status["campaign_bundles"]
            if not bool(item["exists"])
        )
        return {
            **rendered,
            "bundle_type": "workspace_campaign_bundle",
            "workspace_id": payload.get("workspace_id"),
            "track_filter": payload.get("track_filter") or [],
            "artifact_format": payload.get("artifact_format"),
            "artifact_status": artifact_status,
            "campaign_bundle_total": len(campaign_bundles),
            "missing_artifacts": missing_artifacts,
            "manifest": payload,
        }

    if format_version == "autoharness.root_campaign_bundle.v1":
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, dict):
            raise SystemExit(f"Invalid root campaign bundle manifest: {manifest_path}")
        workspace_bundles = artifacts.get("workspace_bundles") or []
        assert isinstance(workspace_bundles, list)
        artifact_status = {
            "root_campaign_report": _artifact_presence(
                bundle_root,
                artifacts.get("root_campaign_report_path"),
            ),
            "workspace_bundles": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                }
                for item in workspace_bundles
                if isinstance(item, dict) and item.get("path") is not None
            ],
        }
        missing_artifacts = []
        root_campaign_report = artifact_status["root_campaign_report"]
        if root_campaign_report is not None and not bool(root_campaign_report["exists"]):
            missing_artifacts.append(str(root_campaign_report["path"]))
        missing_artifacts.extend(
            str(item["path"])
            for item in artifact_status["workspace_bundles"]
            if not bool(item["exists"])
        )
        return {
            **rendered,
            "bundle_type": "root_campaign_bundle",
            "workspace_filter": payload.get("workspace_filter") or [],
            "track_filter": payload.get("track_filter") or [],
            "artifact_format": payload.get("artifact_format"),
            "artifact_status": artifact_status,
            "workspace_bundle_total": len(workspace_bundles),
            "missing_artifacts": missing_artifacts,
            "manifest": payload,
        }

    if format_version == "autoharness.campaign_bundle.v1":
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, dict):
            raise SystemExit(f"Invalid campaign bundle manifest: {manifest_path}")
        proposal_dirs = artifacts.get("proposal_dirs") or []
        record_paths = artifacts.get("record_paths") or []
        iteration_dirs = artifacts.get("iteration_dirs") or []
        promotion_artifacts = artifacts.get("promotion_artifacts") or []
        assert isinstance(proposal_dirs, list)
        assert isinstance(record_paths, list)
        assert isinstance(iteration_dirs, list)
        assert isinstance(promotion_artifacts, list)
        artifact_status = {
            "campaign": _artifact_presence(bundle_root, artifacts.get("campaign_path")),
            "campaign_report": _artifact_presence(
                bundle_root,
                artifacts.get("campaign_report_path"),
            ),
            "proposal_dirs": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                }
                for item in proposal_dirs
                if isinstance(item, dict) and item.get("path") is not None
            ],
            "record_paths": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                }
                for item in record_paths
                if isinstance(item, dict) and item.get("path") is not None
            ],
            "iteration_dirs": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                }
                for item in iteration_dirs
                if isinstance(item, dict) and item.get("path") is not None
            ],
            "promotion_artifacts": [
                {
                    **item,
                    "exists": (bundle_root / str(item["path"])).exists(),
                    "diff_exists": (
                        (bundle_root / str(item["diff_path"])).exists()
                        if item.get("diff_path") is not None
                        else None
                    ),
                }
                for item in promotion_artifacts
                if isinstance(item, dict) and item.get("path") is not None
            ],
            "champion_bundle": (
                {
                    **artifacts["champion_bundle"],
                    "exists": (bundle_root / str(artifacts["champion_bundle"]["path"])).exists(),
                }
                if isinstance(artifacts.get("champion_bundle"), dict)
                and artifacts["champion_bundle"].get("path") is not None
                else None
            ),
        }
        missing_artifacts = []
        for key in ("campaign", "campaign_report"):
            item = artifact_status[key]
            if item is not None and not bool(item["exists"]):
                missing_artifacts.append(str(item["path"]))
        for key in ("proposal_dirs", "record_paths", "iteration_dirs"):
            missing_artifacts.extend(
                str(item["path"]) for item in artifact_status[key] if not bool(item["exists"])
            )
        for item in artifact_status["promotion_artifacts"]:
            if not bool(item["exists"]):
                missing_artifacts.append(str(item["path"]))
            if item.get("diff_path") is not None and item.get("diff_exists") is False:
                missing_artifacts.append(str(item["diff_path"]))
        champion_bundle = artifact_status["champion_bundle"]
        if champion_bundle is not None and not bool(champion_bundle["exists"]):
            missing_artifacts.append(str(champion_bundle["path"]))
        return {
            **rendered,
            "bundle_type": "campaign_bundle",
            "workspace_id": payload.get("workspace_id"),
            "track_id": payload.get("track_id"),
            "campaign_id": payload.get("campaign_id"),
            "artifact_format": payload.get("artifact_format"),
            "artifact_status": artifact_status,
            "proposal_total": len(proposal_dirs),
            "record_total": len(record_paths),
            "iteration_total": len(iteration_dirs),
            "promotion_total": len(promotion_artifacts),
            "missing_artifacts": missing_artifacts,
            "manifest": payload,
        }

    if format_version == "autoharness.champion_export.v1":
        bundle_artifacts = payload.get("bundle_artifacts")
        if not isinstance(bundle_artifacts, dict):
            raise SystemExit(f"Invalid champion bundle manifest: {manifest_path}")
        artifact_status = {
            key: _artifact_presence(bundle_root, value if isinstance(value, str) else None)
            for key, value in bundle_artifacts.items()
        }
        missing_artifacts = [
            str(item["path"])
            for item in artifact_status.values()
            if item is not None and not bool(item["exists"])
        ]
        return {
            **rendered,
            "bundle_type": "champion_bundle",
            "workspace_id": payload.get("workspace_id"),
            "track_id": payload.get("track_id"),
            "record_id": payload.get("record_id"),
            "promotion_id": payload.get("promotion_id"),
            "stage": payload.get("stage"),
            "status": payload.get("status"),
            "artifact_status": artifact_status,
            "missing_artifacts": missing_artifacts,
            "manifest": payload,
        }

    raise SystemExit(
        f"Unsupported bundle manifest format_version `{format_version}`: {manifest_path}"
    )


def _render_bundle_view(path: Path) -> dict[str, object]:
    manifest_path = _resolve_bundle_manifest_path(path)
    payload = _load_structured_file(manifest_path)
    return _render_bundle_view_from_payload(
        bundle_root=manifest_path.parent,
        manifest_path=manifest_path,
        payload=payload,
    )


def _augment_bundle_view_with_nested(
    rendered: dict[str, object],
    *,
    recursive: bool,
) -> dict[str, object]:
    if not recursive:
        return {
            **rendered,
            "recursive": False,
            "nested_bundles": [],
            "nested_bundle_total": 0,
            "nested_error_count": 0,
        }

    bundle_root = Path(str(rendered["bundle_path"]))
    bundle_type = str(rendered["bundle_type"])
    nested_bundles = []
    nested_error_count = 0
    for nested_dir in _nested_bundle_directories(bundle_root, bundle_type):
        nested_rendered = _render_nested_bundle_validation(nested_dir, recursive=True)
        nested_errors = nested_rendered["validation_errors"]
        assert isinstance(nested_errors, list)
        nested_error_count += len(nested_errors)
        nested_bundles.append(
            {
                "path": str(nested_dir.relative_to(bundle_root)),
                **nested_rendered,
            }
        )
    return {
        **rendered,
        "recursive": True,
        "nested_bundles": nested_bundles,
        "nested_bundle_total": len(nested_bundles),
        "nested_error_count": nested_error_count,
    }


def _bundle_validation_from_view(rendered: dict[str, object]) -> dict[str, object]:
    missing_artifacts = rendered["missing_artifacts"]
    assert isinstance(missing_artifacts, list)
    validation_errors = [f"Missing artifact: {item}" for item in missing_artifacts]
    return {
        **rendered,
        "valid": not validation_errors,
        "error_count": len(validation_errors),
        "validation_errors": validation_errors,
    }


def _nested_bundle_directories(bundle_root: Path, bundle_type: str) -> list[Path]:
    if bundle_type == "root_bundle":
        workspaces_dir = bundle_root / "workspaces"
        if not workspaces_dir.exists():
            return []
        return sorted(path for path in workspaces_dir.iterdir() if path.is_dir())
    if bundle_type == "workspace_bundle":
        champions_dir = bundle_root / "champions"
        if not champions_dir.exists():
            return []
        return sorted(path for path in champions_dir.iterdir() if path.is_dir())
    if bundle_type == "workspace_campaign_bundle":
        campaigns_dir = bundle_root / "campaigns"
        if not campaigns_dir.exists():
            return []
        nested_dirs = []
        for track_dir in sorted(path for path in campaigns_dir.iterdir() if path.is_dir()):
            nested_dirs.extend(
                sorted(path for path in track_dir.iterdir() if path.is_dir())
            )
        return nested_dirs
    if bundle_type == "track_bundle":
        champion_dir = bundle_root / "champion"
        if champion_dir.exists() and champion_dir.is_dir():
            return [champion_dir]
    if bundle_type == "root_campaign_bundle":
        workspaces_dir = bundle_root / "workspaces"
        if not workspaces_dir.exists():
            return []
        return sorted(path for path in workspaces_dir.iterdir() if path.is_dir())
    if bundle_type == "campaign_bundle":
        champion_dir = bundle_root / "champion"
        if champion_dir.exists() and champion_dir.is_dir():
            return [champion_dir]
    return []


def _render_nested_bundle_validation(
    path: Path,
    *,
    recursive: bool,
) -> dict[str, object]:
    try:
        return _render_bundle_validation(path, recursive=recursive)
    except SystemExit as exc:
        try:
            bundle_root, manifest_path, _payload, bundle_type = _probe_bundle_reindex_target(path)
        except SystemExit:
            bundle_root = path if path.is_dir() else path.parent
            manifest_path = path if path.is_file() else None
            bundle_type = "unknown"
        validation_errors = [str(exc)]
        return {
            "bundle_type": bundle_type,
            "bundle_path": str(bundle_root),
            "manifest_path": str(manifest_path) if manifest_path is not None else None,
            "format_version": None,
            "missing_artifacts": [],
            "recursive": recursive,
            "nested_bundles": [],
            "nested_bundle_total": 0,
            "nested_error_count": 0,
            "valid": False,
            "error_count": len(validation_errors),
            "validation_errors": validation_errors,
        }


def _augment_bundle_validation_with_nested(
    validation: dict[str, object],
    *,
    recursive: bool,
) -> dict[str, object]:
    if not recursive:
        return {
            **validation,
            "recursive": False,
            "nested_bundles": [],
            "nested_bundle_total": 0,
            "nested_error_count": 0,
        }

    bundle_root = Path(str(validation["bundle_path"]))
    bundle_type = str(validation["bundle_type"])
    nested_bundles = []
    nested_validation_errors = []
    for nested_dir in _nested_bundle_directories(bundle_root, bundle_type):
        nested_validation = _render_nested_bundle_validation(nested_dir, recursive=True)
        nested_path = str(nested_dir.relative_to(bundle_root))
        nested_bundles.append(
            {
                "path": nested_path,
                **nested_validation,
            }
        )
        nested_errors = nested_validation["validation_errors"]
        assert isinstance(nested_errors, list)
        for error in nested_errors:
            nested_validation_errors.append(f"Nested bundle {nested_path}: {error}")

    validation_errors = validation["validation_errors"]
    assert isinstance(validation_errors, list)
    merged_validation_errors = [*validation_errors, *nested_validation_errors]
    return {
        **validation,
        "recursive": True,
        "nested_bundles": nested_bundles,
        "nested_bundle_total": len(nested_bundles),
        "nested_error_count": len(nested_validation_errors),
        "valid": not merged_validation_errors,
        "error_count": len(merged_validation_errors),
        "validation_errors": merged_validation_errors,
    }


def _merge_validation_with_nested_bundles(
    validation: dict[str, object],
    *,
    recursive: bool,
    nested_bundles: list[dict[str, object]],
) -> dict[str, object]:
    if not recursive:
        return {
            **validation,
            "recursive": False,
            "nested_bundles": [],
            "nested_bundle_total": 0,
            "nested_error_count": 0,
        }

    merged_validation_errors = list(validation["validation_errors"])
    nested_error_count = 0
    for nested_bundle in nested_bundles:
        nested_errors = nested_bundle["validation_errors"]
        assert isinstance(nested_errors, list)
        nested_path = str(nested_bundle["path"])
        for error in nested_errors:
            merged_validation_errors.append(f"Nested bundle {nested_path}: {error}")
            nested_error_count += 1

    return {
        **validation,
        "recursive": True,
        "nested_bundles": nested_bundles,
        "nested_bundle_total": len(nested_bundles),
        "nested_error_count": nested_error_count,
        "valid": not merged_validation_errors,
        "error_count": len(merged_validation_errors),
        "validation_errors": merged_validation_errors,
    }


def _relocate_bundle_validation(
    validation: dict[str, object],
    *,
    source_bundle_root: Path,
    rendered_bundle_root: Path,
) -> dict[str, object]:
    def relocate_path(value: object) -> object:
        if value is None:
            return None
        text = str(value)
        source_root_text = str(source_bundle_root)
        if text == source_root_text:
            return str(rendered_bundle_root)
        if text.startswith(source_root_text + "/"):
            return str(rendered_bundle_root / text[len(source_root_text) + 1 :])
        return value

    relocated = {
        **validation,
        "bundle_path": str(rendered_bundle_root),
        "manifest_path": relocate_path(validation.get("manifest_path")),
        "validation_errors": [
            str(error).replace(str(source_bundle_root), str(rendered_bundle_root))
            for error in validation["validation_errors"]
        ],
    }
    nested_bundles = validation.get("nested_bundles")
    if isinstance(nested_bundles, list):
        relocated["nested_bundles"] = [
            _relocate_bundle_validation(
                nested_bundle,
                source_bundle_root=source_bundle_root / str(nested_bundle["path"]),
                rendered_bundle_root=rendered_bundle_root / str(nested_bundle["path"]),
            )
            for nested_bundle in nested_bundles
        ]
    return relocated


def _predict_nested_bundle_validations(
    *,
    source_bundle_root: Path,
    rendered_bundle_root: Path,
    bundle_type: str,
    recursive: bool,
    target_format: str | None,
    reindex_nested: bool,
) -> list[dict[str, object]]:
    if not recursive:
        return []

    nested_bundles = []
    for source_nested_dir in _nested_bundle_directories(source_bundle_root, bundle_type):
        rendered_nested_dir = rendered_bundle_root / source_nested_dir.relative_to(source_bundle_root)
        if reindex_nested:
            (
                predicted_manifest,
                _bundle_root,
                default_manifest_path,
                nested_bundle_type,
                manifest_existed,
                artifact_format,
            ) = _reindex_bundle_manifest(source_nested_dir)
            predicted_manifest_path = _resolve_import_manifest_path(
                bundle_root=rendered_nested_dir,
                bundle_type=nested_bundle_type,
                default_manifest_path=rendered_nested_dir / default_manifest_path.name,
                target_format=target_format,
            )
            predicted_validation = _bundle_validation_from_view(
                _render_bundle_view_from_payload(
                    bundle_root=source_nested_dir,
                    manifest_path=predicted_manifest_path,
                    payload=predicted_manifest,
                    rendered_bundle_path=rendered_nested_dir,
                )
            )
            nested_bundles.append(
                {
                    "path": str(source_nested_dir.relative_to(source_bundle_root)),
                    "manifest_existed": manifest_existed,
                    "artifact_format": artifact_format,
                    "target_format": target_format,
                    **predicted_validation,
                }
            )
            continue

        nested_validation = _render_nested_bundle_validation(source_nested_dir, recursive=True)
        nested_bundles.append(
            {
                "path": str(source_nested_dir.relative_to(source_bundle_root)),
                **_relocate_bundle_validation(
                    nested_validation,
                    source_bundle_root=source_nested_dir,
                    rendered_bundle_root=rendered_nested_dir,
                ),
            }
        )
    return nested_bundles


def _probe_bundle_reindex_target(
    path: Path,
) -> tuple[Path, Path | None, dict[str, object] | None, str]:
    if not path.exists():
        raise SystemExit(f"Bundle path not found: {path}")

    if path.is_file():
        payload = _load_structured_file(path)
        format_version = payload.get("format_version")
        if format_version == "autoharness.root_bundle.v1":
            return path.parent, path, payload, "root_bundle"
        if format_version == "autoharness.workspace_bundle.v1":
            return path.parent, path, payload, "workspace_bundle"
        if format_version == "autoharness.track_bundle.v1":
            return path.parent, path, payload, "track_bundle"
        if format_version == "autoharness.workspace_campaign_bundle.v1":
            return path.parent, path, payload, "workspace_campaign_bundle"
        if format_version == "autoharness.root_campaign_bundle.v1":
            return path.parent, path, payload, "root_campaign_bundle"
        if format_version == "autoharness.campaign_bundle.v1":
            return path.parent, path, payload, "campaign_bundle"
        if format_version == "autoharness.champion_export.v1":
            return path.parent, path, payload, "champion_bundle"
        raise SystemExit(f"Unsupported bundle manifest format_version `{format_version}`: {path}")

    bundle_root = path
    manifest_path = None
    manifest_payload = None
    for candidate_name in (
        "bundle_manifest.json",
        "bundle_manifest.yaml",
        "bundle_manifest.yml",
        "champion.json",
        "champion.yaml",
        "champion.yml",
    ):
        candidate = bundle_root / candidate_name
        if candidate.exists():
            payload = _load_structured_file(candidate)
            format_version = payload.get("format_version")
            if format_version == "autoharness.root_bundle.v1":
                return bundle_root, candidate, payload, "root_bundle"
            if format_version == "autoharness.workspace_bundle.v1":
                return bundle_root, candidate, payload, "workspace_bundle"
            if format_version == "autoharness.track_bundle.v1":
                return bundle_root, candidate, payload, "track_bundle"
            if format_version == "autoharness.workspace_campaign_bundle.v1":
                return bundle_root, candidate, payload, "workspace_campaign_bundle"
            if format_version == "autoharness.root_campaign_bundle.v1":
                return bundle_root, candidate, payload, "root_campaign_bundle"
            if format_version == "autoharness.campaign_bundle.v1":
                return bundle_root, candidate, payload, "campaign_bundle"
            if format_version == "autoharness.champion_export.v1":
                return bundle_root, candidate, payload, "champion_bundle"
            manifest_path = candidate
            manifest_payload = payload
            break

    if _find_structured_artifact(bundle_root, "root_report") is not None:
        return bundle_root, manifest_path, manifest_payload, "root_bundle"
    if _find_structured_artifact(bundle_root, "workspace_report") is not None:
        return bundle_root, manifest_path, manifest_payload, "workspace_bundle"
    if _find_structured_artifact(bundle_root, "track_report") is not None:
        return bundle_root, manifest_path, manifest_payload, "track_bundle"
    if _find_structured_artifact(bundle_root, "workspace_campaign_report") is not None:
        return bundle_root, manifest_path, manifest_payload, "workspace_campaign_bundle"
    if _find_structured_artifact(bundle_root, "root_campaign_report") is not None:
        return bundle_root, manifest_path, manifest_payload, "root_campaign_bundle"
    if _find_structured_artifact(bundle_root, "campaign_report") is not None:
        return bundle_root, manifest_path, manifest_payload, "campaign_bundle"
    if (bundle_root / "source_champion.json").exists():
        return bundle_root, manifest_path, manifest_payload, "champion_bundle"
    raise SystemExit(f"Could not infer bundle type under: {bundle_root}")


def _build_workspace_bundle_manifest(
    *,
    bundle_root: Path,
    existing_manifest: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    workspace_report_path = _find_structured_artifact(bundle_root, "workspace_report")
    if workspace_report_path is None:
        raise SystemExit(f"Workspace bundle missing workspace report: {bundle_root}")
    workspace_report = _load_structured_file(workspace_report_path)
    workspace = workspace_report.get("workspace")
    if not isinstance(workspace, dict):
        raise SystemExit(f"Invalid workspace report in bundle: {workspace_report_path}")
    workspace_id = str(workspace["workspace_id"])
    artifact_format = _structured_format_for_path(workspace_report_path)

    iterations_path = _find_structured_artifact(bundle_root / "listings", "iterations")
    records_path = _find_structured_artifact(bundle_root / "listings", "records")
    promotions_path = _find_structured_artifact(bundle_root / "listings", "promotions")

    track_reports = []
    tracks_dir = bundle_root / "tracks"
    if tracks_dir.exists():
        for track_dir in sorted(path for path in tracks_dir.iterdir() if path.is_dir()):
            report_path = _find_structured_artifact(track_dir, "report")
            if report_path is None:
                continue
            track_report = _load_structured_file(report_path)
            track = track_report.get("track")
            track_id = (
                str(track["track_id"])
                if isinstance(track, dict) and track.get("track_id") is not None
                else track_dir.name
            )
            track_reports.append(
                {
                    "track_id": track_id,
                    "path": str(report_path.relative_to(bundle_root)),
                }
            )

    champion_bundles = []
    champions_dir = bundle_root / "champions"
    if champions_dir.exists():
        for champion_dir in sorted(path for path in champions_dir.iterdir() if path.is_dir()):
            try:
                _nested_bundle_root, _nested_manifest_path, champion_manifest, nested_bundle_type = (
                    _probe_bundle_reindex_target(champion_dir)
                )
            except SystemExit:
                continue
            if nested_bundle_type != "champion_bundle":
                continue
            if champion_manifest is None:
                champion_manifest, _ = _build_champion_bundle_manifest(
                    bundle_root=champion_dir,
                    existing_manifest=None,
                )
            champion_bundles.append(
                {
                    "track_id": str(champion_manifest.get("track_id") or champion_dir.name),
                    "path": str(champion_dir.relative_to(bundle_root)),
                    "record_id": champion_manifest.get("record_id"),
                    "promotion_id": champion_manifest.get("promotion_id"),
                }
            )

    exported_at = (
        str(existing_manifest["exported_at"])
        if isinstance(existing_manifest, dict) and existing_manifest.get("exported_at") is not None
        else _utc_now()
    )
    manifest = {
        "format_version": "autoharness.workspace_bundle.v1",
        "exported_at": exported_at,
        "reindexed_at": _utc_now(),
        "workspace_id": workspace_id,
        "artifact_format": artifact_format,
        "includes": {
            "listings": any(
                item is not None for item in (iterations_path, records_path, promotions_path)
            ),
            "track_reports": bool(track_reports),
            "champion_bundles": bool(champion_bundles),
        },
        "artifacts": {
            "workspace_report_path": str(workspace_report_path.relative_to(bundle_root)),
            "iterations_path": (
                str(iterations_path.relative_to(bundle_root)) if iterations_path is not None else None
            ),
            "records_path": (
                str(records_path.relative_to(bundle_root)) if records_path is not None else None
            ),
            "promotions_path": (
                str(promotions_path.relative_to(bundle_root)) if promotions_path is not None else None
            ),
            "track_reports": track_reports,
            "champion_bundles": champion_bundles,
        },
    }
    return manifest, artifact_format


def _build_track_bundle_manifest(
    *,
    bundle_root: Path,
    existing_manifest: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    track_report_path = _find_structured_artifact(bundle_root, "track_report")
    if track_report_path is None:
        raise SystemExit(f"Track bundle missing track report: {bundle_root}")
    track_report = _load_structured_file(track_report_path)
    track = track_report.get("track")
    if not isinstance(track, dict):
        raise SystemExit(f"Invalid track report in bundle: {track_report_path}")
    workspace_id = str(track["workspace_id"])
    track_id = str(track["track_id"])
    artifact_format = _structured_format_for_path(track_report_path)

    iterations_path = _find_structured_artifact(bundle_root / "listings", "iterations")
    records_path = _find_structured_artifact(bundle_root / "listings", "records")
    promotions_path = _find_structured_artifact(bundle_root / "listings", "promotions")

    champion_bundle = None
    champion_dir = bundle_root / "champion"
    if champion_dir.exists() and champion_dir.is_dir():
        try:
            _nested_bundle_root, _nested_manifest_path, champion_manifest, nested_bundle_type = (
                _probe_bundle_reindex_target(champion_dir)
            )
        except SystemExit:
            champion_manifest = None
            nested_bundle_type = None
        if nested_bundle_type == "champion_bundle" and champion_manifest is None:
            champion_manifest, _ = _build_champion_bundle_manifest(
                bundle_root=champion_dir,
                existing_manifest=None,
            )
        if nested_bundle_type == "champion_bundle" and champion_manifest is not None:
            champion_bundle = {
                "path": "champion",
                "record_id": champion_manifest.get("record_id"),
                "promotion_id": champion_manifest.get("promotion_id"),
            }

    exported_at = (
        str(existing_manifest["exported_at"])
        if isinstance(existing_manifest, dict) and existing_manifest.get("exported_at") is not None
        else _utc_now()
    )
    manifest = {
        "format_version": "autoharness.track_bundle.v1",
        "exported_at": exported_at,
        "reindexed_at": _utc_now(),
        "workspace_id": workspace_id,
        "track_id": track_id,
        "artifact_format": artifact_format,
        "includes": {
            "listings": any(
                item is not None for item in (iterations_path, records_path, promotions_path)
            ),
            "champion_bundle": champion_bundle is not None,
        },
        "artifacts": {
            "track_report_path": str(track_report_path.relative_to(bundle_root)),
            "iterations_path": (
                str(iterations_path.relative_to(bundle_root)) if iterations_path is not None else None
            ),
            "records_path": (
                str(records_path.relative_to(bundle_root)) if records_path is not None else None
            ),
            "promotions_path": (
                str(promotions_path.relative_to(bundle_root)) if promotions_path is not None else None
            ),
            "champion_bundle": champion_bundle,
        },
    }
    return manifest, artifact_format


def _build_root_bundle_manifest(
    *,
    bundle_root: Path,
    existing_manifest: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    root_report_path = _find_structured_artifact(bundle_root, "root_report")
    if root_report_path is None:
        raise SystemExit(f"Root bundle missing root report: {bundle_root}")
    root_report = _load_structured_file(root_report_path)
    workspace_filter = root_report.get("workspace_filter")
    if not isinstance(workspace_filter, list):
        workspace_filter = []
    artifact_format = _structured_format_for_path(root_report_path)

    workspace_bundles = []
    include_listings = False
    include_track_reports = False
    include_champion_bundles = False
    workspaces_dir = bundle_root / "workspaces"
    if workspaces_dir.exists():
        for workspace_dir in sorted(path for path in workspaces_dir.iterdir() if path.is_dir()):
            try:
                (
                    _nested_bundle_root,
                    _nested_manifest_path,
                    workspace_manifest,
                    nested_bundle_type,
                ) = _probe_bundle_reindex_target(workspace_dir)
            except SystemExit:
                continue
            if nested_bundle_type != "workspace_bundle":
                continue
            if workspace_manifest is None:
                workspace_manifest, _ = _build_workspace_bundle_manifest(
                    bundle_root=workspace_dir,
                    existing_manifest=None,
                )
            includes = workspace_manifest.get("includes")
            if isinstance(includes, dict):
                include_listings = include_listings or bool(includes.get("listings"))
                include_track_reports = include_track_reports or bool(
                    includes.get("track_reports")
                )
                include_champion_bundles = include_champion_bundles or bool(
                    includes.get("champion_bundles")
                )
            artifacts = workspace_manifest.get("artifacts")
            track_reports = artifacts.get("track_reports") if isinstance(artifacts, dict) else []
            champion_bundles = (
                artifacts.get("champion_bundles") if isinstance(artifacts, dict) else []
            )
            workspace_bundles.append(
                {
                    "workspace_id": str(
                        workspace_manifest.get("workspace_id") or workspace_dir.name
                    ),
                    "path": str(workspace_dir.relative_to(bundle_root)),
                    "track_report_total": len(track_reports)
                    if isinstance(track_reports, list)
                    else 0,
                    "champion_bundle_total": len(champion_bundles)
                    if isinstance(champion_bundles, list)
                    else 0,
                }
            )

    exported_at = (
        str(existing_manifest["exported_at"])
        if isinstance(existing_manifest, dict) and existing_manifest.get("exported_at") is not None
        else _utc_now()
    )
    manifest = {
        "format_version": "autoharness.root_bundle.v1",
        "exported_at": exported_at,
        "reindexed_at": _utc_now(),
        "workspace_filter": workspace_filter,
        "artifact_format": artifact_format,
        "includes": {
            "workspace_bundles": bool(workspace_bundles),
            "listings": include_listings,
            "track_reports": include_track_reports,
            "champion_bundles": include_champion_bundles,
        },
        "artifacts": {
            "root_report_path": str(root_report_path.relative_to(bundle_root)),
            "workspace_bundles": workspace_bundles,
        },
    }
    return manifest, artifact_format


def _build_workspace_campaign_bundle_manifest(
    *,
    bundle_root: Path,
    existing_manifest: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    workspace_campaign_report_path = _find_structured_artifact(
        bundle_root, "workspace_campaign_report"
    )
    if workspace_campaign_report_path is None:
        raise SystemExit(
            f"Workspace campaign bundle missing workspace campaign report: {bundle_root}"
        )
    workspace_campaign_report = _load_structured_file(workspace_campaign_report_path)
    workspace_id = str(workspace_campaign_report.get("workspace_id"))
    track_filter = workspace_campaign_report.get("track_filter")
    if not isinstance(track_filter, list):
        track_filter = []
    artifact_format = _structured_format_for_path(workspace_campaign_report_path)

    campaign_bundles = []
    campaigns_dir = bundle_root / "campaigns"
    if campaigns_dir.exists():
        for track_dir in sorted(path for path in campaigns_dir.iterdir() if path.is_dir()):
            for campaign_dir in sorted(path for path in track_dir.iterdir() if path.is_dir()):
                try:
                    (
                        _nested_bundle_root,
                        _nested_manifest_path,
                        campaign_manifest,
                        nested_bundle_type,
                    ) = _probe_bundle_reindex_target(campaign_dir)
                except SystemExit:
                    continue
                if nested_bundle_type != "campaign_bundle":
                    continue
                if campaign_manifest is None:
                    campaign_manifest, _ = _build_campaign_bundle_manifest(
                        bundle_root=campaign_dir,
                        existing_manifest=None,
                    )
                campaign_bundles.append(
                    {
                        "track_id": str(campaign_manifest.get("track_id") or track_dir.name),
                        "campaign_id": str(
                            campaign_manifest.get("campaign_id") or campaign_dir.name
                        ),
                        "path": str(campaign_dir.relative_to(bundle_root)),
                    }
                )

    exported_at = (
        str(existing_manifest["exported_at"])
        if isinstance(existing_manifest, dict) and existing_manifest.get("exported_at") is not None
        else _utc_now()
    )
    manifest = {
        "format_version": "autoharness.workspace_campaign_bundle.v1",
        "exported_at": exported_at,
        "reindexed_at": _utc_now(),
        "workspace_id": workspace_id,
        "track_filter": track_filter,
        "artifact_format": artifact_format,
        "artifacts": {
            "workspace_campaign_report_path": str(
                workspace_campaign_report_path.relative_to(bundle_root)
            ),
            "campaign_bundles": campaign_bundles,
        },
    }
    return manifest, artifact_format


def _build_root_campaign_bundle_manifest(
    *,
    bundle_root: Path,
    existing_manifest: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    root_campaign_report_path = _find_structured_artifact(bundle_root, "root_campaign_report")
    if root_campaign_report_path is None:
        raise SystemExit(f"Root campaign bundle missing root campaign report: {bundle_root}")
    root_campaign_report = _load_structured_file(root_campaign_report_path)
    workspace_filter = root_campaign_report.get("workspace_filter")
    if not isinstance(workspace_filter, list):
        workspace_filter = []
    track_filter = root_campaign_report.get("track_filter")
    if not isinstance(track_filter, list):
        track_filter = []
    artifact_format = _structured_format_for_path(root_campaign_report_path)

    workspace_bundles = []
    workspaces_dir = bundle_root / "workspaces"
    if workspaces_dir.exists():
        for workspace_dir in sorted(path for path in workspaces_dir.iterdir() if path.is_dir()):
            try:
                (
                    _nested_bundle_root,
                    _nested_manifest_path,
                    workspace_manifest,
                    nested_bundle_type,
                ) = _probe_bundle_reindex_target(workspace_dir)
            except SystemExit:
                continue
            if nested_bundle_type != "workspace_campaign_bundle":
                continue
            if workspace_manifest is None:
                workspace_manifest, _ = _build_workspace_campaign_bundle_manifest(
                    bundle_root=workspace_dir,
                    existing_manifest=None,
                )
            artifacts = workspace_manifest.get("artifacts")
            campaign_bundles = (
                artifacts.get("campaign_bundles")
                if isinstance(artifacts, dict)
                else []
            )
            workspace_bundles.append(
                {
                    "workspace_id": str(
                        workspace_manifest.get("workspace_id") or workspace_dir.name
                    ),
                    "path": str(workspace_dir.relative_to(bundle_root)),
                    "campaign_total": len(campaign_bundles)
                    if isinstance(campaign_bundles, list)
                    else 0,
                }
            )

    exported_at = (
        str(existing_manifest["exported_at"])
        if isinstance(existing_manifest, dict) and existing_manifest.get("exported_at") is not None
        else _utc_now()
    )
    manifest = {
        "format_version": "autoharness.root_campaign_bundle.v1",
        "exported_at": exported_at,
        "reindexed_at": _utc_now(),
        "workspace_filter": workspace_filter,
        "track_filter": track_filter,
        "artifact_format": artifact_format,
        "artifacts": {
            "root_campaign_report_path": str(root_campaign_report_path.relative_to(bundle_root)),
            "workspace_bundles": workspace_bundles,
        },
    }
    return manifest, artifact_format


def _build_campaign_bundle_manifest(
    *,
    bundle_root: Path,
    existing_manifest: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    campaign_report_path = _find_structured_artifact(bundle_root, "campaign_report")
    if campaign_report_path is None:
        raise SystemExit(f"Campaign bundle missing campaign report: {bundle_root}")
    campaign_report = _load_structured_file(campaign_report_path)
    campaign_payload = campaign_report.get("campaign")
    if not isinstance(campaign_payload, dict):
        raise SystemExit(f"Invalid campaign report in bundle: {campaign_report_path}")
    workspace_id = str(campaign_report.get("workspace_id") or campaign_payload["workspace_id"])
    track_id = str(campaign_report.get("track_id") or campaign_payload["track_id"])
    campaign_id = str(campaign_payload["campaign_run_id"])
    artifact_format = _structured_format_for_path(campaign_report_path)

    campaign_path = _find_structured_artifact(bundle_root, "campaign")
    proposal_dirs = []
    proposals_dir = bundle_root / "proposals"
    if proposals_dir.exists():
        for proposal_dir in sorted(path for path in proposals_dir.iterdir() if path.is_dir()):
            if (proposal_dir / "proposal.json").exists():
                proposal_manifest = _load_structured_file(proposal_dir / "proposal.json")
                proposal_dirs.append(
                    {
                        "proposal_id": proposal_manifest.get("proposal_id", proposal_dir.name),
                        "path": str(proposal_dir.relative_to(bundle_root)),
                    }
                )

    record_paths = []
    records_dir = bundle_root / "records"
    if records_dir.exists():
        for record_path in sorted(records_dir.glob("*.json")):
            record_payload = _load_structured_file(record_path)
            record_paths.append(
                {
                    "record_id": record_payload.get("record_id", record_path.stem),
                    "path": str(record_path.relative_to(bundle_root)),
                }
            )

    iteration_dirs = []
    iterations_dir = bundle_root / "iterations"
    if iterations_dir.exists():
        for iteration_dir in sorted(path for path in iterations_dir.iterdir() if path.is_dir()):
            summary_path = iteration_dir / "summary.json"
            if not summary_path.exists():
                continue
            summary_payload = _load_structured_file(summary_path)
            iteration_dirs.append(
                {
                    "iteration_id": summary_payload.get("iteration_id", iteration_dir.name),
                    "path": str(iteration_dir.relative_to(bundle_root)),
                }
            )

    promotion_artifacts = []
    promotions_dir = bundle_root / "promotions"
    if promotions_dir.exists():
        for promotion_path in sorted(promotions_dir.glob("*.json")):
            promotion_payload = _load_structured_file(promotion_path)
            diff_path = promotion_path.with_suffix(".patch")
            promotion_artifacts.append(
                {
                    "promotion_id": promotion_payload.get("promotion_id", promotion_path.stem),
                    "path": str(promotion_path.relative_to(bundle_root)),
                    "diff_path": (
                        str(diff_path.relative_to(bundle_root)) if diff_path.exists() else None
                    ),
                }
            )

    champion_bundle = None
    champion_dir = bundle_root / "champion"
    if champion_dir.exists() and champion_dir.is_dir():
        try:
            _nested_bundle_root, _nested_manifest_path, champion_manifest, nested_bundle_type = (
                _probe_bundle_reindex_target(champion_dir)
            )
        except SystemExit:
            champion_manifest = None
            nested_bundle_type = None
        if nested_bundle_type == "champion_bundle" and champion_manifest is None:
            champion_manifest, _ = _build_champion_bundle_manifest(
                bundle_root=champion_dir,
                existing_manifest=None,
            )
        if nested_bundle_type == "champion_bundle" and champion_manifest is not None:
            champion_bundle = {
                "path": "champion",
                "record_id": champion_manifest.get("record_id"),
                "promotion_id": champion_manifest.get("promotion_id"),
            }

    exported_at = (
        str(existing_manifest["exported_at"])
        if isinstance(existing_manifest, dict) and existing_manifest.get("exported_at") is not None
        else _utc_now()
    )
    manifest = {
        "format_version": "autoharness.campaign_bundle.v1",
        "exported_at": exported_at,
        "reindexed_at": _utc_now(),
        "workspace_id": workspace_id,
        "track_id": track_id,
        "campaign_id": campaign_id,
        "artifact_format": artifact_format,
        "artifacts": {
            "campaign_path": (
                str(campaign_path.relative_to(bundle_root)) if campaign_path is not None else None
            ),
            "campaign_report_path": str(campaign_report_path.relative_to(bundle_root)),
            "proposal_dirs": proposal_dirs,
            "record_paths": record_paths,
            "iteration_dirs": iteration_dirs,
            "promotion_artifacts": promotion_artifacts,
            "champion_bundle": champion_bundle,
        },
    }
    return manifest, artifact_format


def _build_champion_bundle_manifest(
    *,
    bundle_root: Path,
    existing_manifest: dict[str, object] | None,
) -> tuple[dict[str, object], str]:
    source_champion_path = bundle_root / "source_champion.json"
    benchmark_record_path = bundle_root / "benchmark_record.json"
    promotion_path = bundle_root / "promotion.json"
    if not source_champion_path.exists():
        raise SystemExit(f"Champion bundle missing source_champion.json: {bundle_root}")
    source_champion = _load_structured_file(source_champion_path)
    benchmark_record = (
        _load_structured_file(benchmark_record_path) if benchmark_record_path.exists() else None
    )
    promotion_record = _load_structured_file(promotion_path) if promotion_path.exists() else None
    parsed_artifact_sources_path = bundle_root / "parsed_artifact_sources.json"
    parsed_artifact_sources = (
        _load_structured_file(parsed_artifact_sources_path)
        if parsed_artifact_sources_path.exists()
        else source_champion.get("parsed_artifact_sources")
    )

    exported_at = (
        str(existing_manifest["exported_at"])
        if isinstance(existing_manifest, dict) and existing_manifest.get("exported_at") is not None
        else _utc_now()
    )
    source_artifacts = {}
    if isinstance(existing_manifest, dict):
        source_artifacts = (
            dict(existing_manifest.get("source_artifacts", {}))
            if isinstance(existing_manifest.get("source_artifacts"), dict)
            else {}
        )
    manifest = {
        "format_version": "autoharness.champion_export.v1",
        "exported_at": exported_at,
        "reindexed_at": _utc_now(),
        "workspace_id": source_champion.get(
            "workspace_id",
            benchmark_record.get("workspace_id") if isinstance(benchmark_record, dict) else None,
        ),
        "track_id": source_champion.get(
            "track_id",
            benchmark_record.get("track_id") if isinstance(benchmark_record, dict) else None,
        ),
        "record_id": source_champion.get(
            "record_id",
            benchmark_record.get("record_id") if isinstance(benchmark_record, dict) else None,
        ),
        "promotion_id": source_champion.get(
            "promotion_id",
            promotion_record.get("promotion_id") if isinstance(promotion_record, dict) else None,
        ),
        "iteration_id": source_champion.get("iteration_id"),
        "adapter_id": source_champion.get(
            "adapter_id",
            benchmark_record.get("adapter_id") if isinstance(benchmark_record, dict) else None,
        ),
        "benchmark_name": source_champion.get(
            "benchmark_name",
            benchmark_record.get("benchmark_name") if isinstance(benchmark_record, dict) else None,
        ),
        "stage": source_champion.get("stage"),
        "status": source_champion.get("status"),
        "success": source_champion.get("success"),
        "hypothesis": source_champion.get(
            "hypothesis",
            benchmark_record.get("hypothesis") if isinstance(benchmark_record, dict) else "",
        ),
        "notes": source_champion.get(
            "notes",
            benchmark_record.get("notes") if isinstance(benchmark_record, dict) else "",
        ),
        "target_root": source_champion.get(
            "target_root",
            promotion_record.get("target_root") if isinstance(promotion_record, dict) else None,
        ),
        "parsed_artifact_sources": parsed_artifact_sources,
        "bundle_artifacts": {
            "source_champion_manifest_path": (
                "source_champion.json" if source_champion_path.exists() else None
            ),
            "benchmark_record_path": (
                "benchmark_record.json" if benchmark_record_path.exists() else None
            ),
            "promotion_path": "promotion.json" if promotion_path.exists() else None,
            "diff_path": "candidate.patch" if (bundle_root / "candidate.patch").exists() else None,
            "parsed_artifact_sources_path": (
                "parsed_artifact_sources.json"
                if parsed_artifact_sources_path.exists()
                else None
            ),
            "source_plan_artifact_path": (
                "source_plan.json" if (bundle_root / "source_plan.json").exists() else None
            ),
        },
        "source_artifacts": {
            "source_champion_manifest_path": source_artifacts.get("source_champion_manifest_path"),
            "benchmark_record_path": source_champion.get("record_path")
            or source_artifacts.get("benchmark_record_path"),
            "promotion_path": source_champion.get("promotion_path")
            or source_artifacts.get("promotion_path"),
            "diff_path": source_champion.get("diff_path") or source_artifacts.get("diff_path"),
            "parsed_artifact_sources_path": source_champion.get("parsed_artifact_sources_path")
            or source_artifacts.get("parsed_artifact_sources_path"),
            "source_plan_artifact_path": source_artifacts.get("source_plan_artifact_path"),
        },
    }
    return manifest, "json"


def _reindex_bundle_manifest(
    path: Path,
) -> tuple[dict[str, object], Path, Path, str, bool, str]:
    bundle_root, existing_manifest_path, existing_manifest, bundle_type = (
        _probe_bundle_reindex_target(path)
    )
    if bundle_type == "workspace_bundle":
        manifest, artifact_format = _build_workspace_bundle_manifest(
            bundle_root=bundle_root,
            existing_manifest=existing_manifest,
        )
        default_manifest_path = bundle_root / f"bundle_manifest.{artifact_format}"
    elif bundle_type == "root_bundle":
        manifest, artifact_format = _build_root_bundle_manifest(
            bundle_root=bundle_root,
            existing_manifest=existing_manifest,
        )
        default_manifest_path = bundle_root / f"bundle_manifest.{artifact_format}"
    elif bundle_type == "track_bundle":
        manifest, artifact_format = _build_track_bundle_manifest(
            bundle_root=bundle_root,
            existing_manifest=existing_manifest,
        )
        default_manifest_path = bundle_root / f"bundle_manifest.{artifact_format}"
    elif bundle_type == "workspace_campaign_bundle":
        manifest, artifact_format = _build_workspace_campaign_bundle_manifest(
            bundle_root=bundle_root,
            existing_manifest=existing_manifest,
        )
        default_manifest_path = bundle_root / f"bundle_manifest.{artifact_format}"
    elif bundle_type == "root_campaign_bundle":
        manifest, artifact_format = _build_root_campaign_bundle_manifest(
            bundle_root=bundle_root,
            existing_manifest=existing_manifest,
        )
        default_manifest_path = bundle_root / f"bundle_manifest.{artifact_format}"
    elif bundle_type == "campaign_bundle":
        manifest, artifact_format = _build_campaign_bundle_manifest(
            bundle_root=bundle_root,
            existing_manifest=existing_manifest,
        )
        default_manifest_path = bundle_root / f"bundle_manifest.{artifact_format}"
    else:
        manifest, artifact_format = _build_champion_bundle_manifest(
            bundle_root=bundle_root,
            existing_manifest=existing_manifest,
        )
        default_manifest_path = bundle_root / "champion.json"

    target_manifest_path = existing_manifest_path or default_manifest_path
    manifest_existed = existing_manifest_path is not None and existing_manifest_path.exists()
    return (
        manifest,
        bundle_root,
        target_manifest_path,
        bundle_type,
        manifest_existed,
        artifact_format,
    )


def _render_bundle_validation(path: Path, *, recursive: bool = False) -> dict[str, object]:
    return _augment_bundle_validation_with_nested(
        _bundle_validation_from_view(_render_bundle_view(path)),
        recursive=recursive,
    )


def _write_reindexed_bundle_manifest(
    path: Path,
    *,
    output_path: Path | None = None,
    target_format: str | None = None,
) -> dict[str, object]:
    (
        manifest,
        bundle_root,
        target_manifest_path,
        bundle_type,
        manifest_existed,
        artifact_format,
    ) = _reindex_bundle_manifest(path)
    resolved_output_path = output_path or _resolve_import_manifest_path(
        bundle_root=bundle_root,
        bundle_type=bundle_type,
        default_manifest_path=target_manifest_path,
        target_format=target_format,
    )
    if resolved_output_path.exists() and resolved_output_path.is_dir():
        raise SystemExit(f"Output path is a directory: {resolved_output_path}")
    written_format = _write_structured_payload(
        resolved_output_path,
        manifest,
        explicit_format=target_format,
    )
    if (
        output_path is None
        and resolved_output_path != target_manifest_path
        and target_manifest_path.exists()
    ):
        target_manifest_path.unlink()
    return {
        "bundle_type": bundle_type,
        "bundle_path": str(bundle_root),
        "manifest_path": str(resolved_output_path),
        "manifest_existed": manifest_existed,
        "artifact_format": artifact_format,
        "target_format": target_format,
        "written_format": written_format,
        "manifest": manifest,
    }


def _write_reindexed_nested_bundle_manifests(
    *,
    bundle_root: Path,
    bundle_type: str,
    target_format: str | None,
) -> list[dict[str, object]]:
    nested_bundles = []
    for nested_dir in _nested_bundle_directories(bundle_root, bundle_type):
        nested_bundle = {
            "path": str(nested_dir.relative_to(bundle_root)),
            **_write_reindexed_bundle_manifest(
                nested_dir,
                target_format=target_format,
            ),
        }
        nested_bundle_type = nested_bundle["bundle_type"]
        assert isinstance(nested_bundle_type, str)
        nested_bundle["nested_bundles"] = _write_reindexed_nested_bundle_manifests(
            bundle_root=nested_dir,
            bundle_type=nested_bundle_type,
            target_format=target_format,
        )
        nested_bundles.append(nested_bundle)
    return nested_bundles


def _handle_show_bundle(args: argparse.Namespace) -> int:
    rendered = _augment_bundle_view_with_nested(
        _render_bundle_view(args.path),
        recursive=args.recursive,
    )
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Bundle type: {rendered['bundle_type']}")
    print(f"Bundle path: {rendered['bundle_path']}")
    print(f"Manifest path: {rendered['manifest_path']}")
    print(f"Format version: {rendered['format_version']}")
    if rendered["bundle_type"] == "root_bundle":
        print(f"Artifact format: {rendered['artifact_format']}")
        workspace_filter = rendered["workspace_filter"]
        assert isinstance(workspace_filter, list)
        if workspace_filter:
            print(
                "Workspace filter: " + ", ".join(str(item) for item in workspace_filter)
            )
        includes = rendered["includes"]
        assert isinstance(includes, dict)
        print(f"Workspace bundles: {rendered['workspace_bundle_total']}")
        print(f"Listings: {'included' if includes.get('listings') else 'skipped'}")
        print(
            "Track reports: "
            + ("included" if includes.get("track_reports") else "skipped")
        )
        print(
            "Champion bundles: "
            + ("included" if includes.get("champion_bundles") else "skipped")
        )
    elif rendered["bundle_type"] == "workspace_bundle":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Artifact format: {rendered['artifact_format']}")
        includes = rendered["includes"]
        assert isinstance(includes, dict)
        print(f"Listings: {'included' if includes.get('listings') else 'skipped'}")
        print(
            "Track reports: "
            + (
                str(rendered["track_reports_total"])
                if includes.get("track_reports")
                else "skipped"
            )
        )
        print(
            "Champion bundles: "
            + (
                str(rendered["champion_bundles_total"])
                if includes.get("champion_bundles")
                else "skipped"
            )
        )
    elif rendered["bundle_type"] == "workspace_campaign_bundle":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Artifact format: {rendered['artifact_format']}")
        track_filter = rendered["track_filter"]
        assert isinstance(track_filter, list)
        if track_filter:
            print(f"Track filter: {', '.join(str(item) for item in track_filter)}")
        print(f"Campaign bundles: {rendered['campaign_bundle_total']}")
    elif rendered["bundle_type"] == "root_campaign_bundle":
        print(f"Artifact format: {rendered['artifact_format']}")
        workspace_filter = rendered["workspace_filter"]
        assert isinstance(workspace_filter, list)
        if workspace_filter:
            print(
                "Workspace filter: " + ", ".join(str(item) for item in workspace_filter)
            )
        track_filter = rendered["track_filter"]
        assert isinstance(track_filter, list)
        if track_filter:
            print(f"Track filter: {', '.join(str(item) for item in track_filter)}")
        print(f"Workspace bundles: {rendered['workspace_bundle_total']}")
    elif rendered["bundle_type"] == "track_bundle":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Track: {rendered['track_id']}")
        print(f"Artifact format: {rendered['artifact_format']}")
        includes = rendered["includes"]
        assert isinstance(includes, dict)
        print(f"Listings: {'included' if includes.get('listings') else 'skipped'}")
        champion_status = "skipped"
        if includes.get("champion_bundle"):
            artifact_status = rendered["artifact_status"]
            assert isinstance(artifact_status, dict)
            champion_bundle = artifact_status["champion_bundle"]
            champion_status = "present" if champion_bundle is not None else "absent"
        print(f"Champion bundle: {champion_status}")
    elif rendered["bundle_type"] == "campaign_bundle":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Track: {rendered['track_id']}")
        print(f"Campaign: {rendered['campaign_id']}")
        print(f"Artifact format: {rendered['artifact_format']}")
        champion_status = "absent"
        artifact_status = rendered["artifact_status"]
        assert isinstance(artifact_status, dict)
        if artifact_status["champion_bundle"] is not None:
            champion_status = "present"
        print(f"Proposals: {rendered['proposal_total']}")
        print(f"Records: {rendered['record_total']}")
        print(f"Iterations: {rendered['iteration_total']}")
        print(f"Promotions: {rendered['promotion_total']}")
        print(f"Champion bundle: {champion_status}")
    else:
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Track: {rendered['track_id']}")
        print(f"Record: {rendered['record_id']}")
        print(f"Promotion: {rendered['promotion_id']}")
        print(f"Stage: {rendered['stage'] or '(unset)'}")
        print(f"Status: {rendered['status'] or '(unset)'}")

    print(f"Recursive: {'yes' if args.recursive else 'no'}")
    if args.recursive:
        print(f"Nested bundles: {rendered['nested_bundle_total']}")
        nested_bundles = rendered["nested_bundles"]
        assert isinstance(nested_bundles, list)
        for nested_bundle in nested_bundles:
            nested_valid = bool(nested_bundle["valid"])
            nested_error_count = int(nested_bundle["error_count"])
            print(
                "Nested bundle "
                f"{nested_bundle['path']}: "
                f"{'valid' if nested_valid else 'invalid'}"
                f" ({nested_error_count} errors)"
            )

    missing_artifacts = rendered["missing_artifacts"]
    assert isinstance(missing_artifacts, list)
    print(f"Missing artifacts: {len(missing_artifacts)}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_validate_bundle(args: argparse.Namespace) -> int:
    rendered = _render_bundle_validation(args.path, recursive=args.recursive)
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0 if bool(rendered["valid"]) else 1

    print(f"Bundle type: {rendered['bundle_type']}")
    print(f"Bundle path: {rendered['bundle_path']}")
    print(f"Manifest path: {rendered['manifest_path']}")
    print(f"Recursive: {'yes' if args.recursive else 'no'}")
    if args.recursive:
        print(f"Nested bundles: {rendered['nested_bundle_total']}")
    print(f"Valid: {'yes' if rendered['valid'] else 'no'}")
    print(f"Errors: {rendered['error_count']}")
    validation_errors = rendered["validation_errors"]
    assert isinstance(validation_errors, list)
    for error in validation_errors:
        print(error)
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0 if bool(rendered["valid"]) else 1


def _handle_reindex_bundle(args: argparse.Namespace) -> int:
    bundle_root, _manifest_path, _payload, bundle_type = _probe_bundle_reindex_target(args.path)
    nested_bundles = []
    if args.recursive:
        nested_bundles = _write_reindexed_nested_bundle_manifests(
            bundle_root=bundle_root,
            bundle_type=bundle_type,
            target_format=args.format,
        )
    rendered = {
        **_write_reindexed_bundle_manifest(
            args.path,
            output_path=args.output,
            target_format=args.format,
        ),
        "recursive": args.recursive,
        "nested_bundles": nested_bundles,
        "nested_bundle_total": len(nested_bundles),
    }
    if args.output is not None and args.json:
        print(json.dumps(rendered, indent=2))
        return 0
    if args.output is not None and not args.json:
        print(
            f"Reindexed bundle manifest to {rendered['manifest_path']} ({rendered['written_format']})"
        )
        return 0
    if args.json:
        print(json.dumps(rendered, indent=2))
        return 0

    print(f"Bundle type: {rendered['bundle_type']}")
    print(f"Bundle path: {rendered['bundle_path']}")
    print(f"Manifest path: {rendered['manifest_path']}")
    print(f"Manifest existed: {'yes' if rendered['manifest_existed'] else 'no'}")
    print(f"Artifact format: {rendered['artifact_format']}")
    print(f"Recursive: {'yes' if args.recursive else 'no'}")
    if args.recursive:
        print(f"Nested bundles: {rendered['nested_bundle_total']}")
    if args.format is not None:
        print(f"Target format: {args.format}")
    print(f"Written format: {rendered['written_format']}")
    return 0


def _handle_import_bundle(args: argparse.Namespace) -> int:
    source_root, source_manifest_path, source_manifest, bundle_type = _probe_bundle_reindex_target(
        args.path
    )
    output_dir = args.output
    if _paths_overlap_or_nested(source_root, output_dir):
        raise SystemExit(
            f"Import output must not overlap the source bundle path: {output_dir}"
        )

    source_valid: bool | None = None
    source_validation_errors: list[str] = []
    if args.verify_source:
        source_validation = _render_bundle_validation(args.path, recursive=args.recursive)
        source_valid = bool(source_validation["valid"])
        raw_source_validation_errors = source_validation["validation_errors"]
        assert isinstance(raw_source_validation_errors, list)
        source_validation_errors = list(raw_source_validation_errors)
        if not source_valid and not args.allow_invalid:
            rendered = {
                "source_bundle_path": str(source_root),
                "destination_bundle_path": str(output_dir),
                "bundle_type": bundle_type,
                "source_verified": True,
                "source_valid": source_valid,
                "source_validation_errors": source_validation_errors,
                "allow_invalid": args.allow_invalid,
                "recursive": args.recursive,
                "target_format": args.target_format,
                "dry_run": args.dry_run,
                "would_import": False,
                "import_performed": False,
                "manifest_generated": False,
                "manifest_reindexed": False,
                **source_validation,
            }
            if args.json:
                print(json.dumps(rendered, indent=2))
                return 1

            print(f"Source bundle: {source_root}")
            print(f"Imported bundle: {output_dir}")
            print(f"Bundle type: {bundle_type}")
            print("Source verified: yes")
            print("Source valid: no")
            print(f"Allow invalid: {'yes' if args.allow_invalid else 'no'}")
            print(f"Recursive: {'yes' if args.recursive else 'no'}")
            if args.target_format is not None:
                print(f"Target format: {args.target_format}")
            print(f"Dry run: {'yes' if args.dry_run else 'no'}")
            print("Would import: no")
            print("Import performed: no")
            print("Valid: no")
            print(f"Errors: {rendered['error_count']}")
            validation_errors = rendered["validation_errors"]
            assert isinstance(validation_errors, list)
            for error in validation_errors:
                print(error)
            return 1

    manifest_generated = source_manifest_path is None or not source_manifest_path.exists()
    manifest_reindexed = False
    if args.dry_run:
        if output_dir.exists():
            if not output_dir.is_dir():
                raise SystemExit(f"Import output is not a directory: {output_dir}")
            if any(output_dir.iterdir()) and not args.force:
                raise SystemExit(
                    f"Refusing to write into non-empty directory: {output_dir}. Use --force."
                )

        if manifest_generated or args.reindex:
            (
                generated_manifest,
                _bundle_root,
                default_manifest_path,
                _generated_bundle_type,
                _manifest_existed,
                _artifact_format,
            ) = _reindex_bundle_manifest(source_root)
            predicted_manifest_path = _resolve_import_manifest_path(
                bundle_root=output_dir,
                bundle_type=bundle_type,
                default_manifest_path=output_dir / default_manifest_path.name,
                target_format=args.target_format,
            )
            predicted_view = _render_bundle_view_from_payload(
                bundle_root=source_root,
                manifest_path=predicted_manifest_path,
                payload=generated_manifest,
                rendered_bundle_path=output_dir,
            )
            manifest_reindexed = not manifest_generated
        else:
            assert source_manifest_path is not None
            assert isinstance(source_manifest, dict)
            predicted_manifest_path = _resolve_import_manifest_path(
                bundle_root=output_dir,
                bundle_type=bundle_type,
                default_manifest_path=output_dir / source_manifest_path.name,
                target_format=args.target_format,
            )
            predicted_view = _render_bundle_view_from_payload(
                bundle_root=source_root,
                manifest_path=predicted_manifest_path,
                payload=source_manifest,
                rendered_bundle_path=output_dir,
            )
        predicted_validation = _merge_validation_with_nested_bundles(
            _bundle_validation_from_view(predicted_view),
            recursive=args.recursive,
            nested_bundles=_predict_nested_bundle_validations(
                source_bundle_root=source_root,
                rendered_bundle_root=output_dir,
                bundle_type=bundle_type,
                recursive=args.recursive,
                target_format=args.target_format,
                reindex_nested=args.recursive and args.reindex,
            ),
        )

        rendered = {
            "source_bundle_path": str(source_root),
            "destination_bundle_path": str(output_dir),
            "bundle_type": bundle_type,
            "source_verified": args.verify_source,
            "source_valid": source_valid,
            "source_validation_errors": source_validation_errors,
            "allow_invalid": args.allow_invalid,
            "recursive": args.recursive,
            "target_format": args.target_format,
            "dry_run": True,
            "would_import": True,
            "import_performed": False,
            "manifest_generated": manifest_generated,
            "manifest_reindexed": manifest_reindexed,
            **predicted_validation,
        }
        if args.json:
            print(json.dumps(rendered, indent=2))
            return 0 if bool(rendered["valid"]) else 1

        print(f"Source bundle: {source_root}")
        print(f"Imported bundle: {output_dir}")
        print(f"Bundle type: {bundle_type}")
        print(f"Source verified: {'yes' if args.verify_source else 'no'}")
        if args.verify_source:
            print(f"Source valid: {'yes' if source_valid else 'no'}")
        print(f"Allow invalid: {'yes' if args.allow_invalid else 'no'}")
        print(f"Recursive: {'yes' if args.recursive else 'no'}")
        if args.recursive:
            print(f"Nested bundles: {rendered['nested_bundle_total']}")
        if args.target_format is not None:
            print(f"Target format: {args.target_format}")
        print("Dry run: yes")
        print("Would import: yes")
        print("Import performed: no")
        print(f"Manifest generated: {'yes' if manifest_generated else 'no'}")
        print(f"Manifest reindexed: {'yes' if manifest_reindexed else 'no'}")
        print(f"Predicted manifest path: {rendered['manifest_path']}")
        print(f"Valid: {'yes' if rendered['valid'] else 'no'}")
        print(f"Errors: {rendered['error_count']}")
        validation_errors = rendered["validation_errors"]
        assert isinstance(validation_errors, list)
        for error in validation_errors:
            print(error)
        return 0 if bool(rendered["valid"]) else 1

    _prepare_export_dir(output_dir, force=args.force)
    _copy_bundle_contents(source_root, output_dir)

    nested_bundles: list[dict[str, object]] = []
    if args.recursive and args.reindex:
        nested_bundles = _write_reindexed_nested_bundle_manifests(
            bundle_root=output_dir,
            bundle_type=bundle_type,
            target_format=args.target_format,
        )

    if manifest_generated or args.reindex:
        (
            generated_manifest,
            _bundle_root,
            default_manifest_path,
            _generated_bundle_type,
            _manifest_existed,
            _artifact_format,
        ) = _reindex_bundle_manifest(output_dir)
        generated_manifest_path = _resolve_import_manifest_path(
            bundle_root=output_dir,
            bundle_type=bundle_type,
            default_manifest_path=default_manifest_path,
            target_format=args.target_format,
        )
        _write_structured_payload(
            generated_manifest_path,
            generated_manifest,
            explicit_format=args.target_format,
        )
        if generated_manifest_path != default_manifest_path and default_manifest_path.exists():
            default_manifest_path.unlink()
        manifest_reindexed = not manifest_generated
    elif args.target_format is not None:
        assert source_manifest_path is not None
        assert isinstance(source_manifest, dict)
        copied_manifest_path = output_dir / source_manifest_path.name
        generated_manifest_path = _resolve_import_manifest_path(
            bundle_root=output_dir,
            bundle_type=bundle_type,
            default_manifest_path=copied_manifest_path,
            target_format=args.target_format,
        )
        _write_structured_payload(
            generated_manifest_path,
            source_manifest,
            explicit_format=args.target_format,
        )
        if generated_manifest_path != copied_manifest_path and copied_manifest_path.exists():
            copied_manifest_path.unlink()

    validation = _render_bundle_validation(output_dir, recursive=args.recursive)
    rendered = {
        "source_bundle_path": str(source_root),
        "destination_bundle_path": str(output_dir),
        "bundle_type": bundle_type,
        "source_verified": args.verify_source,
        "source_valid": source_valid,
        "source_validation_errors": source_validation_errors,
        "allow_invalid": args.allow_invalid,
        "recursive": args.recursive,
        "target_format": args.target_format,
        "dry_run": False,
        "would_import": True,
        "import_performed": True,
        "manifest_generated": manifest_generated,
        "manifest_reindexed": manifest_reindexed,
        "nested_reindexed_bundles": nested_bundles,
        **validation,
    }
    if args.json:
        print(json.dumps(rendered, indent=2))
        return 0 if bool(rendered["valid"]) else 1

    print(f"Source bundle: {source_root}")
    print(f"Imported bundle: {output_dir}")
    print(f"Bundle type: {bundle_type}")
    print(f"Source verified: {'yes' if args.verify_source else 'no'}")
    if args.verify_source:
        print(f"Source valid: {'yes' if source_valid else 'no'}")
    print(f"Allow invalid: {'yes' if args.allow_invalid else 'no'}")
    print(f"Recursive: {'yes' if args.recursive else 'no'}")
    if args.recursive:
        print(f"Nested bundles: {rendered['nested_bundle_total']}")
    if args.target_format is not None:
        print(f"Target format: {args.target_format}")
    print("Dry run: no")
    print("Would import: yes")
    print("Import performed: yes")
    print(f"Manifest generated: {'yes' if manifest_generated else 'no'}")
    print(f"Manifest reindexed: {'yes' if manifest_reindexed else 'no'}")
    print(f"Valid: {'yes' if rendered['valid'] else 'no'}")
    print(f"Errors: {rendered['error_count']}")
    validation_errors = rendered["validation_errors"]
    assert isinstance(validation_errors, list)
    for error in validation_errors:
        print(error)
    return 0 if bool(rendered["valid"]) else 1


def _handle_show_promotion_policy(args: argparse.Namespace) -> int:
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
    try:
        policy = load_promotion_policy(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
        )
    except FileNotFoundError as exc:
        raise SystemExit(str(exc)) from exc

    rendered = policy.to_dict()
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Policy path: {policy_path}")
    print(f"Stage: {policy.stage or '(unset)'}")
    print(
        "Min success rate: "
        f"{policy.min_success_rate if policy.min_success_rate is not None else '(unset)'}"
    )
    print(
        "Min improvement: "
        f"{policy.min_improvement if policy.min_improvement is not None else '(unset)'}"
    )
    print(
        "Max regressed tasks: "
        f"{policy.max_regressed_tasks if policy.max_regressed_tasks is not None else '(unset)'}"
    )
    print(
        "Max regressed task fraction: "
        f"{policy.max_regressed_task_fraction if policy.max_regressed_task_fraction is not None else '(unset)'}"
    )
    print(
        "Max regressed task weight: "
        f"{policy.max_regressed_task_weight if policy.max_regressed_task_weight is not None else '(unset)'}"
    )
    print(
        "Max regressed task weight fraction: "
        f"{policy.max_regressed_task_weight_fraction if policy.max_regressed_task_weight_fraction is not None else '(unset)'}"
    )
    print(
        "Task regression margin: "
        f"{policy.task_regression_margin if policy.task_regression_margin is not None else '(unset)'}"
    )
    print(f"Notes: {policy.notes or '(none)'}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _render_track_policy_view(
    *,
    root,
    workspace_id: str,
    requested_track_id: str | None,
) -> dict[str, object]:
    workspace, _, track_id = _resolve_workspace_track(
        root=root,
        workspace_id=workspace_id,
        requested_track_id=requested_track_id,
    )
    resolved = _resolved_track_policy_details(
        root=root,
        workspace=workspace,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    effective_policy = resolved["effective_policy"]
    assert isinstance(effective_policy, dict)
    effective_sources = resolved["effective_sources"]
    assert isinstance(effective_sources, dict)

    return {
        "workspace_id": workspace_id,
        "track_id": track_id,
        **effective_policy,
        "policy_path": resolved["policy_path"],
        "raw_policy_exists": resolved["raw_policy_exists"],
        "raw_policy": resolved["raw_policy"],
        "effective_sources": effective_sources,
        "workspace_fallback_policy": resolved["workspace_fallback_policy"],
    }


def _handle_show_track_policy(args: argparse.Namespace) -> int:
    rendered = _render_track_policy_view(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    track_id = str(rendered["track_id"])
    policy_path = str(rendered["policy_path"])
    effective_sources = rendered["effective_sources"]
    assert isinstance(effective_sources, dict)
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Policy path: {policy_path}")
    print(
        "Search benchmark: "
        f"{rendered['search_benchmark']} [{effective_sources['search_benchmark']}]"
    )
    print(
        "Promotion benchmark: "
        f"{rendered['promotion_benchmark']} [{effective_sources['promotion_benchmark']}]"
    )
    print(
        "Regression benchmark: "
        f"{rendered['regression_benchmark']} [{effective_sources['regression_benchmark']}]"
    )
    print(
        "Search preset: "
        f"{rendered.get('search_preset') or '(none)'} [{effective_sources['search_preset']}]"
    )
    print(
        "Promotion preset: "
        f"{rendered.get('promotion_preset') or '(none)'} [{effective_sources['promotion_preset']}]"
    )
    print(
        "Regression preset: "
        f"{rendered.get('regression_preset') or '(none)'} [{effective_sources['regression_preset']}]"
    )
    print(f"Notes: {rendered['notes'] or '(none)'}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _inspection_report_path_value(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _validate_inspection_report_artifact_payload(
    *,
    payload: dict[str, object],
    report_type: str,
) -> list[str]:
    errors: list[str] = []

    def require_dict(key: str) -> dict[str, object] | None:
        value = payload.get(key)
        if not isinstance(value, dict):
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

    def require_list(key: str) -> list[object] | None:
        value = payload.get(key)
        if not isinstance(value, list):
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

    if report_type == "workspace_summary_export":
        summary = require_dict("summary")
        if summary is None:
            return errors
        workspace_id = summary.get("workspace_id")
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            errors.append("Missing or invalid `summary.workspace_id`.")
        counts = summary.get("counts")
        if not isinstance(counts, dict):
            errors.append("Missing or invalid `summary.counts`.")
        else:
            for key in (
                "tracks_total",
                "iterations_total",
                "records_total",
                "promotions_total",
                "champion_tracks_total",
            ):
                if not isinstance(counts.get(key), int):
                    errors.append(f"Missing or invalid `summary.counts.{key}`.")
        tracks = summary.get("tracks")
        if not isinstance(tracks, list):
            errors.append("Missing or invalid `summary.tracks`.")
        return errors

    if report_type == "root_summary_export":
        summary = require_dict("summary")
        if summary is None:
            return errors
        counts = summary.get("counts")
        if not isinstance(counts, dict):
            errors.append("Missing or invalid `summary.counts`.")
        else:
            for key in (
                "workspaces_total",
                "tracks_total",
                "iterations_total",
                "records_total",
                "promotions_total",
                "champion_tracks_total",
            ):
                if not isinstance(counts.get(key), int):
                    errors.append(f"Missing or invalid `summary.counts.{key}`.")
        workspaces = summary.get("workspaces")
        if not isinstance(workspaces, list):
            errors.append("Missing or invalid `summary.workspaces`.")
        return errors

    if report_type == "root_champion_report":
        champion_report = require_dict("champions")
        if champion_report is None:
            return errors
        for key in ("workspace_total", "champion_total", "transferred_champion_total"):
            if not isinstance(champion_report.get(key), int):
                errors.append(f"Missing or invalid `champions.{key}`.")
        mix = champion_report.get("mix")
        if not isinstance(mix, dict):
            errors.append("Missing or invalid `champions.mix`.")
        else:
            for key in (
                "by_stage",
                "by_adapter_id",
                "by_benchmark_name",
                "by_source_workspace_id",
            ):
                if not isinstance(mix.get(key), dict):
                    errors.append(f"Missing or invalid `champions.mix.{key}`.")
        champion_items = champion_report.get("champions")
        if not isinstance(champion_items, list):
            errors.append("Missing or invalid `champions.champions`.")
        return errors

    if report_type == "track_summary_export":
        summary = require_dict("summary")
        if summary is None:
            return errors
        workspace_id = summary.get("workspace_id")
        if not isinstance(workspace_id, str) or not workspace_id.strip():
            errors.append("Missing or invalid `summary.workspace_id`.")
        track_id = summary.get("track_id")
        if not isinstance(track_id, str) or not track_id.strip():
            errors.append("Missing or invalid `summary.track_id`.")
        records = summary.get("records")
        if not isinstance(records, dict):
            errors.append("Missing or invalid `summary.records`.")
        else:
            if not isinstance(records.get("total"), int):
                errors.append("Missing or invalid `summary.records.total`.")
        promotions = summary.get("promotions")
        if not isinstance(promotions, dict):
            errors.append("Missing or invalid `summary.promotions`.")
        else:
            if not isinstance(promotions.get("total"), int):
                errors.append("Missing or invalid `summary.promotions.total`.")
        return errors

    if report_type == "workspace_report_export":
        workspace = require_dict("workspace")
        if workspace is not None:
            workspace_id = workspace.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id.strip():
                errors.append("Missing or invalid `workspace.workspace_id`.")
        workspace_summary = require_dict("workspace_summary")
        if workspace_summary is not None:
            workspace_id = workspace_summary.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id.strip():
                errors.append("Missing or invalid `workspace_summary.workspace_id`.")
        tracks = require_dict("tracks")
        if tracks is not None:
            track_items = tracks.get("tracks")
            if not isinstance(track_items, list):
                errors.append("Missing or invalid `tracks.tracks`.")
        require_list("track_reports")
        return errors

    if report_type == "root_report_export":
        root_summary = require_dict("root_summary")
        if root_summary is not None:
            counts = root_summary.get("counts")
            if not isinstance(counts, dict):
                errors.append("Missing or invalid `root_summary.counts`.")
            elif not isinstance(counts.get("workspaces_total"), int):
                errors.append(
                    "Missing or invalid `root_summary.counts.workspaces_total`."
                )
        require_list("workspace_reports")
        return errors

    if report_type == "track_report_export":
        track = require_dict("track")
        if track is not None:
            workspace_id = track.get("workspace_id")
            if not isinstance(workspace_id, str) or not workspace_id.strip():
                errors.append("Missing or invalid `track.workspace_id`.")
            track_id = track.get("track_id")
            if not isinstance(track_id, str) or not track_id.strip():
                errors.append("Missing or invalid `track.track_id`.")
        track_summary = require_dict("track_summary")
        if track_summary is not None:
            track_id = track_summary.get("track_id")
            if not isinstance(track_id, str) or not track_id.strip():
                errors.append("Missing or invalid `track_summary.track_id`.")
        require_dict("effective_track_policy")
        require_dict("promotion_policy")
        require_dict("track_artifacts")
        return errors

    errors.append(f"Unsupported inspection report type `{report_type}`.")
    return errors


def _render_inspection_report_artifact(path: Path) -> dict[str, object]:
    payload = _load_structured_file(path)
    format_version = payload.get("format_version")
    if not isinstance(format_version, str):
        raise SystemExit(f"Inspection report missing format_version: {path}")

    rendered: dict[str, object] = {
        "report_path": str(path),
        "format_version": format_version,
        "report": payload,
    }

    if format_version == "autoharness.workspace_summary_export.v1":
        summary = payload.get("summary")
        counts = summary.get("counts") if isinstance(summary, dict) else None
        rendered.update(
            {
                "report_type": "workspace_summary_export",
                "workspace_id": (
                    _inspection_report_path_value(summary, "workspace_id")
                    if isinstance(summary, dict)
                    else None
                ),
                "track_total": (
                    counts.get("tracks_total") if isinstance(counts, dict) else None
                ),
                "record_total": (
                    counts.get("records_total") if isinstance(counts, dict) else None
                ),
                "promotion_total": (
                    counts.get("promotions_total") if isinstance(counts, dict) else None
                ),
                "champion_track_total": (
                    counts.get("champion_tracks_total")
                    if isinstance(counts, dict)
                    else None
                ),
            }
        )
        return rendered

    if format_version == "autoharness.root_summary_export.v1":
        summary = payload.get("summary")
        counts = summary.get("counts") if isinstance(summary, dict) else None
        rendered.update(
            {
                "report_type": "root_summary_export",
                "workspace_total": (
                    counts.get("workspaces_total") if isinstance(counts, dict) else None
                ),
                "track_total": (
                    counts.get("tracks_total") if isinstance(counts, dict) else None
                ),
                "record_total": (
                    counts.get("records_total") if isinstance(counts, dict) else None
                ),
                "promotion_total": (
                    counts.get("promotions_total") if isinstance(counts, dict) else None
                ),
                "champion_track_total": (
                    counts.get("champion_tracks_total")
                    if isinstance(counts, dict)
                    else None
                ),
            }
        )
        return rendered

    if format_version == "autoharness.track_summary_export.v1":
        summary = payload.get("summary")
        records = summary.get("records") if isinstance(summary, dict) else None
        promotions = summary.get("promotions") if isinstance(summary, dict) else None
        champion = summary.get("champion") if isinstance(summary, dict) else None
        rendered.update(
            {
                "report_type": "track_summary_export",
                "workspace_id": (
                    _inspection_report_path_value(summary, "workspace_id")
                    if isinstance(summary, dict)
                    else None
                ),
                "track_id": (
                    _inspection_report_path_value(summary, "track_id")
                    if isinstance(summary, dict)
                    else None
                ),
                "record_total": (
                    records.get("total") if isinstance(records, dict) else None
                ),
                "promotion_total": (
                    promotions.get("total") if isinstance(promotions, dict) else None
                ),
                "has_champion": isinstance(champion, dict),
            }
        )
        return rendered

    if format_version == "autoharness.workspace_report_export.v1":
        workspace = payload.get("workspace")
        workspace_summary = payload.get("workspace_summary")
        track_reports = payload.get("track_reports")
        counts = (
            workspace_summary.get("counts")
            if isinstance(workspace_summary, dict)
            else None
        )
        rendered.update(
            {
                "report_type": "workspace_report_export",
                "workspace_id": (
                    _inspection_report_path_value(workspace, "workspace_id")
                    if isinstance(workspace, dict)
                    else None
                ),
                "track_total": (
                    counts.get("tracks_total") if isinstance(counts, dict) else None
                ),
                "record_total": (
                    counts.get("records_total") if isinstance(counts, dict) else None
                ),
                "promotion_total": (
                    counts.get("promotions_total") if isinstance(counts, dict) else None
                ),
                "track_report_total": len(track_reports)
                if isinstance(track_reports, list)
                else 0,
            }
        )
        return rendered

    if format_version == "autoharness.root_report_export.v1":
        root_summary = payload.get("root_summary")
        workspace_reports = payload.get("workspace_reports")
        counts = root_summary.get("counts") if isinstance(root_summary, dict) else None
        rendered.update(
            {
                "report_type": "root_report_export",
                "workspace_total": (
                    counts.get("workspaces_total") if isinstance(counts, dict) else None
                ),
                "record_total": (
                    counts.get("records_total") if isinstance(counts, dict) else None
                ),
                "promotion_total": (
                    counts.get("promotions_total") if isinstance(counts, dict) else None
                ),
                "workspace_report_total": len(workspace_reports)
                if isinstance(workspace_reports, list)
                else 0,
            }
        )
        return rendered

    if format_version == "autoharness.root_champion_report.v1":
        champion_report = payload.get("champions")
        mix = champion_report.get("mix") if isinstance(champion_report, dict) else None
        rendered.update(
            {
                "report_type": "root_champion_report",
                "workspace_total": (
                    champion_report.get("workspace_total")
                    if isinstance(champion_report, dict)
                    else None
                ),
                "champion_total": (
                    champion_report.get("champion_total")
                    if isinstance(champion_report, dict)
                    else None
                ),
                "transferred_champion_total": (
                    champion_report.get("transferred_champion_total")
                    if isinstance(champion_report, dict)
                    else None
                ),
                "source_workspace_mix_total": (
                    len(mix.get("by_source_workspace_id", {}))
                    if isinstance(mix, dict)
                    and isinstance(mix.get("by_source_workspace_id"), dict)
                    else 0
                ),
            }
        )
        return rendered

    if format_version == "autoharness.track_report_export.v1":
        track = payload.get("track")
        track_summary = payload.get("track_summary")
        records = (
            track_summary.get("records") if isinstance(track_summary, dict) else None
        )
        promotions = (
            track_summary.get("promotions")
            if isinstance(track_summary, dict)
            else None
        )
        champion = (
            track_summary.get("champion") if isinstance(track_summary, dict) else None
        )
        rendered.update(
            {
                "report_type": "track_report_export",
                "workspace_id": (
                    _inspection_report_path_value(track, "workspace_id")
                    if isinstance(track, dict)
                    else None
                ),
                "track_id": (
                    _inspection_report_path_value(track, "track_id")
                    if isinstance(track, dict)
                    else None
                ),
                "record_total": (
                    records.get("total") if isinstance(records, dict) else None
                ),
                "promotion_total": (
                    promotions.get("total") if isinstance(promotions, dict) else None
                ),
                "has_champion": isinstance(champion, dict),
            }
        )
        return rendered

    raise SystemExit(
        f"Unsupported inspection report format_version `{format_version}`: {path}"
    )


def _render_inspection_report_validation(path: Path) -> dict[str, object]:
    rendered = _render_inspection_report_artifact(path)
    report_type = rendered["report_type"]
    assert isinstance(report_type, str)
    report_payload = rendered["report"]
    assert isinstance(report_payload, dict)
    validation_errors = _validate_inspection_report_artifact_payload(
        payload=report_payload,
        report_type=report_type,
    )
    return {
        **rendered,
        "valid": not validation_errors,
        "error_count": len(validation_errors),
        "validation_errors": validation_errors,
    }


def _handle_show_report_file(args: argparse.Namespace) -> int:
    rendered = _render_inspection_report_artifact(args.path)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    print(f"Report type: {rendered['report_type']}")
    print(f"Report path: {rendered['report_path']}")
    print(f"Format version: {rendered['format_version']}")
    report_type = rendered["report_type"]
    if report_type == "workspace_summary_export":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Tracks: {rendered['track_total']}")
        print(f"Records: {rendered['record_total']}")
        print(f"Promotions: {rendered['promotion_total']}")
        print(f"Champion tracks: {rendered['champion_track_total']}")
    elif report_type == "root_summary_export":
        print(f"Workspaces: {rendered['workspace_total']}")
        print(f"Tracks: {rendered['track_total']}")
        print(f"Records: {rendered['record_total']}")
        print(f"Promotions: {rendered['promotion_total']}")
        print(f"Champion tracks: {rendered['champion_track_total']}")
    elif report_type == "track_summary_export":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Track: {rendered['track_id']}")
        print(f"Records: {rendered['record_total']}")
        print(f"Promotions: {rendered['promotion_total']}")
        print(f"Champion: {'present' if rendered['has_champion'] else 'absent'}")
    elif report_type == "workspace_report_export":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Tracks: {rendered['track_total']}")
        print(f"Records: {rendered['record_total']}")
        print(f"Promotions: {rendered['promotion_total']}")
        print(f"Track reports: {rendered['track_report_total']}")
    elif report_type == "root_report_export":
        print(f"Workspaces: {rendered['workspace_total']}")
        print(f"Records: {rendered['record_total']}")
        print(f"Promotions: {rendered['promotion_total']}")
        print(f"Workspace reports: {rendered['workspace_report_total']}")
    elif report_type == "root_champion_report":
        print(f"Workspaces: {rendered['workspace_total']}")
        print(f"Champions: {rendered['champion_total']}")
        print(f"Transferred champions: {rendered['transferred_champion_total']}")
        print(f"Source workspace mix: {rendered['source_workspace_mix_total']}")
    else:
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Track: {rendered['track_id']}")
        print(f"Records: {rendered['record_total']}")
        print(f"Promotions: {rendered['promotion_total']}")
        print(f"Champion: {'present' if rendered['has_champion'] else 'absent'}")

    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_validate_report_file(args: argparse.Namespace) -> int:
    rendered = _render_inspection_report_validation(args.path)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0 if bool(rendered["valid"]) else 1

    print(f"Report type: {rendered['report_type']}")
    print(f"Report path: {rendered['report_path']}")
    print(f"Format version: {rendered['format_version']}")
    print(f"Valid: {'yes' if rendered['valid'] else 'no'}")
    print(f"Errors: {rendered['error_count']}")
    validation_errors = rendered["validation_errors"]
    assert isinstance(validation_errors, list)
    for error in validation_errors:
        print(f"- {error}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0 if bool(rendered["valid"]) else 1


def _artifact_file_handler_pair(path: Path):
    payload = _load_structured_file(path)
    format_version = payload.get("format_version")
    if format_version in {
        "autoharness.workspace_summary_export.v1",
        "autoharness.root_summary_export.v1",
        "autoharness.root_champion_report.v1",
        "autoharness.track_summary_export.v1",
        "autoharness.workspace_report_export.v1",
        "autoharness.root_report_export.v1",
        "autoharness.track_report_export.v1",
    }:
        return _handle_show_report_file, _handle_validate_report_file
    if format_version in {
        "autoharness.campaign_report.v1",
        "autoharness.workspace_campaign_report.v1",
        "autoharness.root_campaign_report.v1",
        "autoharness.workspace_campaign_run_report.v1",
        "autoharness.root_campaign_run_report.v1",
    }:
        return _handle_show_campaign_report_file, _handle_validate_campaign_report_file
    if format_version in {
        "autoharness.iteration_export.v1",
        "autoharness.record_export.v1",
        "autoharness.promotion_export.v1",
        "autoharness.proposal_export.v1",
    }:
        return _handle_show_listing_file, _handle_validate_listing_file
    raw_command = payload.get("suggested_command")
    if format_version == "autoharness.iteration_plan.v1" or (
        isinstance(raw_command, list)
        and len(raw_command) >= 2
        and raw_command[0] == "autoharness"
        and raw_command[1] == "run-iteration"
    ):
        return _handle_show_plan_file, _handle_validate_plan_file
    raise SystemExit(f"Unsupported artifact file: {path}")


def _handle_show_artifact_file(args: argparse.Namespace) -> int:
    show_handler, _ = _artifact_file_handler_pair(args.path)
    return show_handler(args)


def _handle_validate_artifact_file(args: argparse.Namespace) -> int:
    _, validate_handler = _artifact_file_handler_pair(args.path)
    return validate_handler(args)


def _handle_show_root_summary(args: argparse.Namespace) -> int:
    rendered = _render_root_summary(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
    )
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    counts = rendered["counts"]
    assert isinstance(counts, dict)
    status_counts = rendered["workspace_status_counts"]
    assert isinstance(status_counts, dict)
    campaign_default_mix = rendered["active_track_campaign_default_mix"]
    assert isinstance(campaign_default_mix, dict)
    workspaces = rendered["workspaces"]
    assert isinstance(workspaces, list)

    print(f"Root: {rendered['root_path']}")
    if rendered["workspace_filter"]:
        print("Workspace filter: " + ", ".join(rendered["workspace_filter"]))
    print(f"Workspaces: {counts['workspaces_total']}")
    print(f"Active workspaces: {counts['active_workspaces_total']}")
    print(f"Archived workspaces: {counts['archived_workspaces_total']}")
    print(f"Tracks: {counts['tracks_total']}")
    print(f"Iterations: {counts['iterations_total']}")
    print(f"Records: {counts['records_total']}")
    print(f"Saved-plan runs: {counts['source_plan_records_total']}")
    print(f"Promotions: {counts['promotions_total']}")
    print(f"Champion tracks: {counts['champion_tracks_total']}")
    if status_counts:
        print(
            "Workspace status counts: "
            + ", ".join(f"{key}={status_counts[key]}" for key in sorted(status_counts))
        )
    print(
        "Active-track stage mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_stage'][key]}"
            for key in sorted(campaign_default_mix["by_stage"])
        )
    )
    print(
        "Active-track generator mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_generator_id'][key]}"
            for key in sorted(campaign_default_mix["by_generator_id"])
        )
    )
    print(
        "Active-track strategy mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_strategy'][key]}"
            for key in sorted(campaign_default_mix["by_strategy"])
        )
    )
    print(
        "Active-track beam width mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_beam_width'][key]}"
            for key in sorted(campaign_default_mix["by_beam_width"])
        )
    )
    print(
        "Active-track beam group mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_beam_group_limit'][key]}"
            for key in sorted(campaign_default_mix["by_beam_group_limit"])
        )
    )
    print(
        "Active-track repeat count mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_repeat_count'][key]}"
            for key in sorted(campaign_default_mix["by_repeat_count"])
        )
    )
    print(
        "Active-track generation token budget mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_generation_total_tokens'][key]}"
            for key in sorted(campaign_default_mix["by_max_generation_total_tokens"])
        )
    )
    print(
        "Active-track benchmark cost budget mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_benchmark_total_cost'][key]}"
            for key in sorted(campaign_default_mix["by_max_benchmark_total_cost"])
        )
    )
    print(
        "Active-track generation-timeout retry mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_generation_timeout_retries'][key]}"
            for key in sorted(
                campaign_default_mix["by_max_generation_timeout_retries"]
            )
        )
    )
    print(
        "Active-track generation-provider retry mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_generation_provider_retries'][key]}"
            for key in sorted(
                campaign_default_mix["by_max_generation_provider_retries"]
            )
        )
    )
    print(
        "Active-track generation-provider-transport retry mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_generation_provider_transport_retries'][key]}"
            for key in sorted(
                campaign_default_mix["by_max_generation_provider_transport_retries"]
            )
        )
    )
    print(
        "Active-track generation-provider-auth retry mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_generation_provider_auth_retries'][key]}"
            for key in sorted(
                campaign_default_mix["by_max_generation_provider_auth_retries"]
            )
        )
    )
    print(
        "Active-track generation-provider-rate-limit retry mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_generation_provider_rate_limit_retries'][key]}"
            for key in sorted(
                campaign_default_mix["by_max_generation_provider_rate_limit_retries"]
            )
        )
    )
    print(
        "Active-track generation-process retry mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_generation_process_retries'][key]}"
            for key in sorted(
                campaign_default_mix["by_max_generation_process_retries"]
            )
        )
    )
    print(
        "Active-track allow-flaky-promotion mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_allow_flaky_promotion'][key]}"
            for key in sorted(campaign_default_mix["by_allow_flaky_promotion"])
        )
    )
    print(
        "Active-track benchmark-timeout retry mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_benchmark_timeout_retries'][key]}"
            for key in sorted(
                campaign_default_mix["by_max_benchmark_timeout_retries"]
            )
        )
    )
    print(
        "Active-track benchmark-command retry mix: "
        + ", ".join(
            f"{key}={campaign_default_mix['by_max_benchmark_command_retries'][key]}"
            for key in sorted(
                campaign_default_mix["by_max_benchmark_command_retries"]
            )
        )
    )
    for workspace in workspaces:
        assert isinstance(workspace, dict)
        workspace_counts = workspace["counts"]
        assert isinstance(workspace_counts, dict)
        active_track_campaign_policy = workspace["active_track_effective_campaign_policy"]
        assert isinstance(active_track_campaign_policy, dict)
        active_policy = active_track_campaign_policy["effective_policy"]
        assert isinstance(active_policy, dict)
        print(
            f"- {workspace['workspace_id']}: status={workspace['status']}, "
            f"active_track={workspace['active_track_id']}, "
            f"tracks={workspace_counts['tracks_total']}, "
            f"records={workspace_counts['records_total']}, "
            f"generator={active_policy['generator_id']}, "
            f"strategy={active_policy['strategy']}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_root_champions(args: argparse.Namespace) -> int:
    rendered = _render_root_champion_report(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
        requested_track_ids=list(args.track_id),
    )
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Root: {rendered['root_path']}")
    if rendered["workspace_filter"]:
        print("Workspace filter: " + ", ".join(rendered["workspace_filter"]))
    if rendered["track_filter"]:
        print("Track filter: " + ", ".join(rendered["track_filter"]))
    print(f"Workspaces: {rendered['workspace_total']}")
    print(f"Champions: {rendered['champion_total']}")
    print(f"Transferred champions: {rendered['transferred_champion_total']}")
    mix = rendered["mix"]
    assert isinstance(mix, dict)
    print(
        "Champion stage mix: "
        + ", ".join(f"{key}={mix['by_stage'][key]}" for key in sorted(mix["by_stage"]))
    )
    print(
        "Champion source workspace mix: "
        + ", ".join(
            f"{key}={mix['by_source_workspace_id'][key]}"
            for key in sorted(mix["by_source_workspace_id"])
        )
    )
    champions = rendered["champions"]
    assert isinstance(champions, list)
    for item in champions:
        assert isinstance(item, dict)
        print(
            f"- {item['workspace_id']}/{item['track_id']}: "
            f"record={item['record_id']}, benchmark={item['benchmark_name']}, "
            f"source={item['transfer_source'].get('workspace_id') if isinstance(item.get('transfer_source'), dict) else '(native)'}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_export_root_summary(args: argparse.Namespace) -> int:
    rendered = _render_root_summary(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
    )
    output_format = _write_structured_payload(
        args.output,
        {
            "format_version": "autoharness.root_summary_export.v1",
            "exported_at": _utc_now(),
            "summary": rendered,
        },
        explicit_format=args.format,
    )
    print(f"Exported root summary to {args.output} ({output_format})")
    return 0


def _handle_export_root_champion_report(args: argparse.Namespace) -> int:
    rendered = _render_root_champion_report(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
        requested_track_ids=list(args.track_id),
    )
    output_format = _write_structured_payload(
        args.output,
        {
            "format_version": "autoharness.root_champion_report.v1",
            "exported_at": _utc_now(),
            "champions": rendered,
        },
        explicit_format=args.format,
    )
    print(f"Exported root champion report to {args.output} ({output_format})")
    return 0


def _handle_show_workspace_summary(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    rendered = _render_workspace_summary(
        root=args.root,
        workspace_id=args.workspace_id,
    )
    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {rendered['workspace_id']}")
    print(f"Objective: {rendered['objective']}")
    print(f"Domain: {rendered['domain']}")
    print(f"Status: {rendered['status']}")
    print(f"Autonomy mode: {rendered['autonomy_mode']}")
    print(f"Active track: {rendered['active_track_id']}")
    print(f"Tracks: {rendered['counts']['tracks_total']}")
    print(f"Iterations: {rendered['counts']['iterations_total']}")
    print(f"Records: {rendered['counts']['records_total']}")
    print(f"Saved-plan runs: {rendered['counts']['source_plan_records_total']}")
    print(f"Promotions: {rendered['counts']['promotions_total']}")
    print(f"Champion tracks: {rendered['counts']['champion_tracks_total']}")
    active_track_campaign_policy = rendered["active_track_effective_campaign_policy"]
    assert isinstance(active_track_campaign_policy, dict)
    active_campaign_payload = active_track_campaign_policy["effective_policy"]
    assert isinstance(active_campaign_payload, dict)
    active_campaign_sources = active_track_campaign_policy["effective_sources"]
    assert isinstance(active_campaign_sources, dict)
    print(
        "Active track campaign defaults: "
        f"stage={active_campaign_payload['stage']} [{active_campaign_sources['stage']}], "
        f"generator={active_campaign_payload['generator_id']} "
        f"[{active_campaign_sources['generator_id']}], "
        f"strategy={active_campaign_payload['strategy']} "
        f"[{active_campaign_sources['strategy']}], "
        f"beam_width={active_campaign_payload.get('beam_width') or 1} "
        f"[{active_campaign_sources['beam_width']}], "
        f"beam_groups={active_campaign_payload.get('beam_group_limit') or 1} "
        f"[{active_campaign_sources['beam_group_limit']}], "
        f"repeat={active_campaign_payload.get('repeat_count') or 1} "
        f"[{active_campaign_sources['repeat_count']}], "
        "generation_token_budget="
        f"{active_campaign_payload.get('max_generation_total_tokens') or 0} "
        f"[{active_campaign_sources['max_generation_total_tokens']}], "
        "benchmark_cost_budget="
        f"{active_campaign_payload.get('max_benchmark_total_cost') or 0} "
        f"[{active_campaign_sources['max_benchmark_total_cost']}], "
        "allow_flaky_promotion="
        f"{'yes' if active_campaign_payload.get('allow_flaky_promotion') else 'no'} "
        f"[{active_campaign_sources['allow_flaky_promotion']}], "
        "generation_timeout_retries="
        f"{active_campaign_payload.get('max_generation_timeout_retries') or 0} "
        f"[{active_campaign_sources['max_generation_timeout_retries']}], "
        "generation_provider_retries="
        f"{active_campaign_payload.get('max_generation_provider_retries') or 0} "
        f"[{active_campaign_sources['max_generation_provider_retries']}], "
        "generation_provider_transport_retries="
        f"{active_campaign_payload.get('max_generation_provider_transport_retries') or 0} "
        f"[{active_campaign_sources['max_generation_provider_transport_retries']}], "
        "generation_provider_auth_retries="
        f"{active_campaign_payload.get('max_generation_provider_auth_retries') or 0} "
        f"[{active_campaign_sources['max_generation_provider_auth_retries']}], "
        "generation_provider_rate_limit_retries="
        f"{active_campaign_payload.get('max_generation_provider_rate_limit_retries') or 0} "
        f"[{active_campaign_sources['max_generation_provider_rate_limit_retries']}], "
        "generation_process_retries="
        f"{active_campaign_payload.get('max_generation_process_retries') or 0} "
        f"[{active_campaign_sources['max_generation_process_retries']}]"
    )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_export_workspace_summary(args: argparse.Namespace) -> int:
    rendered = _render_workspace_summary(
        root=args.root,
        workspace_id=args.workspace_id,
    )
    output_format = _write_structured_payload(
        args.output,
        {
            "format_version": "autoharness.workspace_summary_export.v1",
            "exported_at": _utc_now(),
            "summary": rendered,
        },
        explicit_format=args.format,
    )
    print(f"Exported workspace summary to {args.output} ({output_format})")
    return 0


def _handle_export_root_report(args: argparse.Namespace) -> int:
    payload = {
        "format_version": "autoharness.root_report_export.v1",
        "exported_at": _utc_now(),
        **_render_root_report(
            root=args.root,
            requested_workspace_ids=list(args.workspace_id),
        ),
    }
    output_format = _write_structured_payload(
        args.output,
        payload,
        explicit_format=args.format,
    )
    print(f"Exported root report to {args.output} ({output_format})")
    return 0


def _handle_show_workspace(args: argparse.Namespace) -> int:
    rendered = _render_workspace_view(
        root=args.root,
        workspace_id=args.workspace_id,
    )
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    workspace_path = workspace_config_path(root=args.root, workspace_id=args.workspace_id)

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {rendered['workspace_id']}")
    print(f"Workspace path: {workspace_path}")
    print(f"Objective: {rendered['objective']}")
    print(f"Domain: {rendered['domain']}")
    print(f"Active track: {rendered['active_track_id']}")
    print(f"Status: {rendered['state']['status']}")
    print(f"Autonomy mode: {rendered['autonomy']['mode']}")
    print(
        "Benchmark policy: "
        f"search={rendered['benchmark_policy'].get('search_benchmark')}, "
        f"promotion={rendered['benchmark_policy'].get('promotion_benchmark')}, "
        f"regression={rendered['benchmark_policy'].get('regression_benchmark')}"
    )
    print(
        "Benchmark presets: "
        f"search={rendered['benchmark_policy'].get('search_preset') or '(none)'}, "
        f"promotion={rendered['benchmark_policy'].get('promotion_preset') or '(none)'}, "
        f"regression={rendered['benchmark_policy'].get('regression_preset') or '(none)'}"
    )
    workspace_campaign_policy = rendered["campaign_policy"]
    assert isinstance(workspace_campaign_policy, dict)
    print(
        "Workspace campaign policy: "
        f"stage={workspace_campaign_policy.get('stage') or '(default)'}, "
        f"generator={workspace_campaign_policy.get('generator_id') or '(default)'}, "
        f"strategy={workspace_campaign_policy.get('strategy') or '(default)'}, "
        f"beam_width={workspace_campaign_policy.get('beam_width') or '(default)'}, "
        f"beam_groups={workspace_campaign_policy.get('beam_group_limit') or '(default)'}"
    )
    active_track_policy = rendered["active_track_effective_policy"]
    assert isinstance(active_track_policy, dict)
    effective_policy = active_track_policy["effective_policy"]
    assert isinstance(effective_policy, dict)
    effective_sources = active_track_policy["effective_sources"]
    assert isinstance(effective_sources, dict)
    print(f"Active track effective policy: {rendered['active_track_id']}")
    print(
        "  Search benchmark: "
        f"{effective_policy['search_benchmark']} [{effective_sources['search_benchmark']}]"
    )
    print(
        "  Promotion benchmark: "
        f"{effective_policy['promotion_benchmark']} [{effective_sources['promotion_benchmark']}]"
    )
    print(
        "  Regression benchmark: "
        f"{effective_policy['regression_benchmark']} [{effective_sources['regression_benchmark']}]"
    )
    print(
        "  Search preset: "
        f"{effective_policy.get('search_preset') or '(none)'} [{effective_sources['search_preset']}]"
    )
    print(
        "  Promotion preset: "
        f"{effective_policy.get('promotion_preset') or '(none)'} [{effective_sources['promotion_preset']}]"
    )
    print(
        "  Regression preset: "
        f"{effective_policy.get('regression_preset') or '(none)'} [{effective_sources['regression_preset']}]"
    )
    active_track_campaign_policy = rendered["active_track_effective_campaign_policy"]
    assert isinstance(active_track_campaign_policy, dict)
    effective_campaign_policy = active_track_campaign_policy["effective_policy"]
    assert isinstance(effective_campaign_policy, dict)
    effective_campaign_sources = active_track_campaign_policy["effective_sources"]
    assert isinstance(effective_campaign_sources, dict)
    print(f"Active track effective campaign policy: {rendered['active_track_id']}")
    print(
        "  Stage: "
        f"{effective_campaign_policy['stage']} [{effective_campaign_sources['stage']}]"
    )
    print(
        "  Generator: "
        f"{effective_campaign_policy['generator_id']} "
        f"[{effective_campaign_sources['generator_id']}]"
    )
    print(
        "  Strategy: "
        f"{effective_campaign_policy['strategy']} "
        f"[{effective_campaign_sources['strategy']}]"
    )
    print(
        "  Beam width: "
        f"{effective_campaign_policy.get('beam_width') or 1} "
        f"[{effective_campaign_sources['beam_width']}]"
    )
    print(
        "  Beam groups: "
        f"{effective_campaign_policy.get('beam_group_limit') or 1} "
        f"[{effective_campaign_sources['beam_group_limit']}]"
    )
    print(
        "  Stage progression: "
        f"{effective_campaign_policy['stage_progression_mode']} "
        f"[{effective_campaign_sources['stage_progression_mode']}]"
    )
    intervention_classes = effective_campaign_policy.get("intervention_classes", [])
    assert isinstance(intervention_classes, list)
    print(
        "  Intervention classes: "
        f"{', '.join(intervention_classes) if intervention_classes else '(none)'} "
        f"[{effective_campaign_sources['intervention_classes']}]"
    )
    preflight_checks = effective_campaign_policy.get("preflight_checks", [])
    assert isinstance(preflight_checks, list)
    print(
        "  Preflight checks: "
        f"{', '.join(preflight_checks) if preflight_checks else '(none)'} "
        f"[{effective_campaign_sources['preflight_checks']}]"
    )
    print(
        "  Retry budgets: "
        f"generation={effective_campaign_policy.get('max_generation_retries') or 0} "
        f"[{effective_campaign_sources['max_generation_retries']}], "
        "generation_timeout="
        f"{effective_campaign_policy.get('max_generation_timeout_retries') or 0} "
        f"[{effective_campaign_sources['max_generation_timeout_retries']}], "
        "generation_provider="
        f"{effective_campaign_policy.get('max_generation_provider_retries') or 0} "
        f"[{effective_campaign_sources['max_generation_provider_retries']}], "
        "generation_provider_transport="
        f"{effective_campaign_policy.get('max_generation_provider_transport_retries') or 0} "
        f"[{effective_campaign_sources['max_generation_provider_transport_retries']}], "
        "generation_provider_auth="
        f"{effective_campaign_policy.get('max_generation_provider_auth_retries') or 0} "
        f"[{effective_campaign_sources['max_generation_provider_auth_retries']}], "
        "generation_provider_rate_limit="
        f"{effective_campaign_policy.get('max_generation_provider_rate_limit_retries') or 0} "
        f"[{effective_campaign_sources['max_generation_provider_rate_limit_retries']}], "
        "generation_process="
        f"{effective_campaign_policy.get('max_generation_process_retries') or 0} "
        f"[{effective_campaign_sources['max_generation_process_retries']}], "
        f"execution={effective_campaign_policy.get('max_execution_retries') or 0} "
        f"[{effective_campaign_sources['max_execution_retries']}], "
        "benchmark_timeout="
        f"{effective_campaign_policy.get('max_benchmark_timeout_retries') or 0} "
        f"[{effective_campaign_sources['max_benchmark_timeout_retries']}], "
        "benchmark_command="
        f"{effective_campaign_policy.get('max_benchmark_command_retries') or 0} "
        f"[{effective_campaign_sources['max_benchmark_command_retries']}], "
        f"inconclusive={effective_campaign_policy.get('max_inconclusive_retries') or 0} "
        f"[{effective_campaign_sources['max_inconclusive_retries']}]"
    )
    print(
        "  Stop budgets: "
        f"successes={effective_campaign_policy.get('max_successes') or 0} "
        f"[{effective_campaign_sources['max_successes']}], "
        f"promotions={effective_campaign_policy.get('max_promotions') or 0} "
        f"[{effective_campaign_sources['max_promotions']}]"
    )
    print(
        "  Auto-promote minimum stage: "
        f"{effective_campaign_policy.get('auto_promote_min_stage') or '(none)'} "
        f"[{effective_campaign_sources['auto_promote_min_stage']}]"
    )
    track_items = rendered["tracks"]
    assert isinstance(track_items, dict)
    print(f"Tracks: {', '.join(sorted(track_items)) or '(none)'}")
    print(f"Notes: {rendered['notes'] or '(none)'}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _render_tracks_view(*, root, workspace_id: str) -> dict[str, object]:
    workspace = load_workspace(root, workspace_id)
    state = load_workspace_state(root, workspace_id)
    rendered = {
        "workspace_id": workspace.workspace_id,
        "active_track_id": workspace.active_track_id,
        "state_active_track_id": state.active_track_id,
        "tracks": [],
    }

    for track_id in sorted(workspace.tracks):
        track = workspace.tracks[track_id]
        rendered["tracks"].append(
            {
                "track_id": track.track_id,
                "active": track_id == workspace.active_track_id,
                "status": track.status,
                "benchmark": track.benchmark,
                "objective": track.objective,
                "kind": track.kind,
                "campaign_id": track.campaign_id,
                "campaign_path": str(
                    track_config_path(
                        root=root,
                        workspace_id=workspace_id,
                        track_id=track_id,
                    )
                ),
                "promotion_policy_path": str(
                    promotion_policy_path(
                        root=root,
                        workspace_id=workspace_id,
                        track_id=track_id,
                    )
                ),
                "track_policy_path": str(
                    track_policy_path(
                        root=root,
                        workspace_id=workspace_id,
                        track_id=track_id,
                    )
                ),
            }
        )
    return rendered


def _handle_show_tracks(args: argparse.Namespace) -> int:
    rendered = _render_tracks_view(
        root=args.root,
        workspace_id=args.workspace_id,
    )
    workspace = load_workspace(args.root, args.workspace_id)

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {workspace.workspace_id}")
    print(f"Active track: {workspace.active_track_id}")
    for item in rendered["tracks"]:
        marker = "*" if item["active"] else "-"
        print(
            f"{marker} {item['track_id']}: "
            f"status={item['status']}, benchmark={item['benchmark']}, kind={item['kind']}, "
            f"campaign_id={item['campaign_id']}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _render_record_summary(*, root, workspace_id: str, track_id: str, record) -> dict[str, object] | None:
    if record is None:
        return None
    return {
        "record_id": record.record_id,
        "created_at": record.created_at,
        "iteration_id": record.iteration_id,
        "adapter_id": record.adapter_id,
        "benchmark_name": record.benchmark_name,
        "stage": record.stage,
        "status": record.status,
        "success": record.success,
        "hypothesis": record.hypothesis,
        "source_plan_path": record.source_plan_path,
        "record_path": str(
            registry_dir_path(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
            / f"{record.record_id}.json"
        ),
    }


def _render_promotion_summary(*, root, workspace_id: str, track_id: str, promotion) -> dict[str, object] | None:
    if promotion is None:
        return None
    return {
        "promotion_id": promotion.promotion_id,
        "created_at": promotion.created_at,
        "record_id": promotion.record_id,
        "iteration_id": promotion.iteration_id,
        "target_root": promotion.target_root,
        "notes": promotion.notes,
        "promotion_path": str(
            promotions_dir_path(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
            / f"{promotion.promotion_id}.json"
        ),
    }


def _render_track_summary(
    *,
    root,
    workspace_id: str,
    requested_track_id: str | None,
) -> dict[str, object]:
    workspace, _, track_id = _resolve_workspace_track(
        root=root,
        workspace_id=workspace_id,
        requested_track_id=requested_track_id,
    )
    track = workspace.tracks[track_id]
    records = list_track_benchmark_records(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    promotions = list_track_promotion_records(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    try:
        champion = load_champion_manifest(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
    except FileNotFoundError:
        champion = None

    status_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    stage_status_counts: dict[str, dict[str, int]] = {}
    source_plan_stage_counts: dict[str, int] = {}
    source_plan_total = 0
    for record in records:
        status_counts[record.status] = int(status_counts.get(record.status, 0)) + 1
        stage_key = record.stage or "unscoped"
        stage_counts[stage_key] = int(stage_counts.get(stage_key, 0)) + 1
        stage_bucket = stage_status_counts.setdefault(stage_key, {})
        stage_bucket[record.status] = int(stage_bucket.get(record.status, 0)) + 1
        if record.source_plan_path is not None:
            source_plan_total += 1
            source_plan_stage_counts[stage_key] = int(
                source_plan_stage_counts.get(stage_key, 0)
            ) + 1

    latest_record = max(
        records,
        key=lambda record: (record.created_at, record.record_id),
        default=None,
    )
    latest_promotion = max(
        promotions,
        key=lambda promotion: (promotion.created_at, promotion.promotion_id),
        default=None,
    )
    effective_campaign_policy = _resolved_track_campaign_policy_details(
        workspace=workspace,
        track_id=track_id,
    )

    return {
        "workspace_id": workspace_id,
        "track_id": track_id,
        "active": track_id == workspace.active_track_id,
        "status": track.status,
        "benchmark": track.benchmark,
        "objective": track.objective,
        "kind": track.kind,
        "campaign_id": track.campaign_id,
        "benchmark_reference_ids": list(track.benchmark_reference_ids),
        "paths": {
            "track_dir": str(
                track_dir_path(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                )
            ),
            "campaign_path": str(
                track_config_path(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                )
            ),
            "registry_dir": str(
                registry_dir_path(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                )
            ),
            "promotions_dir": str(
                promotions_dir_path(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                )
            ),
            "champion_path": str(
                track_dir_path(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                )
                / "champion.json"
            ),
        },
        "records": {
            "total": len(records),
            "by_status": status_counts,
            "by_stage": stage_counts,
            "by_stage_status": stage_status_counts,
            "source_plan_total": source_plan_total,
            "source_plan_by_stage": source_plan_stage_counts,
            "latest": _render_record_summary(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
                record=latest_record,
            ),
        },
        "promotions": {
            "total": len(promotions),
            "latest": _render_promotion_summary(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
                promotion=latest_promotion,
            ),
        },
        "effective_campaign_policy": _render_campaign_default_snapshot(
            effective_campaign_policy
        ),
        "champion": champion.to_dict() if champion is not None else None,
    }


def _render_track_view(
    *,
    root,
    workspace_id: str,
    requested_track_id: str | None,
) -> dict[str, object]:
    workspace, _, track_id = _resolve_workspace_track(
        root=root,
        workspace_id=workspace_id,
        requested_track_id=requested_track_id,
    )
    track = workspace.tracks[track_id]
    effective_campaign_policy = _resolved_track_campaign_policy_details(
        workspace=workspace,
        track_id=track_id,
    )
    return {
        "workspace_id": workspace_id,
        "track_id": track_id,
        "workspace_path": str(workspace_config_path(root=root, workspace_id=workspace_id)),
        "track_path": str(
            track_config_path(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
        ),
        "effective_campaign_policy": effective_campaign_policy,
        **track.to_dict(),
    }


def _handle_show_track_summary(args: argparse.Namespace) -> int:
    rendered = _render_track_summary(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    track_id = str(rendered["track_id"])
    status = str(rendered["status"])
    benchmark = str(rendered["benchmark"])
    objective = str(rendered["objective"])
    kind = str(rendered["kind"])
    record_total = int(rendered["records"]["total"])
    source_plan_total = int(rendered["records"]["source_plan_total"])
    promotion_total = int(rendered["promotions"]["total"])
    status_counts = rendered["records"]["by_status"]
    assert isinstance(status_counts, dict)
    latest_record = rendered["records"]["latest"]
    latest_promotion = rendered["promotions"]["latest"]
    effective_campaign_policy = rendered["effective_campaign_policy"]
    assert isinstance(effective_campaign_policy, dict)
    campaign_payload = effective_campaign_policy["effective_policy"]
    assert isinstance(campaign_payload, dict)
    campaign_sources = effective_campaign_policy["effective_sources"]
    assert isinstance(campaign_sources, dict)
    champion = rendered["champion"]

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Active: {'yes' if rendered['active'] else 'no'}")
    print(f"Status: {status}")
    print(f"Benchmark: {benchmark}")
    print(f"Objective: {objective}")
    print(f"Kind: {kind}")
    print(f"Records: {record_total}")
    print(f"Saved-plan runs: {source_plan_total}")
    print(
        "Campaign defaults: "
        f"stage={campaign_payload['stage']} [{campaign_sources['stage']}], "
        f"generator={campaign_payload['generator_id']} "
        f"[{campaign_sources['generator_id']}], "
        f"strategy={campaign_payload['strategy']} "
        f"[{campaign_sources['strategy']}], "
        f"beam_width={campaign_payload.get('beam_width') or 1} "
        f"[{campaign_sources['beam_width']}], "
        f"beam_groups={campaign_payload.get('beam_group_limit') or 1} "
        f"[{campaign_sources['beam_group_limit']}], "
        f"repeat={campaign_payload.get('repeat_count') or 1} "
        f"[{campaign_sources['repeat_count']}], "
        "generation_token_budget="
        f"{campaign_payload.get('max_generation_total_tokens') or 0} "
        f"[{campaign_sources['max_generation_total_tokens']}], "
        "benchmark_cost_budget="
        f"{campaign_payload.get('max_benchmark_total_cost') or 0} "
        f"[{campaign_sources['max_benchmark_total_cost']}], "
        "allow_flaky_promotion="
        f"{'yes' if campaign_payload.get('allow_flaky_promotion') else 'no'} "
        f"[{campaign_sources['allow_flaky_promotion']}], "
        "generation_timeout_retries="
        f"{campaign_payload.get('max_generation_timeout_retries') or 0} "
        f"[{campaign_sources['max_generation_timeout_retries']}], "
        "generation_provider_retries="
        f"{campaign_payload.get('max_generation_provider_retries') or 0} "
        f"[{campaign_sources['max_generation_provider_retries']}], "
        "generation_provider_transport_retries="
        f"{campaign_payload.get('max_generation_provider_transport_retries') or 0} "
        f"[{campaign_sources['max_generation_provider_transport_retries']}], "
        "generation_provider_auth_retries="
        f"{campaign_payload.get('max_generation_provider_auth_retries') or 0} "
        f"[{campaign_sources['max_generation_provider_auth_retries']}], "
        "generation_provider_rate_limit_retries="
        f"{campaign_payload.get('max_generation_provider_rate_limit_retries') or 0} "
        f"[{campaign_sources['max_generation_provider_rate_limit_retries']}], "
        "generation_process_retries="
        f"{campaign_payload.get('max_generation_process_retries') or 0} "
        f"[{campaign_sources['max_generation_process_retries']}]"
    )
    if status_counts:
        print(
            "Record status counts: "
            + ", ".join(f"{key}={status_counts[key]}" for key in sorted(status_counts))
        )
    print(f"Promotions: {promotion_total}")
    if latest_record is not None:
        assert isinstance(latest_record, dict)
        print(
            f"Latest record: {latest_record['record_id']} "
            f"({latest_record['status']}, stage={latest_record.get('stage') or 'unscoped'})"
        )
    if latest_promotion is not None:
        assert isinstance(latest_promotion, dict)
        print(f"Latest promotion: {latest_promotion['promotion_id']}")
    if champion is not None:
        assert isinstance(champion, dict)
        print(f"Champion record: {champion['record_id']}")
    else:
        print("Champion record: (none)")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_export_track_summary(args: argparse.Namespace) -> int:
    rendered = _render_track_summary(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    output_format = _write_structured_payload(
        args.output,
        {
            "format_version": "autoharness.track_summary_export.v1",
            "exported_at": _utc_now(),
            "summary": rendered,
        },
        explicit_format=args.format,
    )
    print(f"Exported track summary to {args.output} ({output_format})")
    return 0


def _render_track_artifacts(
    *,
    root,
    workspace_id: str,
    requested_track_id: str | None,
) -> dict[str, object]:
    workspace, _, track_id = _resolve_workspace_track(
        root=root,
        workspace_id=workspace_id,
        requested_track_id=requested_track_id,
    )
    track = workspace.tracks[track_id]
    track_dir = track_dir_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    registry_dir = registry_dir_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    promotions_dir = promotions_dir_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    campaign_path = track_config_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    promotion_policy_file = promotion_policy_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    track_policy_file = track_policy_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    champion_path = track_dir / "champion.json"

    promotion_files = []
    if promotions_dir.exists():
        for path in sorted(promotions_dir.glob("promote_*.json")):
            if path.name.endswith(".parsed_artifact_sources.json"):
                continue
            promotion_id = path.stem
            patch_path = promotions_dir / f"{promotion_id}.patch"
            parsed_artifact_sources_path = (
                promotions_dir / f"{promotion_id}.parsed_artifact_sources.json"
            )
            promotion_files.append(
                {
                    "promotion_id": promotion_id,
                    "path": str(path),
                    "diff_path": str(patch_path) if patch_path.exists() else None,
                    "parsed_artifact_sources_path": (
                        str(parsed_artifact_sources_path)
                        if parsed_artifact_sources_path.exists()
                        else None
                    ),
                }
            )

    try:
        champion = load_champion_manifest(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
    except FileNotFoundError:
        champion = None

    registry_files = []
    if registry_dir.exists():
        for path in sorted(registry_dir.glob("*.json")):
            record = load_benchmark_record(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
                record_id=path.stem,
            )
            source_plan_artifact_path = None
            if record.iteration_id is not None:
                candidate_source_plan_path = (
                    iteration_dir_path(
                        root=root,
                        workspace_id=workspace_id,
                        iteration_id=record.iteration_id,
                    )
                    / "source_plan.json"
                )
                if candidate_source_plan_path.exists():
                    source_plan_artifact_path = str(candidate_source_plan_path)
            registry_files.append(
                {
                    "record_id": path.stem,
                    "path": str(path),
                    "iteration_id": record.iteration_id,
                    "source_plan_artifact_path": source_plan_artifact_path,
                }
            )

    source_plan_artifacts = [
        {
            "record_id": item["record_id"],
            "iteration_id": item["iteration_id"],
            "path": item["source_plan_artifact_path"],
            "current_champion": (
                champion is not None and item["record_id"] == champion.record_id
            ),
        }
        for item in registry_files
        if item["source_plan_artifact_path"] is not None
    ]

    champion_source_plan_artifact_path = None
    if champion is not None and champion.iteration_id is not None:
        candidate_source_plan_path = (
            iteration_dir_path(
                root=root,
                workspace_id=workspace_id,
                iteration_id=champion.iteration_id,
            )
            / "source_plan.json"
        )
        if candidate_source_plan_path.exists():
            champion_source_plan_artifact_path = str(candidate_source_plan_path)

    return {
        "workspace_id": workspace_id,
        "track_id": track_id,
        "active": track_id == workspace.active_track_id,
        "status": track.status,
        "artifacts": {
            "track_dir": str(track_dir),
            "campaign_path": str(campaign_path),
            "promotion_policy_path": str(promotion_policy_file),
            "track_policy_path": str(track_policy_file),
            "champion_path": str(champion_path),
            "registry_dir": str(registry_dir),
            "promotions_dir": str(promotions_dir),
        },
        "exists": {
            "campaign": campaign_path.exists(),
            "promotion_policy": promotion_policy_file.exists(),
            "track_policy": track_policy_file.exists(),
            "champion": champion_path.exists(),
            "registry_dir": registry_dir.exists(),
            "promotions_dir": promotions_dir.exists(),
        },
        "registry_records": registry_files,
        "source_plan_artifacts": source_plan_artifacts,
        "promotions": promotion_files,
        "champion_artifacts": (
            {
                "record_id": champion.record_id,
                "iteration_id": champion.iteration_id,
                "promotion_id": champion.promotion_id,
                "manifest_path": str(champion_path),
                "record_path": champion.record_path,
                "promotion_path": champion.promotion_path,
                "diff_path": champion.diff_path,
                "parsed_artifact_sources_path": champion.parsed_artifact_sources_path,
                "source_plan_artifact_path": champion_source_plan_artifact_path,
            }
            if champion is not None
            else None
        ),
    }


def _handle_show_track_artifacts(args: argparse.Namespace) -> int:
    rendered = _render_track_artifacts(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    track_id = str(rendered["track_id"])
    status = str(rendered["status"])
    registry_records = rendered["registry_records"]
    source_plan_artifacts = rendered["source_plan_artifacts"]
    promotions = rendered["promotions"]
    champion_artifacts = rendered["champion_artifacts"]
    assert isinstance(registry_records, list)
    assert isinstance(source_plan_artifacts, list)
    assert isinstance(promotions, list)

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Status: {status}")
    artifacts = rendered["artifacts"]
    assert isinstance(artifacts, dict)
    print(f"Track dir: {artifacts['track_dir']}")
    print(f"Registry records: {len(registry_records)}")
    print(f"Planned run artifacts: {len(source_plan_artifacts)}")
    print(f"Promotion records: {len(promotions)}")
    print(f"Champion manifest: {'present' if champion_artifacts is not None else 'absent'}")
    if champion_artifacts is not None:
        assert isinstance(champion_artifacts, dict)
        if champion_artifacts.get("source_plan_artifact_path") is not None:
            print(f"Champion source plan: {champion_artifacts['source_plan_artifact_path']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_track(args: argparse.Namespace) -> int:
    rendered = _render_track_view(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    track_id = str(rendered["track_id"])

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    benchmark_reference_ids = rendered["benchmark_reference_ids"]
    assert isinstance(benchmark_reference_ids, list)
    benchmark_references = ", ".join(str(value) for value in benchmark_reference_ids) or "(none)"
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Workspace path: {rendered['workspace_path']}")
    print(f"Track path: {rendered['track_path']}")
    print(f"Status: {rendered['status']}")
    print(f"Benchmark: {rendered['benchmark']}")
    print(f"Objective: {rendered['objective']}")
    print(f"Kind: {rendered['kind']}")
    print(f"Campaign id: {rendered['campaign_id']}")
    print(f"Benchmark references: {benchmark_references}")
    effective_campaign_policy = rendered["effective_campaign_policy"]
    assert isinstance(effective_campaign_policy, dict)
    policy_payload = effective_campaign_policy["effective_policy"]
    assert isinstance(policy_payload, dict)
    policy_sources = effective_campaign_policy["effective_sources"]
    assert isinstance(policy_sources, dict)
    print(
        "Campaign policy: "
        f"stage={policy_payload['stage']} [{policy_sources['stage']}], "
        f"generator={policy_payload['generator_id']} [{policy_sources['generator_id']}], "
        f"strategy={policy_payload['strategy']} [{policy_sources['strategy']}], "
        f"beam_width={policy_payload.get('beam_width') or 1} [{policy_sources['beam_width']}], "
        f"beam_groups={policy_payload.get('beam_group_limit') or 1} "
        f"[{policy_sources['beam_group_limit']}], "
        f"stage_progression={policy_payload['stage_progression_mode']} "
        f"[{policy_sources['stage_progression_mode']}]"
    )
    intervention_classes = policy_payload.get("intervention_classes", [])
    assert isinstance(intervention_classes, list)
    print(
        "Campaign interventions: "
        f"{', '.join(intervention_classes) if intervention_classes else '(none)'} "
        f"[{policy_sources['intervention_classes']}]"
    )
    preflight_checks = policy_payload.get("preflight_checks", [])
    assert isinstance(preflight_checks, list)
    print(
        "Campaign preflight checks: "
        f"{', '.join(preflight_checks) if preflight_checks else '(none)'} "
        f"[{policy_sources['preflight_checks']}]"
    )
    print(
        "Campaign retries: "
        f"generation={policy_payload.get('max_generation_retries') or 0} "
        f"[{policy_sources['max_generation_retries']}], "
        "generation_timeout="
        f"{policy_payload.get('max_generation_timeout_retries') or 0} "
        f"[{policy_sources['max_generation_timeout_retries']}], "
        "generation_provider="
        f"{policy_payload.get('max_generation_provider_retries') or 0} "
        f"[{policy_sources['max_generation_provider_retries']}], "
        "generation_provider_transport="
        f"{policy_payload.get('max_generation_provider_transport_retries') or 0} "
        f"[{policy_sources['max_generation_provider_transport_retries']}], "
        "generation_provider_auth="
        f"{policy_payload.get('max_generation_provider_auth_retries') or 0} "
        f"[{policy_sources['max_generation_provider_auth_retries']}], "
        "generation_provider_rate_limit="
        f"{policy_payload.get('max_generation_provider_rate_limit_retries') or 0} "
        f"[{policy_sources['max_generation_provider_rate_limit_retries']}], "
        "generation_process="
        f"{policy_payload.get('max_generation_process_retries') or 0} "
        f"[{policy_sources['max_generation_process_retries']}], "
        f"execution={policy_payload.get('max_execution_retries') or 0} "
        f"[{policy_sources['max_execution_retries']}], "
        "benchmark_timeout="
        f"{policy_payload.get('max_benchmark_timeout_retries') or 0} "
        f"[{policy_sources['max_benchmark_timeout_retries']}], "
        "benchmark_command="
        f"{policy_payload.get('max_benchmark_command_retries') or 0} "
        f"[{policy_sources['max_benchmark_command_retries']}], "
        f"inconclusive={policy_payload.get('max_inconclusive_retries') or 0} "
        f"[{policy_sources['max_inconclusive_retries']}]"
    )
    print(
        "Campaign stop budgets: "
        f"successes={policy_payload.get('max_successes') or 0} "
        f"[{policy_sources['max_successes']}], "
        f"promotions={policy_payload.get('max_promotions') or 0} "
        f"[{policy_sources['max_promotions']}]"
    )
    print(
        "Campaign auto-promote minimum stage: "
        f"{policy_payload.get('auto_promote_min_stage') or '(none)'} "
        f"[{policy_sources['auto_promote_min_stage']}]"
    )
    evaluator = rendered["evaluator"]
    assert isinstance(evaluator, dict)
    print(f"Evaluator version: {evaluator['evaluator_version']}")
    print(f"Judge model: {evaluator['judge_model']}")
    print(f"Diagnostic model: {evaluator['diagnostic_model']}")
    print(f"Max diagnostic tasks: {evaluator['max_diagnostic_tasks']}")
    print(f"Min judge pass rate: {evaluator['min_judge_pass_rate']}")
    print(f"Notes: {rendered['notes'] or '(none)'}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _render_promotion_policy_view(
    *,
    root,
    workspace_id: str,
    requested_track_id: str | None,
) -> dict[str, object]:
    _, _, track_id = _resolve_workspace_track(
        root=root,
        workspace_id=workspace_id,
        requested_track_id=requested_track_id,
    )
    policy_path = promotion_policy_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    try:
        policy = load_promotion_policy(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
    except FileNotFoundError:
        return {
            "workspace_id": workspace_id,
            "track_id": track_id,
            "policy_path": str(policy_path),
            "exists": False,
            "policy": None,
        }

    return {
        "workspace_id": workspace_id,
        "track_id": track_id,
        "policy_path": str(policy_path),
        "exists": True,
        "policy": policy.to_dict(),
    }


def _render_track_report(
    *,
    root,
    workspace_id: str,
    requested_track_id: str | None,
) -> dict[str, object]:
    summary = _render_track_summary(
        root=root,
        workspace_id=workspace_id,
        requested_track_id=requested_track_id,
    )
    track_id = str(summary["track_id"])
    provider_profiles = load_provider_profiles(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    return {
        "track": _render_track_view(
            root=root,
            workspace_id=workspace_id,
            requested_track_id=track_id,
        ),
        "track_summary": summary,
        "effective_track_policy": _render_track_policy_view(
            root=root,
            workspace_id=workspace_id,
            requested_track_id=track_id,
        ),
        "promotion_policy": _render_promotion_policy_view(
            root=root,
            workspace_id=workspace_id,
            requested_track_id=track_id,
        ),
        "provider_profiles": {
            "profile_path": str(
                provider_profiles_path(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                )
            ),
            "profile_total": len(provider_profiles),
            "profiles": provider_profiles,
            "profile_summaries": summarize_provider_profiles(provider_profiles),
        },
        "event_metrics": aggregate_event_metrics(
            load_workspace_events(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
        ),
        "track_artifacts": _render_track_artifacts(
            root=root,
            workspace_id=workspace_id,
            requested_track_id=track_id,
        ),
    }


def _render_workspace_report(*, root, workspace_id: str) -> dict[str, object]:
    tracks_view = _render_tracks_view(
        root=root,
        workspace_id=workspace_id,
    )
    track_items = tracks_view["tracks"]
    assert isinstance(track_items, list)
    return {
        "workspace": _render_workspace_view(
            root=root,
            workspace_id=workspace_id,
        ),
        "workspace_summary": _render_workspace_summary(
            root=root,
            workspace_id=workspace_id,
        ),
        "tracks": tracks_view,
        "event_metrics": aggregate_event_metrics(
            load_workspace_events(
                root=root,
                workspace_id=workspace_id,
            )
        ),
        "track_reports": [
            (
                lambda track_id, track_report: {
                    "track_id": track_id,
                    "summary": track_report["track_summary"],
                    **track_report,
                }
            )(
                str(item["track_id"]),
                _render_track_report(
                    root=root,
                    workspace_id=workspace_id,
                    requested_track_id=str(item["track_id"]),
                ),
            )
            for item in track_items
        ],
    }


def _handle_export_workspace_report(args: argparse.Namespace) -> int:
    payload = {
        "format_version": "autoharness.workspace_report_export.v1",
        "exported_at": _utc_now(),
        **_render_workspace_report(
            root=args.root,
            workspace_id=args.workspace_id,
        ),
    }
    output_format = _write_structured_payload(
        args.output,
        payload,
        explicit_format=args.format,
    )
    print(f"Exported workspace report to {args.output} ({output_format})")
    return 0


def _write_events_jsonl(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(event, sort_keys=False) + "\n" for event in events),
        encoding="utf-8",
    )


def _write_workspace_bundle(
    *,
    root: Path,
    workspace_id: str,
    output_dir: Path,
    explicit_format: str | None,
    force: bool,
    skip_listings: bool,
    skip_track_reports: bool,
    skip_champions: bool,
) -> dict[str, object]:
    _prepare_export_dir(output_dir, force=force)

    workspace = load_workspace(root, workspace_id)

    structured_format = explicit_format or "json"
    suffix = "json" if structured_format == "json" else "yaml"

    workspace_report = _render_workspace_report(
        root=root,
        workspace_id=workspace_id,
    )
    state = load_workspace_state(root, workspace_id)

    workspace_report_path = output_dir / f"workspace_report.{suffix}"
    iterations_path = output_dir / "listings" / f"iterations.{suffix}"
    records_path = output_dir / "listings" / f"records.{suffix}"
    promotions_path = output_dir / "listings" / f"promotions.{suffix}"
    workspace_events_path = output_dir / "events.jsonl"

    _write_structured_payload(
        workspace_report_path,
        workspace_report,
        explicit_format=explicit_format,
    )
    workspace_events = load_workspace_events(root=root, workspace_id=workspace_id)
    _write_events_jsonl(workspace_events_path, workspace_events)
    if not skip_listings:
        iterations_listing = {
            "format_version": "autoharness.iteration_export.v1",
            "exported_at": _utc_now(),
            **_build_iteration_listing_payload(
                root=root,
                workspace_id=workspace_id,
                state=state,
                spec=IterationQuerySpec(),
            ),
        }
        records_listing = {
            "format_version": "autoharness.record_export.v1",
            "exported_at": _utc_now(),
            **_build_record_listing_payload(
                root=root,
                workspace_id=workspace_id,
                spec=RecordQuerySpec(),
            ),
        }
        promotions_listing = {
            "format_version": "autoharness.promotion_export.v1",
            "exported_at": _utc_now(),
            **_build_promotion_listing_payload(
                root=root,
                workspace_id=workspace_id,
                spec=PromotionQuerySpec(),
            ),
        }
        _write_structured_payload(
            iterations_path,
            iterations_listing,
            explicit_format=explicit_format,
        )
        _write_structured_payload(
            records_path,
            records_listing,
            explicit_format=explicit_format,
        )
        _write_structured_payload(
            promotions_path,
            promotions_listing,
            explicit_format=explicit_format,
        )

    track_report_entries = []
    champion_bundle_entries = []
    for track_id in sorted(workspace.tracks):
        if not skip_track_reports:
            track_report = _render_track_report(
                root=root,
                workspace_id=workspace_id,
                requested_track_id=track_id,
            )
            track_report_path = output_dir / "tracks" / track_id / f"report.{suffix}"
            _write_structured_payload(
                track_report_path,
                {
                    "format_version": "autoharness.track_report_export.v1",
                    "exported_at": _utc_now(),
                    **track_report,
                },
                explicit_format=explicit_format,
            )
            track_report_entries.append(
                {
                    "track_id": track_id,
                    "path": str(track_report_path.relative_to(output_dir)),
                }
            )
        if not skip_champions:
            try:
                champion_bundle = _export_champion_bundle(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                    output_dir=output_dir / "champions" / track_id,
                    force=True,
                )
            except SystemExit as exc:
                if "No champion manifest" in str(exc) or "not found" in str(exc):
                    champion_bundle = None
                else:
                    raise
            if champion_bundle is not None:
                champion_bundle_entries.append(
                    {
                        "track_id": track_id,
                        "path": str((Path("champions") / track_id).as_posix()),
                        "record_id": champion_bundle["record_id"],
                        "promotion_id": champion_bundle["promotion_id"],
                    }
                )

    bundle_manifest_path = output_dir / f"bundle_manifest.{suffix}"
    bundle_manifest = {
        "format_version": "autoharness.workspace_bundle.v1",
        "exported_at": _utc_now(),
        "workspace_id": workspace_id,
        "artifact_format": structured_format,
        "includes": {
            "listings": not skip_listings,
            "track_reports": not skip_track_reports,
            "champion_bundles": not skip_champions,
            "event_log": True,
        },
        "artifacts": {
            "workspace_report_path": str(workspace_report_path.relative_to(output_dir)),
            "event_log_path": str(workspace_events_path.relative_to(output_dir)),
            "iterations_path": (
                str(iterations_path.relative_to(output_dir))
                if not skip_listings
                else None
            ),
            "records_path": (
                str(records_path.relative_to(output_dir))
                if not skip_listings
                else None
            ),
            "promotions_path": (
                str(promotions_path.relative_to(output_dir))
                if not skip_listings
                else None
            ),
            "track_reports": track_report_entries,
            "champion_bundles": champion_bundle_entries,
        },
    }
    _write_structured_payload(
        bundle_manifest_path,
        bundle_manifest,
        explicit_format=explicit_format,
    )
    return {
        "workspace_id": workspace_id,
        "bundle_path": output_dir,
        "manifest_path": bundle_manifest_path,
        "artifact_format": structured_format,
        "includes": bundle_manifest["includes"],
        "track_report_total": len(track_report_entries),
        "champion_bundle_total": len(champion_bundle_entries),
    }


def _handle_export_workspace_bundle(args: argparse.Namespace) -> int:
    rendered = _write_workspace_bundle(
        root=args.root,
        workspace_id=args.workspace_id,
        output_dir=args.output,
        explicit_format=args.format,
        force=args.force,
        skip_listings=bool(args.skip_listings),
        skip_track_reports=bool(args.skip_track_reports),
        skip_champions=bool(args.skip_champions),
    )
    includes = rendered["includes"]
    assert isinstance(includes, dict)
    print(f"Workspace: {args.workspace_id}")
    print(f"Bundle path: {rendered['bundle_path']}")
    print(f"Bundle manifest: {rendered['manifest_path']}")
    print(f"Listings: {'included' if includes.get('listings') else 'skipped'}")
    print(
        "Track reports: "
        + (
            "skipped"
            if not includes.get("track_reports")
            else str(rendered["track_report_total"])
        )
    )
    print(
        "Champion bundles: "
        + (
            "skipped"
            if not includes.get("champion_bundles")
            else str(rendered["champion_bundle_total"])
        )
    )
    return 0


def _write_root_bundle(
    *,
    root: Path,
    requested_workspace_ids: list[str],
    output_dir: Path,
    explicit_format: str | None,
    force: bool,
    skip_listings: bool,
    skip_track_reports: bool,
    skip_champions: bool,
) -> dict[str, object]:
    _prepare_export_dir(output_dir, force=force)

    structured_format = explicit_format or "json"
    suffix = "json" if structured_format == "json" else "yaml"
    root_report = {
        "format_version": "autoharness.root_report_export.v1",
        "exported_at": _utc_now(),
        **_render_root_report(
            root=root,
            requested_workspace_ids=requested_workspace_ids,
        ),
    }
    root_report_path = output_dir / f"root_report.{suffix}"
    _write_structured_payload(
        root_report_path,
        root_report,
        explicit_format=explicit_format,
    )

    requested_workspace_id_set = set(requested_workspace_ids)
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not requested_workspace_id_set or workspace_id in requested_workspace_id_set
    ]
    workspace_bundles = []
    for workspace_id in selected_workspace_ids:
        nested_bundle_dir = output_dir / "workspaces" / workspace_id
        workspace_rendered = _write_workspace_bundle(
            root=root,
            workspace_id=workspace_id,
            output_dir=nested_bundle_dir,
            explicit_format=explicit_format,
            force=True,
            skip_listings=skip_listings,
            skip_track_reports=skip_track_reports,
            skip_champions=skip_champions,
        )
        workspace_bundles.append(
            {
                "workspace_id": workspace_id,
                "path": str(nested_bundle_dir.relative_to(output_dir)),
                "track_report_total": workspace_rendered["track_report_total"],
                "champion_bundle_total": workspace_rendered["champion_bundle_total"],
            }
        )

    bundle_manifest_path = output_dir / f"bundle_manifest.{suffix}"
    bundle_manifest = {
        "format_version": "autoharness.root_bundle.v1",
        "exported_at": _utc_now(),
        "workspace_filter": list(requested_workspace_ids),
        "artifact_format": structured_format,
        "includes": {
            "workspace_bundles": True,
            "listings": not skip_listings,
            "track_reports": not skip_track_reports,
            "champion_bundles": not skip_champions,
        },
        "artifacts": {
            "root_report_path": str(root_report_path.relative_to(output_dir)),
            "workspace_bundles": workspace_bundles,
        },
    }
    _write_structured_payload(
        bundle_manifest_path,
        bundle_manifest,
        explicit_format=explicit_format,
    )
    return {
        "bundle_path": output_dir,
        "manifest_path": bundle_manifest_path,
        "artifact_format": structured_format,
        "workspace_total": len(workspace_bundles),
        "includes": bundle_manifest["includes"],
    }


def _handle_export_root_bundle(args: argparse.Namespace) -> int:
    rendered = _write_root_bundle(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
        output_dir=args.output,
        explicit_format=args.format,
        force=args.force,
        skip_listings=bool(args.skip_listings),
        skip_track_reports=bool(args.skip_track_reports),
        skip_champions=bool(args.skip_champions),
    )
    includes = rendered["includes"]
    assert isinstance(includes, dict)
    print(f"Bundle path: {rendered['bundle_path']}")
    print(f"Bundle manifest: {rendered['manifest_path']}")
    print(f"Workspace bundles: {rendered['workspace_total']}")
    print(f"Listings: {'included' if includes.get('listings') else 'skipped'}")
    print(
        "Track reports: "
        + ("included" if includes.get("track_reports") else "skipped")
    )
    print(
        "Champion bundles: "
        + ("included" if includes.get("champion_bundles") else "skipped")
    )
    return 0


def _handle_export_track_bundle(args: argparse.Namespace) -> int:
    _, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    output_dir = args.output
    _prepare_export_dir(output_dir, force=args.force)

    structured_format = args.format or "json"
    suffix = "json" if structured_format == "json" else "yaml"

    track_report = {
        "format_version": "autoharness.track_report_export.v1",
        "exported_at": _utc_now(),
        **_render_track_report(
            root=args.root,
            workspace_id=args.workspace_id,
            requested_track_id=track_id,
        ),
    }
    track_report_path = output_dir / f"track_report.{suffix}"
    iterations_path = output_dir / "listings" / f"iterations.{suffix}"
    records_path = output_dir / "listings" / f"records.{suffix}"
    promotions_path = output_dir / "listings" / f"promotions.{suffix}"

    _write_structured_payload(
        track_report_path,
        track_report,
        explicit_format=args.format,
    )
    if not args.skip_listings:
        state = load_workspace_state(args.root, args.workspace_id)
        iterations_listing = {
            "format_version": "autoharness.iteration_export.v1",
            "exported_at": _utc_now(),
            **_build_iteration_listing_payload(
                root=args.root,
                workspace_id=args.workspace_id,
                state=state,
                spec=IterationQuerySpec(track_id=track_id),
            ),
        }
        records_listing = {
            "format_version": "autoharness.record_export.v1",
            "exported_at": _utc_now(),
            **_build_record_listing_payload(
                root=args.root,
                workspace_id=args.workspace_id,
                spec=RecordQuerySpec(track_id=track_id),
            ),
        }
        promotions_listing = {
            "format_version": "autoharness.promotion_export.v1",
            "exported_at": _utc_now(),
            **_build_promotion_listing_payload(
                root=args.root,
                workspace_id=args.workspace_id,
                spec=PromotionQuerySpec(track_id=track_id),
            ),
        }
        _write_structured_payload(
            iterations_path,
            iterations_listing,
            explicit_format=args.format,
        )
        _write_structured_payload(
            records_path,
            records_listing,
            explicit_format=args.format,
        )
        _write_structured_payload(
            promotions_path,
            promotions_listing,
            explicit_format=args.format,
        )

    champion_bundle_entry = None
    if not args.skip_champion:
        try:
            champion_bundle = _export_champion_bundle(
                root=args.root,
                workspace_id=args.workspace_id,
                track_id=track_id,
                output_dir=output_dir / "champion",
                force=True,
            )
        except SystemExit as exc:
            if "No champion manifest" in str(exc) or "not found" in str(exc):
                champion_bundle = None
            else:
                raise
        if champion_bundle is not None:
            champion_bundle_entry = {
                "path": "champion",
                "record_id": champion_bundle["record_id"],
                "promotion_id": champion_bundle["promotion_id"],
            }

    bundle_manifest_path = output_dir / f"bundle_manifest.{suffix}"
    track_events_path = output_dir / "events.jsonl"
    _write_events_jsonl(
        track_events_path,
        load_workspace_events(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
        ),
    )
    bundle_manifest = {
        "format_version": "autoharness.track_bundle.v1",
        "exported_at": _utc_now(),
        "workspace_id": args.workspace_id,
        "track_id": track_id,
        "artifact_format": structured_format,
        "includes": {
            "listings": not args.skip_listings,
            "champion_bundle": not args.skip_champion,
            "event_log": True,
        },
        "artifacts": {
            "track_report_path": str(track_report_path.relative_to(output_dir)),
            "event_log_path": str(track_events_path.relative_to(output_dir)),
            "iterations_path": (
                str(iterations_path.relative_to(output_dir))
                if not args.skip_listings
                else None
            ),
            "records_path": (
                str(records_path.relative_to(output_dir))
                if not args.skip_listings
                else None
            ),
            "promotions_path": (
                str(promotions_path.relative_to(output_dir))
                if not args.skip_listings
                else None
            ),
            "champion_bundle": champion_bundle_entry,
        },
    }
    _write_structured_payload(
        bundle_manifest_path,
        bundle_manifest,
        explicit_format=args.format,
    )

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Bundle path: {output_dir}")
    print(f"Bundle manifest: {bundle_manifest_path}")
    print(f"Listings: {'included' if not args.skip_listings else 'skipped'}")
    print(
        "Champion bundle: "
        + (
            "skipped"
            if args.skip_champion
            else ("present" if champion_bundle_entry is not None else "absent")
        )
    )
    return 0


def _handle_export_track_report(args: argparse.Namespace) -> int:
    payload = {
        "format_version": "autoharness.track_report_export.v1",
        "exported_at": _utc_now(),
        **_render_track_report(
            root=args.root,
            workspace_id=args.workspace_id,
            requested_track_id=args.track_id,
        ),
    }
    output_format = _write_structured_payload(
        args.output,
        payload,
        explicit_format=args.format,
    )
    print(f"Exported track report to {args.output} ({output_format})")
    return 0


def _handle_show_event_log(args: argparse.Namespace) -> int:
    events = load_workspace_events(
        root=args.root,
        workspace_id=args.workspace_id,
        event_type=args.event_type,
        campaign_run_id=args.campaign_id,
        track_id=args.track_id,
        since=args.since,
        until=args.until,
        limit=args.limit,
    )
    rendered = {
        "workspace_id": args.workspace_id,
        "track_filter": args.track_id,
        "campaign_id": args.campaign_id,
        "event_type": args.event_type,
        "since": args.since,
        "until": args.until,
        "event_total": len(events),
        "events": events,
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    if args.track_id is not None:
        print(f"Track filter: {args.track_id}")
    if args.campaign_id is not None:
        print(f"Campaign filter: {args.campaign_id}")
    if args.event_type is not None:
        print(f"Event type filter: {args.event_type}")
    print(f"Events: {len(events)}")
    for event in events:
        created_at = event.get("created_at")
        event_type = event.get("event_type")
        status = event.get("status")
        track_id = event.get("track_id")
        print(
            f"- {created_at} {event_type} "
            f"track={track_id} status={status}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_tail_campaign_events(args: argparse.Namespace) -> int:
    rendered_args = argparse.Namespace(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=args.track_id,
        campaign_id=args.campaign_id,
        event_type=None,
        since=None,
        until=None,
        limit=args.limit,
        json=args.json,
        output=args.output,
    )
    return _handle_show_event_log(rendered_args)


def _handle_show_event_metrics(args: argparse.Namespace) -> int:
    workspace_ids = args.workspace_id or _discover_workspace_ids(args.root)
    events = [
        event
        for workspace_id in workspace_ids
        for event in load_workspace_events(
            root=args.root,
            workspace_id=workspace_id,
            event_type=args.event_type,
            track_id=args.track_id,
            since=args.since,
            until=args.until,
        )
    ]
    rendered = {
        "workspace_filter": list(args.workspace_id),
        "selected_workspace_total": len(workspace_ids),
        "track_filter": args.track_id,
        "event_type": args.event_type,
        "since": args.since,
        "until": args.until,
        **aggregate_event_metrics(events),
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Selected workspaces: {len(workspace_ids)}")
    if args.track_id is not None:
        print(f"Track filter: {args.track_id}")
    if args.event_type is not None:
        print(f"Event type filter: {args.event_type}")
    print(f"Events: {rendered['event_total']}")
    print(f"Event types: {rendered['event_type_counts']}")
    print(f"Generators: {rendered['generator_counts']}")
    print(f"Providers: {rendered['provider_counts']}")
    print(f"Adapters: {rendered['adapter_counts']}")
    print(f"Retry counts: {rendered['retry_counts']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _load_root_memory_payload(
    *,
    root: Path,
    requested_workspace_ids: list[str],
    refresh: bool,
) -> tuple[dict[str, object], str | None]:
    path = root_memory_path(root)
    if refresh or requested_workspace_ids or not path.exists():
        payload = build_root_memory(
            root=root,
            requested_workspace_ids=requested_workspace_ids or None,
        )
        persisted_path = None
        if refresh and not requested_workspace_ids:
            persisted_path = str(persist_root_memory(root=root, payload=payload))
        return payload, persisted_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Invalid root memory file: {path}")
    return payload, str(path)


def _handle_show_root_memory(args: argparse.Namespace) -> int:
    payload, persisted_path = _load_root_memory_payload(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
        refresh=args.refresh,
    )
    rendered = {
        "root_memory_path": persisted_path,
        **payload,
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Champions: {rendered.get('champion_total')}")
    print(f"Transfer suggestions: {len(rendered.get('transfer_suggestions', []))}")
    print(f"Portfolio schedule entries: {len(rendered.get('portfolio_schedule', []))}")
    if persisted_path is not None:
        print(f"Root memory path: {persisted_path}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_plugin_catalog(args: argparse.Namespace) -> int:
    plugins = plugin_catalog_entries()
    load_failures = plugin_load_failures()
    rendered = {
        "plugin_total": len(plugins),
        "plugins": plugins,
        "load_failure_total": len(load_failures),
        "load_failures": load_failures,
        "search_runtime_contracts": plugin_runtime_contract_summary(),
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Plugins: {len(plugins)}")
    print(f"Load failures: {len(load_failures)}")
    for plugin in plugins:
        print(
            f"- {plugin.get('module')} status={plugin.get('status')} "
            f"generators={len(plugin.get('generator_ids', []))} "
            f"preflight_checks={len(plugin.get('preflight_check_ids', []))} "
            f"search_strategies={len(plugin.get('search_strategy_ids', []))}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0
