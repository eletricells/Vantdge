"""
Set up production database schema and copy data from local.
"""

import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
from psycopg2.extras import RealDictCursor, Json

# Database URLs
LOCAL_URL = os.getenv('DATABASE_URL')
PROD_URL = "postgresql://postgres:rLUGCpOgJHPSuPBJVAcXBdEwIPpyFOVl@trolley.proxy.rlwy.net:57642/railway"


def create_schema(conn):
    """Create missing tables in production."""
    schema_sql = """
    -- Enable UUID extension
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    -- Diseases table
    CREATE TABLE IF NOT EXISTS diseases (
        disease_id SERIAL PRIMARY KEY,
        disease_name_standard VARCHAR(255) NOT NULL UNIQUE,
        disease_aliases JSONB,
        icd10_codes JSONB,
        therapeutic_area VARCHAR(100),
        prevalence_notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Drugs table
    CREATE TABLE IF NOT EXISTS drugs (
        drug_id SERIAL PRIMARY KEY,
        brand_name VARCHAR(255),
        generic_name VARCHAR(255) NOT NULL,
        manufacturer VARCHAR(255),
        drug_type VARCHAR(100),
        mechanism_of_action VARCHAR(500),
        mechanism_details TEXT,
        target VARCHAR(255),
        approval_status VARCHAR(50),
        highest_phase VARCHAR(20),
        first_approval_date DATE,
        dailymed_setid VARCHAR(100),
        parent_drug_id INTEGER REFERENCES drugs(drug_id),
        is_combination BOOLEAN DEFAULT FALSE,
        combination_components INTEGER[],
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Drug indications
    CREATE TABLE IF NOT EXISTS drug_indications (
        indication_id SERIAL PRIMARY KEY,
        drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
        disease_id INTEGER REFERENCES diseases(disease_id),
        disease_name VARCHAR(500),
        indication_raw TEXT,
        approval_status VARCHAR(50),
        approval_date DATE,
        approval_year INTEGER,
        approval_source VARCHAR(50),
        line_of_therapy VARCHAR(100),
        population_restrictions TEXT,
        label_section VARCHAR(100),
        data_source VARCHAR(50),
        severity_mild BOOLEAN DEFAULT FALSE,
        severity_moderate BOOLEAN DEFAULT FALSE,
        severity_severe BOOLEAN DEFAULT FALSE,
        source_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Drug dosing regimens
    CREATE TABLE IF NOT EXISTS drug_dosing_regimens (
        dosing_id SERIAL PRIMARY KEY,
        drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
        indication_id INTEGER REFERENCES drug_indications(indication_id) ON DELETE CASCADE,
        regimen_phase VARCHAR(50),
        dose_amount NUMERIC(10, 2),
        dose_unit VARCHAR(50),
        frequency_standard VARCHAR(20),
        frequency_raw TEXT,
        route_standard VARCHAR(10),
        route_raw TEXT,
        duration_weeks INTEGER,
        weight_based BOOLEAN DEFAULT FALSE,
        sequence_order INTEGER,
        dosing_notes TEXT,
        data_source VARCHAR(50),
        source_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Drug metadata
    CREATE TABLE IF NOT EXISTS drug_metadata (
        drug_id INTEGER PRIMARY KEY REFERENCES drugs(drug_id) ON DELETE CASCADE,
        patent_expiry DATE,
        exclusivity_end DATE,
        orphan_designation BOOLEAN DEFAULT FALSE,
        breakthrough_therapy BOOLEAN DEFAULT FALSE,
        fast_track BOOLEAN DEFAULT FALSE,
        accelerated_approval BOOLEAN DEFAULT FALSE,
        first_in_class BOOLEAN DEFAULT FALSE,
        biosimilar_available BOOLEAN DEFAULT FALSE,
        has_black_box_warning BOOLEAN DEFAULT FALSE,
        contraindications_summary TEXT,
        safety_notes TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Drug identifiers
    CREATE TABLE IF NOT EXISTS drug_identifiers (
        identifier_id SERIAL PRIMARY KEY,
        drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
        identifier_type VARCHAR(50) NOT NULL,
        identifier_value VARCHAR(200) NOT NULL,
        source VARCHAR(100),
        confidence VARCHAR(20) DEFAULT 'high',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(identifier_type, identifier_value)
    );

    -- Drug clinical trials
    CREATE TABLE IF NOT EXISTS drug_clinical_trials (
        trial_id SERIAL PRIMARY KEY,
        drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
        nct_id VARCHAR(20) NOT NULL,
        trial_title TEXT,
        trial_phase VARCHAR(50),
        trial_status VARCHAR(100),
        start_date DATE,
        completion_date DATE,
        enrollment INTEGER,
        conditions JSONB,
        interventions JSONB,
        sponsors JSONB,
        locations JSONB,
        primary_outcome TEXT,
        secondary_outcomes JSONB,
        data_source VARCHAR(50) DEFAULT 'ClinicalTrials.gov',
        last_updated_from_source TIMESTAMP,
        is_industry_sponsored BOOLEAN,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(drug_id, nct_id)
    );

    -- Drug data sources
    CREATE TABLE IF NOT EXISTS drug_data_sources (
        source_id SERIAL PRIMARY KEY,
        drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
        source_type VARCHAR(50) NOT NULL,
        source_name VARCHAR(200),
        source_url TEXT,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        data_hash VARCHAR(64),
        status VARCHAR(20) DEFAULT 'success',
        error_message TEXT
    );

    -- Drug audit log
    CREATE TABLE IF NOT EXISTS drug_audit_log (
        log_id SERIAL PRIMARY KEY,
        drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
        action VARCHAR(50) NOT NULL,
        field_changed VARCHAR(100),
        old_value TEXT,
        new_value TEXT,
        changed_by VARCHAR(100) DEFAULT 'system',
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        source VARCHAR(100)
    );

    -- Drug efficacy data
    CREATE TABLE IF NOT EXISTS drug_efficacy_data (
        efficacy_id SERIAL PRIMARY KEY,
        drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
        indication_id INTEGER REFERENCES drug_indications(indication_id),
        disease_name VARCHAR(500),
        endpoint_name VARCHAR(500),
        endpoint_type VARCHAR(100),
        response_rate NUMERIC(5,2),
        response_rate_unit VARCHAR(50),
        response_n INTEGER,
        total_n INTEGER,
        comparator VARCHAR(255),
        comparator_rate NUMERIC(5,2),
        study_name VARCHAR(500),
        nct_id VARCHAR(20),
        publication_pmid VARCHAR(20),
        data_source VARCHAR(50),
        source_url TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Drug safety data
    CREATE TABLE IF NOT EXISTS drug_safety_data (
        safety_id SERIAL PRIMARY KEY,
        drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
        indication_id INTEGER REFERENCES drug_indications(indication_id),
        disease_name VARCHAR(500),
        event_name VARCHAR(500),
        event_type VARCHAR(100),
        event_rate NUMERIC(5,2),
        event_rate_unit VARCHAR(50),
        event_n INTEGER,
        total_n INTEGER,
        severity VARCHAR(50),
        study_name VARCHAR(500),
        nct_id VARCHAR(20),
        publication_pmid VARCHAR(20),
        data_source VARCHAR(50),
        source_url TEXT,
        notes TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Trial conditions
    CREATE TABLE IF NOT EXISTS trial_conditions (
        id SERIAL PRIMARY KEY,
        nct_id VARCHAR(20) NOT NULL,
        condition_name TEXT NOT NULL,
        condition_mesh_id VARCHAR(20),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Condition mappings
    CREATE TABLE IF NOT EXISTS condition_mappings (
        id SERIAL PRIMARY KEY,
        original_condition TEXT NOT NULL,
        standardized_condition TEXT NOT NULL,
        mesh_id VARCHAR(20),
        mapping_source VARCHAR(50),
        confidence NUMERIC(3,2),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(original_condition)
    );

    -- Standardized conditions
    CREATE TABLE IF NOT EXISTS standardized_conditions (
        id SERIAL PRIMARY KEY,
        condition_name VARCHAR(500) NOT NULL UNIQUE,
        mesh_id VARCHAR(20),
        mesh_term VARCHAR(500),
        synonyms JSONB,
        parent_condition VARCHAR(500),
        therapeutic_area VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Schema migrations
    CREATE TABLE IF NOT EXISTS schema_migrations (
        migration_name TEXT PRIMARY KEY,
        applied_at TIMESTAMP DEFAULT NOW(),
        description TEXT
    );

    -- CS extractions - add missing columns
    ALTER TABLE cs_extractions ADD COLUMN IF NOT EXISTS drug_id INT;
    ALTER TABLE cs_extractions ADD COLUMN IF NOT EXISTS scored_at TIMESTAMP;

    -- Create indexes
    CREATE INDEX IF NOT EXISTS idx_drugs_generic ON drugs(generic_name);
    CREATE INDEX IF NOT EXISTS idx_drugs_brand ON drugs(brand_name);
    CREATE INDEX IF NOT EXISTS idx_drug_indications_drug ON drug_indications(drug_id);
    CREATE INDEX IF NOT EXISTS idx_clinical_trials_drug ON drug_clinical_trials(drug_id);
    CREATE INDEX IF NOT EXISTS idx_efficacy_drug ON drug_efficacy_data(drug_id);
    CREATE INDEX IF NOT EXISTS idx_safety_drug ON drug_safety_data(drug_id);
    """

    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    print("Schema created/updated successfully")


def copy_table_with_json(local_conn, prod_conn, table_name, json_columns=None):
    """Copy table data with proper JSONB handling."""
    json_columns = json_columns or []

    try:
        # Get columns
        with local_conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position
            """, (table_name,))
            local_cols = [row[0] for row in cur.fetchall()]

        with prod_conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = 'public'
                ORDER BY ordinal_position
            """, (table_name,))
            prod_cols = [row[0] for row in cur.fetchall()]

        if not local_cols or not prod_cols:
            print(f"  {table_name}: Table not found, skipping")
            return 0

        common_cols = [c for c in local_cols if c in prod_cols]
        if not common_cols:
            print(f"  {table_name}: No common columns, skipping")
            return 0

        # Fetch data
        with local_conn.cursor(cursor_factory=RealDictCursor) as cur:
            cols_sql = ', '.join([f'"{c}"' for c in common_cols])
            cur.execute(f'SELECT {cols_sql} FROM "{table_name}"')
            rows = cur.fetchall()

        if not rows:
            print(f"  {table_name}: 0 rows (empty)")
            return 0

        # Clear and insert
        with prod_conn.cursor() as cur:
            cur.execute(f'ALTER TABLE "{table_name}" DISABLE TRIGGER ALL')
            cur.execute(f'DELETE FROM "{table_name}"')

            cols_sql = ', '.join([f'"{c}"' for c in common_cols])
            placeholders = ', '.join(['%s'] * len(common_cols))
            insert_sql = f'INSERT INTO "{table_name}" ({cols_sql}) VALUES ({placeholders})'

            batch_size = 100
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                values = []
                for row in batch:
                    row_values = []
                    for c in common_cols:
                        val = row[c]
                        # Convert dict/list to Json for JSONB columns
                        if c in json_columns and isinstance(val, (dict, list)):
                            row_values.append(Json(val))
                        elif isinstance(val, (dict, list)):
                            # Try to detect JSONB columns
                            row_values.append(Json(val))
                        else:
                            row_values.append(val)
                    values.append(row_values)
                cur.executemany(insert_sql, values)

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
    print("Connected\n")

    print("Creating schema in production...")
    create_schema(prod_conn)
    print()

    # Tables to copy with their JSONB columns
    tables = [
        ('diseases', ['disease_aliases', 'icd10_codes']),
        ('drugs', ['combination_components']),
        ('drug_identifiers', []),
        ('drug_indications', []),
        ('drug_dosing_regimens', []),
        ('drug_metadata', []),
        ('drug_clinical_trials', ['conditions', 'interventions', 'sponsors', 'locations', 'secondary_outcomes']),
        ('drug_data_sources', []),
        ('drug_audit_log', []),
        ('drug_efficacy_data', []),
        ('drug_safety_data', []),
        ('trial_conditions', []),
        ('condition_mappings', []),
        ('standardized_conditions', ['synonyms']),
        ('schema_migrations', []),
        ('cs_analysis_runs', ['parameters']),
        ('cs_extractions', ['full_extraction', 'score_breakdown', 'biomarkers_data']),
        ('cs_opportunities', ['pmids']),
        ('cs_market_intelligence', ['approved_drugs', 'pipeline_drugs', 'key_competitors',
                                    'sources_epidemiology', 'sources_approved_drugs',
                                    'sources_treatment', 'sources_pipeline', 'sources_tam']),
        ('cs_disease_name_variants', []),
        ('cs_score_explanations', []),
    ]

    print("Copying tables...")
    total = 0
    for table_name, json_cols in tables:
        result = copy_table_with_json(local_conn, prod_conn, table_name, json_cols)
        if result > 0:
            total += result

    print(f"\nTotal rows copied: {total}")

    # Reset sequences
    print("\nResetting sequences...")
    with prod_conn.cursor() as cur:
        for table_name, _ in tables:
            try:
                # Get primary key column
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = %s AND column_default LIKE 'nextval%%'
                """, (table_name,))
                pk = cur.fetchone()
                if pk:
                    col = pk[0]
                    cur.execute(f"""
                        SELECT setval(pg_get_serial_sequence('{table_name}', '{col}'),
                               COALESCE((SELECT MAX({col}) FROM {table_name}), 1))
                    """)
            except:
                pass
        prod_conn.commit()

    print("\nDone!")
    local_conn.close()
    prod_conn.close()


if __name__ == "__main__":
    main()
