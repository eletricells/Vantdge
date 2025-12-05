-- Biopharma Investment Analysis - MCP Database Schema
-- PostgreSQL schema for proprietary data

-- Historical Deals Table
CREATE TABLE IF NOT EXISTS historical_deals (
    id SERIAL PRIMARY KEY,
    deal_name VARCHAR(255) NOT NULL,
    target_company VARCHAR(255),
    drug_name VARCHAR(255),
    target_biology VARCHAR(255),
    indication VARCHAR(255) NOT NULL,
    phase VARCHAR(50),
    deal_type VARCHAR(50), -- acquisition, license, collaboration
    announcement_date DATE,

    -- Deal terms
    upfront_payment_usd DECIMAL(12, 2),
    milestone_payments_usd DECIMAL(12, 2),
    total_deal_value_usd DECIMAL(12, 2),
    royalty_rate VARCHAR(50),

    -- Analysis at time of deal
    clinical_confidence_score DECIMAL(3, 2),
    commercial_confidence_score DECIMAL(3, 2),
    probability_of_success DECIMAL(3, 2),
    estimated_peak_sales_usd DECIMAL(12, 2),

    -- Outcome data
    outcome VARCHAR(50), -- success, failure, ongoing, terminated
    outcome_date DATE,
    outcome_notes TEXT,
    actual_peak_sales_usd DECIMAL(12, 2),
    regulatory_approval_status VARCHAR(100),

    -- Strategic rationale
    deal_rationale TEXT,
    key_strengths TEXT[],
    key_risks TEXT[],
    competitive_advantages TEXT[],

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Expert Annotations Table
CREATE TABLE IF NOT EXISTS expert_annotations (
    id SERIAL PRIMARY KEY,
    target_name VARCHAR(255) NOT NULL,
    drug_name VARCHAR(255),
    indication VARCHAR(255),

    -- Expert info
    expert_name VARCHAR(255) NOT NULL,
    expert_role VARCHAR(100), -- scientific advisor, clinical expert, commercial lead
    confidence_level VARCHAR(20), -- high, medium, low

    -- Annotation content
    annotation_type VARCHAR(50), -- target_validation, clinical_assessment, commercial_view, safety_concern
    notes TEXT NOT NULL,
    key_insights TEXT[],
    concerns TEXT[],

    -- Supporting data
    supporting_evidence TEXT[],
    citations TEXT[],

    -- Metadata
    annotation_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Target Biology Knowledge Base
CREATE TABLE IF NOT EXISTS target_biology_kb (
    id SERIAL PRIMARY KEY,
    target_name VARCHAR(255) NOT NULL UNIQUE,
    target_type VARCHAR(100), -- receptor, enzyme, etc.

    -- Internal assessment
    genetic_evidence_strength VARCHAR(20), -- HIGH, MEDIUM, LOW
    preclinical_validation_strength VARCHAR(20),
    druggability_score DECIMAL(3, 2),
    safety_risk_level VARCHAR(20),

    -- Strategic importance
    strategic_priority VARCHAR(20), -- high, medium, low
    portfolio_fit_score DECIMAL(3, 2),
    competitive_landscape_assessment TEXT,

    -- Internal notes
    internal_notes TEXT,
    key_papers TEXT[],
    failed_programs TEXT[],

    -- Metadata
    last_reviewed_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Disease Knowledge Base
CREATE TABLE IF NOT EXISTS disease_kb (
    id SERIAL PRIMARY KEY,
    disease_name VARCHAR(255) NOT NULL,
    icd_codes VARCHAR(255)[],

    -- Market assessment
    us_prevalence INTEGER,
    global_prevalence INTEGER,
    market_size_usd DECIMAL(12, 2),
    market_growth_rate DECIMAL(5, 2),

    -- Strategic assessment
    strategic_priority VARCHAR(20),
    unmet_need_severity VARCHAR(20), -- critical, high, moderate, low
    competitive_intensity VARCHAR(20), -- high, medium, low

    -- Internal expertise
    internal_expertise_level VARCHAR(20), -- expert, intermediate, limited
    portfolio_assets_count INTEGER,

    -- Notes
    internal_notes TEXT,
    key_kols TEXT[],
    patient_advocacy_groups TEXT[],

    -- Metadata
    last_reviewed_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Valuation Models Table
CREATE TABLE IF NOT EXISTS valuation_models (
    id SERIAL PRIMARY KEY,
    model_name VARCHAR(255) NOT NULL,
    indication VARCHAR(255),
    phase VARCHAR(50),

    -- Model parameters
    probability_of_success DECIMAL(3, 2),
    peak_sales_estimate_usd DECIMAL(12, 2),
    time_to_peak_years INTEGER,
    cogs_percentage DECIMAL(5, 2),

    -- Valuation outputs
    npv_estimate_usd DECIMAL(12, 2),
    irr_percentage DECIMAL(5, 2),
    risk_adjusted_npv_usd DECIMAL(12, 2),

    -- Model metadata
    model_assumptions TEXT,
    key_sensitivities TEXT[],
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Competitive Intelligence Table
CREATE TABLE IF NOT EXISTS competitive_intelligence (
    id SERIAL PRIMARY KEY,
    competitor_name VARCHAR(255) NOT NULL,
    drug_name VARCHAR(255),
    target_biology VARCHAR(255),
    indication VARCHAR(255),
    phase VARCHAR(50),

    -- Intelligence data
    latest_clinical_data TEXT,
    safety_signals TEXT[],
    efficacy_signals TEXT[],
    market_positioning TEXT,
    estimated_filing_date DATE,

    -- Our assessment
    competitive_threat_level VARCHAR(20), -- critical, high, medium, low
    differentiation_vs_our_assets TEXT,
    strategic_implications TEXT,

    -- Sources
    data_sources TEXT[],
    last_updated DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_historical_deals_indication ON historical_deals(indication);
CREATE INDEX IF NOT EXISTS idx_historical_deals_target ON historical_deals(drug_name, target_biology);
CREATE INDEX IF NOT EXISTS idx_historical_deals_outcome ON historical_deals(outcome);
CREATE INDEX IF NOT EXISTS idx_expert_annotations_target ON expert_annotations(target_name);
CREATE INDEX IF NOT EXISTS idx_expert_annotations_drug ON expert_annotations(drug_name);
CREATE INDEX IF NOT EXISTS idx_target_biology_kb_name ON target_biology_kb(target_name);
CREATE INDEX IF NOT EXISTS idx_disease_kb_name ON disease_kb(disease_name);
CREATE INDEX IF NOT EXISTS idx_competitive_intel_competitor ON competitive_intelligence(competitor_name, drug_name);

-- Landscape Discovery Results Table
CREATE TABLE IF NOT EXISTS landscape_discovery_results (
    id SERIAL PRIMARY KEY,
    indication VARCHAR(500) NOT NULL,

    -- Discovery metadata
    drugs_found_count INTEGER NOT NULL DEFAULT 0,
    iterations_run INTEGER,
    total_searches INTEGER,

    -- Results (stored as JSONB for flexibility)
    drugs_found JSONB NOT NULL,
    standard_endpoints JSONB,

    -- Search metadata
    search_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Uniqueness constraint - one result per indication (most recent)
    UNIQUE(indication)
);

-- Index for fast lookup by indication
CREATE INDEX IF NOT EXISTS idx_landscape_results_indication ON landscape_discovery_results(indication);
CREATE INDEX IF NOT EXISTS idx_landscape_results_date ON landscape_discovery_results(search_date DESC);

-- Views for common queries
CREATE OR REPLACE VIEW successful_deals AS
SELECT * FROM historical_deals
WHERE outcome = 'success' AND regulatory_approval_status LIKE '%approved%';

CREATE OR REPLACE VIEW high_priority_targets AS
SELECT * FROM target_biology_kb
WHERE strategic_priority = 'high' AND genetic_evidence_strength = 'HIGH';

CREATE OR REPLACE VIEW unmet_need_diseases AS
SELECT * FROM disease_kb
WHERE unmet_need_severity IN ('critical', 'high')
ORDER BY market_size_usd DESC;

CREATE OR REPLACE VIEW recent_landscape_discoveries AS
SELECT
    indication,
    drugs_found_count,
    iterations_run,
    search_date,
    drugs_found,
    standard_endpoints
FROM landscape_discovery_results
ORDER BY search_date DESC
LIMIT 50;
