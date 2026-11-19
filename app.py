"""
MTP Push Task EMG Analysis Portal - Flask Backend Server
========================================================
Serves the web dashboard, interactive charts, publication plots, and dynamic trial uploads.
"""

import os
import sys
import json
import webbrowser
import threading
from flask import Flask, request, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename

# Import extraction & simulation logic
import extract_mtp_data
try:
    import generate_simulations
except Exception:
    generate_simulations = None

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")
PLOTS_DIR = os.path.join(BASE_DIR, "plots")
SIMULATIONS_DIR = os.path.join(WEB_DIR, "simulations")
DATA_FILE = os.path.join(WEB_DIR, "data", "mtp_data.json")

app = Flask(__name__, static_folder=WEB_DIR, static_url_path="")

# Ensure CORS/clean headers
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# ─────────────────────────────────────────────────────────────
# STATIC & ASSET ROUTES
# ─────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")

@app.route("/js/<path:filename>")
def serve_js(filename):
    return send_from_directory(os.path.join(WEB_DIR, "js"), filename)

@app.route("/css/<path:filename>")
def serve_css(filename):
    return send_from_directory(os.path.join(WEB_DIR, "css"), filename)

@app.route("/data/<path:filename>")
def serve_data(filename):
    return send_from_directory(os.path.join(WEB_DIR, "data"), filename)

@app.route("/plots/<path:filename>")
def serve_plots(filename):
    return send_from_directory(PLOTS_DIR, filename)

@app.route("/simulations/<path:filename>")
def serve_simulations(filename):
    return send_from_directory(SIMULATIONS_DIR, filename, conditional=True)

# ─────────────────────────────────────────────────────────────
# API ROUTES
# ─────────────────────────────────────────────────────────────
@app.route("/api/data", methods=["GET"])
def get_data():
    if not os.path.exists(DATA_FILE):
        extract_mtp_data.extract_all()
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)

@app.route("/api/recalculate", methods=["POST"])
def recalculate():
    try:
        extract_mtp_data.extract_all()
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify({"status": "success", "message": "All data recalculated successfully", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/upload", methods=["POST"])
def upload_trial():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    load_id = request.form.get("load", "2.5kg").strip().lower()
    subject_id = request.form.get("subject", "").strip().lower()

    if not subject_id:
        return jsonify({"error": "Subject identifier is required"}), 400

    # Determine target directory
    dir_name_map = {
        "2.5kg": "2.5kg push",
        "5kg": "5kg push",
        "7.5kg": "7.5kg push",
        "10kg": "10kg push"
    }

    dir_name = dir_name_map.get(load_id, f"{load_id} push")
    target_dir = os.path.join(BASE_DIR, dir_name, subject_id)
    os.makedirs(target_dir, exist_ok=True)

    filename = secure_filename(file.filename)
    if not filename.lower().endswith((".xlsx", ".csv")):
        return jsonify({"error": "File must be an Excel (.xlsx) or CSV file"}), 400

    target_path = os.path.join(target_dir, filename)
    file.save(target_path)
    print(f"[UPLOAD] Saved new trial to {target_path}")

    # Re-run extraction pipeline to update mtp_data.json & generate 3D simulation
    try:
        extract_mtp_data.extract_all()
        if generate_simulations is not None:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            load_obj = data.get("loads", {}).get(load_id, {})
            subj_data = load_obj.get("subjects", {}).get(subject_id)
            if subj_data:
                generate_simulations.generate_single(
                    load_id, subject_id, subj_data, load_obj.get("mass_kg", 2.5)
                )
        return jsonify({
            "status": "success",
            "message": f"Trial uploaded and processed for {subject_id} at {load_id}",
            "filename": filename,
            "path": target_path
        })
    except Exception as e:
        return jsonify({"error": f"Failed to process EMG data: {str(e)}"}), 500

# ─────────────────────────────────────────────────────────────
# LAUNCHER
# ─────────────────────────────────────────────────────────────
def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")

if __name__ == "__main__":
    port = 5000
    print("\n" + "="*65)
    print("MTP PUSH TASK EMG ANALYSIS PORTAL")
    print(f"Server running at: http://127.0.0.1:{port}/")
    print("="*65 + "\n")

    # Auto-open browser in 1 second
    threading.Timer(1.2, open_browser).start()

    app.run(host="0.0.0.0", port=port, debug=False)

