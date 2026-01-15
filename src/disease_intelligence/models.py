"""
Pydantic models for Disease Intelligence Database.

These models represent the treatment funnel data needed for market sizing:
- Prevalence → Segmentation → Treatment paradigm → Failure rates → Addressable market
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class TreatmentDrug(BaseModel):
    """A drug used in a treatment line."""
    drug_name: str = Field(..., description="Brand name of the drug")
    generic_name: Optional[str] = Field(None, description="Generic/INN name")
    drug_class: Optional[str] = Field(None, description="Drug class (e.g., 'JAK inhibitor', 'Anti-BAFF')")
    wac_monthly: Optional[float] = Field(None, description="Monthly WAC (Wholesale Acquisition Cost) in USD")
    wac_source: Optional[str] = Field(None, description="Source for WAC data")
    is_standard_of_care: bool = Field(default=False, description="Is this a standard of care drug?")
    notes: Optional[str] = None


class TreatmentLine(BaseModel):
    """A line of therapy (1L, 2L, 3L)."""
    line: str = Field(..., description="Line of therapy: '1L', '2L', '3L'")
    description: Optional[str] = Field(None, description="Brief description of this treatment line")
    drugs: List[TreatmentDrug] = Field(default_factory=list, description="Drugs used in this line")


class TreatmentParadigm(BaseModel):
    """Complete treatment paradigm for a disease."""
    first_line: Optional[TreatmentLine] = None
    second_line: Optional[TreatmentLine] = None
    third_line: Optional[TreatmentLine] = None
    summary: Optional[str] = Field(None, description="Overall treatment paradigm summary")


class SeverityBreakdown(BaseModel):
    """Severity distribution of patients."""
    mild: Optional[float] = Field(None, ge=0, le=100, description="Percentage of mild patients")
    moderate: Optional[float] = Field(None, ge=0, le=100, description="Percentage of moderate patients")
    severe: Optional[float] = Field(None, ge=0, le=100, description="Percentage of severe patients")


class Subpopulation(BaseModel):
    """A subpopulation within a disease (e.g., Lupus Nephritis within SLE)."""
    name: str = Field(..., description="Subpopulation name")
    pct_of_total: Optional[float] = Field(None, ge=0, le=100, description="Percentage of total population")
    patients: Optional[int] = Field(None, ge=0, description="Absolute number of patients")
    notes: Optional[str] = None


class SourceEstimate(BaseModel):
    """A single estimate from one source paper."""
    pmid: Optional[str] = Field(None, description="PubMed ID")
    title: Optional[str] = Field(None, description="Paper title")
    authors: Optional[str] = Field(None, description="First author et al.")
    journal: Optional[str] = Field(None, description="Journal name")
    year: Optional[int] = Field(None, description="Publication year")
    url: Optional[str] = Field(None, description="Source URL")
    source_type: str = Field(default="pubmed", description="Source type: pubmed, web, etc.")
    quality_tier: Optional[str] = Field(None, description="Tier 1 (high), Tier 2 (medium), Tier 3 (low)")


class PrevalenceEstimate(SourceEstimate):
    """Prevalence estimate from a single source."""
    estimate_type: Optional[str] = Field(None, description="Type: prevalence, incidence, point_prevalence, period_prevalence")
    total_patients: Optional[int] = Field(None, ge=0, description="Total US patient population")
    adult_patients: Optional[int] = Field(None, ge=0, description="Adult patients if specified")
    pediatric_patients: Optional[int] = Field(None, ge=0, description="Pediatric patients if specified")
    prevalence_rate: Optional[str] = Field(None, description="Prevalence rate as reported (e.g., '72 per 100,000')")
    confidence_interval: Optional[str] = Field(None, description="95% CI if reported (e.g., '68-76 per 100,000')")
    rate_type: Optional[str] = Field(None, description="Rate type: crude, age_adjusted, age_specific")
    data_year: Optional[int] = Field(None, description="Year the prevalence data refers to")
    geography: Optional[str] = Field(None, description="Geographic scope (US national, state, etc.)")
    methodology: Optional[str] = Field(None, description="How prevalence was estimated")
    study_population_n: Optional[int] = Field(None, description="Sample size/denominator used in study")
    database_name: Optional[str] = Field(None, description="Database name if applicable (MarketScan, Optum, etc.)")
    notes: Optional[str] = Field(None, description="Important caveats or context")


class FailureRateEstimate(SourceEstimate):
    """Failure/inadequate response rate from a single source."""
    # Core failure data
    failure_type: Optional[str] = Field(None, description="Type: primary_nonresponse, secondary_loss_of_response, intolerance, discontinuation_any_reason")
    fail_rate_pct: Optional[float] = Field(None, ge=0, le=100, description="Failure rate percentage")
    confidence_interval: Optional[str] = Field(None, description="95% CI if reported (e.g., '31-39%')")

    # Clinical endpoint details
    clinical_endpoint: Optional[str] = Field(None, description="Specific measure (e.g., 'ACR50 non-response at week 24')")
    endpoint_definition: Optional[str] = Field(None, description="How endpoint was defined")
    failure_definition: Optional[str] = Field(None, description="How failure was defined")
    failure_reason: Optional[str] = Field(None, description="Primary reason: inadequate response, intolerance, etc.")

    # Treatment context
    line_of_therapy: Optional[str] = Field(None, description="Which line: 1L, 2L, etc.")
    specific_therapy: Optional[str] = Field(None, description="Specific drug/regimen that failed")
    time_to_failure: Optional[str] = Field(None, description="Time period (e.g., '6 months', '1 year')")
    timepoint_type: Optional[str] = Field(None, description="Type: fixed, median, cumulative")

    # Denominator context
    patient_population: Optional[str] = Field(None, description="Population studied (e.g., 'moderate-severe RA, MTX-naive')")
    denominator_n: Optional[int] = Field(None, description="Sample size in the analysis")
    analysis_type: Optional[str] = Field(None, description="Analysis type: ITT, per_protocol, as_treated")

    # Switching vs discontinuation (important for market sizing)
    switch_rate_pct: Optional[float] = Field(None, ge=0, le=100, description="% who switched to another therapy")
    switch_destination: Optional[str] = Field(None, description="What they switched to (e.g., 'TNF inhibitor')")
    full_discontinuation_pct: Optional[float] = Field(None, ge=0, le=100, description="% who stopped all treatment")

    # Methodology
    methodology: Optional[str] = Field(None, description="Study type: RCT, registry, claims, etc.")
    notes: Optional[str] = Field(None, description="Important caveats")


class TreatmentEstimate(SourceEstimate):
    """Treatment rate estimate from a single source."""
    pct_treated: Optional[float] = Field(None, ge=0, le=100, description="Percentage receiving treatment")
    treatment_definition: Optional[str] = Field(None, description="How 'treated' was defined")
    notes: Optional[str] = None


class PrevalenceData(BaseModel):
    """Prevalence/epidemiology data for a disease - aggregated from multiple sources."""
    # Consensus estimate (median or best estimate)
    total_patients: Optional[int] = Field(None, ge=0, description="Total US patient population (consensus)")
    adult_patients: Optional[int] = Field(None, ge=0, description="Adult patients")
    pediatric_patients: Optional[int] = Field(None, ge=0, description="Pediatric patients")
    prevalence_source: Optional[str] = Field(None, description="Primary source name")
    prevalence_source_url: Optional[str] = Field(None, description="Source URL")
    prevalence_year: Optional[int] = Field(None, ge=1990, le=2030, description="Year of prevalence data")
    confidence: Optional[str] = Field(None, description="Confidence level: 'High', 'Medium', 'Low'")

    # All source estimates for transparency
    source_estimates: List[PrevalenceEstimate] = Field(default_factory=list, description="Individual estimates from each source")
    estimate_range: Optional[str] = Field(None, description="Range of estimates (e.g., '180,000 - 320,000')")
    methodology_notes: Optional[str] = Field(None, description="Notes on how consensus was derived")


class PatientSegmentation(BaseModel):
    """Patient segmentation data."""
    pct_diagnosed: Optional[float] = Field(None, ge=0, le=100, description="Percentage diagnosed")
    pct_treated: Optional[float] = Field(None, ge=0, le=100, description="Percentage receiving any treatment (consensus)")
    pct_treated_source: Optional[str] = Field(None, description="Primary source for treatment rate")
    severity: Optional[SeverityBreakdown] = None
    subpopulations: List[Subpopulation] = Field(default_factory=list)

    # Per-source treatment rate tracking
    treatment_estimates: List[TreatmentEstimate] = Field(default_factory=list, description="Individual treatment rate estimates from each source")
    treatment_rate_range: Optional[str] = Field(None, description="Range of treatment rate estimates")
    treatment_rate_confidence: Optional[str] = Field(None, description="Confidence: High, Medium, Low")
    treatment_rate_confidence_rationale: Optional[str] = Field(None, description="Why this confidence level")


class FailureRates(BaseModel):
    """Treatment failure/inadequate response rates - aggregated from multiple sources."""
    # Consensus estimates (median)
    fail_1L_pct: Optional[float] = Field(None, ge=0, le=100, description="Percentage failing first-line (consensus)")
    fail_1L_reason: Optional[str] = Field(None, description="Primary reason for 1L failure")
    fail_1L_source: Optional[str] = Field(None, description="Primary source for 1L failure rate")
    fail_1L_source_count: Optional[int] = Field(None, description="Number of sources contributing to 1L estimate")
    primary_failure_type: Optional[str] = Field(None, description="Most common failure type: primary_nonresponse, secondary_loss, intolerance")
    fail_2L_pct: Optional[float] = Field(None, ge=0, le=100, description="Percentage failing second-line")
    fail_2L_reason: Optional[str] = Field(None, description="Primary reason for 2L failure")
    source: Optional[str] = Field(None, description="Primary source for failure rate data (deprecated, use fail_1L_source)")

    # Switch vs discontinuation (important for market sizing)
    switch_rate_1L_pct: Optional[float] = Field(None, ge=0, le=100, description="% of 1L failures who switch to another therapy")
    discontinuation_rate_1L_pct: Optional[float] = Field(None, ge=0, le=100, description="% of 1L failures who discontinue all treatment")
    standardized_timepoint: Optional[str] = Field(None, description="Timepoint for comparison (e.g., '6 months', '12 months')")

    # Confidence assessment
    confidence: Optional[str] = Field(None, description="Confidence level: High, Medium, Low")
    confidence_rationale: Optional[str] = Field(None, description="Why this confidence level")

    # All source estimates for transparency
    source_estimates: List[FailureRateEstimate] = Field(default_factory=list, description="Individual estimates from each source")
    estimate_range: Optional[str] = Field(None, description="Range of estimates (e.g., '50% - 70%')")
    methodology_notes: Optional[str] = Field(None, description="Notes on how consensus was derived")


class MarketFunnel(BaseModel):
    """Calculated market funnel from prevalence to addressable market."""
    total_patients: int = Field(..., ge=0, description="Total patient population")
    patients_treated: int = Field(..., ge=0, description="Patients on treatment")
    patients_fail_1L: int = Field(..., ge=0, description="Patients failing 1L (qualify for 2L)")
    patients_addressable_2L: int = Field(..., ge=0, description="Addressable market for 2L")

    # Optional 3L funnel
    patients_fail_2L: Optional[int] = Field(None, ge=0, description="Patients failing 2L")
    patients_addressable_3L: Optional[int] = Field(None, ge=0, description="Addressable for 3L")

    # Market sizing
    avg_annual_cost_2L: Optional[float] = Field(None, description="Average annual cost for 2L therapy")
    market_size_2L_usd: Optional[int] = Field(None, ge=0, description="Total market size for 2L in USD")
    market_size_2L_formatted: Optional[str] = Field(None, description="Formatted market size (e.g., '$5.5B')")

    # Methodology
    calculation_notes: Optional[str] = Field(None, description="Notes on calculation methodology")


class DiseaseSource(BaseModel):
    """A literature source used for disease intelligence."""
    pmid: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    authors: Optional[str] = None
    journal: Optional[str] = None
    publication_year: Optional[int] = None

    source_type: str = Field(..., description="Type: 'epidemiology', 'treatment_guideline', 'real_world', 'market_report'")
    data_extracted: Optional[Dict[str, Any]] = Field(None, description="What data was extracted")
    quality_tier: Optional[str] = Field(None, description="Quality: 'Tier 1', 'Tier 2', 'Tier 3'")

    abstract: Optional[str] = None
    full_text_available: bool = False
    relevant_excerpts: Optional[List[str]] = None


class DiseaseIntelligence(BaseModel):
    """Complete disease intelligence record."""
    disease_id: Optional[int] = None
    disease_name: str = Field(..., description="Canonical disease name")
    disease_aliases: List[str] = Field(default_factory=list, description="Alternative names")
    therapeutic_area: Optional[str] = Field(None, description="Therapeutic area (e.g., 'Autoimmune', 'Oncology')")

    # Core data
    prevalence: PrevalenceData = Field(default_factory=PrevalenceData)
    segmentation: PatientSegmentation = Field(default_factory=PatientSegmentation)
    treatment_paradigm: TreatmentParadigm = Field(default_factory=TreatmentParadigm)
    failure_rates: FailureRates = Field(default_factory=FailureRates)
    market_funnel: Optional[MarketFunnel] = None

    # Sources
    sources: List[DiseaseSource] = Field(default_factory=list)

    # Metadata
    data_quality: Optional[str] = Field(None, description="Overall data quality: 'High', 'Medium', 'Low'")
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def calculate_market_funnel(self) -> MarketFunnel:
        """Calculate market funnel from prevalence and failure rates."""
        total = self.prevalence.total_patients or 0
        pct_treated = self.segmentation.pct_treated or 0
        fail_1L_pct = self.failure_rates.fail_1L_pct or 0

        patients_treated = int(total * pct_treated / 100)
        patients_fail_1L = int(patients_treated * fail_1L_pct / 100)

        # Get average 2L cost from treatment paradigm
        avg_cost = None
        if self.treatment_paradigm.second_line and self.treatment_paradigm.second_line.drugs:
            costs = [d.wac_monthly for d in self.treatment_paradigm.second_line.drugs if d.wac_monthly]
            if costs:
                avg_cost = sum(costs) / len(costs) * 12  # Annual cost

        # Fallback: use prevalence-based tiered pricing
        # - Rare disease (<10K): $200K/year
        # - Specialty (10K-100K): $75K/year
        # - Standard (>100K): $20K/year
        if not avg_cost and total > 0:
            if total < 10000:
                avg_cost = 200000  # Rare disease
            elif total < 100000:
                avg_cost = 75000   # Specialty
            else:
                avg_cost = 20000   # Standard

        # Calculate market size
        market_size = None
        market_formatted = None
        if avg_cost and patients_fail_1L:
            market_size = int(patients_fail_1L * avg_cost)
            if market_size >= 1_000_000_000:
                market_formatted = f"${market_size / 1_000_000_000:.1f}B"
            elif market_size >= 1_000_000:
                market_formatted = f"${market_size / 1_000_000:.0f}M"
            else:
                market_formatted = f"${market_size:,}"

        self.market_funnel = MarketFunnel(
            total_patients=total,
            patients_treated=patients_treated,
            patients_fail_1L=patients_fail_1L,
            patients_addressable_2L=patients_fail_1L,
            avg_annual_cost_2L=avg_cost,
            market_size_2L_usd=market_size,
            market_size_2L_formatted=market_formatted,
        )
        return self.market_funnel

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
            Decimal: lambda v: float(v) if v else None,
        }
