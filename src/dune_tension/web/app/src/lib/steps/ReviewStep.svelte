<script lang="ts">
    import { onMount, onDestroy, createEventDispatcher } from 'svelte';
    import { ApiClient, type TelemetryData } from '../api';
    import InteractivePlot from '../InteractivePlot.svelte';

    const dispatch = createEventDispatcher();

    export let layer: string;
    export let side: string;

    let telemetry: TelemetryData | null = null;
    let measurements: any[] = [];
    let selectedWires: number[] = [];
    let remeasuring = false;
    let error = "";
    let selectionMode = true; // Default to selection mode in review

    let unsubscribe: () => void;

    onMount(async () => {
        const status = await ApiClient.getStatus();
        measurements = status.measurements || [];

        unsubscribe = ApiClient.subscribeTelemetry((data) => {
            telemetry = data;
            if (data.measurements) {
                measurements = data.measurements;
            }
        });
    });

    onDestroy(() => {
        if (unsubscribe) unsubscribe();
    });

    function handleSelection(event: CustomEvent<number[]>) {
        // Merge with existing selection, ensuring unique wire numbers
        const newSelection = event.detail;
        selectedWires = Array.from(new Set([...selectedWires, ...newSelection]));
    }

    function clearSelection() {
        selectedWires = [];
    }

    async function handleRemeasure() {
        if (selectedWires.length === 0) return;
        
        remeasuring = true;
        error = "";
        try {
            await ApiClient.measureList(selectedWires);
        } catch (e: any) {
            error = e.message;
            remeasuring = false;
        }
    }

    async function handleStop() {
        try {
            await ApiClient.stop();
        } catch (e: any) {
            error = e.message;
        }
    }

    $: if (telemetry && !telemetry.is_running && remeasuring) {
        remeasuring = false;
        selectedWires = []; 
    }
</script>

<div class="space-y-8">
    <div class="flex justify-between items-center bg-white dark:bg-gray-800 p-6 rounded-xl shadow-md border border-gray-200 dark:border-gray-700">
        <div class="space-y-1">
            <h2 class="text-2xl font-bold text-gray-900 dark:text-white">4. Review & Remeasure</h2>
            <p class="text-sm text-gray-500">Analyze recorded tensions and select outliers for targeted remeasurement.</p>
        </div>
        
        <div class="flex items-center space-x-4">
            {#if telemetry?.is_running}
                <div class="flex items-center space-x-2 mr-4">
                    <span class="flex h-3 w-3 relative">
                        <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75"></span>
                        <span class="relative inline-flex rounded-full h-3 w-3 bg-orange-500"></span>
                    </span>
                    <span class="text-sm font-medium text-orange-600">Remeasuring...</span>
                </div>
                <button on:click={handleStop} class="bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-6 rounded-lg transition-colors shadow-sm">
                    Stop
                </button>
            {:else}
                <button 
                    on:click={handleRemeasure} 
                    disabled={selectedWires.length === 0}
                    class="bg-orange-600 hover:bg-orange-700 text-white font-bold py-2 px-6 rounded-lg transition-colors disabled:opacity-50 shadow-sm"
                >
                    Remeasure {selectedWires.length > 0 ? selectedWires.length : ''} Selected
                </button>
                <button on:click={() => dispatch('restart')} class="bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-900 dark:text-white font-bold py-2 px-6 rounded-lg transition-colors shadow-sm">
                    Start New APA
                </button>
            {/if}
        </div>
    </div>

    {#if error}
        <div class="p-4 text-sm text-red-800 rounded-lg bg-red-50 dark:bg-gray-800 dark:text-red-400 border border-red-100" role="alert">
            {error}
        </div>
    {/if}

    <div class="space-y-6">
        <div class="relative">
            <div class="absolute top-4 right-16 z-10">
                <div class="inline-flex rounded-md shadow-sm" role="group">
                    <button type="button" on:click={() => selectionMode = false} 
                        class={`px-4 py-2 text-xs font-medium rounded-s-lg border ${!selectionMode ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-900 border-gray-200 hover:bg-gray-100 dark:bg-gray-700 dark:text-white dark:border-gray-600 dark:hover:bg-gray-600'}`}>
                        Zoom/Pan
                    </button>
                    <button type="button" on:click={() => selectionMode = true} 
                        class={`px-4 py-2 text-xs font-medium rounded-e-lg border ${selectionMode ? 'bg-orange-600 text-white border-orange-600' : 'bg-white text-gray-900 border-gray-200 hover:bg-gray-100 dark:bg-gray-700 dark:text-white dark:border-gray-600 dark:hover:bg-gray-600'}`}>
                        Select Area
                    </button>
                </div>
            </div>
            <InteractivePlot {measurements} title={`Recorded Tensions: ${layer} Layer - Side ${side}`} {selectionMode} on:select={handleSelection} />
        </div>
        
        {#if selectedWires.length > 0}
            <div class="bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">
                <div class="flex justify-between items-center mb-6">
                    <h3 class="text-sm font-bold text-gray-500 uppercase tracking-widest">Remeasurement Queue ({selectedWires.length} wires)</h3>
                    <button on:click={clearSelection} class="text-xs text-red-600 hover:underline">Clear All</button>
                </div>
                <div class="flex flex-wrap gap-2 max-h-48 overflow-y-auto p-1">
                    {#each selectedWires as wire}
                        <div class="flex items-center space-x-1 px-3 py-1.5 bg-orange-100 dark:bg-orange-900/40 text-orange-800 dark:text-orange-200 text-xs font-bold rounded-full border border-orange-200 dark:border-orange-800">
                            <span>#{wire}</span>
                            <button on:click={() => selectedWires = selectedWires.filter(w => w !== wire)} 
                                aria-label={`Remove wire ${wire} from queue`}
                                class="ml-1 text-orange-400 hover:text-orange-600">
                                <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"></path></svg>
                            </button>
                        </div>
                    {/each}
                </div>
            </div>
        {/if}
    </div>
</div>
