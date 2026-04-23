from pathlib import Path

import pytest
import yaml

from autoharness.workspace_handlers import _load_settings


def test_load_settings_reads_valid_settings_file(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        yaml.safe_dump(
            {
                "format_version": "autoharness.settings.v1",
                "autonomy": {
                    "mode": "full",
                    "editable_surfaces": ["src"],
                    "protected_surfaces": ["prod"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert _load_settings(settings_path) == {
        "format_version": "autoharness.settings.v1",
        "autonomy": {
            "mode": "full",
            "editable_surfaces": ["src"],
            "protected_surfaces": ["prod"],
        },
    }


def test_load_settings_rejects_missing_autonomy_block(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text("format_version: autoharness.settings.v1\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="Invalid settings file"):
        _load_settings(settings_path)
