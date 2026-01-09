# Disease Intelligence Changelog

## [2026-01-08] Per-Paper Tracking & Weighted Consensus

Major improvements to data quality and transparency in the Disease Intelligence module.

### New Features

#### Per-Paper Estimate Tracking
- Each prevalence and failure rate estimate is now tracked to its source paper
- New fields: `estimate_type`, `confidence_interval`, `rate_type`, `methodology`, `database_name`, `study_population_n`
- Full transparency on where each data point comes from

#### Weighted Consensus Building
- Replaced simple median with weighted consensus
- Quality tier weighting: Tier 1 (3x), Tier 2 (2x), Tier 3 (1x)
- Recency boost: 1.5x for studies from 2020+
- Large study boost: 1.3x for studies with N > 10M
- Automatic confidence assessment with rationale

#### Failure Type Classification
- New `failure_type` field distinguishes:
  - `primary_nonresponse` - Never achieved adequate response
  - `secondary_loss_of_response` - Lost efficacy over time
  - `intolerance` - Stopped due to side effects
  - `discontinuation_any_reason` - All-cause

#### Switch vs Discontinuation Separation
- New fields: `switch_rate_pct`, `switch_destination`, `full_discontinuation_pct`
- Critical for market sizing: switchers are still addressable, discontinuers are lost

#### Extraction Validation
- Automatic sanity checks on extracted data
- Detects: wide prevalence range (>10x), invalid rates, high variability
- Validation issues stored in disease notes

#### Retry Logic
- Failed extractions automatically retry
- Second attempt uses fewer, higher-quality papers

### Schema Changes

**PrevalenceEstimate** - Added fields:
- `estimate_type` (prevalence/incidence/point_prevalence/period_prevalence)
- `confidence_interval` (95% CI as string)
- `rate_type` (crude/age_adjusted/age_specific)
- `study_population_n` (sample size)
- `database_name` (MarketScan, Optum, NHANES, etc.)

**FailureRateEstimate** - Added fields:
- `failure_type` (primary_nonresponse/secondary_loss/intolerance/discontinuation)
- `confidence_interval`
- `clinical_endpoint`
- `endpoint_definition`
- `specific_therapy`
- `timepoint_type` (fixed/median/cumulative)
- `denominator_n`
- `analysis_type` (ITT/per_protocol/as_treated)
- `switch_rate_pct`, `switch_destination`, `full_discontinuation_pct`
- `methodology`

**FailureRates** (aggregate) - Added fields:
- `primary_failure_type`
- `switch_rate_1L_pct`, `discontinuation_rate_1L_pct`
- `standardized_timepoint`
- `confidence`, `confidence_rationale`

### Prompt Improvements

**extract_prevalence.j2**:
- Updated US population to 340M
- Added instructions for estimate type classification
- Added confidence interval extraction
- Added rate type (crude vs age-adjusted) guidance
- Added database name extraction

**extract_failure_rates.j2**:
- Added failure type classification (critical)
- Added clinical endpoint extraction
- Added switch vs discontinuation separation
- Added denominator context (N, analysis type)
- Expanded key terms to look for

**filter_papers.j2**:
- Added relevance scoring (0-1)
- Added quality tier prediction
- Added expected_data field
- Added coverage gap identification

### Search Query Expansion

**Prevalence** (8 PubMed + 5 web queries):
- Added: claims database queries
- Added: NHANES prevalence
- Added: site:cdc.gov searches
- Added: site:rarediseases.info.nih.gov for rare diseases

**Failure Rates** (14 PubMed queries):
- Added: drug survival registry
- Added: persistence adherence real world
- Added: switching biologic therapy
- Added: non-response primary secondary
- Added: loss of response biologic
- Added: intolerance discontinuation safety

### Files Changed

| File | Changes |
|------|---------|
| `src/disease_intelligence/models.py` | Added PrevalenceEstimate and FailureRateEstimate fields |
| `src/disease_intelligence/service.py` | Added weighted consensus, validation, retry logic, WAC estimation |
| `src/disease_intelligence/prompts/extract_prevalence.j2` | Per-paper extraction, 340M population |
| `src/disease_intelligence/prompts/extract_failure_rates.j2` | Failure types, switch rates |
| `src/disease_intelligence/prompts/filter_papers.j2` | Relevance scoring |

### Test Results (SLE)

```
Prevalence: 204,295 (weighted median from 3 sources)
  - CDC meta-analysis: 204,295 (Tier 1)
  - Manhattan registry: 1,285 (Tier 3)
  - Midwest network: 449 (Tier 3)

Failure Rate: 25.5% (median from 4 sources)
  - Primary failure type: primary_nonresponse
  - Switch rate: 100%

Market Size: $3.3B (49K addressable × $66K/year)
```

### Known Limitations

- WAC values are placeholder estimates based on disease prevalence
- Some regional cohort studies may skew prevalence range
- Failure rate definitions vary significantly across studies
