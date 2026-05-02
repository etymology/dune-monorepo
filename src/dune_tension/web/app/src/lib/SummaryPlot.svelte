<script lang="ts">
    import { onMount } from 'svelte';

    export let isRunning = false;
    let plotUrl = "";
    let lastUpdate = Date.now();

    function refreshPlot() {
        // Add cache buster
        plotUrl = `http://localhost:8000/api/summary/plot?t=${Date.now()}`;
        lastUpdate = Date.now();
    }

    onMount(() => {
        refreshPlot();
        const interval = setInterval(() => {
            if (isRunning) {
                refreshPlot();
            }
        }, 5000); // Refresh every 5s if running

        return () => clearInterval(interval);
    });

    $: if (!isRunning) {
        // Refresh once when stopped to show final result
        refreshPlot();
    }
</script>

<div class="bg-white dark:bg-gray-800 p-4 rounded-lg shadow-md border border-gray-200 dark:border-gray-700">
    <div class="flex justify-between items-center mb-2">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white">Measurement Summary</h3>
        <button on:click={refreshPlot} class="text-xs bg-gray-200 hover:bg-gray-300 dark:bg-gray-700 dark:hover:bg-gray-600 px-2 py-1 rounded transition-colors">
            Refresh
        </button>
    </div>
    
    <div class="relative min-h-[300px] flex items-center justify-center bg-gray-50 dark:bg-gray-900 rounded border border-dashed border-gray-300 dark:border-gray-700">
        <img src={plotUrl} alt="Summary Plot" class="max-w-full h-auto" on:error={(e) => e.currentTarget.style.display = 'none'} on:load={(e) => e.currentTarget.style.display = 'block'} />
        <div class="absolute inset-0 flex items-center justify-center pointer-events-none text-gray-400 text-sm" style="z-index: -1;">
            Initializing or no data available...
        </div>
    </div>
    <p class="text-[10px] text-gray-500 mt-2 text-right">Last updated: {new Date(lastUpdate).toLocaleTimeString()}</p>
</div>
