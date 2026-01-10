"""
Factory Functions for Case Series Analysis

Provides factory functions to create fully-wired orchestrators
with all required dependencies.
"""

import os
import logging
from typing import Optional

from src.case_series.orchestrator import CaseSeriesOrchestrator
from src.case_series.services.drug_info_service import DrugInfoService
from src.case_series.services.literature_search_service import LiteratureSearchService
from src.case_series.services.extraction_service import ExtractionService
from src.case_series.services.market_intel_service import MarketIntelService
from src.case_series.services.disease_standardizer import DiseaseStandardizer
from src.case_series.scoring.scoring_engine import ScoringEngine, ScoringWeights
from src.case_series.repositories.case_series_repository import CaseSeriesRepository

logger = logging.getLogger(__name__)


def create_orchestrator(
    anthropic_api_key: Optional[str] = None,
    tavily_api_key: Optional[str] = None,
    database_url: Optional[str] = None,
    semantic_scholar_api_key: Optional[str] = None,
    scoring_weights: Optional[ScoringWeights] = None,
) -> CaseSeriesOrchestrator:
    """
    Create a fully-wired CaseSeriesOrchestrator with all dependencies.

    Args:
        anthropic_api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        tavily_api_key: Tavily API key (defaults to TAVILY_API_KEY env var)
        database_url: PostgreSQL database URL (defaults to DATABASE_URL env var)
        semantic_scholar_api_key: Semantic Scholar API key (defaults to SEMANTIC_SCHOLAR_API_KEY env var)
        scoring_weights: Optional custom scoring weights

    Returns:
        Configured CaseSeriesOrchestrator
    """
    # Get API keys from environment if not provided
    anthropic_api_key = anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
    tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
    database_url = database_url or os.getenv("DATABASE_URL")
    semantic_scholar_api_key = semantic_scholar_api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    ncbi_api_key = os.getenv("NCBI_API_KEY")  # For higher PubMed rate limits

    # Create repository
    repository = None
    if database_url:
        repository = CaseSeriesRepository(database_url)
        logger.info("Created CaseSeriesRepository with database connection")
    else:
        logger.warning("No database URL provided, running without persistence")

    # Create LLM clients
    llm_client = None
    filter_llm_client = None
    if anthropic_api_key:
        # Main client (Sonnet) for extraction - higher quality
        llm_client = _create_anthropic_client(anthropic_api_key, model="claude-sonnet-4-20250514")
        logger.info("Created Anthropic LLM client (Sonnet) for extraction")

        # Filter client (Haiku) for paper filtering - faster, cheaper, higher rate limits
        filter_llm_client = _create_anthropic_client(anthropic_api_key, model="claude-3-5-haiku-20241022")
        logger.info("Created Anthropic LLM client (Haiku) for filtering")
    else:
        raise ValueError("ANTHROPIC_API_KEY is required")

    # Create web searcher
    web_searcher = None
    if tavily_api_key:
        web_searcher = _create_tavily_client(tavily_api_key)
        logger.info("Created Tavily web searcher")
    else:
        logger.warning("No TAVILY_API_KEY provided, web search will be disabled")

    # Create PubMed and Semantic Scholar searchers
    pubmed_searcher = _create_pubmed_client(ncbi_api_key)
    semantic_scholar_searcher = _create_semantic_scholar_client()

    # Create web fetcher
    web_fetcher = _create_web_fetcher()

    # Create disease standardizer
    disease_standardizer = DiseaseStandardizer(
        repository=repository,
        llm_client=llm_client,
    )

    # Create services
    drug_info_service = DrugInfoService(
        repository=repository,
        llm_client=llm_client,
        web_fetcher=web_fetcher,
        database_url=database_url,  # For drug database integration
    )

    literature_search_service = LiteratureSearchService(
        pubmed_searcher=pubmed_searcher,
        semantic_scholar_searcher=semantic_scholar_searcher,
        web_searcher=web_searcher,
        llm_client=llm_client,
        filter_llm_client=filter_llm_client,  # Haiku for fast, cheap filtering
        semantic_scholar_api_key=semantic_scholar_api_key,  # For citation mining
    )

    extraction_service = ExtractionService(
        llm_client=llm_client,
        pubmed_searcher=pubmed_searcher,
        repository=repository,
    )

    market_intel_service = MarketIntelService(
        llm_client=llm_client,
        web_searcher=web_searcher,
        repository=repository,
        disease_standardizer=disease_standardizer,
    )

    # Create scoring engine (use defaults if weights not specified)
    scoring_engine = ScoringEngine(
        repository=repository,
        **({"weights": scoring_weights} if scoring_weights else {}),
    )

    # Create and return orchestrator
    return CaseSeriesOrchestrator(
        drug_info_service=drug_info_service,
        literature_search_service=literature_search_service,
        extraction_service=extraction_service,
        market_intel_service=market_intel_service,
        disease_standardizer=disease_standardizer,
        scoring_engine=scoring_engine,
        repository=repository,
    )


def _create_anthropic_client(api_key: str, model: str = "claude-sonnet-4-20250514"):
    """Create Anthropic LLM client wrapper."""
    from anthropic import Anthropic

    class AnthropicLLMClient:
        """LLM client implementation using Anthropic."""

        def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
            self._client = Anthropic(api_key=api_key)
            self._model = model
            self._usage = {
                'input_tokens': 0,
                'output_tokens': 0,
                'thinking_tokens': 0,
                'cache_creation_tokens': 0,
                'cache_read_tokens': 0,
            }

        async def complete(
            self,
            prompt: str,
            max_tokens: int = 4000,
            temperature: float = 0.0,
            system: Optional[str] = None,
            cache_system: bool = False,
        ) -> str:
            messages = [{"role": "user", "content": prompt}]

            kwargs = {
                "model": self._model,
                "max_tokens": max_tokens,
                "messages": messages,
            }
            if temperature > 0:
                kwargs["temperature"] = temperature

            # Support explicit prompt caching for system prompts
            if system:
                if cache_system and len(system) > 1024:  # Only cache if > 1024 tokens
                    kwargs["system"] = [
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                else:
                    kwargs["system"] = system

            response = self._client.messages.create(**kwargs)
            self._track_usage(response)

            if response.content and len(response.content) > 0:
                return response.content[0].text
            logger.warning("LLM returned empty content")
            return ""

        async def complete_with_thinking(
            self,
            prompt: str,
            thinking_budget: int = 3000,
            max_tokens: int = 8000,
            temperature: float = 1.0,
            system: Optional[str] = None,
            cache_system: bool = False,
        ) -> tuple[str, Optional[str]]:
            kwargs = {
                "model": self._model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": thinking_budget,
                },
                "messages": [{"role": "user", "content": prompt}],
            }

            # Support explicit prompt caching for system prompts
            if system:
                if cache_system and len(system) > 1024:
                    kwargs["system"] = [
                        {
                            "type": "text",
                            "text": system,
                            "cache_control": {"type": "ephemeral"}
                        }
                    ]
                else:
                    kwargs["system"] = system

            response = self._client.messages.create(**kwargs)

            self._track_usage(response)

            # Extract text and thinking
            text = ""
            thinking = None
            if not response.content:
                logger.warning("LLM returned empty content in thinking mode")
                return "", None
            for block in response.content:
                if hasattr(block, 'text'):
                    text = block.text
                elif hasattr(block, 'thinking'):
                    thinking = block.thinking

            return text, thinking

        def count_tokens(self, text: str) -> int:
            # Approximate token count
            return len(text) // 4

        def get_usage_stats(self) -> dict:
            return self._usage.copy()

        def reset_usage_stats(self) -> None:
            self._usage = {k: 0 for k in self._usage}

        def _track_usage(self, response) -> None:
            if hasattr(response, 'usage'):
                usage = response.usage
                self._usage['input_tokens'] += getattr(usage, 'input_tokens', 0)
                self._usage['output_tokens'] += getattr(usage, 'output_tokens', 0)
                # Track cache tokens for prompt caching
                self._usage['cache_creation_tokens'] += getattr(usage, 'cache_creation_input_tokens', 0)
                self._usage['cache_read_tokens'] += getattr(usage, 'cache_read_input_tokens', 0)

    return AnthropicLLMClient(api_key, model=model)


def _create_tavily_client(api_key: str):
    """Create Tavily web search client wrapper."""
    try:
        from tavily import TavilyClient
    except ImportError:
        logger.warning("tavily-python not installed, web search will be disabled")
        return None

    class TavilyWebSearcher:
        """Web search implementation using Tavily."""

        def __init__(self, api_key: str):
            self._client = TavilyClient(api_key=api_key)

        async def search(
            self,
            query: str,
            max_results: int = 10,
            search_depth: str = "basic",
            include_domains: Optional[list] = None,
            exclude_domains: Optional[list] = None,
        ) -> list:
            kwargs = {
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
            }
            if include_domains:
                kwargs["include_domains"] = include_domains
            if exclude_domains:
                kwargs["exclude_domains"] = exclude_domains

            result = self._client.search(**kwargs)
            return result.get("results", [])

        async def search_with_answer(
            self,
            query: str,
            max_results: int = 5,
        ) -> dict:
            result = self._client.search(
                query=query,
                max_results=max_results,
                include_answer=True,
            )
            return {
                "answer": result.get("answer", ""),
                "sources": result.get("results", []),
            }

    return TavilyWebSearcher(api_key)


def _create_pubmed_client(api_key: Optional[str] = None):
    """Create PubMed search client wrapper."""
    try:
        from src.tools.pubmed import PubMedAPI
    except ImportError:
        logger.warning("PubMedAPI not available")
        return None

    class PubMedSearcherWrapper:
        """PubMed search implementation."""

        def __init__(self, api_key: Optional[str] = None):
            self._api = PubMedAPI(api_key=api_key)
            if api_key:
                logger.info("PubMed API key configured (10 req/sec rate limit)")
            else:
                logger.info("No NCBI_API_KEY - using default rate limit (3 req/sec)")

        async def search(
            self,
            query: str,
            max_results: int = 100,
            min_date: Optional[str] = None,
            max_date: Optional[str] = None,
        ) -> list:
            # Use search_papers which returns paper dicts (not just PMIDs)
            return self._api.search_papers(query, max_results=max_results)

        async def fetch_fulltext(self, pmcid: str) -> Optional[str]:
            return self._api.fetch_pmc_fulltext(pmcid)

        async def check_pmc_availability(self, pmid: str) -> Optional[str]:
            # Underlying API expects list and returns dict
            result = self._api.check_pmc_availability([pmid])
            return result.get(pmid) if result else None

        async def check_pmc_availability_batch(self, pmids: list) -> dict:
            # Direct pass-through to underlying API which handles batching
            if not pmids:
                return {}
            return self._api.check_pmc_availability(pmids) or {}

        async def get_paper_details(self, pmid: str) -> Optional[dict]:
            return self._api.get_paper_details(pmid)

    return PubMedSearcherWrapper(api_key=api_key)


def _create_semantic_scholar_client():
    """Create Semantic Scholar search client wrapper."""
    try:
        from src.tools.semantic_scholar import SemanticScholarAPI
    except ImportError:
        logger.warning("SemanticScholarAPI not available")
        return None

    class SemanticScholarWrapper:
        """Semantic Scholar search implementation."""

        def __init__(self):
            self._api = SemanticScholarAPI()

        async def search(
            self,
            query: str,
            limit: int = 100,
            fields: Optional[list] = None,
        ) -> list:
            return self._api.search_papers(query, limit=limit)

        async def get_citations(self, paper_id: str, limit: int = 100) -> list:
            return self._api.get_citations(paper_id, limit=limit)

        async def get_references(self, paper_id: str, limit: int = 100) -> list:
            return self._api.get_references(paper_id, limit=limit)

    return SemanticScholarWrapper()


def _create_web_fetcher():
    """Create simple web fetcher."""
    import aiohttp

    class SimpleWebFetcher:
        """Simple web content fetcher."""

        async def fetch(
            self,
            url: str,
            timeout: int = 30,
        ) -> Optional[str]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            return await response.text()
            except Exception as e:
                logger.warning(f"Failed to fetch {url}: {e}")
            return None

        async def fetch_json(
            self,
            url: str,
            timeout: int = 30,
        ) -> Optional[dict]:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=timeout) as response:
                        if response.status == 200:
                            return await response.json()
            except Exception as e:
                logger.warning(f"Failed to fetch JSON from {url}: {e}")
            return None

        async def fetch_with_cache(
            self,
            url: str,
            cache_hours: int = 24,
        ) -> Optional[str]:
            # Simple implementation without caching
            return await self.fetch(url)

    return SimpleWebFetcher()
