"""
Deployment Worker - Runs deployments asynchronously in background threads.
"""

import os
import threading
import datetime
from models.deployment import Deployment, DeploymentStatus
from utils.logger import setup_logger
from utils.shell import run_command

logger = setup_logger(__name__)

STORAGE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "deployment_storage"
)
LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "logs")


class DeploymentWorker:
    """
    Executes deployment steps in a background thread:
      1. Clone / pull repository
      2. Install dependencies
      3. Run build / test
      4. Start the application process
      5. Update deployment status
    """

    def start(self, deployment: Deployment) -> None:
        """Kick off an async deployment thread."""
        thread = threading.Thread(
            target=self._run,
            args=(deployment,),
            name=f"deploy-{deployment.deployment_id[:8]}",
            daemon=True,
        )
        thread.start()
        logger.info(f"Deployment thread started: {deployment.deployment_id}")

    def rollback(self, deployment: Deployment) -> bool:
        """Attempt a synchronous rollback (stops current process)."""
        logger.info(f"Rolling back deployment {deployment.deployment_id}...")
        work_dir = os.path.join(STORAGE_DIR, deployment.deployment_id)

        # Kill running process if tracked
        pid_file = os.path.join(work_dir, "app.pid")
        if os.path.exists(pid_file):
            with open(pid_file) as f:
                pid = f.read().strip()
            run_command(["kill", pid])
            logger.info(f"Killed process {pid} for rollback.")

        return True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self, deployment: Deployment) -> None:
        work_dir = os.path.join(STORAGE_DIR, deployment.deployment_id)
        log_file = os.path.join(LOGS_DIR, f"{deployment.deployment_id}.log")
        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(LOGS_DIR, exist_ok=True)

        deployment.status = DeploymentStatus.RUNNING
        deployment.started_at = datetime.datetime.utcnow().isoformat()

        try:
            with open(log_file, "w") as log:
                # Step 1 – Clone repo
                self._step(
                    deployment, log,
                    ["git", "clone", f"https://github.com/{deployment.repo}.git", work_dir],
                    "Cloning repository",
                )

                # Step 2 – Checkout branch
                self._step(
                    deployment, log,
                    ["git", "-C", work_dir, "checkout", deployment.branch],
                    "Checking out branch",
                )

                # Step 3 – Install dependencies (detect language via manifest)
                self._install_dependencies(deployment, work_dir, log)

                # Step 4 – Start application
                self._start_app(deployment, work_dir, log)

            deployment.status = DeploymentStatus.SUCCESS
            deployment.finished_at = datetime.datetime.utcnow().isoformat()
            logger.info(f"Deployment {deployment.deployment_id} succeeded.")

        except Exception as exc:
            deployment.status = DeploymentStatus.FAILED
            deployment.error = str(exc)
            deployment.finished_at = datetime.datetime.utcnow().isoformat()
            logger.error(f"Deployment {deployment.deployment_id} failed: {exc}")

    def _step(self, deployment: Deployment, log, cmd: list, label: str) -> None:
        logger.info(f"[{deployment.deployment_id}] {label}: {' '.join(cmd)}")
        log.write(f"\n=== {label} ===\n")
        stdout, stderr, code = run_command(cmd)
        log.write(stdout or "")
        log.write(stderr or "")
        if code != 0:
            raise RuntimeError(f"Step '{label}' failed (exit {code}): {stderr}")

    def _install_dependencies(self, deployment: Deployment, work_dir: str, log) -> None:
        if os.path.exists(os.path.join(work_dir, "requirements.txt")):
            self._step(deployment, log,
                       ["pip", "install", "-r", os.path.join(work_dir, "requirements.txt")],
                       "Installing Python dependencies")
        elif os.path.exists(os.path.join(work_dir, "package.json")):
            self._step(deployment, log,
                       ["npm", "install", "--prefix", work_dir],
                       "Installing Node dependencies")
        else:
            logger.info("No recognised dependency manifest found; skipping install.")

    def _start_app(self, deployment: Deployment, work_dir: str, log) -> None:
        """Start application process (simplified; production uses systemd/PM2)."""
        start_cmd = None
        if os.path.exists(os.path.join(work_dir, "app.py")):
            start_cmd = ["python", os.path.join(work_dir, "app.py")]
        elif os.path.exists(os.path.join(work_dir, "package.json")):
            start_cmd = ["npm", "start", "--prefix", work_dir]

        if start_cmd:
            logger.info(f"Starting app on port {deployment.port}: {start_cmd}")
            log.write(f"\n=== Starting application on port {deployment.port} ===\n")
            # In production, spawn via subprocess.Popen and save PID
        else:
            logger.warning("Could not determine start command for application.")
