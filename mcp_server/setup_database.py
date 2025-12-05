"""
Database Setup Script

Initializes the MCP database schema and optionally loads sample data.
"""
import argparse
import logging
from pathlib import Path
from sqlalchemy import create_engine, text


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def setup_database(database_url: str, load_sample_data: bool = False):
    """
    Set up the MCP database.

    Args:
        database_url: SQLAlchemy database URL
        load_sample_data: Whether to load sample data
    """
    logger.info(f"Connecting to database...")
    engine = create_engine(database_url)

    # Read schema file
    schema_path = Path(__file__).parent / "database_schema.sql"
    logger.info(f"Reading schema from {schema_path}")

    with open(schema_path, 'r') as f:
        schema_sql = f.read()

    # Execute schema
    logger.info("Creating database schema...")
    with engine.begin() as conn:
        # Split by semicolon and execute each statement
        for statement in schema_sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    conn.execute(text(statement))
                except Exception as e:
                    logger.warning(f"Statement failed (may already exist): {str(e)[:100]}")

    logger.info("✅ Database schema created successfully")

    # Load sample data if requested
    if load_sample_data:
        sample_data_path = Path(__file__).parent / "sample_data.sql"
        logger.info(f"Reading sample data from {sample_data_path}")

        with open(sample_data_path, 'r') as f:
            sample_sql = f.read()

        logger.info("Loading sample data...")
        with engine.begin() as conn:
            for statement in sample_sql.split(';'):
                statement = statement.strip()
                if statement and not statement.startswith('--'):
                    try:
                        conn.execute(text(statement))
                    except Exception as e:
                        logger.warning(f"Insert failed (may already exist): {str(e)[:100]}")

        logger.info("✅ Sample data loaded successfully")

    engine.dispose()
    logger.info("Database setup complete!")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Set up MCP database")
    parser.add_argument(
        "--database-url",
        type=str,
        required=True,
        help="SQLAlchemy database URL (e.g., postgresql://user:pass@localhost/dbname)"
    )
    parser.add_argument(
        "--load-sample-data",
        action="store_true",
        help="Load sample data into the database"
    )

    args = parser.parse_args()

    setup_database(args.database_url, args.load_sample_data)


if __name__ == "__main__":
    main()
