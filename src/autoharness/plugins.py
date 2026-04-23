"""Plugin discovery and contribution loading for extensible registries."""

from __future__ import annotations

import importlib.util
import os
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any


_PLUGIN_API_VERSION = "autoharness.plugin.v1"
_CONTRIBUTION_KINDS = ("generators", "preflight_checks", "search_strategies")


def _candidate_plugin_paths() -> list[Path]:
    candidates: list[Path] = []
    env_paths = os.environ.get("AUTOHARNESS_PLUGIN_PATHS", "")
    for raw_path in env_paths.split(os.pathsep):
        if raw_path.strip():
            candidates.append(Path(raw_path.strip()))
    cwd_plugin_dir = Path.cwd() / ".autoharness" / "plugins"
    candidates.append(cwd_plugin_dir)
    return candidates


def _expand_plugin_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists() or not path.is_dir():
        return []
    return sorted(path.glob("*.py"))


def _load_plugin_module(path: Path) -> ModuleType:
    module_name = f"autoharness_plugin_{path.stem}_{abs(hash(path.resolve()))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Unable to load plugin module spec for {path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plugin_metadata(module: ModuleType) -> dict[str, Any]:
    raw = getattr(module, "PLUGIN_INFO", None)
    if raw is None:
        raise ValueError("Missing required `PLUGIN_INFO` metadata.")
    if not isinstance(raw, dict):
        raise ValueError("`PLUGIN_INFO` must be a mapping.")
    api_version = raw.get("api_version")
    if api_version != _PLUGIN_API_VERSION:
        raise ValueError(
            f"Unsupported plugin api_version `{api_version}`; expected `{_PLUGIN_API_VERSION}`."
        )
    if raw.get("enabled") is not True:
        raise ValueError("Plugin must set `PLUGIN_INFO.enabled = True` to be loaded.")
    return dict(raw)


def _call_plugin_registration(
    module: ModuleType,
    *,
    attribute: str,
) -> dict[str, dict[str, object]]:
    register = getattr(module, attribute, None)
    if register is None:
        return {}
    if not callable(register):
        raise ValueError(f"`{attribute}` must be callable when present.")
    payload = register()
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError(f"`{attribute}` must return a mapping.")
    rendered: dict[str, dict[str, object]] = {}
    for key, entry in payload.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"`{attribute}` returned an invalid contribution id.")
        if not isinstance(entry, dict):
            raise ValueError(
                f"`{attribute}` contribution `{key}` must be a mapping."
            )
        rendered[key] = dict(entry)
    return rendered


def _validate_generator_entry(generator_id: str, entry: dict[str, object]) -> None:
    generator = entry.get("generator")
    if generator is None or not hasattr(generator, "generate"):
        raise ValueError(
            f"Generator contribution `{generator_id}` requires a `generator` object with `generate()`."
        )
    catalog_entry = entry.get("catalog")
    if catalog_entry is not None and not isinstance(catalog_entry, dict):
        raise ValueError(f"Generator contribution `{generator_id}` has invalid `catalog` data.")


def _validate_preflight_entry(check_id: str, entry: dict[str, object]) -> None:
    command = entry.get("command")
    argv = entry.get("argv")
    if not (
        (isinstance(command, str) and command.strip())
        or (isinstance(argv, list) and len(argv) > 0)
    ):
        raise ValueError(
            f"Preflight contribution `{check_id}` requires `command` or `argv`."
        )
    for field_name in ("default_stages", "recommended_adapters"):
        value = entry.get(field_name)
        if value is not None and not isinstance(value, list):
            raise ValueError(
                f"Preflight contribution `{check_id}` field `{field_name}` must be a list."
            )


def _validate_search_strategy_entry(strategy_id: str, entry: dict[str, object]) -> None:
    hook = entry.get("hook")
    inherits = entry.get("inherits")
    hook_fields = (
        "resolve_intervention_class",
        "resolve_focus_task_ids",
        "rank_beam_candidate",
        "compute_candidate_branch_score",
        "resolve_next_stage",
    )
    if hook is not None and (not isinstance(hook, str) or not hook.strip()):
        raise ValueError(f"Search strategy `{strategy_id}` has invalid `hook`.")
    if inherits is not None and (not isinstance(inherits, str) or not inherits.strip()):
        raise ValueError(f"Search strategy `{strategy_id}` has invalid `inherits`.")
    if hook is None and inherits is None and not any(
        callable(entry.get(field_name)) for field_name in hook_fields
    ):
        raise ValueError(
            f"Search strategy `{strategy_id}` must declare `hook`, `inherits`, or runtime hook callables."
        )
    for field_name in hook_fields:
        value = entry.get(field_name)
        if value is not None and not callable(value):
            raise ValueError(
                f"Search strategy `{strategy_id}` field `{field_name}` must be callable."
            )


def _serializable_search_entry(entry: dict[str, object]) -> dict[str, object]:
    rendered: dict[str, object] = {}
    for key, value in entry.items():
        if callable(value):
            rendered[key] = f"<callable:{getattr(value, '__name__', 'anonymous')}>"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            rendered[key] = value
        elif isinstance(value, list):
            rendered[key] = list(value)
        elif isinstance(value, dict):
            rendered[key] = dict(value)
    return rendered


@lru_cache(maxsize=1)
def load_plugin_catalog() -> dict[str, object]:
    plugin_entries: list[dict[str, object]] = []
    generators: dict[str, dict[str, object]] = {}
    preflight_checks: dict[str, dict[str, object]] = {}
    search_strategies: dict[str, dict[str, object]] = {}
    load_failures: list[dict[str, object]] = []

    for candidate in _candidate_plugin_paths():
        for plugin_file in _expand_plugin_files(candidate):
            plugin_entry: dict[str, object] = {
                "path": str(plugin_file.resolve()),
                "module": None,
                "name": plugin_file.stem,
                "api_version": None,
                "status": "failed",
                "generator_ids": [],
                "preflight_check_ids": [],
                "search_strategy_ids": [],
                "errors": [],
            }
            try:
                module = _load_plugin_module(plugin_file)
                metadata = _plugin_metadata(module)
                plugin_entry["module"] = module.__name__
                plugin_entry["name"] = str(metadata.get("name") or plugin_file.stem)
                plugin_entry["api_version"] = metadata.get("api_version")
                plugin_entry["description"] = metadata.get("description")
                plugin_entry["status"] = "loaded"

                generator_payload = _call_plugin_registration(
                    module,
                    attribute="register_generators",
                )
                for generator_id, entry in generator_payload.items():
                    _validate_generator_entry(generator_id, entry)
                    generators[generator_id] = dict(entry)
                    plugin_entry["generator_ids"].append(generator_id)

                preflight_payload = _call_plugin_registration(
                    module,
                    attribute="register_preflight_checks",
                )
                for check_id, entry in preflight_payload.items():
                    _validate_preflight_entry(check_id, entry)
                    preflight_checks[check_id] = dict(entry)
                    plugin_entry["preflight_check_ids"].append(check_id)

                search_payload = _call_plugin_registration(
                    module,
                    attribute="register_search_strategies",
                )
                for strategy_id, entry in search_payload.items():
                    _validate_search_strategy_entry(strategy_id, entry)
                    search_strategies[strategy_id] = dict(entry)
                    plugin_entry["search_strategy_ids"].append(strategy_id)
            except Exception as exc:  # pragma: no cover - exercised by integration tests
                plugin_entry["errors"] = [str(exc)]
                load_failures.append(
                    {
                        "path": str(plugin_file.resolve()),
                        "error": str(exc),
                    }
                )
            plugin_entries.append(plugin_entry)

    return {
        "plugins": plugin_entries,
        "generators": generators,
        "preflight_checks": preflight_checks,
        "search_strategies": search_strategies,
        "load_failures": load_failures,
    }


def plugin_catalog_entries() -> list[dict[str, object]]:
    catalog = load_plugin_catalog()
    plugins = catalog.get("plugins", [])
    return [entry for entry in plugins if isinstance(entry, dict)]


def plugin_load_failures() -> list[dict[str, object]]:
    catalog = load_plugin_catalog()
    failures = catalog.get("load_failures", [])
    return [entry for entry in failures if isinstance(entry, dict)]


def plugin_generators() -> dict[str, dict[str, object]]:
    catalog = load_plugin_catalog()
    payload = catalog.get("generators", {})
    return dict(payload) if isinstance(payload, dict) else {}


def plugin_preflight_checks() -> dict[str, dict[str, object]]:
    catalog = load_plugin_catalog()
    payload = catalog.get("preflight_checks", {})
    return dict(payload) if isinstance(payload, dict) else {}


def plugin_search_strategies() -> dict[str, dict[str, object]]:
    catalog = load_plugin_catalog()
    payload = catalog.get("search_strategies", {})
    return dict(payload) if isinstance(payload, dict) else {}


def plugin_runtime_contract_summary() -> dict[str, dict[str, object]]:
    rendered: dict[str, dict[str, object]] = {}
    for strategy_id, entry in plugin_search_strategies().items():
        rendered[strategy_id] = _serializable_search_entry(entry)
    return rendered
