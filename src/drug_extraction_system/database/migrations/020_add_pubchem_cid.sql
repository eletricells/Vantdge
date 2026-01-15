-- Migration 020: Add PubChem identifier column for drug deduplication
-- This enables matching drugs by their PubChem compound/substance ID

-- Add PubChem identifier column
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS pubchem_cid BIGINT;

-- Create index for fast lookups
CREATE INDEX IF NOT EXISTS idx_drugs_pubchem_cid ON drugs(pubchem_cid)
WHERE pubchem_cid IS NOT NULL;

-- Document the convention: positive = CID, negative = SID (substance-only drugs)
COMMENT ON COLUMN drugs.pubchem_cid IS
  'PubChem identifier. Positive values = CID (compound). Negative values = SID (substance-only, e.g., -472419808 for dazukibart)';
