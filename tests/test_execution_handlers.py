import json
from pathlib import Path

import pytest
import yaml

from autoharness.cli import main
from autoharness.execution_support import (
    _compose_benchmark_config,
    _load_iteration_plan,
    _planned_iteration_argv,
    _planned_iteration_cwd,
)


class _FakeAdapter:
    def starter_config(self, *, preset: str) -> dict[str, object]:
        assert preset == "promotion"
        return {
            "agent_dir": "agents/default",
            "benchmark_args": {"limit": 4, "tags": ["base"]},
        }


def test_compose_benchmark_config_merges_preset_file_and_inline_overrides(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_args": {"limit": 8},
                "agent_name": "File Agent",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    rendered = _compose_benchmark_config(
        adapter=_FakeAdapter(),
        config_path=config_path,
        selected_preset="promotion",
        inline_overrides=[
            "benchmark_args.limit=12",
            "benchmark_args.mode=smoke",
            "agent_dir=agents/inline",
        ],
    )

    assert rendered == {
        "agent_dir": "agents/inline",
        "agent_name": "File Agent",
        "benchmark_args": {
            "limit": 12,
            "tags": ["base"],
            "mode": "smoke",
        },
    }


def test_load_iteration_plan_rejects_non_run_iteration_command(tmp_path: Path) -> None:
    plan_path = tmp_path / "bad_plan.json"
    plan_path.write_text(
        """
{
  "suggested_command": ["autoharness", "show-record", "--record-id", "rec_0001"]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        SystemExit,
        match="Iteration plan must contain an `autoharness run-iteration` command",
    ):
        _load_iteration_plan(plan_path)


def test_planned_iteration_helpers_return_argv_and_resolve_cwd(tmp_path: Path) -> None:
    planning_cwd = tmp_path / "cwd"
    planning_cwd.mkdir()
    plan = {
        "suggested_command": [
            "autoharness",
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
        ],
        "planning_cwd": str(planning_cwd),
    }

    assert _planned_iteration_argv(plan) == [
        "run-iteration",
        "--workspace-id",
        "demo",
        "--adapter",
        "generic_command",
    ]
    assert _planned_iteration_cwd(plan, plan_path=tmp_path / "plan.json") == planning_cwd


def test_list_and_show_preflight_checks_commands(capsys) -> None:
    capsys.readouterr()
    assert main(["list-preflight-checks", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["check_total"] >= 3
    assert any(item["check_id"] == "python_compile" for item in listed["checks"])

    capsys.readouterr()
    assert main(["show-preflight-check", "--check", "python_compile", "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["check_id"] == "python_compile"
    assert "compileall" in shown["command"]
