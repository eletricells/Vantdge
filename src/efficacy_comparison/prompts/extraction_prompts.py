"""
Extraction prompts for comprehensive efficacy data extraction.

These prompts are designed to extract all data needed for efficacy comparison tables,
similar to manually curated competitive landscape tables.
"""

from typing import List, Optional


# =============================================================================
# SYSTEM PROMPTS
# =============================================================================

TRIAL_METADATA_SYSTEM_PROMPT = """You are an expert clinical data extractor specializing in pharmaceutical clinical trials.
Your task is to extract trial metadata from clinical trial publications.

EXTRACTION RULES:
1. Extract ONLY data explicitly stated in the source - NEVER infer or estimate
2. If data is not found, use null - do not guess
3. For numerical values, extract the exact numbers as stated
4. Preserve the original terminology used in the source
5. Return valid JSON only - no markdown, no comments

CRITICAL FOR CROSS-TRIAL COMPARISON:
- Patient population type is ESSENTIAL (csDMARD-IR vs bDMARD-IR have very different response rates)
- Concomitant/background therapy requirements affect outcomes
- Prior treatment failure requirements define the patient population

You are extracting data for efficacy comparison tables used in competitive landscape analysis."""

BASELINE_SYSTEM_PROMPT = """You are an expert clinical data extractor specializing in patient baseline characteristics.
Your task is to extract baseline/demographic data from clinical trial publications.

EXTRACTION RULES:
1. Extract ONLY data explicitly stated in the source - NEVER infer or calculate
2. Extract data SEPARATELY for each treatment arm
3. If data is not found for an arm, use null - do not copy from other arms
4. For percentages, extract as decimal (e.g., 65% = 0.65)
5. Preserve exact score names as used in the source (e.g., "EASI", "IGA", "SLEDAI-2K", "DAS28-CRP")
6. Return valid JSON only

CRITICAL FOR RHEUMATOID ARTHRITIS AND AUTOIMMUNE DISEASES:
- Serology status (RF+, anti-CCP+) is critical for RA - seropositive patients respond differently
- Inflammatory markers (CRP, ESR) indicate disease activity
- Number of prior biologic failures defines the population
- Concomitant MTX use and dose affects outcomes
- Steroid use at baseline affects outcomes

You are extracting data for efficacy comparison tables."""

EFFICACY_SYSTEM_PROMPT = """You are an expert clinical data extractor specializing in efficacy endpoints.
Your task is to extract ALL efficacy endpoints from clinical trial publications.

EXTRACTION RULES:
1. Extract EVERY efficacy endpoint mentioned - primary, secondary, exploratory, and PROs
2. Extract data at EVERY timepoint reported (Week 4, Week 8, Week 12, Week 16, etc.)
3. Extract SEPARATELY for each treatment arm
4. For response rates: extract both n (responders) and percentage
5. For continuous endpoints: extract mean/median, change from baseline, and statistical measures
6. Extract p-values exactly as stated (e.g., "<0.001", "0.03", "NS")
7. If data is not explicitly stated, use null - NEVER calculate or infer
8. Return valid JSON only

You are extracting data for comprehensive efficacy comparison tables."""


# =============================================================================
# PROMPT TEMPLATES
# =============================================================================

def build_trial_metadata_prompt(
    content: str,
    drug_name: str,
    trial_name: Optional[str] = None,
    indication: Optional[str] = None,
) -> str:
    """
    Build prompt for extracting trial metadata.

    Extracts:
    - Trial name, NCT ID, phase
    - Patient population (CRITICAL for cross-trial comparison)
    - Treatment arms with dosing
    - Sample sizes per arm
    - Background/concomitant therapy
    """
    return f"""Extract trial metadata from the following clinical trial publication.

DRUG: {drug_name}
TRIAL NAME: {trial_name or "Unknown"}
INDICATION: {indication or "Unknown"}

SOURCE CONTENT:
{content}

---

Extract the following information and return as JSON:

{{
    "trial_name": "Trial acronym/name (e.g., TULIP-2, SOLO-1, RA-BEAM)",
    "nct_id": "NCT ID if mentioned (e.g., NCT02446899)",
    "phase": "Trial phase (e.g., Phase 3, Phase 2)",
    "total_enrollment": "Total number of patients enrolled (integer)",

    "patient_population": "Patient population type - CRITICAL field. Use one of: csDMARD-IR, bDMARD-IR, TNF-IR, MTX-IR, MTX-naive, DMARD-naive, biologic-naive, biologic-IR, anti-TNF-naive, anti-TNF-IR, treatment-naive, treatment-experienced, refractory, or other",
    "patient_population_description": "Full description of patient population from inclusion criteria (e.g., 'Patients with inadequate response to ≥1 csDMARD including methotrexate')",
    "line_of_therapy": "Line of therapy as integer (1 for first-line, 2 for second-line, 3 for third-line+, null if unclear)",

    "prior_treatment_failures_required": "Minimum number of prior treatment failures required (integer or null)",
    "prior_treatment_failures_description": "Description of required prior treatment failures (e.g., '≥1 TNF inhibitor', '≥1 bDMARD')",

    "disease_subtype": "Disease subtype if specified (e.g., 'seropositive', 'seronegative', 'moderate-to-severe')",
    "disease_activity_requirement": "Disease activity requirement for enrollment (e.g., 'DAS28-CRP ≥3.2', 'EASI ≥16')",

    "arms": [
        {{
            "name": "Arm name as described (e.g., 'Baricitinib 4mg QD', 'Placebo')",
            "n": "Number of patients in this arm (integer)",
            "is_active": "true if active treatment, false if placebo/control",
            "dose": "Dose amount (e.g., '4mg', '200mg')",
            "frequency": "Dosing frequency (e.g., 'QD', 'Q2W', 'BID')",
            "route": "Route of administration (e.g., 'oral', 'subcutaneous')"
        }}
    ],

    "background_therapy": "Background therapy allowed/required (e.g., 'methotrexate', 'TCS')",
    "background_therapy_required": "true if background therapy was required, false otherwise",

    "concomitant_therapies": [
        {{
            "therapy_name": "Name of concomitant therapy (e.g., 'methotrexate', 'corticosteroids')",
            "is_required": "true if required for all patients",
            "is_allowed": "true if allowed but not required",
            "dose_requirement": "Dose requirement if specified (e.g., '≥15mg/week for MTX')"
        }}
    ],

    "rescue_therapy_allowed": "true if rescue therapy was allowed, false otherwise",
    "rescue_therapy_description": "Description of rescue therapy if allowed",

    "primary_endpoint": "Primary endpoint name",
    "primary_endpoint_timepoint": "Timepoint for primary endpoint (e.g., 'Week 16')",

    "study_duration": "Total study duration (e.g., '52 weeks', '16 weeks')"
}}

PATIENT POPULATION CLASSIFICATION GUIDE:
- csDMARD-IR: Failed conventional synthetic DMARDs (MTX, sulfasalazine, etc.) but biologic-naive
- bDMARD-IR: Failed ≥1 biologic DMARD (more refractory population, expect lower response rates)
- TNF-IR: Specifically failed TNF inhibitors
- MTX-IR: Failed methotrexate specifically
- MTX-naive: Never received methotrexate (treatment-naive for RA)
- biologic-naive: Never received any biologic (for IBD, dermatology)
- biologic-IR: Failed ≥1 biologic (for IBD, dermatology)

Return ONLY the JSON object, no other text."""


def build_baseline_extraction_prompt(
    content: str,
    drug_name: str,
    arms: List[str],
    indication: Optional[str] = None,
) -> str:
    """
    Build prompt for extracting baseline characteristics.

    Extracts:
    - Demographics (age, sex, race, weight/BMI)
    - Disease characteristics (duration, severity scores)
    - Serology status (RF, anti-CCP, ANA)
    - Inflammatory markers (CRP, ESR)
    - Prior treatments and failures
    - Concomitant therapy at baseline
    """
    arms_list = ", ".join([f'"{arm}"' for arm in arms])

    return f"""Extract baseline characteristics from the following clinical trial publication.

DRUG: {drug_name}
INDICATION: {indication or "Unknown"}
TREATMENT ARMS: {arms_list}

SOURCE CONTENT:
{content}

---

For EACH treatment arm, extract baseline characteristics.

Return JSON in this format:

{{
    "baseline_by_arm": [
        {{
            "arm_name": "Exact arm name",
            "n": "Number of patients in arm (integer)",

            "demographics": {{
                "age_mean": "Mean age in years (number or null)",
                "age_median": "Median age in years (number or null)",
                "age_sd": "Standard deviation (number or null)",
                "age_range_min": "Minimum age (number or null)",
                "age_range_max": "Maximum age (number or null)",
                "male_pct": "Percentage male as decimal (e.g., 0.45 for 45%)",
                "female_pct": "Percentage female as decimal",
                "weight_mean": "Mean weight in kg (number or null)",
                "bmi_mean": "Mean BMI (number or null)"
            }},

            "race": {{
                "white": "Percentage as decimal or null",
                "black": "Percentage as decimal or null",
                "asian": "Percentage as decimal or null",
                "hispanic": "Percentage as decimal or null",
                "other": "Percentage as decimal or null"
            }},

            "disease_characteristics": {{
                "disease_duration_mean": "Mean disease duration (number or null)",
                "disease_duration_median": "Median disease duration (number or null)",
                "disease_duration_unit": "years or months"
            }},

            "severity_scores": [
                {{
                    "name": "Score name exactly as stated (e.g., 'EASI', 'DAS28-CRP', 'CDAI', 'HAQ-DI', 'SLEDAI-2K')",
                    "mean": "Mean value (number or null)",
                    "median": "Median value (number or null)",
                    "sd": "Standard deviation (number or null)",
                    "distribution": "For categorical scores like IGA: {{'score_2': 0.20, 'score_3': 0.65, 'score_4': 0.15}}"
                }}
            ],

            "serology": {{
                "rf_positive_pct": "Rheumatoid factor positive percentage as decimal (for RA)",
                "anti_ccp_positive_pct": "Anti-CCP antibody positive percentage as decimal (for RA)",
                "seropositive_pct": "Either RF+ or anti-CCP+ percentage (often reported combined)",
                "ana_positive_pct": "ANA positive percentage (for SLE)",
                "anti_dsdna_positive_pct": "Anti-dsDNA positive percentage (for SLE)"
            }},

            "inflammatory_markers": {{
                "crp_mean": "Mean C-reactive protein in mg/L (number or null)",
                "crp_median": "Median CRP (number or null)",
                "esr_mean": "Mean erythrocyte sedimentation rate in mm/hr (number or null)"
            }},

            "prior_treatments": {{
                "prior_systemic_pct": "Percentage with prior systemic treatment",
                "prior_biologic_pct": "Percentage with prior biologic treatment",
                "prior_topical_pct": "Percentage with prior topical treatment",
                "prior_biologic_failures_mean": "Mean number of prior biologic failures (for bDMARD-IR populations)",
                "prior_dmard_failures_mean": "Mean number of prior DMARD failures",
                "details": [
                    {{"treatment": "Treatment name (e.g., 'methotrexate', 'adalimumab')", "pct": "Percentage as decimal"}}
                ]
            }},

            "concomitant_therapy_at_baseline": {{
                "on_mtx_pct": "Percentage on methotrexate at baseline",
                "mtx_dose_mean": "Mean MTX dose in mg/week (number or null)",
                "on_steroids_pct": "Percentage on corticosteroids at baseline",
                "steroid_dose_mean": "Mean prednisone equivalent dose in mg/day (number or null)"
            }},

            "source_table": "Source table reference (e.g., 'Table 1')"
        }}
    ]
}}

IMPORTANT:
- Extract data SEPARATELY for each arm - do not combine arms
- Use null for any data not explicitly stated
- Percentages should be decimals (65% = 0.65)
- Extract ALL severity scores mentioned

DISEASE-SPECIFIC SCORES TO LOOK FOR:
- Rheumatoid Arthritis: DAS28-CRP, DAS28-ESR, CDAI, SDAI, HAQ-DI, TJC, SJC
- Atopic Dermatitis: EASI, IGA, BSA, SCORAD, DLQI, POEM, Pruritus NRS
- Psoriasis: PASI, IGA, BSA, DLQI
- SLE: SLEDAI-2K, BILAG, PGA, CLASI
- IBD: Mayo score, CDAI (Crohn's), HBI, SES-CD

Return ONLY the JSON object."""


def build_efficacy_extraction_prompt(
    content: str,
    drug_name: str,
    arms: List[str],
    indication: Optional[str] = None,
    expected_endpoints: Optional[List[str]] = None,
) -> str:
    """
    Build prompt for extracting ALL efficacy endpoints.

    Extracts:
    - Primary endpoints
    - Secondary endpoints
    - PROs (patient-reported outcomes)
    - Biomarkers
    - At ALL timepoints
    """
    arms_list = ", ".join([f'"{arm}"' for arm in arms])

    expected_section = ""
    if expected_endpoints:
        endpoints_list = ", ".join(expected_endpoints)
        expected_section = f"""
EXPECTED ENDPOINTS FOR {indication}:
Look specifically for these endpoints (but also extract any others found):
{endpoints_list}
"""

    return f"""Extract ALL efficacy endpoints from the following clinical trial publication.

DRUG: {drug_name}
INDICATION: {indication or "Unknown"}
TREATMENT ARMS: {arms_list}
{expected_section}

SOURCE CONTENT:
{content}

---

Extract EVERY efficacy endpoint at EVERY timepoint for EACH treatment arm.

Return JSON in this format:

{{
    "endpoints": [
        {{
            "endpoint_name_raw": "Endpoint name exactly as stated in source",
            "endpoint_category": "Primary | Secondary | Exploratory | PRO | Biomarker",
            "arm_name": "Treatment arm name",
            "timepoint": "Timepoint (e.g., 'Week 16', 'Week 52', 'Day 85')",
            "timepoint_weeks": "Timepoint converted to weeks (number)",

            "n_evaluated": "Number of patients evaluated for this endpoint (integer or null)",

            "responders_n": "For binary/responder endpoints: number of responders (integer or null)",
            "responders_pct": "Percentage of responders as decimal (0.75 for 75%)",

            "mean_value": "For continuous endpoints: mean value (number or null)",
            "median_value": "Median value (number or null)",
            "change_from_baseline": "Change from baseline (number or null)",
            "change_from_baseline_pct": "Percent change from baseline as decimal (number or null)",

            "se": "Standard error (number or null)",
            "sd": "Standard deviation (number or null)",
            "ci_lower": "95% CI lower bound (number or null)",
            "ci_upper": "95% CI upper bound (number or null)",

            "vs_comparator": "Comparator arm name for statistical comparison",
            "p_value": "P-value exactly as stated (e.g., '<0.001', '0.03', 'NS')",
            "is_statistically_significant": "true if statistically significant, false if not, null if unclear",

            "source_table": "Table or figure reference (e.g., 'Table 2', 'Figure 1')",
            "source_text": "Brief exact quote from source supporting this data point"
        }}
    ]
}}

ENDPOINT EXTRACTION GUIDELINES:

1. RESPONDER/BINARY ENDPOINTS (extract responders_n and responders_pct):

   RHEUMATOID ARTHRITIS:
   - ACR20, ACR50, ACR70, ACR90 (American College of Rheumatology response criteria)
   - DAS28-CRP remission (<2.6), DAS28-CRP low disease activity (≤3.2)
   - DAS28-ESR remission (<2.6), DAS28-ESR low disease activity (≤3.2)
   - CDAI remission (≤2.8), CDAI low disease activity (≤10)
   - SDAI remission (≤3.3), SDAI low disease activity (≤11)
   - Boolean remission (TJC≤1, SJC≤1, CRP≤1, PGA≤1)
   - HAQ-DI improvement ≥0.22 or ≥0.3 (MCID)
   - Structural progression (mTSS, erosion score)

   ATOPIC DERMATITIS:
   - IGA 0/1, IGA response, IGA success
   - EASI-50, EASI-75, EASI-90, EASI-100
   - Pruritus NRS improvement ≥4 points
   - DLQI 0/1

   PSORIASIS:
   - PASI-50, PASI-75, PASI-90, PASI-100
   - IGA 0/1
   - BSA clear or almost clear

   SLE:
   - SRI-4, SRI-5, SRI-6, SRI-7, SRI-8 (SLE Responder Index)
   - BICLA response
   - LLDAS (Lupus Low Disease Activity State)
   - Flare-free proportion

   IBD:
   - Clinical remission, Clinical response
   - Endoscopic remission, Endoscopic improvement
   - Mucosal healing

2. CONTINUOUS ENDPOINTS (extract mean_value, change_from_baseline):

   RHEUMATOID ARTHRITIS:
   - Mean/LSM change in DAS28-CRP or DAS28-ESR
   - Mean/LSM change in CDAI
   - Mean/LSM change in SDAI
   - Mean/LSM change in HAQ-DI
   - Change in TJC (tender joint count)
   - Change in SJC (swollen joint count)
   - Change in CRP, ESR
   - mTSS change (structural)

   OTHER DISEASES:
   - Mean change in EASI
   - Mean change in DLQI
   - Mean change in POEM
   - Mean change in pruritus NRS
   - Percent change in BSA
   - Mean change in SLEDAI-2K
   - LSM change from baseline

3. TIMEPOINTS - Extract at ALL reported timepoints:
   - Week 2, Week 4, Week 8, Week 12, Week 16, Week 24, Week 52, etc.
   - Create separate entries for each timepoint
   - RA trials often report at Week 12, Week 24, Week 52

4. STATISTICAL DATA:
   - Extract p-values exactly as stated
   - Extract confidence intervals when available
   - Note the comparator arm for statistical tests

IMPORTANT:
- Extract EVERY endpoint found, not just primary
- Create separate entries for each arm x endpoint x timepoint combination
- Use null for missing data - NEVER calculate or infer
- Percentages as decimals (75% = 0.75)

Return ONLY the JSON object."""


# =============================================================================
# ENDPOINT DISCOVERY PROMPT
# =============================================================================

def build_endpoint_discovery_prompt(
    endpoint_name: str,
    indication: str,
    context: Optional[str] = None,
) -> str:
    """
    Build prompt for classifying a newly discovered endpoint.

    Used when an endpoint is not in the library and needs classification.
    """
    return f"""Classify the following clinical endpoint for the endpoint library.

ENDPOINT NAME: {endpoint_name}
INDICATION/DISEASE: {indication}
CONTEXT: {context or "Not provided"}

---

Provide classification for this endpoint:

{{
    "endpoint_name_canonical": "Standardized name (e.g., 'EASI-75', 'IGA 0/1')",
    "endpoint_name_full": "Full description (e.g., '75% improvement in EASI score from baseline')",
    "aliases": ["List of alternative names/spellings"],

    "endpoint_type": "efficacy | safety | PRO | biomarker",
    "endpoint_category_typical": "Primary | Secondary | Exploratory",
    "measurement_type": "responder | continuous | time_to_event | count",

    "direction": "higher_better | lower_better | reduction",
    "typical_timepoints": ["Week 12", "Week 16", "Week 52"],
    "response_threshold": "Threshold for responder definition (e.g., '75% improvement')",

    "is_validated": true/false,
    "regulatory_acceptance": "FDA | EMA | both | none",
    "quality_tier": 1-3 (1=gold standard, 2=validated PRO, 3=exploratory),

    "organ_domain": "Skin | Joint | Renal | Systemic | etc.",

    "reasoning": "Brief explanation of classification"
}}

Return ONLY the JSON object."""
