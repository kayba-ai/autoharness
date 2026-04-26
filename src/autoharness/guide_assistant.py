"""Assistant-facing onboarding handoff helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


_HIGH_PRIORITY_FINDING_QUESTIONS = {
    "autonomy.empty_editable_surfaces": {
        "id": "editable_surfaces",
        "priority": "high",
        "question": "Which folders may autoharness edit during optimization?",
        "why": "Bounded autonomy needs an explicit editable surface list.",
    },
    "benchmark.config_invalid": {
        "id": "benchmark_config",
        "priority": "high",
        "question": "What should the screening benchmark config or command be so it validates cleanly?",
        "why": "The generated benchmark config is not runnable as written.",
    },
    "benchmark.placeholder_command": {
        "id": "benchmark_command",
        "priority": "high",
        "question": "What command should autoharness use as the screening benchmark?",
        "why": "The guide could not confidently detect a real benchmark command.",
    },
    "generator.openai_auth_missing": {
        "id": "generator_backend",
        "priority": "high",
        "question": "Should this project use a local proposal backend, or should OpenAI credentials be configured?",
        "why": "The configured proposal generator cannot run without authentication.",
    },
}
_WARNING_FINDING_QUESTIONS = {
    "benchmark.command_failed": {
        "id": "baseline_health",
        "priority": "medium",
        "question": "Are the current benchmark failures expected baseline behavior or signs of a broken setup?",
        "why": "Optimization should start from a meaningful baseline rather than a misconfigured run.",
    },
    "benchmark.flaky": {
        "id": "benchmark_stability",
        "priority": "medium",
        "question": "How can the benchmark be made more deterministic across repeated runs?",
        "why": "Unstable benchmarks make promotion decisions noisy.",
    },
    "benchmark.slow": {
        "id": "benchmark_cost",
        "priority": "medium",
        "question": "Is there a cheaper screening benchmark or lighter-weight command for the outer loop?",
        "why": "Slow benchmarks make iterative optimization expensive.",
    },
}


def build_assistant_onboarding_packet(
    *,
    assistant: str,
    target_root: Path,
    state: dict[str, object],
    config_path: Path,
    benchmark_config_path: Path,
    summary_path: Path,
    assistant_brief_path: Path,
    doctor_report: dict[str, object] | None,
    interactive: bool,
) -> dict[str, object]:
    findings = (
        list(doctor_report.get("findings", []))
        if isinstance(doctor_report, dict)
        and isinstance(doctor_report.get("findings"), list)
        else []
    )
    open_questions = _open_questions_from_findings(
        findings=findings,
        state=state,
        doctor_report=doctor_report,
    )
    return {
        "format_version": "autoharness.onboarding_packet.v1",
        "assistant": assistant,
        "target_root": str(target_root),
        "interactive_guide_run": interactive,
        "known_facts": {
            "project_name": str(state["project_name"]),
            "workspace_id": str(state["workspace_id"]),
            "benchmark_name": str(state["benchmark_name"]),
            "objective": str(state["objective"]),
            "benchmark_command": list(state["benchmark_command"]),
            "benchmark_reason": str(state["benchmark_reason"]),
            "editable_surfaces": list(state["editable_surfaces"]),
            "protected_surfaces": list(state["protected_surfaces"]),
            "autonomy_mode": str(state["autonomy_mode"]),
            "generator_id": str(state["generator_id"]),
            "generator_options": dict(state["generator_options"]),
        },
        "generated_files": {
            "project_config": str(config_path),
            "benchmark_config": str(benchmark_config_path),
            "project_summary": str(summary_path),
            "assistant_brief": str(assistant_brief_path),
        },
        "doctor_report": doctor_report,
        "open_questions": open_questions,
        "recommended_next_action": _recommended_next_action(
            doctor_report=doctor_report,
            open_questions=open_questions,
        ),
        "assistant_instructions": {
            "conversation_style": "Ask one or two focused questions at a time.",
            "start_with": "Summarize the known facts, then ask the highest-priority unresolved question.",
            "avoid": "Do not edit application code during onboarding unless the user explicitly asks.",
        },
    }


def build_assistant_next_prompt(
    *,
    assistant: str,
    config_path: Path,
    benchmark_config_path: Path,
    assistant_brief_path: Path,
    assistant_packet_path: Path,
) -> str:
    assistant_label = {
        "codex": "Codex",
        "claude": "Claude Code",
        "generic": "your coding assistant",
    }.get(assistant, assistant)
    return (
        f"You are helping finish `autoharness` onboarding for this repo in {assistant_label}.\n\n"
        "Read these files first:\n"
        "- docs/ONBOARDING.md\n"
        f"- {_display_path(assistant_brief_path)}\n"
        f"- {_display_path(assistant_packet_path)}\n"
        f"- {_display_path(config_path)}\n"
        f"- {_display_path(benchmark_config_path)}\n\n"
        "Then:\n"
        "- summarize the known facts briefly\n"
        "- start with the highest-priority open question and doctor findings\n"
        "- ask one or two focused questions at a time\n"
        "- update the generated autoharness config files if needed\n"
        "- warn about flaky, leaky, or slow benchmark setups\n"
        "- do not edit application code unless I explicitly ask\n\n"
        "Leave the repo ready for:\n\n"
        "```bash\n"
        "autoharness doctor\n"
        "autoharness run-benchmark\n"
        "autoharness optimize\n"
        "autoharness report\n"
        "```\n"
    )


def _display_path(path: Path) -> str:
    try:
        return os.path.relpath(path, start=Path.cwd())
    except ValueError:
        return str(path)


def _open_questions_from_findings(
    *,
    findings: list[object],
    state: dict[str, object],
    doctor_report: dict[str, object] | None,
) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for raw_finding in findings:
        if not isinstance(raw_finding, dict):
            continue
        check_id = str(raw_finding.get("check_id", ""))
        template = _HIGH_PRIORITY_FINDING_QUESTIONS.get(check_id)
        if template is None:
            template = _WARNING_FINDING_QUESTIONS.get(check_id)
        if template is None or template["id"] in seen_ids:
            continue
        questions.append(dict(template))
        seen_ids.add(template["id"])

    if (
        str(state.get("autonomy_mode")) == "full"
        and not list(state.get("protected_surfaces", []))
        and "protected_surfaces" not in seen_ids
    ):
        questions.append(
            {
                "id": "protected_surfaces",
                "priority": "low",
                "question": "Are there any paths that should stay protected even with full autonomy?",
                "why": "Full autonomy without protected paths may be broader than necessary.",
            }
        )
        seen_ids.add("protected_surfaces")

    if (
        isinstance(doctor_report, dict)
        and doctor_report.get("status") == "ready"
        and "benchmark_probe" not in seen_ids
        and (
            not isinstance(doctor_report.get("benchmark_probe"), dict)
            or doctor_report["benchmark_probe"] is None
        )
    ):
        questions.append(
            {
                "id": "benchmark_probe",
                "priority": "low",
                "question": "Should we run repeated benchmark probes now to measure flakiness and runtime?",
                "why": "The structural doctor pass succeeded, but repeated-run stability has not been measured yet.",
            }
        )

    return questions


def _recommended_next_action(
    *,
    doctor_report: dict[str, object] | None,
    open_questions: list[dict[str, str]],
) -> str:
    if not isinstance(doctor_report, dict):
        return "Review the generated setup with the user and confirm the benchmark command."
    status = str(doctor_report.get("status", "ready_with_warnings"))
    if status == "blocked":
        if open_questions:
            return "Resolve the highest-priority open question, update the generated files, and rerun `autoharness doctor`."
        return "Inspect the doctor findings, fix the blocking setup issue, and rerun `autoharness doctor`."
    if status == "ready_with_warnings":
        if open_questions:
            return "Confirm the warning tradeoffs with the user, update the config if needed, then rerun `autoharness doctor` or `autoharness run-benchmark`."
        return "Review the warnings with the user, then run `autoharness run-benchmark`."
    if open_questions:
        return "Ask the next focused question, update the generated files if needed, then run `autoharness run-benchmark`."
    return "The setup looks ready. Run `autoharness run-benchmark`, then `autoharness optimize`."
