-- Migration 019: Add workflow tracking tables for Disease Analysis page
-- These tables track workflow runs and flag data conflicts for review

-- Workflow run tracking table (extends existing pipeline_runs with unified view)
CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id SERIAL PRIMARY KEY,
    disease_name VARCHAR(255) NOT NULL,
    therapeutic_area VARCHAR(100),
    workflow_type VARCHAR(50) NOT NULL,  -- 'pipeline_intelligence', 'disease_intelligence'
    run_mode VARCHAR(20) NOT NULL DEFAULT 'full',  -- 'full', 'incremental'
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed'
    started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP WITH TIME ZONE,
    -- Results summary
    items_found INTEGER DEFAULT 0,
    items_new INTEGER DEFAULT 0,
    items_updated INTEGER DEFAULT 0,
    -- Error tracking
    error_message TEXT,
    -- Metadata
    created_by VARCHAR(100),
    CONSTRAINT workflow_type_check CHECK (workflow_type IN ('pipeline_intelligence', 'disease_intelligence')),
    CONSTRAINT status_check CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT run_mode_check CHECK (run_mode IN ('full', 'incremental'))
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_workflow_runs_disease ON workflow_runs(disease_name);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_type ON workflow_runs(workflow_type);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started ON workflow_runs(started_at DESC);

-- Review flags table for tracking data conflicts
CREATE TABLE IF NOT EXISTS workflow_review_flags (
    flag_id SERIAL PRIMARY KEY,
    run_id INTEGER REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    disease_name VARCHAR(255) NOT NULL,
    workflow_type VARCHAR(50) NOT NULL,
    flag_type VARCHAR(50) NOT NULL,  -- 'data_conflict', 'new_data', 'value_change', 'missing_data'
    severity VARCHAR(20) NOT NULL DEFAULT 'info',  -- 'info', 'warning', 'error'
    field_name VARCHAR(100),
    old_value TEXT,
    new_value TEXT,
    message TEXT NOT NULL,
    -- Review status
    reviewed BOOLEAN DEFAULT FALSE,
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    review_action VARCHAR(50),  -- 'accepted', 'rejected', 'modified'
    review_notes TEXT,
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT flag_type_check CHECK (flag_type IN ('data_conflict', 'new_data', 'value_change', 'missing_data')),
    CONSTRAINT severity_check CHECK (severity IN ('info', 'warning', 'error')),
    CONSTRAINT review_action_check CHECK (review_action IS NULL OR review_action IN ('accepted', 'rejected', 'modified'))
);

-- Index for review flag queries
CREATE INDEX IF NOT EXISTS idx_review_flags_disease ON workflow_review_flags(disease_name);
CREATE INDEX IF NOT EXISTS idx_review_flags_unreviewed ON workflow_review_flags(reviewed) WHERE reviewed = FALSE;
CREATE INDEX IF NOT EXISTS idx_review_flags_severity ON workflow_review_flags(severity);

-- View for getting latest run per disease/workflow
CREATE OR REPLACE VIEW v_latest_workflow_runs AS
SELECT DISTINCT ON (disease_name, workflow_type)
    run_id,
    disease_name,
    therapeutic_area,
    workflow_type,
    run_mode,
    status,
    started_at,
    completed_at,
    items_found,
    items_new,
    items_updated,
    error_message
FROM workflow_runs
ORDER BY disease_name, workflow_type, started_at DESC;

-- View for pending review items
CREATE OR REPLACE VIEW v_pending_reviews AS
SELECT
    f.flag_id,
    f.disease_name,
    f.workflow_type,
    f.flag_type,
    f.severity,
    f.field_name,
    f.old_value,
    f.new_value,
    f.message,
    f.created_at,
    r.run_mode,
    r.started_at as run_started_at
FROM workflow_review_flags f
LEFT JOIN workflow_runs r ON f.run_id = r.run_id
WHERE f.reviewed = FALSE
ORDER BY
    CASE f.severity WHEN 'error' THEN 1 WHEN 'warning' THEN 2 ELSE 3 END,
    f.created_at DESC;

-- Comment on tables
COMMENT ON TABLE workflow_runs IS 'Tracks all workflow runs from Disease Analysis page';
COMMENT ON TABLE workflow_review_flags IS 'Flags data changes/conflicts for user review';
COMMENT ON VIEW v_latest_workflow_runs IS 'Latest run per disease/workflow combination';
COMMENT ON VIEW v_pending_reviews IS 'Review items awaiting user action';
