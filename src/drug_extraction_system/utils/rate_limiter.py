"""
Rate Limiter

Implements sliding window rate limiting for API calls.
"""

import time
import threading
from collections import deque
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Sliding window rate limiter for API calls.

    Thread-safe implementation using deque and locks.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_day: Optional[int] = None,
        name: str = "default"
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Max requests per minute (default: 60)
            requests_per_day: Max requests per day (optional)
            name: Name for logging purposes
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_day = requests_per_day
        self.name = name

        # Sliding window for minute-level tracking
        self.minute_window: deque = deque()
        self.minute_lock = threading.Lock()

        # Daily counter (resets at midnight)
        self.daily_count = 0
        self.daily_reset_time = self._get_next_midnight()
        self.daily_lock = threading.Lock()

    def _get_next_midnight(self) -> float:
        """Get timestamp for next midnight."""
        now = time.time()
        # Calculate seconds until midnight
        seconds_in_day = 86400
        midnight = (now // seconds_in_day + 1) * seconds_in_day
        return midnight

    def acquire(self, timeout: float = 60.0) -> bool:
        """
        Acquire permission to make an API call.

        Blocks until rate limit allows, or timeout expires.

        Args:
            timeout: Max seconds to wait (default: 60)

        Returns:
            True if acquired, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self._try_acquire():
                return True

            # Calculate wait time based on oldest request
            wait_time = self._calculate_wait_time()
            if wait_time > 0:
                time.sleep(min(wait_time, 0.5))  # Check every 0.5s max

        logger.warning(f"[{self.name}] Rate limiter timeout after {timeout}s")
        return False

    def _try_acquire(self) -> bool:
        """Try to acquire a slot (non-blocking)."""
        now = time.time()

        # Check daily limit first
        if self.requests_per_day:
            with self.daily_lock:
                # Reset daily counter if past midnight
                if now >= self.daily_reset_time:
                    self.daily_count = 0
                    self.daily_reset_time = self._get_next_midnight()
                    logger.info(f"[{self.name}] Daily counter reset")

                if self.daily_count >= self.requests_per_day:
                    logger.warning(f"[{self.name}] Daily rate limit reached: {self.daily_count}/{self.requests_per_day}")
                    return False

        # Check minute-level limit
        with self.minute_lock:
            # Remove requests older than 60 seconds
            window_start = now - 60.0
            while self.minute_window and self.minute_window[0] < window_start:
                self.minute_window.popleft()

            # Check if under limit
            if len(self.minute_window) >= self.requests_per_minute:
                return False

            # Record this request
            self.minute_window.append(now)

        # Increment daily counter
        if self.requests_per_day:
            with self.daily_lock:
                self.daily_count += 1

        return True

    def _calculate_wait_time(self) -> float:
        """Calculate how long to wait for next available slot."""
        with self.minute_lock:
            if not self.minute_window:
                return 0.0

            # Time until oldest request expires from window
            oldest = self.minute_window[0]
            wait = (oldest + 60.0) - time.time()
            return max(0.0, wait)

    def get_status(self) -> Dict:
        """Get current rate limiter status."""
        with self.minute_lock:
            minute_used = len(self.minute_window)

        with self.daily_lock:
            daily_used = self.daily_count

        return {
            "name": self.name,
            "minute_used": minute_used,
            "minute_limit": self.requests_per_minute,
            "daily_used": daily_used,
            "daily_limit": self.requests_per_day,
        }

