import threading
import subprocess
from utils.logger import setup_logger

logger = setup_logger(__name__)

class CertbotManager:
    """
    Handles asynchronous SSL provisioning via Certbot.
    """
    @staticmethod
    def provision_ssl_background(domain: str, release_dir: str = None, email: str = "admin@ai-cicd-monitor.com", log_path: str = None):
        def _run_certbot():
            logger.info(f"Starting background SSL provisioning for {domain}")
            try:
                # certbot --nginx -d domain --non-interactive --agree-tos -m email --redirect
                cmd = [
                    "sudo", "certbot", "--nginx", "-d", domain,
                    "--non-interactive", "--agree-tos", "-m", email, "--redirect"
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True)
                if proc.returncode == 0:
                    logger.info(f"Successfully provisioned SSL for {domain}")
                    if release_dir:
                        import os
                        ssl_dir = os.path.join(release_dir, "ssl")
                        os.makedirs(ssl_dir, exist_ok=True)
                        # Copy the certs from Let's Encrypt live directory to the local user directory
                        subprocess.run(f"sudo cp -L /etc/letsencrypt/live/{domain}/* {ssl_dir}/", shell=True, capture_output=True)
                        # Make them readable by the current user
                        subprocess.run(f"sudo chown -R $USER:$USER {ssl_dir}/", shell=True, capture_output=True)
                        logger.info(f"Copied SSL certificates to local user folder: {ssl_dir}")
                else:
                    logger.error(f"Certbot failed for {domain}: {proc.stderr}")
                    if log_path:
                        with open(log_path, "a") as f:
                            f.write(f"\n[WARNING] SSL certificate not generated: Certbot process failed for domain {domain}\n")
            except Exception as e:
                logger.error(f"Error executing certbot for {domain}: {e}")
                if log_path:
                    with open(log_path, "a") as f:
                        f.write(f"\n[WARNING] SSL certificate not generated: Exception while executing certbot - {e}\n")

        # Run in a detached background thread so it doesn't block the deployment pipeline
        thread = threading.Thread(target=_run_certbot, name=f"certbot-{domain}", daemon=True)
        thread.start()
