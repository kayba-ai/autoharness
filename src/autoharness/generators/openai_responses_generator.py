"""OpenAI Responses-backed proposal generator."""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..editing import EditPlan, edit_plan_from_dict
from ..proposal_context import ProposalGenerationContext
from .base import (
    GeneratedProposal,
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
        prompt_payload = _build_prompt_payload(context=context, request=request)
        request_payload = _build_openai_request_payload(
            model=model,
            reasoning_effort=reasoning_effort,
            prompt_payload=prompt_payload,
        )
        response_payload = _call_openai_responses_api(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            request_payload=request_payload,
            base_url=str(
                request.metadata.get("base_url")
                or os.environ.get(
                    "AUTOHARNESS_OPENAI_BASE_URL",
                    "https://api.openai.com/v1/responses",
                )
            ),
        )
        response_text = _extract_response_text(response_payload)
        try:
            proposal_payload, response_repair_steps = decode_json_object_text(response_text)
            proposal_payload, payload_repair_steps = normalize_generated_payload(
                payload=proposal_payload,
                request=request,
            )
        except (ProposalGenerationProviderError, ProposalGenerationProviderAuthError):
            raise
        except ValueError as exc:
            raise ProposalGenerationProviderError(
                "OpenAI generator response did not contain a valid edit plan."
            ) from exc
        except Exception as exc:
            raise ProposalGenerationProviderError(
                str(exc),
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
                "response_id": response_payload.get("id"),
                "provider_request_payload": request_payload,
                "provider_response_payload": response_payload,
                "provider_response_text": response_text,
                "repair_steps": response_repair_steps + payload_repair_steps,
                "usage": _extract_usage_summary(response_payload),
            },
        )


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
) -> dict[str, Any]:
    return {
        "model": model,
        "reasoning": {"effort": reasoning_effort},
        "instructions": _proposal_instructions(),
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
) -> dict[str, Any]:
    intervention_class = request.intervention_class or "source"
    target_root = Path(context.target_root)
    return {
        "task": "Generate one conservative autoharness edit plan.",
        "request": request.to_dict(),
        "context": context.to_dict(),
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
        ),
    }


def _proposal_instructions() -> str:
    return (
        "You generate one AUTOHARNESS proposal as JSON. "
        "Return only JSON. "
        "The JSON must contain: hypothesis, summary, intervention_class, operations. "
        "Use only supported operation types: write_file and search_replace. "
        "Paths must stay relative to the target root. "
        "Prefer one or two tightly scoped operations. "
        "Do not invent files outside the target root. "
        "When modifying an existing file, prefer search_replace with a precise search string. "
        "When creating a new file, use write_file. "
        "If you cannot express the patch as operations, you may return a files mapping "
        "from relative path to file content and autoharness will repair it. "
        "The summary should be short and specific."
    )


def _collect_repo_snapshot(
    *,
    target_root: Path,
    intervention_class: str,
) -> dict[str, Any]:
    files: list[Path] = []
    if target_root.exists():
        for path in sorted(target_root.rglob("*")):
            if not path.is_file():
                continue
            if any(part in _IGNORED_DIRS for part in path.parts):
                continue
            files.append(path)
            if len(files) >= 40:
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
    sampled_files = prioritized[:6]
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
                "content": text[:4000],
            }
        )

    return {
        "target_root": str(target_root),
        "file_count": len(files),
        "language_hints": sorted(
            language_counts,
            key=lambda suffix: (-language_counts[suffix], suffix),
        ),
        "sampled_files": rendered_files,
    }


def _intervention_guidance(intervention_class: str) -> dict[str, Any]:
    guidance = {
        "prompt": {
            "focus": "Prefer prompt text, templates, or prompt-routing changes.",
            "preferred_suffixes": [".md", ".txt", ".yaml", ".yml"],
        },
        "config": {
            "focus": "Prefer config or flag changes before code changes.",
            "preferred_suffixes": [".json", ".yaml", ".yml", ".toml", ".ini"],
        },
        "middleware": {
            "focus": "Prefer routing, orchestration, or glue-layer changes.",
            "preferred_suffixes": [".py", ".ts", ".js", ".json"],
        },
        "source": {
            "focus": "Prefer the smallest source change that addresses the failure slice.",
            "preferred_suffixes": [".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"],
        },
    }
    return guidance.get(intervention_class, guidance["source"])
