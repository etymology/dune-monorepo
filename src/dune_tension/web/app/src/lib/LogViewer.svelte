<script lang="ts">
    import { onMount, afterUpdate } from 'svelte';

    export let logs: string[] = [];
    let logContainer: HTMLDivElement;

    function scrollToBottom() {
        if (logContainer) {
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }

    onMount(scrollToBottom);
    afterUpdate(scrollToBottom);
</script>

<div class="bg-gray-900 text-green-400 p-4 rounded-lg shadow-inner h-64 overflow-y-auto font-mono text-sm border border-gray-700" bind:this={logContainer}>
    {#each logs as log}
        <div class="mb-1 border-b border-gray-800 pb-1 last:border-0">{log}</div>
    {:else}
        <div class="text-gray-600 italic">No logs yet...</div>
    {/each}
</div>
