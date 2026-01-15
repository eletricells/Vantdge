-- Migration: Add patient population and enhanced baseline fields
-- Version: 001
-- Date: 2026-01-12
-- Description: Adds fields for proper stratification of trials by patient population
--              (csDMARD-IR vs bDMARD-IR, etc.) and enhanced baseline characteristics

-- ============================================================================
-- TRIALS TABLE - Add patient population fields
-- ============================================================================

-- Patient population classification
ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS patient_population VARCHAR(100);
COMMENT ON COLUMN efficacy_comparison_trials.patient_population IS 'Patient population type: csDMARD-IR, bDMARD-IR, TNF-IR, MTX-naive, biologic-naive, etc.';

ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS patient_population_description TEXT;
COMMENT ON COLUMN efficacy_comparison_trials.patient_population_description IS 'Full description of inclusion criteria for patient population';

ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS line_of_therapy INTEGER;
COMMENT ON COLUMN efficacy_comparison_trials.line_of_therapy IS 'Line of therapy: 1, 2, 3+ (1L, 2L, 3L+)';

-- Prior treatment requirements
ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS prior_treatment_failures_required INTEGER;
COMMENT ON COLUMN efficacy_comparison_trials.prior_treatment_failures_required IS 'Minimum number of prior treatment failures required for enrollment';

ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS prior_treatment_failures_description VARCHAR(500);
COMMENT ON COLUMN efficacy_comparison_trials.prior_treatment_failures_description IS 'Description of prior treatment failure requirements, e.g., ">=1 TNF inhibitor"';

-- Disease subtype
ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS disease_subtype VARCHAR(100);
COMMENT ON COLUMN efficacy_comparison_trials.disease_subtype IS 'Disease subtype: seropositive, seronegative, moderate-to-severe, etc.';

ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS disease_activity_requirement VARCHAR(255);
COMMENT ON COLUMN efficacy_comparison_trials.disease_activity_requirement IS 'Disease activity requirement for enrollment, e.g., "DAS28-CRP >=3.2"';

-- Concomitant therapy details
ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS concomitant_therapies JSONB;
COMMENT ON COLUMN efficacy_comparison_trials.concomitant_therapies IS 'Detailed concomitant therapy requirements as JSONB array';

-- Rescue therapy
ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS rescue_therapy_allowed BOOLEAN DEFAULT FALSE;

ALTER TABLE efficacy_comparison_trials
ADD COLUMN IF NOT EXISTS rescue_therapy_description VARCHAR(500);

-- ============================================================================
-- BASELINE TABLE - Add serology and enhanced fields
-- ============================================================================

-- Weight/BMI
ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS weight_mean FLOAT;

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS weight_unit VARCHAR(10) DEFAULT 'kg';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS bmi_mean FLOAT;

-- Serology status (critical for RA, SLE)
ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS rf_positive_pct FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.rf_positive_pct IS 'Rheumatoid factor positive percentage';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS anti_ccp_positive_pct FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.anti_ccp_positive_pct IS 'Anti-CCP antibody positive percentage';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS seropositive_pct FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.seropositive_pct IS 'Either RF+ or anti-CCP+ percentage';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS ana_positive_pct FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.ana_positive_pct IS 'ANA positive percentage (for SLE)';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS anti_dsdna_positive_pct FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.anti_dsdna_positive_pct IS 'Anti-dsDNA positive percentage (for SLE)';

-- Inflammatory markers
ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS crp_mean FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.crp_mean IS 'C-reactive protein mean (mg/L)';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS crp_median FLOAT;

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS esr_mean FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.esr_mean IS 'Erythrocyte sedimentation rate mean (mm/hr)';

-- Prior treatment failures
ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS prior_biologic_failures_mean FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.prior_biologic_failures_mean IS 'Mean number of prior biologic failures';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS prior_dmard_failures_mean FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.prior_dmard_failures_mean IS 'Mean number of prior DMARD failures';

-- Concomitant therapy at baseline
ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS on_mtx_pct FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.on_mtx_pct IS 'Percentage on methotrexate at baseline';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS mtx_dose_mean FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.mtx_dose_mean IS 'Mean methotrexate dose (mg/week)';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS on_steroids_pct FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.on_steroids_pct IS 'Percentage on corticosteroids at baseline';

ALTER TABLE efficacy_comparison_baseline
ADD COLUMN IF NOT EXISTS steroid_dose_mean FLOAT;
COMMENT ON COLUMN efficacy_comparison_baseline.steroid_dose_mean IS 'Mean corticosteroid dose (prednisone equivalent mg/day)';

-- ============================================================================
-- NEW INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_ect_patient_pop ON efficacy_comparison_trials(patient_population);
CREATE INDEX IF NOT EXISTS idx_ect_line_of_therapy ON efficacy_comparison_trials(line_of_therapy);
CREATE INDEX IF NOT EXISTS idx_ect_disease_subtype ON efficacy_comparison_trials(disease_subtype);
CREATE INDEX IF NOT EXISTS idx_ecb_seropositive ON efficacy_comparison_baseline(seropositive_pct);
CREATE INDEX IF NOT EXISTS idx_ecb_prior_bio ON efficacy_comparison_baseline(prior_biologic_pct);

-- ============================================================================
-- UPDATE VIEWS
-- ============================================================================

-- Drop and recreate views with new columns
DROP VIEW IF EXISTS vw_efficacy_comparison;
DROP VIEW IF EXISTS vw_baseline_comparison;
DROP VIEW IF EXISTS vw_efficacy_by_population;

-- View for comparing endpoints across drugs at the same timepoint
CREATE VIEW vw_efficacy_comparison AS
SELECT
    t.indication_name,
    t.patient_population,
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
CREATE VIEW vw_baseline_comparison AS
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
    b.rf_positive_pct,
    b.anti_ccp_positive_pct,
    b.seropositive_pct,
    b.crp_mean,
    b.esr_mean,
    b.prior_systemic_pct,
    b.prior_biologic_pct,
    b.prior_biologic_failures_mean,
    b.on_mtx_pct,
    b.on_steroids_pct
FROM efficacy_comparison_baseline b
JOIN efficacy_comparison_trials t ON b.trial_id = t.trial_id
ORDER BY t.indication_name, t.patient_population, t.drug_name, b.arm_name;

-- View for comparing trials within same patient population
CREATE VIEW vw_efficacy_by_population AS
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
