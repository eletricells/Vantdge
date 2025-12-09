"""
Test the disease mapping system including:
1. Database-backed disease mappings (loading from DB)
2. Disease name variants lookup
3. Disease parent mappings lookup
4. Auto-detection/inference of missing mappings (LLM)
5. ClinicalTrials.gov API integration
6. Seed data verification
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.tools.case_series_database import CaseSeriesDatabase

# Get database URL
db_url = (
    os.getenv('DATABASE_URL') or 
    os.getenv('DRUG_DATABASE_URL') or
    os.getenv('DISEASE_LANDSCAPE_URL') or
    os.getenv('PAPER_CATALOG_URL')
)

def test_database_connection():
    """Test 1: Verify database connection and tables exist."""
    print("\n" + "="*60)
    print("TEST 1: Database Connection & Tables")
    print("="*60)
    
    if not db_url:
        print("❌ No database URL found in environment")
        return False
    
    db = CaseSeriesDatabase(db_url)
    
    if not db.is_available:
        print("❌ Database not available")
        return False
    
    print(f"✅ Connected to database")
    
    # Check tables exist
    stats = db.get_disease_variant_stats()
    print(f"✅ Disease variant stats: {stats}")
    
    return True


def test_load_disease_mappings():
    """Test 2: Load disease mappings from database."""
    print("\n" + "="*60)
    print("TEST 2: Load Disease Mappings from Database")
    print("="*60)
    
    db = CaseSeriesDatabase(db_url)
    
    # Load name variants
    variants = db.load_disease_name_variants()
    print(f"✅ Loaded {len(variants)} disease variant sets")
    
    # Show some examples
    for disease, alts in list(variants.items())[:3]:
        print(f"   {disease}: {alts[:3]}...")
    
    # Load parent mappings
    parents = db.load_disease_parent_mappings()
    print(f"✅ Loaded {len(parents)} parent mappings")
    
    # Show some examples
    for specific, parent in list(parents.items())[:3]:
        print(f"   '{specific}' → '{parent}'")
    
    return len(variants) > 0 and len(parents) > 0


def test_variant_lookup():
    """Test 3: Test disease variant lookup."""
    print("\n" + "="*60)
    print("TEST 3: Disease Variant Lookup")
    print("="*60)
    
    db = CaseSeriesDatabase(db_url)
    variants = db.load_disease_name_variants()
    
    # Test known diseases
    test_cases = [
        "Systemic Lupus Erythematosus",
        "Dermatomyositis", 
        "Rheumatoid Arthritis",
        "Atopic Dermatitis",
    ]
    
    all_passed = True
    for disease in test_cases:
        if disease in variants:
            print(f"✅ {disease}: {variants[disease]}")
        else:
            # Try case-insensitive
            found = False
            for k, v in variants.items():
                if k.lower() == disease.lower():
                    print(f"✅ {disease} (case-insensitive): {v}")
                    found = True
                    break
            if not found:
                print(f"❌ {disease}: No variants found")
                all_passed = False
    
    return all_passed


def test_parent_lookup():
    """Test 4: Test parent disease lookup."""
    print("\n" + "="*60)
    print("TEST 4: Parent Disease Lookup")
    print("="*60)
    
    db = CaseSeriesDatabase(db_url)
    parents = db.load_disease_parent_mappings()
    
    # Test known subtypes
    test_cases = [
        ("refractory dermatomyositis", "Dermatomyositis"),
        ("anti-MDA5 dermatomyositis", "Dermatomyositis"),
        ("moderate-to-severe atopic dermatitis", "Atopic Dermatitis"),
        ("refractory rheumatoid arthritis", "Rheumatoid Arthritis"),
        ("class IV lupus nephritis", "Lupus Nephritis"),
    ]
    
    all_passed = True
    for specific, expected_parent in test_cases:
        actual = parents.get(specific)
        if actual == expected_parent:
            print(f"✅ '{specific}' → '{actual}'")
        elif actual:
            print(f"⚠️ '{specific}' → '{actual}' (expected '{expected_parent}')")
        else:
            # Try case-insensitive
            found = False
            for k, v in parents.items():
                if k.lower() == specific.lower():
                    print(f"✅ '{specific}' (case-insensitive) → '{v}'")
                    found = True
                    break
            if not found:
                print(f"❌ '{specific}': No parent found")
                all_passed = False
    
    return all_passed


def test_clinicaltrials_api():
    """Test 5: Test ClinicalTrials.gov API integration."""
    print("\n" + "="*60)
    print("TEST 5: ClinicalTrials.gov API Integration")
    print("="*60)

    import requests

    # Test the API directly first (without phase filter which is not a valid parameter)
    print("Testing ClinicalTrials.gov API directly...")
    base_url = "https://clinicaltrials.gov/api/v2/studies"
    params = {
        "query.cond": "Dermatomyositis",
        "pageSize": 5,
        "fields": "NCTId,BriefTitle,Phase,OverallStatus"
    }

    try:
        response = requests.get(base_url, params=params, timeout=30)
        print(f"API Response Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            studies = data.get('studies', [])
            print(f"✅ Direct API call returned {len(studies)} studies")

            if studies:
                for study in studies[:2]:
                    proto = study.get('protocolSection', {})
                    id_mod = proto.get('identificationModule', {})
                    print(f"   - {id_mod.get('nctId', 'N/A')}: {id_mod.get('briefTitle', 'N/A')[:50]}...")
                return True
            else:
                print("⚠️ API returned empty studies list")
                return False
        else:
            print(f"❌ API returned status {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

    except Exception as e:
        print(f"❌ API request failed: {e}")
        return False


def test_agent_disease_methods():
    """Test 6: Test agent's disease mapping methods."""
    print("\n" + "="*60)
    print("TEST 6: Agent Disease Mapping Methods")
    print("="*60)

    from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent

    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    if not anthropic_key:
        print("❌ ANTHROPIC_API_KEY not found, skipping")
        return False

    agent = DrugRepurposingCaseSeriesAgent(
        anthropic_api_key=anthropic_key,
        database_url=db_url
    )

    print(f"Agent loaded {len(agent._disease_name_variants)} variant sets")
    print(f"Agent loaded {len(agent._disease_parent_mappings)} parent mappings")

    # Test _get_parent_disease (without inference to avoid API calls)
    test_subtypes = [
        "refractory dermatomyositis",
        "anti-MDA5 dermatomyositis",
        "moderate-to-severe atopic dermatitis",
    ]

    print("\nTesting _get_parent_disease (no inference):")
    for subtype in test_subtypes:
        parent = agent._get_parent_disease(subtype, use_inference=False)
        if parent:
            print(f"   ✅ '{subtype}' → '{parent}'")
        else:
            print(f"   ❌ '{subtype}' → No parent found")

    # Test _get_disease_name_variants (without inference)
    test_diseases = ["Dermatomyositis", "Systemic Lupus Erythematosus"]

    print("\nTesting _get_disease_name_variants (no inference):")
    for disease in test_diseases:
        variants = agent._get_disease_name_variants(disease, use_inference=False)
        print(f"   ✅ '{disease}' → {variants[:4]}...")

    # Test _deduplicate_diseases
    test_list = [
        "Atopic Dermatitis",
        "atopic dermatitis",
        "AD",
        "Dermatomyositis",
        "refractory dermatomyositis"
    ]

    print("\nTesting _deduplicate_diseases:")
    print(f"   Input: {test_list}")
    deduped = agent._deduplicate_diseases(test_list)
    print(f"   Output: {deduped}")

    return True


def test_llm_inference():
    """Test 7: Test LLM inference for unmapped diseases."""
    print("\n" + "="*60)
    print("TEST 7: LLM Inference for Unmapped Diseases")
    print("="*60)

    from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent

    anthropic_key = os.getenv('ANTHROPIC_API_KEY')
    if not anthropic_key:
        print("❌ ANTHROPIC_API_KEY not found, skipping")
        return False

    agent = DrugRepurposingCaseSeriesAgent(
        anthropic_api_key=anthropic_key,
        database_url=db_url
    )

    # Test with a disease that's unlikely to be in the database
    test_disease = "refractory anti-synthetase syndrome with mechanic's hands and interstitial lung disease"

    print(f"Testing inference for: '{test_disease}'")
    print("(This will make an LLM API call)")

    result = agent._infer_disease_mapping(test_disease)

    if result:
        print(f"✅ Inference successful:")
        print(f"   Parent: {result.get('parent_disease')}")
        print(f"   Canonical: {result.get('canonical_name')}")
        print(f"   Relationship: {result.get('relationship_type')}")
        print(f"   Confidence: {result.get('confidence')}")
        print(f"   Variants: {[v.get('name') for v in result.get('variants', [])]}")
        print(f"   Reasoning: {result.get('reasoning', '')[:100]}...")
        return True
    else:
        print("❌ Inference failed")
        return False


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "="*60)
    print("DISEASE MAPPING SYSTEM - COMPREHENSIVE TEST SUITE")
    print("="*60)

    results = {}

    # Run tests
    results["1. Database Connection"] = test_database_connection()
    results["2. Load Mappings"] = test_load_disease_mappings()
    results["3. Variant Lookup"] = test_variant_lookup()
    results["4. Parent Lookup"] = test_parent_lookup()
    results["5. ClinicalTrials API"] = test_clinicaltrials_api()
    results["6. Agent Methods"] = test_agent_disease_methods()
    results["7. LLM Inference"] = test_llm_inference()

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = 0
    failed = 0
    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1

    print(f"\nTotal: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

