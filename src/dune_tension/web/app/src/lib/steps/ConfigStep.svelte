<script lang="ts">
    import { onMount, createEventDispatcher } from 'svelte';
    import { ApiClient } from '../api';

    const dispatch = createEventDispatcher();

    let apa_name = "";
    let existingApas: string[] = [];
    let layer = "X";
    let side = "A";
    let spoof = true;
    let spoof_movement = true;

    let initializing = false;
    let error = "";
    let isCreatingNew = false;

    onMount(async () => {
        try {
            existingApas = await ApiClient.getApaNames();
            if (existingApas.length > 0) {
                apa_name = existingApas[0];
            } else {
                isCreatingNew = true;
            }
        } catch (e: any) {
            console.error("Failed to load APA names", e);
        }
    });

    async function handleNext() {
        if (!apa_name) {
            error = "Please select or enter an APA name.";
            return;
        }
        initializing = true;
        error = "";
        try {
            const res = await ApiClient.initialize({ apa_name, layer, side, spoof, spoof_movement });
            if (res.status === "success") {
                dispatch('next', { apa_name, layer, side });
            } else {
                error = res.message || "Failed to initialize";
            }
        } catch (e: any) {
            error = e.message;
        } finally {
            initializing = false;
        }
    }
</script>

<div class="max-w-md mx-auto bg-white dark:bg-gray-800 p-8 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">
    <h2 class="text-2xl font-bold mb-6 text-gray-900 dark:text-white text-center">1. Setup Configuration</h2>
    
    <div class="space-y-6">
        <div>
            <div class="flex justify-between items-center mb-2">
                <label for="apa_name" class="block text-sm font-semibold text-gray-700 dark:text-gray-300">APA Name</label>
                <button on:click={() => { isCreatingNew = !isCreatingNew; if(isCreatingNew) apa_name = ""; }} 
                    class="text-xs text-blue-600 dark:text-blue-400 hover:underline font-medium">
                    {isCreatingNew ? 'Select Existing' : 'Create New'}
                </button>
            </div>
            
            {#if isCreatingNew}
                <input id="apa_name" type="text" bind:value={apa_name}
                    class="block w-full rounded-lg border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white p-2.5 focus:ring-blue-500 focus:border-blue-500" 
                    placeholder="Enter new APA name" />
            {:else}
                <select id="apa_name" bind:value={apa_name} 
                    class="block w-full rounded-lg border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white p-2.5">
                    {#each existingApas as apa}
                        <option value={apa}>{apa}</option>
                    {/each}
                </select>
            {/if}
        </div>

        <div class="grid grid-cols-2 gap-6">
            <div>
                <label for="layer" class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Layer</label>
                <select id="layer" bind:value={layer} 
                    class="block w-full rounded-lg border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white p-2.5">
                    <option>X</option>
                    <option>U</option>
                    <option>V</option>
                    <option>G</option>
                </select>
            </div>
            <div>
                <label for="side" class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Side</label>
                <select id="side" bind:value={side} 
                    class="block w-full rounded-lg border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-900 dark:text-white p-2.5">
                    <option>A</option>
                    <option>B</option>
                </select>
            </div>
        </div>

        <div class="flex items-center space-x-6 py-2 border-t border-gray-100 dark:border-gray-700 pt-4">
            <label class="inline-flex items-center cursor-pointer">
                <input type="checkbox" bind:checked={spoof} class="sr-only peer" />
                <div class="relative w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                <span class="ms-3 text-sm font-medium text-gray-700 dark:text-gray-300">Spoof Audio</span>
            </label>
            <label class="inline-flex items-center cursor-pointer">
                <input type="checkbox" bind:checked={spoof_movement} class="sr-only peer" />
                <div class="relative w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                <span class="ms-3 text-sm font-medium text-gray-700 dark:text-gray-300">Spoof Motion</span>
            </label>
        </div>

        {#if error}
            <div class="p-4 text-sm text-red-800 rounded-lg bg-red-50 dark:bg-gray-800 dark:text-red-400 border border-red-100 dark:border-red-900" role="alert">
                <span class="font-bold">Initialization Failed:</span> {error}
            </div>
        {/if}

        <button 
            on:click={handleNext} 
            disabled={initializing}
            class="w-full text-white bg-blue-700 hover:bg-blue-800 focus:ring-4 focus:outline-none focus:ring-blue-300 font-bold rounded-lg text-sm px-5 py-3 text-center dark:bg-blue-600 dark:hover:bg-blue-700 dark:focus:ring-blue-800 disabled:opacity-50 transition-all shadow-md"
        >
            {initializing ? 'Connecting to Tensiometer...' : 'Continue to Calibration'}
        </button>
    </div>
</div>
