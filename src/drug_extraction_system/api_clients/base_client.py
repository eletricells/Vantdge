"""
Base API Client

Provides common functionality for all API clients including:
- Rate limiting
- Retry logic with exponential backoff
- Circuit breaker pattern
- Error handling
"""

import time
import random
import logging
from typing import Dict, Optional, Any
from abc import ABC, abstractmethod
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.drug_extraction_system.utils.rate_limiter import RateLimiter
from src.drug_extraction_system.utils.circuit_breaker import CircuitBreaker, ServiceUnavailableError

logger = logging.getLogger(__name__)


class BaseAPIClient(ABC):
    """
    Base class for all API clients.
    
    Provides rate limiting, retry logic, and common HTTP functionality.
    """

    def __init__(
        self,
        base_url: str,
        rate_limit: int = 60,
        daily_limit: Optional[int] = None,
        timeout: int = 30,
        max_retries: int = 3,
        name: Optional[str] = None,
        enable_circuit_breaker: bool = True
    ):
        """
        Initialize API client.

        Args:
            base_url: Base URL for API endpoints
            rate_limit: Max requests per minute
            daily_limit: Max requests per day (optional)
            timeout: Request timeout in seconds
            max_retries: Max retry attempts on failure
            name: Client name for logging
            enable_circuit_breaker: Enable circuit breaker pattern
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.name = name or self.__class__.__name__

        # Set up rate limiter
        self.rate_limiter = RateLimiter(
            requests_per_minute=rate_limit,
            requests_per_day=daily_limit,
            name=self.name
        )

        # Set up circuit breaker
        self.circuit_breaker = CircuitBreaker(name=self.name) if enable_circuit_breaker else None

        # Set up session with retry adapter
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create requests session with retry configuration."""
        session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        return session

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Optional[Dict]:
        """
        Make HTTP request with rate limiting, circuit breaker, and retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (appended to base_url)
            params: URL parameters
            data: Form data
            json: JSON body
            headers: Additional headers
            timeout: Override default timeout

        Returns:
            Response JSON or None on failure
        """
        # Check circuit breaker
        if self.circuit_breaker and not self.circuit_breaker.allow_request():
            logger.warning(f"[{self.name}] Circuit breaker is OPEN - skipping request")
            return None

        # Wait for rate limiter
        if not self.rate_limiter.acquire(timeout=120):
            logger.error(f"[{self.name}] Rate limiter timeout - aborting request")
            return None

        url = f"{self.base_url}{endpoint}" if not endpoint.startswith('http') else endpoint

        # Prepare headers
        request_headers = {"Accept": "application/json"}
        if headers:
            request_headers.update(headers)

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                json=json,
                headers=request_headers,
                timeout=timeout or self.timeout
            )

            # Handle rate limit response
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"[{self.name}] Rate limited, waiting {retry_after}s")
                time.sleep(retry_after + random.uniform(0, 5))
                return self._make_request(method, endpoint, params, data, json, headers, timeout)

            response.raise_for_status()

            # Record success with circuit breaker
            if self.circuit_breaker:
                self.circuit_breaker.record_success()

            return response.json() if response.content else {}

        except requests.exceptions.Timeout:
            logger.error(f"[{self.name}] Request timeout: {url}")
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return None
        except requests.exceptions.HTTPError as e:
            logger.error(f"[{self.name}] HTTP error: {e}")
            # Don't count 404 (Not Found) as circuit breaker failure
            # 404 is expected when searching for drugs that don't exist
            if self.circuit_breaker and response.status_code != 404:
                self.circuit_breaker.record_failure()
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"[{self.name}] Request failed: {e}")
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return None
        except Exception as e:
            logger.error(f"[{self.name}] Unexpected error: {e}")
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            return None

    def get(self, endpoint: str, params: Optional[Dict] = None, **kwargs) -> Optional[Dict]:
        """Make GET request."""
        return self._make_request("GET", endpoint, params=params, **kwargs)

    def post(self, endpoint: str, json: Optional[Dict] = None, **kwargs) -> Optional[Dict]:
        """Make POST request."""
        return self._make_request("POST", endpoint, json=json, **kwargs)

    def get_status(self) -> Dict:
        """Get client status including rate limiter and circuit breaker status."""
        status = {
            "client": self.name,
            "base_url": self.base_url,
            "rate_limiter": self.rate_limiter.get_status()
        }

        if self.circuit_breaker:
            status["circuit_breaker"] = {
                "state": self.circuit_breaker.get_state().value,
                "details": str(self.circuit_breaker)
            }

        return status

    @abstractmethod
    def health_check(self) -> bool:
        """Check if API is accessible."""
        pass

