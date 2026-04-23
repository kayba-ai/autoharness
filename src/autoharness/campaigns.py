"""Campaign-scoped comparability primitives."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class CampaignEvaluatorPolicy:
    """Pinned evaluator policy for one comparable campaign."""

    evaluator_version: str
    judge_model: str
    diagnostic_model: str
    max_diagnostic_tasks: int = 8
    min_judge_pass_rate: float = 0.55

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CampaignEvaluatorPolicy":
        return cls(
            evaluator_version=str(data["evaluator_version"]),
            judge_model=str(data["judge_model"]),
            diagnostic_model=str(data["diagnostic_model"]),
            max_diagnostic_tasks=int(data.get("max_diagnostic_tasks", 8)),
            min_judge_pass_rate=float(data.get("min_judge_pass_rate", 0.55)),
        )


@dataclass(frozen=True)
class TrackConfig:
    """One benchmark-scoped track inside a workspace."""

    track_id: str
    benchmark: str
    objective: str
    campaign_id: str
    status: str = "active"
    kind: str = "search"
    benchmark_reference_ids: tuple[str, ...] = ()
    notes: str = ""
    campaign_policy: dict[str, object] = field(default_factory=dict)
    evaluator: CampaignEvaluatorPolicy = field(
        default_factory=lambda: CampaignEvaluatorPolicy(
            evaluator_version="dev",
            judge_model="unset",
            diagnostic_model="unset",
        )
    )

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["evaluator"] = self.evaluator.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "TrackConfig":
        evaluator_data = data.get("evaluator", {})
        if not isinstance(evaluator_data, dict):
            raise ValueError("`evaluator` must be a mapping in TrackConfig.")
        campaign_policy_data = data.get("campaign_policy", {})
        if not isinstance(campaign_policy_data, dict):
            raise ValueError("`campaign_policy` must be a mapping in TrackConfig.")
        return cls(
            track_id=str(data["track_id"]),
            benchmark=str(data["benchmark"]),
            objective=str(data["objective"]),
            campaign_id=str(data["campaign_id"]),
            status=str(data.get("status", "active")),
            kind=str(data.get("kind", "search")),
            benchmark_reference_ids=tuple(data.get("benchmark_reference_ids", ())),
            notes=str(data.get("notes", "")),
            campaign_policy=dict(campaign_policy_data),
            evaluator=CampaignEvaluatorPolicy.from_dict(evaluator_data),
        )


@dataclass(frozen=True)
class PromotionPolicy:
    """Pinned promotion policy for one track."""

    format_version: str
    created_at: str
    track_id: str
    stage: str | None = None
    min_success_rate: float | None = None
    min_improvement: float | None = 0.0
    max_regressed_tasks: int | None = None
    max_regressed_task_fraction: float | None = None
    max_regressed_task_weight: float | None = None
    max_regressed_task_weight_fraction: float | None = None
    task_regression_margin: float | None = 0.0
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "PromotionPolicy":
        return cls(
            format_version=str(data["format_version"]),
            created_at=str(data["created_at"]),
            track_id=str(data["track_id"]),
            stage=str(data["stage"]) if data.get("stage") is not None else None,
            min_success_rate=(
                float(data["min_success_rate"])
                if data.get("min_success_rate") is not None
                else None
            ),
            min_improvement=(
                float(data["min_improvement"])
                if data.get("min_improvement") is not None
                else None
            ),
            max_regressed_tasks=(
                int(data["max_regressed_tasks"])
                if data.get("max_regressed_tasks") is not None
                else None
            ),
            max_regressed_task_fraction=(
                float(data["max_regressed_task_fraction"])
                if data.get("max_regressed_task_fraction") is not None
                else None
            ),
            max_regressed_task_weight=(
                float(data["max_regressed_task_weight"])
                if data.get("max_regressed_task_weight") is not None
                else None
            ),
            max_regressed_task_weight_fraction=(
                float(data["max_regressed_task_weight_fraction"])
                if data.get("max_regressed_task_weight_fraction") is not None
                else None
            ),
            task_regression_margin=(
                float(data["task_regression_margin"])
                if data.get("task_regression_margin") is not None
                else None
            ),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class TrackBenchmarkPolicy:
    """Pinned benchmark routing policy for one track."""

    format_version: str
    created_at: str
    track_id: str
    search_benchmark: str
    promotion_benchmark: str
    regression_benchmark: str
    search_preset: str | None = None
    promotion_preset: str | None = None
    regression_preset: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "TrackBenchmarkPolicy":
        return cls(
            format_version=str(data["format_version"]),
            created_at=str(data["created_at"]),
            track_id=str(data["track_id"]),
            search_benchmark=str(data["search_benchmark"]),
            promotion_benchmark=str(data["promotion_benchmark"]),
            regression_benchmark=str(data["regression_benchmark"]),
            search_preset=(
                str(data["search_preset"])
                if data.get("search_preset") is not None
                else None
            ),
            promotion_preset=(
                str(data["promotion_preset"])
                if data.get("promotion_preset") is not None
                else None
            ),
            regression_preset=(
                str(data["regression_preset"])
                if data.get("regression_preset") is not None
                else None
            ),
            notes=str(data.get("notes", "")),
        )
