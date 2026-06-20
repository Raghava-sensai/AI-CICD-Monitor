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

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage"))
RELEASES_DIR = os.path.join(STORAGE_DIR, "releases")
LOGS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "logs")

# Stage Timeouts (in seconds)
BUILD_TIMEOUT = 900
TEST_TIMEOUT = 600
START_TIMEOUT = 300

# Retry up to 30 times with 1-second intervals (handles apps that start in 2s to 30s)
HEALTH_CHECK_RETRIES = 30
HEALTH_CHECK_PATHS = ["/health", "/healthz", "/"]

RUNTIME_IMAGES = {
    "python": "python:3.12",
    "javascript": "node:22",
    "typescript": "node:22",
    "java": "maven:3.9-eclipse-temurin-21",
    "java-gradle": "gradle:8.7-jdk21",
    "go": "golang:1.24",
    "ruby": "ruby:3.3",
    "rust": "rust:latest",
    "php": "php:8.3-cli",
    "static": "nginx:alpine",
}

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
    "static": [
        {
            "name": "Deploy Static Files",
            "cmd": ["sh", "-c", "cp -r {work_dir}/* /usr/share/nginx/html/ || true"],
        },
        {
            "name": "Start Application",
            "cmd": ["nginx", "-g", "daemon off;"],
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
    "python": ["app.py", "main.py", "server.py", "manage.py", "wsgi.py", "run.py", "webui.py", "api.py"],
    "javascript": ["index.js", "server.js", "app.js", "src/index.js"],
    "typescript": ["src/index.ts", "index.ts", "server.ts"],
    "ruby": ["app.rb", "config.ru", "server.rb"],
    "php": ["index.php", "public/index.php"],
    "static": ["index.html"],
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
        Run the full pipeline according to the 6-tier discovery hierarchy.
        """
        from services.deployment_config import DeploymentConfigParser
        from services.ai_config_discovery import AIConfigDiscovery
        from services.docker_runner import DockerBuilder
        
        port = self._ensure_port(deployment)

        # Priority 1: deployment.yml
        custom_config = DeploymentConfigParser().parse(work_dir) or {}
        if custom_config.get("runtime") or custom_config.get("start_command"):
            logger.info(f"Priority 1: deployment.yml found for {work_dir}")
            return self._execute_pipeline(deployment, work_dir, log_path, port, custom_config, "deployment.yml")
            
        # Priority 2: Dockerfile
        if os.path.exists(os.path.join(work_dir, "Dockerfile")):
            logger.info(f"Priority 2: Dockerfile found for {work_dir}")
            return DockerBuilder().run(work_dir, log_path, port, custom_config)
            
        ai_service = AIConfigDiscovery()
        ai_res = ai_service.discover(work_dir)
        
        # Priority 3: DEPLOYMENT.md (AI Analysis)
        if ai_res["source"] == "DEPLOYMENT.md" and ai_res["confidence"] >= 0.9:
            logger.info(f"Priority 3: DEPLOYMENT.md high confidence AI match for {work_dir}")
            return self._execute_pipeline(deployment, work_dir, log_path, port, ai_res, "DEPLOYMENT.md (AI)")
            
        # Priority 4: Manifest Detection
        lang_result = self.detector.detect(work_dir)
        manifests = lang_result.get("manifests", [])
        if len(manifests) == 1:
            logger.info(f"Priority 4: Unambiguous manifest found for {work_dir}")
            manifest_conf = {"runtime": manifests[0]["language"], "working_directory": manifests[0]["dir"]}
            return self._execute_pipeline(deployment, work_dir, log_path, port, manifest_conf, "Manifest Detection")
            
        # Priority 5: README.md AI Analysis
        if ai_res["source"] in ["README.md", "readme.md", "README"] and ai_res["confidence"] >= 0.9:
             logger.info(f"Priority 5: README.md high confidence AI match for {work_dir}")
             return self._execute_pipeline(deployment, work_dir, log_path, port, ai_res, "README.md (AI)")
             
        # Priority 6: CONFIG_REQUIRED
        logger.info(f"Priority 6: CONFIG_REQUIRED hit for {work_dir}")
        msg = "Configuration Required: Multiple deployment targets or no clear manifest found."
        if ai_res["confidence"] >= 0.6:
            msg += f"\nAI Suggestion (confidence {ai_res['confidence']}): runtime={ai_res['runtime']}, directory={ai_res['working_directory']}"
        
        with open(log_path, "a", encoding="utf-8") as log:
             log.write(f"\n{'='*60}\n")
             log.write(f"Pipeline Start: UNKNOWN | port={port}\n")
             log.write(f"Detected via: CONFIG_REQUIRED\n")
             log.write(f"{'='*60}\n")
             log.write(f"\n[FAILED] {msg}\n")
             
        return {
             "language": "unknown",
             "docker_image": "ubuntu:latest",
             "port": port,
             "entry": None,
             "stages": [],
             "failed_stage": "Configuration Discovery",
             "success": False,
             "error_summary": [{"stage": "Configuration Discovery", "snippet": msg, "exit_code": -1}]
        }

    def _execute_pipeline(self, deployment: Deployment, work_dir: str, log_path: str, port: int, custom_config: dict, detection_method: str) -> dict:
        """Inner loop for executing stages once language is decided, using a single stateful container."""
        import docker
        language = custom_config.get("runtime", "unknown")
        
        target_dir = work_dir
        if custom_config.get("working_directory") and custom_config.get("working_directory") != ".":
            target_dir = os.path.abspath(os.path.join(work_dir, custom_config["working_directory"]))

        docker_image = "ubuntu:latest"
        if language in RUNTIME_IMAGES:
             docker_image = RUNTIME_IMAGES[language]

        entry = self._find_entry(target_dir, language)

        ctx = {
            "work_dir": target_dir,
            "entry": entry,
            "port": str(port),
            "binary": os.path.basename(target_dir),
            "custom_config": custom_config,
            "language": language
        }

        # Dynamic Pipeline Generation
        stages = self._generate_stages(language, target_dir, custom_config)
        results = []
        
        # Determine dependencies volume name
        dep_vol_name = f"vol_{deployment.deployment_id}_deps"
        client = docker.from_env()

        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"\n{'='*60}\n")
            log.write(f"Pipeline Start: {language.upper()} | port={port}\n")
            log.write(f"Detected via: {detection_method}\n")
            if target_dir != work_dir:
                log.write(f"Working Directory: {custom_config['working_directory']}\n")
            log.write(f"{'='*60}\n")
            
            validation_result = self._run_worker_validation(log)
            results.append(validation_result)
            if not validation_result["success"]:
                log.write(f"\n[STOP] Pipeline stopped at: Worker Validation\n")
                return self._finalize_pipeline(language, docker_image, port, entry, results, "Worker Validation", False)

            # --- Start Deployment Container ---
            log.write(f"\n[DOCKER] Starting stateful deployment container ({docker_image})...\n")
            host_storage_path = os.getenv("HOST_STORAGE_PATH")
            if host_storage_path:
                rel_path = os.path.relpath(target_dir, STORAGE_DIR)
                host_path = f"{host_storage_path}/{rel_path}".replace("\\", "/")
            else:
                host_path = target_dir
                
            volumes = {
                host_path: {"bind": target_dir, "mode": "rw"}
            }
            
            # Mount anonymous volume for dependencies to preserve +x permissions on Windows
            if language in ["javascript", "typescript"]:
                volumes[dep_vol_name] = {"bind": f"{target_dir}/node_modules", "mode": "rw"}
                
            # Map container port 80 for static sites (nginx), otherwise use the allocated port
            container_port = "80" if language == "static" else str(port)
            ports_mapping = {f"{container_port}/tcp": port}
                
            try:
                container = client.containers.run(
                    docker_image,
                    command=["tail", "-f", "/dev/null"],
                    volumes=volumes,
                    working_dir=target_dir,
                    ports=ports_mapping,
                    environment={"PORT": str(port)},
                    mem_limit="2g",
                    cpu_quota=100000,
                    network_disabled=False,
                    detach=True,
                    name=f"deploy_{deployment.deployment_id}"
                )
            except Exception as e:
                msg = f"Failed to start deployment container: {e}"
                log.write(f"[ERROR] {msg}\n")
                results.append({"stage": "Start Container", "success": False, "error_message": msg})
                return self._finalize_pipeline(language, docker_image, port, entry, results, "Start Container", False)

            has_start_stage = any(s.get("is_start") for s in stages)
            success = True
            
            try:
                for stage in stages:
                    if stage.get("is_start"):
                        result = self._record_start_stage(stage, ctx, log, port, container.name)
                        results.append(result)

                        if not result["success"]:
                            success = False
                            log.write(f"\n[STOP] Pipeline stopped at: {stage['name']}\n")
                            break

                        health_result = self._run_health_check(port, log, custom_config)
                        results.append(health_result)

                        if not health_result["success"]:
                            # We keep success = True so the container isn't destroyed,
                            # but the stage result captures the warning
                            log.write(f"\n[WARNING] Pipeline finished with warnings at: Health Check\n")
                        break
                    else:
                        result = self._run_stage(stage, ctx, log, container.name)
                        results.append(result)

                        if not result["success"] and not stage.get("optional", False):
                            success = False
                            log.write(f"\n[STOP] Pipeline stopped at: {stage['name']}\n")
                            break
            finally:
                # Resource Cleanup Phase
                if not success or not has_start_stage:
                    log.write(f"\n[CLEANUP] Cleaning up deployment container...\n")
                    try:
                        container.stop(timeout=2)
                        container.remove(force=True)
                        client.volumes.get(dep_vol_name).remove(force=True)
                    except Exception as e:
                        logger.warning(f"Cleanup failed for {deployment.deployment_id}: {e}")

        failed_stage = None
        for r in results:
            if not r.get("success") and not r.get("optional") and not r.get("skipped"):
                failed_stage = r.get("stage")
                break

        return self._finalize_pipeline(language, docker_image, port, entry, results, failed_stage, success)

    def _generate_stages(self, language: str, work_dir: str, custom_config: dict) -> list:
        """Dynamically generate pipeline stages based on package manifests."""
        if language not in ["javascript", "typescript"]:
            return PIPELINE_STAGES.get(language, PIPELINE_STAGES["unknown"])
            
        pkg_path = os.path.join(work_dir, "package.json")
        scripts = {}
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    scripts = json.load(f).get("scripts", {})
            except: pass
            
        stages = [
            {
                "name": "Install Dependencies",
                "cmd": ["npm", "install", "--prefix", "{work_dir}"],
            }
        ]
        
        if language == "typescript":
            stages.append({
                "name": "TypeScript Compile",
                "cmd": ["npx", "tsc", "--project", "{work_dir}"],
                "optional": True,
            })
            
        if "lint" in scripts:
            stages.append({
                "name": "Lint (eslint)",
                "cmd": ["npm", "run", "lint", "--prefix", "{work_dir}"],
                "optional": True,
            })
            
        if "test" in scripts and "no test specified" not in scripts["test"]:
            stages.append({
                "name": "Run Tests",
                "cmd": ["npm", "test", "--prefix", "{work_dir}", "--", "--watchAll=false"],
                "optional": True,
            })
            
        if "build" in scripts:
            stages.append({
                "name": "Build",
                "cmd": ["npm", "run", "build", "--prefix", "{work_dir}"],
            })
            
        if "start" in scripts or "dev" in scripts:
            start_cmd = "start" if "start" in scripts else "dev"
            stages.append({
                "name": "Start Application",
                "cmd": ["npm", "run", start_cmd, "--prefix", "{work_dir}"],
                "is_start": True,
            })
            
        # Override with custom config if provided
        if custom_config.get("start_command") and not any(s.get("is_start") for s in stages):
            stages.append({
                "name": "Start Application",
                "cmd": [custom_config["start_command"]],
                "is_start": True,
            })
            
        return stages

    def _finalize_pipeline(self, language, docker_image, port, entry, results, failed_stage, success):
        return {
            "language": language,
            "docker_image": docker_image,
            "port": port,
            "entry": entry,
            "stages": results,
            "failed_stage": failed_stage,
            "success": success,
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

    def _run_worker_validation(self, log) -> dict:
        name = "Worker Validation"
        t0 = time.time()
        started_at = datetime.datetime.utcnow().isoformat() + "Z"
        
        try:
            import docker
            client = docker.from_env()
            client.ping()
            msg = "Docker daemon is reachable."
            success = True
            code = 0
            err_type = None
            err_msg = None
        except Exception as e:
            msg = f"Docker daemon is NOT reachable: {e}"
            success = False
            code = -1
            err_type = "DependencyError"
            err_msg = "Docker is not installed or the socket is inaccessible."
            
        duration = round(time.time() - t0, 2)
        ended_at = datetime.datetime.utcnow().isoformat() + "Z"
        
        level = "[SUCCESS]" if success else "[FAILED]"
        log.write(f"\n{'─'*40}\n▶  {name}\n")
        log.write(f"{level} {name}: {'OK' if success else 'FAILED'} ({duration}s)\n")
        log.write(f"   {msg}\n")
        
        return {
            "stage": name,
            "success": success,
            "duration": duration,
            "started_at": started_at,
            "ended_at": ended_at,
            "exit_code": code,
            "error_type": err_type,
            "error_message": err_msg,
            "output": msg
        }

    def _find_entry(self, work_dir: str, language: str) -> Optional[str]:
        candidates = ENTRY_POINTS.get(language, [])
        for name in candidates:
            path = os.path.join(work_dir, name)
            if os.path.exists(path):
                logger.info(f"Entry point found: {path}")
                return path
        return None

    def _run_stage(self, stage: dict, ctx: dict, log, container_name: str) -> dict:
        name = stage["name"]
        optional = stage.get("optional", False)

        cmd = [c.format(**ctx) for c in stage["cmd"]]
        cwd = stage.get("cwd", ctx["work_dir"])
        if cwd:
            cwd = cwd.format(**ctx)

        log.write(f"\n{'─'*40}\n▶  {name}\n   cmd: {' '.join(cmd)}\n")
        t0 = time.time()
        started_at = datetime.datetime.utcnow().isoformat() + "Z"
        
        timeout = BUILD_TIMEOUT if "Build" in name else (TEST_TIMEOUT if "Test" in name else 600)
        cmd_str = " ".join(cmd)
        
        try:
            # Execute within the stateful container via docker exec
            exec_cmd = ["docker", "exec", "-w", cwd, container_name, "sh", "-c", cmd_str]
            stdout_l, stderr_l, code_l = run_command(exec_cmd, timeout=timeout)
            stdout = stdout_l or ""
            stderr = stderr_l or ""
            code = code_l
        except Exception as e:
            code = -1
            stdout = ""
            stderr = f"Docker execution failed: {e}"
            log.write(f"   [WARNING] {stderr}\n")
            
        duration = round(time.time() - t0, 2)
        ended_at = datetime.datetime.utcnow().isoformat() + "Z"

        log.write(stdout or "")
        if stderr:
            log.write(f"[stderr]\n{stderr}")
        log.write(f"\n   exit={code} duration={duration}s\n")

        success = code == 0
        level = "[SUCCESS]" if success else ("[WARNING]" if optional else "[FAILED]")
        log.write(f"{level} {name}: {'OK' if success else 'FAILED'} ({duration}s)\n")

        err_msg = None
        err_type = None
        if not success:
            err_msg = (stderr or stdout or "").strip()
            if err_msg:
                err_msg = err_msg[-500:]
            else:
                err_msg = f"Process exited with code {code}"
                
            if "Executable not found" in err_msg or "command not found" in err_msg:
                err_type = "DependencyError"
            elif code == -1:
                err_type = "SystemError"
            else:
                err_type = "CommandFailed"

        return {
            "stage": name,
            "success": success,
            "optional": optional,
            "duration": duration,
            "started_at": started_at,
            "ended_at": ended_at,
            "exit_code": code,
            "error_type": err_type,
            "error_message": err_msg,
            "command": cmd_str,
            "output": (stdout or "") + (stderr or ""),
        }

    def _run_health_check(self, port: int, log, custom_config: dict = None) -> dict:
        """
        Poll the app's health endpoint up to timeout limit times.
        Uses custom health_check endpoint if provided, else tries /health, /healthz, /.
        """
        import requests
        custom_config = custom_config or {}
        
        timeout = custom_config.get("deployment_timeout", HEALTH_CHECK_RETRIES)
        try: timeout = int(timeout)
        except: timeout = HEALTH_CHECK_RETRIES
        
        custom_path = custom_config.get("health_check")
        paths_to_try = [custom_path] if custom_path else HEALTH_CHECK_PATHS

        log.write(f"\n{'─'*40}\n")
        log.write(f"[HEALTH] Health Check on port {port}\n")
        log.write(f"   Polling {', '.join(paths_to_try)} (up to {timeout}s)\n")
        t0 = time.time()
        started_at = datetime.datetime.utcnow().isoformat() + "Z"

        last_error_type = "HEALTH_TIMEOUT"
        last_error_msg = f"Application did not become healthy within {timeout} seconds"

        for attempt in range(1, timeout + 1):
            for path in paths_to_try:
                # Use host.docker.internal to reach the port mapped on the host
                url = f"http://host.docker.internal:{port}{path}"
                try:
                    resp = requests.get(url, timeout=2)
                    resp.raise_for_status()
                    
                    log.write(
                        f"[SUCCESS] Health Check: OK at {path} "
                        f"(attempt {attempt}/{timeout})\n"
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
                        "duration": round(time.time() - t0, 2),
                        "started_at": started_at,
                        "ended_at": datetime.datetime.utcnow().isoformat() + "Z",
                    }
                except requests.exceptions.HTTPError as e:
                    last_error_type = f"HTTP_{e.response.status_code}"
                    last_error_msg = f"GET {path} returned {e.response.status_code}"
                except requests.exceptions.ConnectionError:
                    last_error_type = "CONNECTION_REFUSED"
                    last_error_msg = f"Connection refused at localhost:{port}"
                except requests.exceptions.Timeout:
                    last_error_type = "HEALTH_TIMEOUT"
                    last_error_msg = f"Request timed out for {url}"
                except Exception as e:
                    last_error_type = type(e).__name__
                    last_error_msg = str(e)

            time.sleep(1)

        log.write(
            f"[FAILED] Health Check: No response after "
            f"{timeout}s on port {port}. Last Error: {last_error_type} - {last_error_msg}\n"
        )
        logger.warning(f"Health check timed out after {timeout}s on port {port}")
        return {
            "stage": "Health Check",
            "success": False,
            "optional": True,
            "url": f"http://127.0.0.1:{port}",
            "attempt": timeout,
            "error_type": last_error_type,
            "error_message": last_error_msg,
            "duration": round(time.time() - t0, 2),
            "started_at": started_at,
            "ended_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

    def _record_start_stage(self, stage: dict, ctx: dict, log, port: int, container_name: str) -> dict:
        custom_config = ctx.get("custom_config", {})
        start_cmd_str = custom_config.get("start_command")
        
        # Prevent blind formatting and failing with KeyError/None if no entry is found
        if not start_cmd_str and not ctx.get("entry"):
            msg = "Deployment Configuration Missing:\nNo deployment.txt found with a start_command, and no standard entry file (e.g. app.py, main.py) was found in the repository.\nRecommendation: Add a deployment.txt specifying the start_command."
            log.write(f"\n{'─'*40}\n")
            log.write(f"[START] Start Application\n")
            log.write(f"   [ERROR] {msg}\n")
            started_at = datetime.datetime.utcnow().isoformat() + "Z"
            return {
                "stage": "Start Application",
                "success": False,
                "port": port,
                "cmd": "Unknown",
                "output": msg,
                "duration": 0,
                "error_type": "ConfigurationMissing",
                "error_message": msg,
                "started_at": started_at,
                "ended_at": started_at,
            }

        cmd = [c.format(**ctx) for c in stage["cmd"]]
        cwd = stage.get("cwd", ctx["work_dir"])
        if cwd:
            cwd = cwd.format(**ctx)

        log.write(f"\n{'─'*40}\n")
        log.write(f"[START] Start Application\n")
        log.write(f"   cmd: {' '.join(cmd)}\n")
        log.write(f"   cwd: {cwd}\n")
        log.write(f"   port: {port}\n")

        t0 = time.time()
        started_at = datetime.datetime.utcnow().isoformat() + "Z"

        try:
            # --- Default Execution within the single container ---
            start_cmd_str = custom_config.get("start_command") or " ".join(cmd)
            log.write(f"   [START] Command: {start_cmd_str}\n")
            
            # Execute in background inside the already running container
            exec_cmd = ["docker", "exec", "-d", "-e", f"PORT={port}", "-w", cwd, container_name, "sh", "-c", start_cmd_str]
            stdout_l, stderr_l, code = run_command(exec_cmd, timeout=START_TIMEOUT)
            
            if code != 0:
                raise RuntimeError(f"Failed to trigger start command: {stderr_l or stdout_l}")
                
            log.write(f"   [Launched process via docker exec -d]\n")

            return {
                "stage": "Start Application",
                "success": True,
                "port": port,
                "cmd": start_cmd_str,
                "output": f"App launched in persistent container {container_name} on port {port}",
                "duration": round(time.time() - t0, 2),
                "started_at": started_at,
                "ended_at": datetime.datetime.utcnow().isoformat() + "Z",
            }
        except Exception as e:
            import traceback
            msg = f"Failed to start application: {e}"
            log.write(f"   [ERROR] {msg}\n")
            log.write(traceback.format_exc() + "\n")
            logger.error(msg)
            return {
                "stage": "Start Application",
                "success": False,
                "port": port,
                "cmd": " ".join(cmd),
                "output": msg,
                "duration": round(time.time() - t0, 2),
                "started_at": started_at,
                "ended_at": datetime.datetime.utcnow().isoformat() + "Z",
            }

    def _build_error_summary(self, results: list) -> list:
        errors = []
        for r in results:
            if not r.get("success") and not r.get("skipped"):
                output = r.get("output", "")
                
                # Health Check doesn't have an exit_code in the same way
                # Setting it to None produces confusing logs like exit=None
                exit_code_str = ""
                if r.get("exit_code") is not None:
                    exit_code_str = f" exit={r.get('exit_code')}"
                elif r.get("error_type"):
                    exit_code_str = f" type={r.get('error_type')}"
                
                errors.append(
                    {
                        "stage": r["stage"],
                        "exit_code": r.get("exit_code"),
                        "snippet": output[-600:] if output else (r.get("error_message") or "No output captured"),
                    }
                )
        return errors
