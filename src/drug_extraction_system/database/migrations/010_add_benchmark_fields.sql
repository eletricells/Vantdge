-- Migration: 010_add_benchmark_fields.sql
-- Description: Add fields for efficacy benchmarking source tracking and review workflow
-- Created: 2025-01-06

-- ============================================================================
-- Add benchmark tracking fields to drug_efficacy_data
-- ============================================================================

-- Add source_url for traceability (link to publication or CT.gov)
ALTER TABLE drug_efficacy_data
ADD COLUMN IF NOT EXISTS source_url TEXT;

-- Add pmid for publication tracking
ALTER TABLE drug_efficacy_data
ADD COLUMN IF NOT EXISTS pmid VARCHAR(20);

-- Add review_status for hybrid review workflow
-- Values: 'auto_accepted' (confidence >= threshold), 'pending_review', 'user_confirmed', 'user_rejected'
ALTER TABLE drug_efficacy_data
ADD COLUMN IF NOT EXISTS review_status VARCHAR(20) DEFAULT 'auto_accepted';

-- Add user_override_note for review comments
ALTER TABLE drug_efficacy_data
ADD COLUMN IF NOT EXISTS user_override_note TEXT;

-- ============================================================================
-- Indexes for efficient queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_efficacy_review_status ON drug_efficacy_data(review_status);
CREATE INDEX IF NOT EXISTS idx_efficacy_pmid ON drug_efficacy_data(pmid);
CREATE INDEX IF NOT EXISTS idx_efficacy_source_url ON drug_efficacy_data(source_url) WHERE source_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_efficacy_data_source ON drug_efficacy_data(data_source);

-- ============================================================================
-- Record migration
-- ============================================================================

INSERT INTO schema_migrations (migration_name)
VALUES ('010_add_benchmark_fields')
ON CONFLICT (migration_name) DO NOTHING;
