"""Listing and export command registration."""

from __future__ import annotations

from pathlib import Path

from .cli_arguments import (
    _add_iteration_query_arguments,
    _add_json_output_arguments,
    _add_optional_format_argument,
    _add_promotion_query_arguments,
    _add_record_query_arguments,
    _add_required_output_argument,
    _add_workspace_id_argument,
    _add_workspace_root_argument,
)
from .listing_handlers import (
    _handle_export_iterations,
    _handle_export_promotions,
    _handle_export_records,
    _handle_show_listing_file,
    _handle_show_iterations,
    _handle_show_promotions,
    _handle_show_records,
    _handle_validate_listing_file,
)


def register_listing_parsers(subparsers) -> None:
    show_listing_file = subparsers.add_parser(
        "show-listing-file",
        help="Inspect an exported iteration, record, promotion, or proposal listing artifact file.",
    )
    show_listing_file.add_argument(
        "path",
        type=Path,
        help="Listing artifact file path.",
    )
    _add_json_output_arguments(
        show_listing_file,
        json_help="Print the resolved listing artifact JSON.",
        output_help="Optional path to write the resolved listing artifact JSON.",
    )
    show_listing_file.set_defaults(handler=_handle_show_listing_file)

    validate_listing_file = subparsers.add_parser(
        "validate-listing-file",
        help="Validate an exported iteration, record, promotion, or proposal listing artifact file.",
    )
    validate_listing_file.add_argument(
        "path",
        type=Path,
        help="Listing artifact file path.",
    )
    _add_json_output_arguments(
        validate_listing_file,
        json_help="Print listing-file validation JSON.",
        output_help="Optional path to write the listing-file validation JSON.",
    )
    validate_listing_file.set_defaults(handler=_handle_validate_listing_file)

    show_iterations = subparsers.add_parser(
        "show-iterations",
        help="Show iteration summaries for one workspace.",
    )
    _add_workspace_id_argument(show_iterations)
    _add_workspace_root_argument(show_iterations)
    _add_iteration_query_arguments(show_iterations)
    _add_json_output_arguments(
        show_iterations,
        json_help="Print the raw iteration listing JSON.",
        output_help="Optional path to write the iteration listing JSON.",
    )
    show_iterations.set_defaults(handler=_handle_show_iterations)

    export_iterations = subparsers.add_parser(
        "export-iterations",
        help="Export iteration summaries for one workspace.",
    )
    _add_workspace_id_argument(export_iterations)
    _add_workspace_root_argument(export_iterations)
    _add_iteration_query_arguments(export_iterations)
    _add_required_output_argument(
        export_iterations,
        output_help="Output path for the exported iteration listing.",
    )
    _add_optional_format_argument(
        export_iterations,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_iterations.set_defaults(handler=_handle_export_iterations)

    show_records = subparsers.add_parser(
        "show-records",
        help="Show benchmark records for one workspace.",
    )
    _add_workspace_id_argument(show_records)
    _add_workspace_root_argument(show_records)
    _add_record_query_arguments(show_records)
    _add_json_output_arguments(
        show_records,
        json_help="Print the raw record listing JSON.",
        output_help="Optional path to write the record listing JSON.",
    )
    show_records.set_defaults(handler=_handle_show_records)

    export_records = subparsers.add_parser(
        "export-records",
        help="Export benchmark records for one workspace.",
    )
    _add_workspace_id_argument(export_records)
    _add_workspace_root_argument(export_records)
    _add_record_query_arguments(export_records)
    _add_required_output_argument(
        export_records,
        output_help="Output path for the exported record listing.",
    )
    _add_optional_format_argument(
        export_records,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_records.set_defaults(handler=_handle_export_records)

    show_promotions = subparsers.add_parser(
        "show-promotions",
        help="Show promotions for one workspace.",
    )
    _add_workspace_id_argument(show_promotions)
    _add_workspace_root_argument(show_promotions)
    _add_promotion_query_arguments(show_promotions)
    _add_json_output_arguments(
        show_promotions,
        json_help="Print the raw promotion listing JSON.",
        output_help="Optional path to write the promotion listing JSON.",
    )
    show_promotions.set_defaults(handler=_handle_show_promotions)

    export_promotions = subparsers.add_parser(
        "export-promotions",
        help="Export promotions for one workspace.",
    )
    _add_workspace_id_argument(export_promotions)
    _add_workspace_root_argument(export_promotions)
    _add_promotion_query_arguments(export_promotions)
    _add_required_output_argument(
        export_promotions,
        output_help="Output path for the exported promotion listing.",
    )
    _add_optional_format_argument(
        export_promotions,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_promotions.set_defaults(handler=_handle_export_promotions)
