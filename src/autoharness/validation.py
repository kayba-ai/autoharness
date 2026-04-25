"""Repeated validation helpers for autoharness benchmark runs."""

from __future__ import annotations

import copy
from typing import Any

from .adapters.base import BenchmarkAdapter, JsonDict
from .stats import mean_confidence_interval, wilson_interval


_FAILURE_CLASS_PRIORITY = {
    "benchmark_signal_error": 70,
    "benchmark_process_error": 65,
    "benchmark_adapter_validation_error": 60,
    "benchmark_artifact_parse_error": 55,
    "benchmark_metrics_parse_error": 52,
    "benchmark_task_results_parse_error": 51,
    "benchmark_timeout": 50,
    "preflight_failed": 45,
    "benchmark_command_failed": 40,
    "benchmark_failed": 30,
}


def run_validation(
    *,
    adapter: BenchmarkAdapter,
    config: JsonDict,
    dry_run: bool,
    repeat_count: int = 1,
    seed_field: str | None = None,
    seed_start: int | None = None,
    seed_stride: int = 1,
    confidence_level: float = 0.85,
) -> JsonDict:
    """Run or plan one benchmark multiple times and aggregate the result."""
    repeated_configs = build_repeated_configs(
        config=config,
        repeat_count=repeat_count,
        seed_field=seed_field,
        seed_start=seed_start,
        seed_stride=seed_stride,
    )

    runs: list[JsonDict] = []
    for index, run_config in enumerate(repeated_configs, start=1):
        if dry_run:
            run_payload = adapter.build_invocation(run_config).to_dict()
            run_payload["adapter_id"] = adapter.adapter_id
        else:
            run_payload = adapter.run(run_config).to_dict()
        run_payload["validation_index"] = index
        if seed_field is not None and seed_field in run_config:
            run_payload["seed"] = run_config[seed_field]
        runs.append(run_payload)

    if repeat_count == 1:
        payload = dict(runs[0])
        payload["validation_run_count"] = 1
        failure_class = classify_validation_run(payload)
        if failure_class is not None:
            payload["failure_class"] = failure_class
        task_result_summary = _aggregate_task_results(
            runs,
            confidence_level=confidence_level,
        )
        if task_result_summary:
            payload["task_result_summary"] = task_result_summary
        parsed_artifact_sources = _aggregate_parsed_artifact_sources(runs)
        if parsed_artifact_sources:
            payload["parsed_artifact_sources"] = parsed_artifact_sources
        if seed_field is not None:
            payload["validation_seed_field"] = seed_field
            if "seed" in payload:
                payload["validation_seeds"] = [payload["seed"]]
        return payload

    first = runs[0]
    summary = aggregate_validation_runs(
        runs,
        dry_run=dry_run,
        seed_field=seed_field,
        confidence_level=confidence_level,
    )
    payload: JsonDict = {
        "format_version": "autoharness.validation_result.v1",
        "adapter_id": str(first.get("adapter_id", adapter.adapter_id)),
        "benchmark_name": str(first.get("benchmark_name", adapter.adapter_id)),
        "command": list(first.get("command", [])),
        "workdir": first.get("workdir"),
        "dry_run": dry_run,
        "success": summary.get("all_success"),
        "validation_run_count": repeat_count,
        "validation_runs": runs,
        "validation_summary": summary,
    }
    task_identity_profile = first.get("task_identity_profile")
    if isinstance(task_identity_profile, dict) and task_identity_profile:
        payload["task_identity_profile"] = dict(task_identity_profile)
    parsed_artifact_sources = summary.get("parsed_artifact_sources")
    if isinstance(parsed_artifact_sources, dict):
        payload["parsed_artifact_sources"] = parsed_artifact_sources
    if seed_field is not None:
        payload["validation_seed_field"] = seed_field
        payload["validation_seeds"] = summary.get("seeds", [])
    metrics_mean = summary.get("metrics_mean")
    if isinstance(metrics_mean, dict):
        payload["metrics"] = metrics_mean
    task_result_summary = summary.get("task_result_summary")
    if isinstance(task_result_summary, dict):
        payload["task_result_summary"] = task_result_summary
    primary_failure_class = summary.get("primary_failure_class")
    if isinstance(primary_failure_class, str) and primary_failure_class:
        payload["failure_class"] = primary_failure_class
    return payload


def build_repeated_configs(
    *,
    config: JsonDict,
    repeat_count: int,
    seed_field: str | None = None,
    seed_start: int | None = None,
    seed_stride: int = 1,
) -> list[JsonDict]:
    """Return one config per repeated validation run."""
    if repeat_count < 1:
        raise ValueError("`repeat_count` must be at least 1.")
    if seed_stride < 1:
        raise ValueError("`seed_stride` must be at least 1.")

    base_seed: int | None = None
    if seed_field is not None:
        if seed_start is not None:
            base_seed = seed_start
        else:
            raw_seed = config.get(seed_field)
            if raw_seed is None:
                base_seed = 0
            elif isinstance(raw_seed, int):
                base_seed = raw_seed
            else:
                raise ValueError(
                    f"`{seed_field}` must be an integer when used as a repeat seed field."
                )

    repeated: list[JsonDict] = []
    for index in range(repeat_count):
        run_config = copy.deepcopy(config)
        if seed_field is not None and base_seed is not None:
            run_config[seed_field] = base_seed + (index * seed_stride)
        repeated.append(run_config)
    return repeated


def aggregate_validation_runs(
    runs: list[JsonDict],
    *,
    dry_run: bool,
    seed_field: str | None = None,
    confidence_level: float = 0.85,
) -> JsonDict:
    """Aggregate repeated validation runs into a compact summary."""
    summary: JsonDict = {
        "run_count": len(runs),
    }
    if seed_field is not None:
        summary["seed_field"] = seed_field
        summary["seeds"] = [run.get("seed") for run in runs if "seed" in run]

    if dry_run:
        summary["planned_run_count"] = len(runs)
        return summary

    success_count = sum(1 for run in runs if run.get("success") is True)
    failure_count = sum(1 for run in runs if run.get("success") is False)
    durations = [
        float(run["duration_seconds"])
        for run in runs
        if isinstance(run.get("duration_seconds"), (int, float))
    ]
    (
        metrics_mean,
        metrics_counts,
        metrics_confidence_intervals,
        varying_metric_keys,
    ) = _aggregate_numeric_metrics(runs, confidence_level=confidence_level)
    success_rate = success_count / len(runs)
    success_lower, success_upper = wilson_interval(
        successes=success_count,
        trials=len(runs),
        confidence_level=confidence_level,
    )

    summary.update(
        {
            "success_count": success_count,
            "failure_count": failure_count,
            "all_success": success_count == len(runs),
            "success_rate": success_rate,
            "success_rate_confidence_interval": {
                "lower": success_lower,
                "upper": success_upper,
                "confidence_level": confidence_level,
            },
        }
    )
    failure_class_counts = aggregate_validation_failure_classes(runs)
    if failure_class_counts:
        summary["failure_class_counts"] = failure_class_counts
        summary["failure_classes"] = sorted(failure_class_counts)
        summary["primary_failure_class"] = select_primary_failure_class(
            failure_class_counts
        )
    if durations:
        summary["mean_duration_seconds"] = sum(durations) / len(durations)
        summary["max_duration_seconds"] = max(durations)
    if metrics_mean:
        summary["metrics_mean"] = metrics_mean
        summary["metrics_observation_counts"] = metrics_counts
        summary["metrics_confidence_intervals"] = metrics_confidence_intervals
    task_result_summary = _aggregate_task_results(
        runs,
        confidence_level=confidence_level,
    )
    stability_summary: JsonDict = {
        "mixed_success": 0 < success_count < len(runs),
        "varying_metric_keys": varying_metric_keys,
        "varying_metric_count": len(varying_metric_keys),
        "failure_classes": (
            sorted(failure_class_counts)
            if failure_class_counts
            else []
        ),
        "failure_class_count": len(failure_class_counts),
        "mixed_failure_classes": len(failure_class_counts) > 1,
        "varying_task_ids": (
            list(task_result_summary.get("varying_task_ids", []))
            if isinstance(task_result_summary, dict)
            else []
        ),
        "varying_task_count": (
            int(task_result_summary.get("varying_task_count", 0))
            if isinstance(task_result_summary, dict)
            else 0
        ),
    }
    stability_summary["flaky"] = bool(
        stability_summary["mixed_success"]
        or stability_summary["varying_metric_count"]
        or stability_summary["varying_task_count"]
    )
    stability_summary["stability_score"] = stability_score_from_validation_summary(
        {
            **summary,
            "metrics_mean": metrics_mean,
            "task_result_summary": task_result_summary,
            "stability_summary": stability_summary,
        }
    )
    if task_result_summary:
        summary["task_result_summary"] = task_result_summary
    parsed_artifact_sources = _aggregate_parsed_artifact_sources(runs)
    if parsed_artifact_sources:
        summary["parsed_artifact_sources"] = parsed_artifact_sources
    summary["stability_summary"] = stability_summary
    return summary


def stability_score_from_validation_summary(
    validation_summary: JsonDict | None,
) -> float:
    if not isinstance(validation_summary, dict):
        return 1.0
    stability_summary = validation_summary.get("stability_summary")
    if not isinstance(stability_summary, dict):
        return 1.0

    success_rate = validation_summary.get("success_rate")
    success_consistency = (
        float(success_rate)
        if isinstance(success_rate, (int, float)) and not isinstance(success_rate, bool)
        else 1.0
    )
    metrics_mean = validation_summary.get("metrics_mean")
    metric_total = len(metrics_mean) if isinstance(metrics_mean, dict) else 0
    task_result_summary = validation_summary.get("task_result_summary")
    task_total = (
        int(task_result_summary.get("task_count", 0))
        if isinstance(task_result_summary, dict)
        else 0
    )
    varying_metric_count = int(stability_summary.get("varying_metric_count", 0) or 0)
    varying_task_count = int(stability_summary.get("varying_task_count", 0) or 0)

    metric_penalty = (
        float(varying_metric_count) / float(metric_total)
        if metric_total > 0
        else 0.0
    )
    task_penalty = (
        float(varying_task_count) / float(task_total)
        if task_total > 0
        else 0.0
    )
    score = success_consistency - (0.25 * metric_penalty) - (0.25 * task_penalty)
    return max(0.0, min(1.0, score))


def classify_validation_run(run_payload: JsonDict | dict[str, object] | None) -> str | None:
    if not isinstance(run_payload, dict):
        return None
    if run_payload.get("dry_run") is True:
        return None
    if run_payload.get("preflight_failed") is True:
        return "preflight_failed"
    if run_payload.get("adapter_validation_error") is True:
        return "benchmark_adapter_validation_error"
    if run_payload.get("timed_out") is True:
        return "benchmark_timeout"
    process_error = run_payload.get("process_error")
    if isinstance(process_error, str) and process_error:
        return "benchmark_process_error"
    signal_number = run_payload.get("signal_number")
    exit_code = run_payload.get("exit_code")
    if (
        isinstance(signal_number, int)
        and signal_number > 0
    ) or (isinstance(exit_code, int) and exit_code < 0):
        return "benchmark_signal_error"

    metadata = run_payload.get("metadata")
    metadata_payload = metadata if isinstance(metadata, dict) else {}
    metrics_parse_failed = isinstance(metadata_payload.get("metrics_parse_error"), str)
    task_results_parse_failed = isinstance(
        metadata_payload.get("task_results_parse_error"),
        str,
    )
    if metrics_parse_failed and task_results_parse_failed:
        return "benchmark_artifact_parse_error"
    if metrics_parse_failed:
        return "benchmark_metrics_parse_error"
    if task_results_parse_failed:
        return "benchmark_task_results_parse_error"

    success = run_payload.get("success")
    if success is False:
        return "benchmark_command_failed"
    return None


def aggregate_validation_failure_classes(
    runs: list[JsonDict],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in runs:
        failure_class = classify_validation_run(run)
        if failure_class is None:
            continue
        counts[failure_class] = counts.get(failure_class, 0) + 1
    return counts


def select_primary_failure_class(
    failure_class_counts: dict[str, int] | None,
) -> str | None:
    if not isinstance(failure_class_counts, dict) or not failure_class_counts:
        return None
    ranked = sorted(
        (
            (str(failure_class), int(count))
            for failure_class, count in failure_class_counts.items()
            if isinstance(failure_class, str)
        ),
        key=lambda item: (
            -item[1],
            -_FAILURE_CLASS_PRIORITY.get(item[0], 0),
            item[0],
        ),
    )
    return ranked[0][0] if ranked else None


def classify_validation_payload(payload: dict[str, object] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("dry_run") is True:
        return None

    validation_summary = payload.get("validation_summary")
    if isinstance(validation_summary, dict):
        primary_failure_class = validation_summary.get("primary_failure_class")
        if isinstance(primary_failure_class, str) and primary_failure_class:
            return primary_failure_class
        failure_class_counts = validation_summary.get("failure_class_counts")
        if isinstance(failure_class_counts, dict):
            selected = select_primary_failure_class(
                {
                    str(key): int(value)
                    for key, value in failure_class_counts.items()
                    if isinstance(value, int)
                }
            )
            if selected is not None:
                return selected

    validation_runs = payload.get("validation_runs")
    if isinstance(validation_runs, list):
        selected = select_primary_failure_class(
            aggregate_validation_failure_classes(
                [run for run in validation_runs if isinstance(run, dict)]
            )
        )
        if selected is not None:
            return selected

    return classify_validation_run(payload)


def _aggregate_numeric_metrics(
    runs: list[JsonDict],
    *,
    confidence_level: float,
) -> tuple[JsonDict, JsonDict, JsonDict, list[str]]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    values_by_key: dict[str, list[float]] = {}

    for run in runs:
        metrics = run.get("metrics")
        if not isinstance(metrics, dict):
            continue
        for key, value in metrics.items():
            if isinstance(value, bool):
                numeric = 1.0 if value else 0.0
            elif isinstance(value, (int, float)):
                numeric = float(value)
            else:
                continue
            totals[key] = totals.get(key, 0.0) + numeric
            counts[key] = counts.get(key, 0) + 1
            values_by_key.setdefault(key, []).append(numeric)

    means = {
        key: totals[key] / counts[key]
        for key in totals
        if counts.get(key, 0) > 0
    }
    confidence_intervals: JsonDict = {}
    for key, values in values_by_key.items():
        interval = mean_confidence_interval(values, confidence_level=confidence_level)
        if interval is None:
            continue
        confidence_intervals[key] = {
            "lower": interval[0],
            "upper": interval[1],
            "confidence_level": confidence_level,
            "count": len(values),
        }
    varying_metric_keys = sorted(
        key
        for key, values in values_by_key.items()
        if len({round(value, 12) for value in values}) > 1
    )
    return means, counts, confidence_intervals, varying_metric_keys


def _aggregate_task_results(
    runs: list[JsonDict],
    *,
    confidence_level: float,
) -> JsonDict:
    scores_by_task: dict[str, list[float]] = {}

    for run in runs:
        task_results = run.get("task_results")
        if not isinstance(task_results, list):
            continue
        for task_result in task_results:
            if not isinstance(task_result, dict):
                continue
            task_id = task_result.get("task_id")
            score = task_result.get("score")
            if (
                not isinstance(task_id, str)
                or not task_id
                or not isinstance(score, (int, float))
                or isinstance(score, bool)
            ):
                continue
            scores_by_task.setdefault(task_id, []).append(float(score))

    if not scores_by_task:
        return {}

    task_mean_scores = {
        task_id: sum(scores) / len(scores)
        for task_id, scores in scores_by_task.items()
    }
    task_observation_counts = {
        task_id: len(scores)
        for task_id, scores in scores_by_task.items()
    }
    task_confidence_intervals: JsonDict = {}
    for task_id, scores in scores_by_task.items():
        interval = mean_confidence_interval(scores, confidence_level=confidence_level)
        if interval is None:
            continue
        task_confidence_intervals[task_id] = {
            "lower": interval[0],
            "upper": interval[1],
            "confidence_level": confidence_level,
            "count": len(scores),
        }

    return {
        "task_count": len(scores_by_task),
        "task_ids": sorted(scores_by_task),
        "task_mean_scores": task_mean_scores,
        "task_observation_counts": task_observation_counts,
        "task_confidence_intervals": task_confidence_intervals,
        "varying_task_ids": sorted(
            task_id
            for task_id, scores in scores_by_task.items()
            if len({round(score, 12) for score in scores}) > 1
        ),
        "varying_task_count": sum(
            1
            for scores in scores_by_task.values()
            if len({round(score, 12) for score in scores}) > 1
        ),
    }


def _aggregate_parsed_artifact_sources(
    runs: list[JsonDict],
) -> JsonDict:
    aggregated: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}

    for run in runs:
        metadata = run.get("metadata")
        if not isinstance(metadata, dict):
            continue
        parsed_sources = metadata.get("parsed_artifact_sources")
        if not isinstance(parsed_sources, dict):
            continue
        validation_index = run.get("validation_index")
        seed = run.get("seed")

        for category, entries in parsed_sources.items():
            if not isinstance(category, str) or not isinstance(entries, list):
                continue
            category_bucket = aggregated.setdefault(category, {})
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                origin = entry.get("origin")
                path = entry.get("path")
                if (
                    not isinstance(origin, str)
                    or not origin
                    or not isinstance(path, str)
                    or not path
                ):
                    continue
                dedupe_key = (origin, path)
                bucket = category_bucket.setdefault(
                    dedupe_key,
                    {
                        "origin": origin,
                        "path": path,
                        "validation_indices": [],
                        "seeds": [],
                    },
                )
                if isinstance(validation_index, int) and validation_index not in bucket["validation_indices"]:
                    bucket["validation_indices"].append(validation_index)
                if seed is not None and seed not in bucket["seeds"]:
                    bucket["seeds"].append(seed)

    rendered: JsonDict = {}
    for category, entries_by_key in aggregated.items():
        rendered_entries: list[JsonDict] = []
        for entry in sorted(
            entries_by_key.values(),
            key=lambda item: (str(item["origin"]), str(item["path"])),
        ):
            rendered_entry: JsonDict = {
                "origin": entry["origin"],
                "path": entry["path"],
            }
            if entry["validation_indices"]:
                rendered_entry["validation_indices"] = sorted(entry["validation_indices"])
            if entry["seeds"]:
                rendered_entry["seeds"] = list(entry["seeds"])
            rendered_entries.append(rendered_entry)
        if rendered_entries:
            rendered[category] = rendered_entries
    return rendered
