-- Migration: Add drug_dosing_regimens table for structured dosing data
-- Date: 2024-12-22

CREATE TABLE IF NOT EXISTS drug_dosing_regimens (
    regimen_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    indication_id INTEGER REFERENCES drug_indications(indication_id),
    indication_name TEXT,                  -- Fallback if no indication_id
    dose_amount DECIMAL,
    dose_unit TEXT,                        -- mg, mcg, mL, etc.
    dose_range_min DECIMAL,                -- For ranges like "15-30 mg"
    dose_range_max DECIMAL,
    frequency TEXT,                        -- once daily, twice daily, etc.
    route TEXT,                            -- oral, IV, subcutaneous, etc.
    duration TEXT,                         -- 2 weeks, ongoing, etc.
    max_daily_dose DECIMAL,
    max_daily_dose_unit TEXT,
    population TEXT,                       -- adults, pediatric, renal impairment
    titration_schedule TEXT,               -- e.g., "Start 15mg, increase to 30mg after 4 weeks"
    special_instructions TEXT,             -- with food, avoid grapefruit, etc.
    formulation TEXT,                      -- tablet, capsule, injection, etc.
    raw_source_text TEXT,
    confidence_score FLOAT,
    data_source TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dosing_drug_id ON drug_dosing_regimens(drug_id);
CREATE INDEX IF NOT EXISTS idx_dosing_indication_id ON drug_dosing_regimens(indication_id);

COMMENT ON TABLE drug_dosing_regimens IS 'Structured dosing regimen data parsed from FDA labels';

