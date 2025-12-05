"""
Example Usage Scripts for Drug Repurposing Agent
Demonstrates various use cases and workflows
"""

import os
from datetime import datetime
from drug_repurposing_agent import DrugRepurposingAgent
from mechanism_based_agent import MechanismBasedAgent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def example_1_single_drug_analysis():
    """Example 1: Analyze a single drug for repurposing opportunities"""
    print("\n" + "="*80)
    print("EXAMPLE 1: Single Drug Analysis")
    print("="*80)
    
    agent = DrugRepurposingAgent(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY")
    )
    
    drug = "rimegepant"
    print(f"\nAnalyzing: {drug}")
    
    results = agent.analyze_drug(drug)
    
    print(f"\nApproved Indications:")
    for indication in results['approved_indications']:
        print(f"  - {indication}")
    
    print(f"\nRepurposing Opportunities Found: {len(results['case_series'])}")
    
    if results['case_series']:
        print("\nTop 3 Opportunities:")
        for idx, case in enumerate(results['case_series'][:3], 1):
            print(f"\n  {idx}. {case['disease']}")
            print(f"     Priority: {case['scores']['overall_priority']}/10")
            print(f"     N={case['n']}, {case['response_rate']}")
            print(f"     {case['efficacy_summary'][:80]}...")
    
    # Export
    output_file = f"{drug}_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    agent.export_to_excel(results, output_file)
    
    print(f"\n✓ Results exported to: {output_file}")
    print(f"✓ Cost: ${(agent.total_input_tokens * 0.003 / 1000 + agent.total_output_tokens * 0.015 / 1000):.2f}")


def example_2_mechanism_analysis():
    """Example 2: Analyze all drugs with a specific mechanism"""
    print("\n" + "="*80)
    print("EXAMPLE 2: Mechanism-Based Analysis")
    print("="*80)
    
    agent = MechanismBasedAgent(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY")
    )
    
    mechanism = "CGRP receptor antagonist"
    print(f"\nAnalyzing mechanism: {mechanism}")
    
    results = agent.analyze_mechanism(mechanism)
    
    print(f"\nDrugs Found: {len(results['drugs_analyzed'])}")
    for drug_result in results['drugs_analyzed']:
        print(f"  - {drug_result['drug_name']}: {len(drug_result['case_series'])} opportunities")
    
    print(f"\nTotal Opportunities: {results['metadata']['total_opportunities']}")
    
    # Export
    output_file = f"mechanism_{mechanism.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    agent.export_mechanism_analysis(results, output_file)
    
    print(f"\n✓ Results exported to: {output_file}")
    print(f"✓ Cost: ${(agent.total_input_tokens * 0.003 / 1000 + agent.total_output_tokens * 0.015 / 1000):.2f}")


def example_3_batch_drug_analysis():
    """Example 3: Batch analysis of multiple drugs"""
    print("\n" + "="*80)
    print("EXAMPLE 3: Batch Drug Analysis")
    print("="*80)
    
    agent = DrugRepurposingAgent(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY")
    )
    
    drugs = ["rimegepant", "ubrogepant", "atogepant"]
    all_results = []
    
    for drug in drugs:
        print(f"\nAnalyzing: {drug}")
        try:
            result = agent.analyze_drug(drug)
            all_results.append(result)
            print(f"  ✓ Found {len(result['case_series'])} opportunities")
        except Exception as e:
            print(f"  ✗ Error: {e}")
            continue
    
    # Combine results
    print(f"\n{'Drug':<15} {'Opportunities':<15} {'Top Priority':<15}")
    print("-" * 45)
    for result in all_results:
        top_score = result['case_series'][0]['scores']['overall_priority'] if result['case_series'] else 0
        print(f"{result['drug_name']:<15} {len(result['case_series']):<15} {top_score:<15}")
    
    # Export each
    for result in all_results:
        output_file = f"{result['drug_name']}_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        agent.export_to_excel(result, output_file)
        print(f"✓ Exported: {output_file}")


def example_4_filtered_high_priority():
    """Example 4: Focus on high-priority opportunities only"""
    print("\n" + "="*80)
    print("EXAMPLE 4: High-Priority Opportunities Only")
    print("="*80)
    
    agent = DrugRepurposingAgent(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY")
    )
    
    drug = "rimegepant"
    print(f"\nAnalyzing: {drug}")
    
    results = agent.analyze_drug(drug)
    
    # Filter for high priority (score >= 7.0)
    high_priority = [
        case for case in results['case_series']
        if case['scores']['overall_priority'] >= 7.0
    ]
    
    print(f"\nTotal opportunities: {len(results['case_series'])}")
    print(f"High priority (≥7.0): {len(high_priority)}")
    
    if high_priority:
        print("\nHigh-Priority Opportunities:")
        for case in high_priority:
            print(f"\n  • {case['disease']}")
            print(f"    Priority: {case['scores']['overall_priority']}/10")
            print(f"    Clinical Signal: {case['scores']['clinical_signal']}/10")
            print(f"    Market Score: {case['scores']['market_opportunity']}/10")
            print(f"    Prevalence: {case['market_data'].get('us_prevalence_estimate', 'N/A')}")
    else:
        print("\nNo high-priority opportunities found (all scores < 7.0)")


def example_5_custom_scoring():
    """Example 5: Custom scoring weights"""
    print("\n" + "="*80)
    print("EXAMPLE 5: Custom Scoring Weights")
    print("="*80)
    
    agent = DrugRepurposingAgent(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY")
    )
    
    # Custom scoring function that heavily weights clinical signal
    def custom_score(case):
        clinical = agent._score_clinical_signal(case)
        evidence = agent._score_evidence_quality(case)
        market = agent._score_market_opportunity(case)
        feasibility = 7
        
        # 70% clinical, 20% evidence, 10% market
        overall = clinical * 0.7 + evidence * 0.2 + market * 0.1
        
        return {
            'clinical_signal': clinical,
            'evidence_quality': evidence,
            'market_opportunity': market,
            'feasibility': feasibility,
            'overall_priority': round(overall, 1)
        }
    
    # Replace scoring function
    original_score = agent._score_opportunity
    agent._score_opportunity = custom_score
    
    drug = "rimegepant"
    print(f"\nAnalyzing: {drug}")
    print("Using custom weights: 70% clinical, 20% evidence, 10% market")
    
    results = agent.analyze_drug(drug)
    
    print(f"\nTop opportunities with custom scoring:")
    for idx, case in enumerate(results['case_series'][:3], 1):
        print(f"\n  {idx}. {case['disease']}")
        print(f"     Overall: {case['scores']['overall_priority']}/10")
        print(f"     Clinical: {case['scores']['clinical_signal']}/10")
        print(f"     Evidence: {case['scores']['evidence_quality']}/10")


def example_6_therapeutic_area_focus():
    """Example 6: Focus on specific therapeutic area"""
    print("\n" + "="*80)
    print("EXAMPLE 6: Therapeutic Area Focus - Neurology")
    print("="*80)
    
    agent = DrugRepurposingAgent(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY")
    )
    
    drug = "rimegepant"
    print(f"\nAnalyzing: {drug}")
    
    results = agent.analyze_drug(drug)
    
    # Filter for neurological conditions
    neuro_keywords = [
        'headache', 'neuralgia', 'neuropathy', 'migraine', 
        'neurological', 'nerve', 'brain', 'cerebral'
    ]
    
    neuro_opportunities = [
        case for case in results['case_series']
        if any(keyword in case['disease'].lower() for keyword in neuro_keywords)
    ]
    
    print(f"\nTotal opportunities: {len(results['case_series'])}")
    print(f"Neurological opportunities: {len(neuro_opportunities)}")
    
    if neuro_opportunities:
        print("\nNeurological Opportunities:")
        for case in neuro_opportunities:
            print(f"\n  • {case['disease']}")
            print(f"    Priority: {case['scores']['overall_priority']}/10")
            print(f"    N={case['n']}, {case['response_rate']}")


def run_all_examples():
    """Run all examples"""
    print("\n" + "="*80)
    print("DRUG REPURPOSING AGENT - EXAMPLE USAGE SCRIPTS")
    print("="*80)
    
    # Check API keys
    if not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("TAVILY_API_KEY"):
        print("\n⚠ ERROR: API keys not found!")
        print("Please set ANTHROPIC_API_KEY and TAVILY_API_KEY environment variables")
        print("\nYou can:")
        print("1. Copy .env.template to .env and add your keys")
        print("2. Export them in your shell:")
        print("   export ANTHROPIC_API_KEY='your-key'")
        print("   export TAVILY_API_KEY='your-key'")
        return
    
    print("\nAPI keys found ✓")
    print("\nSelect an example to run:")
    print("  1. Single Drug Analysis")
    print("  2. Mechanism-Based Analysis")
    print("  3. Batch Drug Analysis")
    print("  4. High-Priority Opportunities Only")
    print("  5. Custom Scoring Weights")
    print("  6. Therapeutic Area Focus")
    print("  7. Run All Examples (WARNING: High cost)")
    print("  0. Exit")
    
    choice = input("\nEnter choice (1-7, 0 to exit): ").strip()
    
    examples = {
        '1': example_1_single_drug_analysis,
        '2': example_2_mechanism_analysis,
        '3': example_3_batch_drug_analysis,
        '4': example_4_filtered_high_priority,
        '5': example_5_custom_scoring,
        '6': example_6_therapeutic_area_focus
    }
    
    if choice == '0':
        print("\nExiting...")
        return
    elif choice == '7':
        confirm = input("\n⚠ Running all examples will cost ~$10-20. Continue? (y/n): ")
        if confirm.lower() == 'y':
            for func in examples.values():
                func()
        else:
            print("\nCancelled.")
    elif choice in examples:
        examples[choice]()
    else:
        print(f"\n⚠ Invalid choice: {choice}")


if __name__ == "__main__":
    run_all_examples()
