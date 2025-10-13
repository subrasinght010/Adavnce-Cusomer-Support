# System/utils/checkpoint.py
"""
Persistent SQLite Checkpoint for LangGraph (latest version)
Uses Python pickle for serialization
"""

import sqlite3
import pickle
from typing import Any, Optional
from langgraph.checkpoint.base import Checkpoint


class SQLiteCheckpoint(Checkpoint):
    def __init__(self, db_path: str = "langgraph_workflows.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_state (
                workflow_id TEXT PRIMARY KEY,
                state BLOB
            )
        """)
        self.conn.commit()

    def _save(self, workflow_id: str, state: Any):
        """Save workflow state to SQLite using pickle"""
        data = pickle.dumps(state)
        self.conn.execute(
            "REPLACE INTO workflow_state (workflow_id, state) VALUES (?, ?)",
            (workflow_id, data)
        )
        self.conn.commit()

    def _load(self, workflow_id: str) -> Optional[Any]:
        """Load workflow state from SQLite using pickle"""
        cur = self.conn.execute(
            "SELECT state FROM workflow_state WHERE workflow_id=?",
            (workflow_id,)
        ).fetchone()
        if cur:
            return pickle.loads(cur[0])
        return None

    def _delete(self, workflow_id: str):
        """Delete workflow state from SQLite"""
        self.conn.execute(
            "DELETE FROM workflow_state WHERE workflow_id=?",
            (workflow_id,)
        )
        self.conn.commit()
