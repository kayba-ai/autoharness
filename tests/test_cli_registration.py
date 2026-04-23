from __future__ import annotations

import argparse
from pathlib import Path

from autoharness.cli_registration import register_command_parsers
from autoharness.benchmark_handlers import (
    _handle_show_benchmark_config,
    _handle_validate_benchmark_config,
)
from autoharness.inspection_handlers import (
    _handle_export_root_bundle,
    _handle_export_root_champion_report,
    _handle_export_root_report,
    _handle_export_track_bundle,
    _handle_export_track_report,
    _handle_export_root_summary,
    _handle_export_workspace_bundle,
    _handle_export_workspace_summary,
    _handle_import_bundle,
    _handle_reindex_bundle,
    _handle_show_artifact_file,
    _handle_show_event_log,
    _handle_show_event_metrics,
    _handle_show_plugin_catalog,
    _handle_show_report_file,
    _handle_show_bundle,
    _handle_show_root_champions,
    _handle_show_root_memory,
    _handle_show_root_summary,
    _handle_tail_campaign_events,
    _handle_validate_artifact_file,
    _handle_validate_report_file,
    _handle_validate_bundle,
)
from autoharness.execution_handlers import (
    _handle_list_preflight_checks,
    _handle_run_benchmark,
    _handle_run_iteration,
    _handle_show_preflight_check,
    _handle_show_plan_file,
    _handle_validate_plan_file,
)
from autoharness.listing_handlers import (
    _handle_show_listing_file,
    _handle_show_promotions,
    _handle_validate_listing_file,
)
from autoharness.proposal_handlers import (
    _handle_apply_proposal,
    _handle_generate_proposal,
    _handle_list_generators,
    _handle_run_proposal,
    _handle_show_generator,
    _handle_show_proposals,
)
from autoharness.campaign_handlers import (
    _handle_cancel_campaign,
    _handle_pause_campaign,
    _handle_run_campaign,
    _handle_run_campaign_worker,
    _handle_show_campaigns,
)
from autoharness.campaign_handlers import (
    _handle_export_campaign_bundle,
    _handle_export_campaign_report,
    _handle_export_root_campaign_bundle,
    _handle_export_root_campaign_run_report,
    _handle_export_root_campaign_report,
    _handle_export_workspace_campaign_bundle,
    _handle_export_workspace_campaign_run_report,
    _handle_export_workspace_campaign_report,
    _handle_run_root_campaigns,
    _handle_run_workspace_campaigns,
    _handle_show_campaign_report_file,
    _handle_show_campaign_artifacts,
    _handle_show_root_campaigns,
    _handle_validate_campaign_report_file,
)
from autoharness.promotion_handlers import _handle_compare_to_champion
from autoharness.promotion_handlers import _handle_transfer_root_champions
from autoharness.promotion_handlers import _handle_transfer_champion
from autoharness.workspace_handlers import (
    _handle_prune_artifacts,
    _handle_set_provider_profile,
    _handle_set_retention_policy,
    _handle_set_workspace,
    _handle_show_provider_profile,
    _handle_show_retention_policy,
)


def _stub_run_planned_iteration(args) -> None:  # pragma: no cover - identity only
    raise AssertionError(f"unexpected handler execution: {args}")


def _build_registered_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autoharness")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_command_parsers(
        subparsers,
        run_planned_iteration_handler=_stub_run_planned_iteration,
    )
    return parser


def test_register_command_parsers_wires_run_planned_iteration_handler() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["run-planned-iteration", "--plan", "saved-plan.json"])

    assert args.command == "run-planned-iteration"
    assert args.handler is _stub_run_planned_iteration
    assert args.plan == Path("saved-plan.json")


def test_register_command_parsers_wires_show_plan_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-plan-file", "saved-plan.json"])

    assert args.command == "show-plan-file"
    assert args.handler is _handle_show_plan_file
    assert args.path == Path("saved-plan.json")


def test_register_command_parsers_wires_validate_plan_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["validate-plan-file", "saved-plan.json"])

    assert args.command == "validate-plan-file"
    assert args.handler is _handle_validate_plan_file
    assert args.path == Path("saved-plan.json")


def test_register_command_parsers_wires_list_preflight_checks_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["list-preflight-checks"])

    assert args.command == "list-preflight-checks"
    assert args.handler is _handle_list_preflight_checks


def test_register_command_parsers_wires_show_preflight_check_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-preflight-check", "--check", "python_compile"])

    assert args.command == "show-preflight-check"
    assert args.handler is _handle_show_preflight_check
    assert args.check == "python_compile"


def test_register_command_parsers_wires_run_benchmark_preflight_arguments() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "run-benchmark",
            "--adapter",
            "generic_command",
            "--config",
            "config.yaml",
            "--preflight-check",
            "python_compile",
            "--preflight-command",
            "python -c pass",
            "--preflight-timeout-seconds",
            "15",
        ]
    )

    assert args.command == "run-benchmark"
    assert args.handler is _handle_run_benchmark
    assert args.preflight_check == ["python_compile"]
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 15


def test_register_command_parsers_wires_background_campaign_commands() -> None:
    parser = _build_registered_parser()

    run_args = parser.parse_args(
        [
            "run-campaign",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--config",
            "config.yaml",
            "--target-root",
            "candidate",
            "--background",
        ]
    )
    worker_args = parser.parse_args(["run-campaign-worker", "--worker-id", "worker-a"])
    pause_args = parser.parse_args(
        ["pause-campaign", "--workspace-id", "demo", "--campaign-id", "campaign_run_123"]
    )
    cancel_args = parser.parse_args(
        ["cancel-campaign", "--workspace-id", "demo", "--campaign-id", "campaign_run_123"]
    )

    assert run_args.handler is _handle_run_campaign
    assert run_args.background is True
    assert worker_args.handler is _handle_run_campaign_worker
    assert worker_args.worker_id == "worker-a"
    assert pause_args.handler is _handle_pause_campaign
    assert cancel_args.handler is _handle_cancel_campaign


def test_register_command_parsers_wires_provider_retention_and_event_commands() -> None:
    parser = _build_registered_parser()

    provider_args = parser.parse_args(
        [
            "show-provider-profile",
            "--workspace-id",
            "demo",
            "--provider-id",
            "local_command",
        ]
    )
    set_provider_args = parser.parse_args(
        [
            "set-provider-profile",
            "--workspace-id",
            "demo",
            "--provider-id",
            "local_command",
            "--option",
            "model=gpt-5",
        ]
    )
    retention_args = parser.parse_args(
        ["show-retention-policy", "--workspace-id", "demo"]
    )
    set_retention_args = parser.parse_args(
        [
            "set-retention-policy",
            "--workspace-id",
            "demo",
            "--keep-latest-campaign-runs",
            "4",
        ]
    )
    prune_args = parser.parse_args(["prune-artifacts", "--workspace-id", "demo"])
    event_args = parser.parse_args(["show-event-log", "--workspace-id", "demo"])
    event_metrics_args = parser.parse_args(["show-event-metrics"])
    tail_args = parser.parse_args(
        [
            "tail-campaign-events",
            "--workspace-id",
            "demo",
            "--campaign-id",
            "campaign_run_123",
        ]
    )
    root_memory_args = parser.parse_args(["show-root-memory"])
    plugin_args = parser.parse_args(["show-plugin-catalog"])

    assert provider_args.handler is _handle_show_provider_profile
    assert set_provider_args.handler is _handle_set_provider_profile
    assert retention_args.handler is _handle_show_retention_policy
    assert set_retention_args.handler is _handle_set_retention_policy
    assert prune_args.handler is _handle_prune_artifacts
    assert event_args.handler is _handle_show_event_log
    assert event_metrics_args.handler is _handle_show_event_metrics
    assert tail_args.handler is _handle_tail_campaign_events
    assert root_memory_args.handler is _handle_show_root_memory
    assert plugin_args.handler is _handle_show_plugin_catalog


def test_register_command_parsers_wires_show_benchmark_config_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "show-benchmark-config",
            "--adapter",
            "generic_command",
            "--preset",
            "promotion",
            "--set",
            "timeout_seconds=30",
        ]
    )

    assert args.command == "show-benchmark-config"
    assert args.handler is _handle_show_benchmark_config
    assert args.adapter == "generic_command"
    assert args.preset == "promotion"
    assert args.set == ["timeout_seconds=30"]


def test_register_command_parsers_wires_validate_benchmark_config_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "validate-benchmark-config",
            "--adapter",
            "generic_command",
            "--config",
            "generic.yaml",
            "--stage",
            "holdout",
        ]
    )

    assert args.command == "validate-benchmark-config"
    assert args.handler is _handle_validate_benchmark_config
    assert args.adapter == "generic_command"
    assert args.config == Path("generic.yaml")
    assert args.stage == "holdout"


def test_register_command_parsers_wires_workspace_mutation_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "set-workspace",
            "--workspace-id",
            "demo",
            "--campaign-max-generation-timeout-retries",
            "1",
            "--campaign-max-generation-provider-retries",
            "2",
            "--campaign-max-generation-provider-transport-retries",
            "4",
            "--campaign-max-generation-provider-auth-retries",
            "5",
            "--campaign-max-generation-provider-rate-limit-retries",
            "6",
            "--campaign-max-generation-process-retries",
            "3",
            "--campaign-beam-groups",
            "3",
            "--campaign-max-benchmark-process-retries",
            "7",
            "--campaign-max-benchmark-signal-retries",
            "8",
            "--campaign-max-benchmark-parse-retries",
            "10",
            "--campaign-max-benchmark-adapter-validation-retries",
            "11",
            "--campaign-max-benchmark-timeout-retries",
            "9",
            "--campaign-max-benchmark-command-retries",
            "2",
            "--campaign-max-generation-total-tokens",
            "11",
            "--campaign-max-benchmark-total-cost",
            "1.5",
        ]
    )

    assert args.command == "set-workspace"
    assert args.handler is _handle_set_workspace
    assert args.workspace_id == "demo"
    assert args.active_track_id is None
    assert args.campaign_generator is None
    assert args.campaign_max_generation_timeout_retries == 1
    assert args.campaign_max_generation_provider_retries == 2
    assert args.campaign_max_generation_provider_transport_retries == 4
    assert args.campaign_max_generation_provider_auth_retries == 5
    assert args.campaign_max_generation_provider_rate_limit_retries == 6
    assert args.campaign_max_generation_process_retries == 3
    assert args.campaign_beam_groups == 3
    assert args.campaign_max_benchmark_process_retries == 7
    assert args.campaign_max_benchmark_signal_retries == 8
    assert args.campaign_max_benchmark_parse_retries == 10
    assert args.campaign_max_benchmark_adapter_validation_retries == 11
    assert args.campaign_max_benchmark_timeout_retries == 9
    assert args.campaign_max_benchmark_command_retries == 2
    assert args.campaign_max_generation_total_tokens == 11
    assert args.campaign_max_benchmark_total_cost == 1.5


def test_register_command_parsers_wires_listing_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-promotions", "--workspace-id", "demo"])

    assert args.command == "show-promotions"
    assert args.handler is _handle_show_promotions
    assert args.workspace_id == "demo"
    assert args.sort_by == "promotion_id"


def test_register_command_parsers_wires_show_listing_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-listing-file", "iterations.yaml"])

    assert args.command == "show-listing-file"
    assert args.handler is _handle_show_listing_file
    assert args.path == Path("iterations.yaml")


def test_register_command_parsers_wires_validate_listing_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["validate-listing-file", "iterations.yaml"])

    assert args.command == "validate-listing-file"
    assert args.handler is _handle_validate_listing_file
    assert args.path == Path("iterations.yaml")


def test_register_command_parsers_wires_show_artifact_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-artifact-file", "artifact.json"])

    assert args.command == "show-artifact-file"
    assert args.handler is _handle_show_artifact_file
    assert args.path == Path("artifact.json")


def test_register_command_parsers_wires_validate_artifact_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["validate-artifact-file", "artifact.json"])

    assert args.command == "validate-artifact-file"
    assert args.handler is _handle_validate_artifact_file
    assert args.path == Path("artifact.json")


def test_register_command_parsers_wires_show_report_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-report-file", "workspace-report.yaml"])

    assert args.command == "show-report-file"
    assert args.handler is _handle_show_report_file
    assert args.path == Path("workspace-report.yaml")


def test_register_command_parsers_wires_validate_report_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["validate-report-file", "workspace-report.yaml"])

    assert args.command == "validate-report-file"
    assert args.handler is _handle_validate_report_file
    assert args.path == Path("workspace-report.yaml")


def test_register_command_parsers_wires_show_root_summary_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-root-summary", "--workspace-id", "demo"])

    assert args.command == "show-root-summary"
    assert args.handler is _handle_show_root_summary
    assert args.workspace_id == ["demo"]


def test_register_command_parsers_wires_show_root_champions_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        ["show-root-champions", "--workspace-id", "demo", "--track-id", "main"]
    )

    assert args.command == "show-root-champions"
    assert args.handler is _handle_show_root_champions
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]


def test_register_command_parsers_wires_export_root_summary_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        ["export-root-summary", "--workspace-id", "demo", "--output", "root.yaml"]
    )

    assert args.command == "export-root-summary"
    assert args.handler is _handle_export_root_summary
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root.yaml")


def test_register_command_parsers_wires_export_root_champion_report_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-root-champion-report",
            "--workspace-id",
            "demo",
            "--track-id",
            "main",
            "--output",
            "root-champions.yaml",
        ]
    )

    assert args.command == "export-root-champion-report"
    assert args.handler is _handle_export_root_champion_report
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]
    assert args.output == Path("root-champions.yaml")


def test_register_command_parsers_wires_export_root_report_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        ["export-root-report", "--workspace-id", "demo", "--output", "root-report.yaml"]
    )

    assert args.command == "export-root-report"
    assert args.handler is _handle_export_root_report
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root-report.yaml")


def test_register_command_parsers_wires_export_root_bundle_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        ["export-root-bundle", "--workspace-id", "demo", "--output", "root-bundle"]
    )

    assert args.command == "export-root-bundle"
    assert args.handler is _handle_export_root_bundle
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root-bundle")


def test_register_command_parsers_wires_proposal_generation_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "generate-proposal",
            "--workspace-id",
            "demo",
            "--adapter",
            "pytest",
            "--generator",
            "failure_summary",
            "--intervention-class",
            "source",
        ]
    )

    assert args.command == "generate-proposal"
    assert args.handler is _handle_generate_proposal
    assert args.adapter == "pytest"
    assert args.edit_plan is None
    assert args.generator == "failure_summary"
    assert args.intervention_class == "source"


def test_register_command_parsers_wires_list_generators_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["list-generators"])

    assert args.command == "list-generators"
    assert args.handler is _handle_list_generators


def test_register_command_parsers_wires_show_generator_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-generator", "--generator", "local_command"])

    assert args.command == "show-generator"
    assert args.handler is _handle_show_generator
    assert args.generator == "local_command"


def test_register_command_parsers_wires_proposal_listing_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-proposals", "--workspace-id", "demo"])

    assert args.command == "show-proposals"
    assert args.handler is _handle_show_proposals
    assert args.workspace_id == "demo"
    assert args.sort_by == "proposal_id"


def test_register_command_parsers_wires_apply_proposal_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        ["apply-proposal", "--workspace-id", "demo", "--proposal-id", "proposal_123"]
    )

    assert args.command == "apply-proposal"
    assert args.handler is _handle_apply_proposal
    assert args.proposal_id == "proposal_123"


def test_register_command_parsers_wires_run_proposal_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "run-proposal",
            "--workspace-id",
            "demo",
            "--proposal-id",
            "proposal_123",
            "--repeat",
            "2",
            "--preflight-check",
            "python_compile",
            "--preflight-command",
            "python -c pass",
            "--preflight-timeout-seconds",
            "15",
            "--dry-run",
        ]
    )

    assert args.command == "run-proposal"
    assert args.handler is _handle_run_proposal
    assert args.proposal_id == "proposal_123"
    assert args.repeat == 2
    assert args.preflight_check == ["python_compile"]
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 15
    assert args.dry_run is True


def test_register_command_parsers_wires_run_campaign_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "run-campaign",
            "--workspace-id",
            "demo",
            "--adapter",
            "pytest",
            "--generator",
            "failure_summary",
            "--strategy",
            "beam_interventions",
            "--beam-width",
            "3",
            "--beam-groups",
            "2",
            "--repeat",
            "3",
            "--stage-progression",
            "advance_on_promotion",
            "--intervention-class",
            "config",
            "--preflight-command",
            "python -c pass",
            "--preflight-timeout-seconds",
            "18",
            "--max-iterations",
            "4",
            "--max-successes",
            "3",
            "--max-promotions",
            "1",
            "--max-inconclusive",
            "2",
            "--time-budget-seconds",
            "90",
            "--max-generation-timeout-retries",
            "2",
            "--max-generation-provider-retries",
            "3",
            "--max-generation-provider-transport-retries",
            "5",
            "--max-generation-provider-auth-retries",
            "6",
            "--max-generation-provider-rate-limit-retries",
            "7",
            "--max-generation-process-retries",
            "4",
            "--max-generation-total-tokens",
            "123",
            "--max-preflight-retries",
            "5",
            "--max-execution-retries",
            "1",
            "--max-benchmark-process-retries",
            "8",
            "--max-benchmark-signal-retries",
            "9",
            "--max-benchmark-parse-retries",
            "10",
            "--max-benchmark-adapter-validation-retries",
            "11",
            "--max-benchmark-timeout-retries",
            "6",
            "--max-benchmark-command-retries",
            "2",
            "--max-benchmark-total-cost",
            "1.75",
            "--allow-flaky-promotion",
            "--auto-promote-min-stage",
            "validation",
            "--auto-promote",
        ]
    )

    assert args.command == "run-campaign"
    assert args.handler is _handle_run_campaign
    assert args.adapter == "pytest"
    assert args.edit_plan == []
    assert args.generator == "failure_summary"
    assert args.strategy == "beam_interventions"
    assert args.beam_width == 3
    assert args.beam_groups == 2
    assert args.repeat == 3
    assert args.stage_progression == "advance_on_promotion"
    assert args.intervention_class == ["config"]
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 18
    assert args.max_iterations == 4
    assert args.max_successes == 3
    assert args.max_promotions == 1
    assert args.max_inconclusive == 2
    assert args.time_budget_seconds == 90
    assert args.max_generation_timeout_retries == 2
    assert args.max_generation_provider_retries == 3
    assert args.max_generation_provider_transport_retries == 5
    assert args.max_generation_provider_auth_retries == 6
    assert args.max_generation_provider_rate_limit_retries == 7
    assert args.max_generation_process_retries == 4
    assert args.max_generation_total_tokens == 123
    assert args.max_preflight_retries == 5
    assert args.max_execution_retries == 1
    assert args.max_benchmark_process_retries == 8
    assert args.max_benchmark_signal_retries == 9
    assert args.max_benchmark_parse_retries == 10
    assert args.max_benchmark_adapter_validation_retries == 11
    assert args.max_benchmark_timeout_retries == 6
    assert args.max_benchmark_command_retries == 2
    assert args.max_benchmark_total_cost == 1.75
    assert args.allow_flaky_promotion is True
    assert args.auto_promote_min_stage == "validation"
    assert args.auto_promote is True
    assert args.stop_on_first_promotion is None


def test_register_command_parsers_wires_run_workspace_campaigns_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "run-workspace-campaigns",
            "--workspace-id",
            "demo",
            "--adapter",
            "pytest",
            "--strategy",
            "beam_interventions",
            "--beam-width",
            "2",
            "--beam-groups",
            "3",
            "--repeat",
            "4",
            "--preflight-command",
            "python -c pass",
            "--preflight-timeout-seconds",
            "19",
            "--max-generation-timeout-retries",
            "2",
            "--max-generation-provider-retries",
            "3",
            "--max-generation-provider-transport-retries",
            "5",
            "--max-generation-provider-auth-retries",
            "6",
            "--max-generation-provider-rate-limit-retries",
            "7",
            "--max-generation-process-retries",
            "4",
            "--max-generation-total-tokens",
            "222",
            "--max-preflight-retries",
            "6",
            "--max-benchmark-total-cost",
            "2.25",
            "--allow-flaky-promotion",
            "--track-id",
            "main",
            "--track-id",
            "alt",
            "--target-root-base",
            "targets",
            "--continue-on-failure",
        ]
    )

    assert args.command == "run-workspace-campaigns"
    assert args.handler is _handle_run_workspace_campaigns
    assert args.strategy == "beam_interventions"
    assert args.beam_width == 2
    assert args.beam_groups == 3
    assert args.repeat == 4
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 19
    assert args.max_generation_timeout_retries == 2
    assert args.max_generation_provider_retries == 3
    assert args.max_generation_provider_transport_retries == 5
    assert args.max_generation_provider_auth_retries == 6
    assert args.max_generation_provider_rate_limit_retries == 7
    assert args.max_generation_process_retries == 4
    assert args.max_generation_total_tokens == 222
    assert args.max_preflight_retries == 6
    assert args.max_benchmark_total_cost == 2.25
    assert args.allow_flaky_promotion is True
    assert args.track_id == ["main", "alt"]
    assert args.target_root_base == Path("targets")
    assert args.continue_on_failure is True


def test_register_command_parsers_wires_export_workspace_campaign_run_report_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-workspace-campaign-run-report",
            "--workspace-id",
            "demo",
            "--adapter",
            "pytest",
            "--track-id",
            "main",
            "--output",
            "workspace-run-report.json",
        ]
    )

    assert args.command == "export-workspace-campaign-run-report"
    assert args.handler is _handle_export_workspace_campaign_run_report
    assert args.workspace_id == "demo"
    assert args.track_id == ["main"]
    assert args.output == Path("workspace-run-report.json")


def test_register_command_parsers_wires_run_root_campaigns_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "run-root-campaigns",
            "--adapter",
            "pytest",
            "--workspace-id",
            "demo",
            "--workspace-id",
            "demo_b",
            "--beam-groups",
            "2",
            "--repeat",
            "5",
            "--preflight-command",
            "python -c pass",
            "--preflight-timeout-seconds",
            "21",
            "--max-generation-timeout-retries",
            "3",
            "--max-generation-provider-retries",
            "4",
            "--max-generation-provider-transport-retries",
            "6",
            "--max-generation-provider-auth-retries",
            "7",
            "--max-generation-provider-rate-limit-retries",
            "8",
            "--max-generation-process-retries",
            "5",
            "--max-generation-total-tokens",
            "333",
            "--max-preflight-retries",
            "7",
            "--max-benchmark-total-cost",
            "3.25",
            "--allow-flaky-promotion",
            "--workers",
            "3",
            "--schedule",
            "fifo",
            "--target-root-base",
            "targets",
        ]
    )

    assert args.command == "run-root-campaigns"
    assert args.handler is _handle_run_root_campaigns
    assert args.workspace_id == ["demo", "demo_b"]
    assert args.beam_groups == 2
    assert args.repeat == 5
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 21
    assert args.max_generation_timeout_retries == 3
    assert args.max_generation_provider_retries == 4
    assert args.max_generation_provider_transport_retries == 6
    assert args.max_generation_provider_auth_retries == 7
    assert args.max_generation_provider_rate_limit_retries == 8
    assert args.max_generation_process_retries == 5
    assert args.max_generation_total_tokens == 333
    assert args.max_preflight_retries == 7
    assert args.max_benchmark_total_cost == 3.25
    assert args.allow_flaky_promotion is True
    assert args.workers == 3
    assert args.schedule == "fifo"
    assert args.target_root_base == Path("targets")


def test_register_command_parsers_wires_export_root_campaign_run_report_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-root-campaign-run-report",
            "--workspace-id",
            "demo",
            "--adapter",
            "pytest",
            "--output",
            "root-run-report.yaml",
        ]
    )

    assert args.command == "export-root-campaign-run-report"
    assert args.handler is _handle_export_root_campaign_run_report
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root-run-report.yaml")


def test_register_command_parsers_wires_show_root_campaigns_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "show-root-campaigns",
            "--workspace-id",
            "demo",
            "--track-id",
            "main",
        ]
    )

    assert args.command == "show-root-campaigns"
    assert args.handler is _handle_show_root_campaigns
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]


def test_register_command_parsers_wires_export_root_campaign_report_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-root-campaign-report",
            "--workspace-id",
            "demo",
            "--output",
            "root-report.json",
        ]
    )

    assert args.command == "export-root-campaign-report"
    assert args.handler is _handle_export_root_campaign_report
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root-report.json")


def test_register_command_parsers_wires_show_campaigns_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-campaigns", "--workspace-id", "demo"])

    assert args.command == "show-campaigns"
    assert args.handler is _handle_show_campaigns
    assert args.workspace_id == "demo"


def test_register_command_parsers_wires_show_campaign_report_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-campaign-report-file", "campaign-report.yaml"])

    assert args.command == "show-campaign-report-file"
    assert args.handler is _handle_show_campaign_report_file
    assert args.path == Path("campaign-report.yaml")


def test_register_command_parsers_wires_validate_campaign_report_file_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        ["validate-campaign-report-file", "campaign-report.yaml"]
    )

    assert args.command == "validate-campaign-report-file"
    assert args.handler is _handle_validate_campaign_report_file
    assert args.path == Path("campaign-report.yaml")


def test_register_command_parsers_wires_export_workspace_campaign_report_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-workspace-campaign-report",
            "--workspace-id",
            "demo",
            "--track-id",
            "main",
            "--output",
            "workspace-campaign-report.yaml",
        ]
    )

    assert args.command == "export-workspace-campaign-report"
    assert args.handler is _handle_export_workspace_campaign_report
    assert args.workspace_id == "demo"
    assert args.track_id == "main"
    assert args.output == Path("workspace-campaign-report.yaml")


def test_register_command_parsers_wires_export_workspace_campaign_bundle_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-workspace-campaign-bundle",
            "--workspace-id",
            "demo",
            "--track-id",
            "main",
            "--output",
            "workspace-campaign-bundle",
        ]
    )

    assert args.command == "export-workspace-campaign-bundle"
    assert args.handler is _handle_export_workspace_campaign_bundle
    assert args.workspace_id == "demo"
    assert args.track_id == "main"
    assert args.output == Path("workspace-campaign-bundle")


def test_register_command_parsers_wires_show_campaign_artifacts_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        ["show-campaign-artifacts", "--workspace-id", "demo", "--campaign-id", "campaign_123"]
    )

    assert args.command == "show-campaign-artifacts"
    assert args.handler is _handle_show_campaign_artifacts
    assert args.campaign_id == "campaign_123"


def test_register_command_parsers_wires_export_campaign_report_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-campaign-report",
            "--workspace-id",
            "demo",
            "--campaign-id",
            "campaign_123",
            "--output",
            "campaign.yaml",
        ]
    )

    assert args.command == "export-campaign-report"
    assert args.handler is _handle_export_campaign_report
    assert args.campaign_id == "campaign_123"
    assert args.output == Path("campaign.yaml")


def test_register_command_parsers_wires_export_campaign_bundle_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-campaign-bundle",
            "--workspace-id",
            "demo",
            "--campaign-id",
            "campaign_123",
            "--output",
            "campaign-bundle",
        ]
    )

    assert args.command == "export-campaign-bundle"
    assert args.handler is _handle_export_campaign_bundle
    assert args.campaign_id == "campaign_123"
    assert args.output == Path("campaign-bundle")


def test_register_command_parsers_wires_export_root_campaign_bundle_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-root-campaign-bundle",
            "--workspace-id",
            "demo",
            "--track-id",
            "main",
            "--output",
            "root-campaign-bundle",
        ]
    )

    assert args.command == "export-root-campaign-bundle"
    assert args.handler is _handle_export_root_campaign_bundle
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]
    assert args.output == Path("root-campaign-bundle")


def test_register_command_parsers_wires_execution_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "pytest",
            "--preflight-command",
            "python -c pass",
            "--preflight-timeout-seconds",
            "12",
            "--hypothesis",
            "candidate",
        ]
    )

    assert args.command == "run-iteration"
    assert args.handler is _handle_run_iteration
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 12
    assert args.stage == "screening"
    assert args.hypothesis == "candidate"


def test_register_command_parsers_wires_promotion_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "compare-to-champion",
            "--workspace-id",
            "demo",
            "--record-id",
            "record-1",
        ]
    )

    assert args.command == "compare-to-champion"
    assert args.handler is _handle_compare_to_champion
    assert args.record_id == "record-1"


def test_register_command_parsers_wires_transfer_champion_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "transfer-champion",
            "--source-workspace-id",
            "source",
            "--source-track-id",
            "gold",
            "--workspace-id",
            "dest",
            "--track-id",
            "main",
            "--target-root",
            "deploy",
            "--json",
        ]
    )

    assert args.command == "transfer-champion"
    assert args.handler is _handle_transfer_champion
    assert args.source_workspace_id == "source"
    assert args.source_track_id == "gold"
    assert args.workspace_id == "dest"
    assert args.track_id == "main"
    assert args.target_root == Path("deploy")
    assert args.json is True


def test_register_command_parsers_wires_transfer_root_champions_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "transfer-root-champions",
            "--source-workspace-id",
            "source",
            "--source-track-id",
            "gold",
            "--workspace-id",
            "dest_a",
            "--workspace-id",
            "dest_b",
            "--destination-track-id",
            "main",
            "--target-root-base",
            "deployments",
            "--continue-on-failure",
            "--json",
        ]
    )

    assert args.command == "transfer-root-champions"
    assert args.handler is _handle_transfer_root_champions
    assert args.source_workspace_id == "source"
    assert args.source_track_id == "gold"
    assert args.workspace_id == ["dest_a", "dest_b"]
    assert args.destination_track_id == "main"
    assert args.target_root_base == Path("deployments")
    assert args.continue_on_failure is True
    assert args.json is True


def test_register_command_parsers_wires_summary_export_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-workspace-summary",
            "--workspace-id",
            "demo",
            "--output",
            "workspace-summary.yaml",
        ]
    )

    assert args.command == "export-workspace-summary"
    assert args.handler is _handle_export_workspace_summary
    assert args.output == Path("workspace-summary.yaml")


def test_register_command_parsers_wires_show_bundle_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["show-bundle", "bundle-dir", "--recursive", "--json"])

    assert args.command == "show-bundle"
    assert args.handler is _handle_show_bundle
    assert args.path == Path("bundle-dir")
    assert args.recursive is True
    assert args.json is True


def test_register_command_parsers_wires_validate_bundle_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(["validate-bundle", "bundle-dir", "--recursive", "--json"])

    assert args.command == "validate-bundle"
    assert args.handler is _handle_validate_bundle
    assert args.path == Path("bundle-dir")
    assert args.recursive is True
    assert args.json is True


def test_register_command_parsers_wires_reindex_bundle_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        ["reindex-bundle", "bundle-dir", "--format", "yaml", "--recursive", "--json"]
    )

    assert args.command == "reindex-bundle"
    assert args.handler is _handle_reindex_bundle
    assert args.path == Path("bundle-dir")
    assert args.format == "yaml"
    assert args.recursive is True
    assert args.json is True


def test_register_command_parsers_wires_import_bundle_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "import-bundle",
            "bundle-dir",
            "--output",
            "imported-bundle",
            "--reindex",
            "--verify-source",
            "--allow-invalid",
            "--target-format",
            "yaml",
            "--recursive",
            "--dry-run",
            "--json",
        ]
    )

    assert args.command == "import-bundle"
    assert args.handler is _handle_import_bundle
    assert args.path == Path("bundle-dir")
    assert args.output == Path("imported-bundle")
    assert args.reindex is True
    assert args.verify_source is True
    assert args.allow_invalid is True
    assert args.target_format == "yaml"
    assert args.recursive is True
    assert args.dry_run is True
    assert args.json is True


def test_register_command_parsers_wires_track_report_export_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-track-report",
            "--workspace-id",
            "demo",
            "--track-id",
            "alt",
            "--output",
            "track-report.json",
        ]
    )

    assert args.command == "export-track-report"
    assert args.handler is _handle_export_track_report
    assert args.track_id == "alt"
    assert args.output == Path("track-report.json")


def test_register_command_parsers_wires_track_bundle_export_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-track-bundle",
            "--workspace-id",
            "demo",
            "--track-id",
            "alt",
            "--output",
            "track-bundle",
            "--skip-listings",
            "--skip-champion",
        ]
    )

    assert args.command == "export-track-bundle"
    assert args.handler is _handle_export_track_bundle
    assert args.track_id == "alt"
    assert args.output == Path("track-bundle")
    assert args.skip_listings is True
    assert args.skip_champion is True


def test_register_command_parsers_wires_workspace_bundle_export_command() -> None:
    parser = _build_registered_parser()

    args = parser.parse_args(
        [
            "export-workspace-bundle",
            "--workspace-id",
            "demo",
            "--output",
            "workspace-bundle",
            "--skip-track-reports",
            "--skip-champions",
        ]
    )

    assert args.command == "export-workspace-bundle"
    assert args.handler is _handle_export_workspace_bundle
    assert args.output == Path("workspace-bundle")
    assert args.skip_track_reports is True
    assert args.skip_champions is True
