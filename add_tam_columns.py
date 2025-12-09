"""
Migration script to add tam_usd, tam_rationale, and competitive_landscape columns
to cs_market_intelligence table.

Run this script to update the Railway database schema.
"""

import os
import psycopg2
from psycopg2 import sql

def add_columns():
    """Add missing columns to cs_market_intelligence table."""
    
    # Get database URL from environment
    database_url = os.environ.get('DISEASE_LANDSCAPE_URL')
    if not database_url:
        print("❌ Error: DISEASE_LANDSCAPE_URL environment variable not set")
        return False
    
    try:
        # Connect to database
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        
        print("✅ Connected to database")
        
        # Check if columns already exist
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'cs_market_intelligence'
            AND column_name IN ('tam_usd', 'tam_rationale', 'competitive_landscape')
        """)
        existing_columns = [row[0] for row in cur.fetchall()]
        
        print(f"📋 Existing columns: {existing_columns}")
        
        # Add tam_usd column if it doesn't exist
        if 'tam_usd' not in existing_columns:
            print("➕ Adding tam_usd column...")
            cur.execute("""
                ALTER TABLE cs_market_intelligence 
                ADD COLUMN tam_usd BIGINT
            """)
            print("✅ Added tam_usd column")
        else:
            print("⏭️  tam_usd column already exists")
        
        # Add tam_rationale column if it doesn't exist
        if 'tam_rationale' not in existing_columns:
            print("➕ Adding tam_rationale column...")
            cur.execute("""
                ALTER TABLE cs_market_intelligence 
                ADD COLUMN tam_rationale TEXT
            """)
            print("✅ Added tam_rationale column")
        else:
            print("⏭️  tam_rationale column already exists")
        
        # Add competitive_landscape column if it doesn't exist
        if 'competitive_landscape' not in existing_columns:
            print("➕ Adding competitive_landscape column...")
            cur.execute("""
                ALTER TABLE cs_market_intelligence 
                ADD COLUMN competitive_landscape TEXT
            """)
            print("✅ Added competitive_landscape column")
        else:
            print("⏭️  competitive_landscape column already exists")
        
        # Commit changes
        conn.commit()
        print("✅ Migration completed successfully!")
        
        # Verify columns were added
        cur.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'cs_market_intelligence'
            AND column_name IN ('tam_usd', 'tam_rationale', 'competitive_landscape')
            ORDER BY column_name
        """)
        
        print("\n📊 Final column status:")
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[1]}")
        
        cur.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == '__main__':
    print("🚀 Starting database migration...")
    print("=" * 60)
    success = add_columns()
    print("=" * 60)
    if success:
        print("✅ Migration completed successfully!")
    else:
        print("❌ Migration failed!")

