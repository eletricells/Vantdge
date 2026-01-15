"""
Disease Analysis Orchestrator - Coordinates Pipeline + Disease Intelligence.

This orchestrator provides a unified workflow that:
1. Runs Pipeline Intelligence to discover approved + investigational drugs
2. Passes pipeline drugs to Disease Intelligence for enriched treatment paradigm
3. Shares disease synonyms for consistent search across both workflows
4. Combines outputs into a unified market opportunity assessment
"""

import asyncio
import logging
from datetime import datetime
from typing import List, Optional, Callable, Any

from .models import UnifiedDiseaseAnalysis, MarketOpportunity
from ..shared.disease_terms import expand_disease_terms, DiseaseTermExpansion
from ..pipeline_intelligence.service import PipelineIntelligenceService
from ..pipeline_intelligence.models import CompetitiveLandscape, PipelineDrug
from ..disease_intelligence.service import DiseaseIntelligenceService
from ..disease_intelligence.models import DiseaseIntelligence

logger = logging.getLogger(__name__)


class DiseaseAnalysisOrchestrator:
    """
    Orchestrates Pipeline Intelligence and Disease Intelligence workflows.

    This is the main entry point for unified disease analysis. It coordinates
    both workflows to eliminate duplication and share data between them.

    Usage:
        orchestrator = DiseaseAnalysisOrchestrator(
            pipeline_service=pipeline_svc,
            disease_service=disease_svc,
        )
        result = await orchestrator.analyze_disease("Rheumatoid Arthritis")
    """

    def __init__(
        self,
        pipeline_service: PipelineIntelligenceService,
        disease_service: DiseaseIntelligenceService,
        mesh_client: Optional[Any] = None,
    ):
        """
        Initialize the orchestrator.

        Args:
            pipeline_service: Configured PipelineIntelligenceService
            disease_service: Configured DiseaseIntelligenceService
            mesh_client: Optional MeSH client for disease term expansion
        """
        self.pipeline_service = pipeline_service
        self.disease_service = disease_service
        self.mesh_client = mesh_client

    async def analyze_disease(
        self,
        disease_name: str,
        therapeutic_area: str = "Autoimmune",
        include_pipeline: bool = True,
        include_market_sizing: bool = True,
        force_refresh: bool = False,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> UnifiedDiseaseAnalysis:
        """
        Run unified disease analysis.

        This is the main method that coordinates both workflows:
        1. Expands disease terms using MeSH
        2. Runs Pipeline Intelligence for drug discovery
        3. Runs Disease Intelligence with pipeline context
        4. Combines results into unified output

        Args:
            disease_name: Disease to analyze (e.g., "Rheumatoid Arthritis")
            therapeutic_area: Therapeutic area classification
            include_pipeline: Whether to run Pipeline Intelligence
            include_market_sizing: Whether to run Disease Intelligence
            force_refresh: Force refresh even if cached data exists
            progress_callback: Optional callback(phase, message) for progress updates

        Returns:
            UnifiedDiseaseAnalysis with combined results
        """
        logger.info(f"Starting unified disease analysis for: {disease_name}")

        result = UnifiedDiseaseAnalysis(
            disease_name=disease_name,
            therapeutic_area=therapeutic_area,
            run_timestamp=datetime.now(),
        )

        # Phase 1: Expand disease terms
        self._report_progress(progress_callback, "terms", "Expanding disease terms...")
        try:
            term_expansion = expand_disease_terms(disease_name, self.mesh_client)
            result.disease_synonyms = term_expansion.search_terms
            logger.info(f"Expanded to {len(result.disease_synonyms)} search terms")
        except Exception as e:
            logger.warning(f"Disease term expansion failed: {e}")
            result.disease_synonyms = [disease_name]

        # Phase 2: Pipeline Intelligence
        landscape: Optional[CompetitiveLandscape] = None
        if include_pipeline:
            self._report_progress(progress_callback, "pipeline", "Running Pipeline Intelligence...")
            try:
                landscape = await self.pipeline_service.get_landscape(
                    disease_name=disease_name,
                    therapeutic_area=therapeutic_area,
                    force_refresh=force_refresh,
                )
                result.landscape = landscape
                result.pipeline_success = True
                logger.info(f"Pipeline found {landscape.total_drugs} drugs")
            except Exception as e:
                logger.error(f"Pipeline Intelligence failed: {e}")
                result.errors.append(f"Pipeline: {str(e)}")

        # Phase 3: Disease Intelligence (with pipeline context)
        if include_market_sizing:
            self._report_progress(progress_callback, "market", "Running Disease Intelligence...")
            try:
                # Extract approved and pipeline drugs for context
                approved_drugs = landscape.approved_drugs if landscape else []
                pipeline_drugs = landscape.all_drugs if landscape else []

                # Run disease intelligence with pipeline context
                disease_intel = await self._run_disease_intelligence(
                    disease_name=disease_name,
                    therapeutic_area=therapeutic_area,
                    disease_synonyms=result.disease_synonyms,
                    approved_drugs=approved_drugs,
                    pipeline_drugs=pipeline_drugs,
                    force_refresh=force_refresh,
                )
                result.disease_intel = disease_intel
                result.disease_intel_success = True
                result.disease_intel_id = disease_intel.disease_id
                logger.info(f"Disease intel populated, prevalence: {disease_intel.prevalence.total_patients}")
            except Exception as e:
                logger.error(f"Disease Intelligence failed: {e}")
                result.errors.append(f"Disease Intel: {str(e)}")

        # Phase 4: Calculate market opportunity
        self._report_progress(progress_callback, "opportunity", "Calculating market opportunity...")
        result.market_opportunity = self._calculate_market_opportunity(
            landscape=result.landscape,
            disease_intel=result.disease_intel,
        )

        logger.info(f"Unified analysis complete for {disease_name}")
        return result

    async def _run_disease_intelligence(
        self,
        disease_name: str,
        therapeutic_area: str,
        disease_synonyms: List[str],
        approved_drugs: List[PipelineDrug],
        pipeline_drugs: List[PipelineDrug],
        force_refresh: bool,
    ) -> DiseaseIntelligence:
        """
        Run Disease Intelligence with pipeline context.

        This passes the approved drugs and synonyms to Disease Intelligence
        so it can build the treatment paradigm from pipeline data rather
        than re-extracting from literature.
        """
        # Check if the service supports new parameters
        # For backwards compatibility, we try the new signature first
        try:
            return await self.disease_service.populate_disease(
                disease_name=disease_name,
                therapeutic_area=therapeutic_area,
                force_refresh=force_refresh,
                approved_drugs=approved_drugs,
                pipeline_drugs=pipeline_drugs,
                disease_synonyms=disease_synonyms,
            )
        except TypeError:
            # Fall back to old signature if new params not supported
            logger.warning("Disease service doesn't support new params, using legacy mode")
            return await self.disease_service.populate_disease(
                disease_name=disease_name,
                therapeutic_area=therapeutic_area,
                force_refresh=force_refresh,
            )

    def _calculate_market_opportunity(
        self,
        landscape: Optional[CompetitiveLandscape],
        disease_intel: Optional[DiseaseIntelligence],
    ) -> MarketOpportunity:
        """
        Calculate combined market opportunity.

        Combines pipeline competitive data with market sizing.
        """
        opportunity = MarketOpportunity()

        # Populate from disease intelligence
        if disease_intel:
            if disease_intel.prevalence.total_patients:
                opportunity.total_patients = disease_intel.prevalence.total_patients

            if disease_intel.market_funnel:
                mf = disease_intel.market_funnel
                opportunity.patients_treated = mf.patients_treated
                opportunity.patients_fail_1L = mf.patients_fail_1L
                opportunity.addressable_2L = mf.patients_addressable_2L
                opportunity.market_size_2L_usd = mf.market_size_2L_usd
                opportunity.market_size_2L_formatted = mf.market_size_2L_formatted

            opportunity.data_quality = disease_intel.data_quality

        # Populate from pipeline landscape
        if landscape:
            opportunity.approved_drugs_count = landscape.approved_count
            opportunity.phase3_drugs_count = landscape.phase3_count
            opportunity.total_pipeline_drugs = (
                landscape.phase3_count +
                landscape.phase2_count +
                landscape.phase1_count +
                landscape.preclinical_count
            )
            opportunity.key_moa_classes = landscape.key_moa_classes
            opportunity.unmet_need_summary = landscape.unmet_need_summary

        # Generate confidence notes
        notes = []
        if disease_intel and disease_intel.prevalence.confidence:
            notes.append(f"Prevalence: {disease_intel.prevalence.confidence}")
        if disease_intel and disease_intel.failure_rates.confidence:
            notes.append(f"Failure rates: {disease_intel.failure_rates.confidence}")
        if notes:
            opportunity.confidence_notes = "; ".join(notes)

        return opportunity

    def _report_progress(
        self,
        callback: Optional[Callable[[str, str], None]],
        phase: str,
        message: str,
    ):
        """Report progress via callback if provided."""
        if callback:
            try:
                callback(phase, message)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    async def analyze_diseases_batch(
        self,
        diseases: List[str],
        therapeutic_area: str = "Autoimmune",
        max_concurrent: int = 2,
        force_refresh: bool = False,
        progress_callback: Optional[Callable[[str, str, str], None]] = None,
    ) -> List[UnifiedDiseaseAnalysis]:
        """
        Analyze multiple diseases concurrently.

        Args:
            diseases: List of disease names to analyze
            therapeutic_area: Therapeutic area classification
            max_concurrent: Maximum concurrent analyses
            force_refresh: Force refresh even if cached data exists
            progress_callback: Optional callback(disease, phase, message)

        Returns:
            List of UnifiedDiseaseAnalysis results
        """
        logger.info(f"Starting batch analysis for {len(diseases)} diseases")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def analyze_with_semaphore(disease: str) -> UnifiedDiseaseAnalysis:
            async with semaphore:
                def inner_callback(phase: str, message: str):
                    if progress_callback:
                        progress_callback(disease, phase, message)

                return await self.analyze_disease(
                    disease_name=disease,
                    therapeutic_area=therapeutic_area,
                    force_refresh=force_refresh,
                    progress_callback=inner_callback,
                )

        tasks = [analyze_with_semaphore(d) for d in diseases]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Analysis failed for {diseases[i]}: {result}")
                # Return partial result with error
                final_results.append(UnifiedDiseaseAnalysis(
                    disease_name=diseases[i],
                    therapeutic_area=therapeutic_area,
                    errors=[str(result)],
                ))
            else:
                final_results.append(result)

        return final_results


def create_disease_analysis_orchestrator(db) -> DiseaseAnalysisOrchestrator:
    """
    Factory function to create a fully configured DiseaseAnalysisOrchestrator.

    Args:
        db: Database connection

    Returns:
        Configured DiseaseAnalysisOrchestrator
    """
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from src.pipeline_intelligence.service import create_pipeline_intelligence_service
    from src.disease_intelligence.service import create_disease_intelligence_service

    # Create services
    pipeline_service = create_pipeline_intelligence_service(db)
    disease_service = create_disease_intelligence_service(db)

    return DiseaseAnalysisOrchestrator(
        pipeline_service=pipeline_service,
        disease_service=disease_service,
    )
