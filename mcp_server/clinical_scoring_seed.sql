-- Clinical Scoring Seed Data
-- Initial data for organ domains, validated instruments, and safety categories
-- Run after clinical_scoring_schema.sql

-- =====================================================
-- ORGAN DOMAINS
-- =====================================================

INSERT INTO cs_organ_domains (domain_name, description, keywords) VALUES
('musculoskeletal', 'Joint, muscle, and bone manifestations', ARRAY[
    'joint', 'joints', 'arthritis', 'arthralgia', 'articular', 'synovitis', 'synovial',
    'polyarthritis', 'oligoarthritis', 'monoarthritis', 'swollen joint', 'tender joint',
    'sjc', 'tjc', 'sjc28', 'tjc28', 'sjc66', 'tjc68', 'joint count', 'joint swelling',
    'das28', 'das-28', 'das28-crp', 'das28-esr', 'acr20', 'acr50', 'acr70',
    'acr response', 'cdai', 'sdai', 'rapid3', 'eular response',
    'haq', 'haq-di', 'health assessment questionnaire', 'mhaq', 'grip strength',
    'physical function', 'functional capacity', 'disability index',
    'morning stiffness', 'basdai', 'basfi', 'basmi', 'asdas', 'asdas-crp',
    'spinal mobility', 'spine', 'sacroiliac', 'sacroiliitis', 'axial', 'axspa',
    'enthesitis', 'enthesopathy', 'lei', 'mases', 'sparcc', 'dactylitis',
    'mda', 'minimal disease activity', 'dapsa', 'pasdas',
    'myositis', 'myopathy', 'muscle', 'muscular', 'muscle strength', 'muscle weakness',
    'mmt', 'mmt8', 'mmt-8', 'manual muscle test', 'cmas', 'imacs',
    'creatine kinase', 'ck', 'aldolase', 'dermatomyositis', 'polymyositis',
    'bone', 'bone erosion', 'erosion', 'osteitis', 'sharp score', 'radiographic',
    'gout', 'urate', 'uric acid', 'tophus', 'tophi',
    'tendon', 'tendonitis', 'tenosynovitis', 'bursitis', 'fibromyalgia'
]),
('mucocutaneous', 'Skin and mucosal manifestations', ARRAY[
    'skin', 'cutaneous', 'dermatologic', 'dermal', 'epidermal', 'rash', 'lesion',
    'eruption', 'erythema', 'induration', 'sclerosis', 'skin score', 'skin thickness',
    'clasi', 'clasi-a', 'clasi-d', 'cutaneous lupus', 'discoid', 'dle', 'scle',
    'malar', 'malar rash', 'butterfly rash', 'photosensitivity',
    'cdasi', 'cdasi activity', 'gottron', 'heliotrope', 'v-sign', 'shawl sign',
    'pasi', 'pasi50', 'pasi75', 'pasi90', 'pasi100', 'bsa', 'body surface area',
    'iga', 'iga 0/1', 'investigator global', 'spga', 'pga', 'napsi', 'nail psoriasis',
    'easi', 'easi-50', 'easi-75', 'scorad', 'poem', 'eczema', 'atopic', 'pruritus',
    'alopecia', 'hair', 'hair loss', 'salt', 'salt score', 'regrowth',
    'vitiligo', 'vasi', 'repigmentation', 'depigmentation',
    'hidradenitis', 'his4', 'ihs4', 'abscess', 'hurley',
    'mrss', 'modified rodnan', 'rodnan skin score', 'digital ulcer', 'raynaud',
    'mucosal', 'mucosa', 'oral', 'oral ulcer', 'mouth ulcer', 'aphthous', 'stomatitis',
    'wound', 'ulcer', 'ulceration', 'wound healing',
    'urticaria', 'angioedema', 'pemphigus', 'pemphigoid', 'pyoderma gangrenosum'
]),
('renal', 'Kidney and urinary manifestations', ARRAY[
    'kidney', 'renal', 'nephro', 'nephrology', 'nephropathy', 'nephritis',
    'lupus nephritis', 'ln', 'class iii', 'class iv', 'class v',
    'glomerulonephritis', 'gn', 'glomerular',
    'complete renal response', 'crr', 'partial renal response', 'prr', 'renal response',
    'proteinuria', 'protein', 'upcr', 'urine protein', 'urine albumin', 'uacr', 'albuminuria',
    'creatinine', 'serum creatinine', 'scr', 'gfr', 'egfr', 'glomerular filtration',
    'ckd', 'chronic kidney', 'aki', 'acute kidney', 'kidney injury', 'renal function',
    'hematuria', 'rbc cast', 'red cell cast', 'urinary sediment', 'active sediment',
    'dialysis', 'esrd', 'end-stage renal', 'kidney failure', 'renal replacement',
    'renal biopsy', 'kidney biopsy', 'histologic', 'activity index', 'chronicity index'
]),
('neurological', 'Nervous system manifestations', ARRAY[
    'neuro', 'neurologic', 'neurological', 'nervous system', 'cns', 'central nervous',
    'cognitive', 'cognition', 'cognitive impairment', 'brain fog', 'memory', 'mmse', 'moca',
    'psychosis', 'psychotic', 'psychiatric', 'mood', 'depression', 'encephalopathy',
    'seizure', 'seizures', 'epilepsy', 'convulsion',
    'headache', 'migraine', 'intracranial hypertension',
    'stroke', 'cva', 'cerebrovascular', 'tia', 'transient ischemic', 'infarct',
    'neuropathy', 'peripheral neuropathy', 'polyneuropathy', 'mononeuropathy',
    'cranial neuropathy', 'optic neuropathy', 'optic neuritis',
    'chorea', 'movement disorder', 'ataxia', 'myelopathy', 'transverse myelitis',
    'edss', 'expanded disability', 'relapse', 'relapse rate', 'arr', 'annualized relapse',
    'mri lesion', 't2 lesion', 'gadolinium', 'gd-enhancing', 'brain volume', 'neda',
    'msfc', 'timed 25', 't25fw', '9-hole peg', '9hpt', 'sdmt',
    'demyelinating', 'demyelination', 'white matter', 'neuromyelitis', 'nmo', 'myasthenia'
]),
('hematological', 'Blood cell and coagulation manifestations', ARRAY[
    'anemia', 'anaemia', 'hemoglobin', 'hgb', 'hb', 'hematocrit', 'hct',
    'red blood cell', 'rbc', 'erythrocyte', 'hemolytic', 'hemolysis', 'aiha',
    'autoimmune hemolytic', 'coombs', 'direct antiglobulin', 'reticulocyte',
    'leukopenia', 'leucopenia', 'leukocyte', 'wbc', 'white blood cell',
    'lymphopenia', 'lymphocyte', 'alc', 'absolute lymphocyte',
    'neutropenia', 'neutrophil', 'anc', 'absolute neutrophil', 'agranulocytosis',
    'thrombocytopenia', 'platelet', 'plt', 'platelet count', 'itp', 'immune thrombocytopenia',
    'cytopenia', 'cytopenias', 'pancytopenia', 'bicytopenia', 'bone marrow',
    'coagulation', 'coagulopathy', 'bleeding', 'hemorrhage',
    'lupus anticoagulant', 'antiphospholipid', 'aps', 'anticardiolipin', 'anti-beta2',
    'thrombosis', 'thrombotic', 'evans syndrome', 'ttp', 'hemophagocytic', 'hlh', 'mas'
]),
('cardiopulmonary', 'Heart and lung manifestations', ARRAY[
    'cardiac', 'heart', 'cardiovascular', 'cv', 'myocardial', 'cardiomyopathy',
    'heart failure', 'chf', 'ef', 'ejection fraction', 'lvef', 'left ventricular',
    'pericarditis', 'pericardial', 'myocarditis', 'endocarditis', 'valvular',
    'arrhythmia', 'conduction', 'heart block', 'qt prolongation', 'atrial fibrillation',
    'vasculitis', 'vascular', 'arteritis', 'aortitis', 'coronary', 'cad',
    'lung', 'pulmonary', 'respiratory', 'ild', 'interstitial lung', 'interstitial pneumonia',
    'pulmonary fibrosis', 'ipf', 'nsip', 'uip', 'organizing pneumonia',
    'fvc', 'forced vital capacity', 'fev1', 'dlco', 'diffusing capacity', 'pft',
    '6mwd', '6-minute walk', 'six minute walk',
    'pah', 'pulmonary arterial hypertension', 'pulmonary hypertension',
    'mpap', 'pvr', 'pulmonary vascular resistance', 'right heart',
    'pleuritis', 'pleural', 'pleural effusion', 'pneumonitis', 'dyspnea', 'hypoxia'
]),
('immunological', 'Immune system and serological markers', ARRAY[
    'complement', 'c3', 'c4', 'ch50', 'hypocomplementemia', 'low complement',
    'autoantibody', 'autoantibodies', 'antibody', 'ana', 'antinuclear', 'ana titer',
    'anti-dsdna', 'dsdna', 'ds-dna', 'double-stranded dna',
    'anti-smith', 'anti-sm', 'anti-rnp', 'anti-ssa', 'anti-ro', 'anti-ssb', 'anti-la',
    'anca', 'anti-neutrophil', 'pr3', 'mpo', 'c-anca', 'p-anca',
    'anti-jo1', 'antisynthetase', 'anti-mda5', 'anti-mi2', 'myositis specific',
    'anti-ccp', 'acpa', 'citrullinated', 'rf', 'rheumatoid factor',
    'anti-scl70', 'anti-centromere', 'anti-rna polymerase',
    'crp', 'c-reactive', 'esr', 'sed rate', 'sedimentation rate', 'ferritin',
    'immunoglobulin', 'igg', 'iga', 'igm', 'hypergammaglobulinemia',
    'interferon', 'ifn', 'type i interferon', 'ifn signature', 'ifn score',
    'cytokine', 'il-6', 'il-1', 'il-17', 'tnf', 'interleukin',
    'b cell', 'cd19', 'cd20', 't cell', 'cd4', 'cd8', 'treg', 'nk cell',
    'serologic', 'serology', 'seroconversion', 'immune complex', 'cryoglobulin'
]),
('systemic', 'Global disease activity and quality of life', ARRAY[
    'sledai', 'sledai-2k', 'selena-sledai', 'bilag', 'bilag-2004', 'bilag index',
    'sri', 'sri-4', 'sri-5', 'sri-6', 'sri response', 'bicla', 'lldas', 'doris remission',
    'slicc', 'slicc/acr', 'damage index', 'sdi',
    'bvas', 'bvas/wg', 'birmingham vasculitis', 'vdi', 'vasculitis damage index',
    'disease activity', 'global disease activity', 'global assessment',
    'physician global', 'pga', 'mdga', 'patient global', 'ptga',
    'remission', 'low disease activity', 'lda', 'inactive disease',
    'flare', 'disease flare', 'relapse', 'exacerbation',
    'responder', 'response', 'clinical response', 'treatment response', 'improvement',
    'steroid', 'glucocorticoid', 'corticosteroid', 'prednisone', 'prednisolone',
    'steroid dose', 'steroid sparing', 'steroid taper', 'steroid-free',
    'qol', 'quality of life', 'hrqol', 'sf-36', 'sf36', 'sf-12', 'eq-5d', 'eq5d',
    'facit', 'facit-f', 'facit-fatigue', 'fatigue', 'lupusqol', 'dlqi',
    'work productivity', 'wpai', 'absenteeism'
]),
('gastrointestinal', 'Digestive system manifestations', ARRAY[
    'gi', 'gastrointestinal', 'digestive', 'bowel', 'intestinal', 'abdominal', 'gut',
    'mayo', 'mayo score', 'partial mayo', 'total mayo', 'endoscopic mayo',
    'cdai', 'crohn disease activity', 'harvey-bradshaw', 'hbi',
    'ses-cd', 'simple endoscopic', 'cdeis', 'rutgeerts',
    'ibdq', 'ibd questionnaire', 'fecal calprotectin', 'fc', 'lactoferrin',
    'endoscopic remission', 'mucosal healing', 'histologic remission', 'clinical remission',
    'ulcerative colitis', 'uc', 'crohn', 'crohn disease', 'cd', 'colitis',
    'enteritis', 'ileitis', 'proctitis', 'pouchitis', 'fistula', 'stricture',
    'diarrhea', 'bloody stool', 'rectal bleeding', 'urgency', 'stool frequency',
    'abdominal pain', 'nausea', 'vomiting',
    'hepatic', 'liver', 'alt', 'ast', 'transaminase', 'lfts', 'liver function',
    'alkaline phosphatase', 'ggt', 'bilirubin', 'hepatitis', 'hepatotoxicity',
    'autoimmune hepatitis', 'aih', 'pbc', 'psc',
    'dysphagia', 'esophageal', 'gastroparesis', 'pancreatitis', 'peritonitis'
]),
('ocular', 'Eye manifestations', ARRAY[
    'eye', 'ocular', 'ophthalmic', 'ophthalmologic', 'visual',
    'uveitis', 'anterior uveitis', 'posterior uveitis', 'panuveitis', 'intermediate uveitis',
    'iritis', 'iridocyclitis', 'choroiditis', 'chorioretinitis', 'vitritis', 'vitreous',
    'sun criteria', 'sun grading', 'anterior chamber cells', 'vitreous haze',
    'cystoid macular edema', 'cme',
    'scleritis', 'episcleritis', 'scleral', 'necrotizing scleritis',
    'retinal', 'retina', 'retinopathy', 'retinal vasculitis', 'cotton wool',
    'optic', 'optic nerve', 'optic neuritis', 'papillitis',
    'visual acuity', 'bcva', 'best corrected', 'etdrs', 'snellen', 'logmar',
    'visual field', 'perimetry', 'contrast sensitivity', 'vision loss',
    'dry eye', 'keratoconjunctivitis', 'sicca', 'schirmer', 'tear film',
    'corneal', 'keratitis', 'conjunctivitis', 'orbital', 'proptosis',
    'oct', 'optical coherence', 'fluorescein angiography', 'fundus'
]),
('constitutional', 'Systemic symptoms', ARRAY[
    'fatigue', 'tiredness', 'exhaustion', 'asthenia', 'malaise',
    'facit-fatigue', 'facit-f', 'fss', 'fatigue severity scale', 'brief fatigue',
    'fever', 'febrile', 'temperature', 'pyrexia',
    'weight', 'weight loss', 'cachexia', 'wasting', 'bmi', 'body mass index', 'anorexia',
    'sleep', 'insomnia', 'sleep disturbance', 'sleep quality', 'psqi',
    'night sweats', 'diaphoresis', 'chills', 'rigors',
    'lymphadenopathy', 'lymph node', 'splenomegaly', 'hepatomegaly'
])
ON CONFLICT (domain_name) DO UPDATE SET
    keywords = EXCLUDED.keywords,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;

-- =====================================================
-- SAFETY SIGNAL CATEGORIES
-- =====================================================

INSERT INTO cs_safety_categories (category_name, description, keywords, severity_weight, regulatory_flag, meddra_soc) VALUES
('serious_infection', 'Serious and opportunistic infections', ARRAY[
    'serious infection', 'severe infection', 'opportunistic infection', 'sepsis', 'septic',
    'bacteremia', 'fungemia', 'viremia', 'pneumonia', 'tuberculosis', 'tb', 'latent tb',
    'pneumocystis', 'pjp', 'pcp', 'aspergillosis', 'candidiasis', 'invasive fungal',
    'cryptococcal', 'histoplasmosis', 'listeria', 'listeriosis', 'legionella',
    'cmv', 'cytomegalovirus', 'ebv reactivation', 'jc virus', 'pml',
    'progressive multifocal leukoencephalopathy', 'hepatitis b reactivation',
    'cellulitis', 'abscess', 'osteomyelitis', 'endocarditis', 'meningitis',
    'encephalitis', 'pyelonephritis', 'urosepsis', 'necrotizing fasciitis',
    'hospitalized for infection', 'iv antibiotics'
], 9, TRUE, 'Infections and infestations'),
('non_serious_infection', 'Non-serious infections', ARRAY[
    'upper respiratory', 'uri', 'urti', 'common cold', 'rhinitis', 'nasopharyngitis',
    'pharyngitis', 'sinusitis', 'bronchitis', 'urinary tract infection', 'uti', 'cystitis',
    'herpes simplex', 'hsv', 'cold sore', 'herpes zoster', 'shingles', 'zoster', 'vzv',
    'influenza', 'flu', 'gastroenteritis', 'conjunctivitis', 'otitis',
    'skin infection', 'folliculitis', 'impetigo', 'oral candidiasis', 'thrush',
    'vaginal candidiasis', 'yeast infection', 'tinea', 'fungal skin', 'onychomycosis'
], 3, FALSE, 'Infections and infestations'),
('malignancy', 'Malignant neoplasms', ARRAY[
    'malignancy', 'malignant', 'cancer', 'carcinoma', 'sarcoma', 'lymphoma',
    'leukemia', 'leukaemia', 'myeloma', 'tumor', 'tumour', 'neoplasm', 'neoplastic',
    'nmsc', 'non-melanoma skin cancer', 'basal cell', 'bcc', 'squamous cell carcinoma',
    'scc', 'melanoma', 'breast cancer', 'lung cancer', 'colon cancer', 'prostate cancer',
    'lymphoproliferative', 'lpd', 'ptld', 'hepatocellular', 'hcc',
    'solid tumor', 'hematologic malignancy', 'metastatic', 'metastasis'
], 10, TRUE, 'Neoplasms'),
('cardiovascular', 'Major cardiovascular events', ARRAY[
    'mace', 'major adverse cardiovascular', 'cardiovascular event',
    'myocardial infarction', 'mi', 'heart attack', 'stemi', 'nstemi',
    'acute coronary', 'acs', 'unstable angina', 'stroke', 'cva', 'cerebrovascular',
    'heart failure', 'chf', 'cardiac failure', 'cardiomyopathy', 'myocarditis',
    'pericarditis', 'arrhythmia', 'atrial fibrillation', 'afib', 'ventricular',
    'qt prolongation', 'torsades', 'sudden cardiac', 'hypertension', 'hypertensive'
], 9, TRUE, 'Cardiac disorders'),
('thromboembolic', 'Thromboembolic events', ARRAY[
    'vte', 'venous thromboembolism', 'thromboembolism', 'dvt', 'deep vein thrombosis',
    'pe', 'pulmonary embolism', 'pulmonary embolus', 'arterial thrombosis',
    'portal vein thrombosis', 'hepatic vein thrombosis', 'cerebral venous', 'cvst',
    'retinal vein occlusion', 'rvo', 'thrombophlebitis', 'clot', 'blood clot', 'thrombus'
], 9, TRUE, 'Vascular disorders'),
('hepatotoxicity', 'Liver toxicity', ARRAY[
    'hepatotoxicity', 'liver toxicity', 'hepatic toxicity', 'dili', 'drug-induced liver',
    'alt increased', 'ast increased', 'transaminase increased', 'elevated transaminases',
    'elevated liver enzymes', 'lfts elevated', 'hepatitis', 'hepatic injury', 'liver injury',
    'jaundice', 'hyperbilirubinemia', 'cholestasis', 'cholestatic',
    'hepatic failure', 'liver failure', 'acute liver failure', 'hepatic necrosis', 'hy law'
], 8, TRUE, 'Hepatobiliary disorders'),
('cytopenia', 'Blood cell deficiencies', ARRAY[
    'cytopenia', 'pancytopenia', 'bicytopenia', 'neutropenia', 'neutropenic',
    'anc decreased', 'agranulocytosis', 'leukopenia', 'leucopenia', 'wbc decreased',
    'lymphopenia', 'lymphocytopenia', 'alc decreased', 'thrombocytopenia',
    'platelet decreased', 'low platelets', 'anemia', 'anaemia', 'hemoglobin decreased',
    'bone marrow suppression', 'myelosuppression', 'febrile neutropenia'
], 7, TRUE, 'Blood and lymphatic system disorders'),
('gi_perforation', 'GI perforation and bleeding', ARRAY[
    'gi perforation', 'gastrointestinal perforation', 'bowel perforation',
    'intestinal perforation', 'colonic perforation', 'gastric perforation',
    'diverticular perforation', 'diverticulitis', 'peritonitis', 'acute abdomen',
    'gi bleed', 'gastrointestinal bleeding', 'gi hemorrhage',
    'upper gi bleed', 'lower gi bleed', 'melena', 'hematochezia'
], 9, TRUE, 'Gastrointestinal disorders'),
('hypersensitivity', 'Allergic and hypersensitivity reactions', ARRAY[
    'hypersensitivity', 'allergic reaction', 'allergy', 'anaphylaxis', 'anaphylactic',
    'anaphylactoid', 'angioedema', 'urticaria', 'hives', 'infusion reaction',
    'injection site reaction', 'isr', 'serum sickness', 'drug reaction',
    'dress', 'drug rash eosinophilia', 'stevens-johnson', 'sjs',
    'toxic epidermal', 'ten', 'erythema multiforme'
], 7, TRUE, 'Immune system disorders'),
('neurological', 'Neurological adverse events', ARRAY[
    'seizure', 'convulsion', 'epilepsy', 'neuropathy', 'peripheral neuropathy',
    'polyneuropathy', 'guillain-barre', 'gbs', 'cidp', 'demyelinating', 'demyelination',
    'encephalopathy', 'posterior reversible', 'pres', 'headache', 'migraine',
    'dizziness', 'vertigo', 'syncope', 'paresthesia', 'numbness', 'tingling',
    'tremor', 'ataxia', 'cognitive impairment', 'memory impairment', 'confusion'
], 6, FALSE, 'Nervous system disorders'),
('pulmonary', 'Pulmonary adverse events', ARRAY[
    'ild', 'interstitial lung disease', 'interstitial pneumonia', 'pneumonitis',
    'drug-induced pneumonitis', 'pulmonary fibrosis', 'lung fibrosis',
    'respiratory failure', 'ards', 'acute respiratory', 'dyspnea', 'shortness of breath',
    'hypoxia', 'cough', 'bronchospasm', 'wheezing', 'pleural effusion', 'pleuritis'
], 7, TRUE, 'Respiratory disorders'),
('renal', 'Renal adverse events', ARRAY[
    'nephrotoxicity', 'renal toxicity', 'kidney toxicity', 'aki', 'acute kidney injury',
    'acute renal failure', 'ckd progression', 'renal impairment', 'renal insufficiency',
    'creatinine increased', 'gfr decreased', 'egfr decreased', 'proteinuria', 'hematuria',
    'nephritis', 'interstitial nephritis', 'glomerulonephritis', 'renal failure'
], 7, TRUE, 'Renal and urinary disorders'),
('death', 'Fatal events', ARRAY[
    'death', 'died', 'fatal', 'fatality', 'mortality', 'sudden death', 'unexpected death',
    'treatment-related death', 'treatment-emergent death'
], 10, TRUE, 'Death'),
('metabolic', 'Metabolic adverse events', ARRAY[
    'hyperlipidemia', 'dyslipidemia', 'cholesterol increased', 'ldl increased',
    'triglycerides increased', 'hyperglycemia', 'diabetes', 'glucose increased',
    'weight gain', 'obesity', 'hypokalemia', 'hyperkalemia', 'electrolyte',
    'cpk increased', 'ck increased', 'rhabdomyolysis'
], 4, FALSE, 'Metabolism and nutrition disorders'),
('discontinuation', 'Treatment discontinuation', ARRAY[
    'discontinuation', 'discontinued', 'withdrawal', 'treatment discontinuation',
    'drug discontinuation', 'adverse event leading to discontinuation',
    'ae leading to dc', 'teae leading to discontinuation',
    'stopped treatment', 'intolerance', 'intolerable'
], 5, FALSE, 'General disorders')
ON CONFLICT (category_name) DO UPDATE SET
    keywords = EXCLUDED.keywords,
    severity_weight = EXCLUDED.severity_weight,
    regulatory_flag = EXCLUDED.regulatory_flag,
    meddra_soc = EXCLUDED.meddra_soc,
    updated_at = CURRENT_TIMESTAMP;

-- =====================================================
-- VALIDATED INSTRUMENTS - Rheumatoid Arthritis
-- =====================================================
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'ACR20', 10, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'ACR50', 10, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'ACR70', 10, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'DAS28-CRP', 10, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'DAS28-ESR', 10, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'DAS28', 10, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'CDAI', 9, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'SDAI', 9, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'Boolean remission', 9, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'HAQ-DI', 10, 'patient_reported', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'HAQ', 10, 'patient_reported', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'mHAQ', 8, 'patient_reported', FALSE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'RAPID3', 8, 'patient_reported', FALSE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'Sharp score', 9, 'imaging', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'modified Sharp', 9, 'imaging', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'SJC28', 9, 'clinician_reported', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'TJC28', 9, 'clinician_reported', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'Patient Global', 8, 'patient_reported', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'Physician Global', 8, 'clinician_reported', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'EULAR response', 9, 'composite', TRUE),
('rheumatoid_arthritis', ARRAY['RA', 'rheumatoid'], 'ACR/EULAR remission', 10, 'composite', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Systemic Lupus Erythematosus
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'SLEDAI', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'SLEDAI-2K', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'SELENA-SLEDAI', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'BILAG', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'BILAG-2004', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'SRI-4', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'SRI-5', 9, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'BICLA', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'LLDAS', 9, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'DORIS remission', 9, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'SLICC/ACR Damage Index', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'SDI', 10, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'CLASI', 9, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'CLASI-A', 9, 'composite', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'LupusQoL', 8, 'patient_reported', FALSE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'PGA', 8, 'clinician_reported', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'SF-36', 8, 'patient_reported', TRUE),
('systemic_lupus_erythematosus', ARRAY['SLE', 'lupus'], 'FACIT-Fatigue', 8, 'patient_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Lupus Nephritis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'Complete Renal Response', 10, 'composite', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'CRR', 10, 'composite', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'Partial Renal Response', 10, 'composite', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'PRR', 10, 'composite', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'Overall Renal Response', 10, 'composite', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'Proteinuria', 9, 'biomarker', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'UPCR', 9, 'biomarker', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'eGFR', 9, 'biomarker', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'Serum creatinine', 8, 'biomarker', TRUE),
('lupus_nephritis', ARRAY['LN', 'nephritis'], 'Renal flare', 8, 'composite', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Psoriatic Arthritis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('psoriatic_arthritis', ARRAY['PsA'], 'ACR20', 10, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'ACR50', 10, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'ACR70', 10, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'PASI', 10, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'PASI75', 10, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'PASI90', 10, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'MDA', 10, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'Minimal Disease Activity', 10, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'DAPSA', 9, 'composite', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'PASDAS', 9, 'composite', FALSE),
('psoriatic_arthritis', ARRAY['PsA'], 'HAQ-DI', 9, 'patient_reported', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'LEI', 8, 'clinician_reported', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'Dactylitis count', 8, 'clinician_reported', TRUE),
('psoriatic_arthritis', ARRAY['PsA'], 'NAPSI', 8, 'clinician_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Ankylosing Spondylitis / Axial SpA
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'ASAS20', 10, 'composite', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'ASAS40', 10, 'composite', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'ASAS partial remission', 10, 'composite', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'BASDAI', 10, 'patient_reported', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'BASDAI50', 10, 'patient_reported', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'BASFI', 9, 'patient_reported', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'BASMI', 9, 'clinician_reported', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'ASDAS', 10, 'composite', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'ASDAS-CRP', 10, 'composite', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'SPARCC', 9, 'imaging', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'mSASSS', 9, 'imaging', TRUE),
('ankylosing_spondylitis', ARRAY['AS', 'axSpA', 'axial spondyloarthritis'], 'MASES', 8, 'clinician_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Psoriasis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('psoriasis', ARRAY['plaque psoriasis'], 'PASI', 10, 'composite', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'PASI75', 10, 'composite', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'PASI90', 10, 'composite', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'PASI100', 10, 'composite', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'IGA', 10, 'clinician_reported', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'IGA 0/1', 10, 'clinician_reported', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'sPGA', 10, 'clinician_reported', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'BSA', 9, 'clinician_reported', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'DLQI', 9, 'patient_reported', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'NAPSI', 8, 'clinician_reported', TRUE),
('psoriasis', ARRAY['plaque psoriasis'], 'PSSI', 8, 'clinician_reported', FALSE),
('psoriasis', ARRAY['plaque psoriasis'], 'Pruritus NRS', 8, 'patient_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Atopic Dermatitis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'EASI', 10, 'composite', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'EASI-50', 10, 'composite', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'EASI-75', 10, 'composite', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'EASI-90', 10, 'composite', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'IGA', 10, 'clinician_reported', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'vIGA-AD', 10, 'clinician_reported', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'IGA 0/1', 10, 'clinician_reported', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'SCORAD', 9, 'composite', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'BSA', 9, 'clinician_reported', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'Peak Pruritus NRS', 10, 'patient_reported', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'PP-NRS', 10, 'patient_reported', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'DLQI', 9, 'patient_reported', TRUE),
('atopic_dermatitis', ARRAY['AD', 'eczema'], 'POEM', 9, 'patient_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Dermatomyositis / Myositis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'CDASI', 10, 'composite', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'CDASI Activity', 10, 'composite', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'MMT-8', 10, 'clinician_reported', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'MMT8', 10, 'clinician_reported', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'IMACS TIS', 10, 'composite', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'Total Improvement Score', 10, 'composite', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'HAQ-DI', 9, 'patient_reported', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'Physician Global', 9, 'clinician_reported', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'CK', 8, 'biomarker', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'Creatine Kinase', 8, 'biomarker', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'CMAS', 9, 'clinician_reported', TRUE),
('dermatomyositis', ARRAY['DM', 'myositis', 'polymyositis'], 'Myositis Response Criteria', 10, 'composite', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Systemic Sclerosis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'mRSS', 10, 'clinician_reported', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'Modified Rodnan Skin Score', 10, 'clinician_reported', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'FVC', 10, 'biomarker', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'Forced Vital Capacity', 10, 'biomarker', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'DLCO', 9, 'biomarker', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'HAQ-DI', 9, 'patient_reported', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'SHAQ', 9, 'patient_reported', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], '6MWD', 9, 'clinician_reported', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'Digital ulcer count', 8, 'clinician_reported', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'Raynaud Condition Score', 8, 'patient_reported', FALSE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'CRISS', 9, 'composite', TRUE),
('systemic_sclerosis', ARRAY['SSc', 'scleroderma'], 'ACR CRISS', 9, 'composite', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- ANCA Vasculitis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'BVAS', 10, 'composite', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'BVAS v3', 10, 'composite', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'BVAS/WG', 10, 'composite', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'VDI', 9, 'composite', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'Remission', 10, 'composite', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'Complete remission', 10, 'composite', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'Relapse', 9, 'composite', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'GC-free remission', 9, 'composite', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'eGFR', 8, 'biomarker', TRUE),
('anca_vasculitis', ARRAY['AAV', 'GPA', 'MPA', 'EGPA'], 'ANCA titer', 7, 'biomarker', FALSE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- IBD - Ulcerative Colitis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'Mayo Score', 10, 'composite', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'Total Mayo', 10, 'composite', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'Partial Mayo', 9, 'composite', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'Endoscopic Mayo', 10, 'clinician_reported', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'Clinical remission', 10, 'composite', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'Endoscopic remission', 10, 'composite', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'Mucosal healing', 10, 'composite', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'UCEIS', 9, 'clinician_reported', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'Fecal calprotectin', 8, 'biomarker', TRUE),
('ulcerative_colitis', ARRAY['UC', 'IBD'], 'IBDQ', 8, 'patient_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- IBD - Crohn's Disease
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('crohns_disease', ARRAY['CD', 'Crohn'], 'CDAI', 10, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'CDAI-70', 10, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'CDAI-100', 10, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'CDAI remission', 10, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'Harvey-Bradshaw Index', 9, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'HBI', 9, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'SES-CD', 10, 'clinician_reported', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'Endoscopic remission', 10, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'Mucosal healing', 10, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'Fistula closure', 9, 'composite', TRUE),
('crohns_disease', ARRAY['CD', 'Crohn'], 'Fecal calprotectin', 8, 'biomarker', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Multiple Sclerosis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('multiple_sclerosis', ARRAY['MS'], 'EDSS', 10, 'composite', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'ARR', 10, 'composite', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'Annualized Relapse Rate', 10, 'composite', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'NEDA', 10, 'composite', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'NEDA-3', 10, 'composite', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'T2 lesion', 9, 'imaging', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'Gd-enhancing lesion', 9, 'imaging', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'Brain volume', 9, 'imaging', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'MSFC', 9, 'composite', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'T25FW', 9, 'clinician_reported', TRUE),
('multiple_sclerosis', ARRAY['MS'], '9HPT', 9, 'clinician_reported', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'SDMT', 8, 'clinician_reported', TRUE),
('multiple_sclerosis', ARRAY['MS'], 'CDP', 9, 'composite', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Uveitis
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'Anterior chamber cells', 10, 'clinician_reported', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'AC cell grade', 10, 'clinician_reported', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'Vitreous haze', 10, 'clinician_reported', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'SUN criteria', 10, 'composite', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'Uveitis flare', 9, 'composite', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'Time to first flare', 9, 'composite', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'Visual acuity', 10, 'clinician_reported', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'BCVA', 10, 'clinician_reported', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'OCT', 8, 'imaging', TRUE),
('uveitis', ARRAY['anterior uveitis', 'posterior uveitis'], 'VFQ-25', 8, 'patient_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Alopecia Areata
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('alopecia_areata', ARRAY['AA', 'alopecia'], 'SALT', 10, 'clinician_reported', TRUE),
('alopecia_areata', ARRAY['AA', 'alopecia'], 'SALT30', 10, 'clinician_reported', TRUE),
('alopecia_areata', ARRAY['AA', 'alopecia'], 'SALT50', 10, 'clinician_reported', TRUE),
('alopecia_areata', ARRAY['AA', 'alopecia'], 'SALT75', 10, 'clinician_reported', TRUE),
('alopecia_areata', ARRAY['AA', 'alopecia'], 'SALT90', 10, 'clinician_reported', TRUE),
('alopecia_areata', ARRAY['AA', 'alopecia'], 'Regrowth', 8, 'clinician_reported', TRUE),
('alopecia_areata', ARRAY['AA', 'alopecia'], 'ClinRO', 9, 'clinician_reported', TRUE),
('alopecia_areata', ARRAY['AA', 'alopecia'], 'AA-IGA', 9, 'clinician_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Vitiligo
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('vitiligo', ARRAY[]::TEXT[], 'F-VASI', 10, 'composite', TRUE),
('vitiligo', ARRAY[]::TEXT[], 'T-VASI', 10, 'composite', TRUE),
('vitiligo', ARRAY[]::TEXT[], 'VASI', 10, 'composite', TRUE),
('vitiligo', ARRAY[]::TEXT[], 'BSA-V', 9, 'clinician_reported', TRUE),
('vitiligo', ARRAY[]::TEXT[], 'VES', 9, 'clinician_reported', TRUE),
('vitiligo', ARRAY[]::TEXT[], 'F-VASI75', 9, 'composite', TRUE),
('vitiligo', ARRAY[]::TEXT[], 'Repigmentation', 9, 'clinician_reported', TRUE),
('vitiligo', ARRAY[]::TEXT[], 'VitiQoL', 8, 'patient_reported', FALSE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Hidradenitis Suppurativa
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('hidradenitis_suppurativa', ARRAY['HS'], 'HiSCR', 10, 'composite', TRUE),
('hidradenitis_suppurativa', ARRAY['HS'], 'HiSCR50', 10, 'composite', TRUE),
('hidradenitis_suppurativa', ARRAY['HS'], 'HiSCR75', 10, 'composite', TRUE),
('hidradenitis_suppurativa', ARRAY['HS'], 'IHS4', 9, 'composite', TRUE),
('hidradenitis_suppurativa', ARRAY['HS'], 'AN count', 9, 'clinician_reported', TRUE),
('hidradenitis_suppurativa', ARRAY['HS'], 'Draining tunnel count', 9, 'clinician_reported', TRUE),
('hidradenitis_suppurativa', ARRAY['HS'], 'HS-PGA', 9, 'clinician_reported', TRUE),
('hidradenitis_suppurativa', ARRAY['HS'], 'Hurley stage', 8, 'clinician_reported', FALSE),
('hidradenitis_suppurativa', ARRAY['HS'], 'DLQI', 8, 'patient_reported', TRUE),
('hidradenitis_suppurativa', ARRAY['HS'], 'Pain NRS', 8, 'patient_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- Sjogren's Syndrome
INSERT INTO cs_validated_instruments (disease_key, disease_aliases, instrument_name, quality_score, instrument_type, regulatory_acceptance) VALUES
('sjogrens_syndrome', ARRAY['Sjogren', 'SS', 'pSS'], 'ESSDAI', 10, 'composite', TRUE),
('sjogrens_syndrome', ARRAY['Sjogren', 'SS', 'pSS'], 'ESSPRI', 9, 'patient_reported', TRUE),
('sjogrens_syndrome', ARRAY['Sjogren', 'SS', 'pSS'], 'ClinESSDAI', 9, 'composite', TRUE),
('sjogrens_syndrome', ARRAY['Sjogren', 'SS', 'pSS'], 'Schirmer test', 8, 'clinician_reported', TRUE),
('sjogrens_syndrome', ARRAY['Sjogren', 'SS', 'pSS'], 'Salivary flow', 8, 'clinician_reported', TRUE),
('sjogrens_syndrome', ARRAY['Sjogren', 'SS', 'pSS'], 'Ocular staining score', 8, 'clinician_reported', TRUE),
('sjogrens_syndrome', ARRAY['Sjogren', 'SS', 'pSS'], 'SF-36', 8, 'patient_reported', TRUE),
('sjogrens_syndrome', ARRAY['Sjogren', 'SS', 'pSS'], 'EQ-5D', 8, 'patient_reported', TRUE)
ON CONFLICT (disease_key, instrument_name) DO UPDATE SET quality_score = EXCLUDED.quality_score, updated_at = CURRENT_TIMESTAMP;

-- =====================================================
-- DEFAULT SCORING WEIGHTS
-- =====================================================
INSERT INTO cs_scoring_weights (therapeutic_area, description) VALUES
('default', 'Default scoring weights for all therapeutic areas'),
('rare_disease', 'Adjusted weights for rare diseases - lower sample size requirements'),
('autoimmune', 'Standard weights for autoimmune/inflammatory diseases'),
('oncology', 'Oncology-specific weights - higher emphasis on safety')
ON CONFLICT (therapeutic_area) DO NOTHING;

-- Update rare disease weights
UPDATE cs_scoring_weights SET
    weight_response_rate = 0.35,
    weight_safety = 0.30,
    weight_endpoint_quality = 0.20,
    weight_organ_breadth = 0.15
WHERE therapeutic_area = 'rare_disease';

-- Update oncology weights
UPDATE cs_scoring_weights SET
    weight_response_rate = 0.25,
    weight_safety = 0.40,
    weight_endpoint_quality = 0.25,
    weight_organ_breadth = 0.10
WHERE therapeutic_area = 'oncology';

