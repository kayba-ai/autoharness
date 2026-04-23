"""Campaign command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from .campaign_handlers import (
    _handle_cancel_campaign,
    _handle_export_campaign_bundle,
    _handle_export_campaign_report,
    _handle_export_root_campaign_bundle,
    _handle_export_root_campaign_run_report,
    _handle_export_root_campaign_report,
    _handle_pause_campaign,
    _handle_export_workspace_campaign_bundle,
    _handle_export_workspace_campaign_run_report,
    _handle_export_workspace_campaign_report,
    _handle_resume_campaign,
    _handle_run_campaign,
    _handle_run_campaign_worker,
    _handle_run_root_campaigns,
    _handle_run_workspace_campaigns,
    _handle_show_campaign_report_file,
    _handle_show_campaign_artifacts,
    _handle_show_campaign,
    _handle_show_campaigns,
    _handle_show_root_campaigns,
    _handle_validate_campaign_report_file,
)
from .cli_arguments import (
    _add_config_composition_arguments,
    _add_force_argument,
    _add_json_output_arguments,
    _add_optional_format_argument,
    _add_optional_track_selection_argument,
    _add_required_adapter_argument,
    _add_required_output_argument,
    _add_workspace_id_argument,
    _add_workspace_root_argument,
)
from .preflight import available_preflight_checks
from .search import available_search_strategies


def _add_workspace_campaign_batch_arguments(parser) -> None:
    _add_workspace_id_argument(parser)
    _add_workspace_root_argument(parser)
    _add_required_adapter_argument(parser)
    _add_config_composition_arguments(
        parser,
        preset_help=(
            "Optional starter-config preset override. Defaults to each track/workspace "
            "policy preset for the selected stage when available."
        ),
    )
    parser.add_argument(
        "--track-id",
        action="append",
        default=[],
        help="Repeatable track id filter. Defaults to all active tracks.",
    )
    parser.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Evaluation stage policy override for every launched track campaign.",
    )
    parser.add_argument(
        "--generator",
        default=None,
        help="Proposal generator id override for every launched track campaign.",
    )
    parser.add_argument(
        "--strategy",
        choices=available_search_strategies(),
        default=None,
        help="Campaign search strategy override for every launched track campaign.",
    )
    parser.add_argument(
        "--beam-width",
        type=int,
        default=None,
        help="Beam width override for every launched track campaign.",
    )
    parser.add_argument(
        "--beam-groups",
        type=int,
        default=None,
        help="Number of beam groups to keep active at once for each launched track campaign. Default: 1.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="Repeated validation run override for each launched track campaign.",
    )
    parser.add_argument(
        "--stage-progression",
        choices=("fixed", "advance_on_success", "advance_on_promotion"),
        default=None,
        help="Campaign stage progression override for every launched track campaign.",
    )
    parser.add_argument(
        "--edit-plan",
        type=Path,
        action="append",
        default=[],
        help="Repeatable edit-plan input used for each launched track campaign.",
    )
    parser.add_argument(
        "--intervention-class",
        choices=("prompt", "config", "middleware", "source"),
        action="append",
        default=[],
        help="Repeatable intervention-class cycle override for launched track campaigns.",
    )
    parser.add_argument(
        "--preflight-check",
        choices=available_preflight_checks(),
        action="append",
        default=[],
        help="Repeatable built-in preflight check expanded before benchmark execution for each launched track campaign.",
    )
    parser.add_argument(
        "--preflight-command",
        action="append",
        default=[],
        help="Repeatable preflight command run from each launched track campaign target root before benchmark execution.",
    )
    parser.add_argument(
        "--preflight-timeout-seconds",
        type=int,
        default=None,
        help="Optional per-track preflight command timeout.",
    )
    parser.add_argument(
        "--generator-option",
        action="append",
        default=[],
        help="Repeatable key=value generator option passed through to each track campaign.",
    )
    parser.add_argument(
        "--target-root-base",
        type=Path,
        default=Path("."),
        help="Base directory under which each track campaign uses <base>/<track_id> as its target root.",
    )
    parser.add_argument(
        "--max-proposals",
        type=int,
        default=None,
        help="Optional per-track proposal budget before each campaign pauses.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Optional per-track iteration budget.",
    )
    parser.add_argument(
        "--max-successes",
        type=int,
        default=None,
        help="Optional per-track success budget.",
    )
    parser.add_argument(
        "--max-promotions",
        type=int,
        default=None,
        help="Optional per-track promotion budget.",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=None,
        help="Optional per-track failure budget.",
    )
    parser.add_argument(
        "--max-inconclusive",
        type=int,
        default=None,
        help="Optional per-track inconclusive budget.",
    )
    parser.add_argument(
        "--no-improvement-limit",
        type=int,
        default=None,
        help="Optional per-track no-improvement limit.",
    )
    parser.add_argument(
        "--time-budget-seconds",
        type=int,
        default=None,
        help="Optional per-track wall-clock budget in seconds.",
    )
    parser.add_argument(
        "--max-generation-total-tokens",
        type=int,
        default=None,
        help="Optional per-track cumulative generator-token budget.",
    )
    parser.add_argument(
        "--max-benchmark-total-cost",
        type=float,
        default=None,
        help="Optional per-track cumulative benchmark-cost budget.",
    )
    parser.add_argument(
        "--max-generation-retries",
        type=int,
        default=None,
        help="Optional per-track generation retry budget.",
    )
    parser.add_argument(
        "--max-generation-timeout-retries",
        type=int,
        default=None,
        help="Optional per-track generator-timeout retry budget.",
    )
    parser.add_argument(
        "--max-generation-provider-retries",
        type=int,
        default=None,
        help="Optional per-track generator provider/network retry budget.",
    )
    parser.add_argument(
        "--max-generation-provider-transport-retries",
        type=int,
        default=None,
        help="Optional per-track generator provider-transport retry budget.",
    )
    parser.add_argument(
        "--max-generation-provider-auth-retries",
        type=int,
        default=None,
        help="Optional per-track generator provider-auth retry budget.",
    )
    parser.add_argument(
        "--max-generation-provider-rate-limit-retries",
        type=int,
        default=None,
        help="Optional per-track generator provider rate-limit retry budget.",
    )
    parser.add_argument(
        "--max-generation-process-retries",
        type=int,
        default=None,
        help="Optional per-track local generator-process retry budget.",
    )
    parser.add_argument(
        "--max-preflight-retries",
        type=int,
        default=None,
        help="Optional per-track preflight retry budget.",
    )
    parser.add_argument(
        "--max-execution-retries",
        type=int,
        default=None,
        help="Optional per-track execution retry budget.",
    )
    parser.add_argument(
        "--max-benchmark-process-retries",
        type=int,
        default=None,
        help="Optional per-track benchmark process-start retry budget.",
    )
    parser.add_argument(
        "--max-benchmark-signal-retries",
        type=int,
        default=None,
        help="Optional per-track benchmark signal-termination retry budget.",
    )
    parser.add_argument(
        "--max-benchmark-parse-retries",
        type=int,
        default=None,
        help="Optional per-track benchmark parse retry budget.",
    )
    parser.add_argument(
        "--max-benchmark-adapter-validation-retries",
        type=int,
        default=None,
        help="Optional per-track benchmark adapter-validation retry budget.",
    )
    parser.add_argument(
        "--max-benchmark-timeout-retries",
        type=int,
        default=None,
        help="Optional per-track benchmark-timeout retry budget.",
    )
    parser.add_argument(
        "--max-benchmark-command-retries",
        type=int,
        default=None,
        help="Optional per-track benchmark-command retry budget.",
    )
    parser.add_argument(
        "--max-inconclusive-retries",
        type=int,
        default=None,
        help="Optional per-track inconclusive retry budget.",
    )
    parser.add_argument(
        "--auto-promote",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Auto-promotion override for each launched track campaign.",
    )
    parser.add_argument(
        "--allow-flaky-promotion",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Allow automatic promotion even when repeated validation is flaky.",
    )
    parser.add_argument(
        "--auto-promote-min-stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Minimum stage override for automatic campaign promotion.",
    )
    parser.add_argument(
        "--stop-on-first-promotion",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Stop-on-first-promotion override for each launched track campaign.",
    )
    parser.add_argument(
        "--promotion-target-root-base",
        type=Path,
        default=None,
        help="Optional base directory under which each track campaign uses <base>/<track_id> as its promotion root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run each launched track campaign as a dry run.",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Queue each launched track campaign for background workers instead of running it immediately.",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue launching later track campaigns even if one track campaign fails.",
    )


def _add_root_campaign_batch_arguments(parser) -> None:
    parser.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(parser)
    _add_required_adapter_argument(parser)
    _add_config_composition_arguments(
        parser,
        preset_help=(
            "Optional starter-config preset override. Defaults to each track/workspace "
            "policy preset for the selected stage when available."
        ),
    )
    parser.add_argument(
        "--track-id",
        action="append",
        default=[],
        help="Repeatable track id filter forwarded to each workspace campaign run.",
    )
    parser.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Evaluation stage policy override for every launched workspace campaign run.",
    )
    parser.add_argument(
        "--generator",
        default=None,
        help="Proposal generator id override for every launched workspace campaign run.",
    )
    parser.add_argument(
        "--strategy",
        choices=available_search_strategies(),
        default=None,
        help="Campaign search strategy override for every launched workspace campaign run.",
    )
    parser.add_argument(
        "--beam-width",
        type=int,
        default=None,
        help="Beam width override for every launched workspace campaign run.",
    )
    parser.add_argument(
        "--beam-groups",
        type=int,
        default=None,
        help="Number of beam groups to keep active at once for each launched workspace campaign run. Default: 1.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="Repeated validation run override for each launched workspace campaign run.",
    )
    parser.add_argument(
        "--stage-progression",
        choices=("fixed", "advance_on_success", "advance_on_promotion"),
        default=None,
        help="Campaign stage progression override for every launched workspace campaign run.",
    )
    parser.add_argument(
        "--edit-plan",
        type=Path,
        action="append",
        default=[],
        help="Repeatable edit-plan input used for each launched workspace campaign run.",
    )
    parser.add_argument(
        "--intervention-class",
        choices=("prompt", "config", "middleware", "source"),
        action="append",
        default=[],
        help="Repeatable intervention-class cycle override for launched workspace campaign runs.",
    )
    parser.add_argument(
        "--preflight-check",
        choices=available_preflight_checks(),
        action="append",
        default=[],
    )
    parser.add_argument("--preflight-command", action="append", default=[])
    parser.add_argument("--preflight-timeout-seconds", type=int, default=None)
    parser.add_argument(
        "--generator-option",
        action="append",
        default=[],
        help="Repeatable key=value generator option passed through to each workspace campaign run.",
    )
    parser.add_argument(
        "--target-root-base",
        type=Path,
        default=Path("."),
        help="Base directory under which each workspace campaign uses <base>/<workspace>/<track> targets.",
    )
    parser.add_argument("--max-proposals", type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=None)
    parser.add_argument("--max-successes", type=int, default=None)
    parser.add_argument("--max-promotions", type=int, default=None)
    parser.add_argument("--max-failures", type=int, default=None)
    parser.add_argument("--max-inconclusive", type=int, default=None)
    parser.add_argument("--no-improvement-limit", type=int, default=None)
    parser.add_argument(
        "--auto-promote",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--allow-flaky-promotion",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--auto-promote-min-stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
    )
    parser.add_argument(
        "--stop-on-first-promotion",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--promotion-target-root-base",
        type=Path,
        default=None,
        help="Optional base directory under which each workspace campaign uses <base>/<workspace>/<track> promotion roots.",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Queue each launched workspace campaign for background workers instead of running it immediately.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of local workers to use for root-level parallel execution. Default: 1.",
    )
    parser.add_argument(
        "--schedule",
        choices=("portfolio", "fifo"),
        default="portfolio",
        help="Root workspace scheduling mode. Default: portfolio.",
    )
    parser.add_argument(
        "--apply-root-transfers",
        action="store_true",
        help="Apply root-memory transfer suggestions after the batch run completes.",
    )
    parser.add_argument(
        "--root-transfer-target-base",
        type=Path,
        default=Path(".autoharness/root_transfers"),
        help="Base directory used when applying root-memory transfer suggestions.",
    )
    parser.add_argument(
        "--root-transfer-limit",
        type=int,
        default=None,
        help="Optional cap on how many root-memory transfer suggestions to apply.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--time-budget-seconds", type=int, default=None)
    parser.add_argument("--max-generation-total-tokens", type=int, default=None)
    parser.add_argument("--max-benchmark-total-cost", type=float, default=None)
    parser.add_argument("--max-generation-retries", type=int, default=None)
    parser.add_argument("--max-generation-timeout-retries", type=int, default=None)
    parser.add_argument("--max-generation-provider-retries", type=int, default=None)
    parser.add_argument(
        "--max-generation-provider-transport-retries", type=int, default=None
    )
    parser.add_argument(
        "--max-generation-provider-auth-retries", type=int, default=None
    )
    parser.add_argument(
        "--max-generation-provider-rate-limit-retries", type=int, default=None
    )
    parser.add_argument("--max-generation-process-retries", type=int, default=None)
    parser.add_argument("--max-preflight-retries", type=int, default=None)
    parser.add_argument("--max-execution-retries", type=int, default=None)
    parser.add_argument("--max-benchmark-process-retries", type=int, default=None)
    parser.add_argument("--max-benchmark-signal-retries", type=int, default=None)
    parser.add_argument("--max-benchmark-parse-retries", type=int, default=None)
    parser.add_argument(
        "--max-benchmark-adapter-validation-retries", type=int, default=None
    )
    parser.add_argument("--max-benchmark-timeout-retries", type=int, default=None)
    parser.add_argument("--max-benchmark-command-retries", type=int, default=None)
    parser.add_argument("--max-inconclusive-retries", type=int, default=None)
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue across failing tracks and failing workspaces instead of stopping at the first failure.",
    )


def register_campaign_parsers(subparsers) -> None:
    run_campaign = subparsers.add_parser(
        "run-campaign",
        help="Run a resumable campaign from manual edit plans or generator-driven candidates.",
    )
    _add_workspace_id_argument(run_campaign)
    _add_optional_track_selection_argument(run_campaign)
    _add_workspace_root_argument(run_campaign)
    _add_required_adapter_argument(run_campaign)
    _add_config_composition_arguments(
        run_campaign,
        preset_help=(
            "Optional starter-config preset override. Defaults to the track/workspace "
            "policy preset for the selected stage when available."
        ),
    )
    run_campaign.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Evaluation stage policy. Defaults to track/workspace campaign policy, then screening.",
    )
    run_campaign.add_argument(
        "--generator",
        default=None,
        help="Proposal generator id. Defaults to track/workspace campaign policy, then manual.",
    )
    run_campaign.add_argument(
        "--strategy",
        choices=available_search_strategies(),
        default=None,
        help="Campaign search strategy id. Defaults to track/workspace campaign policy.",
    )
    run_campaign.add_argument(
        "--beam-width",
        type=int,
        default=None,
        help="Beam width for beam-style generator campaigns. Defaults to track/workspace campaign policy.",
    )
    run_campaign.add_argument(
        "--beam-groups",
        type=int,
        default=None,
        help=(
            "Number of beam groups to keep active at once for beam-style generator "
            "campaigns. Defaults to track/workspace campaign policy, then 1."
        ),
    )
    run_campaign.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="Repeated validation run override. Defaults to track/workspace campaign policy.",
    )
    run_campaign.add_argument(
        "--stage-progression",
        choices=("fixed", "advance_on_success", "advance_on_promotion"),
        default=None,
        help="Campaign stage progression mode. Defaults to track/workspace campaign policy.",
    )
    run_campaign.add_argument(
        "--edit-plan",
        type=Path,
        action="append",
        default=[],
        help="Repeatable edit-plan input for one sequential campaign candidate.",
    )
    run_campaign.add_argument(
        "--intervention-class",
        choices=("prompt", "config", "middleware", "source"),
        action="append",
        default=[],
        help="Repeatable intervention-class cycle for generator-driven campaigns.",
    )
    run_campaign.add_argument(
        "--preflight-check",
        choices=available_preflight_checks(),
        action="append",
        default=[],
        help="Repeatable built-in preflight check expanded before benchmark execution (for example `python_compile`).",
    )
    run_campaign.add_argument(
        "--preflight-command",
        action="append",
        default=[],
        help="Repeatable preflight command run from the effective target root before benchmark execution.",
    )
    run_campaign.add_argument(
        "--preflight-timeout-seconds",
        type=int,
        default=None,
        help="Per-command preflight timeout. Defaults to campaign policy.",
    )
    run_campaign.add_argument(
        "--generator-option",
        action="append",
        default=[],
        help="Repeatable key=value generator option passed through to campaign proposal generation.",
    )
    run_campaign.add_argument(
        "--target-root",
        type=Path,
        default=Path("."),
        help="Target harness root for generated proposals. Default: current directory.",
    )
    run_campaign.add_argument(
        "--max-proposals",
        type=int,
        default=None,
        help="Optional number of candidates to execute before pausing the campaign.",
    )
    run_campaign.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Optional total candidate-attempt budget across the full campaign.",
    )
    run_campaign.add_argument(
        "--max-successes",
        type=int,
        default=None,
        help="Optional number of successful candidates before the campaign stops.",
    )
    run_campaign.add_argument(
        "--max-promotions",
        type=int,
        default=None,
        help="Optional number of promoted candidates before the campaign stops.",
    )
    run_campaign.add_argument(
        "--max-failures",
        type=int,
        default=None,
        help="Optional number of failed candidates before the campaign stops.",
    )
    run_campaign.add_argument(
        "--max-inconclusive",
        type=int,
        default=None,
        help="Optional number of inconclusive candidates before the campaign pauses.",
    )
    run_campaign.add_argument(
        "--no-improvement-limit",
        type=int,
        default=None,
        help="Optional consecutive non-improving candidates before the campaign pauses.",
    )
    run_campaign.add_argument(
        "--auto-promote",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Promote winning candidates automatically. Defaults to track/workspace campaign policy.",
    )
    run_campaign.add_argument(
        "--allow-flaky-promotion",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Allow automatic promotion even when repeated validation is flaky.",
    )
    run_campaign.add_argument(
        "--auto-promote-min-stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Minimum stage that automatic campaign promotion may use.",
    )
    run_campaign.add_argument(
        "--stop-on-first-promotion",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Stop the campaign as soon as one candidate is promoted. Defaults to track/workspace campaign policy.",
    )
    run_campaign.add_argument(
        "--promotion-target-root",
        type=Path,
        default=None,
        help="Optional target root for automatic promotion. Defaults to --target-root.",
    )
    run_campaign.add_argument(
        "--dry-run",
        action="store_true",
        help="Run proposal-backed iterations as dry runs only.",
    )
    run_campaign.add_argument(
        "--background",
        action="store_true",
        help="Queue the campaign for background execution instead of running it immediately.",
    )
    run_campaign.add_argument(
        "--time-budget-seconds",
        type=int,
        default=None,
        help="Optional wall-clock budget in seconds across the full campaign.",
    )
    run_campaign.add_argument(
        "--max-generation-total-tokens",
        type=int,
        default=None,
        help="Optional cumulative generator-token budget across the full campaign.",
    )
    run_campaign.add_argument(
        "--max-benchmark-total-cost",
        type=float,
        default=None,
        help="Optional cumulative benchmark-cost budget across the full campaign.",
    )
    run_campaign.add_argument(
        "--max-generation-retries",
        type=int,
        default=None,
        help="Optional retry budget for proposal-generation failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-generation-timeout-retries",
        type=int,
        default=None,
        help="Optional retry budget for proposal-generation timeout failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-generation-provider-retries",
        type=int,
        default=None,
        help="Optional retry budget for proposal-generation provider/network failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-generation-provider-transport-retries",
        type=int,
        default=None,
        help="Optional retry budget for proposal-generation provider-transport failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-generation-provider-auth-retries",
        type=int,
        default=None,
        help="Optional retry budget for proposal-generation provider-auth failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-generation-provider-rate-limit-retries",
        type=int,
        default=None,
        help="Optional retry budget for proposal-generation provider rate-limit failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-generation-process-retries",
        type=int,
        default=None,
        help="Optional retry budget for local generator-process failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-preflight-retries",
        type=int,
        default=None,
        help="Optional retry budget for failed preflight validation per candidate.",
    )
    run_campaign.add_argument(
        "--max-execution-retries",
        type=int,
        default=None,
        help="Optional retry budget for execution failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-benchmark-process-retries",
        type=int,
        default=None,
        help="Optional retry budget for benchmark process-start failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-benchmark-signal-retries",
        type=int,
        default=None,
        help="Optional retry budget for benchmark signal-termination failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-benchmark-parse-retries",
        type=int,
        default=None,
        help="Optional retry budget for benchmark parse failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-benchmark-adapter-validation-retries",
        type=int,
        default=None,
        help="Optional retry budget for benchmark adapter-validation failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-benchmark-timeout-retries",
        type=int,
        default=None,
        help="Optional retry budget for benchmark-timeout failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-benchmark-command-retries",
        type=int,
        default=None,
        help="Optional retry budget for benchmark-command failures per candidate.",
    )
    run_campaign.add_argument(
        "--max-inconclusive-retries",
        type=int,
        default=None,
        help="Optional retry budget for inconclusive candidate runs per candidate.",
    )
    _add_json_output_arguments(
        run_campaign,
        json_help="Print the final campaign state as JSON.",
        output_help="Optional path to write the final campaign state JSON.",
    )
    run_campaign.set_defaults(handler=_handle_run_campaign)

    run_campaign_worker = subparsers.add_parser(
        "run-campaign-worker",
        help="Claim and execute queued background campaigns.",
    )
    run_campaign_worker.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(run_campaign_worker)
    run_campaign_worker.add_argument(
        "--track-id",
        action="append",
        default=[],
        help="Repeatable track id filter. Defaults to all tracks in each selected workspace.",
    )
    run_campaign_worker.add_argument(
        "--worker-id",
        default=None,
        help="Optional stable worker identifier. Defaults to a generated id.",
    )
    run_campaign_worker.add_argument(
        "--lease-seconds",
        type=int,
        default=300,
        help="Lease duration for claimed campaigns and workspace ownership. Default: 300.",
    )
    run_campaign_worker.add_argument(
        "--max-campaigns",
        type=int,
        default=None,
        help="Optional cap on how many queued campaigns this worker should process before exiting.",
    )
    _add_json_output_arguments(
        run_campaign_worker,
        json_help="Print the worker claim/result summary as JSON.",
        output_help="Optional path to write the worker summary JSON.",
    )
    run_campaign_worker.set_defaults(handler=_handle_run_campaign_worker)

    run_workspace_campaigns = subparsers.add_parser(
        "run-workspace-campaigns",
        help="Run one campaign per selected active track in a workspace.",
    )
    _add_workspace_campaign_batch_arguments(run_workspace_campaigns)
    _add_json_output_arguments(
        run_workspace_campaigns,
        json_help="Print the workspace campaign batch result as JSON.",
        output_help="Optional path to write the workspace campaign batch JSON.",
    )
    run_workspace_campaigns.set_defaults(handler=_handle_run_workspace_campaigns)

    export_workspace_campaign_run_report = subparsers.add_parser(
        "export-workspace-campaign-run-report",
        help="Run one campaign per selected active track in a workspace and export the batch result.",
    )
    _add_workspace_campaign_batch_arguments(export_workspace_campaign_run_report)
    _add_required_output_argument(
        export_workspace_campaign_run_report,
        output_help="Output path for the exported workspace campaign run report.",
    )
    _add_optional_format_argument(
        export_workspace_campaign_run_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_workspace_campaign_run_report.set_defaults(
        handler=_handle_export_workspace_campaign_run_report
    )

    run_root_campaigns = subparsers.add_parser(
        "run-root-campaigns",
        help="Run workspace campaigns across selected workspaces under one workspace root.",
    )
    _add_root_campaign_batch_arguments(run_root_campaigns)
    _add_json_output_arguments(
        run_root_campaigns,
        json_help="Print the root campaign orchestration result as JSON.",
        output_help="Optional path to write the root campaign orchestration JSON.",
    )
    run_root_campaigns.set_defaults(handler=_handle_run_root_campaigns)

    export_root_campaign_run_report = subparsers.add_parser(
        "export-root-campaign-run-report",
        help="Run workspace campaigns across selected workspaces and export the orchestration result.",
    )
    _add_root_campaign_batch_arguments(export_root_campaign_run_report)
    _add_required_output_argument(
        export_root_campaign_run_report,
        output_help="Output path for the exported root campaign run report.",
    )
    _add_optional_format_argument(
        export_root_campaign_run_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_root_campaign_run_report.set_defaults(
        handler=_handle_export_root_campaign_run_report
    )

    show_root_campaigns = subparsers.add_parser(
        "show-root-campaigns",
        help="List persisted campaign runs across selected workspaces under one workspace root.",
    )
    show_root_campaigns.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(show_root_campaigns)
    show_root_campaigns.add_argument(
        "--track-id",
        action="append",
        default=[],
        help="Repeatable track id filter. Defaults to all tracks in each selected workspace.",
    )
    _add_json_output_arguments(
        show_root_campaigns,
        json_help="Print the root campaign listing as JSON.",
        output_help="Optional path to write the root campaign listing JSON.",
    )
    show_root_campaigns.set_defaults(handler=_handle_show_root_campaigns)

    export_root_campaign_report = subparsers.add_parser(
        "export-root-campaign-report",
        help="Export persisted campaign runs across selected workspaces under one workspace root.",
    )
    export_root_campaign_report.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(export_root_campaign_report)
    export_root_campaign_report.add_argument(
        "--track-id",
        action="append",
        default=[],
        help="Repeatable track id filter. Defaults to all tracks in each selected workspace.",
    )
    _add_required_output_argument(
        export_root_campaign_report,
        output_help="Output path for the exported root campaign report.",
    )
    _add_optional_format_argument(
        export_root_campaign_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_root_campaign_report.set_defaults(handler=_handle_export_root_campaign_report)

    resume_campaign = subparsers.add_parser(
        "resume-campaign",
        help="Resume a previously paused campaign run.",
    )
    _add_workspace_id_argument(resume_campaign)
    _add_optional_track_selection_argument(resume_campaign)
    _add_workspace_root_argument(resume_campaign)
    resume_campaign.add_argument("--campaign-id", required=True)
    _add_json_output_arguments(
        resume_campaign,
        json_help="Print the resumed campaign state as JSON.",
        output_help="Optional path to write the resumed campaign state JSON.",
    )
    resume_campaign.set_defaults(handler=_handle_resume_campaign)

    pause_campaign = subparsers.add_parser(
        "pause-campaign",
        help="Request that a queued or running campaign pause at the next control checkpoint.",
    )
    _add_workspace_id_argument(pause_campaign)
    _add_optional_track_selection_argument(pause_campaign)
    _add_workspace_root_argument(pause_campaign)
    pause_campaign.add_argument("--campaign-id", required=True)
    _add_json_output_arguments(
        pause_campaign,
        json_help="Print the updated campaign state as JSON.",
        output_help="Optional path to write the updated campaign state JSON.",
    )
    pause_campaign.set_defaults(handler=_handle_pause_campaign)

    cancel_campaign = subparsers.add_parser(
        "cancel-campaign",
        help="Request that a queued or running campaign cancel at the next control checkpoint.",
    )
    _add_workspace_id_argument(cancel_campaign)
    _add_optional_track_selection_argument(cancel_campaign)
    _add_workspace_root_argument(cancel_campaign)
    cancel_campaign.add_argument("--campaign-id", required=True)
    _add_json_output_arguments(
        cancel_campaign,
        json_help="Print the updated campaign state as JSON.",
        output_help="Optional path to write the updated campaign state JSON.",
    )
    cancel_campaign.set_defaults(handler=_handle_cancel_campaign)

    show_campaign = subparsers.add_parser(
        "show-campaign",
        help="Show one persisted campaign run.",
    )
    _add_workspace_id_argument(show_campaign)
    _add_optional_track_selection_argument(show_campaign)
    _add_workspace_root_argument(show_campaign)
    show_campaign.add_argument("--campaign-id", required=True)
    _add_json_output_arguments(
        show_campaign,
        json_help="Print the campaign JSON.",
        output_help="Optional path to write the campaign JSON.",
    )
    show_campaign.set_defaults(handler=_handle_show_campaign)

    show_campaigns = subparsers.add_parser(
        "show-campaigns",
        help="List campaign runs for one workspace.",
    )
    _add_workspace_id_argument(show_campaigns)
    _add_optional_track_selection_argument(show_campaigns)
    _add_workspace_root_argument(show_campaigns)
    _add_json_output_arguments(
        show_campaigns,
        json_help="Print the campaign listing JSON.",
        output_help="Optional path to write the campaign listing JSON.",
    )
    show_campaigns.set_defaults(handler=_handle_show_campaigns)

    show_campaign_report_file = subparsers.add_parser(
        "show-campaign-report-file",
        help="Inspect one exported campaign report file.",
    )
    show_campaign_report_file.add_argument("path", type=Path)
    _add_json_output_arguments(
        show_campaign_report_file,
        json_help="Print the exported campaign report inspection JSON.",
        output_help="Optional path to write the exported campaign report inspection JSON.",
    )
    show_campaign_report_file.set_defaults(handler=_handle_show_campaign_report_file)

    validate_campaign_report_file = subparsers.add_parser(
        "validate-campaign-report-file",
        help="Validate one exported campaign report file.",
    )
    validate_campaign_report_file.add_argument("path", type=Path)
    _add_json_output_arguments(
        validate_campaign_report_file,
        json_help="Print the exported campaign report validation JSON.",
        output_help="Optional path to write the exported campaign report validation JSON.",
    )
    validate_campaign_report_file.set_defaults(
        handler=_handle_validate_campaign_report_file
    )

    export_workspace_campaign_report = subparsers.add_parser(
        "export-workspace-campaign-report",
        help="Export persisted campaign runs for one workspace.",
    )
    _add_workspace_id_argument(export_workspace_campaign_report)
    _add_optional_track_selection_argument(export_workspace_campaign_report)
    _add_workspace_root_argument(export_workspace_campaign_report)
    _add_required_output_argument(
        export_workspace_campaign_report,
        output_help="Output path for the exported workspace campaign report.",
    )
    _add_optional_format_argument(
        export_workspace_campaign_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_workspace_campaign_report.set_defaults(
        handler=_handle_export_workspace_campaign_report
    )

    export_workspace_campaign_bundle = subparsers.add_parser(
        "export-workspace-campaign-bundle",
        help="Export persisted campaign runs for one workspace as a portable directory bundle.",
    )
    _add_workspace_id_argument(export_workspace_campaign_bundle)
    _add_optional_track_selection_argument(export_workspace_campaign_bundle)
    _add_workspace_root_argument(export_workspace_campaign_bundle)
    _add_required_output_argument(
        export_workspace_campaign_bundle,
        output_help="Output directory for the exported workspace campaign bundle.",
    )
    _add_optional_format_argument(
        export_workspace_campaign_bundle,
        help_text="Optional structured file format for campaign manifests and reports. Defaults to json.",
    )
    _add_force_argument(
        export_workspace_campaign_bundle,
        help_text="Allow writing into a non-empty output directory.",
    )
    export_workspace_campaign_bundle.set_defaults(
        handler=_handle_export_workspace_campaign_bundle
    )

    show_campaign_artifacts = subparsers.add_parser(
        "show-campaign-artifacts",
        help="Show the proposal, record, and iteration artifacts linked to one campaign run.",
    )
    _add_workspace_id_argument(show_campaign_artifacts)
    _add_optional_track_selection_argument(show_campaign_artifacts)
    _add_workspace_root_argument(show_campaign_artifacts)
    show_campaign_artifacts.add_argument("--campaign-id", required=True)
    _add_json_output_arguments(
        show_campaign_artifacts,
        json_help="Print the campaign artifact listing JSON.",
        output_help="Optional path to write the campaign artifact listing JSON.",
    )
    show_campaign_artifacts.set_defaults(handler=_handle_show_campaign_artifacts)

    export_campaign_report = subparsers.add_parser(
        "export-campaign-report",
        help="Export one campaign run with linked proposal, record, and iteration data.",
    )
    _add_workspace_id_argument(export_campaign_report)
    _add_optional_track_selection_argument(export_campaign_report)
    _add_workspace_root_argument(export_campaign_report)
    export_campaign_report.add_argument("--campaign-id", required=True)
    _add_required_output_argument(
        export_campaign_report,
        output_help="Output path for the exported campaign report.",
    )
    _add_optional_format_argument(
        export_campaign_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_campaign_report.set_defaults(handler=_handle_export_campaign_report)

    export_campaign_bundle = subparsers.add_parser(
        "export-campaign-bundle",
        help="Export one campaign run as a portable directory bundle.",
    )
    _add_workspace_id_argument(export_campaign_bundle)
    _add_optional_track_selection_argument(export_campaign_bundle)
    _add_workspace_root_argument(export_campaign_bundle)
    export_campaign_bundle.add_argument("--campaign-id", required=True)
    _add_required_output_argument(
        export_campaign_bundle,
        output_help="Output directory for the exported campaign bundle.",
    )
    _add_optional_format_argument(
        export_campaign_bundle,
        help_text="Optional structured file format for campaign manifests and reports. Defaults to json.",
    )
    _add_force_argument(
        export_campaign_bundle,
        help_text="Allow writing into a non-empty output directory.",
    )
    export_campaign_bundle.set_defaults(handler=_handle_export_campaign_bundle)

    export_root_campaign_bundle = subparsers.add_parser(
        "export-root-campaign-bundle",
        help="Export persisted campaign runs across selected workspaces as a portable directory bundle.",
    )
    export_root_campaign_bundle.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(export_root_campaign_bundle)
    export_root_campaign_bundle.add_argument(
        "--track-id",
        action="append",
        default=[],
        help="Repeatable track id filter. Defaults to all tracks in each selected workspace.",
    )
    _add_required_output_argument(
        export_root_campaign_bundle,
        output_help="Output directory for the exported root campaign bundle.",
    )
    _add_optional_format_argument(
        export_root_campaign_bundle,
        help_text="Optional structured file format for campaign manifests and reports. Defaults to json.",
    )
    _add_force_argument(
        export_root_campaign_bundle,
        help_text="Allow writing into a non-empty output directory.",
    )
    export_root_campaign_bundle.set_defaults(handler=_handle_export_root_campaign_bundle)
