"""Retention policy persistence and safe artifact pruning."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .campaign_runs import list_track_campaign_runs
from .cli_support import _load_structured_file
from .coordination import write_json_atomic
from .tracking import load_champion_manifest, load_workspace, resolve_workspace_dir


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def retention_policy_path(*, root: Path, workspace_id: str) -> Path:
    return resolve_workspace_dir(root, workspace_id) / "retention_policy.json"


def default_retention_policy() -> dict[str, object]:
    return {
        "format_version": "autoharness.retention_policy.v1",
        "keep_latest_campaign_runs": 5,
        "prune_failed_candidate_patches_older_than_days": 30,
        "keep_champion_campaigns_forever": True,
        "updated_at": _utc_now(),
    }


def load_retention_policy(*, root: Path, workspace_id: str) -> dict[str, object]:
    path = retention_policy_path(root=root, workspace_id=workspace_id)
    if not path.exists():
        return default_retention_policy()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in retention policy file: {path}")
    rendered = default_retention_policy()
    rendered.update(payload)
    return rendered


def persist_retention_policy(
    *,
    root: Path,
    workspace_id: str,
    policy: dict[str, object],
) -> Path:
    rendered = default_retention_policy()
    rendered.update(policy)
    rendered["updated_at"] = _utc_now()
    path = retention_policy_path(root=root, workspace_id=workspace_id)
    write_json_atomic(path, rendered)
    return path


def _collect_reference_ids(
    value: object,
    *,
    campaign_ids: set[str],
    iteration_ids: set[str],
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"campaign_id", "campaign_run_id"} and isinstance(item, str):
                campaign_ids.add(item)
            elif key_text == "iteration_id" and isinstance(item, str):
                iteration_ids.add(item)
            else:
                _collect_reference_ids(item, campaign_ids=campaign_ids, iteration_ids=iteration_ids)
        return
    if isinstance(value, list):
        for item in value:
            _collect_reference_ids(item, campaign_ids=campaign_ids, iteration_ids=iteration_ids)


def _scan_structured_references(
    *,
    workspace_dir: Path,
) -> dict[str, object]:
    campaign_ids: set[str] = set()
    iteration_ids: set[str] = set()
    sources: list[str] = []
    for path in sorted(workspace_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
            continue
        if path.name == "retention_policy.json":
            continue
        if not any(
            marker in path.name
            for marker in ("bundle_manifest", "report", "summary_export")
        ):
            continue
        try:
            payload = _load_structured_file(path)
        except SystemExit:
            continue
        before_campaign_total = len(campaign_ids)
        before_iteration_total = len(iteration_ids)
        _collect_reference_ids(payload, campaign_ids=campaign_ids, iteration_ids=iteration_ids)
        if len(campaign_ids) > before_campaign_total or len(iteration_ids) > before_iteration_total:
            sources.append(str(path))
    return {
        "campaign_ids": sorted(campaign_ids),
        "iteration_ids": sorted(iteration_ids),
        "sources": sources,
    }


def prune_workspace_artifacts(
    *,
    root: Path,
    workspace_id: str,
    track_id: str | None = None,
    dry_run: bool = False,
) -> dict[str, object]:
    workspace = load_workspace(root, workspace_id)
    policy = load_retention_policy(root=root, workspace_id=workspace_id)
    keep_latest_campaign_runs = int(policy.get("keep_latest_campaign_runs", 5) or 0)
    prune_patch_days = int(
        policy.get("prune_failed_candidate_patches_older_than_days", 30) or 0
    )
    keep_champion_campaigns_forever = bool(policy.get("keep_champion_campaigns_forever", True))
    removed_paths: list[str] = []
    kept_campaign_paths: list[str] = []
    keep_reasons_by_path: dict[str, list[str]] = {}

    track_ids = [track_id] if track_id is not None else sorted(workspace.tracks)
    champion_record_ids: set[str] = set()
    for current_track_id in track_ids:
        try:
            champion = load_champion_manifest(
                root=root,
                workspace_id=workspace_id,
                track_id=current_track_id,
            )
        except FileNotFoundError:
            continue
        champion_record_ids.add(champion.record_id)

    workspace_dir = resolve_workspace_dir(root, workspace_id)
    structured_references = _scan_structured_references(workspace_dir=workspace_dir)
    referenced_campaign_ids = set(structured_references["campaign_ids"])
    referenced_iteration_ids = set(structured_references["iteration_ids"])

    for current_track_id in track_ids:
        campaigns = list_track_campaign_runs(
            root=root,
            workspace_id=workspace_id,
            track_id=current_track_id,
        )
        campaigns.sort(key=lambda campaign: _parse_timestamp(campaign.created_at), reverse=True)
        for index, campaign in enumerate(campaigns):
            campaign_path = (
                root
                / workspace_id
                / "tracks"
                / current_track_id
                / "campaign_runs"
                / f"{campaign.campaign_run_id}.json"
            )
            keep_reasons: list[str] = []
            if index < keep_latest_campaign_runs:
                keep_reasons.append("within latest campaign window")
            if campaign.status in {"queued", "running", "paused"}:
                keep_reasons.append(f"campaign status is {campaign.status}")
            if campaign.desired_state in {"run", "paused"} and campaign.status != "completed":
                keep_reasons.append("campaign remains operator-addressable")
            if campaign.campaign_run_id in referenced_campaign_ids:
                keep_reasons.append("referenced by structured report or bundle")
            if keep_champion_campaigns_forever and any(
                candidate.record_id in champion_record_ids or candidate.promoted
                for candidate in campaign.candidates
            ):
                keep_reasons.append("contains champion lineage")
            if keep_reasons:
                kept_campaign_paths.append(str(campaign_path))
                keep_reasons_by_path[str(campaign_path)] = keep_reasons
                continue
            if campaign_path.exists():
                if not dry_run:
                    campaign_path.unlink()
                removed_paths.append(str(campaign_path))

    cutoff = datetime.now(UTC) - timedelta(days=prune_patch_days)
    iterations_dir = root / workspace_id / "iterations"
    if iterations_dir.exists():
        for iteration_dir in sorted(iterations_dir.glob("iter_*")):
            diff_path = iteration_dir / "candidate.patch"
            summary_path = iteration_dir / "summary.json"
            if not diff_path.exists() or not summary_path.exists():
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if not isinstance(summary, dict):
                continue
            if str(summary.get("status")) != "failed":
                continue
            keep_reasons: list[str] = []
            iteration_id = summary.get("iteration_id")
            if isinstance(iteration_id, str) and iteration_id in referenced_iteration_ids:
                keep_reasons.append("referenced by structured report or bundle")
            modified_at = datetime.fromtimestamp(diff_path.stat().st_mtime, tz=UTC)
            if modified_at >= cutoff:
                keep_reasons.append("newer than patch retention cutoff")
            if keep_reasons:
                keep_reasons_by_path[str(diff_path)] = keep_reasons
                continue
            if not dry_run:
                diff_path.unlink()
            removed_paths.append(str(diff_path))

    return {
        "format_version": "autoharness.retention_prune_result.v2",
        "workspace_id": workspace_id,
        "track_filter": track_id,
        "policy": policy,
        "dry_run": dry_run,
        "removed_total": len(removed_paths),
        "removed_paths": removed_paths,
        "kept_campaign_total": len(kept_campaign_paths),
        "kept_campaign_paths": kept_campaign_paths,
        "keep_reasons_by_path": keep_reasons_by_path,
        "reference_summary": {
            "referenced_campaign_ids": sorted(referenced_campaign_ids),
            "referenced_iteration_ids": sorted(referenced_iteration_ids),
            "reference_source_total": len(structured_references["sources"]),
            "reference_sources": structured_references["sources"],
        },
    }
