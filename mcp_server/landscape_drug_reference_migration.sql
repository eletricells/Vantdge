-- Migration: Update Landscape Database to Reference Drug Database
--
-- Goal: Link landscape discovery results to drug database instead of
-- storing full drug data in JSONB.
--
-- Strategy: Add drug_ids array for drug references while keeping
-- drugs_found JSONB for backward compatibility during transition.

-- =============================================================================
-- STEP 1: Add drug_ids column to landscape_discovery_results
-- =============================================================================

-- Add column for array of drug IDs (references to drug database)
ALTER TABLE landscape_discovery_results
ADD COLUMN IF NOT EXISTS drug_ids INTEGER[];

COMMENT ON COLUMN landscape_discovery_results.drug_ids IS
'Array of drug_id references from the drug database. Replaces full drug data in drugs_found JSONB.';

-- Create index for drug_ids array queries
CREATE INDEX IF NOT EXISTS idx_landscape_results_drug_ids ON landscape_discovery_results USING GIN(drug_ids);


-- =============================================================================
-- STEP 2: Create junction table for many-to-many relationship
-- =============================================================================

-- Junction table: landscape_result_drugs
-- Links landscape discovery results to drugs with additional metadata
CREATE TABLE IF NOT EXISTS landscape_result_drugs (
    id SERIAL PRIMARY KEY,
    landscape_result_id INTEGER NOT NULL REFERENCES landscape_discovery_results(id) ON DELETE CASCADE,
    drug_id INTEGER NOT NULL,  -- Reference to drugs table in drug database (no FK - different DB)

    -- Additional drug-specific metadata for this landscape
    development_phase VARCHAR(50),  -- "Phase 2", "Phase 3", "Approved"
    trial_count INTEGER,  -- Number of trials found for this drug in this indication
    has_pivotal_data BOOLEAN DEFAULT FALSE,
    notes TEXT,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_landscape_drug UNIQUE(landscape_result_id, drug_id)
);

CREATE INDEX IF NOT EXISTS idx_landscape_drug_landscape ON landscape_result_drugs(landscape_result_id);
CREATE INDEX IF NOT EXISTS idx_landscape_drug_drug ON landscape_result_drugs(drug_id);

COMMENT ON TABLE landscape_result_drugs IS
'Junction table linking landscape discovery results to drugs in the drug database.';
COMMENT ON COLUMN landscape_result_drugs.drug_id IS
'References drugs.drug_id in the drug database (separate database, no FK constraint).';


-- =============================================================================
-- STEP 3: Create view for combined drug data
-- =============================================================================

-- View: vw_landscape_with_drug_references
-- Combines landscape results with drug IDs for easy querying
CREATE OR REPLACE VIEW vw_landscape_with_drug_references AS
SELECT
    ldr.id,
    ldr.indication,
    ldr.drugs_found_count,
    ldr.iterations_run,
    ldr.total_searches,
    ldr.drug_ids,
    ldr.drugs_found as legacy_drugs_found_jsonb,  -- Keep JSONB for backward compatibility
    ldr.standard_endpoints,
    ldr.search_date,
    -- Aggregate drug metadata from junction table
    ARRAY_AGG(lrd.drug_id) as all_drug_ids,
    ARRAY_AGG(lrd.development_phase) as drug_phases,
    ARRAY_AGG(lrd.trial_count) as drug_trial_counts
FROM landscape_discovery_results ldr
LEFT JOIN landscape_result_drugs lrd ON ldr.id = lrd.landscape_result_id
GROUP BY ldr.id;

COMMENT ON VIEW vw_landscape_with_drug_references IS
'Combined view of landscape results with drug references from both drug_ids array and junction table.';


-- =============================================================================
-- STEP 4: Helper functions for migration
-- =============================================================================

-- Function: sync_drug_ids_from_jsonb
-- Extracts drug names from drugs_found JSONB and looks up drug_ids
-- (Requires drug database to be accessible or manual mapping)
CREATE OR REPLACE FUNCTION sync_drug_ids_from_jsonb()
RETURNS TABLE(landscape_id INTEGER, drug_names TEXT[], missing_drugs TEXT[]) AS $$
BEGIN
    -- This function would extract drug names from drugs_found JSONB
    -- and attempt to look up corresponding drug_ids
    --
    -- Implementation depends on:
    -- 1. Structure of drugs_found JSONB
    -- 2. Access to drug database for lookup
    --
    -- For now, returns structure for manual mapping

    RETURN QUERY
    SELECT
        id as landscape_id,
        ARRAY(
            SELECT jsonb_array_elements(drugs_found)->>'drug_name'
            FROM landscape_discovery_results ldr
            WHERE ldr.id = landscape_discovery_results.id
        ) as drug_names,
        ARRAY[]::TEXT[] as missing_drugs
    FROM landscape_discovery_results
    WHERE drug_ids IS NULL OR array_length(drug_ids, 1) IS NULL;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION sync_drug_ids_from_jsonb IS
'Helper function to extract drug names from drugs_found JSONB for manual drug_id mapping.';


-- =============================================================================
-- STEP 5: Update triggers for maintaining drug_ids
-- =============================================================================

-- Trigger function: Update drug_ids array when junction table changes
CREATE OR REPLACE FUNCTION update_landscape_drug_ids()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE landscape_discovery_results
    SET drug_ids = (
        SELECT ARRAY_AGG(drug_id ORDER BY drug_id)
        FROM landscape_result_drugs
        WHERE landscape_result_id = NEW.landscape_result_id
    )
    WHERE id = NEW.landscape_result_id;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_landscape_drug_ids
AFTER INSERT OR UPDATE OR DELETE ON landscape_result_drugs
FOR EACH ROW
EXECUTE FUNCTION update_landscape_drug_ids();

COMMENT ON FUNCTION update_landscape_drug_ids IS
'Automatically updates drug_ids array in landscape_discovery_results when junction table changes.';


-- =============================================================================
-- STEP 6: Migration notes
-- =============================================================================

-- MIGRATION PLAN:
--
-- 1. Run this migration to add new columns and tables
--
-- 2. For each existing landscape result:
--    a. Extract drug names from drugs_found JSONB
--    b. Look up drug_id in drug database (or create if doesn't exist)
--    c. Insert into landscape_result_drugs junction table
--    d. drug_ids array will auto-update via trigger
--
-- 3. Update application code:
--    a. LandscapeWorkflow: Save drug_ids when creating landscape results
--    b. LandscapeDatabase: Update save_landscape_result() to populate junction table
--    c. Frontend: Query drug details from drug database using drug_ids
--
-- 4. After transition period:
--    a. Verify all landscape results have drug_ids populated
--    b. Optionally deprecate drugs_found JSONB column
--    c. Update queries to use drug_ids instead of JSONB


-- =============================================================================
-- ROLLBACK PLAN
-- =============================================================================

-- To rollback this migration:
-- DROP TRIGGER IF EXISTS trigger_update_landscape_drug_ids ON landscape_result_drugs;
-- DROP FUNCTION IF EXISTS update_landscape_drug_ids();
-- DROP FUNCTION IF EXISTS sync_drug_ids_from_jsonb();
-- DROP VIEW IF EXISTS vw_landscape_with_drug_references;
-- DROP TABLE IF EXISTS landscape_result_drugs;
-- ALTER TABLE landscape_discovery_results DROP COLUMN IF EXISTS drug_ids;
