<script lang="ts">
    import { onMount, createEventDispatcher } from 'svelte';
    import { ApiClient } from '../api';

    const dispatch = createEventDispatcher();

    export let layer: string;
    export let side: string;

    let pins: [string, string][] = [];
    let selectedPin = "";
    let error = "";
    let capturing = false;
    let movingToPin = false;

    onMount(async () => {
        try {
            pins = await ApiClient.getCalibrationPins(layer, side);
            if (pins.length > 0) {
                selectedPin = pins[0][1];
            }
        } catch (e: any) {
            error = "Failed to load calibration pins: " + e.message;
        }
    });

    async function handleJog(dx: number, dy: number) {
        try {
            await ApiClient.jog({ dx, dy });
        } catch (e: any) {
            error = "Jog failed: " + e.message;
        }
    }

    async function handleMoveToPin() {
        movingToPin = true;
        error = "";
        try {
            await ApiClient.moveLaserToPin({ layer, side, pin_name: selectedPin });
        } catch (e: any) {
            error = "Move failed: " + e.message;
        } finally {
            movingToPin = false;
        }
    }

    async function handleCapture() {
        capturing = true;
        error = "";
        try {
            await ApiClient.captureOffset({ layer, side, pin_name: selectedPin });
            dispatch('next');
        } catch (e: any) {
            error = "Capture failed: " + e.message;
        } finally {
            capturing = false;
        }
    }
</script>

<div class="max-w-2xl mx-auto bg-white dark:bg-gray-800 p-8 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-white">2. Laser Offset Calibration</h2>
    
    <p class="text-gray-600 dark:text-gray-400 mb-6">
        Move the laser to a known pin to determine the laser offset. 
        Select the target pin below and use the controls to align the laser precisely.
    </p>

    <div class="space-y-8">
        <div>
            <label for="pin" class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Target Calibration Pin</label>
            <div class="flex space-x-2">
                <select id="pin" bind:value={selectedPin} 
                    class="flex-1 block w-full rounded-lg border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white p-2.5">
                    {#each pins as [label, value]}
                        <option {value}>{label}</option>
                    {/each}
                </select>
                <button 
                    on:click={handleMoveToPin} 
                    disabled={movingToPin || !selectedPin}
                    class="bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold px-4 py-2 rounded-lg disabled:opacity-50 transition-colors whitespace-nowrap"
                >
                    {movingToPin ? 'Moving...' : 'Move Laser to Pin'}
                </button>
            </div>
        </div>

        <div class="flex flex-col items-center space-y-4">
            <span class="text-sm font-semibold text-gray-500 uppercase tracking-wider">Manual Alignment Controls</span>
            <div class="grid grid-cols-3 gap-2">
                <div></div>
                <button on:click={() => handleJog(0, 5)} aria-label="Jog Y+" class="p-4 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 rounded-lg transition-colors">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path></svg>
                </button>
                <div></div>
                
                <button on:click={() => handleJog(-5, 0)} aria-label="Jog X-" class="p-4 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 rounded-lg transition-colors">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path></svg>
                </button>
                <div class="flex items-center justify-center font-bold text-gray-400">JOG</div>
                <button on:click={() => handleJog(5, 0)} aria-label="Jog X+" class="p-4 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 rounded-lg transition-colors">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                </button>

                <div></div>
                <button on:click={() => handleJog(0, -5)} aria-label="Jog Y-" class="p-4 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 rounded-lg transition-colors">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path></svg>
                </button>
                <div></div>
            </div>
            <div class="flex space-x-2">
                <button on:click={() => handleJog(0, 1)} class="px-3 py-1 text-xs bg-gray-200 dark:bg-gray-600 rounded">Fine Y+</button>
                <button on:click={() => handleJog(0, -1)} class="px-3 py-1 text-xs bg-gray-200 dark:bg-gray-600 rounded">Fine Y-</button>
                <button on:click={() => handleJog(-1, 0)} class="px-3 py-1 text-xs bg-gray-200 dark:bg-gray-600 rounded">Fine X-</button>
                <button on:click={() => handleJog(1, 0)} class="px-3 py-1 text-xs bg-gray-200 dark:bg-gray-600 rounded">Fine X+</button>
            </div>
        </div>

        {#if error}
            <div class="p-4 text-sm text-red-800 rounded-lg bg-red-50 dark:bg-gray-800 dark:text-red-400" role="alert">
                {error}
            </div>
        {/if}

        <div class="flex space-x-4">
            <button 
                on:click={() => dispatch('prev')} 
                class="flex-1 py-3 px-5 text-sm font-medium text-gray-900 focus:outline-none bg-white rounded-lg border border-gray-200 hover:bg-gray-100 hover:text-blue-700 focus:z-10 focus:ring-4 focus:ring-gray-100 dark:focus:ring-gray-700 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-600 dark:hover:text-white dark:hover:bg-gray-700"
            >
                Back
            </button>
            <button 
                on:click={handleCapture} 
                disabled={capturing || !selectedPin}
                class="flex-[2] text-white bg-green-600 hover:bg-green-700 focus:ring-4 focus:outline-none focus:ring-green-300 font-bold rounded-lg text-sm px-5 py-3 text-center dark:bg-green-500 dark:hover:bg-green-600 dark:focus:ring-green-800 disabled:opacity-50"
            >
                {capturing ? 'Capturing...' : 'Record Position & Start Measurement'}
            </button>
        </div>
    </div>
</div>
