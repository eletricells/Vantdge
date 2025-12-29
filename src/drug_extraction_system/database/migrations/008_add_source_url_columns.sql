-- Migration: 008_add_source_url_columns.sql
-- Description: Add source_url column to efficacy and safety tables for citation tracking
-- Created: 2025-12-29

-- Add source_url to drug_efficacy_data
ALTER TABLE drug_efficacy_data
ADD COLUMN IF NOT EXISTS source_url TEXT;

-- Add source_url to drug_safety_data
ALTER TABLE drug_safety_data
ADD COLUMN IF NOT EXISTS source_url TEXT;

-- Record migration
INSERT INTO schema_migrations (migration_name)
VALUES ('008_add_source_url_columns')
ON CONFLICT (migration_name) DO NOTHING;
