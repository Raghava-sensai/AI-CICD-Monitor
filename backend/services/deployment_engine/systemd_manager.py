import os
import sys
import subprocess
from utils.logger import setup_logger

logger = setup_logger(__name__)

class SystemdManager:
    """
    Manages the auto-generation and orchestration of systemd service files.
    """
    def __init__(self):
        self.systemd_dir = "/etc/systemd/system"

    def is_supported(self) -> bool:
        return sys.platform.startswith("linux")

    def generate_service(self, project_name: str, config: dict, current_dir: str, port: int, release_dir: str = None, log_path: str = None) -> bool:
        service_path = os.path.join(self.systemd_dir, f"{project_name}.service")
        
        # Build the service file content
        content = f"""[Unit]
Description=AI-CICD-Monitor: {project_name}
After=network.target

[Service]
WorkingDirectory={current_dir}
ExecStart={config.get('start_command', '')}
Restart=always
User=deployrunner
Environment=PORT={port}
Environment=NODE_ENV=production
"""
        # Inject other environment variables from config if they exist
        env_vars = config.get("environment", {})
        for k, v in env_vars.items():
            content += f"Environment={k}={v}\n"

        content += """
[Install]
WantedBy=multi-user.target
"""
        # Always save a local copy to the release directory for the user to inspect
        if release_dir:
            systemd_dir = os.path.join(release_dir, "systemd")
            os.makedirs(systemd_dir, exist_ok=True)
            local_systemd_path = os.path.join(systemd_dir, f"{project_name}.service")
            try:
                with open(local_systemd_path, "w") as f:
                    f.write(content)
                if log_path:
                    with open(log_path, "a") as f:
                        f.write(f"\n[SYSTEMD] Generated Systemd service configuration and saved local copy to {local_systemd_path}\n")
            except Exception as e:
                logger.error(f"Failed to write local Systemd config: {e}")

        if not self.is_supported():
            logger.warning("Systemd is not supported on this OS. Skipping system-level service generation.")
            if log_path:
                with open(log_path, "a") as f:
                    f.write("[SYSTEMD] Skipping system-level /etc/systemd/system configuration (Unsupported OS).\n")
            return True
        
        # Write the file (requires sudo)
        try:
            # We use sudo bash -c to write the file because /etc/systemd/system requires root
            cmd = f"sudo bash -c 'cat > {service_path}'"
            proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, text=True)
            proc.communicate(input=content)
            
            if proc.returncode != 0:
                raise Exception(f"Failed to write service file {service_path}")
                
            # Reload daemon and enable service
            subprocess.run(["sudo", "systemctl", "daemon-reload"], check=True)
            subprocess.run(["sudo", "systemctl", "enable", project_name], check=True)
            return True
        except Exception as e:
            logger.error(f"Failed to generate systemd service: {e}")
            raise

    def restart_service(self, project_name: str) -> bool:
        if not self.is_supported():
            logger.info("Systemd not supported. Simulated service restart.")
            return True
        try:
            subprocess.run(["sudo", "systemctl", "restart", project_name], check=True)
            return True
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to restart systemd service {project_name}: {e}")

    def get_status(self, project_name: str) -> str:
        if not self.is_supported():
            return "simulated"
        try:
            res = subprocess.run(["sudo", "systemctl", "is-active", project_name], capture_output=True, text=True)
            return res.stdout.strip()
        except subprocess.CalledProcessError:
            return "failed"
