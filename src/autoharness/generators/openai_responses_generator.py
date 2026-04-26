"""OpenAI Responses-backed proposal generator."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..editing import EditPlan
from ..proposal_context import ProposalGenerationContext
from .base import (
    GeneratedProposal,
    ProposalGenerationError,
    ProposalGenerationProviderAuthError,
    ProposalGenerationProviderError,
    ProposalGenerationProviderRateLimitError,
    ProposalGenerationProviderTransportError,
    ProposalGenerationRequest,
    ProposalGenerationTimeoutError,
    decode_json_object_text,
    normalize_generated_payload,
    normalized_edit_plan_from_payload,
)


_IGNORED_DIRS = {
    ".git",
    ".autoharness",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
}
_PRIORITY_SUFFIXES = {
    "config": (".json", ".yaml", ".yml", ".toml", ".ini"),
    "middleware": (".py", ".ts", ".js", ".json", ".yaml", ".yml"),
    "prompt": (".md", ".txt", ".yaml", ".yml"),
    "source": (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"),
}
_PROPOSAL_SCOPE_VALUES = ("conservative", "balanced", "broad")
_DEFAULT_MAX_OPERATIONS_BY_SCOPE = {
    "conservative": 2,
    "balanced": 6,
    "broad": 10,
}
_SNAPSHOT_FILE_LIMIT_BY_SCOPE = {
    "conservative": 80,
    "balanced": 120,
    "broad": 160,
}
_SNAPSHOT_FILE_SAMPLE_LIMIT_BY_SCOPE = {
    "conservative": 8,
    "balanced": 12,
    "broad": 16,
}
_SNAPSHOT_FILE_CHAR_LIMIT_BY_SCOPE = {
    "conservative": 4000,
    "balanced": 6000,
    "broad": 8000,
}
_SNAPSHOT_PATH_LIST_LIMIT = 40


class OpenAIResponsesProposalGenerator:
    """Generate one proposal via the OpenAI Responses API."""

    generator_id = "openai_responses"

    def generate(
        self,
        *,
        context: ProposalGenerationContext,
        request: ProposalGenerationRequest,
        edit_plan_path: Path | None = None,
    ) -> GeneratedProposal:
        del edit_plan_path
        api_key = os.environ.get("AUTOHARNESS_OPENAI_API_KEY") or os.environ.get(
            "OPENAI_API_KEY"
        )
        if not api_key:
            raise ValueError(
                "Set AUTOHARNESS_OPENAI_API_KEY or OPENAI_API_KEY before using "
                "`openai_responses`."
            )

        model = str(
            request.metadata.get("model")
            or os.environ.get("AUTOHARNESS_OPENAI_MODEL", "gpt-5.2")
        )
        reasoning_effort = str(
            request.metadata.get("reasoning_effort")
            or os.environ.get("AUTOHARNESS_OPENAI_REASONING_EFFORT", "low")
        )
        timeout_seconds = int(
            request.metadata.get("timeout_seconds")
            or os.environ.get("AUTOHARNESS_OPENAI_TIMEOUT_SECONDS", "60")
        )
        proposal_scope = _resolve_proposal_scope(request.metadata)
        max_operations = _resolve_positive_int_setting(
            request.metadata,
            key="max_operations",
            env_key="AUTOHARNESS_OPENAI_MAX_OPERATIONS",
            default=_DEFAULT_MAX_OPERATIONS_BY_SCOPE[proposal_scope],
        )
        max_repair_attempts = _resolve_nonnegative_int_setting(
            request.metadata,
            key="max_repair_attempts",
            env_key="AUTOHARNESS_OPENAI_MAX_REPAIR_ATTEMPTS",
            default=1,
        )
        prompt_payload = _build_prompt_payload(
            context=context,
            request=request,
            proposal_scope=proposal_scope,
            max_operations=max_operations,
        )
        request_payload = _build_openai_request_payload(
            model=model,
            reasoning_effort=reasoning_effort,
            prompt_payload=prompt_payload,
            instructions=_proposal_instructions(
                proposal_scope=proposal_scope,
                max_operations=max_operations,
            ),
        )
        base_url = str(
            request.metadata.get("base_url")
            or os.environ.get(
                "AUTOHARNESS_OPENAI_BASE_URL",
                "https://api.openai.com/v1/responses",
            )
        )
        response_attempts: list[dict[str, Any]] = []
        proposal_payload: dict[str, Any] | None = None
        final_response_payload: dict[str, Any] | None = None
        final_response_text = ""
        final_response_repair_steps: list[str] = []
        parse_error_message: str | None = None

        for attempt_index in range(max_repair_attempts + 1):
            phase = "initial" if attempt_index == 0 else "repair"
            if attempt_index == 0:
                current_prompt_payload = prompt_payload
                current_request_payload = request_payload
            else:
                current_prompt_payload = _build_repair_prompt_payload(
                    original_prompt_payload=prompt_payload,
                    request=request,
                    invalid_response_text=final_response_text,
                    parse_error=parse_error_message,
                )
                current_request_payload = _build_openai_request_payload(
                    model=model,
                    reasoning_effort=reasoning_effort,
                    prompt_payload=current_prompt_payload,
                    instructions=_repair_instructions(
                        proposal_scope=proposal_scope,
                        max_operations=max_operations,
                    ),
                )
            response_payload = _call_openai_responses_api(
                api_key=api_key,
                timeout_seconds=timeout_seconds,
                request_payload=current_request_payload,
                base_url=base_url,
            )
            response_text = _extract_response_text(response_payload)
            final_response_payload = response_payload
            final_response_text = response_text
            attempt_entry: dict[str, Any] = {
                "attempt_index": attempt_index,
                "phase": phase,
                "request_payload": current_request_payload,
                "response_id": response_payload.get("id"),
                "response_payload": response_payload,
                "response_text": response_text,
            }
            try:
                proposal_payload, final_response_repair_steps = _parse_proposal_response(
                    response_text=response_text,
                    request=request,
                )
            except (ProposalGenerationProviderError, ProposalGenerationProviderAuthError):
                raise
            except (ProposalGenerationError, ValueError) as exc:
                parse_error_message = str(exc)
                attempt_entry["status"] = "invalid"
                attempt_entry["parse_error"] = parse_error_message
                response_attempts.append(attempt_entry)
                if attempt_index >= max_repair_attempts:
                    raise ProposalGenerationProviderError(
                        "OpenAI generator response did not contain a valid edit plan."
                    ) from exc
                continue
            except Exception as exc:
                parse_error_message = str(exc)
                attempt_entry["status"] = "invalid"
                attempt_entry["parse_error"] = parse_error_message
                response_attempts.append(attempt_entry)
                if attempt_index >= max_repair_attempts:
                    raise ProposalGenerationProviderError(str(exc)) from exc
                continue
            attempt_entry["status"] = "success"
            attempt_entry["repair_steps"] = list(final_response_repair_steps)
            response_attempts.append(attempt_entry)
            break

        if proposal_payload is None or final_response_payload is None:
            raise ProposalGenerationProviderError(
                "OpenAI generator response did not contain a valid edit plan."
            )

        edit_plan = normalized_edit_plan_from_payload(proposal_payload)
        intervention_class = request.intervention_class or str(
            proposal_payload.get("intervention_class", "source")
        )
        hypothesis = (
            str(proposal_payload["hypothesis"])
            if proposal_payload.get("hypothesis") is not None
            else None
        )
        return GeneratedProposal(
            generator_id=self.generator_id,
            edit_plan=EditPlan(
                format_version=edit_plan.format_version,
                summary=str(proposal_payload.get("summary", edit_plan.summary)),
                operations=edit_plan.operations,
            ),
            summary=str(proposal_payload.get("summary", edit_plan.summary)),
            hypothesis=hypothesis,
            intervention_class=intervention_class,
            metadata={
                "generation_request": request.to_dict(),
                "provider": "openai",
                "model": model,
                "reasoning_effort": reasoning_effort,
                "response_id": final_response_payload.get("id"),
                "provider_request_payload": request_payload,
                "provider_response_payload": final_response_payload,
                "provider_response_text": final_response_text,
                "provider_attempts": response_attempts,
                "proposal_scope": proposal_scope,
                "max_operations": max_operations,
                "max_repair_attempts": max_repair_attempts,
                "repair_attempt_count": max(0, len(response_attempts) - 1),
                "repair_steps": list(final_response_repair_steps),
                "usage": _extract_usage_summary(final_response_payload),
            },
        )


def _resolve_proposal_scope(metadata: dict[str, Any]) -> str:
    raw_value = metadata.get("proposal_scope")
    if raw_value is None:
        raw_value = os.environ.get("AUTOHARNESS_OPENAI_PROPOSAL_SCOPE", "balanced")
    proposal_scope = str(raw_value).strip().lower()
    if proposal_scope not in _PROPOSAL_SCOPE_VALUES:
        raise ValueError(
            "`openai_responses.proposal_scope` must be one of: "
            + ", ".join(_PROPOSAL_SCOPE_VALUES)
            + "."
        )
    return proposal_scope


def _resolve_positive_int_setting(
    metadata: dict[str, Any],
    *,
    key: str,
    env_key: str,
    default: int,
) -> int:
    raw_value = metadata.get(key)
    if raw_value is None:
        raw_value = os.environ.get(env_key)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"`openai_responses.{key}` must be a positive integer."
        ) from exc
    if value < 1:
        raise ValueError(
            f"`openai_responses.{key}` must be a positive integer."
        )
    return value


def _resolve_nonnegative_int_setting(
    metadata: dict[str, Any],
    *,
    key: str,
    env_key: str,
    default: int,
) -> int:
    raw_value = metadata.get(key)
    if raw_value is None:
        raw_value = os.environ.get(env_key)
    if raw_value is None or raw_value == "":
        return default
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"`openai_responses.{key}` must be a non-negative integer."
        ) from exc
    if value < 0:
        raise ValueError(
            f"`openai_responses.{key}` must be a non-negative integer."
        )
    return value


def _call_openai_responses_api(
    *,
    api_key: str,
    timeout_seconds: int,
    request_payload: dict[str, Any],
    base_url: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        base_url,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise ProposalGenerationTimeoutError(
            f"OpenAI Responses API request timed out after {timeout_seconds}s."
        ) from exc
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            raise ProposalGenerationProviderAuthError(
                f"OpenAI Responses API authentication failed with {exc.code}: {error_body}"
            ) from exc
        if exc.code == 429:
            raise ProposalGenerationProviderRateLimitError(
                f"OpenAI Responses API rate-limited the request with {exc.code}: {error_body}"
            ) from exc
        if exc.code in {408, 500, 502, 503, 504}:
            raise ProposalGenerationProviderTransportError(
                f"OpenAI Responses API transport failure with {exc.code}: {error_body}"
            ) from exc
        raise ProposalGenerationProviderError(
            f"OpenAI Responses API request failed with {exc.code}: {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise ProposalGenerationTimeoutError(
                f"OpenAI Responses API request timed out after {timeout_seconds}s."
            ) from exc
        raise ProposalGenerationProviderTransportError(
            f"OpenAI Responses API request failed: {exc.reason}"
        ) from exc
    if not isinstance(payload, dict):
        raise ProposalGenerationProviderError(
            "OpenAI Responses API returned a non-object payload."
        )
    return payload


def _extract_response_text(response_payload: dict[str, Any]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = response_payload.get("output")
    if isinstance(output, list):
        text_chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for entry in content:
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") == "output_text":
                    text_value = entry.get("text")
                    if isinstance(text_value, str):
                        text_chunks.append(text_value)
        joined = "".join(text_chunks).strip()
        if joined:
            return joined

    raise ProposalGenerationProviderError(
        "OpenAI Responses payload did not include model text output."
    )


def _extract_usage_summary(response_payload: dict[str, Any]) -> dict[str, Any]:
    usage = response_payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    summary: dict[str, Any] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int) and value >= 0:
            summary[key] = value
    return summary


def _build_openai_request_payload(
    *,
    model: str,
    reasoning_effort: str,
    prompt_payload: dict[str, Any],
    instructions: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "reasoning": {"effort": reasoning_effort},
        "instructions": instructions,
        "input": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(prompt_payload, indent=2),
                    }
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_object",
            }
        },
    }


def _build_prompt_payload(
    *,
    context: ProposalGenerationContext,
    request: ProposalGenerationRequest,
    proposal_scope: str,
    max_operations: int,
) -> dict[str, Any]:
    intervention_class = request.intervention_class or "source"
    target_root = Path(context.target_root)
    return {
        "task": _proposal_task(proposal_scope),
        "request": request.to_dict(),
        "context": context.to_dict(),
        "proposal_profile": {
            "scope": proposal_scope,
            "max_operations": max_operations,
            "single_hypothesis": True,
            "allow_multi_file": proposal_scope != "conservative",
            "prefer_supporting_edits": True,
        },
        "benchmark_context": {
            "benchmark_target": context.benchmark_target,
            "selected_preset": context.selected_preset,
            "policy_preset": context.policy_preset,
            "latest_failure_summary": context.latest_failure_summary,
            "latest_regression_summary": context.latest_regression_summary,
        },
        "intervention_guidance": _intervention_guidance(intervention_class),
        "repo_snapshot": _collect_repo_snapshot(
            target_root=target_root,
            intervention_class=intervention_class,
            proposal_scope=proposal_scope,
        ),
    }


def _proposal_task(proposal_scope: str) -> str:
    if proposal_scope == "conservative":
        return "Generate one conservative autoharness edit plan."
    if proposal_scope == "broad":
        return (
            "Generate one broad but coherent autoharness edit plan that may span "
            "multiple supporting files."
        )
    return (
        "Generate one coherent autoharness edit plan that may include supporting "
        "multi-file changes."
    )


def _proposal_instructions(*, proposal_scope: str, max_operations: int) -> str:
    shared = (
        "You generate one AUTOHARNESS proposal as JSON. "
        "Return only JSON. "
        "The JSON must contain: hypothesis, summary, intervention_class, operations. "
        "Use only supported operation types: write_file, search_replace, delete_file, move_path, and unified_diff. "
        "Paths must stay relative to the target root. "
        "Every operation must support one coherent hypothesis rather than unrelated cleanup. "
        "Do not invent files outside the target root. "
        "When modifying an existing file, prefer search_replace with a precise search string. "
        "When creating a new file, use write_file. Use unified_diff when a hunk-style patch is clearer than search_replace. "
        "If you cannot express the patch as operations, you may return a files mapping "
        "from relative path to file content and autoharness will repair it. "
        "The summary should be short and specific."
    )
    if proposal_scope == "conservative":
        return (
            shared
            + " Prefer the smallest safe change set, typically one or two operations. "
            + f"Do not exceed {max_operations} operations."
        )
    if proposal_scope == "broad":
        return (
            shared
            + " Multi-file proposals are encouraged when they materially improve the harness. "
            + "If the root cause spans code, config, prompts, middleware, or tests, include "
            + "the supporting edits needed to keep the proposal internally consistent. "
            + f"You may use up to {max_operations} operations, but avoid scattershot edits."
        )
    return (
        shared
        + " Multi-file proposals are allowed when they materially improve the harness. "
        + "Include supporting config, prompt, middleware, or test updates when they are part "
        + "of the same hypothesis. "
        + f"You may use up to {max_operations} operations."
    )


def _repair_instructions(*, proposal_scope: str, max_operations: int) -> str:
    return (
        "You are repairing a previously invalid AUTOHARNESS proposal response. "
        "Return only valid JSON. "
        "The JSON must contain: hypothesis, summary, intervention_class, operations. "
        "Use only supported operation types: write_file, search_replace, delete_file, move_path, and unified_diff. "
        "Paths must stay relative to the target root. "
        "Preserve the original proposal intent where possible, but fix invalid structure, "
        "missing required fields, and malformed operations. "
        "If you cannot express the patch as operations, you may return a files mapping "
        "from relative path to file content and autoharness will repair it. "
        + _proposal_task(proposal_scope)
        + f" Do not exceed {max_operations} operations."
    )


def _parse_proposal_response(
    *,
    response_text: str,
    request: ProposalGenerationRequest,
) -> tuple[dict[str, Any], list[str]]:
    proposal_payload, response_repair_steps = decode_json_object_text(response_text)
    proposal_payload, payload_repair_steps = normalize_generated_payload(
        payload=proposal_payload,
        request=request,
    )
    return proposal_payload, response_repair_steps + payload_repair_steps


def _build_repair_prompt_payload(
    *,
    original_prompt_payload: dict[str, Any],
    request: ProposalGenerationRequest,
    invalid_response_text: str,
    parse_error: str | None,
) -> dict[str, Any]:
    return {
        "task": "Repair an invalid autoharness proposal response into valid proposal JSON.",
        "request": request.to_dict(),
        "original_prompt_payload": original_prompt_payload,
        "invalid_response_text": invalid_response_text,
        "parse_error": parse_error,
        "repair_requirements": {
            "required_keys": [
                "hypothesis",
                "summary",
                "intervention_class",
                "operations",
            ],
            "supported_operation_types": [
                "write_file",
                "search_replace",
                "delete_file",
                "move_path",
                "unified_diff",
            ],
        },
    }


def _collect_repo_snapshot(
    *,
    target_root: Path,
    intervention_class: str,
    proposal_scope: str,
) -> dict[str, Any]:
    files: list[Path] = []
    inventory_limit = _SNAPSHOT_FILE_LIMIT_BY_SCOPE[proposal_scope]
    file_sample_limit = _SNAPSHOT_FILE_SAMPLE_LIMIT_BY_SCOPE[proposal_scope]
    file_char_limit = _SNAPSHOT_FILE_CHAR_LIMIT_BY_SCOPE[proposal_scope]
    inventory_truncated = False
    if target_root.exists():
        for path in sorted(target_root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in _IGNORED_DIRS for part in path.parts):
                continue
            files.append(path)
            if len(files) >= inventory_limit:
                inventory_truncated = True
                break

    priority_suffixes = _PRIORITY_SUFFIXES.get(intervention_class, ())
    prioritized = sorted(
        files,
        key=lambda path: (
            0 if path.suffix.lower() in priority_suffixes else 1,
            len(path.relative_to(target_root).parts),
            str(path.relative_to(target_root)),
        ),
    )
    sampled_files = prioritized[:file_sample_limit]
    rendered_files = []
    language_counts: dict[str, int] = {}
    for path in sampled_files:
        rel_path = str(path.relative_to(target_root))
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        suffix = path.suffix.lower()
        if suffix:
            language_counts[suffix] = language_counts.get(suffix, 0) + 1
        rendered_files.append(
            {
                "path": rel_path,
                "content": text[:file_char_limit],
            }
        )

    return {
        "target_root": str(target_root),
        "file_count": len(files),
        "inventory_truncated": inventory_truncated,
        "prioritized_paths": [
            str(path.relative_to(target_root))
            for path in prioritized[:_SNAPSHOT_PATH_LIST_LIMIT]
        ],
        "language_hints": sorted(
            language_counts,
            key=lambda suffix: (-language_counts[suffix], suffix),
        ),
        "sampled_files": rendered_files,
    }


def _intervention_guidance(intervention_class: str) -> dict[str, Any]:
    guidance = {
        "prompt": {
            "focus": (
                "Prefer prompt text, templates, or prompt-routing changes, with only the "
                "supporting config or test edits needed to keep the proposal coherent."
            ),
            "preferred_suffixes": [".md", ".txt", ".yaml", ".yml"],
        },
        "config": {
            "focus": (
                "Prefer config or flag changes before code changes, but include small "
                "supporting source, prompt, or test edits when a config-only proposal "
                "would be inconsistent."
            ),
            "preferred_suffixes": [".json", ".yaml", ".yml", ".toml", ".ini"],
        },
        "middleware": {
            "focus": (
                "Prefer routing, orchestration, or glue-layer changes, including the "
                "supporting source or config edits needed for one coherent change set."
            ),
            "preferred_suffixes": [".py", ".ts", ".js", ".json"],
        },
        "source": {
            "focus": (
                "Prefer one coherent source change set that addresses the failure slice, "
                "including supporting tests, prompts, or config updates when they are part "
                "of the same hypothesis."
            ),
            "preferred_suffixes": [".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"],
        },
    }
    return guidance.get(intervention_class, guidance["source"])
