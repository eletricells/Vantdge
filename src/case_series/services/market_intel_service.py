"""
Market Intelligence Service

Gathers market intelligence for diseases:
- Epidemiology (prevalence, incidence)
- Standard of care (approved drugs, efficacy)
- Pipeline therapies (drugs in development)
- Total addressable market (TAM)
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from src.case_series.models import (
    MarketIntelligence,
    EpidemiologyData,
    StandardOfCareData,
    StandardOfCareTreatment,
    PipelineTherapy,
    AttributedSource,
)
from src.case_series.protocols.llm_protocol import LLMClient
from src.case_series.protocols.search_protocol import WebSearcher
from src.case_series.protocols.database_protocol import CaseSeriesRepositoryProtocol
from src.case_series.services.disease_standardizer import DiseaseStandardizer

logger = logging.getLogger(__name__)


class MarketIntelService:
    """
    Service for gathering market intelligence.

    Collects:
    - Epidemiology data (prevalence, incidence, patient population)
    - Standard of care (approved drugs, efficacy benchmarks)
    - Pipeline therapies (drugs in clinical development)
    - TAM calculation
    """

    def __init__(
        self,
        llm_client: LLMClient,
        web_searcher: WebSearcher,
        repository: Optional[CaseSeriesRepositoryProtocol] = None,
        disease_standardizer: Optional[DiseaseStandardizer] = None,
    ):
        """
        Initialize the market intelligence service.

        Args:
            llm_client: LLM client for extraction
            web_searcher: Web searcher for data gathering
            repository: Optional repository for caching
            disease_standardizer: Optional disease name standardizer
        """
        self._llm_client = llm_client
        self._web_searcher = web_searcher
        self._repository = repository
        self._disease_standardizer = disease_standardizer or DiseaseStandardizer()

    async def get_market_intel(
        self,
        disease: str,
        use_cache: bool = True,
        max_age_days: int = 30,
    ) -> MarketIntelligence:
        """
        Get market intelligence for a disease.

        Args:
            disease: Disease name
            use_cache: Whether to use cached data
            max_age_days: Max age for cached data

        Returns:
            MarketIntelligence with all available data
        """
        # Standardize disease name
        canonical_disease = self._disease_standardizer.get_parent_disease(disease)

        # Check cache
        if use_cache and self._repository:
            if self._repository.is_market_intel_fresh(canonical_disease, max_age_days):
                cached = self._repository.load_market_intel(canonical_disease)
                if cached:
                    logger.info(f"Using cached market intel for {canonical_disease}")
                    return MarketIntelligence(**cached)

        # Get search variants for better coverage
        search_variants = self._disease_standardizer.get_search_variants(canonical_disease)

        # Gather data in parallel
        import asyncio

        epidemiology, treatments, pipeline = await asyncio.gather(
            self._get_epidemiology(canonical_disease, search_variants),
            self._get_standard_of_care(canonical_disease, search_variants),
            self._get_pipeline(canonical_disease, search_variants),
        )

        # Calculate TAM
        tam_usd, tam_estimate, tam_rationale = self._calculate_tam(
            epidemiology, treatments
        )

        # Build market intelligence
        mi = MarketIntelligence(
            disease=canonical_disease,
            parent_disease=canonical_disease if disease != canonical_disease else None,
            epidemiology=epidemiology,
            standard_of_care=treatments,
            tam_usd=tam_usd,
            tam_estimate=tam_estimate,
            tam_rationale=tam_rationale,
        )

        # Add pipeline to SOC
        mi.standard_of_care.pipeline_therapies = pipeline
        mi.standard_of_care.num_pipeline_therapies = len(pipeline)

        # Save to cache
        if self._repository:
            self._repository.save_market_intel(canonical_disease, mi.model_dump())

        return mi

    async def _get_epidemiology(
        self,
        disease: str,
        variants: List[str],
    ) -> EpidemiologyData:
        """Get epidemiology data for a disease."""
        from src.case_series.prompts.market_prompts import build_epidemiology_prompt

        # Search for epidemiology data
        query = f"{disease} prevalence United States epidemiology patients"
        try:
            results = await self._web_searcher.search(query, max_results=10)
        except Exception as e:
            logger.warning(f"Epidemiology search failed: {e}")
            return EpidemiologyData()

        if not results:
            return EpidemiologyData()

        # Extract data using LLM
        prompt = build_epidemiology_prompt(
            disease=disease,
            search_results=results,
            disease_variants=variants,
        )

        try:
            response = await self._llm_client.complete(prompt, max_tokens=2000)
            data = json.loads(response)

            return EpidemiologyData(
                us_prevalence_estimate=data.get('us_prevalence'),
                us_incidence_estimate=data.get('us_incidence'),
                global_prevalence=data.get('global_prevalence'),
                patient_population_size=data.get('patient_population'),
                prevalence_source=data.get('source'),
                prevalence_source_url=data.get('source_url'),
                trend=data.get('trend'),
                source_quality=data.get('source_quality'),
                confidence=data.get('confidence'),
            )

        except Exception as e:
            logger.warning(f"Epidemiology extraction failed: {e}")
            return EpidemiologyData()

    async def _get_standard_of_care(
        self,
        disease: str,
        variants: List[str],
    ) -> StandardOfCareData:
        """Get standard of care data for a disease."""
        from src.case_series.prompts.market_prompts import build_treatments_prompt

        # Search for treatment data
        query = f"{disease} FDA approved treatments standard of care guidelines"
        try:
            results = await self._web_searcher.search(query, max_results=10)
        except Exception as e:
            logger.warning(f"Treatment search failed: {e}")
            return StandardOfCareData()

        if not results:
            return StandardOfCareData()

        # Extract data using LLM
        prompt = build_treatments_prompt(
            disease=disease,
            search_results=results,
        )

        try:
            response = await self._llm_client.complete(prompt, max_tokens=3000)
            data = json.loads(response)

            # Build treatments
            treatments = []
            for t in data.get('treatments', []):
                treatments.append(StandardOfCareTreatment(
                    drug_name=t.get('drug_name', 'Unknown'),
                    drug_class=t.get('drug_class'),
                    is_branded_innovative=t.get('is_branded', False),
                    fda_approved=t.get('fda_approved', False),
                    efficacy_range=t.get('efficacy_range'),
                    efficacy_pct=t.get('efficacy_pct'),
                    line_of_therapy=t.get('line_of_therapy'),
                ))

            return StandardOfCareData(
                top_treatments=treatments,
                approved_drug_names=[t.drug_name for t in treatments if t.fda_approved],
                num_approved_drugs=sum(1 for t in treatments if t.fda_approved),
                treatment_paradigm=data.get('treatment_paradigm'),
                unmet_need=data.get('unmet_need', False),
                unmet_need_description=data.get('unmet_need_description'),
            )

        except Exception as e:
            logger.warning(f"Treatment extraction failed: {e}")
            return StandardOfCareData()

    async def _get_pipeline(
        self,
        disease: str,
        variants: List[str],
    ) -> List[PipelineTherapy]:
        """Get pipeline therapy data for a disease."""
        from src.case_series.prompts.market_prompts import build_pipeline_prompt

        # Search for pipeline data
        query = f"{disease} clinical trials pipeline phase 2 phase 3"
        try:
            results = await self._web_searcher.search(query, max_results=10)
        except Exception as e:
            logger.warning(f"Pipeline search failed: {e}")
            return []

        if not results:
            return []

        # Extract data using LLM
        prompt = build_pipeline_prompt(
            disease=disease,
            search_results=results,
        )

        try:
            response = await self._llm_client.complete(prompt, max_tokens=2000)
            data = json.loads(response)

            therapies = []
            for t in data.get('pipeline_therapies', []):
                therapies.append(PipelineTherapy(
                    drug_name=t.get('drug_name', 'Unknown'),
                    company=t.get('company'),
                    mechanism=t.get('mechanism'),
                    phase=t.get('phase'),
                    trial_id=t.get('nct_id'),
                    expected_completion=t.get('expected_completion'),
                    status=t.get('status'),
                ))

            return therapies

        except Exception as e:
            logger.warning(f"Pipeline extraction failed: {e}")
            return []

    def _calculate_tam(
        self,
        epidemiology: EpidemiologyData,
        treatments: StandardOfCareData,
    ) -> tuple[Optional[float], Optional[str], Optional[str]]:
        """
        Calculate Total Addressable Market.

        Returns:
            Tuple of (tam_usd, tam_formatted, rationale)
        """
        patient_pop = epidemiology.patient_population_size
        if not patient_pop or patient_pop == 0:
            return None, None, "Unable to calculate TAM: patient population unknown"

        # Get average cost from treatments
        avg_cost = None
        if treatments.top_treatments:
            costs = [
                t.annual_cost_usd for t in treatments.top_treatments
                if t.annual_cost_usd
            ]
            if costs:
                avg_cost = sum(costs) / len(costs)

        # Estimate cost based on population size
        if not avg_cost:
            if patient_pop < 10000:
                avg_cost = 200000  # Rare disease
            elif patient_pop < 100000:
                avg_cost = 75000   # Specialty
            else:
                avg_cost = 20000   # Standard

        # Calculate TAM
        tam_usd = patient_pop * avg_cost

        # Format TAM
        if tam_usd >= 1_000_000_000:
            tam_estimate = f"${tam_usd / 1_000_000_000:.1f}B"
        elif tam_usd >= 1_000_000:
            tam_estimate = f"${tam_usd / 1_000_000:.0f}M"
        else:
            tam_estimate = f"${tam_usd / 1_000:.0f}K"

        rationale = (
            f"Based on {patient_pop:,} patients × ${avg_cost:,.0f} average annual cost. "
            f"Patient population from {epidemiology.prevalence_source or 'estimate'}. "
        )

        if treatments.num_approved_drugs == 0:
            rationale += "No approved drugs indicates high unmet need."
        else:
            rationale += f"{treatments.num_approved_drugs} approved drugs in market."

        return tam_usd, tam_estimate, rationale

    async def enrich_opportunities(
        self,
        opportunities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Enrich opportunities with market intelligence.

        Args:
            opportunities: List of opportunity dicts with 'disease' key

        Returns:
            Opportunities with 'market_intelligence' added
        """
        # Group by disease to avoid duplicate lookups
        diseases = set(opp.get('disease', '') for opp in opportunities)
        diseases.discard('')

        # Fetch market intel for each disease
        market_intel_cache = {}
        for disease in diseases:
            try:
                mi = await self.get_market_intel(disease)
                market_intel_cache[disease] = mi.model_dump()
            except Exception as e:
                logger.warning(f"Failed to get market intel for {disease}: {e}")

        # Add market intel to opportunities
        for opp in opportunities:
            disease = opp.get('disease', '')
            if disease in market_intel_cache:
                opp['market_intelligence'] = market_intel_cache[disease]

        return opportunities
