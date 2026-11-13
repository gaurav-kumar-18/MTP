"""
EMG Analysis - Ultra-fast xlsx reader via direct XML streaming (White Theme)
===========================================================================
"""

import os
import sys
import time
import zipfile
import re
import io
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams
import warnings
warnings.filterwarnings("ignore")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR   = r"c:\Users\acer\Desktop\mtp\2.5kg push"
FS         = 2000
DURATION_S = 3 * 60
N_SAMPLES  = FS * DURATION_S

OUTPUT_DIR = "c:/Users/acer/Desktop/mtp"
OUTPUT_PNG = OUTPUT_DIR + "/emg_rms_bar_plot.png"

def read_xlsx_two_cols(filepath, skip_rows=4, max_rows=None):
    from xml.etree.ElementTree import iterparse
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    col0, col1 = [], []
    data_row_idx = -1

    with zipfile.ZipFile(filepath, 'r') as zf:
        with zf.open("xl/worksheets/sheet1.xml") as sheet_xml:
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

    return np.array(col0, dtype=np.float64), np.array(col1, dtype=np.float64)


def rms(arr):
    return np.sqrt(np.mean(np.square(arr)))


def preprocess(biceps_arr, triceps_arr):
    non_zero = (biceps_arr != 0) | (triceps_arr != 0)
    first_valid = int(np.argmax(non_zero)) if non_zero.any() else 0
    biceps_arr  = biceps_arr[first_valid:]
    triceps_arr = triceps_arr[first_valid:]

    if len(biceps_arr) < N_SAMPLES:
        biceps_arr = np.pad(biceps_arr, (0, N_SAMPLES - len(biceps_arr)))
        triceps_arr = np.pad(triceps_arr, (0, N_SAMPLES - len(triceps_arr)))
    else:
        biceps_arr  = biceps_arr[:N_SAMPLES]
        triceps_arr = triceps_arr[:N_SAMPLES]

    return biceps_arr, triceps_arr


results  = {}
subjects = sorted([
    d for d in os.listdir(BASE_DIR)
    if os.path.isdir(os.path.join(BASE_DIR, d))
])

for subject in subjects:
    subject_dir  = os.path.join(BASE_DIR, subject)
    trial_files  = sorted([
        f for f in os.listdir(subject_dir)
        if f.lower().endswith(".xlsx") or f.lower().endswith(".csv")
    ])

    if not trial_files:
        continue

    b_rms_list, t_rms_list = [], []

    for tf in trial_files:
        fp = os.path.join(subject_dir, tf)
        b_arr, t_arr = read_xlsx_two_cols(fp, skip_rows=4, max_rows=N_SAMPLES + 10000)
        b_arr, t_arr = preprocess(b_arr, t_arr)

        b_rms_list.append(rms(b_arr))
        t_rms_list.append(rms(t_arr))

    results[subject] = {
        "biceps_rms":  float(np.mean(b_rms_list)),
        "triceps_rms": float(np.mean(t_rms_list)),
    }

# ─────────────────────────────────────────────
# PLOT — Grouped Bar Chart (White Background)
# ─────────────────────────────────────────────
rcParams["font.family"] = "DejaVu Sans"

subjects_list = list(results.keys())
biceps_vals   = [results[s]["biceps_rms"]  for s in subjects_list]
triceps_vals  = [results[s]["triceps_rms"] for s in subjects_list]

x     = np.arange(len(subjects_list))
width = 0.35

BICEPS_COLOR  = "#2563EB"  # Royal Blue
TRICEPS_COLOR = "#DC2626"  # Crimson Red
BG_COLOR      = "#FFFFFF"
TEXT_COLOR    = "#111111"
BORDER_C      = "#CBD5E1"
GRID_C        = "#E2E8F0"

fig, ax = plt.subplots(figsize=(10, 6))
fig.patch.set_facecolor(BG_COLOR)
ax.set_facecolor(BG_COLOR)

bars_b = ax.bar(x - width/2, biceps_vals,  width,
                color=BICEPS_COLOR,  alpha=0.9, zorder=3,
                edgecolor="#1E40AF", linewidth=0.8, label="Biceps")
bars_t = ax.bar(x + width/2, triceps_vals, width,
                color=TRICEPS_COLOR, alpha=0.9, zorder=3,
                edgecolor="#991B1B", linewidth=0.8, label="Triceps")

def annotate_bars(bars, color):
    for bar in bars:
        h = bar.get_height()
        ax.annotate(f"{h:.1f}",
                    xy=(bar.get_x() + bar.get_width()/2, h),
                    xytext=(0, 6), textcoords="offset points",
                    ha="center", va="bottom",
                    color=color, fontsize=10, fontweight="bold")

annotate_bars(bars_b, BICEPS_COLOR)
annotate_bars(bars_t, TRICEPS_COLOR)

top_val = max(max(biceps_vals), max(triceps_vals))
ax.set_ylim(0, top_val * 1.25)
ax.yaxis.grid(True, color=GRID_C, linestyle="--", linewidth=0.8, zorder=0)
ax.set_axisbelow(True)

ax.set_xticks(x)
ax.set_xticklabels([s.capitalize() for s in subjects_list],
                   color=TEXT_COLOR, fontsize=12, fontweight="bold")
ax.tick_params(axis="y", labelcolor=TEXT_COLOR, labelsize=10)
ax.tick_params(axis="x", bottom=False)

for sp in ax.spines.values():
    sp.set_edgecolor(BORDER_C)
    sp.set_linewidth(1.0)

ax.set_xlabel("Subject", color=TEXT_COLOR, fontsize=12, labelpad=10)
ax.set_ylabel("Muscular Activity (RMS - Raw ADC)", color=TEXT_COLOR, fontsize=12, labelpad=10)
ax.set_title("EMG Muscular Activity - 2.5 kg Push Condition\n"
             "3-Minute Trial (Biceps vs Triceps)",
             color=TEXT_COLOR, fontsize=14, fontweight="bold", pad=16)

ax.legend(handles=[
    mpatches.Patch(color=BICEPS_COLOR,  label="Biceps"),
    mpatches.Patch(color=TRICEPS_COLOR, label="Triceps"),
], frameon=True, facecolor="white", edgecolor=BORDER_C,
   labelcolor=TEXT_COLOR, fontsize=11, loc="upper right")

plt.tight_layout(pad=2)
plt.savefig(OUTPUT_PNG, dpi=200, bbox_inches="tight", facecolor=BG_COLOR)
print(f"[OK] Bar plot saved -> {OUTPUT_PNG}")
