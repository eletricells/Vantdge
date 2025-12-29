-- Drug Extraction System Schema
-- Enhanced schema with drug_key system, audit logging, and versioning
-- Compatible with existing drug database tables

-- =============================================================================
-- EXTENSION FOR UUID GENERATION (if not exists)
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- SCHEMA MIGRATIONS TABLE (For tracking applied migrations)
-- =============================================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_name TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT NOW(),
    description TEXT
);

COMMENT ON TABLE schema_migrations IS 'Tracks applied database migrations to prevent re-running';

-- =============================================================================
-- BATCH CHECKPOINTS TABLE (For resumable batch processing)
-- =============================================================================
CREATE TABLE IF NOT EXISTS batch_checkpoints (
    batch_id TEXT PRIMARY KEY,
    csv_file TEXT NOT NULL,
    total_drugs INTEGER NOT NULL,
    processed_drugs INTEGER DEFAULT 0,
    last_processed_index INTEGER DEFAULT -1,
    status TEXT DEFAULT 'in_progress',  -- in_progress, completed, failed, interrupted
    started_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_batch_checkpoints_status ON batch_checkpoints(status);
CREATE INDEX IF NOT EXISTS idx_batch_checkpoints_started_at ON batch_checkpoints(started_at);

COMMENT ON TABLE batch_checkpoints IS 'Tracks batch processing progress for resumable operations';

-- =============================================================================
-- DRUG IDENTIFIERS TABLE (Cross-reference for multiple ID systems)
-- =============================================================================
CREATE TABLE IF NOT EXISTS drug_identifiers (
    identifier_id SERIAL PRIMARY KEY,
    drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
    identifier_type VARCHAR(50) NOT NULL,  -- 'drug_key', 'rxcui', 'chembl_id', etc.
    identifier_value VARCHAR(200) NOT NULL,
    source VARCHAR(100),  -- 'internal', 'rxnorm', 'chembl', 'fda', etc.
    confidence VARCHAR(20) DEFAULT 'high',  -- 'high', 'medium', 'low'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(identifier_type, identifier_value)
);

CREATE INDEX IF NOT EXISTS idx_drug_identifiers_lookup 
ON drug_identifiers(identifier_type, identifier_value);

CREATE INDEX IF NOT EXISTS idx_drug_identifiers_drug_id 
ON drug_identifiers(drug_id);

COMMENT ON TABLE drug_identifiers IS 'Cross-reference table for all drug identifier systems';

-- =============================================================================
-- CLINICAL TRIALS TABLE (Pipeline drug data from ClinicalTrials.gov)
-- =============================================================================
CREATE TABLE IF NOT EXISTS drug_clinical_trials (
    trial_id SERIAL PRIMARY KEY,
    drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
    nct_id VARCHAR(20) NOT NULL,  -- e.g., NCT04869137
    trial_title TEXT,
    trial_phase VARCHAR(50),  -- 'Phase 1', 'Phase 2', etc.
    trial_status VARCHAR(100),  -- 'Recruiting', 'Completed', etc.
    start_date DATE,
    completion_date DATE,
    enrollment INTEGER,
    conditions JSONB,  -- Array of conditions/diseases
    interventions JSONB,  -- Array of interventions
    sponsors JSONB,  -- Lead sponsor and collaborators
    locations JSONB,  -- Trial locations
    primary_outcome TEXT,
    secondary_outcomes JSONB,
    data_source VARCHAR(50) DEFAULT 'ClinicalTrials.gov',
    last_updated_from_source TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(drug_id, nct_id)
);

CREATE INDEX IF NOT EXISTS idx_clinical_trials_drug ON drug_clinical_trials(drug_id);
CREATE INDEX IF NOT EXISTS idx_clinical_trials_nct ON drug_clinical_trials(nct_id);
CREATE INDEX IF NOT EXISTS idx_clinical_trials_phase ON drug_clinical_trials(trial_phase);
CREATE INDEX IF NOT EXISTS idx_clinical_trials_status ON drug_clinical_trials(trial_status);

COMMENT ON TABLE drug_clinical_trials IS 'Clinical trial data from ClinicalTrials.gov';

-- =============================================================================
-- DATA SOURCES TABLE (Track where data came from)
-- =============================================================================
CREATE TABLE IF NOT EXISTS drug_data_sources (
    source_id SERIAL PRIMARY KEY,
    drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE CASCADE,
    source_name VARCHAR(100) NOT NULL,  -- 'openFDA', 'RxNorm', 'ClinicalTrials.gov', etc.
    source_url TEXT,
    source_id_in_system VARCHAR(200),  -- ID in that system (e.g., RxCUI, NDC)
    data_retrieved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_hash VARCHAR(64),  -- SHA-256 hash of retrieved data for change detection
    raw_data JSONB,  -- Optionally store raw response
    UNIQUE(drug_id, source_name)
);

CREATE INDEX IF NOT EXISTS idx_data_sources_drug ON drug_data_sources(drug_id);
CREATE INDEX IF NOT EXISTS idx_data_sources_name ON drug_data_sources(source_name);

COMMENT ON TABLE drug_data_sources IS 'Tracks data provenance for each drug';

-- =============================================================================
-- AUDIT LOG TABLE (Change tracking)
-- =============================================================================
CREATE TABLE IF NOT EXISTS drug_audit_log (
    audit_id SERIAL PRIMARY KEY,
    table_name VARCHAR(100) NOT NULL,
    record_id INTEGER NOT NULL,  -- drug_id, indication_id, etc.
    drug_key VARCHAR(100),  -- For easy reference
    action VARCHAR(20) NOT NULL,  -- 'INSERT', 'UPDATE', 'DELETE'
    old_values JSONB,
    new_values JSONB,
    changed_fields TEXT[],  -- Array of field names that changed
    changed_by VARCHAR(100) DEFAULT 'system',
    batch_id UUID,  -- Links to processing batch
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_log_table ON drug_audit_log(table_name);
CREATE INDEX IF NOT EXISTS idx_audit_log_record ON drug_audit_log(table_name, record_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_drug_key ON drug_audit_log(drug_key);
CREATE INDEX IF NOT EXISTS idx_audit_log_batch ON drug_audit_log(batch_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_created ON drug_audit_log(created_at);

COMMENT ON TABLE drug_audit_log IS 'Audit trail for all drug data changes';

-- =============================================================================
-- PROCESS LOG TABLE (Batch processing tracking)
-- =============================================================================
CREATE TABLE IF NOT EXISTS drug_process_log (
    process_id SERIAL PRIMARY KEY,
    batch_id UUID NOT NULL DEFAULT uuid_generate_v4(),
    csv_file VARCHAR(500),
    total_drugs INTEGER DEFAULT 0,
    successful INTEGER DEFAULT 0,
    partial INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    status VARCHAR(50) DEFAULT 'in_progress',  -- 'in_progress', 'completed', 'failed'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_summary JSONB,  -- Summary of errors encountered
    processing_stats JSONB  -- Timing, API calls, etc.
);

CREATE INDEX IF NOT EXISTS idx_process_log_batch ON drug_process_log(batch_id);
CREATE INDEX IF NOT EXISTS idx_process_log_status ON drug_process_log(status);
CREATE INDEX IF NOT EXISTS idx_process_log_started ON drug_process_log(started_at);

COMMENT ON TABLE drug_process_log IS 'Tracks batch processing runs';

