"""List and export CLI handlers for iterations, records, and promotions."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from .cli_support import _load_structured_file, _resolve_workspace_track
from .listings import (
    _build_iteration_listing_payload,
    _build_promotion_listing_payload,
    _build_record_listing_payload,
    _prepare_listing_payload,
)
from .outputs import (
    _emit_json_output,
    _emit_listing_json_output,
    _emit_text_listing_output,
    _export_listing_payload,
)
from .queries import IterationQuerySpec, PromotionQuerySpec, RecordQuerySpec
from .tracking import load_workspace, load_workspace_state
from .workspace import WorkspaceConfig, WorkspaceState


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_iteration_listing_request(
    *,
    root: Path,
    workspace_id: str,
    requested_track_id: str | None,
) -> tuple[WorkspaceState, str | None]:
    if requested_track_id is not None:
        _, state, resolved_track_id = _resolve_workspace_track(
            root=root,
            workspace_id=workspace_id,
            requested_track_id=requested_track_id,
        )
        return state, resolved_track_id
    return load_workspace_state(root, workspace_id), None


def _resolve_record_listing_request(
    *,
    root: Path,
    workspace_id: str,
    requested_track_id: str | None,
) -> tuple[str | None, WorkspaceConfig]:
    if requested_track_id is not None:
        workspace, _, resolved_track_id = _resolve_workspace_track(
            root=root,
            workspace_id=workspace_id,
            requested_track_id=requested_track_id,
        )
        return resolved_track_id, workspace
    return None, load_workspace(root, workspace_id)


def _resolve_promotion_listing_request(
    *,
    root: Path,
    workspace_id: str,
    requested_track_id: str | None,
) -> tuple[str | None, WorkspaceConfig]:
    if requested_track_id is not None:
        workspace, _, resolved_track_id = _resolve_workspace_track(
            root=root,
            workspace_id=workspace_id,
            requested_track_id=requested_track_id,
        )
        return resolved_track_id, workspace
    return None, load_workspace(root, workspace_id)


def _prepare_iteration_listing(args: argparse.Namespace):
    return _prepare_listing_payload(
        args=args,
        resolve_request=_resolve_iteration_listing_request,
        build_spec=lambda parsed_args, resolved_track_id: IterationQuerySpec.from_args(
            parsed_args,
            resolved_track_id=resolved_track_id,
        ),
        build_payload=lambda state, spec: _build_iteration_listing_payload(
            root=args.root,
            workspace_id=args.workspace_id,
            state=state,
            spec=spec,
        ),
    )


def _prepare_record_listing(args: argparse.Namespace):
    return _prepare_listing_payload(
        args=args,
        resolve_request=lambda **kwargs: tuple(
            reversed(_resolve_record_listing_request(**kwargs))
        ),
        build_spec=lambda parsed_args, resolved_track_id: RecordQuerySpec.from_args(
            parsed_args,
            resolved_track_id=resolved_track_id,
        ),
        build_payload=lambda _workspace, spec: _build_record_listing_payload(
            root=args.root,
            workspace_id=args.workspace_id,
            spec=spec,
        ),
    )


def _prepare_promotion_listing(args: argparse.Namespace):
    return _prepare_listing_payload(
        args=args,
        resolve_request=lambda **kwargs: tuple(
            reversed(_resolve_promotion_listing_request(**kwargs))
        ),
        build_spec=lambda parsed_args, resolved_track_id: PromotionQuerySpec.from_args(
            parsed_args,
            resolved_track_id=resolved_track_id,
        ),
        build_payload=lambda _workspace, spec: _build_promotion_listing_payload(
            root=args.root,
            workspace_id=args.workspace_id,
            spec=spec,
        ),
    )


def _listing_artifact_path_value(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


def _validate_listing_artifact_payload(
    *,
    payload: dict[str, object],
    listing_type: str,
) -> list[str]:
    errors: list[str] = []

    def require_list(key: str) -> list[object] | None:
        value = payload.get(key)
        if not isinstance(value, list):
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

    def require_int(key: str) -> int | None:
        value = payload.get(key)
        if not isinstance(value, int):
            errors.append(f"Missing or invalid `{key}`.")
            return None
        return value

    workspace_id = payload.get("workspace_id")
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        errors.append("Missing or invalid `workspace_id`.")

    if listing_type == "iteration_export":
        require_int("saved_plan_iterations_total")
        iterations = require_list("iterations")
        iterations_dir = payload.get("iterations_dir")
        if not isinstance(iterations_dir, str) or not iterations_dir.strip():
            errors.append("Missing or invalid `iterations_dir`.")
        if iterations is None:
            return errors
        return errors

    if listing_type == "record_export":
        require_int("saved_plan_records_total")
        require_list("records")
        return errors

    if listing_type == "promotion_export":
        require_int("parsed_artifact_sources_total")
        require_list("promotions")
        return errors

    if listing_type == "proposal_export":
        require_int("non_executable_proposals_total")
        require_list("proposals")
        return errors

    errors.append(f"Unsupported listing artifact type `{listing_type}`.")
    return errors


def _render_listing_artifact(path: Path) -> dict[str, object]:
    payload = _load_structured_file(path)
    format_version = payload.get("format_version")
    if not isinstance(format_version, str):
        raise SystemExit(f"Listing export missing format_version: {path}")

    rendered: dict[str, object] = {
        "listing_path": str(path),
        "format_version": format_version,
        "listing": payload,
    }

    if format_version == "autoharness.iteration_export.v1":
        iterations = payload.get("iterations")
        rendered.update(
            {
                "listing_type": "iteration_export",
                "workspace_id": _listing_artifact_path_value(payload, "workspace_id"),
                "item_total": len(iterations) if isinstance(iterations, list) else 0,
                "summary_total": payload.get("saved_plan_iterations_total"),
                "summary_label": "saved_plan_iterations_total",
                "last_iteration_id": payload.get("last_iteration_id"),
            }
        )
        return rendered

    if format_version == "autoharness.record_export.v1":
        records = payload.get("records")
        rendered.update(
            {
                "listing_type": "record_export",
                "workspace_id": _listing_artifact_path_value(payload, "workspace_id"),
                "item_total": len(records) if isinstance(records, list) else 0,
                "summary_total": payload.get("saved_plan_records_total"),
                "summary_label": "saved_plan_records_total",
            }
        )
        return rendered

    if format_version == "autoharness.promotion_export.v1":
        promotions = payload.get("promotions")
        rendered.update(
            {
                "listing_type": "promotion_export",
                "workspace_id": _listing_artifact_path_value(payload, "workspace_id"),
                "item_total": len(promotions) if isinstance(promotions, list) else 0,
                "summary_total": payload.get("parsed_artifact_sources_total"),
                "summary_label": "parsed_artifact_sources_total",
            }
        )
        return rendered

    if format_version == "autoharness.proposal_export.v1":
        proposals = payload.get("proposals")
        rendered.update(
            {
                "listing_type": "proposal_export",
                "workspace_id": _listing_artifact_path_value(payload, "workspace_id"),
                "item_total": len(proposals) if isinstance(proposals, list) else 0,
                "summary_total": payload.get("non_executable_proposals_total"),
                "summary_label": "non_executable_proposals_total",
            }
        )
        return rendered

    raise SystemExit(f"Unsupported listing export format_version `{format_version}`: {path}")


def _render_listing_validation(path: Path) -> dict[str, object]:
    rendered = _render_listing_artifact(path)
    listing_type = rendered["listing_type"]
    assert isinstance(listing_type, str)
    listing_payload = rendered["listing"]
    assert isinstance(listing_payload, dict)
    validation_errors = _validate_listing_artifact_payload(
        payload=listing_payload,
        listing_type=listing_type,
    )
    return {
        **rendered,
        "valid": not validation_errors,
        "error_count": len(validation_errors),
        "validation_errors": validation_errors,
    }


def _handle_show_listing_file(args: argparse.Namespace) -> int:
    rendered = _render_listing_artifact(args.path)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0

    print(f"Listing type: {rendered['listing_type']}")
    print(f"Listing path: {rendered['listing_path']}")
    print(f"Format version: {rendered['format_version']}")
    print(f"Workspace: {rendered['workspace_id']}")
    print(f"Items: {rendered['item_total']}")
    summary_label = rendered["summary_label"]
    assert isinstance(summary_label, str)
    print(f"{summary_label}: {rendered['summary_total']}")
    if rendered.get("last_iteration_id") is not None:
        print(f"Last iteration: {rendered['last_iteration_id']}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0


def _handle_validate_listing_file(args: argparse.Namespace) -> int:
    rendered = _render_listing_validation(args.path)
    if _emit_json_output(rendered=rendered, output=args.output, as_json=args.json):
        return 0 if bool(rendered["valid"]) else 1

    print(f"Listing type: {rendered['listing_type']}")
    print(f"Listing path: {rendered['listing_path']}")
    print(f"Format version: {rendered['format_version']}")
    print(f"Valid: {'yes' if rendered['valid'] else 'no'}")
    print(f"Errors: {rendered['error_count']}")
    validation_errors = rendered["validation_errors"]
    assert isinstance(validation_errors, list)
    for error in validation_errors:
        print(f"- {error}")
    if args.output is not None:
        print(f"Wrote output to {args.output}")
    return 0 if bool(rendered["valid"]) else 1


def _handle_show_iterations(args: argparse.Namespace) -> int:
    state, resolved_track_id, spec, rendered = _prepare_iteration_listing(args)
    rendered_items = rendered["iterations"]
    saved_plan_iterations_total = rendered["saved_plan_iterations_total"]

    if _emit_listing_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    item_lines = []
    for item in rendered_items:
        marker = "*" if item["last_iteration"] else "-"
        saved_plan_suffix = ", saved_plan=yes" if item["saved_plan_run"] else ""
        item_lines.append(
            f"{marker} {item['iteration_id']}: "
            f"track={item['track_id']}, status={item['status']}, "
            f"stage={item['stage'] or 'unscoped'}, record={item['record_id']}"
            f"{saved_plan_suffix}"
        )
    _emit_text_listing_output(
        workspace_id=args.workspace_id,
        collection_label="Iterations",
        collection_count=len(rendered_items),
        summary_label="Saved-plan runs",
        summary_count=saved_plan_iterations_total,
        sort_by=spec.sort_by,
        descending=spec.descending,
        resolved_track_id=resolved_track_id,
        named_filters=[
            ("Stage filter", spec.stage),
            ("Status filter", spec.status),
            ("Benchmark filter", spec.benchmark_name),
            ("Adapter filter", spec.adapter_id),
            ("Hypothesis filter", spec.hypothesis_contains),
            ("Notes filter", spec.notes_contains),
            ("Since filter", spec.since),
            ("Until filter", spec.until),
        ],
        enabled_filters=[
            ("Filter: saved-plan only", spec.saved_plan_only),
        ],
        extra_lines=(
            [f"Last iteration: {state.last_iteration_id}"]
            if state.last_iteration_id is not None
            else []
        ),
        item_lines=item_lines,
        output=args.output,
    )
    return 0


def _handle_export_iterations(args: argparse.Namespace) -> int:
    _, _, _, rendered = _prepare_iteration_listing(args)
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.iteration_export.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )

    print(f"Workspace: {args.workspace_id}")
    print(f"Iterations exported: {len(rendered['iterations'])}")
    print(f"Saved-plan runs: {rendered['saved_plan_iterations_total']}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0


def _handle_show_records(args: argparse.Namespace) -> int:
    _, resolved_track_id, spec, rendered = _prepare_record_listing(args)
    rendered_items = rendered["records"]
    saved_plan_records_total = rendered["saved_plan_records_total"]

    if _emit_listing_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    item_lines = []
    for item in rendered_items:
        saved_plan_suffix = ", saved_plan=yes" if item["saved_plan_run"] else ""
        item_lines.append(
            f"- {item['record_id']}: "
            f"track={item['track_id']}, status={item['status']}, "
            f"stage={item['stage'] or 'unscoped'}, iteration={item['iteration_id'] or 'none'}"
            f"{saved_plan_suffix}"
        )
    _emit_text_listing_output(
        workspace_id=args.workspace_id,
        collection_label="Records",
        collection_count=len(rendered_items),
        summary_label="Saved-plan runs",
        summary_count=saved_plan_records_total,
        sort_by=spec.sort_by,
        descending=spec.descending,
        resolved_track_id=resolved_track_id,
        named_filters=[
            ("Stage filter", spec.stage),
            ("Status filter", spec.status),
            ("Benchmark filter", spec.benchmark_name),
            ("Adapter filter", spec.adapter_id),
            ("Hypothesis filter", spec.hypothesis_contains),
            ("Notes filter", spec.notes_contains),
            ("Since filter", spec.since),
            ("Until filter", spec.until),
        ],
        enabled_filters=[
            ("Filter: saved-plan only", spec.saved_plan_only),
        ],
        extra_lines=[],
        item_lines=item_lines,
        output=args.output,
    )
    return 0


def _handle_export_records(args: argparse.Namespace) -> int:
    _, _, _, rendered = _prepare_record_listing(args)
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.record_export.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )

    print(f"Workspace: {args.workspace_id}")
    print(f"Records exported: {len(rendered['records'])}")
    print(f"Saved-plan runs: {rendered['saved_plan_records_total']}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0


def _handle_show_promotions(args: argparse.Namespace) -> int:
    _, resolved_track_id, spec, rendered = _prepare_promotion_listing(args)
    rendered_items = rendered["promotions"]
    parsed_artifact_sources_total = rendered["parsed_artifact_sources_total"]

    if _emit_listing_json_output(
        rendered=rendered,
        output=args.output,
        as_json=args.json,
    ):
        return 0

    item_lines = []
    for item in rendered_items:
        parsed_sources_suffix = (
            ", parsed_artifact_sources=yes"
            if item["has_parsed_artifact_sources"]
            else ""
        )
        item_lines.append(
            f"- {item['promotion_id']}: "
            f"track={item['track_id']}, record={item['record_id']}, "
            f"iteration={item['iteration_id'] or 'none'}"
            f"{parsed_sources_suffix}"
        )
    _emit_text_listing_output(
        workspace_id=args.workspace_id,
        collection_label="Promotions",
        collection_count=len(rendered_items),
        summary_label="Parsed artifact sources",
        summary_count=parsed_artifact_sources_total,
        sort_by=spec.sort_by,
        descending=spec.descending,
        resolved_track_id=resolved_track_id,
        named_filters=[
            ("Record filter", spec.record_id),
            ("Iteration filter", spec.iteration_id),
            ("Target root filter", spec.target_root_contains),
            ("Notes filter", spec.notes_contains),
            ("Since filter", spec.since),
            ("Until filter", spec.until),
        ],
        enabled_filters=[
            ("Filter: parsed artifact sources only", spec.parsed_artifact_sources_only),
        ],
        extra_lines=[],
        item_lines=item_lines,
        output=args.output,
    )
    return 0


def _handle_export_promotions(args: argparse.Namespace) -> int:
    _, _, _, rendered = _prepare_promotion_listing(args)
    output_format = _export_listing_payload(
        output=args.output,
        explicit_format=args.format,
        format_version="autoharness.promotion_export.v1",
        rendered=rendered,
        exported_at=_utc_now(),
    )

    print(f"Workspace: {args.workspace_id}")
    print(f"Promotions exported: {len(rendered['promotions'])}")
    print(f"Parsed artifact sources: {rendered['parsed_artifact_sources_total']}")
    print(f"Format: {output_format}")
    print(f"Export path: {args.output}")
    return 0
