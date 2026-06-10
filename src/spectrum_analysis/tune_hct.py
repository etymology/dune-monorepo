"""Calibrate the harmonic-comb voiced gate (HCT) against PESTO's voiced labels.

The streaming pipeline uses a cheap harmonic-comb trigger (``comb_score`` /
``spectral_flatness`` / ``rms`` / ``harmonic_valid``) as a *gate* deciding which
audio frames are "voiced" and therefore worth sending to PESTO for pitch
estimation (:mod:`dune_tension.streaming.analysis`). PESTO is the slow,
authoritative voiced detector — its per-frame confidence is the ground truth we
want the gate to agree with.

This tool treats PESTO as the oracle and tunes the gate thresholds so the gate
**captures every voiced frame** (high recall) while still filtering as much
unvoiced audio as possible (the speed win). For each recording it:

1. runs PESTO once to get per-frame confidence (the voiced label), and
2. recomputes the comb features on the *same* frame grid the production
   analyzer uses (reusing :class:`FastFrameAnalyzer`'s exact window / candidate
   setup so the numbers transfer directly).

It then picks thresholds that achieve a target recall against PESTO, reports the
resulting precision / pass-rate / speed-up versus the current defaults, and
plots the feature distributions split by voiced/unvoiced with the recommended
cut lines.

Per-frame features are cached to ``--cache`` (an ``.npz``) so re-tuning the
thresholds does not re-run PESTO.

Examples
--------
    uv run dune-spectrum-tune-hct --limit 400 --cache /tmp/hct.npz
    uv run dune-spectrum-tune-hct --cache /tmp/hct.npz --target-recall 0.99 \\
        --output hct_tuning.png
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from dune_tension.streaming.analysis import (
    FastFrameAnalyzer,
    StreamingAnalysisConfig,
)
from spectrum_analysis.audio_processing import load_audio
from spectrum_analysis.comb_trigger import harmonic_comb_response
from spectrum_analysis.pesto_analysis import analyze_audio_with_pesto
from spectrum_analysis.recordings_pitch_stats import (
    DEFAULT_RECORDINGS_DIR,
    enumerate_recordings,
)

DEFAULT_SAMPLE = 300
DEFAULT_VOICED_CONF = 0.75


# ----------------------------------------------------------------------
# Feature extraction
# ----------------------------------------------------------------------


def _frame_features(
    analyzer: FastFrameAnalyzer, audio: np.ndarray, sr: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Comb features per production frame, plus each frame's [start, end] seconds.

    Mirrors :meth:`FastFrameAnalyzer.analyze_chunk` minus the pose/cruise gating
    (irrelevant here — we calibrate the harmonic features themselves).
    """

    cfg = analyzer.config
    n = audio.size
    starts = list(range(0, n - cfg.frame_size + 1, cfg.hop_size))
    comb = np.empty(len(starts), dtype=np.float64)
    sfm = np.empty(len(starts), dtype=np.float64)
    rms = np.empty(len(starts), dtype=np.float64)
    valid = np.empty(len(starts), dtype=bool)
    spans = np.empty((len(starts), 2), dtype=np.float64)

    for i, start in enumerate(starts):
        frame = audio[start : start + cfg.frame_size]
        c, f, v = harmonic_comb_response(
            frame,
            cfg.sample_rate,
            analyzer.window,
            analyzer.freq_bins,
            analyzer._default_candidates,
            analyzer.weights,
            int(cfg.min_harmonics),
        )
        comb[i] = c
        sfm[i] = f
        valid[i] = v
        rms[i] = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
        spans[i, 0] = start / sr
        spans[i, 1] = (start + cfg.frame_size) / sr

    return comb, sfm, rms, valid, spans


def _label_from_pesto(
    spans: np.ndarray, pesto_times: np.ndarray, pesto_conf: np.ndarray
) -> np.ndarray:
    """Max PESTO confidence falling inside each HCT frame's time span.

    PESTO hops every ~5 ms, the HCT frame spans ~46 ms, so several PESTO frames
    land in each HCT frame; the loudest (max-confidence) one defines the label.
    """

    conf = np.zeros(spans.shape[0], dtype=np.float64)
    if pesto_times.size == 0:
        return conf
    order = np.argsort(pesto_times)
    t = pesto_times[order]
    c = pesto_conf[order]
    lo = np.searchsorted(t, spans[:, 0], side="left")
    hi = np.searchsorted(t, spans[:, 1], side="right")
    for i in range(spans.shape[0]):
        if hi[i] > lo[i]:
            conf[i] = float(np.max(c[lo[i] : hi[i]]))
        else:  # no PESTO frame in span — fall back to nearest
            j = min(max(lo[i], 0), t.size - 1)
            conf[i] = float(c[j])
    return conf


# ----------------------------------------------------------------------
# Collection + cache
# ----------------------------------------------------------------------


def collect_frames(
    recordings_dir: Path,
    *,
    limit: int,
    seed: int,
    apa: Optional[str],
    layer: Optional[str],
    side: Optional[str],
    min_harmonics: int,
) -> dict[str, np.ndarray]:
    """Run PESTO + comb features over a sample of recordings; return flat arrays."""

    recs = enumerate_recordings(recordings_dir, apa=apa, layer=layer, side=side)
    if not recs:
        raise SystemExit(f"No recordings found under {recordings_dir}")
    print(f"Found {len(recs)} recordings.")
    if limit and limit < len(recs):
        rng = np.random.default_rng(seed)
        idx = sorted(rng.choice(len(recs), size=limit, replace=False))
        recs = [recs[i] for i in idx]
        print(f"Sampled {len(recs)} recordings (seed={seed}).")

    comb_l, sfm_l, rms_l, valid_l, conf_l = [], [], [], [], []
    total = len(recs)
    failures = 0
    analyzer: FastFrameAnalyzer | None = None
    analyzer_sr: int | None = None

    for k, rec in enumerate(recs, start=1):
        try:
            target_sr = int(rec.sample_rate) if rec.sample_rate else 44100
            audio, sr = load_audio(rec.path, target_sr)
            if analyzer is None or analyzer_sr != sr:
                analyzer = FastFrameAnalyzer(
                    StreamingAnalysisConfig(sample_rate=sr, min_harmonics=min_harmonics)
                )
                analyzer_sr = sr
            if audio.size < analyzer.config.frame_size:
                continue
            result = analyze_audio_with_pesto(audio, sr)
            comb, sfm, rms, valid, spans = _frame_features(analyzer, audio, sr)
            conf = _label_from_pesto(
                spans, result.frame_times, result.frame_confidences
            )
            comb_l.append(comb)
            sfm_l.append(sfm)
            rms_l.append(rms)
            valid_l.append(valid)
            conf_l.append(conf)
        except Exception as exc:
            failures += 1
            print(f"[WARN] {rec.path.name}: {exc}")
        if k % 10 == 0 or k == total:
            print(
                f"  processed {k}/{total} ({failures} failures)", end="\r", flush=True
            )
    print()

    if not comb_l:
        raise SystemExit("No frames collected.")
    return {
        "comb": np.concatenate(comb_l),
        "sfm": np.concatenate(sfm_l),
        "rms": np.concatenate(rms_l),
        "valid": np.concatenate(valid_l),
        "pesto_conf": np.concatenate(conf_l),
        "min_harmonics": np.array([min_harmonics]),
    }


# ----------------------------------------------------------------------
# Tuning
# ----------------------------------------------------------------------


def _metrics(
    voiced: np.ndarray,
    comb: np.ndarray,
    sfm: np.ndarray,
    rms: np.ndarray,
    valid: np.ndarray,
    *,
    comb_t: float,
    sfm_t: float,
    rms_t: float,
    require_valid: bool,
) -> dict[str, float]:
    passes = (comb >= comb_t) & (sfm <= sfm_t) & (rms >= rms_t)
    if require_valid:
        passes = passes & valid
    n_voiced = int(voiced.sum())
    n_unvoiced = int(voiced.size - n_voiced)
    n_pass = int(passes.sum())
    tp = int((passes & voiced).sum())
    fp = n_pass - tp  # passed the gate but PESTO says unvoiced
    recall = tp / n_voiced if n_voiced else float("nan")
    precision = tp / n_pass if n_pass else float("nan")
    return {
        "comb_t": comb_t,
        "sfm_t": sfm_t,
        "rms_t": rms_t,
        "require_valid": float(require_valid),
        "recall": recall,
        "precision": precision,
        "pass_rate": n_pass / voiced.size,
        "missed_voiced": float(n_voiced - tp),
        "false_pos": float(fp),
        # Fraction of truly-unvoiced frames the gate wrongly lets through.
        "fpr": (fp / n_unvoiced) if n_unvoiced else float("nan"),
        "speedup": (voiced.size / n_pass) if n_pass else float("inf"),
    }


@dataclass
class Recommendation:
    voiced: np.ndarray
    voiced_conf: float
    target_recall: float
    valid_frac_voiced: float
    recommended: dict[str, float]


def recommend(
    data: dict[str, np.ndarray],
    *,
    voiced_conf: float,
    target_recall: float,
) -> Recommendation:
    """Pick gate thresholds achieving ``target_recall`` against PESTO voiced frames.

    For target_recall == 1 the optimal axis-aligned gate sets each threshold to
    the voiced extreme (so no voiced frame is rejected on any axis). For a lower
    target we relax each axis to the matching voiced quantile, then *measure* the
    actual joint recall (the conjunction recall is not separable, so we report
    what the chosen thresholds really achieve rather than assume the target).
    """

    comb, sfm, rms, valid = data["comb"], data["sfm"], data["rms"], data["valid"]
    voiced = data["pesto_conf"] >= voiced_conf
    if not voiced.any():
        raise SystemExit(
            f"No voiced frames at conf>={voiced_conf}; lower --voiced-conf."
        )

    cv, sv, rv, vv = comb[voiced], sfm[voiced], rms[voiced], valid[voiced]
    # Fraction of voiced we permit dropping on each axis.
    q = max(0.0, 1.0 - target_recall)
    comb_t = float(np.quantile(cv, q)) if q else float(cv.min())
    sfm_t = float(np.quantile(sv, 1.0 - q)) if q else float(sv.max())
    rms_t = float(np.quantile(rv, q)) if q else float(rv.min())

    # harmonic_valid is only safe to require if (nearly) all voiced frames satisfy it.
    valid_frac = float(vv.mean())
    require_valid = valid_frac >= target_recall

    rec = _metrics(
        voiced,
        comb,
        sfm,
        rms,
        valid,
        comb_t=comb_t,
        sfm_t=sfm_t,
        rms_t=rms_t,
        require_valid=require_valid,
    )
    return Recommendation(
        voiced=voiced,
        voiced_conf=voiced_conf,
        target_recall=target_recall,
        valid_frac_voiced=valid_frac,
        recommended=rec,
    )


def _print_report(data: dict[str, np.ndarray], result: Recommendation) -> None:
    voiced = result.voiced
    comb, sfm, rms, valid = data["comb"], data["sfm"], data["rms"], data["valid"]
    n = comb.size
    n_voiced = int(np.asarray(voiced).sum())
    print("=" * 70)
    print(
        f"Frames: {n}   voiced (PESTO conf>={result.voiced_conf}): "
        f"{n_voiced} ({100 * n_voiced / n:.1f}%)"
    )
    mh = int(data["min_harmonics"][0])
    print(
        f"harmonic_valid covers {100 * result.valid_frac_voiced:.1f}% "
        f"of voiced frames (min_harmonics={mh})"
    )
    voiced_arr = np.asarray(voiced)
    zero_comb = float((comb[voiced_arr] <= 0.0).mean()) if voiced_arr.any() else 0.0
    if zero_comb > 0.02:
        print(
            f"NOTE: {100 * zero_comb:.1f}% of voiced frames have comb_score==0 "
            f"(comb finds <{mh} harmonics) — the comb gate cannot discriminate "
            "these without lowering --min-harmonics."
        )

    defaults = StreamingAnalysisConfig(sample_rate=1)
    current = _metrics(
        np.asarray(voiced),
        comb,
        sfm,
        rms,
        valid,
        comb_t=defaults.comb_threshold,
        sfm_t=defaults.flatness_threshold,
        rms_t=defaults.min_rms,
        require_valid=True,
    )
    rec = result.recommended

    def row(tag: str, m: dict[str, float]) -> None:
        print(
            f"  {tag:<12} comb>={m['comb_t']:.4g}  sfm<={m['sfm_t']:.4g}  "
            f"rms>={m['rms_t']:.4g}  valid={'yes' if m['require_valid'] else 'no '}"
            f"  | recall={m['recall']:.3f}  prec={m['precision']:.3f}  "
            f"missed={int(m['missed_voiced'])}  "
            f"FP={int(m['false_pos'])} (FPR={m['fpr']:.3f})  "
            f"pass={m['pass_rate']:.3f}  speedup={m['speedup']:.1f}x"
        )

    print("-" * 70)
    print(f"Target recall: {result.target_recall}")
    row("current", current)
    row("recommended", rec)
    print("=" * 70)
    print(
        "Apply to StreamingAnalysisConfig:\n"
        f"    comb_threshold    = {rec['comb_t']:.6g}\n"
        f"    flatness_threshold= {rec['sfm_t']:.6g}\n"
        f"    min_rms           = {rec['rms_t']:.6g}"
    )


# ----------------------------------------------------------------------
# Plotting
# ----------------------------------------------------------------------


def plot_tuning(
    data: dict[str, np.ndarray],
    result: Recommendation,
    output: Optional[Path],
) -> None:
    import matplotlib

    if output is not None:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    voiced = np.asarray(result.voiced)
    rec = result.recommended
    defaults = StreamingAnalysisConfig(sample_rate=1)
    comb, sfm, rms = data["comb"], data["sfm"], data["rms"]

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    fig.suptitle(
        f"HCT vs PESTO voiced calibration — {comb.size} frames, "
        f"target recall {result.target_recall}",
        fontsize=13,
    )

    def feature_hist(ax, vals, *, name, rec_t, cur_t, log, upper):
        v = vals[voiced]
        u = vals[~voiced]
        if log:
            v = v[v > 0]
            u = u[u > 0]
            lo = min(v.min(), u.min()) if v.size and u.size else 1e-12
            hi = max(vals.max(), 1e-12)
            bins = np.logspace(np.log10(max(lo, 1e-15)), np.log10(hi), 50)
            ax.set_xscale("log")
        else:
            bins = np.linspace(0, max(vals.max(), 1e-6), 50)
        ax.hist(u, bins=bins, color="#bbbbbb", alpha=0.7, label="unvoiced")
        ax.hist(v, bins=bins, color="#3b7dd8", alpha=0.7, label="voiced")
        ax.axvline(rec_t, color="#d62728", lw=2, label=f"recommended {rec_t:.3g}")
        ax.axvline(cur_t, color="green", ls="--", lw=1.5, label=f"current {cur_t:.3g}")
        ax.set(title=name, xlabel=name, ylabel="frames")
        ax.legend(fontsize=8)

    feature_hist(
        axes[0, 0],
        comb,
        name="comb_score (gate: >=)",
        rec_t=rec["comb_t"],
        cur_t=defaults.comb_threshold,
        log=False,
        upper=None,
    )
    feature_hist(
        axes[0, 1],
        sfm,
        name="spectral_flatness (gate: <=)",
        rec_t=rec["sfm_t"],
        cur_t=defaults.flatness_threshold,
        log=False,
        upper=None,
    )
    feature_hist(
        axes[1, 0],
        rms,
        name="rms (gate: >=)",
        rec_t=rec["rms_t"],
        cur_t=defaults.min_rms,
        log=True,
        upper=None,
    )

    # Recall / pass-rate tradeoff as comb_threshold sweeps (others held at recommended).
    ax = axes[1, 1]
    grid = np.unique(np.quantile(comb, np.linspace(0, 1, 200)))
    recalls, passes, fprs = [], [], []
    for c in grid:
        m = _metrics(
            voiced,
            comb,
            sfm,
            rms,
            data["valid"],
            comb_t=float(c),
            sfm_t=rec["sfm_t"],
            rms_t=rec["rms_t"],
            require_valid=bool(rec["require_valid"]),
        )
        recalls.append(m["recall"])
        passes.append(m["pass_rate"])
        fprs.append(m["fpr"])
    ax.plot(grid, recalls, color="#3b7dd8", label="recall (voiced captured)")
    ax.plot(grid, fprs, color="#9467bd", label="false-positive rate (unvoiced passed)")
    ax.plot(grid, passes, color="#d8743b", label="pass-rate (sent to PESTO)")
    ax.axvline(rec["comb_t"], color="#d62728", lw=2, label="recommended")
    ax.axvline(defaults.comb_threshold, color="green", ls="--", lw=1.5, label="current")
    ax.set(
        title="comb_threshold sweep (sfm/rms at recommended)",
        xlabel="comb_threshold",
        ylabel="fraction",
    )
    ax.set_ylim(0, 1.02)
    ax.legend(fontsize=8)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    if output is not None:
        fig.savefig(output, dpi=130)
        print(f"Saved figure → {output}")
    else:
        plt.show()


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--recordings-dir", type=Path, default=DEFAULT_RECORDINGS_DIR)
    p.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_SAMPLE,
        help=f"Random sample of recordings (default {DEFAULT_SAMPLE}; 0 = all).",
    )
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--apa")
    p.add_argument("--layer")
    p.add_argument("--side")
    p.add_argument(
        "--voiced-conf",
        type=float,
        default=DEFAULT_VOICED_CONF,
        help="PESTO per-frame confidence at/above which a frame is 'voiced'.",
    )
    p.add_argument(
        "--target-recall",
        type=float,
        default=1.0,
        help="Fraction of voiced frames the gate must capture (default 1.0 = all).",
    )
    p.add_argument(
        "--min-harmonics",
        type=int,
        default=StreamingAnalysisConfig(sample_rate=1).min_harmonics,
        help="Harmonics the comb must find for comb_score>0 / harmonic_valid "
        "(production default 3). Lower it to let the comb gate score sparse tones.",
    )
    p.add_argument(
        "--cache",
        type=Path,
        help="Cache per-frame features here (.npz); reused on re-run to skip PESTO.",
    )
    p.add_argument("--output", type=Path, help="Save figure (PNG) instead of showing.")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    if args.cache and args.cache.exists():
        print(f"Loading cached features ← {args.cache}")
        loaded = np.load(args.cache)
        data = {k: loaded[k] for k in loaded.files}
        cached_mh = int(data["min_harmonics"][0])
        if cached_mh != args.min_harmonics:
            print(
                f"[WARN] cache was built with min_harmonics={cached_mh}, not "
                f"{args.min_harmonics}. Delete {args.cache} to re-extract.",
                file=sys.stderr,
            )
    else:
        if not args.recordings_dir.exists():
            print(f"[ERROR] not found: {args.recordings_dir}", file=sys.stderr)
            return 1
        data = collect_frames(
            args.recordings_dir,
            limit=0 if args.limit == 0 else args.limit,
            seed=args.seed,
            apa=args.apa,
            layer=args.layer,
            side=args.side,
            min_harmonics=args.min_harmonics,
        )
        if args.cache:
            np.savez_compressed(args.cache, **data)
            print(f"Cached features → {args.cache}")

    result = recommend(
        data, voiced_conf=args.voiced_conf, target_recall=args.target_recall
    )
    _print_report(data, result)
    plot_tuning(data, result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
