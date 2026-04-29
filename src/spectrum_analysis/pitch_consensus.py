"""Consensus helpers for aggregating framewise pitch tracks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PITCH_AREA_DISCONTINUITY_CENTS = 250.0
PITCH_AREA_MERGE_CENTS = 250.0


@dataclass(frozen=True)
class PitchConsensus:
    """Aggregate pitch chosen from the largest framewise pitch area."""

    frequency: float
    confidence: float
    selected_frame_count: int
    total_frame_count: int
    area_count: int


@dataclass
class _PitchArea:
    positions: list[np.ndarray]
    frame_count: int
    confidence_sum: float
    center_log2: float


def _empty_consensus() -> PitchConsensus:
    return PitchConsensus(
        frequency=float("nan"),
        confidence=float("nan"),
        selected_frame_count=0,
        total_frame_count=0,
        area_count=0,
    )


def _weighted_log2_average(frequencies: np.ndarray, weights: np.ndarray) -> float:
    log_frequencies = np.log2(frequencies)
    weight_sum = float(np.sum(weights))
    if weight_sum <= 0.0:
        return float(np.mean(log_frequencies))
    return float(np.average(log_frequencies, weights=weights))


def estimate_pitch_consensus(
    predicted_frequencies: np.ndarray,
    frame_confidences: np.ndarray,
    valid_mask: np.ndarray | None = None,
    *,
    discontinuity_cents: float = PITCH_AREA_DISCONTINUITY_CENTS,
    merge_cents: float = PITCH_AREA_MERGE_CENTS,
) -> PitchConsensus:
    """Choose the pitch area that the largest number of valid frames agree on.

    The framewise PESTO track can jump between stable plateaus.  This helper
    splits the track at abrupt pitch jumps, merges non-contiguous segments with
    similar pitch centers, then estimates the pitch only from the area with the
    most frames.
    """

    frequencies = np.asarray(predicted_frequencies, dtype=np.float64).reshape(-1)
    confidences = np.asarray(frame_confidences, dtype=np.float64).reshape(-1)
    if frequencies.size != confidences.size:
        raise ValueError("predicted_frequencies and frame_confidences must match.")

    valid = np.isfinite(frequencies) & (frequencies > 0.0)
    valid &= np.isfinite(confidences) & (confidences > 0.0)
    if valid_mask is not None:
        mask = np.asarray(valid_mask, dtype=bool).reshape(-1)
        if mask.size != frequencies.size:
            raise ValueError("valid_mask must match predicted_frequencies.")
        valid &= mask

    valid_indices = np.flatnonzero(valid)
    if valid_indices.size == 0:
        return _empty_consensus()

    valid_frequencies = frequencies[valid_indices]
    valid_confidences = confidences[valid_indices]
    if valid_frequencies.size == 1:
        return PitchConsensus(
            frequency=float(valid_frequencies[0]),
            confidence=float(valid_confidences[0]),
            selected_frame_count=1,
            total_frame_count=1,
            area_count=1,
        )

    log_frequencies = np.log2(valid_frequencies)
    jump_threshold = max(float(discontinuity_cents), 0.0) / 1200.0
    merge_threshold = max(float(merge_cents), 0.0) / 1200.0
    jumps = np.abs(np.diff(log_frequencies)) > jump_threshold
    gaps = np.diff(valid_indices) > 1
    segment_starts = np.concatenate(
        (
            np.array([0], dtype=np.intp),
            np.flatnonzero(jumps | gaps).astype(np.intp) + 1,
        )
    )
    segment_stops = np.concatenate(
        (
            segment_starts[1:],
            np.array([valid_frequencies.size], dtype=np.intp),
        )
    )

    areas: list[_PitchArea] = []
    for start, stop in zip(segment_starts, segment_stops):
        positions = np.arange(int(start), int(stop), dtype=np.intp)
        segment_frequencies = valid_frequencies[positions]
        segment_confidences = valid_confidences[positions]
        center_log2 = _weighted_log2_average(
            segment_frequencies, segment_confidences
        )
        confidence_sum = float(np.sum(segment_confidences))

        best_area: _PitchArea | None = None
        best_distance = float("inf")
        for area in areas:
            distance = abs(center_log2 - area.center_log2)
            if distance <= merge_threshold and distance < best_distance:
                best_area = area
                best_distance = distance

        if best_area is None:
            areas.append(
                _PitchArea(
                    positions=[positions],
                    frame_count=int(positions.size),
                    confidence_sum=confidence_sum,
                    center_log2=center_log2,
                )
            )
            continue

        old_weight = (
            best_area.confidence_sum
            if best_area.confidence_sum > 0.0
            else float(best_area.frame_count)
        )
        new_weight = confidence_sum if confidence_sum > 0.0 else float(positions.size)
        best_area.positions.append(positions)
        best_area.frame_count += int(positions.size)
        best_area.confidence_sum += confidence_sum
        best_area.center_log2 = (
            (best_area.center_log2 * old_weight) + (center_log2 * new_weight)
        ) / (old_weight + new_weight)

    best_area = max(
        enumerate(areas),
        key=lambda item: (item[1].frame_count, item[1].confidence_sum, -item[0]),
    )[1]
    selected_positions = np.concatenate(best_area.positions)
    selected_frequencies = valid_frequencies[selected_positions]
    selected_confidences = valid_confidences[selected_positions]
    weight_sum = float(np.sum(selected_confidences))
    if weight_sum <= 0.0:
        frequency = float(np.mean(selected_frequencies))
    else:
        frequency = float(np.average(selected_frequencies, weights=selected_confidences))

    return PitchConsensus(
        frequency=frequency,
        confidence=float(np.mean(selected_confidences)),
        selected_frame_count=int(selected_positions.size),
        total_frame_count=int(valid_frequencies.size),
        area_count=len(areas),
    )
