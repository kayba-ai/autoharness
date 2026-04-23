"""Benchmark adapter catalog for autoharness."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


BenchmarkKind = Literal["generic", "agent", "coding", "tool_use"]
SupportLevel = Literal["planned", "candidate", "recommended_v1", "defer"]


@dataclass(frozen=True)
class BenchmarkAdapterSpec:
    """Describes one benchmark family autoharness can target."""

    adapter_id: str
    label: str
    kind: BenchmarkKind
    support_level: SupportLevel
    source: str
    why_it_matters: str
    strengths: tuple[str, ...] = field(default_factory=tuple)
    risks: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def benchmark_catalog() -> tuple[BenchmarkAdapterSpec, ...]:
    """Return the built-in benchmark adapter catalog."""

    return (
        BenchmarkAdapterSpec(
            adapter_id="generic_command",
            label="Generic Command Adapter",
            kind="generic",
            support_level="recommended_v1",
            source="local",
            why_it_matters=(
                "Lets autoharness optimize arbitrary repos that expose a stable "
                "evaluation command, without taking a dependency on a specific "
                "benchmark framework."
            ),
            strengths=(
                "Lowest integration cost",
                "Useful for internal repos and pilots",
                "Works before benchmark-specific adapters exist",
            ),
            risks=(
                "Weak comparability unless users pin commands and artifacts carefully",
            ),
            notes=(
                "This should be the first adapter because it unlocks real harness "
                "optimization immediately."
            ),
        ),
        BenchmarkAdapterSpec(
            adapter_id="pytest",
            label="Pytest Adapter",
            kind="generic",
            support_level="recommended_v1",
            source="local",
            why_it_matters=(
                "A large share of coding-agent harnesses already evaluate through "
                "pytest or a thin wrapper around it."
            ),
            strengths=(
                "Simple execution model",
                "Fast inner loop",
                "Natural fit for direct harness edits",
            ),
            risks=(
                "Can incentivize benchmark-local hacks if tests are too narrow",
            ),
            notes=(
                "Treat this as the default local coding harness adapter, not as a "
                "public leaderboard benchmark."
            ),
        ),
        BenchmarkAdapterSpec(
            adapter_id="harbor",
            label="Harbor",
            kind="coding",
            support_level="recommended_v1",
            source="https://harborframework.com/docs/adapters",
            why_it_matters=(
                "Harbor already provides an adapter model for benchmark datasets and "
                "is a natural bridge into coding-agent evaluation without baking "
                "benchmark-specific logic into autoharness."
            ),
            strengths=(
                "Adapter ecosystem",
                "Good fit for command-line coding tasks",
                "Lets autoharness piggyback on benchmark translations",
            ),
            risks=(
                "Adds another framework dependency",
                "You inherit Harbor semantics and adapter quality",
            ),
            notes=(
                "Recommended as a direct coding benchmark integration alongside HAL, "
                "not instead of HAL."
            ),
        ),
        BenchmarkAdapterSpec(
            adapter_id="tau2_bench",
            label="Tau2 / Tau-Bench",
            kind="agent",
            support_level="recommended_v1",
            source="https://sierra.ai/resources/research/tau-squared-bench",
            why_it_matters=(
                "Strong fit for direct harness optimization over tool-using agents, "
                "with multi-turn interaction and measurable pass-rate outcomes."
            ),
            strengths=(
                "Good fit for multi-turn agent regression checks",
                "Good search benchmark for fast regression checks",
                "Task-oriented harness optimization rather than patch generation",
            ),
            risks=(
                "Provider costs and simulation variance",
                "Requires pinned seeds and evaluator policy for comparability",
            ),
            notes=(
                "This is the best first benchmark-specific agent adapter."
            ),
        ),
        BenchmarkAdapterSpec(
            adapter_id="hal",
            label="HAL Harness",
            kind="generic",
            support_level="recommended_v1",
            source="https://github.com/princeton-pli/hal-harness",
            why_it_matters=(
                "HAL is a unified evaluation harness spanning multiple agent "
                "benchmarks, including tau-bench and AppWorld, with local, Docker, "
                "and cloud execution plus cost and trace logging."
            ),
            strengths=(
                "Unified multi-benchmark CLI",
                "Cloud and parallel execution",
                "Weave logging and cost tracking",
                "Useful bridge to several public benchmarks",
            ),
            risks=(
                "It is a harness-of-harnesses rather than a single benchmark",
                "Adds conda, submodule, and optional Azure complexity",
                "Can overlap with autoharness responsibilities if used as the primary control plane",
            ),
            notes=(
                "Treat HAL as a recommended v1 execution backend for benchmark "
                "breadth, but not as the source of autoharness campaign policy or "
                "experiment memory."
            ),
        ),
        BenchmarkAdapterSpec(
            adapter_id="car_bench",
            label="CAR-bench",
            kind="agent",
            support_level="candidate",
            source="local/CAR-bench",
            why_it_matters=(
                "Good promotion benchmark for harder, ambiguity-heavy, policy-heavy "
                "agent tasks."
            ),
            strengths=(
                "More realism and uncertainty than simple task benchmarks",
                "Good transfer/generalization check after Tau-oriented search",
            ),
            risks=(
                "Heavier environment",
                "More expensive and slower than a search-track benchmark",
            ),
            notes=(
                "Valuable, but not the first adapter to implement in the public repo."
            ),
        ),
        BenchmarkAdapterSpec(
            adapter_id="appworld",
            label="AppWorld",
            kind="tool_use",
            support_level="candidate",
            source="https://github.com/StonyBrookNLP/appworld-leaderboard",
            why_it_matters=(
                "Useful later if autoharness wants a stronger tool-use and "
                "interactive coding benchmark beyond Tau-style workflows."
            ),
            strengths=(
                "Richer app interactions",
                "Interesting for general tool-use agents",
            ),
            risks=(
                "Higher integration complexity",
                "Not the shortest path to a strong v1",
            ),
        ),
        BenchmarkAdapterSpec(
            adapter_id="swe_bench_verified",
            label="SWE-bench Verified",
            kind="coding",
            support_level="defer",
            source="https://github.com/SWE-bench/SWE-bench",
            why_it_matters=(
                "Important as an ecosystem benchmark, but it is not the best first "
                "adapter for a harness optimizer focused on fast, repeated outer-loop "
                "search."
            ),
            strengths=(
                "Recognized benchmark",
                "Clear software-engineering framing",
            ),
            risks=(
                "Heavy runtime",
                "Slow feedback cycle",
                "Less suitable for frequent one-hypothesis outer-loop iteration",
            ),
            notes=(
                "Use later, or via Harbor-style bridge if that ecosystem matures "
                "around it."
            ),
        ),
    )


def recommended_v1_adapter_ids() -> tuple[str, ...]:
    """Return the adapter ids that make the most sense for v1 implementation."""
    return tuple(
        spec.adapter_id
        for spec in benchmark_catalog()
        if spec.support_level == "recommended_v1"
    )


def benchmark_catalog_entry(adapter_id: str) -> BenchmarkAdapterSpec:
    """Return one built-in benchmark adapter spec by id."""
    for spec in benchmark_catalog():
        if spec.adapter_id == adapter_id:
            return spec
    raise KeyError(f"Unknown benchmark adapter id: {adapter_id}")
