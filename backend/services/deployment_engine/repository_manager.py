import os
import subprocess
from utils.logger import setup_logger
from services.deployment_config import DeploymentConfigParser

logger = setup_logger(__name__)

class RepositoryManager:
    """
    Handles cloning the repository, checking out the specific commit, 
    preparing the deployment storage, and reading deployment.txt.
    """
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.releases_dir = os.path.join(storage_dir, "releases")
        os.makedirs(self.releases_dir, exist_ok=True)
        self.config_parser = DeploymentConfigParser()

    def prepare_storage_and_clone(self, deployment_id: str, clone_url: str, branch: str, commit_sha: str = None, github_token: str = None, log_path: str = None) -> dict:
        """
        Creates the release directory and clones the repo.
        Returns a dictionary containing 'release_dir' and 'source_dir'.
        """
        release_dir = os.path.join(self.releases_dir, deployment_id)
        source_dir = os.path.join(release_dir, "source")
        
        os.makedirs(release_dir, exist_ok=True)
        
        # Format the clone URL with token if provided
        if github_token and "://" in clone_url:
            proto, rest = clone_url.split("://", 1)
            # Use just the token, GitHub PATs don't need 'oauth2:' prefix
            auth_url = f"{proto}://{github_token}@{rest}"
        else:
            auth_url = clone_url
            
        logger.info(f"Cloning {clone_url} (branch {branch}) into {source_dir}")
        if log_path:
            with open(log_path, "a") as f:
                f.write(f"\n[CLONE] Cloning {clone_url} (branch {branch})...\n")
        
        try:
            env = os.environ.copy()
            env["GIT_TERMINAL_PROMPT"] = "0"
            
            # Clone only the specific branch to save time/space
            proc = subprocess.run(
                ["git", "clone", "--branch", branch, "--single-branch", auth_url, source_dir],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
                env=env
            )
            if log_path and proc.stdout:
                with open(log_path, "a") as f: f.write(proc.stdout + "\n")
            if log_path and proc.stderr:
                with open(log_path, "a") as f: f.write(proc.stderr + "\n")
            
            if commit_sha:
                proc2 = subprocess.run(
                    ["git", "checkout", commit_sha],
                    cwd=source_dir,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if log_path and proc2.stdout:
                    with open(log_path, "a") as f: f.write(proc2.stdout + "\n")
                if log_path and proc2.stderr:
                    with open(log_path, "a") as f: f.write(proc2.stderr + "\n")
        except subprocess.TimeoutExpired:
            raise Exception("Repository checkout timed out. Check authentication or network.")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Git operation failed: {e.stderr}")
            
        return {
            "release_dir": release_dir,
            "source_dir": source_dir
        }

    def parse_configuration(self, source_dir: str) -> dict:
        """
        Reads and validates deployment.txt.
        """
        return self.config_parser.parse(source_dir)
