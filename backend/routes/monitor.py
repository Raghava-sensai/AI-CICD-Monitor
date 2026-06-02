"""
Monitor Route - Real-time monitoring of projects and pipelines.
"""

from flask import Blueprint, jsonify, request
from services.pipeline_analyzer import PipelineAnalyzer
from services.ai_error_solver import AIErrorSolver
from services.error_tracker import ErrorTracker
from workers.monitor_worker import MonitorWorker
from utils.logger import setup_logger

logger = setup_logger(__name__)
monitor_bp = Blueprint("monitor", __name__)

pipeline_analyzer = PipelineAnalyzer()
ai_error_solver = AIErrorSolver()
error_tracker = ErrorTracker()
monitor_worker = MonitorWorker()


@monitor_bp.route("/health", methods=["GET"])
def system_health():
    """Return overall system health metrics."""
    health = monitor_worker.get_system_health()
    return jsonify(health), 200


@monitor_bp.route("/projects", methods=["GET"])
def list_projects():
    """List all monitored projects with their current status."""
    projects = monitor_worker.get_all_projects()
    return jsonify({"projects": projects}), 200


@monitor_bp.route("/projects/<string:project_id>", methods=["GET"])
def get_project(project_id: str):
    """Get detailed status for a single project."""
    project = monitor_worker.get_project(project_id)
    if not project:
        return jsonify({"error": "Project not found"}), 404
    return jsonify(project), 200


@monitor_bp.route("/pipeline/analyze", methods=["POST"])
def analyze_pipeline():
    """Analyze CI/CD pipeline logs for errors or bottlenecks."""
    data = request.get_json(silent=True) or {}
    logs = data.get("logs", "")
    project_id = data.get("project_id")

    if not logs:
        return jsonify({"error": "logs are required"}), 400

    analysis = pipeline_analyzer.analyze(logs, project_id=project_id)
    return jsonify({"analysis": analysis}), 200


@monitor_bp.route("/errors/explain", methods=["POST"])
def explain_error():
    """Use AI to explain an error and suggest a fix."""
    data = request.get_json(silent=True) or {}
    error_text = data.get("error", "")
    context = data.get("context", {})

    if not error_text:
        return jsonify({"error": "error text is required"}), 400

    explanation = ai_error_solver.explain_error(error_text, context=context)
    return jsonify(explanation), 200


@monitor_bp.route("/issues/top", methods=["GET"])
def top_issues():
    """Get the most frequent errors across all deployments."""
    issues = error_tracker.get_top_issues(limit=10)
    return jsonify({"issues": issues}), 200


@monitor_bp.route("/reports", methods=["GET"])
def list_reports():
    """List all generated monitoring reports."""
    reports = monitor_worker.get_reports()
    return jsonify({"reports": reports}), 200
