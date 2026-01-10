"""
Extract efficacy data from publications using PubMed + Claude.

Priority data source for efficacy benchmarking.
"""

import json
import logging
import re
import os
import time
from typing import List, Optional, Dict, Any

from anthropic import Anthropic
import httpx

from src.tools.pubmed import PubMedAPI
from src.tools.clinicaltrials import ClinicalTrialsAPI
from ..models import (
    EfficacyDataPoint, DataSource, ReviewStatus, ApprovedDrug, DiseaseMatch
)

logger = logging.getLogger(__name__)

# Rate limit settings for PubMed
PUBMED_DELAY_BETWEEN_DRUGS = 2.0  # Seconds between processing different drugs
PUBMED_RETRY_DELAY = 5.0  # Seconds to wait after a 429 error
PUBMED_MAX_RETRIES = 3  # Max retries for rate limit errors


class PublicationEfficacyExtractor:
    """
    Searches for and extracts efficacy data from publications.

    Uses PubMed for paper discovery and Claude for structured data extraction.
    """

    @staticmethod
    def clean_generic_name(name: str) -> str:
        """
        Clean generic name for better PubMed search results.

        Removes suffixes like -FNIA, -XXXX (antibody designations) that aren't
        used in publication titles/abstracts.
        """
        import re
        if not name:
            return name

        # Remove antibody suffix patterns like -FNIA, -ADCC, -XXXX
        # These are FDA-assigned suffixes not used in papers
        cleaned = re.sub(r'-[A-Z]{3,4}$', '', name, flags=re.IGNORECASE)

        # Also handle cases like "ANIFROLUMAB-FNIA" -> "anifrolumab"
        cleaned = cleaned.strip()

        return cleaned

    EXTRACTION_SYSTEM_PROMPT = """You are a clinical data extraction specialist.
Your task is to extract efficacy endpoint data from clinical trial publications.

CRITICAL RULES:
1. Extract ONLY data explicitly stated in the text
2. Do NOT infer, estimate, or calculate values
3. If a value is not clearly stated, use null
4. Include the exact source text in 'source_text' field
5. Extract ALL efficacy endpoints mentioned, not just primary

For each endpoint, extract these fields:
- endpoint_name: Exact name as stated (e.g., "SRI-4", "PASI 75", "ACR20")
- endpoint_type: "primary" or "secondary" or "exploratory"
- drug_arm_name: Drug arm with dose (e.g., "Belimumab 10 mg/kg", "Anifrolumab 300 mg", "Upadacitinib 15 mg")
- drug_arm_result: Numeric value (response rate, score, etc.)
- drug_arm_result_unit: Unit (usually "%", but could be "score", "days", etc.)
- drug_arm_n: Sample size in drug arm
- comparator_arm_name: Comparator name with dose if active (e.g., "Placebo", "Adalimumab 40 mg", "Standard of Care")
- comparator_arm_type: "placebo" or "active" (active = another drug)
- comparator_arm_result: Numeric value for comparator
- comparator_arm_n: Sample size in comparator arm
- p_value: Statistical significance value
- confidence_interval: If available (e.g., "95% CI: 2.1-8.3")
- timepoint: Assessment time (e.g., "Week 52", "Month 6")
- trial_name: Trial name/acronym if mentioned (e.g., "BLISS-52", "TULIP-2", "MUSE")
- nct_id: ClinicalTrials.gov identifier if mentioned (e.g., "NCT00424476")
- trial_phase: Phase (e.g., "Phase 3")
- source_text: Exact quote from paper supporting this data point

IMPORTANT: If the trial has multiple drug arms (e.g., 150 mg and 300 mg), create separate entries for EACH arm.

Return ONLY a valid JSON array. No markdown formatting, no explanations."""

    def __init__(
        self,
        anthropic_client: Optional[Anthropic] = None,
        pubmed_api: Optional[PubMedAPI] = None,
        clinicaltrials_api: Optional[ClinicalTrialsAPI] = None
    ):
        """
        Initialize the extractor.

        Args:
            anthropic_client: Optional Anthropic client (will create if not provided)
            pubmed_api: Optional PubMed API (will create if not provided)
            clinicaltrials_api: Optional ClinicalTrials.gov API
        """
        self.anthropic = anthropic_client or Anthropic(
            api_key=os.getenv("ANTHROPIC_API_KEY")
        )
        self.pubmed = pubmed_api or PubMedAPI(
            api_key=os.getenv("NCBI_API_KEY")
        )
        self.ct_api = clinicaltrials_api or ClinicalTrialsAPI()

    def get_publications_from_trials(
        self,
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        max_trials: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get publications by first finding clinical trials, then getting their linked publications.

        This is more reliable than direct PubMed search as CT.gov links to actual results papers.
        Prioritizes RESULT-type publications (primary results papers) over BACKGROUND references.

        Args:
            drug: Drug to search for
            disease: Disease context
            max_trials: Maximum number of trials to check

        Returns:
            List of paper dictionaries with pmid, title, abstract, nct_id
        """
        clean_name = self.clean_generic_name(drug.generic_name)
        logger.info(f"Finding publications via CT.gov trials for '{clean_name}'")

        # Build list of condition terms to search (disease name + synonyms)
        condition_terms = [disease.standard_name]
        if disease.synonyms:
            # Add synonyms, prioritizing longer/more specific terms
            for syn in disease.synonyms:
                if syn and syn not in condition_terms:
                    condition_terms.append(syn)

        logger.info(f"Searching CT.gov: drug='{clean_name}', conditions={condition_terms[:5]}")

        # Use efficient structured search with proper filters
        # Phase 2/3, Industry-sponsored trials
        all_trials = self.ct_api.search_pivotal_trials(
            drug_name=clean_name,
            conditions=condition_terms[:5],  # Limit to first 5 condition terms
            max_results=max_trials * 3,
            phase_filter="PHASE2|PHASE3",
            sponsor_filter="INDUSTRY",
            status_filter=None  # Include all statuses, completed will be prioritized later
        )

        # If no industry trials found, try without sponsor filter
        if not all_trials:
            logger.info("No industry-sponsored trials found, searching all sponsors...")
            all_trials = self.ct_api.search_pivotal_trials(
                drug_name=clean_name,
                conditions=condition_terms[:5],
                max_results=max_trials * 3,
                phase_filter="PHASE2|PHASE3",
                sponsor_filter=None,  # All sponsors
                status_filter=None
            )

        # Also search with brand name if available and still need more trials
        if drug.brand_name and len(all_trials) < max_trials:
            logger.info(f"Also searching with brand name: '{drug.brand_name}'")
            brand_trials = self.ct_api.search_pivotal_trials(
                drug_name=drug.brand_name,
                conditions=condition_terms[:3],
                max_results=max_trials,
                phase_filter="PHASE2|PHASE3",
                sponsor_filter="INDUSTRY",
                status_filter=None
            )
            # Add unique trials
            seen_ncts = {t.get('nct_id') for t in all_trials}
            for t in brand_trials:
                if t.get('nct_id') not in seen_ncts:
                    all_trials.append(t)

        if not all_trials:
            logger.warning(f"No Phase 2/3 trials found for {clean_name} in {disease.standard_name}")
            return []

        # Sort trials: completed first, then by phase (Phase 3 before Phase 2)
        def trial_sort_key(trial):
            status = trial.get('status', '').upper()
            phase = trial.get('phase', '').upper()
            # Completed = 0, others = 1
            status_score = 0 if 'COMPLETED' in status else 1
            # Phase 3 = 0, Phase 2 = 1
            phase_score = 0 if 'PHASE 3' in phase or 'PHASE3' in phase or 'III' in phase else 1
            return (status_score, phase_score)

        relevant_trials = sorted(all_trials, key=trial_sort_key)

        for trial in relevant_trials[:10]:
            logger.debug(
                f"  Trial: {trial.get('nct_id')} | {trial.get('phase')} | "
                f"{trial.get('status')} | {trial.get('title', '')[:40]}..."
            )

        logger.info(f"Found {len(relevant_trials)} Phase 2/3 trials for {clean_name}")

        # Step 2: Get publications from each trial
        # Prioritize RESULT-type and original publications (primary results papers)
        original_pmids = []  # RESULT type OR is_original=True (primary results papers)
        other_pmids = []     # BACKGROUND and other types
        pmid_to_nct = {}
        pmid_to_original = {}  # Track which PMIDs are original

        for trial in relevant_trials[:max_trials]:
            nct_id = trial.get('nct_id')
            if not nct_id:
                continue

            # Get all publications linked to this trial (sorted by priority)
            pubs = self.ct_api.get_trial_publications(nct_id)
            logger.debug(f"Trial {nct_id}: Found {len(pubs)} publications")

            for pub in pubs:
                pmid = pub.get('pmid')
                pub_type = pub.get('type', 'UNKNOWN').upper()
                is_original = pub.get('is_original', False)

                if pmid:
                    pmid_to_nct[pmid] = nct_id
                    # Prioritize RESULT publications OR papers marked as original
                    # (original = has trial acronym in citation OR primary results keywords)
                    if pub_type == 'RESULT' or is_original:
                        if pmid not in original_pmids:
                            original_pmids.append(pmid)
                            pmid_to_original[pmid] = True
                            logger.debug(f"  ORIGINAL publication: PMID {pmid} (type={pub_type}, is_original={is_original})")
                    else:
                        if pmid not in other_pmids and pmid not in original_pmids:
                            other_pmids.append(pmid)
                            pmid_to_original[pmid] = False

            # Small delay to avoid rate limits
            time.sleep(0.5)

        # Combine PMIDs with original papers first, then others
        all_pmids = original_pmids + other_pmids
        logger.info(f"Found {len(all_pmids)} unique PMIDs ({len(original_pmids)} ORIGINAL, {len(other_pmids)} other)")

        if not all_pmids:
            logger.warning(f"No publications found from {len(relevant_trials)} trials")
            return []

        # Step 3: Fetch paper details from PubMed
        # Fetch in batches to avoid API limits (max 200 IDs per request)
        papers = []
        batch_size = 50
        for i in range(0, len(all_pmids), batch_size):
            batch = all_pmids[i:i + batch_size]
            logger.debug(f"Fetching PubMed batch {i // batch_size + 1}: {len(batch)} PMIDs")
            batch_papers = self.pubmed.fetch_abstracts(batch)
            papers.extend(batch_papers)
            if i + batch_size < len(all_pmids):
                time.sleep(0.5)  # Rate limit between batches

        logger.info(f"Fetched {len(papers)} papers from PubMed")

        # Add NCT ID and track if it was an original/RESULT publication
        original_pmid_set = set(original_pmids)
        for paper in papers:
            pmid = paper.get('pmid')
            if pmid in pmid_to_nct:
                paper['nct_id'] = pmid_to_nct[pmid]
            paper['is_original_pub'] = pmid in original_pmid_set

        # Step 4: Filter to papers likely to contain efficacy data
        # Original/RESULT-type publications get priority and more lenient filtering
        efficacy_papers = []
        efficacy_keywords = ['efficacy', 'safety', 'phase', 'randomized', 'randomised',
                            'trial', 'placebo', 'response', 'endpoint', 'double-blind',
                            'week', 'primary', 'secondary', 'outcome']

        for paper in papers:
            title = (paper.get('title') or '').lower()
            abstract = (paper.get('abstract') or '').lower()
            combined = title + ' ' + abstract

            # Count keyword matches
            matches = sum(1 for kw in efficacy_keywords if kw in combined)

            # Prioritize papers with actual results (numbers in abstract)
            has_numbers = bool(re.search(r'\d+\.?\d*%', abstract))

            # Original publications (has trial acronym or primary results keywords)
            # Use more lenient threshold for these
            is_original = paper.get('is_original_pub', False)

            if is_original:
                # Original publications: only need 1 keyword match OR numbers
                if matches >= 1 or has_numbers:
                    efficacy_papers.append(paper)
                    logger.debug(f"Including ORIGINAL pub PMID {paper.get('pmid')}: {matches} keywords, has_numbers={has_numbers}")
            else:
                # Other publications: require stricter criteria
                if matches >= 3 or (matches >= 2 and has_numbers):
                    efficacy_papers.append(paper)

        # Sort efficacy papers: original papers first, then by PMID (older first)
        def sort_key(paper):
            is_orig = 0 if paper.get('is_original_pub', False) else 1
            try:
                pmid_num = int(paper.get('pmid', 99999999))
            except:
                pmid_num = 99999999
            return (is_orig, pmid_num)

        efficacy_papers.sort(key=sort_key)

        logger.info(f"Filtered to {len(efficacy_papers)} papers with efficacy data")
        return efficacy_papers

    def search_pivotal_trials(
        self,
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for pivotal trial publications.

        NEW FLOW:
        1. Discover trial names (CT.gov + Claude web search)
        2. Search for publications using trial names
        3. Return papers with known trial context

        Args:
            drug: Approved drug to search for
            disease: Disease to search within
            max_results: Maximum number of papers to return

        Returns:
            List of paper dictionaries with pmid, title, abstract, trial_name, etc.
        """
        # Clean the generic name (remove -FNIA, -XXXX suffixes)
        clean_name = self.clean_generic_name(drug.generic_name)
        logger.info(f"Searching for '{clean_name}' (original: '{drug.generic_name}')")

        # STEP 1: Discover trial names
        from .trial_discovery_service import TrialDiscoveryService
        trial_service = TrialDiscoveryService()
        trial_info = trial_service.discover_trials(
            drug_name=drug.brand_name or clean_name,
            generic_name=clean_name,
            indication=disease.standard_name,
            use_web_search=True
        )

        # If we have named trials, search for their publications
        named_trials = [t for t in trial_info.trials if t.name and not t.name.startswith("NCT")]
        if named_trials:
            logger.info(f"Discovered {len(named_trials)} named trials: {[t.name for t in named_trials]}")
            papers = self._search_by_trial_names(
                drug=drug,
                disease=disease,
                trials=named_trials,
                max_results=max_results
            )
            if papers:
                return papers

        # APPROACH 1: Get publications from CT.gov trials (more reliable)
        # Use more trials to find all relevant publications
        ct_papers = self.get_publications_from_trials(drug, disease, max_trials=max_results * 2)

        if ct_papers:
            logger.info(f"Found {len(ct_papers)} papers via CT.gov trial links")

            # Select papers to ensure coverage of different trials (NCT IDs)
            # First, get one paper per unique NCT ID
            selected = []
            seen_ncts = set()
            for paper in ct_papers:
                nct = paper.get('nct_id')
                if nct and nct not in seen_ncts:
                    selected.append(paper)
                    seen_ncts.add(nct)
                    if len(selected) >= max_results:
                        break

            # If we still have room, add more papers (prioritizing original papers)
            if len(selected) < max_results:
                for paper in ct_papers:
                    if paper not in selected:
                        selected.append(paper)
                        if len(selected) >= max_results:
                            break

            # Log which papers are being selected
            for i, paper in enumerate(selected):
                pmid = paper.get('pmid', 'N/A')
                is_orig = paper.get('is_original_pub', False)
                nct = paper.get('nct_id', 'N/A')
                title = (paper.get('title') or '')[:50]
                logger.info(f"  Paper {i+1}: PMID {pmid} | NCT {nct} | original={is_orig} | {title}...")
            return selected

        # APPROACH 2: Fallback to direct PubMed search
        logger.info("CT.gov approach found no papers, falling back to PubMed search")

        # Filter to exclude reviews and get clinical trials
        # NOT review[pt] excludes review articles
        exclude_reviews = "NOT review[pt] NOT meta-analysis[pt]"

        queries = [
            # Primary query: drug + disease + phase 3 (exclude reviews)
            f'"{clean_name}"[Title/Abstract] AND "{disease.standard_name}"[Title/Abstract] AND ("Phase 3"[Title/Abstract] OR "Phase III"[Title/Abstract] OR "pivotal"[Title/Abstract]) {exclude_reviews}',
            # Clinical trial publication type
            f'"{clean_name}"[Title/Abstract] AND "{disease.standard_name}"[Title/Abstract] AND ("randomized controlled trial"[pt] OR "clinical trial, phase iii"[pt])',
            # Efficacy results query (exclude reviews)
            f'"{clean_name}"[Title/Abstract] AND "{disease.standard_name}"[Title/Abstract] AND (efficacy[Title/Abstract] OR response[Title/Abstract]) {exclude_reviews}',
        ]

        # Add brand name search if available
        if drug.brand_name:
            queries.append(
                f'"{drug.brand_name}"[Title/Abstract] AND "{disease.standard_name}"[Title/Abstract] AND (trial[Title/Abstract] OR efficacy[Title/Abstract]) {exclude_reviews}'
            )

        all_papers = []
        seen_pmids = set()

        for query in queries:
            if len(all_papers) >= max_results:
                break

            # Retry logic for rate limit errors
            for retry in range(PUBMED_MAX_RETRIES):
                try:
                    papers = self.pubmed.search_and_fetch(query, max_results=max_results)
                    for paper in papers:
                        pmid = paper.get('pmid')
                        if pmid and pmid not in seen_pmids:
                            seen_pmids.add(pmid)
                            all_papers.append(paper)
                    break  # Success, exit retry loop

                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        wait_time = PUBMED_RETRY_DELAY * (retry + 1)
                        logger.warning(
                            f"PubMed rate limit hit (429). Waiting {wait_time}s before retry {retry + 1}/{PUBMED_MAX_RETRIES}"
                        )
                        time.sleep(wait_time)
                        continue
                    else:
                        logger.warning(f"PubMed search failed for query: {e}")
                        break

                except Exception as e:
                    if "429" in str(e):
                        wait_time = PUBMED_RETRY_DELAY * (retry + 1)
                        logger.warning(
                            f"PubMed rate limit hit. Waiting {wait_time}s before retry {retry + 1}/{PUBMED_MAX_RETRIES}"
                        )
                        time.sleep(wait_time)
                        continue
                    logger.warning(f"PubMed search failed for query: {e}")
                    break

            # Small delay between queries to avoid rate limits
            time.sleep(0.5)

        logger.info(
            f"Found {len(all_papers)} publications for "
            f"{drug.generic_name} in {disease.standard_name}"
        )
        return all_papers[:max_results]

    def _search_by_trial_names(
        self,
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        trials: List,  # List[DiscoveredTrial]
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search for publications using discovered trial names.

        For each trial name, search PubMed for:
        - "[trial_name] [drug_name] efficacy"
        - "[trial_name] phase 3 results"

        Args:
            drug: Drug to search for
            disease: Disease context
            trials: List of DiscoveredTrial objects
            max_results: Maximum papers to return

        Returns:
            List of papers with trial_name pre-populated
        """
        clean_name = self.clean_generic_name(drug.generic_name)
        all_papers = []
        seen_pmids = set()

        # Sort trials to prioritize pivotal Phase 3 trials
        def trial_priority(t):
            name_upper = (t.name or "").upper()
            phase = t.phase or ""

            # Priority: Phase 3 first (0), then Phase 2 (1), then others (2)
            if "PHASE3" in phase.upper().replace(" ", ""):
                phase_score = 0
            elif "PHASE2" in phase.upper().replace(" ", ""):
                phase_score = 1
            else:
                phase_score = 2

            # Deprioritize extension studies and indication-specific trials
            # These are less important than the original pivotal trials
            # Note: Keep route variants (SC, IV) as they are important for formulation data
            is_extension = any(x in name_upper for x in ["LTE", "EXTEND", "OLE", "LONG-TERM", "LONG TERM"])
            is_ln_trial = "LN" in name_upper or "NEPHRITIS" in name_upper

            # Apply penalties to push these trials down
            extension_penalty = 5 if is_extension else 0
            ln_penalty = 10 if is_ln_trial else 0

            return (ln_penalty, extension_penalty, phase_score)

        sorted_trials = sorted(trials, key=trial_priority)

        # Get named trials only (not NCT IDs)
        named_trials = [t for t in sorted_trials if t.name and not t.name.startswith("NCT")]

        # Search more trials than papers needed to ensure we get pivotal trials
        trials_to_search = min(len(named_trials), max(max_results * 2, 10))
        logger.info(f"Prioritized trials for search: {[t.name for t in named_trials[:trials_to_search]]}")

        # Search for each trial name
        for trial in named_trials[:trials_to_search]:
            trial_name = trial.name
            nct_id = trial.nct_id

            logger.info(f"Searching for trial: {trial_name} (NCT: {nct_id})")

            # Build search queries for this trial
            # IMPORTANT: NCT ID first! Primary publications often don't have trial nickname in title
            # e.g., BLISS-52 primary paper (PMID 21296403) has NCT00424476 but no "BLISS-52" in title
            queries = []

            # If we have NCT ID, search by it FIRST (most reliable for primary pubs)
            if nct_id:
                queries.append(f'"{nct_id}"[Title/Abstract]')

            # Trial name + drug
            queries.append(f'"{trial_name}"[Title/Abstract] AND "{clean_name}"[Title/Abstract]')
            # Trial name + efficacy
            queries.append(f'"{trial_name}"[Title/Abstract] AND (efficacy[Title/Abstract] OR results[Title/Abstract])')

            # Track papers found for this trial
            trial_papers = []

            for query in queries:
                try:
                    papers = self.pubmed.search_and_fetch(query, max_results=3)
                    for paper in papers:
                        pmid = paper.get('pmid')
                        if pmid and pmid not in seen_pmids:
                            seen_pmids.add(pmid)
                            # Pre-populate trial name and NCT ID
                            paper['trial_name'] = trial_name
                            paper['nct_id'] = nct_id
                            trial_papers.append(paper)
                            all_papers.append(paper)

                except Exception as e:
                    logger.warning(f"PubMed search failed for {trial_name}: {e}")

                time.sleep(0.3)  # Rate limit

                # If we found enough papers for this trial, move on
                if len(trial_papers) >= 3:
                    break

        logger.info(f"Found {len(all_papers)} papers via trial name search")

        # Filter out review papers and sort to prioritize primary publications
        # Primary publications are usually: older, have percentages in abstract, not reviews
        def paper_priority(paper):
            title = (paper.get('title') or '').lower()
            abstract = (paper.get('abstract') or '').lower()

            # Deprioritize reviews and meta-analyses
            is_review = any(term in title or term in abstract[:200] for term in
                          ['review', 'meta-analysis', 'systematic review', 'pooled analysis'])
            review_penalty = 100 if is_review else 0

            # Prefer papers with efficacy data (percentages in abstract)
            has_efficacy_data = bool(re.search(r'\d+\.?\d*%', abstract))
            efficacy_bonus = -50 if has_efficacy_data else 0

            # Prefer older papers (likely primary publications)
            try:
                year = int(paper.get('year', 2030))
            except:
                year = 2030
            year_bonus = year - 2000  # Older papers get lower scores

            return (review_penalty, efficacy_bonus, year_bonus)

        # Sort papers by priority
        sorted_papers = sorted(all_papers, key=paper_priority)

        # CRITICAL: Ensure at least one paper per discovered trial is selected
        # This prevents missing trials like TULIP-SC, BLISS-76 due to paper limits
        selected = []
        seen_trials = set()

        # First pass: Get best paper from EACH unique trial (regardless of max_results)
        for paper in sorted_papers:
            t_name = paper.get('trial_name')
            if t_name and t_name not in seen_trials:
                selected.append(paper)
                seen_trials.add(t_name)

        logger.info(f"Selected {len(selected)} papers (one per trial: {list(seen_trials)})")

        # Second pass: Fill remaining slots up to max_results with additional papers
        if len(selected) < max_results:
            for paper in sorted_papers:
                if paper not in selected:
                    selected.append(paper)
                    if len(selected) >= max_results:
                        break

        # Note: We may return MORE than max_results to ensure trial coverage
        # This is intentional - it's better to extract more than miss trials
        return selected

    def extract_from_papers(
        self,
        papers: List[Dict[str, Any]],
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        expected_endpoints: List[str]
    ) -> List[EfficacyDataPoint]:
        """
        Extract efficacy data from a list of papers using Claude.

        Args:
            papers: List of paper dictionaries from PubMed
            drug: Drug being extracted
            disease: Disease context
            expected_endpoints: List of expected endpoint names

        Returns:
            List of EfficacyDataPoint objects
        """
        all_data_points = []

        for paper in papers:
            try:
                data_points = self._extract_from_single_paper(
                    paper, drug, disease, expected_endpoints
                )
                all_data_points.extend(data_points)
            except Exception as e:
                logger.error(f"Failed to extract from paper {paper.get('pmid')}: {e}")
                continue

        return all_data_points

    def _extract_from_single_paper(
        self,
        paper: Dict[str, Any],
        drug: ApprovedDrug,
        disease: DiseaseMatch,
        expected_endpoints: List[str]
    ) -> List[EfficacyDataPoint]:
        """
        Extract efficacy data from a single paper.

        Uses full text from PMC if available, otherwise falls back to abstract.
        """
        pmid = paper.get('pmid', 'Unknown')
        abstract = paper.get('abstract', '')

        # Try to get full text if available
        # Note: _parse_pmc_fulltext returns 'content' not 'full_content'
        full_content = paper.get('content', '') or paper.get('full_content', '')
        tables = paper.get('tables', [])
        sections = paper.get('sections', [])
        is_full_text = bool(full_content and len(full_content) > len(abstract) * 2)

        # If no full text in paper dict, try to fetch from PMC
        doi = paper.get('doi')
        if not is_full_text and pmid != 'Unknown':
            try:
                # Check PMC availability and download if open access
                pmc_map = self.pubmed.check_pmc_availability([pmid])
                pmcid = pmc_map.get(pmid)
                if pmcid:
                    logger.info(f"Paper {pmid} is open access (PMCID: {pmcid}), fetching full text...")
                    pmc_xml = self.pubmed.fetch_pmc_fulltext(pmcid)
                    if pmc_xml:
                        parsed = self.pubmed._parse_pmc_fulltext(pmc_xml, pmid, pmcid)
                        if parsed:
                            # Use 'content' field from PMC parser
                            full_content = parsed.get('content', '')
                            tables = parsed.get('tables', [])
                            sections = parsed.get('sections', [])
                            is_full_text = bool(full_content and len(full_content) > 500)
                            if is_full_text:
                                logger.info(f"Successfully extracted full text for {pmid} ({len(full_content)} chars, {len(tables)} tables, {len(sections)} sections)")
                else:
                    # PMC not available - log DOI if available for manual access
                    if doi:
                        logger.info(
                            f"Paper {pmid} not in PMC - full text may be available via DOI: https://doi.org/{doi}"
                        )
                    else:
                        logger.debug(f"Paper {pmid} not in PMC and no DOI available")
            except Exception as e:
                logger.debug(f"Could not fetch full text for {pmid}: {e}")

        if not abstract and not full_content:
            logger.debug(f"Paper {pmid} has no content")
            return []

        # Build paper context
        authors = paper.get('authors', [])
        author_str = ', '.join(authors[:3]) + ' et al.' if len(authors) > 3 else ', '.join(authors)

        # Use full text if available, otherwise abstract
        if is_full_text:
            # For full text, focus on Results section and tables
            content_for_extraction = self._prepare_full_text_for_extraction(full_content, tables, sections)
            source_type = "Full Text (Open Access)"
        else:
            content_for_extraction = abstract
            source_type = "Abstract"

        paper_text = f"""
Title: {paper.get('title', 'N/A')}
Authors: {author_str}
Journal: {paper.get('journal', 'N/A')} ({paper.get('year', 'N/A')})
PMID: {pmid}
Source: {source_type}

{content_for_extraction}
"""

        # Build extraction prompt
        prompt = f"""Extract efficacy data for {drug.generic_name} ({drug.brand_name or 'no brand name'}) treating {disease.standard_name}.

Look specifically for these endpoints: {', '.join(expected_endpoints[:10])}
But also extract any other efficacy endpoints mentioned.

Paper content:
{paper_text}

Return a JSON array of efficacy endpoints. Example format:
[
  {{
    "endpoint_name": "SRI-4",
    "endpoint_type": "primary",
    "drug_arm_name": "Belimumab 10 mg/kg",
    "drug_arm_result": 52.4,
    "drug_arm_result_unit": "%",
    "drug_arm_n": 223,
    "comparator_arm_name": "Placebo",
    "comparator_arm_type": "placebo",
    "comparator_arm_result": 30.9,
    "comparator_arm_n": 226,
    "p_value": 0.001,
    "confidence_interval": null,
    "timepoint": "Week 52",
    "trial_name": "BLISS-52",
    "nct_id": "NCT00424476",
    "trial_phase": "Phase 3",
    "source_text": "At Week 52, 52.4% of patients receiving belimumab 10 mg/kg achieved SRI-4 vs 30.9% placebo (p<0.001)"
  }}
]

Return ONLY valid JSON array (no markdown, no explanation):"""

        try:
            response = self.anthropic.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                system=self.EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )

            raw_response = response.content[0].text
            result_text = self._clean_json_response(raw_response)

            logger.debug(f"Claude raw response ({len(raw_response)} chars): {raw_response[:500]}...")

            if not result_text or result_text == "[]":
                logger.info(f"No efficacy data found in paper {pmid}")
                return []

            parsed_data = json.loads(result_text)

            if not isinstance(parsed_data, list):
                logger.warning(f"Unexpected response format from paper {pmid}")
                return []

            # Get NCT ID and trial name (once per paper, not per endpoint)
            import re

            # Check if trial_name was pre-populated (from trial discovery search)
            default_trial_name = paper.get('trial_name')
            nct_id = paper.get('nct_id')

            # If not pre-populated, try to extract NCT ID from abstract
            if not nct_id:
                nct_match = re.search(r'(NCT\d{8})', abstract, re.IGNORECASE)
                if nct_match:
                    nct_id = nct_match.group(1).upper()
                    logger.debug(f"Extracted NCT ID from abstract: {nct_id}")

            # If trial name not pre-populated, try to get from CT.gov or extract
            ct_brief_title = None
            if not default_trial_name and nct_id:
                try:
                    trial_details = self.ct_api.get_study_details(nct_id)
                    if trial_details:
                        id_module = trial_details.get('protocolSection', {}).get('identificationModule', {})
                        # Use official acronym field first (most reliable)
                        default_trial_name = id_module.get('acronym')
                        ct_brief_title = id_module.get('briefTitle', '')
                except Exception:
                    pass

            # Import TrialNameExtractor for sophisticated trial name extraction
            from src.agents.trial_name_extractor import TrialNameExtractor

            # Source 2: Use TrialNameExtractor on paper title + abstract
            if not default_trial_name:
                paper_title = paper.get('title', '')
                search_text = f"{paper_title} {abstract}"
                # Lower confidence threshold to catch TULIP-1, TULIP-2, etc.
                extracted_names = TrialNameExtractor.extract_from_text(search_text, min_confidence=0.3)
                if extracted_names:
                    # Prefer names with numbers (TULIP-1 over TULIP)
                    names_with_numbers = [n for n in extracted_names if any(c.isdigit() for c in n)]
                    if names_with_numbers:
                        default_trial_name = sorted(names_with_numbers)[0]
                    else:
                        default_trial_name = sorted(extracted_names)[0]
                    logger.debug(f"Extracted trial name '{default_trial_name}' from paper text")

            # Source 3: Fall back to CT.gov brief title, NCT ID, or paper title
            if not default_trial_name:
                if ct_brief_title:
                    default_trial_name = ct_brief_title[:60]
                elif nct_id:
                    default_trial_name = nct_id
                else:
                    default_trial_name = paper.get('title', '')[:60] or 'Unknown Trial'

            # Convert to EfficacyDataPoint objects
            data_points = []
            for item in parsed_data:
                if not item.get('endpoint_name'):
                    continue

                # Prioritize pre-populated trial name from discovery service
                # Only use Claude's extracted name if no pre-populated name available
                pre_populated_trial = paper.get('trial_name')
                if pre_populated_trial:
                    # Trust the discovered trial name over Claude's extraction
                    trial_name = pre_populated_trial
                else:
                    # Validate Claude-extracted trial name
                    claude_trial_name = item.get('trial_name')
                    if claude_trial_name:
                        # Reject obvious false positives (common words, phrases)
                        invalid_patterns = ['EITHER', 'FINDINGS', 'RESULTS', 'STUDY', 'TRIAL',
                                           'PATIENTS', 'TREATMENT', 'ACTIVE', 'PLACEBO']
                        is_valid = not any(p in claude_trial_name.upper() for p in invalid_patterns)
                        # Also require it looks like a trial name (has number OR is known pattern)
                        has_number = any(c.isdigit() for c in claude_trial_name)
                        is_short_acronym = len(claude_trial_name) <= 10 and claude_trial_name.isupper()
                        if is_valid and (has_number or is_short_acronym):
                            trial_name = claude_trial_name
                        else:
                            trial_name = default_trial_name
                    else:
                        trial_name = default_trial_name

                # Prioritize pre-populated NCT ID from discovery over Claude's extraction
                # (Claude might extract combined IDs from pooled analysis papers)
                extracted_nct = nct_id or item.get('nct_id')

                data_point = EfficacyDataPoint(
                    source_type=DataSource.PUBLICATION,
                    source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    pmid=pmid,
                    nct_id=extracted_nct,
                    trial_name=trial_name,
                    trial_phase=item.get('trial_phase'),
                    endpoint_name=item.get('endpoint_name', ''),
                    endpoint_type=item.get('endpoint_type'),
                    drug_arm_name=item.get('drug_arm_name') or drug.generic_name,
                    drug_arm_n=self._safe_int(item.get('drug_arm_n')),
                    drug_arm_result=self._safe_float(item.get('drug_arm_result')),
                    drug_arm_result_unit=item.get('drug_arm_result_unit', '%'),
                    comparator_arm_name=item.get('comparator_arm_name'),
                    comparator_arm_n=self._safe_int(item.get('comparator_arm_n')),
                    comparator_arm_result=self._safe_float(item.get('comparator_arm_result')),
                    p_value=self._safe_float(item.get('p_value')),
                    confidence_interval=item.get('confidence_interval'),
                    timepoint=item.get('timepoint'),
                    disease_mesh_id=disease.mesh_id,
                    indication_name=disease.standard_name,
                    raw_source_text=item.get('source_text'),
                )

                data_points.append(data_point)

            logger.info(f"Extracted {len(data_points)} endpoints from paper {pmid}")
            return data_points

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for paper {pmid}: {e}")
            return []
        except Exception as e:
            logger.error(f"Extraction error for paper {pmid}: {e}")
            return []

    def _clean_json_response(self, text: str) -> str:
        """Clean JSON from Claude response, handling truncation."""
        text = text.strip()

        # Remove markdown code blocks
        if "```" in text:
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if match:
                text = match.group(1).strip()

        # Find JSON array boundaries
        start_idx = text.find('[')
        end_idx = text.rfind(']')

        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx:end_idx + 1]
        elif start_idx != -1:
            # Truncated response - try to repair
            text = self._repair_truncated_json(text[start_idx:])

        return text

    def _repair_truncated_json(self, text: str) -> str:
        """
        Attempt to repair truncated JSON array.

        Handles cases where Claude's response is cut off mid-JSON.
        Tries to extract complete objects from the partial response.
        """
        if not text.startswith('['):
            return "[]"

        # Find the last complete object (ends with })
        last_complete = -1
        brace_count = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(text):
            if escape_next:
                escape_next = False
                continue

            if char == '\\':
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    last_complete = i

        if last_complete > 0:
            # Extract up to the last complete object
            repaired = text[:last_complete + 1]

            # Clean up trailing comma if present and close the array
            repaired = repaired.rstrip()
            if repaired.endswith(','):
                repaired = repaired[:-1]
            repaired = repaired + ']'

            logger.warning(f"Repaired truncated JSON: extracted {repaired.count('{}')} complete objects")
            return repaired

        # No complete objects found
        logger.warning("Could not repair truncated JSON - no complete objects found")
        return "[]"

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert to float."""
        if value is None:
            return None
        try:
            # Handle string values like "<0.001"
            if isinstance(value, str):
                value = value.replace('<', '').replace('>', '').strip()
            return float(value)
        except (ValueError, TypeError):
            return None

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert to int."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _prepare_full_text_for_extraction(
        self,
        full_content: str,
        tables: List[Dict[str, Any]],
        pmc_sections: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Prepare full-text content for efficacy extraction.

        Focuses on the most relevant sections (Results, Discussion) and efficacy tables.
        Leverages PMC section detection when available for better accuracy.
        Limits total length to avoid overwhelming the LLM.

        Args:
            full_content: Full paper content
            tables: List of parsed tables from the paper
            pmc_sections: Optional list of sections from PMC XML parser

        Returns:
            Prepared content string optimized for efficacy extraction
        """
        max_content_length = 15000  # Limit to ~15K chars to stay within context
        output_sections = []

        results_text = ""

        # Method 1: Use PMC sections if available (more reliable)
        # PMC sections is a dict: {section_key: {title, paragraphs, subsections}}
        if pmc_sections and isinstance(pmc_sections, dict):
            for section_key, section_data in pmc_sections.items():
                section_title = section_data.get('title', '').lower()
                section_paragraphs = section_data.get('paragraphs', [])
                section_text = ' '.join(section_paragraphs) if section_paragraphs else ''

                # Look for Results section
                if 'result' in section_key or 'result' in section_title:
                    results_text += section_text + "\n\n"
                # Also include Discussion which often has efficacy summaries
                elif 'discussion' in section_key or 'discussion' in section_title:
                    # Only add first part of discussion
                    results_text += section_text[:2000] + "\n\n"

        # Method 2: Fall back to regex extraction if no PMC sections
        if not results_text:
            results_patterns = [
                r'(?:^|\n)(?:RESULTS?|Results?)\s*\n([\s\S]*?)(?=\n(?:DISCUSSION|Discussion|CONCLUSIONS?|Conclusions?|METHODS?|Methods?|REFERENCES?|References?)|\Z)',
                r'(?:^|\n)(?:3\.|III\.?)\s*(?:RESULTS?|Results?)\s*\n([\s\S]*?)(?=\n(?:4\.|IV\.|DISCUSSION)|\Z)',
            ]

            for pattern in results_patterns:
                match = re.search(pattern, full_content, re.IGNORECASE)
                if match:
                    results_text = match.group(1).strip()
                    break

        if results_text:
            output_sections.append(f"RESULTS SECTION:\n{results_text[:8000]}")

        # Add efficacy-related tables (crucial for data extraction)
        # Score tables by relevance to efficacy data
        table_scores = []
        for table in tables:
            label = table.get('label', '').lower()
            caption = table.get('caption', '').lower()
            content = table.get('content', '').lower()
            combined = f"{label} {caption} {content[:500]}"  # First 500 chars for scoring

            score = 0

            # High-value efficacy keywords (strong signal)
            efficacy_keywords = ['efficacy', 'endpoint', 'response', 'responder', 'crr',
                                'prr', 'sri-4', 'bicla', 'acr20', 'acr50', 'acr70',
                                'das28', 'remission', 'pasi', 'complete']
            score += sum(3 for kw in efficacy_keywords if kw in combined)

            # Moderate-value keywords
            moderate_keywords = ['primary', 'secondary', 'week 52', 'week 104', 'placebo',
                               'treatment', 'outcome', 'improvement', 'difference']
            score += sum(2 for kw in moderate_keywords if kw in combined)

            # Negative keywords (demographics, safety - less relevant for efficacy)
            negative_keywords = ['demographic', 'baseline characteristic', 'age,',
                               'adverse event', 'safety', 'sex,', 'race,']
            score -= sum(3 for kw in negative_keywords if kw in combined)

            table_scores.append((score, table))

        # Sort by score descending
        table_scores.sort(key=lambda x: x[0], reverse=True)

        # Include top tables (prioritize efficacy tables)
        efficacy_tables = []
        for score, table in table_scores[:4]:
            content = table.get('content', '')
            if content:
                table_text = f"\n{table.get('label', 'Table')}: {table.get('caption', '')}\n{content}"
                efficacy_tables.append(table_text)
                logger.debug(f"Including table '{table.get('label')}' with score {score}")

        if efficacy_tables:
            tables_section = "\n\nEFFICACY TABLES:\n" + "\n".join(efficacy_tables[:4])  # Include up to 4 tables
            output_sections.append(tables_section[:6000])

        # If no Results section found, use a portion of full content
        if not results_text:
            # Look for efficacy data patterns in full content
            efficacy_portion = full_content[:10000]
            output_sections.append(f"PAPER CONTENT:\n{efficacy_portion}")

        combined = "\n\n".join(output_sections)

        # Final length check
        if len(combined) > max_content_length:
            combined = combined[:max_content_length] + "\n\n[Content truncated...]"

        return combined
