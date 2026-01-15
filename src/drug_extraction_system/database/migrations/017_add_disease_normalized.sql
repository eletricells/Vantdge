-- Migration 017: Add disease_normalized column to cs_extractions
-- This enables proper disease name standardization for aggregation

-- Add normalized disease column
ALTER TABLE cs_extractions ADD COLUMN IF NOT EXISTS disease_normalized VARCHAR(500);

-- Create index for aggregation queries (group by normalized disease)
CREATE INDEX IF NOT EXISTS idx_cs_extractions_disease_normalized
ON cs_extractions(disease_normalized);

-- Create composite index for drug + normalized disease aggregation
CREATE INDEX IF NOT EXISTS idx_cs_extractions_drug_disease_normalized
ON cs_extractions(drug_name, disease_normalized);

-- Note: Backfill will be done via Python script to apply proper standardization logic
