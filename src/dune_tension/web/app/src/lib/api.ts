export interface TelemetryData {
    active_wire: number | null;
    progress: number;
    is_running: boolean;
    position: { x: number; y: number; focus: number };
    last_audio_analysis: any | null;
    logs: string[];
    measurements: any[];
}

export interface TensiometerStatus {
    is_running: boolean;
    active_wire: number | null;
    progress: number;
    is_initialized: boolean;
    position: { x: number; y: number; focus: number };
    measurements: any[];
}

const API_BASE = import.meta.env.VITE_API_BASE || '';
const WS_BASE = import.meta.env.VITE_WS_BASE || (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host;

export class ApiClient {
    static async getStatus(): Promise<TensiometerStatus> {
        const res = await fetch(`${API_BASE}/api/status`);
        return res.json();
    }

    static async getApaNames(): Promise<string[]> {
        const res = await fetch(`${API_BASE}/api/config/apas`);
        return res.json();
    }

    static async initialize(params: { apa_name: string; layer: string; side: string; spoof: boolean; spoof_movement: boolean }) {
        const res = await fetch(`${API_BASE}/api/initialize`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        return res.json();
    }

    static async getCalibrationPins(layer: string, side: string): Promise<[string, string][]> {
        const res = await fetch(`${API_BASE}/api/calibration/pins?layer=${layer}&side=${side}`);
        return res.json();
    }

    static async getLaserOffset(side: string) {
        const res = await fetch(`${API_BASE}/api/calibration/offset?side=${side}`);
        return res.json();
    }

    static async captureOffset(params: { layer: string; side: string; pin_name: string }) {
        const res = await fetch(`${API_BASE}/api/calibration/capture`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        return res.json();
    }

    static async moveLaserToPin(params: { layer: string; side: string; pin_name: string }) {
        const res = await fetch(`${API_BASE}/api/calibration/move-to-pin`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        return res.json();
    }

    static async jog(params: { dx: number; dy: number }) {
        const res = await fetch(`${API_BASE}/api/motion/jog`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(params)
        });
        return res.json();
    }

    static async startAuto() {
        const res = await fetch(`${API_BASE}/api/measure/auto`, { method: 'POST' });
        return res.json();
    }

    static async measureList(wire_numbers: number[]) {
        const res = await fetch(`${API_BASE}/api/measure/list`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ wire_numbers })
        });
        return res.json();
    }

    static async clearMeasurements() {
        const res = await fetch(`${API_BASE}/api/measure/clear`, { method: 'POST' });
        return res.json();
    }

    static async stop() {
        const res = await fetch(`${API_BASE}/api/stop`, { method: 'POST' });
        return res.json();
    }

    static subscribeTelemetry(callback: (data: TelemetryData) => void): () => void {
        const socket = new WebSocket(`${WS_BASE}/ws/telemetry`);
        
        socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            callback(data);
        };

        socket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };

        return () => {
            socket.close();
        };
    }
}
