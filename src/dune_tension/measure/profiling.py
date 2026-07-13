from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

LOGGER = logging.getLogger(__name__)


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


class MeasurementProfiler:
    """Owns per-batch/per-wire timing state for a measurement run.

    Carved out of ``Tensiometer``; the engine keeps thin delegating methods so
    call sites (and tests reaching ``_record_wire_stage`` / ``_active_wire_profile``)
    are unaffected. ``profile_time`` is the monotonic clock used to stamp starts.
    """

    def __init__(self, profile_time: Callable[[], float]) -> None:
        self._profile_time = profile_time
        self.active_batch: BatchMeasurementProfile | None = None
        self.active_wire: WireMeasurementProfile | None = None

    def start_batch(
        self,
        *,
        workflow: str,
        requested_wires: list[int],
    ) -> BatchMeasurementProfile:
        profile = BatchMeasurementProfile(
            workflow=workflow,
            requested_wires=list(map(int, requested_wires)),
            started_at=self._profile_time(),
        )
        self.active_batch = profile
        LOGGER.info(
            "Timing profile started for %s measurement of %s wire(s): %s",
            workflow,
            len(profile.requested_wires),
            profile.requested_wires,
        )
        return profile

    def finish_batch(self) -> None:
        profile = self.active_batch
        self.active_batch = None
        self.active_wire = None
        if profile is None:
            return
        measured_wires = len(profile.wire_profiles)
        total_wire_seconds = sum(p.total_seconds for p in profile.wire_profiles)
        avg_wire_seconds = (
            total_wire_seconds / measured_wires if measured_wires else 0.0
        )
        aggregate_stages: dict[str, float] = {}
        for wire_profile in profile.wire_profiles:
            for stage, elapsed in wire_profile.stage_seconds.items():
                aggregate_stages[stage] = aggregate_stages.get(stage, 0.0) + elapsed
        stage_summary = (
            ", ".join(
                f"{stage}={elapsed:.2f}s"
                for stage, elapsed in sorted(
                    aggregate_stages.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )
            or "none"
        )
        LOGGER.info(
            "Timing profile summary for %s measurement: requested=%s measured=%s skipped=%s planning=%.2fs avg_wire=%.2fs total=%.2fs stage_totals=[%s]",
            profile.workflow,
            len(profile.requested_wires),
            measured_wires,
            profile.skipped_wires,
            profile.planning_seconds,
            avg_wire_seconds,
            profile.total_seconds,
            stage_summary,
        )

    def start_wire(self, workflow: str, wire_number: int) -> None:
        if self.active_batch is None:
            self.active_wire = None
            return
        self.active_wire = WireMeasurementProfile(
            workflow=workflow,
            wire_number=int(wire_number),
            started_at=self._profile_time(),
        )

    def record_stage(self, stage: str, elapsed: float) -> None:
        if self.active_wire is not None:
            self.active_wire.add(stage, elapsed)

    def complete_wire(self, *, skipped: bool = False) -> None:
        profile = self.active_wire
        self.active_wire = None
        if self.active_batch is None or profile is None:
            return
        if skipped:
            self.active_batch.skipped_wires.append(profile.wire_number)
            return
        self.active_batch.complete_wire(profile)
        stage_summary = (
            ", ".join(
                f"{stage}={elapsed:.2f}s"
                for stage, elapsed in sorted(
                    profile.stage_seconds.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )
            )
            or "none"
        )
        LOGGER.info(
            "Timing profile for %s wire %s: total=%.2fs stages=[%s]",
            profile.workflow,
            profile.wire_number,
            profile.total_seconds,
            stage_summary,
        )
