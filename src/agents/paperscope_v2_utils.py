"""
Utility classes for PaperScope 2.0

This module contains helper classes for configuration, JSON parsing, prompt building,
API client management, and other utilities to improve robustness and maintainability.
"""

import json
import re
import logging
import time
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Type, TypeVar, Callable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class PaperScopeConfig:
    """Centralized configuration for PaperScope 2.0"""
    
    # API Configuration
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens_default: int = 2000
    max_tokens_categorize: int = 2000
    max_tokens_summary: int = 6000
    api_timeout: float = 120.0
    api_retry_max_attempts: int = 3
    api_retry_delay: float = 1.0
    
    # Batch Processing
    batch_size: int = 10  # Papers per batch for Claude categorization
    pubmed_batch_size: int = 50  # PMIDs per PubMed fetch

    # Parallel Processing
    enable_parallel: bool = False  # Enable parallel batch processing (experimental)
    max_workers: int = 3  # Max parallel workers for batch operations
    
    # Search Configuration
    max_results_per_search: int = 100
    trial_family_search_limit: int = 30
    extension_search_limit: int = 20
    web_search_max_results: int = 10
    
    # Filtering Thresholds
    relevance_threshold: float = 0.6  # Drug relevance filter
    trial_name_min_confidence: float = 0.5  # Min confidence for trial name extraction
    trial_name_confidence_threshold: float = 0.6
    indication_fuzzy_match_threshold: int = 85
    
    # Rate Limiting
    rate_limit_delay: float = 0.5
    api_retry_attempts: int = 3
    api_retry_delay: float = 2.0
    
    # Text Processing
    max_abstract_length_prompt: int = 2000
    max_abstract_length_sample: int = 500
    sample_size_for_trial_extraction: int = 50
    
    # Caching
    enable_cache: bool = True
    cache_ttl_hours: int = 24
    
    # Output
    output_dir: str = "data/paperscope_v2"
    save_excel: bool = True
    save_summary: bool = True
    
    # Paper Categories (18+ categories)
    categories: List[str] = field(default_factory=lambda: [
        'Preclinical/Mechanistic',
        'Phase 1',
        'Phase 1/2',
        'Phase 2',
        'Phase 2 - Extensions',
        'Phase 2/3',
        'Phase 3 - Primary Trials',
        'Phase 3 - Long-term Extensions',
        'Phase 3 - Pooled/Post-hoc Analyses',
        'Phase 4',
        'Biomarker Studies',
        'Subgroup Analyses - Demographics',
        'Subgroup Analyses - Disease Characteristics',
        'Subgroup Analyses - Concomitant Medications',
        'Special Populations',
        'Pharmacokinetics/Pharmacodynamics',
        'Drug Interactions',
        'Post-marketing/Real-world',
        'Safety/Pharmacovigilance',
        'Systematic Reviews/Meta-analyses',
        'Economic/Cost-effectiveness',
        'Ongoing Studies',
        'Other'
    ])
    
    # Trial Name Patterns
    trial_patterns: List[str] = field(default_factory=lambda: [
        r'\b([A-Z]{3,}-\d+[A-Z]?)\b',           # TULIP-1, EXTEND-2A
        r'\b([A-Z]{3,}\d+[A-Z]?)\b',            # MUSE2, REACH3
        r'\b([A-Z]{4,})\s+(?:trial|study)\b',   # BLOSSOM trial
    ])


@dataclass
class ParseResult:
    """Result of a JSON parse attempt"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    strategy_used: Optional[str] = None


class JSONParseError(Exception):
    """Raised when all JSON parsing strategies fail"""
    pass


class ClaudeResponseParser:
    """
    Robust JSON parser for Claude API responses.
    
    Implements multiple fallback strategies to handle common JSON issues:
    - Markdown code blocks
    - Trailing commas
    - Newlines in strings
    - Control characters
    - Malformed escaping
    """
    
    def __init__(self, save_failures: bool = True):
        self.save_failures = save_failures
        self.parse_attempts = 0
        self.successful_parses = 0
    
    def parse_json_response(
        self,
        text: str,
        expected_type: Type[T] = list,
        max_retries: int = 4
    ) -> T:
        """
        Parse JSON from Claude response with multiple fallback strategies.
        
        Args:
            text: Raw response text from Claude
            expected_type: Expected Python type (list or dict)
            max_retries: Number of parsing strategies to attempt
            
        Returns:
            Parsed data of expected_type
            
        Raises:
            JSONParseError: If all parsing strategies fail
        """
        self.parse_attempts += 1

        strategies = [
            ("Direct parse", self._direct_parse),
            ("Extract from markdown", self._parse_from_markdown),
            ("Clean and parse", self._clean_and_parse),
            ("Repair JSON", self._repair_json),
        ]

        for strategy_name, strategy_func in strategies[:max_retries]:
            result = strategy_func(text)

            if result.success:
                if isinstance(result.data, expected_type):
                    self.successful_parses += 1
                    logger.info(f"✅ Parsed JSON using: {strategy_name}")
                    return result.data
                else:
                    logger.warning(
                        f"⚠️ {strategy_name} succeeded but returned "
                        f"{type(result.data).__name__} instead of {expected_type.__name__}"
                    )
            else:
                logger.debug(f"❌ {strategy_name} failed: {result.error}")

        # All strategies failed - save for debugging if enabled
        if self.save_failures:
            self._save_failed_parse(text)

        raise JSONParseError(
            f"Failed to parse JSON after {max_retries} strategies. "
            f"Expected {expected_type.__name__}."
        )

    def _direct_parse(self, text: str) -> ParseResult:
        """Strategy 1: Direct JSON parsing"""
        try:
            data = json.loads(text)
            return ParseResult(success=True, data=data, strategy_used="direct")
        except json.JSONDecodeError as e:
            return ParseResult(success=False, error=str(e))

    def _parse_from_markdown(self, text: str) -> ParseResult:
        """Strategy 2: Extract JSON from markdown code blocks"""
        try:
            json_text = self._extract_json_block(text)
            data = json.loads(json_text)
            return ParseResult(success=True, data=data, strategy_used="markdown")
        except (json.JSONDecodeError, ValueError) as e:
            return ParseResult(success=False, error=str(e))

    def _clean_and_parse(self, text: str) -> ParseResult:
        """Strategy 3: Clean common issues then parse"""
        try:
            # Extract JSON block if in markdown
            json_text = self._extract_json_block(text)

            # Apply cleaning transformations
            cleaned = self._clean_json_text(json_text)

            data = json.loads(cleaned)
            return ParseResult(success=True, data=data, strategy_used="cleaned")
        except (json.JSONDecodeError, ValueError) as e:
            return ParseResult(success=False, error=str(e))

    def _repair_json(self, text: str) -> ParseResult:
        """Strategy 4: Use json_repair library if available"""
        try:
            from json_repair import repair_json

            json_text = self._extract_json_block(text)
            repaired = repair_json(json_text)
            data = json.loads(repaired)

            return ParseResult(success=True, data=data, strategy_used="repaired")
        except ImportError:
            return ParseResult(
                success=False,
                error="json_repair library not available"
            )
        except Exception as e:
            return ParseResult(success=False, error=str(e))

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """Extract JSON from markdown code blocks"""
        # Try ```json blocks first
        if '```json' in text:
            parts = text.split('```json')
            if len(parts) > 1:
                json_part = parts[1].split('```')[0].strip()
                return json_part

        # Try generic ``` blocks
        if '```' in text:
            parts = text.split('```')
            if len(parts) >= 3:
                # Take the first code block
                json_part = parts[1].strip()
                # Skip if it's not JSON-like
                if json_part.startswith(('{', '[')):
                    return json_part

        # No code blocks found, return as-is
        return text.strip()

    @staticmethod
    def _clean_json_text(text: str) -> str:
        """
        Clean common JSON formatting issues.

        Handles:
        - Newlines in strings
        - Trailing commas
        - Control characters
        - Multiple consecutive commas
        """
        # Remove newlines and tabs (but preserve spaces)
        cleaned = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')

        # Remove control characters (keep printable ASCII + common unicode)
        cleaned = ''.join(
            char for char in cleaned
            if ord(char) >= 32 or char in ' \n\r\t'
        )

        # Fix trailing commas before closing brackets/braces
        cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)

        # Fix multiple consecutive commas
        cleaned = re.sub(r',\s*,+', ',', cleaned)

        # Fix comma after opening brackets/braces
        cleaned = re.sub(r'([{\[])\s*,', r'\1', cleaned)

        return cleaned.strip()

    def _save_failed_parse(self, text: str) -> None:
        """Save failed parse attempts for debugging"""
        import tempfile
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.json',
                prefix='paperscope_parse_fail_',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(text)
                logger.error(f"Failed JSON parse saved to: {f.name}")
                logger.error(f"Text length: {len(text)} chars")
                logger.error(f"First 500 chars: {text[:500]}")
                logger.error(f"Last 500 chars: {text[-500:]}")
        except Exception as e:
            logger.error(f"Could not save failed parse: {e}")

    def get_stats(self) -> dict:
        """Get parsing statistics"""
        return {
            'total_attempts': self.parse_attempts,
            'successful': self.successful_parses,
            'success_rate': (
                self.successful_parses / self.parse_attempts
                if self.parse_attempts > 0
                else 0.0
            )
        }


class PromptBuilder:
    """
    Centralized prompt building with templates and best practices.

    Now uses the centralized PromptManager for all templates.
    This class is maintained for backward compatibility.
    """

    def __init__(self):
        # Import here to avoid circular dependency
        from src.prompts import get_prompt_manager
        self._prompt_manager = get_prompt_manager()

        # Legacy template names for backward compatibility
        self.templates = {
            'categorize': 'paperscope/categorize',
            'summarize': 'paperscope/summarize',
            'extract_trials': 'paperscope/extract_trials',
            'detect_context': 'paperscope/detect_context',
            'filter_relevance': 'paperscope/filter_relevance',
        }

    def build_prompt(
        self,
        prompt_type: str,
        include_json_instructions: bool = True,
        **kwargs
    ) -> str:
        """
        Build a prompt from template.

        Args:
            prompt_type: Type of prompt ('categorize', 'summarize', etc.)
            include_json_instructions: Whether to append JSON formatting rules (ignored - always included)
            **kwargs: Variables to substitute in template

        Returns:
            Formatted prompt string
        """
        if prompt_type not in self.templates:
            raise ValueError(f"Unknown prompt type: {prompt_type}")

        template_name = self.templates[prompt_type]
        return self._prompt_manager.render(template_name, **kwargs)


class TokenUsageTracker:
    """Track Claude API token usage and costs"""

    # Cost per 1K tokens (as of 2025)
    COSTS = {
        'claude-sonnet-4-5-20250929': {'input': 0.003, 'output': 0.015},
        'claude-sonnet-4-20250514': {'input': 0.003, 'output': 0.015},
    }

    def __init__(self):
        self.total_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def track(self, usage: Any):
        """Track token usage from API response"""
        self.total_calls += 1
        self.total_input_tokens += getattr(usage, 'input_tokens', 0)
        self.total_output_tokens += getattr(usage, 'output_tokens', 0)

    def get_cost(self, model: str) -> float:
        """Calculate estimated cost in USD"""
        costs = self.COSTS.get(model, {'input': 0, 'output': 0})
        return (
            (self.total_input_tokens / 1000) * costs['input'] +
            (self.total_output_tokens / 1000) * costs['output']
        )

    def get_summary(self) -> str:
        """Get formatted usage summary"""
        return (
            f"API Calls: {self.total_calls}\n"
            f"Input Tokens: {self.total_input_tokens:,}\n"
            f"Output Tokens: {self.total_output_tokens:,}\n"
            f"Total Tokens: {self.total_input_tokens + self.total_output_tokens:,}"
        )


class APIClient:
    """
    Wrapper for Anthropic API with retry logic, rate limiting, and caching.

    Features:
    - Automatic retries with exponential backoff
    - Rate limiting to stay within API limits
    - Optional response caching
    - Token usage tracking
    - Timeout handling
    """

    def __init__(
        self,
        anthropic_client: Any,
        config: PaperScopeConfig,
        cache: Optional['ResponseCache'] = None
    ):
        self.anthropic = anthropic_client
        self.config = config
        self.cache = cache
        self.token_tracker = TokenUsageTracker()

        # Rate limiting
        self.last_call_time = 0
        self.min_interval = 1.0 / 50  # 50 requests per second max

    def call_claude(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0,
        cache_key: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3
    ) -> str:
        """
        Call Claude API with retry logic and caching.

        Args:
            prompt: The prompt to send
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            cache_key: Optional key for caching responses
            timeout: Request timeout in seconds
            max_retries: Number of retry attempts

        Returns:
            Response text from Claude

        Raises:
            Exception: If all retry attempts fail
        """
        # Check cache first
        if cache_key and self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"💾 Cache hit for {cache_key[:50]}...")
                return cached

        # Rate limiting
        self._rate_limit()

        # Retry logic
        last_exception = None
        for attempt in range(max_retries):
            try:
                logger.debug(f"Calling Claude API (attempt {attempt + 1}/{max_retries}, max_tokens={max_tokens})")

                response = self.anthropic.messages.create(
                    model=self.config.model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=timeout
                )

                result = response.content[0].text

                # Track token usage
                self.token_tracker.track(response.usage)

                # Cache successful responses
                if cache_key and self.cache:
                    self.cache.set(cache_key, result, ttl_hours=self.config.cache_ttl_hours)

                return result

            except Exception as e:
                last_exception = e
                error_type = type(e).__name__
                logger.warning(f"⚠️ API call failed (attempt {attempt + 1}/{max_retries}): {error_type} - {e}")

                if attempt < max_retries - 1:
                    # Exponential backoff
                    wait_time = self.config.api_retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"❌ All {max_retries} retry attempts failed")

        # All retries failed
        raise last_exception

    def _rate_limit(self):
        """Enforce rate limiting between API calls"""
        elapsed = time.time() - self.last_call_time
        if elapsed < self.min_interval:
            sleep_time = self.min_interval - elapsed
            time.sleep(sleep_time)
        self.last_call_time = time.time()

    def get_usage_stats(self) -> Dict[str, Any]:
        """Get API usage statistics"""
        return {
            'total_calls': self.token_tracker.total_calls,
            'total_input_tokens': self.token_tracker.total_input_tokens,
            'total_output_tokens': self.token_tracker.total_output_tokens,
            'estimated_cost': self.token_tracker.get_cost(self.config.model)
        }


class ResponseCache:
    """
    Disk-based cache for API responses.

    Features:
    - TTL-based expiration
    - Automatic cleanup
    - Hash-based keys
    - JSON serialization
    """

    def __init__(self, cache_dir: Path, default_ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True, parents=True)
        self.default_ttl = default_ttl_hours * 3600  # Convert to seconds

        # Cache statistics
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve value from cache.

        Args:
            key: Cache key (will be hashed)

        Returns:
            Cached value or None if not found/expired
        """
        cache_file = self._get_cache_file(key)

        if not cache_file.exists():
            self.misses += 1
            return None

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)

            # Check TTL
            timestamp = cached_data.get('timestamp', 0)
            ttl = cached_data.get('ttl', self.default_ttl)

            if time.time() - timestamp > ttl:
                logger.debug(f"Cache expired: {key[:50]}...")
                cache_file.unlink()  # Delete expired cache
                self.misses += 1
                return None

            self.hits += 1
            logger.debug(f"Cache hit: {key[:50]}...")
            return cached_data['value']

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Corrupted cache file: {e}")
            cache_file.unlink()
            self.misses += 1
            return None

    def set(
        self,
        key: str,
        value: Any,
        ttl_hours: Optional[int] = None
    ) -> None:
        """
        Store value in cache.

        Args:
            key: Cache key (will be hashed)
            value: Value to cache (must be JSON serializable)
            ttl_hours: Time to live in hours (None = use default)
        """
        cache_file = self._get_cache_file(key)

        ttl = (ttl_hours * 3600) if ttl_hours else self.default_ttl

        cache_data = {
            'value': value,
            'timestamp': time.time(),
            'ttl': ttl,
            'key_preview': key[:100]  # For debugging
        }

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            logger.debug(f"Cached: {key[:50]}...")
        except Exception as e:
            logger.error(f"Failed to cache value: {e}")

    def clear(self) -> int:
        """
        Clear all cache files.

        Returns:
            Number of files deleted
        """
        count = 0
        for cache_file in self.cache_dir.glob('*.json'):
            cache_file.unlink()
            count += 1

        logger.info(f"Cleared {count} cache files")
        return count

    def cleanup_expired(self) -> int:
        """
        Delete expired cache files.

        Returns:
            Number of files deleted
        """
        count = 0
        current_time = time.time()

        for cache_file in self.cache_dir.glob('*.json'):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                timestamp = cached_data.get('timestamp', 0)
                ttl = cached_data.get('ttl', self.default_ttl)

                if current_time - timestamp > ttl:
                    cache_file.unlink()
                    count += 1
            except Exception:
                # If file is corrupted, delete it
                cache_file.unlink()
                count += 1

        logger.info(f"Cleaned up {count} expired cache files")
        return count

    def _get_cache_file(self, key: str) -> Path:
        """Get cache file path for key"""
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"

    def get_stats(self) -> dict:
        """Get cache statistics"""
        total_requests = self.hits + self.misses
        hit_rate = self.hits / total_requests if total_requests > 0 else 0.0

        return {
            'hits': self.hits,
            'misses': self.misses,
            'hit_rate': hit_rate,
            'total_files': len(list(self.cache_dir.glob('*.json')))
        }


class ProgressTracker:
    """Track progress across multiple phases"""

    def __init__(self):
        from datetime import datetime
        self.phases = {
            'trial_discovery': {'total': 4, 'completed': 0},
            'literature_search': {'total': None, 'completed': 0},
            'paper_retrieval': {'total': None, 'completed': 0},
            'categorization': {'total': None, 'completed': 0},
            'summarization': {'total': None, 'completed': 0},
            'cross_referencing': {'total': 3, 'completed': 0}
        }
        self.start_time = datetime.now()
        self.current_phase = None
        self.phase_descriptions = {}

    def start_phase(self, phase: str, description: str = ""):
        """Start a new phase"""
        self.current_phase = phase
        self.phase_descriptions[phase] = description
        if phase not in self.phases:
            self.phases[phase] = {'total': None, 'completed': 0}
        logger.info(f"Starting phase: {phase} - {description}")

    def complete_phase(self, phase: str):
        """Mark a phase as complete"""
        if phase in self.phases:
            if self.phases[phase]['total'] is not None:
                self.phases[phase]['completed'] = self.phases[phase]['total']
            logger.info(f"Completed phase: {phase}")

    def update_progress(self, current: int, total: int, message: str = ""):
        """Update progress with current/total and optional message"""
        if self.current_phase:
            self.phases[self.current_phase]['completed'] = current
            self.phases[self.current_phase]['total'] = total
            if message:
                logger.info(f"  [{current}/{total}] {message}")

    def update(self, phase: str, increment: int = 1):
        """Update progress for a phase"""
        if phase in self.phases:
            self.phases[phase]['completed'] += increment

    def set_total(self, phase: str, total: int):
        """Set total items for a phase"""
        if phase in self.phases:
            self.phases[phase]['total'] = total

    def get_summary(self) -> dict:
        """Get progress summary"""
        from datetime import datetime
        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            'phases': self.phases,
            'elapsed_seconds': elapsed
        }


class StructuredLogger:
    """Enhanced logging with structured output"""

    def __init__(self, name: str, log_dir: Path):
        from datetime import datetime
        self.logger = logging.getLogger(name)
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True, parents=True)

        # Setup file handler
        log_file = self.log_dir / f"{name}_{datetime.now():%Y%m%d_%H%M%S}.log"
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def log_phase_start(self, phase_name: str, description: str):
        """Log phase start"""
        self.logger.info("=" * 80)
        self.logger.info(f"PHASE: {phase_name}")
        self.logger.info(f"Description: {description}")
        self.logger.info("=" * 80)

    def log_phase_complete(self, phase_name: str, metrics: dict):
        """Log phase completion with metrics"""
        self.logger.info(f"✅ {phase_name} complete")
        for key, value in metrics.items():
            self.logger.info(f"  {key}: {value}")

    def log_event(self, event_name: str, data: dict):
        """Log an event with structured data"""
        self.logger.info(f"EVENT: {event_name}")
        for key, value in data.items():
            self.logger.info(f"  {key}: {value}")


class ParallelProcessor:
    """
    Utility for parallel processing with error handling.

    Features:
    - Configurable worker count
    - Progress tracking
    - Error collection
    - Graceful degradation
    """

    def __init__(self, max_workers: int = 5):
        self.max_workers = max_workers
        self.errors = []

    def map_with_progress(
        self,
        func: Callable,
        items: List[Any],
        desc: str = "Processing"
    ) -> List[Any]:
        """
        Map function over items in parallel with progress bar.

        Args:
            func: Function to apply to each item
            items: List of items to process
            desc: Description for progress bar

        Returns:
            List of results (in same order as input)
        """
        try:
            from tqdm import tqdm
            has_tqdm = True
        except ImportError:
            has_tqdm = False
            logger.warning("tqdm not available, progress bar disabled")

        results = [None] * len(items)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(func, item): i
                for i, item in enumerate(items)
            }

            # Process completed tasks
            if has_tqdm:
                pbar = tqdm(total=len(items), desc=desc)

            for future in as_completed(future_to_index):
                index = future_to_index[future]
                try:
                    results[index] = future.result()
                except Exception as e:
                    logger.error(f"Task {index} failed: {e}")
                    self.errors.append({'index': index, 'error': str(e)})
                    results[index] = None
                finally:
                    if has_tqdm:
                        pbar.update(1)

            if has_tqdm:
                pbar.close()

        return results

    def get_error_summary(self) -> str:
        """Get summary of errors"""
        if not self.errors:
            return "No errors"
        return f"{len(self.errors)} errors: " + "; ".join(
            f"Item {e['index']}: {e['error'][:50]}"
            for e in self.errors[:5]
        )


# Input validation with Pydantic
try:
    from pydantic import BaseModel, validator, Field

    class SearchRequest(BaseModel):
        """Validate search request inputs"""

        drug_name: str = Field(..., min_length=2, max_length=200)
        disease_indication: Optional[str] = Field(None, max_length=200)
        drug_class: Optional[str] = Field(None, max_length=100)
        max_results_per_search: int = Field(100, ge=1, le=1000)

        @validator('drug_name')
        def validate_drug_name(cls, v):
            """Ensure drug name is clean"""
            v = v.strip()
            if not v:
                raise ValueError("Drug name cannot be empty or whitespace")
            # Remove special characters that could break searches
            if any(char in v for char in ['<', '>', '"', '`', '{', '}']):
                raise ValueError("Drug name contains invalid characters")
            return v

        @validator('disease_indication')
        def validate_disease(cls, v):
            """Clean disease indication"""
            if v:
                v = v.strip()
                if not v:
                    return None
            return v

        @validator('max_results_per_search')
        def validate_max_results(cls, v):
            """Ensure reasonable search limits"""
            if v > 500:
                logger.warning(f"Large max_results ({v}) may slow down search")
            return v

        class Config:
            schema_extra = {
                "example": {
                    "drug_name": "anifrolumab",
                    "disease_indication": "systemic lupus erythematosus",
                    "drug_class": "monoclonal antibody",
                    "max_results_per_search": 100
                }
            }

    PYDANTIC_AVAILABLE = True
except ImportError:
    logger.warning("Pydantic not available, input validation disabled")
    PYDANTIC_AVAILABLE = False
    SearchRequest = None

