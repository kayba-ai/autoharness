"""Local command-backed proposal generator."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ..editing import EditPlan, edit_plan_from_dict
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


class LocalCommandProposalGenerator:
    """Invoke one local command that returns a proposal JSON payload on stdout."""

    generator_id = "local_command"

    def generate(
        self,
        *,
        context: ProposalGenerationContext,
        request: ProposalGenerationRequest,
        edit_plan_path: Path | None = None,
    ) -> GeneratedProposal:
        del edit_plan_path
        command_path = _resolve_command_path(request.metadata)
        timeout_seconds = _resolve_timeout_seconds(request.metadata)
        command_cwd = _resolve_command_cwd(request.metadata)
        generator_input_payload = {
            "format_version": "autoharness.local_command_input.v1",
            "request": request.to_dict(),
            "context": context.to_dict(),
        }
        process = _run_generator_command(
            command_path=command_path,
            timeout_seconds=timeout_seconds,
            command_cwd=command_cwd,
            payload=generator_input_payload,
        )
        if process.returncode != 0:
            stderr = process.stderr.strip()
            raise ProposalGenerationProcessError(
                f"`local_command` exited with {process.returncode}: "
                f"{stderr or 'no stderr output'}"
            )
        proposal_payload, repair_steps = _decode_command_payload(
            process.stdout,
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
                "provider": "local_command",
                "command_path": str(command_path),
                "command_cwd": str(command_cwd) if command_cwd is not None else None,
                "timeout_seconds": timeout_seconds,
                "generator_input_payload": generator_input_payload,
                "raw_stdout": process.stdout,
                "raw_stderr": process.stderr,
                "repair_steps": repair_steps,
            },
        )


def _resolve_command_path(metadata: dict[str, Any]) -> Path:
    command_path = metadata.get("command_path")
    if isinstance(command_path, str) and command_path:
        return Path(command_path)
    raise ValueError(
        "The `local_command` generator requires "
        "`--generator-option command_path=/path/to/script`."
    )


def _resolve_timeout_seconds(metadata: dict[str, Any]) -> int:
    timeout_value = metadata.get("timeout_seconds", "60")
    try:
        timeout_seconds = int(timeout_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("`local_command.timeout_seconds` must be an integer.") from exc
    if timeout_seconds <= 0:
        raise ValueError("`local_command.timeout_seconds` must be greater than zero.")
    return timeout_seconds


def _resolve_command_cwd(metadata: dict[str, Any]) -> Path | None:
    cwd_value = metadata.get("command_cwd")
    if not isinstance(cwd_value, str) or not cwd_value:
        return None
    return Path(cwd_value)


def _run_generator_command(
    *,
    command_path: Path,
    timeout_seconds: int,
    command_cwd: Path | None,
    payload: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [str(command_path)],
            input=json.dumps(payload, indent=2),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            cwd=str(command_cwd) if command_cwd is not None else None,
        )
    except FileNotFoundError as exc:
        raise ProposalGenerationProcessError(
            f"`local_command` could not execute `{command_path}`."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ProposalGenerationTimeoutError(
            f"`local_command` timed out after {timeout_seconds}s: {command_path}"
        ) from exc


def _decode_command_payload(
    stdout: str,
    *,
    command_path: Path,
    request: ProposalGenerationRequest,
) -> tuple[dict[str, Any], list[str]]:
    try:
        payload, response_repair_steps = decode_json_object_text(stdout)
        payload, payload_repair_steps = normalize_generated_payload(
            payload=payload,
            request=request,
        )
    except ValueError as exc:
        raise ProposalGenerationProcessError(
            f"`local_command` output from `{command_path}` returned an invalid edit plan."
        ) from exc
    except Exception as exc:
        raise ProposalGenerationProcessError(
            f"`local_command` output from `{command_path}` was not valid JSON."
        ) from exc
    return payload, response_repair_steps + payload_repair_steps
