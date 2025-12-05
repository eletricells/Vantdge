"""
Types for Clinical Data Extraction progress reporting and metrics.

Provides progress callbacks and metrics collection for long-running extractions.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Dict, List, Any
from time import perf_counter
from contextlib import contextmanager


@dataclass
class PreparedPaperContent:
    """
    Pre-processed paper content for extraction.

    Avoids repeated truncation of content across multiple stages.
    """
    full: str
    short: str  # 30,000 chars for most stages
    long: str   # 50,000 chars for complex stages
    max: str    # 80,000 chars maximum
    tables: List[Dict[str, Any]]
    metadata: Dict[str, Any]

    @classmethod
    def from_paper(cls, paper: Dict[str, Any]) -> 'PreparedPaperContent':
        """
        Create PreparedPaperContent from raw paper dict.

        Args:
            paper: Paper content dict with 'content', 'tables', etc.

        Returns:
            PreparedPaperContent with pre-computed truncations
        """
        from src.agents.clinical_extraction_constants import (
            CONTENT_TRUNCATION_SHORT,
            CONTENT_TRUNCATION_LONG,
            CONTENT_TRUNCATION_MAX,
        )

        content = paper.get('content', '')

        return cls(
            full=content,
            short=content[:CONTENT_TRUNCATION_SHORT],
            long=content[:CONTENT_TRUNCATION_LONG],
            max=content[:CONTENT_TRUNCATION_MAX],
            tables=paper.get('tables', []),
            metadata={
                'title': paper.get('title', ''),
                'authors': paper.get('authors', []),
                'pmid': paper.get('pmid'),
                'doi': paper.get('doi'),
            }
        )


class ExtractionStage(Enum):
    """Stages in the clinical data extraction pipeline."""
    PREPARATION = "preparation"
    TRIAL_DESIGN = "trial_design"
    TABLE_VALIDATION = "table_validation"
    SECTION_IDENTIFICATION = "section_identification"
    DEMOGRAPHICS = "demographics"
    PRIOR_MEDICATIONS = "prior_medications"
    DISEASE_BASELINE = "disease_baseline"
    EFFICACY = "efficacy"
    FIGURES = "figures"
    SAFETY = "safety"
    VALIDATION = "validation"


@dataclass
class ExtractionProgress:
    """Progress information for extraction pipeline."""
    stage: ExtractionStage
    stage_index: int
    total_stages: int
    arm_index: Optional[int] = None
    total_arms: Optional[int] = None
    message: str = ""
    
    @property
    def overall_progress(self) -> float:
        """Calculate overall progress as percentage (0-100)."""
        base_progress = (self.stage_index / self.total_stages) * 100
        
        if self.arm_index is not None and self.total_arms and self.total_arms > 0:
            arm_contribution = (1 / self.total_stages) * 100
            arm_progress = (self.arm_index / self.total_arms) * arm_contribution
            return base_progress + arm_progress
        
        return base_progress


# Type alias for progress callback function
ProgressCallback = Callable[[ExtractionProgress], None]


@dataclass
class ExtractionMetrics:
    """Metrics collected during extraction."""
    
    # Timing
    total_duration_seconds: float = 0.0
    stage_durations: Dict[str, float] = field(default_factory=dict)
    
    # API usage
    api_calls: int = 0
    api_retries: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    thinking_tokens: int = 0
    cache_creation_tokens: int = 0  # Tokens written to cache (25% more expensive)
    cache_read_tokens: int = 0      # Tokens read from cache (90% discount)
    
    # Extraction results
    arms_extracted: int = 0
    endpoints_extracted: int = 0
    safety_events_extracted: int = 0
    figures_processed: int = 0
    tables_processed: int = 0
    
    # Errors
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    
    @property
    def total_tokens(self) -> int:
        """Total tokens used (input + output + thinking + cache)."""
        return (self.total_input_tokens + self.total_output_tokens +
                self.thinking_tokens + self.cache_creation_tokens +
                self.cache_read_tokens)
    
    @property
    def estimated_cost_usd(self) -> float:
        """
        Estimate cost in USD based on Claude Sonnet 4.5 pricing.

        Pricing (as of 2025):
        - Input: $3 per million tokens
        - Output: $15 per million tokens
        - Thinking: Same as input ($3 per million tokens)
        - Cache Writes (5m): $3.75 per million tokens (25% premium)
        - Cache Reads: $0.30 per million tokens (90% discount)
        """
        # Base input + thinking
        base_input_cost = (self.total_input_tokens + self.thinking_tokens) * 3.0 / 1_000_000

        # Cache writes (25% more expensive than base input)
        cache_write_cost = self.cache_creation_tokens * 3.75 / 1_000_000

        # Cache reads (90% discount from base input)
        cache_read_cost = self.cache_read_tokens * 0.30 / 1_000_000

        # Output tokens
        output_cost = self.total_output_tokens * 15.0 / 1_000_000

        return base_input_cost + cache_write_cost + cache_read_cost + output_cost
    
    def to_dict(self) -> Dict:
        """Convert metrics to dictionary for logging/storage."""
        return {
            'total_duration_seconds': self.total_duration_seconds,
            'stage_durations': self.stage_durations,
            'api_calls': self.api_calls,
            'api_retries': self.api_retries,
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'thinking_tokens': self.thinking_tokens,
            'cache_creation_tokens': self.cache_creation_tokens,
            'cache_read_tokens': self.cache_read_tokens,
            'total_tokens': self.total_tokens,
            'estimated_cost_usd': self.estimated_cost_usd,
            'arms_extracted': self.arms_extracted,
            'endpoints_extracted': self.endpoints_extracted,
            'safety_events_extracted': self.safety_events_extracted,
            'figures_processed': self.figures_processed,
            'tables_processed': self.tables_processed,
            'errors': self.errors,
            'warnings': self.warnings,
        }


class MetricsCollector:
    """Helper class for collecting metrics during extraction."""
    
    def __init__(self, metrics: ExtractionMetrics):
        self.metrics = metrics
        self._stage_start_time: Optional[float] = None
        self._extraction_start_time: Optional[float] = None
    
    @contextmanager
    def track_stage(self, stage_name: str):
        """Context manager to track stage duration."""
        start_time = perf_counter()
        try:
            yield
        finally:
            duration = perf_counter() - start_time
            self.metrics.stage_durations[stage_name] = duration
    
    def record_api_call(self, response, is_retry: bool = False):
        """Record API call metrics from Claude response."""
        self.metrics.api_calls += 1
        if is_retry:
            self.metrics.api_retries += 1

        # Extract token usage from response (including cache tokens)
        if hasattr(response, 'usage'):
            usage = response.usage
            self.metrics.total_input_tokens += getattr(usage, 'input_tokens', 0)
            self.metrics.total_output_tokens += getattr(usage, 'output_tokens', 0)
            self.metrics.cache_creation_tokens += getattr(usage, 'cache_creation_input_tokens', 0)
            self.metrics.cache_read_tokens += getattr(usage, 'cache_read_input_tokens', 0)

