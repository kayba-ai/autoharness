"""Listing query helpers for iterations, records, promotions, and proposals."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .proposals import list_track_proposals, resolve_proposal_artifact_paths
from .tracking import (
    iteration_dir_path,
    list_track_benchmark_records,
    list_track_promotion_records,
    list_workspace_iterations,
    load_workspace,
    promotions_dir_path,
    registry_dir_path,
)


def _parse_iso_datetime_value(
    raw: str,
    *,
    display_name: str,
    end_of_day: bool = False,
) -> datetime:
    value = raw.strip()
    if not value:
        raise SystemExit(f"{display_name} must not be empty.")

    is_date_only = len(value) == 10 and value.count("-") == 2 and "T" not in value and " " not in value
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise SystemExit(
            f"Invalid {display_name} value `{raw}`. Use YYYY-MM-DD or an ISO 8601 timestamp."
        ) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)

    if is_date_only and end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    return parsed


def _parse_casefolded_substring_filter(
    raw: str | None,
    *,
    display_name: str,
) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        raise SystemExit(f"{display_name} must not be empty.")
    return value.casefold()


@dataclass(frozen=True)
class IterationQuerySpec:
    track_id: str | None = None
    stage: str | None = None
    status: str | None = None
    benchmark_name: str | None = None
    adapter_id: str | None = None
    hypothesis_contains: str | None = None
    notes_contains: str | None = None
    sort_by: str = "iteration_id"
    descending: bool = False
    since: str | None = None
    until: str | None = None
    saved_plan_only: bool = False
    limit: int | None = None

    @classmethod
    def from_args(
        cls,
        args: argparse.Namespace,
        *,
        resolved_track_id: str | None = None,
    ) -> "IterationQuerySpec":
        return cls(
            track_id=resolved_track_id if resolved_track_id is not None else getattr(args, "track_id", None),
            stage=getattr(args, "stage", None),
            status=getattr(args, "status", None),
            benchmark_name=getattr(args, "benchmark_name", None),
            adapter_id=getattr(args, "adapter_id", None),
            hypothesis_contains=getattr(args, "hypothesis_contains", None),
            notes_contains=getattr(args, "notes_contains", None),
            sort_by=getattr(args, "sort_by", "iteration_id"),
            descending=getattr(args, "descending", False),
            since=getattr(args, "since", None),
            until=getattr(args, "until", None),
            saved_plan_only=getattr(args, "saved_plan_only", False),
            limit=getattr(args, "limit", None),
        )

    def rendered_filters(self) -> dict[str, object]:
        return {
            "track_id": self.track_id,
            "stage": self.stage,
            "status": self.status,
            "benchmark_name": self.benchmark_name,
            "adapter_id": self.adapter_id,
            "hypothesis_contains": self.hypothesis_contains,
            "notes_contains": self.notes_contains,
            "sort_by": self.sort_by,
            "descending": self.descending,
            "since": self.since,
            "until": self.until,
            "saved_plan_only": self.saved_plan_only,
        }


@dataclass(frozen=True)
class RecordQuerySpec:
    track_id: str | None = None
    stage: str | None = None
    status: str | None = None
    benchmark_name: str | None = None
    adapter_id: str | None = None
    hypothesis_contains: str | None = None
    notes_contains: str | None = None
    sort_by: str = "record_id"
    descending: bool = False
    since: str | None = None
    until: str | None = None
    saved_plan_only: bool = False
    limit: int | None = None

    @classmethod
    def from_args(
        cls,
        args: argparse.Namespace,
        *,
        resolved_track_id: str | None = None,
    ) -> "RecordQuerySpec":
        return cls(
            track_id=resolved_track_id if resolved_track_id is not None else getattr(args, "track_id", None),
            stage=getattr(args, "stage", None),
            status=getattr(args, "status", None),
            benchmark_name=getattr(args, "benchmark_name", None),
            adapter_id=getattr(args, "adapter_id", None),
            hypothesis_contains=getattr(args, "hypothesis_contains", None),
            notes_contains=getattr(args, "notes_contains", None),
            sort_by=getattr(args, "sort_by", "record_id"),
            descending=getattr(args, "descending", False),
            since=getattr(args, "since", None),
            until=getattr(args, "until", None),
            saved_plan_only=getattr(args, "saved_plan_only", False),
            limit=getattr(args, "limit", None),
        )

    def rendered_filters(self) -> dict[str, object]:
        return {
            "track_id": self.track_id,
            "stage": self.stage,
            "status": self.status,
            "benchmark_name": self.benchmark_name,
            "adapter_id": self.adapter_id,
            "hypothesis_contains": self.hypothesis_contains,
            "notes_contains": self.notes_contains,
            "sort_by": self.sort_by,
            "descending": self.descending,
            "since": self.since,
            "until": self.until,
            "saved_plan_only": self.saved_plan_only,
        }


@dataclass(frozen=True)
class PromotionQuerySpec:
    track_id: str | None = None
    record_id: str | None = None
    iteration_id: str | None = None
    target_root_contains: str | None = None
    notes_contains: str | None = None
    sort_by: str = "promotion_id"
    descending: bool = False
    since: str | None = None
    until: str | None = None
    parsed_artifact_sources_only: bool = False
    limit: int | None = None

    @classmethod
    def from_args(
        cls,
        args: argparse.Namespace,
        *,
        resolved_track_id: str | None = None,
    ) -> "PromotionQuerySpec":
        return cls(
            track_id=resolved_track_id if resolved_track_id is not None else getattr(args, "track_id", None),
            record_id=getattr(args, "record_id", None),
            iteration_id=getattr(args, "iteration_id", None),
            target_root_contains=getattr(args, "target_root_contains", None),
            notes_contains=getattr(args, "notes_contains", None),
            sort_by=getattr(args, "sort_by", "promotion_id"),
            descending=getattr(args, "descending", False),
            since=getattr(args, "since", None),
            until=getattr(args, "until", None),
            parsed_artifact_sources_only=getattr(args, "parsed_artifact_sources_only", False),
            limit=getattr(args, "limit", None),
        )

    def rendered_filters(self) -> dict[str, object]:
        return {
            "track_id": self.track_id,
            "record_id": self.record_id,
            "iteration_id": self.iteration_id,
            "target_root_contains": self.target_root_contains,
            "notes_contains": self.notes_contains,
            "sort_by": self.sort_by,
            "descending": self.descending,
            "since": self.since,
            "until": self.until,
            "parsed_artifact_sources_only": self.parsed_artifact_sources_only,
        }


@dataclass(frozen=True)
class ProposalQuerySpec:
    track_id: str | None = None
    stage: str | None = None
    adapter_id: str | None = None
    hypothesis_contains: str | None = None
    notes_contains: str | None = None
    sort_by: str = "proposal_id"
    descending: bool = False
    since: str | None = None
    until: str | None = None
    limit: int | None = None

    @classmethod
    def from_args(
        cls,
        args: argparse.Namespace,
        *,
        resolved_track_id: str | None = None,
    ) -> "ProposalQuerySpec":
        return cls(
            track_id=resolved_track_id if resolved_track_id is not None else getattr(args, "track_id", None),
            stage=getattr(args, "stage", None),
            adapter_id=getattr(args, "adapter_id", None),
            hypothesis_contains=getattr(args, "hypothesis_contains", None),
            notes_contains=getattr(args, "notes_contains", None),
            sort_by=getattr(args, "sort_by", "proposal_id"),
            descending=getattr(args, "descending", False),
            since=getattr(args, "since", None),
            until=getattr(args, "until", None),
            limit=getattr(args, "limit", None),
        )

    def rendered_filters(self) -> dict[str, object]:
        return {
            "track_id": self.track_id,
            "stage": self.stage,
            "adapter_id": self.adapter_id,
            "hypothesis_contains": self.hypothesis_contains,
            "notes_contains": self.notes_contains,
            "sort_by": self.sort_by,
            "descending": self.descending,
            "since": self.since,
            "until": self.until,
        }


def _render_iteration_listing_item(
    *,
    summary: dict[str, object],
    last_iteration_id: str | None,
) -> dict[str, object]:
    source_plan_path = (
        str(summary["source_plan_path"])
        if isinstance(summary.get("source_plan_path"), str)
        else None
    )
    source_plan_artifact_path = None
    if isinstance(summary.get("iteration_path"), str):
        candidate_source_plan_path = Path(summary["iteration_path"]) / "source_plan.json"
        if candidate_source_plan_path.exists():
            source_plan_artifact_path = str(candidate_source_plan_path)
    saved_plan_run = source_plan_path is not None or source_plan_artifact_path is not None
    return {
        "iteration_id": summary.get("iteration_id"),
        "track_id": summary.get("track_id"),
        "record_id": summary.get("record_id"),
        "adapter_id": summary.get("adapter_id"),
        "benchmark_name": summary.get("benchmark_name"),
        "stage": summary.get("stage"),
        "created_at": summary.get("created_at"),
        "hypothesis": summary.get("hypothesis"),
        "notes": summary.get("notes"),
        "status": summary.get("status"),
        "success": summary.get("success"),
        "dry_run": summary.get("dry_run"),
        "last_iteration": summary.get("iteration_id") == last_iteration_id,
        "saved_plan_run": saved_plan_run,
        "source_plan_path": source_plan_path,
        "source_plan_artifact_path": source_plan_artifact_path,
        "iteration_path": summary.get("iteration_path"),
    }


def _render_proposal_listing_item(
    *,
    root: Path,
    proposal,
) -> dict[str, object]:
    artifact_paths = resolve_proposal_artifact_paths(root=root, proposal=proposal)
    return {
        "proposal_id": proposal.proposal_id,
        "created_at": proposal.created_at,
        "track_id": proposal.track_id,
        "adapter_id": proposal.adapter_id,
        "benchmark_name": proposal.benchmark_name,
        "stage": proposal.stage,
        "hypothesis": proposal.hypothesis,
        "notes": proposal.notes,
        "generator_id": proposal.generator_id,
        "preview_state": proposal.preview_state,
        "operation_count": proposal.operation_count,
        "target_root": proposal.target_root,
        "proposal_path": artifact_paths["proposal_path"],
        "patch_path": artifact_paths["patch_path"],
    }


def query_workspace_iteration_items(
    *,
    root: Path,
    workspace_id: str,
    last_iteration_id: str | None,
    spec: IterationQuerySpec | None = None,
) -> tuple[list[dict[str, object]], int]:
    resolved_spec = spec or IterationQuerySpec()
    since_timestamp = (
        _parse_iso_datetime_value(
            resolved_spec.since,
            display_name="`--since`",
        )
        if resolved_spec.since is not None
        else None
    )
    until_timestamp = (
        _parse_iso_datetime_value(
            resolved_spec.until,
            display_name="`--until`",
            end_of_day=True,
        )
        if resolved_spec.until is not None
        else None
    )
    if (
        since_timestamp is not None
        and until_timestamp is not None
        and since_timestamp > until_timestamp
    ):
        raise SystemExit("`--since` must be earlier than or equal to `--until`.")

    hypothesis_filter = _parse_casefolded_substring_filter(
        resolved_spec.hypothesis_contains,
        display_name="`--hypothesis-contains`",
    )
    notes_filter = _parse_casefolded_substring_filter(
        resolved_spec.notes_contains,
        display_name="`--notes-contains`",
    )

    rendered_items = [
        _render_iteration_listing_item(
            summary=summary,
            last_iteration_id=last_iteration_id,
        )
        for summary in list_workspace_iterations(
            root=root,
            workspace_id=workspace_id,
        )
    ]

    if resolved_spec.track_id is not None:
        rendered_items = [item for item in rendered_items if item["track_id"] == resolved_spec.track_id]
    if resolved_spec.stage is not None:
        rendered_items = [item for item in rendered_items if item["stage"] == resolved_spec.stage]
    if resolved_spec.status is not None:
        rendered_items = [item for item in rendered_items if item["status"] == resolved_spec.status]
    if resolved_spec.benchmark_name is not None:
        rendered_items = [
            item for item in rendered_items if item["benchmark_name"] == resolved_spec.benchmark_name
        ]
    if resolved_spec.adapter_id is not None:
        rendered_items = [item for item in rendered_items if item["adapter_id"] == resolved_spec.adapter_id]
    if hypothesis_filter is not None:
        rendered_items = [
            item
            for item in rendered_items
            if hypothesis_filter in str(item.get("hypothesis") or "").casefold()
        ]
    if notes_filter is not None:
        rendered_items = [
            item
            for item in rendered_items
            if notes_filter in str(item.get("notes") or "").casefold()
        ]
    if since_timestamp is not None:
        rendered_items = [
            item
            for item in rendered_items
            if _parse_iso_datetime_value(
                str(item["created_at"]),
                display_name="iteration `created_at`",
            )
            >= since_timestamp
        ]
    if until_timestamp is not None:
        rendered_items = [
            item
            for item in rendered_items
            if _parse_iso_datetime_value(
                str(item["created_at"]),
                display_name="iteration `created_at`",
            )
            <= until_timestamp
        ]

    if resolved_spec.sort_by == "created_at":
        rendered_items.sort(
            key=lambda item: (
                _parse_iso_datetime_value(
                    str(item["created_at"]),
                    display_name="iteration `created_at`",
                ),
                str(item["iteration_id"]),
            ),
            reverse=resolved_spec.descending,
        )
    else:
        rendered_items.sort(
            key=lambda item: str(item["iteration_id"]),
            reverse=resolved_spec.descending,
        )

    saved_plan_iterations_total = sum(1 for item in rendered_items if item["saved_plan_run"])
    if resolved_spec.saved_plan_only:
        rendered_items = [item for item in rendered_items if item["saved_plan_run"]]
    if resolved_spec.limit is not None:
        if resolved_spec.descending:
            rendered_items = rendered_items[: resolved_spec.limit]
        else:
            rendered_items = rendered_items[-resolved_spec.limit :]
    return rendered_items, saved_plan_iterations_total


def query_workspace_proposal_items(
    *,
    root: Path,
    workspace_id: str,
    spec: ProposalQuerySpec | None = None,
) -> tuple[list[dict[str, object]], int]:
    resolved_spec = spec or ProposalQuerySpec()
    workspace = load_workspace(root, workspace_id)

    since_timestamp = (
        _parse_iso_datetime_value(
            resolved_spec.since,
            display_name="`--since`",
        )
        if resolved_spec.since is not None
        else None
    )
    until_timestamp = (
        _parse_iso_datetime_value(
            resolved_spec.until,
            display_name="`--until`",
            end_of_day=True,
        )
        if resolved_spec.until is not None
        else None
    )
    if (
        since_timestamp is not None
        and until_timestamp is not None
        and since_timestamp > until_timestamp
    ):
        raise SystemExit("`--since` must be earlier than or equal to `--until`.")

    hypothesis_filter = _parse_casefolded_substring_filter(
        resolved_spec.hypothesis_contains,
        display_name="`--hypothesis-contains`",
    )
    notes_filter = _parse_casefolded_substring_filter(
        resolved_spec.notes_contains,
        display_name="`--notes-contains`",
    )

    track_ids = (
        [resolved_spec.track_id]
        if resolved_spec.track_id is not None
        else sorted(workspace.tracks)
    )
    rendered_items = []
    for track_id in track_ids:
        rendered_items.extend(
            _render_proposal_listing_item(root=root, proposal=proposal)
            for proposal in list_track_proposals(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
        )

    if resolved_spec.stage is not None:
        rendered_items = [item for item in rendered_items if item["stage"] == resolved_spec.stage]
    if resolved_spec.adapter_id is not None:
        rendered_items = [item for item in rendered_items if item["adapter_id"] == resolved_spec.adapter_id]
    if hypothesis_filter is not None:
        rendered_items = [
            item
            for item in rendered_items
            if hypothesis_filter in str(item.get("hypothesis") or "").casefold()
        ]
    if notes_filter is not None:
        rendered_items = [
            item
            for item in rendered_items
            if notes_filter in str(item.get("notes") or "").casefold()
        ]
    if since_timestamp is not None:
        rendered_items = [
            item
            for item in rendered_items
            if _parse_iso_datetime_value(
                str(item["created_at"]),
                display_name="proposal `created_at`",
            )
            >= since_timestamp
        ]
    if until_timestamp is not None:
        rendered_items = [
            item
            for item in rendered_items
            if _parse_iso_datetime_value(
                str(item["created_at"]),
                display_name="proposal `created_at`",
            )
            <= until_timestamp
        ]

    if resolved_spec.sort_by == "created_at":
        rendered_items.sort(
            key=lambda item: (
                _parse_iso_datetime_value(
                    str(item["created_at"]),
                    display_name="proposal `created_at`",
                ),
                str(item["proposal_id"]),
            ),
            reverse=resolved_spec.descending,
        )
    else:
        rendered_items.sort(
            key=lambda item: str(item["proposal_id"]),
            reverse=resolved_spec.descending,
        )

    non_executable_proposals_total = sum(
        1 for item in rendered_items if item["preview_state"] != "preview"
    )
    if resolved_spec.limit is not None:
        if resolved_spec.descending:
            rendered_items = rendered_items[: resolved_spec.limit]
        else:
            rendered_items = rendered_items[-resolved_spec.limit :]
    return rendered_items, non_executable_proposals_total


def _render_record_listing_item(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    record,
) -> dict[str, object]:
    source_plan_artifact_path = None
    if record.iteration_id is not None:
        candidate_source_plan_path = (
            iteration_dir_path(
                root=root,
                workspace_id=workspace_id,
                iteration_id=record.iteration_id,
            )
            / "source_plan.json"
        )
        if candidate_source_plan_path.exists():
            source_plan_artifact_path = str(candidate_source_plan_path)
    saved_plan_run = (
        record.source_plan_path is not None or source_plan_artifact_path is not None
    )
    return {
        "record_id": record.record_id,
        "created_at": record.created_at,
        "track_id": track_id,
        "iteration_id": record.iteration_id,
        "adapter_id": record.adapter_id,
        "benchmark_name": record.benchmark_name,
        "stage": record.stage,
        "status": record.status,
        "success": record.success,
        "dry_run": record.dry_run,
        "hypothesis": record.hypothesis,
        "notes": record.notes,
        "saved_plan_run": saved_plan_run,
        "source_plan_path": record.source_plan_path,
        "source_plan_artifact_path": source_plan_artifact_path,
        "record_path": str(
            registry_dir_path(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
            / f"{record.record_id}.json"
        ),
    }


def query_workspace_record_items(
    *,
    root: Path,
    workspace_id: str,
    spec: RecordQuerySpec | None = None,
) -> tuple[list[dict[str, object]], int]:
    resolved_spec = spec or RecordQuerySpec()
    workspace = load_workspace(root, workspace_id)

    since_timestamp = (
        _parse_iso_datetime_value(
            resolved_spec.since,
            display_name="`--since`",
        )
        if resolved_spec.since is not None
        else None
    )
    until_timestamp = (
        _parse_iso_datetime_value(
            resolved_spec.until,
            display_name="`--until`",
            end_of_day=True,
        )
        if resolved_spec.until is not None
        else None
    )
    if (
        since_timestamp is not None
        and until_timestamp is not None
        and since_timestamp > until_timestamp
    ):
        raise SystemExit("`--since` must be earlier than or equal to `--until`.")

    hypothesis_filter = _parse_casefolded_substring_filter(
        resolved_spec.hypothesis_contains,
        display_name="`--hypothesis-contains`",
    )
    notes_filter = _parse_casefolded_substring_filter(
        resolved_spec.notes_contains,
        display_name="`--notes-contains`",
    )

    track_ids = (
        [resolved_spec.track_id]
        if resolved_spec.track_id is not None
        else sorted(workspace.tracks)
    )
    rendered_items = []
    for track_id in track_ids:
        rendered_items.extend(
            _render_record_listing_item(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
                record=record,
            )
            for record in list_track_benchmark_records(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
        )

    if resolved_spec.stage is not None:
        rendered_items = [item for item in rendered_items if item["stage"] == resolved_spec.stage]
    if resolved_spec.status is not None:
        rendered_items = [item for item in rendered_items if item["status"] == resolved_spec.status]
    if resolved_spec.benchmark_name is not None:
        rendered_items = [
            item for item in rendered_items if item["benchmark_name"] == resolved_spec.benchmark_name
        ]
    if resolved_spec.adapter_id is not None:
        rendered_items = [item for item in rendered_items if item["adapter_id"] == resolved_spec.adapter_id]
    if hypothesis_filter is not None:
        rendered_items = [
            item
            for item in rendered_items
            if hypothesis_filter in str(item.get("hypothesis") or "").casefold()
        ]
    if notes_filter is not None:
        rendered_items = [
            item
            for item in rendered_items
            if notes_filter in str(item.get("notes") or "").casefold()
        ]
    if since_timestamp is not None:
        rendered_items = [
            item
            for item in rendered_items
            if _parse_iso_datetime_value(
                str(item["created_at"]),
                display_name="record `created_at`",
            )
            >= since_timestamp
        ]
    if until_timestamp is not None:
        rendered_items = [
            item
            for item in rendered_items
            if _parse_iso_datetime_value(
                str(item["created_at"]),
                display_name="record `created_at`",
            )
            <= until_timestamp
        ]

    if resolved_spec.sort_by == "created_at":
        rendered_items.sort(
            key=lambda item: (
                _parse_iso_datetime_value(
                    str(item["created_at"]),
                    display_name="record `created_at`",
                ),
                str(item["record_id"]),
            ),
            reverse=resolved_spec.descending,
        )
    else:
        rendered_items.sort(
            key=lambda item: str(item["record_id"]),
            reverse=resolved_spec.descending,
        )

    saved_plan_records_total = sum(1 for item in rendered_items if item["saved_plan_run"])
    if resolved_spec.saved_plan_only:
        rendered_items = [item for item in rendered_items if item["saved_plan_run"]]
    if resolved_spec.limit is not None:
        if resolved_spec.descending:
            rendered_items = rendered_items[: resolved_spec.limit]
        else:
            rendered_items = rendered_items[-resolved_spec.limit :]
    return rendered_items, saved_plan_records_total


def _render_promotion_listing_item(
    *,
    root: Path,
    workspace_id: str,
    track_id: str,
    promotion,
) -> dict[str, object]:
    promotions_dir = promotions_dir_path(
        root=root,
        workspace_id=workspace_id,
        track_id=track_id,
    )
    promotion_path = promotions_dir / f"{promotion.promotion_id}.json"
    parsed_artifact_sources_path = (
        promotions_dir / f"{promotion.promotion_id}.parsed_artifact_sources.json"
    )
    diff_path = promotions_dir / f"{promotion.promotion_id}.patch"
    return {
        "promotion_id": promotion.promotion_id,
        "created_at": promotion.created_at,
        "track_id": track_id,
        "record_id": promotion.record_id,
        "iteration_id": promotion.iteration_id,
        "target_root": promotion.target_root,
        "notes": promotion.notes,
        "has_parsed_artifact_sources": parsed_artifact_sources_path.exists(),
        "promotion_path": str(promotion_path),
        "parsed_artifact_sources_path": (
            str(parsed_artifact_sources_path)
            if parsed_artifact_sources_path.exists()
            else None
        ),
        "diff_path": str(diff_path) if diff_path.exists() else None,
    }


def query_workspace_promotion_items(
    *,
    root: Path,
    workspace_id: str,
    spec: PromotionQuerySpec | None = None,
) -> tuple[list[dict[str, object]], int]:
    resolved_spec = spec or PromotionQuerySpec()
    workspace = load_workspace(root, workspace_id)

    since_timestamp = (
        _parse_iso_datetime_value(
            resolved_spec.since,
            display_name="`--since`",
        )
        if resolved_spec.since is not None
        else None
    )
    until_timestamp = (
        _parse_iso_datetime_value(
            resolved_spec.until,
            display_name="`--until`",
            end_of_day=True,
        )
        if resolved_spec.until is not None
        else None
    )
    if (
        since_timestamp is not None
        and until_timestamp is not None
        and since_timestamp > until_timestamp
    ):
        raise SystemExit("`--since` must be earlier than or equal to `--until`.")

    target_root_filter = _parse_casefolded_substring_filter(
        resolved_spec.target_root_contains,
        display_name="`--target-root-contains`",
    )
    notes_filter = _parse_casefolded_substring_filter(
        resolved_spec.notes_contains,
        display_name="`--notes-contains`",
    )

    track_ids = (
        [resolved_spec.track_id]
        if resolved_spec.track_id is not None
        else sorted(workspace.tracks)
    )
    rendered_items = []
    for track_id in track_ids:
        rendered_items.extend(
            _render_promotion_listing_item(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
                promotion=promotion,
            )
            for promotion in list_track_promotion_records(
                root=root,
                workspace_id=workspace_id,
                track_id=track_id,
            )
        )

    if resolved_spec.record_id is not None:
        rendered_items = [item for item in rendered_items if item["record_id"] == resolved_spec.record_id]
    if resolved_spec.iteration_id is not None:
        rendered_items = [item for item in rendered_items if item["iteration_id"] == resolved_spec.iteration_id]
    if target_root_filter is not None:
        rendered_items = [
            item
            for item in rendered_items
            if target_root_filter in str(item.get("target_root") or "").casefold()
        ]
    if notes_filter is not None:
        rendered_items = [
            item
            for item in rendered_items
            if notes_filter in str(item.get("notes") or "").casefold()
        ]
    if since_timestamp is not None:
        rendered_items = [
            item
            for item in rendered_items
            if _parse_iso_datetime_value(
                str(item["created_at"]),
                display_name="promotion `created_at`",
            )
            >= since_timestamp
        ]
    if until_timestamp is not None:
        rendered_items = [
            item
            for item in rendered_items
            if _parse_iso_datetime_value(
                str(item["created_at"]),
                display_name="promotion `created_at`",
            )
            <= until_timestamp
        ]

    if resolved_spec.sort_by == "created_at":
        rendered_items.sort(
            key=lambda item: (
                _parse_iso_datetime_value(
                    str(item["created_at"]),
                    display_name="promotion `created_at`",
                ),
                str(item["promotion_id"]),
            ),
            reverse=resolved_spec.descending,
        )
    else:
        rendered_items.sort(
            key=lambda item: str(item["promotion_id"]),
            reverse=resolved_spec.descending,
        )

    parsed_artifact_sources_total = sum(
        1 for item in rendered_items if item["has_parsed_artifact_sources"]
    )
    if resolved_spec.parsed_artifact_sources_only:
        rendered_items = [
            item for item in rendered_items if item["has_parsed_artifact_sources"]
        ]
    if resolved_spec.limit is not None:
        if resolved_spec.descending:
            rendered_items = rendered_items[: resolved_spec.limit]
        else:
            rendered_items = rendered_items[-resolved_spec.limit :]
    return rendered_items, parsed_artifact_sources_total
