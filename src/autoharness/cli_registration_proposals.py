"""Proposal command registration."""

from __future__ import annotations

from pathlib import Path

from .cli_arguments import (
    _add_config_composition_arguments,
    _add_json_output_arguments,
    _add_optional_format_argument,
    _add_optional_output_argument,
    _add_optional_workspace_id_argument,
    _add_optional_track_selection_argument,
    _add_proposal_query_arguments,
    _add_required_adapter_argument,
    _add_required_output_argument,
    _add_required_proposal_id_argument,
    _add_workspace_id_argument,
    _add_workspace_root_argument,
)
from .proposal_handlers import (
    _handle_apply_proposal,
    _handle_export_proposals,
    _handle_generate_proposal,
    _handle_list_generators,
    _handle_run_proposal,
    _handle_show_generator,
    _handle_show_proposal,
    _handle_show_proposals,
)
from .preflight import available_preflight_checks


def register_proposal_parsers(subparsers) -> None:
    list_generators = subparsers.add_parser(
        "list-generators",
        help="Show the built-in proposal generator catalog.",
    )
    _add_json_output_arguments(
        list_generators,
        json_help="Render the generator catalog as JSON.",
        output_help="Optional path to write the rendered generator catalog JSON.",
    )
    list_generators.set_defaults(handler=_handle_list_generators)

    show_generator = subparsers.add_parser(
        "show-generator",
        help="Show one proposal generator's operator-facing metadata.",
    )
    show_generator.add_argument(
        "--generator",
        required=True,
        help="Proposal generator id from the built-in registry.",
    )
    _add_json_output_arguments(
        show_generator,
        json_help="Render the generator metadata as JSON.",
        output_help="Optional path to write the rendered generator metadata JSON.",
    )
    show_generator.set_defaults(handler=_handle_show_generator)

    generate_proposal = subparsers.add_parser(
        "generate-proposal",
        help="Preview and persist one proposal artifact without running the benchmark.",
    )
    _add_optional_workspace_id_argument(generate_proposal)
    _add_required_adapter_argument(generate_proposal)
    _add_config_composition_arguments(
        generate_proposal,
        preset_help=(
            "Optional starter-config preset override. Defaults to the track/workspace "
            "policy preset for the selected stage when available."
        ),
    )
    generate_proposal.add_argument(
        "--edit-plan",
        type=Path,
        default=None,
        help=(
            "Optional YAML or JSON edit plan input. Required for the `manual` generator; "
            "autonomous generators may synthesize the plan directly."
        ),
    )
    generate_proposal.add_argument(
        "--hypothesis",
        default=None,
        help="Optional proposal hypothesis text. Defaults to a generated stage-aware label.",
    )
    generate_proposal.add_argument(
        "--summary",
        default=None,
        help="Optional summary override for the proposal artifact.",
    )
    generate_proposal.add_argument("--notes", default="")
    generate_proposal.add_argument(
        "--generator",
        default="manual",
        help="Proposal generator id. Default: manual.",
    )
    generate_proposal.add_argument(
        "--intervention-class",
        choices=("prompt", "config", "middleware", "source"),
        default=None,
        help="Optional intervention class hint for non-manual proposal generators.",
    )
    generate_proposal.add_argument(
        "--generator-option",
        action="append",
        default=[],
        help="Repeatable key=value generator option passed through to the selected generator.",
    )
    _add_optional_track_selection_argument(generate_proposal)
    _add_workspace_root_argument(generate_proposal)
    generate_proposal.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default="screening",
        help="Evaluation stage policy to plan the proposal against. Default: screening.",
    )
    generate_proposal.add_argument(
        "--target-root",
        type=Path,
        default=Path("."),
        help="Target harness root for edit-plan preview. Default: current directory.",
    )
    _add_json_output_arguments(
        generate_proposal,
        json_help="Print the generated proposal artifact JSON.",
        output_help="Optional path to write the generated proposal artifact JSON.",
    )
    generate_proposal.set_defaults(handler=_handle_generate_proposal)

    show_proposal = subparsers.add_parser(
        "show-proposal",
        help="Show one persisted proposal artifact.",
    )
    _add_optional_workspace_id_argument(show_proposal)
    _add_optional_track_selection_argument(show_proposal)
    _add_required_proposal_id_argument(show_proposal)
    _add_workspace_root_argument(show_proposal)
    _add_json_output_arguments(
        show_proposal,
        json_help="Print the raw proposal JSON with loaded edit-plan artifacts.",
        output_help="Optional path to write the proposal JSON.",
    )
    show_proposal.set_defaults(handler=_handle_show_proposal)

    apply_proposal = subparsers.add_parser(
        "apply-proposal",
        help="Apply one saved proposal to a target harness root and keep the edits.",
    )
    _add_optional_workspace_id_argument(apply_proposal)
    _add_optional_track_selection_argument(apply_proposal)
    _add_required_proposal_id_argument(apply_proposal)
    _add_workspace_root_argument(apply_proposal)
    apply_proposal.add_argument(
        "--target-root",
        type=Path,
        default=None,
        help="Optional target harness root override. Defaults to the proposal target root.",
    )
    _add_json_output_arguments(
        apply_proposal,
        json_help="Print the raw proposal-application JSON.",
        output_help="Optional path to write the proposal-application JSON.",
    )
    apply_proposal.set_defaults(handler=_handle_apply_proposal)

    run_proposal = subparsers.add_parser(
        "run-proposal",
        help="Execute one saved proposal through the existing run-iteration flow.",
    )
    _add_optional_workspace_id_argument(run_proposal)
    _add_optional_track_selection_argument(run_proposal)
    _add_required_proposal_id_argument(run_proposal)
    _add_workspace_root_argument(run_proposal)
    run_proposal.add_argument(
        "--target-root",
        type=Path,
        default=None,
        help="Optional target harness root override. Defaults to the proposal target root.",
    )
    run_proposal.add_argument(
        "--keep-applied-edits",
        action="store_true",
        help="Keep applied edits on disk after the proposal-backed iteration finishes.",
    )
    run_proposal.add_argument(
        "--staging-mode",
        choices=("off", "copy", "auto"),
        default="auto",
        help="Optional isolated target execution mode. Default: auto.",
    )
    run_proposal.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the saved proposal as a dry-run invocation only.",
    )
    run_proposal.add_argument(
        "--preflight-check",
        choices=available_preflight_checks(),
        action="append",
        default=[],
        help="Repeatable built-in preflight check expanded before the benchmark (for example `python_compile`).",
    )
    run_proposal.add_argument(
        "--preflight-command",
        action="append",
        default=[],
        help="Repeatable preflight command run from the effective target root before the benchmark.",
    )
    run_proposal.add_argument(
        "--preflight-timeout-seconds",
        type=int,
        default=None,
        help="Per-command timeout for preflight commands. Defaults to track/workspace campaign policy, then 60.",
    )
    run_proposal.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="Validation repeat-count override. Defaults to track/workspace campaign policy, then the stage default.",
    )
    _add_optional_output_argument(
        run_proposal,
        output_help="Optional path to also write the raw proposal-backed run payload JSON.",
    )
    run_proposal.set_defaults(handler=_handle_run_proposal)

    show_proposals = subparsers.add_parser(
        "show-proposals",
        help="Show proposal artifacts for one workspace.",
    )
    _add_optional_workspace_id_argument(show_proposals)
    _add_workspace_root_argument(show_proposals)
    _add_proposal_query_arguments(show_proposals)
    _add_json_output_arguments(
        show_proposals,
        json_help="Print the raw proposal listing JSON.",
        output_help="Optional path to write the proposal listing JSON.",
    )
    show_proposals.set_defaults(handler=_handle_show_proposals)

    export_proposals = subparsers.add_parser(
        "export-proposals",
        help="Export proposal artifacts for one workspace.",
    )
    _add_workspace_id_argument(export_proposals)
    _add_workspace_root_argument(export_proposals)
    _add_proposal_query_arguments(export_proposals)
    _add_required_output_argument(
        export_proposals,
        output_help="Output path for the exported proposal listing.",
    )
    _add_optional_format_argument(
        export_proposals,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_proposals.set_defaults(handler=_handle_export_proposals)
