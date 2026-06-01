"""
Monitor Worker - Collects health metrics and generates reports.
"""

import os
import json
import datetime
import threading
import time
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "reports")
POLL_INTERVAL_SECONDS = 60  # Background health check interval


class MonitorWorker:
    """
    Background worker that:
      - Polls deployment health endpoints
      - Aggregates system metrics (CPU, memory, disk)
      - Writes periodic reports to the reports/ directory
    """

    def __init__(self):
        self._projects: dict[str, dict] = {}
        self._running = False
        os.makedirs(REPORTS_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_background_polling(self) -> None:
        """Start the background health-check loop in a daemon thread."""
        if self._running:
            return
        self._running = True
        thread = threading.Thread(
            target=self._poll_loop,
            name="monitor-worker",
            daemon=True,
        )
        thread.start()
        logger.info("Monitor worker polling started.")

    def stop(self) -> None:
        self._running = False

    def register_project(self, project_id: str, metadata: dict) -> None:
        """Register a new project to be monitored."""
        self._projects[project_id] = {
            **metadata,
            "project_id": project_id,
            "status": "unknown",
            "last_checked": None,
        }
        logger.info(f"Project registered for monitoring: {project_id}")

    def get_project(self, project_id: str) -> Optional[dict]:
        return self._projects.get(project_id)

    def get_all_projects(self) -> list[dict]:
        return list(self._projects.values())

    def get_system_health(self) -> dict:
        """Return basic OS resource metrics."""
        try:
            import psutil  # type: ignore
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage("/").percent,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }
        except ImportError:
            return {
                "cpu_percent": None,
                "memory_percent": None,
                "disk_percent": None,
                "note": "psutil not installed; install it for real metrics.",
                "timestamp": datetime.datetime.utcnow().isoformat(),
            }

    def get_reports(self) -> list[dict]:
        """List metadata of all saved report files."""
        reports = []
        for fname in sorted(os.listdir(REPORTS_DIR), reverse=True):
            if fname.endswith(".json"):
                path = os.path.join(REPORTS_DIR, fname)
                reports.append({
                    "filename": fname,
                    "path": path,
                    "size_bytes": os.path.getsize(path),
                    "created_at": datetime.datetime.fromtimestamp(
                        os.path.getctime(path)
                    ).isoformat(),
                })
        return reports

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while self._running:
            self._check_all_projects()
            self._write_report()
            time.sleep(POLL_INTERVAL_SECONDS)

    def _check_all_projects(self) -> None:
        for project_id, project in self._projects.items():
            status = self._ping_project(project)
            project["status"] = status
            project["last_checked"] = datetime.datetime.utcnow().isoformat()

    def _ping_project(self, project: dict) -> str:
        """HTTP health check against the project's health endpoint."""
        url = project.get("health_url")
        if not url:
            return "unknown"
        try:
            import requests
            response = requests.get(url, timeout=5)
            return "healthy" if response.ok else "degraded"
        except Exception:
            return "unreachable"

    def _write_report(self) -> None:
        timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report = {
            "generated_at": datetime.datetime.utcnow().isoformat(),
            "system_health": self.get_system_health(),
            "projects": self.get_all_projects(),
        }
        path = os.path.join(REPORTS_DIR, f"report_{timestamp}.json")
        with open(path, "w") as f:
            json.dump(report, f, indent=2)
        logger.debug(f"Health report written to {path}")
