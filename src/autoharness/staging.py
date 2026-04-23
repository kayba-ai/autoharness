"""Copy-based staging helpers for isolated candidate execution."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .adapters.base import AdapterStagingProfile, AdapterStagingSignal


RequestedStagingMode = Literal["off", "copy", "auto"]


@dataclass(frozen=True)
class StagingContext:
    """Describes one staged execution root for an iteration."""

    format_version: str
    mode: str
    source_root: str
    staged_root: str
    path_rewrite_count: int = 0
    workdir_was_defaulted: bool = False
    env_injected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedStagingDecision:
    """One resolved staging choice for a specific adapter/config pair."""

    requested_mode: RequestedStagingMode
    resolved_mode: Literal["off", "copy"]
    default_workdir: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def capture_tree_manifest(*, root: Path) -> dict[str, Any]:
    root_resolved = root.resolve()
    if not root_resolved.exists():
        return {
            "format_version": "autoharness.tree_manifest.v1",
            "root": str(root_resolved),
            "exists": False,
            "file_count": 0,
            "files": [],
        }

    files: list[dict[str, Any]] = []
    for path in sorted(root_resolved.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(root_resolved).as_posix()
        content = path.read_bytes()
        files.append(
            {
                "path": rel_path,
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {
        "format_version": "autoharness.tree_manifest.v1",
        "root": str(root_resolved),
        "exists": True,
        "file_count": len(files),
        "files": files,
    }


def compare_tree_manifests(
    *,
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    before_files = {
        str(entry["path"]): entry
        for entry in before.get("files", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    after_files = {
        str(entry["path"]): entry
        for entry in after.get("files", [])
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    added_paths = sorted(set(after_files) - set(before_files))
    removed_paths = sorted(set(before_files) - set(after_files))
    changed_paths = sorted(
        path
        for path in set(before_files).intersection(after_files)
        if before_files[path].get("sha256") != after_files[path].get("sha256")
    )
    return {
        "format_version": "autoharness.tree_drift.v1",
        "added_paths": added_paths,
        "removed_paths": removed_paths,
        "changed_paths": changed_paths,
        "has_drift": bool(added_paths or removed_paths or changed_paths),
    }


def create_copy_stage(*, source_root: Path, staged_root: Path) -> StagingContext:
    """Create a copy-on-write stage by copying the target tree."""
    source_root_resolved = source_root.resolve()
    if not source_root_resolved.exists():
        raise ValueError(f"Target root does not exist: {source_root}")
    if not source_root_resolved.is_dir():
        raise ValueError(f"Target root must be a directory: {source_root}")
    if staged_root.exists():
        raise ValueError(f"Staging root already exists: {staged_root}")

    staged_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_root_resolved, staged_root)
    return StagingContext(
        format_version="autoharness.staging_context.v1",
        mode="copy",
        source_root=str(source_root_resolved),
        staged_root=str(staged_root.resolve()),
    )


def resolve_staging_decision(
    *,
    profile: AdapterStagingProfile,
    requested_mode: RequestedStagingMode,
    config: dict[str, Any],
    source_root: Path,
    adapter_signal: AdapterStagingSignal | None = None,
) -> ResolvedStagingDecision:
    """Resolve whether a run should use isolated copy staging."""
    if requested_mode == "off":
        return ResolvedStagingDecision(
            requested_mode=requested_mode,
            resolved_mode="off",
            default_workdir=False,
            reason="The operator disabled staging for this iteration.",
        )

    if requested_mode == "copy":
        return ResolvedStagingDecision(
            requested_mode=requested_mode,
            resolved_mode="copy",
            default_workdir=profile.default_workdir,
            reason="The operator explicitly requested copy staging.",
        )

    references_target = _config_references_target(
        config=config,
        target_root=source_root,
        fields=profile.target_path_fields,
    )
    relative_hints = _config_has_relative_path_hints(
        config=config,
        fields=profile.relative_path_fields,
    )
    if profile.default_mode == "copy" and (
        references_target
        or relative_hints
        or adapter_signal is not None
        or (profile.default_workdir and not config.get("workdir"))
    ):
        return ResolvedStagingDecision(
            requested_mode=requested_mode,
            resolved_mode="copy",
            default_workdir=profile.default_workdir,
            reason=(
                adapter_signal.reason
                if adapter_signal is not None
                else "Adapter defaults prefer copy staging for local target execution."
            ),
        )

    if references_target or relative_hints or adapter_signal is not None:
        return ResolvedStagingDecision(
            requested_mode=requested_mode,
            resolved_mode="copy",
            default_workdir=profile.default_workdir,
            reason=(
                adapter_signal.reason
                if adapter_signal is not None
                else (
                    "Adapter config points at the target harness, so copy staging is "
                    "viable."
                )
            ),
        )

    return ResolvedStagingDecision(
        requested_mode=requested_mode,
        resolved_mode="off",
        default_workdir=False,
        reason="No adapter-specific signal suggested isolated staging.",
    )


def rewrite_config_for_stage(
    *,
    config: dict[str, Any],
    source_root: Path,
    staged_root: Path,
    default_workdir: bool = False,
    relative_path_fields: tuple[str, ...] = (),
) -> tuple[dict[str, Any], StagingContext]:
    """Rewrite a benchmark config so it executes against a staged target copy."""
    source_root_resolved = source_root.resolve()
    staged_root_resolved = staged_root.resolve()

    replacements = {
        str(source_root_resolved): str(staged_root_resolved),
        "{target_root}": str(staged_root_resolved),
        "$AUTOHARNESS_TARGET_ROOT": str(staged_root_resolved),
        "${AUTOHARNESS_TARGET_ROOT}": str(staged_root_resolved),
    }
    path_rewrite_count = 0

    def rewrite_value(value: Any) -> Any:
        nonlocal path_rewrite_count
        if isinstance(value, dict):
            return {key: rewrite_value(raw) for key, raw in value.items()}
        if isinstance(value, list):
            return [rewrite_value(item) for item in value]
        if isinstance(value, str):
            rewritten = value
            for needle, replacement in replacements.items():
                if needle in rewritten:
                    rewritten = rewritten.replace(needle, replacement)
                    path_rewrite_count += 1
            return rewritten
        return value

    rewritten = rewrite_value(config)
    if not isinstance(rewritten, dict):
        raise ValueError("Rewritten config must remain a mapping.")

    env_value = rewritten.get("env", {})
    if env_value is None:
        env_value = {}
    if not isinstance(env_value, dict):
        raise ValueError("`env` must remain a mapping after staging rewrite.")
    env = {str(key): str(raw) for key, raw in env_value.items()}
    env.setdefault("AUTOHARNESS_TARGET_ROOT", str(staged_root_resolved))
    env.setdefault("AUTOHARNESS_SOURCE_TARGET_ROOT", str(source_root_resolved))
    env.setdefault("AUTOHARNESS_STAGED_TARGET_ROOT", str(staged_root_resolved))
    rewritten["env"] = env

    for field_name in relative_path_fields:
        if field_name in rewritten:
            rewritten[field_name] = _rewrite_relative_path_value(
                rewritten[field_name],
                staged_root_resolved,
            )

    workdir_was_defaulted = False
    if default_workdir and not rewritten.get("workdir"):
        rewritten["workdir"] = str(staged_root_resolved)
        workdir_was_defaulted = True

    context = StagingContext(
        format_version="autoharness.staging_context.v1",
        mode="copy",
        source_root=str(source_root_resolved),
        staged_root=str(staged_root_resolved),
        path_rewrite_count=path_rewrite_count,
        workdir_was_defaulted=workdir_was_defaulted,
        env_injected=True,
    )
    return rewritten, context


def _config_references_target(
    *,
    config: dict[str, Any],
    target_root: Path,
    fields: tuple[str, ...],
) -> bool:
    target_text = str(target_root.resolve())
    placeholder_tokens = {
        "{target_root}",
        "$AUTOHARNESS_TARGET_ROOT",
        "${AUTOHARNESS_TARGET_ROOT}",
    }

    def has_reference(value: Any) -> bool:
        if isinstance(value, str):
            return target_text in value or value in placeholder_tokens
        if isinstance(value, list):
            return any(has_reference(item) for item in value)
        if isinstance(value, dict):
            return any(has_reference(raw) for raw in value.values())
        return False

    for field_name in fields:
        if field_name in config and has_reference(config[field_name]):
            return True
    return False


def _config_has_relative_path_hints(
    *,
    config: dict[str, Any],
    fields: tuple[str, ...],
) -> bool:
    def is_relative(value: Any) -> bool:
        if isinstance(value, str):
            return bool(value) and not Path(value).is_absolute() and "/" in value
        if isinstance(value, list):
            return any(is_relative(item) for item in value)
        return False

    for field_name in fields:
        if field_name in config and is_relative(config[field_name]):
            return True
    return False


def _rewrite_relative_path_value(value: Any, staged_root: Path) -> Any:
    if isinstance(value, str):
        if value and not Path(value).is_absolute():
            return str((staged_root / value).resolve())
        return value
    if isinstance(value, list):
        rewritten: list[Any] = []
        for item in value:
            if isinstance(item, str) and item and not Path(item).is_absolute():
                rewritten.append(str((staged_root / item).resolve()))
            else:
                rewritten.append(item)
        return rewritten
    return value
