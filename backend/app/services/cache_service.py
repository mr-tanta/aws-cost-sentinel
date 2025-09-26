import json
import pickle
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List, Union
import redis
import structlog
from redis.exceptions import RedisError

from app.core.config import settings

logger = structlog.get_logger(__name__)


class CacheService:
    """Redis-based caching service for performance optimization"""

    def __init__(self):
        self.redis_client = None
        self._connect()

    def _connect(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=False,  # Handle binary data
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Test connection
            self.redis_client.ping()
            logger.info("Redis connection established", redis_url=settings.REDIS_URL)
        except RedisError as e:
            logger.error("Failed to connect to Redis", error=str(e))
            self.redis_client = None

    def _serialize(self, value: Any) -> bytes:
        """Serialize value for Redis storage"""
        if isinstance(value, (dict, list)):
            return json.dumps(value, default=str).encode('utf-8')
        elif isinstance(value, (str, int, float, bool)):
            return json.dumps(value).encode('utf-8')
        else:
            return pickle.dumps(value)

    def _deserialize(self, value: bytes) -> Any:
        """Deserialize value from Redis storage"""
        try:
            # Try JSON first (most common case)
            return json.loads(value.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Fall back to pickle
            return pickle.loads(value)

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis_client:
            return None

        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            return self._deserialize(value)
        except RedisError as e:
            logger.error("Redis get failed", key=key, error=str(e))
            return None

    def set(
        self,
        key: str,
        value: Any,
        expire: Optional[int] = None
    ) -> bool:
        """Set value in cache with optional expiration"""
        if not self.redis_client:
            return False

        try:
            serialized_value = self._serialize(value)
            return self.redis_client.set(key, serialized_value, ex=expire)
        except RedisError as e:
            logger.error("Redis set failed", key=key, error=str(e))
            return False

    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.redis_client:
            return False

        try:
            return bool(self.redis_client.delete(key))
        except RedisError as e:
            logger.error("Redis delete failed", key=key, error=str(e))
            return False

    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.redis_client:
            return False

        try:
            return bool(self.redis_client.exists(key))
        except RedisError as e:
            logger.error("Redis exists check failed", key=key, error=str(e))
            return False

    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Increment integer value in cache"""
        if not self.redis_client:
            return None

        try:
            return self.redis_client.incrby(key, amount)
        except RedisError as e:
            logger.error("Redis increment failed", key=key, error=str(e))
            return None

    def expire(self, key: str, seconds: int) -> bool:
        """Set expiration for existing key"""
        if not self.redis_client:
            return False

        try:
            return self.redis_client.expire(key, seconds)
        except RedisError as e:
            logger.error("Redis expire failed", key=key, error=str(e))
            return False

    def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from cache"""
        if not self.redis_client or not keys:
            return {}

        try:
            values = self.redis_client.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value is not None:
                    result[key] = self._deserialize(value)
            return result
        except RedisError as e:
            logger.error("Redis mget failed", keys=keys, error=str(e))
            return {}

    def set_many(
        self,
        mapping: Dict[str, Any],
        expire: Optional[int] = None
    ) -> bool:
        """Set multiple values in cache"""
        if not self.redis_client or not mapping:
            return False

        try:
            # Serialize all values
            serialized_mapping = {
                key: self._serialize(value)
                for key, value in mapping.items()
            }

            # Use pipeline for atomic operation
            pipe = self.redis_client.pipeline()
            pipe.mset(serialized_mapping)

            # Set expiration if specified
            if expire:
                for key in mapping.keys():
                    pipe.expire(key, expire)

            pipe.execute()
            return True
        except RedisError as e:
            logger.error("Redis mset failed", error=str(e))
            return False

    def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        if not self.redis_client:
            return 0

        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except RedisError as e:
            logger.error("Redis pattern delete failed", pattern=pattern, error=str(e))
            return 0

    def flush_db(self) -> bool:
        """Flush entire Redis database (use with caution)"""
        if not self.redis_client:
            return False

        try:
            self.redis_client.flushdb()
            return True
        except RedisError as e:
            logger.error("Redis flush failed", error=str(e))
            return False

    def get_info(self) -> Dict[str, Any]:
        """Get Redis server information"""
        if not self.redis_client:
            return {}

        try:
            return self.redis_client.info()
        except RedisError as e:
            logger.error("Redis info failed", error=str(e))
            return {}

    # Specialized cache methods for common use cases

    def cache_report_info(self, account_id: str, report_info: Dict[str, Any], ttl: int = 86400) -> bool:
        """Cache report information"""
        try:
            key = f"report_info:{account_id}:{report_info.get('format', 'pdf')}"
            return self.set(key, report_info, expire=ttl)
        except Exception as e:
            logger.error("Failed to cache report info", error=str(e))
            return False

    def get_report_info(self, account_id: str, format_type: str = "pdf") -> Optional[Dict[str, Any]]:
        """Get cached report information"""
        try:
            key = f"report_info:{account_id}:{format_type}"
            return self.get(key)
        except Exception as e:
            logger.error("Failed to get report info", error=str(e))
            return None

    def cache_cost_data(
        self,
        account_id: str,
        start_date: str,
        end_date: str,
        data: Any,
        ttl: int = 3600  # 1 hour default
    ) -> bool:
        """Cache cost data with standardized key format"""
        key = f"cost_data:{account_id}:{start_date}:{end_date}"
        return self.set(key, data, expire=ttl)

    def get_cached_cost_data(
        self,
        account_id: str,
        start_date: str,
        end_date: str
    ) -> Optional[Any]:
        """Get cached cost data"""
        key = f"cost_data:{account_id}:{start_date}:{end_date}"
        return self.get(key)

    def cache_recommendations(
        self,
        account_id: str,
        recommendations: List[Dict[str, Any]],
        ttl: int = 1800  # 30 minutes default
    ) -> bool:
        """Cache recommendations for account"""
        key = f"recommendations:{account_id}"
        return self.set(key, recommendations, expire=ttl)

    def get_cached_recommendations(self, account_id: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached recommendations"""
        key = f"recommendations:{account_id}"
        return self.get(key)

    def cache_waste_scan_results(
        self,
        account_id: str,
        scan_results: Dict[str, Any],
        ttl: int = 7200  # 2 hours default
    ) -> bool:
        """Cache waste scan results"""
        key = f"waste_scan:{account_id}"
        return self.set(key, scan_results, expire=ttl)

    def get_cached_waste_scan(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Get cached waste scan results"""
        key = f"waste_scan:{account_id}"
        return self.get(key)

    def cache_user_session(
        self,
        user_id: str,
        session_data: Dict[str, Any],
        ttl: int = 86400  # 24 hours
    ) -> bool:
        """Cache user session data"""
        key = f"session:{user_id}"
        return self.set(key, session_data, expire=ttl)

    def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached user session"""
        key = f"session:{user_id}"
        return self.get(key)

    def invalidate_user_cache(self, user_id: str) -> int:
        """Invalidate all cache entries for a user"""
        pattern = f"*:{user_id}:*"
        return self.delete_pattern(pattern)

    def invalidate_account_cache(self, account_id: str) -> int:
        """Invalidate all cache entries for an account"""
        patterns = [
            f"cost_data:{account_id}:*",
            f"recommendations:{account_id}",
            f"waste_scan:{account_id}"
        ]
        total_deleted = 0
        for pattern in patterns:
            total_deleted += self.delete_pattern(pattern)
        return total_deleted

    # Rate limiting functionality

    def is_rate_limited(
        self,
        identifier: str,
        limit: int,
        window: int
    ) -> bool:
        """Check if identifier is rate limited"""
        if not self.redis_client:
            return False

        key = f"rate_limit:{identifier}"
        try:
            current = self.redis_client.get(key)
            if current is None:
                # First request
                self.redis_client.setex(key, window, 1)
                return False

            current_count = int(current)
            if current_count >= limit:
                return True

            # Increment counter
            self.redis_client.incr(key)
            return False
        except RedisError as e:
            logger.error("Rate limit check failed", key=key, error=str(e))
            return False

    def get_rate_limit_info(
        self,
        identifier: str
    ) -> Dict[str, Optional[int]]:
        """Get current rate limit information"""
        if not self.redis_client:
            return {"current": None, "ttl": None}

        key = f"rate_limit:{identifier}"
        try:
            current = self.redis_client.get(key)
            ttl = self.redis_client.ttl(key)

            return {
                "current": int(current) if current else None,
                "ttl": ttl if ttl > 0 else None
            }
        except RedisError as e:
            logger.error("Rate limit info failed", key=key, error=str(e))
            return {"current": None, "ttl": None}


# Global cache service instance
cache_service = CacheService()