"""Repo inspection and default selection for `autoharness guide`."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9_-]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "demo"


def detect_editable_surfaces(target_root: Path) -> list[str]:
    candidates = (
        "src",
        "prompts",
        "app",
        "agent",
        "agents",
        "lib",
        "packages",
        "server",
        "client",
    )
    detected = [name for name in candidates if (target_root / name).is_dir()]
    if detected:
        return detected
    return ["src"] if (target_root / "src").exists() else []


def detect_benchmark_command(target_root: Path) -> tuple[list[str], str]:
    makefile_path = target_root / "Makefile"
    if makefile_path.is_file():
        makefile_text = makefile_path.read_text(encoding="utf-8")
        if re.search(r"(?m)^test\s*:", makefile_text):
            return ["make", "test"], "Detected `test` target in Makefile."

    if any(
        (target_root / name).exists()
        for name in ("pytest.ini", "tox.ini", "conftest.py", "tests")
    ) or (target_root / "pyproject.toml").is_file():
        return ["pytest", "-q"], "Detected a Python test layout."

    package_json = target_root / "package.json"
    if package_json.is_file():
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        scripts = payload.get("scripts") if isinstance(payload, dict) else None
        if isinstance(scripts, dict) and isinstance(scripts.get("test"), str):
            return ["npm", "test", "--", "--runInBand"], "Detected an npm test script."

    return (
        ["python", "-c", "print('replace with your benchmark command')"],
        "Could not confidently detect a benchmark command; wrote a placeholder.",
    )


def default_generator_selection(
    *,
    assistant: str | None,
) -> tuple[str, dict[str, object]]:
    if assistant == "codex":
        return "codex_cli", {"sandbox": "read-only"}
    if assistant == "claude":
        return "claude_code", {}
    if os.environ.get("AUTOHARNESS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY"):
        return "openai_responses", {"proposal_scope": "balanced"}
    return "failure_summary", {}
