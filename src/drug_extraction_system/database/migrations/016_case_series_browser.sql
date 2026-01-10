-- Migration 016: Case Series Browser Support
-- Adds drug_id FK and scored_at timestamp to cs_extractions
-- Creates dynamic summary view for drug/disease aggregates

-- Step 1: Add drug_id column to cs_extractions
ALTER TABLE cs_extractions ADD COLUMN IF NOT EXISTS drug_id INT;

-- Step 2: Add scored_at timestamp
ALTER TABLE cs_extractions ADD COLUMN IF NOT EXISTS scored_at TIMESTAMP;

-- Step 3: Create index for drug_id lookups
CREATE INDEX IF NOT EXISTS idx_cs_extractions_drug_id ON cs_extractions(drug_id);

-- Step 4: Create composite index for drug/disease queries
CREATE INDEX IF NOT EXISTS idx_cs_extractions_drug_disease
ON cs_extractions(drug_name, disease);

-- Step 5: Backfill drug_id from drugs table
UPDATE cs_extractions e
SET drug_id = d.drug_id
FROM drugs d
WHERE LOWER(e.drug_name) = LOWER(d.generic_name)
  AND e.drug_id IS NULL;

-- Also try matching brand names
UPDATE cs_extractions e
SET drug_id = d.drug_id
FROM drugs d
WHERE LOWER(e.drug_name) = LOWER(d.brand_name)
  AND e.drug_id IS NULL;

-- Step 6: Set scored_at for records that have scores
UPDATE cs_extractions
SET scored_at = COALESCE(extracted_at, NOW())
WHERE individual_score IS NOT NULL AND scored_at IS NULL;

-- Step 7: Create dynamic summary view
CREATE OR REPLACE VIEW v_cs_drug_disease_summary AS
SELECT
    e.drug_name,
    e.drug_id,
    e.disease,
    e.disease_normalized,
    e.parent_disease,
    COUNT(*) as paper_count,
    SUM(COALESCE(e.n_patients, 0)) as total_patients,

    -- N-weighted aggregate score
    ROUND(
        SUM(COALESCE(e.individual_score, 5.0) * COALESCE(e.n_patients, 1)::numeric) /
        NULLIF(SUM(COALESCE(e.n_patients, 1)), 0),
        2
    ) as aggregate_score,

    -- Best paper info
    MAX(e.individual_score) as best_paper_score,

    -- Average response rate
    ROUND(AVG(e.responders_pct)::numeric, 1) as avg_response_rate,

    -- Dominant efficacy signal
    MODE() WITHIN GROUP (ORDER BY e.efficacy_signal) as efficacy_signal,

    -- Best evidence level (lowest rank = best)
    MIN(CASE e.evidence_level
        WHEN 'RCT' THEN 1
        WHEN 'Randomized Trial' THEN 1
        WHEN 'Controlled Trial' THEN 2
        WHEN 'Meta-Analysis' THEN 2
        WHEN 'Prospective Cohort' THEN 3
        WHEN 'Retrospective Study' THEN 4
        WHEN 'Case Series' THEN 5
        WHEN 'Case Report' THEN 6
        ELSE 7
    END) as evidence_rank,

    -- Best evidence level name
    CASE MIN(CASE e.evidence_level
        WHEN 'RCT' THEN 1
        WHEN 'Randomized Trial' THEN 1
        WHEN 'Controlled Trial' THEN 2
        WHEN 'Meta-Analysis' THEN 2
        WHEN 'Prospective Cohort' THEN 3
        WHEN 'Retrospective Study' THEN 4
        WHEN 'Case Series' THEN 5
        WHEN 'Case Report' THEN 6
        ELSE 7
    END)
        WHEN 1 THEN 'RCT'
        WHEN 2 THEN 'Controlled Trial'
        WHEN 3 THEN 'Prospective Cohort'
        WHEN 4 THEN 'Retrospective Study'
        WHEN 5 THEN 'Case Series'
        WHEN 6 THEN 'Case Report'
        ELSE 'Unknown'
    END as best_evidence_level,

    -- Last scoring timestamp
    MAX(e.scored_at) as last_scored_at,

    -- Last extraction timestamp
    MAX(e.extracted_at) as last_extracted_at

FROM cs_extractions e
WHERE e.is_relevant = true
GROUP BY e.drug_name, e.drug_id, e.disease, e.disease_normalized, e.parent_disease;

-- Step 8: Create drug-level summary view
CREATE OR REPLACE VIEW v_cs_drug_summary AS
SELECT
    drug_name,
    drug_id,
    COUNT(DISTINCT disease) as disease_count,
    SUM(paper_count) as total_papers,
    SUM(total_patients) as total_patients,
    ROUND(AVG(aggregate_score)::numeric, 2) as avg_disease_score,
    MAX(best_paper_score) as top_paper_score,
    MAX(last_scored_at) as last_scored_at,
    MAX(last_extracted_at) as last_extracted_at
FROM v_cs_drug_disease_summary
GROUP BY drug_name, drug_id;

-- Step 9: Create index for faster view queries
CREATE INDEX IF NOT EXISTS idx_cs_extractions_relevant_drug
ON cs_extractions(drug_name, disease)
WHERE is_relevant = true;

COMMENT ON VIEW v_cs_drug_disease_summary IS
'Dynamic aggregates of case series extractions grouped by drug and disease.
Scores are computed from cached individual_score values in cs_extractions.';

COMMENT ON VIEW v_cs_drug_summary IS
'Drug-level summary of case series data for the browser dropdown.';
