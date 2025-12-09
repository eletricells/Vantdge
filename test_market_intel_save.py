"""
Test script to verify market intelligence can be saved to database after fix.
"""
import logging
import os
from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
from src.models.case_series_schemas import (
    MarketIntelligence,
    EpidemiologyData,
    StandardOfCareData,
    StandardOfCareTreatment
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize agent
logger.info("Initializing agent...")
api_key = os.getenv('ANTHROPIC_API_KEY')
db_url = os.getenv('CASE_SERIES_DB_URL')
agent = DrugRepurposingCaseSeriesAgent(
    anthropic_api_key=api_key,
    case_series_database_url=db_url
)

# Create a test market intelligence object
test_mi = MarketIntelligence(
    disease="Test Disease for Database Save",
    epidemiology=EpidemiologyData(
        us_prevalence_estimate="100,000 patients",
        us_incidence_estimate="10,000 new cases/year"
    ),
    standard_of_care=StandardOfCareData(
        approved_drug_names=["Drug A", "Drug B"],
        num_approved_drugs=2,
        unmet_need=True,
        unmet_need_description="High unmet need due to limited efficacy",
        treatment_paradigm="First-line: Drug A, Second-line: Drug B"
    ),
    tam_estimate="$500M",
    tam_usd=500000000.0,
    growth_rate="5% CAGR"
)

# Try to save it
logger.info("Attempting to save market intelligence to database...")
try:
    agent.cs_db.save_market_intelligence(test_mi)
    logger.info("✅ Successfully saved market intelligence!")
    
    # Try to retrieve it
    logger.info("Attempting to retrieve from cache...")
    cached = agent.cs_db.check_market_intel_fresh("Test Disease for Database Save")
    if cached:
        logger.info("✅ Successfully retrieved from cache!")
        logger.info(f"   Disease: {cached.disease}")
        logger.info(f"   TAM: {cached.tam_estimate}")
        logger.info(f"   Unmet Need: {cached.standard_of_care.unmet_need if cached.standard_of_care else 'N/A'}")
    else:
        logger.warning("⚠️ Could not retrieve from cache")
        
except Exception as e:
    logger.error(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

