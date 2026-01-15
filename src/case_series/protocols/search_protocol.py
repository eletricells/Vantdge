"""
Search Protocol Definitions

Defines interfaces for literature search implementations.
"""

from typing import Protocol, Optional, List, Dict, Any


class PubMedSearcher(Protocol):
    """Protocol for PubMed search implementations."""

    async def search(
        self,
        query: str,
        max_results: int = 100,
        min_date: Optional[str] = None,
        max_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search PubMed for papers matching the query.

        Args:
            query: PubMed search query
            max_results: Maximum number of results to return
            min_date: Minimum publication date (YYYY/MM/DD)
            max_date: Maximum publication date (YYYY/MM/DD)

        Returns:
            List of paper metadata dicts with keys:
            - pmid: PubMed ID
            - title: Paper title
            - abstract: Paper abstract
            - authors: Author list
            - journal: Journal name
            - year: Publication year
            - doi: DOI if available
        """
        ...

    async def fetch_fulltext(self, pmcid: str) -> Optional[str]:
        """
        Fetch full text from PubMed Central.

        Args:
            pmcid: PubMed Central ID (e.g., "PMC1234567")

        Returns:
            Full text content if available, None otherwise
        """
        ...

    async def check_pmc_availability(self, pmid: str) -> Optional[str]:
        """
        Check if a PMID has full text available in PMC.

        Args:
            pmid: PubMed ID

        Returns:
            PMCID if available, None otherwise
        """
        ...

    async def check_pmc_availability_batch(self, pmids: List[str]) -> Dict[str, Optional[str]]:
        """
        Check PMC availability for multiple PMIDs in a single API call.

        More efficient than calling check_pmc_availability for each PMID.

        Args:
            pmids: List of PubMed IDs

        Returns:
            Dict mapping PMID -> PMCID (None if not available in PMC)
        """
        ...

    async def get_paper_details(self, pmid: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed metadata for a specific paper.

        Args:
            pmid: PubMed ID

        Returns:
            Paper metadata dict, or None if not found
        """
        ...


class SemanticScholarSearcher(Protocol):
    """Protocol for Semantic Scholar search implementations."""

    async def search(
        self,
        query: str,
        limit: int = 100,
        fields: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search Semantic Scholar for papers.

        Args:
            query: Search query
            limit: Maximum results
            fields: Fields to return (default: title, abstract, authors, year, citationCount)

        Returns:
            List of paper metadata dicts
        """
        ...

    async def get_citations(
        self,
        paper_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get papers that cite the given paper.

        Args:
            paper_id: Semantic Scholar paper ID or DOI
            limit: Maximum citations to return

        Returns:
            List of citing paper metadata
        """
        ...

    async def get_references(
        self,
        paper_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get papers referenced by the given paper.

        Args:
            paper_id: Semantic Scholar paper ID or DOI
            limit: Maximum references to return

        Returns:
            List of referenced paper metadata
        """
        ...


class WebSearcher(Protocol):
    """Protocol for web search implementations (e.g., Tavily)."""

    async def search(
        self,
        query: str,
        max_results: int = 10,
        search_depth: str = "basic",
        include_domains: Optional[List[str]] = None,
        exclude_domains: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search the web for relevant content.

        Args:
            query: Search query
            max_results: Maximum results to return
            search_depth: "basic" or "advanced"
            include_domains: Only include results from these domains
            exclude_domains: Exclude results from these domains

        Returns:
            List of search result dicts with keys:
            - url: Result URL
            - title: Page title
            - content: Page content/snippet
            - score: Relevance score
        """
        ...

    async def search_with_answer(
        self,
        query: str,
        max_results: int = 5,
    ) -> Dict[str, Any]:
        """
        Search and get an AI-generated answer.

        Args:
            query: Search query
            max_results: Maximum results to use for answer

        Returns:
            Dict with 'answer' and 'sources' keys
        """
        ...


class PreprintSearcher(Protocol):
    """Protocol for preprint search implementations (bioRxiv/medRxiv)."""

    def search(
        self,
        query: str,
        server: str = "both",
        max_results: int = 100,
        years_back: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Search preprint servers for papers.

        Args:
            query: Search query (drug name, disease, etc.)
            server: "biorxiv", "medrxiv", or "both"
            max_results: Maximum results to return
            years_back: Number of years back to search (default: 2)

        Returns:
            List of preprint metadata dicts with keys:
            - doi: Preprint DOI
            - title: Paper title
            - abstract: Paper abstract
            - authors: Author string
            - year: Publication year
            - date: Publication date
            - source: Server name (bioRxiv or medRxiv)
            - is_preprint: Always True
            - published_doi: DOI of published version if available
            - preprint_server: Server name lowercase
        """
        ...

    def check_publication_status(self, preprint_doi: str) -> Optional[str]:
        """
        Check if a preprint has been published.

        Args:
            preprint_doi: The preprint DOI

        Returns:
            Published DOI if available, None otherwise
        """
        ...
