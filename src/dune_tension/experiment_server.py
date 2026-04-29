import os
import uuid
import io
import base64
from datetime import datetime
from typing import Any, List, Optional

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from matplotlib.figure import Figure

from dune_tension.tensiometer import build_tensiometer
from dune_tension.experiments import ExperimentMetadata, ExperimentResultRepository
from dune_tension.results import TensionResult
from dune_tension.services import build_runtime_bundle, resolve_runtime_options
from dune_tension.summaries import build_summary_plot_figure_for_config
from dune_tension.tensiometer_functions import TensiometerConfig, make_config
from dune_tension.paths import data_path

app = Flask(__name__, static_folder="../../dune_tension/web", static_url_path="")

EXPERIMENT_DB_PATH = str(data_path("experiment_measurements.db"))
RAW_AUDIO_DIR = data_path("experiment_audio")
RAW_AUDIO_DIR.mkdir(parents=True, exist_ok=True)


class ExperimentServerState:
    def __init__(self):
        self.last_audio_sample = None
        self.last_samplerate = None
        self.last_analysis = None
        self.current_experiment_id = None
        self.current_config = None

    def audio_callback(self, audio_sample, samplerate, analysis):
        self.last_audio_sample = audio_sample
        self.last_samplerate = samplerate
        self.last_analysis = analysis


state = ExperimentServerState()


@app.route("/")
def index():
    return app.send_static_file("Experiment.html")


@app.route("/experiment/start", methods=["POST"])
def start_experiment():
    data = request.get_json()

    state.current_experiment_id = str(uuid.uuid4())

    # Extract metadata
    metadata = ExperimentMetadata(
        experiment_id=state.current_experiment_id,
        experiment_name=data.get("name", "Unnamed Experiment"),
        experiment_type=data.get("type", "single_wire_single_zone"),
        known_tension=data.get("known_tension"),
        zone=data.get("zone"),
        notes=data.get("notes", ""),
    )

    # Store config for summary plots
    state.current_config = make_config(
        apa_name=data.get("apa_name", "TEST_APA"),
        layer=data.get("layer", "U"),
        side=data.get("side", "A"),
    )

    return jsonify(
        {
            "status": "ready",
            "experiment_id": state.current_experiment_id,
            "metadata": data,
        }
    )


def figure_to_base64(fig: Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=200)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@app.route("/experiment/plots/audio", methods=["GET"])
def get_audio_plot():
    if state.last_audio_sample is None:
        return jsonify({"status": "no_data"}), 404

    from dune_tension.gui.live_plots import LivePlotManager

    waveform = np.asarray(state.last_audio_sample, dtype=float).reshape(-1)
    fig = LivePlotManager._build_audio_diagnostics_figure(
        waveform, state.last_samplerate, state.last_analysis
    )

    return jsonify({"status": "success", "image": figure_to_base64(fig)})


@app.route("/experiment/plots/summary", methods=["GET"])
def get_summary_plot():
    if state.current_config is None:
        return jsonify({"status": "no_config"}), 404

    import sqlite3

    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    # Get all samples for current config
    query = "SELECT tension, confidence, amplitude, harmonicity, wire_number, side FROM tension_samples"
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        return jsonify({"status": "no_data"}), 404

    df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
    df["amplitude"] = pd.to_numeric(df["amplitude"], errors="coerce")
    df["harmonicity"] = pd.to_numeric(df["harmonicity"], errors="coerce")
    df = df.dropna(subset=["tension"])

    fig = Figure(figsize=(32, 10), constrained_layout=True)
    gs = fig.add_gridspec(3, 2)

    # 1. Tension Distribution (Histogram)
    ax_hist = fig.add_subplot(gs[0, 0])
    ax_hist.hist(df["tension"].dropna(), bins=20, color="skyblue", edgecolor="black")
    ax_hist.set_title("Tension Distribution")
    ax_hist.set_xlabel("Tension (N)")
    ax_hist.set_ylabel("Count")

    # 2. Tension vs Confidence
    ax_conf = fig.add_subplot(gs[0, 1])
    ax_conf.scatter(df["confidence"], df["tension"], alpha=0.5)
    ax_conf.set_title("Tension vs Confidence")
    ax_conf.set_xlabel("Confidence")
    ax_conf.set_ylabel("Tension (N)")

    # 3. Tension vs Amplitude
    ax_amp = fig.add_subplot(gs[1, 0])
    ax_amp.scatter(df["amplitude"], df["tension"], alpha=0.5, color="orange")
    ax_amp.set_title("Tension vs Amplitude")
    ax_amp.set_xlabel("Amplitude (RMS)")
    ax_amp.set_ylabel("Tension (N)")

    # 4. Tension vs Harmonicity
    ax_harm = fig.add_subplot(gs[1, 1])
    ax_harm.scatter(df["harmonicity"], df["tension"], alpha=0.5, color="green")
    ax_harm.set_title("Tension vs Harmonicity")
    ax_harm.set_xlabel("Harmonicity (r_value)")
    ax_harm.set_ylabel("Tension (N)")

    # 5. Tension vs Wire Number (to see spatial trends if any)
    ax_wire = fig.add_subplot(gs[2, :])
    ax_wire.scatter(
        df["wire_number"], df["tension"], alpha=0.5, c=df["confidence"], cmap="viridis"
    )
    ax_wire.set_title("Tension vs Wire Number (Colored by Confidence)")
    ax_wire.set_xlabel("Wire Number")
    ax_wire.set_ylabel("Tension (N)")

    return jsonify({"status": "success", "image": figure_to_base64(fig)})


@app.route("/experiment/measure", methods=["POST"])
def measure_wire():
    import logging

    logger = logging.getLogger(__name__)

    data = request.get_json()

    wire_number = int(data.get("wire_number"))
    zone = int(data.get("zone", 1))
    apa_name = data.get("apa_name", "TEST_APA")
    layer = data.get("layer", "U")
    side = data.get("side", "A")
    capos_on_combs = data.get("capos_on_combs", [])  # List of ints 1-4
    confidence_threshold = float(data.get("confidence_threshold", 2.0))
    sweeping_wiggle = bool(data.get("sweeping_wiggle", True))
    sweeping_wiggle_span_mm = float(data.get("sweeping_wiggle_span_mm", 1.0))

    logger.info(
        f"measure_wire: wire={wire_number}, zone={zone}, layer={layer}, side={side}"
    )

    # Calculate capo_left/capo_right
    capo_left = False
    capo_right = False
    if zone > 1 and (zone - 1) in capos_on_combs:
        capo_left = True
    if zone < 5 and zone in capos_on_combs:
        capo_right = True

    # Metadata for this specific measurement
    metadata = ExperimentMetadata(
        experiment_id=data.get("experiment_id", "manual"),
        experiment_name=data.get("experiment_name", "Manual"),
        experiment_type=data.get("experiment_type", "manual"),
        known_tension=data.get("known_tension"),
        zone=zone,
        capos_on_combs=",".join(map(str, capos_on_combs)),
        capo_left=capo_left,
        capo_right=capo_right,
        notes=data.get("notes", ""),
    )

    repo = ExperimentResultRepository(EXPERIMENT_DB_PATH, metadata)

    try:
        options = resolve_runtime_options()
        runtime = build_runtime_bundle(options)
        logger.info("Runtime bundle built successfully")
    except Exception as e:
        logger.error(f"Failed to build runtime bundle: {e}")
        return jsonify(
            {"status": "error", "message": f"Failed to build runtime: {e}"}
        ), 500

    # Override repository factory and wire position provider
    runtime = type(runtime)(
        motion=runtime.motion,
        audio=runtime.audio,
        servo_controller=runtime.servo_controller,
        valve_controller=runtime.valve_controller,
        strum=runtime.strum,
        repository_factory=lambda _: repo,
        wire_position_provider=runtime.wire_position_provider,
    )

    try:
        tm = build_tensiometer(
            apa_name=apa_name,
            layer=layer,
            side=side,
            runtime_bundle=runtime,
            samples_per_wire=data.get("samples_per_wire", 1),
            confidence_threshold=confidence_threshold,
            sweeping_wiggle=sweeping_wiggle,
            sweeping_wiggle_span_mm=sweeping_wiggle_span_mm,
        )
        logger.info(f"Tensiometer built successfully with config: {tm.config}")
    except Exception as e:
        logger.error(f"Failed to build tensiometer: {e}")
        return jsonify(
            {"status": "error", "message": f"Failed to build tensiometer: {e}"}
        ), 500

    # Set audio callback
    tm.audio_sample_callback = state.audio_callback

    result = None
    with repo.run_scope():
        # Figure out where to measure
        assert runtime.wire_position_provider is not None
        pose = runtime.wire_position_provider.get_pose_for_zone(
            tm.config,
            wire_number,
            zone,
            current_focus_position=data.get("focus_position"),
        )

        if pose:
            result = tm.goto_collect_wire_data(
                wire_number=wire_number,
                wire_x=pose.x,
                wire_y=pose.y,
                focus_position=pose.focus_position,
                zone=zone,
            )
        else:
            return jsonify(
                {
                    "status": "impossible",
                    "message": f"Wire {wire_number} in zone {zone} is impossible",
                }
            ), 400

    if result:
        return jsonify(
            {
                "status": "success",
                "tension": result.tension,
                "frequency": result.frequency,
                "confidence": result.confidence,
                "x": result.x,
                "y": result.y,
                "focus_position": result.focus_position,
                "zone": zone,
            }
        )
    else:
        return jsonify({"status": "failed"}), 500


@app.route("/experiment/collect_raw", methods=["POST"])
def collect_raw():
    data = request.get_json()

    wire_number = int(data.get("wire_number"))
    zone = int(data.get("zone", 1))
    apa_name = data.get("apa_name", "TEST_APA")
    layer = data.get("layer", "U")
    side = data.get("side", "A")
    samples_to_collect = int(data.get("samples_per_wire", 10))
    record_duration = float(data.get("record_duration", 0.5))

    experiment_id = data.get("experiment_id", str(uuid.uuid4()))

    metadata = ExperimentMetadata(
        experiment_id=experiment_id,
        experiment_name=data.get("experiment_name", "Raw Collection"),
        experiment_type="raw_collection",
        zone=zone,
        notes=f"Raw collection of {samples_to_collect} samples",
    )

    repo = ExperimentResultRepository(EXPERIMENT_DB_PATH, metadata)
    options = resolve_runtime_options()
    runtime = build_runtime_bundle(options)

    tm = build_tensiometer(
        apa_name=apa_name,
        layer=layer,
        side=side,
        runtime_bundle=runtime,
    )

    results = []
    with repo.run_scope():
        assert runtime.wire_position_provider is not None
        pose = runtime.wire_position_provider.get_pose_for_zone(
            tm.config,
            wire_number,
            zone,
            current_focus_position=data.get("focus_position"),
        )
        if not pose:
            return jsonify({"status": "impossible"}), 400

        tm.goto_xy_func(pose.x, pose.y)

        from spectrum_analysis.pitch_compare_config import PitchCompareConfig
        from spectrum_analysis.audio_processing import acquire_audio
        from dune_tension.geometry import length_lookup
        from dune_tension.tension_calculation import wire_equation

        length = length_lookup(layer, wire_number, zone)
        expected_frequency = wire_equation(length=length)["frequency"]

        cfg = PitchCompareConfig(
            sample_rate=tm.samplerate,
            noise_duration=record_duration,
            input_mode="mic" if not options.spoof_audio else "file",
            expected_f0=expected_frequency,
        )

        for i in range(samples_to_collect):
            tm.strum_func()
            audio_sample = acquire_audio(cfg, noise_rms=tm.noise_threshold / 3)

            if audio_sample is not None:
                audio_filename = f"{experiment_id}_{i}.npz"
                audio_save_path = RAW_AUDIO_DIR / audio_filename
                np.savez_compressed(
                    audio_save_path, audio=audio_sample, samplerate=tm.samplerate
                )

                analysis, frequency, confidence = tm._estimate_sample_pitch(
                    audio_sample, None
                )
                state.audio_callback(audio_sample, tm.samplerate, analysis)

                res = TensionResult.from_measurement(
                    apa_name=apa_name,
                    layer=layer,
                    side=side,
                    wire_number=wire_number,
                    frequency=frequency,
                    confidence=confidence,
                    x=pose.x,
                    y=pose.y,
                    time=datetime.now(),
                    zone=zone,
                )
                repo.metadata.raw_audio_path = str(audio_save_path)
                repo.append_sample(res)

                results.append(
                    {
                        "sample_index": i,
                        "frequency": res.frequency,
                        "tension": res.tension,
                        "confidence": res.confidence,
                    }
                )

    return jsonify(
        {"status": "success", "samples": results, "experiment_id": experiment_id}
    )


@app.route("/experiment/reanalyze", methods=["POST"])
def reanalyze():
    data = request.get_json()
    experiment_id = data.get("experiment_id")
    confidence_threshold = float(data.get("confidence_threshold", 0.7))

    import sqlite3

    conn = sqlite3.connect(EXPERIMENT_DB_PATH)
    query = "SELECT raw_audio_path, wire_number, layer, zone FROM tension_samples WHERE experiment_id = ?"
    df = pd.read_sql_query(query, conn, params=(experiment_id,))
    conn.close()

    if df.empty:
        return jsonify({"status": "no_data"}), 404

    passing_samples = []
    for _, row in df.iterrows():
        path = row["raw_audio_path"]
        if not path or not os.path.exists(path):
            continue

        with np.load(path) as loaded:
            audio = loaded["audio"]
            sr = loaded["samplerate"]

        from spectrum_analysis.pesto_analysis import estimate_pitch_from_audio
        from dune_tension.geometry import length_lookup
        from dune_tension.tension_calculation import wire_equation

        freq, conf = estimate_pitch_from_audio(audio, int(sr), expected_frequency=None)

        if conf >= confidence_threshold:
            length = length_lookup(
                row["layer"], int(row["wire_number"]), int(row["zone"])
            )
            tension = wire_equation(length, freq)["tension"]
            passing_samples.append(
                {
                    "path": path,
                    "frequency": float(freq),
                    "confidence": float(conf),
                    "tension": float(tension),
                }
            )

    return jsonify(
        {
            "status": "success",
            "confidence_threshold": confidence_threshold,
            "passing_count": len(passing_samples),
            "total_count": len(df),
            "passing_samples": passing_samples,
        }
    )


if __name__ == "__main__":
    app.run(port=5001, debug=True)
