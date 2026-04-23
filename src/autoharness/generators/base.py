"""Base types for proposal generators."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..editing import EditPlan, edit_plan_from_dict
from ..proposal_context import ProposalGenerationContext


class ProposalGenerationError(ValueError):
    """Base exception for generator failures."""


class ProposalGenerationTimeoutError(ProposalGenerationError):
    """Generator-side timeout failure."""


class ProposalGenerationProviderError(ProposalGenerationError):
    """Provider or remote-service failure during generation."""


class ProposalGenerationProviderTransportError(ProposalGenerationProviderError):
    """Transport or transient availability failure from a generation provider."""


class ProposalGenerationProviderAuthError(ProposalGenerationProviderError):
    """Authentication or authorization failure from a generation provider."""


class ProposalGenerationProviderRateLimitError(ProposalGenerationProviderError):
    """Rate-limit or quota failure from a generation provider."""


class ProposalGenerationProcessError(ProposalGenerationError):
    """Local generator-process execution failure."""


@dataclass(frozen=True)
class ProposalGenerationRequest:
    """One strategy-produced generation request."""

    format_version: str
    candidate_index: int
    strategy_id: str
    source_mode: str
    campaign_run_id: str | None = None
    intervention_class: str | None = None
    input_edit_plan_path: str | None = None
    failure_focus_task_ids: tuple[str, ...] = ()
    regressed_task_ids: tuple[str, ...] = ()
    hypothesis_seed: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "failure_focus_task_ids": list(self.failure_focus_task_ids),
            "regressed_task_ids": list(self.regressed_task_ids),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class GeneratedProposal:
    """One generator-produced proposal payload before persistence."""

    generator_id: str
    edit_plan: EditPlan
    summary: str
    hypothesis: str | None = None
    intervention_class: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "edit_plan": self.edit_plan.to_dict(),
            "metadata": dict(self.metadata),
        }


class ProposalGenerator(Protocol):
    """Protocol implemented by proposal generators."""

    generator_id: str

    def generate(
        self,
        *,
        context: ProposalGenerationContext,
        request: ProposalGenerationRequest,
        edit_plan_path: Path | None = None,
    ) -> GeneratedProposal:
        """Return one generated proposal payload."""


def decode_json_object_text(raw_text: str) -> tuple[dict[str, Any], list[str]]:
    repair_steps: list[str] = []
    candidates = list(_json_text_candidates(raw_text))
    for index, candidate in enumerate(candidates):
        try:
            decoded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(decoded, dict):
            continue
        if index > 0:
            repair_steps.append("recovered_json_object_from_response_text")
        return decoded, repair_steps
    raise ProposalGenerationError("Generator response was not valid JSON.")


def normalize_generated_payload(
    *,
    payload: dict[str, Any],
    request: ProposalGenerationRequest,
) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(payload)
    repair_steps: list[str] = []

    operations = normalized.get("operations")
    if not isinstance(operations, list):
        repaired_operations = _repair_operations_from_payload(normalized)
        if repaired_operations is not None:
            normalized["operations"] = repaired_operations
            repair_steps.append("repaired_operations_payload")

    summary_value = normalized.get("summary")
    if not isinstance(summary_value, str) or not summary_value.strip():
        normalized["summary"] = (
            str(normalized.get("hypothesis"))
            if isinstance(normalized.get("hypothesis"), str)
            and str(normalized.get("hypothesis")).strip()
            else (
                request.hypothesis_seed
                or f"Candidate {request.candidate_index} proposal"
            )
        )
        repair_steps.append("filled_missing_summary")

    intervention_class = normalized.get("intervention_class")
    if not isinstance(intervention_class, str) or not intervention_class.strip():
        normalized["intervention_class"] = request.intervention_class or "source"
        repair_steps.append("filled_missing_intervention_class")

    if normalized.get("hypothesis") is None and request.hypothesis_seed is not None:
        normalized["hypothesis"] = request.hypothesis_seed
        repair_steps.append("filled_missing_hypothesis")

    edit_plan = edit_plan_from_dict(
        {
            "format_version": "autoharness.edit_plan.v1",
            "summary": str(normalized.get("summary", "")),
            "operations": normalized.get("operations"),
        }
    )
    normalized["summary"] = str(normalized.get("summary", edit_plan.summary))
    normalized["_normalized_edit_plan"] = edit_plan
    return normalized, repair_steps


def normalized_edit_plan_from_payload(payload: dict[str, Any]) -> EditPlan:
    edit_plan = payload.get("_normalized_edit_plan")
    if isinstance(edit_plan, EditPlan):
        return edit_plan
    return edit_plan_from_dict(
        {
            "format_version": "autoharness.edit_plan.v1",
            "summary": str(payload.get("summary", "")),
            "operations": payload.get("operations"),
        }
    )


def _json_text_candidates(raw_text: str) -> tuple[str, ...]:
    stripped = raw_text.strip()
    if not stripped:
        return ()
    candidates: list[str] = [stripped]
    fenced_matches = re.findall(r"```(?:json)?\s*(.*?)```", stripped, flags=re.DOTALL)
    for match in fenced_matches:
        candidate = match.strip()
        if candidate:
            candidates.append(candidate)
    balanced = _extract_balanced_json_object(stripped)
    if balanced is not None:
        candidates.append(balanced)
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        deduped.append(candidate)
    return tuple(deduped)


def _extract_balanced_json_object(raw_text: str) -> str | None:
    start = raw_text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(raw_text)):
        char = raw_text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw_text[start : index + 1].strip()
    return None


def _repair_operations_from_payload(
    payload: dict[str, Any],
) -> list[dict[str, Any]] | None:
    files_payload = payload.get("files")
    if isinstance(files_payload, dict):
        repaired: list[dict[str, Any]] = []
        for path, content in files_payload.items():
            if not isinstance(path, str) or not path:
                continue
            if not isinstance(content, str):
                continue
            repaired.append(
                {
                    "type": "write_file",
                    "path": path,
                    "content": content,
                }
            )
        if repaired:
            return repaired

    edits_payload = payload.get("edits")
    if isinstance(edits_payload, list):
        repaired = [entry for entry in edits_payload if isinstance(entry, dict)]
        return repaired or None
    return None
