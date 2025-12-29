-- Migration: Add development_code column to drugs table
-- Version: 005
-- Date: 2024-12-27
-- Description: Adds development_code column for storing drug development codes (e.g., LNP023)
--              Used for clinical trial searches alongside generic name

-- Step 1: Add development_code column to drugs table
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'development_code'
    ) THEN
        ALTER TABLE drugs ADD COLUMN development_code VARCHAR(50);
        RAISE NOTICE 'Added development_code column';
    END IF;
END $$;

-- Step 2: Create index for development_code lookups
CREATE INDEX IF NOT EXISTS idx_drugs_development_code ON drugs(development_code) 
WHERE development_code IS NOT NULL;

-- Step 3: Add comment explaining the column
COMMENT ON COLUMN drugs.development_code IS 'Development/research code (e.g., LNP023, BMS-986165) used for clinical trial searches';

-- Step 4: Update view if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.views 
        WHERE table_name = 'vw_drug_overview'
    ) THEN
        -- Drop and recreate view to include new column
        DROP VIEW IF EXISTS vw_drug_overview;
        
        CREATE VIEW vw_drug_overview AS
        SELECT 
            d.drug_id,
            d.drug_key,
            d.brand_name,
            d.generic_name,
            d.development_code,
            d.manufacturer,
            d.drug_type,
            d.mechanism_of_action,
            d.target,
            d.moa_category,
            d.approval_status,
            d.highest_phase,
            d.first_approval_date,
            d.completeness_score,
            d.created_at,
            d.updated_at,
            (SELECT COUNT(*) FROM drug_indications di WHERE di.drug_id = d.drug_id) as indication_count,
            (SELECT COUNT(*) FROM drug_clinical_trials dct WHERE dct.drug_id = d.drug_id) as trial_count
        FROM drugs d;
        
        RAISE NOTICE 'Recreated vw_drug_overview with development_code';
    END IF;
END $$;

