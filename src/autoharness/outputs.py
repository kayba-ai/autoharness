"""Structured output and listing-render helpers for the CLI layer."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .coordination import write_text_atomic


_SECRET_KEY_FRAGMENTS = (
    "api_key",
    "secret",
    "password",
    "authorization",
    "cookie",
    "client_secret",
)
_SECRET_TOKEN_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "session_token",
    "bearer_token",
    "api_token",
    "auth_token",
}
_REDACTED_VALUE = "[redacted]"


def _should_redact_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in _SECRET_TOKEN_KEYS:
        return True
    if normalized.endswith("_token") and not normalized.endswith("_tokens"):
        return True
    return any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS)


def _redact_payload(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict[object, object] = {}
        for key, item in value.items():
            key_text = str(key)
            if _should_redact_key(key_text):
                redacted[key] = _REDACTED_VALUE
                continue
            redacted[key] = _redact_payload(item)
        return redacted
    if isinstance(value, list):
        return [_redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_payload(item) for item in value]
    return value

def _emit_json_output(
    *,
    rendered: dict[str, object],
    output: Path | None,
    as_json: bool,
) -> bool:
    sanitized = _redact_payload(rendered)
    assert isinstance(sanitized, dict)
    if output is not None:
        _write_json(output, sanitized)
    if as_json:
        print(json.dumps(sanitized, indent=2))
        return True
    return False


def _emit_listing_json_output(
    *,
    rendered: dict[str, object],
    output: Path | None,
    as_json: bool,
) -> bool:
    return _emit_json_output(
        rendered=rendered,
        output=output,
        as_json=as_json,
    )


def _emit_text_listing_output(
    *,
    workspace_id: str,
    collection_label: str,
    collection_count: int,
    summary_label: str,
    summary_count: int,
    sort_by: str,
    descending: bool,
    resolved_track_id: str | None,
    named_filters: list[tuple[str, object | None]],
    enabled_filters: list[tuple[str, bool]],
    extra_lines: list[str],
    item_lines: list[str],
    output: Path | None,
) -> None:
    print(f"Workspace: {workspace_id}")
    print(f"{collection_label}: {collection_count}")
    print(f"{summary_label}: {summary_count}")
    print(f"Sort: {sort_by}{' desc' if descending else ' asc'}")
    if resolved_track_id is not None:
        print(f"Track filter: {resolved_track_id}")
    for label, value in named_filters:
        if value is not None:
            print(f"{label}: {value}")
    for text, enabled in enabled_filters:
        if enabled:
            print(text)
    for line in extra_lines:
        print(line)
    for line in item_lines:
        print(line)
    if output is not None:
        print(f"Wrote output to {output}")


def _export_listing_payload(
    *,
    output: Path,
    explicit_format: str | None,
    format_version: str,
    rendered: dict[str, object],
    exported_at: str,
) -> str:
    if output.exists() and output.is_dir():
        raise SystemExit(f"Export output is a directory: {output}")
    export_payload = {
        "format_version": format_version,
        "exported_at": exported_at,
        **rendered,
    }
    return _write_structured_payload(
        output,
        export_payload,
        explicit_format=explicit_format,
    )


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    sanitized = _redact_payload(payload)
    assert isinstance(sanitized, dict)
    write_text_atomic(
        path,
        yaml.safe_dump(sanitized, sort_keys=False, default_flow_style=False),
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    sanitized = _redact_payload(payload)
    assert isinstance(sanitized, dict)
    write_text_atomic(path, json.dumps(sanitized, indent=2) + "\n")


def _write_structured_payload(
    path: Path,
    payload: dict[str, object],
    *,
    explicit_format: str | None = None,
) -> str:
    output_format = _infer_structured_output_format(
        path=path,
        explicit_format=explicit_format,
    )
    if output_format == "json":
        _write_json(path, payload)
    else:
        _write_yaml(path, payload)
    return output_format


def _write_text_file(path: Path, text: str) -> None:
    write_text_atomic(path, text)


def _write_shell_script(path: Path, shell_command: str) -> None:
    write_text_atomic(
        path,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"{shell_command}\n",
    )
    path.chmod(0o755)


def _infer_structured_output_format(
    *,
    path: Path,
    explicit_format: str | None,
) -> str:
    if explicit_format is not None:
        return explicit_format
    if path.suffix.lower() == ".json":
        return "json"
    return "yaml"
