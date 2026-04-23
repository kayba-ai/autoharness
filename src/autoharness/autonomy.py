"""Autonomy policy definitions for the public autoharness agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal


AutonomyMode = Literal["proposal", "bounded", "full"]


@dataclass(frozen=True)
class AutonomyPolicy:
    """Defines how much authority the meta-agent gets over a target harness."""

    mode: AutonomyMode
    label: str
    description: str
    may_generate_proposals: bool = True
    may_apply_patches: bool = False
    may_execute_commands: bool = True
    requires_explicit_edit_allowlist: bool = False
    allows_repo_wide_edits: bool = False
    protected_surfaces_proposal_only: bool = True
    editable_surfaces: tuple[str, ...] = field(default_factory=tuple)
    protected_surfaces: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def policy_for_mode(
    mode: AutonomyMode,
    *,
    editable_surfaces: tuple[str, ...] = (),
    protected_surfaces: tuple[str, ...] = (),
) -> AutonomyPolicy:
    """Build the default policy for one autonomy mode."""
    if mode == "proposal":
        return AutonomyPolicy(
            mode=mode,
            label="Proposal First",
            description=(
                "Analyze the harness, draft interventions, and emit patch proposals "
                "without applying them."
            ),
            may_apply_patches=False,
            requires_explicit_edit_allowlist=False,
            allows_repo_wide_edits=False,
            editable_surfaces=editable_surfaces,
            protected_surfaces=protected_surfaces,
        )

    if mode == "bounded":
        return AutonomyPolicy(
            mode=mode,
            label="Bounded Autopatch",
            description=(
                "Apply edits inside approved editable surfaces only. Protected "
                "surfaces stay proposal-only."
            ),
            may_apply_patches=True,
            requires_explicit_edit_allowlist=True,
            allows_repo_wide_edits=False,
            editable_surfaces=editable_surfaces,
            protected_surfaces=protected_surfaces,
        )

    if mode == "full":
        return AutonomyPolicy(
            mode=mode,
            label="Full Harness Optimizer",
            description=(
                "Apply edits across the harness, except for explicitly protected "
                "surfaces."
            ),
            may_apply_patches=True,
            requires_explicit_edit_allowlist=False,
            allows_repo_wide_edits=True,
            editable_surfaces=editable_surfaces,
            protected_surfaces=protected_surfaces,
        )

    raise ValueError(f"Unsupported autonomy mode: {mode}")
