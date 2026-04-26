"""Project-level defaults loaded from autoharness.yaml."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from .autonomy import policy_for_mode
from .campaigns import CampaignEvaluatorPolicy, TrackConfig
from .coordination import write_text_atomic
from .mutations import _persist_track_bootstrap_artifacts
from .outputs import _write_yaml
from .tracking import (
    resolve_workspace_dir,
    save_workspace,
    save_workspace_state,
    workspace_config_path,
)
from .workspace import WorkspaceConfig, WorkspaceState


PROJECT_CONFIG_FILENAME = "autoharness.yaml"
PROJECT_CONFIG_FORMAT_VERSION = "autoharness.project.v1"
_AUTO_BOOTSTRAP_COMMANDS = {
    "generate-proposal",
    "optimize",
    "report",
    "run-benchmark",
    "run-campaign",
    "run-iteration",
}
_DEFAULT_JUDGE_MODEL = "gpt-4.1-mini"
_DEFAULT_DIAGNOSTIC_MODEL = "gpt-4.1-mini"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def maybe_bootstrap_project_state(*, args: argparse.Namespace) -> argparse.Namespace:
    command = str(getattr(args, "command", ""))
    if command not in _AUTO_BOOTSTRAP_COMMANDS:
        return args

    config_path_value = getattr(args, "project_config", None)
    if config_path_value is None:
        return args
    config_path = Path(config_path_value)
    config = load_project_config(config_path)

    _bootstrap_settings_if_needed(config=config, config_path=config_path)
    _bootstrap_workspace_if_needed(args=args, config=config, config_path=config_path)
    return args


def _bootstrap_settings_if_needed(
    *,
    config: dict[str, Any],
    config_path: Path,
) -> None:
    settings_path = _resolve_config_path(
        _nested_get(config, "autonomy", "settings_path"),
        config_path=config_path,
    )
    if settings_path is None:
        raise SystemExit(
            f"Project config `{config_path}` must define `autonomy.settings_path` "
            "for automatic setup."
        )
    if settings_path.exists():
        return

    autonomy_mode = _nested_get(config, "autonomy", "mode")
    if not isinstance(autonomy_mode, str) or not autonomy_mode.strip():
        raise SystemExit(
            f"Project config `{config_path}` must define `autonomy.mode` "
            "for automatic setup."
        )
    editable_surfaces = _nested_get(config, "autonomy", "editable_surfaces")
    protected_surfaces = _nested_get(config, "autonomy", "protected_surfaces")
    policy = policy_for_mode(
        autonomy_mode.strip(),
        editable_surfaces=tuple(str(entry) for entry in editable_surfaces or []),
        protected_surfaces=tuple(str(entry) for entry in protected_surfaces or []),
    )
    _write_yaml(
        settings_path,
        {
            "format_version": "autoharness.settings.v1",
            "created_at": _utc_now(),
            "autonomy": policy.to_dict(),
        },
    )


def _bootstrap_workspace_if_needed(
    *,
    args: argparse.Namespace,
    config: dict[str, Any],
    config_path: Path,
) -> None:
    root = getattr(args, "root", None)
    if not isinstance(root, Path):
        return
    workspace_id = getattr(args, "workspace_id", None) or _nested_get(config, "workspace", "id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise SystemExit(
            f"Project config `{config_path}` must define `workspace.id` "
            "for automatic workspace initialization."
        )
    workspace_id = workspace_id.strip()
    workspace_path = workspace_config_path(root=root, workspace_id=workspace_id)
    state_path = resolve_workspace_dir(root, workspace_id) / "state.json"
    if workspace_path.exists() and state_path.exists():
        return
    if workspace_path.exists() or state_path.exists():
        raise SystemExit(
            f"Workspace `{workspace_id}` under `{root}` is partially initialized. "
            "Repair it manually or re-run `autoharness init`."
        )

    objective = _nested_get(config, "workspace", "objective")
    benchmark = _nested_get(config, "workspace", "benchmark")
    if not isinstance(objective, str) or not objective.strip():
        raise SystemExit(
            f"Project config `{config_path}` must define `workspace.objective` "
            "for automatic workspace initialization."
        )
    if not isinstance(benchmark, str) or not benchmark.strip():
        raise SystemExit(
            f"Project config `{config_path}` must define `workspace.benchmark` "
            "for automatic workspace initialization."
        )

    track_id = getattr(args, "track_id", None) or _nested_get(config, "workspace", "track_id") or "main"
    if not isinstance(track_id, str) or not track_id.strip():
        track_id = "main"
    domain = _nested_get(config, "workspace", "domain")
    if not isinstance(domain, str) or not domain.strip():
        domain = "general"
    created_at = _utc_now()
    autonomy_mode = _nested_get(config, "autonomy", "mode")
    if not isinstance(autonomy_mode, str) or not autonomy_mode.strip():
        raise SystemExit(
            f"Project config `{config_path}` must define `autonomy.mode` "
            "for automatic workspace initialization."
        )

    workspace_root = resolve_workspace_dir(root, workspace_id)
    workspace_root.mkdir(parents=True, exist_ok=True)
    (workspace_root / "iterations").mkdir(exist_ok=True)
    (workspace_root / "tracks" / track_id / "registry").mkdir(
        parents=True,
        exist_ok=True,
    )

    track = TrackConfig(
        track_id=track_id,
        benchmark=benchmark.strip(),
        objective=objective.strip(),
        campaign_id=f"{workspace_id}_{track_id}",
        campaign_policy={},
        evaluator=CampaignEvaluatorPolicy(
            evaluator_version=created_at[:10],
            judge_model=_DEFAULT_JUDGE_MODEL,
            diagnostic_model=_DEFAULT_DIAGNOSTIC_MODEL,
        ),
        notes="Initial track scaffold created by autoharness project bootstrap.",
    )
    workspace = WorkspaceConfig(
        format_version="autoharness.workspace.v1",
        workspace_id=workspace_id,
        objective=objective.strip(),
        domain=domain,
        active_track_id=track_id,
        created_at=created_at,
        autonomy=policy_for_mode(
            autonomy_mode.strip(),
            editable_surfaces=tuple(
                str(entry)
                for entry in (_nested_get(config, "autonomy", "editable_surfaces") or [])
            ),
            protected_surfaces=tuple(
                str(entry)
                for entry in (_nested_get(config, "autonomy", "protected_surfaces") or [])
            ),
        ),
        benchmark_policy=_project_benchmark_policy(config),
        campaign_policy=_project_campaign_policy(config),
        tracks={track_id: track},
    )
    state = WorkspaceState(
        format_version="autoharness.workspace_state.v1",
        workspace_id=workspace_id,
        status="active",
        active_track_id=track_id,
    )

    save_workspace(root, workspace)
    save_workspace_state(root, workspace_id, state)
    _persist_track_bootstrap_artifacts(
        root=root,
        workspace_id=workspace_id,
        track=track,
        created_at=created_at,
    )
    write_text_atomic(
        workspace_root / "program.md",
        (
            f"# Workspace Program\n\n"
            f"Objective: {objective.strip()}\n\n"
            f"- Use one hypothesis per iteration.\n"
            f"- Keep the evaluator policy pinned inside this track.\n"
            f"- Respect autonomy mode `{workspace.autonomy.mode}`.\n"
            f"- Prefer the cheapest decisive evaluation path first.\n"
        ),
    )


def _project_benchmark_policy(config: dict[str, Any]) -> dict[str, object]:
    benchmark_name = _nested_get(config, "workspace", "benchmark")
    if not isinstance(benchmark_name, str) or not benchmark_name.strip():
        benchmark_name = "benchmark"
    preset = _nested_get(config, "benchmark", "preset")
    rendered = {
        "search_benchmark": benchmark_name.strip(),
        "promotion_benchmark": benchmark_name.strip(),
        "regression_benchmark": benchmark_name.strip(),
    }
    if isinstance(preset, str) and preset.strip():
        rendered.update(
            {
                "search_preset": preset.strip(),
                "promotion_preset": preset.strip(),
                "regression_preset": preset.strip(),
            }
        )
    return rendered


def _project_campaign_policy(config: dict[str, Any]) -> dict[str, object]:
    rendered: dict[str, object] = {}
    stage = _nested_get(config, "campaign", "stage") or _nested_get(config, "benchmark", "stage")
    if isinstance(stage, str) and stage.strip():
        rendered["stage"] = stage.strip()
    generator_id = _nested_get(config, "campaign", "generator") or _nested_get(config, "generator", "id")
    if isinstance(generator_id, str) and generator_id.strip():
        rendered["generator_id"] = generator_id.strip()
    intervention_classes = _nested_get(config, "campaign", "intervention_classes")
    if intervention_classes is None:
        intervention_class = _nested_get(config, "generator", "intervention_class")
        if isinstance(intervention_class, str) and intervention_class.strip():
            intervention_classes = [intervention_class.strip()]
    if isinstance(intervention_classes, list):
        rendered["intervention_classes"] = [
            str(entry).strip()
            for entry in intervention_classes
            if isinstance(entry, str) and entry.strip()
        ]
    max_iterations = _nested_get(config, "campaign", "max_iterations")
    if isinstance(max_iterations, int):
        rendered["max_iterations"] = max_iterations
    generator_options = _nested_get(config, "generator", "options")
    if isinstance(generator_options, dict) and generator_options:
        rendered["generator_metadata"] = dict(generator_options)
    return rendered
