"""
Circuit Breaker Pattern Implementation

Prevents cascading failures when external APIs are down by temporarily
blocking requests after repeated failures.
"""

import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing, reject requests
    HALF_OPEN = "half_open"    # Testing if recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, all requests allowed
    - OPEN: Too many failures, reject all requests
    - HALF_OPEN: Testing recovery, allow limited requests
    
    Usage:
        breaker = CircuitBreaker(name="openfda")
        
        if not breaker.allow_request():
            logger.warning("OpenFDA circuit is open, skipping request")
            return None
        
        try:
            result = call_api()
            breaker.record_success()
            return result
        except Exception as e:
            breaker.record_failure()
            raise
    """
    
    name: str
    failure_threshold: int = 5          # Failures before opening circuit
    recovery_timeout: int = 60          # Seconds before trying again
    success_threshold: int = 2          # Successes needed to close circuit
    
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure_time: Optional[float] = field(default=None, init=False)
    
    def allow_request(self) -> bool:
        """
        Check if request should be allowed.
        
        Returns:
            True if request should proceed, False if circuit is open
        """
        if self._state == CircuitState.CLOSED:
            return True
        
        if self._state == CircuitState.OPEN:
            # Check if recovery timeout has passed
            if self._last_failure_time and time.time() - self._last_failure_time >= self.recovery_timeout:
                logger.info(f"Circuit '{self.name}': OPEN -> HALF_OPEN (attempting recovery)")
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                return True
            return False
        
        # HALF_OPEN: allow limited requests to test recovery
        return True
    
    def record_success(self):
        """Record a successful request."""
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                logger.info(f"Circuit '{self.name}': HALF_OPEN -> CLOSED (recovered)")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            # Reset failure count on success
            self._failure_count = 0
    
    def record_failure(self):
        """Record a failed request."""
        self._failure_count += 1
        self._last_failure_time = time.time()
        
        if self._state == CircuitState.HALF_OPEN:
            logger.warning(f"Circuit '{self.name}': HALF_OPEN -> OPEN (failure during recovery)")
            self._state = CircuitState.OPEN
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                logger.warning(f"Circuit '{self.name}': CLOSED -> OPEN (threshold {self.failure_threshold} reached)")
                self._state = CircuitState.OPEN
    
    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    def reset(self):
        """Manually reset circuit to CLOSED state."""
        logger.info(f"Circuit '{self.name}': Manually reset to CLOSED")
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None
    
    def __repr__(self) -> str:
        return (f"CircuitBreaker(name='{self.name}', state={self._state.value}, "
                f"failures={self._failure_count}, successes={self._success_count})")


class ServiceUnavailableError(Exception):
    """Raised when a service is unavailable due to circuit breaker."""
    pass

