-- Efficacy Comparison Module Database Schema
-- Version: 1.0
-- Date: 2026-01-10

-- ============================================================================
-- MAIN TABLES
-- ============================================================================

-- Trial-level information for efficacy comparisons
CREATE TABLE IF NOT EXISTS efficacy_comparison_trials (
    trial_id SERIAL PRIMARY KEY,

    -- Drug identification
    drug_id INTEGER REFERENCES drugs(drug_id) ON DELETE SET NULL,
    drug_name VARCHAR(255) NOT NULL,
    generic_name VARCHAR(255),
    manufacturer VARCHAR(255),

    -- Trial identification
    nct_id VARCHAR(20),
    trial_name VARCHAR(100),  -- Acronym like TULIP-2, SOLO-1
    trial_phase VARCHAR(20),  -- Phase 2, Phase 3

    -- Enrollment
    total_enrollment INTEGER,

    -- Indication
    indication_name VARCHAR(500) NOT NULL,
    indication_mesh_id VARCHAR(20),

    -- Patient population - CRITICAL for cross-trial comparison
    patient_population VARCHAR(100),  -- csDMARD-IR, bDMARD-IR, TNF-IR, MTX-naive, biologic-naive, etc.
    patient_population_description TEXT,  -- Full inclusion criteria summary
    line_of_therapy INTEGER,  -- 1, 2, 3+ (line of therapy)

    -- Prior treatment requirements
    prior_treatment_failures_required INTEGER,  -- Minimum number of prior treatment failures
    prior_treatment_failures_description VARCHAR(500),  -- e.g., "≥1 TNF inhibitor", "≥1 bDMARD"

    -- Disease subtype/severity requirements
    disease_subtype VARCHAR(100),  -- seropositive, seronegative, moderate-to-severe, etc.
    disease_activity_requirement VARCHAR(255),  -- e.g., "DAS28-CRP ≥3.2", "EASI ≥16"

    -- Arms stored as JSONB for flexibility
    -- Format: [{"name": "300mg Q2W", "n": 180, "is_active": true, "dose": "300mg", "frequency": "Q2W"}, ...]
    arms JSONB,

    -- Background/concomitant therapy - enhanced
    background_therapy VARCHAR(500),
    background_therapy_required BOOLEAN DEFAULT FALSE,
    -- Detailed concomitant therapies as JSONB
    -- Format: [{"therapy_name": "methotrexate", "is_required": true, "dose_requirement": "≥15mg/week", "percentage_on_therapy": 0.85}]
    concomitant_therapies JSONB,

    -- Rescue therapy
    rescue_therapy_allowed BOOLEAN DEFAULT FALSE,
    rescue_therapy_description VARCHAR(500),

    -- Data source tracking
    primary_source_type VARCHAR(50),  -- PMC_FULLTEXT, ABSTRACT, FDA_LABEL, CTGOV_RESULTS, PRESS_RELEASE
    primary_source_url TEXT,
    pmid VARCHAR(20),
    pmc_id VARCHAR(20),

    -- Extraction metadata
    extraction_timestamp TIMESTAMP DEFAULT NOW(),
    extraction_confidence FLOAT,
    extraction_notes TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT uq_trial_drug_nct UNIQUE(nct_id, drug_id)
);

-- Baseline characteristics per trial arm
CREATE TABLE IF NOT EXISTS efficacy_comparison_baseline (
    baseline_id SERIAL PRIMARY KEY,
    trial_id INTEGER NOT NULL REFERENCES efficacy_comparison_trials(trial_id) ON DELETE CASCADE,
    arm_name VARCHAR(100) NOT NULL,

    -- Sample size
    n INTEGER,

    -- Demographics - Age
    age_mean FLOAT,
    age_median FLOAT,
    age_sd FLOAT,
    age_range_min FLOAT,
    age_range_max FLOAT,

    -- Demographics - Sex
    male_pct FLOAT,
    female_pct FLOAT,

    -- Demographics - Race (stored as JSONB for flexibility)
    -- Format: {"white": 0.65, "black": 0.12, "asian": 0.18, "other": 0.05, "not_reported": 0.0}
    race_breakdown JSONB,

    -- Demographics - Weight/BMI
    weight_mean FLOAT,
    weight_unit VARCHAR(10) DEFAULT 'kg',
    bmi_mean FLOAT,

    -- Disease characteristics
    disease_duration_mean FLOAT,
    disease_duration_median FLOAT,
    disease_duration_unit VARCHAR(20) DEFAULT 'years',  -- years, months

    -- Disease severity scores (disease-specific, stored as JSONB)
    -- Format depends on disease, e.g., for AtD: {"EASI": {"mean": 25.3, "sd": 12.1}, "IGA": {"score_3_pct": 0.65, "score_4_pct": 0.35}, "BSA": {"mean": 45.2}}
    -- For RA: {"DAS28_CRP": {"mean": 5.8, "sd": 0.9}, "CDAI": {"mean": 35.2}, "HAQ_DI": {"mean": 1.5}}
    severity_scores JSONB,

    -- Serology status (critical for RA, SLE, other autoimmune)
    rf_positive_pct FLOAT,  -- Rheumatoid factor positive %
    anti_ccp_positive_pct FLOAT,  -- Anti-CCP antibody positive %
    seropositive_pct FLOAT,  -- Either RF+ or anti-CCP+ (often reported as combined)
    ana_positive_pct FLOAT,  -- ANA positive (for SLE)
    anti_dsdna_positive_pct FLOAT,  -- Anti-dsDNA positive (for SLE)

    -- Inflammatory markers at baseline
    crp_mean FLOAT,  -- C-reactive protein mg/L
    crp_median FLOAT,
    esr_mean FLOAT,  -- Erythrocyte sedimentation rate mm/hr

    -- Prior treatments
    prior_systemic_pct FLOAT,
    prior_biologic_pct FLOAT,
    prior_topical_pct FLOAT,
    -- Detailed prior treatments as JSONB
    -- Format: [{"treatment": "methotrexate", "pct": 0.45}, {"treatment": "cyclosporine", "pct": 0.30}]
    prior_treatments_detail JSONB,

    -- Number of prior treatment failures (for refractory populations)
    prior_biologic_failures_mean FLOAT,
    prior_dmard_failures_mean FLOAT,

    -- Concomitant therapy at baseline
    on_mtx_pct FLOAT,  -- % on methotrexate at baseline
    mtx_dose_mean FLOAT,  -- Mean MTX dose mg/week
    on_steroids_pct FLOAT,  -- % on corticosteroids
    steroid_dose_mean FLOAT,  -- Mean prednisone equivalent dose mg/day

    -- Source tracking
    source_table VARCHAR(100),  -- "Table 1", "Baseline characteristics"

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT uq_baseline_trial_arm UNIQUE(trial_id, arm_name)
);

-- All efficacy endpoints extracted
CREATE TABLE IF NOT EXISTS efficacy_comparison_endpoints (
    endpoint_id SERIAL PRIMARY KEY,
    trial_id INTEGER NOT NULL REFERENCES efficacy_comparison_trials(trial_id) ON DELETE CASCADE,
    arm_name VARCHAR(100) NOT NULL,

    -- Endpoint identification
    endpoint_name_raw VARCHAR(500) NOT NULL,  -- As extracted from source
    endpoint_name_normalized VARCHAR(255),     -- Standardized name from library
    endpoint_category VARCHAR(50),             -- Primary, Secondary, Exploratory, PRO, Biomarker

    -- Timepoint
    timepoint VARCHAR(50),       -- "Week 16", "Month 12", "Day 85"
    timepoint_weeks FLOAT,       -- Normalized to weeks for sorting/comparison

    -- Sample size for this endpoint
    n_evaluated INTEGER,

    -- For responder/binary endpoints (EASI-75, IGA 0/1, ACR20, SRI-4)
    responders_n INTEGER,
    responders_pct FLOAT,

    -- For continuous endpoints (mean change, LSM change)
    mean_value FLOAT,
    median_value FLOAT,
    change_from_baseline FLOAT,
    change_from_baseline_pct FLOAT,
    se FLOAT,                    -- Standard error
    sd FLOAT,                    -- Standard deviation
    ci_lower FLOAT,              -- 95% CI lower bound
    ci_upper FLOAT,              -- 95% CI upper bound

    -- Statistical comparison
    vs_comparator VARCHAR(100),  -- Which arm is being compared (e.g., "Placebo")
    p_value VARCHAR(50),         -- Stored as string to preserve formatting (e.g., "<0.001")
    p_value_numeric FLOAT,       -- Numeric value for sorting/filtering
    is_statistically_significant BOOLEAN,

    -- Source tracking
    source_table VARCHAR(100),   -- "Table 2", "Figure 1"
    source_text TEXT,            -- Exact quote from source

    -- Metadata
    extraction_confidence FLOAT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Constraints
    CONSTRAINT uq_endpoint_trial_arm_name_time UNIQUE(trial_id, arm_name, endpoint_name_normalized, timepoint)
);

-- Endpoint library for standardization and discovery
CREATE TABLE IF NOT EXISTS efficacy_endpoint_library (
    endpoint_lib_id SERIAL PRIMARY KEY,

    -- Disease/therapeutic area context
    therapeutic_area VARCHAR(100),
    -- Array of diseases this endpoint applies to
    diseases TEXT[],

    -- Endpoint definition
    endpoint_name_canonical VARCHAR(255) NOT NULL,  -- e.g., "EASI-75"
    endpoint_name_full VARCHAR(500),                 -- "75% improvement in EASI score from baseline"
    -- Array of alternative names/spellings
    endpoint_aliases TEXT[],                         -- ["EASI 75", "EASI75", "75% EASI improvement", "EASI-75 response"]

    -- Classification
    endpoint_type VARCHAR(50),                       -- efficacy, safety, PRO, biomarker
    endpoint_category_typical VARCHAR(50),           -- Usually primary/secondary for this endpoint
    measurement_type VARCHAR(50),                    -- responder, continuous, time_to_event, count

    -- Interpretation
    direction VARCHAR(20),                           -- higher_better, lower_better, reduction
    typical_timepoints TEXT[],                       -- ["Week 12", "Week 16", "Week 52"]
    response_threshold VARCHAR(100),                 -- "75% improvement from baseline"

    -- Validation status
    is_validated BOOLEAN DEFAULT FALSE,
    regulatory_acceptance VARCHAR(100),              -- FDA, EMA, both, none
    quality_tier INTEGER,                            -- 1=gold standard, 2=validated PRO, 3=exploratory

    -- Organ domain (for multi-system diseases)
    organ_domain VARCHAR(100),                       -- Skin, Joint, Renal, etc.

    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'system',        -- 'system', 'llm_discovery', 'manual'

    -- Constraints
    CONSTRAINT uq_endpoint_canonical_area UNIQUE(endpoint_name_canonical, therapeutic_area)
);

-- Tracking table for identified pivotal trials (for caching/audit)
CREATE TABLE IF NOT EXISTS efficacy_pivotal_trials_cache (
    cache_id SERIAL PRIMARY KEY,

    drug_name VARCHAR(255) NOT NULL,
    generic_name VARCHAR(255),
    indication_name VARCHAR(500) NOT NULL,

    -- Identified trials as JSONB array
    -- Format: [{"nct_id": "NCT02446899", "trial_name": "TULIP-2", "phase": "Phase 3", "confidence": 0.95}]
    pivotal_trials JSONB,

    -- Identification method used
    identification_method VARCHAR(100),  -- fda_label, ctgov_filter, web_search, combined

    -- Cache metadata
    cached_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP,

    CONSTRAINT uq_pivotal_cache UNIQUE(drug_name, indication_name)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Trial indexes
CREATE INDEX IF NOT EXISTS idx_ect_drug_id ON efficacy_comparison_trials(drug_id);
CREATE INDEX IF NOT EXISTS idx_ect_drug_name ON efficacy_comparison_trials(drug_name);
CREATE INDEX IF NOT EXISTS idx_ect_indication ON efficacy_comparison_trials(indication_name);
CREATE INDEX IF NOT EXISTS idx_ect_nct_id ON efficacy_comparison_trials(nct_id);
CREATE INDEX IF NOT EXISTS idx_ect_trial_name ON efficacy_comparison_trials(trial_name);
CREATE INDEX IF NOT EXISTS idx_ect_patient_pop ON efficacy_comparison_trials(patient_population);
CREATE INDEX IF NOT EXISTS idx_ect_line_of_therapy ON efficacy_comparison_trials(line_of_therapy);
CREATE INDEX IF NOT EXISTS idx_ect_disease_subtype ON efficacy_comparison_trials(disease_subtype);

-- Baseline indexes
CREATE INDEX IF NOT EXISTS idx_ecb_trial_id ON efficacy_comparison_baseline(trial_id);
CREATE INDEX IF NOT EXISTS idx_ecb_arm_name ON efficacy_comparison_baseline(arm_name);
CREATE INDEX IF NOT EXISTS idx_ecb_seropositive ON efficacy_comparison_baseline(seropositive_pct);
CREATE INDEX IF NOT EXISTS idx_ecb_prior_bio ON efficacy_comparison_baseline(prior_biologic_pct);

-- Endpoint indexes
CREATE INDEX IF NOT EXISTS idx_ece_trial_id ON efficacy_comparison_endpoints(trial_id);
CREATE INDEX IF NOT EXISTS idx_ece_endpoint_norm ON efficacy_comparison_endpoints(endpoint_name_normalized);
CREATE INDEX IF NOT EXISTS idx_ece_endpoint_raw ON efficacy_comparison_endpoints(endpoint_name_raw);
CREATE INDEX IF NOT EXISTS idx_ece_timepoint_weeks ON efficacy_comparison_endpoints(timepoint_weeks);
CREATE INDEX IF NOT EXISTS idx_ece_category ON efficacy_comparison_endpoints(endpoint_category);
CREATE INDEX IF NOT EXISTS idx_ece_arm ON efficacy_comparison_endpoints(arm_name);

-- Endpoint library indexes
CREATE INDEX IF NOT EXISTS idx_eel_canonical ON efficacy_endpoint_library(endpoint_name_canonical);
CREATE INDEX IF NOT EXISTS idx_eel_area ON efficacy_endpoint_library(therapeutic_area);
CREATE INDEX IF NOT EXISTS idx_eel_diseases ON efficacy_endpoint_library USING GIN(diseases);
CREATE INDEX IF NOT EXISTS idx_eel_aliases ON efficacy_endpoint_library USING GIN(endpoint_aliases);
CREATE INDEX IF NOT EXISTS idx_eel_type ON efficacy_endpoint_library(endpoint_type);

-- Pivotal trials cache index
CREATE INDEX IF NOT EXISTS idx_ptc_drug ON efficacy_pivotal_trials_cache(drug_name);
CREATE INDEX IF NOT EXISTS idx_ptc_indication ON efficacy_pivotal_trials_cache(indication_name);

-- ============================================================================
-- VIEWS
-- ============================================================================

-- View for comparing endpoints across drugs at the same timepoint
-- Now includes patient population for proper stratification
CREATE OR REPLACE VIEW vw_efficacy_comparison AS
SELECT
    t.indication_name,
    t.patient_population,  -- CRITICAL: csDMARD-IR vs bDMARD-IR changes interpretation
    t.line_of_therapy,
    t.drug_name,
    t.generic_name,
    t.trial_name,
    t.nct_id,
    e.arm_name,
    e.endpoint_name_normalized,
    e.endpoint_category,
    e.timepoint,
    e.timepoint_weeks,
    e.n_evaluated,
    e.responders_n,
    e.responders_pct,
    e.change_from_baseline,
    e.change_from_baseline_pct,
    e.p_value,
    e.is_statistically_significant,
    t.background_therapy,
    t.primary_source_type,
    e.extraction_confidence
FROM efficacy_comparison_endpoints e
JOIN efficacy_comparison_trials t ON e.trial_id = t.trial_id
ORDER BY t.indication_name, t.patient_population, e.endpoint_name_normalized, e.timepoint_weeks, t.drug_name;

-- View for baseline comparison across drugs
-- Enhanced with serology and inflammatory markers
CREATE OR REPLACE VIEW vw_baseline_comparison AS
SELECT
    t.indication_name,
    t.patient_population,
    t.line_of_therapy,
    t.drug_name,
    t.trial_name,
    b.arm_name,
    b.n,
    b.age_mean,
    b.male_pct,
    b.disease_duration_mean,
    b.severity_scores,
    -- Serology (critical for RA)
    b.rf_positive_pct,
    b.anti_ccp_positive_pct,
    b.seropositive_pct,
    -- Inflammatory markers
    b.crp_mean,
    b.esr_mean,
    -- Prior treatments
    b.prior_systemic_pct,
    b.prior_biologic_pct,
    b.prior_biologic_failures_mean,
    -- Concomitant therapy
    b.on_mtx_pct,
    b.on_steroids_pct
FROM efficacy_comparison_baseline b
JOIN efficacy_comparison_trials t ON b.trial_id = t.trial_id
ORDER BY t.indication_name, t.patient_population, t.drug_name, b.arm_name;

-- NEW: View for comparing trials within same patient population
-- Use this for head-to-head style comparisons
CREATE OR REPLACE VIEW vw_efficacy_by_population AS
SELECT
    t.indication_name,
    t.patient_population,
    t.drug_name,
    t.generic_name,
    t.trial_name,
    t.total_enrollment,
    t.background_therapy,
    e.endpoint_name_normalized,
    e.timepoint,
    -- Active arm results (exclude placebo)
    MAX(CASE WHEN e.arm_name NOT ILIKE '%placebo%' THEN e.responders_pct END) as active_responders_pct,
    MAX(CASE WHEN e.arm_name ILIKE '%placebo%' THEN e.responders_pct END) as placebo_responders_pct,
    MAX(CASE WHEN e.arm_name NOT ILIKE '%placebo%' THEN e.p_value END) as p_value
FROM efficacy_comparison_endpoints e
JOIN efficacy_comparison_trials t ON e.trial_id = t.trial_id
WHERE e.endpoint_category = 'Primary'
GROUP BY t.indication_name, t.patient_population, t.drug_name, t.generic_name,
         t.trial_name, t.total_enrollment, t.background_therapy,
         e.endpoint_name_normalized, e.timepoint
ORDER BY t.indication_name, t.patient_population, e.endpoint_name_normalized, active_responders_pct DESC;
