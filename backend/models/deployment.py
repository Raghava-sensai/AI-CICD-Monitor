"""
Deployment Model - Represents a single deployment lifecycle.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import datetime


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


@dataclass
class Deployment:
    """Tracks a single deployment from trigger to completion."""

    deployment_id: str
    repo: str
    branch: str
    port: int

    # Core status
    status: DeploymentStatus = DeploymentStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat()
    )
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    commit_sha: Optional[str] = None
    clone_url: Optional[str] = None

    # Error / failure info
    error: Optional[str] = None
    failed_stage: Optional[str] = None
    log_file: Optional[str] = None
    process_pid: Optional[int] = None

    # Rollback tracking
    rolled_back: bool = False
    previous_deployment: Optional[str] = None
    rollback_reason: Optional[str] = None

    # Health check
    health_check_url: Optional[str] = None

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value  # Enum → string
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Deployment":
        data = dict(data)
        if "status" in data:
            data["status"] = DeploymentStatus(data["status"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def duration_seconds(self) -> Optional[float]:
        """Return wall-clock duration if both timestamps are available."""
        if self.started_at and self.finished_at:
            start = datetime.datetime.fromisoformat(self.started_at)
            end = datetime.datetime.fromisoformat(self.finished_at)
            return (end - start).total_seconds()
        return None

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            DeploymentStatus.SUCCESS,
            DeploymentStatus.FAILED,
            DeploymentStatus.ROLLED_BACK,
            DeploymentStatus.CANCELLED,
        )

    def __repr__(self) -> str:
        return (
            f"<Deployment {self.deployment_id[:8]} "
            f"repo={self.repo} "
            f"branch={self.branch} "
            f"status={self.status.value}>"
        )
