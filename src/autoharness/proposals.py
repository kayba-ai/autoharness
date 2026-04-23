"""File-backed proposal artifacts for generated or operator-authored candidates."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .tracking import load_workspace, track_dir_path


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected mapping in JSON file: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def proposals_dir_path(*, root: Path, workspace_id: str, track_id: str) -> Path:
    return track_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / "proposals"


def proposal_dir_path(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    proposal_id: str,
) -> Path:
    return proposals_dir_path(root=root, workspace_id=workspace_id, track_id=track_id) / proposal_id


def proposal_manifest_path(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    proposal_id: str,
) -> Path:
    return proposal_dir_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        proposal_id=proposal_id,
    ) / "proposal.json"


@dataclass(frozen=True)
class ProposalRecord:
    """One persisted proposal preview and its execution context."""

    format_version: str
    proposal_id: str
    created_at: str
    workspace_id: str
    track_id: str
    adapter_id: str
    benchmark_name: str
    stage: str
    hypothesis: str
    notes: str
    generator_id: str
    intervention_class: str | None
    summary: str
    generator_metadata: dict[str, Any]
    generation_context: dict[str, Any]
    input_edit_plan_path: str | None
    config_path: str | None
    selected_preset: str | None
    selected_preset_source: str | None
    policy_preset: str | None
    benchmark_target: str | None
    inline_overrides: tuple[str, ...]
    effective_config: dict[str, Any]
    stage_policy: dict[str, Any]
    applied_stage_override: dict[str, Any] | None
    planned_invocation: dict[str, Any]
    target_root: str
    preview_state: str
    operation_count: int
    touched_paths: tuple[str, ...]
    preview_reasons: tuple[str, ...]
    artifact_files: dict[str, str | None]

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "inline_overrides": list(self.inline_overrides),
            "touched_paths": list(self.touched_paths),
            "preview_reasons": list(self.preview_reasons),
            "artifact_files": dict(self.artifact_files),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProposalRecord":
        return cls(
            format_version=str(data["format_version"]),
            proposal_id=str(data["proposal_id"]),
            created_at=str(data["created_at"]),
            workspace_id=str(data["workspace_id"]),
            track_id=str(data["track_id"]),
            adapter_id=str(data["adapter_id"]),
            benchmark_name=str(data["benchmark_name"]),
            stage=str(data["stage"]),
            hypothesis=str(data.get("hypothesis", "")),
            notes=str(data.get("notes", "")),
            generator_id=str(data.get("generator_id", "manual")),
            intervention_class=(
                str(data["intervention_class"])
                if data.get("intervention_class") is not None
                else None
            ),
            summary=str(data.get("summary", "")),
            generator_metadata=dict(data.get("generator_metadata", {})),
            generation_context=dict(data.get("generation_context", {})),
            input_edit_plan_path=(
                str(data["input_edit_plan_path"])
                if data.get("input_edit_plan_path") is not None
                else None
            ),
            config_path=str(data["config_path"]) if data.get("config_path") is not None else None,
            selected_preset=(
                str(data["selected_preset"]) if data.get("selected_preset") is not None else None
            ),
            selected_preset_source=(
                str(data["selected_preset_source"])
                if data.get("selected_preset_source") is not None
                else None
            ),
            policy_preset=(
                str(data["policy_preset"]) if data.get("policy_preset") is not None else None
            ),
            benchmark_target=(
                str(data["benchmark_target"]) if data.get("benchmark_target") is not None else None
            ),
            inline_overrides=tuple(str(entry) for entry in data.get("inline_overrides", [])),
            effective_config=dict(data.get("effective_config", {})),
            stage_policy=dict(data.get("stage_policy", {})),
            applied_stage_override=(
                dict(data["applied_stage_override"])
                if isinstance(data.get("applied_stage_override"), dict)
                else None
            ),
            planned_invocation=dict(data.get("planned_invocation", {})),
            target_root=str(data["target_root"]),
            preview_state=str(data["preview_state"]),
            operation_count=int(data.get("operation_count", 0)),
            touched_paths=tuple(str(entry) for entry in data.get("touched_paths", [])),
            preview_reasons=tuple(str(entry) for entry in data.get("preview_reasons", [])),
            artifact_files={
                str(key): (str(value) if value is not None else None)
                for key, value in dict(data.get("artifact_files", {})).items()
            },
        )


def _next_proposal_id() -> str:
    return f"proposal_{uuid.uuid4().hex[:12]}"


def create_proposal_record(
    *,
    workspace_id: str,
    track_id: str,
    adapter_id: str,
    benchmark_name: str,
    stage: str,
    hypothesis: str,
    notes: str,
    generator_id: str,
    intervention_class: str | None,
    summary: str,
    generator_metadata: dict[str, Any],
    generation_context: dict[str, Any],
    input_edit_plan_path: str | None,
    config_path: str | None,
    selected_preset: str | None,
    selected_preset_source: str | None,
    policy_preset: str | None,
    benchmark_target: str | None,
    inline_overrides: list[str],
    effective_config: dict[str, Any],
    stage_policy: dict[str, Any],
    applied_stage_override: dict[str, Any] | None,
    planned_invocation: dict[str, Any],
    target_root: Path,
    preview_state: str,
    operation_count: int,
    touched_paths: tuple[str, ...],
    preview_reasons: tuple[str, ...],
) -> ProposalRecord:
    return ProposalRecord(
        format_version="autoharness.proposal.v1",
        proposal_id=_next_proposal_id(),
        created_at=_utc_now(),
        workspace_id=workspace_id,
        track_id=track_id,
        adapter_id=adapter_id,
        benchmark_name=benchmark_name,
        stage=stage,
        hypothesis=hypothesis,
        notes=notes,
        generator_id=generator_id,
        intervention_class=intervention_class,
        summary=summary,
        generator_metadata=dict(generator_metadata),
        generation_context=dict(generation_context),
        input_edit_plan_path=input_edit_plan_path,
        config_path=config_path,
        selected_preset=selected_preset,
        selected_preset_source=selected_preset_source,
        policy_preset=policy_preset,
        benchmark_target=benchmark_target,
        inline_overrides=tuple(inline_overrides),
        effective_config=dict(effective_config),
        stage_policy=dict(stage_policy),
        applied_stage_override=(
            dict(applied_stage_override) if isinstance(applied_stage_override, dict) else None
        ),
        planned_invocation=dict(planned_invocation),
        target_root=str(target_root.resolve()),
        preview_state=preview_state,
        operation_count=operation_count,
        touched_paths=touched_paths,
        preview_reasons=preview_reasons,
        artifact_files={},
    )


def persist_proposal(
    *,
    root: Path,
    proposal: ProposalRecord,
    edit_plan_payload: dict[str, Any],
    preview_application_payload: dict[str, Any],
    patch_text: str,
) -> tuple[ProposalRecord, Path]:
    proposal_dir = proposal_dir_path(
        root=root,
        workspace_id=proposal.workspace_id,
        track_id=proposal.track_id,
        proposal_id=proposal.proposal_id,
    )
    proposal_dir.mkdir(parents=True, exist_ok=True)

    artifact_files = {
        "edit_plan": "edit_plan.json",
        "preview_application": "preview_application.json",
        "effective_config": "effective_config.json",
        "candidate_patch": "candidate.patch" if patch_text else None,
    }
    stored_proposal = replace(proposal, artifact_files=artifact_files)
    manifest_path = proposal_dir / "proposal.json"
    _write_json(manifest_path, stored_proposal.to_dict())
    _write_json(proposal_dir / "edit_plan.json", edit_plan_payload)
    _write_json(proposal_dir / "preview_application.json", preview_application_payload)
    _write_json(proposal_dir / "effective_config.json", stored_proposal.effective_config)
    if patch_text:
        (proposal_dir / "candidate.patch").write_text(patch_text, encoding="utf-8")
    return stored_proposal, manifest_path


def resolve_proposal_artifact_paths(
    *,
    root: Path,
    proposal: ProposalRecord,
) -> dict[str, str | None]:
    proposal_dir = proposal_dir_path(
        root=root,
        workspace_id=proposal.workspace_id,
        track_id=proposal.track_id,
        proposal_id=proposal.proposal_id,
    )
    return {
        "proposal_dir": str(proposal_dir),
        "proposal_path": str(proposal_dir / "proposal.json"),
        "edit_plan_path": (
            str(proposal_dir / proposal.artifact_files["edit_plan"])
            if proposal.artifact_files.get("edit_plan") is not None
            else None
        ),
        "preview_application_path": (
            str(proposal_dir / proposal.artifact_files["preview_application"])
            if proposal.artifact_files.get("preview_application") is not None
            else None
        ),
        "effective_config_path": (
            str(proposal_dir / proposal.artifact_files["effective_config"])
            if proposal.artifact_files.get("effective_config") is not None
            else None
        ),
        "patch_path": (
            str(proposal_dir / proposal.artifact_files["candidate_patch"])
            if proposal.artifact_files.get("candidate_patch") is not None
            else None
        ),
    }


def load_proposal(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    proposal_id: str,
) -> ProposalRecord:
    path = proposal_manifest_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
        proposal_id=proposal_id,
    )
    if not path.exists():
        raise FileNotFoundError(f"Proposal not found: {path}")
    return ProposalRecord.from_dict(_read_json(path))


def load_proposal_edit_plan(
    *,
    root: Path,
    proposal: ProposalRecord,
) -> dict[str, Any]:
    artifact_paths = resolve_proposal_artifact_paths(root=root, proposal=proposal)
    edit_plan_path = artifact_paths["edit_plan_path"]
    if edit_plan_path is None:
        raise FileNotFoundError(f"Proposal `{proposal.proposal_id}` does not have an edit-plan artifact.")
    return _read_json(Path(edit_plan_path))


def load_proposal_preview_application(
    *,
    root: Path,
    proposal: ProposalRecord,
) -> dict[str, Any]:
    artifact_paths = resolve_proposal_artifact_paths(root=root, proposal=proposal)
    preview_path = artifact_paths["preview_application_path"]
    if preview_path is None:
        raise FileNotFoundError(
            f"Proposal `{proposal.proposal_id}` does not have a preview-application artifact."
        )
    return _read_json(Path(preview_path))


def load_proposal_effective_config(
    *,
    root: Path,
    proposal: ProposalRecord,
) -> dict[str, Any]:
    artifact_paths = resolve_proposal_artifact_paths(root=root, proposal=proposal)
    effective_config_path = artifact_paths["effective_config_path"]
    if effective_config_path is None:
        return dict(proposal.effective_config)
    return _read_json(Path(effective_config_path))


def list_track_proposals(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
) -> list[ProposalRecord]:
    proposals_dir = proposals_dir_path(root=root, workspace_id=workspace_id, track_id=track_id)
    if not proposals_dir.exists():
        return []
    proposals: list[ProposalRecord] = []
    for path in sorted(proposals_dir.glob("proposal_*")):
        if not path.is_dir():
            continue
        manifest_path = path / "proposal.json"
        if not manifest_path.exists():
            continue
        proposals.append(ProposalRecord.from_dict(_read_json(manifest_path)))
    return proposals


def resolve_workspace_proposal(
    *,
    root: Path,
    workspace_id: str,
    proposal_id: str,
    track_id: str | None = None,
) -> tuple[str, ProposalRecord]:
    workspace = load_workspace(root, workspace_id)
    candidate_track_ids = [track_id] if track_id is not None else sorted(workspace.tracks)
    matches: list[tuple[str, ProposalRecord]] = []
    for current_track_id in candidate_track_ids:
        try:
            proposal = load_proposal(
                root=root,
                workspace_id=workspace_id,
                track_id=current_track_id,
                proposal_id=proposal_id,
            )
        except FileNotFoundError:
            continue
        matches.append((current_track_id, proposal))

    if not matches:
        if track_id is not None:
            raise FileNotFoundError(
                f"Proposal `{proposal_id}` not found in track `{track_id}` for workspace `{workspace_id}`."
            )
        raise FileNotFoundError(f"Proposal `{proposal_id}` not found in workspace `{workspace_id}`.")
    if len(matches) > 1:
        raise ValueError(
            f"Proposal id `{proposal_id}` is ambiguous in workspace `{workspace_id}`. Specify --track-id."
        )
    return matches[0]
