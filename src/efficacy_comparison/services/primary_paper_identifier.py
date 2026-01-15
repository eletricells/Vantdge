"""
PrimaryPaperIdentifier Service

Finds and screens primary results papers for pivotal clinical trials.
Uses multiple methods: CT.gov linked publications, PubMed search, Haiku screening.
"""

import logging
import re
from typing import Dict, List, Optional

import anthropic

from src.tools.pubmed import PubMedAPI
from src.utils.config import get_settings
from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
from src.efficacy_comparison.models import (
    ApprovedDrug,
    IdentifiedPaper,
    PaperScreeningResult,
    PivotalTrial,
)

logger = logging.getLogger(__name__)


# Haiku model for fast, cheap screening
SCREENING_MODEL = "claude-3-5-haiku-20241022"

# Screening prompt template
PAPER_SCREENING_PROMPT = """You are screening a scientific paper to determine if it is the PRIMARY RESULTS publication for a pivotal clinical trial.

Drug: {drug_name} ({generic_name})
Trial Name: {trial_name}
NCT ID: {nct_id}

Paper Information:
- Title: {title}
- Authors: {authors}
- Journal: {journal}
- Year: {year}
- Abstract: {abstract}

Your task is to determine:

1. **Is this the PRIMARY RESULTS paper for this trial?**
   - Primary results = First publication reporting the main efficacy endpoints
   - NOT: Post-hoc analyses, subgroup analyses, extension studies, pooled analyses, meta-analyses, reviews

2. **Does this paper report EFFICACY ENDPOINTS?**
   - Response rates, disease activity scores, patient-reported outcomes
   - NOT: Study design papers, protocol papers, safety-only papers

3. **Is this from a PIVOTAL/REGISTRATION TRIAL?**
   - Phase 2b or Phase 3 trial designed to support regulatory approval
   - Typically large, randomized, placebo-controlled

4. **What is the primary endpoint reported?** (if identifiable)

5. **Confidence score (0.0-1.0)** that this is the correct paper to extract efficacy data from.

Consider these red flags that suggest this is NOT the primary results paper:
- Title mentions "subgroup", "post-hoc", "pooled", "meta-analysis", "review", "long-term extension"
- Title mentions specific patient populations (e.g., "Asian patients", "elderly patients")
- Paper is much newer than approval date (suggests secondary analysis)
- Abstract focuses on safety only or study methodology

Return your assessment as JSON:
{{
    "is_primary_results": true/false,
    "reports_efficacy": true/false,
    "is_pivotal_trial": true/false,
    "primary_endpoint": "string or null",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation (1-2 sentences)"
}}

Return ONLY the JSON, no other text."""


class PrimaryPaperIdentifier:
    """
    Identifies primary results papers for pivotal trials.

    Uses multiple methods:
    1. ClinicalTrials.gov linked publications (type=RESULT)
    2. PubMed search by trial name
    3. PubMed search by NCT ID
    4. Haiku screening to confirm primary results

    Only returns papers that pass screening with confidence >= threshold.
    """

    def __init__(
        self,
        pubmed_api: Optional[PubMedAPI] = None,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None,
        anthropic_client: Optional[anthropic.Anthropic] = None,
        confidence_threshold: float = 0.7,
    ):
        """
        Initialize the service.

        Args:
            pubmed_api: Optional PubMed API instance
            clinicaltrials_client: Optional CT.gov client
            anthropic_client: Optional Anthropic client for Haiku
            confidence_threshold: Minimum confidence to accept a paper
        """
        self.pubmed = pubmed_api or PubMedAPI()
        self.ctgov = clinicaltrials_client or ClinicalTrialsClient()
        if anthropic_client:
            self.anthropic = anthropic_client
        else:
            settings = get_settings()
            self.anthropic = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.confidence_threshold = confidence_threshold

    async def find_primary_papers(
        self,
        trial: PivotalTrial,
        drug: ApprovedDrug,
        max_papers: int = 2,
    ) -> List[IdentifiedPaper]:
        """
        Find primary results papers for a pivotal trial.

        Args:
            trial: PivotalTrial to find papers for
            drug: ApprovedDrug with drug information
            max_papers: Maximum papers to return (typically 1-2)

        Returns:
            List of IdentifiedPaper objects that passed screening
        """
        logger.info(
            f"Finding primary papers for trial: {trial.trial_name or trial.nct_id}"
        )

        all_papers: List[IdentifiedPaper] = []
        seen_pmids: set = set()

        # Method 1: Get linked publications from ClinicalTrials.gov
        if trial.nct_id:
            ctgov_papers = await self._get_ctgov_linked_papers(trial.nct_id)
            for paper in ctgov_papers:
                if paper.pmid not in seen_pmids:
                    all_papers.append(paper)
                    seen_pmids.add(paper.pmid)

        # Method 2: Search PubMed by trial name
        if trial.trial_name:
            pubmed_papers = await self._search_pubmed_by_trial_name(
                trial.trial_name, drug
            )
            for paper in pubmed_papers:
                if paper.pmid not in seen_pmids:
                    all_papers.append(paper)
                    seen_pmids.add(paper.pmid)

        # Method 3: Search PubMed by NCT ID
        if trial.nct_id:
            nct_papers = await self._search_pubmed_by_nct(trial.nct_id)
            for paper in nct_papers:
                if paper.pmid not in seen_pmids:
                    all_papers.append(paper)
                    seen_pmids.add(paper.pmid)

        if not all_papers:
            logger.warning(
                f"No papers found for trial: {trial.trial_name or trial.nct_id}"
            )
            return []

        logger.info(f"Found {len(all_papers)} candidate papers, screening...")

        # Screen each paper with Haiku
        screened_papers = []
        for paper in all_papers:
            paper.trial_name = trial.trial_name
            paper.nct_id = trial.nct_id

            screening_result = await self._screen_paper(paper, trial, drug)
            paper.screening_result = screening_result

            if (screening_result.is_primary_results and
                screening_result.confidence >= self.confidence_threshold):
                screened_papers.append(paper)
                logger.debug(
                    f"Paper passed screening: {paper.pmid} (confidence: {screening_result.confidence:.2f})"
                )
            else:
                logger.debug(
                    f"Paper failed screening: {paper.pmid} - {screening_result.reasoning}"
                )

        # Sort by confidence (highest first)
        screened_papers.sort(
            key=lambda p: p.screening_result.confidence if p.screening_result else 0,
            reverse=True,
        )

        result = screened_papers[:max_papers]
        logger.info(f"Returning {len(result)} primary papers for {trial.trial_name or trial.nct_id}")

        return result

    async def _get_ctgov_linked_papers(self, nct_id: str) -> List[IdentifiedPaper]:
        """
        Get publications linked to a trial on ClinicalTrials.gov.

        Prioritizes publications with type="RESULT".
        """
        papers = []

        try:
            study = self.ctgov.get_trial_by_nct(nct_id)
            if not study:
                return papers

            # Get references module
            protocol = study.get("protocolSection", {})
            refs_module = protocol.get("referencesModule", {})
            references = refs_module.get("references", [])

            # Filter and prioritize RESULT type publications
            result_refs = []
            other_refs = []

            for ref in references:
                ref_type = ref.get("type", "")
                pmid = ref.get("pmid")

                if not pmid:
                    continue

                if ref_type == "RESULT":
                    result_refs.append(ref)
                elif ref_type != "BACKGROUND":  # Skip BACKGROUND papers
                    other_refs.append(ref)

            # Process RESULT papers first, then others
            for ref in result_refs + other_refs[:3]:  # Limit to prevent too many
                pmid = ref.get("pmid")
                if pmid:
                    paper = await self._fetch_pubmed_details(pmid)
                    if paper:
                        papers.append(paper)

        except Exception as e:
            logger.error(f"Error getting CT.gov linked papers for {nct_id}: {e}")

        return papers

    async def _search_pubmed_by_trial_name(
        self,
        trial_name: str,
        drug: ApprovedDrug,
    ) -> List[IdentifiedPaper]:
        """
        Search PubMed for papers mentioning the trial name.
        """
        papers = []

        try:
            # Build search query
            # Try multiple query formats
            queries = [
                f'"{trial_name}"[Title] AND {drug.generic_name}',
                f'"{trial_name}" AND {drug.generic_name} AND (efficacy OR results)',
            ]

            for query in queries:
                pmids = self.pubmed.search(query, max_results=5)
                if pmids:
                    for pmid in pmids[:3]:
                        paper = await self._fetch_pubmed_details(str(pmid))
                        if paper:
                            papers.append(paper)
                    break  # Stop if we found results

        except Exception as e:
            logger.error(f"Error searching PubMed by trial name: {e}")

        return papers

    async def _search_pubmed_by_nct(self, nct_id: str) -> List[IdentifiedPaper]:
        """
        Search PubMed for papers mentioning the NCT ID.
        """
        papers = []

        try:
            # NCT IDs are sometimes mentioned in abstracts
            pmids = self.pubmed.search(nct_id, max_results=5)
            if pmids:
                for pmid in pmids[:3]:
                    paper = await self._fetch_pubmed_details(str(pmid))
                    if paper:
                        papers.append(paper)

        except Exception as e:
            logger.error(f"Error searching PubMed by NCT ID: {e}")

        return papers

    async def _fetch_pubmed_details(self, pmid: str) -> Optional[IdentifiedPaper]:
        """
        Fetch paper details from PubMed.
        """
        try:
            # Use fetch_abstracts which returns parsed article data
            articles = self.pubmed.fetch_abstracts([pmid])
            if not articles:
                return None

            article = articles[0]

            # Check for PMC ID (open access) using check_pmc_availability
            pmc_map = self.pubmed.check_pmc_availability([pmid])
            pmc_id = pmc_map.get(pmid)
            is_open_access = pmc_id is not None

            # Get publication year - fetch_abstracts returns year directly
            year = article.get("year")
            if year and year != "Unknown":
                try:
                    year = int(year)
                except (ValueError, TypeError):
                    year = None
            else:
                year = None

            # Get first author name
            authors = article.get("authors", [])
            first_author = authors[0] if authors else None

            return IdentifiedPaper(
                pmid=pmid,
                title=article.get("title", ""),
                authors=first_author,
                journal=article.get("journal", ""),
                year=year,
                abstract=article.get("abstract", ""),
                is_open_access=is_open_access,
                pmc_id=pmc_id,
            )

        except Exception as e:
            logger.error(f"Error fetching PubMed details for {pmid}: {e}")
            return None

    async def _screen_paper(
        self,
        paper: IdentifiedPaper,
        trial: PivotalTrial,
        drug: ApprovedDrug,
    ) -> PaperScreeningResult:
        """
        Screen a paper with Haiku to determine if it's the primary results paper.
        """
        try:
            prompt = PAPER_SCREENING_PROMPT.format(
                drug_name=drug.drug_name,
                generic_name=drug.generic_name,
                trial_name=trial.trial_name or "Unknown",
                nct_id=trial.nct_id or "Unknown",
                title=paper.title or "Unknown",
                authors=paper.authors or "Unknown",
                journal=paper.journal or "Unknown",
                year=paper.year or "Unknown",
                abstract=paper.abstract or "No abstract available",
            )

            response = self.anthropic.messages.create(
                model=SCREENING_MODEL,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse JSON response
            response_text = response.content[0].text.strip()

            # Clean up response (remove markdown if present)
            if response_text.startswith("```"):
                response_text = re.sub(r"```json?\n?", "", response_text)
                response_text = response_text.rstrip("`")

            import json
            result = json.loads(response_text)

            return PaperScreeningResult(
                is_primary_results=result.get("is_primary_results", False),
                reports_efficacy=result.get("reports_efficacy", False),
                is_pivotal_trial=result.get("is_pivotal_trial", False),
                primary_endpoint=result.get("primary_endpoint"),
                confidence=result.get("confidence", 0.0),
                reasoning=result.get("reasoning"),
            )

        except Exception as e:
            logger.error(f"Error screening paper {paper.pmid}: {e}")
            # Return a low-confidence result on error
            return PaperScreeningResult(
                is_primary_results=False,
                reports_efficacy=False,
                is_pivotal_trial=False,
                confidence=0.0,
                reasoning=f"Screening failed: {str(e)}",
            )

    def quick_filter(self, paper: IdentifiedPaper) -> bool:
        """
        Quick heuristic filter before LLM screening.

        Returns False for papers that are obviously not primary results.
        """
        title_lower = (paper.title or "").lower()

        # Red flag keywords in title
        red_flags = [
            "meta-analysis", "meta analysis", "systematic review",
            "pooled analysis", "pooled data", "subgroup analysis",
            "post-hoc", "post hoc", "posthoc",
            "long-term extension", "open-label extension", "extension study",
            "protocol", "study design", "rationale",
            "real-world", "real world", "registry",
            "safety profile", "safety analysis",
            "patient-reported outcomes only",
            "in asian", "in japanese", "in chinese", "in elderly",
            "in pediatric", "in adolescents",
        ]

        for flag in red_flags:
            if flag in title_lower:
                return False

        return True
