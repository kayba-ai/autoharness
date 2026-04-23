from pathlib import Path

from autoharness import AdapterStagingSignal, get_adapter
from autoharness.staging import create_copy_stage, rewrite_config_for_stage
from autoharness.staging import resolve_staging_decision


def test_create_copy_stage_copies_source_tree(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    file_path = source_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("STATE = 'old'\n", encoding="utf-8")

    staged_root = tmp_path / "stage"
    context = create_copy_stage(source_root=source_root, staged_root=staged_root)

    assert context.mode == "copy"
    assert (staged_root / "src" / "agent.py").read_text(encoding="utf-8") == "STATE = 'old'\n"


def test_rewrite_config_for_stage_rewrites_paths_and_injects_env(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    staged_root = tmp_path / "stage"
    staged_root.mkdir()

    config = {
        "workdir": str(source_root),
        "env": {"HARNESS_ROOT": str(source_root)},
        "nested": {"path": str(source_root / "src")},
        "command": ["python", "-c", "print('ok')"],
    }
    rewritten, context = rewrite_config_for_stage(
        config=config,
        source_root=source_root,
        staged_root=staged_root,
        default_workdir=True,
    )

    assert rewritten["workdir"] == str(staged_root.resolve())
    assert rewritten["env"]["HARNESS_ROOT"] == str(staged_root.resolve())
    assert rewritten["env"]["AUTOHARNESS_TARGET_ROOT"] == str(staged_root.resolve())
    assert rewritten["nested"]["path"] == str((staged_root / "src").resolve())
    assert context.path_rewrite_count >= 2


def test_rewrite_config_for_stage_absolutizes_relative_path_fields(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    staged_root = tmp_path / "stage"
    staged_root.mkdir()

    config = {
        "agent_dir": "agents/demo_agent",
        "targets": ["tests/test_app.py"],
    }
    rewritten, _ = rewrite_config_for_stage(
        config=config,
        source_root=source_root,
        staged_root=staged_root,
        relative_path_fields=("agent_dir", "targets"),
    )

    assert rewritten["agent_dir"] == str((staged_root / "agents/demo_agent").resolve())
    assert rewritten["targets"] == [
        str((staged_root / "tests/test_app.py").resolve())
    ]


def test_resolve_staging_decision_uses_adapter_defaults_for_auto(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    decision = resolve_staging_decision(
        profile=get_adapter("generic_command").staging_profile(),
        requested_mode="auto",
        config={"command": ["python", "-c", "print('ok')"]},
        source_root=target_root,
    )
    assert decision.resolved_mode == "copy"
    assert decision.default_workdir is True


def test_resolve_staging_decision_stays_off_without_adapter_signal(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    decision = resolve_staging_decision(
        profile=get_adapter("tau2_bench").staging_profile(),
        requested_mode="auto",
        config={"domain": "airline"},
        source_root=target_root,
    )
    assert decision.resolved_mode == "off"


def test_resolve_staging_decision_uses_relative_path_hint_for_hal(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    decision = resolve_staging_decision(
        profile=get_adapter("hal").staging_profile(),
        requested_mode="auto",
        config={
            "benchmark": "taubench_airline",
            "agent_dir": "agents/demo_agent",
            "agent_function": "main.run",
            "agent_name": "Demo Agent",
        },
        source_root=target_root,
    )
    assert decision.resolved_mode == "copy"
    assert decision.default_workdir is True


def test_resolve_staging_decision_uses_adapter_specific_signal(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    decision = resolve_staging_decision(
        profile=get_adapter("tau2_bench").staging_profile(),
        requested_mode="auto",
        config={"domain": "airline"},
        source_root=target_root,
        adapter_signal=AdapterStagingSignal(
            reason="Nested adapter config points at the target harness.",
        ),
    )
    assert decision.resolved_mode == "copy"
    assert decision.reason == "Nested adapter config points at the target harness."
