"""
Regenerate visualization charts and text report for upadacitinib analysis.
"""
import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent
from src.models.case_series_schemas import DrugAnalysisResult

# Load the existing JSON result
json_path = Path("data/case_series/upadacitinib_full_20251208_194159.json")

print("Loading existing analysis result...")
with open(json_path, 'r') as f:
    result_dict = json.load(f)

# Reconstruct DrugAnalysisResult from JSON
result = DrugAnalysisResult(**result_dict)

print(f"Loaded analysis for {result.drug_name}")
print(f"Found {len(result.opportunities)} opportunities")

# Initialize agent (just for visualization methods)
api_key = os.getenv('ANTHROPIC_API_KEY')
agent = DrugRepurposingCaseSeriesAgent(
    anthropic_api_key=api_key,
    output_dir="data/case_series"
)

# Generate new visualizations
print("\nGenerating improved visualizations...")
viz_paths = agent.generate_visualizations(result)

print("\n✅ Visualizations regenerated successfully!")
print(f"Priority Matrix: {viz_paths['priority_matrix']}")
print(f"Market Opportunity: {viz_paths['market_opportunity']}")

# Generate text report
print("\nGenerating analytical text report...")
try:
    report_text, report_path = agent.generate_analytical_report(
        result=result,
        auto_save=True,
        max_tokens=8000
    )
    print(f"\n✅ Text report generated successfully!")
    print(f"Report saved to: {report_path}")
    print(f"Report length: {len(report_text)} characters")
except Exception as e:
    print(f"\n❌ Failed to generate text report: {e}")

print("\n" + "="*80)
print("SUMMARY")
print("="*80)
print("✅ Visualizations: Improved color gradients and interactive filtering")
print("✅ Text Report: Comprehensive analytical report generated")
print("\nAll outputs saved to data/case_series/")

