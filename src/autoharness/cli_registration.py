"""Top-level CLI command registration orchestration."""

from __future__ import annotations

from .cli_registration_benchmarks import register_benchmark_parsers
from .cli_registration_campaigns import register_campaign_parsers
from .cli_registration_execution import register_execution_parsers
from .cli_registration_inspection import register_inspection_parsers
from .cli_registration_listings import register_listing_parsers
from .cli_registration_promotion import register_promotion_parsers
from .cli_registration_proposals import register_proposal_parsers
from .cli_registration_workspace import register_workspace_parsers


def register_command_parsers(
    subparsers,
    *,
    run_planned_iteration_handler,
) -> None:
    register_workspace_parsers(subparsers)
    register_benchmark_parsers(subparsers)
    register_execution_parsers(
        subparsers,
        run_planned_iteration_handler=run_planned_iteration_handler,
    )
    register_campaign_parsers(subparsers)
    register_proposal_parsers(subparsers)
    register_listing_parsers(subparsers)
    register_inspection_parsers(subparsers)
    register_promotion_parsers(subparsers)
