import os
import sqlite3
import datetime
from typing import Dict, List, Optional

class AuditService:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS audit_trail (
                deployment_id TEXT PRIMARY KEY,
                repository TEXT,
                branch TEXT,
                commit_sha TEXT,
                triggered_by TEXT,
                status TEXT,
                error_type TEXT,
                timestamp TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def log_deployment(self, deployment: Dict) -> None:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''
            INSERT OR REPLACE INTO audit_trail 
            (deployment_id, repository, branch, commit_sha, triggered_by, status, error_type, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            deployment.get("deployment_id"),
            deployment.get("repo"),
            deployment.get("branch"),
            deployment.get("commit_sha", ""),
            deployment.get("triggered_by", "system"),
            deployment.get("status"),
            deployment.get("error_type", ""),
            datetime.datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()

    def get_recent_audits(self, limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM audit_trail ORDER BY timestamp DESC LIMIT ?', (limit,))
        rows = c.fetchall()
        conn.close()
        
        return [dict(r) for r in rows]
