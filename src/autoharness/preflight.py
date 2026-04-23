"""Cheap preflight validation helpers run before benchmark execution."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .plugins import plugin_preflight_checks


_MAX_CAPTURE_CHARS = 4000
_PYTHON_IMPORT_SMOKE_SCRIPT = """
from importlib import import_module
from pathlib import Path
import sys

root = Path('.').resolve()
ignored = {
    '.git',
    '.autoharness',
    '.venv',
    'node_modules',
    '__pycache__',
    '.pytest_cache',
}
modules = []
for entry in sorted(root.iterdir()):
    if entry.name in ignored or entry.name.startswith('.'):
        continue
    if entry.is_file() and entry.suffix == '.py' and entry.name != '__init__.py':
        modules.append(entry.stem)
        continue
    if not entry.is_dir():
        continue
    if (entry / '__init__.py').exists():
        modules.append(entry.name)

for module_name in modules:
    import_module(module_name)

print(f"imported {len(modules)} modules")
"""
_PACKAGE_BUILD_SMOKE_SCRIPT = """
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path('.').resolve()
if not any((root / name).exists() for name in ('pyproject.toml', 'setup.py', 'setup.cfg')):
    print('no package build metadata found')
    raise SystemExit(0)

with tempfile.TemporaryDirectory() as output_dir:
    subprocess.run(
        [
            sys.executable,
            '-m',
            'build',
            '--sdist',
            '--wheel',
            '--outdir',
            output_dir,
        ],
        check=True,
        cwd=str(root),
    )

print('package build smoke passed')
"""
_BUILTIN_PREFLIGHT_CHECKS: dict[str, dict[str, object]] = {
    "python_compile": {
        "description": "Compile Python sources under the target root to catch syntax errors cheaply.",
        "argv": [sys.executable, "-m", "compileall", "."],
    },
    "pytest_collect": {
        "description": "Run pytest collection only, without executing tests, to catch import and discovery failures.",
        "argv": [sys.executable, "-m", "pytest", "--collect-only", "-q"],
    },
    "pytest_quick": {
        "description": "Run a quick pytest pass and stop on the first failure.",
        "argv": [sys.executable, "-m", "pytest", "-q", "-x", "--maxfail=1"],
    },
    "pytest_smoke": {
        "description": "Run one short pytest smoke pass against the current target root.",
        "argv": [sys.executable, "-m", "pytest", "-q", "--maxfail=1"],
    },
    "ruff_check": {
        "description": "Run Ruff against the current target root when Ruff is available.",
        "argv": [sys.executable, "-m", "ruff", "check", "."],
    },
    "mypy_quick": {
        "description": "Run a lightweight mypy pass with missing-import noise suppressed.",
        "argv": [
            sys.executable,
            "-m",
            "mypy",
            ".",
            "--follow-imports=silent",
            "--ignore-missing-imports",
            "--hide-error-context",
            "--no-error-summary",
        ],
    },
    "python_import_smoke": {
        "description": "Import top-level Python modules and packages under the target root.",
        "argv": [sys.executable, "-c", _PYTHON_IMPORT_SMOKE_SCRIPT],
    },
    "package_build": {
        "description": "Build the local package when build metadata is present.",
        "argv": [sys.executable, "-c", _PACKAGE_BUILD_SMOKE_SCRIPT],
    },
}
_STAGE_DEFAULT_PREFLIGHT_CHECKS: dict[str, tuple[str, ...]] = {
    "screening": ("python_compile",),
    "validation": ("python_compile", "python_import_smoke"),
    "holdout": ("python_compile", "python_import_smoke"),
    "transfer": ("python_compile", "python_import_smoke"),
}
_ADAPTER_STAGE_RECOMMENDED_PREFLIGHT_CHECKS: dict[str, dict[str, tuple[str, ...]]] = {
    "pytest": {
        "screening": ("pytest_collect",),
        "validation": ("pytest_smoke",),
        "holdout": ("pytest_smoke",),
        "transfer": ("pytest_smoke",),
    },
}
_PREFLIGHT_CACHE_FORMAT_VERSION = "autoharness.preflight_cache.v1"


def _preflight_check_registry() -> dict[str, dict[str, object]]:
    registry = {
        check_id: dict(entry) for check_id, entry in _BUILTIN_PREFLIGHT_CHECKS.items()
    }
    for check_id, entry in plugin_preflight_checks().items():
        registry[check_id] = dict(entry)
    return registry


def _check_entry_command(entry: dict[str, object], *, check_id: str) -> str:
    argv = entry.get("argv")
    if isinstance(argv, list):
        return shlex.join([str(item) for item in argv])
    command = entry.get("command")
    if isinstance(command, str) and command.strip():
        return command.strip()
    raise ValueError(f"Unsupported preflight check `{check_id}`.")


def _truncate_output(text: str) -> tuple[str, bool]:
    if len(text) <= _MAX_CAPTURE_CHARS:
        return text, False
    return text[:_MAX_CAPTURE_CHARS], True


def _argv_for_command(raw_command: str) -> list[str]:
    try:
        argv = shlex.split(raw_command)
    except ValueError as exc:
        raise ValueError(f"Invalid preflight command `{raw_command}`: {exc}") from exc
    if not argv:
        raise ValueError("Preflight commands may not be empty.")
    return argv


def available_preflight_checks() -> tuple[str, ...]:
    return tuple(sorted(_preflight_check_registry()))


def stage_default_preflight_checks(stage: str | None) -> tuple[str, ...]:
    if stage is None:
        return ()
    selected = list(_STAGE_DEFAULT_PREFLIGHT_CHECKS.get(str(stage), ()))
    for check_id, entry in plugin_preflight_checks().items():
        default_stages = entry.get("default_stages")
        if (
            isinstance(default_stages, list)
            and str(stage) in [str(item) for item in default_stages]
            and check_id not in selected
        ):
            selected.append(check_id)
    return tuple(selected)


def adapter_recommended_preflight_checks(
    *,
    adapter_id: str | None,
    stage: str | None,
) -> tuple[str, ...]:
    if adapter_id is None or stage is None:
        return ()
    selected = list(
        _ADAPTER_STAGE_RECOMMENDED_PREFLIGHT_CHECKS.get(str(adapter_id), {}).get(
            str(stage),
            (),
        )
    )
    for check_id, entry in plugin_preflight_checks().items():
        recommended_adapters = entry.get("recommended_adapters")
        if (
            isinstance(recommended_adapters, list)
            and str(adapter_id) in [str(item) for item in recommended_adapters]
            and check_id not in selected
        ):
            selected.append(check_id)
    return tuple(selected)


def preflight_check_catalog() -> list[dict[str, object]]:
    rendered: list[dict[str, object]] = []
    for check_id in available_preflight_checks():
        entry = _preflight_check_registry()[check_id]
        description = entry.get("description")
        default_stages = [
            stage
            for stage, checks in _STAGE_DEFAULT_PREFLIGHT_CHECKS.items()
            if check_id in checks
        ]
        plugin_default_stages = entry.get("default_stages")
        if isinstance(plugin_default_stages, list):
            for stage in plugin_default_stages:
                stage_value = str(stage)
                if stage_value not in default_stages:
                    default_stages.append(stage_value)
        recommended_adapters = [
            adapter_id
            for adapter_id, checks_by_stage in _ADAPTER_STAGE_RECOMMENDED_PREFLIGHT_CHECKS.items()
            if any(check_id in checks for checks in checks_by_stage.values())
        ]
        plugin_recommended_adapters = entry.get("recommended_adapters")
        if isinstance(plugin_recommended_adapters, list):
            for adapter_id in plugin_recommended_adapters:
                adapter_value = str(adapter_id)
                if adapter_value not in recommended_adapters:
                    recommended_adapters.append(adapter_value)
        rendered.append(
            {
                "check_id": check_id,
                "description": str(description) if isinstance(description, str) else "",
                "command": _check_entry_command(entry, check_id=check_id),
                "default_stages": default_stages,
                "recommended_adapters": recommended_adapters,
            }
        )
    return rendered


def resolve_preflight_commands(
    *,
    commands: list[str],
    checks: list[str],
) -> list[str]:
    resolved = list(commands)
    registry = _preflight_check_registry()
    for check_id in checks:
        entry = registry.get(check_id)
        if entry is None:
            raise ValueError(f"Unsupported preflight check `{check_id}`.")
        resolved.append(_check_entry_command(entry, check_id=check_id))
    return resolved


def resolve_effective_preflight_commands(
    *,
    commands: list[str],
    checks: list[str],
    stage: str | None = None,
    adapter_id: str | None = None,
) -> dict[str, object]:
    selected_checks: list[str] = []
    resolution_source = "explicit"

    if commands or checks:
        for check_id in checks:
            if check_id not in selected_checks:
                selected_checks.append(check_id)
    else:
        resolution_source = "none"
        for check_id in stage_default_preflight_checks(stage):
            if check_id not in selected_checks:
                selected_checks.append(check_id)
        for check_id in adapter_recommended_preflight_checks(
            adapter_id=adapter_id,
            stage=stage,
        ):
            if check_id not in selected_checks:
                selected_checks.append(check_id)
        if selected_checks:
            resolution_source = "stage_adapter_defaults"

    resolved_commands = resolve_preflight_commands(
        commands=commands,
        checks=selected_checks,
    )
    return {
        "selected_checks": selected_checks,
        "resolved_commands": resolved_commands,
        "resolution_source": resolution_source,
        "stage_default_checks": list(stage_default_preflight_checks(stage)),
        "adapter_recommended_checks": list(
            adapter_recommended_preflight_checks(
                adapter_id=adapter_id,
                stage=stage,
            )
        ),
    }


def build_preflight_cache_key(
    *,
    cwd: Path,
    commands: list[str],
    timeout_seconds: int,
    changed_paths: list[str] | tuple[str, ...] | None,
) -> str | None:
    if changed_paths is None:
        return None
    changed_path_fingerprints = _fingerprint_changed_paths(
        cwd=cwd,
        changed_paths=tuple(changed_paths),
    )
    payload = {
        "cwd": str(cwd.resolve()),
        "commands": list(commands),
        "timeout_seconds": timeout_seconds,
        "changed_paths": changed_path_fingerprints,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def run_preflight_validation(
    *,
    commands: list[str],
    cwd: Path,
    timeout_seconds: int,
    cache_dir: Path | None = None,
    cache_key: str | None = None,
) -> dict[str, object]:
    if timeout_seconds < 1:
        raise ValueError("`preflight_timeout_seconds` must be at least 1.")

    if cache_dir is not None and cache_key is not None:
        cached_payload = _load_preflight_cache(cache_dir=cache_dir, cache_key=cache_key)
        if cached_payload is not None:
            cached_payload["cache_hit"] = True
            cached_payload["cache_key"] = cache_key
            cached_payload["cache_path"] = str(
                (cache_dir / f"{cache_key}.json").resolve()
            )
            return cached_payload

    command_results: list[dict[str, object]] = []
    passed_count = 0

    for raw_command in commands:
        argv = _argv_for_command(raw_command)
        started = time.monotonic()
        command_result: dict[str, object] = {
            "command": raw_command,
            "argv": argv,
            "cwd": str(cwd),
            "timeout_seconds": timeout_seconds,
        }
        try:
            completed = subprocess.run(
                argv,
                cwd=str(cwd),
                text=True,
                capture_output=True,
                check=False,
                timeout=timeout_seconds,
            )
            duration_seconds = time.monotonic() - started
            stdout_text, stdout_truncated = _truncate_output(completed.stdout or "")
            stderr_text, stderr_truncated = _truncate_output(completed.stderr or "")
            success = completed.returncode == 0
            if success:
                passed_count += 1
            command_result.update(
                {
                    "success": success,
                    "timed_out": False,
                    "exit_code": completed.returncode,
                    "duration_seconds": duration_seconds,
                    "stdout": stdout_text,
                    "stdout_truncated": stdout_truncated,
                    "stderr": stderr_text,
                    "stderr_truncated": stderr_truncated,
                    "error": None,
                }
            )
        except FileNotFoundError as exc:
            duration_seconds = time.monotonic() - started
            command_result.update(
                {
                    "success": False,
                    "timed_out": False,
                    "exit_code": None,
                    "duration_seconds": duration_seconds,
                    "stdout": "",
                    "stdout_truncated": False,
                    "stderr": "",
                    "stderr_truncated": False,
                    "error": str(exc),
                }
            )
        except subprocess.TimeoutExpired as exc:
            duration_seconds = time.monotonic() - started
            stdout_text, stdout_truncated = _truncate_output(exc.stdout or "")
            stderr_text, stderr_truncated = _truncate_output(exc.stderr or "")
            command_result.update(
                {
                    "success": False,
                    "timed_out": True,
                    "exit_code": None,
                    "duration_seconds": duration_seconds,
                    "stdout": stdout_text,
                    "stdout_truncated": stdout_truncated,
                    "stderr": stderr_text,
                    "stderr_truncated": stderr_truncated,
                    "error": f"Preflight command timed out after {timeout_seconds}s.",
                }
            )
        command_results.append(command_result)

    payload = {
        "format_version": "autoharness.preflight_validation.v1",
        "cwd": str(cwd),
        "timeout_seconds": timeout_seconds,
        "command_count": len(command_results),
        "passed_count": passed_count,
        "failed_count": len(command_results) - passed_count,
        "all_passed": passed_count == len(command_results),
        "commands": command_results,
        "cache_hit": False,
    }
    if cache_dir is not None and cache_key is not None:
        payload["cache_key"] = cache_key
        payload["cache_path"] = str((cache_dir / f"{cache_key}.json").resolve())
        if payload["all_passed"] is True:
            _write_preflight_cache(
                cache_dir=cache_dir,
                cache_key=cache_key,
                payload=payload,
            )
    return payload


def _fingerprint_changed_paths(
    *,
    cwd: Path,
    changed_paths: tuple[str, ...],
) -> list[dict[str, object]]:
    fingerprints: list[dict[str, object]] = []
    for raw_path in changed_paths:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = cwd / candidate
        fingerprint = {
            "path": str(candidate.resolve().relative_to(cwd.resolve()))
            if candidate.exists()
            else str(Path(raw_path).as_posix()),
            "exists": candidate.exists(),
            "is_dir": candidate.is_dir(),
        }
        if candidate.is_file():
            content = candidate.read_bytes()
            fingerprint["size"] = len(content)
            fingerprint["sha256"] = hashlib.sha256(content).hexdigest()
        elif candidate.is_dir():
            fingerprint["children"] = sorted(
                str(path.relative_to(candidate).as_posix())
                for path in candidate.rglob("*")
                if path.is_file()
            )
        fingerprints.append(fingerprint)
    return fingerprints


def _load_preflight_cache(
    *,
    cache_dir: Path,
    cache_key: str,
) -> dict[str, object] | None:
    cache_path = cache_dir / f"{cache_key}.json"
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("cache_format_version") != _PREFLIGHT_CACHE_FORMAT_VERSION:
        return None
    cached_payload = dict(payload.get("preflight_validation", {}))
    if not isinstance(cached_payload, dict):
        return None
    return cached_payload if cached_payload.get("all_passed") is True else None


def _write_preflight_cache(
    *,
    cache_dir: Path,
    cache_key: str,
    payload: dict[str, object],
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{cache_key}.json"
    cache_payload = {
        "cache_format_version": _PREFLIGHT_CACHE_FORMAT_VERSION,
        "cached_at_unix_seconds": int(time.time()),
        "preflight_validation": payload,
    }
    cache_path.write_text(json.dumps(cache_payload, indent=2) + "\n", encoding="utf-8")
