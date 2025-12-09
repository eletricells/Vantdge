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
    score_efficacy DECIMAL(5, 2),
    score_safety DECIMAL(5, 2),
    score_evidence DECIMAL(5, 2),
    score_market DECIMAL(5, 2),
    score_feasibility DECIMAL(5, 2),
    score_total DECIMAL(6, 2),
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

-- =====================================================
-- DISEASE NAME VARIANTS - Alternative names/abbreviations for diseases
-- Used to improve search coverage when querying ClinicalTrials.gov, etc.
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_disease_name_variants (
    id SERIAL PRIMARY KEY,
    canonical_name VARCHAR(500) NOT NULL,
    variant_name VARCHAR(500) NOT NULL,
    variant_type VARCHAR(50) DEFAULT 'abbreviation',  -- abbreviation, synonym, alternate_spelling, common_name
    source VARCHAR(255),  -- Where this mapping came from (manual, MeSH, ICD-10, SNOMED)
    confidence DECIMAL(3, 2) DEFAULT 1.0,  -- 0.0-1.0 confidence in mapping
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system',
    UNIQUE(canonical_name, variant_name)
);

CREATE INDEX IF NOT EXISTS idx_cs_variants_canonical ON cs_disease_name_variants(LOWER(canonical_name));
CREATE INDEX IF NOT EXISTS idx_cs_variants_variant ON cs_disease_name_variants(LOWER(variant_name));

-- =====================================================
-- DISEASE PARENT MAPPINGS - Maps specific subtypes to parent diseases
-- Used to aggregate market intelligence at the parent disease level
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_disease_parent_mappings (
    id SERIAL PRIMARY KEY,
    specific_name VARCHAR(500) NOT NULL UNIQUE,
    parent_name VARCHAR(500) NOT NULL,
    relationship_type VARCHAR(50) DEFAULT 'subtype',  -- subtype, variant, refractory, pediatric
    source VARCHAR(255),  -- Where this mapping came from
    confidence DECIMAL(3, 2) DEFAULT 1.0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) DEFAULT 'system'
);

CREATE INDEX IF NOT EXISTS idx_cs_parent_specific ON cs_disease_parent_mappings(LOWER(specific_name));
CREATE INDEX IF NOT EXISTS idx_cs_parent_parent ON cs_disease_parent_mappings(LOWER(parent_name));

-- View: All disease variants with their canonical names
CREATE OR REPLACE VIEW v_cs_disease_variants AS
SELECT
    canonical_name,
    ARRAY_AGG(variant_name ORDER BY confidence DESC, variant_name) as variants,
    COUNT(*) as variant_count
FROM cs_disease_name_variants
GROUP BY canonical_name
ORDER BY canonical_name;

-- View: Disease hierarchy showing parent-child relationships
CREATE OR REPLACE VIEW v_cs_disease_hierarchy AS
SELECT
    parent_name,
    ARRAY_AGG(specific_name ORDER BY specific_name) as subtypes,
    COUNT(*) as subtype_count
FROM cs_disease_parent_mappings
GROUP BY parent_name
ORDER BY parent_name;