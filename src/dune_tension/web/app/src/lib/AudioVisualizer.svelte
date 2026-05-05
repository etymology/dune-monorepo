<script lang="ts">
    import { onMount, afterUpdate } from 'svelte';
    import uPlot from 'uplot';
    import 'uplot/dist/uPlot.min.css';

    export let data: number[] = [];
    export let title: string = "";
    export let color: string = "#3b82f6";

    let chartContainer: HTMLDivElement;
    let u: uPlot;

    function initChart() {
        if (u) u.destroy();
        
        const opts: uPlot.Options = {
            title: title,
            width: chartContainer.clientWidth,
            height: 150,
            series: [
                {},
                {
                    stroke: color,
                    width: 2,
                }
            ],
            axes: [
                { show: false },
                { show: true, grid: { show: false } }
            ],
            cursor: { show: false }
        };

        const plotData: uPlot.AlignedData = [
            Array.from(data.keys()),
            data
        ];

        u = new uPlot(opts, plotData, chartContainer);
    }

    onMount(() => {
        initChart();
        const resizeObserver = new ResizeObserver(() => {
            if (u) u.setSize({ width: chartContainer.clientWidth, height: 150 });
        });
        resizeObserver.observe(chartContainer);
        return () => {
            if (u) u.destroy();
            resizeObserver.disconnect();
        };
    });

    afterUpdate(() => {
        if (u && data.length > 0) {
            u.setData([
                Array.from(data.keys()),
                data
            ]);
        }
    });
</script>

<div class="flex flex-col">
    <div bind:this={chartContainer} class="w-full"></div>
</div>
