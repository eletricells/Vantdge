-- Migration: Extend trial_name column to support longer trial names
-- Version: 002
-- Date: 2026-01-12
-- Description: Some trials from CT.gov have very long descriptive names (e.g.,
--              "A Study Comparing 2 Doses Of CP-690,550 Vs. Placebo For The Treatment
--               Of Rheumatoid Arthritis In Patients On Other Background Arthritis Medications")
--              This migration extends the column to accommodate these.

-- Drop dependent views first
DROP VIEW IF EXISTS vw_efficacy_comparison CASCADE;
DROP VIEW IF EXISTS vw_baseline_comparison CASCADE;
DROP VIEW IF EXISTS vw_efficacy_by_population CASCADE;

-- Extend trial_name column from VARCHAR(100) to VARCHAR(500)
ALTER TABLE efficacy_comparison_trials
ALTER COLUMN trial_name TYPE VARCHAR(500);

-- Also extend arm_name in baseline and endpoints tables to be safe
ALTER TABLE efficacy_comparison_baseline
ALTER COLUMN arm_name TYPE VARCHAR(255);

ALTER TABLE efficacy_comparison_endpoints
ALTER COLUMN arm_name TYPE VARCHAR(255);

-- Recreate views

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
