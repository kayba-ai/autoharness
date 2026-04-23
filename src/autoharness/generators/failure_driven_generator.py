"""Deterministic failure-driven proposal generator."""

from __future__ import annotations

import json
from pathlib import Path

from ..editing import EditOperation, EditPlan
from ..proposal_context import ProposalGenerationContext
from .base import GeneratedProposal, ProposalGenerationRequest


_INTERVENTION_EXTENSIONS = {
    "config": ".json",
    "middleware": ".txt",
    "prompt": ".md",
    "source": ".py",
}


class FailureDrivenWriteFileGenerator:
    """Synthesize one context-rich edit plan from the latest failure state."""

    generator_id = "failure_summary"

    def generate(
        self,
        *,
        context: ProposalGenerationContext,
        request: ProposalGenerationRequest,
        edit_plan_path: Path | None = None,
    ) -> GeneratedProposal:
        del edit_plan_path
        intervention_class = request.intervention_class or "source"
        extension = _INTERVENTION_EXTENSIONS.get(intervention_class, ".txt")
        rel_path = (
            ".autoharness/generated/"
            f"{intervention_class}_candidate_{request.candidate_index:03d}{extension}"
        )
        failure_task_ids = list(request.failure_focus_task_ids)
        if not failure_task_ids and isinstance(context.latest_failure_summary, dict):
            task_keys = context.latest_failure_summary.get("task_keys")
            if isinstance(task_keys, list):
                failure_task_ids = [str(item) for item in task_keys if isinstance(item, str)]
        regressed_task_ids = list(request.regressed_task_ids)
        if not regressed_task_ids and isinstance(context.latest_regression_summary, dict):
            task_keys = context.latest_regression_summary.get("task_keys")
            if isinstance(task_keys, list):
                regressed_task_ids = [str(item) for item in task_keys if isinstance(item, str)]

        content_payload = {
            "workspace_id": context.workspace_id,
            "track_id": context.track_id,
            "strategy_id": request.strategy_id,
            "candidate_index": request.candidate_index,
            "intervention_class": intervention_class,
            "objective": context.objective,
            "stage": context.stage,
            "adapter_id": context.adapter_id,
            "benchmark_target": context.benchmark_target,
            "selected_preset": context.selected_preset,
            "latest_record_status": context.latest_record_status,
            "failure_focus_task_ids": failure_task_ids,
            "regressed_task_ids": regressed_task_ids,
            "latest_failure_summary": context.latest_failure_summary,
            "latest_regression_summary": context.latest_regression_summary,
            "latest_parsed_artifact_sources": context.latest_parsed_artifact_sources,
        }
        hypothesis_bits = [f"{intervention_class} candidate"]
        if failure_task_ids:
            hypothesis_bits.append(f"for {', '.join(failure_task_ids[:3])}")
        elif regressed_task_ids:
            hypothesis_bits.append(f"for regressions {', '.join(regressed_task_ids[:3])}")
        hypothesis = " ".join(hypothesis_bits)

        edit_plan = EditPlan(
            format_version="autoharness.edit_plan.v1",
            summary=f"Generate {intervention_class} candidate context artifact",
            operations=(
                EditOperation(
                    type="write_file",
                    path=rel_path,
                    content=json.dumps(content_payload, indent=2) + "\n",
                    create_if_missing=True,
                ),
            ),
        )
        return GeneratedProposal(
            generator_id=self.generator_id,
            edit_plan=edit_plan,
            summary=edit_plan.summary,
            hypothesis=hypothesis,
            intervention_class=intervention_class,
            metadata={
                "generation_request": request.to_dict(),
                "failure_focus_task_ids": failure_task_ids,
                "regressed_task_ids": regressed_task_ids,
                "generated_path": rel_path,
            },
        )
