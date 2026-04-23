"""Workspace and state file models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .autonomy import AutonomyPolicy
from .campaigns import TrackConfig


@dataclass(frozen=True)
class WorkspaceConfig:
    """Umbrella config for one autoharness optimization effort."""

    format_version: str
    workspace_id: str
    objective: str
    domain: str
    active_track_id: str
    created_at: str
    autonomy: AutonomyPolicy
    benchmark_policy: dict[str, object]
    campaign_policy: dict[str, object] = field(default_factory=dict)
    tracks: dict[str, TrackConfig] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["autonomy"] = self.autonomy.to_dict()
        data["tracks"] = {
            track_id: track.to_dict() for track_id, track in self.tracks.items()
        }
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "WorkspaceConfig":
        autonomy_data = data.get("autonomy", {})
        if not isinstance(autonomy_data, dict):
            raise ValueError("`autonomy` must be a mapping in WorkspaceConfig.")
        tracks_data = data.get("tracks", {})
        if not isinstance(tracks_data, dict):
            raise ValueError("`tracks` must be a mapping in WorkspaceConfig.")
        campaign_policy_data = data.get("campaign_policy", {})
        if not isinstance(campaign_policy_data, dict):
            raise ValueError("`campaign_policy` must be a mapping in WorkspaceConfig.")
        return cls(
            format_version=str(data["format_version"]),
            workspace_id=str(data["workspace_id"]),
            objective=str(data["objective"]),
            domain=str(data["domain"]),
            active_track_id=str(data["active_track_id"]),
            created_at=str(data["created_at"]),
            autonomy=AutonomyPolicy(**autonomy_data),
            benchmark_policy=dict(data.get("benchmark_policy", {})),
            campaign_policy=dict(campaign_policy_data),
            tracks={
                track_id: TrackConfig.from_dict(track_data)
                for track_id, track_data in tracks_data.items()
                if isinstance(track_data, dict)
            },
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class WorkspaceState:
    """Operational state for the next meta-agent iteration."""

    format_version: str
    workspace_id: str
    status: str
    active_track_id: str
    next_iteration_index: int = 1
    last_iteration_id: str | None = None
    last_experiment_id: str | None = None
    current_champion_experiment_id: str | None = None
    summary: dict[str, int] = field(
        default_factory=lambda: {
            "iterations_total": 0,
            "tracks_total": 1,
            "active_tracks_total": 1,
            "archived_tracks_total": 0,
            "validation_runs_total": 0,
            "screening_iterations_total": 0,
            "screening_passes_total": 0,
            "screening_failures_total": 0,
            "screening_inconclusive_total": 0,
            "validation_iterations_total": 0,
            "validation_passes_total": 0,
            "validation_failures_total": 0,
            "validation_inconclusive_total": 0,
            "holdout_iterations_total": 0,
            "holdout_passes_total": 0,
            "holdout_failures_total": 0,
            "holdout_inconclusive_total": 0,
            "transfer_iterations_total": 0,
            "transfer_passes_total": 0,
            "transfer_failures_total": 0,
            "transfer_inconclusive_total": 0,
            "validated_candidates": 0,
            "rejected_candidates": 0,
            "inconclusive_candidates": 0,
            "proposal_only_candidates": 0,
            "promotions_total": 0,
        }
    )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "WorkspaceState":
        return cls(
            format_version=str(data["format_version"]),
            workspace_id=str(data["workspace_id"]),
            status=str(data["status"]),
            active_track_id=str(data["active_track_id"]),
            next_iteration_index=int(data.get("next_iteration_index", 1)),
            last_iteration_id=data.get("last_iteration_id"),
            last_experiment_id=data.get("last_experiment_id"),
            current_champion_experiment_id=data.get("current_champion_experiment_id"),
            summary=dict(data.get("summary", {})),
        )
