"""Guide command for bootstrapping autoharness project config."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

from .cli_arguments import DEFAULT_SETTINGS_PATH, DEFAULT_WORKSPACES_ROOT
from .outputs import _emit_json_output, _write_text_file, _write_yaml
from .project_config import PROJECT_CONFIG_FORMAT_VERSION


def _slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9_-]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "demo"


def _detect_editable_surfaces(target_root: Path) -> list[str]:
    candidates = (
        "src",
        "prompts",
        "app",
        "agent",
        "agents",
        "lib",
        "packages",
        "server",
        "client",
    )
    detected = [name for name in candidates if (target_root / name).is_dir()]
    if detected:
        return detected
    return ["src"] if (target_root / "src").exists() else []


def _detect_benchmark_command(target_root: Path) -> tuple[list[str], str]:
    makefile_path = target_root / "Makefile"
    if makefile_path.is_file():
        makefile_text = makefile_path.read_text(encoding="utf-8")
        if re.search(r"(?m)^test\s*:", makefile_text):
            return ["make", "test"], "Detected `test` target in Makefile."

    if any(
        (target_root / name).exists()
        for name in ("pytest.ini", "tox.ini", "conftest.py", "tests")
    ) or (target_root / "pyproject.toml").is_file():
        return ["pytest", "-q"], "Detected a Python test layout."

    package_json = target_root / "package.json"
    if package_json.is_file():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        scripts = payload.get("scripts") if isinstance(payload, dict) else None
        if isinstance(scripts, dict) and isinstance(scripts.get("test"), str):
            return ["npm", "test", "--", "--runInBand"], "Detected an npm test script."

    return (
        ["python", "-c", "print('replace with your benchmark command')"],
        "Could not confidently detect a benchmark command; wrote a placeholder.",
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
        f"2. Run `autoharness setup`.\n"
        f"3. Run `autoharness init`.\n"
        f"4. Run `autoharness run-benchmark`.\n"
        f"5. Run `autoharness optimize`.\n"
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
        f"What to do next:\n\n"
        f"1. Read `docs/ONBOARDING.md`.\n"
        f"2. Inspect the generated `autoharness.yaml` and benchmark config.\n"
        f"3. Ask one or two focused questions if important setup details are still unclear.\n"
        f"4. Help the user refine benchmark command, editable surfaces, and autonomy mode.\n"
        f"5. Do not edit application code during onboarding unless the user explicitly asks.\n"
        f"6. Aim to leave the user ready to run `autoharness setup`, `autoharness init`, `autoharness run-benchmark`, `autoharness optimize`, and `autoharness report`.\n"
    )


def _handle_guide(args: argparse.Namespace) -> int:
    target_root = args.target_root.resolve()
    project_name = target_root.name or "project"
    workspace_id = args.workspace_id or _slugify(project_name)
    benchmark_name = args.benchmark_name or f"{workspace_id}-screening"
    objective = (
        args.objective
        or "Improve harness benchmark performance without regressions"
    )
    editable_surfaces = _detect_editable_surfaces(target_root)
    benchmark_command, benchmark_reason = _detect_benchmark_command(target_root)

    config_path = args.output_config.resolve()
    benchmark_config_dir = args.benchmark_config_dir.resolve()
    benchmark_config_path = benchmark_config_dir / "screening.yaml"
    summary_path = args.summary_path.resolve()
    assistant_brief_path = None
    if args.assistant is not None:
        assistant_brief_path = (
            args.assistant_brief_path.resolve()
            if args.assistant_brief_path is not None
            else (config_path.parent / f"autoharness.{args.assistant}.md")
        )
    target_root_config_value = os.path.relpath(
        target_root,
        start=config_path.parent,
    )
    benchmark_config_value = os.path.relpath(
        benchmark_config_path,
        start=config_path.parent,
    )

    project_config = {
        "format_version": PROJECT_CONFIG_FORMAT_VERSION,
        "target_root": target_root_config_value,
        "workspace": {
            "id": workspace_id,
            "root": str(DEFAULT_WORKSPACES_ROOT),
            "track_id": "main",
            "objective": objective,
            "benchmark": benchmark_name,
            "domain": "general",
        },
        "benchmark": {
            "adapter": "generic_command",
            "config": benchmark_config_value,
            "preset": None,
            "stage": "screening",
        },
        "generator": {
            "id": "openai_responses",
            "intervention_class": "source",
            "options": {
                "proposal_scope": "balanced",
            },
        },
        "campaign": {
            "stage": "screening",
            "generator": "openai_responses",
            "intervention_classes": ["source"],
            "max_iterations": 10,
        },
        "autonomy": {
            "mode": "bounded",
            "settings_path": str(DEFAULT_SETTINGS_PATH),
            "editable_surfaces": editable_surfaces,
            "protected_surfaces": [],
        },
    }
    benchmark_config = {
        "benchmark_name": benchmark_name,
        "workdir": str(target_root),
        "command": benchmark_command,
    }
    assistant_brief = (
        _assistant_brief_text(
            assistant=args.assistant,
            target_root=target_root,
            workspace_id=workspace_id,
            benchmark_name=benchmark_name,
            editable_surfaces=editable_surfaces,
            benchmark_command=benchmark_command,
            benchmark_reason=benchmark_reason,
            config_path=config_path,
            benchmark_config_path=benchmark_config_path,
            summary_path=summary_path,
        )
        if args.assistant is not None
        else None
    )
    rendered = {
        "project_name": project_name,
        "target_root": str(target_root),
        "workspace_id": workspace_id,
        "benchmark_name": benchmark_name,
        "editable_surfaces": editable_surfaces,
        "benchmark_command": benchmark_command,
        "benchmark_reason": benchmark_reason,
        "output_config": str(config_path),
        "benchmark_config_path": str(benchmark_config_path),
        "summary_path": str(summary_path),
        "assistant": args.assistant,
        "assistant_brief_path": str(assistant_brief_path) if assistant_brief_path is not None else None,
        "assistant_brief": assistant_brief,
        "project_config": project_config,
        "benchmark_config": benchmark_config,
        "dry_run": args.dry_run,
    }

    if not args.dry_run:
        paths_to_write = [config_path, benchmark_config_path, summary_path]
        if assistant_brief_path is not None:
            paths_to_write.append(assistant_brief_path)
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
                project_name=project_name,
                workspace_id=workspace_id,
                benchmark_name=benchmark_name,
                editable_surfaces=editable_surfaces,
                benchmark_command=benchmark_command,
                benchmark_reason=benchmark_reason,
                config_path=config_path,
                benchmark_config_path=Path(benchmark_config_value),
            ),
        )
        if assistant_brief_path is not None and assistant_brief is not None:
            _write_text_file(assistant_brief_path, assistant_brief)

    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    print(f"Target root: {target_root}")
    print(f"Workspace id: {workspace_id}")
    print(f"Benchmark name: {benchmark_name}")
    print(
        "Editable surfaces: "
        + (", ".join(editable_surfaces) if editable_surfaces else "(none detected)")
    )
    print("Benchmark command: " + " ".join(benchmark_command))
    print(f"Detection note: {benchmark_reason}")
    if args.dry_run:
        print("Dry run: no files written")
    else:
        print(f"Wrote project config: {config_path}")
        print(f"Wrote benchmark config: {benchmark_config_path}")
        print(f"Wrote project summary: {summary_path}")
        if assistant_brief_path is not None:
            print(f"Wrote assistant brief: {assistant_brief_path}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0
