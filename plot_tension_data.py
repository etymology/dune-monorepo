import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import os

# Connect to the database
db_path = "dune_tension/data/experiment_measurements.db"
conn = sqlite3.connect(db_path)

# Load data into a DataFrame
query = "SELECT tension, confidence FROM tension_samples"
df = pd.read_sql_query(query, conn)
conn.close()

# Convert to numeric, handle errors by coercing to NaN
df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")

# Drop NaNs
df = df.dropna(subset=["tension", "confidence"])

# Remove outliers using IQR for tension
Q1 = df["tension"].quantile(0.25)
Q3 = df["tension"].quantile(0.75)
IQR = Q3 - Q1
lower_bound = Q1 - 3 * IQR
upper_bound = Q3 + 3 * IQR

df_filtered = df[(df["tension"] >= lower_bound) & (df["tension"] <= upper_bound)]

# Create dual plot
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

# Histogram of tension
ax1.hist(df_filtered["tension"], bins=30, color="skyblue", edgecolor="black")
ax1.set_title("Histogram of Wire Tension (Outliers Removed)")
ax1.set_xlabel("Tension (N)")
ax1.set_ylabel("Frequency")
ax1.grid(True, linestyle="--", alpha=0.7)

# Scatter plot of confidence vs tension
ax2.scatter(
    df_filtered["tension"], df_filtered["confidence"], alpha=0.5, color="orange"
)
ax2.set_title("Confidence vs Tension (Outliers Removed)")
ax2.set_xlabel("Tension (N)")
ax2.set_ylabel("Confidence")
ax2.grid(True, linestyle="--", alpha=0.7)

plt.tight_layout()

# Save the plot
output_path = "dune_tension/data/tension_analysis_plots.png"
plt.savefig(output_path)
print(f"Plots saved to {output_path}")
