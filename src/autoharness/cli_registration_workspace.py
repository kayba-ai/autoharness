"""Workspace, track, and policy mutation registration."""

from __future__ import annotations

from pathlib import Path

from .cli_arguments import (
    DEFAULT_SETTINGS_PATH,
    DEFAULT_WORKSPACES_ROOT,
    _add_benchmark_argument,
    _add_campaign_policy_update_arguments,
    _add_clear_notes_argument,
    _add_confirm_track_id_argument,
    _add_confirm_workspace_id_argument,
    _add_domain_argument,
    _add_force_argument,
    _add_json_output_arguments,
    _add_kind_argument,
    _add_notes_argument,
    _add_objective_argument,
    _add_optional_output_argument,
    _add_optional_track_selection_argument,
    _add_required_track_id_argument,
    _add_routing_policy_update_arguments,
    _add_settings_path_argument,
    _add_track_evaluator_arguments,
    _add_workspace_id_argument,
    _add_workspace_root_argument,
)
from .workspace_handlers import (
    _handle_archive_track,
    _handle_archive_workspace,
    _handle_create_track,
    _handle_init_workspace,
    _handle_prune_artifacts,
    _handle_set_provider_profile,
    _handle_set_retention_policy,
    _handle_purge_track,
    _handle_purge_workspace,
    _handle_set_promotion_policy,
    _handle_set_track,
    _handle_set_track_policy,
    _handle_set_workspace,
    _handle_setup,
    _handle_show_provider_profile,
    _handle_show_retention_policy,
    _handle_switch_track,
)


def register_workspace_parsers(subparsers) -> None:
    setup = subparsers.add_parser("setup", help="Write operator autonomy settings.")
    setup.add_argument(
        "--autonomy",
        choices=("proposal", "bounded", "full"),
        default="full",
        help="How much authority the meta-agent gets. Default: full.",
    )
    setup.add_argument(
        "--editable-surface",
        action="append",
        default=[],
        help="Path that the agent may edit directly. Repeatable.",
    )
    setup.add_argument(
        "--protected-surface",
        action="append",
        default=[],
        help="Path that stays proposal-only. Repeatable.",
    )
    setup.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_SETTINGS_PATH,
        help="Where to write the settings file.",
    )
    _add_force_argument(
        setup,
        help_text="Overwrite an existing settings file.",
    )
    setup.set_defaults(handler=_handle_setup)

    set_workspace = subparsers.add_parser(
        "set-workspace",
        help="Update workspace-level metadata plus fallback benchmark and campaign policy.",
    )
    _add_workspace_id_argument(set_workspace)
    _add_workspace_root_argument(set_workspace)
    _add_objective_argument(set_workspace, default=None)
    _add_domain_argument(set_workspace, default=None)
    set_workspace.add_argument("--active-track-id", default=None)
    _add_routing_policy_update_arguments(
        set_workspace,
        benchmark_help="Set search, promotion, and regression fallback benchmarks to the same value.",
        preset_help="Set search, promotion, and regression fallback presets to the same value.",
        clear_preset_help="Clear search, promotion, and regression fallback presets.",
        clear_search_preset_help="Clear the search fallback preset.",
        clear_promotion_preset_help="Clear the promotion fallback preset.",
        clear_regression_preset_help="Clear the regression fallback preset.",
    )
    _add_campaign_policy_update_arguments(set_workspace)
    _add_notes_argument(set_workspace, default=None)
    _add_clear_notes_argument(
        set_workspace,
        help_text="Clear the workspace notes field.",
    )
    _add_optional_output_argument(
        set_workspace,
        output_help="Optional path to write the updated workspace config JSON.",
    )
    set_workspace.set_defaults(handler=_handle_set_workspace)

    archive_workspace = subparsers.add_parser(
        "archive-workspace",
        help="Archive one workspace without deleting its history.",
    )
    _add_workspace_id_argument(archive_workspace)
    _add_workspace_root_argument(archive_workspace)
    _add_optional_output_argument(
        archive_workspace,
        output_help="Optional path to write the archive result JSON.",
    )
    archive_workspace.set_defaults(handler=_handle_archive_workspace)

    purge_workspace = subparsers.add_parser(
        "purge-workspace",
        help="Permanently remove one archived workspace and all of its history.",
    )
    _add_workspace_id_argument(purge_workspace)
    _add_workspace_root_argument(purge_workspace)
    _add_confirm_workspace_id_argument(purge_workspace)
    _add_optional_output_argument(
        purge_workspace,
        output_help="Optional path to write the purge result JSON.",
    )
    purge_workspace.set_defaults(handler=_handle_purge_workspace)

    create_track = subparsers.add_parser(
        "create-track",
        help="Create a new track inside one workspace.",
    )
    _add_workspace_id_argument(create_track)
    _add_required_track_id_argument(create_track)
    _add_workspace_root_argument(create_track)
    create_track.add_argument(
        "--from-track",
        default=None,
        help="Optional source track to clone evaluator defaults from. Defaults to the active track.",
    )
    _add_benchmark_argument(create_track, default=None)
    _add_objective_argument(create_track, default=None)
    _add_kind_argument(create_track, default=None)
    create_track.add_argument(
        "--benchmark-reference-id",
        action="append",
        default=None,
        help="Optional replacement benchmark reference ids for the new track.",
    )
    _add_notes_argument(create_track, default=None)
    _add_track_evaluator_arguments(create_track)
    create_track.add_argument(
        "--activate",
        action="store_true",
        help="Make the new track active immediately.",
    )
    _add_optional_output_argument(
        create_track,
        output_help="Optional path to write the created track JSON.",
    )
    create_track.set_defaults(handler=_handle_create_track)

    archive_track = subparsers.add_parser(
        "archive-track",
        help="Archive a track and optionally switch the active track.",
    )
    _add_workspace_id_argument(archive_track)
    _add_required_track_id_argument(archive_track)
    _add_workspace_root_argument(archive_track)
    archive_track.add_argument(
        "--activate-track-id",
        default=None,
        help="Optional replacement active track when archiving the current active track.",
    )
    _add_optional_output_argument(
        archive_track,
        output_help="Optional path to write the archive result JSON.",
    )
    archive_track.set_defaults(handler=_handle_archive_track)

    purge_track = subparsers.add_parser(
        "purge-track",
        help="Permanently remove one archived track and its recorded history.",
    )
    _add_workspace_id_argument(purge_track)
    _add_required_track_id_argument(purge_track)
    _add_workspace_root_argument(purge_track)
    _add_confirm_track_id_argument(purge_track)
    _add_optional_output_argument(
        purge_track,
        output_help="Optional path to write the purge result JSON.",
    )
    purge_track.set_defaults(handler=_handle_purge_track)

    switch_track = subparsers.add_parser(
        "switch-track",
        help="Switch the active track for one workspace.",
    )
    _add_workspace_id_argument(switch_track)
    _add_required_track_id_argument(switch_track)
    _add_workspace_root_argument(switch_track)
    _add_optional_output_argument(
        switch_track,
        output_help="Optional path to write the switch result JSON.",
    )
    switch_track.set_defaults(handler=_handle_switch_track)

    set_promotion_policy = subparsers.add_parser(
        "set-promotion-policy",
        help="Update the pinned promotion policy for one workspace track.",
    )
    _add_workspace_id_argument(set_promotion_policy)
    _add_optional_track_selection_argument(set_promotion_policy)
    _add_workspace_root_argument(set_promotion_policy)
    set_promotion_policy.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer", "none"),
        default=None,
        help="Pinned comparison stage. Use `none` to clear it.",
    )
    set_promotion_policy.add_argument("--min-success-rate", type=float, default=None)
    set_promotion_policy.add_argument(
        "--clear-min-success-rate",
        action="store_true",
        help="Clear the pinned minimum success rate.",
    )
    set_promotion_policy.add_argument("--min-improvement", type=float, default=None)
    set_promotion_policy.add_argument(
        "--clear-min-improvement",
        action="store_true",
        help="Clear the pinned improvement margin.",
    )
    set_promotion_policy.add_argument("--max-regressed-tasks", type=int, default=None)
    set_promotion_policy.add_argument(
        "--clear-max-regressed-tasks",
        action="store_true",
        help="Clear the pinned regressed-task count limit.",
    )
    set_promotion_policy.add_argument(
        "--max-regressed-task-fraction",
        type=float,
        default=None,
    )
    set_promotion_policy.add_argument(
        "--clear-max-regressed-task-fraction",
        action="store_true",
        help="Clear the pinned regressed-task fraction limit.",
    )
    set_promotion_policy.add_argument(
        "--max-regressed-task-weight",
        type=float,
        default=None,
    )
    set_promotion_policy.add_argument(
        "--clear-max-regressed-task-weight",
        action="store_true",
        help="Clear the pinned regressed-task weight limit.",
    )
    set_promotion_policy.add_argument(
        "--max-regressed-task-weight-fraction",
        type=float,
        default=None,
    )
    set_promotion_policy.add_argument(
        "--clear-max-regressed-task-weight-fraction",
        action="store_true",
        help="Clear the pinned regressed-task weight fraction limit.",
    )
    set_promotion_policy.add_argument("--task-regression-margin", type=float, default=None)
    set_promotion_policy.add_argument(
        "--clear-task-regression-margin",
        action="store_true",
        help="Clear the pinned task regression margin.",
    )
    _add_notes_argument(set_promotion_policy, default=None)
    _add_clear_notes_argument(
        set_promotion_policy,
        help_text="Clear the policy notes field.",
    )
    _add_optional_output_argument(
        set_promotion_policy,
        output_help="Optional path to write the updated promotion policy JSON.",
    )
    set_promotion_policy.set_defaults(handler=_handle_set_promotion_policy)

    set_track_policy = subparsers.add_parser(
        "set-track-policy",
        help="Update the pinned benchmark routing policy for one workspace track.",
    )
    _add_workspace_id_argument(set_track_policy)
    _add_optional_track_selection_argument(set_track_policy)
    _add_workspace_root_argument(set_track_policy)
    _add_routing_policy_update_arguments(
        set_track_policy,
        benchmark_help="Set search, promotion, and regression benchmark targets to the same value.",
        preset_help="Set search, promotion, and regression presets to the same value.",
        clear_preset_help="Clear search, promotion, and regression presets.",
        clear_search_preset_help="Clear the search preset.",
        clear_promotion_preset_help="Clear the promotion preset.",
        clear_regression_preset_help="Clear the regression preset.",
    )
    _add_notes_argument(set_track_policy, default=None)
    _add_optional_output_argument(
        set_track_policy,
        output_help="Optional path to write the updated track policy JSON.",
    )
    set_track_policy.set_defaults(handler=_handle_set_track_policy)

    set_track = subparsers.add_parser(
        "set-track",
        help="Update the pinned track config and campaign policy override for one workspace track.",
    )
    _add_workspace_id_argument(set_track)
    _add_optional_track_selection_argument(set_track)
    _add_workspace_root_argument(set_track)
    _add_objective_argument(set_track, default=None)
    _add_kind_argument(set_track, default=None)
    set_track.add_argument(
        "--benchmark-reference-id",
        action="append",
        default=None,
        help="Replace the track benchmark reference ids with the provided values.",
    )
    set_track.add_argument(
        "--clear-benchmark-reference-ids",
        action="store_true",
        help="Clear the track benchmark reference ids.",
    )
    _add_notes_argument(set_track, default=None)
    _add_clear_notes_argument(
        set_track,
        help_text="Clear the track notes field.",
    )
    _add_campaign_policy_update_arguments(set_track)
    _add_track_evaluator_arguments(set_track)
    _add_optional_output_argument(
        set_track,
        output_help="Optional path to write the updated track config JSON.",
    )
    set_track.set_defaults(handler=_handle_set_track)

    show_provider_profile = subparsers.add_parser(
        "show-provider-profile",
        help="Show the persisted provider profile overrides for one workspace track.",
    )
    _add_workspace_id_argument(show_provider_profile)
    _add_optional_track_selection_argument(show_provider_profile)
    _add_workspace_root_argument(show_provider_profile)
    show_provider_profile.add_argument(
        "--provider-id",
        default=None,
        help="Optional provider or generator id to show. Defaults to all stored profiles.",
    )
    _add_json_output_arguments(
        show_provider_profile,
        json_help="Print the provider profile payload as JSON.",
        output_help="Optional path to write the provider profile payload JSON.",
    )
    show_provider_profile.set_defaults(handler=_handle_show_provider_profile)

    set_provider_profile = subparsers.add_parser(
        "set-provider-profile",
        help="Create or update one provider profile override for a workspace track.",
    )
    _add_workspace_id_argument(set_provider_profile)
    _add_optional_track_selection_argument(set_provider_profile)
    _add_workspace_root_argument(set_provider_profile)
    set_provider_profile.add_argument(
        "--provider-id",
        required=True,
        help="Provider or generator id to update.",
    )
    set_provider_profile.add_argument(
        "--option",
        action="append",
        default=[],
        help="Repeatable KEY=VALUE assignment for the provider profile payload.",
    )
    set_provider_profile.add_argument(
        "--clear-option",
        action="append",
        default=[],
        help="Repeatable option key to remove from the provider profile.",
    )
    set_provider_profile.add_argument(
        "--clear",
        action="store_true",
        help="Clear the existing provider profile before applying any new --option values.",
    )
    _add_json_output_arguments(
        set_provider_profile,
        json_help="Print the updated provider profile payload as JSON.",
        output_help="Optional path to write the updated provider profile payload JSON.",
    )
    set_provider_profile.set_defaults(handler=_handle_set_provider_profile)

    show_retention_policy = subparsers.add_parser(
        "show-retention-policy",
        help="Show the workspace retention policy used for campaign and artifact pruning.",
    )
    _add_workspace_id_argument(show_retention_policy)
    _add_workspace_root_argument(show_retention_policy)
    _add_json_output_arguments(
        show_retention_policy,
        json_help="Print the retention policy payload as JSON.",
        output_help="Optional path to write the retention policy payload JSON.",
    )
    show_retention_policy.set_defaults(handler=_handle_show_retention_policy)

    set_retention_policy = subparsers.add_parser(
        "set-retention-policy",
        help="Update the workspace retention policy used for campaign and artifact pruning.",
    )
    _add_workspace_id_argument(set_retention_policy)
    _add_workspace_root_argument(set_retention_policy)
    set_retention_policy.add_argument(
        "--keep-latest-campaign-runs",
        type=int,
        default=None,
        help="How many recent campaign run files to retain per track.",
    )
    set_retention_policy.add_argument(
        "--prune-failed-candidate-patches-older-than-days",
        type=int,
        default=None,
        help="Age cutoff in days for pruning failed candidate patch files.",
    )
    set_retention_policy.add_argument(
        "--keep-champion-campaigns-forever",
        action="store_const",
        const=True,
        default=None,
        help="Always retain campaign runs that produced or contain champions.",
    )
    set_retention_policy.add_argument(
        "--no-keep-champion-campaigns-forever",
        dest="keep_champion_campaigns_forever",
        action="store_const",
        const=False,
        help="Allow champion-producing campaign runs to be pruned like other runs.",
    )
    _add_json_output_arguments(
        set_retention_policy,
        json_help="Print the updated retention policy payload as JSON.",
        output_help="Optional path to write the updated retention policy payload JSON.",
    )
    set_retention_policy.set_defaults(handler=_handle_set_retention_policy)

    prune_artifacts = subparsers.add_parser(
        "prune-artifacts",
        help="Apply the workspace retention policy to campaign files and failed candidate patches.",
    )
    _add_workspace_id_argument(prune_artifacts)
    _add_optional_track_selection_argument(prune_artifacts)
    _add_workspace_root_argument(prune_artifacts)
    prune_artifacts.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the paths that would be pruned without deleting anything.",
    )
    _add_json_output_arguments(
        prune_artifacts,
        json_help="Print the prune result payload as JSON.",
        output_help="Optional path to write the prune result payload JSON.",
    )
    prune_artifacts.set_defaults(handler=_handle_prune_artifacts)

    init_workspace = subparsers.add_parser(
        "init-workspace",
        help="Create a new workspace skeleton for one optimization effort.",
    )
    _add_workspace_id_argument(init_workspace)
    _add_objective_argument(init_workspace, required=True)
    _add_benchmark_argument(init_workspace, required=True)
    _add_domain_argument(
        init_workspace,
        default="general",
        help_text="Human-readable domain label. Default: general.",
    )
    init_workspace.add_argument(
        "--track-id",
        default="main",
        help="Initial track id. Default: main.",
    )
    _add_settings_path_argument(
        init_workspace,
        default=DEFAULT_SETTINGS_PATH,
        help_text="Path to the settings file created by autoharness setup.",
    )
    init_workspace.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_WORKSPACES_ROOT,
        help="Workspace root directory.",
    )
    init_workspace.add_argument(
        "--judge-model",
        default="gpt-4.1-mini",
        help="Pinned judge model for the initial campaign.",
    )
    init_workspace.add_argument(
        "--diagnostic-model",
        default="gpt-4.1-mini",
        help="Pinned diagnostic model for the initial campaign.",
    )
    _add_force_argument(
        init_workspace,
        help_text="Overwrite an existing workspace directory.",
    )
    init_workspace.set_defaults(handler=_handle_init_workspace)
