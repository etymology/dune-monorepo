<script lang="ts">
    import { onMount, onDestroy, createEventDispatcher } from 'svelte';
    import { ApiClient, type TelemetryData } from '../api';
    import InteractivePlot from '../InteractivePlot.svelte';
    import AudioVisualizer from '../AudioVisualizer.svelte';
    import LogViewer from '../LogViewer.svelte';

    const dispatch = createEventDispatcher();

    export let layer: string;
    export let side: string;

    let telemetry: TelemetryData | null = null;
    let measurements: any[] = [];
    let allLogs: string[] = [];
    let error = "";

    let unsubscribe: () => void;

    onMount(() => {
        // Clear any previous measurements if we are starting fresh
        ApiClient.clearMeasurements();

        unsubscribe = ApiClient.subscribeTelemetry((data) => {
            telemetry = data;
            if (data.measurements) {
                measurements = data.measurements;
            }
            if (data.logs && data.logs.length > 0) {
                allLogs = [...allLogs, ...data.logs].slice(-500);
            }
        });
    });

    onDestroy(() => {
        if (unsubscribe) unsubscribe();
    });

    async function handleStart() {
        error = "";
        try {
            await ApiClient.startAuto();
        } catch (e: any) {
            error = e.message;
        }
    }

    async function handleStop() {
        try {
            await ApiClient.stop();
        } catch (e: any) {
            error = e.message;
        }
    }

    $: if (!telemetry?.is_running && measurements.length > 0 && !error) {
        // Option to proceed to review when done
    }
</script>

<div class="space-y-8">
    <div class="flex justify-between items-center bg-white dark:bg-gray-800 p-6 rounded-xl shadow-md border border-gray-200 dark:border-gray-700">
        <div class="space-y-1">
            <h2 class="text-2xl font-bold text-gray-900 dark:text-white">3. Tension Measurement</h2>
            <p class="text-sm text-gray-500">{layer} Layer - Side {side}</p>
        </div>
        
        <div class="flex items-center space-x-4">
            {#if telemetry?.is_running}
                <div class="flex items-center space-x-2 mr-4">
                    <span class="flex h-3 w-3 relative">
                        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
                    </span>
                    <span class="text-sm font-medium text-green-600">Measuring...</span>
                </div>
                <button on:click={handleStop} class="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-6 rounded-lg transition-colors">
                    Stop
                </button>
            {:else}
                <button on:click={handleStart} class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-6 rounded-lg transition-colors">
                    Start Measurement
                </button>
                {#if measurements.length > 0}
                    <button on:click={() => dispatch('next')} class="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-6 rounded-lg transition-colors">
                        Review Results
                    </button>
                {/if}
            {/if}
        </div>
    </div>

    {#if error}
        <div class="p-4 text-sm text-red-800 rounded-lg bg-red-50 dark:bg-gray-800 dark:text-red-400" role="alert">
            {error}
        </div>
    {/if}

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <div class="lg:col-span-2 space-y-6">
            <InteractivePlot {measurements} title={`Tensions: ${layer} Layer - Side ${side}`} />
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="bg-white dark:bg-gray-800 p-4 rounded-xl shadow border border-gray-200 dark:border-gray-700">
                    <AudioVisualizer data={telemetry?.last_audio_analysis?.fft || []} title="FFT Spectrum" color="#3b82f6" />
                </div>
                <div class="bg-white dark:bg-gray-800 p-4 rounded-xl shadow border border-gray-200 dark:border-gray-700">
                    <AudioVisualizer data={telemetry?.last_audio_analysis?.acf || []} title="Autocorrelation (ACF)" color="#10b981" />
                </div>
                <div class="bg-white dark:bg-gray-800 p-4 rounded-xl shadow border border-gray-200 dark:border-gray-700">
                    <AudioVisualizer data={telemetry?.last_audio_analysis?.pesto_activations || []} title="Pesto NN Activations" color="#f59e0b" />
                </div>
            </div>
        </div>

        <div class="lg:col-span-1 space-y-6">
            <div class="bg-white dark:bg-gray-800 p-6 rounded-xl shadow border border-gray-200 dark:border-gray-700">
                <h3 class="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4">Current Progress</h3>
                <div class="space-y-4">
                    <div class="flex justify-between text-sm">
                        <span>Wire Number</span>
                        <span class="font-mono font-bold text-lg">{telemetry?.active_wire ?? '--'}</span>
                    </div>
                    <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4">
                        <div class="bg-blue-600 h-4 rounded-full transition-all duration-300" style={`width: ${(telemetry?.progress ?? 0) * 100}%`}></div>
                    </div>
                    <div class="flex justify-between text-xs text-gray-500">
                        <span>X: {telemetry?.position.x.toFixed(2)}</span>
                        <span>Y: {telemetry?.position.y.toFixed(2)}</span>
                        <span>F: {telemetry?.position.focus.toFixed(0)}</span>
                    </div>
                </div>
            </div>

            <LogViewer logs={allLogs} />
        </div>
    </div>
</div>
