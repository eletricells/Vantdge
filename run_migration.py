import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

print("Running database migration: add_is_relevant_to_extractions")

conn = psycopg2.connect(os.getenv('DISEASE_LANDSCAPE_URL'))
cur = conn.cursor()

# Migration SQL
migration_sql = """
-- Add is_relevant column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'cs_extractions'
        AND column_name = 'is_relevant'
    ) THEN
        ALTER TABLE cs_extractions
        ADD COLUMN is_relevant BOOLEAN DEFAULT TRUE;

        RAISE NOTICE 'Added is_relevant column to cs_extractions table';
    ELSE
        RAISE NOTICE 'is_relevant column already exists in cs_extractions table';
    END IF;
END $$;

-- Create index for filtering by relevance
CREATE INDEX IF NOT EXISTS idx_cs_extractions_relevant ON cs_extractions(is_relevant);

-- Update existing rows to set is_relevant = TRUE (assume all existing extractions are relevant)
UPDATE cs_extractions SET is_relevant = TRUE WHERE is_relevant IS NULL;
"""

try:
    cur.execute(migration_sql)
    conn.commit()
    print("✅ Migration completed successfully!")
except Exception as e:
    conn.rollback()
    print(f"❌ Migration failed: {e}")
finally:
    cur.close()
    conn.close()

