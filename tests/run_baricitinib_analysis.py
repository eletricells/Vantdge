"""
Run the full Off-Label Case Study Agent workflow with baricitinib.

This tests the multi-stage extraction pipeline end-to-end.
"""
import os
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.agents.off_label_case_study_agent import OffLabelCaseStudyAgent
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run baricitinib analysis."""
    logger.info("=" * 80)
    logger.info("BARICITINIB OFF-LABEL CASE STUDY ANALYSIS")
    logger.info("=" * 80)
    
    # Check environment variables
    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    database_url = os.getenv('DISEASE_LANDSCAPE_URL')
    pubmed_email = os.getenv('PUBMED_EMAIL', 'test@example.com')
    tavily_key = os.getenv('TAVILY_API_KEY')
    
    if not anthropic_key:
        logger.error("❌ ANTHROPIC_API_KEY not set")
        return
    
    if not database_url:
        logger.error("❌ DISEASE_LANDSCAPE_URL not set")
        return
    
    logger.info("✅ Environment variables loaded")
    
    # Initialize agent
    logger.info("Initializing Off-Label Case Study Agent...")
    agent = OffLabelCaseStudyAgent(
        anthropic_api_key=anthropic_key,
        database_url=database_url,
        pubmed_email=pubmed_email,
        tavily_api_key=tavily_key
    )
    logger.info("✅ Agent initialized")
    
    # Run analysis with limited papers for testing
    drug_name = "baricitinib"
    max_papers = 10  # Limit for testing
    
    logger.info(f"\n{'='*80}")
    logger.info(f"Starting analysis for: {drug_name}")
    logger.info(f"Max papers: {max_papers}")
    logger.info(f"{'='*80}\n")
    
    try:
        # Run the main analyze_drug workflow
        results = agent.analyze_drug(
            drug_name=drug_name,
            max_papers=max_papers,
            use_parallel=False  # Sequential for easier debugging
        )
        
        # Print results summary
        logger.info("\n" + "=" * 80)
        logger.info("ANALYSIS RESULTS")
        logger.info("=" * 80)
        
        logger.info(f"\nDrug: {results.get('drug_name', drug_name)}")
        logger.info(f"Mechanism: {results.get('drug_info', {}).get('mechanism', 'N/A')}")
        logger.info(f"Target: {results.get('drug_info', {}).get('target', 'N/A')}")
        
        logger.info(f"\nPapers found: {results.get('papers_found', 0)}")
        logger.info(f"Papers classified: {results.get('papers_classified', 0)}")
        logger.info(f"Case studies extracted: {results.get('case_studies_extracted', 0)}")
        
        # Get case studies
        case_studies = results.get('case_studies', [])

        if case_studies:
            logger.info(f"\n{'='*80}")
            logger.info("CASE STUDIES EXTRACTED")
            logger.info(f"{'='*80}")

            for i, cs in enumerate(case_studies, 1):
                # Handle both dict and object formats
                if isinstance(cs, dict):
                    pmid = cs.get('pmid', 'N/A')
                    title = cs.get('title', 'N/A')
                    indication = cs.get('indication_treated', 'N/A')
                    study_type = cs.get('study_type', 'N/A')
                    n_patients = cs.get('n_patients', 'N/A')
                    response_rate = cs.get('response_rate', 'N/A')
                    efficacy_signal = cs.get('efficacy_signal', 'N/A')
                    extraction_method = cs.get('extraction_method', 'N/A')
                    stages_completed = cs.get('extraction_stages_completed', [])
                    detailed_efficacy = cs.get('detailed_efficacy_endpoints', [])
                    detailed_safety = cs.get('detailed_safety_endpoints', [])
                    standard_matched = cs.get('standard_endpoints_matched', [])
                else:
                    pmid = cs.pmid
                    title = cs.title
                    indication = cs.indication_treated
                    study_type = cs.study_type
                    n_patients = cs.n_patients
                    response_rate = cs.response_rate
                    efficacy_signal = cs.efficacy_signal
                    extraction_method = cs.extraction_method
                    stages_completed = cs.extraction_stages_completed
                    detailed_efficacy = cs.detailed_efficacy_endpoints
                    detailed_safety = cs.detailed_safety_endpoints
                    standard_matched = cs.standard_endpoints_matched

                logger.info(f"\n--- Case Study {i} ---")
                logger.info(f"PMID: {pmid}")
                logger.info(f"Title: {title[:80]}..." if len(str(title)) > 80 else f"Title: {title}")
                logger.info(f"Indication: {indication}")
                logger.info(f"Study Type: {study_type}")
                logger.info(f"N Patients: {n_patients}")
                logger.info(f"Response Rate: {response_rate}")
                logger.info(f"Efficacy Signal: {efficacy_signal}")
                logger.info(f"Extraction Method: {extraction_method}")
                logger.info(f"Stages Completed: {stages_completed}")

                # Show multi-stage extraction results
                if detailed_efficacy:
                    logger.info(f"  Detailed Efficacy Endpoints: {len(detailed_efficacy)}")
                    for ep in detailed_efficacy[:3]:  # Show first 3
                        if isinstance(ep, dict):
                            logger.info(f"    - {ep.get('endpoint_name', 'N/A')}: {ep.get('responders_pct', 'N/A')}% at {ep.get('timepoint', 'N/A')}")
                        else:
                            logger.info(f"    - {ep.endpoint_name}: {ep.responders_pct}% at {ep.timepoint}")

                if detailed_safety:
                    logger.info(f"  Detailed Safety Endpoints: {len(detailed_safety)}")
                    for se in detailed_safety[:3]:  # Show first 3
                        if isinstance(se, dict):
                            logger.info(f"    - {se.get('event_name', 'N/A')}: {se.get('incidence_pct', 'N/A')}%")
                        else:
                            logger.info(f"    - {se.event_name}: {se.incidence_pct}%")

                if standard_matched:
                    logger.info(f"  Standard Endpoints Matched: {standard_matched}")

            # Export to Excel - fetch full case studies from database
            logger.info(f"\n{'='*80}")
            logger.info("EXPORTING TO EXCEL")
            logger.info(f"{'='*80}")

            # Get full case studies from database for export
            full_case_studies_dicts = agent.db.get_case_studies_by_drug(drug_name)

            if full_case_studies_dicts:
                # Convert dicts to OffLabelCaseStudy objects for export
                from src.models.off_label_schemas import OffLabelCaseStudy

                full_case_studies = []
                for cs_dict in full_case_studies_dicts:
                    # Remove database-specific fields and handle None values
                    cs_dict_clean = {k: v for k, v in cs_dict.items() if k != 'case_study_id'}
                    # Set required fields with defaults if missing
                    cs_dict_clean.setdefault('study_type', 'Unknown')
                    cs_dict_clean.setdefault('relevance_score', 0.5)
                    cs_dict_clean.setdefault('drug_name', drug_name)
                    cs_dict_clean.setdefault('indication_treated', 'Unknown')
                    # Handle None values for list fields
                    if cs_dict_clean.get('detailed_efficacy_endpoints') is None:
                        cs_dict_clean['detailed_efficacy_endpoints'] = []
                    if cs_dict_clean.get('detailed_safety_endpoints') is None:
                        cs_dict_clean['detailed_safety_endpoints'] = []
                    if cs_dict_clean.get('standard_endpoints_matched') is None:
                        cs_dict_clean['standard_endpoints_matched'] = []
                    if cs_dict_clean.get('extraction_stages_completed') is None:
                        cs_dict_clean['extraction_stages_completed'] = []
                    try:
                        full_case_studies.append(OffLabelCaseStudy(**cs_dict_clean))
                    except Exception as e:
                        logger.warning(f"Could not convert case study to object: {e}")

                if full_case_studies:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    output_path = f"data/exports/baricitinib_case_studies_{timestamp}.xlsx"

                    excel_path = agent.export_to_excel(full_case_studies, drug_name, output_path)
                    logger.info(f"✅ Excel exported to: {excel_path}")
                else:
                    logger.warning("Could not convert any case studies for export")
            else:
                logger.warning("No case studies found in database for export")
        else:
            logger.warning("No case studies were extracted")
        
        logger.info("\n" + "=" * 80)
        logger.info("ANALYSIS COMPLETE")
        logger.info("=" * 80)
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    results = main()
    sys.exit(0 if results else 1)

