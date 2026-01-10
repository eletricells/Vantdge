"""
Data models for efficacy benchmarking.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ReviewStatus(Enum):
    """Review status for extracted data points."""
    AUTO_ACCEPTED = "auto_accepted"
    PENDING_REVIEW = "pending_review"
    USER_CONFIRMED = "user_confirmed"
    USER_REJECTED = "user_rejected"


class DataSource(Enum):
    """Data source types for efficacy extraction."""
    PUBLICATION = "publication"
    CLINICALTRIALS = "clinicaltrials.gov"
    OPENFDA = "openfda"
    WEB_SEARCH = "web_search"


@dataclass
class DiseaseMatch:
    """Result of disease standardization."""
    raw_input: str
    standard_name: str
    mesh_id: Optional[str] = None
    therapeutic_area: Optional[str] = None
    confidence: float = 1.0
    synonyms: List[str] = field(default_factory=list)


@dataclass
class ApprovedDrug:
    """Drug approved for a specific indication."""
    drug_id: int
    drug_key: str
    generic_name: str
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    approval_date: Optional[str] = None
    indication_details: Optional[str] = None


@dataclass
class EfficacyDataPoint:
    """Single efficacy endpoint extracted from a source."""
    # Source identification (required for traceability)
    source_type: DataSource
    source_url: str

    # Optional source identifiers
    pmid: Optional[str] = None
    nct_id: Optional[str] = None

    # Trial identification
    trial_name: str = ""
    trial_phase: Optional[str] = None

    # Endpoint data
    endpoint_name: str = ""
    endpoint_type: Optional[str] = None  # "primary", "secondary", "exploratory"

    # Drug arm results
    drug_arm_name: Optional[str] = None
    drug_arm_n: Optional[int] = None
    drug_arm_result: Optional[float] = None
    drug_arm_result_unit: str = "%"

    # Comparator arm results
    comparator_arm_name: Optional[str] = None
    comparator_arm_n: Optional[int] = None
    comparator_arm_result: Optional[float] = None

    # Statistical measures
    p_value: Optional[float] = None
    confidence_interval: Optional[str] = None

    # Timepoint
    timepoint: Optional[str] = None

    # Quality metrics
    confidence_score: float = 0.85
    review_status: ReviewStatus = ReviewStatus.AUTO_ACCEPTED
    extraction_timestamp: datetime = field(default_factory=datetime.now)

    # Metadata
    disease_mesh_id: Optional[str] = None
    indication_name: Optional[str] = None
    population: Optional[str] = None
    raw_source_text: Optional[str] = None


@dataclass
class DrugBenchmarkResult:
    """Complete benchmark result for a single drug."""
    drug: ApprovedDrug
    efficacy_data: List[EfficacyDataPoint] = field(default_factory=list)
    extraction_status: str = "pending"  # "pending", "success", "partial", "failed"
    errors: List[str] = field(default_factory=list)

    @property
    def has_primary_endpoints(self) -> bool:
        """Check if any primary endpoints were extracted."""
        return any(dp.endpoint_type == "primary" for dp in self.efficacy_data)

    @property
    def pending_review_count(self) -> int:
        """Count of data points pending review."""
        return sum(1 for dp in self.efficacy_data if dp.review_status == ReviewStatus.PENDING_REVIEW)


@dataclass
class BenchmarkSession:
    """Session tracking for a benchmarking analysis."""
    session_id: str
    disease: Optional[DiseaseMatch] = None
    drugs: List[ApprovedDrug] = field(default_factory=list)
    results: List[DrugBenchmarkResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    status: str = "initializing"  # "initializing", "extracting", "review_needed", "complete", "failed"

    @property
    def total_data_points(self) -> int:
        """Total number of efficacy data points extracted."""
        return sum(len(r.efficacy_data) for r in self.results)

    @property
    def pending_review_count(self) -> int:
        """Total count of data points pending review."""
        return sum(r.pending_review_count for r in self.results)

    def get_all_efficacy_data(self) -> List[EfficacyDataPoint]:
        """Get all efficacy data points across all drugs."""
        all_data = []
        for result in self.results:
            all_data.extend(result.efficacy_data)
        return all_data


# Disease-specific endpoint configurations
AUTOIMMUNE_ENDPOINTS: Dict[str, Dict[str, List[str]]] = {
    "Systemic Lupus Erythematosus": {
        "primary": ["SRI-4", "BICLA", "SRI-6", "SRI-8"],
        "secondary": ["SLEDAI reduction", "Prednisone taper", "LLDAS", "Time to flare", "BILAG response"],
        "timepoints": ["Week 52", "Week 104", "Year 1", "Year 2"]
    },
    "Lupus Nephritis": {
        "primary": ["Complete renal response", "CRR", "Partial renal response", "Overall renal response"],
        "secondary": ["Proteinuria reduction", "eGFR stabilization", "UPCR improvement"],
        "timepoints": ["Week 52", "Week 104"]
    },
    "Rheumatoid Arthritis": {
        "primary": ["ACR20", "ACR50", "ACR70"],
        "secondary": ["DAS28-CRP", "DAS28-ESR", "HAQ-DI", "Radiographic progression", "CDAI", "SDAI"],
        "timepoints": ["Week 12", "Week 24", "Week 52"]
    },
    "Plaque Psoriasis": {
        "primary": ["PASI 75", "PASI 90", "PASI 100"],
        "secondary": ["IGA 0/1", "BSA improvement", "DLQI 0/1"],
        "timepoints": ["Week 12", "Week 16", "Week 52"]
    },
    "Atopic Dermatitis": {
        "primary": ["EASI 75", "EASI 90", "IGA 0/1"],
        "secondary": ["SCORAD reduction", "Pruritus NRS", "DLQI improvement"],
        "timepoints": ["Week 16", "Week 52"]
    },
    "Psoriatic Arthritis": {
        "primary": ["ACR20", "ACR50", "ACR70"],
        "secondary": ["PASI 75", "DAS28", "HAQ-DI", "Enthesitis resolution", "Dactylitis resolution"],
        "timepoints": ["Week 12", "Week 24", "Week 52"]
    },
    "Ankylosing Spondylitis": {
        "primary": ["ASAS20", "ASAS40"],
        "secondary": ["BASDAI 50", "ASDAS improvement", "MRI spine inflammation"],
        "timepoints": ["Week 12", "Week 24", "Week 52"]
    },
    "Inflammatory Bowel Disease": {
        "primary": ["Clinical remission", "Endoscopic remission", "Clinical response"],
        "secondary": ["Mucosal healing", "CDAI reduction", "Mayo score improvement"],
        "timepoints": ["Week 8", "Week 12", "Week 52"]
    },
    "Dermatomyositis": {
        "primary": ["TIS improvement", "CDASI improvement", "MMT8 improvement"],
        "secondary": ["IMACS response", "Physician Global Assessment", "CK normalization"],
        "timepoints": ["Week 12", "Week 24", "Week 52"]
    },
    "Myasthenia Gravis": {
        "primary": ["MG-ADL improvement", "QMG improvement"],
        "secondary": ["MGC score", "MG-QoL15", "Steroid sparing"],
        "timepoints": ["Week 12", "Week 26", "Week 52"]
    },
}


def get_endpoints_for_disease(disease_name: str) -> Dict[str, List[str]]:
    """
    Get expected efficacy endpoints for a disease.

    Args:
        disease_name: Standardized disease name

    Returns:
        Dict with 'primary', 'secondary', and 'timepoints' keys
    """
    # Exact match
    if disease_name in AUTOIMMUNE_ENDPOINTS:
        return AUTOIMMUNE_ENDPOINTS[disease_name]

    # Partial match
    disease_lower = disease_name.lower()
    for key, endpoints in AUTOIMMUNE_ENDPOINTS.items():
        if key.lower() in disease_lower or disease_lower in key.lower():
            return endpoints

    # Default endpoints for unknown diseases
    return {
        "primary": ["Response rate", "Primary endpoint", "Clinical response"],
        "secondary": ["Secondary endpoint", "Safety", "Quality of life"],
        "timepoints": ["Week 12", "Week 24", "Week 52"]
    }
