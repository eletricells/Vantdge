"""
Drug Repurposing Case Series Agent

Systematically identifies and analyzes drug repurposing opportunities by mining
case series and case reports from medical literature.

Features:
- Integrates with existing Vantdge infrastructure (DrugDatabase, PubMedAPI, etc.)
- Uses both PubMed (peer-reviewed) and Tavily (grey literature) for comprehensive search
- Extracts structured clinical evidence using Claude with extended thinking
- Enriches with market intelligence (epidemiology, SOC, competitive landscape)
- Scores and ranks opportunities by clinical signal, evidence quality, market size

Workflow:
1. Get drug info and approved indications (via DrugDatabase/DailyMed)
2. Search for case series/reports (PubMed + Tavily)
3. Extract structured data from each case series
4. Enrich with market intelligence
5. Score and rank opportunities
6. Export to Excel/JSON
"""

import json
import logging
import os
import re
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set

from anthropic import Anthropic
from pydantic import ValidationError

from src.reports.case_series_report_generator import CaseSeriesReportGenerator
from src.models.case_series_schemas import (
    CaseSeriesExtraction,
    CaseSeriesSource,
    PatientPopulation,
    TreatmentDetails,
    EfficacyOutcome,
    SafetyOutcome,
    EvidenceLevel,
    OutcomeResult,
    EfficacySignal,
    SafetyProfile,
    EpidemiologyData,
    StandardOfCareData,
    StandardOfCareTreatment,
    PipelineTherapy,
    MarketIntelligence,
    OpportunityScores,
    RepurposingOpportunity,
    DrugAnalysisResult,
    MechanismAnalysisResult,
    DetailedEfficacyEndpoint,
    DetailedSafetyEndpoint,
)
from src.tools.pubmed import PubMedAPI
from src.tools.web_search import WebSearchTool
from src.tools.drug_database import DrugDatabase
from src.tools.dailymed import DailyMedAPI
from src.tools.semantic_scholar import SemanticScholarAPI
from src.tools.case_series_database import CaseSeriesDatabase
from src.prompts import get_prompt_manager, PromptManager

logger = logging.getLogger(__name__)

# =============================================================================
# MULTI-STAGE EXTRACTION CONSTANTS
# =============================================================================
THINKING_BUDGET_SECTIONS = 3000  # Stage 1: Section identification
THINKING_BUDGET_EFFICACY = 4000  # Stage 2: Efficacy extraction
THINKING_BUDGET_SAFETY = 2000    # Stage 3: Safety extraction
MIN_FULLTEXT_LENGTH = 2000       # Minimum chars to use multi-stage


# =============================================================================
# DISEASE NAME VARIANTS FOR BETTER SEARCH COVERAGE
# =============================================================================
DISEASE_NAME_VARIANTS = {
    "Primary Sjogren's syndrome": [
        "Sjogren syndrome", "Sjögren's disease", "Sjögren syndrome",
        "sicca syndrome", "primary Sjögren's"
    ],
    "Systemic Lupus Erythematosus": ["SLE", "lupus erythematosus", "systemic lupus"],
    "Rheumatoid Arthritis": ["RA", "rheumatoid"],
    "Atopic Dermatitis": ["AD", "atopic eczema", "eczema"],
    "Dermatomyositis": ["DM", "inflammatory myopathy"],
    "Alopecia Areata": ["AA", "alopecia totalis", "alopecia universalis"],
    "Giant Cell Arteritis": ["GCA", "temporal arteritis"],
    "Takayasu arteritis": ["TAK", "Takayasu's arteritis", "large vessel vasculitis"],
    "Juvenile Idiopathic Arthritis": ["JIA", "juvenile arthritis", "juvenile rheumatoid arthritis"],
    "Adult-onset Still's Disease": ["AOSD", "Still's disease", "adult Still disease"],
    "Graft-versus-Host Disease": ["GVHD", "graft versus host", "GvHD"],
    "Inflammatory Bowel Disease": ["IBD", "Crohn's disease", "ulcerative colitis"],
    "Psoriatic Arthritis": ["PsA", "psoriatic"],
    "Ankylosing Spondylitis": ["AS", "axial spondyloarthritis", "axSpA"],
    "Myasthenia Gravis": ["MG", "myasthenia"],
    "Immune Thrombocytopenia": ["ITP", "immune thrombocytopenic purpura", "idiopathic thrombocytopenic purpura"],
}

# Map overly specific diseases to parent indications for market intel lookup
DISEASE_PARENT_MAPPING = {
    # SLE variants
    "Systemic Lupus Erythematosus with alopecia universalis and arthritis": "Systemic Lupus Erythematosus",
    "SLE with cutaneous manifestations": "Systemic Lupus Erythematosus",
    "refractory systemic lupus erythematosus": "Systemic Lupus Erythematosus",
    # Alopecia variants
    "severe alopecia areata with atopic dermatitis in children": "Alopecia Areata",
    "pediatric alopecia universalis": "Alopecia Areata",
    "alopecia totalis": "Alopecia Areata",
    # Dermatomyositis variants
    "refractory dermatomyositis": "Dermatomyositis",
    "anti-MDA5 antibody-positive dermatomyositis": "Dermatomyositis",
    "Juvenile dermatomyositis-associated calcinosis": "Juvenile Dermatomyositis",
    "refractory or severe juvenile dermatomyositis": "Juvenile Dermatomyositis",
    # JIA variants
    "juvenile idiopathic arthritis associated uveitis": "Juvenile Idiopathic Arthritis",
    "Systemic juvenile idiopathic arthritis with lung disease": "Systemic Juvenile Idiopathic Arthritis",
    # Vasculitis variants
    "Takayasu arteritis refractory to TNF-α inhibitors": "Takayasu arteritis",
    # Uveitis variants
    "Uveitis associated with rheumatoid arthritis": "Uveitis",
    "isolated noninfectious uveitis": "Uveitis",
    "non-infectious inflammatory ocular diseases": "Uveitis",
    # AOSD variants
    "Adult-onset Still's disease (AOSD) and undifferentiated systemic autoinflammatory disease": "Adult-onset Still's Disease",
    # Atopic Dermatitis variants
    "atopic dermatitis": "Atopic Dermatitis",
    "moderate-to-severe atopic dermatitis": "Atopic Dermatitis",
    "moderate and severe atopic dermatitis": "Atopic Dermatitis",
    # ITP variants
    "immune thrombocytopenia (ITP)": "Immune Thrombocytopenia",
    # Lupus variants
    "refractory subacute cutaneous lupus erythematosus": "Cutaneous Lupus Erythematosus",
    "Familial chilblain lupus with TREX1 mutation": "Cutaneous Lupus Erythematosus",
    "Lupus erythematosus panniculitis": "Cutaneous Lupus Erythematosus",
}


# =============================================================================
# EFFICACY SCORING HELPER FUNCTIONS (v2)
# =============================================================================

def _response_pct_to_score(pct: float) -> float:
    """
    Convert response percentage to 1-10 score.

    10 tiers for granularity:
    >=90%: 10, >=80%: 9, >=70%: 8, >=60%: 7, >=50%: 6,
    >=40%: 5, >=30%: 4, >=20%: 3, >=10%: 2, <10%: 1
    """
    if pct >= 90:
        return 10.0
    elif pct >= 80:
        return 9.0
    elif pct >= 70:
        return 8.0
    elif pct >= 60:
        return 7.0
    elif pct >= 50:
        return 6.0
    elif pct >= 40:
        return 5.0
    elif pct >= 30:
        return 4.0
    elif pct >= 20:
        return 3.0
    elif pct >= 10:
        return 2.0
    else:
        return 1.0


def _percent_change_to_score(effective_change: float) -> float:
    """
    Convert percent improvement to 1-10 score.

    effective_change is positive when improvement occurs
    (already adjusted for direction by caller).

    >=60% improvement: 10, >=50%: 9, >=40%: 8, >=30%: 7,
    >=20%: 6, >=10%: 5, 0-10%: 4, worsening: 2-3
    """
    if effective_change >= 60:
        return 10.0
    elif effective_change >= 50:
        return 9.0
    elif effective_change >= 40:
        return 8.0
    elif effective_change >= 30:
        return 7.0
    elif effective_change >= 20:
        return 6.0
    elif effective_change >= 10:
        return 5.0
    elif effective_change >= 0:
        return 4.0
    elif effective_change >= -10:
        return 3.0
    else:
        return 2.0


def _is_decrease_good(endpoint_name: str) -> bool:
    """
    Determine if a decrease in endpoint value indicates improvement.

    Most disease activity scores: decrease = improvement
    Quality of life / response rates: increase = improvement
    """
    endpoint_lower = endpoint_name.lower()

    # Endpoints where INCREASE is good (return False = decrease is NOT good)
    increase_good_patterns = [
        # Response rates
        'acr20', 'acr50', 'acr70', 'acr90',
        'pasi50', 'pasi75', 'pasi90', 'pasi100',
        'easi50', 'easi75', 'easi90',
        'salt50', 'salt75', 'salt90',
        'response', 'responder', 'remission',
        # Quality of life
        'quality of life', 'qol',
        'sf-36', 'sf36',
        'eq-5d', 'eq5d',
        'facit', 'well-being', 'wellbeing',
        # Function
        'function', 'improvement',
        # Clear/almost clear assessments
        'iga 0', 'iga 1', 'clear', 'almost clear',
        # Hair regrowth
        'regrowth', 'hair growth',
    ]

    for pattern in increase_good_patterns:
        if pattern in endpoint_lower:
            return False  # Increase is good, so decrease is NOT good

    # Default: most clinical scores decrease = improvement
    # (DAS28, SLEDAI, PASI score, SALT score, pain VAS, disease activity, etc.)
    return True


def _calculate_evidence_confidence_case_series(
    n_studies: int,
    total_patients: int,
    consistency: str,
    extractions: List[Any]
) -> str:
    """
    Calculate overall confidence in aggregated evidence.

    Calibrated for case series literature where:
    - 20+ patients is substantial
    - 10+ patients is reasonable
    - <5 patients is very limited

    Levels:
    - Moderate: 3+ studies, 20+ patients, consistent results, some full text
    - Low-Moderate: 3+ studies, 20+ patients, consistent results
    - Low: 2+ studies, 10+ patients
    - Very Low: Everything else
    """
    # Count high-quality extractions (multi-stage with full text)
    high_quality = sum(
        1 for ext in extractions
        if getattr(ext, 'extraction_method', '') == 'multi_stage'
    )

    if n_studies >= 3 and total_patients >= 20 and consistency in ['High', 'Moderate']:
        if high_quality >= 2:
            return 'Moderate'
        return 'Low-Moderate'
    elif n_studies >= 2 and total_patients >= 10:
        return 'Low'
    elif n_studies >= 1 and total_patients >= 3:
        return 'Very Low'
    else:
        return 'Very Low'


class CaseSeriesDataExtractor:
    """
    Multi-stage clinical data extractor for case series/reports.

    Implements a 3-stage extraction pipeline:
    - Stage 1: Section identification (find tables, figures, results sections)
    - Stage 2: Efficacy extraction (detailed endpoint extraction with extended thinking)
    - Stage 3: Safety extraction (adverse events, discontinuations)

    Uses extended thinking for complex table interpretation.
    """

    def __init__(self, client: Anthropic, model: str = "claude-sonnet-4-20250514", prompts: Optional[PromptManager] = None):
        self.client = client
        self.model = model
        self._prompts = prompts or get_prompt_manager()
        self.stages_completed = []
        self.extraction_metrics = {
            'input_tokens': 0,
            'output_tokens': 0,
            'thinking_tokens': 0,
            'cache_creation_tokens': 0,
            'cache_read_tokens': 0
        }

    def extract_multi_stage(
        self,
        paper_content: str,
        drug_name: str,
        drug_info: Dict[str, Any],
        paper_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run multi-stage extraction on full-text paper content.

        Args:
            paper_content: Full text of the paper
            drug_name: Name of the drug
            drug_info: Drug information dict
            paper_metadata: Paper metadata (title, pmid, etc.)

        Returns:
            Dict with extraction results including detailed endpoints
        """
        self.stages_completed = []
        results = {
            'sections_identified': None,
            'detailed_efficacy_endpoints': [],
            'detailed_safety_endpoints': [],
            'extraction_method': 'multi_stage',
            'stages_completed': []
        }

        # Stage 1: Section identification
        logger.info("Multi-stage extraction - Stage 1: Section identification")
        sections = self._stage1_identify_sections(paper_content, drug_name, paper_metadata)
        results['sections_identified'] = sections
        self.stages_completed.append('section_identification')

        # Stage 2: Efficacy extraction
        logger.info("Multi-stage extraction - Stage 2: Efficacy extraction")
        efficacy_endpoints = self._stage2_extract_efficacy(
            paper_content, drug_name, drug_info, sections
        )
        results['detailed_efficacy_endpoints'] = efficacy_endpoints
        self.stages_completed.append('efficacy_extraction')

        # Stage 3: Safety extraction
        logger.info("Multi-stage extraction - Stage 3: Safety extraction")
        safety_endpoints = self._stage3_extract_safety(
            paper_content, drug_name, sections
        )
        results['detailed_safety_endpoints'] = safety_endpoints
        self.stages_completed.append('safety_extraction')

        results['stages_completed'] = self.stages_completed.copy()
        return results

    def _stage1_identify_sections(
        self,
        paper_content: str,
        drug_name: str,
        paper_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Stage 1: Identify data-containing sections."""

        prompt = self._prompts.render(
            "case_series/stage1_sections",
            drug_name=drug_name,
            paper_title=paper_metadata.get('title', 'Unknown'),
            paper_content=paper_content[:30000]
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=THINKING_BUDGET_SECTIONS + 2000,  # Must be > thinking budget
                temperature=1,  # Required for extended thinking
                thinking={
                    "type": "enabled",
                    "budget_tokens": THINKING_BUDGET_SECTIONS
                },
                messages=[{"role": "user", "content": prompt}]
            )

            self._track_tokens(response)
            text = self._extract_text_response(response)
            return self._parse_json(text, default={
                'baseline_tables': [],
                'efficacy_tables': [],
                'safety_tables': [],
                'efficacy_figures': [],
                'results_sections': [],
                'notes': 'Failed to parse sections'
            })

        except Exception as e:
            logger.error(f"Stage 1 error: {e}")
            return {'error': str(e)}

    def _stage2_extract_efficacy(
        self,
        paper_content: str,
        drug_name: str,
        drug_info: Dict[str, Any],
        sections: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Stage 2: Extract detailed efficacy endpoints."""

        tables_info = ", ".join(sections.get('efficacy_tables', [])) or "None identified"

        prompt = self._prompts.render(
            "case_series/stage2_efficacy",
            drug_name=drug_name,
            mechanism=drug_info.get('mechanism', 'Unknown'),
            efficacy_tables=tables_info,
            paper_content=paper_content[:35000]
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=THINKING_BUDGET_EFFICACY + 8000,  # Must be > thinking budget
                temperature=1,
                thinking={
                    "type": "enabled",
                    "budget_tokens": THINKING_BUDGET_EFFICACY
                },
                messages=[{"role": "user", "content": prompt}]
            )

            self._track_tokens(response)
            text = self._extract_text_response(response)
            endpoints = self._parse_json(text, default=[])

            # Convert to DetailedEfficacyEndpoint objects
            validated = []
            for ep in endpoints:
                if isinstance(ep, dict) and ep.get('endpoint_name'):
                    validated.append(ep)

            return validated

        except Exception as e:
            logger.error(f"Stage 2 error: {e}")
            return []

    def _stage3_extract_safety(
        self,
        paper_content: str,
        drug_name: str,
        sections: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Stage 3: Extract detailed safety endpoints."""

        tables_info = ", ".join(sections.get('safety_tables', [])) or "None identified"

        prompt = self._prompts.render(
            "case_series/stage3_safety",
            drug_name=drug_name,
            safety_tables=tables_info,
            paper_content=paper_content[:30000]
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=THINKING_BUDGET_SAFETY + 4000,  # Must be > thinking budget
                temperature=1,
                thinking={
                    "type": "enabled",
                    "budget_tokens": THINKING_BUDGET_SAFETY
                },
                messages=[{"role": "user", "content": prompt}]
            )

            self._track_tokens(response)
            text = self._extract_text_response(response)
            events = self._parse_json(text, default=[])

            # Validate events
            validated = []
            for ev in events:
                if isinstance(ev, dict) and ev.get('event_name'):
                    validated.append(ev)

            return validated

        except Exception as e:
            logger.error(f"Stage 3 error: {e}")
            return []

    def _track_tokens(self, response) -> None:
        """Track token usage from response."""
        if hasattr(response, 'usage'):
            self.extraction_metrics['input_tokens'] += response.usage.input_tokens
            self.extraction_metrics['output_tokens'] += response.usage.output_tokens
            # Track cache tokens
            if hasattr(response.usage, 'cache_creation_input_tokens'):
                self.extraction_metrics['cache_creation_tokens'] += response.usage.cache_creation_input_tokens
            if hasattr(response.usage, 'cache_read_input_tokens'):
                self.extraction_metrics['cache_read_tokens'] += response.usage.cache_read_input_tokens

    def _extract_text_response(self, response) -> str:
        """Extract text from response, handling extended thinking format."""
        for block in response.content:
            if hasattr(block, 'text'):
                return block.text
        return ""

    def _parse_json(self, text: str, default: Any = None) -> Any:
        """Parse JSON from response text."""
        # Clean markdown code blocks
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0]
        elif '```' in text:
            text = text.split('```')[1].split('```')[0]

        try:
            return json.loads(text.strip())
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            return default if default is not None else {}


class DrugRepurposingCaseSeriesAgent:
    """
    Agent for identifying drug repurposing opportunities through case series mining.
    
    Integrates with existing Vantdge infrastructure for robust drug data retrieval
    and comprehensive literature search.
    """
    
    def __init__(
        self,
        anthropic_api_key: str,
        database_url: Optional[str] = None,
        case_series_database_url: Optional[str] = None,
        pubmed_email: str = "user@example.com",
        pubmed_api_key: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        semantic_scholar_api_key: Optional[str] = None,
        output_dir: str = "data/case_series",
        cache_max_age_days: int = 30
    ):
        """
        Initialize agent with all required tools.

        Args:
            anthropic_api_key: Anthropic API key for Claude
            database_url: PostgreSQL database URL (optional, for drug lookups)
            case_series_database_url: PostgreSQL URL for case series persistence/caching
            pubmed_email: Email for PubMed API
            pubmed_api_key: PubMed API key (optional, increases rate limits)
            tavily_api_key: Tavily API key for web search
            semantic_scholar_api_key: Semantic Scholar API key (optional, for higher rate limits)
            output_dir: Directory for output files
            cache_max_age_days: Days before cached market intelligence expires (default: 30)
        """
        # Initialize Claude client
        self.client = Anthropic(api_key=anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"
        self.max_tokens = 16000

        # Initialize PromptManager for centralized prompt templates
        self._prompts = get_prompt_manager()

        # Initialize tools
        self.pubmed = PubMedAPI(
            email=pubmed_email,
            api_key=pubmed_api_key
        )
        
        self.web_search = None
        if tavily_api_key:
            self.web_search = WebSearchTool(api_key=tavily_api_key)

        # Semantic Scholar API for semantic search and citation mining
        self.semantic_scholar = SemanticScholarAPI(api_key=semantic_scholar_api_key)
        logger.info("Semantic Scholar API initialized (citation mining enabled)")

        # Database connection (optional)
        self.drug_db = None
        if database_url:
            try:
                self.drug_db = DrugDatabase(database_url)
                self.drug_db.connect()
                logger.info("Connected to drug database")
            except Exception as e:
                logger.warning(f"Could not connect to drug database: {e}")
                self.drug_db = None

        # DailyMed API for FDA label data
        self.dailymed = DailyMedAPI()

        # Drugs.com scraper (lazy loaded)
        self._drugs_com_scraper = None

        # Case Series Database for persistence and caching
        self.cs_db = None
        self.cache_max_age_days = cache_max_age_days
        cs_db_url = case_series_database_url or database_url
        if cs_db_url:
            try:
                self.cs_db = CaseSeriesDatabase(cs_db_url, cache_max_age_days=cache_max_age_days)
                if self.cs_db.is_available:
                    logger.info("Case series database connected (caching enabled)")
                else:
                    logger.warning("Case series database not available (caching disabled)")
                    self.cs_db = None
            except Exception as e:
                logger.warning(f"Could not initialize case series database: {e}")
                self.cs_db = None

        # Current run tracking
        self._current_run_id = None
        self._cache_stats = {
            'papers_from_cache': 0,
            'market_intel_from_cache': 0,
            'tokens_saved_by_cache': 0
        }

        # Clinical scoring reference data (loaded from database on first use)
        self._organ_domains: Optional[Dict[str, List[str]]] = None
        self._safety_categories: Optional[Dict[str, Dict[str, Any]]] = None
        self._scoring_weights: Optional[Dict[str, float]] = None

        # Disease mappings (loaded from DB with fallback to constants)
        self._disease_name_variants: Dict[str, List[str]] = {}
        self._disease_parent_mappings: Dict[str, str] = {}
        self._load_disease_mappings()

        # Output directory
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_cache_read_tokens = 0
        self.search_count = 0

        logger.info("DrugRepurposingCaseSeriesAgent initialized")

    def _load_disease_mappings(self) -> None:
        """
        Load disease mappings from database with fallback to hardcoded constants.

        This method:
        1. Tries to load from database first
        2. Falls back to DISEASE_NAME_VARIANTS and DISEASE_PARENT_MAPPING constants
        3. Merges both sources (DB takes precedence for conflicts)
        """
        # Start with hardcoded constants as baseline
        self._disease_name_variants = dict(DISEASE_NAME_VARIANTS)
        self._disease_parent_mappings = dict(DISEASE_PARENT_MAPPING)

        # Try to load from database and merge
        if self.cs_db and self.cs_db.is_available:
            try:
                # Load name variants from DB
                db_variants = self.cs_db.load_disease_name_variants()
                if db_variants:
                    for canonical, variants in db_variants.items():
                        if canonical in self._disease_name_variants:
                            # Merge with existing, avoiding duplicates
                            existing = set(self._disease_name_variants[canonical])
                            existing.update(variants)
                            self._disease_name_variants[canonical] = list(existing)
                        else:
                            self._disease_name_variants[canonical] = variants
                    logger.info(f"Merged {len(db_variants)} disease variant sets from database")

                # Load parent mappings from DB
                db_parents = self.cs_db.load_disease_parent_mappings()
                if db_parents:
                    # DB mappings override constants
                    self._disease_parent_mappings.update(db_parents)
                    logger.info(f"Merged {len(db_parents)} parent mappings from database")

            except Exception as e:
                logger.warning(f"Error loading disease mappings from database: {e}")

        logger.info(f"Disease mappings loaded: {len(self._disease_name_variants)} variant sets, "
                   f"{len(self._disease_parent_mappings)} parent mappings")

    def _save_new_disease_mapping(
        self,
        specific_name: str,
        parent_name: str,
        relationship_type: str = 'subtype'
    ) -> bool:
        """
        Save a newly discovered disease mapping to the database.

        Called automatically when the agent discovers a new disease subtype
        during extraction that should map to a parent disease.

        Args:
            specific_name: The specific disease subtype found
            parent_name: The parent disease it should map to
            relationship_type: Type of relationship (subtype, variant, refractory)

        Returns:
            True if saved successfully
        """
        if not self.cs_db or not self.cs_db.is_available:
            return False

        # Check if we already have this mapping
        if specific_name.lower() in [k.lower() for k in self._disease_parent_mappings.keys()]:
            return False  # Already exists

        # Save to database
        success = self.cs_db.save_disease_parent_mapping(
            specific_name=specific_name,
            parent_name=parent_name,
            relationship_type=relationship_type,
            source='auto',
            confidence=0.8,  # Auto-discovered mappings get slightly lower confidence
            created_by='agent'
        )

        if success:
            # Also update in-memory mapping
            self._disease_parent_mappings[specific_name] = parent_name
            logger.info(f"Auto-saved new disease mapping: '{specific_name}' -> '{parent_name}'")

        return success

    def _infer_disease_mapping(self, disease_name: str) -> Optional[Dict[str, Any]]:
        """
        Use LLM to infer parent disease and name variants for an unmapped disease.

        This is called when a disease name is not found in the database mappings.
        The LLM suggests the parent disease and alternative names, which are then
        auto-saved to the database for future use.

        Args:
            disease_name: The disease name to analyze

        Returns:
            Dict with parent_disease, relationship_type, canonical_name, variants, confidence
            or None if inference fails
        """
        # Skip inference for very short names (likely already abbreviations)
        if len(disease_name) <= 3:
            return None

        try:
            # Render the inference prompt template
            prompt = self._prompts.render(
                "case_series/infer_disease_mapping",
                disease_name=disease_name
            )

            # Call Claude for inference
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if not json_match:
                logger.warning(f"No JSON found in disease inference response for '{disease_name}'")
                return None

            result = json.loads(json_match.group())

            # Validate required fields
            if 'canonical_name' not in result:
                return None

            logger.info(f"Inferred disease mapping for '{disease_name}': "
                       f"parent='{result.get('parent_disease')}', "
                       f"confidence={result.get('confidence', 0)}")

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse disease inference JSON for '{disease_name}': {e}")
            return None
        except Exception as e:
            logger.warning(f"Disease inference failed for '{disease_name}': {e}")
            return None

    def _save_inferred_disease_mapping(self, inference_result: Dict[str, Any]) -> bool:
        """
        Save an inferred disease mapping to the database.

        Args:
            inference_result: The result from _infer_disease_mapping()

        Returns:
            True if saved successfully
        """
        if not self.cs_db or not self.cs_db.is_available:
            return False

        original = inference_result.get('original_disease', '')
        parent = inference_result.get('parent_disease')
        relationship = inference_result.get('relationship_type', 'variant')
        canonical = inference_result.get('canonical_name', '')
        variants = inference_result.get('variants', [])
        confidence = inference_result.get('confidence', 0.8)

        saved_any = False

        # Save parent mapping if we have one
        if parent and original:
            success = self.cs_db.save_disease_parent_mapping(
                specific_name=original,
                parent_name=parent,
                relationship_type=relationship or 'variant',
                source='llm_inferred',
                confidence=confidence * 0.9,  # Slightly lower confidence for LLM-inferred
                created_by='agent_auto'
            )
            if success:
                self._disease_parent_mappings[original] = parent
                saved_any = True
                logger.info(f"Auto-saved inferred parent mapping: '{original}' -> '{parent}'")

        # Save name variants if we have them
        if canonical and variants:
            for variant in variants:
                variant_name = variant.get('name', '')
                variant_type = variant.get('type', 'synonym')
                if variant_name and variant_name.lower() != canonical.lower():
                    success = self.cs_db.save_disease_variant(
                        canonical_name=canonical,
                        variant_name=variant_name,
                        variant_type=variant_type,
                        source='llm_inferred',
                        confidence=confidence * 0.85
                    )
                    if success:
                        # Update in-memory mapping
                        if canonical not in self._disease_name_variants:
                            self._disease_name_variants[canonical] = []
                        if variant_name not in self._disease_name_variants[canonical]:
                            self._disease_name_variants[canonical].append(variant_name)
                        saved_any = True

            if saved_any:
                logger.info(f"Auto-saved {len(variants)} inferred variants for '{canonical}'")

        return saved_any

    # =========================================================================
    # MAIN ANALYSIS METHODS
    # =========================================================================
    
    def analyze_drug(
        self,
        drug_name: str,
        max_papers: int = 50,
        include_web_search: bool = True,
        enrich_market_data: bool = True
    ) -> DrugAnalysisResult:
        """
        Main entry point: analyze a drug for repurposing opportunities.

        Args:
            drug_name: Drug name to analyze
            max_papers: Maximum papers to screen
            include_web_search: Whether to include Tavily web search
            enrich_market_data: Whether to enrich with market intelligence

        Returns:
            DrugAnalysisResult with all opportunities found
        """
        logger.info(f"Starting repurposing analysis for: {drug_name}")
        start_time = datetime.now()

        # Reset cost and cache tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.search_count = 0
        self._cache_stats = {
            'papers_from_cache': 0,
            'market_intel_from_cache': 0,
            'tokens_saved_by_cache': 0
        }

        # Create database run for tracking
        run_params = {
            'max_papers': max_papers,
            'include_web_search': include_web_search,
            'enrich_market_data': enrich_market_data
        }
        if self.cs_db:
            self._current_run_id = self.cs_db.create_run(drug_name, run_params)
            logger.info(f"Created analysis run: {self._current_run_id}")

        try:
            # Step 1: Get drug information and approved indications
            drug_info = self._get_drug_info(drug_name)
            approved_indications = drug_info.get("approved_indications", [])
            logger.info(f"Found {len(approved_indications)} approved indications")

            # Save drug info to database
            if self.cs_db:
                self.cs_db.save_drug(
                    drug_name=drug_name,
                    generic_name=drug_info.get("generic_name"),
                    mechanism=drug_info.get("mechanism"),
                    target=drug_info.get("target"),
                    approved_indications=approved_indications,
                    data_sources=drug_info.get("data_sources", [])
                )

            # Step 2: Search for case series/reports
            papers = self._search_case_series(
                drug_name,
                approved_indications,
                max_papers=max_papers,
                include_web_search=include_web_search,
                generic_name=drug_info.get("generic_name")
            )
            logger.info(f"Found {len(papers)} potential case series/reports")

            # Update run stats
            if self.cs_db and self._current_run_id:
                self.cs_db.update_run_stats(self._current_run_id, papers_found=len(papers))

            # Step 3: Extract structured data from each paper
            opportunities = []
            extraction_ids = {}  # Map extraction to database ID
            total_extractions = 0
            for i, paper in enumerate(papers, 1):
                logger.info(f"Extracting data from paper {i}/{len(papers)}: {paper.get('title', 'Unknown')[:50]}...")
                try:
                    extraction = self._extract_case_series_data(drug_name, drug_info, paper)
                    if extraction:
                        total_extractions += 1

                        # Save ALL extractions to database (even irrelevant ones for auditing)
                        ext_id = None  # Initialize to avoid UnboundLocalError
                        if self.cs_db and self._current_run_id:
                            ext_id = self.cs_db.save_extraction(
                                self._current_run_id, extraction, drug_name
                            )
                            logger.info(f"  Saved extraction to database (ID: {ext_id}, relevant: {extraction.is_relevant})")

                        # Only add relevant extractions to opportunities
                        if extraction.is_relevant:
                            opportunity = RepurposingOpportunity(extraction=extraction)
                            opportunities.append(opportunity)
                            if ext_id:
                                extraction_ids[id(opportunity)] = ext_id
                        else:
                            logger.info(f"  Skipping irrelevant extraction for opportunities list")

                except Exception as e:
                    logger.error(f"Error extracting paper {i}: {e}")
                    continue

                # Rate limiting
                if i < len(papers):
                    time.sleep(0.5)

            logger.info(f"Successfully extracted {total_extractions} papers ({len(opportunities)} relevant opportunities)")

            # Update run stats (papers_extracted = total extractions, not just relevant)
            if self.cs_db and self._current_run_id:
                self.cs_db.update_run_stats(self._current_run_id, papers_extracted=total_extractions)

            # Step 4: Standardize disease names
            if opportunities:
                logger.info("Standardizing disease names...")
                opportunities = self.standardize_disease_names(opportunities)

            # Step 5: Enrich with market intelligence
            if enrich_market_data and opportunities:
                opportunities = self._enrich_with_market_data(opportunities)

            # Step 6: Score and rank opportunities
            opportunities = self._score_opportunities(opportunities)
            opportunities.sort(key=lambda x: x.scores.overall_priority, reverse=True)

            # Assign ranks and save opportunities
            for i, opp in enumerate(opportunities, 1):
                opp.rank = i
                # Save opportunity to database
                if self.cs_db and self._current_run_id:
                    ext_id = extraction_ids.get(id(opp))
                    if ext_id:
                        self.cs_db.save_opportunity(
                            self._current_run_id, ext_id, opp, drug_name
                        )

            # Calculate cost
            estimated_cost = self._calculate_cost()

            # Build result
            result = DrugAnalysisResult(
                drug_name=drug_name,
                generic_name=drug_info.get("generic_name"),
                mechanism=drug_info.get("mechanism"),
                target=drug_info.get("target"),
                approved_indications=approved_indications,
                opportunities=opportunities,
                analysis_date=datetime.now(),
                papers_screened=len(papers),
                papers_extracted=len(opportunities),
                total_input_tokens=self.total_input_tokens,
                total_output_tokens=self.total_output_tokens,
                estimated_cost_usd=estimated_cost
            )

            # Mark run as completed
            if self.cs_db and self._current_run_id:
                self.cs_db.update_run_stats(
                    self._current_run_id,
                    opportunities_found=len(opportunities),
                    total_input_tokens=self.total_input_tokens,
                    total_output_tokens=self.total_output_tokens,
                    estimated_cost_usd=estimated_cost,
                    papers_from_cache=self._cache_stats['papers_from_cache'],
                    market_intel_from_cache=self._cache_stats['market_intel_from_cache'],
                    tokens_saved_by_cache=self._cache_stats['tokens_saved_by_cache']
                )
                self.cs_db.update_run_status(self._current_run_id, 'completed')

            duration = (datetime.now() - start_time).total_seconds()
            cache_info = f" (cache: {self._cache_stats['papers_from_cache']} papers, {self._cache_stats['market_intel_from_cache']} market intel)"
            logger.info(f"Analysis complete in {duration:.1f}s. Found {len(opportunities)} opportunities. Cost: ${estimated_cost:.2f}{cache_info}")

            return result

        except Exception as e:
            # Mark run as failed
            if self.cs_db and self._current_run_id:
                self.cs_db.update_run_status(self._current_run_id, 'failed', str(e))
            raise

    def analyze_mechanism(
        self,
        mechanism: str,
        max_drugs: int = 10,
        **kwargs
    ) -> MechanismAnalysisResult:
        """
        Analyze all drugs with a given mechanism for repurposing opportunities.

        Args:
            mechanism: Mechanism to analyze (e.g., "JAK inhibitor", "CGRP antagonist")
            max_drugs: Maximum number of drugs to analyze
            **kwargs: Additional args passed to analyze_drug

        Returns:
            MechanismAnalysisResult with all drugs and opportunities
        """
        logger.info(f"Starting mechanism-based analysis: {mechanism}")

        # Find drugs with this mechanism
        drugs = self._find_drugs_by_mechanism(mechanism, max_drugs=max_drugs)
        logger.info(f"Found {len(drugs)} drugs with mechanism: {mechanism}")

        # Analyze each drug
        results = []
        total_opportunities = 0
        total_cost = 0.0

        for i, drug_name in enumerate(drugs, 1):
            logger.info(f"Analyzing drug {i}/{len(drugs)}: {drug_name}")
            try:
                result = self.analyze_drug(drug_name, **kwargs)
                results.append(result)
                total_opportunities += len(result.opportunities)
                total_cost += result.estimated_cost_usd
            except Exception as e:
                logger.error(f"Error analyzing {drug_name}: {e}")
                continue

            # Rate limiting between drugs
            if i < len(drugs):
                time.sleep(1)

        return MechanismAnalysisResult(
            mechanism=mechanism,
            drugs_analyzed=results,
            total_opportunities=total_opportunities,
            analysis_date=datetime.now(),
            total_cost_usd=total_cost
        )

    # =========================================================================
    # HISTORICAL RUNS / DATABASE METHODS
    # =========================================================================

    def get_historical_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of historical analysis runs.

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of run summaries with drug_name, started_at, status, etc.
        """
        if not self.cs_db:
            logger.warning("Case series database not available - no historical runs")
            return []
        return self.cs_db.get_historical_runs(limit=limit)

    def load_historical_run(
        self,
        run_id: str,
        generate_visualizations: bool = True
    ) -> Optional[DrugAnalysisResult]:
        """Load a historical run as a DrugAnalysisResult object.

        Args:
            run_id: UUID of the run to load
            generate_visualizations: Whether to generate/update visualizations

        Returns:
            DrugAnalysisResult or None if not found
        """
        if not self.cs_db:
            logger.warning("Case series database not available")
            return None

        result = self.cs_db.load_run_as_result(run_id)

        # Generate visualizations if requested and result is valid
        if result and generate_visualizations and result.opportunities:
            try:
                # Use run_id in filename for consistency
                timestamp = result.analysis_date.strftime("%Y%m%d_%H%M%S") if result.analysis_date else datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"{result.drug_name.lower().replace(' ', '_')}_{timestamp}.xlsx"
                viz_paths = self.generate_visualizations(result, filename)
                logger.info(f"Generated visualizations for historical run: {list(viz_paths.values())}")
            except Exception as e:
                logger.warning(f"Failed to generate visualizations for historical run (non-critical): {e}")

        return result

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get full details of a specific run including extractions and opportunities.

        Args:
            run_id: UUID of the run

        Returns:
            Dict with run info, extractions, and opportunities
        """
        if not self.cs_db:
            logger.warning("Case series database not available")
            return None
        return self.cs_db.get_run_details(run_id)

    @property
    def database_available(self) -> bool:
        """Check if the case series database is available for persistence/caching."""
        return self.cs_db is not None and self.cs_db.is_available

    # =========================================================================
    # DRUG INFORMATION RETRIEVAL
    # =========================================================================

    def _get_drug_info(self, drug_name: str) -> Dict[str, Any]:
        """
        Get drug information including approved indications.

        Data sources are queried in the following order:
        1. DrugDatabase (PostgreSQL) - cached data from previous runs
        2. DailyMed API - official FDA drug labeling (best for generic_name, mechanism)
        3. Drugs.com Scraping - extracts approved indications from drug monographs
        4. Web Search Fallback - Tavily web search with Claude extraction

        Data is merged across sources to get the most complete picture.
        """
        drug_info = {
            "drug_name": drug_name,
            "generic_name": None,
            "mechanism": None,
            "target": None,
            "approved_indications": []
        }

        # 1. Try database first (cached data from previous runs)
        if self.drug_db:
            db_info = self._get_drug_from_database(drug_name)
            if db_info:
                drug_info.update(db_info)
                if drug_info.get("approved_indications") and drug_info.get("generic_name"):
                    logger.info(f"Got complete drug info from database: {len(drug_info['approved_indications'])} indications")
                    return drug_info

        # 2. Try OpenFDA API first for short mechanism (Established Pharmacologic Class)
        short_mechanism = self._get_short_mechanism_from_openfda(drug_name)
        if short_mechanism:
            drug_info["mechanism"] = short_mechanism
            logger.info(f"Got short mechanism from OpenFDA: {short_mechanism}")

        # 3. Try DailyMed API for official FDA labeling (best source for generic_name)
        dailymed_info = self._get_drug_from_dailymed(drug_name)
        if dailymed_info:
            # Always merge generic_name from DailyMed
            if dailymed_info.get("generic_name"):
                drug_info["generic_name"] = dailymed_info["generic_name"]
            # Only use DailyMed mechanism if we didn't get a short one from OpenFDA
            if not drug_info.get("mechanism") and dailymed_info.get("mechanism"):
                drug_info["mechanism"] = dailymed_info["mechanism"]
            if dailymed_info.get("manufacturer"):
                drug_info["manufacturer"] = dailymed_info["manufacturer"]

            # Only use DailyMed indications if they look good (not raw text blobs)
            dailymed_indications = dailymed_info.get("approved_indications", [])
            if dailymed_indications and len(dailymed_indications) > 0:
                # DailyMed indications are often raw text, check if they're usable
                first_indication = dailymed_indications[0] if dailymed_indications else ""
                # If it's a short, clean indication list, use it
                if len(first_indication) < 200:
                    drug_info["approved_indications"] = dailymed_indications
                    logger.info(f"Got drug info from DailyMed: {len(drug_info['approved_indications'])} indications, generic={drug_info.get('generic_name')}")
                    return drug_info

        # 4. Try Drugs.com scraping for cleaner indications list
        drugs_com_info = self._get_drug_from_drugs_com(drug_name)
        if drugs_com_info:
            if drugs_com_info.get("approved_indications"):
                drug_info["approved_indications"] = drugs_com_info["approved_indications"]
                logger.info(f"Got indications from Drugs.com: {len(drug_info['approved_indications'])} indications")

                # If we still don't have generic_name/mechanism, try to get from DailyMed again
                if not drug_info.get("generic_name") or not drug_info.get("mechanism"):
                    if dailymed_info:
                        if not drug_info.get("generic_name") and dailymed_info.get("generic_name"):
                            drug_info["generic_name"] = dailymed_info["generic_name"]
                        if not drug_info.get("mechanism") and dailymed_info.get("mechanism"):
                            drug_info["mechanism"] = dailymed_info["mechanism"]

                return drug_info

        # 5. Fall back to web search
        if self.web_search:
            web_info = self._get_drug_info_from_web(drug_name)
            if web_info:
                if web_info.get("approved_indications"):
                    drug_info["approved_indications"] = web_info["approved_indications"]
                if not drug_info.get("generic_name") and web_info.get("generic_name"):
                    drug_info["generic_name"] = web_info["generic_name"]
                if not drug_info.get("mechanism") and web_info.get("mechanism"):
                    drug_info["mechanism"] = web_info["mechanism"]

                if drug_info.get("approved_indications"):
                    logger.info(f"Got drug info from web search: {len(drug_info['approved_indications'])} indications")

        return drug_info

    def _get_drug_from_dailymed(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Get drug info from DailyMed API (FDA official labeling)."""
        try:
            # Use get_drug_info which handles search + label parsing
            info = self.dailymed.get_drug_info(drug_name)
            if not info:
                logger.debug(f"No DailyMed data found for {drug_name}")
                return None

            result = {
                "generic_name": info.get("generic_name"),
                "mechanism": info.get("mechanism_of_action"),
                "approved_indications": [],
                "manufacturer": info.get("manufacturer"),
                "route_of_administration": info.get("route_of_administration", [])
            }

            # Extract indications
            indications = info.get("indications", [])
            if isinstance(indications, list):
                result["approved_indications"] = indications
            elif isinstance(indications, str):
                result["approved_indications"] = [indications]

            logger.info(f"Got DailyMed data for {drug_name}: generic={result.get('generic_name')}, mechanism={'Yes' if result.get('mechanism') else 'No'}")
            return result if result.get("approved_indications") or result.get("generic_name") else None

        except Exception as e:
            logger.debug(f"DailyMed API error for {drug_name}: {e}")
            return None

    def _get_short_mechanism_from_openfda(self, drug_name: str) -> Optional[str]:
        """
        Get short mechanism description from OpenFDA's Established Pharmacologic Class (EPC).

        OpenFDA provides standardized, concise pharmacologic class information like:
        - "Janus Kinase Inhibitor [EPC]"
        - "Tumor Necrosis Factor Blocker [EPC]"
        - "Selective Serotonin Reuptake Inhibitor [EPC]"

        This is much more concise than the full mechanism text from DailyMed.
        """
        try:
            import requests

            # Query OpenFDA drug label API - simplified query
            url = "https://api.fda.gov/drug/label.json"
            # Use simple search without quotes first
            params = {
                "search": f"openfda.generic_name:{drug_name}",
                "limit": 1
            }

            response = requests.get(url, params=params, timeout=10)

            # If simple search fails, try with OR
            if response.status_code != 200:
                params = {
                    "search": f"openfda.brand_name:{drug_name}",
                    "limit": 1
                }
                response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                logger.warning(f"OpenFDA API returned status {response.status_code} for {drug_name}")
                return None

            data = response.json()
            results = data.get("results", [])

            if not results:
                logger.warning(f"No OpenFDA results for {drug_name}")
                return None

            openfda = results[0].get("openfda", {})
            logger.info(f"OpenFDA keys for {drug_name}: {list(openfda.keys())}")

            # Try pharm_class_epc first (Established Pharmacologic Class)
            epc = openfda.get("pharm_class_epc", [])
            if epc:
                # Clean up the EPC - remove "[EPC]" suffix
                mechanism = epc[0].replace(" [EPC]", "")
                logger.info(f"Got short mechanism from OpenFDA EPC for {drug_name}: {mechanism}")
                return mechanism

            # Fallback to pharm_class_moa (Mechanism of Action class)
            moa = openfda.get("pharm_class_moa", [])
            if moa:
                mechanism = moa[0].replace(" [MoA]", "").replace(" [MoA]", "")
                logger.info(f"Got short mechanism from OpenFDA MoA for {drug_name}: {mechanism}")
                return mechanism

            logger.warning(f"No pharmacologic class found in OpenFDA for {drug_name}: {openfda}")
            return None

        except Exception as e:
            logger.error(f"OpenFDA API error for {drug_name}: {e}")
            return None

    def _get_drug_from_drugs_com(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Get drug info from Drugs.com scraping."""
        try:
            # Lazy load the scraper
            if self._drugs_com_scraper is None:
                try:
                    from src.tools.drugs_com_scraper import DrugsComScraper
                    self._drugs_com_scraper = DrugsComScraper()
                except ImportError:
                    logger.debug("Drugs.com scraper not available")
                    return None

            # Get approval timeline which includes indications
            approval_events = self._drugs_com_scraper.get_approval_timeline(drug_name)

            if not approval_events:
                return None

            # Extract unique indications
            indications = []
            for event in approval_events:
                indication = event.get("indication") or event.get("indication_normalized")
                if indication and indication not in indications:
                    indications.append(indication)

            if not indications:
                return None

            result = {
                "approved_indications": indications
            }

            # Try to get additional info
            if hasattr(self._drugs_com_scraper, 'get_drug_info'):
                info = self._drugs_com_scraper.get_drug_info(drug_name)
                if info:
                    result["generic_name"] = info.get("generic_name")
                    result["mechanism"] = info.get("mechanism")

            return result

        except Exception as e:
            logger.debug(f"Drugs.com scraper error for {drug_name}: {e}")
            return None

    def _get_drug_from_database(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Get drug info from database."""
        if not self.drug_db:
            return None

        try:
            # Search for drug
            cursor = self.drug_db.connection.cursor()
            cursor.execute("""
                SELECT
                    d.drug_id,
                    d.brand_name,
                    d.generic_name,
                    d.mechanism_of_action,
                    d.drug_type
                FROM drugs d
                WHERE d.brand_name ILIKE %s OR d.generic_name ILIKE %s
                LIMIT 1
            """, (f"%{drug_name}%", f"%{drug_name}%"))

            result = cursor.fetchone()
            if not result:
                return None

            drug_id, brand_name, generic_name, mechanism, drug_type = result

            # Get approved indications
            cursor.execute("""
                SELECT DISTINCT dis.disease_name_standard
                FROM drug_indications di
                JOIN diseases dis ON di.disease_id = dis.disease_id
                WHERE di.drug_id = %s AND di.approval_status = 'Approved'
            """, (drug_id,))

            indications = [row[0] for row in cursor.fetchall()]
            cursor.close()

            return {
                "drug_id": drug_id,
                "drug_name": brand_name or drug_name,
                "generic_name": generic_name,
                "mechanism": mechanism,
                "approved_indications": indications
            }

        except Exception as e:
            logger.error(f"Database query error: {e}")
            return None

    def _get_drug_info_from_web(self, drug_name: str) -> Dict[str, Any]:
        """Get drug info via web search."""
        if not self.web_search:
            return {"approved_indications": []}

        self.search_count += 1

        # Search for FDA approval information
        results = self.web_search.search(
            f"{drug_name} FDA approved indications mechanism of action",
            max_results=5
        )

        if not results:
            return {"approved_indications": []}

        # Use Claude to extract drug info
        prompt = self._prompts.render(
            "case_series/extract_drug_info",
            drug_name=drug_name,
            search_results=results[:8000]
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = response.content[0].text.strip()
            content = self._clean_json_response(content)
            return json.loads(content)
        except Exception as e:
            logger.error(f"Error extracting drug info: {e}")
            return {"approved_indications": []}

    def _find_drugs_by_mechanism(self, mechanism: str, max_drugs: int = 10) -> List[str]:
        """Find drugs with a given mechanism."""
        drugs = []

        # Try database first
        if self.drug_db:
            try:
                cursor = self.drug_db.connection.cursor()
                cursor.execute("""
                    SELECT DISTINCT brand_name, generic_name
                    FROM drugs
                    WHERE mechanism_of_action ILIKE %s
                    AND approval_status = 'Approved'
                    LIMIT %s
                """, (f"%{mechanism}%", max_drugs))

                for row in cursor.fetchall():
                    drugs.append(row[0] or row[1])
                cursor.close()

                if drugs:
                    return drugs
            except Exception as e:
                logger.error(f"Database query error: {e}")

        # Fall back to web search
        if self.web_search:
            self.search_count += 1
            results = self.web_search.search(
                f"{mechanism} approved drugs FDA list",
                max_results=10
            )

            if results:
                prompt = self._prompts.render(
                    "case_series/extract_drugs_by_mechanism",
                    mechanism=mechanism,
                    search_results=results[:6000]
                )

                try:
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=1000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    self._track_tokens(response.usage)

                    content = self._clean_json_response(response.content[0].text.strip())
                    drugs = json.loads(content)[:max_drugs]
                except Exception as e:
                    logger.error(f"Error extracting drugs: {e}")

        return drugs

    # =========================================================================
    # CASE SERIES SEARCH
    # =========================================================================

    def _search_case_series(
        self,
        drug_name: str,
        exclude_indications: List[str],
        max_papers: int = 200,
        include_web_search: bool = True,
        include_semantic_scholar: bool = True,
        include_citation_mining: bool = True,
        use_llm_filtering: bool = True,
        parallel_search: bool = True,
        generic_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Comprehensive search for case series and case reports.

        Multi-layer search strategy (runs in parallel for speed):
        1. Enhanced PubMed search - clinical data indicators, not just "case report"
        2. Semantic Scholar search - semantic relevance ranking
        3. Citation snowballing - mine references from review articles
        4. Web search - grey literature
        5. LLM filtering - Claude validates clinical data presence

        This approach finds papers that describe patient outcomes even if they
        don't explicitly use "case report" terminology.

        Args:
            parallel_search: If True, run search layers concurrently (faster but uses more resources)
            generic_name: Generic name of the drug (if different from brand name)
        """
        all_papers = []

        if parallel_search:
            # Run searches in parallel for speed optimization
            all_papers = self._search_parallel(
                drug_name,
                include_web_search,
                include_semantic_scholar,
                include_citation_mining,
                generic_name
            )
        else:
            # Sequential search (original behavior)
            seen_ids = set()
            all_papers.extend(self._search_pubmed_enhanced(drug_name, seen_ids, generic_name))

            if include_semantic_scholar:
                all_papers.extend(self._search_semantic_scholar(drug_name, seen_ids, generic_name))

            if include_citation_mining:
                all_papers.extend(self._mine_review_citations(drug_name, seen_ids, generic_name))

            if include_web_search and self.web_search:
                all_papers.extend(self._search_web(drug_name, seen_ids))

        # Deduplicate papers from parallel search
        papers = self._deduplicate_papers(all_papers)

        logger.info(f"Total papers from search: {len(papers)}")

        # Stage 2: LLM-based relevance filtering
        if use_llm_filtering and papers:
            logger.info(f"Filtering {len(papers)} papers with LLM for clinical relevance...")
            papers = self._filter_papers_with_llm(papers, drug_name, exclude_indications)
            logger.info(f"After LLM filtering: {len(papers)} relevant papers")

        # Check PMC availability for full text access
        pmids_to_check = [p.get('pmid') for p in papers if p.get('pmid')]
        if pmids_to_check:
            try:
                pmc_map = self.pubmed.check_pmc_availability(pmids_to_check)
                for paper in papers:
                    pmid = paper.get('pmid')
                    if pmid and pmid in pmc_map:
                        paper['pmcid'] = pmc_map[pmid]
                        paper['has_full_text'] = pmc_map[pmid] is not None
            except Exception as e:
                logger.warning(f"Could not check PMC availability: {e}")

        return papers

    def _search_parallel(
        self,
        drug_name: str,
        include_web_search: bool,
        include_semantic_scholar: bool,
        include_citation_mining: bool,
        generic_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Run all search layers in parallel for speed optimization.

        Returns combined results (deduplication done by caller).
        """
        all_papers = []
        search_tasks = []

        # Define search functions to run in parallel
        # Each returns (source_name, papers_list)
        def pubmed_search():
            seen = set()
            return ("PubMed", self._search_pubmed_enhanced(drug_name, seen, generic_name))

        def semantic_search():
            seen = set()
            return ("Semantic Scholar", self._search_semantic_scholar(drug_name, seen, generic_name))

        def citation_search():
            seen = set()
            return ("Citation Mining", self._mine_review_citations(drug_name, seen, generic_name))

        def web_search():
            seen = set()
            return ("Web Search", self._search_web(drug_name, seen))

        # Build task list
        search_tasks.append(pubmed_search)

        if include_semantic_scholar:
            search_tasks.append(semantic_search)

        if include_citation_mining:
            search_tasks.append(citation_search)

        if include_web_search and self.web_search:
            search_tasks.append(web_search)

        # Run in parallel with ThreadPoolExecutor
        logger.info(f"Running {len(search_tasks)} search layers in parallel...")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=len(search_tasks)) as executor:
            futures = {executor.submit(task): task.__name__ for task in search_tasks}

            for future in as_completed(futures):
                try:
                    source_name, papers = future.result()
                    logger.info(f"  {source_name}: {len(papers)} papers")
                    all_papers.extend(papers)
                except Exception as e:
                    task_name = futures[future]
                    logger.error(f"  {task_name} failed: {e}")

        elapsed = time.time() - start_time
        logger.info(f"Parallel search completed in {elapsed:.1f}s, {len(all_papers)} total papers (before dedup)")

        return all_papers

    def _deduplicate_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate papers based on PMID, DOI, or title similarity.

        Keeps the first occurrence (PubMed > Semantic Scholar > Citation Mining > Web).
        """
        seen_pmids = set()
        seen_dois = set()
        seen_titles = set()
        unique_papers = []

        for paper in papers:
            pmid = paper.get('pmid')
            doi = paper.get('doi')
            title = (paper.get('title') or '').lower().strip()

            # Check for duplicates
            is_duplicate = False

            if pmid and pmid in seen_pmids:
                is_duplicate = True
            elif doi and doi in seen_dois:
                is_duplicate = True
            elif title and len(title) > 20:
                # Fuzzy title match - normalize and check
                normalized_title = re.sub(r'[^\w\s]', '', title)[:100]
                if normalized_title in seen_titles:
                    is_duplicate = True

            if not is_duplicate:
                unique_papers.append(paper)
                if pmid:
                    seen_pmids.add(pmid)
                if doi:
                    seen_dois.add(doi)
                if title and len(title) > 20:
                    normalized_title = re.sub(r'[^\w\s]', '', title)[:100]
                    seen_titles.add(normalized_title)

        logger.info(f"Deduplication: {len(papers)} -> {len(unique_papers)} papers")
        return unique_papers

    def _search_pubmed_enhanced(
        self,
        drug_name: str,
        seen_ids: Set[str],
        generic_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Enhanced PubMed search with precision-preserving query expansion.

        Uses clinical data indicators to find papers with patient outcomes
        even if they don't use "case report" terminology.

        Searches for BOTH brand name and generic name to maximize recall.
        """
        papers = []

        # Build drug name search term (brand name OR generic name)
        # This ensures we find papers indexed under either name
        if generic_name and generic_name.lower() != drug_name.lower():
            drug_search_term = f'("{drug_name}"[Title/Abstract] OR "{generic_name}"[Title/Abstract])'
            logger.info(f"Searching for both brand name '{drug_name}' and generic name '{generic_name}'")
        else:
            drug_search_term = f'"{drug_name}"[Title/Abstract]'
            logger.info(f"Searching for drug name '{drug_name}' only")

        # Exclusion terms - filter out non-clinical papers
        # NOTE: We allow RCTs through at search level - LLM filtering will distinguish
        # investigator-sponsored vs manufacturer-sponsored trials later
        # Only exclude Phase III (pivotal/registration trials) at search level
        exclusion_terms = 'NOT ("Review"[Publication Type] OR "Systematic Review"[Publication Type] OR "Meta-Analysis"[Publication Type] OR "Guideline"[Publication Type] OR "Editorial"[Publication Type] OR "Clinical Trial, Phase III"[Publication Type])'

        # Clinical data indicators - terms suggesting patient-level data
        clinical_indicators = '("patients treated" OR "treated with" OR "received treatment" OR "treatment response" OR "clinical response" OR "our experience" OR "retrospective" OR "case series" OR "case report")'

        # Publication types with clinical data
        clinical_pub_types = '("Case Reports"[Publication Type] OR "Clinical Study"[Publication Type] OR "Observational Study"[Publication Type])'

        # Build enhanced query set
        pubmed_queries = [
            # Original case report search (proven effective)
            f'{drug_search_term} AND {clinical_pub_types} {exclusion_terms}',

            # Clinical indicator search (finds case series without "case" in title)
            f'{drug_search_term} AND {clinical_indicators} {exclusion_terms}',

            # Off-label searches (keep these)
            f'{drug_search_term} AND ("off-label" OR "off label") {exclusion_terms}',
            f'{drug_search_term} AND ("expanded access" OR "compassionate use") {exclusion_terms}',
            f'{drug_search_term} AND "repurpos"[Title/Abstract] {exclusion_terms}',

            # Pediatric/juvenile with clinical data (NEW - catches JDM)
            f'{drug_search_term} AND (pediatric OR juvenile OR children) AND (treated OR response OR outcome OR patients) {exclusion_terms}',

            # Common autoimmune conditions with clinical data (NEW)
            f'{drug_search_term} AND (dermatomyositis OR myositis OR lupus OR vasculitis) AND (patients OR treated OR response) {exclusion_terms}',

            # Retrospective/cohort studies (NEW - often contain case data)
            f'{drug_search_term} AND (retrospective OR "cohort study" OR observational) AND (efficacy OR outcome OR response) {exclusion_terms}',
        ]

        papers_per_query = 40  # Get reasonable number per query

        for query in pubmed_queries:
            try:
                logger.info(f"PubMed search: {query[:80]}...")
                pmids = self.pubmed.search(query, max_results=papers_per_query)
                self.search_count += 1

                if pmids:
                    new_pmids = [p for p in pmids if p not in seen_ids]
                    seen_ids.update(new_pmids)

                    if new_pmids:
                        abstracts = self.pubmed.fetch_abstracts(new_pmids)
                        for paper in abstracts:
                            paper['source'] = 'PubMed'
                            paper['search_query'] = query[:100]
                            papers.append(paper)
                        logger.info(f"  Found {len(new_pmids)} new papers")

                time.sleep(0.3)

            except Exception as e:
                logger.error(f"PubMed search error: {e}")

        logger.info(f"PubMed enhanced search: {len(papers)} total papers")
        return papers

    def _search_semantic_scholar(
        self,
        drug_name: str,
        seen_ids: Set[str],
        generic_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Search Semantic Scholar for papers using semantic relevance ranking.

        Better at finding relevant papers that use different terminology.
        Searches for both brand name and generic name if available.
        """
        papers = []

        # Build list of drug names to search
        drug_names = [drug_name]
        if generic_name and generic_name.lower() != drug_name.lower():
            drug_names.append(generic_name)
            logger.info(f"Semantic Scholar: searching for both '{drug_name}' and '{generic_name}'")

        # Semantic search queries (neural embedding based, not keyword)
        # 3 queries for balanced coverage and speed
        ss_queries = []
        for name in drug_names:
            ss_queries.extend([
                f"{name} case report case series treatment outcomes patients",
                f"{name} off-label compassionate use clinical efficacy",
                f"{name} refractory resistant disease treatment response",
            ])

        for query in ss_queries:
            try:
                logger.info(f"Semantic Scholar search: {query}")
                results = self.semantic_scholar.search_papers(
                    query,
                    limit=40,  # Get more per query since fewer queries
                    publication_types=["CaseReport", "JournalArticle"]
                )
                self.search_count += 1

                for paper in results:
                    # Get identifiers for deduplication
                    external_ids = paper.get("externalIds") or {}
                    pmid = external_ids.get("PubMed")
                    doi = external_ids.get("DOI")
                    s2_id = paper.get("paperId")

                    # Check if we've seen this paper
                    if pmid and pmid in seen_ids:
                        continue
                    if doi and doi in seen_ids:
                        continue
                    if s2_id and s2_id in seen_ids:
                        continue

                    # Mark as seen
                    if pmid:
                        seen_ids.add(pmid)
                    if doi:
                        seen_ids.add(doi)
                    if s2_id:
                        seen_ids.add(s2_id)

                    # Format for our pipeline
                    formatted = self.semantic_scholar.format_paper_for_case_series(paper)
                    formatted['search_query'] = query
                    papers.append(formatted)

            except Exception as e:
                logger.error(f"Semantic Scholar search error: {e}")

        logger.info(f"Semantic Scholar search: {len(papers)} papers")
        return papers

    def _mine_review_citations(
        self,
        drug_name: str,
        seen_ids: Set[str],
        generic_name: str = None
    ) -> List[Dict[str, Any]]:
        """
        Citation snowballing strategy: find review articles and extract their references.

        Reviews aggregate all case studies in a field - mining their references
        gives comprehensive coverage even for papers that don't match our queries.
        Searches for both brand name and generic name if available.
        """
        papers = []

        # Build list of drug names to search
        drug_names = [drug_name]
        if generic_name and generic_name.lower() != drug_name.lower():
            drug_names.append(generic_name)
            logger.info(f"Citation mining: searching for both '{drug_name}' and '{generic_name}'")

        for name in drug_names:
            try:
                logger.info(f"Mining citations from review articles for {name}...")

                # Get references from review articles (3 reviews x 50 refs for balanced coverage)
                review_refs = self.semantic_scholar.mine_review_references(
                    name,
                    disease_area=None,  # Search broadly
                    max_reviews=3,
                    max_refs_per_review=50
                )
                self.search_count += 1

                for paper in review_refs:
                    # Get identifiers for deduplication
                    external_ids = paper.get("externalIds") or {}
                    pmid = external_ids.get("PubMed")
                    doi = external_ids.get("DOI")
                    s2_id = paper.get("paperId")

                    # Check if we've seen this paper
                    if pmid and pmid in seen_ids:
                        continue
                    if doi and doi in seen_ids:
                        continue
                    if s2_id and s2_id in seen_ids:
                        continue

                    # Mark as seen
                    if pmid:
                        seen_ids.add(pmid)
                    if doi:
                        seen_ids.add(doi)
                    if s2_id:
                        seen_ids.add(s2_id)

                    # Format for our pipeline
                    formatted = self.semantic_scholar.format_paper_for_case_series(paper)
                    formatted['source'] = 'Citation Mining'
                    papers.append(formatted)

                logger.info(f"Citation mining for {name}: {len(review_refs)} papers from review references")

            except Exception as e:
                logger.error(f"Citation mining error for {name}: {e}")

        logger.info(f"Citation mining total: {len(papers)} papers")
        return papers

    def _search_web(
        self,
        drug_name: str,
        seen_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Web search for grey literature and conference presentations.
        """
        papers = []

        web_queries = [
            f"{drug_name} case report",
            f"{drug_name} case series patient outcomes",
            f"{drug_name} off-label treatment efficacy",
        ]

        for query in web_queries:
            try:
                logger.info(f"Web search: {query}")
                results = self.web_search.search(query, max_results=10)
                self.search_count += 1

                for result in results:
                    title = result.get('title', '')
                    url = result.get('url', '')
                    if url and url not in seen_ids:
                        seen_ids.add(url)
                        papers.append({
                            'title': title,
                            'abstract': result.get('content', ''),
                            'url': url,
                            'source': 'Web Search',
                            'search_query': query
                        })

                time.sleep(0.3)

            except Exception as e:
                logger.error(f"Web search error: {e}")

        logger.info(f"Web search: {len(papers)} papers")
        return papers

    def _filter_papers_with_llm(
        self,
        papers: List[Dict[str, Any]],
        drug_name: str,
        exclude_indications: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Use Claude to evaluate paper relevance based on abstract.

        Filters for papers that contain:
        - Original clinical data (case reports, case series, cohorts)
        - Patient outcomes/efficacy data
        - Off-label or novel indication use

        Excludes:
        - Reviews, guidelines, consensus statements
        - Basic science / mechanistic studies without patients
        - PK/PD studies without efficacy outcomes
        - Approved indication studies

        Also caches all papers to database for future runs.
        """
        if not papers:
            return []

        # Build exclusion list for prompt
        exclude_str = ", ".join(exclude_indications) if exclude_indications else "None specified"

        # Check cache for papers that have already been filtered
        papers_to_filter = []
        filtered_papers = []
        cache_hits = 0

        for paper in papers:
            pmid = paper.get('pmid')
            if pmid and self.cs_db:
                cached = self.cs_db.check_paper_relevance(pmid, drug_name)
                if cached:
                    # Use cached relevance assessment
                    cache_hits += 1
                    if cached.get('is_relevant'):
                        paper['llm_relevance_reason'] = cached.get('relevance_reason', '')
                        paper['extracted_disease'] = cached.get('extracted_disease')
                        filtered_papers.append(paper)
                    continue

            # Need to filter this paper
            papers_to_filter.append(paper)

        if cache_hits > 0:
            logger.info(f"  Using cached relevance for {cache_hits} papers")

        if not papers_to_filter:
            logger.info(f"  All papers found in cache")
            return filtered_papers

        # Process in batches to reduce API calls
        batch_size = 10

        for i in range(0, len(papers_to_filter), batch_size):
            batch = papers_to_filter[i:i + batch_size]

            # Build batch prompt
            papers_text = ""
            for idx, paper in enumerate(batch, 1):
                title = paper.get('title') or 'No title'
                abstract = paper.get('abstract') or 'No abstract available'
                abstract = abstract[:1500]  # Limit abstract length
                papers_text += f"\n---PAPER {idx}---\nTitle: {title}\nAbstract: {abstract}\n"

            prompt = self._prompts.render(
                "case_series/filter_papers",
                drug_name=drug_name,
                exclude_indications=exclude_str,
                papers_text=papers_text,
                batch_size=len(batch)
            )

            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}]
                )

                # Track tokens
                self.total_input_tokens += response.usage.input_tokens
                self.total_output_tokens += response.usage.output_tokens

                # Parse response
                result_text = response.content[0].text.strip()

                # Extract JSON
                if '```json' in result_text:
                    result_text = result_text.split('```json')[1].split('```')[0]
                elif '```' in result_text:
                    result_text = result_text.split('```')[1].split('```')[0]

                result = json.loads(result_text)
                evaluations = result.get('evaluations', [])

                # Filter papers based on evaluation AND save to database
                for eval_item in evaluations:
                    paper_idx = eval_item.get('paper_index', 0) - 1
                    if 0 <= paper_idx < len(batch):
                        paper = batch[paper_idx]
                        is_relevant = eval_item.get('include', False)
                        relevance_reason = eval_item.get('reason', '')
                        extracted_disease = eval_item.get('disease')

                        # Save paper to database (regardless of relevance)
                        if self.cs_db and paper.get('pmid'):
                            self.cs_db.save_paper(
                                pmid=paper['pmid'],
                                drug_name=drug_name,
                                title=paper.get('title', ''),
                                abstract=paper.get('abstract'),
                                year=paper.get('year'),
                                is_relevant=is_relevant,
                                relevance_score=1.0 if is_relevant else 0.0,
                                relevance_reason=relevance_reason,
                                extracted_disease=extracted_disease,
                                source=paper.get('source'),
                                journal=paper.get('journal'),
                                authors=paper.get('authors')
                            )

                        # Add to filtered list if relevant
                        if is_relevant:
                            paper['llm_relevance_reason'] = relevance_reason
                            paper['extracted_disease'] = extracted_disease
                            filtered_papers.append(paper)

                logger.info(f"  Batch {i//batch_size + 1}: {len([e for e in evaluations if e.get('include')])} of {len(batch)} papers relevant")

            except Exception as e:
                logger.error(f"LLM filtering error for batch {i//batch_size + 1}: {e}")
                # On error, include all papers from batch (fail-open)
                filtered_papers.extend(batch)

            time.sleep(0.5)  # Rate limiting between batches

        return filtered_papers

    def _is_case_report_title(self, title: str, approved_indications: List[str] = None) -> bool:
        """
        Filter paper titles to identify actual case reports/series vs reviews/guidelines.

        Returns True if the paper appears to be an original case report/series.
        Returns False if it appears to be a review, guideline, or non-case-report paper.

        This function is STRICT - papers must have at least one include term
        to be included, unless they're from a case report search specifically.
        """
        title_lower = title.lower()

        # Exclude terms - papers with these in the title are likely NOT case reports
        exclude_terms = [
            # Reviews and meta-analyses
            'systematic review', 'meta-analysis', 'meta analysis',
            'narrative review', 'literature review', 'review of',
            'scoping review', 'umbrella review',
            # Guidelines and consensus
            'guideline', 'consensus', 'recommendation',
            'expert opinion', 'position statement', 'position paper',
            'expert statement',
            # Overviews and summaries
            'overview of', 'update on', 'advances in',
            'future directions', 'current landscape', 'therapeutic landscape',
            'state of the art', 'state-of-the-art',
            # Basic science / mechanism papers
            'mechanisms of', 'pathophysiology', 'pathogenesis',
            'molecular basis', 'signaling pathway',
            # PK/PD and methods papers
            'pharmacokinetics', 'pharmacodynamics', 'pk/pd',
            'drug monitoring', 'therapeutic drug monitoring',
            'lc-ms', 'hplc', 'assay', 'bioanalytical',
            'dosing of', 'dose-finding', 'dose finding',
            # Clinical trial design (not results)
            'clinical trials approved', 'trial design', 'study protocol',
            'proposed dosing', 'dosing recommendation',
            # Reference materials
            'statpearls', 'ncbi bookshelf', 'medscape', 'uptodate',
            'drug monograph', 'prescribing information',
            # Safety/risk only papers (no efficacy)
            'risk of major cardiovascular', 'black box warning',
            'safety warning', 'fda warning',
            # Other non-case-reports
            'fill the unmet medical need', 'main results',
            'artificial intelligence-predicted', 'ai-predicted',
            'cost-effectiveness', 'economic analysis',
            'registry data', 'claims database', 'insurance claims',
            # Manufacturer-sponsored trials indicators (we allow investigator-sponsored trials)
            # NOTE: We do NOT exclude all RCTs - only clear manufacturer/pivotal trial indicators
            'pivotal trial', 'pivotal study', 'registration trial',
            'industry-sponsored', 'manufacturer-sponsored',
            'phase 3 trial', 'phase iii trial', 'phase 3 study', 'phase iii study',
            # Large commercial trial names are often all-caps acronyms
        ]

        # If title contains exclude terms, filter it out
        for term in exclude_terms:
            if term in title_lower:
                logger.debug(f"Filtering out (exclude term '{term}'): {title[:60]}")
                return False

        # Exclude papers about approved indications (we want off-label uses)
        if approved_indications:
            for indication in approved_indications:
                indication_lower = indication.lower()
                # Check for exact match or key words from the indication
                if indication_lower in title_lower:
                    logger.debug(f"Filtering out (approved indication '{indication}'): {title[:60]}")
                    return False
                # Check common abbreviations/variants
                indication_keywords = indication_lower.split()
                # Only filter if major keyword found (e.g., "covid-19" or "rheumatoid")
                for kw in indication_keywords:
                    if len(kw) > 5 and kw in title_lower:
                        # Don't filter out if also has "off-label" or "repurpos"
                        if 'off-label' not in title_lower and 'off label' not in title_lower and 'repurpos' not in title_lower:
                            logger.debug(f"Filtering out (approved indication keyword '{kw}'): {title[:60]}")
                            return False

        # Include terms - papers with these are likely case reports
        include_terms = [
            'case report', 'case series', 'case study', 'cases of',
            'retrospective', 'prospective',
            'off-label', 'off label', 'compassionate use',
            'expanded access', 'successful treatment',
            'treated with', 'treatment of', 'efficacy of',
            'effectiveness of', 'response to', 'experience with',
            'clinical experience', 'real-world', 'real world',
            'single-center', 'single center', 'multicenter',
            'patient with', 'patients with'
        ]

        # STRICT: Only include papers that have at least one include term
        for term in include_terms:
            if term in title_lower:
                return True

        # If no include terms found, reject the paper
        logger.debug(f"Filtering out (no include terms): {title[:60]}")
        return False

    # =========================================================================
    # PAPER GROUPING
    # =========================================================================

    def group_papers_by_disease(
        self,
        papers: List[Dict[str, Any]],
        drug_name: str,
        drug_info: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group papers by disease/indication using Claude to extract the disease from each paper.

        For drug-only input: Returns {disease: [papers]}

        Args:
            papers: List of paper dictionaries
            drug_name: Name of the drug being analyzed
            drug_info: Drug information dict with approved indications

        Returns:
            Dict mapping disease names to lists of papers
        """
        logger.info(f"Grouping {len(papers)} papers by disease for {drug_name}")

        grouped = defaultdict(list)
        approved_indications = set(ind.lower() for ind in drug_info.get('approved_indications', []))

        for paper in papers:
            try:
                disease = self._extract_disease_from_paper(paper, drug_name, drug_info)

                if disease:
                    # Skip if it's an approved indication
                    if disease.lower() in approved_indications:
                        logger.debug(f"Skipping approved indication: {disease}")
                        continue

                    # Normalize disease name
                    disease = self._normalize_disease_name(disease)
                    paper['extracted_disease'] = disease
                    grouped[disease].append(paper)
                else:
                    grouped['Unknown/Unclassified'].append(paper)

            except Exception as e:
                logger.warning(f"Error extracting disease from paper: {e}")
                grouped['Unknown/Unclassified'].append(paper)

        # Convert to regular dict and sort by paper count
        result = dict(sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True))

        logger.info(f"Grouped papers into {len(result)} disease categories")
        for disease, disease_papers in result.items():
            logger.info(f"  {disease}: {len(disease_papers)} papers")

        return result

    def group_papers_by_disease_and_drug(
        self,
        papers_by_drug: Dict[str, List[Dict[str, Any]]],
        drug_infos: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Group papers by disease first, then by drug within each disease.

        For mechanism-first input: Returns {disease: {drug: [papers]}}

        Args:
            papers_by_drug: Dict mapping drug names to their papers
            drug_infos: Dict mapping drug names to their info dicts

        Returns:
            Dict mapping disease names to dicts mapping drug names to papers
        """
        logger.info(f"Grouping papers by disease → drug for {len(papers_by_drug)} drugs")

        # First, extract disease from each paper and tag with drug
        disease_drug_papers = defaultdict(lambda: defaultdict(list))

        for drug_name, papers in papers_by_drug.items():
            drug_info = drug_infos.get(drug_name, {})
            approved_indications = set(ind.lower() for ind in drug_info.get('approved_indications', []))

            for paper in papers:
                try:
                    disease = self._extract_disease_from_paper(paper, drug_name, drug_info)

                    if disease:
                        # Skip if approved indication for this drug
                        if disease.lower() in approved_indications:
                            continue

                        disease = self._normalize_disease_name(disease)
                        paper['extracted_disease'] = disease
                        paper['drug_name'] = drug_name
                        disease_drug_papers[disease][drug_name].append(paper)
                    else:
                        disease_drug_papers['Unknown/Unclassified'][drug_name].append(paper)

                except Exception as e:
                    logger.warning(f"Error extracting disease: {e}")
                    disease_drug_papers['Unknown/Unclassified'][drug_name].append(paper)

        # Convert to regular dicts and sort
        result = {}
        for disease in sorted(disease_drug_papers.keys(),
                             key=lambda d: sum(len(papers) for papers in disease_drug_papers[d].values()),
                             reverse=True):
            result[disease] = dict(disease_drug_papers[disease])

        logger.info(f"Grouped into {len(result)} disease categories across {len(papers_by_drug)} drugs")
        return result

    def _extract_disease_from_paper(
        self,
        paper: Dict[str, Any],
        drug_name: str,
        drug_info: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract the disease/indication being treated from a paper using Claude.

        Args:
            paper: Paper dictionary with title and abstract
            drug_name: Name of the drug
            drug_info: Drug information dict

        Returns:
            Disease name or None if cannot be determined
        """
        # Check if already extracted
        if paper.get('extracted_disease'):
            return paper['extracted_disease']

        title = paper.get('title', '')
        abstract = paper.get('abstract', paper.get('content', ''))[:2000]

        if not title and not abstract:
            return None

        approved_indications = drug_info.get('approved_indications', [])
        approved_str = ", ".join(approved_indications) if approved_indications else "Unknown"

        prompt = self._prompts.render(
            "case_series/extract_disease",
            drug_name=drug_name,
            approved_indications=approved_str,
            title=title,
            abstract=abstract
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            disease = response.content[0].text.strip()

            # Clean up response
            disease = disease.replace('"', '').replace("'", '').strip()

            if disease.upper() in ['APPROVED_INDICATION', 'UNKNOWN', 'N/A', 'NONE']:
                return None

            return disease

        except Exception as e:
            logger.error(f"Error extracting disease: {e}")
            return None

    def _normalize_disease_name(self, disease: str) -> str:
        """
        Normalize disease names for consistent grouping.

        Args:
            disease: Raw disease name

        Returns:
            Normalized disease name
        """
        if not disease:
            return "Unknown"

        # Common normalizations
        normalizations = {
            'aa': 'Alopecia Areata',
            'alopecia areata': 'Alopecia Areata',
            'vitiligo': 'Vitiligo',
            'ad': 'Atopic Dermatitis',
            'atopic dermatitis': 'Atopic Dermatitis',
            'psoriasis': 'Psoriasis',
            'ra': 'Rheumatoid Arthritis',
            'rheumatoid arthritis': 'Rheumatoid Arthritis',
            'sle': 'Systemic Lupus Erythematosus',
            'lupus': 'Systemic Lupus Erythematosus',
            'systemic lupus erythematosus': 'Systemic Lupus Erythematosus',
            'covid': 'COVID-19',
            'covid-19': 'COVID-19',
            'coronavirus': 'COVID-19',
            'gvhd': 'Graft-Versus-Host Disease',
            'graft versus host disease': 'Graft-Versus-Host Disease',
            'graft-versus-host disease': 'Graft-Versus-Host Disease',
            'chronic gvhd': 'Chronic Graft-Versus-Host Disease',
            'ibd': 'Inflammatory Bowel Disease',
            'ulcerative colitis': 'Ulcerative Colitis',
            "crohn's disease": "Crohn's Disease",
            'crohn disease': "Crohn's Disease",
            'lichen planus': 'Lichen Planus',
            'dermatomyositis': 'Dermatomyositis',
            'sarcoidosis': 'Sarcoidosis',
            'hidradenitis suppurativa': 'Hidradenitis Suppurativa',
            'hs': 'Hidradenitis Suppurativa',
        }

        disease_lower = disease.lower().strip()

        # Check direct matches
        if disease_lower in normalizations:
            return normalizations[disease_lower]

        # Check partial matches
        for key, normalized in normalizations.items():
            if key in disease_lower:
                return normalized

        # Title case for consistency
        return disease.strip().title()

    # =========================================================================
    # DATA EXTRACTION
    # =========================================================================

    def _extract_case_series_data(
        self,
        drug_name: str,
        drug_info: Dict[str, Any],
        paper: Dict[str, Any],
        fetch_full_text: bool = True
    ) -> Optional[CaseSeriesExtraction]:
        """Extract structured data from a case series/report using Claude.

        Uses multi-stage extraction for full-text papers (>2000 chars) to get
        detailed efficacy and safety endpoints. Falls back to single-pass for
        abstract-only papers.

        Args:
            drug_name: Name of the drug
            drug_info: Drug information dict
            paper: Paper dict with title, abstract, pmid, pmcid, etc.
            fetch_full_text: If True, attempt to fetch full text from PMC for better extraction
        """
        pmid = paper.get('pmid', '')
        title = paper.get('title', 'Unknown')
        abstract = paper.get('abstract', paper.get('content', ''))

        # Check cache for existing extraction
        if self.cs_db and pmid:
            cached = self.cs_db.load_extraction(drug_name, pmid)
            if cached:
                logger.info(f"Using cached extraction for PMID {pmid}")
                self._cache_stats['papers_from_cache'] += 1
                # Estimate tokens saved (average extraction is ~2000 tokens)
                self._cache_stats['tokens_saved_by_cache'] += 2000
                return cached

        # Try to fetch full text from PMC if available and enabled
        full_text_content = None
        if fetch_full_text and paper.get('pmcid'):
            pmcid = paper.get('pmcid')
            logger.info(f"Fetching full text from PMC for {pmcid}...")
            try:
                fulltext_xml = self.pubmed.fetch_pmc_fulltext(pmcid)
                if fulltext_xml:
                    parsed = self.pubmed._parse_pmc_fulltext(
                        fulltext_xml,
                        paper.get('pmid', ''),
                        pmcid
                    )
                    if parsed and parsed.get('content'):
                        full_text_content = parsed.get('content')
                        # Limit to 40000 chars for multi-stage extraction
                        if len(full_text_content) > 40000:
                            full_text_content = full_text_content[:40000] + "\n\n[... content truncated ...]"
                        logger.info(f"Successfully fetched {len(full_text_content)} chars of full text")
            except Exception as e:
                logger.warning(f"Failed to fetch PMC full text: {e}")

        # Use full text if available, otherwise abstract
        content_for_extraction = full_text_content or abstract

        if not content_for_extraction or len(content_for_extraction) < 50:
            logger.warning(f"Skipping paper with insufficient content: {title[:50]}")
            return None

        # Determine extraction method based on content length
        use_multi_stage = (
            full_text_content is not None and
            len(full_text_content) >= MIN_FULLTEXT_LENGTH
        )

        # Update paper dict with full text for prompt generation
        paper_with_content = paper.copy()
        if full_text_content:
            paper_with_content['full_text'] = full_text_content
            paper_with_content['has_full_text_content'] = True

        # Multi-stage detailed extraction for full-text papers
        multi_stage_results = None
        if use_multi_stage:
            logger.info(f"Using MULTI-STAGE extraction for full-text paper ({len(full_text_content)} chars)")
            try:
                extractor = CaseSeriesDataExtractor(self.client, self.model)
                multi_stage_results = extractor.extract_multi_stage(
                    paper_content=full_text_content,
                    drug_name=drug_name,
                    drug_info=drug_info,
                    paper_metadata=paper
                )
                # Track tokens from multi-stage extraction
                self.total_input_tokens += extractor.extraction_metrics.get('input_tokens', 0)
                self.total_output_tokens += extractor.extraction_metrics.get('output_tokens', 0)
                self.total_cache_creation_tokens += extractor.extraction_metrics.get('cache_creation_tokens', 0)
                self.total_cache_read_tokens += extractor.extraction_metrics.get('cache_read_tokens', 0)

                logger.info(f"Multi-stage extraction complete. Stages: {multi_stage_results.get('stages_completed', [])}")
                logger.info(f"  - Efficacy endpoints: {len(multi_stage_results.get('detailed_efficacy_endpoints', []))}")
                logger.info(f"  - Safety endpoints: {len(multi_stage_results.get('detailed_safety_endpoints', []))}")
            except Exception as e:
                logger.error(f"Multi-stage extraction failed: {e}. Falling back to single-pass.")
                multi_stage_results = None
        else:
            logger.info(f"Using single-pass extraction (content length: {len(content_for_extraction)} chars)")

        # Single-pass extraction (always run for basic data)
        prompt = self._get_extraction_prompt(drug_name, drug_info, paper_with_content)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = response.content[0].text.strip()
            content = self._clean_json_response(content)

            data = json.loads(content)

            # Build extraction object
            extraction = self._build_extraction_from_data(data, paper, drug_name, drug_info)

            # Enrich with multi-stage results if available
            if extraction and multi_stage_results:
                extraction = self._enrich_with_multi_stage(extraction, multi_stage_results)

            return extraction

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return None
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return None
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return None

    def _enrich_with_multi_stage(
        self,
        extraction: CaseSeriesExtraction,
        multi_stage_results: Dict[str, Any]
    ) -> CaseSeriesExtraction:
        """Enrich extraction with multi-stage detailed endpoints."""

        # Convert detailed efficacy endpoints
        detailed_efficacy = []
        for ep in multi_stage_results.get('detailed_efficacy_endpoints', []):
            try:
                detailed_efficacy.append(DetailedEfficacyEndpoint(**ep))
            except Exception as e:
                logger.warning(f"Failed to parse efficacy endpoint: {e}")

        # Convert detailed safety endpoints
        detailed_safety = []
        for ep in multi_stage_results.get('detailed_safety_endpoints', []):
            try:
                detailed_safety.append(DetailedSafetyEndpoint(**ep))
            except Exception as e:
                logger.warning(f"Failed to parse safety endpoint: {e}")

        # Update extraction with multi-stage data
        extraction.detailed_efficacy_endpoints = detailed_efficacy
        extraction.detailed_safety_endpoints = detailed_safety
        extraction.extraction_method = 'multi_stage'
        extraction.extraction_stages_completed = multi_stage_results.get('stages_completed', [])
        extraction.data_sections_identified = multi_stage_results.get('sections_identified')

        # Boost confidence if multi-stage extraction succeeded
        if detailed_efficacy or detailed_safety:
            extraction.extraction_confidence = min(extraction.extraction_confidence + 0.1, 1.0)

        logger.info(f"Enriched extraction with {len(detailed_efficacy)} efficacy and {len(detailed_safety)} safety endpoints")

        return extraction

    def _get_extraction_prompt(
        self,
        drug_name: str,
        drug_info: Dict[str, Any],
        paper: Dict[str, Any]
    ) -> str:
        """Build extraction prompt for Claude."""

        approved_indications = drug_info.get('approved_indications', [])
        approved_str = ", ".join(approved_indications) if approved_indications else "Unknown"

        # Use full text if available, otherwise abstract
        if paper.get('has_full_text_content') and paper.get('full_text'):
            content = paper.get('full_text')
            content_label = "FULL TEXT"
        else:
            content = paper.get('abstract', paper.get('content', 'N/A'))
            content = (content or 'N/A')[:4000]  # Limit abstract to 4000 chars
            content_label = "Abstract"

        return self._prompts.render(
            "case_series/main_extraction",
            drug_name=drug_name,
            mechanism=drug_info.get('mechanism', 'Unknown'),
            approved_indications=approved_str,
            paper_title=paper.get('title', 'N/A'),
            content_label=content_label,
            content=content
        )

    def _build_extraction_from_data(
        self,
        data: Dict[str, Any],
        paper: Dict[str, Any],
        drug_name: str,
        drug_info: Dict[str, Any]
    ) -> Optional[CaseSeriesExtraction]:
        """Build CaseSeriesExtraction from extracted data.

        Returns extraction even if irrelevant (for database caching).
        The extraction will have is_relevant=False flag set.
        """

        # Build source
        source = CaseSeriesSource(
            pmid=paper.get('pmid'),
            doi=paper.get('doi'),
            url=paper.get('url'),
            title=paper.get('title', 'Unknown'),
            authors=data.get('authors'),
            journal=data.get('journal'),
            year=data.get('year'),
            publication_venue="Peer-reviewed journal" if paper.get('source') == 'PubMed' else "Web source"
        )

        # Build patient population
        patient_pop = PatientPopulation(
            n_patients=data.get('n_patients', 1),
            description=data.get('patient_description'),
            prior_treatments_failed=data.get('prior_treatments_failed')
        )

        # Build treatment details
        treatment = TreatmentDetails(
            drug_name=drug_name,
            generic_name=drug_info.get('generic_name'),
            mechanism=drug_info.get('mechanism'),
            target=drug_info.get('target'),
            route_of_administration=data.get('route'),
            dose=data.get('dose'),
            duration=data.get('duration')
        )

        # Build efficacy outcome
        efficacy = EfficacyOutcome(
            response_rate=data.get('response_rate'),
            responders_n=data.get('responders_n'),
            responders_pct=data.get('responders_pct'),
            time_to_response=data.get('time_to_response'),
            duration_of_response=data.get('duration_of_response'),
            effect_size_description=data.get('effect_size_description'),
            primary_endpoint=data.get('primary_endpoint'),
            endpoint_result=data.get('endpoint_result'),
            efficacy_summary=data.get('efficacy_summary')
        )

        # Build safety outcome
        safety = SafetyOutcome(
            adverse_events=data.get('adverse_events', []),
            serious_adverse_events=data.get('serious_adverse_events', []),
            sae_count=data.get('sae_count'),
            sae_percentage=data.get('sae_percentage'),
            discontinuations_n=data.get('discontinuations_n'),
            discontinuation_reasons=data.get('discontinuation_reasons', []),
            safety_summary=data.get('safety_summary'),
            safety_profile=SafetyProfile(data.get('safety_profile', 'Unknown'))
        )

        # Map enums
        evidence_level = EvidenceLevel.CASE_REPORT
        if 'series' in data.get('evidence_level', '').lower():
            evidence_level = EvidenceLevel.CASE_SERIES
        elif 'retrospective' in data.get('evidence_level', '').lower():
            evidence_level = EvidenceLevel.RETROSPECTIVE_STUDY

        outcome_result = OutcomeResult.UNKNOWN
        if data.get('outcome_result'):
            try:
                outcome_result = OutcomeResult(data['outcome_result'])
            except ValueError:
                pass

        efficacy_signal = EfficacySignal.UNKNOWN
        if data.get('efficacy_signal'):
            try:
                efficacy_signal = EfficacySignal(data['efficacy_signal'])
            except ValueError:
                pass

        return CaseSeriesExtraction(
            source=source,
            disease=data.get('disease', 'Unknown'),
            is_off_label=True,
            is_relevant=data.get('is_relevant', True),  # Set from extraction data
            evidence_level=evidence_level,
            patient_population=patient_pop,
            treatment=treatment,
            efficacy=efficacy,
            safety=safety,
            outcome_result=outcome_result,
            efficacy_signal=efficacy_signal,
            follow_up_duration=data.get('follow_up_duration'),
            key_findings=data.get('key_findings')
        )

    # =========================================================================
    # DISEASE STANDARDIZATION
    # =========================================================================

    def standardize_disease_names(
        self,
        opportunities: List[RepurposingOpportunity]
    ) -> List[RepurposingOpportunity]:
        """Standardize disease names across extractions using LLM.

        Groups similar/related diseases under canonical names to avoid
        duplicate market intelligence searches and improve reporting.
        """
        if not opportunities:
            return opportunities

        # Collect all unique disease names
        disease_names = list(set(opp.extraction.disease for opp in opportunities))

        if len(disease_names) <= 1:
            return opportunities

        prompt = self._prompts.render(
            "case_series/standardize_diseases",
            disease_names=disease_names
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            disease_mapping = json.loads(content)

            # Apply mapping to opportunities - always set disease_normalized
            standardized_count = 0
            for opp in opportunities:
                original = opp.extraction.disease
                if original in disease_mapping:
                    standardized = disease_mapping[original]
                    # Always set disease_normalized (even if same as original)
                    opp.extraction.disease_normalized = standardized
                    if standardized != original:
                        standardized_count += 1
                        logger.info(f"Standardized disease: '{original}' -> '{standardized}'")
                else:
                    # If not in mapping, set normalized to original
                    opp.extraction.disease_normalized = original

            logger.info(f"Disease standardization complete: {standardized_count} names standardized out of {len(opportunities)}")
            return opportunities

        except Exception as e:
            logger.error(f"Error standardizing disease names: {e}")
            return opportunities

    # =========================================================================
    # MARKET INTELLIGENCE
    # =========================================================================

    def _enrich_with_market_data(
        self,
        opportunities: List[RepurposingOpportunity]
    ) -> List[RepurposingOpportunity]:
        """Enrich opportunities with market intelligence.

        Uses normalized disease name if available to avoid duplicate searches.
        """
        # Group by normalized disease name to avoid duplicate searches
        diseases_seen = set()
        disease_market_data = {}

        for opp in opportunities:
            # Use normalized name if available, otherwise original
            disease = opp.extraction.disease_normalized or opp.extraction.disease
            if disease not in diseases_seen:
                diseases_seen.add(disease)
                logger.info(f"Getting market data for: {disease}")
                market_data = self._get_market_intelligence(disease)
                disease_market_data[disease] = market_data

        # Assign market data to opportunities
        for opp in opportunities:
            disease = opp.extraction.disease_normalized or opp.extraction.disease
            if disease in disease_market_data:
                opp.market_intelligence = disease_market_data[disease]

        return opportunities

    def _get_market_intelligence(self, disease: str) -> MarketIntelligence:
        """Get comprehensive market intelligence for a disease."""
        from src.models.case_series_schemas import AttributedSource

        # Check cache for fresh market intelligence
        if self.cs_db:
            cached = self.cs_db.check_market_intel_fresh(disease)
            if cached:
                logger.info(f"Using cached market intelligence for: {disease}")
                self._cache_stats['market_intel_from_cache'] += 1
                # Estimate tokens saved (average market intel is ~3000 tokens)
                self._cache_stats['tokens_saved_by_cache'] += 3000
                return cached

        # Determine parent disease for better search coverage
        parent_disease = self._get_parent_disease(disease)
        search_disease = parent_disease if parent_disease else disease

        market_intel = MarketIntelligence(disease=disease, parent_disease=parent_disease)
        attributed_sources = []

        if not self.web_search:
            return market_intel

        # Get disease name variants for better search coverage
        disease_variants = self._get_disease_name_variants(search_disease)

        # 1. Get epidemiology data
        self.search_count += 1
        epi_results = self.web_search.search(
            f"{search_disease} prevalence United States epidemiology patients",
            max_results=10
        )

        if epi_results:
            epi_data = self._extract_epidemiology(search_disease, epi_results)
            market_intel.epidemiology = epi_data
            # Track epidemiology sources
            for r in epi_results[:2]:  # Top 2 sources
                if r.get('url'):
                    attributed_sources.append(AttributedSource(
                        url=r.get('url'),
                        title=r.get('title', 'Unknown'),
                        attribution='Epidemiology'
                    ))

        # 2. Get FDA approved drugs specifically
        self.search_count += 1
        fda_results = self.web_search.search(
            f'"{search_disease}" FDA approved drugs treatments biologics site:fda.gov OR site:drugs.com OR site:medscape.com',
            max_results=10
        )

        # 3. Get standard of care
        self.search_count += 1
        soc_results = self.web_search.search(
            f"{search_disease} standard of care treatment guidelines first line second line therapy",
            max_results=10
        )

        # Combine results for SOC extraction
        all_treatment_results = (fda_results or []) + (soc_results or [])
        if all_treatment_results:
            soc_data = self._extract_standard_of_care(search_disease, all_treatment_results, parent_disease=parent_disease)
            market_intel.standard_of_care = soc_data
            # Track SOC sources (FDA approvals, treatment guidelines)
            for r in (fda_results or [])[:2]:
                if r.get('url'):
                    attributed_sources.append(AttributedSource(
                        url=r.get('url'),
                        title=r.get('title', 'Unknown'),
                        attribution='Approved Treatments'
                    ))
            for r in (soc_results or [])[:1]:
                if r.get('url'):
                    attributed_sources.append(AttributedSource(
                        url=r.get('url'),
                        title=r.get('title', 'Unknown'),
                        attribution='Treatment Paradigm'
                    ))

        # 4. Get pipeline data - ENHANCED with ClinicalTrials.gov API

        # 4a. Query ClinicalTrials.gov API directly (primary source - free, structured data)
        ct_gov_trials = self._fetch_clinicaltrials_gov(search_disease)
        ct_gov_parsed = [self._parse_ct_gov_trial(t) for t in ct_gov_trials]

        # 4b. Supplementary web search for additional context (mechanisms, news, etc.)
        all_pipeline_results = []

        self.search_count += 1
        pipeline_results_1 = self.web_search.search(
            f'"{search_disease}" clinical trial Phase 2 OR Phase 3 site:clinicaltrials.gov',
            max_results=10
        )
        all_pipeline_results.extend(pipeline_results_1 or [])

        # Search for pipeline news/press releases
        self.search_count += 1
        pipeline_results_2 = self.web_search.search(
            f'"{search_disease}" Phase 2 Phase 3 trial drug pipeline 2024 OR 2025',
            max_results=8
        )
        all_pipeline_results.extend(pipeline_results_2 or [])

        # Search BioPharma pipeline databases
        self.search_count += 1
        pipeline_results_3 = self.web_search.search(
            f'"{search_disease}" pipeline drug development site:biopharmcatalyst.com OR site:evaluate.com',
            max_results=5
        )
        all_pipeline_results.extend(pipeline_results_3 or [])

        if ct_gov_parsed or all_pipeline_results:
            pipeline_data = self._extract_pipeline_data(
                search_disease,
                all_pipeline_results,
                ct_gov_data=ct_gov_parsed  # Pass structured API data
            )
            # Merge pipeline data into SOC
            market_intel.standard_of_care.pipeline_therapies = pipeline_data.get('therapies', [])
            market_intel.standard_of_care.num_pipeline_therapies = len(pipeline_data.get('therapies', []))
            market_intel.standard_of_care.phase_3_count = pipeline_data.get('phase_3_count', 0)
            market_intel.standard_of_care.phase_2_count = pipeline_data.get('phase_2_count', 0)
            market_intel.standard_of_care.key_catalysts = pipeline_data.get('key_catalysts')
            market_intel.standard_of_care.pipeline_data_quality = pipeline_data.get('data_completeness', 'Unknown')
            if pipeline_data.get('details'):
                market_intel.standard_of_care.pipeline_details = pipeline_data['details']
            # Track pipeline sources - include ClinicalTrials.gov as primary source
            pipeline_source_urls = ['https://clinicaltrials.gov']  # Always include as source
            pipeline_source_urls.extend([r.get('url') for r in all_pipeline_results if r.get('url')][:4])
            market_intel.pipeline_sources = pipeline_source_urls
            # Add ClinicalTrials.gov as attributed source
            attributed_sources.append(AttributedSource(
                url='https://clinicaltrials.gov',
                title='ClinicalTrials.gov API',
                attribution='Pipeline/Clinical Trials (Primary)'
            ))
            for r in all_pipeline_results[:2]:
                if r.get('url'):
                    attributed_sources.append(AttributedSource(
                        url=r.get('url'),
                        title=r.get('title', 'Unknown'),
                        attribution='Pipeline/Clinical Trials'
                    ))

        # 5. Get TAM analysis data (market reports, treatment penetration)
        self.search_count += 1
        tam_results = self.web_search.search(
            f'"{disease}" market size TAM treatment penetration addressable market forecast',
            max_results=5
        )

        # Calculate simple market sizing (backward compatibility)
        market_intel = self._calculate_market_sizing(market_intel)

        # 6. Extract TAM with rationale
        if tam_results or all_treatment_results:
            tam_data = self._extract_tam_analysis(
                disease,
                tam_results or [],
                market_intel.epidemiology,
                market_intel.standard_of_care
            )
            market_intel.tam_usd = tam_data.get('tam_usd')
            market_intel.tam_estimate = tam_data.get('tam_estimate')
            market_intel.tam_rationale = tam_data.get('tam_rationale')
            # Track TAM sources
            if tam_results:
                market_intel.tam_sources = [r.get('url') for r in tam_results if r.get('url')][:3]
                for r in tam_results[:2]:
                    if r.get('url'):
                        attributed_sources.append(AttributedSource(
                            url=r.get('url'),
                            title=r.get('title', 'Unknown'),
                            attribution='TAM/Market Analysis'
                        ))

        # Store all attributed sources
        market_intel.attributed_sources = attributed_sources

        # Save to database for caching
        if self.cs_db:
            self.cs_db.save_market_intelligence(market_intel)
            logger.debug(f"Saved market intelligence to cache for: {disease}")

        return market_intel

    def _calculate_market_sizing(self, market_intel: MarketIntelligence) -> MarketIntelligence:
        """Calculate market size estimates based on epidemiology and treatment cost data."""
        epi = market_intel.epidemiology
        soc = market_intel.standard_of_care

        patient_pop = epi.patient_population_size or 0
        avg_cost = soc.avg_annual_cost_usd

        # Calculate market size if we have the data
        if patient_pop > 0:
            # Use provided cost or estimate based on patient population (rare vs common disease)
            if not avg_cost:
                if patient_pop < 10000:
                    # Ultra-rare: high-priced biologics/gene therapies
                    avg_cost = 200000
                elif patient_pop < 50000:
                    # Rare: specialty biologics
                    avg_cost = 100000
                elif patient_pop < 200000:
                    # Specialty: specialty drugs
                    avg_cost = 50000
                else:
                    # Common: mix of specialty and generics
                    avg_cost = 25000

            market_size_usd = patient_pop * avg_cost
            market_intel.market_size_usd = market_size_usd

            # Format market size estimate
            if market_size_usd >= 1_000_000_000:
                market_intel.market_size_estimate = f"${market_size_usd / 1_000_000_000:.1f}B"
            elif market_size_usd >= 1_000_000:
                market_intel.market_size_estimate = f"${market_size_usd / 1_000_000:.0f}M"
            else:
                market_intel.market_size_estimate = f"${market_size_usd / 1_000:.0f}K"

        # Estimate growth rate based on disease characteristics
        if epi.trend:
            trend = epi.trend.lower()
            if 'increasing' in trend:
                market_intel.growth_rate = "5-10% CAGR (increasing prevalence)"
            elif 'decreasing' in trend:
                market_intel.growth_rate = "0-2% CAGR (decreasing prevalence)"
            else:
                market_intel.growth_rate = "3-5% CAGR (stable prevalence)"
        elif soc.unmet_need:
            # High unmet need often correlates with market growth
            market_intel.growth_rate = "5-8% CAGR (high unmet need)"
        elif soc.num_pipeline_therapies and soc.num_pipeline_therapies > 3:
            # Active pipeline suggests growth potential
            market_intel.growth_rate = "4-7% CAGR (active pipeline)"
        else:
            market_intel.growth_rate = "3-5% CAGR (estimated)"

        return market_intel

    def _get_parent_disease(self, disease: str, use_inference: bool = True) -> Optional[str]:
        """
        Get the parent/canonical disease name for a specific subtype.

        Uses database-backed mappings (loaded on init) with fallback to constants.
        If no mapping exists and use_inference=True, uses LLM to infer the parent
        disease and auto-saves the mapping for future use.

        Args:
            disease: The disease name to look up
            use_inference: Whether to use LLM inference if no mapping exists (default: True)

        Returns:
            Parent disease name or None if disease is already canonical
        """
        # Check exact match first (using instance variable loaded from DB + constants)
        if disease in self._disease_parent_mappings:
            return self._disease_parent_mappings[disease]

        # Check case-insensitive match
        disease_lower = disease.lower()
        for specific, parent in self._disease_parent_mappings.items():
            if specific.lower() == disease_lower:
                return parent

        # No mapping found - try LLM inference if enabled
        if use_inference and len(disease) > 10:  # Only infer for reasonably long names
            logger.info(f"No parent mapping found for '{disease}', attempting LLM inference...")
            inference_result = self._infer_disease_mapping(disease)

            if inference_result:
                parent = inference_result.get('parent_disease')

                # Save the inferred mapping to database
                self._save_inferred_disease_mapping(inference_result)

                if parent:
                    return parent

        return None

    def _get_disease_name_variants(self, disease: str, use_inference: bool = True) -> List[str]:
        """
        Get alternative names/abbreviations for a disease.

        Uses database-backed mappings (loaded on init) with fallback to constants.
        If no variants exist and use_inference=True, uses LLM to infer variants
        and auto-saves them for future use.

        Args:
            disease: The disease name to look up
            use_inference: Whether to use LLM inference if no variants exist (default: True)

        Returns:
            List of disease name variants including the original
        """
        variants = [disease]

        # Check exact match first (using instance variable loaded from DB + constants)
        if disease in self._disease_name_variants:
            variants.extend(self._disease_name_variants[disease])
            return list(set(variants))  # Deduplicate

        # Check case-insensitive match
        disease_lower = disease.lower()
        for canonical, alts in self._disease_name_variants.items():
            if canonical.lower() == disease_lower:
                variants.extend(alts)
                return list(set(variants))  # Deduplicate

        # No variants found - try LLM inference if enabled
        # Note: We may have already called inference in _get_parent_disease,
        # so check if we now have variants after that call
        if use_inference and len(disease) > 5:
            # Check if inference already ran and added variants
            if disease in self._disease_name_variants:
                variants.extend(self._disease_name_variants[disease])
                return list(set(variants))

            # Also check the canonical name from parent mapping
            parent = self._disease_parent_mappings.get(disease)
            if parent and parent in self._disease_name_variants:
                variants.extend(self._disease_name_variants[parent])
                return list(set(variants))

            # Run inference specifically for variants
            logger.info(f"No variants found for '{disease}', attempting LLM inference...")
            inference_result = self._infer_disease_mapping(disease)

            if inference_result:
                # Save the inferred mapping
                self._save_inferred_disease_mapping(inference_result)

                # Extract variants from result
                canonical = inference_result.get('canonical_name', disease)
                inferred_variants = inference_result.get('variants', [])

                for v in inferred_variants:
                    variant_name = v.get('name', '')
                    if variant_name:
                        variants.append(variant_name)

                # Also check if we now have variants in memory
                if canonical in self._disease_name_variants:
                    variants.extend(self._disease_name_variants[canonical])

        return list(set(variants))  # Deduplicate

    def _deduplicate_diseases(self, diseases: List[str]) -> List[str]:
        """
        Deduplicate disease list by normalizing names and keeping canonical versions.

        This prevents redundant market intelligence lookups for the same disease
        with slight naming variations (e.g., case differences, "refractory" prefixes).

        Returns list of unique canonical disease names.
        """
        seen_normalized = {}
        result = []

        for disease in diseases:
            # Normalize: lowercase, remove extra whitespace
            normalized = ' '.join(disease.lower().split())

            # Check if we've seen this or a parent disease
            parent = self._get_parent_disease(disease)
            check_key = normalized

            if parent:
                parent_normalized = ' '.join(parent.lower().split())
                # If parent exists in seen, skip this variant
                if parent_normalized in seen_normalized:
                    logger.debug(f"Skipping '{disease}' - parent disease '{parent}' already processed")
                    continue
                check_key = parent_normalized

            if check_key not in seen_normalized:
                seen_normalized[check_key] = disease
                result.append(disease)
            else:
                logger.debug(f"Skipping duplicate disease: '{disease}' (normalized: '{check_key}')")

        if len(result) < len(diseases):
            logger.info(f"Deduplicated diseases: {len(diseases)} -> {len(result)} unique")

        return result

    def _fetch_clinicaltrials_gov(
        self,
        disease: str,
        phases: List[str] = None,
        statuses: List[str] = None,
        min_start_year: int = None,
        include_completed_recent: bool = True
    ) -> List[Dict]:
        """
        Query ClinicalTrials.gov API v2 directly for comprehensive trial data.

        API Documentation: https://clinicaltrials.gov/api/v2/studies

        Args:
            disease: Disease name to search
            phases: List of phases to include (default: ["PHASE2", "PHASE3"])
            statuses: List of statuses to include (default: active/recruiting)
            min_start_year: Minimum start year to include (default: 5 years ago)
            include_completed_recent: Include trials completed in last 2 years (still relevant)

        Returns:
            List of study records with structured data
        """
        if phases is None:
            phases = ["PHASE2", "PHASE3"]

        # Default: only trials started in the last 5 years (active development)
        if min_start_year is None:
            min_start_year = datetime.now().year - 5

        # Active trial statuses
        active_statuses = [
            "RECRUITING",
            "ACTIVE_NOT_RECRUITING",
            "ENROLLING_BY_INVITATION",
            "NOT_YET_RECRUITING"
        ]

        # Also include recently completed trials (last 2 years) as they indicate active development
        completed_statuses = ["COMPLETED"] if include_completed_recent else []

        base_url = "https://clinicaltrials.gov/api/v2/studies"

        all_trials = []
        disease_variants = self._get_disease_name_variants(disease)

        # Build filter expressions using filter.advanced (API v2 syntax)
        # Phase and status filters must be combined in filter.advanced
        phase_filter = " OR ".join([f"AREA[Phase]{p}" for p in phases])
        status_filter = " OR ".join([f"AREA[OverallStatus]{s}" for s in active_statuses])
        date_filter = f"AREA[StartDate]RANGE[{min_start_year}-01-01,MAX]"

        for variant in disease_variants[:3]:  # Limit to avoid too many API calls
            # First query: Active/recruiting trials (started in last 5 years)
            # Combine all filters in filter.advanced
            advanced_filter = f"({phase_filter}) AND ({status_filter}) AND {date_filter}"
            params = {
                "query.cond": variant,
                "filter.advanced": advanced_filter,
                "pageSize": 50,
                "format": "json"
            }

            try:
                response = requests.get(base_url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    studies = data.get('studies', [])
                    all_trials.extend(studies)
                elif response.status_code == 429:
                    # Rate limited - wait and retry once
                    time.sleep(2)
                    response = requests.get(base_url, params=params, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        studies = data.get('studies', [])
                        all_trials.extend(studies)
                else:
                    logger.warning(f"ClinicalTrials.gov API returned status {response.status_code} for {variant}")
            except requests.exceptions.RequestException as e:
                logger.warning(f"ClinicalTrials.gov API error for {variant}: {e}")
                continue

            # Second query: Recently completed trials (last 2 years) - still indicates active development
            if include_completed_recent:
                completed_min_year = datetime.now().year - 2
                completed_date_filter = f"AREA[PrimaryCompletionDate]RANGE[{completed_min_year}-01-01,MAX]"
                completed_advanced_filter = f"({phase_filter}) AND AREA[OverallStatus]COMPLETED AND {completed_date_filter}"
                params_completed = {
                    "query.cond": variant,
                    "filter.advanced": completed_advanced_filter,
                    "pageSize": 30,
                    "format": "json"
                }
                try:
                    response = requests.get(base_url, params=params_completed, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        studies = data.get('studies', [])
                        all_trials.extend(studies)
                except requests.exceptions.RequestException as e:
                    logger.debug(f"ClinicalTrials.gov completed trials query error: {e}")

        # Deduplicate by NCT ID
        seen_ncts = set()
        unique_trials = []
        for trial in all_trials:
            nct_id = trial.get('protocolSection', {}).get('identificationModule', {}).get('nctId')
            if nct_id and nct_id not in seen_ncts:
                seen_ncts.add(nct_id)
                unique_trials.append(trial)

        logger.info(f"ClinicalTrials.gov API: Found {len(unique_trials)} unique trials for {disease} (started after {min_start_year})")
        return unique_trials

    def _parse_ct_gov_trial(self, trial: Dict) -> Dict:
        """Parse a ClinicalTrials.gov API response into a simplified format."""
        protocol = trial.get('protocolSection', {})
        identification = protocol.get('identificationModule', {})
        status = protocol.get('statusModule', {})
        design = protocol.get('designModule', {})
        sponsor = protocol.get('sponsorCollaboratorsModule', {})
        arms = protocol.get('armsInterventionsModule', {})

        # Extract intervention/drug names
        interventions = arms.get('interventions', [])
        drug_names = []
        for intervention in interventions:
            if intervention.get('type') in ['DRUG', 'BIOLOGICAL']:
                drug_names.append(intervention.get('name', 'Unknown'))

        # Get phase
        phases = design.get('phases', [])
        phase_str = ", ".join(phases) if phases else "Unknown"
        phase_str = phase_str.replace("PHASE", "Phase ")

        # Get dates
        start_date = status.get('startDateStruct', {}).get('date')
        completion_date = status.get('primaryCompletionDateStruct', {}).get('date')

        # Calculate if this represents active development
        # Active = currently recruiting OR recently completed (last 2 years)
        trial_status = status.get('overallStatus', 'Unknown')
        is_active_development = trial_status in [
            'RECRUITING', 'ACTIVE_NOT_RECRUITING',
            'ENROLLING_BY_INVITATION', 'NOT_YET_RECRUITING'
        ]

        # For completed trials, check if completion was recent
        if trial_status == 'COMPLETED' and completion_date:
            try:
                # Parse completion year
                completion_year = int(completion_date.split('-')[0]) if '-' in completion_date else int(completion_date[-4:])
                current_year = datetime.now().year
                is_active_development = (current_year - completion_year) <= 2
            except (ValueError, IndexError):
                is_active_development = False

        return {
            'nct_id': identification.get('nctId'),
            'title': identification.get('briefTitle'),
            'official_title': identification.get('officialTitle'),
            'phase': phase_str,
            'status': trial_status,
            'is_active_development': is_active_development,
            'drug_names': drug_names,
            'sponsor': sponsor.get('leadSponsor', {}).get('name'),
            'start_date': start_date,
            'completion_date': completion_date,
            'enrollment': design.get('enrollmentInfo', {}).get('count')
        }

    def _extract_epidemiology(self, disease: str, results: List[Dict]) -> EpidemiologyData:
        """Extract epidemiology data from search results."""
        # Include URLs in the search results for source citation
        # Note: Tavily API returns 'content', not 'snippet'
        results_with_urls = []
        for r in results:
            results_with_urls.append({
                'title': r.get('title'),
                'content': r.get('content') or r.get('snippet'),  # Tavily uses 'content'
                'url': r.get('url')
            })

        prompt = self._prompts.render(
            "case_series/extract_epidemiology",
            disease=disease,
            search_results=results_with_urls[:6000]
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            return EpidemiologyData(**data)
        except Exception as e:
            logger.error(f"Error extracting epidemiology: {e}")
            return EpidemiologyData()

    def _extract_standard_of_care(self, disease: str, results: List[Dict], parent_disease: Optional[str] = None) -> StandardOfCareData:
        """Extract standard of care from search results - BRANDED INNOVATIVE DRUGS ONLY."""
        # Include URLs for source citation
        # Note: Tavily API returns 'content', not 'snippet'
        results_with_urls = []
        for r in results:
            results_with_urls.append({
                'title': r.get('title'),
                'content': r.get('content') or r.get('snippet'),  # Tavily uses 'content'
                'url': r.get('url')
            })

        prompt = self._prompts.render(
            "case_series/extract_treatments",
            disease=disease,
            search_results=results_with_urls[:8000],  # Increased for more results
            parent_disease=parent_disease  # Pass parent disease for context
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2500,  # Increased for more detailed output
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            # Build treatments with new fields including approval confidence
            treatments = []
            approved_innovative_count = 0
            approved_innovative_names = []

            for t in data.get('top_treatments', []):
                is_branded = t.get('is_branded_innovative', False)
                is_approved = t.get('fda_approved', False)
                fda_indication = t.get('fda_approved_indication')

                treatments.append(StandardOfCareTreatment(
                    drug_name=t.get('drug_name', 'Unknown'),
                    drug_class=t.get('drug_class'),
                    is_branded_innovative=is_branded,
                    fda_approved=is_approved,
                    fda_approved_indication=fda_indication,
                    line_of_therapy=t.get('line_of_therapy'),
                    efficacy_range=t.get('efficacy_range'),
                    annual_cost_usd=t.get('annual_cost_usd'),
                    notes=t.get('notes'),
                    # New fields for approval confidence
                    approval_year=t.get('approval_year'),
                    approval_confidence=t.get('approval_confidence', 'Medium'),
                    approval_evidence=t.get('approval_evidence')
                ))

                # Count branded innovative drugs that are FDA approved FOR THIS EXACT INDICATION
                if is_branded and is_approved:
                    approved_innovative_count += 1
                    approved_innovative_names.append(t.get('drug_name', 'Unknown'))

            # Use validated count from top_treatments (cross-validation)
            # This ensures count matches the actual list
            final_approved_names = approved_innovative_names if approved_innovative_names else data.get('approved_drug_names', [])
            final_count = len(final_approved_names)

            return StandardOfCareData(
                top_treatments=treatments,
                approved_drug_names=final_approved_names,
                num_approved_drugs=final_count,
                num_pipeline_therapies=data.get('num_pipeline_therapies', 0),
                pipeline_details=data.get('pipeline_details'),
                avg_annual_cost_usd=data.get('avg_annual_cost_usd'),
                treatment_paradigm=data.get('treatment_paradigm'),
                unmet_need=data.get('unmet_need', False),
                unmet_need_description=data.get('unmet_need_description'),
                competitive_landscape=data.get('competitive_landscape'),
                soc_source=data.get('soc_source'),
                # New fields for data quality tracking
                recent_approvals=data.get('recent_approvals'),
                data_quality=data.get('data_quality', 'Unknown'),
                data_quality_notes=data.get('data_quality_notes')
            )
        except Exception as e:
            logger.error(f"Error extracting SOC: {e}")
            return StandardOfCareData()

    def _extract_pipeline_data(self, disease: str, results: List[Dict], ct_gov_data: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Extract comprehensive pipeline data from ClinicalTrials.gov focused search."""
        results_with_urls = []
        for r in results:
            results_with_urls.append({
                'title': r.get('title'),
                'content': r.get('content') or r.get('snippet'),
                'url': r.get('url')
            })

        prompt = self._prompts.render(
            "case_series/extract_pipeline",
            disease=disease,
            search_results=results_with_urls[:8000],  # Increased for more results
            ct_gov_data=ct_gov_data  # Pass API data if available
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2500,  # Increased for more detailed output
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            # Build pipeline therapy objects with new fields
            therapies = []
            for t in data.get('pipeline_therapies', []):
                therapies.append(PipelineTherapy(
                    drug_name=t.get('drug_name', 'Unknown'),
                    company=t.get('company'),
                    mechanism=t.get('mechanism'),
                    phase=t.get('phase', 'Unknown'),
                    trial_id=t.get('trial_id'),
                    expected_completion=t.get('expected_completion'),
                    # New fields
                    trial_name=t.get('trial_name'),
                    status=t.get('status'),
                    regulatory_designations=t.get('regulatory_designations'),
                    notes=t.get('notes')
                ))

            return {
                'therapies': therapies,
                'details': data.get('pipeline_summary'),
                'phase_3_count': data.get('phase_3_count', 0),
                'phase_2_count': data.get('phase_2_count', 0),
                'key_catalysts': data.get('key_catalysts'),
                'data_completeness': data.get('data_completeness', 'Unknown'),
                'data_completeness_notes': data.get('data_completeness_notes')
            }
        except Exception as e:
            logger.error(f"Error extracting pipeline data: {e}")
            return {'therapies': [], 'details': None, 'phase_3_count': 0, 'phase_2_count': 0}

    def _extract_tam_analysis(
        self,
        disease: str,
        tam_results: List[Dict],
        epidemiology: EpidemiologyData,
        soc: StandardOfCareData
    ) -> Dict[str, Any]:
        """Extract TAM (Total Addressable Market) with detailed rationale."""
        results_with_urls = []
        for r in tam_results:
            results_with_urls.append({
                'title': r.get('title'),
                'content': r.get('content') or r.get('snippet'),
                'url': r.get('url')
            })

        # Provide context from already-extracted data
        context = {
            'patient_population': epidemiology.patient_population_size,
            'prevalence': epidemiology.us_prevalence_estimate,
            'num_approved_drugs': soc.num_approved_drugs,
            'treatment_paradigm': soc.treatment_paradigm,
            'avg_annual_cost': soc.avg_annual_cost_usd,
            'unmet_need': soc.unmet_need
        }

        prompt = self._prompts.render(
            "case_series/calculate_tam",
            disease=disease,
            context=context,
            search_results=results_with_urls[:4000]
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            return {
                'tam_usd': data.get('tam_usd'),
                'tam_estimate': data.get('tam_estimate'),
                'tam_rationale': data.get('tam_rationale')
            }
        except Exception as e:
            logger.error(f"Error extracting TAM: {e}")
            return {'tam_usd': None, 'tam_estimate': None, 'tam_rationale': None}

    # =========================================================================
    # SCORING
    # =========================================================================

    def _score_opportunities(
        self,
        opportunities: List[RepurposingOpportunity]
    ) -> List[RepurposingOpportunity]:
        """Score all opportunities."""
        for opp in opportunities:
            opp.scores = self._score_opportunity(opp)
        return opportunities

    def _score_opportunity(self, opp: RepurposingOpportunity) -> OpportunityScores:
        """
        Score a single repurposing opportunity.

        UPDATED v2: Removed separate endpoint_quality_score since quality is now
        factored into the efficacy score. Redistributed weights.

        Clinical Signal (50%):
        - Response rate (quality-weighted): 40%
        - Safety profile: 40%
        - Organ domain breadth: 20%

        Evidence Quality (25%):
        - Sample size: 35%
        - Publication venue: 25%
        - Response durability: 25%
        - Extraction completeness: 15%

        Market Opportunity (25%):
        - Competitors: 33%
        - Market size: 33%
        - Unmet need: 33%
        """
        ext = opp.extraction

        # Clinical Signal Score (50% of overall)
        response_score, response_breakdown = self._score_response_rate_v2(ext)
        safety_score, safety_breakdown = self._score_safety_profile_detailed(ext)
        organ_domain_score = self._score_organ_domain_breadth(ext)

        clinical_score = (
            response_score * 0.40 +
            safety_score * 0.40 +
            organ_domain_score * 0.20
        )

        # Evidence Quality Score (25% of overall)
        sample_score = self._score_sample_size_v2(ext)
        venue_score = self._score_publication_venue(ext)
        durability_score = self._score_response_durability(ext)
        completeness_score = self._score_extraction_completeness(ext)

        evidence_score = (
            sample_score * 0.35 +
            venue_score * 0.25 +
            durability_score * 0.25 +
            completeness_score * 0.15
        )

        # Market Opportunity Score (25% of overall)
        competitors_score = self._score_competitors(opp)
        market_size_score = self._score_market_size(opp)
        unmet_need_score = self._score_unmet_need(opp)
        market_score = (competitors_score + market_size_score + unmet_need_score) / 3

        # Overall Priority
        overall = (
            clinical_score * 0.50 +
            evidence_score * 0.25 +
            market_score * 0.25
        )

        # Extract market intelligence data for breakdown
        market_breakdown_data = {
            "competitors": round(competitors_score, 1),
            "market_size": round(market_size_score, 1),
            "unmet_need": round(unmet_need_score, 1)
        }

        # Add actual market intelligence data if available
        if opp.market_intelligence:
            mi = opp.market_intelligence
            if mi.standard_of_care:
                market_breakdown_data["num_approved_drugs"] = mi.standard_of_care.num_approved_drugs
                market_breakdown_data["unmet_need"] = mi.standard_of_care.unmet_need
            if mi.tam_estimate:
                market_breakdown_data["tam_estimate"] = mi.tam_estimate

        return OpportunityScores(
            clinical_signal=round(clinical_score, 1),
            evidence_quality=round(evidence_score, 1),
            market_opportunity=round(market_score, 1),
            overall_priority=round(overall, 1),
            # Clinical breakdown
            response_rate_score=round(response_score, 1),
            safety_profile_score=round(safety_score, 1),
            endpoint_quality_score=None,  # Now baked into response_rate_score
            organ_domain_score=round(organ_domain_score, 1),
            clinical_breakdown={
                "response_rate_quality_weighted": round(response_score, 1),
                "safety_profile": round(safety_score, 1),
                "organ_domain_breadth": round(organ_domain_score, 1),
                "safety_categories": safety_breakdown.get('categories_detected', []),
                "regulatory_flags": safety_breakdown.get('regulatory_flags', []),
                "efficacy_endpoint_count": response_breakdown.get('n_endpoints_scored', 0),
                "efficacy_concordance": response_breakdown.get('concordance_multiplier', 1.0),
            },
            # Evidence breakdown
            sample_size_score=round(sample_score, 1),
            publication_venue_score=round(venue_score, 1),
            followup_duration_score=round(durability_score, 1),
            extraction_completeness_score=round(completeness_score, 1),
            evidence_breakdown={
                "sample_size": round(sample_score, 1),
                "publication_venue": round(venue_score, 1),
                "response_durability": round(durability_score, 1),
                "extraction_completeness": round(completeness_score, 1),
            },
            # Market breakdown
            competitors_score=round(competitors_score, 1),
            market_size_score=round(market_size_score, 1),
            unmet_need_score=round(unmet_need_score, 1),
            market_breakdown=market_breakdown_data
        )

    # -------------------------------------------------------------------------
    # Clinical Signal Component Scores
    # -------------------------------------------------------------------------

    def _score_response_rate(self, ext: CaseSeriesExtraction) -> float:
        """
        Score response rate considering totality of efficacy data (1-10).

        Primary: Based on % patients achieving primary outcome
        Secondary: Adjusted by endpoint concordance across all endpoints

        >80%=10, 60-80%=8, 40-60%=6, 20-40%=4, <20%=2
        Bonus/penalty: +/-1 based on concordance of secondary endpoints
        """
        base_score = 5.0  # Default unknown

        if ext.efficacy.responders_pct is not None:
            pct = ext.efficacy.responders_pct
            if pct >= 80:
                base_score = 10.0
            elif pct >= 60:
                base_score = 8.0
            elif pct >= 40:
                base_score = 6.0
            elif pct >= 20:
                base_score = 4.0
            else:
                base_score = 2.0
        elif ext.efficacy_signal == EfficacySignal.STRONG:
            base_score = 9.0
        elif ext.efficacy_signal == EfficacySignal.MODERATE:
            base_score = 6.0
        elif ext.efficacy_signal == EfficacySignal.WEAK:
            base_score = 3.0
        elif ext.efficacy_signal == EfficacySignal.NONE:
            base_score = 1.0

        # Adjust based on endpoint concordance
        concordance = self._calculate_endpoint_concordance(ext)
        if concordance['total_endpoints'] >= 3:
            # Significant endpoint data - apply concordance adjustment
            concordance_rate = concordance['positive_rate']
            if concordance_rate >= 0.8:
                base_score = min(10.0, base_score + 0.5)  # Strong concordance bonus
            elif concordance_rate >= 0.6:
                pass  # Moderate concordance - no adjustment
            elif concordance_rate < 0.4:
                base_score = max(1.0, base_score - 0.5)  # Poor concordance penalty

        return base_score

    def _score_response_rate_v2(self, ext: CaseSeriesExtraction) -> Tuple[float, Dict[str, Any]]:
        """
        Enhanced response rate scoring using totality of efficacy endpoints
        with quality weighting.

        Returns (score, breakdown_dict) where score is 1-10.

        Scoring approach:
        1. Score each endpoint individually (1-10 based on results)
        2. Get quality score for each endpoint (validated vs ad-hoc)
        3. Calculate weight = (category_weight) × (quality_weight)
        4. Compute weighted average across all endpoints
        5. Apply concordance multiplier (0.85-1.15)
        6. Blend with best single endpoint to prevent dilution

        Category weights: Primary=1.0, Secondary=0.6, Exploratory=0.3
                          Unknown defaults to Secondary (0.6)
        Quality weights: Scaled from 0.4 (ad-hoc) to 1.0 (validated gold-standard)
        """
        breakdown = {
            'method': 'multi_endpoint_quality_weighted',
            'n_endpoints_scored': 0,
            'primary_score': None,
            'secondary_avg_score': None,
            'weighted_avg_score': None,
            'concordance_multiplier': 1.0,
            'best_endpoint_score': None,
            'final_score': None,
            'endpoint_details': []
        }

        # Fallback if no detailed endpoints available
        if not ext.detailed_efficacy_endpoints:
            base_score = self._score_response_rate_fallback(ext)
            breakdown['method'] = 'fallback_no_detailed_endpoints'
            breakdown['final_score'] = base_score
            return base_score, breakdown

        # Get validated instruments for this disease
        disease = ext.disease or ext.disease_normalized or ""
        validated_instruments = self._get_validated_instruments_for_disease(disease)

        # Score each endpoint
        endpoint_scores = []
        primary_scores = []
        secondary_scores = []
        exploratory_scores = []

        for ep in ext.detailed_efficacy_endpoints:
            # Get efficacy score (how good were the results?)
            efficacy_score, efficacy_detail = self._score_single_endpoint(ep)

            # Get quality score (how good was the instrument?)
            quality_score = self._get_endpoint_quality_score_v2(ep, validated_instruments)

            # Determine category (defaults to secondary if unknown)
            raw_category = getattr(ep, 'endpoint_category', '') if hasattr(ep, 'endpoint_category') else ''
            category, category_weight = self._get_category_and_weight(raw_category)

            # Calculate quality weight (scale 0.4 to 1.0)
            # quality_score is 1-10, map to 0.4-1.0
            quality_weight = 0.4 + (quality_score / 10) * 0.6

            # Combined weight
            combined_weight = category_weight * quality_weight

            endpoint_info = {
                'name': getattr(ep, 'endpoint_name', 'Unknown'),
                'category': category,
                'category_inferred': raw_category == '' or raw_category is None,
                'efficacy_score': efficacy_score,
                'quality_score': quality_score,
                'category_weight': category_weight,
                'quality_weight': round(quality_weight, 2),
                'combined_weight': round(combined_weight, 2),
                'efficacy_detail': efficacy_detail
            }
            endpoint_scores.append(endpoint_info)

            # Track by category for reporting
            if category == 'primary':
                primary_scores.append(efficacy_score)
            elif category == 'secondary':
                secondary_scores.append(efficacy_score)
            else:
                exploratory_scores.append(efficacy_score)

        breakdown['endpoint_details'] = endpoint_scores
        breakdown['n_endpoints_scored'] = len(endpoint_scores)

        # Calculate weighted average
        weighted_sum = 0.0
        total_weight = 0.0

        for ep_info in endpoint_scores:
            weighted_sum += ep_info['efficacy_score'] * ep_info['combined_weight']
            total_weight += ep_info['combined_weight']

        weighted_avg = weighted_sum / total_weight if total_weight > 0 else 5.0
        breakdown['weighted_avg_score'] = round(weighted_avg, 2)

        # Track category averages for reporting
        if primary_scores:
            breakdown['primary_score'] = round(sum(primary_scores) / len(primary_scores), 2)
        if secondary_scores:
            breakdown['secondary_avg_score'] = round(sum(secondary_scores) / len(secondary_scores), 2)

        # Calculate concordance multiplier
        concordance_mult = self._calculate_concordance_multiplier_v2(endpoint_scores)
        breakdown['concordance_multiplier'] = concordance_mult

        # Find best single endpoint (prevents dilution of strong signals)
        all_efficacy_scores = [ep['efficacy_score'] for ep in endpoint_scores]
        best_score = max(all_efficacy_scores) if all_efficacy_scores else 5.0
        breakdown['best_endpoint_score'] = best_score

        # Final score calculation:
        # 70% weighted average (with concordance) + 30% best endpoint
        adjusted_avg = weighted_avg * concordance_mult
        final_score = (adjusted_avg * 0.70) + (best_score * 0.30)

        # Clamp to 1-10
        final_score = max(1.0, min(10.0, final_score))
        breakdown['final_score'] = round(final_score, 1)

        return round(final_score, 1), breakdown

    def _get_category_and_weight(self, raw_category: str) -> Tuple[str, float]:
        """
        Get normalized category and weight for an endpoint.

        Handles missing/unknown categories by defaulting to "secondary" (0.6 weight).
        This is conservative - not over-weighting or under-weighting when we don't know.

        Returns: (normalized_category, weight)
        """
        category_lower = (raw_category or '').lower().strip()

        # Primary indicators
        if category_lower in ['primary', 'main', 'principal', 'primary endpoint',
                              'primary outcome', 'main outcome']:
            return 'primary', 1.0

        # Exploratory indicators
        if category_lower in ['exploratory', 'tertiary', 'post-hoc', 'additional',
                              'exploratory endpoint', 'post hoc', 'supplementary']:
            return 'exploratory', 0.3

        # Secondary or unknown → default to secondary weight
        return 'secondary', 0.6

    def _score_single_endpoint(self, ep) -> Tuple[float, Dict[str, Any]]:
        """
        Score a single efficacy endpoint on 1-10 scale based on results.

        Priority order:
        1. Response rate percentage (most direct)
        2. Percent change from baseline
        3. Absolute change from baseline (calculate % if possible)
        4. Statistical significance (weak proxy)

        Returns (score, detail_dict)
        """
        detail = {
            'scoring_basis': None,
            'raw_value': None,
            'interpretation': None
        }

        # Priority 1: Response rate percentage
        responders_pct = getattr(ep, 'responders_pct', None)
        if responders_pct is not None:
            try:
                pct = float(responders_pct)
                score = _response_pct_to_score(pct)
                detail['scoring_basis'] = 'responders_pct'
                detail['raw_value'] = pct
                detail['interpretation'] = f"{pct:.0f}% responders"
                return score, detail
            except (ValueError, TypeError):
                pass

        # Priority 2: Percent change from baseline
        change_pct = getattr(ep, 'change_pct', None)
        if change_pct is not None:
            try:
                pct = float(change_pct)
                ep_name = getattr(ep, 'endpoint_name', '').lower()
                decrease_is_good = _is_decrease_good(ep_name)

                # Flip sign so positive = improvement
                effective_change = -pct if decrease_is_good else pct

                score = _percent_change_to_score(effective_change)
                detail['scoring_basis'] = 'change_pct'
                detail['raw_value'] = pct
                direction = 'improvement' if effective_change > 0 else 'worsening'
                detail['interpretation'] = f"{pct:.1f}% change ({direction})"
                return score, detail
            except (ValueError, TypeError):
                pass

        # Priority 3: Absolute change from baseline
        change = getattr(ep, 'change_from_baseline', None)
        baseline = getattr(ep, 'baseline_value', None)
        if change is not None:
            try:
                change_val = float(change)
                ep_name = getattr(ep, 'endpoint_name', '').lower()
                decrease_is_good = _is_decrease_good(ep_name)

                # Try to calculate percent change if we have baseline
                if baseline is not None:
                    try:
                        baseline_val = float(baseline)
                        if baseline_val != 0:
                            calc_pct = (change_val / baseline_val) * 100
                            effective_change = -calc_pct if decrease_is_good else calc_pct

                            score = _percent_change_to_score(effective_change)
                            detail['scoring_basis'] = 'calculated_pct_change'
                            detail['raw_value'] = round(calc_pct, 1)
                            detail['interpretation'] = f"Calculated {calc_pct:.1f}% change from baseline"
                            return score, detail
                    except (ValueError, TypeError):
                        pass

                # Can't calculate %, use direction only
                is_improved = (change_val < 0) if decrease_is_good else (change_val > 0)
                score = 6.5 if is_improved else 3.5
                detail['scoring_basis'] = 'direction_only'
                detail['raw_value'] = change_val
                detail['interpretation'] = f"Change of {change_val} ({'improved' if is_improved else 'worsened'})"
                return score, detail
            except (ValueError, TypeError):
                pass

        # Priority 4: Statistical significance as weak proxy
        if getattr(ep, 'statistical_significance', False):
            detail['scoring_basis'] = 'statistical_significance'
            detail['raw_value'] = True
            detail['interpretation'] = 'Statistically significant (p<0.05), direction assumed positive'
            return 6.0, detail

        # Check p-value directly
        p_value = getattr(ep, 'p_value', None)
        if p_value is not None:
            try:
                # Handle strings like "<0.001" or "0.03"
                p_str = str(p_value).replace('<', '').replace('>', '').strip()
                p = float(p_str)
                if p < 0.05:
                    detail['scoring_basis'] = 'p_value'
                    detail['raw_value'] = p_value
                    detail['interpretation'] = f'p={p_value}, assumed positive direction'
                    return 6.0, detail
            except (ValueError, TypeError):
                pass

        # Unable to score - return neutral
        detail['scoring_basis'] = 'insufficient_data'
        detail['interpretation'] = 'Could not determine efficacy from available data'
        return 5.0, detail

    def _get_endpoint_quality_score_v2(self, ep, validated_instruments: Dict[str, int]) -> float:
        """
        Get quality score for an endpoint based on whether it uses validated instruments.

        Returns score from 1-10:
        - 10: Gold-standard validated instrument (ACR50, DAS28, SLEDAI, etc.)
        - 7-9: Known validated instruments
        - 4-6: Generic or ad-hoc measures
        - 4: Completely ad-hoc
        """
        ep_name = getattr(ep, 'endpoint_name', '') or ''
        ep_name_lower = ep_name.lower()

        # Check against disease-specific validated instruments from database
        best_score = 0
        for instrument, score in validated_instruments.items():
            if instrument.lower() in ep_name_lower or ep_name_lower in instrument.lower():
                best_score = max(best_score, score)

        if best_score > 0:
            return float(best_score)

        # Check against gold-standard patterns (disease-agnostic)
        gold_standard_patterns = {
            # Rheumatology
            'acr20': 10, 'acr50': 10, 'acr70': 10, 'acr90': 10,
            'das28': 10, 'das-28': 10,
            'sdai': 9, 'cdai': 9,
            'haq': 9, 'haq-di': 9,
            # Lupus
            'sledai': 10, 'sledai-2k': 10,
            'bilag': 10,
            'sri': 9, 'sri-4': 9, 'sri-5': 9,
            'clasi': 9,
            # Dermatology
            'pasi': 10, 'pasi50': 10, 'pasi75': 10, 'pasi90': 10, 'pasi100': 10,
            'easi': 10, 'easi50': 10, 'easi75': 10, 'easi90': 10,
            'iga': 9, 'iga 0/1': 9,
            'dlqi': 9,
            'scorad': 9,
            'salt': 9, 'salt50': 9, 'salt75': 9, 'salt90': 9,  # Alopecia
            # GI
            'mayo': 9, 'mayo score': 9,
            'ses-cd': 9,
            # Neurology
            'edss': 9,
            # General
            'sf-36': 8, 'sf36': 8,
            'eq-5d': 8, 'eq5d': 8,
            'facit': 8, 'facit-fatigue': 8,
            'pain vas': 7, 'vas pain': 7,
            'physician global': 7, 'pga': 7,
            'patient global': 7,
        }

        for pattern, score in gold_standard_patterns.items():
            if pattern in ep_name_lower:
                return float(score)

        # Check for generic positive indicators
        moderate_patterns = ['remission', 'response', 'responder', 'improvement']
        for pattern in moderate_patterns:
            if pattern in ep_name_lower:
                return 7.0

        # Ad-hoc endpoint
        return 4.0

    def _calculate_concordance_multiplier_v2(self, endpoint_scores: List[Dict]) -> float:
        """
        Calculate concordance multiplier (0.85 to 1.15).

        High concordance (most endpoints agree on direction) = bonus
        Low concordance (mixed/contradictory results) = penalty
        """
        if len(endpoint_scores) < 2:
            return 1.0  # No adjustment for single endpoint

        scores = [ep['efficacy_score'] for ep in endpoint_scores]

        # Classify each endpoint result
        positive = sum(1 for s in scores if s > 5.5)   # Clearly positive
        negative = sum(1 for s in scores if s < 4.5)   # Clearly negative
        neutral = sum(1 for s in scores if 4.5 <= s <= 5.5)  # Neutral/unknown
        total = len(scores)

        # Calculate concordance - what fraction point in the same direction?
        if positive >= negative:
            # Majority positive
            concordance = (positive + neutral * 0.5) / total
        else:
            # Majority negative (still concordant, just concordantly bad)
            concordance = (negative + neutral * 0.5) / total

        # Map concordance to multiplier
        if concordance >= 0.9:
            return 1.15  # Very high agreement
        elif concordance >= 0.75:
            return 1.10  # Good agreement
        elif concordance >= 0.6:
            return 1.0   # Acceptable agreement
        elif concordance >= 0.4:
            return 0.90  # Mixed results
        else:
            return 0.85  # Contradictory results

    def _score_response_rate_fallback(self, ext: CaseSeriesExtraction) -> float:
        """
        Fallback scoring when no detailed endpoints available.
        Uses summary efficacy data from extraction.
        """
        # Try responders_pct from summary
        if ext.efficacy.responders_pct is not None:
            return _response_pct_to_score(ext.efficacy.responders_pct)

        # Use efficacy signal enum
        if ext.efficacy_signal == EfficacySignal.STRONG:
            return 8.5
        elif ext.efficacy_signal == EfficacySignal.MODERATE:
            return 6.0
        elif ext.efficacy_signal == EfficacySignal.WEAK:
            return 3.5
        elif ext.efficacy_signal == EfficacySignal.NONE:
            return 1.5

        return 5.0  # Unknown

    def _calculate_endpoint_concordance(self, ext: CaseSeriesExtraction) -> Dict[str, Any]:
        """
        Calculate concordance across all efficacy endpoints.

        Returns dict with:
        - total_endpoints: Number of endpoints analyzed
        - positive_endpoints: Number showing positive results
        - positive_rate: Fraction of positive results
        - significant_endpoints: Number with p<0.05
        - significance_rate: Fraction statistically significant
        - primary_positive: Whether primary endpoint was positive
        - secondary_concordance: % of secondary endpoints concordant with primary
        """
        result = {
            'total_endpoints': 0,
            'positive_endpoints': 0,
            'positive_rate': 0.0,
            'significant_endpoints': 0,
            'significance_rate': 0.0,
            'primary_positive': None,
            'secondary_concordance': 0.0,
            'endpoint_details': []
        }

        if not ext.detailed_efficacy_endpoints:
            return result

        primary_positive = None
        secondary_positive = 0
        secondary_total = 0

        for ep in ext.detailed_efficacy_endpoints:
            result['total_endpoints'] += 1

            # Determine if endpoint shows positive result
            is_positive = self._is_endpoint_positive(ep)
            is_significant = False

            if is_positive:
                result['positive_endpoints'] += 1

            # Check statistical significance
            if hasattr(ep, 'statistical_significance') and ep.statistical_significance:
                is_significant = True
                result['significant_endpoints'] += 1
            elif hasattr(ep, 'p_value') and ep.p_value is not None:
                try:
                    p = float(ep.p_value) if isinstance(ep.p_value, (int, float, str)) else None
                    if p is not None and p < 0.05:
                        is_significant = True
                        result['significant_endpoints'] += 1
                except (ValueError, TypeError):
                    pass

            # Track primary vs secondary
            category = getattr(ep, 'endpoint_category', '').lower() if hasattr(ep, 'endpoint_category') else ''
            if category == 'primary':
                primary_positive = is_positive
            else:
                secondary_total += 1
                if is_positive:
                    secondary_positive += 1

            # Store endpoint detail for rationale
            result['endpoint_details'].append({
                'name': getattr(ep, 'endpoint_name', 'Unknown'),
                'category': category,
                'is_positive': is_positive,
                'is_significant': is_significant,
                'responders_pct': getattr(ep, 'responders_pct', None),
                'change_pct': getattr(ep, 'change_pct', None),
                'p_value': getattr(ep, 'p_value', None)
            })

        # Calculate rates
        if result['total_endpoints'] > 0:
            result['positive_rate'] = result['positive_endpoints'] / result['total_endpoints']
            result['significance_rate'] = result['significant_endpoints'] / result['total_endpoints']

        result['primary_positive'] = primary_positive
        if secondary_total > 0:
            result['secondary_concordance'] = secondary_positive / secondary_total

        return result

    def _is_endpoint_positive(self, ep) -> bool:
        """Determine if an efficacy endpoint shows a positive result."""
        # Check responders percentage (>50% is positive)
        if hasattr(ep, 'responders_pct') and ep.responders_pct is not None:
            return ep.responders_pct >= 50.0

        # Check change from baseline (negative is improvement for most scores)
        if hasattr(ep, 'change_from_baseline') and ep.change_from_baseline is not None:
            try:
                change = float(ep.change_from_baseline)
                # Most clinical scores decrease = improvement
                return change < 0
            except (ValueError, TypeError):
                pass

        # Check percent change
        if hasattr(ep, 'change_pct') and ep.change_pct is not None:
            try:
                pct = float(ep.change_pct)
                # Negative percent change usually = improvement
                return pct < 0
            except (ValueError, TypeError):
                pass

        # Check statistical significance as proxy
        if hasattr(ep, 'statistical_significance') and ep.statistical_significance:
            return True

        return False  # Unable to determine

    def _analyze_efficacy_totality(self, ext: CaseSeriesExtraction) -> Dict[str, Any]:
        """
        Analyze totality of efficacy data for detailed rationale generation.

        Returns comprehensive summary for PDF report narratives.
        """
        concordance = self._calculate_endpoint_concordance(ext)

        # Categorize endpoints by type
        primary_endpoints = []
        secondary_endpoints = []
        exploratory_endpoints = []

        for detail in concordance.get('endpoint_details', []):
            cat = detail.get('category', '').lower()
            if cat == 'primary':
                primary_endpoints.append(detail)
            elif cat == 'secondary':
                secondary_endpoints.append(detail)
            else:
                exploratory_endpoints.append(detail)

        # Count statistically significant by category
        primary_sig = sum(1 for ep in primary_endpoints if ep.get('is_significant'))
        secondary_sig = sum(1 for ep in secondary_endpoints if ep.get('is_significant'))

        # Get best response rates
        all_response_rates = [
            ep.get('responders_pct') for ep in concordance.get('endpoint_details', [])
            if ep.get('responders_pct') is not None
        ]

        return {
            'total_endpoints': concordance['total_endpoints'],
            'positive_endpoints': concordance['positive_endpoints'],
            'positive_rate': concordance['positive_rate'],
            'significant_endpoints': concordance['significant_endpoints'],
            'significance_rate': concordance['significance_rate'],
            # By category
            'primary_count': len(primary_endpoints),
            'primary_positive': sum(1 for ep in primary_endpoints if ep.get('is_positive')),
            'primary_significant': primary_sig,
            'secondary_count': len(secondary_endpoints),
            'secondary_positive': sum(1 for ep in secondary_endpoints if ep.get('is_positive')),
            'secondary_significant': secondary_sig,
            'exploratory_count': len(exploratory_endpoints),
            # Response rates
            'response_rates': all_response_rates,
            'max_response_rate': max(all_response_rates) if all_response_rates else None,
            'min_response_rate': min(all_response_rates) if all_response_rates else None,
            'avg_response_rate': sum(all_response_rates) / len(all_response_rates) if all_response_rates else None,
            # Primary endpoint detail
            'primary_endpoint_name': ext.efficacy.primary_endpoint,
            'primary_response_pct': ext.efficacy.responders_pct,
            # Concordance assessment
            'concordance_assessment': self._assess_concordance(concordance),
            'endpoint_details': concordance.get('endpoint_details', [])
        }

    def _assess_concordance(self, concordance: Dict[str, Any]) -> str:
        """Generate text assessment of endpoint concordance."""
        if concordance['total_endpoints'] < 2:
            return "Limited endpoint data available"

        pos_rate = concordance['positive_rate']
        sig_rate = concordance['significance_rate']

        if pos_rate >= 0.8 and sig_rate >= 0.5:
            return "Strong concordance: majority of endpoints show positive, statistically significant results"
        elif pos_rate >= 0.6:
            return "Moderate concordance: most endpoints show positive results"
        elif pos_rate >= 0.4:
            return "Mixed results: approximately half of endpoints show improvement"
        else:
            return "Limited concordance: minority of endpoints show positive results"

    def _analyze_safety_totality(self, ext: CaseSeriesExtraction) -> Dict[str, Any]:
        """
        Analyze totality of safety data for detailed rationale generation.

        Returns comprehensive safety summary for PDF report narratives.
        """
        safety = ext.safety
        n_patients = ext.patient_population.n_patients if ext.patient_population else None

        # Categorize detailed safety endpoints
        sae_events = []
        ae_events = []
        lab_abnormalities = []

        if ext.detailed_safety_endpoints:
            for ep in ext.detailed_safety_endpoints:
                cat = getattr(ep, 'event_category', '').lower() if hasattr(ep, 'event_category') else ''
                is_serious = getattr(ep, 'is_serious', False)

                event_info = {
                    'name': getattr(ep, 'event_name', 'Unknown'),
                    'category': cat,
                    'n_affected': getattr(ep, 'n_patients_affected', None),
                    'incidence_pct': getattr(ep, 'incidence_pct', None),
                    'is_serious': is_serious
                }

                if is_serious or 'sae' in cat or 'serious' in cat:
                    sae_events.append(event_info)
                elif 'lab' in cat:
                    lab_abnormalities.append(event_info)
                else:
                    ae_events.append(event_info)

        # Calculate rates
        sae_rate = None
        discontinuation_rate = None
        if n_patients and n_patients > 0:
            if safety.sae_count is not None:
                sae_rate = (safety.sae_count / n_patients) * 100
            if safety.discontinuations_n is not None:
                discontinuation_rate = (safety.discontinuations_n / n_patients) * 100

        return {
            'safety_profile': safety.safety_profile.value if safety.safety_profile else 'Unknown',
            'safety_summary': safety.safety_summary,
            # SAE data
            'sae_count': safety.sae_count,
            'sae_percentage': safety.sae_percentage or sae_rate,
            'sae_list': safety.serious_adverse_events or [],
            'sae_events_detailed': sae_events,
            # AE data
            'ae_list': safety.adverse_events or [],
            'ae_events_detailed': ae_events,
            'total_ae_types': len(safety.adverse_events or []),
            # Lab abnormalities
            'lab_abnormalities': lab_abnormalities,
            # Discontinuations
            'discontinuations_n': safety.discontinuations_n,
            'discontinuation_rate': discontinuation_rate,
            'discontinuation_reasons': safety.discontinuation_reasons or [],
            # Assessment
            'safety_assessment': self._assess_safety(safety, n_patients),
            'n_patients': n_patients
        }

    def _assess_safety(self, safety, n_patients: Optional[int]) -> str:
        """Generate text assessment of safety profile."""
        sae_count = safety.sae_count or 0
        disc_n = safety.discontinuations_n or 0

        if sae_count == 0 and disc_n == 0:
            return "Excellent tolerability: no serious adverse events or discontinuations reported"
        elif sae_count == 0:
            return f"Good tolerability: no serious adverse events, {disc_n} discontinuation(s)"
        elif n_patients and sae_count / n_patients < 0.05:
            return f"Acceptable safety: {sae_count} SAE(s) reported (<5% rate)"
        elif n_patients and sae_count / n_patients < 0.1:
            return f"Safety signal present: {sae_count} SAE(s) reported (5-10% rate)"
        else:
            return f"Safety concerns: {sae_count} SAE(s) reported, requires monitoring"

    def _score_safety_profile(self, ext: CaseSeriesExtraction) -> float:
        """
        Score safety profile based on SAE percentage (1-10).

        No SAEs=10, <5%=8, 5-10%=6, 10-20%=4, 20-50%=2, >50%=1
        Also factors in discontinuations due to AEs.
        """
        # Use SAE percentage if available
        if ext.safety.sae_percentage is not None:
            sae_pct = ext.safety.sae_percentage
            if sae_pct == 0:
                return 10.0
            elif sae_pct < 5:
                return 8.0
            elif sae_pct < 10:
                return 6.0
            elif sae_pct < 20:
                return 4.0
            elif sae_pct < 50:
                return 2.0
            else:
                return 1.0

        # Calculate from SAE count if available
        if ext.safety.sae_count is not None and ext.patient_population.n_patients > 0:
            sae_pct = (ext.safety.sae_count / ext.patient_population.n_patients) * 100
            if sae_pct == 0:
                return 10.0
            elif sae_pct < 5:
                return 8.0
            elif sae_pct < 10:
                return 6.0
            elif sae_pct < 20:
                return 4.0
            elif sae_pct < 50:
                return 2.0
            else:
                return 1.0

        # Fallback to safety profile enum
        if ext.safety.safety_profile == SafetyProfile.FAVORABLE:
            return 9.0
        elif ext.safety.safety_profile == SafetyProfile.ACCEPTABLE:
            return 7.0
        elif ext.safety.safety_profile == SafetyProfile.CONCERNING:
            return 3.0

        # Check for any SAEs mentioned
        if ext.safety.serious_adverse_events:
            n_saes = len(ext.safety.serious_adverse_events)
            if n_saes == 0:
                return 9.0
            elif n_saes <= 2:
                return 6.0
            else:
                return 4.0

        return 5.0  # Unknown

    def _is_positive_response(self, endpoint: Dict[str, Any]) -> bool:
        """
        Determine if an endpoint shows a positive response.

        Checks for responder percentages, statistical significance,
        and positive change from baseline.
        """
        # Check responder percentage
        responders_pct = endpoint.get('responders_pct')
        if responders_pct is not None and responders_pct > 30:
            return True

        # Check statistical significance
        if endpoint.get('statistical_significance') is True:
            return True
        if endpoint.get('p_value') is not None:
            try:
                p = float(str(endpoint['p_value']).replace('<', '').replace('>', ''))
                if p < 0.05:
                    return True
            except (ValueError, TypeError):
                pass

        # Check change from baseline (negative is usually improvement)
        change = endpoint.get('change_from_baseline')
        if change is not None:
            try:
                change_val = float(change)
                # Most clinical scores improve with decrease
                if change_val < 0:
                    return True
            except (ValueError, TypeError):
                pass

        # Check for positive keywords in outcome
        outcome = str(endpoint.get('outcome', '')).lower()
        positive_keywords = ['improved', 'improvement', 'response', 'remission',
                           'resolved', 'normalized', 'achieved', 'success']
        if any(kw in outcome for kw in positive_keywords):
            return True

        return False

    def _get_organ_domains(self) -> Dict[str, List[str]]:
        """
        Get organ domain keyword mappings from database (cached).

        Returns dict mapping domain_name to list of keywords.
        Falls back to minimal defaults if database unavailable.
        """
        if self._organ_domains is not None:
            return self._organ_domains

        # Try to load from database
        if self.cs_db:
            self._organ_domains = self.cs_db.get_organ_domains()
            if self._organ_domains:
                logger.debug(f"Loaded {len(self._organ_domains)} organ domains from database")
                return self._organ_domains

        # Fallback to minimal defaults
        logger.warning("Using fallback organ domains (database unavailable)")
        self._organ_domains = {
            'musculoskeletal': ['joint', 'arthritis', 'das28', 'acr20', 'acr50', 'haq'],
            'mucocutaneous': ['skin', 'rash', 'pasi', 'easi', 'bsa'],
            'renal': ['kidney', 'renal', 'proteinuria', 'creatinine', 'gfr'],
            'neurological': ['neuro', 'cognitive', 'edss', 'relapse'],
            'hematological': ['anemia', 'platelet', 'neutropenia', 'cytopenia'],
            'cardiopulmonary': ['cardiac', 'lung', 'fvc', 'dlco'],
            'immunological': ['complement', 'autoantibody', 'crp', 'esr'],
            'systemic': ['sledai', 'bilag', 'bvas', 'disease activity'],
            'gastrointestinal': ['gi', 'bowel', 'mayo', 'cdai'],
            'ocular': ['eye', 'uveitis', 'visual acuity'],
            'constitutional': ['fatigue', 'fever', 'weight loss'],
        }
        return self._organ_domains

    def _score_organ_domain_breadth(self, ext: CaseSeriesExtraction) -> float:
        """
        Score the breadth of organ domain response (1-10).

        Multi-organ response indicates broader therapeutic effect.
        1 domain=4, 2 domains=6, 3 domains=8, 4+ domains=10
        """
        # Collect all endpoint text for matching
        endpoint_texts = []

        # From detailed efficacy endpoints (on extraction, not efficacy)
        if ext.detailed_efficacy_endpoints:
            for ep in ext.detailed_efficacy_endpoints:
                if hasattr(ep, 'endpoint_name') and ep.endpoint_name:
                    endpoint_texts.append(ep.endpoint_name.lower())
                if hasattr(ep, 'endpoint_category') and ep.endpoint_category:
                    endpoint_texts.append(ep.endpoint_category.lower())
                if hasattr(ep, 'notes') and ep.notes:
                    endpoint_texts.append(ep.notes.lower())

        # From efficacy summary
        if ext.efficacy.primary_endpoint:
            endpoint_texts.append(ext.efficacy.primary_endpoint.lower())
        if ext.efficacy.efficacy_summary:
            endpoint_texts.append(ext.efficacy.efficacy_summary.lower())

        # Combine all text for matching
        combined_text = ' '.join(endpoint_texts)

        # Find matching domains using database
        organ_domains = self._get_organ_domains()
        matched_domains = set()
        for domain, keywords in organ_domains.items():
            for keyword in keywords:
                if keyword.lower() in combined_text:
                    matched_domains.add(domain)
                    break  # One match per domain is enough

        # Score based on number of domains
        n_domains = len(matched_domains)
        if n_domains >= 4:
            return 10.0
        elif n_domains == 3:
            return 8.0
        elif n_domains == 2:
            return 6.0
        elif n_domains == 1:
            return 4.0
        else:
            return 3.0  # No domains matched (data quality issue)

    def _get_matched_organ_domains(self, ext: CaseSeriesExtraction) -> List[str]:
        """
        Get list of organ domains matched for an extraction.

        Used for reporting which organ systems showed response.
        """
        # Collect all endpoint text for matching
        endpoint_texts = []

        # From detailed efficacy endpoints
        if ext.detailed_efficacy_endpoints:
            for ep in ext.detailed_efficacy_endpoints:
                if hasattr(ep, 'endpoint_name') and ep.endpoint_name:
                    endpoint_texts.append(ep.endpoint_name.lower())
                if hasattr(ep, 'endpoint_category') and ep.endpoint_category:
                    endpoint_texts.append(ep.endpoint_category.lower())
                if hasattr(ep, 'notes') and ep.notes:
                    endpoint_texts.append(ep.notes.lower())

        # From efficacy summary
        if ext.efficacy.primary_endpoint:
            endpoint_texts.append(ext.efficacy.primary_endpoint.lower())
        if ext.efficacy.efficacy_summary:
            endpoint_texts.append(ext.efficacy.efficacy_summary.lower())

        # Combine all text for matching
        combined_text = ' '.join(endpoint_texts)

        # Find matching domains
        organ_domains = self._get_organ_domains()
        matched_domains = []
        for domain, keywords in organ_domains.items():
            for keyword in keywords:
                if keyword.lower() in combined_text:
                    matched_domains.append(domain)
                    break  # One match per domain is enough

        return sorted(matched_domains)

    def _get_validated_instruments_for_disease(self, disease: str) -> Dict[str, int]:
        """
        Get validated instruments for a disease from the database.

        Returns a dict of instrument_name -> quality_score (1-10).
        Falls back to generic instruments if disease not found.
        """
        if not disease:
            return self._get_generic_instruments()

        # Try database lookup first
        if self.cs_db:
            instruments = self.cs_db.find_instruments_for_disease(disease)
            if instruments:
                return instruments

        # Return generic instruments that apply across diseases
        return self._get_generic_instruments()

    def _get_generic_instruments(self) -> Dict[str, int]:
        """Return generic instruments that apply across diseases."""
        return {
            'Physician Global': 7,
            'Patient Global': 7,
            'SF-36': 8,
            'EQ-5D': 8,
            'Pain VAS': 7,
            'FACIT-Fatigue': 8,
        }

    def _score_endpoint_quality(self, ext: CaseSeriesExtraction) -> float:
        """
        Score endpoint quality based on validated instruments (1-10).

        Uses the database of validated instruments to score endpoints.
        Validated primary endpoints score higher than ad-hoc measures.
        """
        if not ext.detailed_efficacy_endpoints:
            # Fallback: check if primary endpoint mentions validated instruments
            if ext.efficacy.primary_endpoint:
                outcome_lower = ext.efficacy.primary_endpoint.lower()
                # Check for common validated instrument patterns
                validated_patterns = [
                    'acr', 'das28', 'sledai', 'bilag', 'pasi', 'easi',
                    'cdai', 'sdai', 'haq', 'basdai', 'mda', 'sri'
                ]
                if any(p in outcome_lower for p in validated_patterns):
                    return 8.0
            return 5.0  # Unknown quality

        # Get validated instruments for the disease
        disease = ext.disease or ""
        validated_instruments = self._get_validated_instruments_for_disease(disease)

        endpoint_scores = []
        for ep in ext.detailed_efficacy_endpoints:
            ep_name = getattr(ep, 'endpoint_name', '') or ''
            ep_name_lower = ep_name.lower()

            # Check against validated instruments
            best_score = 0
            for instrument, score in validated_instruments.items():
                if instrument.lower() in ep_name_lower or ep_name_lower in instrument.lower():
                    best_score = max(best_score, score)

            # Check for generic validated patterns
            if best_score == 0:
                validated_patterns = {
                    'acr20': 10, 'acr50': 10, 'acr70': 10,
                    'das28': 10, 'sledai': 10, 'bilag': 10,
                    'pasi': 10, 'easi': 10, 'cdai': 9,
                    'remission': 8, 'response': 7,
                }
                for pattern, score in validated_patterns.items():
                    if pattern in ep_name_lower:
                        best_score = max(best_score, score)

            # Boost for primary endpoints
            ep_category = getattr(ep, 'endpoint_category', '') or ''
            if 'primary' in ep_category.lower():
                best_score = min(10, best_score + 1)

            # Boost for statistical significance
            if getattr(ep, 'statistical_significance', False):
                best_score = min(10, best_score + 0.5)

            if best_score > 0:
                endpoint_scores.append(best_score)
            else:
                # Ad-hoc endpoint
                endpoint_scores.append(4.0)

        if endpoint_scores:
            return min(10.0, sum(endpoint_scores) / len(endpoint_scores))
        return 5.0

    def _get_safety_categories(self) -> Dict[str, Dict[str, Any]]:
        """
        Get safety signal categories from database (cached).

        Returns dict mapping category_name to {keywords, severity_weight, regulatory_flag}.
        Falls back to minimal defaults if database unavailable.
        """
        if self._safety_categories is not None:
            return self._safety_categories

        # Try to load from database
        if self.cs_db:
            self._safety_categories = self.cs_db.get_safety_categories()
            if self._safety_categories:
                logger.debug(f"Loaded {len(self._safety_categories)} safety categories from database")
                return self._safety_categories

        # Fallback to minimal defaults
        logger.warning("Using fallback safety categories (database unavailable)")
        self._safety_categories = {
            'serious_infection': {'keywords': ['serious infection', 'sepsis', 'pneumonia', 'tb'], 'severity_weight': 9, 'regulatory_flag': True},
            'malignancy': {'keywords': ['malignancy', 'cancer', 'lymphoma'], 'severity_weight': 10, 'regulatory_flag': True},
            'cardiovascular': {'keywords': ['mace', 'mi', 'stroke', 'heart failure'], 'severity_weight': 9, 'regulatory_flag': True},
            'thromboembolic': {'keywords': ['vte', 'dvt', 'pe', 'thrombosis'], 'severity_weight': 9, 'regulatory_flag': True},
            'hepatotoxicity': {'keywords': ['hepatotoxicity', 'liver injury', 'alt increased'], 'severity_weight': 8, 'regulatory_flag': True},
            'cytopenia': {'keywords': ['neutropenia', 'thrombocytopenia', 'anemia'], 'severity_weight': 7, 'regulatory_flag': True},
            'death': {'keywords': ['death', 'fatal', 'mortality'], 'severity_weight': 10, 'regulatory_flag': True},
        }
        return self._safety_categories

    def _score_safety_profile_detailed(self, ext: CaseSeriesExtraction) -> Tuple[float, Dict[str, Any]]:
        """
        Score safety profile with detailed breakdown by category (1-10).

        Uses database safety categories for MedDRA-aligned classification.
        Returns (score, breakdown_dict).
        """
        breakdown = {
            'categories_detected': [],
            'serious_signals': [],
            'regulatory_flags': [],
            'sae_percentage': None,
            'discontinuation_rate': None,
        }

        # Collect all safety text
        safety_texts = []

        # From detailed safety endpoints (on extraction, not safety)
        if ext.detailed_safety_endpoints:
            for ep in ext.detailed_safety_endpoints:
                if hasattr(ep, 'event_name') and ep.event_name:
                    safety_texts.append(ep.event_name.lower())
                if hasattr(ep, 'event_category') and ep.event_category:
                    safety_texts.append(ep.event_category.lower())

        # From SAE list
        if ext.safety.serious_adverse_events:
            for sae in ext.safety.serious_adverse_events:
                safety_texts.append(sae.lower())

        # From AE list (adverse_events, not common_adverse_events)
        if ext.safety.adverse_events:
            for ae in ext.safety.adverse_events:
                safety_texts.append(ae.lower())

        combined_text = ' '.join(safety_texts)

        # Classify safety signals using database categories
        safety_categories = self._get_safety_categories()
        category_scores = []
        for category, config in safety_categories.items():
            for keyword in config['keywords']:
                if keyword.lower() in combined_text:
                    breakdown['categories_detected'].append(category)
                    category_scores.append(config['severity_weight'])

                    if config['severity_weight'] >= 8:
                        breakdown['serious_signals'].append(category)
                    if config.get('regulatory_flag', False):
                        breakdown['regulatory_flags'].append(category)
                    break  # One match per category

        # Calculate base score from SAE percentage
        base_score = 5.0
        if ext.safety.sae_percentage is not None:
            breakdown['sae_percentage'] = ext.safety.sae_percentage
            sae_pct = ext.safety.sae_percentage
            if sae_pct == 0:
                base_score = 10.0
            elif sae_pct < 5:
                base_score = 8.0
            elif sae_pct < 10:
                base_score = 6.0
            elif sae_pct < 20:
                base_score = 4.0
            else:
                base_score = 2.0
        elif ext.safety.safety_profile == SafetyProfile.FAVORABLE:
            base_score = 9.0
        elif ext.safety.safety_profile == SafetyProfile.ACCEPTABLE:
            base_score = 7.0
        elif ext.safety.safety_profile == SafetyProfile.CONCERNING:
            base_score = 3.0

        # Adjust based on detected categories
        if category_scores:
            avg_severity = sum(category_scores) / len(category_scores)
            # Higher severity = lower safety score
            severity_penalty = (avg_severity - 5) * 0.3  # Scale penalty
            base_score = max(1.0, min(10.0, base_score - severity_penalty))

        # Extra penalty for regulatory flags
        n_regulatory = len(set(breakdown['regulatory_flags']))
        if n_regulatory >= 3:
            base_score = max(1.0, base_score - 2.0)
        elif n_regulatory >= 1:
            base_score = max(1.0, base_score - 1.0)

        # Deduplicate lists
        breakdown['categories_detected'] = list(set(breakdown['categories_detected']))
        breakdown['serious_signals'] = list(set(breakdown['serious_signals']))
        breakdown['regulatory_flags'] = list(set(breakdown['regulatory_flags']))

        return round(base_score, 1), breakdown

    def _score_response_durability(self, ext: CaseSeriesExtraction) -> float:
        """
        Score response durability based on follow-up timepoints (1-10).

        Long-term sustained response scores higher than short-term.
        """
        follow_up = (ext.follow_up_duration or "").lower()

        # Parse follow-up duration
        months = 0

        # Check for years
        year_match = re.search(r'(\d+(?:\.\d+)?)\s*year', follow_up)
        if year_match:
            months = float(year_match.group(1)) * 12

        # Check for months
        month_match = re.search(r'(\d+(?:\.\d+)?)\s*month', follow_up)
        if month_match:
            months = max(months, float(month_match.group(1)))

        # Check for weeks
        week_match = re.search(r'(\d+(?:\.\d+)?)\s*week', follow_up)
        if week_match:
            months = max(months, float(week_match.group(1)) / 4.33)

        # Score based on duration
        if months >= 24:
            duration_score = 10.0
        elif months >= 12:
            duration_score = 9.0
        elif months >= 6:
            duration_score = 7.0
        elif months >= 3:
            duration_score = 5.0
        elif months >= 1:
            duration_score = 3.0
        elif months > 0:
            duration_score = 2.0
        else:
            duration_score = 4.0  # Unknown duration

        # Bonus for sustained response mentioned
        if ext.detailed_efficacy_endpoints:
            for ep in ext.detailed_efficacy_endpoints:
                ep_name = (getattr(ep, 'endpoint_name', '') or '').lower()
                if any(term in ep_name for term in ['sustained', 'durable', 'maintained', 'long-term']):
                    duration_score = min(10.0, duration_score + 1.0)
                    break

        return duration_score

    def _score_extraction_completeness(self, ext: CaseSeriesExtraction) -> float:
        """
        Score data extraction completeness (1-10).

        Higher scores for more complete data extraction.
        """
        completeness_checks = [
            # Source information
            ext.source.pmid is not None,
            ext.source.title is not None and len(ext.source.title) > 10,
            ext.source.journal is not None,
            ext.source.year is not None,

            # Patient population
            ext.patient_population.n_patients is not None and ext.patient_population.n_patients > 0,
            ext.disease is not None,
            ext.patient_population.age_description is not None,

            # Treatment details
            ext.treatment.drug_name is not None,
            ext.treatment.dose is not None,
            ext.treatment.duration is not None,

            # Efficacy data
            ext.efficacy.primary_endpoint is not None,
            ext.efficacy.responders_pct is not None or ext.efficacy.responders_n is not None,
            len(ext.detailed_efficacy_endpoints or []) > 0,

            # Safety data
            len(ext.safety.adverse_events or []) > 0,
            ext.safety.sae_count is not None or ext.safety.sae_percentage is not None,

            # Follow-up
            ext.follow_up_duration is not None,
        ]

        completeness_pct = sum(completeness_checks) / len(completeness_checks)

        # Convert to 1-10 scale
        score = 1.0 + (completeness_pct * 9.0)
        return round(score, 1)

    # -------------------------------------------------------------------------
    # Evidence Quality Component Scores
    # -------------------------------------------------------------------------

    def _score_sample_size(self, ext: CaseSeriesExtraction) -> float:
        """
        Score sample size (1-10).

        N≥50=10, N=20-49=8, N=10-19=6, N=5-9=4, N=2-4=2, N=1=1

        NOTE: This is the legacy method. Use _score_sample_size_v2 for case series.
        """
        # Handle None patient_population or n_patients
        if ext.patient_population is None or ext.patient_population.n_patients is None:
            return 3.0  # Unknown sample size
        n = ext.patient_population.n_patients
        if n >= 50:
            return 10.0
        elif n >= 20:
            return 8.0
        elif n >= 10:
            return 6.0
        elif n >= 5:
            return 4.0
        elif n >= 2:
            return 2.0
        else:
            return 1.0

    def _score_sample_size_v2(self, ext: CaseSeriesExtraction) -> float:
        """
        Score sample size calibrated for case series (1-10).

        For case series, 20+ patients is considered substantial.
        100-patient case series are rare, so thresholds are adjusted accordingly.
        Single case reports get minimal weight.

        Scoring:
        N >= 20: 10 (large case series for this literature type)
        N >= 15: 9  (substantial case series)
        N >= 10: 8  (solid case series)
        N >= 5:  6  (small but acceptable series)
        N >= 3:  4  (minimal case series)
        N >= 2:  2  (two-patient case report)
        N = 1:   1  (single case report)
        N = 0:   1  (unknown, treat as single case)
        """
        # Handle None values for n_patients
        n = 0
        if ext.patient_population and ext.patient_population.n_patients is not None:
            n = ext.patient_population.n_patients

        if n >= 20:
            return 10.0
        elif n >= 15:
            return 9.0
        elif n >= 10:
            return 8.0
        elif n >= 5:
            return 6.0
        elif n >= 3:
            return 4.0
        elif n >= 2:
            return 2.0
        else:
            return 1.0  # N=1 or unknown

    def _score_publication_venue(self, ext: CaseSeriesExtraction) -> float:
        """
        Score publication venue (1-10).

        Peer-reviewed journal=10, Preprint=6, Conference abstract=4, Other=2
        """
        venue = (ext.source.publication_venue or "").lower()

        if 'peer-reviewed' in venue or 'journal' in venue:
            return 10.0
        elif 'preprint' in venue:
            return 6.0
        elif 'conference' in venue or 'abstract' in venue:
            return 4.0
        elif venue and venue != 'unknown':
            return 2.0

        # Try to infer from journal name
        if ext.source.journal:
            # Most journals are peer-reviewed
            return 8.0

        return 5.0  # Unknown

    def _score_followup_duration(self, ext: CaseSeriesExtraction) -> float:
        """
        Score follow-up duration (1-10).

        >1 year=10, 6-12 months=7, 3-6 months=5, 1-3 months=3, <1 month=1
        """
        follow_up = (ext.follow_up_duration or "").lower()

        # Check for years
        if 'year' in follow_up:
            # Try to extract number
            match = re.search(r'(\d+)\s*year', follow_up)
            if match and int(match.group(1)) >= 1:
                return 10.0
            return 10.0

        # Check for months
        if 'month' in follow_up:
            match = re.search(r'(\d+)\s*month', follow_up)
            if match:
                months = int(match.group(1))
                if months >= 12:
                    return 10.0
                elif months >= 6:
                    return 7.0
                elif months >= 3:
                    return 5.0
                elif months >= 1:
                    return 3.0
            return 5.0  # "months" mentioned but unclear

        # Check for weeks
        if 'week' in follow_up:
            match = re.search(r'(\d+)\s*week', follow_up)
            if match:
                weeks = int(match.group(1))
                if weeks >= 4:
                    return 3.0
                else:
                    return 1.0
            return 2.0

        return 5.0  # Unknown

    # -------------------------------------------------------------------------
    # Market Opportunity Component Scores
    # -------------------------------------------------------------------------

    def _score_competitors(self, opp: RepurposingOpportunity) -> float:
        """
        Score based on number of competitors (1-10).

        No approved drugs=10, 1-2=7, 3-5=5, 6-10=3, >10=1
        """
        if not opp.market_intelligence:
            return 5.0

        mi = opp.market_intelligence
        num_drugs = mi.standard_of_care.num_approved_drugs

        if num_drugs == 0:
            return 10.0
        elif num_drugs <= 2:
            return 7.0
        elif num_drugs <= 5:
            return 5.0
        elif num_drugs <= 10:
            return 3.0
        else:
            return 1.0

    def _score_market_size(self, opp: RepurposingOpportunity) -> float:
        """
        Score market size (1-10).

        Market size = patient population × avg annual cost of top 3 branded drugs.
        If no approved drugs, use prevalence-based pricing:
        - Rare (<10K): ~$200K/year
        - Specialty (10K-100K): ~$75K/year
        - Standard (>100K): ~$20K/year

        Scores: >$10B=10, $5-10B=9, $1-5B=8, $500M-1B=7, $100-500M=6,
                $50-100M=5, $10-50M=4, <$10M=2
        """
        if not opp.market_intelligence:
            return 5.0

        mi = opp.market_intelligence
        pop = mi.epidemiology.patient_population_size or 0

        # Use pre-calculated market size if available
        if mi.market_size_usd:
            market_size = mi.market_size_usd
        elif mi.standard_of_care.avg_annual_cost_usd and pop > 0:
            market_size = pop * mi.standard_of_care.avg_annual_cost_usd
        elif pop > 0:
            # Estimate based on prevalence
            if pop < 10000:
                # Rare disease pricing
                annual_cost = 200000
            elif pop < 100000:
                # Specialty pricing
                annual_cost = 75000
            else:
                # Standard pricing
                annual_cost = 20000
            market_size = pop * annual_cost
        else:
            return 5.0  # Unknown

        # Score based on market size
        if market_size >= 10_000_000_000:  # $10B+
            return 10.0
        elif market_size >= 5_000_000_000:  # $5-10B
            return 9.0
        elif market_size >= 1_000_000_000:  # $1-5B
            return 8.0
        elif market_size >= 500_000_000:  # $500M-1B
            return 7.0
        elif market_size >= 100_000_000:  # $100-500M
            return 6.0
        elif market_size >= 50_000_000:  # $50-100M
            return 5.0
        elif market_size >= 10_000_000:  # $10-50M
            return 4.0
        else:  # <$10M
            return 2.0

    def _score_unmet_need(self, opp: RepurposingOpportunity) -> float:
        """
        Score unmet need (1-10).

        Compares efficacy signal from case series vs top 3 approved drugs.
        - Better efficacy than approved options = 10
        - Similar efficacy = 5
        - Worse efficacy = 2
        - No approved drugs for indication = 10
        """
        if not opp.market_intelligence:
            return 5.0

        mi = opp.market_intelligence
        ext = opp.extraction

        # If no approved drugs, unmet need is maximum
        if mi.standard_of_care.num_approved_drugs == 0:
            return 10.0

        # If unmet need is explicitly marked
        if mi.standard_of_care.unmet_need:
            return 10.0

        # Compare case series efficacy to SOC
        case_series_efficacy = ext.efficacy.responders_pct

        # Get average SOC efficacy
        soc_efficacies = []
        for treatment in mi.standard_of_care.top_treatments[:3]:
            if treatment.efficacy_pct:
                soc_efficacies.append(treatment.efficacy_pct)

        if case_series_efficacy and soc_efficacies:
            avg_soc = sum(soc_efficacies) / len(soc_efficacies)

            # Compare: significantly better (+10%) = 10, similar (±10%) = 5, worse = 2
            if case_series_efficacy > avg_soc + 10:
                return 10.0
            elif case_series_efficacy >= avg_soc - 10:
                return 5.0
            else:
                return 2.0

        # Fallback: use efficacy signal
        if ext.efficacy_signal == EfficacySignal.STRONG:
            return 8.0
        elif ext.efficacy_signal == EfficacySignal.MODERATE:
            return 5.0
        elif ext.efficacy_signal == EfficacySignal.WEAK:
            return 3.0

        return 5.0  # Unknown

    # -------------------------------------------------------------------------
    # Cross-Study Aggregation
    # -------------------------------------------------------------------------

    def _aggregate_disease_evidence(
        self,
        disease: str,
        extractions: List[CaseSeriesExtraction]
    ) -> Dict[str, Any]:
        """
        Aggregate evidence across multiple papers for the same disease.

        Returns pooled estimates with confidence metrics:
        - Weighted response rate (by sample size)
        - Response range
        - Heterogeneity assessment
        - Evidence confidence level
        """
        if not extractions:
            return {
                'n_studies': 0,
                'total_patients': 0,
                'total_responders': 0,
                'pooled_response_pct': None,
                'response_range': None,
                'heterogeneity_cv': None,
                'consistency': 'N/A',
                'evidence_confidence': 'None'
            }

        # Collect response rates and sample sizes
        response_data = []
        total_patients = 0
        total_responders = 0

        for ext in extractions:
            # Handle None values for n_patients
            n = 0
            if ext.patient_population and ext.patient_population.n_patients is not None:
                n = ext.patient_population.n_patients
            total_patients += n

            resp_pct = ext.efficacy.responders_pct
            resp_n = ext.efficacy.responders_n

            if resp_n:
                total_responders += resp_n

            if n > 0 and resp_pct is not None:
                response_data.append({
                    'n': n,
                    'response_pct': resp_pct
                })

        # Calculate pooled estimate (weighted by sample size)
        pooled_response = None
        response_range = None
        heterogeneity_cv = None
        consistency = 'N/A'

        if response_data:
            # Weighted average
            total_weight = sum(d['n'] for d in response_data)
            if total_weight > 0:
                pooled_response = sum(
                    d['response_pct'] * d['n'] for d in response_data
                ) / total_weight

            # Range
            rates = [d['response_pct'] for d in response_data]
            response_range = (min(rates), max(rates))

            # Heterogeneity (coefficient of variation)
            if len(rates) >= 2:
                mean_rate = sum(rates) / len(rates)
                if mean_rate > 0:
                    variance = sum((r - mean_rate) ** 2 for r in rates) / len(rates)
                    heterogeneity_cv = (variance ** 0.5) / mean_rate

                    # Classify consistency
                    if heterogeneity_cv < 0.25:
                        consistency = 'High'
                    elif heterogeneity_cv < 0.50:
                        consistency = 'Moderate'
                    else:
                        consistency = 'Low'
            elif len(rates) == 1:
                consistency = 'Single study'

        # Determine evidence confidence (calibrated for case series)
        n_studies = len(extractions)
        evidence_confidence = _calculate_evidence_confidence_case_series(
            n_studies, total_patients, consistency, extractions
        )

        return {
            'n_studies': n_studies,
            'total_patients': total_patients,
            'total_responders': total_responders,
            'pooled_response_pct': round(pooled_response, 1) if pooled_response else None,
            'response_range': response_range,
            'heterogeneity_cv': round(heterogeneity_cv, 2) if heterogeneity_cv else None,
            'consistency': consistency,
            'evidence_confidence': evidence_confidence
        }

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _track_tokens(self, usage) -> None:
        """Track token usage for cost estimation."""
        if hasattr(usage, 'input_tokens'):
            self.total_input_tokens += usage.input_tokens
        if hasattr(usage, 'output_tokens'):
            self.total_output_tokens += usage.output_tokens
        if hasattr(usage, 'cache_creation_input_tokens'):
            self.total_cache_creation_tokens += usage.cache_creation_input_tokens
        if hasattr(usage, 'cache_read_input_tokens'):
            self.total_cache_read_tokens += usage.cache_read_input_tokens

    def _calculate_cost(self) -> float:
        """
        Calculate estimated cost in USD.

        Claude Sonnet 4 pricing (as of 2025):
        - Input: $3 per million tokens
        - Output: $15 per million tokens
        - Cache writes: $3.75 per million tokens (25% premium)
        - Cache reads: $0.30 per million tokens (90% discount)
        """
        input_cost = self.total_input_tokens * 3.0 / 1_000_000
        output_cost = self.total_output_tokens * 15.0 / 1_000_000
        cache_write_cost = self.total_cache_creation_tokens * 3.75 / 1_000_000
        cache_read_cost = self.total_cache_read_tokens * 0.30 / 1_000_000
        return round(input_cost + output_cost + cache_write_cost + cache_read_cost, 4)

    def _clean_json_response(self, text: str) -> str:
        """Clean JSON response from Claude."""
        # Remove markdown code blocks
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        return text.strip()

    # =========================================================================
    # VISUALIZATION METHODS
    # =========================================================================

    def generate_visualizations(
        self,
        result: DrugAnalysisResult,
        excel_filename: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Generate interactive HTML visualizations from analysis results.

        Creates two charts:
        1. Priority Matrix: Clinical Score vs Evidence Score (bubble chart)
        2. Market Opportunity: Competitive Landscape vs Priority Score

        Args:
            result: DrugAnalysisResult to visualize
            excel_filename: Optional Excel filename to derive viz filenames from

        Returns:
            Dict with paths to generated HTML files
        """
        try:
            import plotly.graph_objects as go
            import pandas as pd
        except ImportError:
            logger.error("plotly and pandas required for visualizations. Install with: pip install plotly pandas")
            raise

        # Prepare data from result
        analysis_df = self._prepare_visualization_data(result)

        if analysis_df.empty:
            logger.warning("No data available for visualizations")
            return {}

        # Determine output directory and filenames
        if excel_filename:
            # Use same base name as Excel file
            base_name = Path(excel_filename).stem
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = f"{result.drug_name.lower().replace(' ', '_')}_{timestamp}"

        viz_dir = self.output_dir / 'visualizations'
        viz_dir.mkdir(parents=True, exist_ok=True)

        viz_paths = {}

        # Generate Priority Matrix
        try:
            fig1 = self._create_priority_matrix(analysis_df, result.drug_name)
            path1 = viz_dir / f"{base_name}_priority_matrix.html"
            fig1.write_html(str(path1))
            viz_paths['priority_matrix'] = str(path1)
            logger.info(f"✅ Generated Priority Matrix: {path1}")
        except Exception as e:
            logger.error(f"Error generating priority matrix: {e}")

        # Generate Market Opportunity Chart
        try:
            fig2 = self._create_market_opportunity(analysis_df, result.drug_name)
            path2 = viz_dir / f"{base_name}_market_opportunity.html"
            fig2.write_html(str(path2))
            viz_paths['market_opportunity'] = str(path2)
            logger.info(f"✅ Generated Market Opportunity Chart: {path2}")
        except Exception as e:
            logger.error(f"Error generating market opportunity chart: {e}")

        return viz_paths

    def _prepare_visualization_data(self, result: DrugAnalysisResult) -> 'pd.DataFrame':
        """Prepare data for visualizations from DrugAnalysisResult."""
        import pandas as pd

        # Group opportunities by disease
        disease_data = {}
        for opp in result.opportunities:
            disease = opp.extraction.disease_normalized or opp.extraction.disease

            if disease not in disease_data:
                disease_data[disease] = {
                    'opportunities': [],
                    'total_patients': 0,
                    'n_studies': 0
                }

            disease_data[disease]['opportunities'].append(opp)
            disease_data[disease]['n_studies'] += 1

            # Add patient count
            if opp.extraction.patient_population and opp.extraction.patient_population.n_patients:
                disease_data[disease]['total_patients'] += opp.extraction.patient_population.n_patients

        # Build dataframe
        rows = []
        for disease, data in disease_data.items():
            opps = data['opportunities']

            # Calculate average scores
            avg_clinical = sum(o.scores.clinical_signal for o in opps if o.scores) / len(opps) if opps else 0
            avg_evidence = sum(o.scores.evidence_quality for o in opps if o.scores) / len(opps) if opps else 0
            avg_market = sum(o.scores.market_opportunity for o in opps if o.scores) / len(opps) if opps else 0
            avg_overall = sum(o.scores.overall_priority for o in opps if o.scores) / len(opps) if opps else 0

            # Get market intelligence from best opportunity
            best_opp = max(opps, key=lambda o: o.scores.overall_priority if o.scores else 0)
            mi = best_opp.market_intelligence

            rows.append({
                'Disease': disease,
                '# Studies': data['n_studies'],
                'Total Patients': data['total_patients'],
                'Clinical Score (avg)': round(avg_clinical, 1),
                'Evidence Score (avg)': round(avg_evidence, 1),
                'Market Score (avg)': round(avg_market, 1),
                'Overall Score (avg)': round(avg_overall, 1),
                '# Approved Competitors': mi.standard_of_care.num_approved_drugs if mi and mi.standard_of_care else 0,
                'Unmet Need': 'Yes' if mi and mi.standard_of_care and mi.standard_of_care.unmet_need else 'No',
                'TAM Estimate': mi.tam_estimate if mi else None
            })

        return pd.DataFrame(rows)

    def _create_priority_matrix(self, df: 'pd.DataFrame', drug_name: str):
        """Create priority matrix visualization with filtering."""
        import plotly.graph_objects as go
        import pandas as pd

        # Prepare data
        df = df.copy()
        df['disease_short'] = df['Disease'].apply(lambda x: self._shorten_disease(x, max_len=25))
        df['n_patients'] = df['Total Patients'].fillna(0).astype(int)
        df['bubble_size'] = df['n_patients'].apply(lambda x: max(10, min(80, 10 + x * 2)))

        # Sort by overall score descending
        df = df.sort_values('Overall Score (avg)', ascending=False)

        # Create figure with single trace (all data)
        fig = go.Figure()

        # Add main scatter trace
        fig.add_trace(go.Scatter(
            x=df['Clinical Score (avg)'],
            y=df['Evidence Score (avg)'],
            mode='markers+text',
            marker=dict(
                size=df['bubble_size'],
                color=df['Overall Score (avg)'],
                colorscale='Viridis',  # Better color scale: purple (low) to yellow (high)
                cmin=df['Overall Score (avg)'].min(),
                cmax=df['Overall Score (avg)'].max(),
                line=dict(width=2, color='white'),
                opacity=0.8,
                showscale=True,
                colorbar=dict(
                    title="Overall<br>Score",
                    thickness=15,
                    len=0.7
                )
            ),
            text=df['disease_short'],
            textposition='top center',
            textfont=dict(size=10, color='#333'),
            customdata=df[['Disease', 'Overall Score (avg)', 'n_patients', '# Studies']].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Clinical Score: %{x:.1f}<br>"
                "Evidence Score: %{y:.1f}<br>"
                "Overall Score: %{customdata[1]:.1f}<br>"
                "Total Patients: %{customdata[2]}<br>"
                "# Studies: %{customdata[3]}<br>"
                "<extra></extra>"
            ),
            name='All Opportunities',
            visible=True
        ))

        # Add filtered traces for top N opportunities
        for top_n in [10, 20, 30]:
            df_filtered = df.head(top_n)
            fig.add_trace(go.Scatter(
                x=df_filtered['Clinical Score (avg)'],
                y=df_filtered['Evidence Score (avg)'],
                mode='markers+text',
                marker=dict(
                    size=df_filtered['bubble_size'],
                    color=df_filtered['Overall Score (avg)'],
                    colorscale='Viridis',
                    cmin=df['Overall Score (avg)'].min(),
                    cmax=df['Overall Score (avg)'].max(),
                    line=dict(width=2, color='white'),
                    opacity=0.8,
                    showscale=True,
                    colorbar=dict(
                        title="Overall<br>Score",
                        thickness=15,
                        len=0.7
                    )
                ),
                text=df_filtered['disease_short'],
                textposition='top center',
                textfont=dict(size=10, color='#333'),
                customdata=df_filtered[['Disease', 'Overall Score (avg)', 'n_patients', '# Studies']].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Clinical Score: %{x:.1f}<br>"
                    "Evidence Score: %{y:.1f}<br>"
                    "Overall Score: %{customdata[1]:.1f}<br>"
                    "Total Patients: %{customdata[2]}<br>"
                    "# Studies: %{customdata[3]}<br>"
                    "<extra></extra>"
                ),
                name=f'Top {top_n}',
                visible=False
            ))

        # Create dropdown menu for filtering
        buttons = [
            dict(label='All Opportunities',
                 method='update',
                 args=[{'visible': [True, False, False, False]}]),
            dict(label='Top 10',
                 method='update',
                 args=[{'visible': [False, True, False, False]}]),
            dict(label='Top 20',
                 method='update',
                 args=[{'visible': [False, False, True, False]}]),
            dict(label='Top 30',
                 method='update',
                 args=[{'visible': [False, False, False, True]}])
        ]

        fig.update_layout(
            title=dict(
                text=f'<b>{drug_name.upper()} Repurposing Opportunities</b><br>'
                     f'<sup>Priority Matrix: Clinical Signal vs Evidence Quality</sup>',
                x=0.5,
                font=dict(size=18)
            ),
            xaxis=dict(
                title='Clinical Score (Efficacy + Safety)',
                range=[4, 10],
                dtick=1,
                gridcolor='lightgray'
            ),
            yaxis=dict(
                title='Evidence Score (Sample Size + Quality)',
                range=[3, 10],
                dtick=1,
                gridcolor='lightgray'
            ),
            plot_bgcolor='white',
            height=700,
            updatemenus=[
                dict(
                    buttons=buttons,
                    direction='down',
                    pad={'r': 10, 't': 10},
                    showactive=True,
                    x=0.98,
                    xanchor='right',
                    y=1.15,
                    yanchor='top',
                    bgcolor='white',
                    bordercolor='#ccc',
                    borderwidth=1
                )
            ],
            annotations=[
                dict(
                    text="Bubble size = Total patients<br>Color = Overall priority score (purple=low, yellow=high)",
                    xref="paper", yref="paper",
                    x=0.02, y=0.98,
                    showarrow=False,
                    font=dict(size=10, color='gray'),
                    align='left'
                ),
                dict(
                    text="Filter:",
                    xref="paper", yref="paper",
                    x=0.88, y=1.15,
                    showarrow=False,
                    font=dict(size=12, color='#333'),
                    xanchor='right'
                )
            ]
        )

        return fig

    def _create_market_opportunity(self, df: 'pd.DataFrame', drug_name: str):
        """Create market opportunity visualization with filtering."""
        import plotly.graph_objects as go
        import pandas as pd

        # Prepare data
        df = df.copy()
        df['disease_short'] = df['Disease'].apply(lambda x: self._shorten_disease(x, max_len=25))
        df['n_patients'] = df['Total Patients'].fillna(0).astype(int)
        df['bubble_size'] = df['n_patients'].apply(lambda x: max(10, min(80, 10 + x * 2)))
        df['competitors'] = df.get('# Approved Competitors', pd.Series([0] * len(df))).fillna(0).astype(int)

        # Sort by overall score descending
        df = df.sort_values('Overall Score (avg)', ascending=False)

        # Create figure
        fig = go.Figure()

        # Add main scatter trace
        fig.add_trace(go.Scatter(
            x=df['competitors'],
            y=df['Overall Score (avg)'],
            mode='markers+text',
            marker=dict(
                size=df['bubble_size'],
                color=df['Clinical Score (avg)'],
                colorscale='Plasma',  # Purple to yellow/orange gradient
                cmin=df['Clinical Score (avg)'].min(),
                cmax=df['Clinical Score (avg)'].max(),
                line=dict(width=2, color='white'),
                opacity=0.8,
                showscale=True,
                colorbar=dict(
                    title="Clinical<br>Score",
                    thickness=15,
                    len=0.7
                )
            ),
            text=df['disease_short'],
            textposition='top center',
            textfont=dict(size=10, color='#333'),
            customdata=df[['Disease', 'Clinical Score (avg)', 'n_patients', 'Unmet Need']].values,
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Overall Score: %{y:.1f}<br>"
                "Clinical Score: %{customdata[1]:.1f}<br>"
                "# Competitors: %{x}<br>"
                "Total Patients: %{customdata[2]}<br>"
                "Unmet Need: %{customdata[3]}<br>"
                "<extra></extra>"
            ),
            name='All Opportunities',
            visible=True
        ))

        # Add filtered traces for top N opportunities
        for top_n in [10, 20, 30]:
            df_filtered = df.head(top_n)
            fig.add_trace(go.Scatter(
                x=df_filtered['competitors'],
                y=df_filtered['Overall Score (avg)'],
                mode='markers+text',
                marker=dict(
                    size=df_filtered['bubble_size'],
                    color=df_filtered['Clinical Score (avg)'],
                    colorscale='Plasma',
                    cmin=df['Clinical Score (avg)'].min(),
                    cmax=df['Clinical Score (avg)'].max(),
                    line=dict(width=2, color='white'),
                    opacity=0.8,
                    showscale=True,
                    colorbar=dict(
                        title="Clinical<br>Score",
                        thickness=15,
                        len=0.7
                    )
                ),
                text=df_filtered['disease_short'],
                textposition='top center',
                textfont=dict(size=10, color='#333'),
                customdata=df_filtered[['Disease', 'Clinical Score (avg)', 'n_patients', 'Unmet Need']].values,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "Overall Score: %{y:.1f}<br>"
                    "Clinical Score: %{customdata[1]:.1f}<br>"
                    "# Competitors: %{x}<br>"
                    "Total Patients: %{customdata[2]}<br>"
                    "Unmet Need: %{customdata[3]}<br>"
                    "<extra></extra>"
                ),
                name=f'Top {top_n}',
                visible=False
            ))

        # Create dropdown menu for filtering
        buttons = [
            dict(label='All Opportunities',
                 method='update',
                 args=[{'visible': [True, False, False, False]}]),
            dict(label='Top 10',
                 method='update',
                 args=[{'visible': [False, True, False, False]}]),
            dict(label='Top 20',
                 method='update',
                 args=[{'visible': [False, False, True, False]}]),
            dict(label='Top 30',
                 method='update',
                 args=[{'visible': [False, False, False, True]}])
        ]

        fig.update_layout(
            title=dict(
                text=f'<b>{drug_name.upper()} Market Opportunity Analysis</b><br>'
                     f'<sup>Competitive Landscape vs Priority Score</sup>',
                x=0.5,
                font=dict(size=18)
            ),
            xaxis=dict(
                title='Number of Approved Competitors',
                dtick=1,
                gridcolor='lightgray'
            ),
            yaxis=dict(
                title='Overall Priority Score',
                range=[5, 10],
                dtick=1,
                gridcolor='lightgray'
            ),
            plot_bgcolor='white',
            height=700,
            updatemenus=[
                dict(
                    buttons=buttons,
                    direction='down',
                    pad={'r': 10, 't': 10},
                    showactive=True,
                    x=0.98,
                    xanchor='right',
                    y=1.15,
                    yanchor='top',
                    bgcolor='white',
                    bordercolor='#ccc',
                    borderwidth=1
                )
            ],
            annotations=[
                dict(
                    text="Bubble size = Total patients<br>Color = Clinical score (purple=low, orange=high)<br>"
                         "Sweet spot: High priority + Low competition",
                    xref="paper", yref="paper",
                    x=0.02, y=0.98,
                    showarrow=False,
                    font=dict(size=10, color='gray'),
                    align='left'
                ),
                dict(
                    text="Filter:",
                    xref="paper", yref="paper",
                    x=0.88, y=1.15,
                    showarrow=False,
                    font=dict(size=12, color='#333'),
                    xanchor='right'
                )
            ]
        )

        return fig

    @staticmethod
    def _shorten_disease(name: str, max_len: int = 30) -> str:
        """Shorten disease names for display."""
        if len(str(name)) <= max_len:
            return str(name)

        # Common abbreviations
        abbrevs = {
            'Transplantation-associated Thrombotic Microangiopathy': 'TA-TMA',
            'Membranoproliferative Glomerulonephritis': 'MPGN',
            'Autoimmune Hemolytic Anemia': 'AIHA',
            'C3 Glomerulopathy': 'C3G',
            'Cold Agglutinin Disease': 'CAD',
            'Atypical Hemolytic Uremic Syndrome': 'aHUS',
            'Paroxysmal Nocturnal Hemoglobinuria': 'PNH',
        }

        for full, short in abbrevs.items():
            if full.lower() in name.lower():
                return short

        return str(name)[:max_len-3] + '...'

    # =========================================================================
    # EXPORT METHODS
    # =========================================================================

    def export_to_json(self, result: DrugAnalysisResult, filename: Optional[str] = None) -> str:
        """Export analysis result to JSON."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{result.drug_name.lower().replace(' ', '_')}_{timestamp}.json"

        filepath = self.output_dir / filename

        with open(filepath, 'w') as f:
            json.dump(result.model_dump(mode='json'), f, indent=2, default=str)

        logger.info(f"Exported to JSON: {filepath}")
        return str(filepath)

    def _generate_analysis_summary_sheet(
        self,
        result: DrugAnalysisResult,
        writer,
        pd
    ) -> None:
        """
        Generate consolidated Analysis Summary sheet as first sheet in Excel export.

        Shows top 5 opportunities with aggregated evidence across studies.
        """
        # Group opportunities by disease
        disease_groups: Dict[str, List[RepurposingOpportunity]] = {}
        for opp in result.opportunities:
            disease = opp.extraction.disease_normalized or opp.extraction.disease or 'Unknown'
            if disease not in disease_groups:
                disease_groups[disease] = []
            disease_groups[disease].append(opp)

        # Calculate aggregated metrics for each disease
        disease_summaries = []
        for disease, opps in disease_groups.items():
            # Get extractions for aggregation
            extractions = [opp.extraction for opp in opps]

            # Aggregate evidence
            evidence = self._aggregate_disease_evidence(disease, extractions)

            # Get best opportunity for this disease (highest overall score)
            best_opp = max(opps, key=lambda o: o.scores.overall_priority if o.scores else 0)

            # Calculate average scores across all studies for this disease
            avg_clinical = sum(o.scores.clinical_signal for o in opps if o.scores) / len(opps) if opps else 0
            avg_evidence = sum(o.scores.evidence_quality for o in opps if o.scores) / len(opps) if opps else 0
            avg_market = sum(o.scores.market_opportunity for o in opps if o.scores) / len(opps) if opps else 0
            avg_overall = sum(o.scores.overall_priority for o in opps if o.scores) / len(opps) if opps else 0

            # Get market intelligence from best opportunity
            mi = best_opp.market_intelligence

            disease_summaries.append({
                'disease': disease,
                'n_studies': evidence['n_studies'],
                'total_patients': evidence['total_patients'],
                'pooled_response_pct': evidence['pooled_response_pct'],
                'response_range': evidence['response_range'],
                'consistency': evidence['consistency'],
                'evidence_confidence': evidence['evidence_confidence'],
                'avg_clinical_score': round(avg_clinical, 1),
                'avg_evidence_score': round(avg_evidence, 1),
                'avg_market_score': round(avg_market, 1),
                'avg_overall_score': round(avg_overall, 1),
                'best_overall_score': best_opp.scores.overall_priority if best_opp.scores else 0,
                'market_intelligence': mi,
                'best_opp': best_opp
            })

        # Sort by average overall score and take top 5
        disease_summaries.sort(key=lambda x: x['avg_overall_score'], reverse=True)
        top_5 = disease_summaries[:5]

        # Build summary data
        summary_rows = []
        for i, ds in enumerate(top_5, 1):
            mi = ds['market_intelligence']

            # Format response range
            range_str = None
            if ds['response_range']:
                range_str = f"{ds['response_range'][0]:.0f}%-{ds['response_range'][1]:.0f}%"

            # Get market info
            competitors = mi.standard_of_care.num_approved_drugs if mi and mi.standard_of_care else None
            pipeline = mi.standard_of_care.num_pipeline_therapies if mi and mi.standard_of_care else None
            unmet_need = mi.standard_of_care.unmet_need if mi and mi.standard_of_care else None
            tam = mi.tam_estimate if mi else None

            summary_rows.append({
                'Rank': i,
                'Disease': ds['disease'],
                '# Studies': ds['n_studies'],
                'Total Patients': ds['total_patients'],
                'Pooled Response (%)': ds['pooled_response_pct'],
                'Response Range': range_str,
                'Consistency': ds['consistency'],
                'Evidence Confidence': ds['evidence_confidence'],
                'Clinical Score (avg)': ds['avg_clinical_score'],
                'Evidence Score (avg)': ds['avg_evidence_score'],
                'Market Score (avg)': ds['avg_market_score'],
                'Overall Score (avg)': ds['avg_overall_score'],
                'Best Study Score': ds['best_overall_score'],
                '# Approved Competitors': competitors,
                '# Pipeline Therapies': pipeline,
                'Unmet Need': 'Yes' if unmet_need else 'No' if unmet_need is False else 'Unknown',
                'TAM Estimate': tam
            })

        # Write to Excel
        if summary_rows:
            df = pd.DataFrame(summary_rows)
            df.to_excel(writer, sheet_name='Analysis Summary', index=False)
        else:
            # Empty summary
            pd.DataFrame({'Note': ['No opportunities found']}).to_excel(
                writer, sheet_name='Analysis Summary', index=False
            )

    def export_to_excel(
        self,
        result: DrugAnalysisResult,
        filename: Optional[str] = None,
        generate_visualizations: bool = True,
        generate_text_report: bool = True
    ) -> str:
        """Export analysis result to Excel with multiple sheets.

        Args:
            result: DrugAnalysisResult to export
            filename: Optional filename (auto-generated if None)
            generate_visualizations: Whether to generate interactive HTML visualizations
            generate_text_report: Whether to generate analytical text report

        Returns:
            Path to generated Excel file
        """
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas required for Excel export. Install with: pip install pandas openpyxl")
            raise

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{result.drug_name.lower().replace(' ', '_')}_{timestamp}.xlsx"

        filepath = self.output_dir / filename

        # Calculate estimated cost from token usage (using correct pricing)
        input_cost = result.total_input_tokens * 3.0 / 1_000_000  # $3/1M input tokens
        output_cost = result.total_output_tokens * 15.0 / 1_000_000  # $15/1M output tokens
        estimated_cost = input_cost + output_cost

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Analysis Summary sheet (first sheet - consolidated top 5 opportunities)
            self._generate_analysis_summary_sheet(result, writer, pd)

            # Drug Summary sheet
            summary_data = {
                'Drug': [result.drug_name],
                'Generic Name': [result.generic_name],
                'Mechanism': [result.mechanism],
                'Approved Indications': [', '.join(result.approved_indications)],
                'Papers Screened': [result.papers_screened or len(result.opportunities)],
                'Opportunities Found': [len(result.opportunities)],
                'Analysis Date': [result.analysis_date.strftime("%Y-%m-%d %H:%M")],
                'Input Tokens': [result.total_input_tokens],
                'Output Tokens': [result.total_output_tokens],
                'Estimated Cost': [f"${estimated_cost:.2f}"]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Drug Summary', index=False)

            # Opportunities sheet - enhanced with detailed endpoints
            if result.opportunities:
                opp_data = []
                for opp in result.opportunities:
                    ext = opp.extraction
                    eff = ext.efficacy
                    saf = ext.safety

                    # Get organ domains matched for this extraction
                    organ_domains_matched = self._get_matched_organ_domains(ext)

                    # Get score breakdowns if available
                    clinical_breakdown = (opp.scores.clinical_breakdown if opp.scores and opp.scores.clinical_breakdown else {})
                    evidence_breakdown = (opp.scores.evidence_breakdown if opp.scores and opp.scores.evidence_breakdown else {})

                    opp_data.append({
                        'Rank': opp.rank,
                        'Disease (Standardized)': ext.disease_normalized or ext.disease,
                        'Disease (Original)': ext.disease if ext.disease_normalized else None,
                        'Evidence Level': ext.evidence_level.value,
                        'N Patients': ext.patient_population.n_patients,
                        # Efficacy details
                        'Primary Endpoint': eff.primary_endpoint or 'Not specified',
                        'Endpoint Result': eff.endpoint_result or eff.response_rate,
                        'Response Rate': eff.response_rate,
                        'Responders (%)': eff.responders_pct,
                        'Time to Response': eff.time_to_response,
                        'Duration of Response': eff.duration_of_response,
                        'Efficacy Summary': eff.efficacy_summary,
                        # Safety details
                        'Safety Profile': saf.safety_profile.value,
                        'SAE Count': saf.sae_count,
                        'SAE (%)': saf.sae_percentage,
                        'Discontinuations': saf.discontinuations_n,
                        'Adverse Events': '; '.join(saf.adverse_events or [])[:200] if saf.adverse_events else None,
                        # Serious AEs: show list if available, otherwise show count info
                        'Serious AEs': (
                            '; '.join(saf.serious_adverse_events)[:200] if saf.serious_adverse_events
                            else f"{saf.sae_count} SAE(s)" if saf.sae_count and saf.sae_count > 0
                            else "None reported" if saf.sae_count == 0
                            else None
                        ),
                        'Safety Summary': saf.safety_summary,
                        # Scores - Overall
                        'Clinical Score': opp.scores.clinical_signal if opp.scores else None,
                        'Evidence Score': opp.scores.evidence_quality if opp.scores else None,
                        'Market Score': opp.scores.market_opportunity if opp.scores else None,
                        'Overall Priority': opp.scores.overall_priority if opp.scores else None,
                        # Scores - Clinical Breakdown (v2: quality-weighted efficacy)
                        'Response Rate Score (Quality-Weighted)': clinical_breakdown.get('response_rate_quality_weighted'),
                        'Safety Score': clinical_breakdown.get('safety_profile'),
                        'Organ Domain Score': clinical_breakdown.get('organ_domain_breadth'),
                        '# Efficacy Endpoints Scored': clinical_breakdown.get('efficacy_endpoint_count'),
                        'Efficacy Concordance': clinical_breakdown.get('efficacy_concordance'),
                        # Organ Domains
                        'Organ Domains Matched': ', '.join(organ_domains_matched) if organ_domains_matched else None,
                        'N Organ Domains': len(organ_domains_matched),
                        # Source
                        'Key Findings': ext.key_findings,
                        'Source': ext.source.title,
                        'PMID': ext.source.pmid,
                        'Year': ext.source.year
                    })
                pd.DataFrame(opp_data).to_excel(writer, sheet_name='Opportunities', index=False)

            # Score Breakdown sheet - detailed calculation transparency
            score_breakdown_data = []
            for opp in result.opportunities:
                ext = opp.extraction
                scores = opp.scores

                # Get breakdown dicts
                clinical_bd = scores.clinical_breakdown or {}
                evidence_bd = scores.evidence_breakdown or {}
                market_bd = scores.market_breakdown or {}

                # Format safety categories and regulatory flags
                safety_cats = clinical_bd.get('safety_categories', [])
                safety_cats_str = ', '.join(safety_cats) if safety_cats else 'None detected'
                reg_flags = clinical_bd.get('regulatory_flags', [])
                reg_flags_str = ', '.join(reg_flags) if reg_flags else 'None'

                score_breakdown_data.append({
                    'Rank': opp.rank,
                    'Disease': ext.disease_normalized or ext.disease,
                    'PMID': ext.source.pmid if ext.source else None,

                    # Overall Scores
                    'Overall Priority Score': f"{scores.overall_priority:.2f}",
                    'Clinical Signal (50%)': f"{scores.clinical_signal:.2f}",
                    'Evidence Quality (25%)': f"{scores.evidence_quality:.2f}",
                    'Market Opportunity (25%)': f"{scores.market_opportunity:.2f}",

                    # Clinical Signal Breakdown (50% of total)
                    'Clinical - Response Rate (40%)': f"{scores.response_rate_score:.2f}",
                    'Clinical - Safety Profile (40%)': f"{scores.safety_profile_score:.2f}",
                    'Clinical - Organ Domain (20%)': f"{scores.organ_domain_score:.2f}",
                    'Clinical - # Efficacy Endpoints': clinical_bd.get('efficacy_endpoint_count', 'N/A'),
                    'Clinical - Efficacy Concordance': f"{clinical_bd.get('efficacy_concordance', 0):.1%}" if clinical_bd.get('efficacy_concordance') else 'N/A',
                    'Clinical - Safety Categories': safety_cats_str,
                    'Clinical - Regulatory Flags': reg_flags_str,
                    'Clinical - Response Rate Detail': f"Quality-weighted: {clinical_bd.get('response_rate_quality_weighted', 'N/A')}",

                    # Evidence Quality Breakdown (25% of total)
                    'Evidence - Sample Size (35%)': f"{scores.sample_size_score:.2f}",
                    'Evidence - Publication Venue (25%)': f"{scores.publication_venue_score:.2f}",
                    'Evidence - Follow-up Duration (25%)': f"{scores.followup_duration_score:.2f}",
                    'Evidence - Extraction Completeness (15%)': f"{scores.extraction_completeness_score:.2f}",
                    'Evidence - Sample Size (n)': evidence_bd.get('sample_size', 'N/A'),
                    'Evidence - Venue': evidence_bd.get('venue', 'N/A'),
                    'Evidence - Follow-up (months)': evidence_bd.get('followup_months', 'N/A'),

                    # Market Opportunity Breakdown (25% of total)
                    'Market - Competitors (33%)': f"{scores.competitors_score:.2f}",
                    'Market - Market Size (33%)': f"{scores.market_size_score:.2f}",
                    'Market - Unmet Need (33%)': f"{scores.unmet_need_score:.2f}",
                    'Market - # Approved Drugs': market_bd.get('num_approved_drugs', 'N/A'),
                    'Market - TAM Estimate': market_bd.get('tam_estimate', 'N/A'),
                    'Market - Unmet Need?': market_bd.get('unmet_need', 'N/A'),

                    # Calculation Formula
                    'Formula': f"Overall = (Clinical×0.5) + (Evidence×0.25) + (Market×0.25) = ({scores.clinical_signal:.2f}×0.5) + ({scores.evidence_quality:.2f}×0.25) + ({scores.market_opportunity:.2f}×0.25) = {scores.overall_priority:.2f}"
                })

            if score_breakdown_data:
                pd.DataFrame(score_breakdown_data).to_excel(writer, sheet_name='Score Breakdown', index=False)

            # Market Intelligence sheet - enhanced with TAM and pipeline details
            market_data = []
            for opp in result.opportunities:
                if opp.market_intelligence:
                    mi = opp.market_intelligence
                    epi = mi.epidemiology
                    soc = mi.standard_of_care

                    # Format pipeline therapies with details
                    pipeline_details_formatted = None
                    if soc.pipeline_therapies:
                        pipeline_items = []
                        for pt in soc.pipeline_therapies:
                            item = f"{pt.drug_name} ({pt.phase})"
                            if pt.company:
                                item += f" - {pt.company}"
                            if pt.trial_id:
                                item += f" [{pt.trial_id}]"
                            pipeline_items.append(item)
                        pipeline_details_formatted = "; ".join(pipeline_items)
                    elif soc.pipeline_details:
                        pipeline_details_formatted = soc.pipeline_details

                    # Group sources by category into separate columns
                    sources_by_category = {
                        'Epidemiology': [],
                        'Approved Treatments': [],
                        'Treatment Paradigm': [],
                        'Pipeline/Clinical Trials': [],
                        'TAM/Market Analysis': []
                    }
                    if mi.attributed_sources:
                        for src in mi.attributed_sources:
                            if src.attribution in sources_by_category:
                                sources_by_category[src.attribution].append(src.url or src.title or 'Unknown')

                    # Format each category as comma-separated URLs
                    sources_epidemiology = ', '.join(sources_by_category['Epidemiology']) if sources_by_category['Epidemiology'] else None
                    sources_approved = ', '.join(sources_by_category['Approved Treatments']) if sources_by_category['Approved Treatments'] else None
                    sources_treatment = ', '.join(sources_by_category['Treatment Paradigm']) if sources_by_category['Treatment Paradigm'] else None
                    sources_pipeline = ', '.join(sources_by_category['Pipeline/Clinical Trials']) if sources_by_category['Pipeline/Clinical Trials'] else None
                    sources_tam = ', '.join(sources_by_category['TAM/Market Analysis']) if sources_by_category['TAM/Market Analysis'] else None

                    market_data.append({
                        'Disease': mi.disease,
                        # Epidemiology
                        'US Prevalence': epi.us_prevalence_estimate,
                        'US Incidence': epi.us_incidence_estimate,
                        'Patient Population': epi.patient_population_size,
                        'Prevalence Trend': epi.trend,
                        # Competitive landscape - branded innovative drugs only
                        'Approved Treatments (Count)': soc.num_approved_drugs,
                        'Approved Drug Names': ', '.join(soc.approved_drug_names) if soc.approved_drug_names else None,
                        'Pipeline Therapies (Count)': soc.num_pipeline_therapies,
                        'Pipeline Details': pipeline_details_formatted,
                        'Treatment Paradigm': soc.treatment_paradigm,
                        'Top Treatments': ', '.join([f"{t.drug_name} ({'FDA' if t.fda_approved else 'off-label'})" for t in soc.top_treatments]) if soc.top_treatments else None,
                        # Unmet need
                        'Unmet Need': 'Yes' if soc.unmet_need else 'No',
                        'Unmet Need Description': soc.unmet_need_description,
                        # Market - Simple calculation (backward compatibility)
                        'Avg Annual Cost (USD)': soc.avg_annual_cost_usd,
                        'Market Size Estimate': mi.market_size_estimate,
                        'Market Size (USD)': mi.market_size_usd,
                        'Market Growth Rate': mi.growth_rate,
                        # TAM - Sophisticated market analysis (NEW)
                        'TAM (Total Addressable Market)': mi.tam_estimate,
                        'TAM (USD)': mi.tam_usd,
                        'TAM Rationale': mi.tam_rationale,
                        # Additional context
                        'Competitive Landscape': soc.competitive_landscape,
                        # Sources - Separate columns by category for easy filtering
                        'Sources - Epidemiology': sources_epidemiology,
                        'Sources - Approved Drugs': sources_approved,
                        'Sources - Treatment': sources_treatment,
                        'Sources - Pipeline': sources_pipeline,
                        'Sources - TAM/Market': sources_tam
                    })
            if market_data:
                pd.DataFrame(market_data).to_excel(writer, sheet_name='Market Intelligence', index=False)

            # Detailed Efficacy Endpoints sheet (from multi-stage extraction)
            efficacy_data = []
            for opp in result.opportunities:
                ext = opp.extraction
                disease = ext.disease_normalized or ext.disease
                pmid = ext.source.pmid if ext.source else None

                # Get study-level N as fallback for per-endpoint N
                study_n = ext.patient_population.n_patients if ext.patient_population else None

                # Get detailed endpoints if available
                detailed_eps = getattr(ext, 'detailed_efficacy_endpoints', []) or []
                for ep in detailed_eps:
                    # Handle both dict and Pydantic model
                    if hasattr(ep, 'model_dump'):
                        ep_dict = ep.model_dump()
                    elif isinstance(ep, dict):
                        ep_dict = ep
                    else:
                        continue

                    # Derive Is Primary from endpoint_category
                    endpoint_category = ep_dict.get('endpoint_category', '')
                    is_primary = endpoint_category.lower() == 'primary' if endpoint_category else False

                    # Use per-endpoint total_n if available, otherwise fall back to study N
                    endpoint_total_n = ep_dict.get('total_n') or study_n

                    efficacy_data.append({
                        'Disease': disease,
                        'PMID': pmid,
                        'Endpoint Name': ep_dict.get('endpoint_name'),
                        'Endpoint Category': endpoint_category,
                        'Is Primary': is_primary,
                        'Baseline Value': ep_dict.get('baseline_value'),
                        'Final Value': ep_dict.get('final_value'),
                        'Change from Baseline': ep_dict.get('change_from_baseline'),
                        'Percent Change': ep_dict.get('change_pct'),  # Fixed: was percent_change
                        'P-value': ep_dict.get('p_value'),
                        'Statistical Significance': ep_dict.get('statistical_significance'),
                        'Responders (n)': ep_dict.get('responders_n'),
                        'Total (n)': endpoint_total_n,  # Falls back to study N if not specified
                        # Calculate response rate: use extracted value, or compute from n/total
                        'Response Rate (%)': (
                            ep_dict.get('responders_pct') or
                            (round(ep_dict.get('responders_n') / endpoint_total_n * 100, 1)
                             if ep_dict.get('responders_n') and endpoint_total_n else None)
                        ),
                        'Timepoint': ep_dict.get('timepoint'),
                        'Measurement Type': ep_dict.get('measurement_type'),  # Fixed: was measurement_method
                        'Notes': ep_dict.get('notes')
                    })

            if efficacy_data:
                pd.DataFrame(efficacy_data).to_excel(writer, sheet_name='Efficacy Endpoints', index=False)

            # Detailed Safety Endpoints sheet (from multi-stage extraction)
            safety_data = []
            for opp in result.opportunities:
                ext = opp.extraction
                disease = ext.disease_normalized or ext.disease
                pmid = ext.source.pmid if ext.source else None

                # Get study-level N as fallback for per-event N
                study_n = ext.patient_population.n_patients if ext.patient_population else None

                # Get detailed endpoints if available
                detailed_eps = getattr(ext, 'detailed_safety_endpoints', []) or []
                for ep in detailed_eps:
                    # Handle both dict and Pydantic model
                    if hasattr(ep, 'model_dump'):
                        ep_dict = ep.model_dump()
                    elif isinstance(ep, dict):
                        ep_dict = ep
                    else:
                        continue

                    # Extract values with correct field names (matching schema)
                    patients_affected_n = ep_dict.get('patients_affected_n')
                    patients_affected_pct = ep_dict.get('patients_affected_pct')

                    # Determine total patients: use study N as fallback
                    total_patients_n = study_n

                    # Calculate incidence percentage if not provided
                    # Priority: 1) patients_affected_pct, 2) calculate from n/total, 3) None
                    incidence_pct = patients_affected_pct
                    if incidence_pct is None and patients_affected_n is not None and total_patients_n is not None and total_patients_n > 0:
                        incidence_pct = round((patients_affected_n / total_patients_n) * 100, 1)

                    safety_data.append({
                        'Disease': disease,
                        'PMID': pmid,
                        'Event Name': ep_dict.get('event_name'),
                        'Event Category': ep_dict.get('event_category'),
                        'Is Serious (SAE)': ep_dict.get('is_serious', False),
                        'Severity Grade': ep_dict.get('severity_grade'),
                        'Patients Affected (n)': patients_affected_n,
                        'Total Patients (n)': total_patients_n,
                        'Incidence (%)': incidence_pct,
                        'Related to Drug': ep_dict.get('relatedness'),
                        'Outcome': ep_dict.get('outcome'),
                        'Action Taken': ep_dict.get('action_taken'),
                        'Time to Onset': ep_dict.get('time_to_onset'),
                        'Notes': ep_dict.get('notes')
                    })

            if safety_data:
                pd.DataFrame(safety_data).to_excel(writer, sheet_name='Safety Endpoints', index=False)

        logger.info(f"Exported to Excel: {filepath}")

        # Generate visualizations if requested
        if generate_visualizations:
            try:
                viz_paths = self.generate_visualizations(result, filename)
                logger.info(f"Generated visualizations: {list(viz_paths.values())}")
            except Exception as e:
                logger.warning(f"Failed to generate visualizations (non-critical): {e}")

        # Generate text report if requested
        if generate_text_report:
            try:
                report_text, report_path = self.generate_analytical_report(
                    result=result,
                    auto_save=True,
                    max_tokens=16000  # Use full Claude Sonnet 4 output capacity
                )
                logger.info(f"Generated analytical report: {report_path}")
            except Exception as e:
                logger.warning(f"Failed to generate text report (non-critical): {e}")

        return str(filepath)

    def export_to_pdf(
        self,
        result: DrugAnalysisResult,
        filename: Optional[str] = None,
        include_rationale: bool = True
    ) -> str:
        """
        Export analysis result to PDF with LLM-generated scoring rationale.

        Args:
            result: DrugAnalysisResult to export
            filename: Optional filename (auto-generated if not provided)
            include_rationale: Whether to include LLM-generated rationale for each disease

        Returns:
            Path to generated PDF file
        """
        from src.reports.pdf_report_generator import PDFReportGenerator

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{result.drug_name.lower().replace(' ', '_')}_report_{timestamp}.pdf"

        filepath = self.output_dir / filename

        # Create PDF generator with our client for rationale generation
        pdf_generator = PDFReportGenerator(
            client=self.client if include_rationale else None,
            model=self.model
        )

        # Pass self as analysis_provider so PDF generator can use our
        # _analyze_efficacy_totality and _analyze_safety_totality methods
        output_path = pdf_generator.generate_report(
            result=result,
            output_path=str(filepath),
            include_rationale=include_rationale,
            analysis_provider=self if include_rationale else None
        )

        logger.info(f"Exported to PDF: {output_path}")
        return output_path

    def generate_analytical_report(
        self,
        result: DrugAnalysisResult = None,
        excel_path: str = None,
        output_path: str = None,
        max_tokens: int = 16000,  # Use full Claude Sonnet 4 output capacity
        auto_save: bool = True
    ) -> tuple[str, Optional[str]]:
        """
        Generate a comprehensive analytical report from case series analysis.

        This generates a detailed, objective analysis of the findings without making
        strategic recommendations. The report includes:
        - Score derivation with specific data citations
        - Concordance analysis across studies and endpoints
        - Cross-indication pattern analysis
        - Evidence quality assessment
        - Competitive landscape context

        Parameters:
        -----------
        result : DrugAnalysisResult, optional
            Analysis result object. If None, must provide excel_path.
        excel_path : str, optional
            Path to Excel file. If None, must provide result.
        output_path : str, optional
            Where to save the report. If None, saves to data/reports/
        max_tokens : int
            Maximum tokens for report generation (default: 8000)
        auto_save : bool
            Whether to automatically save the report to file (default: True)

        Returns:
        --------
        tuple[str, Optional[str]]
            (report_text, saved_path) where saved_path is None if auto_save=False

        Raises:
        -------
        ValueError
            If neither result nor excel_path is provided
        """
        try:
            logger.info("Generating analytical report...")

            # Create report generator
            report_gen = CaseSeriesReportGenerator(
                client=self.client,
                model=self.model
            )

            if auto_save:
                # Generate and save in one step
                report_text, saved_path = report_gen.generate_and_save_report(
                    excel_path=excel_path,
                    result=result,
                    output_path=output_path or (self.output_dir / 'reports'),
                    max_tokens=max_tokens
                )
                logger.info(f"Report generated and saved to: {saved_path}")
                return report_text, saved_path
            else:
                # Just generate, don't save
                if excel_path:
                    data = report_gen.format_data_from_excel(excel_path)
                elif result:
                    data = report_gen.format_data_from_result(result)
                else:
                    raise ValueError("Must provide either result or excel_path")

                report_text = report_gen.generate_report(data, max_tokens=max_tokens)
                logger.info(f"Report generated ({len(report_text)} characters)")
                return report_text, None

        except Exception as e:
            logger.error(f"Error generating analytical report: {e}", exc_info=True)
            raise

    # =========================================================================
    # GROUPING & ORGANIZATION
    # =========================================================================

    def group_papers_by_disease(
        self,
        papers: List[Dict[str, Any]],
        drug_name: str,
        drug_info: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group papers by the disease they address (for drug-only analysis).

        Uses Claude to identify the primary disease from each paper's title/abstract.
        Returns a dictionary: {disease_name: [paper1, paper2, ...]}
        """
        if not papers:
            return {}

        # Build papers list for template
        papers_list = []
        for i, paper in enumerate(papers, 1):
            papers_list.append({
                'num': i,
                'title': paper.get('title', 'Unknown'),
                'abstract': paper.get('abstract', '')[:300]
            })

        # Use Claude to classify papers by disease
        prompt = self._prompts.render(
            "case_series/classify_papers_by_disease",
            drug_name=drug_name,
            papers=papers_list
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            # Build grouped result
            grouped = {}
            classifications = data.get('classifications', [])

            for item in classifications:
                paper_num = item.get('paper_num', 0) - 1  # Convert to 0-indexed
                disease = item.get('disease', 'Unknown')

                if 0 <= paper_num < len(papers):
                    paper = papers[paper_num].copy()
                    paper['classified_disease'] = disease

                    if disease not in grouped:
                        grouped[disease] = []
                    grouped[disease].append(paper)

            # Add any unclassified papers
            classified_indices = {item.get('paper_num', 0) - 1 for item in classifications}
            for i, paper in enumerate(papers):
                if i not in classified_indices:
                    paper_copy = paper.copy()
                    paper_copy['classified_disease'] = 'Unknown'
                    if 'Unknown' not in grouped:
                        grouped['Unknown'] = []
                    grouped['Unknown'].append(paper_copy)

            logger.info(f"Grouped {len(papers)} papers into {len(grouped)} disease categories")
            return grouped

        except Exception as e:
            logger.error(f"Error grouping papers by disease: {e}")
            # Return ungrouped as fallback
            return {'All Papers': papers}

    def group_papers_by_disease_and_drug(
        self,
        papers: List[Dict[str, Any]],
        mechanism: str
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Group papers by disease first, then by drug within each disease (for mechanism analysis).

        Returns: {disease_name: {drug_name: [paper1, paper2, ...]}}
        """
        if not papers:
            return {}

        # Build papers list for template
        papers_list = []
        for i, paper in enumerate(papers, 1):
            papers_list.append({
                'num': i,
                'title': paper.get('title', 'Unknown'),
                'abstract': paper.get('abstract', '')[:300]
            })

        # Use Claude to classify papers by disease AND drug
        prompt = self._prompts.render(
            "case_series/classify_papers_by_disease_and_drug",
            mechanism=mechanism,
            papers=papers_list
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            # Build hierarchical grouped result
            grouped = {}
            classifications = data.get('classifications', [])

            for item in classifications:
                paper_num = item.get('paper_num', 0) - 1
                disease = item.get('disease', 'Unknown')
                drug = item.get('drug', 'Unknown')

                if 0 <= paper_num < len(papers):
                    paper = papers[paper_num].copy()
                    paper['classified_disease'] = disease
                    paper['classified_drug'] = drug

                    if disease not in grouped:
                        grouped[disease] = {}
                    if drug not in grouped[disease]:
                        grouped[disease][drug] = []
                    grouped[disease][drug].append(paper)

            # Add any unclassified papers
            classified_indices = {item.get('paper_num', 0) - 1 for item in classifications}
            for i, paper in enumerate(papers):
                if i not in classified_indices:
                    paper_copy = paper.copy()
                    paper_copy['classified_disease'] = 'Unknown'
                    paper_copy['classified_drug'] = 'Unknown'
                    if 'Unknown' not in grouped:
                        grouped['Unknown'] = {}
                    if 'Unknown' not in grouped['Unknown']:
                        grouped['Unknown']['Unknown'] = []
                    grouped['Unknown']['Unknown'].append(paper_copy)

            # Count for logging
            total_diseases = len(grouped)
            total_drugs = sum(len(drugs) for drugs in grouped.values())
            logger.info(f"Grouped {len(papers)} papers into {total_diseases} diseases and {total_drugs} drug groups")
            return grouped

        except Exception as e:
            logger.error(f"Error grouping papers by disease and drug: {e}")
            # Return ungrouped as fallback
            return {'All Papers': {'Unknown': papers}}

    def close(self):
        """Clean up resources."""
        if self.drug_db:
            try:
                self.drug_db.close()
            except Exception:
                pass

