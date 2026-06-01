"""
Project Model - Represents a monitored project.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import datetime


@dataclass
class Project:
    """Represents a GitHub repository being monitored by AI-CICD-Monitor."""

    project_id: str
    repo: str                        # e.g. "owner/repo-name"
    branch: str = "main"
    language: Optional[str] = None
    health_url: Optional[str] = None
    deploy_port: Optional[int] = None
    ssl_enabled: bool = False
    domain: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat()
    )
    last_deployed_at: Optional[str] = None
    status: str = "idle"             # idle | deploying | running | failed | stopped
    tags: list = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Project":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def display_name(self) -> str:
        return self.repo.split("/")[-1]

    def mark_deployed(self) -> None:
        self.last_deployed_at = datetime.datetime.utcnow().isoformat()
        self.status = "running"

    def mark_failed(self) -> None:
        self.status = "failed"

    def __repr__(self) -> str:
        return f"<Project {self.project_id} repo={self.repo} status={self.status}>"
