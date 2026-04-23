"""Adapter registry for autoharness."""

from __future__ import annotations

from .base import BenchmarkAdapter
from .car_bench import CARBenchAdapter
from .generic_command import GenericCommandAdapter
from .hal import HALAdapter
from .harbor import HarborAdapter
from .pytest_adapter import PytestAdapter
from .tau2_bench import Tau2BenchAdapter


_ADAPTERS: dict[str, BenchmarkAdapter] = {
    "car_bench": CARBenchAdapter(),
    "generic_command": GenericCommandAdapter(),
    "harbor": HarborAdapter(),
    "pytest": PytestAdapter(),
    "tau2_bench": Tau2BenchAdapter(),
    "hal": HALAdapter(),
}


def get_adapter(adapter_id: str) -> BenchmarkAdapter:
    """Return one registered benchmark adapter."""
    try:
        return _ADAPTERS[adapter_id]
    except KeyError as exc:
        raise KeyError(f"Unknown adapter id: {adapter_id}") from exc


def list_adapters() -> tuple[BenchmarkAdapter, ...]:
    """Return all registered adapter instances."""
    return tuple(_ADAPTERS.values())


def implemented_adapter_ids() -> tuple[str, ...]:
    """Return the adapter ids backed by concrete implementations."""
    return tuple(_ADAPTERS.keys())
