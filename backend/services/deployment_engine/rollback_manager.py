import os
import json
from typing import Optional
from utils.logger import setup_logger
from services.deployment_engine.runtime_manager import RuntimeManager
from services.deployment_engine.health_checker import HealthChecker

logger = setup_logger(__name__)

class RollbackManager:
    def __init__(self, runtime: RuntimeManager, storage_dir: str):
        self.runtime = runtime
        self.health_checker = HealthChecker()
        self.rollback_dir = os.path.join(storage_dir, "rollback")
        self.history_file = os.path.join(self.rollback_dir, "rollback_history.json")
        os.makedirs(self.rollback_dir, exist_ok=True)

    def trigger_rollback(self, failed_deployment_id: str, previous_deployment_id: str, previous_config: dict, previous_source_dir: str, port: int) -> bool:
        """
        Executes the physical rollback process:
        Stop Current -> Start Previous -> Verify Health
        """
        logger.info(f"Initiating rollback from {failed_deployment_id} to {previous_deployment_id}")
        
        # 1. Stop Current
        self.runtime.stop(failed_deployment_id)
        
        # 2. Start Previous
        log_path = os.path.join(self.rollback_dir, f"rollback_{failed_deployment_id}.log")
        try:
            self.runtime.start(previous_deployment_id, previous_config, previous_source_dir, port, log_path)
        except Exception as e:
            logger.error(f"Rollback to {previous_deployment_id} failed: {e}")
            from models.deployment import DeploymentStatus
            return {"status": "failed", "error": str(e), "recovery_required": True}
            
        # 3. Verify Health
        health_check_endpoint = previous_config.get("health_check", "/")
        result = self.health_checker.check(port, health_check_endpoint, timeout_sec=30)
        
        if result["status"] == "success":
            logger.info("Rollback successful. Previous release is healthy.")
            self._record(failed_deployment_id, previous_deployment_id, True, "Health check passed")
            return True
        else:
            logger.error("Rollback failed health check.")
            self.runtime.stop(previous_deployment_id)
            self._record(failed_deployment_id, previous_deployment_id, False, "Health check failed")
            return False

    def _record(self, failed_id: str, restored_id: str, success: bool, reason: str):
        records = []
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r") as f:
                    records = json.load(f)
            except Exception:
                pass
                
        import datetime
        records.append({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "failed_deployment": failed_id,
            "restored_deployment": restored_id,
            "success": success,
            "reason": reason
        })
        with open(self.history_file, "w") as f:
            json.dump(records, f, indent=2)
