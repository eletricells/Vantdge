-- =====================================================
-- DISEASE MAPPINGS SEED DATA
-- Comprehensive disease name variants and parent mappings
-- for improved ClinicalTrials.gov and market intelligence searches
-- =====================================================

-- Clear existing data (optional - comment out to preserve existing mappings)
-- TRUNCATE cs_disease_name_variants, cs_disease_parent_mappings;

-- =====================================================
-- DISEASE NAME VARIANTS
-- Maps canonical disease names to alternative names, abbreviations, synonyms
-- =====================================================

-- DERMATOLOGY
INSERT INTO cs_disease_name_variants (canonical_name, variant_name, variant_type, source, confidence) VALUES
-- Atopic Dermatitis
('Atopic Dermatitis', 'AD', 'abbreviation', 'manual', 1.0),
('Atopic Dermatitis', 'atopic eczema', 'synonym', 'manual', 1.0),
('Atopic Dermatitis', 'eczema', 'common_name', 'manual', 0.9),
('Atopic Dermatitis', 'neurodermatitis', 'synonym', 'manual', 0.8),
('Atopic Dermatitis', 'atopic dermatitis eczema', 'synonym', 'manual', 1.0),
-- Psoriasis
('Psoriasis', 'plaque psoriasis', 'subtype', 'manual', 1.0),
('Psoriasis', 'psoriasis vulgaris', 'synonym', 'manual', 1.0),
('Psoriasis', 'chronic plaque psoriasis', 'subtype', 'manual', 1.0),
('Psoriasis', 'PsO', 'abbreviation', 'manual', 0.9),
-- Alopecia Areata
('Alopecia Areata', 'AA', 'abbreviation', 'manual', 1.0),
('Alopecia Areata', 'alopecia totalis', 'subtype', 'manual', 1.0),
('Alopecia Areata', 'alopecia universalis', 'subtype', 'manual', 1.0),
('Alopecia Areata', 'patchy alopecia', 'subtype', 'manual', 1.0),
('Alopecia Areata', 'autoimmune alopecia', 'synonym', 'manual', 0.9),
-- Hidradenitis Suppurativa
('Hidradenitis Suppurativa', 'HS', 'abbreviation', 'manual', 1.0),
('Hidradenitis Suppurativa', 'acne inversa', 'synonym', 'manual', 1.0),
('Hidradenitis Suppurativa', 'hidradenitis', 'common_name', 'manual', 0.9),
-- Vitiligo
('Vitiligo', 'nonsegmental vitiligo', 'subtype', 'manual', 1.0),
('Vitiligo', 'segmental vitiligo', 'subtype', 'manual', 1.0),
('Vitiligo', 'generalized vitiligo', 'subtype', 'manual', 1.0),
-- Prurigo Nodularis
('Prurigo Nodularis', 'PN', 'abbreviation', 'manual', 1.0),
('Prurigo Nodularis', 'nodular prurigo', 'synonym', 'manual', 1.0),
-- Chronic Spontaneous Urticaria
('Chronic Spontaneous Urticaria', 'CSU', 'abbreviation', 'manual', 1.0),
('Chronic Spontaneous Urticaria', 'chronic urticaria', 'synonym', 'manual', 1.0),
('Chronic Spontaneous Urticaria', 'chronic idiopathic urticaria', 'synonym', 'manual', 1.0),
('Chronic Spontaneous Urticaria', 'CIU', 'abbreviation', 'manual', 1.0),

-- RHEUMATOLOGY
-- Rheumatoid Arthritis
('Rheumatoid Arthritis', 'RA', 'abbreviation', 'manual', 1.0),
('Rheumatoid Arthritis', 'rheumatoid', 'common_name', 'manual', 0.8),
('Rheumatoid Arthritis', 'seropositive rheumatoid arthritis', 'subtype', 'manual', 1.0),
('Rheumatoid Arthritis', 'seronegative rheumatoid arthritis', 'subtype', 'manual', 1.0),
-- Psoriatic Arthritis
('Psoriatic Arthritis', 'PsA', 'abbreviation', 'manual', 1.0),
('Psoriatic Arthritis', 'psoriatic', 'common_name', 'manual', 0.8),
('Psoriatic Arthritis', 'arthritis psoriatic', 'alternate_spelling', 'manual', 0.9),
-- Axial Spondyloarthritis
('Axial Spondyloarthritis', 'axSpA', 'abbreviation', 'manual', 1.0),
('Axial Spondyloarthritis', 'ankylosing spondylitis', 'synonym', 'manual', 1.0),
('Axial Spondyloarthritis', 'AS', 'abbreviation', 'manual', 1.0),
('Axial Spondyloarthritis', 'nr-axSpA', 'abbreviation', 'manual', 1.0),
('Axial Spondyloarthritis', 'non-radiographic axial spondyloarthritis', 'subtype', 'manual', 1.0),
-- Juvenile Idiopathic Arthritis
('Juvenile Idiopathic Arthritis', 'JIA', 'abbreviation', 'manual', 1.0),
('Juvenile Idiopathic Arthritis', 'juvenile arthritis', 'common_name', 'manual', 0.9),
('Juvenile Idiopathic Arthritis', 'juvenile rheumatoid arthritis', 'synonym', 'manual', 1.0),
('Juvenile Idiopathic Arthritis', 'JRA', 'abbreviation', 'manual', 1.0),
-- Systemic JIA
('Systemic Juvenile Idiopathic Arthritis', 'sJIA', 'abbreviation', 'manual', 1.0),
('Systemic Juvenile Idiopathic Arthritis', 'systemic JIA', 'abbreviation', 'manual', 1.0),
('Systemic Juvenile Idiopathic Arthritis', 'Still disease juvenile', 'synonym', 'manual', 0.9),
-- Giant Cell Arteritis
('Giant Cell Arteritis', 'GCA', 'abbreviation', 'manual', 1.0),
('Giant Cell Arteritis', 'temporal arteritis', 'synonym', 'manual', 1.0),
('Giant Cell Arteritis', 'Horton disease', 'synonym', 'manual', 0.9),
('Giant Cell Arteritis', 'cranial arteritis', 'synonym', 'manual', 0.9),
-- Polymyalgia Rheumatica
('Polymyalgia Rheumatica', 'PMR', 'abbreviation', 'manual', 1.0),
('Polymyalgia Rheumatica', 'polymyalgia', 'common_name', 'manual', 0.9),
-- Takayasu Arteritis
('Takayasu Arteritis', 'TAK', 'abbreviation', 'manual', 1.0),
('Takayasu Arteritis', 'Takayasu''s arteritis', 'alternate_spelling', 'manual', 1.0),
('Takayasu Arteritis', 'large vessel vasculitis', 'synonym', 'manual', 0.9),
('Takayasu Arteritis', 'pulseless disease', 'synonym', 'manual', 0.8)
ON CONFLICT (canonical_name, variant_name) DO NOTHING;

-- Continue with more diseases...
INSERT INTO cs_disease_name_variants (canonical_name, variant_name, variant_type, source, confidence) VALUES
-- LUPUS & RELATED
-- Systemic Lupus Erythematosus
('Systemic Lupus Erythematosus', 'SLE', 'abbreviation', 'manual', 1.0),
('Systemic Lupus Erythematosus', 'lupus', 'common_name', 'manual', 0.9),
('Systemic Lupus Erythematosus', 'systemic lupus', 'common_name', 'manual', 1.0),
('Systemic Lupus Erythematosus', 'lupus erythematosus', 'synonym', 'manual', 1.0),
-- Lupus Nephritis
('Lupus Nephritis', 'LN', 'abbreviation', 'manual', 1.0),
('Lupus Nephritis', 'lupus kidney disease', 'common_name', 'manual', 0.9),
('Lupus Nephritis', 'lupus glomerulonephritis', 'synonym', 'manual', 1.0),
-- Cutaneous Lupus
('Cutaneous Lupus Erythematosus', 'CLE', 'abbreviation', 'manual', 1.0),
('Cutaneous Lupus Erythematosus', 'discoid lupus', 'subtype', 'manual', 1.0),
('Cutaneous Lupus Erythematosus', 'DLE', 'abbreviation', 'manual', 1.0),
('Cutaneous Lupus Erythematosus', 'SCLE', 'abbreviation', 'manual', 1.0),
('Cutaneous Lupus Erythematosus', 'subacute cutaneous lupus', 'subtype', 'manual', 1.0),

-- INFLAMMATORY MYOPATHIES
-- Dermatomyositis
('Dermatomyositis', 'DM', 'abbreviation', 'manual', 1.0),
('Dermatomyositis', 'inflammatory myopathy', 'synonym', 'manual', 0.9),
('Dermatomyositis', 'adult dermatomyositis', 'subtype', 'manual', 1.0),
-- Juvenile Dermatomyositis
('Juvenile Dermatomyositis', 'JDM', 'abbreviation', 'manual', 1.0),
('Juvenile Dermatomyositis', 'pediatric dermatomyositis', 'synonym', 'manual', 1.0),
-- Polymyositis
('Polymyositis', 'PM', 'abbreviation', 'manual', 1.0),
('Polymyositis', 'idiopathic inflammatory myopathy', 'synonym', 'manual', 0.9),
-- Antisynthetase Syndrome
('Antisynthetase Syndrome', 'ASS', 'abbreviation', 'manual', 1.0),
('Antisynthetase Syndrome', 'ASM', 'abbreviation', 'manual', 1.0),
('Antisynthetase Syndrome', 'anti-synthetase syndrome', 'alternate_spelling', 'manual', 1.0),
-- Inclusion Body Myositis
('Inclusion Body Myositis', 'IBM', 'abbreviation', 'manual', 1.0),
('Inclusion Body Myositis', 'sporadic inclusion body myositis', 'subtype', 'manual', 1.0),
('Inclusion Body Myositis', 'sIBM', 'abbreviation', 'manual', 1.0)
ON CONFLICT (canonical_name, variant_name) DO NOTHING;

-- SYSTEMIC SCLEROSIS & SCLERODERMA
INSERT INTO cs_disease_name_variants (canonical_name, variant_name, variant_type, source, confidence) VALUES
('Systemic Sclerosis', 'SSc', 'abbreviation', 'manual', 1.0),
('Systemic Sclerosis', 'scleroderma', 'common_name', 'manual', 1.0),
('Systemic Sclerosis', 'systemic scleroderma', 'synonym', 'manual', 1.0),
('Systemic Sclerosis', 'progressive systemic sclerosis', 'synonym', 'manual', 1.0),
('Systemic Sclerosis', 'PSS', 'abbreviation', 'manual', 0.9),
('Systemic Sclerosis', 'diffuse cutaneous systemic sclerosis', 'subtype', 'manual', 1.0),
('Systemic Sclerosis', 'dcSSc', 'abbreviation', 'manual', 1.0),
('Systemic Sclerosis', 'limited cutaneous systemic sclerosis', 'subtype', 'manual', 1.0),
('Systemic Sclerosis', 'lcSSc', 'abbreviation', 'manual', 1.0),
('Systemic Sclerosis', 'CREST syndrome', 'synonym', 'manual', 1.0),
('Morphea', 'localized scleroderma', 'synonym', 'manual', 1.0),
('Morphea', 'circumscribed scleroderma', 'synonym', 'manual', 1.0),

-- SJOGREN'S SYNDROME
('Primary Sjogren Syndrome', 'Sjogren syndrome', 'synonym', 'manual', 1.0),
('Primary Sjogren Syndrome', 'Sjögren syndrome', 'alternate_spelling', 'manual', 1.0),
('Primary Sjogren Syndrome', 'Sjögren''s disease', 'alternate_spelling', 'manual', 1.0),
('Primary Sjogren Syndrome', 'pSS', 'abbreviation', 'manual', 1.0),
('Primary Sjogren Syndrome', 'sicca syndrome', 'synonym', 'manual', 0.9),
('Primary Sjogren Syndrome', 'primary Sjögren''s', 'alternate_spelling', 'manual', 1.0),

-- INFLAMMATORY BOWEL DISEASE
('Ulcerative Colitis', 'UC', 'abbreviation', 'manual', 1.0),
('Ulcerative Colitis', 'ulcerative proctitis', 'subtype', 'manual', 1.0),
('Crohn Disease', 'Crohn''s disease', 'alternate_spelling', 'manual', 1.0),
('Crohn Disease', 'CD', 'abbreviation', 'manual', 1.0),
('Crohn Disease', 'regional enteritis', 'synonym', 'manual', 0.9),
('Crohn Disease', 'ileitis', 'subtype', 'manual', 0.9),
('Inflammatory Bowel Disease', 'IBD', 'abbreviation', 'manual', 1.0),

-- GVHD
('Graft-versus-Host Disease', 'GVHD', 'abbreviation', 'manual', 1.0),
('Graft-versus-Host Disease', 'GvHD', 'abbreviation', 'manual', 1.0),
('Graft-versus-Host Disease', 'graft versus host', 'common_name', 'manual', 0.9),
('Chronic Graft-versus-Host Disease', 'cGVHD', 'abbreviation', 'manual', 1.0),
('Chronic Graft-versus-Host Disease', 'chronic GVHD', 'synonym', 'manual', 1.0),
('Acute Graft-versus-Host Disease', 'aGVHD', 'abbreviation', 'manual', 1.0),
('Acute Graft-versus-Host Disease', 'acute GVHD', 'synonym', 'manual', 1.0),

-- STILL'S DISEASE
('Adult-onset Still Disease', 'AOSD', 'abbreviation', 'manual', 1.0),
('Adult-onset Still Disease', 'adult Still''s disease', 'alternate_spelling', 'manual', 1.0),
('Adult-onset Still Disease', 'adult-onset Still''s disease', 'alternate_spelling', 'manual', 1.0),
('Adult-onset Still Disease', 'Still disease', 'common_name', 'manual', 0.9),

-- UVEITIS
('Uveitis', 'non-infectious uveitis', 'subtype', 'manual', 1.0),
('Uveitis', 'anterior uveitis', 'subtype', 'manual', 1.0),
('Uveitis', 'posterior uveitis', 'subtype', 'manual', 1.0),
('Uveitis', 'panuveitis', 'subtype', 'manual', 1.0),
('Uveitis', 'intermediate uveitis', 'subtype', 'manual', 1.0),

-- VASCULITIS
('ANCA-Associated Vasculitis', 'AAV', 'abbreviation', 'manual', 1.0),
('ANCA-Associated Vasculitis', 'ANCA vasculitis', 'common_name', 'manual', 1.0),
('Granulomatosis with Polyangiitis', 'GPA', 'abbreviation', 'manual', 1.0),
('Granulomatosis with Polyangiitis', 'Wegener granulomatosis', 'synonym', 'manual', 1.0),
('Granulomatosis with Polyangiitis', 'Wegener''s disease', 'synonym', 'manual', 1.0),
('Microscopic Polyangiitis', 'MPA', 'abbreviation', 'manual', 1.0),
('Eosinophilic Granulomatosis with Polyangiitis', 'EGPA', 'abbreviation', 'manual', 1.0),
('Eosinophilic Granulomatosis with Polyangiitis', 'Churg-Strauss syndrome', 'synonym', 'manual', 1.0),
('Polyarteritis Nodosa', 'PAN', 'abbreviation', 'manual', 1.0),
('Behcet Disease', 'Behçet disease', 'alternate_spelling', 'manual', 1.0),
('Behcet Disease', 'Behcet syndrome', 'synonym', 'manual', 1.0),
('Behcet Disease', 'BD', 'abbreviation', 'manual', 1.0),

-- CYTOPENIAS
('Immune Thrombocytopenia', 'ITP', 'abbreviation', 'manual', 1.0),
('Immune Thrombocytopenia', 'immune thrombocytopenic purpura', 'synonym', 'manual', 1.0),
('Immune Thrombocytopenia', 'idiopathic thrombocytopenic purpura', 'synonym', 'manual', 1.0),
('Autoimmune Hemolytic Anemia', 'AIHA', 'abbreviation', 'manual', 1.0),
('Autoimmune Hemolytic Anemia', 'warm autoimmune hemolytic anemia', 'subtype', 'manual', 1.0),
('Autoimmune Hemolytic Anemia', 'cold agglutinin disease', 'subtype', 'manual', 1.0),
('Autoimmune Hemolytic Anemia', 'CAD', 'abbreviation', 'manual', 0.9),
('Evans Syndrome', 'Evans syndrome', 'synonym', 'manual', 1.0),

-- NEUROLOGY
('Myasthenia Gravis', 'MG', 'abbreviation', 'manual', 1.0),
('Myasthenia Gravis', 'myasthenia', 'common_name', 'manual', 0.9),
('Myasthenia Gravis', 'generalized myasthenia gravis', 'subtype', 'manual', 1.0),
('Myasthenia Gravis', 'gMG', 'abbreviation', 'manual', 1.0),
('Multiple Sclerosis', 'MS', 'abbreviation', 'manual', 1.0),
('Multiple Sclerosis', 'relapsing-remitting MS', 'subtype', 'manual', 1.0),
('Multiple Sclerosis', 'RRMS', 'abbreviation', 'manual', 1.0),
('Multiple Sclerosis', 'progressive MS', 'subtype', 'manual', 1.0),
('Neuromyelitis Optica Spectrum Disorder', 'NMOSD', 'abbreviation', 'manual', 1.0),
('Neuromyelitis Optica Spectrum Disorder', 'NMO', 'abbreviation', 'manual', 1.0),
('Neuromyelitis Optica Spectrum Disorder', 'Devic disease', 'synonym', 'manual', 0.9),
('Chronic Inflammatory Demyelinating Polyneuropathy', 'CIDP', 'abbreviation', 'manual', 1.0),

-- AUTOINFLAMMATORY
('Familial Mediterranean Fever', 'FMF', 'abbreviation', 'manual', 1.0),
('Cryopyrin-Associated Periodic Syndrome', 'CAPS', 'abbreviation', 'manual', 1.0),
('Cryopyrin-Associated Periodic Syndrome', 'NOMID', 'subtype', 'manual', 1.0),
('Cryopyrin-Associated Periodic Syndrome', 'Muckle-Wells syndrome', 'subtype', 'manual', 1.0),
('Cryopyrin-Associated Periodic Syndrome', 'MWS', 'abbreviation', 'manual', 1.0),
('Cryopyrin-Associated Periodic Syndrome', 'FCAS', 'subtype', 'manual', 1.0),
('Hemophagocytic Lymphohistiocytosis', 'HLH', 'abbreviation', 'manual', 1.0),
('Hemophagocytic Lymphohistiocytosis', 'hemophagocytic syndrome', 'synonym', 'manual', 1.0),
('Macrophage Activation Syndrome', 'MAS', 'abbreviation', 'manual', 1.0),

-- TYPE I INTERFERONOPATHIES
('Type I Interferonopathies', 'CANDLE syndrome', 'subtype', 'manual', 1.0),
('Type I Interferonopathies', 'PRAAS', 'subtype', 'manual', 1.0),
('Type I Interferonopathies', 'SAVI', 'subtype', 'manual', 1.0),
('Type I Interferonopathies', 'Aicardi-Goutières syndrome', 'subtype', 'manual', 1.0),
('Type I Interferonopathies', 'AGS', 'abbreviation', 'manual', 1.0),
('Type I Interferonopathies', 'STING-associated vasculopathy', 'subtype', 'manual', 1.0),

-- PULMONARY
('Interstitial Lung Disease', 'ILD', 'abbreviation', 'manual', 1.0),
('Interstitial Lung Disease', 'interstitial pneumonia', 'synonym', 'manual', 0.9),
('Idiopathic Pulmonary Fibrosis', 'IPF', 'abbreviation', 'manual', 1.0),
('Pulmonary Arterial Hypertension', 'PAH', 'abbreviation', 'manual', 1.0),
('Pulmonary Arterial Hypertension', 'pulmonary hypertension', 'common_name', 'manual', 0.9),

-- RARE SKIN
('Pemphigus Vulgaris', 'PV', 'abbreviation', 'manual', 1.0),
('Pemphigus Vulgaris', 'pemphigus', 'common_name', 'manual', 0.9),
('Bullous Pemphigoid', 'BP', 'abbreviation', 'manual', 1.0),
('Epidermolysis Bullosa Acquisita', 'EBA', 'abbreviation', 'manual', 1.0),
('Pyoderma Gangrenosum', 'PG', 'abbreviation', 'manual', 1.0),
('Lichen Planus', 'LP', 'abbreviation', 'manual', 1.0),
('Lichen Planus', 'oral lichen planus', 'subtype', 'manual', 1.0),
('Lichen Planus', 'cutaneous lichen planus', 'subtype', 'manual', 1.0),
('Mucous Membrane Pemphigoid', 'MMP', 'abbreviation', 'manual', 1.0),
('Mucous Membrane Pemphigoid', 'cicatricial pemphigoid', 'synonym', 'manual', 1.0),
('Dermatitis Herpetiformis', 'DH', 'abbreviation', 'manual', 1.0),
('Dermatitis Herpetiformis', 'Duhring disease', 'synonym', 'manual', 0.9),
('Linear IgA Disease', 'LAD', 'abbreviation', 'manual', 1.0),
('Acne Vulgaris', 'acne', 'common_name', 'manual', 1.0),
('Rosacea', 'acne rosacea', 'synonym', 'manual', 0.9),

-- NEPHROLOGY / KIDNEY
('IgA Nephropathy', 'IgAN', 'abbreviation', 'manual', 1.0),
('IgA Nephropathy', 'Berger disease', 'synonym', 'manual', 1.0),
('Membranous Nephropathy', 'MN', 'abbreviation', 'manual', 1.0),
('Membranous Nephropathy', 'membranous glomerulonephritis', 'synonym', 'manual', 1.0),
('Focal Segmental Glomerulosclerosis', 'FSGS', 'abbreviation', 'manual', 1.0),
('Minimal Change Disease', 'MCD', 'abbreviation', 'manual', 1.0),
('Minimal Change Disease', 'lipoid nephrosis', 'synonym', 'manual', 0.9),
('Anti-GBM Disease', 'Goodpasture syndrome', 'synonym', 'manual', 1.0),
('Anti-GBM Disease', 'anti-glomerular basement membrane disease', 'synonym', 'manual', 1.0),
('C3 Glomerulopathy', 'C3G', 'abbreviation', 'manual', 1.0),
('C3 Glomerulopathy', 'dense deposit disease', 'subtype', 'manual', 1.0),
('C3 Glomerulopathy', 'DDD', 'abbreviation', 'manual', 1.0),
('Atypical Hemolytic Uremic Syndrome', 'aHUS', 'abbreviation', 'manual', 1.0),
('Primary Hyperoxaluria', 'PH1', 'abbreviation', 'manual', 1.0),
('Primary Hyperoxaluria', 'oxalosis', 'synonym', 'manual', 0.9),

-- HEPATOLOGY / LIVER
('Primary Biliary Cholangitis', 'PBC', 'abbreviation', 'manual', 1.0),
('Primary Biliary Cholangitis', 'primary biliary cirrhosis', 'synonym', 'manual', 1.0),
('Primary Sclerosing Cholangitis', 'PSC', 'abbreviation', 'manual', 1.0),
('Autoimmune Hepatitis', 'AIH', 'abbreviation', 'manual', 1.0),
('Nonalcoholic Steatohepatitis', 'NASH', 'abbreviation', 'manual', 1.0),
('Nonalcoholic Steatohepatitis', 'fatty liver disease', 'common_name', 'manual', 0.9),
('Nonalcoholic Steatohepatitis', 'metabolic dysfunction-associated steatohepatitis', 'synonym', 'manual', 1.0),
('Nonalcoholic Steatohepatitis', 'MASH', 'abbreviation', 'manual', 1.0),

-- HEMATOLOGIC / BLOOD DISORDERS
('Paroxysmal Nocturnal Hemoglobinuria', 'PNH', 'abbreviation', 'manual', 1.0),
('Aplastic Anemia', 'AA', 'abbreviation', 'manual', 1.0),
('Aplastic Anemia', 'bone marrow failure', 'synonym', 'manual', 0.9),
('Thrombotic Thrombocytopenic Purpura', 'TTP', 'abbreviation', 'manual', 1.0),
('Acquired TTP', 'aTTP', 'abbreviation', 'manual', 1.0),
('Acquired TTP', 'immune TTP', 'synonym', 'manual', 1.0),
('Myelodysplastic Syndromes', 'MDS', 'abbreviation', 'manual', 1.0),
('Beta Thalassemia', 'thalassemia major', 'subtype', 'manual', 1.0),
('Beta Thalassemia', 'Cooley anemia', 'synonym', 'manual', 0.9),
('Sickle Cell Disease', 'SCD', 'abbreviation', 'manual', 1.0),
('Sickle Cell Disease', 'sickle cell anemia', 'synonym', 'manual', 1.0),
('Cold Agglutinin Disease', 'CAD', 'abbreviation', 'manual', 1.0),
('Cold Agglutinin Disease', 'cold AIHA', 'synonym', 'manual', 1.0),
('Warm Autoimmune Hemolytic Anemia', 'wAIHA', 'abbreviation', 'manual', 1.0),

-- OPHTHALMOLOGY / EYE
('Thyroid Eye Disease', 'TED', 'abbreviation', 'manual', 1.0),
('Thyroid Eye Disease', 'Graves ophthalmopathy', 'synonym', 'manual', 1.0),
('Thyroid Eye Disease', 'Graves orbitopathy', 'synonym', 'manual', 1.0),
('Thyroid Eye Disease', 'GO', 'abbreviation', 'manual', 0.9),
('Dry Eye Disease', 'DED', 'abbreviation', 'manual', 1.0),
('Dry Eye Disease', 'keratoconjunctivitis sicca', 'synonym', 'manual', 1.0),
('Geographic Atrophy', 'GA', 'abbreviation', 'manual', 1.0),
('Geographic Atrophy', 'dry AMD', 'synonym', 'manual', 1.0),
('Age-Related Macular Degeneration', 'AMD', 'abbreviation', 'manual', 1.0),
('Age-Related Macular Degeneration', 'ARMD', 'abbreviation', 'manual', 0.9),
('Diabetic Macular Edema', 'DME', 'abbreviation', 'manual', 1.0),
('Diabetic Retinopathy', 'DR', 'abbreviation', 'manual', 1.0),
('Optic Neuritis', 'ON', 'abbreviation', 'manual', 1.0),

-- ENDOCRINE
('Graves Disease', 'Graves'' disease', 'alternate_spelling', 'manual', 1.0),
('Graves Disease', 'hyperthyroidism autoimmune', 'synonym', 'manual', 0.9),
('Hashimoto Thyroiditis', 'Hashimoto''s thyroiditis', 'alternate_spelling', 'manual', 1.0),
('Hashimoto Thyroiditis', 'chronic lymphocytic thyroiditis', 'synonym', 'manual', 1.0),
('Type 1 Diabetes', 'T1D', 'abbreviation', 'manual', 1.0),
('Type 1 Diabetes', 'IDDM', 'abbreviation', 'manual', 0.9),
('Type 1 Diabetes', 'juvenile diabetes', 'common_name', 'manual', 0.8),
('Addison Disease', 'primary adrenal insufficiency', 'synonym', 'manual', 1.0),
('Addison Disease', 'adrenal insufficiency autoimmune', 'synonym', 'manual', 0.9),

-- CARDIOLOGY
('Myocarditis', 'viral myocarditis', 'subtype', 'manual', 1.0),
('Myocarditis', 'autoimmune myocarditis', 'subtype', 'manual', 1.0),
('Pericarditis', 'acute pericarditis', 'subtype', 'manual', 1.0),
('Pericarditis', 'recurrent pericarditis', 'subtype', 'manual', 1.0),
('Cardiac Sarcoidosis', 'heart sarcoidosis', 'synonym', 'manual', 1.0),
('Dilated Cardiomyopathy', 'DCM', 'abbreviation', 'manual', 1.0),

-- NEUROLOGY EXPANDED
('Guillain-Barre Syndrome', 'GBS', 'abbreviation', 'manual', 1.0),
('Guillain-Barre Syndrome', 'acute inflammatory demyelinating polyneuropathy', 'synonym', 'manual', 1.0),
('Guillain-Barre Syndrome', 'AIDP', 'abbreviation', 'manual', 1.0),
('Multifocal Motor Neuropathy', 'MMN', 'abbreviation', 'manual', 1.0),
('Stiff Person Syndrome', 'SPS', 'abbreviation', 'manual', 1.0),
('Stiff Person Syndrome', 'stiff-man syndrome', 'synonym', 'manual', 0.9),
('Autoimmune Encephalitis', 'AE', 'abbreviation', 'manual', 1.0),
('Autoimmune Encephalitis', 'anti-NMDA receptor encephalitis', 'subtype', 'manual', 1.0),
('Autoimmune Encephalitis', 'limbic encephalitis', 'subtype', 'manual', 1.0),
('Lambert-Eaton Myasthenic Syndrome', 'LEMS', 'abbreviation', 'manual', 1.0),
('Transverse Myelitis', 'TM', 'abbreviation', 'manual', 1.0),
('Transverse Myelitis', 'acute transverse myelitis', 'subtype', 'manual', 1.0),
('Amyotrophic Lateral Sclerosis', 'ALS', 'abbreviation', 'manual', 1.0),
('Amyotrophic Lateral Sclerosis', 'Lou Gehrig disease', 'synonym', 'manual', 0.9),
('Amyotrophic Lateral Sclerosis', 'motor neuron disease', 'synonym', 'manual', 0.9),
('Progressive Supranuclear Palsy', 'PSP', 'abbreviation', 'manual', 1.0),
('Chronic Fatigue Syndrome', 'CFS', 'abbreviation', 'manual', 1.0),
('Chronic Fatigue Syndrome', 'ME/CFS', 'abbreviation', 'manual', 1.0),
('Chronic Fatigue Syndrome', 'myalgic encephalomyelitis', 'synonym', 'manual', 1.0),
('Anti-MOG Associated Disease', 'MOGAD', 'abbreviation', 'manual', 1.0),
('Anti-MOG Associated Disease', 'MOG antibody disease', 'synonym', 'manual', 1.0),

-- RARE GENETIC/METABOLIC
('Fabry Disease', 'alpha-galactosidase A deficiency', 'synonym', 'manual', 1.0),
('Gaucher Disease', 'glucocerebrosidase deficiency', 'synonym', 'manual', 1.0),
('Gaucher Disease', 'GD', 'abbreviation', 'manual', 1.0),
('Pompe Disease', 'acid maltase deficiency', 'synonym', 'manual', 1.0),
('Pompe Disease', 'glycogen storage disease type II', 'synonym', 'manual', 1.0),
('Duchenne Muscular Dystrophy', 'DMD', 'abbreviation', 'manual', 1.0),
('Spinal Muscular Atrophy', 'SMA', 'abbreviation', 'manual', 1.0),
('Hereditary Angioedema', 'HAE', 'abbreviation', 'manual', 1.0),
('Hereditary Angioedema', 'C1-INH deficiency', 'synonym', 'manual', 1.0),
('Alpha-1 Antitrypsin Deficiency', 'AATD', 'abbreviation', 'manual', 1.0),
('Alpha-1 Antitrypsin Deficiency', 'A1AT deficiency', 'abbreviation', 'manual', 1.0),
('Complement-Mediated Diseases', 'complement disorders', 'synonym', 'manual', 0.9),

-- RARE AUTOINFLAMMATORY
('TRAPS', 'TNF receptor-associated periodic syndrome', 'synonym', 'manual', 1.0),
('Hyper-IgD Syndrome', 'HIDS', 'abbreviation', 'manual', 1.0),
('Hyper-IgD Syndrome', 'mevalonate kinase deficiency', 'synonym', 'manual', 1.0),
('Blau Syndrome', 'early-onset sarcoidosis', 'synonym', 'manual', 0.9),
('PAPA Syndrome', 'pyogenic arthritis pyoderma gangrenosum and acne', 'synonym', 'manual', 1.0),
('Schnitzler Syndrome', 'chronic urticaria with monoclonal gammopathy', 'synonym', 'manual', 1.0),
('Deficiency of IL-36 Receptor Antagonist', 'DITRA', 'abbreviation', 'manual', 1.0),

-- SARCOIDOSIS
('Sarcoidosis', 'pulmonary sarcoidosis', 'subtype', 'manual', 1.0),
('Sarcoidosis', 'extrapulmonary sarcoidosis', 'subtype', 'manual', 1.0),
('Sarcoidosis', 'Lofgren syndrome', 'subtype', 'manual', 1.0),
('Sarcoidosis', 'neurosarcoidosis', 'subtype', 'manual', 1.0),

-- GI/GASTROENTEROLOGY
('Celiac Disease', 'celiac sprue', 'synonym', 'manual', 1.0),
('Celiac Disease', 'gluten-sensitive enteropathy', 'synonym', 'manual', 1.0),
('Eosinophilic Esophagitis', 'EoE', 'abbreviation', 'manual', 1.0),
('Autoimmune Gastritis', 'pernicious anemia', 'synonym', 'manual', 0.9),
('Autoimmune Pancreatitis', 'AIP', 'abbreviation', 'manual', 1.0),
('Autoimmune Pancreatitis', 'IgG4-related pancreatitis', 'subtype', 'manual', 1.0),

-- IgG4-RELATED DISEASE
('IgG4-Related Disease', 'IgG4-RD', 'abbreviation', 'manual', 1.0),
('IgG4-Related Disease', 'IgG4 related disease', 'alternate_spelling', 'manual', 1.0),
('IgG4-Related Disease', 'hyper-IgG4 disease', 'synonym', 'manual', 0.9),

-- MIXED CONNECTIVE TISSUE DISEASE
('Mixed Connective Tissue Disease', 'MCTD', 'abbreviation', 'manual', 1.0),
('Mixed Connective Tissue Disease', 'Sharp syndrome', 'synonym', 'manual', 0.9),
('Mixed Connective Tissue Disease', 'overlap syndrome', 'synonym', 'manual', 0.8),
('Mixed Connective Tissue Disease', 'undifferentiated connective tissue disease', 'synonym', 'manual', 0.8),
('Mixed Connective Tissue Disease', 'UCTD', 'abbreviation', 'manual', 0.8),

-- ANTIPHOSPHOLIPID SYNDROME
('Antiphospholipid Syndrome', 'APS', 'abbreviation', 'manual', 1.0),
('Antiphospholipid Syndrome', 'APLA syndrome', 'synonym', 'manual', 1.0),
('Antiphospholipid Syndrome', 'Hughes syndrome', 'synonym', 'manual', 0.9),
('Antiphospholipid Syndrome', 'anticardiolipin antibody syndrome', 'synonym', 'manual', 0.9),
('Catastrophic Antiphospholipid Syndrome', 'CAPS', 'abbreviation', 'manual', 1.0),
('Catastrophic Antiphospholipid Syndrome', 'Asherson syndrome', 'synonym', 'manual', 0.9),

-- RELAPSING POLYCHONDRITIS
('Relapsing Polychondritis', 'RP', 'abbreviation', 'manual', 1.0),
('Relapsing Polychondritis', 'relapsing perichondritis', 'synonym', 'manual', 0.9),

-- SPONDYLOARTHRITIS EXPANDED
('Peripheral Spondyloarthritis', 'pSpA', 'abbreviation', 'manual', 1.0),
('Reactive Arthritis', 'ReA', 'abbreviation', 'manual', 1.0),
('Reactive Arthritis', 'Reiter syndrome', 'synonym', 'manual', 0.8),
('Enteropathic Arthritis', 'IBD-associated arthritis', 'synonym', 'manual', 1.0),

-- FIBROMYALGIA
('Fibromyalgia', 'FM', 'abbreviation', 'manual', 1.0),
('Fibromyalgia', 'fibromyalgia syndrome', 'synonym', 'manual', 1.0),
('Fibromyalgia', 'FMS', 'abbreviation', 'manual', 1.0),

-- OSTEOARTHRITIS
('Osteoarthritis', 'OA', 'abbreviation', 'manual', 1.0),
('Osteoarthritis', 'degenerative joint disease', 'synonym', 'manual', 1.0),
('Osteoarthritis', 'DJD', 'abbreviation', 'manual', 0.9),

-- GOUT
('Gout', 'gouty arthritis', 'synonym', 'manual', 1.0),
('Gout', 'crystal arthropathy', 'synonym', 'manual', 0.9),
('Gout', 'chronic gout', 'subtype', 'manual', 1.0),
('Gout', 'tophaceous gout', 'subtype', 'manual', 1.0),

-- SYSTEMIC MASTOCYTOSIS
('Systemic Mastocytosis', 'SM', 'abbreviation', 'manual', 1.0),
('Systemic Mastocytosis', 'mast cell disease', 'synonym', 'manual', 0.9),
('Advanced Systemic Mastocytosis', 'AdvSM', 'abbreviation', 'manual', 1.0),

-- EOSINOPHILIC DISORDERS
('Hypereosinophilic Syndrome', 'HES', 'abbreviation', 'manual', 1.0),
('Eosinophilic Granulomatosis', 'EG', 'abbreviation', 'manual', 1.0),
('Chronic Eosinophilic Pneumonia', 'CEP', 'abbreviation', 'manual', 1.0)
ON CONFLICT (canonical_name, variant_name) DO NOTHING;

-- =====================================================
-- DISEASE PARENT MAPPINGS
-- Maps specific disease subtypes to their parent/canonical disease
-- Used to aggregate market intelligence at the parent level
-- =====================================================

INSERT INTO cs_disease_parent_mappings (specific_name, parent_name, relationship_type, source, confidence, notes) VALUES
-- SLE variants
('Systemic Lupus Erythematosus with alopecia universalis and arthritis', 'Systemic Lupus Erythematosus', 'variant', 'manual', 1.0, NULL),
('SLE with cutaneous manifestations', 'Systemic Lupus Erythematosus', 'variant', 'manual', 1.0, NULL),
('refractory systemic lupus erythematosus', 'Systemic Lupus Erythematosus', 'refractory', 'manual', 1.0, NULL),
('refractory SLE', 'Systemic Lupus Erythematosus', 'refractory', 'manual', 1.0, NULL),
('active SLE', 'Systemic Lupus Erythematosus', 'variant', 'manual', 1.0, NULL),
('moderate-to-severe SLE', 'Systemic Lupus Erythematosus', 'variant', 'manual', 1.0, NULL),
('SLE with nephritis', 'Systemic Lupus Erythematosus', 'variant', 'manual', 0.9, 'May also map to Lupus Nephritis'),

-- Lupus Nephritis variants
('proliferative lupus nephritis', 'Lupus Nephritis', 'subtype', 'manual', 1.0, NULL),
('class III lupus nephritis', 'Lupus Nephritis', 'subtype', 'manual', 1.0, NULL),
('class IV lupus nephritis', 'Lupus Nephritis', 'subtype', 'manual', 1.0, NULL),
('class V lupus nephritis', 'Lupus Nephritis', 'subtype', 'manual', 1.0, NULL),
('refractory lupus nephritis', 'Lupus Nephritis', 'refractory', 'manual', 1.0, NULL),

-- Cutaneous Lupus variants
('refractory subacute cutaneous lupus erythematosus', 'Cutaneous Lupus Erythematosus', 'refractory', 'manual', 1.0, NULL),
('Familial chilblain lupus with TREX1 mutation', 'Cutaneous Lupus Erythematosus', 'subtype', 'manual', 1.0, NULL),
('Lupus erythematosus panniculitis', 'Cutaneous Lupus Erythematosus', 'subtype', 'manual', 1.0, NULL),
('discoid lupus erythematosus', 'Cutaneous Lupus Erythematosus', 'subtype', 'manual', 1.0, NULL),

-- Alopecia variants
('severe alopecia areata with atopic dermatitis in children', 'Alopecia Areata', 'pediatric', 'manual', 1.0, NULL),
('pediatric alopecia universalis', 'Alopecia Areata', 'pediatric', 'manual', 1.0, NULL),
('alopecia totalis', 'Alopecia Areata', 'subtype', 'manual', 1.0, NULL),
('alopecia universalis', 'Alopecia Areata', 'subtype', 'manual', 1.0, NULL),
('refractory alopecia areata', 'Alopecia Areata', 'refractory', 'manual', 1.0, NULL),
('severe alopecia areata', 'Alopecia Areata', 'variant', 'manual', 1.0, NULL),

-- Atopic Dermatitis variants
('atopic dermatitis', 'Atopic Dermatitis', 'variant', 'manual', 1.0, 'Case normalization'),
('moderate-to-severe atopic dermatitis', 'Atopic Dermatitis', 'variant', 'manual', 1.0, NULL),
('moderate and severe atopic dermatitis', 'Atopic Dermatitis', 'variant', 'manual', 1.0, NULL),
('severe atopic dermatitis', 'Atopic Dermatitis', 'variant', 'manual', 1.0, NULL),
('refractory atopic dermatitis', 'Atopic Dermatitis', 'refractory', 'manual', 1.0, NULL),
('pediatric atopic dermatitis', 'Atopic Dermatitis', 'pediatric', 'manual', 1.0, NULL),

-- Dermatomyositis variants
('refractory dermatomyositis', 'Dermatomyositis', 'refractory', 'manual', 1.0, NULL),
('anti-MDA5 antibody-positive dermatomyositis', 'Dermatomyositis', 'subtype', 'manual', 1.0, NULL),
('anti-MDA5 dermatomyositis', 'Dermatomyositis', 'subtype', 'manual', 1.0, NULL),
('amyopathic dermatomyositis', 'Dermatomyositis', 'subtype', 'manual', 1.0, NULL),
('clinically amyopathic dermatomyositis', 'Dermatomyositis', 'subtype', 'manual', 1.0, NULL),
('CADM', 'Dermatomyositis', 'subtype', 'manual', 1.0, 'Clinically amyopathic DM'),
('dermatomyositis with ILD', 'Dermatomyositis', 'variant', 'manual', 1.0, NULL),
('adult dermatomyositis', 'Dermatomyositis', 'variant', 'manual', 1.0, NULL),

-- Juvenile Dermatomyositis variants
('Juvenile dermatomyositis-associated calcinosis', 'Juvenile Dermatomyositis', 'variant', 'manual', 1.0, NULL),
('refractory or severe juvenile dermatomyositis', 'Juvenile Dermatomyositis', 'refractory', 'manual', 1.0, NULL),
('refractory juvenile dermatomyositis', 'Juvenile Dermatomyositis', 'refractory', 'manual', 1.0, NULL),

-- JIA variants
('juvenile idiopathic arthritis associated uveitis', 'Juvenile Idiopathic Arthritis', 'variant', 'manual', 1.0, NULL),
('JIA-associated uveitis', 'Juvenile Idiopathic Arthritis', 'variant', 'manual', 1.0, NULL),
('polyarticular juvenile idiopathic arthritis', 'Juvenile Idiopathic Arthritis', 'subtype', 'manual', 1.0, NULL),
('pJIA', 'Juvenile Idiopathic Arthritis', 'subtype', 'manual', 1.0, NULL),
('oligoarticular JIA', 'Juvenile Idiopathic Arthritis', 'subtype', 'manual', 1.0, NULL),
('enthesitis-related JIA', 'Juvenile Idiopathic Arthritis', 'subtype', 'manual', 1.0, NULL),

-- Systemic JIA variants
('Systemic juvenile idiopathic arthritis with lung disease', 'Systemic Juvenile Idiopathic Arthritis', 'variant', 'manual', 1.0, NULL),
('sJIA with MAS', 'Systemic Juvenile Idiopathic Arthritis', 'variant', 'manual', 1.0, NULL),
('refractory systemic JIA', 'Systemic Juvenile Idiopathic Arthritis', 'refractory', 'manual', 1.0, NULL),

-- Vasculitis variants
('Takayasu arteritis refractory to TNF-α inhibitors', 'Takayasu Arteritis', 'refractory', 'manual', 1.0, NULL),
('refractory Takayasu arteritis', 'Takayasu Arteritis', 'refractory', 'manual', 1.0, NULL),
('refractory giant cell arteritis', 'Giant Cell Arteritis', 'refractory', 'manual', 1.0, NULL),
('GCA with PMR', 'Giant Cell Arteritis', 'variant', 'manual', 1.0, NULL),

-- Uveitis variants
('Uveitis associated with rheumatoid arthritis', 'Uveitis', 'variant', 'manual', 1.0, NULL),
('isolated noninfectious uveitis', 'Uveitis', 'subtype', 'manual', 1.0, NULL),
('non-infectious inflammatory ocular diseases', 'Uveitis', 'subtype', 'manual', 1.0, NULL),
('refractory uveitis', 'Uveitis', 'refractory', 'manual', 1.0, NULL),
('JIA-associated uveitis', 'Uveitis', 'variant', 'manual', 0.9, 'Could also map to JIA'),

-- AOSD variants
('Adult-onset Still''s disease (AOSD) and undifferentiated systemic autoinflammatory disease', 'Adult-onset Still Disease', 'variant', 'manual', 1.0, NULL),
('refractory AOSD', 'Adult-onset Still Disease', 'refractory', 'manual', 1.0, NULL),
('refractory adult-onset Still''s disease', 'Adult-onset Still Disease', 'refractory', 'manual', 1.0, NULL),

-- ITP variants
('immune thrombocytopenia (ITP)', 'Immune Thrombocytopenia', 'variant', 'manual', 1.0, NULL),
('chronic ITP', 'Immune Thrombocytopenia', 'subtype', 'manual', 1.0, NULL),
('refractory ITP', 'Immune Thrombocytopenia', 'refractory', 'manual', 1.0, NULL),
('pediatric ITP', 'Immune Thrombocytopenia', 'pediatric', 'manual', 1.0, NULL),

-- RA variants
('refractory rheumatoid arthritis', 'Rheumatoid Arthritis', 'refractory', 'manual', 1.0, NULL),
('early rheumatoid arthritis', 'Rheumatoid Arthritis', 'subtype', 'manual', 1.0, NULL),
('established rheumatoid arthritis', 'Rheumatoid Arthritis', 'variant', 'manual', 1.0, NULL),
('methotrexate-inadequate responder RA', 'Rheumatoid Arthritis', 'refractory', 'manual', 1.0, NULL),
('MTX-IR RA', 'Rheumatoid Arthritis', 'refractory', 'manual', 1.0, NULL),
('biologic-inadequate responder RA', 'Rheumatoid Arthritis', 'refractory', 'manual', 1.0, NULL),
('bDMARD-IR RA', 'Rheumatoid Arthritis', 'refractory', 'manual', 1.0, NULL),

-- Psoriasis variants
('moderate-to-severe psoriasis', 'Psoriasis', 'variant', 'manual', 1.0, NULL),
('severe plaque psoriasis', 'Psoriasis', 'variant', 'manual', 1.0, NULL),
('refractory psoriasis', 'Psoriasis', 'refractory', 'manual', 1.0, NULL),
('nail psoriasis', 'Psoriasis', 'subtype', 'manual', 1.0, NULL),
('scalp psoriasis', 'Psoriasis', 'subtype', 'manual', 1.0, NULL),
('palmoplantar psoriasis', 'Psoriasis', 'subtype', 'manual', 1.0, NULL),
('pustular psoriasis', 'Psoriasis', 'subtype', 'manual', 1.0, NULL),
('generalized pustular psoriasis', 'Psoriasis', 'subtype', 'manual', 1.0, NULL),
('GPP', 'Psoriasis', 'subtype', 'manual', 1.0, 'Generalized pustular psoriasis'),

-- Systemic Sclerosis variants
('diffuse systemic sclerosis', 'Systemic Sclerosis', 'subtype', 'manual', 1.0, NULL),
('limited systemic sclerosis', 'Systemic Sclerosis', 'subtype', 'manual', 1.0, NULL),
('early diffuse cutaneous systemic sclerosis', 'Systemic Sclerosis', 'subtype', 'manual', 1.0, NULL),
('SSc-ILD', 'Systemic Sclerosis', 'variant', 'manual', 1.0, 'Systemic sclerosis with ILD'),
('systemic sclerosis with interstitial lung disease', 'Systemic Sclerosis', 'variant', 'manual', 1.0, NULL),

-- GVHD variants
('steroid-refractory chronic GVHD', 'Chronic Graft-versus-Host Disease', 'refractory', 'manual', 1.0, NULL),
('steroid-refractory cGVHD', 'Chronic Graft-versus-Host Disease', 'refractory', 'manual', 1.0, NULL),
('moderate-to-severe chronic GVHD', 'Chronic Graft-versus-Host Disease', 'variant', 'manual', 1.0, NULL),
('steroid-refractory acute GVHD', 'Acute Graft-versus-Host Disease', 'refractory', 'manual', 1.0, NULL),

-- Sjogren's variants
('primary Sjögren''s syndrome', 'Primary Sjogren Syndrome', 'variant', 'manual', 1.0, NULL),
('refractory Sjogren syndrome', 'Primary Sjogren Syndrome', 'refractory', 'manual', 1.0, NULL),

-- IBD variants
('moderate-to-severe ulcerative colitis', 'Ulcerative Colitis', 'variant', 'manual', 1.0, NULL),
('refractory ulcerative colitis', 'Ulcerative Colitis', 'refractory', 'manual', 1.0, NULL),
('moderate-to-severe Crohn''s disease', 'Crohn Disease', 'variant', 'manual', 1.0, NULL),
('refractory Crohn''s disease', 'Crohn Disease', 'refractory', 'manual', 1.0, NULL),
('fistulizing Crohn''s disease', 'Crohn Disease', 'subtype', 'manual', 1.0, NULL),
('perianal Crohn''s disease', 'Crohn Disease', 'subtype', 'manual', 1.0, NULL),

-- Myasthenia Gravis variants
('refractory myasthenia gravis', 'Myasthenia Gravis', 'refractory', 'manual', 1.0, NULL),
('AChR-positive myasthenia gravis', 'Myasthenia Gravis', 'subtype', 'manual', 1.0, NULL),
('MuSK-positive myasthenia gravis', 'Myasthenia Gravis', 'subtype', 'manual', 1.0, NULL),
('generalized MG', 'Myasthenia Gravis', 'variant', 'manual', 1.0, NULL),

-- Multiple Sclerosis variants
('relapsing multiple sclerosis', 'Multiple Sclerosis', 'subtype', 'manual', 1.0, NULL),
('relapsing-remitting multiple sclerosis', 'Multiple Sclerosis', 'subtype', 'manual', 1.0, NULL),
('secondary progressive MS', 'Multiple Sclerosis', 'subtype', 'manual', 1.0, NULL),
('SPMS', 'Multiple Sclerosis', 'subtype', 'manual', 1.0, NULL),
('primary progressive MS', 'Multiple Sclerosis', 'subtype', 'manual', 1.0, NULL),
('PPMS', 'Multiple Sclerosis', 'subtype', 'manual', 1.0, NULL),

-- ANCA vasculitis variants
('refractory GPA', 'Granulomatosis with Polyangiitis', 'refractory', 'manual', 1.0, NULL),
('relapsing GPA', 'Granulomatosis with Polyangiitis', 'variant', 'manual', 1.0, NULL),
('refractory MPA', 'Microscopic Polyangiitis', 'refractory', 'manual', 1.0, NULL),
('refractory EGPA', 'Eosinophilic Granulomatosis with Polyangiitis', 'refractory', 'manual', 1.0, NULL),

-- Hidradenitis variants
('moderate-to-severe hidradenitis suppurativa', 'Hidradenitis Suppurativa', 'variant', 'manual', 1.0, NULL),
('refractory hidradenitis suppurativa', 'Hidradenitis Suppurativa', 'refractory', 'manual', 1.0, NULL),
('Hurley stage II/III hidradenitis', 'Hidradenitis Suppurativa', 'variant', 'manual', 1.0, NULL),

-- Vitiligo variants
('active vitiligo', 'Vitiligo', 'variant', 'manual', 1.0, NULL),
('progressive vitiligo', 'Vitiligo', 'variant', 'manual', 1.0, NULL),
('facial vitiligo', 'Vitiligo', 'subtype', 'manual', 1.0, NULL),

-- Pemphigus variants
('refractory pemphigus vulgaris', 'Pemphigus Vulgaris', 'refractory', 'manual', 1.0, NULL),
('pemphigus foliaceus', 'Pemphigus Vulgaris', 'subtype', 'manual', 0.9, 'Related but distinct'),

-- Prurigo Nodularis variants
('chronic prurigo nodularis', 'Prurigo Nodularis', 'variant', 'manual', 1.0, NULL),
('refractory prurigo nodularis', 'Prurigo Nodularis', 'refractory', 'manual', 1.0, NULL),

-- CSU variants
('refractory chronic spontaneous urticaria', 'Chronic Spontaneous Urticaria', 'refractory', 'manual', 1.0, NULL),
('antihistamine-refractory CSU', 'Chronic Spontaneous Urticaria', 'refractory', 'manual', 1.0, NULL),

-- Kidney disease variants
('IgA nephropathy with proteinuria', 'IgA Nephropathy', 'variant', 'manual', 1.0, NULL),
('progressive IgA nephropathy', 'IgA Nephropathy', 'variant', 'manual', 1.0, NULL),
('refractory membranous nephropathy', 'Membranous Nephropathy', 'refractory', 'manual', 1.0, NULL),
('primary membranous nephropathy', 'Membranous Nephropathy', 'subtype', 'manual', 1.0, NULL),
('steroid-resistant nephrotic syndrome', 'Focal Segmental Glomerulosclerosis', 'variant', 'manual', 0.9, NULL),
('primary FSGS', 'Focal Segmental Glomerulosclerosis', 'subtype', 'manual', 1.0, NULL),
('refractory aHUS', 'Atypical Hemolytic Uremic Syndrome', 'refractory', 'manual', 1.0, NULL),

-- Liver disease variants
('refractory primary biliary cholangitis', 'Primary Biliary Cholangitis', 'refractory', 'manual', 1.0, NULL),
('ursodiol-refractory PBC', 'Primary Biliary Cholangitis', 'refractory', 'manual', 1.0, NULL),
('refractory autoimmune hepatitis', 'Autoimmune Hepatitis', 'refractory', 'manual', 1.0, NULL),
('advanced NASH', 'Nonalcoholic Steatohepatitis', 'variant', 'manual', 1.0, NULL),
('NASH with fibrosis', 'Nonalcoholic Steatohepatitis', 'variant', 'manual', 1.0, NULL),

-- Hematologic variants
('refractory PNH', 'Paroxysmal Nocturnal Hemoglobinuria', 'refractory', 'manual', 1.0, NULL),
('severe aplastic anemia', 'Aplastic Anemia', 'variant', 'manual', 1.0, NULL),
('refractory TTP', 'Thrombotic Thrombocytopenic Purpura', 'refractory', 'manual', 1.0, NULL),
('acquired thrombotic thrombocytopenic purpura', 'Acquired TTP', 'variant', 'manual', 1.0, NULL),
('refractory cold agglutinin disease', 'Cold Agglutinin Disease', 'refractory', 'manual', 1.0, NULL),
('transfusion-dependent beta thalassemia', 'Beta Thalassemia', 'variant', 'manual', 1.0, NULL),
('severe sickle cell disease', 'Sickle Cell Disease', 'variant', 'manual', 1.0, NULL),
('sickle cell disease with vaso-occlusive crisis', 'Sickle Cell Disease', 'variant', 'manual', 1.0, NULL),

-- Ophthalmology variants
('moderate-to-severe thyroid eye disease', 'Thyroid Eye Disease', 'variant', 'manual', 1.0, NULL),
('active thyroid eye disease', 'Thyroid Eye Disease', 'variant', 'manual', 1.0, NULL),
('Graves'' ophthalmopathy', 'Thyroid Eye Disease', 'variant', 'manual', 1.0, NULL),
('wet AMD', 'Age-Related Macular Degeneration', 'subtype', 'manual', 1.0, NULL),
('neovascular AMD', 'Age-Related Macular Degeneration', 'subtype', 'manual', 1.0, NULL),
('center-involving diabetic macular edema', 'Diabetic Macular Edema', 'variant', 'manual', 1.0, NULL),
('CI-DME', 'Diabetic Macular Edema', 'variant', 'manual', 1.0, NULL),
('proliferative diabetic retinopathy', 'Diabetic Retinopathy', 'subtype', 'manual', 1.0, NULL),
('PDR', 'Diabetic Retinopathy', 'subtype', 'manual', 1.0, NULL),
('non-proliferative diabetic retinopathy', 'Diabetic Retinopathy', 'subtype', 'manual', 1.0, NULL),
('NPDR', 'Diabetic Retinopathy', 'subtype', 'manual', 1.0, NULL),

-- Endocrine variants
('refractory Graves'' disease', 'Graves Disease', 'refractory', 'manual', 1.0, NULL),
('Graves'' hyperthyroidism', 'Graves Disease', 'variant', 'manual', 1.0, NULL),
('new-onset type 1 diabetes', 'Type 1 Diabetes', 'variant', 'manual', 1.0, NULL),
('recent-onset T1D', 'Type 1 Diabetes', 'variant', 'manual', 1.0, NULL),

-- Neurology variants
('acute Guillain-Barre syndrome', 'Guillain-Barre Syndrome', 'variant', 'manual', 1.0, NULL),
('refractory CIDP', 'Chronic Inflammatory Demyelinating Polyneuropathy', 'refractory', 'manual', 1.0, NULL),
('typical CIDP', 'Chronic Inflammatory Demyelinating Polyneuropathy', 'subtype', 'manual', 1.0, NULL),
('atypical CIDP', 'Chronic Inflammatory Demyelinating Polyneuropathy', 'subtype', 'manual', 1.0, NULL),
('refractory stiff person syndrome', 'Stiff Person Syndrome', 'refractory', 'manual', 1.0, NULL),
('anti-NMDA receptor encephalitis', 'Autoimmune Encephalitis', 'subtype', 'manual', 1.0, NULL),
('anti-LGI1 encephalitis', 'Autoimmune Encephalitis', 'subtype', 'manual', 1.0, NULL),
('anti-CASPR2 encephalitis', 'Autoimmune Encephalitis', 'subtype', 'manual', 1.0, NULL),
('refractory autoimmune encephalitis', 'Autoimmune Encephalitis', 'refractory', 'manual', 1.0, NULL),
('AQP4-positive NMOSD', 'Neuromyelitis Optica Spectrum Disorder', 'subtype', 'manual', 1.0, NULL),
('AQP4-IgG positive NMOSD', 'Neuromyelitis Optica Spectrum Disorder', 'subtype', 'manual', 1.0, NULL),
('seronegative NMOSD', 'Neuromyelitis Optica Spectrum Disorder', 'subtype', 'manual', 1.0, NULL),
('MOG antibody-associated disorder', 'Anti-MOG Associated Disease', 'variant', 'manual', 1.0, NULL),
('MOGAD with optic neuritis', 'Anti-MOG Associated Disease', 'variant', 'manual', 1.0, NULL),
('sporadic ALS', 'Amyotrophic Lateral Sclerosis', 'subtype', 'manual', 1.0, NULL),
('familial ALS', 'Amyotrophic Lateral Sclerosis', 'subtype', 'manual', 1.0, NULL),

-- Sarcoidosis variants
('refractory sarcoidosis', 'Sarcoidosis', 'refractory', 'manual', 1.0, NULL),
('pulmonary sarcoidosis', 'Sarcoidosis', 'subtype', 'manual', 1.0, NULL),
('cardiac sarcoidosis', 'Cardiac Sarcoidosis', 'subtype', 'manual', 1.0, NULL),
('refractory cardiac sarcoidosis', 'Cardiac Sarcoidosis', 'refractory', 'manual', 1.0, NULL),
('cutaneous sarcoidosis', 'Sarcoidosis', 'subtype', 'manual', 1.0, NULL),
('ocular sarcoidosis', 'Sarcoidosis', 'subtype', 'manual', 1.0, NULL),
('neurosarcoidosis', 'Sarcoidosis', 'subtype', 'manual', 1.0, NULL),

-- GI variants
('refractory celiac disease', 'Celiac Disease', 'refractory', 'manual', 1.0, NULL),
('refractory eosinophilic esophagitis', 'Eosinophilic Esophagitis', 'refractory', 'manual', 1.0, NULL),
('fibrostenotic EoE', 'Eosinophilic Esophagitis', 'subtype', 'manual', 1.0, NULL),
('inflammatory EoE', 'Eosinophilic Esophagitis', 'subtype', 'manual', 1.0, NULL),
('type 1 autoimmune pancreatitis', 'Autoimmune Pancreatitis', 'subtype', 'manual', 1.0, NULL),
('type 2 autoimmune pancreatitis', 'Autoimmune Pancreatitis', 'subtype', 'manual', 1.0, NULL),

-- IgG4-RD variants
('IgG4-related sclerosing cholangitis', 'IgG4-Related Disease', 'subtype', 'manual', 1.0, NULL),
('IgG4-related orbital disease', 'IgG4-Related Disease', 'subtype', 'manual', 1.0, NULL),
('IgG4-related sialadenitis', 'IgG4-Related Disease', 'subtype', 'manual', 1.0, NULL),
('IgG4-related aortitis', 'IgG4-Related Disease', 'subtype', 'manual', 1.0, NULL),
('Mikulicz disease', 'IgG4-Related Disease', 'subtype', 'manual', 1.0, NULL),
('refractory IgG4-related disease', 'IgG4-Related Disease', 'refractory', 'manual', 1.0, NULL),

-- Autoinflammatory variants
('refractory FMF', 'Familial Mediterranean Fever', 'refractory', 'manual', 1.0, NULL),
('colchicine-resistant FMF', 'Familial Mediterranean Fever', 'refractory', 'manual', 1.0, NULL),
('NOMID', 'Cryopyrin-Associated Periodic Syndrome', 'subtype', 'manual', 1.0, NULL),
('Muckle-Wells syndrome', 'Cryopyrin-Associated Periodic Syndrome', 'subtype', 'manual', 1.0, NULL),
('FCAS', 'Cryopyrin-Associated Periodic Syndrome', 'subtype', 'manual', 1.0, NULL),
('refractory CAPS', 'Cryopyrin-Associated Periodic Syndrome', 'refractory', 'manual', 1.0, NULL),
('primary HLH', 'Hemophagocytic Lymphohistiocytosis', 'subtype', 'manual', 1.0, NULL),
('secondary HLH', 'Hemophagocytic Lymphohistiocytosis', 'subtype', 'manual', 1.0, NULL),
('refractory HLH', 'Hemophagocytic Lymphohistiocytosis', 'refractory', 'manual', 1.0, NULL),
('MAS secondary to sJIA', 'Macrophage Activation Syndrome', 'variant', 'manual', 1.0, NULL),
('refractory MAS', 'Macrophage Activation Syndrome', 'refractory', 'manual', 1.0, NULL),

-- Hereditary Angioedema variants
('HAE type I', 'Hereditary Angioedema', 'subtype', 'manual', 1.0, NULL),
('HAE type II', 'Hereditary Angioedema', 'subtype', 'manual', 1.0, NULL),
('HAE with normal C1-INH', 'Hereditary Angioedema', 'subtype', 'manual', 1.0, NULL),
('refractory HAE', 'Hereditary Angioedema', 'refractory', 'manual', 1.0, NULL),

-- Rare genetic variants
('late-onset Pompe disease', 'Pompe Disease', 'subtype', 'manual', 1.0, NULL),
('infantile-onset Pompe disease', 'Pompe Disease', 'subtype', 'manual', 1.0, NULL),
('type 1 Gaucher disease', 'Gaucher Disease', 'subtype', 'manual', 1.0, NULL),
('type 3 Gaucher disease', 'Gaucher Disease', 'subtype', 'manual', 1.0, NULL),
('classic Fabry disease', 'Fabry Disease', 'subtype', 'manual', 1.0, NULL),
('late-onset Fabry disease', 'Fabry Disease', 'subtype', 'manual', 1.0, NULL),
('ambulatory DMD', 'Duchenne Muscular Dystrophy', 'variant', 'manual', 1.0, NULL),
('non-ambulatory DMD', 'Duchenne Muscular Dystrophy', 'variant', 'manual', 1.0, NULL),
('SMA type 1', 'Spinal Muscular Atrophy', 'subtype', 'manual', 1.0, NULL),
('SMA type 2', 'Spinal Muscular Atrophy', 'subtype', 'manual', 1.0, NULL),
('SMA type 3', 'Spinal Muscular Atrophy', 'subtype', 'manual', 1.0, NULL),
('later-onset SMA', 'Spinal Muscular Atrophy', 'subtype', 'manual', 1.0, NULL),

-- Pemphigoid/pemphigus extended variants
('refractory bullous pemphigoid', 'Bullous Pemphigoid', 'refractory', 'manual', 1.0, NULL),
('refractory mucous membrane pemphigoid', 'Mucous Membrane Pemphigoid', 'refractory', 'manual', 1.0, NULL),
('ocular cicatricial pemphigoid', 'Mucous Membrane Pemphigoid', 'subtype', 'manual', 1.0, NULL),

-- Antisynthetase Syndrome variants
('refractory antisynthetase syndrome', 'Antisynthetase Syndrome', 'refractory', 'manual', 1.0, NULL),
('antisynthetase syndrome with ILD', 'Antisynthetase Syndrome', 'variant', 'manual', 1.0, NULL),
('anti-Jo-1 syndrome', 'Antisynthetase Syndrome', 'subtype', 'manual', 1.0, NULL),
('anti-synthetase syndrome with mechanic''s hands', 'Antisynthetase Syndrome', 'variant', 'manual', 1.0, NULL),

-- Inclusion Body Myositis variants
('refractory inclusion body myositis', 'Inclusion Body Myositis', 'refractory', 'manual', 1.0, NULL),
('sporadic IBM', 'Inclusion Body Myositis', 'subtype', 'manual', 1.0, NULL),

-- Mixed Connective Tissue Disease
('mixed connective tissue disease', 'Mixed Connective Tissue Disease', 'variant', 'manual', 1.0, NULL),
('MCTD', 'Mixed Connective Tissue Disease', 'abbreviation', 'manual', 1.0, NULL),
('Sharp syndrome', 'Mixed Connective Tissue Disease', 'synonym', 'manual', 0.9, NULL),
('overlap syndrome', 'Mixed Connective Tissue Disease', 'synonym', 'manual', 0.8, NULL),
('refractory MCTD', 'Mixed Connective Tissue Disease', 'refractory', 'manual', 1.0, NULL),
('undifferentiated connective tissue disease', 'Mixed Connective Tissue Disease', 'variant', 'manual', 0.9, NULL),

-- Antiphospholipid Syndrome variants
('primary APS', 'Antiphospholipid Syndrome', 'subtype', 'manual', 1.0, NULL),
('secondary APS', 'Antiphospholipid Syndrome', 'subtype', 'manual', 1.0, NULL),
('obstetric APS', 'Antiphospholipid Syndrome', 'subtype', 'manual', 1.0, NULL),
('thrombotic APS', 'Antiphospholipid Syndrome', 'subtype', 'manual', 1.0, NULL),
('refractory antiphospholipid syndrome', 'Antiphospholipid Syndrome', 'refractory', 'manual', 1.0, NULL),
('catastrophic APS', 'Catastrophic Antiphospholipid Syndrome', 'variant', 'manual', 1.0, NULL),
('refractory CAPS', 'Catastrophic Antiphospholipid Syndrome', 'refractory', 'manual', 1.0, NULL),

-- Relapsing Polychondritis variants
('refractory relapsing polychondritis', 'Relapsing Polychondritis', 'refractory', 'manual', 1.0, NULL),
('MAGIC syndrome', 'Relapsing Polychondritis', 'variant', 'manual', 0.9, 'Mouth and genital ulcers with inflamed cartilage'),

-- Spondyloarthritis variants
('peripheral spondyloarthritis', 'Peripheral Spondyloarthritis', 'variant', 'manual', 1.0, NULL),
('reactive arthritis post-infectious', 'Reactive Arthritis', 'variant', 'manual', 1.0, NULL),
('refractory reactive arthritis', 'Reactive Arthritis', 'refractory', 'manual', 1.0, NULL),
('IBD-associated arthritis', 'Enteropathic Arthritis', 'variant', 'manual', 1.0, NULL),
('Crohn''s associated arthritis', 'Enteropathic Arthritis', 'subtype', 'manual', 1.0, NULL),
('UC-associated arthritis', 'Enteropathic Arthritis', 'subtype', 'manual', 1.0, NULL),

-- Gout variants
('refractory gout', 'Gout', 'refractory', 'manual', 1.0, NULL),
('chronic refractory gout', 'Gout', 'refractory', 'manual', 1.0, NULL),
('uncontrolled gout', 'Gout', 'variant', 'manual', 1.0, NULL),
('tophaceous gout', 'Gout', 'subtype', 'manual', 1.0, NULL),
('acute gout flare', 'Gout', 'variant', 'manual', 1.0, NULL),

-- Systemic Mastocytosis variants
('indolent systemic mastocytosis', 'Systemic Mastocytosis', 'subtype', 'manual', 1.0, NULL),
('ISM', 'Systemic Mastocytosis', 'subtype', 'manual', 1.0, NULL),
('aggressive systemic mastocytosis', 'Advanced Systemic Mastocytosis', 'subtype', 'manual', 1.0, NULL),
('ASM', 'Advanced Systemic Mastocytosis', 'subtype', 'manual', 1.0, NULL),
('mast cell leukemia', 'Advanced Systemic Mastocytosis', 'subtype', 'manual', 1.0, NULL),
('SM with associated hematologic neoplasm', 'Advanced Systemic Mastocytosis', 'subtype', 'manual', 1.0, NULL),
('SM-AHN', 'Advanced Systemic Mastocytosis', 'subtype', 'manual', 1.0, NULL),

-- Eosinophilic disorder variants
('refractory HES', 'Hypereosinophilic Syndrome', 'refractory', 'manual', 1.0, NULL),
('idiopathic HES', 'Hypereosinophilic Syndrome', 'subtype', 'manual', 1.0, NULL),
('lymphocytic variant HES', 'Hypereosinophilic Syndrome', 'subtype', 'manual', 1.0, NULL),
('myeloproliferative HES', 'Hypereosinophilic Syndrome', 'subtype', 'manual', 1.0, NULL),

-- Myocarditis/Pericarditis variants
('autoimmune myocarditis', 'Myocarditis', 'subtype', 'manual', 1.0, NULL),
('giant cell myocarditis', 'Myocarditis', 'subtype', 'manual', 1.0, NULL),
('checkpoint inhibitor myocarditis', 'Myocarditis', 'subtype', 'manual', 1.0, NULL),
('immune checkpoint inhibitor myocarditis', 'Myocarditis', 'subtype', 'manual', 1.0, NULL),
('recurrent pericarditis', 'Pericarditis', 'subtype', 'manual', 1.0, NULL),
('refractory recurrent pericarditis', 'Pericarditis', 'refractory', 'manual', 1.0, NULL),
('colchicine-resistant pericarditis', 'Pericarditis', 'refractory', 'manual', 1.0, NULL),
('idiopathic recurrent pericarditis', 'Pericarditis', 'subtype', 'manual', 1.0, NULL),

-- ANCA vasculitis expanded
('severe GPA', 'Granulomatosis with Polyangiitis', 'variant', 'manual', 1.0, NULL),
('limited GPA', 'Granulomatosis with Polyangiitis', 'variant', 'manual', 1.0, NULL),
('PR3-ANCA vasculitis', 'ANCA-Associated Vasculitis', 'subtype', 'manual', 1.0, NULL),
('MPO-ANCA vasculitis', 'ANCA-Associated Vasculitis', 'subtype', 'manual', 1.0, NULL),
('renal-limited vasculitis', 'ANCA-Associated Vasculitis', 'subtype', 'manual', 1.0, NULL),
('refractory ANCA vasculitis', 'ANCA-Associated Vasculitis', 'refractory', 'manual', 1.0, NULL),
('relapsing ANCA vasculitis', 'ANCA-Associated Vasculitis', 'variant', 'manual', 1.0, NULL),

-- PsA variants
('refractory psoriatic arthritis', 'Psoriatic Arthritis', 'refractory', 'manual', 1.0, NULL),
('peripheral psoriatic arthritis', 'Psoriatic Arthritis', 'subtype', 'manual', 1.0, NULL),
('axial psoriatic arthritis', 'Psoriatic Arthritis', 'subtype', 'manual', 1.0, NULL),
('dactylitis in PsA', 'Psoriatic Arthritis', 'variant', 'manual', 1.0, NULL),
('enthesitis in PsA', 'Psoriatic Arthritis', 'variant', 'manual', 1.0, NULL),

-- AxSpA variants
('active ankylosing spondylitis', 'Axial Spondyloarthritis', 'variant', 'manual', 1.0, NULL),
('refractory ankylosing spondylitis', 'Axial Spondyloarthritis', 'refractory', 'manual', 1.0, NULL),
('nr-axSpA with objective signs', 'Axial Spondyloarthritis', 'subtype', 'manual', 1.0, NULL),
('radiographic axial spondyloarthritis', 'Axial Spondyloarthritis', 'subtype', 'manual', 1.0, NULL),
('r-axSpA', 'Axial Spondyloarthritis', 'subtype', 'manual', 1.0, NULL),
('HLA-B27 positive axSpA', 'Axial Spondyloarthritis', 'subtype', 'manual', 1.0, NULL)
ON CONFLICT (specific_name) DO NOTHING;

-- =====================================================
-- SUMMARY STATISTICS QUERY (run after seeding)
-- =====================================================
-- SELECT
--     (SELECT COUNT(DISTINCT canonical_name) FROM cs_disease_name_variants) as unique_diseases_with_variants,
--     (SELECT COUNT(*) FROM cs_disease_name_variants) as total_variants,
--     (SELECT COUNT(*) FROM cs_disease_parent_mappings) as total_parent_mappings,
--     (SELECT COUNT(DISTINCT parent_name) FROM cs_disease_parent_mappings) as unique_parent_diseases;

