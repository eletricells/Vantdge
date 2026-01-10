"""
Extraction Service

Extracts structured clinical data from case series papers.
Supports two extraction modes:
- Single-pass: For abstracts and short content
- Multi-stage: For full-text papers with extended thinking
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from src.case_series.models import (
    CaseSeriesExtraction,
    CaseSeriesSource,
    PatientPopulation,
    TreatmentDetails,
    EfficacyOutcome,
    SafetyOutcome,
    DetailedEfficacyEndpoint,
    DetailedSafetyEndpoint,
    EvidenceLevel,
    EfficacySignal,
    SafetyProfile,
    BiomarkerResult,
)
from src.case_series.protocols.llm_protocol import LLMClient
from src.case_series.protocols.search_protocol import PubMedSearcher
from src.case_series.protocols.database_protocol import CaseSeriesRepositoryProtocol
from src.case_series.services.drug_info_service import DrugInfo
from src.case_series.services.literature_search_service import Paper

logger = logging.getLogger(__name__)


def _parse_n_patients_from_response_rate(response_rate: Optional[str]) -> Optional[int]:
    """
    Extract n_patients from response_rate text like "10/12 (83%)" or "5/8".

    Args:
        response_rate: Text like "10/12 (83%)", "5/8", "3 of 5 patients"

    Returns:
        Extracted total patient count or None if not parseable
    """
    if not response_rate:
        return None

    # Pattern: "X/Y" where Y is the total
    match = re.search(r'(\d+)\s*/\s*(\d+)', response_rate)
    if match:
        return int(match.group(2))

    # Pattern: "X of Y patients"
    match = re.search(r'(\d+)\s+of\s+(\d+)', response_rate, re.IGNORECASE)
    if match:
        return int(match.group(2))

    # Pattern: "(Y patients)" or "Y patients total"
    match = re.search(r'(\d+)\s*patients?\s*(?:total)?', response_rate, re.IGNORECASE)
    if match:
        return int(match.group(1))

    return None


def _parse_n_patients_from_text(text: Optional[str]) -> Optional[int]:
    """
    Extract n_patients from free text like patient_description or efficacy_summary.

    Handles various patterns:
    - "10 patients with X were treated"
    - "a series of 15 patients"
    - "n=20 patients"
    - "enrolled 25 participants"

    Args:
        text: Free text that may contain patient counts

    Returns:
        Extracted patient count or None if not parseable
    """
    if not text:
        return None

    text_lower = text.lower()

    # Priority patterns (more specific first)
    patterns = [
        # "n=X" or "N=X" or "n = X"
        r'n\s*=\s*(\d+)',

        # "X patients" with various qualifiers
        r'(\d+)\s+patients?\s+(?:with|were|received|treated|enrolled|included|diagnosed)',

        # "series of X patients" or "cohort of X patients"
        r'(?:series|cohort|group)\s+of\s+(\d+)\s+patients?',

        # "enrolled X patients" or "included X patients" or "treated X patients"
        r'(?:enrolled|included|treated|studied|recruited)\s+(\d+)\s+(?:patients?|participants?|subjects?|cases?)',

        # "X consecutive patients"
        r'(\d+)\s+consecutive\s+patients?',

        # "total of X patients"
        r'total\s+of\s+(\d+)\s+patients?',

        # "X patients with" (at start of description)
        r'^(\d+)\s+patients?\s+with',

        # "among X patients"
        r'among\s+(\d+)\s+patients?',

        # "in X patients"
        r'in\s+(\d+)\s+patients?',

        # Fallback: any "X patients" pattern (less specific)
        r'(\d+)\s+patients?',
    ]

    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            n = int(match.group(1))
            # Sanity check: reasonable patient count (not years, percentages, etc.)
            if 1 <= n <= 10000:
                return n

    return None


def _detect_drug_survival_metric(
    primary_endpoint: Optional[str],
    efficacy_summary: Optional[str],
    response_rate: Optional[str],
) -> tuple[str, str]:
    """
    Detect if the metric is actually drug survival rather than efficacy response.

    Drug survival = % patients remaining on medication over time (NOT efficacy).

    Args:
        primary_endpoint: Primary endpoint description
        efficacy_summary: Efficacy summary text
        response_rate: Response rate text

    Returns:
        Tuple of (metric_type, confidence)
    """
    # Combine all text for pattern matching
    text_lower = ' '.join([
        str(primary_endpoint or ''),
        str(efficacy_summary or ''),
        str(response_rate or ''),
    ]).lower()

    # Drug survival patterns
    survival_patterns = [
        'drug survival',
        'drug retention',
        'treatment persistence',
        'medication persistence',
        'treatment continuation',
        'remained on',
        'still on treatment',
        'stayed on',
        'persistence rate',
        'retention rate',
        '-month survival',
        '-year survival',
        'survival rate',
    ]

    for pattern in survival_patterns:
        if pattern in text_lower:
            return ('Drug Survival', 'High')

    # Discontinuation patterns (inverse of survival)
    discontinuation_patterns = [
        'discontinuation rate',
        'discontinued treatment',
        'stopped treatment',
        'treatment discontinuation',
    ]

    for pattern in discontinuation_patterns:
        if pattern in text_lower:
            return ('Discontinuation', 'High')

    # Default - return None to indicate no override needed
    return (None, None)


def _infer_n_patients_from_responders(responders_n: Optional[int], responders_pct: Optional[float]) -> Optional[int]:
    """
    Infer total n_patients from responders_n and responders_pct.

    If we have 10 responders at 83.3%, total is 12.

    Args:
        responders_n: Number of responders
        responders_pct: Response percentage

    Returns:
        Inferred total patient count or None
    """
    if responders_n is not None and responders_pct is not None and responders_pct > 0:
        # n_total = responders_n / (responders_pct / 100)
        inferred = round(responders_n / (responders_pct / 100))
        # Sanity check: inferred should be >= responders_n
        if inferred >= responders_n:
            return inferred
    return None


def _validate_and_flag_broad_disease(disease: Optional[str]) -> tuple[bool, Optional[str]]:
    """
    Check if the extracted disease name is too broad/generic.

    Args:
        disease: Extracted disease name

    Returns:
        Tuple of (is_valid, warning_message)
    """
    if not disease:
        return False, "No disease extracted"

    disease_lower = disease.lower().strip()

    # List of overly broad disease names that should be flagged
    broad_disease_patterns = [
        'immune-related adverse event',
        'immune related adverse event',
        'adverse event',
        'side effect',
        'complication',
        'toxicity',
        'drug reaction',
        'hypersensitivity',
        'autoimmune disorder',  # Too broad - should specify which
        'inflammatory condition',  # Too broad
        'unknown',
        'not specified',
        'various',
        # More specific "multiple" patterns - NOT just 'multiple' alone
        # because "Multiple Sclerosis" is a specific disease
        'multiple conditions',
        'multiple diseases',
        'multiple indications',
        'multiple off-label',
        'multiple autoimmune',
        'multiple systemic',
        'multiple inflammatory',
        'multiple rheumatic',
        'multiple neurological',
    ]

    for pattern in broad_disease_patterns:
        if pattern in disease_lower:
            return False, f"Disease name too broad: '{disease}'. Should specify the specific condition."

    # Check for very short disease names that might be incomplete
    if len(disease) < 4:
        return False, f"Disease name too short: '{disease}'"

    return True, None


def _apply_extraction_fixes(extraction: 'CaseSeriesExtraction') -> 'CaseSeriesExtraction':
    """
    Apply post-processing fixes to an extraction.

    This function ensures that:
    1. n_patients is correctly inferred from response_rate when LLM extraction is wrong
    2. n_patients is parsed from patient_description or efficacy_summary as fallback
    3. metric_type is correctly classified (drug survival vs efficacy response)

    Args:
        extraction: The extraction to fix

    Returns:
        Fixed extraction (modified in place)
    """
    # Fix 1: Correct n_patients from response_rate
    if extraction.efficacy and extraction.efficacy.response_rate:
        n_patients_from_response = _parse_n_patients_from_response_rate(extraction.efficacy.response_rate)
        if n_patients_from_response and extraction.patient_population:
            current_n = extraction.patient_population.n_patients
            if current_n is None or (current_n != n_patients_from_response):
                logger.info(
                    f"Fixing n_patients: {current_n} -> {n_patients_from_response} "
                    f"(from response_rate='{extraction.efficacy.response_rate}')"
                )
                extraction.patient_population.n_patients = n_patients_from_response

    # Fix 2: Try inferring from responders if still None
    if extraction.patient_population and extraction.patient_population.n_patients is None:
        if extraction.efficacy:
            inferred = _infer_n_patients_from_responders(
                extraction.efficacy.responders_n,
                extraction.efficacy.responders_pct
            )
            if inferred:
                extraction.patient_population.n_patients = inferred
                logger.info(f"Inferred n_patients={inferred} from responders")

    # Fix 3: Parse n_patients from patient_description or efficacy_summary as fallback
    if extraction.patient_population and extraction.patient_population.n_patients is None:
        # Try patient_description first
        if extraction.patient_population.description:
            n_from_desc = _parse_n_patients_from_text(extraction.patient_population.description)
            if n_from_desc:
                extraction.patient_population.n_patients = n_from_desc
                logger.info(f"Parsed n_patients={n_from_desc} from patient_description")

        # Try efficacy_summary if still None
        if extraction.patient_population.n_patients is None and extraction.efficacy:
            if extraction.efficacy.efficacy_summary:
                n_from_eff = _parse_n_patients_from_text(extraction.efficacy.efficacy_summary)
                if n_from_eff:
                    extraction.patient_population.n_patients = n_from_eff
                    logger.info(f"Parsed n_patients={n_from_eff} from efficacy_summary")

            # Try key_findings as last resort
            if extraction.patient_population.n_patients is None and extraction.key_findings:
                n_from_findings = _parse_n_patients_from_text(extraction.key_findings)
                if n_from_findings:
                    extraction.patient_population.n_patients = n_from_findings
                    logger.info(f"Parsed n_patients={n_from_findings} from key_findings")

    # Fix 4: Correct metric_type for drug survival
    if extraction.efficacy:
        detected_type, detected_conf = _detect_drug_survival_metric(
            extraction.efficacy.primary_endpoint,
            extraction.efficacy.efficacy_summary,
            extraction.efficacy.response_rate
        )
        if detected_type and detected_type != extraction.efficacy.metric_type:
            logger.info(
                f"Fixing metric_type: {extraction.efficacy.metric_type} -> {detected_type} "
                f"(drug survival detected)"
            )
            extraction.efficacy.metric_type = detected_type
            extraction.efficacy.metric_type_confidence = detected_conf

    # Fix 5: Validate and warn about overly broad disease names
    is_valid_disease, disease_warning = _validate_and_flag_broad_disease(extraction.disease)
    if not is_valid_disease:
        # Build a useful identifier for the paper
        paper_id = 'Unknown'
        if extraction.source:
            if extraction.source.pmid:
                paper_id = f"PMID {extraction.source.pmid}"
            elif extraction.source.doi:
                paper_id = f"DOI {extraction.source.doi}"
            elif extraction.source.title:
                paper_id = f"'{extraction.source.title[:50]}...'"
        logger.warning(f"{paper_id}: {disease_warning}")
        # Store the warning in extraction confidence if available
        if extraction.extraction_confidence_detail:
            limiting_factors = extraction.extraction_confidence_detail.limiting_factors or []
            limiting_factors.append(disease_warning)
            extraction.extraction_confidence_detail.limiting_factors = limiting_factors

    # Fix 6: Infer response rate from efficacy summary if not extracted
    extraction = _infer_response_rate_from_efficacy(extraction)

    # Fix 7: Correct evidence_level based on study_design
    extraction = _fix_evidence_level(extraction)

    return extraction


def _fix_evidence_level(extraction: 'CaseSeriesExtraction') -> 'CaseSeriesExtraction':
    """
    Fix evidence_level based on study_design and content analysis.

    Many RCTs get misclassified as "Case Series" because the prompt options
    didn't include RCT. This function corrects that based on study_design
    and keyword analysis.

    Args:
        extraction: The extraction to fix

    Returns:
        Fixed extraction (modified in place)
    """
    # Map study_design to correct evidence_level
    DESIGN_TO_EVIDENCE = {
        'Randomized Controlled Trial': 'RCT',
        'Double-Blind RCT': 'RCT',
        'Open-Label RCT': 'RCT',
        'Prospective Controlled': 'Controlled Trial',
        'Prospective Open-Label': 'Prospective Cohort',
        'Retrospective': 'Retrospective Study',
        'Retrospective Study': 'Retrospective Study',
        'Case Series': 'Case Series',
        'Case Report': 'Case Report',
    }

    # RCT keywords to detect in title/content
    RCT_KEYWORDS = [
        'randomized', 'randomised', 'placebo-controlled', 'double-blind',
        'double blind', 'phase 2', 'phase 3', 'phase ii', 'phase iii',
        'rct', 'controlled trial'
    ]

    current_level = extraction.evidence_level.value if extraction.evidence_level else 'Case Series'
    study_design = extraction.study_design or ''

    # Check if study_design indicates RCT
    if study_design in DESIGN_TO_EVIDENCE:
        correct_level = DESIGN_TO_EVIDENCE[study_design]
        if correct_level != current_level:
            logger.info(
                f"Fixing evidence_level: {current_level} -> {correct_level} "
                f"(based on study_design='{study_design}')"
            )
            extraction.evidence_level = EvidenceLevel(correct_level)
            return extraction

    # If still Case Series, check for RCT keywords in title
    if current_level == 'Case Series':
        title = (extraction.source.title if extraction.source else '') or ''
        title_lower = title.lower()

        for keyword in RCT_KEYWORDS:
            if keyword in title_lower:
                logger.info(
                    f"Fixing evidence_level: Case Series -> RCT "
                    f"(detected keyword '{keyword}' in title)"
                )
                extraction.evidence_level = EvidenceLevel.RCT
                extraction.study_design = 'Randomized Controlled Trial'
                return extraction

    return extraction


def _infer_response_rate_from_efficacy(extraction: 'CaseSeriesExtraction') -> 'CaseSeriesExtraction':
    """
    Attempt to infer response rate from efficacy summary if not extracted.

    This catches cases where the LLM didn't extract a structured response_rate
    but the efficacy_summary contains the data.

    Args:
        extraction: The extraction to fix

    Returns:
        Fixed extraction (modified in place)
    """
    if not extraction.efficacy:
        return extraction

    # Skip if response_rate already populated
    if extraction.efficacy.response_rate is not None:
        return extraction

    # Skip if no efficacy summary to parse
    if not extraction.efficacy.efficacy_summary:
        return extraction

    text = extraction.efficacy.efficacy_summary.lower()

    # Patterns to extract response rate data
    patterns = [
        # "10 of 12 patients showed improvement" or "10/12 patients responded"
        (r'(\d+)\s*(?:of|/)\s*(\d+)\s*patients?\s*(?:showed|achieved|had|demonstrated|responded|improved)', 2),
        # "10 of 12 (83%) responded"
        (r'(\d+)\s*(?:of|/)\s*(\d+)\s*\(\s*\d+(?:\.\d+)?\s*%\s*\)', 2),
        # "83% of patients achieved response"
        (r'(\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?patients?\s*(?:achieved|showed|had|demonstrated|responded)', 1),
        # "response rate of 83%"
        (r'response\s+rate\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%', 1),
        # "10 patients out of 12 responded"
        (r'(\d+)\s*patients?\s*(?:out of|from)\s*(\d+)\s*(?:responded|achieved|showed)', 2),
        # "achieved response in 10/12"
        (r'(?:achieved|showed)\s+(?:response|improvement)\s+in\s+(\d+)\s*(?:/|of)\s*(\d+)', 2),
    ]

    for pattern, num_groups in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if num_groups == 2 and len(groups) >= 2:
                try:
                    responders = int(groups[0])
                    total = int(groups[1])
                    if total > 0:
                        pct = round(responders / total * 100, 1)
                        extraction.efficacy.response_rate = f"{responders}/{total} ({pct}%)"
                        extraction.efficacy.responders_n = responders
                        extraction.efficacy.responders_pct = pct
                        if extraction.patient_population and extraction.patient_population.n_patients is None:
                            extraction.patient_population.n_patients = total
                        logger.info(f"Inferred response_rate={extraction.efficacy.response_rate} from efficacy_summary")
                        return extraction
                except (ValueError, ZeroDivisionError):
                    continue
            elif num_groups == 1 and len(groups) >= 1:
                try:
                    pct = float(groups[0])
                    if 0 <= pct <= 100:
                        extraction.efficacy.responders_pct = pct
                        logger.info(f"Inferred responders_pct={pct}% from efficacy_summary")
                        return extraction
                except ValueError:
                    continue

    return extraction


# Multi-stage extraction token budgets
THINKING_BUDGET_SECTIONS = 3000
THINKING_BUDGET_EFFICACY = 4000
THINKING_BUDGET_SAFETY = 2000
MIN_FULLTEXT_LENGTH = 2000

# Cacheable system prompt for extraction (static instructions that can be reused)
EXTRACTION_SYSTEM_PROMPT = """You are an expert clinical data extraction assistant specializing in drug repurposing analysis.

Your task is to extract structured clinical data from case series and case reports. Focus on:
1. Patient population characteristics (sample size, demographics, disease severity)
2. Treatment details (dosing, duration, route of administration)
3. Efficacy outcomes (response rates, clinical improvements)
4. Safety data (adverse events, discontinuations)

Guidelines:
- Extract ONLY data explicitly stated in the source
- Use null for missing/unstated values, never infer or estimate
- Distinguish between primary and secondary endpoints
- Flag any potential biases or limitations in the data
- For response rates, prefer objective measures over subjective assessments

Output must be valid JSON matching the requested schema."""


def safe_parse_json(response: str, context: str = "") -> Optional[Dict]:
    """
    Safely parse JSON from LLM response, handling common issues.

    Handles:
    - Empty responses
    - Markdown code blocks (```json ... ```)
    - Extra whitespace
    - JSON with trailing commas
    """
    if not response or not response.strip():
        logger.warning(f"Empty LLM response{f' for {context}' if context else ''}")
        return None

    text = response.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        # Find the end of the first line (might be ```json or just ```)
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # Remove trailing ```
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    if not text:
        logger.warning(f"Empty JSON after stripping{f' for {context}' if context else ''}")
        return None

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to extract JSON from within the text
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # Try array pattern
        array_match = re.search(r'\[[\s\S]*\]', text)
        if array_match:
            try:
                return json.loads(array_match.group())
            except json.JSONDecodeError:
                pass

        logger.error(f"Failed to parse JSON{f' for {context}' if context else ''}: {e}")
        logger.debug(f"Response text: {text[:500]}...")
        return None


@dataclass
class ExtractionMetrics:
    """Token usage metrics for extraction."""
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class ExtractionService:
    """
    Service for extracting structured data from case series papers.

    Supports:
    - Single-pass extraction (abstracts, short content)
    - Multi-stage extraction (full-text with extended thinking)
    - Caching of extractions
    """

    def __init__(
        self,
        llm_client: LLMClient,
        pubmed_searcher: Optional[PubMedSearcher] = None,
        repository: Optional[CaseSeriesRepositoryProtocol] = None,
    ):
        """
        Initialize the extraction service.

        Args:
            llm_client: LLM client for extraction
            pubmed_searcher: PubMed searcher for full text retrieval
            repository: Optional repository for caching
        """
        self._llm_client = llm_client
        self._pubmed = pubmed_searcher
        self._repository = repository
        self._metrics = ExtractionMetrics()

    @property
    def metrics(self) -> ExtractionMetrics:
        """Get extraction metrics."""
        return self._metrics

    def reset_metrics(self) -> None:
        """Reset extraction metrics."""
        self._metrics = ExtractionMetrics()

    async def extract(
        self,
        paper: Paper,
        drug_info: DrugInfo,
        use_cache: bool = True,
    ) -> Optional[CaseSeriesExtraction]:
        """
        Extract structured data from a paper.

        Args:
            paper: Paper metadata
            drug_info: Drug information
            use_cache: Whether to check/use cache

        Returns:
            CaseSeriesExtraction or None if extraction failed
        """
        # Check cache
        if use_cache and self._repository and paper.pmid:
            cached = self._repository.load_extraction(drug_info.drug_name, paper.pmid)
            if cached:
                logger.info(f"Using cached extraction for {paper.pmid}")
                extraction = CaseSeriesExtraction(**cached)
                # Apply post-processing fixes to cached extractions
                return _apply_extraction_fixes(extraction)

        # Fetch full text if available
        full_text = None
        if paper.pmcid and self._pubmed:
            try:
                full_text = await self._pubmed.fetch_fulltext(paper.pmcid)
            except Exception as e:
                logger.warning(f"Failed to fetch full text for {paper.pmcid}: {e}")

        # Determine extraction method
        content = full_text or paper.abstract
        if full_text and len(full_text) >= MIN_FULLTEXT_LENGTH:
            extraction = await self._extract_multi_stage(paper, drug_info, full_text)
        else:
            extraction = await self._extract_single_pass(paper, drug_info, content)

        if extraction:
            # Derive summary from detailed endpoints (fixes summary/detail mismatch)
            extraction = self._derive_summary_from_detailed_endpoints(extraction)

            # Assess relevance
            extraction = self._assess_relevance(extraction, drug_info)

            # Apply post-processing fixes (n_patients parsing, metric type detection)
            extraction = _apply_extraction_fixes(extraction)

            # Save to cache (after fixes so cached data is correct)
            if self._repository and paper.pmid:
                self._repository.save_extraction(
                    drug_info.drug_name,
                    paper.pmid,
                    extraction.model_dump(),
                )

        return extraction

    async def _extract_single_pass(
        self,
        paper: Paper,
        drug_info: DrugInfo,
        content: str,
        is_full_text: bool = False,
    ) -> Optional[CaseSeriesExtraction]:
        """Single-pass extraction for abstracts and short content."""
        from src.case_series.prompts.extraction_prompts import build_main_extraction_prompt

        prompt = build_main_extraction_prompt(
            drug_name=drug_info.drug_name,
            drug_info=drug_info.to_dict(),
            paper_title=paper.title,
            paper_content=content,
            is_full_text=is_full_text,
        )

        try:
            response = await self._llm_client.complete(
                prompt,
                max_tokens=4000,
                system=EXTRACTION_SYSTEM_PROMPT,
                cache_system=True,  # Cache the system prompt for reuse across papers
            )
            data = safe_parse_json(response, f"single-pass {paper.pmid}")
            if data is None:
                logger.warning(f"No valid JSON in single-pass extraction for {paper.pmid}")
                return None

            return self._build_extraction(paper, drug_info, data, 'single_pass')

        except Exception as e:
            logger.error(f"Single-pass extraction failed for {paper.pmid}: {e}")
            return None

    async def _extract_multi_stage(
        self,
        paper: Paper,
        drug_info: DrugInfo,
        full_text: str,
    ) -> Optional[CaseSeriesExtraction]:
        """Multi-stage extraction with extended thinking."""
        from src.case_series.prompts.extraction_prompts import (
            build_section_identification_prompt,
            build_efficacy_extraction_prompt,
            build_safety_extraction_prompt,
        )

        stages_completed = []

        # Stage 1: Section identification
        try:
            section_prompt = build_section_identification_prompt(
                drug_name=drug_info.drug_name,
                paper_title=paper.title,
                paper_content=full_text,
            )

            response, thinking = await self._llm_client.complete_with_thinking(
                section_prompt,
                thinking_budget=THINKING_BUDGET_SECTIONS,
                system=EXTRACTION_SYSTEM_PROMPT,
                cache_system=True,
            )
            sections = safe_parse_json(response, f"sections {paper.pmid}") or {}
            if sections:
                stages_completed.append('section_identification')

        except Exception as e:
            logger.warning(f"Stage 1 failed for {paper.pmid}: {e}")
            sections = {}

        # Stage 2: Efficacy extraction
        efficacy_endpoints = []
        try:
            efficacy_prompt = build_efficacy_extraction_prompt(
                drug_name=drug_info.drug_name,
                drug_info=drug_info.to_dict(),
                paper_content=full_text,
                sections=sections,
            )

            response, thinking = await self._llm_client.complete_with_thinking(
                efficacy_prompt,
                thinking_budget=THINKING_BUDGET_EFFICACY,
                system=EXTRACTION_SYSTEM_PROMPT,
                cache_system=True,
            )
            efficacy_data = safe_parse_json(response, f"efficacy {paper.pmid}")
            if efficacy_data and isinstance(efficacy_data, list):
                efficacy_endpoints = efficacy_data
                stages_completed.append('efficacy_extraction')

        except Exception as e:
            logger.warning(f"Stage 2 failed for {paper.pmid}: {e}")

        # Stage 3: Safety extraction
        safety_endpoints = []
        try:
            safety_prompt = build_safety_extraction_prompt(
                drug_name=drug_info.drug_name,
                paper_content=full_text,
                sections=sections,
            )

            response, thinking = await self._llm_client.complete_with_thinking(
                safety_prompt,
                thinking_budget=THINKING_BUDGET_SAFETY,
                system=EXTRACTION_SYSTEM_PROMPT,
                cache_system=True,
            )
            safety_data = safe_parse_json(response, f"safety {paper.pmid}")
            if safety_data and isinstance(safety_data, list):
                safety_endpoints = safety_data
                stages_completed.append('safety_extraction')

        except Exception as e:
            logger.warning(f"Stage 3 failed for {paper.pmid}: {e}")

        # Build extraction from multi-stage results
        # Also run single-pass for basic fields
        basic_extraction = await self._extract_single_pass(paper, drug_info, full_text, is_full_text=True)

        if basic_extraction:
            # Add multi-stage data
            basic_extraction.extraction_method = 'multi_stage'
            basic_extraction.extraction_stages_completed = stages_completed
            basic_extraction.data_sections_identified = sections

            # Add detailed endpoints
            for ep_data in efficacy_endpoints:
                try:
                    ep = DetailedEfficacyEndpoint(**ep_data)
                    basic_extraction.detailed_efficacy_endpoints.append(ep)
                except Exception as e:
                    logger.debug(f"Failed to parse efficacy endpoint: {e}")

            for ep_data in safety_endpoints:
                try:
                    ep = DetailedSafetyEndpoint(**ep_data)
                    basic_extraction.detailed_safety_endpoints.append(ep)
                except Exception as e:
                    logger.debug(f"Failed to parse safety endpoint: {e}")

            return basic_extraction

        return None

    def _build_extraction(
        self,
        paper: Paper,
        drug_info: DrugInfo,
        data: Dict[str, Any],
        method: str,
    ) -> CaseSeriesExtraction:
        """Build CaseSeriesExtraction from extracted data.

        Handles both flat JSON structure (from main_extraction template) and
        nested structure (legacy format).
        """
        # Ensure authors is a string (Semantic Scholar returns list of dicts)
        authors_str = paper.authors
        if authors_str is not None and not isinstance(authors_str, str):
            if isinstance(authors_str, list):
                author_names = []
                for author in authors_str:
                    if isinstance(author, dict):
                        name = author.get('name', '')
                        if name:
                            author_names.append(name)
                    elif isinstance(author, str):
                        author_names.append(author)
                if len(author_names) > 5:
                    authors_str = ", ".join(author_names[:5]) + " et al."
                else:
                    authors_str = ", ".join(author_names)

        # Build source
        source = CaseSeriesSource(
            pmid=paper.pmid,
            doi=paper.doi,
            url=paper.url,
            title=paper.title or '',
            authors=authors_str,
            journal=paper.journal or data.get('journal'),
            year=paper.year or data.get('year'),
        )

        # Handle both flat and nested JSON structures
        # Flat: {"n_patients": 5, "dose": "100mg", ...}
        # Nested: {"patient_population": {"n_patients": 5}, "treatment": {"dose": "100mg"}, ...}

        # Get efficacy data first (needed for n_patients inference)
        eff_data = data.get('efficacy') or {}
        response_rate = eff_data.get('response_rate') or data.get('response_rate')
        responders_n = eff_data.get('responders_n') or data.get('responders_n')
        responders_pct = eff_data.get('responders_pct') or data.get('responders_pct')

        # Build patient population (check both flat and nested)
        pop_data = data.get('patient_population') or {}
        n_patients = pop_data.get('n_patients') or data.get('n_patients')
        n_patients_llm = n_patients  # Store LLM value for comparison

        # Always try to parse n_patients from response_rate (most reliable source)
        # Example: "10/12 (83%)" -> 12 patients
        n_patients_from_response = _parse_n_patients_from_response_rate(response_rate)

        # Validate and potentially override LLM extraction
        if n_patients_from_response:
            if n_patients is None:
                n_patients = n_patients_from_response
                logger.debug(f"Inferred n_patients={n_patients} from response_rate='{response_rate}'")
            elif n_patients != n_patients_from_response:
                # Sanity check: if parsed value is very small but LLM value is much larger,
                # the parser likely picked up a wrong number (e.g., "2 patients had AEs" vs N=1150)
                if n_patients_from_response < 10 and n_patients_llm > 50 and n_patients_llm > n_patients_from_response * 10:
                    logger.warning(
                        f"n_patients mismatch: LLM={n_patients_llm}, response_rate parse={n_patients_from_response}. "
                        f"Keeping LLM value (parsed value suspiciously small)."
                    )
                    # Keep LLM value - don't override
                else:
                    # LLM extracted a different value - response_rate is more reliable
                    logger.warning(
                        f"n_patients mismatch: LLM={n_patients_llm}, response_rate parse={n_patients_from_response}. "
                        f"Using response_rate value as more reliable."
                    )
                    n_patients = n_patients_from_response

        # If still None, try inferring from responders_n and responders_pct
        if n_patients is None:
            n_patients = _infer_n_patients_from_responders(responders_n, responders_pct)
            if n_patients:
                logger.debug(f"Inferred n_patients={n_patients} from responders_n={responders_n}, responders_pct={responders_pct}")

        # If still None, try parsing from various text fields and original abstract
        # This is the most robust fallback since LLM may not populate derived fields
        if n_patients is None:
            # Try patient_description from LLM
            patient_desc = pop_data.get('description') or data.get('patient_description')
            if patient_desc:
                n_patients = _parse_n_patients_from_text(patient_desc)
                if n_patients:
                    logger.info(f"Parsed n_patients={n_patients} from patient_description")

            # Try efficacy_summary
            if n_patients is None:
                eff_summary = eff_data.get('efficacy_summary') or data.get('efficacy_summary')
                if eff_summary:
                    n_patients = _parse_n_patients_from_text(eff_summary)
                    if n_patients:
                        logger.info(f"Parsed n_patients={n_patients} from efficacy_summary")

            # Try key_findings
            if n_patients is None:
                key_findings = data.get('key_findings')
                if key_findings:
                    n_patients = _parse_n_patients_from_text(key_findings)
                    if n_patients:
                        logger.info(f"Parsed n_patients={n_patients} from key_findings")

            # FINAL FALLBACK: Parse directly from original abstract
            # This is the most reliable since abstracts typically state "X patients with Y"
            if n_patients is None and paper.abstract:
                n_patients = _parse_n_patients_from_text(paper.abstract)
                if n_patients:
                    logger.info(f"Parsed n_patients={n_patients} from original abstract")

        patient_population = PatientPopulation(
            n_patients=n_patients,
            age_description=pop_data.get('age_description') or data.get('patient_description'),
            sex_distribution=pop_data.get('sex_distribution'),
            prior_treatments_failed=pop_data.get('prior_treatments_failed') or data.get('prior_treatments_failed'),
            disease_severity=pop_data.get('disease_severity'),
        )

        # Build treatment details (check both flat and nested)
        treatment_data = data.get('treatment') or {}
        treatment = TreatmentDetails(
            drug_name=drug_info.drug_name,
            generic_name=drug_info.generic_name,
            mechanism=drug_info.mechanism,
            target=drug_info.target,
            dose=treatment_data.get('dose') or data.get('dose'),
            frequency=treatment_data.get('frequency'),
            duration=treatment_data.get('duration') or data.get('duration'),
            route_of_administration=treatment_data.get('route') or data.get('route'),
        )

        # Build efficacy outcome
        metric_type = eff_data.get('metric_type') or data.get('metric_type') or 'Efficacy Response'
        metric_type_confidence = eff_data.get('metric_type_confidence') or data.get('metric_type_confidence') or 'Medium'

        # Post-process: detect drug survival metrics that LLM may have misclassified
        primary_endpoint = eff_data.get('primary_endpoint') or data.get('primary_endpoint')
        efficacy_summary = eff_data.get('efficacy_summary') or data.get('efficacy_summary')
        detected_type, detected_conf = _detect_drug_survival_metric(primary_endpoint, efficacy_summary, response_rate)
        if detected_type and detected_type != metric_type:
            logger.warning(
                f"Overriding metric_type: LLM={metric_type} -> detected={detected_type} "
                f"(based on keywords in endpoint/summary)"
            )
            metric_type = detected_type
            metric_type_confidence = detected_conf

        efficacy = EfficacyOutcome(
            response_rate=response_rate,
            responders_n=responders_n,
            responders_pct=responders_pct,
            metric_type=metric_type,
            metric_type_confidence=metric_type_confidence,
            primary_endpoint=primary_endpoint,
            endpoint_result=eff_data.get('endpoint_result') or data.get('endpoint_result'),
            efficacy_summary=eff_data.get('efficacy_summary') or data.get('efficacy_summary'),
        )

        # Build safety outcome (check both flat and nested)
        safety_data = data.get('safety') or {}
        safety = SafetyOutcome(
            adverse_events=safety_data.get('adverse_events') or data.get('adverse_events', []),
            serious_adverse_events=safety_data.get('serious_adverse_events') or data.get('serious_adverse_events', []),
            sae_count=safety_data.get('sae_count') or data.get('sae_count'),
            sae_percentage=safety_data.get('sae_percentage') or data.get('sae_percentage'),
            discontinuations_n=safety_data.get('discontinuations_n') or data.get('discontinuations_n'),
            safety_summary=safety_data.get('safety_summary') or data.get('safety_summary'),
        )

        # Determine efficacy signal (check both nested and flat)
        efficacy_signal = EfficacySignal.UNKNOWN
        signal_value = eff_data.get('efficacy_signal') or data.get('efficacy_signal')
        if signal_value:
            try:
                efficacy_signal = EfficacySignal(signal_value)
            except ValueError:
                pass

        # Determine safety profile (from flat structure)
        safety_profile = SafetyProfile.UNKNOWN
        safety_value = safety_data.get('safety_profile') or data.get('safety_profile')
        if safety_value:
            try:
                safety_profile = SafetyProfile(safety_value)
            except ValueError:
                pass

        # Determine evidence level (from flat structure)
        evidence_level = EvidenceLevel.CASE_SERIES
        evidence_value = data.get('evidence_level')
        if evidence_value:
            try:
                evidence_level = EvidenceLevel(evidence_value)
            except ValueError:
                pass

        # Parse biomarkers from LLM response
        biomarkers = []
        raw_biomarkers = data.get('biomarkers') or []
        for bm in raw_biomarkers:
            if isinstance(bm, dict) and bm.get('name'):
                try:
                    # Parse change_pct - handle both float and string
                    change_pct = bm.get('change_pct')
                    if isinstance(change_pct, str):
                        try:
                            change_pct = float(change_pct.replace('%', ''))
                        except ValueError:
                            change_pct = None

                    biomarkers.append(BiomarkerResult(
                        biomarker_name=bm.get('name'),
                        biomarker_category=bm.get('category'),
                        baseline_value=float(bm['baseline_value']) if bm.get('baseline_value') and str(bm['baseline_value']).replace('.', '').replace('-', '').isdigit() else None,
                        final_value=float(bm['final_value']) if bm.get('final_value') and str(bm['final_value']).replace('.', '').replace('-', '').isdigit() else None,
                        change_direction=bm.get('direction'),
                        change_pct=change_pct,
                        is_beneficial=bm.get('is_beneficial'),
                        p_value=bm.get('p_value'),
                        notes=bm.get('notes'),
                    ))
                    logger.info(f"Extracted biomarker: {bm.get('name')}")
                except Exception as e:
                    logger.warning(f"Failed to parse biomarker {bm}: {e}")

        return CaseSeriesExtraction(
            source=source,
            disease=data.get('disease') or '',  # Handles None explicitly
            disease_subtype=data.get('disease_subtype'),
            disease_category=data.get('disease_category'),
            is_off_label=data.get('is_off_label', True),
            is_relevant=data.get('is_relevant', True),
            evidence_level=evidence_level,
            patient_population=patient_population,
            treatment=treatment,
            efficacy=efficacy,
            safety=safety,
            efficacy_signal=efficacy_signal,
            safety_profile=safety_profile,
            follow_up_duration=data.get('follow_up_duration'),
            key_findings=data.get('key_findings'),
            extraction_method=method,
            # New fields for scoring
            study_design=data.get('study_design'),
            follow_up_weeks=data.get('follow_up_weeks'),
            response_definition_quality=data.get('response_definition_quality'),
            biomarkers=biomarkers,
        )

    # Common abbreviation mappings for indication matching
    INDICATION_ABBREVIATIONS = {
        'dlbcl': 'diffuse large b-cell lymphoma',
        'sle': 'systemic lupus erythematosus',
        'ra': 'rheumatoid arthritis',
        'uc': 'ulcerative colitis',
        'as': 'ankylosing spondylitis',
        'psa': 'psoriatic arthritis',
        'jia': 'juvenile idiopathic arthritis',
        'itp': 'immune thrombocytopenia',
        'ms': 'multiple sclerosis',
        'ibd': 'inflammatory bowel disease',
        'ad': 'atopic dermatitis',
        'aa': 'alopecia areata',
    }

    # Patterns indicating treatment failure (not a repurposing success)
    TREATMENT_FAILURE_PATTERNS = [
        r'\b(failed|failure|ineffective|no response|non-responder|refractory to)\b',
        r'\b(rescue|salvage)\s+therapy\b',
        r'\b(switched|transitioned)\s+(from|after)\s+\w+',
        r'\b(discontinued|stopped)\s+(due to|for|because of)\s+(lack of|inadequate|poor)\b',
        r'\bdid not respond\b',
        r'\btreatment[- ]?resistant\b',
        r'\bno (clinical )?(improvement|response|benefit)\b',
    ]

    def _detect_treatment_failure(
        self,
        extraction: CaseSeriesExtraction,
        drug_name: str
    ) -> bool:
        """
        Detect if the paper describes treatment failure rather than success.

        Args:
            extraction: The extraction to check
            drug_name: Name of the drug being analyzed

        Returns:
            True if the paper describes the drug failing, False otherwise
        """
        # Combine relevant text fields
        text_to_check = ' '.join(filter(None, [
            extraction.efficacy.efficacy_summary,
            extraction.key_findings,
            extraction.source.title if extraction.source else None,
        ])).lower()

        if not text_to_check:
            return False

        drug_lower = drug_name.lower()

        # Check each failure pattern
        for pattern in self.TREATMENT_FAILURE_PATTERNS:
            # Look for pattern near drug name (within ~100 chars)
            match = re.search(pattern, text_to_check, re.IGNORECASE)
            if match:
                # Check if drug name is nearby
                match_start = match.start()
                match_end = match.end()
                context_start = max(0, match_start - 100)
                context_end = min(len(text_to_check), match_end + 100)
                context = text_to_check[context_start:context_end]

                if drug_lower in context:
                    logger.info(f"Treatment failure detected for {drug_name}: '{match.group()}'")
                    return True

        # Also check if response rate is explicitly 0%
        if extraction.efficacy.responders_pct is not None and extraction.efficacy.responders_pct == 0:
            logger.info(f"Treatment failure detected for {drug_name}: 0% response rate")
            return True

        return False

    def _matches_approved_indication(
        self,
        disease: str,
        approved_indications: List[str]
    ) -> bool:
        """
        Check if disease matches any approved indication with fuzzy matching.

        Handles abbreviations and partial matches.

        Args:
            disease: The disease name from the extraction
            approved_indications: List of approved indication names

        Returns:
            True if the disease matches an approved indication
        """
        if not disease or not approved_indications:
            return False

        disease_lower = disease.lower().strip()

        # Expand abbreviations in disease
        disease_expanded = self.INDICATION_ABBREVIATIONS.get(disease_lower, disease_lower)

        for indication in approved_indications:
            ind_lower = indication.lower().strip()
            ind_expanded = self.INDICATION_ABBREVIATIONS.get(ind_lower, ind_lower)

            # Direct substring match
            if ind_lower in disease_lower or disease_lower in ind_lower:
                return True

            # Expanded abbreviation match
            if ind_expanded in disease_expanded or disease_expanded in ind_expanded:
                return True

            # Handle common variations (e.g., "b-cell" vs "b cell")
            disease_normalized = disease_lower.replace('-', ' ').replace('  ', ' ')
            ind_normalized = ind_lower.replace('-', ' ').replace('  ', ' ')
            if ind_normalized in disease_normalized or disease_normalized in ind_normalized:
                return True

        return False

    def _assess_relevance(
        self,
        extraction: CaseSeriesExtraction,
        drug_info: DrugInfo,
    ) -> CaseSeriesExtraction:
        """Assess if extraction is relevant for drug repurposing."""
        # Check if disease is an approved indication (improved matching)
        if self._matches_approved_indication(extraction.disease, drug_info.approved_indications):
            extraction.is_off_label = False
            extraction.is_relevant = False
            logger.debug(f"Marked as on-label: {extraction.disease}")

        # Check for treatment failure
        if extraction.is_relevant and self._detect_treatment_failure(extraction, drug_info.generic_name):
            extraction.is_relevant = False
            extraction.efficacy_signal = EfficacySignal.NONE
            logger.info(f"Marked as treatment failure: {extraction.source.pmid if extraction.source else 'unknown'}")

        # Check if extraction has meaningful clinical data
        has_clinical_data = (
            extraction.patient_population.n_patients is not None or
            extraction.efficacy.responders_pct is not None or
            extraction.efficacy.response_rate is not None or
            len(extraction.detailed_efficacy_endpoints) > 0
        )

        if not has_clinical_data:
            extraction.is_relevant = False

        return extraction

    def _derive_summary_from_detailed_endpoints(
        self,
        extraction: CaseSeriesExtraction,
    ) -> CaseSeriesExtraction:
        """
        Derive summary fields from detailed endpoints.

        This fixes the issue where detailed endpoints are populated
        but summary fields (efficacy_signal, response_rate, etc.) are empty.
        """
        if not extraction.detailed_efficacy_endpoints:
            return extraction

        endpoints = extraction.detailed_efficacy_endpoints

        # Find primary endpoint (or best secondary)
        primary_eps = [ep for ep in endpoints if ep.endpoint_category and ep.endpoint_category.lower() == 'primary']
        secondary_eps = [ep for ep in endpoints if ep.endpoint_category and ep.endpoint_category.lower() == 'secondary']

        # Use primary endpoint if available, otherwise secondary with best data
        if primary_eps:
            best_ep = primary_eps[0]
        elif secondary_eps:
            # Prefer endpoint with responders_pct
            eps_with_response = [ep for ep in secondary_eps if ep.responders_pct is not None]
            best_ep = eps_with_response[0] if eps_with_response else secondary_eps[0]
        else:
            # Use any endpoint with response data
            eps_with_response = [ep for ep in endpoints if ep.responders_pct is not None]
            best_ep = eps_with_response[0] if eps_with_response else endpoints[0]

        # Derive primary_endpoint if not set
        if not extraction.efficacy.primary_endpoint:
            extraction.efficacy.primary_endpoint = best_ep.endpoint_name

        # Derive response_rate if not set
        if extraction.efficacy.responders_pct is None and best_ep.responders_pct is not None:
            extraction.efficacy.responders_pct = best_ep.responders_pct
            if best_ep.responders_n is not None and best_ep.total_n is not None:
                extraction.efficacy.responders_n = best_ep.responders_n
                extraction.efficacy.response_rate = f"{best_ep.responders_n}/{best_ep.total_n} ({best_ep.responders_pct:.0f}%)"

        # Derive efficacy_signal if not set or unknown
        if extraction.efficacy_signal == EfficacySignal.UNKNOWN:
            extraction.efficacy_signal = self._calculate_efficacy_signal(endpoints)

        # Build efficacy_summary if not set
        if not extraction.efficacy.efficacy_summary:
            extraction.efficacy.efficacy_summary = self._build_efficacy_summary(endpoints, extraction)

        return extraction

    def _calculate_efficacy_signal(
        self,
        endpoints: List[DetailedEfficacyEndpoint],
    ) -> EfficacySignal:
        """Calculate overall efficacy signal from endpoints."""
        if not endpoints:
            return EfficacySignal.UNKNOWN

        # Collect all response rates
        response_rates = []
        for ep in endpoints:
            if ep.responders_pct is not None:
                response_rates.append(ep.responders_pct)
            elif ep.change_pct is not None:
                # Convert change % to pseudo response rate
                # Negative change in most scores = improvement
                ep_name = (ep.endpoint_name or '').lower()
                if any(kw in ep_name for kw in ['response', 'remission', 'acr', 'pasi', 'easi', 'salt']):
                    # Increase is good
                    response_rates.append(max(0, ep.change_pct))
                else:
                    # Decrease is good (disease activity scores)
                    response_rates.append(max(0, -ep.change_pct))

        if not response_rates:
            # No quantitative data, check for any positive signal
            has_stat_sig = any(ep.statistical_significance for ep in endpoints)
            if has_stat_sig:
                return EfficacySignal.MODERATE
            return EfficacySignal.UNKNOWN

        avg_response = sum(response_rates) / len(response_rates)

        if avg_response >= 70:
            return EfficacySignal.STRONG
        elif avg_response >= 40:
            return EfficacySignal.MODERATE
        elif avg_response >= 20:
            return EfficacySignal.WEAK
        else:
            return EfficacySignal.NONE

    def _build_efficacy_summary(
        self,
        endpoints: List[DetailedEfficacyEndpoint],
        extraction: CaseSeriesExtraction,
    ) -> str:
        """Build a summary from detailed endpoints."""
        parts = []
        n_patients = extraction.patient_population.n_patients

        # Find best response data
        best_response = None
        for ep in endpoints:
            if ep.responders_pct is not None:
                if best_response is None or ep.responders_pct > best_response['pct']:
                    best_response = {
                        'name': ep.endpoint_name,
                        'pct': ep.responders_pct,
                        'n': ep.responders_n,
                        'total': ep.total_n,
                    }

        if best_response:
            if n_patients:
                parts.append(f"{best_response['pct']:.0f}% response rate ({best_response['name']}) in {n_patients} patients.")
            else:
                parts.append(f"{best_response['pct']:.0f}% achieved {best_response['name']}.")

        # Add change from baseline info
        changes = []
        for ep in endpoints:
            if ep.change_pct is not None and abs(ep.change_pct) > 20:
                direction = "improved" if ep.change_pct < 0 else "increased"
                changes.append(f"{ep.endpoint_name} {direction} by {abs(ep.change_pct):.0f}%")

        if changes:
            parts.append(" ".join(changes[:2]) + ".")

        # Add statistical significance
        sig_endpoints = [ep.endpoint_name for ep in endpoints if ep.statistical_significance and ep.p_value]
        if sig_endpoints:
            parts.append(f"Statistical significance reached for {', '.join(sig_endpoints[:2])}.")

        return " ".join(parts) if parts else "Efficacy outcomes extracted from detailed endpoints."

    async def extract_batch(
        self,
        papers: List[Paper],
        drug_info: DrugInfo,
        use_cache: bool = True,
        max_concurrent: int = 5,
        on_extraction_complete: Optional[Any] = None,
    ) -> List[CaseSeriesExtraction]:
        """
        Extract data from multiple papers.

        Args:
            papers: List of papers to extract
            drug_info: Drug information
            use_cache: Whether to use cache
            max_concurrent: Max concurrent extractions
            on_extraction_complete: Optional callback called after each extraction.
                                   Signature: callback(extraction: CaseSeriesExtraction, drug_name: str)
                                   Used for saving to database immediately (like V2 agent).

        Returns:
            List of successful extractions
        """
        import asyncio

        extractions = []
        semaphore = asyncio.Semaphore(max_concurrent)
        lock = asyncio.Lock()  # Lock for thread-safe callback invocation

        async def extract_with_limit(paper: Paper, index: int):
            async with semaphore:
                # Check cache first to avoid rate limiting for cached results
                if use_cache and self._repository and paper.pmid:
                    cached = self._repository.load_extraction(drug_info.drug_name, paper.pmid)
                    if cached:
                        logger.debug(f"Using cached extraction for {paper.pmid}")
                        extraction = CaseSeriesExtraction(**cached)
                        # Still call the callback for cached extractions
                        if on_extraction_complete:
                            async with lock:
                                try:
                                    on_extraction_complete(extraction, drug_info.drug_name)
                                except Exception as e:
                                    logger.warning(f"Callback failed for cached extraction: {e}")
                        return extraction

                result = await self.extract(paper, drug_info, use_cache=False)  # Already checked cache

                # Save immediately via callback (like V2 agent)
                if result and on_extraction_complete:
                    async with lock:
                        try:
                            on_extraction_complete(result, drug_info.drug_name)
                            logger.debug(f"Saved extraction for PMID {result.source.pmid if result.source else 'N/A'}")
                        except Exception as e:
                            logger.warning(f"Callback failed for extraction: {e}")

                # Rate limiting only for actual API calls (0.5s like original agent)
                if index < len(papers) - 1:
                    await asyncio.sleep(0.5)
                return result

        tasks = [extract_with_limit(paper, i) for i, paper in enumerate(papers)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, CaseSeriesExtraction):
                extractions.append(result)
            elif isinstance(result, Exception):
                logger.warning(f"Extraction failed: {result}")

        return extractions


async def extract_n_from_abstract_with_haiku(
    abstract: str,
    drug_name: str,
    llm_client: LLMClient,
) -> Dict[str, Any]:
    """
    Extract patient count and key efficacy info from abstract using Haiku.

    Used for papers that passed filters but couldn't get full text.
    This is a lightweight extraction to help prioritize manual review.

    Args:
        abstract: Paper abstract text
        drug_name: Drug being analyzed
        llm_client: LLM client (will use Haiku model)

    Returns:
        Dict with:
            - n_patients: int or None
            - n_confidence: "High", "Medium", "Low"
            - response_rate: str or None (e.g., "80%", "5/6")
            - primary_endpoint: str or None
            - efficacy_mention: str (brief summary of efficacy mentioned)
    """
    if not abstract or len(abstract.strip()) < 50:
        return {
            "n_patients": None,
            "n_confidence": "Unknown",
            "response_rate": None,
            "primary_endpoint": None,
            "efficacy_mention": None,
        }

    prompt = f"""Extract key clinical information from this abstract about {drug_name}.

Abstract:
{abstract[:2000]}

Extract ONLY what is explicitly stated. Return JSON:
{{
    "n_patients": <integer or null if not stated>,
    "n_confidence": "High" if exact number stated, "Medium" if range/approximate, "Low" if inferred,
    "response_rate": "<X/Y>" or "<X%>" format if stated, null otherwise,
    "primary_endpoint": "endpoint name" if stated, null otherwise,
    "efficacy_mention": "One sentence summary of efficacy findings" or null
}}

JSON only, no explanation:"""

    try:
        # Use Haiku for fast, cheap extraction
        response = await llm_client.complete(
            prompt,
            max_tokens=300,
            model="claude-3-5-haiku-latest",  # Fast and cheap
        )

        result = safe_parse_json(response, "haiku_n_extraction")
        if result:
            return {
                "n_patients": result.get("n_patients"),
                "n_confidence": result.get("n_confidence", "Unknown"),
                "response_rate": result.get("response_rate"),
                "primary_endpoint": result.get("primary_endpoint"),
                "efficacy_mention": result.get("efficacy_mention"),
            }
    except Exception as e:
        logger.warning(f"Haiku extraction failed: {e}")

    # Fallback: try regex parsing
    n_patients = _parse_n_patients_from_text(abstract)
    response_rate = None

    # Try to find response rate pattern in abstract
    import re
    rate_match = re.search(r'(\d+)\s*/\s*(\d+)\s*(?:patients?)?\s*(?:\((\d+(?:\.\d+)?%)\))?', abstract)
    if rate_match:
        response_rate = f"{rate_match.group(1)}/{rate_match.group(2)}"
        if rate_match.group(3):
            response_rate += f" ({rate_match.group(3)})"
    else:
        # Try percentage pattern
        pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:response|improvement|remission|success)', abstract, re.IGNORECASE)
        if pct_match:
            response_rate = f"{pct_match.group(1)}%"

    return {
        "n_patients": n_patients,
        "n_confidence": "Medium" if n_patients else "Unknown",
        "response_rate": response_rate,
        "primary_endpoint": None,
        "efficacy_mention": None,
    }
