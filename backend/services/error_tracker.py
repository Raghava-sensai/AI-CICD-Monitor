"""
Error Tracker - Globally tracks the frequency of errors across all deployments.
"""
import os
import json
from collections import defaultdict
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Basic in-memory store backed by a JSON file
STORAGE_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage", "global_errors.json")

class ErrorTracker:
    def __init__(self):
        self.error_counts = defaultdict(int)
        self._load()

    def _load(self):
        if os.path.exists(STORAGE_FILE):
            try:
                with open(STORAGE_FILE, "r") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.error_counts[k] = v
            except Exception as e:
                logger.error(f"Failed to load global errors: {e}")

    def _save(self):
        os.makedirs(os.path.dirname(STORAGE_FILE), exist_ok=True)
        try:
            with open(STORAGE_FILE, "w") as f:
                json.dump(self.error_counts, f)
        except Exception as e:
            logger.error(f"Failed to save global errors: {e}")

    def record_errors(self, error_ids: list[str]):
        """Record occurrences of specific error IDs."""
        if not error_ids:
            return
        for err_id in error_ids:
            self.error_counts[err_id] += 1
        self._save()

    def get_top_issues(self, limit: int = 10) -> list[dict]:
        """Return the most frequent errors sorted by count."""
        sorted_issues = sorted(self.error_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"error_id": k, "count": v} for k, v in sorted_issues[:limit]]
