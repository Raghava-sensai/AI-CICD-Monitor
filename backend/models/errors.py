"""
Error Models - Structured error types for AI-CICD-Monitor.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import datetime


class ErrorSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    BUILD = "build"
    DEPLOY = "deploy"
    RUNTIME = "runtime"
    NETWORK = "network"
    AUTH = "auth"
    SSL = "ssl"
    DEPENDENCY = "dependency"
    UNKNOWN = "unknown"


@dataclass
class PipelineError:
    """Represents a single error captured from a pipeline run."""

    error_id: str
    deployment_id: str
    message: str
    severity: ErrorSeverity = ErrorSeverity.ERROR
    category: ErrorCategory = ErrorCategory.UNKNOWN
    line_number: Optional[int] = None
    stack_trace: Optional[str] = None
    raw_log: Optional[str] = None
    ai_suggestion: Optional[str] = None
    resolved: bool = False
    timestamp: str = field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat()
    )
    resolution_notes: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["severity"] = self.severity.value
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PipelineError":
        data = dict(data)
        data["severity"] = ErrorSeverity(data.get("severity", "error"))
        data["category"] = ErrorCategory(data.get("category", "unknown"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def resolve(self, notes: str = "") -> None:
        self.resolved = True
        self.resolution_notes = notes

    def __repr__(self) -> str:
        return (
            f"<PipelineError {self.error_id[:8]} "
            f"severity={self.severity.value} "
            f"category={self.category.value} "
            f"resolved={self.resolved}>"
        )


@dataclass
class ErrorReport:
    """Aggregated error report for a deployment or project."""

    report_id: str
    deployment_id: str
    errors: list = field(default_factory=list)  # list[PipelineError]
    generated_at: str = field(
        default_factory=lambda: datetime.datetime.utcnow().isoformat()
    )

    @property
    def total(self) -> int:
        return len(self.errors)

    @property
    def critical_count(self) -> int:
        return sum(1 for e in self.errors if e.severity == ErrorSeverity.CRITICAL)

    @property
    def unresolved_count(self) -> int:
        return sum(1 for e in self.errors if not e.resolved)

    def to_dict(self) -> dict:
        return {
            "report_id": self.report_id,
            "deployment_id": self.deployment_id,
            "generated_at": self.generated_at,
            "total": self.total,
            "critical_count": self.critical_count,
            "unresolved_count": self.unresolved_count,
            "errors": [e.to_dict() for e in self.errors],
        }
