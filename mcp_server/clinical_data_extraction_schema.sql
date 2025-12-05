-- =====================================================
-- CLINICAL TRIAL DATA EXTRACTION SCHEMA
-- =====================================================
-- Purpose: Store structured clinical trial data extracted from papers
-- Author: Clinical Data Extractor Agent
-- Date: October 2025
-- =====================================================

-- =====================================================
-- MAIN TRIAL EXTRACTION RECORD
-- =====================================================
-- One row per trial arm (e.g., NCT123 Placebo, NCT123 Drug 300mg)
CREATE TABLE IF NOT EXISTS clinical_trial_extractions (
    extraction_id SERIAL PRIMARY KEY,

    -- Trial identification
    nct_id VARCHAR(50),
    trial_name VARCHAR(255),  -- "SOLO 1", "ARCADIA 1", "DUPIXENT SOLO 1"
    drug_name VARCHAR(255),
    generic_name VARCHAR(255),
    indication VARCHAR(500),

    -- Arm details
    arm_name VARCHAR(255),  -- "Active Treatment", "Placebo", "Arm 1"
    dosing_regimen VARCHAR(255),  -- "300 mg Q2W", "PBO", "dupilumab 300 mg Q2W"
    n INTEGER,  -- Sample size for this specific arm

    -- Trial metadata
    phase VARCHAR(20),  -- "Phase 1", "Phase 2", "Phase 3", "Phase 4"
    background_therapy VARCHAR(255),  -- "TCS-TCI", "PBO", "Standard of Care", "Background therapy allowed"

    -- Data source
    paper_pmid VARCHAR(50),
    paper_doi VARCHAR(100),
    paper_title TEXT,  -- Paper title for display
    paper_path TEXT,  -- File path to source paper
    data_source_type VARCHAR(50),  -- "PMC", "User Upload", "Manual Entry"

    -- Extraction metadata
    extracted_by VARCHAR(100) DEFAULT 'Claude Sonnet 4.5',
    extraction_timestamp TIMESTAMP DEFAULT NOW(),
    extraction_confidence NUMERIC,  -- 0-1, AI confidence in extraction quality
    extraction_notes TEXT,

    -- Prevent duplicate extractions
    UNIQUE(nct_id, arm_name, dosing_regimen)
);

-- =====================================================
-- BASELINE CHARACTERISTICS
-- =====================================================
-- Demographics, disease history, prior medications
CREATE TABLE IF NOT EXISTS trial_baseline_characteristics (
    baseline_id SERIAL PRIMARY KEY,
    extraction_id INTEGER REFERENCES clinical_trial_extractions(extraction_id) ON DELETE CASCADE,

    -- ============= STANDARD DEMOGRAPHICS =============
    -- Always collected regardless of disease

    -- Sample size
    n INTEGER,

    -- Age
    median_age NUMERIC,
    mean_age NUMERIC,
    age_range_min NUMERIC,
    age_range_max NUMERIC,
    age_sd NUMERIC,  -- Standard deviation
    age_range VARCHAR(50),  -- Age range as text (e.g., '18-75')

    -- Sex
    male_n INTEGER,
    male_pct NUMERIC,
    female_n INTEGER,
    female_pct NUMERIC,

    -- Race/Ethnicity (US FDA categories + expanded)
    race_white_n INTEGER,
    race_white_pct NUMERIC,
    race_black_african_american_n INTEGER,
    race_black_african_american_pct NUMERIC,
    race_asian_n INTEGER,
    race_asian_pct NUMERIC,
    race_hispanic_latino_n INTEGER,
    race_hispanic_latino_pct NUMERIC,
    race_native_american_n INTEGER,
    race_native_american_pct NUMERIC,
    race_pacific_islander_n INTEGER,
    race_pacific_islander_pct NUMERIC,
    race_mixed_n INTEGER,
    race_mixed_pct NUMERIC,
    race_other_n INTEGER,
    race_other_pct NUMERIC,
    race_unknown_n INTEGER,
    race_unknown_pct NUMERIC,

    -- Additional race/ethnicity detail (JSONB for flexibility)
    -- Examples: {"race_breakdown_detail": "55% White non-Hispanic, 12% Hispanic White"}
    race_additional_detail JSONB,

    -- ============= DISEASE HISTORY =============

    -- Disease duration
    median_disease_duration NUMERIC,
    mean_disease_duration NUMERIC,
    disease_duration_unit VARCHAR(20) DEFAULT 'years',  -- "years", "months", "days"
    disease_duration_range_min NUMERIC,
    disease_duration_range_max NUMERIC,

    -- ============= PRIOR MEDICATION USE =============
    -- Critical for understanding patient population

    -- Prior systemic medications
    prior_steroid_use_n INTEGER,
    prior_steroid_use_pct NUMERIC,
    prior_biologic_use_n INTEGER,
    prior_biologic_use_pct NUMERIC,
    prior_tnf_inhibitor_use_n INTEGER,
    prior_tnf_inhibitor_use_pct NUMERIC,
    prior_immunosuppressant_use_n INTEGER,
    prior_immunosuppressant_use_pct NUMERIC,

    -- Prior topical therapy
    prior_topical_therapy_n INTEGER,
    prior_topical_therapy_pct NUMERIC,

    -- Treatment status
    treatment_naive_n INTEGER,
    treatment_naive_pct NUMERIC,

    -- Number of prior therapies
    prior_lines_median NUMERIC,
    prior_lines_mean NUMERIC,

    -- Detailed prior medication history (JSONB for flexibility)
    -- Examples:
    -- Atopic Dermatitis: {"prior_dupilumab_pct": 15, "prior_topical_corticosteroids_pct": 85}
    -- Rheumatoid Arthritis: {"prior_methotrexate_pct": 90, "prior_dmard_pct": 95}
    -- Psoriasis: {"prior_phototherapy_pct": 40, "prior_methotrexate_pct": 30}
    prior_medications_detail JSONB,

    -- ============= DISEASE-SPECIFIC BIOMARKERS =============
    -- JSONB for maximum flexibility across diseases
    -- Examples:
    -- Atopic Dermatitis: {"median_affected_bsa": 57, "mean_bsa_affected": 45}
    -- Myasthenia Gravis: {"achr_positive_pct": 85, "musk_positive_pct": 10}
    -- Graves Disease: {"median_trab_level": 15.2, "tpo_antibody_positive_pct": 70}
    -- Rheumatoid Arthritis: {"rf_positive_pct": 75, "anti_ccp_positive_pct": 70}
    disease_specific_baseline JSONB,

    -- ============= BASELINE SEVERITY SCORES =============
    -- JSONB for disease-specific validated scales
    -- Examples:
    -- Atopic Dermatitis: {"median_easi_score": 31.8, "mean_easi_score": 30.4, "iga_score_3_pct": 51}
    -- Psoriasis: {"median_pasi_score": 18.5, "mean_pasi_score": 19.2}
    -- Rheumatoid Arthritis: {"median_das28_score": 6.5}
    -- Graves Disease: {"median_cas_score": 4.5}
    baseline_severity_scores JSONB,

    -- Additional notes
    notes TEXT,

    -- Source reference
    source_table VARCHAR(100),  -- Table/Figure where baseline data was found (e.g., 'Table 1')

    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================================================
-- BASELINE CHARACTERISTICS DETAIL
-- =====================================================
-- Multiple rows per trial arm (one per characteristic)
-- Stores individual demographic characteristics dynamically
CREATE TABLE IF NOT EXISTS trial_baseline_characteristics_detail (
    characteristic_id SERIAL PRIMARY KEY,
    extraction_id INTEGER REFERENCES clinical_trial_extractions(extraction_id) ON DELETE CASCADE,

    -- Characteristic identification
    characteristic_name VARCHAR(500),  -- "Age", "Weight", "Serum C3", "Systolic Blood Pressure", etc.
    characteristic_category VARCHAR(100),  -- "Demographics", "Disease Biomarkers", "Severity Scores", "Lab Values"
    characteristic_description TEXT,  -- Full description if available

    -- Cohort/Subgroup
    cohort VARCHAR(255),  -- "C3G", "Overall study population", "Treatment arm", etc.

    -- Values (flexible to handle different data types)
    value_numeric NUMERIC,  -- For numeric values (age, weight, etc.)
    value_text VARCHAR(500),  -- For categorical values (race, gender, etc.)
    unit VARCHAR(100),  -- "years", "kg", "mg/dl", "%", etc.

    -- Statistical measures
    n_patients INTEGER,  -- Number of patients with this characteristic
    percentage NUMERIC,  -- Percentage (for categorical characteristics)
    mean_value NUMERIC,  -- Mean (for continuous characteristics)
    median_value NUMERIC,  -- Median (for continuous characteristics)
    sd_value NUMERIC,  -- Standard deviation
    range_min NUMERIC,  -- Minimum value in range
    range_max NUMERIC,  -- Maximum value in range

    -- Source reference
    source_table VARCHAR(100),  -- Table/Figure where data was found (e.g., 'Table 1')

    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_baseline_detail_extraction ON trial_baseline_characteristics_detail(extraction_id);
CREATE INDEX IF NOT EXISTS idx_baseline_detail_characteristic ON trial_baseline_characteristics_detail(characteristic_name);
CREATE INDEX IF NOT EXISTS idx_baseline_detail_category ON trial_baseline_characteristics_detail(characteristic_category);

-- =====================================================
-- EFFICACY ENDPOINTS
-- =====================================================
-- Multiple rows per trial arm (one per endpoint per timepoint)
CREATE TABLE IF NOT EXISTS trial_efficacy_endpoints (
    endpoint_id SERIAL PRIMARY KEY,
    extraction_id INTEGER REFERENCES clinical_trial_extractions(extraction_id) ON DELETE CASCADE,

    -- Endpoint identification
    endpoint_category VARCHAR(100),  -- "Primary", "Secondary", "Exploratory", "Post-hoc"
    endpoint_name VARCHAR(500),  -- "IGA Score of 0 or 1", "EASI-75", "≥4 points improvement from BL in EASI"
    endpoint_unit VARCHAR(100),  -- Unit of measurement (e.g., "mg/mg", "ml/min per 1.73 m²", "%")
    endpoint_description TEXT,  -- Full endpoint definition if available
    is_standard_endpoint BOOLEAN DEFAULT FALSE,  -- True if from landscape discovery

    -- Timepoint
    timepoint VARCHAR(50),  -- "Week 16", "Week 2", "Month 6", "Day 15"
    timepoint_weeks INTEGER,  -- Normalized to weeks for sorting (Week 16 = 16, Month 6 = 24)

    -- Analysis type
    analysis_type VARCHAR(50),  -- "ITT", "PP", "Safety", "Per-protocol", "Intent-to-treat", etc.

    -- Binary/Categorical outcomes (e.g., % achieving IGA 0/1)
    n_evaluated INTEGER,  -- Number of patients evaluated at this timepoint
    responders_n INTEGER,  -- Number who achieved endpoint
    responders_pct NUMERIC,  -- Percentage

    -- Continuous outcomes (e.g., change from baseline in EASI score)
    mean_value NUMERIC,
    median_value NUMERIC,
    sd_value NUMERIC,  -- Standard deviation
    change_from_baseline_mean NUMERIC,
    change_from_baseline_median NUMERIC,
    change_from_baseline_sd NUMERIC,
    pct_change_from_baseline NUMERIC,  -- Percent change
    value_unit VARCHAR(50),  -- Unit for value (e.g., 'mg/dL', 'mmHg', 'units/ml')

    -- Statistical significance
    stat_sig BOOLEAN,  -- True if statistically significant
    p_value VARCHAR(50),  -- "p<0.001", "p=0.023", "NS"
    confidence_interval VARCHAR(100),  -- "95% CI: 1.8-2.9"

    -- Comparator arm (if available)
    comparator_arm VARCHAR(255),  -- "Placebo", "Active Comparator"

    -- Raw/complex data (JSONB for unusual endpoint formats)
    -- Example: {"score_distribution": {"0": 10%, "1": 20%, "2": 45%, "3": 25%}}
    raw_data JSONB,

    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================================================
-- SAFETY ENDPOINTS
-- =====================================================
-- Adverse events, discontinuations, deaths
CREATE TABLE IF NOT EXISTS trial_safety_endpoints (
    safety_id SERIAL PRIMARY KEY,
    extraction_id INTEGER REFERENCES clinical_trial_extractions(extraction_id) ON DELETE CASCADE,

    -- Safety categorization
    event_category VARCHAR(100),  -- "Adverse Events", "Serious AEs", "Discontinuations", "Deaths", "Lab Abnormalities"
    event_name VARCHAR(500),  -- "Any TEAE", "Infections", "Injection site reactions", "Hypersensitivity"
    event_description TEXT,

    -- Cohort/Subgroup
    cohort VARCHAR(255),  -- "C3G", "Overall study population", "Placebo", "Treatment arm"

    -- Timepoint (usually overall study period, but can be specific)
    timepoint VARCHAR(50) DEFAULT 'Overall',  -- "Overall", "Week 0-16", "Treatment period"

    -- Event counts
    n_evaluated INTEGER,  -- Patients in safety population
    events_n INTEGER,  -- Number of patients with at least one event
    events_pct NUMERIC,  -- Percentage
    total_events_count INTEGER,  -- Total number of events (may be > n if multiple events per patient)

    -- Severity classification
    severity VARCHAR(50),  -- "Mild", "Moderate", "Severe", "Grade 1", "Grade 2", "Grade 3", "Grade 4"

    -- Causality assessment
    causality VARCHAR(50),  -- "Related", "Unrelated", "Possibly related", "Probably related"

    -- Outcome
    outcome VARCHAR(100),  -- "Resolved", "Ongoing", "Fatal", "Resolved with sequelae"

    -- Actions taken
    led_to_discontinuation BOOLEAN,
    required_intervention BOOLEAN,

    -- Additional detail
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- =====================================================
-- STANDARD CLINICAL ENDPOINTS LIBRARY
-- =====================================================
-- Pre-populated from landscape discovery results
-- Used to prioritize extraction of standard endpoints
CREATE TABLE IF NOT EXISTS standard_clinical_endpoints (
    endpoint_lib_id SERIAL PRIMARY KEY,
    indication VARCHAR(500),
    endpoint_name VARCHAR(500),
    endpoint_type VARCHAR(50),  -- "efficacy", "safety", "biomarker", "quality_of_life"
    description TEXT,
    common_timepoints VARCHAR(255)[],  -- ["Week 12", "Week 16", "Week 52"]
    source VARCHAR(100) DEFAULT 'Landscape Discovery',  -- "Landscape Discovery", "Manual", "FDA Guidance"
    added_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(indication, endpoint_name)
);

-- Pre-populate from landscape discovery (run after schema creation)
-- INSERT INTO standard_clinical_endpoints (indication, endpoint_name, endpoint_type)
-- SELECT
--     indication,
--     jsonb_array_elements_text(standard_endpoints) as endpoint_name,
--     'efficacy' as endpoint_type
-- FROM landscape_discovery_results
-- WHERE standard_endpoints IS NOT NULL;

-- =====================================================
-- INDEXES FOR PERFORMANCE
-- =====================================================

-- Extraction lookups
CREATE INDEX IF NOT EXISTS idx_extractions_indication ON clinical_trial_extractions(indication);
CREATE INDEX IF NOT EXISTS idx_extractions_nct ON clinical_trial_extractions(nct_id);
CREATE INDEX IF NOT EXISTS idx_extractions_drug ON clinical_trial_extractions(drug_name);
CREATE INDEX IF NOT EXISTS idx_extractions_generic ON clinical_trial_extractions(generic_name);
CREATE INDEX IF NOT EXISTS idx_extractions_phase ON clinical_trial_extractions(phase);

-- Baseline lookups
CREATE INDEX IF NOT EXISTS idx_baseline_extraction ON trial_baseline_characteristics(extraction_id);

-- Efficacy lookups
CREATE INDEX IF NOT EXISTS idx_efficacy_extraction ON trial_efficacy_endpoints(extraction_id);
CREATE INDEX IF NOT EXISTS idx_efficacy_endpoint ON trial_efficacy_endpoints(endpoint_name);
CREATE INDEX IF NOT EXISTS idx_efficacy_timepoint ON trial_efficacy_endpoints(timepoint_weeks);
CREATE INDEX IF NOT EXISTS idx_efficacy_category ON trial_efficacy_endpoints(endpoint_category);

-- Safety lookups
CREATE INDEX IF NOT EXISTS idx_safety_extraction ON trial_safety_endpoints(extraction_id);
CREATE INDEX IF NOT EXISTS idx_safety_category ON trial_safety_endpoints(safety_category);

-- Standard endpoints
CREATE INDEX IF NOT EXISTS idx_standard_endpoints_indication ON standard_clinical_endpoints(indication);

-- =====================================================
-- EXTRACTION QUALITY TRACKING
-- =====================================================
-- Stores validation issues, warnings, and data quality notes
-- Associated with specific extractions but separate from actual data
CREATE TABLE IF NOT EXISTS extraction_quality_issues (
    issue_id SERIAL PRIMARY KEY,
    extraction_id INTEGER REFERENCES clinical_trial_extractions(extraction_id) ON DELETE CASCADE,

    -- Issue classification
    issue_type VARCHAR(50),  -- "error", "warning", "info"
    category VARCHAR(100),  -- "data_completeness", "clinical_plausibility", "statistical_inconsistency", "missing_field", "data_quality"

    -- Issue details
    title VARCHAR(255),  -- Short title of the issue
    description TEXT,  -- Detailed description
    severity VARCHAR(20),  -- "critical", "high", "medium", "low"

    -- Context
    affected_section VARCHAR(100),  -- "baseline", "efficacy", "safety", "metadata"
    affected_field VARCHAR(100),  -- Specific field if applicable
    affected_endpoint_id INTEGER REFERENCES trial_efficacy_endpoints(endpoint_id) ON DELETE SET NULL,  -- If related to specific endpoint
    affected_safety_id INTEGER REFERENCES trial_safety_endpoints(safety_id) ON DELETE SET NULL,  -- If related to specific safety event

    -- Suggested action
    suggested_action TEXT,  -- What user should do about this issue

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE,
    resolution_notes TEXT
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_quality_extraction ON extraction_quality_issues(extraction_id);
CREATE INDEX IF NOT EXISTS idx_quality_type ON extraction_quality_issues(issue_type);
CREATE INDEX IF NOT EXISTS idx_quality_category ON extraction_quality_issues(category);
CREATE INDEX IF NOT EXISTS idx_quality_severity ON extraction_quality_issues(severity);

-- =====================================================
-- VIEWS FOR EASY QUERYING
-- =====================================================

-- Complete trial data (denormalized for comparative tables)
CREATE OR REPLACE VIEW vw_complete_trial_data AS
SELECT
    -- Trial identification
    cte.extraction_id,
    cte.nct_id,
    cte.trial_name,
    cte.drug_name,
    cte.generic_name,
    cte.indication,
    cte.arm_name,
    cte.dosing_regimen,
    cte.n as arm_n,
    cte.phase,
    cte.background_therapy,
    cte.paper_pmid,
    cte.extraction_timestamp,

    -- Baseline demographics (selected key fields)
    tbc.median_age,
    tbc.mean_age,
    tbc.male_pct,
    tbc.female_pct,
    tbc.race_white_pct,
    tbc.race_black_african_american_pct,
    tbc.race_asian_pct,
    tbc.race_hispanic_latino_pct,
    tbc.median_disease_duration,
    tbc.prior_biologic_use_pct,
    tbc.prior_tnf_inhibitor_use_pct,
    tbc.treatment_naive_pct,
    tbc.disease_specific_baseline,
    tbc.baseline_severity_scores,
    tbc.prior_medications_detail,

    -- Aggregated efficacy (primary endpoints at primary timepoint)
    (SELECT json_agg(json_build_object(
        'endpoint_name', endpoint_name,
        'timepoint', timepoint,
        'responders_pct', responders_pct,
        'stat_sig', stat_sig,
        'p_value', p_value
    ))
    FROM trial_efficacy_endpoints
    WHERE extraction_id = cte.extraction_id
      AND endpoint_category = 'Primary'
    ) as primary_efficacy,

    -- Aggregated safety
    (SELECT json_agg(json_build_object(
        'safety_measure', safety_measure,
        'events_pct', events_pct,
        'severity', severity
    ))
    FROM trial_safety_endpoints
    WHERE extraction_id = cte.extraction_id
      AND safety_category IN ('Adverse Events', 'Serious AEs')
    ) as safety_summary

FROM clinical_trial_extractions cte
LEFT JOIN trial_baseline_characteristics tbc ON cte.extraction_id = tbc.extraction_id;

-- Efficacy comparison view (all endpoints across trials)
CREATE OR REPLACE VIEW vw_efficacy_comparison AS
SELECT
    cte.drug_name,
    cte.generic_name,
    cte.trial_name,
    cte.nct_id,
    cte.arm_name,
    cte.dosing_regimen,
    cte.n as arm_n,
    cte.indication,
    tee.endpoint_name,
    tee.endpoint_unit,
    tee.endpoint_category,
    tee.timepoint,
    tee.timepoint_weeks,
    tee.analysis_type,
    tee.responders_n,
    tee.responders_pct,
    tee.mean_value,
    tee.change_from_baseline_mean,
    tee.pct_change_from_baseline,
    tee.stat_sig,
    tee.p_value,
    tee.is_standard_endpoint,
    tee.source_table  -- Added to show which endpoints came from figures vs tables
FROM clinical_trial_extractions cte
JOIN trial_efficacy_endpoints tee ON cte.extraction_id = tee.extraction_id
ORDER BY cte.drug_name, tee.endpoint_name, tee.timepoint_weeks;

-- Safety comparison view
CREATE OR REPLACE VIEW vw_safety_comparison AS
SELECT
    cte.drug_name,
    cte.generic_name,
    cte.trial_name,
    cte.nct_id,
    cte.arm_name,
    cte.dosing_regimen,
    cte.n as arm_n,
    cte.indication,
    tse.event_category,
    tse.event_name,
    tse.n_patients as events_n,
    tse.incidence_pct as events_pct,
    tse.severity,
    tse.led_to_discontinuation
FROM clinical_trial_extractions cte
JOIN trial_safety_endpoints tse ON cte.extraction_id = tse.extraction_id
ORDER BY cte.drug_name, tse.event_category, tse.event_name;

-- Baseline characteristics comparison view
CREATE OR REPLACE VIEW vw_baseline_comparison AS
SELECT
    cte.drug_name,
    cte.generic_name,
    cte.trial_name,
    cte.nct_id,
    cte.arm_name,
    cte.n as arm_n,
    cte.indication,
    tbcd.characteristic_name,
    tbcd.characteristic_category,
    tbcd.mean_value,
    tbcd.median_value,
    tbcd.sd_value,
    tbcd.range_min,
    tbcd.range_max,
    tbcd.n_patients,
    tbcd.percentage,
    tbcd.unit,
    tbcd.cohort,
    tbcd.source_table
FROM clinical_trial_extractions cte
JOIN trial_baseline_characteristics_detail tbcd ON cte.extraction_id = tbcd.extraction_id
ORDER BY cte.drug_name, tbcd.characteristic_category, tbcd.characteristic_name;

-- =====================================================
-- HELPER FUNCTIONS
-- =====================================================

-- Function to check if trial arm already extracted
CREATE OR REPLACE FUNCTION check_extraction_exists(
    p_nct_id VARCHAR,
    p_arm_name VARCHAR,
    p_dosing_regimen VARCHAR
) RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1 FROM clinical_trial_extractions
        WHERE nct_id = p_nct_id
          AND arm_name = p_arm_name
          AND dosing_regimen = p_dosing_regimen
    );
END;
$$ LANGUAGE plpgsql;

-- Function to get extraction statistics
CREATE OR REPLACE FUNCTION get_extraction_stats()
RETURNS TABLE (
    total_extractions BIGINT,
    unique_trials BIGINT,
    unique_drugs BIGINT,
    unique_indications BIGINT,
    avg_endpoints_per_trial NUMERIC,
    avg_safety_measures_per_trial NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT as total_extractions,
        COUNT(DISTINCT nct_id)::BIGINT as unique_trials,
        COUNT(DISTINCT drug_name)::BIGINT as unique_drugs,
        COUNT(DISTINCT indication)::BIGINT as unique_indications,
        (SELECT AVG(endpoint_count)
         FROM (SELECT extraction_id, COUNT(*) as endpoint_count
               FROM trial_efficacy_endpoints
               GROUP BY extraction_id) sub) as avg_endpoints_per_trial,
        (SELECT AVG(safety_count)
         FROM (SELECT extraction_id, COUNT(*) as safety_count
               FROM trial_safety_endpoints
               GROUP BY extraction_id) sub) as avg_safety_measures_per_trial
    FROM clinical_trial_extractions;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- COMMENTS FOR DOCUMENTATION
-- =====================================================

COMMENT ON TABLE clinical_trial_extractions IS 'Main table storing one row per trial arm with basic metadata';
COMMENT ON TABLE trial_baseline_characteristics IS 'Patient demographics, disease history, prior medications';
COMMENT ON TABLE trial_efficacy_endpoints IS 'Efficacy outcomes at various timepoints';
COMMENT ON TABLE trial_safety_endpoints IS 'Safety outcomes and adverse events';
COMMENT ON TABLE standard_clinical_endpoints IS 'Library of standard endpoints by indication from landscape discovery';

COMMENT ON COLUMN trial_baseline_characteristics.disease_specific_baseline IS 'JSONB field for biomarkers like TRAb, AChR status, etc.';
COMMENT ON COLUMN trial_baseline_characteristics.baseline_severity_scores IS 'JSONB field for disease-specific scales like EASI, PASI, DAS28';
COMMENT ON COLUMN trial_baseline_characteristics.prior_medications_detail IS 'JSONB field for detailed prior medication history';

-- =====================================================
-- END OF SCHEMA
-- =====================================================
