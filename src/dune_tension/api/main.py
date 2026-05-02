import asyncio
import json
import logging
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dune_tension.api.routes import router
from dune_tension.api.state import state

app = FastAPI(title="Dune Tension Web Interface")


# Logging Hook
class StateLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            state.append_log(msg)
        except Exception:
            self.handleError(record)


# Configure logging to capture output from all relevant modules
log_handler = StateLogHandler()
log_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
)
logging.getLogger("dune_tension").addHandler(log_handler)
logging.getLogger("spectrum_analysis").addHandler(log_handler)

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket):
    await websocket.accept()
    last_log_index = len(state.logs)
    try:
        while True:
            # Poll position if tensiometer is initialized
            if state.tensiometer:
                try:
                    x, y = state.tensiometer.get_current_xy_position()
                    focus = state.tensiometer.focus_position_getter()
                    state.update_position(x, y, focus)
                except Exception:
                    pass

            # New logs since last broadcast
            new_logs = state.logs[last_log_index:]
            last_log_index = len(state.logs)

            telemetry_data = {
                "active_wire": state.active_wire,
                "progress": state.progress,
                "is_running": state.is_running,
                "position": state.position,
                "last_audio_analysis": state.last_audio_analysis,
                "logs": new_logs,
            }
            await websocket.send_text(json.dumps(telemetry_data))
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass


# Static file serving
static_dir = Path(__file__).parent.parent / "web" / "dist"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
else:
    logging.warning(
        f"Static directory {static_dir} not found. Frontend will not be served."
    )

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
