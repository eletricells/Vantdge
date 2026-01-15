"""
Efficacy Comparison Module

This module provides tools for generating comprehensive efficacy comparison
tables for approved drugs in a given disease/indication.

Key components:
- InnovativeDrugFinder: Finds innovative (non-generic) drugs for an indication
- PivotalTrialIdentifier: Identifies pivotal trials that supported FDA approval
- PrimaryPaperIdentifier: Finds primary results publications with screening
- DataSourceResolver: Resolves best available data source with fallbacks
- ComprehensiveExtractor: Multi-stage LLM extraction of all trial data
- EfficacyComparisonAgent: Orchestrates the full pipeline
"""

from .models import (
    ApprovedDrug,
    BaselineCharacteristics,
    DataSourceType,
    DrugEfficacyProfile,
    EfficacyComparisonResult,
    EfficacyEndpoint,
    EndpointCategory,
    EndpointDefinition,
    IdentifiedPaper,
    MeasurementType,
    PaperScreeningResult,
    PivotalTrial,
    PriorTreatment,
    RaceBreakdown,
    ResolvedDataSource,
    SeverityScore,
    TrialArm,
    TrialExtraction,
    TrialMetadata,
)

from .agent import EfficacyComparisonAgent

from .services import (
    ComprehensiveExtractor,
    DataSourceResolver,
    InnovativeDrugFinder,
    PivotalTrialIdentifier,
    PrimaryPaperIdentifier,
)

__all__ = [
    # Agent
    "EfficacyComparisonAgent",
    # Services
    "ComprehensiveExtractor",
    "DataSourceResolver",
    "InnovativeDrugFinder",
    "PivotalTrialIdentifier",
    "PrimaryPaperIdentifier",
    # Models
    "ApprovedDrug",
    "BaselineCharacteristics",
    "DataSourceType",
    "DrugEfficacyProfile",
    "EfficacyComparisonResult",
    "EfficacyEndpoint",
    "EndpointCategory",
    "EndpointDefinition",
    "IdentifiedPaper",
    "MeasurementType",
    "PaperScreeningResult",
    "PivotalTrial",
    "PriorTreatment",
    "RaceBreakdown",
    "ResolvedDataSource",
    "SeverityScore",
    "TrialArm",
    "TrialExtraction",
    "TrialMetadata",
]
