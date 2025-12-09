# Drug Repurposing Agent: Prompt Improvement Recommendations

## Overview

This document consolidates recommended improvements for the drug repurposing case series analysis agent prompts. These changes enhance extraction quality, enable organ domain analysis, improve safety classification, and reduce hallucinations.

---

## 1. `stage2_efficacy.j2` — Add Organ Domain Classification

**Purpose:** Enable organ domain breadth scoring—drugs showing improvement across multiple organ systems are more compelling repurposing candidates.

### Recommended Addition

Add the following fields to each endpoint extraction:

```jinja2
For each endpoint, ALSO classify:
{
    ...existing fields...,
    "organ_domain": "one of: Musculoskeletal | Mucocutaneous | Renal | Neurological | Hematological | Cardiopulmonary | Immunological | Systemic | Gastrointestinal | Ocular | Constitutional",
    "is_validated_instrument": true/false,
    "instrument_quality_tier": 1-3 (1=gold standard like EASI/PASI, 2=validated PRO, 3=investigator-assessed)
}

ORGAN DOMAIN CLASSIFICATION GUIDE:
- Musculoskeletal: Joint counts, ACR responses, DAS28, SPARCC, myositis measures (MMT8, CMAS), bone density
- Mucocutaneous: Skin scores (EASI, PASI, mRODNAN, CDASI), alopecia (SALT), oral ulcers, Raynaud's
- Renal: Proteinuria, eGFR, creatinine, complete/partial renal response, lupus nephritis measures
- Neurological: Cognitive assessments, neuropathy scores, seizure frequency, MS measures (EDSS)
- Hematological: Platelet counts, hemoglobin, WBC, lymphocyte subsets, complement levels
- Cardiopulmonary: Echo findings, PFTs (FVC, DLCO), 6MWD, PAH measures, ILD progression
- Immunological: Autoantibodies, cytokines, interferon signature, B-cell counts
- Systemic: Composite disease activity (SLEDAI, BILAG, PGA), flare rates, remission
- Gastrointestinal: IBD scores (Mayo, CDAI), hepatic enzymes, dysphagia
- Ocular: Uveitis activity, visual acuity, scleritis measures
- Constitutional: Fatigue (FACIT-F), fever, weight, sleep quality

INSTRUMENT QUALITY TIERS:
- Tier 1 (Gold Standard): EASI, PASI, SLEDAI-2K, ACR20/50/70, DAS28, CDASI, SALT, Mayo Score
- Tier 2 (Validated PRO): DLQI, FACIT-F, SF-36, HAQ-DI, patient VAS, PtGA
- Tier 3 (Investigator-Assessed): PGA, clinical response (unvalidated), "improvement" without scale
```

---

## 2. `stage3_safety.j2` — Add MedDRA-Aligned Categories

**Purpose:** Enable structured safety scoring and comparison against known drug class effects.

### Recommended Addition

Replace free-text `event_category` with structured classification:

```jinja2
For each safety event, classify into these MedDRA-aligned categories:

{
    ...existing fields...,
    "category_soc": "Infections | Malignancies | Cardiovascular | Thromboembolic | Hepatotoxicity | Cytopenias | GI Perforation | Hypersensitivity | Neurological | Pulmonary | Renal | Death | Metabolic",
    "infection_type": "Bacterial | Viral | Fungal | Mycobacterial | Opportunistic | Herpes Zoster" or null (only for infections),
    "malignancy_type": "Hematologic | Solid Tumor | NMSC" or null (only for malignancies),
    "cv_type": "MACE | Heart Failure | Arrhythmia" or null (only for cardiovascular),
    "thromboembolic_type": "VTE | DVT | PE | Arterial" or null (only for thromboembolic),
    "is_class_effect": true/false (is this a known effect for this drug class?)
}

CATEGORY CLASSIFICATION GUIDE:
- Infections: Any infection including URI, UTI, pneumonia, sepsis, opportunistic infections, TB, herpes zoster
- Malignancies: Any cancer diagnosis, lymphoma, leukemia, solid tumors, NMSC
- Cardiovascular: MI, stroke, cardiovascular death, heart failure, arrhythmias
- Thromboembolic: DVT, PE, arterial thrombosis, portal vein thrombosis
- Hepatotoxicity: Elevated transaminases, hepatitis, liver failure, drug-induced liver injury
- Cytopenias: Anemia, neutropenia, thrombocytopenia, pancytopenia, lymphopenia
- GI Perforation: Bowel perforation, GI perforation (especially relevant for JAK inhibitors)
- Hypersensitivity: Anaphylaxis, angioedema, severe allergic reactions, drug hypersensitivity
- Neurological: Headache, neuropathy, demyelination, seizures
- Pulmonary: ILD, pneumonitis, respiratory failure (non-infectious)
- Renal: AKI, creatinine elevation, renal failure
- Death: Any death, include cause if known
- Metabolic: Lipid changes, CPK elevation, weight gain

KNOWN CLASS EFFECTS (for is_class_effect):
- JAK inhibitors: Herpes zoster, VTE, MACE, malignancies, cytopenias, lipid elevations
- IL-1 inhibitors: Injection site reactions, infections
- Anti-CD20: Infusion reactions, infections, hypogammaglobulinemia
- TNF inhibitors: Infections, TB reactivation, demyelination, heart failure
```

---

## 3. `main_extraction.j2` — Add Extraction Confidence Scoring

**Purpose:** Flag low-confidence extractions for manual review or re-extraction with full text.

### Recommended Addition

Add at the end of the JSON schema:

```jinja2
Also include:
    "extraction_confidence": {
        "disease_certainty": "High" or "Medium" or "Low",
        "n_patients_certainty": "High" or "Medium" or "Low",
        "efficacy_data_quality": "Complete" or "Partial" or "Sparse",
        "safety_data_quality": "Complete" or "Partial" or "Sparse",
        "data_source": "Abstract only" or "Full text" or "Tables available",
        "limiting_factors": ["list any issues, e.g., 'response rate not explicitly stated', 'safety not reported'"]
    }

CONFIDENCE SCORING GUIDE:
- disease_certainty:
  * High: Disease explicitly named, clearly the focus of treatment
  * Medium: Disease inferable but not explicitly stated, or multiple conditions treated
  * Low: Unclear which condition was treated, vague descriptions

- n_patients_certainty:
  * High: Exact number stated (e.g., "n=15 patients", "a case series of 8 patients")
  * Medium: Range given or approximate (e.g., "approximately 20", "15-20 patients")
  * Low: Not stated or unclear (e.g., "several patients", "a few cases")

- efficacy_data_quality:
  * Complete: Primary endpoint with quantitative results, response rates, statistical measures
  * Partial: Some outcomes reported but missing key data (e.g., no denominators, no timepoints)
  * Sparse: Only qualitative descriptions ("improved", "responded well")

- safety_data_quality:
  * Complete: Systematic AE reporting with counts/percentages
  * Partial: Some AEs mentioned but not systematically collected
  * Sparse: Safety not reported or only "well tolerated" statement
```

---

## 4. `filter_papers.j2` — Add Chain-of-Thought Reasoning

**Purpose:** Improve include/exclude accuracy by requiring explicit reasoning for each criterion.

### Recommended Addition

Add before the JSON output section:

```jinja2
For EACH paper, systematically evaluate these criteria:

INCLUSION CRITERIA (all must be YES to include):
1. PATIENT COUNT: Does it mention a specific number of patients treated?
   - YES: "n=5", "15 patients received", "a 42-year-old woman"
   - NO: "patients were treated", no specific count mentioned

2. CLINICAL OUTCOMES: Does it report efficacy/outcome data?
   - YES: Response rates, remission, improvement scores, disease activity changes
   - NO: Only describes treatment protocol, only pharmacokinetics

3. OFF-LABEL USE: Is this about a non-approved indication?
   - YES: Disease is NOT in the approved indications list
   - NO: Disease is an approved indication ({{ exclude_indications }})

4. ORIGINAL DATA: Is this original patient data (not a review)?
   - YES: Case report, case series, retrospective study, cohort study
   - NO: Review article, meta-analysis, guidelines, editorial

DECISION: Include ONLY if criteria 1-4 are ALL answered YES.

For each paper, provide your reasoning in the "reason" field, referencing which criteria were met or failed.
```

---

## 5. `extract_epidemiology.j2` — Add Source Quality Ranking

**Purpose:** Distinguish between high-quality epidemiological sources and estimates.

### Recommended Addition

Expand the JSON schema:

```jinja2
Return ONLY valid JSON:
{
    "us_prevalence_estimate": "estimated US prevalence (e.g. '1 in 10,000' or '200,000 patients') or null",
    "us_incidence_estimate": "annual incidence estimate or null",
    "patient_population_size": integer estimate of US patient count (MUST be integer, not string),
    "prevalence_source": "name of source (e.g. 'NIH GARD', 'CDC', journal name) or null",
    "prevalence_source_url": "URL of the source or null",
    "trend": "increasing/stable/decreasing or null",
    "source_quality": "Primary" or "Secondary" or "Estimate",
    "data_year": year the prevalence data is from (integer) or null,
    "geographic_scope": "US" or "Global" or "Regional",
    "confidence": "High" or "Medium" or "Low",
    "notes": "any caveats about the estimate (e.g., 'extrapolated from European data', 'wide range reported')"
}

SOURCE QUALITY CLASSIFICATION:
- Primary: CDC, NIH GARD, peer-reviewed epidemiology studies, national registries, NCHS
- Secondary: Disease foundations (Lupus Foundation, NAF), review articles, UpToDate
- Estimate: Calculated from related data, expert opinion, extrapolated from other populations

CONFIDENCE SCORING:
- High: Multiple concordant sources, recent data (within 5 years), US-specific data
- Medium: Single credible source, older data (5-10 years), extrapolated from similar populations
- Low: Only estimates available, conflicting sources, data >10 years old, significant uncertainty
```

---

## 6. `standardize_diseases.j2` — Add Explicit Mapping Hints

**Purpose:** Reduce inconsistency in disease name standardization with explicit mapping rules.

### Recommended Addition

Add after the existing rules:

```jinja2
COMMON ABBREVIATION MAPPINGS:
- "AA", "alopecia", "patchy alopecia", "alopecia totalis", "alopecia universalis" → "Alopecia Areata"
- "AD", "eczema", "atopic eczema", "atopic dermatitis" → "Atopic Dermatitis"
- "DM", "dermatomyositis", "adult dermatomyositis" → "Dermatomyositis"
- "JDM", "juvenile dermatomyositis" → "Juvenile Dermatomyositis"
- "PM", "polymyositis" → "Polymyositis"
- "IIM", "IIMs", "inflammatory myopathy", "inflammatory myopathies" → "Inflammatory Myopathies"
- "ASM", "anti-synthetase", "antisynthetase syndrome" → "Antisynthetase Syndrome"
- "GvHD", "GVHD", "graft versus host", "graft-versus-host" → "Graft-versus-Host Disease"
- "cGVHD", "chronic GVHD", "chronic graft-versus-host" → "Chronic Graft-versus-Host Disease"
- "LN", "lupus nephritis", "lupus kidney" → "Lupus Nephritis"
- "SLE", "lupus", "systemic lupus" (without nephritis) → "Systemic Lupus Erythematosus"
- "CLE", "cutaneous lupus", "discoid lupus", "SCLE", "DLE" → "Cutaneous Lupus Erythematosus"
- "SSc", "PSS", "scleroderma", "systemic sclerosis", "CREST" → "Systemic Sclerosis"
- "RA", "rheumatoid" → "Rheumatoid Arthritis"
- "PsA", "psoriatic arthritis" → "Psoriatic Arthritis"
- "axSpA", "ankylosing spondylitis", "AS", "axial spondyloarthritis" → "Axial Spondyloarthritis"
- "IBD" → keep as "Inflammatory Bowel Disease" unless UC or CD specified
- "UC", "ulcerative colitis" → "Ulcerative Colitis"
- "CD", "Crohn's", "Crohn disease" → "Crohn's Disease"
- "AOSD", "adult Still's", "adult-onset Still's" → "Adult-onset Still's Disease"
- "sJIA", "systemic JIA" → "Systemic Juvenile Idiopathic Arthritis"
- "MAS", "macrophage activation" → "Macrophage Activation Syndrome"
- "HLH", "hemophagocytic" → "Hemophagocytic Lymphohistiocytosis"
- "HS", "hidradenitis", "acne inversa" → "Hidradenitis Suppurativa"
- "LP", "lichen planus" → "Lichen Planus"
- "PG", "pyoderma gangrenosum" → "Pyoderma Gangrenosum"

TYPE I INTERFERONOPATHY GROUPINGS:
- "CANDLE", "PRAAS", "proteasome-associated" → "Type I Interferonopathies (CANDLE)"
- "SAVI", "STING-associated" → "Type I Interferonopathies (SAVI)"
- "AGS", "Aicardi-Goutières" → "Type I Interferonopathies (AGS)"

KEEP DISTINCT (do not merge):
- "Vitiligo" - keep separate
- "Psoriasis" - keep separate from PsA
- "Lichen Planus" - keep separate
- "Morphea" - keep separate from SSc (localized vs systemic)
```

---

## 7. `json_rules.j2` — Strengthen JSON Enforcement

**Purpose:** Reduce parsing errors and improve output consistency.

### Recommended Replacement

Replace the current minimal rules with:

```jinja2
CRITICAL JSON RULES - FOLLOW EXACTLY:

1. OUTPUT FORMAT:
   - Return ONLY valid JSON
   - No markdown code fences (```)
   - No explanatory text before or after the JSON
   - No comments within the JSON

2. NULL VALUES:
   - Use null for missing/unknown values
   - Do NOT use empty strings (""), "N/A", "unknown", or "not reported"
   - Example: "response_rate": null (NOT "response_rate": "")

3. DATA TYPES:
   - Numbers must be numbers: 5 (NOT "5")
   - Percentages as numbers: 80.0 (NOT "80%" or "80.0%")
   - Booleans as true/false: true (NOT "true" or "True")
   - Integers where specified: 15 (NOT 15.0)

4. STRING ESCAPING:
   - Escape quotes within strings: "He said \"hello\""
   - Escape backslashes: "path\\to\\file"
   - No unescaped newlines in string values

5. ARRAY FORMATTING:
   - No trailing commas: ["a", "b"] (NOT ["a", "b",])
   - Empty arrays as []: "adverse_events": []

6. EXTRACTION PRINCIPLES:
   - Extract only what is explicitly stated
   - If a value is not clearly stated, use null
   - Do not infer or calculate values unless specifically instructed
   - When uncertain between two values, prefer null over guessing
```

---

## 8. `stage1_sections.j2` — Add Table Detection Patterns

**Purpose:** Improve table identification accuracy by providing common patterns.

### Recommended Addition

Add after the identification instructions:

```jinja2
COMMON TABLE/FIGURE PATTERNS TO LOOK FOR:

BASELINE/DEMOGRAPHICS (usually Table 1):
- Headers containing: "Baseline", "Demographics", "Characteristics", "Patient characteristics"
- Columns like: Age, Sex, Disease duration, Prior treatments, Baseline disease activity

EFFICACY TABLES (usually Table 2-3):
- Headers containing: "Efficacy", "Outcomes", "Response", "Results", "Clinical outcomes"
- Columns like: Baseline, Week X, Change, % Change, Responders
- Row labels with: Response rates, Disease scores (EASI, PASI, SLEDAI), Remission

SAFETY TABLES (often Table 3-4 or supplementary):
- Headers containing: "Safety", "Adverse Events", "AEs", "Tolerability"
- Columns like: n (%), Events, Related, Serious
- Row labels with: Any AE, Serious AE, Infections, specific event names

EFFICACY FIGURES:
- Kaplan-Meier curves (time to response, duration of response)
- Waterfall plots (individual patient responses)
- Spider plots (disease activity over time)
- Bar charts comparing response rates
- Line graphs showing score changes over time

SUPPLEMENTARY MATERIALS:
- "Supplementary Table S1" often contains detailed AE data
- "Extended Data" may have individual patient data
- "Online supplement" may have additional efficacy endpoints
```

---

## 9. `calculate_tam.j2` — Add Therapeutic Area Benchmarks

**Purpose:** Improve TAM estimates with therapy area-specific context.

### Recommended Addition

Add to the calculation framework:

```jinja2
THERAPEUTIC AREA BENCHMARKS:

AUTOIMMUNE - DERMATOLOGY (Atopic Dermatitis, Psoriasis, Alopecia Areata):
- Pricing: $30-60K/year
- Market penetration: 60-80% of moderate-severe patients
- Treatment duration: Chronic, high compliance
- Reference launches:
  * Dupixent (AD): ~$37K/yr, achieved ~40% market share in moderate-severe
  * Rinvoq (AD): ~$60K/yr, capturing share with oral convenience
  * Skyrizi (Psoriasis): ~$60K/yr, rapid uptake with superior efficacy

AUTOIMMUNE - RHEUMATOLOGY (RA, PsA, axSpA):
- Pricing: $50-80K/year
- Market penetration: 50-70% of biologic-eligible patients
- Treatment duration: Chronic
- Reference launches:
  * Rinvoq (RA): ~$60K/yr, competing with established biologics
  * Taltz (PsA): ~$65K/yr

RARE AUTOIMMUNE (Dermatomyositis, Scleroderma, Vasculitis):
- Pricing: $80-200K/year (orphan eligible)
- Market penetration: 30-50% of diagnosed patients
- Lower diagnosis rates
- Reference: Specialty drugs in similar rare diseases

ULTRA-RARE (<5,000 US patients):
- Pricing: $200-500K/year
- Market penetration: 40-60% of diagnosed (strong unmet need)
- Orphan drug exclusivity benefits

LUPUS (SLE, Lupus Nephritis):
- Pricing: $40-80K/year
- Complex market with multiple lines of therapy
- Market penetration: 40-60%
- Reference launches:
  * Saphnelo (SLE): ~$60K/yr, slow uptake in crowded market
  * Lupkynis (LN): ~$75K/yr, narrow indication

TREATMENT FUNNEL DEFAULTS (if not specified):
- Diagnosis rate: 60-80% for common diseases, 30-50% for rare
- Treatment rate: 50-70% of diagnosed receive systemic treatment
- 2L reach: 25-40% of treated patients fail 1L
- 3L reach: 10-20% of treated patients fail 2L
- New drug peak share: 15-30% in crowded market, 30-50% in underserved

CALCULATION TEMPLATE:
TAM = (Patient population) × (Diagnosis rate) × (Treatment rate) × (Target LOT reach) × (Market share) × (Annual price)

Example for rare autoimmune (10,000 US patients):
= 10,000 × 0.70 × 0.60 × 0.35 × 0.30 × $100,000
= 10,000 × 0.0441 × $100,000 = $44.1M
```

---

## Implementation Priority

| Priority | Prompt | Change Summary |
|----------|--------|----------------|
| 🔴 High | `stage2_efficacy.j2` | Organ domain + instrument quality |
| 🔴 High | `stage3_safety.j2` | MedDRA-aligned categories |
| 🔴 High | `main_extraction.j2` | Extraction confidence scores |
| 🟡 Medium | `filter_papers.j2` | Chain-of-thought reasoning |
| 🟡 Medium | `extract_epidemiology.j2` | Source quality ranking |
| 🟡 Medium | `standardize_diseases.j2` | Explicit mapping hints |
| 🟡 Medium | `json_rules.j2` | Strengthened JSON enforcement |
| 🟢 Lower | `stage1_sections.j2` | Table detection patterns |
| 🟢 Lower | `calculate_tam.j2` | Therapy area benchmarks |

---

## Notes

These recommendations are designed to be additive—they extend existing prompts rather than replacing them entirely. Each section shows the recommended additions that should be inserted into the appropriate location within each prompt file.

After implementing these changes, the downstream scoring functions in the Python code should be updated to leverage the new structured fields (organ_domain, category_soc, extraction_confidence, etc.).
