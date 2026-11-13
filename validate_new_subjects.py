"""
Comprehensive Validation of Ritesh and Tapas Datasets
"""
import os
import zipfile
import re
import numpy as np
from scipy import stats

BASE_MTP_DIR = "c:/Users/acer/Desktop/mtp"
FS = 2000
WINDOW_S = 5
WINDOW_SAMP = FS * WINDOW_S
N_WINDOWS = 36
N_SAMPLES = N_WINDOWS * WINDOW_SAMP

def read_xlsx_full(filepath):
    from xml.etree.ElementTree import iterparse
    NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    col0, col1 = [], []
    headers = []
    data_row_idx = -1

    with zipfile.ZipFile(filepath, 'r') as zf:
        sheet_names = [name for name in zf.namelist() if name.startswith("xl/worksheets/sheet")]
        sheet_file = sheet_names[0] if sheet_names else "xl/worksheets/sheet1.xml"

        with zf.open(sheet_file) as sheet_xml:
            context = iterparse(sheet_xml, events=("start", "end"))
            current_row_cells = {}
            in_row = False
            current_col = None
            current_val = None
            is_shared_string = False

            # shared strings if needed
            shared_strings = []
            if "xl/sharedStrings.xml" in zf.namelist():
                from xml.etree.ElementTree import parse
                with zf.open("xl/sharedStrings.xml") as s_xml:
                    s_tree = parse(s_xml)
                    for si in s_tree.getroot():
                        t_elem = si.find(f"{{{NS}}}t")
                        shared_strings.append(t_elem.text if t_elem is not None else "")

            for event, elem in context:
                tag = elem.tag.replace(f"{{{NS}}}", "")

                if event == "start":
                    if tag == "row":
                        current_row_cells = {}
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
                        if current_col is not None and current_val is not None:
                            if is_shared_string:
                                try:
                                    s_val = shared_strings[int(current_val)]
                                    current_row_cells[current_col] = s_val
                                except:
                                    current_row_cells[current_col] = current_val
                            else:
                                try:
                                    current_row_cells[current_col] = float(current_val)
                                except:
                                    current_row_cells[current_col] = current_val
                        current_col = None
                        current_val = None
                        is_shared_string = False
                    elif tag == "row":
                        in_row = False
                        data_row_idx += 1

                        if data_row_idx < 4:
                            headers.append(current_row_cells)
                            elem.clear()
                            continue

                        c0 = current_row_cells.get(0, None)
                        c1 = current_row_cells.get(1, None)
                        if c0 is not None and c1 is not None and isinstance(c0, (int, float)) and isinstance(c1, (int, float)):
                            col0.append(c0)
                            col1.append(c1)

                        current_row_cells = {}
                        elem.clear()

    return headers, np.array(col0, dtype=np.float64), np.array(col1, dtype=np.float64)

def rms(arr):
    valid = arr[~np.isnan(arr)]
    if len(valid) == 0: return 0.0
    return float(np.sqrt(np.mean(np.square(valid))))

def compute_mdf(window, fs=FS):
    valid = window[~np.isnan(window)]
    if len(valid) == 0: return 0.0
    n = len(valid)
    win = np.hamming(n)
    fft_vals = np.fft.rfft(valid * win, n=n)
    psd = np.abs(fft_vals) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0/fs)
    mask = (freqs >= 10) & (freqs <= 500)
    freqs = freqs[mask]
    psd = psd[mask]
    if len(psd) == 0 or psd.sum() == 0: return 0.0
    cumsum = np.cumsum(psd)
    half = cumsum[-1] / 2.0
    idx = np.searchsorted(cumsum, half)
    idx = min(idx, len(freqs) - 1)
    return float(freqs[idx])

# Run check on all loads for ritesh & tapas
loads = ["2.5kg push", "5kg push", "7.5kg push", "10kg push"]
subjects = ["ritesh", "tapas"]

results = []

for l in loads:
    for s in subjects:
        s_dir = os.path.join(BASE_MTP_DIR, l, s)
        if not os.path.exists(s_dir):
            results.append({"load": l, "subject": s, "status": "NOT FOUND"})
            continue
        
        xlsx_file = os.path.join(s_dir, "trial1.xlsx")
        csv_file = os.path.join(s_dir, "trial1.csv")
        
        has_xlsx = os.path.exists(xlsx_file)
        has_csv = os.path.exists(csv_file)
        
        if not has_xlsx:
            results.append({"load": l, "subject": s, "status": "NO XLSX"})
            continue
            
        headers, b_raw, t_raw = read_xlsx_full(xlsx_file)
        total_samples = len(b_raw)
        
        # Check initial zero baseline
        non_zero = (b_raw != 0) | (t_raw != 0)
        first_valid = int(np.argmax(non_zero)) if non_zero.any() else 0
        b_cropped = b_raw[first_valid:first_valid + N_SAMPLES]
        t_cropped = t_raw[first_valid:first_valid + N_SAMPLES]
        
        b_tot_rms = rms(b_cropped)
        t_tot_rms = rms(t_cropped)
        
        # Windowed MDF
        b_mdf_list = []
        t_mdf_list = []
        for i in range(N_WINDOWS):
            bw = b_cropped[i*WINDOW_SAMP : (i+1)*WINDOW_SAMP]
            tw = t_cropped[i*WINDOW_SAMP : (i+1)*WINDOW_SAMP]
            b_mdf_list.append(compute_mdf(bw))
            t_mdf_list.append(compute_mdf(tw))
            
        b_mdf_mean = float(np.mean(b_mdf_list))
        t_mdf_mean = float(np.mean(t_mdf_list))
        
        # Header channel inspection
        # row 1 & row 2
        h_ch1 = headers[1].get(1, "") if len(headers) > 1 else ""
        h_ch2 = headers[2].get(1, "") if len(headers) > 2 else ""
        
        results.append({
            "load": l,
            "subject": s,
            "status": "VALID",
            "has_csv": has_csv,
            "total_raw_rows": total_samples,
            "sufficient_samples": total_samples >= N_SAMPLES,
            "initial_zero_offset": first_valid,
            "ch1_label": h_ch1,
            "ch2_label": h_ch2,
            "biceps_rms": round(b_tot_rms, 2),
            "triceps_rms": round(t_tot_rms, 2),
            "biceps_mdf": round(b_mdf_mean, 2),
            "triceps_mdf": round(t_mdf_mean, 2),
            "ratio_tb": round(t_tot_rms / b_tot_rms if b_tot_rms > 0 else 0, 2)
        })

print("\n" + "="*80)
print("VALIDATION SUMMARY FOR RITESH & TAPAS")
print("="*80)
for r in results:
    if r["status"] == "NOT FOUND":
        print(f"[{r['load']} | {r['subject'].upper()}]: Directory NOT found")
    else:
        print(f"[{r['load']} | {r['subject'].upper()}]:")
        print(f"  Rows: {r['total_raw_rows']:,} (>= 360,000: {r['sufficient_samples']}) | Zero-offset: {r['initial_zero_offset']}")
        print(f"  Header Channels -> Ch1: '{r['ch1_label']}' | Ch2: '{r['ch2_label']}'")
        print(f"  Biceps  RMS: {r['biceps_rms']} | MDF: {r['biceps_mdf']} Hz")
        print(f"  Triceps RMS: {r['triceps_rms']} | MDF: {r['triceps_mdf']} Hz")
        print(f"  Triceps/Biceps Ratio: {r['ratio_tb']}x")
        print(f"  Has duplicate CSV: {r['has_csv']}")
        print()
