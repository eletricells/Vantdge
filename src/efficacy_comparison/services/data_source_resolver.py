"""
DataSourceResolver Service

Resolves the best available data source for extracting trial efficacy data.
Implements a fallback chain: PMC Full-Text > Abstract > CT.gov Results > FDA Label > Press Release.
"""

import logging
import os
import re
from typing import Dict, List, Optional

import httpx

from src.tools.pubmed import PubMedAPI
from src.drug_extraction_system.api_clients.openfda_client import OpenFDAClient
from src.drug_extraction_system.api_clients.clinicaltrials_client import ClinicalTrialsClient
from src.efficacy_comparison.models import (
    ApprovedDrug,
    DataSourceType,
    IdentifiedPaper,
    PivotalTrial,
    ResolvedDataSource,
)

logger = logging.getLogger(__name__)


# PMC Open Access API
PMC_OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi"
PMC_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class DataSourceResolver:
    """
    Resolves the best available data source for a trial/paper.

    Priority order (highest to lowest quality):
    1. PMC Full-Text (open access)
    2. PubMed Abstract
    3. ClinicalTrials.gov Results Tab
    4. FDA Label Clinical Studies Section
    5. Press Release / Web Search

    Each source has different completeness levels:
    - HIGH: Full-text with tables and figures
    - MEDIUM: Structured data or detailed abstract
    - LOW: Summary data only
    """

    def __init__(
        self,
        pubmed_api: Optional[PubMedAPI] = None,
        openfda_client: Optional[OpenFDAClient] = None,
        clinicaltrials_client: Optional[ClinicalTrialsClient] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Initialize the service.

        Args:
            pubmed_api: Optional PubMed API instance
            openfda_client: Optional OpenFDA client
            clinicaltrials_client: Optional CT.gov client
            http_client: Optional async HTTP client
        """
        self.pubmed = pubmed_api or PubMedAPI()
        self.openfda = openfda_client or OpenFDAClient()
        self.ctgov = clinicaltrials_client or ClinicalTrialsClient()
        self._http_client = http_client

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def resolve_data_source(
        self,
        paper: Optional[IdentifiedPaper],
        trial: PivotalTrial,
        drug: ApprovedDrug,
    ) -> ResolvedDataSource:
        """
        Resolve the best available data source for a trial.

        Tries sources in priority order until one succeeds.

        Args:
            paper: IdentifiedPaper (may be None if no paper found)
            trial: PivotalTrial with trial identifiers
            drug: ApprovedDrug with drug information

        Returns:
            ResolvedDataSource with content to extract from

        Raises:
            NoDataSourceAvailable if all sources fail
        """
        logger.info(
            f"Resolving data source for trial: {trial.trial_name or trial.nct_id}"
        )

        # Track what we've tried for fallback
        abstract_content = None

        # Priority 1: PMC Full-Text
        if paper and paper.pmc_id:
            logger.debug(f"Trying PMC full-text: {paper.pmc_id}")
            pmc_content = await self._fetch_pmc_fulltext(paper.pmc_id)
            if pmc_content:
                logger.info(f"Using PMC full-text for {paper.pmc_id}")
                return ResolvedDataSource(
                    source_type=DataSourceType.PMC_FULLTEXT,
                    content=pmc_content,
                    completeness="HIGH",
                    url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{paper.pmc_id}",
                    pmid=paper.pmid,
                    pmc_id=paper.pmc_id,
                    title=paper.title,
                )

        # Priority 2: PubMed Abstract
        if paper and paper.abstract:
            abstract_content = self._format_abstract_content(paper)
            # Don't return yet - try to get better sources first

        # Also try to fetch abstract if we have PMID but no abstract
        if paper and paper.pmid and not paper.abstract:
            logger.debug(f"Fetching abstract for PMID: {paper.pmid}")
            abstract = await self._fetch_abstract(paper.pmid)
            if abstract:
                paper.abstract = abstract
                abstract_content = self._format_abstract_content(paper)

        # Priority 3: ClinicalTrials.gov Results
        if trial.nct_id:
            logger.debug(f"Trying CT.gov results: {trial.nct_id}")
            ctgov_content = await self._fetch_ctgov_results(trial.nct_id)
            if ctgov_content:
                logger.info(f"Using CT.gov results for {trial.nct_id}")
                return ResolvedDataSource(
                    source_type=DataSourceType.CTGOV_RESULTS,
                    content=ctgov_content,
                    completeness="MEDIUM",
                    url=f"https://clinicaltrials.gov/study/{trial.nct_id}?tab=results",
                    pmid=paper.pmid if paper else None,
                    title=paper.title if paper else trial.trial_name,
                )

        # Priority 4: FDA Label Clinical Studies Section
        logger.debug(f"Trying FDA label for {drug.drug_name}")
        fda_content = await self._fetch_fda_label_trial_section(
            drug, trial.trial_name
        )
        if fda_content:
            logger.info(f"Using FDA label for {drug.drug_name}")
            return ResolvedDataSource(
                source_type=DataSourceType.FDA_LABEL,
                content=fda_content,
                completeness="MEDIUM",
                url=f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={drug.dailymed_setid}"
                if drug.dailymed_setid else None,
                pmid=paper.pmid if paper else None,
                title=f"FDA Label - {drug.drug_name}",
            )

        # Priority 5: Return abstract if we have it (fallback)
        if abstract_content:
            logger.info(f"Using abstract for PMID: {paper.pmid}")
            return ResolvedDataSource(
                source_type=DataSourceType.ABSTRACT,
                content=abstract_content,
                completeness="LOW",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{paper.pmid}",
                pmid=paper.pmid,
                title=paper.title,
            )

        # Priority 6: Web Search for Press Releases (not implemented yet)
        # This would use web search to find press releases about trial results
        logger.warning(
            f"No primary data source found for trial: {trial.trial_name or trial.nct_id}"
        )

        # Return a minimal source with what we know
        return ResolvedDataSource(
            source_type=DataSourceType.WEB_SEARCH,
            content=self._create_minimal_content(trial, drug),
            completeness="LOW",
            url=None,
            title=trial.trial_name,
        )

    async def _fetch_pmc_fulltext(self, pmc_id: str) -> Optional[str]:
        """
        Fetch full-text content from PMC.

        Tries to get the full article text including tables.
        """
        try:
            client = await self._get_http_client()

            # Use efetch to get full text in XML format
            params = {
                "db": "pmc",
                "id": pmc_id.replace("PMC", ""),
                "rettype": "full",
                "retmode": "xml",
            }

            response = await client.get(PMC_EFETCH_URL, params=params)

            if response.status_code != 200:
                logger.debug(f"PMC efetch failed: {response.status_code}")
                return None

            xml_content = response.text

            # Parse XML to extract text content
            text_content = self._parse_pmc_xml(xml_content)

            if text_content and len(text_content) > 500:
                return text_content

        except Exception as e:
            logger.error(f"Error fetching PMC full-text for {pmc_id}: {e}")

        return None

    def _parse_pmc_xml(self, xml_content: str) -> Optional[str]:
        """
        Parse PMC XML to extract relevant text sections.

        Focuses on:
        - Abstract
        - Methods (study design)
        - Results
        - Tables
        """
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(xml_content)

            sections = []

            # Get article title
            title_elem = root.find(".//article-title")
            if title_elem is not None and title_elem.text:
                sections.append(f"TITLE: {title_elem.text}")

            # Get abstract
            abstract_elem = root.find(".//abstract")
            if abstract_elem is not None:
                abstract_text = self._extract_text(abstract_elem)
                if abstract_text:
                    sections.append(f"ABSTRACT:\n{abstract_text}")

            # Get body sections (Results, Methods, etc.)
            for sec in root.findall(".//body//sec"):
                sec_title = sec.find("title")
                if sec_title is not None and sec_title.text:
                    title_lower = sec_title.text.lower()
                    # Focus on relevant sections
                    if any(kw in title_lower for kw in
                           ["result", "efficacy", "outcome", "endpoint",
                            "method", "patient", "baseline", "demographic"]):
                        sec_text = self._extract_text(sec)
                        if sec_text:
                            sections.append(f"{sec_title.text.upper()}:\n{sec_text}")

            # Get tables
            for table_wrap in root.findall(".//table-wrap"):
                table_id = table_wrap.get("id", "")
                caption = table_wrap.find(".//caption")
                caption_text = self._extract_text(caption) if caption is not None else ""

                table = table_wrap.find(".//table")
                if table is not None:
                    table_text = self._parse_table(table)
                    if table_text:
                        sections.append(f"TABLE ({table_id}): {caption_text}\n{table_text}")

            return "\n\n".join(sections) if sections else None

        except Exception as e:
            logger.error(f"Error parsing PMC XML: {e}")
            return None

    def _extract_text(self, element) -> str:
        """Extract all text from an XML element."""
        if element is None:
            return ""
        text_parts = []
        for text in element.itertext():
            if text.strip():
                text_parts.append(text.strip())
        return " ".join(text_parts)

    def _parse_table(self, table_elem) -> str:
        """Parse an HTML/XML table into text format."""
        rows = []

        # Get header row
        thead = table_elem.find(".//thead")
        if thead is not None:
            for tr in thead.findall(".//tr"):
                cells = []
                for th in tr.findall(".//th"):
                    cells.append(self._extract_text(th))
                if cells:
                    rows.append(" | ".join(cells))

        # Get body rows
        tbody = table_elem.find(".//tbody")
        if tbody is not None:
            for tr in tbody.findall(".//tr"):
                cells = []
                for td in tr.findall(".//td"):
                    cells.append(self._extract_text(td))
                if cells:
                    rows.append(" | ".join(cells))

        return "\n".join(rows) if rows else ""

    async def _fetch_abstract(self, pmid: str) -> Optional[str]:
        """Fetch abstract from PubMed."""
        try:
            details = self.pubmed.fetch_details([pmid])
            if details:
                return details[0].get("abstract", "")
        except Exception as e:
            logger.error(f"Error fetching abstract for {pmid}: {e}")
        return None

    def _format_abstract_content(self, paper: IdentifiedPaper) -> str:
        """Format paper info and abstract into extraction content."""
        parts = [
            f"TITLE: {paper.title}",
            f"AUTHORS: {paper.authors}" if paper.authors else "",
            f"JOURNAL: {paper.journal}" if paper.journal else "",
            f"YEAR: {paper.year}" if paper.year else "",
            f"PMID: {paper.pmid}",
            "",
            "ABSTRACT:",
            paper.abstract or "No abstract available",
        ]
        return "\n".join(parts)

    async def _fetch_ctgov_results(self, nct_id: str) -> Optional[str]:
        """
        Fetch results data from ClinicalTrials.gov.

        Extracts outcome measures and results from the trial record.
        """
        try:
            study = self.ctgov.get_trial_by_nct(nct_id)
            if not study:
                return None

            # Check if trial has results
            protocol = study.get("protocolSection", {})
            has_results = study.get("hasResults", False)

            if not has_results:
                logger.debug(f"No results posted for {nct_id}")
                return None

            # Get results section
            results_section = study.get("resultsSection", {})
            if not results_section:
                return None

            parts = []

            # Basic trial info
            id_module = protocol.get("identificationModule", {})
            parts.append(f"TRIAL: {id_module.get('briefTitle', nct_id)}")
            parts.append(f"NCT ID: {nct_id}")

            # Design info
            design_module = protocol.get("designModule", {})
            enrollment = design_module.get("enrollmentInfo", {}).get("count")
            if enrollment:
                parts.append(f"ENROLLMENT: {enrollment}")

            phases = design_module.get("phases", [])
            if phases:
                parts.append(f"PHASE: {', '.join(phases)}")

            parts.append("")

            # Participant flow
            flow = results_section.get("participantFlowModule", {})
            if flow:
                parts.append("PARTICIPANT FLOW:")
                groups = flow.get("groups", [])
                for group in groups:
                    title = group.get("title", "")
                    desc = group.get("description", "")
                    parts.append(f"  - {title}: {desc}")
                parts.append("")

            # Baseline characteristics
            baseline = results_section.get("baselineCharacteristicsModule", {})
            if baseline:
                parts.append("BASELINE CHARACTERISTICS:")
                measures = baseline.get("measures", [])
                for measure in measures[:10]:  # Limit
                    title = measure.get("title", "")
                    parts.append(f"  {title}:")
                    classes = measure.get("classes", [])
                    for cls in classes:
                        categories = cls.get("categories", [])
                        for cat in categories:
                            cat_title = cat.get("title", "")
                            measurements = cat.get("measurements", [])
                            for m in measurements:
                                group_id = m.get("groupId", "")
                                value = m.get("value", "")
                                parts.append(f"    {cat_title} ({group_id}): {value}")
                parts.append("")

            # Outcome measures
            outcomes = results_section.get("outcomeMeasuresModule", {})
            if outcomes:
                parts.append("OUTCOME MEASURES:")
                measures = outcomes.get("outcomeMeasures", [])
                for measure in measures:
                    title = measure.get("title", "")
                    outcome_type = measure.get("type", "")
                    time_frame = measure.get("timeFrame", "")
                    parts.append(f"\n  {outcome_type}: {title}")
                    parts.append(f"  Time Frame: {time_frame}")

                    groups = measure.get("groups", [])
                    classes = measure.get("classes", [])

                    for cls in classes:
                        categories = cls.get("categories", [])
                        for cat in categories:
                            measurements = cat.get("measurements", [])
                            for m in measurements:
                                group_id = m.get("groupId", "")
                                value = m.get("value", "")
                                spread = m.get("spread", "")
                                parts.append(f"    {group_id}: {value} (spread: {spread})")

                    # Statistical analyses
                    analyses = measure.get("analyses", [])
                    for analysis in analyses:
                        stat_method = analysis.get("statisticalMethod", "")
                        p_value = analysis.get("pValue", "")
                        if p_value:
                            parts.append(f"    Statistical: {stat_method}, p={p_value}")

            content = "\n".join(parts)
            return content if len(content) > 200 else None

        except Exception as e:
            logger.error(f"Error fetching CT.gov results for {nct_id}: {e}")
            return None

    async def _fetch_fda_label_trial_section(
        self,
        drug: ApprovedDrug,
        trial_name: Optional[str],
    ) -> Optional[str]:
        """
        Fetch Clinical Studies section from FDA label.
        """
        try:
            labels = self.openfda.search_drug_labels(drug.drug_name, limit=3)
            if not labels:
                labels = self.openfda.search_drug_labels(drug.generic_name, limit=3)

            if not labels:
                return None

            label = labels[0]

            # Get clinical studies section
            clinical_studies = label.get("clinical_studies", [""])[0]

            if not clinical_studies:
                return None

            # If we have a specific trial name, try to extract just that section
            if trial_name:
                # Look for section about this specific trial
                pattern = rf'({trial_name}[^.]*?\..*?(?=\n\n|\Z))'
                match = re.search(pattern, clinical_studies, re.IGNORECASE | re.DOTALL)
                if match:
                    trial_section = match.group(1)
                    if len(trial_section) > 200:
                        return f"FDA LABEL - {drug.drug_name}\n\nCLINICAL STUDIES ({trial_name}):\n{trial_section}"

            # Return full clinical studies section
            return f"FDA LABEL - {drug.drug_name}\n\nCLINICAL STUDIES:\n{clinical_studies}"

        except Exception as e:
            logger.error(f"Error fetching FDA label for {drug.drug_name}: {e}")
            return None

    def _create_minimal_content(
        self,
        trial: PivotalTrial,
        drug: ApprovedDrug,
    ) -> str:
        """Create minimal content when no good source is available."""
        parts = [
            f"DRUG: {drug.drug_name} ({drug.generic_name})",
            f"TRIAL: {trial.trial_name or 'Unknown'}",
            f"NCT ID: {trial.nct_id or 'Unknown'}",
            f"PHASE: {trial.phase or 'Unknown'}",
            f"PRIMARY ENDPOINT: {trial.primary_endpoint or 'Unknown'}",
            "",
            "NOTE: Limited data available. Consider web search or press releases.",
        ]
        return "\n".join(parts)

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
