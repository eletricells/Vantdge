"""
Case Series Analysis Module

A modular, testable architecture for drug repurposing case series analysis.

Components:
- orchestrator: Main entry point that coordinates all services
- protocols: Interfaces for dependency injection
- services: Business logic services
- scoring: Opportunity scoring engine
- prompts: LLM prompt templates
- repositories: Data persistence layer
- export: Excel/JSON export utilities
"""

from src.case_series.orchestrator import (
    CaseSeriesOrchestrator,
    AnalysisConfig,
    AnalysisProgress,
    PaperDiscoveryResult,
    PaperWithFilterStatus,
)
from src.case_series.factory import create_orchestrator

__all__ = [
    "CaseSeriesOrchestrator",
    "create_orchestrator",
    "AnalysisConfig",
    "AnalysisProgress",
    "PaperDiscoveryResult",
    "PaperWithFilterStatus",
]
