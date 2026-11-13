"""
EMG Windowed Analysis — 2.5 kg Push Condition (White Theme)
================================────────────────────────────
- 5-second windows (10,000 samples @ 2000 Hz) → 36 windows per trial
- Computes RMS and Median Frequency (MDF) per window
- Reports Mean RMS ± SD across windows
- Plot 1: Time → RMS  (white background)
- Plot 2: Time → MDF  (white background)
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

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BASE_DIR      = r"c:\Users\acer\Desktop\mtp\2.5kg push"
FS            = 2000          # Hz
WINDOW_S      = 5             # seconds per window
WINDOW_SAMP   = FS * WINDOW_S # 10,000 samples per window
N_WINDOWS     = 36            # 180s / 5s
N_SAMPLES     = N_WINDOWS * WINDOW_SAMP  # 360,000

OUTPUT_DIR    = "c:/Users/acer/Desktop/mtp"
TIME_AXIS     = np.arange(N_WINDOWS) * WINDOW_S + WINDOW_S / 2

# ─────────────────────────────────────────────
# FAST XLSX READER (XML streaming)
# ─────────────────────────────────────────────
def read_xlsx_two_cols(filepath, skip_rows=4, max_rows=None):
    from xml.etree.ElementTree import iterparse
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

    col0, col1 = [], []
    data_row_idx = -1
    t0 = time.time()

    with zipfile.ZipFile(filepath, 'r') as zf:
        with zf.open("xl/worksheets/sheet1.xml") as xml:
            context = iterparse(xml, events=("start", "end"))
            row_cells = []
            in_row = False
            current_col = None
            current_val = None
            is_str = False

            for event, elem in context:
                tag = elem.tag.replace(f"{{{NS}}}", "")

                if event == "start":
                    if tag == "row":
                        row_cells = []
                        in_row = True
                    elif tag == "c" and in_row:
                        ref = elem.get("r", "")
                        m = re.match(r"([A-Z]+)", ref)
                        if m:
                            letters = m.group(1)
                            cidx = 0
                            for ch in letters:
                                cidx = cidx * 26 + (ord(ch) - ord('A') + 1)
                            current_col = cidx - 1
                        else:
                            current_col = None
                        is_str = (elem.get("t", "") == "s")
                        current_val = None

                elif event == "end":
                    if tag == "v" and in_row and current_col is not None:
                        current_val = elem.text
                    elif tag == "c" and in_row:
                        if current_col is not None and current_val is not None and not is_str:
                            try:
                                row_cells.append((current_col, float(current_val)))
                            except (TypeError, ValueError):
                                pass
                        current_col = None; current_val = None; is_str = False
                    elif tag == "row":
                        in_row = False
                        data_row_idx += 1
                        if data_row_idx < skip_rows:
                            row_cells = []; elem.clear(); continue

                        c0 = c1 = None
                        for (cidx, fval) in row_cells:
                            if cidx == 0: c0 = fval
                            elif cidx == 1: c1 = fval

                        if c0 is not None and c1 is not None:
                            col0.append(c0); col1.append(c1)
                            if max_rows is not None and len(col0) >= max_rows:
                                break

                        row_cells = []; elem.clear()

    return np.array(col0, dtype=np.float64), np.array(col1, dtype=np.float64)


def preprocess(b, t):
    nz = (b != 0) | (t != 0)
    first = int(np.argmax(nz)) if nz.any() else 0
    b, t = b[first:], t[first:]
    if len(b) < N_SAMPLES:
        b = np.pad(b, (0, N_SAMPLES - len(b)))
        t = np.pad(t, (0, N_SAMPLES - len(t)))
    else:
        b, t = b[:N_SAMPLES], t[:N_SAMPLES]
    return b, t


def compute_rms(window):
    return np.sqrt(np.mean(np.square(window)))


def compute_mdf(window, fs=FS):
    n = len(window)
    win = np.hamming(n)
    fft_vals = np.fft.rfft(window * win, n=n)
    psd = np.abs(fft_vals) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0/fs)

    mask = (freqs >= 10) & (freqs <= 500)
    freqs = freqs[mask]
    psd = psd[mask]

    if psd.sum() == 0:
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
        rms_arr[i] = compute_rms(w)
        mdf_arr[i] = compute_mdf(w)
    return rms_arr, mdf_arr


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
subjects = sorted([
    d for d in os.listdir(BASE_DIR)
    if os.path.isdir(os.path.join(BASE_DIR, d))
])

all_results = {}

for subject in subjects:
    subject_dir = os.path.join(BASE_DIR, subject)
    trial_files = sorted([
        f for f in os.listdir(subject_dir)
        if f.lower().endswith(".xlsx") or f.lower().endswith(".csv")
    ])
    if not trial_files:
        continue

    b_rms_trials, t_rms_trials = [], []
    b_mdf_trials, t_mdf_trials = [], []

    for tf in trial_files:
        fp = os.path.join(subject_dir, tf)
        b_raw, t_raw = read_xlsx_two_cols(fp, skip_rows=4, max_rows=N_SAMPLES + 5000)
        b_sig, t_sig = preprocess(b_raw, t_raw)

        b_rms_w, b_mdf_w = windowed_metrics(b_sig)
        t_rms_w, t_mdf_w = windowed_metrics(t_sig)

        b_rms_trials.append(b_rms_w)
        t_rms_trials.append(t_rms_w)
        b_mdf_trials.append(b_mdf_w)
        t_mdf_trials.append(t_mdf_w)

    all_results[subject] = {
        "biceps_rms":  np.mean(b_rms_trials, axis=0),
        "triceps_rms": np.mean(t_rms_trials, axis=0),
        "biceps_mdf":  np.mean(b_mdf_trials, axis=0),
        "triceps_mdf": np.mean(t_mdf_trials, axis=0),
    }

# ─────────────────────────────────────────────
# PLOTTING SETUP (White Theme)
# ─────────────────────────────────────────────
rcParams["font.family"] = "DejaVu Sans"

BG_COLOR   = "#FFFFFF"
TEXT_COLOR = "#111111"
GRID_COLOR = "#E2E8F0"
BORDER_C   = "#CBD5E1"

# Distinct palette optimized for white background
SUBJECT_COLORS = {
    "balk": "#1D4ED8",   # Rich Blue
    "gau":  "#D97706",   # Amber / Gold
    "mil":  "#059669",   # Emerald Green
    "muk":  "#DC2626",   # Bright Red
}

SOLID_ALPHA = 0.95
BAND_ALPHA  = 0.12
LW          = 2.2

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
# PLOT 1: Time → RMS (White Background)
# ─────────────────────────────────────────────
fig1, (ax1b, ax1t) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
fig1.patch.set_facecolor(BG_COLOR)
fig1.suptitle(
    "Time → RMS | 2.5 kg Push | 5-Second Windows",
    color=TEXT_COLOR, fontsize=15, fontweight="bold", y=0.98
)

for subj, v in all_results.items():
    c   = SUBJECT_COLORS.get(subj, "#333333")
    lbl = subj.capitalize()
    rms_b = v["biceps_rms"]
    rms_t = v["triceps_rms"]

    ax1b.plot(TIME_AXIS, rms_b, color=c, lw=LW, alpha=SOLID_ALPHA, label=lbl, zorder=3)
    ax1b.fill_between(TIME_AXIS, rms_b - rms_b.std(), rms_b + rms_b.std(),
                      color=c, alpha=BAND_ALPHA, zorder=2)

    ax1t.plot(TIME_AXIS, rms_t, color=c, lw=LW, alpha=SOLID_ALPHA, label=lbl, zorder=3)
    ax1t.fill_between(TIME_AXIS, rms_t - rms_t.std(), rms_t + rms_t.std(),
                      color=c, alpha=BAND_ALPHA, zorder=2)

style_ax(ax1b, "Biceps RMS per Window", "", "Muscular Activity (RMS - ADC)")
style_ax(ax1t, "Triceps RMS per Window", "Time (s)", "Muscular Activity (RMS - ADC)")

ax1b.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=10, loc="upper right")
ax1t.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=10, loc="upper right")

ax1t.set_xticks(np.arange(0, 181, 30))
ax1t.set_xlim(0, 180)

plt.tight_layout(rect=[0, 0, 1, 0.97])
rms_png = OUTPUT_DIR + "/emg_time_rms.png"
plt.savefig(rms_png, dpi=200, bbox_inches="tight", facecolor=BG_COLOR)
print(f"[OK] RMS plot saved -> {rms_png}")
plt.close(fig1)


# ─────────────────────────────────────────────
# PLOT 2: Time → MDF (White Background)
# ─────────────────────────────────────────────
fig2, (ax2b, ax2t) = plt.subplots(2, 1, figsize=(13, 9), sharex=True)
fig2.patch.set_facecolor(BG_COLOR)
fig2.suptitle(
    "Time → Median Frequency (MDF) | 2.5 kg Push | 5-Second Windows",
    color=TEXT_COLOR, fontsize=15, fontweight="bold", y=0.98
)

for subj, v in all_results.items():
    c   = SUBJECT_COLORS.get(subj, "#333333")
    lbl = subj.capitalize()
    mdf_b = v["biceps_mdf"]
    mdf_t = v["triceps_mdf"]

    ax2b.plot(TIME_AXIS, mdf_b, color=c, lw=LW, alpha=SOLID_ALPHA, label=lbl, zorder=3)
    ax2b.fill_between(TIME_AXIS, mdf_b - mdf_b.std(), mdf_b + mdf_b.std(),
                      color=c, alpha=BAND_ALPHA, zorder=2)

    ax2t.plot(TIME_AXIS, mdf_t, color=c, lw=LW, alpha=SOLID_ALPHA, label=lbl, zorder=3)
    ax2t.fill_between(TIME_AXIS, mdf_t - mdf_t.std(), mdf_t + mdf_t.std(),
                      color=c, alpha=BAND_ALPHA, zorder=2)

style_ax(ax2b, "Biceps Median Frequency per Window", "", "MDF (Hz)")
style_ax(ax2t, "Triceps Median Frequency per Window", "Time (s)", "MDF (Hz)")

ax2b.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=10, loc="upper right")
ax2t.legend(frameon=True, facecolor="white", edgecolor=BORDER_C, labelcolor=TEXT_COLOR, fontsize=10, loc="upper right")

ax2t.set_xticks(np.arange(0, 181, 30))
ax2t.set_xlim(0, 180)

plt.tight_layout(rect=[0, 0, 1, 0.97])
mdf_png = OUTPUT_DIR + "/emg_time_mdf.png"
plt.savefig(mdf_png, dpi=200, bbox_inches="tight", facecolor=BG_COLOR)
print(f"[OK] MDF plot saved -> {mdf_png}")
plt.close(fig2)

# Also update overall bar chart script `emg_analysis.py` with white theme
