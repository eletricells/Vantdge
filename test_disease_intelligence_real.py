"""
Test script for Disease Intelligence Database with REAL literature search.

This runs the full pipeline:
1. Multi-source literature search (PubMed, Semantic Scholar, Web)
2. LLM filtering for relevance
3. LLM extraction of prevalence, treatment, failure rates
4. Market funnel calculation
5. Database storage with sources
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from src.drug_extraction_system.database.connection import DatabaseConnection
from src.disease_intelligence.repository import DiseaseIntelligenceRepository
from src.disease_intelligence.service import DiseaseIntelligenceService
from src.tools.pubmed import PubMedAPI
from src.tools.semantic_scholar import SemanticScholarAPI


async def test_real_sle_population():
    """Test real literature-based population for SLE."""
    print("=" * 60)
    print("Testing REAL Disease Intelligence Population for SLE")
    print("=" * 60)

    # Set up database
    db = DatabaseConnection()
    repository = DiseaseIntelligenceRepository(db)

    # Set up searchers
    pubmed = PubMedAPI()
    semantic_scholar = SemanticScholarAPI()

    # Set up web searcher (Tavily)
    try:
        from src.tools.web_search import create_web_searcher
        web_searcher = create_web_searcher()
        print("Web searcher initialized")
    except Exception as e:
        print(f"Web searcher not available: {e}")
        web_searcher = None

    # Set up LLM client
    try:
        from anthropic import AsyncAnthropic

        class SimpleLLMClient:
            """Simple wrapper for Anthropic API."""
            def __init__(self):
                self.client = AsyncAnthropic()

            async def complete(self, prompt: str, model: str = "claude-sonnet-4-20250514", max_tokens: int = 4000) -> str:
                response = await self.client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.content[0].text

        llm_client = SimpleLLMClient()
        print("LLM client initialized")
    except Exception as e:
        print(f"ERROR: Could not initialize LLM client: {e}")
        return

    # Create service
    service = DiseaseIntelligenceService(
        pubmed_searcher=pubmed,
        semantic_scholar_searcher=semantic_scholar,
        web_searcher=web_searcher,
        llm_client=llm_client,
        repository=repository,
    )

    # Delete existing SLE entry to force fresh extraction
    print("\n--- Clearing existing SLE data ---")
    try:
        existing = repository.get_disease("Systemic Lupus Erythematosus")
        if existing and existing.disease_id:
            repository.delete_disease(existing.disease_id)
            print("Deleted existing SLE entry")
    except Exception as e:
        print(f"No existing entry to delete: {e}")

    # Run the real population
    print("\n--- Starting Real Population ---")
    try:
        disease = await service.populate_disease(
            disease_name="Systemic Lupus Erythematosus",
            therapeutic_area="Autoimmune",
            force_refresh=True,
        )

        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        print(f"\nDisease: {disease.disease_name}")
        print(f"Therapeutic Area: {disease.therapeutic_area}")
        print(f"Data Quality: {disease.data_quality}")

        print("\n--- Prevalence (Weighted Consensus) ---")
        if disease.prevalence:
            print(f"  Weighted Median: {disease.prevalence.total_patients:,}" if disease.prevalence.total_patients else "  Total Patients: N/A")
            print(f"  Range: {disease.prevalence.estimate_range}" if disease.prevalence.estimate_range else "")
            print(f"  Confidence: {disease.prevalence.confidence}")
            if disease.prevalence.methodology_notes:
                print(f"  Rationale: {disease.prevalence.methodology_notes}")
            print(f"  Primary Source: {disease.prevalence.prevalence_source}")

            # Show per-paper estimates
            if disease.prevalence.source_estimates:
                print(f"\n  --- Per-Paper Estimates ({len(disease.prevalence.source_estimates)} sources) ---")
                for i, est in enumerate(disease.prevalence.source_estimates, 1):
                    print(f"    {i}. {est.title[:60]}..." if est.title and len(est.title) > 60 else f"    {i}. {est.title}")
                    print(f"       PMID: {est.pmid or 'N/A'} | Year: {est.year or 'N/A'} | Tier: {est.quality_tier or 'N/A'}")
                    print(f"       Type: {est.estimate_type or 'prevalence'} | Rate Type: {est.rate_type or 'N/A'}")
                    print(f"       Patients: {est.total_patients:,}" if est.total_patients else "       Patients: N/A")
                    if est.confidence_interval:
                        print(f"       95% CI: {est.confidence_interval}")
                    if est.methodology:
                        print(f"       Method: {est.methodology}")
                    if est.database_name:
                        print(f"       Database: {est.database_name}")
                    print()

        print("\n--- Segmentation ---")
        if disease.segmentation:
            print(f"  % Treated: {disease.segmentation.pct_treated}%")
            if disease.segmentation.severity:
                print(f"  Severity - Mild: {disease.segmentation.severity.mild}%, Moderate: {disease.segmentation.severity.moderate}%, Severe: {disease.segmentation.severity.severe}%")

        print("\n--- Treatment Paradigm ---")
        if disease.treatment_paradigm:
            print(f"  Summary: {disease.treatment_paradigm.summary}")
            if disease.treatment_paradigm.first_line:
                print(f"  1L: {disease.treatment_paradigm.first_line.description}")
                for drug in disease.treatment_paradigm.first_line.drugs:
                    print(f"      - {drug.drug_name} ({drug.drug_class})")
            if disease.treatment_paradigm.second_line:
                print(f"  2L: {disease.treatment_paradigm.second_line.description}")
                for drug in disease.treatment_paradigm.second_line.drugs:
                    wac = f" - ${drug.wac_monthly:,.0f}/mo" if drug.wac_monthly else ""
                    print(f"      - {drug.drug_name} ({drug.drug_class}){wac}")

        print("\n--- Failure Rates (Consensus) ---")
        if disease.failure_rates:
            print(f"  Median Fail 1L: {disease.failure_rates.fail_1L_pct}%")
            print(f"  Range: {disease.failure_rates.estimate_range}" if disease.failure_rates.estimate_range else "")
            print(f"  Primary Failure Type: {disease.failure_rates.primary_failure_type or 'N/A'}")
            print(f"  Primary Reason: {disease.failure_rates.fail_1L_reason}")
            if disease.failure_rates.switch_rate_1L_pct:
                print(f"  Switch Rate (1L): {disease.failure_rates.switch_rate_1L_pct}%")
            if disease.failure_rates.discontinuation_rate_1L_pct:
                print(f"  Discontinuation Rate (1L): {disease.failure_rates.discontinuation_rate_1L_pct}%")
            print(f"  Confidence: {disease.failure_rates.confidence}")
            if disease.failure_rates.confidence_rationale:
                print(f"  Rationale: {disease.failure_rates.confidence_rationale}")

            # Show per-paper estimates
            if disease.failure_rates.source_estimates:
                print(f"\n  --- Per-Paper Estimates ({len(disease.failure_rates.source_estimates)} sources) ---")
                for i, est in enumerate(disease.failure_rates.source_estimates, 1):
                    print(f"    {i}. {est.title[:60]}..." if est.title and len(est.title) > 60 else f"    {i}. {est.title}")
                    print(f"       PMID: {est.pmid or 'N/A'} | Year: {est.year or 'N/A'} | Tier: {est.quality_tier or 'N/A'}")
                    print(f"       Failure Type: {est.failure_type or 'N/A'}")
                    print(f"       Fail Rate: {est.fail_rate_pct}% ({est.line_of_therapy or 'any'} line)")
                    if est.clinical_endpoint:
                        print(f"       Endpoint: {est.clinical_endpoint}")
                    if est.specific_therapy:
                        print(f"       Therapy: {est.specific_therapy}")
                    if est.switch_rate_pct:
                        print(f"       Switch Rate: {est.switch_rate_pct}% -> {est.switch_destination or 'N/A'}")
                    if est.denominator_n:
                        print(f"       N: {est.denominator_n:,}")
                    print()

        print("\n--- Market Funnel ---")
        if disease.market_funnel:
            print(f"  Total Patients: {disease.market_funnel.total_patients:,}")
            print(f"  Treated: {disease.market_funnel.patients_treated:,}")
            print(f"  Fail 1L: {disease.market_funnel.patients_fail_1L:,}")
            print(f"  Addressable 2L: {disease.market_funnel.patients_addressable_2L:,}")
            print(f"  Avg Annual Cost: ${disease.market_funnel.avg_annual_cost_2L:,.0f}" if disease.market_funnel.avg_annual_cost_2L else "  Avg Annual Cost: N/A")
            print(f"  Market Size: {disease.market_funnel.market_size_2L_formatted}")

        print("\n--- Sources Used ---")
        sources = repository.get_sources(disease.disease_id)
        if sources:
            for i, source in enumerate(sources[:10], 1):
                print(f"  {i}. {source.title[:80]}..." if len(source.title or "") > 80 else f"  {i}. {source.title}")
                if source.pmid:
                    print(f"     PMID: {source.pmid}")
                if source.journal:
                    print(f"     {source.journal} ({source.publication_year})")
        else:
            print("  No sources recorded")

        print("\n" + "=" * 60)
        print("Test Complete!")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_real_sle_population())
