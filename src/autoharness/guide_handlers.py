"""Guide command for bootstrapping autoharness project config."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .cli_arguments import DEFAULT_SETTINGS_PATH, DEFAULT_WORKSPACES_ROOT
from .doctor_handlers import _render_doctor_report
from .guide_assistant import (
    build_assistant_next_prompt,
    build_assistant_onboarding_packet,
)
from .guide_discovery import (
    default_generator_selection,
    detect_benchmark_command,
    detect_editable_surfaces,
    slugify,
)
from .guide_questions import (
    prompt_choice,
    prompt_csv_list,
    prompt_shell_command,
    prompt_text,
    prompt_yes_no,
    stdio_supports_interaction,
)
from .outputs import _emit_json_output, _write_json, _write_text_file, _write_yaml
from .project_config import (
    PROJECT_CONFIG_FORMAT_VERSION,
    apply_project_defaults,
)


def _project_summary_text(
    *,
    project_name: str,
    workspace_id: str,
    benchmark_name: str,
    editable_surfaces: list[str],
    benchmark_command: list[str],
    benchmark_reason: str,
    config_path: Path,
    benchmark_config_path: Path,
) -> str:
    editable_line = ", ".join(editable_surfaces) if editable_surfaces else "(none detected)"
    command_line = " ".join(benchmark_command)
    return (
        f"# Autoharness Project Summary\n\n"
        f"Project: {project_name}\n\n"
        f"- Workspace id: {workspace_id}\n"
        f"- Benchmark name: {benchmark_name}\n"
        f"- Editable surfaces: {editable_line}\n"
        f"- Benchmark command: `{command_line}`\n"
        f"- Detection note: {benchmark_reason}\n\n"
        f"Generated files:\n\n"
        f"- `{config_path.name}`\n"
        f"- `{benchmark_config_path}`\n\n"
        f"Suggested next steps:\n\n"
        f"1. Inspect `{benchmark_config_path}` and replace the command if needed.\n"
        f"2. Run `autoharness run-benchmark`.\n"
        f"3. Run `autoharness optimize`.\n"
        f"4. Run `autoharness report`.\n"
    )


def _assistant_brief_text(
    *,
    assistant: str,
    target_root: Path,
    workspace_id: str,
    benchmark_name: str,
    editable_surfaces: list[str],
    benchmark_command: list[str],
    benchmark_reason: str,
    config_path: Path,
    benchmark_config_path: Path,
    summary_path: Path,
    assistant_packet_path: Path,
) -> str:
    assistant_label = {
        "codex": "Codex",
        "claude": "Claude Code",
        "generic": "your coding assistant",
    }.get(assistant, assistant)
    editable_line = ", ".join(editable_surfaces) if editable_surfaces else "(none detected)"
    command_line = " ".join(benchmark_command)
    return (
        f"# Autoharness Assistant Brief\n\n"
        f"You are helping onboard a repo into `autoharness`.\n\n"
        f"Assistant target: {assistant_label}\n\n"
        f"Use `docs/ONBOARDING.md` as the source of truth.\n\n"
        f"Current generated context:\n\n"
        f"- Target root: `{target_root}`\n"
        f"- Workspace id: `{workspace_id}`\n"
        f"- Benchmark name: `{benchmark_name}`\n"
        f"- Editable surfaces: {editable_line}\n"
        f"- Detected benchmark command: `{command_line}`\n"
        f"- Detection note: {benchmark_reason}\n"
        f"- Project config: `{config_path}`\n"
        f"- Benchmark config: `{benchmark_config_path}`\n"
        f"- Project summary: `{summary_path}`\n\n"
        f"- Onboarding packet: `{assistant_packet_path}`\n\n"
        f"What to do next:\n\n"
        f"1. Read `docs/ONBOARDING.md`.\n"
        f"2. Read the onboarding packet JSON and start with the highest-priority open question.\n"
        f"3. Inspect the generated `autoharness.yaml` and benchmark config.\n"
        f"4. Ask one or two focused questions if important setup details are still unclear.\n"
        f"5. Help the user refine benchmark command, editable surfaces, autonomy mode, and proposal backend.\n"
        f"6. Do not edit application code during onboarding unless the user explicitly asks.\n"
        f"7. Aim to leave the user ready to run `autoharness run-benchmark`, `autoharness optimize`, and `autoharness report`.\n"
    )


def _guide_is_interactive(args: argparse.Namespace) -> bool:
    if args.non_interactive or args.yes or args.json:
        return False
    return stdio_supports_interaction()


def _validate_guide_args(args: argparse.Namespace) -> None:
    if args.print_next_prompt and args.assistant is None:
        raise SystemExit("`guide --print-next-prompt` requires `--assistant`.")


def _default_generator_options(generator_id: str) -> dict[str, object]:
    if generator_id == "codex_cli":
        return {"sandbox": "read-only"}
    if generator_id == "openai_responses":
        return {"proposal_scope": "balanced"}
    return {}


def _resolve_initial_guide_state(
    *,
    args: argparse.Namespace,
    target_root: Path,
) -> dict[str, object]:
    project_name = target_root.name or "project"
    workspace_id = args.workspace_id or slugify(project_name)
    benchmark_name = args.benchmark_name or f"{workspace_id}-screening"
    objective = (
        args.objective
        or "Improve harness benchmark performance without regressions"
    )
    editable_surfaces = (
        list(args.editable_surface)
        if args.editable_surface is not None
        else detect_editable_surfaces(target_root)
    )
    protected_surfaces = list(args.protected_surface or [])
    benchmark_command, benchmark_reason = detect_benchmark_command(target_root)
    if isinstance(args.benchmark_command, str) and args.benchmark_command.strip():
        from shlex import split as shlex_split

        benchmark_command = shlex_split(args.benchmark_command.strip())
        benchmark_reason = "Using explicit benchmark command override."

    detected_generator_id, detected_generator_options = default_generator_selection(
        assistant=args.assistant,
    )
    generator_id = args.generator or detected_generator_id
    generator_options = _default_generator_options(generator_id)
    if not args.generator:
        generator_options = dict(detected_generator_options)

    autonomy_mode = args.autonomy or "bounded"
    return {
        "project_name": project_name,
        "workspace_id": workspace_id,
        "benchmark_name": benchmark_name,
        "objective": objective,
        "editable_surfaces": editable_surfaces,
        "protected_surfaces": protected_surfaces,
        "benchmark_command": benchmark_command,
        "benchmark_reason": benchmark_reason,
        "generator_id": generator_id,
        "generator_options": generator_options,
        "autonomy_mode": autonomy_mode,
    }


def _maybe_run_interactive_questions(
    *,
    args: argparse.Namespace,
    state: dict[str, object],
) -> dict[str, object]:
    if not _guide_is_interactive(args):
        return state

    print("Guide detected a starter setup and will ask a few focused questions.")
    state["workspace_id"] = prompt_text(
        label="Workspace id",
        default=str(state["workspace_id"]),
    )
    state["objective"] = prompt_text(
        label="Optimization objective",
        default=str(state["objective"]),
    )
    state["benchmark_command"] = prompt_shell_command(
        label="Benchmark command",
        default=list(state["benchmark_command"]),
    )
    state["editable_surfaces"] = prompt_csv_list(
        label="Editable surfaces (comma-separated)",
        default=list(state["editable_surfaces"]),
    )
    state["autonomy_mode"] = prompt_choice(
        label="Autonomy mode",
        default=str(state["autonomy_mode"]),
        choices=("proposal", "bounded", "full"),
    )
    if str(state["autonomy_mode"]) == "full":
        state["protected_surfaces"] = prompt_csv_list(
            label="Protected surfaces (comma-separated)",
            default=list(state["protected_surfaces"]),
        )
    state["generator_id"] = prompt_choice(
        label="Proposal generator",
        default=str(state["generator_id"]),
        choices=("failure_summary", "codex_cli", "claude_code", "openai_responses"),
    )
    state["generator_options"] = _default_generator_options(str(state["generator_id"]))
    state["benchmark_name"] = args.benchmark_name or f"{state['workspace_id']}-screening"
    state["benchmark_reason"] = "Guide confirmed or refined the detected benchmark command."
    return state


def _build_project_payloads(
    *,
    args: argparse.Namespace,
    target_root: Path,
    config_path: Path,
    benchmark_config_path: Path,
    summary_path: Path,
    assistant_packet_path: Path | None,
    state: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], str | None]:
    target_root_config_value = os.path.relpath(
        target_root,
        start=config_path.parent,
    )
    benchmark_config_value = os.path.relpath(
        benchmark_config_path,
        start=config_path.parent,
    )
    generator_id = str(state["generator_id"])
    generator_options = dict(state["generator_options"])
    project_config = {
        "format_version": PROJECT_CONFIG_FORMAT_VERSION,
        "target_root": target_root_config_value,
        "workspace": {
            "id": str(state["workspace_id"]),
            "root": str(DEFAULT_WORKSPACES_ROOT),
            "track_id": "main",
            "objective": str(state["objective"]),
            "benchmark": str(state["benchmark_name"]),
            "domain": "general",
        },
        "benchmark": {
            "adapter": "generic_command",
            "config": benchmark_config_value,
            "preset": None,
            "stage": "screening",
        },
        "generator": {
            "id": generator_id,
            "intervention_class": "source",
            "options": generator_options,
        },
        "campaign": {
            "stage": "screening",
            "generator": generator_id,
            "intervention_classes": ["source"],
            "max_iterations": 10,
        },
        "autonomy": {
            "mode": str(state["autonomy_mode"]),
            "settings_path": str(DEFAULT_SETTINGS_PATH),
            "editable_surfaces": list(state["editable_surfaces"]),
            "protected_surfaces": list(state["protected_surfaces"]),
        },
    }
    benchmark_config = {
        "benchmark_name": str(state["benchmark_name"]),
        "workdir": str(target_root),
        "command": list(state["benchmark_command"]),
    }
    assistant_brief = (
        _assistant_brief_text(
            assistant=args.assistant,
            target_root=target_root,
            workspace_id=str(state["workspace_id"]),
            benchmark_name=str(state["benchmark_name"]),
            editable_surfaces=list(state["editable_surfaces"]),
            benchmark_command=list(state["benchmark_command"]),
            benchmark_reason=str(state["benchmark_reason"]),
            config_path=config_path,
            benchmark_config_path=benchmark_config_path,
            summary_path=summary_path,
            assistant_packet_path=assistant_packet_path or (config_path.parent / "autoharness.onboarding.json"),
        )
        if args.assistant is not None and assistant_packet_path is not None
        else None
    )
    return project_config, benchmark_config, assistant_brief


def _guide_doctor_args(
    *,
    config_path: Path,
    skip_benchmark_runs: bool,
) -> argparse.Namespace:
    raw_argv = ["--project-config", str(config_path), "doctor"]
    doctor_args = argparse.Namespace(
        command="doctor",
        project_config=config_path,
        target_root=None,
        adapter=None,
        config=None,
        preset=None,
        set=[],
        stage="screening",
        generator=None,
        generator_option=[],
        repeat=3,
        skip_benchmark_runs=skip_benchmark_runs,
        json=False,
        output=None,
    )
    return apply_project_defaults(
        args=doctor_args,
        raw_argv=raw_argv,
        cwd=config_path.parent,
    )


def _should_run_benchmark_probe(args: argparse.Namespace) -> bool:
    if args.run_benchmark_probe:
        return True
    if not _guide_is_interactive(args):
        return False
    return prompt_yes_no(
        label="Run repeated benchmark probe now",
        default=False,
    )


def _render_doctor_for_guide(
    *,
    args: argparse.Namespace,
    config_path: Path,
) -> dict[str, object] | None:
    if args.skip_doctor:
        return None

    doctor_report = _render_doctor_report(
        _guide_doctor_args(
            config_path=config_path,
            skip_benchmark_runs=True,
        )
    )
    if _should_run_benchmark_probe(args):
        doctor_report = _render_doctor_report(
            _guide_doctor_args(
                config_path=config_path,
                skip_benchmark_runs=False,
            )
        )
    return doctor_report


def _emit_guide_doctor_summary(doctor_report: dict[str, object]) -> None:
    print(f"Doctor status: {doctor_report['status']}")
    findings = doctor_report.get("findings")
    if not isinstance(findings, list):
        return
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        print(
            f"- {finding['severity'].upper()} [{finding['check_id']}]: {finding['message']}"
        )
        print(f"  fix: {finding['suggested_fix']}")


def _handle_guide(args: argparse.Namespace) -> int:
    _validate_guide_args(args)
    target_root = args.target_root.resolve()
    if not target_root.exists():
        raise SystemExit(f"Guide target root not found: {target_root}")
    if not target_root.is_dir():
        raise SystemExit(f"Guide target root must be a directory: {target_root}")

    state = _resolve_initial_guide_state(args=args, target_root=target_root)
    state = _maybe_run_interactive_questions(args=args, state=state)

    config_path = args.output_config.resolve()
    benchmark_config_dir = args.benchmark_config_dir.resolve()
    benchmark_config_path = benchmark_config_dir / "screening.yaml"
    summary_path = args.summary_path.resolve()
    assistant_brief_path = None
    assistant_packet_path = None
    if args.assistant is not None:
        assistant_brief_path = (
            args.assistant_brief_path.resolve()
            if args.assistant_brief_path is not None
            else (config_path.parent / f"autoharness.{args.assistant}.md")
        )
        assistant_packet_path = (
            args.assistant_packet_path.resolve()
            if args.assistant_packet_path is not None
            else (config_path.parent / "autoharness.onboarding.json")
        )

    project_config, benchmark_config, assistant_brief = _build_project_payloads(
        args=args,
        target_root=target_root,
        config_path=config_path,
        benchmark_config_path=benchmark_config_path,
        summary_path=summary_path,
        assistant_packet_path=assistant_packet_path,
        state=state,
    )

    rendered = {
        "project_name": str(state["project_name"]),
        "target_root": str(target_root),
        "workspace_id": str(state["workspace_id"]),
        "benchmark_name": str(state["benchmark_name"]),
        "editable_surfaces": list(state["editable_surfaces"]),
        "protected_surfaces": list(state["protected_surfaces"]),
        "benchmark_command": list(state["benchmark_command"]),
        "benchmark_reason": str(state["benchmark_reason"]),
        "generator_id": str(state["generator_id"]),
        "autonomy_mode": str(state["autonomy_mode"]),
        "output_config": str(config_path),
        "benchmark_config_path": str(benchmark_config_path),
        "summary_path": str(summary_path),
        "assistant": args.assistant,
        "assistant_brief_path": (
            str(assistant_brief_path) if assistant_brief_path is not None else None
        ),
        "assistant_packet_path": (
            str(assistant_packet_path) if assistant_packet_path is not None else None
        ),
        "assistant_brief": assistant_brief,
        "assistant_packet": None,
        "next_prompt": None,
        "project_config": project_config,
        "benchmark_config": benchmark_config,
        "interactive": _guide_is_interactive(args),
        "dry_run": args.dry_run,
        "doctor_report": None,
    }

    if not args.dry_run:
        paths_to_write = [config_path, benchmark_config_path, summary_path]
        if assistant_brief_path is not None:
            paths_to_write.append(assistant_brief_path)
        if assistant_packet_path is not None:
            paths_to_write.append(assistant_packet_path)
        for path in paths_to_write:
            if path.exists() and not args.force:
                raise SystemExit(
                    f"Refusing to overwrite existing file: {path}. Use --force."
                )
        _write_yaml(config_path, project_config)
        _write_yaml(benchmark_config_path, benchmark_config)
        _write_text_file(
            summary_path,
            _project_summary_text(
                project_name=str(state["project_name"]),
                workspace_id=str(state["workspace_id"]),
                benchmark_name=str(state["benchmark_name"]),
                editable_surfaces=list(state["editable_surfaces"]),
                benchmark_command=list(state["benchmark_command"]),
                benchmark_reason=str(state["benchmark_reason"]),
                config_path=config_path,
                benchmark_config_path=Path(
                    os.path.relpath(benchmark_config_path, start=config_path.parent)
                ),
            ),
        )
        if assistant_brief_path is not None and assistant_brief is not None:
            _write_text_file(assistant_brief_path, assistant_brief)
        doctor_report = _render_doctor_for_guide(
            args=args,
            config_path=config_path,
        )
        rendered["doctor_report"] = doctor_report
        if (
            args.assistant is not None
            and assistant_brief_path is not None
            and assistant_packet_path is not None
        ):
            assistant_packet = build_assistant_onboarding_packet(
                assistant=args.assistant,
                target_root=target_root,
                state=state,
                config_path=config_path,
                benchmark_config_path=benchmark_config_path,
                summary_path=summary_path,
                assistant_brief_path=assistant_brief_path,
                doctor_report=doctor_report,
                interactive=_guide_is_interactive(args),
            )
            rendered["assistant_packet"] = assistant_packet
            _write_json(assistant_packet_path, assistant_packet)

    if (
        args.print_next_prompt
        and args.assistant is not None
        and assistant_brief_path is not None
        and assistant_packet_path is not None
    ):
        rendered["next_prompt"] = build_assistant_next_prompt(
            assistant=args.assistant,
            config_path=config_path,
            benchmark_config_path=benchmark_config_path,
            assistant_brief_path=assistant_brief_path,
            assistant_packet_path=assistant_packet_path,
        )

    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    print(f"Target root: {target_root}")
    print(f"Workspace id: {state['workspace_id']}")
    print(f"Benchmark name: {state['benchmark_name']}")
    print(
        "Editable surfaces: "
        + (
            ", ".join(list(state["editable_surfaces"]))
            if list(state["editable_surfaces"])
            else "(none detected)"
        )
    )
    print("Benchmark command: " + " ".join(list(state["benchmark_command"])))
    print(f"Detection note: {state['benchmark_reason']}")
    print(f"Autonomy mode: {state['autonomy_mode']}")
    print(f"Proposal generator: {state['generator_id']}")
    if args.dry_run:
        print("Dry run: no files written")
    else:
        print(f"Wrote project config: {config_path}")
        print(f"Wrote benchmark config: {benchmark_config_path}")
        print(f"Wrote project summary: {summary_path}")
        if assistant_brief_path is not None:
            print(f"Wrote assistant brief: {assistant_brief_path}")
        if assistant_packet_path is not None:
            print(f"Wrote onboarding packet: {assistant_packet_path}")
        doctor_report = rendered.get("doctor_report")
        if isinstance(doctor_report, dict):
            _emit_guide_doctor_summary(doctor_report)
        next_prompt = rendered.get("next_prompt")
        if isinstance(next_prompt, str):
            assistant_label = {
                "codex": "Codex",
                "claude": "Claude Code",
                "generic": "Assistant",
            }.get(args.assistant, "Assistant")
            print()
            print(f"Next prompt for {assistant_label}:")
            print(next_prompt)
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0
