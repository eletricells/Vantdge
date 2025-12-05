-- Database schema for extracted research data
-- Supports flexible storage of diverse data types from papers

-- Analysis runs table - tracks each analysis workflow
CREATE TABLE IF NOT EXISTS analysis_runs (
    id VARCHAR(100) PRIMARY KEY,
    user_query TEXT NOT NULL,
    generic_prompt TEXT,
    refined_prompt TEXT,
    refined_search_terms JSONB,  -- Array of search terms
    refined_data_points JSONB,   -- Array of data points to extract
    refined_endpoints JSONB,      -- Array of endpoints
    refined_focus_areas JSONB,    -- Array of focus areas
    selected_papers JSONB,        -- Array of PMIDs selected by user
    analysis_type VARCHAR(50),    -- 'preclinical', 'clinical', etc.
    status VARCHAR(50),           -- 'in_progress', 'completed', 'failed'
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_date TIMESTAMP,
    created_by VARCHAR(100)
);

-- Extracted data points table - flexible structure for all data types
CREATE TABLE IF NOT EXISTS extracted_data_points (
    id SERIAL PRIMARY KEY,
    analysis_id VARCHAR(100) REFERENCES analysis_runs(id),
    paper_pmid VARCHAR(50) NOT NULL,
    paper_doi VARCHAR(100),
    paper_title TEXT,

    -- Data categorization
    analysis_type VARCHAR(50),     -- 'preclinical', 'clinical', etc.
    data_category VARCHAR(100),    -- 'binding_affinity', 'efficacy', 'safety', 'pk', 'pd'
    data_type VARCHAR(100),        -- 'ic50', 'ec50', 'kd', 'cmax', 'auc', etc.

    -- Flexible data storage (JSONB allows any structure)
    data_value JSONB NOT NULL,     -- e.g., {"value": "2.3", "unit": "nM", "ci": "1.8-2.9"}

    -- Experimental context
    experimental_system TEXT,      -- "CHO-K1 cells", "C57BL/6 mice"
    measurement_context TEXT,      -- "TSH-stimulated cAMP production"
    intervention TEXT,             -- "K1-70 at 10 nM", "100 mg/kg daily"

    -- Source tracing
    figure_table_reference VARCHAR(100),  -- "Figure 2A", "Table 3"
    evidence_text TEXT,            -- Raw text snippet from paper
    page_number INTEGER,

    -- Statistical metadata
    sample_size VARCHAR(50),       -- "n=12", "n=45 patients"
    statistical_significance VARCHAR(100),  -- "p<0.001", "p=0.023"

    -- Extraction metadata
    extracted_by VARCHAR(100),     -- 'enhanced_preclinical_agent'
    extraction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confidence_score FLOAT,        -- 0.0 to 1.0

    -- Indexing for fast queries
    CONSTRAINT valid_confidence CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_data_points_analysis ON extracted_data_points(analysis_id);
CREATE INDEX IF NOT EXISTS idx_data_points_pmid ON extracted_data_points(paper_pmid);
CREATE INDEX IF NOT EXISTS idx_data_points_category ON extracted_data_points(data_category);
CREATE INDEX IF NOT EXISTS idx_data_points_type ON extracted_data_points(data_type);
CREATE INDEX IF NOT EXISTS idx_data_points_analysis_type ON extracted_data_points(analysis_type);

-- Paper metadata table (enhanced version)
CREATE TABLE IF NOT EXISTS papers_metadata (
    pmid VARCHAR(50) PRIMARY KEY,
    doi VARCHAR(100),
    title TEXT NOT NULL,
    authors TEXT,
    journal VARCHAR(200),
    year INTEGER,
    abstract TEXT,
    pmcid VARCHAR(50),

    -- Access metadata
    is_open_access BOOLEAN DEFAULT FALSE,
    open_access_url TEXT,
    cached_locally BOOLEAN DEFAULT FALSE,
    cache_path TEXT,

    -- Discovery metadata
    semantic_scholar_id VARCHAR(100),
    relevance_score FLOAT,
    citation_count INTEGER,

    -- Usage tracking
    times_analyzed INTEGER DEFAULT 0,
    first_analyzed TIMESTAMP,
    last_analyzed TIMESTAMP,

    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Analysis findings table - synthesized conclusions
CREATE TABLE IF NOT EXISTS analysis_findings (
    id SERIAL PRIMARY KEY,
    analysis_id VARCHAR(100) REFERENCES analysis_runs(id),
    finding_text TEXT NOT NULL,
    confidence_score FLOAT,

    -- Supporting evidence (references to extracted_data_points)
    supporting_data_points JSONB,  -- Array of data point IDs

    -- Classification
    finding_category VARCHAR(100), -- 'efficacy', 'safety', 'mechanism', etc.
    risk_level VARCHAR(20),        -- 'low', 'medium', 'high'

    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_finding_confidence CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0)
);

-- Paper selection tracking - what papers users chose for analysis
CREATE TABLE IF NOT EXISTS paper_selections (
    id SERIAL PRIMARY KEY,
    analysis_id VARCHAR(100) REFERENCES analysis_runs(id),
    paper_pmid VARCHAR(50),

    -- Selection context
    was_open_access BOOLEAN,
    was_uploaded BOOLEAN,
    relevance_score FLOAT,
    selection_reason TEXT,

    selected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Views for common queries

-- View: All data by analysis
CREATE OR REPLACE VIEW analysis_data_summary AS
SELECT
    ar.id as analysis_id,
    ar.user_query,
    ar.analysis_type,
    COUNT(DISTINCT edp.id) as total_data_points,
    COUNT(DISTINCT edp.paper_pmid) as papers_with_data,
    array_agg(DISTINCT edp.data_category) as data_categories_found,
    AVG(edp.confidence_score) as avg_confidence,
    ar.created_date,
    ar.status
FROM analysis_runs ar
LEFT JOIN extracted_data_points edp ON ar.id = edp.analysis_id
GROUP BY ar.id, ar.user_query, ar.analysis_type, ar.created_date, ar.status;

-- View: Paper usage statistics
CREATE OR REPLACE VIEW paper_usage_stats AS
SELECT
    pm.pmid,
    pm.title,
    pm.journal,
    pm.year,
    pm.times_analyzed,
    COUNT(DISTINCT edp.analysis_id) as analyses_count,
    COUNT(DISTINCT edp.id) as data_points_extracted,
    array_agg(DISTINCT edp.data_type) as data_types_extracted
FROM papers_metadata pm
LEFT JOIN extracted_data_points edp ON pm.pmid = edp.paper_pmid
GROUP BY pm.pmid, pm.title, pm.journal, pm.year, pm.times_analyzed;

-- View: Data type frequency
CREATE OR REPLACE VIEW data_type_frequency AS
SELECT
    data_type,
    data_category,
    COUNT(*) as frequency,
    COUNT(DISTINCT paper_pmid) as papers_count,
    AVG(confidence_score) as avg_confidence
FROM extracted_data_points
GROUP BY data_type, data_category
ORDER BY frequency DESC;

-- Comments for documentation
COMMENT ON TABLE analysis_runs IS 'Tracks each analysis workflow with refined prompts and selected papers';
COMMENT ON TABLE extracted_data_points IS 'Flexible storage for all types of extracted data with JSONB values';
COMMENT ON TABLE papers_metadata IS 'Enhanced paper metadata with access info and usage tracking';
COMMENT ON TABLE analysis_findings IS 'Synthesized conclusions with supporting evidence references';
COMMENT ON TABLE paper_selections IS 'Tracks which papers users selected for each analysis';
