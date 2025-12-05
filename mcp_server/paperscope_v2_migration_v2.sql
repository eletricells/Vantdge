-- PaperScope V2 Schema Migration - Version 2
-- Adds deduplication, structured summaries, and drug relevance filtering

-- 1. Add unique constraint to prevent duplicate papers per search
-- First, remove any existing duplicates (keep the first occurrence)
DELETE FROM paperscope_v2_papers a USING paperscope_v2_papers b
WHERE a.paper_id > b.paper_id 
  AND a.search_id = b.search_id 
  AND a.pmid = b.pmid
  AND a.pmid IS NOT NULL;

-- Now add the unique constraint
ALTER TABLE paperscope_v2_papers 
DROP CONSTRAINT IF EXISTS unique_paper_per_search;

ALTER TABLE paperscope_v2_papers 
ADD CONSTRAINT unique_paper_per_search UNIQUE (search_id, pmid);

-- 2. Add structured_summary field for structured data extraction
ALTER TABLE paperscope_v2_papers 
ADD COLUMN IF NOT EXISTS structured_summary JSONB;

COMMENT ON COLUMN paperscope_v2_papers.structured_summary IS 'Structured summary with phase, indication, population, results, safety';

-- 3. Add drug_relevance_score for filtering
ALTER TABLE paperscope_v2_papers 
ADD COLUMN IF NOT EXISTS drug_relevance_score NUMERIC(3,2);

COMMENT ON COLUMN paperscope_v2_papers.drug_relevance_score IS 'Drug relevance score (0.0-1.0) from Claude filtering';

-- 4. Add updated_at timestamp for tracking updates
ALTER TABLE paperscope_v2_papers 
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- 5. Create index on trial_name for faster lookups
CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_trial_name 
ON paperscope_v2_papers(trial_name);

-- 6. Create index on drug_relevance_score for filtering
CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_relevance 
ON paperscope_v2_papers(drug_relevance_score);

-- 7. Add discovered_trial_names to searches table
ALTER TABLE paperscope_v2_searches 
ADD COLUMN IF NOT EXISTS discovered_trial_names JSONB;

COMMENT ON COLUMN paperscope_v2_searches.discovered_trial_names IS 'Trial names discovered via web search in Phase 0';

-- 8. Add filtered_papers_count to track how many papers were filtered out
ALTER TABLE paperscope_v2_searches 
ADD COLUMN IF NOT EXISTS filtered_papers_count INTEGER DEFAULT 0;

COMMENT ON COLUMN paperscope_v2_searches.filtered_papers_count IS 'Number of papers filtered out due to low drug relevance';

-- Verify migration
SELECT 
    'Migration complete!' as status,
    COUNT(*) as total_papers,
    COUNT(DISTINCT pmid) as unique_pmids,
    COUNT(structured_summary) as papers_with_structured_summary,
    COUNT(drug_relevance_score) as papers_with_relevance_score
FROM paperscope_v2_papers;

