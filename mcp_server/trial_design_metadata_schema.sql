-- ============================================================================
-- Trial Design Metadata Schema
-- ============================================================================
-- Stores trial-level design information and enrollment criteria
-- Extracted automatically during clinical data extraction
-- Stored in MCP database (alongside landscape_discovery_results, drugs, diseases)
--
-- Created: October 18, 2025
-- ============================================================================

-- Drop existing table if exists (for development)
-- DROP TABLE IF EXISTS trial_design_metadata CASCADE;

-- ============================================================================
-- Main Table: Trial Design Metadata
-- ============================================================================

CREATE TABLE IF NOT EXISTS trial_design_metadata (
    trial_design_id SERIAL PRIMARY KEY,
    nct_id VARCHAR(50) UNIQUE NOT NULL,
    indication VARCHAR(500) NOT NULL,

    -- Trial design summary
    study_design TEXT,  -- "Randomized, double-blind, placebo-controlled, Phase 3"
    trial_design_summary TEXT NOT NULL,  -- AI-generated narrative summary
    enrollment_summary TEXT NOT NULL,  -- Who was enrolled (patient types, characteristics)

    -- Detailed criteria (JSONB arrays for flexibility)
    inclusion_criteria JSONB,  -- ["Age ≥18 years", "EASI ≥16", "Inadequate response to topical therapy"]
    exclusion_criteria JSONB,  -- ["Prior biologic use within 8 weeks", "Active infection", ...]

    -- Key trial parameters
    primary_endpoint_description TEXT,
    secondary_endpoints_summary TEXT,
    sample_size_planned INTEGER,
    sample_size_enrolled INTEGER,
    duration_weeks INTEGER,

    -- Randomization details
    randomization_ratio VARCHAR(50),  -- "1:1:1", "2:1", etc.
    stratification_factors TEXT,  -- Description of stratification

    -- Blinding
    blinding VARCHAR(100),  -- "Double-blind", "Open-label", "Single-blind"

    -- Paper reference
    paper_pmid VARCHAR(50),
    paper_doi VARCHAR(100),
    paper_title TEXT,

    -- Metadata
    extraction_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    extraction_confidence NUMERIC(3,2) CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
    extraction_notes TEXT,

    -- Audit fields
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_trial_design UNIQUE(nct_id)
);

-- ============================================================================
-- Indexes
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_trial_design_indication ON trial_design_metadata(indication);
CREATE INDEX IF NOT EXISTS idx_trial_design_nct ON trial_design_metadata(nct_id);
CREATE INDEX IF NOT EXISTS idx_trial_design_timestamp ON trial_design_metadata(extraction_timestamp);

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function: Check if trial design already extracted
CREATE OR REPLACE FUNCTION trial_design_exists(p_nct_id VARCHAR)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM trial_design_metadata
        WHERE nct_id = p_nct_id
    );
END;
$$ LANGUAGE plpgsql;

-- Function: Get trial design statistics
CREATE OR REPLACE FUNCTION get_trial_design_stats()
RETURNS TABLE(
    total_trials BIGINT,
    unique_indications BIGINT,
    avg_sample_size NUMERIC,
    avg_duration_weeks NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*) AS total_trials,
        COUNT(DISTINCT indication) AS unique_indications,
        ROUND(AVG(sample_size_enrolled), 0) AS avg_sample_size,
        ROUND(AVG(duration_weeks), 1) AS avg_duration_weeks
    FROM trial_design_metadata
    WHERE sample_size_enrolled IS NOT NULL;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Update Trigger
-- ============================================================================

CREATE OR REPLACE FUNCTION update_trial_design_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trial_design_update_timestamp
    BEFORE UPDATE ON trial_design_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_trial_design_timestamp();

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE trial_design_metadata IS 'Trial design and enrollment metadata extracted from clinical trial publications';
COMMENT ON COLUMN trial_design_metadata.trial_design_summary IS 'AI-generated narrative summary of trial design';
COMMENT ON COLUMN trial_design_metadata.enrollment_summary IS 'Description of enrolled patient population and key characteristics';
COMMENT ON COLUMN trial_design_metadata.inclusion_criteria IS 'JSONB array of inclusion criteria strings';
COMMENT ON COLUMN trial_design_metadata.exclusion_criteria IS 'JSONB array of exclusion criteria strings';

-- ============================================================================
-- Sample Query Examples
-- ============================================================================

-- Get all trial designs for an indication
-- SELECT * FROM trial_design_metadata WHERE indication = 'Atopic Dermatitis';

-- Get trial designs with inclusion criteria
-- SELECT nct_id, trial_design_summary, inclusion_criteria
-- FROM trial_design_metadata
-- WHERE inclusion_criteria IS NOT NULL;

-- Get average sample sizes by indication
-- SELECT
--     indication,
--     COUNT(*) as trial_count,
--     AVG(sample_size_enrolled) as avg_sample_size
-- FROM trial_design_metadata
-- GROUP BY indication
-- ORDER BY trial_count DESC;
