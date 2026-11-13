"""
Comprehensive EMG Analysis - 2.5kg, 5kg, and 7.5kg Load Conditions
================================================───────────────────
Processes EMG Excel files for:
  - 2.5kg push
  - 5kg push
  - 7.5kg push

For each load:
  1. Drops NaN values and crops initial zero baseline
  2. Crops 3 minutes of consecutive data (360,000 samples @ 2000 Hz)
  3. Computes total trial RMS for Biceps & Triceps
  4. Divides into 36 x 5-second windows
  5. Computes windowed RMS and Median Frequency (MDF)
  6. Generates 3 white-theme plots saved into separate load folders:
     - emg_rms_bar_plot.png
     - emg_time_rms.png
     - emg_time_mdf.png
"""

import os
import sys
import time
import zipfile
import re
import io
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams
import warnings
warnings.filterwarnings("ignore")

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
BASE_MTP_DIR  = "c:/Users/acer/Desktop/mtp"
FS            = 2000          # Hz
WINDOW_S      = 5             # seconds per window
WINDOW_SAMP   = FS * WINDOW_S # 10,000 samples per window
N_WINDOWS     = 36            # 180s / 5s = 36 windows
N_SAMPLES     = N_WINDOWS * WINDOW_SAMP  # 360,000

TIME_AXIS     = np.arange(N_WINDOWS) * WINDOW_S + WINDOW_S / 2

LOAD_CONFIGS = [
    {"name": "2.5kg", "dir_name": "2.5kg push", "out_dir": os.path.normpath("c:/Users/acer/Desktop/mtp/plots/2.5kg")},
    {"name": "5kg",   "dir_name": "5kg push",   "out_dir": os.path.normpath("c:/Users/acer/Desktop/mtp/plots/5kg")},
    {"name": "7.5kg", "dir_name": "7.5kg push", "out_dir": os.path.normpath("c:/Users/acer/Desktop/mtp/plots/7.5kg")},
    {"name": "10kg",  "dir_name": "10kg push",  "out_dir": os.path.normpath("c:/Users/acer/Desktop/mtp/plots/10kg")},
]

# Style settings (White Theme)
rcParams["font.family"] = "DejaVu Sans"
BG_COLOR   = "#FFFFFF"
TEXT_COLOR = "#111111"
GRID_COLOR = "#E2E8F0"
BORDER_C   = "#CBD5E1"

BICEPS_COLOR  = "#2563EB"  # Royal Blue
TRICEPS_COLOR = "#DC2626"  # Crimson Red

# Distinct subject color palette
PALETTE = [
    "#1D4ED8",  # Blue
    "#D97706",  # Amber / Gold
    "#059669",  # Emerald Green
    "#DC2626",  # Red
    "#7C3AED",  # Purple
    "#DB2777",  # Pink
    "#0891B2",  # Cyan
]

# ─────────────────────────────────────────────
# ULTRA-FAST XLSX READER (XML streaming)
# ─────────────────────────────────────────────
def read_xlsx_two_cols(filepath, skip_rows=4, max_rows=None):
    from xml.etree.ElementTree import iterparse
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    col0, col1 = [], []
    data_row_idx = -1
    t0 = time.time()

    with zipfile.ZipFile(filepath, 'r') as zf:
        # Check sheet name
        sheet_names = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet")]
        sheet_file = sheet_names[0] if sheet_names else "xl/worksheets/sheet1.xml"

        with zf.open(sheet_file) as sheet_xml:
            context = iterparse(sheet_xml, events=("start", "end"))
            current_row_cells = []
            in_row = False
            current_col = None
            current_val = None
            is_shared_string = False

            for event, elem in context:
                tag = elem.tag.replace(f"{{{NS}}}", "")

                if event == "start":
                    if tag == "row":
                        current_row_cells = []
                        in_row = True
                    elif tag == "c" and in_row:
                        ref = elem.get("r", "")
                        col_letter = re.match(r"([A-Z]+)", ref)
                        if col_letter:
                            letters = col_letter.group(1)
                            cidx = 0
                            for ch in letters:
                                cidx = cidx * 26 + (ord(ch) - ord('A') + 1)
                            current_col = cidx - 1
                        else:
                            current_col = None
                        cell_type = elem.get("t", "")
                        is_shared_string = (cell_type == "s")
                        current_val = None

                elif event == "end":
                    if tag == "v" and in_row and current_col is not None:
                        current_val = elem.text
                    elif tag == "c" and in_row:
                        if current_col is not None and current_val is not None and not is_shared_string:
                            try:
                                current_row_cells.append((current_col, float(current_val)))
                            except (TypeError, ValueError):
                                pass
                        current_col = None
                        current_val = None
                        is_shared_string = False
                    elif tag == "row":
                        in_row = False
                        data_row_idx += 1

                        if data_row_idx < skip_rows:
                            current_row_cells = []
                            elem.clear()
                            continue

                        c0_val, c1_val = None, None
                        for (cidx, fval) in current_row_cells:
                            if cidx == 0: c0_val = fval
                            elif cidx == 1: c1_val = fval

                        if c0_val is not None and c1_val is not None:
                            col0.append(c0_val)
                            col1.append(c1_val)
                            if max_rows is not None and len(col0) >= max_rows:
                                break

                        current_row_cells = []
                        elem.clear()

    elapsed = time.time() - t0
    print(f"  Streamed {len(col0):,} valid rows in {elapsed:.1f}s")
    return np.array(col0, dtype=np.float64), np.array(col1, dtype=np.float64)


def preprocess(biceps_arr, triceps_arr):
    non_zero = (biceps_arr != 0) | (triceps_arr != 0)
    first_valid = int(np.argmax(non_zero)) if non_zero.any() else 0
    biceps_arr  = biceps_arr[first_valid:]
    triceps_arr = triceps_arr[first_valid:]

    if len(biceps_arr) < N_SAMPLES:
        pad_len = N_SAMPLES - len(biceps_arr)
        print(f"  [WARN] {len(biceps_arr):,} samples (< {N_SAMPLES:,}). Padding {pad_len:,} missing tail samples with NaN.")
        biceps_arr = np.pad(biceps_arr, (0, pad_len), constant_values=np.nan)
        triceps_arr = np.pad(triceps_arr, (0, pad_len), constant_values=np.nan)
    else:
        biceps_arr  = biceps_arr[:N_SAMPLES]
        triceps_arr = triceps_arr[:N_SAMPLES]

    return biceps_arr, triceps_arr


# ─────────────────────────────────────────────
# METRICS COMPUTATION
# ─────────────────────────────────────────────
def rms(arr):
    valid = arr[~np.isnan(arr)]
    if len(valid) == 0:
        return np.nan
    return np.sqrt(np.mean(np.square(valid)))


def compute_mdf(window, fs=FS):
    valid = window[~np.isnan(window)]
    if len(valid) == 0:
        return np.nan
    n = len(valid)
    win = np.hamming(n)
    fft_vals = np.fft.rfft(valid * win, n=n)
    psd = np.abs(fft_vals) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0/fs)

    mask = (freqs >= 10) & (freqs <= 500)
    freqs = freqs[mask]
    psd = psd[mask]

    if len(psd) == 0 or psd.sum() == 0:
        return np.nan

    cumsum = np.cumsum(psd)
    half = cumsum[-1] / 2.0
    idx = np.searchsorted(cumsum, half)
    idx = min(idx, len(freqs) - 1)
    return float(freqs[idx])


def windowed_metrics(signal):
    rms_arr = np.zeros(N_WINDOWS)
    mdf_arr = np.zeros(N_WINDOWS)
    for i in range(N_WINDOWS):
        w = signal[i * WINDOW_SAMP : (i + 1) * WINDOW_SAMP]
        rms_arr[i] = rms(w)
        mdf_arr[i] = compute_mdf(w)
    return rms_arr, mdf_arr


def style_ax(ax, title, xlabel, ylabel):
    ax.set_facecolor(BG_COLOR)
    ax.tick_params(colors=TEXT_COLOR, labelsize=10)
    for sp in ax.spines.values():
        sp.set_edgecolor(BORDER_C)
        sp.set_linewidth(1.0)
    ax.yaxis.grid(True, color=GRID_COLOR, linestyle="--", lw=0.8, zorder=0)
    ax.xaxis.grid(True, color=GRID_COLOR, linestyle="--", lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title(title, color=TEXT_COLOR, fontsize=13, fontweight="bold", pad=12)
    ax.set_xlabel(xlabel, color=TEXT_COLOR, fontsize=11, labelpad=8)
    ax.set_ylabel(ylabel, color=TEXT_COLOR, fontsize=11, labelpad=8)


# ─────────────────────────────────────────────
# PROCESS LOAD CONDITION
# ─────────────────────────────────────────────
def process_load_condition(cfg):
    load_name = cfg["name"]
    load_dir  = os.path.join(BASE_MTP_DIR, cfg["dir_name"])
    out_dir   = cfg["out_dir"]

    os.makedirs(out_dir, exist_ok=True)
    print("\n" + "="*65)
    print(f"PROCESSING LOAD CONDITION: {load_name} ({cfg['dir_name']})")
    print(f"Output directory: {out_dir}")
    print("="*65)

    if not os.path.exists(load_dir):
        print(f"[ERROR] Directory does not exist: {load_dir}")
        return None

    subjects = sorted([
        d for d in os.listdir(load_dir)
        if os.path.isdir(os.path.join(load_dir, d))
    ])

    print(f"Found subjects: {subjects}")

    results = {}
    summary_rows = []

    for subject in subjects:
        subject_dir = os.path.join(load_dir, subject)
        trial_files = sorted([
            f for f in os.listdir(subject_dir)
            if f.lower().endswith(".xlsx") or f.lower().endswith(".csv")
        ])

        if not trial_files:
            print(f"  [SKIP] No trial files found for subject: {subject}")
            continue

        b_total_rms_list, t_total_rms_list = [], []
        b_rms_w_list, t_rms_w_list = [], []
        b_mdf_w_list, t_mdf_w_list = [], []

        for tf in trial_files:
            fp = os.path.join(subject_dir, tf)
            print(f"\nProcessing [{load_name.upper()} | {subject.upper()}] {tf}...")

            b_raw, t_raw = read_xlsx_two_cols(fp, skip_rows=4, max_rows=N_SAMPLES + 10000)
            b_sig, t_sig = preprocess(b_raw, t_raw)

            # Total trial RMS
            b_tr_rms = rms(b_sig)
            t_tr_rms = rms(t_sig)
            b_total_rms_list.append(b_tr_rms)
            t_total_rms_list.append(t_tr_rms)

            # Windowed RMS & MDF
            b_rms_w, b_mdf_w = windowed_metrics(b_sig)
            t_rms_w, t_mdf_w = windowed_metrics(t_sig)

            b_rms_w_list.append(b_rms_w)
            t_rms_w_list.append(t_rms_w)
            b_mdf_w_list.append(b_mdf_w)
            t_mdf_w_list.append(t_mdf_w)

            print(f"  Total RMS -> Biceps: {b_tr_rms:.2f} | Triceps: {t_tr_rms:.2f}")
            print(f"  Biceps  Window RMS: {b_rms_w.mean():.2f} ± {b_rms_w.std():.2f} | MDF: {b_mdf_w.mean():.1f} ± {b_mdf_w.std():.1f} Hz")
            print(f"  Triceps Window RMS: {t_rms_w.mean():.2f} ± {t_rms_w.std():.2f} | MDF: {t_mdf_w.mean():.1f} ± {t_mdf_w.std():.1f} Hz")

        mean_b_rms_w = np.nanmean(b_rms_w_list, axis=0)
        mean_t_rms_w = np.nanmean(t_rms_w_list, axis=0)
        mean_b_mdf_w = np.nanmean(b_mdf_w_list, axis=0)
        mean_t_mdf_w = np.nanmean(t_mdf_w_list, axis=0)

        results[subject] = {
            "total_biceps_rms":  float(np.nanmean(b_total_rms_list)),
            "total_triceps_rms": float(np.nanmean(t_total_rms_list)),
            "biceps_rms_w":  mean_b_rms_w,
            "triceps_rms_w": mean_t_rms_w,
            "biceps_mdf_w":  mean_b_mdf_w,
            "triceps_mdf_w": mean_t_mdf_w,
        }

        summary_rows.append({
            "Subject": subject.capitalize(),
            "Biceps Total RMS": np.nanmean(b_total_rms_list),
            "Triceps Total RMS": np.nanmean(t_total_rms_list),
            "Biceps Window RMS Mean": np.nanmean(mean_b_rms_w),
            "Biceps Window RMS SD": np.nanstd(mean_b_rms_w),
            "Triceps Window RMS Mean": np.nanmean(mean_t_rms_w),
            "Triceps Window RMS SD": np.nanstd(mean_t_rms_w),
            "Biceps MDF Mean": np.nanmean(mean_b_mdf_w),
            "Biceps MDF SD": np.nanstd(mean_b_mdf_w),
            "Triceps MDF Mean": np.nanmean(mean_t_mdf_w),
            "Triceps MDF SD": np.nanstd(mean_t_mdf_w),
        })

    if not results:
        print(f"[WARN] No valid results for load condition: {load_name}")
        return None

    # ─────────────────────────────────────────────
    # GENERATE PLOTS
    # ─────────────────────────────────────────────
    subjects_list = list(results.keys())
    x = np.arange(len(subjects_list))
    width = 0.35

    # 1. GROUPED BAR PLOT (Total RMS)
    fig_bar, ax_bar = plt.subplots(figsize=(10, 6))
    fig_bar.patch.set_facecolor(BG_COLOR)
    ax_bar.set_facecolor(BG_COLOR)

    b_total_vals = [results[s]["total_biceps_rms"] for s in subjects_list]
    t_total_vals = [results[s]["total_triceps_rms"] for s in subjects_list]

    bars_b = ax_bar.bar(x - width/2, b_total_vals, width,
                        color=BICEPS_COLOR, alpha=0.9, zorder=3,
                        edgecolor="#1E40AF", linewidth=0.8, label="Biceps")
    bars_t = ax_bar.bar(x + width/2, t_total_vals, width,
                        color=TRICEPS_COLOR, alpha=0.9, zorder=3,
                        edgecolor="#991B1B", linewidth=0.8, label="Triceps")

    for bar, val in zip(bars_b, b_total_vals):
        ax_bar.annotate(f"{val:.1f}", xy=(bar.get_x() + bar.get_width()/2, val),
                        xytext=(0, 6), textcoords="offset points", ha="center", va="bottom",
                        color=BICEPS_COLOR, fontsize=10, fontweight="bold")
    for bar, val in zip(bars_t, t_total_vals):
        ax_bar.annotate(f"{val:.1f}", xy=(bar.get_x() + bar.get_width()/2, val),
                        xytext=(0, 6), textcoords="offset points", ha="center", va="bottom",
                        color=TRICEPS_COLOR, fontsize=10, fontweight="bold")

    top_val = max(max(b_total_vals), max(t_total_vals))
    ax_bar.set_ylim(0, top_val * 1.25)
    ax_bar.yaxis.grid(True, color=GRID_COLOR, linestyle="--", linewidth=0.8, zorder=0)
    ax_bar.set_axisbelow(True)

    ax_bar.set_xticks(x)
    ax_bar.set_xticklabels([s.capitalize() for s in subjects_list], color=TEXT_COLOR, fontsize=12, fontweight="bold")
    ax_bar.tick_params(axis="y", labelcolor=TEXT_COLOR, labelsize=10)
    ax_bar.tick_params(axis="x", bottom=False)

    for sp in ax_bar.spines.values():
        sp.set_edgecolor(BORDER_C); sp.set_linewidth(1.0)

    ax_bar.set_xlabel("Subject", color=TEXT_COLOR, fontsize=12, labelpad=10)
    ax_bar.set_ylabel("Muscular Activity (RMS - Raw ADC)", color=TEXT_COLOR, fontsize=12, labelpad=10)
    ax_bar.set_title(f"EMG Muscular Activity - {load_name} Push Condition\n3-Minute Trial (Biceps vs Triceps)",
                     color=TEXT_COLOR, fontsize=14, fontweight="bold", pad=16)
    ax_bar.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=11, loc="upper right")

    plt.tight_layout(pad=2)
    bar_plot_path = os.path.normpath(out_dir + "/emg_rms_bar_plot.png")
    plt.savefig(bar_plot_path, dpi=200, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig_bar)
    print(f"\n[OK] Bar plot saved -> {bar_plot_path}")

    # Subject Colors Mapping
    subject_color_map = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(subjects_list)}

    # 2. TIME -> RMS PLOT
    fig_rms, (ax_b_rms, ax_t_rms) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    fig_rms.patch.set_facecolor(BG_COLOR)
    fig_rms.suptitle(f"Time -> RMS | {load_name} Push | 5-Second Windows", color=TEXT_COLOR, fontsize=15, fontweight="bold", y=0.98)

    for subj in subjects_list:
        c = subject_color_map[subj]
        lbl = subj.capitalize()
        r_b = results[subj]["biceps_rms_w"]
        r_t = results[subj]["triceps_rms_w"]

        ax_b_rms.plot(TIME_AXIS, r_b, color=c, lw=2.2, alpha=0.95, label=lbl, zorder=3)
        ax_b_rms.fill_between(TIME_AXIS, r_b - r_b.std(), r_b + r_b.std(), color=c, alpha=0.12, zorder=2)

        ax_t_rms.plot(TIME_AXIS, r_t, color=c, lw=2.2, alpha=0.95, label=lbl, zorder=3)
        ax_t_rms.fill_between(TIME_AXIS, r_t - r_t.std(), r_t + r_t.std(), color=c, alpha=0.12, zorder=2)

    style_ax(ax_b_rms, "Biceps RMS per Window", "", "Muscular Activity (RMS - ADC)")
    style_ax(ax_t_rms, "Triceps RMS per Window", "Time (s)", "Muscular Activity (RMS - ADC)")

    ax_b_rms.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=10, loc="upper right")
    ax_t_rms.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=10, loc="upper right")
    ax_t_rms.set_xticks(np.arange(0, 181, 30))
    ax_t_rms.set_xlim(0, 180)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    time_rms_path = os.path.normpath(out_dir + "/emg_time_rms.png")
    plt.savefig(time_rms_path, dpi=200, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig_rms)
    print(f"[OK] Time -> RMS plot saved -> {time_rms_path}")

    # 3. TIME -> MDF PLOT
    fig_mdf, (ax_b_mdf, ax_t_mdf) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
    fig_mdf.patch.set_facecolor(BG_COLOR)
    fig_mdf.suptitle(f"Time -> Median Frequency (MDF) | {load_name} Push | 5-Second Windows", color=TEXT_COLOR, fontsize=15, fontweight="bold", y=0.98)

    for subj in subjects_list:
        c = subject_color_map[subj]
        lbl = subj.capitalize()
        m_b = results[subj]["biceps_mdf_w"]
        m_t = results[subj]["triceps_mdf_w"]

        ax_b_mdf.plot(TIME_AXIS, m_b, color=c, lw=2.2, alpha=0.95, label=lbl, zorder=3)
        ax_b_mdf.fill_between(TIME_AXIS, m_b - m_b.std(), m_b + m_b.std(), color=c, alpha=0.12, zorder=2)

        ax_t_mdf.plot(TIME_AXIS, m_t, color=c, lw=2.2, alpha=0.95, label=lbl, zorder=3)
        ax_t_mdf.fill_between(TIME_AXIS, m_t - m_t.std(), m_t + m_t.std(), color=c, alpha=0.12, zorder=2)

    style_ax(ax_b_mdf, "Biceps Median Frequency per Window", "", "MDF (Hz)")
    style_ax(ax_t_mdf, "Triceps Median Frequency per Window", "Time (s)", "MDF (Hz)")

    ax_b_mdf.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=10, loc="upper right")
    ax_t_mdf.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=10, loc="upper right")
    ax_t_mdf.set_xticks(np.arange(0, 181, 30))
    ax_t_mdf.set_xlim(0, 180)

    plt.tight_layout(rect=[0, 0, 1, 0.97])
    time_mdf_path = os.path.normpath(out_dir + "/emg_time_mdf.png")
    plt.savefig(time_mdf_path, dpi=200, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig_mdf)
    print(f"[OK] Time -> MDF plot saved -> {time_mdf_path}")

    return pd.DataFrame(summary_rows)


# ─────────────────────────────────────────────
# MAIN EXECUTION
# ─────────────────────────────────────────────
if __name__ == "__main__":
    all_summaries = {}
    for cfg in LOAD_CONFIGS:
        df_sum = process_load_condition(cfg)
        if df_sum is not None:
            all_summaries[cfg["name"]] = df_sum

    print("\n" + "="*75)
    print("ALL LOAD CONDITIONS PROCESSED SUCCESSFULLY!")
    print("="*75)
    for load_name, df_s in all_summaries.items():
        print(f"\n--- {load_name} Push Summary ---")
        print(df_s.to_string(index=False))
