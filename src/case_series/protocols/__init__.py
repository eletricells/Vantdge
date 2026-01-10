"""
Protocol definitions for dependency injection.

These protocols define the interfaces that services depend on,
allowing for easy mocking in tests and swapping implementations.
"""

from src.case_series.protocols.llm_protocol import LLMClient
from src.case_series.protocols.search_protocol import (
    PubMedSearcher,
    SemanticScholarSearcher,
    WebSearcher,
)
from src.case_series.protocols.database_protocol import CaseSeriesRepositoryProtocol
from src.case_series.protocols.web_protocol import WebFetcher

__all__ = [
    "LLMClient",
    "PubMedSearcher",
    "SemanticScholarSearcher",
    "WebSearcher",
    "CaseSeriesRepositoryProtocol",
    "WebFetcher",
]
