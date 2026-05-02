<script lang="ts">
    import { initializeTensiometer, startAutoMeasurement, type TensiometerInitRequest } from './api';

    let apaName = 'APA1';
    let layer = 'U';
    let side = 'A';
    let spoof = true;
    let spoofMovement = true;

    let loading = false;
    let error = '';
    let message = '';

    async function handleInitialize() {
        loading = true;
        error = '';
        message = '';
        try {
            const req: TensiometerInitRequest = {
                apa_name: apaName,
                layer,
                side,
                spoof,
                spoof_movement: spoofMovement
            };
            const res = await initializeTensiometer(req);
            message = res.message;
        } catch (e: any) {
            error = e.message;
        } finally {
            loading = false;
        }
    }

    async function handleStartMeasure() {
        loading = true;
        error = '';
        try {
            await startAutoMeasurement();
            message = 'Measurement started';
        } catch (e: any) {
            error = e.message;
        } finally {
            loading = false;
        }
    }
</script>

<div class="bg-white p-6 rounded-lg shadow-md">
    <h2 class="text-xl font-bold mb-4 text-gray-800 border-b pb-2">Control Panel</h2>
    
    <div class="grid grid-cols-1 gap-4">
        <div>
            <label class="block text-sm font-medium text-gray-700">APA Name</label>
            <input type="text" bind:value={apaName} class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2" />
        </div>
        
        <div class="grid grid-cols-2 gap-4">
            <div>
                <label class="block text-sm font-medium text-gray-700">Layer</label>
                <select bind:value={layer} class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2">
                    <option value="U">U</option>
                    <option value="V">V</option>
                    <option value="X">X</option>
                    <option value="G">G</option>
                </select>
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700">Side</label>
                <select bind:value={side} class="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm border p-2">
                    <option value="A">A</option>
                    <option value="B">B</option>
                </select>
            </div>
        </div>

        <div class="flex items-center space-x-4">
            <label class="inline-flex items-center">
                <input type="checkbox" bind:checked={spoof} class="rounded border-gray-300 text-indigo-600 shadow-sm focus:border-indigo-500 focus:ring-indigo-500" />
                <span class="ml-2 text-sm text-gray-600">Spoof Audio</span>
            </label>
            <label class="inline-flex items-center">
                <input type="checkbox" bind:checked={spoofMovement} class="rounded border-gray-300 text-indigo-600 shadow-sm focus:border-indigo-500 focus:ring-indigo-500" />
                <span class="ml-2 text-sm text-gray-600">Spoof Motion</span>
            </label>
        </div>

        <div class="flex space-x-2 pt-4">
            <button 
                on:click={handleInitialize} 
                disabled={loading}
                class="flex-1 bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:opacity-50 font-semibold"
            >
                Initialize
            </button>
            <button 
                on:click={handleStartMeasure} 
                disabled={loading}
                class="flex-1 bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 disabled:opacity-50 font-semibold"
            >
                Start Auto
            </button>
        </div>

        {#if error}
            <p class="text-red-600 text-sm mt-2">{error}</p>
        {/if}
        {#if message}
            <p class="text-blue-600 text-sm mt-2">{message}</p>
        {/if}
    </div>
</div>
