"""Immutable audit logging module with hash chaining for chain-of-custody."""
import contextlib
import hashlib
import json
import sqlite3
import time
import uuid
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any


class AuditEventType(Enum):
    """Enumeration of audit event types."""
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    ALERT_VIEWED = "alert_viewed"
    INCIDENT_CREATED = "incident_created"
    CONTAINMENT_EXECUTED = "containment_executed"
    PERMISSION_CHANGED = "permission_changed"
    SYSTEM_CONFIG_CHANGED = "system_config_changed"


class AuditLogger:
    """Provides immutable, cryptographically verifiable audit logging."""

    def __init__(self, db_path: Optional[str] = ":memory:"):
        self.db_path = db_path or ":memory:"
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT UNIQUE NOT NULL,
                        event_type TEXT NOT NULL,
                        user_id TEXT NOT NULL,
                        resource_type TEXT NOT NULL,
                        resource_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        status TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        prev_hash TEXT NOT NULL,
                        record_hash TEXT NOT NULL
                    )
                """)

    def _get_latest_hash(self, conn: sqlite3.Connection) -> str:
        cursor = conn.cursor()
        cursor.execute("SELECT record_hash FROM audit_events ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else "0" * 64

    def _compute_hash(
        self,
        prev_hash: str,
        event_id: str,
        event_type: str,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        status: str,
        ts: float,
    ) -> str:
        payload = f"{prev_hash}|{event_id}|{event_type}|{user_id}|{resource_type}|{resource_id}|{action}|{status}|{ts}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def log_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        resource_type: str,
        resource_id: str,
        action: str,
        status: str,
    ) -> str:
        """Log an audit event with cryptographic chaining."""
        event_id = str(uuid.uuid4())
        event_type_str = event_type.value if isinstance(event_type, Enum) else str(event_type)
        ts = time.time()

        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                prev_hash = self._get_latest_hash(conn)
                record_hash = self._compute_hash(
                    prev_hash, event_id, event_type_str, user_id, resource_type, resource_id, action, status, ts
                )
                conn.execute(
                    """
                    INSERT INTO audit_events (
                        event_id, event_type, user_id, resource_type, resource_id, action, status, timestamp, prev_hash, record_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, event_type_str, user_id, resource_type, resource_id, action, status, ts, prev_hash, record_hash),
                )

        return event_id

    def query_events(
        self,
        user_id: Optional[str] = None,
        event_type: Optional[Any] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit events with optional filtering."""
        query = "SELECT event_id, event_type, user_id, resource_type, resource_id, action, status, timestamp, prev_hash, record_hash FROM audit_events WHERE 1=1"
        params: List[Any] = []

        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        if event_type:
            etype_str = event_type.value if isinstance(event_type, Enum) else str(event_type)
            query += " AND event_type = ?"
            params.append(etype_str)

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        results = []
        with contextlib.closing(self._get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor.fetchall():
                results.append({
                    "event_id": row[0],
                    "event_type": row[1],
                    "user_id": row[2],
                    "resource_type": row[3],
                    "resource_id": row[4],
                    "action": row[5],
                    "status": row[6],
                    "timestamp": row[7],
                    "prev_hash": row[8],
                    "record_hash": row[9],
                })
        return results

    def verify_chain_integrity(self) -> Tuple[bool, int]:
        """Verify the cryptographic integrity of the entire audit log chain."""
        with contextlib.closing(self._get_connection()) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, event_id, event_type, user_id, resource_type, resource_id, action, status, timestamp, prev_hash, record_hash FROM audit_events ORDER BY id ASC")
            rows = cursor.fetchall()

        if not rows:
            return True, 0

        expected_prev_hash = "0" * 64
        count = 0

        for row in rows:
            (_, event_id, event_type, user_id, resource_type, resource_id, action, status, ts, prev_hash, record_hash) = row
            if prev_hash != expected_prev_hash:
                return False, count
            computed_hash = self._compute_hash(
                prev_hash, event_id, event_type, user_id, resource_type, resource_id, action, status, ts
            )
            if computed_hash != record_hash:
                return False, count
            expected_prev_hash = record_hash
            count += 1

        return True, count
