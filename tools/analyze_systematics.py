import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
import os


def load_data(db_path):
    if not os.path.exists(db_path):
        print(f"Error: Database {db_path} not found.")
        return None

    conn = sqlite3.connect(db_path)
    # Load both summary results and raw samples
    df_results = pd.read_sql_query("SELECT * FROM tension_data", conn)
    df_samples = pd.read_sql_query("SELECT * FROM tension_samples", conn)
    conn.close()

    # Convert numeric columns
    for df in [df_results, df_samples]:
        for col in [
            "tension",
            "frequency",
            "confidence",
            "wire_length",
            "known_tension",
            "x",
            "y",
            "focus_position",
        ]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

    return df_results, df_samples


def analyze_spread(df, group_by=["experiment_id", "wire_number", "zone"]):
    stats = (
        df.groupby(group_by)["tension"]
        .agg(["mean", "std", "count", "min", "max"])
        .reset_index()
    )
    stats["range"] = stats["max"] - stats["min"]
    return stats


def plot_interzone_variance(df_samples):
    # Filter for wires measured in multiple zones within the same experiment
    multi_zone = df_samples.groupby(["experiment_id", "wire_number"])["zone"].nunique()
    multi_zone_wires = multi_zone[multi_zone > 1].index

    if multi_zone_wires.empty:
        print("No multi-zone data found for inter-zone variance analysis.")
        return

    df_multi = (
        df_samples.set_index(["experiment_id", "wire_number"])
        .loc[multi_zone_wires]
        .reset_index()
    )

    plt.figure(figsize=(12, 6))
    sns.boxplot(data=df_multi, x="wire_number", y="tension", hue="zone")
    plt.title("Tension Spread across Multiple Zones (Same Wire)")
    plt.ylabel("Tension (N)")
    plt.xlabel("Wire Number")
    plt.legend(title="Zone")
    plt.savefig("interzone_variance.png")
    print("Saved interzone_variance.png")


def plot_experiment_comparison(df_samples):
    plt.figure(figsize=(10, 6))
    sns.violinplot(data=df_samples, x="experiment_name", y="tension")
    plt.title("Tension Distribution Comparison across Experiments")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("experiment_comparison.png")
    print("Saved experiment_comparison.png")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze Tension Measurement Systematics"
    )
    parser.add_argument(
        "--db",
        default="data/experiment_measurements.db",
        help="Path to experiment database",
    )
    args = parser.parse_args()

    df_results, df_samples = load_data(args.db)
    if df_samples is None or df_samples.empty:
        return

    print("\n--- Measurement Statistics per Wire/Zone ---")
    stats = analyze_spread(df_samples)
    print(stats)

    plot_interzone_variance(df_samples)
    plot_experiment_comparison(df_samples)


if __name__ == "__main__":
    main()
