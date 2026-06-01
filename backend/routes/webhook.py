"""
Webhook Route - Handles incoming GitHub webhook events.
"""

import hmac
import hashlib
from flask import Blueprint, request, jsonify, current_app
from services.github_service import GithubService
from services.deployment_service import DeploymentService
from utils.logger import setup_logger

logger = setup_logger(__name__)
webhook_bp = Blueprint("webhook", __name__)

github_service = GithubService()
deployment_service = DeploymentService()


def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify the HMAC-SHA256 GitHub webhook signature."""
    mac = hmac.new(secret.encode(), payload, hashlib.sha256)
    expected = "sha256=" + mac.hexdigest()
    return hmac.compare_digest(expected, signature)



@webhook_bp.route("/github", methods=["POST"])
def github_webhook():
    """Receive and process GitHub webhook events."""
    secret = current_app.config.get("GITHUB_WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256", "")

    if secret and not verify_signature(request.data, signature, secret):
        logger.warning("Invalid webhook signature received.")
        return jsonify({"error": "Invalid signature"}), 401

    event = request.headers.get("X-GitHub-Event", "unknown")
    payload = request.get_json(silent=True) or {}

    logger.info(f"Received GitHub event: {event}")

    if event == "push":
        result = github_service.handle_push_event(payload)
        if result.get("should_deploy"):
            deployment_service.trigger_deployment(result)
        return jsonify({"status": "push processed", "data": result}), 200

    elif event == "pull_request":
        result = github_service.handle_pr_event(payload)
        return jsonify({"status": "pr processed", "data": result}), 200

    elif event == "workflow_run":
        result = github_service.handle_workflow_event(payload)
        return jsonify({"status": "workflow processed", "data": result}), 200

    return jsonify({"status": "event ignored", "event": event}), 200


@webhook_bp.route("/ping", methods=["GET"])
def ping():
    """Health check for webhook route."""
    return jsonify({"status": "ok", "service": "webhook"}), 200
