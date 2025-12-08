# Excel Output Summary - Case Series v2 Scoring

## Overview
The Excel export now contains **4 sheets** with enhanced v2 scoring metrics:

---

## Sheet 1: Analysis Summary (NEW - First Sheet)
**Purpose:** Consolidated view of top 5 opportunities with cross-study aggregated evidence

### Columns:
| Column | Description | Example |
|--------|-------------|---------|
| **Rank** | Ranking by average overall score | 1, 2, 3, 4, 5 |
| **Disease** | Disease/indication name | "Rheumatoid Arthritis" |
| **# Studies** | Number of case series for this disease | 3 |
| **Total Patients** | Sum of patients across all studies | 45 |
| **Pooled Response (%)** | Weighted average response rate | 75.5 |
| **Response Range** | Min-max response rates | "60%-90%" |
| **Consistency** | Evidence consistency level | "High", "Moderate", "Low" |
| **Evidence Confidence** | Overall confidence level | "Moderate", "Low-Moderate", "Low", "Very Low" |
| **Clinical Score (avg)** | Average clinical signal score | 7.8 |
| **Evidence Score (avg)** | Average evidence quality score | 6.5 |
| **Market Score (avg)** | Average market opportunity score | 8.2 |
| **Overall Score (avg)** | Average overall priority score | 7.5 |
| **Best Study Score** | Highest overall score from any single study | 8.1 |
| **# Approved Competitors** | Number of approved drugs | 5 |
| **# Pipeline Therapies** | Number of pipeline therapies | 12 |
| **Unmet Need** | Whether unmet need exists | "Yes", "No", "Unknown" |
| **TAM Estimate** | Total addressable market estimate | "$2.5B annually" |

**Key Features:**
- Shows **top 5 diseases** ranked by average overall score
- Aggregates evidence across multiple studies for same disease
- Provides confidence metrics (consistency, evidence confidence)
- Includes market intelligence from best-scoring study

---

## Sheet 2: Drug Summary (Renamed from "Summary")
**Purpose:** High-level drug information and analysis metadata

### Columns:
| Column | Description |
|--------|-------------|
| **Drug** | Drug brand name |
| **Generic Name** | Generic/chemical name |
| **Mechanism** | Mechanism of action |
| **Approved Indications** | FDA-approved uses |
| **Papers Screened** | Number of papers analyzed |
| **Opportunities Found** | Number of repurposing opportunities |
| **Analysis Date** | When analysis was run |
| **Input Tokens** | Total input tokens used |
| **Output Tokens** | Total output tokens used |
| **Estimated Cost** | Estimated API cost |

---

## Sheet 3: Opportunities (Enhanced with v2 Scoring)
**Purpose:** Detailed breakdown of each repurposing opportunity

### Key Changes in v2:

#### New Columns (v2 Scoring):
- **Response Rate Score (Quality-Weighted)** - Multi-endpoint efficacy score with quality weighting
- **# Efficacy Endpoints Scored** - Number of endpoints used in scoring
- **Efficacy Concordance** - Concordance multiplier (0.85-1.15) based on endpoint agreement

#### Removed Columns (Deprecated):
- ~~Endpoint Quality Score~~ - Replaced by quality-weighted multi-endpoint scoring

### All Columns in Opportunities Sheet:

#### Basic Information:
- **Rank** - Overall ranking
- **Disease (Standardized)** - Normalized disease name
- **Disease (Original)** - Original disease name from paper
- **Evidence Level** - Case series, case report, etc.
- **N Patients** - Number of patients in study

#### Efficacy Details:
- **Primary Endpoint** - Main efficacy measure
- **Endpoint Result** - Result value/description
- **Response Rate** - Overall response rate description
- **Responders (%)** - Percentage of responders
- **Time to Response** - How long until response seen
- **Duration of Response** - How long response lasted
- **Efficacy Summary** - Narrative summary

#### Safety Details:
- **Safety Profile** - Excellent/Good/Acceptable/Concerning/Poor
- **SAE Count** - Number of serious adverse events
- **SAE (%)** - Percentage with serious adverse events
- **Discontinuations** - Number who discontinued
- **Adverse Events** - List of adverse events (truncated to 200 chars)
- **Serious AEs** - List of serious adverse events
- **Safety Summary** - Narrative summary

#### Scores - Overall (1-10 scale):
- **Clinical Score** - Clinical signal strength (50% weight)
- **Evidence Score** - Evidence quality (25% weight)
- **Market Score** - Market opportunity (25% weight)
- **Overall Priority** - Weighted average of above

#### Scores - Clinical Breakdown (v2):
- **Response Rate Score (Quality-Weighted)** - Multi-endpoint efficacy with quality weighting (40% of clinical)
- **Safety Score** - Safety profile score (40% of clinical)
- **Organ Domain Score** - Breadth of organ systems affected (20% of clinical)
- **# Efficacy Endpoints Scored** - Count of endpoints used
- **Efficacy Concordance** - Agreement multiplier (0.85-1.15)

#### Organ Domains:
- **Organ Domains Matched** - List of matched organ systems
- **N Organ Domains** - Count of organ domains

#### Source Information:
- **Key Findings** - Main takeaways from paper
- **Source** - Paper title
- **PMID** - PubMed ID
- **Year** - Publication year

---

## Sheet 4: Market Intelligence
**Purpose:** Detailed market analysis for each opportunity

### Columns:

#### Disease & Epidemiology:
- **Disease** - Disease/indication name
- **US Prevalence** - Prevalence estimate
- **US Incidence** - Incidence estimate
- **Patient Population** - Total patient population size
- **Prevalence Trend** - Increasing/Stable/Decreasing

#### Competitive Landscape:
- **Approved Treatments (Count)** - Number of approved drugs
- **Approved Drug Names** - List of approved drugs
- **Pipeline Therapies (Count)** - Number of pipeline therapies
- **Pipeline Details** - Detailed pipeline information with phase/company/trial ID
- **Unmet Need** - Whether unmet need exists
- **Treatment Paradigm** - Current treatment approach

#### Market Opportunity:
- **TAM Estimate** - Total addressable market
- **TAM Methodology** - How TAM was calculated
- **Market Dynamics** - Market trends and dynamics

#### Sources (Attributed by Category):
- **Sources: Epidemiology** - URLs for epidemiology data
- **Sources: Approved Treatments** - URLs for approved treatment info
- **Sources: Treatment Paradigm** - URLs for treatment paradigm
- **Sources: Pipeline/Clinical Trials** - URLs for pipeline data
- **Sources: TAM/Market Analysis** - URLs for market analysis

---

## Key Improvements in v2 Output:

### 1. **Analysis Summary Sheet (NEW)**
- First sheet provides executive summary
- Cross-study aggregation for same disease
- Evidence confidence metrics (consistency, confidence level)
- Top 5 opportunities at a glance

### 2. **Multi-Endpoint Efficacy Scoring**
- Scores ALL efficacy endpoints (primary, secondary, exploratory)
- Quality weighting (0.4-1.0) based on endpoint characteristics
- Category weighting (Primary=1.0, Secondary=0.6, Exploratory=0.3)
- Concordance multiplier (0.85-1.15) rewards consistent results

### 3. **Enhanced Transparency**
- Shows # of endpoints scored
- Shows concordance multiplier
- Deprecated endpoint_quality_score removed

### 4. **Sample Size Calibration**
- Calibrated for case series (N≥20=10, N≥15=9, N≥10=8, etc.)
- Appropriate for small sample literature

### 5. **Evidence Confidence Levels**
- Moderate: 3+ studies, 20+ patients, consistent, high-quality
- Low-Moderate: 3+ studies, 20+ patients, consistent
- Low: 2+ studies, 10+ patients
- Very Low: Single study or small samples

---

## Example Use Cases:

### For Quick Review:
→ **Analysis Summary sheet** - See top 5 opportunities with aggregated evidence

### For Deep Dive:
→ **Opportunities sheet** - Examine individual studies with detailed scoring breakdown

### For Market Assessment:
→ **Market Intelligence sheet** - Evaluate competitive landscape and TAM

### For Drug Overview:
→ **Drug Summary sheet** - Basic drug info and analysis metadata


