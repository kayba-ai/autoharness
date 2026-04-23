"""Append-only workspace event logs and derived metrics."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .coordination import append_jsonl_record


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def workspace_event_log_path(*, root: Path, workspace_id: str) -> Path:
    return root / workspace_id / "events.jsonl"


def append_workspace_event(
    *,
    root: Path,
    workspace_id: str,
    event_type: str,
    track_id: str | None = None,
    campaign_run_id: str | None = None,
    iteration_id: str | None = None,
    record_id: str | None = None,
    proposal_id: str | None = None,
    promotion_id: str | None = None,
    status: str | None = None,
    generator_id: str | None = None,
    provider_id: str | None = None,
    adapter_id: str | None = None,
    benchmark_name: str | None = None,
    details: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> Path:
    path = workspace_event_log_path(root=root, workspace_id=workspace_id)
    append_jsonl_record(
        path,
        {
            "format_version": "autoharness.workspace_event.v1",
            "created_at": created_at or _utc_now(),
            "workspace_id": workspace_id,
            "track_id": track_id,
            "campaign_run_id": campaign_run_id,
            "iteration_id": iteration_id,
            "record_id": record_id,
            "proposal_id": proposal_id,
            "promotion_id": promotion_id,
            "event_type": event_type,
            "status": status,
            "generator_id": generator_id,
            "provider_id": provider_id,
            "adapter_id": adapter_id,
            "benchmark_name": benchmark_name,
            "details": dict(details or {}),
        },
    )
    return path


def load_workspace_events(
    *,
    root: Path,
    workspace_id: str,
    event_type: str | None = None,
    campaign_run_id: str | None = None,
    track_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    path = workspace_event_log_path(root=root, workspace_id=workspace_id)
    if not path.exists():
        return []
    since_dt = _parse_timestamp(since) if isinstance(since, str) else None
    until_dt = _parse_timestamp(until) if isinstance(until, str) else None
    rendered: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        payload = json.loads(raw_line)
        if not isinstance(payload, dict):
            continue
        if event_type is not None and payload.get("event_type") != event_type:
            continue
        if campaign_run_id is not None and payload.get("campaign_run_id") != campaign_run_id:
            continue
        if track_id is not None and payload.get("track_id") != track_id:
            continue
        created_at = payload.get("created_at")
        if isinstance(created_at, str):
            created_dt = _parse_timestamp(created_at)
            if since_dt is not None and created_dt < since_dt:
                continue
            if until_dt is not None and created_dt > until_dt:
                continue
        rendered.append(payload)
    if limit is not None and limit >= 0:
        return rendered[-limit:]
    return rendered


def aggregate_event_metrics(
    events: list[dict[str, Any]],
) -> dict[str, object]:
    def _increment(counts: dict[str, int], value: object) -> None:
        if not isinstance(value, str) or not value:
            return
        counts[value] = counts.get(value, 0) + 1

    def _resource_float(value: object) -> float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return 0.0

    def _resource_int(value: object) -> int:
        if isinstance(value, int) and value >= 0:
            return value
        return 0

    def _add_resource_totals(
        bucket: dict[str, dict[str, float | int]],
        bucket_key: str,
        resource_usage: dict[str, Any],
    ) -> None:
        entry = bucket.setdefault(
            bucket_key,
            {
                "generation_total_tokens": 0,
                "generation_total_cost_usd": 0.0,
                "generation_total_duration_seconds": 0.0,
                "benchmark_total_cost": 0.0,
                "benchmark_total_duration_seconds": 0.0,
            },
        )
        entry["generation_total_tokens"] = int(entry["generation_total_tokens"]) + _resource_int(
            resource_usage.get("generation_total_tokens")
        )
        entry["generation_total_cost_usd"] = float(entry["generation_total_cost_usd"]) + _resource_float(
            resource_usage.get("generation_total_cost_usd")
        )
        entry["generation_total_duration_seconds"] = float(
            entry["generation_total_duration_seconds"]
        ) + _resource_float(resource_usage.get("generation_total_duration_seconds"))
        entry["benchmark_total_cost"] = float(entry["benchmark_total_cost"]) + _resource_float(
            resource_usage.get("benchmark_total_cost")
        )
        entry["benchmark_total_duration_seconds"] = float(
            entry["benchmark_total_duration_seconds"]
        ) + _resource_float(resource_usage.get("benchmark_total_duration_seconds"))

    event_type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    workspace_counts: dict[str, int] = {}
    track_counts: dict[str, int] = {}
    campaign_counts: dict[str, int] = {}
    generator_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    adapter_counts: dict[str, int] = {}
    benchmark_counts: dict[str, int] = {}
    retry_counts: dict[str, int] = {}
    generation_total_tokens = 0
    generation_total_cost_usd = 0.0
    generation_total_duration_seconds = 0.0
    benchmark_total_cost = 0.0
    benchmark_total_duration_seconds = 0.0
    resource_totals_by_workspace_id: dict[str, dict[str, float | int]] = {}
    resource_totals_by_track_id: dict[str, dict[str, float | int]] = {}
    resource_totals_by_campaign_run_id: dict[str, dict[str, float | int]] = {}

    for event in events:
        event_type = str(event.get("event_type") or "(unknown)")
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1
        workspace_id = event.get("workspace_id")
        _increment(workspace_counts, workspace_id)
        track_id = event.get("track_id")
        _increment(track_counts, track_id)
        _increment(campaign_counts, event.get("campaign_run_id"))
        _increment(generator_counts, event.get("generator_id"))
        _increment(provider_counts, event.get("provider_id"))
        _increment(adapter_counts, event.get("adapter_id"))
        _increment(benchmark_counts, event.get("benchmark_name"))
        _increment(status_counts, event.get("status"))
        details = event.get("details")
        if not isinstance(details, dict):
            continue
        retry_bucket = details.get("retry_bucket") or details.get("failure_class") or event.get(
            "status"
        )
        retry_count = details.get("retry_count")
        if isinstance(retry_bucket, str) and isinstance(retry_count, int):
            retry_counts[retry_bucket] = retry_counts.get(retry_bucket, 0) + retry_count
        resource_usage = details.get("resource_usage")
        if not isinstance(resource_usage, dict):
            continue
        generation_total_tokens += _resource_int(resource_usage.get("generation_total_tokens"))
        generation_total_cost_usd += _resource_float(
            resource_usage.get("generation_total_cost_usd")
        )
        generation_total_duration_seconds += _resource_float(
            resource_usage.get("generation_total_duration_seconds")
        )
        benchmark_total_cost += _resource_float(resource_usage.get("benchmark_total_cost"))
        benchmark_total_duration_seconds += _resource_float(
            resource_usage.get("benchmark_total_duration_seconds")
        )
        if isinstance(workspace_id, str):
            _add_resource_totals(
                resource_totals_by_workspace_id,
                workspace_id,
                resource_usage,
            )
        if isinstance(track_id, str):
            _add_resource_totals(resource_totals_by_track_id, track_id, resource_usage)
        campaign_run_id = event.get("campaign_run_id")
        if isinstance(campaign_run_id, str):
            _add_resource_totals(
                resource_totals_by_campaign_run_id,
                campaign_run_id,
                resource_usage,
            )

    return {
        "format_version": "autoharness.event_metrics.v1",
        "event_total": len(events),
        "event_type_counts": event_type_counts,
        "status_counts": status_counts,
        "workspace_counts": workspace_counts,
        "track_counts": track_counts,
        "campaign_counts": campaign_counts,
        "generator_counts": generator_counts,
        "provider_counts": provider_counts,
        "adapter_counts": adapter_counts,
        "benchmark_counts": benchmark_counts,
        "retry_counts": retry_counts,
        "generation_total_tokens": generation_total_tokens,
        "generation_total_cost_usd": generation_total_cost_usd,
        "generation_total_duration_seconds": generation_total_duration_seconds,
        "benchmark_total_cost": benchmark_total_cost,
        "benchmark_total_duration_seconds": benchmark_total_duration_seconds,
        "resource_totals_by_workspace_id": resource_totals_by_workspace_id,
        "resource_totals_by_track_id": resource_totals_by_track_id,
        "resource_totals_by_campaign_run_id": resource_totals_by_campaign_run_id,
    }
