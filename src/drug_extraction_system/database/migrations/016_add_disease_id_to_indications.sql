-- Migration: 016_add_disease_id_to_indications
-- Description: Add disease_id column to drug_indications for proper foreign key relationship
-- Date: 2026-01-09
-- Reason: The original migration 003 used disease_name (text), but the repository and full schema
--         expect disease_id (integer) for referential integrity with diseases table

-- 1. Add disease_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'disease_id'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN disease_id INTEGER REFERENCES diseases(disease_id);
    END IF;
END $$;

-- 2. Populate disease_id from disease_name where possible
UPDATE drug_indications di
SET disease_id = d.disease_id
FROM diseases d
WHERE di.disease_id IS NULL
  AND (LOWER(di.disease_name) = LOWER(d.disease_name_standard)
       OR LOWER(di.disease_name) LIKE '%' || LOWER(d.disease_name_standard) || '%');

-- 3. Create index on disease_id
CREATE INDEX IF NOT EXISTS idx_drug_indications_disease_id ON drug_indications(disease_id);

-- 4. Drop the old unique constraint if it exists (uses disease_name)
DROP INDEX IF EXISTS idx_indications_unique;

-- 5. Create new unique constraint using disease_id (but keep disease_name for backwards compat)
-- Use COALESCE to handle NULLs in line_of_therapy
CREATE UNIQUE INDEX IF NOT EXISTS idx_indications_unique_v2
    ON drug_indications(drug_id, COALESCE(disease_id, 0), COALESCE(line_of_therapy, 'any'));

-- 6. Add indication_raw column if it doesn't exist (used by full schema)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'indication_raw'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN indication_raw TEXT;
    END IF;
END $$;

-- 7. Add approval_year column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'approval_year'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN approval_year INTEGER;
    END IF;
END $$;

-- 8. Add approval_source column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'approval_source'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN approval_source VARCHAR(50);
    END IF;
END $$;

-- 9. Add population_restrictions column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'population_restrictions'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN population_restrictions TEXT;
    END IF;
END $$;

-- 10. Add label_section column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'label_section'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN label_section VARCHAR(100);
    END IF;
END $$;

-- 11. Add severity columns if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'severity_mild'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN severity_mild BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'severity_moderate'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN severity_moderate BOOLEAN DEFAULT FALSE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'drug_indications' AND column_name = 'severity_severe'
    ) THEN
        ALTER TABLE drug_indications
        ADD COLUMN severity_severe BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

COMMENT ON COLUMN drug_indications.disease_id IS 'Foreign key to diseases table for proper referential integrity';
