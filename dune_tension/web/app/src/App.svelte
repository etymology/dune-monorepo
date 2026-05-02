<script lang="ts">
  import './app.css';
  import ControlPanel from './lib/ControlPanel.svelte';
  import StatusPanel from './lib/StatusPanel.svelte';
  import LogViewer from './lib/LogViewer.svelte';
</script>

<main class="min-h-screen bg-gray-100 p-8 font-sans antialiased">
  <header class="max-w-6xl mx-auto mb-8 flex items-center justify-between">
    <div class="flex items-center space-x-3">
      <div class="w-10 h-10 bg-indigo-600 rounded-lg flex items-center justify-center shadow-lg">
        <span class="text-white font-black text-xl">D</span>
      </div>
      <h1 class="text-2xl font-black text-gray-900 tracking-tight">DUNE TENSION <span class="font-light text-gray-400">| WEB INTERFACE</span></h1>
    </div>
    <div class="flex space-x-4">
      <span class="px-3 py-1 bg-white rounded-full text-xs font-bold text-gray-500 shadow-sm border uppercase">v2.0 (Svelte)</span>
    </div>
  </header>

  <div class="max-w-6xl mx-auto grid grid-cols-1 lg:grid-cols-3 gap-8">
    <!-- Left Column: Controls -->
    <section class="lg:col-span-1 space-y-8">
      <ControlPanel />
    </section>

    <!-- Right Column: Status & Visuals -->
    <section class="lg:col-span-2 space-y-8">
      <StatusPanel />
      
      <!-- Live Plot Placeholder -->
      <div class="bg-white p-6 rounded-lg shadow-md h-80 flex flex-col">
        <h2 class="text-xl font-bold mb-4 text-gray-800 border-b pb-2">Live Analysis</h2>
        <div class="flex-1 bg-gray-50 border-2 border-dashed border-gray-200 rounded-lg flex items-center justify-center">
          <p class="text-gray-400 text-sm italic">Live audio plot (Coming in Phase 3...)</p>
        </div>
      </div>

      <LogViewer />
    </section>
  </div>
  
  <footer class="max-w-6xl mx-auto mt-12 pt-8 border-t border-gray-200 text-center text-gray-400 text-sm">
    <p>&copy; 2026 DUNE Collaboration | High-Performance Rust Measurement Core</p>
  </footer>
</main>

<style>
  :global(body) {
    @apply m-0 p-0 overflow-x-hidden;
  }
</style>
