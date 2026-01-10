"""
Models for Case Series Analysis

Re-exports existing Pydantic models from the main models module.
Also exports service-specific models for convenience.
"""

from src.models.case_series_schemas import (
    # Enums
    EvidenceLevel,
    OutcomeResult,
    EfficacySignal,
    SafetyProfile,
    DevelopmentPotential,
    StudyDesign,
    ResponseDefinitionQuality,
    OutcomeMetricType,
    # Clinical Evidence
    CaseSeriesSource,
    PatientPopulation,
    TreatmentDetails,
    EfficacyOutcome,
    SafetyOutcome,
    DetailedEfficacyEndpoint,
    DetailedSafetyEndpoint,
    ExtractionConfidence,
    CaseSeriesExtraction,
    # New scoring models
    BiomarkerResult,
    IndividualStudyScore,
    AggregateScore,
    # Market Intelligence
    EpidemiologyData,
    StandardOfCareTreatment,
    PipelineTherapy,
    StandardOfCareData,
    AttributedSource,
    MarketIntelligence,
    # Scoring
    OpportunityScores,
    # Opportunity
    RepurposingOpportunity,
    # Results
    PaperForManualReview,
    DrugAnalysisResult,
    MechanismAnalysisResult,
)

__all__ = [
    # Enums
    "EvidenceLevel",
    "OutcomeResult",
    "EfficacySignal",
    "SafetyProfile",
    "DevelopmentPotential",
    "StudyDesign",
    "ResponseDefinitionQuality",
    "OutcomeMetricType",
    # Clinical Evidence
    "CaseSeriesSource",
    "PatientPopulation",
    "TreatmentDetails",
    "EfficacyOutcome",
    "SafetyOutcome",
    "DetailedEfficacyEndpoint",
    "DetailedSafetyEndpoint",
    "ExtractionConfidence",
    "CaseSeriesExtraction",
    # Scoring models
    "BiomarkerResult",
    "IndividualStudyScore",
    "AggregateScore",
    # Market Intelligence
    "EpidemiologyData",
    "StandardOfCareTreatment",
    "PipelineTherapy",
    "StandardOfCareData",
    "AttributedSource",
    "MarketIntelligence",
    # Scoring
    "OpportunityScores",
    # Opportunity
    "RepurposingOpportunity",
    # Results
    "PaperForManualReview",
    "DrugAnalysisResult",
    "MechanismAnalysisResult",
    # Service models
    "Paper",
    "DrugInfo",
]

# Import service models
from src.case_series.services.literature_search_service import Paper
from src.case_series.services.drug_info_service import DrugInfo

# Import taxonomy
from src.case_series.taxonomy import (
    DiseaseTaxonomy,
    DiseaseEntry,
    EndpointDefinition,
    get_default_taxonomy,
)

__all__ += [
    "DiseaseTaxonomy",
    "DiseaseEntry",
    "EndpointDefinition",
    "get_default_taxonomy",
]
