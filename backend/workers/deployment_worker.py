"""
Deployment Worker - Runs deployments asynchronously in background threads.
Uses the restructured storage layout:

    deployment_storage/
    ├── active/           ← current deployment pointer
    ├── releases/<id>/    ← per-deployment artefacts
    │   ├── source/       ← extracted project files
    │   ├── pipeline.log
    │   ├── analysis.json
    │   └── metadata.json
    ├── rollback/         ← managed by RollbackService
    └── metadata/         ← global state
"""

import os
import json
import threading
import datetime
import zipfile
import shutil
from models.deployment import Deployment, DeploymentStatus
from services.pipeline_runner import PipelineRunner
from services.pipeline_analyzer import PipelineAnalyzer
from services.error_tracker import ErrorTracker
from utils.logger import setup_logger

logger = setup_logger(__name__)

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage")
RELEASES_DIR = os.path.join(STORAGE_DIR, "releases")
MAX_RELEASES = 20          # keep the last 20 releases on disk


class DeploymentWorker:
    """
    Runs deployment in a background thread.
    Supports two sources:
      - GitHub URL  (clone from remote)
      - Local path  (already extracted upload)
    """

    def __init__(self):
        self.runner = PipelineRunner()
        self.analyzer = PipelineAnalyzer()
        self.error_tracker = ErrorTracker()

    def start(self, deployment: Deployment, source_dir: str = None) -> None:
        """Kick off an async deployment thread."""
        thread = threading.Thread(
            target=self._run,
            args=(deployment, source_dir),
            name=f"deploy-{deployment.deployment_id[:8]}",
            daemon=True,
        )
        thread.start()
        logger.info(f"Deployment thread started: {deployment.deployment_id}")

    def rollback(self, deployment: Deployment) -> bool:
        """Synchronous rollback — stop the process and mark rolled back."""
        logger.info(f"Rolling back deployment {deployment.deployment_id}...")
        release_dir = os.path.join(RELEASES_DIR, deployment.deployment_id)
        pid_file = os.path.join(release_dir, "app.pid")
        if os.path.exists(pid_file):
            with open(pid_file) as f:
                pid = f.read().strip()
            try:
                os.kill(int(pid), 9)
                logger.info(f"Killed PID {pid} for rollback.")
            except Exception as e:
                logger.warning(f"Could not kill PID {pid}: {e}")
        return True

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self, deployment: Deployment, source_dir: str = None) -> None:
        release_dir = os.path.join(RELEASES_DIR, deployment.deployment_id)
        # Source files live inside the release directory
        work_dir = source_dir or os.path.join(release_dir, "source")
        log_path = os.path.join(release_dir, "pipeline.log")

        os.makedirs(release_dir, exist_ok=True)
        os.makedirs(work_dir, exist_ok=True)

        deployment.status = DeploymentStatus.RUNNING
        deployment.started_at = datetime.datetime.utcnow().isoformat()
        deployment.log_file = log_path

        try:
            # Clone if no local source provided
            if source_dir is None:
                self._clone(deployment, work_dir, log_path)

            # Run full CI/CD pipeline (including health check)
            result = self.runner.run(deployment, work_dir, log_path)

            deployment.port = result["port"]
            deployment.failed_stage = result.get("failed_stage")

            # Capture health_check_url from the health check stage result
            for stage_result in result.get("stages", []):
                if stage_result.get("stage") == "Health Check" and stage_result.get("success"):
                    deployment.health_check_url = stage_result.get("url")
                    break

            if result["success"]:
                deployment.status = DeploymentStatus.SUCCESS
                logger.info(
                    f"Deployment {deployment.deployment_id[:8]} succeeded "
                    f"(lang={result['language']} port={result['port']})"
                )
                # Update global active/previous pointers
                try:
                    from services import global_metadata
                    global_metadata.on_deployment_success(deployment.deployment_id)
                except Exception as e:
                    logger.warning(f"global_metadata.on_deployment_success failed: {e}")
            else:
                deployment.status = DeploymentStatus.FAILED
                deployment.error = self._format_errors(result["error_summary"])
                logger.error(
                    f"Deployment {deployment.deployment_id[:8]} failed: "
                    f"{deployment.error[:200]}"
                )

        except Exception as exc:
            deployment.status = DeploymentStatus.FAILED
            deployment.error = str(exc)
            logger.error(f"Deployment {deployment.deployment_id} exception: {exc}")

        finally:
            deployment.finished_at = datetime.datetime.utcnow().isoformat()

            # Write startup.log snapshot
            self._write_startup_log(release_dir, log_path)

            # Write metadata.json
            self._write_metadata(deployment, release_dir)

            # Post-deployment analysis and caching
            self._analyze_and_cache(deployment, release_dir, log_path)

            # Enforce log retention (keep last MAX_RELEASES)
            self._prune_old_releases()

    def _clone(self, deployment: Deployment, work_dir: str, log_path: str):
        from utils.shell import run_command

        repo_url = deployment.clone_url or f"https://github.com/{deployment.repo}.git"
        with open(log_path, "w", encoding="utf-8") as log:
            log.write(f"Cloning {repo_url} → {work_dir}\n")
        stdout, stderr, code = run_command(
            ["git", "clone", repo_url, work_dir], timeout=120
        )
        if code != 0:
            raise RuntimeError(
                f"Step 'Cloning repository' failed (exit {code}): {stderr}"
            )
        run_command(["git", "-C", work_dir, "checkout", deployment.branch])

    def _write_metadata(self, deployment: Deployment, release_dir: str):
        """Persist deployment metadata as metadata.json inside the release directory."""
        meta_path = os.path.join(release_dir, "metadata.json")
        try:
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(deployment.to_dict(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write metadata for {deployment.deployment_id}: {e}")

    def _write_startup_log(self, release_dir: str, log_path: str):
        """
        Extract startup-relevant lines from the full pipeline log and save
        as startup.log for instant visibility on failures.

        Captures lines containing common startup errors:
            ImportError, ModuleNotFoundError, SyntaxError,
            Address already in use, Traceback, etc.
        """
        import re
        STARTUP_PATTERNS = re.compile(
            r"(ImportError|ModuleNotFoundError|SyntaxError|"
            r"Address already in use|Traceback|Error:|FAILED|"
            r"\[START\]|\[HEALTH\]|\[FAILED\]|\[SUCCESS\] Health)",
            re.IGNORECASE,
        )
        startup_log_path = os.path.join(release_dir, "startup.log")
        try:
            if not os.path.exists(log_path):
                return
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            # Find the index where the Start stage begins
            start_idx = 0
            for i, line in enumerate(lines):
                if "[START]" in line:
                    start_idx = i
                    break
            # Take lines from Start stage onward, filtered by patterns
            relevant = [
                line for line in lines[start_idx:]
                if STARTUP_PATTERNS.search(line)
            ]
            with open(startup_log_path, "w", encoding="utf-8") as f:
                f.writelines(relevant or ["(no startup errors detected)\n"])
        except Exception as e:
            logger.error(f"Failed to write startup.log: {e}")

    def _analyze_and_cache(self, deployment: Deployment, release_dir: str, log_path: str):
        """Run pipeline analysis once and cache to analysis.json."""
        try:
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    logs = f.read()
                analysis_result = self.analyzer.analyze(logs, deployment.deployment_id)

                # Track global error frequencies
                error_ids = [e["error_id"] for e in analysis_result.get("errors", [])]
                if error_ids:
                    self.error_tracker.record_errors(error_ids)

                analysis_path = os.path.join(release_dir, "analysis.json")
                with open(analysis_path, "w", encoding="utf-8") as f:
                    json.dump(analysis_result, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to analyze deployment {deployment.deployment_id}: {e}")

    def _prune_old_releases(self):
        """Delete the oldest release directories when count exceeds MAX_RELEASES."""
        try:
            os.makedirs(RELEASES_DIR, exist_ok=True)
            entries = []
            for name in os.listdir(RELEASES_DIR):
                path = os.path.join(RELEASES_DIR, name)
                if not os.path.isdir(path):
                    continue
                meta = os.path.join(path, "metadata.json")
                created_at = ""
                if os.path.exists(meta):
                    try:
                        with open(meta) as f:
                            data = json.load(f)
                        created_at = data.get("created_at", "")
                    except Exception:
                        pass
                entries.append((created_at, path))

            if len(entries) <= MAX_RELEASES:
                return

            entries.sort(key=lambda x: x[0])  # oldest first
            to_delete = entries[: len(entries) - MAX_RELEASES]
            for _, path in to_delete:
                shutil.rmtree(path, ignore_errors=True)
                logger.info(f"Pruned old release: {path}")
        except Exception as e:
            logger.error(f"Release pruning failed: {e}")

    @staticmethod
    def _format_errors(error_summary: list) -> str:
        if not error_summary:
            return "Unknown error"
        parts = []
        for e in error_summary:
            parts.append(f"[{e['stage']}] exit={e['exit_code']}\n{e['snippet']}")
        return "\n\n".join(parts)
