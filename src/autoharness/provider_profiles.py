"""Workspace and track scoped provider profile persistence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .coordination import write_json_atomic
from .outputs import _redact_payload
from .tracking import track_dir_path


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def provider_profiles_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return (
        track_dir_path(root=root, workspace_id=workspace_id, track_id=track_id)
        / "provider_profiles.json"
    )


def load_provider_profiles(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> dict[str, dict[str, Any]]:
    path = provider_profiles_path(root=root, workspace_id=workspace_id, track_id=track_id)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in provider profile file: {path}")
    profiles = payload.get("profiles", {})
    if not isinstance(profiles, dict):
        return {}
    rendered: dict[str, dict[str, Any]] = {}
    for provider_id, entry in profiles.items():
        if isinstance(provider_id, str) and isinstance(entry, dict):
            rendered[provider_id] = dict(entry)
    return rendered


def persist_provider_profiles(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    profiles: dict[str, dict[str, Any]],
) -> Path:
    path = provider_profiles_path(root=root, workspace_id=workspace_id, track_id=track_id)
    write_json_atomic(
        path,
        {
            "format_version": "autoharness.provider_profiles.v1",
            "updated_at": _utc_now(),
            "workspace_id": workspace_id,
            "track_id": track_id,
            "profiles": profiles,
        },
    )
    return path


def resolve_provider_profile(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    provider_id: str,
) -> dict[str, Any]:
    profiles = load_provider_profiles(root=root, workspace_id=workspace_id, track_id=track_id)
    return dict(profiles.get(provider_id, {}))


def merge_provider_profile(
    *,
    explicit_metadata: dict[str, str],
    profile: dict[str, Any],
) -> dict[str, str]:
    merged = {
        str(key): str(value)
        for key, value in profile.items()
        if value is not None
    }
    merged.update({str(key): str(value) for key, value in explicit_metadata.items()})
    return merged


def summarize_provider_profile(
    *,
    provider_id: str,
    profile: dict[str, Any],
    explicit_metadata: dict[str, Any] | None = None,
) -> dict[str, object]:
    explicit = {
        str(key): value
        for key, value in dict(explicit_metadata or {}).items()
    }
    merged = merge_provider_profile(
        explicit_metadata={
            str(key): str(value)
            for key, value in explicit.items()
            if value is not None
        },
        profile=profile,
    )
    redacted_profile = _redact_payload(profile)
    redacted_merged = _redact_payload(merged)
    assert isinstance(redacted_profile, dict)
    assert isinstance(redacted_merged, dict)
    profile_keys = sorted(str(key) for key in profile)
    explicit_keys = sorted(str(key) for key in explicit)
    merged_keys = sorted(str(key) for key in merged)
    redacted_key_total = sum(
        1 for key in merged_keys if redacted_merged.get(key) == "[redacted]"
    )
    return {
        "provider_id": provider_id,
        "profile_applied": bool(profile),
        "profile_key_total": len(profile_keys),
        "profile_keys": profile_keys,
        "explicit_key_total": len(explicit_keys),
        "explicit_keys": explicit_keys,
        "merged_key_total": len(merged_keys),
        "merged_keys": merged_keys,
        "redacted_key_total": redacted_key_total,
        "redacted_profile": redacted_profile,
        "redacted_merged_profile": redacted_merged,
    }


def summarize_provider_profiles(
    profiles: dict[str, dict[str, Any]],
) -> dict[str, dict[str, object]]:
    return {
        str(provider_id): summarize_provider_profile(
            provider_id=str(provider_id),
            profile=dict(profile),
        )
        for provider_id, profile in sorted(profiles.items())
        if isinstance(provider_id, str) and isinstance(profile, dict)
    }
