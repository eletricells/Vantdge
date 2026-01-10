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

logger = logging.getLogger(__name__)

# Load Jinja2 templates
PROMPTS_DIR = Path(__file__).parent / "prompts"
jinja_env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))

# Known pipeline drugs by indication (FOR VALIDATION ONLY - not used as source data)
# This is used to check completeness of de novo extraction
KNOWN_PIPELINE_VALIDATION = {
    "systemic lupus erythematosus": {
        "approved_us": ["belimumab", "anifrolumab"],
        "active_phase3": ["deucravacitinib", "cenerimod", "litifilimab", "dapirolizumab pegol", "iberdomide", "telitacicept"],
        "active_phase2": ["nipocalimab", "obexelimab", "ianalumab", "upadacitinib", "IMVT-1402", "rozanolixizumab"],
        "active_phase1": ["VIB7734", "KPL-404", "prulacabtagene leucel"],
        "discontinued": [
            "baricitinib",  # Eli Lilly discontinued 2022
            "atacicept",  # Merck/Serono discontinued
            "tabalumab",  # Eli Lilly discontinued
            "blisibimod",  # Anthera discontinued
            "epratuzumab",  # UCB Phase 3 failure
            "sifalimumab",  # AstraZeneca discontinued (precursor to anifrolumab)
            "rontalizumab",  # Genentech discontinued
            "lupuzor",  # ImmuPharma Phase 3 failure
            "abatacept",  # BMS failed in SLE
            "rituximab",  # Failed EXPLORER/LUNAR trials
            "ocrelizumab",  # Roche discontinued for SLE
        ],
    }
}

# Drugs that are FDA-approved for SPECIFIC indications
# Only mark as "Approved" if the drug is approved for the indication being searched
# Other FDA-approved drugs remain as "investigational" for that indication
INDICATION_APPROVED_DRUGS = {
    "systemic lupus erythematosus": ["belimumab", "anifrolumab"],
    "lupus nephritis": ["belimumab", "voclosporin"],
    "rheumatoid arthritis": ["adalimumab", "etanercept", "infliximab", "certolizumab", "golimumab",
                             "tocilizumab", "sarilumab", "tofacitinib", "baricitinib", "upadacitinib",
                             "abatacept", "rituximab"],
    "psoriatic arthritis": ["adalimumab", "etanercept", "infliximab", "certolizumab", "golimumab",
                            "secukinumab", "ixekizumab", "ustekinumab", "apremilast", "tofacitinib",
                            "abatacept", "guselkumab", "upadacitinib", "deucravacitinib"],
}


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

        # Create pipeline run record
        run_id = self.repo.create_run(disease_id, disease_key, "full")

        try:
            # Step 1: Search ClinicalTrials.gov (INDUSTRY-SPONSORED ONLY)
            logger.info("Step 1: Searching ClinicalTrials.gov (industry-sponsored)...")
            trials = await self._search_clinical_trials(disease_name)
            logger.info(f"  Found {len(trials)} industry-sponsored clinical trials")

            # Step 2: Extract drugs from trials (in batches to avoid JSON parsing issues)
            logger.info("Step 2: Extracting drugs from trials (batched)...")
            drugs_from_trials = await self._extract_drugs_from_trials_batched(disease_name, trials)
            logger.info(f"  Extracted {len(drugs_from_trials)} drugs from trials")

            # Step 3: Web search for active pipeline
            web_sources = []
            drugs_from_news = []
            discontinued_drugs = []
            if include_web_search and self.web_searcher:
                logger.info("Step 3: Searching web for active pipeline...")
                web_sources = await self._search_pipeline_news(disease_name)
                logger.info(f"  Found {len(web_sources)} web sources")

                if web_sources:
                    drugs_from_news = await self._extract_from_news(
                        disease_name, web_sources, drugs_from_trials
                    )
                    logger.info(f"  Extracted {len(drugs_from_news)} drugs from news")

                # Step 4: Search for discontinued/failed programs
                logger.info("Step 4: Searching for discontinued/failed programs...")
                discontinued_sources = await self._search_discontinued_programs(disease_name)
                logger.info(f"  Found {len(discontinued_sources)} discontinued program sources")

                if discontinued_sources:
                    discontinued_drugs = await self._extract_discontinued_drugs(
                        disease_name, discontinued_sources
                    )
                    logger.info(f"  Extracted {len(discontinued_drugs)} discontinued drugs")

            # Step 5: Merge all sources (trials + news)
            logger.info("Step 5: Merging and deduplicating...")
            all_drugs = self._merge_drugs(drugs_from_trials, drugs_from_news)
            # Merge discontinued (but mark them appropriately)
            all_drugs = self._merge_drugs(all_drugs, discontinued_drugs)
            logger.info(f"  Total unique drugs: {len(all_drugs)}")

            # Step 5a: Filter out established/generic drugs (comparators, not novel pipeline)
            established_count = sum(1 for d in all_drugs if self._is_established_drug(d.generic_name))
            if established_count > 0:
                all_drugs = [d for d in all_drugs if not self._is_established_drug(d.generic_name)]
                logger.info(f"  Filtered out {established_count} established/generic drugs")
                logger.info(f"  Remaining pipeline drugs: {len(all_drugs)}")

            # Step 5.5: LLM-based filtering for related but distinct conditions
            if filter_related_conditions and len(all_drugs) > 0:
                logger.info("Step 5.5: Filtering drugs for related but distinct conditions...")
                all_drugs = await self._filter_related_conditions(disease_name, all_drugs)
                logger.info(f"  After filtering: {len(all_drugs)} drugs")

            # Step 6: Verify approved drugs using indication-specific approval list
            logger.info("Step 6: Verifying approved drugs for indication...")
            all_drugs = await self._verify_approved_drugs(all_drugs, disease_name)

            # Step 7: Validate against known list and run supplementary search for missing
            logger.info("Step 7: Validating against known drug list...")
            missing_drugs = self._validate_against_known_list(disease_name, all_drugs)

            # Step 8: Supplementary search for missing drugs
            if missing_drugs:
                logger.info(f"Step 8: Running supplementary search for {len(missing_drugs)} missing drugs...")
                supplementary_drugs = await self._search_missing_drugs(disease_name, missing_drugs)
                if supplementary_drugs:
                    logger.info(f"  Found {len(supplementary_drugs)} drugs via supplementary search")
                    all_drugs = self._merge_drugs(all_drugs, supplementary_drugs)
                    # Re-validate to see final gaps
                    logger.info("  Re-validating after supplementary search...")
                    final_missing = self._validate_against_known_list(disease_name, all_drugs)
                    if final_missing:
                        logger.warning(f"  Final missing drugs: {', '.join(final_missing)}")

            # Step 9: Build landscape
            landscape = self._build_landscape(disease_name, all_drugs, therapeutic_area)
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

    def _validate_against_known_list(self, disease_name: str, drugs: List[PipelineDrug]) -> List[str]:
        """Validate extracted drugs against known list and report gaps.

        Returns:
            List of missing drug names for supplementary search
        """
        disease_key = disease_name.lower()
        known = KNOWN_PIPELINE_VALIDATION.get(disease_key, {})

        if not known:
            logger.info("  No validation list available for this disease")
            return []

        extracted_names = {d.generic_name.lower() for d in drugs}

        # Check for missing drugs
        all_known = (
            known.get("approved_us", []) +
            known.get("active_phase3", []) +
            known.get("active_phase2", []) +
            known.get("active_phase1", []) +
            known.get("discontinued", [])
        )

        missing = []
        for drug in all_known:
            if drug.lower() not in extracted_names:
                missing.append(drug)

        if missing:
            logger.warning(f"  VALIDATION: Missing {len(missing)} known drugs: {', '.join(missing)}")
        else:
            logger.info(f"  VALIDATION: All {len(all_known)} known drugs found")

        return missing

    async def _verify_approved_drugs(
        self, drugs: List[PipelineDrug], disease_name: str = ""
    ) -> List[PipelineDrug]:
        """
        Verify approved status for the SPECIFIC indication being searched.

        A drug is only marked as "Approved" if it is FDA-approved for THIS indication.
        Drugs approved for other indications remain as their trial phase for this indication.
        """
        # First, normalize drug names using aliases
        for drug in drugs:
            generic_lower = drug.generic_name.lower()
            if generic_lower in self.DRUG_ALIASES:
                canonical_name = self.DRUG_ALIASES[generic_lower]
                logger.info(f"  Normalizing {drug.generic_name} to {canonical_name}")
                drug.generic_name = canonical_name

        # Get list of drugs approved for this specific indication
        disease_key = disease_name.lower()
        indication_approved = INDICATION_APPROVED_DRUGS.get(disease_key, [])
        indication_approved_lower = [d.lower() for d in indication_approved]

        for drug in drugs:
            generic_lower = drug.generic_name.lower()

            # Check if this drug is approved for THIS specific indication
            if generic_lower in indication_approved_lower:
                drug.approval_status = "approved"
                drug.highest_phase = "Approved"
                if "FDA Approved for Indication" not in drug.data_sources:
                    drug.data_sources.append("FDA Approved for Indication")
                logger.info(f"  {drug.generic_name} is FDA-approved for {disease_name}")
            elif drug.highest_phase == "Approved" or drug.approval_status == "approved":
                # Drug was marked as approved but not for THIS indication
                # Keep as investigational with its highest phase from trials
                logger.info(f"  {drug.generic_name} not approved for {disease_name}, marking as investigational")
                drug.approval_status = "investigational"
                # Try to get phase from trial data, default to Phase 2/3 for approved drugs
                if drug.highest_phase == "Approved":
                    drug.highest_phase = "Phase 3"  # Assume Phase 3 if approved elsewhere

        # Optional: Also verify with OpenFDA for drugs we think are approved
        if self.openfda and indication_approved:
            for drug in drugs:
                if drug.approval_status == "approved":
                    try:
                        is_fda_approved = self.openfda.is_drug_approved(drug.generic_name)
                        if is_fda_approved:
                            if "FDA Verified" not in drug.data_sources:
                                drug.data_sources.append("FDA Verified")
                    except Exception as e:
                        logger.warning(f"FDA verification failed for {drug.generic_name}: {e}")

        return drugs

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

    async def _search_clinical_trials(self, disease_name: str) -> List[Dict]:
        """Search ClinicalTrials.gov for INDUSTRY-SPONSORED, ACTIVE trials related to the disease."""
        # Filter for industry-sponsored AND active/recruiting trials only
        # This significantly reduces noise from old completed trials
        # Use separate filter parameters (not combined in filter.advanced) for proper API syntax
        search_params = {
            "query.cond": disease_name,  # Search in conditions
            "pageSize": 100,
            "format": "json",
            # Industry-sponsored (using advanced filter)
            "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY",
            # Active status (using dedicated status filter)
            "filter.overallStatus": ",".join(self.ACTIVE_TRIAL_STATUSES),
        }

        all_trials = []
        page_token = None

        while True:
            params = search_params.copy()
            if page_token:
                params["pageToken"] = page_token

            result = self.ct_client.get("/studies", params=params)

            if not result or "studies" not in result:
                break

            studies = result["studies"]
            all_trials.extend(studies)

            page_token = result.get("nextPageToken")
            if not page_token or len(all_trials) >= 300:  # Cap at 300 active trials
                break

        logger.info(f"    Found {len(all_trials)} active/recruiting trials")

        # PRIORITY: Search for completed Phase 3 trials - these represent late-stage drugs
        # that may be awaiting regulatory filing or approval
        # Note: Using separate API calls since combined filters can cause 400 errors
        phase3_completed_params = {
            "query.cond": disease_name,
            "query.term": "AREA[Phase]PHASE3",  # Use query.term for phase filter
            "pageSize": 30,
            "format": "json",
            "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY AND AREA[OverallStatus]COMPLETED",
            "sort": "CompletionDate:desc",
        }

        result = self.ct_client.get("/studies", params=phase3_completed_params)
        if result and "studies" in result:
            phase3_completed = result["studies"]
            logger.info(f"    Found {len(phase3_completed)} completed Phase 3 trials")
            # Add these with high priority - they represent late-stage drugs
            all_trials.extend(phase3_completed)
        else:
            # Fallback: search without phase filter and filter results
            logger.info("    Phase 3 filter failed, using fallback search")
            fallback_params = {
                "query.cond": disease_name,
                "pageSize": 50,
                "format": "json",
                "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY AND AREA[OverallStatus]COMPLETED",
                "sort": "CompletionDate:desc",
            }
            result = self.ct_client.get("/studies", params=fallback_params)
            if result and "studies" in result:
                # Filter for Phase 3 manually
                phase3_completed = []
                for study in result["studies"]:
                    phases = study.get("protocolSection", {}).get("designModule", {}).get("phases", [])
                    if "PHASE3" in phases or "PHASE2/PHASE3" in phases:
                        phase3_completed.append(study)
                logger.info(f"    Found {len(phase3_completed)} completed Phase 3 trials (fallback)")
                all_trials.extend(phase3_completed)

        # Also search for recently completed trials (last 3 years) for context
        # These may represent drugs that completed Phase 2/3 and are awaiting results
        recent_completed_params = {
            "query.cond": disease_name,
            "pageSize": 50,
            "format": "json",
            "filter.advanced": "AREA[LeadSponsorClass]INDUSTRY",
            "filter.overallStatus": "COMPLETED",
            "sort": "CompletionDate:desc",  # Most recent first
        }

        result = self.ct_client.get("/studies", params=recent_completed_params)
        if result and "studies" in result:
            # Only include trials completed in the last 4 years
            cutoff_year = str(datetime.now().year - 4)
            recent_completed = []
            for study in result["studies"][:50]:
                try:
                    completion_date = study.get("protocolSection", {}).get("statusModule", {}).get("completionDateStruct", {}).get("date", "")
                    if completion_date and completion_date >= cutoff_year:
                        recent_completed.append(study)
                except:
                    pass
            logger.info(f"    Found {len(recent_completed)} recently completed trials (since {cutoff_year})")
            all_trials.extend(recent_completed)

        return all_trials

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

    async def _search_missing_drugs(
        self,
        disease_name: str,
        missing_drug_names: List[str]
    ) -> List[PipelineDrug]:
        """Search for specific missing drugs by intervention name in ClinicalTrials.gov.

        This is a supplementary search to find drugs that may be registered
        under different names or in trials not captured by condition-based search.
        """
        if not missing_drug_names:
            return []

        logger.info(f"  Searching for {len(missing_drug_names)} missing drugs by intervention name...")

        found_drugs = []
        for drug_name in missing_drug_names:
            try:
                # Search by intervention name
                params = {
                    "query.intr": drug_name,
                    "query.cond": disease_name,
                    "pageSize": 10,
                    "format": "json",
                }

                result = self.ct_client.get("/studies", params=params)

                if result and "studies" in result and len(result["studies"]) > 0:
                    studies = result["studies"]
                    # Get the most advanced trial
                    best_phase = None
                    best_study = None
                    phase_order = {"PHASE4": 1, "PHASE3": 2, "PHASE2/PHASE3": 2.5,
                                   "PHASE2": 3, "PHASE1/PHASE2": 3.5, "PHASE1": 4,
                                   "EARLY_PHASE1": 5, "NA": 6}

                    for study in studies:
                        design = study.get("protocolSection", {}).get("designModule", {})
                        phases = design.get("phases", [])
                        for phase in phases:
                            if best_phase is None or phase_order.get(phase, 6) < phase_order.get(best_phase, 6):
                                best_phase = phase
                                best_study = study

                    if best_study:
                        trial_data = self.ct_client.extract_trial_data(best_study)
                        status = trial_data.get("trial_status", "UNKNOWN")
                        sponsors = trial_data.get("sponsors", {})

                        # Determine development status
                        dev_status = "active"
                        if status in self.INACTIVE_TRIAL_STATUSES:
                            dev_status = "discontinued"

                        # Convert phase to readable format
                        phase_str = best_phase.replace("PHASE", "Phase ").replace("/Phase ", "/").title() if best_phase else "Unknown"
                        if phase_str == "Na":
                            phase_str = "Unknown"

                        drug = PipelineDrug(
                            generic_name=drug_name,
                            manufacturer=sponsors.get("lead"),
                            highest_phase=phase_str,
                            development_status=dev_status,
                            source_nct_ids=[trial_data.get("nct_id")] if trial_data.get("nct_id") else [],
                            data_sources=["ClinicalTrials.gov (Supplementary Search)"],
                            confidence_score=0.7,
                        )
                        found_drugs.append(drug)
                        logger.info(f"    Found {drug_name} via intervention search: {phase_str}")

            except Exception as e:
                logger.warning(f"    Search for {drug_name} failed: {e}")

        return found_drugs

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
                "Approved": 1, "NDA Filed": 2, "Phase 3": 3, "Phase 2/3": 3,
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

                    # Check for regulatory filing - indicates Phase 3 complete
                    if update_type == "regulatory_filing":
                        news_phase = "NDA Filed"
                        logger.info(f"  News: {matching_drug.generic_name} has regulatory filing - updating to NDA Filed")

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

    # Phase ranking for comparison (lower number = more advanced)
    PHASE_RANK = {
        "Approved": 1, "NDA Filed": 2, "Phase 3": 3, "Phase 2/3": 3,
        "Phase 2": 4, "Phase 1/2": 4, "Phase 1": 5, "Preclinical": 6
    }

    def _merge_drugs(
        self,
        trials_drugs: List[PipelineDrug],
        news_drugs: List[PipelineDrug]
    ) -> List[PipelineDrug]:
        """Merge and deduplicate drugs from different sources."""
        # Use generic_name as key
        drug_map: Dict[str, PipelineDrug] = {}

        # First pass: add trials drugs, keeping most advanced phase for duplicates
        for drug in trials_drugs:
            key = drug.generic_name.lower()
            if key in drug_map:
                existing = drug_map[key]
                existing_rank = self.PHASE_RANK.get(existing.highest_phase, 10)
                incoming_rank = self.PHASE_RANK.get(drug.highest_phase, 10)
                if incoming_rank < existing_rank:
                    # Incoming has more advanced phase - merge into existing but update phase
                    existing.highest_phase = drug.highest_phase
                    existing.source_nct_ids.extend(drug.source_nct_ids)
                    existing.data_sources = list(set(existing.data_sources + drug.data_sources))
                else:
                    # Keep existing phase but merge other data
                    existing.source_nct_ids.extend(drug.source_nct_ids)
            else:
                drug_map[key] = drug

        for drug in news_drugs:
            key = drug.generic_name.lower()
            if key in drug_map:
                # Merge data
                existing = drug_map[key]
                if drug.recent_milestone and not existing.recent_milestone:
                    existing.recent_milestone = drug.recent_milestone
                if drug.efficacy_summary and not existing.efficacy_summary:
                    existing.efficacy_summary = drug.efficacy_summary
                existing.source_urls.extend(drug.source_urls)
                existing.data_sources = list(set(existing.data_sources + drug.data_sources))

                # CRITICAL: Update phase if incoming drug has more advanced phase
                existing_rank = self.PHASE_RANK.get(existing.highest_phase, 10)
                incoming_rank = self.PHASE_RANK.get(drug.highest_phase, 10)
                if incoming_rank < existing_rank:
                    logger.info(f"  Merge: Upgrading {existing.generic_name} from {existing.highest_phase} to {drug.highest_phase}")
                    existing.highest_phase = drug.highest_phase

                # If the incoming drug is marked as discontinued, update existing
                if drug.development_status in ["discontinued", "failed", "terminated", "on_hold"]:
                    existing.development_status = drug.development_status
                    if drug.discontinuation_date:
                        existing.discontinuation_date = drug.discontinuation_date
                    if drug.discontinuation_reason:
                        existing.discontinuation_reason = drug.discontinuation_reason
                    if drug.failure_stage:
                        existing.failure_stage = drug.failure_stage
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
        if "approved" in phase_lower or "market" in phase_lower:
            return "Approved"
        elif "phase 3" in phase_lower or "phase3" in phase_lower or "iii" in phase_lower:
            return "Phase 3"
        elif "phase 2" in phase_lower or "phase2" in phase_lower or "ii" in phase_lower:
            return "Phase 2"
        elif "phase 1" in phase_lower or "phase1" in phase_lower or "i" in phase_lower:
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
        therapeutic_area: Optional[str] = None
    ) -> CompetitiveLandscape:
        """Build competitive landscape from drugs."""
        landscape = CompetitiveLandscape(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area
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
