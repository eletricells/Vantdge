"""
Web Fetching Protocol

Defines the interface for web content fetching operations.
"""

from typing import Protocol, Optional, Dict, Any


class WebFetcher(Protocol):
    """Protocol for web content fetching implementations."""

    async def fetch(
        self,
        url: str,
        timeout: int = 30,
    ) -> Optional[str]:
        """
        Fetch content from a URL.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds

        Returns:
            Page content as text, or None if failed
        """
        ...

    async def fetch_json(
        self,
        url: str,
        timeout: int = 30,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch JSON content from a URL.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds

        Returns:
            Parsed JSON as dict, or None if failed
        """
        ...

    async def fetch_with_cache(
        self,
        url: str,
        cache_hours: int = 24,
    ) -> Optional[str]:
        """
        Fetch content with caching.

        Args:
            url: URL to fetch
            cache_hours: How long to cache the result

        Returns:
            Page content as text, or None if failed
        """
        ...
