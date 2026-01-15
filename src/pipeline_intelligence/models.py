"""Pydantic models for Pipeline Intelligence."""

from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class DosingRegimen(BaseModel):
    """Dosing regimen for a drug."""
    phase: Optional[str] = Field(None, description="loading, maintenance, induction")
    dose_amount: Optional[float] = None
    dose_unit: Optional[str] = None  # mg, mg/kg, mg/m2
    frequency: Optional[str] = None  # QW, Q2W, Q4W, QD, BID
    frequency_raw: Optional[str] = None  # "once weekly", "every 4 weeks"
    route: Optional[str] = None  # SC, IV, PO, IM
    route_raw: Optional[str] = None  # "subcutaneous injection"
    duration_weeks: Optional[int] = None
    notes: Optional[str] = None


class ClinicalTrial(BaseModel):
    """Clinical trial information."""
    nct_id: str
    title: Optional[str] = None
    phase: Optional[str] = None  # Phase 1, Phase 2, Phase 3
    status: Optional[str] = None  # Recruiting, Active, Completed
    start_date: Optional[date] = None
    completion_date: Optional[date] = None
    enrollment: Optional[int] = None
    primary_endpoint: Optional[str] = None
    sponsor: Optional[str] = None
    collaborators: Optional[List[str]] = None


class PipelineDrug(BaseModel):
    """A drug in the pipeline or approved for a disease."""
    # Identification
    drug_id: Optional[int] = None  # From drugs table if exists
    brand_name: Optional[str] = None
    generic_name: str
    manufacturer: Optional[str] = None

    # Classification
    drug_type: Optional[str] = None  # mAb, small molecule, ADC, gene therapy
    mechanism_of_action: Optional[str] = None  # IL-17A inhibitor, KRAS G12C inhibitor
    target: Optional[str] = None  # IL-17A, KRAS G12C, CD20
    modality: Optional[str] = None  # biologic, small molecule, cell therapy

    # Development Status
    approval_status: str = "investigational"  # approved, investigational, discontinued
    highest_phase: Optional[str] = None  # Phase 1, Phase 2, Phase 3, Approved
    phase_for_indication: Optional[str] = None  # Phase for this specific indication

    # Approval info (for approved drugs)
    first_approval_date: Optional[date] = None
    indication_approval_date: Optional[date] = None

    # Clinical trials (for investigational)
    trials: List[ClinicalTrial] = Field(default_factory=list)
    lead_trial_nct: Optional[str] = None  # Most advanced trial

    # Dosing
    dosing: List[DosingRegimen] = Field(default_factory=list)
    dosing_summary: Optional[str] = None  # "300mg SC QW x4 then Q4W"

    # Efficacy (if available)
    efficacy_summary: Optional[str] = None  # Brief efficacy data
    primary_endpoint_result: Optional[str] = None

    # Safety
    safety_summary: Optional[str] = None
    notable_aes: Optional[List[str]] = None

    # Timeline
    expected_approval: Optional[str] = None  # "2025 H2", "2026"
    recent_milestone: Optional[str] = None  # "Phase 3 top-line positive Jan 2026"
    milestone_date: Optional[date] = None

    # Discontinuation/Failure tracking
    development_status: str = "active"  # active, discontinued, failed, on_hold
    discontinuation_date: Optional[str] = None  # "2022-03", "2022"
    discontinuation_reason: Optional[str] = None  # "Lack of efficacy", "Strategic", "Safety"
    failure_stage: Optional[str] = None  # "Phase 2", "Phase 3"

    # Sources
    source_nct_ids: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)
    data_sources: List[str] = Field(default_factory=list)  # "ClinicalTrials.gov", "Press Release"

    # Metadata
    last_updated: Optional[datetime] = None
    confidence_score: Optional[float] = None  # 0.0-1.0

    # PubChem identifier for deduplication
    # Positive values = CID (compound), Negative values = SID (substance-only)
    pubchem_cid: Optional[int] = None


class CompetitiveLandscape(BaseModel):
    """Complete competitive landscape for a disease."""
    # Disease identification
    disease_name: str
    disease_key: Optional[str] = None
    disease_id: Optional[int] = None
    therapeutic_area: Optional[str] = None

    # Disease synonyms (from MeSH expansion) - shared with Disease Intelligence
    disease_synonyms: List[str] = Field(default_factory=list)
    mesh_id: Optional[str] = Field(None, description="MeSH ID if found")

    # Drug counts by phase
    total_drugs: int = 0
    approved_count: int = 0
    phase3_count: int = 0
    phase2_count: int = 0
    phase1_count: int = 0
    preclinical_count: int = 0

    # Drugs by phase
    approved_drugs: List[PipelineDrug] = Field(default_factory=list)
    phase3_drugs: List[PipelineDrug] = Field(default_factory=list)
    phase2_drugs: List[PipelineDrug] = Field(default_factory=list)
    phase1_drugs: List[PipelineDrug] = Field(default_factory=list)
    preclinical_drugs: List[PipelineDrug] = Field(default_factory=list)

    # Discontinued/Failed drugs (kept for historical context)
    discontinued_drugs: List[PipelineDrug] = Field(default_factory=list)
    discontinued_count: int = 0

    # Market context
    unmet_need_summary: Optional[str] = None
    key_moa_classes: List[str] = Field(default_factory=list)  # ["IL-17", "JAK", "PDE4"]

    # Search metadata
    search_timestamp: Optional[datetime] = None
    sources_searched: List[str] = Field(default_factory=list)
    trials_reviewed: int = 0

    @property
    def all_drugs(self) -> List[PipelineDrug]:
        """All drugs in the landscape."""
        return (
            self.approved_drugs +
            self.phase3_drugs +
            self.phase2_drugs +
            self.phase1_drugs +
            self.preclinical_drugs
        )

    def update_counts(self):
        """Update drug counts from lists."""
        self.approved_count = len(self.approved_drugs)
        self.phase3_count = len(self.phase3_drugs)
        self.phase2_count = len(self.phase2_drugs)
        self.phase1_count = len(self.phase1_drugs)
        self.preclinical_count = len(self.preclinical_drugs)
        self.total_drugs = (
            self.approved_count +
            self.phase3_count +
            self.phase2_count +
            self.phase1_count +
            self.preclinical_count
        )


class PipelineSource(BaseModel):
    """Source for pipeline information."""
    source_id: Optional[int] = None
    disease_id: Optional[int] = None
    drug_id: Optional[int] = None

    # Source identification
    nct_id: Optional[str] = None
    source_url: Optional[str] = None
    source_type: str  # clinicaltrials_gov, press_release, sec_filing, conference, publication

    # Content
    title: Optional[str] = None
    publication_date: Optional[date] = None
    content_summary: Optional[str] = None

    # Extracted data
    extracted_data: Optional[dict] = None

    # Quality
    confidence_score: Optional[float] = None
    verified: bool = False


class PipelineRun(BaseModel):
    """Record of a pipeline discovery run."""
    run_id: Optional[int] = None
    disease_id: Optional[int] = None
    disease_key: Optional[str] = None

    # Run metadata
    run_timestamp: Optional[datetime] = None
    run_type: str = "full"  # full, incremental, news_only

    # Search statistics
    clinicaltrials_searched: int = 0
    web_sources_searched: int = 0
    drugs_found_total: int = 0
    drugs_new: int = 0
    drugs_updated: int = 0

    # Status
    status: str = "running"  # running, completed, failed
    error_message: Optional[str] = None


class TrialSearchResult(BaseModel):
    """Result from ClinicalTrials.gov search."""
    nct_id: str
    title: str
    phase: Optional[str] = None
    status: Optional[str] = None
    conditions: List[str] = Field(default_factory=list)
    interventions: List[str] = Field(default_factory=list)
    sponsor: Optional[str] = None
    start_date: Optional[str] = None
    completion_date: Optional[str] = None
    enrollment: Optional[int] = None
