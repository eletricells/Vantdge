# Clinical Scoring Improvements for Drug Repurposing Case Series Agent

## Overview

This document outlines recommendations for enhancing the clinical scoring system in the `DrugRepurposingCaseSeriesAgent`. The key insight is that the multi-stage extraction pipeline now captures rich `detailed_efficacy_endpoints` and `detailed_safety_endpoints` data, but the scoring functions aren't yet leveraging this granular information.

The proposed changes introduce:
1. **Organ Domain Analysis** - Score breadth of response across organ systems
2. **Endpoint Quality Scoring** - Weight validated instruments higher than ad-hoc measures
3. **Enhanced Safety Scoring** - Granular AE analysis using detailed extraction
4. **Response Durability Scoring** - Reward sustained/long-term responses
5. **Revised Composite Scoring** - Restructured weights using new components

---

## 1. Organ Domain Analysis

Particularly valuable for autoimmune/inflammatory diseases where drugs often show differential efficacy across organ systems. Inspired by the pooled TULIP analysis approach for anifrolumab.

```python
# =============================================================================
# COMPREHENSIVE ORGAN DOMAIN KEYWORD MAPPING
# =============================================================================
# This mapping covers clinical endpoints, disease activity measures, and 
# anatomical terms across major organ systems. Keywords are lowercase for 
# case-insensitive matching.

ORGAN_DOMAINS = {
    'musculoskeletal': [
        # Joint-specific terms
        'joint', 'joints', 'arthritis', 'arthralgia', 'articular', 'synovitis',
        'synovial', 'polyarthritis', 'oligoarthritis', 'monoarthritis',
        'swollen joint', 'tender joint', 'sjc', 'tjc', 'sjc28', 'tjc28',
        'sjc66', 'tjc68', 'joint count', 'joint swelling', 'joint tenderness',
        'joint pain', 'joint stiffness', 'joint erosion', 'joint damage',
        'joint space narrowing', 'jadas', 'juvenile arthritis',
        
        # Rheumatoid arthritis measures
        'das28', 'das-28', 'das28-crp', 'das28-esr', 'das44',
        'acr20', 'acr50', 'acr70', 'acr-20', 'acr-50', 'acr-70',
        'acr response', 'acr criteria', 'acr/eular', 'eular response',
        'cdai', 'sdai', 'rapid3', 'boolean remission',
        
        # Functional measures
        'haq', 'haq-di', 'haq-s', 'health assessment questionnaire',
        'mhaq', 'grip strength', 'hand function', 'physical function',
        'functional capacity', 'functional status', 'disability index',
        
        # Morning stiffness
        'morning stiffness', 'am stiffness', 'stiffness duration',
        
        # Spondyloarthritis specific
        'basdai', 'basfi', 'basmi', 'asdas', 'asdas-crp', 'asdas-esr',
        'spinal mobility', 'spine', 'sacroiliac', 'sacroiliitis', 'axial',
        'axspa', 'ankylosing spondylitis', 'nr-axspa', 'r-axspa',
        'enthesitis', 'enthesopathy', 'lei', 'mases', 'sparcc',
        'dactylitis', 'sausage digit', 'leeds enthesitis',
        
        # Psoriatic arthritis specific
        'psa', 'psoriatic arthritis', 'mda', 'minimal disease activity',
        'dapsa', 'pasdas', 'cpdai', 'grappa', 'caspar',
        
        # Myositis/muscle
        'myositis', 'myopathy', 'muscle', 'muscular', 'muscle strength',
        'muscle weakness', 'proximal weakness', 'mmt', 'mmt8', 'mmt-8',
        'manual muscle test', 'cmas', 'childhood myositis', 'imacs',
        'total improvement score', 'tis', 'myositis response criteria',
        'creatine kinase', 'ck', 'aldolase', 'ldh', 'muscle enzyme',
        'dermatomyositis', 'polymyositis', 'ibm', 'inclusion body',
        'antisynthetase', 'necrotizing myopathy', 'imnm',
        
        # Bone/structural
        'bone', 'bone erosion', 'erosion', 'osteitis', 'bone marrow edema',
        'sharp score', 'van der heijde', 'modified sharp', 'genant',
        'radiographic progression', 'structural damage', 'mri bone',
        
        # Gout specific
        'gout', 'urate', 'uric acid', 'tophus', 'tophi', 'gout flare',
        'crystal', 'monosodium urate',
        
        # Other MSK
        'tendon', 'tendonitis', 'tenosynovitis', 'bursitis', 'fibromyalgia',
        'connective tissue', 'scleroderma', 'systemic sclerosis'
    ],
    
    'mucocutaneous': [
        # General skin terms
        'skin', 'cutaneous', 'dermatologic', 'dermal', 'epidermal',
        'rash', 'lesion', 'lesions', 'eruption', 'erythema',
        'induration', 'sclerosis', 'skin score', 'skin thickness',
        
        # Lupus skin measures
        'clasi', 'clasi-a', 'clasi-d', 'cutaneous lupus', 'cle',
        'discoid', 'dle', 'subacute cutaneous', 'scle', 'acle',
        'malar', 'malar rash', 'butterfly rash', 'photosensitivity',
        'lupus skin', 'lupus rash',
        
        # Dermatomyositis skin measures
        'cdasi', 'cdasi activity', 'cdasi damage', 'gottron',
        'heliotrope', 'periorbital', 'v-sign', 'shawl sign',
        'mechanic hands', 'calcinosis', 'cutaneous dermatomyositis',
        
        # Psoriasis measures
        'pasi', 'pasi50', 'pasi75', 'pasi90', 'pasi100', 'pasi-75',
        'pasi response', 'bsa', 'body surface area', 'plaque',
        'iga', 'iga 0/1', 'investigator global', 'spga', 'pga',
        'scalp psoriasis', 'palmoplantar', 'nail psoriasis', 'napsi',
        'ppasi', 'pssi', 'physician static global',
        
        # Atopic dermatitis measures
        'easi', 'easi-50', 'easi-75', 'easi-90', 'scorad', 'poem',
        'eczema', 'atopic', 'pruritus', 'itch', 'nrs itch', 'itch nrs',
        'peak pruritus', 'pp-nrs', 'aderm-ss', 'aderm-is', 'hads',
        'ida', 'ida score', 'iga-ad', 'viga-ad',
        
        # Alopecia measures
        'alopecia', 'hair', 'hair loss', 'hair regrowth', 'salt',
        'salt score', 'severity of alopecia tool', 'alodex', 'aat',
        'alopecia areata', 'androgenetic', 'scarring alopecia',
        'hair count', 'terminal hair', 'vellus', 'regrowth',
        
        # Vitiligo measures
        'vitiligo', 'vasi', 'vitiligo area', 'vetf', 'vscoring',
        'repigmentation', 'depigmentation', 'facial vitiligo', 'f-vasi',
        't-vasi', 'vie', 'vitiligo impact', 'bsa-v',
        
        # Hidradenitis measures
        'hidradenitis', 'his4', 'ihs4', 'an count', 'abscess',
        'hs-pga', 'hurley', 'sartorius', 'nodule', 'draining tunnel',
        
        # Scleroderma skin
        'mrss', 'modified rodnan', 'rodnan skin score', 'skin thickness',
        'skin fibrosis', 'digital ulcer', 'digital pitting', 'calcinosis',
        'raynaud', 'raynaud phenomenon', 'digital ischemia',
        
        # Oral/mucosal
        'mucosal', 'mucosa', 'oral', 'oral ulcer', 'mouth ulcer',
        'aphthous', 'stomatitis', 'nasal ulcer', 'genital ulcer',
        'mucocutaneous', 'mucous membrane',
        
        # Wound healing
        'wound', 'ulcer', 'ulceration', 'wound healing', 'epithelialization',
        
        # Other skin conditions
        'urticaria', 'angioedema', 'pemphigus', 'pemphigoid', 'bullous',
        'blistering', 'lichenoid', 'lichen planus', 'morphea',
        'granuloma', 'panniculitis', 'livedo', 'vasculitic skin',
        'pyoderma', 'pyoderma gangrenosum', 'erythema nodosum',
        'sweet syndrome', 'neutrophilic dermatosis'
    ],
    
    'renal': [
        # General renal terms
        'kidney', 'renal', 'nephro', 'nephrology', 'nephropathy',
        
        # Lupus nephritis specific
        'nephritis', 'lupus nephritis', 'ln', 'class iii', 'class iv',
        'class v', 'proliferative', 'membranous', 'mesangial',
        'glomerulonephritis', 'gn', 'glomerular',
        
        # Renal response criteria
        'complete renal response', 'crr', 'partial renal response', 'prr',
        'renal response', 'renal remission', 'renal flare', 'renal relapse',
        
        # Proteinuria measures
        'proteinuria', 'protein', 'upcr', 'urine protein', 'urine albumin',
        'uacr', 'albuminuria', 'protein creatinine ratio', '24-hour protein',
        '24h protein', 'spot urine', 'dipstick protein',
        
        # Kidney function
        'creatinine', 'serum creatinine', 'scr', 'gfr', 'egfr',
        'glomerular filtration', 'creatinine clearance', 'crcl',
        'ckd', 'chronic kidney', 'aki', 'acute kidney', 'kidney injury',
        'renal function', 'renal impairment', 'renal insufficiency',
        
        # Urinalysis
        'hematuria', 'rbc cast', 'red cell cast', 'urinary sediment',
        'active sediment', 'pyuria', 'wbc cast', 'granular cast',
        'urine microscopy',
        
        # Dialysis/ESRD
        'dialysis', 'esrd', 'end-stage renal', 'kidney failure',
        'renal replacement', 'transplant', 'kidney transplant',
        
        # Biopsy
        'renal biopsy', 'kidney biopsy', 'histologic', 'chronicity index',
        'activity index', 'nih class', 'isn/rps',
        
        # Other
        'bun', 'blood urea nitrogen', 'cystatin', 'cystatin c'
    ],
    
    'neurological': [
        # General neuro terms
        'neuro', 'neurologic', 'neurological', 'nervous system',
        'cns', 'central nervous', 'pns', 'peripheral nervous',
        
        # Cognitive/psychiatric
        'cognitive', 'cognition', 'cognitive impairment', 'brain fog',
        'memory', 'concentration', 'mental status', 'mmse',
        'moca', 'pasat', 'symbol digit', 'sdmt',
        'psychosis', 'psychotic', 'psychiatric', 'mood', 'depression',
        'anxiety', 'organic brain', 'encephalopathy', 'confusion',
        'delirium', 'altered mental',
        
        # Seizures
        'seizure', 'seizures', 'epilepsy', 'convulsion', 'epileptic',
        
        # Headache
        'headache', 'migraine', 'cephalalgia', 'intracranial hypertension',
        'pseudotumor',
        
        # Stroke/vascular
        'stroke', 'cva', 'cerebrovascular', 'tia', 'transient ischemic',
        'infarct', 'cerebral infarct', 'brain infarct', 'ischemic stroke',
        'hemorrhagic stroke', 'cerebral hemorrhage',
        
        # Neuropathy
        'neuropathy', 'peripheral neuropathy', 'polyneuropathy',
        'mononeuropathy', 'mononeuritis multiplex', 'cranial neuropathy',
        'cranial nerve', 'optic neuropathy', 'optic neuritis',
        'sensory neuropathy', 'motor neuropathy', 'autonomic neuropathy',
        'small fiber', 'large fiber', 'nerve conduction', 'emg',
        
        # Movement disorders
        'chorea', 'movement disorder', 'ataxia', 'cerebellar',
        'myelopathy', 'transverse myelitis', 'spinal cord',
        
        # MS specific
        'edss', 'expanded disability', 'relapse', 'relapse rate',
        'arr', 'annualized relapse', 'mri lesion', 't2 lesion',
        'gadolinium', 'gd-enhancing', 'brain volume', 'brain atrophy',
        'msfc', 'timed 25', 't25fw', '9-hole peg', '9hpt',
        'no evidence of disease activity', 'neda',
        
        # Other
        'aseptic meningitis', 'meningitis', 'encephalitis',
        'demyelinating', 'demyelination', 'white matter',
        'neuromyelitis', 'nmo', 'nmosd', 'myasthenia', 'guillain'
    ],
    
    'hematological': [
        # Red blood cells
        'anemia', 'anaemia', 'hemoglobin', 'hgb', 'hb', 'hematocrit', 'hct',
        'red blood cell', 'rbc', 'erythrocyte', 'hemolytic', 'hemolysis',
        'aiha', 'autoimmune hemolytic', 'coombs', 'direct antiglobulin',
        'reticulocyte', 'haptoglobin', 'ldh', 'bilirubin',
        
        # White blood cells
        'leukopenia', 'leucopenia', 'leukocyte', 'wbc', 'white blood cell',
        'lymphopenia', 'lymphocyte', 'alc', 'absolute lymphocyte',
        'neutropenia', 'neutrophil', 'anc', 'absolute neutrophil',
        'agranulocytosis', 'granulocyte',
        
        # Platelets
        'thrombocytopenia', 'platelet', 'plt', 'platelet count',
        'itp', 'immune thrombocytopenia', 'thrombocytopenic purpura',
        
        # Combined
        'cytopenia', 'cytopenias', 'pancytopenia', 'bicytopenia',
        'bone marrow', 'myelosuppression', 'hematologic',
        
        # Coagulation
        'coagulation', 'coagulopathy', 'bleeding', 'hemorrhage',
        'anticoagulant', 'lupus anticoagulant', 'antiphospholipid',
        'aps', 'anticardiolipin', 'anti-beta2', 'b2gp1',
        'thrombosis', 'thrombotic', 'clotting',
        
        # Other
        'evans syndrome', 'ttp', 'hus', 'hemophagocytic', 'hlh',
        'macrophage activation', 'mas', 'felty'
    ],
    
    'cardiopulmonary': [
        # Cardiac general
        'cardiac', 'heart', 'cardiovascular', 'cv', 'myocardial',
        'cardiomyopathy', 'heart failure', 'chf', 'ef', 'ejection fraction',
        'lvef', 'left ventricular', 'diastolic', 'systolic',
        
        # Pericardial/endocardial
        'pericarditis', 'pericardial', 'pericardial effusion',
        'myocarditis', 'endocarditis', 'libman-sacks', 'valvular',
        
        # Arrhythmia
        'arrhythmia', 'conduction', 'heart block', 'qt prolongation',
        'atrial fibrillation', 'afib',
        
        # Vascular
        'vasculitis', 'vascular', 'arteritis', 'aortitis',
        'coronary', 'cad', 'atherosclerosis',
        
        # Pulmonary general
        'lung', 'pulmonary', 'respiratory', 'pneumo',
        
        # ILD specific
        'ild', 'interstitial lung', 'interstitial pneumonia',
        'pulmonary fibrosis', 'ipf', 'nsip', 'uip', 'organizing pneumonia',
        'ground glass', 'honeycombing', 'traction bronchiectasis',
        'hrct', 'high resolution ct',
        
        # PFTs
        'fvc', 'forced vital capacity', 'fev1', 'dlco', 'diffusing capacity',
        'tlco', 'pft', 'pulmonary function', 'spirometry', 'lung function',
        '6mwd', '6-minute walk', 'six minute walk', '6mwt',
        
        # PAH specific
        'pah', 'pulmonary arterial hypertension', 'pulmonary hypertension',
        'ph', 'mpap', 'mean pulmonary', 'pvr', 'pulmonary vascular resistance',
        'right heart', 'rvsp', 'tricuspid regurgitation', 'rhc',
        'right heart catheterization', 'who functional class', 'nyha',
        'borg dyspnea', 'reveal score',
        
        # Pleural
        'pleuritis', 'pleural', 'pleural effusion', 'pleurisy',
        
        # Other
        'pneumonitis', 'alveolitis', 'dah', 'diffuse alveolar hemorrhage',
        'shrinking lung', 'diaphragm', 'hypoxia', 'oxygen', 'spo2',
        'dyspnea', 'shortness of breath', 'cough', 'sgrq', 'k-bild'
    ],
    
    'immunological': [
        # Complement
        'complement', 'c3', 'c4', 'ch50', 'c3a', 'c5a', 'hypocomplementemia',
        'low complement', 'complement consumption', 'complement activation',
        
        # Autoantibodies - general
        'autoantibody', 'autoantibodies', 'antibody', 'antibodies',
        'ana', 'antinuclear', 'anti-nuclear', 'ana titer',
        
        # Lupus specific antibodies
        'anti-dsdna', 'dsdna', 'ds-dna', 'double-stranded dna',
        'anti-smith', 'anti-sm', 'anti-rnp', 'anti-u1rnp',
        'anti-ssa', 'anti-ro', 'anti-ssb', 'anti-la',
        'anti-ribosomal p', 'ribosomal p',
        
        # Other disease-specific antibodies
        'anca', 'anti-neutrophil', 'pr3', 'mpo', 'c-anca', 'p-anca',
        'anti-jo1', 'antisynthetase', 'anti-mda5', 'anti-mi2',
        'anti-nxp2', 'anti-tif1', 'myositis specific', 'msa',
        'anti-ccp', 'acpa', 'citrullinated', 'rf', 'rheumatoid factor',
        'anti-scl70', 'anti-centromere', 'anti-rna polymerase',
        
        # Inflammatory markers
        'crp', 'c-reactive', 'esr', 'sed rate', 'sedimentation rate',
        'ferritin', 'procalcitonin', 'calprotectin',
        
        # Immunoglobulins
        'immunoglobulin', 'igg', 'iga', 'igm', 'ige', 'ig level',
        'hypergammaglobulinemia', 'hypogammaglobulinemia',
        
        # Interferon/cytokines
        'interferon', 'ifn', 'type i interferon', 'ifn signature',
        'ifn score', 'ifn-alpha', 'ifn-gamma', 'ifi27', 'ifi44',
        'cytokine', 'il-6', 'il-1', 'il-17', 'il-18', 'tnf',
        'interleukin', 'chemokine', 'cxcl', 'ccl',
        
        # Lymphocyte subsets
        'b cell', 'cd19', 'cd20', 'b lymphocyte', 'plasma cell',
        't cell', 'cd4', 'cd8', 't lymphocyte', 't helper', 'treg',
        'nk cell', 'natural killer', 'cd56',
        
        # Serologic
        'serologic', 'serology', 'serological', 'seroconversion',
        'seronegativity', 'seropositivity',
        
        # Other
        'immune complex', 'cryoglobulin', 'cold agglutinin'
    ],
    
    'systemic': [
        # Lupus composite measures
        'sledai', 'sledai-2k', 'selena-sledai', 'safety sledai',
        'bilag', 'bilag-2004', 'bilag index', 'bilag a', 'bilag b',
        'sri', 'sri-4', 'sri-5', 'sri-6', 'sri-7', 'sri-8', 'sri response',
        'bicla', 'british isles lupus', 'lldas', 'lupus low disease',
        'doris', 'definition of remission', 'lupus remission',
        'slicc', 'slicc/acr', 'damage index', 'sdi',
        
        # Vasculitis composite measures
        'bvas', 'bvas/wg', 'birmingham vasculitis', 'bvas v3',
        'vdi', 'vasculitis damage index', 'vcrc',
        'five factor score', 'ffs',
        
        # General disease activity
        'disease activity', 'global disease activity', 'global assessment',
        'physician global', 'pga', 'mdga', 'patient global', 'ptga',
        'disease severity', 'disease state', 'active disease',
        'remission', 'low disease activity', 'lda', 'inactive disease',
        'flare', 'disease flare', 'relapse', 'exacerbation',
        
        # Response measures
        'responder', 'response', 'clinical response', 'treatment response',
        'improvement', 'clinical improvement', 'partial response', 'cr', 'pr',
        
        # Steroid sparing
        'steroid', 'glucocorticoid', 'corticosteroid', 'prednisone',
        'prednisolone', 'steroid dose', 'steroid sparing', 'steroid taper',
        'steroid reduction', 'steroid discontinuation', 'steroid-free',
        'gc dose', 'daily prednisone', 'cumulative steroid',
        
        # Quality of life
        'qol', 'quality of life', 'hrqol', 'health-related quality',
        'sf-36', 'sf36', 'short form 36', 'sf-12',
        'eq-5d', 'eq5d', 'euroqol', 'vas', 'visual analog',
        'facit', 'facit-f', 'facit-fatigue', 'fatigue',
        'lupusqol', 'sleqol', 'dlqi', 'dermatology life quality',
        'work productivity', 'wpai', 'absenteeism', 'presenteeism',
        
        # Constitutional symptoms
        'fatigue', 'malaise', 'fever', 'weight loss', 'night sweats',
        'constitutional', 'systemic symptoms'
    ],
    
    'gastrointestinal': [
        # General GI
        'gi', 'gastrointestinal', 'digestive', 'bowel', 'intestinal',
        'abdominal', 'abdomen', 'gut',
        
        # IBD measures
        'mayo', 'mayo score', 'partial mayo', 'total mayo',
        'endoscopic mayo', 'uc mayo', 'modified mayo',
        'cdai', 'crohn disease activity', 'harvey-bradshaw', 'hbi',
        'ses-cd', 'simple endoscopic', 'cdeis',
        'rutgeerts', 'postoperative recurrence',
        'ibdq', 'ibd questionnaire', 'sibdq',
        'fecal calprotectin', 'fc', 'lactoferrin',
        'endoscopic remission', 'mucosal healing', 'histologic remission',
        'clinical remission', 'steroid-free remission',
        
        # Specific conditions
        'ulcerative colitis', 'uc', 'crohn', 'crohn disease', 'cd',
        'colitis', 'enteritis', 'ileitis', 'proctitis',
        'pouchitis', 'fistula', 'fistulizing', 'stricture',
        
        # Symptoms
        'diarrhea', 'bloody stool', 'rectal bleeding', 'urgency',
        'stool frequency', 'bowel movement', 'constipation',
        'abdominal pain', 'cramping', 'bloating', 'nausea', 'vomiting',
        
        # Hepatic
        'hepatic', 'liver', 'hepato', 'hepatobiliary',
        'alt', 'ast', 'transaminase', 'lfts', 'liver function',
        'alkaline phosphatase', 'alp', 'ggt', 'bilirubin',
        'hepatitis', 'hepatotoxicity', 'dili', 'drug-induced liver',
        'cirrhosis', 'fibrosis', 'fibroscan', 'steatosis',
        'autoimmune hepatitis', 'aih', 'pbc', 'psc',
        
        # Other
        'dysphagia', 'esophageal', 'esophagitis', 'gastroparesis',
        'pancreatitis', 'pancreatic', 'peritonitis', 'ascites',
        'mesenteric', 'intestinal pseudo-obstruction', 'malabsorption'
    ],
    
    'ocular': [
        # General eye terms
        'eye', 'ocular', 'ophthalmic', 'ophthalmologic', 'visual',
        
        # Uveitis
        'uveitis', 'anterior uveitis', 'posterior uveitis', 'panuveitis',
        'intermediate uveitis', 'uveal', 'iritis', 'iridocyclitis',
        'choroiditis', 'chorioretinitis', 'vitritis', 'vitreous',
        'sun criteria', 'sun grading', 'anterior chamber cells',
        'vitreous haze', 'cystoid macular edema', 'cme',
        
        # Scleritis/episcleritis
        'scleritis', 'episcleritis', 'scleral', 'necrotizing scleritis',
        
        # Retinal
        'retinal', 'retina', 'retinopathy', 'retinal vasculitis',
        'cotton wool', 'retinal hemorrhage', 'vascular occlusion',
        'optic', 'optic nerve', 'optic neuritis', 'papillitis',
        
        # Vision measures
        'visual acuity', 'bcva', 'best corrected', 'etdrs', 'snellen',
        'logmar', 'visual field', 'perimetry', 'contrast sensitivity',
        'color vision', 'vision loss', 'blindness',
        
        # Other
        'dry eye', 'keratoconjunctivitis', 'sicca', 'xerophthalmia',
        'schirmer', 'tear film', 'corneal', 'keratitis',
        'conjunctivitis', 'conjunctival', 'orbital', 'proptosis',
        'diplopia', 'strabismus', 'ptosis', 'eyelid',
        'oct', 'optical coherence', 'fluorescein angiography', 'fa',
        'indocyanine green', 'icg', 'fundus', 'fundoscopy'
    ],
    
    'constitutional': [
        # Fatigue
        'fatigue', 'tiredness', 'exhaustion', 'asthenia', 'malaise',
        'facit-fatigue', 'facit-f', 'fss', 'fatigue severity scale',
        'brief fatigue', 'bfi', 'multidimensional fatigue',
        
        # Fever
        'fever', 'febrile', 'temperature', 'pyrexia',
        
        # Weight
        'weight', 'weight loss', 'cachexia', 'wasting', 'bmi',
        'body mass index', 'weight gain', 'anorexia',
        
        # Sleep
        'sleep', 'insomnia', 'sleep disturbance', 'sleep quality',
        'psqi', 'pittsburgh sleep',
        
        # Other constitutional
        'night sweats', 'diaphoresis', 'chills', 'rigors',
        'lymphadenopathy', 'lymph node', 'splenomegaly', 'hepatomegaly'
    ]
}

def _score_organ_domain_breadth(self, ext: CaseSeriesExtraction) -> Tuple[float, Dict[str, Any]]:
    """
    Score based on breadth and consistency of response across organ domains.
    
    Higher scores for drugs showing improvement across multiple organ systems.
    Uses comprehensive keyword matching across 11 organ domains.
    
    Returns:
        Tuple of (score, details_dict) where details contains domain breakdown
    """
    
    detailed_eps = getattr(ext, 'detailed_efficacy_endpoints', []) or []
    
    domains_with_response = set()
    domain_results = {}
    
    for ep in detailed_eps:
        ep_dict = ep if isinstance(ep, dict) else ep.model_dump() if hasattr(ep, 'model_dump') else {}
        ep_name = (ep_dict.get('endpoint_name') or '').lower()
        
        for domain, keywords in ORGAN_DOMAINS.items():
            if any(kw in ep_name for kw in keywords):
                # Check if this represents a positive response
                is_positive = self._is_positive_response(ep_dict)
                
                if is_positive:
                    domains_with_response.add(domain)
                    if domain not in domain_results:
                        domain_results[domain] = []
                    domain_results[domain].append({
                        'endpoint': ep_dict.get('endpoint_name'),
                        'result': ep_dict.get('responders_pct') or ep_dict.get('percent_change'),
                        'significant': ep_dict.get('statistical_significance')
                    })
                break  # Each endpoint only counts for one domain
    
    # Score based on breadth of organ domain response
    n_domains = len(domains_with_response)
    if n_domains >= 5:
        score = 10.0
    elif n_domains == 4:
        score = 9.0
    elif n_domains == 3:
        score = 7.5
    elif n_domains == 2:
        score = 6.0
    elif n_domains == 1:
        score = 4.0
    else:
        score = 3.0  # No domain data available - neutral
    
    return score, {
        'domains_responding': list(domains_with_response),
        'n_domains': n_domains,
        'domain_details': domain_results
    }


def _is_positive_response(self, ep_dict: Dict[str, Any]) -> bool:
    """
    Determine if an endpoint represents a positive/favorable response.
    """
    # Statistical significance is strong signal
    if ep_dict.get('statistical_significance'):
        return True
    
    # Response rate above threshold
    responders_pct = ep_dict.get('responders_pct') or ep_dict.get('response_rate_pct')
    if responders_pct and responders_pct > 30:
        return True
    
    # Percent change (negative = improvement for most disease scores)
    pct_change = ep_dict.get('percent_change')
    if pct_change is not None and pct_change < -20:
        return True
    
    # Change from baseline (negative = improvement)
    change = ep_dict.get('change_from_baseline')
    if change is not None and change < 0:
        return True
    
    return False
```

---

## 2. Endpoint Quality Scoring

Not all endpoints are equal. Validated clinical instruments and primary endpoints should score higher than ad-hoc measures. 

### Approach: Hybrid Hardcoded + Dynamic Lookup

For a drug with 30+ diseases, we use a **hybrid approach**:

1. **Comprehensive hardcoded base** - Covers validated instruments across major disease areas (catches ~80% of cases)
2. **Dynamic LLM lookup** - If hardcoded matching finds <2 validated instruments for a disease, trigger LLM + web search
3. **Cache results** - Store LLM-determined instruments in database for future runs

```python
# =============================================================================
# COMPREHENSIVE VALIDATED INSTRUMENTS DATABASE
# =============================================================================
# Quality scores: 10 = regulatory-accepted primary endpoint
#                 9 = validated composite, widely used in trials  
#                 8 = validated PRO or secondary endpoint
#                 7 = established clinical measure
#                 6 = supportive/exploratory endpoint
#                 5 = biomarker (mechanistic, not clinical)

VALIDATED_INSTRUMENTS = {
    # =========================================================================
    # SYSTEMIC LUPUS ERYTHEMATOSUS (SLE)
    # =========================================================================
    # Composite response measures (FDA-accepted)
    'sri-4': 10, 'sri-5': 10, 'sri-6': 10, 'sri-7': 10, 'sri-8': 10,
    'sri': 10, 'sle responder index': 10,
    'bicla': 9, 'british isles lupus assessment': 9,
    
    # Disease activity indices
    'sledai': 9, 'sledai-2k': 9, 'selena-sledai': 9, 'safety of estrogens': 9,
    'bilag': 9, 'bilag-2004': 9, 'bilag index': 9,
    'bilag a': 8, 'bilag b': 8, 'bilag c': 7,
    'slam': 8, 'slam-r': 8, 'systemic lupus activity measure': 8,
    'eclam': 8, 'european consensus': 8,
    
    # Remission/low disease activity
    'lldas': 8, 'lupus low disease activity': 8,
    'doris': 8, 'definition of remission': 8,
    
    # Damage
    'sdi': 8, 'slicc damage': 8, 'slicc/acr damage': 8, 'damage index': 8,
    
    # Lupus skin
    'clasi': 9, 'clasi-a': 9, 'clasi-d': 8, 'cutaneous lupus': 8,
    'clasi activity': 9, 'clasi damage': 8,
    
    # Lupus nephritis
    'complete renal response': 10, 'crr': 10,
    'partial renal response': 9, 'prr': 9,
    'overall renal response': 9, 'orr': 9,
    'renal response': 9, 'renal remission': 9,
    
    # Lupus flare
    'sfi': 8, 'selena flare index': 8, 'severe flare': 8, 'mild/moderate flare': 7,
    
    # =========================================================================
    # RHEUMATOID ARTHRITIS
    # =========================================================================
    # ACR response (FDA primary endpoints)
    'acr20': 9, 'acr50': 10, 'acr70': 10, 'acr-20': 9, 'acr-50': 10, 'acr-70': 10,
    'acr response': 9, 'acr criteria': 9, 'acr/eular': 9,
    
    # Disease activity scores
    'das28': 9, 'das-28': 9, 'das28-crp': 9, 'das28-esr': 9, 'das44': 8,
    'cdai': 9, 'clinical disease activity': 9,
    'sdai': 9, 'simplified disease activity': 9,
    'rapid3': 7, 'rapid-3': 7,
    
    # Remission criteria
    'boolean remission': 10, 'acr/eular remission': 10,
    'das28 remission': 9, 'das28 < 2.6': 9,
    'cdai remission': 9, 'cdai ≤ 2.8': 9, 'cdai <= 2.8': 9,
    'sdai remission': 9, 'sdai ≤ 3.3': 9, 'sdai <= 3.3': 9,
    
    # Low disease activity
    'lda': 8, 'low disease activity': 8,
    'das28 lda': 8, 'cdai lda': 8,
    
    # EULAR response
    'eular response': 8, 'eular good': 9, 'eular moderate': 7,
    
    # Functional
    'haq': 8, 'haq-di': 8, 'health assessment questionnaire': 8,
    'haq disability': 8, 'mhaq': 7, 'mcid haq': 8,
    
    # Structural/radiographic
    'modified sharp': 9, 'sharp score': 9, 'van der heijde': 9,
    'total sharp score': 9, 'tss': 9,
    'erosion score': 8, 'jsn score': 8, 'joint space narrowing': 8,
    'radiographic progression': 9, 'structural progression': 9,
    'genant': 8, 'larsen': 7,
    
    # Joint counts
    'sjc': 7, 'tjc': 7, 'sjc28': 7, 'tjc28': 7, 'swollen joint count': 7,
    'tender joint count': 7, 'sjc66': 7, 'tjc68': 7,
    
    # =========================================================================
    # PSORIATIC ARTHRITIS
    # =========================================================================
    'acr20 psa': 9, 'acr50 psa': 10, 'acr70 psa': 10,
    'mda': 9, 'minimal disease activity': 9, 'psa mda': 9,
    'dapsa': 9, 'disease activity psoriatic': 9,
    'dapsa remission': 9, 'dapsa lda': 8,
    'pasdas': 8, 'psoriatic arthritis disease activity': 8,
    'cpdai': 8, 'composite psoriatic': 8,
    'grappa': 8, 'grace': 7,
    'lei': 7, 'leeds enthesitis': 7, 'enthesitis count': 7,
    'dactylitis count': 7, 'dactylitis severity': 7,
    
    # =========================================================================
    # AXIAL SPONDYLOARTHRITIS / ANKYLOSING SPONDYLITIS
    # =========================================================================
    'asas20': 9, 'asas40': 10, 'asas-20': 9, 'asas-40': 10,
    'asas response': 9, 'asas partial remission': 9,
    'asas-pr': 9, 'asas pr': 9,
    'asdas': 9, 'asdas-crp': 9, 'asdas-esr': 9,
    'asdas inactive': 9, 'asdas < 1.3': 9, 'asdas major improvement': 9,
    'asdas clinically important': 8,
    'basdai': 8, 'bath ankylosing': 8, 'basdai 50': 9,
    'basfi': 8, 'bath function': 8,
    'basmi': 8, 'bath metrology': 8,
    'mases': 7, 'maastricht enthesitis': 7,
    'sparcc': 8, 'sparcc mri': 8,
    
    # =========================================================================
    # DERMATOMYOSITIS / POLYMYOSITIS / MYOSITIS
    # =========================================================================
    # IMACS core set measures (ACR/EULAR)
    'tis': 9, 'total improvement score': 9,
    'imacs': 9, 'imacs response': 9,
    'acr/eular myositis': 9, 'myositis response criteria': 9,
    'minimal improvement': 8, 'moderate improvement': 9, 'major improvement': 10,
    
    # Muscle strength
    'mmt': 8, 'mmt-8': 8, 'mmt8': 8, 'manual muscle test': 8,
    'mmt-24': 8, 'mmt24': 8,
    
    # Pediatric myositis
    'cmas': 9, 'childhood myositis assessment': 9, 'cmas-14': 9,
    'printo': 8, 'printo criteria': 8,
    
    # Skin (dermatomyositis)
    'cdasi': 9, 'cdasi activity': 9, 'cdasi damage': 8,
    'cdasi-a': 9, 'cdasi-d': 8,
    'myositis disease activity': 8, 'mdaat': 8,
    
    # Physician/patient global
    'mdga': 8, 'myositis physician global': 8,
    'ptga myositis': 7, 'patient global myositis': 7,
    
    # Extramuscular
    'myositis damage index': 8, 'mdi': 8,
    'mdaat': 8, 'myositis disease activity assessment tool': 8,
    'hai': 7, 'health assessment': 7,
    
    # =========================================================================
    # PSORIASIS (CUTANEOUS)
    # =========================================================================
    'pasi': 9, 'pasi 50': 8, 'pasi 75': 9, 'pasi 90': 10, 'pasi 100': 10,
    'pasi-50': 8, 'pasi-75': 9, 'pasi-90': 10, 'pasi-100': 10,
    'pasi50': 8, 'pasi75': 9, 'pasi90': 10, 'pasi100': 10,
    
    'iga': 9, 'iga 0/1': 10, 'iga clear': 10, 'iga 0': 10, 'iga 1': 9,
    'iga mod 2011': 9, 'spga': 9, 'static physician global': 9,
    'iga psoriasis': 9, 'investigator global': 9,
    
    'bsa': 7, 'body surface area': 7, 'bsa psoriasis': 7,
    'pga': 8, 'physician global assessment': 8,
    'pga x bsa': 8, 'pasi x bsa': 8,
    
    # Special psoriasis sites
    'napsi': 8, 'nail psoriasis severity': 8, 'nail pasi': 8,
    'pssi': 8, 'scalp psoriasis': 8, 'scalp iga': 8,
    'ppasi': 8, 'palmoplantar': 8, 'pp-iga': 8, 'pppasi': 8,
    'gpppga': 8, 'generalized pustular': 8,
    
    # =========================================================================
    # ATOPIC DERMATITIS
    # =========================================================================
    'easi': 9, 'easi 50': 8, 'easi 75': 9, 'easi 90': 10,
    'easi-50': 8, 'easi-75': 9, 'easi-90': 10,
    
    'iga-ad': 9, 'viga-ad': 9, 'iga 0/1 ad': 10,
    'iga clear/almost clear': 10, 'validated iga': 9,
    
    'scorad': 8, 'scorad 50': 8, 'scorad 75': 9,
    'poem': 8, 'patient-oriented eczema': 8,
    'adderm-ss': 8, 'adderm-is': 8,
    
    # Itch
    'pp-nrs': 9, 'peak pruritus nrs': 9, 'itch nrs': 8,
    'nrs itch': 8, 'worst itch': 8, 'pruritus nrs': 8,
    'pruritus vas': 7, '5-d itch': 7,
    
    'dlqi': 8, 'dermatology life quality': 8,
    'cdlqi': 8, 'children dermatology life quality': 8,
    
    # =========================================================================
    # ALOPECIA AREATA
    # =========================================================================
    'salt': 9, 'salt score': 9, 'severity of alopecia tool': 9,
    'salt 30': 8, 'salt 50': 9, 'salt 75': 9, 'salt 90': 10,
    'salt30': 8, 'salt50': 9, 'salt75': 9, 'salt90': 10,
    'salt ≤ 20': 9, 'salt <= 20': 9,
    'absolute salt': 9, 'relative salt': 8,
    
    'alodex': 8, 'alopecia density': 8,
    'aat': 7, 'alopecia areata tool': 7,
    'aasis': 7, 'alopecia areata symptom': 7,
    'cte-ae': 7, 'clinical trial endpoint': 7,
    'aa-pga': 7, 'aa iga': 7,
    'regrowth': 7, 'hair regrowth': 7, 'terminal hair': 7,
    
    # =========================================================================
    # VITILIGO
    # =========================================================================
    'f-vasi': 9, 'facial vitiligo': 9, 'face vasi': 9,
    't-vasi': 9, 'total vasi': 9, 'vasi': 9,
    'vasi 50': 8, 'vasi 75': 9, 'vasi 90': 10,
    'vetf': 8, 'vitiligo extent tensity': 8,
    'vie': 7, 'vitiligo impact': 7,
    'bsa-v': 7, 'vitiligo bsa': 7,
    'repigmentation': 8, 'f-bsa': 8, 'facial bsa': 8,
    'vns': 7, 'vitiligo noticeability': 7,
    
    # =========================================================================
    # HIDRADENITIS SUPPURATIVA
    # =========================================================================
    'his4': 9, 'ihs4': 9, 'international hidradenitis': 9,
    'hidradenitis clinical response': 9, 'hiscr': 9,
    'hiscr50': 9, 'hiscr75': 9, 'hiscr90': 10,
    'an count': 8, 'abscess and nodule': 8,
    'hs-pga': 8, 'hs pga': 8,
    'hurley stage': 7, 'hurley': 7, 'hurley i': 7, 'hurley ii': 7, 'hurley iii': 7,
    'sartorius score': 7, 'modified sartorius': 7,
    'draining tunnel': 7, 'fistula count': 7,
    'dlqi hs': 7, 'hidradenitis quality': 7,
    
    # =========================================================================
    # VASCULITIS (ANCA-ASSOCIATED AND OTHER)
    # =========================================================================
    'bvas': 9, 'bvas v3': 9, 'birmingham vasculitis': 9,
    'bvas/wg': 9, 'bvas/gpa': 9, 'bvas for wegeners': 9,
    'vdi': 8, 'vasculitis damage index': 8,
    'complete remission': 10, 'sustained remission': 10,
    'vcrc': 8, 'vasculitis clinical research': 8,
    'five factor score': 8, 'ffs': 8,
    'relapse-free': 9, 'relapse rate': 8,
    'anca negativity': 7, 'pr3 anca': 6, 'mpo anca': 6,
    
    # Giant cell arteritis
    'gca relapse': 8, 'gca remission': 9,
    'sustained gca remission': 9, 'steroid-free gca': 9,
    
    # Takayasu
    'itas': 8, 'indian takayasu': 8,
    'kerr criteria': 7,
    
    # =========================================================================
    # SYSTEMIC SCLEROSIS / SCLERODERMA
    # =========================================================================
    'mrss': 9, 'modified rodnan': 9, 'rodnan skin score': 9,
    'skin score': 8, 'skin thickness': 8, 'durometer': 7,
    
    # Lung (SSc-ILD)
    'fvc': 9, 'forced vital capacity': 9, 'fvc % predicted': 9,
    'dlco': 8, 'diffusing capacity': 8, 'dlco % predicted': 8,
    'fvc decline': 9, 'fvc stabilization': 9,
    
    # Function
    'shaq': 8, 'scleroderma haq': 8, 'shaq-di': 8,
    'sgrq': 8, 'st george respiratory': 8,
    'k-bild': 8, 'king brief ild': 8,
    
    # Digital ulcers
    'digital ulcer': 8, 'du healing': 8, 'new du': 8,
    'raynaud condition score': 7, 'rcs': 7,
    
    # Composite
    'criss': 8, 'acr criss': 8, 'combined response': 8,
    
    # =========================================================================
    # INFLAMMATORY BOWEL DISEASE (CROHN'S, UC)
    # =========================================================================
    # Ulcerative colitis
    'mayo score': 9, 'total mayo': 9, 'modified mayo': 9,
    'full mayo': 9, 'partial mayo': 8,
    'endoscopic mayo': 9, 'mayo endoscopic': 9, 'mes': 9,
    'mes 0': 10, 'mes 0/1': 9, 'endoscopic remission uc': 10,
    'clinical remission uc': 9, 'clinical response uc': 8,
    'stool frequency': 7, 'rectal bleeding': 7,
    'uceis': 8, 'ulcerative colitis endoscopic': 8,
    'pucai': 8, 'pediatric uc activity': 8,
    'robarts histopathology': 7, 'nancy histological': 7,
    
    # Crohn's disease
    'cdai': 9, 'crohn disease activity': 9, 'cdai 100': 8, 'cdai 150': 9,
    'cdai remission': 9, 'cdai < 150': 9, 'cdai response': 8,
    'harvey-bradshaw': 8, 'hbi': 8, 'harvey bradshaw index': 8,
    'ses-cd': 9, 'simple endoscopic score': 9, 'endoscopic remission cd': 10,
    'cdeis': 8, 'crohn disease endoscopic': 8,
    'pcdai': 8, 'pediatric crohn': 8,
    
    # Both IBD
    'mucosal healing': 10, 'endoscopic healing': 10,
    'histologic remission': 9, 'histologic healing': 9,
    'corticosteroid-free remission': 9, 'steroid-free remission': 9,
    'deep remission': 10, 'clinical + endoscopic remission': 10,
    'ibdq': 8, 'ibd questionnaire': 8, 'sibdq': 7,
    'fecal calprotectin': 7, 'fc': 7, 'calprotectin': 7,
    'fistula response': 8, 'fistula healing': 9, 'fistula closure': 9,
    
    # =========================================================================
    # MULTIPLE SCLEROSIS
    # =========================================================================
    'edss': 9, 'expanded disability': 9, 'edss progression': 9,
    'edss confirmed': 9, 'cdp': 9, 'confirmed disability progression': 9,
    '12-week cdp': 9, '24-week cdp': 9,
    'arr': 9, 'annualized relapse rate': 9, 'relapse rate': 9,
    'relapse-free': 9, 'time to relapse': 8,
    'neda': 10, 'no evidence of disease activity': 10, 'neda-3': 10, 'neda-4': 10,
    'mri activity': 8, 'new t2': 8, 'gd-enhancing': 8, 'gadolinium': 8,
    't2 lesion volume': 8, 'brain volume': 8, 'brain atrophy': 8, 'pbvc': 8,
    'msfc': 8, 'ms functional composite': 8,
    't25fw': 8, 'timed 25-foot walk': 8, '25-foot walk': 8,
    '9hpt': 8, '9-hole peg test': 8, 'nine-hole peg': 8,
    'pasat': 7, 'symbol digit': 7, 'sdmt': 7,
    
    # =========================================================================
    # GOUT
    # =========================================================================
    'gout flare': 8, 'flare rate': 8, 'time to first flare': 8,
    'serum urate': 8, 'sua': 8, 'uric acid': 8, 'sua < 6': 9,
    'sua target': 9, 'sua < 5': 9,
    'tophus': 8, 'tophus resolution': 9, 'target tophus': 9,
    'tophus volume': 8, 'dect': 7, 'dual energy ct': 7,
    
    # =========================================================================
    # JUVENILE IDIOPATHIC ARTHRITIS (JIA)
    # =========================================================================
    'jia acr30': 9, 'jia acr50': 9, 'jia acr70': 10, 'jia acr90': 10,
    'jadas': 9, 'jadas-27': 9, 'jadas-71': 9, 'jadas-10': 9,
    'jadas inactive': 10, 'jadas remission': 10,
    'jia inactive disease': 10, 'wallace criteria': 9,
    'chaq': 8, 'childhood haq': 8,
    'jspada': 8, 'juvenile spa': 8,
    
    # =========================================================================
    # SYSTEMIC JIA / ADULT-ONSET STILL'S DISEASE
    # =========================================================================
    'sjia acr30': 9, 'sjia response': 9,
    'fever resolution': 8, 'fever-free': 8,
    'rash resolution': 7, 'systemic features': 8,
    'ferritin normalization': 7, 'crp normalization': 7,
    'inactive systemic disease': 9, 'clinically inactive': 9,
    'aosd response': 8, 'pouchot': 7,
    
    # =========================================================================
    # UVEITIS
    # =========================================================================
    'sun criteria': 9, 'sun grading': 9, 'sun uveitis': 9,
    'anterior chamber cells': 8, 'acc': 8, 'ac cell grade': 8,
    'vitreous haze': 8, 'vh': 8, 'vitreous haze grade': 8,
    'bcva': 8, 'best corrected visual acuity': 8, 'visual acuity': 8,
    'uveitis recurrence': 8, 'uveitis-free': 9,
    'corticosteroid-sparing': 9, 'steroid-sparing': 9,
    'cme resolution': 8, 'macular edema': 8,
    
    # =========================================================================
    # BEHCET'S DISEASE
    # =========================================================================
    'bdcaf': 8, 'behcet disease current activity': 8,
    'oral ulcer recurrence': 8, 'genital ulcer': 7,
    'pathergy': 6, 'behcet response': 8,
    
    # =========================================================================
    # SJOGREN'S SYNDROME
    # =========================================================================
    'essdai': 9, 'eular sjogren disease activity': 9,
    'esspri': 8, 'eular sjogren patient reported': 8,
    'schirmer': 7, 'schirmer test': 7,
    'unstimulated salivary': 7, 'usf': 7, 'stimulated salivary': 7,
    'ocular staining': 7, 'oss': 7,
    'clin-essdai': 9, 'clinical essdai': 9,
    
    # =========================================================================
    # QUALITY OF LIFE / PRO MEASURES (CROSS-DISEASE)
    # =========================================================================
    'sf-36': 8, 'sf36': 8, 'short form 36': 8, 'sf-36 pcs': 8, 'sf-36 mcs': 8,
    'sf-12': 7, 'sf12': 7,
    'eq-5d': 8, 'eq5d': 8, 'euroqol': 8, 'eq-5d-5l': 8, 'eq-vas': 7,
    'haq': 8, 'haq-di': 8, 'health assessment questionnaire': 8,
    'promis': 8, 'promis-29': 8, 'promis physical function': 8,
    'promis fatigue': 7, 'promis pain': 7, 'promis sleep': 7,
    'facit': 7, 'facit-f': 8, 'facit-fatigue': 8,
    'brief fatigue': 7, 'bfi': 7,
    'fss': 7, 'fatigue severity scale': 7,
    'dlqi': 8, 'dermatology life quality index': 8,
    'wpai': 7, 'work productivity': 7,
    'vas': 6, 'visual analog scale': 6, 'vas pain': 6, 'vas fatigue': 6,
    'nrs': 6, 'numeric rating scale': 6, 'pain nrs': 6,
    'pga': 7, 'patient global assessment': 7, 'ptga': 7,
    'physician global': 7, 'mdga': 7,
    
    # =========================================================================
    # BIOMARKERS (Supportive, not clinical endpoints)
    # =========================================================================
    'crp': 5, 'c-reactive protein': 5, 'hs-crp': 5,
    'esr': 5, 'sed rate': 5, 'sedimentation rate': 5,
    'ferritin': 5, 'serum ferritin': 5,
    'complement': 5, 'c3': 5, 'c4': 5, 'ch50': 5,
    'anti-dsdna': 6, 'dsdna': 6, 'ds-dna': 6,
    'anca': 5, 'pr3': 5, 'mpo': 5,
    'rf': 5, 'rheumatoid factor': 5,
    'anti-ccp': 6, 'acpa': 6,
    'ifn signature': 6, 'interferon signature': 6, 'ifn score': 6,
    'gene expression': 5, 'gene signature': 5,
    'cytokine': 5, 'il-6': 5, 'tnf': 5,
    'ck': 5, 'creatine kinase': 5, 'aldolase': 5,
    'calprotectin': 6, 'fecal calprotectin': 6,
    
    # =========================================================================
    # STEROID SPARING (Important for autoimmune)
    # =========================================================================
    'steroid': 7, 'glucocorticoid': 7, 'prednisone': 7, 'corticosteroid': 7,
    'steroid dose': 7, 'gc dose': 7, 'daily prednisone': 7,
    'steroid reduction': 8, 'steroid taper': 8, 'steroid sparing': 8,
    'steroid-free': 9, 'steroid free': 9, 'corticosteroid-free': 9,
    'prednisone < 7.5': 8, 'prednisone ≤ 7.5': 8, 'prednisone <= 7.5': 8,
    'prednisone < 5': 9, 'prednisone ≤ 5': 9,
    'cumulative steroid': 7, 'cumulative glucocorticoid': 7,
}


# =============================================================================
# DYNAMIC INSTRUMENT LOOKUP (Hybrid Approach)
# =============================================================================

def _get_validated_instruments_for_disease(
    self, 
    disease: str, 
    ext: CaseSeriesExtraction
) -> Dict[str, int]:
    """
    Get validated instruments for a specific disease.
    
    Uses hybrid approach:
    1. Check hardcoded VALIDATED_INSTRUMENTS for matches
    2. If <2 instruments found, trigger LLM lookup
    3. Cache results for future use
    
    Args:
        disease: Disease name (e.g., "dermatomyositis", "lupus nephritis")
        ext: Extraction object for context
        
    Returns:
        Dict mapping instrument names to quality scores (1-10)
    """
    # First, check hardcoded instruments
    matched_instruments = {}
    detailed_eps = getattr(ext, 'detailed_efficacy_endpoints', []) or []
    
    for ep in detailed_eps:
        ep_dict = ep if isinstance(ep, dict) else ep.model_dump() if hasattr(ep, 'model_dump') else {}
        ep_name = (ep_dict.get('endpoint_name') or '').lower()
        
        for instrument, score in VALIDATED_INSTRUMENTS.items():
            if instrument in ep_name:
                matched_instruments[instrument] = score
                break
    
    # If we found sufficient matches, return hardcoded results
    if len(matched_instruments) >= 2:
        logger.debug(f"Found {len(matched_instruments)} validated instruments via hardcoded lookup for {disease}")
        return matched_instruments
    
    # Otherwise, trigger dynamic LLM lookup
    logger.info(f"Insufficient hardcoded matches ({len(matched_instruments)}) for {disease}, triggering LLM lookup")
    
    # Check cache first
    if self.cs_db:
        cached = self.cs_db.get_cached_instruments(disease)
        if cached:
            logger.info(f"Using cached validated instruments for {disease}")
            return cached
    
    # LLM lookup with web search
    dynamic_instruments = self._lookup_validated_instruments_llm(disease)
    
    # Merge with hardcoded matches
    merged = {**dynamic_instruments, **matched_instruments}
    
    # Cache for future use
    if self.cs_db and dynamic_instruments:
        self.cs_db.cache_instruments(disease, dynamic_instruments)
    
    return merged


def _lookup_validated_instruments_llm(self, disease: str) -> Dict[str, int]:
    """
    Use LLM with web search to identify validated clinical endpoints for a disease.
    
    Returns:
        Dict mapping instrument names to quality scores
    """
    if not self.web_search:
        return {}
    
    # Search for validated endpoints
    self.search_count += 1
    results = self.web_search.search(
        f'"{disease}" validated clinical endpoints outcome measures FDA trials',
        max_results=5
    )
    
    if not results:
        return {}
    
    prompt = f"""Identify the validated clinical endpoints and outcome measures used in clinical trials for {disease}.

Search Results:
{json.dumps(results, indent=2)[:5000]}

Return ONLY valid JSON mapping endpoint names to quality scores (1-10):
- 10 = FDA-accepted primary endpoint for this indication
- 9 = Validated composite measure, widely used in Phase 3 trials
- 8 = Validated PRO or established secondary endpoint
- 7 = Common clinical measure with good psychometric properties
- 6 = Exploratory endpoint or biomarker with clinical relevance

Example format:
{{
    "sledai-2k": 9,
    "sri-4": 10,
    "clasi": 9,
    "anti-dsdna": 6
}}

Focus on:
1. Composite response criteria (e.g., ACR20, SRI-4, ASAS40)
2. Disease activity indices (e.g., DAS28, SLEDAI, CDAI)
3. Validated organ-specific measures (e.g., CLASI, CDASI, SALT)
4. Established PROs (e.g., HAQ, SF-36, disease-specific QoL)
5. Regulatory-accepted endpoints for this indication

Return ONLY the JSON, no other text."""

    try:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        self._track_tokens(response.usage)
        
        content = self._clean_json_response(response.content[0].text.strip())
        instruments = json.loads(content)
        
        # Validate and normalize
        validated = {}
        for name, score in instruments.items():
            if isinstance(score, (int, float)) and 1 <= score <= 10:
                validated[name.lower()] = int(score)
        
        logger.info(f"LLM identified {len(validated)} validated instruments for {disease}")
        return validated
        
    except Exception as e:
        logger.error(f"Error in LLM instrument lookup for {disease}: {e}")
        return {}


def _score_endpoint_quality(self, ext: CaseSeriesExtraction) -> float:
    """
    Score based on quality and validation level of endpoints used.
    
    Uses hybrid approach: hardcoded instruments + dynamic LLM lookup.
    
    Returns:
        Float score 1-10
    """
    disease = ext.disease_normalized or ext.disease
    
    # Get validated instruments (hybrid: hardcoded + dynamic)
    instruments = self._get_validated_instruments_for_disease(disease, ext)
    
    detailed_eps = getattr(ext, 'detailed_efficacy_endpoints', []) or []
    
    if not detailed_eps:
        # Fall back to basic efficacy info
        if ext.efficacy.primary_endpoint:
            return 6.0  # Has primary endpoint defined
        return 5.0  # Default
    
    endpoint_scores = []
    
    for ep in detailed_eps:
        ep_dict = ep if isinstance(ep, dict) else ep.model_dump() if hasattr(ep, 'model_dump') else {}
        ep_name = (ep_dict.get('endpoint_name') or '').lower()
        ep_category = (ep_dict.get('endpoint_category') or '').lower()
        
        # Base score from instrument validation level
        base_score = 4.0  # Ad-hoc measure default
        
        for instrument, inst_score in VALIDATED_INSTRUMENTS.items():
            if instrument in ep_name:
                base_score = inst_score
                break
        
        # Modifiers
        # +1 for primary endpoint designation
        if 'primary' in ep_category or ep_dict.get('is_primary'):
            base_score = min(base_score + 1.0, 10.0)
        
        # +1 for statistical significance
        if ep_dict.get('statistical_significance'):
            base_score = min(base_score + 1.0, 10.0)
        
        # +0.5 for having p-value reported (even if not significant)
        if ep_dict.get('p_value'):
            base_score = min(base_score + 0.5, 10.0)
        
        # -1 for exploratory endpoints
        if 'exploratory' in ep_category:
            base_score = max(base_score - 1.0, 1.0)
        
        endpoint_scores.append(base_score)
    
    # Return weighted average (primary endpoints count more)
    if endpoint_scores:
        return sum(endpoint_scores) / len(endpoint_scores)
    return 5.0
```

---

## 3. Enhanced Safety Scoring

Granular safety scoring using detailed safety endpoints to identify specific concerning signals. Safety terminology is more standardized (MedDRA) so we can use a comprehensive hardcoded approach.

```python
# =============================================================================
# COMPREHENSIVE SAFETY SIGNAL CLASSIFICATION
# =============================================================================
# Based on MedDRA System Organ Classes (SOC) and common safety concerns
# for immunomodulatory drugs. Each category includes preferred terms (PTs)
# and lower-level terms (LLTs) commonly seen in case series.

SAFETY_SIGNAL_CATEGORIES = {
    # =========================================================================
    # INFECTIONS (Critical for immunomodulators)
    # =========================================================================
    'serious_infection': {
        'severity': 'high',
        'score_penalty': 2.0,
        'terms': [
            # Bacterial
            'sepsis', 'septicemia', 'bacteremia', 'bacterial infection',
            'pneumonia', 'bacterial pneumonia', 'community-acquired pneumonia',
            'hospital-acquired pneumonia', 'aspiration pneumonia',
            'cellulitis', 'abscess', 'skin abscess', 'soft tissue infection',
            'osteomyelitis', 'septic arthritis', 'endocarditis',
            'meningitis', 'bacterial meningitis', 'encephalitis',
            'pyelonephritis', 'urinary tract infection', 'uti', 'urosepsis',
            'cholecystitis', 'cholangitis', 'appendicitis', 'diverticulitis',
            'peritonitis', 'intra-abdominal infection', 'intra-abdominal abscess',
            'clostridium difficile', 'c diff', 'c. difficile', 'cdiff',
            
            # Viral
            'herpes zoster', 'shingles', 'zoster', 'disseminated zoster',
            'ophthalmic zoster', 'herpes simplex', 'hsv', 'hsv reactivation',
            'cytomegalovirus', 'cmv', 'cmv reactivation', 'cmv infection',
            'ebv', 'epstein-barr', 'viral meningitis', 'viral encephalitis',
            'influenza', 'covid', 'covid-19', 'sars-cov-2',
            'hepatitis b reactivation', 'hbv reactivation',
            'jc virus', 'progressive multifocal leukoencephalopathy', 'pml',
            
            # Fungal
            'fungal infection', 'candidiasis', 'candidemia', 'invasive candida',
            'aspergillosis', 'invasive aspergillosis', 'aspergillus',
            'pneumocystis', 'pjp', 'pneumocystis jirovecii', 'pcp',
            'cryptococcosis', 'cryptococcal', 'histoplasmosis', 'coccidioidomycosis',
            'mucormycosis', 'zygomycosis',
            
            # Mycobacterial
            'tuberculosis', 'tb', 'tb reactivation', 'latent tb', 'active tb',
            'miliary tb', 'extrapulmonary tb', 'tuberculous',
            'ntm', 'nontuberculous mycobacteria', 'mac', 'mycobacterium avium',
            
            # Opportunistic
            'opportunistic infection', 'oi', 'listeria', 'listeriosis',
            'nocardia', 'nocardiosis', 'legionella', 'legionellosis',
            'toxoplasmosis', 'strongyloides', 'parasitic infection',
        ]
    },
    
    'non_serious_infection': {
        'severity': 'low',
        'score_penalty': 0.5,
        'terms': [
            'upper respiratory', 'uri', 'nasopharyngitis', 'pharyngitis',
            'sinusitis', 'bronchitis', 'rhinitis', 'common cold',
            'urinary tract infection mild', 'cystitis',
            'oral candidiasis', 'oral thrush', 'vaginal candidiasis',
            'conjunctivitis', 'otitis', 'otitis media',
            'skin infection', 'folliculitis', 'impetigo',
            'gastroenteritis', 'viral gastroenteritis',
            'herpes labialis', 'cold sore',
        ]
    },
    
    # =========================================================================
    # MALIGNANCIES (Critical - class warning for some drugs)
    # =========================================================================
    'malignancy': {
        'severity': 'critical',
        'score_penalty': 3.0,
        'terms': [
            # Hematologic
            'lymphoma', 'non-hodgkin lymphoma', 'nhl', 'hodgkin lymphoma',
            'leukemia', 'acute leukemia', 'chronic leukemia', 'cll', 'aml', 'all',
            'multiple myeloma', 'myeloma', 'myelodysplastic', 'mds',
            'lymphoproliferative', 'ptld', 'post-transplant lymphoproliferative',
            
            # Solid tumors
            'cancer', 'carcinoma', 'adenocarcinoma', 'squamous cell carcinoma',
            'malignancy', 'malignant neoplasm', 'tumor', 'tumour',
            'lung cancer', 'breast cancer', 'colon cancer', 'colorectal cancer',
            'prostate cancer', 'melanoma', 'skin cancer', 'basal cell', 'bcc',
            'hepatocellular carcinoma', 'hcc', 'pancreatic cancer',
            'renal cell carcinoma', 'rcc', 'bladder cancer',
            'ovarian cancer', 'cervical cancer', 'endometrial cancer',
            'gastric cancer', 'esophageal cancer', 'thyroid cancer',
            'brain tumor', 'glioma', 'meningioma',
            
            # Non-melanoma skin cancer
            'nmsc', 'non-melanoma skin cancer', 'keratinocyte carcinoma',
            'squamous cell skin', 'basal cell skin', 'actinic keratosis',
        ]
    },
    
    # =========================================================================
    # CARDIOVASCULAR EVENTS (MACE - class warning for JAK inhibitors)
    # =========================================================================
    'cardiovascular': {
        'severity': 'critical',
        'score_penalty': 2.5,
        'terms': [
            # MACE components
            'mace', 'major adverse cardiovascular', 'cardiovascular death',
            'myocardial infarction', 'mi', 'heart attack', 'stemi', 'nstemi',
            'acute coronary syndrome', 'acs', 'unstable angina',
            'stroke', 'cva', 'cerebrovascular accident', 'ischemic stroke',
            'hemorrhagic stroke', 'cerebral hemorrhage', 'intracranial hemorrhage',
            'transient ischemic attack', 'tia',
            
            # Heart failure
            'heart failure', 'chf', 'congestive heart failure',
            'cardiac failure', 'left ventricular dysfunction', 'lvd',
            'reduced ejection fraction', 'hfref', 'hfpef',
            'cardiomyopathy', 'dilated cardiomyopathy',
            
            # Arrhythmia
            'arrhythmia', 'atrial fibrillation', 'afib', 'atrial flutter',
            'ventricular tachycardia', 'vt', 'ventricular fibrillation', 'vf',
            'sudden cardiac death', 'cardiac arrest',
            'qt prolongation', 'long qt', 'torsades', 'torsades de pointes',
            'bradycardia', 'heart block', 'av block', 'sick sinus',
            
            # Inflammatory
            'myocarditis', 'pericarditis', 'pericardial effusion',
            'cardiac tamponade', 'endocarditis',
            
            # Vascular
            'hypertension', 'hypertensive crisis', 'malignant hypertension',
            'hypotension', 'orthostatic hypotension',
            'aortic dissection', 'aneurysm', 'aortic aneurysm',
        ]
    },
    
    # =========================================================================
    # THROMBOEMBOLIC EVENTS (VTE - class warning for JAK inhibitors)
    # =========================================================================
    'thromboembolic': {
        'severity': 'high',
        'score_penalty': 2.0,
        'terms': [
            'vte', 'venous thromboembolism',
            'deep vein thrombosis', 'dvt', 'deep venous thrombosis',
            'pulmonary embolism', 'pe', 'pulmonary thromboembolism',
            'thrombosis', 'thrombus', 'blood clot', 'clot',
            'thrombophlebitis', 'superficial thrombophlebitis',
            'portal vein thrombosis', 'pvt', 'hepatic vein thrombosis',
            'budd-chiari', 'mesenteric thrombosis', 'renal vein thrombosis',
            'cerebral venous thrombosis', 'cvt', 'sinus thrombosis',
            'retinal vein occlusion', 'rvo',
            'arterial thrombosis', 'arterial embolism',
        ]
    },
    
    # =========================================================================
    # HEPATOTOXICITY
    # =========================================================================
    'hepatotoxicity': {
        'severity': 'high',
        'score_penalty': 1.5,
        'terms': [
            'hepatotoxicity', 'drug-induced liver injury', 'dili',
            'hepatitis', 'drug-induced hepatitis', 'autoimmune hepatitis',
            'liver injury', 'hepatic injury', 'acute liver injury',
            'alt elevation', 'ast elevation', 'transaminase elevation',
            'elevated liver enzymes', 'elevated lfts', 'abnormal lfts',
            'hyperbilirubinemia', 'jaundice', 'cholestatic',
            'hepatic failure', 'liver failure', 'acute liver failure',
            'fulminant hepatitis', 'hepatic necrosis',
            'hy law', "hy's law",
            'alt > 3x uln', 'alt > 5x uln', 'alt > 10x uln',
            'hepatic steatosis', 'fatty liver', 'nash',
            'hepatomegaly', 'liver enlargement',
            'cirrhosis', 'portal hypertension', 'ascites',
            'hepatic encephalopathy', 'varices', 'variceal bleeding',
        ]
    },
    
    # =========================================================================
    # CYTOPENIAS
    # =========================================================================
    'cytopenia': {
        'severity': 'moderate',
        'score_penalty': 1.0,
        'terms': [
            # Neutropenia
            'neutropenia', 'neutropenic', 'low neutrophils', 'anc < 1000',
            'agranulocytosis', 'febrile neutropenia', 'severe neutropenia',
            'grade 3 neutropenia', 'grade 4 neutropenia',
            
            # Lymphopenia
            'lymphopenia', 'lymphocytopenia', 'low lymphocytes',
            'cd4 lymphopenia', 't cell depletion',
            
            # Anemia
            'anemia', 'anaemia', 'low hemoglobin', 'decreased hemoglobin',
            'hemolytic anemia', 'aplastic anemia', 'pure red cell aplasia',
            'prca', 'macrocytic anemia', 'microcytic anemia',
            
            # Thrombocytopenia
            'thrombocytopenia', 'low platelets', 'decreased platelets',
            'platelet count decreased', 'severe thrombocytopenia',
            'immune thrombocytopenia', 'itp',
            
            # Combined
            'pancytopenia', 'bicytopenia', 'bone marrow suppression',
            'myelosuppression', 'cytopenia', 'cytopenias',
        ]
    },
    
    # =========================================================================
    # GASTROINTESTINAL PERFORATION
    # =========================================================================
    'gi_perforation': {
        'severity': 'critical',
        'score_penalty': 2.5,
        'terms': [
            'gi perforation', 'gastrointestinal perforation',
            'bowel perforation', 'intestinal perforation',
            'gastric perforation', 'stomach perforation',
            'colonic perforation', 'colon perforation',
            'diverticular perforation', 'perforated diverticulitis',
            'esophageal perforation',
            'free air', 'pneumoperitoneum',
        ]
    },
    
    # =========================================================================
    # HYPERSENSITIVITY / INFUSION REACTIONS
    # =========================================================================
    'hypersensitivity': {
        'severity': 'moderate',
        'score_penalty': 1.0,
        'terms': [
            'anaphylaxis', 'anaphylactic', 'anaphylactoid',
            'hypersensitivity', 'allergic reaction', 'allergy',
            'angioedema', 'urticaria', 'hives',
            'infusion reaction', 'infusion-related reaction', 'irr',
            'injection site reaction', 'isr', 'injection site',
            'drug reaction', 'drug hypersensitivity',
            'serum sickness', 'serum sickness-like',
            'dress', 'drug rash eosinophilia',
            'stevens-johnson', 'sjs', 'toxic epidermal necrolysis', 'ten',
            'erythema multiforme',
        ]
    },
    
    # =========================================================================
    # NEUROLOGICAL
    # =========================================================================
    'neurological': {
        'severity': 'moderate',
        'score_penalty': 1.0,
        'terms': [
            'seizure', 'convulsion', 'epilepsy', 'status epilepticus',
            'encephalopathy', 'posterior reversible encephalopathy', 'pres',
            'peripheral neuropathy', 'neuropathy', 'paresthesia', 'numbness',
            'guillain-barre', 'gbs', 'cidp',
            'demyelinating', 'demyelination', 'ms-like',
            'optic neuritis', 'papilledema',
            'headache severe', 'migraine',
            'tremor', 'ataxia', 'dyskinesia',
            'confusion', 'altered mental status', 'delirium',
            'memory impairment', 'cognitive impairment',
            'dizziness', 'vertigo', 'syncope',
        ]
    },
    
    # =========================================================================
    # PULMONARY
    # =========================================================================
    'pulmonary': {
        'severity': 'high',
        'score_penalty': 1.5,
        'terms': [
            'interstitial lung disease', 'ild', 'pneumonitis',
            'drug-induced pneumonitis', 'hypersensitivity pneumonitis',
            'pulmonary fibrosis', 'organizing pneumonia', 'boop',
            'acute respiratory distress', 'ards',
            'respiratory failure', 'hypoxia', 'hypoxemia',
            'bronchospasm', 'bronchitis severe', 'asthma exacerbation',
            'pleural effusion', 'pleurisy', 'hemoptysis',
            'pulmonary hypertension', 'pah',
        ]
    },
    
    # =========================================================================
    # RENAL
    # =========================================================================
    'renal': {
        'severity': 'moderate',
        'score_penalty': 1.0,
        'terms': [
            'acute kidney injury', 'aki', 'acute renal failure',
            'chronic kidney disease', 'ckd', 'renal impairment',
            'nephrotoxicity', 'drug-induced nephrotoxicity',
            'creatinine increase', 'creatinine elevation', 'elevated creatinine',
            'decreased gfr', 'gfr decline',
            'proteinuria', 'nephrotic syndrome', 'glomerulonephritis',
            'tubulointerstitial nephritis', 'tin',
            'renal tubular acidosis', 'rta',
            'dialysis', 'esrd', 'end-stage renal',
        ]
    },
    
    # =========================================================================
    # DEATH
    # =========================================================================
    'death': {
        'severity': 'critical',
        'score_penalty': 4.0,
        'terms': [
            'death', 'died', 'fatal', 'mortality', 'deceased',
            'sudden death', 'unexplained death',
        ]
    },
    
    # =========================================================================
    # METABOLIC / LABORATORY
    # =========================================================================
    'metabolic': {
        'severity': 'low',
        'score_penalty': 0.5,
        'terms': [
            'hyperlipidemia', 'dyslipidemia', 'elevated cholesterol',
            'ldl increase', 'triglyceride increase', 'hypercholesterolemia',
            'hyperglycemia', 'diabetes', 'new-onset diabetes',
            'hypoglycemia', 'glucose intolerance',
            'hypokalemia', 'hyperkalemia', 'electrolyte abnormality',
            'hyponatremia', 'hypernatremia',
            'hypophosphatemia', 'hypomagnesemia',
            'elevated cpk', 'ck elevation', 'rhabdomyolysis',
            'tumor lysis syndrome', 'tls',
        ]
    },
    
    # =========================================================================
    # DISCONTINUATION
    # =========================================================================
    'discontinuation': {
        'severity': 'moderate',
        'score_penalty': 1.0,
        'terms': [
            'discontinuation', 'discontinued', 'withdrawal', 'withdrew',
            'treatment discontinuation', 'early termination',
            'stopped treatment', 'ceased treatment',
            'discontinuation due to ae', 'discontinued due to adverse',
            'intolerance', 'intolerable', 'lack of tolerability',
        ]
    },
}


def _score_safety_profile_detailed(self, ext: CaseSeriesExtraction) -> Tuple[float, Dict[str, Any]]:
    """
    Enhanced safety scoring using detailed safety endpoints and comprehensive
    MedDRA-aligned safety signal classification.
    
    Returns:
        Tuple of (score, safety_signals_dict)
    """
    detailed_safety = getattr(ext, 'detailed_safety_endpoints', []) or []
    n_patients = ext.patient_population.n_patients or 1
    
    # Initialize comprehensive safety signal tracking
    safety_signals = {
        'total_events': len(detailed_safety),
        'by_category': {},
        'sae_count': 0,
        'drug_related_sae': 0,
        'grade_3_4_events': 0,
        'discontinuations': 0,
        'deaths': 0,
        'concerning_events': []
    }
    
    # Initialize category counts
    for category in SAFETY_SIGNAL_CATEGORIES:
        safety_signals['by_category'][category] = {
            'count': 0,
            'events': [],
            'severity': SAFETY_SIGNAL_CATEGORIES[category]['severity'],
            'penalty': SAFETY_SIGNAL_CATEGORIES[category]['score_penalty']
        }
    
    if not detailed_safety:
        # Fall back to summary-level scoring
        return self._score_safety_profile(ext), safety_signals
    
    # Process each safety event
    for event in detailed_safety:
        ev_dict = event if isinstance(event, dict) else event.model_dump() if hasattr(event, 'model_dump') else {}
        event_name = (ev_dict.get('event_name') or '').lower()
        event_category = (ev_dict.get('event_category') or '').lower()
        
        # Check if serious
        is_serious = (
            ev_dict.get('is_serious') or 
            'sae' in event_category or 
            'serious' in event_category or
            'serious' in event_name
        )
        if is_serious:
            safety_signals['sae_count'] += 1
            
            relatedness = (ev_dict.get('relatedness') or '').lower()
            if 'related' in relatedness or 'possible' in relatedness or 'probable' in relatedness:
                safety_signals['drug_related_sae'] += 1
        
        # Check severity grade
        grade = str(ev_dict.get('grade') or '').lower()
        if any(g in grade for g in ['3', '4', '5', 'severe', 'life-threatening', 'fatal']):
            safety_signals['grade_3_4_events'] += 1
        
        # Categorize by safety signal type
        categorized = False
        for category, category_info in SAFETY_SIGNAL_CATEGORIES.items():
            for term in category_info['terms']:
                if term in event_name:
                    safety_signals['by_category'][category]['count'] += 1
                    safety_signals['by_category'][category]['events'].append({
                        'event': event_name,
                        'patients': ev_dict.get('n_patients_affected'),
                        'serious': is_serious,
                        'related': ev_dict.get('relatedness')
                    })
                    categorized = True
                    
                    # Track high-severity events
                    if category_info['severity'] in ['critical', 'high']:
                        safety_signals['concerning_events'].append({
                            'event': event_name,
                            'category': category,
                            'severity': category_info['severity'],
                            'patients': ev_dict.get('n_patients_affected')
                        })
                    
                    # Special tracking
                    if category == 'death':
                        safety_signals['deaths'] += 1
                    if category == 'discontinuation':
                        safety_signals['discontinuations'] += 1
                    
                    break
            if categorized:
                break
    
    # Calculate score (start at 10, deduct for concerning signals)
    score = 10.0
    
    # Deductions by category
    for category, category_data in safety_signals['by_category'].items():
        if category_data['count'] > 0:
            # Calculate rate
            rate = (category_data['count'] / n_patients) * 100
            penalty = category_data['penalty']
            
            # Apply penalty based on rate and severity
            if category_data['severity'] == 'critical':
                # Any critical event is significant
                score -= min(penalty * category_data['count'], penalty * 2)
            elif category_data['severity'] == 'high':
                if rate > 10:
                    score -= penalty * 1.5
                elif rate > 5:
                    score -= penalty
                elif category_data['count'] > 0:
                    score -= penalty * 0.5
            elif category_data['severity'] == 'moderate':
                if rate > 20:
                    score -= penalty
                elif rate > 10:
                    score -= penalty * 0.5
            elif category_data['severity'] == 'low':
                if rate > 30:
                    score -= penalty
    
    # Additional deductions for overall SAE rate
    overall_sae_rate = (safety_signals['sae_count'] / n_patients) * 100
    if overall_sae_rate > 30:
        score -= 1.5
    elif overall_sae_rate > 20:
        score -= 1.0
    elif overall_sae_rate > 15:
        score -= 0.5
    
    # Ensure score stays in bounds
    score = max(min(score, 10.0), 1.0)
    
    return score, safety_signals
```

---

## 4. Response Durability Scoring

Reward sustained and long-term responses over transient effects.

```python
def _score_response_durability(self, ext: CaseSeriesExtraction) -> float:
    """
    Score based on durability and sustainability of clinical response.
    
    Long-term sustained responses score higher than short-term or
    transient responses. Important for chronic diseases.
    
    Returns:
        Float score 1-10
    """
    detailed_eps = getattr(ext, 'detailed_efficacy_endpoints', []) or []
    
    # Track longest timepoint with positive response
    durability_signals = []
    
    # Timepoint patterns with scores
    LONG_TERM_PATTERNS = [
        ('year 2', 10), ('104 week', 10), ('96 week', 10),
        ('year 1', 9), ('52 week', 9), ('48 week', 9), ('12 month', 9),
        ('36 week', 8), ('9 month', 8),
    ]
    
    MEDIUM_TERM_PATTERNS = [
        ('24 week', 7), ('26 week', 7), ('6 month', 7),
        ('20 week', 6.5), ('5 month', 6.5),
        ('16 week', 6), ('4 month', 6),
    ]
    
    SHORT_TERM_PATTERNS = [
        ('12 week', 5), ('3 month', 5),
        ('8 week', 4), ('2 month', 4),
        ('4 week', 3), ('1 month', 3),
        ('2 week', 2),
    ]
    
    ALL_PATTERNS = LONG_TERM_PATTERNS + MEDIUM_TERM_PATTERNS + SHORT_TERM_PATTERNS
    
    for ep in detailed_eps:
        ep_dict = ep if isinstance(ep, dict) else ep.model_dump() if hasattr(ep, 'model_dump') else {}
        timepoint = (ep_dict.get('timepoint') or '').lower()
        
        # Only count if endpoint shows positive response
        if not self._is_positive_response(ep_dict):
            continue
        
        for pattern, score in ALL_PATTERNS:
            if pattern in timepoint:
                durability_signals.append(score)
                break
    
    # Check duration_of_response field for qualitative indicators
    dor = (ext.efficacy.duration_of_response or '').lower()
    DURABILITY_KEYWORDS = {
        'sustained': 8, 'maintained': 8, 'durable': 8, 'persistent': 7,
        'long-term': 8, 'ongoing': 7, 'continued': 7,
        'stable': 6, 'consistent': 6
    }
    
    for keyword, score in DURABILITY_KEYWORDS.items():
        if keyword in dor:
            durability_signals.append(score)
            break
    
    # Check follow-up duration as additional signal
    follow_up = (ext.follow_up_duration or '').lower()
    for pattern, score in ALL_PATTERNS:
        if pattern in follow_up:
            # Follow-up duration gives context but endpoints are more important
            durability_signals.append(score * 0.8)
            break
    
    if durability_signals:
        # Use max score (longest/most durable response)
        # with small bonus for multiple long-term endpoints
        max_score = max(durability_signals)
        long_term_count = sum(1 for s in durability_signals if s >= 7)
        bonus = min(long_term_count * 0.2, 1.0)
        return min(max_score + bonus, 10.0)
    
    # Default if no durability data
    return 5.0


def _score_extraction_completeness(self, ext: CaseSeriesExtraction) -> float:
    """
    Score based on completeness of data extraction.
    
    More complete extraction = higher confidence in the data.
    
    Returns:
        Float score 1-10
    """
    completeness_score = 0.0
    max_points = 10.0
    
    # Check for detailed endpoints (4 points)
    detailed_efficacy = getattr(ext, 'detailed_efficacy_endpoints', []) or []
    detailed_safety = getattr(ext, 'detailed_safety_endpoints', []) or []
    
    if len(detailed_efficacy) >= 5:
        completeness_score += 2.0
    elif len(detailed_efficacy) >= 2:
        completeness_score += 1.0
    
    if len(detailed_safety) >= 3:
        completeness_score += 2.0
    elif len(detailed_safety) >= 1:
        completeness_score += 1.0
    
    # Check for primary endpoint defined (1 point)
    if ext.efficacy.primary_endpoint:
        completeness_score += 1.0
    
    # Check for response rate quantified (1 point)
    if ext.efficacy.responders_pct or ext.efficacy.response_rate:
        completeness_score += 1.0
    
    # Check for safety summary (1 point)
    if ext.safety.safety_summary:
        completeness_score += 1.0
    
    # Check for follow-up duration (1 point)
    if ext.follow_up_duration:
        completeness_score += 1.0
    
    # Check for multi-stage extraction (1 point bonus)
    extraction_method = getattr(ext, 'extraction_method', None)
    if extraction_method == 'multi_stage':
        completeness_score += 1.0
    
    return min(completeness_score, max_points)
```

---

## 5. Revised Composite Scoring

Restructured scoring weights that leverage the new detailed components.

```python
def _score_opportunity(self, opp: RepurposingOpportunity) -> OpportunityScores:
    """
    Enhanced opportunity scoring using detailed endpoint data.
    
    SCORING WEIGHTS:
    
    Clinical Signal (50% of total):
      - Response magnitude: 25% (response rate, effect size)
      - Endpoint quality: 10% (validated instruments, primary endpoints)
      - Organ domain breadth: 10% (multi-system responses)
      - Safety profile: 5% (detailed AE analysis)
    
    Evidence Quality (25% of total):
      - Sample size: 10%
      - Publication venue: 5%
      - Follow-up duration: 5%
      - Extraction completeness: 5%
    
    Market Opportunity (25% of total):
      - Competitive landscape: 10%
      - Market size: 10%
      - Unmet need: 5%
    
    Returns:
        OpportunityScores object with all component scores
    """
    ext = opp.extraction
    
    # =========================================================================
    # CLINICAL SIGNAL COMPONENTS (50%)
    # =========================================================================
    
    # Response magnitude (25% of total = 50% of clinical)
    response_score = self._score_response_rate(ext)
    
    # Endpoint quality (10% of total = 20% of clinical)
    endpoint_quality_score = self._score_endpoint_quality(ext)
    
    # Organ domain breadth (10% of total = 20% of clinical)
    organ_score, organ_details = self._score_organ_domain_breadth(ext)
    
    # Safety profile (5% of total = 10% of clinical)
    safety_score, safety_details = self._score_safety_profile_detailed(ext)
    
    # Composite clinical score
    clinical_score = (
        response_score * 0.50 +
        endpoint_quality_score * 0.20 +
        organ_score * 0.20 +
        safety_score * 0.10
    )
    
    # =========================================================================
    # EVIDENCE QUALITY COMPONENTS (25%)
    # =========================================================================
    
    # Sample size (10% of total = 40% of evidence)
    sample_score = self._score_sample_size(ext)
    
    # Publication venue (5% of total = 20% of evidence)
    venue_score = self._score_publication_venue(ext)
    
    # Follow-up duration / durability (5% of total = 20% of evidence)
    durability_score = self._score_response_durability(ext)
    
    # Extraction completeness (5% of total = 20% of evidence)
    completeness_score = self._score_extraction_completeness(ext)
    
    # Composite evidence score
    evidence_score = (
        sample_score * 0.40 +
        venue_score * 0.20 +
        durability_score * 0.20 +
        completeness_score * 0.20
    )
    
    # =========================================================================
    # MARKET OPPORTUNITY COMPONENTS (25%)
    # =========================================================================
    
    # Competitive landscape (10% of total = 40% of market)
    competitors_score = self._score_competitors(opp)
    
    # Market size (10% of total = 40% of market)
    market_size_score = self._score_market_size(opp)
    
    # Unmet need (5% of total = 20% of market)
    unmet_need_score = self._score_unmet_need(opp)
    
    # Composite market score
    market_score = (
        competitors_score * 0.40 +
        market_size_score * 0.40 +
        unmet_need_score * 0.20
    )
    
    # =========================================================================
    # OVERALL PRIORITY SCORE
    # =========================================================================
    
    overall = (
        clinical_score * 0.50 +
        evidence_score * 0.25 +
        market_score * 0.25
    )
    
    # =========================================================================
    # BUILD SCORES OBJECT
    # =========================================================================
    
    return OpportunityScores(
        # Top-level dimension scores
        clinical_signal=round(clinical_score, 1),
        evidence_quality=round(evidence_score, 1),
        market_opportunity=round(market_score, 1),
        overall_priority=round(overall, 1),
        
        # Clinical breakdown
        response_rate_score=round(response_score, 1),
        safety_profile_score=round(safety_score, 1),
        clinical_breakdown={
            'response_magnitude': round(response_score, 1),
            'endpoint_quality': round(endpoint_quality_score, 1),
            'organ_domain_breadth': round(organ_score, 1),
            'safety_profile': round(safety_score, 1),
            # Include detailed analysis
            'organ_details': organ_details,
            'safety_details': safety_details
        },
        
        # Evidence breakdown
        sample_size_score=round(sample_score, 1),
        publication_venue_score=round(venue_score, 1),
        followup_duration_score=round(durability_score, 1),
        evidence_breakdown={
            'sample_size': round(sample_score, 1),
            'publication_venue': round(venue_score, 1),
            'response_durability': round(durability_score, 1),
            'extraction_completeness': round(completeness_score, 1)
        },
        
        # Market breakdown
        competitors_score=round(competitors_score, 1),
        market_size_score=round(market_size_score, 1),
        unmet_need_score=round(unmet_need_score, 1),
        market_breakdown={
            'competitive_landscape': round(competitors_score, 1),
            'market_size': round(market_size_score, 1),
            'unmet_need': round(unmet_need_score, 1)
        }
    )
```

---

## 6. Schema Updates Required

Add these fields to `OpportunityScores` in your schemas file:

```python
class OpportunityScores(BaseModel):
    """Scores for ranking repurposing opportunities."""
    
    # Top-level dimension scores (1-10)
    clinical_signal: float
    evidence_quality: float
    market_opportunity: float
    overall_priority: float
    
    # Clinical component scores
    response_rate_score: Optional[float] = None
    safety_profile_score: Optional[float] = None
    endpoint_quality_score: Optional[float] = None  # NEW
    organ_domain_score: Optional[float] = None  # NEW
    
    # Evidence component scores
    sample_size_score: Optional[float] = None
    publication_venue_score: Optional[float] = None
    followup_duration_score: Optional[float] = None
    extraction_completeness_score: Optional[float] = None  # NEW
    
    # Market component scores
    competitors_score: Optional[float] = None
    market_size_score: Optional[float] = None
    unmet_need_score: Optional[float] = None
    
    # Detailed breakdowns (for debugging/transparency)
    clinical_breakdown: Optional[Dict[str, Any]] = None
    evidence_breakdown: Optional[Dict[str, Any]] = None
    market_breakdown: Optional[Dict[str, Any]] = None
```

---

## 7. Excel Export Updates

Update `export_to_excel` to include the new scoring details:

```python
# In the Opportunities sheet, add these columns:
opp_data.append({
    # ... existing fields ...
    
    # New scoring columns
    'Endpoint Quality Score': opp.scores.clinical_breakdown.get('endpoint_quality') if opp.scores and opp.scores.clinical_breakdown else None,
    'Organ Breadth Score': opp.scores.clinical_breakdown.get('organ_domain_breadth') if opp.scores and opp.scores.clinical_breakdown else None,
    'Organ Domains': ', '.join(opp.scores.clinical_breakdown.get('organ_details', {}).get('domains_responding', [])) if opp.scores and opp.scores.clinical_breakdown else None,
    'Response Durability Score': opp.scores.evidence_breakdown.get('response_durability') if opp.scores and opp.scores.evidence_breakdown else None,
    'Extraction Completeness': opp.scores.evidence_breakdown.get('extraction_completeness') if opp.scores and opp.scores.evidence_breakdown else None,
    
    # Safety signal summary
    'Drug-Related SAEs': opp.scores.clinical_breakdown.get('safety_details', {}).get('drug_related_sae') if opp.scores and opp.scores.clinical_breakdown else None,
    'Serious Infections': opp.scores.clinical_breakdown.get('safety_details', {}).get('serious_infections') if opp.scores and opp.scores.clinical_breakdown else None,
    'Discontinuations': opp.scores.clinical_breakdown.get('safety_details', {}).get('discontinuations') if opp.scores and opp.scores.clinical_breakdown else None,
})
```

---

## 8. Configurable Weights by Therapeutic Area

Consider making scoring weights configurable based on therapeutic area:

```python
SCORING_WEIGHTS = {
    'rare_disease': {
        # Lower evidence weight (small samples expected)
        'clinical': 0.55,
        'evidence': 0.15,
        'market': 0.30,
        # Within evidence, lower sample size weight
        'evidence_sample_size': 0.20,
        'evidence_completeness': 0.40,
    },
    'autoimmune': {
        # Standard weights, emphasize organ breadth
        'clinical': 0.50,
        'evidence': 0.25,
        'market': 0.25,
        # Within clinical, higher organ breadth
        'clinical_organ_breadth': 0.25,
    },
    'oncology': {
        # Higher safety weight (toxicity critical)
        'clinical': 0.50,
        'evidence': 0.25,
        'market': 0.25,
        # Within clinical, higher safety
        'clinical_safety': 0.20,
    },
    'default': {
        'clinical': 0.50,
        'evidence': 0.25,
        'market': 0.25,
    }
}
```

---

## Summary of Changes

| Component | Current State | Proposed Enhancement |
|-----------|--------------|---------------------|
| Response Rate | Uses summary `responders_pct` or `efficacy_signal` enum | Same, validated against detailed endpoints |
| Safety Profile | Uses `sae_percentage` or `safety_profile` enum | Granular MedDRA-aligned classification with 13 categories |
| **NEW: Endpoint Quality** | Not scored | Hybrid: 200+ hardcoded instruments + dynamic LLM lookup |
| **NEW: Organ Domain Breadth** | Not scored | 11 organ domains with 500+ clinical terms |
| **NEW: Response Durability** | Follow-up duration only | Long-term vs short-term response maintenance |
| **NEW: Extraction Completeness** | Not scored | Confidence metric based on data completeness |
| Scoring Weights | Equal weights within dimensions | Configurable by therapeutic area |

---

## 9. Database Schema for Instrument Caching

Add this table to support the hybrid validated instruments lookup:

```sql
-- Table: validated_instruments_cache
-- Stores LLM-determined validated instruments per disease for reuse
CREATE TABLE IF NOT EXISTS validated_instruments_cache (
    id SERIAL PRIMARY KEY,
    disease_name VARCHAR(255) NOT NULL,
    disease_normalized VARCHAR(255),
    instruments JSONB NOT NULL,  -- {"sledai-2k": 9, "sri-4": 10, ...}
    source VARCHAR(50) DEFAULT 'llm_lookup',  -- 'llm_lookup' or 'manual'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,  -- Optional expiry for cache refresh
    lookup_query TEXT,  -- The search query used
    confidence_score FLOAT,  -- How confident we are in the results
    UNIQUE(disease_normalized)
);

-- Index for fast lookup
CREATE INDEX idx_instruments_disease ON validated_instruments_cache(disease_normalized);
CREATE INDEX idx_instruments_expires ON validated_instruments_cache(expires_at);
```

Add these methods to `CaseSeriesDatabase`:

```python
def get_cached_instruments(self, disease: str) -> Optional[Dict[str, int]]:
    """Get cached validated instruments for a disease."""
    if not self.is_available:
        return None
    
    disease_normalized = self._normalize_disease_name(disease)
    
    try:
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT instruments 
                FROM validated_instruments_cache 
                WHERE disease_normalized = :disease
                AND (expires_at IS NULL OR expires_at > NOW())
            """), {"disease": disease_normalized})
            
            row = result.fetchone()
            if row:
                return row[0]  # JSONB returns as dict
        return None
    except Exception as e:
        logger.error(f"Error fetching cached instruments: {e}")
        return None


def cache_instruments(
    self, 
    disease: str, 
    instruments: Dict[str, int],
    expires_days: int = 90
) -> bool:
    """Cache validated instruments for a disease."""
    if not self.is_available:
        return False
    
    disease_normalized = self._normalize_disease_name(disease)
    
    try:
        with self.engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO validated_instruments_cache 
                    (disease_name, disease_normalized, instruments, expires_at)
                VALUES 
                    (:disease, :normalized, :instruments, NOW() + INTERVAL ':days days')
                ON CONFLICT (disease_normalized) 
                DO UPDATE SET 
                    instruments = :instruments,
                    updated_at = NOW(),
                    expires_at = NOW() + INTERVAL ':days days'
            """), {
                "disease": disease,
                "normalized": disease_normalized,
                "instruments": json.dumps(instruments),
                "days": expires_days
            })
            conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error caching instruments: {e}")
        return False
```

---

## 10. Implementation Priority

Recommended implementation order:

1. **Phase 1 - Quick Wins** (1-2 days)
   - Add comprehensive `ORGAN_DOMAINS` keywords (copy from this doc)
   - Add comprehensive `VALIDATED_INSTRUMENTS` hardcoded list
   - Update `_score_opportunity()` to use new component scores
   - Update Excel export with new columns

2. **Phase 2 - Safety Enhancement** (1 day)
   - Add `SAFETY_SIGNAL_CATEGORIES` with MedDRA-aligned terms
   - Implement `_score_safety_profile_detailed()`
   - Add safety breakdown to Excel export

3. **Phase 3 - Dynamic Lookup** (2-3 days)
   - Add database table for instrument caching
   - Implement `_get_validated_instruments_for_disease()`
   - Implement `_lookup_validated_instruments_llm()`
   - Test with diseases not in hardcoded list

4. **Phase 4 - Refinement** (ongoing)
   - Add configurable weights by therapeutic area
   - Tune scoring thresholds based on real results
   - Add more disease-specific instruments to hardcoded list
   - Build out organ domain analysis visualization

---

## 11. Testing Recommendations

```python
def test_organ_domain_scoring():
    """Test organ domain breadth scoring with known case series."""
    
    # Test case: Baricitinib in dermatomyositis (multi-organ response)
    test_endpoints = [
        {"endpoint_name": "CDASI Activity Score", "responders_pct": 75},
        {"endpoint_name": "MMT-8 improvement", "responders_pct": 60},
        {"endpoint_name": "HAQ-DI change", "change_from_baseline": -0.5},
        {"endpoint_name": "Physician Global Assessment", "responders_pct": 70},
        {"endpoint_name": "CK normalization", "responders_pct": 80},
    ]
    
    # Should identify: mucocutaneous (CDASI), musculoskeletal (MMT-8, HAQ), 
    # systemic (PGA), immunological/biomarker (CK)
    # Expected score: 4+ domains = 9-10
    
    
def test_endpoint_quality_scoring():
    """Test endpoint quality with validated vs ad-hoc measures."""
    
    # High quality endpoints (validated)
    validated_eps = [
        {"endpoint_name": "ACR50 response", "endpoint_category": "Primary"},
        {"endpoint_name": "DAS28-CRP remission", "statistical_significance": True},
    ]
    # Expected score: 9-10
    
    # Low quality endpoints (ad-hoc)
    adhoc_eps = [
        {"endpoint_name": "Patient-reported improvement"},
        {"endpoint_name": "Investigator assessment of response"},
    ]
    # Expected score: 4-5


def test_safety_scoring():
    """Test safety scoring with concerning vs benign AE profiles."""
    
    # Concerning profile
    concerning_safety = [
        {"event_name": "Herpes zoster", "is_serious": True},
        {"event_name": "Pneumonia", "is_serious": True},
        {"event_name": "DVT", "is_serious": True},
    ]
    # Expected score: 3-5
    
    # Benign profile
    benign_safety = [
        {"event_name": "Headache", "is_serious": False},
        {"event_name": "Nasopharyngitis", "is_serious": False},
        {"event_name": "Nausea", "is_serious": False},
    ]
    # Expected score: 8-10
```

These changes should significantly improve the discriminatory power of your scoring system, particularly for differentiating high-quality clinical signals from weak ones, while keeping computational costs reasonable through the hybrid caching approach.
