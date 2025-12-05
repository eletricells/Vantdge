-- PaperScope V2 Migration V3: Add Full-Text Content Support
-- This migration adds fields to store full-text content, tables, sections, and metadata
-- to standardize PaperScope v2 papers with PaperScope v1 format

-- 1. Add content field for full-text content (CRITICAL)
ALTER TABLE paperscope_v2_papers 
ADD COLUMN IF NOT EXISTS content TEXT;

COMMENT ON COLUMN paperscope_v2_papers.content IS 'Full-text content from PubMed Central or PDF extraction';

-- 2. Add tables field for extracted tables (HIGH PRIORITY)
ALTER TABLE paperscope_v2_papers 
ADD COLUMN IF NOT EXISTS tables JSONB;

COMMENT ON COLUMN paperscope_v2_papers.tables IS 'Extracted tables in structured format (array of table objects)';

-- 3. Add sections field for structured sections (MEDIUM PRIORITY)
ALTER TABLE paperscope_v2_papers 
ADD COLUMN IF NOT EXISTS sections JSONB;

COMMENT ON COLUMN paperscope_v2_papers.sections IS 'Structured sections (abstract, introduction, methods, results, discussion, conclusions)';

-- 4. Add metadata field for extraction tracking (MEDIUM PRIORITY)
ALTER TABLE paperscope_v2_papers 
ADD COLUMN IF NOT EXISTS metadata JSONB;

COMMENT ON COLUMN paperscope_v2_papers.metadata IS 'Extraction metadata (source, method, open_access, extraction_date, etc.)';

-- 5. Create index on content for full-text search (optional but recommended)
CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_content_search 
ON paperscope_v2_papers USING gin(to_tsvector('english', content));

-- 6. Add index on papers without content (for backfill queries)
CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_content_null 
ON paperscope_v2_papers(pmid) WHERE content IS NULL;

-- Verify migration
DO $$
BEGIN
    -- Check if all columns exist
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'paperscope_v2_papers' 
        AND column_name IN ('content', 'tables', 'sections', 'metadata')
        GROUP BY table_name
        HAVING COUNT(*) = 4
    ) THEN
        RAISE NOTICE 'Migration V3 completed successfully - all columns added';
    ELSE
        RAISE WARNING 'Migration V3 incomplete - some columns may be missing';
    END IF;
END $$;

