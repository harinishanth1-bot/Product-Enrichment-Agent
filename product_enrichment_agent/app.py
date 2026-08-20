"""
Flask Web Application for Product Data Enrichment Agent
Provides web interface for file upload, configuration, real-time enrichment monitoring, and artifact downloads.
"""

import json
import logging
import os
import threading
import uuid
from typing import Dict, Any
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd

from pd_enrichment.detector import detect_columns
from pd_enrichment.enricher_genai import GroundingEnricher, trigger_adc_login_terminal
from run_enrichment import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024  # 32 MB limit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# In-memory store for background tasks
TASKS: Dict[str, Dict[str, Any]] = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/architecture")
def architecture_view():
    return render_template("architecture.html")




@app.route("/api/preflight", methods=["GET"])
def preflight_check():
    """System preflight check for ADC & GenAI availability."""
    project_id = request.args.get("project_id") or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT_ID")
    model_name = request.args.get("model_name", "gemini-2.5-flash")
    
    enricher = GroundingEnricher(project_id=project_id, model_name=model_name)
    check_status = enricher.check_preflight()
    return jsonify(check_status)


@app.route("/api/reauth", methods=["POST"])
def trigger_reauth():
    """Triggers terminal window for 1-click gcloud auth application-default login."""
    success = trigger_adc_login_terminal()
    if success:
        return jsonify({"status": "started", "message": "Terminal launched! Complete browser login in the opened terminal."})
    else:
        return jsonify({"status": "error", "message": "Failed to launch reauth terminal."}), 500


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Handles file upload and returns column schema analysis."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Selected file is empty"}), 400

    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext not in [".csv", ".xlsx", ".xls"]:
        return jsonify({"error": "Unsupported file format. Please upload a .csv or .xlsx file."}), 400

    file_id = str(uuid.uuid4())[:8]
    saved_filename = f"{file_id}_{filename}"
    file_path = os.path.join(UPLOAD_FOLDER, saved_filename)
    file.save(file_path)

    # Inspect schema
    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)

        columns = list(df.columns)
        schema = detect_columns(columns)
        
        return jsonify({
            "file_id": file_id,
            "filename": filename,
            "file_path": file_path,
            "total_rows": len(df),
            "columns": columns,
            "identity_columns": schema["identity_columns"],
            "attribute_columns": schema["attribute_columns"],
            "recommended_search_column": schema["primary_search_column"]
        })
    except Exception as e:
        logger.error(f"Failed to parse uploaded file: {e}")
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500


@app.route("/api/process", methods=["POST"])
def process_enrichment():
    """Triggers asynchronous product enrichment process."""
    data = request.json or {}
    file_path = data.get("file_path")
    search_column = data.get("search_column")
    target_attributes = data.get("target_attributes") # List of selected attribute columns
    use_genai = data.get("use_genai", True)
    genai_project = data.get("genai_project")
    genai_model = data.get("genai_model", "gemini-2.5-flash")
    confidence_threshold = int(data.get("confidence_threshold", 75))
    max_search_depth = int(data.get("max_search_depth", 3))
    max_concurrency = int(data.get("max_concurrency", 5))

    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "Invalid or missing file path"}), 400

    task_id = str(uuid.uuid4())[:8]
    ext = os.path.splitext(file_path)[1].lower()
    out_ext = ".xlsx" if ext in [".xlsx", ".xls"] else ".csv"
    
    out_file = os.path.join(OUTPUT_FOLDER, f"enriched_{task_id}{out_ext}")
    evidence_json = os.path.join(OUTPUT_FOLDER, f"evidence_{task_id}.json")
    review_csv = os.path.join(OUTPUT_FOLDER, f"review_{task_id}.csv")

    TASKS[task_id] = {
        "status": "processing",
        "stage_id": 1,
        "stage_name": "File Ingestion & Schema Analysis",
        "progress": 0,
        "message": "Initializing process...",
        "stage_details": {},
        "summary": None,
        "error": None,
        "out_file": out_file,
        "evidence_json": evidence_json,
        "review_csv": review_csv
    }

    def background_task():
        def update_progress(data):
            if task_id in TASKS:
                if isinstance(data, dict):
                    TASKS[task_id]["stage_id"] = data.get("stage_id", 1)
                    TASKS[task_id]["stage_name"] = data.get("stage_name", "")
                    TASKS[task_id]["message"] = data.get("message", "")
                    TASKS[task_id]["progress"] = data.get("progress", 0)
                    TASKS[task_id]["stage_details"] = data.get("details", {})
                else:
                    TASKS[task_id]["message"] = str(data)

        try:
            res = run_pipeline(
                input_file=file_path,
                output_file=out_file,
                evidence_json=evidence_json,
                review_csv=review_csv,
                search_column=search_column,
                target_attributes=target_attributes,
                use_genai=use_genai,
                genai_project=genai_project,
                genai_model=genai_model,
                confidence_threshold=confidence_threshold,
                max_search_depth=max_search_depth,
                max_concurrency=max_concurrency,
                progress_callback=update_progress
            )
            TASKS[task_id]["status"] = "completed"
            TASKS[task_id]["stage_id"] = 6
            TASKS[task_id]["stage_name"] = "Export & Artifact Generation"
            TASKS[task_id]["progress"] = 100
            TASKS[task_id]["message"] = "Enrichment completed successfully!"
            TASKS[task_id]["summary"] = res
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            TASKS[task_id]["status"] = "failed"
            TASKS[task_id]["error"] = str(e)
            TASKS[task_id]["message"] = f"Error: {str(e)}"

    thread = threading.Thread(target=background_task)
    thread.start()

    return jsonify({"task_id": task_id, "status": "started"})


@app.route("/api/status/<task_id>")
def get_status(task_id):
    """Checks progress status of a running task."""
    task = TASKS.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(task)


@app.route("/download/output/<task_id>")
def download_output(task_id):
    task = TASKS.get(task_id)
    if not task or not os.path.exists(task["out_file"]):
        return jsonify({"error": "Output file not found"}), 404
    return send_file(task["out_file"], as_attachment=True)


@app.route("/download/evidence/<task_id>")
def download_evidence(task_id):
    task = TASKS.get(task_id)
    if not task or not os.path.exists(task["evidence_json"]):
        return jsonify({"error": "Evidence file not found"}), 404
    return send_file(task["evidence_json"], as_attachment=True)


@app.route("/download/review/<task_id>")
def download_review(task_id):
    task = TASKS.get(task_id)
    if not task or not os.path.exists(task["review_csv"]):
        return jsonify({"error": "Review file not found"}), 404
    return send_file(task["review_csv"], as_attachment=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
