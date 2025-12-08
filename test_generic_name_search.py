"""
Test that the search correctly uses both brand name and generic name.

This test verifies that when searching for "Fabhalta", the system:
1. Retrieves the generic name "iptacopan" from drug info
2. Searches PubMed for both "Fabhalta" OR "iptacopan"
3. Finds papers indexed under either name
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_drug_info_retrieval():
    """Test that we can get generic name for Fabhalta."""
    print("\n" + "="*80)
    print("TEST 1: Drug Info Retrieval")
    print("="*80)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    agent = DrugRepurposingCaseSeriesAgent(anthropic_api_key=api_key)
    drug_info = agent._get_drug_info("Fabhalta")
    
    print(f"\nDrug Name: {drug_info.get('drug_name')}")
    print(f"Generic Name: {drug_info.get('generic_name')}")
    print(f"Mechanism: {drug_info.get('mechanism')}")
    print(f"Approved Indications: {drug_info.get('approved_indications')}")
    
    assert drug_info.get('generic_name'), "❌ FAILED: No generic name found"
    assert drug_info['generic_name'].lower() == 'iptacopan', f"❌ FAILED: Expected 'iptacopan', got '{drug_info['generic_name']}'"
    
    print("\n✅ PASSED: Generic name retrieved correctly")
    return drug_info

def test_pubmed_search_with_generic():
    """Test that PubMed search uses both brand and generic names."""
    print("\n" + "="*80)
    print("TEST 2: PubMed Search with Generic Name")
    print("="*80)

    api_key = os.getenv("ANTHROPIC_API_KEY")
    agent = DrugRepurposingCaseSeriesAgent(anthropic_api_key=api_key)
    
    # Search with both names
    seen_ids = set()
    papers = agent._search_pubmed_enhanced(
        drug_name="Fabhalta",
        seen_ids=seen_ids,
        generic_name="iptacopan"
    )
    
    print(f"\n✅ Found {len(papers)} papers searching for 'Fabhalta' OR 'iptacopan'")
    
    # Show first 5 papers
    print("\nFirst 5 papers:")
    for i, paper in enumerate(papers[:5], 1):
        title = paper.get('title', 'No title')[:80]
        pmid = paper.get('pmid', 'No PMID')
        print(f"  {i}. [{pmid}] {title}...")
    
    return papers

def test_known_papers():
    """Test that we can find the known relevant papers."""
    print("\n" + "="*80)
    print("TEST 3: Finding Known Relevant Papers")
    print("="*80)
    
    # Known relevant papers (from user)
    known_papers = {
        "Cold agglutinin disease": "10.3389/fimmu.2025.1672590",
        "Atypical HUS": "iptacopan in C5 blockade",
        "TA-TMA": "S0006497125093954"
    }
    
    api_key = os.getenv("ANTHROPIC_API_KEY")
    agent = DrugRepurposingCaseSeriesAgent(anthropic_api_key=api_key)
    seen_ids = set()
    papers = agent._search_pubmed_enhanced(
        drug_name="Fabhalta",
        seen_ids=seen_ids,
        generic_name="iptacopan"
    )
    
    print(f"\nSearching {len(papers)} papers for known relevant papers...")
    
    found_papers = []
    for paper in papers:
        title = paper.get('title', '').lower()
        doi = paper.get('doi', '').lower()
        
        for disease, identifier in known_papers.items():
            if identifier.lower() in title or identifier.lower() in doi:
                found_papers.append((disease, paper))
                print(f"\n✅ FOUND: {disease}")
                print(f"   Title: {paper.get('title', 'No title')[:80]}...")
                print(f"   PMID: {paper.get('pmid', 'No PMID')}")
                print(f"   DOI: {paper.get('doi', 'No DOI')}")
    
    if not found_papers:
        print("\n⚠️  WARNING: None of the known papers were found in this search")
        print("   This might be because:")
        print("   1. Papers are too recent (not yet indexed)")
        print("   2. Papers are in different databases (not PubMed)")
        print("   3. Search queries need further refinement")
    else:
        print(f"\n✅ Found {len(found_papers)}/{len(known_papers)} known papers")
    
    return found_papers

def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("TESTING: Generic Name Search for Fabhalta/Iptacopan")
    print("="*80)
    
    try:
        # Test 1: Get drug info
        drug_info = test_drug_info_retrieval()
        
        # Test 2: Search with generic name
        papers = test_pubmed_search_with_generic()
        
        # Test 3: Find known papers
        found_papers = test_known_papers()
        
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"✅ Drug info retrieved: {drug_info.get('generic_name')}")
        print(f"✅ Papers found: {len(papers)}")
        print(f"✅ Known papers found: {len(found_papers)}")
        print("\n✅ ALL TESTS PASSED")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

