"""
Drug Repurposing Case Series Agent

Systematically identifies and analyzes drug repurposing opportunities by mining
case series and case reports from medical literature.

Features:
- Integrates with existing Vantdge infrastructure (DrugDatabase, PubMedAPI, etc.)
- Uses both PubMed (peer-reviewed) and Tavily (grey literature) for comprehensive search
- Extracts structured clinical evidence using Claude with extended thinking
- Enriches with market intelligence (epidemiology, SOC, competitive landscape)
- Scores and ranks opportunities by clinical signal, evidence quality, market size

Workflow:
1. Get drug info and approved indications (via DrugDatabase/DailyMed)
2. Search for case series/reports (PubMed + Tavily)
3. Extract structured data from each case series
4. Enrich with market intelligence
5. Score and rank opportunities
6. Export to Excel/JSON
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set

from anthropic import Anthropic
from pydantic import ValidationError

from src.models.case_series_schemas import (
    CaseSeriesExtraction,
    CaseSeriesSource,
    PatientPopulation,
    TreatmentDetails,
    EfficacyOutcome,
    SafetyOutcome,
    EvidenceLevel,
    OutcomeResult,
    EfficacySignal,
    SafetyProfile,
    EpidemiologyData,
    StandardOfCareData,
    StandardOfCareTreatment,
    MarketIntelligence,
    OpportunityScores,
    RepurposingOpportunity,
    DrugAnalysisResult,
    MechanismAnalysisResult,
)
from src.tools.pubmed import PubMedAPI
from src.tools.web_search import WebSearchTool
from src.tools.drug_database import DrugDatabase
from src.tools.dailymed import DailyMedAPI

logger = logging.getLogger(__name__)


class DrugRepurposingCaseSeriesAgent:
    """
    Agent for identifying drug repurposing opportunities through case series mining.
    
    Integrates with existing Vantdge infrastructure for robust drug data retrieval
    and comprehensive literature search.
    """
    
    def __init__(
        self,
        anthropic_api_key: str,
        database_url: Optional[str] = None,
        pubmed_email: str = "user@example.com",
        pubmed_api_key: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        output_dir: str = "data/case_series"
    ):
        """
        Initialize agent with all required tools.
        
        Args:
            anthropic_api_key: Anthropic API key for Claude
            database_url: PostgreSQL database URL (optional, for drug lookups)
            pubmed_email: Email for PubMed API
            pubmed_api_key: PubMed API key (optional, increases rate limits)
            tavily_api_key: Tavily API key for web search
            output_dir: Directory for output files
        """
        # Initialize Claude client
        self.client = Anthropic(api_key=anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"
        self.max_tokens = 16000
        
        # Initialize tools
        self.pubmed = PubMedAPI(
            email=pubmed_email,
            api_key=pubmed_api_key
        )
        
        self.web_search = None
        if tavily_api_key:
            self.web_search = WebSearchTool(api_key=tavily_api_key)
        
        # Database connection (optional)
        self.drug_db = None
        if database_url:
            try:
                self.drug_db = DrugDatabase(database_url)
                self.drug_db.connect()
                logger.info("Connected to drug database")
            except Exception as e:
                logger.warning(f"Could not connect to drug database: {e}")
                self.drug_db = None

        # DailyMed API for FDA label data
        self.dailymed = DailyMedAPI()

        # Drugs.com scraper (lazy loaded)
        self._drugs_com_scraper = None

        # Output directory
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.search_count = 0
        
        logger.info("DrugRepurposingCaseSeriesAgent initialized")
    
    # =========================================================================
    # MAIN ANALYSIS METHODS
    # =========================================================================
    
    def analyze_drug(
        self,
        drug_name: str,
        max_papers: int = 50,
        include_web_search: bool = True,
        enrich_market_data: bool = True
    ) -> DrugAnalysisResult:
        """
        Main entry point: analyze a drug for repurposing opportunities.
        
        Args:
            drug_name: Drug name to analyze
            max_papers: Maximum papers to screen
            include_web_search: Whether to include Tavily web search
            enrich_market_data: Whether to enrich with market intelligence
            
        Returns:
            DrugAnalysisResult with all opportunities found
        """
        logger.info(f"Starting repurposing analysis for: {drug_name}")
        start_time = datetime.now()
        
        # Reset cost tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.search_count = 0
        
        # Step 1: Get drug information and approved indications
        drug_info = self._get_drug_info(drug_name)
        approved_indications = drug_info.get("approved_indications", [])
        logger.info(f"Found {len(approved_indications)} approved indications")

        # Step 2: Search for case series/reports
        papers = self._search_case_series(
            drug_name,
            approved_indications,
            max_papers=max_papers,
            include_web_search=include_web_search
        )
        logger.info(f"Found {len(papers)} potential case series/reports")

        # Step 3: Extract structured data from each paper
        opportunities = []
        for i, paper in enumerate(papers, 1):
            logger.info(f"Extracting data from paper {i}/{len(papers)}: {paper.get('title', 'Unknown')[:50]}...")
            try:
                extraction = self._extract_case_series_data(drug_name, drug_info, paper)
                if extraction:
                    opportunity = RepurposingOpportunity(extraction=extraction)
                    opportunities.append(opportunity)
            except Exception as e:
                logger.error(f"Error extracting paper {i}: {e}")
                continue

            # Rate limiting
            if i < len(papers):
                time.sleep(0.5)

        logger.info(f"Successfully extracted {len(opportunities)} case series")

        # Step 4: Enrich with market intelligence
        if enrich_market_data and opportunities:
            opportunities = self._enrich_with_market_data(opportunities)

        # Step 5: Score and rank opportunities
        opportunities = self._score_opportunities(opportunities)
        opportunities.sort(key=lambda x: x.scores.overall_priority, reverse=True)

        # Assign ranks
        for i, opp in enumerate(opportunities, 1):
            opp.rank = i

        # Calculate cost
        estimated_cost = self._calculate_cost()

        # Build result
        result = DrugAnalysisResult(
            drug_name=drug_name,
            generic_name=drug_info.get("generic_name"),
            mechanism=drug_info.get("mechanism"),
            target=drug_info.get("target"),
            approved_indications=approved_indications,
            opportunities=opportunities,
            analysis_date=datetime.now(),
            papers_screened=len(papers),
            papers_extracted=len(opportunities),
            total_input_tokens=self.total_input_tokens,
            total_output_tokens=self.total_output_tokens,
            estimated_cost_usd=estimated_cost
        )

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Analysis complete in {duration:.1f}s. Found {len(opportunities)} opportunities. Cost: ${estimated_cost:.2f}")

        return result

    def analyze_mechanism(
        self,
        mechanism: str,
        max_drugs: int = 10,
        **kwargs
    ) -> MechanismAnalysisResult:
        """
        Analyze all drugs with a given mechanism for repurposing opportunities.

        Args:
            mechanism: Mechanism to analyze (e.g., "JAK inhibitor", "CGRP antagonist")
            max_drugs: Maximum number of drugs to analyze
            **kwargs: Additional args passed to analyze_drug

        Returns:
            MechanismAnalysisResult with all drugs and opportunities
        """
        logger.info(f"Starting mechanism-based analysis: {mechanism}")

        # Find drugs with this mechanism
        drugs = self._find_drugs_by_mechanism(mechanism, max_drugs=max_drugs)
        logger.info(f"Found {len(drugs)} drugs with mechanism: {mechanism}")

        # Analyze each drug
        results = []
        total_opportunities = 0
        total_cost = 0.0

        for i, drug_name in enumerate(drugs, 1):
            logger.info(f"Analyzing drug {i}/{len(drugs)}: {drug_name}")
            try:
                result = self.analyze_drug(drug_name, **kwargs)
                results.append(result)
                total_opportunities += len(result.opportunities)
                total_cost += result.estimated_cost_usd
            except Exception as e:
                logger.error(f"Error analyzing {drug_name}: {e}")
                continue

            # Rate limiting between drugs
            if i < len(drugs):
                time.sleep(1)

        return MechanismAnalysisResult(
            mechanism=mechanism,
            drugs_analyzed=results,
            total_opportunities=total_opportunities,
            analysis_date=datetime.now(),
            total_cost_usd=total_cost
        )

    # =========================================================================
    # DRUG INFORMATION RETRIEVAL
    # =========================================================================

    def _get_drug_info(self, drug_name: str) -> Dict[str, Any]:
        """
        Get drug information including approved indications.

        Data sources are queried in the following order:
        1. DrugDatabase (PostgreSQL) - cached data from previous runs
        2. DailyMed API - official FDA drug labeling (best for generic_name, mechanism)
        3. Drugs.com Scraping - extracts approved indications from drug monographs
        4. Web Search Fallback - Tavily web search with Claude extraction

        Data is merged across sources to get the most complete picture.
        """
        drug_info = {
            "drug_name": drug_name,
            "generic_name": None,
            "mechanism": None,
            "target": None,
            "approved_indications": []
        }

        # 1. Try database first (cached data from previous runs)
        if self.drug_db:
            db_info = self._get_drug_from_database(drug_name)
            if db_info:
                drug_info.update(db_info)
                if drug_info.get("approved_indications") and drug_info.get("generic_name"):
                    logger.info(f"Got complete drug info from database: {len(drug_info['approved_indications'])} indications")
                    return drug_info

        # 2. Try OpenFDA API first for short mechanism (Established Pharmacologic Class)
        short_mechanism = self._get_short_mechanism_from_openfda(drug_name)
        if short_mechanism:
            drug_info["mechanism"] = short_mechanism
            logger.info(f"Got short mechanism from OpenFDA: {short_mechanism}")

        # 3. Try DailyMed API for official FDA labeling (best source for generic_name)
        dailymed_info = self._get_drug_from_dailymed(drug_name)
        if dailymed_info:
            # Always merge generic_name from DailyMed
            if dailymed_info.get("generic_name"):
                drug_info["generic_name"] = dailymed_info["generic_name"]
            # Only use DailyMed mechanism if we didn't get a short one from OpenFDA
            if not drug_info.get("mechanism") and dailymed_info.get("mechanism"):
                drug_info["mechanism"] = dailymed_info["mechanism"]
            if dailymed_info.get("manufacturer"):
                drug_info["manufacturer"] = dailymed_info["manufacturer"]

            # Only use DailyMed indications if they look good (not raw text blobs)
            dailymed_indications = dailymed_info.get("approved_indications", [])
            if dailymed_indications and len(dailymed_indications) > 0:
                # DailyMed indications are often raw text, check if they're usable
                first_indication = dailymed_indications[0] if dailymed_indications else ""
                # If it's a short, clean indication list, use it
                if len(first_indication) < 200:
                    drug_info["approved_indications"] = dailymed_indications
                    logger.info(f"Got drug info from DailyMed: {len(drug_info['approved_indications'])} indications, generic={drug_info.get('generic_name')}")
                    return drug_info

        # 4. Try Drugs.com scraping for cleaner indications list
        drugs_com_info = self._get_drug_from_drugs_com(drug_name)
        if drugs_com_info:
            if drugs_com_info.get("approved_indications"):
                drug_info["approved_indications"] = drugs_com_info["approved_indications"]
                logger.info(f"Got indications from Drugs.com: {len(drug_info['approved_indications'])} indications")

                # If we still don't have generic_name/mechanism, try to get from DailyMed again
                if not drug_info.get("generic_name") or not drug_info.get("mechanism"):
                    if dailymed_info:
                        if not drug_info.get("generic_name") and dailymed_info.get("generic_name"):
                            drug_info["generic_name"] = dailymed_info["generic_name"]
                        if not drug_info.get("mechanism") and dailymed_info.get("mechanism"):
                            drug_info["mechanism"] = dailymed_info["mechanism"]

                return drug_info

        # 5. Fall back to web search
        if self.web_search:
            web_info = self._get_drug_info_from_web(drug_name)
            if web_info:
                if web_info.get("approved_indications"):
                    drug_info["approved_indications"] = web_info["approved_indications"]
                if not drug_info.get("generic_name") and web_info.get("generic_name"):
                    drug_info["generic_name"] = web_info["generic_name"]
                if not drug_info.get("mechanism") and web_info.get("mechanism"):
                    drug_info["mechanism"] = web_info["mechanism"]

                if drug_info.get("approved_indications"):
                    logger.info(f"Got drug info from web search: {len(drug_info['approved_indications'])} indications")

        return drug_info

    def _get_drug_from_dailymed(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Get drug info from DailyMed API (FDA official labeling)."""
        try:
            # Use get_drug_info which handles search + label parsing
            info = self.dailymed.get_drug_info(drug_name)
            if not info:
                logger.debug(f"No DailyMed data found for {drug_name}")
                return None

            result = {
                "generic_name": info.get("generic_name"),
                "mechanism": info.get("mechanism_of_action"),
                "approved_indications": [],
                "manufacturer": info.get("manufacturer"),
                "route_of_administration": info.get("route_of_administration", [])
            }

            # Extract indications
            indications = info.get("indications", [])
            if isinstance(indications, list):
                result["approved_indications"] = indications
            elif isinstance(indications, str):
                result["approved_indications"] = [indications]

            logger.info(f"Got DailyMed data for {drug_name}: generic={result.get('generic_name')}, mechanism={'Yes' if result.get('mechanism') else 'No'}")
            return result if result.get("approved_indications") or result.get("generic_name") else None

        except Exception as e:
            logger.debug(f"DailyMed API error for {drug_name}: {e}")
            return None

    def _get_short_mechanism_from_openfda(self, drug_name: str) -> Optional[str]:
        """
        Get short mechanism description from OpenFDA's Established Pharmacologic Class (EPC).

        OpenFDA provides standardized, concise pharmacologic class information like:
        - "Janus Kinase Inhibitor [EPC]"
        - "Tumor Necrosis Factor Blocker [EPC]"
        - "Selective Serotonin Reuptake Inhibitor [EPC]"

        This is much more concise than the full mechanism text from DailyMed.
        """
        try:
            import requests

            # Query OpenFDA drug label API - simplified query
            url = "https://api.fda.gov/drug/label.json"
            # Use simple search without quotes first
            params = {
                "search": f"openfda.generic_name:{drug_name}",
                "limit": 1
            }

            response = requests.get(url, params=params, timeout=10)

            # If simple search fails, try with OR
            if response.status_code != 200:
                params = {
                    "search": f"openfda.brand_name:{drug_name}",
                    "limit": 1
                }
                response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                logger.warning(f"OpenFDA API returned status {response.status_code} for {drug_name}")
                return None

            data = response.json()
            results = data.get("results", [])

            if not results:
                logger.warning(f"No OpenFDA results for {drug_name}")
                return None

            openfda = results[0].get("openfda", {})
            logger.info(f"OpenFDA keys for {drug_name}: {list(openfda.keys())}")

            # Try pharm_class_epc first (Established Pharmacologic Class)
            epc = openfda.get("pharm_class_epc", [])
            if epc:
                # Clean up the EPC - remove "[EPC]" suffix
                mechanism = epc[0].replace(" [EPC]", "")
                logger.info(f"Got short mechanism from OpenFDA EPC for {drug_name}: {mechanism}")
                return mechanism

            # Fallback to pharm_class_moa (Mechanism of Action class)
            moa = openfda.get("pharm_class_moa", [])
            if moa:
                mechanism = moa[0].replace(" [MoA]", "").replace(" [MoA]", "")
                logger.info(f"Got short mechanism from OpenFDA MoA for {drug_name}: {mechanism}")
                return mechanism

            logger.warning(f"No pharmacologic class found in OpenFDA for {drug_name}: {openfda}")
            return None

        except Exception as e:
            logger.error(f"OpenFDA API error for {drug_name}: {e}")
            return None

    def _get_drug_from_drugs_com(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Get drug info from Drugs.com scraping."""
        try:
            # Lazy load the scraper
            if self._drugs_com_scraper is None:
                try:
                    from src.tools.drugs_com_scraper import DrugsComScraper
                    self._drugs_com_scraper = DrugsComScraper()
                except ImportError:
                    logger.debug("Drugs.com scraper not available")
                    return None

            # Get approval timeline which includes indications
            approval_events = self._drugs_com_scraper.get_approval_timeline(drug_name)

            if not approval_events:
                return None

            # Extract unique indications
            indications = []
            for event in approval_events:
                indication = event.get("indication") or event.get("indication_normalized")
                if indication and indication not in indications:
                    indications.append(indication)

            if not indications:
                return None

            result = {
                "approved_indications": indications
            }

            # Try to get additional info
            if hasattr(self._drugs_com_scraper, 'get_drug_info'):
                info = self._drugs_com_scraper.get_drug_info(drug_name)
                if info:
                    result["generic_name"] = info.get("generic_name")
                    result["mechanism"] = info.get("mechanism")

            return result

        except Exception as e:
            logger.debug(f"Drugs.com scraper error for {drug_name}: {e}")
            return None

    def _get_drug_from_database(self, drug_name: str) -> Optional[Dict[str, Any]]:
        """Get drug info from database."""
        if not self.drug_db:
            return None

        try:
            # Search for drug
            cursor = self.drug_db.connection.cursor()
            cursor.execute("""
                SELECT
                    d.drug_id,
                    d.brand_name,
                    d.generic_name,
                    d.mechanism_of_action,
                    d.drug_type
                FROM drugs d
                WHERE d.brand_name ILIKE %s OR d.generic_name ILIKE %s
                LIMIT 1
            """, (f"%{drug_name}%", f"%{drug_name}%"))

            result = cursor.fetchone()
            if not result:
                return None

            drug_id, brand_name, generic_name, mechanism, drug_type = result

            # Get approved indications
            cursor.execute("""
                SELECT DISTINCT dis.disease_name_standard
                FROM drug_indications di
                JOIN diseases dis ON di.disease_id = dis.disease_id
                WHERE di.drug_id = %s AND di.approval_status = 'Approved'
            """, (drug_id,))

            indications = [row[0] for row in cursor.fetchall()]
            cursor.close()

            return {
                "drug_id": drug_id,
                "drug_name": brand_name or drug_name,
                "generic_name": generic_name,
                "mechanism": mechanism,
                "approved_indications": indications
            }

        except Exception as e:
            logger.error(f"Database query error: {e}")
            return None

    def _get_drug_info_from_web(self, drug_name: str) -> Dict[str, Any]:
        """Get drug info via web search."""
        if not self.web_search:
            return {"approved_indications": []}

        self.search_count += 1

        # Search for FDA approval information
        results = self.web_search.search(
            f"{drug_name} FDA approved indications mechanism of action",
            max_results=5
        )

        if not results:
            return {"approved_indications": []}

        # Use Claude to extract drug info
        prompt = f"""Extract drug information from these search results for {drug_name}.

Search Results:
{json.dumps(results, indent=2)[:8000]}

Return ONLY valid JSON:
{{
    "generic_name": "generic name or null",
    "mechanism": "mechanism of action or null",
    "target": "molecular target or null",
    "approved_indications": ["indication 1", "indication 2", ...]
}}

Be comprehensive with indications. Return ONLY the JSON, nothing else."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = response.content[0].text.strip()
            content = self._clean_json_response(content)
            return json.loads(content)
        except Exception as e:
            logger.error(f"Error extracting drug info: {e}")
            return {"approved_indications": []}

    def _find_drugs_by_mechanism(self, mechanism: str, max_drugs: int = 10) -> List[str]:
        """Find drugs with a given mechanism."""
        drugs = []

        # Try database first
        if self.drug_db:
            try:
                cursor = self.drug_db.connection.cursor()
                cursor.execute("""
                    SELECT DISTINCT brand_name, generic_name
                    FROM drugs
                    WHERE mechanism_of_action ILIKE %s
                    AND approval_status = 'Approved'
                    LIMIT %s
                """, (f"%{mechanism}%", max_drugs))

                for row in cursor.fetchall():
                    drugs.append(row[0] or row[1])
                cursor.close()

                if drugs:
                    return drugs
            except Exception as e:
                logger.error(f"Database query error: {e}")

        # Fall back to web search
        if self.web_search:
            self.search_count += 1
            results = self.web_search.search(
                f"{mechanism} approved drugs FDA list",
                max_results=10
            )

            if results:
                prompt = f"""Extract FDA-approved drug names with this mechanism: {mechanism}

Search Results:
{json.dumps(results, indent=2)[:6000]}

Return ONLY a JSON array of generic drug names:
["drug1", "drug2", ...]

Return ONLY the JSON array, nothing else."""

                try:
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=1000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    self._track_tokens(response.usage)

                    content = self._clean_json_response(response.content[0].text.strip())
                    drugs = json.loads(content)[:max_drugs]
                except Exception as e:
                    logger.error(f"Error extracting drugs: {e}")

        return drugs

    # =========================================================================
    # CASE SERIES SEARCH
    # =========================================================================

    def _search_case_series(
        self,
        drug_name: str,
        exclude_indications: List[str],
        max_papers: int = 200,  # Higher default, but LLM filtering will reduce
        include_web_search: bool = True,
        use_llm_filtering: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search for case series and case reports.

        Two-stage approach:
        1. Broad PubMed search - get ALL potentially relevant papers
        2. LLM-based filtering - Claude evaluates each abstract for clinical relevance

        Combines PubMed (peer-reviewed) and Tavily (grey literature) searches.
        """
        papers = []
        seen_ids = set()

        # Exclusion terms for PubMed - filter out obvious non-case-reports at query level
        exclusion_terms = 'NOT ("Review"[Publication Type] OR "Systematic Review"[Publication Type] OR "Meta-Analysis"[Publication Type] OR "Guideline"[Publication Type])'

        # PubMed search strategies - BROAD search to get all relevant papers
        pubmed_queries = [
            f'"{drug_name}"[Title/Abstract] AND ("case report"[Publication Type] OR "case series"[Title/Abstract] OR "case study"[Title/Abstract]) {exclusion_terms}',
            f'"{drug_name}"[Title/Abstract] AND ("off-label"[Title/Abstract] OR "off label"[Title/Abstract]) {exclusion_terms}',
            f'"{drug_name}"[Title/Abstract] AND ("expanded access"[Title/Abstract] OR "compassionate use"[Title/Abstract]) {exclusion_terms}',
            f'"{drug_name}"[Title/Abstract] AND "repurpos"[Title/Abstract] {exclusion_terms}',
            f'"{drug_name}"[Title/Abstract] AND ("efficacy"[Title/Abstract] OR "successful treatment"[Title/Abstract]) {exclusion_terms}',
        ]

        # Get ALL papers from each query (up to max_papers total)
        papers_per_query = max(50, max_papers // len(pubmed_queries))

        for query in pubmed_queries:
            try:
                logger.info(f"PubMed search: {query[:80]}...")
                pmids = self.pubmed.search(query, max_results=papers_per_query)
                self.search_count += 1

                if pmids:
                    new_pmids = [p for p in pmids if p not in seen_ids]
                    seen_ids.update(new_pmids)

                    if new_pmids:
                        abstracts = self.pubmed.fetch_abstracts(new_pmids)
                        for paper in abstracts:
                            paper['source'] = 'PubMed'
                            paper['search_query'] = query
                            papers.append(paper)
                        logger.info(f"  Found {len(new_pmids)} new papers")

                time.sleep(0.3)  # Rate limiting

            except Exception as e:
                logger.error(f"PubMed search error: {e}")

        # Web search for grey literature
        if include_web_search and self.web_search:
            web_queries = [
                f"{drug_name} case report",
                f"{drug_name} case series",
                f"{drug_name} off-label use efficacy",
            ]

            for query in web_queries:
                try:
                    logger.info(f"Web search: {query}")
                    results = self.web_search.search(query, max_results=10)
                    self.search_count += 1

                    for result in results:
                        title = result.get('title', '')
                        url = result.get('url', '')
                        if url not in seen_ids:
                            seen_ids.add(url)
                            papers.append({
                                'title': title,
                                'abstract': result.get('content', ''),
                                'url': url,
                                'source': 'Web Search',
                                'search_query': query
                            })

                    time.sleep(0.3)

                except Exception as e:
                    logger.error(f"Web search error: {e}")

        logger.info(f"Total papers from search: {len(papers)}")

        # Stage 2: LLM-based relevance filtering
        if use_llm_filtering and papers:
            logger.info(f"Filtering {len(papers)} papers with LLM for clinical relevance...")
            papers = self._filter_papers_with_llm(papers, drug_name, exclude_indications)
            logger.info(f"After LLM filtering: {len(papers)} relevant papers")

        # Check PMC availability for full text access
        pmids_to_check = [p.get('pmid') for p in papers if p.get('pmid')]
        if pmids_to_check:
            try:
                pmc_map = self.pubmed.check_pmc_availability(pmids_to_check)
                for paper in papers:
                    pmid = paper.get('pmid')
                    if pmid and pmid in pmc_map:
                        paper['pmcid'] = pmc_map[pmid]
                        paper['has_full_text'] = pmc_map[pmid] is not None
            except Exception as e:
                logger.warning(f"Could not check PMC availability: {e}")

        return papers

    def _filter_papers_with_llm(
        self,
        papers: List[Dict[str, Any]],
        drug_name: str,
        exclude_indications: List[str]
    ) -> List[Dict[str, Any]]:
        """
        Use Claude to evaluate paper relevance based on abstract.

        Filters for papers that contain:
        - Original clinical data (case reports, case series, cohorts)
        - Patient outcomes/efficacy data
        - Off-label or novel indication use

        Excludes:
        - Reviews, guidelines, consensus statements
        - Basic science / mechanistic studies without patients
        - PK/PD studies without efficacy outcomes
        - Approved indication studies
        """
        if not papers:
            return []

        # Build exclusion list for prompt
        exclude_str = ", ".join(exclude_indications) if exclude_indications else "None specified"

        # Process in batches to reduce API calls
        batch_size = 10
        filtered_papers = []

        for i in range(0, len(papers), batch_size):
            batch = papers[i:i + batch_size]

            # Build batch prompt
            papers_text = ""
            for idx, paper in enumerate(batch, 1):
                title = paper.get('title') or 'No title'
                abstract = paper.get('abstract') or 'No abstract available'
                abstract = abstract[:1500]  # Limit abstract length
                papers_text += f"\n---PAPER {idx}---\nTitle: {title}\nAbstract: {abstract}\n"

            prompt = f"""Evaluate these papers for relevance to off-label drug repurposing research for {drug_name}.

APPROVED INDICATIONS TO EXCLUDE: {exclude_str}

For each paper, determine if it contains ORIGINAL CLINICAL DATA that would be useful for evaluating off-label efficacy.

INCLUDE papers that have:
- Case reports or case series with patient outcomes
- Retrospective or prospective studies with efficacy data
- Compassionate use / expanded access reports
- Real-world evidence with response rates

EXCLUDE papers that are:
- Reviews, guidelines, consensus statements, position papers
- Basic science / mechanistic studies without patients
- Pharmacokinetics/pharmacodynamics studies without efficacy
- Drug monitoring / analytical method papers
- Studies ONLY about approved indications listed above
- Safety-only studies without efficacy outcomes
- Clinical trial protocols (not results)

{papers_text}

Return ONLY a JSON object with this exact format:
{{
    "evaluations": [
        {{"paper_index": 1, "include": true, "reason": "Case series with 15 patients showing efficacy in vitiligo", "disease": "vitiligo"}},
        {{"paper_index": 2, "include": false, "reason": "Review article, no original patient data", "disease": null}},
        ...
    ]
}}

Evaluate ALL {len(batch)} papers. Return ONLY the JSON, no other text."""

            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}]
                )

                # Track tokens
                self.total_input_tokens += response.usage.input_tokens
                self.total_output_tokens += response.usage.output_tokens

                # Parse response
                result_text = response.content[0].text.strip()

                # Extract JSON
                if '```json' in result_text:
                    result_text = result_text.split('```json')[1].split('```')[0]
                elif '```' in result_text:
                    result_text = result_text.split('```')[1].split('```')[0]

                result = json.loads(result_text)
                evaluations = result.get('evaluations', [])

                # Filter papers based on evaluation
                for eval_item in evaluations:
                    paper_idx = eval_item.get('paper_index', 0) - 1
                    if 0 <= paper_idx < len(batch) and eval_item.get('include', False):
                        paper = batch[paper_idx]
                        paper['llm_relevance_reason'] = eval_item.get('reason', '')
                        paper['extracted_disease'] = eval_item.get('disease')
                        filtered_papers.append(paper)

                logger.info(f"  Batch {i//batch_size + 1}: {len([e for e in evaluations if e.get('include')])} of {len(batch)} papers relevant")

            except Exception as e:
                logger.error(f"LLM filtering error for batch {i//batch_size + 1}: {e}")
                # On error, include all papers from batch (fail-open)
                filtered_papers.extend(batch)

            time.sleep(0.5)  # Rate limiting between batches

        return filtered_papers

    def _is_case_report_title(self, title: str, approved_indications: List[str] = None) -> bool:
        """
        Filter paper titles to identify actual case reports/series vs reviews/guidelines.

        Returns True if the paper appears to be an original case report/series.
        Returns False if it appears to be a review, guideline, or non-case-report paper.

        This function is STRICT - papers must have at least one include term
        to be included, unless they're from a case report search specifically.
        """
        title_lower = title.lower()

        # Exclude terms - papers with these in the title are likely NOT case reports
        exclude_terms = [
            # Reviews and meta-analyses
            'systematic review', 'meta-analysis', 'meta analysis',
            'narrative review', 'literature review', 'review of',
            'scoping review', 'umbrella review',
            # Guidelines and consensus
            'guideline', 'consensus', 'recommendation',
            'expert opinion', 'position statement', 'position paper',
            'expert statement',
            # Overviews and summaries
            'overview of', 'update on', 'advances in',
            'future directions', 'current landscape', 'therapeutic landscape',
            'state of the art', 'state-of-the-art',
            # Basic science / mechanism papers
            'mechanisms of', 'pathophysiology', 'pathogenesis',
            'molecular basis', 'signaling pathway',
            # PK/PD and methods papers
            'pharmacokinetics', 'pharmacodynamics', 'pk/pd',
            'drug monitoring', 'therapeutic drug monitoring',
            'lc-ms', 'hplc', 'assay', 'bioanalytical',
            'dosing of', 'dose-finding', 'dose finding',
            # Clinical trial design (not results)
            'clinical trials approved', 'trial design', 'study protocol',
            'proposed dosing', 'dosing recommendation',
            # Reference materials
            'statpearls', 'ncbi bookshelf', 'medscape', 'uptodate',
            'drug monograph', 'prescribing information',
            # Safety/risk only papers (no efficacy)
            'risk of major cardiovascular', 'black box warning',
            'safety warning', 'fda warning',
            # Other non-case-reports
            'fill the unmet medical need', 'main results',
            'artificial intelligence-predicted', 'ai-predicted',
            'cost-effectiveness', 'economic analysis',
            'registry data', 'claims database', 'insurance claims'
        ]

        # If title contains exclude terms, filter it out
        for term in exclude_terms:
            if term in title_lower:
                logger.debug(f"Filtering out (exclude term '{term}'): {title[:60]}")
                return False

        # Exclude papers about approved indications (we want off-label uses)
        if approved_indications:
            for indication in approved_indications:
                indication_lower = indication.lower()
                # Check for exact match or key words from the indication
                if indication_lower in title_lower:
                    logger.debug(f"Filtering out (approved indication '{indication}'): {title[:60]}")
                    return False
                # Check common abbreviations/variants
                indication_keywords = indication_lower.split()
                # Only filter if major keyword found (e.g., "covid-19" or "rheumatoid")
                for kw in indication_keywords:
                    if len(kw) > 5 and kw in title_lower:
                        # Don't filter out if also has "off-label" or "repurpos"
                        if 'off-label' not in title_lower and 'off label' not in title_lower and 'repurpos' not in title_lower:
                            logger.debug(f"Filtering out (approved indication keyword '{kw}'): {title[:60]}")
                            return False

        # Include terms - papers with these are likely case reports
        include_terms = [
            'case report', 'case series', 'case study', 'cases of',
            'retrospective', 'prospective',
            'off-label', 'off label', 'compassionate use',
            'expanded access', 'successful treatment',
            'treated with', 'treatment of', 'efficacy of',
            'effectiveness of', 'response to', 'experience with',
            'clinical experience', 'real-world', 'real world',
            'single-center', 'single center', 'multicenter',
            'patient with', 'patients with'
        ]

        # STRICT: Only include papers that have at least one include term
        for term in include_terms:
            if term in title_lower:
                return True

        # If no include terms found, reject the paper
        logger.debug(f"Filtering out (no include terms): {title[:60]}")
        return False

    # =========================================================================
    # PAPER GROUPING
    # =========================================================================

    def group_papers_by_disease(
        self,
        papers: List[Dict[str, Any]],
        drug_name: str,
        drug_info: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group papers by disease/indication using Claude to extract the disease from each paper.

        For drug-only input: Returns {disease: [papers]}

        Args:
            papers: List of paper dictionaries
            drug_name: Name of the drug being analyzed
            drug_info: Drug information dict with approved indications

        Returns:
            Dict mapping disease names to lists of papers
        """
        logger.info(f"Grouping {len(papers)} papers by disease for {drug_name}")

        grouped = defaultdict(list)
        approved_indications = set(ind.lower() for ind in drug_info.get('approved_indications', []))

        for paper in papers:
            try:
                disease = self._extract_disease_from_paper(paper, drug_name, drug_info)

                if disease:
                    # Skip if it's an approved indication
                    if disease.lower() in approved_indications:
                        logger.debug(f"Skipping approved indication: {disease}")
                        continue

                    # Normalize disease name
                    disease = self._normalize_disease_name(disease)
                    paper['extracted_disease'] = disease
                    grouped[disease].append(paper)
                else:
                    grouped['Unknown/Unclassified'].append(paper)

            except Exception as e:
                logger.warning(f"Error extracting disease from paper: {e}")
                grouped['Unknown/Unclassified'].append(paper)

        # Convert to regular dict and sort by paper count
        result = dict(sorted(grouped.items(), key=lambda x: len(x[1]), reverse=True))

        logger.info(f"Grouped papers into {len(result)} disease categories")
        for disease, disease_papers in result.items():
            logger.info(f"  {disease}: {len(disease_papers)} papers")

        return result

    def group_papers_by_disease_and_drug(
        self,
        papers_by_drug: Dict[str, List[Dict[str, Any]]],
        drug_infos: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Group papers by disease first, then by drug within each disease.

        For mechanism-first input: Returns {disease: {drug: [papers]}}

        Args:
            papers_by_drug: Dict mapping drug names to their papers
            drug_infos: Dict mapping drug names to their info dicts

        Returns:
            Dict mapping disease names to dicts mapping drug names to papers
        """
        logger.info(f"Grouping papers by disease → drug for {len(papers_by_drug)} drugs")

        # First, extract disease from each paper and tag with drug
        disease_drug_papers = defaultdict(lambda: defaultdict(list))

        for drug_name, papers in papers_by_drug.items():
            drug_info = drug_infos.get(drug_name, {})
            approved_indications = set(ind.lower() for ind in drug_info.get('approved_indications', []))

            for paper in papers:
                try:
                    disease = self._extract_disease_from_paper(paper, drug_name, drug_info)

                    if disease:
                        # Skip if approved indication for this drug
                        if disease.lower() in approved_indications:
                            continue

                        disease = self._normalize_disease_name(disease)
                        paper['extracted_disease'] = disease
                        paper['drug_name'] = drug_name
                        disease_drug_papers[disease][drug_name].append(paper)
                    else:
                        disease_drug_papers['Unknown/Unclassified'][drug_name].append(paper)

                except Exception as e:
                    logger.warning(f"Error extracting disease: {e}")
                    disease_drug_papers['Unknown/Unclassified'][drug_name].append(paper)

        # Convert to regular dicts and sort
        result = {}
        for disease in sorted(disease_drug_papers.keys(),
                             key=lambda d: sum(len(papers) for papers in disease_drug_papers[d].values()),
                             reverse=True):
            result[disease] = dict(disease_drug_papers[disease])

        logger.info(f"Grouped into {len(result)} disease categories across {len(papers_by_drug)} drugs")
        return result

    def _extract_disease_from_paper(
        self,
        paper: Dict[str, Any],
        drug_name: str,
        drug_info: Dict[str, Any]
    ) -> Optional[str]:
        """
        Extract the disease/indication being treated from a paper using Claude.

        Args:
            paper: Paper dictionary with title and abstract
            drug_name: Name of the drug
            drug_info: Drug information dict

        Returns:
            Disease name or None if cannot be determined
        """
        # Check if already extracted
        if paper.get('extracted_disease'):
            return paper['extracted_disease']

        title = paper.get('title', '')
        abstract = paper.get('abstract', paper.get('content', ''))[:2000]

        if not title and not abstract:
            return None

        approved_indications = drug_info.get('approved_indications', [])
        approved_str = ", ".join(approved_indications) if approved_indications else "Unknown"

        prompt = f"""Extract the disease/indication being treated in this paper.

Drug: {drug_name}
Approved Indications (exclude these): {approved_str}

Title: {title}
Abstract: {abstract}

Return ONLY the disease/indication name in a simple format (e.g., "vitiligo", "alopecia areata", "chronic graft-versus-host disease").
If multiple diseases are mentioned, return the PRIMARY one being treated.
If this is about an APPROVED indication, return "APPROVED_INDICATION".
If you cannot determine the disease, return "UNKNOWN".

Disease:"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            disease = response.content[0].text.strip()

            # Clean up response
            disease = disease.replace('"', '').replace("'", '').strip()

            if disease.upper() in ['APPROVED_INDICATION', 'UNKNOWN', 'N/A', 'NONE']:
                return None

            return disease

        except Exception as e:
            logger.error(f"Error extracting disease: {e}")
            return None

    def _normalize_disease_name(self, disease: str) -> str:
        """
        Normalize disease names for consistent grouping.

        Args:
            disease: Raw disease name

        Returns:
            Normalized disease name
        """
        if not disease:
            return "Unknown"

        # Common normalizations
        normalizations = {
            'aa': 'Alopecia Areata',
            'alopecia areata': 'Alopecia Areata',
            'vitiligo': 'Vitiligo',
            'ad': 'Atopic Dermatitis',
            'atopic dermatitis': 'Atopic Dermatitis',
            'psoriasis': 'Psoriasis',
            'ra': 'Rheumatoid Arthritis',
            'rheumatoid arthritis': 'Rheumatoid Arthritis',
            'sle': 'Systemic Lupus Erythematosus',
            'lupus': 'Systemic Lupus Erythematosus',
            'systemic lupus erythematosus': 'Systemic Lupus Erythematosus',
            'covid': 'COVID-19',
            'covid-19': 'COVID-19',
            'coronavirus': 'COVID-19',
            'gvhd': 'Graft-Versus-Host Disease',
            'graft versus host disease': 'Graft-Versus-Host Disease',
            'graft-versus-host disease': 'Graft-Versus-Host Disease',
            'chronic gvhd': 'Chronic Graft-Versus-Host Disease',
            'ibd': 'Inflammatory Bowel Disease',
            'ulcerative colitis': 'Ulcerative Colitis',
            "crohn's disease": "Crohn's Disease",
            'crohn disease': "Crohn's Disease",
            'lichen planus': 'Lichen Planus',
            'dermatomyositis': 'Dermatomyositis',
            'sarcoidosis': 'Sarcoidosis',
            'hidradenitis suppurativa': 'Hidradenitis Suppurativa',
            'hs': 'Hidradenitis Suppurativa',
        }

        disease_lower = disease.lower().strip()

        # Check direct matches
        if disease_lower in normalizations:
            return normalizations[disease_lower]

        # Check partial matches
        for key, normalized in normalizations.items():
            if key in disease_lower:
                return normalized

        # Title case for consistency
        return disease.strip().title()

    # =========================================================================
    # DATA EXTRACTION
    # =========================================================================

    def _extract_case_series_data(
        self,
        drug_name: str,
        drug_info: Dict[str, Any],
        paper: Dict[str, Any],
        fetch_full_text: bool = True
    ) -> Optional[CaseSeriesExtraction]:
        """Extract structured data from a case series/report using Claude.

        Args:
            drug_name: Name of the drug
            drug_info: Drug information dict
            paper: Paper dict with title, abstract, pmid, pmcid, etc.
            fetch_full_text: If True, attempt to fetch full text from PMC for better extraction
        """
        title = paper.get('title', 'Unknown')
        abstract = paper.get('abstract', paper.get('content', ''))

        # Try to fetch full text from PMC if available and enabled
        full_text_content = None
        if fetch_full_text and paper.get('pmcid'):
            pmcid = paper.get('pmcid')
            logger.info(f"Fetching full text from PMC for {pmcid}...")
            try:
                fulltext_xml = self.pubmed.fetch_pmc_fulltext(pmcid)
                if fulltext_xml:
                    parsed = self.pubmed._parse_pmc_fulltext(
                        fulltext_xml,
                        paper.get('pmid', ''),
                        pmcid
                    )
                    if parsed and parsed.get('content'):
                        full_text_content = parsed.get('content')
                        # Limit to 15000 chars to stay within token limits
                        if len(full_text_content) > 15000:
                            full_text_content = full_text_content[:15000] + "\n\n[... content truncated ...]"
                        logger.info(f"Successfully fetched {len(full_text_content)} chars of full text")
            except Exception as e:
                logger.warning(f"Failed to fetch PMC full text: {e}")

        # Use full text if available, otherwise abstract
        content_for_extraction = full_text_content or abstract

        if not content_for_extraction or len(content_for_extraction) < 50:
            logger.warning(f"Skipping paper with insufficient content: {title[:50]}")
            return None

        # Update paper dict with full text for prompt generation
        paper_with_content = paper.copy()
        if full_text_content:
            paper_with_content['full_text'] = full_text_content
            paper_with_content['has_full_text_content'] = True

        prompt = self._get_extraction_prompt(drug_name, drug_info, paper_with_content)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = response.content[0].text.strip()
            content = self._clean_json_response(content)

            data = json.loads(content)

            # Build extraction object
            extraction = self._build_extraction_from_data(data, paper, drug_name, drug_info)
            return extraction

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return None
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return None
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return None

    def _get_extraction_prompt(
        self,
        drug_name: str,
        drug_info: Dict[str, Any],
        paper: Dict[str, Any]
    ) -> str:
        """Build extraction prompt for Claude."""

        approved_indications = drug_info.get('approved_indications', [])
        approved_str = ", ".join(approved_indications) if approved_indications else "Unknown"

        # Use full text if available, otherwise abstract
        if paper.get('has_full_text_content') and paper.get('full_text'):
            content = paper.get('full_text')
            content_label = "FULL TEXT"
        else:
            content = paper.get('abstract', paper.get('content', 'N/A'))
            content = (content or 'N/A')[:4000]  # Limit abstract to 4000 chars
            content_label = "Abstract"

        return f"""You are analyzing a medical case report/series for drug repurposing opportunities.

Drug: {drug_name}
Mechanism: {drug_info.get('mechanism', 'Unknown')}
Approved Indications: {approved_str}

Paper:
Title: {paper.get('title', 'N/A')}
{content_label}: {content}

Extract structured data about this case report/series. Focus on:
1. What disease/condition was treated (OFF-LABEL use)?
2. How many patients were treated?
3. What were the efficacy outcomes?
4. What were the safety outcomes?

Return ONLY valid JSON in this format:
{{
    "disease": "specific disease name treated",
    "is_relevant": true or false (is this actually about off-label use of {drug_name}?),
    "evidence_level": "Case Report" or "Case Series" or "Retrospective Study",
    "n_patients": number,
    "patient_description": "brief description of patient characteristics",
    "prior_treatments_failed": ["treatment1", "treatment2"],
    "dose": "dose used",
    "route": "oral/IV/etc",
    "duration": "treatment duration",
    "primary_endpoint": "the main efficacy endpoint measured (e.g., 'CDASI score reduction', 'remission rate', 'CRP reduction')",
    "endpoint_result": "result on primary endpoint (e.g., '50% reduction in CDASI', 'complete remission in 3/5 patients')",
    "response_rate": "X/N (Y%)" or null,
    "responders_n": number or null,
    "responders_pct": percentage or null,
    "time_to_response": "time description" or null,
    "duration_of_response": "how long the response lasted" or null,
    "effect_size_description": "description of effect size",
    "efficacy_summary": "2-3 sentence efficacy summary",
    "adverse_events": ["AE1", "AE2"] or [],
    "serious_adverse_events": ["SAE1", "SAE2"] or [],
    "sae_count": number of patients with serious adverse events or null,
    "sae_percentage": percentage of patients with SAEs or null,
    "discontinuations_n": number of discontinuations or null,
    "discontinuation_reasons": ["reason1", "reason2"] or [],
    "safety_summary": "2-3 sentence safety summary",
    "outcome_result": "Success" or "Fail" or "Mixed",
    "efficacy_signal": "Strong" or "Moderate" or "Weak" or "None",
    "safety_profile": "Favorable" or "Acceptable" or "Concerning" or "Unknown",
    "follow_up_duration": "duration" or null,
    "key_findings": "1-2 sentence key findings",
    "year": publication year or null,
    "journal": "journal name" or null,
    "authors": "author list" or null
}}

CRITICAL:
- Set is_relevant=false if this is NOT about off-label use
- Set is_relevant=false if the disease is one of the approved indications
- Return ONLY the JSON, no other text"""

    def _build_extraction_from_data(
        self,
        data: Dict[str, Any],
        paper: Dict[str, Any],
        drug_name: str,
        drug_info: Dict[str, Any]
    ) -> Optional[CaseSeriesExtraction]:
        """Build CaseSeriesExtraction from extracted data."""

        # Skip irrelevant papers
        if not data.get('is_relevant', True):
            logger.info(f"Skipping irrelevant paper: {paper.get('title', 'Unknown')[:50]}")
            return None

        # Build source
        source = CaseSeriesSource(
            pmid=paper.get('pmid'),
            doi=paper.get('doi'),
            url=paper.get('url'),
            title=paper.get('title', 'Unknown'),
            authors=data.get('authors'),
            journal=data.get('journal'),
            year=data.get('year'),
            publication_venue="Peer-reviewed journal" if paper.get('source') == 'PubMed' else "Web source"
        )

        # Build patient population
        patient_pop = PatientPopulation(
            n_patients=data.get('n_patients', 1),
            description=data.get('patient_description'),
            prior_treatments_failed=data.get('prior_treatments_failed')
        )

        # Build treatment details
        treatment = TreatmentDetails(
            drug_name=drug_name,
            generic_name=drug_info.get('generic_name'),
            mechanism=drug_info.get('mechanism'),
            target=drug_info.get('target'),
            route_of_administration=data.get('route'),
            dose=data.get('dose'),
            duration=data.get('duration')
        )

        # Build efficacy outcome
        efficacy = EfficacyOutcome(
            response_rate=data.get('response_rate'),
            responders_n=data.get('responders_n'),
            responders_pct=data.get('responders_pct'),
            time_to_response=data.get('time_to_response'),
            duration_of_response=data.get('duration_of_response'),
            effect_size_description=data.get('effect_size_description'),
            primary_endpoint=data.get('primary_endpoint'),
            endpoint_result=data.get('endpoint_result'),
            efficacy_summary=data.get('efficacy_summary')
        )

        # Build safety outcome
        safety = SafetyOutcome(
            adverse_events=data.get('adverse_events', []),
            serious_adverse_events=data.get('serious_adverse_events', []),
            sae_count=data.get('sae_count'),
            sae_percentage=data.get('sae_percentage'),
            discontinuations_n=data.get('discontinuations_n'),
            discontinuation_reasons=data.get('discontinuation_reasons', []),
            safety_summary=data.get('safety_summary'),
            safety_profile=SafetyProfile(data.get('safety_profile', 'Unknown'))
        )

        # Map enums
        evidence_level = EvidenceLevel.CASE_REPORT
        if 'series' in data.get('evidence_level', '').lower():
            evidence_level = EvidenceLevel.CASE_SERIES
        elif 'retrospective' in data.get('evidence_level', '').lower():
            evidence_level = EvidenceLevel.RETROSPECTIVE_STUDY

        outcome_result = OutcomeResult.UNKNOWN
        if data.get('outcome_result'):
            try:
                outcome_result = OutcomeResult(data['outcome_result'])
            except ValueError:
                pass

        efficacy_signal = EfficacySignal.UNKNOWN
        if data.get('efficacy_signal'):
            try:
                efficacy_signal = EfficacySignal(data['efficacy_signal'])
            except ValueError:
                pass

        return CaseSeriesExtraction(
            source=source,
            disease=data.get('disease', 'Unknown'),
            is_off_label=True,
            evidence_level=evidence_level,
            patient_population=patient_pop,
            treatment=treatment,
            efficacy=efficacy,
            safety=safety,
            outcome_result=outcome_result,
            efficacy_signal=efficacy_signal,
            follow_up_duration=data.get('follow_up_duration'),
            key_findings=data.get('key_findings')
        )

    # =========================================================================
    # DISEASE STANDARDIZATION
    # =========================================================================

    def standardize_disease_names(
        self,
        opportunities: List[RepurposingOpportunity]
    ) -> List[RepurposingOpportunity]:
        """Standardize disease names across extractions using LLM.

        Groups similar/related diseases under canonical names to avoid
        duplicate market intelligence searches and improve reporting.
        """
        if not opportunities:
            return opportunities

        # Collect all unique disease names
        disease_names = list(set(opp.extraction.disease for opp in opportunities))

        if len(disease_names) <= 1:
            return opportunities

        prompt = f"""You are a medical terminology expert. Standardize these disease names by grouping similar/related conditions under canonical names.

Disease names found in papers:
{json.dumps(disease_names, indent=2)}

RULES:
1. Group diseases that are essentially the same condition with different descriptions
2. Group subtypes under their parent disease when appropriate
3. Keep distinct diseases separate
4. Use standard medical terminology (prefer MeSH/ICD-10 naming)
5. For autoinflammatory conditions, group CANDLE, SAVI, AGS, NNS under "Type I Interferonopathies"
6. Adult-onset Still's disease variants should all be "Adult-onset Still's Disease (AOSD)"
7. Keep specific diseases like "vitiligo", "atopic dermatitis", "lichen planus" as their own categories

Return ONLY valid JSON mapping original names to standardized names:
{{
    "original disease name 1": "Standardized Disease Name",
    "original disease name 2": "Standardized Disease Name",
    "vitiligo": "Vitiligo"
}}

Return ONLY the JSON mapping."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            disease_mapping = json.loads(content)

            # Apply mapping to opportunities
            for opp in opportunities:
                original = opp.extraction.disease
                if original in disease_mapping:
                    standardized = disease_mapping[original]
                    if standardized != original:
                        logger.info(f"Standardized disease: '{original}' -> '{standardized}'")
                        opp.extraction.disease_normalized = standardized
                        # Keep original in disease field for reference, use normalized for grouping

            return opportunities

        except Exception as e:
            logger.error(f"Error standardizing disease names: {e}")
            return opportunities

    # =========================================================================
    # MARKET INTELLIGENCE
    # =========================================================================

    def _enrich_with_market_data(
        self,
        opportunities: List[RepurposingOpportunity]
    ) -> List[RepurposingOpportunity]:
        """Enrich opportunities with market intelligence.

        Uses normalized disease name if available to avoid duplicate searches.
        """
        # Group by normalized disease name to avoid duplicate searches
        diseases_seen = set()
        disease_market_data = {}

        for opp in opportunities:
            # Use normalized name if available, otherwise original
            disease = opp.extraction.disease_normalized or opp.extraction.disease
            if disease not in diseases_seen:
                diseases_seen.add(disease)
                logger.info(f"Getting market data for: {disease}")
                market_data = self._get_market_intelligence(disease)
                disease_market_data[disease] = market_data

        # Assign market data to opportunities
        for opp in opportunities:
            disease = opp.extraction.disease_normalized or opp.extraction.disease
            if disease in disease_market_data:
                opp.market_intelligence = disease_market_data[disease]

        return opportunities

    def _get_market_intelligence(self, disease: str) -> MarketIntelligence:
        """Get market intelligence for a disease."""

        market_intel = MarketIntelligence(disease=disease)

        if not self.web_search:
            return market_intel

        # Get epidemiology data
        self.search_count += 1
        epi_results = self.web_search.search(
            f"{disease} prevalence United States epidemiology patients",
            max_results=5
        )

        if epi_results:
            epi_data = self._extract_epidemiology(disease, epi_results)
            market_intel.epidemiology = epi_data

        # Get FDA approved drugs specifically
        self.search_count += 1
        fda_results = self.web_search.search(
            f'"{disease}" FDA approved drugs treatments biologics site:fda.gov OR site:drugs.com OR site:medscape.com',
            max_results=5
        )

        # Get standard of care and pipeline
        self.search_count += 1
        soc_results = self.web_search.search(
            f"{disease} standard of care treatment guidelines clinical trials pipeline",
            max_results=5
        )

        # Combine results for better extraction
        all_treatment_results = (fda_results or []) + (soc_results or [])
        if all_treatment_results:
            soc_data = self._extract_standard_of_care(disease, all_treatment_results)
            market_intel.standard_of_care = soc_data

        return market_intel

    def _extract_epidemiology(self, disease: str, results: List[Dict]) -> EpidemiologyData:
        """Extract epidemiology data from search results."""
        # Include URLs in the search results for source citation
        results_with_urls = []
        for r in results:
            results_with_urls.append({
                'title': r.get('title'),
                'snippet': r.get('snippet'),
                'url': r.get('url')
            })

        prompt = f"""Extract epidemiology data for {disease} from these search results.

Search Results:
{json.dumps(results_with_urls, indent=2)[:5000]}

Return ONLY valid JSON:
{{
    "us_prevalence_estimate": "estimated US prevalence (e.g. '1 in 10,000' or '200,000 patients') or null",
    "us_incidence_estimate": "annual incidence estimate or null",
    "patient_population_size": integer estimate of US patient count or null (MUST be integer, not string),
    "prevalence_source": "name of source (e.g. 'NIH GARD', 'CDC', journal name) or null",
    "prevalence_source_url": "URL of the source or null",
    "trend": "increasing/stable/decreasing or null"
}}

IMPORTANT: patient_population_size must be a single integer, not a range or string.
Return ONLY the JSON."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            return EpidemiologyData(**data)
        except Exception as e:
            logger.error(f"Error extracting epidemiology: {e}")
            return EpidemiologyData()

    def _extract_standard_of_care(self, disease: str, results: List[Dict]) -> StandardOfCareData:
        """Extract standard of care from search results."""
        # Include URLs for source citation
        results_with_urls = []
        for r in results:
            results_with_urls.append({
                'title': r.get('title'),
                'snippet': r.get('snippet'),
                'url': r.get('url')
            })

        prompt = f"""Extract FDA-approved treatments and standard of care information for {disease}.

IMPORTANT: Count FDA-approved drugs accurately. Include:
- Drugs with SPECIFIC FDA approval for this disease
- Drugs approved for related/similar indications commonly used (e.g., biologics like Ilaris/canakinumab, Kineret/anakinra, Actemra/tocilizumab for autoinflammatory diseases)
- Both brand and generic names count as 1 drug

Search Results:
{json.dumps(results_with_urls, indent=2)[:6000]}

Return ONLY valid JSON:
{{
    "top_treatments": [
        {{"drug_name": "Brand Name (generic)", "drug_class": "class", "fda_approved": true/false, "efficacy_range": "60-70%", "notes": "FDA indication or off-label"}},
        {{"drug_name": "Drug2", "drug_class": "class", "fda_approved": true/false, "efficacy_range": "50-60%", "notes": "note"}}
    ],
    "approved_drug_names": ["list", "of", "FDA", "approved", "drug", "names"],
    "num_approved_drugs": integer count of FDA-approved drugs (count accurately from top_treatments where fda_approved=true),
    "num_pipeline_therapies": integer count of drugs in clinical trials,
    "pipeline_details": "brief description of key pipeline drugs and their phases or null",
    "treatment_paradigm": "brief description of treatment approach",
    "unmet_need": true or false,
    "unmet_need_description": "description of unmet need or null",
    "competitive_landscape": "2-sentence summary including approved drugs and unmet needs",
    "soc_source": "primary source name and URL for this information"
}}

CRITICAL: Be thorough in identifying FDA-approved drugs. Many rare diseases have approved biologics.
Return ONLY the JSON."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            # Build treatments
            treatments = []
            for t in data.get('top_treatments', []):
                treatments.append(StandardOfCareTreatment(
                    drug_name=t.get('drug_name', 'Unknown'),
                    drug_class=t.get('drug_class'),
                    efficacy_range=t.get('efficacy_range'),
                    notes=t.get('notes')
                ))

            return StandardOfCareData(
                top_treatments=treatments,
                approved_drug_names=data.get('approved_drug_names', []),
                num_approved_drugs=data.get('num_approved_drugs', 0),
                num_pipeline_therapies=data.get('num_pipeline_therapies', 0),
                pipeline_details=data.get('pipeline_details'),
                treatment_paradigm=data.get('treatment_paradigm'),
                unmet_need=data.get('unmet_need', False),
                unmet_need_description=data.get('unmet_need_description'),
                competitive_landscape=data.get('competitive_landscape'),
                soc_source=data.get('soc_source')
            )
        except Exception as e:
            logger.error(f"Error extracting SOC: {e}")
            return StandardOfCareData()

    # =========================================================================
    # SCORING
    # =========================================================================

    def _score_opportunities(
        self,
        opportunities: List[RepurposingOpportunity]
    ) -> List[RepurposingOpportunity]:
        """Score all opportunities."""
        for opp in opportunities:
            opp.scores = self._score_opportunity(opp)
        return opportunities

    def _score_opportunity(self, opp: RepurposingOpportunity) -> OpportunityScores:
        """
        Score a single repurposing opportunity.

        Weights: Clinical 50%, Evidence 25%, Market 25%
        Each dimension is the average of its component scores (all 1-10).
        """
        ext = opp.extraction

        # Clinical Signal Score (50% weight) - average of response rate and safety
        response_score = self._score_response_rate(ext)
        safety_score = self._score_safety_profile(ext)
        clinical_score = (response_score + safety_score) / 2

        # Evidence Quality Score (25% weight) - average of sample size, venue, followup
        sample_score = self._score_sample_size(ext)
        venue_score = self._score_publication_venue(ext)
        followup_score = self._score_followup_duration(ext)
        evidence_score = (sample_score + venue_score + followup_score) / 3

        # Market Opportunity Score (25% weight) - average of competitors, market size, unmet need
        competitors_score = self._score_competitors(opp)
        market_size_score = self._score_market_size(opp)
        unmet_need_score = self._score_unmet_need(opp)
        market_score = (competitors_score + market_size_score + unmet_need_score) / 3

        # Overall Priority (weighted average)
        # 50% clinical, 25% evidence, 25% market
        overall = (
            clinical_score * 0.50 +
            evidence_score * 0.25 +
            market_score * 0.25
        )

        return OpportunityScores(
            clinical_signal=round(clinical_score, 1),
            evidence_quality=round(evidence_score, 1),
            market_opportunity=round(market_score, 1),
            overall_priority=round(overall, 1),
            # Clinical breakdown
            response_rate_score=round(response_score, 1),
            safety_profile_score=round(safety_score, 1),
            clinical_breakdown={
                "response_rate": round(response_score, 1),
                "safety_profile": round(safety_score, 1)
            },
            # Evidence breakdown
            sample_size_score=round(sample_score, 1),
            publication_venue_score=round(venue_score, 1),
            followup_duration_score=round(followup_score, 1),
            evidence_breakdown={
                "sample_size": round(sample_score, 1),
                "publication_venue": round(venue_score, 1),
                "followup_duration": round(followup_score, 1)
            },
            # Market breakdown
            competitors_score=round(competitors_score, 1),
            market_size_score=round(market_size_score, 1),
            unmet_need_score=round(unmet_need_score, 1),
            market_breakdown={
                "competitors": round(competitors_score, 1),
                "market_size": round(market_size_score, 1),
                "unmet_need": round(unmet_need_score, 1)
            }
        )

    # -------------------------------------------------------------------------
    # Clinical Signal Component Scores
    # -------------------------------------------------------------------------

    def _score_response_rate(self, ext: CaseSeriesExtraction) -> float:
        """
        Score response rate (1-10).

        Based on % patients achieving primary outcome:
        >80%=10, 60-80%=8, 40-60%=6, 20-40%=4, <20%=2
        """
        if ext.efficacy.responders_pct is not None:
            pct = ext.efficacy.responders_pct
            if pct >= 80:
                return 10.0
            elif pct >= 60:
                return 8.0
            elif pct >= 40:
                return 6.0
            elif pct >= 20:
                return 4.0
            else:
                return 2.0

        # Fallback to efficacy signal if no percentage available
        if ext.efficacy_signal == EfficacySignal.STRONG:
            return 9.0
        elif ext.efficacy_signal == EfficacySignal.MODERATE:
            return 6.0
        elif ext.efficacy_signal == EfficacySignal.WEAK:
            return 3.0
        elif ext.efficacy_signal == EfficacySignal.NONE:
            return 1.0

        return 5.0  # Unknown

    def _score_safety_profile(self, ext: CaseSeriesExtraction) -> float:
        """
        Score safety profile based on SAE percentage (1-10).

        No SAEs=10, <5%=8, 5-10%=6, 10-20%=4, 20-50%=2, >50%=1
        Also factors in discontinuations due to AEs.
        """
        # Use SAE percentage if available
        if ext.safety.sae_percentage is not None:
            sae_pct = ext.safety.sae_percentage
            if sae_pct == 0:
                return 10.0
            elif sae_pct < 5:
                return 8.0
            elif sae_pct < 10:
                return 6.0
            elif sae_pct < 20:
                return 4.0
            elif sae_pct < 50:
                return 2.0
            else:
                return 1.0

        # Calculate from SAE count if available
        if ext.safety.sae_count is not None and ext.patient_population.n_patients > 0:
            sae_pct = (ext.safety.sae_count / ext.patient_population.n_patients) * 100
            if sae_pct == 0:
                return 10.0
            elif sae_pct < 5:
                return 8.0
            elif sae_pct < 10:
                return 6.0
            elif sae_pct < 20:
                return 4.0
            elif sae_pct < 50:
                return 2.0
            else:
                return 1.0

        # Fallback to safety profile enum
        if ext.safety.safety_profile == SafetyProfile.FAVORABLE:
            return 9.0
        elif ext.safety.safety_profile == SafetyProfile.ACCEPTABLE:
            return 7.0
        elif ext.safety.safety_profile == SafetyProfile.CONCERNING:
            return 3.0

        # Check for any SAEs mentioned
        if ext.safety.serious_adverse_events:
            n_saes = len(ext.safety.serious_adverse_events)
            if n_saes == 0:
                return 9.0
            elif n_saes <= 2:
                return 6.0
            else:
                return 4.0

        return 5.0  # Unknown

    # -------------------------------------------------------------------------
    # Evidence Quality Component Scores
    # -------------------------------------------------------------------------

    def _score_sample_size(self, ext: CaseSeriesExtraction) -> float:
        """
        Score sample size (1-10).

        N≥50=10, N=20-49=8, N=10-19=6, N=5-9=4, N=2-4=2, N=1=1
        """
        n = ext.patient_population.n_patients
        if n is None:
            return 3.0  # Unknown sample size
        if n >= 50:
            return 10.0
        elif n >= 20:
            return 8.0
        elif n >= 10:
            return 6.0
        elif n >= 5:
            return 4.0
        elif n >= 2:
            return 2.0
        else:
            return 1.0

    def _score_publication_venue(self, ext: CaseSeriesExtraction) -> float:
        """
        Score publication venue (1-10).

        Peer-reviewed journal=10, Preprint=6, Conference abstract=4, Other=2
        """
        venue = (ext.source.publication_venue or "").lower()

        if 'peer-reviewed' in venue or 'journal' in venue:
            return 10.0
        elif 'preprint' in venue:
            return 6.0
        elif 'conference' in venue or 'abstract' in venue:
            return 4.0
        elif venue and venue != 'unknown':
            return 2.0

        # Try to infer from journal name
        if ext.source.journal:
            # Most journals are peer-reviewed
            return 8.0

        return 5.0  # Unknown

    def _score_followup_duration(self, ext: CaseSeriesExtraction) -> float:
        """
        Score follow-up duration (1-10).

        >1 year=10, 6-12 months=7, 3-6 months=5, 1-3 months=3, <1 month=1
        """
        follow_up = (ext.follow_up_duration or "").lower()

        # Check for years
        if 'year' in follow_up:
            # Try to extract number
            match = re.search(r'(\d+)\s*year', follow_up)
            if match and int(match.group(1)) >= 1:
                return 10.0
            return 10.0

        # Check for months
        if 'month' in follow_up:
            match = re.search(r'(\d+)\s*month', follow_up)
            if match:
                months = int(match.group(1))
                if months >= 12:
                    return 10.0
                elif months >= 6:
                    return 7.0
                elif months >= 3:
                    return 5.0
                elif months >= 1:
                    return 3.0
            return 5.0  # "months" mentioned but unclear

        # Check for weeks
        if 'week' in follow_up:
            match = re.search(r'(\d+)\s*week', follow_up)
            if match:
                weeks = int(match.group(1))
                if weeks >= 4:
                    return 3.0
                else:
                    return 1.0
            return 2.0

        return 5.0  # Unknown

    # -------------------------------------------------------------------------
    # Market Opportunity Component Scores
    # -------------------------------------------------------------------------

    def _score_competitors(self, opp: RepurposingOpportunity) -> float:
        """
        Score based on number of competitors (1-10).

        No approved drugs=10, 1-2=7, 3-5=5, 6-10=3, >10=1
        """
        if not opp.market_intelligence:
            return 5.0

        mi = opp.market_intelligence
        num_drugs = mi.standard_of_care.num_approved_drugs

        if num_drugs == 0:
            return 10.0
        elif num_drugs <= 2:
            return 7.0
        elif num_drugs <= 5:
            return 5.0
        elif num_drugs <= 10:
            return 3.0
        else:
            return 1.0

    def _score_market_size(self, opp: RepurposingOpportunity) -> float:
        """
        Score market size (1-10).

        Market size = patient population × avg annual cost of top 3 branded drugs.
        If no approved drugs, use prevalence-based pricing:
        - Rare (<10K): ~$200K/year
        - Specialty (10K-100K): ~$75K/year
        - Standard (>100K): ~$20K/year

        Scores: >$10B=10, $5-10B=9, $1-5B=8, $500M-1B=7, $100-500M=6,
                $50-100M=5, $10-50M=4, <$10M=2
        """
        if not opp.market_intelligence:
            return 5.0

        mi = opp.market_intelligence
        pop = mi.epidemiology.patient_population_size or 0

        # Use pre-calculated market size if available
        if mi.market_size_usd:
            market_size = mi.market_size_usd
        elif mi.standard_of_care.avg_annual_cost_usd and pop > 0:
            market_size = pop * mi.standard_of_care.avg_annual_cost_usd
        elif pop > 0:
            # Estimate based on prevalence
            if pop < 10000:
                # Rare disease pricing
                annual_cost = 200000
            elif pop < 100000:
                # Specialty pricing
                annual_cost = 75000
            else:
                # Standard pricing
                annual_cost = 20000
            market_size = pop * annual_cost
        else:
            return 5.0  # Unknown

        # Score based on market size
        if market_size >= 10_000_000_000:  # $10B+
            return 10.0
        elif market_size >= 5_000_000_000:  # $5-10B
            return 9.0
        elif market_size >= 1_000_000_000:  # $1-5B
            return 8.0
        elif market_size >= 500_000_000:  # $500M-1B
            return 7.0
        elif market_size >= 100_000_000:  # $100-500M
            return 6.0
        elif market_size >= 50_000_000:  # $50-100M
            return 5.0
        elif market_size >= 10_000_000:  # $10-50M
            return 4.0
        else:  # <$10M
            return 2.0

    def _score_unmet_need(self, opp: RepurposingOpportunity) -> float:
        """
        Score unmet need (1-10).

        Compares efficacy signal from case series vs top 3 approved drugs.
        - Better efficacy than approved options = 10
        - Similar efficacy = 5
        - Worse efficacy = 2
        - No approved drugs for indication = 10
        """
        if not opp.market_intelligence:
            return 5.0

        mi = opp.market_intelligence
        ext = opp.extraction

        # If no approved drugs, unmet need is maximum
        if mi.standard_of_care.num_approved_drugs == 0:
            return 10.0

        # If unmet need is explicitly marked
        if mi.standard_of_care.unmet_need:
            return 10.0

        # Compare case series efficacy to SOC
        case_series_efficacy = ext.efficacy.responders_pct

        # Get average SOC efficacy
        soc_efficacies = []
        for treatment in mi.standard_of_care.top_treatments[:3]:
            if treatment.efficacy_pct:
                soc_efficacies.append(treatment.efficacy_pct)

        if case_series_efficacy and soc_efficacies:
            avg_soc = sum(soc_efficacies) / len(soc_efficacies)

            # Compare: significantly better (+10%) = 10, similar (±10%) = 5, worse = 2
            if case_series_efficacy > avg_soc + 10:
                return 10.0
            elif case_series_efficacy >= avg_soc - 10:
                return 5.0
            else:
                return 2.0

        # Fallback: use efficacy signal
        if ext.efficacy_signal == EfficacySignal.STRONG:
            return 8.0
        elif ext.efficacy_signal == EfficacySignal.MODERATE:
            return 5.0
        elif ext.efficacy_signal == EfficacySignal.WEAK:
            return 3.0

        return 5.0  # Unknown

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    def _track_tokens(self, usage) -> None:
        """Track token usage for cost estimation."""
        if hasattr(usage, 'input_tokens'):
            self.total_input_tokens += usage.input_tokens
        if hasattr(usage, 'output_tokens'):
            self.total_output_tokens += usage.output_tokens

    def _calculate_cost(self) -> float:
        """Calculate estimated cost in USD."""
        # Claude Sonnet pricing (approximate)
        input_cost = self.total_input_tokens * 0.003 / 1000
        output_cost = self.total_output_tokens * 0.015 / 1000
        return round(input_cost + output_cost, 4)

    def _clean_json_response(self, text: str) -> str:
        """Clean JSON response from Claude."""
        # Remove markdown code blocks
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'^```\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        return text.strip()

    # =========================================================================
    # EXPORT METHODS
    # =========================================================================

    def export_to_json(self, result: DrugAnalysisResult, filename: Optional[str] = None) -> str:
        """Export analysis result to JSON."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{result.drug_name.lower().replace(' ', '_')}_{timestamp}.json"

        filepath = self.output_dir / filename

        with open(filepath, 'w') as f:
            json.dump(result.model_dump(mode='json'), f, indent=2, default=str)

        logger.info(f"Exported to JSON: {filepath}")
        return str(filepath)

    def export_to_excel(self, result: DrugAnalysisResult, filename: Optional[str] = None) -> str:
        """Export analysis result to Excel with multiple sheets."""
        try:
            import pandas as pd
        except ImportError:
            logger.error("pandas required for Excel export. Install with: pip install pandas openpyxl")
            raise

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{result.drug_name.lower().replace(' ', '_')}_{timestamp}.xlsx"

        filepath = self.output_dir / filename

        # Calculate estimated cost from token usage
        input_cost = result.total_input_tokens * 0.003 / 1000  # $3/1M input tokens
        output_cost = result.total_output_tokens * 0.015 / 1000  # $15/1M output tokens
        estimated_cost = input_cost + output_cost

        with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
            # Summary sheet
            summary_data = {
                'Drug': [result.drug_name],
                'Generic Name': [result.generic_name],
                'Mechanism': [result.mechanism],
                'Approved Indications': [', '.join(result.approved_indications)],
                'Papers Screened': [result.papers_screened or len(result.opportunities)],
                'Opportunities Found': [len(result.opportunities)],
                'Analysis Date': [result.analysis_date.strftime("%Y-%m-%d %H:%M")],
                'Input Tokens': [result.total_input_tokens],
                'Output Tokens': [result.total_output_tokens],
                'Estimated Cost': [f"${estimated_cost:.2f}"]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)

            # Opportunities sheet - enhanced with detailed endpoints
            if result.opportunities:
                opp_data = []
                for opp in result.opportunities:
                    ext = opp.extraction
                    eff = ext.efficacy
                    saf = ext.safety

                    opp_data.append({
                        'Rank': opp.rank,
                        'Disease (Standardized)': ext.disease_normalized or ext.disease,
                        'Disease (Original)': ext.disease if ext.disease_normalized else None,
                        'Evidence Level': ext.evidence_level.value,
                        'N Patients': ext.patient_population.n_patients,
                        # Efficacy details
                        'Primary Endpoint': eff.primary_endpoint or 'Not specified',
                        'Endpoint Result': eff.endpoint_result or eff.response_rate,
                        'Response Rate': eff.response_rate,
                        'Responders (%)': eff.responders_pct,
                        'Time to Response': eff.time_to_response,
                        'Duration of Response': eff.duration_of_response,
                        'Efficacy Summary': eff.efficacy_summary,
                        # Safety details
                        'Safety Profile': saf.safety_profile.value,
                        'SAE Count': saf.sae_count,
                        'SAE (%)': saf.sae_percentage,
                        'Discontinuations': saf.discontinuations_n,
                        'Adverse Events': '; '.join(saf.adverse_events or [])[:200] if saf.adverse_events else None,
                        'Serious AEs': '; '.join(saf.serious_adverse_events or [])[:200] if saf.serious_adverse_events else None,
                        'Safety Summary': saf.safety_summary,
                        # Scores
                        'Clinical Score': opp.scores.clinical_signal if opp.scores else None,
                        'Evidence Score': opp.scores.evidence_quality if opp.scores else None,
                        'Market Score': opp.scores.market_opportunity if opp.scores else None,
                        'Overall Priority': opp.scores.overall_priority if opp.scores else None,
                        # Source
                        'Key Findings': ext.key_findings,
                        'Source': ext.source.title,
                        'PMID': ext.source.pmid,
                        'Year': ext.source.year
                    })
                pd.DataFrame(opp_data).to_excel(writer, sheet_name='Opportunities', index=False)

            # Market Intelligence sheet - enhanced with sources and pipeline
            market_data = []
            for opp in result.opportunities:
                if opp.market_intelligence:
                    mi = opp.market_intelligence
                    epi = mi.epidemiology
                    soc = mi.standard_of_care

                    market_data.append({
                        'Disease': mi.disease,
                        # Epidemiology
                        'US Prevalence': epi.us_prevalence_estimate,
                        'US Incidence': epi.us_incidence_estimate,
                        'Patient Population': epi.patient_population_size,
                        'Prevalence Trend': epi.trend,
                        'Epidemiology Source': epi.prevalence_source,
                        'Epidemiology Source URL': epi.prevalence_source_url,
                        # Competitive landscape - separate columns
                        'Approved Treatments (Count)': soc.num_approved_drugs,
                        'Approved Drug Names': ', '.join(soc.approved_drug_names) if soc.approved_drug_names else None,
                        'Pipeline Therapies (Count)': soc.num_pipeline_therapies,
                        'Pipeline Details': soc.pipeline_details,
                        'Treatment Paradigm': soc.treatment_paradigm,
                        'Top Treatments': ', '.join([t.drug_name for t in soc.top_treatments]) if soc.top_treatments else None,
                        # Unmet need
                        'Unmet Need': 'Yes' if soc.unmet_need else 'No',
                        'Unmet Need Description': soc.unmet_need_description,
                        # Market
                        'Avg Annual Cost (USD)': soc.avg_annual_cost_usd,
                        'Market Size Estimate': mi.market_size_estimate,
                        'Market Size (USD)': mi.market_size_usd,
                        'Market Growth Rate': mi.growth_rate,
                        'Competitive Landscape': soc.competitive_landscape,
                        'SOC Source': soc.soc_source
                    })
            if market_data:
                pd.DataFrame(market_data).to_excel(writer, sheet_name='Market Intelligence', index=False)

        logger.info(f"Exported to Excel: {filepath}")
        return str(filepath)

    # =========================================================================
    # GROUPING & ORGANIZATION
    # =========================================================================

    def group_papers_by_disease(
        self,
        papers: List[Dict[str, Any]],
        drug_name: str,
        drug_info: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group papers by the disease they address (for drug-only analysis).

        Uses Claude to identify the primary disease from each paper's title/abstract.
        Returns a dictionary: {disease_name: [paper1, paper2, ...]}
        """
        if not papers:
            return {}

        # Use Claude to classify papers by disease
        prompt = f"""Classify these papers by the primary disease/condition being studied for {drug_name}.

Papers:
"""
        for i, paper in enumerate(papers, 1):
            prompt += f"\n{i}. Title: {paper.get('title', 'Unknown')}"
            abstract = paper.get('abstract', '')[:300]
            if abstract:
                prompt += f"\n   Abstract: {abstract}..."

        prompt += """

Return ONLY valid JSON mapping paper number to disease:
{
    "classifications": [
        {"paper_num": 1, "disease": "exact disease name"},
        {"paper_num": 2, "disease": "exact disease name"},
        ...
    ]
}

Rules:
- Use standardized disease names (e.g., "Vitiligo" not "vitiligo", "Alopecia Areata" not "AA")
- If a paper covers multiple diseases, choose the PRIMARY one
- If disease is unclear, use "Unknown"
- Group similar conditions together (e.g., all types of eczema under "Atopic Dermatitis")"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            # Build grouped result
            grouped = {}
            classifications = data.get('classifications', [])

            for item in classifications:
                paper_num = item.get('paper_num', 0) - 1  # Convert to 0-indexed
                disease = item.get('disease', 'Unknown')

                if 0 <= paper_num < len(papers):
                    paper = papers[paper_num].copy()
                    paper['classified_disease'] = disease

                    if disease not in grouped:
                        grouped[disease] = []
                    grouped[disease].append(paper)

            # Add any unclassified papers
            classified_indices = {item.get('paper_num', 0) - 1 for item in classifications}
            for i, paper in enumerate(papers):
                if i not in classified_indices:
                    paper_copy = paper.copy()
                    paper_copy['classified_disease'] = 'Unknown'
                    if 'Unknown' not in grouped:
                        grouped['Unknown'] = []
                    grouped['Unknown'].append(paper_copy)

            logger.info(f"Grouped {len(papers)} papers into {len(grouped)} disease categories")
            return grouped

        except Exception as e:
            logger.error(f"Error grouping papers by disease: {e}")
            # Return ungrouped as fallback
            return {'All Papers': papers}

    def group_papers_by_disease_and_drug(
        self,
        papers: List[Dict[str, Any]],
        mechanism: str
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Group papers by disease first, then by drug within each disease (for mechanism analysis).

        Returns: {disease_name: {drug_name: [paper1, paper2, ...]}}
        """
        if not papers:
            return {}

        # Use Claude to classify papers by disease AND drug
        prompt = f"""Classify these papers by both the disease being studied AND the specific drug used.
These papers are about drugs with the mechanism: {mechanism}

Papers:
"""
        for i, paper in enumerate(papers, 1):
            prompt += f"\n{i}. Title: {paper.get('title', 'Unknown')}"
            abstract = paper.get('abstract', '')[:300]
            if abstract:
                prompt += f"\n   Abstract: {abstract}..."

        prompt += """

Return ONLY valid JSON mapping paper number to disease and drug:
{
    "classifications": [
        {"paper_num": 1, "disease": "exact disease name", "drug": "drug name"},
        {"paper_num": 2, "disease": "exact disease name", "drug": "drug name"},
        ...
    ]
}

Rules:
- Use standardized disease names (e.g., "Vitiligo", "Alopecia Areata", "Rheumatoid Arthritis")
- Use standardized drug names (generic name preferred, e.g., "baricitinib", "tofacitinib")
- If a paper covers multiple diseases, choose the PRIMARY one
- If disease or drug is unclear, use "Unknown"
"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            # Build hierarchical grouped result
            grouped = {}
            classifications = data.get('classifications', [])

            for item in classifications:
                paper_num = item.get('paper_num', 0) - 1
                disease = item.get('disease', 'Unknown')
                drug = item.get('drug', 'Unknown')

                if 0 <= paper_num < len(papers):
                    paper = papers[paper_num].copy()
                    paper['classified_disease'] = disease
                    paper['classified_drug'] = drug

                    if disease not in grouped:
                        grouped[disease] = {}
                    if drug not in grouped[disease]:
                        grouped[disease][drug] = []
                    grouped[disease][drug].append(paper)

            # Add any unclassified papers
            classified_indices = {item.get('paper_num', 0) - 1 for item in classifications}
            for i, paper in enumerate(papers):
                if i not in classified_indices:
                    paper_copy = paper.copy()
                    paper_copy['classified_disease'] = 'Unknown'
                    paper_copy['classified_drug'] = 'Unknown'
                    if 'Unknown' not in grouped:
                        grouped['Unknown'] = {}
                    if 'Unknown' not in grouped['Unknown']:
                        grouped['Unknown']['Unknown'] = []
                    grouped['Unknown']['Unknown'].append(paper_copy)

            # Count for logging
            total_diseases = len(grouped)
            total_drugs = sum(len(drugs) for drugs in grouped.values())
            logger.info(f"Grouped {len(papers)} papers into {total_diseases} diseases and {total_drugs} drug groups")
            return grouped

        except Exception as e:
            logger.error(f"Error grouping papers by disease and drug: {e}")
            # Return ungrouped as fallback
            return {'All Papers': {'Unknown': papers}}

    def close(self):
        """Clean up resources."""
        if self.drug_db:
            try:
                self.drug_db.close()
            except Exception:
                pass

