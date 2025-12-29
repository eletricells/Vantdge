-- Migration: Add drug_key and external identifier columns to drugs table
-- Version: 001
-- Date: 2024-12-22
-- Description: Adds stable drug_key identifier and external ID columns

-- Step 1: Add new columns to drugs table (if they don't exist)
DO $$
BEGIN
    -- Add drug_key column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'drug_key'
    ) THEN
        ALTER TABLE drugs ADD COLUMN drug_key VARCHAR(100);
        RAISE NOTICE 'Added drug_key column';
    END IF;

    -- Add rxcui column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'rxcui'
    ) THEN
        ALTER TABLE drugs ADD COLUMN rxcui VARCHAR(20);
        RAISE NOTICE 'Added rxcui column';
    END IF;

    -- Add chembl_id column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'chembl_id'
    ) THEN
        ALTER TABLE drugs ADD COLUMN chembl_id VARCHAR(20);
        RAISE NOTICE 'Added chembl_id column';
    END IF;

    -- Add inchi_key column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'inchi_key'
    ) THEN
        ALTER TABLE drugs ADD COLUMN inchi_key VARCHAR(27);
        RAISE NOTICE 'Added inchi_key column';
    END IF;

    -- Add cas_number column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'cas_number'
    ) THEN
        ALTER TABLE drugs ADD COLUMN cas_number VARCHAR(20);
        RAISE NOTICE 'Added cas_number column';
    END IF;

    -- Add unii column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'unii'
    ) THEN
        ALTER TABLE drugs ADD COLUMN unii VARCHAR(10);
        RAISE NOTICE 'Added unii column';
    END IF;

    -- Add data_version column for versioning
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'data_version'
    ) THEN
        ALTER TABLE drugs ADD COLUMN data_version INTEGER DEFAULT 1;
        RAISE NOTICE 'Added data_version column';
    END IF;

    -- Add completeness_score column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'completeness_score'
    ) THEN
        ALTER TABLE drugs ADD COLUMN completeness_score NUMERIC(5,4);
        RAISE NOTICE 'Added completeness_score column';
    END IF;

    -- Add last_enrichment_at column
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'last_enrichment_at'
    ) THEN
        ALTER TABLE drugs ADD COLUMN last_enrichment_at TIMESTAMP;
        RAISE NOTICE 'Added last_enrichment_at column';
    END IF;
END $$;

-- Step 2: Create indexes for new columns (if they don't exist)
CREATE INDEX IF NOT EXISTS idx_drugs_drug_key ON drugs(drug_key);
CREATE INDEX IF NOT EXISTS idx_drugs_rxcui ON drugs(rxcui) WHERE rxcui IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drugs_chembl_id ON drugs(chembl_id) WHERE chembl_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drugs_unii ON drugs(unii) WHERE unii IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_drugs_completeness ON drugs(completeness_score);

-- Step 3: Add unique constraint on drug_key (after migration script populates keys)
-- NOTE: Run this AFTER running the Python migration to generate drug_keys
-- ALTER TABLE drugs ADD CONSTRAINT unique_drug_key UNIQUE(drug_key);

COMMENT ON COLUMN drugs.drug_key IS 'Stable, deterministic identifier in format DRG-{NAME}-{CHECKSUM}';
COMMENT ON COLUMN drugs.rxcui IS 'RxNorm Concept Unique Identifier';
COMMENT ON COLUMN drugs.chembl_id IS 'ChEMBL molecule identifier';
COMMENT ON COLUMN drugs.inchi_key IS 'International Chemical Identifier Key';
COMMENT ON COLUMN drugs.cas_number IS 'Chemical Abstracts Service Registry Number';
COMMENT ON COLUMN drugs.unii IS 'FDA Unique Ingredient Identifier';
COMMENT ON COLUMN drugs.data_version IS 'Version number incremented on each update';
COMMENT ON COLUMN drugs.completeness_score IS 'Data completeness score 0.0-1.0';
COMMENT ON COLUMN drugs.last_enrichment_at IS 'Timestamp of last enrichment from external sources';

-- Log migration
DO $$
BEGIN
    RAISE NOTICE 'Migration 001_add_drug_key_columns completed successfully';
END $$;

