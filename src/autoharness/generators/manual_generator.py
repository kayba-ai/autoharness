"""Manual edit-plan proposal generator."""

from __future__ import annotations

from pathlib import Path

from ..cli_support import _load_structured_file
from ..editing import edit_plan_from_dict
from ..proposal_context import ProposalGenerationContext
from .base import GeneratedProposal, ProposalGenerationRequest


class ManualEditPlanGenerator:
    """Treat one operator-supplied edit plan as a generated proposal."""

    generator_id = "manual"

    def generate(
        self,
        *,
        context: ProposalGenerationContext,
        request: ProposalGenerationRequest,
        edit_plan_path: Path | None = None,
    ) -> GeneratedProposal:
        del context  # manual generation does not transform the plan yet
        if edit_plan_path is None:
            raise ValueError("The `manual` generator requires --edit-plan.")
        edit_plan = edit_plan_from_dict(_load_structured_file(edit_plan_path))
        return GeneratedProposal(
            generator_id=self.generator_id,
            edit_plan=edit_plan,
            summary=edit_plan.summary,
            hypothesis=request.hypothesis_seed,
            intervention_class=request.intervention_class,
            metadata={
                "edit_plan_path": str(edit_plan_path),
                "generation_request": request.to_dict(),
            },
        )
