"""
Configuration classes for PDF extraction pipeline.

Centralizes all hardcoded thresholds and magic numbers for easier tuning.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TableValidationConfig:
    """Configuration for table validation."""
    min_rows: int = 3
    min_columns: int = 2
    min_fill_ratio: float = 0.2
    min_fill_ratio_wide_tables: float = 0.25
    wide_table_min_columns: int = 4
    high_confidence_fill_ratio: float = 0.5
    max_cell_count_variation: int = 3
    min_numeric_ratio: float = 0.1  # Minimum ratio of numeric cells for data tables


@dataclass
class HeaderRecoveryConfig:
    """Configuration for header recovery."""
    batch_size: int = 3
    batch_delay_seconds: float = 1.0
    max_retries: int = 2
    min_confidence_threshold: float = 0.7
    enable_caching: bool = True


@dataclass
class TextExtractionConfig:
    """Configuration for text extraction."""
    prefer_markdown: bool = True
    max_pages: Optional[int] = None
    table_strategy: str = 'lines_strict'
    min_quality_score: float = 0.5
    min_content_length: int = 500
    enable_ocr_fallback: bool = False


@dataclass
class ExtractionConfig:
    """Master configuration for PDF extraction."""
    table_validation: TableValidationConfig = field(default_factory=TableValidationConfig)
    header_recovery: HeaderRecoveryConfig = field(default_factory=HeaderRecoveryConfig)
    text_extraction: TextExtractionConfig = field(default_factory=TextExtractionConfig)
    
    enable_header_recovery: bool = True
    enable_section_detection: bool = True
    enable_figure_extraction: bool = False
    enable_ocr_fallback: bool = False
    
    # Performance settings
    max_parallel_extractions: int = 3
    
    @classmethod
    def default(cls) -> 'ExtractionConfig':
        """Create default configuration."""
        return cls()
    
    @classmethod
    def fast(cls) -> 'ExtractionConfig':
        """Create configuration optimized for speed."""
        config = cls()
        config.enable_header_recovery = False
        config.enable_section_detection = False
        config.enable_figure_extraction = False
        return config
    
    @classmethod
    def comprehensive(cls) -> 'ExtractionConfig':
        """Create configuration for comprehensive extraction."""
        config = cls()
        config.enable_header_recovery = True
        config.enable_section_detection = True
        config.enable_figure_extraction = True
        config.enable_ocr_fallback = True
        return config

