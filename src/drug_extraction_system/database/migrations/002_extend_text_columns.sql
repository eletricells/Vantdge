-- Migration: Extend text columns to handle longer content from APIs
-- Version: 002
-- Date: 2024-12-22
-- Description: Changes VARCHAR columns to TEXT for fields that may contain long content

-- Step 0: Drop dependent view temporarily
DROP VIEW IF EXISTS vw_drug_overview;

-- Step 1: Alter mechanism_of_action to TEXT
DO $$
BEGIN
    -- Check if column exists and alter it
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drugs' AND column_name = 'mechanism_of_action'
    ) THEN
        ALTER TABLE drugs ALTER COLUMN mechanism_of_action TYPE TEXT;
        RAISE NOTICE 'Changed mechanism_of_action to TEXT';
    END IF;
END $$;

-- Step 2: Alter warnings column if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'warnings'
    ) THEN
        ALTER TABLE drugs ALTER COLUMN warnings TYPE TEXT;
        RAISE NOTICE 'Changed warnings to TEXT';
    END IF;
END $$;

-- Step 3: Alter contraindications column if it exists
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'contraindications'
    ) THEN
        ALTER TABLE drugs ALTER COLUMN contraindications TYPE TEXT;
        RAISE NOTICE 'Changed contraindications to TEXT';
    END IF;
END $$;

-- Step 4: Add warnings and contraindications columns if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'warnings'
    ) THEN
        ALTER TABLE drugs ADD COLUMN warnings TEXT;
        RAISE NOTICE 'Added warnings column';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'contraindications'
    ) THEN
        ALTER TABLE drugs ADD COLUMN contraindications TEXT;
        RAISE NOTICE 'Added contraindications column';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'drugs' AND column_name = 'boxed_warning'
    ) THEN
        ALTER TABLE drugs ADD COLUMN boxed_warning TEXT;
        RAISE NOTICE 'Added boxed_warning column';
    END IF;
END $$;

-- Step 5: Recreate the vw_drug_overview view
CREATE OR REPLACE VIEW vw_drug_overview AS
SELECT
    d.drug_id,
    d.brand_name,
    d.generic_name,
    d.manufacturer,
    d.drug_type,
    d.mechanism_of_action,
    d.approval_status,
    d.highest_phase,
    d.first_approval_date,
    d.is_combination,
    m.orphan_designation,
    m.breakthrough_therapy,
    m.has_black_box_warning,
    m.biosimilar_available,
    m.patent_expiry,
    COUNT(DISTINCT di.indication_id) as indication_count
FROM drugs d
LEFT JOIN drug_metadata m ON d.drug_id = m.drug_id
LEFT JOIN drug_indications di ON d.drug_id = di.drug_id
GROUP BY d.drug_id, m.drug_id;

COMMENT ON VIEW vw_drug_overview IS 'Comprehensive drug overview with metadata and indication count';

-- Log migration
DO $$
BEGIN
    RAISE NOTICE 'Migration 002_extend_text_columns completed successfully';
END $$;

