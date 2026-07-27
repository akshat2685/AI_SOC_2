"""Session tracking and concurrent session management module."""
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Session:
    """Active user session representation."""
    session_id: str
    user_id: str
    username: str
    role: str
    tenant: str
    ip_address: str
    user_agent: str
    created_at: float
    last_active: float


class SessionManager:
    """Manages user sessions and enforces concurrent session limits."""

    DEFAULT_CONCURRENT_LIMITS: Dict[str, int] = {
        "soc_analyst": 3,
        "analyst": 3,
        "soc_manager": 5,
        "manager": 5,
        "admin": 10,
    }

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[str, List[str]] = {}

    def create_session(
        self,
        user_id: str,
        username: str,
        role: str,
        tenant: str,
        ip_address: str,
        user_agent: str,
    ) -> Session:
        """Create a new session and enforce concurrent session limits."""
        now = time.time()
        session_id = str(uuid.uuid4())
        session = Session(
            session_id=session_id,
            user_id=user_id,
            username=username,
            role=role,
            tenant=tenant,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
            last_active=now,
        )

        # Enforce limits
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        
        limit = self.DEFAULT_CONCURRENT_LIMITS.get(role.lower(), 5)
        while len(self._user_sessions[user_id]) >= limit:
            oldest_sid = self._user_sessions[user_id].pop(0)
            if oldest_sid in self._sessions:
                del self._sessions[oldest_sid]

        self._sessions[session_id] = session
        self._user_sessions[user_id].append(session_id)
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Retrieve an active session by ID."""
        return self._sessions.get(session_id)

    def list_active_sessions(self, user_id: str) -> List[Session]:
        """List all active sessions for a user."""
        sids = self._user_sessions.get(user_id, [])
        return [self._sessions[sid] for sid in sids if sid in self._sessions]

    def terminate_session(self, session_id: str) -> bool:
        """Terminate a session by ID."""
        if session_id in self._sessions:
            session = self._sessions.pop(session_id)
            if session.user_id in self._user_sessions:
                self._user_sessions[session.user_id] = [
                    sid for sid in self._user_sessions[session.user_id] if sid != session_id
                ]
            return True
        return False
