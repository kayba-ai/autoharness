"""Simple search-strategy helpers for campaign candidate selection."""

from __future__ import annotations

from typing import Any

from .plugins import plugin_search_strategies


_STAGE_ORDER = ("screening", "validation", "holdout", "transfer")
_GREEDY_STRATEGIES = {"greedy_failure_focus", "regression_first"}
_ROTATING_STRATEGIES = {
    "round_robin_interventions",
    "alternate_failure_regression",
}
_BEAM_STRATEGIES = {
    "beam_interventions",
    "beam_scored",
}
_SCORED_STRATEGIES = {
    "beam_scored",
    "diversity_first",
    "stability_weighted",
    "explore_then_exploit",
}
_FAILURE_CLASS_SEVERITY = {
    "stage_gate_failed": 1,
    "benchmark_failed": 1,
    "benchmark_regression": 2,
    "benchmark_inconclusive": 2,
    "benchmark_metrics_parse_error": 4,
    "benchmark_task_results_parse_error": 4,
    "benchmark_artifact_parse_error": 4,
    "benchmark_timeout": 4,
    "benchmark_command_failed": 4,
    "benchmark_process_error": 5,
    "benchmark_signal_error": 5,
    "benchmark_adapter_validation_error": 5,
    "preflight_failed": 4,
    "execution_error": 4,
    "generation_error": 4,
    "generation_provider_error": 5,
    "generation_provider_transport_error": 5,
    "generation_provider_rate_limit_error": 5,
    "generation_timeout": 5,
    "generation_process_error": 6,
    "generation_provider_auth_error": 7,
}
_HARD_FAILURE_SEVERITY = 4
_BUILTIN_STRATEGY_CATALOG = {
    "sequential_manual": {
        "label": "Sequential Manual",
        "inherits": None,
    },
    "greedy_failure_focus": {
        "label": "Greedy Failure Focus",
        "inherits": None,
    },
    "round_robin_interventions": {
        "label": "Round Robin Interventions",
        "inherits": None,
    },
    "regression_first": {
        "label": "Regression First",
        "inherits": None,
    },
    "alternate_failure_regression": {
        "label": "Alternate Failure Regression",
        "inherits": None,
    },
    "beam_interventions": {
        "label": "Beam Interventions",
        "inherits": None,
    },
    "beam_scored": {
        "label": "Beam Scored",
        "inherits": None,
    },
    "diversity_first": {
        "label": "Diversity First",
        "inherits": None,
    },
    "stability_weighted": {
        "label": "Stability Weighted",
        "inherits": None,
    },
    "explore_then_exploit": {
        "label": "Explore Then Exploit",
        "inherits": None,
    },
}


def search_strategy_catalog() -> dict[str, dict[str, object]]:
    catalog = {
        strategy_id: dict(entry)
        for strategy_id, entry in _BUILTIN_STRATEGY_CATALOG.items()
    }
    for strategy_id, entry in plugin_search_strategies().items():
        catalog[strategy_id] = dict(entry)
    return catalog


def available_search_strategies() -> tuple[str, ...]:
    return tuple(sorted(search_strategy_catalog()))


def _plugin_strategy_entry(strategy_id: str) -> dict[str, object]:
    entry = plugin_search_strategies().get(strategy_id, {})
    return dict(entry) if isinstance(entry, dict) else {}


def _canonical_strategy_id(strategy_id: str, *, _seen: set[str] | None = None) -> str:
    if strategy_id in _BUILTIN_STRATEGY_CATALOG:
        return strategy_id
    spec = search_strategy_catalog().get(strategy_id, {})
    hook = spec.get("hook")
    if isinstance(hook, str) and hook.strip():
        return _canonical_strategy_id(hook.strip(), _seen=_seen)
    inherited = spec.get("inherits")
    if not isinstance(inherited, str) or not inherited.strip():
        return strategy_id
    seen = set(_seen or set())
    if strategy_id in seen:
        return strategy_id
    seen.add(strategy_id)
    return _canonical_strategy_id(inherited.strip(), _seen=seen)


def _summary_task_keys(summary: dict[str, Any] | None) -> tuple[str, ...]:
    if not isinstance(summary, dict):
        return ()
    task_keys = summary.get("task_keys")
    if not isinstance(task_keys, list):
        return ()
    return tuple(str(entry) for entry in task_keys if isinstance(entry, str) and entry)


def _request_task_count(candidate_snapshot: dict[str, Any], key: str) -> int:
    request = candidate_snapshot.get("generation_request")
    if not isinstance(request, dict):
        return 0
    value = request.get(key)
    if not isinstance(value, list):
        return 0
    return sum(1 for entry in value if isinstance(entry, str) and entry)


def resolve_intervention_class(
    *,
    strategy_id: str,
    intervention_classes: tuple[str, ...],
    candidate_index: int,
) -> str | None:
    plugin_entry = _plugin_strategy_entry(strategy_id)
    plugin_hook = plugin_entry.get("resolve_intervention_class")
    if callable(plugin_hook):
        resolved = plugin_hook(
            strategy_id=strategy_id,
            intervention_classes=intervention_classes,
            candidate_index=candidate_index,
        )
        return str(resolved) if isinstance(resolved, str) and resolved else None
    strategy_id = _canonical_strategy_id(strategy_id)
    if not intervention_classes:
        return None
    if strategy_id in {"round_robin_interventions", "beam_interventions"}:
        return intervention_classes[candidate_index % len(intervention_classes)]
    return intervention_classes[0]


def resolve_focus_task_ids(
    *,
    strategy_id: str,
    candidate_index: int,
    latest_failure_summary: dict[str, Any] | None,
    latest_regression_summary: dict[str, Any] | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    plugin_entry = _plugin_strategy_entry(strategy_id)
    plugin_hook = plugin_entry.get("resolve_focus_task_ids")
    if callable(plugin_hook):
        rendered = plugin_hook(
            strategy_id=strategy_id,
            candidate_index=candidate_index,
            latest_failure_summary=latest_failure_summary,
            latest_regression_summary=latest_regression_summary,
        )
        if (
            isinstance(rendered, tuple)
            and len(rendered) == 2
            and all(isinstance(item, tuple) for item in rendered)
        ):
            return (
                tuple(str(value) for value in rendered[0] if isinstance(value, str)),
                tuple(str(value) for value in rendered[1] if isinstance(value, str)),
            )
    strategy_id = _canonical_strategy_id(strategy_id)
    failure_task_ids = _summary_task_keys(latest_failure_summary)
    regressed_task_ids = _summary_task_keys(latest_regression_summary)
    if not failure_task_ids and not regressed_task_ids:
        return (), ()
    if strategy_id == "regression_first":
        if regressed_task_ids:
            return (), (regressed_task_ids[0],)
        return (failure_task_ids[0],), ()
    if strategy_id == "alternate_failure_regression":
        if failure_task_ids and regressed_task_ids:
            if candidate_index % 2 == 0:
                focus_index = (candidate_index // 2) % len(failure_task_ids)
                return (failure_task_ids[focus_index],), ()
            focus_index = (candidate_index // 2) % len(regressed_task_ids)
            return (), (regressed_task_ids[focus_index],)
        if failure_task_ids:
            focus_index = candidate_index % len(failure_task_ids)
            return (failure_task_ids[focus_index],), ()
        focus_index = candidate_index % len(regressed_task_ids)
        return (), (regressed_task_ids[focus_index],)
    if strategy_id == "round_robin_interventions":
        if failure_task_ids:
            focus_index = candidate_index % len(failure_task_ids)
            return (failure_task_ids[focus_index],), ()
        focus_index = candidate_index % len(regressed_task_ids)
        return (), (regressed_task_ids[focus_index],)
    if strategy_id == "beam_interventions":
        if failure_task_ids:
            focus_index = candidate_index % len(failure_task_ids)
            return (failure_task_ids[focus_index],), regressed_task_ids[:1]
        focus_index = candidate_index % len(regressed_task_ids)
        return (), (regressed_task_ids[focus_index],)
    if failure_task_ids:
        return (failure_task_ids[0],), regressed_task_ids[:1]
    return (), regressed_task_ids[:1]


def strategy_prefers_regressions(strategy_id: str) -> bool:
    strategy_id = _canonical_strategy_id(strategy_id)
    return strategy_id == "regression_first"


def strategy_rotates_focus(strategy_id: str) -> bool:
    strategy_id = _canonical_strategy_id(strategy_id)
    return strategy_id in _ROTATING_STRATEGIES


def strategy_uses_beam(strategy_id: str) -> bool:
    strategy_id = _canonical_strategy_id(strategy_id)
    return strategy_id in _BEAM_STRATEGIES


def strategy_uses_scoring(strategy_id: str) -> bool:
    strategy_id = _canonical_strategy_id(strategy_id)
    return strategy_id in _SCORED_STRATEGIES


def resolve_beam_group_start(*, candidate_index: int, beam_width: int | None) -> int:
    if beam_width is None or beam_width < 2:
        return candidate_index
    return candidate_index - (candidate_index % beam_width)


def summarize_beam_group_outcomes(
    candidate_snapshots: list[dict[str, Any]],
) -> dict[int, dict[str, int]]:
    group_outcomes: dict[int, dict[str, int]] = {}
    for snapshot in candidate_snapshots:
        request = snapshot.get("generation_request")
        if not isinstance(request, dict):
            continue
        group_index = request.get("beam_group_index")
        if not isinstance(group_index, int):
            continue
        group = group_outcomes.setdefault(
            group_index,
            {
                "attempts": 0,
                "soft_failures": 0,
                "hard_failures": 0,
                "inconclusive": 0,
                "successes": 0,
            },
        )
        status = snapshot.get("status")
        if status in {"pending", "pruned"}:
            continue
        group["attempts"] += 1
        if status in {"success", "dry_run"}:
            group["successes"] += 1
            continue
        if status == "inconclusive":
            group["inconclusive"] += 1
            continue
        failure_class = snapshot.get("failure_class")
        severity = _FAILURE_CLASS_SEVERITY.get(
            str(failure_class) if failure_class is not None else "",
            _HARD_FAILURE_SEVERITY,
        )
        if severity >= _HARD_FAILURE_SEVERITY:
            group["hard_failures"] += 1
        else:
            group["soft_failures"] += 1
    return group_outcomes


def rank_beam_candidate(
    *,
    strategy_id: str,
    candidate_snapshot: dict[str, Any],
    group_outcomes: dict[int, dict[str, int]],
    attempted_intervention_classes: set[str],
    branch_score: float | None = None,
) -> tuple[int, int, int, int, int, int, int, int, int]:
    plugin_entry = _plugin_strategy_entry(strategy_id)
    plugin_hook = plugin_entry.get("rank_beam_candidate")
    if callable(plugin_hook):
        rendered = plugin_hook(
            strategy_id=strategy_id,
            candidate_snapshot=candidate_snapshot,
            group_outcomes=group_outcomes,
            attempted_intervention_classes=attempted_intervention_classes,
            branch_score=branch_score,
        )
        if isinstance(rendered, tuple):
            return tuple(int(value) for value in rendered)  # type: ignore[return-value]
    strategy_id = _canonical_strategy_id(strategy_id)
    request = candidate_snapshot.get("generation_request")
    if not isinstance(request, dict):
        request = {}
    group_index = request.get("beam_group_index")
    group = (
        group_outcomes.get(group_index)
        if isinstance(group_index, int)
        else None
    ) or {
        "attempts": 0,
        "soft_failures": 0,
        "hard_failures": 0,
        "inconclusive": 0,
        "successes": 0,
    }
    intervention_class = candidate_snapshot.get("intervention_class")
    novelty_penalty = (
        1
        if isinstance(intervention_class, str)
        and intervention_class in attempted_intervention_classes
        else 0
    )
    failure_focus_count = _request_task_count(candidate_snapshot, "failure_focus_task_ids")
    regression_focus_count = _request_task_count(candidate_snapshot, "regressed_task_ids")
    focus_penalty = 0 if (failure_focus_count + regression_focus_count) > 0 else 1
    regression_preference_penalty = 0
    if strategy_id == "regression_first":
        regression_preference_penalty = 0 if regression_focus_count > 0 else 1
    elif strategy_id == "alternate_failure_regression":
        regression_preference_penalty = 0 if regression_focus_count > 0 else 1
    slot_index = request.get("beam_slot_index")
    return (
        int(group["hard_failures"]),
        int(group["soft_failures"]),
        int(group["inconclusive"]),
        novelty_penalty,
        focus_penalty,
        regression_preference_penalty,
        -int(round((branch_score or 0.0) * 1000.0)),
        int(slot_index) if isinstance(slot_index, int) else int(candidate_snapshot["index"]),
        int(candidate_snapshot["index"]),
    )


def compute_candidate_branch_score(
    *,
    strategy_id: str,
    candidate_snapshot: dict[str, Any],
    attempted_intervention_classes: set[str],
) -> tuple[float, dict[str, Any]]:
    plugin_entry = _plugin_strategy_entry(strategy_id)
    plugin_hook = plugin_entry.get("compute_candidate_branch_score")
    if callable(plugin_hook):
        rendered = plugin_hook(
            strategy_id=strategy_id,
            candidate_snapshot=candidate_snapshot,
            attempted_intervention_classes=attempted_intervention_classes,
        )
        if (
            isinstance(rendered, tuple)
            and len(rendered) == 2
            and isinstance(rendered[1], dict)
        ):
            return float(rendered[0]), dict(rendered[1])
    strategy_id = _canonical_strategy_id(strategy_id)
    request = candidate_snapshot.get("generation_request")
    if not isinstance(request, dict):
        request = {}

    stage = str(request.get("stage") or "screening")
    stage_score = (
        float(_STAGE_ORDER.index(stage) + 1)
        if stage in _STAGE_ORDER
        else 1.0
    )
    intervention_class = candidate_snapshot.get("intervention_class")
    novelty_bonus = 1.0
    if (
        isinstance(intervention_class, str)
        and intervention_class
        and intervention_class in attempted_intervention_classes
    ):
        novelty_bonus = 0.0
    if strategy_id == "diversity_first":
        novelty_bonus *= 2.0
    elif strategy_id == "explore_then_exploit":
        novelty_bonus *= 1.5

    failure_focus_count = _request_task_count(candidate_snapshot, "failure_focus_task_ids")
    regression_focus_count = _request_task_count(candidate_snapshot, "regressed_task_ids")
    focus_bonus = min(float(failure_focus_count + regression_focus_count), 2.0) * 0.25
    regression_bonus = 0.5 if regression_focus_count > 0 else 0.0

    status = str(candidate_snapshot.get("status") or "pending")
    failure_class = str(candidate_snapshot.get("failure_class") or "")
    severity = _FAILURE_CLASS_SEVERITY.get(failure_class, _HARD_FAILURE_SEVERITY)
    outcome_score = 0.0
    if status == "success":
        outcome_score = 2.0
    elif status == "dry_run":
        outcome_score = 0.5
    elif status == "inconclusive":
        outcome_score = -0.25
    elif status in {"failed", "error"}:
        outcome_score = -0.25 * float(severity)
    if candidate_snapshot.get("promoted") is True:
        outcome_score += 1.5

    stability_penalty = 1.0 if candidate_snapshot.get("flaky") is True else 0.0
    if strategy_id == "stability_weighted":
        stability_penalty *= 2.0

    benchmark_cost = candidate_snapshot.get("benchmark_cost")
    benchmark_duration_seconds = candidate_snapshot.get("benchmark_duration_seconds")
    cost_penalty = 0.0
    if isinstance(benchmark_cost, (int, float)) and not isinstance(benchmark_cost, bool):
        cost_penalty += min(float(benchmark_cost), 10.0) * 0.1
    if isinstance(benchmark_duration_seconds, (int, float)) and not isinstance(
        benchmark_duration_seconds,
        bool,
    ):
        cost_penalty += min(float(benchmark_duration_seconds), 120.0) / 120.0

    score = stage_score + novelty_bonus + focus_bonus + regression_bonus + outcome_score
    score -= stability_penalty
    score -= cost_penalty
    rationale = {
        "stage": stage,
        "stage_score": stage_score,
        "novelty_bonus": novelty_bonus,
        "focus_bonus": focus_bonus,
        "regression_bonus": regression_bonus,
        "outcome_score": outcome_score,
        "stability_penalty": stability_penalty,
        "cost_penalty": cost_penalty,
        "failure_class": failure_class or None,
        "status": status,
        "promoted": bool(candidate_snapshot.get("promoted")),
        "flaky": bool(candidate_snapshot.get("flaky")),
    }
    return score, rationale


def resolve_next_stage(
    *,
    current_stage: str,
    stage_progression_mode: str,
    candidate_status: str,
    promoted: bool,
) -> str:
    plugin_entry = _plugin_strategy_entry(stage_progression_mode)
    plugin_hook = plugin_entry.get("resolve_next_stage")
    if callable(plugin_hook):
        rendered = plugin_hook(
            current_stage=current_stage,
            stage_progression_mode=stage_progression_mode,
            candidate_status=candidate_status,
            promoted=promoted,
        )
        if isinstance(rendered, str) and rendered:
            return rendered
    if stage_progression_mode == "fixed":
        return current_stage
    if stage_progression_mode == "advance_on_promotion" and not promoted:
        return current_stage
    if stage_progression_mode == "advance_on_success" and candidate_status != "success":
        return current_stage
    try:
        stage_index = _STAGE_ORDER.index(current_stage)
    except ValueError:
        return current_stage
    if stage_index >= len(_STAGE_ORDER) - 1:
        return current_stage
    return _STAGE_ORDER[stage_index + 1]


def stage_meets_minimum(stage: str, minimum_stage: str | None) -> bool:
    if minimum_stage is None:
        return True
    try:
        return _STAGE_ORDER.index(stage) >= _STAGE_ORDER.index(minimum_stage)
    except ValueError:
        return False
