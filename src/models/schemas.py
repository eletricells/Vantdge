"""
Pydantic models for data structures in the biopharma investment analysis system.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime
from enum import Enum


class RiskLevel(str, Enum):
    """Risk level classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Recommendation(str, Enum):
    """Investment recommendation types"""
    ACQUIRE = "acquire"
    MONITOR = "monitor"
    PASS = "pass"


class Citation(BaseModel):
    """Source citation for a fact or finding"""
    source: str = Field(..., description="Source name (e.g., 'ClinicalTrials.gov', 'PubMed')")
    url: Optional[str] = Field(None, description="URL to the source")
    date_accessed: datetime = Field(default_factory=datetime.now, description="When the source was accessed")
    snippet: str = Field(..., description="Relevant excerpt from the source")

    class Config:
        json_schema_extra = {
            "example": {
                "source": "ClinicalTrials.gov",
                "url": "https://clinicaltrials.gov/study/NCT12345678",
                "date_accessed": "2024-10-02T12:00:00",
                "snippet": "Phase 2 trial showed 45% ORR in NSCLC patients"
            }
        }


class AnalysisFinding(BaseModel):
    """Individual finding with confidence score and evidence"""
    finding: str = Field(..., description="The finding or observation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0)")
    citations: List[Citation] = Field(default_factory=list, description="Supporting evidence")
    risk_level: RiskLevel = Field(..., description="Associated risk level")
    reasoning: Optional[str] = Field(None, description="Explanation of the finding")

    class Config:
        json_schema_extra = {
            "example": {
                "finding": "Phase 2 data shows strong efficacy signal",
                "confidence": 0.85,
                "citations": [],
                "risk_level": "low",
                "reasoning": "ORR of 45% vs 20% SOC with statistical significance"
            }
        }


class ClinicalAnalysis(BaseModel):
    """Output from clinical agent"""
    target: str = Field(..., description="Drug or company name")
    indication: str = Field(..., description="Therapeutic indication")
    phase: str = Field(..., description="Development phase (e.g., 'Phase 2', 'Phase 3')")
    findings: List[AnalysisFinding] = Field(default_factory=list, description="All clinical findings")
    probability_of_success: float = Field(..., ge=0.0, le=1.0, description="Overall probability of success")
    key_risks: List[str] = Field(default_factory=list, description="Major risks identified")
    key_opportunities: List[str] = Field(default_factory=list, description="Major opportunities identified")
    overall_assessment: str = Field(..., description="Summary assessment")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Overall confidence in analysis")
    analysis_timestamp: datetime = Field(default_factory=datetime.now, description="When analysis was performed")

    class Config:
        json_schema_extra = {
            "example": {
                "target": "Company XYZ - Drug ABC",
                "indication": "Non-small cell lung cancer",
                "phase": "Phase 2",
                "findings": [],
                "probability_of_success": 0.67,
                "key_risks": ["Small sample size", "Single-arm design"],
                "key_opportunities": ["Novel mechanism", "Unmet medical need"],
                "overall_assessment": "Promising early data with manageable risks",
                "confidence_score": 0.75,
                "analysis_timestamp": "2024-10-02T12:00:00"
            }
        }


class InvestmentThesis(BaseModel):
    """Final output from manager agent"""
    target: str = Field(..., description="Drug or company name")
    indication: str = Field(..., description="Therapeutic indication")
    recommendation: Recommendation = Field(..., description="Investment recommendation")
    rationale: str = Field(..., description="Detailed rationale for recommendation")
    key_strengths: List[str] = Field(default_factory=list, description="Major strengths")
    key_risks: List[str] = Field(default_factory=list, description="Major risks")
    estimated_value: Optional[str] = Field(None, description="Estimated value range")
    estimated_peak_sales: Optional[str] = Field(None, description="Estimated peak sales")
    deal_structure_suggestions: List[str] = Field(default_factory=list, description="Suggested deal terms")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Overall confidence in thesis")
    executive_summary: str = Field(..., description="Executive summary for BD team")
    clinical_analysis_summary: Optional[str] = Field(None, description="Summary of clinical analysis")
    analysis_timestamp: datetime = Field(default_factory=datetime.now, description="When thesis was generated")

    class Config:
        json_schema_extra = {
            "example": {
                "target": "Company XYZ - Drug ABC",
                "indication": "Non-small cell lung cancer",
                "recommendation": "acquire",
                "rationale": "Strong clinical signal in high unmet need indication",
                "key_strengths": ["Novel mechanism", "Compelling efficacy data"],
                "key_risks": ["Small Phase 2 trial", "Competitive landscape"],
                "estimated_value": "$200-300M upfront",
                "estimated_peak_sales": "$500M-$800M",
                "deal_structure_suggestions": ["Upfront + milestones", "Royalty structure"],
                "confidence_score": 0.85,
                "executive_summary": "Drug ABC represents a compelling opportunity...",
                "clinical_analysis_summary": "Phase 2 data shows 45% ORR...",
                "analysis_timestamp": "2024-10-02T12:00:00"
            }
        }


class AnalysisState(BaseModel):
    """State that flows through the LangGraph workflow"""
    target: str = Field(..., description="Drug or company being analyzed")
    indication: str = Field(..., description="Therapeutic indication")
    phase: Optional[str] = Field(None, description="Development phase")

    # Agent outputs
    clinical_data: Optional[ClinicalAnalysis] = Field(None, description="Output from clinical agent")
    manager_synthesis: Optional[InvestmentThesis] = Field(None, description="Output from manager agent")

    # Workflow control
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Overall confidence")
    iteration_count: int = Field(default=0, description="Number of refinement iterations")
    requires_followup: bool = Field(default=False, description="Whether manager needs more analysis")
    max_iterations: int = Field(default=3, description="Maximum refinement iterations")

    # Additional context
    context: dict = Field(default_factory=dict, description="Additional context or parameters")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")

    class Config:
        arbitrary_types_allowed = True
        json_schema_extra = {
            "example": {
                "target": "Company XYZ - Drug ABC",
                "indication": "Non-small cell lung cancer",
                "phase": "Phase 2",
                "clinical_data": None,
                "manager_synthesis": None,
                "confidence_score": 0.0,
                "iteration_count": 0,
                "requires_followup": False,
                "max_iterations": 3,
                "context": {},
                "errors": []
            }
        }
