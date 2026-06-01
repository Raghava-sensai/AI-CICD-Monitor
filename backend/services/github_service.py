"""
GitHub Service - Handles GitHub API interactions and webhook event processing.
"""

import os
import requests
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GithubService:
    def __init__(self):
        self.token = os.environ.get("GITHUB_TOKEN", "")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ------------------------------------------------------------------
    # Webhook Event Handlers
    # ------------------------------------------------------------------

    def handle_push_event(self, payload: dict) -> dict:
        """Process a push event and decide whether to deploy."""
        repo = payload.get("repository", {}).get("full_name", "unknown")
        branch = payload.get("ref", "").replace("refs/heads/", "")
        commit_sha = payload.get("after", "")
        pusher = payload.get("pusher", {}).get("name", "unknown")

        logger.info(f"Push event: {repo}@{branch} by {pusher} (sha={commit_sha})")

        return {
            "repo": repo,
            "branch": branch,
            "commit_sha": commit_sha,
            "pusher": pusher,
            "should_deploy": branch in ("main", "master", "production"),
        }

    def handle_pr_event(self, payload: dict) -> dict:
        """Process a pull request event."""
        action = payload.get("action", "unknown")
        pr = payload.get("pull_request", {})
        return {
            "action": action,
            "pr_number": pr.get("number"),
            "title": pr.get("title"),
            "state": pr.get("state"),
            "repo": payload.get("repository", {}).get("full_name"),
        }

    def handle_workflow_event(self, payload: dict) -> dict:
        """Process a workflow_run event."""
        run = payload.get("workflow_run", {})
        return {
            "workflow": run.get("name"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "run_id": run.get("id"),
            "repo": payload.get("repository", {}).get("full_name"),
        }

    # ------------------------------------------------------------------
    # GitHub API Helpers
    # ------------------------------------------------------------------

    def get_repo_info(self, repo_full_name: str) -> Optional[dict]:
        """Fetch repository metadata from the GitHub API."""
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            logger.error(f"Failed to fetch repo info for {repo_full_name}: {exc}")
            return None

    def get_latest_commit(self, repo_full_name: str, branch: str = "main") -> Optional[dict]:
        """Return the latest commit on a branch."""
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/commits/{branch}"
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            return {
                "sha": data.get("sha"),
                "message": data.get("commit", {}).get("message"),
                "author": data.get("commit", {}).get("author", {}).get("name"),
                "date": data.get("commit", {}).get("author", {}).get("date"),
            }
        except requests.RequestException as exc:
            logger.error(f"Failed to fetch latest commit: {exc}")
            return None

    def post_commit_status(
        self,
        repo_full_name: str,
        sha: str,
        state: str,
        description: str,
        context: str = "ci/cd-monitor",
    ) -> bool:
        """Update the commit status on GitHub (pending / success / failure / error)."""
        url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/statuses/{sha}"
        payload = {
            "state": state,
            "description": description,
            "context": context,
        }
        try:
            response = requests.post(url, json=payload, headers=self.headers, timeout=10)
            response.raise_for_status()
            logger.info(f"Commit status '{state}' posted for {sha}")
            return True
        except requests.RequestException as exc:
            logger.error(f"Failed to post commit status: {exc}")
            return False
