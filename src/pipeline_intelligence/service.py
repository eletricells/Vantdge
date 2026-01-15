"""Pipeline Intelligence Service.

Extracts and tracks competitive landscape (pipeline and approved drugs) for diseases.
"""

import logging
import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .models import (
    PipelineDrug, CompetitiveLandscape, PipelineSource, PipelineRun,
    ClinicalTrial, TrialSearchResult
)
from .repository import PipelineIntelligenceRepository

# Import DrugProcessor for full drug extraction (optional dependency)
try:
    from src.drug_extraction_system.processors.drug_processor import DrugProcessor
    DRUG_PROCESSOR_AVAILABLE = True
except ImportError:
    DRUG_PROCESSOR_AVAILABLE = False

# Import MeSH client for disease term expansion (optional dependency)
try:
    from src.drug_extraction_system.api_clients.mesh_client import MeSHClient
    MESH_CLIENT_AVAILABLE = True
except ImportError:
    MESH_CLIENT_AVAILABLE = False

# Import shared disease term expansion
try:
    from src.shared.disease_terms import expand_disease_terms as shared_expand_disease_terms
    SHARED_DISEASE_TERMS_AVAILABLE = True
except ImportError:
    SHARED_DISEASE_TERMS_AVAILABLE = False

# Import PubChem client for drug deduplication
try:
    from src.drug_extraction_system.api_clients.pubchem_client import PubChemClient
    PUBCHEM_CLIENT_AVAILABLE = True
except ImportError:
    PUBCHEM_CLIENT_AVAILABLE = False

logger = logging.getLogger(__name__)

# Load Jinja2 templates
PROMPTS_DIR = Path(__file__).parent / "prompts"
jinja_env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

# NOTE: Hardcoded drug lists (KNOWN_PIPELINE_VALIDATION, INDICATION_APPROVED_DRUGS)
# have been removed in favor of dynamic discovery via:
# 1. MeSH API for disease term expansion
# 2. Web search + LLM + OpenFDA for approved drug discovery
# 3. Enhanced ClinicalTrials.gov search with disease synonyms


class PipelineIntelligenceService:
    """Service for extracting pipeline and competitive landscape data."""

    # Known drug aliases for FDA verification (internal codes to generic names)
    DRUG_ALIASES = {
        "hgs1006": "belimumab",
        "medi-545": "anifrolumab",
        "medi545": "anifrolumab",
        "bms-986165": "deucravacitinib",
        "cc-220": "iberdomide",
        "cfz533": "iscalimab",
        "vay736": "ianalumab",
    }

    def __init__(
        self,
        clinicaltrials_client,
        web_searcher,
        llm_client,
        repository: PipelineIntelligenceRepository,
        openfda_client=None
    ):
        """
        Initialize the service.

        Args:
            clinicaltrials_client: Client for ClinicalTrials.gov API
            web_searcher: Web search client (Tavily)
            llm_client: LLM client for extraction
            repository: Database repository
            openfda_client: Client for OpenFDA API (for approved drug verification)
        """
        self.ct_client = clinicaltrials_client
        self.web_searcher = web_searcher
        self.llm = llm_client
        self.repo = repository
        self.openfda = openfda_client
        # Cache staleness threshold (7 days)
        self.cache_stale_days = 7
        # Initialize MeSH client for disease term expansion
        self.mesh_client = MeSHClient() if MESH_CLIENT_AVAILABLE else None
        # Initialize PubChem client for drug deduplication
        self.pubchem_client = PubChemClient() if PUBCHEM_CLIENT_AVAILABLE else None

    async def _expand_disease_terms(self, disease_name: str) -> Dict[str, Any]:
        """
        Expand disease name to comprehensive search terms using MeSH.

        This now delegates to the shared disease_terms module for consistency
        with Disease Intelligence. Falls back to local implementation if
        the shared module is not available.

        Args:
            disease_name: Original disease name (e.g., "Sjogren's syndrome")

        Returns:
            {
                "mesh_id": "D012859" or None,
                "preferred_name": "Sjogren's Syndrome",
                "search_terms": ["sjogren's syndrome", "sjögren syndrome", ...]
            }
        """
        # Use shared implementation if available
        if SHARED_DISEASE_TERMS_AVAILABLE:
            try:
                result = shared_expand_disease_terms(disease_name, self.mesh_client)
                logger.info(f"Expanded '{disease_name}' to {len(result.search_terms)} search terms (shared)")
                return {
                    "mesh_id": result.mesh_id,
                    "preferred_name": result.preferred_name,
                    "search_terms": result.search_terms,
                }
            except Exception as e:
                logger.warning(f"Shared disease term expansion failed, using fallback: {e}")

        # Fallback to local implementation
        search_terms = set([disease_name.lower()])
        mesh_id = None
        preferred_name = disease_name

        # Try MeSH lookup with different name variations
        if self.mesh_client:
            # Get first word without apostrophes for fallback search
            first_word = disease_name.split()[0] if " " in disease_name else disease_name
            first_word_clean = first_word.replace("'s", "").replace("'s", "").replace("'", "")

            # Try original name first, then variations without apostrophes/special chars
            name_variations = [
                disease_name,
                disease_name.replace("'s", "s").replace("'s", "s"),  # Remove possessive
                disease_name.replace("'", "").replace("'", ""),  # Remove apostrophes
                first_word_clean,  # First word without apostrophes (e.g., "Sjogren" from "Sjogren's")
            ]

            for name_var in name_variations:
                try:
                    mesh_data = self.mesh_client.get_disease_search_terms(name_var)
                    if mesh_data and mesh_data.get("mesh_id"):
                        mesh_id = mesh_data.get("mesh_id")
                        preferred_name = mesh_data.get("preferred_name", disease_name)
                        for term in mesh_data.get("search_terms", []):
                            search_terms.add(term.lower())
                        logger.info(f"  MeSH match found via '{name_var}': {preferred_name} ({mesh_id})")
                        break
                except Exception as e:
                    logger.debug(f"MeSH lookup failed for '{name_var}': {e}")
                    continue

        # Add common variations programmatically
        for term in list(search_terms):
            # Handle apostrophe variations
            search_terms.add(term.replace("'s", "s"))
            search_terms.add(term.replace("'s", "'s"))
            search_terms.add(term.replace("'", ""))
            # Handle umlaut variations
            search_terms.add(term.replace("ö", "o"))
            search_terms.add(term.replace("ü", "u"))
            search_terms.add(term.replace("ä", "a"))

        # Remove empty strings and duplicates
        search_terms = [t for t in search_terms if t.strip()]

        logger.info(f"Expanded '{disease_name}' to {len(search_terms)} search terms (fallback)")

        return {
            "mesh_id": mesh_id,
            "preferred_name": preferred_name,
            "search_terms": list(search_terms),
        }

    async def _discover_approved_drugs_via_web(
        self,
        disease_name: str,
        search_terms: List[str]
    ) -> List[PipelineDrug]:
        """
        Discover FDA-approved drugs for indication via web search + LLM + OpenFDA verification.

        This replaces the hardcoded INDICATION_APPROVED_DRUGS dictionary.

        Args:
            disease_name: Disease name
            search_terms: Expanded search terms from MeSH

        Returns:
            List of verified approved drugs for this indication
        """
        if not self.web_searcher:
            logger.warning("Web searcher not available, skipping approved drug discovery")
            return []

        logger.info(f"Discovering FDA-approved drugs for {disease_name}...")

        # Build search queries
        queries = [
            f"{disease_name} FDA approved drugs treatments",
            f"{disease_name} approved therapies medications list",
            f"drugs approved for {disease_name} FDA label",
        ]

        # Add queries for top synonyms (avoid duplicates)
        for term in search_terms[:3]:
            if term.lower() != disease_name.lower():
                queries.append(f"{term} FDA approved treatments")

        # Collect web search results
        all_results = []
        for query in queries[:5]:  # Limit to 5 queries
            try:
                results = self.web_searcher.search(query, max_results=5)
                if results:
                    all_results.extend(results)
            except Exception as e:
                logger.warning(f"Web search failed for '{query}': {e}")

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        if not unique_results:
            logger.warning(f"No web results found for approved drugs")
            return []

        logger.info(f"  Found {len(unique_results)} web sources for approved drug discovery")

        # Extract candidates using LLM
        approved_candidates = await self._extract_approved_drug_candidates(
            disease_name, unique_results[:15]
        )

        if not approved_candidates:
            logger.info(f"  No approved drug candidates extracted from web")
            return []

        logger.info(f"  Extracted {len(approved_candidates)} approved drug candidates")

        # Verify each candidate with OpenFDA
        verified_drugs = []
        for candidate in approved_candidates:
            is_verified = await self._verify_drug_approval_openfda(
                candidate.generic_name, disease_name
            )
            if is_verified:
                candidate.approval_status = "approved"
                candidate.highest_phase = "Approved"
                if "FDA Approved (Web + OpenFDA verified)" not in candidate.data_sources:
                    candidate.data_sources.append("FDA Approved (Web + OpenFDA verified)")
                verified_drugs.append(candidate)
                logger.info(f"    Verified: {candidate.generic_name} is FDA-approved for {disease_name}")
            else:
                # Still include if confidence is high enough (OpenFDA may not have all indications)
                if candidate.confidence_score and candidate.confidence_score >= 0.8:
                    candidate.approval_status = "approved"
                    candidate.highest_phase = "Approved"
                    candidate.data_sources.append("FDA Approved (Web, high confidence)")
                    verified_drugs.append(candidate)
                    logger.info(f"    High-confidence: {candidate.generic_name} (OpenFDA verification unavailable)")
                else:
                    logger.debug(f"    Not verified: {candidate.generic_name}")

        logger.info(f"  Found {len(verified_drugs)} verified FDA-approved drugs for {disease_name}")
        return verified_drugs

    async def _extract_approved_drug_candidates(
        self,
        disease_name: str,
        web_results: List[Dict]
    ) -> List[PipelineDrug]:
        """
        Extract FDA-approved drug candidates from web search results using LLM.

        Uses a strict prompt that emphasizes:
        1. Only drugs with FDA approval for THIS EXACT indication
        2. Distinguish from related indications
        3. Focus on branded innovative drugs
        """
        if not web_results:
            return []

        try:
            template = jinja_env.get_template("extract_approved_drugs.j2")
            prompt = template.render(
                disease_name=disease_name,
                search_results=web_results
            )
        except Exception as e:
            logger.error(f"Failed to load extract_approved_drugs.j2 template: {e}")
            return []

        try:
            response = await self.llm.complete(prompt, max_tokens=2000)
            data = self._parse_json_response(response)

            if not data or "approved_drugs" not in data:
                return []

            drugs = []
            for d in data["approved_drugs"]:
                if not d.get("generic_name"):
                    continue

                # Skip low-confidence candidates
                confidence = d.get("confidence_score", 0.5)
                if confidence < 0.5:
                    continue

                drug = PipelineDrug(
                    generic_name=d["generic_name"],
                    brand_name=d.get("brand_name"),
                    manufacturer=d.get("manufacturer"),
                    drug_type=d.get("drug_type"),
                    mechanism_of_action=d.get("mechanism_of_action"),
                    approval_status="pending_verification",
                    highest_phase="Approved",
                    data_sources=["Web Search - Approved Candidates"],
                    confidence_score=confidence,
                )
                drugs.append(drug)

            return drugs

        except Exception as e:
            logger.error(f"Approved drug extraction failed: {e}")
            return []

    async def _verify_drug_approval_openfda(
        self,
        drug_name: str,
        indication: str
    ) -> bool:
        """
        Verify if a drug is FDA-approved for a specific indication using OpenFDA.

        Args:
            drug_name: Generic drug name
            indication: Disease/indication to verify

        Returns:
            True if verified approved for this indication
        """
        if not self.openfda:
            logger.debug("OpenFDA client not available, cannot verify approval")
            return False

        try:
            is_approved, indications_text, matched_terms = self.openfda.is_approved_for_indication(
                drug_name, indication
            )
            return is_approved
        except Exception as e:
            logger.warning(f"OpenFDA verification failed for {drug_name}: {e}")
            return False

    def _build_landscape_from_cache(
        self,
        disease_name: str,
        disease_id: int,
        disease_key: str,
        therapeutic_area: Optional[str] = None
    ) -> Optional[CompetitiveLandscape]:
        """Build a CompetitiveLandscape from cached database data."""
        try:
            # Get drugs from database
            cached_drugs = self.repo.get_pipeline_for_disease(disease_name)
            if not cached_drugs:
                return None

            # Build PipelineDrug objects from cached data
            approved_drugs = []
            phase3_drugs = []
            phase2_drugs = []
            phase1_drugs = []
            preclinical_drugs = []
            discontinued_drugs = []

            for drug_data in cached_drugs:
                drug = PipelineDrug(
                    generic_name=drug_data.get("generic_name", ""),
                    brand_name=drug_data.get("brand_name"),
                    manufacturer=drug_data.get("manufacturer"),
                    drug_type=drug_data.get("drug_type"),
                    mechanism_of_action=drug_data.get("mechanism_of_action"),
                    approval_status=drug_data.get("approval_status"),
                    highest_phase=drug_data.get("highest_phase"),
                    data_sources=["Cached"],
                )

                phase = drug_data.get("highest_phase", "").lower()
                status = drug_data.get("indication_status", "").lower()

                if status == "discontinued" or status == "failed":
                    discontinued_drugs.append(drug)
                elif phase == "approved":
                    approved_drugs.append(drug)
                elif phase == "phase 3":
                    phase3_drugs.append(drug)
                elif phase == "phase 2":
                    phase2_drugs.append(drug)
                elif phase == "phase 1":
                    phase1_drugs.append(drug)
                elif phase == "preclinical":
                    preclinical_drugs.append(drug)

            # Get latest run info for metadata
            latest_run = self.repo.get_latest_run(disease_id)

            landscape = CompetitiveLandscape(
                disease_name=disease_name,
                disease_key=disease_key,
                disease_id=disease_id,
                therapeutic_area=therapeutic_area,
                approved_drugs=approved_drugs,
                phase3_drugs=phase3_drugs,
                phase2_drugs=phase2_drugs,
                phase1_drugs=phase1_drugs,
                preclinical_drugs=preclinical_drugs,
                discontinued_drugs=discontinued_drugs,
                approved_count=len(approved_drugs),
                phase3_count=len(phase3_drugs),
                phase2_count=len(phase2_drugs),
                phase1_count=len(phase1_drugs),
                preclinical_count=len(preclinical_drugs),
                discontinued_count=len(discontinued_drugs),
                total_drugs=len(approved_drugs) + len(phase3_drugs) + len(phase2_drugs) + len(phase1_drugs) + len(preclinical_drugs),
                search_timestamp=latest_run.run_timestamp if latest_run else None,
                sources_searched=["ClinicalTrials.gov (cached)"],
                trials_reviewed=latest_run.clinicaltrials_searched if latest_run else 0,
            )

            return landscape

        except Exception as e:
            logger.warning(f"Failed to build landscape from cache: {e}")
            return None

    def _is_cache_valid(self, disease_id: int) -> bool:
        """Check if cached data is recent enough to use."""
        latest_run = self.repo.get_latest_run(disease_id)
        if not latest_run:
            return False

        if latest_run.status != "completed":
            return False

        # Check if run is within staleness threshold
        age = datetime.now() - latest_run.run_timestamp
        return age.days < self.cache_stale_days

    async def get_landscape(
        self,
        disease_name: str,
        therapeutic_area: Optional[str] = None,
        include_web_search: bool = True,
        force_refresh: bool = False,
        filter_related_conditions: bool = True,
        enrich_new_drugs: bool = False,
    ) -> CompetitiveLandscape:
        """
        Get complete competitive landscape for a disease.

        Args:
            disease_name: Name of the disease (e.g., "Systemic Lupus Erythematosus")
            therapeutic_area: Optional therapeutic area
            include_web_search: Whether to supplement with web search
            force_refresh: Force refresh even if recent data exists
            filter_related_conditions: Use LLM to filter out trials/drugs for related
                                       but distinct conditions (e.g., TED vs Graves Disease)
            enrich_new_drugs: If True, run new drugs through full DrugProcessor extraction
                             to get detailed MOA, targets, dosing, indications

        Returns:
            CompetitiveLandscape with all pipeline drugs
        """
        logger.info(f"Getting pipeline landscape for: {disease_name}")

        # Ensure disease exists in database (creates if needed)
        disease_record = self.repo.ensure_disease(disease_name, therapeutic_area)
        disease_id = disease_record["disease_id"]
        disease_key = disease_record.get("disease_key", "")

        # Check for cached data if not forcing refresh
        if not force_refresh and self._is_cache_valid(disease_id):
            logger.info(f"Using cached data for {disease_name} (cache is valid)")
            cached_landscape = self._build_landscape_from_cache(
                disease_name, disease_id, disease_key, therapeutic_area
            )
            if cached_landscape:
                return cached_landscape
            logger.info("Cache build failed, proceeding with fresh extraction")

        # Create pipeline run record
        run_id = self.repo.create_run(disease_id, disease_key, "full")

        try:
            # Step 1: Expand disease terms using MeSH (NEW - dynamic synonym discovery)
            logger.info("Step 1: Expanding disease terms with MeSH...")
            disease_terms = await self._expand_disease_terms(disease_name)
            search_terms = disease_terms.get("search_terms", [disease_name])
            logger.info(f"  Expanded to {len(search_terms)} search terms")

            # Step 2: Discover FDA-approved drugs via web search (NEW - replaces hardcoded list)
            approved_from_web = []
            if include_web_search and self.web_searcher:
                logger.info("Step 2: Discovering FDA-approved drugs via web search...")
                approved_from_web = await self._discover_approved_drugs_via_web(
                    disease_name, search_terms
                )
                logger.info(f"  Found {len(approved_from_web)} verified approved drugs")

            # Step 3: Search ClinicalTrials.gov (ENHANCED with synonyms)
            logger.info("Step 3: Searching ClinicalTrials.gov (industry-sponsored, with synonyms)...")
            trials = await self._search_clinical_trials(disease_name, search_terms)
            logger.info(f"  Found {len(trials)} industry-sponsored clinical trials")

            # Step 4: Extract drugs from trials (in batches to avoid JSON parsing issues)
            logger.info("Step 4: Extracting drugs from trials (batched)...")
            drugs_from_trials = await self._extract_drugs_from_trials_batched(disease_name, trials)
            logger.info(f"  Extracted {len(drugs_from_trials)} drugs from trials")

            # Step 5: Web search for active pipeline
            web_sources = []
            drugs_from_news = []
            discontinued_drugs = []
            if include_web_search and self.web_searcher:
                logger.info("Step 5: Searching web for active pipeline...")
                web_sources = await self._search_pipeline_news(disease_name)
                logger.info(f"  Found {len(web_sources)} web sources")

                if web_sources:
                    drugs_from_news = await self._extract_from_news(
                        disease_name, web_sources, drugs_from_trials
                    )
                    logger.info(f"  Extracted {len(drugs_from_news)} drugs from news")

                # Step 6: Search for discontinued/failed programs
                logger.info("Step 6: Searching for discontinued/failed programs...")
                discontinued_sources = await self._search_discontinued_programs(disease_name)
                logger.info(f"  Found {len(discontinued_sources)} discontinued program sources")

                if discontinued_sources:
                    discontinued_drugs = await self._extract_discontinued_drugs(
                        disease_name, discontinued_sources
                    )
                    logger.info(f"  Extracted {len(discontinued_drugs)} discontinued drugs")

            # Step 7: Merge all sources (trials + news + discontinued + approved from web)
            logger.info("Step 7: Merging and deduplicating...")
            all_drugs = self._merge_drugs(drugs_from_trials, drugs_from_news)
            all_drugs = self._merge_drugs(all_drugs, discontinued_drugs)
            all_drugs = self._merge_drugs(all_drugs, approved_from_web)  # Add approved drugs from web
            logger.info(f"  Total unique drugs: {len(all_drugs)}")

            # Step 7.5: Validate discontinuation status for each drug
            # Some drugs may have active trials for other indications but failed for this disease
            logger.info("Step 7.5: Validating discontinuation status per-drug...")
            all_drugs = await self._validate_discontinuation_status(disease_name, all_drugs)

            # Step 8: Filter out established/generic drugs (comparators, not novel pipeline)
            # BUT keep drugs that are already marked as approved for THIS indication
            established_drugs_to_filter = [
                d for d in all_drugs
                if self._is_established_drug(d.generic_name) and d.approval_status != "approved"
            ]
            if established_drugs_to_filter:
                established_names = [d.generic_name for d in established_drugs_to_filter]
                all_drugs = [
                    d for d in all_drugs
                    if not self._is_established_drug(d.generic_name) or d.approval_status == "approved"
                ]
                logger.info(f"  Filtered out {len(established_drugs_to_filter)} established/generic drugs: {established_names[:5]}...")
                logger.info(f"  Remaining pipeline drugs: {len(all_drugs)}")

            # Step 9: LLM-based filtering for related but distinct conditions
            if filter_related_conditions and len(all_drugs) > 0:
                logger.info("Step 9: Filtering drugs for related but distinct conditions...")
                all_drugs = await self._filter_related_conditions(disease_name, all_drugs)
                logger.info(f"  After filtering: {len(all_drugs)} drugs")

            # Step 10: Build landscape (include disease synonyms for sharing with Disease Intelligence)
            landscape = self._build_landscape(
                disease_name=disease_name,
                drugs=all_drugs,
                therapeutic_area=therapeutic_area,
                disease_synonyms=disease_terms.get("search_terms", []),
                mesh_id=disease_terms.get("mesh_id"),
            )
            landscape.trials_reviewed = len(trials)
            landscape.search_timestamp = datetime.now()
            landscape.sources_searched = ["ClinicalTrials.gov"]
            if include_web_search:
                landscape.sources_searched.append("Web Search")

            # Step 6: Store in database (if we have disease_id)
            if disease_id:
                await self._store_drugs(
                    all_drugs, disease_id, disease_name, therapeutic_area,
                    enrich_new_drugs=enrich_new_drugs
                )

            # Update run status
            if run_id:
                self.repo.update_run(
                    run_id=run_id,
                    status="completed",
                    clinicaltrials_searched=len(trials),
                    web_sources_searched=len(web_sources),
                    drugs_found_total=len(all_drugs),
                    drugs_new=len(all_drugs),  # For now, count all as new
                    drugs_updated=0
                )

            return landscape

        except Exception as e:
            logger.error(f"Pipeline extraction failed: {e}")
            if run_id:
                self.repo.update_run(run_id, status="failed", error_message=str(e))
            raise

    # Active trial statuses
    ACTIVE_TRIAL_STATUSES = [
        "RECRUITING",
        "NOT_YET_RECRUITING",
        "ACTIVE_NOT_RECRUITING",
        "ENROLLING_BY_INVITATION",
    ]

    # Inactive trial statuses that indicate discontinued programs
    INACTIVE_TRIAL_STATUSES = [
        "TERMINATED",
        "WITHDRAWN",
        "SUSPENDED",
    ]

    async def _search_clinical_trials(
        self,
        disease_name: str,
        search_terms: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Search ClinicalTrials.gov for INDUSTRY-SPONSORED trials related to the disease.

        Args:
            disease_name: Primary disease name
            search_terms: Optional list of synonym search terms from MeSH expansion

        Returns:
            Deduplicated list of clinical trials (by NCT ID)
        """
        # Build list of condition search terms
        conditions_to_search = [disease_name]
        if search_terms:
            # Add top synonyms (limit to 5 to avoid too many API calls)
            for term in search_terms[:5]:
                if term.lower() not in [c.lower() for c in conditions_to_search]:
                    conditions_to_search.append(term)

        logger.info(f"  Searching ClinicalTrials.gov with {len(conditions_to_search)} condition terms")

        # Use dict for deduplication by NCT ID
        all_trials = {}

        for condition in conditions_to_search:
            logger.info(f"    Searching: {condition}")

            # Search for active/recruiting industry-sponsored trials
            search_params = {
                "query.cond": condition,
                "pageSize": 100,
                "format": "json",
                "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY",
                "filter.overallStatus": ",".join(self.ACTIVE_TRIAL_STATUSES),
            }

            page_token = None
            condition_trials = 0

            while True:
                params = search_params.copy()
                if page_token:
                    params["pageToken"] = page_token

                result = self.ct_client.get("/studies", params=params)

                if not result or "studies" not in result:
                    break

                for study in result["studies"]:
                    nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                    if nct_id and nct_id not in all_trials:
                        all_trials[nct_id] = study
                        condition_trials += 1

                page_token = result.get("nextPageToken")
                if not page_token or condition_trials >= 100:  # Cap per condition
                    break

            # Search for completed Phase 3 trials (late-stage drugs)
            phase3_params = {
                "query.cond": condition,
                "pageSize": 30,
                "format": "json",
                "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY AND AREA[OverallStatus]COMPLETED",
                "sort": "CompletionDate:desc",
            }

            result = self.ct_client.get("/studies", params=phase3_params)
            if result and "studies" in result:
                for study in result["studies"]:
                    phases = study.get("protocolSection", {}).get("designModule", {}).get("phases", [])
                    if "PHASE3" in phases or "PHASE2/PHASE3" in phases:
                        nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                        if nct_id and nct_id not in all_trials:
                            all_trials[nct_id] = study

            # Search for recently completed trials (last 4 years)
            recent_params = {
                "query.cond": condition,
                "pageSize": 30,
                "format": "json",
                "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY",
                "filter.overallStatus": "COMPLETED",
                "sort": "CompletionDate:desc",
            }

            result = self.ct_client.get("/studies", params=recent_params)
            if result and "studies" in result:
                cutoff_year = str(datetime.now().year - 4)
                for study in result["studies"][:30]:
                    try:
                        completion_date = study.get("protocolSection", {}).get("statusModule", {}).get("completionDateStruct", {}).get("date", "")
                        if completion_date and completion_date >= cutoff_year:
                            nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
                            if nct_id and nct_id not in all_trials:
                                all_trials[nct_id] = study
                    except:
                        pass

        logger.info(f"  Found {len(all_trials)} unique trials across {len(conditions_to_search)} search terms")
        return list(all_trials.values())

    async def _filter_related_conditions(
        self,
        target_disease: str,
        drugs: List[PipelineDrug]
    ) -> List[PipelineDrug]:
        """
        Use LLM to filter out drugs that are for related but distinct conditions.

        This is a scalable approach that doesn't require hardcoded condition mappings.
        The LLM understands medical context and can distinguish between:
        - Graves Disease (hyperthyroidism) vs Thyroid Eye Disease
        - Rheumatoid Arthritis vs Psoriatic Arthritis
        - etc.

        Args:
            target_disease: The disease we're searching for
            drugs: List of extracted drugs to filter

        Returns:
            Filtered list with only drugs truly targeting the specified disease
        """
        if not drugs or not self.llm:
            return drugs

        # Fetch trial details for better context
        # This helps the LLM understand what indication each trial is actually studying
        trial_details_cache = {}
        for drug in drugs:
            for nct_id in (drug.source_nct_ids or [])[:2]:  # Limit to 2 trials per drug
                if nct_id and nct_id not in trial_details_cache:
                    try:
                        result = self.ct_client.get(f"/studies/{nct_id}")
                        if result:
                            ps = result.get("protocolSection", {})
                            conditions = ps.get("conditionsModule", {}).get("conditions", [])
                            brief_title = ps.get("identificationModule", {}).get("briefTitle", "")
                            description = ps.get("descriptionModule", {}).get("briefSummary", "")[:300]
                            trial_details_cache[nct_id] = {
                                "conditions": conditions,
                                "title": brief_title,
                                "description": description
                            }
                    except Exception:
                        pass

        # Build drug summary for LLM with trial context
        drug_summaries = []
        for i, drug in enumerate(drugs):
            # Get trial conditions for this drug
            trial_info = []
            for nct_id in (drug.source_nct_ids or [])[:2]:
                if nct_id in trial_details_cache:
                    details = trial_details_cache[nct_id]
                    trial_info.append({
                        "nct_id": nct_id,
                        "conditions": details["conditions"],
                        "title": details["title"][:100],
                        "description_snippet": details["description"][:200] if details["description"] else None
                    })

            summary = {
                "index": i,
                "drug_name": drug.brand_name or drug.generic_name,
                "generic_name": drug.generic_name,
                "manufacturer": drug.manufacturer,
                "moa": drug.mechanism_of_action,
                "target": drug.target,
                "phase": drug.highest_phase,
                "trials": trial_info,  # Now includes actual trial conditions and descriptions
            }
            drug_summaries.append(summary)

        # Create prompt for LLM
        prompt = f"""You are a medical expert helping to filter clinical pipeline data.

TARGET DISEASE: {target_disease}

I have a list of drugs that were found when searching for "{target_disease}". However, some of these drugs may actually be for RELATED BUT DISTINCT conditions, not the target disease itself.

Common examples of related but distinct conditions:
- "Graves Disease" (autoimmune hyperthyroidism) vs "Thyroid Eye Disease" / "Graves Ophthalmopathy" (eye manifestation)
- "Rheumatoid Arthritis" vs "Psoriatic Arthritis" vs "Osteoarthritis"
- "Crohn's Disease" vs "Ulcerative Colitis" (both IBD but distinct)
- "Type 1 Diabetes" vs "Type 2 Diabetes"
- "Systemic Lupus Erythematosus" vs "Lupus Nephritis" (subset, usually include)

DRUGS TO EVALUATE:
{json.dumps(drug_summaries, indent=2)}

IMPORTANT: Each drug includes its clinical trial details with:
- "conditions": The actual conditions being studied in the trial
- "title": The trial title
- "description_snippet": Brief trial description

USE THIS TRIAL INFORMATION to determine the true indication. Trial conditions and descriptions are more reliable than just the drug name.

For each drug, determine if it is TRULY being developed for "{target_disease}" or if it's actually for a related but distinct condition.

Return a JSON object with:
{{
  "target_disease_clarification": "<brief clarification of what the target disease IS vs related conditions>",
  "drugs_to_keep": [<list of drug indices (integers) that ARE for the target disease>],
  "drugs_to_exclude": [
    {{"index": <int>, "drug_name": "<name>", "actual_condition": "<what condition it's actually for based on trial info>", "reason": "<brief reason citing trial conditions/description>"}}
  ]
}}

Rules:
- PRIORITIZE trial conditions and descriptions over just drug name/MOA
- If trial conditions explicitly list a DIFFERENT indication (e.g., "Thyroid Eye Disease" when target is "Graves Disease"), EXCLUDE it
- If trial description mentions endpoints for a different condition (e.g., proptosis, eye symptoms for TED), EXCLUDE it
- If a drug is for a SUBSET of the target disease (e.g., Lupus Nephritis within SLE), KEEP it
- If a drug is for a DISTINCT related condition (different ICD code, different treatment paradigm), EXCLUDE it
- Consider the mechanism of action in context of the trial's stated goals

Return ONLY valid JSON, no other text."""

        try:
            response = await self.llm.complete(prompt, model="claude-sonnet-4-20250514", max_tokens=2000)

            # Parse response
            result = self._parse_json_response(response)
            if not result:
                logger.warning("Failed to parse LLM filtering response, keeping all drugs")
                return drugs

            drugs_to_keep_indices = set(result.get("drugs_to_keep", range(len(drugs))))
            drugs_to_exclude = result.get("drugs_to_exclude", [])

            if drugs_to_exclude:
                for excluded in drugs_to_exclude:
                    logger.info(f"  Excluding {excluded.get('drug_name')}: {excluded.get('actual_condition')} ({excluded.get('reason')})")

            # Filter drugs
            filtered_drugs = [drug for i, drug in enumerate(drugs) if i in drugs_to_keep_indices]

            if len(filtered_drugs) < len(drugs):
                logger.info(f"  Filtered out {len(drugs) - len(filtered_drugs)} drugs for related conditions")

            return filtered_drugs

        except Exception as e:
            logger.warning(f"LLM filtering failed: {e}, keeping all drugs")
            return drugs

    async def _extract_drugs_from_trials_batched(
        self,
        disease_name: str,
        trials: List[Dict]
    ) -> List[PipelineDrug]:
        """Extract drugs from trials in batches to avoid JSON parsing failures."""
        if not trials:
            return []

        # Parse trial data into structured format
        parsed_trials = []
        for study in trials:
            try:
                trial_data = self.ct_client.extract_trial_data(study)
                trial_status = trial_data.get("trial_status", "UNKNOWN")
                parsed_trials.append({
                    "nct_id": trial_data.get("nct_id"),
                    "title": trial_data.get("trial_title"),
                    "phase": trial_data.get("trial_phase"),
                    "status": trial_status,
                    "is_active": trial_status in self.ACTIVE_TRIAL_STATUSES,
                    "is_completed": trial_status == "COMPLETED",
                    "sponsor": trial_data.get("sponsors", {}).get("lead"),
                    "interventions": [
                        i.get("name", "") for i in trial_data.get("interventions", [])
                        if i.get("type") in ["DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT"]
                    ],
                    "conditions": trial_data.get("conditions", []),
                    "start_date": trial_data.get("start_date"),
                    "completion_date": trial_data.get("completion_date"),
                    "enrollment": trial_data.get("enrollment"),
                })
            except Exception as e:
                logger.warning(f"Failed to parse trial: {e}")
                continue

        if not parsed_trials:
            return []

        # Process in batches of 15 trials (smaller to avoid truncated JSON)
        BATCH_SIZE = 15
        all_drugs = []

        for i in range(0, len(parsed_trials), BATCH_SIZE):
            batch = parsed_trials[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            total_batches = (len(parsed_trials) + BATCH_SIZE - 1) // BATCH_SIZE
            logger.info(f"    Processing batch {batch_num}/{total_batches} ({len(batch)} trials)")

            try:
                template = jinja_env.get_template("extract_pipeline_drugs.j2")
                prompt = template.render(
                    disease_name=disease_name,
                    trials=batch,
                    web_sources=[]
                )

                response = await self.llm.complete(prompt)
                drugs_data = self._parse_json_response(response)

                if not drugs_data or "drugs" not in drugs_data:
                    logger.warning(f"    No drugs extracted from batch {batch_num}")
                    continue

                for d in drugs_data["drugs"]:
                    if not d.get("generic_name"):
                        continue

                    drug = PipelineDrug(
                        generic_name=d["generic_name"],
                        brand_name=d.get("brand_name"),
                        manufacturer=d.get("manufacturer"),
                        drug_type=d.get("drug_type"),
                        mechanism_of_action=d.get("mechanism_of_action"),
                        target=d.get("target"),
                        modality=d.get("modality"),
                        highest_phase=d.get("highest_phase"),
                        source_nct_ids=d.get("trial_nct_ids", []),
                        lead_trial_nct=d.get("lead_trial_nct"),
                        efficacy_summary=d.get("efficacy_summary"),
                        dosing_summary=d.get("dosing_info"),
                        confidence_score=d.get("confidence_score", 0.5),
                        data_sources=["ClinicalTrials.gov"],
                        last_updated=datetime.now()
                    )

                    # Add trial info
                    if d.get("lead_trial_nct"):
                        drug.trials.append(ClinicalTrial(
                            nct_id=d["lead_trial_nct"],
                            phase=d.get("highest_phase"),
                            status=d.get("trial_status"),
                            enrollment=d.get("enrollment"),
                            primary_endpoint=d.get("primary_endpoint")
                        ))

                    all_drugs.append(drug)

            except Exception as e:
                logger.error(f"    Batch {batch_num} extraction failed: {e}")
                continue

        return all_drugs

    def _get_year_range(self, years_back: int = 1, years_forward: int = 2) -> str:
        """Generate dynamic year range string for searches.

        Args:
            years_back: Number of years to look back from current year
            years_forward: Number of years to look forward from current year

        Returns:
            Space-separated year string, e.g., "2025 2026 2027 2028"
        """
        current_year = datetime.now().year
        years = range(current_year - years_back, current_year + years_forward + 1)
        return " ".join(str(y) for y in years)

    async def _search_discontinued_programs(self, disease_name: str) -> List[Dict]:
        """Search web for discontinued/failed drug programs."""
        if not self.web_searcher:
            return []

        # Dynamic year range: last 5 years
        recent_years = self._get_year_range(years_back=5, years_forward=0)

        queries = [
            f"{disease_name} drug discontinued development",
            f"{disease_name} clinical trial failure terminated",
            f"{disease_name} drug program halted stopped",
            f"{disease_name} phase 3 failure",
            f"{disease_name} drug development terminated {recent_years}",
        ]

        all_results = []
        for query in queries:
            try:
                results = self.web_searcher.search(query, max_results=5)
                if results:
                    all_results.extend(results)
            except Exception as e:
                logger.warning(f"Web search failed for '{query}': {e}")

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        return unique_results[:15]

    async def _extract_discontinued_drugs(
        self,
        disease_name: str,
        web_sources: List[Dict]
    ) -> List[PipelineDrug]:
        """Extract discontinued/failed drugs from web search results."""
        if not web_sources:
            return []

        template = jinja_env.get_template("extract_discontinued.j2")
        prompt = template.render(
            disease_name=disease_name,
            search_results=web_sources
        )

        try:
            response = await self.llm.complete(prompt)
            data = self._parse_json_response(response)

            if not data or "discontinued_drugs" not in data:
                return []

            drugs = []
            for d in data["discontinued_drugs"]:
                if not d.get("generic_name"):
                    continue

                drug = PipelineDrug(
                    generic_name=d["generic_name"],
                    brand_name=d.get("brand_name"),
                    manufacturer=d.get("manufacturer"),
                    mechanism_of_action=d.get("mechanism_of_action"),
                    highest_phase=d.get("highest_phase_reached"),
                    # Mark as discontinued
                    development_status=d.get("development_status", "discontinued"),
                    discontinuation_date=d.get("discontinuation_date"),
                    discontinuation_reason=d.get("discontinuation_reason"),
                    failure_stage=d.get("highest_phase_reached"),
                    # Sources
                    source_urls=[d.get("source_url")] if d.get("source_url") else [],
                    data_sources=["Web Search - Discontinued"],
                    confidence_score=d.get("confidence_score", 0.6),
                    last_updated=datetime.now()
                )
                drugs.append(drug)

            return drugs

        except Exception as e:
            logger.error(f"Discontinued drug extraction failed: {e}")
            return []

    async def _validate_discontinuation_status(
        self,
        disease_name: str,
        drugs: List[PipelineDrug],
        max_drugs_to_check: int = 30
    ) -> List[PipelineDrug]:
        """
        Validate discontinuation status for each drug specifically for this indication.

        Some drugs may have active trials for other indications but failed for this
        specific disease. This method checks each drug individually.

        Args:
            disease_name: The disease to check discontinuation for
            drugs: List of drugs to validate
            max_drugs_to_check: Maximum number of drugs to validate (rate limiting)

        Returns:
            Updated list of drugs with corrected discontinuation status
        """
        if not self.web_searcher or not drugs:
            return drugs

        # Only check drugs not already marked as discontinued
        drugs_to_check = [
            d for d in drugs
            if d.development_status not in ["discontinued", "failed", "terminated"]
            and d.approval_status != "approved"  # Don't check approved drugs
        ][:max_drugs_to_check]

        if not drugs_to_check:
            return drugs

        logger.info(f"Validating discontinuation status for {len(drugs_to_check)} drugs...")

        # Batch the drug names for a single LLM call instead of per-drug web searches
        drug_names = [d.generic_name for d in drugs_to_check]

        # Do a focused web search for discontinuation info
        query = f"{disease_name} drug discontinued failed {' OR '.join(drug_names[:10])}"
        try:
            search_results = self.web_searcher.search(query, max_results=10)
        except Exception as e:
            logger.warning(f"Web search for discontinuation validation failed: {e}")
            return drugs

        if not search_results:
            return drugs

        # Use LLM to check which drugs failed for this indication
        prompt = f"""Analyze these search results about {disease_name} drug development.

For each of these drugs, determine if it has FAILED or been DISCONTINUED specifically for {disease_name}:
{', '.join(drug_names)}

Search results:
{json.dumps(search_results[:10], indent=2)}

Return JSON with ONLY drugs that have failed/discontinued for {disease_name}:
{{
  "failed_drugs": [
    {{
      "generic_name": "drug name",
      "failure_reason": "brief reason (e.g., 'Phase 3 failed to meet primary endpoint')",
      "discontinuation_date": "YYYY-MM or YYYY if known",
      "failure_stage": "Phase 2, Phase 3, etc."
    }}
  ]
}}

IMPORTANT:
- Only include drugs that SPECIFICALLY failed for {disease_name}
- A drug active for other diseases but failed for {disease_name} should be included
- Do NOT include drugs that are still in active development for {disease_name}
- Return empty list if no drugs failed for {disease_name}
"""

        try:
            response = await self.llm.complete(prompt)
            data = self._parse_json_response(response)

            if not data or "failed_drugs" not in data:
                return drugs

            # Create a lookup for failed drugs
            failed_lookup = {
                d["generic_name"].lower(): d
                for d in data["failed_drugs"]
                if d.get("generic_name")
            }

            if failed_lookup:
                logger.info(f"Found {len(failed_lookup)} drugs that failed for {disease_name}: {list(failed_lookup.keys())}")

            # Update drug statuses
            for drug in drugs:
                drug_key = drug.generic_name.lower()
                if drug_key in failed_lookup:
                    failure_info = failed_lookup[drug_key]
                    drug.development_status = "discontinued"
                    drug.discontinuation_reason = failure_info.get("failure_reason")
                    drug.discontinuation_date = failure_info.get("discontinuation_date")
                    drug.failure_stage = failure_info.get("failure_stage")
                    logger.info(f"  Marked '{drug.generic_name}' as discontinued for {disease_name}: {failure_info.get('failure_reason')}")

        except Exception as e:
            logger.error(f"Discontinuation validation failed: {e}")

        return drugs

    async def _extract_drugs_from_trials(
        self,
        disease_name: str,
        trials: List[Dict]
    ) -> List[PipelineDrug]:
        """Extract drug information from clinical trials using LLM."""
        if not trials:
            return []

        # Parse trial data into structured format
        parsed_trials = []
        for study in trials:
            try:
                trial_data = self.ct_client.extract_trial_data(study)
                parsed_trials.append({
                    "nct_id": trial_data.get("nct_id"),
                    "title": trial_data.get("trial_title"),
                    "phase": trial_data.get("trial_phase"),
                    "status": trial_data.get("trial_status"),
                    "sponsor": trial_data.get("sponsors", {}).get("lead"),
                    "interventions": [
                        i.get("name", "") for i in trial_data.get("interventions", [])
                        if i.get("type") in ["DRUG", "BIOLOGICAL", "COMBINATION_PRODUCT"]
                    ],
                    "conditions": trial_data.get("conditions", []),
                    "start_date": trial_data.get("start_date"),
                    "completion_date": trial_data.get("completion_date"),
                    "enrollment": trial_data.get("enrollment"),
                })
            except Exception as e:
                logger.warning(f"Failed to parse trial: {e}")
                continue

        if not parsed_trials:
            return []

        # Use LLM to extract drugs
        template = jinja_env.get_template("extract_pipeline_drugs.j2")
        prompt = template.render(
            disease_name=disease_name,
            trials=parsed_trials[:50],  # Limit to 50 trials per prompt
            web_sources=[]
        )

        try:
            response = await self.llm.complete(prompt)
            drugs_data = self._parse_json_response(response)

            if not drugs_data or "drugs" not in drugs_data:
                logger.warning("No drugs extracted from trials")
                return []

            drugs = []
            for d in drugs_data["drugs"]:
                if not d.get("generic_name"):
                    continue

                drug = PipelineDrug(
                    generic_name=d["generic_name"],
                    brand_name=d.get("brand_name"),
                    manufacturer=d.get("manufacturer"),
                    drug_type=d.get("drug_type"),
                    mechanism_of_action=d.get("mechanism_of_action"),
                    target=d.get("target"),
                    modality=d.get("modality"),
                    highest_phase=d.get("highest_phase"),
                    source_nct_ids=d.get("trial_nct_ids", []),
                    lead_trial_nct=d.get("lead_trial_nct"),
                    efficacy_summary=d.get("efficacy_summary"),
                    dosing_summary=d.get("dosing_info"),
                    confidence_score=d.get("confidence_score", 0.5),
                    data_sources=["ClinicalTrials.gov"],
                    last_updated=datetime.now()
                )

                # Add trial info
                if d.get("lead_trial_nct"):
                    drug.trials.append(ClinicalTrial(
                        nct_id=d["lead_trial_nct"],
                        phase=d.get("highest_phase"),
                        status=d.get("trial_status"),
                        enrollment=d.get("enrollment"),
                        primary_endpoint=d.get("primary_endpoint")
                    ))

                drugs.append(drug)

            return drugs

        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return []

    async def _search_pipeline_news(self, disease_name: str) -> List[Dict]:
        """Search web for recent pipeline news."""
        if not self.web_searcher:
            return []

        # Dynamic year range: last 1 year to 2 years forward
        pipeline_years = self._get_year_range(years_back=1, years_forward=2)

        queries = [
            f"{disease_name} pipeline drugs {pipeline_years}",
            f"{disease_name} clinical trial results",
            f"{disease_name} FDA approval drug",
            f"{disease_name} phase 3 trial results",
            # Regulatory filing searches - critical for capturing late-stage progress
            f"{disease_name} NDA filing FDA submission {pipeline_years}",
            f"{disease_name} phase 3 positive results regulatory",
            f"{disease_name} drug approval breakthrough therapy",
        ]

        all_results = []
        for query in queries:
            try:
                # Web searcher is synchronous
                results = self.web_searcher.search(query, max_results=5)
                if results:
                    all_results.extend(results)
            except Exception as e:
                logger.warning(f"Web search failed for '{query}': {e}")

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(r)

        return unique_results[:20]  # Limit to 20 results

    async def _extract_from_news(
        self,
        disease_name: str,
        web_sources: List[Dict],
        known_drugs: List[PipelineDrug]
    ) -> List[PipelineDrug]:
        """Extract pipeline updates from news sources."""
        if not web_sources:
            return []

        template = jinja_env.get_template("extract_pipeline_news.j2")
        prompt = template.render(
            disease_name=disease_name,
            search_results=web_sources,
            known_drugs=[
                {"generic_name": d.generic_name, "manufacturer": d.manufacturer, "highest_phase": d.highest_phase}
                for d in known_drugs
            ]
        )

        try:
            response = await self.llm.complete(prompt)
            news_data = self._parse_json_response(response)

            if not news_data:
                return []

            # Phase ranking for comparison (lower number = more advanced)
            phase_rank = {
                "Approved": 1, "NDA Filed": 2, "NDA Planned": 2.5, "Phase 3": 3, "Phase 2/3": 3,
                "Phase 2": 4, "Phase 1/2": 4, "Phase 1": 5, "Preclinical": 6
            }

            # Create drugs from updates
            drugs = []
            for update in news_data.get("updates", []):
                drug_name = update.get("drug_name", "").lower()
                # Find matching known drug
                matching_drug = next(
                    (d for d in known_drugs if d.generic_name.lower() == drug_name or
                     (d.brand_name and d.brand_name.lower() == drug_name)),
                    None
                )

                if matching_drug:
                    # Update existing drug
                    if update.get("efficacy_data"):
                        matching_drug.efficacy_summary = update["efficacy_data"]
                    if update.get("recent_milestone") or update.get("headline"):
                        matching_drug.recent_milestone = update.get("headline") or update.get("recent_milestone")
                    if update.get("source_url"):
                        matching_drug.source_urls.append(update["source_url"])
                    matching_drug.data_sources.append("Web Search")

                    # CRITICAL: Update phase if news indicates advancement
                    news_phase = update.get("phase_mentioned")
                    update_type = update.get("update_type", "")

                    # Check for regulatory filing - indicates NDA/BLA submitted
                    if update_type == "regulatory_filing":
                        news_phase = "NDA Filed"
                        logger.info(f"  News: {matching_drug.generic_name} has regulatory filing - updating to NDA Filed")
                    # Check for NDA planned - positive Phase 3, planning to file
                    elif update_type in ("nda_planned", "positive_phase3"):
                        news_phase = "NDA Planned"
                        logger.info(f"  News: {matching_drug.generic_name} has {update_type} - updating to NDA Planned")

                    # Update phase if news indicates more advanced phase
                    if news_phase:
                        current_rank = phase_rank.get(matching_drug.highest_phase, 10)
                        news_rank = phase_rank.get(news_phase, 10)

                        if news_rank < current_rank:
                            logger.info(f"  News update: {matching_drug.generic_name} phase {matching_drug.highest_phase} -> {news_phase}")
                            matching_drug.highest_phase = news_phase
                            matching_drug.data_sources.append("News (Phase Update)")

            # Add newly discovered drugs
            for new_drug in news_data.get("new_drugs_discovered", []):
                if new_drug.get("generic_name"):
                    drugs.append(PipelineDrug(
                        generic_name=new_drug["generic_name"],
                        manufacturer=new_drug.get("manufacturer"),
                        mechanism_of_action=new_drug.get("mechanism_of_action"),
                        highest_phase=new_drug.get("phase"),
                        data_sources=["Web Search"],
                        confidence_score=0.6
                    ))

            return drugs

        except Exception as e:
            logger.error(f"News extraction failed: {e}")
            return []

    def _resolve_drug_via_pubchem(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Resolve drug name via PubChem for deduplication.

        Returns dict with 'cid' and 'generic_name' if found, None on failure.
        Graceful degradation - returns None if PubChem unavailable or lookup fails.
        """
        if not self.pubchem_client:
            return None

        try:
            compound = self.pubchem_client.search_by_name(name)
            if compound:
                generic_name = self.pubchem_client.find_generic_name(name)
                return {
                    'cid': compound.cid,
                    'generic_name': generic_name
                }
        except Exception as e:
            logger.debug(f"PubChem lookup failed for {name}: {e}")
        return None

    # Phase ranking for comparison (lower number = more advanced)
    PHASE_RANK = {
        "Approved": 1, "NDA Filed": 2, "NDA Planned": 2.5, "Phase 3": 3, "Phase 2/3": 3,
        "Phase 2": 4, "Phase 1/2": 4, "Phase 1": 5, "Preclinical": 6
    }

    def _merge_drugs(
        self,
        trials_drugs: List[PipelineDrug],
        news_drugs: List[PipelineDrug]
    ) -> List[PipelineDrug]:
        """Merge and deduplicate drugs from different sources.

        Uses both generic_name and PubChem CID for deduplication to catch
        cases like 'PF-06823859' and 'dazukibart' being the same compound.
        """
        # Maps for deduplication
        drug_map: Dict[str, PipelineDrug] = {}  # canonical_name → drug
        cid_map: Dict[int, str] = {}  # pubchem_cid → canonical_name

        def get_canonical_key(drug: PipelineDrug) -> str:
            """Get canonical key for drug, using PubChem when available."""
            # Try to resolve via PubChem
            pubchem_info = self._resolve_drug_via_pubchem(drug.generic_name)

            if pubchem_info and pubchem_info.get('cid'):
                cid = pubchem_info['cid']
                drug.pubchem_cid = cid  # Store for later use

                # Check if this CID was already seen
                if cid in cid_map:
                    existing_key = cid_map[cid]
                    if existing_key != drug.generic_name.lower():
                        logger.info(f"  PubChem dedup: '{drug.generic_name}' matches '{existing_key}' (CID: {cid})")
                    return existing_key

                # Use PubChem generic name if available, otherwise original name
                canonical = pubchem_info.get('generic_name') or drug.generic_name.lower()
                cid_map[cid] = canonical
                return canonical

            # Fallback to original name if PubChem unavailable
            return drug.generic_name.lower()

        def merge_into_existing(existing: PipelineDrug, incoming: PipelineDrug):
            """Merge incoming drug data into existing entry."""
            # Merge NCT IDs and URLs
            existing.source_nct_ids.extend(incoming.source_nct_ids)
            existing.source_urls.extend(incoming.source_urls)
            existing.data_sources = list(set(existing.data_sources + incoming.data_sources))

            # Update phase if incoming is more advanced
            existing_rank = self.PHASE_RANK.get(existing.highest_phase, 10)
            incoming_rank = self.PHASE_RANK.get(incoming.highest_phase, 10)
            if incoming_rank < existing_rank:
                logger.info(f"  Merge: Upgrading {existing.generic_name} from {existing.highest_phase} to {incoming.highest_phase}")
                existing.highest_phase = incoming.highest_phase

            # Copy milestone/efficacy if not present
            if incoming.recent_milestone and not existing.recent_milestone:
                existing.recent_milestone = incoming.recent_milestone
            if incoming.efficacy_summary and not existing.efficacy_summary:
                existing.efficacy_summary = incoming.efficacy_summary

            # Handle discontinuation status
            if incoming.development_status in ["discontinued", "failed", "terminated", "on_hold"]:
                existing.development_status = incoming.development_status
                if incoming.discontinuation_date:
                    existing.discontinuation_date = incoming.discontinuation_date
                if incoming.discontinuation_reason:
                    existing.discontinuation_reason = incoming.discontinuation_reason
                if incoming.failure_stage:
                    existing.failure_stage = incoming.failure_stage

            # Preserve PubChem CID if incoming has it
            if incoming.pubchem_cid and not existing.pubchem_cid:
                existing.pubchem_cid = incoming.pubchem_cid

        # Process all drugs (trials first, then news)
        for drug in trials_drugs + news_drugs:
            key = get_canonical_key(drug)

            if key in drug_map:
                merge_into_existing(drug_map[key], drug)
            else:
                drug_map[key] = drug

        return list(drug_map.values())

    # Established/generic drugs commonly used as comparators in trials
    # These are not novel pipeline drugs and should skip full extraction
    ESTABLISHED_DRUGS = {
        # Immunosuppressants
        "mycophenolate mofetil", "mycophenolate", "azathioprine", "methotrexate",
        "cyclosporine", "tacrolimus", "sirolimus", "everolimus",
        # Corticosteroids
        "prednisone", "prednisolone", "methylprednisolone", "dexamethasone",
        "hydrocortisone", "budesonide", "triamcinolone",
        # NSAIDs
        "ibuprofen", "naproxen", "celecoxib", "diclofenac", "indomethacin",
        # Common DMARDs
        "hydroxychloroquine", "sulfasalazine", "leflunomide",
        # Common biologics (established)
        "rituximab", "infliximab", "adalimumab", "etanercept",
        # Chemotherapy agents
        "cyclophosphamide", "chlorambucil", "vincristine", "doxorubicin",
        # Other common generics
        "aspirin", "acetaminophen", "gabapentin", "pregabalin",
        "omeprazole", "pantoprazole", "atorvastatin", "metformin",
    }

    def _is_established_drug(self, drug_name: str) -> bool:
        """
        Check if a drug is an established/generic drug.

        Established drugs are well-known generics commonly used as comparators
        in clinical trials. We skip full extraction for these since they're
        not the novel pipeline drugs we're interested in.
        """
        if not drug_name:
            return False

        name_lower = drug_name.lower().strip()

        # Check against known established drugs
        if name_lower in self.ESTABLISHED_DRUGS:
            return True

        # Check if any established drug is contained in the name
        for established in self.ESTABLISHED_DRUGS:
            if established in name_lower:
                return True

        return False

    def _normalize_phase(self, phase: str) -> str:
        """Normalize phase to valid database values."""
        if not phase:
            return "Preclinical"

        phase_lower = phase.lower()

        # Map to valid values: Phase 1, Phase 2, Phase 3, Approved, Discontinued, Preclinical
        # Check most specific patterns first to avoid false matches
        if "approved" in phase_lower or "market" in phase_lower:
            return "Approved"
        # NDA/BLA stages are late-stage (effectively Phase 3 equivalent)
        elif "nda" in phase_lower or "bla" in phase_lower or "regulatory" in phase_lower:
            return "Phase 3"
        # Phase matching - use word boundaries to avoid "i" in "filed" matching phase 1
        elif "phase 3" in phase_lower or "phase3" in phase_lower or " iii" in phase_lower or phase_lower == "iii":
            return "Phase 3"
        elif "phase 2" in phase_lower or "phase2" in phase_lower or " ii" in phase_lower or phase_lower == "ii":
            return "Phase 2"
        elif "phase 1" in phase_lower or "phase1" in phase_lower or " i" in phase_lower or phase_lower == "i":
            return "Phase 1"
        elif "discontinued" in phase_lower or "terminated" in phase_lower:
            return "Discontinued"
        elif "preclinical" in phase_lower or "pre-clinical" in phase_lower:
            return "Preclinical"
        else:
            return "Preclinical"  # Default

    def _build_landscape(
        self,
        disease_name: str,
        drugs: List[PipelineDrug],
        therapeutic_area: Optional[str] = None,
        disease_synonyms: Optional[List[str]] = None,
        mesh_id: Optional[str] = None,
    ) -> CompetitiveLandscape:
        """Build competitive landscape from drugs."""
        landscape = CompetitiveLandscape(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area,
            disease_synonyms=disease_synonyms or [],
            mesh_id=mesh_id,
        )

        # Normalize phases and categorize
        for drug in drugs:
            drug.highest_phase = self._normalize_phase(drug.highest_phase)

        # Categorize by phase (but separate discontinued drugs first)
        for drug in drugs:
            # Check if this is a discontinued/failed drug
            if drug.development_status in ["discontinued", "failed", "terminated", "on_hold"]:
                landscape.discontinued_drugs.append(drug)
                continue

            phase = (drug.highest_phase or "").lower()
            if "approved" in phase:
                drug.approval_status = "approved"
                landscape.approved_drugs.append(drug)
            elif "phase 3" in phase or "phase3" in phase:
                landscape.phase3_drugs.append(drug)
            elif "phase 2" in phase or "phase2" in phase:
                landscape.phase2_drugs.append(drug)
            elif "phase 1" in phase or "phase1" in phase:
                landscape.phase1_drugs.append(drug)
            elif "discontinued" in phase:
                # Catch any that were marked with phase = "Discontinued"
                drug.development_status = "discontinued"
                landscape.discontinued_drugs.append(drug)
            else:
                landscape.preclinical_drugs.append(drug)

        # Sort each category by manufacturer
        for drug_list in [
            landscape.approved_drugs,
            landscape.phase3_drugs,
            landscape.phase2_drugs,
            landscape.phase1_drugs,
            landscape.preclinical_drugs
        ]:
            drug_list.sort(key=lambda d: d.manufacturer or "ZZZ")

        # Sort discontinued by discontinuation date (most recent first)
        landscape.discontinued_drugs.sort(
            key=lambda d: d.discontinuation_date or "0000",
            reverse=True
        )

        landscape.update_counts()
        landscape.discontinued_count = len(landscape.discontinued_drugs)

        # Extract key MOA classes (from active drugs only)
        moa_classes = set()
        active_drugs = (
            landscape.approved_drugs +
            landscape.phase3_drugs +
            landscape.phase2_drugs +
            landscape.phase1_drugs
        )
        for drug in active_drugs:
            if drug.target:
                moa_classes.add(drug.target)
            elif drug.mechanism_of_action:
                # Extract target from MOA (e.g., "IL-17A inhibitor" -> "IL-17A")
                moa = drug.mechanism_of_action
                if "inhibitor" in moa.lower():
                    target = moa.lower().replace("inhibitor", "").strip()
                    moa_classes.add(target.upper())

        landscape.key_moa_classes = list(moa_classes)[:10]

        return landscape

    async def _store_drugs(
        self,
        drugs: List[PipelineDrug],
        disease_id: int,
        disease_name: str,
        therapeutic_area: Optional[str],
        enrich_new_drugs: bool = False
    ):
        """
        Store drugs in the database.

        Args:
            drugs: List of pipeline drugs to store
            disease_id: Disease intelligence table ID
            disease_name: Name of the disease
            therapeutic_area: Therapeutic area (optional)
            enrich_new_drugs: If True, run new drugs through full DrugProcessor extraction
        """
        # Ensure disease exists in drug database
        drug_db_disease_id = self.repo.ensure_disease_in_drug_db(disease_name, therapeutic_area)

        # Initialize DrugProcessor if enrichment is enabled
        drug_processor = None
        if enrich_new_drugs and DRUG_PROCESSOR_AVAILABLE:
            try:
                drug_processor = DrugProcessor(db=self.repo.db, skip_parsing=False)
                logger.info("DrugProcessor initialized for new drug enrichment")
            except Exception as e:
                logger.warning(f"Failed to initialize DrugProcessor: {e}")

        drugs_enriched = 0
        drugs_stored = 0

        for drug in drugs:
            try:
                # Check if drug already exists in database
                existing_drug = self.repo.find_drug_by_name(drug.generic_name, drug.brand_name)

                if existing_drug:
                    # Drug exists - just update and link
                    drug_id = self.repo.upsert_drug(drug)
                    logger.debug(f"Updated existing drug: {drug.generic_name} (ID: {drug_id})")
                elif drug_processor:
                    # Skip enrichment for established/generic drugs (comparators, not novel pipeline)
                    if self._is_established_drug(drug.generic_name):
                        logger.info(f"Skipping enrichment for established drug: {drug.generic_name}")
                        drug_id = self.repo.upsert_drug(drug)
                    else:
                        # New drug - run through full extraction pipeline
                        logger.info(f"Running full extraction for new drug: {drug.generic_name}")
                        drug_was_enriched = False
                        try:
                            result = drug_processor.process(drug.generic_name, force_refresh=False)
                            if result.drug_id:
                                drug_id = result.drug_id
                                drugs_enriched += 1
                                drug_was_enriched = True
                                logger.info(f"  Enriched {drug.generic_name}: {result.status.value} ({result.completeness_score:.0%})")
                            else:
                                # DrugProcessor failed, fall back to basic storage
                                logger.warning(f"  DrugProcessor failed for {drug.generic_name}: {result.error}")
                                drug_id = self.repo.upsert_drug(drug)
                        except Exception as e:
                            logger.warning(f"  DrugProcessor error for {drug.generic_name}: {e}")
                            drug_id = self.repo.upsert_drug(drug)

                        # For enriched drugs, skip disease linking (DrugProcessor stores indications)
                        # but still store pipeline sources for traceability
                        if drug_was_enriched:
                            for nct_id in drug.source_nct_ids:
                                self.repo.add_source(PipelineSource(
                                    disease_id=disease_id,
                                    drug_id=drug_id,
                                    nct_id=nct_id,
                                    source_type="clinicaltrials_gov",
                                    confidence_score=drug.confidence_score
                                ))
                            for url in drug.source_urls:
                                self.repo.add_source(PipelineSource(
                                    disease_id=disease_id,
                                    drug_id=drug_id,
                                    source_url=url,
                                    source_type="press_release",
                                    confidence_score=drug.confidence_score
                                ))
                            drugs_stored += 1
                            continue
                else:
                    # No enrichment - basic storage
                    drug_id = self.repo.upsert_drug(drug)

                drugs_stored += 1

                # Link to disease
                self.repo.link_drug_to_disease(
                    drug_id=drug_id,
                    disease_id=drug_db_disease_id,
                    disease_name=disease_name,
                    approval_status=drug.approval_status,
                    data_source=", ".join(drug.data_sources)
                )

                # Store sources
                for nct_id in drug.source_nct_ids:
                    self.repo.add_source(PipelineSource(
                        disease_id=disease_id,
                        drug_id=drug_id,
                        nct_id=nct_id,
                        source_type="clinicaltrials_gov",
                        confidence_score=drug.confidence_score
                    ))

                for url in drug.source_urls:
                    self.repo.add_source(PipelineSource(
                        disease_id=disease_id,
                        drug_id=drug_id,
                        source_url=url,
                        source_type="press_release",
                        confidence_score=drug.confidence_score
                    ))

            except Exception as e:
                logger.warning(f"Failed to store drug {drug.generic_name}: {e}")

        if enrich_new_drugs:
            logger.info(f"Storage complete: {drugs_stored} drugs stored, {drugs_enriched} enriched via DrugProcessor")

    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Parse JSON from LLM response with robust error handling."""
        try:
            # Try to find JSON in the response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                json_str = json_match.group()
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    # Try to fix common issues
                    logger.debug(f"Initial JSON parse failed: {e}")

                    # Try to fix truncated JSON by finding complete objects
                    # Find the last complete drug entry and close the JSON
                    fixed_json = self._fix_truncated_json(json_str)
                    if fixed_json:
                        try:
                            return json.loads(fixed_json)
                        except json.JSONDecodeError:
                            pass

                    # Log the error location for debugging
                    logger.warning(f"Failed to parse JSON at position {e.pos}: {e.msg}")
                    return None
            return None
        except Exception as e:
            logger.warning(f"Failed to parse JSON: {e}")
            return None

    def _fix_truncated_json(self, json_str: str) -> Optional[str]:
        """Attempt to fix truncated JSON by finding complete drug entries."""
        try:
            # Find all complete drug objects (ending with })
            # Look for pattern: "generic_name": "something" ... }
            drug_pattern = r'\{\s*"generic_name"\s*:\s*"[^"]+"\s*[^}]*?\}'

            drugs = re.findall(drug_pattern, json_str, re.DOTALL)
            if drugs:
                # Try to reconstruct valid JSON with complete drugs
                drugs_json = ",\n    ".join(drugs)
                fixed = f'{{"drugs": [{drugs_json}], "extraction_notes": "Recovered from truncated response"}}'
                return fixed
            return None
        except Exception:
            return None

    def format_landscape_report(self, landscape: CompetitiveLandscape) -> str:
        """Format landscape as a readable report."""
        lines = [
            "=" * 60,
            f"COMPETITIVE LANDSCAPE: {landscape.disease_name}",
            "=" * 60,
            "",
            f"Total Active Drugs: {landscape.total_drugs}",
            f"  Approved: {landscape.approved_count}",
            f"  Phase 3: {landscape.phase3_count}",
            f"  Phase 2: {landscape.phase2_count}",
            f"  Phase 1: {landscape.phase1_count}",
            f"  Preclinical: {landscape.preclinical_count}",
            f"",
            f"Discontinued/Failed: {landscape.discontinued_count}",
            "",
        ]

        if landscape.key_moa_classes:
            lines.append(f"Key MOA Classes: {', '.join(landscape.key_moa_classes)}")
            lines.append("")

        def format_drugs(drug_list: List[PipelineDrug], header: str):
            if not drug_list:
                return []
            result = [f"--- {header} ({len(drug_list)}) ---"]
            for i, drug in enumerate(drug_list, 1):
                name = drug.brand_name or drug.generic_name
                result.append(f"{i}. {name} ({drug.generic_name})")
                result.append(f"   Manufacturer: {drug.manufacturer or 'N/A'}")
                result.append(f"   MOA: {drug.mechanism_of_action or 'N/A'}")
                if drug.dosing_summary:
                    result.append(f"   Dosing: {drug.dosing_summary}")
                if drug.recent_milestone:
                    result.append(f"   Recent: {drug.recent_milestone}")
                if drug.source_nct_ids:
                    result.append(f"   Trials: {', '.join(drug.source_nct_ids[:3])}")
                result.append("")
            return result

        def format_discontinued_drugs(drug_list: List[PipelineDrug]):
            if not drug_list:
                return []
            result = [f"--- DISCONTINUED/FAILED ({len(drug_list)}) ---"]
            for i, drug in enumerate(drug_list, 1):
                name = drug.brand_name or drug.generic_name
                status = drug.development_status or "discontinued"
                result.append(f"{i}. {name} ({drug.generic_name}) [{status.upper()}]")
                result.append(f"   Manufacturer: {drug.manufacturer or 'N/A'}")
                result.append(f"   MOA: {drug.mechanism_of_action or 'N/A'}")
                result.append(f"   Highest Phase: {drug.failure_stage or drug.highest_phase or 'N/A'}")
                if drug.discontinuation_date:
                    result.append(f"   Discontinued: {drug.discontinuation_date}")
                if drug.discontinuation_reason:
                    result.append(f"   Reason: {drug.discontinuation_reason}")
                if drug.source_urls:
                    result.append(f"   Source: {drug.source_urls[0][:60]}...")
                result.append("")
            return result

        lines.extend(format_drugs(landscape.approved_drugs, "APPROVED"))
        lines.extend(format_drugs(landscape.phase3_drugs, "PHASE 3"))
        lines.extend(format_drugs(landscape.phase2_drugs, "PHASE 2"))
        lines.extend(format_drugs(landscape.phase1_drugs, "PHASE 1"))
        lines.extend(format_drugs(landscape.preclinical_drugs, "PRECLINICAL"))
        lines.extend(format_discontinued_drugs(landscape.discontinued_drugs))

        lines.append("-" * 60)
        lines.append(f"Search: {landscape.search_timestamp}")
        lines.append(f"Trials Reviewed: {landscape.trials_reviewed}")
        lines.append(f"Sources: {', '.join(landscape.sources_searched)}")

        return "\n".join(lines)
