"""
Clinical trial data extraction schemas.

These schemas define the structure for extracting structured clinical trial data
from scientific papers, including baseline characteristics, efficacy endpoints,
and safety data.
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime


class TrialDesignMetadata(BaseModel):
    """
    Trial design and enrollment metadata.

    Trial-level information (not arm-specific) including study design,
    enrollment criteria, and key trial parameters.
    """
    nct_id: str = Field(..., description="ClinicalTrials.gov NCT ID")
    indication: str = Field(..., description="Disease indication")

    # Design summary
    study_design: Optional[str] = Field(
        None,
        description="Study design classification (e.g., 'Randomized, double-blind, placebo-controlled, Phase 3')"
    )
    trial_design_summary: str = Field(
        ...,
        description="AI-generated narrative summary of trial design"
    )
    enrollment_summary: str = Field(
        ...,
        description="Description of enrolled patient population and key characteristics"
    )

    # Detailed criteria (JSONB arrays)
    inclusion_criteria: Optional[List[str]] = Field(
        None,
        description="List of inclusion criteria (e.g., ['Age ≥18 years', 'EASI ≥16'])"
    )
    exclusion_criteria: Optional[List[str]] = Field(
        None,
        description="List of exclusion criteria (e.g., ['Prior biologic use', 'Active infection'])"
    )

    # Key trial parameters
    primary_endpoint_description: Optional[str] = Field(
        None,
        description="Description of primary endpoint"
    )
    secondary_endpoints_summary: Optional[str] = Field(
        None,
        description="Summary of secondary endpoints"
    )
    sample_size_planned: Optional[int] = Field(
        None,
        description="Planned sample size"
    )
    sample_size_enrolled: Optional[int] = Field(
        None,
        description="Actual enrolled sample size"
    )
    duration_weeks: Optional[int] = Field(
        None,
        description="Trial duration in weeks"
    )

    # Randomization details
    randomization_ratio: Optional[str] = Field(
        None,
        description="Randomization ratio (e.g., '1:1:1', '2:1')"
    )
    stratification_factors: Optional[str] = Field(
        None,
        description="Description of stratification factors"
    )

    # Blinding
    blinding: Optional[str] = Field(
        None,
        description="Blinding approach (e.g., 'Double-blind', 'Open-label')"
    )

    # Paper reference
    paper_pmid: Optional[str] = Field(None, description="PubMed ID")
    paper_doi: Optional[str] = Field(None, description="DOI")
    paper_title: Optional[str] = Field(None, description="Paper title")

    # Metadata
    extraction_timestamp: datetime = Field(
        default_factory=datetime.now,
        description="When extraction was performed"
    )
    extraction_confidence: Optional[float] = Field(
        None,
        description="Overall confidence in extraction (0.0-1.0)"
    )
    extraction_notes: Optional[str] = Field(
        None,
        description="Notes about extraction quality or issues"
    )


class TrialArm(BaseModel):
    """
    Individual trial arm/treatment group.

    One trial can have multiple arms (e.g., placebo, low dose, high dose).
    """
    arm_name: str = Field(..., description="Arm name (e.g., 'Placebo', 'Drug 300mg Q2W')")
    dosing_regimen: Optional[str] = Field(None, description="Dosing schedule (e.g., '300mg Q2W')")
    background_therapy: Optional[str] = Field(None, description="Concomitant medications allowed")
    n: Optional[int] = Field(None, description="Number of patients in this arm")


class BaselineCharacteristics(BaseModel):
    """
    Baseline patient characteristics for a trial arm.

    Includes standard demographics, expanded race categories, prior medication use,
    and flexible disease-specific fields.
    """
    # Sample size
    n: Optional[int] = Field(None, description="Number of patients")

    # Standard demographics
    median_age: Optional[float] = Field(None, description="Median age in years")
    mean_age: Optional[float] = Field(None, description="Mean age in years")
    age_range: Optional[str] = Field(None, description="Age range (e.g., '18-75')")
    male_pct: Optional[float] = Field(None, description="Male percentage")
    female_pct: Optional[float] = Field(None, description="Female percentage")

    # Expanded race categories (9 fields)
    race_white_pct: Optional[float] = Field(None, description="White percentage")
    race_black_african_american_pct: Optional[float] = Field(None, description="Black/African American percentage")
    race_asian_pct: Optional[float] = Field(None, description="Asian percentage")
    race_hispanic_latino_pct: Optional[float] = Field(None, description="Hispanic/Latino percentage")
    race_native_american_pct: Optional[float] = Field(None, description="Native American percentage")
    race_pacific_islander_pct: Optional[float] = Field(None, description="Pacific Islander percentage")
    race_mixed_pct: Optional[float] = Field(None, description="Mixed race percentage")
    race_other_pct: Optional[float] = Field(None, description="Other race percentage")
    race_unknown_pct: Optional[float] = Field(None, description="Unknown race percentage")
    race_additional_detail: Optional[Dict[str, Any]] = Field(None, description="Additional race data in JSON")

    # Disease history
    median_disease_duration: Optional[float] = Field(None, description="Median disease duration (years or months)")
    mean_disease_duration: Optional[float] = Field(None, description="Mean disease duration")
    disease_duration_unit: Optional[str] = Field(None, description="Unit for disease duration (years/months)")

    # Prior medication use (7 standard fields)
    prior_steroid_use_pct: Optional[float] = Field(None, description="Prior steroid use percentage")
    prior_biologic_use_pct: Optional[float] = Field(None, description="Prior biologic use percentage")
    prior_tnf_inhibitor_use_pct: Optional[float] = Field(None, description="Prior TNF inhibitor use percentage")
    prior_immunosuppressant_use_pct: Optional[float] = Field(None, description="Prior immunosuppressant use percentage")
    prior_topical_therapy_pct: Optional[float] = Field(None, description="Prior topical therapy use percentage")
    treatment_naive_pct: Optional[float] = Field(None, description="Treatment-naive percentage")
    prior_lines_median: Optional[float] = Field(None, description="Median prior lines of therapy")

    # Flexible JSONB fields for disease-specific data
    prior_medications_detail: Optional[Dict[str, Any]] = Field(
        None,
        description="Detailed prior medication history (JSON). Examples: "
                    "{'prior_biologics': ['adalimumab', 'etanercept'], 'prior_lines_median': 2}"
    )
    disease_specific_baseline: Optional[Dict[str, Any]] = Field(
        None,
        description="Disease-specific biomarkers (JSON). Examples: "
                    "{'achr_positive_pct': 85, 'trab_mean': 12.3}"
    )
    baseline_severity_scores: Optional[Dict[str, Any]] = Field(
        None,
        description="Baseline severity scores (JSON). Examples: "
                    "{'EASI_mean': 32.5, 'IGA_4_pct': 48}"
    )

    # Table reference
    source_table: Optional[str] = Field(None, description="Table/Figure where data was found (e.g., 'Table 1')")


class BaselineCharacteristicDetail(BaseModel):
    """
    Individual baseline characteristic (demographic or disease-specific).

    Stores one characteristic per record, allowing flexible extraction of any demographic
    or disease-specific characteristic from baseline tables.
    Similar structure to EfficacyEndpoint for consistency.
    """
    # Characteristic identification
    characteristic_name: str = Field(..., description="Characteristic name (e.g., 'Age', 'Weight', 'Serum C3', 'Systolic Blood Pressure')")
    characteristic_category: Optional[str] = Field(None, description="Category (e.g., 'Demographics', 'Disease Biomarkers', 'Severity Scores', 'Lab Values')")
    characteristic_description: Optional[str] = Field(None, description="Full description if available")

    # Cohort/Subgroup
    cohort: Optional[str] = Field(None, description="Cohort name (e.g., 'C3G', 'Overall', 'Treatment arm')")

    # Values (flexible to handle different data types)
    value_numeric: Optional[float] = Field(None, description="Numeric value (age, weight, etc.)")
    value_text: Optional[str] = Field(None, description="Categorical value (race, gender, etc.)")
    unit: Optional[str] = Field(None, description="Unit (e.g., 'years', 'kg', 'mg/dl', '%')")

    # Statistical measures
    n_patients: Optional[int] = Field(None, description="Number of patients with this characteristic")
    percentage: Optional[float] = Field(None, description="Percentage (for categorical characteristics)")
    mean_value: Optional[float] = Field(None, description="Mean (for continuous characteristics)")
    median_value: Optional[float] = Field(None, description="Median (for continuous characteristics)")
    sd_value: Optional[float] = Field(None, description="Standard deviation")
    range_min: Optional[float] = Field(None, description="Minimum value in range")
    range_max: Optional[float] = Field(None, description="Maximum value in range")

    # Source reference
    source_table: Optional[str] = Field(None, description="Table/Figure where data was found (e.g., 'Table 1')")


class EfficacyEndpoint(BaseModel):
    """
    Individual efficacy endpoint result.

    Can be primary or secondary endpoint at various timepoints.
    """
    endpoint_category: Optional[str] = Field(None, description="Category (e.g., 'Primary', 'Secondary', 'Exploratory')")
    endpoint_name: str = Field(..., description="Endpoint name (e.g., 'EASI-75', 'ACR20', 'Change in FEV1')")
    endpoint_unit: Optional[str] = Field(None, description="Unit of measurement (e.g., 'mg/mg', 'ml/min per 1.73 m²', '%')")
    is_standard_endpoint: Optional[bool] = Field(False, description="Whether this is a standard endpoint from landscape discovery")

    # Timepoint
    timepoint: str = Field(..., description="Timepoint (e.g., 'Week 16', 'Month 3', 'Day 85')")
    timepoint_weeks: Optional[float] = Field(None, description="Timepoint converted to weeks for sorting (can be fractional for days)")

    # Analysis type
    analysis_type: Optional[str] = Field(None, description="Analysis population (e.g., 'ITT', 'PP', 'Safety', 'Per-protocol')")

    # Results
    responders_n: Optional[int] = Field(None, description="Number of responders")
    n_evaluated: Optional[int] = Field(None, description="Total patients evaluated for this endpoint (denominator)")
    responders_pct: Optional[float] = Field(None, description="Percentage of responders")
    mean_value: Optional[float] = Field(None, description="Mean value for continuous endpoints")
    median_value: Optional[float] = Field(None, description="Median value")
    change_from_baseline: Optional[float] = Field(None, description="Change from baseline (mean or median)")
    change_from_baseline_mean: Optional[float] = Field(None, description="Mean change from baseline")
    pct_change_from_baseline: Optional[float] = Field(None, description="Percent change from baseline")

    # Statistics
    stat_sig: Optional[bool] = Field(None, description="Whether statistically significant vs control")
    p_value: Optional[str] = Field(None, description="P-value (e.g., 'p<0.001', 'p=0.023')")
    confidence_interval: Optional[str] = Field(None, description="95% CI (e.g., '95% CI: 12.3-18.7')")

    # Comparator
    comparator_arm: Optional[str] = Field(None, description="Comparator arm name for statistical comparison")

    # Source
    source_table: Optional[str] = Field(None, description="Table/Figure reference")

    @validator('responders_n', pre=True)
    def parse_fraction_format(cls, v):
        """
        Parse fraction format like "6/8" into numerator.

        If agent returns "6/8", extract 6 as responders_n.
        The denominator should be in n_evaluated field.
        """
        if isinstance(v, str) and '/' in v:
            try:
                numerator = v.split('/')[0].strip()
                return int(numerator)
            except (ValueError, IndexError):
                return None
        return v


class SafetyEndpoint(BaseModel):
    """
    Safety endpoint or adverse event data.

    Includes treatment-emergent AEs, SAEs, and specific events of interest.
    """
    event_category: str = Field(..., description="Category (e.g., 'TEAE', 'SAE', 'AE leading to discontinuation')")
    event_name: str = Field(..., description="Event name (e.g., 'Nasopharyngitis', 'Injection site reaction')")
    severity: Optional[str] = Field(None, description="Severity (e.g., 'Mild', 'Moderate', 'Severe', 'Grade 3+')")

    # Incidence
    n_events: Optional[int] = Field(None, description="Number of events")
    n_patients: Optional[int] = Field(None, description="Number of patients with event")
    incidence_pct: Optional[float] = Field(None, description="Percentage of patients with event")

    # Cohort/Subgroup
    cohort: Optional[str] = Field(None, description="Subgroup or cohort name (e.g., 'C3G', 'Overall study population')")

    # Timing
    timepoint: Optional[str] = Field(None, description="When measured (e.g., 'Through Week 16')")

    # Source
    source_table: Optional[str] = Field(None, description="Table/Figure reference")


class ClinicalTrialExtraction(BaseModel):
    """
    Complete clinical trial data extraction for one trial arm.

    Represents all data extracted from a single trial arm, including baseline,
    efficacy, and safety data.
    """
    # Trial identifiers
    nct_id: str = Field(..., description="ClinicalTrials.gov NCT ID")
    trial_name: Optional[str] = Field(None, description="Trial name/acronym (e.g., 'SOLO 1', 'ARCADIA')")

    # Drug info
    drug_name: str = Field(..., description="Brand name (e.g., 'DUPIXENT')")
    generic_name: Optional[str] = Field(None, description="Generic name (e.g., 'dupilumab')")
    indication: str = Field(..., description="Disease indication")

    # Trial arm
    arm_name: str = Field(..., description="Arm name (e.g., 'Placebo', 'DUPIXENT 300mg Q2W')")
    dosing_regimen: Optional[str] = Field(None, description="Dosing schedule")
    background_therapy: Optional[str] = Field(None, description="Background therapy allowed")
    n: Optional[int] = Field(None, description="Number of patients in arm")

    # Trial metadata
    phase: Optional[str] = Field(None, description="Trial phase (e.g., 'Phase 2', 'Phase 3')")

    # Paper reference
    paper_pmid: Optional[str] = Field(None, description="PubMed ID of paper")
    paper_doi: Optional[str] = Field(None, description="DOI of paper")
    paper_title: Optional[str] = Field(None, description="Paper title")

    # Extracted data
    baseline: Optional[BaselineCharacteristics] = Field(None, description="Baseline characteristics (summary)")
    baseline_characteristics_detail: List[BaselineCharacteristicDetail] = Field(default_factory=list, description="Individual baseline characteristics (demographics, biomarkers, etc.)")
    efficacy_endpoints: List[EfficacyEndpoint] = Field(default_factory=list, description="All efficacy endpoints")
    safety_endpoints: List[SafetyEndpoint] = Field(default_factory=list, description="All safety endpoints")

    # Metadata
    extraction_timestamp: datetime = Field(default_factory=datetime.now, description="When extraction was performed")
    extraction_confidence: Optional[float] = Field(None, description="Overall confidence in extraction (0.0-1.0)")
    extraction_notes: Optional[str] = Field(None, description="Notes about extraction quality or issues")


class ExtractionValidationResult(BaseModel):
    """
    Validation result for clinical trial extraction.

    Checks for data quality, completeness, and clinical plausibility.
    """
    is_valid: bool = Field(..., description="Whether extraction passes validation")
    issues: List[str] = Field(default_factory=list, description="List of validation issues found")
    warnings: List[str] = Field(default_factory=list, description="Non-critical warnings")

    # Quality checks
    has_baseline_data: bool = Field(False, description="Whether baseline data was extracted")
    has_efficacy_data: bool = Field(False, description="Whether efficacy data was extracted")
    has_safety_data: bool = Field(False, description="Whether safety data was extracted")
    baseline_completeness_pct: float = Field(0.0, description="Percentage of standard baseline fields populated")
    efficacy_endpoint_count: int = Field(0, description="Number of efficacy endpoints extracted")
    safety_endpoint_count: int = Field(0, description="Number of safety endpoints extracted")

    # Clinical plausibility flags
    demographics_plausible: bool = Field(True, description="Demographics within expected ranges")
    efficacy_plausible: bool = Field(True, description="Efficacy results clinically plausible")

    def summary(self) -> str:
        """Generate summary of validation result."""
        lines = []
        lines.append(f"Validation: {'PASSED' if self.is_valid else 'FAILED'}")
        lines.append(f"Baseline: {self.baseline_completeness_pct:.0f}% complete")
        lines.append(f"Efficacy endpoints: {self.efficacy_endpoint_count}")
        lines.append(f"Safety endpoints: {self.safety_endpoint_count}")

        if self.issues:
            lines.append(f"\nISSUES ({len(self.issues)}):")
            for issue in self.issues:
                lines.append(f"  - {issue}")

        if self.warnings:
            lines.append(f"\nWARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                lines.append(f"  - {warning}")

        return "\n".join(lines)


class DataSectionIdentification(BaseModel):
    """
    Result of identifying data sections in a paper.

    Stage 1 output: Identifies where baseline, efficacy, and safety data are located.
    """
    baseline_tables: List[str] = Field(default_factory=list, description="Tables/figures with baseline data")
    efficacy_tables: List[str] = Field(default_factory=list, description="Tables/figures with efficacy data")
    safety_tables: List[str] = Field(default_factory=list, description="Tables/figures with safety data")

    # Trial arms identified
    trial_arms: List[TrialArm] = Field(default_factory=list, description="All trial arms found")

    # Confidence
    confidence: float = Field(..., description="Confidence in section identification (0.0-1.0)")
    notes: Optional[str] = Field(None, description="Notes about data structure")
