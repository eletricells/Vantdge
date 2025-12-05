"""
Pydantic models for Off-Label Case Study Agent.

These models define the data structures for case studies, case series,
and expanded access programs.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# =====================================================
# STUDY CLASSIFICATION
# =====================================================

class StudyClassification(BaseModel):
    """
    Classification of study type.

    Used to categorize papers as case reports, case series, clinical trials, etc.
    """
    study_type: str = Field(..., description="Case Report, Case Series, Retrospective Cohort, Prospective Cohort, Clinical Trial, Expanded Access Program, Real-World Evidence, N-of-1 Trial, or Not Relevant")
    n_patients: Optional[int] = Field(None, description="Number of patients in study")
    is_off_label: bool = Field(True, description="Whether use is off-label")
    indication: Optional[str] = Field(None, description="Disease/condition being treated")
    relevance_score: float = Field(..., description="Relevance score 0.0-1.0")
    rationale: str = Field(..., description="Why this classification was chosen")


# =====================================================
# BASELINE CHARACTERISTICS
# =====================================================

class OffLabelBaseline(BaseModel):
    """
    Patient demographics and disease characteristics.
    
    Similar to BaselineCharacteristics but adapted for case studies.
    """
    n: Optional[int] = Field(None, description="Sample size")
    
    # Age
    median_age: Optional[float] = Field(None, description="Median age")
    mean_age: Optional[float] = Field(None, description="Mean age")
    age_range: Optional[str] = Field(None, description="Age range (e.g., '35-67')")
    age_sd: Optional[float] = Field(None, description="Standard deviation of age")
    
    # Sex
    male_n: Optional[int] = Field(None, description="Number of males")
    male_pct: Optional[float] = Field(None, description="Percentage male")
    female_n: Optional[int] = Field(None, description="Number of females")
    female_pct: Optional[float] = Field(None, description="Percentage female")
    
    # Race/Ethnicity (flexible)
    race_ethnicity: Optional[Dict[str, Any]] = Field(None, description="Race/ethnicity breakdown")
    
    # Disease characteristics
    median_disease_duration: Optional[float] = Field(None, description="Median disease duration")
    mean_disease_duration: Optional[float] = Field(None, description="Mean disease duration")
    disease_duration_unit: str = Field("years", description="Unit for disease duration")
    disease_duration_range: Optional[str] = Field(None, description="Disease duration range")
    
    disease_severity: Optional[str] = Field(None, description="Disease severity description")
    baseline_severity_scores: Optional[Dict[str, Any]] = Field(None, description="Disease-specific severity scores")
    
    # Prior therapies
    prior_medications_detail: Optional[List[Dict[str, Any]]] = Field(None, description="Prior medications with details")
    prior_lines_median: Optional[float] = Field(None, description="Median prior lines of therapy")
    prior_lines_mean: Optional[float] = Field(None, description="Mean prior lines of therapy")
    treatment_naive_n: Optional[int] = Field(None, description="Number treatment-naive")
    treatment_naive_pct: Optional[float] = Field(None, description="Percentage treatment-naive")
    
    prior_steroid_use_n: Optional[int] = Field(None, description="Number with prior steroid use")
    prior_steroid_use_pct: Optional[float] = Field(None, description="Percentage with prior steroid use")
    prior_biologic_use_n: Optional[int] = Field(None, description="Number with prior biologic use")
    prior_biologic_use_pct: Optional[float] = Field(None, description="Percentage with prior biologic use")
    prior_immunosuppressant_use_n: Optional[int] = Field(None, description="Number with prior immunosuppressant use")
    prior_immunosuppressant_use_pct: Optional[float] = Field(None, description="Percentage with prior immunosuppressant use")
    
    # Comorbidities
    comorbidities: Optional[List[str]] = Field(None, description="List of comorbidities")
    
    # Biomarkers
    biomarkers: Optional[Dict[str, Any]] = Field(None, description="Disease-specific biomarkers")
    
    # Notes
    notes: Optional[str] = Field(None, description="Additional notes")
    source_table: Optional[str] = Field(None, description="Source table/figure")


# =====================================================
# OUTCOMES
# =====================================================

class OffLabelOutcome(BaseModel):
    """
    Treatment outcome/efficacy data.
    
    Similar to EfficacyEndpoint but adapted for case studies.
    """
    outcome_category: Optional[str] = Field(None, description="Primary, Secondary, Clinical Response, Biomarker")
    outcome_name: str = Field(..., description="Name of outcome")
    outcome_description: Optional[str] = Field(None, description="Detailed description")
    outcome_unit: Optional[str] = Field(None, description="Unit of measurement")
    
    # Timepoint
    timepoint: Optional[str] = Field(None, description="Timepoint (e.g., 'Week 4', 'Month 6')")
    timepoint_weeks: Optional[int] = Field(None, description="Timepoint normalized to weeks")
    
    # Measurement type
    measurement_type: Optional[str] = Field(None, description="Responder, Change from baseline, Absolute value")
    
    # Responder data
    responders_n: Optional[int] = Field(None, description="Number of responders")
    responders_pct: Optional[float] = Field(None, description="Percentage of responders")
    non_responders_n: Optional[int] = Field(None, description="Number of non-responders")
    
    # Continuous data
    mean_value: Optional[float] = Field(None, description="Mean value")
    median_value: Optional[float] = Field(None, description="Median value")
    sd: Optional[float] = Field(None, description="Standard deviation")
    range_min: Optional[float] = Field(None, description="Minimum value")
    range_max: Optional[float] = Field(None, description="Maximum value")
    
    # Change from baseline
    mean_change: Optional[float] = Field(None, description="Mean change from baseline")
    median_change: Optional[float] = Field(None, description="Median change from baseline")
    pct_change: Optional[float] = Field(None, description="Percent change from baseline")
    
    # Durability
    sustained_response: Optional[bool] = Field(None, description="Whether response was sustained")
    duration_of_response: Optional[str] = Field(None, description="Duration of response")
    
    # Statistical significance
    p_value: Optional[float] = Field(None, description="P-value")
    ci_lower: Optional[float] = Field(None, description="Lower confidence interval")
    ci_upper: Optional[float] = Field(None, description="Upper confidence interval")
    
    # Notes
    notes: Optional[str] = Field(None, description="Additional notes")
    source_table: Optional[str] = Field(None, description="Source table/figure")


# =====================================================
# SAFETY EVENTS
# =====================================================

class OffLabelSafetyEvent(BaseModel):
    """
    Adverse event/safety data.
    
    Similar to SafetyEndpoint but adapted for case studies.
    """
    event_category: Optional[str] = Field(None, description="Adverse Event, Serious AE, Discontinuation, Death")
    event_name: str = Field(..., description="Name of adverse event")
    event_description: Optional[str] = Field(None, description="Detailed description")
    
    # Severity
    severity: Optional[str] = Field(None, description="Mild, Moderate, Severe, Grade 3+, Life-threatening")
    
    # Incidence
    n_events: Optional[int] = Field(None, description="Number of events")
    n_patients: Optional[int] = Field(None, description="Number of patients with event")
    incidence_pct: Optional[float] = Field(None, description="Percentage of patients with event")
    
    # Timing
    time_to_onset: Optional[str] = Field(None, description="Time to onset")
    
    # Outcome
    event_outcome: Optional[str] = Field(None, description="Resolved, Ongoing, Led to discontinuation, Fatal")
    
    # Causality
    causality_assessment: Optional[str] = Field(None, description="Definitely/Probably/Possibly/Unlikely related")
    
    # Action taken
    action_taken: Optional[str] = Field(None, description="Dose reduction, Temporary hold, Permanent discontinuation, No action")
    
    # Notes
    notes: Optional[str] = Field(None, description="Additional notes")
    source_table: Optional[str] = Field(None, description="Source table/figure")


# =====================================================
# MAIN CASE STUDY MODEL
# =====================================================

class OffLabelCaseStudy(BaseModel):
    """
    Complete off-label case study extraction.
    
    Main data model containing all extracted information.
    """
    # Paper identification
    pmid: Optional[str] = Field(None, description="PubMed ID")
    doi: Optional[str] = Field(None, description="DOI")
    pmc: Optional[str] = Field(None, description="PubMed Central ID")
    title: str = Field(..., description="Paper title")
    authors: Optional[str] = Field(None, description="Comma-separated author list")
    journal: Optional[str] = Field(None, description="Journal name")
    year: Optional[int] = Field(None, description="Publication year")
    abstract: Optional[str] = Field(None, description="Abstract text")
    
    # Study classification
    study_type: str = Field(..., description="Case Report, Case Series, etc.")
    relevance_score: float = Field(..., description="Relevance score 0.0-1.0")
    
    # Drug & indication
    drug_id: Optional[int] = Field(None, description="Drug ID from database")
    drug_name: str = Field(..., description="Drug name")
    generic_name: Optional[str] = Field(None, description="Generic name")
    mechanism: Optional[str] = Field(None, description="Mechanism of action")
    target: Optional[str] = Field(None, description="Molecular target")
    
    indication_treated: str = Field(..., description="Off-label indication")
    approved_indications: Optional[List[str]] = Field(None, description="Approved indications for comparison")
    is_off_label: bool = Field(True, description="Whether use is off-label")
    
    # Patient cohort
    n_patients: Optional[int] = Field(None, description="Total number of patients")
    
    # Treatment details
    dosing_regimen: Optional[str] = Field(None, description="Dosing regimen")
    treatment_duration: Optional[str] = Field(None, description="Treatment duration")
    concomitant_medications: Optional[List[str]] = Field(None, description="Concomitant medications")
    
    # Outcomes (summary)
    response_rate: Optional[str] = Field(None, description="Response rate description")
    responders_n: Optional[int] = Field(None, description="Number of responders")
    responders_pct: Optional[float] = Field(None, description="Percentage of responders")
    time_to_response: Optional[str] = Field(None, description="Time to response")
    duration_of_response: Optional[str] = Field(None, description="Duration of response")
    
    # Safety (summary)
    adverse_events: Optional[List[Dict[str, Any]]] = Field(None, description="Summary of adverse events")
    serious_adverse_events_n: Optional[int] = Field(None, description="Number of serious AEs")
    discontinuations_n: Optional[int] = Field(None, description="Number of discontinuations")
    
    # Clinical assessment (AI-generated)
    efficacy_signal: Optional[str] = Field(None, description="Strong, Moderate, Weak, None")
    safety_profile: Optional[str] = Field(None, description="Acceptable, Concerning, Unknown")
    mechanism_rationale: Optional[str] = Field(None, description="Why mechanism makes sense")
    development_potential: Optional[str] = Field(None, description="High, Medium, Low")
    key_findings: Optional[str] = Field(None, description="1-2 sentence summary")
    
    # Detailed data (child records)
    baseline_characteristics: Optional[OffLabelBaseline] = Field(None, description="Detailed baseline data")
    outcomes: List[OffLabelOutcome] = Field(default_factory=list, description="Detailed outcome data")
    safety_events: List[OffLabelSafetyEvent] = Field(default_factory=list, description="Detailed safety data")
    
    # Metadata
    paper_path: Optional[str] = Field(None, description="Path to downloaded paper")
    is_open_access: bool = Field(False, description="Whether paper is open access")
    citation_count: Optional[int] = Field(None, description="Number of citations")
    
    # Extraction metadata
    extracted_by: str = Field("Claude Sonnet 4.5", description="Model used for extraction")
    extraction_timestamp: datetime = Field(default_factory=datetime.now, description="When extraction was performed")
    extraction_confidence: Optional[float] = Field(None, description="Confidence in extraction (0.0-1.0)")
    extraction_notes: Optional[str] = Field(None, description="Notes about extraction")

    # Evidence quality assessment (NEW)
    evidence_quality: Optional[Dict[str, Any]] = Field(None, description="Evidence quality assessment using GRADE criteria")
    evidence_grade: Optional[str] = Field(None, description="Overall evidence grade (A/B/C/D)")

    # Search metadata
    search_query: Optional[str] = Field(None, description="Search query that found this paper")
    search_source: Optional[str] = Field(None, description="PubMed, Tavily, User Upload, ClinicalTrials.gov")


# =====================================================
# VALIDATION
# =====================================================

class OffLabelValidationResult(BaseModel):
    """
    Validation result for off-label case study extraction.
    
    Similar to ExtractionValidationResult but adapted for case studies.
    """
    is_valid: bool = Field(..., description="Whether extraction passes validation")
    issues: List[str] = Field(default_factory=list, description="List of validation issues")
    warnings: List[str] = Field(default_factory=list, description="Non-critical warnings")
    
    # Quality checks
    has_baseline_data: bool = Field(False, description="Whether baseline data was extracted")
    has_outcome_data: bool = Field(False, description="Whether outcome data was extracted")
    has_safety_data: bool = Field(False, description="Whether safety data was extracted")
    baseline_completeness_pct: float = Field(0.0, description="Percentage of baseline fields populated")
    outcome_count: int = Field(0, description="Number of outcomes extracted")
    safety_event_count: int = Field(0, description="Number of safety events extracted")
    
    # Clinical plausibility
    demographics_plausible: bool = Field(True, description="Demographics within expected ranges")
    outcomes_plausible: bool = Field(True, description="Outcomes clinically plausible")
    
    def summary(self) -> str:
        """Generate summary of validation result."""
        lines = []
        lines.append(f"Validation: {'PASSED' if self.is_valid else 'FAILED'}")
        lines.append(f"Baseline: {self.baseline_completeness_pct:.0f}% complete")
        lines.append(f"Outcomes: {self.outcome_count}")
        lines.append(f"Safety events: {self.safety_event_count}")
        
        if self.issues:
            lines.append(f"\nISSUES ({len(self.issues)}):")
            for issue in self.issues:
                lines.append(f"  - {issue}")
        
        if self.warnings:
            lines.append(f"\nWARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                lines.append(f"  - {warning}")
        
        return "\n".join(lines)

