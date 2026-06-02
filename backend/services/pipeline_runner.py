"""
Pipeline Runner Service
-----------------------
Executes real CI/CD pipeline stages per language:
  detect → install → build → test → start → health-check

If the port is unavailable at any stage, it auto-reallocates
a new free port and rewrites every config that references it.
"""

import os
import json
import datetime
import threading
import subprocess
import time
import urllib.request
from typing import Optional
from models.deployment import Deployment
from services.language_detector import LanguageDetector
from services.port_manager import PortManager
from utils.logger import setup_logger
from utils.shell import run_command

logger = setup_logger(__name__)

STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage")
RELEASES_DIR = os.path.join(STORAGE_DIR, "releases")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "logs")

# Retry up to 30 times with 1-second intervals (handles apps that start in 2s to 30s)
HEALTH_CHECK_RETRIES = 30
HEALTH_CHECK_PATHS = ["/health", "/healthz", "/"]

# ── Per-language pipeline definitions ─────────────────────────────────────────
PIPELINE_STAGES = {
    "python": [
        {
            "name": "Install Dependencies",
            "check": "requirements.txt",
            "cmd": ["pip", "install", "-r", "{work_dir}/requirements.txt"],
        },
        {
            "name": "Lint (flake8)",
            "check": "requirements.txt",
            "cmd": [
                "python",
                "-m",
                "flake8",
                "{work_dir}",
                "--max-line-length=120",
                "--exclude=__pycache__,.git,venv",
            ],
            "optional": True,
        },
        {
            "name": "Run Tests (pytest)",
            "check": "requirements.txt",
            "cmd": ["python", "-m", "pytest", "{work_dir}", "--tb=short", "-q"],
            "optional": True,
        },
        {"name": "Start Application", "cmd": ["python", "{entry}"], "is_start": True},
    ],
    "javascript": [
        {
            "name": "Install Dependencies",
            "check": "package.json",
            "cmd": ["npm", "install", "--prefix", "{work_dir}"],
        },
        {
            "name": "Lint (eslint)",
            "cmd": ["npx", "eslint", "{work_dir}", "--ext", ".js,.jsx"],
            "optional": True,
        },
        {
            "name": "Run Tests",
            "cmd": ["npm", "test", "--prefix", "{work_dir}", "--", "--watchAll=false"],
            "optional": True,
        },
        {
            "name": "Build",
            "cmd": ["npm", "run", "build", "--prefix", "{work_dir}"],
            "optional": True,
        },
        {
            "name": "Start Application",
            "cmd": ["npm", "start", "--prefix", "{work_dir}"],
            "is_start": True,
        },
    ],
    "typescript": [
        {
            "name": "Install Dependencies",
            "check": "package.json",
            "cmd": ["npm", "install", "--prefix", "{work_dir}"],
        },
        {
            "name": "TypeScript Compile",
            "cmd": ["npx", "tsc", "--project", "{work_dir}"],
            "optional": True,
        },
        {
            "name": "Run Tests",
            "cmd": ["npm", "test", "--prefix", "{work_dir}", "--", "--watchAll=false"],
            "optional": True,
        },
        {
            "name": "Start Application",
            "cmd": ["npm", "start", "--prefix", "{work_dir}"],
            "is_start": True,
        },
    ],
    "go": [
        {
            "name": "Download Dependencies",
            "check": "go.mod",
            "cmd": ["go", "mod", "download"],
            "cwd": "{work_dir}",
        },
        {"name": "Build", "cmd": ["go", "build", "./..."], "cwd": "{work_dir}"},
        {
            "name": "Run Tests",
            "cmd": ["go", "test", "./...", "-v"],
            "cwd": "{work_dir}",
            "optional": True,
        },
        {
            "name": "Start Application",
            "cmd": ["go", "run", "."],
            "cwd": "{work_dir}",
            "is_start": True,
        },
    ],
    "java": [
        {
            "name": "Build (Maven)",
            "check": "pom.xml",
            "cmd": ["mvn", "clean", "package", "-q", "-DskipTests=false"],
            "cwd": "{work_dir}",
        },
        {
            "name": "Run Tests",
            "cmd": ["mvn", "test", "-q"],
            "cwd": "{work_dir}",
            "optional": True,
        },
        {
            "name": "Start Application",
            "cmd": ["java", "-jar", "{work_dir}/target/*.jar"],
            "is_start": True,
        },
    ],
    "ruby": [
        {
            "name": "Install Dependencies",
            "check": "Gemfile",
            "cmd": ["bundle", "install", "--path", "{work_dir}/vendor/bundle"],
            "cwd": "{work_dir}",
        },
        {
            "name": "Run Tests (rspec)",
            "cmd": ["bundle", "exec", "rspec"],
            "cwd": "{work_dir}",
            "optional": True,
        },
        {"name": "Start Application", "cmd": ["ruby", "{entry}"], "is_start": True},
    ],
    "rust": [
        {
            "name": "Build (cargo)",
            "check": "Cargo.toml",
            "cmd": ["cargo", "build", "--release"],
            "cwd": "{work_dir}",
        },
        {
            "name": "Run Tests",
            "cmd": ["cargo", "test"],
            "cwd": "{work_dir}",
            "optional": True,
        },
        {
            "name": "Start Application",
            "cmd": ["{work_dir}/target/release/{binary}"],
            "is_start": True,
        },
    ],
    "php": [
        {
            "name": "Install Dependencies",
            "check": "composer.json",
            "cmd": ["composer", "install", "--no-dev"],
            "cwd": "{work_dir}",
        },
        {
            "name": "Run Tests",
            "cmd": ["./vendor/bin/phpunit"],
            "cwd": "{work_dir}",
            "optional": True,
        },
        {
            "name": "Start Application",
            "cmd": ["php", "-S", "0.0.0.0:{port}", "-t", "{work_dir}/public"],
            "is_start": True,
        },
    ],
    "unknown": [
        {
            "name": "Start Application",
            "cmd": ["echo", "No known start command for this language."],
            "is_start": True,
        },
    ],
}

# Entry-point file patterns per language
ENTRY_POINTS = {
    "python": ["app.py", "main.py", "server.py", "manage.py", "wsgi.py", "run.py"],
    "javascript": ["index.js", "server.js", "app.js", "src/index.js"],
    "typescript": ["src/index.ts", "index.ts", "server.ts"],
    "ruby": ["app.rb", "config.ru", "server.rb"],
    "php": ["index.php", "public/index.php"],
}


class PipelineRunner:
    """
    Orchestrates the full CI/CD pipeline for any supported language.
    Handles port conflicts automatically.
    """

    def __init__(self):
        self.detector = LanguageDetector()
        self.port_mgr = PortManager()

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self, deployment: Deployment, work_dir: str, log_path: str) -> dict:
        """
        Run the full pipeline. Returns a result dict with all stage results.
        Automatically re-allocates port if the assigned one becomes busy.
        """
        # 1. Detect language
        lang_result = self.detector.detect(work_dir)
        language = lang_result["language"]
        logger.info(
            f"[{deployment.deployment_id[:8]}] Detected language: {language} "
            f"(confidence={lang_result['confidence']})"
        )

        # 2. Resolve entry point
        entry = self._find_entry(work_dir, language)

        # 3. Resolve port — check if still free, reallocate if not
        port = self._ensure_port(deployment)

        # 4. Build stage context
        ctx = {
            "work_dir": work_dir,
            "entry": entry or os.path.join(work_dir, "app.py"),
            "port": str(port),
            "binary": os.path.basename(work_dir),
        }

        stages = PIPELINE_STAGES.get(language, PIPELINE_STAGES["unknown"])
        results = []

        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"\n{'='*60}\n")
            log.write(f"Pipeline Start: {language.upper()} | port={port}\n")
            log.write(f"Detected via: {lang_result['method']}\n")
            log.write(f"{'='*60}\n")

            for stage in stages:
                if stage.get("is_start"):
                    result = self._record_start_stage(stage, ctx, log, port)
                    results.append(result)

                    if not result["success"]:
                        log.write(f"\n[STOP] Pipeline stopped at: {stage['name']}\n")
                        break

                    # Run health check only after the start stage succeeds
                    health_result = self._run_health_check(port, log)
                    results.append(health_result)

                    if not health_result["success"]:
                        log.write(f"\n[STOP] Pipeline stopped at: Health Check\n")
                        logger.warning(
                            f"[{deployment.deployment_id[:8]}] "
                            f"Health check failed after app start on port {port}"
                        )
                    break
                else:
                    result = self._run_stage(stage, ctx, log)
                    results.append(result)

                    if not result["success"] and not stage.get("optional", False):
                        log.write(f"\n[STOP] Pipeline stopped at: {stage['name']}\n")
                        logger.warning(
                            f"[{deployment.deployment_id[:8]}] "
                            f"Pipeline failed at '{stage['name']}'"
                        )
                        break

        # Determine the failed stage (first non-optional failure)
        failed_stage = None
        for r in results:
            if not r.get("success") and not r.get("optional") and not r.get("skipped"):
                failed_stage = r.get("stage")
                break

        return {
            "language": language,
            "docker_image": lang_result["docker_image"],
            "port": port,
            "entry": entry,
            "stages": results,
            "failed_stage": failed_stage,
            "success": all(
                r["success"] for r in results if not r.get("optional", False)
            ),
            "error_summary": self._build_error_summary(results),
        }

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_port(self, deployment: Deployment) -> int:
        """
        Check if the deployment's assigned port is still free.
        If not, release it and allocate a new one — update the deployment record.
        """
        import socket

        port = deployment.port

        def _is_free(p):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("0.0.0.0", p))
                    return True
                except OSError:
                    return False

        if not _is_free(port):
            logger.warning(f"Port {port} is busy — auto-reallocating...")
            self.port_mgr.release(port)
            new_port = self.port_mgr.allocate()
            deployment.port = new_port
            logger.info(f"Port reassigned: {port} → {new_port}")
            port = new_port

        return port

    def _find_entry(self, work_dir: str, language: str) -> Optional[str]:
        candidates = ENTRY_POINTS.get(language, [])
        for name in candidates:
            path = os.path.join(work_dir, name)
            if os.path.exists(path):
                logger.info(f"Entry point found: {path}")
                return path
        return None

    def _run_stage(self, stage: dict, ctx: dict, log) -> dict:
        name = stage["name"]
        optional = stage.get("optional", False)

        # Check prerequisite file
        check_file = stage.get("check")
        if check_file:
            check_path = os.path.join(ctx["work_dir"], check_file)
            if not os.path.exists(check_path):
                msg = f"Skipped (no {check_file} found)"
                log.write(f"\n[SKIPPED] {name}: {msg}\n")
                return {
                    "stage": name,
                    "success": True,
                    "skipped": True,
                    "optional": optional,
                    "output": msg,
                }

        # Resolve template variables in command
        cmd = [c.format(**ctx) for c in stage["cmd"]]
        cwd = stage.get("cwd", ctx["work_dir"])
        if cwd:
            cwd = cwd.format(**ctx)

        log.write(f"\n{'─'*40}\n▶  {name}\n   cmd: {' '.join(cmd)}\n")
        t0 = time.time()
        stdout, stderr, code = run_command(cmd, cwd=cwd, timeout=180)
        duration = round(time.time() - t0, 2)

        log.write(stdout or "")
        if stderr:
            log.write(f"[stderr]\n{stderr}")
        log.write(f"\n   exit={code} duration={duration}s\n")

        success = code == 0
        level = "[SUCCESS]" if success else ("[WARNING]" if optional else "[FAILED]")
        log.write(f"{level} {name}: {'OK' if success else 'FAILED'} ({duration}s)\n")

        return {
            "stage": name,
            "success": success,
            "optional": optional,
            "duration": duration,
            "exit_code": code,
            "output": (stdout or "") + (stderr or ""),
        }

    def _run_health_check(self, port: int, log) -> dict:
        """
        Poll the app's health endpoint up to HEALTH_CHECK_RETRIES times.
        Tries /health, /healthz, / in order. Returns success on the first 200.
        No fixed sleep — polls every 1 second so fast apps are detected quickly.
        """
        log.write(f"\n{'─'*40}\n")
        log.write(f"[HEALTH] Health Check on port {port}\n")
        log.write(f"   Polling /health, /healthz, / (up to {HEALTH_CHECK_RETRIES}s)\n")

        for attempt in range(1, HEALTH_CHECK_RETRIES + 1):
            for path in HEALTH_CHECK_PATHS:
                url = f"http://127.0.0.1:{port}{path}"
                try:
                    with urllib.request.urlopen(url, timeout=2) as resp:
                        if resp.status == 200:
                            log.write(
                                f"[SUCCESS] Health Check: OK at {path} "
                                f"(attempt {attempt}/{HEALTH_CHECK_RETRIES})\n"
                            )
                            logger.info(
                                f"Health check passed on {url} "
                                f"(attempt {attempt})"
                            )
                            return {
                                "stage": "Health Check",
                                "success": True,
                                "url": url,
                                "attempt": attempt,
                            }
                except Exception:
                    pass  # App not ready yet — try again

            time.sleep(1)

        log.write(
            f"[FAILED] Health Check: No response after "
            f"{HEALTH_CHECK_RETRIES}s on port {port}\n"
        )
        logger.warning(f"Health check timed out after {HEALTH_CHECK_RETRIES}s on port {port}")
        return {
            "stage": "Health Check",
            "success": False,
            "url": f"http://127.0.0.1:{port}",
            "attempt": HEALTH_CHECK_RETRIES,
        }

    def _record_start_stage(self, stage: dict, ctx: dict, log, port: int) -> dict:
        cmd = [c.format(**ctx) for c in stage["cmd"]]
        cwd = stage.get("cwd", ctx["work_dir"])
        if cwd:
            cwd = cwd.format(**ctx)

        log.write(f"\n{'─'*40}\n")
        log.write(f"[START] Start Application\n")
        log.write(f"   cmd: {' '.join(cmd)}\n")
        log.write(f"   cwd: {cwd}\n")
        log.write(f"   port: {port}\n")

        env = os.environ.copy()
        env["PORT"] = str(port)

        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

            proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                creationflags=creationflags
            )

            pid_file = os.path.join(ctx.get("work_dir", ""), "app.pid")
            with open(pid_file, "w") as f:
                f.write(str(proc.pid))

            log.write(f"   [Launched process PID: {proc.pid}]\n")

            return {
                "stage": "Start Application",
                "success": True,
                "port": port,
                "cmd": " ".join(cmd),
                "pid": proc.pid,
                "output": f"App launched with PID {proc.pid} on port {port}",
            }
        except Exception as e:
            msg = f"Failed to start application: {e}"
            log.write(f"   [ERROR] {msg}\n")
            logger.error(msg)
            return {
                "stage": "Start Application",
                "success": False,
                "port": port,
                "cmd": " ".join(cmd),
                "output": msg,
            }

    def _build_error_summary(self, results: list) -> list:
        errors = []
        for r in results:
            if not r.get("success") and not r.get("skipped"):
                output = r.get("output", "")
                errors.append(
                    {
                        "stage": r["stage"],
                        "exit_code": r.get("exit_code"),
                        "snippet": output[-600:] if output else "No output captured",
                    }
                )
        return errors
