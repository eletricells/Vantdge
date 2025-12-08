"""
Full baricitinib analysis with database persistence verification.
"""
import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Enable verbose logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, '.')
load_dotenv()

def main():
    from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
    import psycopg2
    
    print("=" * 60)
    print("BARICITINIB FULL ANALYSIS WITH DATABASE VERIFICATION")
    print("=" * 60)
    print(f"Started at: {datetime.now().isoformat()}")
    
    # Initialize agent WITH database connection
    agent = DrugRepurposingCaseSeriesAgent(
        anthropic_api_key=os.getenv('ANTHROPIC_API_KEY'),
        database_url=os.getenv('DISEASE_LANDSCAPE_URL'),  # For drug lookups
        case_series_database_url=os.getenv('DISEASE_LANDSCAPE_URL'),  # For persistence/caching
        pubmed_email=os.getenv('PUBMED_EMAIL', 'user@example.com'),
        pubmed_api_key=os.getenv('PUBMED_API_KEY'),
        semantic_scholar_api_key=os.getenv('SEMANTIC_SCHOLAR_API_KEY'),
        output_dir='data/case_series'
    )
    
    print("\n✅ Agent initialized successfully")
    
    # Run analysis (max_papers=500 = no practical limit)
    print("\n🔄 Starting full analysis for baricitinib...")
    print("   This will take 30-60 minutes. Progress will be logged.\n")
    
    result = agent.analyze_drug(
        drug_name='baricitinib',
        max_papers=500,  # No practical limit
        include_web_search=True,
        enrich_market_data=True
    )
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Drug: {result.drug_name}")
    print(f"Mechanism: {result.mechanism}")
    print(f"Approved indications: {len(result.approved_indications or [])}")
    print(f"Total opportunities found: {len(result.opportunities)}")
    print(f"Total cost: ${result.estimated_cost_usd:.2f}")
    print(f"Input tokens: {result.total_input_tokens:,}")
    print(f"Output tokens: {result.total_output_tokens:,}")

    # Export results
    print("\n" + "=" * 60)
    print("EXPORTING RESULTS")
    print("=" * 60)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_filename = f"baricitinib_report_{timestamp}.xlsx"
    json_filename = f"baricitinib_full_{timestamp}.json"

    excel_path = agent.export_to_excel(result, excel_filename)
    json_path = agent.export_to_json(result, json_filename)

    print(f"📊 Excel report: {excel_path}")
    print(f"📄 JSON data: {json_path}")
    
    # Verify database persistence
    print("\n" + "=" * 60)
    print("DATABASE VERIFICATION")
    print("=" * 60)
    
    conn = psycopg2.connect(os.getenv('DISEASE_LANDSCAPE_URL'))
    cur = conn.cursor()
    
    # Check cs_analysis_runs
    cur.execute("""
        SELECT run_id, drug_name, status, papers_found, papers_extracted, opportunities_found, created_at
        FROM cs_analysis_runs
        WHERE drug_name ILIKE '%baricitinib%'
        ORDER BY created_at DESC
        LIMIT 3
    """)
    runs = cur.fetchall()
    print(f"\n📊 cs_analysis_runs: {len(runs)} recent runs")
    for r in runs:
        run_id_short = str(r[0])[:8] if r[0] else "N/A"
        print(f"   Run {run_id_short}...: {r[2]} | Papers: {r[3]} found, {r[4]} extracted | Opps: {r[5]} | {r[6]}")
    
    # Check cs_extractions
    cur.execute("SELECT COUNT(*) FROM cs_extractions WHERE drug_name ILIKE '%baricitinib%'")
    ext_count = cur.fetchone()[0]
    print(f"\n📄 cs_extractions: {ext_count} total extractions")
    
    # Check cs_opportunities
    cur.execute("SELECT COUNT(*) FROM cs_opportunities WHERE drug_name ILIKE '%baricitinib%'")
    opp_count = cur.fetchone()[0]
    print(f"🎯 cs_opportunities: {opp_count} total opportunities")
    
    # Check cs_drugs
    cur.execute("SELECT * FROM cs_drugs WHERE drug_name ILIKE '%baricitinib%'")
    drug = cur.fetchone()
    print(f"💊 cs_drugs: {'Found' if drug else 'NOT FOUND'}")
    
    conn.close()
    
    # Check Excel export
    print("\n" + "=" * 60)
    print("FILE EXPORT VERIFICATION")
    print("=" * 60)
    
    export_dir = 'data/case_series'
    files = [f for f in os.listdir(export_dir) if 'baricitinib' in f.lower()]
    excel_files = [f for f in files if f.endswith('.xlsx')]
    json_files = [f for f in files if f.endswith('.json')]
    
    print(f"\n📁 Export directory: {export_dir}")
    print(f"   Excel files: {len(excel_files)}")
    print(f"   JSON files: {len(json_files)}")
    
    if excel_files:
        latest_excel = sorted(excel_files, reverse=True)[0]
        print(f"\n📊 Latest Excel file: {os.path.join(export_dir, latest_excel)}")
    
    print("\n✅ Analysis and verification complete!")
    print(f"Completed at: {datetime.now().isoformat()}")

if __name__ == "__main__":
    main()

