"""
Re-extract priority papers with updated prompts.

This script re-extracts papers that had extraction failures or misclassifications.
Priority papers were identified in the extraction quality audit (2026-01-10).

Priority 1: Large studies with complete extraction failures (N>=20)
Priority 2: Potential RCT misclassifications (N>=100)

Usage:
    python scripts/reextract_priority_papers.py [--dry-run] [--pmids PMID1,PMID2]
"""

import os
import sys
import asyncio
import argparse
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Priority papers from extraction quality audit
PRIORITY_PAPERS = {
    # Papers with missing efficacy data (N>=10) - from Jan 10 2026 audit
    "38031478": {"drug": "baricitinib", "n": 422, "issue": "no_efficacy", "expected": "Atopic Dermatitis retrospective"},
    "37977159": {"drug": "baricitinib", "n": 125, "issue": "no_efficacy", "expected": "COVID-19 RCT"},
    "34090959": {"drug": "baricitinib", "n": 110, "issue": "no_efficacy", "expected": "Alopecia Areata RCT"},
    "30043749": {"drug": "baricitinib", "n": 105, "issue": "no_efficacy", "expected": "SLE RCT"},
    "40179237": {"drug": "baricitinib", "n": 95, "issue": "no_efficacy", "expected": "Alopecia Areata"},
    "30923002": {"drug": "rituximab", "n": 20, "issue": "no_efficacy", "expected": "Bullous pemphigoid"},
    "36639911": {"drug": "baricitinib", "n": 19, "issue": "no_efficacy", "expected": "COVID-19 RCT"},
    "39731852": {"drug": "baricitinib", "n": 19, "issue": "no_efficacy", "expected": "COVID-19 RCT"},
    "32439463": {"drug": "belimumab", "n": 16, "issue": "no_efficacy", "expected": "Cutaneous Lupus"},
    "41074910": {"drug": "tofacitinib", "n": 13, "issue": "no_efficacy", "expected": "Urticarial Vasculitis"},
    "36921971": {"drug": "tofacitinib", "n": 11, "issue": "no_efficacy", "expected": "Granulomatosis with Polyangiitis"},
}


def get_paper_from_pubmed(pmid: str):
    """Fetch paper metadata from PubMed."""
    from src.tools.pubmed import PubMedAPI

    pubmed = PubMedAPI()
    papers = pubmed.fetch_abstracts([pmid])
    if papers:
        return papers[0]
    return None


def get_drug_info(drug_name: str):
    """Get drug info from database."""
    from src.case_series.services.drug_info_service import DrugInfo
    from src.drug_extraction_system.database.connection import DatabaseConnection

    db = DatabaseConnection()
    with db.cursor() as cur:
        cur.execute("""
            SELECT d.drug_id, d.generic_name, d.brand_name, d.mechanism_of_action, d.target, d.drug_type
            FROM drugs d
            WHERE LOWER(d.generic_name) = LOWER(%s) OR LOWER(d.brand_name) = LOWER(%s)
            LIMIT 1
        """, (drug_name, drug_name))
        row = cur.fetchone()

        if not row:
            logger.warning(f"Drug not found in database: {drug_name}")
            return DrugInfo(
                drug_name=drug_name,
                generic_name=drug_name,
                approved_indications=[]
            )

        # Get indications
        cur.execute("""
            SELECT disease_name FROM drug_indications WHERE drug_id = %s
        """, (row['drug_id'],))
        indications = [r['disease_name'] for r in cur.fetchall()]

        return DrugInfo(
            drug_name=drug_name,
            drug_id=row['drug_id'],
            generic_name=row['generic_name'],
            brand_name=row['brand_name'],
            mechanism=row['mechanism_of_action'],
            target=row['target'],
            drug_type=row['drug_type'],
            approved_indications=indications
        )


def delete_existing_extraction(pmid: str, drug_name: str):
    """Delete existing extraction for a paper."""
    from src.drug_extraction_system.database.connection import DatabaseConnection

    db = DatabaseConnection()
    with db.cursor() as cur:
        cur.execute("""
            DELETE FROM cs_extractions
            WHERE pmid = %s AND LOWER(drug_name) = LOWER(%s)
            RETURNING id
        """, (pmid, drug_name))
        deleted = cur.fetchall()
        db.commit()

    if deleted:
        logger.info(f"Deleted {len(deleted)} existing extraction(s) for PMID {pmid}")
    return len(deleted) > 0


async def reextract_paper(pmid: str, drug_name: str, dry_run: bool = False):
    """Re-extract a single paper."""
    from src.case_series.services.extraction_service import ExtractionService
    from src.case_series.services.literature_search_service import Paper
    from src.tools.case_series_database import CaseSeriesDatabase
    from src.case_series.factory import create_orchestrator

    logger.info(f"\n{'='*60}")
    logger.info(f"Processing PMID {pmid} ({drug_name})")
    logger.info(f"{'='*60}")

    # Get paper from PubMed
    logger.info("Fetching paper from PubMed...")
    paper_data = get_paper_from_pubmed(pmid)
    if not paper_data:
        logger.error(f"Could not fetch paper {pmid} from PubMed")
        return None

    # Create Paper object
    paper = Paper(
        pmid=paper_data.get('pmid'),
        pmcid=paper_data.get('pmcid'),
        doi=paper_data.get('doi'),
        title=paper_data.get('title', ''),
        abstract=paper_data.get('abstract', ''),
        authors=paper_data.get('authors'),
        journal=paper_data.get('journal'),
        year=paper_data.get('year'),
        source='PubMed',
    )

    logger.info(f"Title: {paper.title[:80]}...")
    logger.info(f"Year: {paper.year}, Journal: {paper.journal}")
    logger.info(f"Abstract length: {len(paper.abstract)} chars")

    if dry_run:
        logger.info("[DRY RUN] Would delete existing extraction and re-extract")
        return None

    # Get drug info
    drug_info = get_drug_info(drug_name)
    logger.info(f"Drug: {drug_info.generic_name}, Mechanism: {drug_info.mechanism}")
    logger.info(f"Approved indications: {drug_info.approved_indications}")

    # Delete existing extraction
    delete_existing_extraction(pmid, drug_name)

    # Create orchestrator to get properly configured extraction service
    database_url = os.getenv('DATABASE_URL')
    orchestrator = create_orchestrator(database_url=database_url)
    extraction_service = orchestrator._extraction_service
    cs_db = CaseSeriesDatabase(database_url) if database_url else None

    # Extract
    logger.info("Running extraction...")
    extraction = await extraction_service.extract(paper, drug_info, use_cache=False)

    if extraction:
        logger.info(f"\n--- Extraction Results ---")
        logger.info(f"Disease: {extraction.disease}")
        logger.info(f"N patients: {extraction.patient_population.n_patients}")
        logger.info(f"Evidence level: {extraction.evidence_level}")
        logger.info(f"Study design: {extraction.study_design}")
        logger.info(f"Efficacy signal: {extraction.efficacy_signal}")
        logger.info(f"Response rate: {extraction.efficacy.response_rate}")
        logger.info(f"Efficacy summary: {extraction.efficacy.efficacy_summary[:200] if extraction.efficacy.efficacy_summary else 'None'}...")

        # Save to database
        if cs_db and cs_db.is_available:
            # Create a temporary run for re-extractions
            run_id = cs_db.create_run(drug_name, {"type": "re-extraction", "pmids": [pmid]})
            extraction_id = cs_db.save_extraction(run_id, extraction, drug_name)
            logger.info(f"Saved extraction ID: {extraction_id}")
            cs_db.update_run_status(run_id, 'completed')

        return extraction
    else:
        logger.error(f"Extraction failed for PMID {pmid}")
        return None


async def main():
    parser = argparse.ArgumentParser(description='Re-extract priority papers')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--pmids', type=str, help='Comma-separated list of specific PMIDs to process')
    parser.add_argument('--drug', type=str, help='Process only papers for a specific drug')
    parser.add_argument('--issue', type=str, choices=['complete_failure', 'rct_misclassified'],
                       help='Process only papers with a specific issue type')
    args = parser.parse_args()

    # Filter papers
    papers_to_process = PRIORITY_PAPERS.copy()

    if args.pmids:
        pmid_list = [p.strip() for p in args.pmids.split(',')]
        papers_to_process = {k: v for k, v in papers_to_process.items() if k in pmid_list}

    if args.drug:
        papers_to_process = {k: v for k, v in papers_to_process.items()
                           if v['drug'].lower() == args.drug.lower()}

    if args.issue:
        papers_to_process = {k: v for k, v in papers_to_process.items()
                           if v['issue'] == args.issue}

    logger.info(f"Re-extraction script started at {datetime.now()}")
    logger.info(f"Processing {len(papers_to_process)} papers")
    if args.dry_run:
        logger.info("DRY RUN MODE - no changes will be made")

    results = {
        'success': [],
        'failed': [],
        'skipped': []
    }

    for pmid, info in papers_to_process.items():
        try:
            extraction = await reextract_paper(pmid, info['drug'], dry_run=args.dry_run)
            if extraction:
                results['success'].append({
                    'pmid': pmid,
                    'drug': info['drug'],
                    'disease': extraction.disease,
                    'evidence_level': str(extraction.evidence_level),
                    'n_patients': extraction.patient_population.n_patients,
                })
            elif args.dry_run:
                results['skipped'].append({'pmid': pmid, 'reason': 'dry_run'})
            else:
                results['failed'].append({'pmid': pmid, 'drug': info['drug'], 'reason': 'extraction_returned_none'})
        except Exception as e:
            logger.error(f"Error processing PMID {pmid}: {e}")
            results['failed'].append({'pmid': pmid, 'drug': info['drug'], 'reason': str(e)})

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("RE-EXTRACTION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Successful: {len(results['success'])}")
    logger.info(f"Failed: {len(results['failed'])}")
    logger.info(f"Skipped: {len(results['skipped'])}")

    if results['success']:
        logger.info("\nSuccessful extractions:")
        for r in results['success']:
            logger.info(f"  PMID {r['pmid']}: {r['drug']} - {r['disease']} (N={r['n_patients']}, {r['evidence_level']})")

    if results['failed']:
        logger.info("\nFailed extractions:")
        for r in results['failed']:
            logger.info(f"  PMID {r['pmid']}: {r['drug']} - {r['reason']}")


if __name__ == "__main__":
    asyncio.run(main())
