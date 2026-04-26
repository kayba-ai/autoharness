from __future__ import annotations

from pathlib import Path

from autoharness.cli_parser import build_parser


def _stub_run_planned_iteration(args) -> None:  # pragma: no cover - identity only
    raise AssertionError(f"unexpected handler execution: {args}")


def test_build_parser_wires_run_planned_iteration_handler() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["run-planned-iteration", "--plan", "saved-plan.json"])

    assert args.command == "run-planned-iteration"
    assert args.handler is _stub_run_planned_iteration
    assert args.plan == Path("saved-plan.json")


def test_build_parser_top_level_help_surfaces_common_path() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    help_text = parser.format_help()

    assert "Optimize an existing harness repo" in help_text
    assert "Common path:" in help_text
    assert "autoharness guide" in help_text
    assert "autoharness run-benchmark" in help_text
    assert "autoharness optimize" in help_text
    assert "autoharness report" in help_text
    assert "auto-bootstrap missing setup" in help_text


def test_build_parser_parses_global_project_config_and_guide_command() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "--project-config",
            "autoharness.yaml",
            "guide",
            "--target-root",
            "repo",
            "--assistant",
            "codex",
            "--assistant-brief-path",
            "autoharness.codex.md",
        ]
    )

    assert args.project_config == Path("autoharness.yaml")
    assert args.command == "guide"
    assert args.target_root == Path("repo")
    assert args.assistant == "codex"
    assert args.assistant_brief_path == Path("autoharness.codex.md")


def test_build_parser_parses_show_plan_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-plan-file", "saved-plan.json"])

    assert args.command == "show-plan-file"
    assert args.path == Path("saved-plan.json")


def test_build_parser_parses_validate_plan_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["validate-plan-file", "saved-plan.json"])

    assert args.command == "validate-plan-file"
    assert args.path == Path("saved-plan.json")


def test_build_parser_parses_show_preflight_check_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-preflight-check", "--check", "python_compile"])

    assert args.command == "show-preflight-check"
    assert args.check == "python_compile"


def test_build_parser_parses_run_benchmark_preflight_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.preflight_check == ["python_compile"]
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 15


def test_build_parser_parses_preflight_check_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
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
            "--preflight-check",
            "python_compile",
            "--preflight-check",
            "pytest_collect",
        ]
    )

    assert args.command == "run-campaign"
    assert args.preflight_check == ["python_compile", "pytest_collect"]


def test_build_parser_parses_background_campaign_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
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

    assert args.command == "run-campaign"
    assert args.background is True


def test_build_parser_allows_common_commands_without_workspace_id() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    benchmark_args = parser.parse_args(
        [
            "run-benchmark",
            "--config",
            "config.yaml",
        ]
    )
    generate_args = parser.parse_args(
        [
            "generate-proposal",
            "--config",
            "config.yaml",
        ]
    )
    iteration_args = parser.parse_args(
        [
            "run-iteration",
            "--config",
            "config.yaml",
            "--hypothesis",
            "candidate",
        ]
    )
    campaign_args = parser.parse_args(
        [
            "optimize",
            "--config",
            "config.yaml",
        ]
    )
    compare_args = parser.parse_args(
        [
            "compare-to-champion",
            "--record-id",
            "record-1",
        ]
    )

    assert benchmark_args.command == "run-benchmark"
    assert benchmark_args.adapter is None
    assert generate_args.command == "generate-proposal"
    assert generate_args.workspace_id is None
    assert generate_args.adapter is None
    assert iteration_args.command == "run-iteration"
    assert iteration_args.workspace_id is None
    assert iteration_args.adapter is None
    assert campaign_args.command == "optimize"
    assert campaign_args.workspace_id is None
    assert campaign_args.adapter is None
    assert compare_args.command == "compare-to-champion"
    assert compare_args.workspace_id is None


def test_build_parser_parses_init_and_report_aliases() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    init_args = parser.parse_args(["init"])
    report_args = parser.parse_args(["report"])

    assert init_args.command == "init"
    assert init_args.workspace_id is None
    assert init_args.benchmark is None
    assert report_args.command == "report"
    assert report_args.workspace_id is None


def test_build_parser_parses_optimize_alias() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "optimize",
            "--adapter",
            "generic_command",
            "--config",
            "config.yaml",
        ]
    )

    assert args.command == "optimize"
    assert args.workspace_id is None


def test_build_parser_parses_campaign_worker_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "run-campaign-worker",
            "--workspace-id",
            "demo",
            "--track-id",
            "main",
            "--worker-id",
            "worker-a",
            "--lease-seconds",
            "90",
            "--max-campaigns",
            "2",
        ]
    )

    assert args.command == "run-campaign-worker"
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]
    assert args.worker_id == "worker-a"
    assert args.lease_seconds == 90
    assert args.max_campaigns == 2


def test_build_parser_parses_provider_profile_and_retention_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    provider_args = parser.parse_args(
        [
            "set-provider-profile",
            "--workspace-id",
            "demo",
            "--provider-id",
            "local_command",
            "--option",
            "model=gpt-5",
            "--clear-option",
            "temperature",
        ]
    )
    retention_args = parser.parse_args(
        [
            "set-retention-policy",
            "--workspace-id",
            "demo",
            "--keep-latest-campaign-runs",
            "3",
            "--no-keep-champion-campaigns-forever",
        ]
    )

    assert provider_args.command == "set-provider-profile"
    assert provider_args.provider_id == "local_command"
    assert provider_args.option == ["model=gpt-5"]
    assert provider_args.clear_option == ["temperature"]
    assert retention_args.command == "set-retention-policy"
    assert retention_args.keep_latest_campaign_runs == 3
    assert retention_args.keep_champion_campaigns_forever is False


def test_build_parser_parses_event_and_root_memory_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    event_args = parser.parse_args(
        [
            "show-event-log",
            "--workspace-id",
            "demo",
            "--campaign-id",
            "campaign_run_123",
            "--event-type",
            "candidate_completed",
            "--limit",
            "5",
        ]
    )
    memory_args = parser.parse_args(
        [
            "show-root-memory",
            "--workspace-id",
            "demo",
            "--refresh",
        ]
    )

    assert event_args.command == "show-event-log"
    assert event_args.campaign_id == "campaign_run_123"
    assert event_args.event_type == "candidate_completed"
    assert event_args.limit == 5
    assert memory_args.command == "show-root-memory"
    assert memory_args.workspace_id == ["demo"]
    assert memory_args.refresh is True


def test_build_parser_parses_show_benchmark_config_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.adapter == "generic_command"
    assert args.preset == "promotion"
    assert args.set == ["timeout_seconds=30"]
    assert args.stage is None


def test_build_parser_parses_validate_benchmark_config_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.adapter == "generic_command"
    assert args.config == Path("generic.yaml")
    assert args.stage == "holdout"


def test_build_parser_parses_show_root_summary_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-root-summary", "--workspace-id", "demo"])

    assert args.command == "show-root-summary"
    assert args.workspace_id == ["demo"]


def test_build_parser_parses_show_root_champions_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        ["show-root-champions", "--workspace-id", "demo", "--track-id", "main"]
    )

    assert args.command == "show-root-champions"
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]


def test_build_parser_parses_export_root_summary_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        ["export-root-summary", "--workspace-id", "demo", "--output", "root.yaml"]
    )

    assert args.command == "export-root-summary"
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root.yaml")


def test_build_parser_parses_export_root_champion_report_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]
    assert args.output == Path("root-champions.yaml")


def test_build_parser_parses_export_root_report_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        ["export-root-report", "--workspace-id", "demo", "--output", "root-report.yaml"]
    )

    assert args.command == "export-root-report"
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root-report.yaml")


def test_build_parser_parses_export_root_bundle_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        ["export-root-bundle", "--workspace-id", "demo", "--output", "root-bundle"]
    )

    assert args.command == "export-root-bundle"
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root-bundle")


def test_build_parser_parses_workspace_campaign_beam_group_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
            "4",
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
    assert args.workspace_id == "demo"
    assert args.campaign_max_generation_timeout_retries == 1
    assert args.campaign_max_generation_provider_retries == 2
    assert args.campaign_max_generation_provider_transport_retries == 4
    assert args.campaign_max_generation_provider_auth_retries == 5
    assert args.campaign_max_generation_provider_rate_limit_retries == 6
    assert args.campaign_max_generation_process_retries == 3
    assert args.campaign_beam_groups == 4
    assert args.campaign_max_benchmark_process_retries == 7
    assert args.campaign_max_benchmark_signal_retries == 8
    assert args.campaign_max_benchmark_parse_retries == 10
    assert args.campaign_max_benchmark_adapter_validation_retries == 11
    assert args.campaign_max_benchmark_timeout_retries == 9
    assert args.campaign_max_benchmark_command_retries == 2
    assert args.campaign_max_generation_total_tokens == 11
    assert args.campaign_max_benchmark_total_cost == 1.5


def test_build_parser_parses_iteration_listing_defaults() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-iterations", "--workspace-id", "demo"])

    assert args.command == "show-iterations"
    assert args.workspace_id == "demo"
    assert args.track_id is None
    assert args.stage is None
    assert args.status is None
    assert args.limit is None
    assert args.sort_by == "iteration_id"
    assert args.descending is False
    assert args.saved_plan_only is False


def test_build_parser_parses_record_export_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "export-records",
            "--workspace-id",
            "demo",
            "--track-id",
            "alt",
            "--saved-plan-only",
            "--output",
            "records.yaml",
        ]
    )

    assert args.command == "export-records"
    assert args.workspace_id == "demo"
    assert args.track_id == "alt"
    assert args.saved_plan_only is True
    assert args.output == Path("records.yaml")


def test_build_parser_parses_proposal_listing_defaults() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-proposals", "--workspace-id", "demo"])

    assert args.command == "show-proposals"
    assert args.workspace_id == "demo"
    assert args.track_id is None
    assert args.stage is None
    assert args.adapter_id is None
    assert args.limit is None
    assert args.sort_by == "proposal_id"
    assert args.descending is False


def test_build_parser_parses_list_generators_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["list-generators"])

    assert args.command == "list-generators"


def test_build_parser_parses_show_generator_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-generator", "--generator", "local_command"])

    assert args.command == "show-generator"
    assert args.generator == "local_command"


def test_build_parser_parses_run_proposal_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "run-proposal",
            "--workspace-id",
            "demo",
            "--proposal-id",
            "proposal_123",
            "--repeat",
            "2",
            "--preflight-command",
            "python -c pass",
            "--preflight-timeout-seconds",
            "15",
            "--keep-applied-edits",
        ]
    )

    assert args.command == "run-proposal"
    assert args.workspace_id == "demo"
    assert args.proposal_id == "proposal_123"
    assert args.repeat == 2
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 15
    assert args.keep_applied_edits is True


def test_build_parser_parses_transfer_champion_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
            "--notes",
            "handoff",
            "--json",
        ]
    )

    assert args.command == "transfer-champion"
    assert args.source_workspace_id == "source"
    assert args.source_track_id == "gold"
    assert args.workspace_id == "dest"
    assert args.track_id == "main"
    assert args.target_root == Path("deploy")
    assert args.notes == "handoff"
    assert args.json is True


def test_build_parser_parses_transfer_root_champions_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.source_workspace_id == "source"
    assert args.source_track_id == "gold"
    assert args.workspace_id == ["dest_a", "dest_b"]
    assert args.destination_track_id == "main"
    assert args.target_root_base == Path("deployments")
    assert args.continue_on_failure is True
    assert args.json is True


def test_build_parser_parses_run_campaign_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "run-campaign",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--generator",
            "failure_summary",
            "--strategy",
            "beam_interventions",
            "--beam-width",
            "4",
            "--beam-groups",
            "2",
            "--repeat",
            "3",
            "--stage-progression",
            "advance_on_success",
            "--intervention-class",
            "prompt",
            "--preflight-command",
            "python -c pass",
            "--preflight-timeout-seconds",
            "18",
            "--max-iterations",
            "5",
            "--max-successes",
            "4",
            "--max-promotions",
            "2",
            "--max-failures",
            "2",
            "--max-inconclusive",
            "1",
            "--no-improvement-limit",
            "3",
            "--time-budget-seconds",
            "60",
            "--max-generation-retries",
            "1",
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
            "2",
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
            "4",
            "--max-benchmark-total-cost",
            "1.75",
            "--max-inconclusive-retries",
            "3",
            "--allow-flaky-promotion",
            "--auto-promote-min-stage",
            "holdout",
            "--stop-on-first-promotion",
        ]
    )

    assert args.command == "run-campaign"
    assert args.workspace_id == "demo"
    assert args.adapter == "generic_command"
    assert args.stage is None
    assert args.stage_progression == "advance_on_success"
    assert args.generator == "failure_summary"
    assert args.strategy == "beam_interventions"
    assert args.beam_width == 4
    assert args.beam_groups == 2
    assert args.repeat == 3
    assert args.intervention_class == ["prompt"]
    assert args.preflight_command == ["python -c pass"]
    assert args.preflight_timeout_seconds == 18
    assert args.edit_plan == []
    assert args.max_iterations == 5
    assert args.max_successes == 4
    assert args.max_promotions == 2
    assert args.max_failures == 2
    assert args.max_inconclusive == 1
    assert args.no_improvement_limit == 3
    assert args.time_budget_seconds == 60
    assert args.max_generation_retries == 1
    assert args.max_generation_timeout_retries == 2
    assert args.max_generation_provider_retries == 3
    assert args.max_generation_provider_transport_retries == 5
    assert args.max_generation_provider_auth_retries == 6
    assert args.max_generation_provider_rate_limit_retries == 7
    assert args.max_generation_process_retries == 4
    assert args.max_generation_total_tokens == 123
    assert args.max_preflight_retries == 5
    assert args.max_execution_retries == 2
    assert args.max_benchmark_process_retries == 8
    assert args.max_benchmark_signal_retries == 9
    assert args.max_benchmark_parse_retries == 10
    assert args.max_benchmark_adapter_validation_retries == 11
    assert args.max_benchmark_timeout_retries == 6
    assert args.max_benchmark_command_retries == 4
    assert args.max_benchmark_total_cost == 1.75
    assert args.max_inconclusive_retries == 3
    assert args.allow_flaky_promotion is True
    assert args.auto_promote_min_stage == "holdout"
    assert args.stop_on_first_promotion is True


def test_build_parser_parses_export_campaign_report_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "export-campaign-report",
            "--workspace-id",
            "demo",
            "--campaign-id",
            "campaign_123",
            "--output",
            "campaign.json",
        ]
    )

    assert args.command == "export-campaign-report"
    assert args.workspace_id == "demo"
    assert args.campaign_id == "campaign_123"
    assert args.output == Path("campaign.json")


def test_build_parser_parses_export_campaign_bundle_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.workspace_id == "demo"
    assert args.campaign_id == "campaign_123"
    assert args.output == Path("campaign-bundle")


def test_build_parser_parses_run_workspace_campaigns_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "run-workspace-campaigns",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
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
    assert args.workspace_id == "demo"
    assert args.adapter == "generic_command"
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


def test_build_parser_parses_export_workspace_campaign_run_report_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "export-workspace-campaign-run-report",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--track-id",
            "main",
            "--output",
            "workspace-run-report.json",
        ]
    )

    assert args.command == "export-workspace-campaign-run-report"
    assert args.workspace_id == "demo"
    assert args.adapter == "generic_command"
    assert args.track_id == ["main"]
    assert args.output == Path("workspace-run-report.json")


def test_build_parser_parses_run_root_campaigns_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "run-root-campaigns",
            "--adapter",
            "generic_command",
            "--workspace-id",
            "demo",
            "--workspace-id",
            "demo_b",
            "--beam-width",
            "3",
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
    assert args.adapter == "generic_command"
    assert args.workspace_id == ["demo", "demo_b"]
    assert args.beam_width == 3
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


def test_build_parser_parses_export_root_campaign_run_report_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "export-root-campaign-run-report",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--output",
            "root-run-report.yaml",
        ]
    )

    assert args.command == "export-root-campaign-run-report"
    assert args.workspace_id == ["demo"]
    assert args.adapter == "generic_command"
    assert args.output == Path("root-run-report.yaml")


def test_build_parser_parses_show_root_campaigns_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]


def test_build_parser_parses_show_campaign_queue_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "show-campaign-queue",
            "--workspace-id",
            "demo",
            "--track-id",
            "main",
        ]
    )

    assert args.command == "show-campaign-queue"
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]


def test_build_parser_parses_show_listing_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-listing-file", "iterations.yaml"])

    assert args.command == "show-listing-file"
    assert args.path == Path("iterations.yaml")


def test_build_parser_parses_validate_listing_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["validate-listing-file", "iterations.yaml"])

    assert args.command == "validate-listing-file"
    assert args.path == Path("iterations.yaml")


def test_build_parser_parses_show_artifact_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-artifact-file", "artifact.json"])

    assert args.command == "show-artifact-file"
    assert args.path == Path("artifact.json")


def test_build_parser_parses_validate_artifact_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["validate-artifact-file", "artifact.json"])

    assert args.command == "validate-artifact-file"
    assert args.path == Path("artifact.json")


def test_build_parser_parses_show_report_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-report-file", "workspace-report.yaml"])

    assert args.command == "show-report-file"
    assert args.path == Path("workspace-report.yaml")


def test_build_parser_parses_validate_report_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["validate-report-file", "workspace-report.yaml"])

    assert args.command == "validate-report-file"
    assert args.path == Path("workspace-report.yaml")


def test_build_parser_parses_show_campaign_report_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(["show-campaign-report-file", "campaign-report.yaml"])

    assert args.command == "show-campaign-report-file"
    assert args.path == Path("campaign-report.yaml")


def test_build_parser_parses_validate_campaign_report_file_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        ["validate-campaign-report-file", "campaign-report.yaml"]
    )

    assert args.command == "validate-campaign-report-file"
    assert args.path == Path("campaign-report.yaml")


def test_build_parser_parses_export_workspace_campaign_report_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.workspace_id == "demo"
    assert args.track_id == "main"
    assert args.output == Path("workspace-campaign-report.yaml")


def test_build_parser_parses_export_workspace_campaign_bundle_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.workspace_id == "demo"
    assert args.track_id == "main"
    assert args.output == Path("workspace-campaign-bundle")


def test_build_parser_parses_export_root_campaign_report_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

    args = parser.parse_args(
        [
            "export-root-campaign-report",
            "--workspace-id",
            "demo",
            "--output",
            "root-report.yaml",
        ]
    )

    assert args.command == "export-root-campaign-report"
    assert args.workspace_id == ["demo"]
    assert args.output == Path("root-report.yaml")


def test_build_parser_parses_export_root_campaign_bundle_arguments() -> None:
    parser = build_parser(run_planned_iteration_handler=_stub_run_planned_iteration)

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
    assert args.workspace_id == ["demo"]
    assert args.track_id == ["main"]
    assert args.output == Path("root-campaign-bundle")
