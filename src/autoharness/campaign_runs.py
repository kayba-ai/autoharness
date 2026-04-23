"""Persisted campaign-run state for resumable proposal execution."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .coordination import file_lock, write_json_atomic
from .tracking import load_workspace, track_dir_path


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_utc_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in JSON file: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    write_json_atomic(path, payload)


def campaign_runs_dir_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return track_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / "campaign_runs"


def campaign_run_path(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    campaign_run_id: str,
) -> Path:
    return campaign_runs_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / f"{campaign_run_id}.json"


def workspace_campaign_lease_path(*, root: Path, workspace_id: str) -> Path:
    return root / workspace_id / "campaign_worker_lease.json"


@dataclass(frozen=True)
class CampaignCandidateRun:
    index: int
    edit_plan_path: str | None = None
    attempt_count: int = 0
    retry_counts: dict[str, int] = field(default_factory=dict)
    source_mode: str = "manual_edit_plan"
    intervention_class: str | None = None
    hypothesis: str | None = None
    generation_request: dict[str, Any] = field(default_factory=dict)
    proposal_id: str | None = None
    iteration_id: str | None = None
    record_id: str | None = None
    promotion_id: str | None = None
    promoted: bool = False
    comparison_decision: str | None = None
    branch_score: float | None = None
    branch_score_rationale: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"
    failure_class: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "retry_counts": dict(self.retry_counts),
            "generation_request": dict(self.generation_request),
            "branch_score_rationale": dict(self.branch_score_rationale),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignCandidateRun":
        return cls(
            index=int(data["index"]),
            edit_plan_path=(
                str(data["edit_plan_path"]) if data.get("edit_plan_path") is not None else None
            ),
            attempt_count=int(data.get("attempt_count", 0)),
            retry_counts={
                str(key): int(value)
                for key, value in dict(data.get("retry_counts", {})).items()
            },
            source_mode=str(data.get("source_mode", "manual_edit_plan")),
            intervention_class=(
                str(data["intervention_class"])
                if data.get("intervention_class") is not None
                else None
            ),
            hypothesis=str(data["hypothesis"]) if data.get("hypothesis") is not None else None,
            generation_request=dict(data.get("generation_request", {})),
            proposal_id=str(data["proposal_id"]) if data.get("proposal_id") is not None else None,
            iteration_id=str(data["iteration_id"]) if data.get("iteration_id") is not None else None,
            record_id=str(data["record_id"]) if data.get("record_id") is not None else None,
            promotion_id=(
                str(data["promotion_id"]) if data.get("promotion_id") is not None else None
            ),
            promoted=bool(data.get("promoted", False)),
            comparison_decision=(
                str(data["comparison_decision"])
                if data.get("comparison_decision") is not None
                else None
            ),
            branch_score=(
                float(data["branch_score"])
                if data.get("branch_score") is not None
                else None
            ),
            branch_score_rationale=dict(data.get("branch_score_rationale", {})),
            status=str(data.get("status", "pending")),
            failure_class=(
                str(data["failure_class"]) if data.get("failure_class") is not None else None
            ),
            error=str(data["error"]) if data.get("error") is not None else None,
        )


@dataclass(frozen=True)
class CampaignDecisionLogEntry:
    created_at: str
    event: str
    candidate_index: int | None = None
    proposal_id: str | None = None
    record_id: str | None = None
    promotion_id: str | None = None
    status: str | None = None
    failure_class: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "details": dict(self.details),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignDecisionLogEntry":
        return cls(
            created_at=str(data["created_at"]),
            event=str(data["event"]),
            candidate_index=(
                int(data["candidate_index"])
                if data.get("candidate_index") is not None
                else None
            ),
            proposal_id=str(data["proposal_id"]) if data.get("proposal_id") is not None else None,
            record_id=str(data["record_id"]) if data.get("record_id") is not None else None,
            promotion_id=(
                str(data["promotion_id"]) if data.get("promotion_id") is not None else None
            ),
            status=str(data["status"]) if data.get("status") is not None else None,
            failure_class=(
                str(data["failure_class"]) if data.get("failure_class") is not None else None
            ),
            details=dict(data.get("details", {})),
        )


@dataclass(frozen=True)
class CampaignRun:
    format_version: str
    campaign_run_id: str
    created_at: str
    updated_at: str
    workspace_id: str
    track_id: str
    adapter_id: str
    stage: str
    initial_stage: str
    stage_progression_mode: str
    generator_id: str
    execution_mode: str
    desired_state: str
    status: str
    strategy: str
    beam_width: int | None
    beam_group_limit: int | None
    repeat_count: int | None
    candidate_source_mode: str
    target_root: str
    config_path: str | None
    preset: str | None
    inline_overrides: tuple[str, ...]
    intervention_classes: tuple[str, ...]
    preflight_checks: tuple[str, ...]
    preflight_commands: tuple[str, ...]
    preflight_timeout_seconds: int | None
    generator_metadata: dict[str, Any]
    dry_run: bool
    max_proposals: int | None
    max_iterations: int | None
    max_successes: int | None
    max_promotions: int | None
    max_failures: int | None
    max_inconclusive: int | None
    max_runtime_seconds: int | None
    max_generation_total_tokens: int | None
    max_benchmark_total_cost: float | None
    max_generation_retries: int | None
    max_generation_timeout_retries: int | None
    max_generation_provider_retries: int | None
    max_generation_provider_transport_retries: int | None
    max_generation_provider_auth_retries: int | None
    max_generation_provider_rate_limit_retries: int | None
    max_generation_process_retries: int | None
    max_preflight_retries: int | None
    max_execution_retries: int | None
    max_benchmark_process_retries: int | None
    max_benchmark_signal_retries: int | None
    max_benchmark_parse_retries: int | None
    max_benchmark_adapter_validation_retries: int | None
    max_benchmark_timeout_retries: int | None
    max_benchmark_command_retries: int | None
    max_inconclusive_retries: int | None
    no_improvement_limit: int | None
    success_count: int
    failure_count: int
    inconclusive_count: int
    no_improvement_streak: int
    promoted_count: int
    auto_promote: bool
    allow_flaky_promotion: bool
    auto_promote_min_stage: str | None
    stop_on_first_promotion: bool
    promotion_target_root: str | None
    next_candidate_index: int
    lease_owner: str | None = None
    lease_claimed_at: str | None = None
    lease_heartbeat_at: str | None = None
    lease_expires_at: str | None = None
    stop_reason: str | None = None
    candidates: tuple[CampaignCandidateRun, ...] = ()
    decision_log: tuple[CampaignDecisionLogEntry, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "inline_overrides": list(self.inline_overrides),
            "intervention_classes": list(self.intervention_classes),
            "preflight_checks": list(self.preflight_checks),
            "preflight_commands": list(self.preflight_commands),
            "generator_metadata": dict(self.generator_metadata),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "decision_log": [entry.to_dict() for entry in self.decision_log],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CampaignRun":
        return cls(
            format_version=str(data["format_version"]),
            campaign_run_id=str(data["campaign_run_id"]),
            created_at=str(data["created_at"]),
            updated_at=str(data["updated_at"]),
            workspace_id=str(data["workspace_id"]),
            track_id=str(data["track_id"]),
            adapter_id=str(data["adapter_id"]),
            stage=str(data["stage"]),
            initial_stage=str(data.get("initial_stage", data["stage"])),
            stage_progression_mode=str(data.get("stage_progression_mode", "fixed")),
            generator_id=str(data.get("generator_id", "manual")),
            execution_mode=str(data.get("execution_mode", "foreground")),
            desired_state=str(data.get("desired_state", "run")),
            status=str(data["status"]),
            strategy=str(data.get("strategy", "sequential_manual")),
            beam_width=(
                int(data["beam_width"]) if data.get("beam_width") is not None else None
            ),
            beam_group_limit=(
                int(data["beam_group_limit"])
                if data.get("beam_group_limit") is not None
                else None
            ),
            repeat_count=(
                int(data["repeat_count"])
                if data.get("repeat_count") is not None
                else None
            ),
            candidate_source_mode=str(
                data.get(
                    "candidate_source_mode",
                    "manual_edit_plan_list"
                    if data.get("generator_id", "manual") == "manual"
                    else "generator_loop",
                )
            ),
            target_root=str(data["target_root"]),
            config_path=str(data["config_path"]) if data.get("config_path") is not None else None,
            preset=str(data["preset"]) if data.get("preset") is not None else None,
            inline_overrides=tuple(str(entry) for entry in data.get("inline_overrides", [])),
            intervention_classes=tuple(
                str(entry) for entry in data.get("intervention_classes", ())
            ),
            preflight_checks=tuple(
                str(entry) for entry in data.get("preflight_checks", ())
            ),
            preflight_commands=tuple(
                str(entry) for entry in data.get("preflight_commands", ())
            ),
            preflight_timeout_seconds=(
                int(data["preflight_timeout_seconds"])
                if data.get("preflight_timeout_seconds") is not None
                else None
            ),
            generator_metadata={
                str(key): str(value)
                for key, value in dict(data.get("generator_metadata", {})).items()
            },
            dry_run=bool(data.get("dry_run", False)),
            max_proposals=(
                int(data["max_proposals"]) if data.get("max_proposals") is not None else None
            ),
            max_iterations=(
                int(data["max_iterations"]) if data.get("max_iterations") is not None else None
            ),
            max_successes=(
                int(data["max_successes"]) if data.get("max_successes") is not None else None
            ),
            max_promotions=(
                int(data["max_promotions"]) if data.get("max_promotions") is not None else None
            ),
            max_failures=(
                int(data["max_failures"]) if data.get("max_failures") is not None else None
            ),
            max_inconclusive=(
                int(data["max_inconclusive"])
                if data.get("max_inconclusive") is not None
                else None
            ),
            max_runtime_seconds=(
                int(data["max_runtime_seconds"])
                if data.get("max_runtime_seconds") is not None
                else None
            ),
            max_generation_total_tokens=(
                int(data["max_generation_total_tokens"])
                if data.get("max_generation_total_tokens") is not None
                else None
            ),
            max_benchmark_total_cost=(
                float(data["max_benchmark_total_cost"])
                if data.get("max_benchmark_total_cost") is not None
                else None
            ),
            max_generation_retries=(
                int(data["max_generation_retries"])
                if data.get("max_generation_retries") is not None
                else None
            ),
            max_generation_timeout_retries=(
                int(data["max_generation_timeout_retries"])
                if data.get("max_generation_timeout_retries") is not None
                else None
            ),
            max_generation_provider_retries=(
                int(data["max_generation_provider_retries"])
                if data.get("max_generation_provider_retries") is not None
                else None
            ),
            max_generation_provider_transport_retries=(
                int(data["max_generation_provider_transport_retries"])
                if data.get("max_generation_provider_transport_retries") is not None
                else None
            ),
            max_generation_provider_auth_retries=(
                int(data["max_generation_provider_auth_retries"])
                if data.get("max_generation_provider_auth_retries") is not None
                else None
            ),
            max_generation_provider_rate_limit_retries=(
                int(data["max_generation_provider_rate_limit_retries"])
                if data.get("max_generation_provider_rate_limit_retries") is not None
                else None
            ),
            max_generation_process_retries=(
                int(data["max_generation_process_retries"])
                if data.get("max_generation_process_retries") is not None
                else None
            ),
            max_preflight_retries=(
                int(data["max_preflight_retries"])
                if data.get("max_preflight_retries") is not None
                else None
            ),
            max_execution_retries=(
                int(data["max_execution_retries"])
                if data.get("max_execution_retries") is not None
                else None
            ),
            max_benchmark_process_retries=(
                int(data["max_benchmark_process_retries"])
                if data.get("max_benchmark_process_retries") is not None
                else None
            ),
            max_benchmark_signal_retries=(
                int(data["max_benchmark_signal_retries"])
                if data.get("max_benchmark_signal_retries") is not None
                else None
            ),
            max_benchmark_parse_retries=(
                int(data["max_benchmark_parse_retries"])
                if data.get("max_benchmark_parse_retries") is not None
                else None
            ),
            max_benchmark_adapter_validation_retries=(
                int(data["max_benchmark_adapter_validation_retries"])
                if data.get("max_benchmark_adapter_validation_retries") is not None
                else None
            ),
            max_benchmark_timeout_retries=(
                int(data["max_benchmark_timeout_retries"])
                if data.get("max_benchmark_timeout_retries") is not None
                else None
            ),
            max_benchmark_command_retries=(
                int(data["max_benchmark_command_retries"])
                if data.get("max_benchmark_command_retries") is not None
                else None
            ),
            max_inconclusive_retries=(
                int(data["max_inconclusive_retries"])
                if data.get("max_inconclusive_retries") is not None
                else None
            ),
            no_improvement_limit=(
                int(data["no_improvement_limit"])
                if data.get("no_improvement_limit") is not None
                else None
            ),
            success_count=int(data.get("success_count", 0)),
            failure_count=int(data.get("failure_count", 0)),
            inconclusive_count=int(data.get("inconclusive_count", 0)),
            no_improvement_streak=int(data.get("no_improvement_streak", 0)),
            promoted_count=int(data.get("promoted_count", 0)),
            auto_promote=bool(data.get("auto_promote", False)),
            allow_flaky_promotion=bool(data.get("allow_flaky_promotion", False)),
            auto_promote_min_stage=(
                str(data["auto_promote_min_stage"])
                if data.get("auto_promote_min_stage") is not None
                else None
            ),
            stop_on_first_promotion=bool(data.get("stop_on_first_promotion", False)),
            promotion_target_root=(
                str(data["promotion_target_root"])
                if data.get("promotion_target_root") is not None
                else None
            ),
            next_candidate_index=int(data.get("next_candidate_index", 0)),
            lease_owner=(
                str(data["lease_owner"]) if data.get("lease_owner") is not None else None
            ),
            lease_claimed_at=(
                str(data["lease_claimed_at"])
                if data.get("lease_claimed_at") is not None
                else None
            ),
            lease_heartbeat_at=(
                str(data["lease_heartbeat_at"])
                if data.get("lease_heartbeat_at") is not None
                else None
            ),
            lease_expires_at=(
                str(data["lease_expires_at"])
                if data.get("lease_expires_at") is not None
                else None
            ),
            stop_reason=str(data["stop_reason"]) if data.get("stop_reason") is not None else None,
            candidates=tuple(
                CampaignCandidateRun.from_dict(entry)
                for entry in data.get("candidates", [])
                if isinstance(entry, dict)
            ),
            decision_log=tuple(
                CampaignDecisionLogEntry.from_dict(entry)
                for entry in data.get("decision_log", [])
                if isinstance(entry, dict)
            ),
        )


def create_campaign_run(
    *,
    workspace_id: str,
    track_id: str,
    adapter_id: str,
    stage: str,
    stage_progression_mode: str,
    generator_id: str,
    strategy: str,
    beam_width: int | None,
    beam_group_limit: int | None,
    repeat_count: int | None,
    candidate_source_mode: str,
    target_root: Path,
    config_path: Path | None,
    preset: str | None,
    inline_overrides: list[str],
    intervention_classes: tuple[str, ...],
    preflight_checks: tuple[str, ...],
    preflight_commands: tuple[str, ...],
    preflight_timeout_seconds: int | None,
    generator_metadata: dict[str, str],
    dry_run: bool,
    max_proposals: int | None,
    max_iterations: int | None,
    max_successes: int | None,
    max_promotions: int | None,
    max_failures: int | None,
    max_inconclusive: int | None,
    max_runtime_seconds: int | None,
    max_generation_total_tokens: int | None,
    max_benchmark_total_cost: float | None,
    max_generation_retries: int | None,
    max_generation_timeout_retries: int | None,
    max_generation_provider_retries: int | None,
    max_generation_provider_transport_retries: int | None,
    max_generation_provider_auth_retries: int | None,
    max_generation_provider_rate_limit_retries: int | None,
    max_generation_process_retries: int | None,
    max_preflight_retries: int | None,
    max_execution_retries: int | None,
    max_benchmark_process_retries: int | None,
    max_benchmark_signal_retries: int | None,
    max_benchmark_parse_retries: int | None,
    max_benchmark_adapter_validation_retries: int | None,
    max_benchmark_timeout_retries: int | None,
    max_benchmark_command_retries: int | None,
    max_inconclusive_retries: int | None,
    no_improvement_limit: int | None,
    auto_promote: bool,
    allow_flaky_promotion: bool,
    auto_promote_min_stage: str | None,
    stop_on_first_promotion: bool,
    promotion_target_root: Path | None,
    edit_plan_paths: list[Path],
    execution_mode: str = "foreground",
) -> CampaignRun:
    return CampaignRun(
        format_version="autoharness.campaign_run.v16",
        campaign_run_id=f"campaign_run_{uuid.uuid4().hex[:12]}",
        created_at=_utc_now(),
        updated_at=_utc_now(),
        workspace_id=workspace_id,
        track_id=track_id,
        adapter_id=adapter_id,
        stage=stage,
        initial_stage=stage,
        stage_progression_mode=stage_progression_mode,
        generator_id=generator_id,
        execution_mode=execution_mode,
        desired_state="run",
        status="queued" if execution_mode == "background" else "running",
        strategy=strategy,
        beam_width=beam_width,
        beam_group_limit=beam_group_limit,
        repeat_count=repeat_count,
        candidate_source_mode=candidate_source_mode,
        target_root=str(target_root.resolve()),
        config_path=str(config_path.resolve()) if config_path is not None else None,
        preset=preset,
        inline_overrides=tuple(inline_overrides),
        intervention_classes=intervention_classes,
        preflight_checks=preflight_checks,
        preflight_commands=preflight_commands,
        preflight_timeout_seconds=preflight_timeout_seconds,
        generator_metadata=dict(generator_metadata),
        dry_run=dry_run,
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
        success_count=0,
        failure_count=0,
        inconclusive_count=0,
        no_improvement_streak=0,
        promoted_count=0,
        auto_promote=auto_promote,
        allow_flaky_promotion=allow_flaky_promotion,
        auto_promote_min_stage=auto_promote_min_stage,
        stop_on_first_promotion=stop_on_first_promotion,
        promotion_target_root=(
            str(promotion_target_root.resolve()) if promotion_target_root is not None else None
        ),
        next_candidate_index=0,
        candidates=tuple(
            CampaignCandidateRun(
                index=index,
                edit_plan_path=str(path.resolve()),
                source_mode="manual_edit_plan",
                generation_request={
                    "format_version": "autoharness.proposal_generation_request.v1",
                    "candidate_index": index,
                    "strategy_id": strategy,
                    "source_mode": candidate_source_mode,
                    "input_edit_plan_path": str(path.resolve()),
                },
            )
            for index, path in enumerate(edit_plan_paths)
        ),
        decision_log=(
            CampaignDecisionLogEntry(
                created_at=_utc_now(),
                event="campaign_created",
                details={
                    "strategy": strategy,
                    "beam_width": beam_width,
                    "initial_stage": stage,
                    "stage_progression_mode": stage_progression_mode,
                    "candidate_source_mode": candidate_source_mode,
                    "generator_id": generator_id,
                    "initial_candidate_total": len(edit_plan_paths),
                    "intervention_classes": list(intervention_classes),
                    "generator_metadata": dict(generator_metadata),
                    "auto_promote_min_stage": auto_promote_min_stage,
                },
            ),
        ),
    )


def persist_campaign_run(
    *,
    root: Path,
    campaign: CampaignRun,
) -> Path:
    path = campaign_run_path(
        root=root,
        workspace_id=campaign.workspace_id,
        track_id=campaign.track_id,
        campaign_run_id=campaign.campaign_run_id,
    )
    _write_json(path, campaign.to_dict())
    return path


def _campaign_run_control_path(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    campaign_run_id: str,
) -> Path:
    return campaign_run_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        campaign_run_id=campaign_run_id,
    )


def campaign_lease_is_stale(
    campaign: CampaignRun,
    *,
    now: datetime | None = None,
) -> bool:
    if campaign.lease_expires_at is None:
        return True
    current_time = now or datetime.now(UTC)
    return _parse_utc_timestamp(campaign.lease_expires_at) <= current_time


def claim_campaign_run(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    campaign_run_id: str,
    worker_id: str,
    lease_seconds: int,
) -> CampaignRun | None:
    path = _campaign_run_control_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        campaign_run_id=campaign_run_id,
    )
    with file_lock(path):
        current = load_campaign_run(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            campaign_run_id=campaign_run_id,
        )
        if current.desired_state == "canceled":
            return None
        if current.lease_owner not in {None, worker_id} and not campaign_lease_is_stale(current):
            return None
        now = datetime.now(UTC)
        claimed = replace(
            current,
            updated_at=_utc_now(),
            status="running",
            lease_owner=worker_id,
            lease_claimed_at=current.lease_claimed_at or _utc_now(),
            lease_heartbeat_at=_utc_now(),
            lease_expires_at=(
                now + timedelta(seconds=max(lease_seconds, 1))
            ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        )
        _write_json(path, claimed.to_dict())
        return claimed


def heartbeat_campaign_run(
    *,
    root: Path,
    campaign: CampaignRun,
    worker_id: str,
    lease_seconds: int,
) -> CampaignRun:
    if campaign.lease_owner is not None and campaign.lease_owner != worker_id:
        return campaign
    refreshed = replace(
        campaign,
        updated_at=_utc_now(),
        lease_owner=worker_id,
        lease_claimed_at=campaign.lease_claimed_at or _utc_now(),
        lease_heartbeat_at=_utc_now(),
        lease_expires_at=(
            datetime.now(UTC) + timedelta(seconds=max(lease_seconds, 1))
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    persist_campaign_run(root=root, campaign=refreshed)
    return refreshed


def release_campaign_run(
    *,
    root: Path,
    campaign: CampaignRun,
    final_status: str | None = None,
    stop_reason: str | None = None,
) -> CampaignRun:
    released = replace(
        campaign,
        updated_at=_utc_now(),
        status=final_status or campaign.status,
        stop_reason=stop_reason if stop_reason is not None else campaign.stop_reason,
        lease_owner=None,
        lease_claimed_at=campaign.lease_claimed_at,
        lease_heartbeat_at=None,
        lease_expires_at=None,
    )
    persist_campaign_run(root=root, campaign=released)
    return released


def set_campaign_desired_state(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    campaign_run_id: str,
    desired_state: str,
) -> CampaignRun:
    path = _campaign_run_control_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        campaign_run_id=campaign_run_id,
    )
    with file_lock(path):
        campaign = load_campaign_run(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            campaign_run_id=campaign_run_id,
        )
        next_status = campaign.status
        next_stop_reason = campaign.stop_reason
        if desired_state == "paused" and campaign.status == "queued":
            next_status = "paused"
            next_stop_reason = "pause_requested"
        elif desired_state == "canceled":
            next_status = "canceled"
            next_stop_reason = "cancel_requested"
        updated = replace(
            campaign,
            updated_at=_utc_now(),
            desired_state=desired_state,
            status=next_status,
            stop_reason=next_stop_reason,
        )
        _write_json(path, updated.to_dict())
        return updated


def claim_workspace_campaign_lease(
    *,
    root: Path,
    workspace_id: str,
    worker_id: str,
    lease_seconds: int,
) -> bool:
    path = workspace_campaign_lease_path(root=root, workspace_id=workspace_id)
    with file_lock(path):
        payload = _read_json(path) if path.exists() else {}
        lease_owner = payload.get("lease_owner")
        lease_expires_at = payload.get("lease_expires_at")
        if (
            isinstance(lease_owner, str)
            and lease_owner != worker_id
            and isinstance(lease_expires_at, str)
            and _parse_utc_timestamp(lease_expires_at) > datetime.now(UTC)
        ):
            return False
        now = datetime.now(UTC)
        _write_json(
            path,
            {
                "format_version": "autoharness.workspace_campaign_lease.v1",
                "workspace_id": workspace_id,
                "lease_owner": worker_id,
                "lease_claimed_at": payload.get("lease_claimed_at") or _utc_now(),
                "lease_heartbeat_at": _utc_now(),
                "lease_expires_at": (
                    now + timedelta(seconds=max(lease_seconds, 1))
                ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            },
        )
        return True


def release_workspace_campaign_lease(
    *,
    root: Path,
    workspace_id: str,
    worker_id: str,
) -> None:
    path = workspace_campaign_lease_path(root=root, workspace_id=workspace_id)
    if not path.exists():
        return
    with file_lock(path):
        payload = _read_json(path) if path.exists() else {}
        if payload.get("lease_owner") not in {None, worker_id}:
            return
        path.unlink(missing_ok=True)


def heartbeat_workspace_campaign_lease(
    *,
    root: Path,
    workspace_id: str,
    worker_id: str,
    lease_seconds: int,
) -> None:
    path = workspace_campaign_lease_path(root=root, workspace_id=workspace_id)
    if not path.exists():
        return
    with file_lock(path):
        payload = _read_json(path) if path.exists() else {}
        if payload.get("lease_owner") not in {None, worker_id}:
            return
        _write_json(
            path,
            {
                "format_version": "autoharness.workspace_campaign_lease.v1",
                "workspace_id": workspace_id,
                "lease_owner": worker_id,
                "lease_claimed_at": payload.get("lease_claimed_at") or _utc_now(),
                "lease_heartbeat_at": _utc_now(),
                "lease_expires_at": (
                    datetime.now(UTC) + timedelta(seconds=max(lease_seconds, 1))
                ).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            },
        )


def load_campaign_run(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    campaign_run_id: str,
) -> CampaignRun:
    path = campaign_run_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        campaign_run_id=campaign_run_id,
    )
    if not path.exists():
        raise FileNotFoundError(f"Campaign run not found: {path}")
    return CampaignRun.from_dict(_read_json(path))


def list_track_campaign_runs(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> list[CampaignRun]:
    runs_dir = campaign_runs_dir_path(root=root, workspace_id=workspace_id, track_id=track_id)
    if not runs_dir.exists():
        return []
    return [
        CampaignRun.from_dict(_read_json(path))
        for path in sorted(runs_dir.glob("campaign_run_*.json"))
    ]


def list_runnable_campaign_runs(
    *,
    root: Path,
    workspace_ids: list[str] | None = None,
    track_ids: list[str] | None = None,
) -> list[CampaignRun]:
    if not root.exists():
        return []
    workspace_filter = set(workspace_ids or [])
    track_filter = set(track_ids or [])
    runnable: list[CampaignRun] = []
    for workspace_id in sorted(
        workspace.workspace_id
        for workspace in (
            load_workspace(root, workspace_id)
            for workspace_id in (
                workspace_ids or [path.name for path in sorted(root.iterdir()) if (path / "workspace.json").exists()]
            )
        )
    ):
        workspace = load_workspace(root, workspace_id)
        if workspace_filter and workspace.workspace_id not in workspace_filter:
            continue
        for track_id in sorted(workspace.tracks):
            if track_filter and track_id not in track_filter:
                continue
            for campaign in list_track_campaign_runs(
                root=root,
                workspace_id=workspace.workspace_id,
                track_id=track_id,
            ):
                if campaign.execution_mode != "background":
                    continue
                if campaign.desired_state == "canceled":
                    continue
                if campaign.status not in {"queued", "running", "paused"}:
                    continue
                if campaign.status == "paused":
                    if campaign.desired_state == "paused":
                        continue
                    if campaign.stop_reason != "lease_lost":
                        continue
                runnable.append(campaign)
    status_priority = {
        "queued": 0,
        "paused": 1,
        "running": 2,
    }
    runnable.sort(
        key=lambda campaign: (
            status_priority.get(campaign.status, 99),
            campaign.created_at,
            campaign.campaign_run_id,
        )
    )
    return runnable


def resolve_workspace_campaign_run(
    *,
    root: Path,
    workspace_id: str,
    campaign_run_id: str,
    track_id: str | None = None,
) -> tuple[str, CampaignRun]:
    workspace = load_workspace(root, workspace_id)
    track_ids = [track_id] if track_id is not None else sorted(workspace.tracks)
    matches: list[tuple[str, CampaignRun]] = []
    for current_track_id in track_ids:
        try:
            campaign = load_campaign_run(
                root=root,
                workspace_id=workspace_id,
                track_id=current_track_id,
                campaign_run_id=campaign_run_id,
            )
        except FileNotFoundError:
            continue
        matches.append((current_track_id, campaign))

    if not matches:
        raise FileNotFoundError(
            f"Campaign run `{campaign_run_id}` not found in workspace `{workspace_id}`."
        )
    if len(matches) > 1:
        raise ValueError(
            f"Campaign run id `{campaign_run_id}` is ambiguous in workspace `{workspace_id}`. Specify --track-id."
        )
    return matches[0]
