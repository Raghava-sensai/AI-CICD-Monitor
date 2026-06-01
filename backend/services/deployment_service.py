"""
Deployment Service - Orchestrates the full deployment lifecycle.
"""

import uuid
import datetime
from typing import Optional
from models.deployment import Deployment, DeploymentStatus
from services.port_manager import PortManager
from services.ssl_manager import SSLManager
from services.language_detector import LanguageDetector
from workers.deployment_worker import DeploymentWorker
from utils.logger import setup_logger
from utils.shell import run_command

logger = setup_logger(__name__)

# In-memory deployment registry (replace with a DB in production)
_deployments: dict[str, Deployment] = {}


class DeploymentService:
    def __init__(self):
        self.port_manager = PortManager()
        self.ssl_manager = SSLManager()
        self.language_detector = LanguageDetector()
        self.worker = DeploymentWorker()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get(self, deployment_id: str) -> Optional[dict]:
        dep = _deployments.get(deployment_id)
        return dep.to_dict() if dep else None

    def list_all(self) -> list[dict]:
        return [d.to_dict() for d in _deployments.values()]

    def get_status(self, deployment_id: str) -> str:
        dep = _deployments.get(deployment_id)
        return dep.status.value if dep else "not_found"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def trigger_deployment(self, event: dict) -> dict:
        """Create a deployment record and hand off to the worker."""
        deployment_id = str(uuid.uuid4())
        repo = event.get("repo", "unknown")
        branch = event.get("branch", "main")

        port = self.port_manager.allocate()
        deployment = Deployment(
            deployment_id=deployment_id,
            repo=repo,
            branch=branch,
            port=port,
            status=DeploymentStatus.PENDING,
            created_at=datetime.datetime.utcnow().isoformat(),
        )
        _deployments[deployment_id] = deployment

        logger.info(f"Deployment {deployment_id} queued for {repo}@{branch} on port {port}")

        # Kick off async worker
        self.worker.start(deployment)

        return deployment.to_dict()

    def rollback(self, deployment_id: str) -> bool:
        """Roll back to the previous successful deployment."""
        dep = _deployments.get(deployment_id)
        if not dep:
            logger.warning(f"Rollback failed: {deployment_id} not found.")
            return False

        dep.status = DeploymentStatus.ROLLING_BACK
        result = self.worker.rollback(dep)
        if result:
            dep.status = DeploymentStatus.ROLLED_BACK
            logger.info(f"Deployment {deployment_id} rolled back successfully.")
        else:
            dep.status = DeploymentStatus.FAILED
        return result
