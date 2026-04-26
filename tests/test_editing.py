from pathlib import Path

from autoharness.autonomy import policy_for_mode
from autoharness.editing import apply_edit_plan, edit_plan_from_dict, start_edit_session


def test_apply_edit_plan_applies_bounded_allowlisted_change(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODE = 'old'\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "format_version": "autoharness.edit_plan.v1",
            "summary": "Update one constant",
            "operations": [
                {
                    "type": "search_replace",
                    "path": "src/agent.py",
                    "search": "old",
                    "replace": "new",
                    "expected_count": 1,
                }
            ],
        }
    )

    result = apply_edit_plan(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("bounded", editable_surfaces=("src",)),
    )

    assert result.status == "applied"
    assert result.applied is True
    assert file_path.read_text(encoding="utf-8") == "MODE = 'new'\n"


def test_apply_edit_plan_downgrades_proposal_mode(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODE = 'old'\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "operations": [
                {
                    "type": "search_replace",
                    "path": "src/agent.py",
                    "search": "old",
                    "replace": "new",
                }
            ]
        }
    )

    result = apply_edit_plan(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("proposal"),
    )

    assert result.status == "proposal_only"
    assert result.applied is False
    assert file_path.read_text(encoding="utf-8") == "MODE = 'old'\n"


def test_apply_edit_plan_blocks_bounded_change_outside_allowlist(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODE = 'old'\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "operations": [
                {
                    "type": "search_replace",
                    "path": "src/agent.py",
                    "search": "old",
                    "replace": "new",
                }
            ]
        }
    )

    result = apply_edit_plan(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("bounded", editable_surfaces=("prompts",)),
    )

    assert result.status == "blocked"
    assert result.blocked is True
    assert file_path.read_text(encoding="utf-8") == "MODE = 'old'\n"


def test_apply_edit_plan_downgrades_protected_surface(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODE = 'old'\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "operations": [
                {
                    "type": "search_replace",
                    "path": "src/agent.py",
                    "search": "old",
                    "replace": "new",
                }
            ]
        }
    )

    result = apply_edit_plan(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("full", protected_surfaces=("src",)),
    )

    assert result.status == "proposal_only"
    assert result.proposal_only is True
    assert file_path.read_text(encoding="utf-8") == "MODE = 'old'\n"


def test_start_edit_session_can_revert_to_original_contents(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODE = 'old'\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "operations": [
                {
                    "type": "search_replace",
                    "path": "src/agent.py",
                    "search": "old",
                    "replace": "new",
                }
            ]
        }
    )

    session = start_edit_session(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("full"),
    )
    assert session.application.status == "applied"
    assert file_path.read_text(encoding="utf-8") == "MODE = 'new'\n"

    restore = session.finalize()
    assert restore.status == "reverted"
    assert file_path.read_text(encoding="utf-8") == "MODE = 'old'\n"


def test_start_edit_session_renders_unified_diff(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODE = 'old'\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "operations": [
                {
                    "type": "search_replace",
                    "path": "src/agent.py",
                    "search": "old",
                    "replace": "new",
                }
            ]
        }
    )

    session = start_edit_session(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("full"),
    )
    diff_text = session.render_unified_diff()
    session.finalize()

    assert "--- a/src/agent.py" in diff_text
    assert "+++ b/src/agent.py" in diff_text
    assert "-MODE = 'old'" in diff_text
    assert "+MODE = 'new'" in diff_text


def test_start_edit_session_supports_ordered_multi_step_updates(
    tmp_path: Path,
) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODE = 'old'\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "operations": [
                {
                    "type": "search_replace",
                    "path": "src/agent.py",
                    "search": "old",
                    "replace": "mid",
                },
                {
                    "type": "search_replace",
                    "path": "src/agent.py",
                    "search": "mid",
                    "replace": "new",
                },
            ]
        }
    )

    session = start_edit_session(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("full"),
    )

    assert session.application.status == "applied"
    assert file_path.read_text(encoding="utf-8") == "MODE = 'new'\n"
    session.finalize()


def test_apply_edit_plan_rejects_path_escape(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    plan = edit_plan_from_dict(
        {
            "operations": [
                {
                    "type": "write_file",
                    "path": "../escape.txt",
                    "content": "bad",
                }
            ]
        }
    )

    try:
        apply_edit_plan(
            plan=plan,
            target_root=target_root,
            policy=policy_for_mode("full"),
        )
    except ValueError as exc:
        assert "escapes target root" in str(exc)
    else:
        raise AssertionError("Expected ValueError for path escape")


def test_apply_edit_plan_supports_delete_file_in_v2(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "obsolete.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("print('old')\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "format_version": "autoharness.edit_plan.v2",
            "operations": [
                {
                    "type": "delete_file",
                    "path": "src/obsolete.py",
                }
            ],
        }
    )

    session = start_edit_session(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("full"),
    )

    assert session.application.status == "applied"
    assert file_path.exists() is False
    restore = session.finalize()
    assert restore.status == "reverted"
    assert file_path.read_text(encoding="utf-8") == "print('old')\n"


def test_apply_edit_plan_supports_move_path_in_v2(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    source_path = target_root / "src" / "old_name.py"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("VALUE = 1\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "format_version": "autoharness.edit_plan.v2",
            "operations": [
                {
                    "type": "move_path",
                    "path": "src/old_name.py",
                    "dest_path": "src/new_name.py",
                }
            ],
        }
    )

    session = start_edit_session(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("full"),
    )

    assert session.application.status == "applied"
    assert source_path.exists() is False
    assert (target_root / "src" / "new_name.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    session.finalize()
    assert source_path.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (target_root / "src" / "new_name.py").exists() is False


def test_apply_edit_plan_supports_unified_diff_in_v2(tmp_path: Path) -> None:
    target_root = tmp_path / "target"
    target_root.mkdir()
    file_path = target_root / "src" / "agent.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("MODE = 'old'\n", encoding="utf-8")

    plan = edit_plan_from_dict(
        {
            "format_version": "autoharness.edit_plan.v2",
            "operations": [
                {
                    "type": "unified_diff",
                    "path": "src/agent.py",
                    "diff": (
                        "--- a/src/agent.py\n"
                        "+++ b/src/agent.py\n"
                        "@@ -1 +1 @@\n"
                        "-MODE = 'old'\n"
                        "+MODE = 'new'\n"
                    ),
                }
            ],
        }
    )

    result = apply_edit_plan(
        plan=plan,
        target_root=target_root,
        policy=policy_for_mode("full"),
    )

    assert result.status == "applied"
    assert file_path.read_text(encoding="utf-8") == "MODE = 'new'\n"
