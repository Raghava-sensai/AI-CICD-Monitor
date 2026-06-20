import os
import json
import datetime
from typing import List, Dict

class TimelineService:
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir

    def _get_path(self, deployment_id: str) -> str:
        return os.path.join(self.storage_dir, "releases", deployment_id, "stages.json")

    def _load(self, deployment_id: str) -> List[Dict]:
        path = self._get_path(deployment_id)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save(self, deployment_id: str, stages: List[Dict]) -> None:
        path = self._get_path(deployment_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(stages, f, indent=2)

    def start_stage(self, deployment_id: str, stage_name: str) -> None:
        stages = self._load(deployment_id)
        # End any currently running stage
        for s in stages:
            if s.get("status") == "running" and not s.get("ended_at"):
                s["ended_at"] = datetime.datetime.utcnow().isoformat()
                s["status"] = "success"
                s["success"] = True

        stages.append({
            "stage": stage_name,
            "started_at": datetime.datetime.utcnow().isoformat(),
            "ended_at": None,
            "status": "running"
        })
        self._save(deployment_id, stages)

    def end_stage(self, deployment_id: str, stage_name: str, success: bool = True, skipped: bool = False) -> None:
        stages = self._load(deployment_id)
        now = datetime.datetime.utcnow().isoformat()
        
        for s in reversed(stages):
            if s["stage"] == stage_name:
                s["ended_at"] = now
                s["success"] = success
                s["skipped"] = skipped
                
                if skipped:
                    s["status"] = "skipped"
                else:
                    s["status"] = "success" if success else "failed"
                    
                if s.get("started_at"):
                    start = datetime.datetime.fromisoformat(s["started_at"])
                    end = datetime.datetime.fromisoformat(now)
                    s["duration"] = round((end - start).total_seconds(), 1)
                break
        
        self._save(deployment_id, stages)
