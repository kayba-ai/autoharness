"""CLI handlers for resumable campaign runs."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .campaign_runs import (
    CampaignCandidateRun,
    CampaignDecisionLogEntry,
    CampaignRun,
    _utc_now,
    campaign_lease_is_stale,
    campaign_run_path,
    claim_campaign_run,
    claim_workspace_campaign_lease,
    create_campaign_run,
    heartbeat_workspace_campaign_lease,
    list_track_campaign_runs,
    list_runnable_campaign_runs,
    load_campaign_run,
    persist_campaign_run,
    release_campaign_run,
    release_workspace_campaign_lease,
    resolve_workspace_campaign_run,
    set_campaign_desired_state,
    workspace_campaign_lease_path,
)
from .cli_support import _load_structured_file
from .cli_support import _resolve_workspace_id, _resolve_workspace_track
from .generators import (
    ProposalGenerationProcessError,
    ProposalGenerationProviderAuthError,
    ProposalGenerationProviderError,
    ProposalGenerationProviderRateLimitError,
    ProposalGenerationProviderTransportError,
    ProposalGenerationTimeoutError,
)
from .events import append_workspace_event, aggregate_event_metrics, load_workspace_events
from .mutations import _resolve_track_campaign_policy
from .outputs import _emit_json_output
from .outputs import _export_listing_payload
from .outputs import _write_structured_payload
from .preflight import resolve_effective_preflight_commands
from .promotion_handlers import (
    _compute_champion_comparison,
    _export_champion_bundle,
    _prepare_export_dir,
    _promote_record,
)
from .proposal_handlers import _handle_generate_proposal, _handle_run_proposal
from .proposal_context import load_latest_generation_signals
from .proposals import load_proposal, resolve_proposal_artifact_paths
from .provider_profiles import (
    load_provider_profiles,
    provider_profiles_path,
    summarize_provider_profiles,
)
from .root_memory import (
    apply_transfer_suggestions,
    build_root_memory,
    persist_root_memory,
    schedule_root_workspaces,
)
from .search import (
    available_search_strategies,
    compute_candidate_branch_score,
    rank_beam_candidate,
    resolve_beam_group_start,
    resolve_focus_task_ids,
    resolve_intervention_class,
    resolve_next_stage,
    stage_meets_minimum,
    summarize_beam_group_outcomes,
    strategy_uses_beam,
    strategy_uses_scoring,
)
from .tracking import (
    iteration_dir_path,
    load_benchmark_record,
    load_promotion_record,
    load_champion_manifest,
    load_iteration_summary,
    load_workspace,
    load_workspace_state,
)
from .validation import classify_validation_payload, stability_score_from_validation_summary


def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _candidate_attempt_total(candidates: list[CampaignCandidateRun]) -> int:
    return sum(1 for candidate in candidates if candidate.status not in {"pending", "pruned"})


def _next_runnable_candidate_index(
    candidates: list[CampaignCandidateRun],
    *,
    start_index: int,
) -> int:
    index = start_index
    while index < len(candidates) and candidates[index].status == "pruned":
        index += 1
    return index


def _classify_candidate_failure(*, candidate_status: str, exit_code: int | None) -> str | None:
    if candidate_status == "success":
        return None
    if candidate_status == "dry_run":
        return None
    if candidate_status == "inconclusive":
        return "benchmark_inconclusive"
    if candidate_status == "failed":
        return "benchmark_failed"
    if exit_code is not None:
        return "execution_error"
    return "generation_error"


def _payload_run_payloads(payload: dict[str, object]) -> list[dict[str, object]]:
    validation_runs = payload.get("validation_runs")
    if isinstance(validation_runs, list):
        runs = [run for run in validation_runs if isinstance(run, dict)]
        if runs:
            return runs
    return [payload]


def _payload_run_metadata(run_payload: dict[str, object]) -> dict[str, object]:
    metadata = run_payload.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _payload_contains_timed_out_run(payload: dict[str, object]) -> bool:
    return any(run.get("timed_out") is True for run in _payload_run_payloads(payload))


def _payload_contains_process_error(payload: dict[str, object]) -> bool:
    return any(
        isinstance(run.get("process_error"), str) and run.get("process_error")
        for run in _payload_run_payloads(payload)
    )


def _payload_contains_signal_error(payload: dict[str, object]) -> bool:
    for run in _payload_run_payloads(payload):
        signal_number = run.get("signal_number")
        if isinstance(signal_number, int) and signal_number > 0:
            return True
        exit_code = run.get("exit_code")
        if isinstance(exit_code, int) and exit_code < 0:
            return True
    return False


def _payload_parse_failure_class(payload: dict[str, object]) -> str | None:
    metrics_parse_failed = False
    task_results_parse_failed = False
    for run in _payload_run_payloads(payload):
        metadata = _payload_run_metadata(run)
        if isinstance(metadata.get("metrics_parse_error"), str):
            metrics_parse_failed = True
        if isinstance(metadata.get("task_results_parse_error"), str):
            task_results_parse_failed = True
    if metrics_parse_failed and task_results_parse_failed:
        return "benchmark_artifact_parse_error"
    if metrics_parse_failed:
        return "benchmark_metrics_parse_error"
    if task_results_parse_failed:
        return "benchmark_task_results_parse_error"
    return None


def _classify_record_failure(record) -> str | None:
    if record.status == "success":
        return None
    if record.status == "dry_run":
        return None
    if record.status == "inconclusive":
        return "benchmark_inconclusive"
    if record.status != "failed":
        return "benchmark_failed"

    payload = record.payload
    if not isinstance(payload, dict):
        return "benchmark_failed"
    validation_failure_class = classify_validation_payload(payload)
    if validation_failure_class is not None:
        return validation_failure_class
    stage_evaluation = payload.get("stage_evaluation")
    if isinstance(stage_evaluation, dict):
        baseline_comparison = stage_evaluation.get("baseline_comparison")
        if isinstance(baseline_comparison, dict):
            regressed_task_ids = baseline_comparison.get("regressed_task_ids")
            regressed_tasks = baseline_comparison.get("regressed_tasks")
            if (
                baseline_comparison.get("passed") is False
                and (
                    (isinstance(regressed_task_ids, list) and len(regressed_task_ids) > 0)
                    or (isinstance(regressed_tasks, list) and len(regressed_tasks) > 0)
                )
            ):
                return "benchmark_regression"
    success_value = payload.get("success")
    if success_value is False:
        return "benchmark_command_failed"
    if isinstance(stage_evaluation, dict):
        if stage_evaluation.get("passed") is False:
            return "stage_gate_failed"
    return "benchmark_failed"


def _classify_generation_exception(exc: BaseException) -> str:
    current: BaseException | None = exc
    while current is not None:
        if isinstance(current, ProposalGenerationTimeoutError):
            return "generation_timeout"
        if isinstance(current, ProposalGenerationProviderTransportError):
            return "generation_provider_transport_error"
        if isinstance(current, ProposalGenerationProviderAuthError):
            return "generation_provider_auth_error"
        if isinstance(current, ProposalGenerationProviderRateLimitError):
            return "generation_provider_rate_limit_error"
        if isinstance(current, ProposalGenerationProviderError):
            return "generation_provider_error"
        if isinstance(current, ProposalGenerationProcessError):
            return "generation_process_error"
        current = getattr(current, "__cause__", None)
    return "generation_error"


def _record_is_flaky(record) -> bool:
    payload = record.payload
    if not isinstance(payload, dict):
        return False
    validation_summary = payload.get("validation_summary")
    if not isinstance(validation_summary, dict):
        return False
    stability_summary = validation_summary.get("stability_summary")
    if not isinstance(stability_summary, dict):
        return False
    return bool(stability_summary.get("flaky"))


def _record_stability_score(record) -> float | None:
    payload = record.payload
    if not isinstance(payload, dict):
        return None
    stage_evaluation = payload.get("stage_evaluation")
    if isinstance(stage_evaluation, dict):
        stability_gate = stage_evaluation.get("stability_gate")
        if isinstance(stability_gate, dict):
            stability_score = stability_gate.get("stability_score")
            if (
                isinstance(stability_score, (int, float))
                and not isinstance(stability_score, bool)
            ):
                return float(stability_score)
    validation_summary = payload.get("validation_summary")
    if not isinstance(validation_summary, dict):
        return None
    return stability_score_from_validation_summary(validation_summary)


def _record_confidence_interval_width(record) -> float | None:
    payload = record.payload
    if not isinstance(payload, dict):
        return None
    stage_evaluation = payload.get("stage_evaluation")
    if isinstance(stage_evaluation, dict):
        stability_gate = stage_evaluation.get("stability_gate")
        if isinstance(stability_gate, dict):
            width = stability_gate.get("confidence_interval_width")
            if isinstance(width, (int, float)) and not isinstance(width, bool):
                return float(width)
    validation_summary = payload.get("validation_summary")
    if not isinstance(validation_summary, dict):
        return None
    interval = validation_summary.get("success_rate_confidence_interval")
    if not isinstance(interval, dict):
        return None
    lower = interval.get("lower")
    upper = interval.get("upper")
    if (
        isinstance(lower, (int, float))
        and not isinstance(lower, bool)
        and isinstance(upper, (int, float))
        and not isinstance(upper, bool)
    ):
        return float(upper) - float(lower)
    return None


def _record_stability_gate(record) -> dict[str, object] | None:
    payload = record.payload
    if not isinstance(payload, dict):
        return None
    stage_evaluation = payload.get("stage_evaluation")
    if not isinstance(stage_evaluation, dict):
        return None
    stability_gate = stage_evaluation.get("stability_gate")
    return dict(stability_gate) if isinstance(stability_gate, dict) else None


def _empty_resource_usage() -> dict[str, float | int]:
    return {
        "generation_input_tokens": 0,
        "generation_output_tokens": 0,
        "generation_total_tokens": 0,
        "generation_total_cost_usd": 0.0,
        "generation_total_duration_seconds": 0.0,
        "benchmark_total_cost": 0.0,
        "benchmark_total_duration_seconds": 0.0,
    }


def _resource_int(value: object) -> int:
    return int(value) if isinstance(value, int) and value >= 0 else 0


def _resource_float(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        return numeric if numeric >= 0.0 else 0.0
    return 0.0


def _add_resource_usage(
    totals: dict[str, float | int],
    delta: dict[str, float | int],
) -> dict[str, float | int]:
    updated = dict(totals)
    for key, value in delta.items():
        if key.endswith("_tokens"):
            updated[key] = int(updated.get(key, 0)) + int(value)
        else:
            updated[key] = float(updated.get(key, 0.0)) + float(value)
    return updated


def _normalized_resource_usage(value: object) -> dict[str, float | int]:
    payload = value if isinstance(value, dict) else {}
    return {
        "generation_input_tokens": _resource_int(payload.get("generation_input_tokens")),
        "generation_output_tokens": _resource_int(
            payload.get("generation_output_tokens")
        ),
        "generation_total_tokens": _resource_int(payload.get("generation_total_tokens")),
        "generation_total_cost_usd": _resource_float(
            payload.get("generation_total_cost_usd")
        ),
        "generation_total_duration_seconds": _resource_float(
            payload.get("generation_total_duration_seconds")
        ),
        "benchmark_total_cost": _resource_float(payload.get("benchmark_total_cost")),
        "benchmark_total_duration_seconds": _resource_float(
            payload.get("benchmark_total_duration_seconds")
        ),
    }


def _proposal_resource_usage_from_metadata(
    metadata: dict[str, object],
) -> dict[str, float | int]:
    usage_payload = metadata.get("usage")
    usage = usage_payload if isinstance(usage_payload, dict) else {}
    input_tokens = _resource_int(usage.get("input_tokens"))
    output_tokens = _resource_int(usage.get("output_tokens"))
    total_tokens = _resource_int(usage.get("total_tokens"))
    if total_tokens == 0:
        total_tokens = input_tokens + output_tokens
    cost_usd = _resource_float(usage.get("cost_usd"))
    if cost_usd == 0.0:
        cost_usd = _resource_float(metadata.get("cost_usd"))
    return {
        "generation_input_tokens": input_tokens,
        "generation_output_tokens": output_tokens,
        "generation_total_tokens": total_tokens,
        "generation_total_cost_usd": cost_usd,
        "generation_total_duration_seconds": _resource_float(
            metadata.get("generation_duration_seconds")
        ),
        "benchmark_total_cost": 0.0,
        "benchmark_total_duration_seconds": 0.0,
    }


def _metric_cost(metrics: object) -> float:
    if not isinstance(metrics, dict):
        return 0.0
    if "cost" in metrics:
        return _resource_float(metrics.get("cost"))
    if "mean_cost" in metrics:
        return _resource_float(metrics.get("mean_cost"))
    return 0.0


def _record_resource_usage_from_payload(
    payload: dict[str, object],
) -> dict[str, float | int]:
    benchmark_total_cost = 0.0
    benchmark_total_duration_seconds = 0.0
    validation_runs = payload.get("validation_runs")
    if isinstance(validation_runs, list) and validation_runs:
        for run in validation_runs:
            if not isinstance(run, dict):
                continue
            benchmark_total_duration_seconds += _resource_float(
                run.get("duration_seconds")
            )
            benchmark_total_cost += _metric_cost(run.get("metrics"))
    else:
        benchmark_total_duration_seconds += _resource_float(
            payload.get("duration_seconds")
        )
        benchmark_total_cost += _metric_cost(payload.get("metrics"))
        if benchmark_total_duration_seconds == 0.0:
            validation_summary = payload.get("validation_summary")
            if isinstance(validation_summary, dict):
                benchmark_total_duration_seconds += _resource_float(
                    validation_summary.get("mean_duration_seconds")
                )
                metrics_mean = validation_summary.get("metrics_mean")
                benchmark_total_cost += _metric_cost(metrics_mean)
    return {
        "generation_input_tokens": 0,
        "generation_output_tokens": 0,
        "generation_total_tokens": 0,
        "generation_total_cost_usd": 0.0,
        "generation_total_duration_seconds": 0.0,
        "benchmark_total_cost": benchmark_total_cost,
        "benchmark_total_duration_seconds": benchmark_total_duration_seconds,
    }


def _campaign_resource_usage(
    *,
    root: Path,
    campaign: CampaignRun,
) -> dict[str, float | int]:
    proposal_ids: set[str] = set()
    record_ids: set[str] = set()
    for candidate in campaign.candidates:
        if isinstance(candidate.proposal_id, str):
            proposal_ids.add(candidate.proposal_id)
        if isinstance(candidate.record_id, str):
            record_ids.add(candidate.record_id)
    for entry in campaign.decision_log:
        if isinstance(entry.proposal_id, str):
            proposal_ids.add(entry.proposal_id)
        if isinstance(entry.record_id, str):
            record_ids.add(entry.record_id)

    totals = _empty_resource_usage()
    for proposal_id in sorted(proposal_ids):
        try:
            proposal = load_proposal(
                root=root,
                workspace_id=campaign.workspace_id,
                track_id=campaign.track_id,
                proposal_id=proposal_id,
            )
        except FileNotFoundError:
            continue
        totals = _add_resource_usage(
            totals,
            _proposal_resource_usage_from_metadata(proposal.generator_metadata),
        )
    for record_id in sorted(record_ids):
        try:
            record = load_benchmark_record(
                root=root,
                workspace_id=campaign.workspace_id,
                track_id=campaign.track_id,
                record_id=record_id,
            )
        except FileNotFoundError:
            continue
        totals = _add_resource_usage(
            totals,
            _record_resource_usage_from_payload(record.payload),
        )
    return totals


def _summarize_campaign_resource_usage(
    items: list[dict[str, object]],
) -> dict[str, float | int]:
    totals = _empty_resource_usage()
    for item in items:
        totals = _add_resource_usage(
            totals,
            _normalized_resource_usage(item.get("resource_usage")),
        )
    return totals


def _print_resource_usage_summary(resource_usage: object) -> None:
    normalized = _normalized_resource_usage(resource_usage)
    print(f"Generation input tokens: {normalized['generation_input_tokens']}")
    print(f"Generation output tokens: {normalized['generation_output_tokens']}")
    print(f"Generation total tokens: {normalized['generation_total_tokens']}")
    print(f"Generation cost: {normalized['generation_total_cost_usd']}")
    print(
        f"Generation seconds: {normalized['generation_total_duration_seconds']}"
    )
    print(f"Benchmark cost: {normalized['benchmark_total_cost']}")
    print(
        f"Benchmark seconds: {normalized['benchmark_total_duration_seconds']}"
    )


def _retry_limit_for_failure_class(campaign: CampaignRun, failure_class: str) -> int:
    if failure_class == "generation_error":
        return int(campaign.max_generation_retries or 0)
    if failure_class == "generation_timeout":
        return int(campaign.max_generation_timeout_retries or 0)
    if failure_class == "generation_provider_transport_error":
        return int(campaign.max_generation_provider_transport_retries or 0)
    if failure_class == "generation_provider_auth_error":
        return int(campaign.max_generation_provider_auth_retries or 0)
    if failure_class == "generation_provider_rate_limit_error":
        return int(campaign.max_generation_provider_rate_limit_retries or 0)
    if failure_class == "generation_provider_error":
        return int(campaign.max_generation_provider_retries or 0)
    if failure_class == "generation_process_error":
        return int(campaign.max_generation_process_retries or 0)
    if failure_class == "preflight_failed":
        return int(campaign.max_preflight_retries or 0)
    if failure_class == "execution_error":
        return int(campaign.max_execution_retries or 0)
    if failure_class == "benchmark_process_error":
        return int(campaign.max_benchmark_process_retries or 0)
    if failure_class == "benchmark_signal_error":
        return int(campaign.max_benchmark_signal_retries or 0)
    if failure_class in {
        "benchmark_metrics_parse_error",
        "benchmark_task_results_parse_error",
        "benchmark_artifact_parse_error",
    }:
        return int(campaign.max_benchmark_parse_retries or 0)
    if failure_class == "benchmark_adapter_validation_error":
        return int(campaign.max_benchmark_adapter_validation_retries or 0)
    if failure_class == "benchmark_timeout":
        return int(campaign.max_benchmark_timeout_retries or 0)
    if failure_class == "benchmark_command_failed":
        return int(campaign.max_benchmark_command_retries or 0)
    if failure_class == "benchmark_inconclusive":
        return int(campaign.max_inconclusive_retries or 0)
    if failure_class == "unstable_validation":
        return 1
    return 0


def _resolve_intervention_class(campaign: CampaignRun, *, candidate_index: int) -> str | None:
    return resolve_intervention_class(
        strategy_id=campaign.strategy,
        intervention_classes=campaign.intervention_classes,
        candidate_index=candidate_index,
    )


def _parse_generator_options(raw_options: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_entry in raw_options:
        if "=" not in raw_entry:
            raise SystemExit("`--generator-option` must use key=value format.")
        key, value = raw_entry.split("=", 1)
        if not key.strip() or not value.strip():
            raise SystemExit("`--generator-option` requires non-empty key and value.")
        parsed[key.strip()] = value.strip()
    return parsed


_PROPOSAL_REUSE_FAILURE_CLASSES = {
    "preflight_failed",
    "execution_error",
    "benchmark_process_error",
    "benchmark_signal_error",
    "benchmark_metrics_parse_error",
    "benchmark_task_results_parse_error",
    "benchmark_artifact_parse_error",
    "benchmark_adapter_validation_error",
    "benchmark_timeout",
    "benchmark_command_failed",
    "benchmark_inconclusive",
    "unstable_validation",
}


def _run_campaign_args_for_track(
    *,
    args: argparse.Namespace,
    track_id: str,
    target_root: Path,
    promotion_target_root: Path | None,
) -> argparse.Namespace:
    return argparse.Namespace(
        workspace_id=args.workspace_id,
        track_id=track_id,
        root=args.root,
        adapter=args.adapter,
        config=args.config,
        preset=args.preset,
        set=list(args.set),
        stage=args.stage,
        preflight_command=list(args.preflight_command),
        preflight_check=list(getattr(args, "preflight_check", [])),
        preflight_timeout_seconds=args.preflight_timeout_seconds,
        generator=args.generator,
        strategy=args.strategy,
        beam_width=args.beam_width,
        beam_groups=args.beam_groups,
        repeat=args.repeat,
        stage_progression=args.stage_progression,
        edit_plan=list(args.edit_plan),
        intervention_class=list(args.intervention_class),
        generator_option=list(args.generator_option),
        target_root=target_root,
        max_proposals=args.max_proposals,
        max_iterations=args.max_iterations,
        max_successes=args.max_successes,
        max_promotions=args.max_promotions,
        max_failures=args.max_failures,
        max_inconclusive=args.max_inconclusive,
        no_improvement_limit=args.no_improvement_limit,
        auto_promote=args.auto_promote,
        allow_flaky_promotion=args.allow_flaky_promotion,
        auto_promote_min_stage=args.auto_promote_min_stage,
        stop_on_first_promotion=args.stop_on_first_promotion,
        promotion_target_root=promotion_target_root,
        dry_run=args.dry_run,
        background=getattr(args, "background", False),
        time_budget_seconds=args.time_budget_seconds,
        max_generation_total_tokens=args.max_generation_total_tokens,
        max_benchmark_total_cost=args.max_benchmark_total_cost,
        max_generation_retries=args.max_generation_retries,
        max_generation_timeout_retries=args.max_generation_timeout_retries,
        max_generation_provider_retries=args.max_generation_provider_retries,
        max_generation_provider_transport_retries=(
            args.max_generation_provider_transport_retries
        ),
        max_generation_provider_auth_retries=args.max_generation_provider_auth_retries,
        max_generation_provider_rate_limit_retries=(
            args.max_generation_provider_rate_limit_retries
        ),
        max_generation_process_retries=args.max_generation_process_retries,
        max_preflight_retries=args.max_preflight_retries,
        max_execution_retries=args.max_execution_retries,
        max_benchmark_process_retries=args.max_benchmark_process_retries,
        max_benchmark_signal_retries=args.max_benchmark_signal_retries,
        max_benchmark_parse_retries=args.max_benchmark_parse_retries,
        max_benchmark_adapter_validation_retries=(
            args.max_benchmark_adapter_validation_retries
        ),
        max_benchmark_timeout_retries=args.max_benchmark_timeout_retries,
        max_benchmark_command_retries=args.max_benchmark_command_retries,
        max_inconclusive_retries=args.max_inconclusive_retries,
        json=True,
        output=None,
    )


def _capture_handler_json(handler, args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        exit_code = handler(args)
    output = buffer.getvalue().strip()
    if not output:
        return exit_code, {}
    return exit_code, json.loads(output)


def _write_events_jsonl(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(event, sort_keys=False) + "\n" for event in events),
        encoding="utf-8",
    )


def _render_campaign(campaign: CampaignRun, *, root: Path) -> dict[str, object]:
    completed_candidates = [
        candidate
        for candidate in campaign.candidates
        if candidate.status not in {"pending", "pruned"}
    ]
    pruned_candidate_total = sum(
        1 for candidate in campaign.candidates if candidate.status == "pruned"
    )
    failure_class_counts: dict[str, int] = {}
    for candidate in campaign.candidates:
        if candidate.failure_class is None:
            continue
        failure_class_counts[candidate.failure_class] = (
            failure_class_counts.get(candidate.failure_class, 0) + 1
        )
    scored_candidates = [
        candidate for candidate in campaign.candidates if candidate.branch_score is not None
    ]
    resource_usage = _campaign_resource_usage(root=root, campaign=campaign)
    return {
        "campaign": campaign.to_dict(),
        "campaign_path": str(
            campaign_run_path(
                root=root,
                workspace_id=campaign.workspace_id,
                track_id=campaign.track_id,
                campaign_run_id=campaign.campaign_run_id,
            )
        ),
        "candidate_total": len(campaign.candidates),
        "completed_candidate_total": len(completed_candidates),
        "pruned_candidate_total": pruned_candidate_total,
        "attempt_total": sum(candidate.attempt_count for candidate in campaign.candidates),
        "current_stage": campaign.stage,
        "initial_stage": campaign.initial_stage,
        "success_count": campaign.success_count,
        "failure_count": campaign.failure_count,
        "inconclusive_count": campaign.inconclusive_count,
        "failure_class_counts": failure_class_counts,
        "scored_candidate_total": len(scored_candidates),
        "top_branch_score": (
            max(candidate.branch_score for candidate in scored_candidates)
            if scored_candidates
            else None
        ),
        "no_improvement_streak": campaign.no_improvement_streak,
        "promoted_count": campaign.promoted_count,
        "decision_log_total": len(campaign.decision_log),
        "recent_decisions": [entry.to_dict() for entry in campaign.decision_log[-10:]],
        "resource_usage": resource_usage,
    }


def _render_campaign_artifacts(
    *,
    root: Path,
    campaign: CampaignRun,
) -> dict[str, object]:
    proposal_artifacts = []
    record_artifacts = []
    iteration_artifacts = []
    promotion_artifacts = []
    for candidate in campaign.candidates:
        if candidate.proposal_id is not None:
            try:
                proposal = load_proposal(
                    root=root,
                    workspace_id=campaign.workspace_id,
                    track_id=campaign.track_id,
                    proposal_id=candidate.proposal_id,
                )
            except FileNotFoundError:
                proposal = None
            if proposal is not None:
                proposal_artifacts.append(
                    {
                        "proposal_id": proposal.proposal_id,
                        **resolve_proposal_artifact_paths(root=root, proposal=proposal),
                    }
                )
        if candidate.record_id is not None:
            record_path = (
                root
                / campaign.workspace_id
                / "tracks"
                / campaign.track_id
                / "registry"
                / f"{candidate.record_id}.json"
            )
            record_artifacts.append(
                {
                    "record_id": candidate.record_id,
                    "record_path": str(record_path),
                }
            )
        if candidate.iteration_id is not None:
            iteration_path = iteration_dir_path(
                root=root,
                workspace_id=campaign.workspace_id,
                iteration_id=candidate.iteration_id,
            )
            iteration_artifacts.append(
                {
                    "iteration_id": candidate.iteration_id,
                    "iteration_path": str(iteration_path),
                    "summary_path": str(iteration_path / "summary.json"),
                }
            )
        if candidate.promotion_id is not None:
            promotion_path = (
                root
                / campaign.workspace_id
                / "tracks"
                / campaign.track_id
                / "promotions"
                / f"{candidate.promotion_id}.json"
            )
            diff_path = (
                root
                / campaign.workspace_id
                / "tracks"
                / campaign.track_id
                / "promotions"
                / f"{candidate.promotion_id}.patch"
            )
            promotion_artifacts.append(
                {
                    "promotion_id": candidate.promotion_id,
                    "promotion_path": str(promotion_path),
                    "diff_path": str(diff_path) if diff_path.exists() else None,
                }
            )
    champion_artifacts = None
    try:
        champion = load_champion_manifest(
            root=root,
            workspace_id=campaign.workspace_id,
            track_id=campaign.track_id,
        )
    except FileNotFoundError:
        champion = None
    if champion is not None:
        champion_artifacts = {
            "record_id": champion.record_id,
            "promotion_id": champion.promotion_id,
            "manifest_path": str(
                root
                / campaign.workspace_id
                / "tracks"
                / campaign.track_id
                / "champion.json"
            ),
            "record_path": champion.record_path,
            "promotion_path": champion.promotion_path,
            "diff_path": champion.diff_path,
        }
    return {
        "workspace_id": campaign.workspace_id,
        "track_id": campaign.track_id,
        "campaign_id": campaign.campaign_run_id,
        "campaign_path": str(
            campaign_run_path(
                root=root,
                workspace_id=campaign.workspace_id,
                track_id=campaign.track_id,
                campaign_run_id=campaign.campaign_run_id,
            )
        ),
        "proposal_artifacts": proposal_artifacts,
        "record_artifacts": record_artifacts,
        "iteration_artifacts": iteration_artifacts,
        "promotion_artifacts": promotion_artifacts,
        "champion_artifacts": champion_artifacts,
    }


def _render_campaign_report(
    *,
    root: Path,
    campaign: CampaignRun,
) -> dict[str, object]:
    proposals = []
    records = []
    iterations = []
    promotions = []
    for candidate in campaign.candidates:
        if candidate.proposal_id is not None:
            try:
                proposal = load_proposal(
                    root=root,
                    workspace_id=campaign.workspace_id,
                    track_id=campaign.track_id,
                    proposal_id=candidate.proposal_id,
                )
            except FileNotFoundError:
                proposal = None
            if proposal is not None:
                proposals.append(proposal.to_dict())
        if candidate.record_id is not None:
            try:
                record = load_benchmark_record(
                    root=root,
                    workspace_id=campaign.workspace_id,
                    track_id=campaign.track_id,
                    record_id=candidate.record_id,
                )
            except FileNotFoundError:
                record = None
            if record is not None:
                records.append(record.to_dict())
        if candidate.iteration_id is not None:
            try:
                iteration_summary = load_iteration_summary(
                    root=root,
                    workspace_id=campaign.workspace_id,
                    iteration_id=candidate.iteration_id,
                )
            except FileNotFoundError:
                iteration_summary = None
            if iteration_summary is not None:
                iterations.append(iteration_summary)
        if candidate.promotion_id is not None:
            try:
                promotion = load_promotion_record(
                    root=root,
                    workspace_id=campaign.workspace_id,
                    track_id=campaign.track_id,
                    promotion_id=candidate.promotion_id,
                )
            except FileNotFoundError:
                promotion = None
            if promotion is not None:
                promotions.append(promotion.to_dict())
    try:
        champion = load_champion_manifest(
            root=root,
            workspace_id=campaign.workspace_id,
            track_id=campaign.track_id,
        )
    except FileNotFoundError:
        champion = None
    provider_profiles = load_provider_profiles(
        root=root,
        workspace_id=campaign.workspace_id,
        track_id=campaign.track_id,
    )
    campaign_events = load_workspace_events(
        root=root,
        workspace_id=campaign.workspace_id,
        campaign_run_id=campaign.campaign_run_id,
        track_id=campaign.track_id,
    )
    return {
        "workspace_id": campaign.workspace_id,
        "track_id": campaign.track_id,
        "campaign": campaign.to_dict(),
        "provider_profiles": {
            "profile_path": str(
                provider_profiles_path(
                    root=root,
                    workspace_id=campaign.workspace_id,
                    track_id=campaign.track_id,
                )
            ),
            "profile_total": len(provider_profiles),
            "profiles": provider_profiles,
            "profile_summaries": summarize_provider_profiles(provider_profiles),
        },
        "event_total": len(campaign_events),
        "event_metrics": aggregate_event_metrics(campaign_events),
        "campaign_events": campaign_events,
        "proposals": proposals,
        "records": records,
        "iterations": iterations,
        "promotions": promotions,
        "champion": champion.to_dict() if champion is not None else None,
    }


def _execute_campaign(
    *,
    root: Path,
    campaign: CampaignRun,
    worker_id: str | None = None,
    lease_seconds: int = 300,
) -> CampaignRun:
    candidates = list(campaign.candidates)
    decision_log = list(campaign.decision_log)
    success_count = campaign.success_count
    failure_count = campaign.failure_count
    inconclusive_count = campaign.inconclusive_count
    no_improvement_streak = campaign.no_improvement_streak
    promoted_count = campaign.promoted_count
    active_stage = campaign.stage
    desired_state = campaign.desired_state
    resource_usage = _campaign_resource_usage(root=root, campaign=campaign)
    seen_proposal_ids = {
        proposal_id
        for candidate in candidates
        if isinstance((proposal_id := candidate.proposal_id), str)
    }
    seen_record_ids = {
        record_id
        for candidate in candidates
        if isinstance((record_id := candidate.record_id), str)
    }
    for entry in decision_log:
        if isinstance(entry.proposal_id, str):
            seen_proposal_ids.add(entry.proposal_id)
        if isinstance(entry.record_id, str):
            seen_record_ids.add(entry.record_id)

    def _checkpoint(*, status: str, stop_reason: str | None, next_index: int) -> CampaignRun:
        checkpoint = replace(
            campaign,
            updated_at=_utc_now(),
            stage=active_stage,
            desired_state=desired_state,
            status=status,
            stop_reason=stop_reason,
            next_candidate_index=next_index,
            candidates=tuple(candidates),
            success_count=success_count,
            failure_count=failure_count,
            inconclusive_count=inconclusive_count,
            no_improvement_streak=no_improvement_streak,
            promoted_count=promoted_count,
            decision_log=tuple(decision_log),
        )
        if campaign.execution_mode == "background" and worker_id is not None:
            checkpoint = replace(
                checkpoint,
                lease_owner=worker_id,
                lease_claimed_at=checkpoint.lease_claimed_at or _utc_now(),
                lease_heartbeat_at=_utc_now(),
                lease_expires_at=(
                    datetime.now(UTC) + timedelta(seconds=max(lease_seconds, 1))
                ).isoformat().replace("+00:00", "Z"),
            )
        persist_campaign_run(root=root, campaign=checkpoint)
        if campaign.execution_mode == "background" and worker_id is not None:
            heartbeat_workspace_campaign_lease(
                root=root,
                workspace_id=campaign.workspace_id,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
        return checkpoint

    def _append_decision(
        event: str,
        *,
        candidate_index: int | None = None,
        proposal_id: str | None = None,
        record_id: str | None = None,
        promotion_id: str | None = None,
        status: str | None = None,
        failure_class: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        entry = CampaignDecisionLogEntry(
            created_at=_utc_now(),
            event=event,
            candidate_index=candidate_index,
            proposal_id=proposal_id,
            record_id=record_id,
            promotion_id=promotion_id,
            status=status,
            failure_class=failure_class,
            details=dict(details or {}),
        )
        decision_log.append(entry)
        append_workspace_event(
            root=root,
            workspace_id=campaign.workspace_id,
            track_id=campaign.track_id,
            campaign_run_id=campaign.campaign_run_id,
            proposal_id=proposal_id,
            record_id=record_id,
            promotion_id=promotion_id,
            status=status,
            event_type=event,
            generator_id=campaign.generator_id,
            provider_id=campaign.generator_id,
            adapter_id=campaign.adapter_id,
            details={
                "candidate_index": candidate_index,
                "failure_class": failure_class,
                **dict(details or {}),
            },
            created_at=entry.created_at,
        )

    def _pause_campaign(*, stop_reason: str, next_index: int, status: str = "paused") -> CampaignRun:
        _append_decision(
            "campaign_stopped",
            status=status,
            details={"stop_reason": stop_reason, "next_candidate_index": next_index},
        )
        checkpoint = _checkpoint(status=status, stop_reason=stop_reason, next_index=next_index)
        if campaign.execution_mode == "background" and worker_id is not None:
            checkpoint = release_campaign_run(
                root=root,
                campaign=checkpoint,
                final_status=status,
                stop_reason=stop_reason,
            )
            release_workspace_campaign_lease(
                root=root,
                workspace_id=campaign.workspace_id,
                worker_id=worker_id,
            )
        return checkpoint

    def _refresh_control_state() -> CampaignRun:
        nonlocal desired_state
        if campaign.execution_mode != "background":
            return campaign
        latest = load_campaign_run(
            root=root,
            workspace_id=campaign.workspace_id,
            track_id=campaign.track_id,
            campaign_run_id=campaign.campaign_run_id,
        )
        desired_state = latest.desired_state
        return latest

    def _schedule_retry(
        *,
        index: int,
        candidate: CampaignCandidateRun,
        failure_class: str,
        error: str | None,
        details: dict[str, object] | None = None,
    ) -> bool:
        retry_limit = _retry_limit_for_failure_class(campaign, failure_class)
        retries_used = int(candidate.retry_counts.get(failure_class, 0))
        if retries_used >= retry_limit:
            _append_decision(
                "candidate_retry_exhausted",
                candidate_index=index,
                proposal_id=candidate.proposal_id,
                record_id=candidate.record_id,
                status=candidate.status,
                failure_class=failure_class,
                details={
                    "retry_count": retries_used,
                    "retry_limit": retry_limit,
                    **dict(details or {}),
                },
            )
            return False
        retry_counts = dict(candidate.retry_counts)
        retry_counts[failure_class] = retries_used + 1
        candidates[index] = replace(
            candidate,
            status="pending",
            failure_class=failure_class,
            error=error,
            retry_counts=retry_counts,
        )
        _append_decision(
            "candidate_retry_scheduled",
            candidate_index=index,
            proposal_id=candidate.proposal_id,
            record_id=candidate.record_id,
            status="pending",
            failure_class=failure_class,
            details={
                "retry_count": retry_counts[failure_class],
                "retry_limit": retry_limit,
                **dict(details or {}),
            },
        )
        _checkpoint(status="running", stop_reason=None, next_index=index)
        return True

    def _prune_pending_beam_group_candidates(
        *,
        winner_index: int,
        reason: str,
        proposal_id: str | None,
        record_id: str | None,
        promotion_id: str | None,
        status: str,
    ) -> list[int]:
        if not strategy_uses_beam(campaign.strategy):
            return []
        winner = candidates[winner_index]
        beam_group_index = winner.generation_request.get("beam_group_index")
        if not isinstance(beam_group_index, int):
            return []
        pruned_indices: list[int] = []
        for candidate_index, candidate in enumerate(candidates):
            if candidate_index == winner_index:
                continue
            if candidate.status != "pending":
                continue
            if candidate.generation_request.get("beam_group_index") != beam_group_index:
                continue
            candidates[candidate_index] = replace(
                candidate,
                status="pruned",
                failure_class=None,
                error=None,
            )
            pruned_indices.append(candidate_index)
        if pruned_indices:
            _append_decision(
                "beam_group_pruned",
                candidate_index=winner_index,
                proposal_id=proposal_id,
                record_id=record_id,
                promotion_id=promotion_id,
                status=status,
                details={
                    "beam_group_index": beam_group_index,
                    "pruned_candidate_indices": pruned_indices,
                    "reason": reason,
                },
            )
        return pruned_indices

    def _source_single_generator_candidate(index: int) -> CampaignCandidateRun:
        intervention_class = _resolve_intervention_class(campaign, candidate_index=index)
        generated_candidate = CampaignCandidateRun(
            index=index,
            source_mode="generator_generated",
            intervention_class=intervention_class,
            generation_request={
                "format_version": "autoharness.proposal_generation_request.v1",
                "candidate_index": index,
                "strategy_id": campaign.strategy,
                "source_mode": campaign.candidate_source_mode,
                "campaign_run_id": campaign.campaign_run_id,
                "intervention_class": intervention_class,
                "stage": active_stage,
            },
        )
        candidates.append(generated_candidate)
        _append_decision(
            "candidate_sourced",
            candidate_index=index,
            details={
                "source_mode": generated_candidate.source_mode,
                "intervention_class": intervention_class,
                "stage": active_stage,
            },
        )
        _checkpoint(status="running", stop_reason=None, next_index=index)
        return generated_candidate

    def _source_beam_group(group_number: int, *, beam_width: int) -> bool:
        group_start = group_number * beam_width
        state = load_workspace_state(root, campaign.workspace_id)
        latest_failure_summary, latest_regression_summary = load_latest_generation_signals(
            root=root,
            workspace_id=campaign.workspace_id,
            track_id=campaign.track_id,
            state=state,
        )
        failure_focus_task_ids, regressed_task_ids = resolve_focus_task_ids(
            strategy_id=campaign.strategy,
            candidate_index=group_number,
            latest_failure_summary=latest_failure_summary,
            latest_regression_summary=latest_regression_summary,
        )
        sourced_any = False
        for slot_index in range(beam_width):
            candidate_index = group_start + slot_index
            if candidate_index < len(candidates):
                continue
            intervention_class = _resolve_intervention_class(
                campaign,
                candidate_index=candidate_index,
            )
            generated_candidate = CampaignCandidateRun(
                index=candidate_index,
                source_mode="generator_generated",
                intervention_class=intervention_class,
                generation_request={
                    "format_version": "autoharness.proposal_generation_request.v1",
                    "candidate_index": candidate_index,
                    "strategy_id": campaign.strategy,
                    "source_mode": campaign.candidate_source_mode,
                    "campaign_run_id": campaign.campaign_run_id,
                    "intervention_class": intervention_class,
                    "stage": active_stage,
                    "beam_group_index": group_number,
                    "beam_slot_index": slot_index,
                    "beam_width": beam_width,
                    "failure_focus_task_ids": list(failure_focus_task_ids),
                    "regressed_task_ids": list(regressed_task_ids),
                },
            )
            candidates.append(generated_candidate)
            sourced_any = True
            _append_decision(
                "candidate_sourced",
                candidate_index=candidate_index,
                details={
                    "source_mode": generated_candidate.source_mode,
                    "intervention_class": intervention_class,
                    "stage": active_stage,
                    "beam_group_index": group_number,
                    "beam_slot_index": slot_index,
                    "beam_width": beam_width,
                    "failure_focus_task_ids": list(failure_focus_task_ids),
                    "regressed_task_ids": list(regressed_task_ids),
                },
            )
        if sourced_any:
            _checkpoint(status="running", stop_reason=None, next_index=group_start)
        return sourced_any

    def _active_beam_group_indices() -> set[int]:
        active_groups: set[int] = set()
        for candidate in candidates:
            if candidate.status not in {"pending", "running"}:
                continue
            group_index = candidate.generation_request.get("beam_group_index")
            if isinstance(group_index, int):
                active_groups.add(group_index)
        return active_groups

    def _next_beam_group_number() -> int:
        group_indices = [
            int(group_index)
            for candidate in candidates
            if isinstance(
                (group_index := candidate.generation_request.get("beam_group_index")),
                int,
            )
        ]
        return max(group_indices) + 1 if group_indices else 0

    def _ensure_candidate_pool(start_index: int) -> None:
        if campaign.candidate_source_mode != "generator_loop":
            return
        beam_width = campaign.beam_width if strategy_uses_beam(campaign.strategy) else None
        if beam_width is None or beam_width < 2:
            if start_index >= len(candidates):
                _source_single_generator_candidate(start_index)
            return
        beam_group_limit = max(int(campaign.beam_group_limit or 1), 1)
        active_group_indices = _active_beam_group_indices()
        next_group_number = _next_beam_group_number()
        while len(active_group_indices) < beam_group_limit:
            if not _source_beam_group(next_group_number, beam_width=beam_width):
                break
            active_group_indices.add(next_group_number)
            next_group_number += 1

    def _attempted_intervention_classes() -> set[str]:
        attempted: set[str] = set()
        for candidate in candidates:
            if candidate.status in {"pending", "pruned"}:
                continue
            if isinstance(candidate.intervention_class, str) and candidate.intervention_class:
                attempted.add(candidate.intervention_class)
        return attempted

    def _candidate_snapshot(candidate) -> dict[str, object]:
        generation_request = dict(candidate.generation_request)
        if "stage" not in generation_request and active_stage:
            generation_request["stage"] = active_stage
        retry_count_total = sum(int(value) for value in candidate.retry_counts.values())
        snapshot: dict[str, object] = {
            "index": candidate.index,
            "attempt_count": candidate.attempt_count,
            "retry_count_total": retry_count_total,
            "status": candidate.status,
            "failure_class": candidate.failure_class,
            "intervention_class": candidate.intervention_class,
            "generation_request": generation_request,
            "promoted": candidate.promoted,
            "comparison_decision": candidate.comparison_decision,
        }
        if isinstance(candidate.branch_score_rationale, dict):
            for key in (
                "flaky",
                "benchmark_cost",
                "benchmark_duration_seconds",
                "stability_score",
                "confidence_interval_width",
            ):
                if key in candidate.branch_score_rationale:
                    snapshot[key] = candidate.branch_score_rationale[key]
        return snapshot

    def _pending_candidate_score(candidate) -> tuple[float, dict[str, object]]:
        return compute_candidate_branch_score(
            strategy_id=campaign.strategy,
            candidate_snapshot=_candidate_snapshot(candidate),
            attempted_intervention_classes=_attempted_intervention_classes(),
        )

    def _select_beam_candidate_index() -> int | None:
        candidate_snapshots: list[dict[str, object]] = []
        attempted_intervention_classes = _attempted_intervention_classes()
        for candidate in candidates:
            candidate_snapshots.append(_candidate_snapshot(candidate))

        group_outcomes = summarize_beam_group_outcomes(candidate_snapshots)
        pending_candidates: list[tuple[tuple[int, ...], int]] = []
        for candidate_index, candidate in enumerate(candidates):
            if candidate.status != "pending":
                continue
            candidate_snapshot = _candidate_snapshot(candidate)
            branch_score = None
            if strategy_uses_scoring(campaign.strategy):
                branch_score, _branch_rationale = _pending_candidate_score(candidate)
            pending_candidates.append(
                (
                    rank_beam_candidate(
                        strategy_id=campaign.strategy,
                        candidate_snapshot=candidate_snapshot,
                        group_outcomes=group_outcomes,
                        attempted_intervention_classes=attempted_intervention_classes,
                        branch_score=branch_score,
                    ),
                    candidate_index,
                )
            )
        if not pending_candidates:
            return None
        pending_candidates.sort(key=lambda item: item[0])
        return pending_candidates[0][1]

    def _select_scored_candidate_index() -> int | None:
        pending_rankings: list[tuple[tuple[float, int, int], int]] = []
        attempted_interventions = _attempted_intervention_classes()
        flaky_interventions = {
            candidate.intervention_class
            for candidate in candidates
            if candidate.branch_score_rationale.get("flaky") is True
            and isinstance(candidate.intervention_class, str)
            and candidate.intervention_class
        }
        for candidate_index, candidate in enumerate(candidates):
            if candidate.status != "pending":
                continue
            branch_score, _rationale = compute_candidate_branch_score(
                strategy_id=campaign.strategy,
                candidate_snapshot=_candidate_snapshot(candidate),
                attempted_intervention_classes=attempted_interventions,
            )
            intervention_class = candidate.intervention_class
            exploration_penalty = 0
            if campaign.strategy == "explore_then_exploit":
                exploration_penalty = (
                    0
                    if isinstance(intervention_class, str)
                    and intervention_class
                    and intervention_class not in attempted_interventions
                    else 1
                )
            flaky_penalty = 0
            if (
                campaign.strategy == "stability_weighted"
                and isinstance(intervention_class, str)
                and intervention_class in flaky_interventions
            ):
                flaky_penalty = 1
            pending_rankings.append(
                (
                    (
                        float(exploration_penalty),
                        float(flaky_penalty),
                        -branch_score,
                        int(candidate.index),
                    ),
                    candidate_index,
                )
            )
        if not pending_rankings:
            return None
        pending_rankings.sort(key=lambda item: item[0])
        return pending_rankings[0][1]

    def _select_next_candidate_index(start_index: int) -> int:
        beam_width = campaign.beam_width if strategy_uses_beam(campaign.strategy) else None
        if beam_width is not None and beam_width >= 2:
            selected_index = _select_beam_candidate_index()
            if selected_index is not None:
                return selected_index
        if strategy_uses_scoring(campaign.strategy):
            selected_index = _select_scored_candidate_index()
            if selected_index is not None:
                return selected_index
        return _next_runnable_candidate_index(candidates, start_index=start_index)

    def _maybe_auto_promote(
        *,
        record,
        state,
        candidate_stage: str,
    ) -> tuple[bool, str | None, str | None]:
        if not campaign.auto_promote:
            return False, None, None
        if not campaign.allow_flaky_promotion and _record_is_flaky(record):
            return False, "provisional_winner", None
        if not stage_meets_minimum(candidate_stage, campaign.auto_promote_min_stage):
            return False, "auto_promote_min_stage_not_reached", None
        stage_evaluation = record.payload.get("stage_evaluation")
        if not isinstance(stage_evaluation, dict) or stage_evaluation.get("passed") is not True:
            return False, "stage_gate_failed", None
        stability_gate = _record_stability_gate(record)
        if isinstance(stability_gate, dict) and stability_gate.get("applies") is True:
            if stability_gate.get("passed") is not True:
                if bool(stability_gate.get("flaky")) and campaign.allow_flaky_promotion:
                    pass
                else:
                    return False, (
                        "provisional_winner"
                        if bool(stability_gate.get("flaky"))
                        else "stability_gate_failed"
                    ), None

        promotion_target_root = Path(campaign.promotion_target_root or campaign.target_root)
        try:
            load_champion_manifest(
                root=root,
                workspace_id=campaign.workspace_id,
                track_id=campaign.track_id,
            )
        except FileNotFoundError:
            promoted = _promote_record(
                root=root,
                workspace_id=campaign.workspace_id,
                state=state,
                track_id=campaign.track_id,
                record=record,
                target_root=promotion_target_root,
                notes="automatic campaign promotion",
            )
            return True, "promoted_without_prior_champion", str(
                promoted["promotion"]["promotion_id"]
            )

        comparison = _compute_champion_comparison(
            root=root,
            workspace_id=campaign.workspace_id,
            requested_track_id=campaign.track_id,
            record_id=record.record_id,
            stage=None,
            min_success_rate=None,
            min_improvement=None,
            max_regressed_tasks=None,
            max_regressed_task_fraction=None,
            max_regressed_task_weight=None,
            max_regressed_task_weight_fraction=None,
            task_regression_margin=None,
        )
        rendered_comparison = comparison["rendered"]
        baseline_comparison = rendered_comparison["stage_evaluation"].get("baseline_comparison")
        if (
            rendered_comparison["candidate_is_current_champion"]
            or rendered_comparison["stage_evaluation"].get("passed") is not True
            or not isinstance(baseline_comparison, dict)
            or baseline_comparison.get("passed") is not True
        ):
            return False, (
                baseline_comparison.get("decision")
                if isinstance(baseline_comparison, dict)
                else rendered_comparison["stage_evaluation"].get("decision")
            ), None
        promoted = _promote_record(
            root=root,
            workspace_id=campaign.workspace_id,
            state=state,
            track_id=campaign.track_id,
            record=record,
            target_root=promotion_target_root,
            notes="automatic campaign promotion",
        )
        return True, (
            baseline_comparison.get("decision")
            if isinstance(baseline_comparison, dict)
            else "promoted"
        ), str(promoted["promotion"]["promotion_id"])

    index = campaign.next_candidate_index
    while True:
        live_campaign = _refresh_control_state()
        if campaign.execution_mode == "background":
            if desired_state == "paused":
                return _pause_campaign(
                    stop_reason="pause_requested",
                    next_index=index,
                    status="paused",
                )
            if desired_state == "canceled":
                return _pause_campaign(
                    stop_reason="cancel_requested",
                    next_index=index,
                    status="canceled",
                )
            if worker_id is not None and live_campaign.lease_owner not in {None, worker_id}:
                return _pause_campaign(
                    stop_reason="lease_lost",
                    next_index=index,
                    status="paused",
                )
        index = _next_runnable_candidate_index(candidates, start_index=index)
        if (
            campaign.max_iterations is not None
            and _candidate_attempt_total(candidates) >= campaign.max_iterations
        ):
            return _pause_campaign(
                stop_reason="iteration_budget_reached",
                next_index=index,
                status="completed",
            )
        if campaign.max_runtime_seconds is not None:
            elapsed_seconds = int((datetime.now(UTC) - _parse_utc_timestamp(campaign.created_at)).total_seconds())
            if elapsed_seconds >= campaign.max_runtime_seconds:
                return _pause_campaign(stop_reason="time_budget_reached", next_index=index)
        if (
            campaign.max_generation_total_tokens is not None
            and int(resource_usage["generation_total_tokens"])
            >= campaign.max_generation_total_tokens
        ):
            return _pause_campaign(
                stop_reason="generation_token_budget_reached",
                next_index=index,
                status="completed",
            )
        if (
            campaign.max_benchmark_total_cost is not None
            and float(resource_usage["benchmark_total_cost"])
            >= campaign.max_benchmark_total_cost
        ):
            return _pause_campaign(
                stop_reason="benchmark_cost_budget_reached",
                next_index=index,
                status="completed",
            )
        if campaign.candidate_source_mode == "manual_edit_plan_list" and index >= len(candidates):
            return _pause_campaign(
                stop_reason="proposal_list_exhausted",
                next_index=index,
                status="completed",
            )
        processed_this_run = _candidate_attempt_total(candidates) - campaign.next_candidate_index
        if campaign.max_proposals is not None and processed_this_run >= campaign.max_proposals:
            return _pause_campaign(stop_reason="proposal_budget_reached", next_index=index)

        _ensure_candidate_pool(index)
        index = _select_next_candidate_index(index)
        candidate = candidates[index] if index < len(candidates) else None
        if candidate is None:
            terminal_reason = (
                "proposal_list_exhausted"
                if campaign.candidate_source_mode == "manual_edit_plan_list"
                else "candidate_source_exhausted"
            )
            return _pause_campaign(
                stop_reason=terminal_reason,
                next_index=index,
                status="completed",
            )
        while True:
            candidate = candidates[index]
            candidate = replace(candidate, attempt_count=candidate.attempt_count + 1)
            candidates[index] = candidate
            branch_score = None
            branch_score_rationale: dict[str, object] | None = None
            if strategy_uses_scoring(campaign.strategy):
                branch_score, branch_score_rationale = _pending_candidate_score(candidate)
            _append_decision(
                "candidate_attempt_started",
                candidate_index=index,
                proposal_id=candidate.proposal_id,
                status="running",
                failure_class=candidate.failure_class,
                details={
                    "attempt_count": candidate.attempt_count,
                    "reuse_proposal": (
                        candidate.proposal_id is not None
                        and candidate.failure_class in _PROPOSAL_REUSE_FAILURE_CLASSES
                    ),
                    "branch_score": branch_score,
                    "branch_score_rationale": branch_score_rationale,
                },
            )
            _checkpoint(status="running", stop_reason=None, next_index=index)

            reuse_existing_proposal = (
                candidate.proposal_id is not None
                and candidate.failure_class in _PROPOSAL_REUSE_FAILURE_CLASSES
            )
            proposal_id = candidate.proposal_id if reuse_existing_proposal else None
            candidate_hypothesis = candidate.hypothesis
            candidate_stage = active_stage

            if proposal_id is None:
                generation_request = dict(candidate.generation_request)
                if not generation_request.get("failure_focus_task_ids") and not generation_request.get(
                    "regressed_task_ids"
                ):
                    state = load_workspace_state(root, campaign.workspace_id)
                    latest_failure_summary, latest_regression_summary = load_latest_generation_signals(
                        root=root,
                        workspace_id=campaign.workspace_id,
                        track_id=campaign.track_id,
                        state=state,
                    )
                    failure_focus_task_ids, regressed_task_ids = resolve_focus_task_ids(
                        strategy_id=campaign.strategy,
                        candidate_index=index,
                        latest_failure_summary=latest_failure_summary,
                        latest_regression_summary=latest_regression_summary,
                    )
                    generation_request["failure_focus_task_ids"] = list(failure_focus_task_ids)
                    generation_request["regressed_task_ids"] = list(regressed_task_ids)
                    generation_request["stage"] = candidate_stage
                    candidate = replace(candidate, generation_request=generation_request)
                    candidates[index] = candidate
                    _append_decision(
                        "candidate_focus_selected",
                        candidate_index=index,
                        proposal_id=proposal_id,
                        status="planned",
                        details={
                            "stage": candidate_stage,
                            "failure_focus_task_ids": list(failure_focus_task_ids),
                            "regressed_task_ids": list(regressed_task_ids),
                        },
                    )
                    _checkpoint(status="running", stop_reason=None, next_index=index)
                generate_args = argparse.Namespace(
                    workspace_id=campaign.workspace_id,
                    adapter=campaign.adapter_id,
                    config=Path(campaign.config_path) if campaign.config_path is not None else None,
                    preset=campaign.preset,
                    set=list(campaign.inline_overrides),
                    edit_plan=Path(candidate.edit_plan_path) if candidate.edit_plan_path is not None else None,
                    hypothesis=None,
                    summary=None,
                    notes="",
                    generator=campaign.generator_id,
                    intervention_class=candidate.intervention_class,
                    track_id=campaign.track_id,
                    root=root,
                    stage=candidate_stage,
                    target_root=Path(campaign.target_root),
                    json=True,
                    output=None,
                    generation_candidate_index=index,
                    generation_strategy_id=campaign.strategy,
                    generation_source_mode=campaign.candidate_source_mode,
                    campaign_run_id=campaign.campaign_run_id,
                    generation_metadata={
                        **dict(campaign.generator_metadata),
                        **dict(candidate.generation_request),
                    },
                    failure_focus_task_ids=tuple(candidate.generation_request.get("failure_focus_task_ids", ())),
                    regressed_task_ids=tuple(candidate.generation_request.get("regressed_task_ids", ())),
                    hypothesis_seed=candidate.hypothesis,
                )
                try:
                    _, generated = _capture_handler_json(
                        _handle_generate_proposal,
                        generate_args,
                    )
                    proposal = generated["proposal"]
                    proposal_id = str(proposal["proposal_id"])
                    candidate_hypothesis = (
                        str(proposal["hypothesis"])
                        if proposal.get("hypothesis") is not None
                        else None
                    )
                    proposal_generator_metadata = proposal.get("generator_metadata")
                    generator_attempts = []
                    if isinstance(proposal_generator_metadata, dict):
                        raw_attempts = proposal_generator_metadata.get("generator_attempts")
                        if isinstance(raw_attempts, list):
                            generator_attempts = [
                                entry for entry in raw_attempts if isinstance(entry, dict)
                            ]
                    _append_decision(
                        "proposal_generated",
                        candidate_index=index,
                        proposal_id=proposal_id,
                        status="generated",
                        details={
                            "intervention_class": candidate.intervention_class,
                            "generator_id": str(
                                proposal.get("generator_id", campaign.generator_id)
                            ),
                            "attempt_count": candidate.attempt_count,
                            "generator_attempt_count": len(generator_attempts),
                            "fallback_used": len(generator_attempts) > 1,
                        },
                    )
                    if proposal_id not in seen_proposal_ids:
                        proposal_metadata = proposal.get("generator_metadata")
                        if isinstance(proposal_metadata, dict):
                            resource_usage = _add_resource_usage(
                                resource_usage,
                                _proposal_resource_usage_from_metadata(proposal_metadata),
                            )
                        seen_proposal_ids.add(proposal_id)
                except (SystemExit, KeyError, json.JSONDecodeError) as exc:
                    generation_error = str(exc)
                    failure_class = _classify_generation_exception(exc)
                    retry_scheduled = _schedule_retry(
                        index=index,
                        candidate=replace(
                            candidate,
                            proposal_id=None,
                            iteration_id=None,
                            record_id=None,
                            promotion_id=None,
                            promoted=False,
                            comparison_decision=None,
                        ),
                        failure_class=failure_class,
                        error=generation_error,
                        details={"attempt_count": candidate.attempt_count},
                    )
                    if retry_scheduled:
                        continue
                    candidates[index] = replace(
                        candidate,
                        status="error",
                        proposal_id=None,
                        iteration_id=None,
                        record_id=None,
                        promotion_id=None,
                        promoted=False,
                        comparison_decision=None,
                        failure_class=failure_class,
                        error=generation_error,
                    )
                    failure_count += 1
                    no_improvement_streak += 1
                    _append_decision(
                        "candidate_failed",
                        candidate_index=index,
                        status="error",
                        failure_class=failure_class,
                        details={
                            "error": generation_error,
                            "attempt_count": candidate.attempt_count,
                        },
                    )
                    _checkpoint(status="running", stop_reason=None, next_index=index + 1)
                    if campaign.max_failures is not None and failure_count >= campaign.max_failures:
                        return _pause_campaign(
                            stop_reason="failure_budget_reached",
                            next_index=index + 1,
                            status="failed",
                        )
                    if (
                        campaign.no_improvement_limit is not None
                        and no_improvement_streak >= campaign.no_improvement_limit
                    ):
                        return _pause_campaign(
                            stop_reason="no_improvement_limit_reached",
                            next_index=index + 1,
                        )
                    index += 1
                    break

            run_args = argparse.Namespace(
                workspace_id=campaign.workspace_id,
                track_id=campaign.track_id,
                proposal_id=proposal_id,
                root=root,
                target_root=None,
                keep_applied_edits=False,
                staging_mode="auto",
                dry_run=campaign.dry_run,
                preflight_command=list(campaign.preflight_commands),
                preflight_timeout_seconds=campaign.preflight_timeout_seconds or 60,
                repeat=campaign.repeat_count,
                output=None,
            )
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    exit_code = _handle_run_proposal(run_args)
            except SystemExit as exc:
                exit_code = int(exc.code) if isinstance(exc.code, int) else 1

            if exit_code != 0:
                execution_error = f"run-proposal exited with {exit_code}"
                retry_scheduled = _schedule_retry(
                    index=index,
                    candidate=replace(
                        candidate,
                        hypothesis=candidate_hypothesis,
                        proposal_id=proposal_id,
                        iteration_id=None,
                        record_id=None,
                        promotion_id=None,
                        promoted=False,
                        comparison_decision=None,
                    ),
                    failure_class="execution_error",
                    error=execution_error,
                    details={"attempt_count": candidate.attempt_count},
                )
                if retry_scheduled:
                    continue
                candidate_status = "error"
                candidate_error = execution_error
                record_id = None
                iteration_id = None
                promoted = False
                comparison_decision = None
                promotion_id = None
            else:
                candidate_status = "completed"
                candidate_error = None
                record_id = None
                iteration_id = None
                promoted = False
                comparison_decision = None
                promotion_id = None
                record = None
                state = load_workspace_state(root, campaign.workspace_id)
                record_id = state.last_experiment_id
                iteration_id = state.last_iteration_id
                if record_id is not None:
                    record = load_benchmark_record(
                        root=root,
                        workspace_id=campaign.workspace_id,
                        track_id=campaign.track_id,
                        record_id=record_id,
                    )
                    if record_id not in seen_record_ids:
                        resource_usage = _add_resource_usage(
                            resource_usage,
                            _record_resource_usage_from_payload(record.payload),
                        )
                        seen_record_ids.add(record_id)
                    candidate_status = record.status
                    record_failure_class = _classify_record_failure(record)
                    retryable_record_failure_class = None
                    if candidate_status == "inconclusive":
                        retryable_record_failure_class = "benchmark_inconclusive"
                    elif record_failure_class == "benchmark_process_error":
                        retryable_record_failure_class = "benchmark_process_error"
                    elif record_failure_class == "benchmark_signal_error":
                        retryable_record_failure_class = "benchmark_signal_error"
                    elif record_failure_class in {
                        "benchmark_metrics_parse_error",
                        "benchmark_task_results_parse_error",
                        "benchmark_artifact_parse_error",
                    }:
                        retryable_record_failure_class = record_failure_class
                    elif record_failure_class == "benchmark_adapter_validation_error":
                        retryable_record_failure_class = (
                            "benchmark_adapter_validation_error"
                        )
                    elif record_failure_class == "benchmark_timeout":
                        retryable_record_failure_class = "benchmark_timeout"
                    elif record_failure_class == "benchmark_command_failed":
                        retryable_record_failure_class = "benchmark_command_failed"
                    elif record_failure_class == "preflight_failed":
                        retryable_record_failure_class = "preflight_failed"
                    else:
                        stability_gate = _record_stability_gate(record)
                        if candidate_status == "success" and (
                            _record_is_flaky(record)
                            or (
                                isinstance(stability_gate, dict)
                                and stability_gate.get("applies") is True
                                and stability_gate.get("passed") is not True
                            )
                        ):
                            retryable_record_failure_class = "unstable_validation"
                    if retryable_record_failure_class is not None:
                        retry_scheduled = _schedule_retry(
                            index=index,
                            candidate=replace(
                                candidate,
                                hypothesis=candidate_hypothesis,
                                proposal_id=proposal_id,
                                iteration_id=iteration_id,
                                record_id=record_id,
                            ),
                            failure_class=retryable_record_failure_class,
                            error=None,
                            details={
                                "attempt_count": candidate.attempt_count,
                                "iteration_id": iteration_id,
                                "record_id": record_id,
                            },
                        )
                        if retry_scheduled:
                            continue
                    promoted, comparison_decision, promotion_id = _maybe_auto_promote(
                        record=record,
                        state=state,
                        candidate_stage=candidate_stage,
                    )
                    if candidate_status == "success":
                        success_count += 1
                    elif candidate_status == "inconclusive":
                        inconclusive_count += 1

            if exit_code == 0 and record is not None:
                final_failure_class = _classify_record_failure(record)
            else:
                final_failure_class = _classify_candidate_failure(
                    candidate_status=candidate_status,
                    exit_code=None if exit_code == 0 else exit_code,
                )
            completed_snapshot = _candidate_snapshot(candidate)
            completed_snapshot["status"] = candidate_status
            completed_snapshot["failure_class"] = final_failure_class
            completed_snapshot["promoted"] = promoted
            if record is not None:
                record_resource_usage = _record_resource_usage_from_payload(record.payload)
                completed_snapshot["flaky"] = _record_is_flaky(record)
                completed_snapshot["benchmark_cost"] = record_resource_usage[
                    "benchmark_total_cost"
                ]
                completed_snapshot["benchmark_duration_seconds"] = record_resource_usage[
                    "benchmark_total_duration_seconds"
                ]
                stability_score = _record_stability_score(record)
                if stability_score is not None:
                    completed_snapshot["stability_score"] = stability_score
                confidence_interval_width = _record_confidence_interval_width(record)
                if confidence_interval_width is not None:
                    completed_snapshot["confidence_interval_width"] = (
                        confidence_interval_width
                    )
                baseline_comparison = record.payload.get("stage_evaluation", {}).get(
                    "baseline_comparison"
                ) if isinstance(record.payload.get("stage_evaluation"), dict) else None
                if isinstance(baseline_comparison, dict):
                    baseline_decision = baseline_comparison.get("decision")
                    if isinstance(baseline_decision, str) and baseline_decision:
                        completed_snapshot["comparison_decision"] = baseline_decision
            branch_score, branch_score_rationale = compute_candidate_branch_score(
                strategy_id=campaign.strategy,
                candidate_snapshot=completed_snapshot,
                attempted_intervention_classes=_attempted_intervention_classes(),
            )
            if record is not None:
                branch_score_rationale["benchmark_cost"] = completed_snapshot.get(
                    "benchmark_cost"
                )
                branch_score_rationale["benchmark_duration_seconds"] = completed_snapshot.get(
                    "benchmark_duration_seconds"
                )
            candidates[index] = replace(
                candidate,
                hypothesis=candidate_hypothesis,
                proposal_id=proposal_id,
                iteration_id=iteration_id,
                record_id=record_id,
                promotion_id=promotion_id,
                promoted=promoted,
                comparison_decision=comparison_decision,
                branch_score=branch_score,
                branch_score_rationale=branch_score_rationale,
                status=candidate_status,
                failure_class=final_failure_class,
                error=candidate_error,
            )
            if candidate_status in {"failed", "error"}:
                failure_count += 1
            improved = promoted or candidate_status == "success"
            if improved:
                no_improvement_streak = 0
            else:
                no_improvement_streak += 1
            _append_decision(
                "candidate_completed",
                candidate_index=index,
                proposal_id=proposal_id,
                record_id=record_id,
                promotion_id=promotion_id,
                status=candidate_status,
                failure_class=final_failure_class,
                details={
                    "attempt_count": candidate.attempt_count,
                    "stage": candidate_stage,
                    "iteration_id": iteration_id,
                    "comparison_decision": comparison_decision,
                    "promoted": promoted,
                    "branch_score": branch_score,
                    "branch_score_rationale": branch_score_rationale,
                },
            )
            next_stage = resolve_next_stage(
                current_stage=candidate_stage,
                stage_progression_mode=campaign.stage_progression_mode,
                candidate_status=candidate_status,
                promoted=promoted,
            )
            if next_stage != candidate_stage:
                active_stage = next_stage
                _append_decision(
                    "campaign_stage_advanced",
                    candidate_index=index,
                    proposal_id=proposal_id,
                    record_id=record_id,
                    promotion_id=promotion_id,
                    status=candidate_status,
                    details={
                        "from_stage": candidate_stage,
                        "to_stage": next_stage,
                        "stage_progression_mode": campaign.stage_progression_mode,
                    },
                )
            next_index = _next_runnable_candidate_index(candidates, start_index=index + 1)
            if promoted:
                promoted_count += 1
                _append_decision(
                    "candidate_promoted",
                    candidate_index=index,
                    proposal_id=proposal_id,
                    record_id=record_id,
                    promotion_id=promotion_id,
                    status=candidate_status,
                    details={"attempt_count": candidate.attempt_count},
                )
                _prune_pending_beam_group_candidates(
                    winner_index=index,
                    reason="candidate_promoted",
                    proposal_id=proposal_id,
                    record_id=record_id,
                    promotion_id=promotion_id,
                    status=candidate_status,
                )
                if campaign.stop_on_first_promotion:
                    return _pause_campaign(
                        stop_reason="promotion_found",
                        next_index=_next_runnable_candidate_index(
                            candidates,
                            start_index=index + 1,
                        ),
                        status="completed",
                    )
            elif candidate_status == "success":
                _prune_pending_beam_group_candidates(
                    winner_index=index,
                    reason="candidate_success",
                    proposal_id=proposal_id,
                    record_id=record_id,
                    promotion_id=promotion_id,
                    status=candidate_status,
                )
            next_index = _next_runnable_candidate_index(candidates, start_index=index + 1)
            _checkpoint(status="running", stop_reason=None, next_index=next_index)
            if (
                campaign.max_successes is not None
                and success_count >= campaign.max_successes
            ):
                return _pause_campaign(
                    stop_reason="success_budget_reached",
                    next_index=next_index,
                    status="completed",
                )
            if (
                campaign.max_promotions is not None
                and promoted_count >= campaign.max_promotions
            ):
                return _pause_campaign(
                    stop_reason="promotion_budget_reached",
                    next_index=next_index,
                    status="completed",
                )
            if campaign.max_failures is not None and failure_count >= campaign.max_failures:
                return _pause_campaign(
                    stop_reason="failure_budget_reached",
                    next_index=next_index,
                    status="failed",
                )
            if (
                campaign.max_inconclusive is not None
                and inconclusive_count >= campaign.max_inconclusive
            ):
                return _pause_campaign(
                    stop_reason="inconclusive_budget_reached",
                    next_index=next_index,
                )
            if (
                campaign.no_improvement_limit is not None
                and no_improvement_streak >= campaign.no_improvement_limit
            ):
                return _pause_campaign(
                    stop_reason="no_improvement_limit_reached",
                    next_index=next_index,
                )
            index = next_index
            break

def _handle_run_campaign(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    if not isinstance(args.adapter, str) or not args.adapter.strip():
        raise SystemExit(
            "`--adapter` is required unless provided by autoharness project config."
        )
    workspace, _, track_id = _resolve_workspace_track(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    effective_campaign_policy, _ = _resolve_track_campaign_policy(
        workspace=workspace,
        track_id=track_id,
    )
    stage = args.stage or str(effective_campaign_policy["stage"])
    stage_progression_mode = (
        args.stage_progression
        if getattr(args, "stage_progression", None) is not None
        else str(effective_campaign_policy["stage_progression_mode"])
    )
    generator_id = args.generator or str(effective_campaign_policy["generator_id"])
    strategy = args.strategy or str(effective_campaign_policy["strategy"])
    beam_width = (
        args.beam_width
        if getattr(args, "beam_width", None) is not None
        else effective_campaign_policy.get("beam_width")
    )
    beam_group_limit = getattr(args, "beam_groups", None)
    if beam_group_limit is None:
        beam_group_limit = effective_campaign_policy.get("beam_group_limit")
    repeat_count = (
        args.repeat
        if getattr(args, "repeat", None) is not None
        else effective_campaign_policy.get("repeat_count")
    )
    intervention_classes = (
        tuple(args.intervention_class)
        if args.intervention_class
        else tuple(
            str(entry)
            for entry in effective_campaign_policy.get("intervention_classes", [])
        )
    )
    explicit_preflight_commands = list(getattr(args, "preflight_command", []))
    explicit_preflight_checks = list(getattr(args, "preflight_check", []))
    if explicit_preflight_commands or explicit_preflight_checks:
        selected_preflight_checks = tuple(str(entry) for entry in explicit_preflight_checks)
        try:
            preflight_resolution = resolve_effective_preflight_commands(
                commands=explicit_preflight_commands,
                checks=explicit_preflight_checks,
                stage=stage,
                adapter_id=args.adapter,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        preflight_commands = list(preflight_resolution["resolved_commands"])
        selected_preflight_checks = tuple(preflight_resolution["selected_checks"])
    else:
        policy_preflight_commands = [
            str(entry)
            for entry in effective_campaign_policy.get("preflight_commands", [])
        ]
        policy_preflight_checks = [
            str(entry)
            for entry in effective_campaign_policy.get("preflight_checks", [])
        ]
        try:
            preflight_resolution = resolve_effective_preflight_commands(
                commands=policy_preflight_commands,
                checks=policy_preflight_checks,
                stage=stage,
                adapter_id=args.adapter,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        preflight_commands = list(preflight_resolution["resolved_commands"])
        selected_preflight_checks = tuple(preflight_resolution["selected_checks"])
    preflight_timeout_seconds = (
        args.preflight_timeout_seconds
        if getattr(args, "preflight_timeout_seconds", None) is not None
        else effective_campaign_policy.get("preflight_timeout_seconds")
    )
    generator_metadata = (
        _parse_generator_options(list(args.generator_option))
        if args.generator_option
        else {
            str(key): str(value)
            for key, value in dict(
                effective_campaign_policy.get("generator_metadata", {})
            ).items()
        }
    )
    max_proposals = (
        args.max_proposals
        if args.max_proposals is not None
        else effective_campaign_policy.get("max_proposals")
    )
    max_iterations = (
        args.max_iterations
        if args.max_iterations is not None
        else effective_campaign_policy.get("max_iterations")
    )
    max_successes = (
        args.max_successes
        if args.max_successes is not None
        else effective_campaign_policy.get("max_successes")
    )
    max_promotions = (
        args.max_promotions
        if args.max_promotions is not None
        else effective_campaign_policy.get("max_promotions")
    )
    max_failures = (
        args.max_failures
        if args.max_failures is not None
        else effective_campaign_policy.get("max_failures")
    )
    max_inconclusive = (
        args.max_inconclusive
        if args.max_inconclusive is not None
        else effective_campaign_policy.get("max_inconclusive")
    )
    max_runtime_seconds = (
        args.time_budget_seconds
        if args.time_budget_seconds is not None
        else effective_campaign_policy.get("max_runtime_seconds")
    )
    max_generation_total_tokens = (
        args.max_generation_total_tokens
        if args.max_generation_total_tokens is not None
        else effective_campaign_policy.get("max_generation_total_tokens")
    )
    max_benchmark_total_cost = (
        args.max_benchmark_total_cost
        if args.max_benchmark_total_cost is not None
        else effective_campaign_policy.get("max_benchmark_total_cost")
    )
    max_generation_retries = (
        args.max_generation_retries
        if args.max_generation_retries is not None
        else effective_campaign_policy.get("max_generation_retries")
    )
    max_generation_timeout_retries = (
        args.max_generation_timeout_retries
        if args.max_generation_timeout_retries is not None
        else effective_campaign_policy.get("max_generation_timeout_retries")
    )
    max_generation_provider_retries = (
        args.max_generation_provider_retries
        if args.max_generation_provider_retries is not None
        else effective_campaign_policy.get("max_generation_provider_retries")
    )
    max_generation_provider_transport_retries = (
        args.max_generation_provider_transport_retries
        if args.max_generation_provider_transport_retries is not None
        else effective_campaign_policy.get("max_generation_provider_transport_retries")
    )
    max_generation_provider_auth_retries = (
        args.max_generation_provider_auth_retries
        if args.max_generation_provider_auth_retries is not None
        else effective_campaign_policy.get("max_generation_provider_auth_retries")
    )
    max_generation_provider_rate_limit_retries = (
        args.max_generation_provider_rate_limit_retries
        if args.max_generation_provider_rate_limit_retries is not None
        else effective_campaign_policy.get("max_generation_provider_rate_limit_retries")
    )
    max_generation_process_retries = (
        args.max_generation_process_retries
        if args.max_generation_process_retries is not None
        else effective_campaign_policy.get("max_generation_process_retries")
    )
    max_preflight_retries = (
        args.max_preflight_retries
        if args.max_preflight_retries is not None
        else effective_campaign_policy.get("max_preflight_retries")
    )
    max_execution_retries = (
        args.max_execution_retries
        if args.max_execution_retries is not None
        else effective_campaign_policy.get("max_execution_retries")
    )
    max_benchmark_process_retries = (
        args.max_benchmark_process_retries
        if args.max_benchmark_process_retries is not None
        else effective_campaign_policy.get("max_benchmark_process_retries")
    )
    max_benchmark_signal_retries = (
        args.max_benchmark_signal_retries
        if args.max_benchmark_signal_retries is not None
        else effective_campaign_policy.get("max_benchmark_signal_retries")
    )
    max_benchmark_parse_retries = (
        args.max_benchmark_parse_retries
        if args.max_benchmark_parse_retries is not None
        else effective_campaign_policy.get("max_benchmark_parse_retries")
    )
    max_benchmark_adapter_validation_retries = (
        args.max_benchmark_adapter_validation_retries
        if args.max_benchmark_adapter_validation_retries is not None
        else effective_campaign_policy.get("max_benchmark_adapter_validation_retries")
    )
    max_benchmark_timeout_retries = (
        args.max_benchmark_timeout_retries
        if args.max_benchmark_timeout_retries is not None
        else effective_campaign_policy.get("max_benchmark_timeout_retries")
    )
    max_benchmark_command_retries = (
        args.max_benchmark_command_retries
        if args.max_benchmark_command_retries is not None
        else effective_campaign_policy.get("max_benchmark_command_retries")
    )
    max_inconclusive_retries = (
        args.max_inconclusive_retries
        if args.max_inconclusive_retries is not None
        else effective_campaign_policy.get("max_inconclusive_retries")
    )
    no_improvement_limit = (
        args.no_improvement_limit
        if args.no_improvement_limit is not None
        else effective_campaign_policy.get("no_improvement_limit")
    )
    auto_promote = (
        args.auto_promote
        if args.auto_promote is not None
        else bool(effective_campaign_policy["auto_promote"])
    )
    allow_flaky_promotion = (
        args.allow_flaky_promotion
        if getattr(args, "allow_flaky_promotion", None) is not None
        else bool(effective_campaign_policy.get("allow_flaky_promotion", False))
    )
    auto_promote_min_stage = args.auto_promote_min_stage
    if auto_promote_min_stage is None:
        policy_auto_promote_min_stage = effective_campaign_policy.get(
            "auto_promote_min_stage"
        )
        if isinstance(policy_auto_promote_min_stage, str) and policy_auto_promote_min_stage:
            auto_promote_min_stage = policy_auto_promote_min_stage
    stop_on_first_promotion = (
        args.stop_on_first_promotion
        if args.stop_on_first_promotion is not None
        else bool(effective_campaign_policy["stop_on_first_promotion"])
    )
    promotion_target_root = args.promotion_target_root
    if promotion_target_root is None:
        policy_promotion_target_root = effective_campaign_policy.get(
            "promotion_target_root"
        )
        if isinstance(policy_promotion_target_root, str) and policy_promotion_target_root:
            promotion_target_root = Path(policy_promotion_target_root)

    if generator_id == "manual" and not args.edit_plan:
        raise SystemExit("Provide at least one --edit-plan for run-campaign when using `manual`.")
    candidate_source_mode = (
        "manual_edit_plan_list" if args.edit_plan else "generator_loop"
    )
    if candidate_source_mode == "generator_loop" and strategy == "sequential_manual":
        strategy = "greedy_failure_focus"
    if strategy_uses_beam(strategy) and beam_width is None:
        beam_width = max(len(intervention_classes), 2) if intervention_classes else 2
    if strategy_uses_beam(strategy) and beam_group_limit is None:
        beam_group_limit = 1
    if beam_group_limit is not None and beam_group_limit < 1:
        raise SystemExit("`--beam-groups` must be greater than zero.")
    campaign = create_campaign_run(
        workspace_id=args.workspace_id,
        track_id=track_id,
        adapter_id=args.adapter,
        stage=stage,
        stage_progression_mode=stage_progression_mode,
        generator_id=generator_id,
        strategy=strategy,
        beam_width=beam_width,
        beam_group_limit=beam_group_limit,
        repeat_count=repeat_count,
        candidate_source_mode=candidate_source_mode,
        target_root=args.target_root,
        config_path=args.config,
        preset=args.preset,
        inline_overrides=list(args.set),
        intervention_classes=intervention_classes,
        preflight_checks=selected_preflight_checks,
        preflight_commands=tuple(preflight_commands),
        preflight_timeout_seconds=preflight_timeout_seconds,
        generator_metadata=generator_metadata,
        dry_run=args.dry_run,
        max_proposals=max_proposals,
        max_iterations=max_iterations,
        max_successes=max_successes,
        max_promotions=max_promotions,
        max_failures=max_failures,
        max_inconclusive=max_inconclusive,
        max_runtime_seconds=max_runtime_seconds,
        max_generation_total_tokens=max_generation_total_tokens,
        max_benchmark_total_cost=max_benchmark_total_cost,
        max_generation_retries=max_generation_retries,
        max_generation_timeout_retries=max_generation_timeout_retries,
        max_generation_provider_retries=max_generation_provider_retries,
        max_generation_provider_transport_retries=(
            max_generation_provider_transport_retries
        ),
        max_generation_provider_auth_retries=max_generation_provider_auth_retries,
        max_generation_provider_rate_limit_retries=(
            max_generation_provider_rate_limit_retries
        ),
        max_generation_process_retries=max_generation_process_retries,
        max_preflight_retries=max_preflight_retries,
        max_execution_retries=max_execution_retries,
        max_benchmark_process_retries=max_benchmark_process_retries,
        max_benchmark_signal_retries=max_benchmark_signal_retries,
        max_benchmark_parse_retries=max_benchmark_parse_retries,
        max_benchmark_adapter_validation_retries=(
            max_benchmark_adapter_validation_retries
        ),
        max_benchmark_timeout_retries=max_benchmark_timeout_retries,
        max_benchmark_command_retries=max_benchmark_command_retries,
        max_inconclusive_retries=max_inconclusive_retries,
        no_improvement_limit=no_improvement_limit,
        auto_promote=auto_promote,
        allow_flaky_promotion=allow_flaky_promotion,
        auto_promote_min_stage=auto_promote_min_stage,
        stop_on_first_promotion=stop_on_first_promotion,
        promotion_target_root=promotion_target_root,
        edit_plan_paths=list(args.edit_plan),
        execution_mode="background" if getattr(args, "background", False) else "foreground",
    )
    persist_campaign_run(root=args.root, campaign=campaign)
    append_workspace_event(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        campaign_run_id=campaign.campaign_run_id,
        status=campaign.status,
        event_type="campaign_created",
        generator_id=campaign.generator_id,
        provider_id=campaign.generator_id,
        adapter_id=campaign.adapter_id,
        details={
            "execution_mode": campaign.execution_mode,
            "strategy": campaign.strategy,
            "generator_id": campaign.generator_id,
            "stage": campaign.stage,
        },
    )
    if getattr(args, "background", False):
        rendered = _render_campaign(campaign, root=args.root)
        if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
            return 0
        print(f"Workspace: {args.workspace_id}")
        print(f"Track: {track_id}")
        print(f"Campaign run: {campaign.campaign_run_id}")
        print("Status: queued")
        print("Execution mode: background")
        if args.output is not None:
            print(f"Wrote output to {args.output}")
        return 0
    campaign = _execute_campaign(root=args.root, campaign=campaign)
    rendered = _render_campaign(campaign, root=args.root)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Campaign run: {campaign.campaign_run_id}")
    print(f"Status: {campaign.status}")
    print(f"Stage: {campaign.stage}")
    print(f"Strategy: {campaign.strategy}")
    if campaign.beam_width is not None:
        print(f"Beam width: {campaign.beam_width}")
    if campaign.beam_group_limit is not None:
        print(f"Beam groups: {campaign.beam_group_limit}")
    print(f"Source mode: {campaign.candidate_source_mode}")
    if campaign.auto_promote_min_stage is not None:
        print(f"Auto-promote minimum stage: {campaign.auto_promote_min_stage}")
    print(f"Stop reason: {campaign.stop_reason}")
    print(f"Candidates: {len(campaign.candidates)}")
    print(f"Completed candidates: {rendered['completed_candidate_total']}")
    print(f"Successes: {rendered['success_count']}")
    print(f"Failures: {rendered['failure_count']}")
    print(f"Inconclusive: {rendered['inconclusive_count']}")
    print(f"Promotions: {rendered['promoted_count']}")
    print(f"Pruned candidates: {rendered['pruned_candidate_total']}")
    print(f"Attempts: {rendered['attempt_total']}")
    resource_usage = rendered["resource_usage"]
    assert isinstance(resource_usage, dict)
    print(f"Generation tokens: {resource_usage['generation_total_tokens']}")
    print(f"Generation seconds: {resource_usage['generation_total_duration_seconds']}")
    print(f"Benchmark cost: {resource_usage['benchmark_total_cost']}")
    print(
        f"Benchmark seconds: {resource_usage['benchmark_total_duration_seconds']}"
    )
    if rendered["failure_class_counts"]:
        print(f"Failure classes: {rendered['failure_class_counts']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _claim_next_background_campaign(
    *,
    root: Path,
    workspace_ids: list[str],
    track_ids: list[str],
    worker_id: str,
    lease_seconds: int,
) -> CampaignRun | None:
    for campaign in list_runnable_campaign_runs(
        root=root,
        workspace_ids=workspace_ids,
        track_ids=track_ids,
    ):
        if not claim_workspace_campaign_lease(
            root=root,
            workspace_id=campaign.workspace_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        ):
            continue
        claimed = claim_campaign_run(
            root=root,
            workspace_id=campaign.workspace_id,
            track_id=campaign.track_id,
            campaign_run_id=campaign.campaign_run_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        if claimed is None:
            release_workspace_campaign_lease(
                root=root,
                workspace_id=campaign.workspace_id,
                worker_id=worker_id,
            )
            continue
        append_workspace_event(
            root=root,
            workspace_id=claimed.workspace_id,
            track_id=claimed.track_id,
            campaign_run_id=claimed.campaign_run_id,
            status=claimed.status,
            event_type="campaign_claimed",
            generator_id=claimed.generator_id,
            provider_id=claimed.generator_id,
            adapter_id=claimed.adapter_id,
            details={"worker_id": worker_id},
        )
        return claimed
    return None


def _run_campaign_worker(
    *,
    root: Path,
    workspace_ids: list[str],
    track_ids: list[str],
    worker_id: str,
    lease_seconds: int,
    max_campaigns: int | None,
) -> dict[str, object]:
    processed: list[dict[str, object]] = []
    while max_campaigns is None or len(processed) < max_campaigns:
        campaign = _claim_next_background_campaign(
            root=root,
            workspace_ids=workspace_ids,
            track_ids=track_ids,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        if campaign is None:
            break
        completed = _execute_campaign(
            root=root,
            campaign=campaign,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        processed.append(
            {
                "workspace_id": completed.workspace_id,
                "track_id": completed.track_id,
                "campaign_id": completed.campaign_run_id,
                "status": completed.status,
                "stop_reason": completed.stop_reason,
            }
        )
    return {
        "worker_id": worker_id,
        "claimed_campaign_total": len(processed),
        "campaigns": processed,
    }


def _launched_campaign_item_from_track_run(
    track_run: dict[str, object],
    *,
    workspace_id: str | None = None,
) -> dict[str, object] | None:
    rendered = track_run.get("rendered")
    if not isinstance(rendered, dict):
        return None
    campaign_payload = rendered.get("campaign")
    if not isinstance(campaign_payload, dict):
        return None
    item = {
        "track_id": track_run.get("track_id"),
        "campaign_id": campaign_payload.get("campaign_run_id"),
        "stage": campaign_payload.get("stage"),
        "stage_progression_mode": campaign_payload.get("stage_progression_mode"),
        "generator_id": campaign_payload.get("generator_id"),
        "strategy": campaign_payload.get("strategy"),
        "beam_width": campaign_payload.get("beam_width"),
        "beam_group_limit": campaign_payload.get("beam_group_limit"),
        "repeat_count": campaign_payload.get("repeat_count"),
        "candidate_source_mode": campaign_payload.get("candidate_source_mode"),
        "preflight_enabled": bool(campaign_payload.get("preflight_commands")),
        "preflight_checks": list(campaign_payload.get("preflight_checks", [])),
        "preflight_check_count": len(campaign_payload.get("preflight_checks", [])),
        "preflight_command_count": len(campaign_payload.get("preflight_commands", [])),
        "preflight_timeout_seconds": campaign_payload.get("preflight_timeout_seconds"),
        "max_generation_total_tokens": campaign_payload.get("max_generation_total_tokens"),
        "max_benchmark_total_cost": campaign_payload.get("max_benchmark_total_cost"),
        "max_generation_retries": campaign_payload.get("max_generation_retries"),
        "max_generation_timeout_retries": campaign_payload.get(
            "max_generation_timeout_retries"
        ),
        "max_generation_provider_retries": campaign_payload.get(
            "max_generation_provider_retries"
        ),
        "max_generation_provider_transport_retries": campaign_payload.get(
            "max_generation_provider_transport_retries"
        ),
        "max_generation_provider_auth_retries": campaign_payload.get(
            "max_generation_provider_auth_retries"
        ),
        "max_generation_provider_rate_limit_retries": campaign_payload.get(
            "max_generation_provider_rate_limit_retries"
        ),
        "max_generation_process_retries": campaign_payload.get(
            "max_generation_process_retries"
        ),
        "max_preflight_retries": campaign_payload.get("max_preflight_retries"),
        "max_execution_retries": campaign_payload.get("max_execution_retries"),
        "max_benchmark_process_retries": campaign_payload.get(
            "max_benchmark_process_retries"
        ),
        "max_benchmark_signal_retries": campaign_payload.get(
            "max_benchmark_signal_retries"
        ),
        "max_benchmark_parse_retries": campaign_payload.get(
            "max_benchmark_parse_retries"
        ),
        "max_benchmark_adapter_validation_retries": campaign_payload.get(
            "max_benchmark_adapter_validation_retries"
        ),
        "max_benchmark_timeout_retries": campaign_payload.get(
            "max_benchmark_timeout_retries"
        ),
        "max_benchmark_command_retries": campaign_payload.get(
            "max_benchmark_command_retries"
        ),
        "max_inconclusive_retries": campaign_payload.get("max_inconclusive_retries"),
        "auto_promote": campaign_payload.get("auto_promote"),
        "allow_flaky_promotion": campaign_payload.get("allow_flaky_promotion"),
        "auto_promote_min_stage": campaign_payload.get("auto_promote_min_stage"),
        "stop_on_first_promotion": campaign_payload.get("stop_on_first_promotion"),
        "resource_usage": rendered.get("resource_usage"),
    }
    if workspace_id is not None:
        item["workspace_id"] = workspace_id
    return item


def _render_workspace_campaign_batch_result(
    *,
    root: Path,
    workspace_id: str,
    track_runs: list[dict[str, object]],
) -> dict[str, object]:
    launched_campaign_items = [
        item
        for item in (
            _launched_campaign_item_from_track_run(track_run)
            for track_run in track_runs
        )
        if item is not None
    ]
    failed_track_total = sum(
        1
        for item in track_runs
        if item.get("exit_code") != 0
        or item.get("campaign_status") in {"failed", "error"}
    )
    status = "partial" if failed_track_total > 0 else "completed"
    stop_reason = "track_campaign_failed" if failed_track_total > 0 else "all_tracks_completed"
    return {
        "workspace_id": workspace_id,
        "track_total": len(track_runs),
        "completed_track_total": len(track_runs),
        "success_track_total": sum(
            1 for item in track_runs if item.get("campaign_status") == "completed"
        ),
        "failed_track_total": failed_track_total,
        "status": status,
        "stop_reason": stop_reason,
        "search_policy_mix": _summarize_campaign_search_policy_mix(
            launched_campaign_items
        ),
        "resource_usage": _summarize_campaign_resource_usage(launched_campaign_items),
        "event_metrics": aggregate_event_metrics(
            load_workspace_events(root=root, workspace_id=workspace_id)
        ),
        "tracks": track_runs,
    }


def _refresh_workspace_run_after_workers(
    *,
    root: Path,
    workspace_result: dict[str, object],
) -> dict[str, object]:
    workspace_id = workspace_result.get("workspace_id")
    rendered = workspace_result.get("rendered")
    if not isinstance(workspace_id, str) or not isinstance(rendered, dict):
        return workspace_result
    raw_track_runs = rendered.get("tracks")
    if not isinstance(raw_track_runs, list):
        return workspace_result
    refreshed_track_runs: list[dict[str, object]] = []
    for raw_track_run in raw_track_runs:
        if not isinstance(raw_track_run, dict):
            continue
        refreshed_track_run = dict(raw_track_run)
        track_id = raw_track_run.get("track_id")
        campaign_id = raw_track_run.get("campaign_id")
        if isinstance(track_id, str) and isinstance(campaign_id, str):
            try:
                campaign = load_campaign_run(
                    root=root,
                    workspace_id=workspace_id,
                    track_id=track_id,
                    campaign_run_id=campaign_id,
                )
            except FileNotFoundError:
                pass
            else:
                refreshed_track_run["campaign_status"] = campaign.status
                refreshed_track_run["campaign_stop_reason"] = campaign.stop_reason
                refreshed_track_run["rendered"] = _render_campaign(campaign, root=root)
        refreshed_track_runs.append(refreshed_track_run)
    refreshed_rendered = _render_workspace_campaign_batch_result(
        root=root,
        workspace_id=workspace_id,
        track_runs=refreshed_track_runs,
    )
    return {
        **workspace_result,
        "status": refreshed_rendered["status"],
        "stop_reason": refreshed_rendered["stop_reason"],
        "rendered": refreshed_rendered,
    }


def _run_local_worker_pool(
    *,
    root: Path,
    workspace_ids: list[str],
    track_ids: list[str],
    workers: int,
    lease_seconds: int,
    campaign_total: int,
) -> list[dict[str, object]]:
    worker_total = max(workers, 1)
    remaining_campaign_total = max(campaign_total, 0)
    if remaining_campaign_total == 0:
        return []

    worker_quotas: list[int] = []
    base_quota, remainder = divmod(remaining_campaign_total, worker_total)
    for worker_index in range(worker_total):
        quota = base_quota + (1 if worker_index < remainder else 0)
        if quota > 0:
            worker_quotas.append(quota)

    rendered: list[dict[str, object]] = []
    with ProcessPoolExecutor(max_workers=worker_total) as executor:
        futures = [
            executor.submit(
                _run_campaign_worker,
                root=root,
                workspace_ids=workspace_ids,
                track_ids=track_ids,
                worker_id=f"worker_pool_{worker_index + 1:02d}",
                lease_seconds=lease_seconds,
                max_campaigns=quota,
            )
            for worker_index, quota in enumerate(worker_quotas)
        ]
        for future in as_completed(futures):
            rendered.append(future.result())
    rendered.sort(key=lambda item: str(item.get("worker_id")))
    return rendered


def _handle_run_workspace_campaigns(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.root, args.workspace_id)
    selected_track_ids = [
        track_id
        for track_id in sorted(workspace.tracks)
        if workspace.tracks[track_id].status == "active"
        and (not args.track_id or track_id in set(args.track_id))
    ]
    if not selected_track_ids:
        raise SystemExit("No active tracks matched the requested workspace campaign run.")

    track_runs: list[dict[str, object]] = []
    launched_campaign_items: list[dict[str, object]] = []
    status = "completed"
    stop_reason = "all_tracks_completed"

    for track_id in selected_track_ids:
        target_root = args.target_root_base / track_id
        target_root.mkdir(parents=True, exist_ok=True)
        promotion_target_root = None
        if args.promotion_target_root_base is not None:
            promotion_target_root = args.promotion_target_root_base / track_id
            promotion_target_root.mkdir(parents=True, exist_ok=True)
        exit_code, rendered = _capture_handler_json(
            _handle_run_campaign,
            _run_campaign_args_for_track(
                args=args,
                track_id=track_id,
                target_root=target_root,
                promotion_target_root=promotion_target_root,
            ),
        )
        campaign_payload = rendered.get("campaign")
        campaign_status = None
        campaign_stop_reason = None
        campaign_id = None
        if isinstance(campaign_payload, dict):
            campaign_status = campaign_payload.get("status")
            campaign_stop_reason = campaign_payload.get("stop_reason")
            campaign_id = campaign_payload.get("campaign_run_id")
            launched_campaign_items.append(
                {
                    "track_id": track_id,
                    "campaign_id": campaign_id,
                    "stage": campaign_payload.get("stage"),
                    "stage_progression_mode": campaign_payload.get(
                        "stage_progression_mode"
                    ),
                    "generator_id": campaign_payload.get("generator_id"),
                    "strategy": campaign_payload.get("strategy"),
                    "beam_width": campaign_payload.get("beam_width"),
                    "beam_group_limit": campaign_payload.get("beam_group_limit"),
                    "repeat_count": campaign_payload.get("repeat_count"),
                    "candidate_source_mode": campaign_payload.get(
                        "candidate_source_mode"
                    ),
                    "preflight_enabled": bool(
                        campaign_payload.get("preflight_commands")
                    ),
                    "preflight_checks": list(
                        campaign_payload.get("preflight_checks", [])
                    ),
                    "preflight_check_count": len(
                        campaign_payload.get("preflight_checks", [])
                    ),
                    "preflight_command_count": len(
                        campaign_payload.get("preflight_commands", [])
                    ),
                    "preflight_timeout_seconds": campaign_payload.get(
                        "preflight_timeout_seconds"
                    ),
                    "max_generation_total_tokens": campaign_payload.get(
                        "max_generation_total_tokens"
                    ),
                    "max_benchmark_total_cost": campaign_payload.get(
                        "max_benchmark_total_cost"
                    ),
                    "max_generation_retries": campaign_payload.get(
                        "max_generation_retries"
                    ),
                    "max_generation_timeout_retries": campaign_payload.get(
                        "max_generation_timeout_retries"
                    ),
                    "max_generation_provider_retries": campaign_payload.get(
                        "max_generation_provider_retries"
                    ),
                    "max_generation_provider_transport_retries": campaign_payload.get(
                        "max_generation_provider_transport_retries"
                    ),
                    "max_generation_provider_auth_retries": campaign_payload.get(
                        "max_generation_provider_auth_retries"
                    ),
                    "max_generation_provider_rate_limit_retries": campaign_payload.get(
                        "max_generation_provider_rate_limit_retries"
                    ),
                    "max_generation_process_retries": campaign_payload.get(
                        "max_generation_process_retries"
                    ),
                    "max_preflight_retries": campaign_payload.get(
                        "max_preflight_retries"
                    ),
                    "max_execution_retries": campaign_payload.get(
                        "max_execution_retries"
                    ),
                    "max_benchmark_process_retries": campaign_payload.get(
                        "max_benchmark_process_retries"
                    ),
                    "max_benchmark_signal_retries": campaign_payload.get(
                        "max_benchmark_signal_retries"
                    ),
                    "max_benchmark_parse_retries": campaign_payload.get(
                        "max_benchmark_parse_retries"
                    ),
                    "max_benchmark_adapter_validation_retries": campaign_payload.get(
                        "max_benchmark_adapter_validation_retries"
                    ),
                    "max_benchmark_timeout_retries": campaign_payload.get(
                        "max_benchmark_timeout_retries"
                    ),
                    "max_benchmark_command_retries": campaign_payload.get(
                        "max_benchmark_command_retries"
                    ),
                    "max_inconclusive_retries": campaign_payload.get(
                        "max_inconclusive_retries"
                    ),
                    "auto_promote": campaign_payload.get("auto_promote"),
                    "allow_flaky_promotion": campaign_payload.get(
                        "allow_flaky_promotion"
                    ),
                    "auto_promote_min_stage": campaign_payload.get(
                        "auto_promote_min_stage"
                    ),
                    "stop_on_first_promotion": campaign_payload.get(
                        "stop_on_first_promotion"
                    ),
                    "resource_usage": rendered.get("resource_usage"),
                }
            )
        track_result = {
            "track_id": track_id,
            "target_root": str(target_root.resolve()),
            "promotion_target_root": (
                str(promotion_target_root.resolve())
                if promotion_target_root is not None
                else None
            ),
            "exit_code": exit_code,
            "campaign_id": campaign_id,
            "campaign_status": campaign_status,
            "campaign_stop_reason": campaign_stop_reason,
            "rendered": rendered,
        }
        track_runs.append(track_result)
        track_failed = (
            exit_code != 0
            or campaign_status in {"failed", "error"}
        )
        if track_failed and not args.continue_on_failure:
            status = "failed"
            stop_reason = "track_campaign_failed"
            break
        if track_failed:
            status = "partial"
            stop_reason = "track_campaign_failed"

    rendered = {
        "workspace_id": args.workspace_id,
        "track_total": len(selected_track_ids),
        "completed_track_total": len(track_runs),
        "success_track_total": sum(
            1 for item in track_runs if item.get("campaign_status") == "completed"
        ),
        "failed_track_total": sum(
            1
            for item in track_runs
            if item.get("exit_code") != 0 or item.get("campaign_status") in {"failed", "error"}
        ),
        "status": status,
        "stop_reason": stop_reason,
        "search_policy_mix": _summarize_campaign_search_policy_mix(
            launched_campaign_items
        ),
        "resource_usage": _summarize_campaign_resource_usage(launched_campaign_items),
        "event_metrics": aggregate_event_metrics(
            load_workspace_events(root=args.root, workspace_id=args.workspace_id)
        ),
        "tracks": track_runs,
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Tracks run: {len(track_runs)}/{len(selected_track_ids)}")
    print(f"Status: {status}")
    print(f"Stop reason: {stop_reason}")
    _print_resource_usage_summary(rendered["resource_usage"])
    search_policy_mix = rendered["search_policy_mix"]
    assert isinstance(search_policy_mix, dict)
    by_generator_id = search_policy_mix["by_generator_id"]
    by_strategy = search_policy_mix["by_strategy"]
    by_stage_progression_mode = search_policy_mix["by_stage_progression_mode"]
    by_candidate_source_mode = search_policy_mix["by_candidate_source_mode"]
    by_beam_width = search_policy_mix["by_beam_width"]
    by_beam_group_limit = search_policy_mix["by_beam_group_limit"]
    by_repeat_count = search_policy_mix["by_repeat_count"]
    by_preflight_check_count = search_policy_mix["by_preflight_check_count"]
    by_max_generation_total_tokens = search_policy_mix["by_max_generation_total_tokens"]
    by_max_benchmark_total_cost = search_policy_mix["by_max_benchmark_total_cost"]
    by_max_generation_retries = search_policy_mix["by_max_generation_retries"]
    by_max_generation_timeout_retries = search_policy_mix[
        "by_max_generation_timeout_retries"
    ]
    by_max_generation_provider_retries = search_policy_mix[
        "by_max_generation_provider_retries"
    ]
    by_max_generation_process_retries = search_policy_mix[
        "by_max_generation_process_retries"
    ]
    by_max_execution_retries = search_policy_mix["by_max_execution_retries"]
    by_max_benchmark_timeout_retries = search_policy_mix[
        "by_max_benchmark_timeout_retries"
    ]
    by_max_benchmark_command_retries = search_policy_mix[
        "by_max_benchmark_command_retries"
    ]
    by_max_inconclusive_retries = search_policy_mix["by_max_inconclusive_retries"]
    by_auto_promote = search_policy_mix["by_auto_promote"]
    by_allow_flaky_promotion = search_policy_mix["by_allow_flaky_promotion"]
    by_auto_promote_min_stage = search_policy_mix["by_auto_promote_min_stage"]
    by_stop_on_first_promotion = search_policy_mix["by_stop_on_first_promotion"]
    assert isinstance(by_generator_id, dict)
    assert isinstance(by_strategy, dict)
    assert isinstance(by_stage_progression_mode, dict)
    assert isinstance(by_candidate_source_mode, dict)
    assert isinstance(by_beam_width, dict)
    assert isinstance(by_beam_group_limit, dict)
    assert isinstance(by_repeat_count, dict)
    assert isinstance(by_preflight_check_count, dict)
    assert isinstance(by_max_generation_total_tokens, dict)
    assert isinstance(by_max_benchmark_total_cost, dict)
    assert isinstance(by_max_generation_retries, dict)
    assert isinstance(by_max_generation_timeout_retries, dict)
    assert isinstance(by_max_generation_provider_retries, dict)
    assert isinstance(by_max_generation_process_retries, dict)
    assert isinstance(by_max_execution_retries, dict)
    assert isinstance(by_max_benchmark_timeout_retries, dict)
    assert isinstance(by_max_benchmark_command_retries, dict)
    assert isinstance(by_max_inconclusive_retries, dict)
    assert isinstance(by_auto_promote, dict)
    assert isinstance(by_allow_flaky_promotion, dict)
    assert isinstance(by_auto_promote_min_stage, dict)
    assert isinstance(by_stop_on_first_promotion, dict)
    print("Generator mix: " + _format_count_map(by_generator_id))
    print("Strategy mix: " + _format_count_map(by_strategy))
    print("Stage progression mix: " + _format_count_map(by_stage_progression_mode))
    print("Source mode mix: " + _format_count_map(by_candidate_source_mode))
    print("Beam width mix: " + _format_count_map(by_beam_width))
    print("Beam group mix: " + _format_count_map(by_beam_group_limit))
    print("Repeat count mix: " + _format_count_map(by_repeat_count))
    print("Preflight check mix: " + _format_count_map(by_preflight_check_count))
    print(
        "Generation token budget mix: "
        + _format_count_map(by_max_generation_total_tokens)
    )
    print(
        "Benchmark cost budget mix: "
        + _format_count_map(by_max_benchmark_total_cost)
    )
    print("Generation retry mix: " + _format_count_map(by_max_generation_retries))
    print(
        "Generation-timeout retry mix: "
        + _format_count_map(by_max_generation_timeout_retries)
    )
    print(
        "Generation-provider retry mix: "
        + _format_count_map(by_max_generation_provider_retries)
    )
    print(
        "Generation-process retry mix: "
        + _format_count_map(by_max_generation_process_retries)
    )
    print("Execution retry mix: " + _format_count_map(by_max_execution_retries))
    print(
        "Benchmark-timeout retry mix: "
        + _format_count_map(by_max_benchmark_timeout_retries)
    )
    print(
        "Benchmark-command retry mix: "
        + _format_count_map(by_max_benchmark_command_retries)
    )
    print(
        "Inconclusive retry mix: "
        + _format_count_map(by_max_inconclusive_retries)
    )
    print("Auto-promote mix: " + _format_count_map(by_auto_promote))
    print(
        "Allow-flaky-promotion mix: "
        + _format_count_map(by_allow_flaky_promotion)
    )
    print(
        "Auto-promote minimum stage mix: "
        + _format_count_map(by_auto_promote_min_stage)
    )
    print(
        "Stop-on-first-promotion mix: "
        + _format_count_map(by_stop_on_first_promotion)
    )
    for item in track_runs:
        print(
            f"- {item['track_id']}: status={item.get('campaign_status')}, "
            f"campaign={item.get('campaign_id')}, stop_reason={item.get('campaign_stop_reason')}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _discover_workspace_ids(root: Path) -> list[str]:
    if not root.exists():
        return []
    workspace_ids: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        if (path / "workspace.json").exists():
            workspace_ids.append(path.name)
    return workspace_ids


def _policy_mix_key(value: object) -> str:
    if value is None:
        return "(unset)"
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or "(unset)"
    return str(value)


def _summarize_campaign_search_policy_mix(
    items: list[dict[str, object]],
) -> dict[str, dict[str, int]]:
    stage_counts: dict[str, int] = {}
    stage_progression_counts: dict[str, int] = {}
    generator_counts: dict[str, int] = {}
    strategy_counts: dict[str, int] = {}
    source_mode_counts: dict[str, int] = {}
    preflight_enabled_counts: dict[str, int] = {}
    preflight_check_id_counts: dict[str, int] = {}
    preflight_check_count_counts: dict[str, int] = {}
    preflight_command_count_counts: dict[str, int] = {}
    preflight_timeout_counts: dict[str, int] = {}
    beam_width_counts: dict[str, int] = {}
    beam_group_counts: dict[str, int] = {}
    repeat_count_counts: dict[str, int] = {}
    generation_total_token_budget_counts: dict[str, int] = {}
    benchmark_total_cost_budget_counts: dict[str, int] = {}
    generation_retry_counts: dict[str, int] = {}
    generation_timeout_retry_counts: dict[str, int] = {}
    generation_provider_retry_counts: dict[str, int] = {}
    generation_provider_transport_retry_counts: dict[str, int] = {}
    generation_provider_auth_retry_counts: dict[str, int] = {}
    generation_provider_rate_limit_retry_counts: dict[str, int] = {}
    generation_process_retry_counts: dict[str, int] = {}
    preflight_retry_counts: dict[str, int] = {}
    execution_retry_counts: dict[str, int] = {}
    benchmark_process_retry_counts: dict[str, int] = {}
    benchmark_signal_retry_counts: dict[str, int] = {}
    benchmark_parse_retry_counts: dict[str, int] = {}
    benchmark_adapter_validation_retry_counts: dict[str, int] = {}
    benchmark_timeout_retry_counts: dict[str, int] = {}
    benchmark_command_retry_counts: dict[str, int] = {}
    inconclusive_retry_counts: dict[str, int] = {}
    auto_promote_counts: dict[str, int] = {}
    allow_flaky_promotion_counts: dict[str, int] = {}
    auto_promote_min_stage_counts: dict[str, int] = {}
    stop_on_first_promotion_counts: dict[str, int] = {}
    for item in items:
        stage_key = _policy_mix_key(item.get("stage"))
        stage_counts[stage_key] = stage_counts.get(stage_key, 0) + 1
        stage_progression_key = _policy_mix_key(item.get("stage_progression_mode"))
        stage_progression_counts[stage_progression_key] = (
            stage_progression_counts.get(stage_progression_key, 0) + 1
        )
        generator_key = _policy_mix_key(item.get("generator_id"))
        generator_counts[generator_key] = generator_counts.get(generator_key, 0) + 1
        strategy_key = _policy_mix_key(item.get("strategy"))
        strategy_counts[strategy_key] = strategy_counts.get(strategy_key, 0) + 1
        source_mode_key = _policy_mix_key(item.get("candidate_source_mode"))
        source_mode_counts[source_mode_key] = (
            source_mode_counts.get(source_mode_key, 0) + 1
        )
        preflight_enabled_key = _policy_mix_key(item.get("preflight_enabled"))
        preflight_enabled_counts[preflight_enabled_key] = (
            preflight_enabled_counts.get(preflight_enabled_key, 0) + 1
        )
        preflight_checks = item.get("preflight_checks")
        if isinstance(preflight_checks, list):
            for check_id in preflight_checks:
                if not isinstance(check_id, str) or not check_id:
                    continue
                preflight_check_id_counts[check_id] = (
                    preflight_check_id_counts.get(check_id, 0) + 1
                )
        preflight_check_count_key = _policy_mix_key(item.get("preflight_check_count"))
        preflight_check_count_counts[preflight_check_count_key] = (
            preflight_check_count_counts.get(preflight_check_count_key, 0) + 1
        )
        preflight_command_count_key = _policy_mix_key(
            item.get("preflight_command_count")
        )
        preflight_command_count_counts[preflight_command_count_key] = (
            preflight_command_count_counts.get(preflight_command_count_key, 0) + 1
        )
        preflight_timeout_key = _policy_mix_key(item.get("preflight_timeout_seconds"))
        preflight_timeout_counts[preflight_timeout_key] = (
            preflight_timeout_counts.get(preflight_timeout_key, 0) + 1
        )
        beam_width_key = _policy_mix_key(item.get("beam_width"))
        beam_width_counts[beam_width_key] = beam_width_counts.get(beam_width_key, 0) + 1
        beam_group_key = _policy_mix_key(item.get("beam_group_limit"))
        beam_group_counts[beam_group_key] = beam_group_counts.get(beam_group_key, 0) + 1
        repeat_count_key = _policy_mix_key(item.get("repeat_count"))
        repeat_count_counts[repeat_count_key] = (
            repeat_count_counts.get(repeat_count_key, 0) + 1
        )
        generation_total_token_budget_key = _policy_mix_key(
            item.get("max_generation_total_tokens")
        )
        generation_total_token_budget_counts[generation_total_token_budget_key] = (
            generation_total_token_budget_counts.get(
                generation_total_token_budget_key, 0
            )
            + 1
        )
        benchmark_total_cost_budget_key = _policy_mix_key(
            item.get("max_benchmark_total_cost")
        )
        benchmark_total_cost_budget_counts[benchmark_total_cost_budget_key] = (
            benchmark_total_cost_budget_counts.get(
                benchmark_total_cost_budget_key, 0
            )
            + 1
        )
        generation_retry_key = _policy_mix_key(item.get("max_generation_retries"))
        generation_retry_counts[generation_retry_key] = (
            generation_retry_counts.get(generation_retry_key, 0) + 1
        )
        generation_timeout_retry_key = _policy_mix_key(
            item.get("max_generation_timeout_retries")
        )
        generation_timeout_retry_counts[generation_timeout_retry_key] = (
            generation_timeout_retry_counts.get(generation_timeout_retry_key, 0) + 1
        )
        generation_provider_retry_key = _policy_mix_key(
            item.get("max_generation_provider_retries")
        )
        generation_provider_retry_counts[generation_provider_retry_key] = (
            generation_provider_retry_counts.get(generation_provider_retry_key, 0)
            + 1
        )
        generation_provider_transport_retry_key = _policy_mix_key(
            item.get("max_generation_provider_transport_retries")
        )
        generation_provider_transport_retry_counts[
            generation_provider_transport_retry_key
        ] = (
            generation_provider_transport_retry_counts.get(
                generation_provider_transport_retry_key, 0
            )
            + 1
        )
        generation_provider_auth_retry_key = _policy_mix_key(
            item.get("max_generation_provider_auth_retries")
        )
        generation_provider_auth_retry_counts[generation_provider_auth_retry_key] = (
            generation_provider_auth_retry_counts.get(
                generation_provider_auth_retry_key, 0
            )
            + 1
        )
        generation_provider_rate_limit_retry_key = _policy_mix_key(
            item.get("max_generation_provider_rate_limit_retries")
        )
        generation_provider_rate_limit_retry_counts[
            generation_provider_rate_limit_retry_key
        ] = (
            generation_provider_rate_limit_retry_counts.get(
                generation_provider_rate_limit_retry_key, 0
            )
            + 1
        )
        generation_process_retry_key = _policy_mix_key(
            item.get("max_generation_process_retries")
        )
        generation_process_retry_counts[generation_process_retry_key] = (
            generation_process_retry_counts.get(generation_process_retry_key, 0)
            + 1
        )
        preflight_retry_key = _policy_mix_key(item.get("max_preflight_retries"))
        preflight_retry_counts[preflight_retry_key] = (
            preflight_retry_counts.get(preflight_retry_key, 0) + 1
        )
        execution_retry_key = _policy_mix_key(item.get("max_execution_retries"))
        execution_retry_counts[execution_retry_key] = (
            execution_retry_counts.get(execution_retry_key, 0) + 1
        )
        benchmark_process_retry_key = _policy_mix_key(
            item.get("max_benchmark_process_retries")
        )
        benchmark_process_retry_counts[benchmark_process_retry_key] = (
            benchmark_process_retry_counts.get(benchmark_process_retry_key, 0) + 1
        )
        benchmark_signal_retry_key = _policy_mix_key(
            item.get("max_benchmark_signal_retries")
        )
        benchmark_signal_retry_counts[benchmark_signal_retry_key] = (
            benchmark_signal_retry_counts.get(benchmark_signal_retry_key, 0) + 1
        )
        benchmark_parse_retry_key = _policy_mix_key(
            item.get("max_benchmark_parse_retries")
        )
        benchmark_parse_retry_counts[benchmark_parse_retry_key] = (
            benchmark_parse_retry_counts.get(benchmark_parse_retry_key, 0) + 1
        )
        benchmark_adapter_validation_retry_key = _policy_mix_key(
            item.get("max_benchmark_adapter_validation_retries")
        )
        benchmark_adapter_validation_retry_counts[
            benchmark_adapter_validation_retry_key
        ] = (
            benchmark_adapter_validation_retry_counts.get(
                benchmark_adapter_validation_retry_key, 0
            )
            + 1
        )
        benchmark_timeout_retry_key = _policy_mix_key(
            item.get("max_benchmark_timeout_retries")
        )
        benchmark_timeout_retry_counts[benchmark_timeout_retry_key] = (
            benchmark_timeout_retry_counts.get(benchmark_timeout_retry_key, 0) + 1
        )
        benchmark_command_retry_key = _policy_mix_key(
            item.get("max_benchmark_command_retries")
        )
        benchmark_command_retry_counts[benchmark_command_retry_key] = (
            benchmark_command_retry_counts.get(benchmark_command_retry_key, 0) + 1
        )
        inconclusive_retry_key = _policy_mix_key(item.get("max_inconclusive_retries"))
        inconclusive_retry_counts[inconclusive_retry_key] = (
            inconclusive_retry_counts.get(inconclusive_retry_key, 0) + 1
        )
        auto_promote_key = _policy_mix_key(item.get("auto_promote"))
        auto_promote_counts[auto_promote_key] = (
            auto_promote_counts.get(auto_promote_key, 0) + 1
        )
        allow_flaky_promotion_key = _policy_mix_key(
            item.get("allow_flaky_promotion")
        )
        allow_flaky_promotion_counts[allow_flaky_promotion_key] = (
            allow_flaky_promotion_counts.get(allow_flaky_promotion_key, 0) + 1
        )
        auto_promote_min_stage_key = _policy_mix_key(item.get("auto_promote_min_stage"))
        auto_promote_min_stage_counts[auto_promote_min_stage_key] = (
            auto_promote_min_stage_counts.get(auto_promote_min_stage_key, 0) + 1
        )
        stop_on_first_promotion_key = _policy_mix_key(
            item.get("stop_on_first_promotion")
        )
        stop_on_first_promotion_counts[stop_on_first_promotion_key] = (
            stop_on_first_promotion_counts.get(stop_on_first_promotion_key, 0) + 1
        )
    return {
        "by_stage": stage_counts,
        "by_stage_progression_mode": stage_progression_counts,
        "by_generator_id": generator_counts,
        "by_strategy": strategy_counts,
        "by_candidate_source_mode": source_mode_counts,
        "by_preflight_enabled": preflight_enabled_counts,
        "by_preflight_check_id": preflight_check_id_counts,
        "by_preflight_check_count": preflight_check_count_counts,
        "by_preflight_command_count": preflight_command_count_counts,
        "by_preflight_timeout_seconds": preflight_timeout_counts,
        "by_beam_width": beam_width_counts,
        "by_beam_group_limit": beam_group_counts,
        "by_repeat_count": repeat_count_counts,
        "by_max_generation_total_tokens": generation_total_token_budget_counts,
        "by_max_benchmark_total_cost": benchmark_total_cost_budget_counts,
        "by_max_generation_retries": generation_retry_counts,
        "by_max_generation_timeout_retries": generation_timeout_retry_counts,
        "by_max_generation_provider_retries": generation_provider_retry_counts,
        "by_max_generation_provider_transport_retries": (
            generation_provider_transport_retry_counts
        ),
        "by_max_generation_provider_auth_retries": (
            generation_provider_auth_retry_counts
        ),
        "by_max_generation_provider_rate_limit_retries": (
            generation_provider_rate_limit_retry_counts
        ),
        "by_max_generation_process_retries": generation_process_retry_counts,
        "by_max_preflight_retries": preflight_retry_counts,
        "by_max_execution_retries": execution_retry_counts,
        "by_max_benchmark_process_retries": benchmark_process_retry_counts,
        "by_max_benchmark_signal_retries": benchmark_signal_retry_counts,
        "by_max_benchmark_parse_retries": benchmark_parse_retry_counts,
        "by_max_benchmark_adapter_validation_retries": (
            benchmark_adapter_validation_retry_counts
        ),
        "by_max_benchmark_timeout_retries": benchmark_timeout_retry_counts,
        "by_max_benchmark_command_retries": benchmark_command_retry_counts,
        "by_max_inconclusive_retries": inconclusive_retry_counts,
        "by_auto_promote": auto_promote_counts,
        "by_allow_flaky_promotion": allow_flaky_promotion_counts,
        "by_auto_promote_min_stage": auto_promote_min_stage_counts,
        "by_stop_on_first_promotion": stop_on_first_promotion_counts,
    }


def _format_count_map(mapping: dict[str, int]) -> str:
    return ", ".join(f"{key}={mapping[key]}" for key in sorted(mapping)) or "(none)"


def _merge_count_maps(
    counts: dict[str, int],
    additions: dict[str, int],
) -> dict[str, int]:
    merged = dict(counts)
    for key, value in additions.items():
        merged[key] = merged.get(key, 0) + int(value)
    return merged


def _campaign_retry_counts(campaign: CampaignRun) -> dict[str, int]:
    retry_counts: dict[str, int] = {}
    for candidate in campaign.candidates:
        retry_counts = _merge_count_maps(
            retry_counts,
            {
                str(key): int(value)
                for key, value in candidate.retry_counts.items()
            },
        )
    return retry_counts


def _campaign_failure_class_counts(campaign: CampaignRun) -> dict[str, int]:
    failure_class_counts: dict[str, int] = {}
    for candidate in campaign.candidates:
        if not isinstance(candidate.failure_class, str):
            continue
        failure_class_counts[candidate.failure_class] = (
            failure_class_counts.get(candidate.failure_class, 0) + 1
        )
    return failure_class_counts


def _load_workspace_campaign_lease_entry(
    *,
    root: Path,
    workspace_id: str,
) -> dict[str, object] | None:
    path = workspace_campaign_lease_path(root=root, workspace_id=workspace_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "workspace_id": workspace_id,
            "lease_path": str(path),
            "lease_owner": None,
            "lease_claimed_at": None,
            "lease_heartbeat_at": None,
            "lease_expires_at": None,
            "is_stale": None,
            "load_error": str(exc),
        }
    if not isinstance(payload, dict):
        return {
            "workspace_id": workspace_id,
            "lease_path": str(path),
            "lease_owner": None,
            "lease_claimed_at": None,
            "lease_heartbeat_at": None,
            "lease_expires_at": None,
            "is_stale": None,
            "load_error": f"Expected mapping in JSON file: {path}",
        }

    lease_expires_at = payload.get("lease_expires_at")
    try:
        is_stale = (
            _parse_utc_timestamp(lease_expires_at) <= datetime.now(UTC)
            if isinstance(lease_expires_at, str)
            else False
        )
    except ValueError as exc:
        return {
            "workspace_id": workspace_id,
            "lease_path": str(path),
            "lease_owner": None,
            "lease_claimed_at": None,
            "lease_heartbeat_at": None,
            "lease_expires_at": (
                str(lease_expires_at) if lease_expires_at is not None else None
            ),
            "is_stale": None,
            "load_error": str(exc),
        }
    return {
        "workspace_id": workspace_id,
        "lease_path": str(path),
        "lease_owner": (
            str(payload["lease_owner"]) if payload.get("lease_owner") is not None else None
        ),
        "lease_claimed_at": (
            str(payload["lease_claimed_at"])
            if payload.get("lease_claimed_at") is not None
            else None
        ),
        "lease_heartbeat_at": (
            str(payload["lease_heartbeat_at"])
            if payload.get("lease_heartbeat_at") is not None
            else None
        ),
        "lease_expires_at": (
            str(payload["lease_expires_at"])
            if payload.get("lease_expires_at") is not None
            else None
        ),
        "is_stale": is_stale,
        "load_error": None,
    }


def _summarize_queue_workers(
    *,
    workspace_leases: list[dict[str, object]],
    campaign_items: list[dict[str, object]],
) -> list[dict[str, object]]:
    workers: dict[str, dict[str, object]] = {}

    def _worker_entry(worker_id: str) -> dict[str, object]:
        return workers.setdefault(
            worker_id,
            {
                "worker_id": worker_id,
                "active_campaign_lease_total": 0,
                "stale_campaign_lease_total": 0,
                "active_workspace_lease_total": 0,
                "stale_workspace_lease_total": 0,
                "workspace_ids": set(),
                "campaign_ids": set(),
            },
        )

    for lease in workspace_leases:
        worker_id = lease.get("lease_owner")
        workspace_id = lease.get("workspace_id")
        if not isinstance(worker_id, str) or not worker_id:
            continue
        entry = _worker_entry(worker_id)
        if isinstance(workspace_id, str):
            entry["workspace_ids"].add(workspace_id)
        if lease.get("is_stale") is True:
            entry["stale_workspace_lease_total"] = (
                int(entry["stale_workspace_lease_total"]) + 1
            )
        else:
            entry["active_workspace_lease_total"] = (
                int(entry["active_workspace_lease_total"]) + 1
            )

    for item in campaign_items:
        lease = item.get("lease")
        if not isinstance(lease, dict):
            continue
        worker_id = lease.get("lease_owner")
        if not isinstance(worker_id, str) or not worker_id:
            continue
        entry = _worker_entry(worker_id)
        workspace_id = item.get("workspace_id")
        if isinstance(workspace_id, str):
            entry["workspace_ids"].add(workspace_id)
        campaign_id = item.get("campaign_id")
        track_id = item.get("track_id")
        if (
            isinstance(workspace_id, str)
            and isinstance(track_id, str)
            and isinstance(campaign_id, str)
        ):
            entry["campaign_ids"].add(f"{workspace_id}/{track_id}/{campaign_id}")
        if lease.get("is_stale") is True:
            entry["stale_campaign_lease_total"] = (
                int(entry["stale_campaign_lease_total"]) + 1
            )
        else:
            entry["active_campaign_lease_total"] = (
                int(entry["active_campaign_lease_total"]) + 1
            )

    rendered: list[dict[str, object]] = []
    for worker_id in sorted(workers):
        entry = workers[worker_id]
        rendered.append(
            {
                "worker_id": worker_id,
                "active_campaign_lease_total": int(
                    entry["active_campaign_lease_total"]
                ),
                "stale_campaign_lease_total": int(entry["stale_campaign_lease_total"]),
                "active_workspace_lease_total": int(
                    entry["active_workspace_lease_total"]
                ),
                "stale_workspace_lease_total": int(
                    entry["stale_workspace_lease_total"]
                ),
                "workspace_ids": sorted(
                    str(item) for item in set(entry["workspace_ids"])
                ),
                "campaign_ids": sorted(str(item) for item in set(entry["campaign_ids"])),
            }
        )
    return rendered


def _render_campaign_queue(
    *,
    root: Path,
    requested_workspace_ids: list[str],
    requested_track_ids: list[str],
) -> dict[str, object]:
    workspace_filter = set(requested_workspace_ids)
    track_filter = set(requested_track_ids)
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not workspace_filter or workspace_id in workspace_filter
    ]
    runnable_campaign_ids = {
        campaign.campaign_run_id
        for campaign in list_runnable_campaign_runs(
            root=root,
            workspace_ids=list(requested_workspace_ids),
            track_ids=list(requested_track_ids),
        )
    }

    status_priority = {
        "queued": 0,
        "paused": 1,
        "running": 2,
    }
    workspace_leases = [
        lease
        for lease in (
            _load_workspace_campaign_lease_entry(root=root, workspace_id=workspace_id)
            for workspace_id in selected_workspace_ids
        )
        if lease is not None
    ]

    active_campaigns: list[CampaignRun] = []
    for workspace_id in selected_workspace_ids:
        workspace = load_workspace(root, workspace_id)
        for track_id in sorted(workspace.tracks):
            if track_filter and track_id not in track_filter:
                continue
            for campaign in list_track_campaign_runs(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            ):
                if campaign.execution_mode != "background":
                    continue
                if campaign.status not in {"queued", "running", "paused"}:
                    continue
                active_campaigns.append(campaign)

    active_campaigns.sort(
        key=lambda campaign: (
            status_priority.get(campaign.status, 99),
            campaign.created_at,
            campaign.workspace_id,
            campaign.track_id,
            campaign.campaign_run_id,
        )
    )

    items: list[dict[str, object]] = []
    retry_counts: dict[str, int] = {}
    failure_class_counts: dict[str, int] = {}
    campaign_status_counts: dict[str, int] = {}
    desired_state_counts: dict[str, int] = {}
    lease_state_counts: dict[str, int] = {}
    unique_tracks: set[tuple[str, str]] = set()
    event_total = 0
    for campaign in active_campaigns:
        unique_tracks.add((campaign.workspace_id, campaign.track_id))
        campaign_retry_counts = _campaign_retry_counts(campaign)
        campaign_failure_class_counts = _campaign_failure_class_counts(campaign)
        retry_counts = _merge_count_maps(retry_counts, campaign_retry_counts)
        failure_class_counts = _merge_count_maps(
            failure_class_counts,
            campaign_failure_class_counts,
        )
        campaign_status_counts[campaign.status] = (
            campaign_status_counts.get(campaign.status, 0) + 1
        )
        desired_state_counts[campaign.desired_state] = (
            desired_state_counts.get(campaign.desired_state, 0) + 1
        )
        campaign_lease = {
            "lease_owner": campaign.lease_owner,
            "lease_claimed_at": campaign.lease_claimed_at,
            "lease_heartbeat_at": campaign.lease_heartbeat_at,
            "lease_expires_at": campaign.lease_expires_at,
            "is_stale": (
                campaign_lease_is_stale(campaign)
                if campaign.lease_owner is not None
                else False
            ),
        }
        lease_state_key = "campaign_unleased"
        if campaign.lease_owner is not None:
            lease_state_key = (
                "campaign_stale" if campaign_lease["is_stale"] else "campaign_active"
            )
        lease_state_counts[lease_state_key] = lease_state_counts.get(lease_state_key, 0) + 1

        campaign_events = load_workspace_events(
            root=root,
            workspace_id=campaign.workspace_id,
            campaign_run_id=campaign.campaign_run_id,
            track_id=campaign.track_id,
        )
        event_total += len(campaign_events)
        items.append(
            {
                "workspace_id": campaign.workspace_id,
                "track_id": campaign.track_id,
                "campaign_id": campaign.campaign_run_id,
                "campaign_path": str(
                    campaign_run_path(
                        root=root,
                        workspace_id=campaign.workspace_id,
                        track_id=campaign.track_id,
                        campaign_run_id=campaign.campaign_run_id,
                    )
                ),
                "status": campaign.status,
                "desired_state": campaign.desired_state,
                "stop_reason": campaign.stop_reason,
                "runnable": campaign.campaign_run_id in runnable_campaign_ids,
                "stage": campaign.stage,
                "stage_progression_mode": campaign.stage_progression_mode,
                "adapter_id": campaign.adapter_id,
                "generator_id": campaign.generator_id,
                "strategy": campaign.strategy,
                "beam_width": campaign.beam_width,
                "beam_group_limit": campaign.beam_group_limit,
                "repeat_count": campaign.repeat_count,
                "candidate_source_mode": campaign.candidate_source_mode,
                "next_candidate_index": campaign.next_candidate_index,
                "candidate_total": len(campaign.candidates),
                "pruned_candidate_total": sum(
                    1 for candidate in campaign.candidates if candidate.status == "pruned"
                ),
                "attempt_total": sum(
                    int(candidate.attempt_count) for candidate in campaign.candidates
                ),
                "success_count": campaign.success_count,
                "failure_count": campaign.failure_count,
                "inconclusive_count": campaign.inconclusive_count,
                "promoted_count": campaign.promoted_count,
                "event_total": len(campaign_events),
                "retry_counts": campaign_retry_counts,
                "retry_total": sum(campaign_retry_counts.values()),
                "failure_class_counts": campaign_failure_class_counts,
                "resource_usage": _campaign_resource_usage(root=root, campaign=campaign),
                "lease": campaign_lease,
            }
        )

    for workspace_lease in workspace_leases:
        lease_state_key = "workspace_invalid"
        if workspace_lease.get("load_error") is None:
            lease_state_key = (
                "workspace_stale"
                if workspace_lease.get("is_stale") is True
                else "workspace_active"
            )
        lease_state_counts[lease_state_key] = lease_state_counts.get(lease_state_key, 0) + 1

    workers = _summarize_queue_workers(
        workspace_leases=workspace_leases,
        campaign_items=items,
    )
    return {
        "workspace_filter": list(requested_workspace_ids),
        "track_filter": list(requested_track_ids),
        "workspace_total": len(selected_workspace_ids),
        "track_total": len(unique_tracks),
        "campaign_total": len(items),
        "runnable_campaign_total": len(runnable_campaign_ids),
        "worker_total": len(workers),
        "active_worker_total": sum(
            1
            for worker in workers
            if int(worker["active_campaign_lease_total"]) > 0
            or int(worker["active_workspace_lease_total"]) > 0
        ),
        "campaign_status_counts": campaign_status_counts,
        "desired_state_counts": desired_state_counts,
        "lease_state_counts": lease_state_counts,
        "retry_counts": retry_counts,
        "failure_class_counts": failure_class_counts,
        "event_total": event_total,
        "resource_usage": _summarize_campaign_resource_usage(items),
        "workspace_leases": workspace_leases,
        "workers": workers,
        "campaigns": items,
    }


def _collect_root_campaign_items(
    *,
    root: Path,
    requested_workspace_ids: list[str],
    requested_track_ids: list[str],
) -> tuple[list[str], list[dict[str, object]]]:
    workspace_filter = set(requested_workspace_ids)
    track_filter = set(requested_track_ids)
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not workspace_filter or workspace_id in workspace_filter
    ]
    items: list[dict[str, object]] = []
    for workspace_id in selected_workspace_ids:
        workspace = load_workspace(root, workspace_id)
        for track_id in sorted(workspace.tracks):
            if track_filter and track_id not in track_filter:
                continue
            for campaign in list_track_campaign_runs(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            ):
                rendered = _render_campaign(campaign, root=root)
                items.append(
                    {
                        "workspace_id": workspace_id,
                        "track_id": track_id,
                        "campaign_id": campaign.campaign_run_id,
                        "status": campaign.status,
                        "stage": campaign.stage,
                        "stage_progression_mode": campaign.stage_progression_mode,
                        "adapter_id": campaign.adapter_id,
                        "generator_id": campaign.generator_id,
                        "strategy": campaign.strategy,
                        "beam_width": campaign.beam_width,
                        "beam_group_limit": campaign.beam_group_limit,
                        "repeat_count": campaign.repeat_count,
                        "candidate_source_mode": campaign.candidate_source_mode,
                        "preflight_enabled": bool(campaign.preflight_commands),
                        "preflight_checks": list(campaign.preflight_checks),
                        "preflight_check_count": len(campaign.preflight_checks),
                        "preflight_command_count": len(campaign.preflight_commands),
                        "preflight_timeout_seconds": campaign.preflight_timeout_seconds,
                        "max_generation_total_tokens": (
                            campaign.max_generation_total_tokens
                        ),
                        "max_benchmark_total_cost": campaign.max_benchmark_total_cost,
                        "max_generation_retries": campaign.max_generation_retries,
                        "max_generation_timeout_retries": (
                            campaign.max_generation_timeout_retries
                        ),
                        "max_generation_provider_retries": (
                            campaign.max_generation_provider_retries
                        ),
                        "max_generation_provider_transport_retries": (
                            campaign.max_generation_provider_transport_retries
                        ),
                        "max_generation_provider_auth_retries": (
                            campaign.max_generation_provider_auth_retries
                        ),
                        "max_generation_provider_rate_limit_retries": (
                            campaign.max_generation_provider_rate_limit_retries
                        ),
                        "max_generation_process_retries": (
                            campaign.max_generation_process_retries
                        ),
                        "max_preflight_retries": campaign.max_preflight_retries,
                        "max_execution_retries": campaign.max_execution_retries,
                        "max_benchmark_process_retries": (
                            campaign.max_benchmark_process_retries
                        ),
                        "max_benchmark_signal_retries": (
                            campaign.max_benchmark_signal_retries
                        ),
                        "max_benchmark_parse_retries": (
                            campaign.max_benchmark_parse_retries
                        ),
                        "max_benchmark_adapter_validation_retries": (
                            campaign.max_benchmark_adapter_validation_retries
                        ),
                        "max_benchmark_timeout_retries": (
                            campaign.max_benchmark_timeout_retries
                        ),
                        "max_benchmark_command_retries": (
                            campaign.max_benchmark_command_retries
                        ),
                        "max_inconclusive_retries": campaign.max_inconclusive_retries,
                        "auto_promote": campaign.auto_promote,
                        "allow_flaky_promotion": campaign.allow_flaky_promotion,
                        "auto_promote_min_stage": campaign.auto_promote_min_stage,
                        "stop_on_first_promotion": campaign.stop_on_first_promotion,
                        "next_candidate_index": campaign.next_candidate_index,
                        "candidate_total": len(campaign.candidates),
                        "pruned_candidate_total": rendered["pruned_candidate_total"],
                        "attempt_total": rendered["attempt_total"],
                        "success_count": campaign.success_count,
                        "failure_count": campaign.failure_count,
                        "inconclusive_count": campaign.inconclusive_count,
                        "promoted_count": campaign.promoted_count,
                        "campaign_path": rendered["campaign_path"],
                        "resource_usage": rendered["resource_usage"],
                    }
                )
    items.sort(
        key=lambda item: (
            str(item["workspace_id"]),
            str(item["track_id"]),
            str(item["campaign_id"]),
        )
    )
    return selected_workspace_ids, items


def _render_root_campaign_listing(
    *,
    root: Path,
    requested_workspace_ids: list[str],
    requested_track_ids: list[str],
) -> dict[str, object]:
    selected_workspace_ids, items = _collect_root_campaign_items(
        root=root,
        requested_workspace_ids=requested_workspace_ids,
        requested_track_ids=requested_track_ids,
    )
    status_counts: dict[str, int] = {}
    unique_tracks: set[tuple[str, str]] = set()
    for item in items:
        status = str(item["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        unique_tracks.add((str(item["workspace_id"]), str(item["track_id"])))
    return {
        "workspace_filter": list(requested_workspace_ids),
        "track_filter": list(requested_track_ids),
        "workspace_total": len(selected_workspace_ids),
        "track_total": len(unique_tracks),
        "campaign_total": len(items),
        "campaign_status_counts": status_counts,
        "search_policy_mix": _summarize_campaign_search_policy_mix(items),
        "resource_usage": _summarize_campaign_resource_usage(items),
        "pruned_candidate_total": sum(int(item["pruned_candidate_total"]) for item in items),
        "attempt_total": sum(int(item["attempt_total"]) for item in items),
        "promoted_candidate_total": sum(int(item["promoted_count"]) for item in items),
        "campaigns": items,
    }


def _render_workspace_campaign_listing(
    *,
    root: Path,
    workspace_id: str,
    requested_track_ids: list[str],
) -> dict[str, object]:
    if requested_track_ids:
        workspace = load_workspace(root, workspace_id)
        requested_track_id_set = set(requested_track_ids)
        track_ids = [
            track_id for track_id in sorted(workspace.tracks) if track_id in requested_track_id_set
        ]
    else:
        workspace = load_workspace(root, workspace_id)
        track_ids = sorted(workspace.tracks)

    items = []
    for track_id in track_ids:
        for campaign in list_track_campaign_runs(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        ):
            rendered = _render_campaign(campaign, root=root)
            items.append(
                {
                    "campaign_id": campaign.campaign_run_id,
                    "track_id": track_id,
                    "status": campaign.status,
                    "stage": campaign.stage,
                    "stage_progression_mode": campaign.stage_progression_mode,
                    "adapter_id": campaign.adapter_id,
                    "generator_id": campaign.generator_id,
                    "strategy": campaign.strategy,
                    "beam_width": campaign.beam_width,
                    "beam_group_limit": campaign.beam_group_limit,
                    "repeat_count": campaign.repeat_count,
                    "candidate_source_mode": campaign.candidate_source_mode,
                    "preflight_enabled": bool(campaign.preflight_commands),
                    "preflight_checks": list(campaign.preflight_checks),
                    "preflight_check_count": len(campaign.preflight_checks),
                    "preflight_command_count": len(campaign.preflight_commands),
                    "preflight_timeout_seconds": campaign.preflight_timeout_seconds,
                    "max_generation_total_tokens": (
                        campaign.max_generation_total_tokens
                    ),
                    "max_benchmark_total_cost": campaign.max_benchmark_total_cost,
                    "max_generation_retries": campaign.max_generation_retries,
                    "max_generation_timeout_retries": (
                        campaign.max_generation_timeout_retries
                    ),
                    "max_generation_provider_retries": (
                        campaign.max_generation_provider_retries
                    ),
                    "max_generation_provider_transport_retries": (
                        campaign.max_generation_provider_transport_retries
                    ),
                    "max_generation_provider_auth_retries": (
                        campaign.max_generation_provider_auth_retries
                    ),
                    "max_generation_provider_rate_limit_retries": (
                        campaign.max_generation_provider_rate_limit_retries
                    ),
                    "max_generation_process_retries": (
                        campaign.max_generation_process_retries
                    ),
                    "max_preflight_retries": campaign.max_preflight_retries,
                    "max_execution_retries": campaign.max_execution_retries,
                    "max_benchmark_process_retries": (
                        campaign.max_benchmark_process_retries
                    ),
                    "max_benchmark_signal_retries": (
                        campaign.max_benchmark_signal_retries
                    ),
                    "max_benchmark_parse_retries": (
                        campaign.max_benchmark_parse_retries
                    ),
                    "max_benchmark_adapter_validation_retries": (
                        campaign.max_benchmark_adapter_validation_retries
                    ),
                    "max_benchmark_timeout_retries": (
                        campaign.max_benchmark_timeout_retries
                    ),
                    "max_benchmark_command_retries": (
                        campaign.max_benchmark_command_retries
                    ),
                    "max_inconclusive_retries": campaign.max_inconclusive_retries,
                    "auto_promote": campaign.auto_promote,
                    "allow_flaky_promotion": campaign.allow_flaky_promotion,
                    "auto_promote_min_stage": campaign.auto_promote_min_stage,
                    "stop_on_first_promotion": campaign.stop_on_first_promotion,
                    "next_candidate_index": campaign.next_candidate_index,
                    "candidate_total": len(campaign.candidates),
                    "pruned_candidate_total": rendered["pruned_candidate_total"],
                    "attempt_total": rendered["attempt_total"],
                    "success_count": campaign.success_count,
                    "failure_count": campaign.failure_count,
                    "inconclusive_count": campaign.inconclusive_count,
                    "promoted_count": campaign.promoted_count,
                    "campaign_path": rendered["campaign_path"],
                    "resource_usage": rendered["resource_usage"],
                }
            )
    items.sort(key=lambda item: (str(item["track_id"]), str(item["campaign_id"])))
    status_counts: dict[str, int] = {}
    unique_tracks: set[str] = set()
    for item in items:
        status = str(item["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        unique_tracks.add(str(item["track_id"]))
    return {
        "workspace_id": workspace_id,
        "track_filter": list(requested_track_ids),
        "track_total": len(unique_tracks),
        "campaign_total": len(items),
        "campaign_status_counts": status_counts,
        "search_policy_mix": _summarize_campaign_search_policy_mix(items),
        "resource_usage": _summarize_campaign_resource_usage(items),
        "pruned_candidate_total": sum(int(item["pruned_candidate_total"]) for item in items),
        "attempt_total": sum(int(item["attempt_total"]) for item in items),
        "promoted_candidate_total": sum(int(item["promoted_count"]) for item in items),
        "campaigns": items,
    }


def _handle_run_root_campaigns(args: argparse.Namespace) -> int:
    worker_total = int(getattr(args, "workers", 1) or 1)
    if worker_total < 1:
        raise SystemExit("`--workers` must be greater than zero.")
    if getattr(args, "background", False) and worker_total > 1:
        raise SystemExit("`--workers` cannot be combined with `--background` for run-root-campaigns.")
    requested_workspace_ids = set(args.workspace_id)
    discovered_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(args.root)
        if not requested_workspace_ids or workspace_id in requested_workspace_ids
    ]
    initial_root_memory = build_root_memory(
        root=args.root,
        requested_workspace_ids=list(requested_workspace_ids),
    )
    workspace_schedule = schedule_root_workspaces(
        root=args.root,
        requested_workspace_ids=list(requested_workspace_ids),
        memory_payload=initial_root_memory,
        mode=str(getattr(args, "schedule", "portfolio") or "portfolio"),
    )
    scheduled_workspace_ids = [
        str(item["workspace_id"])
        for item in workspace_schedule
        if isinstance(item, dict) and isinstance(item.get("workspace_id"), str)
    ]
    selected_workspace_ids = [
        workspace_id for workspace_id in scheduled_workspace_ids if workspace_id in discovered_workspace_ids
    ] + [
        workspace_id for workspace_id in discovered_workspace_ids if workspace_id not in scheduled_workspace_ids
    ]
    if not selected_workspace_ids:
        raise SystemExit("No workspaces matched the requested root campaign run.")

    workspace_runs: list[dict[str, object]] = []
    launched_campaign_items: list[dict[str, object]] = []
    worker_results: list[dict[str, object]] = []
    status = "completed"
    stop_reason = "all_workspaces_completed"
    queue_in_background = bool(getattr(args, "background", False) or worker_total > 1)

    for workspace_id in selected_workspace_ids:
        target_root_base = args.target_root_base / workspace_id
        target_root_base.mkdir(parents=True, exist_ok=True)
        promotion_target_root_base = None
        if args.promotion_target_root_base is not None:
            promotion_target_root_base = args.promotion_target_root_base / workspace_id
            promotion_target_root_base.mkdir(parents=True, exist_ok=True)
        workspace_args = argparse.Namespace(
            workspace_id=workspace_id,
            root=args.root,
            adapter=args.adapter,
            config=args.config,
            preset=args.preset,
            set=list(args.set),
            track_id=list(args.track_id),
            stage=args.stage,
            generator=args.generator,
            strategy=args.strategy,
            beam_width=args.beam_width,
            beam_groups=args.beam_groups,
            repeat=args.repeat,
            stage_progression=args.stage_progression,
            edit_plan=list(args.edit_plan),
            intervention_class=list(args.intervention_class),
            preflight_command=list(args.preflight_command),
            preflight_check=list(getattr(args, "preflight_check", [])),
            preflight_timeout_seconds=args.preflight_timeout_seconds,
            generator_option=list(args.generator_option),
            target_root_base=target_root_base,
            max_proposals=args.max_proposals,
            max_iterations=args.max_iterations,
            max_successes=args.max_successes,
            max_promotions=args.max_promotions,
            max_failures=args.max_failures,
            max_inconclusive=args.max_inconclusive,
            no_improvement_limit=args.no_improvement_limit,
            auto_promote=args.auto_promote,
            allow_flaky_promotion=args.allow_flaky_promotion,
            auto_promote_min_stage=args.auto_promote_min_stage,
            stop_on_first_promotion=args.stop_on_first_promotion,
            promotion_target_root_base=promotion_target_root_base,
            dry_run=args.dry_run,
            time_budget_seconds=args.time_budget_seconds,
            max_generation_total_tokens=args.max_generation_total_tokens,
            max_benchmark_total_cost=args.max_benchmark_total_cost,
            max_generation_retries=args.max_generation_retries,
            max_generation_timeout_retries=args.max_generation_timeout_retries,
            max_generation_provider_retries=args.max_generation_provider_retries,
            max_generation_provider_transport_retries=(
                args.max_generation_provider_transport_retries
            ),
            max_generation_provider_auth_retries=(
                args.max_generation_provider_auth_retries
            ),
            max_generation_provider_rate_limit_retries=(
                args.max_generation_provider_rate_limit_retries
            ),
            max_generation_process_retries=args.max_generation_process_retries,
            max_preflight_retries=args.max_preflight_retries,
            max_execution_retries=args.max_execution_retries,
            max_benchmark_process_retries=args.max_benchmark_process_retries,
            max_benchmark_signal_retries=args.max_benchmark_signal_retries,
            max_benchmark_parse_retries=args.max_benchmark_parse_retries,
            max_benchmark_adapter_validation_retries=(
                args.max_benchmark_adapter_validation_retries
            ),
            max_benchmark_timeout_retries=args.max_benchmark_timeout_retries,
            max_benchmark_command_retries=args.max_benchmark_command_retries,
            max_inconclusive_retries=args.max_inconclusive_retries,
            continue_on_failure=args.continue_on_failure,
            background=queue_in_background,
            json=True,
            output=None,
        )
        try:
            exit_code, rendered = _capture_handler_json(
                _handle_run_workspace_campaigns,
                workspace_args,
            )
        except SystemExit as exc:
            exit_code = int(exc.code) if isinstance(exc.code, int) else 1
            rendered = {}
        workspace_status = rendered.get("status")
        workspace_stop_reason = rendered.get("stop_reason")
        workspace_tracks = rendered.get("tracks")
        if isinstance(workspace_tracks, list):
            for track_item in workspace_tracks:
                if not isinstance(track_item, dict):
                    continue
                campaign_rendered = track_item.get("rendered")
                campaign_payload = (
                    campaign_rendered.get("campaign")
                    if isinstance(campaign_rendered, dict)
                    else None
                )
                if not isinstance(campaign_payload, dict):
                    continue
                launched_campaign_items.append(
                    {
                        "workspace_id": workspace_id,
                        "track_id": track_item.get("track_id"),
                        "campaign_id": campaign_payload.get("campaign_run_id"),
                        "stage": campaign_payload.get("stage"),
                        "stage_progression_mode": campaign_payload.get(
                            "stage_progression_mode"
                        ),
                        "generator_id": campaign_payload.get("generator_id"),
                        "strategy": campaign_payload.get("strategy"),
                        "beam_width": campaign_payload.get("beam_width"),
                        "beam_group_limit": campaign_payload.get("beam_group_limit"),
                        "repeat_count": campaign_payload.get("repeat_count"),
                        "candidate_source_mode": campaign_payload.get(
                            "candidate_source_mode"
                        ),
                        "preflight_enabled": bool(
                            campaign_payload.get("preflight_commands")
                        ),
                        "preflight_checks": list(
                            campaign_payload.get("preflight_checks", [])
                        ),
                        "preflight_check_count": len(
                            campaign_payload.get("preflight_checks", [])
                        ),
                        "preflight_command_count": len(
                            campaign_payload.get("preflight_commands", [])
                        ),
                        "preflight_timeout_seconds": campaign_payload.get(
                            "preflight_timeout_seconds"
                        ),
                        "max_generation_total_tokens": campaign_payload.get(
                            "max_generation_total_tokens"
                        ),
                        "max_benchmark_total_cost": campaign_payload.get(
                            "max_benchmark_total_cost"
                        ),
                        "max_generation_retries": campaign_payload.get(
                            "max_generation_retries"
                        ),
                        "max_generation_timeout_retries": campaign_payload.get(
                            "max_generation_timeout_retries"
                        ),
                        "max_generation_provider_retries": campaign_payload.get(
                            "max_generation_provider_retries"
                        ),
                        "max_generation_provider_transport_retries": campaign_payload.get(
                            "max_generation_provider_transport_retries"
                        ),
                        "max_generation_provider_auth_retries": campaign_payload.get(
                            "max_generation_provider_auth_retries"
                        ),
                        "max_generation_provider_rate_limit_retries": campaign_payload.get(
                            "max_generation_provider_rate_limit_retries"
                        ),
                        "max_generation_process_retries": campaign_payload.get(
                            "max_generation_process_retries"
                        ),
                        "max_preflight_retries": campaign_payload.get(
                            "max_preflight_retries"
                        ),
                        "max_execution_retries": campaign_payload.get(
                            "max_execution_retries"
                        ),
                        "max_benchmark_process_retries": campaign_payload.get(
                            "max_benchmark_process_retries"
                        ),
                        "max_benchmark_signal_retries": campaign_payload.get(
                            "max_benchmark_signal_retries"
                        ),
                        "max_benchmark_parse_retries": campaign_payload.get(
                            "max_benchmark_parse_retries"
                        ),
                        "max_benchmark_adapter_validation_retries": campaign_payload.get(
                            "max_benchmark_adapter_validation_retries"
                        ),
                        "max_benchmark_timeout_retries": campaign_payload.get(
                            "max_benchmark_timeout_retries"
                        ),
                        "max_benchmark_command_retries": campaign_payload.get(
                            "max_benchmark_command_retries"
                        ),
                        "max_inconclusive_retries": campaign_payload.get(
                            "max_inconclusive_retries"
                        ),
                        "auto_promote": campaign_payload.get("auto_promote"),
                        "allow_flaky_promotion": campaign_payload.get(
                            "allow_flaky_promotion"
                        ),
                        "auto_promote_min_stage": campaign_payload.get(
                            "auto_promote_min_stage"
                        ),
                        "stop_on_first_promotion": campaign_payload.get(
                            "stop_on_first_promotion"
                        ),
                        "resource_usage": campaign_rendered.get("resource_usage"),
                    }
                )
        workspace_result = {
            "workspace_id": workspace_id,
            "exit_code": exit_code,
            "status": workspace_status,
            "stop_reason": workspace_stop_reason,
            "rendered": rendered,
            "target_root_base": str(target_root_base.resolve()),
            "promotion_target_root_base": (
                str(promotion_target_root_base.resolve())
                if promotion_target_root_base is not None
                else None
            ),
        }
        workspace_runs.append(workspace_result)
        workspace_failed = exit_code != 0 or workspace_status in {"failed", "partial"}
        if workspace_failed and not args.continue_on_failure:
            status = "failed"
            stop_reason = "workspace_campaign_failed"
            break
        if workspace_failed:
            status = "partial"
            stop_reason = "workspace_campaign_failed"

    if worker_total > 1:
        queued_campaign_total = sum(
            1
            for workspace_result in workspace_runs
            for track_run in (
                workspace_result.get("rendered", {}).get("tracks", [])
                if isinstance(workspace_result.get("rendered"), dict)
                else []
            )
            if isinstance(track_run, dict)
            and isinstance(track_run.get("campaign_id"), str)
        )
        worker_results = _run_local_worker_pool(
            root=args.root,
            workspace_ids=selected_workspace_ids,
            track_ids=list(args.track_id),
            workers=worker_total,
            lease_seconds=300,
            campaign_total=queued_campaign_total,
        )
        workspace_runs = [
            _refresh_workspace_run_after_workers(
                root=args.root,
                workspace_result=workspace_result,
            )
            for workspace_result in workspace_runs
        ]
        launched_campaign_items = []
        for workspace_result in workspace_runs:
            workspace_id = workspace_result.get("workspace_id")
            rendered_workspace = workspace_result.get("rendered")
            if not isinstance(workspace_id, str) or not isinstance(rendered_workspace, dict):
                continue
            track_runs = rendered_workspace.get("tracks")
            if not isinstance(track_runs, list):
                continue
            for track_run in track_runs:
                if not isinstance(track_run, dict):
                    continue
                item = _launched_campaign_item_from_track_run(
                    track_run,
                    workspace_id=workspace_id,
                )
                if item is not None:
                    launched_campaign_items.append(item)
        failed_workspace_total = sum(
            1
            for item in workspace_runs
            if item.get("exit_code") != 0 or item.get("status") in {"failed", "partial"}
        )
        status = "partial" if failed_workspace_total > 0 else "completed"
        stop_reason = (
            "workspace_campaign_failed"
            if failed_workspace_total > 0
            else "all_workspaces_completed"
        )

    selected_workspace_events = [
        event
        for workspace_id in selected_workspace_ids
        for event in load_workspace_events(root=args.root, workspace_id=workspace_id)
    ]
    root_memory = build_root_memory(
        root=args.root,
        requested_workspace_ids=selected_workspace_ids,
    )
    root_memory_output_path = persist_root_memory(root=args.root, payload=root_memory)
    transfer_suggestions = [
        item
        for item in root_memory.get("transfer_suggestions", [])
        if isinstance(item, dict)
    ]
    applied_transfers = (
        apply_transfer_suggestions(
            root=args.root,
            suggestions=transfer_suggestions,
            target_root_base=args.root_transfer_target_base,
            limit=args.root_transfer_limit,
        )
        if args.apply_root_transfers
        else []
    )

    rendered = {
        "workspace_total": len(selected_workspace_ids),
        "completed_workspace_total": len(workspace_runs),
        "success_workspace_total": sum(
            1 for item in workspace_runs if item.get("status") == "completed"
        ),
        "failed_workspace_total": sum(
            1
            for item in workspace_runs
            if item.get("exit_code") != 0 or item.get("status") in {"failed", "partial"}
        ),
        "status": status,
        "stop_reason": stop_reason,
        "search_policy_mix": _summarize_campaign_search_policy_mix(
            launched_campaign_items
        ),
        "resource_usage": _summarize_campaign_resource_usage(launched_campaign_items),
        "workers_requested": worker_total,
        "schedule_mode": str(getattr(args, "schedule", "portfolio") or "portfolio"),
        "workspace_schedule": workspace_schedule,
        "worker_results": worker_results,
        "event_metrics": aggregate_event_metrics(selected_workspace_events),
        "root_memory_path": str(root_memory_output_path),
        "root_memory": root_memory,
        "transfer_suggestions": transfer_suggestions,
        "applied_transfers": applied_transfers,
        "workspaces": workspace_runs,
    }
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspaces run: {len(workspace_runs)}/{len(selected_workspace_ids)}")
    print(f"Schedule mode: {rendered['schedule_mode']}")
    print(f"Status: {status}")
    print(f"Stop reason: {stop_reason}")
    _print_resource_usage_summary(rendered["resource_usage"])
    search_policy_mix = rendered["search_policy_mix"]
    assert isinstance(search_policy_mix, dict)
    by_generator_id = search_policy_mix["by_generator_id"]
    by_strategy = search_policy_mix["by_strategy"]
    by_stage_progression_mode = search_policy_mix["by_stage_progression_mode"]
    by_candidate_source_mode = search_policy_mix["by_candidate_source_mode"]
    by_beam_width = search_policy_mix["by_beam_width"]
    by_beam_group_limit = search_policy_mix["by_beam_group_limit"]
    by_repeat_count = search_policy_mix["by_repeat_count"]
    by_preflight_check_count = search_policy_mix["by_preflight_check_count"]
    by_max_generation_total_tokens = search_policy_mix["by_max_generation_total_tokens"]
    by_max_benchmark_total_cost = search_policy_mix["by_max_benchmark_total_cost"]
    by_max_generation_retries = search_policy_mix["by_max_generation_retries"]
    by_max_generation_timeout_retries = search_policy_mix[
        "by_max_generation_timeout_retries"
    ]
    by_max_generation_provider_retries = search_policy_mix[
        "by_max_generation_provider_retries"
    ]
    by_max_generation_process_retries = search_policy_mix[
        "by_max_generation_process_retries"
    ]
    by_max_execution_retries = search_policy_mix["by_max_execution_retries"]
    by_max_benchmark_timeout_retries = search_policy_mix[
        "by_max_benchmark_timeout_retries"
    ]
    by_max_benchmark_command_retries = search_policy_mix[
        "by_max_benchmark_command_retries"
    ]
    by_max_inconclusive_retries = search_policy_mix["by_max_inconclusive_retries"]
    by_auto_promote = search_policy_mix["by_auto_promote"]
    by_allow_flaky_promotion = search_policy_mix["by_allow_flaky_promotion"]
    by_auto_promote_min_stage = search_policy_mix["by_auto_promote_min_stage"]
    by_stop_on_first_promotion = search_policy_mix["by_stop_on_first_promotion"]
    assert isinstance(by_generator_id, dict)
    assert isinstance(by_strategy, dict)
    assert isinstance(by_stage_progression_mode, dict)
    assert isinstance(by_candidate_source_mode, dict)
    assert isinstance(by_beam_width, dict)
    assert isinstance(by_beam_group_limit, dict)
    assert isinstance(by_repeat_count, dict)
    assert isinstance(by_preflight_check_count, dict)
    assert isinstance(by_max_generation_total_tokens, dict)
    assert isinstance(by_max_benchmark_total_cost, dict)
    assert isinstance(by_max_generation_retries, dict)
    assert isinstance(by_max_generation_timeout_retries, dict)
    assert isinstance(by_max_generation_provider_retries, dict)
    assert isinstance(by_max_generation_process_retries, dict)
    assert isinstance(by_max_execution_retries, dict)
    assert isinstance(by_max_benchmark_timeout_retries, dict)
    assert isinstance(by_max_benchmark_command_retries, dict)
    assert isinstance(by_max_inconclusive_retries, dict)
    assert isinstance(by_auto_promote, dict)
    assert isinstance(by_allow_flaky_promotion, dict)
    assert isinstance(by_auto_promote_min_stage, dict)
    assert isinstance(by_stop_on_first_promotion, dict)
    print("Generator mix: " + _format_count_map(by_generator_id))
    print("Strategy mix: " + _format_count_map(by_strategy))
    print("Stage progression mix: " + _format_count_map(by_stage_progression_mode))
    print("Source mode mix: " + _format_count_map(by_candidate_source_mode))
    print("Beam width mix: " + _format_count_map(by_beam_width))
    print("Beam group mix: " + _format_count_map(by_beam_group_limit))
    print("Repeat count mix: " + _format_count_map(by_repeat_count))
    print("Preflight check mix: " + _format_count_map(by_preflight_check_count))
    print(
        "Generation token budget mix: "
        + _format_count_map(by_max_generation_total_tokens)
    )
    print(
        "Benchmark cost budget mix: "
        + _format_count_map(by_max_benchmark_total_cost)
    )
    print("Generation retry mix: " + _format_count_map(by_max_generation_retries))
    print(
        "Generation-timeout retry mix: "
        + _format_count_map(by_max_generation_timeout_retries)
    )
    print(
        "Generation-provider retry mix: "
        + _format_count_map(by_max_generation_provider_retries)
    )
    print(
        "Generation-process retry mix: "
        + _format_count_map(by_max_generation_process_retries)
    )
    print("Execution retry mix: " + _format_count_map(by_max_execution_retries))
    print(
        "Benchmark-timeout retry mix: "
        + _format_count_map(by_max_benchmark_timeout_retries)
    )
    print(
        "Benchmark-command retry mix: "
        + _format_count_map(by_max_benchmark_command_retries)
    )
    print(
        "Inconclusive retry mix: "
        + _format_count_map(by_max_inconclusive_retries)
    )
    print("Auto-promote mix: " + _format_count_map(by_auto_promote))
    print(
        "Allow-flaky-promotion mix: "
        + _format_count_map(by_allow_flaky_promotion)
    )
    print(
        "Auto-promote minimum stage mix: "
        + _format_count_map(by_auto_promote_min_stage)
    )
    print(
        "Stop-on-first-promotion mix: "
        + _format_count_map(by_stop_on_first_promotion)
    )
    for item in workspace_runs:
        print(
            f"- {item['workspace_id']}: status={item.get('status')}, "
            f"stop_reason={item.get('stop_reason')}, exit_code={item.get('exit_code')}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _capture_batch_run_rendered(
    handler,
    args: argparse.Namespace,
) -> dict[str, object]:
    run_args_data = dict(vars(args))
    run_args_data["json"] = True
    run_args_data["output"] = None
    run_args = argparse.Namespace(**run_args_data)
    _, rendered = _capture_handler_json(handler, run_args)
    return rendered


def _campaign_report_path_value(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _validate_campaign_report_artifact_payload(
    *,
    payload: dict[str, object],
    report_type: str,
) -> list[str]:
    errors: list[str] = []

    def require_str(key: str) -> str | None:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

    def require_dict(key: str) -> dict[str, object] | None:
        value = payload.get(key)
        if not isinstance(value, dict):
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

    def require_list(key: str) -> list[object] | None:
        value = payload.get(key)
        if not isinstance(value, list):
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

    def require_int(key: str) -> int | None:
        value = payload.get(key)
        if not isinstance(value, int):
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

    if report_type == "campaign_report":
        require_str("workspace_id")
        require_str("track_id")
        campaign_payload = require_dict("campaign")
        if campaign_payload is not None:
            campaign_id = campaign_payload.get("campaign_run_id")
            if not isinstance(campaign_id, str) or not campaign_id.strip():
                errors.append("Missing or invalid `campaign.campaign_run_id`.")
        require_list("proposals")
        require_list("records")
        require_list("iterations")
        require_list("promotions")
        champion_payload = payload.get("champion")
        if champion_payload is not None and not isinstance(champion_payload, dict):
            errors.append("Invalid `champion`.")
        return errors

    if report_type == "workspace_campaign_report":
        require_str("workspace_id")
        track_filter = payload.get("track_filter")
        if track_filter is None and payload.get("track_id") is not None:
            track_filter = [payload.get("track_id")]
        if track_filter is not None and not isinstance(track_filter, list):
            errors.append("Invalid `track_filter`.")
        require_int("track_total")
        require_int("campaign_total")
        require_int("attempt_total")
        require_int("pruned_candidate_total")
        require_int("promoted_candidate_total")
        require_dict("campaign_status_counts")
        require_dict("search_policy_mix")
        require_list("campaigns")
        return errors

    if report_type == "root_campaign_report":
        workspace_filter = payload.get("workspace_filter")
        if workspace_filter is not None and not isinstance(workspace_filter, list):
            errors.append("Invalid `workspace_filter`.")
        track_filter = payload.get("track_filter")
        if track_filter is not None and not isinstance(track_filter, list):
            errors.append("Invalid `track_filter`.")
        require_int("workspace_total")
        require_int("track_total")
        require_int("campaign_total")
        require_int("attempt_total")
        require_int("pruned_candidate_total")
        require_int("promoted_candidate_total")
        require_dict("campaign_status_counts")
        require_dict("search_policy_mix")
        require_list("campaigns")
        return errors

    if report_type == "workspace_campaign_run_report":
        require_str("workspace_id")
        require_int("track_total")
        require_int("completed_track_total")
        require_int("success_track_total")
        require_int("failed_track_total")
        require_str("status")
        require_str("stop_reason")
        require_dict("search_policy_mix")
        require_list("tracks")
        return errors

    if report_type == "root_campaign_run_report":
        require_int("workspace_total")
        require_int("completed_workspace_total")
        require_int("success_workspace_total")
        require_int("failed_workspace_total")
        require_str("status")
        require_str("stop_reason")
        require_dict("search_policy_mix")
        require_list("workspaces")
        return errors

    errors.append(f"Unsupported campaign report type `{report_type}`.")
    return errors


def _render_campaign_report_artifact(path: Path) -> dict[str, object]:
    payload = _load_structured_file(path)
    format_version = payload.get("format_version")
    if not isinstance(format_version, str):
        raise SystemExit(f"Campaign report missing format_version: {path}")

    rendered: dict[str, object] = {
        "report_path": str(path),
        "format_version": format_version,
        "report": payload,
    }

    if format_version == "autoharness.campaign_report.v1":
        campaign_payload = payload.get("campaign")
        campaign_id = (
            campaign_payload.get("campaign_run_id")
            if isinstance(campaign_payload, dict)
            else None
        )
        rendered.update(
            {
                "report_type": "campaign_report",
                "workspace_id": _campaign_report_path_value(payload, "workspace_id"),
                "track_id": _campaign_report_path_value(payload, "track_id"),
                "campaign_id": campaign_id if isinstance(campaign_id, str) else None,
                "proposal_total": len(payload.get("proposals", []))
                if isinstance(payload.get("proposals"), list)
                else 0,
                "record_total": len(payload.get("records", []))
                if isinstance(payload.get("records"), list)
                else 0,
                "iteration_total": len(payload.get("iterations", []))
                if isinstance(payload.get("iterations"), list)
                else 0,
                "promotion_total": len(payload.get("promotions", []))
                if isinstance(payload.get("promotions"), list)
                else 0,
                "has_champion": isinstance(payload.get("champion"), dict),
            }
        )
        return rendered

    if format_version == "autoharness.workspace_campaign_report.v1":
        track_filter = payload.get("track_filter")
        if track_filter is None and payload.get("track_id") is not None:
            track_filter = [payload.get("track_id")]
        rendered.update(
            {
                "report_type": "workspace_campaign_report",
                "workspace_id": _campaign_report_path_value(payload, "workspace_id"),
                "track_filter": track_filter if isinstance(track_filter, list) else [],
                "track_total": payload.get("track_total"),
                "campaign_total": payload.get("campaign_total"),
                "attempt_total": payload.get("attempt_total"),
                "pruned_candidate_total": payload.get("pruned_candidate_total"),
                "promoted_candidate_total": payload.get("promoted_candidate_total"),
                "resource_usage": _normalized_resource_usage(
                    payload.get("resource_usage")
                ),
            }
        )
        return rendered

    if format_version == "autoharness.root_campaign_report.v1":
        rendered.update(
            {
                "report_type": "root_campaign_report",
                "workspace_filter": payload.get("workspace_filter")
                if isinstance(payload.get("workspace_filter"), list)
                else [],
                "track_filter": payload.get("track_filter")
                if isinstance(payload.get("track_filter"), list)
                else [],
                "workspace_total": payload.get("workspace_total"),
                "track_total": payload.get("track_total"),
                "campaign_total": payload.get("campaign_total"),
                "attempt_total": payload.get("attempt_total"),
                "pruned_candidate_total": payload.get("pruned_candidate_total"),
                "promoted_candidate_total": payload.get("promoted_candidate_total"),
                "resource_usage": _normalized_resource_usage(
                    payload.get("resource_usage")
                ),
            }
        )
        return rendered

    if format_version == "autoharness.workspace_campaign_run_report.v1":
        rendered.update(
            {
                "report_type": "workspace_campaign_run_report",
                "workspace_id": _campaign_report_path_value(payload, "workspace_id"),
                "track_total": payload.get("track_total"),
                "completed_track_total": payload.get("completed_track_total"),
                "success_track_total": payload.get("success_track_total"),
                "failed_track_total": payload.get("failed_track_total"),
                "status": _campaign_report_path_value(payload, "status"),
                "stop_reason": _campaign_report_path_value(payload, "stop_reason"),
                "resource_usage": _normalized_resource_usage(
                    payload.get("resource_usage")
                ),
            }
        )
        return rendered

    if format_version == "autoharness.root_campaign_run_report.v1":
        rendered.update(
            {
                "report_type": "root_campaign_run_report",
                "workspace_total": payload.get("workspace_total"),
                "completed_workspace_total": payload.get("completed_workspace_total"),
                "success_workspace_total": payload.get("success_workspace_total"),
                "failed_workspace_total": payload.get("failed_workspace_total"),
                "status": _campaign_report_path_value(payload, "status"),
                "stop_reason": _campaign_report_path_value(payload, "stop_reason"),
                "resource_usage": _normalized_resource_usage(
                    payload.get("resource_usage")
                ),
            }
        )
        return rendered

    raise SystemExit(f"Unsupported campaign report format_version `{format_version}`: {path}")


def _render_campaign_report_validation(path: Path) -> dict[str, object]:
    rendered = _render_campaign_report_artifact(path)
    report_type = rendered["report_type"]
    assert isinstance(report_type, str)
    report_payload = rendered["report"]
    assert isinstance(report_payload, dict)
    validation_errors = _validate_campaign_report_artifact_payload(
        payload=report_payload,
        report_type=report_type,
    )
    return {
        **rendered,
        "valid": not validation_errors,
        "error_count": len(validation_errors),
        "validation_errors": validation_errors,
    }


def _handle_show_campaign_report_file(args: argparse.Namespace) -> int:
    rendered = _render_campaign_report_artifact(args.path)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    print(f"Report type: {rendered['report_type']}")
    print(f"Report path: {rendered['report_path']}")
    print(f"Format version: {rendered['format_version']}")
    report_type = rendered["report_type"]
    if report_type == "campaign_report":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Track: {rendered['track_id']}")
        print(f"Campaign: {rendered['campaign_id']}")
        print(f"Proposals: {rendered['proposal_total']}")
        print(f"Records: {rendered['record_total']}")
        print(f"Iterations: {rendered['iteration_total']}")
        print(f"Promotions: {rendered['promotion_total']}")
        print(f"Champion: {'present' if rendered['has_champion'] else 'absent'}")
    elif report_type == "workspace_campaign_report":
        print(f"Workspace: {rendered['workspace_id']}")
        track_filter = rendered["track_filter"]
        assert isinstance(track_filter, list)
        if track_filter:
            print("Track filter: " + ", ".join(str(item) for item in track_filter))
        print(f"Tracks: {rendered['track_total']}")
        print(f"Campaigns: {rendered['campaign_total']}")
        print(f"Attempts: {rendered['attempt_total']}")
        print(f"Pruned candidates: {rendered['pruned_candidate_total']}")
        print(f"Promoted candidates: {rendered['promoted_candidate_total']}")
        _print_resource_usage_summary(rendered["resource_usage"])
    elif report_type == "root_campaign_report":
        workspace_filter = rendered["workspace_filter"]
        assert isinstance(workspace_filter, list)
        if workspace_filter:
            print("Workspace filter: " + ", ".join(str(item) for item in workspace_filter))
        track_filter = rendered["track_filter"]
        assert isinstance(track_filter, list)
        if track_filter:
            print("Track filter: " + ", ".join(str(item) for item in track_filter))
        print(f"Workspaces: {rendered['workspace_total']}")
        print(f"Tracks: {rendered['track_total']}")
        print(f"Campaigns: {rendered['campaign_total']}")
        print(f"Attempts: {rendered['attempt_total']}")
        print(f"Pruned candidates: {rendered['pruned_candidate_total']}")
        print(f"Promoted candidates: {rendered['promoted_candidate_total']}")
        _print_resource_usage_summary(rendered["resource_usage"])
    elif report_type == "workspace_campaign_run_report":
        print(f"Workspace: {rendered['workspace_id']}")
        print(f"Tracks run: {rendered['completed_track_total']}/{rendered['track_total']}")
        print(f"Success tracks: {rendered['success_track_total']}")
        print(f"Failed tracks: {rendered['failed_track_total']}")
        print(f"Status: {rendered['status']}")
        print(f"Stop reason: {rendered['stop_reason']}")
        _print_resource_usage_summary(rendered["resource_usage"])
    else:
        print(
            f"Workspaces run: "
            f"{rendered['completed_workspace_total']}/{rendered['workspace_total']}"
        )
        print(f"Success workspaces: {rendered['success_workspace_total']}")
        print(f"Failed workspaces: {rendered['failed_workspace_total']}")
        print(f"Status: {rendered['status']}")
        print(f"Stop reason: {rendered['stop_reason']}")
        _print_resource_usage_summary(rendered["resource_usage"])

    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_validate_campaign_report_file(args: argparse.Namespace) -> int:
    rendered = _render_campaign_report_validation(args.path)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0 if bool(rendered["valid"]) else 1

    print(f"Report type: {rendered['report_type']}")
    print(f"Report path: {rendered['report_path']}")
    print(f"Format version: {rendered['format_version']}")
    print(f"Valid: {'yes' if rendered['valid'] else 'no'}")
    print(f"Errors: {rendered['error_count']}")
    validation_errors = rendered["validation_errors"]
    assert isinstance(validation_errors, list)
    for error in validation_errors:
        print(error)
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0 if bool(rendered["valid"]) else 1


def _handle_export_workspace_campaign_run_report(args: argparse.Namespace) -> int:
    rendered = _capture_batch_run_rendered(_handle_run_workspace_campaigns, args)
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.workspace_campaign_run_report.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )
    print(f"Workspace: {rendered['workspace_id']}")
    print(f"Tracks run: {rendered['completed_track_total']}/{rendered['track_total']}")
    print(f"Status: {rendered['status']}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0


def _handle_export_root_campaign_run_report(args: argparse.Namespace) -> int:
    rendered = _capture_batch_run_rendered(_handle_run_root_campaigns, args)
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.root_campaign_run_report.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )
    print(f"Workspaces run: {rendered['completed_workspace_total']}/{rendered['workspace_total']}")
    print(f"Status: {rendered['status']}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0


def _handle_show_root_campaigns(args: argparse.Namespace) -> int:
    rendered = _render_root_campaign_listing(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
        requested_track_ids=list(args.track_id),
    )
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspaces: {rendered['workspace_total']}")
    print(f"Tracks: {rendered['track_total']}")
    print(f"Campaigns: {rendered['campaign_total']}")
    print(f"Attempts: {rendered['attempt_total']}")
    print(f"Pruned candidates: {rendered['pruned_candidate_total']}")
    print(f"Promoted candidates: {rendered['promoted_candidate_total']}")
    _print_resource_usage_summary(rendered["resource_usage"])
    search_policy_mix = rendered["search_policy_mix"]
    assert isinstance(search_policy_mix, dict)
    by_generator_id = search_policy_mix["by_generator_id"]
    by_strategy = search_policy_mix["by_strategy"]
    by_stage_progression_mode = search_policy_mix["by_stage_progression_mode"]
    by_candidate_source_mode = search_policy_mix["by_candidate_source_mode"]
    by_beam_width = search_policy_mix["by_beam_width"]
    by_beam_group_limit = search_policy_mix["by_beam_group_limit"]
    by_repeat_count = search_policy_mix["by_repeat_count"]
    by_preflight_check_count = search_policy_mix["by_preflight_check_count"]
    by_max_generation_total_tokens = search_policy_mix["by_max_generation_total_tokens"]
    by_max_benchmark_total_cost = search_policy_mix["by_max_benchmark_total_cost"]
    by_max_generation_retries = search_policy_mix["by_max_generation_retries"]
    by_max_generation_timeout_retries = search_policy_mix[
        "by_max_generation_timeout_retries"
    ]
    by_max_generation_provider_retries = search_policy_mix[
        "by_max_generation_provider_retries"
    ]
    by_max_generation_process_retries = search_policy_mix[
        "by_max_generation_process_retries"
    ]
    by_max_execution_retries = search_policy_mix["by_max_execution_retries"]
    by_max_benchmark_timeout_retries = search_policy_mix[
        "by_max_benchmark_timeout_retries"
    ]
    by_max_benchmark_command_retries = search_policy_mix[
        "by_max_benchmark_command_retries"
    ]
    by_max_inconclusive_retries = search_policy_mix["by_max_inconclusive_retries"]
    by_auto_promote = search_policy_mix["by_auto_promote"]
    by_allow_flaky_promotion = search_policy_mix["by_allow_flaky_promotion"]
    by_auto_promote_min_stage = search_policy_mix["by_auto_promote_min_stage"]
    by_stop_on_first_promotion = search_policy_mix["by_stop_on_first_promotion"]
    assert isinstance(by_generator_id, dict)
    assert isinstance(by_strategy, dict)
    assert isinstance(by_stage_progression_mode, dict)
    assert isinstance(by_candidate_source_mode, dict)
    assert isinstance(by_beam_width, dict)
    assert isinstance(by_beam_group_limit, dict)
    assert isinstance(by_repeat_count, dict)
    assert isinstance(by_preflight_check_count, dict)
    assert isinstance(by_max_generation_total_tokens, dict)
    assert isinstance(by_max_benchmark_total_cost, dict)
    assert isinstance(by_max_generation_retries, dict)
    assert isinstance(by_max_generation_timeout_retries, dict)
    assert isinstance(by_max_generation_provider_retries, dict)
    assert isinstance(by_max_generation_process_retries, dict)
    assert isinstance(by_max_execution_retries, dict)
    assert isinstance(by_max_benchmark_timeout_retries, dict)
    assert isinstance(by_max_benchmark_command_retries, dict)
    assert isinstance(by_max_inconclusive_retries, dict)
    assert isinstance(by_auto_promote, dict)
    assert isinstance(by_allow_flaky_promotion, dict)
    assert isinstance(by_auto_promote_min_stage, dict)
    assert isinstance(by_stop_on_first_promotion, dict)
    print("Generator mix: " + _format_count_map(by_generator_id))
    print("Strategy mix: " + _format_count_map(by_strategy))
    print("Stage progression mix: " + _format_count_map(by_stage_progression_mode))
    print("Source mode mix: " + _format_count_map(by_candidate_source_mode))
    print("Beam width mix: " + _format_count_map(by_beam_width))
    print("Beam group mix: " + _format_count_map(by_beam_group_limit))
    print("Repeat count mix: " + _format_count_map(by_repeat_count))
    print("Preflight check mix: " + _format_count_map(by_preflight_check_count))
    print(
        "Generation token budget mix: "
        + _format_count_map(by_max_generation_total_tokens)
    )
    print(
        "Benchmark cost budget mix: "
        + _format_count_map(by_max_benchmark_total_cost)
    )
    print("Generation retry mix: " + _format_count_map(by_max_generation_retries))
    print(
        "Generation-timeout retry mix: "
        + _format_count_map(by_max_generation_timeout_retries)
    )
    print(
        "Generation-provider retry mix: "
        + _format_count_map(by_max_generation_provider_retries)
    )
    print(
        "Generation-process retry mix: "
        + _format_count_map(by_max_generation_process_retries)
    )
    print("Execution retry mix: " + _format_count_map(by_max_execution_retries))
    print(
        "Benchmark-timeout retry mix: "
        + _format_count_map(by_max_benchmark_timeout_retries)
    )
    print(
        "Benchmark-command retry mix: "
        + _format_count_map(by_max_benchmark_command_retries)
    )
    print(
        "Inconclusive retry mix: "
        + _format_count_map(by_max_inconclusive_retries)
    )
    print("Auto-promote mix: " + _format_count_map(by_auto_promote))
    print(
        "Allow-flaky-promotion mix: "
        + _format_count_map(by_allow_flaky_promotion)
    )
    print(
        "Auto-promote minimum stage mix: "
        + _format_count_map(by_auto_promote_min_stage)
    )
    print(
        "Stop-on-first-promotion mix: "
        + _format_count_map(by_stop_on_first_promotion)
    )
    if args.workspace_id:
        print(f"Workspace filter: {', '.join(args.workspace_id)}")
    if args.track_id:
        print(f"Track filter: {', '.join(args.track_id)}")
    for item in rendered["campaigns"]:
        print(
            f"- {item['workspace_id']}/{item['track_id']}/{item['campaign_id']}: "
            f"status={item['status']}, stage={item['stage']}, "
            f"generator={item['generator_id']}, strategy={item['strategy']}, "
            f"beam_width={item.get('beam_width') or 1}, "
            f"beam_groups={item.get('beam_group_limit') or 1}, "
            f"source={item['candidate_source_mode']}, next={item['next_candidate_index']}/{item['candidate_total']}, "
            f"successes={item['success_count']}, failures={item['failure_count']}, "
            f"inconclusive={item['inconclusive_count']}, promotions={item['promoted_count']}, "
            f"pruned={item['pruned_candidate_total']}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_campaign_queue(args: argparse.Namespace) -> int:
    rendered = _render_campaign_queue(
        root=args.root,
        requested_workspace_ids=list(getattr(args, "workspace_id", [])),
        requested_track_ids=list(getattr(args, "track_id", [])),
    )
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspaces: {rendered['workspace_total']}")
    print(f"Tracks: {rendered['track_total']}")
    print(f"Campaigns: {rendered['campaign_total']}")
    print(f"Runnable campaigns: {rendered['runnable_campaign_total']}")
    print(f"Workers: {rendered['worker_total']}")
    print(f"Active workers: {rendered['active_worker_total']}")
    print("Campaign statuses: " + _format_count_map(rendered["campaign_status_counts"]))
    print("Desired states: " + _format_count_map(rendered["desired_state_counts"]))
    print("Lease states: " + _format_count_map(rendered["lease_state_counts"]))
    print("Retry counts: " + _format_count_map(rendered["retry_counts"]))
    print(
        "Failure classes: "
        + _format_count_map(rendered["failure_class_counts"])
    )
    print(f"Events: {rendered['event_total']}")
    _print_resource_usage_summary(rendered["resource_usage"])
    if rendered["workspace_leases"]:
        print("Workspace leases:")
        for lease in rendered["workspace_leases"]:
            print(
                f"- {lease['workspace_id']}: "
                f"worker={lease.get('lease_owner') or '(none)'} "
                f"stale={lease.get('is_stale')} "
                f"expires={lease.get('lease_expires_at') or '(none)'}"
            )
    if rendered["workers"]:
        print("Workers:")
        for worker in rendered["workers"]:
            print(
                f"- {worker['worker_id']}: "
                f"campaign_leases={worker['active_campaign_lease_total']} "
                f"stale_campaign_leases={worker['stale_campaign_lease_total']} "
                f"workspace_leases={worker['active_workspace_lease_total']} "
                f"stale_workspace_leases={worker['stale_workspace_lease_total']}"
            )
    for item in rendered["campaigns"]:
        lease = item["lease"]
        print(
            f"- {item['workspace_id']}/{item['track_id']}/{item['campaign_id']}: "
            f"status={item['status']} desired={item['desired_state']} "
            f"runnable={item['runnable']} "
            f"worker={lease.get('lease_owner') or '(none)'} "
            f"stale={lease.get('is_stale')} "
            f"retries={_format_count_map(item['retry_counts'])} "
            f"failures={_format_count_map(item['failure_class_counts'])}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_export_root_campaign_report(args: argparse.Namespace) -> int:
    rendered = _render_root_campaign_listing(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
        requested_track_ids=list(args.track_id),
    )
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.root_campaign_report.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )
    print(f"Workspaces: {rendered['workspace_total']}")
    print(f"Campaigns: {rendered['campaign_total']}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0


def _handle_run_campaign_worker(args: argparse.Namespace) -> int:
    worker_id = args.worker_id or f"worker_{uuid.uuid4().hex[:8]}"
    rendered = _run_campaign_worker(
        root=args.root,
        workspace_ids=list(getattr(args, "workspace_id", [])),
        track_ids=list(getattr(args, "track_id", [])),
        worker_id=worker_id,
        lease_seconds=args.lease_seconds,
        max_campaigns=args.max_campaigns if args.max_campaigns is not None else None,
    )
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Worker: {worker_id}")
    claimed_campaign_total = rendered["claimed_campaign_total"]
    assert isinstance(claimed_campaign_total, int)
    print(f"Claimed campaigns: {claimed_campaign_total}")
    campaigns = rendered["campaigns"]
    assert isinstance(campaigns, list)
    for item in campaigns:
        assert isinstance(item, dict)
        print(
            f"- {item['workspace_id']}/{item['track_id']}: "
            f"{item['campaign_id']} status={item['status']} stop_reason={item['stop_reason']}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_pause_campaign(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    try:
        track_id, campaign = resolve_workspace_campaign_run(
            root=args.root,
            workspace_id=args.workspace_id,
            campaign_run_id=args.campaign_id,
            track_id=args.track_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    updated = set_campaign_desired_state(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        campaign_run_id=campaign.campaign_run_id,
        desired_state="paused",
    )
    append_workspace_event(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        campaign_run_id=campaign.campaign_run_id,
        status=updated.status,
        event_type="campaign_pause_requested",
        details={"desired_state": updated.desired_state},
    )
    rendered = _render_campaign(updated, root=args.root)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Campaign run: {campaign.campaign_run_id}")
    print("Desired state: paused")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_cancel_campaign(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    try:
        track_id, campaign = resolve_workspace_campaign_run(
            root=args.root,
            workspace_id=args.workspace_id,
            campaign_run_id=args.campaign_id,
            track_id=args.track_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    updated = set_campaign_desired_state(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        campaign_run_id=campaign.campaign_run_id,
        desired_state="canceled",
    )
    append_workspace_event(
        root=args.root,
        workspace_id=args.workspace_id,
        track_id=track_id,
        campaign_run_id=campaign.campaign_run_id,
        status=updated.status,
        event_type="campaign_cancel_requested",
        details={"desired_state": updated.desired_state},
    )
    rendered = _render_campaign(updated, root=args.root)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {track_id}")
    print(f"Campaign run: {campaign.campaign_run_id}")
    print("Desired state: canceled")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_resume_campaign(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    try:
        track_id, campaign = resolve_workspace_campaign_run(
            root=args.root,
            workspace_id=args.workspace_id,
            campaign_run_id=args.campaign_id,
            track_id=args.track_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    if campaign.execution_mode == "background":
        campaign = set_campaign_desired_state(
            root=args.root,
            workspace_id=args.workspace_id,
            track_id=track_id,
            campaign_run_id=campaign.campaign_run_id,
            desired_state="run",
        )
    campaign = replace(
        campaign,
        status="running",
        stop_reason=None,
        desired_state="run",
    )
    campaign = _execute_campaign(root=args.root, campaign=campaign)
    rendered = _render_campaign(campaign, root=args.root)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {campaign.track_id}")
    print(f"Campaign run: {campaign.campaign_run_id}")
    print(f"Status: {campaign.status}")
    print(f"Strategy: {campaign.strategy}")
    if campaign.beam_width is not None:
        print(f"Beam width: {campaign.beam_width}")
    if campaign.beam_group_limit is not None:
        print(f"Beam groups: {campaign.beam_group_limit}")
    print(f"Source mode: {campaign.candidate_source_mode}")
    print(f"Stop reason: {campaign.stop_reason}")
    print(f"Successes: {rendered['success_count']}")
    print(f"Failures: {rendered['failure_count']}")
    print(f"Inconclusive: {rendered['inconclusive_count']}")
    print(f"Promotions: {rendered['promoted_count']}")
    print(f"Pruned candidates: {rendered['pruned_candidate_total']}")
    print(f"Attempts: {rendered['attempt_total']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_campaign(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    try:
        _, campaign = resolve_workspace_campaign_run(
            root=args.root,
            workspace_id=args.workspace_id,
            campaign_run_id=args.campaign_id,
            track_id=args.track_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    rendered = _render_campaign(campaign, root=args.root)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {campaign.track_id}")
    print(f"Campaign run: {campaign.campaign_run_id}")
    print(f"Status: {campaign.status}")
    print(f"Strategy: {campaign.strategy}")
    if campaign.beam_width is not None:
        print(f"Beam width: {campaign.beam_width}")
    if campaign.preflight_checks:
        print("Preflight checks: " + ", ".join(campaign.preflight_checks))
    print(f"Source mode: {campaign.candidate_source_mode}")
    print(f"Next candidate index: {campaign.next_candidate_index}")
    print(f"Stop reason: {campaign.stop_reason or '(none)'}")
    print(f"Decision log entries: {len(campaign.decision_log)}")
    print(f"Pruned candidates: {rendered['pruned_candidate_total']}")
    print(f"Attempts: {rendered['attempt_total']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_show_campaigns(args: argparse.Namespace) -> int:
    args.workspace_id = _resolve_workspace_id(
        root=args.root,
        requested_workspace_id=args.workspace_id,
    )
    rendered = _render_workspace_campaign_listing(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_ids=[args.track_id] if args.track_id is not None else [],
    )
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Tracks: {rendered['track_total']}")
    print(f"Campaign runs: {rendered['campaign_total']}")
    print(f"Attempts: {rendered['attempt_total']}")
    print(f"Pruned candidates: {rendered['pruned_candidate_total']}")
    print(f"Promoted candidates: {rendered['promoted_candidate_total']}")
    _print_resource_usage_summary(rendered["resource_usage"])
    if args.track_id is not None:
        print(f"Track filter: {args.track_id}")
    search_policy_mix = rendered["search_policy_mix"]
    assert isinstance(search_policy_mix, dict)
    by_generator_id = search_policy_mix["by_generator_id"]
    by_strategy = search_policy_mix["by_strategy"]
    by_stage_progression_mode = search_policy_mix["by_stage_progression_mode"]
    by_candidate_source_mode = search_policy_mix["by_candidate_source_mode"]
    by_beam_width = search_policy_mix["by_beam_width"]
    by_beam_group_limit = search_policy_mix["by_beam_group_limit"]
    by_repeat_count = search_policy_mix["by_repeat_count"]
    by_preflight_check_count = search_policy_mix["by_preflight_check_count"]
    by_max_generation_total_tokens = search_policy_mix["by_max_generation_total_tokens"]
    by_max_benchmark_total_cost = search_policy_mix["by_max_benchmark_total_cost"]
    by_max_generation_retries = search_policy_mix["by_max_generation_retries"]
    by_max_generation_timeout_retries = search_policy_mix[
        "by_max_generation_timeout_retries"
    ]
    by_max_generation_provider_retries = search_policy_mix[
        "by_max_generation_provider_retries"
    ]
    by_max_generation_process_retries = search_policy_mix[
        "by_max_generation_process_retries"
    ]
    by_max_execution_retries = search_policy_mix["by_max_execution_retries"]
    by_max_benchmark_timeout_retries = search_policy_mix[
        "by_max_benchmark_timeout_retries"
    ]
    by_max_benchmark_command_retries = search_policy_mix[
        "by_max_benchmark_command_retries"
    ]
    by_max_inconclusive_retries = search_policy_mix["by_max_inconclusive_retries"]
    by_auto_promote = search_policy_mix["by_auto_promote"]
    by_auto_promote_min_stage = search_policy_mix["by_auto_promote_min_stage"]
    by_stop_on_first_promotion = search_policy_mix["by_stop_on_first_promotion"]
    assert isinstance(by_generator_id, dict)
    assert isinstance(by_strategy, dict)
    assert isinstance(by_stage_progression_mode, dict)
    assert isinstance(by_candidate_source_mode, dict)
    assert isinstance(by_beam_width, dict)
    assert isinstance(by_beam_group_limit, dict)
    assert isinstance(by_repeat_count, dict)
    assert isinstance(by_preflight_check_count, dict)
    assert isinstance(by_max_generation_total_tokens, dict)
    assert isinstance(by_max_benchmark_total_cost, dict)
    assert isinstance(by_max_generation_retries, dict)
    assert isinstance(by_max_generation_timeout_retries, dict)
    assert isinstance(by_max_generation_provider_retries, dict)
    assert isinstance(by_max_generation_process_retries, dict)
    assert isinstance(by_max_execution_retries, dict)
    assert isinstance(by_max_benchmark_timeout_retries, dict)
    assert isinstance(by_max_benchmark_command_retries, dict)
    assert isinstance(by_max_inconclusive_retries, dict)
    assert isinstance(by_auto_promote, dict)
    assert isinstance(by_auto_promote_min_stage, dict)
    assert isinstance(by_stop_on_first_promotion, dict)
    print("Generator mix: " + _format_count_map(by_generator_id))
    print("Strategy mix: " + _format_count_map(by_strategy))
    print("Stage progression mix: " + _format_count_map(by_stage_progression_mode))
    print("Source mode mix: " + _format_count_map(by_candidate_source_mode))
    print("Beam width mix: " + _format_count_map(by_beam_width))
    print("Beam group mix: " + _format_count_map(by_beam_group_limit))
    print("Repeat count mix: " + _format_count_map(by_repeat_count))
    print("Preflight check mix: " + _format_count_map(by_preflight_check_count))
    print(
        "Generation token budget mix: "
        + _format_count_map(by_max_generation_total_tokens)
    )
    print(
        "Benchmark cost budget mix: "
        + _format_count_map(by_max_benchmark_total_cost)
    )
    print("Generation retry mix: " + _format_count_map(by_max_generation_retries))
    print(
        "Generation-timeout retry mix: "
        + _format_count_map(by_max_generation_timeout_retries)
    )
    print(
        "Generation-provider retry mix: "
        + _format_count_map(by_max_generation_provider_retries)
    )
    print(
        "Generation-process retry mix: "
        + _format_count_map(by_max_generation_process_retries)
    )
    print("Execution retry mix: " + _format_count_map(by_max_execution_retries))
    print(
        "Benchmark-timeout retry mix: "
        + _format_count_map(by_max_benchmark_timeout_retries)
    )
    print(
        "Benchmark-command retry mix: "
        + _format_count_map(by_max_benchmark_command_retries)
    )
    print(
        "Inconclusive retry mix: "
        + _format_count_map(by_max_inconclusive_retries)
    )
    print("Auto-promote mix: " + _format_count_map(by_auto_promote))
    print(
        "Auto-promote minimum stage mix: "
        + _format_count_map(by_auto_promote_min_stage)
    )
    print(
        "Stop-on-first-promotion mix: "
        + _format_count_map(by_stop_on_first_promotion)
    )
    for item in rendered["campaigns"]:
        resource_usage = item.get("resource_usage")
        generation_total_tokens = None
        benchmark_total_cost = None
        if isinstance(resource_usage, dict):
            generation_total_tokens = resource_usage.get("generation_total_tokens")
            benchmark_total_cost = resource_usage.get("benchmark_total_cost")
        print(
            f"- {item['campaign_id']}: track={item['track_id']}, status={item['status']}, "
            f"stage={item['stage']}, adapter={item['adapter_id']}, "
            f"strategy={item['strategy']}, beam_width={item.get('beam_width') or 1}, "
            f"beam_groups={item.get('beam_group_limit') or 1}, "
            f"repeat={item.get('repeat_count') or 1}, "
            f"source={item['candidate_source_mode']}, "
            f"next={item['next_candidate_index']}/{item['candidate_total']}, "
            f"successes={item['success_count']}, failures={item['failure_count']}, "
            f"inconclusive={item['inconclusive_count']}, promotions={item['promoted_count']}, "
            f"pruned={item['pruned_candidate_total']}, "
            f"generation_tokens={generation_total_tokens or 0}, "
            f"benchmark_cost={benchmark_total_cost or 0.0}"
        )
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_export_workspace_campaign_report(args: argparse.Namespace) -> int:
    rendered = _render_workspace_campaign_listing(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_ids=[args.track_id] if args.track_id is not None else [],
    )
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.workspace_campaign_report.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )
    print(f"Workspace: {args.workspace_id}")
    print(f"Campaigns: {rendered['campaign_total']}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0


def _write_campaign_bundle(
    *,
    root: Path,
    campaign: CampaignRun,
    output_dir: Path,
    explicit_format: str | None,
    force: bool,
) -> dict[str, object]:
    _prepare_export_dir(output_dir, force=force)

    structured_format = explicit_format or "json"
    suffix = "json" if structured_format == "json" else "yaml"

    campaign_rendered = _render_campaign(campaign, root=root)
    campaign_report = {
        "format_version": "autoharness.campaign_report.v1",
        "exported_at": _utc_now(),
        **_render_campaign_report(root=root, campaign=campaign),
    }

    campaign_payload_path = output_dir / f"campaign.{suffix}"
    campaign_report_path = output_dir / f"campaign_report.{suffix}"
    campaign_events_path = output_dir / "campaign_events.jsonl"
    _write_structured_payload(
        campaign_payload_path,
        campaign_rendered,
        explicit_format=explicit_format,
    )
    _write_structured_payload(
        campaign_report_path,
        campaign_report,
        explicit_format=explicit_format,
    )
    _write_events_jsonl(
        campaign_events_path,
        load_workspace_events(
            root=root,
            workspace_id=campaign.workspace_id,
            track_id=campaign.track_id,
            campaign_run_id=campaign.campaign_run_id,
        ),
    )

    proposal_entries = []
    record_entries = []
    iteration_entries = []
    promotion_entries = []
    for candidate in campaign.candidates:
        if candidate.proposal_id is not None:
            proposal = load_proposal(
                root=root,
                workspace_id=campaign.workspace_id,
                track_id=campaign.track_id,
                proposal_id=candidate.proposal_id,
            )
            proposal_artifacts = resolve_proposal_artifact_paths(root=root, proposal=proposal)
            source_dir = Path(proposal_artifacts["proposal_dir"])
            target_dir = output_dir / "proposals" / proposal.proposal_id
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            proposal_entries.append(
                {
                    "proposal_id": proposal.proposal_id,
                    "path": str(target_dir.relative_to(output_dir)),
                }
            )
        if candidate.record_id is not None:
            source_path = (
                root
                / campaign.workspace_id
                / "tracks"
                / campaign.track_id
                / "registry"
                / f"{candidate.record_id}.json"
            )
            target_path = output_dir / "records" / source_path.name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            record_entries.append(
                {
                    "record_id": candidate.record_id,
                    "path": str(target_path.relative_to(output_dir)),
                }
            )
        if candidate.iteration_id is not None:
            source_dir = iteration_dir_path(
                root=root,
                workspace_id=campaign.workspace_id,
                iteration_id=candidate.iteration_id,
            )
            target_dir = output_dir / "iterations" / candidate.iteration_id
            shutil.copytree(source_dir, target_dir, dirs_exist_ok=True)
            iteration_entries.append(
                {
                    "iteration_id": candidate.iteration_id,
                    "path": str(target_dir.relative_to(output_dir)),
                }
            )
        if candidate.promotion_id is not None:
            promotion_json = (
                root
                / campaign.workspace_id
                / "tracks"
                / campaign.track_id
                / "promotions"
                / f"{candidate.promotion_id}.json"
            )
            promotion_patch = promotion_json.with_suffix(".patch")
            target_json = output_dir / "promotions" / promotion_json.name
            target_json.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(promotion_json, target_json)
            target_patch = None
            if promotion_patch.exists():
                target_patch = output_dir / "promotions" / promotion_patch.name
                shutil.copy2(promotion_patch, target_patch)
            promotion_entries.append(
                {
                    "promotion_id": candidate.promotion_id,
                    "path": str(target_json.relative_to(output_dir)),
                    "diff_path": (
                        str(target_patch.relative_to(output_dir))
                        if target_patch is not None
                        else None
                    ),
                }
            )

    champion_bundle = None
    try:
        champion_bundle = _export_champion_bundle(
            root=root,
            workspace_id=campaign.workspace_id,
            track_id=campaign.track_id,
            output_dir=output_dir / "champion",
            force=True,
        )
    except SystemExit as exc:
        if "No champion manifest" not in str(exc) and "not found" not in str(exc):
            raise
        champion_bundle = None

    bundle_manifest_path = output_dir / f"bundle_manifest.{suffix}"
    bundle_manifest = {
        "format_version": "autoharness.campaign_bundle.v1",
        "exported_at": _utc_now(),
        "workspace_id": campaign.workspace_id,
        "track_id": campaign.track_id,
        "campaign_id": campaign.campaign_run_id,
        "artifact_format": structured_format,
        "artifacts": {
            "campaign_path": str(campaign_payload_path.relative_to(output_dir)),
            "campaign_report_path": str(campaign_report_path.relative_to(output_dir)),
            "campaign_events_path": str(campaign_events_path.relative_to(output_dir)),
            "proposal_dirs": proposal_entries,
            "record_paths": record_entries,
            "iteration_dirs": iteration_entries,
            "promotion_artifacts": promotion_entries,
            "champion_bundle": (
                {
                    "path": "champion",
                    "record_id": champion_bundle["record_id"],
                    "promotion_id": champion_bundle["promotion_id"],
                }
                if champion_bundle is not None
                else None
            ),
        },
    }
    _write_structured_payload(
        bundle_manifest_path,
        bundle_manifest,
        explicit_format=explicit_format,
    )
    return {
        "workspace_id": campaign.workspace_id,
        "track_id": campaign.track_id,
        "campaign_id": campaign.campaign_run_id,
        "bundle_path": output_dir,
        "manifest_path": bundle_manifest_path,
        "artifact_format": structured_format,
    }


def _write_workspace_campaign_bundle(
    *,
    root: Path,
    workspace_id: str,
    requested_track_ids: list[str],
    output_dir: Path,
    explicit_format: str | None,
    force: bool,
) -> dict[str, object]:
    _prepare_export_dir(output_dir, force=force)

    structured_format = explicit_format or "json"
    suffix = "json" if structured_format == "json" else "yaml"
    rendered = _render_workspace_campaign_listing(
        root=root,
        workspace_id=workspace_id,
        requested_track_ids=requested_track_ids,
    )
    workspace_report = {
        "format_version": "autoharness.workspace_campaign_report.v1",
        "exported_at": _utc_now(),
        **rendered,
    }
    workspace_report_path = output_dir / f"workspace_campaign_report.{suffix}"
    workspace_events_path = output_dir / "workspace_events.jsonl"
    _write_structured_payload(
        workspace_report_path,
        workspace_report,
        explicit_format=explicit_format,
    )
    _write_events_jsonl(
        workspace_events_path,
        load_workspace_events(root=root, workspace_id=workspace_id),
    )

    campaign_bundles = []
    for item in rendered["campaigns"]:
        track_id = str(item["track_id"])
        campaign_id = str(item["campaign_id"])
        campaign = load_campaign_run(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            campaign_run_id=campaign_id,
        )
        nested_bundle_dir = output_dir / "campaigns" / track_id / campaign_id
        _write_campaign_bundle(
            root=root,
            campaign=campaign,
            output_dir=nested_bundle_dir,
            explicit_format=explicit_format,
            force=True,
        )
        campaign_bundles.append(
            {
                "track_id": track_id,
                "campaign_id": campaign_id,
                "path": str(nested_bundle_dir.relative_to(output_dir)),
            }
        )

    bundle_manifest_path = output_dir / f"bundle_manifest.{suffix}"
    bundle_manifest = {
        "format_version": "autoharness.workspace_campaign_bundle.v1",
        "exported_at": _utc_now(),
        "workspace_id": workspace_id,
        "track_filter": list(requested_track_ids),
        "artifact_format": structured_format,
        "artifacts": {
            "workspace_campaign_report_path": str(
                workspace_report_path.relative_to(output_dir)
            ),
            "workspace_events_path": str(workspace_events_path.relative_to(output_dir)),
            "campaign_bundles": campaign_bundles,
        },
    }
    _write_structured_payload(
        bundle_manifest_path,
        bundle_manifest,
        explicit_format=explicit_format,
    )
    return {
        "workspace_id": workspace_id,
        "bundle_path": output_dir,
        "manifest_path": bundle_manifest_path,
        "artifact_format": structured_format,
        "campaign_total": len(campaign_bundles),
    }


def _write_root_campaign_bundle(
    *,
    root: Path,
    requested_workspace_ids: list[str],
    requested_track_ids: list[str],
    output_dir: Path,
    explicit_format: str | None,
    force: bool,
) -> dict[str, object]:
    _prepare_export_dir(output_dir, force=force)

    structured_format = explicit_format or "json"
    suffix = "json" if structured_format == "json" else "yaml"
    rendered = _render_root_campaign_listing(
        root=root,
        requested_workspace_ids=requested_workspace_ids,
        requested_track_ids=requested_track_ids,
    )
    root_report = {
        "format_version": "autoharness.root_campaign_report.v1",
        "exported_at": _utc_now(),
        **rendered,
    }
    root_report_path = output_dir / f"root_campaign_report.{suffix}"
    _write_structured_payload(
        root_report_path,
        root_report,
        explicit_format=explicit_format,
    )

    requested_workspace_id_set = set(requested_workspace_ids)
    selected_workspace_ids = [
        workspace_id
        for workspace_id in _discover_workspace_ids(root)
        if not requested_workspace_id_set or workspace_id in requested_workspace_id_set
    ]
    workspace_bundles = []
    for workspace_id in selected_workspace_ids:
        nested_bundle_dir = output_dir / "workspaces" / workspace_id
        workspace_rendered = _write_workspace_campaign_bundle(
            root=root,
            workspace_id=workspace_id,
            requested_track_ids=requested_track_ids,
            output_dir=nested_bundle_dir,
            explicit_format=explicit_format,
            force=True,
        )
        workspace_bundles.append(
            {
                "workspace_id": workspace_id,
                "path": str(nested_bundle_dir.relative_to(output_dir)),
                "campaign_total": workspace_rendered["campaign_total"],
            }
        )

    bundle_manifest_path = output_dir / f"bundle_manifest.{suffix}"
    bundle_manifest = {
        "format_version": "autoharness.root_campaign_bundle.v1",
        "exported_at": _utc_now(),
        "workspace_filter": list(requested_workspace_ids),
        "track_filter": list(requested_track_ids),
        "artifact_format": structured_format,
        "artifacts": {
            "root_campaign_report_path": str(root_report_path.relative_to(output_dir)),
            "workspace_bundles": workspace_bundles,
        },
    }
    _write_structured_payload(
        bundle_manifest_path,
        bundle_manifest,
        explicit_format=explicit_format,
    )
    return {
        "bundle_path": output_dir,
        "manifest_path": bundle_manifest_path,
        "artifact_format": structured_format,
        "workspace_total": len(workspace_bundles),
    }


def _handle_show_campaign_artifacts(args: argparse.Namespace) -> int:
    try:
        _, campaign = resolve_workspace_campaign_run(
            root=args.root,
            workspace_id=args.workspace_id,
            campaign_run_id=args.campaign_id,
            track_id=args.track_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    rendered = _render_campaign_artifacts(root=args.root, campaign=campaign)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {campaign.track_id}")
    print(f"Campaign run: {campaign.campaign_run_id}")
    print(f"Proposals: {len(rendered['proposal_artifacts'])}")
    print(f"Records: {len(rendered['record_artifacts'])}")
    print(f"Iterations: {len(rendered['iteration_artifacts'])}")
    print(f"Promotions: {len(rendered['promotion_artifacts'])}")
    print(f"Champion: {'present' if rendered['champion_artifacts'] is not None else 'absent'}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_export_campaign_report(args: argparse.Namespace) -> int:
    try:
        _, campaign = resolve_workspace_campaign_run(
            root=args.root,
            workspace_id=args.workspace_id,
            campaign_run_id=args.campaign_id,
            track_id=args.track_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    rendered = _render_campaign_report(root=args.root, campaign=campaign)
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.campaign_report.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )
    print(f"Workspace: {args.workspace_id}")
    print(f"Track: {campaign.track_id}")
    print(f"Campaign run: {campaign.campaign_run_id}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0


def _handle_export_campaign_bundle(args: argparse.Namespace) -> int:
    try:
        _, campaign = resolve_workspace_campaign_run(
            root=args.root,
            workspace_id=args.workspace_id,
            campaign_run_id=args.campaign_id,
            track_id=args.track_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    rendered = _write_campaign_bundle(
        root=args.root,
        campaign=campaign,
        output_dir=args.output,
        explicit_format=args.format,
        force=args.force,
    )

    print(f"Workspace: {campaign.workspace_id}")
    print(f"Track: {campaign.track_id}")
    print(f"Campaign run: {campaign.campaign_run_id}")
    print(f"Bundle path: {rendered['bundle_path']}")
    print(f"Bundle manifest: {rendered['manifest_path']}")
    return 0


def _handle_export_workspace_campaign_bundle(args: argparse.Namespace) -> int:
    rendered = _write_workspace_campaign_bundle(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_ids=[args.track_id] if args.track_id is not None else [],
        output_dir=args.output,
        explicit_format=args.format,
        force=args.force,
    )
    print(f"Workspace: {args.workspace_id}")
    if args.track_id is not None:
        print(f"Track filter: {args.track_id}")
    print(f"Campaigns: {rendered['campaign_total']}")
    print(f"Bundle path: {rendered['bundle_path']}")
    print(f"Bundle manifest: {rendered['manifest_path']}")
    return 0


def _handle_export_root_campaign_bundle(args: argparse.Namespace) -> int:
    rendered = _write_root_campaign_bundle(
        root=args.root,
        requested_workspace_ids=list(args.workspace_id),
        requested_track_ids=list(args.track_id),
        output_dir=args.output,
        explicit_format=args.format,
        force=args.force,
    )
    print(f"Workspaces: {rendered['workspace_total']}")
    print(f"Bundle path: {rendered['bundle_path']}")
    print(f"Bundle manifest: {rendered['manifest_path']}")
    return 0
