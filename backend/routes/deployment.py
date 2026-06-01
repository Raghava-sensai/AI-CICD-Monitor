"""
Deployment Route - Manage and query deployments.
"""

from flask import Blueprint, request, jsonify
from services.deployment_service import DeploymentService
from models.deployment import DeploymentStatus
from utils.logger import setup_logger

logger = setup_logger(__name__)
deployment_bp = Blueprint("deployment", __name__)

deployment_service = DeploymentService()


@deployment_bp.route("/", methods=["GET"])
def list_deployments():
    """List all tracked deployments."""
    deployments = deployment_service.list_all()
    return jsonify({"deployments": deployments}), 200


@deployment_bp.route("/<string:deployment_id>", methods=["GET"])
def get_deployment(deployment_id: str):
    """Retrieve details for a specific deployment."""
    deployment = deployment_service.get(deployment_id)
    if not deployment:
        return jsonify({"error": "Deployment not found"}), 404
    return jsonify(deployment), 200


@deployment_bp.route("/trigger", methods=["POST"])
def trigger_deployment():
    """Manually trigger a deployment."""
    data = request.get_json(silent=True) or {}
    repo = data.get("repo")
    branch = data.get("branch", "main")

    if not repo:
        return jsonify({"error": "repo is required"}), 400

    result = deployment_service.trigger_deployment({"repo": repo, "branch": branch})
    return jsonify({"status": "triggered", "result": result}), 202


@deployment_bp.route("/<string:deployment_id>/rollback", methods=["POST"])
def rollback_deployment(deployment_id: str):
    """Roll back a deployment to the previous version."""
    result = deployment_service.rollback(deployment_id)
    if not result:
        return jsonify({"error": "Rollback failed or deployment not found"}), 400
    return jsonify({"status": "rolled back", "deployment_id": deployment_id}), 200


@deployment_bp.route("/<string:deployment_id>/status", methods=["GET"])
def deployment_status(deployment_id: str):
    """Get the live status of a deployment."""
    status = deployment_service.get_status(deployment_id)
    return jsonify({"deployment_id": deployment_id, "status": status}), 200
