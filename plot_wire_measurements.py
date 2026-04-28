import sqlite3
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# Connect to database
conn = sqlite3.connect('dune_tension/data/experiment_measurements.db')
cursor = conn.cursor()

cursor.execute("SELECT frequency, confidence, tension FROM tension_data WHERE wire_number='1000'")
td_rows = cursor.fetchall()

cursor.execute("SELECT frequency, confidence, tension FROM tension_samples WHERE wire_number='1000'")
ts_rows = cursor.fetchall()
conn.close()

all_freqs = [float(r[0]) for r in ts_rows]
all_confs = [float(r[1]) for r in ts_rows]
all_tensions = [float(r[2]) for r in ts_rows]

td_freqs = [float(r[0]) for r in td_rows]
td_confs = [float(r[1]) for r in td_rows]
td_tensions = [float(r[2]) for r in td_rows]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

ax1.hist(all_freqs, bins=30, color='steelblue', edgecolor='black', alpha=0.7)
ax1.set_xlabel('Frequency (Hz)', fontsize=12)
ax1.set_ylabel('Count', fontsize=12)
ax1.set_title('Histogram of Frequency Measurements for Wire 1000', fontsize=14, fontweight='bold')
ax1.grid(axis='y', alpha=0.3)
mean_f = np.mean(all_freqs)
median_f = np.median(all_freqs)
std_f = np.std(all_freqs)
ax1.axvline(mean_f, color='red', linestyle='--', linewidth=2, label=f'Mean: {mean_f:.2f} Hz')
ax1.axvline(median_f, color='green', linestyle='--', linewidth=2, label=f'Median: {median_f:.2f} Hz')
ax1.legend(fontsize=10)
ax1.text(0.02, 0.98, f'N={len(all_freqs)}\nStd={std_f:.2f} Hz', transform=ax1.transAxes, fontsize=10,
         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

scatter = ax2.scatter(td_tensions, td_confs, c=td_freqs, cmap='viridis', 
                      s=80, alpha=0.7, edgecolors='black', linewidth=0.5, label='tension_data')
ax2.scatter(all_tensions, all_confs, c=all_freqs, cmap='viridis', 
            s=30, alpha=0.4, edgecolors='none', label='tension_samples')
ax2.set_xlabel('Tension', fontsize=12)
ax2.set_ylabel('Confidence', fontsize=12)
ax2.set_title('Confidence vs Tension for Wire 1000', fontsize=14, fontweight='bold')
ax2.grid(alpha=0.3)
ax2.legend(fontsize=9)
cbar = plt.colorbar(scatter, ax=ax2)
cbar.set_label('Frequency (Hz)', fontsize=10)
corr = np.corrcoef(td_tensions, td_confs)[0, 1]
ax2.text(0.02, 0.98, f'Pearson r = {corr:.4f}', transform=ax2.transAxes, fontsize=11,
         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.5))

plt.suptitle('Wire 1000 - Measurement Analysis', fontsize=16, fontweight='bold')
plt.tight_layout()
output = 'dune_tension/data/wire_1000_analysis.png'
plt.savefig(output, dpi=150, bbox_inches='tight')
print(f'Saved to {output}')
print(f'\nWire 1000 Summary:')
print(f'  tension_data points: {len(td_rows)}, tension_samples points: {len(ts_rows)}')
print(f'  Frequency:  mean={mean_f:.2f}, std={std_f:.2f} Hz')
print(f'  Tension:    mean={np.mean(td_tensions):.4f}, std={np.std(td_tensions):.4f}')
print(f'  Confidence: mean={np.mean(td_confs):.4f}, std={np.std(td_confs):.4f}')
print(f'  Tension-Confidence corr: {corr:.4f}')
