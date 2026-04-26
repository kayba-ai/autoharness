"""Local coding-assistant CLI-backed proposal generators."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..editing import EditPlan
from ..proposal_context import ProposalGenerationContext
from .base import (
    GeneratedProposal,
    ProposalGenerationProcessError,
    ProposalGenerationRequest,
    ProposalGenerationTimeoutError,
    decode_json_object_text,
    normalize_generated_payload,
    normalized_edit_plan_from_payload,
)

_ASSISTANT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "hypothesis": {"type": "string"},
        "summary": {"type": "string"},
        "intervention_class": {"type": "string"},
        "operations": {
            "type": "array",
            "items": {"type": "object"},
        },
    },
    "required": ["summary", "operations"],
    "additionalProperties": True,
}


@dataclass(frozen=True)
class _AssistantProcessResult:
    process: subprocess.CompletedProcess[str]
    response_text: str
    executed_command: tuple[str, ...]
    prompt_text: str


class _AssistantCLIProposalGenerator:
    assistant_id: str
    generator_id: str
    assistant_label: str
    default_command_path: str

    def generate(
        self,
        *,
        context: ProposalGenerationContext,
        request: ProposalGenerationRequest,
        edit_plan_path: Path | None = None,
    ) -> GeneratedProposal:
        del edit_plan_path
        target_root = Path(context.target_root)
        command_path = _resolve_command_path(
            metadata=request.metadata,
            default_command_path=self.default_command_path,
        )
        timeout_seconds = _resolve_timeout_seconds(request.metadata)
        generator_input_payload = {
            "format_version": "autoharness.assistant_cli_input.v1",
            "assistant": self.assistant_id,
            "request": request.to_dict(),
            "context": context.to_dict(),
        }

        with tempfile.TemporaryDirectory(
            prefix=f"autoharness_{self.generator_id}_"
        ) as tempdir_name:
            tempdir = Path(tempdir_name)
            input_path = tempdir / "proposal_input.json"
            input_path.write_text(
                json.dumps(generator_input_payload, indent=2) + "\n",
                encoding="utf-8",
            )
            schema_path = tempdir / "proposal_schema.json"
            schema_path.write_text(
                json.dumps(_ASSISTANT_OUTPUT_SCHEMA, indent=2) + "\n",
                encoding="utf-8",
            )
            prompt_text = _assistant_prompt_text(
                assistant_label=self.assistant_label,
                assistant_id=self.assistant_id,
                input_path=input_path,
                target_root=target_root,
                intervention_class=request.intervention_class,
            )
            result = self._run_assistant(
                command_path=command_path,
                target_root=target_root,
                tempdir=tempdir,
                schema_path=schema_path,
                prompt_text=prompt_text,
                timeout_seconds=timeout_seconds,
                metadata=request.metadata,
            )

        if result.process.returncode != 0:
            stderr = result.process.stderr.strip()
            raise ProposalGenerationProcessError(
                f"`{self.generator_id}` exited with {result.process.returncode}: "
                f"{stderr or 'no stderr output'}"
            )
        proposal_payload, repair_steps = _decode_assistant_payload(
            raw_text=result.response_text,
            generator_id=self.generator_id,
            command_path=command_path,
            request=request,
        )
        edit_plan = normalized_edit_plan_from_payload(proposal_payload)
        intervention_class = request.intervention_class or str(
            proposal_payload.get("intervention_class", "source")
        )
        hypothesis = (
            str(proposal_payload["hypothesis"])
            if proposal_payload.get("hypothesis") is not None
            else request.hypothesis_seed
        )
        summary = str(proposal_payload.get("summary", edit_plan.summary))
        payload_metadata = (
            dict(proposal_payload.get("metadata", {}))
            if isinstance(proposal_payload.get("metadata"), dict)
            else {}
        )
        return GeneratedProposal(
            generator_id=self.generator_id,
            edit_plan=EditPlan(
                format_version=edit_plan.format_version,
                summary=summary,
                operations=edit_plan.operations,
            ),
            summary=summary,
            hypothesis=hypothesis,
            intervention_class=intervention_class,
            metadata={
                **payload_metadata,
                "generation_request": request.to_dict(),
                "provider": self.generator_id,
                "assistant_id": self.assistant_id,
                "command_path": str(command_path),
                "executed_command": list(result.executed_command),
                "timeout_seconds": timeout_seconds,
                "generator_input_payload": generator_input_payload,
                "prompt_text": result.prompt_text,
                "raw_response_text": result.response_text,
                "raw_stdout": result.process.stdout,
                "raw_stderr": result.process.stderr,
                "repair_steps": repair_steps,
            },
        )

    def _run_assistant(
        self,
        *,
        command_path: Path,
        target_root: Path,
        tempdir: Path,
        schema_path: Path,
        prompt_text: str,
        timeout_seconds: int,
        metadata: dict[str, Any],
    ) -> _AssistantProcessResult:
        raise NotImplementedError


class CodexCLIProposalGenerator(_AssistantCLIProposalGenerator):
    assistant_id = "codex"
    generator_id = "codex_cli"
    assistant_label = "Codex"
    default_command_path = "codex"

    def _run_assistant(
        self,
        *,
        command_path: Path,
        target_root: Path,
        tempdir: Path,
        schema_path: Path,
        prompt_text: str,
        timeout_seconds: int,
        metadata: dict[str, Any],
    ) -> _AssistantProcessResult:
        output_path = tempdir / "codex_last_message.json"
        command = [
            str(command_path),
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--color",
            "never",
            "--sandbox",
            _resolve_codex_sandbox(metadata),
            "--cd",
            str(target_root),
            "--add-dir",
            str(tempdir),
            "--output-schema",
            str(schema_path),
            "--output-last-message",
            str(output_path),
        ]
        model = metadata.get("model")
        if isinstance(model, str) and model.strip():
            command.extend(["--model", model.strip()])
        profile = metadata.get("profile")
        if isinstance(profile, str) and profile.strip():
            command.extend(["--profile", profile.strip()])
        command.append("-")
        try:
            process = subprocess.run(
                command,
                input=prompt_text,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
                cwd=str(target_root),
            )
        except FileNotFoundError as exc:
            raise ProposalGenerationProcessError(
                f"`{self.generator_id}` could not execute `{command_path}`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProposalGenerationTimeoutError(
                f"`{self.generator_id}` timed out after {timeout_seconds}s: {command_path}"
            ) from exc

        response_text = (
            output_path.read_text(encoding="utf-8")
            if output_path.is_file()
            else process.stdout
        )
        return _AssistantProcessResult(
            process=process,
            response_text=response_text,
            executed_command=tuple(command),
            prompt_text=prompt_text,
        )


class ClaudeCodeProposalGenerator(_AssistantCLIProposalGenerator):
    assistant_id = "claude"
    generator_id = "claude_code"
    assistant_label = "Claude Code"
    default_command_path = "claude"

    def _run_assistant(
        self,
        *,
        command_path: Path,
        target_root: Path,
        tempdir: Path,
        schema_path: Path,
        prompt_text: str,
        timeout_seconds: int,
        metadata: dict[str, Any],
    ) -> _AssistantProcessResult:
        del schema_path
        command = [
            str(command_path),
            "--print",
            "--bare",
            "--no-session-persistence",
            "--add-dir",
            str(tempdir),
            "--json-schema",
            json.dumps(_ASSISTANT_OUTPUT_SCHEMA, separators=(",", ":")),
            "--permission-mode",
            _resolve_claude_permission_mode(metadata),
        ]
        model = metadata.get("model")
        if isinstance(model, str) and model.strip():
            command.extend(["--model", model.strip()])
        effort = metadata.get("effort")
        if isinstance(effort, str) and effort.strip():
            command.extend(["--effort", effort.strip()])
        command.append(prompt_text)
        try:
            process = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
                cwd=str(target_root),
            )
        except FileNotFoundError as exc:
            raise ProposalGenerationProcessError(
                f"`{self.generator_id}` could not execute `{command_path}`."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ProposalGenerationTimeoutError(
                f"`{self.generator_id}` timed out after {timeout_seconds}s: {command_path}"
            ) from exc

        return _AssistantProcessResult(
            process=process,
            response_text=process.stdout,
            executed_command=tuple(command),
            prompt_text=prompt_text,
        )


def _resolve_command_path(*, metadata: dict[str, Any], default_command_path: str) -> Path:
    command_path = metadata.get("command_path")
    if isinstance(command_path, str) and command_path.strip():
        return Path(command_path.strip())
    return Path(default_command_path)


def _resolve_timeout_seconds(metadata: dict[str, Any]) -> int:
    timeout_value = metadata.get("timeout_seconds", "180")
    try:
        timeout_seconds = int(timeout_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("`timeout_seconds` must be an integer.") from exc
    if timeout_seconds <= 0:
        raise ValueError("`timeout_seconds` must be greater than zero.")
    return timeout_seconds


def _resolve_codex_sandbox(metadata: dict[str, Any]) -> str:
    sandbox = metadata.get("sandbox", "read-only")
    if not isinstance(sandbox, str) or not sandbox.strip():
        return "read-only"
    return sandbox.strip()


def _resolve_claude_permission_mode(metadata: dict[str, Any]) -> str:
    permission_mode = metadata.get("permission_mode", "default")
    if not isinstance(permission_mode, str) or not permission_mode.strip():
        return "default"
    return permission_mode.strip()


def _assistant_prompt_text(
    *,
    assistant_label: str,
    assistant_id: str,
    input_path: Path,
    target_root: Path,
    intervention_class: str | None,
) -> str:
    intervention_line = (
        f"- Preferred intervention class: `{intervention_class}`\n"
        if isinstance(intervention_class, str) and intervention_class
        else ""
    )
    return (
        f"You are {assistant_label}, generating one autoharness proposal.\n\n"
        f"Read the full proposal-generation payload from `{input_path}`.\n"
        f"The target repo root is `{target_root}`.\n\n"
        f"Task:\n"
        f"- Inspect the repo only as needed to understand the likely harness change.\n"
        f"- Produce one coherent proposal for the current benchmark context.\n"
        f"{intervention_line}"
        f"- Do not apply edits.\n"
        f"- Return exactly one JSON object and nothing else.\n\n"
        f"Output requirements:\n"
        f"- Use only supported operation types: `search_replace`, `write_file`, `delete_file`, `move_path`, and `unified_diff`.\n"
        f"- Paths must be relative to the target repo root.\n"
        f"- Keep the proposal bounded but allow multiple files when they support one hypothesis.\n"
        f"- Prefer harness-side changes over broad unrelated rewrites.\n"
        f"- If context is ambiguous, choose the safest useful candidate rather than stalling.\n\n"
        f"The input file already includes:\n"
        f"- request metadata\n"
        f"- workspace and benchmark context\n"
        f"- recent failure and regression summaries when available\n\n"
        f"Respond for the `{assistant_id}` autoharness generator."
    )


def _decode_assistant_payload(
    *,
    raw_text: str,
    generator_id: str,
    command_path: Path,
    request: ProposalGenerationRequest,
) -> tuple[dict[str, Any], list[str]]:
    try:
        payload, response_repair_steps = decode_json_object_text(raw_text)
        payload, payload_repair_steps = normalize_generated_payload(
            payload=payload,
            request=request,
        )
    except ValueError as exc:
        raise ProposalGenerationProcessError(
            f"`{generator_id}` output from `{command_path}` returned an invalid edit plan."
        ) from exc
    except Exception as exc:
        raise ProposalGenerationProcessError(
            f"`{generator_id}` output from `{command_path}` was not valid JSON."
        ) from exc
    return payload, response_repair_steps + payload_repair_steps
