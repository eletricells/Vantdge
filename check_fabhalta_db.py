import psycopg2
import os
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

conn = psycopg2.connect(os.getenv('DISEASE_LANDSCAPE_URL'))

print("\n" + "="*60)
print("FABHALTA DATABASE CHECK")
print("="*60)

# Check analysis runs
print("\n=== ANALYSIS RUNS ===")
cur = conn.cursor(cursor_factory=RealDictCursor)
cur.execute("""
    SELECT run_id, drug_name, started_at, completed_at, status, 
           papers_found, papers_extracted, opportunities_found,
           total_input_tokens, total_output_tokens, estimated_cost_usd
    FROM cs_analysis_runs 
    WHERE drug_name ILIKE '%fabhalta%' 
    ORDER BY started_at DESC 
    LIMIT 5
""")
runs = cur.fetchall()
for i, run in enumerate(runs, 1):
    print(f"\n{i}. Run ID: {run['run_id']}")
    print(f"   Drug: {run['drug_name']}")
    print(f"   Started: {run['started_at']}")
    print(f"   Completed: {run['completed_at']}")
    print(f"   Status: {run['status']}")
    print(f"   Papers found: {run['papers_found']}")
    print(f"   Papers extracted: {run['papers_extracted']}")
    print(f"   Opportunities: {run['opportunities_found']}")
    print(f"   Tokens: {run['total_input_tokens']} in / {run['total_output_tokens']} out")
    print(f"   Cost: ${run['estimated_cost_usd']}")

# Check extractions
print("\n=== EXTRACTIONS ===")
cur.execute("SELECT COUNT(*) as count FROM cs_extractions WHERE drug_name ILIKE '%fabhalta%'")
ext_count = cur.fetchone()['count']
print(f"Total extractions: {ext_count}")

if ext_count > 0:
    cur.execute("""
        SELECT pmid, disease, n_patients, response_rate, efficacy_signal
        FROM cs_extractions 
        WHERE drug_name ILIKE '%fabhalta%'
        LIMIT 10
    """)
    extractions = cur.fetchall()
    print("\nSample extractions:")
    for ext in extractions:
        print(f"  - PMID {ext['pmid']}: {ext['disease']} (N={ext['n_patients']}, RR={ext['response_rate']}, Signal={ext['efficacy_signal']})")

# Check opportunities
print("\n=== OPPORTUNITIES ===")
cur.execute("SELECT COUNT(*) as count FROM cs_opportunities WHERE drug_name ILIKE '%fabhalta%'")
opp_count = cur.fetchone()['count']
print(f"Total opportunities: {opp_count}")

if opp_count > 0:
    cur.execute("""
        SELECT disease, n_patients, response_rate, overall_score
        FROM cs_opportunities 
        WHERE drug_name ILIKE '%fabhalta%'
        ORDER BY overall_score DESC
        LIMIT 10
    """)
    opportunities = cur.fetchall()
    print("\nTop opportunities:")
    for opp in opportunities:
        print(f"  - {opp['disease']}: N={opp['n_patients']}, RR={opp['response_rate']}, Score={opp['overall_score']}")

# Check papers
print("\n=== PAPERS ===")
cur.execute("SELECT COUNT(*) as count FROM cs_papers WHERE relevance_drug ILIKE '%fabhalta%'")
paper_count = cur.fetchone()['count']
print(f"Total papers cached: {paper_count}")

if paper_count > 0:
    cur.execute("""
        SELECT pmid, title, is_relevant, relevance_score, extracted_disease
        FROM cs_papers 
        WHERE relevance_drug ILIKE '%fabhalta%'
        ORDER BY fetched_at DESC
        LIMIT 10
    """)
    papers = cur.fetchall()
    print("\nRecent papers:")
    for paper in papers:
        print(f"  - PMID {paper['pmid']}: {paper['title'][:80]}...")
        print(f"    Relevant: {paper['is_relevant']}, Score: {paper['relevance_score']}, Disease: {paper['extracted_disease']}")

conn.close()

print("\n" + "="*60)
print("CHECK COMPLETE")
print("="*60)

