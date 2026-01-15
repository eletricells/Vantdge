"""
Models for unified Disease Analysis workflow.

Combines Pipeline Intelligence and Disease Intelligence outputs
into a single comprehensive disease analysis result.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field

from ..pipeline_intelligence.models import CompetitiveLandscape, PipelineDrug
from ..disease_intelligence.models import DiseaseIntelligence, MarketFunnel


class MarketOpportunity(BaseModel):
    """
    Combined market opportunity assessment.

    Integrates pipeline competitive data with market sizing to provide
    a comprehensive view of the market opportunity.
    """
    # Patient funnel
    total_patients: int = Field(0, description="Total US patient population")
    patients_treated: int = Field(0, description="Patients receiving treatment")
    patients_fail_1L: int = Field(0, description="Patients failing 1L therapy")
    addressable_2L: int = Field(0, description="Addressable market for 2L therapies")

    # Market sizing
    market_size_2L_usd: Optional[int] = Field(None, description="2L market size in USD")
    market_size_2L_formatted: Optional[str] = Field(None, description="Formatted market size")

    # Competitive context
    approved_drugs_count: int = Field(0, description="Number of approved drugs")
    phase3_drugs_count: int = Field(0, description="Number of Phase 3 drugs")
    total_pipeline_drugs: int = Field(0, description="Total pipeline drugs (excl. approved)")

    # Key competitive insights
    key_moa_classes: List[str] = Field(default_factory=list, description="Key mechanism classes in pipeline")
    unmet_need_summary: Optional[str] = Field(None, description="Summary of unmet need")

    # Confidence
    data_quality: Optional[str] = Field(None, description="Overall data quality: High, Medium, Low")
    confidence_notes: Optional[str] = Field(None, description="Notes on data confidence")


class UnifiedDiseaseAnalysis(BaseModel):
    """
    Complete unified disease analysis result.

    Combines:
    - Pipeline Intelligence: Competitive landscape (approved + pipeline drugs)
    - Disease Intelligence: Market sizing (prevalence, failure rates, treatment)
    - Market Opportunity: Combined assessment
    """
    # Identification
    disease_name: str
    therapeutic_area: Optional[str] = None

    # Pipeline Intelligence output
    landscape: Optional[CompetitiveLandscape] = None

    # Disease Intelligence output
    disease_intel: Optional[DiseaseIntelligence] = None

    # Combined market opportunity
    market_opportunity: Optional[MarketOpportunity] = None

    # Disease synonyms (from MeSH expansion)
    disease_synonyms: List[str] = Field(default_factory=list)

    # Run metadata
    run_timestamp: datetime = Field(default_factory=datetime.now)
    pipeline_run_id: Optional[int] = None
    disease_intel_id: Optional[int] = None

    # Status
    pipeline_success: bool = False
    disease_intel_success: bool = False
    errors: List[str] = Field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Check if both workflows completed successfully."""
        return self.pipeline_success and self.disease_intel_success

    @property
    def approved_drugs(self) -> List[PipelineDrug]:
        """Get approved drugs from landscape."""
        if self.landscape:
            return self.landscape.approved_drugs
        return []

    @property
    def pipeline_drugs(self) -> List[PipelineDrug]:
        """Get all pipeline drugs (excl. approved)."""
        if self.landscape:
            return (
                self.landscape.phase3_drugs +
                self.landscape.phase2_drugs +
                self.landscape.phase1_drugs +
                self.landscape.preclinical_drugs
            )
        return []

    def summary(self) -> str:
        """Generate a text summary of the analysis."""
        lines = [
            f"Disease Analysis: {self.disease_name}",
            f"={'=' * 50}",
        ]

        if self.landscape:
            lines.extend([
                "",
                "COMPETITIVE LANDSCAPE:",
                f"  Approved: {self.landscape.approved_count}",
                f"  Phase 3: {self.landscape.phase3_count}",
                f"  Phase 2: {self.landscape.phase2_count}",
                f"  Phase 1: {self.landscape.phase1_count}",
                f"  Discontinued: {self.landscape.discontinued_count}",
            ])

        if self.disease_intel and self.disease_intel.prevalence:
            prev = self.disease_intel.prevalence
            lines.extend([
                "",
                "MARKET SIZING:",
                f"  Prevalence: {prev.total_patients:,}" if prev.total_patients else "  Prevalence: N/A",
            ])
            if self.disease_intel.segmentation.pct_treated:
                lines.append(f"  Treated: {self.disease_intel.segmentation.pct_treated:.1f}%")
            if self.disease_intel.failure_rates.fail_1L_pct:
                lines.append(f"  Fail 1L: {self.disease_intel.failure_rates.fail_1L_pct:.1f}%")

        if self.market_opportunity:
            mo = self.market_opportunity
            lines.extend([
                "",
                "MARKET OPPORTUNITY:",
                f"  Addressable 2L: {mo.addressable_2L:,}" if mo.addressable_2L else "  Addressable 2L: N/A",
                f"  Market Size: {mo.market_size_2L_formatted}" if mo.market_size_2L_formatted else "  Market Size: N/A",
            ])

        return "\n".join(lines)

    class Config:
        """Pydantic config."""
        arbitrary_types_allowed = True
