"""
Deployment Service - Orchestrates the full deployment lifecycle.
"""

import os
import time
import uuid
import datetime
from typing import Optional
from models.deployment import Deployment, DeploymentStatus
from services.port_manager import PortManager
from services.ssl_manager import SSLManager
from services.language_detector import LanguageDetector
from services.rollback_service import RollbackService
from services import global_metadata
from workers.deployment_worker import DeploymentWorker
from utils.logger import setup_logger

logger = setup_logger(__name__)

# In-memory deployment registry (replace with a DB in production)
_deployments: dict[str, Deployment] = {}


class DeploymentService:
    def __init__(self):
        self.port_manager = PortManager()
        self.ssl_manager = SSLManager()
        self.language_detector = LanguageDetector()
        self.worker = DeploymentWorker()
        self.rollback_svc = RollbackService(_deployments)

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

    def trigger_deployment(self, data: dict) -> dict:
        """
        Create a new deployment record and start it.
        Called by webhook handlers or manual trigger API.
        """
        lock_path = os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage", "deployment.lock")
        try:
            # Simple lock mechanism
            if os.path.exists(lock_path):
                # Check if lock is stale (> 5 mins)
                if time.time() - os.path.getmtime(lock_path) > 300:
                    os.remove(lock_path)
                else:
                    logger.warning("Deployment triggered but another deployment is locking the system.")
            
            with open(lock_path, "w") as f:
                f.write(str(time.time()))

            repo = data.get("repo", "unknown/repo")
            branch = data.get("branch", "main")
            clone_url = data.get("clone_url")
            github_token = data.get("github_token")
            simulation_scenario = data.get("simulation_scenario")
            deployment_id = str(uuid.uuid4())

            port = self.port_manager.allocate()
            previous_id = self._get_current_active_id()

            deployment = Deployment(
                deployment_id=deployment_id,
                repo=repo,
                branch=branch,
                port=port,
                status=DeploymentStatus.PENDING,
                created_at=datetime.datetime.utcnow().isoformat(),
                clone_url=clone_url,
                previous_deployment=previous_id,
            )
            _deployments[deployment_id] = deployment
            global_metadata.on_deployment_created()

            logger.info(
                f"Deployment {deployment_id} queued for {repo}@{branch} on port {port} (Scenario: {simulation_scenario})"
            )

            self.worker.start(deployment, github_token=github_token, simulation_scenario=simulation_scenario)
            return deployment.to_dict()
        finally:
            if os.path.exists(lock_path):
                os.remove(lock_path)

    def trigger_upload_deployment(self, event: dict) -> dict:
        """
        Create a deployment from an already-extracted local directory.
        Used by the /upload endpoint.
        """
        deployment_id = event.get("deployment_id") or str(uuid.uuid4())
        repo = event.get("repo", "local/upload")
        branch = event.get("branch", "upload")
        source_dir = event.get("source_dir")
        github_token = event.get("github_token")

        # Find the current active deployment to record as previous
        previous_id = self._get_current_active_id()

        port = self.port_manager.allocate()
        deployment = Deployment(
            deployment_id=deployment_id,
            repo=repo,
            branch=branch,
            port=port,
            status=DeploymentStatus.PENDING,
            created_at=datetime.datetime.utcnow().isoformat(),
            previous_deployment=previous_id,
        )
        _deployments[deployment_id] = deployment
        global_metadata.on_deployment_created()

        logger.info(
            f"Upload deployment {deployment_id} queued "
            f"(source={source_dir} port={port})"
        )

        self.worker.start(deployment, source_dir=source_dir, github_token=github_token)
        return deployment.to_dict()

    def rollback(self, deployment_id: str, reason: str = "Manual rollback") -> dict:
        """
        Roll back the given deployment to the previous successful one.
        Returns a structured result dict from RollbackService.
        """
        dep = _deployments.get(deployment_id)
        if not dep:
            logger.warning(f"Rollback failed: {deployment_id} not found.")
            return {"success": False, "reason": "Deployment not found"}

        dep.status = DeploymentStatus.ROLLING_BACK
        result = self.rollback_svc.rollback(deployment_id, reason=reason)

        if not result["success"]:
            dep.status = DeploymentStatus.FAILED
        return result

    def notify_success(self, deployment_id: str) -> None:
        """Called by DeploymentWorker when a deployment reaches SUCCESS."""
        global_metadata.on_deployment_success(deployment_id)

    def get_global_metadata(self) -> dict:
        """Return the contents of metadata/global.json."""
        return global_metadata.get()

    def get_rollback_history(self) -> list[dict]:
        """Return all rollback events, newest first."""
        return self.rollback_svc.get_history()

    def recover_deployments(self):
        """Scans database and revives processes that died due to a system reboot."""
        import fcntl
        import os
        import psutil
        
        lock_file = "/tmp/ai-cicd-recovery.lock"
        try:
            # Prevent multiple gunicorn workers from recovering simultaneously
            self._recovery_lock = open(lock_file, "w")
            fcntl.flock(self._recovery_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            return
            
        logger.info("Running reboot recovery sequence...")
        from services.deployment_engine.runtime_manager import NativeRuntimeManager
        from models.deployment import DeploymentStatus
        
        runtime = NativeRuntimeManager()
        for dep_id, dep in _deployments.items():
            if dep.status in (DeploymentStatus.SUCCESS, DeploymentStatus.RUNNING):
                if dep.process_pid and not psutil.pid_exists(dep.process_pid):
                    if dep.working_directory and dep.start_command and dep.port:
                        try:
                            logger.info(f"Reviving {dep_id[:8]} on port {dep.port}...")
                            meta = runtime.restart(
                                deployment_id=dep_id,
                                working_directory=dep.working_directory,
                                start_command=dep.start_command,
                                port=dep.port
                            )
                            dep.process_pid = meta["process_pid"]
                            dep.status = DeploymentStatus.SUCCESS
                            self.save_deployment(dep)
                        except Exception as e:
                            logger.error(f"Failed to recover {dep_id}: {e}")
                            dep.status = DeploymentStatus.FAILED
                            self.save_deployment(dep)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_current_active_id(self) -> Optional[str]:
        """Return the ID of the most recent successful deployment, if any."""
        candidates = [
            d for d in _deployments.values()
            if d.status == DeploymentStatus.SUCCESS
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda d: d.finished_at or d.created_at, reverse=True)
        return candidates[0].deployment_id
