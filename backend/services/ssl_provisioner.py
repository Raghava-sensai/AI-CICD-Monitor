import os
import subprocess

CADDY_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage", "caddy"))
CADDY_FILE = os.path.join(CADDY_DIR, "Caddyfile")

class SSLProvisioner:
    """
    Handles automatic SSL provisioning via Caddy.
    Generates/appends to a Caddyfile and reloads the Caddy daemon.
    """
    def provision(self, domain: str, port: int, log_file) -> bool:
        os.makedirs(CADDY_DIR, exist_ok=True)
        
        config_block = f"""
{domain} {{
    reverse_proxy 127.0.0.1:{port}
}}
"""
        try:
            content = ""
            if os.path.exists(CADDY_FILE):
                with open(CADDY_FILE, "r") as f:
                    content = f.read()
                    
            if domain in content:
                log_file.write(f"[SSL] Domain {domain} already exists in Caddyfile, skipping append.\n")
                # For a full implementation, you'd parse and replace the existing block.
                # For now, we skip appending if it exists to avoid duplicates.
            else:
                with open(CADDY_FILE, "a") as f:
                    f.write(config_block)
                log_file.write(f"[SSL] Appended reverse_proxy config for {domain} -> port {port}\n")
                
            log_file.write("[SSL] Reloading Caddy daemon...\n")
            
            # Attempt to reload. If Caddy isn't running, this will fail.
            res = subprocess.run(["caddy", "reload", "--config", CADDY_FILE], capture_output=True, text=True)
            if res.returncode != 0:
                log_file.write(f"[SSL] Caddy reload failed. Attempting to start Caddy in background...\n")
                # Start caddy in the background
                subprocess.Popen(
                    ["caddy", "run", "--config", CADDY_FILE],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True # Detach from python process
                )
            
            log_file.write("[SSL] Caddy provisioned successfully.\n")
            return True
        except Exception as e:
            log_file.write(f"[SSL] Failed to provision Caddy: {e}\n")
            return False
