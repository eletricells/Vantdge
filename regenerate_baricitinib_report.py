"""
Script to regenerate the Excel report for baricitinib analysis from database.
This script loads the extractions from the database, re-runs the scoring with the fixed function,
and generates the Excel output.
"""
import sys
import os
from pathlib import Path
from datetime import datetime
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.tools.case_series_database import CaseSeriesDatabase
from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
from src.models.case_series_schemas import DrugAnalysisResult, RepurposingOpportunity
from src.utils.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    """Regenerate the baricitinib report from database."""

    # Load settings
    settings = get_settings()
    database_url = settings.drug_database_url or settings.disease_landscape_url or settings.paper_catalog_url

    if not database_url:
        logger.error("No database URL configured! Please set DRUG_DATABASE_URL or DATABASE_URL in .env")
        return

    logger.info(f"Using database URL: {database_url[:30]}...")

    # Initialize database
    db = CaseSeriesDatabase(database_url)
    
    # Get the most recent baricitinib run
    logger.info("Fetching historical runs...")
    runs = db.get_historical_runs(limit=10)
    
    baricitinib_run = None
    for run in runs:
        if run['drug_name'].lower() == 'baricitinib':
            baricitinib_run = run
            break
    
    if not baricitinib_run:
        logger.error("No baricitinib run found in database!")
        return
    
    run_id = baricitinib_run['run_id']
    logger.info(f"Found baricitinib run: {run_id}")
    logger.info(f"  Started: {baricitinib_run['started_at']}")
    logger.info(f"  Papers found: {baricitinib_run['papers_found']}")
    logger.info(f"  Papers extracted: {baricitinib_run['papers_extracted']}")
    logger.info(f"  Opportunities found: {baricitinib_run['opportunities_found']}")
    
    # Get run details with extractions
    logger.info("Loading extractions from database...")
    run_details = db.get_run_details(run_id)
    
    if not run_details or not run_details.get('extractions'):
        logger.error("No extractions found for this run!")
        return
    
    logger.info(f"Loaded {len(run_details['extractions'])} extractions")
    
    # Initialize agent
    logger.info("Initializing agent...")
    agent = DrugRepurposingCaseSeriesAgent(
        anthropic_api_key=settings.anthropic_api_key,
        database_url=database_url,
        case_series_database_url=database_url,
        tavily_api_key=getattr(settings, 'tavily_api_key', None),
        pubmed_email='noreply@example.com',
        pubmed_api_key=getattr(settings, 'pubmed_api_key', None),
        semantic_scholar_api_key=getattr(settings, 'semantic_scholar_api_key', None)
    )
    
    # Reconstruct opportunities from extractions
    logger.info("Reconstructing opportunities from extractions...")
    opportunities = []

    for ext_row in run_details['extractions']:
        if not ext_row.get('full_extraction'):
            continue

        try:
            from src.models.case_series_schemas import CaseSeriesExtraction
            extraction = CaseSeriesExtraction.model_validate(ext_row['full_extraction'])

            # Create opportunity object (scores will be calculated later)
            opp = RepurposingOpportunity(
                extraction=extraction,
                market_intelligence=None  # Will be loaded from cache below
            )
            opportunities.append(opp)

        except Exception as e:
            logger.error(f"Error loading extraction {ext_row.get('id')}: {e}")
            continue

    logger.info(f"Reconstructed {len(opportunities)} opportunities")

    # Standardize disease names FIRST (needed for market intel cache lookup)
    logger.info("Standardizing disease names...")
    try:
        opportunities = agent.standardize_disease_names(opportunities)
        logger.info("Disease names standardized")
    except Exception as e:
        logger.warning(f"Disease standardization failed (non-critical): {e}")

    # Load market intelligence from cache (after standardization)
    logger.info("Loading market intelligence from cache...")
    market_intel_loaded = 0
    for opp in opportunities:
        disease = opp.extraction.disease_normalized or opp.extraction.disease
        if disease:
            cached_mi = agent.cs_db.check_market_intel_fresh(disease)
            if cached_mi:
                opp.market_intelligence = cached_mi
                market_intel_loaded += 1
    logger.info(f"Loaded market intelligence for {market_intel_loaded}/{len(opportunities)} opportunities")

    # Score opportunities using the FIXED scoring function
    logger.info("Scoring opportunities with fixed scoring function...")
    try:
        scored_opportunities = agent._score_opportunities(opportunities)
        logger.info(f"Successfully scored {len(scored_opportunities)} opportunities")
    except Exception as e:
        logger.error(f"Error scoring opportunities: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Create DrugAnalysisResult
    logger.info("Creating analysis result...")
    result = DrugAnalysisResult(
        drug_name=baricitinib_run['drug_name'],
        generic_name="baricitinib",
        mechanism="JAK1/JAK2 inhibitor",
        approved_indications=["Rheumatoid arthritis", "Atopic dermatitis", "Alopecia areata"],
        opportunities=scored_opportunities,
        papers_screened=baricitinib_run['papers_found'],
        analysis_date=baricitinib_run['started_at'] or datetime.now(),
        total_input_tokens=0,  # Not tracked in this regeneration
        total_output_tokens=0
    )
    
    # Export to Excel
    logger.info("Generating Excel report...")
    try:
        excel_filepath = agent.export_to_excel(result)
        logger.info(f"✅ Successfully generated Excel report: {excel_filepath}")
        logger.info(f"   Total opportunities: {len(result.opportunities)}")
        logger.info(f"   Top 5 opportunities:")
        for i, opp in enumerate(result.opportunities[:5], 1):
            score = opp.scores.overall_priority if opp.scores else 0
            logger.info(f"     {i}. {opp.extraction.disease} (Score: {score:.1f})")

    except Exception as e:
        logger.error(f"Error generating Excel: {e}")
        import traceback
        traceback.print_exc()
        return

    # Generate narrative report from Excel (more reliable than from result object)
    logger.info("\nGenerating narrative analytical report from Excel...")
    try:
        report_text, report_path = agent.generate_analytical_report(
            excel_path=str(excel_filepath),
            max_tokens=16000,
            auto_save=True
        )
        logger.info(f"✅ Successfully generated narrative report: {report_path}")
        logger.info(f"   Report length: {len(report_text)} characters")

    except Exception as e:
        logger.error(f"Error generating narrative report: {e}")
        import traceback
        traceback.print_exc()
        # Continue even if report generation fails

    # Skip PDF report for now (has style conflict issue)
    # logger.info("\nGenerating PDF report...")
    # try:
    #     pdf_path = agent.export_to_pdf(result, include_rationale=True)
    #     logger.info(f"✅ Successfully generated PDF report: {pdf_path}")
    #
    # except Exception as e:
    #     logger.error(f"Error generating PDF report: {e}")
    #     import traceback
    #     traceback.print_exc()
    #     # Continue even if PDF generation fails

    logger.info("\n" + "="*80)
    logger.info("SUMMARY OF GENERATED FILES:")
    logger.info("="*80)
    logger.info(f"📊 Excel Report: {excel_filepath}")
    if 'report_path' in locals():
        logger.info(f"📄 Narrative Report: {report_path}")
    if 'pdf_path' in locals():
        logger.info(f"📑 PDF Report: {pdf_path}")
    logger.info("="*80)

if __name__ == "__main__":
    main()

