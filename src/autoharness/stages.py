"""Stage-aware evaluation policies for autoharness."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .stats import paired_mean_confidence_interval


StageName = Literal["screening", "validation", "holdout", "transfer"]
StageDecisionMode = Literal["threshold", "confidence_interval"]
_STABILITY_GATE_THRESHOLDS = {
    "validation": {
        "minimum_stability_score": 0.8,
        "max_confidence_interval_width": 0.5,
    },
    "holdout": {
        "minimum_stability_score": 0.85,
        "max_confidence_interval_width": 0.45,
    },
    "transfer": {
        "minimum_stability_score": 0.85,
        "max_confidence_interval_width": 0.45,
    },
}


@dataclass(frozen=True)
class StagePolicy:
    """One stage-specific evaluation policy."""

    stage: StageName
    benchmark_policy_key: str
    default_repeat_count: int
    min_success_rate: float
    decision_mode: StageDecisionMode
    confidence_level: float | None = None
    max_regressed_tasks: int | None = None
    max_regressed_task_fraction: float | None = None
    max_regressed_task_weight: float | None = None
    max_regressed_task_weight_fraction: float | None = None
    task_regression_margin: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def stage_policy_for(
    stage: StageName,
    *,
    min_judge_pass_rate: float = 0.55,
    max_regressed_tasks: int | None = None,
    max_regressed_task_fraction: float | None = None,
    max_regressed_task_weight: float | None = None,
    max_regressed_task_weight_fraction: float | None = None,
    task_regression_margin: float = 0.0,
) -> StagePolicy:
    """Return the default stage policy for one stage name."""
    if max_regressed_tasks is not None and max_regressed_tasks < 0:
        raise ValueError("`max_regressed_tasks` must be at least 0 when provided.")
    if max_regressed_task_fraction is not None and not (
        0.0 <= max_regressed_task_fraction <= 1.0
    ):
        raise ValueError(
            "`max_regressed_task_fraction` must be between 0 and 1 when provided."
        )
    if max_regressed_task_weight is not None and max_regressed_task_weight < 0.0:
        raise ValueError("`max_regressed_task_weight` must be at least 0 when provided.")
    if max_regressed_task_weight_fraction is not None and not (
        0.0 <= max_regressed_task_weight_fraction <= 1.0
    ):
        raise ValueError(
            "`max_regressed_task_weight_fraction` must be between 0 and 1 when provided."
        )
    if task_regression_margin < 0.0:
        raise ValueError("`task_regression_margin` must be at least 0.")
    if stage == "screening":
        return StagePolicy(
            stage=stage,
            benchmark_policy_key="search_benchmark",
            default_repeat_count=1,
            min_success_rate=1.0,
            decision_mode="threshold",
            max_regressed_tasks=max_regressed_tasks,
            max_regressed_task_fraction=max_regressed_task_fraction,
            max_regressed_task_weight=max_regressed_task_weight,
            max_regressed_task_weight_fraction=max_regressed_task_weight_fraction,
            task_regression_margin=task_regression_margin,
        )
    if stage == "validation":
        return StagePolicy(
            stage=stage,
            benchmark_policy_key="search_benchmark",
            default_repeat_count=3,
            min_success_rate=min_judge_pass_rate,
            decision_mode="confidence_interval",
            confidence_level=0.85,
            max_regressed_tasks=max_regressed_tasks,
            max_regressed_task_fraction=max_regressed_task_fraction,
            max_regressed_task_weight=max_regressed_task_weight,
            max_regressed_task_weight_fraction=max_regressed_task_weight_fraction,
            task_regression_margin=task_regression_margin,
        )
    if stage == "holdout":
        return StagePolicy(
            stage=stage,
            benchmark_policy_key="promotion_benchmark",
            default_repeat_count=3,
            min_success_rate=min_judge_pass_rate,
            decision_mode="confidence_interval",
            confidence_level=0.85,
            max_regressed_tasks=max_regressed_tasks,
            max_regressed_task_fraction=max_regressed_task_fraction,
            max_regressed_task_weight=max_regressed_task_weight,
            max_regressed_task_weight_fraction=max_regressed_task_weight_fraction,
            task_regression_margin=task_regression_margin,
        )
    if stage == "transfer":
        return StagePolicy(
            stage=stage,
            benchmark_policy_key="regression_benchmark",
            default_repeat_count=3,
            min_success_rate=min_judge_pass_rate,
            decision_mode="confidence_interval",
            confidence_level=0.85,
            max_regressed_tasks=max_regressed_tasks,
            max_regressed_task_fraction=max_regressed_task_fraction,
            max_regressed_task_weight=max_regressed_task_weight,
            max_regressed_task_weight_fraction=max_regressed_task_weight_fraction,
            task_regression_margin=task_regression_margin,
        )
    raise ValueError(f"Unsupported stage: {stage}")


def apply_stage_overrides(
    config: dict[str, Any],
    *,
    stage: StageName,
) -> tuple[dict[str, Any], bool]:
    """Overlay optional stage-specific config onto one benchmark config."""
    resolved = copy.deepcopy(config)
    stage_overrides = resolved.pop("stage_overrides", None)
    if not isinstance(stage_overrides, dict):
        return resolved, False

    override = stage_overrides.get(stage)
    if override is None:
        return resolved, False
    if not isinstance(override, dict):
        raise ValueError(f"`stage_overrides.{stage}` must be a mapping.")
    return _deep_merge_dicts(resolved, override), True


def evaluate_stage_result(
    *,
    payload: dict[str, Any],
    stage_policy: StagePolicy,
    benchmark_target: str | None = None,
    applied_stage_override: bool = False,
    baseline_payload: dict[str, Any] | None = None,
    baseline_label: str | None = None,
    baseline_stage: str | None = None,
    min_improvement: float = 0.0,
) -> dict[str, Any]:
    """Evaluate one run payload against the active stage gate."""
    run_count = _resolve_run_count(payload)
    observed_success_rate, observed_source, confidence_interval = _resolve_observed_success_rate(
        payload
    )

    result: dict[str, Any] = {
        "stage": stage_policy.stage,
        "benchmark_policy_key": stage_policy.benchmark_policy_key,
        "benchmark_target": benchmark_target,
        "default_repeat_count": stage_policy.default_repeat_count,
        "min_success_rate": stage_policy.min_success_rate,
        "decision_mode": stage_policy.decision_mode,
        "confidence_level": stage_policy.confidence_level,
        "max_regressed_tasks": stage_policy.max_regressed_tasks,
        "max_regressed_task_fraction": stage_policy.max_regressed_task_fraction,
        "max_regressed_task_weight": stage_policy.max_regressed_task_weight,
        "max_regressed_task_weight_fraction": stage_policy.max_regressed_task_weight_fraction,
        "task_regression_margin": stage_policy.task_regression_margin,
        "run_count": run_count,
        "applied_stage_override": applied_stage_override,
    }
    if observed_success_rate is not None:
        result["observed_success_rate"] = observed_success_rate
        result["observed_source"] = observed_source
    if confidence_interval is not None:
        result["confidence_interval"] = confidence_interval
    validation_summary = payload.get("validation_summary")
    if isinstance(validation_summary, dict):
        stability_summary = validation_summary.get("stability_summary")
        if isinstance(stability_summary, dict):
            result["stability_summary"] = dict(stability_summary)
        stability_gate = _evaluate_stability_gate(
            stage_policy=stage_policy,
            validation_summary=validation_summary,
        )
        if stability_gate is not None:
            result["stability_gate"] = stability_gate

    if payload.get("dry_run") is True:
        result["decision"] = "planned"
        result["passed"] = None
        result["reason"] = "Dry-run only: stage gate was planned but not executed."
        if baseline_payload is not None:
            result["baseline_comparison"] = compare_against_baseline(
                candidate_payload=payload,
                baseline_payload=baseline_payload,
                baseline_label=baseline_label,
                baseline_stage=baseline_stage,
                min_improvement=min_improvement,
                max_regressed_tasks=stage_policy.max_regressed_tasks,
                max_regressed_task_fraction=stage_policy.max_regressed_task_fraction,
                max_regressed_task_weight=stage_policy.max_regressed_task_weight,
                max_regressed_task_weight_fraction=stage_policy.max_regressed_task_weight_fraction,
                task_regression_margin=stage_policy.task_regression_margin,
            )
        return result

    if observed_success_rate is None:
        result["decision"] = "unscored"
        result["passed"] = None
        result["reason"] = "No success-rate signal was available for stage evaluation."
        if baseline_payload is not None:
            result["baseline_comparison"] = compare_against_baseline(
                candidate_payload=payload,
                baseline_payload=baseline_payload,
                baseline_label=baseline_label,
                baseline_stage=baseline_stage,
                min_improvement=min_improvement,
                max_regressed_tasks=stage_policy.max_regressed_tasks,
                max_regressed_task_fraction=stage_policy.max_regressed_task_fraction,
                max_regressed_task_weight=stage_policy.max_regressed_task_weight,
                max_regressed_task_weight_fraction=stage_policy.max_regressed_task_weight_fraction,
                task_regression_margin=stage_policy.task_regression_margin,
            )
        return result

    if stage_policy.decision_mode == "threshold":
        passed = observed_success_rate >= stage_policy.min_success_rate
        result["passed"] = passed
        result["decision"] = "passed" if passed else "failed"
        result["reason"] = (
            f"Observed success rate {observed_success_rate:.3f} "
            f"{'met' if passed else 'fell below'} the {stage_policy.stage} threshold "
            f"of {stage_policy.min_success_rate:.3f}."
        )
        return _apply_baseline_gate(
            result=result,
            payload=payload,
            baseline_payload=baseline_payload,
            baseline_label=baseline_label,
            baseline_stage=baseline_stage,
            min_improvement=min_improvement,
            max_regressed_tasks=stage_policy.max_regressed_tasks,
            max_regressed_task_fraction=stage_policy.max_regressed_task_fraction,
            max_regressed_task_weight=stage_policy.max_regressed_task_weight,
            max_regressed_task_weight_fraction=stage_policy.max_regressed_task_weight_fraction,
            task_regression_margin=stage_policy.task_regression_margin,
        )

    if confidence_interval is None:
        result["decision"] = "inconclusive"
        result["passed"] = None
        result["reason"] = (
            "This stage requires a confidence interval, but none was available from "
            "the validation result."
        )
        return _apply_baseline_gate(
            result=result,
            payload=payload,
            baseline_payload=baseline_payload,
            baseline_label=baseline_label,
            baseline_stage=baseline_stage,
            min_improvement=min_improvement,
            max_regressed_tasks=stage_policy.max_regressed_tasks,
            max_regressed_task_fraction=stage_policy.max_regressed_task_fraction,
            max_regressed_task_weight=stage_policy.max_regressed_task_weight,
            max_regressed_task_weight_fraction=stage_policy.max_regressed_task_weight_fraction,
            task_regression_margin=stage_policy.task_regression_margin,
        )

    lower = confidence_interval["lower"]
    upper = confidence_interval["upper"]
    if lower >= stage_policy.min_success_rate:
        result["decision"] = "passed"
        result["passed"] = True
        result["reason"] = (
            f"The lower confidence bound {lower:.3f} met the {stage_policy.stage} "
            f"threshold of {stage_policy.min_success_rate:.3f}."
        )
        return _apply_baseline_gate(
            result=result,
            payload=payload,
            baseline_payload=baseline_payload,
            baseline_label=baseline_label,
            baseline_stage=baseline_stage,
            min_improvement=min_improvement,
            max_regressed_tasks=stage_policy.max_regressed_tasks,
            max_regressed_task_fraction=stage_policy.max_regressed_task_fraction,
            max_regressed_task_weight=stage_policy.max_regressed_task_weight,
            max_regressed_task_weight_fraction=stage_policy.max_regressed_task_weight_fraction,
            task_regression_margin=stage_policy.task_regression_margin,
        )
    if upper < stage_policy.min_success_rate:
        result["decision"] = "failed"
        result["passed"] = False
        result["reason"] = (
            f"The upper confidence bound {upper:.3f} fell below the "
            f"{stage_policy.stage} threshold of {stage_policy.min_success_rate:.3f}."
        )
        return _apply_baseline_gate(
            result=result,
            payload=payload,
            baseline_payload=baseline_payload,
            baseline_label=baseline_label,
            baseline_stage=baseline_stage,
            min_improvement=min_improvement,
            max_regressed_tasks=stage_policy.max_regressed_tasks,
            max_regressed_task_fraction=stage_policy.max_regressed_task_fraction,
            max_regressed_task_weight=stage_policy.max_regressed_task_weight,
            max_regressed_task_weight_fraction=stage_policy.max_regressed_task_weight_fraction,
            task_regression_margin=stage_policy.task_regression_margin,
        )

    result["decision"] = "inconclusive"
    result["passed"] = None
    result["reason"] = (
        f"The confidence interval [{lower:.3f}, {upper:.3f}] straddled the "
        f"{stage_policy.stage} threshold of {stage_policy.min_success_rate:.3f}."
    )
    return _apply_baseline_gate(
        result=result,
        payload=payload,
        baseline_payload=baseline_payload,
        baseline_label=baseline_label,
        baseline_stage=baseline_stage,
        min_improvement=min_improvement,
        max_regressed_tasks=stage_policy.max_regressed_tasks,
        max_regressed_task_fraction=stage_policy.max_regressed_task_fraction,
        max_regressed_task_weight=stage_policy.max_regressed_task_weight,
        max_regressed_task_weight_fraction=stage_policy.max_regressed_task_weight_fraction,
        task_regression_margin=stage_policy.task_regression_margin,
    )


def compare_against_baseline(
    *,
    candidate_payload: dict[str, Any],
    baseline_payload: dict[str, Any],
    baseline_label: str | None,
    baseline_stage: str | None,
    min_improvement: float = 0.0,
    confidence_level: float = 0.85,
    max_regressed_tasks: int | None = None,
    max_regressed_task_fraction: float | None = None,
    max_regressed_task_weight: float | None = None,
    max_regressed_task_weight_fraction: float | None = None,
    task_regression_margin: float = 0.0,
) -> dict[str, Any]:
    """Compare a candidate payload against one baseline payload."""
    candidate_rate, candidate_source, candidate_interval = _resolve_observed_success_rate(
        candidate_payload
    )
    baseline_rate, baseline_source, baseline_interval = _resolve_observed_success_rate(
        baseline_payload
    )

    result: dict[str, Any] = {
        "baseline_label": baseline_label,
        "baseline_stage": baseline_stage,
        "min_improvement": min_improvement,
        "max_regressed_tasks": max_regressed_tasks,
        "max_regressed_task_fraction": max_regressed_task_fraction,
        "max_regressed_task_weight": max_regressed_task_weight,
        "max_regressed_task_weight_fraction": max_regressed_task_weight_fraction,
        "task_regression_margin": task_regression_margin,
    }
    if candidate_rate is not None:
        result["candidate_observed_success_rate"] = candidate_rate
        result["candidate_observed_source"] = candidate_source
    if baseline_rate is not None:
        result["baseline_observed_success_rate"] = baseline_rate
        result["baseline_observed_source"] = baseline_source
    if candidate_interval is not None:
        result["candidate_confidence_interval"] = candidate_interval
    if baseline_interval is not None:
        result["baseline_confidence_interval"] = baseline_interval

    if candidate_payload.get("dry_run") is True:
        result["decision"] = "planned"
        result["passed"] = None
        result["reason"] = "Dry-run only: baseline comparison was planned but not executed."
        return result
    if baseline_payload.get("dry_run") is True:
        result["decision"] = "unavailable"
        result["passed"] = None
        result["reason"] = "Baseline payload is a dry-run and has no comparable result."
        return result

    task_comparison = _compare_task_results(
        candidate_payload=candidate_payload,
        baseline_payload=baseline_payload,
        min_improvement=min_improvement,
        confidence_level=confidence_level,
        max_regressed_tasks=max_regressed_tasks,
        max_regressed_task_fraction=max_regressed_task_fraction,
        max_regressed_task_weight=max_regressed_task_weight,
        max_regressed_task_weight_fraction=max_regressed_task_weight_fraction,
        task_regression_margin=task_regression_margin,
    )
    if task_comparison is not None:
        result.update(task_comparison)
        return result

    paired_comparison = _compare_paired_runs(
        candidate_payload=candidate_payload,
        baseline_payload=baseline_payload,
        min_improvement=min_improvement,
        confidence_level=confidence_level,
    )
    if paired_comparison is not None:
        result.update(paired_comparison)
        return result

    if candidate_rate is None or baseline_rate is None:
        result["decision"] = "unavailable"
        result["passed"] = None
        result["reason"] = "Candidate or baseline did not expose a comparable success-rate signal."
        return result

    candidate_lower = (
        candidate_interval["lower"] if isinstance(candidate_interval, dict) else candidate_rate
    )
    candidate_upper = (
        candidate_interval["upper"] if isinstance(candidate_interval, dict) else candidate_rate
    )
    baseline_lower = (
        baseline_interval["lower"] if isinstance(baseline_interval, dict) else baseline_rate
    )
    baseline_upper = (
        baseline_interval["upper"] if isinstance(baseline_interval, dict) else baseline_rate
    )

    if candidate_lower >= baseline_upper + min_improvement:
        result["decision"] = "improved"
        result["passed"] = True
        result["reason"] = (
            f"The candidate lower bound {candidate_lower:.3f} exceeded the baseline upper bound "
            f"{baseline_upper:.3f} by at least {min_improvement:.3f}."
        )
        return result
    if candidate_upper < baseline_lower + min_improvement:
        result["decision"] = "regressed"
        result["passed"] = False
        result["reason"] = (
            f"The candidate upper bound {candidate_upper:.3f} did not clear the baseline lower bound "
            f"{baseline_lower:.3f} plus the required improvement margin {min_improvement:.3f}."
        )
        return result

    result["decision"] = "inconclusive"
    result["passed"] = None
    result["reason"] = (
        f"The candidate interval [{candidate_lower:.3f}, {candidate_upper:.3f}] did not separate "
        f"cleanly from the baseline interval [{baseline_lower:.3f}, {baseline_upper:.3f}] with the "
        f"required improvement margin {min_improvement:.3f}."
    )
    return result


def _evaluate_stability_gate(
    *,
    stage_policy: StagePolicy,
    validation_summary: dict[str, Any],
) -> dict[str, Any] | None:
    thresholds = _STABILITY_GATE_THRESHOLDS.get(stage_policy.stage)
    if thresholds is None:
        return None

    stability_summary = validation_summary.get("stability_summary")
    if not isinstance(stability_summary, dict):
        return None

    stability_score = stability_summary.get("stability_score")
    numeric_stability_score = (
        float(stability_score)
        if isinstance(stability_score, (int, float)) and not isinstance(stability_score, bool)
        else None
    )
    confidence_interval = validation_summary.get("success_rate_confidence_interval")
    confidence_interval_width = None
    if isinstance(confidence_interval, dict):
        lower = confidence_interval.get("lower")
        upper = confidence_interval.get("upper")
        if (
            isinstance(lower, (int, float))
            and not isinstance(lower, bool)
            and isinstance(upper, (int, float))
            and not isinstance(upper, bool)
        ):
            confidence_interval_width = float(upper) - float(lower)

    minimum_stability_score = float(thresholds["minimum_stability_score"])
    max_confidence_interval_width = float(thresholds["max_confidence_interval_width"])
    reasons: list[str] = []
    passed = True
    if (
        numeric_stability_score is not None
        and numeric_stability_score < minimum_stability_score
    ):
        passed = False
        reasons.append(
            f"stability_score {numeric_stability_score:.3f} was below the minimum "
            f"of {minimum_stability_score:.3f}"
        )
    if (
        confidence_interval_width is not None
        and confidence_interval_width > max_confidence_interval_width
    ):
        passed = False
        reasons.append(
            f"success-rate interval width {confidence_interval_width:.3f} exceeded the "
            f"maximum of {max_confidence_interval_width:.3f}"
        )

    return {
        "applies": True,
        "passed": passed,
        "flaky": bool(stability_summary.get("flaky")),
        "stability_score": numeric_stability_score,
        "minimum_stability_score": minimum_stability_score,
        "confidence_interval_width": confidence_interval_width,
        "max_confidence_interval_width": max_confidence_interval_width,
        "reason": "; ".join(reasons) if reasons else "Validation stability satisfied the promotion gate.",
    }


def _compare_task_results(
    *,
    candidate_payload: dict[str, Any],
    baseline_payload: dict[str, Any],
    min_improvement: float,
    confidence_level: float,
    max_regressed_tasks: int | None,
    max_regressed_task_fraction: float | None,
    max_regressed_task_weight: float | None,
    max_regressed_task_weight_fraction: float | None,
    task_regression_margin: float,
) -> dict[str, Any] | None:
    candidate_outcomes = _resolve_task_outcomes(candidate_payload)
    baseline_outcomes = _resolve_task_outcomes(baseline_payload)
    if candidate_outcomes is None or baseline_outcomes is None:
        return None

    matched_task_ids = sorted(set(candidate_outcomes) & set(baseline_outcomes))
    if not matched_task_ids:
        return None

    candidate_values = [candidate_outcomes[task_id]["score"] for task_id in matched_task_ids]
    baseline_values = [baseline_outcomes[task_id]["score"] for task_id in matched_task_ids]
    delta_interval = paired_mean_confidence_interval(
        candidate_values,
        baseline_values,
        confidence_level=confidence_level,
    )
    if delta_interval is None:
        return None

    mean_delta = sum(
        candidate - baseline
        for candidate, baseline in zip(candidate_values, baseline_values, strict=True)
    ) / len(candidate_values)
    lower, upper = delta_interval
    task_alignment_key = _resolve_task_alignment_key(candidate_payload, baseline_payload)
    result: dict[str, Any] = {
        "comparison_mode": "task_delta",
        "task_alignment_key": task_alignment_key,
        "matched_task_count": len(matched_task_ids),
        "matched_task_ids": matched_task_ids,
        "mean_delta": mean_delta,
        "delta_confidence_interval": {
            "lower": lower,
            "upper": upper,
            "confidence_level": confidence_level,
        },
        "max_regressed_tasks": max_regressed_tasks,
        "max_regressed_task_fraction": max_regressed_task_fraction,
        "max_regressed_task_weight": max_regressed_task_weight,
        "max_regressed_task_weight_fraction": max_regressed_task_weight_fraction,
        "task_regression_margin": task_regression_margin,
    }

    regressed_tasks: list[dict[str, Any]] = []
    improved_task_ids: list[str] = []
    for task_id in matched_task_ids:
        candidate_score = candidate_outcomes[task_id]["score"]
        baseline_score = baseline_outcomes[task_id]["score"]
        delta = candidate_score - baseline_score
        if candidate_score < baseline_score - task_regression_margin:
            regressed_task: dict[str, Any] = {
                "task_id": task_id,
                "candidate_score": candidate_score,
                "baseline_score": baseline_score,
                "delta": delta,
                "weight": candidate_outcomes[task_id]["weight"],
            }
            candidate_task_result = candidate_outcomes[task_id].get("task_result")
            baseline_task_result = baseline_outcomes[task_id].get("task_result")
            if isinstance(candidate_task_result, dict):
                regressed_task["candidate_task_result"] = candidate_task_result
            if isinstance(baseline_task_result, dict):
                regressed_task["baseline_task_result"] = baseline_task_result
            regressed_tasks.append(regressed_task)
        elif candidate_score > baseline_score + task_regression_margin:
            improved_task_ids.append(task_id)

    regressed_task_ids = [task["task_id"] for task in regressed_tasks]
    regressed_task_fraction = len(regressed_tasks) / len(matched_task_ids)
    matched_task_weight_total = sum(
        float(candidate_outcomes[task_id]["weight"])
        for task_id in matched_task_ids
    )
    regressed_task_weight_total = sum(float(task["weight"]) for task in regressed_tasks)
    regressed_task_weight_fraction = (
        regressed_task_weight_total / matched_task_weight_total
        if matched_task_weight_total > 0.0
        else 0.0
    )
    result["regressed_task_count"] = len(regressed_tasks)
    result["regressed_task_fraction"] = regressed_task_fraction
    result["regressed_task_ids"] = regressed_task_ids
    result["regressed_tasks"] = regressed_tasks
    result["improved_task_count"] = len(improved_task_ids)
    result["improved_task_ids"] = improved_task_ids
    result["matched_task_weight_total"] = matched_task_weight_total
    result["regressed_task_weight_total"] = regressed_task_weight_total
    result["regressed_task_weight_fraction"] = regressed_task_weight_fraction

    regression_reasons: list[str] = []
    if max_regressed_tasks is not None and len(regressed_tasks) > max_regressed_tasks:
        regression_reasons.append(
            f"{len(regressed_tasks)} matched tasks regressed, exceeding the limit of "
            f"{max_regressed_tasks}."
        )
    if (
        max_regressed_task_fraction is not None
        and regressed_task_fraction > max_regressed_task_fraction
    ):
        regression_reasons.append(
            f"The regressed task fraction {regressed_task_fraction:.3f} exceeded the "
            f"limit of {max_regressed_task_fraction:.3f}."
        )
    if (
        max_regressed_task_weight is not None
        and regressed_task_weight_total > max_regressed_task_weight
    ):
        regression_reasons.append(
            f"The regressed task weight total {regressed_task_weight_total:.3f} exceeded "
            f"the limit of {max_regressed_task_weight:.3f}."
        )
    if (
        max_regressed_task_weight_fraction is not None
        and regressed_task_weight_fraction > max_regressed_task_weight_fraction
    ):
        regression_reasons.append(
            f"The regressed task weight fraction {regressed_task_weight_fraction:.3f} "
            f"exceeded the limit of {max_regressed_task_weight_fraction:.3f}."
        )
    if regression_reasons:
        result["decision"] = "regressed"
        result["passed"] = False
        result["reason"] = " ".join(regression_reasons)
        return result

    if lower >= min_improvement:
        result["decision"] = "improved"
        result["passed"] = True
        result["reason"] = (
            f"The matched-task delta lower bound {lower:.3f} met the required "
            f"improvement margin of {min_improvement:.3f}."
        )
        return result
    if upper < min_improvement:
        result["decision"] = "regressed"
        result["passed"] = False
        result["reason"] = (
            f"The matched-task delta upper bound {upper:.3f} fell below the required "
            f"improvement margin of {min_improvement:.3f}."
        )
        return result

    result["decision"] = "inconclusive"
    result["passed"] = None
    result["reason"] = (
        f"The matched-task delta interval [{lower:.3f}, {upper:.3f}] straddled the "
        f"required improvement margin of {min_improvement:.3f}."
    )
    return result


def _apply_baseline_gate(
    *,
    result: dict[str, Any],
    payload: dict[str, Any],
    baseline_payload: dict[str, Any] | None,
    baseline_label: str | None,
    baseline_stage: str | None,
    min_improvement: float,
    max_regressed_tasks: int | None,
    max_regressed_task_fraction: float | None,
    max_regressed_task_weight: float | None,
    max_regressed_task_weight_fraction: float | None,
    task_regression_margin: float,
) -> dict[str, Any]:
    if baseline_payload is None:
        return result

    comparison = compare_against_baseline(
        candidate_payload=payload,
        baseline_payload=baseline_payload,
        baseline_label=baseline_label,
        baseline_stage=baseline_stage,
        min_improvement=min_improvement,
        confidence_level=(
            result.get("confidence_level")
            if isinstance(result.get("confidence_level"), float)
            else 0.85
        ),
        max_regressed_tasks=max_regressed_tasks,
        max_regressed_task_fraction=max_regressed_task_fraction,
        max_regressed_task_weight=max_regressed_task_weight,
        max_regressed_task_weight_fraction=max_regressed_task_weight_fraction,
        task_regression_margin=task_regression_margin,
    )
    result["baseline_comparison"] = comparison

    if result.get("decision") != "passed":
        return result

    comparison_decision = comparison.get("decision")
    if comparison_decision == "improved":
        return result
    if comparison_decision == "regressed":
        result["decision"] = "failed"
        result["passed"] = False
        result["reason"] = comparison["reason"]
        return result

    result["decision"] = "inconclusive"
    result["passed"] = None
    result["reason"] = comparison["reason"]
    return result


def _compare_paired_runs(
    *,
    candidate_payload: dict[str, Any],
    baseline_payload: dict[str, Any],
    min_improvement: float,
    confidence_level: float,
) -> dict[str, Any] | None:
    paired = _extract_paired_signals(candidate_payload, baseline_payload)
    if paired is None:
        return None

    candidate_values, baseline_values, alignment_key = paired
    delta_interval = paired_mean_confidence_interval(
        candidate_values,
        baseline_values,
        confidence_level=confidence_level,
    )
    if delta_interval is None:
        return None

    mean_delta = sum(
        candidate - baseline
        for candidate, baseline in zip(candidate_values, baseline_values, strict=True)
    ) / len(candidate_values)
    lower, upper = delta_interval
    result: dict[str, Any] = {
        "comparison_mode": "paired_delta",
        "paired_alignment_key": alignment_key,
        "paired_run_count": len(candidate_values),
        "mean_delta": mean_delta,
        "delta_confidence_interval": {
            "lower": lower,
            "upper": upper,
            "confidence_level": confidence_level,
        },
    }
    if lower >= min_improvement:
        result["decision"] = "improved"
        result["passed"] = True
        result["reason"] = (
            f"The paired delta lower bound {lower:.3f} met the required improvement "
            f"margin of {min_improvement:.3f}."
        )
        return result
    if upper < min_improvement:
        result["decision"] = "regressed"
        result["passed"] = False
        result["reason"] = (
            f"The paired delta upper bound {upper:.3f} fell below the required "
            f"improvement margin of {min_improvement:.3f}."
        )
        return result

    result["decision"] = "inconclusive"
    result["passed"] = None
    result["reason"] = (
        f"The paired delta interval [{lower:.3f}, {upper:.3f}] straddled the required "
        f"improvement margin of {min_improvement:.3f}."
    )
    return result


def _resolve_task_outcomes(payload: dict[str, Any]) -> dict[str, dict[str, Any]] | None:
    scores_by_task: dict[str, list[float]] = {}
    sample_results_by_task: dict[str, dict[str, Any]] = {}
    weights_by_task: dict[str, float] = {}
    task_identity_profile = _resolve_task_identity_profile(payload)
    _collect_task_outcomes(
        scores_by_task,
        sample_results_by_task,
        weights_by_task,
        payload.get("task_results"),
        task_identity_profile=task_identity_profile,
    )

    validation_runs = payload.get("validation_runs")
    if isinstance(validation_runs, list):
        for run in validation_runs:
            if not isinstance(run, dict):
                continue
            _collect_task_outcomes(
                scores_by_task,
                sample_results_by_task,
                weights_by_task,
                run.get("task_results"),
                task_identity_profile=task_identity_profile,
            )

    if scores_by_task:
        return {
            task_id: {
                "score": sum(scores) / len(scores),
                "weight": weights_by_task.get(task_id, 1.0),
                **(
                    {"task_result": sample_results_by_task[task_id]}
                    if task_id in sample_results_by_task
                    else {}
                ),
            }
            for task_id, scores in scores_by_task.items()
        }

    summary = payload.get("task_result_summary")
    if isinstance(summary, dict):
        raw_means = summary.get("task_mean_scores")
        if isinstance(raw_means, dict):
            normalized_means = _normalize_task_score_mapping(raw_means)
            if normalized_means:
                return {
                    task_id: {"score": score, "weight": 1.0}
                    for task_id, score in normalized_means.items()
                }
    return None


def _resolve_task_identity_profile(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw_profile = payload.get("task_identity_profile")
    if isinstance(raw_profile, dict):
        return raw_profile

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        nested_profile = metadata.get("task_identity_profile")
        if isinstance(nested_profile, dict):
            return nested_profile

    validation_runs = payload.get("validation_runs")
    if isinstance(validation_runs, list):
        for run in validation_runs:
            if not isinstance(run, dict):
                continue
            raw_profile = run.get("task_identity_profile")
            if isinstance(raw_profile, dict):
                return raw_profile
            metadata = run.get("metadata")
            if isinstance(metadata, dict):
                nested_profile = metadata.get("task_identity_profile")
                if isinstance(nested_profile, dict):
                    return nested_profile
    return None


def _resolve_task_alignment_key(
    candidate_payload: dict[str, Any],
    baseline_payload: dict[str, Any],
) -> str:
    candidate_profile = _resolve_task_identity_profile(candidate_payload)
    baseline_profile = _resolve_task_identity_profile(baseline_payload)
    candidate_key = _resolve_profile_match_key(candidate_profile)
    baseline_key = _resolve_profile_match_key(baseline_profile)
    if candidate_key == baseline_key:
        return candidate_key
    if candidate_key != "task_id":
        return candidate_key
    if baseline_key != "task_id":
        return baseline_key
    return "task_id"


def _resolve_profile_match_key(task_identity_profile: dict[str, Any] | None) -> str:
    if not isinstance(task_identity_profile, dict):
        return "task_id"
    match_key_field = task_identity_profile.get("match_key_field")
    if isinstance(match_key_field, str) and match_key_field:
        return match_key_field
    return "task_id"


def _resolve_task_match_key(
    task_result: dict[str, Any],
    *,
    task_identity_profile: dict[str, Any] | None,
) -> str | None:
    match_key_field = _resolve_profile_match_key(task_identity_profile)
    raw_match_key = task_result.get(match_key_field)
    if isinstance(raw_match_key, str) and raw_match_key:
        return raw_match_key
    raw_task_id = task_result.get("task_id")
    if isinstance(raw_task_id, str) and raw_task_id:
        return raw_task_id
    raw_fallback_id = task_result.get("id")
    if isinstance(raw_fallback_id, str) and raw_fallback_id:
        return raw_fallback_id
    return None


def _resolve_task_weight(
    task_result: dict[str, Any],
    *,
    task_identity_profile: dict[str, Any] | None,
) -> float:
    default_weight = 1.0
    if isinstance(task_identity_profile, dict):
        raw_default_weight = task_identity_profile.get("default_weight")
        if (
            isinstance(raw_default_weight, (int, float))
            and not isinstance(raw_default_weight, bool)
            and float(raw_default_weight) >= 0.0
        ):
            default_weight = float(raw_default_weight)

        weight_field = task_identity_profile.get("weight_field")
        if isinstance(weight_field, str) and weight_field:
            raw_weight = task_result.get(weight_field)
            if (
                isinstance(raw_weight, (int, float))
                and not isinstance(raw_weight, bool)
                and float(raw_weight) >= 0.0
            ):
                return float(raw_weight)

        tier_field = task_identity_profile.get("tier_field")
        tier_weights = task_identity_profile.get("tier_weights")
        if (
            isinstance(tier_field, str)
            and tier_field
            and isinstance(tier_weights, dict)
        ):
            raw_tier = task_result.get(tier_field)
            raw_weight = tier_weights.get(raw_tier)
            if (
                isinstance(raw_weight, (int, float))
                and not isinstance(raw_weight, bool)
                and float(raw_weight) >= 0.0
            ):
                return float(raw_weight)

    return default_weight


def _extract_paired_signals(
    candidate_payload: dict[str, Any],
    baseline_payload: dict[str, Any],
) -> tuple[list[float], list[float], str] | None:
    candidate_runs = candidate_payload.get("validation_runs")
    baseline_runs = baseline_payload.get("validation_runs")
    if not isinstance(candidate_runs, list) or not isinstance(baseline_runs, list):
        return None

    if not candidate_runs or not baseline_runs:
        return None

    candidate_by_seed = _index_runs_by_key(candidate_runs, "seed")
    baseline_by_seed = _index_runs_by_key(baseline_runs, "seed")
    if candidate_by_seed is not None and baseline_by_seed is not None:
        if set(candidate_by_seed) != set(baseline_by_seed):
            return None
        ordered_keys = sorted(candidate_by_seed)
        return _paired_values_from_keys(
            ordered_keys,
            candidate_by_seed,
            baseline_by_seed,
            alignment_key="seed",
        )

    candidate_by_index = _index_runs_by_key(candidate_runs, "validation_index")
    baseline_by_index = _index_runs_by_key(baseline_runs, "validation_index")
    if candidate_by_index is not None and baseline_by_index is not None:
        if set(candidate_by_index) != set(baseline_by_index):
            return None
        ordered_keys = sorted(candidate_by_index)
        return _paired_values_from_keys(
            ordered_keys,
            candidate_by_index,
            baseline_by_index,
            alignment_key="validation_index",
        )

    return None


def _index_runs_by_key(
    runs: list[Any],
    key: str,
) -> dict[Any, dict[str, Any]] | None:
    indexed: dict[Any, dict[str, Any]] = {}
    for run in runs:
        if not isinstance(run, dict):
            return None
        raw_key = run.get(key)
        if raw_key is None:
            return None
        if raw_key in indexed:
            return None
        indexed[raw_key] = run
    return indexed


def _paired_values_from_keys(
    keys: list[Any],
    candidate_runs: dict[Any, dict[str, Any]],
    baseline_runs: dict[Any, dict[str, Any]],
    *,
    alignment_key: str,
) -> tuple[list[float], list[float], str] | None:
    candidate_values: list[float] = []
    baseline_values: list[float] = []
    for key in keys:
        candidate_value = _resolve_run_signal(candidate_runs[key])
        baseline_value = _resolve_run_signal(baseline_runs[key])
        if candidate_value is None or baseline_value is None:
            return None
        candidate_values.append(candidate_value)
        baseline_values.append(baseline_value)
    return candidate_values, baseline_values, alignment_key


def _collect_task_outcomes(
    scores_by_task: dict[str, list[float]],
    sample_results_by_task: dict[str, dict[str, Any]],
    weights_by_task: dict[str, float],
    task_results: Any,
    *,
    task_identity_profile: dict[str, Any] | None,
) -> None:
    if not isinstance(task_results, list):
        return
    for task_result in task_results:
        if not isinstance(task_result, dict):
            continue
        task_id = _resolve_task_match_key(
            task_result,
            task_identity_profile=task_identity_profile,
        )
        score = task_result.get("score")
        if (
            not isinstance(task_id, str)
            or not task_id
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
        ):
            continue
        scores_by_task.setdefault(task_id, []).append(float(score))
        if task_id not in sample_results_by_task:
            sample_results_by_task[task_id] = dict(task_result)
        if task_id not in weights_by_task:
            weights_by_task[task_id] = _resolve_task_weight(
                task_result,
                task_identity_profile=task_identity_profile,
            )


def _normalize_task_score_mapping(raw_means: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for task_id, score in raw_means.items():
        if (
            not isinstance(task_id, str)
            or not task_id
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
        ):
            continue
        normalized[task_id] = float(score)
    return normalized


def _resolve_run_signal(run: dict[str, Any]) -> float | None:
    metrics = run.get("metrics")
    if isinstance(metrics, dict):
        raw_pass_rate = metrics.get("pass_rate")
        if isinstance(raw_pass_rate, (int, float)) and not isinstance(raw_pass_rate, bool):
            return float(raw_pass_rate)
    success = run.get("success")
    if isinstance(success, bool):
        return 1.0 if success else 0.0
    return None


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _resolve_run_count(payload: dict[str, Any]) -> int:
    raw_run_count = payload.get("validation_run_count")
    if isinstance(raw_run_count, int) and raw_run_count > 0:
        return raw_run_count
    validation_summary = payload.get("validation_summary")
    if isinstance(validation_summary, dict):
        run_count = validation_summary.get("run_count")
        if isinstance(run_count, int) and run_count > 0:
            return run_count
    return 1


def _resolve_observed_success_rate(
    payload: dict[str, Any],
) -> tuple[float | None, str | None, dict[str, Any] | None]:
    metrics = payload.get("metrics")
    validation_summary = payload.get("validation_summary")
    if isinstance(metrics, dict):
        raw_pass_rate = metrics.get("pass_rate")
        if isinstance(raw_pass_rate, (int, float)) and not isinstance(raw_pass_rate, bool):
            interval = None
            if isinstance(validation_summary, dict):
                metric_intervals = validation_summary.get("metrics_confidence_intervals")
                if isinstance(metric_intervals, dict):
                    pass_rate_interval = metric_intervals.get("pass_rate")
                    if isinstance(pass_rate_interval, dict):
                        interval = pass_rate_interval
            return float(raw_pass_rate), "metrics.pass_rate", interval

    if isinstance(validation_summary, dict):
        success_count = validation_summary.get("success_count")
        run_count = validation_summary.get("run_count")
        if isinstance(success_count, int) and isinstance(run_count, int) and run_count > 0:
            interval = validation_summary.get("success_rate_confidence_interval")
            return (
                success_count / run_count,
                "validation_summary.success_count",
                interval if isinstance(interval, dict) else None,
            )

    success = payload.get("success")
    if isinstance(success, bool):
        return (1.0 if success else 0.0), "payload.success", None
    return None, None, None
