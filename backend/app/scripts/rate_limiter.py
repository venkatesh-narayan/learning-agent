import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class MultiKeyRateLimiter:
    """Rate limiter that manages multiple API keys with their own limits."""

    def __init__(
        self,
        api_keys: List[str],
        calls_per_second: float,
        calls_per_day: Optional[int] = None,
        calls_per_month: Optional[int] = None,
    ):
        self.api_keys = api_keys
        self.rate = calls_per_second
        self.daily_limit = calls_per_day
        self.monthly_limit = calls_per_month

        # Create separate counters for each API key
        self.last_request = {key: 0.0 for key in api_keys}
        self.daily_requests = {key: 0 for key in api_keys}
        self.monthly_requests = {key: 0 for key in api_keys}

        self.last_reset = {key: datetime.now() for key in api_keys}
        self.monthly_reset = {key: datetime.now() for key in api_keys}

        self.current_key_index = 0
        self.lock = asyncio.Lock()

    def _get_next_key(self) -> str:
        """Get next available API key using round-robin."""
        key = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        return key

    async def acquire(self) -> Optional[str]:
        """Acquire rate limit slot and return the API key to use."""
        async with self.lock:
            # Try each API key until we find one that's available
            keys_tried = 0
            while keys_tried < len(self.api_keys):
                key = self._get_next_key()
                now = datetime.now()

                # Reset counters if needed
                if now.date() > self.last_reset[key].date():
                    self.daily_requests[key] = 0
                    self.last_reset[key] = now

                if now.month != self.monthly_reset[key].month:
                    self.monthly_requests[key] = 0
                    self.monthly_reset[key] = now

                # Check limits
                if self.daily_limit and self.daily_requests[key] >= self.daily_limit:
                    keys_tried += 1
                    continue

                if (
                    self.monthly_limit
                    and self.monthly_requests[key] >= self.monthly_limit
                ):
                    keys_tried += 1
                    continue

                # Calculate wait time for rate limit
                current = datetime.now().timestamp()
                wait_time = max(
                    0, (1 / self.rate) - (current - self.last_request[key])
                )

                if wait_time > 0:
                    await asyncio.sleep(wait_time)

                # Update counters
                self.last_request[key] = datetime.now().timestamp()
                self.daily_requests[key] += 1
                self.monthly_requests[key] += 1

                return key

            # If we get here, no keys are available
            logger.warning("No API keys available within rate limits")
            return None


class MultiAPIRateLimiter:
    """Rate limiter for different APIs with multiple keys per API."""

    def __init__(self, api_configs: Dict[str, Dict[str, List[str]]]):
        """
        Initialize with API configurations.

        api_configs format:
        {
            "api_name": {
                "keys": ["key1", "key2", ...],
                "calls_per_second": float,
                "calls_per_day": Optional[int],
                "calls_per_month": Optional[int]
            }
        }
        """
        self.limiters = {}
        for api_name, config in api_configs.items():
            self.limiters[api_name] = MultiKeyRateLimiter(
                api_keys=config["keys"],
                calls_per_second=config.get("calls_per_second", 1.0),
                calls_per_day=config.get("calls_per_day"),
                calls_per_month=config.get("calls_per_month"),
            )

        # Track usage for monitoring
        self.usage = defaultdict(
            lambda: {
                "daily": defaultdict(int),
                "monthly": defaultdict(int),
                "errors": defaultdict(int),
                "last_error": {},
                "last_success": {},
            }
        )

    async def acquire(self, api_name: str) -> Optional[str]:
        """Acquire rate limit slot for specific API and return API key to use."""
        if api_name not in self.limiters:
            logger.warning(f"No rate limiter defined for {api_name}")
            return None

        try:
            key = await self.limiters[api_name].acquire()
            if key:
                self.usage[api_name]["daily"][key] += 1
                self.usage[api_name]["monthly"][key] += 1
                self.usage[api_name]["last_success"][key] = datetime.now()
            else:
                # Track error for all keys since none were available
                for key in self.limiters[api_name].api_keys:
                    self.usage[api_name]["errors"][key] += 1
                    self.usage[api_name]["last_error"][key] = datetime.now()
            return key

        except Exception as e:
            logger.error(f"Error in rate limiter for {api_name}: {str(e)}")
            return None

    def get_usage_stats(self) -> Dict:
        """Get current usage statistics per API and key."""
        stats = dict(self.usage)
        for api_name, limiter in self.limiters.items():
            if api_name in stats:
                for key in limiter.api_keys:
                    if limiter.daily_limit:
                        stats[api_name][f"daily_percent_{key}"] = (
                            stats[api_name]["daily"][key] / limiter.daily_limit * 100
                        )
                    if limiter.monthly_limit:
                        stats[api_name][f"monthly_percent_{key}"] = (
                            stats[api_name]["monthly"][key]
                            / limiter.monthly_limit
                            * 100
                        )
        return stats

    def reset_usage_stats(self):
        """Reset usage statistics."""
        self.usage.clear()

    def get_remaining_calls(self, api_name: str) -> Dict[str, Dict[str, int]]:
        """Get remaining API calls for different time periods per key."""
        if api_name not in self.limiters:
            return {}

        limiter = self.limiters[api_name]
        usage = self.usage[api_name]

        remaining = {}
        for key in limiter.api_keys:
            remaining[key] = {}
            if limiter.daily_limit:
                remaining[key]["daily"] = max(
                    0, limiter.daily_limit - usage["daily"][key]
                )
            if limiter.monthly_limit:
                remaining[key]["monthly"] = max(
                    0, limiter.monthly_limit - usage["monthly"][key]
                )

        return remaining
