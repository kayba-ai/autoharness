"""Execution and planning support helpers."""

from __future__ import annotations

from pathlib import Path

import yaml

from .campaigns import TrackBenchmarkPolicy
from .cli_support import _load_structured_file, _preset_policy_key_for_stage


def _deep_merge_dicts(base: dict[str, object], overlay: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = _deep_merge_dicts(
                dict(base_value),
                dict(overlay_value),
            )
        else:
            merged[key] = overlay_value
    return merged


def _resolve_stage_config_preset(
    *,
    cli_preset: str | None,
    track_policy: TrackBenchmarkPolicy | None,
    stage_policy,
) -> tuple[str | None, str | None, str | None]:
    policy_preset = None
    if track_policy is not None:
        policy_preset = getattr(track_policy, _preset_policy_key_for_stage(stage_policy))
    if cli_preset is not None:
        return cli_preset, policy_preset, "cli"
    if policy_preset is not None:
        return policy_preset, policy_preset, "policy"
    return None, None, None


def _parse_inline_config_override(raw: str) -> dict[str, object]:
    if "=" not in raw:
        raise SystemExit(
            f"Invalid inline override `{raw}`. Use dotted.path=value syntax."
        )
    raw_path, raw_value = raw.split("=", 1)
    path_segments = [segment.strip() for segment in raw_path.split(".")]
    if not path_segments or any(not segment for segment in path_segments):
        raise SystemExit(
            f"Invalid inline override path `{raw_path}` in `{raw}`."
        )
    try:
        value = yaml.safe_load(raw_value)
    except yaml.YAMLError as exc:
        raise SystemExit(f"Invalid inline override value in `{raw}`: {exc}") from exc

    nested: object = value
    for segment in reversed(path_segments):
        nested = {segment: nested}
    if not isinstance(nested, dict):
        raise SystemExit(f"Inline override did not produce a mapping: {raw}")
    return nested


def _load_inline_config_overrides(entries: list[str]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for entry in entries:
        merged = _deep_merge_dicts(merged, _parse_inline_config_override(entry))
    return merged


def _compose_benchmark_config(
    *,
    adapter,
    config_path: Path | None,
    selected_preset: str | None,
    inline_overrides: list[str],
) -> dict[str, object]:
    composed: dict[str, object] = {}
    if selected_preset is not None:
        try:
            composed = _deep_merge_dicts(
                composed,
                adapter.starter_config(preset=selected_preset),
            )
        except KeyError as exc:
            raise SystemExit(str(exc)) from exc
    if config_path is not None:
        composed = _deep_merge_dicts(
            composed,
            _load_structured_file(config_path),
        )
    if inline_overrides:
        composed = _deep_merge_dicts(
            composed,
            _load_inline_config_overrides(inline_overrides),
        )
    if not composed:
        raise SystemExit(
            "Provide --config, --set, or a preset from CLI/policy to build the benchmark config."
        )
    return composed


def _load_iteration_plan(path: Path) -> dict[str, object]:
    if not path.exists():
        raise SystemExit(f"Iteration plan not found: {path}")
    payload = _load_structured_file(path)
    format_version = payload.get("format_version")
    if format_version is not None and format_version != "autoharness.iteration_plan.v1":
        raise SystemExit(
            f"Unsupported iteration plan format_version `{format_version}`: {path}"
        )
    raw_command = payload.get("suggested_command")
    if not isinstance(raw_command, list) or not raw_command:
        raise SystemExit(
            f"Iteration plan must include a non-empty `suggested_command` list: {path}"
        )
    if any(not isinstance(entry, str) or not entry for entry in raw_command):
        raise SystemExit(
            f"Iteration plan `suggested_command` entries must be non-empty strings: {path}"
        )
    if len(raw_command) < 2 or raw_command[0] != "autoharness" or raw_command[1] != "run-iteration":
        raise SystemExit(
            f"Iteration plan must contain an `autoharness run-iteration` command: {path}"
        )
    return payload


def _suggest_iteration_hypothesis(
    *,
    stage: str,
    adapter_id: str,
    benchmark_target: str | None,
    selected_preset: str | None,
) -> str:
    target_label = benchmark_target or adapter_id
    if selected_preset is not None:
        return (
            f"Run {stage} iteration for {target_label} with {adapter_id} "
            f"using {selected_preset} preset"
        )
    return f"Run {stage} iteration for {target_label} with {adapter_id}"


def _build_run_iteration_command(
    *,
    workspace_id: str,
    track_id: str,
    root: Path,
    adapter_id: str,
    config_path: Path | None,
    stage: str,
    hypothesis: str,
    preset: str | None,
    preset_source: str | None,
    inline_overrides: list[str],
    dry_run: bool,
) -> list[str]:
    command = [
        "autoharness",
        "run-iteration",
        "--workspace-id",
        workspace_id,
        "--track-id",
        track_id,
        "--adapter",
        adapter_id,
        "--hypothesis",
        hypothesis,
        "--root",
        str(root),
        "--stage",
        stage,
    ]
    if config_path is not None:
        command.extend(["--config", str(config_path)])
    if preset is not None and preset_source == "cli":
        command.extend(["--preset", preset])
    for entry in inline_overrides:
        command.extend(["--set", entry])
    if dry_run:
        command.append("--dry-run")
    return command


def _planned_iteration_argv(plan: dict[str, object]) -> list[str]:
    raw_command = plan.get("suggested_command")
    assert isinstance(raw_command, list)
    return [str(entry) for entry in raw_command[1:]]


def _planned_iteration_cwd(
    plan: dict[str, object],
    *,
    plan_path: Path,
) -> Path | None:
    raw_cwd = plan.get("planning_cwd")
    if raw_cwd is None:
        return None
    if not isinstance(raw_cwd, str) or not raw_cwd:
        raise SystemExit(
            f"Iteration plan `planning_cwd` must be a non-empty string when present: {plan_path}"
        )
    planning_cwd = Path(raw_cwd)
    if not planning_cwd.exists() or not planning_cwd.is_dir():
        raise SystemExit(f"Planned working directory not found: {planning_cwd}")
    return planning_cwd
