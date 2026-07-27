"""OAuth2 token management and verification module."""
import time
import uuid
from typing import Dict, List, Optional, Any, Set
import jwt  # PyJWT

SECRET_KEY = "edysor-production-secret-key-change-in-prod"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600
REFRESH_TOKEN_EXPIRE_SECONDS = 86400 * 7

# In-memory revocation denylist for tokens (in production, use Redis)
_REVOKED_TOKENS: Set[str] = set()


def _encode_token(payload: Dict[str, Any], key: str = SECRET_KEY, algorithm: str = ALGORITHM) -> str:
    """Encode a JWT payload into a token string."""
    return jwt.encode(payload, key, algorithm=algorithm)


def _decode_token(token: str, key: str = SECRET_KEY, algorithm: str = ALGORITHM) -> Optional[Dict[str, Any]]:
    """Decode and verify a JWT token string."""
    if token in _REVOKED_TOKENS:
        return None
    try:
        payload = jwt.decode(token, key, algorithms=[algorithm], options={"verify_aud": False, "verify_iss": False})
        return payload
    except jwt.PyJWTError:
        return None


def create_access_token(
    sub: str, username: str, roles: List[str], tenant: Optional[str] = None
) -> str:
    """Create a new JWT access token."""
    now = int(time.time())
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": sub,
        "username": username,
        "roles": roles,
        "type": "access",
        "iss": "edysor-soc",
        "aud": "edysor-api",
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE_SECONDS,
    }
    if tenant:
        payload["tenant"] = tenant
    return _encode_token(payload)


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify an access token and return its payload if valid."""
    payload = _decode_token(token)
    if payload and payload.get("type") == "access":
        return payload
    return None


def create_token_pair(sub: str, username: str, roles: List[str]) -> Dict[str, str]:
    """Create a pair of access and refresh tokens."""
    access_token = create_access_token(sub, username, roles)
    
    now = int(time.time())
    refresh_payload = {
        "jti": str(uuid.uuid4()),
        "sub": sub,
        "username": username,
        "roles": roles,
        "type": "refresh",
        "iss": "edysor-soc",
        "aud": "edysor-api",
        "iat": now,
        "exp": now + REFRESH_TOKEN_EXPIRE_SECONDS,
    }
    refresh_token = _encode_token(refresh_payload)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
    }


def refresh_tokens(refresh_token: str, username: str, roles: List[str]) -> Optional[Dict[str, str]]:
    """Verify refresh token and issue a new token pair, revoking the old refresh token."""
    payload = _decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return None
    
    revoke_token(refresh_token)
    sub = str(payload.get("sub", username))
    return create_token_pair(sub, username, roles)


def revoke_token(token: str) -> None:
    """Revoke a token by adding it to the denylist."""
    _REVOKED_TOKENS.add(token)
