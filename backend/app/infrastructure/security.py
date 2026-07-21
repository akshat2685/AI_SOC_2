import secrets
import hashlib
from typing import Tuple

def generate_api_key() -> Tuple[str, str, str]:
    """
    Generates a secure API key.
    Returns:
        tuple: (raw_key, key_prefix, key_hash)
    """
    raw_key = secrets.token_urlsafe(32) # 43 characters
    key_prefix = raw_key[:8]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_prefix, key_hash

def hash_api_key(raw_key: str) -> str:
    """
    Hashes an API key for lookup.
    """
    return hashlib.sha256(raw_key.encode()).hexdigest()
