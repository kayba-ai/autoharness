"""Workspace and track mutation helpers for the CLI layer."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from .campaigns import (
    CampaignEvaluatorPolicy,
    PromotionPolicy,
    TrackBenchmarkPolicy,
    TrackConfig,
)
from .preflight import available_preflight_checks
from .search import available_search_strategies
from .stages import stage_policy_for
from .tracking import (
    load_promotion_policy,
    load_track_policy,
    persist_promotion_policy,
    persist_track_config,
    persist_track_policy,
    promotion_policy_path,
    registry_dir_path,
    track_policy_path,
)
from .workspace import WorkspaceConfig, WorkspaceState


_CAMPAIGN_STAGE_VALUES = ("screening", "validation", "holdout", "transfer")
_CAMPAIGN_INTERVENTION_VALUES = ("prompt", "config", "middleware", "source")
_CAMPAIGN_STRATEGY_VALUES = available_search_strategies()
_CAMPAIGN_STAGE_PROGRESSION_VALUES = (
    "fixed",
    "advance_on_success",
    "advance_on_promotion",
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_promotion_policy(*, track_id: str, created_at: str | None = None) -> PromotionPolicy:
    return PromotionPolicy(
        format_version="autoharness.promotion_policy.v1",
        created_at=created_at or _utc_now(),
        track_id=track_id,
        min_improvement=0.0,
        task_regression_margin=0.0,
        notes=(
            "Pinned track-level promotion policy used by compare-to-champion and "
            "promote-from-compare. Edit this file to tighten promotion gates."
        ),
    )


def _default_track_benchmark_policy(
    *,
    track_id: str,
    benchmark: str,
    created_at: str | None = None,
) -> TrackBenchmarkPolicy:
    return TrackBenchmarkPolicy(
        format_version="autoharness.track_policy.v1",
        created_at=created_at or _utc_now(),
        track_id=track_id,
        search_benchmark=benchmark,
        promotion_benchmark=benchmark,
        regression_benchmark=benchmark,
        search_preset=None,
        promotion_preset=None,
        regression_preset=None,
        notes=(
            "Pinned track-level benchmark routing policy. Edit this file to change "
            "search, promotion, and regression benchmark targets for the track."
        ),
    )


def _default_campaign_policy_values() -> dict[str, object]:
    return {
        "stage": "screening",
        "stage_progression_mode": "fixed",
        "generator_id": "manual",
        "strategy": "sequential_manual",
        "beam_width": None,
        "beam_group_limit": None,
        "repeat_count": None,
        "intervention_classes": [],
        "preflight_checks": [],
        "preflight_commands": [],
        "preflight_timeout_seconds": None,
        "generator_metadata": {},
        "max_proposals": None,
        "max_iterations": None,
        "max_successes": None,
        "max_promotions": None,
        "max_failures": None,
        "max_inconclusive": None,
        "max_runtime_seconds": None,
        "max_generation_total_tokens": None,
        "max_benchmark_total_cost": None,
        "max_generation_retries": None,
        "max_generation_timeout_retries": None,
        "max_generation_provider_retries": None,
        "max_generation_provider_transport_retries": None,
        "max_generation_provider_auth_retries": None,
        "max_generation_provider_rate_limit_retries": None,
        "max_generation_process_retries": None,
        "max_preflight_retries": None,
        "max_execution_retries": None,
        "max_benchmark_process_retries": None,
        "max_benchmark_signal_retries": None,
        "max_benchmark_parse_retries": None,
        "max_benchmark_adapter_validation_retries": None,
        "max_benchmark_timeout_retries": None,
        "max_benchmark_command_retries": None,
        "max_inconclusive_retries": None,
        "no_improvement_limit": None,
        "auto_promote": False,
        "allow_flaky_promotion": False,
        "auto_promote_min_stage": None,
        "stop_on_first_promotion": False,
        "promotion_target_root": None,
    }


def _normalize_campaign_policy(policy: dict[str, object]) -> dict[str, object]:
    defaults = _default_campaign_policy_values()
    extra_keys = sorted(set(policy) - set(defaults))
    if extra_keys:
        raise SystemExit(
            "Unsupported campaign policy keys: " + ", ".join(extra_keys)
        )

    normalized: dict[str, object] = {}
    for key, value in policy.items():
        if key in {
            "stage",
            "stage_progression_mode",
            "generator_id",
            "strategy",
            "auto_promote_min_stage",
            "promotion_target_root",
        }:
            if not isinstance(value, str) or not value.strip():
                raise SystemExit(f"`campaign_policy.{key}` must be a non-empty string.")
            stripped = value.strip()
            if key == "stage" and stripped not in _CAMPAIGN_STAGE_VALUES:
                raise SystemExit(
                    "`campaign_policy.stage` must be one of: "
                    + ", ".join(_CAMPAIGN_STAGE_VALUES)
                    + "."
                )
            if key == "strategy" and stripped not in _CAMPAIGN_STRATEGY_VALUES:
                raise SystemExit(
                    "`campaign_policy.strategy` must be one of: "
                    + ", ".join(_CAMPAIGN_STRATEGY_VALUES)
                    + "."
                )
            if (
                key == "auto_promote_min_stage"
                and stripped not in _CAMPAIGN_STAGE_VALUES
            ):
                raise SystemExit(
                    "`campaign_policy.auto_promote_min_stage` must be one of: "
                    + ", ".join(_CAMPAIGN_STAGE_VALUES)
                    + "."
                )
            if (
                key == "stage_progression_mode"
                and stripped not in _CAMPAIGN_STAGE_PROGRESSION_VALUES
            ):
                raise SystemExit(
                    "`campaign_policy.stage_progression_mode` must be one of: "
                    + ", ".join(_CAMPAIGN_STAGE_PROGRESSION_VALUES)
                    + "."
                )
            normalized[key] = stripped
            continue

        if key == "intervention_classes":
            if not isinstance(value, (list, tuple)):
                raise SystemExit(
                    "`campaign_policy.intervention_classes` must be a list of strings."
                )
            seen: set[str] = set()
            normalized_values: list[str] = []
            for entry in value:
                if not isinstance(entry, str) or not entry.strip():
                    raise SystemExit(
                        "`campaign_policy.intervention_classes` may not contain empty values."
                    )
                stripped = entry.strip()
                if stripped not in _CAMPAIGN_INTERVENTION_VALUES:
                    raise SystemExit(
                        "`campaign_policy.intervention_classes` must use only: "
                        + ", ".join(_CAMPAIGN_INTERVENTION_VALUES)
                        + "."
                    )
                if stripped in seen:
                    continue
                seen.add(stripped)
                normalized_values.append(stripped)
            normalized[key] = normalized_values
            continue

        if key == "preflight_commands":
            if not isinstance(value, (list, tuple)):
                raise SystemExit(
                    "`campaign_policy.preflight_commands` must be a list of strings."
                )
            normalized_commands: list[str] = []
            for entry in value:
                if not isinstance(entry, str) or not entry.strip():
                    raise SystemExit(
                        "`campaign_policy.preflight_commands` may not contain empty values."
                    )
                normalized_commands.append(entry.strip())
            normalized[key] = normalized_commands
            continue

        if key == "preflight_checks":
            if not isinstance(value, (list, tuple)):
                raise SystemExit(
                    "`campaign_policy.preflight_checks` must be a list of strings."
                )
            supported_checks = set(available_preflight_checks())
            normalized_checks: list[str] = []
            for entry in value:
                if not isinstance(entry, str) or not entry.strip():
                    raise SystemExit(
                        "`campaign_policy.preflight_checks` may not contain empty values."
                    )
                stripped = entry.strip()
                if stripped not in supported_checks:
                    raise SystemExit(
                        "`campaign_policy.preflight_checks` must use only: "
                        + ", ".join(sorted(supported_checks))
                        + "."
                    )
                normalized_checks.append(stripped)
            normalized[key] = normalized_checks
            continue

        if key == "generator_metadata":
            if not isinstance(value, dict):
                raise SystemExit(
                    "`campaign_policy.generator_metadata` must be a mapping."
                )
            normalized_metadata: dict[str, str] = {}
            for metadata_key, metadata_value in value.items():
                if not isinstance(metadata_key, str) or not metadata_key.strip():
                    raise SystemExit(
                        "`campaign_policy.generator_metadata` may not contain empty keys."
                    )
                if not isinstance(metadata_value, str) or not metadata_value.strip():
                    raise SystemExit(
                        "`campaign_policy.generator_metadata` may not contain empty values."
                    )
                normalized_metadata[metadata_key.strip()] = metadata_value.strip()
            normalized[key] = normalized_metadata
            continue

        if key in {
            "max_proposals",
            "beam_width",
            "beam_group_limit",
            "repeat_count",
            "preflight_timeout_seconds",
            "max_iterations",
            "max_successes",
            "max_promotions",
            "max_failures",
            "max_inconclusive",
            "max_runtime_seconds",
            "max_generation_total_tokens",
            "max_generation_retries",
            "max_generation_timeout_retries",
            "max_generation_provider_retries",
            "max_generation_provider_transport_retries",
            "max_generation_provider_auth_retries",
            "max_generation_provider_rate_limit_retries",
            "max_generation_process_retries",
            "max_preflight_retries",
            "max_execution_retries",
            "max_benchmark_process_retries",
            "max_benchmark_signal_retries",
            "max_benchmark_parse_retries",
            "max_benchmark_adapter_validation_retries",
            "max_benchmark_timeout_retries",
            "max_benchmark_command_retries",
            "max_inconclusive_retries",
            "no_improvement_limit",
        }:
            if not isinstance(value, int) or value < 1:
                raise SystemExit(f"`campaign_policy.{key}` must be an integer >= 1.")
            normalized[key] = value
            continue

        if key in {
            "max_benchmark_total_cost",
        }:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise SystemExit(f"`campaign_policy.{key}` must be a number > 0.")
            normalized[key] = float(value)
            continue

        if key in {
            "auto_promote",
            "allow_flaky_promotion",
            "stop_on_first_promotion",
        }:
            if not isinstance(value, bool):
                raise SystemExit(f"`campaign_policy.{key}` must be a boolean.")
            normalized[key] = value
            continue

        raise SystemExit(f"Unsupported campaign policy key: {key}")

    return normalized


def _resolve_track_campaign_policy(
    *,
    workspace: WorkspaceConfig,
    track_id: str,
) -> tuple[dict[str, object], dict[str, str]]:
    defaults = _default_campaign_policy_values()
    workspace_defaults = _normalize_campaign_policy(dict(workspace.campaign_policy))
    track_defaults = _normalize_campaign_policy(
        dict(workspace.tracks[track_id].campaign_policy)
    )
    effective: dict[str, object] = {}
    sources: dict[str, str] = {}
    for key, default_value in defaults.items():
        if key in track_defaults:
            effective[key] = track_defaults[key]
            sources[key] = "track_override"
        elif key in workspace_defaults:
            effective[key] = workspace_defaults[key]
            sources[key] = "workspace_default"
        else:
            effective[key] = default_value
            sources[key] = "built_in"
    return effective, sources


def _coalesce_track_policy_with_workspace_defaults(
    *,
    policy: TrackBenchmarkPolicy,
    workspace_defaults: dict[str, object],
) -> TrackBenchmarkPolicy:
    def _optional_default(key: str) -> str | None:
        value = workspace_defaults.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return None

    return replace(
        policy,
        search_preset=policy.search_preset or _optional_default("search_preset"),
        promotion_preset=policy.promotion_preset or _optional_default("promotion_preset"),
        regression_preset=policy.regression_preset or _optional_default("regression_preset"),
    )


def _resolve_promotion_policy(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> tuple[PromotionPolicy | None, str]:
    policy_path = promotion_policy_path(root=root, workspace_id=workspace_id, track_id=track_id)
    try:
        return (
            load_promotion_policy(root=root, workspace_id=workspace_id, track_id=track_id),
            str(policy_path),
        )
    except FileNotFoundError:
        return None, str(policy_path)


def _resolve_track_benchmark_policy(
    *,
    root: Path,
    workspace: WorkspaceConfig,
    workspace_id: str,
    track_id: str,
) -> tuple[TrackBenchmarkPolicy, str]:
    policy_path = track_policy_path(root=root, workspace_id=workspace_id, track_id=track_id)
    workspace_defaults = workspace.benchmark_policy
    try:
        policy = load_track_policy(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
        )
        return (
            _coalesce_track_policy_with_workspace_defaults(
                policy=policy,
                workspace_defaults=workspace_defaults,
            ),
            str(policy_path),
        )
    except FileNotFoundError:
        return (
            TrackBenchmarkPolicy(
                format_version="autoharness.track_policy.v1",
                created_at=workspace.created_at,
                track_id=track_id,
                search_benchmark=str(
                    workspace_defaults.get(
                        "search_benchmark",
                        workspace.tracks[track_id].benchmark,
                    )
                ),
                promotion_benchmark=str(
                    workspace_defaults.get(
                        "promotion_benchmark",
                        workspace.tracks[track_id].benchmark,
                    )
                ),
                regression_benchmark=str(
                    workspace_defaults.get(
                        "regression_benchmark",
                        workspace.tracks[track_id].benchmark,
                    )
                ),
                search_preset=(
                    str(workspace_defaults["search_preset"])
                    if workspace_defaults.get("search_preset") is not None
                    else None
                ),
                promotion_preset=(
                    str(workspace_defaults["promotion_preset"])
                    if workspace_defaults.get("promotion_preset") is not None
                    else None
                ),
                regression_preset=(
                    str(workspace_defaults["regression_preset"])
                    if workspace_defaults.get("regression_preset") is not None
                    else None
                ),
                notes="Workspace-level benchmark policy fallback.",
            ),
            str(policy_path),
        )


def _validate_promotion_policy(policy: PromotionPolicy) -> None:
    if policy.stage is not None and policy.stage not in (
        "screening",
        "validation",
        "holdout",
        "transfer",
    ):
        raise SystemExit(f"Unsupported promotion policy stage: {policy.stage}")
    if policy.min_success_rate is not None and not (0.0 <= policy.min_success_rate <= 1.0):
        raise SystemExit("`min_success_rate` must be between 0 and 1 when provided.")
    if policy.min_improvement is not None and policy.min_improvement < 0.0:
        raise SystemExit("`min_improvement` must be at least 0 when provided.")
    try:
        stage_policy_for(
            policy.stage or "screening",
            min_judge_pass_rate=(
                policy.min_success_rate if policy.min_success_rate is not None else 0.55
            ),
            max_regressed_tasks=policy.max_regressed_tasks,
            max_regressed_task_fraction=policy.max_regressed_task_fraction,
            max_regressed_task_weight=policy.max_regressed_task_weight,
            max_regressed_task_weight_fraction=policy.max_regressed_task_weight_fraction,
            task_regression_margin=policy.task_regression_margin or 0.0,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _policy_or_override(override, policy_value, fallback):
    if override is not None:
        return override
    if policy_value is not None:
        return policy_value
    return fallback


def _resolve_update_field(
    *,
    option_name: str,
    current_value,
    value,
    clear: bool = False,
):
    if clear and value is not None:
        raise SystemExit(f"Use either `--{option_name}` or `--clear-{option_name}`, not both.")
    if clear:
        return None, True
    if value is not None:
        return value, True
    return current_value, False


def _resolve_campaign_policy_updates(
    *,
    current_values: dict[str, object],
    args: argparse.Namespace,
    changed_prefix: str,
    remove_cleared: bool,
) -> tuple[dict[str, object], list[str]]:
    updated = dict(current_values)
    changed_fields: list[str] = []

    scalar_specs = (
        ("campaign_stage", "stage"),
        ("campaign_stage_progression", "stage_progression_mode"),
        ("campaign_generator", "generator_id"),
        ("campaign_strategy", "strategy"),
        ("campaign_beam_width", "beam_width"),
        ("campaign_beam_groups", "beam_group_limit"),
        ("campaign_repeat_count", "repeat_count"),
        ("campaign_preflight_timeout_seconds", "preflight_timeout_seconds"),
        ("campaign_auto_promote_min_stage", "auto_promote_min_stage"),
        ("campaign_promotion_target_root", "promotion_target_root"),
        ("campaign_max_proposals", "max_proposals"),
        ("campaign_max_iterations", "max_iterations"),
        ("campaign_max_successes", "max_successes"),
        ("campaign_max_promotions", "max_promotions"),
        ("campaign_max_failures", "max_failures"),
        ("campaign_max_inconclusive", "max_inconclusive"),
        ("campaign_max_runtime_seconds", "max_runtime_seconds"),
        ("campaign_max_generation_total_tokens", "max_generation_total_tokens"),
        ("campaign_max_benchmark_total_cost", "max_benchmark_total_cost"),
        ("campaign_max_generation_retries", "max_generation_retries"),
        (
            "campaign_max_generation_timeout_retries",
            "max_generation_timeout_retries",
        ),
        (
            "campaign_max_generation_provider_retries",
            "max_generation_provider_retries",
        ),
        (
            "campaign_max_generation_provider_transport_retries",
            "max_generation_provider_transport_retries",
        ),
        (
            "campaign_max_generation_provider_auth_retries",
            "max_generation_provider_auth_retries",
        ),
        (
            "campaign_max_generation_provider_rate_limit_retries",
            "max_generation_provider_rate_limit_retries",
        ),
        (
            "campaign_max_generation_process_retries",
            "max_generation_process_retries",
        ),
        ("campaign_max_preflight_retries", "max_preflight_retries"),
        ("campaign_max_execution_retries", "max_execution_retries"),
        (
            "campaign_max_benchmark_process_retries",
            "max_benchmark_process_retries",
        ),
        (
            "campaign_max_benchmark_signal_retries",
            "max_benchmark_signal_retries",
        ),
        (
            "campaign_max_benchmark_parse_retries",
            "max_benchmark_parse_retries",
        ),
        (
            "campaign_max_benchmark_adapter_validation_retries",
            "max_benchmark_adapter_validation_retries",
        ),
        (
            "campaign_max_benchmark_timeout_retries",
            "max_benchmark_timeout_retries",
        ),
        (
            "campaign_max_benchmark_command_retries",
            "max_benchmark_command_retries",
        ),
        ("campaign_max_inconclusive_retries", "max_inconclusive_retries"),
        ("campaign_no_improvement_limit", "no_improvement_limit"),
    )
    for option_name, field_name in scalar_specs:
        value = getattr(args, option_name, None)
        if field_name == "promotion_target_root" and value is not None:
            value = str(value)
        clear = bool(getattr(args, f"clear_{option_name}", False))
        resolved, changed = _resolve_update_field(
            option_name=option_name.replace("_", "-"),
            current_value=updated.get(field_name),
            value=value,
            clear=clear,
        )
        if not changed:
            continue
        if remove_cleared and resolved is None:
            updated.pop(field_name, None)
        else:
            updated[field_name] = resolved
        changed_fields.append(f"{changed_prefix}{field_name}")

    if (
        getattr(args, "clear_campaign_intervention_classes", False)
        and getattr(args, "campaign_intervention_class", None)
    ):
        raise SystemExit(
            "Use either `--campaign-intervention-class` or "
            "`--clear-campaign-intervention-classes`, not both."
        )
    if getattr(args, "clear_campaign_intervention_classes", False):
        if remove_cleared:
            updated.pop("intervention_classes", None)
        else:
            updated["intervention_classes"] = []
        changed_fields.append(f"{changed_prefix}intervention_classes")
    elif getattr(args, "campaign_intervention_class", None):
        updated["intervention_classes"] = list(args.campaign_intervention_class)
        changed_fields.append(f"{changed_prefix}intervention_classes")

    if (
        getattr(args, "clear_campaign_preflight_checks", False)
        and getattr(args, "campaign_preflight_check", None)
    ):
        raise SystemExit(
            "Use either `--campaign-preflight-check` or "
            "`--clear-campaign-preflight-checks`, not both."
        )
    if getattr(args, "clear_campaign_preflight_checks", False):
        if remove_cleared:
            updated.pop("preflight_checks", None)
        else:
            updated["preflight_checks"] = []
        changed_fields.append(f"{changed_prefix}preflight_checks")
    elif getattr(args, "campaign_preflight_check", None):
        updated["preflight_checks"] = list(args.campaign_preflight_check)
        changed_fields.append(f"{changed_prefix}preflight_checks")

    if (
        getattr(args, "clear_campaign_preflight_commands", False)
        and getattr(args, "campaign_preflight_command", None)
    ):
        raise SystemExit(
            "Use either `--campaign-preflight-command` or "
            "`--clear-campaign-preflight-commands`, not both."
        )
    if getattr(args, "clear_campaign_preflight_commands", False):
        if remove_cleared:
            updated.pop("preflight_commands", None)
        else:
            updated["preflight_commands"] = []
        changed_fields.append(f"{changed_prefix}preflight_commands")
    elif getattr(args, "campaign_preflight_command", None):
        updated["preflight_commands"] = list(args.campaign_preflight_command)
        changed_fields.append(f"{changed_prefix}preflight_commands")

    if (
        getattr(args, "clear_campaign_generator_options", False)
        and getattr(args, "campaign_generator_option", None)
    ):
        raise SystemExit(
            "Use either `--campaign-generator-option` or "
            "`--clear-campaign-generator-options`, not both."
        )
    if getattr(args, "clear_campaign_generator_options", False):
        if remove_cleared:
            updated.pop("generator_metadata", None)
        else:
            updated["generator_metadata"] = {}
        changed_fields.append(f"{changed_prefix}generator_metadata")
    elif getattr(args, "campaign_generator_option", None):
        generator_metadata: dict[str, str] = {}
        for raw_entry in args.campaign_generator_option:
            if "=" not in raw_entry:
                raise SystemExit(
                    "`--campaign-generator-option` must use key=value format."
                )
            key, value = raw_entry.split("=", 1)
            if not key.strip() or not value.strip():
                raise SystemExit(
                    "`--campaign-generator-option` requires non-empty key and value."
                )
            generator_metadata[key.strip()] = value.strip()
        updated["generator_metadata"] = generator_metadata
        changed_fields.append(f"{changed_prefix}generator_metadata")

    bool_specs = (
        ("campaign_auto_promote", "auto_promote"),
        ("campaign_allow_flaky_promotion", "allow_flaky_promotion"),
        ("campaign_stop_on_first_promotion", "stop_on_first_promotion"),
    )
    for option_name, field_name in bool_specs:
        clear = bool(getattr(args, f"clear_{option_name}", False))
        value = getattr(args, option_name, None)
        if clear and value is not None:
            raise SystemExit(
                f"Use either `--{option_name.replace('_', '-')}` or "
                f"`--clear-{option_name.replace('_', '-')}`, not both."
            )
        if clear:
            if remove_cleared:
                updated.pop(field_name, None)
            else:
                updated[field_name] = None
            changed_fields.append(f"{changed_prefix}{field_name}")
        elif value is not None:
            updated[field_name] = bool(value)
            changed_fields.append(f"{changed_prefix}{field_name}")

    return _normalize_campaign_policy(updated), changed_fields


def _resolve_notes_update(
    *,
    current_value: str | None,
    value: str | None,
    clear: bool,
) -> tuple[str, bool]:
    resolved, changed = _resolve_update_field(
        option_name="notes",
        current_value=current_value,
        value=value,
        clear=clear,
    )
    return ("" if resolved is None else str(resolved)), changed


def _apply_track_evaluator_overrides(
    *,
    evaluator: CampaignEvaluatorPolicy,
    args: argparse.Namespace,
    field_prefix: str = "evaluator",
) -> tuple[CampaignEvaluatorPolicy, list[str]]:
    updated = evaluator
    changed_fields: list[str] = []
    override_specs = (
        ("evaluator_version", "evaluator_version"),
        ("judge_model", "judge_model"),
        ("diagnostic_model", "diagnostic_model"),
        ("max_diagnostic_tasks", "max_diagnostic_tasks"),
        ("min_judge_pass_rate", "min_judge_pass_rate"),
    )
    for attr_name, field_name in override_specs:
        value = getattr(args, attr_name, None)
        if value is None:
            continue
        updated = replace(updated, **{attr_name: value})
        changed_fields.append(f"{field_prefix}.{field_name}")
    return updated, changed_fields


def _resolve_routing_policy_updates(
    *,
    current_values: dict[str, str | None],
    args: argparse.Namespace,
    changed_prefix: str,
    remove_cleared_presets: bool,
) -> tuple[dict[str, str | None], list[str]]:
    updated = dict(current_values)
    changed_fields: list[str] = []

    benchmark = args.benchmark
    for field_name in (
        "search_benchmark",
        "promotion_benchmark",
        "regression_benchmark",
    ):
        value = getattr(args, field_name)
        if benchmark is None and value is None:
            continue
        updated[field_name] = value or benchmark
        changed_fields.append(f"{changed_prefix}{field_name}")

    preset = args.preset
    for field_name in (
        "search_preset",
        "promotion_preset",
        "regression_preset",
    ):
        clear_field_name = f"clear_{field_name}"
        if getattr(args, "clear_preset") or getattr(args, clear_field_name):
            if remove_cleared_presets:
                updated.pop(field_name, None)
            else:
                updated[field_name] = None
            changed_fields.append(f"{changed_prefix}{field_name}")
        value = getattr(args, field_name)
        if preset is None and value is None:
            continue
        updated[field_name] = value or preset
        changed_fields.append(f"{changed_prefix}{field_name}")

    return updated, changed_fields


def _validate_track_benchmark_policy(policy: TrackBenchmarkPolicy) -> None:
    if not policy.search_benchmark:
        raise SystemExit("`search_benchmark` must be non-empty.")
    if not policy.promotion_benchmark:
        raise SystemExit("`promotion_benchmark` must be non-empty.")
    if not policy.regression_benchmark:
        raise SystemExit("`regression_benchmark` must be non-empty.")
    for field_name in ("search_preset", "promotion_preset", "regression_preset"):
        value = getattr(policy, field_name)
        if value is not None and not value.strip():
            raise SystemExit(f"`{field_name}` must be non-empty when provided.")


def _validate_track_config(track: TrackConfig) -> None:
    if not track.benchmark.strip():
        raise SystemExit("`benchmark` must be non-empty.")
    if not track.objective.strip():
        raise SystemExit("`objective` must be non-empty.")
    if track.status not in {"active", "archived"}:
        raise SystemExit("`status` must be either `active` or `archived`.")
    if not track.kind.strip():
        raise SystemExit("`kind` must be non-empty.")
    if not track.campaign_id.strip():
        raise SystemExit("`campaign_id` must be non-empty.")
    if any(not reference_id.strip() for reference_id in track.benchmark_reference_ids):
        raise SystemExit("`benchmark_reference_ids` may not contain empty values.")
    if not track.evaluator.evaluator_version.strip():
        raise SystemExit("`evaluator_version` must be non-empty.")
    if not track.evaluator.judge_model.strip():
        raise SystemExit("`judge_model` must be non-empty.")
    if not track.evaluator.diagnostic_model.strip():
        raise SystemExit("`diagnostic_model` must be non-empty.")
    if track.evaluator.max_diagnostic_tasks < 0:
        raise SystemExit("`max_diagnostic_tasks` must be at least 0.")
    if not (0.0 <= track.evaluator.min_judge_pass_rate <= 1.0):
        raise SystemExit("`min_judge_pass_rate` must be between 0 and 1.")


def _validate_workspace_config(workspace: WorkspaceConfig) -> None:
    if not workspace.objective.strip():
        raise SystemExit("`objective` must be non-empty.")
    if not workspace.domain.strip():
        raise SystemExit("`domain` must be non-empty.")
    if workspace.active_track_id not in workspace.tracks:
        raise SystemExit(
            f"`active_track_id` must reference an existing track. Got `{workspace.active_track_id}`."
        )
    if workspace.tracks[workspace.active_track_id].status != "active":
        raise SystemExit("`active_track_id` must reference a track with status `active`.")
    for key in ("search_benchmark", "promotion_benchmark", "regression_benchmark"):
        value = workspace.benchmark_policy.get(key)
        if not isinstance(value, str) or not value.strip():
            raise SystemExit(f"`benchmark_policy.{key}` must be a non-empty string.")
    for key in ("search_preset", "promotion_preset", "regression_preset"):
        value = workspace.benchmark_policy.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise SystemExit(
                f"`benchmark_policy.{key}` must be a non-empty string when provided."
            )
    _normalize_campaign_policy(dict(workspace.campaign_policy))
    for track in workspace.tracks.values():
        _normalize_campaign_policy(dict(track.campaign_policy))


def _require_active_workspace_state(*, workspace_id: str, state: WorkspaceState) -> None:
    if state.status != "active":
        raise SystemExit(f"Workspace `{workspace_id}` is archived and cannot be modified.")


def _workspace_track_count_summary(workspace: WorkspaceConfig) -> dict[str, int]:
    return {
        "tracks_total": len(workspace.tracks),
        "active_tracks_total": sum(
            1 for track in workspace.tracks.values() if track.status == "active"
        ),
        "archived_tracks_total": sum(
            1 for track in workspace.tracks.values() if track.status == "archived"
        ),
    }


def _refresh_workspace_state_track_counts(
    *,
    state: WorkspaceState,
    workspace: WorkspaceConfig,
    active_track_id: str,
) -> WorkspaceState:
    summary = dict(state.summary)
    summary.update(_workspace_track_count_summary(workspace))
    return replace(
        state,
        active_track_id=active_track_id,
        summary=summary,
    )


def _persist_track_bootstrap_artifacts(
    *,
    root: Path,
    workspace_id: str,
    track: TrackConfig,
    created_at: str,
) -> None:
    persist_track_config(
        root=root,
        workspace_id=workspace_id,
        track=track,
    )
    persist_promotion_policy(
        root=root,
        workspace_id=workspace_id,
        track_id=track.track_id,
        policy=_default_promotion_policy(
            track_id=track.track_id,
            created_at=created_at,
        ),
    )
    persist_track_policy(
        root=root,
        workspace_id=workspace_id,
        track_id=track.track_id,
        policy=_default_track_benchmark_policy(
            track_id=track.track_id,
            benchmark=track.benchmark,
            created_at=created_at,
        ),
    )
    registry_dir_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track.track_id,
    ).mkdir(parents=True, exist_ok=True)
