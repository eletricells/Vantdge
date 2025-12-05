"""
Pydantic schemas for Drug Repurposing Case Series Agent

Defines structured data models for:
- Case series/report extraction
- Clinical evidence
- Market intelligence
- Priority scoring
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class EvidenceLevel(str, Enum):
    """Level of clinical evidence"""
    CASE_REPORT = "Case Report"
    CASE_SERIES = "Case Series"
    RETROSPECTIVE_STUDY = "Retrospective Study"
    PROSPECTIVE_STUDY = "Prospective Study"
    RANDOMIZED_TRIAL = "Randomized Trial"
    META_ANALYSIS = "Meta-Analysis"


class OutcomeResult(str, Enum):
    """Overall outcome classification"""
    SUCCESS = "Success"
    FAIL = "Fail"
    MIXED = "Mixed"
    UNKNOWN = "Unknown"


class EfficacySignal(str, Enum):
    """Strength of efficacy signal"""
    STRONG = "Strong"
    MODERATE = "Moderate"
    WEAK = "Weak"
    NONE = "None"
    UNKNOWN = "Unknown"


class SafetyProfile(str, Enum):
    """Safety profile assessment"""
    FAVORABLE = "Favorable"
    ACCEPTABLE = "Acceptable"
    CONCERNING = "Concerning"
    UNKNOWN = "Unknown"


class DevelopmentPotential(str, Enum):
    """Development potential assessment"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"


# ============================================================
# Clinical Evidence Schemas
# ============================================================

class CaseSeriesSource(BaseModel):
    """Source information for a case series/report"""
    pmid: Optional[str] = Field(None, description="PubMed ID")
    doi: Optional[str] = Field(None, description="Digital Object Identifier")
    url: Optional[str] = Field(None, description="Source URL")
    title: str = Field(..., description="Publication title")
    authors: Optional[str] = Field(None, description="Authors list")
    journal: Optional[str] = Field(None, description="Journal name")
    year: Optional[int] = Field(None, description="Publication year")
    citation: Optional[str] = Field(None, description="Full citation string")
    publication_venue: str = Field("Unknown", description="Peer-reviewed journal, Conference abstract, etc.")
    is_open_access: bool = Field(False, description="Whether paper is open access")


class PatientPopulation(BaseModel):
    """Patient characteristics from case series"""
    n_patients: Optional[int] = Field(None, description="Number of patients")
    age_description: Optional[str] = Field(None, description="Age range or mean")
    sex_distribution: Optional[str] = Field(None, description="Sex distribution")
    prior_treatments_failed: Optional[List[str]] = Field(None, description="Prior treatments that failed")
    disease_severity: Optional[str] = Field(None, description="Disease severity at baseline")
    comorbidities: Optional[List[str]] = Field(None, description="Notable comorbidities")
    description: Optional[str] = Field(None, description="Free-text population description")


class TreatmentDetails(BaseModel):
    """Treatment regimen details"""
    drug_name: str = Field(..., description="Drug name used")
    generic_name: Optional[str] = Field(None, description="Generic name")
    mechanism: Optional[str] = Field(None, description="Mechanism of action")
    target: Optional[str] = Field(None, description="Molecular target")
    route_of_administration: Optional[str] = Field(None, description="Route (oral, IV, etc.)")
    dose: Optional[str] = Field(None, description="Dose used")
    frequency: Optional[str] = Field(None, description="Dosing frequency")
    duration: Optional[str] = Field(None, description="Treatment duration")
    concomitant_medications: Optional[List[str]] = Field(None, description="Other medications used")


class EfficacyOutcome(BaseModel):
    """Efficacy outcomes from case series"""
    response_rate: Optional[str] = Field(None, description="Response rate (e.g., '3/3 (100%)')")
    responders_n: Optional[int] = Field(None, description="Number of responders")
    responders_pct: Optional[float] = Field(None, description="Response percentage")
    time_to_response: Optional[str] = Field(None, description="Time to response")
    duration_of_response: Optional[str] = Field(None, description="Duration of response")
    effect_size_description: Optional[str] = Field(None, description="Effect size description")
    primary_endpoint: Optional[str] = Field(None, description="Primary efficacy endpoint")
    endpoint_result: Optional[str] = Field(None, description="Result on primary endpoint")
    durability_signal: Optional[str] = Field(None, description="Durability of response")
    efficacy_summary: Optional[str] = Field(None, description="2-3 sentence efficacy summary")


class SafetyOutcome(BaseModel):
    """Safety outcomes from case series"""
    adverse_events: Optional[List[str]] = Field(None, description="List of adverse events")
    serious_adverse_events: Optional[List[str]] = Field(None, description="Serious adverse events")
    sae_count: Optional[int] = Field(None, description="Number of patients with SAEs")
    sae_percentage: Optional[float] = Field(None, description="Percentage of patients with SAEs")
    discontinuations_n: Optional[int] = Field(None, description="Number of discontinuations")
    discontinuations_due_to_ae: Optional[int] = Field(None, description="Discontinuations due to adverse events")
    discontinuation_reasons: Optional[List[str]] = Field(None, description="Reasons for discontinuation")
    safety_summary: Optional[str] = Field(None, description="2-3 sentence safety summary")
    safety_profile: SafetyProfile = Field(SafetyProfile.UNKNOWN, description="Overall safety assessment")


class CaseSeriesExtraction(BaseModel):
    """Complete extraction from a case series/report"""
    # Source info
    source: CaseSeriesSource
    
    # Disease/indication
    disease: str = Field(..., description="Disease/condition treated")
    disease_normalized: Optional[str] = Field(None, description="Normalized disease name")
    is_off_label: bool = Field(True, description="Whether use is off-label")
    
    # Clinical data
    evidence_level: EvidenceLevel = Field(EvidenceLevel.CASE_REPORT)
    patient_population: PatientPopulation
    treatment: TreatmentDetails
    efficacy: EfficacyOutcome
    safety: SafetyOutcome
    
    # Overall assessment
    outcome_result: OutcomeResult = Field(OutcomeResult.UNKNOWN)
    efficacy_signal: EfficacySignal = Field(EfficacySignal.UNKNOWN)
    comparator_baseline: Optional[str] = Field(None, description="What was compared to")
    follow_up_duration: Optional[str] = Field(None, description="Duration of follow-up")
    key_findings: Optional[str] = Field(None, description="1-2 sentence key findings")
    
    # Metadata
    extraction_timestamp: datetime = Field(default_factory=datetime.now)
    extraction_confidence: float = Field(0.5, description="Confidence in extraction (0-1)")


# ============================================================
# Market Intelligence Schemas
# ============================================================

class EpidemiologyData(BaseModel):
    """Epidemiology data for a disease"""
    us_prevalence_estimate: Optional[str] = Field(None, description="US prevalence estimate")
    us_incidence_estimate: Optional[str] = Field(None, description="US incidence estimate")
    global_prevalence: Optional[str] = Field(None, description="Global prevalence")
    patient_population_size: Optional[int] = Field(None, description="Estimated patient count")
    prevalence_source: Optional[str] = Field(None, description="Source of prevalence data")
    prevalence_source_url: Optional[str] = Field(None, description="URL for prevalence source")
    trend: Optional[str] = Field(None, description="Trend (increasing, stable, decreasing)")


class StandardOfCareTreatment(BaseModel):
    """A standard of care treatment"""
    drug_name: str = Field(..., description="Drug name")
    drug_class: Optional[str] = Field(None, description="Drug class")
    efficacy_range: Optional[str] = Field(None, description="Efficacy range (e.g., '60-70%')")
    efficacy_pct: Optional[float] = Field(None, description="Efficacy percentage for comparison")
    annual_cost_usd: Optional[float] = Field(None, description="Annual cost in USD")
    line_of_therapy: Optional[str] = Field(None, description="Line of therapy (1L, 2L, etc.)")
    notes: Optional[str] = Field(None, description="Additional notes")


class StandardOfCareData(BaseModel):
    """Standard of care for a disease"""
    top_treatments: List[StandardOfCareTreatment] = Field(default_factory=list)
    approved_drug_names: List[str] = Field(default_factory=list, description="List of FDA-approved drug names")
    num_approved_drugs: Optional[int] = Field(0, description="Number of approved drugs for indication")
    num_pipeline_therapies: Optional[int] = Field(0, description="Number of pipeline therapies in clinical trials")
    pipeline_details: Optional[str] = Field(None, description="Details on pipeline therapies")
    avg_annual_cost_usd: Optional[float] = Field(None, description="Average annual cost of top 3 branded drugs")
    treatment_paradigm: Optional[str] = Field(None, description="Description of treatment approach")
    unmet_need: bool = Field(False, description="Whether there is unmet need")
    unmet_need_description: Optional[str] = Field(None, description="Description of unmet need")
    competitive_landscape: Optional[str] = Field(None, description="Competitive landscape summary")
    soc_source: Optional[str] = Field(None, description="Source for SOC data")


class MarketIntelligence(BaseModel):
    """Complete market intelligence for an indication"""
    disease: str = Field(..., description="Disease name")
    epidemiology: EpidemiologyData = Field(default_factory=EpidemiologyData)
    standard_of_care: StandardOfCareData = Field(default_factory=StandardOfCareData)
    market_size_estimate: Optional[str] = Field(None, description="Market size estimate")
    market_size_usd: Optional[float] = Field(None, description="Market size in USD (patient pop x avg cost)")
    growth_rate: Optional[str] = Field(None, description="Market growth rate")


# ============================================================
# Scoring Schemas
# ============================================================

class OpportunityScores(BaseModel):
    """
    Scoring for a repurposing opportunity.

    Weights: Clinical 50%, Evidence 25%, Market 25%
    """
    # Dimension scores (1-10 each)
    clinical_signal: float = Field(5.0, description="Clinical signal score (1-10, 50% weight)")
    evidence_quality: float = Field(5.0, description="Evidence quality score (1-10, 25% weight)")
    market_opportunity: float = Field(5.0, description="Market opportunity score (1-10, 25% weight)")
    overall_priority: float = Field(5.0, description="Weighted overall priority (1-10)")

    # Clinical breakdown (response rate + safety profile, averaged)
    clinical_breakdown: Optional[Dict[str, Any]] = Field(None, description="Clinical score breakdown")
    response_rate_score: float = Field(5.0, description="Response rate score (1-10)")
    safety_profile_score: float = Field(5.0, description="Safety profile score based on SAE % (1-10)")

    # Evidence breakdown (sample size + venue + followup, averaged)
    evidence_breakdown: Optional[Dict[str, Any]] = Field(None, description="Evidence score breakdown")
    sample_size_score: float = Field(5.0, description="Sample size score (1-10)")
    publication_venue_score: float = Field(5.0, description="Publication venue score (1-10)")
    followup_duration_score: float = Field(5.0, description="Follow-up duration score (1-10)")

    # Market breakdown (competitors + market size + unmet need, averaged)
    market_breakdown: Optional[Dict[str, Any]] = Field(None, description="Market score breakdown")
    competitors_score: float = Field(5.0, description="Number of competitors score (1-10)")
    market_size_score: float = Field(5.0, description="Market size score (1-10)")
    unmet_need_score: float = Field(5.0, description="Unmet need score (1-10)")


# ============================================================
# Complete Opportunity Schema
# ============================================================

class RepurposingOpportunity(BaseModel):
    """Complete repurposing opportunity with all data"""
    # Core data
    extraction: CaseSeriesExtraction

    # Market intelligence
    market_intelligence: Optional[MarketIntelligence] = None

    # Scoring
    scores: OpportunityScores = Field(default_factory=OpportunityScores)

    # Ranking
    rank: Optional[int] = Field(None, description="Rank among opportunities")


# ============================================================
# Analysis Results Schemas
# ============================================================

class DrugAnalysisResult(BaseModel):
    """Complete analysis result for a drug"""
    drug_name: str = Field(..., description="Drug analyzed")
    generic_name: Optional[str] = Field(None, description="Generic name")
    mechanism: Optional[str] = Field(None, description="Mechanism of action")
    target: Optional[str] = Field(None, description="Molecular target")
    approved_indications: List[str] = Field(default_factory=list, description="FDA-approved indications")

    # Opportunities found
    opportunities: List[RepurposingOpportunity] = Field(default_factory=list)

    # Metadata
    analysis_date: datetime = Field(default_factory=datetime.now)
    search_queries_used: List[str] = Field(default_factory=list)
    papers_screened: int = Field(0, description="Total papers screened")
    papers_extracted: int = Field(0, description="Papers with data extracted")

    # Cost tracking
    total_input_tokens: int = Field(0)
    total_output_tokens: int = Field(0)
    estimated_cost_usd: float = Field(0.0)


class MechanismAnalysisResult(BaseModel):
    """Analysis result for a mechanism class"""
    mechanism: str = Field(..., description="Mechanism analyzed")
    drugs_analyzed: List[DrugAnalysisResult] = Field(default_factory=list)
    total_opportunities: int = Field(0)
    analysis_date: datetime = Field(default_factory=datetime.now)
    total_cost_usd: float = Field(0.0)

