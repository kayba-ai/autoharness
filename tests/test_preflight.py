from __future__ import annotations

import sys
from pathlib import Path

import pytest

from autoharness.preflight import (
    adapter_recommended_preflight_checks,
    available_preflight_checks,
    build_preflight_cache_key,
    preflight_check_catalog,
    resolve_effective_preflight_commands,
    resolve_preflight_commands,
    run_preflight_validation,
    stage_default_preflight_checks,
)


def test_available_preflight_checks_exposes_builtin_catalog() -> None:
    assert available_preflight_checks() == (
        "mypy_quick",
        "package_build",
        "pytest_collect",
        "pytest_quick",
        "pytest_smoke",
        "python_compile",
        "python_import_smoke",
        "ruff_check",
    )


def test_resolve_preflight_commands_expands_builtin_checks() -> None:
    commands = resolve_preflight_commands(
        commands=["echo ok"],
        checks=["python_compile", "pytest_collect"],
    )

    assert commands[0] == "echo ok"
    assert "compileall ." in commands[1]
    assert "pytest --collect-only -q" in commands[2]


def test_resolve_preflight_commands_rejects_unknown_checks() -> None:
    with pytest.raises(ValueError, match="Unsupported preflight check"):
        resolve_preflight_commands(commands=[], checks=["missing"])


def test_preflight_check_catalog_renders_descriptions_and_commands() -> None:
    catalog = preflight_check_catalog()

    assert [entry["check_id"] for entry in catalog] == list(available_preflight_checks())
    assert catalog[0]["description"]
    assert "python -m compileall ." in next(
        entry["command"] for entry in catalog if entry["check_id"] == "python_compile"
    )
    pytest_smoke = next(
        entry for entry in catalog if entry["check_id"] == "pytest_smoke"
    )
    assert pytest_smoke["recommended_adapters"] == ["pytest"]


def test_resolve_effective_preflight_commands_uses_stage_and_adapter_defaults() -> None:
    screening = resolve_effective_preflight_commands(
        commands=[],
        checks=[],
        stage="screening",
        adapter_id="generic_command",
    )
    assert screening["selected_checks"] == ["python_compile"]
    assert screening["resolution_source"] == "stage_adapter_defaults"

    pytest_validation = resolve_effective_preflight_commands(
        commands=[],
        checks=[],
        stage="validation",
        adapter_id="pytest",
    )
    assert pytest_validation["selected_checks"] == [
        "python_compile",
        "python_import_smoke",
        "pytest_smoke",
    ]


def test_stage_and_adapter_preflight_defaults_are_exposed() -> None:
    assert stage_default_preflight_checks("screening") == ("python_compile",)
    assert adapter_recommended_preflight_checks(
        adapter_id="pytest",
        stage="validation",
    ) == ("pytest_smoke",)


def test_run_preflight_validation_can_reuse_cache(tmp_path: Path) -> None:
    counter_path = tmp_path / "counter.txt"
    script_path = tmp_path / "count.py"
    script_path.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"path = Path({str(counter_path)!r})",
                "current = int(path.read_text(encoding='utf-8')) if path.exists() else 0",
                "path.write_text(str(current + 1), encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cache_key = build_preflight_cache_key(
        cwd=tmp_path,
        commands=[f"{sys.executable} {script_path}"],
        timeout_seconds=30,
        changed_paths=[],
    )
    assert isinstance(cache_key, str)

    first = run_preflight_validation(
        commands=[f"{sys.executable} {script_path}"],
        cwd=tmp_path,
        timeout_seconds=30,
        cache_dir=tmp_path / "cache",
        cache_key=cache_key,
    )
    second = run_preflight_validation(
        commands=[f"{sys.executable} {script_path}"],
        cwd=tmp_path,
        timeout_seconds=30,
        cache_dir=tmp_path / "cache",
        cache_key=cache_key,
    )

    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert counter_path.read_text(encoding="utf-8") == "1"
