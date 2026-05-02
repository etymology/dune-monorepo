<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { connectTelemetry, getStatus, type Status } from './api';

    let status: Status = {
        is_running: false,
        active_wire: null,
        progress: 0.0,
        is_initialized: false
    };

    let ws: WebSocket;

    onMount(async () => {
        try {
            status = await getStatus();
        } catch (e) {
            console.error("Failed to get initial status", e);
        }

        ws = connectTelemetry((data) => {
            status = { ...status, ...data };
        });
    });

    onDestroy(() => {
        if (ws) ws.close();
    });
</script>

<div class="bg-white p-6 rounded-lg shadow-md">
    <h2 class="text-xl font-bold mb-4 text-gray-800 border-b pb-2">Status</h2>
    
    <div class="grid grid-cols-2 gap-4">
        <div class="p-3 bg-gray-50 rounded border">
            <span class="block text-xs font-semibold text-gray-500 uppercase">State</span>
            <span class="text-lg font-mono {status.is_running ? 'text-green-600' : 'text-gray-600'}">
                {status.is_running ? 'RUNNING' : 'IDLE'}
            </span>
        </div>
        
        <div class="p-3 bg-gray-50 rounded border">
            <span class="block text-xs font-semibold text-gray-500 uppercase">Initialized</span>
            <span class="text-lg font-mono {status.is_initialized ? 'text-blue-600' : 'text-red-600'}">
                {status.is_initialized ? 'YES' : 'NO'}
            </span>
        </div>

        <div class="p-3 bg-gray-50 rounded border">
            <span class="block text-xs font-semibold text-gray-500 uppercase">Active Wire</span>
            <span class="text-lg font-mono text-indigo-700">
                {status.active_wire !== null ? status.active_wire : '---'}
            </span>
        </div>

        <div class="p-3 bg-gray-50 rounded border">
            <span class="block text-xs font-semibold text-gray-500 uppercase">Progress</span>
            <span class="text-lg font-mono text-indigo-700">
                {(status.progress * 100).toFixed(1)}%
            </span>
        </div>
    </div>

    <div class="mt-4 w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
        <div class="bg-indigo-600 h-2.5 rounded-full transition-all duration-500" style="width: {status.progress * 100}%"></div>
    </div>
</div>
