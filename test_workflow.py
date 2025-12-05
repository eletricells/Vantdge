"""
Comprehensive test script for Case Study Analysis workflow.
Tests ALL 5 Tabs: Drug Info, Case Series Search, Data Extraction, Scoring, Full Analysis
Output saved to test_outputs/ folder for review.
"""
import os
import sys
import json
from datetime import datetime
from io import StringIO
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent

# Output capturing
class OutputCapture:
    def __init__(self):
        self.lines = []

    def write(self, text):
        self.lines.append(text)
        sys.__stdout__.write(text)

    def flush(self):
        sys.__stdout__.flush()

    def get_output(self):
        return ''.join(self.lines)

def pr(title):
    print("\n" + "=" * 80 + f"\n {title}\n" + "=" * 80)

def test_tab1(agent, drug):
    """Test Tab 1: Fetch Drug Information"""
    pr(f"TAB 1: DRUG INFO FOR '{drug.upper()}'")
    info = agent._get_drug_info(drug)

    print(f"\n  Drug Name:    {info.get('drug_name', 'N/A')}")
    print(f"  Generic Name: {info.get('generic_name', 'N/A')}")
    print(f"  Mechanism:    {info.get('mechanism', 'N/A')}")
    print(f"  Manufacturer: {info.get('manufacturer', 'N/A')}")

    inds = info.get('approved_indications', [])
    print(f"\n  Approved Indications ({len(inds)}):")
    for i, ind in enumerate(inds[:10], 1):
        print(f"    {i}. {ind}")

    print("\n--- Validation ---")
    if not info.get('generic_name'):
        print("  FAIL: Missing generic_name")
    else:
        print("  PASS: generic_name populated")

    mech = info.get('mechanism', '')
    if not mech:
        print("  FAIL: Missing mechanism")
    elif len(mech) > 100:
        print(f"  WARN: Mechanism too long ({len(mech)} chars)")
    else:
        print(f"  PASS: mechanism concise: '{mech}'")

    if not inds:
        print("  FAIL: No approved indications")
    else:
        print(f"  PASS: Found {len(inds)} indications")

    return info

def test_tab2(agent, drug, exclude):
    """Test Tab 2: Case Series Search"""
    pr(f"TAB 2: CASE SERIES SEARCH FOR '{drug.upper()}'")
    
    print(f"\n  Drug: {drug}")
    print(f"  Exclude: {exclude[:3]}..." if len(exclude) > 3 else f"  Exclude: {exclude}")
    print("\nSearching... (may take 1-2 mins)")
    
    papers = agent._search_case_series(
        drug_name=drug,
        exclude_indications=exclude,
        max_papers=100,
        include_web_search=False,
        use_llm_filtering=True
    )
    
    print(f"\n--- Results: {len(papers)} papers ---")
    ft = sum(1 for p in papers if p.get('has_full_text'))
    llm = sum(1 for p in papers if p.get('llm_relevance_reason'))
    print(f"  Full text (PMC): {ft}")
    print(f"  LLM verified: {llm}")
    
    # Group by disease
    diseases = {}
    for p in papers:
        d = p.get('extracted_disease') or 'Unknown'
        diseases[d] = diseases.get(d, 0) + 1
    
    print(f"\n  Diseases ({len(diseases)}):")
    for d, c in sorted(diseases.items(), key=lambda x: -x[1])[:15]:
        print(f"    - {d}: {c}")
    
    print("\n--- Sample Papers ---")
    for i, p in enumerate(papers[:5], 1):
        print(f"\n  {i}. {p.get('title', 'N/A')[:70]}...")
        print(f"     PMID: {p.get('pmid', 'N/A')} | Disease: {p.get('extracted_disease', 'N/A')}")
        print(f"     Full text: {p.get('has_full_text', False)}")
        r = p.get('llm_relevance_reason', '')
        if r: print(f"     Why: {r[:80]}...")
    
    print("\n--- Validation ---")
    bad = ['statpearls', 'review', 'guideline', 'pharmacokinetic']
    bad_found = [p for p in papers if any(k in p.get('title', '').lower() for k in bad)]
    
    if len(papers) == 0:
        print("  FAIL: No papers found")
    else:
        print(f"  PASS: Found {len(papers)} papers")
    
    if bad_found:
        print(f"  WARN: {len(bad_found)} potentially irrelevant papers")
        for p in bad_found[:3]:
            print(f"    - {p.get('title', '')[:50]}...")
    else:
        print("  PASS: No irrelevant papers detected")
    
    return papers

def test_tab3(agent, papers, drug, drug_info):
    """Test Tab 3: Data Extraction (with PMC full text)"""
    pr("TAB 3: DATA EXTRACTION (WITH PMC FULL TEXT)")

    if not papers:
        print("  FAIL: No papers to extract")
        return []

    # Extract from ALL papers with full text available
    papers_with_ft = [p for p in papers if p.get('has_full_text')]

    # Use all papers with full text for comprehensive test
    test_papers = papers_with_ft
    if not test_papers:
        print("  WARN: No papers with PMC full text, using abstracts only")
        test_papers = papers[:10]  # Fallback to first 10 abstracts

    print(f"\n  Extracting from {len(test_papers)} papers with PMC full text...")
    print(f"  (This may take several minutes)")

    results = []
    for i, p in enumerate(test_papers, 1):
        has_ft = "PMC" if p.get('has_full_text') else "Abstract only"
        print(f"\n  {i}. [{has_ft}] {p.get('title', 'N/A')[:55]}...")
        try:
            ext = agent._extract_case_series_data(drug, drug_info, p, fetch_full_text=True)
            results.append(ext)
            if ext:
                # CaseSeriesExtraction is a Pydantic model
                disease = getattr(ext, 'disease', 'N/A')
                pop = getattr(ext, 'patient_population', None)
                n = pop.n_patients if pop else 'N/A'
                eff = getattr(ext, 'efficacy', None)
                rr = eff.responders_pct if eff else 'N/A'
                print(f"     PASS: Disease={disease}, N={n}, Response={rr}%")

                # Show more details
                if eff and eff.efficacy_summary:
                    print(f"     Efficacy: {eff.efficacy_summary[:80]}...")
                safety = getattr(ext, 'safety', None)
                if safety and safety.safety_summary:
                    print(f"     Safety: {safety.safety_summary[:80]}...")
            else:
                print("     WARN: No data extracted")
        except Exception as e:
            print(f"     FAIL: {e}")
            results.append(None)

    ok = sum(1 for r in results if r)
    print(f"\n--- Validation ---")
    print(f"  Successful: {ok}/{len(test_papers)}")
    return results

def test_tab4(agent, extractions, drug):
    """Test Tab 4: Scoring & Prioritization"""
    pr("TAB 4: SCORING & PRIORITIZATION")

    if not extractions or not any(extractions):
        print("  SKIP: No extractions to score")
        return []

    valid_extractions = [e for e in extractions if e]
    print(f"\n  Scoring {len(valid_extractions)} extractions...")

    # Build opportunities from extractions
    from src.models.case_series_schemas import RepurposingOpportunity
    opportunities = []
    for ext in valid_extractions:
        opp = RepurposingOpportunity(extraction=ext)
        opportunities.append(opp)

    # Step 1: Standardize disease names
    print("\n  Standardizing disease names...")
    opportunities = agent.standardize_disease_names(opportunities)

    # Show standardization results
    standardized_count = sum(1 for o in opportunities if o.extraction.disease_normalized)
    if standardized_count > 0:
        print(f"  Standardized {standardized_count} disease names")
        unique_diseases = set(o.extraction.disease_normalized or o.extraction.disease for o in opportunities)
        print(f"  Unique diseases after standardization: {len(unique_diseases)}")

    # Step 2: Enrich with market intelligence (web search for each disease)
    print("\n  Fetching market intelligence for each disease...")
    print("  (This requires web search for epidemiology & standard of care)")
    opportunities = agent._enrich_with_market_data(opportunities)

    # Count how many got market data
    with_market = sum(1 for o in opportunities if o.market_intelligence and
                      o.market_intelligence.epidemiology.patient_population_size)
    print(f"  Market data fetched for {with_market}/{len(opportunities)} diseases")

    # Step 2: Score opportunities
    scored = agent._score_opportunities(opportunities)

    print("\n--- Scored Opportunities ---")
    for i, opp in enumerate(scored, 1):
        scores = opp.scores
        disease = opp.extraction.disease  # Access via extraction
        if scores:
            print(f"\n  {i}. {disease}")
            print(f"     Clinical:  {scores.clinical_signal:.1f}/10 (50% weight)")
            print(f"     Evidence:  {scores.evidence_quality:.1f}/10 (25% weight)")
            print(f"     Market:    {scores.market_opportunity:.1f}/10 (25% weight)")
            print(f"     TOTAL:     {scores.overall_priority:.1f}/10")
        else:
            print(f"\n  {i}. {disease} - No scores")

    print("\n--- Validation ---")
    scored_count = sum(1 for o in scored if o.scores and o.scores.overall_priority > 0)
    print(f"  Scored: {scored_count}/{len(scored)}")
    return scored


def test_tab5(agent, drug, drug_info, papers, extractions):
    """Test Tab 5: Full Analysis summary"""
    pr("TAB 5: FULL ANALYSIS SUMMARY")

    print(f"\n  Drug: {drug}")
    print(f"  Mechanism: {drug_info.get('mechanism', 'N/A')}")
    print(f"  Approved Indications: {len(drug_info.get('approved_indications', []))}")
    print(f"  Papers Found: {len(papers)}")
    print(f"  Papers with PMC Full Text: {sum(1 for p in papers if p.get('has_full_text'))}")
    print(f"  Extractions: {sum(1 for e in extractions if e)}")

    # Disease breakdown
    diseases = {}
    for p in papers:
        d = p.get('extracted_disease') or 'Unknown'
        diseases[d] = diseases.get(d, 0) + 1

    print(f"\n--- Top Off-Label Indications ---")
    for d, c in sorted(diseases.items(), key=lambda x: -x[1])[:10]:
        print(f"    {d}: {c} papers")

    print("\n--- Validation ---")
    print(f"  PASS: Full pipeline executed")
    return True


def main():
    # Create output directory
    output_dir = "test_outputs"
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_dir, f"workflow_test_{timestamp}.txt")

    # Capture output
    capture = OutputCapture()
    sys.stdout = capture

    try:
        pr("CASE STUDY ANALYSIS - COMPREHENSIVE TEST (ALL 5 TABS)")
        print(f"  Drug: BARICITINIB")
        print(f"  Started: {datetime.now()}")
        print(f"  Output will be saved to: {output_file}")

        print("\nInitializing agent...")
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            print("ERROR: ANTHROPIC_API_KEY not found in environment")
            return

        agent = DrugRepurposingCaseSeriesAgent(
            anthropic_api_key=api_key,
            pubmed_email=os.getenv("PUBMED_EMAIL", "user@example.com"),
            pubmed_api_key=os.getenv("PUBMED_API_KEY"),
            tavily_api_key=os.getenv("TAVILY_API_KEY")
        )
        print("Agent ready.\n")

        # Run all 5 tabs
        info = test_tab1(agent, "baricitinib")
        papers = test_tab2(agent, "baricitinib", info.get('approved_indications', []))
        extractions = test_tab3(agent, papers, "baricitinib", info)
        scored = test_tab4(agent, extractions, "baricitinib")
        test_tab5(agent, "baricitinib", info, papers, extractions)

        pr("FINAL SUMMARY")
        print(f"  Tab 1 Drug Info:   {'PASS' if info.get('mechanism') else 'FAIL'}")
        print(f"  Tab 2 Search:      {'PASS' if papers else 'FAIL'} ({len(papers)} papers)")
        print(f"  Tab 3 Extraction:  {'PASS' if any(extractions) else 'FAIL'} ({sum(1 for e in extractions if e)} successful)")
        print(f"  Tab 4 Scoring:     {'PASS' if scored else 'FAIL'} ({len(scored)} scored)")
        print(f"  Tab 5 Analysis:    PASS")
        print(f"\n  Total API Tokens: {agent.total_input_tokens + agent.total_output_tokens:,}")
        print(f"  Completed: {datetime.now()}")

        # Save structured data as JSON
        json_file = os.path.join(output_dir, f"workflow_data_{timestamp}.json")
        data = {
            "drug_info": info,
            "papers": papers[:20],  # First 20 papers
            "extractions": [e.model_dump() if e else None for e in extractions],
            "scored": [{"disease": o.extraction.disease, "scores": o.scores.model_dump() if o.scores else None} for o in scored] if scored else []
        }
        with open(json_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"\n  JSON data saved to: {json_file}")

        # Generate proper final report (Excel + formatted report)
        pr("GENERATING FINAL REPORT")
        from src.models.case_series_schemas import DrugAnalysisResult

        # Build DrugAnalysisResult for export
        result = DrugAnalysisResult(
            drug_name="baricitinib",
            generic_name=info.get('generic_name'),
            mechanism=info.get('mechanism'),
            approved_indications=info.get('approved_indications', []),
            opportunities=scored,
            papers_screened=len(papers),
            papers_extracted=len(extractions),
            total_input_tokens=agent.total_input_tokens,
            total_output_tokens=agent.total_output_tokens
        )

        # Assign ranks
        sorted_opps = sorted(result.opportunities, key=lambda x: x.scores.overall_priority, reverse=True)
        for i, opp in enumerate(sorted_opps, 1):
            opp.rank = i
        result.opportunities = sorted_opps

        # Export to Excel
        excel_file = agent.export_to_excel(result, f"baricitinib_report_{timestamp}.xlsx")
        print(f"  Excel report: {excel_file}")

        # Export full JSON
        full_json = agent.export_to_json(result, f"baricitinib_full_{timestamp}.json")
        print(f"  Full JSON: {full_json}")

    finally:
        sys.stdout = sys.__stdout__

        # Save output to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(capture.get_output())
        print(f"\nOutput saved to: {output_file}")


if __name__ == "__main__":
    main()

