"""
Global Metadata Manager
-----------------------
Manages deployment_storage/metadata/global.json

Tracks:
  - active_deployment     : currently live deployment ID
  - previous_deployment   : the one that was active before the current
  - total_deployments     : running count of all deployments created
  - total_rollbacks       : running count of rollbacks performed
  - last_successful       : ID of the last deployment that reached SUCCESS
"""

import os
import json
from utils.logger import setup_logger

logger = setup_logger(__name__)

STORAGE_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "deployment_storage"
)
METADATA_DIR = os.path.join(STORAGE_DIR, "metadata")
GLOBAL_FILE = os.path.join(METADATA_DIR, "global.json")

_DEFAULTS = {
    "active_deployment": None,
    "previous_deployment": None,
    "total_deployments": 0,
    "total_rollbacks": 0,
    "last_successful": None,
}


def _read() -> dict:
    os.makedirs(METADATA_DIR, exist_ok=True)
    if not os.path.exists(GLOBAL_FILE):
        return dict(_DEFAULTS)
    try:
        with open(GLOBAL_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Back-fill any missing keys from defaults
        for k, v in _DEFAULTS.items():
            data.setdefault(k, v)
        return data
    except Exception as e:
        logger.error(f"Failed to read global.json: {e}")
        return dict(_DEFAULTS)


def _write(data: dict) -> None:
    os.makedirs(METADATA_DIR, exist_ok=True)
    try:
        with open(GLOBAL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write global.json: {e}")


def get() -> dict:
    """Return current global metadata."""
    return _read()


def on_deployment_created() -> None:
    """Increment total_deployments counter."""
    data = _read()
    data["total_deployments"] += 1
    _write(data)


def on_deployment_success(deployment_id: str) -> None:
    """
    Promote a deployment to active.
    Previous active becomes previous_deployment pointer.
    """
    data = _read()
    old_active = data.get("active_deployment")
    data["previous_deployment"] = old_active
    data["active_deployment"] = deployment_id
    data["last_successful"] = deployment_id
    _write(data)
    logger.info(
        f"Global state: active={deployment_id} "
        f"previous={old_active}"
    )


def on_rollback(restored_id: str) -> None:
    """
    Swap active ↔ previous and increment rollback counter.
    """
    data = _read()
    # The failed deployment's ID is currently active — demote it
    failed_active = data.get("active_deployment")
    data["previous_deployment"] = failed_active
    data["active_deployment"] = restored_id
    data["total_rollbacks"] += 1
    _write(data)
    logger.info(
        f"Global state after rollback: active={restored_id} "
        f"previous={failed_active} rollbacks={data['total_rollbacks']}"
    )


def get_previous_active() -> str | None:
    """Return the previous active deployment ID (used by RollbackService)."""
    return _read().get("previous_deployment")
