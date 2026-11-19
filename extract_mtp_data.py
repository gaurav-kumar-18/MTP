"""
Extract and serialize all MTP Push Task EMG Analysis data into a structured JSON dataset.
"""

import os
import sys
import json
import time
import zipfile
import re
import numpy as np
from scipy import stats

BASE_MTP_DIR  = "c:/Users/acer/Desktop/mtp"
FS            = 2000
WINDOW_S      = 5
WINDOW_SAMP   = FS * WINDOW_S
N_WINDOWS     = 36
N_SAMPLES     = N_WINDOWS * WINDOW_SAMP  # 360,000

TIME_AXIS     = [(i * WINDOW_S + WINDOW_S / 2.0) for i in range(N_WINDOWS)]

LOAD_CONFIGS = [
    {"id": "2.5kg", "name": "2.5 kg Push", "dir_name": "2.5kg push", "mass_kg": 2.5},
    {"id": "5kg",   "name": "5.0 kg Push", "dir_name": "5kg push",   "mass_kg": 5.0},
    {"id": "7.5kg", "name": "7.5 kg Push", "dir_name": "7.5kg push", "mass_kg": 7.5},
    {"id": "10kg",  "name": "10.0 kg Push", "dir_name": "10kg push",  "mass_kg": 10.0},
]

SUBJECT_FULLNAMES = {
    "balk": "Balkaran",
    "gau": "Gaurav",
    "mil": "Milan",
    "muk": "Mukesh",
    "priy": "Priyanshu",
    "ritesh": "Ritesh",
    "swr": "Swaraj",
    "tapas": "Tapas"
}

def read_xlsx_two_cols(filepath, skip_rows=4, max_rows=None):
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    col0, col1 = [], []
    data_row_idx = -1

    with zipfile.ZipFile(filepath, 'r') as zf:
        sheet_names = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet")]
        sheet_file = sheet_names[0] if sheet_names else "xl/worksheets/sheet1.xml"

        with zf.open(sheet_file) as sheet_xml:
            from xml.etree.ElementTree import iterparse
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

def preprocess(biceps_arr, triceps_arr):
    non_zero = (biceps_arr != 0) | (triceps_arr != 0)
    first_valid = int(np.argmax(non_zero)) if non_zero.any() else 0
    biceps_arr  = biceps_arr[first_valid:]
    triceps_arr = triceps_arr[first_valid:]

    if len(biceps_arr) < N_SAMPLES:
        pad_len = N_SAMPLES - len(biceps_arr)
        biceps_arr = np.pad(biceps_arr, (0, pad_len), constant_values=np.nan)
        triceps_arr = np.pad(triceps_arr, (0, pad_len), constant_values=np.nan)
    else:
        biceps_arr  = biceps_arr[:N_SAMPLES]
        triceps_arr = triceps_arr[:N_SAMPLES]

    return biceps_arr, triceps_arr

def rms(arr):
    valid = arr[~np.isnan(arr)]
    if len(valid) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(valid))))

def compute_mdf(window, fs=FS):
    valid = window[~np.isnan(window)]
    if len(valid) == 0:
        return 0.0
    n = len(valid)
    win = np.hamming(n)
    fft_vals = np.fft.rfft(valid * win, n=n)
    psd = np.abs(fft_vals) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0/fs)

    mask = (freqs >= 10) & (freqs <= 500)
    freqs = freqs[mask]
    psd = psd[mask]

    if len(psd) == 0 or psd.sum() == 0:
        return 0.0

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

def calc_slope(y_vals, x_vals):
    # linear regression slope
    y = np.array(y_vals)
    x = np.array(x_vals)
    mask = ~np.isnan(y)
    if mask.sum() < 2:
        return 0.0, 0.0, 0.0
    res = stats.linregress(x[mask], y[mask])
    return float(res.slope), float(res.intercept), float(res.rvalue)

def extract_all():
    print("Beginning extraction of all MTP data...")
    all_data = {
        "metadata": {
            "title": "MTP Push Task EMG Analysis Portal",
            "task_description": "Isometric Sustained Push Task across Varied Loads",
            "sampling_frequency_hz": FS,
            "duration_seconds": 180,
            "window_size_seconds": WINDOW_S,
            "total_windows": N_WINDOWS,
            "muscles": [
                {
                    "id": "biceps",
                    "name": "Biceps Brachii",
                    "role": "Stabilizer / Antagonist Co-activation",
                    "color": "#3B82F6",
                    "badge_color": "bg-blue-100 text-blue-800 border-blue-300"
                },
                {
                    "id": "triceps",
                    "name": "Triceps Brachii",
                    "role": "Primary Agonist (Push Extensor)",
                    "color": "#EF4444",
                    "badge_color": "bg-red-100 text-red-800 border-red-300"
                }
            ],
            "time_axis": TIME_AXIS,
            "loads": [cfg["id"] for cfg in LOAD_CONFIGS],
            "load_details": LOAD_CONFIGS,
            "subject_fullnames": SUBJECT_FULLNAMES
        },
        "loads": {},
        "subjects": {},
        "comparison_matrix": [],
        "load_scaling_summary": {}
    }

    # Track all unique subjects found
    unique_subjects = set()

    for cfg in LOAD_CONFIGS:
        load_id = cfg["id"]
        load_dir = os.path.join(BASE_MTP_DIR, cfg["dir_name"])
        print(f"\nExtracting load: {load_id} ({load_dir})")

        load_entry = {
            "id": load_id,
            "name": cfg["name"],
            "mass_kg": cfg["mass_kg"],
            "plot_images": {
                "bar_rms": f"/plots/{load_id}/emg_rms_bar_plot.png",
                "time_rms": f"/plots/{load_id}/emg_time_rms.png",
                "time_mdf": f"/plots/{load_id}/emg_time_mdf.png"
            },
            "subjects": {},
            "load_stats": {
                "mean_biceps_rms": 0.0,
                "mean_triceps_rms": 0.0,
                "mean_biceps_mdf": 0.0,
                "mean_triceps_mdf": 0.0,
                "subject_count": 0
            }
        }

        if not os.path.exists(load_dir):
            print(f"Directory not found: {load_dir}")
            continue

        subj_folders = sorted([d for d in os.listdir(load_dir) if os.path.isdir(os.path.join(load_dir, d))])
        
        load_b_rms_totals = []
        load_t_rms_totals = []
        load_b_mdf_means = []
        load_t_mdf_means = []

        for subj in subj_folders:
            unique_subjects.add(subj)
            s_dir = os.path.join(load_dir, subj)
            trial_files = sorted([f for f in os.listdir(s_dir) if f.lower().endswith(('.xlsx', '.csv'))])
            if not trial_files:
                continue

            tf = trial_files[0] # primary trial
            fp = os.path.join(s_dir, tf)
            print(f"  Reading [{load_id} | {subj}] {tf}...")
            
            b_raw, t_raw = read_xlsx_two_cols(fp, skip_rows=4, max_rows=N_SAMPLES + 10000)
            b_sig, t_sig = preprocess(b_raw, t_raw)

            b_tot_rms = rms(b_sig)
            t_tot_rms = rms(t_sig)

            b_rms_w, b_mdf_w = windowed_metrics(b_sig)
            t_rms_w, t_mdf_w = windowed_metrics(t_sig)

            # Slopes
            b_mdf_slope, b_mdf_int, b_mdf_r = calc_slope(b_mdf_w, TIME_AXIS)
            t_mdf_slope, t_mdf_int, t_mdf_r = calc_slope(t_mdf_w, TIME_AXIS)
            b_rms_slope, b_rms_int, b_rms_r = calc_slope(b_rms_w, TIME_AXIS)
            t_rms_slope, t_rms_int, t_rms_r = calc_slope(t_rms_w, TIME_AXIS)

            # MDF % drop from initial window (avg of first 3 windows) to final (avg of last 3 windows)
            b_init_mdf = float(np.mean(b_mdf_w[:3])) if len(b_mdf_w) >= 3 else float(b_mdf_w[0])
            b_final_mdf = float(np.mean(b_mdf_w[-3:])) if len(b_mdf_w) >= 3 else float(b_mdf_w[-1])
            b_mdf_drop_pct = float(((b_final_mdf - b_init_mdf) / b_init_mdf * 100.0) if b_init_mdf > 0 else 0.0)

            t_init_mdf = float(np.mean(t_mdf_w[:3])) if len(t_mdf_w) >= 3 else float(t_mdf_w[0])
            t_final_mdf = float(np.mean(t_mdf_w[-3:])) if len(t_mdf_w) >= 3 else float(t_mdf_w[-1])
            t_mdf_drop_pct = float(((t_final_mdf - t_init_mdf) / t_init_mdf * 100.0) if t_init_mdf > 0 else 0.0)

            ratio_tb = float(t_tot_rms / b_tot_rms) if b_tot_rms > 0 else 0.0

            subj_data = {
                "subject_id": subj,
                "display_name": SUBJECT_FULLNAMES.get(subj, subj.capitalize()),
                "load_id": load_id,
                "file_name": tf,
                "simulation_video": f"/simulations/{load_id}/{subj}.mp4",
                "total_biceps_rms": round(b_tot_rms, 2),
                "total_triceps_rms": round(t_tot_rms, 2),
                "triceps_biceps_ratio": round(ratio_tb, 2),
                "biceps": {
                    "total_rms": round(b_tot_rms, 2),
                    "mean_window_rms": round(float(np.mean(b_rms_w)), 2),
                    "std_window_rms": round(float(np.std(b_rms_w)), 2),
                    "mean_mdf": round(float(np.mean(b_mdf_w)), 2),
                    "std_mdf": round(float(np.std(b_mdf_w)), 2),
                    "mdf_slope_hz_s": round(b_mdf_slope, 4),
                    "mdf_drop_pct": round(b_mdf_drop_pct, 1),
                    "rms_slope": round(b_rms_slope, 4),
                    "rms_series": [round(float(v), 2) for v in b_rms_w],
                    "mdf_series": [round(float(v), 2) for v in b_mdf_w]
                },
                "triceps": {
                    "total_rms": round(t_tot_rms, 2),
                    "mean_window_rms": round(float(np.mean(t_rms_w)), 2),
                    "std_window_rms": round(float(np.std(t_rms_w)), 2),
                    "mean_mdf": round(float(np.mean(t_mdf_w)), 2),
                    "std_mdf": round(float(np.std(t_mdf_w)), 2),
                    "mdf_slope_hz_s": round(t_mdf_slope, 4),
                    "mdf_drop_pct": round(t_mdf_drop_pct, 1),
                    "rms_slope": round(t_rms_slope, 4),
                    "rms_series": [round(float(v), 2) for v in t_rms_w],
                    "mdf_series": [round(float(v), 2) for v in t_mdf_w]
                }
            }

            load_entry["subjects"][subj] = subj_data

            load_b_rms_totals.append(b_tot_rms)
            load_t_rms_totals.append(t_tot_rms)
            load_b_mdf_means.append(float(np.mean(b_mdf_w)))
            load_t_mdf_means.append(float(np.mean(t_mdf_w)))

            # Append to comparison matrix flat table
            all_data["comparison_matrix"].append({
                "load": load_id,
                "load_mass": cfg["mass_kg"],
                "subject": subj,
                "subject_name": SUBJECT_FULLNAMES.get(subj, subj.capitalize()),
                "biceps_total_rms": round(b_tot_rms, 2),
                "triceps_total_rms": round(t_tot_rms, 2),
                "biceps_mean_mdf": round(float(np.mean(b_mdf_w)), 2),
                "triceps_mean_mdf": round(float(np.mean(t_mdf_w)), 2),
                "biceps_fatigue_drop": round(b_mdf_drop_pct, 1),
                "triceps_fatigue_drop": round(t_mdf_drop_pct, 1),
                "triceps_biceps_ratio": round(ratio_tb, 2),
                "simulation_video": f"/simulations/{load_id}/{subj}.mp4"
            })

        if load_b_rms_totals:
            load_entry["load_stats"]["mean_biceps_rms"] = round(float(np.mean(load_b_rms_totals)), 2)
            load_entry["load_stats"]["mean_triceps_rms"] = round(float(np.mean(load_t_rms_totals)), 2)
            load_entry["load_stats"]["mean_biceps_mdf"] = round(float(np.mean(load_b_mdf_means)), 2)
            load_entry["load_stats"]["mean_triceps_mdf"] = round(float(np.mean(load_t_mdf_means)), 2)
            load_entry["load_stats"]["subject_count"] = len(load_entry["subjects"])

        all_data["loads"][load_id] = load_entry

    # Organize by Subject for subject-centric view
    for subj in sorted(list(unique_subjects)):
        all_data["subjects"][subj] = {
            "id": subj,
            "name": SUBJECT_FULLNAMES.get(subj, subj.capitalize()),
            "participated_loads": [],
            "load_data": {}
        }

    for load_id, load_obj in all_data["loads"].items():
        for subj, sdata in load_obj["subjects"].items():
            all_data["subjects"][subj]["participated_loads"].append(load_id)
            all_data["subjects"][subj]["load_data"][load_id] = sdata

    # Calculate Cross-Load trends for subjects present in multiple loads (e.g. Gau, Mil, Balk, Swr)
    for subj, sinfo in all_data["subjects"].items():
        loads_present = [l for l in LOAD_CONFIGS if l["id"] in sinfo["participated_loads"]]
        if len(loads_present) >= 2:
            loads_present.sort(key=lambda x: x["mass_kg"])
            masses = [l["mass_kg"] for l in loads_present]
            b_rms_vals = [sinfo["load_data"][l["id"]]["total_biceps_rms"] for l in loads_present]
            t_rms_vals = [sinfo["load_data"][l["id"]]["total_triceps_rms"] for l in loads_present]
            b_mdf_vals = [sinfo["load_data"][l["id"]]["biceps"]["mean_mdf"] for l in loads_present]
            t_mdf_vals = [sinfo["load_data"][l["id"]]["triceps"]["mean_mdf"] for l in loads_present]

            b_rms_scaling, _, _ = calc_slope(b_rms_vals, masses)
            t_rms_scaling, _, _ = calc_slope(t_rms_vals, masses)

            all_data["load_scaling_summary"][subj] = {
                "name": sinfo["name"],
                "loads": [l["id"] for l in loads_present],
                "masses": masses,
                "biceps_rms": b_rms_vals,
                "triceps_rms": t_rms_vals,
                "biceps_mdf": b_mdf_vals,
                "triceps_mdf": t_mdf_vals,
                "biceps_rms_slope_per_kg": round(b_rms_scaling, 2),
                "triceps_rms_slope_per_kg": round(t_rms_scaling, 2)
            }

    # Save to output files (web, public, docs, api)
    out_json = os.path.join(BASE_MTP_DIR, "web", "data", "mtp_data.json")
    embedded_js_content = "window.EMBEDDED_MTP_DATA = " + json.dumps(all_data, separators=(",", ":")) + ";"

    for data_dir in [
        os.path.join(BASE_MTP_DIR, "web", "data"),
        os.path.join(BASE_MTP_DIR, "public", "data"),
        os.path.join(BASE_MTP_DIR, "docs", "data"),
    ]:
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "mtp_data.json"), "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2)
        with open(os.path.join(data_dir, "embedded_data.js"), "w", encoding="utf-8") as f:
            f.write(embedded_js_content)

    api_dir = os.path.join(BASE_MTP_DIR, "api")
    if os.path.exists(api_dir):
        with open(os.path.join(api_dir, "mtp_data.json"), "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2)

    print(f"\n[SUCCESS] Successfully saved extracted dataset to: {out_json}")
    print(f"Total Subjects: {len(all_data['subjects'])}")
    print(f"Total Comparison Rows: {len(all_data['comparison_matrix'])}")
    return out_json

if __name__ == "__main__":
    extract_all()

