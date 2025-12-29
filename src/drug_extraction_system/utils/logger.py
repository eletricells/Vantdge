"""
Logging Configuration

Sets up rotating file logging and console logging for the drug extraction system.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional


# Module-level logger cache
_loggers: dict = {}

# Default log directory
LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "logs", "drug_extraction")


def setup_logger(
    name: str = "drug_extraction",
    log_dir: Optional[str] = None,
    level: int = logging.INFO,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    console_output: bool = True
) -> logging.Logger:
    """
    Set up logger with rotating file handler and optional console output.

    Args:
        name: Logger name
        log_dir: Directory for log files (default: logs/drug_extraction/)
        level: Logging level
        max_bytes: Max size per log file before rotation
        backup_count: Number of backup files to keep
        console_output: Whether to also log to console

    Returns:
        Configured logger
    """
    # Return existing logger if already set up
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Create log directory
    log_directory = log_dir or LOG_DIR
    os.makedirs(log_directory, exist_ok=True)

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Rotating file handler
    log_file = os.path.join(log_directory, f"{name}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler (optional)
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # Cache logger
    _loggers[name] = logger

    logger.info(f"Logger '{name}' initialized. Log file: {log_file}")
    return logger


def get_logger(name: str = "drug_extraction") -> logging.Logger:
    """
    Get existing logger or create new one with defaults.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    if name in _loggers:
        return _loggers[name]

    return setup_logger(name)


def log_batch_start(batch_id: str, csv_path: str, total_drugs: int, logger: Optional[logging.Logger] = None):
    """Log batch processing start."""
    log = logger or get_logger()
    log.info("=" * 60)
    log.info(f"BATCH PROCESSING STARTED")
    log.info(f"  Batch ID: {batch_id}")
    log.info(f"  CSV File: {csv_path}")
    log.info(f"  Total Drugs: {total_drugs}")
    log.info(f"  Started At: {datetime.now().isoformat()}")
    log.info("=" * 60)


def log_batch_end(batch_id: str, results: dict, logger: Optional[logging.Logger] = None):
    """Log batch processing end."""
    log = logger or get_logger()
    log.info("=" * 60)
    log.info(f"BATCH PROCESSING COMPLETED")
    log.info(f"  Batch ID: {batch_id}")
    log.info(f"  Total: {results.get('total', 0)}")
    log.info(f"  Successful: {results.get('successful', 0)}")
    log.info(f"  Partial: {results.get('partial', 0)}")
    log.info(f"  Failed: {results.get('failed', 0)}")
    log.info(f"  Completed At: {datetime.now().isoformat()}")
    log.info("=" * 60)


def log_drug_processing(
    drug_name: str,
    status: str,
    completeness: float = 0.0,
    error: Optional[str] = None,
    logger: Optional[logging.Logger] = None
):
    """Log individual drug processing result."""
    log = logger or get_logger()
    if status == "success":
        log.info(f"[OK] {drug_name}: {status} (completeness: {completeness:.2%})")
    elif status == "partial":
        log.warning(f"[PARTIAL] {drug_name}: {status} (completeness: {completeness:.2%})")
    else:
        log.error(f"[FAIL] {drug_name}: {status} - {error or 'Unknown error'}")

