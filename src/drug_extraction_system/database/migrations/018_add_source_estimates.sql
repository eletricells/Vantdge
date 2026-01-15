-- Migration 018: Add columns for storing multiple source estimates with citations
-- This enables proper sourcing with superscript references

-- Add prevalence estimates array (stores multiple PrevalenceEstimate objects)
ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS prevalence_estimates JSONB DEFAULT '[]'::jsonb;

-- Add failure rate estimates array (stores multiple FailureRateEstimate objects)
ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS failure_rate_estimates JSONB DEFAULT '[]'::jsonb;

-- Add treatment rate estimates array
ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS treatment_estimates JSONB DEFAULT '[]'::jsonb;

-- Add methodology notes for how consensus values were derived
ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS prevalence_methodology TEXT;

ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS failure_rate_methodology TEXT;

-- Add confidence levels
ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS prevalence_confidence VARCHAR(20);

ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS failure_rate_confidence VARCHAR(20);

-- Add estimate ranges
ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS prevalence_range VARCHAR(100);

ALTER TABLE disease_intelligence
ADD COLUMN IF NOT EXISTS failure_rate_range VARCHAR(100);

-- Record migration
INSERT INTO schema_migrations (migration_name, applied_at)
VALUES ('018_add_source_estimates', CURRENT_TIMESTAMP)
ON CONFLICT (migration_name) DO NOTHING;
