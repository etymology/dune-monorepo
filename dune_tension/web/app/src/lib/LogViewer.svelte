<script lang="ts">
    import { onMount, afterUpdate } from 'svelte';

    export let logs: string[] = [
        "System ready...",
        "Waiting for initialization..."
    ];

    let logContainer: HTMLElement;

    function scrollToBottom() {
        if (logContainer) {
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }

    onMount(scrollToBottom);
    afterUpdate(scrollToBottom);
</script>

<div class="bg-gray-900 p-4 rounded-lg shadow-inner h-64 flex flex-col">
    <h2 class="text-sm font-bold mb-2 text-gray-400 uppercase tracking-wider">Console Logs</h2>
    <div 
        bind:this={logContainer}
        class="flex-1 overflow-y-auto font-mono text-xs text-green-400 space-y-1 scrollbar-thin scrollbar-thumb-gray-700"
    >
        {#each logs as log}
            <div class="border-l-2 border-green-800 pl-2">
                <span class="text-gray-600 mr-2">[{new Date().toLocaleTimeString()}]</span>
                {log}
            </div>
        {/each}
    </div>
</div>
