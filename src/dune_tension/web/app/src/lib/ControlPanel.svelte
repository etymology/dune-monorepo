<script lang="ts">
    import { ApiClient } from '../lib/api';

    let apa_name = "UK-APA-1";
    let layer = "X";
    let side = "A";
    let spoof = true;
    let spoof_movement = true;

    let initializing = false;
    let message = "";

    async function handleInitialize() {
        initializing = true;
        message = "Initializing...";
        try {
            const res = await ApiClient.initialize({ apa_name, layer, side, spoof, spoof_movement });
            message = res.message;
        } catch (e: any) {
            message = `Error: ${e.message}`;
        } finally {
            initializing = false;
        }
    }

    async function handleStart() {
        try {
            await ApiClient.startAuto();
        } catch (e: any) {
            message = `Error: ${e.message}`;
        }
    }

    async function handleStop() {
        try {
            await ApiClient.stop();
        } catch (e: any) {
            message = `Error: ${e.message}`;
        }
    }
</script>

<div class="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-md border border-gray-200 dark:border-gray-700">
    <h2 class="text-xl font-semibold mb-4 text-gray-900 dark:text-white">Control Panel</h2>
    
    <div class="space-y-4">
        <div>
            <label for="apa_name" class="block text-sm font-medium text-gray-700 dark:text-gray-300">APA Name</label>
            <input id="apa_name" type="text" bind:value={apa_name} class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white" />
        </div>

        <div class="grid grid-cols-2 gap-4">
            <div>
                <label for="layer" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Layer</label>
                <select id="layer" bind:value={layer} class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                    <option>X</option>
                    <option>U</option>
                    <option>V</option>
                    <option>G</option>
                </select>
            </div>
            <div>
                <label for="side" class="block text-sm font-medium text-gray-700 dark:text-gray-300">Side</label>
                <select id="side" bind:value={side} class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm dark:bg-gray-700 dark:border-gray-600 dark:text-white">
                    <option>A</option>
                    <option>B</option>
                </select>
            </div>
        </div>

        <div class="flex items-center space-x-4">
            <label class="flex items-center">
                <input type="checkbox" bind:checked={spoof} class="rounded border-gray-300 text-indigo-600 shadow-sm focus:ring-indigo-500" />
                <span class="ml-2 text-sm text-gray-600 dark:text-gray-400">Spoof Audio</span>
            </label>
            <label class="flex items-center">
                <input type="checkbox" bind:checked={spoof_movement} class="rounded border-gray-300 text-indigo-600 shadow-sm focus:ring-indigo-500" />
                <span class="ml-2 text-sm text-gray-600 dark:text-gray-400">Spoof Motion</span>
            </label>
        </div>

        <div class="pt-4 space-y-2">
            <button 
                on:click={handleInitialize} 
                disabled={initializing}
                class="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-bold py-2 px-4 rounded disabled:opacity-50 transition-colors"
            >
                Initialize Tensiometer
            </button>
            
            <div class="flex space-x-2">
                <button 
                    on:click={handleStart}
                    class="flex-1 bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded transition-colors"
                >
                    Start Auto
                </button>
                <button 
                    on:click={handleStop}
                    class="flex-1 bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded transition-colors"
                >
                    Stop
                </button>
            </div>
        </div>

        {#if message}
            <p class="text-sm text-gray-500 dark:text-gray-400 mt-2 italic">{message}</p>
        {/if}
    </div>
</div>
