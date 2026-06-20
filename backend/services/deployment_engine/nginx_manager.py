import os
import sys
import subprocess
from utils.logger import setup_logger

logger = setup_logger(__name__)

class NginxManager:
    """
    Manages the auto-generation and orchestration of Nginx reverse proxy configurations.
    """
    def __init__(self):
        self.sites_available = "/etc/nginx/sites-available"
        self.sites_enabled = "/etc/nginx/sites-enabled"

    def is_supported(self) -> bool:
        return sys.platform.startswith("linux")

    def generate_config(self, project_name: str, domain: str, port: int, release_dir: str = None, log_path: str = None) -> bool:
        config_path = os.path.join(self.sites_available, project_name)
        symlink_path = os.path.join(self.sites_enabled, project_name)
        
        content = f"""server {{
    listen 80;
    server_name {domain};

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""
        # 1. Always save a local copy to the release directory for the user to inspect
        if release_dir:
            nginx_dir = os.path.join(release_dir, "nginx")
            os.makedirs(nginx_dir, exist_ok=True)
            local_nginx_path = os.path.join(nginx_dir, "nginx.conf")
            try:
                with open(local_nginx_path, "w") as f:
                    f.write(content)
                if log_path:
                    with open(log_path, "a") as f:
                        f.write(f"\n[NGINX] Generated Nginx configuration and saved local copy to {local_nginx_path}\n")
                        f.write(f"[NGINX] File contents:\n{content}\n")
            except Exception as e:
                logger.error(f"Failed to write local Nginx config: {e}")

        # 2. Skip system-level Nginx installation if not supported (e.g. Windows)
        if not self.is_supported():
            logger.warning("Nginx is not supported on this OS. Skipping system-level Nginx config generation.")
            if log_path:
                with open(log_path, "a") as f:
                    f.write("[NGINX] Skipping system-level /etc/nginx configuration (Unsupported OS).\n")
            return True
        try:
            # Write config file
            cmd = f"sudo bash -c 'cat > {config_path}'"
            proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, text=True)
            proc.communicate(input=content)
            
            if proc.returncode != 0:
                raise Exception(f"Failed to write nginx config {config_path}")
                
            # Create symlink if it doesn't exist
            link_cmd = f"sudo ln -sfn {config_path} {symlink_path}"
            subprocess.run(link_cmd, shell=True, check=True)
            return True
        except Exception as e:
            logger.error(f"Failed to generate Nginx config: {e}")
            raise

    def reload(self) -> bool:
        if not self.is_supported():
            logger.info("Nginx not supported. Simulated reload.")
            return True
        try:
            # Test config first
            subprocess.run(["sudo", "nginx", "-t"], check=True)
            # Reload Nginx
            subprocess.run(["sudo", "systemctl", "reload", "nginx"], check=True)
            return True
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to reload Nginx: {e}")
