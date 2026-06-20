import os
import subprocess
from utils.logger import setup_logger

logger = setup_logger(__name__)

class CaddySSLManager:
    """
    Automated SSL and reverse proxy management using Caddy.
    Generates a Caddyfile mapping the internal container port to the public domain.
    """
    def __init__(self, storage_dir: str):
        self.caddy_dir = os.path.join(storage_dir, "caddy")
        self.caddyfile_path = os.path.join(self.caddy_dir, "Caddyfile")
        os.makedirs(self.caddy_dir, exist_ok=True)
        
        if not os.path.exists(self.caddyfile_path):
            with open(self.caddyfile_path, "w") as f:
                f.write("# Auto-generated Caddyfile by AI-CICD-Monitor\\n")

    def assign_domain(self, domain: str, internal_port: int) -> bool:
        """
        Appends the reverse proxy configuration to the Caddyfile and reloads Caddy.
        """
        logger.info(f"Assigning domain {domain} to port {internal_port} via Caddy")
        
        with open(self.caddyfile_path, "r") as f:
            content = f.read()
            if f"{domain} {{" in content:
                logger.info(f"Domain {domain} already configured in Caddyfile.")
                return self._reload_caddy()
                
        config_block = f"\\n{domain} {{\\n    reverse_proxy localhost:{internal_port}\\n}}\\n"
        with open(self.caddyfile_path, "a") as f:
            f.write(config_block)
            
        return self._reload_caddy()

    def _reload_caddy(self) -> bool:
        """
        Reloads the Caddy server to apply the new configuration.
        """
        try:
            subprocess.run(
                ["caddy", "reload", "--config", self.caddyfile_path],
                check=True,
                capture_output=True,
                text=True
            )
            return True
        except FileNotFoundError:
            logger.warning("Caddy executable not found in PATH. Please install Caddy for SSL features.")
            return False
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to reload Caddy: {e.stderr}")
            return False
