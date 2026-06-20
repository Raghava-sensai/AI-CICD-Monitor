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
from services.audit_service import AuditService
from services.language_detector import LanguageDetector
from utils.logger import setup_logger
from utils.auth import require_github_token

logger = setup_logger(__name__)
deployment_bp = Blueprint("deployment", __name__)
deployment_service = DeploymentService()
language_detector = LanguageDetector()

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage"))
RELEASES_DIR = os.path.join(STORAGE_DIR, "releases")
ALLOWED_EXTENSIONS = {".zip"}


# ── List & details ────────────────────────────────────────────────────────────


@deployment_bp.route("/", methods=["GET"])
def list_deployments():
    """List all tracked deployments."""
    return jsonify({"deployments": deployment_service.list_all()}), 200

@deployment_bp.route("/audit", methods=["GET"])
def get_audit_trail():
    """List historical audit logs."""
    audit_svc = AuditService(os.path.join(STORAGE_DIR, "audit.db"))
    limit = int(request.args.get("limit", 50))
    audits = audit_svc.get_recent_audits(limit)
    return jsonify({"audits": audits}), 200


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
    data = deployment_service.get_global_metadata()
    
    total = data.get("total_deployments", 0)
    failed = data.get("failed_deployments", 0)
    success = total - failed
    
    success_rate = 100.0
    if total > 0:
        success_rate = (success / total) * 100
        
    mrt = 0
    recovery_times = data.get("recovery_times", [])
    if recovery_times:
        mrt = sum(recovery_times) / len(recovery_times)
        
    data["success_rate"] = round(success_rate, 1)
    data["mean_recovery_time_s"] = round(mrt, 1)
    
    return jsonify(data), 200




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

    stages = []
    stages_path = os.path.join(RELEASES_DIR, deployment_id, "stages.json")
    if os.path.exists(stages_path):
        import json
        try:
            with open(stages_path, "r", encoding="utf-8") as f:
                stages = json.load(f)
            
            # Add formatted status for the frontend
            for stage in stages:
                # Provide a generic result string if one wasn't explicitly captured
                if "result" not in stage:
                    stage["result"] = "OK" if stage.get("success") else "FAILED"
                
                # Standardize status
                if stage.get("status") == "running":
                    pass # Preserve the running status
                elif stage.get("skipped"):
                    stage["status"] = "skipped"
                elif stage.get("success"):
                    stage["status"] = "success"
                elif stage.get("optional"):
                    stage["status"] = "warning"
                else:
                    stage["status"] = "failed"
        except Exception as e:
            logger.error(f"Failed to read stages.json for {deployment_id}: {e}")

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
    if os.path.exists(analysis_path):
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                analysis = json.load(f)
            return jsonify(analysis), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # Fallback if no specific analysis.json is written
    return jsonify({
        "health_score": 0 if dep.get("status") == "failed" else 50,
        "severity": "CRITICAL" if dep.get("status") == "failed" else "WARNING",
        "errors": [{
            "description": dep.get("error") or "Unknown Error",
            "recommendation": "No recommendation available."
        }]
    }), 200


@deployment_bp.route("/rollbacks", methods=["GET"])
def list_rollbacks():
    """Return the full rollback history, newest first."""
    history = deployment_service.get_rollback_history()
    return jsonify({"rollbacks": history}), 200


# ── Trigger from GitHub URL / Webhook ─────────────────────────────────────────

@deployment_bp.route("/webhook/github", methods=["POST"])
def github_webhook():
    """
    True GitHub Webhook endpoint. 
    Verifies X-Hub-Signature-256 and auto-triggers deployment.
    """
    import hmac
    import hashlib
    
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        logger.error("GITHUB_WEBHOOK_SECRET is not set, rejecting webhook.")
        return jsonify({"error": "Webhook secret not configured on server"}), 500

    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        return jsonify({"error": "Missing X-Hub-Signature-256 header"}), 401

    payload = request.get_data()
    expected_mac = hmac.new(
        secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256
    ).hexdigest()
    expected_signature = f"sha256={expected_mac}"

    if not hmac.compare_digest(expected_signature, signature):
        logger.warning("Invalid webhook signature received.")
        return jsonify({"error": "Invalid signature"}), 401

    data = request.get_json(silent=True) or {}
    
    # Handle GitHub's initial ping event
    if "zen" in data:
        return jsonify({"status": "ping received"}), 200

    ref = data.get("ref")
    if not ref:
        return jsonify({"error": "Missing ref in payload (not a push event?)"}), 400

    ALLOWED_BRANCHES = {"refs/heads/main", "refs/heads/master"}
    if ref not in ALLOWED_BRANCHES:
        logger.info(f"Ignored push to branch: {ref}")
        return jsonify({"message": f"Branch {ref} ignored"}), 200
        
    branch = ref.replace("refs/heads/", "")
    repository = data.get("repository", {})
    repo = repository.get("full_name")
    clone_url = repository.get("clone_url")
    
    if not repo or not clone_url:
        return jsonify({"error": "Missing repository information"}), 400

    logger.info(f"Valid webhook received for {repo} on branch {branch}")
    
    result = deployment_service.trigger_deployment({
        "repo": repo,
        "branch": branch,
        "clone_url": clone_url
    })
    
    return jsonify({"status": "triggered", "result": result}), 202

@deployment_bp.route("/github", methods=["POST"])
@require_github_token
def deploy_github_url(github_token: str):
    """Manually trigger a deployment from a GitHub repo URL (via UI)."""
    data = request.get_json(silent=True) or {}
    repo_url = data.get("repo_url")
    branch = data.get("branch", "main")

    if not repo_url:
        return jsonify({"error": "repo_url is required"}), 400

    import re
    repo = repo_url
    match = re.search(r"github\.com/([^/]+/[^/.]+)", repo_url)
    if match:
        repo = match.group(1)
        
    result = deployment_service.trigger_deployment({
        "repo": repo,
        "branch": branch,
        "clone_url": repo_url,
        "github_token": github_token
    })
    return jsonify({"status": "triggered", "result": result}), 202


@deployment_bp.route("/trigger", methods=["POST"])
@require_github_token
def trigger_deployment(github_token: str):
    """Manually trigger a deployment from a GitHub repo URL."""
    data = request.get_json(silent=True) or {}
    repo = data.get("repo")
    branch = data.get("branch", "main")

    if not repo:
        return jsonify({"error": "repo is required (e.g. 'username/repo-name')"}), 400

    result = deployment_service.trigger_deployment({"repo": repo, "branch": branch, "github_token": github_token})
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
    has_zip = "file" in request.files
    has_folder = "files[]" in request.files or "files" in request.files

    if not has_zip and not has_folder:
        return (
            jsonify(
                {
                    "error": "No file uploaded. Send a .zip ('file') or a folder ('files[]')"
                }
            ),
            400,
        )

    # Prepare directories
    deployment_id = str(uuid.uuid4())
    release_dir = os.path.join(RELEASES_DIR, deployment_id)
    work_dir = os.path.join(release_dir, "source")
    os.makedirs(work_dir, exist_ok=True)
    
    project_name = request.form.get("name") or "uploaded-project"
    branch = request.form.get("branch", "upload")

    if has_zip:
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "Filename is empty"}), 400

        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error": f"Only .zip files are accepted (got '{ext}')"}), 400

        if not request.form.get("name"):
            project_name = os.path.splitext(f.filename)[0]

        zip_path = os.path.join(work_dir, "upload.zip")
        f.save(zip_path)
        logger.info(f"ZIP uploaded: {f.filename} -> {zip_path}")

        # Extract
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(work_dir)
            os.remove(zip_path)
        except zipfile.BadZipFile:
            return jsonify({"error": "Uploaded file is not a valid ZIP archive"}), 400

        # Flatten single top-level folder
        entries = [e for e in os.listdir(work_dir) if not e.startswith(".")]
        if len(entries) == 1 and os.path.isdir(os.path.join(work_dir, entries[0])):
            inner = os.path.join(work_dir, entries[0])
            for item in os.listdir(inner):
                os.rename(os.path.join(inner, item), os.path.join(work_dir, item))
            os.rmdir(inner)
            
    else:
        # Handle unzipped folder upload via files[]
        files = request.files.getlist("files[]") or request.files.getlist("files")
        if not files or all(not f.filename for f in files):
            return jsonify({"error": "No files found in folder upload"}), 400
            
        logger.info(f"Folder uploaded: {len(files)} files received.")
        from werkzeug.utils import secure_filename
        
        for f in files:
            if f.filename:
                # Sanitize path to prevent directory traversal
                parts = [secure_filename(p) for p in f.filename.replace("\\", "/").split("/") if p]
                if not parts:
                    continue
                safe_rel_path = os.path.join(*parts)
                full_path = os.path.join(work_dir, safe_rel_path)
                
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                f.save(full_path)
                
        # Flatten single top-level folder (in case browser prepends the folder name to all files)
        entries = [e for e in os.listdir(work_dir) if not e.startswith(".")]
        if len(entries) == 1 and os.path.isdir(os.path.join(work_dir, entries[0])):
            inner = os.path.join(work_dir, entries[0])
            for item in os.listdir(inner):
                os.rename(os.path.join(inner, item), os.path.join(work_dir, item))
            os.rmdir(inner)

    # 2.5 Traverse to find the actual project root using BFS (shallowest match wins)
    actual_root = work_dir
    queue = [work_dir]
    found = False
    
    while queue and not found:
        current_dir = queue.pop(0)
        try:
            entries = os.listdir(current_dir)
        except OSError:
            continue
            
        # Check files in current dir
        for f in entries:
            if f in ("deployment.txt", "deployment.txt.txt", "package.json", "requirements.txt"):
                actual_root = current_dir
                found = True
                
                # Auto-fix deployment.txt.txt if user accidentally saved it that way
                if f == "deployment.txt.txt" and "deployment.txt" not in entries:
                    os.rename(os.path.join(current_dir, "deployment.txt.txt"), os.path.join(current_dir, "deployment.txt"))
                break
                
        # If not found, add subdirectories to queue (skipping heavy/irrelevant ones)
        if not found:
            for d in entries:
                full_path = os.path.join(current_dir, d)
                if os.path.isdir(full_path):
                    if d not in (".git", "node_modules", "venv", ".venv", "__pycache__", "build", "dist", "target"):
                        queue.append(full_path)
            
    if actual_root != work_dir:
        logger.info(f"Nested project root found at: {actual_root}")
        work_dir = actual_root

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
            "github_token": None,
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
