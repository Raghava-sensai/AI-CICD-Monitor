"""
Deployment Route - Manage and query deployments.
Includes file upload endpoint for local project ZIP files.
"""

import os
import uuid
import zipfile
import datetime
from flask import Blueprint, request, jsonify
from services.deployment_service import DeploymentService
from services.language_detector import LanguageDetector
from utils.logger import setup_logger

logger = setup_logger(__name__)
deployment_bp = Blueprint("deployment", __name__)
deployment_service = DeploymentService()
language_detector = LanguageDetector()

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage")
RELEASES_DIR = os.path.join(STORAGE_DIR, "releases")
ALLOWED_EXTENSIONS = {".zip"}


# ── List & details ────────────────────────────────────────────────────────────


@deployment_bp.route("/", methods=["GET"])
def list_deployments():
    """List all tracked deployments."""
    return jsonify({"deployments": deployment_service.list_all()}), 200


@deployment_bp.route("/<string:deployment_id>", methods=["GET"])
def get_deployment(deployment_id: str):
    """Retrieve details for a specific deployment."""
    dep = deployment_service.get(deployment_id)
    if not dep:
        return jsonify({"error": "Deployment not found"}), 404
    return jsonify(dep), 200


@deployment_bp.route("/<string:deployment_id>/status", methods=["GET"])
def deployment_status(deployment_id: str):
    """Get the live status of a deployment."""
    status = deployment_service.get_status(deployment_id)
    dep = deployment_service.get(deployment_id)
    return (
        jsonify(
            {
                "deployment_id": deployment_id,
                "status": status,
                "port": dep.get("port") if dep else None,
                "error": dep.get("error") if dep else None,
                "log_file": dep.get("log_file") if dep else None,
            }
        ),
        200,
    )


@deployment_bp.route("/<string:deployment_id>/log", methods=["GET"])
def deployment_log(deployment_id: str):
    """Return the raw pipeline log for a deployment."""
    dep = deployment_service.get(deployment_id)
    if not dep:
        return jsonify({"error": "Deployment not found"}), 404
    log_file = dep.get("log_file")
    if not log_file:
        # Try the new releases/ layout
        log_file = os.path.join(RELEASES_DIR, deployment_id, "pipeline.log")
    if not os.path.exists(log_file):
        return jsonify({"log": "(no log file yet)"}), 200
    try:
        with open(log_file, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"deployment_id": deployment_id, "log": content}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@deployment_bp.route("/<string:deployment_id>/startup", methods=["GET"])
def startup_log(deployment_id: str):
    """
    Return the startup.log snapshot — shows startup errors instantly.
    Includes ImportError, ModuleNotFoundError, Address already in use, etc.
    """
    dep = deployment_service.get(deployment_id)
    if not dep:
        return jsonify({"error": "Deployment not found"}), 404
    startup_path = os.path.join(RELEASES_DIR, deployment_id, "startup.log")
    if not os.path.exists(startup_path):
        return jsonify({"startup_log": "(not available yet)"}), 200
    try:
        with open(startup_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        return jsonify({"deployment_id": deployment_id, "startup_log": content}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@deployment_bp.route("/global", methods=["GET"])
def global_metadata_endpoint():
    """Return the global deployment state from metadata/global.json."""
    return jsonify(deployment_service.get_global_metadata()), 200




# ── Pipeline stage status ─────────────────────────────────────────────────────


@deployment_bp.route("/<string:deployment_id>/pipeline", methods=["GET"])
def pipeline_stages(deployment_id: str):
    """
    Return CI/CD pipeline stage results for a deployment.
    Reads the log file and extracts stage pass/fail lines.
    """
    dep = deployment_service.get(deployment_id)
    if not dep:
        return jsonify({"error": "Deployment not found"}), 404

    log_file = dep.get("log_file")
    stages = []

    if log_file and os.path.exists(log_file):
        import re

        with open(log_file, encoding="utf-8", errors="replace") as f:
            log_text = f.read()

        # Parse stage result lines  e.g. "✅ Install Dependencies: OK (3.2s)"
        for line in log_text.splitlines():
            m = re.search(
                r"([✅❌⚠️⏭🚀])\s+(.+?):\s+(OK|FAILED|Skipped.+?)\s*\(?([\d.]+s)?\)?",
                line,
            )
            if m:
                icon, name, result, dur = m.groups()
                stages.append(
                    {
                        "stage": name,
                        "status": (
                            "success"
                            if icon in ("✅", "🚀", "⏭")
                            else "warning" if icon == "⚠️" else "failed"
                        ),
                        "duration": dur,
                        "result": result,
                    }
                )

    return (
        jsonify(
            {
                "deployment_id": deployment_id,
                "status": dep.get("status"),
                "port": dep.get("port"),
                "stages": stages,
                "error_summary": dep.get("error"),
            }
        ),
        200,
    )


@deployment_bp.route("/<string:deployment_id>/analysis", methods=["GET"])
def get_analysis(deployment_id: str):
    """Retrieve the cached analysis for a deployment."""
    import json
    dep = deployment_service.get(deployment_id)
    if not dep:
        return jsonify({"error": "Deployment not found"}), 404

    analysis_path = os.path.join(RELEASES_DIR, deployment_id, "analysis.json")
    if not os.path.exists(analysis_path):
        return jsonify({"error": "Analysis not ready or not found"}), 404

    try:
        with open(analysis_path, "r", encoding="utf-8") as f:
            analysis = json.load(f)
        return jsonify(analysis), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@deployment_bp.route("/rollbacks", methods=["GET"])
def list_rollbacks():
    """Return the full rollback history, newest first."""
    history = deployment_service.get_rollback_history()
    return jsonify({"rollbacks": history}), 200


# ── Trigger from GitHub URL ───────────────────────────────────────────────────


@deployment_bp.route("/trigger", methods=["POST"])
def trigger_deployment():
    """Manually trigger a deployment from a GitHub repo URL."""
    data = request.get_json(silent=True) or {}
    repo = data.get("repo")
    branch = data.get("branch", "main")

    if not repo:
        return jsonify({"error": "repo is required (e.g. 'username/repo-name')"}), 400

    result = deployment_service.trigger_deployment({"repo": repo, "branch": branch})
    return jsonify({"status": "triggered", "result": result}), 202


# ── Upload project ZIP ────────────────────────────────────────────────────────


@deployment_bp.route("/upload", methods=["POST"])
def upload_project():
    """
    Upload a ZIP file of any project (Python, Node, Go, Java, Ruby, Rust, PHP…).

    The server will:
      1. Extract the ZIP
      2. Auto-detect the language
      3. Allocate a free port (auto-reallocate if busy)
      4. Run the full CI/CD pipeline (install → build → test → start)
      5. Return the deployment ID to track progress

    Form fields:
      file      (required) — the .zip project archive
      name      (optional) — display name for the project
      branch    (optional) — branch name label (default: "upload")
    """
    if "file" not in request.files:
        return (
            jsonify(
                {
                    "error": "No file uploaded. Send a .zip as multipart form-data with field name 'file'"
                }
            ),
            400,
        )

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Filename is empty"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"error": f"Only .zip files are accepted (got '{ext}')"}), 400

    project_name = request.form.get("name") or os.path.splitext(f.filename)[0]
    branch = request.form.get("branch", "upload")

    # 1. Save ZIP into releases/<id>/source/
    deployment_id = str(uuid.uuid4())
    release_dir = os.path.join(RELEASES_DIR, deployment_id)
    work_dir = os.path.join(release_dir, "source")
    os.makedirs(work_dir, exist_ok=True)

    zip_path = os.path.join(work_dir, "upload.zip")
    f.save(zip_path)
    logger.info(f"ZIP uploaded: {f.filename} → {zip_path}")

    # 2. Extract
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(work_dir)
        os.remove(zip_path)  # clean up zip after extraction
    except zipfile.BadZipFile:
        return jsonify({"error": "Uploaded file is not a valid ZIP archive"}), 400

    # Flatten single top-level folder (common zip layout)
    entries = [e for e in os.listdir(work_dir) if not e.startswith(".")]
    if len(entries) == 1 and os.path.isdir(os.path.join(work_dir, entries[0])):
        inner = os.path.join(work_dir, entries[0])
        for item in os.listdir(inner):
            os.rename(os.path.join(inner, item), os.path.join(work_dir, item))
        os.rmdir(inner)

    # 3. Detect language
    lang_result = language_detector.detect(work_dir)
    language = lang_result["language"]
    logger.info(
        f"Language detected: {language} (confidence={lang_result['confidence']})"
    )

    # 4. Create deployment record and start pipeline
    result = deployment_service.trigger_upload_deployment(
        {
            "deployment_id": deployment_id,
            "repo": f"local/{project_name}",
            "branch": branch,
            "source_dir": work_dir,
            "language": language,
        }
    )

    return (
        jsonify(
            {
                "status": "upload accepted",
                "deployment_id": deployment_id,
                "project_name": project_name,
                "language": language,
                "confidence": lang_result["confidence"],
                "docker_image": lang_result["docker_image"],
                "track_at": f"/api/deployment/{deployment_id}/pipeline",
                "log_at": f"/api/deployment/{deployment_id}/log",
            }
        ),
        202,
    )


# ── Rollback ──────────────────────────────────────────────────────────────────


@deployment_bp.route("/<string:deployment_id>/rollback", methods=["POST"])
def rollback_deployment(deployment_id: str):
    """Roll back a deployment to the last successful one."""
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "Manual rollback via API")
    result = deployment_service.rollback(deployment_id, reason=reason)
    if not result.get("success"):
        return jsonify({"error": result.get("reason", "Rollback failed")}), 400
    return jsonify({
        "status": "rolled_back",
        "deployment_id": deployment_id,
        "restored": result.get("restored"),
        "reason": reason,
        "failed_stage": result.get("failed_stage"),
    }), 200
