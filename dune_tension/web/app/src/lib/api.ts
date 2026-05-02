export interface Status {
    is_running: boolean;
    active_wire: number | null;
    progress: number;
    is_initialized: boolean;
}

export interface TensiometerInitRequest {
    apa_name: string;
    layer: string;
    side: string;
    spoof: boolean;
    spoof_movement: boolean;
}

const API_BASE = "/api";

export async function getStatus(): Promise<Status> {
    const res = await fetch(`${API_BASE}/status`);
    if (!res.ok) throw new Error("Failed to fetch status");
    return res.json();
}

export async function initializeTensiometer(req: TensiometerInitRequest): Promise<any> {
    const res = await fetch(`${API_BASE}/initialize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
    });
    if (!res.ok) throw new Error("Failed to initialize tensiometer");
    return res.json();
}

export async function startAutoMeasurement(): Promise<any> {
    const res = await fetch(`${API_BASE}/measure/auto`, { method: "POST" });
    if (!res.ok) throw new Error("Failed to start auto measurement");
    return res.json();
}

export function connectTelemetry(onMessage: (data: any) => void): WebSocket {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const ws = new WebSocket(`${protocol}//${host}/ws/telemetry`);
    ws.onmessage = (event) => {
        onMessage(JSON.parse(event.data));
    };
    return ws;
}
