"""Proposal generator registry."""

import copy

from ..plugins import plugin_generators
from .base import (
    GeneratedProposal,
    ProposalGenerationError,
    ProposalGenerationProcessError,
    ProposalGenerationProviderAuthError,
    ProposalGenerationProviderError,
    ProposalGenerationProviderRateLimitError,
    ProposalGenerationProviderTransportError,
    ProposalGenerationRequest,
    ProposalGenerationTimeoutError,
    ProposalGenerator,
)
from .failure_driven_generator import FailureDrivenWriteFileGenerator
from .local_command_generator import LocalCommandProposalGenerator
from .manual_generator import ManualEditPlanGenerator
from .openai_responses_generator import OpenAIResponsesProposalGenerator
from .template_generator import LocalTemplateProposalGenerator


_GENERATORS = {
    "failure_summary": FailureDrivenWriteFileGenerator(),
    "local_command": LocalCommandProposalGenerator(),
    "local_template": LocalTemplateProposalGenerator(),
    "manual": ManualEditPlanGenerator(),
    "openai_responses": OpenAIResponsesProposalGenerator(),
}

_GENERATOR_CATALOG = {
    "failure_summary": {
        "label": "Failure Summary",
        "kind": "deterministic",
        "description": (
            "Synthesizes one deterministic edit plan from the latest failure, "
            "regression, and artifact context."
        ),
        "requires_edit_plan_input": False,
        "can_generate_without_edit_plan": True,
        "accepts_intervention_class": True,
        "generator_option_keys": ["fallback_generators"],
        "environment_variables": [],
        "notes": (
            "Best suited for lightweight autonomous search without external providers."
        ),
    },
    "local_command": {
        "label": "Local Command",
        "kind": "local_process",
        "description": (
            "Invokes one local executable that receives proposal-generation JSON on stdin "
            "and returns one proposal JSON object on stdout."
        ),
        "requires_edit_plan_input": False,
        "can_generate_without_edit_plan": True,
        "accepts_intervention_class": True,
        "generator_option_keys": [
            "command_path",
            "timeout_seconds",
            "command_cwd",
            "fallback_generators",
        ],
        "environment_variables": [],
        "notes": "Requires --generator-option command_path=/path/to/script.",
    },
    "local_template": {
        "label": "Local Template",
        "kind": "local_template",
        "description": (
            "Renders one local structured template into a concrete edit plan using the "
            "current proposal context."
        ),
        "requires_edit_plan_input": False,
        "can_generate_without_edit_plan": True,
        "accepts_intervention_class": True,
        "generator_option_keys": ["template_path", "fallback_generators"],
        "environment_variables": [],
        "notes": "Accepts --edit-plan as the template path when template_path is not set.",
    },
    "manual": {
        "label": "Manual Edit Plan",
        "kind": "manual",
        "description": "Treats one operator-supplied edit plan as the generated proposal.",
        "requires_edit_plan_input": True,
        "can_generate_without_edit_plan": False,
        "accepts_intervention_class": True,
        "generator_option_keys": ["fallback_generators"],
        "environment_variables": [],
        "notes": "Requires --edit-plan.",
    },
    "openai_responses": {
        "label": "OpenAI Responses",
        "kind": "api",
        "description": (
            "Calls the OpenAI Responses API with repository and failure context to "
            "synthesize one proposal edit plan."
        ),
        "requires_edit_plan_input": False,
        "can_generate_without_edit_plan": True,
        "accepts_intervention_class": True,
        "generator_option_keys": [
            "model",
            "reasoning_effort",
            "timeout_seconds",
            "base_url",
            "proposal_scope",
            "max_operations",
            "fallback_generators",
        ],
        "environment_variables": [
            "AUTOHARNESS_OPENAI_API_KEY",
            "OPENAI_API_KEY",
            "AUTOHARNESS_OPENAI_MODEL",
            "AUTOHARNESS_OPENAI_REASONING_EFFORT",
            "AUTOHARNESS_OPENAI_TIMEOUT_SECONDS",
            "AUTOHARNESS_OPENAI_BASE_URL",
            "AUTOHARNESS_OPENAI_PROPOSAL_SCOPE",
            "AUTOHARNESS_OPENAI_MAX_OPERATIONS",
        ],
        "notes": (
            "Requires an OpenAI API key via environment variable. Defaults to a balanced "
            "multi-file proposal profile; tune with proposal_scope and max_operations."
        ),
    },
}


def _generator_registry() -> dict[str, ProposalGenerator]:
    registry = dict(_GENERATORS)
    for generator_id, entry in plugin_generators().items():
        generator = entry.get("generator")
        if (
            isinstance(generator_id, str)
            and generator is not None
            and hasattr(generator, "generate")
        ):
            registry[generator_id] = generator
    return registry


def _generator_catalog_registry() -> dict[str, dict[str, object]]:
    catalog = {generator_id: copy.deepcopy(entry) for generator_id, entry in _GENERATOR_CATALOG.items()}
    for generator_id, entry in plugin_generators().items():
        catalog_entry = entry.get("catalog")
        if isinstance(generator_id, str) and isinstance(catalog_entry, dict):
            catalog[generator_id] = copy.deepcopy(catalog_entry)
    return catalog


def get_generator(generator_id: str) -> ProposalGenerator:
    try:
        return _generator_registry()[generator_id]
    except KeyError as exc:
        known = ", ".join(sorted(_generator_registry()))
        raise KeyError(
            f"Unknown proposal generator `{generator_id}`. Known generators: {known}"
        ) from exc


def list_generators() -> tuple[str, ...]:
    return tuple(sorted(_generator_registry()))


def generator_catalog_entry(generator_id: str) -> dict[str, object]:
    try:
        metadata = copy.deepcopy(_generator_catalog_registry()[generator_id])
    except KeyError as exc:
        known = ", ".join(sorted(_generator_registry()))
        raise KeyError(
            f"Unknown proposal generator `{generator_id}`. Known generators: {known}"
        ) from exc
    return {
        "generator_id": generator_id,
        **metadata,
    }


def generator_catalog() -> tuple[dict[str, object], ...]:
    return tuple(generator_catalog_entry(generator_id) for generator_id in list_generators())


__all__ = [
    "GeneratedProposal",
    "ProposalGenerationError",
    "ProposalGenerationProcessError",
    "ProposalGenerationProviderAuthError",
    "ProposalGenerationProviderError",
    "ProposalGenerationProviderRateLimitError",
    "ProposalGenerationProviderTransportError",
    "ProposalGenerationRequest",
    "ProposalGenerationTimeoutError",
    "ProposalGenerator",
    "generator_catalog",
    "generator_catalog_entry",
    "get_generator",
    "list_generators",
]
