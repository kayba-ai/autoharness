from __future__ import annotations

import json
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

import autoharness.adapters.base as adapters_base
import autoharness.campaign_handlers as campaign_handlers
import autoharness.campaign_runs as campaign_runs
import autoharness.plugins as plugins
from autoharness.cli import main
from autoharness.generators import (
    ProposalGenerationProcessError,
    ProposalGenerationProviderAuthError,
    ProposalGenerationProviderError,
    ProposalGenerationProviderRateLimitError,
    ProposalGenerationProviderTransportError,
    ProposalGenerationTimeoutError,
)
from autoharness.proposals import load_proposal
from autoharness.tracking import (
    create_benchmark_record,
    load_workspace_state,
    persist_benchmark_record,
    save_workspace_state,
)


def _write_local_command_generator_script(
    path: Path,
    *,
    input_tokens: int = 2,
    output_tokens: int = 3,
    total_tokens: int = 5,
    cost_usd: float = 0.11,
) -> None:
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import sys",
                "payload = json.load(sys.stdin)",
                "request = payload['request']",
                "context = payload['context']",
                "result = {",
                "    'hypothesis': f\"Usage candidate {request['candidate_index']}\",",
                "    'summary': f\"Usage proposal {request['candidate_index']}\",",
                "    'intervention_class': request.get('intervention_class') or 'source',",
                "    'operations': [",
                "        {",
                "            'type': 'write_file',",
                "            'path': f\".autoharness/generated/usage_{request['candidate_index']}.txt\",",
                "            'content': f\"workspace={context['workspace_id']}\\ntrack={context['track_id']}\\n\",",
                "        }",
                "    ],",
                "    'metadata': {",
                "        'usage': {",
                f"            'input_tokens': {input_tokens},",
                f"            'output_tokens': {output_tokens},",
                f"            'total_tokens': {total_tokens},",
                f"            'cost_usd': {cost_usd},",
                "        }",
                "    },",
                "}",
                "print(json.dumps(result))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_run_and_resume_campaign(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-smoke",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_paths = []
    for filename in ("alpha.txt", "beta.txt"):
        edit_plan_path = tmp_path / f"{filename}.yaml"
        edit_plan_path.write_text(
            yaml.safe_dump(
                {
                    "operations": [
                        {
                            "type": "write_file",
                            "path": filename,
                            "content": f"{filename}\n",
                        }
                    ]
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        edit_plan_paths.append(edit_plan_path)

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_paths[0]),
                "--edit-plan",
                str(edit_plan_paths[1]),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    campaign_id = campaign["campaign_run_id"]
    assert campaign["status"] == "paused"
    assert campaign["stop_reason"] == "proposal_budget_reached"
    assert campaign["strategy"] == "sequential_manual"
    assert campaign["candidate_source_mode"] == "manual_edit_plan_list"
    assert campaign["next_candidate_index"] == 1
    assert campaign["max_benchmark_process_retries"] is None
    assert campaign["max_benchmark_signal_retries"] is None
    assert campaign["max_benchmark_parse_retries"] is None
    assert campaign["max_benchmark_adapter_validation_retries"] is None
    assert len(campaign["decision_log"]) >= 3
    assert campaign["candidates"][0]["proposal_id"] is not None
    assert campaign["candidates"][0]["record_id"] is not None
    assert campaign["candidates"][1]["status"] == "pending"

    capsys.readouterr()
    assert (
        main(
            [
                "resume-campaign",
                "--workspace-id",
                "demo",
                "--campaign-id",
                campaign_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["campaign"]["status"] == "completed"
    assert resumed["campaign"]["stop_reason"] == "proposal_list_exhausted"
    assert resumed["campaign"]["next_candidate_index"] == 2
    assert resumed["campaign"]["candidates"][1]["proposal_id"] is not None
    assert resumed["campaign"]["candidates"][1]["record_id"] is not None

    capsys.readouterr()
    assert (
        main(
            [
                "show-campaigns",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    campaign_listing = json.loads(capsys.readouterr().out)
    assert [item["campaign_id"] for item in campaign_listing["campaigns"]] == [campaign_id]
    assert campaign_listing["campaign_total"] == 1
    assert campaign_listing["search_policy_mix"]["by_strategy"] == {
        "sequential_manual": 1
    }
    assert campaign_listing["search_policy_mix"]["by_max_generation_retries"] == {
        "(unset)": 1
    }
    assert campaign_listing["search_policy_mix"][
        "by_max_generation_timeout_retries"
    ] == {"(unset)": 1}
    assert campaign_listing["search_policy_mix"][
        "by_max_generation_provider_retries"
    ] == {"(unset)": 1}
    assert campaign_listing["search_policy_mix"][
        "by_max_generation_process_retries"
    ] == {"(unset)": 1}
    assert campaign_listing["search_policy_mix"]["by_max_execution_retries"] == {
        "(unset)": 1
    }
    assert campaign_listing["search_policy_mix"]["by_max_benchmark_process_retries"] == {
        "(unset)": 1
    }
    assert campaign_listing["search_policy_mix"]["by_max_benchmark_signal_retries"] == {
        "(unset)": 1
    }
    assert campaign_listing["search_policy_mix"]["by_max_benchmark_parse_retries"] == {
        "(unset)": 1
    }
    assert campaign_listing["search_policy_mix"][
        "by_max_benchmark_adapter_validation_retries"
    ] == {"(unset)": 1}
    assert campaign_listing["search_policy_mix"]["by_max_benchmark_timeout_retries"] == {
        "(unset)": 1
    }
    assert campaign_listing["search_policy_mix"]["by_max_benchmark_command_retries"] == {
        "(unset)": 1
    }
    assert campaign_listing["search_policy_mix"]["by_max_inconclusive_retries"] == {
        "(unset)": 1
    }

    workspace_report_path = tmp_path / "workspace-campaign-report.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-workspace-campaign-report",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(workspace_report_path),
            ]
        )
        == 0
    )
    workspace_report = yaml.safe_load(
        workspace_report_path.read_text(encoding="utf-8")
    )
    assert workspace_report["format_version"] == "autoharness.workspace_campaign_report.v1"
    assert workspace_report["workspace_id"] == "demo"
    assert workspace_report["campaign_total"] == 1
    assert workspace_report["search_policy_mix"]["by_strategy"] == {
        "sequential_manual": 1
    }
    assert workspace_report["search_policy_mix"]["by_max_generation_retries"] == {
        "(unset)": 1
    }
    assert workspace_report["search_policy_mix"][
        "by_max_generation_timeout_retries"
    ] == {"(unset)": 1}
    assert workspace_report["search_policy_mix"][
        "by_max_generation_provider_retries"
    ] == {"(unset)": 1}
    assert workspace_report["search_policy_mix"][
        "by_max_generation_process_retries"
    ] == {"(unset)": 1}
    assert workspace_report["search_policy_mix"]["by_max_execution_retries"] == {
        "(unset)": 1
    }
    assert workspace_report["search_policy_mix"]["by_max_benchmark_process_retries"] == {
        "(unset)": 1
    }
    assert workspace_report["search_policy_mix"]["by_max_benchmark_signal_retries"] == {
        "(unset)": 1
    }
    assert workspace_report["search_policy_mix"]["by_max_benchmark_parse_retries"] == {
        "(unset)": 1
    }
    assert workspace_report["search_policy_mix"][
        "by_max_benchmark_adapter_validation_retries"
    ] == {"(unset)": 1}
    assert workspace_report["search_policy_mix"]["by_max_benchmark_timeout_retries"] == {
        "(unset)": 1
    }
    assert workspace_report["search_policy_mix"]["by_max_benchmark_command_retries"] == {
        "(unset)": 1
    }
    assert workspace_report["search_policy_mix"]["by_max_inconclusive_retries"] == {
        "(unset)": 1
    }

    capsys.readouterr()
    assert (
        main(
            [
                "show-campaign-report-file",
                str(workspace_report_path),
                "--json",
            ]
        )
        == 0
    )
    shown_workspace_report = json.loads(capsys.readouterr().out)
    assert shown_workspace_report["report_type"] == "workspace_campaign_report"
    assert shown_workspace_report["workspace_id"] == "demo"
    assert shown_workspace_report["campaign_total"] == 1

    capsys.readouterr()
    assert main(["show-artifact-file", str(workspace_report_path), "--json"]) == 0
    generic_shown = json.loads(capsys.readouterr().out)
    assert generic_shown["report_type"] == "workspace_campaign_report"
    assert generic_shown["workspace_id"] == "demo"

    capsys.readouterr()
    assert (
        main(
            [
                "validate-campaign-report-file",
                str(workspace_report_path),
                "--json",
            ]
        )
        == 0
    )
    validated_workspace_report = json.loads(capsys.readouterr().out)
    assert validated_workspace_report["valid"] is True

    capsys.readouterr()
    assert (
        main(["validate-artifact-file", str(workspace_report_path), "--json"]) == 0
    )
    generic_validated = json.loads(capsys.readouterr().out)
    assert generic_validated["report_type"] == "workspace_campaign_report"
    assert generic_validated["valid"] is True

    capsys.readouterr()
    assert (
        main(
            [
                "show-campaign",
                "--workspace-id",
                "demo",
                "--campaign-id",
                campaign_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["campaign"]["campaign_run_id"] == campaign_id
    assert shown["campaign"]["status"] == "completed"
    assert shown["success_count"] == 2

    capsys.readouterr()
    assert (
        main(
            [
                "show-campaign-artifacts",
                "--workspace-id",
                "demo",
                "--campaign-id",
                campaign_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    artifacts = json.loads(capsys.readouterr().out)
    assert len(artifacts["proposal_artifacts"]) == 2
    assert len(artifacts["record_artifacts"]) == 2
    assert len(artifacts["iteration_artifacts"]) == 2
    assert artifacts["promotion_artifacts"] == []
    assert artifacts["champion_artifacts"] is None

    report_path = tmp_path / "campaign-report.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-campaign-report",
                "--workspace-id",
                "demo",
                "--campaign-id",
                campaign_id,
                "--root",
                str(workspaces_root),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    report = yaml.safe_load(report_path.read_text(encoding="utf-8"))
    assert report["format_version"] == "autoharness.campaign_report.v1"
    assert report["campaign"]["campaign_run_id"] == campaign_id
    assert len(report["proposals"]) == 2
    assert len(report["records"]) == 2
    assert len(report["iterations"]) == 2
    assert report["promotions"] == []
    assert report["champion"] is None

    capsys.readouterr()
    assert main(["show-campaign-report-file", str(report_path), "--json"]) == 0
    shown_campaign_report = json.loads(capsys.readouterr().out)
    assert shown_campaign_report["report_type"] == "campaign_report"
    assert shown_campaign_report["campaign_id"] == campaign_id
    assert shown_campaign_report["proposal_total"] == 2

    capsys.readouterr()
    assert main(["validate-campaign-report-file", str(report_path), "--json"]) == 0
    validated_campaign_report = json.loads(capsys.readouterr().out)
    assert validated_campaign_report["valid"] is True

    bundle_dir = tmp_path / "campaign-bundle"
    capsys.readouterr()
    assert (
        main(
            [
                "export-campaign-bundle",
                "--workspace-id",
                "demo",
                "--campaign-id",
                campaign_id,
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_dir),
            ]
        )
        == 0
    )
    bundle_manifest = json.loads(
        (bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert bundle_manifest["format_version"] == "autoharness.campaign_bundle.v1"
    assert bundle_manifest["campaign_id"] == campaign_id
    assert bundle_manifest["artifacts"]["campaign_events_path"] == "campaign_events.jsonl"
    assert len(bundle_manifest["artifacts"]["proposal_dirs"]) == 2
    assert len(bundle_manifest["artifacts"]["record_paths"]) == 2
    assert len(bundle_manifest["artifacts"]["iteration_dirs"]) == 2

    capsys.readouterr()
    assert main(["show-bundle", str(bundle_dir), "--json"]) == 0
    bundle_view = json.loads(capsys.readouterr().out)
    assert bundle_view["bundle_type"] == "campaign_bundle"
    assert bundle_view["campaign_id"] == campaign_id
    assert bundle_view["proposal_total"] == 2

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_dir), "--json"]) == 0
    validation = json.loads(capsys.readouterr().out)
    assert validation["valid"] is True

    bundled_record_path = (
        bundle_dir / bundle_manifest["artifacts"]["record_paths"][0]["path"]
    )
    bundled_record_path.unlink()

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_dir), "--json"]) == 1
    invalid_validation = json.loads(capsys.readouterr().out)
    assert invalid_validation["valid"] is False


def test_run_campaign_blocks_auto_promotion_for_flaky_repeated_validation(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    counter_path = tmp_path / "repeat_counter.txt"
    config_path = tmp_path / "generic_flaky.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-flaky",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        f"from pathlib import Path; path = Path({str(counter_path)!r}); "
                        "count = int(path.read_text(encoding='utf-8')) if path.exists() else 0; "
                        "path.write_text(str(count + 1), encoding='utf-8'); "
                        "print(json.dumps({'pass_rate': 1.0, 'score': float(count)}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--repeat",
                "2",
                "--auto-promote",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]

    assert campaign["status"] == "completed"
    assert campaign["promoted_count"] == 0
    assert candidate["status"] == "success"
    assert candidate["promoted"] is False
    assert candidate["comparison_decision"] == "provisional_winner"
    assert not (
        workspaces_root / "demo" / "tracks" / "main" / "champion.json"
    ).exists()


def test_run_campaign_can_allow_flaky_auto_promotion_when_enabled(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    counter_path = tmp_path / "repeat_counter.txt"
    config_path = tmp_path / "generic_flaky.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-flaky-promote",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        f"from pathlib import Path; path = Path({str(counter_path)!r}); "
                        "count = int(path.read_text(encoding='utf-8')) if path.exists() else 0; "
                        "path.write_text(str(count + 1), encoding='utf-8'); "
                        "print(json.dumps({'pass_rate': 1.0, 'score': float(count)}))"
                    ),
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--repeat",
                "2",
                "--auto-promote",
                "--allow-flaky-promotion",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]

    assert campaign["status"] == "completed"
    assert campaign["promoted_count"] == 1
    assert candidate["status"] == "success"
    assert candidate["promoted"] is True
    assert candidate["comparison_decision"] == "promoted_without_prior_champion"
    assert (
        workspaces_root / "demo" / "tracks" / "main" / "champion.json"
    ).exists()


def test_run_campaign_stops_on_generation_token_budget(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    generator_script = tmp_path / "generator.py"
    generator_script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json, sys",
                "payload = json.load(sys.stdin)",
                "index = payload['request']['candidate_index']",
                "print(json.dumps({",
                "  'summary': f'candidate {index}',",
                "  'hypothesis': f'candidate {index}',",
                "  'intervention_class': 'source',",
                "  'operations': [",
                "    {'type': 'write_file', 'path': f'candidate_{index}.txt', 'content': 'ok\\n'}",
                "  ],",
                "  'metadata': {'usage': {'input_tokens': 1, 'output_tokens': 2, 'total_tokens': 3}}",
                "}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    generator_script.chmod(0o755)

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-budget",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--generator",
                "local_command",
                "--generator-option",
                f"command_path={generator_script}",
                "--max-generation-total-tokens",
                "2",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]

    assert campaign["stop_reason"] == "generation_token_budget_reached"
    assert rendered["resource_usage"]["generation_total_tokens"] == 3
    assert rendered["success_count"] == 1


def test_run_campaign_stops_on_benchmark_cost_budget(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic_cost.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-cost-budget",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 1.0, 'cost': 0.7}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_paths = []
    for filename in ("alpha.txt", "beta.txt", "gamma.txt"):
        edit_plan_path = tmp_path / f"{filename}.yaml"
        edit_plan_path.write_text(
            yaml.safe_dump(
                {
                    "operations": [
                        {
                            "type": "write_file",
                            "path": filename,
                            "content": f"{filename}\n",
                        }
                    ]
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        edit_plan_paths.append(edit_plan_path)

    command = [
        "run-campaign",
        "--workspace-id",
        "demo",
        "--adapter",
        "generic_command",
        "--config",
        str(config_path),
        "--target-root",
        str(target_root),
        "--max-benchmark-total-cost",
        "1.0",
        "--root",
        str(workspaces_root),
        "--json",
    ]
    for edit_plan_path in edit_plan_paths:
        command.extend(["--edit-plan", str(edit_plan_path)])

    capsys.readouterr()
    assert main(command) == 0
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]

    assert campaign["stop_reason"] == "benchmark_cost_budget_reached"
    assert rendered["success_count"] == 2
    assert rendered["resource_usage"]["benchmark_total_cost"] == pytest.approx(1.4)


def test_run_campaign_stops_on_failure_budget(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-fail",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "import sys; sys.exit(1)"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_paths = []
    for filename in ("alpha.txt", "beta.txt"):
        edit_plan_path = tmp_path / f"{filename}.yaml"
        edit_plan_path.write_text(
            yaml.safe_dump(
                {
                    "operations": [
                        {
                            "type": "write_file",
                            "path": filename,
                            "content": f"{filename}\n",
                        }
                    ]
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        edit_plan_paths.append(edit_plan_path)

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_paths[0]),
                "--edit-plan",
                str(edit_plan_paths[1]),
                "--max-failures",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["campaign"]["status"] == "failed"
    assert rendered["campaign"]["stop_reason"] == "failure_budget_reached"
    assert rendered["campaign"]["failure_count"] == 1
    assert rendered["campaign"]["next_candidate_index"] == 1
    assert rendered["campaign"]["candidates"][0]["status"] == "failed"
    assert rendered["campaign"]["candidates"][1]["status"] == "pending"


def test_run_campaign_auto_promotes_first_winner(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    promotion_root = tmp_path / "promoted"
    target_root.mkdir()
    promotion_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-promote",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--promotion-target-root",
                str(promotion_root),
                "--auto-promote",
                "--edit-plan",
                str(edit_plan_path),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    candidate = rendered["campaign"]["candidates"][0]
    assert rendered["campaign"]["promoted_count"] == 1
    assert candidate["promoted"] is True
    assert candidate["promotion_id"] is not None
    assert candidate["comparison_decision"] == "promoted_without_prior_champion"
    champion_manifest_path = (
        workspaces_root / "demo" / "tracks" / "main" / "champion.json"
    )
    assert champion_manifest_path.exists()

    capsys.readouterr()
    assert (
        main(
            [
                "show-campaign-artifacts",
                "--workspace-id",
                "demo",
                "--campaign-id",
                rendered["campaign"]["campaign_run_id"],
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    artifacts = json.loads(capsys.readouterr().out)
    assert len(artifacts["promotion_artifacts"]) == 1
    assert artifacts["champion_artifacts"]["promotion_id"] == candidate["promotion_id"]

    bundle_dir = tmp_path / "campaign-promoted-bundle"
    capsys.readouterr()
    assert (
        main(
            [
                "export-campaign-bundle",
                "--workspace-id",
                "demo",
                "--campaign-id",
                rendered["campaign"]["campaign_run_id"],
                "--root",
                str(workspaces_root),
                "--output",
                str(bundle_dir),
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert main(["show-bundle", str(bundle_dir), "--recursive", "--json"]) == 0
    recursive_view = json.loads(capsys.readouterr().out)
    assert recursive_view["bundle_type"] == "campaign_bundle"
    assert recursive_view["recursive"] is True
    assert recursive_view["nested_bundle_total"] == 1

    capsys.readouterr()
    assert main(["validate-bundle", str(bundle_dir), "--recursive", "--json"]) == 0
    recursive_validation = json.loads(capsys.readouterr().out)
    assert recursive_validation["valid"] is True
    assert recursive_validation["nested_bundle_total"] == 1


def test_run_campaign_respects_auto_promote_min_stage(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    promotion_root = tmp_path / "promoted"
    target_root.mkdir()
    promotion_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-promote-min-stage",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--stage",
                "screening",
                "--target-root",
                str(target_root),
                "--promotion-target-root",
                str(promotion_root),
                "--auto-promote",
                "--auto-promote-min-stage",
                "holdout",
                "--edit-plan",
                str(edit_plan_path),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    candidate = rendered["campaign"]["candidates"][0]
    assert rendered["campaign"]["promoted_count"] == 0
    assert candidate["promoted"] is False
    assert candidate["promotion_id"] is None
    assert candidate["comparison_decision"] == "auto_promote_min_stage_not_reached"
    champion_manifest_path = (
        workspaces_root / "demo" / "tracks" / "main" / "champion.json"
    )
    assert not champion_manifest_path.exists()


def test_run_campaign_stops_on_success_budget(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-success-budget",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_paths = []
    for filename in ("alpha.txt", "beta.txt"):
        edit_plan_path = tmp_path / f"{filename}.yaml"
        edit_plan_path.write_text(
            yaml.safe_dump(
                {
                    "operations": [
                        {
                            "type": "write_file",
                            "path": filename,
                            "content": f"{filename}\n",
                        }
                    ]
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        edit_plan_paths.append(edit_plan_path)

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_paths[0]),
                "--edit-plan",
                str(edit_plan_paths[1]),
                "--max-successes",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["campaign"]["status"] == "completed"
    assert rendered["campaign"]["stop_reason"] == "success_budget_reached"
    assert rendered["campaign"]["success_count"] == 1
    assert rendered["campaign"]["next_candidate_index"] == 1
    assert rendered["campaign"]["candidates"][0]["status"] == "success"
    assert rendered["campaign"]["candidates"][1]["status"] == "pending"


def test_run_campaign_persists_selected_focus_task_ids(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    seed_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="seed-failure-context",
        config={"command": ["python", "-c", "print('seed')"]},
        payload={
            "benchmark_name": "seed-failure-context",
            "command": ["python", "-c", "print('seed')"],
            "success": False,
            "task_results": [
                {"task_id": "task_a", "score": 0.0},
                {"task_id": "task_b", "score": 0.4},
            ],
            "stage_evaluation": {
                "baseline_comparison": {
                    "regressed_task_ids": ["regressed_x", "regressed_y"],
                    "decision": "regressed",
                }
            },
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
    )
    persist_benchmark_record(root=workspaces_root, record=seed_record)
    state = load_workspace_state(workspaces_root, "demo")
    save_workspace_state(
        workspaces_root,
        "demo",
        replace(state, last_experiment_id=seed_record.record_id),
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-persisted-focus",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--strategy",
                "regression_first",
                "--intervention-class",
                "source",
                "--target-root",
                str(target_root),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    first_request = campaign["candidates"][0]["generation_request"]
    assert first_request["failure_focus_task_ids"] == []
    assert first_request["regressed_task_ids"] == ["regressed_x"]
    assert any(entry["event"] == "candidate_focus_selected" for entry in campaign["decision_log"])


def test_classify_record_failure_uses_regression_and_stage_taxonomy() -> None:
    regression_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="regression-taxonomy",
        config={},
        payload={
            "benchmark_name": "regression-taxonomy",
            "command": ["python", "-c", "print('ok')"],
            "stage_evaluation": {
                "passed": False,
                "baseline_comparison": {
                    "passed": False,
                    "regressed_task_ids": ["task_a"],
                },
            },
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
    )
    stage_gate_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="stage-gate-taxonomy",
        config={},
        payload={
            "benchmark_name": "stage-gate-taxonomy",
            "command": ["python", "-c", "print('ok')"],
            "stage_evaluation": {"passed": False, "decision": "failed_gate"},
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
    )
    command_failure_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="command-taxonomy",
        config={},
        payload={
            "benchmark_name": "command-taxonomy",
            "command": ["python", "-c", "print('ok')"],
            "success": False,
        },
        dry_run=False,
        workspace_id="demo",
        track_id="main",
    )

    assert campaign_handlers._classify_record_failure(regression_record) == "benchmark_regression"
    assert campaign_handlers._classify_record_failure(stage_gate_record) == "stage_gate_failed"
    assert (
        campaign_handlers._classify_record_failure(command_failure_record)
        == "benchmark_command_failed"
    )


def test_run_workspace_campaigns_runs_each_active_track(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    main(
        [
            "create-track",
            "--workspace-id",
            "demo",
            "--track-id",
            "alt",
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "workspace-campaign-batch",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-workspace-campaigns",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--track-id",
                "main",
                "--track-id",
                "alt",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["workspace_id"] == "demo"
    assert rendered["track_total"] == 2
    assert rendered["completed_track_total"] == 2
    assert rendered["status"] == "completed"
    assert rendered["search_policy_mix"]["by_generator_id"] == {"failure_summary": 2}
    assert rendered["search_policy_mix"]["by_strategy"] == {"greedy_failure_focus": 2}
    assert rendered["search_policy_mix"]["by_stage_progression_mode"] == {"fixed": 2}
    assert rendered["search_policy_mix"]["by_candidate_source_mode"] == {
        "generator_loop": 2
    }
    assert rendered["search_policy_mix"]["by_beam_width"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_beam_group_limit"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_max_generation_retries"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_max_generation_provider_retries"] == {
        "(unset)": 2
    }
    assert rendered["search_policy_mix"]["by_max_generation_process_retries"] == {
        "(unset)": 2
    }
    assert rendered["search_policy_mix"]["by_max_execution_retries"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_max_benchmark_command_retries"] == {
        "(unset)": 2
    }
    assert rendered["search_policy_mix"]["by_max_inconclusive_retries"] == {
        "(unset)": 2
    }
    assert rendered["search_policy_mix"]["by_auto_promote"] == {"False": 2}
    assert rendered["search_policy_mix"]["by_auto_promote_min_stage"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_stop_on_first_promotion"] == {"False": 2}
    assert [item["track_id"] for item in rendered["tracks"]] == ["alt", "main"]
    for item in rendered["tracks"]:
        assert item["campaign_status"] == "paused"
        assert item["campaign_stop_reason"] == "proposal_budget_reached"
        assert Path(item["target_root"]) == (target_root_base / item["track_id"]).resolve()


def test_export_workspace_campaign_run_report_exports_versioned_batch_result(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    main(
        [
            "create-track",
            "--workspace-id",
            "demo",
            "--track-id",
            "alt",
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "workspace-campaign-batch-export",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    export_path = tmp_path / "workspace-run-report.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-workspace-campaign-run-report",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--track-id",
                "main",
                "--track-id",
                "alt",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--output",
                str(export_path),
            ]
        )
        == 0
    )
    report = yaml.safe_load(export_path.read_text(encoding="utf-8"))
    assert report["format_version"] == "autoharness.workspace_campaign_run_report.v1"
    assert isinstance(report["exported_at"], str)
    assert report["workspace_id"] == "demo"
    assert report["track_total"] == 2
    assert report["completed_track_total"] == 2
    assert report["status"] == "completed"
    assert report["search_policy_mix"]["by_generator_id"] == {"failure_summary": 2}
    assert report["search_policy_mix"]["by_strategy"] == {"greedy_failure_focus": 2}
    assert report["search_policy_mix"]["by_stage_progression_mode"] == {"fixed": 2}
    assert report["search_policy_mix"]["by_candidate_source_mode"] == {
        "generator_loop": 2
    }
    assert report["search_policy_mix"]["by_beam_width"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_beam_group_limit"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_max_generation_provider_retries"] == {
        "(unset)": 2
    }
    assert report["search_policy_mix"]["by_max_generation_process_retries"] == {
        "(unset)": 2
    }
    assert report["search_policy_mix"]["by_max_generation_retries"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_max_execution_retries"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_max_benchmark_command_retries"] == {
        "(unset)": 2
    }
    assert report["search_policy_mix"]["by_max_inconclusive_retries"] == {
        "(unset)": 2
    }
    assert report["search_policy_mix"]["by_auto_promote"] == {"False": 2}
    assert report["search_policy_mix"]["by_auto_promote_min_stage"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_stop_on_first_promotion"] == {"False": 2}
    assert [item["track_id"] for item in report["tracks"]] == ["alt", "main"]


def test_run_campaign_sources_beam_candidate_group(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "beam-campaign",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--strategy",
                "beam_interventions",
                "--beam-width",
                "3",
                "--intervention-class",
                "config",
                "--intervention-class",
                "source",
                "--intervention-class",
                "prompt",
                "--target-root",
                str(target_root),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    assert campaign["strategy"] == "beam_interventions"
    assert campaign["beam_width"] == 3
    assert rendered["pruned_candidate_total"] == 2
    assert len(campaign["candidates"]) == 3
    assert [item["intervention_class"] for item in campaign["candidates"]] == [
        "config",
        "source",
        "prompt",
    ]
    for slot_index, item in enumerate(campaign["candidates"]):
        request = item["generation_request"]
        assert request["beam_group_index"] == 0
        assert request["beam_slot_index"] == slot_index
        assert request["beam_width"] == 3
    assert campaign["candidates"][0]["status"] == "success"
    assert campaign["candidates"][1]["status"] == "pruned"
    assert campaign["candidates"][2]["status"] == "pruned"
    assert any(
        entry["event"] == "beam_group_pruned"
        for entry in campaign["decision_log"]
    )
    assert campaign["stop_reason"] == "proposal_budget_reached"


def test_run_campaign_with_multiple_active_beam_groups(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "beam-groups-campaign",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--strategy",
                "beam_interventions",
                "--beam-width",
                "2",
                "--beam-groups",
                "2",
                "--intervention-class",
                "config",
                "--intervention-class",
                "source",
                "--target-root",
                str(target_root),
                "--max-proposals",
                "2",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    assert campaign["beam_width"] == 2
    assert campaign["beam_group_limit"] == 2
    assert rendered["pruned_candidate_total"] == 2
    assert len(campaign["candidates"]) == 6
    assert [item["generation_request"].get("beam_group_index") for item in campaign["candidates"]] == [
        0,
        0,
        1,
        1,
        2,
        2,
    ]
    assert campaign["candidates"][0]["status"] == "success"
    assert campaign["candidates"][1]["status"] == "pruned"
    assert {campaign["candidates"][2]["status"], campaign["candidates"][3]["status"]} == {
        "success",
        "pruned",
    }
    assert campaign["candidates"][4]["status"] == "pending"
    assert campaign["candidates"][5]["status"] == "pending"


def test_run_campaign_with_local_command_generator(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "command-campaign",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    script_path = tmp_path / "proposal_generator.py"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "import sys",
                "payload = json.load(sys.stdin)",
                "request = payload['request']",
                "context = payload['context']",
                "result = {",
                "    'hypothesis': f\"Campaign command candidate {request['candidate_index']}\",",
                "    'summary': f\"Campaign command proposal {request['candidate_index']}\",",
                "    'intervention_class': request.get('intervention_class') or 'source',",
                "    'operations': [",
                "        {",
                "            'type': 'write_file',",
                "            'path': f\".autoharness/generated/campaign_command_{request['candidate_index']}.txt\",",
                "            'content': f\"workspace={context['workspace_id']}\\ntrack={context['track_id']}\\n\",",
                "        }",
                "    ],",
                "}",
                "print(json.dumps(result))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "local_command",
                "--generator-option",
                f"command_path={script_path}",
                "--intervention-class",
                "source",
                "--target-root",
                str(target_root),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    assert campaign["generator_id"] == "local_command"
    assert campaign["status"] == "paused"
    assert campaign["stop_reason"] == "proposal_budget_reached"
    assert campaign["candidates"][0]["status"] == "success"
    assert campaign["candidates"][0]["proposal_id"] is not None


def test_run_root_campaigns_runs_each_workspace(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    for workspace_id in ("demo", "demo_b"):
        main(
            [
                "init-workspace",
                "--workspace-id",
                workspace_id,
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "root-campaign",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-root-campaigns",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["workspace_total"] == 2
    assert rendered["completed_workspace_total"] == 2
    assert rendered["status"] == "completed"
    assert rendered["search_policy_mix"]["by_generator_id"] == {"failure_summary": 2}
    assert rendered["search_policy_mix"]["by_strategy"] == {"greedy_failure_focus": 2}
    assert rendered["search_policy_mix"]["by_stage_progression_mode"] == {"fixed": 2}
    assert rendered["search_policy_mix"]["by_candidate_source_mode"] == {
        "generator_loop": 2
    }
    assert rendered["search_policy_mix"]["by_beam_width"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_beam_group_limit"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_max_generation_retries"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_max_generation_provider_retries"] == {
        "(unset)": 2
    }
    assert rendered["search_policy_mix"]["by_max_generation_process_retries"] == {
        "(unset)": 2
    }
    assert rendered["search_policy_mix"]["by_max_execution_retries"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_max_benchmark_command_retries"] == {
        "(unset)": 2
    }
    assert rendered["search_policy_mix"]["by_max_inconclusive_retries"] == {
        "(unset)": 2
    }
    assert rendered["search_policy_mix"]["by_auto_promote"] == {"False": 2}
    assert rendered["search_policy_mix"]["by_auto_promote_min_stage"] == {"(unset)": 2}
    assert rendered["search_policy_mix"]["by_stop_on_first_promotion"] == {"False": 2}
    assert [item["workspace_id"] for item in rendered["workspaces"]] == ["demo", "demo_b"]
    for item in rendered["workspaces"]:
        assert item["status"] == "completed"
        assert item["rendered"]["workspace_id"] == item["workspace_id"]
        assert item["rendered"]["track_total"] == 1
        assert Path(item["target_root_base"]) == (target_root_base / item["workspace_id"]).resolve()

    capsys.readouterr()
    assert (
        main(
            [
                "show-root-campaigns",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    root_listing = json.loads(capsys.readouterr().out)
    assert root_listing["workspace_total"] == 2
    assert root_listing["campaign_total"] == 2
    assert root_listing["search_policy_mix"]["by_generator_id"] == {"failure_summary": 2}
    assert root_listing["search_policy_mix"]["by_strategy"] == {"greedy_failure_focus": 2}
    assert root_listing["search_policy_mix"]["by_stage_progression_mode"] == {"fixed": 2}
    assert root_listing["search_policy_mix"]["by_candidate_source_mode"] == {
        "generator_loop": 2
    }
    assert root_listing["search_policy_mix"]["by_beam_width"] == {"(unset)": 2}
    assert root_listing["search_policy_mix"]["by_beam_group_limit"] == {"(unset)": 2}
    assert root_listing["search_policy_mix"]["by_max_generation_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_max_generation_timeout_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_max_generation_provider_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_max_generation_process_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_max_execution_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_max_benchmark_process_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_max_benchmark_signal_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_max_benchmark_parse_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"][
        "by_max_benchmark_adapter_validation_retries"
    ] == {"(unset)": 2}
    assert root_listing["search_policy_mix"]["by_max_benchmark_command_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_max_inconclusive_retries"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_auto_promote"] == {"False": 2}
    assert root_listing["search_policy_mix"]["by_auto_promote_min_stage"] == {
        "(unset)": 2
    }
    assert root_listing["search_policy_mix"]["by_stop_on_first_promotion"] == {
        "False": 2
    }
    assert [item["workspace_id"] for item in root_listing["campaigns"]] == ["demo", "demo_b"]
    assert root_listing["campaigns"][0]["track_id"] == "main"

    root_report_path = tmp_path / "root-campaign-report.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-root-campaign-report",
                "--root",
                str(workspaces_root),
                "--output",
                str(root_report_path),
            ]
        )
        == 0
    )
    root_report = yaml.safe_load(root_report_path.read_text(encoding="utf-8"))
    assert root_report["format_version"] == "autoharness.root_campaign_report.v1"
    assert root_report["workspace_total"] == 2
    assert root_report["campaign_total"] == 2
    assert root_report["search_policy_mix"]["by_generator_id"] == {"failure_summary": 2}
    assert root_report["search_policy_mix"]["by_stage_progression_mode"] == {"fixed": 2}
    assert root_report["search_policy_mix"]["by_max_generation_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_max_generation_timeout_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_max_generation_provider_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_max_generation_process_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_max_execution_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_max_benchmark_process_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_max_benchmark_signal_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_max_benchmark_parse_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"][
        "by_max_benchmark_adapter_validation_retries"
    ] == {"(unset)": 2}
    assert root_report["search_policy_mix"]["by_max_benchmark_command_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_max_inconclusive_retries"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_auto_promote"] == {"False": 2}
    assert root_report["search_policy_mix"]["by_auto_promote_min_stage"] == {
        "(unset)": 2
    }
    assert root_report["search_policy_mix"]["by_stop_on_first_promotion"] == {
        "False": 2
    }

    capsys.readouterr()
    assert main(["show-campaign-report-file", str(root_report_path), "--json"]) == 0
    shown_root_report = json.loads(capsys.readouterr().out)
    assert shown_root_report["report_type"] == "root_campaign_report"
    assert shown_root_report["workspace_total"] == 2

    capsys.readouterr()
    assert (
        main(["validate-campaign-report-file", str(root_report_path), "--json"]) == 0
    )
    validated_root_report = json.loads(capsys.readouterr().out)
    assert validated_root_report["valid"] is True

    root_bundle_dir = tmp_path / "root-campaign-bundle"
    capsys.readouterr()
    assert (
        main(
            [
                "export-root-campaign-bundle",
                "--root",
                str(workspaces_root),
                "--output",
                str(root_bundle_dir),
            ]
        )
        == 0
    )
    root_bundle_manifest = json.loads(
        (root_bundle_dir / "bundle_manifest.json").read_text(encoding="utf-8")
    )
    assert root_bundle_manifest["format_version"] == "autoharness.root_campaign_bundle.v1"
    assert len(root_bundle_manifest["artifacts"]["workspace_bundles"]) == 2

    capsys.readouterr()
    assert main(["show-bundle", str(root_bundle_dir), "--recursive", "--json"]) == 0
    root_bundle_view = json.loads(capsys.readouterr().out)
    assert root_bundle_view["bundle_type"] == "root_campaign_bundle"
    assert root_bundle_view["workspace_bundle_total"] == 2
    assert root_bundle_view["nested_bundle_total"] == 2

    capsys.readouterr()
    assert main(["validate-bundle", str(root_bundle_dir), "--recursive", "--json"]) == 0
    root_bundle_validation = json.loads(capsys.readouterr().out)
    assert root_bundle_validation["valid"] is True


def test_root_campaign_views_include_preflight_check_mix(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    for workspace_id in ("demo", "demo_b"):
        main(
            [
                "init-workspace",
                "--workspace-id",
                workspace_id,
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )

    config_path = tmp_path / "root-preflight-mix.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "root-preflight-mix",
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "root-preflight-mix-alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-root-campaigns",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--edit-plan",
                str(edit_plan_path),
                "--preflight-check",
                "python_compile",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    root_run = json.loads(capsys.readouterr().out)
    assert root_run["search_policy_mix"]["by_preflight_check_count"] == {"1": 2}

    capsys.readouterr()
    assert (
        main(
            [
                "show-root-campaigns",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    root_listing = json.loads(capsys.readouterr().out)
    assert root_listing["search_policy_mix"]["by_preflight_check_count"] == {"1": 2}

    root_report_path = tmp_path / "root-preflight-mix-report.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-root-campaign-report",
                "--root",
                str(workspaces_root),
                "--output",
                str(root_report_path),
            ]
        )
        == 0
    )
    root_report = yaml.safe_load(root_report_path.read_text(encoding="utf-8"))
    assert root_report["search_policy_mix"]["by_preflight_check_count"] == {"1": 2}


def test_workspace_campaign_views_include_aggregated_resource_usage(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "workspace-resource.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "workspace-resource",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 1.0, 'cost': 0.7}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    generator_script = tmp_path / "workspace_generator.py"
    _write_local_command_generator_script(generator_script)

    capsys.readouterr()
    assert (
        main(
            [
                "run-workspace-campaigns",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "local_command",
                "--generator-option",
                f"command_path={generator_script}",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    workspace_run = json.loads(capsys.readouterr().out)
    assert workspace_run["resource_usage"]["generation_total_tokens"] == 5
    assert workspace_run["resource_usage"]["generation_total_cost_usd"] == pytest.approx(
        0.11
    )
    assert workspace_run["resource_usage"]["benchmark_total_cost"] == pytest.approx(0.7)
    assert (
        workspace_run["tracks"][0]["rendered"]["resource_usage"]["generation_total_tokens"]
        == 5
    )

    capsys.readouterr()
    assert (
        main(
            [
                "show-campaigns",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    workspace_listing = json.loads(capsys.readouterr().out)
    assert workspace_listing["resource_usage"]["generation_total_tokens"] == 5
    assert workspace_listing["resource_usage"]["generation_total_cost_usd"] == pytest.approx(
        0.11
    )
    assert workspace_listing["resource_usage"]["benchmark_total_cost"] == pytest.approx(
        0.7
    )
    assert (
        workspace_listing["campaigns"][0]["resource_usage"]["generation_total_tokens"]
        == 5
    )

    workspace_report_path = tmp_path / "workspace-campaign-report.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-workspace-campaign-report",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--output",
                str(workspace_report_path),
            ]
        )
        == 0
    )
    workspace_report = yaml.safe_load(
        workspace_report_path.read_text(encoding="utf-8")
    )
    assert workspace_report["resource_usage"]["generation_total_tokens"] == 5
    assert workspace_report["resource_usage"]["generation_total_cost_usd"] == pytest.approx(
        0.11
    )
    assert workspace_report["resource_usage"]["benchmark_total_cost"] == pytest.approx(
        0.7
    )

    capsys.readouterr()
    assert main(["show-campaign-report-file", str(workspace_report_path), "--json"]) == 0
    shown_report = json.loads(capsys.readouterr().out)
    assert shown_report["report_type"] == "workspace_campaign_report"
    assert shown_report["resource_usage"]["generation_total_tokens"] == 5
    assert shown_report["resource_usage"]["benchmark_total_cost"] == pytest.approx(0.7)


def test_root_campaign_views_include_aggregated_resource_usage(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    for workspace_id in ("demo", "demo_b"):
        main(
            [
                "init-workspace",
                "--workspace-id",
                workspace_id,
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )

    config_path = tmp_path / "root-resource.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "root-resource",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    "import json; print(json.dumps({'pass_rate': 1.0, 'cost': 0.7}))",
                ],
                "metrics_parser": {"format": "json_stdout"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    generator_script = tmp_path / "root_generator.py"
    _write_local_command_generator_script(generator_script)

    capsys.readouterr()
    assert (
        main(
            [
                "run-root-campaigns",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "local_command",
                "--generator-option",
                f"command_path={generator_script}",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    root_run = json.loads(capsys.readouterr().out)
    assert root_run["resource_usage"]["generation_total_tokens"] == 10
    assert root_run["resource_usage"]["generation_total_cost_usd"] == pytest.approx(0.22)
    assert root_run["resource_usage"]["benchmark_total_cost"] == pytest.approx(1.4)
    for workspace_item in root_run["workspaces"]:
        assert (
            workspace_item["rendered"]["resource_usage"]["generation_total_tokens"] == 5
        )
        assert workspace_item["rendered"]["resource_usage"]["benchmark_total_cost"] == pytest.approx(
            0.7
        )

    capsys.readouterr()
    assert (
        main(
            [
                "show-root-campaigns",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    root_listing = json.loads(capsys.readouterr().out)
    assert root_listing["resource_usage"]["generation_total_tokens"] == 10
    assert root_listing["resource_usage"]["generation_total_cost_usd"] == pytest.approx(
        0.22
    )
    assert root_listing["resource_usage"]["benchmark_total_cost"] == pytest.approx(1.4)
    assert (
        root_listing["campaigns"][0]["resource_usage"]["generation_total_tokens"] == 5
    )

    root_report_path = tmp_path / "root-campaign-report.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-root-campaign-report",
                "--root",
                str(workspaces_root),
                "--output",
                str(root_report_path),
            ]
        )
        == 0
    )
    root_report = yaml.safe_load(root_report_path.read_text(encoding="utf-8"))
    assert root_report["resource_usage"]["generation_total_tokens"] == 10
    assert root_report["resource_usage"]["generation_total_cost_usd"] == pytest.approx(
        0.22
    )
    assert root_report["resource_usage"]["benchmark_total_cost"] == pytest.approx(1.4)

    capsys.readouterr()
    assert main(["show-campaign-report-file", str(root_report_path), "--json"]) == 0
    shown_report = json.loads(capsys.readouterr().out)
    assert shown_report["report_type"] == "root_campaign_report"
    assert shown_report["resource_usage"]["generation_total_tokens"] == 10
    assert shown_report["resource_usage"]["benchmark_total_cost"] == pytest.approx(1.4)


def test_export_root_campaign_run_report_exports_versioned_batch_result(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    for workspace_id in ("demo", "demo_b"):
        main(
            [
                "init-workspace",
                "--workspace-id",
                workspace_id,
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "root-campaign-export",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    export_path = tmp_path / "root-run-report.json"
    capsys.readouterr()
    assert (
        main(
            [
                "export-root-campaign-run-report",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--output",
                str(export_path),
                "--format",
                "json",
            ]
        )
        == 0
    )
    report = json.loads(export_path.read_text(encoding="utf-8"))
    assert report["format_version"] == "autoharness.root_campaign_run_report.v1"
    assert isinstance(report["exported_at"], str)
    assert report["workspace_total"] == 2
    assert report["completed_workspace_total"] == 2
    assert report["status"] == "completed"
    assert report["search_policy_mix"]["by_max_generation_provider_retries"] == {
        "(unset)": 2
    }
    assert report["search_policy_mix"]["by_max_generation_process_retries"] == {
        "(unset)": 2
    }
    assert report["search_policy_mix"]["by_generator_id"] == {"failure_summary": 2}
    assert report["search_policy_mix"]["by_strategy"] == {"greedy_failure_focus": 2}
    assert report["search_policy_mix"]["by_stage_progression_mode"] == {"fixed": 2}
    assert report["search_policy_mix"]["by_candidate_source_mode"] == {
        "generator_loop": 2
    }
    assert report["search_policy_mix"]["by_beam_width"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_beam_group_limit"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_max_generation_retries"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_max_execution_retries"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_max_benchmark_command_retries"] == {
        "(unset)": 2
    }
    assert report["search_policy_mix"]["by_max_inconclusive_retries"] == {
        "(unset)": 2
    }
    assert report["search_policy_mix"]["by_auto_promote"] == {"False": 2}
    assert report["search_policy_mix"]["by_auto_promote_min_stage"] == {"(unset)": 2}
    assert report["search_policy_mix"]["by_stop_on_first_promotion"] == {"False": 2}
    assert [item["workspace_id"] for item in report["workspaces"]] == ["demo", "demo_b"]

    capsys.readouterr()
    assert main(["show-campaign-report-file", str(export_path), "--json"]) == 0
    shown_root_run_report = json.loads(capsys.readouterr().out)
    assert shown_root_run_report["report_type"] == "root_campaign_run_report"
    assert shown_root_run_report["workspace_total"] == 2

    capsys.readouterr()
    assert (
        main(["validate-campaign-report-file", str(export_path), "--json"]) == 0
    )
    validated_root_run_report = json.loads(capsys.readouterr().out)
    assert validated_root_run_report["valid"] is True


def test_validate_campaign_report_file_rejects_malformed_report(
    tmp_path: Path, capsys
) -> None:
    report_path = tmp_path / "bad-campaign-report.yaml"
    report_path.write_text(
        yaml.safe_dump(
            {
                "format_version": "autoharness.campaign_report.v1",
                "workspace_id": "demo",
                "track_id": "main",
                "proposals": [],
                "records": [],
                "iterations": [],
                "promotions": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert main(["validate-campaign-report-file", str(report_path), "--json"]) == 1
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["report_type"] == "campaign_report"
    assert rendered["valid"] is False
    assert "Missing or invalid `campaign`." in rendered["validation_errors"]


def test_run_campaign_uses_inherited_campaign_policy_defaults(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    promotion_root = tmp_path / "promoted"
    target_root.mkdir()
    promotion_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    main(
        [
            "set-workspace",
            "--workspace-id",
            "demo",
            "--root",
            str(workspaces_root),
            "--campaign-stage",
            "holdout",
            "--campaign-generator",
            "failure_summary",
            "--campaign-strategy",
            "greedy_failure_focus",
            "--campaign-intervention-class",
            "source",
            "--campaign-max-iterations",
            "3",
            "--campaign-max-generation-timeout-retries",
            "1",
            "--campaign-max-benchmark-timeout-retries",
            "4",
            "--campaign-max-benchmark-command-retries",
            "2",
        ]
    )
    main(
        [
            "set-track",
            "--workspace-id",
            "demo",
            "--root",
            str(workspaces_root),
            "--campaign-intervention-class",
            "config",
            "--campaign-auto-promote",
            "--campaign-stop-on-first-promotion",
            "--campaign-promotion-target-root",
            str(promotion_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-inherited",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    assert campaign["stage"] == "holdout"
    assert campaign["generator_id"] == "failure_summary"
    assert campaign["strategy"] == "greedy_failure_focus"
    assert campaign["intervention_classes"] == ["config"]
    assert campaign["max_iterations"] == 3
    assert campaign["max_generation_timeout_retries"] == 1
    assert campaign["max_benchmark_timeout_retries"] == 4
    assert campaign["max_benchmark_command_retries"] == 2
    assert campaign["auto_promote"] is True
    assert campaign["stop_on_first_promotion"] is True
    assert Path(campaign["promotion_target_root"]) == promotion_root.resolve()
    assert campaign["candidate_source_mode"] == "generator_loop"
    assert campaign["status"] == "completed"
    assert campaign["stop_reason"] == "promotion_found"
    assert campaign["promoted_count"] == 1
    assert campaign["candidates"][0]["promoted"] is True
    assert campaign["candidates"][0]["intervention_class"] == "config"


def test_run_campaign_inherits_beam_group_limit_from_campaign_policy(
    tmp_path: Path, capsys
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )
    main(
        [
            "set-workspace",
            "--workspace-id",
            "demo",
            "--root",
            str(workspaces_root),
            "--campaign-generator",
            "failure_summary",
            "--campaign-strategy",
            "beam_interventions",
            "--campaign-beam-width",
            "2",
            "--campaign-beam-groups",
            "2",
            "--campaign-max-iterations",
            "1",
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-beam-inherited",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    assert campaign["generator_id"] == "failure_summary"
    assert campaign["strategy"] == "beam_interventions"
    assert campaign["beam_width"] == 2
    assert campaign["beam_group_limit"] == 2
    assert campaign["max_iterations"] == 1


def test_run_campaign_stops_on_first_promotion(tmp_path: Path, capsys) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    promotion_root = tmp_path / "promoted"
    target_root.mkdir()
    promotion_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-promote",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_paths = []
    for filename in ("alpha.txt", "beta.txt"):
        edit_plan_path = tmp_path / f"{filename}.yaml"
        edit_plan_path.write_text(
            yaml.safe_dump(
                {
                    "operations": [
                        {
                            "type": "write_file",
                            "path": filename,
                            "content": f"{filename}\n",
                        }
                    ]
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        edit_plan_paths.append(edit_plan_path)

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--promotion-target-root",
                str(promotion_root),
                "--auto-promote",
                "--stop-on-first-promotion",
                "--edit-plan",
                str(edit_plan_paths[0]),
                "--edit-plan",
                str(edit_plan_paths[1]),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["campaign"]["status"] == "completed"
    assert rendered["campaign"]["stop_reason"] == "promotion_found"
    assert rendered["campaign"]["next_candidate_index"] == 1
    assert rendered["campaign"]["promoted_count"] == 1
    assert rendered["campaign"]["candidates"][0]["promoted"] is True
    assert rendered["campaign"]["candidates"][1]["status"] == "pending"


def test_run_campaign_retries_execution_failures(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-retry",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    original_run_proposal = campaign_handlers._handle_run_proposal
    call_count = {"value": 0}

    def flaky_run_proposal(args):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise SystemExit(2)
        return original_run_proposal(args)

    monkeypatch.setattr(campaign_handlers, "_handle_run_proposal", flaky_run_proposal)

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--max-execution-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert call_count["value"] == 2
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["execution_error"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "execution_error"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_benchmark_command_failures(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    counter_path = tmp_path / "benchmark_attempts.txt"
    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-benchmark-command-retry",
                "workdir": str(tmp_path),
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "import sys\n"
                        f"path = Path(r\"{counter_path}\")\n"
                        "count = int(path.read_text() if path.exists() else '0')\n"
                        "path.write_text(str(count + 1), encoding='utf-8')\n"
                        "if count == 0:\n"
                        "    sys.exit(1)\n"
                        "print('ok')\n"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--max-benchmark-command-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert counter_path.read_text(encoding="utf-8") == "2"
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["benchmark_command_failed"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "benchmark_command_failed"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_benchmark_timeouts(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    counter_path = tmp_path / "benchmark_timeout_attempts.txt"
    config_path = tmp_path / "generic-timeout.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-benchmark-timeout-retry",
                "workdir": str(tmp_path),
                "timeout_seconds": 0.05,
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "import time\n"
                        f"path = Path(r\"{counter_path}\")\n"
                        "count = int(path.read_text() if path.exists() else '0')\n"
                        "path.write_text(str(count + 1), encoding='utf-8')\n"
                        "if count == 0:\n"
                        "    time.sleep(0.2)\n"
                        "print('ok')\n"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha-timeout.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--max-benchmark-timeout-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert counter_path.read_text(encoding="utf-8") == "2"
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["benchmark_timeout"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "benchmark_timeout"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_benchmark_process_failures(
    tmp_path: Path,
    capsys,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic-process.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-benchmark-process-retry",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha-process.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    missing_workdir = tmp_path / "missing-process-workdir"
    original_execute_invocation = adapters_base.execute_invocation
    call_count = {"value": 0}

    def flaky_execute_invocation(adapter_id, invocation, *, metadata=None):
        call_count["value"] += 1
        effective_invocation = invocation
        if call_count["value"] == 1:
            effective_invocation = replace(
                invocation,
                workdir=str(missing_workdir),
            )
        return original_execute_invocation(
            adapter_id,
            effective_invocation,
            metadata=metadata,
        )

    monkeypatch.setattr(
        adapters_base,
        "execute_invocation",
        flaky_execute_invocation,
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--max-benchmark-process-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert call_count["value"] == 2
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["benchmark_process_error"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "benchmark_process_error"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_benchmark_metrics_parse_failures(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    counter_path = tmp_path / "benchmark_metrics_parse_attempts.txt"
    config_path = tmp_path / "generic-metrics-parse.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-benchmark-metrics-parse-retry",
                "workdir": str(tmp_path),
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "import json\n"
                        f"counter = Path(r\"{counter_path}\")\n"
                        "count = int(counter.read_text() if counter.exists() else '0')\n"
                        "counter.write_text(str(count + 1), encoding='utf-8')\n"
                        "metrics_path = Path('metrics.json')\n"
                        "if count == 0:\n"
                        "    metrics_path.write_text('{not-json', encoding='utf-8')\n"
                        "else:\n"
                        "    metrics_path.write_text(json.dumps({'pass_rate': 1.0}), encoding='utf-8')\n"
                        "print('ok')\n"
                    ),
                ],
                "metrics_parser": {
                    "format": "json_file",
                    "path": "metrics.json",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha-metrics-parse.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--max-benchmark-parse-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert counter_path.read_text(encoding="utf-8") == "2"
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["benchmark_metrics_parse_error"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "benchmark_metrics_parse_error"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_marks_flaky_success_as_provisional_after_revalidation(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    counter_path = tmp_path / "benchmark_flaky_attempts.txt"
    config_path = tmp_path / "generic-flaky-success.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-flaky-success",
                "workdir": str(tmp_path),
                "command": [
                    "python",
                    "-c",
                    (
                        "from pathlib import Path\n"
                        "import json\n"
                        f"counter = Path(r\"{counter_path}\")\n"
                        "count = int(counter.read_text() if counter.exists() else '0')\n"
                        "counter.write_text(str(count + 1), encoding='utf-8')\n"
                        "metrics_path = Path('metrics.json')\n"
                        "score = 1.0 if count % 2 == 0 else 0.9\n"
                        "metrics_path.write_text(json.dumps({'score': score}), encoding='utf-8')\n"
                        "print('ok')\n"
                    ),
                ],
                "metrics_parser": {
                    "format": "json_file",
                    "path": "metrics.json",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha-flaky.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--repeat",
                "2",
                "--auto-promote",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]

    assert counter_path.read_text(encoding="utf-8") == "4"
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["unstable_validation"] == 1
    assert candidate["status"] == "success"
    assert candidate["promoted"] is False
    assert candidate["comparison_decision"] == "provisional_winner"
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "unstable_validation"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_preflight_failures(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    preflight_counter = tmp_path / "preflight_counter.txt"
    benchmark_counter = tmp_path / "benchmark_counter.txt"
    preflight_script = tmp_path / "preflight_retry.py"
    preflight_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"counter_path = Path({str(preflight_counter)!r})",
                "count = int(counter_path.read_text(encoding='utf-8')) if counter_path.exists() else 0",
                "count += 1",
                "counter_path.write_text(str(count), encoding='utf-8')",
                "raise SystemExit(0 if count >= 2 else 1)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-preflight-retry",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"counter_path = Path({str(benchmark_counter)!r}); "
                        "count = int(counter_path.read_text(encoding='utf-8')) if counter_path.exists() else 0; "
                        "counter_path.write_text(str(count + 1), encoding='utf-8'); "
                        "print('ok')"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--preflight-command",
                f"{sys.executable} {preflight_script}",
                "--max-preflight-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert preflight_counter.read_text(encoding="utf-8") == "2"
    assert benchmark_counter.read_text(encoding="utf-8") == "1"
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["preflight_failed"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "preflight_failed"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_supports_builtin_preflight_checks(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    (target_root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    benchmark_counter = tmp_path / "campaign_builtin_preflight_benchmark.txt"

    config_path = tmp_path / "campaign_builtin_preflight.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-builtin-preflight",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"Path({str(benchmark_counter)!r}).write_text('1', encoding='utf-8')"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "builtin_preflight_alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--preflight-check",
                "python_compile",
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]

    assert campaign["preflight_checks"] == ["python_compile"]
    assert "compileall" in campaign["preflight_commands"][0]
    assert candidate["status"] == "failed"
    assert candidate["failure_class"] == "preflight_failed"
    assert rendered["failure_count"] == 1
    assert not benchmark_counter.exists()


def test_run_campaign_retries_generation_timeouts(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-generation-timeout-retry",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    original_generate_proposal = campaign_handlers._handle_generate_proposal
    call_count = {"value": 0}

    def flaky_generate_proposal(args):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise SystemExit("generator timed out") from ProposalGenerationTimeoutError(
                "generator timed out"
            )
        return original_generate_proposal(args)

    monkeypatch.setattr(
        campaign_handlers,
        "_handle_generate_proposal",
        flaky_generate_proposal,
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--generator",
                "failure_summary",
                "--max-iterations",
                "1",
                "--max-generation-timeout-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert call_count["value"] == 2
    assert campaign["max_generation_timeout_retries"] == 1
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["generation_timeout"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "generation_timeout"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_generation_provider_failures(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-generation-provider-retry",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    original_generate_proposal = campaign_handlers._handle_generate_proposal
    call_count = {"value": 0}

    def flaky_generate_proposal(args):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise SystemExit("provider failed") from ProposalGenerationProviderError(
                "provider failed"
            )
        return original_generate_proposal(args)

    monkeypatch.setattr(
        campaign_handlers,
        "_handle_generate_proposal",
        flaky_generate_proposal,
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--generator",
                "failure_summary",
                "--max-iterations",
                "1",
                "--max-generation-provider-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert call_count["value"] == 2
    assert campaign["max_generation_provider_retries"] == 1
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["generation_provider_error"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "generation_provider_error"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_generation_provider_transport_failures(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-generation-provider-transport-retry",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    original_generate_proposal = campaign_handlers._handle_generate_proposal
    call_count = {"value": 0}

    def flaky_generate_proposal(args):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise SystemExit("provider transport failed") from (
                ProposalGenerationProviderTransportError("provider transport failed")
            )
        return original_generate_proposal(args)

    monkeypatch.setattr(
        campaign_handlers,
        "_handle_generate_proposal",
        flaky_generate_proposal,
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--generator",
                "failure_summary",
                "--max-iterations",
                "1",
                "--max-generation-provider-transport-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert call_count["value"] == 2
    assert campaign["max_generation_provider_transport_retries"] == 1
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["generation_provider_transport_error"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "generation_provider_transport_error"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_generation_provider_auth_failures(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-generation-provider-auth-retry",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    original_generate_proposal = campaign_handlers._handle_generate_proposal
    call_count = {"value": 0}

    def flaky_generate_proposal(args):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise SystemExit("provider auth failed") from (
                ProposalGenerationProviderAuthError("provider auth failed")
            )
        return original_generate_proposal(args)

    monkeypatch.setattr(
        campaign_handlers,
        "_handle_generate_proposal",
        flaky_generate_proposal,
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--generator",
                "failure_summary",
                "--max-iterations",
                "1",
                "--max-generation-provider-auth-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert call_count["value"] == 2
    assert campaign["max_generation_provider_auth_retries"] == 1
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["generation_provider_auth_error"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "generation_provider_auth_error"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_generation_provider_rate_limit_failures(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-generation-provider-rate-limit-retry",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    original_generate_proposal = campaign_handlers._handle_generate_proposal
    call_count = {"value": 0}

    def flaky_generate_proposal(args):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise SystemExit("provider rate limited") from (
                ProposalGenerationProviderRateLimitError("provider rate limited")
            )
        return original_generate_proposal(args)

    monkeypatch.setattr(
        campaign_handlers,
        "_handle_generate_proposal",
        flaky_generate_proposal,
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--generator",
                "failure_summary",
                "--max-iterations",
                "1",
                "--max-generation-provider-rate-limit-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert call_count["value"] == 2
    assert campaign["max_generation_provider_rate_limit_retries"] == 1
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["generation_provider_rate_limit_error"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "generation_provider_rate_limit_error"
        for entry in campaign["decision_log"]
    )


def test_run_campaign_retries_generation_process_failures(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-generation-process-retry",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    original_generate_proposal = campaign_handlers._handle_generate_proposal
    call_count = {"value": 0}

    def flaky_generate_proposal(args):
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise SystemExit("process failed") from ProposalGenerationProcessError(
                "process failed"
            )
        return original_generate_proposal(args)

    monkeypatch.setattr(
        campaign_handlers,
        "_handle_generate_proposal",
        flaky_generate_proposal,
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--generator",
                "failure_summary",
                "--max-iterations",
                "1",
                "--max-generation-process-retries",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert call_count["value"] == 2
    assert campaign["max_generation_process_retries"] == 1
    assert rendered["attempt_total"] == 2
    assert candidate["attempt_count"] == 2
    assert candidate["retry_counts"]["generation_process_error"] == 1
    assert candidate["status"] == "success"
    assert candidate["failure_class"] is None
    assert any(
        entry["event"] == "candidate_retry_scheduled"
        and entry["failure_class"] == "generation_process_error"
        for entry in campaign["decision_log"]
    )


def test_classify_record_failure_recognizes_signal_parse_and_adapter_validation() -> None:
    signal_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="signal-smoke",
        config={},
        payload={
            "command": ["python"],
            "success": False,
            "exit_code": -15,
            "signal_number": 15,
        },
        dry_run=False,
    )
    parse_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="parse-smoke",
        config={},
        payload={
            "command": ["python"],
            "success": False,
            "metadata": {"task_results_parse_error": "bad task results"},
        },
        dry_run=False,
    )
    adapter_validation_record = create_benchmark_record(
        adapter_id="generic_command",
        benchmark_name="validation-smoke",
        config={},
        payload={
            "command": [],
            "success": False,
            "adapter_validation_error": True,
            "adapter_error": "missing command",
        },
        dry_run=False,
    )

    assert campaign_handlers._classify_record_failure(signal_record) == (
        "benchmark_signal_error"
    )
    assert campaign_handlers._classify_record_failure(parse_record) == (
        "benchmark_task_results_parse_error"
    )
    assert campaign_handlers._classify_record_failure(adapter_validation_record) == (
        "benchmark_adapter_validation_error"
    )


def test_run_campaign_generator_loop_sources_candidates_without_edit_plan(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-generator",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--intervention-class",
                "config",
                "--target-root",
                str(target_root),
                "--max-proposals",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    candidate = campaign["candidates"][0]
    assert campaign["strategy"] == "greedy_failure_focus"
    assert campaign["candidate_source_mode"] == "generator_loop"
    assert campaign["stop_reason"] == "proposal_budget_reached"
    assert candidate["source_mode"] == "generator_generated"
    assert candidate["intervention_class"] == "config"
    assert candidate["proposal_id"] is not None
    assert candidate["status"] == "success"
    assert campaign["success_count"] == 1
    assert any(entry["event"] == "candidate_sourced" for entry in campaign["decision_log"])


def test_run_campaign_round_robin_strategy_cycles_intervention_classes(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-round-robin",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--strategy",
                "round_robin_interventions",
                "--intervention-class",
                "config",
                "--intervention-class",
                "source",
                "--target-root",
                str(target_root),
                "--max-proposals",
                "2",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    assert [candidate["intervention_class"] for candidate in campaign["candidates"][:2]] == [
        "config",
        "source",
    ]


def test_run_campaign_advances_stage_after_success(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-stage-ladder",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_paths = []
    for filename in ("alpha.txt", "beta.txt"):
        edit_plan_path = tmp_path / f"{filename}.yaml"
        edit_plan_path.write_text(
            yaml.safe_dump(
                {
                    "operations": [
                        {
                            "type": "write_file",
                            "path": filename,
                            "content": f"{filename}\n",
                        }
                    ]
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        edit_plan_paths.append(edit_plan_path)

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--stage",
                "screening",
                "--stage-progression",
                "advance_on_success",
                "--edit-plan",
                str(edit_plan_paths[0]),
                "--edit-plan",
                str(edit_plan_paths[1]),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    campaign = rendered["campaign"]
    assert campaign["initial_stage"] == "screening"
    assert campaign["stage"] == "holdout"
    assert campaign["stage_progression_mode"] == "advance_on_success"
    assert sum(
        1 for entry in campaign["decision_log"] if entry["event"] == "campaign_stage_advanced"
    ) == 2

    first_proposal = load_proposal(
        root=workspaces_root,
        workspace_id="demo",
        track_id="main",
        proposal_id=campaign["candidates"][0]["proposal_id"],
    )
    second_proposal = load_proposal(
        root=workspaces_root,
        workspace_id="demo",
        track_id="main",
        proposal_id=campaign["candidates"][1]["proposal_id"],
    )
    assert first_proposal.stage == "screening"
    assert second_proposal.stage == "validation"


def test_run_campaign_stops_on_inconclusive_budget(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    main(["setup", "--output", str(settings)])
    main(
        [
            "init-workspace",
            "--workspace-id",
            "demo",
            "--objective",
            "Improve harness correctness",
            "--benchmark",
            "tau-bench-airline",
            "--settings",
            str(settings),
            "--root",
            str(workspaces_root),
        ]
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "campaign-inconclusive",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"counter = Path({str(tmp_path / 'campaign_counter.txt')!r}); "
                        "count = int(counter.read_text() if counter.exists() else '0'); "
                        "counter.write_text(str(count + 1)); "
                        "raise SystemExit(0 if count == 0 else 1)"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "alpha.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "alpha.txt",
                        "content": "alpha\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--stage",
                "validation",
                "--max-inconclusive",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["campaign"]["stop_reason"] == "inconclusive_budget_reached"
    assert rendered["campaign"]["inconclusive_count"] == 1
    assert rendered["campaign"]["candidates"][0]["status"] == "inconclusive"


def _init_demo_workspace(tmp_path: Path) -> tuple[Path, Path, Path]:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()

    assert main(["setup", "--output", str(settings)]) == 0
    assert (
        main(
            [
                "init-workspace",
                "--workspace-id",
                "demo",
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    return settings, workspaces_root, target_root


def _write_success_config(tmp_path: Path, *, name: str) -> Path:
    config_path = tmp_path / f"{name}.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": name,
                "workdir": str(tmp_path),
                "command": [sys.executable, "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def _write_edit_plan(tmp_path: Path, *, filename: str) -> Path:
    edit_plan_path = tmp_path / f"{filename}.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": f"{filename}.txt",
                        "content": f"{filename}\n",
                    }
                ]
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return edit_plan_path


def _stale_utc_timestamp(*, seconds_ago: int = 600) -> str:
    return (
        datetime.now(UTC) - timedelta(seconds=seconds_ago)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_background_campaign_worker_executes_queued_campaign(tmp_path: Path, capsys) -> None:
    _, workspaces_root, target_root = _init_demo_workspace(tmp_path)
    config_path = _write_success_config(tmp_path, name="background-campaign")
    edit_plan_path = _write_edit_plan(tmp_path, filename="alpha")

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--background",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    queued = json.loads(capsys.readouterr().out)
    campaign_id = queued["campaign"]["campaign_run_id"]
    assert queued["campaign"]["status"] == "queued"
    assert queued["campaign"]["execution_mode"] == "background"

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign-worker",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    worker = json.loads(capsys.readouterr().out)
    assert worker["claimed_campaign_total"] == 1
    assert worker["campaigns"][0]["campaign_id"] == campaign_id
    assert worker["campaigns"][0]["status"] == "completed"

    capsys.readouterr()
    assert (
        main(
            [
                "show-campaign",
                "--workspace-id",
                "demo",
                "--campaign-id",
                campaign_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["campaign"]["status"] == "completed"
    assert rendered["campaign"]["lease_owner"] is None
    assert rendered["campaign"]["stop_reason"] == "proposal_list_exhausted"

    capsys.readouterr()
    assert (
        main(
            [
                "show-event-log",
                "--workspace-id",
                "demo",
                "--campaign-id",
                campaign_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    event_log = json.loads(capsys.readouterr().out)
    event_types = {event["event_type"] for event in event_log["events"]}
    assert "campaign_created" in event_types
    assert "campaign_claimed" in event_types
    assert "campaign_stopped" in event_types

    capsys.readouterr()
    assert (
        main(
            [
                "show-event-metrics",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["event_total"] >= len(event_log["events"])
    assert metrics["event_type_counts"]["campaign_created"] >= 1


def test_background_worker_recovers_stale_campaign_and_workspace_leases(
    tmp_path: Path,
    capsys,
) -> None:
    _, workspaces_root, target_root = _init_demo_workspace(tmp_path)
    config_path = _write_success_config(tmp_path, name="stale-lease-campaign")
    edit_plan_path = _write_edit_plan(tmp_path, filename="stale")

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--background",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    queued = json.loads(capsys.readouterr().out)
    campaign_id = queued["campaign"]["campaign_run_id"]

    stale_timestamp = _stale_utc_timestamp()
    campaign = campaign_runs.load_campaign_run(
        root=workspaces_root,
        workspace_id="demo",
        track_id="main",
        campaign_run_id=campaign_id,
    )
    campaign_runs.persist_campaign_run(
        root=workspaces_root,
        campaign=replace(
            campaign,
            status="running",
            desired_state="run",
            stop_reason=None,
            lease_owner="stale_worker",
            lease_claimed_at=stale_timestamp,
            lease_heartbeat_at=stale_timestamp,
            lease_expires_at=stale_timestamp,
        ),
    )

    workspace_lease_path = campaign_runs.workspace_campaign_lease_path(
        root=workspaces_root,
        workspace_id="demo",
    )
    workspace_lease_path.write_text(
        json.dumps(
            {
                "format_version": "autoharness.workspace_campaign_lease.v1",
                "workspace_id": "demo",
                "lease_owner": "stale_worker",
                "lease_claimed_at": stale_timestamp,
                "lease_heartbeat_at": stale_timestamp,
                "lease_expires_at": stale_timestamp,
            }
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign-worker",
                "--workspace-id",
                "demo",
                "--worker-id",
                "recovery_worker",
                "--lease-seconds",
                "60",
                "--max-campaigns",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    worker = json.loads(capsys.readouterr().out)
    assert worker["claimed_campaign_total"] == 1
    assert worker["campaigns"][0]["campaign_id"] == campaign_id
    assert worker["campaigns"][0]["status"] == "completed"

    recovered = campaign_runs.load_campaign_run(
        root=workspaces_root,
        workspace_id="demo",
        track_id="main",
        campaign_run_id=campaign_id,
    )
    assert recovered.status == "completed"
    assert recovered.stop_reason == "proposal_list_exhausted"
    assert recovered.lease_owner is None
    assert not workspace_lease_path.exists()


def test_background_worker_drains_queued_campaigns_before_lease_lost_recovery(
    tmp_path: Path,
    capsys,
) -> None:
    _, workspaces_root, target_root = _init_demo_workspace(tmp_path)
    config_path = _write_success_config(tmp_path, name="queued-before-recovery")
    queued_plan_path = _write_edit_plan(tmp_path, filename="queued")
    recovery_plan_path = _write_edit_plan(tmp_path, filename="recovery")

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(queued_plan_path),
                "--background",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    queued_campaign = json.loads(capsys.readouterr().out)["campaign"]

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(recovery_plan_path),
                "--background",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    recovery_campaign = json.loads(capsys.readouterr().out)["campaign"]

    stale_timestamp = _stale_utc_timestamp()
    campaign = campaign_runs.load_campaign_run(
        root=workspaces_root,
        workspace_id="demo",
        track_id="main",
        campaign_run_id=recovery_campaign["campaign_run_id"],
    )
    campaign_runs.persist_campaign_run(
        root=workspaces_root,
        campaign=replace(
            campaign,
            status="paused",
            desired_state="run",
            stop_reason="lease_lost",
            lease_owner="lost_worker",
            lease_claimed_at=stale_timestamp,
            lease_heartbeat_at=stale_timestamp,
            lease_expires_at=stale_timestamp,
        ),
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign-worker",
                "--workspace-id",
                "demo",
                "--worker-id",
                "priority_worker",
                "--max-campaigns",
                "1",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    worker = json.loads(capsys.readouterr().out)
    assert worker["claimed_campaign_total"] == 1
    assert worker["campaigns"][0]["campaign_id"] == queued_campaign["campaign_run_id"]

    completed_queued = campaign_runs.load_campaign_run(
        root=workspaces_root,
        workspace_id="demo",
        track_id="main",
        campaign_run_id=queued_campaign["campaign_run_id"],
    )
    deferred_recovery = campaign_runs.load_campaign_run(
        root=workspaces_root,
        workspace_id="demo",
        track_id="main",
        campaign_run_id=recovery_campaign["campaign_run_id"],
    )
    assert completed_queued.status == "completed"
    assert deferred_recovery.status == "paused"
    assert deferred_recovery.stop_reason == "lease_lost"


def test_pause_cancel_and_resume_background_campaigns(tmp_path: Path, capsys) -> None:
    _, workspaces_root, target_root = _init_demo_workspace(tmp_path)
    config_path = _write_success_config(tmp_path, name="paused-campaign")
    edit_plan_path = _write_edit_plan(tmp_path, filename="beta")

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--background",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    queued = json.loads(capsys.readouterr().out)
    paused_campaign_id = queued["campaign"]["campaign_run_id"]

    capsys.readouterr()
    assert (
        main(
            [
                "pause-campaign",
                "--workspace-id",
                "demo",
                "--campaign-id",
                paused_campaign_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    paused = json.loads(capsys.readouterr().out)
    assert paused["campaign"]["desired_state"] == "paused"
    assert paused["campaign"]["status"] == "paused"

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign-worker",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    idle_worker = json.loads(capsys.readouterr().out)
    assert idle_worker["claimed_campaign_total"] == 0

    capsys.readouterr()
    assert (
        main(
            [
                "resume-campaign",
                "--workspace-id",
                "demo",
                "--campaign-id",
                paused_campaign_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    resumed = json.loads(capsys.readouterr().out)
    assert resumed["campaign"]["status"] == "completed"
    assert resumed["campaign"]["desired_state"] == "run"

    cancel_plan_path = _write_edit_plan(tmp_path, filename="gamma")
    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(cancel_plan_path),
                "--background",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    queued_cancel = json.loads(capsys.readouterr().out)
    canceled_campaign_id = queued_cancel["campaign"]["campaign_run_id"]

    capsys.readouterr()
    assert (
        main(
            [
                "cancel-campaign",
                "--workspace-id",
                "demo",
                "--campaign-id",
                canceled_campaign_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    canceled = json.loads(capsys.readouterr().out)
    assert canceled["campaign"]["desired_state"] == "canceled"
    assert canceled["campaign"]["status"] == "canceled"

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign-worker",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    canceled_worker = json.loads(capsys.readouterr().out)
    assert canceled_worker["claimed_campaign_total"] == 0


def test_provider_profile_retention_and_root_memory_commands(
    tmp_path: Path,
    capsys,
) -> None:
    _, workspaces_root, _ = _init_demo_workspace(tmp_path)

    capsys.readouterr()
    assert (
        main(
            [
                "set-provider-profile",
                "--workspace-id",
                "demo",
                "--provider-id",
                "local_command",
                "--option",
                "model=gpt-5.4",
                "--option",
                "endpoint=http://localhost:8000",
                "--option",
                "api_key=super-secret",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    provider_update = json.loads(capsys.readouterr().out)
    assert provider_update["provider_id"] == "local_command"
    assert provider_update["profile"]["model"] == "gpt-5.4"
    assert provider_update["profile"]["api_key"] == "[redacted]"
    assert provider_update["profile_summary"]["redacted_key_total"] >= 1

    capsys.readouterr()
    assert (
        main(
            [
                "show-provider-profile",
                "--workspace-id",
                "demo",
                "--provider-id",
                "local_command",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    provider_profile = json.loads(capsys.readouterr().out)
    assert provider_profile["profile"]["endpoint"] == "http://localhost:8000"
    assert provider_profile["profile"]["api_key"] == "[redacted]"
    assert provider_profile["profile_summary"]["profile_applied"] is True

    capsys.readouterr()
    assert (
        main(
            [
                "set-retention-policy",
                "--workspace-id",
                "demo",
                "--keep-latest-campaign-runs",
                "2",
                "--prune-failed-candidate-patches-older-than-days",
                "7",
                "--no-keep-champion-campaigns-forever",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    retention_update = json.loads(capsys.readouterr().out)
    assert retention_update["policy"]["keep_latest_campaign_runs"] == 2
    assert (
        retention_update["policy"]["prune_failed_candidate_patches_older_than_days"] == 7
    )
    assert retention_update["policy"]["keep_champion_campaigns_forever"] is False

    capsys.readouterr()
    assert (
        main(
            [
                "prune-artifacts",
                "--workspace-id",
                "demo",
                "--dry-run",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    prune_result = json.loads(capsys.readouterr().out)
    assert prune_result["dry_run"] is True
    assert prune_result["policy"]["keep_latest_campaign_runs"] == 2
    assert isinstance(prune_result["keep_reasons_by_path"], dict)
    assert isinstance(prune_result["reference_summary"]["reference_source_total"], int)

    capsys.readouterr()
    assert (
        main(
            [
                "show-root-memory",
                "--workspace-id",
                "demo",
                "--refresh",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    root_memory = json.loads(capsys.readouterr().out)
    assert root_memory["champion_total"] == 0
    assert root_memory["transfer_suggestions"] == []
    assert len(root_memory["workspace_insights"]) == 1
    assert len(root_memory["portfolio_schedule"]) == 1

    capsys.readouterr()
    assert main(["show-plugin-catalog", "--json"]) == 0
    plugin_catalog = json.loads(capsys.readouterr().out)
    assert isinstance(plugin_catalog["plugin_total"], int)
    assert isinstance(plugin_catalog["load_failure_total"], int)


def test_prune_artifacts_keeps_report_referenced_campaigns(
    tmp_path: Path,
    capsys,
) -> None:
    _, workspaces_root, target_root = _init_demo_workspace(tmp_path)
    config_path = _write_success_config(tmp_path, name="retention-report")
    edit_plan_path = _write_edit_plan(tmp_path, filename="delta")

    capsys.readouterr()
    assert (
        main(
            [
                "run-campaign",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--target-root",
                str(target_root),
                "--edit-plan",
                str(edit_plan_path),
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    campaign_run = json.loads(capsys.readouterr().out)
    campaign_id = campaign_run["campaign"]["campaign_run_id"]
    campaign_path = campaign_run["campaign_path"]

    report_path = workspaces_root / "demo" / "referenced_campaign_report.json"
    capsys.readouterr()
    assert (
        main(
            [
                "export-campaign-report",
                "--workspace-id",
                "demo",
                "--campaign-id",
                campaign_id,
                "--root",
                str(workspaces_root),
                "--output",
                str(report_path),
            ]
        )
        == 0
    )

    capsys.readouterr()
    assert (
        main(
            [
                "set-retention-policy",
                "--workspace-id",
                "demo",
                "--keep-latest-campaign-runs",
                "0",
                "--no-keep-champion-campaigns-forever",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "prune-artifacts",
                "--workspace-id",
                "demo",
                "--dry-run",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    prune_result = json.loads(capsys.readouterr().out)
    assert campaign_path in prune_result["kept_campaign_paths"]
    assert "referenced by structured report or bundle" in prune_result["keep_reasons_by_path"][campaign_path]
    assert str(report_path) in prune_result["reference_summary"]["reference_sources"]


def test_show_plugin_catalog_reports_contract_failures(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    valid_plugin = plugin_dir / "valid_plugin.py"
    valid_plugin.write_text(
        "\n".join(
            [
                "PLUGIN_INFO = {",
                "    'name': 'valid-plugin',",
                "    'api_version': 'autoharness.plugin.v1',",
                "    'enabled': True,",
                "}",
                "def register_search_strategies():",
                "    return {",
                "        'plugin_strategy': {",
                "            'label': 'Plugin Strategy',",
                "            'hook': 'regression_first',",
                "        }",
                "    }",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    invalid_plugin = plugin_dir / "invalid_plugin.py"
    invalid_plugin.write_text("def register_search_strategies():\n    return {}\n", encoding="utf-8")

    monkeypatch.setenv("AUTOHARNESS_PLUGIN_PATHS", str(plugin_dir))
    plugins.load_plugin_catalog.cache_clear()
    try:
        capsys.readouterr()
        assert main(["show-plugin-catalog", "--json"]) == 0
        catalog = json.loads(capsys.readouterr().out)
    finally:
        plugins.load_plugin_catalog.cache_clear()
        monkeypatch.delenv("AUTOHARNESS_PLUGIN_PATHS", raising=False)

    assert catalog["plugin_total"] == 2
    assert catalog["load_failure_total"] == 1
    loaded_plugins = [item for item in catalog["plugins"] if item["status"] == "loaded"]
    assert len(loaded_plugins) == 1
    assert loaded_plugins[0]["search_strategy_ids"] == ["plugin_strategy"]
    assert catalog["search_runtime_contracts"]["plugin_strategy"]["hook"] == "regression_first"


def test_run_root_campaigns_with_workers_uses_local_worker_pool(
    tmp_path: Path,
    capsys,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    for workspace_id in ("demo", "demo_b"):
        main(
            [
                "init-workspace",
                "--workspace-id",
                workspace_id,
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )

    config_path = tmp_path / "root-workers.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "root-workers",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(0.2); print('ok')",
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    capsys.readouterr()
    assert (
        main(
            [
                "run-root-campaigns",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--workers",
                "2",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["workspace_total"] == 2
    assert rendered["completed_workspace_total"] == 2
    assert rendered["status"] == "completed"
    assert rendered["workers_requested"] == 2
    assert rendered["schedule_mode"] == "portfolio"
    assert len(rendered["workspace_schedule"]) == 2
    assert len(rendered["worker_results"]) == 2
    assert sum(
        int(item["claimed_campaign_total"]) for item in rendered["worker_results"]
    ) == 2
    assert rendered["event_metrics"]["generator_counts"]["failure_summary"] >= 2
    assert rendered["event_metrics"]["adapter_counts"]["generic_command"] >= 2
    for workspace_item in rendered["workspaces"]:
        assert workspace_item["status"] == "completed"
        assert workspace_item["rendered"]["track_total"] == 1
        assert workspace_item["rendered"]["tracks"][0]["campaign_status"] == "paused"


def test_concurrent_background_workers_do_not_double_claim_campaigns(
    tmp_path: Path,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root_base = tmp_path / "targets"

    main(["setup", "--output", str(settings)])
    workspace_ids = ["demo", "demo_b", "demo_c"]
    for workspace_id in workspace_ids:
        main(
            [
                "init-workspace",
                "--workspace-id",
                workspace_id,
                "--objective",
                "Improve harness correctness",
                "--benchmark",
                "tau-bench-airline",
                "--settings",
                str(settings),
                "--root",
                str(workspaces_root),
            ]
        )
        main(
            [
                "create-track",
                "--workspace-id",
                workspace_id,
                "--track-id",
                "alt",
                "--root",
                str(workspaces_root),
            ]
        )

    config_path = tmp_path / "queued-workers.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "queued-workers",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    "import time; time.sleep(0.2); print('ok')",
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "run-root-campaigns",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "failure_summary",
                "--target-root-base",
                str(target_root_base),
                "--max-proposals",
                "1",
                "--background",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )

    with ProcessPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                campaign_handlers._run_campaign_worker,
                root=workspaces_root,
                workspace_ids=workspace_ids,
                track_ids=[],
                worker_id=f"contention_worker_{index + 1:02d}",
                lease_seconds=300,
                max_campaigns=3,
            )
            for index in range(2)
        ]
        worker_results = [future.result() for future in futures]

    claimed_campaign_ids = [
        str(item["campaign_id"])
        for worker_result in worker_results
        for item in worker_result["campaigns"]
    ]
    assert sorted(
        int(worker_result["claimed_campaign_total"]) for worker_result in worker_results
    ) == [3, 3]
    assert len(claimed_campaign_ids) == 6
    assert len(set(claimed_campaign_ids)) == 6
