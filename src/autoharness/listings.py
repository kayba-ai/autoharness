"""Listing payload builders shared by CLI list and export commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from .queries import (
    IterationQuerySpec,
    ProposalQuerySpec,
    PromotionQuerySpec,
    RecordQuerySpec,
    query_workspace_iteration_items,
    query_workspace_proposal_items,
    query_workspace_promotion_items,
    query_workspace_record_items,
)
from .tracking import iterations_dir_path
from .workspace import WorkspaceState


def _build_iteration_listing_payload(
    *,
    root: Path,
    workspace_id: str,
    state: WorkspaceState,
    spec: IterationQuerySpec,
) -> dict[str, object]:
    rendered_items, saved_plan_iterations_total = query_workspace_iteration_items(
        root=root,
        workspace_id=workspace_id,
        last_iteration_id=state.last_iteration_id,
        spec=spec,
    )
    return {
        "workspace_id": workspace_id,
        **spec.rendered_filters(),
        "last_iteration_id": state.last_iteration_id,
        "iterations_dir": str(iterations_dir_path(root=root, workspace_id=workspace_id)),
        "saved_plan_iterations_total": saved_plan_iterations_total,
        "iterations": rendered_items,
    }


def _build_record_listing_payload(
    *,
    root: Path,
    workspace_id: str,
    spec: RecordQuerySpec,
) -> dict[str, object]:
    rendered_items, saved_plan_records_total = query_workspace_record_items(
        root=root,
        workspace_id=workspace_id,
        spec=spec,
    )
    return {
        "workspace_id": workspace_id,
        **spec.rendered_filters(),
        "saved_plan_records_total": saved_plan_records_total,
        "records": rendered_items,
    }


def _build_proposal_listing_payload(
    *,
    root: Path,
    workspace_id: str,
    spec: ProposalQuerySpec,
) -> dict[str, object]:
    rendered_items, non_executable_proposals_total = query_workspace_proposal_items(
        root=root,
        workspace_id=workspace_id,
        spec=spec,
    )
    return {
        "workspace_id": workspace_id,
        **spec.rendered_filters(),
        "non_executable_proposals_total": non_executable_proposals_total,
        "proposals": rendered_items,
    }


def _build_promotion_listing_payload(
    *,
    root: Path,
    workspace_id: str,
    spec: PromotionQuerySpec,
) -> dict[str, object]:
    rendered_items, parsed_artifact_sources_total = query_workspace_promotion_items(
        root=root,
        workspace_id=workspace_id,
        spec=spec,
    )
    return {
        "workspace_id": workspace_id,
        **spec.rendered_filters(),
        "parsed_artifact_sources_total": parsed_artifact_sources_total,
        "promotions": rendered_items,
    }


def _prepare_listing_payload(
    *,
    args: argparse.Namespace,
    resolve_request,
    build_spec,
    build_payload,
):
    context, resolved_track_id = resolve_request(
        root=args.root,
        workspace_id=args.workspace_id,
        requested_track_id=args.track_id,
    )
    spec = build_spec(args, resolved_track_id)
    rendered = build_payload(context, spec)
    return context, resolved_track_id, spec, rendered
