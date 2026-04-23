from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

import autoharness.generators.openai_responses_generator as openai_responses_generator
from autoharness.cli import main


def test_generate_proposal_persists_artifacts_and_show_proposal(
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
                "benchmark_name": "proposal-smoke",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "format_version": "autoharness.edit_plan.v1",
                "summary": "Create one candidate file",
                "operations": [
                    {
                        "type": "write_file",
                        "path": "candidate.txt",
                        "content": "candidate change\n",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "proposal.json"
    capsys.readouterr()
    assert (
        main(
            [
                "generate-proposal",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(target_root),
                "--hypothesis",
                "Preview candidate patch",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    proposal = rendered["proposal"]
    artifacts = rendered["artifacts"]
    proposal_id = proposal["proposal_id"]

    assert proposal["track_id"] == "main"
    assert proposal["preview_state"] == "preview"
    assert proposal["operation_count"] == 1
    assert Path(artifacts["proposal_path"]).exists()
    assert Path(artifacts["edit_plan_path"]).exists()
    assert Path(artifacts["preview_application_path"]).exists()
    assert Path(artifacts["patch_path"]).exists()
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered
    assert not (target_root / "candidate.txt").exists()

    capsys.readouterr()
    assert (
        main(
            [
                "show-proposal",
                "--workspace-id",
                "demo",
                "--proposal-id",
                proposal_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    shown = json.loads(capsys.readouterr().out)
    assert shown["proposal"]["proposal_id"] == proposal_id
    assert shown["proposal"]["hypothesis"] == "Preview candidate patch"
    assert shown["edit_plan"]["summary"] == "Create one candidate file"
    assert shown["preview_application"]["preview_only"] is True
    assert shown["preview_application"]["plan_path"] == str(edit_plan_path)


def test_show_and_export_proposals(
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
                "benchmark_name": "proposal-smoke",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    for filename, hypothesis, notes in (
        ("alpha.txt", "Alpha candidate", "stage alpha"),
        ("beta.txt", "Beta candidate", "stage beta"),
    ):
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
        assert (
            main(
                [
                    "generate-proposal",
                    "--workspace-id",
                    "demo",
                    "--adapter",
                    "generic_command",
                    "--config",
                    str(config_path),
                    "--edit-plan",
                    str(edit_plan_path),
                    "--target-root",
                    str(target_root),
                    "--hypothesis",
                    hypothesis,
                    "--notes",
                    notes,
                    "--root",
                    str(workspaces_root),
                ]
            )
            == 0
        )

    output_path = tmp_path / "proposals.json"
    capsys.readouterr()
    assert (
        main(
            [
                "show-proposals",
                "--workspace-id",
                "demo",
                "--hypothesis-contains",
                "beta",
                "--root",
                str(workspaces_root),
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["non_executable_proposals_total"] == 0
    assert [item["hypothesis"] for item in rendered["proposals"]] == ["Beta candidate"]
    assert rendered["proposals"][0]["preview_state"] == "preview"
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered

    export_path = tmp_path / "proposals.yaml"
    capsys.readouterr()
    assert (
        main(
            [
                "export-proposals",
                "--workspace-id",
                "demo",
                "--notes-contains",
                "stage",
                "--output",
                str(export_path),
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )
    export_payload = yaml.safe_load(export_path.read_text(encoding="utf-8"))
    assert export_payload["format_version"] == "autoharness.proposal_export.v1"
    assert len(export_payload["proposals"]) == 2

    capsys.readouterr()
    assert main(["show-listing-file", str(export_path), "--json"]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["listing_type"] == "proposal_export"
    assert shown["workspace_id"] == "demo"
    assert shown["item_total"] == 2

    capsys.readouterr()
    assert main(["validate-listing-file", str(export_path), "--json"]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["listing_type"] == "proposal_export"
    assert validated["valid"] is True


def test_list_and_show_generators(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "generators.json"

    capsys.readouterr()
    assert (
        main(
            [
                "list-generators",
                "--json",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )
    rendered = json.loads(capsys.readouterr().out)
    assert json.loads(output_path.read_text(encoding="utf-8")) == rendered
    generator_ids = {item["generator_id"] for item in rendered["generators"]}
    assert generator_ids == {
        "failure_summary",
        "local_command",
        "local_template",
        "manual",
        "openai_responses",
    }
    manual_entry = next(
        item for item in rendered["generators"] if item["generator_id"] == "manual"
    )
    assert manual_entry["requires_edit_plan_input"] is True
    assert manual_entry["can_generate_without_edit_plan"] is False

    capsys.readouterr()
    assert (
        main(
            [
                "show-generator",
                "--generator",
                "local_command",
                "--json",
            ]
        )
        == 0
    )
    generator_rendered = json.loads(capsys.readouterr().out)
    assert generator_rendered["generator_id"] == "local_command"
    assert generator_rendered["can_generate_without_edit_plan"] is True
    assert generator_rendered["generator_option_keys"] == [
        "command_path",
        "timeout_seconds",
        "command_cwd",
        "fallback_generators",
    ]

    capsys.readouterr()
    assert (
        main(
            [
                "show-generator",
                "--generator",
                "openai_responses",
                "--json",
            ]
        )
        == 0
    )
    generator_rendered = json.loads(capsys.readouterr().out)
    assert generator_rendered["generator_id"] == "openai_responses"
    assert generator_rendered["generator_option_keys"] == [
        "model",
        "reasoning_effort",
        "timeout_seconds",
        "base_url",
        "proposal_scope",
        "max_operations",
        "fallback_generators",
    ]


def test_generate_proposal_with_failure_summary_generator_without_edit_plan(
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

    failing_config_path = tmp_path / "failing.yaml"
    failing_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "proposal-context-failure",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "import sys; sys.exit(1)"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "run-iteration",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(failing_config_path),
                "--hypothesis",
                "Seed failing context",
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    passing_config_path = tmp_path / "passing.yaml"
    passing_config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "proposal-smoke",
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
                "generate-proposal",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(passing_config_path),
                "--generator",
                "failure_summary",
                "--intervention-class",
                "source",
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
    assert rendered["proposal"]["generator_id"] == "failure_summary"
    assert rendered["proposal"]["intervention_class"] == "source"
    assert rendered["generation_request"]["source_mode"] == "direct_cli"
    edit_plan = json.loads(Path(rendered["artifacts"]["edit_plan_path"]).read_text(encoding="utf-8"))
    assert edit_plan["operations"][0]["path"].endswith("source_candidate_000.py")


def test_generate_proposal_with_openai_responses_generator(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()
    (target_root / "service.py").write_text("print('hello')\n", encoding="utf-8")

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
                "benchmark_name": "proposal-openai",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call(**kwargs):
        request_payload = kwargs["request_payload"]
        assert request_payload["model"] == "gpt-5.1"
        assert request_payload["reasoning"]["effort"] == "high"
        assert "up to 8 operations" in request_payload["instructions"]
        prompt_payload = json.loads(request_payload["input"][0]["content"][0]["text"])
        assert prompt_payload["proposal_profile"]["scope"] == "broad"
        assert prompt_payload["proposal_profile"]["max_operations"] == 8
        return {
            "id": "resp_cli",
            "output_text": json.dumps(
                {
                    "hypothesis": "Refine service greeting",
                    "summary": "Patch the service module greeting",
                    "intervention_class": "source",
                    "operations": [
                        {
                            "type": "search_replace",
                            "path": "service.py",
                            "search": "print('hello')\n",
                            "replace": "print('hello world')\n",
                            "expected_count": 1,
                        }
                    ],
                }
            ),
        }

    monkeypatch.setattr(
        openai_responses_generator,
        "_call_openai_responses_api",
        fake_call,
    )

    capsys.readouterr()
    assert (
        main(
            [
                "generate-proposal",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "openai_responses",
                "--generator-option",
                "model=gpt-5.1",
                "--generator-option",
                "reasoning_effort=high",
                "--generator-option",
                "proposal_scope=broad",
                "--generator-option",
                "max_operations=8",
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
    assert rendered["proposal"]["generator_id"] == "openai_responses"
    assert rendered["proposal"]["hypothesis"] == "Refine service greeting"
    assert rendered["proposal"]["generator_metadata"]["provider"] == "openai"
    assert rendered["proposal"]["generator_metadata"]["proposal_scope"] == "broad"
    assert rendered["proposal"]["generator_metadata"]["max_operations"] == 8


def test_generate_proposal_with_local_command_generator(
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
                "benchmark_name": "proposal-local-command",
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
                "    'hypothesis': f\"Command proposal {request['candidate_index']}\",",
                "    'summary': 'Generate one local-command candidate',",
                "    'intervention_class': request.get('intervention_class') or 'source',",
                "    'operations': [",
                "        {",
                "            'type': 'write_file',",
                "            'path': f\".autoharness/generated/local_command_{request['candidate_index']}.txt\",",
                "            'content': f\"workspace={context['workspace_id']}\\nstage={context['stage']}\\n\",",
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
                "generate-proposal",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "local_command",
                "--intervention-class",
                "source",
                "--generator-option",
                f"command_path={script_path}",
                "--generator-option",
                "timeout_seconds=15",
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
    assert rendered["proposal"]["generator_id"] == "local_command"
    assert rendered["proposal"]["hypothesis"] == "Command proposal 0"
    assert rendered["proposal"]["generator_metadata"]["provider"] == "local_command"
    edit_plan = json.loads(
        Path(rendered["artifacts"]["edit_plan_path"]).read_text(encoding="utf-8")
    )
    assert edit_plan["operations"][0]["path"].endswith("local_command_0.txt")


def test_generate_proposal_uses_fallback_generator_chain(
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

    config_path = tmp_path / "generic_fallback.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "proposal-fallback",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    failing_script_path = tmp_path / "proposal_generator_fail.py"
    failing_script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "raise SystemExit(1)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    failing_script_path.chmod(0o755)

    template_path = tmp_path / "fallback_template.yaml"
    template_path.write_text(
        yaml.safe_dump(
            {
                "hypothesis": "Fallback proposal",
                "summary": "Template fallback candidate",
                "intervention_class": "source",
                "operations": [
                    {
                        "type": "write_file",
                        "path": ".autoharness/generated/fallback.txt",
                        "content": "fallback\n",
                    }
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
                "generate-proposal",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--generator",
                "local_command",
                "--generator-option",
                f"command_path={failing_script_path}",
                "--generator-option",
                "fallback_generators=local_template",
                "--generator-option",
                f"template_path={template_path}",
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
    assert rendered["proposal"]["generator_id"] == "local_template"
    metadata = rendered["proposal"]["generator_metadata"]
    assert metadata["requested_generator_id"] == "local_command"
    assert metadata["fallback_used"] is True
    assert len(metadata["generator_attempts"]) == 2
    assert metadata["generator_attempts"][0]["status"] == "error"
    assert metadata["generator_attempts"][1]["status"] == "success"


def test_apply_proposal_keeps_edits_and_run_proposal_records_lineage(
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
                "benchmark_name": "proposal-smoke",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "print('ok')"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "operations": [
                    {
                        "type": "write_file",
                        "path": "candidate.txt",
                        "content": "candidate change\n",
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
                "generate-proposal",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(target_root),
                "--hypothesis",
                "Candidate run",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    generated = json.loads(capsys.readouterr().out)
    proposal_id = generated["proposal"]["proposal_id"]

    capsys.readouterr()
    assert (
        main(
            [
                "apply-proposal",
                "--workspace-id",
                "demo",
                "--proposal-id",
                proposal_id,
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["edit_application"]["status"] == "applied"
    assert applied["edit_restore"]["status"] == "kept"
    assert (target_root / "candidate.txt").read_text(encoding="utf-8") == "candidate change\n"

    (target_root / "candidate.txt").unlink()

    assert (
        main(
            [
                "run-proposal",
                "--workspace-id",
                "demo",
                "--proposal-id",
                proposal_id,
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    state = json.loads(
        (workspaces_root / "demo" / "state.json").read_text(encoding="utf-8")
    )
    assert state["last_iteration_id"] == "iter_0001"

    iteration_summary = json.loads(
        (
            workspaces_root
            / "demo"
            / "iterations"
            / "iter_0001"
            / "summary.json"
        ).read_text(encoding="utf-8")
    )
    assert iteration_summary["source_proposal_id"] == proposal_id
    assert iteration_summary["source_proposal_path"].endswith(
        f"tracks/main/proposals/{proposal_id}/proposal.json"
    )

    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    assert len(registry_records) == 1
    record = json.loads(registry_records[0].read_text(encoding="utf-8"))
    assert record["source_proposal_id"] == proposal_id
    assert record["source_proposal_path"].endswith(
        f"tracks/main/proposals/{proposal_id}/proposal.json"
    )


def test_run_proposal_inherits_campaign_preflight_policy(
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

    preflight_marker = tmp_path / "preflight_marker.txt"
    benchmark_marker = tmp_path / "benchmark_marker.txt"
    preflight_script = tmp_path / "preflight_ok.py"
    preflight_script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                f"Path({str(preflight_marker)!r}).write_text('ok', encoding='utf-8')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "set-workspace",
                "--workspace-id",
                "demo",
                "--root",
                str(workspaces_root),
                "--campaign-preflight-command",
                f"{sys.executable} {preflight_script}",
                "--campaign-preflight-timeout-seconds",
                "11",
            ]
        )
        == 0
    )

    config_path = tmp_path / "generic.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "benchmark_name": "proposal-preflight",
                "workdir": str(tmp_path),
                "command": [
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"Path({str(benchmark_marker)!r}).write_text('ok', encoding='utf-8')"
                    ),
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "format_version": "autoharness.edit_plan.v1",
                "summary": "Create one candidate file",
                "operations": [
                    {
                        "type": "write_file",
                        "path": "candidate.txt",
                        "content": "candidate change\n",
                    }
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
                "generate-proposal",
                "--workspace-id",
                "demo",
                "--adapter",
                "generic_command",
                "--config",
                str(config_path),
                "--edit-plan",
                str(edit_plan_path),
                "--target-root",
                str(target_root),
                "--hypothesis",
                "Candidate run with inherited preflight",
                "--root",
                str(workspaces_root),
                "--json",
            ]
        )
        == 0
    )
    generated = json.loads(capsys.readouterr().out)
    proposal_id = generated["proposal"]["proposal_id"]

    assert (
        main(
            [
                "run-proposal",
                "--workspace-id",
                "demo",
                "--proposal-id",
                proposal_id,
                "--root",
                str(workspaces_root),
            ]
        )
        == 0
    )

    registry_records = sorted(
        (workspaces_root / "demo" / "tracks" / "main" / "registry").glob("*.json")
    )
    assert len(registry_records) == 1
    record = json.loads(registry_records[0].read_text(encoding="utf-8"))
    payload = record["payload"]

    assert payload["preflight_validation"]["all_passed"] is True
    assert payload["preflight_validation"]["timeout_seconds"] == 11
    assert preflight_marker.read_text(encoding="utf-8") == "ok"
    assert benchmark_marker.read_text(encoding="utf-8") == "ok"
