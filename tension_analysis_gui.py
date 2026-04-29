import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import gaussian_kde
import os
import tkinter as tk
from tkinter import ttk, messagebox
import sys

# Use macosx backend if on macOS to avoid tkagg issues
if sys.platform == "darwin":
    try:
        import matplotlib

        matplotlib.use("macosx")
    except Exception:
        pass


def get_mode_kde(series):
    s = series.dropna()
    if len(s) < 2:
        return None
    try:
        if s.nunique() == 1:
            return s.iloc[0]
        kde = gaussian_kde(s)
        x_range = np.linspace(s.min(), s.max(), 1000)
        kde_values = kde(x_range)
        mode = x_range[np.argmax(kde_values)]
        return mode
    except Exception:
        return None


def process_db(db_path, all_diffs, min_samples, ma_window, layer_filter):
    if not os.path.exists(db_path):
        return 0, 0

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tension_samples';"
        )
        if not cursor.fetchone():
            conn.close()
            return 0, 0

        cursor.execute("PRAGMA table_info(tension_samples)")
        cols = [c[1] for c in cursor.fetchall()]

        if "tension" not in cols:
            conn.close()
            return 0, 0

        id_cols = ["apa_name", "layer", "side"]
        if "wire_number" in cols:
            id_cols.append("wire_number")
        elif "x" in cols and "y" in cols:
            id_cols.extend(["x", "y"])
        else:
            conn.close()
            return 0, 0

        query = f"SELECT {', '.join(id_cols)}, tension FROM tension_samples"
        if layer_filter != "All":
            query += f" WHERE layer = '{layer_filter}'"

        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            return 0, 0

        df["tension"] = pd.to_numeric(df["tension"], errors="coerce")
        df = df.dropna(subset=["tension"])
        df = df[df["tension"] > 0]

        grouped = df.groupby(id_cols)

        db_diff_count = 0
        wires_processed = 0
        for name, group in grouped:
            if len(group) >= min_samples:
                tension_vals = group["tension"]
                mode = get_mode_kde(tension_vals)
                if mode is not None:
                    ma = tension_vals.rolling(window=ma_window).mean().dropna()
                    diffs = ma - mode
                    all_diffs.extend(diffs.tolist())
                    db_diff_count += len(diffs)
                    wires_processed += 1
        return wires_processed, db_diff_count
    except Exception as e:
        print(f"Error processing {db_path}: {e}")
        return 0, 0


class TensionAnalysisApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tension Analysis GUI")
        self.root.geometry("600x200")

        # Configuration Frame
        config_frame = ttk.LabelFrame(root, text="Parameters", padding="10")
        config_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Min Samples
        ttk.Label(config_frame, text="Min Samples per Wire:").grid(
            row=0, column=0, sticky=tk.W, padx=5
        )
        self.min_samples_var = tk.IntVar(value=10)
        ttk.Entry(config_frame, textvariable=self.min_samples_var, width=10).grid(
            row=0, column=1, sticky=tk.W, padx=5
        )

        # Moving Average Window
        ttk.Label(config_frame, text="MA Window Size:").grid(
            row=1, column=0, sticky=tk.W, padx=5
        )
        self.ma_window_var = tk.IntVar(value=3)
        ttk.Entry(config_frame, textvariable=self.ma_window_var, width=10).grid(
            row=1, column=1, sticky=tk.W, padx=5
        )

        # Layer Filter
        ttk.Label(config_frame, text="Layer Filter:").grid(
            row=2, column=0, sticky=tk.W, padx=5
        )
        self.layer_var = tk.StringVar(value="All")
        layer_combo = ttk.Combobox(
            config_frame,
            textvariable=self.layer_var,
            values=["All", "U", "V", "X"],
            width=10,
        )
        layer_combo.grid(row=2, column=1, sticky=tk.W, padx=5)

        # Buttons Frame
        btn_frame = ttk.Frame(config_frame)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=10)

        # Generate Button
        self.generate_btn = ttk.Button(
            btn_frame, text="Generate & Show Plot", command=self.run_analysis
        )
        self.generate_btn.pack(side=tk.LEFT, padx=10)

        # Save Button
        self.save_btn = ttk.Button(
            btn_frame, text="Save Last Plot", command=self.save_plot, state=tk.DISABLED
        )
        self.save_btn.pack(side=tk.LEFT, padx=10)

        self.current_fig = None

    def run_analysis(self):
        self.generate_btn.config(state=tk.DISABLED)
        self.save_btn.config(state=tk.DISABLED)
        try:
            min_samples = self.min_samples_var.get()
            ma_window = self.ma_window_var.get()
            layer_filter = self.layer_var.get()

            databases = [
                "dune_tension/data/tension_data/tension_data.db",
                "dune_tension/data/tension_measurements.db",
                "dune_tension/data/experiment_measurements.db",
            ]

            all_diffs = []
            total_wires = 0

            for db in databases:
                wires, samples = process_db(
                    db, all_diffs, min_samples, ma_window, layer_filter
                )
                total_wires += wires

            if not all_diffs:
                messagebox.showwarning(
                    "No Data",
                    f"No differences calculated with parameters:\nMinSamples={min_samples}, Window={ma_window}, Layer={layer_filter}",
                )
                return

            self.show_plot(all_diffs, total_wires, min_samples, ma_window, layer_filter)
            self.save_btn.config(state=tk.NORMAL)

        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")
        finally:
            self.generate_btn.config(state=tk.NORMAL)

    def show_plot(self, all_diffs, total_wires, min_samples, ma_window, layer_filter):
        plt.close("all")
        self.current_fig = plt.figure(figsize=(10, 6))
        sns.set_theme(style="whitegrid")

        sns.histplot(all_diffs, bins=100, kde=True, color="skyblue", edgecolor="black")

        plt.title(
            f"MA Differences from Mode\n(MinSamples={min_samples}, Window={ma_window}, Layer={layer_filter})"
        )
        plt.xlabel("Difference from Mode (N)")
        plt.ylabel("Frequency")

        mu = np.mean(all_diffs)
        std = np.std(all_diffs)
        textstr = f"Wires = {total_wires}\nSamples = {len(all_diffs)}\nMean = {mu:.4f}\nStd = {std:.4f}"
        plt.text(
            0.95,
            0.95,
            textstr,
            transform=plt.gca().transAxes,
            fontsize=10,
            verticalalignment="top",
            horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.5),
        )

        plt.show(block=False)

    def save_plot(self):
        if self.current_fig:
            output_path = "dune_tension/data/tension_mode_diff_gui_output.png"
            self.current_fig.savefig(output_path)
            messagebox.showinfo("Saved", f"Plot saved to {output_path}")


if __name__ == "__main__":
    root = tk.Tk()
    app = TensionAnalysisApp(root)
    root.mainloop()
