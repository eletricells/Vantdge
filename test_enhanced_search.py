"""
Test script to compare old vs new search results for baricitinib.
Focuses on whether the enhanced search finds JDM case studies.
"""
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.agents.drug_repurposing_case_series_agent import DrugRepurposingCaseSeriesAgent

def main():
    # Initialize agent
    agent = DrugRepurposingCaseSeriesAgent(
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        pubmed_email=os.getenv("PUBMED_EMAIL", "test@example.com"),
        pubmed_api_key=os.getenv("PUBMED_API_KEY"),
        tavily_api_key=os.getenv("TAVILY_API_KEY"),
        semantic_scholar_api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
        output_dir="data/case_series_test"
    )
    
    # Test the enhanced search only (not full analysis)
    drug_name = "baricitinib"
    exclude_indications = [
        "rheumatoid arthritis",
        "alopecia areata", 
        "covid-19",
        "coronavirus"
    ]
    
    print(f"\n{'='*60}")
    print(f"Testing enhanced search for: {drug_name}")
    print(f"Excluding: {exclude_indications}")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    
    # Run the search
    papers = agent._search_case_series(
        drug_name=drug_name,
        exclude_indications=exclude_indications,
        max_papers=200,
        include_web_search=True,
        include_semantic_scholar=True,
        include_citation_mining=True,
        use_llm_filtering=True
    )
    
    elapsed = time.time() - start_time
    
    print(f"\n{'='*60}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Total papers found: {len(papers)}")
    print(f"Time elapsed: {elapsed:.1f} seconds")
    print(f"API calls made: {agent.search_count}")
    
    # Extract diseases from LLM filtering
    diseases_found = {}
    for paper in papers:
        disease = paper.get('extracted_disease', 'Unknown')
        if disease:
            if disease not in diseases_found:
                diseases_found[disease] = []
            diseases_found[disease].append({
                'title': paper.get('title', 'No title')[:80],
                'pmid': paper.get('pmid'),
                'source': paper.get('source', 'Unknown')
            })
    
    print(f"\nDiseases identified: {len(diseases_found)}")
    print("-" * 40)
    for disease in sorted(diseases_found.keys()):
        papers_list = diseases_found[disease]
        print(f"\n{disease} ({len(papers_list)} papers):")
        for p in papers_list[:3]:  # Show first 3
            print(f"  - {p['title']}")
            if p['pmid']:
                print(f"    PMID: {p['pmid']}")
    
    # Check specifically for JDM / dermatomyositis
    jdm_keywords = ['juvenile dermatomyositis', 'jdm', 'dermatomyositis', 'myositis']
    jdm_found = []
    for paper in papers:
        title = (paper.get('title') or '').lower()
        abstract = (paper.get('abstract') or '').lower()
        disease = (paper.get('extracted_disease') or '').lower()
        
        for kw in jdm_keywords:
            if kw in title or kw in abstract or kw in disease:
                jdm_found.append(paper)
                break
    
    print(f"\n{'='*60}")
    print(f"JDM / DERMATOMYOSITIS CHECK")
    print(f"{'='*60}")
    print(f"Papers mentioning JDM/dermatomyositis: {len(jdm_found)}")
    for paper in jdm_found[:10]:
        print(f"\n  Title: {paper.get('title', 'No title')[:100]}")
        print(f"  PMID: {paper.get('pmid', 'N/A')}")
        print(f"  Source: {paper.get('source', 'Unknown')}")
        print(f"  Disease: {paper.get('extracted_disease', 'N/A')}")
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"data/case_series_test/baricitinib_enhanced_test_{timestamp}.json"
    os.makedirs("data/case_series_test", exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump({
            'drug_name': drug_name,
            'search_timestamp': timestamp,
            'total_papers': len(papers),
            'diseases_found': list(diseases_found.keys()),
            'jdm_papers_count': len(jdm_found),
            'papers': papers
        }, f, indent=2, default=str)
    
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()

