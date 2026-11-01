import os
import json
from flask import Flask, jsonify, send_from_directory

app = Flask(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DATA_PATH = os.path.join(ROOT_DIR, "public", "data", "mtp_data.json")

# In case Vercel bundles relative to current dir
if not os.path.exists(DATA_PATH):
    DATA_PATH = os.path.join(CURRENT_DIR, "mtp_data.json")

@app.route("/api/data", methods=["GET"])
def get_data():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    return jsonify({"error": "Data file not found"}), 404

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "MTP EMG Analysis API"})

# Export app for Vercel
app_handler = app
