<script lang="ts">
    import { onMount, afterUpdate, createEventDispatcher } from 'svelte';
    import uPlot from 'uplot';
    import 'uplot/dist/uPlot.min.css';

    const dispatch = createEventDispatcher();

    export let measurements: any[] = [];
    export let title: string = "Wire Tensions (Hz)";
    export let selectionMode: boolean = false;

    let chartContainer: HTMLDivElement;
    let u: uPlot;

    function initChart() {
        if (u) u.destroy();
        
        const opts: uPlot.Options = {
            title: title,
            width: chartContainer.clientWidth,
            height: 450,
            mode: 2, // Scatter mode
            series: [
                {},
                {
                    label: "Tension",
                    stroke: "#10b981",
                    fill: "rgba(16, 185, 129, 0.1)",
                    points: { 
                        size: 8, 
                        fill: "#10b981", 
                        stroke: "#059669",
                        width: 1
                    },
                    paths: () => null, 
                }
            ],
            axes: [
                { 
                    label: "Wire Number",
                    grid: { stroke: "rgba(100,116,139,0.1)" }
                },
                { 
                    label: "Frequency (Hz)",
                    grid: { stroke: "rgba(100,116,139,0.1)" }
                }
            ],
            cursor: {
                drag: { 
                    x: true, 
                    y: true,
                    // If selectionMode is true, we use drag for selection, otherwise for zoom
                    setScale: !selectionMode 
                }
            },
            select: {
                show: selectionMode
            },
            hooks: {
                setSelect: [
                    (uPlotInstance: uPlot) => {
                        if (!selectionMode) return;
                        const { left, top, width, height } = uPlotInstance.select;
                        if (width > 0 && height > 0) {
                            const xMin = uPlotInstance.posToVal(left, "x");
                            const xMax = uPlotInstance.posToVal(left + width, "x");
                            const yMin = uPlotInstance.posToVal(top + height, "y");
                            const yMax = uPlotInstance.posToVal(top, "y");

                            const selectedWires = measurements
                                .filter(m => m.wire_number >= xMin && m.wire_number <= xMax && m.frequency >= yMin && m.frequency <= yMax)
                                .map(m => m.wire_number);
                            
                            if (selectedWires.length > 0) {
                                dispatch('select', selectedWires);
                            }
                        }
                    }
                ]
            }
        };

        const sorted = [...measurements].sort((a, b) => a.wire_number - b.wire_number);
        const plotData: uPlot.AlignedData = [
            sorted.map(m => m.wire_number),
            sorted.map(m => m.frequency)
        ];

        u = new uPlot(opts, plotData, chartContainer);
    }

    onMount(() => {
        initChart();
        const resizeObserver = new ResizeObserver(() => {
            if (u) u.setSize({ width: chartContainer.clientWidth, height: 450 });
        });
        resizeObserver.observe(chartContainer);
        return () => {
            if (u) u.destroy();
            resizeObserver.disconnect();
        };
    });

    afterUpdate(() => {
        if (u) {
            const sorted = [...measurements].sort((a, b) => a.wire_number - b.wire_number);
            u.setData([
                sorted.map(m => m.wire_number),
                sorted.map(m => m.frequency)
            ]);
        }
    });

    // Re-init chart when selectionMode changes
    $: if (selectionMode !== undefined && u) {
        initChart();
    }
</script>

<div class="flex flex-col bg-white dark:bg-gray-800 p-6 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700">
    <div class="flex justify-between items-center mb-4">
        <h3 class="text-lg font-bold text-gray-800 dark:text-gray-200">{title}</h3>
        <div class="flex items-center space-x-2">
            <span class="text-xs font-medium text-gray-500">Mode:</span>
            <span class={`px-2 py-1 rounded text-xs font-bold ${selectionMode ? 'bg-orange-100 text-orange-700' : 'bg-blue-100 text-blue-700'}`}>
                {selectionMode ? 'Selection' : 'Zoom/Pan'}
            </span>
        </div>
    </div>
    
    <div bind:this={chartContainer} class="w-full"></div>
    
    <div class="flex justify-between mt-4 text-[10px] text-gray-400 font-medium italic">
        <span>{selectionMode ? 'Drag to select wires for remeasurement' : 'Drag to zoom, double-click to reset'}</span>
        <span>{measurements.length} wires recorded</span>
    </div>
</div>
