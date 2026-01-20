
import time
import logging
from redis import Redis

class RateLimiter:
    """
    Distributed Token Bucket Rate Limiter using Redis.
    Reference: Neural-Home Infrastructure Blueprint v3.0 - Sec 4.3
    """
    def __init__(self, redis_client: Redis):
        self.redis = redis_client
        # Default Limits: (tokens, replenish_rate_per_minute)
        self.default_limits = {
            "global": (1000, 60),       # 1000 burst, 1/sec
            "expensive": (50, 5),       # 50 burst, 1/12sec (e.g. GPT-4)
            "cheap": (2000, 120)        # 2000 burst, 2/sec (e.g. Ollama)
        }

    def check_limit(self, key: str, cost: int = 1, limit_type: str = "global") -> bool:
        """
        Consumes tokens from the bucket. Returns True if allowed, False if limited.
        """
        max_tokens, rate_per_min = self.default_limits.get(limit_type, self.default_limits["global"])
        rate_per_sec = rate_per_min / 60.0
        
        bucket_key = f"limiter:{key}:{limit_type}"
        last_check_key = f"limiter:{key}:{limit_type}:ts"
        
        # Redis Lua Script for Atomicity
        # ARGV[1]: max_tokens
        # ARGV[2]: rate_per_sec
        # ARGV[3]: current_timestamp
        # ARGV[4]: cost
        lua_script = """
        local bucket_key = KEYS[1]
        local ts_key = KEYS[2]
        local max_tokens = tonumber(ARGV[1])
        local rate = tonumber(ARGV[2])
        local now = tonumber(ARGV[3])
        local cost = tonumber(ARGV[4])

        local current_tokens = tonumber(redis.call('get', bucket_key) or max_tokens)
        local last_ts = tonumber(redis.call('get', ts_key) or now)

        -- Replenish tokens
        local delta = math.max(0, now - last_ts)
        local new_tokens = math.min(max_tokens, current_tokens + (delta * rate))

        if new_tokens >= cost then
            -- Consume
            redis.call('set', bucket_key, new_tokens - cost)
            redis.call('set', ts_key, now)
            -- Set expiry to avoid stale keys (e.g. 1 hour)
            redis.call('expire', bucket_key, 3600)
            redis.call('expire', ts_key, 3600)
            return 1 -- Allowed
        else
            return 0 -- Rejected
        end
        """
        
        try:
            result = self.redis.eval(lua_script, 2, bucket_key, last_check_key, 
                                   max_tokens, rate_per_sec, time.time(), cost)
            return bool(result)
        except Exception as e:
            logging.error(f"Rate Limiter Error: {e}")
            # Fail open (allow request) if Redis fails
            return True
