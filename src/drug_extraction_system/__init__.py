"""
Drug Extraction System

A comprehensive system for extracting structured drug data from multiple sources
and storing it in a PostgreSQL database.

Features:
- Multi-source data extraction (openFDA, RxNorm, MeSH, ClinicalTrials.gov)
- Automatic drug status detection (approved vs pipeline)
- Data enrichment via Claude API and Tavily search
- Batch CSV processing with progress tracking
- Versioned database storage with audit logging
- Unique drug key generation for stable identifiers
"""

__version__ = "1.0.0"
__author__ = "Vantdge"

from src.drug_extraction_system.utils.drug_key_generator import DrugKeyGenerator

__all__ = [
    "DrugKeyGenerator",
    "__version__",
]

