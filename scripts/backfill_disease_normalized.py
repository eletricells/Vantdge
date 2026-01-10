"""
Backfill disease_normalized column in cs_extractions table.

This script normalizes existing disease names using the DiseaseStandardizer
to ensure consistent aggregation across all extractions.
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_disease_normalized():
    """Backfill disease_normalized column in cs_extractions."""
    from src.drug_extraction_system.database.connection import DatabaseConnection
    from src.case_series.services.disease_standardizer import DiseaseStandardizer

    db = DatabaseConnection()
    standardizer = DiseaseStandardizer()

    logger.info("Starting disease_normalized backfill...")

    # First, run the migration to add the column if needed
    logger.info("Ensuring disease_normalized column exists...")
    with db.cursor() as cur:
        cur.execute("""
            ALTER TABLE cs_extractions
            ADD COLUMN IF NOT EXISTS disease_normalized VARCHAR(500)
        """)
        db.commit()

    # Create index if not exists
    with db.cursor() as cur:
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cs_extractions_disease_normalized
            ON cs_extractions(disease_normalized)
        """)
        db.commit()

    # Get all distinct diseases that need normalization
    with db.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT disease
            FROM cs_extractions
            WHERE disease IS NOT NULL
              AND disease != ''
              AND (disease_normalized IS NULL OR disease_normalized = '')
        """)
        diseases = [row['disease'] for row in cur.fetchall()]

    logger.info(f"Found {len(diseases)} distinct diseases to normalize")

    # Pre-compute normalizations
    disease_mapping = {}
    for disease in diseases:
        normalized = standardizer.standardize(disease)
        disease_mapping[disease] = normalized
        if disease != normalized:
            logger.info(f"  '{disease}' -> '{normalized}'")

    # Update in batches
    batch_size = 100
    updated_count = 0

    for disease, normalized in disease_mapping.items():
        with db.cursor() as cur:
            cur.execute("""
                UPDATE cs_extractions
                SET disease_normalized = %s
                WHERE disease = %s
                  AND (disease_normalized IS NULL OR disease_normalized = '')
            """, (normalized, disease))
            updated_count += cur.rowcount
            db.commit()

    logger.info(f"Updated {updated_count} extractions with normalized disease names")

    # Also update parent_disease column if it exists
    try:
        with db.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'cs_extractions' AND column_name = 'parent_disease'
            """)
            if cur.fetchone():
                logger.info("Updating parent_disease column...")
                for disease, normalized in disease_mapping.items():
                    parent = standardizer.get_parent_disease(normalized)
                    cur.execute("""
                        UPDATE cs_extractions
                        SET parent_disease = %s
                        WHERE disease = %s
                          AND (parent_disease IS NULL OR parent_disease = '')
                    """, (parent if parent != normalized else None, disease))
                db.commit()
                logger.info("Parent disease column updated")
    except Exception as e:
        logger.warning(f"Could not update parent_disease: {e}")

    # Print summary of normalizations
    logger.info("\n=== Disease Normalization Summary ===")
    changed = [(d, n) for d, n in disease_mapping.items() if d != n]
    if changed:
        logger.info(f"\n{len(changed)} diseases were normalized:")
        for disease, normalized in sorted(changed):
            logger.info(f"  '{disease}' -> '{normalized}'")
    else:
        logger.info("No diseases required normalization")

    logger.info("\nBackfill complete!")


if __name__ == "__main__":
    backfill_disease_normalized()
