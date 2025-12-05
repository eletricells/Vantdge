"""
MCP Database Tool for Agent Integration

Provides agents with tool definitions to query proprietary data.
"""
import logging
from typing import Dict, Any, Optional, List
from mcp_server.server import VantdgeDatabaseServer


logger = logging.getLogger(__name__)


class MCPDatabaseTool:
    """
    MCP Database Tool for agent integration.

    Wraps VantdgeDatabaseServer and provides Claude-compatible tool definitions.
    """

    def __init__(self, database_url: str):
        """
        Initialize MCP database tool.

        Args:
            database_url: SQLAlchemy database URL
        """
        self.server = VantdgeDatabaseServer(database_url)
        logger.info("MCPDatabaseTool initialized")

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Get all tool definitions for Claude.

        Returns:
            List of tool definition dictionaries
        """
        return [
            {
                "name": "query_similar_deals",
                "description": "Query internal database for historical deals similar to the current opportunity. Returns deal outcomes, rationale, strengths, and risks from past transactions.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Drug name or target biology (e.g., 'KRAS G12C', 'pembrolizumab')"
                        },
                        "indication": {
                            "type": "string",
                            "description": "Therapeutic indication (e.g., 'NSCLC', 'melanoma', 'Alzheimer's')"
                        },
                        "phase": {
                            "type": "string",
                            "description": "Development phase (e.g., 'Phase 2', 'Phase 3', 'Approved')"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of deals to return (default 5)",
                            "default": 5
                        }
                    }
                }
            },
            {
                "name": "query_expert_annotations",
                "description": "Query internal database for expert insights and annotations on specific targets, drugs, or indications. Returns scientific advisor opinions, clinical expert assessments, and internal expert concerns.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Target name (e.g., 'KRAS G12C', 'PD-1')"
                        },
                        "drug": {
                            "type": "string",
                            "description": "Drug name (e.g., 'Sotorasib', 'Pembrolizumab')"
                        },
                        "indication": {
                            "type": "string",
                            "description": "Therapeutic indication"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of annotations to return (default 10)",
                            "default": 10
                        }
                    }
                }
            },
            {
                "name": "query_target_biology_knowledge",
                "description": "Query internal knowledge base for target biology assessment including genetic evidence strength, druggability score, safety risk level, and strategic priority.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "Target name",
                            "required": True
                        }
                    },
                    "required": ["target"]
                }
            },
            {
                "name": "query_disease_knowledge",
                "description": "Query internal knowledge base for disease assessment including prevalence, market size, unmet need severity, and strategic priority.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "disease": {
                            "type": "string",
                            "description": "Disease name",
                            "required": True
                        }
                    },
                    "required": ["disease"]
                }
            },
            {
                "name": "query_competitive_intelligence",
                "description": "Query internal competitive intelligence database for information on competitor programs, clinical data, and strategic positioning.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "competitor": {
                            "type": "string",
                            "description": "Competitor company name"
                        },
                        "drug": {
                            "type": "string",
                            "description": "Drug name"
                        },
                        "target": {
                            "type": "string",
                            "description": "Target biology"
                        },
                        "indication": {
                            "type": "string",
                            "description": "Therapeutic indication"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of results (default 5)",
                            "default": 5
                        }
                    }
                }
            }
        ]

    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """
        Execute a tool call from Claude.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Tool input parameters

        Returns:
            Formatted results as string
        """
        try:
            if tool_name == "query_similar_deals":
                results = self.server.query_similar_deals(
                    target=tool_input.get("target"),
                    indication=tool_input.get("indication"),
                    phase=tool_input.get("phase"),
                    limit=tool_input.get("limit", 5)
                )
                return self.server.format_results_for_llm(results, "similar_deals")

            elif tool_name == "query_expert_annotations":
                results = self.server.query_expert_annotations(
                    target=tool_input.get("target"),
                    drug=tool_input.get("drug"),
                    indication=tool_input.get("indication"),
                    limit=tool_input.get("limit", 10)
                )
                return self.server.format_results_for_llm(results, "expert_annotations")

            elif tool_name == "query_target_biology_knowledge":
                target = tool_input.get("target")
                if not target:
                    return "Error: target parameter is required"

                result = self.server.query_target_biology_kb(target)
                if result:
                    return self._format_target_biology_kb(result)
                else:
                    return f"No internal knowledge found for target: {target}"

            elif tool_name == "query_disease_knowledge":
                disease = tool_input.get("disease")
                if not disease:
                    return "Error: disease parameter is required"

                result = self.server.query_disease_kb(disease)
                if result:
                    return self._format_disease_kb(result)
                else:
                    return f"No internal knowledge found for disease: {disease}"

            elif tool_name == "query_competitive_intelligence":
                results = self.server.query_competitive_intelligence(
                    competitor=tool_input.get("competitor"),
                    drug=tool_input.get("drug"),
                    target=tool_input.get("target"),
                    indication=tool_input.get("indication"),
                    limit=tool_input.get("limit", 5)
                )
                return self._format_competitive_intelligence(results)

            else:
                return f"Unknown tool: {tool_name}"

        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name}: {str(e)}")
            return f"Error executing {tool_name}: {str(e)}"

    def _format_target_biology_kb(self, data: Dict[str, Any]) -> str:
        """Format target biology knowledge base entry"""
        formatted = f"# Internal Target Biology Assessment: {data.get('target_name')}\n\n"
        formatted += f"**Target Type**: {data.get('target_type', 'N/A')}\n"
        formatted += f"**Genetic Evidence Strength**: {data.get('genetic_evidence_strength', 'N/A')}\n"
        formatted += f"**Preclinical Validation Strength**: {data.get('preclinical_validation_strength', 'N/A')}\n"
        formatted += f"**Druggability Score**: {data.get('druggability_score', 0):.2f}\n"
        formatted += f"**Safety Risk Level**: {data.get('safety_risk_level', 'N/A')}\n"
        formatted += f"**Strategic Priority**: {data.get('strategic_priority', 'N/A')}\n"
        formatted += f"**Portfolio Fit Score**: {data.get('portfolio_fit_score', 0):.2f}\n\n"

        if data.get('competitive_landscape_assessment'):
            formatted += f"**Competitive Landscape**: {data.get('competitive_landscape_assessment')}\n\n"

        if data.get('internal_notes'):
            formatted += f"**Internal Notes**: {data.get('internal_notes')}\n\n"

        if data.get('failed_programs'):
            formatted += f"**Failed Programs**: {', '.join(data.get('failed_programs', []))}\n\n"

        if data.get('key_papers'):
            formatted += f"**Key Papers**: {', '.join(data.get('key_papers', []))}\n\n"

        formatted += f"**Last Reviewed**: {data.get('last_reviewed_date', 'N/A')}\n"

        return formatted

    def _format_disease_kb(self, data: Dict[str, Any]) -> str:
        """Format disease knowledge base entry"""
        formatted = f"# Internal Disease Assessment: {data.get('disease_name')}\n\n"

        if data.get('icd_codes'):
            formatted += f"**ICD Codes**: {', '.join(data.get('icd_codes', []))}\n"

        formatted += f"**US Prevalence**: {data.get('us_prevalence', 0):,}\n"
        formatted += f"**Global Prevalence**: {data.get('global_prevalence', 0):,}\n"
        formatted += f"**Market Size**: ${data.get('market_size_usd', 0):,.0f}\n"
        formatted += f"**Market Growth Rate**: {data.get('market_growth_rate', 0):.1f}%\n\n"

        formatted += f"**Strategic Priority**: {data.get('strategic_priority', 'N/A')}\n"
        formatted += f"**Unmet Need Severity**: {data.get('unmet_need_severity', 'N/A')}\n"
        formatted += f"**Competitive Intensity**: {data.get('competitive_intensity', 'N/A')}\n"
        formatted += f"**Internal Expertise Level**: {data.get('internal_expertise_level', 'N/A')}\n"
        formatted += f"**Portfolio Assets Count**: {data.get('portfolio_assets_count', 0)}\n\n"

        if data.get('internal_notes'):
            formatted += f"**Internal Notes**: {data.get('internal_notes')}\n\n"

        if data.get('key_kols'):
            formatted += f"**Key KOLs**: {', '.join(data.get('key_kols', []))}\n"

        if data.get('patient_advocacy_groups'):
            formatted += f"**Patient Advocacy Groups**: {', '.join(data.get('patient_advocacy_groups', []))}\n"

        formatted += f"\n**Last Reviewed**: {data.get('last_reviewed_date', 'N/A')}\n"

        return formatted

    def _format_competitive_intelligence(self, results: List[Dict[str, Any]]) -> str:
        """Format competitive intelligence results"""
        if not results:
            return "No competitive intelligence found in internal database."

        formatted = f"# Competitive Intelligence ({len(results)} entries found)\n\n"

        for entry in results:
            formatted += f"## {entry.get('competitor_name')} - {entry.get('drug_name', 'N/A')}\n"
            formatted += f"- **Target**: {entry.get('target_biology', 'N/A')}\n"
            formatted += f"- **Indication**: {entry.get('indication', 'N/A')}\n"
            formatted += f"- **Phase**: {entry.get('phase', 'N/A')}\n"
            formatted += f"- **Threat Level**: {entry.get('competitive_threat_level', 'N/A')}\n\n"

            if entry.get('latest_clinical_data'):
                formatted += f"**Latest Clinical Data**: {entry.get('latest_clinical_data')}\n\n"

            if entry.get('efficacy_signals'):
                formatted += f"**Efficacy Signals**: {', '.join(entry.get('efficacy_signals', []))}\n"

            if entry.get('safety_signals'):
                formatted += f"**Safety Signals**: {', '.join(entry.get('safety_signals', []))}\n"

            if entry.get('differentiation_vs_our_assets'):
                formatted += f"**Differentiation vs Our Assets**: {entry.get('differentiation_vs_our_assets')}\n"

            formatted += f"\n**Last Updated**: {entry.get('last_updated', 'N/A')}\n\n---\n\n"

        return formatted

    def close(self):
        """Clean up resources"""
        self.server.close()
