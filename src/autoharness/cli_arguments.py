"""Shared argparse option specs and parser helper builders."""

from __future__ import annotations

import argparse
from pathlib import Path

from .preflight import available_preflight_checks
from .search import available_search_strategies


DEFAULT_SETTINGS_PATH = Path(".autoharness/settings.yaml")
DEFAULT_WORKSPACES_ROOT = Path(".autoharness/workspaces")


def _argument_spec(*flags: str, **kwargs) -> tuple[tuple[str, ...], dict[str, object]]:
    return flags, kwargs


def _add_argument_specs(
    parser: argparse.ArgumentParser,
    specs: list[tuple[tuple[str, ...], dict[str, object]]],
) -> None:
    for flags, kwargs in specs:
        parser.add_argument(*flags, **kwargs)


def _limit_argument_spec(collection_name: str) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--limit",
        type=int,
        default=None,
        help=f"Optional limit on how many {collection_name} to return.",
    )


def _track_id_argument_spec(collection_name: str) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--track-id",
        default=None,
        help=f"Optional track id to filter the {collection_name} listing.",
    )


def _workspace_id_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--workspace-id", required=True)


def _optional_track_selection_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--track-id", default=None)


def _required_track_id_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--track-id", required=True)


def _workspace_root_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--root",
        type=Path,
        default=DEFAULT_WORKSPACES_ROOT,
        help="Workspace root directory.",
    )


def _stage_argument_spec(collection_name: str) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help=f"Optional stage to filter the {collection_name} listing.",
    )


def _status_argument_spec(collection_name: str) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--status",
        choices=("success", "failed", "inconclusive", "dry_run"),
        default=None,
        help=f"Optional run status to filter the {collection_name} listing.",
    )


def _benchmark_name_argument_spec(
    collection_name: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--benchmark-name",
        default=None,
        help=f"Optional benchmark name to filter the {collection_name} listing.",
    )


def _adapter_id_argument_spec(collection_name: str) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--adapter-id",
        default=None,
        help=f"Optional adapter id to filter the {collection_name} listing.",
    )


def _record_id_argument_spec(collection_name: str) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--record-id",
        default=None,
        help=f"Optional record id to filter the {collection_name} listing.",
    )


def _iteration_id_argument_spec(
    collection_name: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--iteration-id",
        default=None,
        help=f"Optional iteration id to filter the {collection_name} listing.",
    )


def _hypothesis_contains_argument_spec(
    collection_name: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--hypothesis-contains",
        default=None,
        help=(
            "Optional case-insensitive hypothesis substring to filter the "
            f"{collection_name} listing."
        ),
    )


def _notes_contains_argument_spec(collection_name: str) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--notes-contains",
        default=None,
        help=(
            "Optional case-insensitive notes substring to filter the "
            f"{collection_name} listing."
        ),
    )


def _target_root_contains_argument_spec(
    collection_name: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--target-root-contains",
        default=None,
        help=(
            "Optional case-insensitive target root substring to filter the "
            f"{collection_name} listing."
        ),
    )


def _sort_by_argument_spec(
    collection_name: str,
    *,
    choices: tuple[str, ...],
    default: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--sort-by",
        choices=choices,
        default=default,
        help=f"Sort order for the {collection_name} listing. Default: {default}.",
    )


def _descending_argument_spec(
    collection_name: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--descending",
        action="store_true",
        help=f"Reverse the selected {collection_name} sort order.",
    )


def _since_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--since",
        default=None,
        help="Optional inclusive lower timestamp bound. Use YYYY-MM-DD or ISO 8601.",
    )


def _until_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--until",
        default=None,
        help="Optional inclusive upper timestamp bound. Use YYYY-MM-DD or ISO 8601.",
    )


def _saved_plan_only_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--saved-plan-only",
        action="store_true",
        help=help_text,
    )


def _parsed_artifact_sources_only_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--parsed-artifact-sources-only",
        action="store_true",
        help=help_text,
    )


def _json_flag_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--json",
        action="store_true",
        help=help_text,
    )


def _optional_output_path_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--output",
        type=Path,
        default=None,
        help=help_text,
    )


def _required_output_path_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--output",
        type=Path,
        required=True,
        help=help_text,
    )


def _optional_format_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--format",
        choices=("yaml", "json"),
        default=None,
        help=help_text,
    )


def _force_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--force",
        action="store_true",
        help=help_text,
    )


def _skip_listings_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--skip-listings",
        action="store_true",
        help=help_text,
    )


def _skip_track_reports_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--skip-track-reports",
        action="store_true",
        help=help_text,
    )


def _skip_champions_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--skip-champions",
        action="store_true",
        help=help_text,
    )


def _skip_champion_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--skip-champion",
        action="store_true",
        help=help_text,
    )


def _confirm_workspace_id_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--confirm-workspace-id",
        required=True,
        help="Safety check. Must exactly match --workspace-id.",
    )


def _confirm_track_id_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--confirm-track-id",
        required=True,
        help="Safety check. Must exactly match --track-id.",
    )


def _required_record_id_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--record-id", required=True)


def _required_target_root_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--target-root", type=Path, required=True)


def _required_iteration_id_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--iteration-id", required=True)


def _required_promotion_id_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--promotion-id", required=True)


def _required_proposal_id_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--proposal-id", required=True)


def _required_plan_path_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec("--plan", type=Path, required=True, help=help_text)


def _required_adapter_argument_spec(
    help_text: str | None = None,
) -> tuple[tuple[str, ...], dict[str, object]]:
    kwargs: dict[str, object] = {"required": True}
    if help_text is not None:
        kwargs["help"] = help_text
    return _argument_spec("--adapter", **kwargs)


def _benchmark_preset_argument_spec(
    help_text: str,
    *,
    default: str = "default",
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--preset",
        default=default,
        help=help_text,
    )


def _config_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--config",
        type=Path,
        default=None,
        help="Optional YAML or JSON config file for the adapter.",
    )


def _preset_argument_spec(
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--preset",
        default=None,
        help=help_text,
    )


def _inline_set_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--set",
        action="append",
        default=[],
        help="Inline config override using dotted.path=value syntax. Repeatable.",
    )


def _repeat_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--repeat",
        type=int,
        default=None,
        help="How many repeated validation runs to execute. Defaults to the stage policy.",
    )


def _seed_field_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--seed-field",
        default=None,
        help="Optional config field to increment across repeated runs.",
    )


def _seed_start_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--seed-start",
        type=int,
        default=None,
        help="Optional starting seed when using --seed-field.",
    )


def _seed_stride_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--seed-stride",
        type=int,
        default=1,
        help="How much to increment the seed field between repeated runs.",
    )


def _write_config_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--write-config",
        type=Path,
        default=None,
        help="Optional path to write the composed stage-ready config.",
    )


def _write_hypothesis_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--write-hypothesis",
        type=Path,
        default=None,
        help="Optional path to write the planned hypothesis text.",
    )


def _write_command_argument_spec() -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--write-command",
        type=Path,
        default=None,
        help="Optional path to write the suggested shell command as an executable script.",
    )


def _objective_argument_spec(
    *,
    required: bool = False,
    default: str | None = None,
    help_text: str | None = None,
) -> tuple[tuple[str, ...], dict[str, object]]:
    kwargs: dict[str, object] = {}
    if required:
        kwargs["required"] = True
    else:
        kwargs["default"] = default
    if help_text is not None:
        kwargs["help"] = help_text
    return _argument_spec("--objective", **kwargs)


def _benchmark_argument_spec(
    *,
    required: bool = False,
    default: str | None = None,
    help_text: str | None = None,
) -> tuple[tuple[str, ...], dict[str, object]]:
    kwargs: dict[str, object] = {}
    if required:
        kwargs["required"] = True
    else:
        kwargs["default"] = default
    if help_text is not None:
        kwargs["help"] = help_text
    return _argument_spec("--benchmark", **kwargs)


def _domain_argument_spec(
    *,
    default: str | None = None,
    help_text: str | None = None,
) -> tuple[tuple[str, ...], dict[str, object]]:
    kwargs: dict[str, object] = {"default": default}
    if help_text is not None:
        kwargs["help"] = help_text
    return _argument_spec("--domain", **kwargs)


def _kind_argument_spec(
    *,
    default: str | None = None,
    help_text: str | None = None,
) -> tuple[tuple[str, ...], dict[str, object]]:
    kwargs: dict[str, object] = {"default": default}
    if help_text is not None:
        kwargs["help"] = help_text
    return _argument_spec("--kind", **kwargs)


def _settings_path_argument_spec(
    *,
    default: Path = DEFAULT_SETTINGS_PATH,
    help_text: str,
) -> tuple[tuple[str, ...], dict[str, object]]:
    return _argument_spec(
        "--settings",
        type=Path,
        default=default,
        help=help_text,
    )


def _add_workspace_id_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_workspace_id_argument_spec()])


def _add_required_adapter_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str | None = None,
) -> None:
    _add_argument_specs(parser, [_required_adapter_argument_spec(help_text)])


def _add_optional_track_selection_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_optional_track_selection_argument_spec()])


def _add_required_track_id_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_required_track_id_argument_spec()])


def _add_workspace_root_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_workspace_root_argument_spec()])


def _add_optional_output_argument(
    parser: argparse.ArgumentParser,
    *,
    output_help: str,
) -> None:
    _add_argument_specs(
        parser,
        [_optional_output_path_argument_spec(output_help)],
    )


def _add_required_output_argument(
    parser: argparse.ArgumentParser,
    *,
    output_help: str,
) -> None:
    _add_argument_specs(
        parser,
        [_required_output_path_argument_spec(output_help)],
    )


def _add_confirm_workspace_id_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_confirm_workspace_id_argument_spec()])


def _add_confirm_track_id_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_confirm_track_id_argument_spec()])


def _add_required_record_id_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_required_record_id_argument_spec()])


def _add_required_target_root_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_required_target_root_argument_spec()])


def _add_required_iteration_id_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_required_iteration_id_argument_spec()])


def _add_required_promotion_id_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_required_promotion_id_argument_spec()])


def _add_required_proposal_id_argument(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(parser, [_required_proposal_id_argument_spec()])


def _add_required_plan_path_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    _add_argument_specs(parser, [_required_plan_path_argument_spec(help_text)])


def _add_json_output_arguments(
    parser: argparse.ArgumentParser,
    *,
    json_help: str,
    output_help: str,
) -> None:
    _add_argument_specs(
        parser,
        [
            _json_flag_argument_spec(json_help),
            _optional_output_path_argument_spec(output_help),
        ],
    )


def _add_benchmark_preset_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
    default: str = "default",
) -> None:
    _add_argument_specs(
        parser,
        [_benchmark_preset_argument_spec(help_text, default=default)],
    )


def _add_optional_format_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    _add_argument_specs(
        parser,
        [_optional_format_argument_spec(help_text)],
    )


def _add_force_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    _add_argument_specs(parser, [_force_argument_spec(help_text)])


def _add_skip_listings_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    _add_argument_specs(parser, [_skip_listings_argument_spec(help_text)])


def _add_skip_track_reports_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    _add_argument_specs(parser, [_skip_track_reports_argument_spec(help_text)])


def _add_skip_champions_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    _add_argument_specs(parser, [_skip_champions_argument_spec(help_text)])


def _add_skip_champion_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    _add_argument_specs(parser, [_skip_champion_argument_spec(help_text)])


def _add_objective_argument(
    parser: argparse.ArgumentParser,
    *,
    required: bool = False,
    default: str | None = None,
    help_text: str | None = None,
) -> None:
    _add_argument_specs(
        parser,
        [_objective_argument_spec(required=required, default=default, help_text=help_text)],
    )


def _add_benchmark_argument(
    parser: argparse.ArgumentParser,
    *,
    required: bool = False,
    default: str | None = None,
    help_text: str | None = None,
) -> None:
    _add_argument_specs(
        parser,
        [_benchmark_argument_spec(required=required, default=default, help_text=help_text)],
    )


def _add_domain_argument(
    parser: argparse.ArgumentParser,
    *,
    default: str | None = None,
    help_text: str | None = None,
) -> None:
    _add_argument_specs(
        parser,
        [_domain_argument_spec(default=default, help_text=help_text)],
    )


def _add_kind_argument(
    parser: argparse.ArgumentParser,
    *,
    default: str | None = None,
    help_text: str | None = None,
) -> None:
    _add_argument_specs(
        parser,
        [_kind_argument_spec(default=default, help_text=help_text)],
    )


def _add_settings_path_argument(
    parser: argparse.ArgumentParser,
    *,
    default: Path = DEFAULT_SETTINGS_PATH,
    help_text: str,
) -> None:
    _add_argument_specs(
        parser,
        [_settings_path_argument_spec(default=default, help_text=help_text)],
    )


def _add_notes_argument(
    parser: argparse.ArgumentParser,
    *,
    default: str | None,
    help_text: str | None = None,
) -> None:
    kwargs: dict[str, object] = {"default": default}
    if help_text is not None:
        kwargs["help"] = help_text
    parser.add_argument("--notes", **kwargs)


def _add_clear_notes_argument(
    parser: argparse.ArgumentParser,
    *,
    help_text: str,
) -> None:
    parser.add_argument(
        "--clear-notes",
        action="store_true",
        help=help_text,
    )


def _add_track_evaluator_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--evaluator-version", default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--diagnostic-model", default=None)
    parser.add_argument("--max-diagnostic-tasks", type=int, default=None)
    parser.add_argument("--min-judge-pass-rate", type=float, default=None)


def _add_routing_policy_update_arguments(
    parser: argparse.ArgumentParser,
    *,
    benchmark_help: str,
    preset_help: str,
    clear_preset_help: str,
    clear_search_preset_help: str,
    clear_promotion_preset_help: str,
    clear_regression_preset_help: str,
) -> None:
    _add_benchmark_argument(parser, default=None, help_text=benchmark_help)
    parser.add_argument(
        "--preset",
        default=None,
        help=preset_help,
    )
    parser.add_argument("--search-benchmark", default=None)
    parser.add_argument("--promotion-benchmark", default=None)
    parser.add_argument("--regression-benchmark", default=None)
    parser.add_argument("--search-preset", default=None)
    parser.add_argument("--promotion-preset", default=None)
    parser.add_argument("--regression-preset", default=None)
    parser.add_argument(
        "--clear-preset",
        action="store_true",
        help=clear_preset_help,
    )
    parser.add_argument(
        "--clear-search-preset",
        action="store_true",
        help=clear_search_preset_help,
    )
    parser.add_argument(
        "--clear-promotion-preset",
        action="store_true",
        help=clear_promotion_preset_help,
    )
    parser.add_argument(
        "--clear-regression-preset",
        action="store_true",
        help=clear_regression_preset_help,
    )


def _add_campaign_policy_update_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--campaign-stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Set the default campaign stage.",
    )
    parser.add_argument(
        "--campaign-stage-progression",
        choices=("fixed", "advance_on_success", "advance_on_promotion"),
        default=None,
        help="Set the default campaign stage progression mode.",
    )
    parser.add_argument(
        "--clear-campaign-stage",
        action="store_true",
        help="Clear the default campaign stage override.",
    )
    parser.add_argument(
        "--clear-campaign-stage-progression",
        action="store_true",
        help="Clear the default campaign stage progression override.",
    )
    parser.add_argument(
        "--campaign-generator",
        default=None,
        help="Set the default campaign proposal generator id.",
    )
    parser.add_argument(
        "--clear-campaign-generator",
        action="store_true",
        help="Clear the default campaign generator override.",
    )
    parser.add_argument(
        "--campaign-strategy",
        choices=available_search_strategies(),
        default=None,
        help="Set the default campaign strategy id.",
    )
    parser.add_argument(
        "--clear-campaign-strategy",
        action="store_true",
        help="Clear the default campaign strategy override.",
    )
    parser.add_argument(
        "--campaign-beam-width",
        type=int,
        default=None,
        help="Set the default beam width for beam-style campaign strategies.",
    )
    parser.add_argument(
        "--clear-campaign-beam-width",
        action="store_true",
        help="Clear the default campaign beam-width override.",
    )
    parser.add_argument(
        "--campaign-beam-groups",
        type=int,
        default=None,
        help="Set the default number of active beam groups for beam-style campaign strategies.",
    )
    parser.add_argument(
        "--clear-campaign-beam-groups",
        action="store_true",
        help="Clear the default campaign beam-group override.",
    )
    parser.add_argument(
        "--campaign-intervention-class",
        choices=("prompt", "config", "middleware", "source"),
        action="append",
        default=None,
        help="Replace the default campaign intervention-class cycle.",
    )
    parser.add_argument(
        "--clear-campaign-intervention-classes",
        action="store_true",
        help="Clear the default campaign intervention-class cycle.",
    )
    parser.add_argument(
        "--campaign-preflight-check",
        choices=available_preflight_checks(),
        action="append",
        default=None,
        help="Replace default campaign preflight checks with repeatable built-in check ids.",
    )
    parser.add_argument(
        "--clear-campaign-preflight-checks",
        action="store_true",
        help="Clear the default campaign preflight check list.",
    )
    parser.add_argument(
        "--campaign-preflight-command",
        action="append",
        default=None,
        help="Replace default campaign preflight commands with repeatable command strings.",
    )
    parser.add_argument(
        "--clear-campaign-preflight-commands",
        action="store_true",
        help="Clear the default campaign preflight command list.",
    )
    parser.add_argument(
        "--campaign-preflight-timeout-seconds",
        type=int,
        default=None,
        help="Set the default per-command timeout for campaign preflight commands.",
    )
    parser.add_argument(
        "--clear-campaign-preflight-timeout-seconds",
        action="store_true",
        help="Clear the default campaign preflight timeout.",
    )
    parser.add_argument(
        "--campaign-generator-option",
        action="append",
        default=None,
        help="Replace default generator metadata with repeatable key=value entries.",
    )
    parser.add_argument(
        "--clear-campaign-generator-options",
        action="store_true",
        help="Clear the default campaign generator metadata mapping.",
    )
    parser.add_argument("--campaign-max-proposals", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-proposals",
        action="store_true",
        help="Clear the default campaign proposal budget.",
    )
    parser.add_argument("--campaign-max-iterations", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-iterations",
        action="store_true",
        help="Clear the default campaign iteration budget.",
    )
    parser.add_argument("--campaign-max-successes", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-successes",
        action="store_true",
        help="Clear the default campaign success budget.",
    )
    parser.add_argument("--campaign-max-promotions", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-promotions",
        action="store_true",
        help="Clear the default campaign promotion budget.",
    )
    parser.add_argument("--campaign-max-failures", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-failures",
        action="store_true",
        help="Clear the default campaign failure budget.",
    )
    parser.add_argument("--campaign-max-inconclusive", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-inconclusive",
        action="store_true",
        help="Clear the default campaign inconclusive budget.",
    )
    parser.add_argument("--campaign-max-runtime-seconds", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-runtime-seconds",
        action="store_true",
        help="Clear the default campaign wall-clock budget.",
    )
    parser.add_argument("--campaign-max-generation-total-tokens", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-generation-total-tokens",
        action="store_true",
        help="Clear the default campaign generator-token budget.",
    )
    parser.add_argument("--campaign-max-benchmark-total-cost", type=float, default=None)
    parser.add_argument(
        "--clear-campaign-max-benchmark-total-cost",
        action="store_true",
        help="Clear the default campaign benchmark-cost budget.",
    )
    parser.add_argument("--campaign-max-generation-retries", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-generation-retries",
        action="store_true",
        help="Clear the default campaign generation-retry budget.",
    )
    parser.add_argument(
        "--campaign-max-generation-timeout-retries", type=int, default=None
    )
    parser.add_argument(
        "--clear-campaign-max-generation-timeout-retries",
        action="store_true",
        help="Clear the default campaign generation-timeout retry budget.",
    )
    parser.add_argument(
        "--campaign-max-generation-provider-retries", type=int, default=None
    )
    parser.add_argument(
        "--clear-campaign-max-generation-provider-retries",
        action="store_true",
        help="Clear the default campaign provider/network retry budget.",
    )
    parser.add_argument(
        "--campaign-max-generation-provider-transport-retries",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--clear-campaign-max-generation-provider-transport-retries",
        action="store_true",
        help="Clear the default campaign provider-transport retry budget.",
    )
    parser.add_argument(
        "--campaign-max-generation-provider-auth-retries",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--clear-campaign-max-generation-provider-auth-retries",
        action="store_true",
        help="Clear the default campaign provider-auth retry budget.",
    )
    parser.add_argument(
        "--campaign-max-generation-provider-rate-limit-retries",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--clear-campaign-max-generation-provider-rate-limit-retries",
        action="store_true",
        help="Clear the default campaign provider rate-limit retry budget.",
    )
    parser.add_argument(
        "--campaign-max-generation-process-retries", type=int, default=None
    )
    parser.add_argument(
        "--clear-campaign-max-generation-process-retries",
        action="store_true",
        help="Clear the default campaign local generator-process retry budget.",
    )
    parser.add_argument("--campaign-max-preflight-retries", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-preflight-retries",
        action="store_true",
        help="Clear the default campaign preflight retry budget.",
    )
    parser.add_argument("--campaign-max-execution-retries", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-execution-retries",
        action="store_true",
        help="Clear the default campaign execution-retry budget.",
    )
    parser.add_argument(
        "--campaign-max-benchmark-process-retries", type=int, default=None
    )
    parser.add_argument(
        "--clear-campaign-max-benchmark-process-retries",
        action="store_true",
        help="Clear the default campaign benchmark-process retry budget.",
    )
    parser.add_argument(
        "--campaign-max-benchmark-signal-retries", type=int, default=None
    )
    parser.add_argument(
        "--clear-campaign-max-benchmark-signal-retries",
        action="store_true",
        help="Clear the default campaign benchmark-signal retry budget.",
    )
    parser.add_argument(
        "--campaign-max-benchmark-parse-retries", type=int, default=None
    )
    parser.add_argument(
        "--clear-campaign-max-benchmark-parse-retries",
        action="store_true",
        help="Clear the default campaign benchmark-parse retry budget.",
    )
    parser.add_argument(
        "--campaign-max-benchmark-adapter-validation-retries",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--clear-campaign-max-benchmark-adapter-validation-retries",
        action="store_true",
        help="Clear the default campaign benchmark adapter-validation retry budget.",
    )
    parser.add_argument(
        "--campaign-max-benchmark-timeout-retries", type=int, default=None
    )
    parser.add_argument(
        "--clear-campaign-max-benchmark-timeout-retries",
        action="store_true",
        help="Clear the default campaign benchmark-timeout retry budget.",
    )
    parser.add_argument(
        "--campaign-max-benchmark-command-retries", type=int, default=None
    )
    parser.add_argument(
        "--clear-campaign-max-benchmark-command-retries",
        action="store_true",
        help="Clear the default campaign benchmark-command retry budget.",
    )
    parser.add_argument("--campaign-max-inconclusive-retries", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-max-inconclusive-retries",
        action="store_true",
        help="Clear the default campaign inconclusive-retry budget.",
    )
    parser.add_argument("--campaign-no-improvement-limit", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-no-improvement-limit",
        action="store_true",
        help="Clear the default campaign no-improvement limit.",
    )
    parser.add_argument("--campaign-repeat-count", type=int, default=None)
    parser.add_argument(
        "--clear-campaign-repeat-count",
        action="store_true",
        help="Clear the default campaign validation repeat override.",
    )
    parser.add_argument(
        "--campaign-auto-promote",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Set whether campaigns auto-promote successful winners by default.",
    )
    parser.add_argument(
        "--campaign-auto-promote-min-stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=None,
        help="Set the minimum stage that campaign auto-promotion may use.",
    )
    parser.add_argument(
        "--clear-campaign-auto-promote",
        action="store_true",
        help="Clear the default campaign auto-promote override.",
    )
    parser.add_argument(
        "--campaign-allow-flaky-promotion",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Set whether campaigns may auto-promote flaky repeated validations by default.",
    )
    parser.add_argument(
        "--clear-campaign-auto-promote-min-stage",
        action="store_true",
        help="Clear the default campaign auto-promote minimum-stage override.",
    )
    parser.add_argument(
        "--clear-campaign-allow-flaky-promotion",
        action="store_true",
        help="Clear the default flaky-promotion override.",
    )
    parser.add_argument(
        "--campaign-stop-on-first-promotion",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Set whether campaigns stop after the first promotion by default.",
    )
    parser.add_argument(
        "--clear-campaign-stop-on-first-promotion",
        action="store_true",
        help="Clear the default stop-on-first-promotion override.",
    )
    parser.add_argument(
        "--campaign-promotion-target-root",
        type=Path,
        default=None,
        help="Set the default target root for automatic campaign promotions.",
    )
    parser.add_argument(
        "--clear-campaign-promotion-target-root",
        action="store_true",
        help="Clear the default campaign promotion target root override.",
    )


def _add_config_composition_arguments(
    parser: argparse.ArgumentParser,
    *,
    preset_help: str,
) -> None:
    _add_argument_specs(
        parser,
        [
            _config_argument_spec(),
            _preset_argument_spec(preset_help),
            _inline_set_argument_spec(),
        ],
    )


def _add_repeat_seed_arguments(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(
        parser,
        [
            _repeat_argument_spec(),
            _seed_field_argument_spec(),
            _seed_start_argument_spec(),
            _seed_stride_argument_spec(),
        ],
    )


def _add_plan_artifact_write_arguments(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(
        parser,
        [
            _write_config_argument_spec(),
            _write_hypothesis_argument_spec(),
            _write_command_argument_spec(),
        ],
    )


def _add_stage_policy_argument(
    parser: argparse.ArgumentParser,
    *,
    default: str | None,
    help_text: str,
) -> None:
    parser.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default=default,
        help=help_text,
    )


def _add_comparison_gate_arguments(
    parser: argparse.ArgumentParser,
    *,
    comparison_target_label: str,
    min_success_rate_default: float | None,
    min_improvement_default: float | None,
    task_regression_margin_default: float | None,
) -> None:
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=min_success_rate_default,
        help="Optional stage gate override for the minimum success rate.",
    )
    parser.add_argument(
        "--min-improvement",
        type=float,
        default=min_improvement_default,
        help=f"Required improvement margin over the {comparison_target_label} success signal.",
    )
    parser.add_argument(
        "--max-regressed-tasks",
        type=int,
        default=None,
        help=f"Optional ceiling on matched tasks that may regress against the {comparison_target_label}.",
    )
    parser.add_argument(
        "--max-regressed-task-fraction",
        type=float,
        default=None,
        help="Optional ceiling on the fraction of matched tasks that may regress.",
    )
    parser.add_argument(
        "--max-regressed-task-weight",
        type=float,
        default=None,
        help="Optional ceiling on the total weight of matched tasks that may regress.",
    )
    parser.add_argument(
        "--max-regressed-task-weight-fraction",
        type=float,
        default=None,
        help="Optional ceiling on the weighted fraction of matched tasks that may regress.",
    )
    parser.add_argument(
        "--task-regression-margin",
        type=float,
        default=task_regression_margin_default,
        help="How much a task score may drop before it counts as a regression.",
    )


def _add_iteration_query_arguments(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(
        parser,
        [
            _limit_argument_spec("iterations"),
            _track_id_argument_spec("iteration"),
            _stage_argument_spec("iteration"),
            _status_argument_spec("iteration"),
            _benchmark_name_argument_spec("iteration"),
            _adapter_id_argument_spec("iteration"),
            _hypothesis_contains_argument_spec("iteration"),
            _notes_contains_argument_spec("iteration"),
            _sort_by_argument_spec(
                "iteration",
                choices=("created_at", "iteration_id"),
                default="iteration_id",
            ),
            _descending_argument_spec("iteration"),
            _since_argument_spec(),
            _until_argument_spec(),
            _saved_plan_only_argument_spec(
                "Return only iterations replayed from saved plans."
            ),
        ],
    )


def _add_record_query_arguments(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(
        parser,
        [
            _limit_argument_spec("records"),
            _track_id_argument_spec("record"),
            _stage_argument_spec("record"),
            _status_argument_spec("record"),
            _benchmark_name_argument_spec("record"),
            _adapter_id_argument_spec("record"),
            _hypothesis_contains_argument_spec("record"),
            _notes_contains_argument_spec("record"),
            _sort_by_argument_spec(
                "record",
                choices=("created_at", "record_id"),
                default="record_id",
            ),
            _descending_argument_spec("record"),
            _since_argument_spec(),
            _until_argument_spec(),
            _saved_plan_only_argument_spec(
                "Return only records backed by saved plans."
            ),
        ],
    )


def _add_promotion_query_arguments(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(
        parser,
        [
            _limit_argument_spec("promotions"),
            _track_id_argument_spec("promotion"),
            _record_id_argument_spec("promotion"),
            _iteration_id_argument_spec("promotion"),
            _target_root_contains_argument_spec("promotion"),
            _notes_contains_argument_spec("promotion"),
            _sort_by_argument_spec(
                "promotion",
                choices=("created_at", "promotion_id"),
                default="promotion_id",
            ),
            _descending_argument_spec("promotion"),
            _since_argument_spec(),
            _until_argument_spec(),
            _parsed_artifact_sources_only_argument_spec(
                "Return only promotions with parsed artifact source sidecars."
            ),
        ],
    )


def _add_proposal_query_arguments(parser: argparse.ArgumentParser) -> None:
    _add_argument_specs(
        parser,
        [
            _limit_argument_spec("proposals"),
            _track_id_argument_spec("proposal"),
            _stage_argument_spec("proposal"),
            _adapter_id_argument_spec("proposal"),
            _hypothesis_contains_argument_spec("proposal"),
            _notes_contains_argument_spec("proposal"),
            _sort_by_argument_spec(
                "proposal",
                choices=("created_at", "proposal_id"),
                default="proposal_id",
            ),
            _descending_argument_spec("proposal"),
            _since_argument_spec(),
            _until_argument_spec(),
        ],
    )
