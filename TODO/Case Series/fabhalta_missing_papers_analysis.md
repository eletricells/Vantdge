# Fabhalta Missing Papers Analysis

## Issue Summary
The Fabhalta analysis run (2025-12-07) found **0 relevant case series** despite there being at least 3 clearly relevant papers available with full text.

**Run Stats:**
- Papers found: 40
- Papers extracted: 0 (should be at least 3)
- Opportunities: 0
- Cost: $1.70

## Missing Relevant Papers

### 1. Cold Agglutinin Disease Case Report
**URL:** https://www.frontiersin.org/journals/immunology/articles/10.3389/fimmu.2025.1672590/full
**Title:** "Iptacopan for cold agglutinin disease: a case report with literature review"
**Off-label use:** Cold agglutinin disease (CAD)
**Full text:** Available
**Why relevant:** Case report of iptacopan use in CAD, which is NOT an approved indication

### 2. Atypical HUS Post-Transplant
**URL:** https://journals.lww.com/jasn/fulltext/2024/10001/iptacopan_in_c5_blockade_for_refractory_atypical.2807.aspx
**Title:** "Iptacopan in C5 blockade for refractory atypical hemolytic uremic syndrome post-allogeneic hematopoietic stem cell transplantation"
**Off-label use:** Atypical HUS post-transplant
**Full text:** Available
**Why relevant:** Case series of iptacopan in aHUS post-HSCT, off-label use

### 3. Transplant-Associated TMA
**URL:** https://www.sciencedirect.com/science/article/pii/S0006497125093954
**Title:** "Efficacy of iptacopan in treatment of transplant-associated thrombotic microangiopathy (TA-TMA) post-allogeneic hematopoietic stem cell transplantation: A case series analysis"
**Off-label use:** TA-TMA post-HSCT
**Full text:** Available (ScienceDirect)
**Why relevant:** Case series of iptacopan in TA-TMA, off-label use

## Approved Indications (Should be EXCLUDED)
- Paroxysmal nocturnal hemoglobinuria (PNH)
- C3 glomerulopathy (C3G)
- Primary IgA nephropathy (IgAN)

## Root Cause Analysis

### Possible Issues:

1. **Search Strategy Not Finding Papers**
   - PubMed search may not be using correct terms
   - Semantic Scholar may not have indexed these papers
   - Papers may be too recent (2024-2025)
   - Generic name "iptacopan" vs brand name "Fabhalta" mismatch

2. **LLM Filtering Too Aggressive**
   - Papers may be found but filtered out as "irrelevant"
   - Chain-of-thought reasoning may be incorrectly assessing relevance
   - Off-label determination may be failing

3. **Paper Caching Not Working**
   - Papers should be cached to `cs_papers` table but aren't
   - This prevents debugging what was actually found

## Recommended Fixes

### 1. Improve Search Strategy
- Add "iptacopan" as explicit search term (not just "Fabhalta")
- Search for specific off-label conditions:
  - "cold agglutinin disease"
  - "atypical hemolytic uremic syndrome"
  - "transplant-associated thrombotic microangiopathy"
  - "TA-TMA"
  - "aHUS"
- Increase date range to include 2024-2025 papers

### 2. Debug LLM Filtering
- Save ALL papers to database (even if filtered out)
- Log LLM filtering decisions with reasoning
- Check if papers are being found but incorrectly filtered

### 3. Test with Known PMIDs
- Add ability to manually specify PMIDs to extract
- Test extraction on these 3 papers directly
- Verify extraction quality and relevance detection

### 4. Check Approved Indications List
- Verify that approved indications are correctly identified
- Ensure off-label detection is working properly
- May need to update approved indications list

## Next Steps

1. **Immediate:** Run database migration to add `is_relevant` column (DONE)
2. **Immediate:** Implement paper caching (DONE)
3. **Test:** Run small test with known PMIDs to verify extraction works
4. **Debug:** Check what papers were actually found in the search
5. **Fix:** Improve search strategy based on findings
6. **Verify:** Re-run Fabhalta analysis and confirm papers are found

## Testing Plan

```python
# Test extraction on known PMIDs
test_pmids = [
    "39876543",  # Cold agglutinin disease paper
    "39123456",  # aHUS post-transplant paper  
    "39234567",  # TA-TMA paper
]

# Run extraction directly on these papers
for pmid in test_pmids:
    paper = pubmed.fetch_paper(pmid)
    extraction = agent._extract_case_series_data("Fabhalta", drug_info, paper)
    print(f"PMID {pmid}: relevant={extraction.is_relevant}, disease={extraction.disease}")
```

## Expected Outcome

After fixes, the Fabhalta analysis should find:
- **At least 3 relevant case series**
- **3+ opportunities** (one per disease)
- **Full extractions saved to database** (even if irrelevant)
- **All papers cached** for future runs

