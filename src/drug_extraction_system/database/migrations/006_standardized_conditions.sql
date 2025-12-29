-- Migration: Add standardized conditions system
-- Date: 2024-12-27
-- Purpose: Normalize disease/condition names from clinical trials

-- =============================================================================
-- STANDARDIZED CONDITIONS TABLE (Master list of normalized condition names)
-- =============================================================================
CREATE TABLE IF NOT EXISTS standardized_conditions (
    condition_id SERIAL PRIMARY KEY,
    standard_name VARCHAR(255) NOT NULL UNIQUE,  -- e.g., "Plaque Psoriasis"
    mesh_id VARCHAR(20),                          -- MeSH descriptor ID (e.g., D011565)
    mesh_term VARCHAR(255),                       -- MeSH preferred term
    icd10_codes TEXT[],                           -- Array of ICD-10 codes
    therapeutic_area VARCHAR(100),                -- e.g., "Dermatology", "Rheumatology"
    parent_condition_id INTEGER REFERENCES standardized_conditions(condition_id),
    aliases TEXT[],                               -- Alternative names
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_std_conditions_name ON standardized_conditions(standard_name);
CREATE INDEX IF NOT EXISTS idx_std_conditions_mesh ON standardized_conditions(mesh_id);
CREATE INDEX IF NOT EXISTS idx_std_conditions_area ON standardized_conditions(therapeutic_area);

COMMENT ON TABLE standardized_conditions IS 'Master list of standardized disease/condition names';

-- =============================================================================
-- CONDITION MAPPINGS TABLE (Maps raw names to standardized names)
-- =============================================================================
CREATE TABLE IF NOT EXISTS condition_mappings (
    mapping_id SERIAL PRIMARY KEY,
    raw_name VARCHAR(500) NOT NULL,               -- Original name from trial
    condition_id INTEGER REFERENCES standardized_conditions(condition_id) ON DELETE CASCADE,
    match_type VARCHAR(50) DEFAULT 'exact',       -- exact, fuzzy, manual, mesh_lookup
    confidence DECIMAL(3,2) DEFAULT 1.0,          -- 0.0-1.0 confidence score
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(raw_name)
);

CREATE INDEX IF NOT EXISTS idx_condition_mappings_raw ON condition_mappings(raw_name);
CREATE INDEX IF NOT EXISTS idx_condition_mappings_condition ON condition_mappings(condition_id);

COMMENT ON TABLE condition_mappings IS 'Maps raw condition names to standardized conditions';

-- =============================================================================
-- TRIAL CONDITIONS TABLE (Links trials to standardized conditions)
-- =============================================================================
CREATE TABLE IF NOT EXISTS trial_conditions (
    id SERIAL PRIMARY KEY,
    trial_id INTEGER REFERENCES drug_clinical_trials(trial_id) ON DELETE CASCADE,
    condition_id INTEGER REFERENCES standardized_conditions(condition_id) ON DELETE CASCADE,
    is_primary BOOLEAN DEFAULT TRUE,              -- Primary vs secondary condition
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(trial_id, condition_id)
);

CREATE INDEX IF NOT EXISTS idx_trial_conditions_trial ON trial_conditions(trial_id);
CREATE INDEX IF NOT EXISTS idx_trial_conditions_condition ON trial_conditions(condition_id);

COMMENT ON TABLE trial_conditions IS 'Links clinical trials to standardized conditions';

-- =============================================================================
-- VIEW: Trial count by standardized condition
-- =============================================================================
CREATE OR REPLACE VIEW trial_counts_by_condition AS
SELECT 
    sc.condition_id,
    sc.standard_name,
    sc.therapeutic_area,
    COUNT(DISTINCT tc.trial_id) as trial_count,
    COUNT(DISTINCT dct.drug_id) as drug_count
FROM standardized_conditions sc
LEFT JOIN trial_conditions tc ON sc.condition_id = tc.condition_id
LEFT JOIN drug_clinical_trials dct ON tc.trial_id = dct.trial_id
GROUP BY sc.condition_id, sc.standard_name, sc.therapeutic_area
ORDER BY trial_count DESC;

-- =============================================================================
-- VIEW: Trials with standardized conditions
-- =============================================================================
CREATE OR REPLACE VIEW trials_with_conditions AS
SELECT 
    dct.trial_id,
    dct.nct_id,
    dct.trial_title,
    dct.trial_phase,
    dct.trial_status,
    d.generic_name as drug_name,
    d.brand_name,
    ARRAY_AGG(DISTINCT sc.standard_name) as conditions
FROM drug_clinical_trials dct
JOIN drugs d ON dct.drug_id = d.drug_id
LEFT JOIN trial_conditions tc ON dct.trial_id = tc.trial_id
LEFT JOIN standardized_conditions sc ON tc.condition_id = sc.condition_id
GROUP BY dct.trial_id, dct.nct_id, dct.trial_title, dct.trial_phase, 
         dct.trial_status, d.generic_name, d.brand_name;

