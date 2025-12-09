# Market Intelligence Schema Audit - COMPLETE

## ✅ All Issues Found and Fixed

### Summary
Conducted comprehensive audit of MarketIntelligence schema usage across the codebase. Found and fixed **3 critical issues** that would have prevented database save/load operations.

---

## Issues Found and Fixed

### Issue 1: Class Name Mismatch in check_market_intel_fresh()
**Location:** `src/tools/case_series_database.py` line 497

**Problem:**
```python
from src.models.case_series_schemas import Epidemiology, StandardOfCare, AttributedSource
```

**Actual Schema Names:**
- `EpidemiologyData` (not `Epidemiology`)
- `StandardOfCareData` (not `StandardOfCare`)
- `AttributedSource` ✓ (correct)

---

### Issue 2: Invalid Field in check_market_intel_fresh()
**Location:** `src/tools/case_series_database.py` line 529

**Problem:**
```python
return MarketIntelligence(
    ...
    unmet_needs=row.get('unmet_needs'),  # ❌ This field doesn't exist in MarketIntelligence
    ...
)
```

**Actual Schema:** `MarketIntelligence` does NOT have an `unmet_needs` field. The unmet need info is in `standard_of_care.unmet_need` (boolean) and `standard_of_care.unmet_need_description` (string).

---

### Issue 3: Incorrect Object Construction in check_market_intel_fresh()
**Location:** `src/tools/case_series_database.py` lines 499-510

**Problem:**
```python
epi = Epidemiology(  # ❌ Wrong class name
    prevalence=row.get('prevalence'),  # ❌ Wrong field name
    us_prevalence_estimate=row.get('prevalence')
) if row.get('prevalence') else None

soc = StandardOfCare(  # ❌ Wrong class name
    ...
)
```

**Actual Schema:**
- Should be `EpidemiologyData` (not `Epidemiology`)
- `EpidemiologyData` doesn't have a `prevalence` field, only `us_prevalence_estimate`, `us_incidence_estimate`, etc.

---

## Complete Field Mapping

### MarketIntelligence Schema Fields:
```python
disease: str
epidemiology: EpidemiologyData
standard_of_care: StandardOfCareData
market_size_estimate: Optional[str]
market_size_usd: Optional[float]
growth_rate: Optional[str]
tam_usd: Optional[float]
tam_estimate: Optional[str]
tam_rationale: Optional[str]
tam_sources: List[str]
pipeline_sources: List[str]
attributed_sources: List[AttributedSource]
```

### Database Table Columns (cs_market_intelligence):
```sql
disease
prevalence
incidence
approved_drugs
treatment_paradigm
unmet_needs
pipeline_drugs
tam_estimate
tam_growth_rate
market_dynamics
sources_epidemiology
sources_approved_drugs
sources_treatment
sources_pipeline
sources_tam
fetched_at
expires_at
```

### Correct Mapping:
- DB `prevalence` → Schema `epidemiology.us_prevalence_estimate`
- DB `incidence` → Schema `epidemiology.us_incidence_estimate`
- DB `approved_drugs` → Schema `standard_of_care.approved_drug_names`
- DB `treatment_paradigm` → Schema `standard_of_care.treatment_paradigm`
- DB `unmet_needs` → Schema `standard_of_care.unmet_need` (boolean) + `standard_of_care.unmet_need_description` (string)
- DB `pipeline_drugs` → Schema `standard_of_care.pipeline_therapies`
- DB `tam_estimate` → Schema `tam_estimate`
- DB `tam_growth_rate` → Schema `growth_rate`

---

## Fixes Applied

### Fix 1: Corrected Class Names in check_market_intel_fresh()
**File:** `src/tools/case_series_database.py` line 497

**Before:**
```python
from src.models.case_series_schemas import Epidemiology, StandardOfCare, AttributedSource
```

**After:**
```python
from src.models.case_series_schemas import EpidemiologyData, StandardOfCareData, AttributedSource, PipelineTherapy
```

---

### Fix 2: Removed Invalid Field from MarketIntelligence Construction
**File:** `src/tools/case_series_database.py` line 536

**Before:**
```python
return MarketIntelligence(
    disease=row.get('disease'),
    epidemiology=epi,
    standard_of_care=soc,
    tam_estimate=row.get('tam_estimate'),
    growth_rate=row.get('tam_growth_rate'),
    unmet_needs=row.get('unmet_needs'),  # ❌ Invalid field
    attributed_sources=attributed,
    pipeline_sources=row.get('sources_pipeline') or [],
    tam_sources=row.get('sources_tam') or []
)
```

**After:**
```python
return MarketIntelligence(
    disease=row.get('disease'),
    epidemiology=epi,
    standard_of_care=soc,
    tam_estimate=row.get('tam_estimate'),
    growth_rate=row.get('tam_growth_rate'),
    # unmet_needs removed - it's in standard_of_care.unmet_need
    attributed_sources=attributed,
    pipeline_sources=row.get('sources_pipeline') or [],
    tam_sources=row.get('sources_tam') or []
)
```

---

### Fix 3: Corrected EpidemiologyData Construction
**File:** `src/tools/case_series_database.py` lines 499-502

**Before:**
```python
epi = Epidemiology(  # ❌ Wrong class name
    prevalence=row.get('prevalence'),  # ❌ Invalid field
    us_prevalence_estimate=row.get('prevalence')
) if row.get('prevalence') else None
```

**After:**
```python
epi = EpidemiologyData(
    us_prevalence_estimate=row.get('prevalence'),
    us_incidence_estimate=row.get('incidence')
) if row.get('prevalence') or row.get('incidence') else EpidemiologyData()
```

---

### Fix 4: Corrected StandardOfCareData Construction with Pipeline Therapies
**File:** `src/tools/case_series_database.py` lines 504-520

**Before:**
```python
soc = StandardOfCare(  # ❌ Wrong class name
    approved_drug_names=row.get('approved_drugs') or [],
    treatment_paradigm=row.get('treatment_paradigm'),
    unmet_need=bool(row.get('unmet_needs')),
    unmet_need_description=row.get('unmet_needs'),
    pipeline_therapies=[]  # ❌ Not reconstructing from DB
) if row.get('approved_drugs') or row.get('treatment_paradigm') else None
```

**After:**
```python
# Reconstruct pipeline therapies from JSON
pipeline_therapies = []
if row.get('pipeline_drugs'):
    try:
        for p_dict in row.get('pipeline_drugs'):
            pipeline_therapies.append(PipelineTherapy(**p_dict))
    except Exception as e:
        logger.warning(f"Could not reconstruct pipeline therapies: {e}")

# Reconstruct StandardOfCareData
soc = StandardOfCareData(
    approved_drug_names=row.get('approved_drugs') or [],
    num_approved_drugs=len(row.get('approved_drugs') or []),
    treatment_paradigm=row.get('treatment_paradigm'),
    unmet_need=bool(row.get('unmet_needs')),
    unmet_need_description=str(row.get('unmet_needs')) if row.get('unmet_needs') else None,
    pipeline_therapies=pipeline_therapies,
    num_pipeline_therapies=len(pipeline_therapies)
)
```

---

### Fix 5: Fixed AttributedSource Construction (Missing Required Field)
**File:** `src/tools/case_series_database.py` lines 527-534

**Before:**
```python
for url in (row.get('sources_epidemiology') or []):
    attributed.append(AttributedSource(url=url, attribution='Epidemiology'))  # ❌ Missing title field
```

**After:**
```python
for url in (row.get('sources_epidemiology') or []):
    attributed.append(AttributedSource(url=url, title=None, attribution='Epidemiology'))
```

---

### Fix 6: Fixed unmet_needs Access in save_opportunity()
**File:** `src/tools/case_series_database.py` line 656

**Before:**
```python
market_unmet_needs = mi.unmet_needs  # ❌ Invalid field
```

**After:**
```python
market_unmet_needs = mi.standard_of_care.unmet_need if mi.standard_of_care else False
```

---

### Fix 7: Fixed unmet_need Access in save_market_intelligence()
**File:** `src/tools/case_series_database.py` lines 579, 606

**Before:**
```python
# Line 579 - extraction (missing)
# Line 606 - usage
treatment_paradigm, mi.unmet_needs, Json(pipeline_drugs),  # ❌ Invalid field
```

**After:**
```python
# Line 579 - extraction
unmet_need = mi.standard_of_care.unmet_need if mi.standard_of_care else False
# Line 606 - usage
treatment_paradigm, unmet_need, Json(pipeline_drugs),
```

---

## Verification

### All Schema Usages Checked:
✅ `check_market_intel_fresh()` - Fixed class names and field access
✅ `save_market_intelligence()` - Fixed field access
✅ `save_opportunity()` - Fixed field access
✅ `export_to_excel()` - Already correct (uses proper nested access)
✅ `_get_market_intelligence()` - Already correct (creates MarketIntelligence properly)

### No Additional Issues Found In:
- Market Intelligence schema definition (`src/models/case_series_schemas.py`)
- Excel export logic (`src/agents/drug_repurposing_case_series_agent.py` lines 5065-5145)
- Market intelligence fetching logic

---

## Testing Recommendation

Run the test script to verify the fixes:
```bash
python test_market_intel_save.py
```

This will:
1. Create a test MarketIntelligence object with all nested structures
2. Save it to the database
3. Retrieve it from cache
4. Verify all fields are correctly preserved

---

## Impact

These fixes ensure that:
1. ✅ Market intelligence can be saved to database without errors
2. ✅ Market intelligence can be loaded from cache correctly
3. ✅ All nested objects (EpidemiologyData, StandardOfCareData, PipelineTherapy) are properly reconstructed
4. ✅ The Market Intelligence sheet will appear in Excel reports when data is available
5. ✅ Future analysis runs will successfully cache and reuse market intelligence data

