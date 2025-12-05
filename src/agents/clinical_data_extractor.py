"""
Clinical Data Extractor Agent.

Extracts structured clinical trial data from scientific papers including:
- Baseline patient characteristics (demographics, prior medications)
- Efficacy endpoints (primary, secondary, exploratory)
- Safety endpoints (AEs, SAEs, discontinuations)

Uses multi-stage extraction with extended thinking for complex table interpretation.
"""
from typing import Dict, Any, List, Optional, Callable, TypeVar, Tuple
import json
import logging
import re
import base64
import time
from pathlib import Path
from functools import wraps
from time import perf_counter
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from anthropic import Anthropic

from src.agents.base_agent import BaseAgent
from src.agents.clinical_extraction_types import (
    ExtractionStage,
    ExtractionProgress,
    ExtractionMetrics,
    MetricsCollector,
    ProgressCallback,
    PreparedPaperContent,
)
from src.utils.paperscope_v2_adapter import PaperScopeV2Adapter
from src.agents.clinical_extraction_constants import (
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    RETRYABLE_STATUS_CODES,
    THINKING_BUDGET_SECTIONS,
    THINKING_BUDGET_MEDICATIONS,
    THINKING_BUDGET_DISEASE,
    THINKING_BUDGET_EFFICACY,
    THINKING_BUDGET_VALIDATION,
    MAX_TOKENS_DEFAULT,
    MAX_TOKENS_TRIAL_DESIGN,
    MAX_TOKENS_EFFICACY,
    MAX_TOKENS_SAFETY,
    MAX_TOKENS_FIGURE,
    CONTENT_TRUNCATION_SHORT,
    MIN_FIGURE_WIDTH,
    MIN_FIGURE_HEIGHT,
)
from src.models.clinical_extraction_schemas import (
    ClinicalTrialExtraction,
    BaselineCharacteristics,
    EfficacyEndpoint,
    SafetyEndpoint,
    TrialArm,
    TrialDesignMetadata,
    DataSectionIdentification,
    ExtractionValidationResult,
)
from src.prompts import PromptManager, get_prompt_manager

logger = logging.getLogger(__name__)

# Type variable for retry decorator
T = TypeVar('T')


def with_retry(
    max_retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY,
    retryable_errors: tuple = RETRYABLE_STATUS_CODES
) -> Callable:
    """
    Decorator for API calls with exponential backoff retry.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (multiplied by attempt number)
        retryable_errors: HTTP status codes that should trigger retry

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_msg = str(e)

                    # Check if retryable
                    is_retryable = any(
                        str(code) in error_msg
                        for code in retryable_errors
                    ) or "Internal server error" in error_msg

                    if is_retryable and attempt < max_retries - 1:
                        wait_time = base_delay * (attempt + 1)
                        logger.warning(
                            f"Retryable error on attempt {attempt + 1}/{max_retries}, "
                            f"waiting {wait_time}s: {e}"
                        )
                        time.sleep(wait_time)
                    else:
                        raise

            raise last_exception
        return wrapper
    return decorator


# PyMuPDF for figure extraction
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    logger.warning("PyMuPDF not available. Figure extraction will be disabled.")
    PYMUPDF_AVAILABLE = False


@dataclass
class ArmExtractionResult:
    """Result of extracting data for a single arm."""
    arm: TrialArm
    baseline: BaselineCharacteristics
    baseline_detail: List[Dict[str, Any]]
    efficacy: List[EfficacyEndpoint]
    safety: List[SafetyEndpoint]
    error: Optional[str] = None


class ClinicalDataExtractorAgent(BaseAgent):
    """
    Clinical data extraction agent with multi-stage prompting.

    This agent extracts structured clinical trial data from scientific papers
    including baseline characteristics, efficacy endpoints, and safety data.

    Extraction Pipeline:
        Stage 0: Trial design metadata (trial-level information)
        Stage 0.5: Table validation (filter false positives by caption)
        Stage 1: Section identification (EXTENDED THINKING)
        Stage 2: Standard demographics extraction
        Stage 3: Prior medications (EXTENDED THINKING)
        Stage 4: Disease-specific baseline (EXTENDED THINKING)
        Stage 5: Efficacy endpoints (EXTENDED THINKING)
        Stage 5b: Figure extraction (VISION API, filtered by caption)
        Stage 6: Safety endpoints
        Stage 7: Validation (EXTENDED THINKING)

    Cost Optimizations:
        - Parallel arm processing (3x speedup)
        - Caption-based figure filtering (reduces vision API calls)
        - Table caption validation (filters false positives)
        - Reduced max_tokens limits (20-30% reduction)

    Attributes:
        client: Anthropic API client
        model: Claude model identifier
        max_tokens: Maximum tokens per response
        strict_validation: Whether to enforce strict validation rules

    Example:
        >>> agent = ClinicalDataExtractorAgent(client)
        >>> design, extractions = agent.extract_trial_data(
        ...     paper=paper_dict,
        ...     nct_id="NCT12345678",
        ...     drug_name="Upadacitinib",
        ...     indication="Rheumatoid Arthritis"
        ... )
    """

    def __init__(
        self,
        client: Anthropic,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = MAX_TOKENS_EFFICACY,
        strict_validation: bool = True,
        pubmed_api=None,
        parallel_arms: bool = True,
        max_parallel_arms: int = 3,
        filter_figures_by_caption: bool = True  # Only process figures with relevant captions
    ):
        """
        Initialize clinical data extractor agent.

        Args:
            client: Anthropic API client
            model: Claude model to use
            max_tokens: Maximum tokens per response (default: 12000 for comprehensive baseline extraction)
            strict_validation: Use strict validation rules
            pubmed_api: Optional PubMedAPI instance for downloading full text from PaperScope v2 papers
            parallel_arms: Enable parallel processing of trial arms (default: True)
            max_parallel_arms: Maximum number of arms to process in parallel (default: 3)
            filter_figures_by_caption: Only process figures with relevant captions (default: True, reduces cost)
        """
        super().__init__(client, model, max_tokens)
        self.strict_validation = strict_validation
        self.parallel_arms = parallel_arms
        self.max_parallel_arms = max_parallel_arms
        self.filter_figures_by_caption = filter_figures_by_caption
        self._prompts = get_prompt_manager()

        # Metrics tracking
        self._metrics: Optional[ExtractionMetrics] = None
        self._metrics_collector: Optional[MetricsCollector] = None

        # Pre-processed content (set during extraction)
        self._prepared_content: Optional[PreparedPaperContent] = None

        # PaperScope v2 adapter for converting papers
        self._paperscope_adapter = PaperScopeV2Adapter(pubmed_api=pubmed_api)

    def analyze(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main analysis method - satisfies BaseAgent abstract method requirement.

        This is a wrapper around extract_trial_data() for compatibility with
        the base agent interface.

        Args:
            state: Workflow state containing:
                - paper: Paper content dict
                - nct_id: ClinicalTrials.gov NCT ID
                - drug_name: Drug brand name
                - indication: Disease indication
                - standard_endpoints: Optional list of standard clinical endpoints

        Returns:
            Dictionary containing:
                - trial_design: TrialDesignMetadata
                - extractions: List of ClinicalTrialExtraction objects
        """
        paper = state.get('paper', {})
        nct_id = state.get('nct_id', '')
        drug_name = state.get('drug_name', '')
        indication = state.get('indication', '')
        standard_endpoints = state.get('standard_endpoints')

        trial_design, extractions, metrics = self.extract_trial_data(
            paper=paper,
            nct_id=nct_id,
            drug_name=drug_name,
            indication=indication,
            standard_endpoints=standard_endpoints
        )

        return {
            'trial_design': trial_design,
            'extractions': extractions,
            'metrics': metrics.to_dict() if metrics else None
        }

    def extract_trial_data(
        self,
        paper: Dict[str, Any],
        nct_id: str,
        drug_name: str,
        indication: str,
        standard_endpoints: Optional[List[str]] = None,
        progress_callback: Optional[ProgressCallback] = None
    ) -> Tuple[TrialDesignMetadata, List[ClinicalTrialExtraction], ExtractionMetrics]:
        """
        Main extraction method - extracts trial design + all trial arms from a paper.

        Args:
            paper: Paper content dict with 'content', 'title', 'authors', etc.
            nct_id: ClinicalTrials.gov NCT ID
            drug_name: Drug brand name
            indication: Disease indication
            standard_endpoints: List of standard clinical endpoints from landscape discovery
            progress_callback: Optional callback for progress reporting

        Returns:
            Tuple of (TrialDesignMetadata, List[ClinicalTrialExtraction], ExtractionMetrics)

        Raises:
            ValueError: If required inputs are missing or invalid
        """
        # Initialize metrics tracking
        extraction_start_time = perf_counter()
        self._metrics = ExtractionMetrics()
        self._metrics_collector = MetricsCollector(self._metrics)

        # Helper function for progress reporting
        def report_progress(stage: ExtractionStage, index: int, **kwargs):
            if progress_callback:
                progress_callback(ExtractionProgress(
                    stage=stage,
                    stage_index=index,
                    total_stages=11,  # Total stages: 0, 0.5, 1, 2, 3, 4, 5, 5b, 6, 7, validation
                    **kwargs
                ))

        # INPUT VALIDATION (may convert PaperScope v2 papers, infer indication, and find NCT ID)
        report_progress(ExtractionStage.PREPARATION, 0, message="Validating inputs")
        paper, indication, nct_id = self._validate_inputs(paper, nct_id, drug_name, indication)

        logger.info(f"Starting clinical data extraction for {nct_id} ({drug_name} for {indication})")

        # PRE-PROCESS CONTENT (avoid repeated truncation)
        logger.info("Pre-processing paper content")
        self._prepared_content = PreparedPaperContent.from_paper(paper)

        # VALIDATE NCT ID (FIX #3)
        validated_nct_id = self._validate_nct_id(paper, nct_id)
        if validated_nct_id != nct_id:
            logger.info(f"Using validated NCT ID: {validated_nct_id} (provided: {nct_id})")
            nct_id = validated_nct_id

        # CHECK FOR DUPLICATE EXTRACTION (FIX #1)
        if self._trial_already_extracted(nct_id):
            logger.warning(f"Trial {nct_id} already extracted. Skipping to avoid duplicates.")
            logger.warning(f"To re-extract, first delete existing data using: db.delete_trial_data('{nct_id}')")
            self._metrics.total_duration_seconds = perf_counter() - extraction_start_time
            return None, [], self._metrics

        # GET TRIAL NAME FROM DATABASE (FIX #4)
        trial_name = self._get_trial_name_from_database(nct_id)
        if trial_name:
            logger.info(f"Retrieved trial name from database: {trial_name}")
        else:
            logger.warning(f"No trial name found in database for {nct_id}")

        # Stage 0: Extract trial design metadata
        report_progress(ExtractionStage.TRIAL_DESIGN, 1, message="Extracting trial design")
        logger.info("Stage 0: Extracting trial design metadata")
        with self._metrics_collector.track_stage("stage0_trial_design"):
            trial_design = self._stage0_extract_trial_design(paper, nct_id, indication, trial_name)

        # Stage 0.5a: Filter tables by caption relevance (LLM-based)
        report_progress(ExtractionStage.TABLE_VALIDATION, 2, message="Filtering tables by caption")
        logger.info("Stage 0.5a: Filtering tables by caption relevance")
        with self._metrics_collector.track_stage("stage0.5a_table_caption_filter"):
            paper = self._filter_tables_by_caption(paper)
            logger.info(f"After caption filtering: {len(paper.get('tables', []))} tables remaining")

        # Stage 0.5b: Validate tables (NEW)
        report_progress(ExtractionStage.TABLE_VALIDATION, 2, message="Validating tables")
        logger.info("Stage 0.5b: Validating extracted tables")
        with self._metrics_collector.track_stage("stage0.5b_table_validation"):
            paper = self._validate_and_filter_tables(paper, drug_name, indication)
            self._metrics.tables_processed = len(paper.get('tables', []))

        # Stage 1: Identify data sections (EXTENDED THINKING)
        report_progress(ExtractionStage.SECTION_IDENTIFICATION, 3, message="Identifying data sections")
        logger.info("Stage 1: Identifying data sections with extended thinking")
        with self._metrics_collector.track_stage("stage1_sections"):
            sections = self._stage1_identify_sections(paper, nct_id, indication)

        if not sections.trial_arms:
            logger.warning(f"No trial arms identified in {nct_id}")
            self._metrics.total_duration_seconds = perf_counter() - extraction_start_time
            return trial_design, [], self._metrics

        logger.info(f"Stage 1: Found {len(sections.trial_arms)} trial arms")

        # Extract data for each trial arm (parallel or sequential)
        total_arms = len(sections.trial_arms)
        self._metrics.arms_extracted = total_arms

        arm_results = self._extract_all_arms(
            paper=paper,
            sections=sections,
            standard_endpoints=standard_endpoints,
            indication=indication,
            nct_id=nct_id,
            trial_name=trial_name,
            drug_name=drug_name,
            progress_callback=report_progress
        )

        # Convert arm results to extraction objects
        extractions = []
        for result in arm_results:
            if result.error:
                logger.error(f"Arm extraction failed for {result.arm.arm_name}: {result.error}")
                self._metrics.warnings.append(f"Arm extraction failed: {result.arm.arm_name}")
                continue

            extraction = ClinicalTrialExtraction(
                nct_id=nct_id,
                trial_name=trial_name,
                drug_name=drug_name,
                generic_name=self._extract_generic_name(paper, drug_name),
                indication=indication,
                arm_name=result.arm.arm_name,
                dosing_regimen=self._normalize_dosing_regimen(result.arm.dosing_regimen),
                background_therapy=result.arm.background_therapy,
                n=result.arm.n,
                phase=self._extract_phase(paper),
                paper_pmid=paper.get('pmid'),
                paper_doi=paper.get('doi'),
                paper_title=paper.get('title'),
                baseline=result.baseline,
                baseline_characteristics_detail=result.baseline_detail,
                efficacy_endpoints=result.efficacy,
                safety_endpoints=result.safety
            )

            extractions.append(extraction)

            # Track extraction metrics
            self._metrics.endpoints_extracted += len(result.efficacy)
            self._metrics.safety_events_extracted += len(result.safety)

        # Stage 7: Validate all extractions
        report_progress(ExtractionStage.VALIDATION, 10, message="Validating extractions")
        logger.info("Stage 7: Validating extractions with extended thinking")
        with self._metrics_collector.track_stage("stage7_validation"):
            for extraction in extractions:
                validation = self._validate_extraction(extraction)
                extraction.extraction_confidence = self._calculate_confidence(validation)
                extraction.extraction_notes = validation.summary()

                if not validation.is_valid and self.strict_validation:
                    logger.warning(f"Validation failed for {extraction.arm_name}: {validation.summary()}")
                    self._metrics.warnings.append(f"Validation failed for {extraction.arm_name}")

        # Finalize metrics
        self._metrics.total_duration_seconds = perf_counter() - extraction_start_time

        logger.info(f"Extraction complete: {len(extractions)} trial arms extracted")
        logger.info(f"Metrics: {self._metrics.api_calls} API calls, {self._metrics.total_tokens} tokens, "
                   f"${self._metrics.estimated_cost_usd:.4f} estimated cost, "
                   f"{self._metrics.total_duration_seconds:.1f}s duration")

        return trial_design, extractions, self._metrics

    def _extract_all_arms(
        self,
        paper: Dict[str, Any],
        sections: DataSectionIdentification,
        standard_endpoints: Optional[List[str]],
        indication: str,
        nct_id: str,
        trial_name: str,
        drug_name: str,
        progress_callback: Optional[Callable] = None
    ) -> List[ArmExtractionResult]:
        """
        Extract data for all arms (parallel or sequential based on settings).

        This method orchestrates arm extraction, using parallel processing when
        enabled and beneficial (multi-arm trials).
        """
        total_arms = len(sections.trial_arms)

        # Use sequential processing for single-arm trials or if parallel disabled
        if not self.parallel_arms or total_arms == 1:
            logger.info(f"Using sequential arm extraction (parallel={self.parallel_arms}, arms={total_arms})")
            return self._extract_arms_sequential(
                paper, sections, standard_endpoints, indication, progress_callback
            )

        # Use parallel processing for multi-arm trials
        logger.info(f"Using parallel arm extraction with max_workers={self.max_parallel_arms}")
        return self._extract_arms_parallel(
            paper, sections, standard_endpoints, indication, progress_callback
        )

    def _extract_arms_sequential(
        self,
        paper: Dict[str, Any],
        sections: DataSectionIdentification,
        standard_endpoints: Optional[List[str]],
        indication: str,
        progress_callback: Optional[Callable] = None
    ) -> List[ArmExtractionResult]:
        """Extract arms sequentially (original behavior)."""
        results = []
        total_arms = len(sections.trial_arms)

        for i, arm in enumerate(sections.trial_arms, 1):
            logger.info(f"Extracting data for arm {i}/{total_arms}: {arm.arm_name}")
            result = self._extract_single_arm(
                paper, arm, sections, standard_endpoints, indication, i, total_arms, progress_callback
            )
            results.append(result)

        return results

    def _extract_arms_parallel(
        self,
        paper: Dict[str, Any],
        sections: DataSectionIdentification,
        standard_endpoints: Optional[List[str]],
        indication: str,
        progress_callback: Optional[Callable] = None
    ) -> List[ArmExtractionResult]:
        """Extract arms in parallel using ThreadPoolExecutor."""
        results = []
        total_arms = len(sections.trial_arms)

        with ThreadPoolExecutor(max_workers=self.max_parallel_arms) as executor:
            # Submit all arm extraction tasks
            future_to_arm = {
                executor.submit(
                    self._extract_single_arm,
                    paper, arm, sections, standard_endpoints, indication,
                    i, total_arms, progress_callback
                ): (i, arm)
                for i, arm in enumerate(sections.trial_arms, 1)
            }

            # Collect results as they complete
            for future in as_completed(future_to_arm):
                i, arm = future_to_arm[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"Completed extraction for arm {i}/{total_arms}: {arm.arm_name}")
                except Exception as e:
                    logger.error(f"Extraction failed for arm {arm.arm_name}: {e}")
                    results.append(ArmExtractionResult(
                        arm=arm,
                        baseline=BaselineCharacteristics(),
                        baseline_detail=[],
                        efficacy=[],
                        safety=[],
                        error=str(e)
                    ))

        # Sort results by original arm order
        arm_order = {arm.arm_name: i for i, arm in enumerate(sections.trial_arms)}
        results.sort(key=lambda r: arm_order.get(r.arm.arm_name, 999))

        return results

    def _extract_single_arm(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        sections: DataSectionIdentification,
        standard_endpoints: Optional[List[str]],
        indication: str,
        arm_index: int,
        total_arms: int,
        progress_callback: Optional[Callable] = None
    ) -> ArmExtractionResult:
        """Extract all data for a single arm (stages 2-6)."""
        try:
            # Stage 2: Demographics
            if progress_callback:
                progress_callback(ExtractionStage.DEMOGRAPHICS, 4, arm_index=arm_index,
                                total_arms=total_arms, message=f"Extracting demographics for {arm.arm_name}")

            logger.info(f"Stage 2: Extracting standard demographics for {arm.arm_name}")
            with self._metrics_collector.track_stage(f"stage2_demographics_arm{arm_index}"):
                baseline, baseline_detail = self._stage2_extract_demographics(
                    paper, arm, sections.baseline_tables
                )

            # Stage 3: Prior medications
            if progress_callback:
                progress_callback(ExtractionStage.PRIOR_MEDICATIONS, 5, arm_index=arm_index,
                                total_arms=total_arms, message=f"Extracting prior medications for {arm.arm_name}")

            logger.info(f"Stage 3: Extracting prior medications with extended thinking")
            with self._metrics_collector.track_stage(f"stage3_medications_arm{arm_index}"):
                baseline = self._stage3_extract_prior_medications(
                    paper, arm, baseline, sections.baseline_tables, indication
                )

            # Stage 4: Disease baseline
            if progress_callback:
                progress_callback(ExtractionStage.DISEASE_BASELINE, 6, arm_index=arm_index,
                                total_arms=total_arms, message=f"Extracting disease baseline for {arm.arm_name}")

            logger.info(f"Stage 4: Extracting disease-specific baseline with extended thinking")
            with self._metrics_collector.track_stage(f"stage4_disease_arm{arm_index}"):
                baseline = self._stage4_extract_disease_baseline(
                    paper, arm, baseline, sections.baseline_tables, indication
                )

            # Stage 5: Efficacy
            if progress_callback:
                progress_callback(ExtractionStage.EFFICACY, 7, arm_index=arm_index,
                                total_arms=total_arms, message=f"Extracting efficacy endpoints for {arm.arm_name}")

            logger.info(f"Stage 5: Extracting efficacy endpoints with extended thinking")
            with self._metrics_collector.track_stage(f"stage5_efficacy_arm{arm_index}"):
                efficacy = self._stage5_extract_efficacy(
                    paper, arm, sections.efficacy_tables, standard_endpoints, indication
                )

            # Stage 5b: Figures (filter by caption if enabled to reduce cost)
            if progress_callback:
                progress_callback(ExtractionStage.FIGURES, 8, arm_index=arm_index,
                                total_arms=total_arms, message=f"Extracting figures for {arm.arm_name}")

            logger.info(f"Stage 5b: Extracting efficacy from figures using vision API")
            with self._metrics_collector.track_stage(f"stage5b_figures_arm{arm_index}"):
                figure_efficacy = self._stage5b_extract_figures(paper, arm, indication)

            if figure_efficacy:
                logger.info(f"Stage 5b: Found {len(figure_efficacy)} additional endpoints from figures")
                efficacy.extend(figure_efficacy)
                self._metrics.figures_processed += len(figure_efficacy)

            # Stage 6: Safety
            if progress_callback:
                progress_callback(ExtractionStage.SAFETY, 9, arm_index=arm_index,
                                total_arms=total_arms, message=f"Extracting safety endpoints for {arm.arm_name}")

            logger.info(f"Stage 6: Extracting safety endpoints")
            with self._metrics_collector.track_stage(f"stage6_safety_arm{arm_index}"):
                safety = self._stage6_extract_safety(paper, arm, sections.safety_tables)

            return ArmExtractionResult(
                arm=arm,
                baseline=baseline,
                baseline_detail=baseline_detail,
                efficacy=efficacy,
                safety=safety
            )

        except Exception as e:
            logger.error(f"Error extracting arm {arm.arm_name}: {e}")
            import traceback
            traceback.print_exc()
            return ArmExtractionResult(
                arm=arm,
                baseline=BaselineCharacteristics(),
                baseline_detail=[],
                efficacy=[],
                safety=[],
                error=str(e)
            )

    def _stage1_identify_sections(
        self,
        paper: Dict[str, Any],
        nct_id: str,
        indication: str
    ) -> DataSectionIdentification:
        """
        Stage 1: Identify data sections using extended thinking.

        Uses extended thinking to interpret complex table structures and identify
        where baseline, efficacy, and safety data are located.

        Token budget: ~5,000 thinking tokens
        """
        prompt = self._get_stage1_prompt(paper, nct_id, indication)

        # Build system message with paper content for caching
        paper_content = paper.get('content', '')
        system_message = f"""You are a clinical trial data extraction specialist.

PAPER CONTENT:
{paper_content[:50000]}"""

        # Use extended thinking for table interpretation with cached paper content
        response = self._call_claude_with_thinking(
            prompt,
            thinking_budget=THINKING_BUDGET_SECTIONS,
            system_message=system_message,
            enable_caching=True
        )

        text = self._extract_text_response(response)

        # Parse JSON response (strip markdown code blocks first)
        json_str = self._extract_json_from_text(text)
        if not json_str:
            logger.error(f"Failed to extract JSON from Stage 1 response. First 1000 chars: {text[:1000]}")
            return DataSectionIdentification(
                baseline_tables=[],
                efficacy_tables=[],
                safety_tables=[],
                trial_arms=[],
                confidence=0.0,
                notes="Failed to extract JSON from response"
            )

        try:
            data = json.loads(json_str)
            return DataSectionIdentification(**data)
        except Exception as e:
            logger.error(f"JSON parsing failed in Stage 1: {e}")
            logger.error(f"Extracted JSON string: {json_str[:500]}")
            return DataSectionIdentification(
                baseline_tables=[],
                efficacy_tables=[],
                safety_tables=[],
                trial_arms=[],
                confidence=0.0,
                notes=f"Failed to parse response: {str(e)}"
            )

    def _stage2_extract_demographics(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        baseline_tables: List[str]
    ) -> tuple[BaselineCharacteristics, List[Dict[str, Any]]]:
        """
        Stage 2: Extract standard demographics and detailed characteristics.

        Extracts universal demographic fields (age, sex, race) AND all individual
        demographic characteristics (weight, BMI, lab values, biomarkers, etc.).

        No extended thinking needed - tables are now explicitly provided in prompt.

        Returns:
            Tuple of (BaselineCharacteristics summary, List of detailed characteristics)

        Token budget: ~8,000 output tokens
        """
        prompt = self._get_stage2_prompt(paper, arm, baseline_tables)

        # Build system message with paper content for caching
        paper_content = paper.get('content', '')
        system_message = f"""You are a clinical trial data extraction specialist.

PAPER CONTENT:
{paper_content[:50000]}"""

        response = self._call_claude(prompt, system=system_message, enable_caching=True)
        text = self._extract_text_response(response)

        # Parse JSON
        baseline = BaselineCharacteristics()
        characteristics_detail = []

        try:
            data = json.loads(text)

            # Extract baseline summary
            if "baseline" in data:
                baseline = BaselineCharacteristics(**data["baseline"])
            else:
                baseline = BaselineCharacteristics(**data)

            # Extract detailed characteristics
            if "baseline_characteristics_detail" in data:
                characteristics_detail = data["baseline_characteristics_detail"]

            return baseline, characteristics_detail

        except json.JSONDecodeError:
            json_str = self._extract_json_from_text(text)
            if json_str:
                try:
                    data = json.loads(json_str)

                    # Extract baseline summary
                    if "baseline" in data:
                        baseline = BaselineCharacteristics(**data["baseline"])
                    else:
                        baseline = BaselineCharacteristics(**data)

                    # Extract detailed characteristics
                    if "baseline_characteristics_detail" in data:
                        characteristics_detail = data["baseline_characteristics_detail"]

                    return baseline, characteristics_detail
                except Exception as e:
                    logger.error(f"Failed to parse Stage 2 JSON: {e}")
                    pass

            logger.error(f"Failed to parse Stage 2 response: {text[:500]}")
            return BaselineCharacteristics(), []

    def _stage3_extract_prior_medications(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        baseline: BaselineCharacteristics,
        baseline_tables: List[str],
        indication: str
    ) -> BaselineCharacteristics:
        """
        Stage 3: Extract prior medication use with extended thinking.

        Requires understanding of drug classes and therapeutic area conventions.

        Token budget: ~3,000 thinking tokens
        """
        prompt = self._get_stage3_prompt(paper, arm, baseline_tables, indication)

        # Build system message with paper content for caching
        paper_content = paper.get('content', '')
        system_message = f"""You are a clinical trial data extraction specialist.

PAPER CONTENT:
{paper_content[:50000]}"""

        response = self._call_claude_with_thinking(
            prompt,
            thinking_budget=THINKING_BUDGET_MEDICATIONS,
            system_message=system_message,
            enable_caching=True
        )

        text = self._extract_text_response(response)

        # Parse and update baseline
        data = self._parse_json_response(text, "stage3", fallback={})
        if data:
            # Update baseline with prior medication fields
            for key, value in data.items():
                if hasattr(baseline, key):
                    setattr(baseline, key, value)

        return baseline

    def _stage4_extract_disease_baseline(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        baseline: BaselineCharacteristics,
        baseline_tables: List[str],
        indication: str
    ) -> BaselineCharacteristics:
        """
        Stage 4: Extract disease-specific baseline with extended thinking.

        Identifies and extracts disease-specific biomarkers and severity scores.

        Token budget: ~3,000 thinking tokens
        """
        prompt = self._get_stage4_prompt(paper, arm, baseline_tables, indication)

        # Build system message with paper content for caching
        paper_content = paper.get('content', '')
        system_message = f"""You are a clinical trial data extraction specialist.

PAPER CONTENT:
{paper_content[:50000]}"""

        response = self._call_claude_with_thinking(
            prompt,
            thinking_budget=THINKING_BUDGET_DISEASE,
            system_message=system_message,
            enable_caching=True
        )

        text = self._extract_text_response(response)

        # Parse and update baseline
        data = self._parse_json_response(text, "stage4", fallback={})
        if data:
            if "disease_specific_baseline" in data:
                baseline.disease_specific_baseline = data["disease_specific_baseline"]
            if "baseline_severity_scores" in data:
                baseline.baseline_severity_scores = data["baseline_severity_scores"]

        return baseline

    def _stage5_extract_efficacy(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        efficacy_tables: List[str],
        standard_endpoints: Optional[List[str]],
        indication: str
    ) -> List[EfficacyEndpoint]:
        """
        Stage 5: Extract efficacy endpoints with extended thinking.

        Matches to standard endpoints and extracts new disease-specific endpoints.
        Largest thinking budget due to fuzzy matching complexity.

        Token budget: ~5,000 thinking tokens, ~16,000 output tokens
        """
        prompt = self._get_stage5_prompt(
            paper, arm, efficacy_tables, standard_endpoints, indication
        )

        # Increase output token limit for large endpoint lists
        original_max_tokens = self.max_tokens
        self.max_tokens = MAX_TOKENS_EFFICACY

        # Build system message with paper content for caching
        paper_content = paper.get('content', '')
        system_message = f"""You are a clinical trial data extraction specialist.

PAPER CONTENT:
{paper_content[:50000]}"""

        response = self._call_claude_with_thinking(
            prompt,
            thinking_budget=THINKING_BUDGET_EFFICACY,
            system_message=system_message,
            enable_caching=True
        )

        text = self._extract_text_response(response)

        # Restore token limit
        self.max_tokens = original_max_tokens

        # Parse endpoints
        data = self._parse_json_response(text, "stage5", fallback=[])
        if not data:
            return []

        # Handle wrapped response
        if isinstance(data, dict) and "endpoints" in data:
            data = data["endpoints"]

        # Parse endpoints
        endpoints = []
        for item in data:
            try:
                endpoint = EfficacyEndpoint(**item)
                endpoints.append(endpoint)
            except Exception as e:
                logger.warning(f"Failed to parse efficacy endpoint: {e}")
                continue

        # Standardize endpoint names
        endpoints = self._standardize_endpoint_names(endpoints)

        return endpoints

    def _stage5b_extract_figures(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        indication: str
    ) -> List[EfficacyEndpoint]:
        """
        Stage 5b: Extract efficacy endpoints from figures using vision API.

        This stage:
        1. Extracts figure images from the PDF
        2. Filters for likely data figures (>200x200 pixels)
        3. Sends to Claude vision API for data extraction
        4. Parses JSON responses into EfficacyEndpoint objects
        5. Returns endpoints that match the current arm

        Token budget: ~1,500 input tokens (image) + ~4,000 output tokens per figure
        """
        if not PYMUPDF_AVAILABLE:
            logger.warning("PyMuPDF not available - skipping figure extraction")
            return []

        # Get PDF path from paper metadata
        pdf_path = paper.get('metadata', {}).get('original_pdf')
        if not pdf_path or not Path(pdf_path).exists():
            logger.info("No PDF path available - skipping figure extraction")
            return []

        logger.info(f"Extracting figures from PDF: {pdf_path}")

        try:
            # Step 1: Extract figure images from PDF
            figures = self._extract_figure_images(pdf_path)

            if not figures:
                logger.info("No figures found in PDF")
                return []

            logger.info(f"Found {len(figures)} figure(s) in PDF")

            # Step 2: Extract figure captions from paper content
            figure_captions = self._extract_figure_captions(paper.get('content', ''))
            logger.info(f"Extracted {len(figure_captions)} figure captions from paper text")

            # Step 3: Filter figures by caption relevance (if enabled)
            if self.filter_figures_by_caption and figure_captions:
                logger.info(f"Filtering figures by caption relevance using LLM...")

                # Batch classify all captions at once
                relevant_figure_numbers = self._classify_figure_captions_batch(figure_captions)

                relevant_figures = []
                for i, figure in enumerate(figures, 1):
                    caption = figure_captions.get(f"Figure {i}") or figure_captions.get(f"Fig {i}") or figure_captions.get(f"Fig. {i}")

                    if i in relevant_figure_numbers:
                        logger.info(f"Figure {i} (page {figure['page']}): Efficacy figure ✓ - '{caption[:80] if caption else 'No caption'}...'")
                        figure['caption'] = caption
                        relevant_figures.append(figure)
                    else:
                        logger.info(f"Figure {i} (page {figure['page']}): Non-efficacy figure (skipped) - '{caption[:80] if caption else 'No caption'}...'")

                efficacy_figures = relevant_figures
                logger.info(f"Filtered to {len(efficacy_figures)}/{len(figures)} efficacy figures")
            else:
                # Fallback to vision-based classification if caption filtering disabled
                logger.info(f"Classifying figures using vision API...")
                efficacy_figures = []

                for i, figure in enumerate(figures, 1):
                    try:
                        is_efficacy = self._classify_figure(figure)

                        if is_efficacy:
                            logger.info(f"Figure {i} (page {figure['page']}): Efficacy figure ✓")
                            efficacy_figures.append(figure)
                        else:
                            logger.info(f"Figure {i} (page {figure['page']}): Non-efficacy figure (skipped)")

                    except Exception as e:
                        logger.warning(f"Failed to classify figure {i}: {e}, will attempt extraction anyway")
                        efficacy_figures.append(figure)  # Include if classification fails

                logger.info(f"Identified {len(efficacy_figures)}/{len(figures)} efficacy figures")

            if not efficacy_figures:
                logger.info("No efficacy figures identified")
                return []

            # Step 3: Extract data from efficacy figures only
            all_endpoints = []

            for i, figure in enumerate(efficacy_figures, 1):
                logger.info(f"Extracting data from efficacy figure {i}/{len(efficacy_figures)} (page {figure['page']})")

                try:
                    # Extract data from figure using vision API
                    figure_data = self._extract_data_from_figure(figure, arm, indication)

                    if figure_data:
                        logger.info(f"Extracted {len(figure_data)} data points from figure {i}")
                        all_endpoints.extend(figure_data)
                    else:
                        logger.info(f"No relevant data found in figure {i}")

                except Exception as e:
                    logger.warning(f"Failed to extract data from figure {i}: {e}")
                    continue

            # Step 3: Filter for endpoints matching current arm
            arm_endpoints = [
                ep for ep in all_endpoints
                if self._endpoint_matches_arm(ep, arm)
            ]

            logger.info(f"Found {len(arm_endpoints)} endpoints for arm '{arm.arm_name}' from figures")

            # Step 4: Standardize endpoint names
            logger.info(f"Standardizing endpoint names...")
            arm_endpoints = self._standardize_endpoint_names(arm_endpoints)

            return arm_endpoints

        except Exception as e:
            logger.error(f"Figure extraction failed: {e}")
            return []

    def _extract_figure_captions(self, paper_content: str) -> Dict[str, str]:
        """
        Extract figure captions from paper content.

        Looks for patterns like:
        - "Figure 1. Caption text..."
        - "Fig 1. Caption text..."
        - "Fig. 1: Caption text..."

        Returns:
            Dictionary mapping figure labels to captions
        """
        captions = {}

        # Pattern to match figure captions
        # Matches: "Figure 1.", "Fig 1:", "Fig. 1 -", etc.
        pattern = r'(Figure|Fig\.?)\s+(\d+[A-Z]?)[\.\:\-\s]+([^\n]+(?:\n(?![A-Z][a-z]+\s+\d+)[^\n]+)*)'

        matches = re.finditer(pattern, paper_content, re.IGNORECASE | re.MULTILINE)

        for match in matches:
            fig_type = match.group(1)  # "Figure" or "Fig"
            fig_num = match.group(2)   # "1", "2A", etc.
            caption = match.group(3).strip()

            # Normalize figure label
            fig_label = f"Figure {fig_num}"

            # Clean up caption (remove extra whitespace, limit length)
            caption = ' '.join(caption.split())
            caption = caption[:500]  # Limit to 500 chars

            captions[fig_label] = caption
            logger.debug(f"Extracted caption for {fig_label}: {caption[:80]}...")

        return captions

    def _classify_figure_captions_batch(self, figure_captions: Dict[str, str]) -> List[int]:
        """
        Classify figure captions to identify which contain efficacy data.

        Uses LLM to batch classify all captions at once, which is more accurate
        than keyword matching and more efficient than individual API calls.

        Args:
            figure_captions: Dictionary mapping figure labels to captions

        Returns:
            List of figure numbers that contain efficacy data (e.g., [3, 4])
        """
        if not figure_captions:
            return []

        # Build prompt with all captions
        captions_text = "\n".join([
            f"{label}: {caption}"
            for label, caption in figure_captions.items()
        ])

        prompt = f"""Analyze these figure captions from a clinical trial paper and identify which figures contain EFFICACY DATA.

EFFICACY DATA includes:
- Treatment response rates or clinical outcomes
- Endpoint results (e.g., ACR20, EASI-75, PASI-75, PGA scores, SRI-4, BICLA)
- Comparison of outcomes between treatment arms
- Time-course data showing clinical improvements
- Forest plots with treatment effects
- Kaplan-Meier curves for clinical endpoints

NON-EFFICACY DATA includes:
- Study design diagrams or schematics
- Patient flow diagrams (CONSORT, trial profile, disposition)
- Mechanism of action illustrations
- Molecular pathways or biological processes
- Pharmacokinetic curves or drug concentration data
- Safety data ONLY (adverse events without efficacy)

Figure captions:
{captions_text}

Return ONLY a JSON array of figure numbers that contain efficacy data.
For example: [1, 3, 4] or [] if none contain efficacy data.

Your response (JSON array only):"""

        try:
            # Call Claude with minimal tokens
            response = self.client.messages.create(
                model=self.model,
                max_tokens=50,  # Just need a short JSON array
                messages=[{"role": "user", "content": prompt}]
            )

            # Record API call (if metrics collector is available)
            if self._metrics_collector:
                self._metrics_collector.record_api_call(response)

            # Parse response
            response_text = response.content[0].text.strip()
            logger.debug(f"LLM response: {response_text}")

            # Strip markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            # Parse JSON array
            figure_numbers = json.loads(response_text)

            logger.info(f"LLM classified {len(figure_numbers)}/{len(figure_captions)} figures as efficacy figures: {figure_numbers}")
            return figure_numbers

        except Exception as e:
            logger.warning(f"Failed to classify figure captions with LLM: {e}, will process all figures")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            # Fallback: process all figures if classification fails
            return list(range(1, len(figure_captions) + 1))

    def _filter_tables_by_caption(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        """
        Filter tables using LLM-based caption classification.

        Similar to figure filtering, this uses Claude to identify which tables
        contain clinical data vs layout artifacts (references, headers, etc.).

        Args:
            paper: Paper dict with 'tables' list

        Returns:
            Updated paper dict with filtered tables
        """
        tables = paper.get('tables', [])
        if not tables:
            return paper

        logger.info(f"Filtering {len(tables)} tables by caption/content relevance...")

        # Build table descriptions for LLM
        table_descriptions = []
        for i, table in enumerate(tables, 1):
            label = table.get('label', f'Table {i}')
            content_preview = table.get('content', '')[:300]  # First 300 chars

            table_descriptions.append(f"{label}: {content_preview}")

        # Call LLM to classify tables
        relevant_table_labels = self._classify_table_captions_batch(table_descriptions)

        # Filter tables
        filtered_tables = []
        for table in tables:
            label = table.get('label', '')
            if label in relevant_table_labels:
                filtered_tables.append(table)
                logger.info(f"  ✓ Keeping: {label}")
            else:
                logger.info(f"  ✗ Filtering out: {label} (layout artifact)")

        paper['tables'] = filtered_tables
        logger.info(f"Table filtering complete: {len(filtered_tables)}/{len(tables)} tables kept")

        return paper

    def _classify_table_captions_batch(self, table_descriptions: List[str]) -> List[str]:
        """
        Classify table captions to identify which contain clinical data.

        Uses LLM to batch classify all table descriptions at once.

        Args:
            table_descriptions: List of strings with table label and content preview

        Returns:
            List of table labels that contain clinical data (e.g., ["Table I", "Table 2"])
        """
        if not table_descriptions:
            return []

        # Build prompt with all table descriptions
        tables_text = "\n\n".join([
            f"{i+1}. {desc}"
            for i, desc in enumerate(table_descriptions)
        ])

        prompt = f"""Analyze these tables from a clinical trial paper and identify which contain CLINICAL DATA.

CLINICAL DATA includes:
- Baseline patient characteristics (demographics, disease severity, prior medications)
- Efficacy endpoints (response rates, clinical outcomes, treatment effects)
- Safety data (adverse events, serious AEs, discontinuations)
- Patient disposition or enrollment data
- Statistical comparisons between treatment arms

LAYOUT ARTIFACTS (should be filtered out):
- Journal headers/footers with page numbers and journal names
- Two-column page layouts mistakenly detected as tables
- Reference lists or bibliographies
- Author affiliations or acknowledgments
- Figure captions or legends formatted as tables

Tables:
{tables_text}

Return ONLY a JSON array of table labels (e.g., "Table I", "Table 1", "Table 2A") that contain clinical data.
For example: ["Table I", "Table 2"] or [] if none contain clinical data.

Your response (JSON array only):"""

        try:
            # Call Claude with minimal tokens
            response = self.client.messages.create(
                model=self.model,
                max_tokens=100,  # Just need a short JSON array
                messages=[{"role": "user", "content": prompt}]
            )

            # Record API call (if metrics collector is available)
            if self._metrics_collector:
                self._metrics_collector.record_api_call(response)

            # Parse response
            response_text = response.content[0].text.strip()
            logger.debug(f"LLM response: {response_text}")

            # Strip markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            # Parse JSON array
            table_labels = json.loads(response_text)

            logger.info(f"LLM classified {len(table_labels)}/{len(table_descriptions)} tables as clinical data tables: {table_labels}")
            return table_labels

        except Exception as e:
            logger.warning(f"Failed to classify table captions with LLM: {e}, will keep all tables")
            import traceback
            logger.debug(f"Traceback: {traceback.format_exc()}")
            # Fallback: keep all tables if classification fails
            return [table.split(':')[0] for table in table_descriptions]

    def _extract_figure_images(self, pdf_path: str) -> List[Dict[str, Any]]:
        """
        Extract figure images from PDF.

        Returns list of dicts with:
        - page: Page number
        - image_data: Base64-encoded image
        - media_type: MIME type (image/jpeg, image/png)
        - width: Image width in pixels
        - height: Image height in pixels
        """
        figures = []

        try:
            doc = fitz.open(pdf_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images(full=True)

                for img_index, img in enumerate(image_list):
                    xref = img[0]

                    # Extract image
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    width = base_image["width"]
                    height = base_image["height"]
                    image_ext = base_image["ext"]

                    # Filter for likely figures (exclude logos/icons)
                    if width > MIN_FIGURE_WIDTH and height > MIN_FIGURE_HEIGHT:
                        # Encode as base64
                        image_data = base64.standard_b64encode(image_bytes).decode('utf-8')

                        # Determine media type
                        media_type_map = {
                            'png': 'image/png',
                            'jpg': 'image/jpeg',
                            'jpeg': 'image/jpeg'
                        }
                        media_type = media_type_map.get(image_ext, 'image/png')

                        figures.append({
                            'page': page_num + 1,
                            'index': img_index + 1,
                            'image_data': image_data,
                            'media_type': media_type,
                            'width': width,
                            'height': height
                        })

            doc.close()
            return figures

        except Exception as e:
            logger.error(f"Failed to extract figures from PDF: {e}")
            return []

    def _classify_figure(self, figure: Dict[str, Any]) -> bool:
        """
        Classify a figure to determine if it contains efficacy data.

        Uses Claude vision API with a lightweight prompt to identify:
        - Efficacy figures: Bar charts, line graphs with response rates/outcomes
        - Non-efficacy figures: Study design, patient flow, mechanism diagrams

        Returns True if figure likely contains efficacy data.

        Token budget: ~1,500 input tokens (image) + ~50 output tokens (yes/no)
        Cost: ~$0.015 per figure (half the cost of full extraction)
        """
        prompt = """Analyze this figure and determine if it contains EFFICACY DATA from a clinical trial.

EFFICACY DATA includes:
- Bar charts or line graphs showing treatment response rates
- Endpoint results (e.g., ACR20, EASI-75, SRI-4, BICLA)
- Comparison of outcomes between treatment arms
- Time-course data showing clinical improvements
- Forest plots with treatment effects

NON-EFFICACY DATA includes:
- Study design diagrams (patient flow, randomization)
- Mechanism of action illustrations
- Molecular pathways or biological processes
- Patient disposition flowcharts
- Pharmacokinetic curves
- Safety data only (adverse events without efficacy)

Answer with ONLY one word:
- "YES" if this figure contains efficacy data
- "NO" if this figure does not contain efficacy data

Your answer:"""

        try:
            # Call Claude vision API with minimal tokens
            response = self.client.messages.create(
                model=self.model,
                max_tokens=10,  # Just need "YES" or "NO"
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": figure['media_type'],
                                    "data": figure['image_data']
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            # Extract text response
            text = self._extract_text_response(response).strip().upper()

            # Parse response
            if "YES" in text:
                return True
            elif "NO" in text:
                return False
            else:
                # If unclear, default to True (attempt extraction)
                logger.warning(f"Unclear classification response: {text}, defaulting to True")
                return True

        except Exception as e:
            logger.error(f"Figure classification failed: {e}")
            # On error, default to True (attempt extraction)
            return True

    def _extract_data_from_figure(
        self,
        figure: Dict[str, Any],
        arm: TrialArm,
        indication: str
    ) -> List[EfficacyEndpoint]:
        """
        Extract efficacy data from a single figure using Claude vision API.

        Returns list of EfficacyEndpoint objects.
        """
        prompt = self._get_figure_extraction_prompt(indication)

        try:
            # Call Claude vision API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS_FIGURE,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": figure['media_type'],
                                    "data": figure['image_data']
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )

            # Extract text response
            text = self._extract_text_response(response)

            # Strip code blocks if present
            json_str = self._extract_json_from_text(text)
            if not json_str:
                logger.warning(f"Failed to extract JSON from figure extraction response")
                return []

            # Parse JSON
            data = json.loads(json_str)

            # Check for error response
            if "error" in data:
                logger.info(f"Figure extraction returned error: {data['error']}")
                return []

            # Parse data points into EfficacyEndpoint objects
            endpoints = []
            for dp in data.get('data_points', []):
                try:
                    # Convert statistical significance markers to boolean
                    stat_sig_str = dp.get('statistical_significance', '')
                    stat_sig = self._parse_stat_sig(stat_sig_str)

                    # Map figure data to EfficacyEndpoint schema
                    # Store treatment_arm temporarily for filtering

                    # Determine field mapping based on unit type
                    unit = dp.get('unit', '%')
                    value = dp.get('value')

                    # Initialize all fields as None
                    responders_pct = None
                    responders_n = None
                    mean_value = None

                    # Map value based on unit type
                    if unit == '%':
                        # Percentage data → responder data
                        responders_pct = value
                        responders_n = dp.get('sample_size_n')
                    elif 'per patient' in unit.lower() or 'events' in unit.lower() or '/PY' in unit:
                        # Event rate data → mean_value (NOT responders_n!)
                        mean_value = value
                        responders_n = None  # Do NOT use sample_size_n for event counts
                    else:
                        # Other continuous data → mean_value
                        mean_value = value

                    endpoint = EfficacyEndpoint(
                        endpoint_name=dp.get('endpoint_name', ''),
                        endpoint_category=dp.get('endpoint_category', 'Additional'),
                        timepoint=dp.get('timepoint', ''),
                        timepoint_weeks=self._parse_timepoint_weeks(dp.get('timepoint', '')),
                        responders_pct=responders_pct,
                        responders_n=responders_n,
                        mean_value=mean_value,
                        n_evaluated=dp.get('sample_size_total'),
                        stat_sig=stat_sig,
                        p_value=stat_sig_str if stat_sig_str and not stat_sig_str.startswith('*') else None,
                        endpoint_unit=unit,
                        analysis_type='Response Rate' if unit == '%' else 'Mean Change',
                        is_standard_endpoint=False,  # Figure data is typically exploratory
                        source_table=f"Figure (page {figure['page']})"
                    )

                    # Attach treatment_arm as temporary attribute for filtering
                    endpoint._treatment_arm = dp.get('treatment_arm', '')

                    endpoints.append(endpoint)
                except Exception as e:
                    logger.warning(f"Failed to parse figure data point: {e}")
                    continue

            return endpoints

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse figure extraction response as JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"Figure extraction API call failed: {e}")
            return []

    def _endpoint_matches_arm(self, endpoint: EfficacyEndpoint, arm: TrialArm) -> bool:
        """
        Check if an endpoint belongs to the current arm.

        Uses fuzzy matching to handle variations in arm naming between
        the database and figure labels.
        """
        # Get treatment arm from temporary attribute
        if not hasattr(endpoint, '_treatment_arm'):
            logger.warning("Endpoint missing _treatment_arm attribute")
            return False

        figure_arm = endpoint._treatment_arm.lower().strip()
        db_arm = arm.arm_name.lower().strip()

        # Exact match
        if figure_arm == db_arm:
            return True

        # Fuzzy matching for common variations
        # Example: "ABBV-599 high dose" vs "ABBV-599 High Dose"
        if figure_arm.replace('-', '').replace(' ', '') == db_arm.replace('-', '').replace(' ', ''):
            return True

        # Check if one contains the other (for partial matches)
        # Example: "Upadacitinib 30 mg" vs "Upadacitinib 30 mg once daily"
        if figure_arm in db_arm or db_arm in figure_arm:
            return True

        return False

    def _parse_timepoint_weeks(self, timepoint: str) -> Optional[int]:
        """Parse timepoint string to extract weeks (e.g., 'Week 24' -> 24)."""
        match = re.search(r'week\s*(\d+)', timepoint, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _parse_stat_sig(self, stat_sig_str: str) -> Optional[bool]:
        """
        Parse statistical significance string to boolean.

        Handles:
        - Asterisks: *, **, *** -> True
        - P-values: p<0.05, P=0.001 -> True if p<0.05
        - Empty string -> None
        """
        if not stat_sig_str or stat_sig_str.strip() == '':
            return None

        # Check for asterisks (any number means significant)
        if '*' in stat_sig_str:
            return True

        # Check for p-values
        p_match = re.search(r'[pP]\s*[=<]\s*([\d.]+)', stat_sig_str)
        if p_match:
            p_value = float(p_match.group(1))
            return p_value < 0.05

        return None

    def _standardize_endpoint_names(self, endpoints: List[EfficacyEndpoint]) -> List[EfficacyEndpoint]:
        """
        Standardize endpoint names to canonical forms for easier filtering and analysis.

        Handles variations like:
        - "SRI-4 and glucocorticoid dose ≤10 mg/day QD"
        - "SRI-4 response and glucocorticoid dose ≤10 mg QD"
        - "SRI-4 response with glucocorticoid dose ≤10 mg QD"
        → All become: "SRI-4 and glucocorticoid dose ≤10 mg QD"

        Also handles:
        - Removing redundant words like "response", "achievement"
        - Standardizing symbols (≤, <=, ≥, >=)
        - Normalizing spacing and capitalization
        - Removing trailing "QD" variations
        """
        standardization_rules = [
            # Normalize dose units FIRST (before other rules)
            # mg/day, mg/d, mg per day → mg QD (QD = once daily = per day)
            (r'mg/day', 'mg QD', re.IGNORECASE),
            (r'mg/d(?!\w)', 'mg QD', re.IGNORECASE),  # mg/d but not mg/dL
            (r'mg\s+per\s+day', 'mg QD', re.IGNORECASE),

            # SLE-specific endpoints
            (r'SRI-4\s+response\s+(and|with)\s+glucocorticoid', 'SRI-4 and glucocorticoid', re.IGNORECASE),
            (r'SRI-4\s+(and|with)\s+glucocorticoid\s+dose\s*[≤<=]\s*10\s*mg\s+QD', 'SRI-4 and glucocorticoid dose ≤10 mg QD', re.IGNORECASE),
            (r'BICLA\s+response', 'BICLA', re.IGNORECASE),
            (r'LLDAS\s+achievement', 'LLDAS', re.IGNORECASE),
            (r'LLDAS\s+attainment', 'LLDAS', re.IGNORECASE),

            # General endpoint standardization
            (r'\s+response\s+rate', '', re.IGNORECASE),  # Remove "response rate"
            (r'\s+achievement', '', re.IGNORECASE),  # Remove "achievement"
            (r'\s+attainment', '', re.IGNORECASE),  # Remove "attainment"

            # Standardize symbols
            (r'<=', '≤', 0),
            (r'>=', '≥', 0),

            # Normalize spacing around symbols
            (r'\s*≤\s*', ' ≤', 0),
            (r'\s*≥\s*', ' ≥', 0),
            (r'\s*[<>]\s*', ' ', 0),

            # Remove multiple spaces
            (r'\s+', ' ', 0),
        ]

        standardized_count = 0

        for endpoint in endpoints:
            original_name = endpoint.endpoint_name
            standardized_name = original_name.strip()

            # Apply standardization rules
            for pattern, replacement, flags in standardization_rules:
                if flags:
                    standardized_name = re.sub(pattern, replacement, standardized_name, flags=flags)
                else:
                    standardized_name = re.sub(pattern, replacement, standardized_name)

            # Final cleanup
            standardized_name = standardized_name.strip()

            # Update endpoint if changed
            if standardized_name != original_name:
                logger.debug(f"Standardized: '{original_name}' → '{standardized_name}'")
                endpoint.endpoint_name = standardized_name
                standardized_count += 1

        if standardized_count > 0:
            logger.info(f"Standardized {standardized_count} endpoint names")

        return endpoints

    def _stage6_extract_safety(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        safety_tables: List[str]
    ) -> List[SafetyEndpoint]:
        """
        Stage 6: Extract safety endpoints.

        Straightforward extraction of AEs and SAEs.
        No extended thinking needed.

        Token budget: ~12,000 output tokens
        """
        # FALLBACK: If Stage 1 identified wrong tables, search for safety tables by content
        actual_safety_tables = self._find_safety_tables_by_content(paper, arm)
        if actual_safety_tables:
            logger.info(f"Found safety tables by content: {actual_safety_tables}")
            safety_tables = actual_safety_tables
        else:
            logger.info(f"Using Stage 1 identified safety tables: {safety_tables}")

        prompt = self._get_stage6_prompt(paper, arm, safety_tables)

        # Increase token limit for large safety tables
        original_max_tokens = self.max_tokens
        self.max_tokens = MAX_TOKENS_SAFETY

        # Build system message with paper content for caching
        paper_content = paper.get('content', '')
        system_message = f"""You are a clinical trial data extraction specialist.

PAPER CONTENT:
{paper_content[:50000]}"""

        response = self._call_claude(prompt, system=system_message, enable_caching=True)
        text = self._extract_text_response(response)

        # Restore token limit
        self.max_tokens = original_max_tokens

        # Parse safety endpoints
        data = self._parse_json_response(text, "stage6", fallback=[])
        if not data:
            return []

        # Handle wrapped response
        if isinstance(data, dict) and "endpoints" in data:
            data = data["endpoints"]

        # Parse endpoints
        endpoints = []
        for item in data:
            try:
                endpoint = SafetyEndpoint(**item)
                endpoints.append(endpoint)
            except Exception as e:
                logger.warning(f"Failed to parse safety endpoint: {e}")
                continue

        return endpoints

    def _find_safety_tables_by_content(
        self,
        paper: Dict[str, Any],
        arm: TrialArm
    ) -> List[str]:
        """
        Find safety tables by analyzing content.

        Looks for tables with:
        1. Column headers matching (N = X) format
        2. Rows with adverse event keywords
        3. Numeric data in cells
        4. Proper table structure (not text paragraphs)

        Returns list of table labels that likely contain safety data.
        """
        import re

        candidates = []

        # Safety keywords to look for in event names
        safety_keywords = [
            'adverse event',
            'serious adverse',
            'herpes zoster',
            'upper respiratory',
            'nasopharyngitis',
            'bronchitis',
            'infection',
            'discontinuation'
        ]

        for table in paper.get('tables', []):
            label = table.get('label', '')
            content = table.get('content', '')

            if not content:
                continue

            # Check if table has (N = X) format headers
            has_n_format = f'(N = {arm.n})' in content or f'(N={arm.n})' in content

            # Check if table has safety keywords
            safety_keyword_count = sum(1 for kw in safety_keywords if kw.lower() in content.lower())

            # Check if table has numeric data (counts and percentages)
            # Look for patterns like "153 (84.1)" or "2 (1.1)"
            numeric_pattern = r'\d+\s*\(\d+\.\d+\)'
            numeric_matches = len(re.findall(numeric_pattern, content))

            # Check for proper table structure
            # Count rows with pipe separators (markdown table format)
            lines = content.split('\n')
            table_rows = [l for l in lines if l.strip() and '|' in l and not l.startswith('|:')]

            # Check if first line looks like a header with "Event" column
            has_event_header = any('Event' in line or 'event' in line for line in lines[:3])

            # Penalize tables with very long text blocks (likely narrative text, not data tables)
            # Count lines with more than 60 characters without pipe separators
            long_text_lines = sum(1 for l in lines if len(l) > 60 and '|' not in l)

            # Check for data density: ratio of numeric matches to table rows
            # Good data tables have high density (most rows have numbers)
            data_density = numeric_matches / max(len(table_rows), 1)

            # Prefer compact tables (20-40 rows) over very large tables (>50 rows)
            # Large tables are often narrative text or poorly extracted
            size_penalty = 0
            if len(table_rows) > 50:
                size_penalty = (len(table_rows) - 50) * 0.5

            # Score the table
            score = 0
            if has_n_format:
                score += 10
            if has_event_header:
                score += 5
            score += safety_keyword_count * 2
            score += min(numeric_matches, 20)  # Cap at 20
            score += min(len(table_rows), 30)  # Prefer tables with more rows (up to 30)
            score += data_density * 10  # Reward high data density
            score -= long_text_lines * 2  # Penalize narrative text
            score -= size_penalty  # Penalize very large tables

            # If score is high enough, consider it a safety table
            if score >= 15:
                candidates.append({
                    'label': label,
                    'score': score,
                    'table_rows': len(table_rows),
                    'numeric_matches': numeric_matches
                })

        # Sort by score (highest first)
        candidates.sort(key=lambda x: x['score'], reverse=True)

        # Log candidates
        for c in candidates[:3]:
            logger.info(f"Safety table candidate: {c['label']} (score: {c['score']}, rows: {c['table_rows']}, numeric: {c['numeric_matches']})")

        # Return top 2 table labels
        return [c['label'] for c in candidates[:2]]

    def _validate_extraction(
        self,
        extraction: ClinicalTrialExtraction
    ) -> ExtractionValidationResult:
        """
        Validate extraction quality with extended thinking.

        Checks clinical plausibility and data completeness.

        Token budget: ~2,000 thinking tokens
        """
        prompt = self._get_validation_prompt(extraction)

        response = self._call_claude_with_thinking(
            prompt,
            thinking_budget=THINKING_BUDGET_VALIDATION
        )

        text = self._extract_text_response(response)

        # Parse validation result
        data = self._parse_json_response(text, "validation", fallback=None)
        if data:
            try:
                return ExtractionValidationResult(**data)
            except Exception as e:
                logger.error(f"Failed to create ExtractionValidationResult: {e}")

        # Return failed validation if parsing failed
        return ExtractionValidationResult(
            is_valid=False,
            issues=["Validation parsing failed"],
            warnings=[]
        )

    def _call_claude(
        self,
        prompt: str,
        system: Optional[str] = None,
        tools: Optional[list] = None,
        max_retries: int = 3,
        enable_caching: bool = False
    ):
        """
        Override base agent's _call_claude to record metrics.

        Args:
            prompt: User prompt/question
            system: System prompt (uses get_system_prompt() if not provided)
            tools: Optional list of tool definitions for tool use
            max_retries: Maximum number of retries for transient errors
            enable_caching: Whether to enable prompt caching for system message

        Returns:
            Claude API response
        """
        response = super()._call_claude(prompt, system, tools, max_retries, enable_caching)

        # Record metrics if collector is available
        if self._metrics_collector:
            self._metrics_collector.record_api_call(response)

        return response

    @with_retry(max_retries=MAX_RETRIES, base_delay=RETRY_BASE_DELAY)
    def _call_claude_with_thinking(
        self,
        prompt: str,
        thinking_budget: int = THINKING_BUDGET_SECTIONS,
        system_message: Optional[str] = None,
        enable_caching: bool = True
    ):
        """
        Call Claude with extended thinking enabled.

        Args:
            prompt: User prompt
            thinking_budget: Maximum thinking tokens
            system_message: Optional system message (will be cached if enable_caching=True)
            enable_caching: Whether to enable prompt caching for system message

        Returns:
            Claude API response with thinking content
        """
        # Ensure max_tokens > thinking_budget_tokens (API requirement)
        # Add buffer to allow for output tokens beyond thinking tokens
        required_max_tokens = thinking_budget + MAX_TOKENS_DEFAULT

        # Build API call parameters
        api_params = {
            "model": self.model,
            "max_tokens": required_max_tokens,
            "thinking": {
                "type": "enabled",
                "budget_tokens": thinking_budget
            },
            "messages": [{
                "role": "user",
                "content": prompt
            }]
        }

        # Add system message with caching if provided
        if system_message:
            if enable_caching:
                # Use cache_control to cache the system message
                api_params["system"] = [
                    {
                        "type": "text",
                        "text": system_message,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
            else:
                # Simple system message without caching
                api_params["system"] = system_message

        response = self.client.messages.create(**api_params)

        # Record metrics if collector is available
        if self._metrics_collector:
            self._metrics_collector.record_api_call(response)

        return response

    def _validate_inputs(
        self,
        paper: Dict[str, Any],
        nct_id: str,
        drug_name: str,
        indication: str
    ) -> tuple[Dict[str, Any], str, str]:
        """
        Validate required inputs for extraction.

        Handles both traditional papers (with 'content') and PaperScope v2 papers
        (which may need full-text download).

        Args:
            paper: Paper content dict (traditional or PaperScope v2 format)
            nct_id: ClinicalTrials.gov NCT ID (may be PMID_xxx, will search paper for real NCT)
            drug_name: Drug brand name
            indication: Disease indication (may be None or "Unknown")

        Returns:
            Tuple of (validated paper dict, validated indication string, validated nct_id string)

        Raises:
            ValueError: If any required input is missing or invalid
        """
        # Validate paper
        if not paper:
            raise ValueError("Paper content is required")

        # Check if paper needs conversion from PaperScope v2 format
        if not paper.get('content'):
            logger.info("Paper missing 'content' field - attempting PaperScope v2 conversion")

            # Check if it's a PaperScope v2 paper (has abstract or detailed_summary)
            if paper.get('abstract') or paper.get('detailed_summary'):
                logger.info("Detected PaperScope v2 paper - converting to clinical extractor format")
                try:
                    paper = self._paperscope_adapter.convert_paper(
                        paper,
                        download_full_text=True
                    )
                    logger.info("Successfully converted PaperScope v2 paper")
                except Exception as e:
                    raise ValueError(f"Failed to convert PaperScope v2 paper: {e}")
            else:
                raise ValueError("Paper must have 'content' field or be a valid PaperScope v2 paper")

        # Validate NCT ID
        if not nct_id:
            raise ValueError("NCT ID is required")

        # If NCT ID doesn't start with 'NCT', try to find it in the paper content
        original_nct_id = nct_id
        if not nct_id.startswith('NCT'):
            content = paper.get('content') or ''

            # Search for NCT ID in paper content (search first 10000 chars to cover intro/methods)
            import re
            nct_pattern = r'NCT\d{8}'
            matches = re.findall(nct_pattern, content[:10000])  # Search first 10000 chars

            if matches:
                # Found NCT ID in paper - use it!
                nct_id = matches[0]
                logger.info(f"Found NCT ID in paper content: {nct_id} (original identifier: {original_nct_id})")
            else:
                # No NCT ID found in paper
                if len(content) < 5000:
                    raise ValueError(
                        f"Cannot extract clinical data: Paper identifier '{nct_id}' is not a valid NCT ID, "
                        f"and paper has insufficient content (likely abstract-only). "
                        f"Please upload the full PDF for this paper to enable extraction."
                    )
                else:
                    # Has substantial content but no NCT ID - likely a review/meta-analysis
                    raise ValueError(
                        f"Cannot extract clinical data: Paper identifier '{nct_id}' is not a valid NCT ID. "
                        f"This paper may be a review, meta-analysis, or mechanistic study without a clinical trial registration. "
                        f"Clinical data extraction requires papers with NCT IDs (registered clinical trials)."
                    )

        # Validate drug name
        if not drug_name:
            raise ValueError("Drug name is required")

        # Validate indication - try to infer from paper if missing
        if not indication or indication == "Unknown":
            # Try to get indication from structured_summary
            structured = paper.get('structured_summary')
            if structured:
                if isinstance(structured, str):
                    try:
                        import json
                        structured = json.loads(structured)
                    except:
                        structured = {}
                if isinstance(structured, dict):
                    inferred_indication = structured.get('indication')
                    if inferred_indication and inferred_indication != 'Unknown':
                        indication = inferred_indication
                        logger.info(f"Inferred indication from paper: {indication}")

            # If still no indication, raise error
            if not indication or indication == "Unknown":
                raise ValueError(
                    "Indication is required but not provided and could not be inferred from paper. "
                    "Please specify the disease indication for this trial."
                )

        # Log validation success
        logger.info(
            f"Input validation passed",
            extra={
                "nct_id": nct_id,
                "drug_name": drug_name,
                "indication": indication,
                "content_length": len(paper.get('content', ''))
            }
        )

        return paper, indication, nct_id

    def _parse_json_response(
        self,
        text: str,
        stage: str,
        fallback: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Centralized JSON parsing with consistent error handling.

        Args:
            text: Raw response text from Claude
            stage: Stage identifier for logging (e.g., "stage1", "stage5")
            fallback: Optional fallback value if parsing fails

        Returns:
            Parsed JSON dict or fallback value
        """
        # Attempt 1: Direct parsing
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.debug(f"Stage {stage}: Direct JSON parsing failed: {e}")

        # Attempt 2: Extract from markdown code blocks
        json_str = self._extract_json_from_text(text)
        if json_str:
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"Stage {stage}: JSON extraction failed after fix attempt: {e}"
                )

        # Log failure with context
        logger.error(
            f"Stage {stage}: All JSON parsing attempts failed",
            extra={
                "response_preview": text[:500],
                "response_length": len(text)
            }
        )

        return fallback

    def _format_tables_for_prompt(self, paper: Dict[str, Any], table_names: List[str]) -> str:
        """
        Format table content for inclusion in prompts.

        Args:
            paper: Paper dictionary with 'tables' array
            table_names: List of table names to include (e.g., ["Table 1", "Table 2"])

        Returns:
            Formatted string with table content
        """
        tables = paper.get('tables', [])
        if not tables:
            return "No tables found in paper."

        formatted_tables = []

        for table_name in table_names:
            # Find matching table
            for table in tables:
                table_label = table.get('label', '').lower()
                table_caption = str(table.get('content', ''))[:200].lower()

                # Match by label or by finding table name in content
                if (table_name.lower() in table_label or
                    table_name.lower() in table_caption):

                    content = table.get('content', '')
                    if content:
                        formatted_tables.append(f"\n{'='*80}\n{table_name.upper()}\n{'='*80}\n{content}\n")
                        break

        if not formatted_tables:
            # If no tables matched, include first table (likely baseline)
            first_table = tables[0]
            content = first_table.get('content', '')
            if content:
                formatted_tables.append(f"\n{'='*80}\nBASELINE TABLE\n{'='*80}\n{content}\n")

        return '\n'.join(formatted_tables) if formatted_tables else "No matching tables found."

    def _extract_json_from_text(self, text: str) -> Optional[str]:
        """Extract JSON from text that may contain markdown code blocks."""
        # Try markdown code block first
        code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if code_block_match:
            json_content = code_block_match.group(1).strip()
            if json_content.startswith('{') or json_content.startswith('['):
                # Try to fix incomplete JSON
                json_content = self._fix_incomplete_json(json_content)
                return json_content

        # Try to find JSON object
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            json_content = match.group(0)
            # Try to fix incomplete JSON
            json_content = self._fix_incomplete_json(json_content)
            return json_content

        # Try to find JSON array
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            json_content = match.group(0)
            # Try to fix incomplete JSON
            json_content = self._fix_incomplete_json(json_content)
            return json_content

        return None

    def _fix_incomplete_json(self, json_str: str) -> str:
        """
        Attempt to fix incomplete JSON by closing unclosed structures.

        Handles cases where Claude's response was cut off mid-JSON.
        """
        # Step 1: Fix incomplete values at the end
        # Replace incomplete values like: "key": n with "key": null
        json_str = re.sub(r':\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*([,\}\]])', r': null\2', json_str)

        # Step 2: Remove any trailing incomplete text after the last complete value
        # Find the last complete closing bracket/brace and truncate there
        last_close_brace = json_str.rfind('}')
        last_close_bracket = json_str.rfind(']')
        last_close = max(last_close_brace, last_close_bracket)

        if last_close > 0:
            # Find any trailing garbage after the last close
            trailing = json_str[last_close + 1:].strip()
            if trailing and not trailing.startswith('}') and not trailing.startswith(']'):
                json_str = json_str[:last_close + 1]

        # Step 3: Count braces and brackets to close unclosed structures
        open_braces = json_str.count('{') - json_str.count('}')
        open_brackets = json_str.count('[') - json_str.count(']')

        # Step 4: Close any unclosed structures
        json_str += '}' * open_braces
        json_str += ']' * open_brackets

        return json_str

    def _calculate_confidence(self, validation: ExtractionValidationResult) -> float:
        """Calculate overall confidence score from validation."""
        if not validation.is_valid:
            return 0.5  # Low confidence if validation failed

        # Start with baseline
        confidence = 0.6

        # Boost for data completeness
        if validation.has_baseline_data:
            confidence += 0.1
        if validation.has_efficacy_data:
            confidence += 0.1
        if validation.has_safety_data:
            confidence += 0.1

        # Boost for completeness
        confidence += (validation.baseline_completeness_pct / 100) * 0.1

        # Cap at 1.0
        return min(confidence, 1.0)

    def _get_trial_name_from_database(self, nct_id: str) -> Optional[str]:
        """
        Get trial name from trial_summaries database.

        The trial name was already extracted during landscape discovery phase
        and stored in the database. This method retrieves it.

        Args:
            nct_id: NCT ID to look up

        Returns:
            Trial name if found in database, None otherwise
        """
        try:
            from src.tools.trial_summary_database import TrialSummaryDatabase
            from src.utils.config import get_settings

            # Get database URL from settings
            settings = get_settings()
            database_url = settings.drug_database_url or settings.paper_catalog_url

            if not database_url:
                logger.warning("No database URL configured - cannot retrieve trial name")
                return None

            # Initialize database connection
            db = TrialSummaryDatabase(database_url)
            db.connect()

            try:
                # Query trial_summaries table for trial_name
                with db.connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT trial_name FROM trial_summaries WHERE nct_id = %s",
                        (nct_id,)
                    )
                    result = cursor.fetchone()

                    if result and result[0]:
                        return result[0]
                    else:
                        logger.warning(f"No trial name found in database for NCT ID: {nct_id}")
                        return None
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error retrieving trial name from database: {e}")
            return None

    def _validate_nct_id(self, paper: Dict[str, Any], provided_nct_id: str) -> str:
        """
        Validate NCT ID by searching for it in the paper content.

        Args:
            paper: Paper content dict
            provided_nct_id: NCT ID provided by caller (may be PMID_xxx or PAPER_xxx format)

        Returns:
            Validated NCT ID (either provided or found in paper)

        Raises:
            ValueError: If provided NCT ID is invalid and no NCT ID found in paper
        """
        import re

        content = paper.get('content') or ''  # Handle None content

        # Search for NCT IDs in first 5000 characters (abstract/intro)
        nct_pattern = r'NCT\d{8}'
        matches = re.findall(nct_pattern, content[:CONTENT_TRUNCATION_SHORT])

        if matches:
            found_nct = matches[0]  # Use first occurrence

            # If provided ID is not a valid NCT format (e.g., PMID_xxx), use found NCT
            if not re.match(r'^NCT\d{8}$', provided_nct_id):
                logger.info(
                    f"Provided ID '{provided_nct_id}' is not a valid NCT format. "
                    f"Using NCT ID found in paper: {found_nct}"
                )
                return found_nct

            if found_nct != provided_nct_id:
                logger.warning(
                    f"NCT ID mismatch: provided={provided_nct_id}, found in paper={found_nct}. "
                    f"Using paper NCT ID: {found_nct}"
                )
                return found_nct
        else:
            # No NCT ID found in paper
            if not re.match(r'^NCT\d{8}$', provided_nct_id):
                # Provided ID is not valid NCT format (e.g., PMID_xxx, PAPER_xxx)
                # For papers without full-text content, we can't extract clinical data
                if not content or len(content) < 1000:
                    raise ValueError(
                        f"Cannot extract clinical data: Paper has no full-text content and no NCT ID found. "
                        f"Please upload the full PDF for this paper to enable extraction."
                    )
                else:
                    # Has content but no NCT ID found
                    raise ValueError(
                        f"Invalid NCT ID format: {provided_nct_id}. Must start with 'NCT' followed by 8 digits. "
                        f"No NCT ID found in paper content either."
                    )
            logger.warning(f"No NCT ID found in paper content. Using provided: {provided_nct_id}")

        # If no NCT found in paper or it matches, use provided ID
        return provided_nct_id

    def _extract_generic_name(self, paper: Dict[str, Any], drug_name: str) -> Optional[str]:
        """Extract generic drug name from paper."""
        # TODO: Extract from paper or lookup in drug database
        return None

    def _extract_phase(self, paper: Dict[str, Any]) -> Optional[str]:
        """Extract trial phase from paper."""
        content = paper.get('content', '')
        # Look for "Phase 2", "Phase 3", etc.
        import re
        match = re.search(r'Phase\s+([123])', content[:2000], re.IGNORECASE)
        if match:
            return f"Phase {match.group(1)}"
        return None

    def _validate_and_filter_tables(
        self,
        paper: Dict[str, Any],
        drug_name: str,
        indication: str
    ) -> Dict[str, Any]:
        """
        Validate extracted tables and filter out false positives.

        Uses TableValidationAgent to distinguish real clinical data tables
        from text extraction errors.

        Args:
            paper: Paper dict with 'tables' field
            drug_name: Drug name for context
            indication: Indication for context

        Returns:
            Updated paper dict with validated tables
        """
        try:
            from src.agents.table_validation_agent import TableValidationAgent

            tables = paper.get('tables', [])
            if not tables:
                logger.info("No tables to validate")
                return paper

            logger.info(f"Validating {len(tables)} extracted tables")

            # Initialize validator
            validator = TableValidationAgent(self.client)

            # Validate tables
            paper_context = {
                'title': paper.get('title', ''),
                'drug': drug_name,
                'indication': indication
            }

            validated_tables = validator.validate_tables(tables, paper_context)

            # Get summary
            summary = validator.get_validation_summary(validated_tables)

            logger.info(f"Table validation complete: {summary['total_valid_tables']} valid tables")
            logger.info(f"Table types: {summary['by_type']}")
            logger.info(f"Average confidence: {summary['average_confidence']:.2f}")

            # Update paper with validated tables
            paper['tables'] = validated_tables
            paper['table_validation_summary'] = summary

            return paper

        except Exception as e:
            logger.warning(f"Table validation failed: {e}")
            # Return paper unchanged if validation fails
            return paper

    def get_system_prompt(self) -> str:
        """Return system prompt for clinical data extraction."""
        return """You are an expert clinical trial data analyst specializing in extracting
structured data from scientific publications.

Your role is to extract comprehensive clinical trial data including:
- Baseline patient characteristics (demographics, prior medications, disease-specific biomarkers)
- Efficacy endpoints (primary, secondary, exploratory)
- Safety endpoints (AEs, SAEs, discontinuations)

Key principles:
1. Extract exact quantitative values, not approximations
2. Preserve units and statistical measures
3. Link data to specific trial arms
4. Note table/figure references for all data
5. Distinguish between standard and disease-specific endpoints

Always output valid JSON in the requested format."""

    # ==================== PROMPT METHODS ====================
    # These will be implemented next...

    def _get_stage1_prompt(self, paper: Dict[str, Any], nct_id: str, indication: str) -> str:
        """Generate Stage 1 prompt for section identification."""
        return self._prompts.render(
            "clinical_extraction/stage1_sections",
            nct_id=nct_id,
            indication=indication,
            paper_content=paper.get('content', '')
        )

    def _get_stage2_prompt(self, paper: Dict[str, Any], arm: TrialArm, tables: List[str]) -> str:
        """Generate Stage 2 prompt for demographics extraction."""
        # Get table content from tables array
        table_content = self._format_tables_for_prompt(paper, tables)

        return self._prompts.render(
            "clinical_extraction/stage2_demographics",
            arm_name=arm.arm_name,
            n=arm.n,
            tables=tables,
            table_content=table_content,
            paper_content=paper.get('content', '')
        )

    def _get_stage3_prompt(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        tables: List[str],
        indication: str
    ) -> str:
        """Generate Stage 3 prompt for prior medications extraction."""
        return self._prompts.render(
            "clinical_extraction/stage3_medications",
            arm_name=arm.arm_name,
            indication=indication,
            tables=tables,
            paper_content=paper.get('content', '')
        )

    def _get_stage4_prompt(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        tables: List[str],
        indication: str
    ) -> str:
        """Generate Stage 4 prompt for disease-specific baseline."""
        return self._prompts.render(
            "clinical_extraction/stage4_disease_baseline",
            arm_name=arm.arm_name,
            indication=indication,
            tables=tables,
            paper_content=paper.get('content', '')
        )

    def _get_stage5_prompt(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        tables: List[str],
        standard_endpoints: Optional[List[str]],
        indication: str
    ) -> str:
        """Generate Stage 5 prompt for efficacy endpoints."""
        # Get table content from tables array
        table_content = self._format_tables_for_prompt(paper, tables)

        return self._prompts.render(
            "clinical_extraction/stage5_efficacy",
            arm_name=arm.arm_name,
            indication=indication,
            tables=tables,
            standard_endpoints=standard_endpoints,
            table_content=table_content,
            paper_content=paper.get('content', '')
        )

    def _get_figure_extraction_prompt(self, indication: str) -> str:
        """Generate prompt for figure extraction using vision API."""
        return f"""You are analyzing a figure from a clinical trial paper for {indication}.

Extract ALL numerical data from this figure into structured JSON format.

🚨🚨🚨 CRITICAL WARNING - EVENT RATE DATA 🚨🚨🚨

IF the figure shows EVENT RATES (e.g., "Flares per patient-year", "Infections per patient-year"):
- The figure may show BOTH a rate (e.g., "1.7") AND an event count (e.g., "51 events")
- Extract the RATE value (e.g., 1.7) → put in "value" field
- Set "unit" to "events per patient-year" or similar
- DO NOT extract the event count (e.g., 51) as "sample_size_n"
- Event counts are NOT patient counts!

Example: Figure shows "Overall Flares: 1.7 per patient-year (51 events/PY)"
→ value: 1.7 (the RATE, not 51!)
→ unit: "events per patient-year"
→ sample_size_n: null (51 is event count, not patient count!)

🚨🚨🚨 END CRITICAL WARNING 🚨🚨🚨

For each data series/bar/point, extract:
- endpoint_name: Name of the endpoint/outcome measure (e.g., "SRI-4", "BICLA", "Overall Flares")
- endpoint_category: Category (e.g., "Primary", "Secondary", "Additional")
- treatment_arm: Name of the treatment group (e.g., "ABBV-599 high dose", "Upadacitinib 30 mg", "Placebo")
- timepoint: Time point (e.g., "Week 24", "Week 48")
- value: Numerical value (response rate %, mean change, event rate, etc.)
- sample_size_n: Number of responders if shown (e.g., from "37/68" extract 37) - BUT NOT for event counts!
- sample_size_total: Total sample size if shown (e.g., from "37/68" extract 68)
- statistical_significance: Any significance markers (*, **, ***) or p-values
- unit: Unit of measurement (%, mg/dL, events per patient-year, etc.)

CRITICAL INSTRUCTIONS:
- Extract ONLY data that is clearly visible in the figure
- DO NOT fabricate or estimate values
- If you cannot read a value clearly, omit that data point
- Include ALL treatment arms shown in the figure
- Preserve exact numerical values as shown
- For event rate data: Extract the RATE, NOT the event count!

Return ONLY valid JSON in this format (NO code blocks, NO markdown):
{{
  "figure_title": "extracted title from figure",
  "data_points": [
    {{
      "endpoint_name": "...",
      "endpoint_category": "Primary|Secondary|Additional",
      "treatment_arm": "...",
      "timepoint": "...",
      "value": 0.0,
      "sample_size_n": 0,
      "sample_size_total": 0,
      "statistical_significance": "...",
      "unit": "..."
    }}
  ]
}}

If you cannot extract data from this image, return:
{{"error": "reason why data cannot be extracted"}}

DO NOT wrap the JSON in code blocks. Return raw JSON only."""

    def _get_stage6_prompt(
        self,
        paper: Dict[str, Any],
        arm: TrialArm,
        tables: List[str]
    ) -> str:
        """Generate Stage 6 prompt for safety endpoints."""
        # Get table content from tables array
        table_content = self._format_tables_for_prompt(paper, tables)

        return self._prompts.render(
            "clinical_extraction/stage6_safety",
            arm_name=arm.arm_name,
            n=arm.n,
            tables=tables,
            table_content=table_content,
            paper_content=paper.get('content', '')
        )

    def _get_validation_prompt(self, extraction: ClinicalTrialExtraction) -> str:
        """Generate validation prompt."""
        extraction_json = extraction.model_dump_json(indent=2)

        return f"""Validate the clinical trial data extraction for quality and plausibility.

EXTRACTION:
{extraction_json}

INSTRUCTIONS:
Check for:
1. Data completeness (baseline, efficacy, safety all present?)
2. Clinical plausibility (demographics in expected ranges? efficacy results reasonable?)
3. Missing critical fields
4. Statistical inconsistencies

OUTPUT FORMAT:
{{
  "is_valid": true/false,
  "issues": ["Critical issue 1", ...],
  "warnings": ["Non-critical warning 1", ...],
  "has_baseline_data": true/false,
  "has_efficacy_data": true/false,
  "has_safety_data": true/false,
  "baseline_completeness_pct": 75.0,
  "efficacy_endpoint_count": 12,
  "safety_endpoint_count": 15,
  "demographics_plausible": true/false,
  "efficacy_plausible": true/false
}}

IMPORTANT NOTES:
- ALL boolean fields MUST be true or false, NEVER null
- If demographics are missing, set demographics_plausible=false (not null)
- If efficacy data is missing, set efficacy_plausible=false (not null)

CRITICAL: Return ONLY the raw JSON object. Do NOT wrap it in ```json``` code blocks.
Do NOT include any markdown formatting. Return pure JSON only.
If the JSON is too long, truncate the "issues" and "warnings" arrays but keep the JSON valid."""

    def _stage0_extract_trial_design(
        self,
        paper: Dict[str, Any],
        nct_id: str,
        indication: str,
        trial_name: Optional[str] = None
    ) -> TrialDesignMetadata:
        """
        Stage 0: Extract trial design metadata.

        Extracts trial-level information including study design, enrollment criteria,
        and key trial parameters. This is extracted once per trial (not per arm).

        No extended thinking needed - straightforward extraction from methods section.

        Token budget: ~4,000 output tokens

        Args:
            paper: Paper content dict
            nct_id: NCT ID
            indication: Disease indication
            trial_name: Optional trial name/acronym extracted from paper
        """
        prompt = self._get_stage0_prompt(paper, nct_id, indication)

        # Use higher token limit for comprehensive trial design
        original_max_tokens = self.max_tokens
        self.max_tokens = MAX_TOKENS_TRIAL_DESIGN

        # Build system message with paper content for caching
        paper_content = paper.get('content', '')
        system_message = f"""You are a clinical trial data extraction specialist.

PAPER CONTENT:
{paper_content[:50000]}"""

        response = self._call_claude(prompt, system=system_message, enable_caching=True)
        text = self._extract_text_response(response)

        # Restore token limit
        self.max_tokens = original_max_tokens

        # Parse JSON response (strip markdown code blocks first)
        json_str = self._extract_json_from_text(text)
        if not json_str:
            logger.error(f"Failed to extract JSON from Stage 0 response. First 1000 chars: {text[:1000]}")
            # Return minimal trial design
            return TrialDesignMetadata(
                nct_id=nct_id,
                indication=indication,
                study_design="Unknown",
                trial_design_summary="Failed to extract trial design",
                enrollment_summary="Unknown",
                inclusion_criteria=[],
                exclusion_criteria=[],
                primary_endpoint_description="Unknown",
                secondary_endpoints_summary="Unknown"
            )

        try:
            data = json.loads(json_str)
            # Override trial_name if we extracted it
            if trial_name:
                data['trial_name'] = trial_name
            trial_design = TrialDesignMetadata(**data)
            return trial_design
        except Exception as e:
            logger.error(f"JSON parsing failed in Stage 0: {e}")
            logger.error(f"Extracted JSON string: {json_str[:500]}")

            logger.error(f"Failed to parse Stage 0 response. First 1000 chars: {text[:1000]}")
            # Return minimal trial design
            return TrialDesignMetadata(
                nct_id=nct_id,
                indication=indication,
                trial_name=trial_name,  # Include trial_name if available
                trial_design_summary="Failed to extract trial design",
                enrollment_summary="Failed to extract enrollment criteria",
                extraction_confidence=0.0,
                extraction_notes="Extraction parsing failed"
            )

    def _get_stage0_prompt(self, paper: Dict[str, Any], nct_id: str, indication: str) -> str:
        """Generate Stage 0 prompt for trial design extraction."""
        return self._prompts.render(
            "clinical_extraction/stage0_trial_design",
            nct_id=nct_id,
            indication=indication,
            paper_title=paper.get('title', 'Unknown'),
            paper_authors=', '.join(paper.get('authors', ['Unknown'])),
            paper_content=paper.get('content', ''),
            paper_pmid=paper.get('pmid', ''),
            paper_doi=paper.get('doi', '')
        )

    def _trial_already_extracted(self, nct_id: str) -> bool:
        """
        Check if trial data already exists in database.

        Args:
            nct_id: NCT ID to check

        Returns:
            True if trial already extracted, False otherwise
        """
        try:
            from src.tools.clinical_extraction_database import ClinicalExtractionDatabase
            from src.utils.config import get_settings

            settings = get_settings()
            database_url = settings.drug_database_url or settings.paper_catalog_url

            if not database_url:
                logger.warning("No database URL configured - cannot check for duplicates")
                return False

            db = ClinicalExtractionDatabase(database_url)
            db.connect()

            try:
                with db.connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT COUNT(*) FROM clinical_trial_extractions WHERE nct_id = %s",
                        (nct_id,)
                    )
                    count = cursor.fetchone()[0]
                    return count > 0
            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error checking for duplicate extraction: {e}")
            return False

    def _normalize_dosing_regimen(self, dosing_regimen: str) -> str:
        """
        Normalize dosing regimen to prevent duplicates from capitalization.

        Args:
            dosing_regimen: Raw dosing regimen string

        Returns:
            Normalized dosing regimen
        """
        if not dosing_regimen:
            return dosing_regimen

        # Trim whitespace
        normalized = dosing_regimen.strip()

        # Remove double spaces
        while "  " in normalized:
            normalized = normalized.replace("  ", " ")

        # Capitalize first letter of each sentence/drug name consistently
        # Keep "mg", "Q2W", "QD" etc. in lowercase for consistency
        # This is a simple normalization - can be enhanced if needed

        return normalized
