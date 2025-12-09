# Case Study Analysis v2 - Full Analysis Workflow

**Date:** December 8, 2025

---

## What's New in v3 (December 2025)

This version represents a major methodological upgrade focused on **clinical rigor** and **scoring accuracy**:

### 🔬 Enhanced Clinical Data Extraction
- **Multi-Stage Extraction for Full-Text Papers**: 3-stage deep dive (metadata → efficacy → safety) for papers with full text access (>2000 characters)
- **Detailed Endpoint Capture**: Extracts granular efficacy and safety endpoints with statistical significance and time-to-event data
- **Extraction Method Tracking**: Distinguishes between multi-stage (high detail) vs single-pass (abstract-only) extractions

### 📊 Advanced Scoring Methodology
- **Quality-Weighted Response Scoring**: Endpoints scored by both results AND instrument quality (validated vs ad-hoc measures)
- **Concordance Analysis**: Bonus/penalty based on agreement across multiple endpoints (0.85-1.15x multiplier)
- **Category-Weighted Scoring**: Primary endpoints weighted 1.0x, secondary 0.6x, exploratory 0.3x
- **MedDRA-Aligned Safety Scoring**: Database-backed safety categories with regulatory flag detection

### 🎯 Improved Search & Filtering
- **LLM-Powered Paper Filtering**: Claude validates clinical data presence before extraction (reduces false positives)
- **Citation Snowballing**: Mines references from review articles to find original case series papers
- **Semantic Scholar Integration**: Semantic relevance ranking for better recall
- **Parallel Search Execution**: Multiple search strategies run simultaneously for speed

### 💾 Intelligent Caching
- **Paper Extraction Caching**: Indefinite cache (keyed by drug + PMID) saves ~50% on re-runs
- **Market Intelligence Caching**: 30-day cache prevents duplicate web searches
- **Token Savings Tracking**: Reports estimated tokens saved by cache hits

### 📈 Enhanced Market Intelligence
- **TAM Analysis with Rationale**: Total addressable market estimates with source attribution
- **Pipeline Therapy Tracking**: Clinical trial data from ClinicalTrials.gov
- **Attributed Sources**: All market claims tracked with URLs for verification

---

## Overview

The Case Study Analysis v2 tool identifies drug repurposing opportunities by analyzing published case series and case reports. When you enter a drug name in the "Full Analysis" tab and click "Run Full Analysis", the system executes a comprehensive 6-stage pipeline that typically takes 30-60 minutes and costs $5-10 in API fees.

---

## The 6-Stage Analysis Pipeline

### **Stage 1: Drug Information Retrieval**

**What happens:**
- The system looks up the drug in multiple data sources (in priority order):
  1. Internal PostgreSQL database (cached from previous runs)
  2. DailyMed API (official FDA drug labeling)
  3. Drugs.com web scraping
  4. Tavily web search as fallback

**What it extracts:**
- Generic name (e.g., "ixekizumab" for brand name "Taltz")
- Mechanism of action (e.g., "IL-17A inhibitor")
- Molecular target (e.g., "Interleukin-17A")
- **Approved indications** - critical for filtering out on-label uses

**Why this matters:**
The approved indications list is used to exclude papers about already-approved uses. We only want to find *off-label* or *repurposing* opportunities.

---

### **Stage 2: Comprehensive Literature Search**

**What happens:**
The system executes a multi-layer search strategy with parallel execution for speed. All search strategies run simultaneously, then results are deduplicated and filtered.

---

#### **Search Strategy Layers**

**1. Enhanced PubMed Search**

Uses clinical data indicators beyond simple "case report" keywords:

**Query Construction:**
- Drug name + "case series" OR "case report"
- Drug name + "off-label" OR "compassionate use"
- Drug name + "expanded access"
- Drug name + disease terms (if known)
- Filters: English language, has abstract

**Clinical Data Indicators:**
- Looks for N= patterns (sample size mentions)
- Response rate mentions (e.g., "5/7 patients responded")
- Efficacy endpoint mentions (e.g., "PASI-75", "remission")
- Safety event mentions (e.g., "adverse events", "tolerability")

**2. Semantic Scholar Search**

Uses semantic embeddings for relevance ranking:
- Finds papers semantically similar to "case series of [drug] for [indication]"
- Captures papers that don't use exact "case report" terminology
- Better recall for international journals and non-standard terminology

**3. Citation Snowballing**

Mines references from review articles:
- Searches for review articles about the drug
- Extracts cited PMIDs from review article reference lists
- Follows citations to find original case reports
- Particularly effective for finding older/obscure case reports

**4. Web Search (Tavily)**

Captures grey literature and recent publications:
- Conference abstracts not yet indexed in PubMed
- Preprints (medRxiv, bioRxiv)
- Hospital case reports
- International journals not indexed in PubMed
- Very recent publications (last 3-6 months)

---

#### **LLM-Powered Filtering**

After initial search (typically 200+ papers), Claude AI reviews each abstract:

**Filtering Criteria:**

✅ **Include if:**
- Contains actual patient-level clinical data
- Describes treatment outcomes (efficacy or safety)
- Reports off-label or novel indication use
- Case series (N≥2) or case report (N=1)

❌ **Exclude if:**
- Review article without original data
- Preclinical/in vitro study
- Animal study
- Editorial or commentary
- About approved indication (matches exclusion list)
- No clinical outcomes reported

**Filtering Prompt:**
Claude receives:
- Paper title and abstract
- Drug's approved indications (exclusion list)
- Instructions to verify clinical data presence

**Filtering Output:**
- Binary decision: Include or Exclude
- Reason for exclusion (for auditing)
- Typically reduces 200+ papers → 30-60 relevant papers

---

#### **Deduplication**

Papers deduplicated by:
- PMID (PubMed ID) - primary key
- DOI (Digital Object Identifier) - secondary key
- Title similarity (fuzzy matching) - catches same paper from different sources

---

#### **Full-Text Availability Check**

For each paper:
- Checks if PMC ID exists (indicates open access full text)
- Flags papers with full text for multi-stage extraction
- Papers without full text → single-pass extraction from abstract

---

#### **Output**

A curated list of papers with:
- Title, abstract, PMID (PubMed ID)
- PMC ID (if open access full text is available)
- Publication metadata (journal, year, authors)
- Source (PubMed, Semantic Scholar, Web, Citation)
- Relevance score (from LLM filtering)
- Full-text availability flag

---

### **Stage 3: Clinical Data Extraction**

**What happens:**
For each paper, the system extracts structured clinical data using Claude AI. The extraction method adapts based on content availability.

---

#### **Extraction Method Selection**

**Multi-Stage Extraction** (for full-text papers ≥2000 characters):
- Triggered when PMC full text is available
- 3-stage sequential extraction for maximum detail
- ~4000 tokens per stage (12,000 total)

**Single-Pass Extraction** (for abstract-only papers):
- Used when only abstract/snippet available
- All data extracted in one Claude call
- ~4000 tokens total

---

#### **Multi-Stage Extraction Methodology (Full-Text Papers)**

**Stage 1: Basic Metadata Extraction**
- Disease/indication being treated
- Sample size (N patients)
- Study design (case series, case report, retrospective, prospective)
- Patient demographics (age, sex distribution)
- Prior treatment failures
- Treatment regimen (dose, route, duration)
- **Relevance check**: Is this actually off-label use?

**Stage 2: Deep Efficacy Extraction**
- **Detailed efficacy endpoints** with granular data:
  - Endpoint name (e.g., "PASI-75", "ACR50", "remission rate")
  - Endpoint category (primary, secondary, exploratory)
  - Baseline value (e.g., "mean PASI 18.2")
  - Follow-up value (e.g., "mean PASI 4.1 at week 12")
  - Result interpretation (e.g., "77% reduction from baseline")
  - Statistical significance (p-value, confidence interval)
  - Time point (e.g., "week 12", "6 months")
  - Number of responders (e.g., "12/15 patients achieved PASI-75")
- **Response rate calculation**: % achieving primary outcome
- **Durability signals**: Time to response, duration of response
- **Effect size**: Magnitude of clinical benefit

**Stage 3: Deep Safety Extraction**
- **Detailed safety endpoints** with event-level data:
  - Event name (e.g., "neutropenia", "injection site reaction")
  - Event category (infection, hepatotoxicity, cardiovascular, etc.)
  - Severity grade (Grade 1-5, mild/moderate/severe)
  - Number affected (e.g., "2/15 patients")
  - Percentage (e.g., "13.3%")
  - Action taken (dose reduction, discontinuation, hospitalization)
  - Outcome (resolved, ongoing, fatal)
- **Serious adverse events (SAEs)**: Life-threatening or requiring hospitalization
- **Discontinuation rate**: % stopping due to adverse events
- **Safety profile classification**: Favorable, Acceptable, Concerning

---

#### **Single-Pass Extraction (Abstract-Only Papers)**

Extracts all available information in one pass:
- Basic metadata (disease, sample size, study design)
- Summary efficacy (response rate, efficacy signal strength)
- Summary safety (adverse events list, safety profile)
- Publication metadata (journal, year, PMID)

**Limitations:**
- Less granular endpoint data
- May miss statistical significance details
- Limited safety event categorization

---

#### **Data Validation & Quality Control**

**Relevance Filtering:**
- Claude evaluates if paper describes actual off-label clinical use
- Filters out: preclinical studies, in vitro studies, review articles without original data
- Flags papers about approved indications for exclusion

**Extraction Completeness Scoring:**
- Tracks which fields were successfully extracted
- Used in Evidence Quality scoring (Stage 6)
- Helps identify high-quality vs low-quality extractions

**Caching Strategy:**
- All extractions saved to PostgreSQL database
- Cache key: `drug_name + PMID`
- Cache duration: Indefinite (extractions don't change)
- On re-run: Cached extractions loaded instantly (saves ~2000 tokens per paper)
- Token savings tracked and reported

---

### **Stage 4: Disease Name Standardization**

**What happens:**
Claude AI standardizes disease names across all extractions to enable aggregation and prevent duplicate market intelligence searches.

---

#### **Standardization Methodology**

**Step 1: Collect Unique Disease Names**
- Extracts all unique disease names from extractions
- Example raw names: ["Crohn's disease", "Crohn disease", "CD", "inflammatory bowel disease - Crohn's type"]

**Step 2: LLM-Based Grouping**

Claude receives:
- List of all disease names
- Instructions to group similar/related diseases
- Guidelines for canonical naming

**Grouping Rules:**
- Synonyms → Same canonical name (e.g., "Crohn's disease" = "Crohn disease")
- Abbreviations → Full name (e.g., "CD" → "Crohn's Disease")
- Subtypes → Parent disease (e.g., "plaque psoriasis" → "Psoriasis")
- Related conditions → Keep separate if clinically distinct

**Step 3: Assign Canonical Names**

For each group, Claude selects the most standard/recognizable name:
- Prefers full disease names over abbreviations
- Uses standard medical terminology
- Maintains clinical specificity when important

**Example Standardization:**

**Input:**
- "Crohn's disease"
- "Crohn disease"
- "CD"
- "inflammatory bowel disease - Crohn's"

**Output:**
- Canonical name: "Crohn's Disease"
- All 4 extractions mapped to this name

**Step 4: Update Extractions**

Each extraction updated with:
- `disease_normalized`: Canonical disease name
- `disease`: Original disease name (preserved for auditing)

---

#### **Why This Matters**

**Prevents Duplicate Market Intelligence Searches:**
- Without standardization: 4 separate market searches for "Crohn's disease", "Crohn disease", "CD", "IBD-Crohn's"
- With standardization: 1 market search for "Crohn's Disease", results shared across all 4 extractions
- Saves ~3 web searches × $0.10 = $0.30 per duplicate
- Saves ~3000 tokens × 3 = 9000 tokens per duplicate

**Improves Aggregation:**
- Can calculate total patients across all Crohn's papers
- Can identify most common efficacy endpoints for Crohn's
- Can compare response rates across different Crohn's studies

**Better Reporting:**
- Summary tables show "Crohn's Disease" once instead of 4 separate rows
- Easier to identify top opportunities by indication
- Cleaner Excel exports

---

### **Stage 5: Market Intelligence Enrichment** (Optional)

**What happens:**
For each unique disease (after standardization), the system performs 5 targeted web searches to gather comprehensive market context. This stage is optional but highly recommended for prioritization.

---

#### **Market Intelligence Search Strategy**

**1. Epidemiology Search**

**Query:** `"{disease}" prevalence United States epidemiology patients`

**Target Sources:**
- CDC reports
- NIH/NIDDK statistics
- Medical journal epidemiology studies
- Patient advocacy organization data

**Extraction:**
- US prevalence (e.g., "1.3 million patients")
- US incidence (e.g., "70,000 new cases per year")
- Patient population size
- Trend direction (increasing/stable/decreasing)
- Data source and year

**Claude Extraction Prompt:**
- Receives top 5 search results
- Extracts numerical prevalence/incidence
- Identifies most authoritative source
- Flags conflicting estimates

---

**2. FDA Approved Drugs Search**

**Query:** `"{disease}" FDA approved drugs treatments biologics site:fda.gov OR site:drugs.com OR site:medscape.com`

**Target Sources:**
- FDA.gov drug approvals
- Drugs.com drug monographs
- Medscape treatment guidelines

**Extraction:**
- List of FDA-approved drugs for this indication
- Drug classes (e.g., "TNF inhibitors", "IL-17 inhibitors")
- Approval dates
- Number of approved therapies (for competitor scoring)

---

**3. Standard of Care Search**

**Query:** `"{disease}" standard of care treatment guidelines first line second line therapy`

**Target Sources:**
- Clinical practice guidelines (ACR, AAD, AGA, etc.)
- UpToDate treatment algorithms
- Medical society recommendations

**Extraction:**
- First-line therapies (e.g., "methotrexate, TNF inhibitors")
- Second-line therapies (e.g., "IL-17 inhibitors, JAK inhibitors")
- Third-line/refractory options
- Treatment paradigm description
- Efficacy ranges for standard therapies (e.g., "ACR50: 40-60%")

**Why This Matters:**
- Enables comparison of case series efficacy vs standard of care
- Informs unmet need scoring
- Identifies positioning opportunities (first-line vs refractory)

---

**4. Pipeline Search**

**Query:** `"{disease}" clinical trial Phase 2 OR Phase 3 site:clinicaltrials.gov OR site:biopharmcatalyst.com`

**Target Sources:**
- ClinicalTrials.gov trial listings
- BiopharmCatalyst pipeline database
- Pharmaceutical company press releases

**Extraction:**
- Drugs in Phase 2/3 development
- Mechanisms of action in pipeline
- Expected approval timelines
- Number of pipeline therapies (for competitor scoring)
- Trial status (recruiting, completed, failed)

**Why This Matters:**
- Identifies future competition
- Reveals mechanism validation (multiple companies pursuing same target)
- Informs market timing (crowded vs open field)

---

**5. Market Size Search (TAM Analysis)**

**Query:** `"{disease}" market size TAM treatment penetration addressable market forecast`

**Target Sources:**
- Market research reports (GlobalData, Evaluate Pharma)
- Pharmaceutical analyst reports
- Company investor presentations
- Healthcare market forecasts

**Extraction:**
- Total addressable market (TAM) in USD
- Current market size
- Projected market growth (CAGR)
- Treatment penetration rate
- Average annual cost per patient
- Market forecast year

**Calculation Methodology:**

If direct TAM data unavailable, system calculates:

**TAM = Patient Population × Treatment Penetration × Annual Cost**

**Treatment Penetration Estimates:**
- Rare diseases (<10K patients): 80-90% (high diagnosis rate)
- Specialty diseases (10K-100K): 60-70%
- Common diseases (>100K): 40-50%

**Annual Cost Estimates (if no approved drugs):**
- Rare disease (<10K patients): $200K+/year
- Specialty disease (10K-100K): $50-100K/year
- Common disease (>100K): $10-30K/year

---

#### **Source Attribution**

All market intelligence claims tracked with:
- Source URL
- Source title
- Attribution category (e.g., "Epidemiology", "Approved Treatments", "Pipeline")
- Search date

**Example Attribution:**
```
Epidemiology:
- "1.3M US patients" → CDC.gov, "Inflammatory Bowel Disease Statistics", 2023

Approved Treatments:
- "5 FDA-approved biologics" → FDA.gov, "Crohn's Disease Approvals", 2024

Pipeline:
- "8 drugs in Phase 2/3" → ClinicalTrials.gov, searched Dec 2025
```

---

#### **Caching Strategy**

**Cache Duration:** 30 days

**Rationale:**
- Epidemiology data changes slowly (annual updates)
- Approved drugs change infrequently (quarterly at most)
- Pipeline data changes monthly
- Market forecasts updated quarterly

**Cache Key:** `disease_normalized + "market_intel"`

**Cache Hit Benefits:**
- Instant retrieval (no web searches)
- Saves ~5 web searches × $0.10 = $0.50 per disease
- Saves ~3000 tokens per disease
- Enables fast re-runs across multiple drugs

**Cache Invalidation:**
- Automatic after 30 days
- Manual invalidation available for major events (e.g., new drug approval)

---

#### **Output**

Each opportunity enriched with:
- **Epidemiology:** Patient population, prevalence, incidence, trend
- **Standard of Care:** Approved drugs, treatment paradigm, efficacy ranges
- **Pipeline:** Drugs in development, mechanisms, trial status
- **Market Size:** TAM estimate, market forecast, annual cost
- **Unmet Need:** Assessment based on SOC efficacy vs case series efficacy
- **Competitive Landscape:** Number of approved + pipeline therapies
- **Sources:** URLs for all claims (for verification)

---

### **Stage 6: Scoring and Ranking**

**What happens:**
Each repurposing opportunity is scored on three dimensions using a sophisticated multi-factor methodology.

---

#### **Clinical Signal Score (50% of overall score)**

**Components:**
- Response rate (quality-weighted): 40%
- Safety profile: 40%
- Organ domain breadth: 20%

---

##### **Response Rate Scoring Methodology**

This is the most complex component, using a **quality-weighted multi-endpoint approach**:

**Step 1: Score Each Endpoint Individually (1-10 scale)**

For each detailed efficacy endpoint:
- Extract the result (e.g., "80% achieved PASI-75")
- Convert to efficacy score based on magnitude:
  - >80% response = 10
  - 60-80% response = 8
  - 40-60% response = 6
  - 20-40% response = 4
  - <20% response = 2

**Step 2: Assess Endpoint Quality (1-10 scale)**

Each endpoint is scored for instrument quality:

**Validated Gold-Standard Instruments (Score: 10):**
- FDA-approved endpoints (e.g., PASI, EASI, ACR, DAS28)
- Regulatory-grade biomarkers (e.g., HbA1c, viral load)
- Standardized clinical scales (e.g., SLEDAI, CDAI)

**Moderate-Quality Instruments (Score: 7):**
- Physician Global Assessment (PGA)
- Patient-reported outcomes (PROs)
- Generic response/remission criteria

**Ad-Hoc Instruments (Score: 4):**
- Non-standardized measures
- Investigator-defined endpoints
- Narrative descriptions without quantification

**Quality Score Calculation:**
- System maintains database of validated instruments by disease
- Matches endpoint names against known instruments
- Assigns quality score based on validation status

**Step 3: Calculate Category Weights**

Endpoints weighted by hierarchy:
- **Primary endpoints**: 1.0x weight
- **Secondary endpoints**: 0.6x weight
- **Exploratory endpoints**: 0.3x weight

**Step 4: Calculate Quality Weights**

Quality score (1-10) mapped to weight (0.4-1.0):
- Quality weight = 0.4 + (quality_score / 10) × 0.6
- Example: Quality score 10 → weight 1.0
- Example: Quality score 4 → weight 0.64

**Step 5: Calculate Combined Weight**

For each endpoint:
- Combined weight = category_weight × quality_weight
- Example: Secondary endpoint (0.6) with validated instrument (1.0) = 0.6 total weight
- Example: Primary endpoint (1.0) with ad-hoc measure (0.64) = 0.64 total weight

**Step 6: Calculate Weighted Average**

Weighted average = Σ(efficacy_score × combined_weight) / Σ(combined_weight)

**Step 7: Apply Concordance Multiplier**

**Concordance Analysis:**
- Classifies each endpoint as positive (score >5.5), negative (score <4.5), or neutral (4.5-5.5)
- Calculates concordance = fraction pointing in same direction
- Applies multiplier:
  - ≥90% concordance: 1.15x (very high agreement)
  - ≥75% concordance: 1.10x (good agreement)
  - ≥60% concordance: 1.00x (acceptable)
  - ≥40% concordance: 0.90x (mixed results)
  - <40% concordance: 0.85x (contradictory results)

**Rationale:** High concordance across endpoints strengthens confidence in the signal. Mixed results suggest heterogeneous response or methodological issues.

**Step 8: Blend with Best Endpoint**

To prevent dilution of strong signals:
- Find best single endpoint score
- Final score = (weighted_avg × concordance × 0.70) + (best_endpoint × 0.30)

**Rationale:** If one endpoint shows exceptional results (e.g., 95% remission rate), we don't want it diluted by weaker exploratory endpoints.

**Step 9: Clamp to 1-10 Range**

Final response rate score bounded to 1-10 scale.

---

##### **Safety Profile Scoring Methodology**

**Step 1: Collect Safety Data**
- Detailed safety endpoints (event-level data)
- Serious adverse events (SAE) list
- Adverse events (AE) list
- Discontinuation data

**Step 2: Classify Safety Signals**

Uses **MedDRA-aligned safety categories** from database:
- Infection (severity weight: 6, regulatory flag: Yes)
- Hepatotoxicity (severity weight: 8, regulatory flag: Yes)
- Cardiovascular events (severity weight: 9, regulatory flag: Yes)
- Malignancy (severity weight: 10, regulatory flag: Yes)
- Cytopenia (severity weight: 7, regulatory flag: Yes)
- Death (severity weight: 10, regulatory flag: Yes)

**Step 3: Calculate Base Score from SAE Percentage**
- 0% SAEs = 10.0
- <5% SAEs = 8.0
- 5-10% SAEs = 6.0
- 10-20% SAEs = 4.0
- >20% SAEs = 2.0

**Step 4: Apply Severity Penalty**

If serious safety categories detected:
- Calculate average severity weight across detected categories
- Severity penalty = (avg_severity - 5) × 0.3
- Adjusted score = base_score - severity_penalty

**Step 5: Flag Regulatory Concerns**

Tracks categories with regulatory flags for reporting:
- Hepatotoxicity → Black box warning risk
- Cardiovascular events → REMS program risk
- Malignancy → Long-term safety monitoring required

**Output:**
- Safety score (1-10)
- Categories detected (e.g., ["infection", "hepatotoxicity"])
- Regulatory flags (e.g., ["hepatotoxicity"])
- SAE percentage
- Discontinuation rate

---

##### **Organ Domain Breadth Scoring**

Scores diversity of organ systems affected (1-10):
- Measures whether drug shows efficacy across multiple organ domains
- Higher score = broader applicability
- Example: Drug effective in skin, joints, and GI = higher score than skin only

---

#### **Evidence Quality Score (25% of overall score)**

**Components:**
- Sample size: 35%
- Publication venue: 25%
- Response durability: 25%
- Extraction completeness: 15%

**Sample Size Scoring:**
- N≥50 = 10
- N=20-49 = 8
- N=10-19 = 6
- N=5-9 = 4
- N=2-4 = 2
- N=1 = 1

**Publication Venue Scoring:**
- Peer-reviewed journal = 10
- Preprint = 6
- Conference abstract = 4
- Other = 2

**Response Durability Scoring:**
- >1 year follow-up = 10
- 6-12 months = 7
- 3-6 months = 5
- 1-3 months = 3
- <1 month = 1

**Extraction Completeness Scoring:**
- Measures % of fields successfully extracted
- Higher completeness = more reliable data

---

#### **Market Opportunity Score (25% of overall score)**

**Components:**
- Number of competitors: 33%
- Market size: 33%
- Unmet need: 33%

**Competitors Scoring:**
- No approved drugs = 10
- 1-2 approved drugs = 7
- 3-5 approved drugs = 5
- 6-10 approved drugs = 3
- >10 approved drugs = 1

**Market Size Scoring:**
- >$10B = 10
- $5-10B = 9
- $1-5B = 8
- $500M-1B = 7
- $100-500M = 6
- $50-100M = 5
- $10-50M = 4
- <$10M = 2

**Unmet Need Scoring:**
- Compares case series efficacy vs approved drug efficacy
- No approved drugs = 10 (automatic)
- Better efficacy than approved = 10
- Similar efficacy = 5
- Worse efficacy = 2

---

#### **Overall Priority Calculation**

**Formula:**
Overall Priority = (Clinical × 0.50) + (Evidence × 0.25) + (Market × 0.25)

**Output:**
- Opportunities ranked by overall priority score (1-10 scale)
- High priority = score ≥ 7
- Each opportunity assigned a rank (#1, #2, #3, etc.)
- Detailed breakdown of all component scores saved for transparency

---

## Final Outputs

### **1. Database Storage**
All data is saved to PostgreSQL:
- Run metadata (drug name, parameters, timestamp)
- Drug information
- Paper extractions (all papers, even irrelevant ones for auditing)
- Repurposing opportunities (only relevant extractions)
- Market intelligence (cached for reuse)

### **2. Excel Report**
Auto-generated spreadsheet with multiple tabs:
- Summary tab with top opportunities
- Detailed opportunity data
- Clinical endpoints
- Market intelligence
- Source citations

**Filename:** `{drug_name}_report_{timestamp}.xlsx`

### **3. JSON Export**
Complete structured data export for programmatic access.

**Filename:** `{drug_name}_full_{timestamp}.json`

### **4. Interactive Dashboard**
The Streamlit UI displays:
- Summary metrics (total opportunities, high priority count, avg score)
- Visual analysis (charts and graphs)
- Detailed opportunity cards with expandable sections
- Ability to load historical runs

---

## Key Features

### **Intelligent Caching**
- Paper extractions cached indefinitely (keyed by drug + PMID)
- Market intelligence cached for 30 days
- Saves ~50% of API costs on re-runs

### **Quality Control**
- LLM filtering ensures papers contain actual clinical data
- Relevance flagging excludes non-repurposing papers
- Multi-stage extraction for full-text papers ensures detail

### **Transparency**
- All sources tracked with URLs
- Extraction method logged (multi-stage vs single-pass)
- Token usage and cost estimates provided

### **Scalability**
- Parallel searches for speed
- Database-backed for handling 100+ drugs
- Designed for mechanism-based analysis (analyze all drugs with a given mechanism)

---

## Typical Results

**For a single drug analysis:**
- 30-60 relevant papers found
- 20-40 repurposing opportunities identified
- 5-10 high-priority opportunities (score ≥ 7)
- 30-60 minutes runtime
- $5-10 API cost

**Example output:**
"Rituximab analysis found 42 opportunities across 28 unique indications, with 8 high-priority opportunities including autoimmune encephalitis (score: 8.2), IgG4-related disease (score: 7.9), and pemphigus vulgaris (score: 7.7)."

