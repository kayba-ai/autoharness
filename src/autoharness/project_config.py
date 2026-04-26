"""Project-level defaults loaded from autoharness.yaml."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


PROJECT_CONFIG_FILENAME = "autoharness.yaml"
PROJECT_CONFIG_FORMAT_VERSION = "autoharness.project.v1"


def discover_project_config(*, cwd: Path) -> Path | None:
    current = cwd.resolve()
    for directory in (current, *current.parents):
        candidate = directory / PROJECT_CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def load_project_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Project config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise SystemExit(f"Project config must decode to a mapping: {path}")
    format_version = payload.get("format_version")
    if format_version not in {None, PROJECT_CONFIG_FORMAT_VERSION}:
        raise SystemExit(
            f"Unsupported project config format `{format_version}` in {path}."
        )
    return dict(payload)


def _argv_has_flag(raw_argv: list[str], *flags: str) -> bool:
    for arg in raw_argv:
        for flag in flags:
            if arg == flag or arg.startswith(flag + "="):
                return True
    return False


def _nested_get(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _resolve_config_path(value: object, *, config_path: Path) -> Path | None:
    if isinstance(value, Path):
        rendered = value
    elif isinstance(value, str) and value.strip():
        rendered = Path(value)
    else:
        return None
    if not rendered.is_absolute():
        rendered = config_path.parent / rendered
    return rendered


def _set_scalar_default(
    args: argparse.Namespace,
    *,
    field_name: str,
    value: object,
    raw_argv: list[str],
    flags: tuple[str, ...],
) -> None:
    if not hasattr(args, field_name) or value is None:
        return
    if _argv_has_flag(raw_argv, *flags):
        return
    setattr(args, field_name, value)


def _set_sequence_default(
    args: argparse.Namespace,
    *,
    field_name: str,
    value: object,
    raw_argv: list[str],
    flags: tuple[str, ...],
) -> None:
    if not hasattr(args, field_name):
        return
    if _argv_has_flag(raw_argv, *flags):
        return
    if isinstance(value, list):
        setattr(args, field_name, list(value))


def apply_project_defaults(
    *,
    args: argparse.Namespace,
    raw_argv: list[str],
    cwd: Path,
) -> argparse.Namespace:
    requested_project_config = getattr(args, "project_config", None)
    config_path = (
        _resolve_config_path(requested_project_config, config_path=cwd / PROJECT_CONFIG_FILENAME)
        if requested_project_config is not None
        else None
    )
    if config_path is None:
        config_path = discover_project_config(cwd=cwd)
    if config_path is None:
        return args

    config = load_project_config(config_path)
    args.project_config = config_path

    _set_scalar_default(
        args,
        field_name="root",
        value=_resolve_config_path(
            _nested_get(config, "workspace", "root"),
            config_path=config_path,
        ),
        raw_argv=raw_argv,
        flags=("--root",),
    )
    _set_scalar_default(
        args,
        field_name="workspace_id",
        value=_nested_get(config, "workspace", "id"),
        raw_argv=raw_argv,
        flags=("--workspace-id",),
    )
    _set_scalar_default(
        args,
        field_name="track_id",
        value=_nested_get(config, "workspace", "track_id"),
        raw_argv=raw_argv,
        flags=("--track-id",),
    )
    _set_scalar_default(
        args,
        field_name="target_root",
        value=_resolve_config_path(
            _nested_get(config, "target_root"),
            config_path=config_path,
        ),
        raw_argv=raw_argv,
        flags=("--target-root",),
    )
    _set_scalar_default(
        args,
        field_name="settings",
        value=_resolve_config_path(
            _nested_get(config, "autonomy", "settings_path"),
            config_path=config_path,
        ),
        raw_argv=raw_argv,
        flags=("--settings",),
    )

    command = str(getattr(args, "command", ""))

    if command == "setup":
        _set_scalar_default(
            args,
            field_name="autonomy",
            value=_nested_get(config, "autonomy", "mode"),
            raw_argv=raw_argv,
            flags=("--autonomy",),
        )
        _set_scalar_default(
            args,
            field_name="output",
            value=_resolve_config_path(
                _nested_get(config, "autonomy", "settings_path"),
                config_path=config_path,
            ),
            raw_argv=raw_argv,
            flags=("--output",),
        )
        _set_sequence_default(
            args,
            field_name="editable_surface",
            value=_nested_get(config, "autonomy", "editable_surfaces"),
            raw_argv=raw_argv,
            flags=("--editable-surface",),
        )
        _set_sequence_default(
            args,
            field_name="protected_surface",
            value=_nested_get(config, "autonomy", "protected_surfaces"),
            raw_argv=raw_argv,
            flags=("--protected-surface",),
        )

    if command in {"init", "init-workspace"}:
        _set_scalar_default(
            args,
            field_name="objective",
            value=_nested_get(config, "workspace", "objective"),
            raw_argv=raw_argv,
            flags=("--objective",),
        )
        _set_scalar_default(
            args,
            field_name="benchmark",
            value=_nested_get(config, "workspace", "benchmark"),
            raw_argv=raw_argv,
            flags=("--benchmark",),
        )
        _set_scalar_default(
            args,
            field_name="domain",
            value=_nested_get(config, "workspace", "domain"),
            raw_argv=raw_argv,
            flags=("--domain",),
        )

    if command in {
        "run-benchmark",
        "generate-proposal",
        "run-iteration",
        "run-campaign",
        "optimize",
    }:
        _set_scalar_default(
            args,
            field_name="adapter",
            value=_nested_get(config, "benchmark", "adapter"),
            raw_argv=raw_argv,
            flags=("--adapter",),
        )
        _set_scalar_default(
            args,
            field_name="config",
            value=_resolve_config_path(
                _nested_get(config, "benchmark", "config"),
                config_path=config_path,
            ),
            raw_argv=raw_argv,
            flags=("--config",),
        )
        _set_scalar_default(
            args,
            field_name="preset",
            value=_nested_get(config, "benchmark", "preset"),
            raw_argv=raw_argv,
            flags=("--preset",),
        )

    if command == "run-benchmark":
        _set_scalar_default(
            args,
            field_name="stage",
            value=_nested_get(config, "benchmark", "stage"),
            raw_argv=raw_argv,
            flags=("--stage",),
        )

    if command in {"generate-proposal", "run-campaign", "optimize"}:
        _set_scalar_default(
            args,
            field_name="stage",
            value=(
                _nested_get(config, "campaign", "stage")
                or _nested_get(config, "benchmark", "stage")
            ),
            raw_argv=raw_argv,
            flags=("--stage",),
        )
        _set_scalar_default(
            args,
            field_name="generator",
            value=(
                _nested_get(config, "campaign", "generator")
                or _nested_get(config, "generator", "id")
            ),
            raw_argv=raw_argv,
            flags=("--generator",),
        )
        generator_options = _nested_get(config, "generator", "options")
        if isinstance(generator_options, dict):
            rendered_options = [
                f"{key}={value}"
                for key, value in generator_options.items()
                if isinstance(key, str) and key and value is not None
            ]
            _set_sequence_default(
                args,
                field_name="generator_option",
                value=rendered_options,
                raw_argv=raw_argv,
                flags=("--generator-option",),
            )

    if command == "generate-proposal":
        _set_scalar_default(
            args,
            field_name="intervention_class",
            value=_nested_get(config, "generator", "intervention_class"),
            raw_argv=raw_argv,
            flags=("--intervention-class",),
        )

    if command in {"run-campaign", "optimize"}:
        intervention_classes = _nested_get(config, "campaign", "intervention_classes")
        if intervention_classes is None:
            generator_intervention = _nested_get(
                config, "generator", "intervention_class"
            )
            if isinstance(generator_intervention, str) and generator_intervention:
                intervention_classes = [generator_intervention]
        _set_sequence_default(
            args,
            field_name="intervention_class",
            value=intervention_classes,
            raw_argv=raw_argv,
            flags=("--intervention-class",),
        )
        _set_scalar_default(
            args,
            field_name="max_iterations",
            value=_nested_get(config, "campaign", "max_iterations"),
            raw_argv=raw_argv,
            flags=("--max-iterations",),
        )

    return args
