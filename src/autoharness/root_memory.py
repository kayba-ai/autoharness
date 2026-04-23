"""Cross-workspace champion memory, scheduling, and transfer suggestions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .coordination import write_json_atomic
from .events import aggregate_event_metrics, load_workspace_events
from .promotion_handlers import _transfer_champion_to_destination
from .tracking import load_benchmark_record, load_champion_manifest, load_workspace


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _discover_workspace_ids(root: Path) -> list[str]:
    if not root.exists():
        return []
    workspace_ids: list[str] = []
    for path in sorted(root.iterdir()):
        if path.is_dir() and (path / "workspace.json").exists():
            workspace_ids.append(path.name)
    return workspace_ids


def _record_regressed_task_ids(payload: dict[str, Any]) -> list[str]:
    stage_evaluation = payload.get("stage_evaluation")
    baseline_comparison = (
        stage_evaluation.get("baseline_comparison")
        if isinstance(stage_evaluation, dict)
        else None
    )
    task_ids = baseline_comparison.get("regressed_task_ids") if isinstance(baseline_comparison, dict) else None
    if not isinstance(task_ids, list):
        return []
    return [str(item) for item in task_ids if isinstance(item, str) and item]


def _record_task_result_patterns(payload: dict[str, Any]) -> dict[str, object]:
    validation_summary = payload.get("validation_summary")
    task_summary = (
        validation_summary.get("task_result_summary")
        if isinstance(validation_summary, dict)
        else None
    )
    if not isinstance(task_summary, dict):
        return {
            "failed_task_total": 0,
            "task_keys": [],
            "failed_task_keys": [],
        }
    task_keys = task_summary.get("task_keys")
    failed_task_keys = task_summary.get("failed_task_keys")
    return {
        "failed_task_total": (
            int(task_summary.get("failed_task_count"))
            if isinstance(task_summary.get("failed_task_count"), int)
            else 0
        ),
        "task_keys": [
            str(item) for item in task_keys if isinstance(item, str) and item
        ]
        if isinstance(task_keys, list)
        else [],
        "failed_task_keys": [
            str(item) for item in failed_task_keys if isinstance(item, str) and item
        ]
        if isinstance(failed_task_keys, list)
        else [],
    }


def _transfer_chain_depth(transfer_source: object) -> int:
    if not isinstance(transfer_source, dict):
        return 0
    previous = transfer_source.get("previous_transfer_source")
    return 1 + _transfer_chain_depth(previous)


def _champion_entry(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> dict[str, Any] | None:
    workspace = load_workspace(root, workspace_id)
    try:
        champion = load_champion_manifest(root=root, workspace_id=workspace_id, track_id=track_id)
        record = load_benchmark_record(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            record_id=champion.record_id,
        )
    except FileNotFoundError:
        return None

    payload = record.payload if isinstance(record.payload, dict) else {}
    validation_summary = payload.get("validation_summary")
    stability_summary = (
        validation_summary.get("stability_summary")
        if isinstance(validation_summary, dict)
        else None
    )
    transfer_source = payload.get("transfer_source")
    task_patterns = _record_task_result_patterns(payload)
    generator_metadata = payload.get("generation_metadata")
    generator_ids = (
        [str(item) for item in generator_metadata.get("generator_ids", []) if isinstance(item, str)]
        if isinstance(generator_metadata, dict) and isinstance(generator_metadata.get("generator_ids"), list)
        else []
    )
    if not generator_ids:
        source_proposal_id = payload.get("source_proposal_id")
        if isinstance(source_proposal_id, str) and source_proposal_id:
            generator_ids.append("proposal_backed")
    return {
        "workspace_id": workspace_id,
        "track_id": track_id,
        "record_id": champion.record_id,
        "promotion_id": champion.promotion_id,
        "adapter_id": record.adapter_id,
        "benchmark_name": record.benchmark_name,
        "stage": record.stage,
        "objective": workspace.objective,
        "domain": workspace.domain,
        "target_root": champion.target_root,
        "created_at": record.created_at,
        "updated_at": champion.updated_at,
        "transfer_source": transfer_source,
        "transfer_chain_depth": _transfer_chain_depth(transfer_source),
        "regressed_task_ids": _record_regressed_task_ids(payload),
        "task_patterns": task_patterns,
        "generator_ids": generator_ids,
        "success_rate": (
            float(validation_summary.get("success_rate"))
            if isinstance(validation_summary, dict)
            and isinstance(validation_summary.get("success_rate"), (int, float))
            else None
        ),
        "stability_score": (
            float(stability_summary.get("stability_score"))
            if isinstance(stability_summary, dict)
            and isinstance(stability_summary.get("stability_score"), (int, float))
            else None
        ),
        "flaky": bool(stability_summary.get("flaky"))
        if isinstance(stability_summary, dict)
        else False,
        "metrics_mean": (
            dict(validation_summary.get("metrics_mean"))
            if isinstance(validation_summary, dict)
            and isinstance(validation_summary.get("metrics_mean"), dict)
            else {}
        ),
        "stage_evaluation": payload.get("stage_evaluation"),
    }


def root_memory_path(root: Path) -> Path:
    return root / "root_memory.json"


def suggest_root_transfers(
    *,
    root: Path,
    memory_entries: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    entries = memory_entries
    if entries is None:
        payload = build_root_memory(root=root)
        raw_entries = payload.get("champions", [])
        entries = [entry for entry in raw_entries if isinstance(entry, dict)]

    suggestions: list[dict[str, Any]] = []
    for source in entries:
        source_workspace_id = source.get("workspace_id")
        if not isinstance(source_workspace_id, str):
            continue
        source_track_id = str(source.get("track_id") or "main")
        source_benchmark = str(source.get("benchmark_name") or "")
        source_domain = str(source.get("domain") or "")
        source_success_rate = float(source.get("success_rate") or 0.0)
        source_stability_score = float(source.get("stability_score") or 0.0)
        source_regressed_total = len(source.get("regressed_task_ids", [])) if isinstance(
            source.get("regressed_task_ids"),
            list,
        ) else 0
        for destination in entries:
            destination_workspace_id = destination.get("workspace_id")
            if not isinstance(destination_workspace_id, str):
                continue
            if destination_workspace_id == source_workspace_id:
                continue
            destination_track_id = str(destination.get("track_id") or "main")
            destination_benchmark = str(destination.get("benchmark_name") or "")
            destination_domain = str(destination.get("domain") or "")

            score = 0.0
            reasons: list[str] = []
            if destination_benchmark == source_benchmark and source_benchmark:
                score += 4.0
                reasons.append(f"shared benchmark {source_benchmark}")
            if destination_domain == source_domain and source_domain:
                score += 1.5
                reasons.append(f"shared domain {source_domain}")
            if source_success_rate >= 0.8:
                score += 1.0
                reasons.append("high success rate")
            if source_stability_score >= 0.7:
                score += 1.0
                reasons.append("stable validation")
            if source_regressed_total > 0:
                score += 0.5
                reasons.append("regression-targeted champion")
            if score <= 0.0:
                continue
            suggestions.append(
                {
                    "source_workspace_id": source_workspace_id,
                    "source_track_id": source_track_id,
                    "source_record_id": source.get("record_id"),
                    "source_promotion_id": source.get("promotion_id"),
                    "destination_workspace_id": destination_workspace_id,
                    "destination_track_id": destination_track_id,
                    "score": round(score, 2),
                    "reason": ", ".join(reasons),
                    "rationale": {
                        "source_benchmark": source_benchmark,
                        "destination_benchmark": destination_benchmark,
                        "source_domain": source_domain,
                        "destination_domain": destination_domain,
                        "success_rate": source_success_rate,
                        "stability_score": source_stability_score,
                        "regressed_task_total": source_regressed_total,
                    },
                }
            )
    suggestions.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["source_workspace_id"]),
            str(item["destination_workspace_id"]),
        )
    )
    deduped: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for item in suggestions:
        key = (
            str(item["source_workspace_id"]),
            str(item["destination_workspace_id"]),
        )
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        deduped.append(item)
    return deduped


def schedule_root_workspaces(
    *,
    root: Path,
    requested_workspace_ids: list[str] | None = None,
    memory_payload: dict[str, object] | None = None,
    mode: str = "portfolio",
) -> list[dict[str, object]]:
    workspace_filter = set(requested_workspace_ids or [])
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not workspace_filter or workspace_id in workspace_filter
    ]
    if mode != "portfolio":
        return [
            {
                "workspace_id": workspace_id,
                "score": 0.0,
                "reason": "fifo order",
                "rationale": {"mode": mode},
            }
            for workspace_id in selected_workspace_ids
        ]

    memory = memory_payload or build_root_memory(
        root=root,
        requested_workspace_ids=selected_workspace_ids,
    )
    champions = memory.get("champions", [])
    suggestions = memory.get("transfer_suggestions", [])
    champion_entries = [entry for entry in champions if isinstance(entry, dict)]
    transfer_suggestions = [entry for entry in suggestions if isinstance(entry, dict)]
    champions_by_workspace: dict[str, list[dict[str, Any]]] = {}
    for entry in champion_entries:
        workspace_id = entry.get("workspace_id")
        if isinstance(workspace_id, str):
            champions_by_workspace.setdefault(workspace_id, []).append(entry)
    transfer_targets: dict[str, list[dict[str, Any]]] = {}
    for entry in transfer_suggestions:
        workspace_id = entry.get("destination_workspace_id")
        if isinstance(workspace_id, str):
            transfer_targets.setdefault(workspace_id, []).append(entry)

    schedule: list[dict[str, object]] = []
    for workspace_id in selected_workspace_ids:
        workspace_champions = champions_by_workspace.get(workspace_id, [])
        workspace_events = load_workspace_events(root=root, workspace_id=workspace_id, limit=200)
        metrics = aggregate_event_metrics(workspace_events)
        event_total = int(metrics.get("event_total", 0))
        retry_total = sum(
            int(value)
            for value in dict(metrics.get("retry_counts", {})).values()
            if isinstance(value, int)
        )
        status_counts = metrics.get("status_counts", {})
        failed_events = (
            int(status_counts.get("failed", 0))
            if isinstance(status_counts, dict)
            else 0
        )
        last_event_age_hours = None
        if workspace_events:
            created_at = workspace_events[-1].get("created_at")
            if isinstance(created_at, str):
                last_event_age_hours = max(
                    0.0,
                    (datetime.now(UTC) - _parse_timestamp(created_at)).total_seconds() / 3600.0,
                )
        score = 0.0
        reasons: list[str] = []
        if not workspace_champions:
            score += 6.0
            reasons.append("no champion yet")
        else:
            champion = workspace_champions[0]
            if champion.get("flaky") is True:
                score += 2.0
                reasons.append("current champion is flaky")
            regressed_task_ids = champion.get("regressed_task_ids")
            if isinstance(regressed_task_ids, list) and regressed_task_ids:
                score += 1.5
                reasons.append("champion still reflects regressions")
        if retry_total > 0:
            score += min(float(retry_total), 5.0) * 0.5
            reasons.append("recent retry pressure")
        if failed_events > 0:
            score += min(float(failed_events), 4.0) * 0.5
            reasons.append("recent failed events")
        if last_event_age_hours is None:
            score += 2.0
            reasons.append("no recent event history")
        elif last_event_age_hours >= 24.0:
            score += 1.5
            reasons.append("stale workspace")
        destination_suggestions = transfer_targets.get(workspace_id, [])
        if destination_suggestions:
            score += min(len(destination_suggestions), 3) * 1.5
            reasons.append("has reusable transfer candidates")
        schedule.append(
            {
                "workspace_id": workspace_id,
                "score": round(score, 2),
                "reason": ", ".join(reasons) if reasons else "steady-state workspace",
                "rationale": {
                    "champion_total": len(workspace_champions),
                    "event_total": event_total,
                    "retry_total": retry_total,
                    "failed_event_total": failed_events,
                    "last_event_age_hours": last_event_age_hours,
                    "transfer_candidate_total": len(destination_suggestions),
                    "mode": mode,
                },
            }
        )
    schedule.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["workspace_id"]),
        )
    )
    return schedule


def build_root_memory(
    *,
    root: Path,
    requested_workspace_ids: list[str] | None = None,
) -> dict[str, object]:
    workspace_filter = set(requested_workspace_ids or [])
    entries: list[dict[str, Any]] = []
    workspace_insights: list[dict[str, Any]] = []
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not workspace_filter or workspace_id in workspace_filter
    ]
    for workspace_id in selected_workspace_ids:
        workspace = load_workspace(root, workspace_id)
        workspace_entries: list[dict[str, Any]] = []
        for track_id in sorted(workspace.tracks):
            entry = _champion_entry(root=root, workspace_id=workspace_id, track_id=track_id)
            if entry is not None:
                entries.append(entry)
                workspace_entries.append(entry)
        events = load_workspace_events(root=root, workspace_id=workspace_id, limit=200)
        event_metrics = aggregate_event_metrics(events)
        workspace_insights.append(
            {
                "workspace_id": workspace_id,
                "domain": workspace.domain,
                "objective": workspace.objective,
                "champion_total": len(workspace_entries),
                "transferred_champion_total": sum(
                    1 for entry in workspace_entries if isinstance(entry.get("transfer_source"), dict)
                ),
                "regressed_champion_total": sum(
                    1
                    for entry in workspace_entries
                    if isinstance(entry.get("regressed_task_ids"), list)
                    and len(entry["regressed_task_ids"]) > 0
                ),
                "flaky_champion_total": sum(1 for entry in workspace_entries if entry.get("flaky") is True),
                "event_metrics": event_metrics,
                "generator_ids": sorted(
                    {
                        generator_id
                        for entry in workspace_entries
                        for generator_id in entry.get("generator_ids", [])
                        if isinstance(generator_id, str)
                    }
                ),
            }
        )
    suggestions = suggest_root_transfers(root=root, memory_entries=entries)
    schedule = schedule_root_workspaces(
        root=root,
        requested_workspace_ids=selected_workspace_ids,
        memory_payload={
            "champions": entries,
            "transfer_suggestions": suggestions,
        },
        mode="portfolio",
    )
    return {
        "format_version": "autoharness.root_memory.v2",
        "generated_at": _utc_now(),
        "workspace_total": len({entry["workspace_id"] for entry in entries}),
        "champion_total": len(entries),
        "champions": entries,
        "workspace_insights": workspace_insights,
        "transfer_suggestions": suggestions,
        "portfolio_schedule": schedule,
    }


def persist_root_memory(
    *,
    root: Path,
    payload: dict[str, object],
) -> Path:
    path = root_memory_path(root)
    write_json_atomic(path, payload)
    return path


def apply_transfer_suggestions(
    *,
    root: Path,
    suggestions: list[dict[str, Any]],
    target_root_base: Path,
    limit: int | None = None,
) -> list[dict[str, object]]:
    applied: list[dict[str, object]] = []
    for suggestion in suggestions:
        if limit is not None and len(applied) >= limit:
            break
        source_workspace_id = suggestion.get("source_workspace_id")
        destination_workspace_id = suggestion.get("destination_workspace_id")
        if not isinstance(source_workspace_id, str) or not isinstance(destination_workspace_id, str):
            continue
        rendered = _transfer_champion_to_destination(
            root=root,
            source_workspace_id=source_workspace_id,
            source_track_id=(
                str(suggestion["source_track_id"])
                if suggestion.get("source_track_id") is not None
                else None
            ),
            destination_workspace_id=destination_workspace_id,
            destination_track_id=(
                str(suggestion["destination_track_id"])
                if suggestion.get("destination_track_id") is not None
                else None
            ),
            target_root=target_root_base / destination_workspace_id,
            notes=(
                "automatic root-memory transfer from "
                f"{source_workspace_id}/{suggestion.get('source_track_id')}"
            ),
        )
        applied.append(
            {
                **rendered,
                "suggestion": dict(suggestion),
            }
        )
    return applied
