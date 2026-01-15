"""
Case Series Analysis Orchestrator

Main entry point that coordinates all services for drug repurposing analysis.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Set

from src.case_series.models import (
    CaseSeriesExtraction,
    RepurposingOpportunity,
    DrugAnalysisResult,
    OpportunityScores,
    MarketIntelligence,
    AggregateScore,
    PaperForManualReview,
)
from src.case_series.services.drug_info_service import DrugInfoService, DrugInfo
from src.case_series.services.literature_search_service import LiteratureSearchService, Paper, SearchResult
from src.case_series.services.extraction_service import ExtractionService
from src.case_series.services.market_intel_service import MarketIntelService
from src.case_series.services.disease_standardizer import DiseaseStandardizer
from src.case_series.services.score_explanation_service import ScoreExplanationService
from src.case_series.services.preprint_search_service import PreprintSearchService
from src.case_series.services.aggregation_service import (
    get_disease_aggregations_dict,
    get_opportunities_by_disease,
)
from src.case_series.scoring.scoring_engine import ScoringEngine
from src.case_series.scoring.case_series_scorer import CaseSeriesScorer
from src.case_series.repositories.case_series_repository import CaseSeriesRepository

logger = logging.getLogger(__name__)


@dataclass
class AnalysisProgress:
    """Tracks analysis progress for UI updates."""
    status: str = "initializing"
    current_step: str = ""
    papers_found: int = 0
    papers_extracted: int = 0
    opportunities_found: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


@dataclass
class AnalysisConfig:
    """Configuration for analysis run."""
    max_papers_per_source: int = 500  # High default to get all available papers
    max_papers_to_extract: Optional[int] = None  # None = extract all found papers
    max_total_discovered_papers: Optional[int] = None  # Limit total papers before filtering (for testing)
    filter_with_llm: bool = True
    use_cache: bool = True
    enrich_market_data: bool = True
    # Reduced from 5, increased from 2 to 3 (Haiku filtering reduces Sonnet load)
    max_concurrent_extractions: int = 3
    # Source selection (for testing - disable expensive sources)
    use_pubmed: bool = True
    use_semantic_scholar: bool = True
    use_citation_mining: bool = True
    use_web_search: bool = True
    # Supplemental mode: skip papers already processed in previous runs
    supplemental: bool = False


@dataclass
class PaperWithFilterStatus:
    """Paper with filter evaluation status."""
    paper: Paper
    would_pass_filter: bool = False
    filter_reason: str = ""
    disease: str = ""
    patient_count: Optional[int] = None


@dataclass
class PaperDiscoveryResult:
    """Result of paper discovery with filter evaluation."""
    drug_name: str
    generic_name: Optional[str] = None
    total_papers: int = 0
    papers_by_disease: Dict[str, List[PaperWithFilterStatus]] = field(default_factory=dict)
    unclassified_papers: List[PaperWithFilterStatus] = field(default_factory=list)
    approved_indications: List[str] = field(default_factory=list)
    sources_searched: List[str] = field(default_factory=list)
    papers_passing_filter: int = 0
    duplicates_removed: int = 0


class CaseSeriesOrchestrator:
    """
    Main orchestrator for case series analysis.

    Coordinates:
    1. Drug info retrieval
    2. Literature search
    3. Data extraction
    4. Disease standardization
    5. Market intelligence enrichment
    6. Opportunity scoring and ranking

    Each step can be called independently for testing.
    """

    def __init__(
        self,
        drug_info_service: DrugInfoService,
        literature_search_service: LiteratureSearchService,
        extraction_service: ExtractionService,
        market_intel_service: MarketIntelService,
        disease_standardizer: DiseaseStandardizer,
        scoring_engine: ScoringEngine,
        repository: Optional[CaseSeriesRepository] = None,
        preprint_search_service: Optional[PreprintSearchService] = None,
    ):
        """
        Initialize the orchestrator with all required services.

        Args:
            drug_info_service: Service for drug info retrieval
            literature_search_service: Service for literature search
            extraction_service: Service for data extraction
            market_intel_service: Service for market intelligence
            disease_standardizer: Service for disease name normalization
            scoring_engine: Engine for opportunity scoring
            repository: Optional repository for persistence
            preprint_search_service: Optional service for preprint search (bioRxiv/medRxiv)
        """
        self._drug_info_service = drug_info_service
        self._literature_search_service = literature_search_service
        self._preprint_search_service = preprint_search_service
        self._extraction_service = extraction_service
        self._market_intel_service = market_intel_service
        self._disease_standardizer = disease_standardizer
        self._scoring_engine = scoring_engine
        self._repository = repository
        self._case_series_scorer = CaseSeriesScorer()

        self._progress = AnalysisProgress()
        self._run_id: Optional[str] = None

    @property
    def progress(self) -> AnalysisProgress:
        """Get current analysis progress."""
        return self._progress

    async def analyze(
        self,
        drug_name: str,
        config: Optional[AnalysisConfig] = None,
    ) -> DrugAnalysisResult:
        """
        Run full analysis pipeline for a drug.

        Args:
            drug_name: Name of the drug to analyze
            config: Optional analysis configuration

        Returns:
            DrugAnalysisResult with all opportunities
        """
        config = config or AnalysisConfig()
        self._progress = AnalysisProgress(status="running")

        # Create run in database
        if self._repository:
            self._run_id = self._repository.create_run(
                drug_name=drug_name,
                parameters={
                    'max_papers': config.max_papers_per_source,
                    'filter_with_llm': config.filter_with_llm,
                    'enrich_market_data': config.enrich_market_data,
                }
            )

        try:
            # Step 1: Get drug info
            self._progress.current_step = "Getting drug information"
            drug_info = await self.get_drug_info(drug_name)

            # Step 2: Search literature (with generic name for better coverage)
            self._progress.current_step = "Searching literature"
            logger.info(f"Analysis config: max_papers_per_source={config.max_papers_per_source}, "
                       f"max_papers_to_extract={config.max_papers_to_extract}, "
                       f"max_total_discovered={config.max_total_discovered_papers}, "
                       f"sources=[pubmed={config.use_pubmed}, semantic_scholar={config.use_semantic_scholar}, "
                       f"citation_mining={config.use_citation_mining}, web={config.use_web_search}], "
                       f"enrich_market_data={config.enrich_market_data}, "
                       f"supplemental={config.supplemental}")

            # Supplemental mode: get PMIDs to skip BEFORE expensive LLM filtering
            skip_pmids = None
            if config.supplemental and self._repository and self._repository._db:
                self._progress.current_step = "Loading previously processed papers"
                skip_pmids = self._repository._db.get_processed_pmids(drug_name)
                if skip_pmids:
                    logger.info(f"Supplemental mode: Will skip {len(skip_pmids)} already-processed papers BEFORE filtering")
                else:
                    logger.info(f"Supplemental mode: No previously processed papers found for {drug_name}")

            # Create checkpoint callback to save progress every 50 batches
            def filter_checkpoint_callback(papers_so_far: list, batch_num: int):
                """Save filtered papers checkpoint to database."""
                if not self._repository or not self._repository._db:
                    return
                try:
                    papers_for_checkpoint = []
                    for p in papers_so_far:
                        patient_count = getattr(p, 'extracted_patient_count', None)
                        if patient_count is not None:
                            try:
                                patient_count = int(patient_count)
                            except (ValueError, TypeError):
                                patient_count = None
                        papers_for_checkpoint.append({
                            'pmid': p.pmid,
                            'doi': p.doi,
                            'title': p.title,
                            'abstract': p.abstract,
                            'year': p.year,
                            'journal': p.journal,
                            'source': p.source,
                            'disease': getattr(p, 'extracted_disease', None),
                            'patient_count': patient_count,
                            'would_pass_filter': True,
                            'filter_reason': f'Passed filter (checkpoint at batch {batch_num})',
                        })
                    # Save checkpoint
                    self._repository.save_paper_discovery(
                        drug_name=drug_name,
                        generic_name=drug_info.generic_name,
                        papers=papers_for_checkpoint,
                        approved_indications=drug_info.approved_indications,
                        sources_searched=['checkpoint'],
                        duplicates_removed=0,
                    )
                    logger.info(f"Checkpoint saved: {len(papers_for_checkpoint)} papers at batch {batch_num}")
                except Exception as e:
                    logger.warning(f"Checkpoint save failed at batch {batch_num}: {e}")

            search_result = await self.search_literature(
                drug_name=drug_name,
                exclude_indications=drug_info.approved_indications,
                max_per_source=config.max_papers_per_source,
                max_total_papers=config.max_total_discovered_papers,
                filter_with_llm=config.filter_with_llm,
                generic_name=drug_info.generic_name,
                use_pubmed=config.use_pubmed,
                use_semantic_scholar=config.use_semantic_scholar,
                use_citation_mining=config.use_citation_mining,
                use_web_search=config.use_web_search,
                skip_pmids=skip_pmids,  # Skip these BEFORE LLM filter
                filter_checkpoint_callback=filter_checkpoint_callback,
            )
            self._progress.papers_found = len(search_result.papers)

            # Save discovered papers to database for future supplemental runs
            # This saves the papers that passed the Haiku filter
            if self._repository and self._repository._db and search_result.papers:
                try:
                    papers_for_db = []
                    for p in search_result.papers:
                        # Handle patient_count - ensure it's an integer or None
                        patient_count = getattr(p, 'extracted_patient_count', None)
                        if patient_count is not None:
                            try:
                                patient_count = int(patient_count)
                            except (ValueError, TypeError):
                                patient_count = None  # Can't convert, set to None

                        papers_for_db.append({
                            'pmid': p.pmid,
                            'doi': p.doi,
                            'title': p.title,
                            'abstract': p.abstract,
                            'year': p.year,
                            'journal': p.journal,
                            'source': p.source,
                            'disease': getattr(p, 'extracted_disease', None),
                            'patient_count': patient_count,
                            'would_pass_filter': True,  # These all passed the LLM filter
                            'filter_reason': 'Passed Haiku filter in analyze()',
                        })
                    discovery_id = self._repository.save_paper_discovery(
                        drug_name=drug_name,
                        generic_name=drug_info.generic_name,
                        papers=papers_for_db,
                        approved_indications=drug_info.approved_indications,
                        sources_searched=search_result.sources_searched,
                        duplicates_removed=search_result.duplicates_removed,
                    )
                    if discovery_id:
                        logger.info(f"Saved {len(papers_for_db)} papers to discovery cache for future supplemental runs")
                except Exception as e:
                    logger.warning(f"Failed to save paper discovery: {e}")

            # Step 3: Extract data
            self._progress.current_step = "Extracting clinical data"
            papers_to_extract = search_result.papers

            # Sort by relevance_score (patient count / 100) so high-N papers are extracted first
            papers_to_extract = sorted(
                papers_to_extract,
                key=lambda p: (p.relevance_score or 0, p.pmid or ''),
                reverse=True
            )
            logger.info(f"Sorted {len(papers_to_extract)} papers by relevance (top 5 scores: {[p.relevance_score for p in papers_to_extract[:5]]})")

            # Pre-filter: Skip papers where Haiku already identified an approved indication
            # This saves expensive Sonnet extraction calls
            approved_lower = [ind.lower() for ind in drug_info.approved_indications]
            pre_filter_count = len(papers_to_extract)

            def is_likely_off_label(paper) -> bool:
                """Check if paper's extracted disease is likely off-label."""
                raw_disease = getattr(paper, 'extracted_disease', '') or ''
                # Handle case where extracted_disease is a list
                if isinstance(raw_disease, list):
                    raw_disease = ', '.join(str(d) for d in raw_disease) if raw_disease else ''
                disease = raw_disease.lower()
                if not disease:
                    # No disease extracted by Haiku - skip to avoid wasted Sonnet extraction
                    logger.debug(f"Pre-filter excluding {paper.pmid}: No disease extracted by Haiku")
                    return False
                # Check if disease matches any approved indication
                for approved in approved_lower:
                    if approved in disease or disease in approved:
                        logger.debug(f"Pre-filter excluding {paper.pmid}: '{disease}' matches approved '{approved}'")
                        return False
                return True

            papers_to_extract = [p for p in papers_to_extract if is_likely_off_label(p)]
            skipped_count = pre_filter_count - len(papers_to_extract)
            if skipped_count > 0:
                logger.info(f"Pre-filter: Skipped {skipped_count} papers (no disease or approved indication), {len(papers_to_extract)} remaining for extraction")

            if config.max_papers_to_extract and len(papers_to_extract) > config.max_papers_to_extract:
                logger.info(f"Limiting extraction to {config.max_papers_to_extract} papers (found {len(papers_to_extract)})")
                papers_to_extract = papers_to_extract[:config.max_papers_to_extract]

            extractions = await self.extract_data(
                papers=papers_to_extract,
                drug_info=drug_info,
                use_cache=config.use_cache,
                max_concurrent=config.max_concurrent_extractions,
            )
            self._progress.papers_extracted = len(extractions)

            # Filter to relevant extractions only
            relevant_extractions = [e for e in extractions if e.is_relevant]

            # Step 4: Standardize disease names
            self._progress.current_step = "Standardizing disease names"
            extractions = self.standardize_diseases(relevant_extractions)

            # Step 4.5: Compute individual and aggregate scores
            self._progress.current_step = "Computing study quality scores"
            aggregate_scores = self.compute_individual_and_aggregate_scores(extractions)

            # Step 5: Build opportunities with aggregate scores
            opportunities = []
            for ext in extractions:
                disease = ext.disease_normalized or ext.disease
                opp = RepurposingOpportunity(extraction=ext)
                # Attach aggregate score for this disease
                if disease and disease in aggregate_scores:
                    opp.aggregate_score = aggregate_scores[disease]
                opportunities.append(opp)

            # Step 6: Enrich with market data
            if config.enrich_market_data:
                self._progress.current_step = "Gathering market intelligence"
                opportunities = await self.enrich_with_market_data(opportunities)

            # Step 7: Score and rank
            self._progress.current_step = "Scoring opportunities"
            opportunities = self.score_and_rank(opportunities)
            self._progress.opportunities_found = len(opportunities)

            # Step 8: Save opportunities to database
            if self._repository and self._run_id:
                self._progress.current_step = "Saving opportunities"
                for opp in opportunities:
                    try:
                        self._repository.save_opportunity(
                            run_id=self._run_id,
                            drug_name=drug_name,
                            opportunity=opp,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to save opportunity: {e}")
                logger.info(f"Saved {len(opportunities)} opportunities to database")

            # Step 8.5: Assign parent diseases for hierarchy display
            self._progress.current_step = "Assigning disease hierarchy"
            self._disease_standardizer.assign_parent_diseases(extractions)

            # Update extractions and opportunities with parent disease
            if self._repository and self._run_id:
                for ext in extractions:
                    if ext.source and ext.source.pmid:
                        parent = getattr(ext, 'parent_disease', None)
                        try:
                            self._repository.update_extraction_parent_disease(
                                run_id=self._run_id,
                                pmid=ext.source.pmid,
                                parent_disease=parent,
                            )
                        except Exception as e:
                            logger.debug(f"Could not update parent disease for {ext.source.pmid}: {e}")

                for opp in opportunities:
                    disease = opp.extraction.disease_normalized or opp.extraction.disease
                    parent = self._disease_standardizer.get_parent_disease(disease) if disease else None
                    if parent and parent.lower() == disease.lower():
                        parent = None  # Don't set parent if same as disease
                    try:
                        self._repository.update_opportunity_parent_disease(
                            run_id=self._run_id,
                            drug_name=drug_name,
                            disease=disease,
                            parent_disease=parent,
                        )
                    except Exception as e:
                        logger.debug(f"Could not update opportunity parent disease: {e}")

            # Step 8.6: Generate score explanations (using Haiku for cost efficiency)
            self._progress.current_step = "Generating score explanations"
            try:
                # Use Haiku client for explanations (from literature search service)
                haiku_client = getattr(self._literature_search_service, '_filter_llm_client', None)
                if haiku_client and opportunities:
                    explanation_service = ScoreExplanationService(llm_client=haiku_client)

                    # Build aggregations for explanations
                    disease_aggregations = get_disease_aggregations_dict(opportunities)
                    opportunities_by_disease = get_opportunities_by_disease(opportunities)

                    # Generate explanations
                    explanations = await explanation_service.generate_all_explanations(
                        drug_name=drug_name,
                        disease_aggregations=disease_aggregations,
                        opportunities_by_disease=opportunities_by_disease,
                        include_paper_explanations=True,  # Generate per-paper explanations too
                    )

                    # Save explanations to database
                    if self._repository and self._run_id:
                        for disease, result in explanations.items():
                            parent = self._disease_standardizer.get_parent_disease(disease)
                            if parent.lower() == disease.lower():
                                parent = None

                            # Build input summary for debugging/regeneration
                            agg = disease_aggregations.get(disease)
                            input_summary = {
                                'n_studies': agg.n_studies if agg else 0,
                                'total_patients': agg.total_patients if agg else 0,
                                'pooled_response_pct': agg.pooled_response_pct if agg else None,
                                'avg_clinical_score': agg.avg_clinical_score if agg else 0,
                                'avg_evidence_score': agg.avg_evidence_score if agg else 0,
                                'avg_market_score': agg.avg_market_score if agg else 0,
                            }

                            try:
                                self._repository.save_score_explanation(
                                    run_id=self._run_id,
                                    drug_name=drug_name,
                                    disease=disease,
                                    parent_disease=parent,
                                    explanation=result.explanation,
                                    input_summary=input_summary,
                                    model=result.model,
                                    tokens=result.tokens_used,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to save explanation for {disease}: {e}")

                        # Save per-paper explanations
                        for opp in opportunities:
                            if opp.extraction and opp.extraction.score_explanation:
                                pmid = opp.extraction.source.pmid if opp.extraction.source else None
                                if pmid:
                                    try:
                                        self._repository.save_paper_explanation(
                                            run_id=self._run_id,
                                            pmid=pmid,
                                            explanation=opp.extraction.score_explanation,
                                        )
                                    except Exception as e:
                                        logger.debug(f"Could not save paper explanation: {e}")

                    logger.info(f"Generated {len(explanations)} score explanations")
                else:
                    logger.info("Skipping explanation generation (no Haiku client or no opportunities)")
            except Exception as e:
                logger.warning(f"Score explanation generation failed: {e}")
                # Non-fatal - continue without explanations

            # Calculate estimated cost (Claude Sonnet pricing: $3/M input, $15/M output)
            input_tokens = self._extraction_service.metrics.input_tokens
            output_tokens = self._extraction_service.metrics.output_tokens
            estimated_cost = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)

            # Step 9: Identify papers that need manual review (abstract-only)
            self._progress.current_step = "Identifying papers for manual review"
            papers_for_review = await self.identify_papers_for_manual_review(
                extractions=extractions,
                papers=papers_to_extract,
                drug_name=drug_name,
                use_haiku_extraction=True,
            )

            # Save papers for manual review to database
            if self._repository and self._run_id and papers_for_review:
                try:
                    saved_count = self._repository.save_papers_for_manual_review(
                        run_id=self._run_id,
                        drug_name=drug_name,
                        papers=papers_for_review,
                    )
                    logger.info(f"Saved {saved_count} papers for manual review to database")
                except Exception as e:
                    logger.warning(f"Failed to save papers for manual review: {e}")

            # Build result
            result = DrugAnalysisResult(
                drug_name=drug_name,
                generic_name=drug_info.generic_name,
                mechanism=drug_info.mechanism,
                target=drug_info.target,
                approved_indications=drug_info.approved_indications,
                opportunities=opportunities,
                papers_for_manual_review=papers_for_review,
                analysis_date=datetime.now(),
                search_queries_used=search_result.queries_used,
                papers_screened=search_result.total_found,
                papers_extracted=len(extractions),
                total_input_tokens=input_tokens,
                total_output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost,
            )

            # Update run status
            self._progress.status = "completed"
            if self._repository and self._run_id:
                self._repository.update_run(
                    run_id=self._run_id,
                    status="completed",
                    papers_found=len(search_result.papers),
                    papers_extracted=len(extractions),
                    opportunities_found=len(opportunities),
                )

            return result

        except Exception as e:
            self._progress.status = "failed"
            logger.error(f"Analysis failed: {e}")

            if self._repository and self._run_id:
                self._repository.update_run(
                    run_id=self._run_id,
                    status="failed",
                )

            raise

    async def analyze_with_selected_papers(
        self,
        drug_name: str,
        papers: List[Paper],
        config: Optional[AnalysisConfig] = None,
    ) -> DrugAnalysisResult:
        """
        Run analysis pipeline using user-selected papers instead of automatic search/filter.

        This method bypasses the search and LLM filter steps, allowing users to
        manually select which papers to include in the analysis.

        Args:
            drug_name: Name of the drug to analyze
            papers: List of papers to extract (user-selected)
            config: Optional analysis configuration

        Returns:
            DrugAnalysisResult with all opportunities
        """
        config = config or AnalysisConfig()
        self._progress = AnalysisProgress(status="running")

        # Create run in database
        if self._repository:
            self._run_id = self._repository.create_run(
                drug_name=drug_name,
                parameters={
                    'max_papers': len(papers),
                    'user_selected': True,
                    'enrich_market_data': config.enrich_market_data,
                }
            )

        try:
            # Step 1: Get drug info
            self._progress.current_step = "Getting drug information"
            drug_info = await self.get_drug_info(drug_name)

            # Step 2: Skip search - use provided papers
            self._progress.current_step = "Using user-selected papers"
            self._progress.papers_found = len(papers)
            logger.info(f"Analyzing {len(papers)} user-selected papers for {drug_name}")

            # Step 3: Extract data
            self._progress.current_step = "Extracting clinical data"
            papers_to_extract = papers
            if config.max_papers_to_extract and len(papers_to_extract) > config.max_papers_to_extract:
                logger.info(f"Limiting extraction to {config.max_papers_to_extract} papers (selected {len(papers_to_extract)})")
                papers_to_extract = papers_to_extract[:config.max_papers_to_extract]

            extractions = await self.extract_data(
                papers=papers_to_extract,
                drug_info=drug_info,
                use_cache=config.use_cache,
                max_concurrent=config.max_concurrent_extractions,
            )
            self._progress.papers_extracted = len(extractions)

            # Filter to relevant extractions only
            relevant_extractions = [e for e in extractions if e.is_relevant]

            # Step 4: Standardize disease names
            self._progress.current_step = "Standardizing disease names"
            extractions = self.standardize_diseases(relevant_extractions)

            # Step 4.5: Compute individual and aggregate scores
            self._progress.current_step = "Computing study quality scores"
            aggregate_scores = self.compute_individual_and_aggregate_scores(extractions)

            # Step 5: Build opportunities with aggregate scores
            opportunities = []
            for ext in extractions:
                disease = ext.disease_normalized or ext.disease
                opp = RepurposingOpportunity(extraction=ext)
                # Attach aggregate score for this disease
                if disease and disease in aggregate_scores:
                    opp.aggregate_score = aggregate_scores[disease]
                opportunities.append(opp)

            # Step 6: Enrich with market data
            if config.enrich_market_data:
                self._progress.current_step = "Gathering market intelligence"
                opportunities = await self.enrich_with_market_data(opportunities)

            # Step 7: Score and rank
            self._progress.current_step = "Scoring opportunities"
            opportunities = self.score_and_rank(opportunities)
            self._progress.opportunities_found = len(opportunities)

            # Step 8: Save opportunities to database
            if self._repository and self._run_id:
                self._progress.current_step = "Saving opportunities"
                for opp in opportunities:
                    try:
                        self._repository.save_opportunity(
                            run_id=self._run_id,
                            drug_name=drug_name,
                            opportunity=opp,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to save opportunity: {e}")
                logger.info(f"Saved {len(opportunities)} opportunities to database")

            # Step 8.5: Assign parent diseases for hierarchy display
            self._progress.current_step = "Assigning disease hierarchy"
            self._disease_standardizer.assign_parent_diseases(extractions)

            # Update extractions and opportunities with parent disease
            if self._repository and self._run_id:
                for ext in extractions:
                    if ext.source and ext.source.pmid:
                        parent = getattr(ext, 'parent_disease', None)
                        try:
                            self._repository.update_extraction_parent_disease(
                                run_id=self._run_id,
                                pmid=ext.source.pmid,
                                parent_disease=parent,
                            )
                        except Exception as e:
                            logger.debug(f"Could not update parent disease for {ext.source.pmid}: {e}")

                for opp in opportunities:
                    disease = opp.extraction.disease_normalized or opp.extraction.disease
                    parent = self._disease_standardizer.get_parent_disease(disease) if disease else None
                    if parent and parent.lower() == disease.lower():
                        parent = None
                    try:
                        self._repository.update_opportunity_parent_disease(
                            run_id=self._run_id,
                            drug_name=drug_name,
                            disease=disease,
                            parent_disease=parent,
                        )
                    except Exception as e:
                        logger.debug(f"Could not update opportunity parent disease: {e}")

            # Step 8.6: Generate score explanations (using Haiku for cost efficiency)
            self._progress.current_step = "Generating score explanations"
            try:
                haiku_client = getattr(self._literature_search_service, '_filter_llm_client', None)
                if haiku_client and opportunities:
                    explanation_service = ScoreExplanationService(llm_client=haiku_client)

                    disease_aggregations = get_disease_aggregations_dict(opportunities)
                    opportunities_by_disease = get_opportunities_by_disease(opportunities)

                    explanations = await explanation_service.generate_all_explanations(
                        drug_name=drug_name,
                        disease_aggregations=disease_aggregations,
                        opportunities_by_disease=opportunities_by_disease,
                        include_paper_explanations=True,
                    )

                    if self._repository and self._run_id:
                        for disease, result in explanations.items():
                            parent = self._disease_standardizer.get_parent_disease(disease)
                            if parent.lower() == disease.lower():
                                parent = None

                            agg = disease_aggregations.get(disease)
                            input_summary = {
                                'n_studies': agg.n_studies if agg else 0,
                                'total_patients': agg.total_patients if agg else 0,
                                'pooled_response_pct': agg.pooled_response_pct if agg else None,
                                'avg_clinical_score': agg.avg_clinical_score if agg else 0,
                                'avg_evidence_score': agg.avg_evidence_score if agg else 0,
                                'avg_market_score': agg.avg_market_score if agg else 0,
                            }

                            try:
                                self._repository.save_score_explanation(
                                    run_id=self._run_id,
                                    drug_name=drug_name,
                                    disease=disease,
                                    parent_disease=parent,
                                    explanation=result.explanation,
                                    input_summary=input_summary,
                                    model=result.model,
                                    tokens=result.tokens_used,
                                )
                            except Exception as e:
                                logger.warning(f"Failed to save explanation for {disease}: {e}")

                        for opp in opportunities:
                            if opp.extraction and opp.extraction.score_explanation:
                                pmid = opp.extraction.source.pmid if opp.extraction.source else None
                                if pmid:
                                    try:
                                        self._repository.save_paper_explanation(
                                            run_id=self._run_id,
                                            pmid=pmid,
                                            explanation=opp.extraction.score_explanation,
                                        )
                                    except Exception as e:
                                        logger.debug(f"Could not save paper explanation: {e}")

                    logger.info(f"Generated {len(explanations)} score explanations")
                else:
                    logger.info("Skipping explanation generation (no Haiku client or no opportunities)")
            except Exception as e:
                logger.warning(f"Score explanation generation failed: {e}")

            # Calculate estimated cost (Claude Sonnet pricing: $3/M input, $15/M output)
            input_tokens = self._extraction_service.metrics.input_tokens
            output_tokens = self._extraction_service.metrics.output_tokens
            estimated_cost = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)

            # Identify papers that need manual review (abstract-only)
            papers_for_review = await self.identify_papers_for_manual_review(
                extractions=extractions,
                papers=papers,
                drug_name=drug_name,
                use_haiku_extraction=True,
            )

            # Save papers for manual review to database
            if self._repository and self._run_id and papers_for_review:
                try:
                    saved_count = self._repository.save_papers_for_manual_review(
                        run_id=self._run_id,
                        drug_name=drug_name,
                        papers=papers_for_review,
                    )
                    logger.info(f"Saved {saved_count} papers for manual review to database")
                except Exception as e:
                    logger.warning(f"Failed to save papers for manual review: {e}")

            # Build result
            result = DrugAnalysisResult(
                drug_name=drug_name,
                generic_name=drug_info.generic_name,
                mechanism=drug_info.mechanism,
                target=drug_info.target,
                approved_indications=drug_info.approved_indications,
                opportunities=opportunities,
                papers_for_manual_review=papers_for_review,
                analysis_date=datetime.now(),
                search_queries_used=["User-selected papers"],
                papers_screened=len(papers),
                papers_extracted=len(extractions),
                total_input_tokens=input_tokens,
                total_output_tokens=output_tokens,
                estimated_cost_usd=estimated_cost,
            )

            # Update run status
            self._progress.status = "completed"
            if self._repository and self._run_id:
                self._repository.update_run(
                    run_id=self._run_id,
                    status="completed",
                    papers_found=len(papers),
                    papers_extracted=len(extractions),
                    opportunities_found=len(opportunities),
                )

            return result

        except Exception as e:
            self._progress.status = "failed"
            logger.error(f"Analysis failed: {e}")

            if self._repository and self._run_id:
                self._repository.update_run(
                    run_id=self._run_id,
                    status="failed",
                )

            raise

    # -------------------------------------------------------------------------
    # Individual Steps (for testing and incremental use)
    # -------------------------------------------------------------------------

    async def get_drug_info(self, drug_name: str) -> DrugInfo:
        """
        Step 1: Get approved indications for a drug.

        Args:
            drug_name: Name of the drug

        Returns:
            DrugInfo with mechanism, target, and approved indications
        """
        return await self._drug_info_service.get_drug_info(drug_name)

    async def search_literature(
        self,
        drug_name: str,
        exclude_indications: List[str] = None,
        max_per_source: int = 100,
        max_total_papers: Optional[int] = None,
        filter_with_llm: bool = True,
        generic_name: Optional[str] = None,
        use_pubmed: bool = True,
        use_semantic_scholar: bool = True,
        use_citation_mining: bool = True,
        use_web_search: bool = True,
        skip_pmids: Optional[Set[str]] = None,
        filter_checkpoint_callback: callable = None,
    ) -> SearchResult:
        """
        Step 2: Search for case series in literature.

        Args:
            drug_name: Name of the drug
            exclude_indications: List of approved indications to exclude
            max_per_source: Max results per search source
            max_total_papers: Limit total papers before filtering (for testing)
            filter_with_llm: Whether to use LLM for relevance filtering
            generic_name: Generic name of drug (searches both if different from drug_name)
            use_pubmed: Whether to search PubMed
            use_semantic_scholar: Whether to search Semantic Scholar
            use_citation_mining: Whether to mine citations from reviews
            use_web_search: Whether to search web sources
            skip_pmids: Set of PMIDs to skip (already processed in previous runs)
            filter_checkpoint_callback: Optional callback(papers, batch_num) for saving progress every 50 batches

        Returns:
            SearchResult with filtered papers
        """
        return await self._literature_search_service.search(
            drug_name=drug_name,
            exclude_indications=exclude_indications or [],
            max_results_per_source=max_per_source,
            max_total_papers=max_total_papers,
            filter_with_llm=filter_with_llm,
            include_citation_mining=use_citation_mining,
            generic_name=generic_name,
            use_pubmed=use_pubmed,
            use_semantic_scholar=use_semantic_scholar,
            use_web_search=use_web_search,
            skip_pmids=skip_pmids,
            filter_checkpoint_callback=filter_checkpoint_callback,
        )

    async def search_preprint_literature(
        self,
        drug_name: str,
        generic_name: Optional[str] = None,
        approved_indications: Optional[List[str]] = None,
        max_results: int = 200,
        server: str = "both",
        years_back: int = 2,
        apply_llm_filter: bool = True,
        standard_papers: Optional[List[Paper]] = None,
    ) -> SearchResult:
        """
        Search preprint servers (bioRxiv/medRxiv) for case series papers.

        This is a separate, optional search that can be run independently
        of the standard literature search. Results are returned separately
        and should be displayed in a dedicated preprint tab.

        Args:
            drug_name: Brand name of drug
            generic_name: Generic name (if different from brand)
            approved_indications: List of approved indications to exclude
            max_results: Maximum papers to return
            server: "biorxiv", "medrxiv", or "both"
            years_back: Number of years back to search (default: 2)
            apply_llm_filter: Whether to apply LLM-based filtering
            standard_papers: Optional list of papers from standard search
                            (used to deduplicate preprints with published versions)

        Returns:
            SearchResult with preprint papers
        """
        if not self._preprint_search_service:
            logger.warning("Preprint search service not configured")
            return SearchResult(
                papers=[],
                queries_used=[],
                sources_searched=["bioRxiv", "medRxiv"],
                total_found=0,
                duplicates_removed=0
            )

        # Run preprint search
        result = await self._preprint_search_service.search(
            drug_name=drug_name,
            generic_name=generic_name,
            approved_indications=approved_indications or [],
            max_results=max_results,
            server=server,
            years_back=years_back,
            apply_llm_filter=apply_llm_filter,
        )

        # Deduplicate with standard papers if provided
        if standard_papers and result.papers:
            original_count = len(result.papers)
            result.papers = self._preprint_search_service.deduplicate_with_published(
                preprint_papers=result.papers,
                standard_papers=standard_papers,
            )
            dedup_count = original_count - len(result.papers)
            result.duplicates_removed += dedup_count
            logger.info(f"Removed {dedup_count} preprints with published versions")

        self._progress.status = "preprint_search_complete"
        logger.info(
            f"Preprint search complete: {len(result.papers)} papers "
            f"from {', '.join(result.sources_searched)}"
        )

        return result

    async def extract_data(
        self,
        papers: List[Paper],
        drug_info: DrugInfo,
        use_cache: bool = True,
        max_concurrent: int = 5,
    ) -> List[CaseSeriesExtraction]:
        """
        Step 3: Extract structured data from papers.

        Saves each extraction to database immediately as it completes (like V2 agent)
        for real-time visibility and failure recovery.

        Args:
            papers: List of papers to extract
            drug_info: Drug information
            use_cache: Whether to use extraction cache
            max_concurrent: Max concurrent extractions

        Returns:
            List of extractions
        """
        # Create callback to save each extraction immediately (like V2)
        # Only save relevant extractions to avoid cluttering database
        def save_extraction_callback(extraction: CaseSeriesExtraction, drug_name: str):
            if self._repository and self._run_id:
                # Get paper identifier - prefer PMID, fallback to DOI
                pmid = extraction.source.pmid if extraction.source else None
                doi = extraction.source.doi if extraction.source else None

                # Use DOI as fallback identifier if no PMID
                paper_id = pmid
                if not paper_id and doi:
                    paper_id = f"DOI:{doi}"
                    logger.info(f"Using DOI as identifier for paper: {doi}")

                if paper_id:
                    try:
                        # Save extraction (including non-relevant ones for future skip optimization)
                        self._repository.save_extraction(
                            drug_name=drug_name,
                            pmid=paper_id,
                            extraction_data=extraction.model_dump(),
                            run_id=self._run_id,
                        )
                        if extraction.is_relevant:
                            logger.info(f"Saved extraction for {paper_id} (disease: {extraction.disease})")
                        else:
                            logger.info(f"Saved non-relevant extraction for {paper_id} (reason: {extraction.disease}) - will skip in future runs")

                        # Save additional diseases as separate extractions (only for relevant papers)
                        if extraction.is_relevant and extraction.additional_diseases:
                            for add_disease in extraction.additional_diseases:
                                # Create a copy of extraction with the additional disease
                                add_extraction_data = extraction.model_dump()

                                # Override disease identification
                                add_extraction_data['disease'] = add_disease.disease
                                add_extraction_data['disease_subtype'] = add_disease.disease_subtype
                                add_extraction_data['disease_category'] = add_disease.disease_category
                                add_extraction_data['additional_diseases'] = []  # Clear to avoid recursion

                                # Override patient population if specified for this disease
                                if add_disease.n_patients is not None:
                                    add_extraction_data['patient_population']['n_patients'] = add_disease.n_patients
                                if add_disease.patient_description:
                                    add_extraction_data['patient_population']['description'] = add_disease.patient_description
                                if add_disease.disease_severity:
                                    add_extraction_data['patient_population']['disease_severity'] = add_disease.disease_severity

                                # Override disease-specific efficacy data
                                if add_disease.response_rate:
                                    add_extraction_data['efficacy']['response_rate'] = add_disease.response_rate
                                if add_disease.responders_n is not None:
                                    add_extraction_data['efficacy']['responders_n'] = add_disease.responders_n
                                if add_disease.responders_pct is not None:
                                    add_extraction_data['efficacy']['responders_pct'] = add_disease.responders_pct
                                if add_disease.primary_endpoint:
                                    add_extraction_data['efficacy']['primary_endpoint'] = add_disease.primary_endpoint
                                if add_disease.endpoint_result:
                                    add_extraction_data['efficacy']['endpoint_result'] = add_disease.endpoint_result
                                if add_disease.efficacy_summary:
                                    add_extraction_data['efficacy']['efficacy_summary'] = add_disease.efficacy_summary

                                # Override efficacy signal if specified
                                if add_disease.efficacy_signal:
                                    add_extraction_data['efficacy_signal'] = add_disease.efficacy_signal

                                # Override follow-up and findings if specified
                                if add_disease.follow_up_duration:
                                    add_extraction_data['follow_up_duration'] = add_disease.follow_up_duration
                                if add_disease.key_findings:
                                    add_extraction_data['key_findings'] = add_disease.key_findings

                                self._repository.save_extraction(
                                    drug_name=drug_name,
                                    pmid=paper_id,
                                    extraction_data=add_extraction_data,
                                    run_id=self._run_id,
                                )
                                logger.info(f"Saved additional disease extraction for {paper_id} (disease: {add_disease.disease}, n={add_disease.n_patients}, responders_pct={add_disease.responders_pct})")
                    except Exception as e:
                        logger.warning(f"Failed to save extraction for {paper_id}: {e}")
                else:
                    # No PMID or DOI - cannot save
                    title = extraction.source.title if extraction.source else "Unknown"
                    logger.warning(f"Cannot save extraction - no PMID or DOI for paper: {title[:100]}")

        extractions = await self._extraction_service.extract_batch(
            papers=papers,
            drug_info=drug_info,
            use_cache=use_cache,
            max_concurrent=max_concurrent,
            on_extraction_complete=save_extraction_callback if (self._repository and self._run_id) else None,
        )

        return extractions

    def standardize_diseases(
        self,
        extractions: List[CaseSeriesExtraction],
    ) -> List[CaseSeriesExtraction]:
        """
        Step 4: Standardize disease names.

        Args:
            extractions: List of extractions

        Returns:
            Extractions with standardized disease names
        """
        for extraction in extractions:
            if extraction.disease:
                extraction.disease_normalized = self._disease_standardizer.standardize(
                    extraction.disease
                )
        return extractions

    async def identify_papers_for_manual_review(
        self,
        extractions: List[CaseSeriesExtraction],
        papers: List[Paper],
        drug_name: str,
        use_haiku_extraction: bool = True,
    ) -> List[PaperForManualReview]:
        """
        Identify papers that passed filters but were extracted from abstract only.

        These papers need manual review as they may contain important indications
        that couldn't be fully extracted without full text access.

        Args:
            extractions: List of extractions from the analysis
            papers: Original list of papers that were processed
            drug_name: Name of the drug being analyzed
            use_haiku_extraction: Whether to use Haiku to extract N from abstract

        Returns:
            List of PaperForManualReview objects, sorted by N (descending)
        """
        from src.case_series.services.extraction_service import extract_n_from_abstract_with_haiku

        manual_review_papers = []

        # Build a map of PMID -> extraction for quick lookup
        extraction_map = {}
        for ext in extractions:
            if ext.source and ext.source.pmid:
                extraction_map[ext.source.pmid] = ext

        # Build a map of PMID -> paper for original paper data
        paper_map = {}
        for paper in papers:
            if paper.pmid:
                paper_map[paper.pmid] = paper

        for ext in extractions:
            # Skip if this extraction used multi-stage (full text was available and used)
            if ext.extraction_method == 'multi_stage':
                continue

            # Check if this was an abstract-only extraction
            # Single-pass means either no full text available or full text was too short
            source = ext.source
            if not source:
                continue

            # Get the original paper to check full text availability
            original_paper = paper_map.get(source.pmid) if source.pmid else None
            had_full_text = original_paper.has_full_text if original_paper else False

            # Determine reason for manual review
            if had_full_text:
                reason = "Full text fetch failed - had PMCID but couldn't retrieve content"
            else:
                reason = "Abstract only - full text not available in PMC"

            # Create manual review entry
            review_paper = PaperForManualReview(
                pmid=source.pmid,
                doi=source.doi,
                title=source.title or "",
                authors=source.authors,
                journal=source.journal,
                year=source.year,
                abstract=original_paper.abstract if original_paper else None,
                disease=ext.disease_normalized or ext.disease,
                n_patients=ext.patient_population.n_patients if ext.patient_population else None,
                n_confidence="Medium" if (ext.patient_population and ext.patient_population.n_patients) else "Unknown",
                response_rate=ext.efficacy.response_rate if ext.efficacy else None,
                primary_endpoint=ext.efficacy.primary_endpoint if ext.efficacy else None,
                efficacy_mention=ext.efficacy.efficacy_summary if ext.efficacy else None,
                reason=reason,
                has_full_text=had_full_text,
                extraction_method=ext.extraction_method or "single_pass",
            )

            # If N is still unknown and we have an abstract, try Haiku extraction
            if use_haiku_extraction and review_paper.n_patients is None and review_paper.abstract:
                try:
                    haiku_client = getattr(self._literature_search_service, '_filter_llm_client', None)
                    if haiku_client:
                        haiku_result = await extract_n_from_abstract_with_haiku(
                            abstract=review_paper.abstract,
                            drug_name=drug_name,
                            llm_client=haiku_client,
                        )
                        if haiku_result.get('n_patients'):
                            review_paper.n_patients = haiku_result['n_patients']
                            review_paper.n_confidence = haiku_result.get('n_confidence', 'Medium')
                        if haiku_result.get('response_rate') and not review_paper.response_rate:
                            review_paper.response_rate = haiku_result['response_rate']
                        if haiku_result.get('primary_endpoint') and not review_paper.primary_endpoint:
                            review_paper.primary_endpoint = haiku_result['primary_endpoint']
                        if haiku_result.get('efficacy_mention') and not review_paper.efficacy_mention:
                            review_paper.efficacy_mention = haiku_result['efficacy_mention']
                except Exception as e:
                    logger.debug(f"Haiku extraction failed for {review_paper.pmid}: {e}")

            manual_review_papers.append(review_paper)

        # Sort by N (descending), with None values at the end
        manual_review_papers.sort(
            key=lambda p: (p.n_patients is not None, p.n_patients or 0),
            reverse=True
        )

        logger.info(f"Identified {len(manual_review_papers)} papers for manual review (abstract-only extractions)")

        return manual_review_papers

    def compute_individual_and_aggregate_scores(
        self,
        extractions: List[CaseSeriesExtraction],
    ) -> Dict[str, AggregateScore]:
        """
        Compute individual scores for each extraction and aggregate scores per disease.

        This method:
        1. Scores each individual extraction using the 6-dimension scoring system
        2. Groups extractions by normalized disease name
        3. Computes N-weighted aggregate scores for each disease

        Args:
            extractions: List of extractions (should already be standardized)

        Returns:
            Dict mapping disease name to AggregateScore
        """
        # Step 1: Score each individual extraction
        for extraction in extractions:
            if extraction.individual_score is None:
                extraction.individual_score = self._case_series_scorer.score_extraction(extraction)
                logger.debug(
                    f"Scored extraction {extraction.source.pmid if extraction.source else 'unknown'}: "
                    f"{extraction.individual_score.total_score}/10"
                )

        # Step 1b: Update extractions in database with individual scores
        if self._repository and self._run_id:
            for extraction in extractions:
                if extraction.source and extraction.source.pmid and extraction.individual_score:
                    try:
                        self._repository.save_extraction(
                            drug_name=extraction.treatment.drug_name if extraction.treatment else "",
                            pmid=extraction.source.pmid,
                            extraction_data=extraction.model_dump(),
                            run_id=self._run_id,
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update extraction score for {extraction.source.pmid}: {e}")

        # Step 2: Group extractions by disease
        disease_groups: Dict[str, List[CaseSeriesExtraction]] = {}
        for extraction in extractions:
            disease = extraction.disease_normalized or extraction.disease
            if not disease:
                continue
            if disease not in disease_groups:
                disease_groups[disease] = []
            disease_groups[disease].append(extraction)

        # Step 3: Compute aggregate scores per disease
        aggregate_scores: Dict[str, AggregateScore] = {}
        for disease, group in disease_groups.items():
            aggregate = self._case_series_scorer.score_aggregate(group)
            aggregate_scores[disease] = aggregate
            logger.info(
                f"Aggregate score for {disease}: {aggregate.aggregate_score}/10 "
                f"(N={aggregate.total_patients}, {aggregate.study_count} studies, "
                f"best paper: {aggregate.best_paper_pmid} @ {aggregate.best_paper_score}/10)"
            )

        return aggregate_scores

    async def enrich_with_market_data(
        self,
        opportunities: List[RepurposingOpportunity],
    ) -> List[RepurposingOpportunity]:
        """
        Step 5: Add market intelligence to opportunities.

        Args:
            opportunities: List of opportunities

        Returns:
            Opportunities with market intelligence added
        """
        # Group by disease to avoid duplicate lookups
        diseases = set()
        for opp in opportunities:
            disease = opp.extraction.disease_normalized or opp.extraction.disease
            if disease:
                diseases.add(disease)

        # Fetch market intel for each unique disease
        market_intel_cache: Dict[str, MarketIntelligence] = {}
        for disease in diseases:
            try:
                mi = await self._market_intel_service.get_market_intel(disease)
                market_intel_cache[disease] = mi

                # Also cache under parent disease
                parent = self._disease_standardizer.get_parent_disease(disease)
                if parent != disease:
                    market_intel_cache[parent] = mi

            except Exception as e:
                logger.warning(f"Failed to get market intel for {disease}: {e}")

        # Add market intel to opportunities
        for opp in opportunities:
            disease = opp.extraction.disease_normalized or opp.extraction.disease
            if disease and disease in market_intel_cache:
                opp.market_intelligence = market_intel_cache[disease]

        return opportunities

    def score_and_rank(
        self,
        opportunities: List[RepurposingOpportunity],
    ) -> List[RepurposingOpportunity]:
        """
        Step 6: Score and rank opportunities.

        Args:
            opportunities: List of opportunities

        Returns:
            Sorted list with scores and ranks
        """
        return self._scoring_engine.rank(opportunities)

    # -------------------------------------------------------------------------
    # Export Methods
    # -------------------------------------------------------------------------

    def export_to_excel(
        self,
        result: DrugAnalysisResult,
        output_path: str,
    ) -> str:
        """
        Export results to Excel file.

        Args:
            result: Analysis result
            output_path: Output file path

        Returns:
            Path to created file
        """
        # Import export functionality
        from src.case_series.export.excel_exporter import export_to_excel
        return export_to_excel(result, output_path)

    def export_to_json(
        self,
        result: DrugAnalysisResult,
        output_path: str,
    ) -> str:
        """
        Export results to JSON file.

        Args:
            result: Analysis result
            output_path: Output file path

        Returns:
            Path to created file
        """
        from src.case_series.export.json_exporter import export_to_json
        return export_to_json(result, output_path)

    # -------------------------------------------------------------------------
    # Mechanism-Based Analysis Methods
    # -------------------------------------------------------------------------

    async def analyze_mechanism(
        self,
        target: str,
        drug_names: List[str],
        config: Optional[AnalysisConfig] = None,
        max_concurrent_drugs: int = 3,
        progress_callback: Optional[callable] = None,
    ) -> "MechanismAnalysisResult":
        """
        Run case study analysis for multiple drugs sharing a mechanism.

        Analyzes drugs in parallel (up to max_concurrent_drugs) and aggregates
        all opportunities, ranking them together by mechanism.

        Args:
            target: The mechanism/target being analyzed (e.g., 'JAK1')
            drug_names: List of drug names to analyze
            config: Optional analysis configuration
            max_concurrent_drugs: Max drugs to analyze concurrently
            progress_callback: Optional callback for progress updates
                              Called with (drug_name, status, result_or_error)

        Returns:
            MechanismAnalysisResult with aggregated opportunities
        """
        import asyncio
        from src.models.case_series_schemas import MechanismAnalysisResult

        config = config or AnalysisConfig()
        all_opportunities: List[RepurposingOpportunity] = []
        drug_results: Dict[str, DrugAnalysisResult] = {}
        failed_drugs: Dict[str, str] = {}

        # Create semaphore for concurrent limit
        semaphore = asyncio.Semaphore(max_concurrent_drugs)

        async def analyze_drug(drug_name: str) -> Optional[DrugAnalysisResult]:
            """Analyze a single drug with semaphore limiting."""
            async with semaphore:
                try:
                    if progress_callback:
                        progress_callback(drug_name, "started", None)

                    result = await self.analyze(drug_name, config)

                    if progress_callback:
                        progress_callback(drug_name, "completed", result)

                    return result

                except Exception as e:
                    logger.error(f"Analysis failed for {drug_name}: {e}")
                    if progress_callback:
                        progress_callback(drug_name, "failed", str(e))
                    return None

        # Run analyses in parallel
        tasks = [analyze_drug(name) for name in drug_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        for drug_name, result in zip(drug_names, results):
            if isinstance(result, Exception):
                failed_drugs[drug_name] = str(result)
            elif result is None:
                failed_drugs[drug_name] = "Analysis returned no result"
            elif isinstance(result, DrugAnalysisResult):
                drug_results[drug_name] = result
                # Add drug name to each opportunity for tracking
                for opp in result.opportunities:
                    opp.extraction.treatment.drug_name = drug_name
                all_opportunities.extend(result.opportunities)

        # Re-rank all opportunities together
        if all_opportunities:
            all_opportunities = self._scoring_engine.rank(all_opportunities)

        # Calculate totals
        total_papers_screened = sum(r.papers_screened for r in drug_results.values())
        total_papers_extracted = sum(r.papers_extracted for r in drug_results.values())
        total_input_tokens = sum(r.total_input_tokens for r in drug_results.values())
        total_output_tokens = sum(r.total_output_tokens for r in drug_results.values())
        estimated_cost = (total_input_tokens * 3 / 1_000_000) + (total_output_tokens * 15 / 1_000_000)

        # Aggregate papers for manual review from all drug results
        all_papers_for_review: List[PaperForManualReview] = []
        for drug_result in drug_results.values():
            if drug_result.papers_for_manual_review:
                all_papers_for_review.extend(drug_result.papers_for_manual_review)

        # Sort by N (descending), with None values at the end
        all_papers_for_review.sort(
            key=lambda p: (p.n_patients is not None, p.n_patients or 0),
            reverse=True
        )

        return MechanismAnalysisResult(
            mechanism_target=target,
            drugs_analyzed=list(drug_results.keys()),
            drugs_failed=failed_drugs,
            opportunities=all_opportunities,
            drug_results=drug_results,
            papers_for_manual_review=all_papers_for_review,
            papers_screened=total_papers_screened,
            papers_extracted=total_papers_extracted,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            estimated_cost_usd=estimated_cost,
        )

    async def analyze_drugs_parallel(
        self,
        drug_names: List[str],
        config: Optional[AnalysisConfig] = None,
        max_concurrent: int = 3,
    ) -> List[DrugAnalysisResult]:
        """
        Run analysis for multiple drugs in parallel.

        Simpler version that just runs analyses and returns individual results.

        Args:
            drug_names: List of drug names to analyze
            config: Optional analysis configuration
            max_concurrent: Max concurrent analyses

        Returns:
            List of DrugAnalysisResult (successful only)
        """
        import asyncio

        config = config or AnalysisConfig()
        semaphore = asyncio.Semaphore(max_concurrent)
        results = []

        async def analyze_with_limit(drug_name: str):
            async with semaphore:
                try:
                    return await self.analyze(drug_name, config)
                except Exception as e:
                    logger.error(f"Analysis failed for {drug_name}: {e}")
                    return None

        tasks = [analyze_with_limit(name) for name in drug_names]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in task_results:
            if isinstance(result, DrugAnalysisResult):
                results.append(result)

        return results

    async def analyze_mechanism_with_selections(
        self,
        target: str,
        drug_papers: Dict[str, List[Paper]],
        config: Optional[AnalysisConfig] = None,
        max_concurrent_drugs: int = 3,
        progress_callback: Optional[callable] = None,
    ) -> "MechanismAnalysisResult":
        """
        Run case study analysis for multiple drugs using user-selected papers.

        Similar to analyze_mechanism but uses pre-selected papers instead of
        running the full search/filter pipeline.

        Args:
            target: The mechanism/target being analyzed (e.g., 'JAK1')
            drug_papers: Dict mapping drug_name -> List of user-selected papers
            config: Optional analysis configuration
            max_concurrent_drugs: Max drugs to analyze concurrently
            progress_callback: Optional callback for progress updates

        Returns:
            MechanismAnalysisResult with aggregated opportunities
        """
        import asyncio
        from src.models.case_series_schemas import MechanismAnalysisResult

        config = config or AnalysisConfig()
        all_opportunities: List[RepurposingOpportunity] = []
        drug_results: Dict[str, DrugAnalysisResult] = {}
        failed_drugs: Dict[str, str] = {}

        # Create semaphore for concurrent limit
        semaphore = asyncio.Semaphore(max_concurrent_drugs)

        async def analyze_drug(drug_name: str, papers: List[Paper]) -> Optional[DrugAnalysisResult]:
            """Analyze a single drug with user-selected papers."""
            async with semaphore:
                try:
                    if progress_callback:
                        progress_callback(drug_name, "started", None)

                    result = await self.analyze_with_selected_papers(
                        drug_name=drug_name,
                        papers=papers,
                        config=config,
                    )

                    if progress_callback:
                        progress_callback(drug_name, "completed", result)

                    return result

                except Exception as e:
                    logger.error(f"Analysis failed for {drug_name}: {e}")
                    if progress_callback:
                        progress_callback(drug_name, "failed", str(e))
                    return None

        # Run analyses in parallel
        tasks = [analyze_drug(name, papers) for name, papers in drug_papers.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        for (drug_name, _), result in zip(drug_papers.items(), results):
            if isinstance(result, Exception):
                failed_drugs[drug_name] = str(result)
            elif result is None:
                failed_drugs[drug_name] = "Analysis returned no result"
            elif isinstance(result, DrugAnalysisResult):
                drug_results[drug_name] = result
                # Add drug name to each opportunity for tracking
                for opp in result.opportunities:
                    if opp.extraction.treatment:
                        opp.extraction.treatment.drug_name = drug_name
                all_opportunities.extend(result.opportunities)

        # Re-rank all opportunities together
        if all_opportunities:
            all_opportunities = self._scoring_engine.rank(all_opportunities)

        # Calculate totals
        total_papers_screened = sum(r.papers_screened for r in drug_results.values())
        total_papers_extracted = sum(r.papers_extracted for r in drug_results.values())
        total_input_tokens = sum(r.total_input_tokens for r in drug_results.values())
        total_output_tokens = sum(r.total_output_tokens for r in drug_results.values())
        estimated_cost = (total_input_tokens * 3 / 1_000_000) + (total_output_tokens * 15 / 1_000_000)

        # Aggregate papers for manual review from all drug results
        all_papers_for_review: List[PaperForManualReview] = []
        for drug_result in drug_results.values():
            if drug_result.papers_for_manual_review:
                all_papers_for_review.extend(drug_result.papers_for_manual_review)

        # Sort by N (descending), with None values at the end
        all_papers_for_review.sort(
            key=lambda p: (p.n_patients is not None, p.n_patients or 0),
            reverse=True
        )

        return MechanismAnalysisResult(
            mechanism_target=target,
            drugs_analyzed=list(drug_results.keys()),
            drugs_failed=failed_drugs,
            opportunities=all_opportunities,
            drug_results=drug_results,
            papers_for_manual_review=all_papers_for_review,
            papers_screened=total_papers_screened,
            papers_extracted=total_papers_extracted,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            estimated_cost_usd=estimated_cost,
        )

    async def discover_papers(
        self,
        drug_name: str,
        max_per_source: int = 100,
        evaluate_filter: bool = True,
    ) -> PaperDiscoveryResult:
        """
        Discover papers for a drug and evaluate which would pass filtering.

        Returns all papers organized by disease with filter status for manual review.
        Useful for understanding what papers are available and which would be included.

        Args:
            drug_name: Name of the drug
            max_per_source: Max papers per search source
            evaluate_filter: Whether to evaluate which papers would pass the filter

        Returns:
            PaperDiscoveryResult with papers organized by disease and filter status
        """
        # Get drug info first
        drug_info = await self.get_drug_info(drug_name)

        # Search without LLM filtering
        search_result = await self.search_literature(
            drug_name=drug_name,
            exclude_indications=[],  # Don't exclude any indications for discovery
            max_per_source=max_per_source,
            filter_with_llm=False,  # No filtering - get all papers
            generic_name=drug_info.generic_name,
        )

        papers = search_result.papers
        papers_by_disease: Dict[str, List[PaperWithFilterStatus]] = {}
        unclassified: List[PaperWithFilterStatus] = []
        papers_passing = 0

        if evaluate_filter and papers and self._literature_search_service._llm_client:
            # Use the filter prompt which also classifies by disease
            from src.case_series.prompts.filtering_prompts import build_paper_filter_prompt
            from src.case_series.services.literature_search_service import _safe_parse_json_list

            # Process in batches
            batch_size = 10
            for i in range(0, len(papers), batch_size):
                batch = papers[i:i + batch_size]
                paper_dicts = [
                    {
                        'pmid': p.pmid or p.doi or f"paper_{j}",
                        'title': p.title or '',
                        'abstract': (p.abstract or '')[:1500],
                    }
                    for j, p in enumerate(batch)
                ]

                prompt = build_paper_filter_prompt(
                    drug_name=drug_name,
                    papers=paper_dicts,
                    approved_indications=drug_info.approved_indications,
                )

                try:
                    response = await self._literature_search_service._llm_client.complete(
                        prompt, max_tokens=4000
                    )
                    # Template returns {"evaluations": [...]}
                    results = _safe_parse_json_list(
                        response, f"filter evaluation batch {i}", list_key="evaluations"
                    )

                    if results:
                        for j, paper in enumerate(batch):
                            # Find matching result (template uses paper_index, 1-indexed)
                            result = next(
                                (r for r in results if r.get('paper_index') == j + 1),
                                None
                            )

                            would_pass = False
                            reason = "Not evaluated"
                            disease = ""
                            patient_count = None

                            if result:
                                would_pass = result.get('include', False)
                                reason = result.get('reason', '')
                                raw_disease = result.get('disease', '') or ''
                                patient_count = result.get('patient_count')
                                # Convert patient_count to int or None (LLM may return "Unknown")
                                if patient_count is not None:
                                    try:
                                        patient_count = int(patient_count)
                                    except (ValueError, TypeError):
                                        patient_count = None

                                # Standardize disease name using taxonomy
                                disease = raw_disease
                                if raw_disease and self._disease_standardizer:
                                    # Get parent disease for grouping
                                    standardized = self._disease_standardizer.get_parent_disease(raw_disease)
                                    if standardized and standardized != raw_disease:
                                        disease = standardized
                                        logger.debug(f"Standardized disease: '{raw_disease}' -> '{disease}'")
                                    else:
                                        # Try normalize() for alias matching
                                        normalized = self._disease_standardizer.standardize(raw_disease)
                                        if normalized and normalized != raw_disease:
                                            disease = normalized
                                            logger.debug(f"Normalized disease: '{raw_disease}' -> '{disease}'")

                                if would_pass:
                                    papers_passing += 1

                            paper_with_status = PaperWithFilterStatus(
                                paper=paper,
                                would_pass_filter=would_pass,
                                filter_reason=reason,
                                disease=disease,
                                patient_count=patient_count,
                            )

                            if disease and disease.lower() not in ['unknown', 'null', 'none', '']:
                                if disease not in papers_by_disease:
                                    papers_by_disease[disease] = []
                                papers_by_disease[disease].append(paper_with_status)
                            else:
                                unclassified.append(paper_with_status)
                    else:
                        # Failed to parse - add all as unclassified
                        for paper in batch:
                            unclassified.append(PaperWithFilterStatus(
                                paper=paper,
                                would_pass_filter=False,
                                filter_reason="Failed to evaluate",
                            ))

                except Exception as e:
                    logger.warning(f"Filter evaluation failed for batch: {e}")
                    for paper in batch:
                        unclassified.append(PaperWithFilterStatus(
                            paper=paper,
                            would_pass_filter=False,
                            filter_reason=f"Error: {str(e)[:50]}",
                        ))
        else:
            # No evaluation - wrap all papers without status
            for paper in papers:
                unclassified.append(PaperWithFilterStatus(
                    paper=paper,
                    would_pass_filter=False,
                    filter_reason="Not evaluated",
                ))

        # Post-process: Use LLM to standardize unknown diseases
        # Collect diseases that weren't standardized by taxonomy
        unknown_diseases = []
        for disease in papers_by_disease.keys():
            if self._disease_standardizer:
                entry = self._disease_standardizer._taxonomy.get_disease(disease)
                if not entry:
                    unknown_diseases.append(disease)

        # If we have unknown diseases and LLM client, try to standardize them
        if unknown_diseases and self._disease_standardizer and self._disease_standardizer._llm_client:
            logger.info(f"Found {len(unknown_diseases)} unknown diseases, attempting LLM standardization...")
            try:
                known_canonicals = list(self._disease_standardizer._taxonomy.get_all_diseases())
                standardized_map = await self._disease_standardizer.standardize_with_llm(
                    diseases=unknown_diseases,
                    known_canonicals=known_canonicals,
                )

                # Re-group papers by standardized disease names
                new_papers_by_disease: Dict[str, List[PaperWithFilterStatus]] = {}
                for disease, paper_list in papers_by_disease.items():
                    canonical = standardized_map.get(disease, disease)
                    if canonical not in new_papers_by_disease:
                        new_papers_by_disease[canonical] = []
                    # Update disease field in each paper
                    for p in paper_list:
                        p.disease = canonical
                    new_papers_by_disease[canonical].extend(paper_list)

                papers_by_disease = new_papers_by_disease
                logger.info(f"LLM standardization complete. Grouped into {len(papers_by_disease)} diseases.")

                # Save new mappings to database
                if self._repository:
                    for raw_disease, canonical in standardized_map.items():
                        if raw_disease != canonical:
                            try:
                                self._repository.save_disease_mapping(raw_disease, canonical)
                                logger.debug(f"Saved disease mapping: '{raw_disease}' -> '{canonical}'")
                            except Exception as e:
                                logger.debug(f"Could not save mapping: {e}")

            except Exception as e:
                logger.warning(f"LLM disease standardization failed: {e}")

        result = PaperDiscoveryResult(
            drug_name=drug_name,
            generic_name=drug_info.generic_name,
            total_papers=len(papers),
            papers_by_disease=papers_by_disease,
            unclassified_papers=unclassified,
            approved_indications=drug_info.approved_indications,
            sources_searched=search_result.sources_searched,
            papers_passing_filter=papers_passing,
            duplicates_removed=search_result.duplicates_removed,
        )

        # Save discovery to database
        if self._repository:
            try:
                # Flatten all papers into list of dicts for storage
                all_papers_for_db = []

                # Papers by disease
                for disease, paper_list in papers_by_disease.items():
                    for p in paper_list:
                        all_papers_for_db.append({
                            'pmid': p.paper.pmid,
                            'doi': p.paper.doi,
                            'title': p.paper.title,
                            'abstract': p.paper.abstract,
                            'year': p.paper.year,
                            'journal': p.paper.journal,
                            'source': p.paper.source,
                            'disease': p.disease,
                            'patient_count': p.patient_count,
                            'would_pass_filter': p.would_pass_filter,
                            'filter_reason': p.filter_reason,
                        })

                # Unclassified papers
                for p in unclassified:
                    all_papers_for_db.append({
                        'pmid': p.paper.pmid,
                        'doi': p.paper.doi,
                        'title': p.paper.title,
                        'abstract': p.paper.abstract,
                        'year': p.paper.year,
                        'journal': p.paper.journal,
                        'source': p.paper.source,
                        'disease': p.disease,
                        'patient_count': p.patient_count,
                        'would_pass_filter': p.would_pass_filter,
                        'filter_reason': p.filter_reason,
                    })

                discovery_id = self._repository.save_paper_discovery(
                    drug_name=drug_name,
                    generic_name=drug_info.generic_name,
                    papers=all_papers_for_db,
                    approved_indications=drug_info.approved_indications,
                    sources_searched=search_result.sources_searched,
                    duplicates_removed=search_result.duplicates_removed,
                )
                if discovery_id:
                    logger.info(f"Saved paper discovery {discovery_id} with {len(all_papers_for_db)} papers")
            except Exception as e:
                logger.warning(f"Failed to save paper discovery to database: {e}")

        return result

    def load_paper_discovery(
        self,
        drug_name: str,
        max_age_days: int = 7,
    ) -> Optional[PaperDiscoveryResult]:
        """
        Load a previous paper discovery from the database.

        Args:
            drug_name: Name of the drug
            max_age_days: Maximum age of discovery to consider fresh

        Returns:
            PaperDiscoveryResult if found, None otherwise
        """
        if not self._repository:
            logger.debug(f"No repository available for loading discovery for {drug_name}")
            return None

        try:
            logger.info(f"Loading paper discovery for {drug_name} (max_age_days={max_age_days})")
            stored = self._repository.load_paper_discovery(drug_name, max_age_days)
            if not stored:
                logger.info(f"No paper discovery found for {drug_name} within {max_age_days} days")
                return None

            logger.info(f"Found stored discovery for {drug_name} with {len(stored.get('papers', []))} papers")

            # Reconstruct PaperDiscoveryResult from stored data
            from src.case_series.services.literature_search_service import Paper

            papers_by_disease: Dict[str, List[PaperWithFilterStatus]] = {}
            unclassified: List[PaperWithFilterStatus] = []
            papers_passing = 0

            for paper_dict in stored.get('papers', []):
                paper = Paper(
                    pmid=paper_dict.get('pmid'),
                    doi=paper_dict.get('doi'),
                    title=paper_dict.get('title'),
                    abstract=paper_dict.get('abstract'),
                    year=paper_dict.get('year'),
                    journal=paper_dict.get('journal'),
                    source=paper_dict.get('source'),
                )

                paper_with_status = PaperWithFilterStatus(
                    paper=paper,
                    would_pass_filter=paper_dict.get('would_pass_filter', False),
                    filter_reason=paper_dict.get('filter_reason', ''),
                    disease=paper_dict.get('disease', ''),
                    patient_count=paper_dict.get('patient_count'),
                )

                if paper_with_status.would_pass_filter:
                    papers_passing += 1

                disease = paper_dict.get('disease', '')
                if disease and disease.lower() not in ['unknown', 'null', 'none', '']:
                    if disease not in papers_by_disease:
                        papers_by_disease[disease] = []
                    papers_by_disease[disease].append(paper_with_status)
                else:
                    unclassified.append(paper_with_status)

            result = PaperDiscoveryResult(
                drug_name=stored.get('drug_name', drug_name),
                generic_name=stored.get('generic_name'),
                total_papers=stored.get('total_papers', len(stored.get('papers', []))),
                papers_by_disease=papers_by_disease,
                unclassified_papers=unclassified,
                approved_indications=stored.get('approved_indications', []),
                sources_searched=stored.get('sources_searched', []),
                papers_passing_filter=papers_passing,
                duplicates_removed=stored.get('duplicates_removed', 0),
            )
            logger.info(f"Successfully loaded discovery for {drug_name}: {result.total_papers} total, {len(papers_by_disease)} diseases, {papers_passing} passing filter")
            return result

        except Exception as e:
            logger.error(f"Failed to load paper discovery for {drug_name}: {e}", exc_info=True)
            return None

    def get_discovery_history(
        self,
        drug_name: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Get paper discovery history.

        Args:
            drug_name: Optional drug name to filter by
            limit: Maximum number of discoveries to return

        Returns:
            List of discovery summaries
        """
        if not self._repository:
            return []

        return self._repository.get_discovery_history(drug_name, limit)
