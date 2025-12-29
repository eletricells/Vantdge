"""
Batch Processor

Processes multiple drugs from CSV input with parallel execution.
"""

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

from src.drug_extraction_system.processors.drug_processor import DrugProcessor, ProcessingResult, ProcessingStatus
from src.drug_extraction_system.database.connection import DatabaseConnection
from src.drug_extraction_system.database.operations import DrugDatabaseOperations
from src.drug_extraction_system.config import get_config
from src.drug_extraction_system.utils.logger import log_batch_start, log_batch_end, log_drug_processing

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    """Result of batch processing."""
    batch_id: str
    csv_file: str
    total: int = 0
    successful: int = 0
    partial: int = 0
    failed: int = 0
    skipped: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    results: List[ProcessingResult] = field(default_factory=list)
    errors: List[Dict] = field(default_factory=list)


class BatchProcessor:
    """
    Processes batches of drugs from CSV files.
    
    Features:
    - Parallel processing with ThreadPoolExecutor
    - Progress tracking and logging
    - Error aggregation
    - Database batch logging
    """

    def __init__(
        self,
        db: Optional[DatabaseConnection] = None,
        max_workers: int = 5,
        batch_size: int = 10,
        continue_on_error: bool = True
    ):
        """
        Initialize batch processor.

        Args:
            db: Database connection
            max_workers: Max parallel workers
            batch_size: Number of drugs per batch
            continue_on_error: If True, continue processing after errors
        """
        self.config = get_config()
        self.max_workers = max_workers or self.config.processing.max_workers
        self.batch_size = batch_size or self.config.processing.batch_size
        self.continue_on_error = continue_on_error

        # Initialize database
        self.db = db
        self.db_ops = DrugDatabaseOperations(db) if db else None

    def process_csv(
        self,
        csv_path: str,
        drug_name_column: str = "drug_name",
        force_refresh: bool = False,
        resume: bool = True
    ) -> BatchResult:
        """
        Process drugs from a CSV file with checkpointing support.

        Args:
            csv_path: Path to CSV file
            drug_name_column: Column name containing drug names
            force_refresh: If True, refresh existing drugs
            resume: If True, resume from last checkpoint if available

        Returns:
            BatchResult with processing summary
        """
        # Read drug names from CSV
        drug_names = self._read_csv(csv_path, drug_name_column)

        if not drug_names:
            logger.warning(f"No drugs found in CSV: {csv_path}")
            return BatchResult(batch_id=str(uuid4()), csv_file=csv_path, total=0)

        # Generate batch ID from CSV path for consistency
        batch_id = self._generate_batch_id(csv_path)

        # Check for existing checkpoint
        checkpoint = None
        start_index = 0
        if resume and self.db:
            checkpoint = self._load_checkpoint(batch_id)
            if checkpoint and checkpoint['status'] == 'in_progress':
                start_index = checkpoint['last_processed_index'] + 1
                logger.info(f"Resuming batch {batch_id} from index {start_index}/{len(drug_names)}")

        # Create result object
        result = BatchResult(batch_id=batch_id, csv_file=csv_path, total=len(drug_names))

        # Create or update checkpoint
        if self.db:
            if not checkpoint:
                self._create_checkpoint(batch_id, csv_path, len(drug_names))
            else:
                # Update checkpoint to in_progress if it was failed/interrupted
                self._update_checkpoint_status(batch_id, 'in_progress')

        log_batch_start(batch_id, csv_path, len(drug_names))

        # Log batch start in database
        if self.db_ops:
            try:
                from uuid import UUID
                self.db_ops.log_process_start(UUID(batch_id), csv_path, len(drug_names))
            except Exception as e:
                logger.warning(f"Failed to log batch start: {e}")

        # Process drugs starting from checkpoint
        try:
            for i in range(start_index, len(drug_names)):
                drug_name = drug_names[i]

                try:
                    # Create processor for each drug
                    processor = DrugProcessor(db=self.db)
                    drug_result = processor.process(drug_name, force_refresh, batch_id)
                    result.results.append(drug_result)

                    # Update counts
                    if drug_result.status == ProcessingStatus.SUCCESS:
                        result.successful += 1
                    elif drug_result.status == ProcessingStatus.PARTIAL:
                        result.partial += 1
                    elif drug_result.status == ProcessingStatus.SKIPPED:
                        result.skipped += 1
                    else:
                        result.failed += 1
                        if drug_result.error:
                            result.errors.append({"drug": drug_name, "error": drug_result.error})

                    # Update checkpoint after each drug
                    if self.db:
                        self._update_checkpoint(batch_id, i, result.successful + result.partial + result.failed + result.skipped)

                    # Log progress every 10 drugs
                    if (i + 1) % 10 == 0 or (i + 1) == len(drug_names):
                        logger.info(f"Progress: {i + 1}/{len(drug_names)} drugs processed")

                except Exception as e:
                    logger.error(f"Failed to process '{drug_name}': {e}")
                    result.failed += 1
                    result.errors.append({"drug": drug_name, "error": str(e)})

                    # Update checkpoint with error
                    if self.db:
                        self._update_checkpoint(batch_id, i, result.successful + result.partial + result.failed + result.skipped, error=str(e))

                    if not self.continue_on_error:
                        raise

        except KeyboardInterrupt:
            logger.warning("Batch processing interrupted by user")
            if self.db:
                self._update_checkpoint_status(batch_id, 'interrupted')
            raise

        result.completed_at = datetime.now()

        # Mark checkpoint as complete
        if self.db:
            self._complete_checkpoint(batch_id)

        # Log batch end
        log_batch_end(batch_id, {
            "total": result.total,
            "successful": result.successful,
            "partial": result.partial,
            "failed": result.failed,
            "skipped": result.skipped,
        })

        # Log batch end in database
        if self.db_ops:
            try:
                from uuid import UUID
                self.db_ops.log_process_end(
                    UUID(batch_id),
                    result.successful,
                    result.partial,
                    result.failed,
                    {"errors": result.errors[:100]}  # Limit stored errors
                )
            except Exception as e:
                logger.warning(f"Failed to log batch end: {e}")

        return result

    def _read_csv(self, csv_path: str, drug_name_column: str) -> List[str]:
        """Read drug names from CSV file."""
        drug_names = []
        path = Path(csv_path)

        if not path.exists():
            logger.error(f"CSV file not found: {csv_path}")
            return []

        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                if drug_name_column not in reader.fieldnames:
                    logger.error(f"Column '{drug_name_column}' not found in CSV")
                    return []

                for row in reader:
                    name = row.get(drug_name_column, "").strip()
                    if name:
                        drug_names.append(name)

        except Exception as e:
            logger.error(f"Failed to read CSV: {e}")

        return drug_names

    def _process_batch(
        self,
        drug_names: List[str],
        batch_id: str,
        force_refresh: bool
    ) -> List[ProcessingResult]:
        """Process a batch of drugs in parallel."""
        results = []

        # Create processor for this batch
        processor = DrugProcessor(db=self.db)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(processor.process, name, force_refresh, batch_id): name
                for name in drug_names
            }

            for future in as_completed(futures):
                drug_name = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    log_drug_processing(
                        result.drug_name,
                        result.status.value,
                        result.completeness_score,
                        result.error
                    )
                except Exception as e:
                    logger.error(f"Exception processing '{drug_name}': {e}")
                    results.append(ProcessingResult(
                        drug_name=drug_name,
                        status=ProcessingStatus.FAILED,
                        error=str(e)
                    ))

        return results

    def _generate_batch_id(self, csv_path: str) -> str:
        """Generate consistent batch ID from CSV path."""
        import hashlib
        path_hash = hashlib.md5(csv_path.encode()).hexdigest()[:8]
        return f"batch_{path_hash}"

    def _create_checkpoint(self, batch_id: str, csv_file: str, total_drugs: int):
        """Create a new checkpoint record."""
        if not self.db:
            return

        try:
            with self.db.get_cursor() as cur:
                cur.execute("""
                    INSERT INTO batch_checkpoints
                    (batch_id, csv_file, total_drugs, status, started_at, updated_at)
                    VALUES (%s, %s, %s, 'in_progress', NOW(), NOW())
                    ON CONFLICT (batch_id) DO UPDATE
                    SET status = 'in_progress', updated_at = NOW()
                """, (batch_id, csv_file, total_drugs))
            logger.info(f"Created checkpoint for batch {batch_id}")
        except Exception as e:
            logger.warning(f"Failed to create checkpoint: {e}")

    def _load_checkpoint(self, batch_id: str) -> Optional[Dict]:
        """Load existing checkpoint."""
        if not self.db:
            return None

        try:
            with self.db.get_cursor() as cur:
                cur.execute("""
                    SELECT batch_id, csv_file, total_drugs, processed_drugs,
                           last_processed_index, status, started_at, error_message
                    FROM batch_checkpoints
                    WHERE batch_id = %s
                """, (batch_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None

    def _update_checkpoint(self, batch_id: str, last_index: int, processed_count: int, error: Optional[str] = None):
        """Update checkpoint progress."""
        if not self.db:
            return

        try:
            with self.db.get_cursor() as cur:
                if error:
                    cur.execute("""
                        UPDATE batch_checkpoints
                        SET last_processed_index = %s,
                            processed_drugs = %s,
                            error_message = %s,
                            updated_at = NOW()
                        WHERE batch_id = %s
                    """, (last_index, processed_count, error, batch_id))
                else:
                    cur.execute("""
                        UPDATE batch_checkpoints
                        SET last_processed_index = %s,
                            processed_drugs = %s,
                            updated_at = NOW()
                        WHERE batch_id = %s
                    """, (last_index, processed_count, batch_id))
        except Exception as e:
            logger.warning(f"Failed to update checkpoint: {e}")

    def _update_checkpoint_status(self, batch_id: str, status: str):
        """Update checkpoint status."""
        if not self.db:
            return

        try:
            with self.db.get_cursor() as cur:
                cur.execute("""
                    UPDATE batch_checkpoints
                    SET status = %s, updated_at = NOW()
                    WHERE batch_id = %s
                """, (status, batch_id))
        except Exception as e:
            logger.warning(f"Failed to update checkpoint status: {e}")

    def _complete_checkpoint(self, batch_id: str):
        """Mark checkpoint as completed."""
        if not self.db:
            return

        try:
            with self.db.get_cursor() as cur:
                cur.execute("""
                    UPDATE batch_checkpoints
                    SET status = 'completed',
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE batch_id = %s
                """, (batch_id,))
            logger.info(f"Completed checkpoint for batch {batch_id}")
        except Exception as e:
            logger.warning(f"Failed to complete checkpoint: {e}")

