"""
Pipeline Analyzer - Parses and analyzes CI/CD pipeline logs.
"""
import re
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Structured mappings: (regex, severity, error_id, problem_desc, fix_desc)
ERROR_MAPPINGS = [
    (re.compile(r"ModuleNotFoundError:\s+No module named\s+'?([^']+)'?", re.IGNORECASE), 
     "Critical 🔴", "MOD-NOT-FOUND", "Module '{}' is missing", "Run pip install {}"),
    
    (re.compile(r"ImportError:\s+(.+)", re.IGNORECASE), 
     "Critical 🔴", "IMPORT-ERR", "Failed to import module: '{}'", "Check module dependencies and installation."),
     
    (re.compile(r"SyntaxError:\s+(.+)", re.IGNORECASE), 
     "Critical 🔴", "SYNTAX-ERR", "Syntax error in code: '{}'", "Fix the syntax error at the reported line."),
     
    (re.compile(r"connection refused", re.IGNORECASE), 
     "Critical 🔴", "CONN-REFUSED", "Connection refused to dependent service", "Ensure the required services (e.g. Database) are running."),
     
    (re.compile(r"AssertionError:\s*(.*)", re.IGNORECASE), 
     "High 🟠", "ASSERT-ERR", "Test assertion failed: '{}'", "Update the code to pass the test or fix the assertion."),
     
    (re.compile(r"AttributeError:\s+(.+)", re.IGNORECASE), 
     "High 🟠", "ATTR-ERR", "Attribute access failed: '{}'", "Check if the object has the required attribute."),
     
    (re.compile(r"TypeError:\s+(.+)", re.IGNORECASE), 
     "High 🟠", "TYPE-ERR", "Type mismatch: '{}'", "Ensure variables are of the correct type."),
     
    (re.compile(r"([A-Z]:\\[^\s:]+:\d+:\d+:\s+E501.+)", re.IGNORECASE), 
     "Medium 🟡", "FLAKE8-E501", "Line too long", "Break the line into multiple lines to meet PEP8 max length."),
     
    (re.compile(r"([A-Z]:\\[^\s:]+:\d+:\d+:\s+E221.+)", re.IGNORECASE), 
     "Medium 🟡", "FLAKE8-E221", "Multiple spaces before operator", "Remove extra spaces before the operator."),
     
    (re.compile(r"npm ERR!\s+(.+)", re.IGNORECASE),
     "Critical 🔴", "NPM-ERR", "NPM error: '{}'", "Run npm install or check package.json dependencies."),
]

WARNING_MAPPINGS = [
    (re.compile(r"DeprecationWarning:\s+(.+)", re.IGNORECASE), 
     "Low 🔵", "WARN-DEPRECATED", "Using deprecated feature: '{}'", "Update to the recommended alternative."),
    
    (re.compile(r"PendingDeprecationWarning:\s+(.+)", re.IGNORECASE), 
     "Low 🔵", "WARN-PENDING-DEPRECATED", "Feature will be deprecated soon: '{}'", "Plan to migrate away from this feature."),
]


class PipelineAnalyzer:
    """
    Analyzes raw pipeline / build logs to identify structured errors, 
    warnings, calculate health score, and parse stages.
    """

    def analyze(self, logs: str, project_id: Optional[str] = None) -> dict:
        """Main entry point: parse and analyse log text."""
        lines = logs.splitlines()
        
        errors = self._find_issues(lines, ERROR_MAPPINGS)
        warnings = self._find_issues(lines, WARNING_MAPPINGS)
        stages = self._extract_stages(lines)
        
        # Calculate health score (0-100)
        critical_count = sum(1 for e in errors if "Critical" in e["severity"])
        high_count = sum(1 for e in errors if "High" in e["severity"])
        medium_count = sum(1 for e in errors if "Medium" in e["severity"])
        low_count = len(warnings)
        
        score = 100 - (critical_count * 25) - (high_count * 10) - (medium_count * 5) - (low_count * 2)
        health_score = max(0, min(100, score))
        
        overall_status = "FAILED"
        if health_score == 100 and not any(s["status"] == "failed" for s in stages):
            overall_status = "SUCCESS"
        elif len(errors) == 0 and len(warnings) > 0 and not any(s["status"] == "failed" for s in stages):
            overall_status = "WARNING"

        logger.info(
            f"Pipeline analysis for project {project_id}: "
            f"Score {health_score}, {len(errors)} errors, {len(warnings)} warnings."
        )

        return {
            "project_id": project_id,
            "overall_status": overall_status,
            "health_score": health_score,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "stages": stages,
            "errors": errors[:20],  # cap output
            "warnings": warnings[:10],
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _extract_stages(self, lines: list[str]) -> list[dict]:
        stages = []
        # Match lines like: "[SUCCESS] Install Dependencies: OK (3.2s)"
        for line in lines:
            m = re.search(r"\[(SUCCESS|FAILED|WARNING|SKIPPED|START)\]\s+(.+?):\s+(OK|FAILED|Skipped.+?)\s*\(?([\d.]+s)?\)?", line)
            if m:
                label, name, result, dur = m.groups()
                status = "success" if label in ("SUCCESS", "START", "SKIPPED") else "warning" if label == "WARNING" else "failed"
                stages.append({
                    "name": name.strip(),
                    "status": status,
                    "duration": dur,
                    "result_text": result.strip()
                })
        return stages

    def _find_issues(self, lines: list[str], mappings: list) -> list[dict]:
        issues = []
        for i, line in enumerate(lines, 1):
            line_str = line.strip()
            if not line_str:
                continue
                
            matched = False
            for pattern, severity, err_id, prob_tpl, fix_tpl in mappings:
                m = pattern.search(line_str)
                if m:
                    # Extract matched group or use full line
                    detail = m.group(1) if m.groups() else line_str
                    
                    issues.append({
                        "error_id": err_id,
                        "line_number": i,
                        "severity": severity,
                        "problem": prob_tpl.format(detail),
                        "why_it_happened": line_str,
                        "fix": fix_tpl.format(detail)
                    })
                    matched = True
                    break
                    
            # Fallback for generic 'FAILED' or 'error:' if searching for errors
            if not matched and mappings is ERROR_MAPPINGS:
                # We don't want to double count the stage summary lines (e.g. [FAILED] Lint: FAILED)
                if "[FAILED]" not in line_str and "[WARNING]" not in line_str:
                    if re.search(r"FAILED", line_str, re.IGNORECASE):
                        issues.append({
                            "error_id": "GENERIC-FAILED",
                            "line_number": i,
                            "severity": "High 🟠",
                            "problem": "Generic pipeline failure",
                            "why_it_happened": line_str,
                            "fix": "Review the build log context to identify the root cause."
                        })
                    elif re.search(r"error:", line_str, re.IGNORECASE):
                        issues.append({
                            "error_id": "GENERIC-ERR",
                            "line_number": i,
                            "severity": "High 🟠",
                            "problem": "Generic pipeline error",
                            "why_it_happened": line_str,
                            "fix": "Review the build log context to identify the root cause."
                        })
        return issues
