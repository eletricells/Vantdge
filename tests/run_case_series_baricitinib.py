#!/usr/bin/env python3
"""
Test script for the enhanced DrugRepurposingCaseSeriesAgent with multi-stage extraction.
Runs the full baricitinib workflow to verify the changes work.
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent

def main():
    load_dotenv()
    
    # Get API keys from environment
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    pubmed_email = os.getenv("PUBMED_EMAIL", "user@example.com")
    pubmed_api_key = os.getenv("PUBMED_API_KEY")
    semantic_scholar_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
    
    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        return
    
    print("=" * 60)
    print("DRUG REPURPOSING CASE SERIES AGENT - MULTI-STAGE TEST")
    print("=" * 60)
    print(f"Drug: baricitinib")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Initialize agent
    agent = DrugRepurposingCaseSeriesAgent(
        anthropic_api_key=anthropic_key,
        pubmed_email=pubmed_email,
        pubmed_api_key=pubmed_api_key,
        semantic_scholar_api_key=semantic_scholar_key,
        output_dir="data/case_series"
    )
    
    print("\n[1/4] Running full analysis for baricitinib...")
    print("This will search PubMed + Semantic Scholar for case reports/series")
    print("-" * 60)
    
    # Run the analysis
    result = agent.analyze_drug("baricitinib")
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    
    # Print summary
    print(f"\nDrug: {result.drug_name}")
    print(f"Mechanism: {result.mechanism}")
    print(f"Approved Indications: {', '.join(result.approved_indications)}")
    print(f"\nTotal Opportunities Found: {len(result.opportunities)}")
    
    # Count extraction methods
    single_pass_count = 0
    multi_stage_count = 0
    
    for opp in result.opportunities:
        if hasattr(opp.extraction, 'extraction_method'):
            if opp.extraction.extraction_method == 'multi_stage':
                multi_stage_count += 1
            else:
                single_pass_count += 1
        else:
            single_pass_count += 1
    
    print(f"\nExtraction Methods Used:")
    print(f"  - Single-pass: {single_pass_count}")
    print(f"  - Multi-stage: {multi_stage_count}")
    
    # Show detailed endpoints from multi-stage extractions
    print("\n" + "-" * 60)
    print("MULTI-STAGE EXTRACTION DETAILS")
    print("-" * 60)
    
    for i, opp in enumerate(result.opportunities[:10], 1):  # Show first 10
        extraction = opp.extraction
        method = getattr(extraction, 'extraction_method', 'single_pass')
        
        print(f"\n{i}. {extraction.disease}")
        print(f"   PMID: {extraction.source.pmid}")
        print(f"   Method: {method}")
        
        if method == 'multi_stage':
            efficacy_eps = getattr(extraction, 'detailed_efficacy_endpoints', [])
            safety_eps = getattr(extraction, 'detailed_safety_endpoints', [])
            stages = getattr(extraction, 'extraction_stages_completed', [])
            
            print(f"   Stages completed: {stages}")
            print(f"   Detailed efficacy endpoints: {len(efficacy_eps)}")
            print(f"   Detailed safety endpoints: {len(safety_eps)}")
            
            # Show first few endpoints
            if efficacy_eps:
                print("   Sample efficacy endpoints:")
                for ep in efficacy_eps[:3]:
                    name = ep.endpoint_name if hasattr(ep, 'endpoint_name') else ep.get('endpoint_name', 'Unknown')
                    print(f"     - {name}")
    
    print("\n" + "=" * 60)
    print(f"Results saved to: data/case_series/")
    print("=" * 60)

if __name__ == "__main__":
    main()

