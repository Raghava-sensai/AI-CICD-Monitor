from flask import Blueprint, request, jsonify
from services.deployment_service import DeploymentService
import uuid

simulator_bp = Blueprint("simulator_bp", __name__)
deployment_svc = DeploymentService()

@simulator_bp.route("/deploy", methods=["POST"])
def simulate_deployment():
    data = request.json or {}
    scenario = data.get("scenario", "SUCCESS")

    # Pass the simulation request to the deployment service
    # We create a dummy webhook payload
    payload = {
        "repo": "simulation/test-app",
        "branch": "main",
        "clone_url": "https://github.com/simulation/test-app.git",
        "simulation_scenario": scenario
    }
    
    deployment = deployment_svc.trigger_deployment(payload)
    return jsonify(deployment), 202
