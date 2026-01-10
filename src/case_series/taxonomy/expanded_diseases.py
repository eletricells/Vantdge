"""
Expanded Disease Taxonomy

Contains 295+ indications from the Trial Matrix, organized by therapeutic category.
Includes aliases, subtypes, and standard endpoints.
"""

from typing import Dict
from src.case_series.taxonomy.disease_taxonomy import DiseaseEntry, EndpointDefinition


def get_expanded_disease_entries() -> Dict[str, DiseaseEntry]:
    """
    Get expanded disease entries covering autoimmune, rare, and other diseases.

    Categories:
    - Inflammatory Myopathies
    - Rheumatic Diseases
    - Dermatologic Diseases
    - Respiratory Diseases
    - Gastrointestinal Diseases
    - Neurological Diseases
    - Hematologic Diseases
    - Renal Diseases
    - Cardiovascular Diseases
    - Ophthalmologic Diseases
    - Oncology
    - Transplant
    - Other Autoimmune
    """
    diseases = {}

    # =========================================================================
    # INFLAMMATORY MYOPATHIES
    # =========================================================================

    diseases["Dermatomyositis"] = DiseaseEntry(
        canonical_name="Dermatomyositis",
        category="Inflammatory Myopathies",
        parent_disease=None,
        subtypes=[
            "Amyopathic Dermatomyositis",
            "Hypomyopathic Dermatomyositis",
            "Classic Dermatomyositis",
            "Juvenile Dermatomyositis",
            "Clinically Amyopathic Dermatomyositis",
            "Anti-MDA5 Dermatomyositis",
        ],
        aliases=["DM", "dermatomyositis", "adult dermatomyositis"],
        icd10_codes=["M33.1", "M33.10", "M33.11", "M33.12"],
        standard_endpoints=[
            EndpointDefinition(name="CDASI", full_name="Cutaneous Dermatomyositis Disease Area and Severity Index", category="efficacy", aliases=["cdasi score"], is_validated=True),
            EndpointDefinition(name="MMT8", full_name="Manual Muscle Testing 8", category="efficacy", aliases=["mmt-8", "manual muscle test"], is_validated=True),
            EndpointDefinition(name="Physician Global", full_name="Physician Global Assessment", category="efficacy", aliases=["PGA"], is_validated=True),
            EndpointDefinition(name="HAQ-DI", full_name="Health Assessment Questionnaire Disability Index", category="PRO", is_validated=True),
            EndpointDefinition(name="CK", full_name="Creatine Kinase", category="biomarker", aliases=["creatine kinase"]),
        ],
        prevalence_per_100k=1.0,
        is_rare=True,
    )

    diseases["Polymyositis"] = DiseaseEntry(
        canonical_name="Polymyositis",
        category="Inflammatory Myopathies",
        parent_disease=None,
        subtypes=[],
        aliases=["PM", "polymyositis"],
        icd10_codes=["M33.2"],
        standard_endpoints=[
            EndpointDefinition(name="MMT8", full_name="Manual Muscle Testing 8", category="efficacy", is_validated=True),
            EndpointDefinition(name="CK", full_name="Creatine Kinase", category="biomarker"),
        ],
        prevalence_per_100k=0.5,
        is_rare=True,
    )

    diseases["Inclusion Body Myositis"] = DiseaseEntry(
        canonical_name="Inclusion Body Myositis",
        category="Inflammatory Myopathies",
        parent_disease=None,
        subtypes=[],
        aliases=["IBM", "sporadic inclusion body myositis", "sIBM"],
        icd10_codes=["G72.41"],
        standard_endpoints=[
            EndpointDefinition(name="6MWD", full_name="6-Minute Walk Distance", category="efficacy", is_validated=True),
            EndpointDefinition(name="IBM-FRS", full_name="IBM Functional Rating Scale", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=0.5,
        is_rare=True,
    )

    # =========================================================================
    # RHEUMATIC DISEASES
    # =========================================================================

    diseases["Rheumatoid Arthritis"] = DiseaseEntry(
        canonical_name="Rheumatoid Arthritis",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=[
            "Seropositive Rheumatoid Arthritis",
            "Seronegative Rheumatoid Arthritis",
            "Early Rheumatoid Arthritis",
            "TNF-IR Rheumatoid Arthritis",
            "Biologic-IR Rheumatoid Arthritis",
        ],
        aliases=["RA", "rheumatoid", "Early RA", "RA (TNF-IR)", "RA (bio-IR)"],
        icd10_codes=["M05", "M06"],
        standard_endpoints=[
            EndpointDefinition(name="ACR20", full_name="ACR 20% Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="ACR50", full_name="ACR 50% Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="ACR70", full_name="ACR 70% Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="DAS28", full_name="Disease Activity Score 28", category="efficacy", aliases=["DAS28-CRP", "DAS28-ESR"], is_validated=True),
            EndpointDefinition(name="HAQ-DI", full_name="Health Assessment Questionnaire", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=500.0,
        is_rare=False,
    )

    diseases["Psoriatic Arthritis"] = DiseaseEntry(
        canonical_name="Psoriatic Arthritis",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=["Peripheral Psoriatic Arthritis", "Axial Psoriatic Arthritis", "TNF-IR Psoriatic Arthritis"],
        aliases=["PsA", "PsA (TNF-IR)"],
        icd10_codes=["L40.5", "M07"],
        standard_endpoints=[
            EndpointDefinition(name="ACR20", full_name="ACR 20% Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="MDA", full_name="Minimal Disease Activity", category="efficacy", is_validated=True),
            EndpointDefinition(name="DAPSA", full_name="Disease Activity in Psoriatic Arthritis", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    diseases["Ankylosing Spondylitis"] = DiseaseEntry(
        canonical_name="Ankylosing Spondylitis",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=["TNF-IR Ankylosing Spondylitis"],
        aliases=["AS", "AS (TNF-IR)", "axial spondyloarthritis"],
        icd10_codes=["M45"],
        standard_endpoints=[
            EndpointDefinition(name="ASAS20", full_name="ASAS 20% Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="ASAS40", full_name="ASAS 40% Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="BASDAI", full_name="Bath Ankylosing Spondylitis Disease Activity Index", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=200.0,
        is_rare=False,
    )

    diseases["Non-radiographic Axial Spondyloarthritis"] = DiseaseEntry(
        canonical_name="Non-radiographic Axial Spondyloarthritis",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["nr-axSpA", "non-radiographic axSpA"],
        icd10_codes=["M46.8"],
        standard_endpoints=[
            EndpointDefinition(name="ASAS40", full_name="ASAS 40% Response", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    diseases["Juvenile Idiopathic Arthritis"] = DiseaseEntry(
        canonical_name="Juvenile Idiopathic Arthritis",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=["Polyarticular JIA", "Systemic JIA"],
        aliases=["JIA", "Polyarticular JIA", "sJIA", "Systemic JIA"],
        icd10_codes=["M08"],
        standard_endpoints=[
            EndpointDefinition(name="ACR-Pedi-30", full_name="ACR Pediatric 30% Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="JADAS", full_name="Juvenile Arthritis Disease Activity Score", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=20.0,
        is_rare=True,
    )

    diseases["Gout"] = DiseaseEntry(
        canonical_name="Gout",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=["Acute Gout", "Chronic Gout"],
        aliases=["Acute Gout", "Gout Flares"],
        icd10_codes=["M10"],
        standard_endpoints=[
            EndpointDefinition(name="Pain VAS", full_name="Pain Visual Analog Scale", category="PRO", is_validated=True),
            EndpointDefinition(name="Flare Rate", full_name="Gout Flare Rate", category="efficacy"),
        ],
        prevalence_per_100k=4000.0,
        is_rare=False,
    )

    diseases["Giant Cell Arteritis"] = DiseaseEntry(
        canonical_name="Giant Cell Arteritis",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["GCA", "temporal arteritis"],
        icd10_codes=["M31.5", "M31.6"],
        standard_endpoints=[
            EndpointDefinition(name="Sustained Remission", full_name="Sustained Clinical Remission", category="efficacy", is_validated=True),
            EndpointDefinition(name="GC Sparing", full_name="Glucocorticoid Sparing", category="efficacy"),
        ],
        prevalence_per_100k=20.0,
        is_rare=True,
    )

    diseases["Polymyalgia Rheumatica"] = DiseaseEntry(
        canonical_name="Polymyalgia Rheumatica",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["PMR"],
        icd10_codes=["M35.3"],
        standard_endpoints=[
            EndpointDefinition(name="PMR-AS", full_name="PMR Activity Score", category="efficacy"),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    diseases["Osteoarthritis"] = DiseaseEntry(
        canonical_name="Osteoarthritis",
        category="Rheumatic Diseases",
        parent_disease=None,
        subtypes=["Knee Osteoarthritis", "Hip Osteoarthritis"],
        aliases=["OA"],
        icd10_codes=["M15", "M16", "M17"],
        standard_endpoints=[
            EndpointDefinition(name="WOMAC", full_name="Western Ontario and McMaster Universities Osteoarthritis Index", category="PRO", is_validated=True),
            EndpointDefinition(name="Pain VAS", full_name="Pain Visual Analog Scale", category="PRO"),
        ],
        prevalence_per_100k=10000.0,
        is_rare=False,
    )

    # =========================================================================
    # LUPUS
    # =========================================================================

    diseases["Systemic Lupus Erythematosus"] = DiseaseEntry(
        canonical_name="Systemic Lupus Erythematosus",
        category="Lupus",
        parent_disease=None,
        subtypes=["Lupus Nephritis", "Cutaneous Lupus", "Neuropsychiatric Lupus", "Pediatric SLE"],
        aliases=["SLE", "lupus", "Systemic Lupus", "SLE with Arthritis"],
        icd10_codes=["M32"],
        standard_endpoints=[
            EndpointDefinition(name="SRI-4", full_name="SLE Responder Index 4", category="efficacy", is_validated=True),
            EndpointDefinition(name="SLEDAI", full_name="SLE Disease Activity Index", category="efficacy", is_validated=True),
            EndpointDefinition(name="BILAG", full_name="British Isles Lupus Assessment Group", category="efficacy", is_validated=True),
            EndpointDefinition(name="CLASI", full_name="Cutaneous Lupus Disease Area and Severity Index", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    diseases["Lupus Nephritis"] = DiseaseEntry(
        canonical_name="Lupus Nephritis",
        category="Lupus",
        parent_disease="Systemic Lupus Erythematosus",
        subtypes=["Class III Lupus Nephritis", "Class IV Lupus Nephritis", "Class V Lupus Nephritis"],
        aliases=["LN", "Lupus Nephritis (Class III/IV)"],
        icd10_codes=["M32.14"],
        standard_endpoints=[
            EndpointDefinition(name="Complete Renal Response", full_name="Complete Renal Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="Proteinuria", full_name="Proteinuria Reduction", category="efficacy"),
            EndpointDefinition(name="eGFR", full_name="Estimated Glomerular Filtration Rate", category="efficacy"),
        ],
        prevalence_per_100k=10.0,
        is_rare=True,
    )

    diseases["Cutaneous Lupus"] = DiseaseEntry(
        canonical_name="Cutaneous Lupus",
        category="Lupus",
        parent_disease="Systemic Lupus Erythematosus",
        subtypes=["Discoid Lupus"],
        aliases=["CLE", "Discoid Lupus"],
        icd10_codes=["L93"],
        standard_endpoints=[
            EndpointDefinition(name="CLASI", full_name="Cutaneous Lupus Disease Area and Severity Index", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=30.0,
        is_rare=False,
    )

    # =========================================================================
    # DERMATOLOGIC DISEASES
    # =========================================================================

    diseases["Psoriasis"] = DiseaseEntry(
        canonical_name="Psoriasis",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=["Plaque Psoriasis", "Guttate Psoriasis", "Pustular Psoriasis", "Palmoplantar Pustulosis", "Scalp Psoriasis", "Nail Psoriasis"],
        aliases=["PsO", "Plaque Psoriasis", "PsO (UST-IR)"],
        icd10_codes=["L40"],
        standard_endpoints=[
            EndpointDefinition(name="PASI", full_name="Psoriasis Area and Severity Index", category="efficacy", aliases=["PASI75", "PASI90", "PASI100"], is_validated=True),
            EndpointDefinition(name="IGA", full_name="Investigator Global Assessment", category="efficacy", is_validated=True),
            EndpointDefinition(name="BSA", full_name="Body Surface Area", category="efficacy"),
            EndpointDefinition(name="DLQI", full_name="Dermatology Life Quality Index", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=2000.0,
        is_rare=False,
    )

    diseases["Generalized Pustular Psoriasis"] = DiseaseEntry(
        canonical_name="Generalized Pustular Psoriasis",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=["GPP Flares", "GPP Prevention"],
        aliases=["GPP", "GPP Flares", "GPP Prevention"],
        icd10_codes=["L40.1"],
        standard_endpoints=[
            EndpointDefinition(name="GPPGA", full_name="GPP Physician Global Assessment", category="efficacy", is_validated=True),
            EndpointDefinition(name="GPPASI", full_name="GPP Area and Severity Index", category="efficacy"),
        ],
        prevalence_per_100k=0.5,
        is_rare=True,
    )

    diseases["Atopic Dermatitis"] = DiseaseEntry(
        canonical_name="Atopic Dermatitis",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=["Moderate Atopic Dermatitis", "Severe Atopic Dermatitis", "Adolescent Atopic Dermatitis", "Pediatric Atopic Dermatitis"],
        aliases=["AD", "eczema", "Atopic Dermatitis (+TCS)", "Atopic Dermatitis (adult)", "Atopic Dermatitis (adolescents)"],
        icd10_codes=["L20"],
        standard_endpoints=[
            EndpointDefinition(name="EASI", full_name="Eczema Area and Severity Index", category="efficacy", aliases=["EASI75", "EASI90"], is_validated=True),
            EndpointDefinition(name="IGA", full_name="Investigator Global Assessment", category="efficacy", is_validated=True),
            EndpointDefinition(name="Pruritus NRS", full_name="Pruritus Numerical Rating Scale", category="PRO", is_validated=True),
            EndpointDefinition(name="SCORAD", full_name="Scoring Atopic Dermatitis", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=1000.0,
        is_rare=False,
    )

    diseases["Alopecia Areata"] = DiseaseEntry(
        canonical_name="Alopecia Areata",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=[
            "Alopecia Totalis",
            "Alopecia Universalis",
            "Patchy Alopecia Areata",
            "Severe Alopecia Areata",
            "Moderate-to-Severe Alopecia Areata",
            "Ophiasis",
            "Sisaipho",
            "Diffuse Alopecia Areata",
            "Pediatric Alopecia Areata",
            "Alopecia Areata with Nail Involvement",
        ],
        aliases=[
            "AA",
            "alopecia",
            "spot baldness",
            "severe alopecia areata",
            "moderate to severe alopecia areata",
            "refractory alopecia areata",
            "extensive alopecia areata",
            "alopecia areata universalis",
            "alopecia areata totalis",
            "severe AA",
            "pediatric alopecia universalis",
        ],
        icd10_codes=["L63", "L63.0", "L63.1", "L63.2", "L63.8", "L63.9"],
        standard_endpoints=[
            EndpointDefinition(name="SALT", full_name="Severity of Alopecia Tool", category="efficacy", is_validated=True, typical_responder_threshold="SALT ≤20 or 50% improvement"),
            EndpointDefinition(name="Regrowth", full_name="Hair Regrowth Assessment", category="efficacy"),
            EndpointDefinition(name="AASIS", full_name="Alopecia Areata Symptom Impact Scale", category="PRO"),
            EndpointDefinition(name="Skindex-16", full_name="Skindex-16 Quality of Life", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=200.0,
        is_rare=False,
    )

    diseases["Vitiligo"] = DiseaseEntry(
        canonical_name="Vitiligo",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=["Non-segmental Vitiligo", "Segmental Vitiligo"],
        aliases=[],
        icd10_codes=["L80"],
        standard_endpoints=[
            EndpointDefinition(name="F-VASI", full_name="Facial Vitiligo Area Scoring Index", category="efficacy", is_validated=True),
            EndpointDefinition(name="T-VASI", full_name="Total Vitiligo Area Scoring Index", category="efficacy", is_validated=True),
            EndpointDefinition(name="Repigmentation", full_name="Repigmentation Assessment", category="efficacy"),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    diseases["Hidradenitis Suppurativa"] = DiseaseEntry(
        canonical_name="Hidradenitis Suppurativa",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["HS", "Hidradenitis", "acne inversa"],
        icd10_codes=["L73.2"],
        standard_endpoints=[
            EndpointDefinition(name="HiSCR", full_name="Hidradenitis Suppurativa Clinical Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="AN Count", full_name="Abscess and Nodule Count", category="efficacy"),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    diseases["Chronic Spontaneous Urticaria"] = DiseaseEntry(
        canonical_name="Chronic Spontaneous Urticaria",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=["Omalizumab-IR CSU", "Cold Urticaria", "Symptomatic Dermographism"],
        aliases=["CSU", "chronic urticaria", "CSU (omalizumab-IR)", "Chronic Urticaria", "Cold Urticaria", "Symptomatic Dermographism"],
        icd10_codes=["L50.1"],
        standard_endpoints=[
            EndpointDefinition(name="UAS7", full_name="Urticaria Activity Score 7", category="efficacy", is_validated=True),
            EndpointDefinition(name="ISS7", full_name="Itch Severity Score 7", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    diseases["Prurigo Nodularis"] = DiseaseEntry(
        canonical_name="Prurigo Nodularis",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["PN"],
        icd10_codes=["L28.1"],
        standard_endpoints=[
            EndpointDefinition(name="WI-NRS", full_name="Worst Itch Numerical Rating Scale", category="PRO", is_validated=True),
            EndpointDefinition(name="IGA-PN", full_name="Investigator Global Assessment for PN", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    diseases["Bullous Pemphigoid"] = DiseaseEntry(
        canonical_name="Bullous Pemphigoid",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["BP"],
        icd10_codes=["L12.0"],
        standard_endpoints=[
            EndpointDefinition(name="BPDAI", full_name="Bullous Pemphigoid Disease Area Index", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    diseases["Pemphigus"] = DiseaseEntry(
        canonical_name="Pemphigus",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=["Pemphigus Vulgaris", "Pemphigus Foliaceus"],
        aliases=["PV"],
        icd10_codes=["L10"],
        standard_endpoints=[
            EndpointDefinition(name="PDAI", full_name="Pemphigus Disease Area Index", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=2.0,
        is_rare=True,
    )

    diseases["Acne"] = DiseaseEntry(
        canonical_name="Acne",
        category="Dermatologic Diseases",
        parent_disease=None,
        subtypes=["Moderate Acne", "Severe Acne"],
        aliases=["acne vulgaris"],
        icd10_codes=["L70"],
        standard_endpoints=[
            EndpointDefinition(name="IGA", full_name="Investigator Global Assessment", category="efficacy", is_validated=True),
            EndpointDefinition(name="Lesion Count", full_name="Inflammatory Lesion Count", category="efficacy"),
        ],
        prevalence_per_100k=5000.0,
        is_rare=False,
    )

    # =========================================================================
    # RESPIRATORY DISEASES
    # =========================================================================

    diseases["Asthma"] = DiseaseEntry(
        canonical_name="Asthma",
        category="Respiratory Diseases",
        parent_disease=None,
        subtypes=[
            "Severe Asthma", "Eosinophilic Asthma", "Moderate-to-Severe Asthma",
            "OCS-Dependent Asthma", "Severe Refractory Asthma", "Severe Eosinophilic Asthma"
        ],
        aliases=["Severe Asthma", "Eosinophilic Asthma", "Moderate-Severe Asthma", "Asthma (biomarker-high)"],
        icd10_codes=["J45"],
        standard_endpoints=[
            EndpointDefinition(name="AAER", full_name="Annualized Asthma Exacerbation Rate", category="efficacy", is_validated=True),
            EndpointDefinition(name="FEV1", full_name="Forced Expiratory Volume in 1 Second", category="efficacy", is_validated=True),
            EndpointDefinition(name="ACQ", full_name="Asthma Control Questionnaire", category="PRO", is_validated=True),
            EndpointDefinition(name="OCS Reduction", full_name="Oral Corticosteroid Dose Reduction", category="efficacy"),
        ],
        prevalence_per_100k=8000.0,
        is_rare=False,
    )

    diseases["COPD"] = DiseaseEntry(
        canonical_name="COPD",
        category="Respiratory Diseases",
        parent_disease=None,
        subtypes=["Eosinophilic COPD"],
        aliases=["COPD (eos ≥300)", "COPD (All Smokers)", "COPD (Former Smokers)"],
        icd10_codes=["J44"],
        standard_endpoints=[
            EndpointDefinition(name="Exacerbation Rate", full_name="COPD Exacerbation Rate", category="efficacy", is_validated=True),
            EndpointDefinition(name="FEV1", full_name="Forced Expiratory Volume in 1 Second", category="efficacy", is_validated=True),
            EndpointDefinition(name="SGRQ", full_name="St. George's Respiratory Questionnaire", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=6000.0,
        is_rare=False,
    )

    diseases["Chronic Rhinosinusitis with Nasal Polyps"] = DiseaseEntry(
        canonical_name="Chronic Rhinosinusitis with Nasal Polyps",
        category="Respiratory Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["CRSwNP", "nasal polyps"],
        icd10_codes=["J33"],
        standard_endpoints=[
            EndpointDefinition(name="NPS", full_name="Nasal Polyp Score", category="efficacy", is_validated=True),
            EndpointDefinition(name="NCS", full_name="Nasal Congestion Score", category="PRO", is_validated=True),
            EndpointDefinition(name="SNOT-22", full_name="Sino-Nasal Outcome Test", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=2000.0,
        is_rare=False,
    )

    diseases["Idiopathic Pulmonary Fibrosis"] = DiseaseEntry(
        canonical_name="Idiopathic Pulmonary Fibrosis",
        category="Respiratory Diseases",
        parent_disease=None,
        subtypes=["Progressive Pulmonary Fibrosis"],
        aliases=["IPF", "Progressive Pulmonary Fibrosis"],
        icd10_codes=["J84.1"],
        standard_endpoints=[
            EndpointDefinition(name="FVC", full_name="Forced Vital Capacity", category="efficacy", is_validated=True),
            EndpointDefinition(name="6MWD", full_name="6-Minute Walk Distance", category="efficacy"),
        ],
        prevalence_per_100k=15.0,
        is_rare=True,
    )

    diseases["Eosinophilic Esophagitis"] = DiseaseEntry(
        canonical_name="Eosinophilic Esophagitis",
        category="Respiratory Diseases",
        parent_disease=None,
        subtypes=["Eosinophilic Gastritis/Duodenitis"],
        aliases=["EoE", "Eosinophilic Gastritis/Duodenitis"],
        icd10_codes=["K20.0"],
        standard_endpoints=[
            EndpointDefinition(name="DSQ", full_name="Dysphagia Symptom Questionnaire", category="PRO", is_validated=True),
            EndpointDefinition(name="Eosinophil Count", full_name="Peak Esophageal Eosinophil Count", category="biomarker"),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    diseases["Hypereosinophilic Syndrome"] = DiseaseEntry(
        canonical_name="Hypereosinophilic Syndrome",
        category="Respiratory Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["HES"],
        icd10_codes=["D72.1"],
        standard_endpoints=[
            EndpointDefinition(name="AEC", full_name="Absolute Eosinophil Count", category="biomarker", is_validated=True),
        ],
        prevalence_per_100k=2.0,
        is_rare=True,
    )

    # =========================================================================
    # GASTROINTESTINAL DISEASES
    # =========================================================================

    diseases["Crohn's Disease"] = DiseaseEntry(
        canonical_name="Crohn's Disease",
        category="Gastrointestinal Diseases",
        parent_disease=None,
        subtypes=["Fistulizing Crohn's Disease", "Anti-TNF Failure Crohn's Disease"],
        aliases=["CD", "Crohns Disease", "Crohn's Disease Induction", "Crohn's Disease Maintenance", "Crohns Disease (anti-TNF failure)", "Fistulizing Crohn's"],
        icd10_codes=["K50"],
        standard_endpoints=[
            EndpointDefinition(name="CDAI", full_name="Crohn's Disease Activity Index", category="efficacy", is_validated=True),
            EndpointDefinition(name="SES-CD", full_name="Simple Endoscopic Score for CD", category="efficacy", is_validated=True),
            EndpointDefinition(name="Clinical Remission", full_name="Clinical Remission (CDAI<150)", category="efficacy", is_validated=True),
            EndpointDefinition(name="Endoscopic Response", full_name="Endoscopic Response", category="efficacy"),
        ],
        prevalence_per_100k=200.0,
        is_rare=False,
    )

    diseases["Ulcerative Colitis"] = DiseaseEntry(
        canonical_name="Ulcerative Colitis",
        category="Gastrointestinal Diseases",
        parent_disease=None,
        subtypes=["Pediatric UC"],
        aliases=["UC", "Pediatric UC"],
        icd10_codes=["K51"],
        standard_endpoints=[
            EndpointDefinition(name="Mayo Score", full_name="Mayo Clinic Score", category="efficacy", is_validated=True),
            EndpointDefinition(name="Clinical Remission", full_name="Clinical Remission", category="efficacy", is_validated=True),
            EndpointDefinition(name="Endoscopic Improvement", full_name="Endoscopic Improvement", category="efficacy"),
        ],
        prevalence_per_100k=250.0,
        is_rare=False,
    )

    diseases["Celiac Disease"] = DiseaseEntry(
        canonical_name="Celiac Disease",
        category="Gastrointestinal Diseases",
        parent_disease=None,
        subtypes=["Non-Responsive Celiac Disease", "Refractory Celiac Type II"],
        aliases=["Celiac Disease (NRCD)", "Refractory Celiac Type II"],
        icd10_codes=["K90.0"],
        standard_endpoints=[
            EndpointDefinition(name="Villous Atrophy", full_name="Villous Atrophy Improvement", category="efficacy"),
            EndpointDefinition(name="Symptoms", full_name="Symptom Improvement", category="PRO"),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    diseases["Inflammatory Bowel Disease"] = DiseaseEntry(
        canonical_name="Inflammatory Bowel Disease",
        category="Gastrointestinal Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["IBD"],
        icd10_codes=["K50", "K51"],
        standard_endpoints=[],
        prevalence_per_100k=450.0,
        is_rare=False,
    )

    # =========================================================================
    # NEUROLOGICAL DISEASES
    # =========================================================================

    diseases["Multiple Sclerosis"] = DiseaseEntry(
        canonical_name="Multiple Sclerosis",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=[
            "Relapsing-Remitting MS", "Primary Progressive MS", "Secondary Progressive MS",
            "Clinically Isolated Syndrome"
        ],
        aliases=["MS", "RRMS", "Relapsing MS", "Relapsing Multiple Sclerosis", "Relapsing-Remitting MS",
                 "Primary Progressive MS", "Secondary Progressive MS", "Clinically Isolated Syndrome"],
        icd10_codes=["G35"],
        standard_endpoints=[
            EndpointDefinition(name="ARR", full_name="Annualized Relapse Rate", category="efficacy", is_validated=True),
            EndpointDefinition(name="EDSS", full_name="Expanded Disability Status Scale", category="efficacy", is_validated=True),
            EndpointDefinition(name="MRI Lesions", full_name="New/Enlarging T2 Lesions", category="efficacy"),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    diseases["Neuromyelitis Optica Spectrum Disorder"] = DiseaseEntry(
        canonical_name="Neuromyelitis Optica Spectrum Disorder",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["NMOSD", "NMO", "NMOSD (add-on)", "NMOSD (monotherapy)"],
        icd10_codes=["G36.0"],
        standard_endpoints=[
            EndpointDefinition(name="Relapse Rate", full_name="Annualized Relapse Rate", category="efficacy", is_validated=True),
            EndpointDefinition(name="Time to Relapse", full_name="Time to First Relapse", category="efficacy"),
        ],
        prevalence_per_100k=3.0,
        is_rare=True,
    )

    diseases["Myasthenia Gravis"] = DiseaseEntry(
        canonical_name="Myasthenia Gravis",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=["Generalized Myasthenia Gravis", "Ocular Myasthenia Gravis", "Anti-AChR MG", "Anti-MuSK MG"],
        aliases=["MG", "gMG", "Generalized MG", "Generalized Myasthenia Gravis"],
        icd10_codes=["G70.0"],
        standard_endpoints=[
            EndpointDefinition(name="MG-ADL", full_name="MG Activities of Daily Living", category="PRO", is_validated=True),
            EndpointDefinition(name="QMG", full_name="Quantitative MG Score", category="efficacy", is_validated=True),
            EndpointDefinition(name="MGC", full_name="MG Composite", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=20.0,
        is_rare=True,
    )

    diseases["Chronic Inflammatory Demyelinating Polyneuropathy"] = DiseaseEntry(
        canonical_name="Chronic Inflammatory Demyelinating Polyneuropathy",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["CIDP"],
        icd10_codes=["G61.8"],
        standard_endpoints=[
            EndpointDefinition(name="INCAT", full_name="Inflammatory Neuropathy Cause and Treatment Disability Score", category="efficacy", is_validated=True),
            EndpointDefinition(name="I-RODS", full_name="Inflammatory Rasch-built Overall Disability Scale", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=3.0,
        is_rare=True,
    )

    diseases["Guillain-Barre Syndrome"] = DiseaseEntry(
        canonical_name="Guillain-Barre Syndrome",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["GBS"],
        icd10_codes=["G61.0"],
        standard_endpoints=[
            EndpointDefinition(name="GBS Disability Scale", full_name="GBS Disability Scale", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=2.0,
        is_rare=True,
    )

    diseases["Amyotrophic Lateral Sclerosis"] = DiseaseEntry(
        canonical_name="Amyotrophic Lateral Sclerosis",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["ALS", "Lou Gehrig's disease"],
        icd10_codes=["G12.21"],
        standard_endpoints=[
            EndpointDefinition(name="ALSFRS-R", full_name="ALS Functional Rating Scale Revised", category="efficacy", is_validated=True),
            EndpointDefinition(name="SVC", full_name="Slow Vital Capacity", category="efficacy"),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    diseases["Alzheimer's Disease"] = DiseaseEntry(
        canonical_name="Alzheimer's Disease",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["AD", "Cognitive decline"],
        icd10_codes=["G30"],
        standard_endpoints=[
            EndpointDefinition(name="CDR-SB", full_name="Clinical Dementia Rating Sum of Boxes", category="efficacy", is_validated=True),
            EndpointDefinition(name="ADAS-Cog", full_name="Alzheimer's Disease Assessment Scale-Cognitive", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=1000.0,
        is_rare=False,
    )

    diseases["Huntington's Disease"] = DiseaseEntry(
        canonical_name="Huntington's Disease",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["Huntington Disease", "HD"],
        icd10_codes=["G10"],
        standard_endpoints=[
            EndpointDefinition(name="TFC", full_name="Total Functional Capacity", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    diseases["Duchenne Muscular Dystrophy"] = DiseaseEntry(
        canonical_name="Duchenne Muscular Dystrophy",
        category="Neurological Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["DMD", "Duchenne MD"],
        icd10_codes=["G71.01"],
        standard_endpoints=[
            EndpointDefinition(name="6MWD", full_name="6-Minute Walk Distance", category="efficacy", is_validated=True),
            EndpointDefinition(name="NSAA", full_name="North Star Ambulatory Assessment", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    # =========================================================================
    # HEMATOLOGIC DISEASES
    # =========================================================================

    diseases["Immune Thrombocytopenia"] = DiseaseEntry(
        canonical_name="Immune Thrombocytopenia",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=["Chronic ITP", "First-line ITP", "Second-line ITP"],
        aliases=["ITP", "Chronic ITP", "Immune Thrombocytopenia (1st line)", "Immune Thrombocytopenia (2nd line)"],
        icd10_codes=["D69.3"],
        standard_endpoints=[
            EndpointDefinition(name="Platelet Response", full_name="Platelet Count Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="Durable Response", full_name="Durable Platelet Response", category="efficacy"),
        ],
        prevalence_per_100k=10.0,
        is_rare=True,
    )

    diseases["Cold Agglutinin Disease"] = DiseaseEntry(
        canonical_name="Cold Agglutinin Disease",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["CAD", "Cold Agglutinin Disease (no transfusion)"],
        icd10_codes=["D59.12"],
        standard_endpoints=[
            EndpointDefinition(name="Hemoglobin Response", full_name="Hemoglobin Response", category="efficacy", is_validated=True),
            EndpointDefinition(name="Transfusion-Free", full_name="Transfusion Avoidance", category="efficacy"),
        ],
        prevalence_per_100k=1.0,
        is_rare=True,
    )

    diseases["Warm Autoimmune Hemolytic Anemia"] = DiseaseEntry(
        canonical_name="Warm Autoimmune Hemolytic Anemia",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["wAIHA", "Warm AIHA"],
        icd10_codes=["D59.11"],
        standard_endpoints=[
            EndpointDefinition(name="Hemoglobin Response", full_name="Hemoglobin Response", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=1.0,
        is_rare=True,
    )

    diseases["Paroxysmal Nocturnal Hemoglobinuria"] = DiseaseEntry(
        canonical_name="Paroxysmal Nocturnal Hemoglobinuria",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["PNH", "PNH (monotherapy)", "PNH (treatment-naive)", "PNH (C5i inadequate response)"],
        icd10_codes=["D59.5"],
        standard_endpoints=[
            EndpointDefinition(name="LDH", full_name="Lactate Dehydrogenase", category="biomarker", is_validated=True),
            EndpointDefinition(name="Transfusion Avoidance", full_name="Transfusion Avoidance", category="efficacy"),
            EndpointDefinition(name="Breakthrough Hemolysis", full_name="Breakthrough Hemolysis", category="safety"),
        ],
        prevalence_per_100k=1.0,
        is_rare=True,
    )

    diseases["Atypical Hemolytic Uremic Syndrome"] = DiseaseEntry(
        canonical_name="Atypical Hemolytic Uremic Syndrome",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["aHUS", "Atypical HUS"],
        icd10_codes=["D59.3"],
        standard_endpoints=[
            EndpointDefinition(name="TMA Event-Free", full_name="TMA Event-Free Status", category="efficacy", is_validated=True),
            EndpointDefinition(name="Platelet Normalization", full_name="Platelet Count Normalization", category="efficacy"),
        ],
        prevalence_per_100k=0.5,
        is_rare=True,
    )

    diseases["Myelofibrosis"] = DiseaseEntry(
        canonical_name="Myelofibrosis",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["MF"],
        icd10_codes=["D47.4"],
        standard_endpoints=[
            EndpointDefinition(name="SVR35", full_name="Spleen Volume Reduction ≥35%", category="efficacy", is_validated=True),
            EndpointDefinition(name="TSS50", full_name="Total Symptom Score ≥50% Reduction", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=2.0,
        is_rare=True,
    )

    diseases["Polycythemia Vera"] = DiseaseEntry(
        canonical_name="Polycythemia Vera",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["PV"],
        icd10_codes=["D45"],
        standard_endpoints=[
            EndpointDefinition(name="Hematocrit Control", full_name="Hematocrit Control", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    diseases["Systemic Mastocytosis"] = DiseaseEntry(
        canonical_name="Systemic Mastocytosis",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=["Advanced Systemic Mastocytosis", "Indolent Systemic Mastocytosis", "Non-Advanced SM"],
        aliases=["SM", "Advanced Systemic Mastocytosis", "Indolent Systemic Mastocytosis"],
        icd10_codes=["D47.02"],
        standard_endpoints=[
            EndpointDefinition(name="ORR", full_name="Overall Response Rate", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=1.0,
        is_rare=True,
    )

    diseases["Severe Aplastic Anemia"] = DiseaseEntry(
        canonical_name="Severe Aplastic Anemia",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["SAA"],
        icd10_codes=["D61.9"],
        standard_endpoints=[
            EndpointDefinition(name="Hematologic Response", full_name="Hematologic Response", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=2.0,
        is_rare=True,
    )

    diseases["Sickle Cell Disease"] = DiseaseEntry(
        canonical_name="Sickle Cell Disease",
        category="Hematologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["SCD"],
        icd10_codes=["D57"],
        standard_endpoints=[
            EndpointDefinition(name="VOC Rate", full_name="Vaso-Occlusive Crisis Rate", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=40.0,
        is_rare=False,
    )

    # =========================================================================
    # RENAL DISEASES
    # =========================================================================

    diseases["IgA Nephropathy"] = DiseaseEntry(
        canonical_name="IgA Nephropathy",
        category="Renal Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["IgAN", "Berger's disease"],
        icd10_codes=["N02.8"],
        standard_endpoints=[
            EndpointDefinition(name="Proteinuria", full_name="Proteinuria Reduction", category="efficacy", is_validated=True),
            EndpointDefinition(name="eGFR", full_name="Estimated GFR Slope", category="efficacy"),
        ],
        prevalence_per_100k=25.0,
        is_rare=True,
    )

    diseases["Membranous Nephropathy"] = DiseaseEntry(
        canonical_name="Membranous Nephropathy",
        category="Renal Diseases",
        parent_disease=None,
        subtypes=["Primary Membranous Nephropathy"],
        aliases=["MN", "PMN", "Primary Membranous Nephropathy"],
        icd10_codes=["N04.2"],
        standard_endpoints=[
            EndpointDefinition(name="Complete Remission", full_name="Complete Remission of Proteinuria", category="efficacy", is_validated=True),
            EndpointDefinition(name="PLA2R Antibody", full_name="PLA2R Antibody Response", category="biomarker"),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    diseases["C3 Glomerulopathy"] = DiseaseEntry(
        canonical_name="C3 Glomerulopathy",
        category="Renal Diseases",
        parent_disease=None,
        subtypes=["C3 Glomerulonephritis", "Dense Deposit Disease"],
        aliases=["C3G", "C3 Glomerulopathy/IC-MPGN", "Immune Complex MPGN"],
        icd10_codes=["N05.8"],
        standard_endpoints=[
            EndpointDefinition(name="Proteinuria", full_name="Proteinuria Reduction", category="efficacy"),
            EndpointDefinition(name="eGFR", full_name="eGFR Stabilization", category="efficacy"),
        ],
        prevalence_per_100k=2.0,
        is_rare=True,
    )

    diseases["Diabetic Kidney Disease"] = DiseaseEntry(
        canonical_name="Diabetic Kidney Disease",
        category="Renal Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["DKD", "diabetic nephropathy"],
        icd10_codes=["E11.22"],
        standard_endpoints=[
            EndpointDefinition(name="eGFR Slope", full_name="eGFR Slope", category="efficacy", is_validated=True),
            EndpointDefinition(name="UACR", full_name="Urine Albumin-to-Creatinine Ratio", category="efficacy"),
        ],
        prevalence_per_100k=500.0,
        is_rare=False,
    )

    # =========================================================================
    # VASCULITIS
    # =========================================================================

    diseases["ANCA-Associated Vasculitis"] = DiseaseEntry(
        canonical_name="ANCA-Associated Vasculitis",
        category="Vasculitis",
        parent_disease=None,
        subtypes=[
            "Granulomatosis with Polyangiitis",
            "Microscopic Polyangiitis",
            "Eosinophilic Granulomatosis with Polyangiitis",
        ],
        aliases=["AAV", "ANCA Vasculitis", "ANCA-associated Vasculitis", "GPA", "MPA", "EGPA", "EGPA (Churg-Strauss)"],
        icd10_codes=["M31.3", "M31.7", "M30.1"],
        standard_endpoints=[
            EndpointDefinition(name="BVAS", full_name="Birmingham Vasculitis Activity Score", category="efficacy", is_validated=True),
            EndpointDefinition(name="Remission", full_name="Complete Remission", category="efficacy"),
            EndpointDefinition(name="GC Sparing", full_name="Glucocorticoid Sparing", category="efficacy"),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    diseases["Behcet's Disease"] = DiseaseEntry(
        canonical_name="Behcet's Disease",
        category="Vasculitis",
        parent_disease=None,
        subtypes=[],
        aliases=["Behcet Disease", "BD", "ANCA Vasculitis/Behçet's"],
        icd10_codes=["M35.2"],
        standard_endpoints=[
            EndpointDefinition(name="Oral Ulcer Count", full_name="Oral Ulcer Count", category="efficacy"),
            EndpointDefinition(name="BDCAF", full_name="Behcet's Disease Current Activity Form", category="efficacy"),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    # =========================================================================
    # SJOGREN'S SYNDROME
    # =========================================================================

    diseases["Sjogren's Syndrome"] = DiseaseEntry(
        canonical_name="Sjogren's Syndrome",
        category="Autoimmune Diseases",
        parent_disease=None,
        subtypes=["Primary Sjogren's Syndrome", "Secondary Sjogren's Syndrome"],
        aliases=["SS", "Sjogren's", "Sjogrens", "Sjögren's Syndrome", "Sjögren's Disease", "Sjogren Disease", "Primary Sjogren's Syndrome"],
        icd10_codes=["M35.0"],
        standard_endpoints=[
            EndpointDefinition(name="ESSDAI", full_name="EULAR Sjogren's Syndrome Disease Activity Index", category="efficacy", is_validated=True),
            EndpointDefinition(name="ESSPRI", full_name="EULAR Sjogren's Syndrome Patient Reported Index", category="PRO", is_validated=True),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    # =========================================================================
    # SYSTEMIC SCLEROSIS
    # =========================================================================

    diseases["Systemic Sclerosis"] = DiseaseEntry(
        canonical_name="Systemic Sclerosis",
        category="Autoimmune Diseases",
        parent_disease=None,
        subtypes=["Diffuse Cutaneous SSc", "Limited Cutaneous SSc", "SSc-ILD"],
        aliases=["SSc", "scleroderma", "Systemic Sclerosis ILD", "SSc-ILD", "Diffuse Cutaneous SSc"],
        icd10_codes=["M34"],
        standard_endpoints=[
            EndpointDefinition(name="mRSS", full_name="Modified Rodnan Skin Score", category="efficacy", is_validated=True),
            EndpointDefinition(name="FVC", full_name="Forced Vital Capacity", category="efficacy"),
            EndpointDefinition(name="HAQ-DI", full_name="Health Assessment Questionnaire", category="PRO"),
        ],
        prevalence_per_100k=20.0,
        is_rare=True,
    )

    # =========================================================================
    # AUTOINFLAMMATORY DISEASES
    # =========================================================================

    diseases["Cryopyrin-Associated Periodic Syndromes"] = DiseaseEntry(
        canonical_name="Cryopyrin-Associated Periodic Syndromes",
        category="Autoinflammatory Diseases",
        parent_disease=None,
        subtypes=["FCAS", "MWS", "NOMID"],
        aliases=["CAPS", "CAPS (FCAS/MWS)", "CAPS (MWS/FCAS)", "CAPS/NOMID"],
        icd10_codes=["E85.0"],
        standard_endpoints=[
            EndpointDefinition(name="Disease Flare", full_name="Disease Flare Prevention", category="efficacy"),
            EndpointDefinition(name="CRP/SAA", full_name="CRP/SAA Normalization", category="biomarker"),
        ],
        prevalence_per_100k=0.5,
        is_rare=True,
    )

    diseases["Adult-Onset Still's Disease"] = DiseaseEntry(
        canonical_name="Adult-Onset Still's Disease",
        category="Autoinflammatory Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["AOSD"],
        icd10_codes=["M06.1"],
        standard_endpoints=[
            EndpointDefinition(name="ACR30", full_name="ACR 30% Response", category="efficacy"),
            EndpointDefinition(name="Ferritin", full_name="Ferritin Normalization", category="biomarker"),
        ],
        prevalence_per_100k=1.0,
        is_rare=True,
    )

    diseases["Familial Mediterranean Fever"] = DiseaseEntry(
        canonical_name="Familial Mediterranean Fever",
        category="Autoinflammatory Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["FMF", "TRAPS/HIDS/FMF"],
        icd10_codes=["E85.0"],
        standard_endpoints=[
            EndpointDefinition(name="Attack Frequency", full_name="Attack Frequency Reduction", category="efficacy"),
        ],
        prevalence_per_100k=10.0,
        is_rare=True,
    )

    diseases["DIRA"] = DiseaseEntry(
        canonical_name="DIRA",
        category="Autoinflammatory Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["Deficiency of IL-1 Receptor Antagonist"],
        icd10_codes=["D89.8"],
        standard_endpoints=[],
        prevalence_per_100k=0.1,
        is_rare=True,
    )

    diseases["Recurrent Pericarditis"] = DiseaseEntry(
        canonical_name="Recurrent Pericarditis",
        category="Autoinflammatory Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["RP"],
        icd10_codes=["I30.1"],
        standard_endpoints=[
            EndpointDefinition(name="Recurrence Rate", full_name="Pericarditis Recurrence Rate", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    # =========================================================================
    # OPHTHALMOLOGIC DISEASES
    # =========================================================================

    diseases["Thyroid Eye Disease"] = DiseaseEntry(
        canonical_name="Thyroid Eye Disease",
        category="Ophthalmologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["TED", "Graves ophthalmopathy", "Graves Disease"],
        icd10_codes=["H05.0"],
        standard_endpoints=[
            EndpointDefinition(name="Proptosis", full_name="Proptosis Improvement", category="efficacy", is_validated=True),
            EndpointDefinition(name="CAS", full_name="Clinical Activity Score", category="efficacy"),
        ],
        prevalence_per_100k=20.0,
        is_rare=True,
    )

    diseases["Non-Infectious Uveitis"] = DiseaseEntry(
        canonical_name="Non-Infectious Uveitis",
        category="Ophthalmologic Diseases",
        parent_disease=None,
        subtypes=["Inactive NIU"],
        aliases=["NIU", "uveitis", "Non-Infectious Uveitis (inactive)"],
        icd10_codes=["H20"],
        standard_endpoints=[
            EndpointDefinition(name="Flare Rate", full_name="Uveitis Flare Rate", category="efficacy", is_validated=True),
            EndpointDefinition(name="Visual Acuity", full_name="Best Corrected Visual Acuity", category="efficacy"),
        ],
        prevalence_per_100k=20.0,
        is_rare=True,
    )

    diseases["Dry Eye Disease"] = DiseaseEntry(
        canonical_name="Dry Eye Disease",
        category="Ophthalmologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["DED"],
        icd10_codes=["H04.12"],
        standard_endpoints=[
            EndpointDefinition(name="OSDI", full_name="Ocular Surface Disease Index", category="PRO", is_validated=True),
            EndpointDefinition(name="Schirmer Test", full_name="Schirmer Test", category="efficacy"),
        ],
        prevalence_per_100k=1000.0,
        is_rare=False,
    )

    diseases["Geographic Atrophy"] = DiseaseEntry(
        canonical_name="Geographic Atrophy",
        category="Ophthalmologic Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["GA", "dry AMD"],
        icd10_codes=["H35.31"],
        standard_endpoints=[
            EndpointDefinition(name="GA Lesion Growth", full_name="GA Lesion Growth Rate", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=100.0,
        is_rare=False,
    )

    # =========================================================================
    # TRANSPLANT
    # =========================================================================

    diseases["Graft-versus-Host Disease"] = DiseaseEntry(
        canonical_name="Graft-versus-Host Disease",
        category="Transplant",
        parent_disease=None,
        subtypes=["Acute GVHD", "Chronic GVHD", "Steroid-Refractory GVHD"],
        aliases=["GVHD", "GvHD", "Acute GVHD", "Acute GvHD", "Chronic GVHD", "Chronic GvHD",
                 "Acute Graft-versus-Host Disease", "Acute GI GVHD", "Steroid-refractory aGVHD"],
        icd10_codes=["T86.09"],
        standard_endpoints=[
            EndpointDefinition(name="ORR", full_name="Overall Response Rate", category="efficacy", is_validated=True),
            EndpointDefinition(name="CR", full_name="Complete Response", category="efficacy"),
        ],
        prevalence_per_100k=10.0,
        is_rare=True,
    )

    diseases["Transplant Rejection"] = DiseaseEntry(
        canonical_name="Transplant Rejection",
        category="Transplant",
        parent_disease=None,
        subtypes=["Antibody-Mediated Rejection", "Kidney Transplant Rejection"],
        aliases=["Antibody-Mediated Rejection", "Kidney Transplant Rejection", "Chronic Active AMR", "Late Antibody-Mediated Rejection"],
        icd10_codes=["T86"],
        standard_endpoints=[
            EndpointDefinition(name="Graft Survival", full_name="Graft Survival", category="efficacy"),
            EndpointDefinition(name="DSA Reduction", full_name="Donor-Specific Antibody Reduction", category="biomarker"),
        ],
        prevalence_per_100k=50.0,
        is_rare=False,
    )

    diseases["Transplant-Associated Thrombotic Microangiopathy"] = DiseaseEntry(
        canonical_name="Transplant-Associated Thrombotic Microangiopathy",
        category="Transplant",
        parent_disease=None,
        subtypes=[],
        aliases=[
            "TA-TMA", "TATMA", "TMA",
            "Transplantation-Associated Thrombotic Microangiopathy",
            "Transplant Associated Thrombotic Microangiopathy",
            "Transplantation Associated Thrombotic Microangiopathy",
            "HSCT-TMA", "Stem Cell Transplant TMA",
            "Hematopoietic Stem Cell Transplant TMA",
            "Post-Transplant TMA", "Post Transplant TMA",
        ],
        icd10_codes=["M31.1", "T86.09"],
        standard_endpoints=[
            EndpointDefinition(name="TMA Event-Free", full_name="TMA Event-Free Status", category="efficacy", is_validated=True),
            EndpointDefinition(name="Hematologic Response", full_name="Hematologic Response", category="efficacy"),
            EndpointDefinition(name="LDH Normalization", full_name="LDH Normalization", category="biomarker"),
            EndpointDefinition(name="Platelet Recovery", full_name="Platelet Count Recovery", category="biomarker"),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    # =========================================================================
    # OTHER RARE DISEASES
    # =========================================================================

    diseases["Hereditary Angioedema"] = DiseaseEntry(
        canonical_name="Hereditary Angioedema",
        category="Rare Diseases",
        parent_disease=None,
        subtypes=["HAE Acute Attack", "HAE Prophylaxis"],
        aliases=["HAE", "HAE Acute Attack", "HAE Prophylaxis"],
        icd10_codes=["D84.1"],
        standard_endpoints=[
            EndpointDefinition(name="Attack Rate", full_name="HAE Attack Rate", category="efficacy", is_validated=True),
            EndpointDefinition(name="Time to Resolution", full_name="Time to Attack Resolution", category="efficacy"),
        ],
        prevalence_per_100k=2.0,
        is_rare=True,
    )

    diseases["Type 1 Diabetes"] = DiseaseEntry(
        canonical_name="Type 1 Diabetes",
        category="Metabolic Diseases",
        parent_disease=None,
        subtypes=["New-Onset T1D", "T1D Prevention"],
        aliases=["T1D", "T1D New-Onset", "T1D Prevention"],
        icd10_codes=["E10"],
        standard_endpoints=[
            EndpointDefinition(name="C-peptide", full_name="C-peptide AUC", category="biomarker", is_validated=True),
            EndpointDefinition(name="Insulin Use", full_name="Insulin Use Reduction", category="efficacy"),
        ],
        prevalence_per_100k=200.0,
        is_rare=False,
    )

    diseases["IgG4-Related Disease"] = DiseaseEntry(
        canonical_name="IgG4-Related Disease",
        category="Rare Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=["IgG4-RD"],
        icd10_codes=["D89.82"],
        standard_endpoints=[
            EndpointDefinition(name="Complete Response", full_name="Complete Response", category="efficacy"),
            EndpointDefinition(name="IgG4 Reduction", full_name="Serum IgG4 Reduction", category="biomarker"),
        ],
        prevalence_per_100k=5.0,
        is_rare=True,
    )

    diseases["Castleman Disease"] = DiseaseEntry(
        canonical_name="Castleman Disease",
        category="Rare Diseases",
        parent_disease=None,
        subtypes=["Multicentric Castleman Disease"],
        aliases=["MCD", "Multicentric Castleman Disease"],
        icd10_codes=["D47.Z2"],
        standard_endpoints=[
            EndpointDefinition(name="Durable Response", full_name="Durable Tumor and Symptom Response", category="efficacy", is_validated=True),
        ],
        prevalence_per_100k=1.0,
        is_rare=True,
    )

    # =========================================================================
    # CARDIOVASCULAR
    # =========================================================================

    diseases["Heart Failure"] = DiseaseEntry(
        canonical_name="Heart Failure",
        category="Cardiovascular Diseases",
        parent_disease=None,
        subtypes=["HFrEF", "HFpEF"],
        aliases=["HF"],
        icd10_codes=["I50"],
        standard_endpoints=[
            EndpointDefinition(name="CV Death/HF Hospitalization", full_name="CV Death or HF Hospitalization", category="efficacy", is_validated=True),
            EndpointDefinition(name="NT-proBNP", full_name="NT-proBNP Reduction", category="biomarker"),
        ],
        prevalence_per_100k=2000.0,
        is_rare=False,
    )

    diseases["Myocarditis"] = DiseaseEntry(
        canonical_name="Myocarditis",
        category="Cardiovascular Diseases",
        parent_disease=None,
        subtypes=[],
        aliases=[],
        icd10_codes=["I40"],
        standard_endpoints=[
            EndpointDefinition(name="LVEF", full_name="Left Ventricular Ejection Fraction", category="efficacy"),
        ],
        prevalence_per_100k=10.0,
        is_rare=True,
    )

    # =========================================================================
    # INFECTIONS
    # =========================================================================

    diseases["COVID-19"] = DiseaseEntry(
        canonical_name="COVID-19",
        category="Infectious Diseases",
        parent_disease=None,
        subtypes=["COVID-19 Pneumonia", "COVID-19 ARDS", "Severe COVID-19"],
        aliases=["COVID-19 (ICU)", "COVID-19 ARDS", "COVID-19 Pneumonia", "COVID-19 Pneumonia (Severe)"],
        icd10_codes=["U07.1"],
        standard_endpoints=[
            EndpointDefinition(name="Recovery", full_name="Clinical Recovery", category="efficacy"),
            EndpointDefinition(name="Mortality", full_name="Mortality Rate", category="efficacy"),
        ],
        prevalence_per_100k=5000.0,
        is_rare=False,
    )

    return diseases
