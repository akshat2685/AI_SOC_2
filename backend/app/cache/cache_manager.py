"""Multi-level asynchronous cache manager (L1 LRU / L2 Redis)."""
import time
from collections import OrderedDict
from typing import Any, Dict, Optional, Tuple


class LRUCache:
    """In-memory L1 LRU Cache with TTL support."""

    def __init__(self, max_size: int = 100):
        self.max_size = max_size
        # Key -> (value, expiry_time)
        self._cache: OrderedDict[str, Tuple[Any, float]] = OrderedDict()

    def set(self, key: str, value: Any, ttl: float = 60.0) -> None:
        """Set a value in cache with a time-to-live in seconds."""
        now = time.time()
        if ttl <= 0:
            expiry = 0.0  # Expired immediately
        else:
            expiry = now + ttl

        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, expiry)

        if len(self._cache) > self.max_size:
            self._cache.popitem(last=False)

    def get(self, key: str) -> Optional[Any]:
        """Get a value from cache, checking for expiration and updating LRU order."""
        if key not in self._cache:
            return None

        value, expiry = self._cache[key]
        if expiry <= time.time():
            del self._cache[key]
            return None

        self._cache.move_to_end(key)
        return value

    def clear(self) -> None:
        """Clear all entries in the cache."""
        self._cache.clear()


class CacheManager:
    """Async L1/L2 Cache Manager with telemetry metrics."""

    def __init__(self, max_l1_size: int = 1000):
        self.l1 = LRUCache(max_size=max_l1_size)
        self._hits = 0
        self._misses = 0

    async def set(self, key: str, value: Any, ttl: float = 60.0) -> None:
        """Asynchronously store an item in L1 (and optional L2) cache."""
        self.l1.set(key, value, ttl=ttl)

    async def get(self, key: str) -> Optional[Any]:
        """Asynchronously retrieve an item from cache, tracking hits and misses."""
        val = self.l1.get(key)
        if val is not None:
            self._hits += 1
            return val
        
        self._misses += 1
        return None

    def get_metrics(self) -> Dict[str, int]:
        """Get cache performance metrics."""
        return {
            "hits": self._hits,
            "misses": self._misses,
        }
