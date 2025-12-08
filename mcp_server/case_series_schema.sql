-- Case Series Workflow Database Schema
-- Supports progressive saving, caching, and historical run management

-- =====================================================
-- ANALYSIS RUNS - Tracks each workflow execution
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_analysis_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name VARCHAR(255) NOT NULL,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'in_progress',
    parameters JSONB DEFAULT '{}',
    papers_found INT DEFAULT 0,
    papers_extracted INT DEFAULT 0,
    opportunities_found INT DEFAULT 0,
    total_input_tokens INT DEFAULT 0,
    total_output_tokens INT DEFAULT 0,
    estimated_cost_usd DECIMAL(10, 4) DEFAULT 0,
    papers_from_cache INT DEFAULT 0,
    market_intel_from_cache INT DEFAULT 0,
    tokens_saved_by_cache INT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cs_runs_drug ON cs_analysis_runs(drug_name);
CREATE INDEX IF NOT EXISTS idx_cs_runs_status ON cs_analysis_runs(status);
CREATE INDEX IF NOT EXISTS idx_cs_runs_started ON cs_analysis_runs(started_at DESC);

-- =====================================================
-- DRUGS - Cached drug metadata
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_drugs (
    id SERIAL PRIMARY KEY,
    drug_name VARCHAR(255) NOT NULL UNIQUE,
    generic_name VARCHAR(255),
    mechanism TEXT,
    target VARCHAR(255),
    approved_indications JSONB DEFAULT '[]',
    data_sources JSONB DEFAULT '[]',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cs_drugs_name ON cs_drugs(drug_name);

-- =====================================================
-- PAPERS - Cached paper metadata and relevance
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_papers (
    id SERIAL PRIMARY KEY,
    pmid VARCHAR(20),
    pmcid VARCHAR(20),
    doi VARCHAR(255),
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT,
    journal VARCHAR(500),
    year INT,
    source VARCHAR(50),
    url TEXT,
    has_full_text BOOLEAN DEFAULT FALSE,
    full_text_url TEXT,
    relevance_drug VARCHAR(255),
    is_relevant BOOLEAN,
    relevance_score DECIMAL(3, 2),
    relevance_reason TEXT,
    extracted_disease VARCHAR(500),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pmid, relevance_drug)
);

CREATE INDEX IF NOT EXISTS idx_cs_papers_pmid ON cs_papers(pmid);
CREATE INDEX IF NOT EXISTS idx_cs_papers_drug ON cs_papers(relevance_drug);
CREATE INDEX IF NOT EXISTS idx_cs_papers_relevant ON cs_papers(is_relevant) WHERE is_relevant = TRUE;

-- =====================================================
-- CASE SERIES EXTRACTIONS - Extracted clinical data
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_extractions (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES cs_analysis_runs(run_id) ON DELETE SET NULL,
    pmid VARCHAR(20),
    paper_title TEXT,
    paper_year INT,
    drug_name VARCHAR(255) NOT NULL,
    disease VARCHAR(500) NOT NULL,
    is_off_label BOOLEAN DEFAULT TRUE,
    is_relevant BOOLEAN DEFAULT TRUE,
    n_patients INT,
    age_description VARCHAR(255),
    gender_distribution VARCHAR(255),
    disease_severity VARCHAR(255),
    prior_treatments TEXT,
    dosing_regimen TEXT,
    treatment_duration VARCHAR(255),
    concomitant_medications JSONB,
    response_rate VARCHAR(100),
    responders_n INT,
    responders_pct DECIMAL(5, 2),
    time_to_response VARCHAR(255),
    duration_of_response VARCHAR(255),
    primary_endpoint TEXT,
    primary_endpoint_result TEXT,
    efficacy_summary TEXT,
    efficacy_signal VARCHAR(50),
    adverse_events JSONB,
    serious_adverse_events JSONB,
    sae_count INT,
    sae_percentage DECIMAL(5, 2),
    discontinuations_n INT,
    safety_summary TEXT,
    safety_profile VARCHAR(50),
    evidence_level VARCHAR(50),
    study_design VARCHAR(100),
    follow_up_duration VARCHAR(255),
    key_findings TEXT,
    limitations TEXT,
    full_extraction JSONB,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(pmid, drug_name, disease)
);

CREATE INDEX IF NOT EXISTS idx_cs_extractions_run ON cs_extractions(run_id);
CREATE INDEX IF NOT EXISTS idx_cs_extractions_pmid ON cs_extractions(pmid);
CREATE INDEX IF NOT EXISTS idx_cs_extractions_drug ON cs_extractions(drug_name);
CREATE INDEX IF NOT EXISTS idx_cs_extractions_disease ON cs_extractions(disease);

-- =====================================================
-- MARKET INTELLIGENCE - Cached market data per disease
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_market_intelligence (
    id SERIAL PRIMARY KEY,
    disease VARCHAR(500) NOT NULL UNIQUE,
    prevalence VARCHAR(255),
    prevalence_source VARCHAR(500),
    incidence VARCHAR(255),
    incidence_source VARCHAR(500),
    approved_drugs JSONB DEFAULT '[]',
    treatment_paradigm TEXT,
    unmet_needs TEXT,
    pipeline_drugs JSONB DEFAULT '[]',
    tam_estimate VARCHAR(255),
    tam_source VARCHAR(500),
    tam_growth_rate VARCHAR(100),
    market_dynamics TEXT,
    key_competitors JSONB DEFAULT '[]',
    sources_epidemiology JSONB DEFAULT '[]',
    sources_approved_drugs JSONB DEFAULT '[]',
    sources_treatment JSONB DEFAULT '[]',
    sources_pipeline JSONB DEFAULT '[]',
    sources_tam JSONB DEFAULT '[]',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP + INTERVAL '30 days')
);

CREATE INDEX IF NOT EXISTS idx_cs_market_disease ON cs_market_intelligence(disease);
CREATE INDEX IF NOT EXISTS idx_cs_market_expires ON cs_market_intelligence(expires_at);

-- =====================================================
-- OPPORTUNITIES - Scored repurposing opportunities
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_opportunities (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES cs_analysis_runs(run_id) ON DELETE CASCADE,
    drug_name VARCHAR(255) NOT NULL,
    disease VARCHAR(500) NOT NULL,
    total_patients INT DEFAULT 0,
    paper_count INT DEFAULT 0,
    avg_response_rate DECIMAL(5, 2),
    efficacy_signal VARCHAR(50),
    safety_profile VARCHAR(50),
    evidence_level VARCHAR(50),
    score_efficacy DECIMAL(3, 2),
    score_safety DECIMAL(3, 2),
    score_evidence DECIMAL(3, 2),
    score_market DECIMAL(3, 2),
    score_feasibility DECIMAL(3, 2),
    score_total DECIMAL(4, 2),
    rank INT,
    market_tam VARCHAR(255),
    market_prevalence VARCHAR(255),
    market_unmet_needs TEXT,
    recommendation TEXT,
    key_findings TEXT,
    pmids JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(run_id, drug_name, disease)
);

CREATE INDEX IF NOT EXISTS idx_cs_opportunities_run ON cs_opportunities(run_id);
CREATE INDEX IF NOT EXISTS idx_cs_opportunities_drug ON cs_opportunities(drug_name);
CREATE INDEX IF NOT EXISTS idx_cs_opportunities_disease ON cs_opportunities(disease);
CREATE INDEX IF NOT EXISTS idx_cs_opportunities_score ON cs_opportunities(score_total DESC);

-- =====================================================
-- VIEWS - Useful queries
-- =====================================================

-- Recent runs with summary stats
CREATE OR REPLACE VIEW v_cs_recent_runs AS
SELECT
    run_id,
    drug_name,
    started_at,
    completed_at,
    status,
    papers_found,
    papers_extracted,
    opportunities_found,
    estimated_cost_usd,
    papers_from_cache,
    market_intel_from_cache,
    EXTRACT(EPOCH FROM (completed_at - started_at)) as duration_seconds
FROM cs_analysis_runs
ORDER BY started_at DESC
LIMIT 50;

-- Top opportunities across all runs
CREATE OR REPLACE VIEW v_cs_top_opportunities AS
SELECT
    o.drug_name,
    o.disease,
    o.score_total,
    o.total_patients,
    o.paper_count,
    o.efficacy_signal,
    o.safety_profile,
    o.market_tam,
    r.started_at as run_date
FROM cs_opportunities o
JOIN cs_analysis_runs r ON o.run_id = r.run_id
WHERE r.status = 'completed'
ORDER BY o.score_total DESC
LIMIT 100;

-- Market intelligence cache status
CREATE OR REPLACE VIEW v_cs_market_cache_status AS
SELECT
    disease,
    fetched_at,
    expires_at,
    CASE
        WHEN expires_at > CURRENT_TIMESTAMP THEN 'fresh'
        ELSE 'expired'
    END as cache_status,
    EXTRACT(EPOCH FROM (expires_at - CURRENT_TIMESTAMP)) / 86400 as days_until_expiry
FROM cs_market_intelligence
ORDER BY expires_at;