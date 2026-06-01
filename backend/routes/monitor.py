"""
Monitor Route - Real-time monitoring of projects and pipelines.
"""

from flask import Blueprint, jsonify, request
from services.pipeline_analyzer import PipelineAnalyzer
from services.ai_error_solver import AIErrorSolver
from workers.monitor_worker import MonitorWorker
from utils.logger import setup_logger

logger = setup_logger(__name__)
monitor_bp = Blueprint("monitor", __name__)

pipeline_analyzer = PipelineAnalyzer()
ai_error_solver = AIErrorSolver()
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


@monitor_bp.route("/errors/solve", methods=["POST"])
def solve_error():
    """Use AI to suggest a fix for a given error."""
    data = request.get_json(silent=True) or {}
    error_text = data.get("error", "")
    context = data.get("context", {})

    if not error_text:
        return jsonify({"error": "error text is required"}), 400

    solution = ai_error_solver.suggest_fix(error_text, context=context)
    return jsonify({"solution": solution}), 200


@monitor_bp.route("/reports", methods=["GET"])
def list_reports():
    """List all generated monitoring reports."""
    reports = monitor_worker.get_reports()
    return jsonify({"reports": reports}), 200
