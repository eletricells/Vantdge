"""
Web search tool using Tavily API for real-time information gathering.
"""
import httpx
from typing import List, Dict, Optional, Any
import logging


logger = logging.getLogger(__name__)


class WebSearchTool:
    """
    Web search using Tavily API.

    Tavily is optimized for LLM applications and provides clean, relevant results.
    """

    def __init__(self, api_key: str, timeout: int = 30):
        """
        Initialize web search tool.

        Args:
            api_key: Tavily API key
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.tavily.com"

    def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "advanced",
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform web search.

        Args:
            query: Search query
            max_results: Maximum number of results
            search_depth: "basic" or "advanced" (advanced is more thorough)
            include_domains: Optional list of domains to include
            exclude_domains: Optional list of domains to exclude

        Returns:
            List of search results
        """
        try:
            payload = {
                "api_key": self.api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
                "include_answer": False,
                "include_raw_content": False
            }

            if include_domains:
                payload["include_domains"] = include_domains
            if exclude_domains:
                payload["exclude_domains"] = exclude_domains

            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/search",
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                logger.info(f"Found {len(results)} results for: {query}")
                return results

        except httpx.HTTPError as e:
            logger.error(f"Web search error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in web search: {str(e)}")
            return []

    def format_for_llm(self, results: List[Dict[str, Any]]) -> str:
        """
        Format search results for LLM consumption.

        Args:
            results: Search results from Tavily

        Returns:
            Formatted text
        """
        if not results:
            return "No search results found."

        output = []
        for i, result in enumerate(results, 1):
            output.append(f"""
Result {i}:
Title: {result.get('title', 'N/A')}
URL: {result.get('url', 'N/A')}
Content: {result.get('content', 'N/A')}
Score: {result.get('score', 'N/A')}
---""")

        return "\n".join(output)


class BraveSearchTool:
    """
    Alternative web search using Brave Search API.
    """

    def __init__(self, api_key: str, timeout: int = 30):
        """
        Initialize Brave search tool.

        Args:
            api_key: Brave Search API key
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = "https://api.search.brave.com/res/v1"

    def search(
        self,
        query: str,
        max_results: int = 5,
        country: str = "US"
    ) -> List[Dict[str, Any]]:
        """
        Perform web search using Brave.

        Args:
            query: Search query
            max_results: Maximum number of results
            country: Country code for search

        Returns:
            List of search results
        """
        try:
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key
            }

            params = {
                "q": query,
                "count": max_results,
                "country": country
            }

            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(
                    f"{self.base_url}/web/search",
                    headers=headers,
                    params=params
                )
                response.raise_for_status()
                data = response.json()

                results = data.get("web", {}).get("results", [])
                logger.info(f"Found {len(results)} results for: {query}")
                return results

        except httpx.HTTPError as e:
            logger.error(f"Brave search error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error in Brave search: {str(e)}")
            return []

    def format_for_llm(self, results: List[Dict[str, Any]]) -> str:
        """
        Format Brave search results for LLM.

        Args:
            results: Search results from Brave

        Returns:
            Formatted text
        """
        if not results:
            return "No search results found."

        output = []
        for i, result in enumerate(results, 1):
            output.append(f"""
Result {i}:
Title: {result.get('title', 'N/A')}
URL: {result.get('url', 'N/A')}
Description: {result.get('description', 'N/A')}
---""")

        return "\n".join(output)


def create_web_searcher() -> Optional[WebSearchTool]:
    """
    Factory function to create a WebSearchTool with API key from environment.

    Returns:
        WebSearchTool instance or None if API key not configured
    """
    import os
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        logger.warning("TAVILY_API_KEY not set - web search disabled")
        return None
    return WebSearchTool(api_key=api_key)


def get_tool_definition() -> dict:
    """
    Get tool definition for Claude tool use.

    Returns:
        Tool definition dictionary
    """
    return {
        "name": "web_search",
        "description": "Search the web for recent information about drugs, clinical trials, companies, FDA approvals, conference presentations, or biopharma news. Returns relevant and up-to-date results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query about drugs, trials, companies, or biopharma news"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
