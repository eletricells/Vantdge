"""
Drug Extraction System - Main Entry Point

Usage:
    python -m src.drug_extraction_system.main --csv drugs.csv
    python -m src.drug_extraction_system.main --drug "upadacitinib"
    python -m src.drug_extraction_system.main --setup-db
"""

import argparse
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.drug_extraction_system.config import get_config, load_config
from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.processors.drug_processor import DrugProcessor
from src.drug_extraction_system.processors.batch_processor import BatchProcessor
from src.drug_extraction_system.utils.logger import setup_logger, get_logger


def setup_database(db: DatabaseConnection):
    """Run database setup/migration scripts with tracking."""
    logger = get_logger()
    logger.info("Setting up database schema...")

    # Read and execute schema SQL
    schema_dir = Path(__file__).parent / "database"

    # Execute main schema (always idempotent with IF NOT EXISTS)
    schema_file = schema_dir / "schema.sql"
    if schema_file.exists():
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        with db.cursor() as cur:
            cur.execute(schema_sql)
        db.commit()
        logger.info("Main schema executed successfully")

    # Get already-applied migrations
    with db.cursor() as cur:
        cur.execute("SELECT migration_name FROM schema_migrations")
        applied = {row[0] for row in cur.fetchall()}

    if applied:
        logger.info(f"Found {len(applied)} already-applied migrations")

    # Execute only NEW migrations
    migrations_dir = schema_dir / "migrations"
    if migrations_dir.exists():
        migration_files = sorted(migrations_dir.glob("*.sql"))
        new_migrations = [f for f in migration_files if f.name not in applied]

        if not new_migrations:
            logger.info("No new migrations to apply")
        else:
            logger.info(f"Applying {len(new_migrations)} new migration(s)")

            for migration_file in new_migrations:
                migration_name = migration_file.name
                logger.info(f"Running migration: {migration_name}")

                with open(migration_file, 'r') as f:
                    migration_sql = f.read()

                with db.cursor() as cur:
                    cur.execute(migration_sql)
                    cur.execute(
                        "INSERT INTO schema_migrations (migration_name) VALUES (%s)",
                        (migration_name,)
                    )
                db.commit()
                logger.info(f"Migration {migration_name} completed")

    logger.info("Database setup complete")


def process_single_drug(drug_name: str, force_refresh: bool = False):
    """Process a single drug."""
    logger = get_logger()
    config = get_config()

    with DatabaseConnection() as db:
        processor = DrugProcessor(db=db)
        result = processor.process(drug_name, force_refresh=force_refresh)

        logger.info(f"\nResult for '{drug_name}':")
        logger.info(f"  Status: {result.status.value}")
        logger.info(f"  Drug Key: {result.drug_key or 'N/A'}")
        logger.info(f"  Drug ID: {result.drug_id}")
        completeness = result.completeness_score or 0
        logger.info(f"  Completeness: {completeness:.2%}")
        logger.info(f"  Data Sources: {', '.join(result.data_sources) if result.data_sources else 'N/A'}")

        if result.error:
            logger.error(f"  Error: {result.error}")

        return result


def process_csv(csv_path: str, drug_column: str = "drug_name", force_refresh: bool = False):
    """Process drugs from CSV file."""
    logger = get_logger()
    config = get_config()

    with DatabaseConnection() as db:
        processor = BatchProcessor(
            db=db,
            max_workers=config.processing.max_workers,
            batch_size=config.processing.batch_size
        )

        result = processor.process_csv(
            csv_path=csv_path,
            drug_name_column=drug_column,
            force_refresh=force_refresh
        )

        logger.info(f"\n{'='*60}")
        logger.info("BATCH PROCESSING SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"  Batch ID: {result.batch_id}")
        logger.info(f"  CSV File: {result.csv_file}")
        logger.info(f"  Total Drugs: {result.total}")
        logger.info(f"  Successful: {result.successful}")
        logger.info(f"  Partial: {result.partial}")
        logger.info(f"  Failed: {result.failed}")
        logger.info(f"  Skipped: {result.skipped}")
        logger.info(f"  Duration: {result.completed_at - result.started_at}")
        logger.info(f"{'='*60}")

        if result.errors:
            logger.warning(f"\nErrors ({len(result.errors)}):")
            for err in result.errors[:10]:
                logger.warning(f"  - {err['drug']}: {err['error']}")

        return result


def run_health_check():
    """Check all system components and connectivity."""
    logger = get_logger()
    config = get_config()

    logger.info("\n" + "="*60)
    logger.info("SYSTEM HEALTH CHECK")
    logger.info("="*60 + "\n")

    results = {
        'database': False,
        'openfda': False,
        'dailymed': False,
        'clinicaltrials': False,
        'rxnorm': False,
        'mesh': False,
        'anthropic': False,
        'tavily': False,
    }

    # Check database
    logger.info("Checking Database...")
    try:
        with DatabaseConnection() as db:
            with db.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        results['database'] = True
        logger.info("  ✓ Database: Connected")
    except Exception as e:
        logger.error(f"  ✗ Database: {e}")

    # Check OpenFDA
    logger.info("\nChecking OpenFDA API...")
    try:
        from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
        client = OpenFDAClient()
        if client.health_check():
            results['openfda'] = True
            logger.info("  ✓ OpenFDA: Accessible")
        else:
            logger.error("  ✗ OpenFDA: Health check failed")
    except Exception as e:
        logger.error(f"  ✗ OpenFDA: {e}")

    # Check DailyMed
    logger.info("\nChecking DailyMed API...")
    try:
        from src.tools.dailymed import DailyMedAPI
        client = DailyMedAPI()
        # Try a simple search
        test_result = client.search_drug("aspirin")
        if test_result:
            results['dailymed'] = True
            logger.info("  ✓ DailyMed: Accessible")
        else:
            logger.warning("  ⚠ DailyMed: No results for test query")
    except Exception as e:
        logger.error(f"  ✗ DailyMed: {e}")

    # Check ClinicalTrials.gov
    logger.info("\nChecking ClinicalTrials.gov API...")
    try:
        from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
        client = ClinicalTrialsClient()
        if client.health_check():
            results['clinicaltrials'] = True
            logger.info("  ✓ ClinicalTrials.gov: Accessible")
        else:
            logger.error("  ✗ ClinicalTrials.gov: Health check failed")
    except Exception as e:
        logger.error(f"  ✗ ClinicalTrials.gov: {e}")

    # Check RxNorm
    logger.info("\nChecking RxNorm API...")
    try:
        from src.drug_extraction_system.api_clients.rxnorm_client import RxNormClient
        client = RxNormClient()
        if client.health_check():
            results['rxnorm'] = True
            logger.info("  ✓ RxNorm: Accessible")
        else:
            logger.error("  ✗ RxNorm: Health check failed")
    except Exception as e:
        logger.error(f"  ✗ RxNorm: {e}")

    # Check MeSH
    logger.info("\nChecking MeSH API...")
    try:
        from src.drug_extraction_system.api_clients.mesh_client import MeSHClient
        client = MeSHClient()
        if client.health_check():
            results['mesh'] = True
            logger.info("  ✓ MeSH: Accessible")
        else:
            logger.error("  ✗ MeSH: Health check failed")
    except Exception as e:
        logger.error(f"  ✗ MeSH: {e}")

    # Check Anthropic (Claude)
    logger.info("\nChecking Anthropic API...")
    try:
        import anthropic
        import os
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("  ✗ Anthropic: ANTHROPIC_API_KEY not set")
        else:
            client = anthropic.Anthropic(api_key=api_key)
            # Simple test message
            response = client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=10,
                messages=[{"role": "user", "content": "test"}]
            )
            if response:
                results['anthropic'] = True
                logger.info("  ✓ Anthropic: Accessible")
    except Exception as e:
        logger.error(f"  ✗ Anthropic: {e}")

    # Check Tavily (optional)
    logger.info("\nChecking Tavily API...")
    try:
        import os
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            logger.warning("  ⚠ Tavily: TAVILY_API_KEY not set (optional)")
        else:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            # Simple test search
            result = client.search("test", max_results=1)
            if result:
                results['tavily'] = True
                logger.info("  ✓ Tavily: Accessible")
    except Exception as e:
        logger.warning(f"  ⚠ Tavily: {e} (optional)")

    # Summary
    logger.info("\n" + "="*60)
    critical_services = ['database', 'openfda', 'clinicaltrials', 'anthropic']
    critical_healthy = all(results[s] for s in critical_services)
    all_healthy = all(results.values())

    logger.info("HEALTH CHECK SUMMARY")
    logger.info("="*60)
    logger.info(f"Critical Services: {'PASSED ✓' if critical_healthy else 'FAILED ✗'}")
    logger.info(f"All Services: {'PASSED ✓' if all_healthy else 'PARTIAL ⚠'}")
    logger.info(f"\nServices Status:")
    for service, status in results.items():
        symbol = "✓" if status else "✗"
        logger.info(f"  {symbol} {service.upper()}")
    logger.info("="*60 + "\n")

    return 0 if critical_healthy else 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Drug Extraction System - Extract and store drug data"
    )

    parser.add_argument("--csv", type=str, help="Path to CSV file with drug names")
    parser.add_argument("--drug", type=str, help="Single drug name to process")
    parser.add_argument("--column", type=str, default="drug_name",
                        help="Column name in CSV containing drug names")
    parser.add_argument("--refresh", action="store_true",
                        help="Force refresh existing drugs")
    parser.add_argument("--setup-db", action="store_true",
                        help="Run database setup/migrations")
    parser.add_argument("--health-check", action="store_true",
                        help="Check system health and connectivity to all services")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    # Setup logging
    import logging
    setup_logger(level=getattr(logging, args.log_level))
    logger = get_logger()

    # Load config
    load_config()

    try:
        if args.setup_db:
            with DatabaseConnection() as db:
                setup_database(db)

        elif args.health_check:
            exit_code = run_health_check()
            sys.exit(exit_code)

        elif args.csv:
            process_csv(args.csv, args.column, args.refresh)

        elif args.drug:
            process_single_drug(args.drug, args.refresh)

        else:
            parser.print_help()
            sys.exit(1)

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

