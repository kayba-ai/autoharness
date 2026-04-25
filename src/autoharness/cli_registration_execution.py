"""Execution and planning command registration."""

from __future__ import annotations

import argparse
from pathlib import Path

from .cli_arguments import (
    DEFAULT_WORKSPACES_ROOT,
    _add_comparison_gate_arguments,
    _add_config_composition_arguments,
    _add_json_output_arguments,
    _add_optional_workspace_id_argument,
    _add_plan_artifact_write_arguments,
    _add_repeat_seed_arguments,
    _add_required_adapter_argument,
    _add_required_plan_path_argument,
    _add_stage_policy_argument,
    _add_workspace_id_argument,
    _add_workspace_root_argument,
)
from .execution_handlers import (
    _handle_list_preflight_checks,
    _handle_plan_iteration,
    _handle_run_benchmark,
    _handle_run_iteration,
    _handle_show_preflight_check,
    _handle_show_plan_file,
    _handle_validate_plan_file,
)
from .preflight import available_preflight_checks


def register_execution_parsers(
    subparsers,
    *,
    run_planned_iteration_handler,
) -> None:
    list_preflight_checks = subparsers.add_parser(
        "list-preflight-checks",
        help="Show the built-in preflight check catalog.",
    )
    _add_json_output_arguments(
        list_preflight_checks,
        json_help="Render the preflight check catalog as JSON.",
        output_help="Optional path to write the rendered preflight check catalog JSON.",
    )
    list_preflight_checks.set_defaults(handler=_handle_list_preflight_checks)

    show_preflight_check = subparsers.add_parser(
        "show-preflight-check",
        help="Show one built-in preflight check.",
    )
    show_preflight_check.add_argument(
        "--check",
        required=True,
        choices=available_preflight_checks(),
        help="Built-in preflight check id.",
    )
    _add_json_output_arguments(
        show_preflight_check,
        json_help="Render the preflight check as JSON.",
        output_help="Optional path to write the rendered preflight check JSON.",
    )
    show_preflight_check.set_defaults(handler=_handle_show_preflight_check)

    run_benchmark = subparsers.add_parser(
        "run-benchmark",
        help="Run one implemented benchmark adapter from a config file.",
    )
    _add_required_adapter_argument(
        run_benchmark,
        help_text="Adapter id to execute.",
    )
    _add_config_composition_arguments(
        run_benchmark,
        preset_help=(
            "Optional starter-config preset to compose under the provided config. "
            "Defaults to the track/workspace policy preset for the selected stage when available."
        ),
    )
    run_benchmark.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the result or dry-run invocation JSON.",
    )
    run_benchmark.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the normalized invocation without executing it.",
    )
    run_benchmark.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default="screening",
        help="Evaluation stage policy to apply. Default: screening.",
    )
    _add_repeat_seed_arguments(run_benchmark)
    run_benchmark.add_argument(
        "--min-success-rate",
        type=float,
        default=None,
        help="Optional stage gate override for the minimum success rate.",
    )
    run_benchmark.add_argument(
        "--baseline-source",
        choices=("none", "champion"),
        default="none",
        help="Optional baseline source inside the workspace track. Default: none.",
    )
    run_benchmark.add_argument(
        "--baseline-record-id",
        default=None,
        help="Optional explicit baseline record id inside the same workspace track.",
    )
    run_benchmark.add_argument(
        "--min-improvement",
        type=float,
        default=0.0,
        help="Required improvement margin over the baseline success signal.",
    )
    run_benchmark.add_argument(
        "--max-regressed-tasks",
        type=int,
        default=None,
        help="Optional ceiling on matched tasks that may regress against the baseline.",
    )
    run_benchmark.add_argument(
        "--max-regressed-task-fraction",
        type=float,
        default=None,
        help="Optional ceiling on the fraction of matched tasks that may regress.",
    )
    run_benchmark.add_argument(
        "--max-regressed-task-weight",
        type=float,
        default=None,
        help="Optional ceiling on the total weight of matched tasks that may regress.",
    )
    run_benchmark.add_argument(
        "--max-regressed-task-weight-fraction",
        type=float,
        default=None,
        help="Optional ceiling on the weighted fraction of matched tasks that may regress.",
    )
    run_benchmark.add_argument(
        "--task-regression-margin",
        type=float,
        default=0.0,
        help="How much a task score may drop before it counts as a regression.",
    )
    run_benchmark.add_argument(
        "--preflight-check",
        choices=available_preflight_checks(),
        action="append",
        default=[],
        help="Repeatable built-in preflight check expanded before benchmark execution (for example `python_compile`).",
    )
    run_benchmark.add_argument(
        "--preflight-command",
        action="append",
        default=[],
        help="Repeatable preflight command run before benchmark execution.",
    )
    run_benchmark.add_argument(
        "--preflight-timeout-seconds",
        type=int,
        default=60,
        help="Per-command timeout for preflight commands. Default: 60.",
    )
    run_benchmark.add_argument(
        "--workspace-id",
        default=None,
        help="Optional workspace id. If set, persist the run in the track registry.",
    )
    run_benchmark.add_argument(
        "--track-id",
        default=None,
        help="Track id to use when persisting a record.",
    )
    run_benchmark.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_WORKSPACES_ROOT,
        help="Workspace root directory when persisting records.",
    )
    run_benchmark.add_argument(
        "--hypothesis",
        default="",
        help="Optional hypothesis label when persisting a record.",
    )
    run_benchmark.add_argument(
        "--notes",
        default="",
        help="Optional notes when persisting a record.",
    )
    run_benchmark.set_defaults(handler=_handle_run_benchmark)

    plan_iteration = subparsers.add_parser(
        "plan-iteration",
        help="Render a stage-ready run-iteration command from workspace policy and presets.",
    )
    _add_workspace_id_argument(plan_iteration)
    _add_required_adapter_argument(plan_iteration)
    _add_config_composition_arguments(
        plan_iteration,
        preset_help=(
            "Optional starter-config preset override. Defaults to the track/workspace "
            "policy preset for the selected stage when available."
        ),
    )
    plan_iteration.add_argument(
        "--hypothesis",
        default=None,
        help="Optional hypothesis text. Defaults to a generated stage-aware label.",
    )
    plan_iteration.add_argument(
        "--track-id",
        default=None,
        help="Track id to plan against. Defaults to the active track.",
    )
    _add_workspace_root_argument(plan_iteration)
    plan_iteration.add_argument(
        "--stage",
        choices=("screening", "validation", "holdout", "transfer"),
        default="screening",
        help="Evaluation stage policy to plan for. Default: screening.",
    )
    plan_iteration.add_argument(
        "--dry-run",
        action="store_true",
        help="Include --dry-run in the suggested run-iteration command.",
    )
    plan_iteration.add_argument(
        "--json",
        action="store_true",
        help="Render the iteration plan as JSON.",
    )
    plan_iteration.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write the iteration plan JSON.",
    )
    _add_plan_artifact_write_arguments(plan_iteration)
    plan_iteration.set_defaults(handler=_handle_plan_iteration)

    show_plan_file = subparsers.add_parser(
        "show-plan-file",
        help="Inspect a saved plan-iteration artifact file.",
    )
    show_plan_file.add_argument(
        "path",
        type=Path,
        help="Path to a saved iteration plan file.",
    )
    _add_json_output_arguments(
        show_plan_file,
        json_help="Print the resolved iteration plan JSON.",
        output_help="Optional path to write the resolved iteration plan JSON.",
    )
    show_plan_file.set_defaults(handler=_handle_show_plan_file)

    validate_plan_file = subparsers.add_parser(
        "validate-plan-file",
        help="Validate a saved plan-iteration artifact file.",
    )
    validate_plan_file.add_argument(
        "path",
        type=Path,
        help="Path to a saved iteration plan file.",
    )
    _add_json_output_arguments(
        validate_plan_file,
        json_help="Print iteration-plan validation JSON.",
        output_help="Optional path to write the iteration-plan validation JSON.",
    )
    validate_plan_file.set_defaults(handler=_handle_validate_plan_file)

    run_planned_iteration = subparsers.add_parser(
        "run-planned-iteration",
        help="Replay a saved plan-iteration JSON by executing its suggested run-iteration command.",
    )
    _add_required_plan_path_argument(
        run_planned_iteration,
        help_text="Path to a saved iteration plan JSON from plan-iteration.",
    )
    run_planned_iteration.set_defaults(handler=run_planned_iteration_handler)

    run_iteration = subparsers.add_parser(
        "run-iteration",
        help="Run exactly one hypothesis inside an existing workspace and record it.",
    )
    _add_optional_workspace_id_argument(run_iteration)
    _add_required_adapter_argument(run_iteration)
    _add_config_composition_arguments(
        run_iteration,
        preset_help=(
            "Optional starter-config preset to compose under the provided config. "
            "Defaults to the track/workspace policy preset for the selected stage when available."
        ),
    )
    run_iteration.add_argument("--hypothesis", required=True)
    run_iteration.add_argument("--notes", default="")
    run_iteration.add_argument(
        "--edit-plan",
        type=Path,
        default=None,
        help="Optional YAML or JSON edit plan to apply before the benchmark.",
    )
    run_iteration.add_argument(
        "--preflight-check",
        choices=available_preflight_checks(),
        action="append",
        default=[],
        help="Repeatable built-in preflight check expanded before the benchmark (for example `python_compile`).",
    )
    run_iteration.add_argument(
        "--preflight-command",
        action="append",
        default=[],
        help="Repeatable preflight command run from the effective target root before the benchmark.",
    )
    run_iteration.add_argument(
        "--preflight-timeout-seconds",
        type=int,
        default=60,
        help="Per-command timeout for preflight commands. Default: 60.",
    )
    run_iteration.add_argument(
        "--target-root",
        type=Path,
        default=Path("."),
        help="Target harness root for edit plans. Default: current directory.",
    )
    run_iteration.add_argument(
        "--keep-applied-edits",
        action="store_true",
        help="Keep applied edits on disk after the iteration finishes.",
    )
    run_iteration.add_argument(
        "--staging-mode",
        choices=("off", "copy", "auto"),
        default="auto",
        help="Optional isolated target execution mode. Default: auto.",
    )
    run_iteration.add_argument("--track-id", default=None)
    _add_workspace_root_argument(run_iteration)
    run_iteration.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the iteration as a dry-run invocation only.",
    )
    run_iteration.add_argument(
        "--source-plan-path",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    run_iteration.add_argument(
        "--source-proposal-id",
        default=None,
        help=argparse.SUPPRESS,
    )
    run_iteration.add_argument(
        "--source-proposal-path",
        type=Path,
        default=None,
        help=argparse.SUPPRESS,
    )
    _add_stage_policy_argument(
        run_iteration,
        default="screening",
        help_text="Evaluation stage policy to apply. Default: screening.",
    )
    _add_repeat_seed_arguments(run_iteration)
    run_iteration.add_argument(
        "--baseline-source",
        choices=("none", "champion"),
        default="none",
        help="Optional baseline source inside the workspace track. Default: none.",
    )
    run_iteration.add_argument(
        "--baseline-record-id",
        default=None,
        help="Optional explicit baseline record id inside the same workspace track.",
    )
    _add_comparison_gate_arguments(
        run_iteration,
        comparison_target_label="baseline",
        min_success_rate_default=None,
        min_improvement_default=0.0,
        task_regression_margin_default=0.0,
    )
    run_iteration.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to also write the raw run payload or invocation JSON.",
    )
    run_iteration.set_defaults(handler=_handle_run_iteration)
