"""Readiness checks for the config-first autoharness workflow."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .adapters import get_adapter
from .execution_support import _compose_benchmark_config
from .generators import generator_catalog_entry, get_generator
from .outputs import _emit_json_output
from .project_config import load_project_config
from .stages import apply_stage_overrides
from .validation import classify_validation_payload, run_validation


_DOCTOR_FORMAT_VERSION = "autoharness.doctor.v1"
_STRUCTURAL_FAILURE_CLASSES = {
    "benchmark_adapter_validation_error",
    "benchmark_artifact_parse_error",
    "benchmark_metrics_parse_error",
    "benchmark_process_error",
    "benchmark_signal_error",
    "benchmark_task_results_parse_error",
    "benchmark_timeout",
    "preflight_failed",
}
_PLACEHOLDER_BENCHMARK_TEXT = "replace with your benchmark command"


def _parse_generator_options(raw_options: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_entry in raw_options:
        if "=" not in raw_entry:
            raise SystemExit("`--generator-option` must use key=value format.")
        key, value = raw_entry.split("=", 1)
        if not key.strip() or not value.strip():
            raise SystemExit("`--generator-option` requires non-empty key and value.")
        parsed[key.strip()] = value.strip()
    return parsed


def _add_finding(
    findings: list[dict[str, str]],
    *,
    severity: str,
    check_id: str,
    message: str,
    suggested_fix: str,
) -> None:
    findings.append(
        {
            "severity": severity,
            "check_id": check_id,
            "message": message,
            "suggested_fix": suggested_fix,
        }
    )


def _resolve_command_path(command_value: str) -> str | None:
    if os.path.sep in command_value or (
        os.path.altsep is not None and os.path.altsep in command_value
    ):
        candidate = Path(command_value)
        if candidate.exists():
            return str(candidate.resolve())
        return None
    resolved = shutil.which(command_value)
    return resolved


def _check_generator_readiness(
    *,
    generator_id: str | None,
    generator_options: dict[str, str],
    findings: list[dict[str, str]],
) -> dict[str, object]:
    if not isinstance(generator_id, str) or not generator_id.strip():
        _add_finding(
            findings,
            severity="warning",
            check_id="generator.missing",
            message="No proposal generator is configured for optimization.",
            suggested_fix="Set `generator.id` in `autoharness.yaml` or pass `--generator`.",
        )
        return {"generator_id": None, "generator_ready": False, "catalog": None}

    generator_id = generator_id.strip()
    try:
        get_generator(generator_id)
        catalog = generator_catalog_entry(generator_id)
    except KeyError as exc:
        _add_finding(
            findings,
            severity="error",
            check_id="generator.unknown",
            message=str(exc),
            suggested_fix="Choose a generator from `autoharness list-generators`.",
        )
        return {
            "generator_id": generator_id,
            "generator_ready": False,
            "catalog": None,
        }

    if generator_id == "openai_responses":
        api_key = os.environ.get("AUTOHARNESS_OPENAI_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        if not api_key:
            _add_finding(
                findings,
                severity="error",
                check_id="generator.openai_auth_missing",
                message=(
                    "`openai_responses` is configured but no OpenAI API key is set."
                ),
                suggested_fix=(
                    "Export `OPENAI_API_KEY` or switch the project config to a local "
                    "generator like `codex_cli`, `claude_code`, or `failure_summary`."
                ),
            )
            return {
                "generator_id": generator_id,
                "generator_ready": False,
                "catalog": catalog,
            }
        return {
            "generator_id": generator_id,
            "generator_ready": True,
            "catalog": catalog,
        }

    if generator_id in {"codex_cli", "claude_code"}:
        command_path = generator_options.get(
            "command_path",
            "codex" if generator_id == "codex_cli" else "claude",
        )
        resolved_path = _resolve_command_path(command_path)
        if resolved_path is None:
            _add_finding(
                findings,
                severity="error",
                check_id=f"generator.{generator_id}_command_missing",
                message=(
                    f"`{generator_id}` is configured but `{command_path}` is not "
                    "available on PATH."
                ),
                suggested_fix=(
                    f"Install the local CLI or set "
                    f"`--generator-option command_path=/path/to/{command_path}`."
                ),
            )
            return {
                "generator_id": generator_id,
                "generator_ready": False,
                "catalog": catalog,
            }
        return {
            "generator_id": generator_id,
            "generator_ready": True,
            "catalog": catalog,
            "resolved_command_path": resolved_path,
        }

    if generator_id == "local_command":
        command_path = generator_options.get("command_path")
        if not isinstance(command_path, str) or not command_path.strip():
            _add_finding(
                findings,
                severity="error",
                check_id="generator.local_command_missing_command_path",
                message=(
                    "`local_command` is configured without a generator command path."
                ),
                suggested_fix=(
                    "Set `generator.options.command_path` in `autoharness.yaml` or "
                    "pass `--generator-option command_path=/path/to/script`."
                ),
            )
            return {
                "generator_id": generator_id,
                "generator_ready": False,
                "catalog": catalog,
            }
        resolved_path = _resolve_command_path(command_path.strip())
        if resolved_path is None:
            _add_finding(
                findings,
                severity="error",
                check_id="generator.local_command_not_found",
                message=(
                    f"`local_command` is configured but `{command_path}` cannot be executed."
                ),
                suggested_fix="Point `command_path` at an installed local executable.",
            )
            return {
                "generator_id": generator_id,
                "generator_ready": False,
                "catalog": catalog,
            }
        return {
            "generator_id": generator_id,
            "generator_ready": True,
            "catalog": catalog,
            "resolved_command_path": resolved_path,
        }

    return {
        "generator_id": generator_id,
        "generator_ready": True,
        "catalog": catalog,
    }


def _check_project_shape(
    *,
    project_config_path: Path | None,
    project_config: dict[str, Any] | None,
    target_root: Path | None,
    findings: list[dict[str, str]],
) -> dict[str, object]:
    rendered: dict[str, object] = {
        "project_config_path": (
            str(project_config_path.resolve()) if project_config_path is not None else None
        ),
        "target_root": str(target_root) if target_root is not None else None,
    }
    if project_config_path is not None:
        _add_finding(
            findings,
            severity="info",
            check_id="project_config.loaded",
            message=f"Loaded project config from `{project_config_path}`.",
            suggested_fix="No action needed.",
        )
    if target_root is None:
        _add_finding(
            findings,
            severity="warning",
            check_id="target_root.missing",
            message="No target root is configured for optimization.",
            suggested_fix="Set `target_root` in `autoharness.yaml` or pass `--target-root`.",
        )
        return rendered
    if not target_root.exists():
        _add_finding(
            findings,
            severity="error",
            check_id="target_root.missing_path",
            message=f"Target root does not exist: {target_root}",
            suggested_fix="Fix `target_root` so it points at the harness repo to optimize.",
        )
        return rendered
    if not target_root.is_dir():
        _add_finding(
            findings,
            severity="error",
            check_id="target_root.not_directory",
            message=f"Target root is not a directory: {target_root}",
            suggested_fix="Point `target_root` at a repo directory, not a file.",
        )
        return rendered

    rendered["target_root"] = str(target_root.resolve())

    if isinstance(project_config, dict):
        autonomy = project_config.get("autonomy")
        autonomy_payload = autonomy if isinstance(autonomy, dict) else {}
        autonomy_mode = autonomy_payload.get("mode")
        editable_surfaces = autonomy_payload.get("editable_surfaces")
        if autonomy_mode == "bounded" and not editable_surfaces:
            _add_finding(
                findings,
                severity="error",
                check_id="autonomy.empty_editable_surfaces",
                message=(
                    "Bounded autonomy is configured without any editable surfaces."
                ),
                suggested_fix=(
                    "Set `autonomy.editable_surfaces` in `autoharness.yaml` or "
                    "switch to `proposal` mode until you decide what may be edited."
                ),
            )
            rendered["autonomy_mode"] = autonomy_mode
            rendered["editable_surfaces"] = []
            return rendered
        if isinstance(autonomy_mode, str) and autonomy_mode:
            rendered["autonomy_mode"] = autonomy_mode
        if isinstance(editable_surfaces, list):
            rendered["editable_surfaces"] = list(editable_surfaces)
    return rendered


def _render_doctor_report(args: argparse.Namespace) -> dict[str, object]:
    findings: list[dict[str, str]] = []
    repeat_count = int(getattr(args, "repeat", 3))
    if repeat_count < 1:
        _add_finding(
            findings,
            severity="error",
            check_id="benchmark.invalid_repeat_count",
            message="`--repeat` must be at least 1.",
            suggested_fix="Run `autoharness doctor --repeat 3` or another positive integer.",
        )
        repeat_count = 1
    project_config_path = (
        Path(args.project_config).resolve()
        if getattr(args, "project_config", None) is not None
        else None
    )
    project_config = (
        load_project_config(project_config_path) if project_config_path is not None else None
    )

    target_root = (
        Path(args.target_root).resolve()
        if isinstance(getattr(args, "target_root", None), Path)
        else None
    )
    project_shape = _check_project_shape(
        project_config_path=project_config_path,
        project_config=project_config,
        target_root=target_root,
        findings=findings,
    )

    generator_options = _parse_generator_options(list(getattr(args, "generator_option", [])))
    generator_report = _check_generator_readiness(
        generator_id=getattr(args, "generator", None),
        generator_options=generator_options,
        findings=findings,
    )

    adapter_id = getattr(args, "adapter", None)
    adapter = None
    benchmark_validation: dict[str, object] = {
        "adapter_id": adapter_id,
        "selected_preset": getattr(args, "preset", None),
        "config_path": (
            str(args.config.resolve())
            if isinstance(getattr(args, "config", None), Path)
            else None
        ),
        "inline_overrides": list(getattr(args, "set", [])),
        "stage": getattr(args, "stage", None),
        "valid": False,
        "applied_stage_override": False,
        "effective_config": None,
        "planned_invocation": None,
        "validation_errors": [],
    }
    benchmark_probe: dict[str, object] | None = None

    if not isinstance(adapter_id, str) or not adapter_id.strip():
        _add_finding(
            findings,
            severity="error",
            check_id="benchmark.adapter_missing",
            message="No benchmark adapter is configured.",
            suggested_fix="Set `benchmark.adapter` in `autoharness.yaml` or pass `--adapter`.",
        )
    else:
        try:
            adapter = get_adapter(adapter_id)
        except KeyError as exc:
            benchmark_validation["validation_errors"] = [str(exc)]
            _add_finding(
                findings,
                severity="error",
                check_id="benchmark.adapter_unknown",
                message=str(exc),
                suggested_fix="Choose an implemented adapter from `autoharness list-benchmarks`.",
            )
        else:
            try:
                config = _compose_benchmark_config(
                    adapter=adapter,
                    config_path=getattr(args, "config", None),
                    selected_preset=getattr(args, "preset", None),
                    inline_overrides=list(getattr(args, "set", [])),
                )
                effective_config, applied_stage_override = apply_stage_overrides(
                    config,
                    stage=str(getattr(args, "stage", "screening")),
                )
                adapter.validate_config(effective_config)
                invocation = adapter.build_invocation(effective_config)
            except (SystemExit, ValueError, KeyError) as exc:
                benchmark_validation["validation_errors"] = [str(exc)]
                _add_finding(
                    findings,
                    severity="error",
                    check_id="benchmark.config_invalid",
                    message=str(exc),
                    suggested_fix=(
                        "Fix the benchmark config or inspect the composed config with "
                        "`autoharness show-benchmark-config`."
                    ),
                )
            else:
                benchmark_validation.update(
                    {
                        "valid": True,
                        "applied_stage_override": applied_stage_override,
                        "effective_config": effective_config,
                        "planned_invocation": invocation.to_dict(),
                        "validation_errors": [],
                    }
                )
                command_text = json.dumps(invocation.to_dict().get("command", []))
                effective_text = json.dumps(effective_config, sort_keys=True)
                if (
                    _PLACEHOLDER_BENCHMARK_TEXT in command_text
                    or _PLACEHOLDER_BENCHMARK_TEXT in effective_text
                ):
                    _add_finding(
                        findings,
                        severity="error",
                        check_id="benchmark.placeholder_command",
                        message=(
                            "The benchmark config still contains the guide placeholder command."
                        ),
                        suggested_fix=(
                            "Replace the generated command in `benchmarks/screening.yaml` "
                            "with a real, repeatable eval command."
                        ),
                    )
                elif getattr(args, "skip_benchmark_runs", False):
                    _add_finding(
                        findings,
                        severity="info",
                        check_id="benchmark.probe_skipped",
                        message="Skipped repeated benchmark probe runs.",
                        suggested_fix="Run `autoharness doctor` without `--skip-benchmark-runs` to measure stability.",
                    )
                else:
                    benchmark_probe = run_validation(
                        adapter=adapter,
                        config=effective_config,
                        dry_run=False,
                        repeat_count=repeat_count,
                    )
                    validation_summary = benchmark_probe.get("validation_summary")
                    summary_payload = (
                        validation_summary if isinstance(validation_summary, dict) else {}
                    )
                    primary_failure_class = classify_validation_payload(benchmark_probe)
                    if primary_failure_class in _STRUCTURAL_FAILURE_CLASSES:
                        _add_finding(
                            findings,
                            severity="error",
                            check_id="benchmark.structural_failure",
                            message=(
                                "Repeated benchmark probe runs hit a structural failure: "
                                f"{primary_failure_class}."
                            ),
                            suggested_fix=(
                                "Fix the benchmark command, adapter config, or artifact parsing "
                                "before starting optimization."
                            ),
                        )
                    elif primary_failure_class == "benchmark_command_failed":
                        _add_finding(
                            findings,
                            severity="warning",
                            check_id="benchmark.command_failed",
                            message=(
                                "The benchmark command returned failures during the doctor probe."
                            ),
                            suggested_fix=(
                                "Confirm that failures represent a meaningful baseline and not a "
                                "broken setup."
                            ),
                        )
                    stability_summary = summary_payload.get("stability_summary")
                    stability_payload = (
                        stability_summary if isinstance(stability_summary, dict) else {}
                    )
                    if bool(stability_payload.get("flaky")):
                        _add_finding(
                            findings,
                            severity="warning",
                            check_id="benchmark.flaky",
                            message="Repeated benchmark runs were not stable enough for clean comparison.",
                            suggested_fix=(
                                "Reduce nondeterminism, isolate external state, or simplify the "
                                "benchmark before running `optimize`."
                            ),
                        )
                    mean_duration = summary_payload.get("mean_duration_seconds")
                    if isinstance(mean_duration, (int, float)) and float(mean_duration) > 60.0:
                        _add_finding(
                            findings,
                            severity="warning",
                            check_id="benchmark.slow",
                            message=(
                                f"Doctor probe runs average {float(mean_duration):.1f}s, which is expensive for iterative search."
                            ),
                            suggested_fix=(
                                "Prefer a cheaper screening benchmark or lower-cost stage for the outer loop."
                            ),
                        )

    error_count = sum(1 for finding in findings if finding["severity"] == "error")
    warning_count = sum(1 for finding in findings if finding["severity"] == "warning")
    status = "blocked" if error_count else ("ready_with_warnings" if warning_count else "ready")

    return {
        "format_version": _DOCTOR_FORMAT_VERSION,
        "status": status,
        "finding_count": len(findings),
        "summary": {
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": sum(1 for finding in findings if finding["severity"] == "info"),
        },
        "findings": findings,
        "project": project_shape,
        "generator": {
            "generator_id": generator_report.get("generator_id"),
            "generator_ready": generator_report.get("generator_ready", False),
            "resolved_command_path": generator_report.get("resolved_command_path"),
            "options": generator_options,
        },
        "benchmark_validation": benchmark_validation,
        "benchmark_probe": benchmark_probe,
    }


def _handle_doctor(args: argparse.Namespace) -> int:
    rendered = _render_doctor_report(args)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0 if rendered["status"] != "blocked" else 1

    print(f"Status: {rendered['status']}")
    project = rendered["project"]
    assert isinstance(project, dict)
    if project.get("project_config_path") is not None:
        print(f"Project config: {project['project_config_path']}")
    if project.get("target_root") is not None:
        print(f"Target root: {project['target_root']}")
    generator = rendered["generator"]
    assert isinstance(generator, dict)
    print(f"Generator: {generator.get('generator_id') or '(none)'}")
    benchmark_validation = rendered["benchmark_validation"]
    assert isinstance(benchmark_validation, dict)
    print(f"Adapter: {benchmark_validation.get('adapter_id') or '(none)'}")
    print(f"Stage: {benchmark_validation.get('stage') or '(none)'}")
    print(f"Benchmark valid: {'yes' if benchmark_validation.get('valid') else 'no'}")
    benchmark_probe = rendered.get("benchmark_probe")
    if isinstance(benchmark_probe, dict):
        summary = benchmark_probe.get("validation_summary")
        if isinstance(summary, dict):
            run_count = summary.get("run_count")
            success_rate = summary.get("success_rate")
            stability_summary = summary.get("stability_summary")
            stability_score = (
                stability_summary.get("stability_score")
                if isinstance(stability_summary, dict)
                else None
            )
            if isinstance(success_rate, (int, float)):
                print(
                    f"Benchmark probe: {run_count} runs, success rate {float(success_rate):.2f}"
                )
            if isinstance(stability_score, (int, float)):
                print(f"Stability score: {float(stability_score):.2f}")
    print(f"Findings: {rendered['finding_count']}")
    for finding in rendered["findings"]:
        assert isinstance(finding, dict)
        print(
            f"- {finding['severity'].upper()} [{finding['check_id']}]: {finding['message']}"
        )
        print(f"  fix: {finding['suggested_fix']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0 if rendered["status"] != "blocked" else 1
