"""Test baricitinib workflow with database persistence."""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
from src.tools.case_series_database import CaseSeriesDatabase

# Get API keys
anthropic_key = os.getenv('ANTHROPIC_API_KEY')
tavily_key = os.getenv('TAVILY_API_KEY')
pubmed_email = os.getenv('PUBMED_EMAIL', 'test@example.com')
pubmed_api_key = os.getenv('PUBMED_API_KEY')
db_url = os.getenv('DATABASE_URL')

print("=" * 60)
print("BARICITINIB CASE SERIES WORKFLOW - DATABASE PERSISTENCE TEST")
print("=" * 60)

# Check database connection first
print("\n1. Checking database connection...")
db = CaseSeriesDatabase(db_url)
print(f"   Database available: {db.is_available}")

# Count existing runs
runs_before = db.get_historical_runs(limit=100)
print(f"   Existing runs in database: {len(runs_before)}")

# Initialize agent
print("\n2. Initializing agent with database...")
agent = DrugRepurposingCaseSeriesAgent(
    anthropic_api_key=anthropic_key,
    database_url=db_url,
    case_series_database_url=db_url,
    pubmed_email=pubmed_email,
    pubmed_api_key=pubmed_api_key,
    tavily_api_key=tavily_key,
    cache_max_age_days=30
)
print(f"   Agent database available: {agent.database_available}")

# Run analysis (limited to 3 papers for quick test)
print("\n3. Running baricitinib analysis (max 3 papers)...")
print("   This will take a few minutes...")

result = agent.analyze_drug(
    drug_name="baricitinib",
    max_papers=3,
    include_web_search=False,
    enrich_market_data=True
)

print(f"\n4. Results:")
print(f"   Papers screened: {result.papers_screened}")
print(f"   Papers extracted: {result.papers_extracted}")
print(f"   Opportunities found: {len(result.opportunities)}")
print(f"   Estimated cost: ${result.estimated_cost_usd:.2f}")

# Check database was updated
print("\n5. Verifying database persistence...")
runs_after = db.get_historical_runs(limit=100)
print(f"   Runs in database now: {len(runs_after)}")
print(f"   New runs added: {len(runs_after) - len(runs_before)}")

# Find the new run
if runs_after:
    latest_run = runs_after[0]
    print(f"\n6. Latest run details:")
    print(f"   Run ID: {latest_run.get('run_id')}")
    print(f"   Drug: {latest_run.get('drug_name')}")
    print(f"   Status: {latest_run.get('status')}")
    print(f"   Papers found: {latest_run.get('papers_found')}")
    print(f"   Papers extracted: {latest_run.get('papers_extracted')}")
    print(f"   Opportunities: {latest_run.get('opportunities_found')}")
    print(f"   Cache hits (papers): {latest_run.get('papers_from_cache')}")
    print(f"   Cache hits (market intel): {latest_run.get('market_intel_from_cache')}")
    
    # Get full details
    run_details = db.get_run_details(latest_run.get('run_id'))
    if run_details:
        print(f"\n7. Database contents for this run:")
        print(f"   Extractions saved: {len(run_details.get('extractions', []))}")
        print(f"   Opportunities saved: {len(run_details.get('opportunities', []))}")
        
        for ext in run_details.get('extractions', []):
            print(f"   - Extraction: {ext.get('disease')} (PMID: {ext.get('pmid')})")

# Check if we can load the run back
print("\n8. Testing load_run_as_result...")
loaded = agent.load_historical_run(latest_run.get('run_id'))
if loaded:
    print(f"   ✅ Successfully loaded run with {len(loaded.opportunities)} opportunities")
else:
    print("   ❌ Failed to load run")

print("\n" + "=" * 60)
print("✅ DATABASE PERSISTENCE TEST COMPLETE")
print("=" * 60)

