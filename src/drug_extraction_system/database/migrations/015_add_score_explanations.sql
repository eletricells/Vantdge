-- Migration 015: Add score explanations and disease hierarchy support
-- For case series analysis drill-down feature

-- =====================================================
-- NEW TABLE: Score Explanations
-- Stores pre-generated Claude explanations for score transparency
-- =====================================================
CREATE TABLE IF NOT EXISTS cs_score_explanations (
    id SERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    drug_name VARCHAR(255) NOT NULL,
    disease VARCHAR(500) NOT NULL,
    parent_disease VARCHAR(500),  -- NULL if this IS the parent disease

    -- Aggregate-level explanation (for disease summary)
    aggregate_explanation TEXT,  -- 2-3 paragraph Claude-generated narrative
    explanation_model VARCHAR(50) DEFAULT 'claude-3-haiku',  -- Model used

    -- Input data used for generation (for debugging/regeneration)
    input_summary JSONB,  -- Contains aggregate scores, paper summaries

    -- Metadata
    generated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    generation_tokens INTEGER,  -- Tokens used for generation

    UNIQUE(run_id, drug_name, disease)
);

-- Indexes for efficient retrieval
CREATE INDEX IF NOT EXISTS idx_cs_score_explanations_run
ON cs_score_explanations(run_id);

CREATE INDEX IF NOT EXISTS idx_cs_score_explanations_drug_disease
ON cs_score_explanations(drug_name, LOWER(disease));

CREATE INDEX IF NOT EXISTS idx_cs_score_explanations_parent
ON cs_score_explanations(parent_disease) WHERE parent_disease IS NOT NULL;


-- =====================================================
-- MODIFY: cs_opportunities
-- Add parent disease for hierarchy display
-- =====================================================
ALTER TABLE cs_opportunities
ADD COLUMN IF NOT EXISTS parent_disease VARCHAR(500);

ALTER TABLE cs_opportunities
ADD COLUMN IF NOT EXISTS disease_normalized VARCHAR(500);

-- Index for parent-child grouping
CREATE INDEX IF NOT EXISTS idx_cs_opportunities_parent_disease
ON cs_opportunities(parent_disease) WHERE parent_disease IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cs_opportunities_normalized
ON cs_opportunities(LOWER(disease_normalized));


-- =====================================================
-- MODIFY: cs_extractions
-- Add parent disease and per-paper score explanation
-- =====================================================
ALTER TABLE cs_extractions
ADD COLUMN IF NOT EXISTS parent_disease VARCHAR(500);

-- Brief 2-3 sentence explanation for this specific paper
ALTER TABLE cs_extractions
ADD COLUMN IF NOT EXISTS score_explanation TEXT;

-- Index for parent grouping on extractions
CREATE INDEX IF NOT EXISTS idx_cs_extractions_parent_disease
ON cs_extractions(parent_disease) WHERE parent_disease IS NOT NULL;


-- =====================================================
-- VIEW: Hierarchical disease opportunities
-- Provides parent-child structure for UI display
-- =====================================================
CREATE OR REPLACE VIEW v_cs_hierarchical_opportunities AS
WITH parent_aggregates AS (
    SELECT
        run_id,
        drug_name,
        COALESCE(parent_disease, disease) AS parent_disease,
        COUNT(*) AS child_count,
        SUM(total_patients) AS total_patients,
        SUM(study_count) AS total_studies,
        AVG(score_total) AS avg_score,
        MAX(score_total) AS best_score,
        STRING_AGG(DISTINCT disease, ', ') AS child_diseases
    FROM cs_opportunities
    GROUP BY run_id, drug_name, COALESCE(parent_disease, disease)
)
SELECT
    pa.*,
    o.disease AS child_disease,
    o.score_total AS child_score,
    o.study_count AS child_study_count,
    o.total_patients AS child_patient_count,
    e.aggregate_explanation,
    CASE WHEN o.parent_disease IS NOT NULL THEN TRUE ELSE FALSE END AS is_child
FROM parent_aggregates pa
LEFT JOIN cs_opportunities o
    ON o.run_id = pa.run_id
    AND o.drug_name = pa.drug_name
    AND COALESCE(o.parent_disease, o.disease) = pa.parent_disease
LEFT JOIN cs_score_explanations e
    ON e.run_id = pa.run_id
    AND e.drug_name = pa.drug_name
    AND e.disease = pa.parent_disease
ORDER BY pa.run_id, pa.drug_name, pa.avg_score DESC, o.score_total DESC;
