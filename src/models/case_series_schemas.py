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
    PROSPECTIVE_COHORT = "Prospective Cohort"
    PROSPECTIVE_STUDY = "Prospective Study"  # Legacy - maps to Prospective Cohort
    CONTROLLED_TRIAL = "Controlled Trial"
    RCT = "RCT"
    RANDOMIZED_TRIAL = "Randomized Trial"  # Legacy - maps to RCT
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


class ExtractionConfidence(BaseModel):
    """Confidence assessment for extraction quality"""
    disease_certainty: str = Field("Medium", description="High/Medium/Low - certainty about disease identification")
    n_patients_certainty: str = Field("Medium", description="High/Medium/Low - certainty about patient count")
    efficacy_data_quality: str = Field("Partial", description="Complete/Partial/Sparse - quality of efficacy data")
    safety_data_quality: str = Field("Partial", description="Complete/Partial/Sparse - quality of safety data")
    data_source: str = Field("Abstract only", description="Abstract only/Full text/Tables available")
    limiting_factors: List[str] = Field(default_factory=list, description="List of issues limiting extraction quality")


class DevelopmentPotential(str, Enum):
    """Development potential assessment"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    UNKNOWN = "Unknown"


class OutcomeMetricType(str, Enum):
    """Type of efficacy metric being reported.

    Critical for proper interpretation:
    - EFFICACY_RESPONSE: Clinical improvement (e.g., ACR50, PASI75, symptom improvement)
    - DRUG_SURVIVAL: % patients remaining on drug over time (NOT efficacy)
    - DRUG_RETENTION: Same as survival, often used interchangeably
    - REMISSION: Disease remission rate
    - DISCONTINUATION: % patients stopping drug (inverse of survival)
    - COMPOSITE: Combined endpoint with multiple components
    - OTHER: Other metric types
    """
    EFFICACY_RESPONSE = "Efficacy Response"
    DRUG_SURVIVAL = "Drug Survival"
    DRUG_RETENTION = "Drug Retention"
    REMISSION = "Remission"
    DISCONTINUATION = "Discontinuation"
    COMPOSITE = "Composite"
    OTHER = "Other"


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
    metric_type: Optional[str] = Field(
        "Efficacy Response",
        description="Type of metric: 'Efficacy Response' (clinical improvement), 'Drug Survival' (retention on drug), 'Remission', 'Discontinuation', 'Other'"
    )
    metric_type_confidence: Optional[str] = Field(
        "High",
        description="Confidence in metric type classification: High/Medium/Low"
    )
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


class DetailedEfficacyEndpoint(BaseModel):
    """Detailed efficacy endpoint from multi-stage extraction"""
    endpoint_name: str = Field(..., description="Name of the endpoint (original)")
    endpoint_normalized: Optional[str] = Field(None, description="Standardized endpoint name from taxonomy")
    endpoint_category: str = Field("Other", description="Primary/Secondary/Exploratory")
    timepoint: Optional[str] = Field(None, description="Measurement timepoint")
    measurement_type: Optional[str] = Field(None, description="Responder/Change from baseline/Absolute")
    value: Optional[float] = Field(None, description="Numerical value")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    total_n: Optional[int] = Field(None, description="Total number of patients evaluated")
    responders_n: Optional[int] = Field(None, description="Number of responders")
    responders_pct: Optional[float] = Field(None, description="Percentage of responders")
    baseline_value: Optional[float] = Field(None, description="Baseline value")
    final_value: Optional[float] = Field(None, description="Final/post-treatment value")
    change_from_baseline: Optional[float] = Field(None, description="Change from baseline")
    change_pct: Optional[float] = Field(None, description="Percentage change")
    p_value: Optional[str] = Field(None, description="P-value if reported")
    confidence_interval: Optional[str] = Field(None, description="95% CI if reported")
    statistical_significance: Optional[bool] = Field(None, description="Whether statistically significant")
    notes: Optional[str] = Field(None, description="Additional notes")

    # New fields from prompt improvements
    organ_domain: Optional[str] = Field(None, description="Organ domain: Musculoskeletal/Mucocutaneous/Renal/Neurological/Hematological/Cardiopulmonary/Immunological/Systemic/Gastrointestinal/Ocular/Constitutional")
    is_validated_instrument: Optional[bool] = Field(None, description="Whether this is a validated clinical instrument")
    instrument_quality_tier: Optional[int] = Field(None, description="Quality tier: 1=gold standard, 2=validated PRO, 3=investigator-assessed")
    is_biomarker: Optional[bool] = Field(None, description="True if this is a laboratory biomarker (CRP, LDH, complement, cytokines, etc.) rather than clinical endpoint")

    @property
    def is_primary(self) -> bool:
        """Derived property: True if endpoint_category is 'Primary'"""
        return self.endpoint_category.lower() == 'primary' if self.endpoint_category else False


class DetailedSafetyEndpoint(BaseModel):
    """Detailed safety endpoint from multi-stage extraction"""
    event_name: str = Field(..., description="Name of the adverse event")
    event_category: str = Field("AE", description="AE/SAE/AESI/Discontinuation")
    severity_grade: Optional[str] = Field(None, description="Severity grade if reported")
    patients_affected_n: Optional[int] = Field(None, description="Number of patients affected")
    patients_affected_pct: Optional[float] = Field(None, description="Percentage of patients affected")
    events_total: Optional[int] = Field(None, description="Total number of events")
    relatedness: Optional[str] = Field(None, description="Related/Possibly related/Unrelated")
    outcome: Optional[str] = Field(None, description="Resolved/Ongoing/Fatal")
    action_taken: Optional[str] = Field(None, description="Dose reduced/Discontinued/None")
    notes: Optional[str] = Field(None, description="Additional notes")

    # New fields from prompt improvements - MedDRA-aligned categories
    category_soc: Optional[str] = Field(None, description="System Organ Class: Infections/Malignancies/Cardiovascular/Thromboembolic/Hepatotoxicity/Cytopenias/GI Perforation/Hypersensitivity/Neurological/Pulmonary/Renal/Death/Metabolic")
    infection_type: Optional[str] = Field(None, description="For infections: Bacterial/Viral/Fungal/Mycobacterial/Opportunistic/Herpes Zoster")
    malignancy_type: Optional[str] = Field(None, description="For malignancies: Hematologic/Solid Tumor/NMSC")
    cv_type: Optional[str] = Field(None, description="For cardiovascular: MACE/Heart Failure/Arrhythmia")
    thromboembolic_type: Optional[str] = Field(None, description="For thromboembolic: VTE/DVT/PE/Arterial")
    is_class_effect: Optional[bool] = Field(None, description="Whether this is a known effect for this drug class")


class BiomarkerResult(BaseModel):
    """Structured biomarker data extracted from case series"""
    biomarker_name: str = Field(..., description="Name of the biomarker (e.g., 'LDH', 'CXCL9', 'CRP')")
    biomarker_category: Optional[str] = Field(None, description="Category: Inflammatory/Complement/Autoantibody/Enzyme/Cytokine/Other")
    baseline_value: Optional[float] = Field(None, description="Baseline/pre-treatment value")
    baseline_unit: Optional[str] = Field(None, description="Unit for baseline value")
    final_value: Optional[float] = Field(None, description="Final/post-treatment value")
    change_direction: Optional[str] = Field(None, description="Increased/Decreased/No change")
    change_pct: Optional[float] = Field(None, description="Percentage change from baseline")
    is_beneficial: Optional[bool] = Field(None, description="True if change is in expected/therapeutic direction")
    p_value: Optional[str] = Field(None, description="Statistical significance if reported")
    supports_mechanism: Optional[bool] = Field(None, description="True if biomarker change supports drug's mechanism")
    notes: Optional[str] = Field(None, description="Additional context")


class StudyDesign(str, Enum):
    """Study design classification"""
    CASE_REPORT = "Case Report"
    CASE_SERIES = "Case Series"
    RETROSPECTIVE = "Retrospective"
    PROSPECTIVE_OPEN_LABEL = "Prospective Open-Label"
    PROSPECTIVE_CONTROLLED = "Prospective Controlled"
    RANDOMIZED_CONTROLLED_TRIAL = "Randomized Controlled Trial"
    DOUBLE_BLIND_RCT = "Double-Blind RCT"
    OPEN_LABEL_RCT = "Open-Label RCT"
    UNKNOWN = "Unknown"


class ResponseDefinitionQuality(str, Enum):
    """Quality of response definition used in study"""
    IMPLICIT = "Implicit"  # "Patient improved"
    AUTHOR_DEFINED = "Author-Defined"  # Custom criteria
    DISEASE_SPECIFIC = "Disease-Specific"  # Disease-specific but not regulatory
    REGULATORY = "Regulatory"  # ACR/EULAR, PASI, etc.
    UNKNOWN = "Unknown"


class IndividualStudyScore(BaseModel):
    """Scoring breakdown for an individual case series study"""
    total_score: float = Field(..., description="Overall score 1-10")

    # Dimension scores (1-10 each)
    efficacy_score: float = Field(..., description="Efficacy/quantitative rigor score")
    sample_size_score: float = Field(..., description="Sample size score")
    endpoint_quality_score: float = Field(..., description="Endpoint quality score")
    biomarker_score: float = Field(..., description="Biomarker support score")
    response_definition_score: float = Field(..., description="Response definition quality score")
    followup_score: float = Field(..., description="Follow-up duration score")

    # Dimension weights used
    weights: Dict[str, float] = Field(
        default_factory=lambda: {
            "efficacy": 0.35,
            "sample_size": 0.15,
            "endpoint_quality": 0.10,
            "biomarker": 0.15,
            "response_definition": 0.15,
            "followup": 0.10,
        }
    )

    # Scoring rationale
    scoring_notes: Optional[str] = Field(None, description="Notes explaining the scoring")


class AggregateScore(BaseModel):
    """Aggregate scoring across multiple studies for a disease"""
    aggregate_score: float = Field(..., description="N-weighted average of individual scores")
    study_count: int = Field(..., description="Number of studies included")
    total_patients: int = Field(..., description="Total patients across studies")

    # Best paper info
    best_paper_pmid: Optional[str] = Field(None, description="PMID of highest-scoring paper")
    best_paper_score: Optional[float] = Field(None, description="Score of best paper")

    # Consistency metrics
    consistency_level: Optional[str] = Field(None, description="High/Moderate/Low based on CV")
    response_rate_cv: Optional[float] = Field(None, description="Coefficient of variation of response rates")

    # Individual scores
    individual_scores: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of {pmid, n_patients, score} for each study"
    )


class CaseSeriesExtraction(BaseModel):
    """Complete extraction from a case series/report"""
    # Source info
    source: CaseSeriesSource

    # Disease/indication
    disease: str = Field(..., description="Disease/condition treated")
    disease_normalized: Optional[str] = Field(None, description="Normalized/canonical disease name")
    disease_subtype: Optional[str] = Field(None, description="Disease subtype (e.g., 'Amyopathic' for Dermatomyositis)")
    disease_category: Optional[str] = Field(None, description="Top-level disease category (e.g., 'Inflammatory Myopathies')")
    disease_raw: Optional[str] = Field(None, description="Original disease text before normalization")
    parent_disease: Optional[str] = Field(None, description="Parent disease for hierarchy grouping (e.g., 'SLE' for 'Lupus Nephritis')")
    score_explanation: Optional[str] = Field(None, description="AI-generated explanation of how the score was derived")
    is_off_label: bool = Field(True, description="Whether use is off-label")
    is_relevant: bool = Field(True, description="Whether paper is relevant for drug repurposing (set by LLM during extraction)")

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

    # Multi-stage extraction detailed data
    detailed_efficacy_endpoints: List[DetailedEfficacyEndpoint] = Field(
        default_factory=list,
        description="Detailed efficacy endpoints from multi-stage extraction"
    )
    detailed_safety_endpoints: List[DetailedSafetyEndpoint] = Field(
        default_factory=list,
        description="Detailed safety endpoints from multi-stage extraction"
    )

    # New fields for refined scoring (Phase 2)
    study_design: Optional[str] = Field(
        None,
        description="Study design: Case Report, Case Series, Retrospective, Prospective Open-Label"
    )
    biomarkers: List[BiomarkerResult] = Field(
        default_factory=list,
        description="Biomarker results extracted from the study"
    )
    response_definition_quality: Optional[str] = Field(
        None,
        description="Quality of response definition: Implicit, Author-Defined, Disease-Specific, Regulatory"
    )
    follow_up_weeks: Optional[float] = Field(
        None,
        description="Follow-up duration in weeks (numeric for scoring)"
    )

    # Scoring results
    individual_score: Optional[IndividualStudyScore] = Field(
        None,
        description="Individual study score breakdown"
    )

    # Extraction metadata
    extraction_timestamp: datetime = Field(default_factory=datetime.now)
    extraction_confidence: float = Field(0.5, description="Confidence in extraction (0-1) - DEPRECATED, use extraction_confidence_detail")
    extraction_confidence_detail: Optional[ExtractionConfidence] = Field(None, description="Detailed confidence assessment from main_extraction prompt")
    extraction_method: str = Field("single_pass", description="single_pass or multi_stage")
    extraction_stages_completed: List[str] = Field(
        default_factory=list,
        description="List of extraction stages completed"
    )
    data_sections_identified: Optional[Dict[str, Any]] = Field(
        None,
        description="Sections identified in Stage 1 (tables, figures, etc.)"
    )


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

    # New fields from prompt improvements
    source_quality: Optional[str] = Field(None, description="Primary/Secondary/Estimate - quality of data source")
    data_year: Optional[int] = Field(None, description="Year the prevalence data is from")
    geographic_scope: Optional[str] = Field(None, description="US/Global/Regional - geographic scope of data")
    confidence: Optional[str] = Field(None, description="High/Medium/Low - confidence in estimate")
    notes: Optional[str] = Field(None, description="Caveats about the estimate")


class StandardOfCareTreatment(BaseModel):
    """A standard of care treatment"""
    drug_name: str = Field(..., description="Drug name")
    drug_class: Optional[str] = Field(None, description="Drug class")
    is_branded_innovative: bool = Field(False, description="True if branded innovative drug (biologic, novel small molecule)")
    fda_approved: bool = Field(False, description="True if FDA-approved for this EXACT indication")
    fda_approved_indication: Optional[str] = Field(None, description="The exact indication name from FDA label")
    efficacy_range: Optional[str] = Field(None, description="Efficacy range (e.g., '60-70%')")
    efficacy_pct: Optional[float] = Field(None, description="Efficacy percentage for comparison")
    annual_cost_usd: Optional[float] = Field(None, description="Annual cost in USD")
    line_of_therapy: Optional[str] = Field(None, description="Line of therapy (1L, 2L, etc.)")
    notes: Optional[str] = Field(None, description="Additional notes")
    # New fields for approval confidence tracking
    approval_year: Optional[int] = Field(None, description="Year of FDA approval")
    approval_confidence: str = Field("Medium", description="Confidence in approval status: High/Medium/Low")
    approval_evidence: Optional[str] = Field(None, description="Evidence supporting approval status (e.g., 'FDA label', 'Drugs@FDA')")


class PipelineTherapy(BaseModel):
    """A drug in clinical development pipeline"""
    drug_name: str = Field(..., description="Drug name or code")
    company: Optional[str] = Field(None, description="Sponsoring company")
    mechanism: Optional[str] = Field(None, description="Mechanism of action")
    phase: Optional[str] = Field("Unknown", description="Trial phase (Phase 1, 2, 3)")
    trial_id: Optional[str] = Field(None, description="ClinicalTrials.gov ID (NCT number)")
    expected_completion: Optional[str] = Field(None, description="Expected completion date")
    # New fields for enhanced pipeline tracking
    trial_name: Optional[str] = Field(None, description="Trial acronym or name (e.g., 'TULIP-2')")
    status: Optional[str] = Field(None, description="Trial status (Recruiting, Active, Completed, etc.)")
    regulatory_designations: Optional[str] = Field(None, description="Regulatory designations (Breakthrough, Fast Track, Orphan, etc.)")
    notes: Optional[str] = Field(None, description="Additional notes about the trial")


class StandardOfCareData(BaseModel):
    """Standard of care for a disease"""
    top_treatments: List[StandardOfCareTreatment] = Field(default_factory=list)
    approved_drug_names: List[str] = Field(default_factory=list, description="List of FDA-approved branded innovative drug names")
    num_approved_drugs: Optional[int] = Field(0, description="Number of FDA-approved branded innovative drugs")
    num_pipeline_therapies: Optional[int] = Field(0, description="Number of drugs in active clinical trials (Phase 1-3)")
    pipeline_therapies: List[PipelineTherapy] = Field(default_factory=list, description="Detailed pipeline therapy list")
    pipeline_details: Optional[str] = Field(None, description="Summary of pipeline therapies")
    avg_annual_cost_usd: Optional[float] = Field(None, description="Average annual cost of top 3 branded drugs")
    treatment_paradigm: Optional[str] = Field(None, description="Description of treatment approach")
    unmet_need: bool = Field(False, description="Whether there is unmet need")
    unmet_need_description: Optional[str] = Field(None, description="Description of unmet need")
    competitive_landscape: Optional[str] = Field(None, description="Competitive landscape summary")
    soc_source: Optional[str] = Field(None, description="Source for SOC data")
    # New fields for enhanced pipeline data quality tracking
    phase_3_count: int = Field(0, description="Number of Phase 3 trials")
    phase_2_count: int = Field(0, description="Number of Phase 2 trials")
    key_catalysts: Optional[str] = Field(None, description="Key upcoming catalysts (data readouts, FDA decisions)")
    pipeline_data_quality: str = Field("Unknown", description="Pipeline data quality: High/Medium/Low/Unknown")
    recent_approvals: Optional[str] = Field(None, description="Recent drug approvals in this indication")
    data_quality: str = Field("Unknown", description="Overall data quality: High/Medium/Low/Unknown")
    data_quality_notes: Optional[str] = Field(None, description="Notes about data quality or limitations")


class AttributedSource(BaseModel):
    """A source with attribution to specific data elements"""
    url: Optional[str] = Field(None, description="Source URL")
    title: Optional[str] = Field(None, description="Source title/name")
    attribution: str = Field(..., description="What this source is used for (e.g., 'Epidemiology', 'TAM Analysis')")


class MarketIntelligence(BaseModel):
    """Complete market intelligence for an indication"""
    disease: str = Field(..., description="Disease name")
    parent_disease: Optional[str] = Field(None, description="Parent/canonical disease name for subtypes (e.g., 'Lupus' for 'Lupus Nephritis')")
    epidemiology: EpidemiologyData = Field(default_factory=EpidemiologyData)
    standard_of_care: StandardOfCareData = Field(default_factory=StandardOfCareData)
    # Simple market sizing (patient pop x avg cost) - kept for backward compatibility
    market_size_estimate: Optional[str] = Field(None, description="Simple market size estimate (patient pop x cost)")
    market_size_usd: Optional[float] = Field(None, description="Simple market size in USD")
    growth_rate: Optional[str] = Field(None, description="Market growth rate")
    # TAM analysis - more sophisticated market sizing
    tam_usd: Optional[float] = Field(None, description="Total Addressable Market in USD")
    tam_estimate: Optional[str] = Field(None, description="TAM formatted string (e.g., '$2.5B')")
    tam_rationale: Optional[str] = Field(None, description="Detailed explanation of TAM calculation assumptions")
    # Source tracking - attributed sources for transparency
    tam_sources: List[str] = Field(default_factory=list, description="Source URLs used for TAM analysis")
    pipeline_sources: List[str] = Field(default_factory=list, description="Source URLs used for pipeline data")
    attributed_sources: List[AttributedSource] = Field(default_factory=list, description="All sources with attributions")


# ============================================================
# Scoring Schemas
# ============================================================

class OpportunityScores(BaseModel):
    """
    Scoring for a repurposing opportunity.

    Enhanced scoring v2 with quality-weighted efficacy:
    - Clinical Signal (50%): response rate (quality-weighted, 40%), safety (40%), organ domain (20%)
    - Evidence Quality (25%): sample size (35%), venue (25%), durability (25%), completeness (15%)
    - Market Opportunity (25%): competitors (33%), market size (33%), unmet need (33%)

    Note: endpoint_quality_score is deprecated - quality is now baked into response_rate_score
    via multi-endpoint quality weighting.
    """
    # Dimension scores (1-10 each)
    clinical_signal: float = Field(5.0, description="Clinical signal score (1-10, 50% weight)")
    evidence_quality: float = Field(5.0, description="Evidence quality score (1-10, 25% weight)")
    market_opportunity: float = Field(5.0, description="Market opportunity score (1-10, 25% weight)")
    overall_priority: float = Field(5.0, description="Weighted overall priority (1-10)")

    # Clinical breakdown (v2: quality-weighted efficacy, no separate endpoint_quality)
    clinical_breakdown: Optional[Dict[str, Any]] = Field(None, description="Clinical score breakdown with efficacy_endpoint_count, efficacy_concordance")
    response_rate_score: float = Field(5.0, description="Response rate score with quality weighting (1-10)")
    safety_profile_score: float = Field(5.0, description="Safety profile score based on SAE % and signal categories (1-10)")
    endpoint_quality_score: Optional[float] = Field(None, description="DEPRECATED: Now baked into response_rate_score via quality weighting")
    organ_domain_score: float = Field(5.0, description="Organ domain breadth score (1-10)")

    # Evidence breakdown (enhanced with extraction completeness)
    evidence_breakdown: Optional[Dict[str, Any]] = Field(None, description="Evidence score breakdown")
    sample_size_score: float = Field(5.0, description="Sample size score (1-10)")
    publication_venue_score: float = Field(5.0, description="Publication venue score (1-10)")
    followup_duration_score: float = Field(5.0, description="Follow-up duration/durability score (1-10)")
    extraction_completeness_score: float = Field(5.0, description="Data extraction completeness score (1-10)")

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

    # Aggregate scoring (for disease-level aggregation)
    aggregate_score: Optional[AggregateScore] = Field(
        None, description="Aggregate score across all studies for this disease"
    )

    # Ranking
    rank: Optional[int] = Field(None, description="Rank among opportunities")


# ============================================================
# Analysis Results Schemas
# ============================================================

class PaperForManualReview(BaseModel):
    """Paper that passed filters but couldn't extract full text - needs manual review."""
    pmid: Optional[str] = Field(None, description="PubMed ID")
    doi: Optional[str] = Field(None, description="DOI")
    title: str = Field("", description="Paper title")
    authors: Optional[str] = Field(None, description="Authors")
    journal: Optional[str] = Field(None, description="Journal name")
    year: Optional[int] = Field(None, description="Publication year")
    abstract: Optional[str] = Field(None, description="Abstract text")
    disease: Optional[str] = Field(None, description="Disease extracted from abstract")
    # N extraction from abstract
    n_patients: Optional[int] = Field(None, description="Patient count (extracted from abstract)")
    n_confidence: str = Field("Unknown", description="Confidence in N extraction: High, Medium, Low, Unknown")
    # Efficacy info from abstract
    response_rate: Optional[str] = Field(None, description="Response rate if mentioned (e.g., '80%', '5/6')")
    primary_endpoint: Optional[str] = Field(None, description="Primary endpoint if mentioned")
    efficacy_mention: Optional[str] = Field(None, description="Brief efficacy summary from abstract")
    # Why this needs manual review
    reason: str = Field("Abstract only - full text not available", description="Reason for manual review")
    has_full_text: bool = Field(False, description="Whether full text was available")
    extraction_method: str = Field("single_pass", description="Extraction method used")


class DrugAnalysisResult(BaseModel):
    """Complete analysis result for a drug"""
    drug_name: str = Field(..., description="Drug analyzed")
    generic_name: Optional[str] = Field(None, description="Generic name")
    mechanism: Optional[str] = Field(None, description="Mechanism of action")
    target: Optional[str] = Field(None, description="Molecular target")
    approved_indications: List[str] = Field(default_factory=list, description="FDA-approved indications")

    # Opportunities found
    opportunities: List[RepurposingOpportunity] = Field(default_factory=list)

    # Papers requiring manual review (abstract-only extractions)
    papers_for_manual_review: List[PaperForManualReview] = Field(
        default_factory=list,
        description="Papers that passed filters but need manual review (no full text access)"
    )

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
    """Analysis result for a mechanism class (multi-drug analysis)"""
    mechanism_target: str = Field(..., description="Mechanism/target analyzed (e.g., 'JAK1', 'IL-6')")
    drugs_analyzed: List[str] = Field(default_factory=list, description="Drug names that were successfully analyzed")
    drugs_failed: Dict[str, str] = Field(default_factory=dict, description="Drugs that failed: {drug_name: error_message}")
    opportunities: List[RepurposingOpportunity] = Field(default_factory=list, description="All opportunities ranked together")
    drug_results: Dict[str, "DrugAnalysisResult"] = Field(default_factory=dict, description="Individual results by drug name")
    analysis_date: datetime = Field(default_factory=datetime.now)

    # Papers requiring manual review (aggregated across all drugs)
    papers_for_manual_review: List[PaperForManualReview] = Field(
        default_factory=list,
        description="Papers that passed filters but need manual review (no full text access)"
    )

    # Aggregate metrics
    papers_screened: int = Field(0, description="Total papers screened across all drugs")
    papers_extracted: int = Field(0, description="Total papers extracted across all drugs")
    total_input_tokens: int = Field(0)
    total_output_tokens: int = Field(0)
    estimated_cost_usd: float = Field(0.0)

    @property
    def total_opportunities(self) -> int:
        """Total number of opportunities found."""
        return len(self.opportunities)

    @property
    def successful_drugs(self) -> int:
        """Number of drugs successfully analyzed."""
        return len(self.drugs_analyzed)

    @property
    def failed_drug_count(self) -> int:
        """Number of drugs that failed analysis."""
        return len(self.drugs_failed)

    # Backward compatibility
    @property
    def mechanism(self) -> str:
        """Alias for mechanism_target (backward compatibility)."""
        return self.mechanism_target

