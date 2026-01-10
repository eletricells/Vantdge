"""
Recalculate individual paper scores after data fixes.

This script recalculates scores for papers that had evidence level fixes
or efficacy data re-extracted.
"""

import os
import sys
import json
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def recalculate_scores(drug_names: list = None, dry_run: bool = False):
    """Recalculate scores for specified drugs or all drugs."""
    from src.drug_extraction_system.database.connection import DatabaseConnection
    from src.case_series.scoring.case_series_scorer import CaseSeriesScorer
    from src.models.case_series_schemas import (
        CaseSeriesExtraction, CaseSeriesSource, PatientPopulation,
        TreatmentDetails, EfficacyOutcome, SafetyOutcome
    )

    db = DatabaseConnection()
    scorer = CaseSeriesScorer()

    # Build query
    if drug_names:
        drug_filter = "AND LOWER(drug_name) IN (SELECT LOWER(unnest(%s::text[])))"
        params = (drug_names,)
    else:
        drug_filter = ""
        params = ()

    with db.cursor() as cur:
        # Get all extractions that need rescoring
        cur.execute(f"""
            SELECT id, pmid, drug_name, disease, n_patients,
                   efficacy_signal, efficacy_summary, response_rate, responders_pct,
                   evidence_level, study_design, follow_up_duration, follow_up_weeks,
                   primary_endpoint, response_definition_quality, biomarkers_data,
                   paper_title, paper_year, individual_score
            FROM cs_extractions
            WHERE 1=1 {drug_filter}
            ORDER BY drug_name, n_patients DESC NULLS LAST
        """, params if params else None)

        rows = cur.fetchall()
        logger.info(f"Found {len(rows)} extractions to rescore")

        updated = 0
        by_drug = {}

        for row in rows:
            drug = row['drug_name']
            if drug not in by_drug:
                by_drug[drug] = {'count': 0, 'old_avg': 0, 'new_avg': 0, 'scores': []}

            # Build minimal extraction object for scoring
            extraction = CaseSeriesExtraction(
                source=CaseSeriesSource(
                    pmid=row['pmid'],
                    title=row['paper_title'] or '',
                    year=row['paper_year'],
                ),
                disease=row['disease'] or 'Unknown',
                evidence_level=row['evidence_level'] or 'Case Report',
                patient_population=PatientPopulation(
                    n_patients=row['n_patients'],
                ),
                treatment=TreatmentDetails(
                    drug_name=drug,
                ),
                efficacy=EfficacyOutcome(
                    response_rate=row['response_rate'],
                    responders_pct=row['responders_pct'],
                    efficacy_summary=row['efficacy_summary'],
                    primary_endpoint=row['primary_endpoint'],
                ),
                safety=SafetyOutcome(),
                efficacy_signal=row['efficacy_signal'] or 'Unknown',
                study_design=row['study_design'],
                follow_up_duration=row['follow_up_duration'],
                follow_up_weeks=row['follow_up_weeks'],
                response_definition_quality=row['response_definition_quality'],
            )

            # Parse biomarkers if present
            if row['biomarkers_data']:
                try:
                    biomarkers = json.loads(row['biomarkers_data']) if isinstance(row['biomarkers_data'], str) else row['biomarkers_data']
                    from src.models.case_series_schemas import BiomarkerResult
                    extraction.biomarkers = [BiomarkerResult(**b) for b in biomarkers]
                except:
                    pass

            # Calculate new score
            new_score = scorer.score_extraction(extraction)
            old_score = float(row['individual_score']) if row['individual_score'] is not None else None

            by_drug[drug]['count'] += 1
            by_drug[drug]['scores'].append(new_score.total_score)
            if old_score:
                by_drug[drug]['old_avg'] += old_score

            # Update if score changed
            if old_score is None or abs(new_score.total_score - old_score) > 0.01:
                if not dry_run:
                    cur.execute("""
                        UPDATE cs_extractions
                        SET individual_score = %s,
                            score_breakdown = %s
                        WHERE id = %s
                    """, (
                        new_score.total_score,
                        json.dumps(new_score.model_dump()),
                        row['id']
                    ))
                updated += 1

                if row['n_patients'] and row['n_patients'] >= 50:
                    logger.info(f"  {row['pmid']}: {drug} N={row['n_patients']} | {old_score} -> {new_score.total_score}")

        if not dry_run:
            db.commit()

    # Summary
    logger.info(f"\n{'='*80}")
    logger.info(f"SCORE RECALCULATION {'(DRY RUN)' if dry_run else 'COMPLETE'}")
    logger.info(f"{'='*80}")
    logger.info(f"Total extractions processed: {len(rows)}")
    logger.info(f"Scores updated: {updated}")

    logger.info(f"\nBy Drug:")
    for drug, stats in sorted(by_drug.items()):
        if stats['scores']:
            new_avg = sum(stats['scores']) / len(stats['scores'])
            old_avg = stats['old_avg'] / stats['count'] if stats['count'] > 0 else 0
            logger.info(f"  {drug}: {stats['count']} papers, avg score {old_avg:.2f} -> {new_avg:.2f}")

    return updated


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Recalculate paper scores')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without updating')
    parser.add_argument('--drugs', type=str, help='Comma-separated list of drugs to rescore')
    args = parser.parse_args()

    drugs = args.drugs.split(',') if args.drugs else None
    recalculate_scores(drug_names=drugs, dry_run=args.dry_run)
