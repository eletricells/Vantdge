# Disease Intelligence Database

## Overview

A database of disease-level market intelligence focused on the **treatment funnel** - the data needed to calculate addressable market for advanced therapies.

**Goal:** Populate structured data for diseases that enables market sizing:
```
204K adults with SLE
  → 95% treated
  → 25% fail 1L
  → ~49K qualify for advanced therapy
  × $5,500 WAC × 12 months
  = ~$3.3B gross market
```

## Key Data Points Per Disease (USA Focus)

| Category | Data Points |
|----------|-------------|
| **Prevalence** | Total patients, adult/pediatric split, estimate type, confidence intervals, source quality tier |
| **Segmentation** | % diagnosed, % treated, severity breakdown |
| **Treatment Paradigm** | 1L drugs, 2L drugs, drug classes, estimated WAC |
| **Failure Rates** | % fail 1L, failure type (primary/secondary/intolerance), switch vs discontinuation rates |
| **Market Funnel** | Addressable patients, market size USD |

## Implementation Status

### Completed ✅

| Component | File | Description |
|-----------|------|-------------|
| Database Migration | `migrations/020_create_disease_intelligence.sql` | 3 tables: disease_intelligence, disease_treatments, disease_intel_sources |
| Pydantic Models | `src/disease_intelligence/models.py` | DiseaseIntelligence, PrevalenceEstimate, FailureRateEstimate, etc. |
| Repository | `src/disease_intelligence/repository.py` | CRUD operations, source tracking |
| LLM Prompts | `src/disease_intelligence/prompts/` | filter_papers.j2, extract_prevalence.j2, extract_treatment.j2, extract_failure_rates.j2 |
| Main Service | `src/disease_intelligence/service.py` | DiseaseIntelligenceService with multi-source search, weighted consensus, validation |
| Frontend | `frontend/pages/99_Disease_Intelligence.py` | View/edit disease data, market funnel visualization |

### Recent Improvements (Jan 2026)

See [CHANGELOG.md](CHANGELOG.md) for details.

| Improvement | Impact |
|-------------|--------|
| Per-paper estimate tracking | Transparency on data sources |
| Weighted consensus building | Better estimates (quality + recency weighted) |
| Failure type classification | Distinguish primary/secondary/intolerance |
| Switch vs discontinuation separation | More accurate market sizing |
| Extraction validation | Catch data quality issues |
| Expanded search queries | Better coverage of failure rate literature |

## Module Structure

```
src/disease_intelligence/
    __init__.py
    models.py                    # Pydantic models (PrevalenceEstimate, FailureRateEstimate, etc.)
    service.py                   # DiseaseIntelligenceService with validation & retry logic
    repository.py                # Database operations
    prompts/
        filter_papers.j2         # LLM paper filtering with relevance scoring
        extract_prevalence.j2    # Prevalence extraction (per-paper, CI, methodology)
        extract_treatment.j2     # Treatment paradigm extraction
        extract_failure_rates.j2 # Failure rate extraction (failure types, switch rates)
```

## Data Quality Features

### Per-Paper Estimate Tracking

Each data point is tracked to its source paper:
```python
PrevalenceEstimate(
    title="Prevalence of SLE in the United States...",
    pmid="34345022",
    quality_tier="Tier 1",
    estimate_type="prevalence",  # vs incidence
    total_patients=204295,
    confidence_interval="65.3-81.0 per 100,000",
    rate_type="crude",  # vs age_adjusted
    methodology="CDC National Lupus Registry meta-analysis",
    database_name="CDC National Lupus Registry network",
    data_year=2021,
)
```

### Weighted Consensus Building

Consensus estimates use quality and recency weighting:
- **Tier 1 sources**: 3x weight
- **Tier 2 sources**: 2x weight
- **Tier 3 sources**: 1x weight
- **Recency boost**: 1.5x for studies from 2020+
- **Large study boost**: 1.3x for N > 10M

### Failure Type Classification

```python
FailureRateEstimate(
    failure_type="primary_nonresponse",  # Never achieved response
    # or "secondary_loss_of_response",    # Lost response over time
    # or "intolerance",                   # Stopped due to side effects
    # or "discontinuation_any_reason",    # All-cause
    fail_rate_pct=25.5,
    clinical_endpoint="ACR50 non-response at week 24",
    switch_rate_pct=80.0,  # % who switched to another therapy
    switch_destination="TNF inhibitor",
    full_discontinuation_pct=20.0,  # % who stopped all treatment
)
```

### Extraction Validation

Automatic validation catches issues:
- Prevalence range > 10x spread → Warning
- Failure rates outside 0-100% → Error
- High variability in estimates → Warning
- Missing critical data → Warning

## Database Schema

### disease_intelligence
Main table with all disease data:
- Prevalence (total_patients, adult_patients, pediatric_patients, confidence)
- Segmentation (pct_diagnosed, pct_treated, severity_breakdown)
- Treatment paradigm (JSONB with 1L, 2L, 3L structure)
- Failure rates (fail_1L_pct, primary_failure_type, switch_rate_1L_pct)
- Market funnel (patients_treated, patients_fail_1L, market_size_2L_usd)

### disease_treatments
Normalized treatments by line:
- line_of_therapy (1L, 2L, 3L)
- drug_name, generic_name, drug_class
- wac_monthly, wac_source

### disease_intel_sources
Literature sources with tracking:
- pmid, doi, url, title, authors
- source_type (epidemiology, treatment_guideline, real_world)
- quality_tier (Tier 1, Tier 2, Tier 3)

## Usage

### Programmatic Population
```python
from src.disease_intelligence.service import DiseaseIntelligenceService
from src.disease_intelligence.repository import DiseaseIntelligenceRepository

# Auto-populate from literature
service = DiseaseIntelligenceService(...)
disease = await service.populate_disease(
    "Systemic Lupus Erythematosus",
    therapeutic_area="Autoimmune",
    force_refresh=True
)

# Access per-paper estimates
for est in disease.prevalence.source_estimates:
    print(f"{est.title}: {est.total_patients:,} ({est.quality_tier})")

# Access failure types
for est in disease.failure_rates.source_estimates:
    print(f"{est.failure_type}: {est.fail_rate_pct}%")
```

### Concurrent Processing
```python
# Process multiple diseases concurrently
diseases = ["Systemic Lupus Erythematosus", "Rheumatoid Arthritis", "NMOSD"]
results = await service.populate_diseases_concurrent(
    disease_names=diseases,
    max_concurrent=3,
    force_refresh=False,
)
```

## Literature Search Strategy

### Search Queries

**Prevalence** (8 PubMed + 5 web queries):
- `{disease} prevalence United States epidemiology`
- `{disease} claims database prevalence`
- `{disease} NHANES prevalence`
- `site:cdc.gov {disease} prevalence`
- `site:rarediseases.info.nih.gov {disease}`

**Failure Rates** (14 PubMed queries):
- `{disease} inadequate response first line therapy`
- `{disease} drug survival registry`
- `{disease} switching biologic therapy`
- `{disease} non-response primary secondary`
- `{disease} loss of response biologic`
- `{disease} intolerance discontinuation safety`

### Source Quality Tiers

| Tier | Sources | Weight |
|------|---------|--------|
| Tier 1 (High) | CDC, NIH GARD, systematic reviews, national registries, large RCTs | 3x |
| Tier 2 (Medium) | Claims databases (>10M lives), patient advocacy, state registries | 2x |
| Tier 3 (Low) | Single-center studies, older estimates (pre-2015), case series | 1x |

## Example: SLE (Real Extraction)

```yaml
disease: Systemic Lupus Erythematosus
therapeutic_area: Autoimmune
data_quality: High

prevalence:
  weighted_median: 204,295
  range: "449 - 204,295"
  confidence: Low  # Due to high CV (171%)
  source_count: 3
  sources:
    - title: "CDC National Lupus Registry meta-analysis"
      tier: Tier 1
      patients: 204,295
      ci: "65.3-81.0 per 100,000"
    - title: "Manhattan Lupus Surveillance Program"
      tier: Tier 3
      patients: 1,285

segmentation:
  pct_treated: 95
  severity:
    mild: 30
    moderate: 50
    severe: 20

treatment_paradigm:
  first_line:
    drugs: [Plaquenil, CellCept, Cytoxan]
  second_line:
    drugs:
      - Benlysta (BLyS inhibitor) - $5,500/mo (estimated)
      - Saphnelo (Type 1 IFN inhibitor) - $5,500/mo (estimated)
      - Lupkynis (Calcineurin inhibitor) - $5,500/mo (estimated)

failure_rates:
  median_fail_1L: 25.5%
  range: "18% - 34%"
  primary_failure_type: primary_nonresponse
  switch_rate_1L: 100%
  confidence: Low

market_funnel:
  total: 204,295
  treated: 194,080 (95%)
  fail_1L: 49,490 (25.5%)
  market_size: $3.3B
```

## WAC Estimation

Currently using placeholder WAC values based on disease prevalence:

| Prevalence | Estimated WAC/month |
|------------|---------------------|
| >500K patients | $4,500 |
| 100K-500K | $5,500 |
| 50K-100K | $8,000 |
| 10K-50K | $15,000 |
| 1K-10K | $30,000 |
| <1K (ultra-rare) | $50,000 |

Therapeutic area adjustments:
- Oncology: +50%
- Cell/Gene Therapy: +200%
- Neurology: +20%

## Future Extensions

- [ ] Real WAC lookup from drug database or external sources
- [ ] ClinicalTrials.gov integration for failure rates
- [ ] Competitor analysis by MOA
- [ ] Relative efficacy benchmarking
- [ ] Pipeline drug tracking
- [ ] Geographic expansion beyond USA
