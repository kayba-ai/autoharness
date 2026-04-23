"""Context assembly for proposal generation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .tracking import load_benchmark_record, load_iteration_summary
from .workspace import WorkspaceConfig, WorkspaceState


@dataclass(frozen=True)
class ProposalGenerationContext:
    """Stable context passed to proposal generators."""

    format_version: str
    workspace_id: str
    track_id: str
    objective: str
    domain: str
    stage: str
    adapter_id: str
    autonomy: dict[str, Any]
    benchmark_target: str | None
    selected_preset: str | None
    selected_preset_source: str | None
    policy_preset: str | None
    effective_track_policy: dict[str, Any]
    effective_config: dict[str, Any]
    target_root: str
    active_track_id: str
    workspace_status: str
    last_iteration_id: str | None = None
    last_record_id: str | None = None
    current_champion_record_id: str | None = None
    latest_iteration_summary: dict[str, Any] | None = None
    latest_record_status: str | None = None
    latest_stage_evaluation: dict[str, Any] | None = None
    latest_failure_summary: dict[str, Any] | None = None
    latest_regression_summary: dict[str, Any] | None = None
    latest_parsed_artifact_sources: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _task_key(task_result: dict[str, Any]) -> str:
    for field_name in ("case_id", "task_id"):
        value = task_result.get(field_name)
        if isinstance(value, str) and value:
            return value
    return "<unknown>"


def _render_task_entry(task_result: dict[str, Any]) -> dict[str, Any]:
    rendered: dict[str, Any] = {
        "task_key": _task_key(task_result),
    }
    for field_name in ("task_id", "case_id", "score", "success", "category", "tier", "owner"):
        value = task_result.get(field_name)
        if value is not None:
            rendered[field_name] = value
    return rendered


def _extract_failure_summary(record_payload: dict[str, Any]) -> dict[str, Any] | None:
    task_results = record_payload.get("task_results")
    if isinstance(task_results, list):
        failing_tasks = []
        for entry in task_results:
            if not isinstance(entry, dict):
                continue
            score = entry.get("score")
            success = entry.get("success")
            if isinstance(score, (int, float)) and not isinstance(score, bool):
                failed = float(score) < 1.0
            elif isinstance(success, bool):
                failed = not success
            else:
                failed = False
            if failed:
                failing_tasks.append(_render_task_entry(entry))
        failing_tasks.sort(key=lambda item: (float(item.get("score", 1.0)), str(item["task_key"])))
        if failing_tasks:
            return {
                "task_count": len(failing_tasks),
                "task_keys": [item["task_key"] for item in failing_tasks],
                "tasks": failing_tasks[:10],
                "source": "task_results",
            }

    validation_summary = record_payload.get("validation_summary")
    if not isinstance(validation_summary, dict):
        return None
    task_result_summary = validation_summary.get("task_result_summary")
    if not isinstance(task_result_summary, dict):
        return None
    mean_scores = task_result_summary.get("task_mean_scores")
    if not isinstance(mean_scores, dict):
        return None
    failing_entries = []
    for task_key, score in mean_scores.items():
        if (
            isinstance(task_key, str)
            and task_key
            and isinstance(score, (int, float))
            and not isinstance(score, bool)
            and float(score) < 1.0
        ):
            failing_entries.append({"task_key": task_key, "score": float(score)})
    failing_entries.sort(key=lambda item: (float(item["score"]), str(item["task_key"])))
    if not failing_entries:
        return None
    return {
        "task_count": len(failing_entries),
        "task_keys": [item["task_key"] for item in failing_entries],
        "tasks": failing_entries[:10],
        "source": "validation_summary.task_result_summary",
    }


def _extract_regression_summary(record_payload: dict[str, Any]) -> dict[str, Any] | None:
    stage_evaluation = record_payload.get("stage_evaluation")
    if not isinstance(stage_evaluation, dict):
        return None
    baseline_comparison = stage_evaluation.get("baseline_comparison")
    if not isinstance(baseline_comparison, dict):
        return None
    regressed_tasks = baseline_comparison.get("regressed_tasks")
    regressed_task_ids = baseline_comparison.get("regressed_task_ids")
    if not isinstance(regressed_tasks, list) and not isinstance(regressed_task_ids, list):
        return None

    rendered_tasks = []
    if isinstance(regressed_tasks, list):
        for entry in regressed_tasks:
            if not isinstance(entry, dict):
                continue
            rendered: dict[str, Any] = {}
            for field_name in (
                "task_id",
                "candidate_score",
                "baseline_score",
                "delta",
                "weight",
            ):
                value = entry.get(field_name)
                if value is not None:
                    rendered[field_name] = value
            candidate_task_result = entry.get("candidate_task_result")
            if isinstance(candidate_task_result, dict):
                rendered["task_key"] = _task_key(candidate_task_result)
                for field_name in ("case_id", "category", "tier", "owner"):
                    value = candidate_task_result.get(field_name)
                    if value is not None:
                        rendered[field_name] = value
            elif isinstance(entry.get("task_id"), str):
                rendered["task_key"] = str(entry["task_id"])
            if rendered:
                rendered_tasks.append(rendered)

    resolved_task_ids = []
    if isinstance(regressed_task_ids, list):
        resolved_task_ids = [str(entry) for entry in regressed_task_ids if isinstance(entry, str)]
    elif rendered_tasks:
        resolved_task_ids = [
            str(entry["task_key"])
            for entry in rendered_tasks
            if isinstance(entry.get("task_key"), str)
        ]
    if not resolved_task_ids and not rendered_tasks:
        return None

    return {
        "task_count": len(resolved_task_ids) or len(rendered_tasks),
        "task_keys": resolved_task_ids,
        "tasks": rendered_tasks[:10],
        "decision": baseline_comparison.get("decision"),
        "reason": baseline_comparison.get("reason"),
        "source": "stage_evaluation.baseline_comparison",
    }


def load_latest_generation_signals(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    state: WorkspaceState,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if state.last_experiment_id is None:
        return None, None
    try:
        latest_record = load_benchmark_record(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            record_id=state.last_experiment_id,
        )
    except FileNotFoundError:
        return None, None
    return (
        _extract_failure_summary(latest_record.payload),
        _extract_regression_summary(latest_record.payload),
    )


def build_proposal_generation_context(
    *,
    root: Path,
    workspace: WorkspaceConfig,
    state: WorkspaceState,
    track_id: str,
    adapter_id: str,
    stage: str,
    benchmark_target: str | None,
    selected_preset: str | None,
    selected_preset_source: str | None,
    policy_preset: str | None,
    effective_track_policy: dict[str, Any],
    effective_config: dict[str, Any],
    target_root: Path,
) -> ProposalGenerationContext:
    latest_iteration_summary = None
    latest_record_status = None
    latest_stage_evaluation = None
    latest_failure_summary = None
    latest_regression_summary = None
    latest_parsed_artifact_sources = None
    if state.last_iteration_id is not None:
        try:
            latest_iteration_summary = load_iteration_summary(
                root=root,
                workspace_id=workspace.workspace_id,
                iteration_id=state.last_iteration_id,
            )
        except FileNotFoundError:
            latest_iteration_summary = None

    if state.last_experiment_id is not None:
        try:
            latest_record = load_benchmark_record(
                root=root,
                workspace_id=workspace.workspace_id,
                track_id=track_id,
                record_id=state.last_experiment_id,
            )
        except FileNotFoundError:
            latest_record = None
        if latest_record is not None:
            latest_record_status = latest_record.status
            stage_evaluation = latest_record.payload.get("stage_evaluation")
            if isinstance(stage_evaluation, dict):
                latest_stage_evaluation = stage_evaluation
            latest_failure_summary = _extract_failure_summary(latest_record.payload)
            latest_regression_summary = _extract_regression_summary(latest_record.payload)
            parsed_artifact_sources = latest_record.payload.get("parsed_artifact_sources")
            if isinstance(parsed_artifact_sources, dict):
                latest_parsed_artifact_sources = parsed_artifact_sources

    return ProposalGenerationContext(
        format_version="autoharness.proposal_context.v1",
        workspace_id=workspace.workspace_id,
        track_id=track_id,
        objective=workspace.objective,
        domain=workspace.domain,
        stage=stage,
        adapter_id=adapter_id,
        autonomy=workspace.autonomy.to_dict(),
        benchmark_target=benchmark_target,
        selected_preset=selected_preset,
        selected_preset_source=selected_preset_source,
        policy_preset=policy_preset,
        effective_track_policy=dict(effective_track_policy),
        effective_config=dict(effective_config),
        target_root=str(target_root.resolve()),
        active_track_id=state.active_track_id,
        workspace_status=state.status,
        last_iteration_id=state.last_iteration_id,
        last_record_id=state.last_experiment_id,
        current_champion_record_id=state.current_champion_experiment_id,
        latest_iteration_summary=latest_iteration_summary,
        latest_record_status=latest_record_status,
        latest_stage_evaluation=latest_stage_evaluation,
        latest_failure_summary=latest_failure_summary,
        latest_regression_summary=latest_regression_summary,
        latest_parsed_artifact_sources=latest_parsed_artifact_sources,
    )
