<script lang="ts">
    import ConfigStep from './lib/steps/ConfigStep.svelte';
    import CalibrationStep from './lib/steps/CalibrationStep.svelte';
    import MeasurementStep from './lib/steps/MeasurementStep.svelte';
    import ReviewStep from './lib/steps/ReviewStep.svelte';

    type Step = 'config' | 'calibration' | 'measurement' | 'review';
    let currentStep: Step = 'config';

    let config = {
        apa_name: '',
        layer: '',
        side: ''
    };

    function handleConfigNext(event: CustomEvent) {
        config = event.detail;
        currentStep = 'calibration';
    }

    function handleCalibrationNext() {
        currentStep = 'measurement';
    }

    function handleMeasurementNext() {
        currentStep = 'review';
    }

    function handleRestart() {
        currentStep = 'config';
    }
</script>

<main class="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100 p-4 md:p-8">
    <div class="max-w-7xl mx-auto space-y-8">
        <header class="flex justify-between items-center pb-6 border-b border-gray-200 dark:border-gray-800">
            <div class="flex items-center space-x-4">
                <div class="bg-blue-600 p-2 rounded-lg">
                    <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>
                </div>
                <div>
                    <h1 class="text-3xl font-extrabold tracking-tight">Dune Tension</h1>
                    <p class="text-sm text-gray-500 font-medium uppercase tracking-widest">Tensiometer Control Interface</p>
                </div>
            </div>

            <!-- Stepper Indicator -->
            <nav class="hidden md:flex items-center space-x-4 text-sm font-medium">
                <span class={currentStep === 'config' ? 'text-blue-600' : 'text-gray-400'}>1. Setup</span>
                <svg class="w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                <span class={currentStep === 'calibration' ? 'text-blue-600' : 'text-gray-400'}>2. Calibrate</span>
                <svg class="w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                <span class={currentStep === 'measurement' ? 'text-blue-600' : 'text-gray-400'}>3. Measure</span>
                <svg class="w-4 h-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                <span class={currentStep === 'review' ? 'text-blue-600' : 'text-gray-400'}>4. Review</span>
            </nav>
        </header>

        <div class="transition-all duration-500 ease-in-out">
            {#if currentStep === 'config'}
                <ConfigStep on:next={handleConfigNext} />
            {:else if currentStep === 'calibration'}
                <CalibrationStep layer={config.layer} side={config.side} on:next={handleCalibrationNext} on:prev={() => currentStep = 'config'} />
            {:else if currentStep === 'measurement'}
                <MeasurementStep layer={config.layer} side={config.side} on:next={handleMeasurementNext} />
            {:else if currentStep === 'review'}
                <ReviewStep layer={config.layer} side={config.side} on:restart={handleRestart} />
            {/if}
        </div>
    </div>
</main>

<style>
    :global(body) {
        margin: 0;
        font-family: 'Inter', system-ui, -apple-system, sans-serif;
    }
</style>
