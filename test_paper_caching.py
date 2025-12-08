"""
Test script to verify paper caching and extraction saving works correctly.
This simulates a small run to check:
1. Papers are saved to cs_papers table
2. Extractions are saved to cs_extractions table (even if irrelevant)
3. Cache is used on subsequent runs
"""
import os
from dotenv import load_dotenv
from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
from src.tools.case_series_database import CaseSeriesDatabase
import psycopg2

load_dotenv()

print("="*60)
print("TESTING PAPER CACHING & EXTRACTION SAVING")
print("="*60)

# Get database connection
db_url = os.getenv('DISEASE_LANDSCAPE_URL')
db = CaseSeriesDatabase(db_url)

# Test drug (use a small test case)
test_drug = "Dupilumab"  # Well-known drug with case series

print(f"\n1. Testing with drug: {test_drug}")
print(f"   Database available: {db.is_available}")

# Count existing papers and extractions for this drug
conn = psycopg2.connect(db_url)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM cs_papers WHERE relevance_drug ILIKE %s", (f'%{test_drug}%',))
papers_before = cur.fetchone()[0]
print(f"   Papers in cache before: {papers_before}")

cur.execute("SELECT COUNT(*) FROM cs_extractions WHERE drug_name ILIKE %s", (f'%{test_drug}%',))
extractions_before = cur.fetchone()[0]
print(f"   Extractions in DB before: {extractions_before}")

conn.close()

# Initialize agent
print(f"\n2. Initializing agent...")
agent = DrugRepurposingCaseSeriesAgent(
    anthropic_api_key=os.getenv('ANTHROPIC_API_KEY'),
    database_url=db_url,
    case_series_database_url=db_url,
    pubmed_email=os.getenv('PUBMED_EMAIL', 'test@example.com'),
    pubmed_api_key=os.getenv('PUBMED_API_KEY'),
    semantic_scholar_api_key=os.getenv('SEMANTIC_SCHOLAR_API_KEY'),
    cache_max_age_days=30
)

# Run analysis with very limited papers (just 5 for testing)
print(f"\n3. Running analysis (max 5 papers for testing)...")
try:
    result = agent.analyze_drug(
        drug_name=test_drug,
        max_papers=5,  # Very small for testing
        include_web_search=False  # Disable web search for speed
    )
    
    print(f"\n4. Analysis complete!")
    print(f"   Papers found: {result.papers_screened}")
    print(f"   Papers extracted: {result.papers_extracted}")
    print(f"   Opportunities: {len(result.opportunities)}")
    print(f"   Cost: ${result.estimated_cost_usd:.2f}")
    
except Exception as e:
    print(f"\n❌ Analysis failed: {e}")
    import traceback
    traceback.print_exc()

# Check database after run
print(f"\n5. Checking database after run...")
conn = psycopg2.connect(db_url)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM cs_papers WHERE relevance_drug ILIKE %s", (f'%{test_drug}%',))
papers_after = cur.fetchone()[0]
print(f"   Papers in cache after: {papers_after} (added {papers_after - papers_before})")

cur.execute("SELECT COUNT(*) FROM cs_extractions WHERE drug_name ILIKE %s", (f'%{test_drug}%',))
extractions_after = cur.fetchone()[0]
print(f"   Extractions in DB after: {extractions_after} (added {extractions_after - extractions_before})")

# Check relevance breakdown
cur.execute("""
    SELECT is_relevant, COUNT(*) 
    FROM cs_extractions 
    WHERE drug_name ILIKE %s 
    GROUP BY is_relevant
""", (f'%{test_drug}%',))
relevance_breakdown = cur.fetchall()
print(f"\n   Extraction relevance breakdown:")
for is_relevant, count in relevance_breakdown:
    print(f"     - {'Relevant' if is_relevant else 'Irrelevant'}: {count}")

# Check paper cache
cur.execute("""
    SELECT is_relevant, COUNT(*) 
    FROM cs_papers 
    WHERE relevance_drug ILIKE %s 
    GROUP BY is_relevant
""", (f'%{test_drug}%',))
paper_relevance = cur.fetchall()
print(f"\n   Paper cache relevance breakdown:")
for is_relevant, count in paper_relevance:
    print(f"     - {'Relevant' if is_relevant else 'Irrelevant'}: {count}")

conn.close()

print("\n" + "="*60)
print("TEST COMPLETE")
print("="*60)
print("\n✅ Expected behavior:")
print("   - Papers should be saved to cs_papers (even if irrelevant)")
print("   - Extractions should be saved to cs_extractions (even if irrelevant)")
print("   - Only relevant extractions should create opportunities")
print("\n🔄 Run this script again to test caching:")
print("   - Should use cached paper relevance assessments")
print("   - Should skip LLM filtering for cached papers")
print("   - Should be much faster on second run")

