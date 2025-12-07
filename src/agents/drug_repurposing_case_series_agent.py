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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    PipelineTherapy,
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
from src.tools.semantic_scholar import SemanticScholarAPI
from src.tools.case_series_database import CaseSeriesDatabase

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
        case_series_database_url: Optional[str] = None,
        pubmed_email: str = "user@example.com",
        pubmed_api_key: Optional[str] = None,
        tavily_api_key: Optional[str] = None,
        semantic_scholar_api_key: Optional[str] = None,
        output_dir: str = "data/case_series",
        cache_max_age_days: int = 30
    ):
        """
        Initialize agent with all required tools.

        Args:
            anthropic_api_key: Anthropic API key for Claude
            database_url: PostgreSQL database URL (optional, for drug lookups)
            case_series_database_url: PostgreSQL URL for case series persistence/caching
            pubmed_email: Email for PubMed API
            pubmed_api_key: PubMed API key (optional, increases rate limits)
            tavily_api_key: Tavily API key for web search
            semantic_scholar_api_key: Semantic Scholar API key (optional, for higher rate limits)
            output_dir: Directory for output files
            cache_max_age_days: Days before cached market intelligence expires (default: 30)
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

        # Semantic Scholar API for semantic search and citation mining
        self.semantic_scholar = SemanticScholarAPI(api_key=semantic_scholar_api_key)
        logger.info("Semantic Scholar API initialized (citation mining enabled)")

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

        # Case Series Database for persistence and caching
        self.cs_db = None
        self.cache_max_age_days = cache_max_age_days
        cs_db_url = case_series_database_url or database_url
        if cs_db_url:
            try:
                self.cs_db = CaseSeriesDatabase(cs_db_url, cache_max_age_days=cache_max_age_days)
                if self.cs_db.is_available:
                    logger.info("Case series database connected (caching enabled)")
                else:
                    logger.warning("Case series database not available (caching disabled)")
                    self.cs_db = None
            except Exception as e:
                logger.warning(f"Could not initialize case series database: {e}")
                self.cs_db = None

        # Current run tracking
        self._current_run_id = None
        self._cache_stats = {
            'papers_from_cache': 0,
            'market_intel_from_cache': 0,
            'tokens_saved_by_cache': 0
        }

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

        # Reset cost and cache tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.search_count = 0
        self._cache_stats = {
            'papers_from_cache': 0,
            'market_intel_from_cache': 0,
            'tokens_saved_by_cache': 0
        }

        # Create database run for tracking
        run_params = {
            'max_papers': max_papers,
            'include_web_search': include_web_search,
            'enrich_market_data': enrich_market_data
        }
        if self.cs_db:
            self._current_run_id = self.cs_db.create_run(drug_name, run_params)
            logger.info(f"Created analysis run: {self._current_run_id}")

        try:
            # Step 1: Get drug information and approved indications
            drug_info = self._get_drug_info(drug_name)
            approved_indications = drug_info.get("approved_indications", [])
            logger.info(f"Found {len(approved_indications)} approved indications")

            # Save drug info to database
            if self.cs_db:
                self.cs_db.save_drug(
                    drug_name=drug_name,
                    generic_name=drug_info.get("generic_name"),
                    mechanism=drug_info.get("mechanism"),
                    target=drug_info.get("target"),
                    approved_indications=approved_indications,
                    data_sources=drug_info.get("data_sources", [])
                )

            # Step 2: Search for case series/reports
            papers = self._search_case_series(
                drug_name,
                approved_indications,
                max_papers=max_papers,
                include_web_search=include_web_search
            )
            logger.info(f"Found {len(papers)} potential case series/reports")

            # Update run stats
            if self.cs_db and self._current_run_id:
                self.cs_db.update_run_stats(self._current_run_id, papers_found=len(papers))

            # Step 3: Extract structured data from each paper
            opportunities = []
            extraction_ids = {}  # Map extraction to database ID
            for i, paper in enumerate(papers, 1):
                logger.info(f"Extracting data from paper {i}/{len(papers)}: {paper.get('title', 'Unknown')[:50]}...")
                try:
                    extraction = self._extract_case_series_data(drug_name, drug_info, paper)
                    if extraction:
                        opportunity = RepurposingOpportunity(extraction=extraction)
                        opportunities.append(opportunity)

                        # Save extraction to database
                        if self.cs_db and self._current_run_id:
                            ext_id = self.cs_db.save_extraction(
                                self._current_run_id, extraction, drug_name
                            )
                            if ext_id:
                                extraction_ids[id(opportunity)] = ext_id
                except Exception as e:
                    logger.error(f"Error extracting paper {i}: {e}")
                    continue

                # Rate limiting
                if i < len(papers):
                    time.sleep(0.5)

            logger.info(f"Successfully extracted {len(opportunities)} case series")

            # Update run stats
            if self.cs_db and self._current_run_id:
                self.cs_db.update_run_stats(self._current_run_id, papers_extracted=len(opportunities))

            # Step 4: Enrich with market intelligence
            if enrich_market_data and opportunities:
                opportunities = self._enrich_with_market_data(opportunities)

            # Step 5: Score and rank opportunities
            opportunities = self._score_opportunities(opportunities)
            opportunities.sort(key=lambda x: x.scores.overall_priority, reverse=True)

            # Assign ranks and save opportunities
            for i, opp in enumerate(opportunities, 1):
                opp.rank = i
                # Save opportunity to database
                if self.cs_db and self._current_run_id:
                    ext_id = extraction_ids.get(id(opp))
                    if ext_id:
                        self.cs_db.save_opportunity(
                            self._current_run_id, ext_id, opp, drug_name
                        )

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

            # Mark run as completed
            if self.cs_db and self._current_run_id:
                self.cs_db.update_run_stats(
                    self._current_run_id,
                    opportunities_found=len(opportunities),
                    total_input_tokens=self.total_input_tokens,
                    total_output_tokens=self.total_output_tokens,
                    estimated_cost_usd=estimated_cost,
                    papers_from_cache=self._cache_stats['papers_from_cache'],
                    market_intel_from_cache=self._cache_stats['market_intel_from_cache'],
                    tokens_saved_by_cache=self._cache_stats['tokens_saved_by_cache']
                )
                self.cs_db.update_run_status(self._current_run_id, 'completed')

            duration = (datetime.now() - start_time).total_seconds()
            cache_info = f" (cache: {self._cache_stats['papers_from_cache']} papers, {self._cache_stats['market_intel_from_cache']} market intel)"
            logger.info(f"Analysis complete in {duration:.1f}s. Found {len(opportunities)} opportunities. Cost: ${estimated_cost:.2f}{cache_info}")

            return result

        except Exception as e:
            # Mark run as failed
            if self.cs_db and self._current_run_id:
                self.cs_db.update_run_status(self._current_run_id, 'failed', str(e))
            raise

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
    # HISTORICAL RUNS / DATABASE METHODS
    # =========================================================================

    def get_historical_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of historical analysis runs.

        Args:
            limit: Maximum number of runs to return

        Returns:
            List of run summaries with drug_name, started_at, status, etc.
        """
        if not self.cs_db:
            logger.warning("Case series database not available - no historical runs")
            return []
        return self.cs_db.get_historical_runs(limit=limit)

    def load_historical_run(self, run_id: str) -> Optional[DrugAnalysisResult]:
        """Load a historical run as a DrugAnalysisResult object.

        Args:
            run_id: UUID of the run to load

        Returns:
            DrugAnalysisResult or None if not found
        """
        if not self.cs_db:
            logger.warning("Case series database not available")
            return None
        return self.cs_db.load_run_as_result(run_id)

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get full details of a specific run including extractions and opportunities.

        Args:
            run_id: UUID of the run

        Returns:
            Dict with run info, extractions, and opportunities
        """
        if not self.cs_db:
            logger.warning("Case series database not available")
            return None
        return self.cs_db.get_run_details(run_id)

    @property
    def database_available(self) -> bool:
        """Check if the case series database is available for persistence/caching."""
        return self.cs_db is not None and self.cs_db.is_available

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
        max_papers: int = 200,
        include_web_search: bool = True,
        include_semantic_scholar: bool = True,
        include_citation_mining: bool = True,
        use_llm_filtering: bool = True,
        parallel_search: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Comprehensive search for case series and case reports.

        Multi-layer search strategy (runs in parallel for speed):
        1. Enhanced PubMed search - clinical data indicators, not just "case report"
        2. Semantic Scholar search - semantic relevance ranking
        3. Citation snowballing - mine references from review articles
        4. Web search - grey literature
        5. LLM filtering - Claude validates clinical data presence

        This approach finds papers that describe patient outcomes even if they
        don't explicitly use "case report" terminology.

        Args:
            parallel_search: If True, run search layers concurrently (faster but uses more resources)
        """
        all_papers = []

        if parallel_search:
            # Run searches in parallel for speed optimization
            all_papers = self._search_parallel(
                drug_name,
                include_web_search,
                include_semantic_scholar,
                include_citation_mining
            )
        else:
            # Sequential search (original behavior)
            seen_ids = set()
            all_papers.extend(self._search_pubmed_enhanced(drug_name, seen_ids))

            if include_semantic_scholar:
                all_papers.extend(self._search_semantic_scholar(drug_name, seen_ids))

            if include_citation_mining:
                all_papers.extend(self._mine_review_citations(drug_name, seen_ids))

            if include_web_search and self.web_search:
                all_papers.extend(self._search_web(drug_name, seen_ids))

        # Deduplicate papers from parallel search
        papers = self._deduplicate_papers(all_papers)

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

    def _search_parallel(
        self,
        drug_name: str,
        include_web_search: bool,
        include_semantic_scholar: bool,
        include_citation_mining: bool
    ) -> List[Dict[str, Any]]:
        """
        Run all search layers in parallel for speed optimization.

        Returns combined results (deduplication done by caller).
        """
        all_papers = []
        search_tasks = []

        # Define search functions to run in parallel
        # Each returns (source_name, papers_list)
        def pubmed_search():
            seen = set()
            return ("PubMed", self._search_pubmed_enhanced(drug_name, seen))

        def semantic_search():
            seen = set()
            return ("Semantic Scholar", self._search_semantic_scholar(drug_name, seen))

        def citation_search():
            seen = set()
            return ("Citation Mining", self._mine_review_citations(drug_name, seen))

        def web_search():
            seen = set()
            return ("Web Search", self._search_web(drug_name, seen))

        # Build task list
        search_tasks.append(pubmed_search)

        if include_semantic_scholar:
            search_tasks.append(semantic_search)

        if include_citation_mining:
            search_tasks.append(citation_search)

        if include_web_search and self.web_search:
            search_tasks.append(web_search)

        # Run in parallel with ThreadPoolExecutor
        logger.info(f"Running {len(search_tasks)} search layers in parallel...")
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=len(search_tasks)) as executor:
            futures = {executor.submit(task): task.__name__ for task in search_tasks}

            for future in as_completed(futures):
                try:
                    source_name, papers = future.result()
                    logger.info(f"  {source_name}: {len(papers)} papers")
                    all_papers.extend(papers)
                except Exception as e:
                    task_name = futures[future]
                    logger.error(f"  {task_name} failed: {e}")

        elapsed = time.time() - start_time
        logger.info(f"Parallel search completed in {elapsed:.1f}s, {len(all_papers)} total papers (before dedup)")

        return all_papers

    def _deduplicate_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate papers based on PMID, DOI, or title similarity.

        Keeps the first occurrence (PubMed > Semantic Scholar > Citation Mining > Web).
        """
        seen_pmids = set()
        seen_dois = set()
        seen_titles = set()
        unique_papers = []

        for paper in papers:
            pmid = paper.get('pmid')
            doi = paper.get('doi')
            title = (paper.get('title') or '').lower().strip()

            # Check for duplicates
            is_duplicate = False

            if pmid and pmid in seen_pmids:
                is_duplicate = True
            elif doi and doi in seen_dois:
                is_duplicate = True
            elif title and len(title) > 20:
                # Fuzzy title match - normalize and check
                normalized_title = re.sub(r'[^\w\s]', '', title)[:100]
                if normalized_title in seen_titles:
                    is_duplicate = True

            if not is_duplicate:
                unique_papers.append(paper)
                if pmid:
                    seen_pmids.add(pmid)
                if doi:
                    seen_dois.add(doi)
                if title and len(title) > 20:
                    normalized_title = re.sub(r'[^\w\s]', '', title)[:100]
                    seen_titles.add(normalized_title)

        logger.info(f"Deduplication: {len(papers)} -> {len(unique_papers)} papers")
        return unique_papers

    def _search_pubmed_enhanced(
        self,
        drug_name: str,
        seen_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Enhanced PubMed search with precision-preserving query expansion.

        Uses clinical data indicators to find papers with patient outcomes
        even if they don't use "case report" terminology.
        """
        papers = []

        # Exclusion terms - filter out obvious non-clinical papers
        exclusion_terms = 'NOT ("Review"[Publication Type] OR "Systematic Review"[Publication Type] OR "Meta-Analysis"[Publication Type] OR "Guideline"[Publication Type] OR "Editorial"[Publication Type])'

        # Clinical data indicators - terms suggesting patient-level data
        clinical_indicators = '("patients treated" OR "treated with" OR "received treatment" OR "treatment response" OR "clinical response" OR "our experience" OR "retrospective" OR "case series" OR "case report")'

        # Publication types with clinical data
        clinical_pub_types = '("Case Reports"[Publication Type] OR "Clinical Study"[Publication Type] OR "Observational Study"[Publication Type])'

        # Build enhanced query set
        pubmed_queries = [
            # Original case report search (proven effective)
            f'"{drug_name}"[Title/Abstract] AND {clinical_pub_types} {exclusion_terms}',

            # Clinical indicator search (finds case series without "case" in title)
            f'"{drug_name}"[Title/Abstract] AND {clinical_indicators} {exclusion_terms}',

            # Off-label searches (keep these)
            f'"{drug_name}"[Title/Abstract] AND ("off-label" OR "off label") {exclusion_terms}',
            f'"{drug_name}"[Title/Abstract] AND ("expanded access" OR "compassionate use") {exclusion_terms}',
            f'"{drug_name}"[Title/Abstract] AND "repurpos"[Title/Abstract] {exclusion_terms}',

            # Pediatric/juvenile with clinical data (NEW - catches JDM)
            f'"{drug_name}"[Title/Abstract] AND (pediatric OR juvenile OR children) AND (treated OR response OR outcome OR patients) {exclusion_terms}',

            # Common autoimmune conditions with clinical data (NEW)
            f'"{drug_name}"[Title/Abstract] AND (dermatomyositis OR myositis OR lupus OR vasculitis) AND (patients OR treated OR response) {exclusion_terms}',

            # Retrospective/cohort studies (NEW - often contain case data)
            f'"{drug_name}"[Title/Abstract] AND (retrospective OR "cohort study" OR observational) AND (efficacy OR outcome OR response) {exclusion_terms}',
        ]

        papers_per_query = 40  # Get reasonable number per query

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
                            paper['search_query'] = query[:100]
                            papers.append(paper)
                        logger.info(f"  Found {len(new_pmids)} new papers")

                time.sleep(0.3)

            except Exception as e:
                logger.error(f"PubMed search error: {e}")

        logger.info(f"PubMed enhanced search: {len(papers)} total papers")
        return papers

    def _search_semantic_scholar(
        self,
        drug_name: str,
        seen_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Search Semantic Scholar for papers using semantic relevance ranking.

        Better at finding relevant papers that use different terminology.
        """
        papers = []

        # Semantic search queries (neural embedding based, not keyword)
        # 3 queries for balanced coverage and speed
        ss_queries = [
            f"{drug_name} case report case series treatment outcomes patients",
            f"{drug_name} off-label compassionate use clinical efficacy",
            f"{drug_name} refractory resistant disease treatment response",
        ]

        for query in ss_queries:
            try:
                logger.info(f"Semantic Scholar search: {query}")
                results = self.semantic_scholar.search_papers(
                    query,
                    limit=40,  # Get more per query since fewer queries
                    publication_types=["CaseReport", "JournalArticle"]
                )
                self.search_count += 1

                for paper in results:
                    # Get identifiers for deduplication
                    external_ids = paper.get("externalIds") or {}
                    pmid = external_ids.get("PubMed")
                    doi = external_ids.get("DOI")
                    s2_id = paper.get("paperId")

                    # Check if we've seen this paper
                    if pmid and pmid in seen_ids:
                        continue
                    if doi and doi in seen_ids:
                        continue
                    if s2_id and s2_id in seen_ids:
                        continue

                    # Mark as seen
                    if pmid:
                        seen_ids.add(pmid)
                    if doi:
                        seen_ids.add(doi)
                    if s2_id:
                        seen_ids.add(s2_id)

                    # Format for our pipeline
                    formatted = self.semantic_scholar.format_paper_for_case_series(paper)
                    formatted['search_query'] = query
                    papers.append(formatted)

            except Exception as e:
                logger.error(f"Semantic Scholar search error: {e}")

        logger.info(f"Semantic Scholar search: {len(papers)} papers")
        return papers

    def _mine_review_citations(
        self,
        drug_name: str,
        seen_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Citation snowballing strategy: find review articles and extract their references.

        Reviews aggregate all case studies in a field - mining their references
        gives comprehensive coverage even for papers that don't match our queries.
        """
        papers = []

        try:
            logger.info(f"Mining citations from review articles for {drug_name}...")

            # Get references from review articles (3 reviews x 50 refs for balanced coverage)
            review_refs = self.semantic_scholar.mine_review_references(
                drug_name,
                disease_area=None,  # Search broadly
                max_reviews=3,
                max_refs_per_review=50
            )
            self.search_count += 1

            for paper in review_refs:
                # Get identifiers for deduplication
                external_ids = paper.get("externalIds") or {}
                pmid = external_ids.get("PubMed")
                doi = external_ids.get("DOI")
                s2_id = paper.get("paperId")

                # Check if we've seen this paper
                if pmid and pmid in seen_ids:
                    continue
                if doi and doi in seen_ids:
                    continue
                if s2_id and s2_id in seen_ids:
                    continue

                # Mark as seen
                if pmid:
                    seen_ids.add(pmid)
                if doi:
                    seen_ids.add(doi)
                if s2_id:
                    seen_ids.add(s2_id)

                # Format for our pipeline
                formatted = self.semantic_scholar.format_paper_for_case_series(paper)
                formatted['source'] = 'Citation Mining'
                papers.append(formatted)

            logger.info(f"Citation mining: {len(papers)} papers from review references")

        except Exception as e:
            logger.error(f"Citation mining error: {e}")

        return papers

    def _search_web(
        self,
        drug_name: str,
        seen_ids: Set[str]
    ) -> List[Dict[str, Any]]:
        """
        Web search for grey literature and conference presentations.
        """
        papers = []

        web_queries = [
            f"{drug_name} case report",
            f"{drug_name} case series patient outcomes",
            f"{drug_name} off-label treatment efficacy",
        ]

        for query in web_queries:
            try:
                logger.info(f"Web search: {query}")
                results = self.web_search.search(query, max_results=10)
                self.search_count += 1

                for result in results:
                    title = result.get('title', '')
                    url = result.get('url', '')
                    if url and url not in seen_ids:
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

        logger.info(f"Web search: {len(papers)} papers")
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

STRICT REQUIREMENTS - To be INCLUDED, a paper MUST contain:
1. A specific number of patients treated (e.g., "n=5 patients", "15 patients received", "a 12-year-old girl")
2. Clinical outcome data (response rate, improvement, remission, disease activity scores)
3. Treatment details (drug name with dose or duration mentioned)

INCLUDE papers that have ALL of the above:
- Case reports or case series with patient outcomes
- Retrospective or prospective studies with efficacy data
- Cohort studies with treatment outcomes
- Compassionate use / expanded access reports with results
- Real-world evidence with response rates
- Studies labeled "experience with" or "treated with" that report outcomes

EXCLUDE papers that are:
- Reviews, guidelines, consensus statements, position papers (even if they cite patient data)
- Basic science / mechanistic studies without patients treated
- Pharmacokinetics/pharmacodynamics studies without clinical efficacy
- Drug monitoring / analytical method papers
- Studies ONLY about approved indications: {exclude_str}
- Safety-only studies without efficacy outcomes
- Clinical trial protocols (not results)
- Letters/editorials without original patient data
- In vitro or animal studies only

{papers_text}

Return ONLY a JSON object with this exact format:
{{
    "evaluations": [
        {{"paper_index": 1, "include": true, "reason": "Case series with 15 patients showing 80% response rate in dermatomyositis", "disease": "dermatomyositis", "patient_count": 15}},
        {{"paper_index": 2, "include": false, "reason": "Review article summarizing literature, no original patient data", "disease": null, "patient_count": null}},
        ...
    ]
}}

Evaluate ALL {len(batch)} papers. Be thorough but strict - only include papers with actual patient treatment data. Return ONLY the JSON, no other text."""

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
        pmid = paper.get('pmid', '')
        title = paper.get('title', 'Unknown')
        abstract = paper.get('abstract', paper.get('content', ''))

        # Check cache for existing extraction
        if self.cs_db and pmid:
            cached = self.cs_db.load_extraction(drug_name, pmid)
            if cached:
                logger.info(f"Using cached extraction for PMID {pmid}")
                self._cache_stats['papers_from_cache'] += 1
                # Estimate tokens saved (average extraction is ~2000 tokens)
                self._cache_stats['tokens_saved_by_cache'] += 2000
                return cached

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
        """Get comprehensive market intelligence for a disease."""
        from src.models.case_series_schemas import AttributedSource

        # Check cache for fresh market intelligence
        if self.cs_db:
            cached = self.cs_db.check_market_intel_fresh(disease)
            if cached:
                logger.info(f"Using cached market intelligence for: {disease}")
                self._cache_stats['market_intel_from_cache'] += 1
                # Estimate tokens saved (average market intel is ~3000 tokens)
                self._cache_stats['tokens_saved_by_cache'] += 3000
                return cached

        market_intel = MarketIntelligence(disease=disease)
        attributed_sources = []

        if not self.web_search:
            return market_intel

        # 1. Get epidemiology data
        self.search_count += 1
        epi_results = self.web_search.search(
            f"{disease} prevalence United States epidemiology patients",
            max_results=5
        )

        if epi_results:
            epi_data = self._extract_epidemiology(disease, epi_results)
            market_intel.epidemiology = epi_data
            # Track epidemiology sources
            for r in epi_results[:2]:  # Top 2 sources
                if r.get('url'):
                    attributed_sources.append(AttributedSource(
                        url=r.get('url'),
                        title=r.get('title', 'Unknown'),
                        attribution='Epidemiology'
                    ))

        # 2. Get FDA approved drugs specifically
        self.search_count += 1
        fda_results = self.web_search.search(
            f'"{disease}" FDA approved drugs treatments biologics site:fda.gov OR site:drugs.com OR site:medscape.com',
            max_results=5
        )

        # 3. Get standard of care
        self.search_count += 1
        soc_results = self.web_search.search(
            f"{disease} standard of care treatment guidelines first line second line therapy",
            max_results=5
        )

        # Combine results for SOC extraction
        all_treatment_results = (fda_results or []) + (soc_results or [])
        if all_treatment_results:
            soc_data = self._extract_standard_of_care(disease, all_treatment_results)
            market_intel.standard_of_care = soc_data
            # Track SOC sources (FDA approvals, treatment guidelines)
            for r in (fda_results or [])[:2]:
                if r.get('url'):
                    attributed_sources.append(AttributedSource(
                        url=r.get('url'),
                        title=r.get('title', 'Unknown'),
                        attribution='Approved Treatments'
                    ))
            for r in (soc_results or [])[:1]:
                if r.get('url'):
                    attributed_sources.append(AttributedSource(
                        url=r.get('url'),
                        title=r.get('title', 'Unknown'),
                        attribution='Treatment Paradigm'
                    ))

        # 4. Get dedicated pipeline data (ClinicalTrials.gov focused)
        self.search_count += 1
        pipeline_results = self.web_search.search(
            f'"{disease}" clinical trial Phase 2 OR Phase 3 site:clinicaltrials.gov OR site:biopharmcatalyst.com',
            max_results=5
        )

        if pipeline_results:
            pipeline_data = self._extract_pipeline_data(disease, pipeline_results)
            # Merge pipeline data into SOC
            market_intel.standard_of_care.pipeline_therapies = pipeline_data.get('therapies', [])
            market_intel.standard_of_care.num_pipeline_therapies = len(pipeline_data.get('therapies', []))
            if pipeline_data.get('details'):
                market_intel.standard_of_care.pipeline_details = pipeline_data['details']
            # Track pipeline sources
            market_intel.pipeline_sources = [r.get('url') for r in pipeline_results if r.get('url')][:3]
            for r in pipeline_results[:2]:
                if r.get('url'):
                    attributed_sources.append(AttributedSource(
                        url=r.get('url'),
                        title=r.get('title', 'Unknown'),
                        attribution='Pipeline/Clinical Trials'
                    ))

        # 5. Get TAM analysis data (market reports, treatment penetration)
        self.search_count += 1
        tam_results = self.web_search.search(
            f'"{disease}" market size TAM treatment penetration addressable market forecast',
            max_results=5
        )

        # Calculate simple market sizing (backward compatibility)
        market_intel = self._calculate_market_sizing(market_intel)

        # 6. Extract TAM with rationale
        if tam_results or all_treatment_results:
            tam_data = self._extract_tam_analysis(
                disease,
                tam_results or [],
                market_intel.epidemiology,
                market_intel.standard_of_care
            )
            market_intel.tam_usd = tam_data.get('tam_usd')
            market_intel.tam_estimate = tam_data.get('tam_estimate')
            market_intel.tam_rationale = tam_data.get('tam_rationale')
            # Track TAM sources
            if tam_results:
                market_intel.tam_sources = [r.get('url') for r in tam_results if r.get('url')][:3]
                for r in tam_results[:2]:
                    if r.get('url'):
                        attributed_sources.append(AttributedSource(
                            url=r.get('url'),
                            title=r.get('title', 'Unknown'),
                            attribution='TAM/Market Analysis'
                        ))

        # Store all attributed sources
        market_intel.attributed_sources = attributed_sources

        # Save to database for caching
        if self.cs_db:
            self.cs_db.save_market_intelligence(market_intel)
            logger.debug(f"Saved market intelligence to cache for: {disease}")

        return market_intel

    def _calculate_market_sizing(self, market_intel: MarketIntelligence) -> MarketIntelligence:
        """Calculate market size estimates based on epidemiology and treatment cost data."""
        epi = market_intel.epidemiology
        soc = market_intel.standard_of_care

        patient_pop = epi.patient_population_size or 0
        avg_cost = soc.avg_annual_cost_usd

        # Calculate market size if we have the data
        if patient_pop > 0:
            # Use provided cost or estimate based on patient population (rare vs common disease)
            if not avg_cost:
                if patient_pop < 10000:
                    # Ultra-rare: high-priced biologics/gene therapies
                    avg_cost = 200000
                elif patient_pop < 50000:
                    # Rare: specialty biologics
                    avg_cost = 100000
                elif patient_pop < 200000:
                    # Specialty: specialty drugs
                    avg_cost = 50000
                else:
                    # Common: mix of specialty and generics
                    avg_cost = 25000

            market_size_usd = patient_pop * avg_cost
            market_intel.market_size_usd = market_size_usd

            # Format market size estimate
            if market_size_usd >= 1_000_000_000:
                market_intel.market_size_estimate = f"${market_size_usd / 1_000_000_000:.1f}B"
            elif market_size_usd >= 1_000_000:
                market_intel.market_size_estimate = f"${market_size_usd / 1_000_000:.0f}M"
            else:
                market_intel.market_size_estimate = f"${market_size_usd / 1_000:.0f}K"

        # Estimate growth rate based on disease characteristics
        if epi.trend:
            trend = epi.trend.lower()
            if 'increasing' in trend:
                market_intel.growth_rate = "5-10% CAGR (increasing prevalence)"
            elif 'decreasing' in trend:
                market_intel.growth_rate = "0-2% CAGR (decreasing prevalence)"
            else:
                market_intel.growth_rate = "3-5% CAGR (stable prevalence)"
        elif soc.unmet_need:
            # High unmet need often correlates with market growth
            market_intel.growth_rate = "5-8% CAGR (high unmet need)"
        elif soc.num_pipeline_therapies and soc.num_pipeline_therapies > 3:
            # Active pipeline suggests growth potential
            market_intel.growth_rate = "4-7% CAGR (active pipeline)"
        else:
            market_intel.growth_rate = "3-5% CAGR (estimated)"

        return market_intel

    def _extract_epidemiology(self, disease: str, results: List[Dict]) -> EpidemiologyData:
        """Extract epidemiology data from search results."""
        # Include URLs in the search results for source citation
        # Note: Tavily API returns 'content', not 'snippet'
        results_with_urls = []
        for r in results:
            results_with_urls.append({
                'title': r.get('title'),
                'content': r.get('content') or r.get('snippet'),  # Tavily uses 'content'
                'url': r.get('url')
            })

        prompt = f"""Extract epidemiology data for {disease} from these search results.

Search Results:
{json.dumps(results_with_urls, indent=2)[:6000]}

Return ONLY valid JSON:
{{
    "us_prevalence_estimate": "estimated US prevalence (e.g. '1 in 10,000' or '200,000 patients') or null",
    "us_incidence_estimate": "annual incidence estimate or null",
    "patient_population_size": integer estimate of US patient count (MUST be integer, not string),
    "prevalence_source": "name of source (e.g. 'NIH GARD', 'CDC', journal name) or null",
    "prevalence_source_url": "URL of the source or null",
    "trend": "increasing/stable/decreasing or null"
}}

CRITICAL FOR patient_population_size:
- This MUST be an integer estimate of US patients (not null unless truly unknown)
- If prevalence is given as percentage (e.g., "1%"), calculate: US population (335M) * prevalence
- If prevalence is "1 in X", calculate: 335,000,000 / X
- If worldwide cases given (e.g., "130 worldwide"), estimate US portion (~4% of world population)
- If a range is given, use the midpoint
- Example: "1-2% prevalence" -> 335M * 0.015 = 5,025,000
- Example: "1 in 10,000" -> 335M / 10000 = 33,500
- Example: "130 worldwide" -> 130 * 0.04 = ~5 (round to nearest integer)
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
        """Extract standard of care from search results - BRANDED INNOVATIVE DRUGS ONLY."""
        # Include URLs for source citation
        # Note: Tavily API returns 'content', not 'snippet'
        results_with_urls = []
        for r in results:
            results_with_urls.append({
                'title': r.get('title'),
                'content': r.get('content') or r.get('snippet'),  # Tavily uses 'content'
                'url': r.get('url')
            })

        prompt = f"""Extract FDA-approved BRANDED INNOVATIVE treatments for {disease}.

=== CRITICAL: INDICATION-SPECIFIC FDA APPROVALS ONLY ===
Only count drugs with FDA approval for THIS EXACT INDICATION: "{disease}"

IMPORTANT INDICATION DISTINCTIONS (different FDA labels):
- "Systemic Lupus Erythematosus (SLE)" ≠ "Lupus Nephritis" (different indications!)
  * SLE approved: Benlysta, Saphnelo
  * Lupus Nephritis approved: Lupkynis, Benlysta
- "Rheumatoid Arthritis" ≠ "Juvenile Idiopathic Arthritis"
- "Atopic Dermatitis" (adult) may have different approvals than pediatric
- "Crohn's Disease" ≠ "Ulcerative Colitis"

If analyzing "{disease}", only count drugs FDA-approved for EXACTLY "{disease}".
Do NOT count drugs approved for related but different indications.

=== BRANDED INNOVATIVE DRUGS ONLY ===
INCLUDE (is_branded_innovative=true):
- Biologics: monoclonal antibodies, fusion proteins, recombinant proteins
  Examples: Ilaris, Kineret, Actemra, Humira, Enbrel, Cosentyx, Stelara, Dupixent, Ocrevus
- Novel small molecules with brand names: JAK inhibitors, kinase inhibitors, targeted therapies
  Examples: Olumiant (baricitinib), Xeljanz (tofacitinib), Rinvoq (upadacitinib), Jakafi
- Specialty drugs: IVIG products, enzyme replacement therapies
  Examples: Octagam 10%, Gamunex-C, Cerezyme, Fabrazyme
- Gene/cell therapies: Zolgensma, Luxturna, Yescarta

EXCLUDE (is_branded_innovative=false):
- Generic drugs even with brand names: corticosteroids (prednisone, Medrol), methotrexate, azathioprine, cyclosporine
- Supportive care: NSAIDs, pain medications, antihistamines
- OTC medications: eye drops, topical steroids
- Branded generics: Cyclogyl (cyclopentolate), generic-equivalent products

Search Results:
{json.dumps(results_with_urls, indent=2)[:6000]}

Return ONLY valid JSON:
{{
    "top_treatments": [
        {{
            "drug_name": "Brand Name (generic)",
            "drug_class": "class (e.g., IL-1 inhibitor, JAK inhibitor)",
            "is_branded_innovative": true/false,
            "fda_approved": true/false,
            "fda_approved_indication": "EXACT indication name from FDA label or null",
            "line_of_therapy": "1L/2L/3L or null",
            "efficacy_range": "60-70%",
            "annual_cost_usd": integer or null,
            "notes": "FDA approval details including specific indication"
        }}
    ],
    "approved_drug_names": ["Brand1 (generic1)", "Brand2 (generic2)"],
    "num_approved_drugs": integer (count of drugs FDA-approved for EXACTLY "{disease}"),
    "avg_annual_cost_usd": integer (average of branded innovative drugs only),
    "treatment_paradigm": "1-2 sentence description of treatment approach including line of therapy",
    "unmet_need": true/false,
    "unmet_need_description": "description or null",
    "competitive_landscape": "2-sentence summary",
    "soc_source": "source name and URL"
}}

VALIDATION RULES:
1. fda_approved=true ONLY if FDA approved for EXACTLY "{disease}" (not related conditions)
2. approved_drug_names MUST only contain drugs where is_branded_innovative=true AND fda_approved=true for THIS indication
3. num_approved_drugs MUST exactly equal length of approved_drug_names list
4. Generic drugs (corticosteroids, methotrexate, etc.) should NEVER appear in approved_drug_names
5. If drug is approved for related but different indication (e.g., Lupus Nephritis vs SLE), set fda_approved=false

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

            # Build treatments with new fields
            treatments = []
            approved_innovative_count = 0
            approved_innovative_names = []

            for t in data.get('top_treatments', []):
                is_branded = t.get('is_branded_innovative', False)
                is_approved = t.get('fda_approved', False)
                fda_indication = t.get('fda_approved_indication')

                treatments.append(StandardOfCareTreatment(
                    drug_name=t.get('drug_name', 'Unknown'),
                    drug_class=t.get('drug_class'),
                    is_branded_innovative=is_branded,
                    fda_approved=is_approved,
                    fda_approved_indication=fda_indication,
                    line_of_therapy=t.get('line_of_therapy'),
                    efficacy_range=t.get('efficacy_range'),
                    annual_cost_usd=t.get('annual_cost_usd'),
                    notes=t.get('notes')
                ))

                # Count branded innovative drugs that are FDA approved FOR THIS EXACT INDICATION
                if is_branded and is_approved:
                    approved_innovative_count += 1
                    approved_innovative_names.append(t.get('drug_name', 'Unknown'))

            # Use validated count from top_treatments (cross-validation)
            # This ensures count matches the actual list
            final_approved_names = approved_innovative_names if approved_innovative_names else data.get('approved_drug_names', [])
            final_count = len(final_approved_names)

            return StandardOfCareData(
                top_treatments=treatments,
                approved_drug_names=final_approved_names,
                num_approved_drugs=final_count,
                num_pipeline_therapies=data.get('num_pipeline_therapies', 0),
                pipeline_details=data.get('pipeline_details'),
                avg_annual_cost_usd=data.get('avg_annual_cost_usd'),
                treatment_paradigm=data.get('treatment_paradigm'),
                unmet_need=data.get('unmet_need', False),
                unmet_need_description=data.get('unmet_need_description'),
                competitive_landscape=data.get('competitive_landscape'),
                soc_source=data.get('soc_source')
            )
        except Exception as e:
            logger.error(f"Error extracting SOC: {e}")
            return StandardOfCareData()

    def _extract_pipeline_data(self, disease: str, results: List[Dict]) -> Dict[str, Any]:
        """Extract comprehensive pipeline data from ClinicalTrials.gov focused search."""
        results_with_urls = []
        for r in results:
            results_with_urls.append({
                'title': r.get('title'),
                'content': r.get('content') or r.get('snippet'),
                'url': r.get('url')
            })

        prompt = f"""Extract clinical trial pipeline data for {disease}.

Search Results:
{json.dumps(results_with_urls, indent=2)[:5000]}

Return ONLY valid JSON:
{{
    "pipeline_therapies": [
        {{
            "drug_name": "Drug name or code (e.g., 'ABC-123' or 'drugname')",
            "company": "Sponsoring company",
            "mechanism": "Mechanism of action",
            "phase": "Phase 1/Phase 2/Phase 3",
            "trial_id": "NCT number if available",
            "expected_completion": "Expected date or null"
        }}
    ],
    "pipeline_summary": "1-2 sentence summary of pipeline activity"
}}

RULES:
- Only include drugs in ACTIVE clinical trials (Phase 1, 2, or 3)
- EXCLUDE: Preclinical drugs, discontinued trials, already approved drugs
- EXCLUDE: Trials for other indications even if same drug
- Include NCT numbers when available
- Focus on this SPECIFIC indication: {disease}

Return ONLY the JSON."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            # Build pipeline therapy objects
            therapies = []
            for t in data.get('pipeline_therapies', []):
                therapies.append(PipelineTherapy(
                    drug_name=t.get('drug_name', 'Unknown'),
                    company=t.get('company'),
                    mechanism=t.get('mechanism'),
                    phase=t.get('phase', 'Unknown'),
                    trial_id=t.get('trial_id'),
                    expected_completion=t.get('expected_completion')
                ))

            return {
                'therapies': therapies,
                'details': data.get('pipeline_summary')
            }
        except Exception as e:
            logger.error(f"Error extracting pipeline data: {e}")
            return {'therapies': [], 'details': None}

    def _extract_tam_analysis(
        self,
        disease: str,
        tam_results: List[Dict],
        epidemiology: EpidemiologyData,
        soc: StandardOfCareData
    ) -> Dict[str, Any]:
        """Extract TAM (Total Addressable Market) with detailed rationale."""
        results_with_urls = []
        for r in tam_results:
            results_with_urls.append({
                'title': r.get('title'),
                'content': r.get('content') or r.get('snippet'),
                'url': r.get('url')
            })

        # Provide context from already-extracted data
        context = {
            'patient_population': epidemiology.patient_population_size,
            'prevalence': epidemiology.us_prevalence_estimate,
            'num_approved_drugs': soc.num_approved_drugs,
            'treatment_paradigm': soc.treatment_paradigm,
            'avg_annual_cost': soc.avg_annual_cost_usd,
            'unmet_need': soc.unmet_need
        }

        prompt = f"""Calculate the Total Addressable Market (TAM) for a NEW DRUG entering the {disease} market.

=== KNOWN DATA ===
{json.dumps(context, indent=2)}

=== MARKET RESEARCH RESULTS ===
{json.dumps(results_with_urls, indent=2)[:4000]}

=== TAM CALCULATION FRAMEWORK ===
TAM should account for REALISTIC market penetration, not total patient population x cost.

Consider:
1. TREATMENT FUNNEL:
   - What % of patients are diagnosed?
   - What % of diagnosed patients receive treatment?
   - What line of therapy would a new drug likely be positioned? (1L, 2L, 3L)
   - What % of patients reach each line of therapy?

2. MARKET PENETRATION:
   - How many approved competitors exist?
   - What market share could a new entrant realistically capture?
   - Typical new drug peak market share: 10-30% in crowded markets, 30-50% in underserved

3. TREATMENT DURATION:
   - Is this chronic or acute treatment?
   - What is typical treatment duration and compliance?

4. PRICING:
   - What is realistic pricing for this indication?
   - Orphan drugs: $100K-500K/yr, Specialty: $50K-150K/yr, Primary care: $10K-50K/yr

Return ONLY valid JSON:
{{
    "tam_usd": integer (Total Addressable Market in USD),
    "tam_estimate": "formatted string (e.g., '$2.5B')",
    "tam_rationale": "Detailed 2-4 sentence explanation including: patient funnel (X diagnosed, Y% treated, Z% reach target LOT), assumed market share (A%), pricing ($B/yr), calculation steps"
}}

EXAMPLE tam_rationale:
"Of ~100,000 US patients with [disease], ~70% are diagnosed (70K), ~60% receive systemic treatment (42K), ~30% fail 1L therapy and are candidates for 2L+ (12.6K). A new 2L drug could capture 25-35% market share (~3.8K patients). At $75K/yr, TAM = $285M. High unmet need in refractory population supports premium pricing."

Return ONLY the JSON."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}]
            )
            self._track_tokens(response.usage)

            content = self._clean_json_response(response.content[0].text.strip())
            data = json.loads(content)

            return {
                'tam_usd': data.get('tam_usd'),
                'tam_estimate': data.get('tam_estimate'),
                'tam_rationale': data.get('tam_rationale')
            }
        except Exception as e:
            logger.error(f"Error extracting TAM: {e}")
            return {'tam_usd': None, 'tam_estimate': None, 'tam_rationale': None}

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

            # Market Intelligence sheet - enhanced with TAM and pipeline details
            market_data = []
            for opp in result.opportunities:
                if opp.market_intelligence:
                    mi = opp.market_intelligence
                    epi = mi.epidemiology
                    soc = mi.standard_of_care

                    # Format pipeline therapies with details
                    pipeline_details_formatted = None
                    if soc.pipeline_therapies:
                        pipeline_items = []
                        for pt in soc.pipeline_therapies:
                            item = f"{pt.drug_name} ({pt.phase})"
                            if pt.company:
                                item += f" - {pt.company}"
                            if pt.trial_id:
                                item += f" [{pt.trial_id}]"
                            pipeline_items.append(item)
                        pipeline_details_formatted = "; ".join(pipeline_items)
                    elif soc.pipeline_details:
                        pipeline_details_formatted = soc.pipeline_details

                    # Group sources by category into separate columns
                    sources_by_category = {
                        'Epidemiology': [],
                        'Approved Treatments': [],
                        'Treatment Paradigm': [],
                        'Pipeline/Clinical Trials': [],
                        'TAM/Market Analysis': []
                    }
                    if mi.attributed_sources:
                        for src in mi.attributed_sources:
                            if src.attribution in sources_by_category:
                                sources_by_category[src.attribution].append(src.url or src.title or 'Unknown')

                    # Format each category as comma-separated URLs
                    sources_epidemiology = ', '.join(sources_by_category['Epidemiology']) if sources_by_category['Epidemiology'] else None
                    sources_approved = ', '.join(sources_by_category['Approved Treatments']) if sources_by_category['Approved Treatments'] else None
                    sources_treatment = ', '.join(sources_by_category['Treatment Paradigm']) if sources_by_category['Treatment Paradigm'] else None
                    sources_pipeline = ', '.join(sources_by_category['Pipeline/Clinical Trials']) if sources_by_category['Pipeline/Clinical Trials'] else None
                    sources_tam = ', '.join(sources_by_category['TAM/Market Analysis']) if sources_by_category['TAM/Market Analysis'] else None

                    market_data.append({
                        'Disease': mi.disease,
                        # Epidemiology
                        'US Prevalence': epi.us_prevalence_estimate,
                        'US Incidence': epi.us_incidence_estimate,
                        'Patient Population': epi.patient_population_size,
                        'Prevalence Trend': epi.trend,
                        # Competitive landscape - branded innovative drugs only
                        'Approved Treatments (Count)': soc.num_approved_drugs,
                        'Approved Drug Names': ', '.join(soc.approved_drug_names) if soc.approved_drug_names else None,
                        'Pipeline Therapies (Count)': soc.num_pipeline_therapies,
                        'Pipeline Details': pipeline_details_formatted,
                        'Treatment Paradigm': soc.treatment_paradigm,
                        'Top Treatments': ', '.join([f"{t.drug_name} ({'FDA' if t.fda_approved else 'off-label'})" for t in soc.top_treatments]) if soc.top_treatments else None,
                        # Unmet need
                        'Unmet Need': 'Yes' if soc.unmet_need else 'No',
                        'Unmet Need Description': soc.unmet_need_description,
                        # Market - Simple calculation (backward compatibility)
                        'Avg Annual Cost (USD)': soc.avg_annual_cost_usd,
                        'Market Size Estimate': mi.market_size_estimate,
                        'Market Size (USD)': mi.market_size_usd,
                        'Market Growth Rate': mi.growth_rate,
                        # TAM - Sophisticated market analysis (NEW)
                        'TAM (Total Addressable Market)': mi.tam_estimate,
                        'TAM (USD)': mi.tam_usd,
                        'TAM Rationale': mi.tam_rationale,
                        # Additional context
                        'Competitive Landscape': soc.competitive_landscape,
                        # Sources - Separate columns by category for easy filtering
                        'Sources - Epidemiology': sources_epidemiology,
                        'Sources - Approved Drugs': sources_approved,
                        'Sources - Treatment': sources_treatment,
                        'Sources - Pipeline': sources_pipeline,
                        'Sources - TAM/Market': sources_tam
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

