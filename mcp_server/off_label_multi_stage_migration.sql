-- =====================================================
-- OFF-LABEL CASE STUDY MULTI-STAGE EXTRACTION MIGRATION
-- =====================================================
-- Purpose: Add columns for enhanced multi-stage extraction and evidence quality
-- Date: 2025-12-06
-- =====================================================

-- Add evidence quality columns
ALTER TABLE off_label_case_studies 
ADD COLUMN IF NOT EXISTS evidence_quality JSONB,
ADD COLUMN IF NOT EXISTS evidence_grade VARCHAR(10);

-- Add multi-stage extraction columns
ALTER TABLE off_label_case_studies 
ADD COLUMN IF NOT EXISTS extraction_method VARCHAR(20) DEFAULT 'single_pass',
ADD COLUMN IF NOT EXISTS extraction_stages_completed JSONB DEFAULT '[]'::jsonb;

-- Add detailed endpoint columns (from multi-stage extraction)
ALTER TABLE off_label_case_studies 
ADD COLUMN IF NOT EXISTS detailed_efficacy_endpoints JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS detailed_safety_endpoints JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS standard_endpoints_matched JSONB DEFAULT '[]'::jsonb;

-- Add indexes for new columns
CREATE INDEX IF NOT EXISTS idx_off_label_evidence_grade ON off_label_case_studies(evidence_grade);
CREATE INDEX IF NOT EXISTS idx_off_label_extraction_method ON off_label_case_studies(extraction_method);

-- Add comments for documentation
COMMENT ON COLUMN off_label_case_studies.evidence_quality IS 'Evidence quality assessment using modified GRADE criteria';
COMMENT ON COLUMN off_label_case_studies.evidence_grade IS 'Overall evidence grade: A (high), B (moderate), C (low), D (very low)';
COMMENT ON COLUMN off_label_case_studies.extraction_method IS 'Extraction method used: single_pass (abstract-only) or multi_stage (full-text)';
COMMENT ON COLUMN off_label_case_studies.extraction_stages_completed IS 'List of extraction stages completed (e.g., section_id, efficacy, safety)';
COMMENT ON COLUMN off_label_case_studies.detailed_efficacy_endpoints IS 'Detailed efficacy endpoints from multi-stage extraction (EfficacyEndpoint format)';
COMMENT ON COLUMN off_label_case_studies.detailed_safety_endpoints IS 'Detailed safety endpoints from multi-stage extraction (SafetyEndpoint format)';
COMMENT ON COLUMN off_label_case_studies.standard_endpoints_matched IS 'Standard endpoints from landscape discovery that were matched';

