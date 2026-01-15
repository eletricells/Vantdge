"""
Disease Intelligence Service - Main orchestrator for populating disease data.

Uses multi-source literature search (PubMed, Semantic Scholar, Web) with LLM extraction,
following the same rigorous approach as case series analysis.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from jinja2 import Environment, FileSystemLoader

from .models import (
    DiseaseIntelligence,
    PrevalenceData,
    PrevalenceEstimate,
    PatientSegmentation,
    TreatmentParadigm,
    TreatmentLine,
    TreatmentDrug,
    TreatmentEstimate,
    FailureRates,
    FailureRateEstimate,
    MarketFunnel,
    DiseaseSource,
    SeverityBreakdown,
    Subpopulation,
)
import statistics
from .repository import DiseaseIntelligenceRepository

# Import PipelineDrug for hybrid treatment paradigm (optional dependency)
try:
    from ..pipeline_intelligence.models import PipelineDrug
    PIPELINE_DRUG_AVAILABLE = True
except ImportError:
    PIPELINE_DRUG_AVAILABLE = False
    PipelineDrug = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class ExtractionLog:
    """Log of LLM extraction for debugging and auditing."""
    extraction_id: str
    disease_name: str
    data_type: str  # "prevalence", "treatment", "failure_rates"
    model_used: str
    prompt_template: str
    input_sources: List[str]  # Titles or PMIDs
    raw_llm_response: str
    parsed_output: Dict[str, Any]
    validation_warnings: List[str] = field(default_factory=list)
    extraction_timestamp: datetime = field(default_factory=datetime.now)
    processing_time_seconds: float = 0.0


def calculate_weighted_consensus(
    estimates: List[PrevalenceEstimate],
    recency_boost_year: int = 2020
) -> Dict[str, Any]:
    """
    Calculate consensus prevalence with quality and recency weighting.

    Args:
        estimates: List of prevalence estimates from different sources
        recency_boost_year: Studies from this year onward get 1.5x weight

    Returns:
        Dict with median, weighted_mean, range, and confidence assessment
    """
    if not estimates:
        return {"median": None, "confidence": "Low", "confidence_rationale": "No estimates available"}

    # Quality weights
    tier_weights = {"Tier 1": 3.0, "Tier 2": 2.0, "Tier 3": 1.0}

    weighted_values = []
    raw_values = []

    for est in estimates:
        if not est.total_patients:
            continue

        # Only use prevalence estimates, not incidence
        if est.estimate_type and est.estimate_type == "incidence":
            continue

        raw_values.append(est.total_patients)

        # Base weight from quality tier
        weight = tier_weights.get(est.quality_tier, 1.0)

        # Recency boost
        if est.data_year and est.data_year >= recency_boost_year:
            weight *= 1.5

        # Large study boost (if we have study population N)
        if est.study_population_n:
            if est.study_population_n > 10_000_000:
                weight *= 1.3
            elif est.study_population_n > 1_000_000:
                weight *= 1.1

        # Add weighted copies for weighted median calculation
        weighted_values.extend([est.total_patients] * int(weight * 10))

    if not raw_values:
        return {"median": None, "confidence": "Low", "confidence_rationale": "No valid prevalence estimates"}

    # Calculate metrics
    simple_median = int(statistics.median(raw_values))
    weighted_median = int(statistics.median(weighted_values)) if weighted_values else simple_median

    # Assess confidence based on agreement
    cv = statistics.stdev(raw_values) / statistics.mean(raw_values) if len(raw_values) > 1 else 0
    tier1_count = sum(1 for e in estimates if e.quality_tier == "Tier 1" and e.total_patients)

    if tier1_count >= 2 and cv < 0.3:
        confidence = "High"
        confidence_rationale = f"{tier1_count} Tier-1 sources agree within 30% CV"
    elif tier1_count >= 1 and cv < 0.5:
        confidence = "Medium"
        confidence_rationale = f"Tier-1 source available, {cv:.0%} CV across estimates"
    else:
        confidence = "Low"
        confidence_rationale = f"No Tier-1 sources or high variability ({cv:.0%} CV)"

    return {
        "simple_median": simple_median,
        "weighted_median": weighted_median,
        "recommended_estimate": weighted_median,
        "range_low": min(raw_values),
        "range_high": max(raw_values),
        "estimate_count": len(raw_values),
        "tier1_count": tier1_count,
        "coefficient_of_variation": round(cv, 3) if len(raw_values) > 1 else 0,
        "confidence": confidence,
        "confidence_rationale": confidence_rationale,
    }


def validate_extraction(
    disease_name: str,
    prevalence_data: Dict,
    failure_data: Dict,
    treatment_data: Dict
) -> List[Dict[str, Any]]:
    """
    Validate extracted data for consistency and plausibility.

    Returns:
        List of validation warnings/errors
    """
    issues = []

    # Prevalence validation
    prev_estimates = prevalence_data.get("source_estimates", [])
    prev_values = [e.get("total_patients") for e in prev_estimates if e.get("total_patients")]

    if prev_values:
        # Check for extreme outliers (>10x range)
        if len(prev_values) > 1 and max(prev_values) / min(prev_values) > 10:
            issues.append({
                "severity": "warning",
                "field": "prevalence",
                "message": f"Wide prevalence range: {min(prev_values):,} to {max(prev_values):,} (>10x spread)",
                "action": "Review sources for methodology differences or extraction errors"
            })

        # Sanity check vs rare disease threshold
        median_prev = statistics.median(prev_values)
        if "rare" in disease_name.lower() and median_prev > 200_000:
            issues.append({
                "severity": "warning",
                "field": "prevalence",
                "message": f"High prevalence ({median_prev:,}) for disease labeled 'rare'",
                "action": "Verify disease classification or prevalence data"
            })

        # Check for suspiciously round numbers (possible estimates vs real data)
        round_count = sum(1 for v in prev_values if v % 10000 == 0)
        if round_count == len(prev_values) and len(prev_values) > 1:
            issues.append({
                "severity": "info",
                "field": "prevalence",
                "message": "All estimates are round numbers - may be rough estimates",
                "action": "Look for more precise data sources"
            })
    else:
        issues.append({
            "severity": "warning",
            "field": "prevalence",
            "message": "No prevalence estimates extracted",
            "action": "Check search results and extraction prompt"
        })

    # Failure rate validation
    fail_estimates = failure_data.get("source_estimates", [])
    fail_values = [e.get("fail_rate_pct") for e in fail_estimates if e.get("fail_rate_pct") is not None]

    if fail_values:
        # Check for impossible values
        invalid = [v for v in fail_values if v < 0 or v > 100]
        if invalid:
            issues.append({
                "severity": "error",
                "field": "failure_rates",
                "message": f"Invalid failure rate values: {invalid}",
                "action": "Extraction error - rates must be 0-100%"
            })

        # Check for extreme variability
        if len(fail_values) > 1:
            if max(fail_values) - min(fail_values) > 50:
                issues.append({
                    "severity": "warning",
                    "field": "failure_rates",
                    "message": f"High variability in failure rates: {min(fail_values):.0f}% to {max(fail_values):.0f}%",
                    "action": "Check if studies use different failure definitions or timepoints"
                })
    else:
        issues.append({
            "severity": "warning",
            "field": "failure_rates",
            "message": "No failure rate estimates extracted - critical gap for market sizing",
            "action": "Expand search queries or check paper relevance"
        })

    # Cross-field validation
    pct_treated = treatment_data.get("segmentation", {}).get("pct_treated")
    if pct_treated is not None:
        if pct_treated > 100:
            issues.append({
                "severity": "error",
                "field": "segmentation",
                "message": f"Invalid pct_treated: {pct_treated}%",
                "action": "Extraction error - must be 0-100%"
            })
        elif pct_treated < 20:
            issues.append({
                "severity": "info",
                "field": "segmentation",
                "message": f"Low treatment rate ({pct_treated}%) - verify this is disease-specific",
                "action": "Confirm data refers to relevant treatment type"
            })

    return issues


@dataclass
class Paper:
    """Represents a paper/source from literature search."""
    title: str
    authors: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[int] = None
    abstract: Optional[str] = None
    content: Optional[str] = None  # Full text or web content
    pmid: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source_type: str = "pubmed"  # pubmed, semantic_scholar, web


class DiseaseIntelligenceService:
    """
    Populates disease intelligence database using rigorous literature search.

    Uses the same approach as case series analysis:
    1. Multi-source search (PubMed, Semantic Scholar, Web)
    2. LLM filtering for relevance
    3. Multi-stage extraction with extended thinking
    4. Cross-validation across sources
    """

    def __init__(
        self,
        pubmed_searcher,
        semantic_scholar_searcher,
        web_searcher,
        llm_client,
        repository: DiseaseIntelligenceRepository,
        filter_model: str = "claude-3-haiku-20240307",
        extraction_model: str = "claude-sonnet-4-20250514",
    ):
        """
        Initialize the service.

        Args:
            pubmed_searcher: PubMed search tool
            semantic_scholar_searcher: Semantic Scholar search tool
            web_searcher: Web search tool (Tavily)
            llm_client: LLM client for extraction
            repository: Database repository
            filter_model: Model for paper filtering (Haiku for speed)
            extraction_model: Model for data extraction (Sonnet for quality)
        """
        self.pubmed = pubmed_searcher
        self.semantic_scholar = semantic_scholar_searcher
        self.web_searcher = web_searcher
        self.llm = llm_client
        self.repository = repository
        self.filter_model = filter_model
        self.extraction_model = extraction_model

        # Load Jinja2 templates
        prompts_dir = Path(__file__).parent / "prompts"
        self.jinja_env = Environment(loader=FileSystemLoader(str(prompts_dir)))

    async def populate_disease(
        self,
        disease_name: str,
        therapeutic_area: Optional[str] = None,
        force_refresh: bool = False,
        # New parameters for integrated workflow with Pipeline Intelligence
        approved_drugs: Optional[List[Any]] = None,  # List[PipelineDrug]
        pipeline_drugs: Optional[List[Any]] = None,  # List[PipelineDrug]
        disease_synonyms: Optional[List[str]] = None,
    ) -> DiseaseIntelligence:
        """
        Gather and store all intelligence for a disease.

        Args:
            disease_name: Disease name to research
            therapeutic_area: Optional therapeutic area classification
            force_refresh: If True, re-fetch even if data exists
            approved_drugs: Optional list of approved drugs from Pipeline Intelligence
                           (used to build treatment paradigm without re-extraction)
            pipeline_drugs: Optional list of all pipeline drugs from Pipeline Intelligence
                           (for context in treatment paradigm)
            disease_synonyms: Optional list of disease synonyms from MeSH expansion
                             (used for more comprehensive literature search)

        Returns:
            Complete DiseaseIntelligence record
        """
        logger.info(f"Starting disease intelligence population for: {disease_name}")
        if disease_synonyms:
            logger.info(f"  Using {len(disease_synonyms)} disease synonyms from Pipeline")
        if approved_drugs:
            logger.info(f"  Using {len(approved_drugs)} approved drugs from Pipeline")

        # Check if we already have data
        if not force_refresh:
            existing = self.repository.get_disease(disease_name)
            if existing and existing.prevalence.total_patients:
                logger.info(f"Using cached data for {disease_name}")
                return existing

        # Initialize disease record
        disease = DiseaseIntelligence(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area,
        )

        # Use disease synonyms for search if provided (from Pipeline Intelligence)
        search_terms = disease_synonyms if disease_synonyms else [disease_name]

        # Run searches and extractions in parallel where possible
        try:
            # Phase 1: Search for all data types (using synonyms for better coverage)
            logger.info("Phase 1: Multi-source literature search")
            prevalence_papers, treatment_papers, failure_papers = await asyncio.gather(
                self._search_prevalence(disease_name, search_terms),
                self._search_treatment(disease_name, search_terms),
                self._search_failure_rates(disease_name, search_terms),
            )

            logger.info(f"Found: {len(prevalence_papers)} prevalence, {len(treatment_papers)} treatment, {len(failure_papers)} failure papers")

            # Phase 2: Extract data from each set
            # For treatment, use hybrid approach if approved_drugs provided from Pipeline
            logger.info("Phase 2: LLM extraction")
            prevalence_data, failure_data = await asyncio.gather(
                self._extract_prevalence(disease_name, prevalence_papers),
                self._extract_failure_rates(disease_name, failure_papers),
            )

            # Hybrid treatment paradigm: Use Pipeline drugs as foundation, enrich with literature
            if approved_drugs:
                logger.info("Phase 2b: Building hybrid treatment paradigm from Pipeline drugs + literature")
                treatment_data = await self._build_hybrid_treatment_paradigm(
                    disease_name=disease_name,
                    approved_drugs=approved_drugs,
                    pipeline_drugs=pipeline_drugs or [],
                    treatment_papers=treatment_papers,
                )
            else:
                # Fallback to pure literature extraction
                treatment_data = await self._extract_treatment(disease_name, treatment_papers)

            # Phase 3: Assemble disease record
            logger.info("Phase 3: Assembling disease record")
            disease = self._assemble_disease(
                disease_name,
                therapeutic_area,
                prevalence_data,
                treatment_data,
                failure_data,
                prevalence_papers + treatment_papers + failure_papers,
            )

            # Phase 3.5: Validate extraction results
            logger.info("Phase 3.5: Validating extraction results")
            validation_issues = validate_extraction(
                disease_name, prevalence_data, failure_data, treatment_data
            )
            for issue in validation_issues:
                if issue["severity"] == "error":
                    logger.error(f"Validation error [{issue['field']}]: {issue['message']}")
                elif issue["severity"] == "warning":
                    logger.warning(f"Validation warning [{issue['field']}]: {issue['message']}")
                else:
                    logger.info(f"Validation info [{issue['field']}]: {issue['message']}")

            # Store validation notes in disease record
            if validation_issues:
                issue_summary = "; ".join([f"{i['field']}: {i['message']}" for i in validation_issues if i["severity"] in ["error", "warning"]])
                if disease.notes:
                    disease.notes += f"\n\nValidation notes: {issue_summary}"
                else:
                    disease.notes = f"Validation notes: {issue_summary}"

            # Phase 4: Calculate market funnel
            logger.info("Phase 4: Calculating market funnel")
            disease.calculate_market_funnel()

            # Phase 5: Save to database
            logger.info("Phase 5: Saving to database")
            disease_id = self.repository.save_disease(disease)
            disease.disease_id = disease_id

            # Save sources
            all_papers = prevalence_papers + treatment_papers + failure_papers
            for paper in all_papers:
                # Convert authors to string if it's a list
                authors = paper.authors
                if isinstance(authors, list):
                    authors = ", ".join(authors)

                source = DiseaseSource(
                    pmid=paper.pmid,
                    doi=paper.doi,
                    url=paper.url,
                    title=paper.title,
                    authors=authors,
                    journal=paper.journal,
                    publication_year=paper.year,
                    source_type=paper.source_type,
                    abstract=paper.abstract,
                )
                self.repository.save_source(disease_id, source)

            logger.info(f"Successfully populated disease intelligence for {disease_name}")
            return disease

        except Exception as e:
            logger.error(f"Error populating disease intelligence: {e}")
            raise

    async def _search_prevalence(
        self,
        disease: str,
        search_terms: Optional[List[str]] = None,
    ) -> List[Paper]:
        """Search multiple sources for prevalence data."""
        papers = []

        # Use primary disease name and top synonyms for queries
        primary_terms = [disease]
        if search_terms:
            # Add top 3 synonyms for broader coverage
            for term in search_terms[:4]:
                if term.lower() not in [t.lower() for t in primary_terms]:
                    primary_terms.append(term)

        # Build queries using primary terms
        pubmed_queries = []
        for term in primary_terms[:3]:  # Use top 3 terms
            pubmed_queries.extend([
                f"{term} prevalence United States epidemiology",
                f"{term} incidence United States population",
                f"{term} burden of disease epidemiology",
                f"{term} national estimates United States",
            ])
        # Add specific queries for better coverage
        pubmed_queries.extend([
            f"{disease} claims database prevalence",
            f'"{disease}" registry United States patient',
            f"{disease} NHANES prevalence",  # National survey data
            f"{disease} epidemiology systematic review meta-analysis",
            f"{disease} prevalence trends United States",
            f"{disease} patient population survey United States",
            f"{disease} MarketScan Optum claims prevalence",
            f"{disease} age-adjusted prevalence rate",
        ])

        for query in pubmed_queries:
            try:
                results = await self._search_pubmed(query, max_results=10)  # Increased from 8
                papers.extend(results)
            except Exception as e:
                logger.warning(f"PubMed search failed for '{query}': {e}")

        # Web search for authoritative sources - significantly expanded
        web_queries = [
            f"{disease} prevalence United States CDC NIH",
            f"{disease} patient population statistics US",
            f"site:cdc.gov {disease} prevalence",
            f"site:rarediseases.info.nih.gov {disease}",  # NIH GARD for rare diseases
            f"{disease} prevalence patient advocacy foundation",
            f"{disease} epidemiology statistics United States 2024",
            f"{disease} disease burden patients United States",
            f"site:arthritis.org {disease} statistics",  # Arthritis Foundation
            f"site:lupus.org prevalence statistics",  # Lupus Foundation
            f"{disease} market size patient population",
            f"{disease} healthcare database prevalence claims",
        ]

        for query in web_queries:
            try:
                results = await self._search_web(query, max_results=5)  # Increased from 4
                papers.extend(results)
            except Exception as e:
                logger.warning(f"Web search failed for '{query}': {e}")

        # Deduplicate by title
        seen_titles = set()
        unique_papers = []
        for paper in papers:
            title_lower = paper.title.lower() if paper.title else ""
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_papers.append(paper)

        logger.info(f"Found {len(unique_papers)} unique prevalence papers")
        return unique_papers[:60]  # Increased limit for better source coverage

    async def _search_treatment(
        self,
        disease: str,
        search_terms: Optional[List[str]] = None,
    ) -> List[Paper]:
        """Search for treatment guidelines and patterns."""
        papers = []

        # Use primary disease name and top synonyms for queries
        primary_terms = [disease]
        if search_terms:
            for term in search_terms[:2]:
                if term.lower() not in [t.lower() for t in primary_terms]:
                    primary_terms.append(term)

        # PubMed for guidelines (with synonyms)
        pubmed_queries = []
        for term in primary_terms[:2]:
            pubmed_queries.extend([
                f"{term} treatment guidelines recommendations",
                f"{term} standard of care therapy",
            ])
        pubmed_queries.append(f"{disease} treatment algorithm biologic")

        for query in pubmed_queries:
            try:
                results = await self._search_pubmed(query, max_results=10)
                papers.extend(results)
            except Exception as e:
                logger.warning(f"PubMed search failed for '{query}': {e}")

        # Web search for official guidelines
        web_queries = [
            f"{disease} ACR EULAR treatment guidelines 2024",
            f"{disease} treatment recommendations society guidelines",
        ]

        for query in web_queries:
            try:
                results = await self._search_web(query, max_results=5)
                papers.extend(results)
            except Exception as e:
                logger.warning(f"Web search failed for '{query}': {e}")

        # Deduplicate
        seen_titles = set()
        unique_papers = []
        for paper in papers:
            title_lower = paper.title.lower() if paper.title else ""
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_papers.append(paper)

        logger.info(f"Found {len(unique_papers)} unique treatment papers")
        return unique_papers[:15]

    async def _search_failure_rates(
        self,
        disease: str,
        search_terms: Optional[List[str]] = None,
    ) -> List[Paper]:
        """Search for treatment failure/inadequate response data."""
        papers = []

        # Use primary disease name and top synonyms
        primary_terms = [disease]
        if search_terms:
            for term in search_terms[:2]:
                if term.lower() not in [t.lower() for t in primary_terms]:
                    primary_terms.append(term)

        pubmed_queries = []
        # Build queries using primary terms
        for term in primary_terms[:2]:
            pubmed_queries.extend([
                f"{term} inadequate response first line therapy",
                f"{term} treatment failure conventional",
                f"{term} real world treatment discontinuation",
            ])
        # Add disease-specific queries
        pubmed_queries.extend([
            f"{disease} biologic naive population",
            # Drug survival / persistence
            f"{disease} drug survival registry",
            f"{disease} persistence adherence real world",
            f"{disease} treatment retention biologic",
            # Switching patterns
            f"{disease} switching biologic therapy",
            f"{disease} cycling treatment failure",
            f"{disease} second line after failure",
            # Specific failure terminology
            f"{disease} refractory prevalence epidemiology",
            f"{disease} non-response primary secondary",
            f"{disease} loss of response biologic",
            f"{disease} intolerance discontinuation safety",
        ])

        for query in pubmed_queries:
            try:
                results = await self._search_pubmed(query, max_results=6)
                papers.extend(results)
            except Exception as e:
                logger.warning(f"PubMed search failed for '{query}': {e}")

        # Deduplicate
        seen_titles = set()
        unique_papers = []
        for paper in papers:
            title_lower = paper.title.lower() if paper.title else ""
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                unique_papers.append(paper)

        logger.info(f"Found {len(unique_papers)} unique failure rate papers")
        return unique_papers[:15]  # Increased from 12 to get better coverage

    async def _search_pubmed(self, query: str, max_results: int = 10) -> List[Paper]:
        """Search PubMed and return papers."""
        try:
            # Use the pubmed searcher - search_and_fetch returns paper dicts
            results = self.pubmed.search_and_fetch(query, max_results=max_results)
            papers = []
            for r in results:
                papers.append(Paper(
                    title=r.get("title", ""),
                    authors=r.get("authors", ""),
                    journal=r.get("journal", ""),
                    year=r.get("year"),
                    abstract=r.get("abstract", ""),
                    pmid=r.get("pmid"),
                    doi=r.get("doi"),
                    source_type="pubmed",
                ))
            return papers
        except Exception as e:
            logger.warning(f"PubMed search error: {e}")
            return []

    async def _search_web(self, query: str, max_results: int = 5) -> List[Paper]:
        """Search web and return papers."""
        if not self.web_searcher:
            logger.debug("Web searcher not configured")
            return []

        try:
            # WebSearchTool.search is synchronous, so run in executor
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self.web_searcher.search(query, max_results=max_results)
            )
            papers = []
            for r in results:
                papers.append(Paper(
                    title=r.get("title", ""),
                    content=r.get("content", r.get("snippet", "")),
                    url=r.get("url"),
                    source_type="web",
                ))
            return papers
        except Exception as e:
            logger.warning(f"Web search error: {e}")
            return []

    async def _extract_prevalence(
        self,
        disease: str,
        papers: List[Paper],
    ) -> Dict[str, Any]:
        """Extract prevalence data from papers using LLM."""
        if not papers:
            return {}

        # Prepare sources for template
        sources = []
        for p in papers[:10]:  # Limit to 10 for context
            sources.append({
                "title": p.title,
                "pmid": p.pmid,
                "authors": p.authors,
                "journal": p.journal,
                "year": p.year,
                "url": p.url,
                "content": p.abstract or p.content or "",
            })

        # Render prompt
        template = self.jinja_env.get_template("extract_prevalence.j2")
        prompt = template.render(disease_name=disease, sources=sources)

        # Call LLM
        try:
            response = await self._call_llm(prompt, self.extraction_model)
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"Prevalence extraction failed: {e}")
            return {}

    async def _extract_treatment(
        self,
        disease: str,
        papers: List[Paper],
    ) -> Dict[str, Any]:
        """Extract treatment paradigm from papers using LLM."""
        if not papers:
            return {}

        sources = []
        for p in papers[:10]:
            sources.append({
                "title": p.title,
                "pmid": p.pmid,
                "authors": p.authors,
                "journal": p.journal,
                "year": p.year,
                "url": p.url,
                "content": p.abstract or p.content or "",
            })

        template = self.jinja_env.get_template("extract_treatment.j2")
        prompt = template.render(disease_name=disease, sources=sources)

        try:
            response = await self._call_llm(prompt, self.extraction_model)
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"Treatment extraction failed: {e}")
            return {}

    async def _extract_failure_rates(
        self,
        disease: str,
        papers: List[Paper],
    ) -> Dict[str, Any]:
        """Extract failure rates from papers using LLM."""
        if not papers:
            return {}

        sources = []
        for p in papers[:10]:
            sources.append({
                "title": p.title,
                "pmid": p.pmid,
                "authors": p.authors,
                "journal": p.journal,
                "year": p.year,
                "url": p.url,
                "content": p.abstract or p.content or "",
            })

        template = self.jinja_env.get_template("extract_failure_rates.j2")
        prompt = template.render(disease_name=disease, sources=sources)

        try:
            response = await self._call_llm(prompt, self.extraction_model)
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"Failure rate extraction failed: {e}")
            return {}

    async def _build_hybrid_treatment_paradigm(
        self,
        disease_name: str,
        approved_drugs: List[Any],  # List[PipelineDrug]
        pipeline_drugs: List[Any],  # List[PipelineDrug]
        treatment_papers: List[Paper],
    ) -> Dict[str, Any]:
        """
        Build treatment paradigm using hybrid approach:
        - Pipeline drugs as foundation (approved status, MOA, targets)
        - Literature enrichment (off-label uses, combinations, guidelines, WAC)

        This eliminates duplicate drug discovery by using Pipeline Intelligence
        data as the source of truth for approved drugs.

        Args:
            disease_name: Disease name
            approved_drugs: Approved drugs from Pipeline Intelligence
            pipeline_drugs: All pipeline drugs for context
            treatment_papers: Treatment papers from literature search

        Returns:
            Treatment data dict compatible with _assemble_disease
        """
        logger.info(f"Building hybrid treatment paradigm from {len(approved_drugs)} approved drugs")

        # Deduplicate incoming drugs by PubChem CID (safety net for Pipeline Intelligence dedup)
        seen_cids = set()
        unique_drugs = []
        for drug in approved_drugs:
            cid = getattr(drug, 'pubchem_cid', None)
            if cid and cid in seen_cids:
                logger.info(f"Skipping duplicate drug in treatment paradigm: {drug.generic_name} (CID: {cid})")
                continue
            if cid:
                seen_cids.add(cid)
            unique_drugs.append(drug)

        if len(unique_drugs) < len(approved_drugs):
            logger.info(f"Deduplicated {len(approved_drugs)} → {len(unique_drugs)} drugs by PubChem CID")
        approved_drugs = unique_drugs

        # Build base treatment paradigm from Pipeline drugs
        # Convert all drugs to entry format first
        all_drug_entries = []
        for drug in approved_drugs:
            drug_entry = {
                "drug_name": drug.brand_name or drug.generic_name,
                "generic_name": drug.generic_name,
                "drug_class": drug.mechanism_of_action or drug.drug_type,
                "drug_type": drug.drug_type,
                "is_standard_of_care": True,
                "notes": f"Approved: {drug.first_approval_date}" if drug.first_approval_date else None,
            }
            all_drug_entries.append(drug_entry)

        # Use LLM + web search to classify drugs into treatment lines
        first_line_drugs, second_line_drugs = await self._classify_treatment_lines_llm(
            disease_name=disease_name,
            drugs=all_drug_entries
        )

        # Enrich with literature context (WAC, combinations, guidelines)
        enrichment_data = {}
        if treatment_papers:
            logger.info("Enriching treatment paradigm with literature context")
            # Extract treatment context focusing on enrichment, not drug discovery
            enrichment_data = await self._extract_treatment_enrichment(
                disease_name=disease_name,
                known_drugs=[d.get("generic_name") or d.get("drug_name") for d in first_line_drugs + second_line_drugs],
                papers=treatment_papers,
            )

        # Merge enrichment data with Pipeline drugs
        # Add WAC pricing from enrichment
        wac_data = enrichment_data.get("wac_prices", {})
        for drug in second_line_drugs:
            drug_name = (drug.get("generic_name") or drug.get("drug_name") or "").lower()
            if drug_name in wac_data:
                drug["wac_monthly"] = wac_data[drug_name].get("wac_monthly")
                drug["wac_source"] = wac_data[drug_name].get("source")

        # Build treatment paradigm structure
        treatment_paradigm = {
            "first_line": {
                "description": enrichment_data.get("first_line_description", "Standard first-line therapy"),
                "drugs": first_line_drugs,
            },
            "second_line": {
                "description": enrichment_data.get("second_line_description", "Advanced therapy after 1L failure"),
                "drugs": second_line_drugs,
            },
            "paradigm_summary": enrichment_data.get("paradigm_summary"),
        }

        # Extract segmentation data from enrichment
        segmentation = enrichment_data.get("segmentation", {})
        treatment_rate_estimates = enrichment_data.get("treatment_rate_estimates", [])

        return {
            "treatment_paradigm": treatment_paradigm,
            "segmentation": segmentation,
            "treatment_rate_estimates": treatment_rate_estimates,
            "consensus": enrichment_data.get("consensus", {}),
        }

    async def _classify_treatment_lines_llm(
        self,
        disease_name: str,
        drugs: List[Dict[str, Any]]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Classify drugs into treatment lines using LLM + web search.

        This is more scalable than keyword matching as it uses actual
        treatment guidelines from web search.

        Args:
            disease_name: Disease name
            drugs: List of drug entries to classify

        Returns:
            Tuple of (first_line_drugs, second_line_drugs)
        """
        if not drugs:
            return [], []

        drug_names = [d.get("generic_name") or d.get("drug_name") for d in drugs]
        logger.info(f"Classifying {len(drugs)} drugs into treatment lines for {disease_name}")

        # Web search for treatment guidelines
        search_results = []
        if self.web_searcher:
            queries = [
                f"{disease_name} treatment guidelines first line second line",
                f"{disease_name} therapy algorithm recommendations",
                f"{disease_name} standard of care treatment sequence",
            ]
            for query in queries:
                try:
                    results = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda q=query: self.web_searcher.search(q, max_results=5)
                    )
                    if results:
                        search_results.extend(results)
                except Exception as e:
                    logger.warning(f"Web search for treatment guidelines failed: {e}")

        # Build context from search results
        guidelines_context = ""
        if search_results:
            guidelines_context = "\n\n".join([
                f"Source: {r.get('title', 'Unknown')}\n{r.get('content', r.get('snippet', ''))[:500]}"
                for r in search_results[:8]
            ])

        # Use LLM to classify drugs
        prompt = f"""Classify these drugs into first-line (1L) and second-line (2L) therapy for {disease_name}.

DRUGS TO CLASSIFY:
{json.dumps([{"name": d.get("generic_name") or d.get("drug_name"), "class": d.get("drug_class"), "type": d.get("drug_type")} for d in drugs], indent=2)}

TREATMENT GUIDELINES CONTEXT:
{guidelines_context if guidelines_context else "No specific guidelines found - use general medical knowledge."}

CLASSIFICATION RULES:
- First-line (1L): Initial therapies used when patient is diagnosed. Usually includes:
  - Conventional/traditional therapies (DMARDs, antimalarials, corticosteroids, NSAIDs)
  - Well-established, often generic medications
  - Lower cost, broader experience

- Second-line (2L): Used after 1L failure or for more severe cases. Usually includes:
  - Biologics (monoclonal antibodies, fusion proteins)
  - Targeted small molecules (JAK inhibitors, kinase inhibitors)
  - Newer, often more expensive therapies

Return JSON:
{{
  "first_line": [
    {{"generic_name": "drug name", "rationale": "brief reason"}}
  ],
  "second_line": [
    {{"generic_name": "drug name", "rationale": "brief reason"}}
  ],
  "classification_confidence": "High/Medium/Low",
  "notes": "any important context about treatment sequencing for {disease_name}"
}}

IMPORTANT: Classify ALL drugs provided. Every drug must appear in either first_line or second_line."""

        try:
            response = await self._call_llm(prompt, self.extraction_model)
            data = self._parse_json_response(response)

            if not data:
                logger.warning("LLM classification returned no data, using fallback")
                return self._fallback_classify_drugs(drugs)

            # Build lookup for classification results
            first_line_names = {d["generic_name"].lower() for d in data.get("first_line", [])}
            second_line_names = {d["generic_name"].lower() for d in data.get("second_line", [])}

            first_line_drugs = []
            second_line_drugs = []

            for drug in drugs:
                drug_name = (drug.get("generic_name") or drug.get("drug_name") or "").lower()
                if drug_name in first_line_names:
                    first_line_drugs.append(drug)
                elif drug_name in second_line_names:
                    second_line_drugs.append(drug)
                else:
                    # Default unclassified drugs to 2L (safer assumption for newer drugs)
                    second_line_drugs.append(drug)

            logger.info(f"LLM classified: {len(first_line_drugs)} 1L, {len(second_line_drugs)} 2L")
            if data.get("notes"):
                logger.info(f"Classification notes: {data.get('notes')}")

            return first_line_drugs, second_line_drugs

        except Exception as e:
            logger.error(f"LLM treatment classification failed: {e}")
            return self._fallback_classify_drugs(drugs)

    def _fallback_classify_drugs(self, drugs: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Fallback keyword-based classification if LLM fails."""
        first_line_drugs = []
        second_line_drugs = []

        first_line_keywords = [
            "hydroxychloroquine", "chloroquine", "methotrexate", "azathioprine",
            "mycophenolate", "cyclophosphamide", "prednisone", "prednisolone",
            "methylprednisolone", "dexamethasone", "ibuprofen", "naproxen", "celecoxib"
        ]

        for drug in drugs:
            drug_name = (drug.get("generic_name") or drug.get("drug_name") or "").lower()
            if any(kw in drug_name for kw in first_line_keywords):
                first_line_drugs.append(drug)
            else:
                second_line_drugs.append(drug)

        return first_line_drugs, second_line_drugs

    async def _extract_treatment_enrichment(
        self,
        disease_name: str,
        known_drugs: List[str],
        papers: List[Paper],
    ) -> Dict[str, Any]:
        """
        Extract treatment enrichment data from literature.

        This is different from full treatment extraction - it focuses on:
        - WAC pricing for known drugs
        - Treatment guidelines and sequences
        - Off-label uses and combination therapies
        - Treatment rate estimates

        NOT: Discovering which drugs are approved (Pipeline already did this)

        Args:
            disease_name: Disease name
            known_drugs: List of drug names from Pipeline Intelligence
            papers: Treatment papers from literature search

        Returns:
            Enrichment data dict with WAC, guidelines, combinations
        """
        if not papers:
            return {}

        sources = []
        for p in papers[:10]:
            sources.append({
                "title": p.title,
                "pmid": p.pmid,
                "authors": p.authors,
                "journal": p.journal,
                "year": p.year,
                "url": p.url,
                "content": p.abstract or p.content or "",
            })

        # Use the standard treatment extraction template
        # The template will be updated to focus on enrichment when known_drugs are provided
        template = self.jinja_env.get_template("extract_treatment.j2")
        prompt = template.render(
            disease_name=disease_name,
            sources=sources,
            known_drugs=known_drugs,  # Pass known drugs so LLM focuses on enrichment
        )

        try:
            response = await self._call_llm(prompt, self.extraction_model)
            return self._parse_json_response(response)
        except Exception as e:
            logger.error(f"Treatment enrichment extraction failed: {e}")
            return {}

    async def _call_llm(self, prompt: str, model: str) -> str:
        """Call LLM with prompt."""
        # This will be implemented based on your LLM client interface
        # For now, using a simple interface
        try:
            response = await self.llm.complete(
                prompt=prompt,
                model=model,
                max_tokens=4000,
            )
            return response
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def _extract_with_retry(
        self,
        disease: str,
        papers: List[Paper],
        data_type: str,
        max_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Extract data with retry logic using alternative approaches.

        If initial extraction fails or returns empty, tries:
        1. Retry with same prompt
        2. Retry with fewer papers (focus on best quality)
        """
        # Map data_type to extraction method
        extract_methods = {
            "prevalence": self._extract_prevalence,
            "treatment": self._extract_treatment,
            "failure_rates": self._extract_failure_rates,
        }

        extract_method = extract_methods.get(data_type)
        if not extract_method:
            logger.error(f"Unknown data type: {data_type}")
            return {}

        # Primary extraction
        result = await extract_method(disease, papers)

        if self._is_extraction_successful(result, data_type):
            return result

        # Retry logic
        for attempt in range(max_retries):
            logger.info(f"Retry {attempt + 1} for {data_type} extraction")

            # First retry: same papers, just retry
            if attempt == 0:
                result = await extract_method(disease, papers)
                if self._is_extraction_successful(result, data_type):
                    return result

            # Second retry: use fewer, higher quality papers
            if attempt == 1 and len(papers) > 5:
                # Rank papers by quality indicators (recency, journal presence)
                ranked_papers = sorted(
                    papers,
                    key=lambda p: (p.year or 0, bool(p.journal)),
                    reverse=True
                )[:5]
                result = await extract_method(disease, ranked_papers)
                if self._is_extraction_successful(result, data_type):
                    logger.info(f"Retry with fewer papers succeeded for {data_type}")
                    return result

        logger.warning(f"All extraction attempts failed for {disease} {data_type}")
        return result

    def _is_extraction_successful(self, result: Dict, data_type: str) -> bool:
        """Check if extraction returned usable data."""
        if not result:
            return False

        if data_type == "prevalence":
            estimates = result.get("source_estimates", [])
            return any(e.get("total_patients") for e in estimates)

        elif data_type == "failure_rates":
            estimates = result.get("source_estimates", [])
            return any(e.get("fail_rate_pct") is not None for e in estimates)

        elif data_type == "treatment":
            paradigm = result.get("treatment_paradigm", {})
            return bool(paradigm.get("first_line") or paradigm.get("second_line"))

        return False

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
        try:
            # Try to find JSON in the response
            response = response.strip()

            # Look for JSON block
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                response = response[start:end].strip()

            # Find the JSON object
            if response.startswith("{"):
                # Find matching closing brace
                brace_count = 0
                end_idx = 0
                for i, char in enumerate(response):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end_idx = i + 1
                            break
                response = response[:end_idx]

            return json.loads(response)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {e}")
            return {}

    def _assemble_disease(
        self,
        disease_name: str,
        therapeutic_area: Optional[str],
        prevalence_data: Dict[str, Any],
        treatment_data: Dict[str, Any],
        failure_data: Dict[str, Any],
        papers: List[Paper],
    ) -> DiseaseIntelligence:
        """Assemble all extracted data into a DiseaseIntelligence record."""

        # Build per-source prevalence estimates with new fields (deduplicated by PMID)
        prevalence_estimates = []
        seen_pmids_prevalence = set()
        for est in prevalence_data.get("source_estimates", []):
            if est.get("total_patients"):
                pmid = str(est.get("pmid")) if est.get("pmid") else None
                # Skip duplicates by PMID (same paper, same estimate type)
                dedup_key = f"{pmid}_{est.get('estimate_type')}"
                if pmid and pmid != "N/A" and dedup_key in seen_pmids_prevalence:
                    logger.debug(f"Skipping duplicate prevalence estimate from PMID {pmid}")
                    continue
                if pmid and pmid != "N/A":
                    seen_pmids_prevalence.add(dedup_key)

                prevalence_estimates.append(PrevalenceEstimate(
                    pmid=pmid,
                    title=est.get("title"),
                    authors=est.get("authors"),
                    journal=est.get("journal"),
                    year=est.get("publication_year"),
                    quality_tier=est.get("quality_tier"),
                    # New fields
                    estimate_type=est.get("estimate_type"),
                    total_patients=est.get("total_patients"),
                    adult_patients=est.get("adult_patients"),
                    pediatric_patients=est.get("pediatric_patients"),
                    prevalence_rate=est.get("prevalence_rate"),
                    confidence_interval=est.get("confidence_interval"),
                    rate_type=est.get("rate_type"),
                    data_year=est.get("data_year"),
                    geography=est.get("geography"),
                    methodology=est.get("methodology"),
                    study_population_n=est.get("study_population_n"),
                    database_name=est.get("database_name"),
                    notes=est.get("notes") or est.get("calculation_notes"),
                ))

        # Use weighted consensus calculation
        weighted_result = calculate_weighted_consensus(prevalence_estimates)
        consensus = prevalence_data.get("consensus", {})

        if weighted_result.get("recommended_estimate"):
            median_prev = weighted_result["recommended_estimate"]
            range_str = f"{weighted_result['range_low']:,} - {weighted_result['range_high']:,}" if weighted_result.get("range_low") else None
            confidence = weighted_result.get("confidence")
            confidence_rationale = weighted_result.get("confidence_rationale")
        else:
            median_prev = consensus.get("median_estimate") or consensus.get("recommended_estimate")
            range_str = None
            confidence = consensus.get("confidence")
            confidence_rationale = consensus.get("confidence_rationale")

        # Find the primary source (best quality or first)
        primary_source = None
        if prevalence_estimates:
            # Prefer Tier 1, then most recent
            tier1 = [e for e in prevalence_estimates if e.quality_tier == "Tier 1"]
            primary_source = tier1[0] if tier1 else prevalence_estimates[0]

        prevalence = PrevalenceData(
            total_patients=median_prev,
            adult_patients=primary_source.adult_patients if primary_source else None,
            pediatric_patients=primary_source.pediatric_patients if primary_source else None,
            prevalence_source=primary_source.title if primary_source else consensus.get("recommended_estimate"),
            prevalence_year=primary_source.data_year or (primary_source.year if primary_source else None),
            confidence=confidence,
            source_estimates=prevalence_estimates,
            estimate_range=range_str,
            methodology_notes=confidence_rationale or consensus.get("notes"),
        )

        # Extract treatment paradigm
        tp_raw = treatment_data.get("treatment_paradigm", {})
        treatment_paradigm = TreatmentParadigm(
            summary=tp_raw.get("paradigm_summary"),
        )

        # First line
        if tp_raw.get("first_line"):
            fl = tp_raw["first_line"]
            drugs = []
            for d in fl.get("drugs", []):
                # Get drug name - try multiple possible keys from LLM output
                drug_name = d.get("drug_name") or d.get("name") or d.get("brand_name") or ""
                if not drug_name:
                    continue  # Skip drugs without names
                drugs.append(TreatmentDrug(
                    drug_name=drug_name,
                    generic_name=d.get("generic_name") or d.get("generic"),
                    drug_class=d.get("drug_class") or d.get("class"),
                    is_standard_of_care=d.get("is_standard_of_care", False),
                    notes=d.get("notes"),
                ))
            treatment_paradigm.first_line = TreatmentLine(
                line="1L",
                description=fl.get("description"),
                drugs=drugs,
            )

        # Second line - apply estimated WAC if not provided
        estimated_wac = self._estimate_wac_monthly(
            prevalence.total_patients,
            therapeutic_area
        )

        if tp_raw.get("second_line"):
            sl = tp_raw["second_line"]
            drugs = []
            for d in sl.get("drugs", []):
                # Get drug name - try multiple possible keys from LLM output
                drug_name = d.get("drug_name") or d.get("name") or d.get("brand_name") or ""
                if not drug_name:
                    continue  # Skip drugs without names

                # Use provided WAC or fall back to estimated
                wac = d.get("wac_monthly") or d.get("wac")
                wac_source = d.get("wac_source")
                if not wac:
                    wac = estimated_wac
                    wac_source = "Estimated based on disease prevalence"

                drugs.append(TreatmentDrug(
                    drug_name=drug_name,
                    generic_name=d.get("generic_name") or d.get("generic"),
                    drug_class=d.get("drug_class") or d.get("class"),
                    wac_monthly=wac,
                    wac_source=wac_source,
                    is_standard_of_care=d.get("is_standard_of_care", False),
                ))
            treatment_paradigm.second_line = TreatmentLine(
                line="2L",
                description=sl.get("description"),
                drugs=drugs,
            )
        else:
            # Create placeholder 2L with estimated WAC for market sizing
            treatment_paradigm.second_line = TreatmentLine(
                line="2L",
                description="Advanced therapy (estimated)",
                drugs=[TreatmentDrug(
                    drug_name="Advanced Therapy",
                    drug_class="Biologic/Advanced",
                    wac_monthly=estimated_wac,
                    wac_source="Estimated based on disease prevalence",
                )],
            )

        # Extract segmentation from treatment data
        seg_raw = treatment_data.get("segmentation", {})
        severity = None
        if seg_raw.get("severity_breakdown"):
            sev = seg_raw["severity_breakdown"]
            severity = SeverityBreakdown(
                mild=sev.get("mild"),
                moderate=sev.get("moderate"),
                severe=sev.get("severe"),
            )

        # Build per-source treatment rate estimates
        treatment_estimates = []
        seen_pmids_treatment = set()  # Deduplicate by PMID
        for est in treatment_data.get("treatment_rate_estimates", []):
            if est.get("pct_treated") is not None:
                pmid = str(est.get("pmid")) if est.get("pmid") else None
                # Skip duplicates by PMID
                if pmid and pmid != "N/A" and pmid in seen_pmids_treatment:
                    continue
                if pmid and pmid != "N/A":
                    seen_pmids_treatment.add(pmid)

                treatment_estimates.append(TreatmentEstimate(
                    pmid=pmid,
                    title=est.get("title"),
                    authors=est.get("authors"),
                    journal=est.get("journal"),
                    year=est.get("publication_year"),
                    quality_tier=est.get("quality_tier"),
                    pct_treated=est.get("pct_treated"),
                    treatment_definition=est.get("treatment_definition"),
                    notes=est.get("notes"),
                ))

        # Calculate consensus treatment rate
        treatment_consensus = treatment_data.get("consensus", {})
        treatment_rate_values = [e.pct_treated for e in treatment_estimates if e.pct_treated is not None]

        if treatment_rate_values:
            median_pct_treated = statistics.median(treatment_rate_values)
            treatment_rate_range = f"{min(treatment_rate_values):.0f}% - {max(treatment_rate_values):.0f}%" if len(treatment_rate_values) > 1 else None
            # Prefer Tier 1 source for primary
            tier1_treatment = [e for e in treatment_estimates if e.quality_tier == "Tier 1"]
            primary_treatment_source = tier1_treatment[0].title if tier1_treatment else (treatment_estimates[0].title if treatment_estimates else None)
        else:
            # Fall back to old format or consensus
            median_pct_treated = seg_raw.get("pct_treated") or treatment_consensus.get("median_pct_treated") or treatment_consensus.get("recommended_estimate")
            treatment_rate_range = treatment_consensus.get("range")
            primary_treatment_source = treatment_consensus.get("recommended_rationale")

        # Assess treatment rate confidence
        tier1_treatment_count = sum(1 for e in treatment_estimates if e.quality_tier == "Tier 1")
        if tier1_treatment_count >= 2 and len(treatment_rate_values) > 1:
            treatment_confidence = "High"
            treatment_confidence_rationale = f"{tier1_treatment_count} Tier-1 sources with treatment rate data"
        elif tier1_treatment_count >= 1:
            treatment_confidence = "Medium"
            treatment_confidence_rationale = "Tier-1 source available"
        elif treatment_rate_values:
            treatment_confidence = "Low"
            treatment_confidence_rationale = "No Tier-1 sources"
        else:
            treatment_confidence = treatment_consensus.get("confidence", "Low")
            treatment_confidence_rationale = treatment_consensus.get("confidence_rationale", "Limited data")

        segmentation = PatientSegmentation(
            pct_treated=median_pct_treated,
            pct_treated_source=primary_treatment_source,
            severity=severity,
            treatment_estimates=treatment_estimates,
            treatment_rate_range=treatment_rate_range,
            treatment_rate_confidence=treatment_confidence,
            treatment_rate_confidence_rationale=treatment_confidence_rationale,
        )

        # Build per-source failure rate estimates with new fields (deduplicated by PMID)
        failure_estimates = []
        seen_pmids_failure = set()
        for est in failure_data.get("source_estimates", []):
            if est.get("fail_rate_pct") is not None:
                pmid = str(est.get("pmid")) if est.get("pmid") else None
                # Skip duplicates by PMID (but allow multiple estimates from same paper with different failure types)
                dedup_key = f"{pmid}_{est.get('failure_type')}_{est.get('line_of_therapy')}"
                if pmid and pmid != "N/A" and dedup_key in seen_pmids_failure:
                    continue
                if pmid and pmid != "N/A":
                    seen_pmids_failure.add(dedup_key)

                failure_estimates.append(FailureRateEstimate(
                    pmid=pmid,
                    title=est.get("title"),
                    authors=est.get("authors"),
                    journal=est.get("journal"),
                    year=est.get("publication_year"),
                    quality_tier=est.get("quality_tier"),
                    # Core failure data
                    failure_type=est.get("failure_type"),
                    fail_rate_pct=est.get("fail_rate_pct"),
                    confidence_interval=est.get("confidence_interval"),
                    # Clinical endpoint details
                    clinical_endpoint=est.get("clinical_endpoint"),
                    endpoint_definition=est.get("endpoint_definition"),
                    failure_definition=est.get("failure_definition"),
                    failure_reason=est.get("failure_reason"),
                    # Treatment context
                    line_of_therapy=est.get("line_of_therapy"),
                    specific_therapy=est.get("specific_therapy"),
                    time_to_failure=est.get("time_to_failure"),
                    timepoint_type=est.get("timepoint_type"),
                    # Denominator context
                    patient_population=est.get("patient_population"),
                    denominator_n=est.get("denominator_n"),
                    analysis_type=est.get("analysis_type"),
                    # Switch vs discontinuation
                    switch_rate_pct=est.get("switch_rate_pct"),
                    switch_destination=est.get("switch_destination"),
                    full_discontinuation_pct=est.get("full_discontinuation_pct"),
                    # Methodology
                    methodology=est.get("methodology"),
                    notes=est.get("notes"),
                ))

        # Calculate median failure rate (1L only)
        fail_1L_values = [e.fail_rate_pct for e in failure_estimates
                         if e.fail_rate_pct and e.line_of_therapy in ["1L", "any", None]]
        fail_consensus = failure_data.get("consensus", {})

        if fail_1L_values:
            median_fail = statistics.median(fail_1L_values)
            fail_range = f"{min(fail_1L_values):.0f}% - {max(fail_1L_values):.0f}%" if len(fail_1L_values) > 1 else None
        else:
            median_fail = fail_consensus.get("median_fail_1L_pct")
            fail_range = fail_consensus.get("range_1L")

        # Find primary reason and failure type from estimates
        reasons = [e.failure_reason for e in failure_estimates if e.failure_reason]
        primary_reason = max(set(reasons), key=reasons.count) if reasons else fail_consensus.get("primary_reason")

        failure_types = [e.failure_type for e in failure_estimates if e.failure_type]
        primary_failure_type = max(set(failure_types), key=failure_types.count) if failure_types else fail_consensus.get("primary_failure_type")

        # Calculate median switch and discontinuation rates
        switch_rates = [e.switch_rate_pct for e in failure_estimates if e.switch_rate_pct is not None]
        switch_rate_1L = statistics.median(switch_rates) if switch_rates else fail_consensus.get("switch_rate_1L")

        discont_rates = [e.full_discontinuation_pct for e in failure_estimates if e.full_discontinuation_pct is not None]
        discont_rate_1L = statistics.median(discont_rates) if discont_rates else fail_consensus.get("discontinuation_rate_1L")

        # Assess failure rate confidence
        tier1_fail = sum(1 for e in failure_estimates if e.quality_tier == "Tier 1")
        if tier1_fail >= 2 and len(fail_1L_values) > 1:
            fail_confidence = "High"
            fail_confidence_rationale = f"{tier1_fail} Tier-1 sources with consistent definitions"
        elif tier1_fail >= 1:
            fail_confidence = "Medium"
            fail_confidence_rationale = "Tier-1 source available"
        else:
            fail_confidence = "Low"
            fail_confidence_rationale = "No Tier-1 sources or limited data"

        # Determine primary source for failure rate (prefer Tier 1)
        tier1_failure = [e for e in failure_estimates if e.quality_tier == "Tier 1" and e.line_of_therapy in ["1L", "any", None]]
        primary_failure_source = tier1_failure[0].title if tier1_failure else (failure_estimates[0].title if failure_estimates else None)
        fail_1L_source_count = len([e for e in failure_estimates if e.line_of_therapy in ["1L", "any", None]])

        failure_rates = FailureRates(
            fail_1L_pct=median_fail,
            fail_1L_reason=primary_reason,
            fail_1L_source=primary_failure_source,
            fail_1L_source_count=fail_1L_source_count,
            primary_failure_type=primary_failure_type,
            source=primary_failure_source,  # Keep for backwards compatibility
            # Switch vs discontinuation
            switch_rate_1L_pct=switch_rate_1L,
            discontinuation_rate_1L_pct=discont_rate_1L,
            standardized_timepoint=fail_consensus.get("standardized_timepoint"),
            # Confidence
            confidence=fail_confidence,
            confidence_rationale=fail_confidence_rationale,
            # Source tracking
            source_estimates=failure_estimates,
            estimate_range=fail_range,
            methodology_notes=fail_consensus.get("notes"),
        )

        # Determine data quality
        data_quality = "Medium"
        if prevalence.total_patients and segmentation.pct_treated and failure_rates.fail_1L_pct:
            data_quality = "High"
        elif not prevalence.total_patients:
            data_quality = "Low"

        return DiseaseIntelligence(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area,
            prevalence=prevalence,
            segmentation=segmentation,
            treatment_paradigm=treatment_paradigm,
            failure_rates=failure_rates,
            data_quality=data_quality,
            notes=prevalence_data.get("data_quality_notes"),
        )

    async def populate_diseases_concurrent(
        self,
        disease_names: List[str],
        max_concurrent: int = 3,
        force_refresh: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Populate disease intelligence for multiple diseases concurrently.

        Args:
            disease_names: List of disease names to research
            max_concurrent: Maximum concurrent disease processing (default 3)
            force_refresh: If True, re-fetch even if data exists
            progress_callback: Optional callback(disease_name, status, result_or_error)
                              status is one of: "started", "completed", "failed", "skipped"

        Returns:
            Dict with:
                - successful: List of successfully populated diseases
                - failed: Dict mapping disease name to error message
                - skipped: List of diseases that already had data (if not force_refresh)
        """
        logger.info(f"Starting concurrent disease intelligence population for {len(disease_names)} diseases (max_concurrent={max_concurrent})")

        semaphore = asyncio.Semaphore(max_concurrent)
        results = {
            "successful": [],
            "failed": {},
            "skipped": [],
        }

        async def process_disease(disease_name: str) -> Tuple[str, str, Optional[DiseaseIntelligence]]:
            """Process a single disease with semaphore limiting."""
            async with semaphore:
                try:
                    # Check if we already have data
                    if not force_refresh:
                        existing = self.repository.get_disease(disease_name)
                        if existing and existing.data_quality in ["High", "Medium"]:
                            logger.info(f"Skipping {disease_name} - already has {existing.data_quality} quality data")
                            if progress_callback:
                                progress_callback(disease_name, "skipped", existing)
                            return (disease_name, "skipped", existing)

                    if progress_callback:
                        progress_callback(disease_name, "started", None)

                    logger.info(f"Processing disease: {disease_name}")
                    result = await self.populate_disease(
                        disease_name=disease_name,
                        force_refresh=force_refresh,
                    )

                    if progress_callback:
                        progress_callback(disease_name, "completed", result)

                    return (disease_name, "completed", result)

                except Exception as e:
                    logger.error(f"Failed to populate {disease_name}: {e}")
                    if progress_callback:
                        progress_callback(disease_name, "failed", str(e))
                    return (disease_name, "failed", str(e))

        # Run all diseases concurrently with semaphore limiting
        tasks = [process_disease(name) for name in disease_names]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        for result in task_results:
            if isinstance(result, Exception):
                # This shouldn't happen since we catch exceptions in process_disease
                logger.error(f"Unexpected exception: {result}")
                continue

            disease_name, status, data = result
            if status == "completed":
                results["successful"].append(disease_name)
            elif status == "failed":
                results["failed"][disease_name] = data
            elif status == "skipped":
                results["skipped"].append(disease_name)

        logger.info(
            f"Disease intelligence population complete: "
            f"{len(results['successful'])} successful, "
            f"{len(results['failed'])} failed, "
            f"{len(results['skipped'])} skipped"
        )

        return results

    def _estimate_wac_monthly(self, prevalence: int, therapeutic_area: Optional[str] = None) -> float:
        """
        Estimate monthly WAC based on disease prevalence/rarity.

        Uses industry benchmarks for biologic/advanced therapy pricing:
        - Common diseases (>500K patients): ~$4,000-5,000/month
        - Less common (100K-500K): ~$5,000-7,000/month
        - Rare diseases (10K-100K): ~$8,000-15,000/month
        - Ultra-rare (<10K): ~$20,000-50,000/month

        Args:
            prevalence: Total patient population
            therapeutic_area: Optional therapeutic area for adjustments

        Returns:
            Estimated monthly WAC in USD
        """
        if not prevalence or prevalence <= 0:
            return 5000.0  # Default mid-range estimate

        # Base WAC by prevalence tier
        if prevalence > 500000:
            # Common diseases (RA, psoriasis, etc.)
            base_wac = 4500.0
        elif prevalence > 100000:
            # Less common (SLE, AS, etc.)
            base_wac = 5500.0
        elif prevalence > 50000:
            # Moderately rare
            base_wac = 8000.0
        elif prevalence > 10000:
            # Rare diseases
            base_wac = 15000.0
        elif prevalence > 1000:
            # Very rare
            base_wac = 30000.0
        else:
            # Ultra-rare (<1000 patients)
            base_wac = 50000.0

        # Therapeutic area adjustments
        if therapeutic_area:
            ta_lower = therapeutic_area.lower()
            if "oncology" in ta_lower or "cancer" in ta_lower:
                base_wac *= 1.5  # Oncology typically higher
            elif "gene therapy" in ta_lower or "cell therapy" in ta_lower:
                base_wac *= 3.0  # CGT much higher
            elif "neurology" in ta_lower:
                base_wac *= 1.2  # Neuro slightly higher

        return round(base_wac, 2)

    def get_diseases_needing_population(
        self,
        disease_names: List[str],
        min_quality: str = "Medium",
    ) -> List[str]:
        """
        Filter a list of diseases to only those needing population.

        Args:
            disease_names: List of disease names to check
            min_quality: Minimum quality level to consider "populated" (High, Medium, Low)

        Returns:
            List of disease names that need population
        """
        quality_levels = {"High": 3, "Medium": 2, "Low": 1}
        min_quality_level = quality_levels.get(min_quality, 2)

        needs_population = []
        for disease_name in disease_names:
            existing = self.repository.get_disease(disease_name)
            if not existing:
                needs_population.append(disease_name)
            elif not existing.data_quality:
                needs_population.append(disease_name)
            elif quality_levels.get(existing.data_quality, 0) < min_quality_level:
                needs_population.append(disease_name)

        return needs_population


def create_disease_intelligence_service(db) -> DiseaseIntelligenceService:
    """
    Factory function to create a fully configured DiseaseIntelligenceService.

    Args:
        db: Database connection

    Returns:
        Configured DiseaseIntelligenceService
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from src.tools.pubmed import PubMedAPI
    from src.tools.semantic_scholar import SemanticScholarAPI
    from src.tools.web_search import create_web_searcher
    from src.case_series.protocols.llm_protocol import LLMClient

    # Create searchers
    pubmed = PubMedAPI()
    semantic_scholar = SemanticScholarAPI()
    web_searcher = create_web_searcher()

    # Create LLM client (reuse existing)
    # This needs to be configured based on your setup
    llm_client = None  # TODO: Configure based on your LLM setup

    # Create repository
    repository = DiseaseIntelligenceRepository(db)

    return DiseaseIntelligenceService(
        pubmed_searcher=pubmed,
        semantic_scholar_searcher=semantic_scholar,
        web_searcher=web_searcher,
        llm_client=llm_client,
        repository=repository,
    )
