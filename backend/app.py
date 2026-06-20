"""
AI-CICD-Monitor - Main Flask Application Entry Point
"""

import os
import yaml
from flask import Flask, jsonify, make_response

from routes.webhook import webhook_bp
from routes.deployment import deployment_bp
from routes.monitor import monitor_bp
from routes.simulator import simulator_bp
from routes.templates import templates_bp
from utils.logger import setup_logger

logger = setup_logger(__name__)

def load_config(path: str = "config.yaml") -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", path)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)

def create_app(config: dict = None) -> Flask:
    app = Flask(__name__)

    if config is None:
        config = load_config()

    app.config.update(config)

    # Versioned API routes
    app.register_blueprint(webhook_bp, url_prefix="/api/v1/webhook")
    app.register_blueprint(deployment_bp, url_prefix="/api/v1/deployment")
    app.register_blueprint(monitor_bp, url_prefix="/api/v1/monitor")
    app.register_blueprint(simulator_bp, url_prefix="/api/v1/simulator")
    app.register_blueprint(templates_bp, url_prefix="/api/v1/templates")

    # Recover deployments that died during a server reboot
    try:
        from services import deployment_service
        deployment_service.recover_deployments()
    except Exception as e:
        logger.error(f"Failed to run recovery sequence: {e}")

    @app.route("/")
    def index():
        return jsonify({"message": "AI-CICD-Monitor Backend API is running. Access the frontend via your Vite dev server or Nginx proxy."}), 200

    @app.route("/api/v1")
    def api_index():
        return (
            jsonify(
                {
                    "name": "AI-CICD-Monitor API",
                    "version": "v1",
                    "status": "running",
                    "routes": {
                        "webhook": "/api/v1/webhook",
                        "deployment": "/api/v1/deployment",
                        "monitor": "/api/v1/monitor",
                    },
                }
            ),
            200,
        )

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not Found", "hint": "Check /api/v1 endpoints"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method Not Allowed", "message": str(e)}), 405

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500

    logger.info("AI-CICD-Monitor backend started.")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=False)
