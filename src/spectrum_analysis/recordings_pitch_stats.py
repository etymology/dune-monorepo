"""Run PESTO pitch estimation over saved recordings and plot statistics.

Enumerates the WAV files captured by :class:`dune_tension.audio_store.AudioStore`
(default ``dune_tension/audio/recordings``), runs PESTO on each, and renders a
panel of plots summarising the per-file consensus pitch and confidence.

File enumeration prefers ``audio_recordings.db`` so wire-identity metadata
(APA / layer / side / wire number / duration) is available for the plots; it
falls back to a recursive ``*.wav`` glob when the database is absent.

Examples
--------
    uv run dune-spectrum-recording-stats                       # default sample
    uv run dune-spectrum-recording-stats --all                 # every recording
    uv run dune-spectrum-recording-stats --limit 2000 --side B
    uv run dune-spectrum-recording-stats --output stats.png --csv per_file.csv

Backend selection is via the ``PESTO_BACKEND`` env var (``auto``/``pytorch``/
``onnx``); the ONNX backend is markedly faster for a bulk sweep like this.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from spectrum_analysis.audio_processing import load_audio
from spectrum_analysis.pesto_analysis import analyze_audio_with_pesto

DEFAULT_RECORDINGS_DIR = Path("dune_tension/audio/recordings")
DB_FILENAME = "audio_recordings.db"
DEFAULT_SAMPLE = 500


@dataclass
class Recording:
    """One enumerated recording plus whatever metadata we could recover."""

    path: Path
    sample_rate: Optional[int] = None
    apa_name: Optional[str] = None
    layer: Optional[str] = None
    side: Optional[str] = None
    wire_number: Optional[int] = None
    duration_s: Optional[float] = None
    wire_length_m: Optional[float] = None


@dataclass
class PitchStat:
    """Per-file PESTO consensus result joined with recording metadata."""

    rec: Recording
    frequency: float
    confidence: float


# ----------------------------------------------------------------------
# Enumeration
# ----------------------------------------------------------------------


def _enumerate_from_db(
    root: Path,
    *,
    apa: Optional[str],
    layer: Optional[str],
    side: Optional[str],
) -> list[Recording]:
    db_path = root / DB_FILENAME
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        where: list[str] = []
        params: list[object] = []
        if apa:
            where.append("apa_name = ?")
            params.append(apa)
        if layer:
            where.append("layer = ?")
            params.append(layer)
        if side:
            where.append("side = ?")
            params.append(side)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = conn.execute(
            "SELECT wav_path, sample_rate, apa_name, layer, side, "
            "wire_number, duration_s, wire_length_m "
            f"FROM audio_recordings{clause} ORDER BY timestamp",
            params,
        ).fetchall()
    finally:
        conn.close()

    recs: list[Recording] = []
    for r in rows:
        wav = root / r["wav_path"]
        if not wav.exists():
            continue
        recs.append(
            Recording(
                path=wav,
                sample_rate=r["sample_rate"],
                apa_name=r["apa_name"],
                layer=r["layer"],
                side=r["side"],
                wire_number=r["wire_number"],
                duration_s=r["duration_s"],
                wire_length_m=r["wire_length_m"],
            )
        )
    return recs


def _enumerate_from_glob(root: Path) -> list[Recording]:
    return [Recording(path=p) for p in sorted(root.rglob("*.wav"))]


def enumerate_recordings(
    root: Path,
    *,
    apa: Optional[str],
    layer: Optional[str],
    side: Optional[str],
) -> list[Recording]:
    """Enumerate recordings, preferring the metadata DB over a raw glob."""

    if (root / DB_FILENAME).exists():
        recs = _enumerate_from_db(root, apa=apa, layer=layer, side=side)
        if recs:
            return recs
        print("[WARN] DB present but no rows matched; falling back to glob.")
    elif apa or layer or side:
        print("[WARN] No DB found; --apa/--layer/--side filters are ignored.")
    return _enumerate_from_glob(root)


# ----------------------------------------------------------------------
# Analysis
# ----------------------------------------------------------------------


def analyze_recordings(recs: list[Recording]) -> list[PitchStat]:
    """Run PESTO on each recording, returning per-file consensus stats."""

    stats: list[PitchStat] = []
    total = len(recs)
    failures = 0
    for i, rec in enumerate(recs, start=1):
        try:
            # Pass the recording's own sample rate as the target so load_audio
            # does not resample; fall back to 44.1 kHz when the DB lacks it.
            target_sr = int(rec.sample_rate) if rec.sample_rate else 44100
            audio, sr = load_audio(rec.path, target_sr)
            result = analyze_audio_with_pesto(audio, sr)
            stats.append(
                PitchStat(
                    rec=rec,
                    frequency=float(result.frequency),
                    confidence=float(result.confidence),
                )
            )
        except Exception as exc:  # keep going; one bad file shouldn't abort the sweep
            failures += 1
            print(f"[WARN] {rec.path.name}: {exc}")

        if i % 25 == 0 or i == total:
            print(f"  analysed {i}/{total} ({failures} failures)", end="\r", flush=True)
    print()
    return stats


# ----------------------------------------------------------------------
# Plotting / reporting
# ----------------------------------------------------------------------


def _summary_lines(freqs: np.ndarray, confs: np.ndarray, n_total: int) -> list[str]:
    def fmt(arr: np.ndarray, unit: str) -> str:
        if arr.size == 0:
            return "n/a"
        return (
            f"n={arr.size}  mean={arr.mean():.2f}{unit}  median={np.median(arr):.2f}{unit}  "
            f"std={arr.std():.2f}{unit}  min={arr.min():.2f}  max={arr.max():.2f}"
        )

    return [
        f"Files analysed: {n_total}   voiced (finite pitch): {freqs.size}",
        f"Pitch (Hz):  {fmt(freqs, 'Hz')}",
        f"Confidence:  {fmt(confs, '')}",
    ]


def plot_stats(stats: list[PitchStat], output: Optional[Path]) -> None:
    import matplotlib

    if output is not None:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    freq_all = np.array([s.frequency for s in stats], dtype=float)
    conf_all = np.array([s.confidence for s in stats], dtype=float)
    finite = np.isfinite(freq_all) & np.isfinite(conf_all)
    freqs = freq_all[finite]
    confs = conf_all[finite]

    for line in _summary_lines(freqs, conf_all[np.isfinite(conf_all)], len(stats)):
        print(line)

    if freqs.size == 0:
        print("[ERROR] No finite pitch estimates to plot (PESTO deps available?).")
        return

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    fig.suptitle(
        f"PESTO recording statistics — {len(stats)} files ({freqs.size} voiced)",
        fontsize=13,
    )

    # 1. Confidence histogram
    ax = axes[0, 0]
    ax.hist(confs, bins=40, color="#3b7dd8", edgecolor="white")
    ax.axvline(
        np.median(confs),
        color="k",
        ls="--",
        lw=1,
        label=f"median {np.median(confs):.3f}",
    )
    ax.set(title="Confidence distribution", xlabel="confidence", ylabel="count")
    ax.legend()

    # 2. Pitch histogram
    ax = axes[0, 1]
    ax.hist(freqs, bins=60, color="#d8743b", edgecolor="white")
    ax.axvline(
        np.median(freqs),
        color="k",
        ls="--",
        lw=1,
        label=f"median {np.median(freqs):.1f} Hz",
    )
    ax.set(title="Pitch distribution", xlabel="frequency (Hz)", ylabel="count")
    ax.legend()

    # 3. Pitch vs confidence scatter
    ax = axes[1, 0]
    sc = ax.scatter(freqs, confs, c=confs, cmap="viridis", s=12, alpha=0.6)
    ax.set(title="Pitch vs confidence", xlabel="frequency (Hz)", ylabel="confidence")
    fig.colorbar(sc, ax=ax, label="confidence")

    # 4. Confidence by side/layer group (boxplot) if metadata exists, else CDF.
    ax = axes[1, 1]
    groups: dict[str, list[float]] = {}
    for s in stats:
        if not np.isfinite(s.confidence):
            continue
        key_parts = [p for p in (s.rec.apa_name, s.rec.layer, s.rec.side) if p]
        key = "/".join(key_parts) if key_parts else "all"
        groups.setdefault(key, []).append(s.confidence)

    if len(groups) > 1:
        labels = sorted(groups)
        ax.boxplot([groups[k] for k in labels], tick_labels=labels, showfliers=False)
        ax.set(title="Confidence by group", ylabel="confidence")
        ax.tick_params(axis="x", rotation=45)
    else:
        order = np.sort(confs)
        cdf = np.arange(1, order.size + 1) / order.size
        ax.plot(order, cdf, color="#3b7dd8")
        ax.set(title="Confidence CDF", xlabel="confidence", ylabel="fraction ≤ x")
        ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=(0, 0, 1, 0.96))

    if output is not None:
        fig.savefig(output, dpi=130)
        print(f"Saved figure → {output}")
    else:
        plt.show()


def write_csv(stats: list[PitchStat], path: Path) -> None:
    with path.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "wav_path",
                "apa_name",
                "layer",
                "side",
                "wire_number",
                "duration_s",
                "frequency_hz",
                "confidence",
            ]
        )
        for s in stats:
            r = s.rec
            writer.writerow(
                [
                    str(r.path),
                    r.apa_name,
                    r.layer,
                    r.side,
                    r.wire_number,
                    r.duration_s,
                    f"{s.frequency:.4f}",
                    f"{s.confidence:.4f}",
                ]
            )
    print(f"Wrote per-file results → {path}")


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    summary = (__doc__ or "").splitlines()[0]
    p = argparse.ArgumentParser(description=summary)
    p.add_argument(
        "--recordings-dir",
        type=Path,
        default=DEFAULT_RECORDINGS_DIR,
        help=f"Directory of recordings (default: {DEFAULT_RECORDINGS_DIR}).",
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_SAMPLE,
        help=f"Random sample of this many files (default: {DEFAULT_SAMPLE}). "
        "0 means all.",
    )
    g.add_argument("--all", action="store_true", help="Analyse every recording.")
    p.add_argument("--seed", type=int, default=0, help="RNG seed for sampling.")
    p.add_argument("--apa", help="Filter by APA name (requires the metadata DB).")
    p.add_argument("--layer", help="Filter by layer (requires the metadata DB).")
    p.add_argument("--side", help="Filter by side (requires the metadata DB).")
    p.add_argument(
        "--output",
        type=Path,
        help="Save the figure here (PNG) instead of showing it interactively.",
    )
    p.add_argument("--csv", type=Path, help="Also write per-file results to this CSV.")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    root = args.recordings_dir
    if not root.exists():
        print(f"[ERROR] Recordings directory not found: {root}", file=sys.stderr)
        return 1

    recs = enumerate_recordings(root, apa=args.apa, layer=args.layer, side=args.side)
    if not recs:
        print(f"[ERROR] No recordings found under {root}", file=sys.stderr)
        return 1
    print(f"Found {len(recs)} recordings under {root}.")

    limit = 0 if args.all else args.limit
    if limit and limit < len(recs):
        rng = np.random.default_rng(args.seed)
        idx = rng.choice(len(recs), size=limit, replace=False)
        recs = [recs[i] for i in sorted(idx)]
        print(
            f"Sampled {len(recs)} files (seed={args.seed}). Use --all for everything."
        )

    stats = analyze_recordings(recs)
    if not stats:
        print("[ERROR] No files analysed successfully.", file=sys.stderr)
        return 1

    if args.csv:
        write_csv(stats, args.csv)

    plot_stats(stats, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
