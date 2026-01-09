"""
Disease Intelligence Module

Provides structured disease-level market intelligence focused on the treatment funnel:
- Prevalence data
- Patient segmentation
- Treatment paradigm (1L, 2L, 3L)
- Failure rates
- Market funnel calculations
"""

from .models import (
    DiseaseIntelligence,
    PrevalenceData,
    PatientSegmentation,
    TreatmentParadigm,
    TreatmentLine,
    TreatmentDrug,
    FailureRates,
    MarketFunnel,
    DiseaseSource,
)

__all__ = [
    "DiseaseIntelligence",
    "PrevalenceData",
    "PatientSegmentation",
    "TreatmentParadigm",
    "TreatmentLine",
    "TreatmentDrug",
    "FailureRates",
    "MarketFunnel",
    "DiseaseSource",
]
