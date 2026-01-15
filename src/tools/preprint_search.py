"""
bioRxiv and medRxiv API integration for preprint paper search.

Provides:
- Search across bioRxiv and medRxiv preprint servers
- Publication status checking (if preprint was later published)
- Results limited to last 2 years by default
- Rate limiting to respect API limits

API Documentation: https://api.biorxiv.org/
"""
import httpx
from typing import List, Dict, Optional, Any
import logging
import time
from datetime import datetime, timedelta
from urllib.parse import quote

logger = logging.getLogger(__name__)


class PreprintSearchAPI:
    """
    Wrapper for bioRxiv/medRxiv API with rate limiting.

    Supports:
    - Content search across both servers
    - Date range queries
    - Publication status checking
    """

    BASE_URL = "https://api.biorxiv.org"

    # Default to last 2 years
    DEFAULT_YEARS_BACK = 2

    def __init__(self, timeout: int = 30):
        """
        Initialize preprint API client.

        Args:
            timeout: Request timeout in seconds
        """
        self.timeout = timeout
        self.session = httpx.Client(timeout=timeout)
        self.last_request_time = 0
        # Conservative rate limit: 60 requests per minute
        self.rate_limit_delay = 1.0  # 1 second between requests
        self.max_retries = 3
        self.base_backoff = 5.0

        logger.info("Preprint Search API initialized (bioRxiv/medRxiv)")

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        self.last_request_time = time.time()

    def _request_with_retry(
        self,
        url: str,
        params: Optional[Dict] = None
    ) -> Optional[Dict]:
        """
        Make HTTP request with retry on failure.

        Args:
            url: Request URL
            params: Query parameters

        Returns:
            JSON response or None if failed
        """
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()

                response = self.session.get(url, params=params)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 429:
                    # Rate limited
                    backoff = self.base_backoff * (2 ** attempt)
                    logger.warning(f"Rate limited, retry {attempt + 1} after {backoff:.1f}s")
                    time.sleep(backoff)
                    continue

                response.raise_for_status()

            except httpx.HTTPError as e:
                if attempt < self.max_retries - 1:
                    backoff = self.base_backoff * (2 ** attempt)
                    logger.warning(f"Request error, retry {attempt + 1}: {e}")
                    time.sleep(backoff)
                    continue
                logger.error(f"Request failed after retries: {e}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                return None

        return None

    def _get_date_range(self, years_back: int = None) -> tuple[str, str]:
        """
        Get date range for queries.

        Args:
            years_back: Number of years back from today (default: 2)

        Returns:
            Tuple of (start_date, end_date) in YYYY-MM-DD format
        """
        if years_back is None:
            years_back = self.DEFAULT_YEARS_BACK

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * years_back)

        return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")

    def search(
        self,
        query: str,
        server: str = "both",
        max_results: int = 100,
        years_back: int = None
    ) -> List[Dict[str, Any]]:
        """
        Search for preprints on bioRxiv and/or medRxiv.

        Args:
            query: Search query (drug name, disease, etc.)
            server: "biorxiv", "medrxiv", or "both"
            max_results: Maximum results to return
            years_back: Number of years back to search (default: 2)

        Returns:
            List of preprint paper dictionaries
        """
        all_papers = []

        if server in ["biorxiv", "both"]:
            papers = self._search_server("biorxiv", query, max_results, years_back)
            all_papers.extend(papers)

        if server in ["medrxiv", "both"]:
            papers = self._search_server("medrxiv", query, max_results, years_back)
            all_papers.extend(papers)

        # Deduplicate by DOI
        seen_dois = set()
        unique_papers = []
        for paper in all_papers:
            doi = paper.get("doi")
            if doi and doi not in seen_dois:
                seen_dois.add(doi)
                unique_papers.append(paper)
            elif not doi:
                unique_papers.append(paper)

        logger.info(f"Preprint search: Found {len(unique_papers)} unique papers for '{query}'")
        return unique_papers[:max_results]

    def _search_server(
        self,
        server: str,
        query: str,
        max_results: int,
        years_back: int = None
    ) -> List[Dict[str, Any]]:
        """
        Search a single preprint server.

        Args:
            server: "biorxiv" or "medrxiv"
            query: Search query
            max_results: Maximum results
            years_back: Years back to search

        Returns:
            List of papers from this server
        """
        start_date, end_date = self._get_date_range(years_back)

        # Use the content search endpoint
        # Format: /pubs/{server}/{term}
        encoded_query = quote(query)
        url = f"{self.BASE_URL}/pubs/{server}/{encoded_query}"

        response = self._request_with_retry(url)

        if not response:
            logger.warning(f"No response from {server} for query: {query}")
            return []

        # Check response status
        messages = response.get("messages", [])
        if messages and messages[0].get("status") != "ok":
            logger.warning(f"{server} search returned error: {messages}")
            return []

        collection = response.get("collection", [])

        # Filter by date and normalize
        papers = []
        for item in collection:
            paper_date = item.get("date", "")

            # Filter by date range (last N years)
            if paper_date and paper_date >= start_date:
                normalized = self._normalize_paper(item, server)
                papers.append(normalized)

        logger.info(f"{server}: Found {len(papers)} papers within date range")
        return papers[:max_results]

    def search_by_date_range(
        self,
        server: str,
        start_date: str,
        end_date: str,
        cursor: int = 0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search preprints by date range using the details endpoint.

        Args:
            server: "biorxiv" or "medrxiv"
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            cursor: Pagination cursor
            limit: Results per page

        Returns:
            List of papers in date range
        """
        # Format: /details/{server}/{interval}/{cursor}
        interval = f"{start_date}/{end_date}"
        url = f"{self.BASE_URL}/details/{server}/{interval}/{cursor}"

        response = self._request_with_retry(url)

        if not response:
            return []

        collection = response.get("collection", [])

        papers = []
        for item in collection:
            normalized = self._normalize_paper(item, server)
            papers.append(normalized)

        return papers[:limit]

    def _normalize_paper(self, item: Dict[str, Any], server: str) -> Dict[str, Any]:
        """
        Normalize preprint data to standard paper format.

        Args:
            item: Raw API response item
            server: Source server name

        Returns:
            Normalized paper dictionary
        """
        # Parse authors (semicolon-separated)
        authors_raw = item.get("authors", "")
        if isinstance(authors_raw, str):
            authors = [a.strip() for a in authors_raw.split(";") if a.strip()]
        else:
            authors = []

        # Format author string
        if len(authors) > 3:
            author_str = ", ".join(authors[:3]) + " et al."
        else:
            author_str = ", ".join(authors)

        # Extract year from date
        date_str = item.get("date", "")
        year = None
        if date_str and len(date_str) >= 4:
            try:
                year = int(date_str[:4])
            except ValueError:
                pass

        # Check if published (has a published DOI)
        published_doi = item.get("published")
        is_published = published_doi and published_doi != "NA"

        # Build preprint DOI URL
        preprint_doi = item.get("doi", "")
        if preprint_doi:
            url = f"https://doi.org/{preprint_doi}"
        else:
            url = None

        return {
            "title": item.get("title", ""),
            "abstract": item.get("abstract", ""),
            "authors": author_str,
            "authors_list": authors,
            "year": year,
            "date": date_str,
            "doi": preprint_doi,
            "published_doi": published_doi if is_published else None,
            "url": url,
            "source": server.capitalize(),  # "Biorxiv" or "Medrxiv"
            "preprint_server": server,
            "category": item.get("category", ""),
            "is_preprint": True,
            "is_published": is_published,
            # Metadata
            "jatsxml": item.get("jatsxml"),  # Link to full XML if available
            "version": item.get("version"),
            "type": item.get("type", "preprint"),
        }

    def check_publication_status(self, preprint_doi: str) -> Optional[str]:
        """
        Check if a preprint has been published.

        Uses the bioRxiv API to check if a preprint DOI has a corresponding
        published version.

        Args:
            preprint_doi: The preprint DOI (e.g., "10.1101/2024.01.01.123456")

        Returns:
            Published DOI if available, None otherwise
        """
        # Extract the bioRxiv/medRxiv ID from DOI
        # Format: 10.1101/YYYY.MM.DD.NNNNNN
        if not preprint_doi or "10.1101" not in preprint_doi:
            return None

        # Use the pub endpoint to check publication status
        url = f"{self.BASE_URL}/pub/{preprint_doi}"

        response = self._request_with_retry(url)

        if not response:
            return None

        collection = response.get("collection", [])
        if collection:
            # Return the published DOI if available
            for item in collection:
                published = item.get("published")
                if published and published != "NA":
                    return published

        return None

    def format_paper_for_case_series(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format preprint data to match case series Paper format.

        Args:
            paper: Normalized preprint paper

        Returns:
            Paper dict compatible with case series service
        """
        return {
            "pmid": None,  # Preprints don't have PMIDs
            "pmcid": None,
            "doi": paper.get("doi"),
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", ""),
            "authors": paper.get("authors", ""),
            "journal": f"{paper.get('source', 'Preprint')} (preprint)",
            "year": paper.get("year"),
            "url": paper.get("url"),
            "source": paper.get("source", "Preprint"),
            "has_full_text": bool(paper.get("jatsxml")),  # JATS XML = full text available
            "relevance_score": 0.0,
            "relevance_reason": None,
            "extracted_disease": None,
            # Preprint-specific fields
            "is_preprint": True,
            "published_doi": paper.get("published_doi"),
            "preprint_server": paper.get("preprint_server"),
        }

    def format_for_llm(self, papers: List[Dict[str, Any]]) -> str:
        """
        Format papers for LLM consumption.

        Args:
            papers: List of preprint papers

        Returns:
            Formatted text for LLM
        """
        if not papers:
            return "No preprint papers found."

        output = []
        for i, paper in enumerate(papers[:20], 1):
            title = paper.get("title", "No title")
            abstract = paper.get("abstract", "No abstract")[:500]
            year = paper.get("year", "Unknown")
            authors = paper.get("authors", "Unknown")
            server = paper.get("source", "Preprint")
            is_published = paper.get("is_published", False)

            status = "(PUBLISHED)" if is_published else "(PREPRINT)"

            output.append(f"""
Preprint {i} {status}:
Title: {title}
Authors: {authors}
Year: {year}
Server: {server}
Abstract: {abstract}...
---""")

        return "\n".join(output)

    def close(self):
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_tool_definition() -> dict:
    """
    Get tool definition for Claude tool use.

    Returns:
        Tool definition dictionary
    """
    return {
        "name": "search_preprints",
        "description": "Search bioRxiv and medRxiv preprint servers for unpublished research papers. Returns preprints from the last 2 years. Note: Preprints are not peer-reviewed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (drug name, disease, mechanism, etc.)"
                },
                "server": {
                    "type": "string",
                    "enum": ["biorxiv", "medrxiv", "both"],
                    "description": "Which preprint server to search (default: both)",
                    "default": "both"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of preprints to return (default: 50)",
                    "default": 50
                }
            },
            "required": ["query"]
        }
    }
