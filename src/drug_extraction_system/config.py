"""
Configuration for Drug Extraction System

Loads configuration from environment variables and config.yaml file.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Tuple
import logging

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system env vars

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing required values."""
    pass


@dataclass
class APIConfig:
    """API client configuration."""
    openfda_api_key: Optional[str] = None
    openfda_rate_limit: int = 240  # requests per minute with API key
    openfda_daily_limit: int = 120000  # requests per day with API key
    
    rxnorm_rate_limit: int = 20  # requests per second (conservative)
    mesh_rate_limit: int = 50  # requests per minute
    clinicaltrials_rate_limit: int = 50  # requests per minute
    
    claude_model: str = "claude-sonnet-4-5-20250929"
    claude_max_tokens: int = 4000
    
    tavily_api_key: Optional[str] = None


@dataclass
class DatabaseConfig:
    """Database configuration."""
    database_url: str = ""
    min_connections: int = 1
    max_connections: int = 10


@dataclass
class ProcessingConfig:
    """Processing configuration."""
    batch_size: int = 10
    max_workers: int = 5
    completeness_threshold: float = 0.8  # Threshold for "success" status
    partial_threshold: float = 0.5  # Threshold for storing partial records
    refresh_existing: bool = False  # Whether to refresh existing drugs by default
    
    # Completeness weights
    core_weight: float = 0.30
    indications_weight: float = 0.25
    trials_weight: float = 0.25
    dosing_weight: float = 0.20


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    log_dir: str = "logs/drug_extraction"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


@dataclass
class Config:
    """Main configuration class."""
    api: APIConfig = field(default_factory=APIConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def load_config() -> Config:
    """
    Load configuration from environment variables.

    Environment variables:
        DRUG_DATABASE_URL: PostgreSQL connection string
        OPEN_FDA_API_KEY: OpenFDA API key (optional but recommended)
        TAVILY_API_KEY: Tavily API key
        ANTHROPIC_API_KEY: Claude API key (checked separately)
        CLAUDE_MODEL: Claude model name
        LOG_LEVEL: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    config = Config()

    # Database
    config.database.database_url = os.getenv("DRUG_DATABASE_URL", "")
    if not config.database.database_url:
        logger.warning("DRUG_DATABASE_URL not set")

    # API keys
    config.api.openfda_api_key = os.getenv("OPEN_FDA_API_KEY")
    if not config.api.openfda_api_key:
        logger.warning("OPEN_FDA_API_KEY not set - using lower rate limits (40/min)")
        config.api.openfda_rate_limit = 40  # Without API key

    config.api.tavily_api_key = os.getenv("TAVILY_API_KEY")
    
    # Claude config
    config.api.claude_model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
    max_tokens = os.getenv("MAX_TOKENS")
    if max_tokens:
        config.api.claude_max_tokens = int(max_tokens)

    # Logging
    config.logging.level = os.getenv("LOG_LEVEL", "INFO")

    # Processing (can be overridden via CLI)
    batch_size = os.getenv("DRUG_EXTRACTION_BATCH_SIZE")
    if batch_size:
        config.processing.batch_size = int(batch_size)

    logger.info("Configuration loaded successfully")
    return config


def validate_config(config: Config, strict: bool = True) -> Tuple[List[str], List[str]]:
    """
    Validate configuration and return errors and warnings.

    Args:
        config: Configuration to validate
        strict: If True, raise ConfigurationError for critical issues

    Returns:
        Tuple of (errors, warnings) lists

    Raises:
        ConfigurationError: If strict=True and critical errors found
    """
    errors = []
    warnings = []

    # Critical: Database URL
    if not config.database.database_url:
        errors.append("DRUG_DATABASE_URL is required but not set")
    elif not config.database.database_url.startswith("postgresql://"):
        errors.append(f"DRUG_DATABASE_URL must start with 'postgresql://', got: {config.database.database_url[:20]}...")

    # Critical: Anthropic API key (checked from environment)
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_key:
        errors.append("ANTHROPIC_API_KEY is required but not set")

    # Warning: OpenFDA API key (optional but recommended)
    if not config.api.openfda_api_key:
        warnings.append("OPEN_FDA_API_KEY not set - using lower rate limits (40/min instead of 240/min)")

    # Warning: Tavily API key (optional but useful for enrichment)
    if not config.api.tavily_api_key:
        warnings.append("TAVILY_API_KEY not set - web search enrichment will be disabled")

    # Validation: Processing config
    if config.processing.batch_size < 1:
        errors.append(f"batch_size must be >= 1, got: {config.processing.batch_size}")

    if config.processing.max_workers < 1:
        errors.append(f"max_workers must be >= 1, got: {config.processing.max_workers}")

    if not 0 <= config.processing.completeness_threshold <= 1:
        errors.append(f"completeness_threshold must be between 0 and 1, got: {config.processing.completeness_threshold}")

    if not 0 <= config.processing.partial_threshold <= 1:
        errors.append(f"partial_threshold must be between 0 and 1, got: {config.processing.partial_threshold}")

    # Validation: Database connection pool
    if config.database.min_connections < 1:
        errors.append(f"min_connections must be >= 1, got: {config.database.min_connections}")

    if config.database.max_connections < config.database.min_connections:
        errors.append(f"max_connections ({config.database.max_connections}) must be >= min_connections ({config.database.min_connections})")

    # Log results
    if errors:
        logger.error(f"Configuration validation failed with {len(errors)} error(s):")
        for error in errors:
            logger.error(f"  - {error}")

    if warnings:
        logger.warning(f"Configuration has {len(warnings)} warning(s):")
        for warning in warnings:
            logger.warning(f"  - {warning}")

    # Raise exception if strict mode and errors found
    if strict and errors:
        error_msg = "\n".join(f"  - {e}" for e in errors)
        raise ConfigurationError(f"Configuration validation failed:\n{error_msg}")

    return errors, warnings


# Global config instance
_config: Optional[Config] = None


def get_config(validate: bool = True, strict: bool = False) -> Config:
    """
    Get or create global config instance.

    Args:
        validate: If True, validate configuration
        strict: If True, raise ConfigurationError on validation errors

    Returns:
        Config instance

    Raises:
        ConfigurationError: If strict=True and validation fails
    """
    global _config
    if _config is None:
        _config = load_config()
        if validate:
            validate_config(_config, strict=strict)
    return _config


def reload_config(validate: bool = True, strict: bool = False) -> Config:
    """
    Force reload configuration.

    Args:
        validate: If True, validate configuration
        strict: If True, raise ConfigurationError on validation errors

    Returns:
        Config instance

    Raises:
        ConfigurationError: If strict=True and validation fails
    """
    global _config
    _config = load_config()
    if validate:
        validate_config(_config, strict=strict)
    return _config

