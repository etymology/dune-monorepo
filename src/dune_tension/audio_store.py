"""Persistent audio recording store for reanalysis and ML training.

Every audio sample captured during tension measurement is saved as a
32-bit float WAV alongside a row in ``audio_recordings.db`` carrying all
wire-identity and physical-position metadata needed to re-run analysis
without the hardware present.

Disable by setting ``DUNE_TENSION_RECORD_AUDIO=0`` in the environment.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

LOGGER = logging.getLogger(__name__)

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS audio_recordings (
    recording_id      TEXT PRIMARY KEY,
    wav_path          TEXT NOT NULL,
    timestamp         TEXT NOT NULL,
    apa_name          TEXT,
    layer             TEXT,
    side              TEXT,
    wire_number       INTEGER,
    x_mm              REAL,
    y_mm              REAL,
    focus_position    INTEGER,
    zone              INTEGER,
    wire_length_m     REAL,
    sample_rate       INTEGER,
    n_samples         INTEGER,
    duration_s        REAL,
    amplitude_rms     REAL,
    noise_filter_applied INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_audio_wire
    ON audio_recordings (apa_name, layer, side, wire_number);
CREATE INDEX IF NOT EXISTS idx_audio_timestamp
    ON audio_recordings (timestamp);
"""


@dataclass
class AudioRecordingMeta:
    apa_name: str
    layer: str
    side: str
    wire_number: int
    x_mm: float
    y_mm: float
    focus_position: int | None
    zone: int | None
    wire_length_m: float
    timestamp: datetime
    noise_filter_applied: bool = True


class AudioStore:
    """Save captured audio samples and metadata for later reanalysis or training.

    Each call to :meth:`save` writes one WAV file and one database row.
    Recordings are organised as::

        <root_dir>/
          <apa_name>/<layer>/<side>/
            <timestamp>_<wire_number>_<uuid8>.wav
          audio_recordings.db
    """

    def __init__(self, root_dir: Path, enabled: bool = True) -> None:
        self.root_dir = Path(root_dir)
        self.enabled = bool(enabled)
        self._db_path = self.root_dir / "audio_recordings.db"
        self._conn: sqlite3.Connection | None = None

    @classmethod
    def from_environ(cls, root_dir: Path) -> "AudioStore":
        """Build from the environment; disabled when ``DUNE_TENSION_RECORD_AUDIO=0``."""
        disabled = os.environ.get("DUNE_TENSION_RECORD_AUDIO", "1").strip() == "0"
        instance = cls(root_dir=root_dir, enabled=not disabled)
        if instance.enabled:
            LOGGER.info(
                "AudioStore enabled — recordings → %s  (set DUNE_TENSION_RECORD_AUDIO=0 to disable)",
                root_dir,
            )
        return instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_open(self) -> sqlite3.Connection:
        if self._conn is None:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        return self._conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(
        self,
        audio_sample: Any,
        sample_rate: int,
        meta: AudioRecordingMeta,
    ) -> str | None:
        """Persist one audio capture.

        Returns the ``recording_id`` (UUID string) on success, or ``None``
        when the store is disabled or a non-fatal error occurs.
        """
        if not self.enabled:
            return None

        arr = np.asarray(audio_sample, dtype=np.float32).reshape(-1)
        if arr.size == 0:
            return None

        recording_id = str(uuid.uuid4())

        # WAV path: <apa>/<layer>/<side>/<timestamp>_<wire>_<uuid8>.wav
        rel_dir = (
            Path(meta.apa_name or "unknown")
            / (meta.layer or "unknown")
            / (meta.side or "unknown")
        )
        wav_dir = self.root_dir / rel_dir
        wav_dir.mkdir(parents=True, exist_ok=True)

        ts_str = meta.timestamp.strftime("%Y%m%dT%H%M%S%f")
        wav_filename = f"{ts_str}_{meta.wire_number:04d}_{recording_id[:8]}.wav"
        rel_wav = str(rel_dir / wav_filename)
        wav_path = self.root_dir / rel_wav

        try:
            _write_wav(wav_path, arr, sample_rate)
        except Exception as exc:
            LOGGER.warning("AudioStore: failed to write WAV %s: %s", wav_path, exc)
            return None

        amplitude_rms = float(
            np.sqrt(np.mean(np.square(arr.astype(np.float64)) + 1e-12))
        )
        n_samples = int(arr.size)
        duration_s = n_samples / max(int(sample_rate), 1)

        try:
            conn = self._ensure_open()
            conn.execute(
                """
                INSERT INTO audio_recordings (
                    recording_id, wav_path, timestamp,
                    apa_name, layer, side, wire_number,
                    x_mm, y_mm, focus_position, zone, wire_length_m,
                    sample_rate, n_samples, duration_s,
                    amplitude_rms, noise_filter_applied
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recording_id,
                    rel_wav,
                    meta.timestamp.isoformat(),
                    meta.apa_name,
                    meta.layer,
                    meta.side,
                    int(meta.wire_number),
                    float(meta.x_mm),
                    float(meta.y_mm),
                    int(meta.focus_position) if meta.focus_position is not None else None,
                    int(meta.zone) if meta.zone is not None else None,
                    float(meta.wire_length_m),
                    int(sample_rate),
                    n_samples,
                    float(duration_s),
                    amplitude_rms,
                    int(meta.noise_filter_applied),
                ),
            )
            conn.commit()
        except Exception as exc:
            LOGGER.warning(
                "AudioStore: failed to write metadata for %s: %s", recording_id, exc
            )
            return None

        LOGGER.debug(
            "AudioStore: saved %s wire=%s %.3fs %d samples",
            recording_id[:8],
            meta.wire_number,
            duration_s,
            n_samples,
        )
        return recording_id

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    """Write a 32-bit float WAV file (lossless, no quantisation)."""
    from scipy.io import wavfile  # lazy — scipy is a project dependency

    wavfile.write(str(path), int(sample_rate), samples.astype(np.float32))


__all__ = ["AudioRecordingMeta", "AudioStore"]
