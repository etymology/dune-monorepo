import logging
import threading
import io
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from dune_tension.api.state import state
from dune_tension.tensiometer import build_tensiometer
from dune_tension.summaries import build_summary_plot_figure_for_config
from dune_tension.layer_calibration import (
    get_bottom_pin_options,
    get_laser_offset,
    capture_laser_offset,
    get_calibrated_pin_xy_for_side,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)


class TensiometerInitRequest(BaseModel):
    apa_name: str
    layer: str
    side: str
    spoof: bool = False
    spoof_movement: bool = False


class CaptureOffsetRequest(BaseModel):
    layer: str
    side: str
    pin_name: str


class MoveToPinRequest(BaseModel):
    layer: str
    side: str
    pin_name: str


class JogRequest(BaseModel):
    dx: float = 0.0
    dy: float = 0.0


class TensiometerMeasureListRequest(BaseModel):
    wire_numbers: list[int]


@router.get("/config/apas")
async def get_apa_names():
    from dune_tension.paths import data_path, tension_data_db_path

    apas = set()

    # 1. Query the main SQLite database
    db_path = tension_data_db_path()
    if db_path.exists():
        import sqlite3

        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute("SELECT DISTINCT apa_name FROM tension_data")
                for row in cursor:
                    if row[0]:
                        apas.add(str(row[0]))
        except Exception:
            LOGGER.debug("Could not query tension_data database for APA names")

    # 2. Also scan summary files for any that might not be in the DB yet
    summary_path = data_path("tension_summaries")
    if summary_path.exists():
        for f in summary_path.glob("tension_summary_*.csv"):
            parts = f.stem.split("_")
            if len(parts) >= 3:
                apa = "_".join(parts[2:-1])
                if apa:
                    apas.add(apa)

    return sorted(list(apas))


@router.get("/status")
async def get_status():
    return {
        "is_running": state.is_running,
        "active_wire": state.active_wire,
        "progress": state.progress,
        "is_initialized": state.tensiometer is not None,
        "position": state.position,
        "measurements": state.all_measurements,
    }


@router.post("/initialize")
async def initialize_tensiometer(req: TensiometerInitRequest):
    try:

        def on_audio_sample(sample, samplerate, analysis):
            if analysis:
                import numpy as np

                serializable_analysis = {}
                for k, v in analysis.items():
                    if isinstance(v, np.ndarray):
                        serializable_analysis[k] = v.tolist()
                    else:
                        serializable_analysis[k] = v
                state.update_audio(serializable_analysis)

        def on_wire_preview(wire_number, x, y):
            state.active_wire = wire_number
            # Simple progress estimation if we know the range
            if state.tensiometer and state.tensiometer.config:
                cfg = state.tensiometer.config
                total = cfg.wire_max - cfg.wire_min + 1
                if total > 0:
                    state.progress = (wire_number - cfg.wire_min) / total

        def on_wire_result(result):
            res_dict = {
                "wire_number": int(result.wire_number),
                "frequency": float(result.frequency),
                "tension": float(result.tension),
                "confidence": float(result.confidence),
                "time": str(result.time),
                "x": float(result.x),
                "y": float(result.y),
                "focus_position": result.focus_position,
            }
            state.add_measurement(res_dict)

        t = build_tensiometer(
            apa_name=req.apa_name,
            layer=req.layer,
            side=req.side,
            spoof=req.spoof,
            spoof_movement=req.spoof_movement,
            audio_sample_callback=on_audio_sample,
            wire_preview_callback=on_wire_preview,
            wire_result_callback=on_wire_result,
        )
        state.update_tensiometer(t)
        return {
            "status": "success",
            "message": f"Tensiometer initialized for {req.apa_name} {req.layer} {req.side}",
        }
    except Exception as e:
        LOGGER.exception("Failed to initialize tensiometer")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/measure/clear")
async def clear_measurements():
    state.clear_measurements()
    return {"status": "success"}


@router.post("/measure/list")
async def start_list_measurement(req: TensiometerMeasureListRequest):
    if state.tensiometer is None:
        raise HTTPException(status_code=400, detail="Tensiometer not initialized")

    if state.is_running:
        return {"status": "already_running"}

    def run_measure():
        state.set_running(True)
        try:
            state.tensiometer.measure_list(req.wire_numbers, preserve_order=True)
        except Exception as e:
            LOGGER.error(f"List measurement error: {e}")
        finally:
            state.set_running(False)

    thread = threading.Thread(target=run_measure, daemon=True)
    thread.start()

    return {"status": "started"}


@router.post("/measure/auto")
async def start_auto_measurement():
    if state.tensiometer is None:
        raise HTTPException(status_code=400, detail="Tensiometer not initialized")

    if state.is_running:
        return {"status": "already_running"}

    def run_measure():
        state.set_running(True)
        try:
            state.tensiometer.measure_auto()
        except Exception as e:
            LOGGER.error(f"Measurement error: {e}")
        finally:
            state.set_running(False)

    thread = threading.Thread(target=run_measure, daemon=True)
    thread.start()

    return {"status": "started"}


@router.post("/stop")
async def stop_measurement():
    if state.tensiometer:
        state.tensiometer.stop_event.set()
        return {"status": "stopping"}
    return {"status": "not_initialized"}


@router.get("/summary/plot")
async def get_summary_plot():
    if state.tensiometer is None:
        return Response(status_code=400, content="Tensiometer not initialized")

    try:
        # Generate the plot
        fig = build_summary_plot_figure_for_config(state.tensiometer.config)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)

        return Response(content=buf.read(), media_type="image/png")
    except Exception as e:
        LOGGER.exception("Failed to generate summary plot")
        return Response(status_code=500, content=str(e))


@router.get("/calibration/pins")
async def get_calibration_pins(layer: str, side: str):
    return get_bottom_pin_options(layer, side)


@router.get("/calibration/offset")
async def get_current_offset(side: str):
    return get_laser_offset(side)


@router.post("/calibration/capture")
async def capture_offset(req: CaptureOffsetRequest):
    if state.tensiometer is None:
        raise HTTPException(status_code=400, detail="Tensiometer not initialized")

    try:
        x, y = state.tensiometer.get_current_xy_position()
        focus = state.tensiometer.focus_position_getter()
        entry = capture_laser_offset(
            layer=req.layer,
            side=req.side,
            pin_name=req.pin_name,
            captured_stage_xy=(x, y),
            captured_focus=focus,
        )
        return entry
    except Exception as e:
        LOGGER.exception("Failed to capture offset")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calibration/move-to-pin")
async def move_to_pin(req: MoveToPinRequest):
    if state.tensiometer is None:
        raise HTTPException(status_code=400, detail="Tensiometer not initialized")

    try:
        # Calculate pin XY
        pin_x, pin_y = get_calibrated_pin_xy_for_side(req.layer, req.side, req.pin_name)

        # Apply laser offset
        offset = get_laser_offset(req.side)
        if offset:
            stage_x = pin_x - float(offset["x"])
            stage_y = pin_y - float(offset["y"])
        else:
            stage_x, stage_y = pin_x, pin_y

        state.tensiometer.goto_xy_func(stage_x, stage_y)
        return {"status": "success", "target": {"x": stage_x, "y": stage_y}}
    except Exception as e:
        LOGGER.exception("Failed to move to pin")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/motion/jog")
async def jog_motion(req: JogRequest):
    if state.tensiometer is None:
        raise HTTPException(status_code=400, detail="Tensiometer not initialized")

    try:
        state.tensiometer.motion.increment(req.dx, req.dy)
        return {"status": "success"}
    except Exception as e:
        LOGGER.exception("Failed to jog motion")
        raise HTTPException(status_code=500, detail=str(e))
