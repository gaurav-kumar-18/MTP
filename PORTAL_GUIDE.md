# MTP Push Task EMG Analysis Web Portal

Welcome to your **Master's Thesis Project (MTP) EMG Push Task Analysis & Comparison Portal**.

This interactive web application provides a clean, modern, and comprehensive platform to visualize, compare, and upload electromyographic (EMG) data for sustained isometric push tasks across loads and subjects.

---

## 🚀 Quick Start

### 1. One-Click Launch
Double-click `start_website.bat` in this folder, or run:
```bash
python app.py
```
This automatically launches the local server and opens your browser at **[http://127.0.0.1:5000/](http://127.0.0.1:5000/)**.

---

## 🔬 Core Features & Interface Structure

### 1. Dashboard Overview
- **Metric Cards**: Quick view of total load conditions (4), unique participants (6), and trials processed (13 trials, 4.68 million samples).
- **Global Scaling Charts**: 
  - **RMS Muscular Activity vs External Load (2.5kg to 10kg)** showing agonist (Triceps) vs antagonist/stabilizer (Biceps) recruitment.
  - **Median Frequency (MDF) Fatigue Scaling** showing spectral shifts across loads.
- **Load Cards**: Instant overview of active subjects, mean RMS, and single-click access to load conditions.

### 2. Loads & Muscles Explorer (`Loads & Muscles` tab)
- **Interactive Multi-Level Filtering**:
  - **Load Selector**: Switch between `2.5 kg`, `5.0 kg`, `7.5 kg`, `10.0 kg`, or `All Loads Combined`.
  - **Muscle Selector**: Toggle `Biceps Brachii`, `Triceps Brachii`, or `Both Muscles`.
  - **Metric Selector**:
    - `Muscular Activity (RMS)`: Dynamic 36-window (0–180s) time series.
    - `Median Frequency (MDF Fatigue)`: Power spectral shift (10–500 Hz band).
    - `Total RMS Bar Chart`: Grouped bar chart comparing total trial muscular effort across subjects.
  - **Interactive Subject Toggles**: Click subject pills (`BALK`, `GAU`, `MIL`, `MUK`, `PRIY`, `SWR`) to toggle their curves on/off dynamically.
- **Publication-Ready Figures**:
  - Embedded high-resolution (200 DPI) white-theme Matplotlib figures (`emg_rms_bar_plot.png`, `emg_time_rms.png`, `emg_time_mdf.png`).
  - Fullscreen click-to-zoom modal and direct **"Download PNG"** button for thesis writeups and papers.

### 3. Comparative Neuromuscular Studio (`Compare Studio` tab)
Three specialized comparative modes:
1. **Subject Across Loads**:
   - Compare a participant (e.g. Gaurav, Milan, Balkaran) across all loads they performed (e.g. 2.5kg vs 5kg vs 7.5kg vs 10kg).
   - Reveals load-dependent neuromuscular recruitment rate and fatigue acceleration.
2. **Multiple Subjects at 1 Load**:
   - Benchmark all participants under identical resistance side-by-side.
3. **Biceps vs Triceps Co-Activation (Head-to-Head)**:
   - Evaluates joint stabilization, agonist-antagonist co-contraction ratios, and differential fatigue decay.
4. **Recruitment & Fatigue Regression Insights Table**:
   - Displays linear slope per kilogram added ($\Delta \text{RMS} / \text{kg}$), initial vs final MDF frequency drop, and fatigue indices.

### 4. Interactive Dataset Table (`Dataset` tab)
- Searchable & filterable table of all 13 trials.
- Real-time search by subject name or load condition.
- Color-coded metrics for positive/negative fatigue drops and Triceps/Biceps co-contraction ratios.
- **"Export CSV"** and **"Export JSON"** buttons to export processed trial data into Excel, R, or Python.

### 5. Upload New Trials (`Upload Trial` tab)
- Drag-and-drop or select new `.xlsx` or `.csv` files.
- Select target load condition (2.5kg, 5kg, 7.5kg, 10kg) and subject (or add a new participant).
- Automated XML streaming processing: automatically crops the 180-second trial (360,000 samples @ 2000 Hz), calculates RMS, windowed RMS, FFT Median Frequency, and updates the entire dashboard immediately!

---

## 📁 Project File Structure

- [`app.py`](file:///c:/Users/acer/Desktop/mtp/app.py): Flask application serving dashboard, APIs, static assets, and upload processor.
- [`extract_mtp_data.py`](file:///c:/Users/acer/Desktop/mtp/extract_mtp_data.py): Fast XML streaming data extractor and statistical regression calculator.
- [`start_website.bat`](file:///c:/Users/acer/Desktop/mtp/start_website.bat): One-click Windows batch launcher.
- `web/`:
  - [`index.html`](file:///c:/Users/acer/Desktop/mtp/web/index.html): Responsive dashboard UI (Tailwind CSS, Inter font, responsive layout).
  - [`js/app.js`](file:///c:/Users/acer/Desktop/mtp/web/js/app.js): Client-side chart rendering (Chart.js), dynamic filtering, modal zoom, comparisons, and export.
  - `data/mtp_data.json`: Structured JSON database of all trials and windowed time series.
  - `data/embedded_data.js`: Embedded fallback dataset ensuring the portal works even offline or via static file viewing.
- `plots/`: Contains high-resolution publication PNGs for `2.5kg`, `5kg`, `7.5kg`, and `10kg`.

