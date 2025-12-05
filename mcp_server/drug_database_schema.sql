-- Drug Database Schema
-- Comprehensive structured database for approved and pipeline drugs
-- Designed to integrate with DailyMed, clinical trials, and commercial data

-- Drop tables if they exist (for clean setup)
DROP TABLE IF EXISTS drug_commercial_data CASCADE;
DROP TABLE IF EXISTS drug_metadata CASCADE;
DROP TABLE IF EXISTS drug_label_versions CASCADE;
DROP TABLE IF EXISTS drug_formulations CASCADE;
DROP TABLE IF EXISTS drug_dosing_regimens CASCADE;
DROP TABLE IF EXISTS drug_indications CASCADE;
DROP TABLE IF EXISTS diseases CASCADE;
DROP TABLE IF EXISTS drugs CASCADE;

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- 1. Diseases Master Table (Normalized Indications)
CREATE TABLE diseases (
    disease_id SERIAL PRIMARY KEY,
    disease_name_standard VARCHAR(255) NOT NULL UNIQUE,
    disease_aliases JSONB,  -- ["Graves' Disease", "Grave's Disease", "Graves disease"]
    icd10_codes JSONB,  -- ["E05.00", "E05.01"]
    therapeutic_area VARCHAR(100),  -- "Autoimmune", "Oncology", "Cardiovascular"
    prevalence_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_diseases_therapeutic_area ON diseases(therapeutic_area);
CREATE INDEX idx_diseases_aliases ON diseases USING GIN(disease_aliases);

COMMENT ON TABLE diseases IS 'Master table for all diseases/indications with standardized naming';
COMMENT ON COLUMN diseases.disease_aliases IS 'JSON array of alternative names and spellings';
COMMENT ON COLUMN diseases.icd10_codes IS 'JSON array of ICD-10 diagnostic codes';


-- 2. Drugs Master Table (Brand, Generic, Biosimilars, Combinations)
CREATE TABLE drugs (
    drug_id SERIAL PRIMARY KEY,
    brand_name VARCHAR(255),
    generic_name VARCHAR(255) NOT NULL,
    manufacturer VARCHAR(255),  -- "generic" for generics, company name for branded/biosimilars
    drug_type VARCHAR(100),  -- "mAb", "small molecule", "ADC", "gene therapy", "bispecific", "CAR-T"
    mechanism_of_action VARCHAR(500),  -- "IL-17A inhibitor", "KRAS G12C inhibitor", "CD20 antagonist"
    mechanism_details TEXT,  -- Extended description
    approval_status VARCHAR(50),  -- "approved", "investigational", "discontinued"
    highest_phase VARCHAR(20),  -- "Phase 1", "Phase 2", "Phase 3", "Approved", "Discontinued"
    first_approval_date DATE,
    dailymed_setid VARCHAR(100),  -- DailyMed Set ID for approved drugs
    parent_drug_id INTEGER REFERENCES drugs(drug_id),  -- For biosimilars to link to originator
    is_combination BOOLEAN DEFAULT FALSE,
    combination_components INTEGER[],  -- Array of drug_ids if combination therapy
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_brand_manufacturer UNIQUE(brand_name, manufacturer),
    CONSTRAINT valid_approval_status CHECK (approval_status IN ('approved', 'investigational', 'discontinued')),
    CONSTRAINT valid_highest_phase CHECK (highest_phase IN ('Phase 1', 'Phase 2', 'Phase 3', 'Approved', 'Discontinued', 'Preclinical'))
);

CREATE INDEX idx_drugs_generic ON drugs(generic_name);
CREATE INDEX idx_drugs_brand ON drugs(brand_name);
CREATE INDEX idx_drugs_approval_status ON drugs(approval_status);
CREATE INDEX idx_drugs_manufacturer ON drugs(manufacturer);
CREATE INDEX idx_drugs_parent ON drugs(parent_drug_id);

COMMENT ON TABLE drugs IS 'Master registry of all drugs (approved, investigational, generics, biosimilars)';
COMMENT ON COLUMN drugs.manufacturer IS 'Set to "generic" for generic drugs; company name for branded/biosimilars';
COMMENT ON COLUMN drugs.parent_drug_id IS 'For biosimilars: references the originator drug';
COMMENT ON COLUMN drugs.combination_components IS 'Array of drug_ids for combination therapies (e.g., Drug A + Drug B)';


-- 3. Drug Indications (Many-to-Many: Drugs ↔ Diseases)
CREATE TABLE drug_indications (
    indication_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    disease_id INTEGER NOT NULL REFERENCES diseases(disease_id),
    indication_raw TEXT,  -- Verbatim from label/source
    approval_status VARCHAR(50),  -- "approved", "investigational", "failed"
    approval_date DATE,
    approval_year INTEGER,  -- Year for quick filtering
    approval_source VARCHAR(50),  -- "Drugs.com", "AI Agent", "DailyMed", etc.
    line_of_therapy VARCHAR(100),  -- "1L", "2L", "3L+", "any", "1L after anti-TNF failure"
    population_restrictions TEXT,  -- "moderate-to-severe", "BRAF V600E mutation-positive"
    label_section VARCHAR(100),  -- "INDICATIONS AND USAGE", "CLINICAL STUDIES"
    data_source VARCHAR(50),  -- "DailyMed", "ClinicalTrials.gov", "Paper", "Agent"
    severity_mild BOOLEAN DEFAULT FALSE,  -- Approved for mild disease
    severity_moderate BOOLEAN DEFAULT FALSE,  -- Approved for moderate disease
    severity_severe BOOLEAN DEFAULT FALSE,  -- Approved for severe disease
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_drug_disease_line UNIQUE(drug_id, disease_id, line_of_therapy)
);

CREATE INDEX idx_drug_indications_drug ON drug_indications(drug_id);
CREATE INDEX idx_drug_indications_disease ON drug_indications(disease_id);
CREATE INDEX idx_drug_indications_approval ON drug_indications(approval_status);

COMMENT ON TABLE drug_indications IS 'Many-to-many relationship between drugs and diseases/indications';
COMMENT ON COLUMN drug_indications.line_of_therapy IS 'Treatment line: 1L, 2L, 3L+, any, or conditional (e.g., "after anti-TNF failure")';
COMMENT ON COLUMN drug_indications.data_source IS 'Source of indication data: DailyMed for approved, ClinicalTrials.gov for investigational, Paper/Agent for pipeline';


-- 4. Drug Dosing Regimens (Complex Dosing: Loading, Maintenance, Indication-Specific)
CREATE TABLE drug_dosing_regimens (
    dosing_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    indication_id INTEGER REFERENCES drug_indications(indication_id) ON DELETE CASCADE,  -- NULL for general dosing
    regimen_phase VARCHAR(50),  -- "loading", "maintenance", "single", "induction"
    dose_amount NUMERIC(10, 2),
    dose_unit VARCHAR(20),  -- "mg", "mg/kg", "mg/m2", "units", "IU"
    frequency_standard VARCHAR(20),  -- "QW", "Q2W", "Q4W", "Q8W", "Q12W", "QD", "BID", "TID", "BIW", "PRN"
    frequency_raw TEXT,  -- "once every 4 weeks", "twice daily"
    route_standard VARCHAR(10),  -- "SC", "IV", "PO", "IM", "IT", "topical"
    route_raw TEXT,  -- "subcutaneous injection", "intravenous infusion"
    duration_weeks INTEGER,  -- For loading/induction phases
    weight_based BOOLEAN DEFAULT FALSE,
    sequence_order INTEGER,  -- 1 for loading, 2 for maintenance, etc.
    dosing_notes TEXT,  -- Special instructions, dose adjustments
    data_source VARCHAR(50),  -- "DailyMed", "Paper", "Agent"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_regimen_phase CHECK (regimen_phase IN ('loading', 'maintenance', 'single', 'induction'))
);

CREATE INDEX idx_dosing_drug ON drug_dosing_regimens(drug_id);
CREATE INDEX idx_dosing_indication ON drug_dosing_regimens(indication_id);
CREATE INDEX idx_dosing_phase ON drug_dosing_regimens(regimen_phase);

COMMENT ON TABLE drug_dosing_regimens IS 'Dosing regimens with loading/maintenance phases, indication-specific dosing';
COMMENT ON COLUMN drug_dosing_regimens.indication_id IS 'NULL for general dosing; FK to specific indication if dosing varies by disease';
COMMENT ON COLUMN drug_dosing_regimens.frequency_standard IS 'Standardized frequency code: QW, Q2W, Q4W, QD, BID, etc.';
COMMENT ON COLUMN drug_dosing_regimens.sequence_order IS 'Order of dosing phases: 1=loading, 2=maintenance';


-- 5. Drug Formulations (Routes, Strengths, Packaging)
CREATE TABLE drug_formulations (
    formulation_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    route VARCHAR(10),  -- "SC", "IV", "PO"
    formulation_type VARCHAR(100),  -- "pre-filled syringe", "autoinjector", "vial", "tablet", "capsule"
    strengths JSONB,  -- ["150mg/mL", "300mg/2mL"] for SC; ["50mg", "100mg", "200mg"] for tablets
    storage_requirements TEXT,  -- "Refrigerate 2-8°C", "Room temperature"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_formulations_drug ON drug_formulations(drug_id);
CREATE INDEX idx_formulations_route ON drug_formulations(route);

COMMENT ON TABLE drug_formulations IS 'Available formulations, strengths, and packaging for each drug';
COMMENT ON COLUMN drug_formulations.strengths IS 'JSON array of available strengths (varies by formulation)';


-- 6. Drug Label Versions (Version History: Keep Current + 2 Historical)
CREATE TABLE drug_label_versions (
    version_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    dailymed_setid VARCHAR(100),
    version_date DATE NOT NULL,
    label_data JSONB,  -- Full structured label data
    label_pdf_url TEXT,
    is_current BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_drug_version_date UNIQUE(drug_id, version_date)
);

CREATE INDEX idx_label_versions_drug ON drug_label_versions(drug_id);
CREATE INDEX idx_label_versions_current ON drug_label_versions(drug_id, is_current) WHERE is_current = TRUE;
CREATE INDEX idx_label_versions_date ON drug_label_versions(version_date DESC);

COMMENT ON TABLE drug_label_versions IS 'Label version history (keep current + 2 historical versions)';
COMMENT ON COLUMN drug_label_versions.is_current IS 'TRUE for current version; only one current version per drug';
COMMENT ON COLUMN drug_label_versions.label_data IS 'Full DailyMed label data as JSON';


-- 7. Drug Metadata (Extended Information, Safety, Regulatory)
CREATE TABLE drug_metadata (
    drug_id INTEGER PRIMARY KEY REFERENCES drugs(drug_id) ON DELETE CASCADE,
    patent_expiry DATE,
    exclusivity_end DATE,
    orphan_designation BOOLEAN DEFAULT FALSE,
    breakthrough_therapy BOOLEAN DEFAULT FALSE,
    fast_track BOOLEAN DEFAULT FALSE,
    accelerated_approval BOOLEAN DEFAULT FALSE,
    first_in_class BOOLEAN DEFAULT FALSE,
    biosimilar_available BOOLEAN DEFAULT FALSE,
    has_black_box_warning BOOLEAN DEFAULT FALSE,
    contraindications_summary TEXT,  -- Brief summary, link to full label for details
    safety_notes TEXT,  -- High-level safety concerns
    notes TEXT,  -- General notes
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE drug_metadata IS 'Extended drug information: regulatory status, safety flags, IP';
COMMENT ON COLUMN drug_metadata.has_black_box_warning IS 'Flag for black box warning presence (see DailyMed for full text)';
COMMENT ON COLUMN drug_metadata.contraindications_summary IS 'High-level summary; link to DailyMed for complete contraindications';


-- 8. Drug Commercial Data (Time-Series: TRx, NRx, Market Share, Revenue)
CREATE TABLE drug_commercial_data (
    commercial_id SERIAL PRIMARY KEY,
    drug_id INTEGER NOT NULL REFERENCES drugs(drug_id) ON DELETE CASCADE,
    disease_id INTEGER REFERENCES diseases(disease_id),  -- Optional: indication-specific data
    data_type VARCHAR(50),  -- "TRx", "NRx", "market_share", "revenue", "patients"
    time_period DATE,  -- First day of month/quarter
    period_type VARCHAR(20),  -- "monthly", "quarterly", "annual"
    value NUMERIC(15, 2),
    geography VARCHAR(100),  -- "US", "EU5", "Global", "Japan"
    data_source VARCHAR(100),  -- "IQVIA", "Symphony", "Internal"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_commercial_datapoint UNIQUE(drug_id, disease_id, data_type, time_period, geography),
    CONSTRAINT valid_period_type CHECK (period_type IN ('monthly', 'quarterly', 'annual'))
);

CREATE INDEX idx_commercial_drug ON drug_commercial_data(drug_id);
CREATE INDEX idx_commercial_disease ON drug_commercial_data(disease_id);
CREATE INDEX idx_commercial_time ON drug_commercial_data(time_period);
CREATE INDEX idx_commercial_type ON drug_commercial_data(data_type);

COMMENT ON TABLE drug_commercial_data IS 'Time-series commercial data: prescriptions, market share, revenue';
COMMENT ON COLUMN drug_commercial_data.disease_id IS 'NULL for total drug sales; FK to specific indication for indication-level data';
COMMENT ON COLUMN drug_commercial_data.data_type IS 'Type of metric: TRx, NRx, market_share (%), revenue ($), patients (#)';


-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to get current label for a drug
CREATE OR REPLACE FUNCTION get_current_label(p_drug_id INTEGER)
RETURNS JSONB AS $$
BEGIN
    RETURN (
        SELECT label_data
        FROM drug_label_versions
        WHERE drug_id = p_drug_id AND is_current = TRUE
        LIMIT 1
    );
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_current_label IS 'Retrieve current label data for a drug';


-- Function to maintain only 3 label versions (current + 2 historical)
CREATE OR REPLACE FUNCTION maintain_label_versions()
RETURNS TRIGGER AS $$
BEGIN
    -- Delete old versions beyond 3 most recent
    DELETE FROM drug_label_versions
    WHERE drug_id = NEW.drug_id
    AND version_id NOT IN (
        SELECT version_id
        FROM drug_label_versions
        WHERE drug_id = NEW.drug_id
        ORDER BY version_date DESC
        LIMIT 3
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_maintain_label_versions
AFTER INSERT ON drug_label_versions
FOR EACH ROW
EXECUTE FUNCTION maintain_label_versions();

COMMENT ON FUNCTION maintain_label_versions IS 'Trigger function to keep only 3 most recent label versions';


-- Function to update timestamps
CREATE OR REPLACE FUNCTION update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_drugs_timestamp BEFORE UPDATE ON drugs FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER update_diseases_timestamp BEFORE UPDATE ON diseases FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER update_indications_timestamp BEFORE UPDATE ON drug_indications FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER update_dosing_timestamp BEFORE UPDATE ON drug_dosing_regimens FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER update_formulations_timestamp BEFORE UPDATE ON drug_formulations FOR EACH ROW EXECUTE FUNCTION update_timestamp();
CREATE TRIGGER update_metadata_timestamp BEFORE UPDATE ON drug_metadata FOR EACH ROW EXECUTE FUNCTION update_timestamp();


-- =============================================================================
-- VIEWS FOR COMMON QUERIES
-- =============================================================================

-- View: Drug Overview (combines drugs + metadata)
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


-- View: Drug-Disease Matrix
CREATE OR REPLACE VIEW vw_drug_disease_matrix AS
SELECT
    d.brand_name,
    d.generic_name,
    d.manufacturer,
    d.approval_status as drug_status,
    dis.disease_name_standard,
    dis.therapeutic_area,
    di.approval_status as indication_status,
    di.approval_date,
    di.line_of_therapy
FROM drugs d
JOIN drug_indications di ON d.drug_id = di.drug_id
JOIN diseases dis ON di.disease_id = dis.disease_id;

COMMENT ON VIEW vw_drug_disease_matrix IS 'Matrix view of all drug-disease combinations';


-- View: Complete Dosing Information
CREATE OR REPLACE VIEW vw_complete_dosing AS
SELECT
    d.brand_name,
    d.generic_name,
    dis.disease_name_standard,
    dr.regimen_phase,
    dr.dose_amount,
    dr.dose_unit,
    dr.frequency_standard,
    dr.route_standard,
    dr.duration_weeks,
    dr.sequence_order,
    dr.dosing_notes
FROM drug_dosing_regimens dr
JOIN drugs d ON dr.drug_id = d.drug_id
LEFT JOIN drug_indications di ON dr.indication_id = di.indication_id
LEFT JOIN diseases dis ON di.disease_id = dis.disease_id
ORDER BY d.brand_name, dr.sequence_order;

COMMENT ON VIEW vw_complete_dosing IS 'Complete dosing regimens with drug and indication details';


-- =============================================================================
-- SAMPLE DATA (Optional - for testing)
-- =============================================================================

-- Insert sample disease
INSERT INTO diseases (disease_name_standard, disease_aliases, therapeutic_area) VALUES
('Plaque Psoriasis', '["Psoriasis", "Psoriasis Vulgaris"]', 'Dermatology');

-- Insert Cosentyx as example
INSERT INTO drugs (brand_name, generic_name, manufacturer, drug_type, mechanism_of_action, approval_status, highest_phase, first_approval_date, dailymed_setid) VALUES
('Cosentyx', 'secukinumab', 'Novartis', 'mAb', 'IL-17A inhibitor', 'approved', 'Approved', '2015-01-21', 'c6e0b4e4-example');

-- Insert indication
INSERT INTO drug_indications (drug_id, disease_id, indication_raw, approval_status, approval_date, line_of_therapy, data_source) VALUES
(1, 1, 'treatment of moderate to severe plaque psoriasis in adult patients', 'approved', '2015-01-21', 'any', 'DailyMed');

-- Insert dosing regimens (loading + maintenance)
INSERT INTO drug_dosing_regimens (drug_id, indication_id, regimen_phase, dose_amount, dose_unit, frequency_standard, frequency_raw, route_standard, route_raw, duration_weeks, sequence_order, data_source) VALUES
(1, 1, 'loading', 300, 'mg', 'QW', 'once weekly', 'SC', 'subcutaneous injection', 4, 1, 'DailyMed'),
(1, 1, 'maintenance', 300, 'mg', 'Q4W', 'every 4 weeks', 'SC', 'subcutaneous injection', NULL, 2, 'DailyMed');

-- Insert metadata
INSERT INTO drug_metadata (drug_id, orphan_designation, breakthrough_therapy, first_in_class) VALUES
(1, FALSE, FALSE, FALSE);
