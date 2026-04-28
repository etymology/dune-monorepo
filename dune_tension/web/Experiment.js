document.getElementById('start-btn').addEventListener('click', async () => {
    const name = document.getElementById('exp-name').value;
    const apa_name = document.getElementById('apa-name').value;
    const layer = document.getElementById('layer').value;
    const side = document.getElementById('side').value;
    const wire_number = parseInt(document.getElementById('wire-number').value);
    const zone = parseInt(document.getElementById('zone').value);
    const known_tension = parseFloat(document.getElementById('known-tension').value) || null;
    const focus_position = parseInt(document.getElementById('focus-pos').value);
    const samples_per_wire = parseInt(document.getElementById('samples-per-wire').value);
    
    const capos_on_combs = Array.from(document.querySelectorAll('input[name="capo-comb"]:checked'))
        .map(cb => parseInt(cb.value));

    const statusDisplay = document.getElementById('status-display');
    const resultsTable = document.getElementById('results-table').getElementsByTagName('tbody')[0];
    const progressBar = document.getElementById('progress-bar');
    const audioPlot = document.getElementById('audio-plot');
    const summaryPlot = document.getElementById('summary-plot');

    statusDisplay.textContent = "Starting experiment...";
    progressBar.style.width = "0%";
    resultsTable.innerHTML = "";

    async function refreshPlots() {
        try {
            const audioResponse = await fetch('/experiment/plots/audio');
            if (audioResponse.ok) {
                const audioData = await audioResponse.json();
                audioPlot.src = `data:image/png;base64,${audioData.image}`;
            }

            const summaryResponse = await fetch('/experiment/plots/summary');
            if (summaryResponse.ok) {
                const summaryData = await summaryResponse.json();
                summaryPlot.src = `data:image/png;base64,${summaryData.image}`;
            }
        } catch (e) {
            console.error("Failed to refresh plots", e);
        }
    }

    try {
        // 1. Start Experiment
        const startResponse = await fetch('/experiment/start', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                name, apa_name, layer, side, known_tension, focus_position, zone, 
                capos_on_combs, type: "single_wire_single_zone" 
            })
        });
        const startData = await startResponse.json();
        const experiment_id = startData.experiment_id;

        statusDisplay.textContent = `Experiment ${experiment_id} active. Running loop...`;

        // 2. Run Measurement Loop
        for (let i = 0; i < samples_per_wire; i++) {
            statusDisplay.textContent = `Measuring sample ${i + 1} of ${samples_per_wire}...`;
            
            const measureResponse = await fetch('/experiment/measure', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    experiment_id,
                    experiment_name: name,
                    apa_name,
                    layer,
                    side,
                    wire_number,
                    zone,
                    known_tension,
                    focus_position,
                    capos_on_combs,
                    samples_per_wire: 1,
                })
            });
            
            const result = await measureResponse.json();
            
            if (result.status === 'success') {
                const row = resultsTable.insertRow(0); // Insert at top
                row.insertCell(0).textContent = i + 1;
                row.insertCell(1).textContent = result.frequency.toFixed(2);
                row.insertCell(2).textContent = result.tension.toFixed(2);
                row.insertCell(3).textContent = result.confidence.toFixed(2);
                row.insertCell(4).textContent = `${result.x.toFixed(1)}, ${result.y.toFixed(1)} (Z${result.zone})`;
                
                // Refresh plots after success
                await refreshPlots();
            } else if (result.status === 'impossible') {
                statusDisplay.textContent = `Error: ${result.message}`;
                break;
            } else {
                const row = resultsTable.insertRow(0);
                row.insertCell(0).textContent = i + 1;
                row.insertCell(1).colSpan = 4;
                row.cells[1].textContent = "Measurement failed";
            }
            
            progressBar.style.width = `${((i + 1) / samples_per_wire) * 100}%`;
        }

        if (statusDisplay.textContent !== "Experiment complete.") {
             statusDisplay.textContent = "Experiment finished.";
        }

    } catch (error) {
        statusDisplay.textContent = `Error: ${error.message}`;
        console.error(error);
    }
});

document.getElementById('collect-raw-btn').addEventListener('click', async () => {
    const name = document.getElementById('exp-name').value;
    const apa_name = document.getElementById('apa-name').value;
    const layer = document.getElementById('layer').value;
    const side = document.getElementById('side').value;
    const wire_number = parseInt(document.getElementById('wire-number').value);
    const zone = parseInt(document.getElementById('zone').value);
    const known_tension = parseFloat(document.getElementById('known-tension').value) || null;
    const focus_position = parseInt(document.getElementById('focus-pos').value);
    const samples_per_wire = parseInt(document.getElementById('samples-per-wire').value);
    const record_duration = parseFloat(document.getElementById('record-duration').value);

    const statusDisplay = document.getElementById('status-display');
    const resultsTable = document.getElementById('results-table').getElementsByTagName('tbody')[0];
    const audioPlot = document.getElementById('audio-plot');
    const summaryPlot = document.getElementById('summary-plot');

    statusDisplay.textContent = "Collecting raw samples...";
    resultsTable.innerHTML = "";

    try {
        const response = await fetch('/experiment/collect_raw', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                experiment_name: name, apa_name, layer, side, wire_number, zone, 
                known_tension, focus_position, samples_per_wire, record_duration 
            })
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            statusDisplay.textContent = `Collected ${data.samples.length} raw samples. Exp ID: ${data.experiment_id}`;
            document.getElementById('reanalyze-exp-id').value = data.experiment_id;
            
            data.samples.forEach(s => {
                const row = resultsTable.insertRow();
                row.insertCell(0).textContent = s.sample_index + 1;
                row.insertCell(1).textContent = s.frequency.toFixed(2);
                row.insertCell(2).textContent = s.tension.toFixed(2);
                row.insertCell(3).textContent = s.confidence.toFixed(2);
                row.insertCell(4).textContent = "RAW SAVED";
            });
            
            // Refresh summary plot
            const summaryResponse = await fetch('/experiment/plots/summary');
            if (summaryResponse.ok) {
                const summaryData = await summaryResponse.json();
                summaryPlot.src = `data:image/png;base64,${summaryData.image}`;
            }
        } else {
            statusDisplay.textContent = `Error: ${data.message || 'Collection failed'}`;
        }
    } catch (error) {
        statusDisplay.textContent = `Error: ${error.message}`;
    }
});

document.getElementById('reanalyze-btn').addEventListener('click', async () => {
    const experiment_id = document.getElementById('reanalyze-exp-id').value;
    const confidence_threshold = parseFloat(document.getElementById('conf-threshold').value);
    const resultsDiv = document.getElementById('reanalyze-results');

    if (!experiment_id) {
        alert("Please provide an Experiment ID");
        return;
    }

    resultsDiv.textContent = "Reanalyzing...";

    try {
        const response = await fetch('/experiment/reanalyze', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ experiment_id, confidence_threshold })
        });
        const data = await response.json();
        
        if (data.status === 'success') {
            resultsDiv.innerHTML = `
                <p><strong>Total Samples:</strong> ${data.total_count}</p>
                <p><strong>Passing (@${confidence_threshold}):</strong> ${data.passing_count}</p>
                <ul>
                    ${data.passing_samples.slice(0, 10).map(s => `<li>Freq: ${s.frequency.toFixed(2)}Hz, Conf: ${s.confidence.toFixed(2)}, Tension: ${s.tension.toFixed(2)}N</li>`).join('')}
                    ${data.passing_samples.length > 10 ? '<li>...</li>' : ''}
                </ul>
            `;
        } else {
            resultsDiv.textContent = `Error: ${data.status}`;
        }
    } catch (error) {
        resultsDiv.textContent = `Error: ${error.message}`;
    }
});
