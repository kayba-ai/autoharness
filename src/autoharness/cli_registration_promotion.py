"""Promotion and champion action registration."""

from __future__ import annotations

from pathlib import Path

from .cli_arguments import (
    _add_comparison_gate_arguments,
    _add_force_argument,
    _add_json_output_arguments,
    _add_notes_argument,
    _add_optional_output_argument,
    _add_optional_track_selection_argument,
    _add_optional_workspace_id_argument,
    _add_required_output_argument,
    _add_required_record_id_argument,
    _add_required_target_root_argument,
    _add_stage_policy_argument,
    _add_workspace_id_argument,
    _add_workspace_root_argument,
)
from .promotion_handlers import (
    _handle_compare_to_champion,
    _handle_export_champion,
    _handle_promote,
    _handle_promote_from_compare,
    _handle_transfer_root_champions,
    _handle_transfer_champion,
)


def register_promotion_parsers(subparsers) -> None:
    promote = subparsers.add_parser(
        "promote",
        help="Replay one recorded candidate onto a target harness and mark it champion.",
    )
    _add_optional_workspace_id_argument(promote)
    _add_required_record_id_argument(promote)
    _add_required_target_root_argument(promote)
    _add_optional_track_selection_argument(promote)
    _add_workspace_root_argument(promote)
    promote.add_argument("--notes", default="")
    _add_optional_output_argument(
        promote,
        output_help="Optional path to write the promotion payload JSON.",
    )
    promote.set_defaults(handler=_handle_promote)

    export_champion = subparsers.add_parser(
        "export-champion",
        help="Export the current champion bundle for one workspace track.",
    )
    _add_workspace_id_argument(export_champion)
    _add_optional_track_selection_argument(export_champion)
    _add_workspace_root_argument(export_champion)
    _add_required_output_argument(
        export_champion,
        output_help="Output directory for the exported champion bundle.",
    )
    _add_force_argument(
        export_champion,
        help_text="Allow writing into a non-empty output directory.",
    )
    export_champion.set_defaults(handler=_handle_export_champion)

    transfer_champion = subparsers.add_parser(
        "transfer-champion",
        help="Transfer an active champion from one workspace track into another.",
    )
    transfer_champion.add_argument("--source-workspace-id", required=True)
    transfer_champion.add_argument("--source-track-id", default=None)
    _add_workspace_id_argument(transfer_champion)
    _add_optional_track_selection_argument(transfer_champion)
    _add_required_target_root_argument(transfer_champion)
    _add_workspace_root_argument(transfer_champion)
    _add_notes_argument(
        transfer_champion,
        default="",
        help_text="Optional note for the destination promotion record.",
    )
    _add_json_output_arguments(
        transfer_champion,
        json_help="Print the transfer payload JSON.",
        output_help="Optional path to write the transfer payload JSON.",
    )
    transfer_champion.set_defaults(handler=_handle_transfer_champion)

    transfer_root_champions = subparsers.add_parser(
        "transfer-root-champions",
        help="Transfer one source champion into multiple destination workspaces.",
    )
    transfer_root_champions.add_argument("--source-workspace-id", required=True)
    transfer_root_champions.add_argument("--source-track-id", default=None)
    transfer_root_champions.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Destination workspace to receive the transferred champion. Repeatable.",
    )
    transfer_root_champions.add_argument("--destination-track-id", default=None)
    transfer_root_champions.add_argument("--target-root-base", type=Path, required=True)
    transfer_root_champions.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Keep transferring to later workspaces after one destination fails.",
    )
    _add_workspace_root_argument(transfer_root_champions)
    _add_notes_argument(
        transfer_root_champions,
        default="",
        help_text="Optional note for each destination promotion record.",
    )
    _add_json_output_arguments(
        transfer_root_champions,
        json_help="Print the root transfer batch payload JSON.",
        output_help="Optional path to write the root transfer batch JSON.",
    )
    transfer_root_champions.set_defaults(handler=_handle_transfer_root_champions)

    compare_to_champion = subparsers.add_parser(
        "compare-to-champion",
        help="Compare one recorded candidate against the active track champion.",
    )
    _add_optional_workspace_id_argument(compare_to_champion)
    _add_required_record_id_argument(compare_to_champion)
    _add_optional_track_selection_argument(compare_to_champion)
    _add_workspace_root_argument(compare_to_champion)
    _add_stage_policy_argument(
        compare_to_champion,
        default=None,
        help_text=(
            "Optional stage policy to use for the comparison. Defaults to the "
            "candidate record stage."
        ),
    )
    _add_comparison_gate_arguments(
        compare_to_champion,
        comparison_target_label="champion",
        min_success_rate_default=None,
        min_improvement_default=None,
        task_regression_margin_default=None,
    )
    _add_json_output_arguments(
        compare_to_champion,
        json_help="Print the raw comparison JSON.",
        output_help="Optional path to write the comparison JSON.",
    )
    compare_to_champion.set_defaults(handler=_handle_compare_to_champion)

    promote_from_compare = subparsers.add_parser(
        "promote-from-compare",
        help="Compare a recorded candidate to the active champion and promote only if it wins.",
    )
    _add_optional_workspace_id_argument(promote_from_compare)
    _add_required_record_id_argument(promote_from_compare)
    _add_required_target_root_argument(promote_from_compare)
    _add_optional_track_selection_argument(promote_from_compare)
    _add_workspace_root_argument(promote_from_compare)
    _add_stage_policy_argument(
        promote_from_compare,
        default=None,
        help_text=(
            "Optional stage policy to use for the comparison. Defaults to the "
            "candidate record stage."
        ),
    )
    _add_comparison_gate_arguments(
        promote_from_compare,
        comparison_target_label="champion",
        min_success_rate_default=None,
        min_improvement_default=None,
        task_regression_margin_default=None,
    )
    promote_from_compare.add_argument("--notes", default="")
    _add_optional_output_argument(
        promote_from_compare,
        output_help="Optional path to write the combined comparison and promotion JSON.",
    )
    promote_from_compare.set_defaults(handler=_handle_promote_from_compare)
