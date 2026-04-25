"""Inspection and detail command registration."""

from __future__ import annotations

from pathlib import Path

from .cli_arguments import (
    _add_force_argument,
    _add_json_output_arguments,
    _add_optional_format_argument,
    _add_optional_workspace_id_argument,
    _add_optional_track_selection_argument,
    _add_required_output_argument,
    _add_required_iteration_id_argument,
    _add_required_promotion_id_argument,
    _add_required_record_id_argument,
    _add_skip_champion_argument,
    _add_skip_champions_argument,
    _add_skip_listings_argument,
    _add_skip_track_reports_argument,
    _add_workspace_id_argument,
    _add_workspace_root_argument,
)
from .detail_handlers import (
    _handle_show_champion,
    _handle_show_iteration,
    _handle_show_promotion,
    _handle_show_record,
)
from .inspection_handlers import (
    _handle_show_artifact_file,
    _handle_export_root_bundle,
    _handle_export_root_champion_report,
    _handle_export_root_report,
    _handle_export_root_summary,
    _handle_show_event_log,
    _handle_show_event_metrics,
    _handle_show_plugin_catalog,
    _handle_show_root_memory,
    _handle_export_track_bundle,
    _handle_export_track_report,
    _handle_export_track_summary,
    _handle_export_workspace_bundle,
    _handle_export_workspace_report,
    _handle_export_workspace_summary,
    _handle_import_bundle,
    _handle_reindex_bundle,
    _handle_show_report_file,
    _handle_show_bundle,
    _handle_show_root_champions,
    _handle_show_root_summary,
    _handle_validate_artifact_file,
    _handle_validate_bundle,
    _handle_validate_report_file,
    _handle_show_promotion_policy,
    _handle_show_track,
    _handle_show_track_artifacts,
    _handle_show_track_policy,
    _handle_show_track_summary,
    _handle_show_tracks,
    _handle_show_workspace,
    _handle_show_workspace_summary,
    _handle_tail_campaign_events,
)


def register_inspection_parsers(subparsers) -> None:
    show_artifact_file = subparsers.add_parser(
        "show-artifact-file",
        help="Auto-detect and inspect a saved plan, listing, or report artifact file.",
    )
    show_artifact_file.add_argument(
        "path",
        type=Path,
        help="Artifact file path.",
    )
    _add_json_output_arguments(
        show_artifact_file,
        json_help="Print the resolved artifact JSON.",
        output_help="Optional path to write the resolved artifact JSON.",
    )
    show_artifact_file.set_defaults(handler=_handle_show_artifact_file)

    validate_artifact_file = subparsers.add_parser(
        "validate-artifact-file",
        help="Auto-detect and validate a saved plan, listing, or report artifact file.",
    )
    validate_artifact_file.add_argument(
        "path",
        type=Path,
        help="Artifact file path.",
    )
    _add_json_output_arguments(
        validate_artifact_file,
        json_help="Print artifact validation JSON.",
        output_help="Optional path to write the artifact validation JSON.",
    )
    validate_artifact_file.set_defaults(handler=_handle_validate_artifact_file)

    show_report_file = subparsers.add_parser(
        "show-report-file",
        help="Inspect an exported workspace or track summary/report artifact file.",
    )
    show_report_file.add_argument(
        "path",
        type=Path,
        help="Summary or report file path.",
    )
    _add_json_output_arguments(
        show_report_file,
        json_help="Print the resolved report artifact JSON.",
        output_help="Optional path to write the resolved report artifact JSON.",
    )
    show_report_file.set_defaults(handler=_handle_show_report_file)

    validate_report_file = subparsers.add_parser(
        "validate-report-file",
        help="Validate an exported workspace or track summary/report artifact file.",
    )
    validate_report_file.add_argument(
        "path",
        type=Path,
        help="Summary or report file path.",
    )
    _add_json_output_arguments(
        validate_report_file,
        json_help="Print report-file validation JSON.",
        output_help="Optional path to write the report-file validation JSON.",
    )
    validate_report_file.set_defaults(handler=_handle_validate_report_file)

    show_bundle = subparsers.add_parser(
        "show-bundle",
        help="Inspect an exported workspace, track, or champion bundle directory.",
    )
    show_bundle.add_argument(
        "path",
        type=Path,
        help="Bundle directory or manifest file path.",
    )
    _add_json_output_arguments(
        show_bundle,
        json_help="Print the resolved bundle manifest and artifact status JSON.",
        output_help="Optional path to write the resolved bundle manifest JSON.",
    )
    show_bundle.add_argument(
        "--recursive",
        action="store_true",
        help="Also inspect nested champion bundles inside workspace and track bundles.",
    )
    show_bundle.set_defaults(handler=_handle_show_bundle)

    validate_bundle = subparsers.add_parser(
        "validate-bundle",
        help="Validate an exported workspace, track, or champion bundle directory.",
    )
    validate_bundle.add_argument(
        "path",
        type=Path,
        help="Bundle directory or manifest file path.",
    )
    _add_json_output_arguments(
        validate_bundle,
        json_help="Print bundle validation JSON.",
        output_help="Optional path to write the bundle validation JSON.",
    )
    validate_bundle.add_argument(
        "--recursive",
        action="store_true",
        help="Also validate nested champion bundles inside workspace and track bundles.",
    )
    validate_bundle.set_defaults(handler=_handle_validate_bundle)

    reindex_bundle = subparsers.add_parser(
        "reindex-bundle",
        help="Rebuild a bundle manifest from the files currently present in the bundle directory.",
    )
    reindex_bundle.add_argument(
        "path",
        type=Path,
        help="Bundle directory or manifest file path.",
    )
    _add_json_output_arguments(
        reindex_bundle,
        json_help="Print the rebuilt bundle manifest JSON.",
        output_help="Optional path to write the rebuilt bundle manifest. Defaults to rewriting the bundle manifest in place.",
    )
    _add_optional_format_argument(
        reindex_bundle,
        help_text="Optional manifest format. Defaults to preserving the existing manifest path or the bundle artifact format.",
    )
    reindex_bundle.add_argument(
        "--recursive",
        action="store_true",
        help="Also restamp nested champion bundle manifests before rebuilding the selected bundle manifest.",
    )
    reindex_bundle.set_defaults(handler=_handle_reindex_bundle)

    import_bundle = subparsers.add_parser(
        "import-bundle",
        help="Copy a saved workspace, track, or champion bundle into a new directory and validate it.",
    )
    import_bundle.add_argument(
        "path",
        type=Path,
        help="Source bundle directory or manifest file path.",
    )
    import_bundle.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination directory for the imported bundle.",
    )
    _add_force_argument(
        import_bundle,
        help_text="Allow importing into a non-empty destination directory.",
    )
    import_bundle.add_argument(
        "--reindex",
        action="store_true",
        help="Rewrite the destination bundle manifest to match the artifacts actually copied.",
    )
    import_bundle.add_argument(
        "--verify-source",
        action="store_true",
        help="Validate the source bundle before copying and fail early if it is invalid.",
    )
    import_bundle.add_argument(
        "--allow-invalid",
        action="store_true",
        help="When used with --verify-source, continue copying even if the source bundle is invalid.",
    )
    import_bundle.add_argument(
        "--target-format",
        choices=("yaml", "json"),
        default=None,
        help="Optional manifest format for the imported bundle. Defaults to preserving the source manifest format.",
    )
    import_bundle.add_argument(
        "--recursive",
        action="store_true",
        help="Apply source validation, destination validation, and any requested reindexing recursively to nested champion bundles.",
    )
    import_bundle.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the import, validation, and manifest decision without writing the destination bundle.",
    )
    import_bundle.add_argument(
        "--json",
        action="store_true",
        help="Print bundle import and validation JSON.",
    )
    import_bundle.set_defaults(handler=_handle_import_bundle)

    show_champion = subparsers.add_parser(
        "show-champion",
        help="Show the current champion manifest for one workspace track.",
    )
    _add_workspace_id_argument(show_champion)
    _add_optional_track_selection_argument(show_champion)
    _add_workspace_root_argument(show_champion)
    _add_json_output_arguments(
        show_champion,
        json_help="Print the raw champion manifest JSON.",
        output_help="Optional path to write the champion manifest JSON.",
    )
    show_champion.set_defaults(handler=_handle_show_champion)

    show_workspace_summary = subparsers.add_parser(
        "show-workspace-summary",
        aliases=["report"],
        help="Show aggregate summary across tracks, records, promotions, and iterations.",
    )
    _add_optional_workspace_id_argument(show_workspace_summary)
    _add_workspace_root_argument(show_workspace_summary)
    _add_json_output_arguments(
        show_workspace_summary,
        json_help="Print the raw workspace summary JSON.",
        output_help="Optional path to write the workspace summary JSON.",
    )
    show_workspace_summary.set_defaults(handler=_handle_show_workspace_summary)

    show_root_summary = subparsers.add_parser(
        "show-root-summary",
        help="Show aggregate summary across selected workspaces under one workspace root.",
    )
    show_root_summary.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(show_root_summary)
    _add_json_output_arguments(
        show_root_summary,
        json_help="Print the raw root summary JSON.",
        output_help="Optional path to write the root summary JSON.",
    )
    show_root_summary.set_defaults(handler=_handle_show_root_summary)

    show_root_champions = subparsers.add_parser(
        "show-root-champions",
        help="Show champions across selected workspaces under one workspace root.",
    )
    show_root_champions.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    show_root_champions.add_argument(
        "--track-id",
        action="append",
        default=[],
        help="Repeatable track id filter. Defaults to all tracks with champions.",
    )
    _add_workspace_root_argument(show_root_champions)
    _add_json_output_arguments(
        show_root_champions,
        json_help="Print the raw root champion listing JSON.",
        output_help="Optional path to write the root champion listing JSON.",
    )
    show_root_champions.set_defaults(handler=_handle_show_root_champions)

    export_workspace_summary = subparsers.add_parser(
        "export-workspace-summary",
        help="Export the workspace summary as a versioned YAML or JSON artifact.",
    )
    _add_workspace_id_argument(export_workspace_summary)
    _add_workspace_root_argument(export_workspace_summary)
    _add_required_output_argument(
        export_workspace_summary,
        output_help="Output path for the exported workspace summary.",
    )
    _add_optional_format_argument(
        export_workspace_summary,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_workspace_summary.set_defaults(handler=_handle_export_workspace_summary)

    export_root_summary = subparsers.add_parser(
        "export-root-summary",
        help="Export the root summary as a versioned YAML or JSON artifact.",
    )
    export_root_summary.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(export_root_summary)
    _add_required_output_argument(
        export_root_summary,
        output_help="Output path for the exported root summary.",
    )
    _add_optional_format_argument(
        export_root_summary,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_root_summary.set_defaults(handler=_handle_export_root_summary)

    export_root_champion_report = subparsers.add_parser(
        "export-root-champion-report",
        help="Export the root champion listing as a versioned YAML or JSON artifact.",
    )
    export_root_champion_report.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    export_root_champion_report.add_argument(
        "--track-id",
        action="append",
        default=[],
        help="Repeatable track id filter. Defaults to all tracks with champions.",
    )
    _add_workspace_root_argument(export_root_champion_report)
    _add_required_output_argument(
        export_root_champion_report,
        output_help="Output path for the exported root champion report.",
    )
    _add_optional_format_argument(
        export_root_champion_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_root_champion_report.set_defaults(handler=_handle_export_root_champion_report)

    export_root_report = subparsers.add_parser(
        "export-root-report",
        help="Export a bundled root report with root summary and per-workspace reports.",
    )
    export_root_report.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(export_root_report)
    _add_required_output_argument(
        export_root_report,
        output_help="Output path for the exported root report.",
    )
    _add_optional_format_argument(
        export_root_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_root_report.set_defaults(handler=_handle_export_root_report)

    export_root_bundle = subparsers.add_parser(
        "export-root-bundle",
        help="Export a portable root handoff bundle as a directory.",
    )
    export_root_bundle.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(export_root_bundle)
    _add_required_output_argument(
        export_root_bundle,
        output_help="Output directory for the exported root bundle.",
    )
    _add_optional_format_argument(
        export_root_bundle,
        help_text="Optional structured file format for bundle manifests and reports. Defaults to json.",
    )
    _add_force_argument(
        export_root_bundle,
        help_text="Allow writing into a non-empty output directory.",
    )
    _add_skip_listings_argument(
        export_root_bundle,
        help_text="Omit bundled iteration, record, and promotion listing exports from nested workspace bundles.",
    )
    _add_skip_track_reports_argument(
        export_root_bundle,
        help_text="Omit per-track report files from nested workspace bundles.",
    )
    _add_skip_champions_argument(
        export_root_bundle,
        help_text="Omit champion bundle directories from nested workspace bundles.",
    )
    export_root_bundle.set_defaults(handler=_handle_export_root_bundle)

    export_workspace_report = subparsers.add_parser(
        "export-workspace-report",
        help="Export a bundled workspace report with summaries and per-track rollups.",
    )
    _add_workspace_id_argument(export_workspace_report)
    _add_workspace_root_argument(export_workspace_report)
    _add_required_output_argument(
        export_workspace_report,
        output_help="Output path for the exported workspace report.",
    )
    _add_optional_format_argument(
        export_workspace_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_workspace_report.set_defaults(handler=_handle_export_workspace_report)

    export_workspace_bundle = subparsers.add_parser(
        "export-workspace-bundle",
        help="Export a portable workspace handoff bundle as a directory.",
    )
    _add_workspace_id_argument(export_workspace_bundle)
    _add_workspace_root_argument(export_workspace_bundle)
    _add_required_output_argument(
        export_workspace_bundle,
        output_help="Output directory for the exported workspace bundle.",
    )
    _add_optional_format_argument(
        export_workspace_bundle,
        help_text="Optional structured file format for bundle manifests and reports. Defaults to json.",
    )
    _add_force_argument(
        export_workspace_bundle,
        help_text="Allow writing into a non-empty output directory.",
    )
    _add_skip_listings_argument(
        export_workspace_bundle,
        help_text="Omit the bundled iteration, record, and promotion listing exports.",
    )
    _add_skip_track_reports_argument(
        export_workspace_bundle,
        help_text="Omit the per-track report files under tracks/<track>/.",
    )
    _add_skip_champions_argument(
        export_workspace_bundle,
        help_text="Omit champion bundle directories for tracks with champions.",
    )
    export_workspace_bundle.set_defaults(handler=_handle_export_workspace_bundle)

    show_workspace = subparsers.add_parser(
        "show-workspace",
        help="Show the pinned workspace config and current state.",
    )
    _add_workspace_id_argument(show_workspace)
    _add_workspace_root_argument(show_workspace)
    _add_json_output_arguments(
        show_workspace,
        json_help="Print the raw workspace config JSON with state summary.",
        output_help="Optional path to write the workspace config JSON.",
    )
    show_workspace.set_defaults(handler=_handle_show_workspace)

    show_tracks = subparsers.add_parser(
        "show-tracks",
        help="Show all tracks for one workspace.",
    )
    _add_workspace_id_argument(show_tracks)
    _add_workspace_root_argument(show_tracks)
    _add_json_output_arguments(
        show_tracks,
        json_help="Print the raw track list JSON.",
        output_help="Optional path to write the track list JSON.",
    )
    show_tracks.set_defaults(handler=_handle_show_tracks)

    show_iteration = subparsers.add_parser(
        "show-iteration",
        help="Show one iteration artifact bundle for a workspace.",
    )
    _add_workspace_id_argument(show_iteration)
    _add_required_iteration_id_argument(show_iteration)
    _add_workspace_root_argument(show_iteration)
    _add_json_output_arguments(
        show_iteration,
        json_help="Print the raw iteration artifact JSON.",
        output_help="Optional path to write the iteration artifact JSON.",
    )
    show_iteration.set_defaults(handler=_handle_show_iteration)

    show_track_summary = subparsers.add_parser(
        "show-track-summary",
        help="Show record, promotion, and champion summary for one track.",
    )
    _add_workspace_id_argument(show_track_summary)
    _add_optional_track_selection_argument(show_track_summary)
    _add_workspace_root_argument(show_track_summary)
    _add_json_output_arguments(
        show_track_summary,
        json_help="Print the raw track summary JSON.",
        output_help="Optional path to write the track summary JSON.",
    )
    show_track_summary.set_defaults(handler=_handle_show_track_summary)

    export_track_summary = subparsers.add_parser(
        "export-track-summary",
        help="Export the track summary as a versioned YAML or JSON artifact.",
    )
    _add_workspace_id_argument(export_track_summary)
    _add_optional_track_selection_argument(export_track_summary)
    _add_workspace_root_argument(export_track_summary)
    _add_required_output_argument(
        export_track_summary,
        output_help="Output path for the exported track summary.",
    )
    _add_optional_format_argument(
        export_track_summary,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_track_summary.set_defaults(handler=_handle_export_track_summary)

    export_track_report = subparsers.add_parser(
        "export-track-report",
        help="Export a bundled track report with summary, policy, and artifact views.",
    )
    _add_workspace_id_argument(export_track_report)
    _add_optional_track_selection_argument(export_track_report)
    _add_workspace_root_argument(export_track_report)
    _add_required_output_argument(
        export_track_report,
        output_help="Output path for the exported track report.",
    )
    _add_optional_format_argument(
        export_track_report,
        help_text="Optional explicit output format. Defaults to YAML unless the output ends in .json.",
    )
    export_track_report.set_defaults(handler=_handle_export_track_report)

    export_track_bundle = subparsers.add_parser(
        "export-track-bundle",
        help="Export a portable track handoff bundle as a directory.",
    )
    _add_workspace_id_argument(export_track_bundle)
    _add_optional_track_selection_argument(export_track_bundle)
    _add_workspace_root_argument(export_track_bundle)
    _add_required_output_argument(
        export_track_bundle,
        output_help="Output directory for the exported track bundle.",
    )
    _add_optional_format_argument(
        export_track_bundle,
        help_text="Optional structured file format for bundle manifests and reports. Defaults to json.",
    )
    _add_force_argument(
        export_track_bundle,
        help_text="Allow writing into a non-empty output directory.",
    )
    _add_skip_listings_argument(
        export_track_bundle,
        help_text="Omit the bundled track-scoped iteration, record, and promotion listing exports.",
    )
    _add_skip_champion_argument(
        export_track_bundle,
        help_text="Omit the champion bundle directory even when the track has a champion.",
    )
    export_track_bundle.set_defaults(handler=_handle_export_track_bundle)

    show_track_artifacts = subparsers.add_parser(
        "show-track-artifacts",
        help="Show concrete artifact paths for one workspace track.",
    )
    _add_workspace_id_argument(show_track_artifacts)
    _add_optional_track_selection_argument(show_track_artifacts)
    _add_workspace_root_argument(show_track_artifacts)
    _add_json_output_arguments(
        show_track_artifacts,
        json_help="Print the raw track artifact listing JSON.",
        output_help="Optional path to write the track artifact listing JSON.",
    )
    show_track_artifacts.set_defaults(handler=_handle_show_track_artifacts)

    show_record = subparsers.add_parser(
        "show-record",
        help="Show one benchmark record for a workspace track.",
    )
    _add_workspace_id_argument(show_record)
    _add_required_record_id_argument(show_record)
    _add_optional_track_selection_argument(show_record)
    _add_workspace_root_argument(show_record)
    _add_json_output_arguments(
        show_record,
        json_help="Print the raw record JSON with the resolved record path.",
        output_help="Optional path to write the record JSON.",
    )
    show_record.set_defaults(handler=_handle_show_record)

    show_promotion = subparsers.add_parser(
        "show-promotion",
        help="Show one promotion record for a workspace track.",
    )
    _add_workspace_id_argument(show_promotion)
    _add_required_promotion_id_argument(show_promotion)
    _add_optional_track_selection_argument(show_promotion)
    _add_workspace_root_argument(show_promotion)
    _add_json_output_arguments(
        show_promotion,
        json_help="Print the raw promotion JSON with resolved artifact paths.",
        output_help="Optional path to write the promotion JSON.",
    )
    show_promotion.set_defaults(handler=_handle_show_promotion)

    show_promotion_policy = subparsers.add_parser(
        "show-promotion-policy",
        help="Show the pinned promotion policy for one workspace track.",
    )
    _add_workspace_id_argument(show_promotion_policy)
    _add_optional_track_selection_argument(show_promotion_policy)
    _add_workspace_root_argument(show_promotion_policy)
    _add_json_output_arguments(
        show_promotion_policy,
        json_help="Print the raw promotion policy JSON.",
        output_help="Optional path to write the promotion policy JSON.",
    )
    show_promotion_policy.set_defaults(handler=_handle_show_promotion_policy)

    show_track_policy = subparsers.add_parser(
        "show-track-policy",
        help="Show the pinned benchmark routing policy for one workspace track.",
    )
    _add_workspace_id_argument(show_track_policy)
    _add_optional_track_selection_argument(show_track_policy)
    _add_workspace_root_argument(show_track_policy)
    _add_json_output_arguments(
        show_track_policy,
        json_help="Print the raw track policy JSON.",
        output_help="Optional path to write the track policy JSON.",
    )
    show_track_policy.set_defaults(handler=_handle_show_track_policy)

    show_track = subparsers.add_parser(
        "show-track",
        help="Show the pinned track config for one workspace track.",
    )
    _add_workspace_id_argument(show_track)
    _add_optional_track_selection_argument(show_track)
    _add_workspace_root_argument(show_track)
    _add_json_output_arguments(
        show_track,
        json_help="Print the raw track config JSON.",
        output_help="Optional path to write the track config JSON.",
    )
    show_track.set_defaults(handler=_handle_show_track)

    show_event_log = subparsers.add_parser(
        "show-event-log",
        help="Show the append-only event log for one workspace.",
    )
    _add_workspace_id_argument(show_event_log)
    _add_optional_track_selection_argument(show_event_log)
    _add_workspace_root_argument(show_event_log)
    show_event_log.add_argument(
        "--campaign-id",
        default=None,
        help="Optional campaign id filter.",
    )
    show_event_log.add_argument(
        "--event-type",
        default=None,
        help="Optional event type filter.",
    )
    show_event_log.add_argument(
        "--since",
        default=None,
        help="Optional inclusive lower timestamp bound.",
    )
    show_event_log.add_argument(
        "--until",
        default=None,
        help="Optional inclusive upper timestamp bound.",
    )
    show_event_log.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on how many events to return.",
    )
    _add_json_output_arguments(
        show_event_log,
        json_help="Print the filtered event log payload as JSON.",
        output_help="Optional path to write the filtered event log payload JSON.",
    )
    show_event_log.set_defaults(handler=_handle_show_event_log)

    tail_campaign_events = subparsers.add_parser(
        "tail-campaign-events",
        help="Show the latest events for one campaign run.",
    )
    _add_workspace_id_argument(tail_campaign_events)
    _add_optional_track_selection_argument(tail_campaign_events)
    _add_workspace_root_argument(tail_campaign_events)
    tail_campaign_events.add_argument("--campaign-id", required=True)
    tail_campaign_events.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many recent campaign events to return. Default: 20.",
    )
    _add_json_output_arguments(
        tail_campaign_events,
        json_help="Print the recent campaign event payload as JSON.",
        output_help="Optional path to write the recent campaign event payload JSON.",
    )
    tail_campaign_events.set_defaults(handler=_handle_tail_campaign_events)

    show_event_metrics = subparsers.add_parser(
        "show-event-metrics",
        help="Aggregate event log metrics across one or more workspaces.",
    )
    show_event_metrics.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_optional_track_selection_argument(show_event_metrics)
    _add_workspace_root_argument(show_event_metrics)
    show_event_metrics.add_argument(
        "--event-type",
        default=None,
        help="Optional event type filter.",
    )
    show_event_metrics.add_argument(
        "--since",
        default=None,
        help="Optional inclusive lower timestamp bound.",
    )
    show_event_metrics.add_argument(
        "--until",
        default=None,
        help="Optional inclusive upper timestamp bound.",
    )
    _add_json_output_arguments(
        show_event_metrics,
        json_help="Print the aggregated event metrics payload as JSON.",
        output_help="Optional path to write the aggregated event metrics payload JSON.",
    )
    show_event_metrics.set_defaults(handler=_handle_show_event_metrics)

    show_root_memory = subparsers.add_parser(
        "show-root-memory",
        help="Show or rebuild the cross-workspace root-memory summary.",
    )
    show_root_memory.add_argument(
        "--workspace-id",
        action="append",
        default=[],
        help="Repeatable workspace id filter. Defaults to all workspaces found under --root.",
    )
    _add_workspace_root_argument(show_root_memory)
    show_root_memory.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild the root-memory payload from current champion artifacts before showing it.",
    )
    _add_json_output_arguments(
        show_root_memory,
        json_help="Print the root-memory payload as JSON.",
        output_help="Optional path to write the root-memory payload JSON.",
    )
    show_root_memory.set_defaults(handler=_handle_show_root_memory)

    show_plugin_catalog = subparsers.add_parser(
        "show-plugin-catalog",
        help="Show dynamically discovered autoharness plugin contributions.",
    )
    _add_json_output_arguments(
        show_plugin_catalog,
        json_help="Print the plugin catalog payload as JSON.",
        output_help="Optional path to write the plugin catalog payload JSON.",
    )
    show_plugin_catalog.set_defaults(handler=_handle_show_plugin_catalog)
