-- =====================================================
-- OFF-LABEL CASE STUDY DATABASE SCHEMA
-- =====================================================
-- Purpose: Store off-label case studies, expanded access data, and real-world evidence
-- Author: Off-Label Case Study Agent
-- Date: 2025-11-18
-- =====================================================

-- =====================================================
-- MAIN CASE STUDY TABLE
-- =====================================================
-- One row per case study/paper
CREATE TABLE IF NOT EXISTS off_label_case_studies (
    case_study_id SERIAL PRIMARY KEY,
    
    -- Paper identification
    pmid VARCHAR(50),
    doi VARCHAR(100),
    pmc VARCHAR(50),
    title TEXT NOT NULL,
    authors TEXT,  -- Comma-separated author list
    journal VARCHAR(200),
    year INTEGER,
    abstract TEXT,
    
    -- Study classification
    study_type VARCHAR(50) NOT NULL,  -- "Case Report", "Case Series", "Retrospective Cohort", "EAP", "RWE", "N-of-1"
    relevance_score NUMERIC(3,2),  -- 0.0-1.0 relevance score
    
    -- Drug & indication
    drug_id INTEGER,  -- Link to drugs table (if exists)
    drug_name VARCHAR(255) NOT NULL,
    generic_name VARCHAR(255),
    mechanism VARCHAR(500),
    target VARCHAR(255),  -- Molecular target (e.g., "JAK1/JAK3", "PD-1")
    
    indication_treated VARCHAR(500) NOT NULL,  -- Off-label indication
    approved_indications JSONB,  -- Array of approved indications for comparison
    is_off_label BOOLEAN DEFAULT TRUE,  -- True if indication not in approved list
    
    -- Patient cohort
    n_patients INTEGER,  -- Total number of patients in study
    
    -- Treatment details
    dosing_regimen VARCHAR(255),  -- "5mg BID", "300mg Q2W", etc.
    treatment_duration VARCHAR(100),  -- "6 months", "12 weeks", etc.
    concomitant_medications JSONB,  -- Array of other drugs used
    
    -- Outcomes (summary)
    response_rate VARCHAR(100),  -- "75% (9/12)", "8/10 patients", etc.
    responders_n INTEGER,  -- Number of responders
    responders_pct NUMERIC,  -- Percentage of responders
    time_to_response VARCHAR(100),  -- "4-8 weeks", "2 months", etc.
    duration_of_response VARCHAR(100),  -- "Sustained at 12 months", "6 months", etc.
    
    -- Safety (summary)
    adverse_events JSONB,  -- Array of {event_name, n_patients, severity}
    serious_adverse_events_n INTEGER,
    discontinuations_n INTEGER,
    
    -- Clinical assessment (AI-generated)
    efficacy_signal VARCHAR(50),  -- "Strong", "Moderate", "Weak", "None"
    safety_profile VARCHAR(50),  -- "Acceptable", "Concerning", "Unknown"
    mechanism_rationale TEXT,  -- Why this mechanism makes sense for this indication
    development_potential VARCHAR(50),  -- "High", "Medium", "Low"
    key_findings TEXT,  -- 1-2 sentence summary
    
    -- Metadata
    paper_path TEXT,  -- Path to downloaded JSON/PDF
    is_open_access BOOLEAN DEFAULT FALSE,
    citation_count INTEGER,
    
    -- Extraction metadata
    extracted_by VARCHAR(100) DEFAULT 'Claude Sonnet 4.5',
    extraction_timestamp TIMESTAMP DEFAULT NOW(),
    extraction_confidence NUMERIC(3,2),  -- 0-1 confidence in extraction quality
    extraction_notes TEXT,
    
    -- Search metadata
    search_query TEXT,  -- Original search query that found this paper
    search_source VARCHAR(50),  -- "PubMed", "Tavily", "User Upload", "ClinicalTrials.gov"
    
    -- Prevent duplicate extractions
    UNIQUE(pmid, drug_name, indication_treated)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_off_label_drug_id ON off_label_case_studies(drug_id);
CREATE INDEX IF NOT EXISTS idx_off_label_drug_name ON off_label_case_studies(drug_name);
CREATE INDEX IF NOT EXISTS idx_off_label_indication ON off_label_case_studies(indication_treated);
CREATE INDEX IF NOT EXISTS idx_off_label_mechanism ON off_label_case_studies(mechanism);
CREATE INDEX IF NOT EXISTS idx_off_label_target ON off_label_case_studies(target);
CREATE INDEX IF NOT EXISTS idx_off_label_relevance ON off_label_case_studies(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_off_label_year ON off_label_case_studies(year DESC);
CREATE INDEX IF NOT EXISTS idx_off_label_study_type ON off_label_case_studies(study_type);

-- =====================================================
-- BASELINE CHARACTERISTICS (DETAILED)
-- =====================================================
-- Patient demographics and disease characteristics
-- Similar structure to trial_baseline_characteristics
CREATE TABLE IF NOT EXISTS off_label_baseline_characteristics (
    baseline_id SERIAL PRIMARY KEY,
    case_study_id INTEGER REFERENCES off_label_case_studies(case_study_id) ON DELETE CASCADE,
    
    -- Sample size
    n INTEGER,
    
    -- ============= STANDARD DEMOGRAPHICS =============
    
    -- Age
    median_age NUMERIC,
    mean_age NUMERIC,
    age_range VARCHAR(50),  -- "35-67", "18-75"
    age_sd NUMERIC,
    
    -- Sex
    male_n INTEGER,
    male_pct NUMERIC,
    female_n INTEGER,
    female_pct NUMERIC,
    
    -- Race/Ethnicity (flexible JSONB for case studies)
    race_ethnicity JSONB,  -- {"White": 8, "Asian": 2, "Hispanic": 2}
    
    -- ============= DISEASE CHARACTERISTICS =============
    
    -- Disease duration
    median_disease_duration NUMERIC,
    mean_disease_duration NUMERIC,
    disease_duration_unit VARCHAR(20) DEFAULT 'years',
    disease_duration_range VARCHAR(50),
    
    -- Disease severity
    disease_severity VARCHAR(100),  -- "Moderate to severe", "Refractory", "Mild"
    baseline_severity_scores JSONB,  -- Disease-specific scores
    
    -- ============= PRIOR THERAPIES =============
    
    -- Prior medication use (detailed)
    prior_medications_detail JSONB,  -- Array of {medication, n_patients, pct, outcome}
    prior_lines_median NUMERIC,
    prior_lines_mean NUMERIC,
    treatment_naive_n INTEGER,
    treatment_naive_pct NUMERIC,
    
    -- Specific prior therapy categories
    prior_steroid_use_n INTEGER,
    prior_steroid_use_pct NUMERIC,
    prior_biologic_use_n INTEGER,
    prior_biologic_use_pct NUMERIC,
    prior_immunosuppressant_use_n INTEGER,
    prior_immunosuppressant_use_pct NUMERIC,
    
    -- ============= COMORBIDITIES =============
    comorbidities JSONB,  -- Array of comorbidity names
    
    -- ============= BIOMARKERS =============
    biomarkers JSONB,  -- Disease-specific biomarkers
    
    -- Notes
    notes TEXT,
    source_table VARCHAR(100),  -- "Table 1", "Supplementary Table S1"
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_off_label_baseline_case_study ON off_label_baseline_characteristics(case_study_id);

-- =====================================================
-- OUTCOMES (DETAILED)
-- =====================================================
-- Treatment outcomes and efficacy data
-- Similar structure to trial_efficacy_endpoints
CREATE TABLE IF NOT EXISTS off_label_outcomes (
    outcome_id SERIAL PRIMARY KEY,
    case_study_id INTEGER REFERENCES off_label_case_studies(case_study_id) ON DELETE CASCADE,
    
    -- Outcome identification
    outcome_category VARCHAR(100),  -- "Primary", "Secondary", "Clinical Response", "Biomarker"
    outcome_name VARCHAR(500),  -- "Skin rash improvement", "Muscle strength", "CRP reduction"
    outcome_description TEXT,
    outcome_unit VARCHAR(100),  -- "%", "mg/dL", "score"
    
    -- Timepoint
    timepoint VARCHAR(50),  -- "Week 4", "Month 6", "End of treatment"
    timepoint_weeks INTEGER,  -- Normalized to weeks
    
    -- Measurement type
    measurement_type VARCHAR(50),  -- "Responder", "Change from baseline", "Absolute value"
    
    -- Responder data
    responders_n INTEGER,
    responders_pct NUMERIC,
    non_responders_n INTEGER,
    
    -- Continuous data
    mean_value NUMERIC,
    median_value NUMERIC,
    sd NUMERIC,
    range_min NUMERIC,
    range_max NUMERIC,
    
    -- Change from baseline
    mean_change NUMERIC,
    median_change NUMERIC,
    pct_change NUMERIC,
    
    -- Durability
    sustained_response BOOLEAN,  -- True if response maintained
    duration_of_response VARCHAR(100),  -- "6 months", "Ongoing at 12 months"
    
    -- Statistical significance (if reported)
    p_value NUMERIC,
    ci_lower NUMERIC,
    ci_upper NUMERIC,
    
    -- Notes
    notes TEXT,
    source_table VARCHAR(100),
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_off_label_outcomes_case_study ON off_label_outcomes(case_study_id);
CREATE INDEX IF NOT EXISTS idx_off_label_outcomes_name ON off_label_outcomes(outcome_name);
CREATE INDEX IF NOT EXISTS idx_off_label_outcomes_timepoint ON off_label_outcomes(timepoint_weeks);

-- =====================================================
-- SAFETY EVENTS (DETAILED)
-- =====================================================
-- Adverse events and safety data
-- Similar structure to trial_safety_endpoints
CREATE TABLE IF NOT EXISTS off_label_safety_events (
    safety_id SERIAL PRIMARY KEY,
    case_study_id INTEGER REFERENCES off_label_case_studies(case_study_id) ON DELETE CASCADE,
    
    -- Event categorization
    event_category VARCHAR(100),  -- "Adverse Event", "Serious AE", "Discontinuation", "Death"
    event_name VARCHAR(500),  -- "Infection", "Injection site reaction", "Elevated liver enzymes"
    event_description TEXT,
    
    -- Severity
    severity VARCHAR(50),  -- "Mild", "Moderate", "Severe", "Grade 3+", "Life-threatening"
    
    -- Incidence
    n_events INTEGER,  -- Number of events (can be > n_patients if multiple events per patient)
    n_patients INTEGER,  -- Number of patients with event
    incidence_pct NUMERIC,  -- Percentage of patients with event
    
    -- Timing
    time_to_onset VARCHAR(100),  -- "Week 2", "After 3 doses"
    
    -- Outcome
    event_outcome VARCHAR(100),  -- "Resolved", "Ongoing", "Led to discontinuation", "Fatal"
    
    -- Causality
    causality_assessment VARCHAR(100),  -- "Definitely related", "Probably related", "Possibly related", "Unlikely related"
    
    -- Action taken
    action_taken VARCHAR(255),  -- "Dose reduction", "Temporary hold", "Permanent discontinuation", "No action"
    
    -- Notes
    notes TEXT,
    source_table VARCHAR(100),
    
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_off_label_safety_case_study ON off_label_safety_events(case_study_id);
CREATE INDEX IF NOT EXISTS idx_off_label_safety_category ON off_label_safety_events(event_category);
CREATE INDEX IF NOT EXISTS idx_off_label_safety_severity ON off_label_safety_events(severity);

-- =====================================================
-- MECHANISM CROSS-REFERENCE
-- =====================================================
-- Aggregated analysis by mechanism + indication
CREATE TABLE IF NOT EXISTS mechanism_cross_reference (
    cross_ref_id SERIAL PRIMARY KEY,
    
    mechanism VARCHAR(500) NOT NULL,
    target VARCHAR(255),
    indication VARCHAR(500) NOT NULL,
    
    -- Aggregate statistics
    n_drugs_with_evidence INTEGER,
    n_studies INTEGER,
    total_patients INTEGER,
    aggregate_response_rate VARCHAR(100),  -- "75% (49/65)"
    pooled_response_pct NUMERIC,  -- Weighted average
    
    -- Drugs involved
    drugs_list JSONB,  -- Array of {drug_name, n_studies, n_patients, response_rate}
    
    -- Evidence assessment
    evidence_strength VARCHAR(50),  -- "Strong", "Moderate", "Weak"
    safety_assessment VARCHAR(50),  -- "Acceptable", "Concerning", "Unknown"
    mechanism_rationale TEXT,
    
    -- Development recommendation
    development_recommendation TEXT,
    repurposing_score NUMERIC(5,2),  -- 0-100 composite score
    
    -- Temporal data
    first_case_study_year INTEGER,
    most_recent_case_study_year INTEGER,
    trend VARCHAR(50),  -- "Increasing", "Stable", "Decreasing"
    
    -- Metadata
    last_updated TIMESTAMP DEFAULT NOW(),
    
    UNIQUE(mechanism, indication)
);

CREATE INDEX IF NOT EXISTS idx_mechanism_cross_ref_mechanism ON mechanism_cross_reference(mechanism);
CREATE INDEX IF NOT EXISTS idx_mechanism_cross_ref_indication ON mechanism_cross_reference(indication);
CREATE INDEX IF NOT EXISTS idx_mechanism_cross_ref_score ON mechanism_cross_reference(repurposing_score DESC);

-- =====================================================
-- COMMENTS FOR DOCUMENTATION
-- =====================================================
COMMENT ON TABLE off_label_case_studies IS 'Main table storing off-label case studies with summary data';
COMMENT ON TABLE off_label_baseline_characteristics IS 'Patient demographics and disease characteristics';
COMMENT ON TABLE off_label_outcomes IS 'Treatment outcomes and efficacy data';
COMMENT ON TABLE off_label_safety_events IS 'Adverse events and safety data';
COMMENT ON TABLE mechanism_cross_reference IS 'Aggregated analysis by mechanism + indication';

COMMENT ON COLUMN off_label_case_studies.relevance_score IS 'AI-generated relevance score (0-1): 1.0=direct match, 0.8=mechanism match, 0.6=indication match';
COMMENT ON COLUMN off_label_case_studies.efficacy_signal IS 'AI assessment: Strong (>70% response), Moderate (40-70%), Weak (<40%)';
COMMENT ON COLUMN off_label_case_studies.development_potential IS 'AI assessment: High (recommend Phase 2), Medium (monitor), Low (insufficient evidence)';
COMMENT ON COLUMN mechanism_cross_reference.repurposing_score IS 'Composite score (0-100): 80+=strong signal, 60-79=moderate, 40-59=weak, <40=insufficient';

