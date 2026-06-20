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
        
        # Stage-based scoring
        stage_weights = {
            "Repository Checkout": 20,
            "Deploy Static Files": 25,
            "Install Dependencies": 25, # Default to 25 unless build is present
            "Build": 15,
            "Build (Maven)": 25,
            "Build (cargo)": 25,
            "Download Dependencies": 10,
            "Start Application": 25,
            "Health Check": 30
        }
        
        has_build = any(s["name"] in ["Build", "TypeScript Compile"] for s in stages)
        
        earned = 0
        failed_stage_name = None
        for s in stages:
            if s["status"] == "success":
                w = stage_weights.get(s["name"], 0)
                if s["name"] == "Install Dependencies" and has_build:
                    w = 10
                elif s["name"] == "TypeScript Compile":
                    w = 15
                earned += w
            elif s["status"] in ["failed", "warning"]:
                failed_stage_name = s["name"]
                
        health_score = min(100, earned)
        
        if health_score == 100 and not failed_stage_name:
            overall_status = "SUCCESS"
            severity = "SUCCESS"
        elif health_score >= 50:
            overall_status = "WARNING"
            severity = "WARNING"
        else:
            overall_status = "CRITICAL"
            severity = "CRITICAL"
            
        if failed_stage_name == "Health Check":
            errors.insert(0, {
                "error_id": "HEALTH-CHECK-FAIL",
                "line_number": -1,
                "severity": "Warning 🟡",
                "problem": "Application health check failed.",
                "why_it_happened": "Possible causes: Wrong port mapping, Slow startup, Health endpoint missing.",
                "fix": "Ensure the application binds to the correct port (0.0.0.0) and responds with 200 OK."
            })
        elif failed_stage_name and not errors:
            errors.insert(0, {
                "error_id": "STAGE-FAIL",
                "line_number": -1,
                "severity": "Critical 🔴" if severity == "CRITICAL" else "Warning 🟡",
                "problem": f"Pipeline failed at stage: {failed_stage_name}",
                "why_it_happened": "Review the pipeline logs for more details.",
                "fix": "Check the stack trace to identify the root cause."
            })

        logger.info(
            f"Pipeline analysis for project {project_id}: "
            f"Score {health_score}, Severity {severity}, {len(errors)} errors, {len(warnings)} warnings."
        )

        return {
            "project_id": project_id,
            "overall_status": overall_status,
            "severity": severity,
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
