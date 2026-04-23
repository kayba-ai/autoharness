"""Planning and execution CLI handlers for benchmark and iteration runs."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

from .adapters import get_adapter
from .campaigns import TrackBenchmarkPolicy
from .cli_support import (
    _load_structured_file,
    _resolve_workspace_track,
    _resolved_track_policy_details,
)
from .editing import edit_plan_from_dict, start_edit_session
from .events import append_workspace_event
from .execution_support import (
    _build_run_iteration_command,
    _compose_benchmark_config,
    _load_iteration_plan,
    _planned_iteration_argv,
    _planned_iteration_cwd,
    _resolve_stage_config_preset,
    _suggest_iteration_hypothesis,
)
from .mutations import (
    _require_active_workspace_state,
    _resolve_track_benchmark_policy,
    _utc_now,
)
from .outputs import (
    _emit_json_output,
    _write_json,
    _write_shell_script,
    _write_structured_payload,
    _write_text_file,
)
from .preflight import (
    build_preflight_cache_key,
    preflight_check_catalog,
    resolve_effective_preflight_commands,
    run_preflight_validation,
)
from .stages import apply_stage_overrides, evaluate_stage_result, stage_policy_for
from .staging import (
    capture_tree_manifest,
    compare_tree_manifests,
    create_copy_stage,
    resolve_staging_decision,
    rewrite_config_for_stage,
)
from .tracking import (
    create_benchmark_record,
    load_workspace,
    load_workspace_state,
    next_iteration_id,
    persist_benchmark_record,
    resolve_baseline_record,
    update_state_after_iteration,
    write_iteration_artifacts,
)
from .validation import run_validation


def _benchmark_event_resource_usage(payload: dict[str, object]) -> dict[str, float | int]:
    validation_summary = payload.get("validation_summary")
    metrics_mean = (
        validation_summary.get("metrics_mean")
        if isinstance(validation_summary, dict)
        else payload.get("metrics")
    )
    benchmark_total_cost = 0.0
    benchmark_total_duration_seconds = 0.0
    if isinstance(metrics_mean, dict):
        if isinstance(metrics_mean.get("cost"), (int, float)):
            benchmark_total_cost = float(metrics_mean["cost"])
        elif isinstance(metrics_mean.get("mean_cost"), (int, float)):
            benchmark_total_cost = float(metrics_mean["mean_cost"])
    if isinstance(validation_summary, dict) and isinstance(
        validation_summary.get("mean_duration_seconds"),
        (int, float),
    ):
        benchmark_total_duration_seconds = float(validation_summary["mean_duration_seconds"])
    elif isinstance(payload.get("duration_seconds"), (int, float)):
        benchmark_total_duration_seconds = float(payload["duration_seconds"])
    return {
        "generation_total_tokens": 0,
        "generation_total_cost_usd": 0.0,
        "generation_total_duration_seconds": 0.0,
        "benchmark_total_cost": benchmark_total_cost,
        "benchmark_total_duration_seconds": benchmark_total_duration_seconds,
    }


def _handle_plan_iteration(args: argparse.Namespace) -> int:
    workspace, state, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    try:
        adapter = get_adapter(args.adapter)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    track = workspace.tracks[track_id]
    try:
        stage_policy = stage_policy_for(
            args.stage,
            min_judge_pass_rate=track.evaluator.min_judge_pass_rate,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    resolved_policy = _resolved_track_policy_details(
        root=args.root,
        workspace=workspace,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    effective_policy = resolved_policy["effective_policy"]
    assert isinstance(effective_policy, dict)
    benchmark_target = effective_policy.get(stage_policy.benchmark_policy_key)
    selected_preset, policy_preset, preset_source = _resolve_stage_config_preset(
        cli_preset=args.preset,
        track_policy=TrackBenchmarkPolicy.from_dict(effective_policy),
        stage_policy=stage_policy,
    )
    composed_config = _compose_benchmark_config(
        adapter=adapter,
        config_path=args.config,
        selected_preset=selected_preset,
        inline_overrides=list(args.set),
    )
    try:
        effective_config, applied_stage_override = apply_stage_overrides(
            composed_config,
            stage=args.stage,
        )
        invocation = adapter.build_invocation(effective_config)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    hypothesis = args.hypothesis or _suggest_iteration_hypothesis(
        stage=args.stage,
        adapter_id=args.adapter,
        benchmark_target=(
            str(benchmark_target) if benchmark_target is not None else None
        ),
        selected_preset=selected_preset,
    )
    written_artifacts: dict[str, object] = {}
    command_config_path = args.config
    command_preset = selected_preset
    command_preset_source = preset_source
    command_inline_overrides = list(args.set)
    if args.write_config is not None:
        config_format = _write_structured_payload(
            args.write_config,
            effective_config,
        )
        written_artifacts["config_path"] = str(args.write_config)
        written_artifacts["config_format"] = config_format
        command_config_path = args.write_config
        command_preset = None
        command_preset_source = None
        command_inline_overrides = []
    if args.write_hypothesis is not None:
        _write_text_file(args.write_hypothesis, hypothesis + "\n")
        written_artifacts["hypothesis_path"] = str(args.write_hypothesis)
    suggested_command = _build_run_iteration_command(
        workspace_id=args.workspace_id,
        track_id=track_id,
        root=args.root,
        adapter_id=args.adapter,
        config_path=command_config_path,
        stage=args.stage,
        hypothesis=hypothesis,
        preset=command_preset,
        preset_source=command_preset_source,
        inline_overrides=command_inline_overrides,
        dry_run=args.dry_run,
    )
    suggested_shell_command = shlex.join(suggested_command)
    if args.write_command is not None:
        _write_shell_script(args.write_command, suggested_shell_command)
        written_artifacts["command_path"] = str(args.write_command)

    rendered = {
        "format_version": "autoharness.iteration_plan.v1",
        "planned_at": _utc_now(),
        "workspace_id": args.workspace_id,
        "workspace_status": state.status,
        "track_id": track_id,
        "adapter_id": args.adapter,
        "stage": args.stage,
        "planning_cwd": str(Path.cwd()),
        "benchmark_target": benchmark_target,
        "benchmark_preset_target": policy_preset,
        "stage_policy": stage_policy.to_dict(),
        "selected_preset": selected_preset,
        "selected_preset_source": preset_source,
        "config_path": str(args.config) if args.config is not None else None,
        "inline_overrides": list(args.set),
        "applied_stage_override": applied_stage_override,
        "effective_config": effective_config,
        "written_artifacts": written_artifacts,
        "planned_invocation": invocation.to_dict(),
        "suggested_hypothesis": hypothesis,
        "suggested_command": suggested_command,
        "suggested_shell_command": suggested_shell_command,
        "effective_track_policy": effective_policy,
        "effective_track_policy_sources": resolved_policy["effective_sources"],
    }

    if _emit_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    print(f"Workspace: {args.workspace_id}")
    print(f"Workspace status: {state.status}")
    print(f"Track: {track_id}")
    print(f"Adapter: {args.adapter}")
    print(f"Stage: {args.stage}")
    print(f"Benchmark target: {benchmark_target or '(none)'}")
    print(f"Preset: {selected_preset or '(none)'} ({preset_source or 'unset'})")
    print(f"Hypothesis: {hypothesis}")
    if "config_path" in written_artifacts:
        print(f"Written config: {written_artifacts['config_path']}")
    if "hypothesis_path" in written_artifacts:
        print(f"Written hypothesis: {written_artifacts['hypothesis_path']}")
    if "command_path" in written_artifacts:
        print(f"Written command: {written_artifacts['command_path']}")
    print(f"Shell command: {rendered['suggested_shell_command']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _validate_iteration_plan_payload(payload: dict[str, object]) -> list[str]:
    errors: list[str] = []

    def require_str(key: str) -> str | None:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

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

    format_version = payload.get("format_version")
    if format_version is not None and format_version != "autoharness.iteration_plan.v1":
        errors.append("Missing or invalid `format_version`.")

    require_str("workspace_id")
    require_str("workspace_status")
    require_str("track_id")
    require_str("adapter_id")
    require_str("stage")
    require_str("planning_cwd")
    require_dict("stage_policy")
    require_list("inline_overrides")
    require_dict("effective_config")
    require_dict("written_artifacts")
    require_dict("planned_invocation")
    require_str("suggested_hypothesis")
    require_str("suggested_shell_command")
    require_dict("effective_track_policy")
    require_dict("effective_track_policy_sources")
    return errors


def _render_iteration_plan_artifact(path: Path) -> dict[str, object]:
    payload = _load_iteration_plan(path)
    written_artifacts = payload.get("written_artifacts")
    rendered: dict[str, object] = {
        "plan_path": str(path),
        "format_version": payload.get("format_version"),
        "legacy_format": payload.get("format_version") is None,
        "plan": payload,
        "workspace_id": payload.get("workspace_id"),
        "workspace_status": payload.get("workspace_status"),
        "track_id": payload.get("track_id"),
        "adapter_id": payload.get("adapter_id"),
        "stage": payload.get("stage"),
        "planning_cwd": payload.get("planning_cwd"),
        "benchmark_target": payload.get("benchmark_target"),
        "selected_preset": payload.get("selected_preset"),
        "selected_preset_source": payload.get("selected_preset_source"),
        "suggested_hypothesis": payload.get("suggested_hypothesis"),
        "has_written_config": isinstance(written_artifacts, dict)
        and isinstance(written_artifacts.get("config_path"), str),
        "has_written_hypothesis": isinstance(written_artifacts, dict)
        and isinstance(written_artifacts.get("hypothesis_path"), str),
        "has_written_command": isinstance(written_artifacts, dict)
        and isinstance(written_artifacts.get("command_path"), str),
    }
    return rendered


def _render_iteration_plan_validation(path: Path) -> dict[str, object]:
    rendered = _render_iteration_plan_artifact(path)
    plan_payload = rendered["plan"]
    assert isinstance(plan_payload, dict)
    validation_errors = _validate_iteration_plan_payload(plan_payload)
    return {
        **rendered,
        "valid": not validation_errors,
        "error_count": len(validation_errors),
        "validation_errors": validation_errors,
    }


def _handle_show_plan_file(args: argparse.Namespace) -> int:
    rendered = _render_iteration_plan_artifact(args.path)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    format_version = rendered["format_version"] or "(legacy/unset)"
    print(f"Plan path: {rendered['plan_path']}")
    print(f"Format version: {format_version}")
    print(f"Workspace: {rendered['workspace_id']}")
    print(f"Workspace status: {rendered['workspace_status']}")
    print(f"Track: {rendered['track_id']}")
    print(f"Adapter: {rendered['adapter_id']}")
    print(f"Stage: {rendered['stage']}")
    print(f"Planning cwd: {rendered['planning_cwd']}")
    print(f"Benchmark target: {rendered['benchmark_target'] or '(none)'}")
    print(
        "Preset: "
        f"{rendered['selected_preset'] or '(none)'} "
        f"({rendered['selected_preset_source'] or 'unset'})"
    )
    print(f"Hypothesis: {rendered['suggested_hypothesis']}")
    print(
        "Written artifacts: "
        f"config={'yes' if rendered['has_written_config'] else 'no'}, "
        f"hypothesis={'yes' if rendered['has_written_hypothesis'] else 'no'}, "
        f"command={'yes' if rendered['has_written_command'] else 'no'}"
    )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_validate_plan_file(args: argparse.Namespace) -> int:
    rendered = _render_iteration_plan_validation(args.path)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0 if bool(rendered["valid"]) else 1

    format_version = rendered["format_version"] or "(legacy/unset)"
    print(f"Plan path: {rendered['plan_path']}")
    print(f"Format version: {format_version}")
    print(f"Valid: {'yes' if rendered['valid'] else 'no'}")
    print(f"Errors: {rendered['error_count']}")
    validation_errors = rendered["validation_errors"]
    assert isinstance(validation_errors, list)
    for error in validation_errors:
        print(f"- {error}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0 if bool(rendered["valid"]) else 1


def _handle_list_preflight_checks(args: argparse.Namespace) -> int:
    checks = preflight_check_catalog()
    rendered = {
        "check_total": len(checks),
        "checks": checks,
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Preflight checks: {rendered['check_total']}")
    for check in checks:
        print(
            f"- {check['check_id']}: {check['description']} "
            f"({check['command']})"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_preflight_check(args: argparse.Namespace) -> int:
    rendered = next(
        (item for item in preflight_check_catalog() if item["check_id"] == args.check),
        None,
    )
    if rendered is None:
        raise SystemExit(f"Unknown preflight check `{args.check}`.")
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Check: {rendered['check_id']}")
    print(f"Description: {rendered['description']}")
    print(f"Command: {rendered['command']}")
    default_stages = rendered.get("default_stages") or []
    if default_stages:
        assert isinstance(default_stages, list)
        print("Default stages: " + ", ".join(str(value) for value in default_stages))
    recommended_adapters = rendered.get("recommended_adapters") or []
    if recommended_adapters:
        assert isinstance(recommended_adapters, list)
        print(
            "Recommended adapters: "
            + ", ".join(str(value) for value in recommended_adapters)
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _benchmark_preflight_cwd(
    *,
    config: dict[str, object],
    config_path: Path | None,
) -> Path:
    workdir = config.get("workdir")
    if isinstance(workdir, str) and workdir.strip():
        candidate = Path(workdir)
        if not candidate.is_absolute() and config_path is not None:
            candidate = config_path.parent / candidate
        return candidate
    if config_path is not None:
        return config_path.parent
    return Path(".")


def _workspace_preflight_cache_dir(*, root: Path, workspace_id: str) -> Path:
    return root / workspace_id / "preflight_cache"


def _capture_run_environment(
    *,
    execution_root: Path | None,
    benchmark_workdir: object,
) -> dict[str, object]:
    whitelisted_env: dict[str, str] = {}
    for key in sorted(os.environ):
        if key.startswith("AUTOHARNESS_") or key in {"PATH", "PYTHONPATH", "VIRTUAL_ENV"}:
            whitelisted_env[key] = os.environ[key]
    return {
        "format_version": "autoharness.run_environment.v1",
        "python_version": sys.version,
        "python_executable": sys.executable,
        "process_cwd": str(Path.cwd()),
        "execution_root": str(execution_root.resolve()) if execution_root is not None else None,
        "benchmark_workdir": str(benchmark_workdir) if isinstance(benchmark_workdir, str) else None,
        "environment": whitelisted_env,
    }


def _handle_run_benchmark(args: argparse.Namespace) -> int:
    try:
        adapter = get_adapter(args.adapter)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    try:
        stage_policy = stage_policy_for(
            args.stage,
            min_judge_pass_rate=(
                args.min_success_rate if args.min_success_rate is not None else 0.55
            ),
            max_regressed_tasks=args.max_regressed_tasks,
            max_regressed_task_fraction=args.max_regressed_task_fraction,
            max_regressed_task_weight=args.max_regressed_task_weight,
            max_regressed_task_weight_fraction=args.max_regressed_task_weight_fraction,
            task_regression_margin=args.task_regression_margin,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    repeat_count = (
        args.repeat if args.repeat is not None else stage_policy.default_repeat_count
    )
    track_policy = None
    benchmark_target = None
    if args.workspace_id is not None and args.track_id is not None:
        workspace, _, resolved_track_id = _resolve_workspace_track(
            root=args.root,
            workspace_id=args.workspace_id,
            requested_track_id=args.track_id,
        )
        track_policy, _ = _resolve_track_benchmark_policy(
            root=args.root,
            workspace=workspace,
            workspace_id=args.workspace_id,
            track_id=resolved_track_id,
        )
        benchmark_target = getattr(track_policy, stage_policy.benchmark_policy_key)
    selected_preset, policy_preset, preset_source = _resolve_stage_config_preset(
        cli_preset=args.preset,
        track_policy=track_policy,
        stage_policy=stage_policy,
    )
    config = _compose_benchmark_config(
        adapter=adapter,
        config_path=args.config,
        selected_preset=selected_preset,
        inline_overrides=list(args.set),
    )
    try:
        benchmark_config, applied_stage_override = apply_stage_overrides(
            config,
            stage=args.stage,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    baseline_record = None
    if args.baseline_source != "none" or args.baseline_record_id is not None:
        if not args.workspace_id or not args.track_id:
            raise SystemExit(
                "`--workspace-id` and `--track-id` are required when baseline comparison is requested."
            )
        try:
            state = load_workspace_state(args.root, args.workspace_id)
            baseline_record = resolve_baseline_record(
                root=args.root,
                workspace_id=args.workspace_id,
                track_id=args.track_id,
                state=state,
                baseline_source=args.baseline_source,
                baseline_record_id=args.baseline_record_id,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc)) from exc

    try:
        preflight_resolution = resolve_effective_preflight_commands(
            commands=list(getattr(args, "preflight_command", [])),
            checks=list(getattr(args, "preflight_check", [])),
            stage=args.stage,
            adapter_id=args.adapter,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    preflight_commands = list(preflight_resolution["resolved_commands"])
    preflight_timeout_seconds = int(
        getattr(args, "preflight_timeout_seconds", 60) or 60
    )
    preflight_validation: dict[str, object] | None = None
    adapter_error: str | None = None
    try:
        if preflight_commands and not args.dry_run:
            cache_key = None
            cache_dir = None
            if args.workspace_id is not None:
                cache_dir = _workspace_preflight_cache_dir(
                    root=args.root,
                    workspace_id=args.workspace_id,
                )
                cache_key = build_preflight_cache_key(
                    cwd=_benchmark_preflight_cwd(
                        config=benchmark_config,
                        config_path=args.config,
                    ),
                    commands=preflight_commands,
                    timeout_seconds=preflight_timeout_seconds,
                    changed_paths=[],
                )
            preflight_validation = run_preflight_validation(
                commands=preflight_commands,
                cwd=_benchmark_preflight_cwd(
                    config=benchmark_config,
                    config_path=args.config,
                ),
                timeout_seconds=preflight_timeout_seconds,
                cache_dir=cache_dir,
                cache_key=cache_key,
            )
        if preflight_validation is not None and not bool(
            preflight_validation.get("all_passed")
        ):
            payload = {
                "adapter_id": args.adapter,
                "benchmark_name": str(
                    benchmark_config.get("benchmark_name", args.adapter)
                ),
                "command": [],
                "workdir": str(
                    _benchmark_preflight_cwd(
                        config=benchmark_config,
                        config_path=args.config,
                    )
                ),
                "success": False,
                "preflight_failed": True,
                "adapter_error": "Preflight validation failed.",
            }
        else:
            payload = run_validation(
                adapter=adapter,
                config=benchmark_config,
                dry_run=args.dry_run,
                repeat_count=repeat_count,
                seed_field=args.seed_field,
                seed_start=args.seed_start,
                seed_stride=args.seed_stride,
                confidence_level=stage_policy.confidence_level or 0.85,
            )
    except ValueError as exc:
        adapter_error = str(exc)
        payload = {
            "adapter_id": args.adapter,
            "benchmark_name": str(benchmark_config.get("benchmark_name", args.adapter)),
            "command": [],
            "workdir": str(
                _benchmark_preflight_cwd(
                    config=benchmark_config,
                    config_path=args.config,
                )
            ),
            "success": False,
            "adapter_error": adapter_error,
            "adapter_validation_error": True,
        }
    payload["dry_run"] = args.dry_run
    if preflight_validation is not None:
        payload["preflight_validation"] = preflight_validation
        payload["preflight_resolution"] = preflight_resolution
    if selected_preset is not None:
        payload["config_preset"] = selected_preset
        payload["config_preset_source"] = preset_source
    if policy_preset is not None:
        payload["policy_preset"] = policy_preset
    payload["stage_evaluation"] = evaluate_stage_result(
        payload=payload,
        stage_policy=stage_policy,
        benchmark_target=str(benchmark_target) if benchmark_target is not None else None,
        applied_stage_override=applied_stage_override,
        baseline_payload=baseline_record.payload if baseline_record is not None else None,
        baseline_label=baseline_record.record_id if baseline_record is not None else None,
        baseline_stage=baseline_record.stage if baseline_record is not None else None,
        min_improvement=args.min_improvement,
    )
    if policy_preset is not None and isinstance(payload["stage_evaluation"], dict):
        payload["stage_evaluation"]["benchmark_preset_target"] = policy_preset

    if args.workspace_id:
        state = load_workspace_state(args.root, args.workspace_id)
        _require_active_workspace_state(workspace_id=args.workspace_id, state=state)
        if not args.track_id:
            raise SystemExit("`--track-id` is required when `--workspace-id` is set.")
        record = create_benchmark_record(
            adapter_id=args.adapter,
            benchmark_name=str(payload.get("benchmark_name", args.adapter)),
            stage=args.stage,
            config=benchmark_config,
            payload=payload,
            dry_run=args.dry_run,
            workspace_id=args.workspace_id,
            track_id=args.track_id,
            hypothesis=args.hypothesis,
            notes=args.notes,
            config_path=str(args.config) if args.config is not None else None,
        )
        record_path = persist_benchmark_record(root=args.root, record=record)
        append_workspace_event(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=args.track_id,
            record_id=record.record_id,
            status=record.status,
            event_type="benchmark_completed",
            adapter_id=args.adapter,
            benchmark_name=record.benchmark_name,
            details={
                "stage": args.stage,
                "stage_decision": (
                    payload.get("stage_evaluation", {}).get("decision")
                    if isinstance(payload.get("stage_evaluation"), dict)
                    else None
                ),
                "resource_usage": _benchmark_event_resource_usage(payload),
            },
        )
        print(f"Recorded benchmark run at {record_path}")

    rendered = json.dumps(payload, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(f"Wrote output to {args.output}")
    else:
        print(rendered, end="")
    return 0


def _handle_run_iteration(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    state = load_workspace_state(args.root, args.workspace_id)
    _require_active_workspace_state(workspace_id=args.workspace_id, state=state)
    track_id = args.track_id or state.active_track_id or workspace.active_track_id
    if track_id not in workspace.tracks:
        raise SystemExit(
            f"Unknown track `{track_id}` for workspace `{args.workspace_id}`."
        )

    try:
        adapter = get_adapter(args.adapter)
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc

    iteration_id = next_iteration_id(state)
    edit_application = None
    edit_restore = None
    edit_session = None
    staging_context = None
    staging_decision = None
    execution_target_root = args.target_root
    effective_dry_run = args.dry_run
    source_plan_payload = (
        _load_iteration_plan(args.source_plan_path)
        if args.source_plan_path is not None
        else None
    )
    track = workspace.tracks[track_id]
    min_success_rate = (
        args.min_success_rate
        if args.min_success_rate is not None
        else track.evaluator.min_judge_pass_rate
    )
    try:
        stage_policy = stage_policy_for(
            args.stage,
            min_judge_pass_rate=min_success_rate,
            max_regressed_tasks=args.max_regressed_tasks,
            max_regressed_task_fraction=args.max_regressed_task_fraction,
            max_regressed_task_weight=args.max_regressed_task_weight,
            max_regressed_task_weight_fraction=args.max_regressed_task_weight_fraction,
            task_regression_margin=args.task_regression_margin,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    repeat_count = (
        args.repeat if args.repeat is not None else stage_policy.default_repeat_count
    )
    track_policy, _ = _resolve_track_benchmark_policy(
        root=args.root,
        workspace=workspace,
        workspace_id=args.workspace_id,
        track_id=track_id,
    )
    benchmark_target = getattr(track_policy, stage_policy.benchmark_policy_key)
    selected_preset, policy_preset, preset_source = _resolve_stage_config_preset(
        cli_preset=args.preset,
        track_policy=track_policy,
        stage_policy=stage_policy,
    )
    benchmark_config = _compose_benchmark_config(
        adapter=adapter,
        config_path=args.config,
        selected_preset=selected_preset,
        inline_overrides=list(args.set),
    )
    try:
        benchmark_config, applied_stage_override = apply_stage_overrides(
            benchmark_config,
            stage=args.stage,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        baseline_record = resolve_baseline_record(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
            state=state,
            baseline_source=args.baseline_source,
            baseline_record_id=args.baseline_record_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    if args.edit_plan is not None:
        requested_staging_mode = args.staging_mode
        if args.keep_applied_edits and requested_staging_mode == "auto":
            requested_staging_mode = "off"
        staging_decision = resolve_staging_decision(
            profile=adapter.staging_profile(),
            requested_mode=requested_staging_mode,
            config=benchmark_config,
            source_root=args.target_root,
            adapter_signal=adapter.suggest_staging(
                benchmark_config,
                source_root=args.target_root,
            ),
        )
        if staging_decision.resolved_mode == "copy":
            stage_root = (
                args.root
                / args.workspace_id
                / "iterations"
                / iteration_id
                / "staging"
                / "target"
            )
            try:
                create_copy_stage(source_root=args.target_root, staged_root=stage_root)
                benchmark_config, staging_context = rewrite_config_for_stage(
                    config=benchmark_config,
                    source_root=args.target_root,
                    staged_root=stage_root,
                    default_workdir=staging_decision.default_workdir,
                    relative_path_fields=adapter.staging_profile().relative_path_fields,
                )
                benchmark_config = adapter.rewrite_config_for_stage(
                    benchmark_config,
                    source_root=args.target_root,
                    staged_root=stage_root,
                )
            except ValueError as exc:
                raise SystemExit(str(exc)) from exc
            execution_target_root = stage_root

        raw_plan = _load_structured_file(args.edit_plan)
        try:
            edit_plan = edit_plan_from_dict(raw_plan)
            edit_session = start_edit_session(
                plan=edit_plan,
                target_root=execution_target_root,
                policy=workspace.autonomy,
                preview_only=args.dry_run,
                plan_path=args.edit_plan,
            )
            edit_application = edit_session.application
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        effective_dry_run = args.dry_run or not edit_application.applied

    try:
        preflight_resolution = resolve_effective_preflight_commands(
            commands=list(getattr(args, "preflight_command", [])),
            checks=list(getattr(args, "preflight_check", [])),
            stage=args.stage,
            adapter_id=args.adapter,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    preflight_commands = list(preflight_resolution["resolved_commands"])
    preflight_timeout_seconds = int(
        getattr(args, "preflight_timeout_seconds", 60) or 60
    )
    preflight_validation: dict[str, object] | None = None
    has_execution_target_root = (
        args.edit_plan is not None
        or staging_context is not None
        or args.target_root != Path(".")
    )
    effective_execution_root = (
        execution_target_root if has_execution_target_root else None
    )
    preflight_cwd = effective_execution_root or _benchmark_preflight_cwd(
        config=benchmark_config,
        config_path=args.config,
    )
    capture_execution_manifest = (
        has_execution_target_root
        and effective_execution_root is not None
    )
    manifest_root = (
        effective_execution_root
        if capture_execution_manifest
        and effective_execution_root.exists()
        and effective_execution_root.is_dir()
        else None
    )
    execution_manifest_before = (
        capture_tree_manifest(root=manifest_root) if manifest_root is not None else None
    )
    execution_manifest_after = None
    execution_manifest_drift = None

    payload: dict[str, object]
    adapter_error: str | None = None
    try:
        if preflight_commands and not effective_dry_run:
            cache_identity_root = (
                Path(staging_context.source_root)
                if staging_context is not None
                else preflight_cwd
            )
            cache_key = build_preflight_cache_key(
                cwd=cache_identity_root,
                commands=preflight_commands,
                timeout_seconds=preflight_timeout_seconds,
                changed_paths=(
                    list(edit_application.touched_paths)
                    if edit_application is not None
                    else None
                ),
            )
            preflight_validation = run_preflight_validation(
                commands=preflight_commands,
                cwd=preflight_cwd,
                timeout_seconds=preflight_timeout_seconds,
                cache_dir=_workspace_preflight_cache_dir(
                    root=args.root,
                    workspace_id=args.workspace_id,
                ),
                cache_key=cache_key,
            )
        if preflight_validation is not None and not bool(
            preflight_validation.get("all_passed")
        ):
            adapter_error = "Preflight validation failed."
            payload = {
                "adapter_id": args.adapter,
                "benchmark_name": str(
                    benchmark_config.get("benchmark_name", args.adapter)
                ),
                "command": [],
                "workdir": str(preflight_cwd),
                "success": False,
                "preflight_failed": True,
                "adapter_error": adapter_error,
            }
        else:
            payload = run_validation(
                adapter=adapter,
                config=benchmark_config,
                dry_run=effective_dry_run,
                repeat_count=repeat_count,
                seed_field=args.seed_field,
                seed_start=args.seed_start,
                seed_stride=args.seed_stride,
                confidence_level=stage_policy.confidence_level or 0.85,
            )
    except ValueError as exc:
        adapter_error = str(exc)
        payload = {
            "adapter_id": args.adapter,
            "benchmark_name": args.adapter,
            "command": [],
            "workdir": None,
            "success": False,
            "adapter_error": adapter_error,
            "adapter_validation_error": True,
        }
    finally:
        if edit_session is not None:
            edit_restore = edit_session.finalize(
                keep_applied=args.keep_applied_edits,
            )
        if manifest_root is not None:
            execution_manifest_after = capture_tree_manifest(root=manifest_root)
            if execution_manifest_before is not None:
                execution_manifest_drift = compare_tree_manifests(
                    before=execution_manifest_before,
                    after=execution_manifest_after,
                )

    payload["dry_run"] = effective_dry_run
    payload["run_environment"] = _capture_run_environment(
        execution_root=effective_execution_root,
        benchmark_workdir=payload.get("workdir"),
    )
    payload["working_directory_manifest"] = {
        "execution_root": (
            str(effective_execution_root.resolve())
            if effective_execution_root is not None
            else None
        ),
        "preflight_cwd": str(preflight_cwd.resolve()),
        "config_path": str(args.config.resolve()) if args.config is not None else None,
    }
    if preflight_validation is not None:
        payload["preflight_validation"] = preflight_validation
        payload["preflight_resolution"] = preflight_resolution
    if selected_preset is not None:
        payload["config_preset"] = selected_preset
        payload["config_preset_source"] = preset_source
    if policy_preset is not None:
        payload["policy_preset"] = policy_preset
    payload["stage_evaluation"] = evaluate_stage_result(
        payload=payload,
        stage_policy=stage_policy,
        benchmark_target=str(benchmark_target) if benchmark_target is not None else None,
        applied_stage_override=applied_stage_override,
        baseline_payload=baseline_record.payload if baseline_record is not None else None,
        baseline_label=baseline_record.record_id if baseline_record is not None else None,
        baseline_stage=baseline_record.stage if baseline_record is not None else None,
        min_improvement=args.min_improvement,
    )
    if policy_preset is not None and isinstance(payload["stage_evaluation"], dict):
        payload["stage_evaluation"]["benchmark_preset_target"] = policy_preset

    if edit_application is not None:
        payload["edit_application"] = edit_application.to_dict()
    if edit_restore is not None:
        payload["edit_restore"] = edit_restore.to_dict()
    if execution_manifest_before is not None and execution_manifest_after is not None:
        payload["execution_manifest"] = {
            "before": execution_manifest_before,
            "after": execution_manifest_after,
            "drift": execution_manifest_drift,
        }
    if edit_restore is not None and execution_manifest_drift is not None:
        payload["cleanup_validation"] = {
            "format_version": "autoharness.cleanup_validation.v1",
            "keep_applied_edits": bool(args.keep_applied_edits),
            "passed": not bool(execution_manifest_drift.get("has_drift")),
            "drift": execution_manifest_drift,
        }
    if staging_context is not None:
        staging_payload = staging_context.to_dict()
        if staging_decision is not None:
            staging_payload["decision"] = staging_decision.to_dict()
        if execution_manifest_before is not None:
            staging_payload["file_inventory"] = execution_manifest_before
        payload["staging"] = staging_payload
    edit_diff_text = edit_session.render_unified_diff() if edit_session is not None else ""

    record = create_benchmark_record(
        adapter_id=args.adapter,
        benchmark_name=str(payload.get("benchmark_name", args.adapter)),
        stage=args.stage,
        config=benchmark_config,
        payload=payload,
        dry_run=effective_dry_run,
        workspace_id=args.workspace_id,
        track_id=track_id,
        iteration_id=iteration_id,
        hypothesis=args.hypothesis,
        notes=args.notes,
        config_path=str(args.config) if args.config is not None else None,
        source_plan_path=(
            str(args.source_plan_path) if args.source_plan_path is not None else None
        ),
        source_proposal_id=getattr(args, "source_proposal_id", None),
        source_proposal_path=(
            str(getattr(args, "source_proposal_path"))
            if getattr(args, "source_proposal_path", None) is not None
            else None
        ),
    )
    record_path = persist_benchmark_record(root=args.root, record=record)
    artifact_paths = write_iteration_artifacts(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        iteration_id=iteration_id,
        record=record,
        source_plan_payload=source_plan_payload,
        edit_diff_text=edit_diff_text,
    )
    append_workspace_event(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        iteration_id=iteration_id,
        record_id=record.record_id,
        proposal_id=getattr(args, "source_proposal_id", None),
        status=record.status,
        event_type="benchmark_completed",
        adapter_id=args.adapter,
        benchmark_name=record.benchmark_name,
        details={
            "stage": args.stage,
            "stage_decision": (
                payload.get("stage_evaluation", {}).get("decision")
                if isinstance(payload.get("stage_evaluation"), dict)
                else None
            ),
            "resource_usage": _benchmark_event_resource_usage(payload),
        },
    )
    next_state = update_state_after_iteration(
        root=args.root,
        workspace_id=args.workspace_id,
        state=state,
        record=record,
        iteration_id=iteration_id,
    )

    if args.output is not None:
        _write_json(args.output, payload)

    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Iteration: {iteration_id}")
    print(f"Record: {record.record_id}")
    print(f"Stage: {args.stage}")
    print(f"Status: {record.status}")
    if isinstance(payload.get("validation_summary"), dict):
        summary = payload["validation_summary"]
        print(
            "Validation runs: "
            f"{payload.get('validation_run_count', 1)}"
        )
        if isinstance(summary.get("success_count"), int):
            print(
                "Validation success: "
                f"{summary['success_count']}/{summary.get('run_count', payload.get('validation_run_count', 1))}"
            )
    if isinstance(payload.get("stage_evaluation"), dict):
        stage_eval = payload["stage_evaluation"]
        print(f"Stage decision: {stage_eval.get('decision')}")
        baseline_comparison = stage_eval.get("baseline_comparison")
        if isinstance(baseline_comparison, dict):
            print(
                "Baseline comparison: "
                f"{baseline_comparison.get('decision')}"
            )
    if edit_application is not None:
        print(f"Edit status: {edit_application.status}")
        if edit_application.touched_paths:
            print(f"Edited paths: {', '.join(edit_application.touched_paths)}")
    if edit_restore is not None:
        print(f"Edit restore: {edit_restore.status}")
    print(f"Registry path: {record_path}")
    print(f"Summary path: {artifact_paths['summary_path']}")
    print(f"Next iteration index: {next_state.next_iteration_index}")
    return 0
