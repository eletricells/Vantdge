"""
Test the literature search workflow with tapinarof.
"""
import sys
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_literature_search():
    """Test the literature search workflow with tapinarof."""
    from src.utils.config import get_settings
    from src.tools.pubmed import PubMedAPI
    from src.tools.clinicaltrials import ClinicalTrialsAPI
    from src.tools.web_search import WebSearchTool
    from src.agents.paperscope_v2 import PaperScopeV2Agent
    from anthropic import Anthropic
    
    settings = get_settings()
    
    print("="*80)
    print("Testing Literature Search Workflow with 'tapinarof'")
    print("="*80)
    
    # Check API keys
    print("\n1. Checking API keys...")
    print(f"   Anthropic API key: {'✓ Set' if settings.anthropic_api_key else '✗ Missing'}")
    print(f"   PubMed API key: {'✓ Set' if settings.pubmed_api_key else '○ Not set (using lower rate limit)'}")
    print(f"   Tavily API key: {'✓ Set' if settings.tavily_api_key else '○ Not set (web search disabled)'}")
    
    if not settings.anthropic_api_key:
        print("\n❌ Anthropic API key is required!")
        return False
    
    # Initialize APIs
    print("\n2. Initializing APIs...")
    try:
        pubmed_api = PubMedAPI(
            api_key=settings.pubmed_api_key,
            email="noreply@example.com"
        )
        print("   ✓ PubMed API initialized")
    except Exception as e:
        print(f"   ✗ PubMed API failed: {e}")
        return False
    
    try:
        anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
        print("   ✓ Anthropic client initialized")
    except Exception as e:
        print(f"   ✗ Anthropic client failed: {e}")
        return False
    
    web_search_tool = None
    if settings.tavily_api_key:
        try:
            web_search_tool = WebSearchTool(api_key=settings.tavily_api_key)
            print("   ✓ Web search tool initialized")
        except Exception as e:
            print(f"   ○ Web search tool failed (optional): {e}")
    
    ct_api = None
    try:
        ct_api = ClinicalTrialsAPI()
        print("   ✓ ClinicalTrials.gov API initialized")
    except Exception as e:
        print(f"   ○ ClinicalTrials API failed (optional): {e}")
    
    # Initialize PaperScope agent
    print("\n3. Initializing PaperScope V2 Agent...")
    try:
        agent = PaperScopeV2Agent(
            pubmed_api=pubmed_api,
            anthropic_client=anthropic_client,
            web_search_tool=web_search_tool,
            clinicaltrials_api=ct_api,
            output_dir="data/paperscope_v2/test"
        )
        print("   ✓ PaperScope V2 Agent initialized")
    except Exception as e:
        print(f"   ✗ PaperScope V2 Agent failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Run search
    print("\n4. Running literature search for 'tapinarof'...")
    print("   (This may take a few minutes...)")
    try:
        results = agent.search_and_categorize(
            drug_name="tapinarof",
            max_results_per_search=20  # Reduced for testing
        )
        print("   ✓ Search completed!")
    except Exception as e:
        print(f"   ✗ Search failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Display results
    print("\n5. Results Summary:")
    metadata = results.get('metadata', {})
    print(f"   Total papers: {metadata.get('total_unique_papers', 0)}")
    print(f"   Ongoing trials: {metadata.get('ongoing_trials_count', 0)}")
    print(f"   Elapsed time: {metadata.get('elapsed_seconds', 0):.1f}s")
    print(f"   Detected indication: {metadata.get('disease_indication', 'N/A')}")
    print(f"   Drug class: {metadata.get('drug_class', 'N/A')}")
    
    # Show paper sources
    sources = metadata.get('paper_sources', {})
    if sources:
        print("\n   Paper Sources:")
        for source, count in sources.items():
            print(f"     - {source}: {count}")
    
    # Show categorized papers
    categorized = results.get('categorized_papers', {})
    if categorized:
        print("\n   Papers by Category:")
        for category, papers in categorized.items():
            if papers:
                print(f"     - {category}: {len(papers)} papers")
    
    # Show sample papers
    print("\n6. Sample Papers (first 3):")
    all_papers = []
    for papers in categorized.values():
        all_papers.extend(papers)
    
    for i, paper in enumerate(all_papers[:3]):
        print(f"\n   [{i+1}] {paper.get('title', 'No title')[:80]}...")
        print(f"       PMID: {paper.get('pmid', 'N/A')}")
        print(f"       Year: {paper.get('year', 'N/A')}")
        print(f"       Category: {paper.get('category', 'N/A')}")
    
    print("\n" + "="*80)
    print("✓ Literature search workflow test completed successfully!")
    print("="*80)
    
    return True


if __name__ == "__main__":
    success = test_literature_search()
    sys.exit(0 if success else 1)

