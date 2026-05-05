<script lang="ts">
    import type { TelemetryData } from '../lib/api';

    export let telemetry: TelemetryData | null = null;
</script>

<div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md border border-gray-200 dark:border-gray-700 h-full">
    <h2 class="text-xl font-semibold mb-4 text-gray-900 dark:text-white">Status Panel</h2>

    {#if telemetry}
        <div class="grid grid-cols-2 gap-6">
            <div class="space-y-4">
                <div>
                    <span class="text-sm text-gray-500 dark:text-gray-400 block uppercase tracking-wider font-bold">State</span>
                    <span class={`text-lg font-mono ${telemetry.is_running ? 'text-green-500' : 'text-yellow-500'}`}>
                        {telemetry.is_running ? 'RUNNING' : 'IDLE'}
                    </span>
                </div>
                <div>
                    <span class="text-sm text-gray-500 dark:text-gray-400 block uppercase tracking-wider font-bold">Active Wire</span>
                    <span class="text-2xl font-mono text-gray-900 dark:text-white">
                        {telemetry.active_wire ?? '--'}
                    </span>
                </div>
                <div>
                    <span class="text-sm text-gray-500 dark:text-gray-400 block uppercase tracking-wider font-bold">Progress</span>
                    <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4 mt-2">
                        <div class="bg-indigo-600 h-4 rounded-full transition-all duration-300" style={`width: ${telemetry.progress * 100}%`}></div>
                    </div>
                    <span class="text-xs text-gray-500 mt-1 block">{(telemetry.progress * 100).toFixed(1)}%</span>
                </div>
            </div>

            <div class="space-y-4">
                <div>
                    <span class="text-sm text-gray-500 dark:text-gray-400 block uppercase tracking-wider font-bold">Position (mm)</span>
                    <div class="grid grid-cols-2 gap-2 text-lg font-mono text-gray-900 dark:text-white">
                        <div>X: {telemetry.position.x.toFixed(2)}</div>
                        <div>Y: {telemetry.position.y.toFixed(2)}</div>
                    </div>
                </div>
                <div>
                    <span class="text-sm text-gray-500 dark:text-gray-400 block uppercase tracking-wider font-bold">Focus</span>
                    <span class="text-lg font-mono text-gray-900 dark:text-white">
                        {telemetry.position.focus.toFixed(0)}
                    </span>
                </div>
                {#if telemetry.last_audio_analysis}
                    <div>
                        <span class="text-sm text-gray-500 dark:text-gray-400 block uppercase tracking-wider font-bold">Last Analysis</span>
                        <div class="text-sm font-mono text-gray-900 dark:text-white">
                            {telemetry.last_audio_analysis.frequency?.toFixed(2)} Hz 
                            ({(telemetry.last_audio_analysis.confidence ?? 0).toFixed(2)})
                        </div>
                    </div>
                {/if}
            </div>
        </div>
    {:else}
        <div class="flex items-center justify-center h-48 text-gray-400 italic">
            Waiting for telemetry...
        </div>
    {/if}
</div>
