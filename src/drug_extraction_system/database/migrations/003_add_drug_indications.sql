-- Migration: Add drug_indications table for structured indication data
-- Date: 2024-12-22

CREATE TABLE IF NOT EXISTS drug_indications (
    indication_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    disease_name TEXT NOT NULL,
    mesh_id TEXT,                          -- MeSH disease ID for standardization
    icd10_code TEXT,                       -- ICD-10 code if available
    population TEXT DEFAULT '',            -- adults, pediatric, specific age ranges
    severity TEXT,                         -- mild, moderate, severe
    line_of_therapy TEXT,                  -- first-line, second-line, adjunct
    combination_therapy TEXT,              -- monotherapy, combination with X
    approval_status TEXT DEFAULT 'approved', -- approved, investigational
    approval_date DATE,
    regulatory_region TEXT DEFAULT 'US',
    special_conditions TEXT,               -- e.g., "after failure of DMARDs"
    raw_source_text TEXT,                  -- Original text for reference
    confidence_score FLOAT,                -- Parser confidence (0.0-1.0)
    data_source TEXT,                      -- openfda, clinicaltrials, manual
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create unique index using COALESCE for population
CREATE UNIQUE INDEX IF NOT EXISTS idx_indications_unique
    ON drug_indications(drug_id, disease_name, COALESCE(population, ''), regulatory_region);

CREATE INDEX IF NOT EXISTS idx_indications_drug_id ON drug_indications(drug_id);
CREATE INDEX IF NOT EXISTS idx_indications_mesh_id ON drug_indications(mesh_id);
CREATE INDEX IF NOT EXISTS idx_indications_disease_name ON drug_indications(disease_name);

COMMENT ON TABLE drug_indications IS 'Structured indication data parsed from FDA labels';

