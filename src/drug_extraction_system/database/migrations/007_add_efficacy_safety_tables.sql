-- Migration: 007_add_efficacy_safety_tables.sql
-- Description: Add tables for structured efficacy and safety data extraction
-- Created: 2025-12-29

-- ============================================================================
-- Table: drug_efficacy_data
-- Stores structured clinical trial efficacy results extracted from FDA labels
-- ============================================================================

CREATE TABLE IF NOT EXISTS drug_efficacy_data (
    efficacy_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    indication_id INTEGER REFERENCES drug_indications(indication_id) ON DELETE SET NULL,

    -- Trial identification
    trial_name TEXT,                            -- "Trial PsO1", "MEASURE 1", "VOYAGE 1"
    nct_id VARCHAR(20),                         -- NCT01365455
    trial_phase VARCHAR(50),                    -- "Phase 2", "Phase 3"

    -- Efficacy endpoint
    endpoint_name TEXT NOT NULL,                -- "PASI 75", "ACR20", "IGA 0/1"
    endpoint_type VARCHAR(50),                  -- "primary", "secondary", "exploratory"

    -- Drug arm results
    drug_arm_name TEXT,                         -- "COSENTYX 300 mg", "Secukinumab 150 mg"
    drug_arm_n INTEGER,                         -- Sample size (N=245)
    drug_arm_result DECIMAL,                    -- 81.6
    drug_arm_result_unit VARCHAR(20),           -- "%", "months", "score"

    -- Comparator arm results
    comparator_arm_name TEXT,                   -- "Placebo", "Adalimumab", "Etanercept"
    comparator_arm_n INTEGER,
    comparator_arm_result DECIMAL,

    -- Statistical measures
    p_value DECIMAL,                            -- 0.001
    confidence_interval TEXT,                   -- "95% CI: 75.2-88.0"

    -- Timepoint
    timepoint TEXT,                             -- "Week 12", "Week 52", "Month 6"

    -- Metadata
    population TEXT,                            -- "ITT", "per-protocol", "adults"
    indication_name TEXT,                       -- Denormalized for easy display
    raw_source_text TEXT,                       -- Original text for reference
    data_source VARCHAR(50) DEFAULT 'openfda',  -- "openfda", "web_search", "clinicaltrials"
    confidence_score FLOAT DEFAULT 0.85,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for drug_efficacy_data
CREATE INDEX IF NOT EXISTS idx_efficacy_drug_id ON drug_efficacy_data(drug_id);
CREATE INDEX IF NOT EXISTS idx_efficacy_indication_id ON drug_efficacy_data(indication_id);
CREATE INDEX IF NOT EXISTS idx_efficacy_endpoint ON drug_efficacy_data(endpoint_name);
CREATE INDEX IF NOT EXISTS idx_efficacy_trial ON drug_efficacy_data(trial_name);


-- ============================================================================
-- Table: drug_safety_data
-- Stores structured adverse event and safety data from FDA labels
-- ============================================================================

CREATE TABLE IF NOT EXISTS drug_safety_data (
    safety_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    indication_id INTEGER REFERENCES drug_indications(indication_id) ON DELETE SET NULL,

    -- Adverse event identification
    adverse_event TEXT NOT NULL,                -- "Nasopharyngitis", "Diarrhea", "Upper respiratory tract infection"
    system_organ_class TEXT,                    -- "Infections and infestations", "Gastrointestinal disorders"
    severity VARCHAR(50),                       -- "mild", "moderate", "severe", "life-threatening"
    is_serious BOOLEAN DEFAULT FALSE,

    -- Drug arm incidence
    drug_arm_name TEXT,                         -- "COSENTYX 300 mg"
    drug_arm_n INTEGER,                         -- Sample size (N=691)
    drug_arm_count INTEGER,                     -- Number of events (79)
    drug_arm_rate DECIMAL,                      -- 11.4
    drug_arm_rate_unit VARCHAR(20) DEFAULT '%',

    -- Comparator arm incidence
    comparator_arm_name TEXT,                   -- "Placebo"
    comparator_arm_n INTEGER,
    comparator_arm_count INTEGER,
    comparator_arm_rate DECIMAL,                -- 8.6

    -- Context
    timepoint TEXT,                             -- "Week 12", "1 year", "52 weeks"
    trial_context TEXT,                         -- "Pooled from PsO1, PsO2, PsO3, PsO4"

    -- Special warnings
    is_boxed_warning BOOLEAN DEFAULT FALSE,
    warning_category TEXT,                      -- "Infections", "Malignancy", "Cardiovascular"

    -- Metadata
    population TEXT,                            -- "adults", "pediatric", "elderly"
    indication_name TEXT,                       -- Denormalized for easy display
    raw_source_text TEXT,
    data_source VARCHAR(50) DEFAULT 'openfda',
    confidence_score FLOAT DEFAULT 0.85,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for drug_safety_data
CREATE INDEX IF NOT EXISTS idx_safety_drug_id ON drug_safety_data(drug_id);
CREATE INDEX IF NOT EXISTS idx_safety_indication_id ON drug_safety_data(indication_id);
CREATE INDEX IF NOT EXISTS idx_safety_adverse_event ON drug_safety_data(adverse_event);
CREATE INDEX IF NOT EXISTS idx_safety_soc ON drug_safety_data(system_organ_class);
CREATE INDEX IF NOT EXISTS idx_safety_serious ON drug_safety_data(is_serious) WHERE is_serious = TRUE;
CREATE INDEX IF NOT EXISTS idx_safety_boxed ON drug_safety_data(is_boxed_warning) WHERE is_boxed_warning = TRUE;


-- ============================================================================
-- Record migration
-- ============================================================================

INSERT INTO schema_migrations (migration_name)
VALUES ('007_add_efficacy_safety_tables')
ON CONFLICT (migration_name) DO NOTHING;
