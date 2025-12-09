-- Migration: Increase precision for score fields in cs_opportunities table
-- Date: 2025-12-09
-- Reason: Score values can exceed 10.0, but NUMERIC(3,2) only allows -9.99 to 9.99

-- Increase precision for individual score fields from NUMERIC(3,2) to NUMERIC(5,2)
-- This allows values from -999.99 to 999.99
ALTER TABLE cs_opportunities
    ALTER COLUMN score_efficacy TYPE NUMERIC(5, 2),
    ALTER COLUMN score_safety TYPE NUMERIC(5, 2),
    ALTER COLUMN score_evidence TYPE NUMERIC(5, 2),
    ALTER COLUMN score_market TYPE NUMERIC(5, 2),
    ALTER COLUMN score_feasibility TYPE NUMERIC(5, 2);

-- Drop view that depends on score_total column
DROP VIEW IF EXISTS v_cs_top_opportunities;

-- Increase precision for total score from NUMERIC(4,2) to NUMERIC(6,2)
-- This allows values from -9999.99 to 9999.99
ALTER TABLE cs_opportunities
    ALTER COLUMN score_total TYPE NUMERIC(6, 2);

-- Recreate the view with updated column type
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

-- Verify the changes
SELECT 
    column_name, 
    data_type, 
    numeric_precision, 
    numeric_scale
FROM information_schema.columns
WHERE table_name = 'cs_opportunities' 
    AND column_name LIKE 'score_%'
ORDER BY column_name;

