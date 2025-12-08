"""
Test that database schema has been updated correctly with is_relevant column.
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

print("="*60)
print("DATABASE SCHEMA VERIFICATION")
print("="*60)

db_url = os.getenv('DISEASE_LANDSCAPE_URL')
conn = psycopg2.connect(db_url)
cur = conn.cursor()

# Check cs_extractions table has is_relevant column
print("\n1. Checking cs_extractions table schema...")
cur.execute("""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_name = 'cs_extractions'
    AND column_name IN ('is_off_label', 'is_relevant')
    ORDER BY column_name
""")
columns = cur.fetchall()
print("   Columns found:")
for col in columns:
    print(f"     - {col[0]}: {col[1]} (nullable: {col[2]}, default: {col[3]})")

# Check if is_relevant column exists
has_is_relevant = any(col[0] == 'is_relevant' for col in columns)
if has_is_relevant:
    print("   ✅ is_relevant column exists!")
else:
    print("   ❌ is_relevant column NOT FOUND!")

# Check cs_papers table schema
print("\n2. Checking cs_papers table schema...")
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_name = 'cs_papers'
    AND column_name IN ('pmid', 'relevance_drug', 'is_relevant', 'relevance_score', 'extracted_disease')
    ORDER BY column_name
""")
paper_columns = cur.fetchall()
print("   Columns found:")
for col in paper_columns:
    print(f"     - {col[0]}: {col[1]} (nullable: {col[2]})")

# Check indexes
print("\n3. Checking indexes...")
cur.execute("""
    SELECT indexname, indexdef
    FROM pg_indexes
    WHERE tablename IN ('cs_extractions', 'cs_papers')
    AND indexname LIKE '%relevant%'
""")
indexes = cur.fetchall()
if indexes:
    print("   Relevance indexes found:")
    for idx in indexes:
        print(f"     - {idx[0]}")
else:
    print("   ⚠️  No relevance indexes found")

# Test inserting a mock extraction with is_relevant=False
print("\n4. Testing insert with is_relevant=False...")
try:
    cur.execute("""
        INSERT INTO cs_extractions (
            drug_name, disease, is_off_label, is_relevant,
            n_patients, paper_title, full_extraction
        ) VALUES (
            'TEST_DRUG', 'TEST_DISEASE', TRUE, FALSE,
            10, 'Test Paper', '{}'::jsonb
        )
        RETURNING id, is_relevant
    """)
    result = cur.fetchone()
    print(f"   ✅ Successfully inserted extraction with is_relevant=False")
    print(f"      ID: {result[0]}, is_relevant: {result[1]}")
    
    # Clean up test data
    cur.execute("DELETE FROM cs_extractions WHERE drug_name = 'TEST_DRUG'")
    conn.commit()
    print("   ✅ Test data cleaned up")
    
except Exception as e:
    conn.rollback()
    print(f"   ❌ Insert failed: {e}")

# Test inserting a mock paper
print("\n5. Testing paper insert...")
try:
    cur.execute("""
        INSERT INTO cs_papers (
            pmid, relevance_drug, title, is_relevant, relevance_score
        ) VALUES (
            'TEST12345', 'TEST_DRUG', 'Test Paper Title', FALSE, 0.0
        )
        RETURNING pmid, is_relevant
    """)
    result = cur.fetchone()
    print(f"   ✅ Successfully inserted paper with is_relevant=False")
    print(f"      PMID: {result[0]}, is_relevant: {result[1]}")
    
    # Clean up test data
    cur.execute("DELETE FROM cs_papers WHERE pmid = 'TEST12345'")
    conn.commit()
    print("   ✅ Test data cleaned up")
    
except Exception as e:
    conn.rollback()
    print(f"   ❌ Insert failed: {e}")

conn.close()

print("\n" + "="*60)
print("SCHEMA VERIFICATION COMPLETE")
print("="*60)

