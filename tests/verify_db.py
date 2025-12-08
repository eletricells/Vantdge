"""Verify database persistence for baricitinib analysis."""
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

conn = psycopg2.connect(os.getenv('DISEASE_LANDSCAPE_URL'))
cur = conn.cursor()

print("=" * 60)
print("DATABASE VERIFICATION")
print("=" * 60)

# Check cs_analysis_runs
cur.execute("""
    SELECT run_id, drug_name, status, papers_found, papers_extracted, opportunities_found, created_at
    FROM cs_analysis_runs
    WHERE drug_name ILIKE '%baricitinib%'
    ORDER BY created_at DESC
    LIMIT 5
""")
runs = cur.fetchall()
print(f"\n📊 cs_analysis_runs: {len(runs)} recent runs")
for r in runs:
    print(f"   Run {r[0][:8]}...: {r[2]} | Papers: {r[3]} found, {r[4]} extracted | Opps: {r[5]} | {r[6]}")

# Check cs_extractions
cur.execute("SELECT COUNT(*) FROM cs_extractions WHERE drug_name ILIKE '%baricitinib%'")
ext_count = cur.fetchone()[0]
print(f"\n📄 cs_extractions: {ext_count} total extractions")

# Get cs_extractions columns
cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'cs_extractions' ORDER BY ordinal_position")
ext_cols = [r[0] for r in cur.fetchall()]
print(f"   Columns: {ext_cols[:10]}...")

# Show sample extractions if any exist
if ext_count > 0:
    cur.execute("""
        SELECT disease, pmid, n_patients, efficacy_signal
        FROM cs_extractions
        WHERE drug_name ILIKE '%baricitinib%'
        ORDER BY id DESC
        LIMIT 10
    """)
    print("\nRecent extractions:")
    for e in cur.fetchall():
        disease = e[0][:40] if e[0] else "Unknown"
        print(f"   {disease} | PMID:{e[1]} | N={e[2]} | {e[3]}")

# Check cs_opportunities  
cur.execute("SELECT COUNT(*) FROM cs_opportunities WHERE drug_name ILIKE '%baricitinib%'")
opp_count = cur.fetchone()[0]
print(f"\n🎯 cs_opportunities: {opp_count} total opportunities")

# Check cs_drugs
cur.execute("SELECT drug_name, mechanism, approved_indications FROM cs_drugs WHERE drug_name ILIKE '%baricitinib%'")
drug = cur.fetchone()
if drug:
    print(f"\n💊 cs_drugs: Found - {drug[0]}")
    print(f"   Mechanism: {drug[1]}")
    print(f"   Approved indications: {drug[2]}")
else:
    print("\n💊 cs_drugs: NOT FOUND")

conn.close()

# Check file exports
print("\n" + "=" * 60)
print("FILE EXPORT VERIFICATION")
print("=" * 60)

export_dir = 'data/case_series'
if os.path.exists(export_dir):
    files = os.listdir(export_dir)
    excel_files = sorted([f for f in files if 'baricitinib' in f.lower() and f.endswith('.xlsx')], reverse=True)
    json_files = sorted([f for f in files if 'baricitinib' in f.lower() and f.endswith('.json')], reverse=True)
    
    print(f"\n📁 Export directory: {export_dir}")
    print(f"   Excel files: {len(excel_files)}")
    print(f"   JSON files: {len(json_files)}")
    
    if excel_files:
        latest_excel = excel_files[0]
        full_path = os.path.join(os.path.abspath(export_dir), latest_excel)
        print(f"\n📊 Latest Excel file:")
        print(f"   {full_path}")
        
        # Get file size
        size_bytes = os.path.getsize(os.path.join(export_dir, latest_excel))
        print(f"   Size: {size_bytes / 1024:.1f} KB")
else:
    print(f"\n⚠️ Export directory not found: {export_dir}")

print("\n✅ Verification complete!")

