"""
Pipeline Analyzer - Parses and analyzes CI/CD pipeline logs.
"""

import re
from typing import Optional
from utils.logger import setup_logger
from utils.parser import extract_error_blocks

logger = setup_logger(__name__)

# Common error patterns to scan for
ERROR_PATTERNS = [
    re.compile(r"error:", re.IGNORECASE),
    re.compile(r"FAILED", re.IGNORECASE),
    re.compile(r"Exception", re.IGNORECASE),
    re.compile(r"Traceback", re.IGNORECASE),
    re.compile(r"npm ERR!", re.IGNORECASE),
    re.compile(r"ModuleNotFoundError", re.IGNORECASE),
    re.compile(r"SyntaxError", re.IGNORECASE),
    re.compile(r"connection refused", re.IGNORECASE),
    re.compile(r"No such file or directory", re.IGNORECASE),
]


class PipelineAnalyzer:
    """
    Analyzes raw pipeline / build logs to identify:
    - Errors and their locations
    - Build duration
    - Test results summary
    - Recommendations
    """

    def analyze(self, logs: str, project_id: Optional[str] = None) -> dict:
        """Main entry point: parse and analyse log text."""
        lines = logs.splitlines()
        errors = self._find_errors(lines)
        warnings = self._find_warnings(lines)
        test_summary = self._extract_test_summary(logs)
        duration = self._extract_duration(logs)

        severity = (
            "critical" if len(errors) > 5
            else "high" if errors
            else "low"
        )

        logger.info(
            f"Pipeline analysis for project {project_id}: "
            f"{len(errors)} errors, {len(warnings)} warnings."
        )

        return {
            "project_id": project_id,
            "total_lines": len(lines),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "severity": severity,
            "errors": errors[:20],          # cap output
            "warnings": warnings[:10],
            "test_summary": test_summary,
            "duration_seconds": duration,
            "recommendations": self._build_recommendations(errors),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _find_errors(self, lines: list[str]) -> list[dict]:
        errors = []
        for i, line in enumerate(lines, 1):
            for pattern in ERROR_PATTERNS:
                if pattern.search(line):
                    errors.append({"line_number": i, "content": line.strip()})
                    break
        return errors

    def _find_warnings(self, lines: list[str]) -> list[dict]:
        warnings = []
        warn_pattern = re.compile(r"warn(ing)?", re.IGNORECASE)
        for i, line in enumerate(lines, 1):
            if warn_pattern.search(line):
                warnings.append({"line_number": i, "content": line.strip()})
        return warnings

    def _extract_test_summary(self, logs: str) -> dict:
        """Try to extract pytest / jest / mocha summary lines."""
        summary = {}
        # pytest style: "5 passed, 2 failed in 3.22s"
        m = re.search(r"(\d+) passed", logs)
        if m:
            summary["passed"] = int(m.group(1))
        m = re.search(r"(\d+) failed", logs)
        if m:
            summary["failed"] = int(m.group(1))
        return summary

    def _extract_duration(self, logs: str) -> Optional[float]:
        """Parse total build duration in seconds if present."""
        m = re.search(r"in\s+([\d.]+)s", logs)
        if m:
            return float(m.group(1))
        return None

    def _build_recommendations(self, errors: list[dict]) -> list[str]:
        recs = []
        content = " ".join(e["content"] for e in errors)
        if "ModuleNotFoundError" in content:
            recs.append("Run `pip install -r requirements.txt` to install missing dependencies.")
        if "npm ERR!" in content:
            recs.append("Run `npm install` to restore node_modules.")
        if "connection refused" in content:
            recs.append("Check that dependent services (DB, cache) are running.")
        if not recs and errors:
            recs.append("Review the error lines above and check build configuration.")
        return recs
