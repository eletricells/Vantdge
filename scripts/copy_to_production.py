"""
Copy data from local database to production database.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import sql

# Database URLs
LOCAL_URL = os.getenv('DATABASE_URL')
PROD_URL = "postgresql://postgres:rLUGCpOgJHPSuPBJVAcXBdEwIPpyFOVl@trolley.proxy.rlwy.net:57642/railway"

# Tables to copy (in order to respect foreign keys)
TABLES_TO_COPY = [
    # Core reference tables first
    'drugs',
    'diseases',
    'schema_migrations',

    # Drug-related tables
    'drug_identifiers',
    'drug_indications',
    'drug_dosing_regimens',
    'drug_efficacy_data',
    'drug_safety_data',
    'drug_clinical_trials',
    'drug_data_sources',
    'drug_audit_log',
    'drug_metadata',

    # Trial conditions
    'trial_conditions',

    # Condition/disease mappings
    'condition_mappings',
    'standardized_conditions',

    # Case series tables
    'cs_analysis_runs',
    'cs_extractions',
    'cs_opportunities',
    'cs_market_intelligence',
    'cs_discovery_papers',
    'cs_disease_name_variants',
    'cs_papers_for_manual_review',
    'cs_score_explanations',
    'cs_drugs',
    'cs_paper_discoveries',

    # Disease intelligence
    'disease_intelligence',
    'disease_intel_sources',
    'disease_pipeline_runs',
    'disease_pipeline_sources',
]


def get_table_columns(conn, table_name):
    """Get column names for a table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = %s AND table_schema = 'public'
            ORDER BY ordinal_position
        """, (table_name,))
        return [row[0] for row in cur.fetchall()]


def copy_table(local_conn, prod_conn, table_name):
    """Copy all data from local table to production."""
    try:
        # Get columns from local
        local_cols = get_table_columns(local_conn, table_name)
        prod_cols = get_table_columns(prod_conn, table_name)

        if not local_cols:
            print(f"  {table_name}: Table not found in local DB, skipping")
            return 0

        if not prod_cols:
            print(f"  {table_name}: Table not found in production DB, skipping")
            return 0

        # Use intersection of columns (handle schema differences)
        common_cols = [c for c in local_cols if c in prod_cols]

        if not common_cols:
            print(f"  {table_name}: No common columns, skipping")
            return 0

        # Fetch all data from local
        with local_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cols_sql = ', '.join([f'"{c}"' for c in common_cols])
            cur.execute(f'SELECT {cols_sql} FROM "{table_name}"')
            rows = cur.fetchall()

        if not rows:
            print(f"  {table_name}: 0 rows (empty)")
            return 0

        # Clear production table and insert
        with prod_conn.cursor() as cur:
            # Disable triggers temporarily
            cur.execute(f'ALTER TABLE "{table_name}" DISABLE TRIGGER ALL')

            # Delete existing data
            cur.execute(f'DELETE FROM "{table_name}"')

            # Build insert query
            cols_sql = ', '.join([f'"{c}"' for c in common_cols])
            placeholders = ', '.join(['%s'] * len(common_cols))
            insert_sql = f'INSERT INTO "{table_name}" ({cols_sql}) VALUES ({placeholders})'

            # Insert in batches
            batch_size = 100
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                values = [[row[c] for c in common_cols] for row in batch]
                cur.executemany(insert_sql, values)

            # Re-enable triggers
            cur.execute(f'ALTER TABLE "{table_name}" ENABLE TRIGGER ALL')

            prod_conn.commit()

        print(f"  {table_name}: {len(rows)} rows copied")
        return len(rows)

    except Exception as e:
        prod_conn.rollback()
        print(f"  {table_name}: ERROR - {str(e)[:100]}")
        return -1


def main():
    print("Connecting to databases...")

    local_conn = psycopg2.connect(LOCAL_URL)
    prod_conn = psycopg2.connect(PROD_URL)

    print(f"Local: connected")
    print(f"Production: connected")
    print()

    total_rows = 0
    errors = []

    print("Copying tables...")
    for table in TABLES_TO_COPY:
        result = copy_table(local_conn, prod_conn, table)
        if result > 0:
            total_rows += result
        elif result < 0:
            errors.append(table)

    print()
    print("="*60)
    print(f"COPY COMPLETE")
    print(f"Total rows copied: {total_rows}")
    if errors:
        print(f"Tables with errors: {', '.join(errors)}")
    print("="*60)

    local_conn.close()
    prod_conn.close()


if __name__ == "__main__":
    main()
