import os
import subprocess
from .base import ProcessManager

class SystemdManager(ProcessManager):
    def start(self, project_name: str, start_command: str, work_dir: str, port: int, log_file) -> dict:
        log_file.write(f"\n[SYSTEMD] Starting {project_name} on port {port} via User Systemd\n")
        
        service_name = f"aicicd-{project_name}.service"
        
        # User systemd directory
        systemd_dir = os.path.expanduser("~/.config/systemd/user")
        os.makedirs(systemd_dir, exist_ok=True)
        
        service_path = os.path.join(systemd_dir, service_name)
        
        service_content = f"""[Unit]
Description=AI-CICD Deployment: {project_name}
After=network.target

[Service]
Type=simple
WorkingDirectory={work_dir}
Environment=PORT={port}
ExecStart={start_command}
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
"""
        
        try:
            with open(service_path, "w") as f:
                f.write(service_content)
                
            log_file.write(f"Created systemd service file at {service_path}\n")
            
            # Reload daemon
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
            
            # Start service
            subprocess.run(["systemctl", "--user", "restart", service_name], check=True)
            
            # Enable service
            subprocess.run(["systemctl", "--user", "enable", service_name], check=True)
            
            return {
                "success": True,
                "pid": None,
                "output": f"Successfully started {service_name} via Systemd."
            }
            
        except Exception as e:
            import traceback
            log_file.write(traceback.format_exc() + "\n")
            return {
                "success": False,
                "output": f"Systemd exception: {e}"
            }

    def stop(self, project_name: str) -> bool:
        service_name = f"aicicd-{project_name}.service"
        try:
            subprocess.run(["systemctl", "--user", "stop", service_name], check=True)
            subprocess.run(["systemctl", "--user", "disable", service_name], check=True)
            return True
        except Exception:
            return False
