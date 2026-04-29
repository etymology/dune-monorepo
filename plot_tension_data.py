import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from scipy.stats import gaussian_kde
import os

# Connect to the database
db_path = "dune_tension/data/experiment_measurements.db"
conn = sqlite3.connect(db_path)

# Load data into a DataFrame, ordering by ROWID to maintain time sequence
query = "SELECT tension FROM tension_samples ORDER BY ROWID"
df = pd.read_sql_query(query, conn)
conn.close()

# Convert to numeric, handle errors by coercing to NaN
df["tension"] = pd.to_numeric(df["tension"], errors="coerce")

# Drop NaNs
df = df.dropna(subset=["tension"])

# Remove outliers using IQR for tension
Q1 = df["tension"].quantile(0.25)
Q3 = df["tension"].quantile(0.75)
IQR = Q3 - Q1
lower_bound = Q1 - 2 * IQR
upper_bound = Q3 + 2 * IQR

df_filtered = df[(df["tension"] >= lower_bound) & (df["tension"] <= upper_bound)].copy()

# Calculate moving averages for original sequence
df_filtered["tension_ma3"] = df_filtered["tension"].rolling(window=3).mean()
df_filtered["tension_ma5"] = df_filtered["tension"].rolling(window=5).mean()

# Create random permutation and calculate its moving averages
df_filtered["tension_shuffled"] = np.random.permutation(df_filtered["tension"].values)
df_filtered["shuffled_ma3"] = df_filtered["tension_shuffled"].rolling(window=3).mean()
df_filtered["shuffled_ma5"] = df_filtered["tension_shuffled"].rolling(window=5).mean()


# Calculate statistics including KDE mode
def get_stats(series):
    s = series.dropna()
    if len(s) < 2:
        return {"mean": s.mean() if not s.empty else 0, "std": 0, "range": 0, "mode": 0}

    mean = s.mean()
    std = s.std()
    rng = s.max() - s.min()

    # Estimate mode using KDE
    kde = gaussian_kde(s)
    x_range = np.linspace(s.min(), s.max(), 1000)
    kde_values = kde(x_range)
    mode = x_range[np.argmax(kde_values)]

    return {"mean": mean, "std": std, "range": rng, "mode": mode}


stats_raw = get_stats(df_filtered["tension"])
stats_ma3 = get_stats(df_filtered["tension_ma3"])
stats_ma5 = get_stats(df_filtered["tension_ma5"])
stats_shuff_ma3 = get_stats(df_filtered["shuffled_ma3"])
stats_shuff_ma5 = get_stats(df_filtered["shuffled_ma5"])

# Set seaborn style
sns.set_theme(style="whitegrid")

# Create plots (3 rows, 2 columns)
fig, axes = plt.subplots(3, 2, figsize=(15, 15))
(ax1, ax2), (ax3, ax4), (ax5, ax6) = axes


def plot_dist(ax, data, title, stats, color):
    sns.histplot(
        data, bins=30, kde=True, ax=ax, color=color, edgecolor="black", stat="density"
    )
    textstr = (
        f"Mean: {stats['mean']:.3f} N\n"
        f"Sigma: {stats['std']:.3f} N\n"
        f"Mode (KDE): {stats['mode']:.3f} N\n"
        f"Range: {stats['range']:.3f} N"
    )
    ax.text(
        0.95,
        0.95,
        textstr,
        transform=ax.transAxes,
        fontsize=10,
        verticalalignment="top",
        horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="white", alpha=0.5),
    )
    ax.set_title(title)
    ax.set_xlabel("Tension (N)")
    ax.set_ylabel("Density")


# 1. Histogram of raw tension
plot_dist(
    ax1, df_filtered["tension"], "Histogram of Raw Wire Tension", stats_raw, "skyblue"
)

# 2. Time series of measurements
ax2.plot(
    df_filtered.index, df_filtered["tension"], color="green", alpha=0.3, label="Raw"
)
ax2.plot(
    df_filtered.index,
    df_filtered["tension_ma3"],
    color="red",
    linewidth=1.5,
    label="3-pt MA",
)
ax2.plot(
    df_filtered.index,
    df_filtered["tension_ma5"],
    color="blue",
    linewidth=2,
    label="5-pt MA",
)
ax2.set_title("Time Series of Tension Measurements")
ax2.set_xlabel("Sample Index")
ax2.set_ylabel("Tension (N)")
ax2.legend()
ax2.grid(True, linestyle="--", alpha=0.7)

# 3. Distribution of 3-point moving average (Original)
plot_dist(
    ax3,
    df_filtered["tension_ma3"].dropna(),
    "Original: 3-pt Moving Average",
    stats_ma3,
    "lightcoral",
)

# 4. Distribution of 5-point moving average (Original)
plot_dist(
    ax4,
    df_filtered["tension_ma5"].dropna(),
    "Original: 5-pt Moving Average",
    stats_ma5,
    "cornflowerblue",
)

# 5. Distribution of 3-point moving average (Shuffled)
plot_dist(
    ax5,
    df_filtered["shuffled_ma3"].dropna(),
    "Shuffled: 3-pt Moving Average",
    stats_shuff_ma3,
    "salmon",
)

# 6. Distribution of 5-point moving average (Shuffled)
plot_dist(
    ax6,
    df_filtered["shuffled_ma5"].dropna(),
    "Shuffled: 5-pt Moving Average",
    stats_shuff_ma5,
    "steelblue",
)

plt.tight_layout()

# Save the plot
output_path = "dune_tension/data/tension_analysis_plots.png"
plt.savefig(output_path)
print(f"Plots saved to {output_path}")
print(f"Raw Stats: {stats_raw}")
print(f"3-pt MA Stats: {stats_ma3}")
print(f"5-pt MA Stats: {stats_ma5}")
print(f"Shuffled 3-pt MA Stats: {stats_shuff_ma3}")
print(f"Shuffled 5-pt MA Stats: {stats_shuff_ma5}")
