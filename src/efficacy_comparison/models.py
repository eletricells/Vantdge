"""
Data models for the Efficacy Comparison module.

These models represent the core data structures used throughout the
efficacy comparison pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DataSourceType(str, Enum):
    """Types of data sources for efficacy extraction."""
    PMC_FULLTEXT = "PMC_FULLTEXT"
    ABSTRACT = "ABSTRACT"
    CTGOV_RESULTS = "CTGOV_RESULTS"
    FDA_LABEL = "FDA_LABEL"
    PRESS_RELEASE = "PRESS_RELEASE"
    CONFERENCE_ABSTRACT = "CONFERENCE_ABSTRACT"
    WEB_SEARCH = "WEB_SEARCH"


class EndpointCategory(str, Enum):
    """Categories for efficacy endpoints."""
    PRIMARY = "Primary"
    SECONDARY = "Secondary"
    EXPLORATORY = "Exploratory"
    PRO = "PRO"  # Patient-reported outcome
    BIOMARKER = "Biomarker"
    SAFETY = "Safety"


class MeasurementType(str, Enum):
    """Types of endpoint measurements."""
    RESPONDER = "responder"  # Binary: achieved threshold or not
    CONTINUOUS = "continuous"  # Mean change, LSM, etc.
    TIME_TO_EVENT = "time_to_event"  # Survival analysis
    COUNT = "count"  # Event counts


# ============================================================================
# DRUG AND TRIAL IDENTIFICATION
# ============================================================================

@dataclass
class ApprovedDrug:
    """An innovative drug approved for an indication."""
    drug_name: str  # Brand name
    generic_name: str
    manufacturer: Optional[str] = None
    drug_id: Optional[int] = None  # Database ID if exists

    # Approval info
    approval_date: Optional[str] = None
    application_number: Optional[str] = None  # NDA/BLA number

    # Classification
    drug_type: Optional[str] = None  # small_molecule, biologic
    mechanism_of_action: Optional[str] = None

    # Source
    dailymed_setid: Optional[str] = None
    rxcui: Optional[str] = None


@dataclass
class PivotalTrial:
    """A pivotal trial identified for a drug+indication."""
    nct_id: str
    trial_name: Optional[str] = None  # Acronym like TULIP-2
    phase: Optional[str] = None  # Phase 2, Phase 3

    # Enrollment
    enrollment: Optional[int] = None

    # Primary endpoint (if known)
    primary_endpoint: Optional[str] = None

    # Status
    status: Optional[str] = None  # Completed, Active, etc.

    # Sponsor
    sponsor: Optional[str] = None

    # Confidence that this is actually a pivotal trial
    confidence: float = 0.0

    # How was this trial identified
    identification_source: Optional[str] = None  # fda_label, ctgov, web_search


@dataclass
class IdentifiedPaper:
    """A paper identified as potentially containing trial results."""
    pmid: str
    title: str

    # Authors and publication info
    authors: Optional[str] = None
    journal: Optional[str] = None
    year: Optional[int] = None

    # Abstract
    abstract: Optional[str] = None

    # Open access status
    is_open_access: bool = False
    pmc_id: Optional[str] = None

    # Link to trial
    nct_id: Optional[str] = None
    trial_name: Optional[str] = None

    # Screening result
    screening_result: Optional['PaperScreeningResult'] = None


@dataclass
class PaperScreeningResult:
    """Result of screening a paper with Haiku."""
    is_primary_results: bool
    reports_efficacy: bool
    is_pivotal_trial: bool
    primary_endpoint: Optional[str] = None
    confidence: float = 0.0
    reasoning: Optional[str] = None


# ============================================================================
# DATA SOURCES
# ============================================================================

@dataclass
class ResolvedDataSource:
    """A resolved data source for extraction."""
    source_type: DataSourceType
    content: str  # The actual content to extract from
    completeness: str  # HIGH, MEDIUM, LOW
    url: Optional[str] = None

    # Additional metadata
    pmid: Optional[str] = None
    pmc_id: Optional[str] = None
    title: Optional[str] = None


# ============================================================================
# TRIAL DATA
# ============================================================================

@dataclass
class TrialArm:
    """A treatment arm in a clinical trial."""
    name: str  # e.g., "300mg Q2W", "Placebo"
    n: Optional[int] = None
    is_active: bool = True  # False for placebo/control

    # Dosing details
    dose: Optional[str] = None  # e.g., "300mg"
    frequency: Optional[str] = None  # e.g., "Q2W", "QD"
    route: Optional[str] = None  # e.g., "subcutaneous", "oral"


class PatientPopulationType(str, Enum):
    """Standard patient population types for trials."""
    # RA-specific
    CSDMARD_IR = "csDMARD-IR"  # Inadequate response to conventional synthetic DMARDs
    BDMARD_IR = "bDMARD-IR"   # Inadequate response to biologic DMARDs
    TNF_IR = "TNF-IR"         # Inadequate response to TNF inhibitors
    MTX_IR = "MTX-IR"         # Inadequate response to methotrexate specifically
    MTX_NAIVE = "MTX-naive"   # Never received methotrexate
    DMARD_NAIVE = "DMARD-naive"  # Treatment-naive

    # IBD-specific
    ANTI_TNF_NAIVE = "anti-TNF-naive"
    ANTI_TNF_IR = "anti-TNF-IR"
    BIOLOGIC_NAIVE = "biologic-naive"
    BIOLOGIC_IR = "biologic-IR"

    # General
    TREATMENT_NAIVE = "treatment-naive"
    TREATMENT_EXPERIENCED = "treatment-experienced"
    REFRACTORY = "refractory"

    # Other
    OTHER = "other"


@dataclass
class ConcomitantTherapy:
    """Details of required/allowed concomitant therapy."""
    therapy_name: str  # e.g., "methotrexate", "topical corticosteroids"
    is_required: bool = False
    is_allowed: bool = True
    dose_requirement: Optional[str] = None  # e.g., "stable dose ≥15mg/week"
    percentage_on_therapy: Optional[float] = None  # % of patients actually on this


@dataclass
class TrialMetadata:
    """Metadata for a clinical trial."""
    nct_id: Optional[str] = None
    trial_name: Optional[str] = None
    phase: Optional[str] = None

    # Drug info
    drug_name: Optional[str] = None
    generic_name: Optional[str] = None
    manufacturer: Optional[str] = None

    # Indication
    indication_name: Optional[str] = None

    # Patient population - CRITICAL for cross-trial comparison
    patient_population: Optional[str] = None  # e.g., "csDMARD-IR", "bDMARD-IR"
    patient_population_type: Optional[PatientPopulationType] = None
    patient_population_description: Optional[str] = None  # Full inclusion criteria
    line_of_therapy: Optional[int] = None  # 1L, 2L, 3L+

    # Prior treatment requirements
    prior_treatment_failures_required: Optional[int] = None  # Min number of prior failures
    prior_treatment_failures_description: Optional[str] = None  # e.g., "≥1 TNF inhibitor"

    # Disease subtype (for diseases with subtypes)
    disease_subtype: Optional[str] = None  # e.g., "seropositive", "moderate-to-severe"
    disease_activity_requirement: Optional[str] = None  # e.g., "DAS28-CRP ≥3.2"

    # Arms
    arms: List[TrialArm] = field(default_factory=list)
    total_enrollment: Optional[int] = None

    # Background/concomitant therapy - enhanced
    background_therapy: Optional[str] = None  # Simple string for backward compat
    background_therapy_required: bool = False
    concomitant_therapies: List[ConcomitantTherapy] = field(default_factory=list)

    # Rescue therapy allowed?
    rescue_therapy_allowed: bool = False
    rescue_therapy_description: Optional[str] = None

    # Data source
    source_type: Optional[DataSourceType] = None
    source_url: Optional[str] = None
    pmid: Optional[str] = None
    pmc_id: Optional[str] = None

    # Extraction metadata
    extraction_confidence: Optional[float] = None
    extraction_notes: Optional[str] = None


# ============================================================================
# BASELINE CHARACTERISTICS
# ============================================================================

@dataclass
class RaceBreakdown:
    """Race/ethnicity breakdown for a trial arm."""
    white: Optional[float] = None
    black: Optional[float] = None
    asian: Optional[float] = None
    hispanic: Optional[float] = None
    other: Optional[float] = None
    not_reported: Optional[float] = None

    def to_dict(self) -> Dict[str, float]:
        return {k: v for k, v in {
            'white': self.white,
            'black': self.black,
            'asian': self.asian,
            'hispanic': self.hispanic,
            'other': self.other,
            'not_reported': self.not_reported
        }.items() if v is not None}


@dataclass
class SeverityScore:
    """A disease severity score measurement."""
    name: str  # e.g., "EASI", "SLEDAI-2K"
    mean: Optional[float] = None
    median: Optional[float] = None
    sd: Optional[float] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None

    # For categorical scores (e.g., IGA distribution)
    distribution: Optional[Dict[str, float]] = None  # {"score_3": 0.65, "score_4": 0.35}


@dataclass
class PriorTreatment:
    """Prior treatment information."""
    treatment: str  # e.g., "methotrexate", "cyclosporine"
    percentage: Optional[float] = None
    category: Optional[str] = None  # systemic, biologic, topical


@dataclass
class BaselineCharacteristics:
    """Baseline characteristics for a trial arm."""
    arm_name: str
    n: Optional[int] = None

    # Demographics - Age
    age_mean: Optional[float] = None
    age_median: Optional[float] = None
    age_sd: Optional[float] = None
    age_range_min: Optional[float] = None
    age_range_max: Optional[float] = None

    # Demographics - Sex
    male_pct: Optional[float] = None
    female_pct: Optional[float] = None

    # Demographics - Race
    race: Optional[RaceBreakdown] = None

    # Demographics - Weight/BMI (relevant for dosing)
    weight_mean: Optional[float] = None
    weight_unit: str = "kg"
    bmi_mean: Optional[float] = None

    # Disease characteristics
    disease_duration_mean: Optional[float] = None
    disease_duration_median: Optional[float] = None
    disease_duration_unit: str = "years"

    # Severity scores (disease-specific)
    severity_scores: List[SeverityScore] = field(default_factory=list)

    # Serology status (critical for RA, SLE)
    rf_positive_pct: Optional[float] = None  # Rheumatoid factor positive %
    anti_ccp_positive_pct: Optional[float] = None  # Anti-CCP antibody positive %
    seropositive_pct: Optional[float] = None  # Either RF+ or anti-CCP+
    ana_positive_pct: Optional[float] = None  # ANA positive (for SLE)
    anti_dsdna_positive_pct: Optional[float] = None  # Anti-dsDNA (for SLE)

    # Inflammatory markers
    crp_mean: Optional[float] = None  # C-reactive protein mg/L
    esr_mean: Optional[float] = None  # Erythrocyte sedimentation rate mm/hr

    # Prior treatments
    prior_systemic_pct: Optional[float] = None
    prior_biologic_pct: Optional[float] = None
    prior_topical_pct: Optional[float] = None
    prior_treatments: List[PriorTreatment] = field(default_factory=list)

    # Number of prior treatment failures (for bDMARD-IR populations)
    prior_biologic_failures_mean: Optional[float] = None
    prior_dmard_failures_mean: Optional[float] = None

    # Concomitant therapy at baseline
    on_mtx_pct: Optional[float] = None  # % on methotrexate
    on_steroids_pct: Optional[float] = None  # % on corticosteroids
    steroid_dose_mean: Optional[float] = None  # Mean steroid dose (prednisone equiv mg/day)

    # Source
    source_table: Optional[str] = None


# ============================================================================
# EFFICACY ENDPOINTS
# ============================================================================

@dataclass
class EfficacyEndpoint:
    """An efficacy endpoint extracted from a trial."""
    # Identification
    endpoint_name_raw: str  # As extracted
    endpoint_name_normalized: Optional[str] = None  # Standardized
    endpoint_category: Optional[EndpointCategory] = None

    # Arm
    arm_name: Optional[str] = None

    # Timepoint
    timepoint: Optional[str] = None  # "Week 16"
    timepoint_weeks: Optional[float] = None  # 16.0

    # Sample size
    n_evaluated: Optional[int] = None

    # For responder endpoints
    responders_n: Optional[int] = None
    responders_pct: Optional[float] = None

    # For continuous endpoints
    mean_value: Optional[float] = None
    median_value: Optional[float] = None
    change_from_baseline: Optional[float] = None
    change_from_baseline_pct: Optional[float] = None
    se: Optional[float] = None
    sd: Optional[float] = None
    ci_lower: Optional[float] = None
    ci_upper: Optional[float] = None

    # Statistical comparison
    vs_comparator: Optional[str] = None  # "Placebo"
    p_value: Optional[str] = None  # "<0.001"
    p_value_numeric: Optional[float] = None
    is_statistically_significant: Optional[bool] = None

    # Source
    source_table: Optional[str] = None
    source_text: Optional[str] = None

    # Confidence
    extraction_confidence: Optional[float] = None


# ============================================================================
# COMPLETE EXTRACTION RESULT
# ============================================================================

@dataclass
class TrialExtraction:
    """Complete extraction result for a single trial."""
    # Trial metadata
    metadata: TrialMetadata

    # Baseline characteristics per arm
    baseline: List[BaselineCharacteristics] = field(default_factory=list)

    # All efficacy endpoints
    endpoints: List[EfficacyEndpoint] = field(default_factory=list)

    # Extraction metadata
    extraction_timestamp: datetime = field(default_factory=datetime.now)
    extraction_confidence: float = 0.0
    extraction_notes: Optional[str] = None

    # Data source
    data_source: Optional[ResolvedDataSource] = None


@dataclass
class DrugEfficacyProfile:
    """Complete efficacy profile for a drug in an indication."""
    drug: ApprovedDrug
    indication_name: str

    # All pivotal trials
    pivotal_trials: List[PivotalTrial] = field(default_factory=list)

    # All extractions
    extractions: List[TrialExtraction] = field(default_factory=list)

    # Metadata
    extraction_timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class EfficacyComparisonResult:
    """Complete result for an efficacy comparison analysis."""
    indication_name: str
    indication_mesh_id: Optional[str] = None

    # All drug profiles
    drug_profiles: List[DrugEfficacyProfile] = field(default_factory=list)

    # Summary statistics
    total_drugs: int = 0
    total_trials: int = 0
    total_endpoints: int = 0

    # Metadata
    analysis_timestamp: datetime = field(default_factory=datetime.now)
    analysis_notes: Optional[str] = None


# ============================================================================
# ENDPOINT LIBRARY
# ============================================================================

@dataclass
class EndpointDefinition:
    """Definition of a standard endpoint in the library."""
    endpoint_name_canonical: str  # e.g., "EASI-75"
    endpoint_name_full: Optional[str] = None  # "75% improvement in EASI score"

    # Aliases for matching
    aliases: List[str] = field(default_factory=list)

    # Classification
    therapeutic_area: Optional[str] = None
    diseases: List[str] = field(default_factory=list)
    endpoint_type: Optional[str] = None  # efficacy, safety, PRO, biomarker
    endpoint_category_typical: Optional[str] = None  # Primary, Secondary
    measurement_type: Optional[MeasurementType] = None

    # Interpretation
    direction: Optional[str] = None  # higher_better, lower_better, reduction
    typical_timepoints: List[str] = field(default_factory=list)
    response_threshold: Optional[str] = None

    # Validation
    is_validated: bool = False
    regulatory_acceptance: Optional[str] = None
    quality_tier: Optional[int] = None  # 1=gold standard, 2=validated, 3=exploratory

    # Organ domain
    organ_domain: Optional[str] = None
