import json
import os
from pathlib import Path

import pytest
import yaml

from autoharness.cli import main


def test_list_benchmarks_json_filters_to_implemented_entries(
    tmp_path: Path,
    capsys,
) -> None:
    output_path = tmp_path / "benchmarks.json"

    capsys.readouterr()
    assert (
        main(
            [
                "list-benchmarks",
                "--implemented-only",
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload

    benchmark_ids = {entry["adapter_id"] for entry in payload["benchmarks"]}
    assert "hal" in benchmark_ids
    assert "generic_command" in benchmark_ids
    assert "appworld" not in benchmark_ids

    hal_entry = next(
        entry for entry in payload["benchmarks"] if entry["adapter_id"] == "hal"
    )
    assert hal_entry["implemented"] is True
    assert hal_entry["capabilities"]["required_fields"] == [
        "benchmark",
        "agent_dir",
        "agent_function",
        "agent_name",
    ]
    assert hal_entry["capabilities"]["native_metrics_artifact_fields"] == [
        "summary_json_path",
        "result_json_path",
        "results_json_path",
        "artifact_json_path",
    ]


def test_show_benchmark_renders_adapter_capabilities(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "hal.json"

    capsys.readouterr()
    assert (
        main(
            [
                "show-benchmark",
                "--adapter",
                "hal",
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    rendered = json.loads(capsys.readouterr().out)
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered
    assert rendered["adapter_id"] == "hal"
    assert rendered["implemented"] is True
    assert rendered["capabilities"]["default_task_identity_profile"] == {
        "match_key_field": "task_id",
        "tier_field": "tier",
        "weight_field": None,
        "tier_weights": {},
        "default_weight": 1.0,
    }
    assert rendered["capabilities"]["staging_profile"]["relative_path_fields"] == [
        "agent_dir"
    ]
    assert rendered["capabilities"]["supported_metrics_parser_formats"] == [
        "json_stdout",
        "json_file",
    ]
    assert rendered["capabilities"]["available_starter_presets"] == [
        "default",
        "search",
        "promotion",
        "native-artifact",
    ]
    assert rendered["capabilities"]["selected_starter_preset"] == "default"
    assert rendered["capabilities"]["starter_config"] == {
        "benchmark": "taubench_airline",
        "agent_dir": "agents/demo",
        "agent_function": "agent.run",
        "agent_name": "Demo Agent",
        "benchmark_args": {"split": "test"},
    }


def test_show_benchmark_for_catalog_only_entry(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "appworld.json"

    capsys.readouterr()
    assert (
        main(
            [
                "show-benchmark",
                "--adapter",
                "appworld",
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    rendered = json.loads(capsys.readouterr().out)
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered
    assert rendered["adapter_id"] == "appworld"
    assert rendered["implemented"] is False
    assert rendered["capabilities"] is None


def test_show_benchmark_renders_named_preset(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "harbor_preset.json"

    capsys.readouterr()
    assert (
        main(
            [
                "show-benchmark",
                "--adapter",
                "harbor",
                "--preset",
                "native-artifact",
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    rendered = json.loads(capsys.readouterr().out)
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered
    assert rendered["capabilities"]["selected_starter_preset"] == "native-artifact"
    assert rendered["capabilities"]["starter_config"] == {
        "dataset": "terminal-bench/terminal-bench-2",
        "model": "openai/gpt-4.1",
        "agent": "codex-cli",
        "summary_json_path": "artifacts/harbor_summary.json",
        "result_json_path": "artifacts/harbor_results.json",
    }


def test_init_benchmark_config_writes_yaml_scaffold(tmp_path: Path) -> None:
    output_path = tmp_path / "tau2.yaml"

    assert (
        main(
            [
                "init-benchmark-config",
                "--adapter",
                "tau2_bench",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    payload = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "domain": "airline",
        "agent": "llm",
        "agent_llm": "gpt-4.1-mini",
        "task_split_name": "test",
        "num_trials": 1,
        "save_to": "demo-run",
    }


def test_init_benchmark_config_writes_json_when_requested(tmp_path: Path) -> None:
    output_path = tmp_path / "harbor.json"

    assert (
        main(
            [
                "init-benchmark-config",
                "--adapter",
                "harbor",
                "--output",
                str(output_path),
                "--format",
                "json",
            ]
        )
        == 0
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "dataset": "terminal-bench/terminal-bench-2",
        "model": "openai/gpt-4.1",
        "agent": "codex-cli",
        "num_trials": 1,
    }


def test_init_benchmark_config_writes_named_preset_with_default_filename(
    tmp_path: Path,
) -> None:
    current_dir = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert (
            main(
                [
                    "init-benchmark-config",
                    "--adapter",
                    "hal",
                    "--preset",
                    "promotion",
                ]
            )
            == 0
        )
    finally:
        os.chdir(current_dir)

    output_path = tmp_path / "hal.promotion.yaml"
    payload = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert payload == {
        "benchmark": "taubench_airline",
        "agent_dir": "agents/demo",
        "agent_function": "agent.run",
        "agent_name": "Demo Agent",
        "benchmark_args": {"split": "test"},
        "docker": True,
    }


def test_init_benchmark_config_rejects_unknown_preset(tmp_path: Path) -> None:
    output_path = tmp_path / "bad.yaml"

    with pytest.raises(SystemExit, match="Unknown starter preset `does-not-exist`"):
        main(
            [
                "init-benchmark-config",
                "--adapter",
                "tau2_bench",
                "--preset",
                "does-not-exist",
                "--output",
                str(output_path),
            ]
        )


def test_show_benchmark_config_renders_effective_config_and_invocation(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = tmp_path / "generic.yaml"
    output_path = tmp_path / "generic_config_preview.json"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "config-preview",
                "command": ["python", "-c", "print('ok')"],
                "stage_overrides": {
                    "holdout": {
                        "command": ["python", "-c", "print('holdout')"],
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-benchmark-config",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--stage",
                "holdout",
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    rendered = json.loads(capsys.readouterr().out)
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered
    assert rendered["adapter_id"] == "generic_command"
    assert rendered["stage"] == "holdout"
    assert rendered["applied_stage_override"] is True
    assert rendered["effective_config"]["benchmark_name"] == "config-preview"
    assert rendered["planned_invocation"]["command"] == [
        "python",
        "-c",
        "print('holdout')",
    ]


def test_validate_benchmark_config_reports_invalid_config(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = tmp_path / "bad_generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "bad-config",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "validate-benchmark-config",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--json",
            ]
        )
        == 1
    )

    rendered = json.loads(capsys.readouterr().out)
    assert rendered["adapter_id"] == "generic_command"
    assert rendered["valid"] is False
    assert rendered["error_count"] == 1
    assert rendered["validation_errors"] == [
        "`command` must be a non-empty list of strings."
    ]
