"""
Configuration management for the Vantdge platform.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# Find the project root (where .env file lives)
# Go up from src/utils/config.py to find the root
_THIS_FILE = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent.parent  # src/utils -> src -> project root
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Required API Keys
    anthropic_api_key: str

    # Optional API Keys
    tavily_api_key: Optional[str] = None
    brave_api_key: Optional[str] = None
    clinicaltrials_api_key: Optional[str] = None
    pubmed_api_key: Optional[str] = None
    semantic_scholar_api_key: Optional[str] = None

    # MCP Database Configuration
    mcp_server_url: str = "http://localhost:8080"
    enable_mcp_database: bool = False
    disease_landscape_url: Optional[str] = None
    expert_database_url: Optional[str] = None

    # Drug Database Configuration (PostgreSQL)
    drug_database_url: Optional[str] = None
    enable_drug_database: bool = True

    # Paper Catalog Configuration (PostgreSQL)
    paper_catalog_url: str = "postgresql://postgres:password@localhost:5432/vantdge"
    enable_paper_catalog: bool = True

    # PDF Processing Configuration
    use_camelot: bool = True
    camelot_flavor: str = "lattice"
    camelot_fallback_to_stream: bool = True
    extract_figures: bool = False

    # Storage Configuration
    data_dir: str = "data"
    papers_dir: str = "data/papers"
    extracted_dir: str = "data/extracted"

    # Claude Configuration
    claude_model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 4000
    max_iterations: int = 3
    confidence_threshold: float = 0.7

    # Feature Flags
    enable_web_search: bool = True
    max_web_searches_per_agent: int = 5

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    @property
    def has_web_search(self) -> bool:
        """Check if web search is available"""
        return self.enable_web_search and (
            self.tavily_api_key is not None or
            self.brave_api_key is not None
        )

    @property
    def has_mcp_database(self) -> bool:
        """Check if MCP database access is available"""
        return (
            self.enable_mcp_database and
            self.mcp_server_url is not None and
            self.disease_landscape_url is not None
        )

    @property
    def has_paper_catalog(self) -> bool:
        """Check if paper catalog is available"""
        return self.enable_paper_catalog and self.paper_catalog_url is not None

    @property
    def has_drug_database(self) -> bool:
        """Check if drug database is available"""
        return self.enable_drug_database and self.drug_database_url is not None


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get or create the global settings instance.

    Returns:
        Settings instance loaded from environment
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    Force reload settings from environment.

    Returns:
        New Settings instance
    """
    global _settings
    _settings = Settings()
    return _settings

