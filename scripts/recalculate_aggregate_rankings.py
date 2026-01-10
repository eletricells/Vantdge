"""
Recalculate aggregate rankings in cs_opportunities table.

This script recalculates disease-level aggregate scores and rankings
after individual paper scores have been updated.

Aggregation logic:
- aggregate_score: N-weighted average of individual paper scores
- best_paper: PMID with highest individual score
- consistency_level: Based on coefficient of variation of response rates
- evidence_level: Best (highest) evidence level from component papers
"""

import os
import sys
import json
import logging
import statistics
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Evidence level hierarchy (higher = better)
EVIDENCE_HIERARCHY = {
    'RCT': 10,
    'Randomized Trial': 10,
    'Controlled Trial': 9,
    'Meta-Analysis': 8,
    'Systematic Review': 7,
    'Prospective Cohort': 6,
    'Retrospective Study': 5,
    'Case Series': 4,
    'Case Report': 3,
    'Unknown': 1,
}


def get_best_evidence_level(evidence_levels: List[str]) -> str:
    """Get the best (highest quality) evidence level from a list."""
    if not evidence_levels:
        return 'Case Report'

    scored = [(level, EVIDENCE_HIERARCHY.get(level, 1)) for level in evidence_levels]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[0][0]


def calculate_consistency(response_rates: List[float]) -> Tuple[str, Optional[float]]:
    """
    Calculate consistency level based on coefficient of variation.

    Returns:
        Tuple of (consistency_level, cv)
    """
    if len(response_rates) < 2:
        return 'N/A', None

    # Filter out None and 0 values for meaningful CV
    valid_rates = [r for r in response_rates if r is not None and r > 0]
    if len(valid_rates) < 2:
        return 'N/A', None

    try:
        mean = statistics.mean(valid_rates)
        if mean == 0:
            return 'N/A', None
        stdev = statistics.stdev(valid_rates)
        cv = (stdev / mean) * 100  # CV as percentage

        if cv < 25:
            return 'High', round(cv, 2)
        elif cv < 50:
            return 'Moderate', round(cv, 2)
        else:
            return 'Low', round(cv, 2)
    except Exception:
        return 'N/A', None


def get_aggregate_efficacy_signal(signals: List[str]) -> str:
    """Determine aggregate efficacy signal from component papers."""
    signal_scores = {
        'Strong': 3,
        'Moderate': 2,
        'Weak': 1,
        'None': 0,
        'Mixed': 1.5,
        'Unknown': None,
    }

    valid_signals = [s for s in signals if s and s != 'Unknown']
    if not valid_signals:
        return 'Unknown'

    scored = [signal_scores.get(s, 0) for s in valid_signals if signal_scores.get(s) is not None]
    if not scored:
        return 'Unknown'

    avg = sum(scored) / len(scored)
    if avg >= 2.5:
        return 'Strong'
    elif avg >= 1.5:
        return 'Moderate'
    elif avg >= 0.5:
        return 'Weak'
    else:
        return 'None'


def recalculate_aggregate_rankings(drug_names: List[str] = None, dry_run: bool = False):
    """Recalculate aggregate rankings for specified drugs or all drugs."""
    from src.drug_extraction_system.database.connection import DatabaseConnection

    db = DatabaseConnection()

    # Build drug filter
    if drug_names:
        drug_filter = "AND LOWER(e.drug_name) IN (SELECT LOWER(unnest(%s::text[])))"
        params = (drug_names,)
    else:
        drug_filter = ""
        params = ()

    with db.cursor() as cur:
        # Get all extractions grouped by drug/disease
        cur.execute(f"""
            SELECT
                e.drug_name,
                e.disease,
                e.pmid,
                e.n_patients,
                e.individual_score,
                e.responders_pct,
                e.evidence_level,
                e.efficacy_signal,
                e.safety_summary,
                e.run_id
            FROM cs_extractions e
            WHERE e.is_relevant = true
            {drug_filter}
            ORDER BY e.drug_name, e.disease, e.individual_score DESC NULLS LAST
        """, params if params else None)

        rows = cur.fetchall()
        logger.info(f"Found {len(rows)} relevant extractions")

        # Group by drug/disease
        groups = defaultdict(list)
        for row in rows:
            key = (row['drug_name'], row['disease'])
            groups[key].append(row)

        logger.info(f"Grouped into {len(groups)} drug/disease combinations")

        updated = 0
        inserted = 0

        for (drug_name, disease), papers in groups.items():
            # Calculate aggregates
            total_patients = sum(p['n_patients'] or 0 for p in papers)
            paper_count = len(papers)

            # N-weighted average score
            weighted_scores = []
            total_weight = 0
            for p in papers:
                n = p['n_patients'] or 1
                score = float(p['individual_score']) if p['individual_score'] is not None else 5.0
                weighted_scores.append(score * n)
                total_weight += n

            aggregate_score = sum(weighted_scores) / total_weight if total_weight > 0 else 5.0

            # Best paper
            best_paper = max(papers, key=lambda x: float(x['individual_score']) if x['individual_score'] else 0)
            best_paper_pmid = best_paper['pmid']
            best_paper_score = float(best_paper['individual_score']) if best_paper['individual_score'] else None

            # Response rate metrics
            response_rates = [float(p['responders_pct']) for p in papers if p['responders_pct'] is not None]
            avg_response_rate = statistics.mean(response_rates) if response_rates else None
            consistency_level, cv = calculate_consistency(response_rates)

            # Evidence level (best from papers)
            evidence_levels = [p['evidence_level'] for p in papers if p['evidence_level']]
            best_evidence = get_best_evidence_level(evidence_levels)

            # Efficacy signal (aggregate)
            signals = [p['efficacy_signal'] for p in papers if p['efficacy_signal']]
            aggregate_signal = get_aggregate_efficacy_signal(signals)

            # PMIDs list
            pmids = [p['pmid'] for p in papers if p['pmid']]

            # Get run_id (use most recent)
            run_id = papers[0]['run_id']

            # Individual scores for JSON
            individual_scores = [
                {
                    'pmid': p['pmid'],
                    'n_patients': p['n_patients'],
                    'score': float(p['individual_score']) if p['individual_score'] else None
                }
                for p in papers
            ]

            if not dry_run:
                # Check if opportunity exists
                cur.execute("""
                    SELECT id FROM cs_opportunities
                    WHERE drug_name = %s AND disease = %s
                """, (drug_name, disease))
                existing = cur.fetchone()

                if existing:
                    # Update existing - include ALL aggregate columns
                    cur.execute("""
                        UPDATE cs_opportunities SET
                            total_patients = %s,
                            paper_count = %s,
                            study_count = %s,
                            avg_response_rate = %s,
                            efficacy_signal = %s,
                            evidence_level = %s,
                            score_total = %s,
                            aggregate_score = %s,
                            best_paper_pmid = %s,
                            best_paper_score = %s,
                            consistency_level = %s,
                            response_rate_cv = %s,
                            pmids = %s
                        WHERE id = %s
                    """, (
                        total_patients,
                        paper_count,
                        paper_count,  # study_count = paper_count
                        avg_response_rate,
                        aggregate_signal,
                        best_evidence,
                        round(aggregate_score, 2),
                        round(aggregate_score, 2),  # aggregate_score
                        best_paper_pmid,
                        round(best_paper_score, 2) if best_paper_score else None,
                        consistency_level if consistency_level != 'N/A' else None,
                        cv,
                        json.dumps(pmids),
                        existing['id']
                    ))
                    updated += 1
                else:
                    # Insert new - include ALL aggregate columns
                    cur.execute("""
                        INSERT INTO cs_opportunities (
                            run_id, drug_name, disease, total_patients, paper_count,
                            study_count, avg_response_rate, efficacy_signal, evidence_level,
                            score_total, aggregate_score, best_paper_pmid, best_paper_score,
                            consistency_level, response_rate_cv, pmids
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        run_id,
                        drug_name,
                        disease,
                        total_patients,
                        paper_count,
                        paper_count,  # study_count
                        avg_response_rate,
                        aggregate_signal,
                        best_evidence,
                        round(aggregate_score, 2),
                        round(aggregate_score, 2),  # aggregate_score
                        best_paper_pmid,
                        round(best_paper_score, 2) if best_paper_score else None,
                        consistency_level if consistency_level != 'N/A' else None,
                        cv,
                        json.dumps(pmids)
                    ))
                    inserted += 1

                # Log significant changes
                if paper_count >= 3 or total_patients >= 50:
                    logger.info(f"  {drug_name} | {disease}: {paper_count} papers, N={total_patients}, score={aggregate_score:.2f}")

        # Recalculate ranks within each drug
        if not dry_run:
            cur.execute("""
                WITH ranked AS (
                    SELECT id, drug_name, score_total,
                           ROW_NUMBER() OVER (PARTITION BY drug_name ORDER BY score_total DESC) as new_rank
                    FROM cs_opportunities
                )
                UPDATE cs_opportunities o
                SET rank = r.new_rank
                FROM ranked r
                WHERE o.id = r.id
            """)

            db.commit()

    # Summary
    logger.info(f"\n{'='*80}")
    logger.info(f"AGGREGATE RANKING UPDATE {'(DRY RUN)' if dry_run else 'COMPLETE'}")
    logger.info(f"{'='*80}")
    logger.info(f"Drug/disease combinations processed: {len(groups)}")
    logger.info(f"Opportunities updated: {updated}")
    logger.info(f"Opportunities inserted: {inserted}")

    return updated + inserted


def show_top_opportunities(drug_names: List[str] = None, top_n: int = 10):
    """Display top opportunities after recalculation."""
    from src.drug_extraction_system.database.connection import DatabaseConnection

    db = DatabaseConnection()

    if drug_names:
        drug_filter = "WHERE LOWER(drug_name) IN (SELECT LOWER(unnest(%s::text[])))"
        params = (drug_names,)
    else:
        drug_filter = ""
        params = ()

    with db.cursor() as cur:
        cur.execute(f"""
            SELECT drug_name, disease, total_patients, paper_count,
                   score_total, efficacy_signal, evidence_level, rank
            FROM cs_opportunities
            {drug_filter}
            ORDER BY score_total DESC
            LIMIT %s
        """, (*params, top_n) if params else (top_n,))

        rows = cur.fetchall()

        logger.info(f"\n{'='*80}")
        logger.info(f"TOP {top_n} OPPORTUNITIES")
        logger.info(f"{'='*80}")

        for row in rows:
            logger.info(
                f"#{row['rank']} | {row['drug_name']} → {row['disease']} | "
                f"Score: {row['score_total']} | N={row['total_patients']} | "
                f"{row['paper_count']} papers | {row['evidence_level']} | {row['efficacy_signal']}"
            )


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Recalculate aggregate rankings')
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without updating')
    parser.add_argument('--drugs', type=str, help='Comma-separated list of drugs to process')
    parser.add_argument('--show-top', type=int, default=10, help='Show top N opportunities after update')
    args = parser.parse_args()

    drugs = args.drugs.split(',') if args.drugs else None

    recalculate_aggregate_rankings(drug_names=drugs, dry_run=args.dry_run)

    if not args.dry_run:
        show_top_opportunities(drug_names=drugs, top_n=args.show_top)
