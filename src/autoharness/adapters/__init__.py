"""Benchmark adapter implementations for autoharness."""

from .base import (
    AdapterCapabilityProfile,
    AdapterStagingSignal,
    AdapterStagingProfile,
    BenchmarkAdapter,
    BenchmarkInvocation,
    BenchmarkRunResult,
    TaskIdentityProfile,
)
from .registry import get_adapter, implemented_adapter_ids, list_adapters

__all__ = [
    "AdapterCapabilityProfile",
    "AdapterStagingProfile",
    "AdapterStagingSignal",
    "BenchmarkAdapter",
    "BenchmarkInvocation",
    "BenchmarkRunResult",
    "TaskIdentityProfile",
    "get_adapter",
    "implemented_adapter_ids",
    "list_adapters",
]
