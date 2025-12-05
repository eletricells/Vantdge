-- PaperScope V2 Database Schema
-- Stores comprehensive paper catalogs with web search results, detailed summaries, and ongoing trials

-- Drop existing tables (if recreating)
-- DROP TABLE IF EXISTS paperscope_v2_ongoing_trials CASCADE;
-- DROP TABLE IF EXISTS paperscope_v2_papers CASCADE;
-- DROP TABLE IF EXISTS paperscope_v2_searches CASCADE;

-- Drug searches table
CREATE TABLE IF NOT EXISTS paperscope_v2_searches (
    search_id SERIAL PRIMARY KEY,
    drug_name VARCHAR(255) NOT NULL,
    disease_indication VARCHAR(500),
    drug_class VARCHAR(255),
    search_date TIMESTAMP DEFAULT NOW(),
    total_papers INTEGER,
    total_ongoing_trials INTEGER,
    paper_sources JSONB,
    elapsed_seconds NUMERIC,
    search_log JSONB,
    UNIQUE(drug_name, search_date)
);

-- Papers table
CREATE TABLE IF NOT EXISTS paperscope_v2_papers (
    paper_id SERIAL PRIMARY KEY,
    search_id INTEGER REFERENCES paperscope_v2_searches(search_id) ON DELETE CASCADE,
    pmid VARCHAR(50),
    title TEXT NOT NULL,
    authors TEXT,
    journal VARCHAR(500),
    year INTEGER,
    abstract TEXT,
    detailed_summary TEXT,
    key_takeaways JSONB,
    categories JSONB,
    source VARCHAR(100),
    links JSONB,
    primary_link TEXT,
    doi VARCHAR(255),
    pmc VARCHAR(50),
    trial_name VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index on pmid for faster lookups
CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_pmid 
ON paperscope_v2_papers(pmid);

-- Create index on search_id for faster joins
CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_search_id 
ON paperscope_v2_papers(search_id);

-- Ongoing trials table
CREATE TABLE IF NOT EXISTS paperscope_v2_ongoing_trials (
    trial_id SERIAL PRIMARY KEY,
    search_id INTEGER REFERENCES paperscope_v2_searches(search_id) ON DELETE CASCADE,
    nct_id VARCHAR(50) NOT NULL,
    title TEXT,
    phase VARCHAR(50),
    status VARCHAR(100),
    enrollment INTEGER,
    start_date DATE,
    completion_date DATE,
    primary_completion_date DATE,
    conditions JSONB,
    interventions JSONB,
    url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index on nct_id
CREATE INDEX IF NOT EXISTS idx_paperscope_v2_ongoing_trials_nct_id 
ON paperscope_v2_ongoing_trials(nct_id);

-- Comments for documentation
COMMENT ON TABLE paperscope_v2_searches IS 'Stores metadata about each PaperScope V2 search';
COMMENT ON TABLE paperscope_v2_papers IS 'Stores papers with detailed summaries and categorization';
COMMENT ON TABLE paperscope_v2_ongoing_trials IS 'Stores ongoing/recruiting trials from ClinicalTrials.gov';

COMMENT ON COLUMN paperscope_v2_searches.drug_name IS 'Generic drug name';
COMMENT ON COLUMN paperscope_v2_searches.disease_indication IS 'Auto-detected disease indication';
COMMENT ON COLUMN paperscope_v2_searches.drug_class IS 'Auto-detected drug class (e.g., Monoclonal Antibody)';
COMMENT ON COLUMN paperscope_v2_searches.paper_sources IS 'JSON object tracking paper sources (pubmed, bioRxiv, etc.)';
COMMENT ON COLUMN paperscope_v2_searches.search_log IS 'JSON array of all searches performed';

COMMENT ON COLUMN paperscope_v2_papers.detailed_summary IS '3-4 sentence summary with study design, endpoints, p-values';
COMMENT ON COLUMN paperscope_v2_papers.key_takeaways IS 'JSON array of 2-3 key takeaways';
COMMENT ON COLUMN paperscope_v2_papers.categories IS 'JSON array of categories (multi-label classification)';
COMMENT ON COLUMN paperscope_v2_papers.source IS 'Paper source (pubmed, bioRxiv, medRxiv, conference_abstract, etc.)';
COMMENT ON COLUMN paperscope_v2_papers.links IS 'JSON array of all available links (PubMed, PMC, DOI, journal)';
COMMENT ON COLUMN paperscope_v2_papers.primary_link IS 'Primary/preferred link to paper';

COMMENT ON COLUMN paperscope_v2_ongoing_trials.nct_id IS 'ClinicalTrials.gov NCT ID';
COMMENT ON COLUMN paperscope_v2_ongoing_trials.conditions IS 'JSON array of conditions/diseases';
COMMENT ON COLUMN paperscope_v2_ongoing_trials.interventions IS 'JSON array of interventions/drugs';

