import os
import json
import psycopg
from typing import Dict, Any, List, Optional

class MemoryLearningSystem:
    def __init__(self, dsn: str = None):
        self.dsn = dsn or os.getenv("POSTGRES_DSN", "postgresql://postgres:postgres@localhost:5432/ai_soc")

    def _get_connection(self):
        import psycopg
        return psycopg.connect(self.dsn)

    def initialize_schema(self):
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS incident_memory (
                        id SERIAL PRIMARY KEY,
                        incident_id VARCHAR(255) NOT NULL,
                        incident_data JSONB NOT NULL,
                        resolution_status VARCHAR(50),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cur.execute('''
                    CREATE TABLE IF NOT EXISTS action_approvals (
                        id SERIAL PRIMARY KEY,
                        incident_id VARCHAR(255) NOT NULL,
                        suggested_action JSONB NOT NULL,
                        status VARCHAR(50) DEFAULT 'PENDING',
                        human_feedback TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            conn.commit()

    def record_incident(self, incident_id: str, incident_data: Dict[str, Any], status: str = 'OPEN') -> int:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO incident_memory (incident_id, incident_data, resolution_status) VALUES (%s, %s, %s) RETURNING id",
                    (incident_id, json.dumps(incident_data), status)
                )
                record_id = cur.fetchone()[0]
            conn.commit()
            return record_id

    def request_human_approval(self, incident_id: str, suggested_action: Dict[str, Any]) -> int:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO action_approvals (incident_id, suggested_action, status) VALUES (%s, %s, 'PENDING') RETURNING id",
                    (incident_id, json.dumps(suggested_action))
                )
                approval_id = cur.fetchone()[0]
            conn.commit()
            return approval_id

    def review_action(self, approval_id: int, status: str, human_feedback: Optional[str] = None):
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE action_approvals SET status = %s, human_feedback = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (status, human_feedback, approval_id)
                )
            conn.commit()

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, incident_id, suggested_action, status, human_feedback FROM action_approvals WHERE status = 'PENDING'"
                )
                rows = cur.fetchall()
                return [
                    {
                        "id": row[0],
                        "incident_id": row[1],
                        "suggested_action": row[2],
                        "status": row[3],
                        "human_feedback": row[4]
                    }
                    for row in rows
                ]

    def get_incident_memory(self, incident_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT incident_id, incident_data, resolution_status FROM incident_memory WHERE incident_id = %s",
                    (incident_id,)
                )
                row = cur.fetchone()
                if row:
                    return {
                        "incident_id": row[0],
                        "incident_data": row[1],
                        "resolution_status": row[2]
                    }
                return None
