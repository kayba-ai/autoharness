"""Shared CLI support helpers."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .mutations import _resolve_track_benchmark_policy, _resolve_track_campaign_policy
from .tracking import (
    load_track_policy,
    load_workspace,
    load_workspace_state,
    track_policy_path,
)
from .workspace import WorkspaceConfig, WorkspaceState


def _resolve_workspace_track(
    *,
    root: Path,
    workspace_id: str,
    requested_track_id: str | None,
) -> tuple[WorkspaceConfig, WorkspaceState, str]:
    workspace = load_workspace(root, workspace_id)
    state = load_workspace_state(root, workspace_id)
    track_id = requested_track_id or state.active_track_id or workspace.active_track_id
    if track_id not in workspace.tracks:
        raise SystemExit(f"Unknown track `{track_id}` for workspace `{workspace_id}`.")
    return workspace, state, track_id


def _track_policy_field_source(
    *,
    field_name: str,
    raw_policy,
    workspace: WorkspaceConfig,
) -> str:
    raw_value = getattr(raw_policy, field_name) if raw_policy is not None else None
    if isinstance(raw_value, str) and raw_value.strip():
        return "track_policy"
    workspace_value = workspace.benchmark_policy.get(field_name)
    if isinstance(workspace_value, str) and workspace_value.strip():
        return "workspace_fallback"
    if field_name.endswith("_benchmark"):
        return "track_default"
    return "unset"


def _resolved_track_policy_details(
    *,
    root: Path,
    workspace: WorkspaceConfig,
    workspace_id: str,
    track_id: str,
) -> dict[str, object]:
    policy_path = track_policy_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    try:
        raw_policy = load_track_policy(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
    except FileNotFoundError:
        raw_policy = None

    effective_policy, _ = _resolve_track_benchmark_policy(
        root=root,
        workspace=workspace,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    field_names = (
        "search_benchmark",
        "promotion_benchmark",
        "regression_benchmark",
        "search_preset",
        "promotion_preset",
        "regression_preset",
    )
    effective_sources = {
        field_name: _track_policy_field_source(
            field_name=field_name,
            raw_policy=raw_policy,
            workspace=workspace,
        )
        for field_name in field_names
    }
    return {
        "track_id": track_id,
        "policy_path": str(policy_path),
        "raw_policy_exists": raw_policy is not None,
        "raw_policy": raw_policy.to_dict() if raw_policy is not None else None,
        "effective_policy": effective_policy.to_dict(),
        "effective_sources": effective_sources,
        "workspace_fallback_policy": {
            key: workspace.benchmark_policy.get(key)
            for key in field_names
        },
    }


def _resolved_track_campaign_policy_details(
    *,
    workspace: WorkspaceConfig,
    track_id: str,
) -> dict[str, object]:
    raw_track_policy = dict(workspace.tracks[track_id].campaign_policy)
    workspace_defaults = dict(workspace.campaign_policy)
    effective_policy, effective_sources = _resolve_track_campaign_policy(
        workspace=workspace,
        track_id=track_id,
    )
    return {
        "track_id": track_id,
        "track_policy": raw_track_policy,
        "effective_policy": effective_policy,
        "effective_sources": effective_sources,
        "workspace_default_policy": workspace_defaults,
    }


def _preset_policy_key_for_stage(stage_policy) -> str:
    return stage_policy.benchmark_policy_key.replace("_benchmark", "_preset")


def _load_structured_file(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(f"Config file not found: {path}")

    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(text)
    else:
        payload = yaml.safe_load(text)

    if not isinstance(payload, dict):
        raise SystemExit(f"Config file must decode to a mapping: {path}")
    return payload
