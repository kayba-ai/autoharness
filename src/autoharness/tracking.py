"""File-based tracking for autoharness benchmark runs and iterations."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .campaigns import PromotionPolicy, TrackBenchmarkPolicy, TrackConfig
from .coordination import write_json_atomic
from .workspace import WorkspaceConfig, WorkspaceState


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in JSON file: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    write_json_atomic(path, payload)


def resolve_workspace_dir(root: Path, workspace_id: str) -> Path:
    return root / workspace_id


def workspace_config_path(*, root: Path, workspace_id: str) -> Path:
    return resolve_workspace_dir(root, workspace_id) / "workspace.json"


def track_config_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return resolve_workspace_dir(root, workspace_id) / "tracks" / track_id / "campaign.json"


def track_dir_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return resolve_workspace_dir(root, workspace_id) / "tracks" / track_id


def registry_dir_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return track_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / "registry"


def promotions_dir_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return track_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / "promotions"


def iterations_dir_path(*, root: Path, workspace_id: str) -> Path:
    return resolve_workspace_dir(root, workspace_id) / "iterations"


def iteration_dir_path(*, root: Path, workspace_id: str, iteration_id: str) -> Path:
    return iterations_dir_path(root=root, workspace_id=workspace_id) / iteration_id


def load_workspace(root: Path, workspace_id: str) -> WorkspaceConfig:
    path = workspace_config_path(root=root, workspace_id=workspace_id)
    if not path.exists():
        raise FileNotFoundError(f"Workspace config not found: {path}")
    return WorkspaceConfig.from_dict(_read_json(path))


def promotion_policy_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return track_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / "promotion_policy.json"


def track_policy_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return track_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / "track_policy.json"


def load_workspace_state(root: Path, workspace_id: str) -> WorkspaceState:
    workspace_dir = resolve_workspace_dir(root, workspace_id)
    path = workspace_dir / "state.json"
    if not path.exists():
        raise FileNotFoundError(f"Workspace state not found: {path}")
    return WorkspaceState.from_dict(_read_json(path))


def save_workspace_state(root: Path, workspace_id: str, state: WorkspaceState) -> Path:
    path = resolve_workspace_dir(root, workspace_id) / "state.json"
    _write_json(path, state.to_dict())
    return path


def save_workspace(root: Path, workspace: WorkspaceConfig) -> Path:
    path = workspace_config_path(root=root, workspace_id=workspace.workspace_id)
    _write_json(path, workspace.to_dict())
    return path


def persist_track_config(
    *,
    root: Path,
    workspace_id: str,
    track: TrackConfig,
) -> Path:
    path = track_config_path(root=root, workspace_id=workspace_id, track_id=track.track_id)
    _write_json(path, track.to_dict())
    return path


def persist_workspace_track(
    *,
    root: Path,
    workspace: WorkspaceConfig,
    track_id: str,
) -> dict[str, str]:
    if track_id not in workspace.tracks:
        raise ValueError(f"Unknown track `{track_id}` for workspace `{workspace.workspace_id}`.")
    workspace_path = save_workspace(root, workspace)
    track_path = persist_track_config(
        root=root,
        workspace_id=workspace.workspace_id,
        track=workspace.tracks[track_id],
    )
    return {
        "workspace_path": str(workspace_path),
        "track_path": str(track_path),
    }


def next_iteration_id(state: WorkspaceState) -> str:
    return f"iter_{state.next_iteration_index:04d}"


def _next_record_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class BenchmarkRecord:
    """One file-backed benchmark execution or dry-run record."""

    format_version: str
    record_id: str
    created_at: str
    adapter_id: str
    benchmark_name: str
    stage: str | None
    workspace_id: str | None
    track_id: str | None
    iteration_id: str | None
    dry_run: bool
    status: str
    success: bool | None
    command: list[str]
    workdir: str | None
    config: dict[str, Any]
    payload: dict[str, Any]
    hypothesis: str = ""
    notes: str = ""
    config_path: str | None = None
    source_plan_path: str | None = None
    source_proposal_id: str | None = None
    source_proposal_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkRecord":
        return cls(
            format_version=str(data["format_version"]),
            record_id=str(data["record_id"]),
            created_at=str(data["created_at"]),
            adapter_id=str(data["adapter_id"]),
            benchmark_name=str(data["benchmark_name"]),
            stage=str(data["stage"]) if data.get("stage") is not None else None,
            workspace_id=(
                str(data["workspace_id"]) if data.get("workspace_id") is not None else None
            ),
            track_id=str(data["track_id"]) if data.get("track_id") is not None else None,
            iteration_id=(
                str(data["iteration_id"]) if data.get("iteration_id") is not None else None
            ),
            dry_run=bool(data["dry_run"]),
            status=str(data["status"]),
            success=data.get("success"),
            command=list(data.get("command", [])),
            workdir=str(data["workdir"]) if data.get("workdir") is not None else None,
            config=dict(data.get("config", {})),
            payload=dict(data.get("payload", {})),
            hypothesis=str(data.get("hypothesis", "")),
            notes=str(data.get("notes", "")),
            config_path=(
                str(data["config_path"]) if data.get("config_path") is not None else None
            ),
            source_plan_path=(
                str(data["source_plan_path"])
                if data.get("source_plan_path") is not None
                else None
            ),
            source_proposal_id=(
                str(data["source_proposal_id"])
                if data.get("source_proposal_id") is not None
                else None
            ),
            source_proposal_path=(
                str(data["source_proposal_path"])
                if data.get("source_proposal_path") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class PromotionRecord:
    """One operator-initiated promotion of a recorded candidate."""

    format_version: str
    promotion_id: str
    created_at: str
    workspace_id: str
    track_id: str
    record_id: str
    iteration_id: str | None
    target_root: str
    notes: str
    edit_restore: dict[str, Any]
    parsed_artifact_sources: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromotionRecord":
        return cls(
            format_version=str(data["format_version"]),
            promotion_id=str(data["promotion_id"]),
            created_at=str(data["created_at"]),
            workspace_id=str(data["workspace_id"]),
            track_id=str(data["track_id"]),
            record_id=str(data["record_id"]),
            iteration_id=(
                str(data["iteration_id"]) if data.get("iteration_id") is not None else None
            ),
            target_root=str(data["target_root"]),
            notes=str(data.get("notes", "")),
            edit_restore=(
                dict(data["edit_restore"])
                if isinstance(data.get("edit_restore"), dict)
                else {}
            ),
            parsed_artifact_sources=(
                dict(data["parsed_artifact_sources"])
                if isinstance(data.get("parsed_artifact_sources"), dict)
                else None
            ),
        )


@dataclass(frozen=True)
class ChampionManifest:
    """Track-level pointer to the currently promoted champion."""

    format_version: str
    updated_at: str
    workspace_id: str
    track_id: str
    record_id: str
    promotion_id: str
    iteration_id: str | None
    adapter_id: str
    benchmark_name: str
    stage: str | None
    status: str
    success: bool | None
    hypothesis: str
    notes: str
    target_root: str
    record_path: str
    promotion_path: str
    diff_path: str | None = None
    parsed_artifact_sources_path: str | None = None
    parsed_artifact_sources: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChampionManifest":
        return cls(
            format_version=str(data["format_version"]),
            updated_at=str(data["updated_at"]),
            workspace_id=str(data["workspace_id"]),
            track_id=str(data["track_id"]),
            record_id=str(data["record_id"]),
            promotion_id=str(data["promotion_id"]),
            iteration_id=(
                str(data["iteration_id"]) if data.get("iteration_id") is not None else None
            ),
            adapter_id=str(data["adapter_id"]),
            benchmark_name=str(data["benchmark_name"]),
            stage=str(data["stage"]) if data.get("stage") is not None else None,
            status=str(data["status"]),
            success=data.get("success"),
            hypothesis=str(data.get("hypothesis", "")),
            notes=str(data.get("notes", "")),
            target_root=str(data["target_root"]),
            record_path=str(data["record_path"]),
            promotion_path=str(data["promotion_path"]),
            diff_path=str(data["diff_path"]) if data.get("diff_path") is not None else None,
            parsed_artifact_sources_path=(
                str(data["parsed_artifact_sources_path"])
                if data.get("parsed_artifact_sources_path") is not None
                else None
            ),
            parsed_artifact_sources=(
                dict(data["parsed_artifact_sources"])
                if isinstance(data.get("parsed_artifact_sources"), dict)
                else None
            ),
        )


def create_benchmark_record(
    *,
    adapter_id: str,
    benchmark_name: str,
    config: dict[str, Any],
    payload: dict[str, Any],
    dry_run: bool,
    workspace_id: str | None = None,
    track_id: str | None = None,
    iteration_id: str | None = None,
    hypothesis: str = "",
    notes: str = "",
    config_path: str | None = None,
    source_plan_path: str | None = None,
    source_proposal_id: str | None = None,
    source_proposal_path: str | None = None,
    stage: str | None = None,
) -> BenchmarkRecord:
    status: str
    success: bool | None
    if dry_run:
        status = "dry_run"
        success = None
    else:
        stage_evaluation = payload.get("stage_evaluation")
        if isinstance(stage_evaluation, dict) and isinstance(
            stage_evaluation.get("passed"),
            bool,
        ):
            success = bool(stage_evaluation["passed"])
            status = "success" if success else "failed"
        elif isinstance(stage_evaluation, dict) and stage_evaluation.get("decision") == "inconclusive":
            success = None
            status = "inconclusive"
        else:
            raw_success = payload.get("success")
            success = bool(raw_success) if isinstance(raw_success, bool) else None
            status = "success" if success else "failed"

    command_value = payload.get("command", [])
    command = (
        list(command_value)
        if isinstance(command_value, list)
        else [str(command_value)]
    )

    return BenchmarkRecord(
        format_version="autoharness.benchmark_record.v1",
        record_id=_next_record_id(),
        created_at=_utc_now(),
        adapter_id=adapter_id,
        benchmark_name=benchmark_name,
        stage=stage,
        workspace_id=workspace_id,
        track_id=track_id,
        iteration_id=iteration_id,
        dry_run=dry_run,
        status=status,
        success=success,
        command=command,
        workdir=payload.get("workdir") if isinstance(payload.get("workdir"), str) else None,
        config=dict(config),
        payload=dict(payload),
        hypothesis=hypothesis,
        notes=notes,
        config_path=config_path,
        source_plan_path=source_plan_path,
        source_proposal_id=source_proposal_id,
        source_proposal_path=source_proposal_path,
    )


def persist_benchmark_record(
    *,
    root: Path,
    record: BenchmarkRecord,
) -> Path:
    if not record.workspace_id or not record.track_id:
        raise ValueError("Benchmark records need workspace_id and track_id to persist.")
    registry_dir = registry_dir_path(
        root=root,
        workspace_id=record.workspace_id,
        track_id=record.track_id,
    )
    path = registry_dir / f"{record.record_id}.json"
    _write_json(path, record.to_dict())
    return path


def load_benchmark_record(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    record_id: str,
) -> BenchmarkRecord:
    path = registry_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / f"{record_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Benchmark record not found: {path}")
    return BenchmarkRecord.from_dict(_read_json(path))


def load_promotion_record(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    promotion_id: str,
) -> PromotionRecord:
    path = promotions_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / f"{promotion_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Promotion record not found: {path}")
    return PromotionRecord.from_dict(_read_json(path))


def load_iteration_summary(
    *,
    root: Path,
    workspace_id: str,
    iteration_id: str,
) -> dict[str, Any]:
    path = iteration_dir_path(root=root, workspace_id=workspace_id, iteration_id=iteration_id) / "summary.json"
    if not path.exists():
        raise FileNotFoundError(f"Iteration summary not found: {path}")
    return _read_json(path)


def load_iteration_linked_records(
    *,
    root: Path,
    workspace_id: str,
    iteration_id: str,
) -> dict[str, Any]:
    path = iteration_dir_path(root=root, workspace_id=workspace_id, iteration_id=iteration_id) / "linked_records.json"
    if not path.exists():
        raise FileNotFoundError(f"Iteration linked records not found: {path}")
    return _read_json(path)


def list_workspace_iterations(
    *,
    root: Path,
    workspace_id: str,
) -> list[dict[str, Any]]:
    iterations_dir = iterations_dir_path(root=root, workspace_id=workspace_id)
    if not iterations_dir.exists():
        return []
    iterations: list[dict[str, Any]] = []
    for path in sorted(iterations_dir.glob("iter_*")):
        if not path.is_dir():
            continue
        summary_path = path / "summary.json"
        if not summary_path.exists():
            continue
        summary = _read_json(summary_path)
        summary["iteration_path"] = str(path)
        iterations.append(summary)
    return iterations


def list_track_benchmark_records(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> list[BenchmarkRecord]:
    registry_dir = registry_dir_path(root=root, workspace_id=workspace_id, track_id=track_id)
    if not registry_dir.exists():
        return []
    return [
        BenchmarkRecord.from_dict(_read_json(path))
        for path in sorted(registry_dir.glob("*.json"))
    ]


def list_track_promotion_records(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> list[PromotionRecord]:
    promotions_dir = promotions_dir_path(root=root, workspace_id=workspace_id, track_id=track_id)
    if not promotions_dir.exists():
        return []
    promotions: list[PromotionRecord] = []
    for path in sorted(promotions_dir.glob("promote_*.json")):
        if path.name.endswith(".parsed_artifact_sources.json"):
            continue
        promotions.append(PromotionRecord.from_dict(_read_json(path)))
    return promotions


def load_champion_manifest(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> ChampionManifest:
    path = track_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / "champion.json"
    if not path.exists():
        raise FileNotFoundError(f"Champion manifest not found: {path}")
    return ChampionManifest.from_dict(_read_json(path))


def load_promotion_policy(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> PromotionPolicy:
    path = promotion_policy_path(root=root, workspace_id=workspace_id, track_id=track_id)
    if not path.exists():
        raise FileNotFoundError(f"Promotion policy not found: {path}")
    return PromotionPolicy.from_dict(_read_json(path))


def load_track_policy(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> TrackBenchmarkPolicy:
    path = track_policy_path(root=root, workspace_id=workspace_id, track_id=track_id)
    if not path.exists():
        raise FileNotFoundError(f"Track policy not found: {path}")
    return TrackBenchmarkPolicy.from_dict(_read_json(path))


def persist_promotion_policy(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    policy: PromotionPolicy,
) -> Path:
    path = promotion_policy_path(root=root, workspace_id=workspace_id, track_id=track_id)
    _write_json(path, policy.to_dict())
    return path


def persist_track_policy(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    policy: TrackBenchmarkPolicy,
) -> Path:
    path = track_policy_path(root=root, workspace_id=workspace_id, track_id=track_id)
    _write_json(path, policy.to_dict())
    return path


def resolve_baseline_record(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    state: WorkspaceState | None = None,
    baseline_source: str = "none",
    baseline_record_id: str | None = None,
) -> BenchmarkRecord | None:
    """Resolve one baseline record inside a workspace track."""
    if baseline_record_id and baseline_source != "none":
        raise ValueError(
            "Use either `baseline_record_id` or `baseline_source`, not both."
        )

    if baseline_record_id:
        return load_benchmark_record(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            record_id=baseline_record_id,
        )

    if baseline_source == "none":
        return None
    if baseline_source == "champion":
        if state is None:
            raise ValueError("Workspace state is required to resolve the champion baseline.")
        if not state.current_champion_experiment_id:
            raise FileNotFoundError(
                f"Workspace `{workspace_id}` does not have a current champion record."
            )
        return load_benchmark_record(
            root=root,
            workspace_id=workspace_id,
            track_id=track_id,
            record_id=state.current_champion_experiment_id,
        )

    raise ValueError(f"Unsupported baseline source: {baseline_source}")


def create_promotion_record(
    *,
    workspace_id: str,
    track_id: str,
    record: BenchmarkRecord,
    target_root: Path,
    notes: str,
    edit_restore: dict[str, Any],
) -> PromotionRecord:
    parsed_artifact_sources = record.payload.get("parsed_artifact_sources")
    return PromotionRecord(
        format_version="autoharness.promotion_record.v1",
        promotion_id=f"promote_{uuid.uuid4().hex[:12]}",
        created_at=_utc_now(),
        workspace_id=workspace_id,
        track_id=track_id,
        record_id=record.record_id,
        iteration_id=record.iteration_id,
        target_root=str(target_root.resolve()),
        notes=notes,
        edit_restore=dict(edit_restore),
        parsed_artifact_sources=(
            dict(parsed_artifact_sources)
            if isinstance(parsed_artifact_sources, dict)
            else None
        ),
    )


def persist_promotion_record(
    *,
    root: Path,
    promotion: PromotionRecord,
    diff_text: str = "",
) -> dict[str, str]:
    promotions_dir = promotions_dir_path(
        root=root,
        workspace_id=promotion.workspace_id,
        track_id=promotion.track_id,
    )
    json_path = promotions_dir / f"{promotion.promotion_id}.json"
    _write_json(json_path, promotion.to_dict())
    artifacts = {"promotion_path": str(json_path)}
    if isinstance(promotion.parsed_artifact_sources, dict):
        parsed_artifact_sources_path = (
            promotions_dir / f"{promotion.promotion_id}.parsed_artifact_sources.json"
        )
        _write_json(parsed_artifact_sources_path, promotion.parsed_artifact_sources)
        artifacts["parsed_artifact_sources_path"] = str(parsed_artifact_sources_path)
    if diff_text:
        patch_path = promotions_dir / f"{promotion.promotion_id}.patch"
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(diff_text, encoding="utf-8")
        artifacts["diff_path"] = str(patch_path)
    return artifacts


def persist_champion_manifest(
    *,
    root: Path,
    record: BenchmarkRecord,
    promotion: PromotionRecord,
    promotion_artifacts: dict[str, str],
) -> Path:
    if not record.workspace_id or not record.track_id:
        raise ValueError("Champion manifest requires record workspace_id and track_id.")

    track_dir = resolve_workspace_dir(root, record.workspace_id) / "tracks" / record.track_id
    record_path = track_dir / "registry" / f"{record.record_id}.json"
    if not record_path.exists():
        raise FileNotFoundError(f"Benchmark record not found for champion manifest: {record_path}")

    manifest = ChampionManifest(
        format_version="autoharness.champion_manifest.v1",
        updated_at=_utc_now(),
        workspace_id=record.workspace_id,
        track_id=record.track_id,
        record_id=record.record_id,
        promotion_id=promotion.promotion_id,
        iteration_id=record.iteration_id,
        adapter_id=record.adapter_id,
        benchmark_name=record.benchmark_name,
        stage=record.stage,
        status=record.status,
        success=record.success,
        hypothesis=record.hypothesis,
        notes=promotion.notes or record.notes,
        target_root=promotion.target_root,
        record_path=str(record_path),
        promotion_path=promotion_artifacts["promotion_path"],
        diff_path=promotion_artifacts.get("diff_path"),
        parsed_artifact_sources_path=promotion_artifacts.get("parsed_artifact_sources_path"),
        parsed_artifact_sources=promotion.parsed_artifact_sources,
    )
    champion_path = track_dir / "champion.json"
    _write_json(champion_path, manifest.to_dict())
    return champion_path


def write_iteration_artifacts(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    iteration_id: str,
    record: BenchmarkRecord,
    source_plan_payload: dict[str, Any] | None = None,
    edit_diff_text: str | None = None,
) -> dict[str, str]:
    iteration_dir = resolve_workspace_dir(root, workspace_id) / "iterations" / iteration_id
    iteration_dir.mkdir(parents=True, exist_ok=True)
    edit_application = record.payload.get("edit_application")
    edit_restore = record.payload.get("edit_restore")
    staging = record.payload.get("staging")
    execution_manifest = record.payload.get("execution_manifest")
    cleanup_validation = record.payload.get("cleanup_validation")
    run_environment = record.payload.get("run_environment")
    working_directory_manifest = record.payload.get("working_directory_manifest")
    metrics = record.payload.get("metrics")
    validation_summary = record.payload.get("validation_summary")
    stage_evaluation = record.payload.get("stage_evaluation")
    parsed_artifact_sources = record.payload.get("parsed_artifact_sources")
    config_preset = record.payload.get("config_preset")
    config_preset_source = record.payload.get("config_preset_source")
    policy_preset = record.payload.get("policy_preset")

    summary = {
        "iteration_id": iteration_id,
        "workspace_id": workspace_id,
        "track_id": track_id,
        "record_id": record.record_id,
        "adapter_id": record.adapter_id,
        "benchmark_name": record.benchmark_name,
        "stage": record.stage,
        "created_at": record.created_at,
        "status": record.status,
        "dry_run": record.dry_run,
        "success": record.success,
        "hypothesis": record.hypothesis,
        "notes": record.notes,
    }
    if isinstance(record.source_plan_path, str):
        summary["source_plan_path"] = record.source_plan_path
    if isinstance(record.source_proposal_id, str):
        summary["source_proposal_id"] = record.source_proposal_id
    if isinstance(record.source_proposal_path, str):
        summary["source_proposal_path"] = record.source_proposal_path
    if isinstance(edit_application, dict):
        summary["edit_application"] = edit_application
    if isinstance(edit_restore, dict):
        summary["edit_restore"] = edit_restore
    if isinstance(staging, dict):
        summary["staging"] = staging
    if isinstance(execution_manifest, dict):
        summary["execution_manifest"] = execution_manifest
    if isinstance(cleanup_validation, dict):
        summary["cleanup_validation"] = cleanup_validation
    if isinstance(run_environment, dict):
        summary["run_environment"] = run_environment
    if isinstance(working_directory_manifest, dict):
        summary["working_directory_manifest"] = working_directory_manifest
    if isinstance(metrics, dict):
        summary["metrics"] = metrics
    if isinstance(validation_summary, dict):
        summary["validation_summary"] = validation_summary
    if isinstance(stage_evaluation, dict):
        summary["stage_evaluation"] = stage_evaluation
    if isinstance(parsed_artifact_sources, dict):
        summary["parsed_artifact_sources"] = parsed_artifact_sources
    if isinstance(config_preset, str):
        summary["config_preset"] = config_preset
    if isinstance(config_preset_source, str):
        summary["config_preset_source"] = config_preset_source
    if isinstance(policy_preset, str):
        summary["policy_preset"] = policy_preset
    summary_path = iteration_dir / "summary.json"
    _write_json(summary_path, summary)

    hypothesis_path = iteration_dir / "hypothesis.md"
    hypothesis_path.write_text(
        (
            f"# Hypothesis\n\n"
            f"{record.hypothesis or '(none)'}\n\n"
            f"## Adapter\n\n"
            f"{record.adapter_id}\n\n"
            f"## Benchmark\n\n"
            f"{record.benchmark_name}\n\n"
            f"## Stage\n\n"
            f"{record.stage or '(none)'}\n\n"
            f"## Notes\n\n"
            f"{record.notes or '(none)'}\n"
        ),
        encoding="utf-8",
    )

    linked_records_path = iteration_dir / "linked_records.json"
    _write_json(
        linked_records_path,
        {
            "record_ids": [record.record_id],
            "track_id": track_id,
        },
    )

    artifacts = {
        "summary_path": str(summary_path),
        "hypothesis_path": str(hypothesis_path),
        "linked_records_path": str(linked_records_path),
    }
    if isinstance(source_plan_payload, dict):
        source_plan_artifact_path = iteration_dir / "source_plan.json"
        _write_json(source_plan_artifact_path, source_plan_payload)
        artifacts["source_plan_artifact_path"] = str(source_plan_artifact_path)
    if isinstance(edit_application, dict):
        edit_application_path = iteration_dir / "edit_application.json"
        _write_json(edit_application_path, edit_application)
        artifacts["edit_application_path"] = str(edit_application_path)
    if isinstance(edit_restore, dict):
        edit_restore_path = iteration_dir / "edit_restore.json"
        _write_json(edit_restore_path, edit_restore)
        artifacts["edit_restore_path"] = str(edit_restore_path)
    if isinstance(staging, dict):
        staging_path = iteration_dir / "staging.json"
        _write_json(staging_path, staging)
        artifacts["staging_path"] = str(staging_path)
    if isinstance(execution_manifest, dict):
        execution_manifest_path = iteration_dir / "execution_manifest.json"
        _write_json(execution_manifest_path, execution_manifest)
        artifacts["execution_manifest_path"] = str(execution_manifest_path)
    if isinstance(cleanup_validation, dict):
        cleanup_validation_path = iteration_dir / "cleanup_validation.json"
        _write_json(cleanup_validation_path, cleanup_validation)
        artifacts["cleanup_validation_path"] = str(cleanup_validation_path)
    if isinstance(run_environment, dict):
        run_environment_path = iteration_dir / "run_environment.json"
        _write_json(run_environment_path, run_environment)
        artifacts["run_environment_path"] = str(run_environment_path)
    if isinstance(working_directory_manifest, dict):
        working_directory_manifest_path = iteration_dir / "working_directory_manifest.json"
        _write_json(working_directory_manifest_path, working_directory_manifest)
        artifacts["working_directory_manifest_path"] = str(working_directory_manifest_path)
    if isinstance(parsed_artifact_sources, dict):
        parsed_artifact_sources_path = iteration_dir / "parsed_artifact_sources.json"
        _write_json(parsed_artifact_sources_path, parsed_artifact_sources)
        artifacts["parsed_artifact_sources_path"] = str(parsed_artifact_sources_path)
    if edit_diff_text:
        diff_path = iteration_dir / "candidate.patch"
        diff_path.write_text(edit_diff_text, encoding="utf-8")
        artifacts["edit_diff_path"] = str(diff_path)

    return artifacts


def update_state_after_iteration(
    *,
    root: Path,
    workspace_id: str,
    state: WorkspaceState,
    record: BenchmarkRecord,
    iteration_id: str,
) -> WorkspaceState:
    summary = dict(state.summary)
    summary["iterations_total"] = int(summary.get("iterations_total", 0)) + 1
    if record.dry_run:
        summary["proposal_only_candidates"] = int(
            summary.get("proposal_only_candidates", 0)
        ) + 1
    elif record.success:
        summary["validated_candidates"] = int(
            summary.get("validated_candidates", 0)
        ) + 1
    else:
        if record.status == "inconclusive":
            summary["inconclusive_candidates"] = int(
                summary.get("inconclusive_candidates", 0)
            ) + 1
        else:
            summary["rejected_candidates"] = int(
                summary.get("rejected_candidates", 0)
            ) + 1
    validation_run_count = record.payload.get("validation_run_count")
    if isinstance(validation_run_count, int) and validation_run_count > 0:
        summary["validation_runs_total"] = int(
            summary.get("validation_runs_total", 0)
        ) + validation_run_count
    if record.stage:
        summary[f"{record.stage}_iterations_total"] = int(
            summary.get(f"{record.stage}_iterations_total", 0)
        ) + 1
        if record.dry_run:
            summary[f"{record.stage}_planned_total"] = int(
                summary.get(f"{record.stage}_planned_total", 0)
            ) + 1
        elif record.success:
            summary[f"{record.stage}_passes_total"] = int(
                summary.get(f"{record.stage}_passes_total", 0)
            ) + 1
        else:
            if record.status == "inconclusive":
                summary[f"{record.stage}_inconclusive_total"] = int(
                    summary.get(f"{record.stage}_inconclusive_total", 0)
                ) + 1
            else:
                summary[f"{record.stage}_failures_total"] = int(
                    summary.get(f"{record.stage}_failures_total", 0)
                ) + 1

    next_state = WorkspaceState(
        format_version=state.format_version,
        workspace_id=state.workspace_id,
        status=state.status,
        active_track_id=state.active_track_id,
        next_iteration_index=state.next_iteration_index + 1,
        last_iteration_id=iteration_id,
        last_experiment_id=record.record_id,
        current_champion_experiment_id=state.current_champion_experiment_id,
        summary=summary,
    )
    save_workspace_state(root, workspace_id, next_state)
    return next_state


def update_state_after_promotion(
    *,
    root: Path,
    workspace_id: str,
    state: WorkspaceState,
    record_id: str,
) -> WorkspaceState:
    summary = dict(state.summary)
    summary["promotions_total"] = int(summary.get("promotions_total", 0)) + 1
    next_state = WorkspaceState(
        format_version=state.format_version,
        workspace_id=state.workspace_id,
        status=state.status,
        active_track_id=state.active_track_id,
        next_iteration_index=state.next_iteration_index,
        last_iteration_id=state.last_iteration_id,
        last_experiment_id=state.last_experiment_id,
        current_champion_experiment_id=record_id,
        summary=summary,
    )
    save_workspace_state(root, workspace_id, next_state)
    return next_state
