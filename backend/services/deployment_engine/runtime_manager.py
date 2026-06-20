import os
import time
import docker
from abc import ABC, abstractmethod
from utils.logger import setup_logger

logger = setup_logger(__name__)

class RuntimeManager(ABC):
    @abstractmethod
    def start(self, deployment_id: str, config: dict, source_dir: str, port: int, log_path: str) -> dict:
        pass
        
    @abstractmethod
    def stop(self, deployment_id: str) -> bool:
        pass
        
    @abstractmethod
    def restart(self, deployment_id: str) -> bool:
        pass

import subprocess
import shlex
import psutil

class NativeRuntimeManager(RuntimeManager):
    def __init__(self):
        pass

    def build(self, deployment_id: str, config: dict, source_dir: str, log_path: str) -> bool:
        build_cmd = config.get("build_command", "")
        
        # Runtime Detection Priority Hierarchy
        # 1. deployment.txt (Highest priority)
        if build_cmd:
            pass
        # 2. Docker Compose / Dockerfile (Second priority)
        elif os.path.exists(os.path.join(source_dir, "docker-compose.yml")):
            build_cmd = "docker-compose build"
            config["start_command"] = config.get("start_command", "docker-compose up -d")
        elif os.path.exists(os.path.join(source_dir, "Dockerfile")):
            build_cmd = f"docker build -t app-{deployment_id[:8]} ."
            config["start_command"] = config.get("start_command", f"docker run -d -p {config.get('port', 3000)}:{config.get('port', 3000)} app-{deployment_id[:8]}")
        # 3. Manifest Detection (Third priority)
        else:
            if os.path.exists(os.path.join(source_dir, "package.json")):
                if os.path.exists(os.path.join(source_dir, "package-lock.json")):
                    build_cmd = "npm ci"
                else:
                    build_cmd = "npm install"
                config["start_command"] = config.get("start_command", "npm start")
            elif os.path.exists(os.path.join(source_dir, "requirements.txt")):
                build_cmd = "pip install -r requirements.txt"
                config["start_command"] = config.get("start_command", "python app.py")
            elif os.path.exists(os.path.join(source_dir, "pom.xml")):
                build_cmd = "mvn package"
            elif os.path.exists(os.path.join(source_dir, "go.mod")):
                build_cmd = "go mod download"
                
        if not build_cmd:
            with open(log_path, "a") as f:
                f.write("\n[NATIVE] No build dependencies required.\n")
            return True

        with open(log_path, "a") as f:
            f.write(f"\n[NATIVE] Executing build command: {build_cmd}\n")
            
        import sys
        try:
            if sys.platform == "win32":
                build_cmd_str = build_cmd
            else:
                build_cmd_str = f"sudo -u deployrunner bash -c {shlex.quote(build_cmd)}"
                
            with open(log_path, "a") as log_file:
                proc = subprocess.run(build_cmd_str, shell=True, cwd=source_dir, stdout=log_file, stderr=subprocess.STDOUT)
                if proc.returncode != 0:
                    raise Exception(f"Build command failed with exit code {proc.returncode}")
            return True
        except Exception as e:
            raise Exception(f"Dependency Installation failed: {str(e)}")

    def start(self, deployment_id: str, config: dict, source_dir: str, port: int, log_path: str) -> dict:
        start_cmd = config.get("start_command", "")
        if not start_cmd:
            raise Exception("No start_command provided in deployment configuration.")

        import sys
        import time

        with open(log_path, "a") as f:
            f.write(f"\n[NATIVE] Preparing native runtime for {deployment_id[:8]}\n")

        # Start the application
        with open(log_path, "a") as f:
            f.write(f"\n[NATIVE] Starting application on port {port}...\n")

        env_vars = f"PORT={port} "
        if config.get("env"):
            for k, v in config["env"].items():
                env_vars += f"{k}={shlex.quote(str(v))} "

        if sys.platform == "win32":
            # Just set the environment variables via shell prefix on Windows isn't as clean,
            # but since it's local test, we'll run it directly. No trailing space!
            full_cmd = f"set PORT={port}&& {start_cmd}"
        else:
            full_cmd = f"sudo -u deployrunner bash -c {shlex.quote(env_vars + start_cmd)}"

        log_file_handle = open(log_path, "a")
        
        # Cross-platform process group creation for clean termination
        if sys.platform == "win32":
            process = subprocess.Popen(
                full_cmd,
                shell=True,
                cwd=source_dir,
                stdout=log_file_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            process = subprocess.Popen(
                full_cmd,
                shell=True,
                cwd=source_dir,
                stdout=log_file_handle,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid  # Create a new process group on POSIX
            )
            
        # Wait a moment to catch immediate startup crashes
        time.sleep(1.5)
        if process.poll() is not None:
            raise Exception(f"Process crashed immediately on startup with exit code {process.returncode}. Check logs.")

        return {
            "process_pid": process.pid,
            "working_directory": source_dir,
            "runtime_type": config.get("runtime", "generic"),
            "start_command": start_cmd,
            "port": port
        }

    def stop(self, process_pid: int) -> bool:
        if not process_pid:
            return True
        import sys
        import signal
        try:
            if sys.platform == "win32":
                import ctypes
                # Windows equivalent of sending SIGTERM/SIGKILL to process group
                subprocess.call(['taskkill', '/F', '/T', '/PID', str(process_pid)])
            else:
                os.killpg(os.getpgid(process_pid), signal.SIGTERM)
                time.sleep(1)
                os.killpg(os.getpgid(process_pid), signal.SIGKILL)
        except ProcessLookupError:
            pass # Already dead
        except Exception as e:
            logger.warning(f"Failed to kill process {process_pid}: {e}")
            return False
        return True

    def restart(self, deployment_id: str, working_directory: str, start_command: str, port: int) -> dict:
        log_path = os.path.join(working_directory, "..", "pipeline.log")
        env_vars = f"PORT={port} "
        
        import sys
        if sys.platform == "win32":
            full_cmd = f"set PORT={port} && {start_command}"
        else:
            full_cmd = f"sudo -u deployrunner bash -c {shlex.quote(env_vars + start_command)}"
        
        log_file_handle = open(log_path, "a")
        log_file_handle.write(f"\\n[NATIVE] System Reboot Recovery... Restarting {deployment_id[:8]}\\n")
        
        if sys.platform == "win32":
            process = subprocess.Popen(
                full_cmd,
                shell=True,
                cwd=working_directory,
                stdout=log_file_handle,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            process = subprocess.Popen(
                full_cmd,
                shell=True,
                cwd=working_directory,
                stdout=log_file_handle,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid
            )
            
        time.sleep(1.5)
        if process.poll() is not None:
            raise Exception(f"Process crashed immediately on restart with exit code {process.returncode}")
            
        return {"process_pid": process.pid}
