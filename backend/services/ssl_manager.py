"""
SSL Manager - Provisions and manages TLS certificates via Let's Encrypt / certbot.
"""

import subprocess
import os
from utils.logger import setup_logger
from utils.shell import run_command

logger = setup_logger(__name__)

CERTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "certs")


class SSLManager:
    """
    Manages SSL/TLS certificate provisioning for deployed projects.
    Uses certbot (Let's Encrypt) for automatic certificate issuance
    and renewal.  Falls back to self-signed certs for local/dev usage.
    """

    def __init__(self, certs_dir: str = CERTS_DIR):
        self.certs_dir = certs_dir
        os.makedirs(self.certs_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def provision(self, domain: str, email: str = "") -> dict:
        """
        Provision a TLS certificate for *domain*.
        Returns a dict with cert_path and key_path.
        """
        cert_path = os.path.join(self.certs_dir, f"{domain}.crt")
        key_path = os.path.join(self.certs_dir, f"{domain}.key")

        if os.path.exists(cert_path) and os.path.exists(key_path):
            logger.info(f"Certificate already exists for {domain}.")
            return {"cert_path": cert_path, "key_path": key_path, "domain": domain}

        logger.info(f"Provisioning SSL certificate for {domain}...")
        # Attempt certbot; fall back to self-signed
        if self._certbot_available():
            success = self._issue_letsencrypt(domain, email)
        else:
            success = self._issue_self_signed(domain, cert_path, key_path)

        if success:
            logger.info(f"Certificate provisioned for {domain}.")
            return {"cert_path": cert_path, "key_path": key_path, "domain": domain}
        else:
            logger.error(f"Failed to provision certificate for {domain}.")
            return {"error": "certificate provisioning failed", "domain": domain}

    def revoke(self, domain: str) -> bool:
        """Remove existing certificates for *domain*."""
        cert_path = os.path.join(self.certs_dir, f"{domain}.crt")
        key_path = os.path.join(self.certs_dir, f"{domain}.key")
        removed = False
        for path in (cert_path, key_path):
            if os.path.exists(path):
                os.remove(path)
                removed = True
        if removed:
            logger.info(f"Certificates revoked for {domain}.")
        return removed

    # ------------------------------------------------------------------
    # Internal Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _certbot_available() -> bool:
        try:
            result = subprocess.run(
                ["certbot", "--version"], capture_output=True, timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _issue_letsencrypt(self, domain: str, email: str) -> bool:
        cmd = [
            "certbot",
            "certonly",
            "--standalone",
            "-d",
            domain,
            "--non-interactive",
            "--agree-tos",
            "--email",
            email or f"admin@{domain}",
        ]
        stdout, stderr, code = run_command(cmd)
        return code == 0

    def _issue_self_signed(self, domain: str, cert_path: str, key_path: str) -> bool:
        cmd = [
            "openssl",
            "req",
            "-x509",
            "-nodes",
            "-days",
            "365",
            "-newkey",
            "rsa:2048",
            "-keyout",
            key_path,
            "-out",
            cert_path,
            "-subj",
            f"/CN={domain}",
        ]
        stdout, stderr, code = run_command(cmd)
        return code == 0
