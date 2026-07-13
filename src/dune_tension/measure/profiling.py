from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WireMeasurementProfile:
    """Timing breakdown for one wire inside a list/auto batch run."""

    workflow: str
    wire_number: int
    started_at: float
    stage_seconds: dict[str, float] = field(default_factory=dict)

    def add(self, stage: str, elapsed: float) -> None:
        self.stage_seconds[stage] = self.stage_seconds.get(stage, 0.0) + max(
            0.0,
            float(elapsed),
        )

    @property
    def total_seconds(self) -> float:
        if "wire_total_wall" in self.stage_seconds:
            return max(0.0, float(self.stage_seconds["wire_total_wall"]))
        return max(0.0, float(sum(self.stage_seconds.values())))


@dataclass
class BatchMeasurementProfile:
    """Aggregate timing for a list/auto wire measurement batch."""

    workflow: str
    requested_wires: list[int]
    started_at: float
    planning_seconds: float = 0.0
    wire_profiles: list[WireMeasurementProfile] = field(default_factory=list)
    skipped_wires: list[int] = field(default_factory=list)

    def complete_wire(self, profile: WireMeasurementProfile | None) -> None:
        if profile is not None:
            self.wire_profiles.append(profile)

    @property
    def total_seconds(self) -> float:
        return max(
            0.0,
            float(
                sum(p.total_seconds for p in self.wire_profiles) + self.planning_seconds
            ),
        )
