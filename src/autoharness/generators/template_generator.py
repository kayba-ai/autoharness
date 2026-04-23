"""Local template-backed proposal generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cli_support import _load_structured_file
from ..editing import edit_plan_from_dict
from ..proposal_context import ProposalGenerationContext
from .base import GeneratedProposal, ProposalGenerationRequest


class _TemplateFormatMap(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return ""


class LocalTemplateProposalGenerator:
    """Render a local structured template into one concrete edit plan."""

    generator_id = "local_template"

    def generate(
        self,
        *,
        context: ProposalGenerationContext,
        request: ProposalGenerationRequest,
        edit_plan_path: Path | None = None,
    ) -> GeneratedProposal:
        template_path_value = request.metadata.get("template_path")
        template_path = (
            Path(str(template_path_value))
            if template_path_value is not None
            else edit_plan_path
        )
        if template_path is None:
            raise ValueError(
                "The `local_template` generator requires `template_path` metadata or --edit-plan."
            )

        raw_template = _load_structured_file(template_path)
        if not isinstance(raw_template, dict):
            raise ValueError("Template generator input must decode to a mapping.")

        template_vars = _build_template_vars(context=context, request=request)
        rendered_template = _render_template_value(raw_template, template_vars)
        if not isinstance(rendered_template, dict):
            raise ValueError("Rendered template payload must remain a mapping.")

        edit_plan = edit_plan_from_dict(
            {
                "format_version": "autoharness.edit_plan.v1",
                "summary": str(rendered_template.get("summary", "")),
                "operations": rendered_template.get("operations"),
            }
        )
        intervention_class = str(
            rendered_template.get(
                "intervention_class",
                request.intervention_class or "source",
            )
        )
        hypothesis = (
            str(rendered_template["hypothesis"])
            if rendered_template.get("hypothesis") is not None
            else request.hypothesis_seed
        )
        summary = str(rendered_template.get("summary", edit_plan.summary))
        return GeneratedProposal(
            generator_id=self.generator_id,
            edit_plan=edit_plan,
            summary=summary,
            hypothesis=hypothesis,
            intervention_class=intervention_class,
            metadata={
                "generation_request": request.to_dict(),
                "provider": "local_template",
                "template_path": str(template_path),
                "template_variables": template_vars,
            },
        )


def _build_template_vars(
    *,
    context: ProposalGenerationContext,
    request: ProposalGenerationRequest,
) -> dict[str, str]:
    intervention_class = request.intervention_class or "source"
    failure_focus_task_ids = list(request.failure_focus_task_ids)
    regressed_task_ids = list(request.regressed_task_ids)
    focus_task_ids = failure_focus_task_ids or regressed_task_ids
    focus_kind = "failure" if failure_focus_task_ids else "regression"
    return {
        "workspace_id": context.workspace_id,
        "track_id": context.track_id,
        "objective": context.objective,
        "stage": context.stage,
        "adapter_id": context.adapter_id,
        "benchmark_target": context.benchmark_target or "",
        "selected_preset": context.selected_preset or "",
        "selected_preset_source": context.selected_preset_source or "",
        "latest_record_status": context.latest_record_status or "",
        "candidate_index": str(request.candidate_index),
        "strategy_id": request.strategy_id,
        "source_mode": request.source_mode,
        "campaign_run_id": request.campaign_run_id or "",
        "intervention_class": intervention_class,
        "hypothesis_seed": request.hypothesis_seed or "",
        "failure_focus_task_ids_csv": ",".join(failure_focus_task_ids),
        "regressed_task_ids_csv": ",".join(regressed_task_ids),
        "focus_task_ids_csv": ",".join(focus_task_ids),
        "focus_kind": focus_kind if focus_task_ids else "",
        "focus_label": ", ".join(focus_task_ids),
        "target_root": str(context.target_root),
    }


def _render_template_value(value: Any, variables: dict[str, str]) -> Any:
    if isinstance(value, str):
        return value.format_map(_TemplateFormatMap(variables))
    if isinstance(value, list):
        return [_render_template_value(entry, variables) for entry in value]
    if isinstance(value, dict):
        return {
            str(key): _render_template_value(entry, variables)
            for key, entry in value.items()
        }
    return value
