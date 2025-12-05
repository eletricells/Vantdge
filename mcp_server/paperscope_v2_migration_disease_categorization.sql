-- PaperScope V2 Migration: Disease-Based Categorization
-- Adds support for grouping papers by disease/indication

-- 1. Add indication field to papers table
ALTER TABLE paperscope_v2_papers 
ADD COLUMN IF NOT EXISTS indication VARCHAR(500);

COMMENT ON COLUMN paperscope_v2_papers.indication IS 'Normalized disease/indication name extracted from paper (e.g., "Plaque Psoriasis", "Atopic Dermatitis")';

-- Create index for fast filtering by indication
CREATE INDEX IF NOT EXISTS idx_papers_indication 
ON paperscope_v2_papers(indication);

-- 2. Add discovered_indications field to searches table
ALTER TABLE paperscope_v2_searches 
ADD COLUMN IF NOT EXISTS discovered_indications JSONB;

COMMENT ON COLUMN paperscope_v2_searches.discovered_indications IS 'List of all indications discovered from ClinicalTrials.gov during Phase 0 (e.g., ["Plaque Psoriasis", "Atopic Dermatitis", "Vitiligo"])';

-- Verify changes
SELECT 
    column_name, 
    data_type, 
    character_maximum_length,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'paperscope_v2_papers' 
AND column_name = 'indication';

SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'paperscope_v2_searches' 
AND column_name = 'discovered_indications';

-- Show indexes
SELECT 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE tablename = 'paperscope_v2_papers' 
AND indexname = 'idx_papers_indication';

