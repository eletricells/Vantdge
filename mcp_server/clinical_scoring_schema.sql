-- Clinical Scoring Reference Tables Schema
-- Provides structured reference data for scoring drug repurposing opportunities
-- Part of the Case Series Workflow

-- =====================================================
-- ORGAN DOMAINS - Clinical endpoint keyword mapping
-- =====================================================
-- Maps organ systems to clinical keywords for breadth analysis
CREATE TABLE IF NOT EXISTS cs_organ_domains (
    id SERIAL PRIMARY KEY,
    domain_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cs_organ_domains_name ON cs_organ_domains(domain_name);

-- =====================================================
-- VALIDATED INSTRUMENTS - Clinical endpoint quality scores
-- =====================================================
-- Stores validated clinical instruments with quality scores by disease
CREATE TABLE IF NOT EXISTS cs_validated_instruments (
    id SERIAL PRIMARY KEY,
    disease_key VARCHAR(100) NOT NULL,
    disease_aliases TEXT[] DEFAULT '{}',
    instrument_name VARCHAR(255) NOT NULL,
    quality_score INT NOT NULL CHECK (quality_score >= 1 AND quality_score <= 10),
    instrument_type VARCHAR(100),  -- 'composite', 'patient_reported', 'clinician_reported', 'biomarker', 'imaging'
    regulatory_acceptance BOOLEAN DEFAULT FALSE,  -- FDA/EMA accepted as endpoint
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(disease_key, instrument_name)
);

CREATE INDEX IF NOT EXISTS idx_cs_instruments_disease ON cs_validated_instruments(disease_key);
CREATE INDEX IF NOT EXISTS idx_cs_instruments_name ON cs_validated_instruments(instrument_name);
CREATE INDEX IF NOT EXISTS idx_cs_instruments_score ON cs_validated_instruments(quality_score DESC);

-- =====================================================
-- SAFETY SIGNAL CATEGORIES - MedDRA-aligned classification
-- =====================================================
-- Categorizes adverse events for safety scoring
CREATE TABLE IF NOT EXISTS cs_safety_categories (
    id SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    keywords TEXT[] NOT NULL DEFAULT '{}',
    severity_weight INT NOT NULL CHECK (severity_weight >= 1 AND severity_weight <= 10),
    regulatory_flag BOOLEAN DEFAULT FALSE,  -- Known regulatory concern for immunomodulators
    meddra_soc VARCHAR(255),  -- MedDRA System Organ Class alignment
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cs_safety_category ON cs_safety_categories(category_name);
CREATE INDEX IF NOT EXISTS idx_cs_safety_severity ON cs_safety_categories(severity_weight DESC);

-- =====================================================
-- INSTRUMENT CACHE - LLM-discovered instruments
-- =====================================================
-- Caches validated instruments discovered via LLM lookup for diseases not in database
CREATE TABLE IF NOT EXISTS cs_instrument_cache (
    id SERIAL PRIMARY KEY,
    disease_name VARCHAR(500) NOT NULL,
    disease_normalized VARCHAR(255) NOT NULL UNIQUE,
    instruments JSONB NOT NULL DEFAULT '{}',  -- {instrument_name: quality_score}
    source VARCHAR(50) DEFAULT 'llm',  -- 'llm', 'manual', 'imported'
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cs_instrument_cache_disease ON cs_instrument_cache(disease_normalized);

-- =====================================================
-- SCORING WEIGHTS - Configurable weights by therapeutic area
-- =====================================================
-- Allows different scoring weights for different therapeutic areas
CREATE TABLE IF NOT EXISTS cs_scoring_weights (
    id SERIAL PRIMARY KEY,
    therapeutic_area VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    -- Clinical signal component weights (should sum to 1.0)
    weight_response_rate DECIMAL(3,2) DEFAULT 0.30,
    weight_safety DECIMAL(3,2) DEFAULT 0.30,
    weight_endpoint_quality DECIMAL(3,2) DEFAULT 0.25,
    weight_organ_breadth DECIMAL(3,2) DEFAULT 0.15,
    -- Dimension weights (should sum to 1.0)
    weight_clinical DECIMAL(3,2) DEFAULT 0.50,
    weight_evidence DECIMAL(3,2) DEFAULT 0.25,
    weight_market DECIMAL(3,2) DEFAULT 0.25,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =====================================================
-- HELPER VIEWS
-- =====================================================

-- View: Instruments by disease with aliases
CREATE OR REPLACE VIEW v_cs_instruments_by_disease AS
SELECT 
    disease_key,
    disease_aliases,
    COUNT(*) as instrument_count,
    AVG(quality_score) as avg_quality_score,
    array_agg(instrument_name ORDER BY quality_score DESC) as instruments
FROM cs_validated_instruments
GROUP BY disease_key, disease_aliases;

-- View: Safety categories with keyword counts
CREATE OR REPLACE VIEW v_cs_safety_overview AS
SELECT 
    category_name,
    severity_weight,
    regulatory_flag,
    array_length(keywords, 1) as keyword_count,
    meddra_soc
FROM cs_safety_categories
ORDER BY severity_weight DESC;

-- View: Organ domains with keyword counts
CREATE OR REPLACE VIEW v_cs_organ_domain_overview AS
SELECT 
    domain_name,
    description,
    array_length(keywords, 1) as keyword_count
FROM cs_organ_domains
ORDER BY domain_name;

