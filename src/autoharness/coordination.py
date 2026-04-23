"""Atomic file writes and cooperative file-lock helpers."""

from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _lock_path(path: Path) -> Path:
    return path.with_name(f"{path.name}.lock")


def _lock_metadata() -> dict[str, object]:
    return {
        "pid": os.getpid(),
        "created_at": _utc_now(),
        "created_at_unix_seconds": time.time(),
    }


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    write_text_atomic(path, json.dumps(payload, indent=2) + "\n")


@contextmanager
def file_lock(
    path: Path,
    *,
    timeout_seconds: float = 30.0,
    poll_interval_seconds: float = 0.05,
    stale_after_seconds: float | None = 300.0,
) -> Iterator[Path]:
    """Acquire a cooperative lock next to ``path`` using an exclusive lock file."""

    lock_path = _lock_path(path)
    deadline = time.monotonic() + timeout_seconds
    metadata_text = json.dumps(_lock_metadata(), indent=2) + "\n"

    while True:
        try:
            fd = os.open(
                lock_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            if stale_after_seconds is not None and lock_path.exists():
                age_seconds = time.time() - lock_path.stat().st_mtime
                if age_seconds >= stale_after_seconds:
                    try:
                        lock_path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for lock: {lock_path}")
            time.sleep(poll_interval_seconds)
            continue
        try:
            os.write(fd, metadata_text.encode("utf-8"))
        finally:
            os.close(fd)
        break

    try:
        yield lock_path
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def append_jsonl_record(
    path: Path,
    payload: dict[str, Any],
    *,
    timeout_seconds: float = 30.0,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, sort_keys=False) + "\n"
    with file_lock(path, timeout_seconds=timeout_seconds):
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
