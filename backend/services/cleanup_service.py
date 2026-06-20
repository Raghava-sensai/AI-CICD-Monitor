import os
import shutil
from typing import List, Dict
from models.deployment import DeploymentStatus
from services.audit_service import AuditService
from utils.logger import setup_logger

logger = setup_logger(__name__)

class CleanupService:
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.releases_dir = os.path.join(storage_dir, "releases")
        self.audit = AuditService(os.path.join(storage_dir, "audit.db"))

    def cleanup_old_releases(self, max_success: int = 5, max_failed: int = 10) -> None:
        """
        Retain only the latest `max_success` successful and `max_failed` failed releases.
        Delete the physical directory for older deployments to save disk space.
        """
        try:
            # Note: The active deployment shouldn't be deleted even if it falls out of the bound.
            # But the bounds (5 and 10) are usually safe enough to cover active.
            
            audits = self.audit.get_recent_audits(limit=1000) # Get all deployments
            
            success_count = 0
            failed_count = 0
            to_delete = []

            for record in audits:
                status = record.get("status")
                dep_id = record.get("deployment_id")
                
                if status == DeploymentStatus.SUCCESS:
                    success_count += 1
                    if success_count > max_success:
                        to_delete.append(dep_id)
                elif status in [DeploymentStatus.FAILED, DeploymentStatus.ROLLED_BACK]:
                    failed_count += 1
                    if failed_count > max_failed:
                        to_delete.append(dep_id)

            for dep_id in to_delete:
                path = os.path.join(self.releases_dir, dep_id)
                if os.path.exists(path):
                    shutil.rmtree(path, ignore_errors=True)
                    logger.info(f"Cleaned up old release: {dep_id}")
                    
        except Exception as e:
            logger.error(f"Cleanup service failed: {e}")
