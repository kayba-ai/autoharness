"""Structured intervention types for the public autoharness loop."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Literal


TargetClass = Literal["harness_internal", "runtime", "mixed"]
RuntimeAction = Literal["catch", "enable"]
OptimizationLevel = Literal["l1", "l2", "l3", "l4"]


@dataclass(frozen=True)
class Intervention:
    """One explicit optimization hypothesis."""

    intervention_id: str
    kind: str
    target: str
    summary: str
    target_class: TargetClass = "harness_internal"
    runtime_action: RuntimeAction | None = None
    optimization_level: OptimizationLevel = "l1"
    requires_code_edit: bool = False
    params: MappingProxyType[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["params"] = dict(self.params)
        return data


def intervention_from_dict(data: dict[str, Any]) -> Intervention:
    return Intervention(
        intervention_id=data["intervention_id"],
        kind=data["kind"],
        target=data["target"],
        summary=data["summary"],
        target_class=data.get("target_class", "harness_internal"),
        runtime_action=data.get("runtime_action"),
        optimization_level=data.get("optimization_level", "l1"),
        requires_code_edit=data.get("requires_code_edit", False),
        params=MappingProxyType(dict(data.get("params", {}))),
    )
