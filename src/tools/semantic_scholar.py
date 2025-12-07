"""
Semantic Scholar API integration for academic paper search and citation mining.

Provides:
- Semantic search with better relevance ranking than PubMed
- Citation graph traversal (find citing papers and references)
- Related paper discovery
- Open access detection

Rate limits (without API key): 100 requests per 5 minutes
Rate limits (with API key): 1 request per second sustained
"""
import httpx
from typing import List, Dict, Optional, Any
import logging
import time
import random

logger = logging.getLogger(__name__)


class SemanticScholarAPI:
    """
    Wrapper for Semantic Scholar Academic Graph API with robust rate limiting.

    Documentation: https://api.semanticscholar.org/api-docs/

    Features:
    - Automatic retry with exponential backoff on rate limits
    - Configurable rate limiting to avoid 429 errors
    - Graceful degradation on errors
    """

    BASE_URL = "https://api.semanticscholar.org/graph/v1"

    # Default fields to retrieve for papers
    DEFAULT_FIELDS = [
        "paperId", "externalIds", "title", "abstract", "year",
        "authors", "venue", "publicationTypes", "openAccessPdf",
        "citationCount", "referenceCount", "fieldsOfStudy"
    ]

    # Extended fields for detailed paper info
    EXTENDED_FIELDS = DEFAULT_FIELDS + ["tldr", "citations", "references"]

    def __init__(self, api_key: Optional[str] = None, timeout: int = 30):
        """
        Initialize Semantic Scholar API client.

        Args:
            api_key: Optional API key for higher rate limits
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.timeout = timeout
        self.session = httpx.Client(timeout=timeout)

        # Thread-safe rate limiting with sliding window
        # Without key: 100 requests per 5 minutes = 1 request per 3 seconds
        # With key: 1 request per second
        import threading
        self._rate_lock = threading.Lock()
        self._request_times: List[float] = []
        self._window_size = 300  # 5 minutes in seconds
        self._max_requests_per_window = 95 if not api_key else 300  # Leave buffer
        self._min_delay = 3.0 if not api_key else 1.0  # Minimum delay between requests

        self.max_retries = 3
        self.base_backoff = 10.0  # Base backoff time in seconds (increased for safety)

        self.headers = {"Accept": "application/json"}
        if api_key:
            self.headers["x-api-key"] = api_key
            logger.info("Semantic Scholar API initialized with API key")
        else:
            logger.info("Semantic Scholar API initialized without API key (strict rate limiting: 100 req/5min)")

    def _rate_limit(self):
        """
        Enforce rate limiting using sliding window algorithm.

        Thread-safe implementation that tracks requests over a 5-minute window
        and ensures we stay under the limit (100 requests per 5 minutes without API key).
        """
        with self._rate_lock:
            current_time = time.time()

            # Remove requests outside the sliding window
            window_start = current_time - self._window_size
            self._request_times = [t for t in self._request_times if t > window_start]

            # Check if we're at capacity
            if len(self._request_times) >= self._max_requests_per_window:
                # Wait until the oldest request falls outside the window
                oldest = self._request_times[0]
                wait_time = oldest + self._window_size - current_time + 1  # +1 for safety
                if wait_time > 0:
                    logger.info(f"Rate limit window full ({len(self._request_times)} requests), waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                    current_time = time.time()
                    # Clean up again after waiting
                    window_start = current_time - self._window_size
                    self._request_times = [t for t in self._request_times if t > window_start]

            # Also enforce minimum delay between consecutive requests
            if self._request_times:
                time_since_last = current_time - self._request_times[-1]
                if time_since_last < self._min_delay:
                    sleep_time = self._min_delay - time_since_last
                    time.sleep(sleep_time)
                    current_time = time.time()

            # Record this request
            self._request_times.append(current_time)

    def _request_with_retry(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        **kwargs
    ) -> Optional[httpx.Response]:
        """
        Make HTTP request with exponential backoff retry on rate limits.

        Args:
            method: HTTP method (get, post, etc.)
            url: Request URL
            params: Query parameters
            **kwargs: Additional arguments for httpx

        Returns:
            Response object or None if all retries failed
        """
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                self._rate_limit()

                response = getattr(self.session, method)(
                    url,
                    params=params,
                    headers=self.headers,
                    **kwargs
                )

                # Success
                if response.status_code == 200:
                    return response

                # Rate limited - retry with backoff
                if response.status_code == 429:
                    if attempt < self.max_retries:
                        # Exponential backoff with jitter
                        backoff = self.base_backoff * (2 ** attempt) + random.uniform(0, 2)
                        logger.warning(
                            f"Rate limited (429), retry {attempt + 1}/{self.max_retries} "
                            f"after {backoff:.1f}s"
                        )
                        time.sleep(backoff)
                        continue
                    else:
                        logger.error(f"Rate limit exceeded after {self.max_retries} retries")
                        return None

                # Other HTTP errors
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429 and attempt < self.max_retries:
                    backoff = self.base_backoff * (2 ** attempt) + random.uniform(0, 2)
                    logger.warning(f"Rate limited, retry {attempt + 1} after {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                logger.error(f"HTTP error: {e}")
                return None

            except httpx.RequestError as e:
                last_error = e
                if attempt < self.max_retries:
                    backoff = self.base_backoff * (2 ** attempt)
                    logger.warning(f"Request error, retry {attempt + 1} after {backoff:.1f}s: {e}")
                    time.sleep(backoff)
                    continue
                logger.error(f"Request failed after retries: {e}")
                return None

        if last_error:
            logger.error(f"All retries exhausted. Last error: {last_error}")
        return None
    
    def search_papers(
        self,
        query: str,
        limit: int = 50,
        fields: Optional[List[str]] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        open_access_only: bool = False,
        publication_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for papers using semantic search with retry on rate limits.

        Unlike PubMed keyword search, this uses neural embeddings
        for better relevance ranking.

        Args:
            query: Search query (semantic, not just keyword matching)
            limit: Maximum results (max 100 per request)
            fields: Fields to return (default: comprehensive set)
            year_min: Minimum publication year
            year_max: Maximum publication year
            open_access_only: Only return open-access papers
            publication_types: Filter by types like "CaseReport", "Review", etc.

        Returns:
            List of paper dictionaries with requested fields
        """
        if fields is None:
            fields = self.DEFAULT_FIELDS

        params = {
            "query": query,
            "limit": min(limit, 100),
            "fields": ",".join(fields)
        }

        # Add year filter
        if year_min and year_max:
            params["year"] = f"{year_min}-{year_max}"
        elif year_min:
            params["year"] = f"{year_min}-"
        elif year_max:
            params["year"] = f"-{year_max}"

        # Add open access filter
        if open_access_only:
            params["openAccessPdf"] = ""

        # Add publication type filter
        if publication_types:
            params["publicationTypes"] = ",".join(publication_types)

        response = self._request_with_retry(
            "get",
            f"{self.BASE_URL}/paper/search",
            params=params
        )

        if response is None:
            return []

        try:
            data = response.json()
            papers = data.get("data", [])

            # Add relevance rank (Semantic Scholar returns in relevance order)
            for i, paper in enumerate(papers):
                paper["relevance_rank"] = i + 1

            logger.info(f"Semantic Scholar: Found {len(papers)} papers for '{query[:50]}...'")
            return papers

        except Exception as e:
            logger.error(f"Error parsing Semantic Scholar response: {e}")
            return []

    def get_paper_details(
        self,
        paper_id: str,
        fields: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific paper with retry.

        Args:
            paper_id: Semantic Scholar paper ID, DOI, PMID, etc.
                     Formats: "DOI:10.xxx", "PMID:12345", or raw S2 ID
            fields: Fields to return

        Returns:
            Paper details or None if not found
        """
        if fields is None:
            fields = self.EXTENDED_FIELDS

        params = {"fields": ",".join(fields)}

        response = self._request_with_retry(
            "get",
            f"{self.BASE_URL}/paper/{paper_id}",
            params=params
        )

        if response is None:
            return None

        try:
            return response.json()
        except Exception as e:
            logger.error(f"Error parsing paper details for {paper_id}: {e}")
            return None

    def get_paper_by_pmid(self, pmid: str) -> Optional[Dict[str, Any]]:
        """Get paper details by PubMed ID."""
        return self.get_paper_details(f"PMID:{pmid}")

    def get_paper_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """Get paper details by DOI."""
        return self.get_paper_details(f"DOI:{doi}")

    def get_citations(
        self,
        paper_id: str,
        limit: int = 100,
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get papers that CITE this paper (forward citations) with retry.

        This is crucial for citation snowballing - find newer papers
        that build on important case studies.

        Args:
            paper_id: Paper identifier (S2 ID, DOI:xxx, PMID:xxx)
            limit: Maximum citations to return (max 1000)
            fields: Fields for citing papers

        Returns:
            List of citing paper dictionaries
        """
        if fields is None:
            fields = self.DEFAULT_FIELDS

        params = {
            "fields": ",".join(fields),
            "limit": min(limit, 1000)
        }

        response = self._request_with_retry(
            "get",
            f"{self.BASE_URL}/paper/{paper_id}/citations",
            params=params
        )

        if response is None:
            return []

        try:
            data = response.json()
            citations = [item.get("citingPaper", {}) for item in data.get("data", [])]
            logger.info(f"Found {len(citations)} papers citing {paper_id}")
            return citations
        except Exception as e:
            logger.error(f"Error parsing citations for {paper_id}: {e}")
            return []

    def get_references(
        self,
        paper_id: str,
        limit: int = 100,
        fields: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get papers that this paper REFERENCES (backward citations) with retry.

        Essential for mining review articles - extracts all studies
        the review cites.

        Args:
            paper_id: Paper identifier
            limit: Maximum references to return (max 1000)
            fields: Fields for referenced papers

        Returns:
            List of referenced paper dictionaries
        """
        if fields is None:
            fields = self.DEFAULT_FIELDS

        params = {
            "fields": ",".join(fields),
            "limit": min(limit, 1000)
        }

        response = self._request_with_retry(
            "get",
            f"{self.BASE_URL}/paper/{paper_id}/references",
            params=params
        )

        if response is None:
            return []

        try:
            data = response.json()
            references = [item.get("citedPaper", {}) for item in data.get("data", [])]
            logger.info(f"Found {len(references)} references in {paper_id}")
            return references
        except Exception as e:
            logger.error(f"Error parsing references for {paper_id}: {e}")
            return []

    def search_with_citation_expansion(
        self,
        query: str,
        limit: int = 30,
        expand_top_n: int = 5,
        citation_limit: int = 20
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search and expand results via citation graph.

        Strategy:
        1. Search for papers matching query
        2. For top N results, get their citations and references
        3. Return combined, deduplicated results

        This finds papers that might not match the query directly
        but are connected to relevant papers.

        Args:
            query: Search query
            limit: Initial search limit
            expand_top_n: Number of top papers to expand citations for
            citation_limit: Max citations/references per paper

        Returns:
            Dict with 'search_results', 'citing_papers', 'referenced_papers'
        """
        results = {
            "search_results": [],
            "citing_papers": [],
            "referenced_papers": [],
            "all_unique": []
        }
        seen_ids = set()

        # Step 1: Initial search
        search_results = self.search_papers(query, limit=limit)
        results["search_results"] = search_results

        for paper in search_results:
            paper_id = paper.get("paperId")
            if paper_id:
                seen_ids.add(paper_id)

        # Step 2: Expand top results
        for paper in search_results[:expand_top_n]:
            paper_id = paper.get("paperId")
            if not paper_id:
                continue

            # Get forward citations
            citations = self.get_citations(paper_id, limit=citation_limit)
            for citing_paper in citations:
                citing_id = citing_paper.get("paperId")
                if citing_id and citing_id not in seen_ids:
                    seen_ids.add(citing_id)
                    citing_paper["_source"] = f"cites:{paper_id}"
                    results["citing_papers"].append(citing_paper)

            # Get backward references
            references = self.get_references(paper_id, limit=citation_limit)
            for ref_paper in references:
                ref_id = ref_paper.get("paperId")
                if ref_id and ref_id not in seen_ids:
                    seen_ids.add(ref_id)
                    ref_paper["_source"] = f"referenced_by:{paper_id}"
                    results["referenced_papers"].append(ref_paper)

        # Combine all unique papers
        results["all_unique"] = (
            results["search_results"] +
            results["citing_papers"] +
            results["referenced_papers"]
        )

        logger.info(
            f"Citation expansion: {len(results['search_results'])} direct + "
            f"{len(results['citing_papers'])} citing + "
            f"{len(results['referenced_papers'])} referenced = "
            f"{len(results['all_unique'])} total unique papers"
        )

        return results

    def mine_review_references(
        self,
        drug_name: str,
        disease_area: Optional[str] = None,
        max_reviews: int = 5,
        max_refs_per_review: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Find review articles and extract their references.

        This is the citation snowballing strategy - reviews aggregate
        all the case studies in a field, so mining their references
        gives comprehensive coverage.

        Args:
            drug_name: Drug to search for
            disease_area: Optional disease focus
            max_reviews: Number of reviews to mine
            max_refs_per_review: Max references to extract per review

        Returns:
            List of referenced papers from reviews
        """
        # Build review search query
        if disease_area:
            query = f"{drug_name} {disease_area} review"
        else:
            query = f"{drug_name} review treatment"

        # Find review articles
        reviews = self.search_papers(
            query,
            limit=max_reviews * 2,  # Get more to filter
            publication_types=["Review"]
        )

        if not reviews:
            # Fallback: search without publication type filter
            reviews = self.search_papers(query, limit=max_reviews)
            # Filter for reviews manually
            reviews = [
                p for p in reviews
                if any(
                    "review" in str(pt).lower()
                    for pt in p.get("publicationTypes", [])
                )
            ]

        logger.info(f"Found {len(reviews)} review articles to mine")

        # Extract references from top reviews
        all_references = []
        seen_ids = set()

        for review in reviews[:max_reviews]:
            paper_id = review.get("paperId")
            if not paper_id:
                continue

            refs = self.get_references(paper_id, limit=max_refs_per_review)

            for ref in refs:
                ref_id = ref.get("paperId")
                if ref_id and ref_id not in seen_ids:
                    seen_ids.add(ref_id)
                    ref["_mined_from_review"] = review.get("title", "Unknown review")
                    ref["_review_paper_id"] = paper_id
                    all_references.append(ref)

        logger.info(f"Mined {len(all_references)} unique references from {len(reviews[:max_reviews])} reviews")
        return all_references

    def format_paper_for_case_series(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format Semantic Scholar paper data to match case series agent format.

        Args:
            paper: Raw paper from Semantic Scholar

        Returns:
            Formatted paper dict compatible with case series agent
        """
        external_ids = paper.get("externalIds") or {}
        authors = paper.get("authors") or []

        # Format author string
        author_names = [a.get("name", "") for a in authors[:5]]
        author_str = ", ".join(author_names)
        if len(authors) > 5:
            author_str += f" et al."

        # Get open access PDF URL if available
        oa_pdf = paper.get("openAccessPdf") or {}
        pdf_url = oa_pdf.get("url")

        return {
            "title": paper.get("title", ""),
            "abstract": paper.get("abstract", ""),
            "authors": author_str,
            "year": paper.get("year"),
            "pmid": external_ids.get("PubMed"),
            "doi": external_ids.get("DOI"),
            "s2_paper_id": paper.get("paperId"),
            "venue": paper.get("venue", ""),
            "citation_count": paper.get("citationCount", 0),
            "publication_types": paper.get("publicationTypes", []),
            "open_access_url": pdf_url,
            "source": "Semantic Scholar",
            "url": f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}" if paper.get('paperId') else None,
            # Metadata from mining
            "_mined_from_review": paper.get("_mined_from_review"),
            "_source": paper.get("_source"),
            "relevance_rank": paper.get("relevance_rank")
        }

    def format_for_llm(self, papers: List[Dict[str, Any]]) -> str:
        """
        Format papers for LLM consumption.

        Args:
            papers: List of papers

        Returns:
            Formatted text for LLM
        """
        if not papers:
            return "No papers found."

        output = []
        for i, paper in enumerate(papers[:20], 1):  # Limit to 20 for context
            title = paper.get("title", "No title")
            abstract = paper.get("abstract", "No abstract")[:500]
            year = paper.get("year", "Unknown")
            authors = paper.get("authors", [])

            if isinstance(authors, list) and authors:
                if isinstance(authors[0], dict):
                    author_str = authors[0].get("name", "Unknown")
                else:
                    author_str = str(authors[0])
            else:
                author_str = "Unknown"

            output.append(f"""
Paper {i}:
Title: {title}
Authors: {author_str} et al.
Year: {year}
Abstract: {abstract}...
---""")

        return "\n".join(output)

