from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

import autoharness.generators.assistant_cli_generator as assistant_cli_generator
import autoharness.generators.openai_responses_generator as openai_responses_generator
from autoharness.cli import main
from autoharness.generators import ProposalGenerationRequest, get_generator
from autoharness.proposal_context import build_proposal_generation_context
from autoharness.tracking import load_workspace, load_workspace_state


def test_manual_generator_loads_edit_plan_and_context(
    tmp_path: Path,
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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="screening",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={"benchmark_name": "proposal-smoke", "command": ["python", "-c", "print('ok')"]},
        target_root=target_root,
    )

    edit_plan_path = tmp_path / "edit_plan.yaml"
    edit_plan_path.write_text(
        yaml.safe_dump(
            {
                "summary": "Create candidate file",
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

    generator = get_generator("manual")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=0,
            strategy_id="direct",
            source_mode="test",
            input_edit_plan_path=str(edit_plan_path),
        ),
        edit_plan_path=edit_plan_path,
    )

    assert generated.generator_id == "manual"
    assert generated.summary == "Create candidate file"
    assert generated.edit_plan.operations[0].path == "candidate.txt"
    assert generated.metadata["edit_plan_path"] == str(edit_plan_path)
    assert generated.metadata["generation_request"]["candidate_index"] == 0
    assert context.workspace_id == "demo"
    assert context.track_id == "main"
    assert context.selected_preset == "search"


def test_failure_summary_generator_uses_latest_failure_context(
    tmp_path: Path,
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
                "benchmark_name": "failing-context",
                "workdir": str(tmp_path),
                "command": ["python", "-c", "import sys; sys.exit(1)"],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    main(
        [
            "run-iteration",
            "--workspace-id",
            "demo",
            "--adapter",
            "generic_command",
            "--stage",
            "screening",
            "--config",
            str(failing_config_path),
            "--hypothesis",
            "seed failure context",
            "--root",
            str(workspaces_root),
        ]
    )

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="screening",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={"benchmark_name": "proposal-smoke", "command": ["python", "-c", "print('ok')"]},
        target_root=target_root,
    )

    generator = get_generator("failure_summary")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=2,
            strategy_id="greedy_failure_focus",
            source_mode="generator_loop",
            intervention_class="config",
        ),
    )

    assert generated.generator_id == "failure_summary"
    assert generated.intervention_class == "config"
    assert generated.edit_plan.operations[0].path.endswith("config_candidate_002.json")
    assert "generation_request" in generated.metadata


def test_openai_responses_generator_uses_api_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = tmp_path / ".autoharness" / "settings.yaml"
    workspaces_root = tmp_path / ".autoharness" / "workspaces"
    target_root = tmp_path / "candidate"
    target_root.mkdir()
    (target_root / "service.py").write_text("print('hello')\n", encoding="utf-8")
    (target_root / "router.py").write_text("def route():\n    return 'primary'\n", encoding="utf-8")
    (target_root / "config.yaml").write_text("retries: 1\n", encoding="utf-8")

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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="screening",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={"benchmark_name": "proposal-smoke", "command": ["python", "-c", "print('ok')"]},
        target_root=target_root,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AUTOHARNESS_OPENAI_MODEL", "gpt-5.2")

    def fake_call(**kwargs):
        request_payload = kwargs["request_payload"]
        assert request_payload["model"] == "gpt-5.1"
        assert request_payload["reasoning"]["effort"] == "high"
        assert "up to 7 operations" in request_payload["instructions"]
        prompt_payload = json.loads(request_payload["input"][0]["content"][0]["text"])
        assert prompt_payload["context"]["workspace_id"] == "demo"
        assert prompt_payload["proposal_profile"]["scope"] == "broad"
        assert prompt_payload["proposal_profile"]["max_operations"] == 7
        assert "service.py" in {
            entry["path"] for entry in prompt_payload["repo_snapshot"]["sampled_files"]
        }
        assert len(prompt_payload["repo_snapshot"]["prioritized_paths"]) >= 3
        return {
            "id": "resp_test",
            "output_text": json.dumps(
                {
                    "hypothesis": "Tighten service output handling",
                    "summary": "Update the service module",
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

    generator = get_generator("openai_responses")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=1,
            strategy_id="greedy_failure_focus",
            source_mode="generator_loop",
            intervention_class="source",
            metadata={
                "model": "gpt-5.1",
                "reasoning_effort": "high",
                "proposal_scope": "broad",
                "max_operations": "7",
            },
        ),
    )

    assert generated.generator_id == "openai_responses"
    assert generated.summary == "Update the service module"
    assert generated.hypothesis == "Tighten service output handling"
    assert generated.intervention_class == "source"
    assert generated.edit_plan.operations[0].type == "search_replace"
    assert generated.edit_plan.operations[0].path == "service.py"
    assert generated.metadata["provider"] == "openai"
    assert generated.metadata["response_id"] == "resp_test"
    assert generated.metadata["provider_request_payload"]["model"] == "gpt-5.1"
    assert generated.metadata["proposal_scope"] == "broad"
    assert generated.metadata["max_operations"] == 7
    assert generated.metadata["max_repair_attempts"] == 1
    assert generated.metadata["repair_attempt_count"] == 0
    assert generated.metadata["provider_attempts"][0]["status"] == "success"
    assert generated.metadata["repair_steps"] == []


def test_openai_responses_generator_repairs_fenced_files_payload(
    tmp_path: Path,
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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="validation",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={"benchmark_name": "proposal-smoke", "command": ["python", "-c", "print('ok')"]},
        target_root=target_root,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_call(**kwargs):
        return {
            "id": "resp_repair",
            "output_text": (
                "Proposal draft follows.\n"
                "```json\n"
                + json.dumps(
                    {
                        "hypothesis": "Repair service greeting",
                        "files": {
                            "service.py": "print('hello repaired')\n",
                        },
                    }
                )
                + "\n```"
            ),
        }

    monkeypatch.setattr(
        openai_responses_generator,
        "_call_openai_responses_api",
        fake_call,
    )

    generator = get_generator("openai_responses")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=2,
            strategy_id="greedy_failure_focus",
            source_mode="generator_loop",
            intervention_class="source",
        ),
    )

    assert generated.edit_plan.operations[0].type == "write_file"
    assert generated.edit_plan.operations[0].path == "service.py"
    assert generated.metadata["response_id"] == "resp_repair"
    assert "recovered_json_object_from_response_text" in generated.metadata["repair_steps"]
    assert "repaired_operations_payload" in generated.metadata["repair_steps"]


def test_openai_responses_generator_attempts_provider_repair_on_invalid_output(
    tmp_path: Path,
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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="validation",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={"benchmark_name": "proposal-smoke", "command": ["python", "-c", "print('ok')"]},
        target_root=target_root,
    )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    call_payloads: list[dict[str, object]] = []

    def fake_call(**kwargs):
        request_payload = kwargs["request_payload"]
        call_payloads.append(request_payload)
        if len(call_payloads) == 1:
            return {
                "id": "resp_invalid",
                "output_text": "this is not valid json",
            }
        repair_prompt = json.loads(request_payload["input"][0]["content"][0]["text"])
        assert repair_prompt["task"].startswith("Repair an invalid autoharness proposal")
        assert repair_prompt["invalid_response_text"] == "this is not valid json"
        return {
            "id": "resp_repaired",
            "output_text": json.dumps(
                {
                    "hypothesis": "Repair invalid provider output",
                    "summary": "Repair the service proposal",
                    "intervention_class": "source",
                    "operations": [
                        {
                            "type": "write_file",
                            "path": "service.py",
                            "content": "print('hello repaired')\n",
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

    generator = get_generator("openai_responses")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=3,
            strategy_id="greedy_failure_focus",
            source_mode="generator_loop",
            intervention_class="source",
            metadata={"max_repair_attempts": "1"},
        ),
    )

    assert len(call_payloads) == 2
    assert generated.edit_plan.operations[0].type == "write_file"
    assert generated.metadata["response_id"] == "resp_repaired"
    assert generated.metadata["repair_attempt_count"] == 1
    assert generated.metadata["provider_attempts"][0]["status"] == "invalid"
    assert generated.metadata["provider_attempts"][0]["parse_error"]
    assert generated.metadata["provider_attempts"][1]["status"] == "success"


def test_local_template_generator_renders_context_variables(
    tmp_path: Path,
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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="screening",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={"benchmark_name": "proposal-smoke", "command": ["python", "-c", "print('ok')"]},
        target_root=target_root,
    )

    template_path = tmp_path / "template.yaml"
    template_path.write_text(
        yaml.safe_dump(
            {
                "hypothesis": "Tighten {intervention_class} handling for {focus_label}",
                "summary": "Render {intervention_class} candidate {candidate_index}",
                "intervention_class": "{intervention_class}",
                "operations": [
                    {
                        "type": "write_file",
                        "path": ".autoharness/generated/{intervention_class}_{candidate_index}.txt",
                        "content": "workspace={workspace_id}\nfocus={focus_task_ids_csv}\n",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    generator = get_generator("local_template")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=4,
            strategy_id="beam_interventions",
            source_mode="generator_loop",
            intervention_class="source",
            failure_focus_task_ids=("task_a", "task_b"),
            metadata={"template_path": str(template_path)},
        ),
    )

    assert generated.generator_id == "local_template"
    assert generated.hypothesis == "Tighten source handling for task_a, task_b"
    assert generated.summary == "Render source candidate 4"
    assert generated.intervention_class == "source"
    assert generated.edit_plan.operations[0].path == ".autoharness/generated/source_4.txt"
    assert "workspace=demo" in str(generated.edit_plan.operations[0].content)
    assert "focus=task_a,task_b" in str(generated.edit_plan.operations[0].content)
    assert generated.metadata["provider"] == "local_template"


def test_local_command_generator_invokes_script(
    tmp_path: Path,
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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="screening",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={
            "benchmark_name": "proposal-smoke",
            "command": ["python", "-c", "print('ok')"],
        },
        target_root=target_root,
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
                "    'hypothesis': f\"Command candidate {request['candidate_index']}\",",
                "    'summary': f\"Local command proposal {request['candidate_index']}\",",
                "    'intervention_class': request.get('intervention_class') or 'source',",
                "    'operations': [",
                "        {",
                "            'type': 'write_file',",
                "            'path': f\".autoharness/generated/command_{request['candidate_index']}.txt\",",
                "            'content': f\"workspace={context['workspace_id']}\\nstrategy={request['strategy_id']}\\n\",",
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

    generator = get_generator("local_command")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=6,
            strategy_id="beam_interventions",
            source_mode="generator_loop",
            intervention_class="source",
            metadata={"command_path": str(script_path), "timeout_seconds": "15"},
        ),
    )

    assert generated.generator_id == "local_command"
    assert generated.summary == "Local command proposal 6"
    assert generated.hypothesis == "Command candidate 6"
    assert generated.intervention_class == "source"
    assert generated.edit_plan.operations[0].path == ".autoharness/generated/command_6.txt"
    assert "workspace=demo" in str(generated.edit_plan.operations[0].content)
    assert generated.metadata["provider"] == "local_command"
    assert generated.metadata["generator_input_payload"]["request"]["candidate_index"] == 6
    assert generated.metadata["repair_steps"] == []


def test_local_command_generator_repairs_files_payload(
    tmp_path: Path,
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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="screening",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={
            "benchmark_name": "proposal-smoke",
            "command": ["python", "-c", "print('ok')"],
        },
        target_root=target_root,
    )

    script_path = tmp_path / "proposal_generator_files.py"
    script_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "import json",
                "print('proposal wrapper')",
                "print(json.dumps({'hypothesis': 'Files payload', 'files': {'candidate.txt': 'candidate\\n'}}))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    script_path.chmod(0o755)

    generator = get_generator("local_command")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=7,
            strategy_id="beam_interventions",
            source_mode="generator_loop",
            intervention_class="source",
            metadata={"command_path": str(script_path), "timeout_seconds": "15"},
        ),
    )

    assert generated.edit_plan.operations[0].type == "write_file"
    assert generated.edit_plan.operations[0].path == "candidate.txt"
    assert "recovered_json_object_from_response_text" in generated.metadata["repair_steps"]
    assert "repaired_operations_payload" in generated.metadata["repair_steps"]


def test_codex_cli_generator_invokes_codex_exec(
    tmp_path: Path,
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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="screening",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={
            "benchmark_name": "proposal-smoke",
            "command": ["python", "-c", "print('ok')"],
        },
        target_root=target_root,
    )

    def fake_run(command, **kwargs):
        assert command[:2] == ["codex", "exec"]
        assert "--output-schema" in command
        assert "--output-last-message" in command
        assert "--sandbox" in command
        assert command[-1] == "-"
        prompt_text = kwargs["input"]
        assert "proposal_input.json" in prompt_text
        assert "service.py" not in prompt_text
        schema_path = Path(command[command.index("--output-schema") + 1])
        output_path = Path(command[command.index("--output-last-message") + 1])
        input_dir = schema_path.parent
        generator_input = json.loads(
            (input_dir / "proposal_input.json").read_text(encoding="utf-8")
        )
        assert generator_input["assistant"] == "codex"
        assert generator_input["context"]["workspace_id"] == "demo"
        output_path.write_text(
            json.dumps(
                {
                    "hypothesis": "Use Codex to refine routing",
                    "summary": "Codex CLI proposal",
                    "intervention_class": "source",
                    "operations": [
                        {
                            "type": "write_file",
                            "path": "candidate.txt",
                            "content": "codex\n",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "progress\n", "")

    monkeypatch.setattr(assistant_cli_generator.subprocess, "run", fake_run)

    generator = get_generator("codex_cli")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=8,
            strategy_id="beam_interventions",
            source_mode="generator_loop",
            intervention_class="source",
            metadata={"model": "gpt-5.5", "sandbox": "read-only"},
        ),
    )

    assert generated.generator_id == "codex_cli"
    assert generated.summary == "Codex CLI proposal"
    assert generated.hypothesis == "Use Codex to refine routing"
    assert generated.edit_plan.operations[0].path == "candidate.txt"
    assert generated.metadata["assistant_id"] == "codex"
    assert generated.metadata["provider"] == "codex_cli"
    assert generated.metadata["generator_input_payload"]["request"]["candidate_index"] == 8


def test_claude_code_generator_invokes_claude_print(
    tmp_path: Path,
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

    workspace = load_workspace(workspaces_root, "demo")
    state = load_workspace_state(workspaces_root, "demo")
    context = build_proposal_generation_context(
        root=workspaces_root,
        workspace=workspace,
        state=state,
        track_id="main",
        adapter_id="generic_command",
        stage="screening",
        benchmark_target="tau-bench-airline",
        selected_preset="search",
        selected_preset_source="policy",
        policy_preset="search",
        effective_track_policy={
            "search_benchmark": "tau-bench-airline",
            "search_preset": "search",
        },
        effective_config={
            "benchmark_name": "proposal-smoke",
            "command": ["python", "-c", "print('ok')"],
        },
        target_root=target_root,
    )

    def fake_run(command, **kwargs):
        assert command[0] == "claude"
        assert "--print" in command
        assert "--json-schema" in command
        assert "--permission-mode" in command
        schema_raw = command[command.index("--json-schema") + 1]
        schema = json.loads(schema_raw)
        assert schema["required"] == ["summary", "operations"]
        prompt_text = command[-1]
        assert "proposal_input.json" in prompt_text
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(
                {
                    "hypothesis": "Use Claude to tighten retries",
                    "summary": "Claude Code proposal",
                    "intervention_class": "config",
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
            "",
        )

    monkeypatch.setattr(assistant_cli_generator.subprocess, "run", fake_run)

    generator = get_generator("claude_code")
    generated = generator.generate(
        context=context,
        request=ProposalGenerationRequest(
            format_version="autoharness.proposal_generation_request.v1",
            candidate_index=9,
            strategy_id="beam_interventions",
            source_mode="generator_loop",
            intervention_class="config",
            metadata={"model": "sonnet", "effort": "high"},
        ),
    )

    assert generated.generator_id == "claude_code"
    assert generated.summary == "Claude Code proposal"
    assert generated.hypothesis == "Use Claude to tighten retries"
    assert generated.intervention_class == "config"
    assert generated.edit_plan.operations[0].type == "search_replace"
    assert generated.metadata["assistant_id"] == "claude"
    assert generated.metadata["provider"] == "claude_code"
