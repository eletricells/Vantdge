-- Sample data for testing MCP database integration

-- Sample Historical Deals
INSERT INTO historical_deals (
    deal_name, target_company, drug_name, target_biology, indication, phase, deal_type,
    announcement_date, upfront_payment_usd, milestone_payments_usd, total_deal_value_usd,
    clinical_confidence_score, probability_of_success, estimated_peak_sales_usd,
    outcome, deal_rationale, key_strengths, key_risks
) VALUES
(
    'AbbVie-Allergan Acquisition',
    'Allergan',
    'Botox, Restasis, others',
    'Multiple',
    'Multiple indications',
    'Approved',
    'acquisition',
    '2019-06-25',
    63000000000.00,
    0,
    63000000000.00,
    0.95,
    0.90,
    15000000000.00,
    'success',
    'Strategic acquisition to diversify portfolio beyond Humira patent cliff',
    ARRAY['Established brands', 'Diversified portfolio', 'Strong cash flow'],
    ARRAY['Integration complexity', 'High valuation', 'Generic competition']
),
(
    'Pfizer-Array BioPharma',
    'Array BioPharma',
    'Braftovi + Mektovi',
    'BRAF/MEK',
    'BRAF-mutant melanoma',
    'Phase 3',
    'acquisition',
    '2019-06-17',
    11400000000.00,
    0,
    11400000000.00,
    0.85,
    0.75,
    800000000.00,
    'success',
    'Bolster oncology pipeline with differentiated BRAF/MEK combo',
    ARRAY['Strong Phase 3 data', 'Differentiated from competition', 'Experienced team'],
    ARRAY['Competitive landscape', 'Limited to BRAF-mutant patients', 'Reimbursement pressure']
),
(
    'BMS-Celgene',
    'Celgene',
    'Revlimid, Pomalyst, others',
    'Multiple',
    'Multiple myeloma, others',
    'Approved',
    'acquisition',
    '2019-01-03',
    74000000000.00,
    0,
    74000000000.00,
    0.90,
    0.85,
    12000000000.00,
    'success',
    'Create leading biopharma company with complementary portfolios',
    ARRAY['Revlimid blockbuster', 'Strong pipeline', 'Hematology leadership'],
    ARRAY['Revlimid patent cliff', 'Pipeline execution risk', 'Integration challenges']
);

-- Sample Expert Annotations
INSERT INTO expert_annotations (
    target_name, drug_name, indication, expert_name, expert_role, confidence_level,
    annotation_type, notes, key_insights, concerns, annotation_date
) VALUES
(
    'KRAS G12C',
    'Sotorasib',
    'NSCLC',
    'Dr. Sarah Chen',
    'Scientific Advisor - Oncology',
    'high',
    'target_validation',
    'KRAS G12C represents a validated oncogenic driver in ~13% of NSCLC. Sotorasib showed impressive ORR of 37.1% in CodeBreaK 100. Key question is durability of response and resistance mechanisms.',
    ARRAY['Clear genetic driver', 'First-in-class validation', 'Significant unmet need'],
    ARRAY['Acquired resistance mechanisms', 'Limited to G12C mutation', 'Combination strategy unclear'],
    '2023-06-15'
),
(
    'PD-1',
    'Pembrolizumab',
    'Multiple cancers',
    'Dr. Michael Roberts',
    'Clinical Expert - Immunotherapy',
    'high',
    'clinical_assessment',
    'Pembrolizumab has demonstrated unprecedented efficacy across multiple tumor types. The key is biomarker selection (PD-L1, TMB, MSI-H) to identify responders. Durability of responses is remarkable.',
    ARRAY['Durable responses', 'Broad applicability', 'Established biomarkers'],
    ARRAY['Immune-related adverse events', 'Primary resistance in many patients', 'Combination complexity'],
    '2023-08-22'
);

-- Sample Target Biology KB
INSERT INTO target_biology_kb (
    target_name, target_type, genetic_evidence_strength, preclinical_validation_strength,
    druggability_score, safety_risk_level, strategic_priority, portfolio_fit_score,
    internal_notes, failed_programs, last_reviewed_date
) VALUES
(
    'KRAS G12C',
    'Small GTPase',
    'HIGH',
    'HIGH',
    0.85,
    'medium',
    'high',
    0.90,
    'Highly validated target with first-in-class drugs approved. Resistance mechanisms emerging. Consider combination strategies.',
    ARRAY['Multiple early-stage programs failed before covalent inhibitor approach'],
    '2024-01-15'
),
(
    'PD-1/PD-L1',
    'Immune checkpoint',
    'HIGH',
    'HIGH',
    0.95,
    'medium',
    'high',
    0.85,
    'Blockbuster target class. Market highly competitive. Focus on differentiation via biomarkers and combinations.',
    ARRAY[],
    '2024-02-10'
),
(
    'TIGIT',
    'Immune checkpoint',
    'MEDIUM',
    'MEDIUM',
    0.70,
    'low',
    'medium',
    0.60,
    'Emerging checkpoint target. Mixed clinical data to date. Watch for differentiated antibodies with superior biology.',
    ARRAY['Roche vibostolimab failed in combo with PD-1'],
    '2023-12-20'
);

-- Sample Disease KB
INSERT INTO disease_kb (
    disease_name, icd_codes, us_prevalence, global_prevalence, market_size_usd,
    market_growth_rate, strategic_priority, unmet_need_severity, competitive_intensity,
    internal_expertise_level, portfolio_assets_count, internal_notes, last_reviewed_date
) VALUES
(
    'Non-small cell lung cancer',
    ARRAY['C34.90', 'C34.91'],
    250000,
    2200000,
    25000000000.00,
    8.5,
    'high',
    'high',
    'high',
    'intermediate',
    2,
    'Large market with multiple validated targets (EGFR, ALK, KRAS, etc.). Biomarker-driven treatment paradigm. Focus on underserved mutations.',
    '2024-01-30'
),
(
    'Alzheimer''s disease',
    ARRAY['G30.9'],
    6500000,
    55000000,
    8000000000.00,
    12.0,
    'high',
    'critical',
    'high',
    'limited',
    0,
    'Massive unmet need. High risk/high reward. Recent anti-amyloid antibodies (aducanumab, lecanemab) show modest efficacy. Need better targets.',
    '2024-02-01'
),
(
    'Rheumatoid arthritis',
    ARRAY['M06.9'],
    1500000,
    18000000,
    45000000000.00,
    4.2,
    'medium',
    'moderate',
    'high',
    'expert',
    3,
    'Well-served market but significant refractory patient population. Focus on novel MOAs beyond TNF/IL-6/JAK.',
    '2023-11-15'
);

-- Sample Competitive Intelligence
INSERT INTO competitive_intelligence (
    competitor_name, drug_name, target_biology, indication, phase,
    latest_clinical_data, safety_signals, efficacy_signals,
    competitive_threat_level, differentiation_vs_our_assets, last_updated
) VALUES
(
    'Amgen',
    'Sotorasib (Lumakras)',
    'KRAS G12C',
    'NSCLC',
    'Approved',
    'CodeBreaK 200 showed improvement over docetaxel (PFS 5.6 vs 4.5 months). ORR 28.1%.',
    ARRAY['Diarrhea (31.7%)', 'Increased AST/ALT (~10%)', 'Fatigue'],
    ARRAY['ORR 28.1% in 2L+ NSCLC', 'Disease control rate 82.5%', 'Median DOR 5.7 months'],
    'high',
    'Direct competitor. Our G12C program has differentiated PK/PD profile and potentially better brain penetration.',
    '2024-01-20'
),
(
    'Mirati',
    'Adagrasib',
    'KRAS G12C',
    'NSCLC, CRC',
    'Approved (NSCLC)',
    'KRYSTAL-1: ORR 42.9% in NSCLC, 34% in CRC. Improved CNS penetration.',
    ARRAY['Nausea (53%)', 'Diarrhea (51%)', 'Vomiting (40%)', 'QTc prolongation'],
    ARRAY['ORR 42.9% in NSCLC', 'CNS activity demonstrated', 'Activity in CRC'],
    'high',
    'Strong CNS data is differentiator. Higher toxicity rate may limit use. Our program has cleaner safety profile.',
    '2024-01-25'
);
