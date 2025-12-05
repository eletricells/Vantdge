"""
PaperScope V2 Database Interface

Service class for saving and retrieving PaperScope V2 results.
Stores comprehensive paper catalogs with web search results, detailed summaries, and ongoing trials.
"""
import psycopg2
from psycopg2.extras import Json, RealDictCursor
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class PaperScopeV2Database:
    """
    Database interface for PaperScope V2 results.
    
    Handles CRUD operations for:
    - Drug searches (metadata about each search)
    - Papers (categorized papers with detailed summaries)
    - Ongoing trials (recruiting/active trials from ClinicalTrials.gov)
    - Paper sources (tracking where papers came from)
    """
    
    def __init__(self, database_url: str):
        """
        Initialize PaperScope V2 database connection.
        
        Args:
            database_url: PostgreSQL connection string
        """
        self.database_url = database_url
        self.connection = None
    
    @property
    def conn(self):
        """Alias for connection."""
        return self.connection
    
    def connect(self):
        """Establish database connection."""
        try:
            self.connection = psycopg2.connect(self.database_url)
            logger.info("Connected to PaperScope V2 database")
        except Exception as e:
            logger.error(f"Failed to connect to PaperScope V2 database: {e}")
            raise
    
    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Closed PaperScope V2 database connection")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
    
    def create_tables(self):
        """Create PaperScope V2 tables if they don't exist."""
        try:
            with self.connection.cursor() as cursor:
                # Drug searches table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS paperscope_v2_searches (
                        search_id SERIAL PRIMARY KEY,
                        drug_name VARCHAR(255) NOT NULL,
                        disease_indication VARCHAR(500),
                        drug_class VARCHAR(255),
                        search_date TIMESTAMP DEFAULT NOW(),
                        total_papers INTEGER,
                        total_ongoing_trials INTEGER,
                        paper_sources JSONB,
                        elapsed_seconds NUMERIC,
                        search_log JSONB,
                        UNIQUE(drug_name, search_date)
                    )
                """)
                
                # Papers table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS paperscope_v2_papers (
                        paper_id SERIAL PRIMARY KEY,
                        search_id INTEGER REFERENCES paperscope_v2_searches(search_id) ON DELETE CASCADE,
                        pmid VARCHAR(50),
                        title TEXT NOT NULL,
                        authors TEXT,
                        journal VARCHAR(500),
                        year INTEGER,
                        abstract TEXT,
                        detailed_summary TEXT,
                        structured_summary JSONB,
                        key_takeaways JSONB,
                        categories JSONB,
                        source VARCHAR(100),
                        links JSONB,
                        primary_link TEXT,
                        doi VARCHAR(255),
                        pmc VARCHAR(50),
                        trial_name VARCHAR(255),
                        drug_relevance_score NUMERIC(3,2),
                        content TEXT,
                        tables JSONB,
                        sections JSONB,
                        metadata JSONB,
                        created_at TIMESTAMP DEFAULT NOW(),
                        updated_at TIMESTAMP DEFAULT NOW(),
                        CONSTRAINT unique_paper_per_search UNIQUE (search_id, pmid)
                    )
                """)
                
                # Create index on pmid for faster lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_pmid
                    ON paperscope_v2_papers(pmid)
                """)

                # Create index on search_id for faster joins
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_search_id
                    ON paperscope_v2_papers(search_id)
                """)

                # Create index on trial_name for faster lookups
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_trial_name
                    ON paperscope_v2_papers(trial_name)
                """)

                # Create index on drug_relevance_score for filtering
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paperscope_v2_papers_relevance
                    ON paperscope_v2_papers(drug_relevance_score)
                """)
                
                # Ongoing trials table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS paperscope_v2_ongoing_trials (
                        trial_id SERIAL PRIMARY KEY,
                        search_id INTEGER REFERENCES paperscope_v2_searches(search_id) ON DELETE CASCADE,
                        nct_id VARCHAR(50) NOT NULL,
                        title TEXT,
                        phase VARCHAR(50),
                        status VARCHAR(100),
                        enrollment INTEGER,
                        start_date DATE,
                        completion_date DATE,
                        primary_completion_date DATE,
                        conditions JSONB,
                        interventions JSONB,
                        url TEXT,
                        created_at TIMESTAMP DEFAULT NOW()
                    )
                """)
                
                # Create index on nct_id
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_paperscope_v2_ongoing_trials_nct_id 
                    ON paperscope_v2_ongoing_trials(nct_id)
                """)
                
                self.connection.commit()
                logger.info("PaperScope V2 tables created successfully")
                
        except Exception as e:
            logger.error(f"Error creating PaperScope V2 tables: {e}")
            self.connection.rollback()
            raise
    
    def save_search(
        self,
        drug_name: str,
        results: Dict[str, Any]
    ) -> int:
        """
        Save a PaperScope V2 search and all associated data.
        
        Args:
            drug_name: Drug name
            results: Complete results dictionary from PaperScopeV2Agent
            
        Returns:
            search_id of the saved search
        """
        try:
            with self.connection.cursor() as cursor:
                metadata = results.get('metadata', {})
                
                # Insert search record
                cursor.execute("""
                    INSERT INTO paperscope_v2_searches (
                        drug_name,
                        disease_indication,
                        drug_class,
                        total_papers,
                        total_ongoing_trials,
                        paper_sources,
                        elapsed_seconds,
                        search_log,
                        discovered_trial_names,
                        discovered_indications,
                        filtered_papers_count
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING search_id
                """, (
                    drug_name,
                    metadata.get('disease_indication'),
                    metadata.get('drug_class'),
                    metadata.get('total_unique_papers', 0),
                    metadata.get('ongoing_trials_count', 0),
                    Json(metadata.get('paper_sources', {})),
                    metadata.get('elapsed_seconds'),
                    Json(results.get('search_log', [])),
                    Json(results.get('discovered_trial_names', [])),
                    Json(results.get('discovered_indications', [])),
                    metadata.get('filtered_papers_count', 0)
                ))

                search_id = cursor.fetchone()[0]

                # Collect unique papers (deduplicate across categories)
                unique_papers = {}
                categorized_papers = results.get('categorized_papers', {})

                for category, papers in categorized_papers.items():
                    for paper in papers:
                        pmid = paper.get('pmid')
                        if pmid:
                            if pmid not in unique_papers:
                                unique_papers[pmid] = paper.copy()
                                unique_papers[pmid]['categories'] = []
                            unique_papers[pmid]['categories'].append(category)

                # Save each paper once with all categories
                for paper in unique_papers.values():
                    self._save_paper(cursor, search_id, paper)
                
                # Save ongoing trials
                ongoing_trials = results.get('ongoing_trials', [])
                for trial in ongoing_trials:
                    self._save_ongoing_trial(cursor, search_id, trial)
                
                self.connection.commit()
                logger.info(f"Saved PaperScope V2 search for {drug_name} (search_id={search_id}, {len(unique_papers)} unique papers)")
                return search_id
                
        except Exception as e:
            logger.error(f"Error saving PaperScope V2 search: {e}")
            self.connection.rollback()
            raise
    
    def _save_paper(
        self,
        cursor,
        search_id: int,
        paper: Dict[str, Any],
        category: str = None  # Now optional since categories come from paper dict
    ):
        """
        Save a single paper with deduplication support.

        Uses INSERT ... ON CONFLICT to handle duplicates.
        If paper already exists for this search, updates categories array.
        """
        # Get categories from paper dict (already collected in save_search)
        categories = paper.get('categories', [category] if category else [])

        # Extract indication from structured_summary if available
        indication = None
        structured_summary = paper.get('structured_summary', {})
        if isinstance(structured_summary, dict):
            indication = structured_summary.get('indication')

        # Sanitize year field - must be integer or None
        year = paper.get('year')
        if year is not None:
            if isinstance(year, str):
                # Try to convert string to int
                if year.isdigit():
                    year = int(year)
                else:
                    # Invalid year string (e.g., "Not specified")
                    year = None
            elif not isinstance(year, int):
                year = None

        # Sanitize drug_relevance_score - must be numeric or None
        drug_relevance_score = paper.get('drug_relevance_score')
        if drug_relevance_score is not None:
            if isinstance(drug_relevance_score, str):
                try:
                    drug_relevance_score = float(drug_relevance_score)
                except (ValueError, TypeError):
                    drug_relevance_score = None
            elif not isinstance(drug_relevance_score, (int, float)):
                drug_relevance_score = None

        cursor.execute("""
            INSERT INTO paperscope_v2_papers (
                search_id,
                pmid,
                title,
                authors,
                journal,
                year,
                abstract,
                detailed_summary,
                structured_summary,
                key_takeaways,
                categories,
                source,
                links,
                primary_link,
                doi,
                pmc,
                trial_name,
                indication,
                drug_relevance_score,
                content,
                tables,
                sections,
                metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (search_id, pmid)
            DO UPDATE SET
                categories = EXCLUDED.categories,
                indication = EXCLUDED.indication,
                content = COALESCE(EXCLUDED.content, paperscope_v2_papers.content),
                tables = COALESCE(EXCLUDED.tables, paperscope_v2_papers.tables),
                sections = COALESCE(EXCLUDED.sections, paperscope_v2_papers.sections),
                metadata = COALESCE(EXCLUDED.metadata, paperscope_v2_papers.metadata),
                updated_at = NOW()
        """, (
            search_id,
            paper.get('pmid'),
            paper.get('title'),
            paper.get('authors'),
            paper.get('journal'),
            year,
            paper.get('abstract'),
            paper.get('detailed_summary'),
            Json(paper.get('structured_summary', {})),
            Json(paper.get('key_takeaways', [])),
            Json(categories),
            paper.get('source'),
            Json(paper.get('links', [])),
            paper.get('primary_link'),
            paper.get('doi'),
            paper.get('pmc'),
            paper.get('trial_name'),
            indication,
            drug_relevance_score,
            paper.get('content'),
            Json(paper.get('tables', [])) if paper.get('tables') else None,
            Json(paper.get('sections', {})) if paper.get('sections') else None,
            Json(paper.get('metadata', {})) if paper.get('metadata') else None
        ))
    
    def _save_ongoing_trial(
        self,
        cursor,
        search_id: int,
        trial: Dict[str, Any]
    ):
        """Save a single ongoing trial."""
        cursor.execute("""
            INSERT INTO paperscope_v2_ongoing_trials (
                search_id,
                nct_id,
                title,
                phase,
                status,
                enrollment,
                start_date,
                completion_date,
                primary_completion_date,
                conditions,
                interventions,
                url
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            search_id,
            trial.get('nct_id'),
            trial.get('title'),
            trial.get('phase'),
            trial.get('status'),
            trial.get('enrollment'),
            trial.get('start_date'),
            trial.get('completion_date'),
            trial.get('primary_completion_date'),
            Json(trial.get('conditions', [])),
            Json(trial.get('interventions', [])),
            trial.get('url')
        ))

    def get_search_by_drug(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent search for a drug.

        Args:
            drug_name: Drug name

        Returns:
            Search record or None
        """
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM paperscope_v2_searches
                    WHERE drug_name = %s
                    ORDER BY search_date DESC
                    LIMIT 1
                """, (drug_name,))

                return cursor.fetchone()

        except Exception as e:
            logger.error(f"Error getting search for {drug_name}: {e}")
            return None

    def get_all_searches(self) -> List[Dict[str, Any]]:
        """
        Get all searches ordered by date.

        Returns:
            List of search records
        """
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM paperscope_v2_searches
                    ORDER BY search_date DESC
                """)

                results = cursor.fetchall()
                return results if results is not None else []

        except Exception as e:
            logger.error(f"Error getting all searches: {e}")
            return []

    def get_papers_by_search_id(self, search_id: int) -> List[Dict[str, Any]]:
        """
        Get all papers for a search.

        Args:
            search_id: Search ID

        Returns:
            List of paper records
        """
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM paperscope_v2_papers
                    WHERE search_id = %s
                    ORDER BY year DESC, title
                """, (search_id,))

                results = cursor.fetchall()
                return results if results is not None else []

        except Exception as e:
            logger.error(f"Error getting papers for search_id {search_id}: {e}")
            return []

    def get_ongoing_trials_by_search_id(self, search_id: int) -> List[Dict[str, Any]]:
        """
        Get all ongoing trials for a search.

        Args:
            search_id: Search ID

        Returns:
            List of trial records
        """
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM paperscope_v2_ongoing_trials
                    WHERE search_id = %s
                    ORDER BY phase, nct_id
                """, (search_id,))

                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error getting ongoing trials for search_id {search_id}: {e}")
            return []

    def delete_search(self, search_id: int):
        """
        Delete a search and all associated data.

        Args:
            search_id: Search ID
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM paperscope_v2_searches
                    WHERE search_id = %s
                """, (search_id,))

                self.connection.commit()
                logger.info(f"Deleted search {search_id}")

        except Exception as e:
            logger.error(f"Error deleting search {search_id}: {e}")
            self.connection.rollback()
            raise

    def get_papers_by_category(
        self,
        search_id: int,
        category: str
    ) -> List[Dict[str, Any]]:
        """
        Get papers in a specific category.

        Args:
            search_id: Search ID
            category: Category name

        Returns:
            List of paper records
        """
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    SELECT * FROM paperscope_v2_papers
                    WHERE search_id = %s
                    AND categories @> %s::jsonb
                    ORDER BY year DESC, title
                """, (search_id, json.dumps([category])))

                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error getting papers for category {category}: {e}")
            return []

    def get_papers_without_content(
        self,
        search_id: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get papers that don't have full-text content yet.

        Useful for backfilling content for existing papers.

        Args:
            search_id: Optional search ID to filter by
            limit: Optional limit on number of papers to return

        Returns:
            List of paper records without content
        """
        try:
            with self.connection.cursor(cursor_factory=RealDictCursor) as cursor:
                query = """
                    SELECT * FROM paperscope_v2_papers
                    WHERE content IS NULL
                    AND pmid IS NOT NULL
                """
                params = []

                if search_id:
                    query += " AND search_id = %s"
                    params.append(search_id)

                query += " ORDER BY year DESC, paper_id"

                if limit:
                    query += " LIMIT %s"
                    params.append(limit)

                cursor.execute(query, params)
                return cursor.fetchall()

        except Exception as e:
            logger.error(f"Error getting papers without content: {e}")
            return []

    def update_paper_content(
        self,
        paper_id: int,
        content: Optional[str] = None,
        tables: Optional[List[Dict[str, Any]]] = None,
        sections: Optional[Dict[str, str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update full-text content and related fields for a paper.

        Used for backfilling content for existing papers.

        Args:
            paper_id: Paper ID
            content: Full-text content
            tables: Extracted tables
            sections: Structured sections
            metadata: Extraction metadata

        Returns:
            True if update successful, False otherwise
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE paperscope_v2_papers
                    SET
                        content = COALESCE(%s, content),
                        tables = COALESCE(%s, tables),
                        sections = COALESCE(%s, sections),
                        metadata = COALESCE(%s, metadata),
                        updated_at = NOW()
                    WHERE paper_id = %s
                """, (
                    content,
                    Json(tables) if tables else None,
                    Json(sections) if sections else None,
                    Json(metadata) if metadata else None,
                    paper_id
                ))

                self.connection.commit()
                logger.info(f"Updated content for paper_id {paper_id}")
                return True

        except Exception as e:
            logger.error(f"Error updating paper content: {e}")
            self.connection.rollback()
            return False

