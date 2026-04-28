import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import os

# Connect to the database
db_path = "dune_tension/data/experiment_measurements.db"
conn = sqlite3.connect(db_path)

# Load data into a DataFrame including 'time'
query = "SELECT tension, confidence, time FROM tension_samples"
df = pd.read_sql_query(query, conn)
conn.close()

# Convert to numeric and datetime
df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")
df["time"] = pd.to_datetime(df["time"])
df = df.dropna(subset=["tension", "confidence", "time"])

# Sort by time to ensure moving average is chronological
df = df.sort_values("time")

# 1. Remove outliers using IQR (Baseline)
Q1 = df["tension"].quantile(0.25)
Q3 = df["tension"].quantile(0.75)
IQR = Q3 - Q1
lower_bound = Q1 - 1.5 * IQR
upper_bound = Q3 + 1.5 * IQR
df_filtered = df[(df["tension"] >= lower_bound) & (df["tension"] <= upper_bound)].copy()

# 2. Apply smoothing (3-point rolling average)
df_smoothed = df_filtered.copy()
df_smoothed["tension"] = df_filtered["tension"].rolling(window=3).mean()
df_smoothed["confidence"] = df_filtered["confidence"].rolling(window=3).mean()
df_smoothed = df_smoothed.dropna(subset=["tension", "confidence"])

# Create 2x2 comparison plot
fig, axes = plt.subplots(2, 2, figsize=(14, 10))

# Top Left: Original Histogram
axes[0, 0].hist(df_filtered["tension"], bins=30, color="skyblue", edgecolor="black")
axes[0, 0].set_title("Original Tension Histogram (No Outliers, Time Sorted)")
axes[0, 0].set_xlabel("Tension (N)")
axes[0, 0].set_ylabel("Frequency")
axes[0, 0].grid(True, linestyle="--", alpha=0.7)

# Top Right: Original Scatter
axes[0, 1].scatter(
    df_filtered["tension"], df_filtered["confidence"], alpha=0.5, color="orange"
)
axes[0, 1].set_title("Original Confidence vs Tension")
axes[0, 1].set_xlabel("Tension (N)")
axes[0, 1].set_ylabel("Confidence")
axes[0, 1].grid(True, linestyle="--", alpha=0.7)

# Bottom Left: Smoothed Histogram
axes[1, 0].hist(df_smoothed["tension"], bins=30, color="lightgreen", edgecolor="black")
axes[1, 0].set_title("Smoothed Tension Histogram (3-pt Moving Avg by Time)")
axes[1, 0].set_xlabel("Tension (N)")
axes[1, 0].set_ylabel("Frequency")
axes[1, 0].grid(True, linestyle="--", alpha=0.7)

# Bottom Right: Smoothed Scatter
axes[1, 1].scatter(
    df_smoothed["tension"], df_smoothed["confidence"], alpha=0.5, color="red"
)
axes[1, 1].set_title("Smoothed Confidence vs Tension")
axes[1, 1].set_xlabel("Tension (N)")
axes[1, 1].set_ylabel("Confidence")
axes[1, 1].grid(True, linestyle="--", alpha=0.7)

plt.tight_layout()

# Save the plot
output_path = "dune_tension/data/tension_smoothing_comparison.png"
plt.savefig(output_path)
print(f"Time-sorted comparison plots saved to {output_path}")
