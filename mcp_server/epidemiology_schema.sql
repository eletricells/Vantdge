-- Epidemiology Module Database Schema
-- Stores comprehensive epidemiological data for market sizing and precision medicine opportunities
-- Supports incremental updates and smart caching

-- =============================================================================
-- MAIN ANALYSIS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS epidemiology_analyses (
    analysis_id SERIAL PRIMARY KEY,
    disease_name VARCHAR(500) NOT NULL,
    disease_normalized VARCHAR(500),
    icd10_codes JSONB,  -- ["E05.00", "E05.01"]
    
    -- Prevalence data with ranges (NULL if not searched for that region)
    -- US (using DECIMAL to support fractional rates like 21.4 per 100,000)
    prevalence_us_min DECIMAL(10,2),
    prevalence_us_max DECIMAL(10,2),
    prevalence_us_best_estimate DECIMAL(10,2),
    prevalence_us_year INTEGER,  -- Year of data
    prevalence_us_confidence VARCHAR(20),  -- HIGH, MEDIUM, LOW
    prevalence_us_diagnosed_pct DECIMAL(5,2),  -- % diagnosed (Option 3)

    -- EU5
    prevalence_eu5_min DECIMAL(10,2),
    prevalence_eu5_max DECIMAL(10,2),
    prevalence_eu5_best_estimate DECIMAL(10,2),
    prevalence_eu5_year INTEGER,
    prevalence_eu5_confidence VARCHAR(20),
    prevalence_eu5_diagnosed_pct DECIMAL(5,2),

    -- Global
    prevalence_global_min DECIMAL(10,2),
    prevalence_global_max DECIMAL(10,2),
    prevalence_global_best_estimate DECIMAL(10,2),
    prevalence_global_year INTEGER,
    prevalence_global_confidence VARCHAR(20),
    prevalence_global_diagnosed_pct DECIMAL(5,2),

    -- Japan
    prevalence_japan_min DECIMAL(10,2),
    prevalence_japan_max DECIMAL(10,2),
    prevalence_japan_best_estimate DECIMAL(10,2),
    prevalence_japan_year INTEGER,
    prevalence_japan_confidence VARCHAR(20),
    prevalence_japan_diagnosed_pct DECIMAL(5,2),

    -- China
    prevalence_china_min DECIMAL(10,2),
    prevalence_china_max DECIMAL(10,2),
    prevalence_china_best_estimate DECIMAL(10,2),
    prevalence_china_year INTEGER,
    prevalence_china_confidence VARCHAR(20),
    prevalence_china_diagnosed_pct DECIMAL(5,2),

    -- Incidence data (Option 3 - expanded for all regions)
    incidence_us_per_100k DECIMAL(10,2),
    incidence_us_annual INTEGER,
    incidence_us_year INTEGER,
    incidence_us_confidence VARCHAR(20),

    incidence_eu5_per_100k DECIMAL(10,2),
    incidence_eu5_annual INTEGER,
    incidence_eu5_year INTEGER,
    incidence_eu5_confidence VARCHAR(20),

    incidence_global_per_100k DECIMAL(10,2),
    incidence_global_annual INTEGER,
    incidence_global_year INTEGER,
    incidence_global_confidence VARCHAR(20),

    incidence_japan_per_100k DECIMAL(10,2),
    incidence_japan_annual INTEGER,
    incidence_japan_year INTEGER,
    incidence_japan_confidence VARCHAR(20),

    incidence_china_per_100k DECIMAL(10,2),
    incidence_china_annual INTEGER,
    incidence_china_year INTEGER,
    incidence_china_confidence VARCHAR(20),
    
    -- Overall quality metrics
    data_quality_score DECIMAL(3,2),  -- 0.0 to 1.0
    confidence_level VARCHAR(20),  -- HIGH, MEDIUM, LOW
    data_gaps TEXT[],  -- ["No China data available", "EU5 estimates outdated"]
    data_quality_flags JSONB,  -- Option 3: Quality issues identified during validation

    -- Segmentation summary
    segmentation_summary TEXT,
    precision_medicine_opportunities TEXT,

    -- Market sizing
    addressable_market_us INTEGER,
    addressable_market_global INTEGER,
    market_sizing_assumptions TEXT,

    -- Cost tracking (Option 1)
    api_tokens_used INTEGER DEFAULT 0,
    estimated_api_cost DECIMAL(10,4) DEFAULT 0.0,

    -- Metadata
    regions_searched VARCHAR(50)[],  -- ["US", "EU5", "Global"]
    search_date TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    search_phases_completed INTEGER,
    total_searches_performed INTEGER,

    -- Allow multiple analyses per disease (for re-runs)
    created_at TIMESTAMP DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_epi_disease ON epidemiology_analyses(disease_normalized);
CREATE INDEX IF NOT EXISTS idx_epi_search_date ON epidemiology_analyses(search_date DESC);

-- =============================================================================
-- SOURCE-LEVEL PREVALENCE ESTIMATES TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS epidemiology_source_prevalence (
    source_prevalence_id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES epidemiology_analyses(analysis_id) ON DELETE CASCADE,

    -- Geography
    geography VARCHAR(50) NOT NULL,  -- US, EU5, Global, Japan, China

    -- Source information
    source_title TEXT NOT NULL,
    source_url TEXT,
    source_type VARCHAR(50),  -- pubmed, cdc, who, nih, guideline, registry, company_presentation, other

    -- Prevalence estimates from this specific source
    min_estimate DECIMAL(10,2),
    max_estimate DECIMAL(10,2),
    best_estimate DECIMAL(10,2),
    year INTEGER,
    confidence VARCHAR(20),  -- HIGH, MEDIUM, LOW
    diagnosed_percentage DECIMAL(5,2),  -- Option 3: % diagnosed
    quality_score DECIMAL(3,2),  -- Option 1: Source quality score (0.0-1.0)

    -- Additional context
    notes TEXT,  -- Methodology notes, population specifics, etc.

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_prev_analysis ON epidemiology_source_prevalence(analysis_id);
CREATE INDEX IF NOT EXISTS idx_source_prev_geography ON epidemiology_source_prevalence(geography);

-- =============================================================================
-- PATIENT SEGMENTATION TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS epidemiology_patient_segments (
    segment_id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES epidemiology_analyses(analysis_id) ON DELETE CASCADE,
    
    -- Segmentation hierarchy (supports nested segments)
    segmentation_type VARCHAR(100),  -- "severity", "subtype", "biomarker", "age", "geography"
    parent_segment_id INTEGER REFERENCES epidemiology_patient_segments(segment_id),
    segment_level INTEGER DEFAULT 1,  -- 1 = top level, 2 = child, 3 = grandchild, etc.
    
    -- Segment details
    segment_name VARCHAR(255) NOT NULL,
    segment_description TEXT,
    
    -- Population estimates (with ranges)
    patient_count_min INTEGER,
    patient_count_max INTEGER,
    patient_count_best_estimate INTEGER,
    percentage_of_total DECIMAL(5,2),
    data_year INTEGER,  -- Year of data
    
    -- Geography (if segment is region-specific)
    geography VARCHAR(50),  -- "US", "EU5", "Global", NULL for all regions
    
    -- Quality metrics
    confidence_score DECIMAL(3,2),  -- 0.0 to 1.0
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_epi_segments_analysis ON epidemiology_patient_segments(analysis_id);
CREATE INDEX IF NOT EXISTS idx_epi_segments_parent ON epidemiology_patient_segments(parent_segment_id);
CREATE INDEX IF NOT EXISTS idx_epi_segments_type ON epidemiology_patient_segments(segmentation_type);

-- =============================================================================
-- BIOMARKER TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS epidemiology_biomarkers (
    biomarker_id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES epidemiology_analyses(analysis_id) ON DELETE CASCADE,
    
    -- Biomarker details
    biomarker_name VARCHAR(255) NOT NULL,
    biomarker_type VARCHAR(100),  -- "genetic", "protein", "imaging", "clinical", "composite"
    biomarker_category VARCHAR(100),  -- "diagnostic", "prognostic", "predictive", "pharmacodynamic"
    
    -- Clinical context
    prevalence_in_population DECIMAL(5,2),  -- % of patients with this biomarker
    clinical_significance TEXT,
    treatment_implications TEXT,
    data_year INTEGER,  -- Year of data
    
    -- Precision medicine potential
    companion_diagnostic_exists BOOLEAN DEFAULT FALSE,
    
    -- Evidence quality
    evidence_strength VARCHAR(20),  -- "STRONG", "MODERATE", "WEAK"
    confidence_score DECIMAL(3,2),  -- 0.0 to 1.0
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_epi_biomarkers_analysis ON epidemiology_biomarkers(analysis_id);
CREATE INDEX IF NOT EXISTS idx_epi_biomarkers_name ON epidemiology_biomarkers(biomarker_name);

-- Junction table: Biomarkers to Segments (many-to-many)
CREATE TABLE IF NOT EXISTS epidemiology_biomarker_segments (
    biomarker_id INTEGER NOT NULL REFERENCES epidemiology_biomarkers(biomarker_id) ON DELETE CASCADE,
    segment_id INTEGER NOT NULL REFERENCES epidemiology_patient_segments(segment_id) ON DELETE CASCADE,
    PRIMARY KEY (biomarker_id, segment_id)
);

-- =============================================================================
-- SOURCE CITATIONS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS epidemiology_sources (
    source_id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES epidemiology_analyses(analysis_id) ON DELETE CASCADE,
    
    -- Source metadata
    source_type VARCHAR(50),  -- "pubmed", "cdc", "who", "nih", "company_presentation", "registry", "guideline"
    title TEXT NOT NULL,
    authors TEXT,
    publication_year INTEGER,
    journal VARCHAR(255),
    url TEXT,
    pmid VARCHAR(20),
    doi VARCHAR(100),
    
    -- Quality assessment
    source_quality_tier INTEGER CHECK (source_quality_tier BETWEEN 1 AND 5),  -- 1 = highest, 5 = lowest
    peer_reviewed BOOLEAN DEFAULT FALSE,
    
    -- Content
    relevant_excerpt TEXT,
    data_points_extracted JSONB,  -- {"prevalence_us": 1000000, "year": 2024}
    
    -- What this source supports
    supports_prevalence BOOLEAN DEFAULT FALSE,
    supports_segmentation BOOLEAN DEFAULT FALSE,
    supports_biomarkers BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Prevent duplicate sources
    UNIQUE(analysis_id, url)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_epi_sources_analysis ON epidemiology_sources(analysis_id);
CREATE INDEX IF NOT EXISTS idx_epi_sources_type ON epidemiology_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_epi_sources_quality ON epidemiology_sources(source_quality_tier);

-- =============================================================================
-- SEARCH LOG TABLE (for transparency and debugging)
-- =============================================================================

CREATE TABLE IF NOT EXISTS epidemiology_search_log (
    log_id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES epidemiology_analyses(analysis_id) ON DELETE CASCADE,
    
    -- Search details
    search_phase INTEGER,  -- 1 = prevalence, 2 = segmentation, 3 = biomarkers, 4 = validation
    search_query TEXT NOT NULL,
    search_purpose VARCHAR(255),
    regions_targeted VARCHAR(50)[],  -- ["US", "EU5"]
    
    -- Results
    results_found INTEGER,
    new_sources_added INTEGER,
    
    -- Metadata
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Index
CREATE INDEX IF NOT EXISTS idx_epi_search_log_analysis ON epidemiology_search_log(analysis_id);

-- =============================================================================
-- HELPER VIEWS
-- =============================================================================

-- View: Latest analysis per disease
CREATE OR REPLACE VIEW epidemiology_latest_analyses AS
SELECT DISTINCT ON (disease_normalized)
    analysis_id,
    disease_name,
    disease_normalized,
    prevalence_us_best_estimate,
    prevalence_global_best_estimate,
    confidence_level,
    search_date,
    regions_searched
FROM epidemiology_analyses
ORDER BY disease_normalized, search_date DESC;

-- View: Biomarkers with segment associations
CREATE OR REPLACE VIEW epidemiology_biomarkers_with_segments AS
SELECT 
    b.biomarker_id,
    b.analysis_id,
    b.biomarker_name,
    b.biomarker_type,
    b.biomarker_category,
    b.prevalence_in_population,
    b.evidence_strength,
    ARRAY_AGG(s.segment_name) FILTER (WHERE s.segment_name IS NOT NULL) as associated_segments
FROM epidemiology_biomarkers b
LEFT JOIN epidemiology_biomarker_segments bs ON b.biomarker_id = bs.biomarker_id
LEFT JOIN epidemiology_patient_segments s ON bs.segment_id = s.segment_id
GROUP BY b.biomarker_id, b.analysis_id, b.biomarker_name, b.biomarker_type, 
         b.biomarker_category, b.prevalence_in_population, b.evidence_strength;

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE epidemiology_analyses IS 'Main table storing epidemiological analyses for diseases';
COMMENT ON TABLE epidemiology_patient_segments IS 'Hierarchical patient segmentation data';
COMMENT ON TABLE epidemiology_biomarkers IS 'Biomarkers for patient stratification and precision medicine';
COMMENT ON TABLE epidemiology_sources IS 'Source citations with quality tiers';
COMMENT ON TABLE epidemiology_search_log IS 'Search history for transparency and debugging';
COMMENT ON COLUMN epidemiology_sources.source_quality_tier IS '1=CDC/WHO/NIH, 2=Peer-reviewed, 3=Company/Conference, 4=Market research, 5=News/blogs';

