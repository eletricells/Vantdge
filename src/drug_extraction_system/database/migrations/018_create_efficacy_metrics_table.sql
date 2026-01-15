-- Migration 018: Create cs_efficacy_metrics table for structured efficacy data
-- This normalizes the detailed_efficacy_endpoints from full_extraction JSONB
-- Supports multiple metric types: response rates, hazard ratios, biomarker changes, etc.

CREATE TABLE IF NOT EXISTS cs_efficacy_metrics (
    metric_id SERIAL PRIMARY KEY,
    extraction_id INTEGER REFERENCES cs_extractions(id) ON DELETE CASCADE,

    -- Metric classification
    metric_category VARCHAR(50) NOT NULL,  -- response, ratio, reduction, score, biomarker, survival, time, retention
    metric_name VARCHAR(300),              -- specific endpoint name (e.g., EASI-75, Ferritin, Mortality HR)
    endpoint_category VARCHAR(50),         -- Primary, Secondary, Exploratory
    organ_domain VARCHAR(100),             -- Musculoskeletal, Renal, etc.

    -- Response rate metrics
    responders_n INTEGER,
    responders_pct NUMERIC(6,2),
    total_n INTEGER,

    -- Comparative metrics (HR, OR, RR)
    ratio_value NUMERIC(10,4),             -- HR=0.68, OR=0.36
    ratio_type VARCHAR(20),                -- HR, OR, RR
    ci_lower NUMERIC(10,4),
    ci_upper NUMERIC(10,4),
    comparator VARCHAR(300),               -- placebo, standard care, other drug

    -- Change metrics (baseline -> final)
    baseline_value NUMERIC(15,4),
    final_value NUMERIC(15,4),
    change_absolute NUMERIC(15,4),
    change_pct NUMERIC(8,2),
    unit VARCHAR(100),

    -- Statistical context
    p_value VARCHAR(30),
    is_statistically_significant BOOLEAN,

    -- Timepoint
    timepoint VARCHAR(100),                -- Week 12, Month 6, Day 28

    -- Quality indicators
    is_primary_endpoint BOOLEAN DEFAULT FALSE,
    is_biomarker BOOLEAN DEFAULT FALSE,
    is_validated_instrument BOOLEAN,
    instrument_quality_tier INTEGER,       -- 1=gold standard, 2=validated PRO, 3=investigator-assessed

    -- Metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_cs_efficacy_extraction ON cs_efficacy_metrics(extraction_id);
CREATE INDEX IF NOT EXISTS idx_cs_efficacy_category ON cs_efficacy_metrics(metric_category);
CREATE INDEX IF NOT EXISTS idx_cs_efficacy_biomarker ON cs_efficacy_metrics(is_biomarker) WHERE is_biomarker = true;
CREATE INDEX IF NOT EXISTS idx_cs_efficacy_primary ON cs_efficacy_metrics(is_primary_endpoint) WHERE is_primary_endpoint = true;

-- View for drug-level efficacy summary
CREATE OR REPLACE VIEW v_cs_drug_efficacy_summary AS
SELECT
    e.drug_name,
    e.disease,
    m.metric_category,
    COUNT(*) as metric_count,

    -- Response metrics
    AVG(m.responders_pct) FILTER (WHERE m.metric_category = 'response') as avg_response_pct,
    MAX(m.responders_pct) FILTER (WHERE m.metric_category = 'response') as max_response_pct,

    -- Ratio metrics (HR/OR)
    AVG(m.ratio_value) FILTER (WHERE m.metric_category = 'ratio') as avg_ratio,
    MIN(m.ratio_value) FILTER (WHERE m.metric_category = 'ratio') as best_ratio,

    -- Biomarker change
    AVG(m.change_pct) FILTER (WHERE m.is_biomarker = true) as avg_biomarker_change_pct,

    -- Count of statistically significant findings
    COUNT(*) FILTER (WHERE m.is_statistically_significant = true) as significant_findings

FROM cs_extractions e
JOIN cs_efficacy_metrics m ON e.id = m.extraction_id
WHERE e.is_relevant = true
GROUP BY e.drug_name, e.disease, m.metric_category;

COMMENT ON TABLE cs_efficacy_metrics IS 'Normalized efficacy metrics extracted from case series papers. Supports multiple metric types: response rates, hazard ratios, biomarker changes, score improvements, etc.';

COMMENT ON VIEW v_cs_drug_efficacy_summary IS 'Aggregated efficacy metrics by drug and disease for comparison views.';
