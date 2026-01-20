import os
import time
import redis
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class RateLimiter:
    """
    Redis-based Rate Limiter for AI Providers.
    Manages daily quotas with auto-reset at midnight.
    Reference: Neural-Home Infrastructure Blueprint v3.0 - Phase 3
    """
    
    # Default limits (requests per day) - can be overridden by config
    DEFAULT_LIMITS = {
        "gemini": 1500,
        "groq": 1000,
        "qwen": 1000, # Cloud provider placeholder
        "ollama": 100000 # Local model, virtually unlimited
    }
    
    def __init__(self, redis_host='localhost', redis_port=6379, redis_db=0):
        # Allow override from env
        self.redis_host = os.getenv("REDIS_HOST", redis_host)
        self.redis_port = int(os.getenv("REDIS_PORT", redis_port))
        self.redis_client = redis.Redis(
            host=self.redis_host, 
            port=self.redis_port, 
            db=redis_db, 
            decode_responses=True
        )

    def _get_key(self, provider):
        """Generate a daily key for the provider, e.g., quota:gemini:2026-01-20"""
        today = datetime.now().strftime("%Y-%m-%d")
        return f"quota:{provider}:{today}"

    def get_limit(self, provider):
        """Get the defined limit for a provider."""
        # In a real scenario, this could fetch from a dynamic config or Redis Config
        return self.DEFAULT_LIMITS.get(provider, 1000)

    def check_limit(self, provider):
        """
        Check if the provider has remaining quota for today.
        Returns: True if request is allowed, False if limit exceeded.
        """
        key = self._get_key(provider)
        current_usage = self.redis_client.get(key)
        
        if current_usage is None:
            return True
            
        limit = self.get_limit(provider)
        return int(current_usage) < limit

    def increment_usage(self, provider):
        """
        Increment the usage counter for the provider.
        Sets TTL to expire at midnight + buffer if key is new.
        """
        key = self._get_key(provider)
        pipe = self.redis_client.pipeline()
        pipe.incr(key)
        
        # Set expiry if it's a new key (TTL until end of day)
        if self.redis_client.ttl(key) == -1:
            now = datetime.now()
            tomorrow = datetime.replace(now + timedelta(days=1), hour=0, minute=0, second=0, microsecond=0)
            seconds_until_midnight = int((tomorrow - now).total_seconds())
            pipe.expire(key, seconds_until_midnight + 3600) # +1 hour buffer
            
        pipe.execute()
        
    def get_usage(self, provider):
        """Return current usage for the day."""
        key = self._get_key(provider)
        val = self.redis_client.get(key)
        return int(val) if val else 0
