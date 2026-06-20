"""
Rollback Service - Manages deployment rollbacks and rollback history.
"""

import os
import json
import datetime
from typing import Optional, TYPE_CHECKING
from services import global_metadata
from utils.logger import setup_logger

if TYPE_CHECKING:
    from models.deployment import Deployment

logger = setup_logger(__name__)

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage"))
ROLLBACK_DIR = os.path.join(STORAGE_DIR, "rollback")
HISTORY_FILE = os.path.join(ROLLBACK_DIR, "rollback_history.json")


class RollbackService:
    """
    Manages automatic and manual rollbacks.

    Rollback flow:
        1. Find the last deployment with status SUCCESS (excluding the failed one)
        2. Mark it as the active deployment
        3. Record the rollback event to rollback_history.json
    """

    def __init__(self, deployments_registry: dict):
        """
        Args:
            deployments_registry: The shared in-memory dict of Deployment objects.
        """
        self._deployments = deployments_registry
        os.makedirs(ROLLBACK_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rollback(
        self,
        failed_deployment_id: str,
        reason: str = "Manual rollback",
    ) -> dict:
        """
        Roll back by activating the last successful deployment.

        Returns a dict with keys:
            success (bool), restored (str|None), reason (str), failed_stage (str|None)
        """
        from models.deployment import DeploymentStatus

        failed_dep = self._deployments.get(failed_deployment_id)
        failed_stage = failed_dep.failed_stage if failed_dep else None

        last_good = self._get_last_successful(exclude_id=failed_deployment_id)

        if not last_good:
            logger.warning(
                f"Rollback failed — no successful deployment found "
                f"to restore from {failed_deployment_id}."
            )
            self._record(
                failed_id=failed_deployment_id,
                restored_id=None,
                reason=reason,
                failed_stage=failed_stage,
                success=False,
            )
            return {
                "success": False,
                "restored": None,
                "reason": "No successful deployment found to roll back to.",
                "failed_stage": failed_stage,
            }

        # Mark the failed deployment as rolled back
        if failed_dep:
            failed_dep.status = DeploymentStatus.ROLLED_BACK
            failed_dep.rolled_back = True
            failed_dep.rollback_reason = reason
            failed_dep.previous_deployment = last_good.deployment_id

        # Activate the last good deployment
        self._activate(last_good)

        # Update global.json pointers and counter
        global_metadata.on_rollback(last_good.deployment_id)

        self._record(
            failed_id=failed_deployment_id,
            restored_id=last_good.deployment_id,
            reason=reason,
            failed_stage=failed_stage,
            success=True,
        )

        logger.info(
            f"Rolled back from {failed_deployment_id[:8]} "
            f"to {last_good.deployment_id[:8]} — reason: {reason}"
        )
        return {
            "success": True,
            "restored": last_good.deployment_id,
            "reason": reason,
            "failed_stage": failed_stage,
        }

    def get_history(self) -> list[dict]:
        """Return all recorded rollback events, newest first."""
        if not os.path.exists(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
            return list(reversed(records))
        except Exception as e:
            logger.error(f"Failed to read rollback history: {e}")
            return []

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_last_successful(self, exclude_id: str) -> Optional["Deployment"]:
        """
        Use the global.json previous_deployment pointer for precision.
        Falls back to scanning the in-memory registry if the pointer isn't set.

        Example:
            D1 SUCCESS → D2 SUCCESS → D3 FAILED
            Rollback should restore D2 (the previous active), not D1.
        """
        from models.deployment import DeploymentStatus

        # First try the explicit previous-active pointer
        prev_id = global_metadata.get_previous_active()
        if prev_id and prev_id != exclude_id:
            dep = self._deployments.get(prev_id)
            if dep and dep.status == DeploymentStatus.SUCCESS:
                logger.info(f"Rollback target from global.json pointer: {prev_id}")
                return dep

        # Fallback: scan registry for most-recent successful deployment
        candidates = [
            d for d in self._deployments.values()
            if d.status == DeploymentStatus.SUCCESS
            and d.deployment_id != exclude_id
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda d: d.finished_at or d.created_at,
            reverse=True,
        )
        logger.info(f"Rollback target from scan fallback: {candidates[0].deployment_id}")
        return candidates[0]

    def _activate(self, deployment: "Deployment") -> None:
        """Write the active deployment pointer to disk."""
        active_dir = os.path.join(STORAGE_DIR, "active")
        os.makedirs(active_dir, exist_ok=True)
        pointer = os.path.join(active_dir, "current.json")
        with open(pointer, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "deployment_id": deployment.deployment_id,
                    "repo": deployment.repo,
                    "port": deployment.port,
                    "activated_at": datetime.datetime.utcnow().isoformat(),
                },
                f,
                indent=2,
            )

    def _record(
        self,
        failed_id: str,
        restored_id: Optional[str],
        reason: str,
        failed_stage: Optional[str],
        success: bool,
    ) -> None:
        """Append a rollback event to rollback_history.json."""
        records: list = []
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    records = json.load(f)
            except Exception:
                records = []

        records.append(
            {
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "failed": failed_id,
                "restored": restored_id,
                "reason": reason,
                "failed_stage": failed_stage,
                "success": success,
            }
        )

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
