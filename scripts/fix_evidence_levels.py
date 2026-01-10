"""
Fix evidence level mismatches in cs_extractions table.

This script corrects evidence_level based on study_design for existing extractions
that weren't processed through the updated extraction pipeline.

Mappings:
- Prospective Controlled → RCT (if title suggests randomized) or Controlled Trial
- Double-Blind RCT → RCT
- Open-Label RCT → RCT
- Randomized Controlled Trial → RCT
- Retrospective (design) + Case Series (level) → Retrospective Study
- Prospective Open-Label + Case Series → Prospective Cohort
"""

import os
import sys
import re
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

# Keywords that suggest RCT
RCT_KEYWORDS = [
    'randomized', 'randomised', 'placebo-controlled', 'double-blind',
    'double blind', 'phase 2', 'phase 3', 'phase ii', 'phase iii',
    'phase 2b', 'phase 3b', 'rct', 'controlled trial'
]


def title_suggests_rct(title: str) -> bool:
    """Check if paper title suggests it's an RCT."""
    if not title:
        return False
    title_lower = title.lower()
    return any(kw in title_lower for kw in RCT_KEYWORDS)


def fix_evidence_levels(dry_run: bool = False):
    """Fix evidence level mismatches in database."""
    from src.drug_extraction_system.database.connection import DatabaseConnection

    db = DatabaseConnection()

    changes = {
        'prospective_controlled_to_rct': [],
        'prospective_controlled_to_controlled_trial': [],
        'retrospective_to_retrospective_study': [],
        'prospective_open_label_to_prospective_cohort': [],
        'double_blind_rct_to_rct': [],
        'open_label_rct_to_rct': [],
        'randomized_to_rct': [],
    }

    with db.cursor() as cur:
        # Get all records with potential mismatches
        cur.execute("""
            SELECT id, pmid, drug_name, disease, paper_title, study_design, evidence_level, n_patients
            FROM cs_extractions
            WHERE (
                -- Prospective Controlled but not RCT/Controlled Trial
                (study_design = 'Prospective Controlled' AND evidence_level NOT IN ('RCT', 'Controlled Trial', 'Randomized Trial'))
                -- Or explicit RCT designs not mapped
                OR (study_design IN ('Double-Blind RCT', 'Open-Label RCT', 'Randomized Controlled Trial') AND evidence_level != 'RCT')
                -- Or Retrospective design but Case Series level
                OR (study_design = 'Retrospective' AND evidence_level = 'Case Series')
                -- Or Prospective Open-Label but Case Series level (for large studies)
                OR (study_design = 'Prospective Open-Label' AND evidence_level = 'Case Series' AND n_patients >= 20)
            )
            ORDER BY n_patients DESC NULLS LAST
        """)

        records = cur.fetchall()
        logger.info(f"Found {len(records)} records with potential evidence level issues")

        for record in records:
            old_level = record['evidence_level']
            new_level = None
            change_type = None

            design = record['study_design']
            title = record['paper_title'] or ''

            if design == 'Prospective Controlled':
                if title_suggests_rct(title):
                    new_level = 'RCT'
                    change_type = 'prospective_controlled_to_rct'
                else:
                    new_level = 'Controlled Trial'
                    change_type = 'prospective_controlled_to_controlled_trial'

            elif design == 'Double-Blind RCT':
                new_level = 'RCT'
                change_type = 'double_blind_rct_to_rct'

            elif design == 'Open-Label RCT':
                new_level = 'RCT'
                change_type = 'open_label_rct_to_rct'

            elif design == 'Randomized Controlled Trial':
                new_level = 'RCT'
                change_type = 'randomized_to_rct'

            elif design == 'Retrospective' and old_level == 'Case Series':
                new_level = 'Retrospective Study'
                change_type = 'retrospective_to_retrospective_study'

            elif design == 'Prospective Open-Label' and old_level == 'Case Series':
                new_level = 'Prospective Cohort'
                change_type = 'prospective_open_label_to_prospective_cohort'

            if new_level and new_level != old_level:
                changes[change_type].append({
                    'id': record['id'],
                    'pmid': record['pmid'],
                    'drug': record['drug_name'],
                    'disease': record['disease'],
                    'n': record['n_patients'],
                    'old': old_level,
                    'new': new_level,
                    'title': title[:60]
                })

                if not dry_run:
                    cur.execute("""
                        UPDATE cs_extractions
                        SET evidence_level = %s
                        WHERE id = %s
                    """, (new_level, record['id']))

        if not dry_run:
            db.commit()

    # Print summary
    total_changes = sum(len(v) for v in changes.values())
    logger.info(f"\n{'='*80}")
    logger.info(f"EVIDENCE LEVEL FIX {'(DRY RUN)' if dry_run else 'COMPLETE'}")
    logger.info(f"{'='*80}")
    logger.info(f"Total changes: {total_changes}")

    for change_type, records in changes.items():
        if records:
            logger.info(f"\n{change_type.upper().replace('_', ' ')} ({len(records)} records):")
            for r in records[:5]:
                logger.info(f"  PMID {r['pmid']}: {r['drug']} N={r['n']} | {r['old']} → {r['new']}")
                logger.info(f"    {r['disease']}: {r['title']}...")
            if len(records) > 5:
                logger.info(f"  ... and {len(records) - 5} more")

    return changes


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Fix evidence level mismatches')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without making changes')
    args = parser.parse_args()

    fix_evidence_levels(dry_run=args.dry_run)
