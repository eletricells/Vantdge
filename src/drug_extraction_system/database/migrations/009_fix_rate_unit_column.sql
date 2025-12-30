-- Migration: 009_fix_rate_unit_column.sql
-- Description: Increase drug_arm_rate_unit column size to accommodate longer units
-- Created: 2025-12-29

-- Fix drug_efficacy_data
ALTER TABLE drug_efficacy_data
ALTER COLUMN drug_arm_result_unit TYPE VARCHAR(50);

-- Fix drug_safety_data
ALTER TABLE drug_safety_data
ALTER COLUMN drug_arm_rate_unit TYPE VARCHAR(50);

-- Record migration
INSERT INTO schema_migrations (migration_name)
VALUES ('009_fix_rate_unit_column')
ON CONFLICT (migration_name) DO NOTHING;
