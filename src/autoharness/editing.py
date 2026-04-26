"""Edit-plan parsing, application, and transactional restore support."""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from .autonomy import AutonomyPolicy


EditOperationType = Literal[
    "search_replace",
    "write_file",
    "delete_file",
    "move_path",
    "unified_diff",
]
EditApplicationStatus = Literal["applied", "preview", "proposal_only", "blocked"]
EditRestoreStatus = Literal["reverted", "kept", "not_applied"]
_UNIFIED_DIFF_HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$"
)


@dataclass(frozen=True)
class EditOperation:
    """One normalized file edit inside an edit plan."""

    type: EditOperationType
    path: str
    search: str | None = None
    replace: str | None = None
    expected_count: int | None = None
    content: str | None = None
    create_if_missing: bool = True
    dest_path: str | None = None
    diff: str | None = None
    overwrite: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EditPlan:
    """A proposal or executable edit bundle for one hypothesis."""

    format_version: str
    operations: tuple[EditOperation, ...]
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "summary": self.summary,
            "operations": [operation.to_dict() for operation in self.operations],
        }


@dataclass(frozen=True)
class EditApplicationResult:
    """Outcome of evaluating or applying one edit plan."""

    format_version: str
    status: EditApplicationStatus
    mode: str
    applied: bool
    preview_only: bool
    proposal_only: bool
    blocked: bool
    operation_count: int
    touched_paths: tuple[str, ...]
    reasons: tuple[str, ...] = ()
    target_root: str | None = None
    plan_path: str | None = None
    summary: str = ""
    operations: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "status": self.status,
            "mode": self.mode,
            "applied": self.applied,
            "preview_only": self.preview_only,
            "proposal_only": self.proposal_only,
            "blocked": self.blocked,
            "operation_count": self.operation_count,
            "touched_paths": list(self.touched_paths),
            "reasons": list(self.reasons),
            "target_root": self.target_root,
            "plan_path": self.plan_path,
            "summary": self.summary,
            "operations": list(self.operations),
        }


@dataclass(frozen=True)
class EditRestoreResult:
    """Result of either reverting an applied edit session or keeping it."""

    format_version: str
    status: EditRestoreStatus
    reverted: bool
    kept: bool
    restored_paths: tuple[str, ...]
    deleted_paths: tuple[str, ...] = ()
    target_root: str | None = None
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": self.format_version,
            "status": self.status,
            "reverted": self.reverted,
            "kept": self.kept,
            "restored_paths": list(self.restored_paths),
            "deleted_paths": list(self.deleted_paths),
            "target_root": self.target_root,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class _FileSnapshot:
    rel_path: str
    existed_before: bool
    content_before: str | None


@dataclass(frozen=True)
class _PlannedWrite:
    rel_path: str
    content_after: str | None


@dataclass
class EditSession:
    """In-memory handle for one applied or previewed edit plan."""

    application: EditApplicationResult
    target_root: Path
    snapshots: tuple[_FileSnapshot, ...] = ()
    writes: tuple[_PlannedWrite, ...] = ()
    _finalized: bool = field(default=False, init=False, repr=False)

    def render_unified_diff(self) -> str:
        """Render a unified patch for the candidate edits recorded in this session."""
        chunks: list[str] = []
        snapshots_by_path = {snapshot.rel_path: snapshot for snapshot in self.snapshots}
        for write in self.writes:
            snapshot = snapshots_by_path.get(write.rel_path)
            before = snapshot.content_before if snapshot is not None else None
            after = write.content_after
            if before == after:
                continue
            before_lines = [] if before is None else before.splitlines(keepends=True)
            after_lines = [] if after is None else after.splitlines(keepends=True)
            fromfile = (
                "/dev/null"
                if snapshot is not None and not snapshot.existed_before
                else f"a/{write.rel_path}"
            )
            tofile = "/dev/null" if after is None else f"b/{write.rel_path}"
            chunks.extend(
                difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=fromfile,
                    tofile=tofile,
                )
            )
        return "".join(chunks)

    def finalize(self, *, keep_applied: bool = False) -> EditRestoreResult:
        """Restore touched files unless the caller intentionally keeps them."""
        if self._finalized:
            raise RuntimeError("Edit session already finalized.")
        self._finalized = True

        if not self.application.applied:
            return EditRestoreResult(
                format_version="autoharness.edit_restore.v1",
                status="not_applied",
                reverted=False,
                kept=False,
                restored_paths=(),
                deleted_paths=(),
                target_root=str(self.target_root),
                reasons=("No edits were applied, so there was nothing to restore.",),
            )

        if keep_applied:
            return EditRestoreResult(
                format_version="autoharness.edit_restore.v1",
                status="kept",
                reverted=False,
                kept=True,
                restored_paths=tuple(snapshot.rel_path for snapshot in self.snapshots),
                deleted_paths=(),
                target_root=str(self.target_root),
                reasons=("The operator requested that applied edits remain in place.",),
            )

        restored_paths: list[str] = []
        deleted_paths: list[str] = []
        for snapshot in reversed(self.snapshots):
            path = self.target_root / snapshot.rel_path
            if snapshot.existed_before:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(snapshot.content_before or "", encoding="utf-8")
                restored_paths.append(snapshot.rel_path)
            elif path.exists():
                path.unlink()
                deleted_paths.append(snapshot.rel_path)

        return EditRestoreResult(
            format_version="autoharness.edit_restore.v1",
            status="reverted",
            reverted=True,
            kept=False,
            restored_paths=tuple(restored_paths),
            deleted_paths=tuple(deleted_paths),
            target_root=str(self.target_root),
            reasons=("Applied edits were restored after the iteration completed.",),
        )


def edit_plan_from_dict(data: dict[str, Any]) -> EditPlan:
    """Validate and normalize a decoded edit-plan payload."""
    operations_value = data.get("operations")
    if not isinstance(operations_value, list) or not operations_value:
        raise ValueError("`operations` must be a non-empty list.")

    operations: list[EditOperation] = []
    for index, raw_operation in enumerate(operations_value):
        if not isinstance(raw_operation, dict):
            raise ValueError(f"Operation {index} must be a mapping.")
        raw_type = raw_operation.get("type")
        raw_path = raw_operation.get("path")
        if raw_type not in {
            "search_replace",
            "write_file",
            "delete_file",
            "move_path",
            "unified_diff",
        }:
            raise ValueError(
                f"Operation {index} has unsupported type: {raw_type!r}."
            )
        if raw_type != "move_path" and (
            not isinstance(raw_path, str) or not raw_path
        ):
            raise ValueError(f"Operation {index} needs a non-empty `path`.")

        if raw_type == "search_replace":
            search = raw_operation.get("search")
            replace = raw_operation.get("replace")
            if not isinstance(search, str) or search == "":
                raise ValueError(f"Operation {index} needs a non-empty `search`.")
            if not isinstance(replace, str):
                raise ValueError(f"Operation {index} needs a string `replace`.")
            expected_count = raw_operation.get("expected_count")
            if expected_count is not None and (
                not isinstance(expected_count, int) or expected_count < 1
            ):
                raise ValueError(
                    f"Operation {index} `expected_count` must be a positive integer."
                )
            operations.append(
                EditOperation(
                    type="search_replace",
                    path=raw_path,
                    search=search,
                    replace=replace,
                    expected_count=expected_count,
                )
            )
            continue

        if raw_type == "write_file":
            content = raw_operation.get("content")
            if not isinstance(content, str):
                raise ValueError(f"Operation {index} needs string `content`.")
            create_if_missing = raw_operation.get("create_if_missing", True)
            if not isinstance(create_if_missing, bool):
                raise ValueError(
                    f"Operation {index} `create_if_missing` must be a boolean."
                )
            operations.append(
                EditOperation(
                    type="write_file",
                    path=raw_path,
                    content=content,
                    create_if_missing=create_if_missing,
                )
            )
            continue

        if raw_type == "delete_file":
            operations.append(
                EditOperation(
                    type="delete_file",
                    path=raw_path,
                )
            )
            continue

        if raw_type == "move_path":
            if not isinstance(raw_path, str) or not raw_path:
                raise ValueError(f"Operation {index} needs a non-empty `path`.")
            dest_path = raw_operation.get("dest_path")
            if not isinstance(dest_path, str) or not dest_path:
                raise ValueError(f"Operation {index} needs a non-empty `dest_path`.")
            overwrite = raw_operation.get("overwrite", False)
            if not isinstance(overwrite, bool):
                raise ValueError(
                    f"Operation {index} `overwrite` must be a boolean."
                )
            operations.append(
                EditOperation(
                    type="move_path",
                    path=raw_path,
                    dest_path=dest_path,
                    overwrite=overwrite,
                )
            )
            continue

        diff = raw_operation.get("diff")
        if not isinstance(diff, str) or not diff.strip():
            raise ValueError(f"Operation {index} needs non-empty string `diff`.")
        operations.append(
            EditOperation(
                type="unified_diff",
                path=raw_path,
                diff=diff,
            )
        )

    return EditPlan(
        format_version=str(data.get("format_version", "autoharness.edit_plan.v1")),
        summary=str(data.get("summary", "")),
        operations=tuple(operations),
    )


def apply_edit_plan(
    *,
    plan: EditPlan,
    target_root: Path,
    policy: AutonomyPolicy,
    preview_only: bool = False,
    plan_path: Path | None = None,
) -> EditApplicationResult:
    """Apply an edit plan immediately and return the application result."""
    session = start_edit_session(
        plan=plan,
        target_root=target_root,
        policy=policy,
        preview_only=preview_only,
        plan_path=plan_path,
    )
    return session.application


def start_edit_session(
    *,
    plan: EditPlan,
    target_root: Path,
    policy: AutonomyPolicy,
    preview_only: bool = False,
    plan_path: Path | None = None,
) -> EditSession:
    """Apply an edit plan transactionally and retain snapshots for later restore."""
    target_root_resolved = target_root.resolve()
    if not target_root_resolved.exists():
        raise ValueError(f"Target root does not exist: {target_root}")
    if not target_root_resolved.is_dir():
        raise ValueError(f"Target root must be a directory: {target_root}")

    touched_paths: list[str] = []
    operation_dicts: list[dict[str, Any]] = []
    proposal_reasons: list[str] = []
    blocked_reasons: list[str] = []
    working_contents: dict[str, str | None] = {}
    snapshots: dict[str, _FileSnapshot] = {}
    write_order: list[str] = []

    for operation in plan.operations:
        if operation.type == "move_path":
            dest_path = operation.dest_path or ""
            source_resolved, source_rel_path = _resolve_relative_path(
                root=target_root_resolved,
                raw_path=operation.path,
            )
            dest_resolved, dest_rel_path = _resolve_relative_path(
                root=target_root_resolved,
                raw_path=dest_path,
            )
            if source_rel_path == dest_rel_path:
                raise ValueError(
                    f"move_path source and destination must differ: {source_rel_path}"
                )
            touched_paths.extend([source_rel_path, dest_rel_path])
            operation_dicts.append(operation.to_dict())
            source_content = _load_current_content(
                resolved_path=source_resolved,
                rel_path=source_rel_path,
                working_contents=working_contents,
                snapshots=snapshots,
                write_order=write_order,
            )
            if not _current_file_exists(
                rel_path=source_rel_path,
                working_contents=working_contents,
                snapshots=snapshots,
            ):
                raise ValueError(f"move_path source does not exist: {source_rel_path}")
            _load_current_content(
                resolved_path=dest_resolved,
                rel_path=dest_rel_path,
                working_contents=working_contents,
                snapshots=snapshots,
                write_order=write_order,
            )
            if (
                _current_file_exists(
                    rel_path=dest_rel_path,
                    working_contents=working_contents,
                    snapshots=snapshots,
                )
                and not operation.overwrite
            ):
                raise ValueError(
                    f"move_path destination already exists: {dest_rel_path}"
                )
            working_contents[source_rel_path] = None
            working_contents[dest_rel_path] = source_content

            for rel_path in (source_rel_path, dest_rel_path):
                protected_match = _match_surfaces(rel_path, policy.protected_surfaces)
                editable_match = _match_surfaces(rel_path, policy.editable_surfaces)
                if protected_match is not None:
                    proposal_reasons.append(
                        f"{rel_path} is inside protected surface `{protected_match}`."
                    )
                    continue
                if policy.requires_explicit_edit_allowlist and editable_match is None:
                    blocked_reasons.append(
                        f"{rel_path} is outside editable surfaces for bounded mode."
                    )
            continue

        resolved_path, rel_path = _resolve_relative_path(
            root=target_root_resolved,
            raw_path=operation.path,
        )
        touched_paths.append(rel_path)
        operation_dicts.append(operation.to_dict())

        current_content = _load_current_content(
            resolved_path=resolved_path,
            rel_path=rel_path,
            working_contents=working_contents,
            snapshots=snapshots,
            write_order=write_order,
        )
        file_exists = _current_file_exists(
            rel_path=rel_path,
            working_contents=working_contents,
            snapshots=snapshots,
        )
        working_contents[rel_path] = _apply_operation_to_content(
            operation=operation,
            rel_path=rel_path,
            current_content=current_content,
            file_exists=file_exists,
        )

        protected_match = _match_surfaces(rel_path, policy.protected_surfaces)
        editable_match = _match_surfaces(rel_path, policy.editable_surfaces)
        if protected_match is not None:
            proposal_reasons.append(
                f"{rel_path} is inside protected surface `{protected_match}`."
            )
            continue
        if policy.requires_explicit_edit_allowlist and editable_match is None:
            blocked_reasons.append(
                f"{rel_path} is outside editable surfaces for bounded mode."
            )
            continue

    unique_paths = tuple(dict.fromkeys(touched_paths))
    if policy.mode == "proposal":
        proposal_reasons.insert(
            0,
            "Autonomy mode `proposal` does not permit applying edits directly.",
        )

    application = _build_application_result(
        plan=plan,
        policy=policy,
        preview_only=preview_only,
        touched_paths=unique_paths,
        proposal_reasons=proposal_reasons,
        blocked_reasons=blocked_reasons,
        target_root=target_root_resolved,
        plan_path=plan_path,
        operation_dicts=tuple(operation_dicts),
    )
    if not application.applied:
        return EditSession(
            application=application,
            target_root=target_root_resolved,
            snapshots=tuple(snapshots[rel_path] for rel_path in write_order),
            writes=tuple(
                _PlannedWrite(rel_path=rel_path, content_after=working_contents[rel_path])
                for rel_path in write_order
            ),
        )

    for rel_path in write_order:
        path = target_root_resolved / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        content_after = working_contents[rel_path]
        if content_after is None:
            if path.exists():
                path.unlink()
            continue
        path.write_text(content_after, encoding="utf-8")

    ordered_snapshots = tuple(snapshots[rel_path] for rel_path in write_order)
    ordered_writes = tuple(
        _PlannedWrite(rel_path=rel_path, content_after=working_contents[rel_path])
        for rel_path in write_order
    )
    return EditSession(
        application=application,
        target_root=target_root_resolved,
        snapshots=ordered_snapshots,
        writes=ordered_writes,
    )


def _build_application_result(
    *,
    plan: EditPlan,
    policy: AutonomyPolicy,
    preview_only: bool,
    touched_paths: tuple[str, ...],
    proposal_reasons: list[str],
    blocked_reasons: list[str],
    target_root: Path,
    plan_path: Path | None,
    operation_dicts: tuple[dict[str, Any], ...],
) -> EditApplicationResult:
    if preview_only:
        reasons = tuple(blocked_reasons or proposal_reasons)
        if not reasons:
            reasons = ("Preview only: no edit was applied.",)
        return EditApplicationResult(
            format_version="autoharness.edit_application.v1",
            status="preview",
            mode=policy.mode,
            applied=False,
            preview_only=True,
            proposal_only=bool(proposal_reasons),
            blocked=bool(blocked_reasons),
            operation_count=len(plan.operations),
            touched_paths=touched_paths,
            reasons=reasons,
            target_root=str(target_root),
            plan_path=str(plan_path) if plan_path is not None else None,
            summary=plan.summary,
            operations=operation_dicts,
        )

    if blocked_reasons:
        return EditApplicationResult(
            format_version="autoharness.edit_application.v1",
            status="blocked",
            mode=policy.mode,
            applied=False,
            preview_only=False,
            proposal_only=False,
            blocked=True,
            operation_count=len(plan.operations),
            touched_paths=touched_paths,
            reasons=tuple(blocked_reasons),
            target_root=str(target_root),
            plan_path=str(plan_path) if plan_path is not None else None,
            summary=plan.summary,
            operations=operation_dicts,
        )

    if proposal_reasons:
        return EditApplicationResult(
            format_version="autoharness.edit_application.v1",
            status="proposal_only",
            mode=policy.mode,
            applied=False,
            preview_only=False,
            proposal_only=True,
            blocked=False,
            operation_count=len(plan.operations),
            touched_paths=touched_paths,
            reasons=tuple(proposal_reasons),
            target_root=str(target_root),
            plan_path=str(plan_path) if plan_path is not None else None,
            summary=plan.summary,
            operations=operation_dicts,
        )

    return EditApplicationResult(
        format_version="autoharness.edit_application.v1",
        status="applied",
        mode=policy.mode,
        applied=True,
        preview_only=False,
        proposal_only=False,
        blocked=False,
        operation_count=len(plan.operations),
        touched_paths=touched_paths,
        reasons=(),
        target_root=str(target_root),
        plan_path=str(plan_path) if plan_path is not None else None,
        summary=plan.summary,
        operations=operation_dicts,
    )


def _load_current_content(
    *,
    resolved_path: Path,
    rel_path: str,
    working_contents: dict[str, str],
    snapshots: dict[str, _FileSnapshot],
    write_order: list[str],
) -> str:
    if rel_path in working_contents:
        return working_contents[rel_path] or ""

    if rel_path not in snapshots:
        existed_before = resolved_path.exists()
        if existed_before and not resolved_path.is_file():
            raise ValueError(f"Edit operation target must be a file: {rel_path}")
        content_before = (
            resolved_path.read_text(encoding="utf-8") if existed_before else None
        )
        snapshots[rel_path] = _FileSnapshot(
            rel_path=rel_path,
            existed_before=existed_before,
            content_before=content_before,
        )
        write_order.append(rel_path)

    return snapshots[rel_path].content_before or ""


def _current_file_exists(
    *,
    rel_path: str,
    working_contents: dict[str, str | None],
    snapshots: dict[str, _FileSnapshot],
) -> bool:
    if rel_path in working_contents:
        return working_contents[rel_path] is not None
    snapshot = snapshots.get(rel_path)
    return snapshot.existed_before if snapshot is not None else False


def _apply_operation_to_content(
    *,
    operation: EditOperation,
    rel_path: str,
    current_content: str,
    file_exists: bool,
) -> str | None:
    if operation.type == "search_replace":
        search = operation.search or ""
        replace = operation.replace or ""
        matches = current_content.count(search)
        if not file_exists:
            raise ValueError(f"search_replace target does not exist: {rel_path}")
        if matches < 1:
            raise ValueError(f"search_replace found no matches in {rel_path}")
        if operation.expected_count is not None and matches != operation.expected_count:
            raise ValueError(
                f"search_replace expected {operation.expected_count} matches in "
                f"{rel_path}, found {matches}"
            )
        return current_content.replace(search, replace)

    if operation.type == "write_file":
        if not file_exists and not operation.create_if_missing:
            raise ValueError(
                f"write_file target does not exist and create_if_missing is false: "
                f"{rel_path}"
            )
        return operation.content or ""

    if operation.type == "delete_file":
        if not file_exists:
            raise ValueError(f"delete_file target does not exist: {rel_path}")
        return None

    if operation.type == "unified_diff":
        if not file_exists:
            raise ValueError(f"unified_diff target does not exist: {rel_path}")
        return _apply_unified_diff_to_content(
            diff_text=operation.diff or "",
            current_content=current_content,
            rel_path=rel_path,
        )

    raise ValueError(f"Unsupported edit operation type: {operation.type}")


def _apply_unified_diff_to_content(
    *,
    diff_text: str,
    current_content: str,
    rel_path: str,
) -> str:
    diff_lines = diff_text.splitlines(keepends=True)
    index = 0
    while index < len(diff_lines):
        line = diff_lines[index]
        if line.startswith("@@"):
            break
        if line.startswith(("--- ", "+++ ", "diff --git ", "index ")) or not line.strip():
            index += 1
            continue
        raise ValueError(
            f"unified_diff contains unsupported prelude line for {rel_path}: {line.rstrip()}"
        )
    if index >= len(diff_lines):
        raise ValueError(f"unified_diff did not contain any hunks for {rel_path}")

    source_lines = current_content.splitlines(keepends=True)
    rendered: list[str] = []
    source_index = 0

    while index < len(diff_lines):
        header = diff_lines[index].rstrip("\n")
        match = _UNIFIED_DIFF_HUNK_RE.match(header)
        if match is None:
            raise ValueError(f"Invalid unified_diff hunk header for {rel_path}: {header}")
        old_start = int(match.group(1))
        target_index = max(old_start - 1, 0)
        if target_index < source_index:
            raise ValueError(f"unified_diff hunks overlap or go backwards in {rel_path}")

        rendered.extend(source_lines[source_index:target_index])
        cursor = target_index
        index += 1
        while index < len(diff_lines) and not diff_lines[index].startswith("@@"):
            line = diff_lines[index]
            if line.startswith("\\ No newline at end of file"):
                index += 1
                continue
            if not line or line[0] not in {" ", "+", "-"}:
                raise ValueError(
                    f"Invalid unified_diff hunk line for {rel_path}: {line.rstrip()}"
                )
            content = line[1:]
            if line[0] == " ":
                if cursor >= len(source_lines) or source_lines[cursor] != content:
                    raise ValueError(
                        f"unified_diff context mismatch in {rel_path}: {content!r}"
                    )
                rendered.append(content)
                cursor += 1
            elif line[0] == "-":
                if cursor >= len(source_lines) or source_lines[cursor] != content:
                    raise ValueError(
                        f"unified_diff deletion mismatch in {rel_path}: {content!r}"
                    )
                cursor += 1
            else:
                rendered.append(content)
            index += 1
        source_index = cursor

    rendered.extend(source_lines[source_index:])
    return "".join(rendered)


def _resolve_relative_path(*, root: Path, raw_path: str) -> tuple[Path, str]:
    if not raw_path:
        raise ValueError("Edit operation path must be non-empty.")
    candidate = (root / raw_path).resolve()
    try:
        rel_path = candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"Edit operation path escapes target root: {raw_path}"
        ) from exc
    return candidate, rel_path


def _match_surfaces(path: str, surfaces: tuple[str, ...]) -> str | None:
    normalized_path = _normalize_surface(path)
    for surface in surfaces:
        normalized_surface = _normalize_surface(surface)
        if normalized_surface == ".":
            return surface
        if (
            normalized_path == normalized_surface
            or normalized_path.startswith(f"{normalized_surface}/")
        ):
            return surface
    return None


def _normalize_surface(value: str) -> str:
    normalized = PurePosixPath(value).as_posix().strip("/")
    return normalized or "."
