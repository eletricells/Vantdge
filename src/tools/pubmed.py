"""
PubMed API wrapper for searching biomedical literature.
"""
import httpx
from typing import List, Dict, Optional, Any
import logging
import time
import json
from pathlib import Path
from datetime import datetime
from xml.etree import ElementTree as ET


logger = logging.getLogger(__name__)


class PubMedAPI:
    """
    Wrapper for NCBI PubMed E-utilities API.

    Documentation: https://www.ncbi.nlm.nih.gov/books/NBK25501/
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, api_key: Optional[str] = None, email: Optional[str] = None, timeout: int = 30):
        """
        Initialize PubMed API client.

        Args:
            api_key: NCBI API key (for higher rate limits)
            email: Email address (required by NCBI for tracking)
            timeout: Request timeout in seconds
        """
        self.api_key = api_key
        self.email = email or "noreply@example.com"
        self.timeout = timeout
        self.session = httpx.Client(timeout=timeout)
        self.last_request_time = 0
        # Rate limit: 3 req/sec without key, 10 req/sec with key
        self.rate_limit_delay = 0.11 if api_key else 0.35

        # Paper cache configuration
        self.cache_dir = Path("data/downloaded_papers")
        self.cache_index_path = self.cache_dir / "index.json"
        self._init_cache()

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - time_since_last)
        self.last_request_time = time.time()

    def _init_cache(self):
        """Initialize paper cache directory and index."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if not self.cache_index_path.exists():
            # Create empty index
            self._save_index({})
            logger.info(f"Initialized paper cache at {self.cache_dir}")
        else:
            logger.info(f"Using existing paper cache at {self.cache_dir}")

    def _load_index(self) -> Dict[str, Any]:
        """Load cache index."""
        try:
            with open(self.cache_index_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load cache index: {e}")
            return {}

    def _save_index(self, index: Dict[str, Any]):
        """Save cache index."""
        try:
            with open(self.cache_index_path, 'w') as f:
                json.dump(index, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cache index: {e}")

    def _get_cached_paper(self, pmid: str) -> Optional[Dict[str, Any]]:
        """
        Get paper from cache if available.

        Args:
            pmid: PubMed ID

        Returns:
            Cached paper data or None if not cached
        """
        index = self._load_index()

        if pmid in index:
            paper_path = self.cache_dir / f"{pmid}.json"
            if paper_path.exists():
                try:
                    with open(paper_path, 'r', encoding='utf-8') as f:
                        paper = json.load(f)
                    logger.info(f"✓ Using cached paper: PMID {pmid}")
                    return paper
                except Exception as e:
                    logger.error(f"Failed to load cached paper {pmid}: {e}")

        return None

    def _save_paper_to_cache(self, paper: Dict[str, Any], save_dir: Optional[Path] = None,
                            drug_name: Optional[str] = None) -> Path:
        """
        Save paper to cache with metadata and proper naming.

        Args:
            paper: Paper data dictionary
            save_dir: Directory to save paper (defaults to self.cache_dir)
            drug_name: Drug name for filename (if provided, uses format: YYYY-MM_Author_drug.json)

        Returns:
            Path to saved file
        """
        pmid = paper.get('pmid')
        if not pmid:
            logger.warning("Cannot cache paper without PMID")
            return None

        try:
            # Determine save directory
            target_dir = save_dir if save_dir else self.cache_dir
            target_dir.mkdir(parents=True, exist_ok=True)

            # Determine filename
            if drug_name and paper.get('year') and paper.get('authors'):
                # Format: YYYY-MM_FirstAuthor_drug.json
                year = paper.get('year', 'Unknown')
                month = paper.get('month', '01')  # Default to January if no month

                # Format month as 2-digit string
                if isinstance(month, int):
                    month_str = f"{month:02d}"
                elif isinstance(month, str) and month.isdigit():
                    month_str = f"{int(month):02d}"
                else:
                    month_str = str(month) if month else '01'

                # Get first author's last name
                authors = paper.get('authors', [])
                if authors:
                    first_author = authors[0]
                    # Extract last name (format is usually "FirstName LastName" or "LastName")
                    author_parts = first_author.split()
                    last_name = author_parts[-1] if author_parts else 'Unknown'
                else:
                    last_name = 'Unknown'

                # Clean drug name for filename
                clean_drug = drug_name.lower().replace(' ', '_')

                filename = f"{year}-{month_str}_{last_name}_{clean_drug}.json"
            else:
                # Fallback to PMID-based naming
                filename = f"{pmid}.json"

            paper_path = target_dir / filename

            # Save paper JSON
            with open(paper_path, 'w', encoding='utf-8') as f:
                json.dump(paper, f, indent=2, ensure_ascii=False)

            # Update index
            index = self._load_index()
            index[pmid] = {
                'pmid': pmid,
                'pmcid': paper.get('pmcid'),
                'doi': paper.get('doi'),
                'title': paper.get('title'),
                'authors': paper.get('authors', []),
                'journal': paper.get('journal'),
                'year': paper.get('year'),
                'cached_date': datetime.now().isoformat(),
                'file_path': str(paper_path)
            }
            self._save_index(index)

            logger.info(f"✓ Cached paper: PMID {pmid} ({paper.get('title', 'Unknown')[:50]}...)")

            return paper_path

        except Exception as e:
            logger.error(f"Failed to cache paper {pmid}: {e}")
            return None

    def search_cached_papers(
        self,
        query: Optional[str] = None,
        drug: Optional[str] = None,
        target: Optional[str] = None,
        year_min: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search cached papers by metadata.

        Args:
            query: Text query to match in title
            drug: Drug name to match
            target: Target name to match
            year_min: Minimum publication year

        Returns:
            List of matching papers from cache index
        """
        index = self._load_index()
        results = []

        for pmid, metadata in index.items():
            # Apply filters
            if query and query.lower() not in metadata.get('title', '').lower():
                continue

            if drug and drug.lower() not in metadata.get('title', '').lower():
                continue

            if target and target.upper() not in metadata.get('title', '').upper():
                continue

            if year_min and metadata.get('year'):
                try:
                    if int(metadata['year']) < year_min:
                        continue
                except (ValueError, TypeError):
                    pass

            results.append(metadata)

        logger.info(f"Found {len(results)} cached papers matching search criteria")
        return results

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the paper cache.

        Returns:
            Dictionary with cache statistics
        """
        index = self._load_index()

        total_papers = len(index)
        total_size = 0

        for paper_path in self.cache_dir.glob("*.json"):
            if paper_path.name != "index.json":
                total_size += paper_path.stat().st_size

        # Extract years
        years = []
        for metadata in index.values():
            if metadata.get('year'):
                try:
                    years.append(int(metadata['year']))
                except (ValueError, TypeError):
                    pass

        stats = {
            'total_papers': total_papers,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'cache_dir': str(self.cache_dir),
            'year_range': f"{min(years)}-{max(years)}" if years else "N/A",
            'index_path': str(self.cache_index_path)
        }

        return stats

    def search(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "relevance"
    ) -> List[str]:
        """
        Search PubMed and return PMIDs.

        Args:
            query: Search query
            max_results: Maximum number of results
            sort: Sort order (relevance, pub_date)

        Returns:
            List of PubMed IDs (PMIDs)
        """
        try:
            self._rate_limit()  # Enforce rate limiting

            params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": sort,
                "tool": "biopharma-investment-agent",
                "email": self.email
            }

            if self.api_key:
                params["api_key"] = self.api_key

            response = self.session.get(
                f"{self.BASE_URL}/esearch.fcgi",
                params=params
            )
            response.raise_for_status()

            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse PubMed search JSON response: {e}")
                return []

            pmids = data.get("esearchresult", {}).get("idlist", [])

            logger.info(f"Found {len(pmids)} articles for query: {query}")
            return pmids

        except httpx.HTTPError as e:
            logger.error(f"PubMed search error: {str(e)}")
            return []

    def fetch_abstracts(self, pmids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch article abstracts for given PMIDs.

        Args:
            pmids: List of PubMed IDs

        Returns:
            List of article details with abstracts
        """
        if not pmids:
            return []

        try:
            self._rate_limit()  # Enforce rate limiting

            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                "rettype": "abstract",
                "tool": "biopharma-investment-agent",
                "email": self.email
            }

            if self.api_key:
                params["api_key"] = self.api_key

            response = self.session.get(
                f"{self.BASE_URL}/efetch.fcgi",
                params=params
            )
            response.raise_for_status()

            # Parse XML response
            articles = self._parse_xml_response(response.text)
            logger.info(f"Retrieved {len(articles)} article abstracts")

            return articles

        except httpx.HTTPError as e:
            logger.error(f"PubMed fetch error: {str(e)}")
            return []

    def search_and_fetch(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "relevance"
    ) -> List[Dict[str, Any]]:
        """
        Search PubMed and fetch abstracts in one call.

        Args:
            query: Search query
            max_results: Maximum number of results
            sort: Sort order

        Returns:
            List of article details with abstracts
        """
        pmids = self.search(query, max_results, sort)
        if pmids:
            return self.fetch_abstracts(pmids)
        return []

    def search_papers(
        self,
        query: str,
        max_results: int = 10,
        sort: str = "relevance"
    ) -> List[Dict[str, Any]]:
        """
        Search PubMed for papers (alias for search_and_fetch).

        Args:
            query: Search query
            max_results: Maximum number of results
            sort: Sort order (relevance, pub_date)

        Returns:
            List of paper dictionaries with pmid, title, abstract, authors, journal, year, publication_date, doi
        """
        return self.search_and_fetch(query, max_results, sort)

    def _parse_xml_response(self, xml_text: str) -> List[Dict[str, Any]]:
        """
        Parse PubMed XML response into structured data.

        Args:
            xml_text: XML response from PubMed

        Returns:
            List of article dictionaries
        """
        try:
            root = ET.fromstring(xml_text)
            articles = []

            for article_elem in root.findall(".//PubmedArticle"):
                article = self._extract_article_data(article_elem)
                if article:
                    articles.append(article)

            return articles

        except ET.ParseError as e:
            logger.error(f"XML parsing error: {str(e)}")
            return []

    def _extract_article_data(self, article_elem) -> Optional[Dict[str, Any]]:
        """Extract article data from XML element"""
        try:
            # PMID
            pmid_elem = article_elem.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else None

            # Article metadata
            medline = article_elem.find(".//MedlineCitation")
            article_data = medline.find(".//Article") if medline is not None else None

            if article_data is None:
                return None

            # Title
            title_elem = article_data.find(".//ArticleTitle")
            title = title_elem.text if title_elem is not None else "No title"

            # Abstract
            abstract_elem = article_data.find(".//Abstract/AbstractText")
            abstract = abstract_elem.text if abstract_elem is not None else "No abstract available"

            # Authors
            authors = []
            author_list = article_data.find(".//AuthorList")
            if author_list is not None:
                for author in author_list.findall(".//Author"):
                    last_name = author.find("LastName")
                    fore_name = author.find("ForeName")
                    if last_name is not None:
                        author_name = last_name.text
                        if fore_name is not None:
                            author_name = f"{fore_name.text} {author_name}"
                        authors.append(author_name)

            # Journal
            journal_elem = article_data.find(".//Journal/Title")
            journal = journal_elem.text if journal_elem is not None else "Unknown journal"

            # Publication date (extract full date if available)
            pub_date = article_data.find(".//Journal/JournalIssue/PubDate")
            year = "Unknown"
            month = None
            day = None
            publication_date = None

            if pub_date is not None:
                year_elem = pub_date.find("Year")
                month_elem = pub_date.find("Month")
                day_elem = pub_date.find("Day")

                year = year_elem.text if year_elem is not None else "Unknown"
                month = month_elem.text if month_elem is not None else None
                day = day_elem.text if day_elem is not None else None

                # Build publication_date string
                if year != "Unknown":
                    if month and day:
                        # Convert month name to number if needed
                        month_map = {
                            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                        }
                        month_num = month_map.get(month, month)
                        publication_date = f"{year}-{month_num}-{day}"
                    elif month:
                        month_map = {
                            'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                            'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                            'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                        }
                        month_num = month_map.get(month, month)
                        publication_date = f"{year}-{month_num}"
                    else:
                        publication_date = year

            # DOI
            doi = None
            for article_id in article_elem.findall(".//ArticleId"):
                if article_id.get("IdType") == "doi":
                    doi = article_id.text
                    break

            return {
                "pmid": pmid,
                "title": title,
                "abstract": abstract,
                "authors": authors,  # All authors
                "journal": journal,
                "year": year,
                "publication_date": publication_date,
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
            }

        except Exception as e:
            logger.error(f"Error extracting article data: {str(e)}")
            return None

    def format_for_llm(self, articles: List[Dict[str, Any]]) -> str:
        """
        Format articles for LLM consumption.

        Args:
            articles: List of article dictionaries

        Returns:
            Formatted text
        """
        if not articles:
            return "No articles found."

        output = []
        for i, article in enumerate(articles, 1):
            authors_str = ", ".join(article.get("authors", []))
            if len(article.get("authors", [])) > 3:
                authors_str += " et al."

            output.append(f"""
Article {i}:
PMID: {article.get('pmid', 'N/A')}
Title: {article.get('title', 'N/A')}
Authors: {authors_str}
Journal: {article.get('journal', 'N/A')} ({article.get('year', 'N/A')})
URL: {article.get('url', 'N/A')}

Abstract:
{article.get('abstract', 'N/A')}
---""")

        return "\n".join(output)

    def check_pmc_availability(self, pmids: List[str]) -> Dict[str, Optional[str]]:
        """
        Check which articles are available in PubMed Central (open access).

        Uses PubMed efetch to extract PMCIDs from article metadata.

        Args:
            pmids: List of PubMed IDs

        Returns:
            Dictionary mapping PMID -> PMCID (None if not available in PMC)
        """
        if not pmids:
            return {}

        try:
            self._rate_limit()  # Enforce rate limiting

            # Use efetch to get PubMed records with PMCID info
            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml",
                "tool": "biopharma-investment-agent",
                "email": self.email
            }

            if self.api_key:
                params["api_key"] = self.api_key

            response = self.session.get(
                f"{self.BASE_URL}/efetch.fcgi",
                params=params
            )

            response.raise_for_status()

            # Parse XML to extract PMCIDs
            root = ET.fromstring(response.text)
            pmc_map = {}

            for article in root.findall(".//PubmedArticle"):
                # Get PMID
                pmid_elem = article.find(".//PMID")
                pmid = pmid_elem.text if pmid_elem is not None else None

                # Get PMCID from ArticleIdList
                pmcid = None
                for article_id in article.findall(".//ArticleId[@IdType='pmc']"):
                    pmcid = article_id.text
                    break

                if pmid:
                    pmc_map[pmid] = pmcid
                    if pmcid:
                        logger.info(f"PMID {pmid} -> {pmcid} (open access)")
                    else:
                        logger.info(f"PMID {pmid} -> No PMCID (not in PMC)")

            # For PMIDs not in response, mark as unavailable
            for pmid in pmids:
                if pmid not in pmc_map:
                    pmc_map[pmid] = None

            available_count = sum(1 for v in pmc_map.values() if v)
            logger.info(f"PMC availability: {available_count}/{len(pmids)} papers available in PMC")

            return pmc_map

        except Exception as e:
            logger.error(f"PMC availability check error: {str(e)}")
            logger.warning("Could not determine PMC availability")
            # Return dict with all None to mark as paywalled
            return {pmid: None for pmid in pmids}

    def fetch_pmc_pdf(self, pmcid: str, save_path: Path) -> bool:
        """
        Download actual PDF file from PubMed Central.

        Args:
            pmcid: PubMed Central ID (e.g., "PMC1234567")
            save_path: Path where PDF should be saved

        Returns:
            True if PDF downloaded successfully, False otherwise
        """
        try:
            self._rate_limit()  # Enforce rate limiting

            # PMC PDF URL
            pmcid_num = pmcid.replace("PMC", "")
            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid_num}/pdf/"

            logger.info(f"Attempting to download PDF from {pdf_url}")

            response = self.session.get(pdf_url, follow_redirects=True)
            response.raise_for_status()

            # Check if we got a PDF
            content_type = response.headers.get('content-type', '')
            if 'application/pdf' not in content_type:
                logger.warning(f"Response is not a PDF (content-type: {content_type})")
                return False

            # Save PDF
            with open(save_path, 'wb') as f:
                f.write(response.content)

            logger.info(f"✓ Successfully downloaded PDF for {pmcid} ({len(response.content)} bytes)")
            return True

        except httpx.HTTPError as e:
            logger.warning(f"PMC PDF download failed for {pmcid}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading PDF for {pmcid}: {str(e)}")
            return False

    def fetch_pmc_fulltext(self, pmcid: str) -> Optional[str]:
        """
        Fetch full-text XML from PubMed Central.

        Args:
            pmcid: PubMed Central ID (e.g., "PMC1234567")

        Returns:
            Full-text content as string, or None if unavailable
        """
        try:
            self._rate_limit()  # Enforce rate limiting

            params = {
                "db": "pmc",
                "id": pmcid.replace("PMC", ""),  # Remove PMC prefix if present
                "retmode": "xml",
                "tool": "biopharma-investment-agent",
                "email": self.email
            }

            if self.api_key:
                params["api_key"] = self.api_key

            response = self.session.get(
                f"{self.BASE_URL}/efetch.fcgi",
                params=params
            )
            response.raise_for_status()

            logger.info(f"Successfully fetched full-text for {pmcid}")
            return response.text

        except httpx.HTTPError as e:
            logger.error(f"PMC full-text fetch error for {pmcid}: {str(e)}")
            return None

    def download_open_access_papers(
        self,
        pmids: List[str]
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """
        Download full-text for open-access papers, return PMIDs that need user upload.

        Uses local cache to avoid redundant downloads.

        Args:
            pmids: List of PubMed IDs

        Returns:
            Tuple of (downloaded_papers, paywalled_pmids)
        """
        downloaded_papers = []
        paywalled_pmids = []
        cache_hits = 0
        new_downloads = 0

        for pmid in pmids:
            # Check cache first
            cached_paper = self._get_cached_paper(pmid)
            if cached_paper:
                downloaded_papers.append(cached_paper)
                cache_hits += 1
                continue

            # Not in cache - need to download
            # Check PMC availability for this PMID
            pmc_map = self.check_pmc_availability([pmid])
            pmcid = pmc_map.get(pmid)

            # Try to download if we have a PMCID
            if pmcid:
                logger.info(f"Downloading PMID {pmid} from PMC (PMCID: {pmcid})")
                fulltext = self.fetch_pmc_fulltext(pmcid)  # Rate limited internally
                if fulltext:
                    # Parse full-text XML
                    parsed = self._parse_pmc_fulltext(fulltext, pmid, pmcid)
                    if parsed:
                        # Save to cache
                        self._save_paper_to_cache(parsed)
                        downloaded_papers.append(parsed)
                        new_downloads += 1
                        logger.info(f"✓ Successfully downloaded: PMID {pmid} (PMCID {pmcid})")
                        continue
                    else:
                        logger.warning(f"✗ Failed to parse PMC XML for PMID {pmid}")
                else:
                    logger.warning(f"✗ Failed to fetch PMC full-text for PMID {pmid}")

            # If no PMCID or download failed, mark as paywalled
            paywalled_pmids.append(pmid)
            logger.info(f"✗ Paywalled or unavailable: PMID {pmid} (no PMCID or download failed)")

        logger.info(
            f"Download summary: {len(downloaded_papers)} papers available "
            f"({cache_hits} from cache, {new_downloads} newly downloaded), "
            f"{len(paywalled_pmids)} need user upload"
        )

        return downloaded_papers, paywalled_pmids

    def download_paper(self, pmid: str, storage_path: Optional[Path] = None,
                      drug_name: Optional[str] = None, indication: Optional[str] = None) -> tuple[Optional[str], bool]:
        """
        Download a single paper and return the file path.

        Args:
            pmid: PubMed ID
            storage_path: Optional path to save paper (e.g., data/clinical_papers/drug/indication)
            drug_name: Optional drug name for filename
            indication: Optional indication for context

        Returns:
            Tuple of (file_path, is_cached)
            - file_path: Path to downloaded PDF or JSON, or None if paywalled
            - is_cached: True if loaded from cache, False if newly downloaded
        """
        # Determine save directory
        save_dir = storage_path if storage_path else self.cache_dir

        # Check cache first - check for both PDF and JSON in save_dir
        # Also check old cache location for backward compatibility
        pdf_cache_path = save_dir / f"{pmid}.pdf"
        json_cache_path = save_dir / f"{pmid}.json"
        old_json_cache = self.cache_dir / f"{pmid}.json"

        if pdf_cache_path.exists():
            logger.info(f"✓ Using cached PDF: PMID {pmid}")
            return (str(pdf_cache_path), True)

        if json_cache_path.exists():
            logger.info(f"✓ Using cached JSON: PMID {pmid}")
            return (str(json_cache_path), True)

        # Check old cache location and migrate if needed
        if old_json_cache.exists() and old_json_cache != json_cache_path:
            logger.info(f"✓ Found cached JSON in old location: PMID {pmid}")

            # If storage_path and drug_name provided, migrate to new location with proper naming
            if storage_path and drug_name:
                try:
                    # Load the old cached paper
                    import json
                    with open(old_json_cache, 'r', encoding='utf-8') as f:
                        paper_data = json.load(f)

                    # Save to new location with proper naming
                    new_file_path = self._save_paper_to_cache(paper_data, save_dir, drug_name)
                    if new_file_path:
                        logger.info(f"✓ Migrated paper to new location: {new_file_path}")
                        return (str(new_file_path), True)
                except Exception as e:
                    logger.warning(f"Failed to migrate paper {pmid}: {e}")

            # Fallback: return old location
            return (str(old_json_cache), True)

        # Not in cache - try to download
        pmc_map = self.check_pmc_availability([pmid])
        pmcid = pmc_map.get(pmid)

        if pmcid:
            logger.info(f"Downloading PMID {pmid} from PMC (PMCID: {pmcid})")

            # Download full-text XML and parse
            fulltext = self.fetch_pmc_fulltext(pmcid)
            if fulltext:
                parsed = self._parse_pmc_fulltext(fulltext, pmid, pmcid)
                if parsed:
                    # Save with proper naming if drug_name provided
                    file_path = self._save_paper_to_cache(parsed, save_dir, drug_name)
                    logger.info(f"✓ Successfully downloaded as JSON: PMID {pmid}")
                    return (str(file_path), False)

        # Paywalled or download failed
        return (None, False)

    def _try_alternative_download(self, pmid: str) -> Optional[Dict[str, Any]]:
        """
        Try alternative methods to download full-text.

        This attempts to fetch from PMC even without a known PMCID,
        as the API sometimes works with PMID directly.

        Args:
            pmid: PubMed ID

        Returns:
            Parsed paper data if successful, None otherwise
        """
        try:
            # Try fetching with PMID directly (sometimes works)
            fulltext = self.fetch_pmc_fulltext(pmid)
            if fulltext:
                parsed = self._parse_pmc_fulltext(fulltext, pmid, f"PMC-{pmid}")
                if parsed:
                    return parsed
        except:
            pass

        return None

    def _parse_pmc_fulltext(self, xml_text: str, pmid: str, pmcid: str) -> Optional[Dict[str, Any]]:
        """
        Parse PMC full-text XML into structured format with section detection and table validation.

        Args:
            xml_text: PMC full-text XML
            pmid: PubMed ID
            pmcid: PubMed Central ID

        Returns:
            Dictionary with paper content including sections and validated tables
        """
        try:
            root = ET.fromstring(xml_text)

            # Extract title
            title_elem = root.find(".//article-title")
            title = title_elem.text if title_elem is not None else "No title"

            # Extract authors
            authors = []
            for contrib in root.findall(".//contrib[@contrib-type='author']"):
                surname = contrib.find(".//surname")
                given_names = contrib.find(".//given-names")
                if surname is not None:
                    author = surname.text or ""
                    if given_names is not None:
                        author = f"{given_names.text} {author}"
                    authors.append(author)

            # Extract journal
            journal_elem = root.find(".//journal-title")
            if not journal_elem:
                journal_elem = root.find(".//journal-id")
            journal = journal_elem.text if journal_elem is not None else "Unknown journal"

            # Extract year and month
            year_elem = root.find(".//pub-date/year")
            if not year_elem:
                year_elem = root.find(".//year")
            year = year_elem.text if year_elem is not None else "Unknown"

            month_elem = root.find(".//pub-date/month")
            if not month_elem:
                month_elem = root.find(".//month")
            month = month_elem.text if month_elem is not None else "01"
            # Convert month name to number if needed
            if month and not month.isdigit():
                month_map = {
                    'jan': '01', 'january': '01',
                    'feb': '02', 'february': '02',
                    'mar': '03', 'march': '03',
                    'apr': '04', 'april': '04',
                    'may': '05',
                    'jun': '06', 'june': '06',
                    'jul': '07', 'july': '07',
                    'aug': '08', 'august': '08',
                    'sep': '09', 'september': '09',
                    'oct': '10', 'october': '10',
                    'nov': '11', 'november': '11',
                    'dec': '12', 'december': '12'
                }
                month = month_map.get(month.lower(), '01')

            # Extract DOI
            doi_elem = root.find(".//article-id[@pub-id-type='doi']")
            doi = doi_elem.text if doi_elem is not None else None

            # Extract additional metadata (based on tidypmc pmc_metadata approach)
            keywords = self._extract_keywords(root)
            volume = self._extract_volume(root)
            issue = self._extract_issue(root)
            pages = self._extract_pages(root)
            article_type = self._extract_article_type(root)
            pub_date = self._extract_pub_date(root)

            # Extract abstract
            abstract_elem = root.find(".//abstract")
            abstract = ""
            if abstract_elem is not None:
                abstract = " ".join(abstract_elem.itertext())

            # Extract full body text
            body_elem = root.find(".//body")
            body_text = ""
            if body_elem is not None:
                body_text = " ".join(body_elem.itertext())

            # Extract and validate tables
            tables = self._extract_and_validate_pmc_tables(root)

            # Combine all content
            full_content = f"{title}\n\nAbstract:\n{abstract}\n\nFull Text:\n{body_text}"

            # Debug logging
            logger.info(f"Parsed {pmcid}: title={len(title)} chars, abstract={len(abstract)} chars, body={len(body_text)} chars, total={len(full_content)} chars")
            logger.info(f"Metadata: authors={len(authors)}, journal={journal}, year={year}, doi={doi}, tables={len(tables)}")

            # Check if we actually got content
            if len(full_content) < 100 or (not abstract and not body_text):
                logger.warning(f"Very little content extracted from {pmcid}. XML might be in different format or empty.")
                # Try to extract at least the article text if XPath failed
                all_text = " ".join(root.itertext())
                if len(all_text) > len(full_content):
                    logger.info(f"Falling back to extracting all text from XML ({len(all_text)} chars)")
                    full_content = all_text

            # Extract sections directly from PMC XML structure (based on tidypmc pmc_text approach)
            sections = self._extract_sections_from_pmc_xml(root)

            # If no sections found in XML, try pattern-based detection on content
            if not sections:
                logger.debug(f"  No sections found in XML structure, trying pattern-based detection...")
                sections = self._detect_sections_in_pmc_content(full_content)

            # Extract captions (based on tidypmc pmc_caption approach)
            captions = self._extract_captions(root)

            # Extract references (based on tidypmc pmc_reference approach)
            references = self._extract_references(root)

            return {
                "paper_id": f"{pmid}_{pmcid}",
                "pmid": pmid,
                "pmcid": pmcid,
                "title": title,
                "authors": authors[:3] if authors else [],  # First 3 authors
                "journal": journal,
                "year": year,
                "month": month,  # Add month for filename generation
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "content": full_content,
                "sections": sections,
                "tables": tables,
                "captions": captions,  # NEW: Figure/table captions
                "references": references,  # NEW: References
                "metadata": {
                    "source": "PubMed Central",
                    "open_access": True,
                    "extraction_method": "PMC XML + tidypmc approach (text, table, caption, reference, metadata)",
                    "tables_validated": len(tables) > 0,
                    "sections_detected": len(sections),
                    "captions_extracted": sum(len(v) for v in captions.values()),
                    "references_extracted": len(references),
                    # Enhanced metadata (based on tidypmc pmc_metadata)
                    "keywords": keywords,
                    "volume": volume,
                    "issue": issue,
                    "pages": pages,
                    "article_type": article_type,
                    "pub_date": pub_date
                }
            }

        except Exception as e:
            logger.error(f"Error parsing PMC full-text for {pmcid}: {str(e)}")
            return None

    def _extract_and_validate_pmc_tables(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract tables from PMC XML and validate them.

        Only includes tables that have:
        - A label (Table 1, Table 2, etc.)
        - Actual table structure (not just text)
        - Both headers and data rows

        Args:
            root: XML root element

        Returns:
            List of validated tables
        """
        validated_tables = []

        for table_wrap in root.findall(".//table-wrap"):
            try:
                # Get table label
                table_label = table_wrap.find(".//label")
                label = table_label.text if table_label is not None else "Table"

                # Try to extract table structure
                table_elem = table_wrap.find(".//table")
                if table_elem is None:
                    logger.debug(f"  Skipping {label}: No <table> element found")
                    continue

                # Extract table content as markdown
                table_content = self._convert_pmc_table_to_markdown(table_elem)

                # Validate table structure
                if not self._is_valid_table(table_content, label):
                    logger.debug(f"  Skipping {label}: Invalid table structure")
                    continue

                # Add validated table
                validated_tables.append({
                    "label": label,
                    "content": table_content,
                    "validation_status": "valid"
                })
                logger.debug(f"  ✓ Validated {label}")

            except Exception as e:
                logger.debug(f"  Error processing table: {e}")
                continue

        return validated_tables

    def _convert_pmc_table_to_markdown(self, table_elem: ET.Element) -> str:
        """
        Convert PMC table XML to markdown format.

        Handles:
        - rowspan and colspan attributes
        - multiline headers
        - missing headers (uses first body row as header)
        - special characters (NO-BREAK spaces, etc.)

        Based on tidypmc R package approach.

        Args:
            table_elem: XML table element

        Returns:
            Markdown formatted table
        """
        # Parse header
        thead_rows = table_elem.findall(".//thead/tr")
        tbody_rows = table_elem.findall(".//tbody/tr")

        # If no tbody, try to use all tr elements
        if not tbody_rows:
            all_rows = table_elem.findall(".//tr")
            if len(all_rows) > len(thead_rows):
                tbody_rows = all_rows[len(thead_rows):]

        if not tbody_rows:
            return ""

        # Parse header (handle multiline headers with rowspan/colspan)
        headers = self._parse_table_header(thead_rows)

        # Parse body rows (handle rowspan/colspan)
        body_data = self._parse_table_body(tbody_rows, len(headers) if headers else None)

        if not body_data:
            return ""

        # If no headers, use first body row as header
        if not headers and body_data:
            headers = body_data[0]
            body_data = body_data[1:]

        # Convert to markdown
        markdown_lines = []

        # Add header (always present now)
        if headers:
            markdown_lines.append("| " + " | ".join(headers) + " |")
            markdown_lines.append("|" + "|".join(["---"] * len(headers)) + "|")

        # Add body rows
        for row in body_data:
            # Pad row to match header length
            if headers and len(row) < len(headers):
                row.extend([""] * (len(headers) - len(row)))
            markdown_lines.append("| " + " | ".join(row[:len(headers)] if headers else row) + " |")

        return "\n".join(markdown_lines)

    def _parse_table_header(self, thead_rows: list) -> list:
        """
        Parse table header rows, handling rowspan/colspan.

        If no thead rows provided, returns empty list (caller will use first body row as header).

        Args:
            thead_rows: List of <tr> elements from <thead>

        Returns:
            List of header cell values
        """
        if not thead_rows:
            return []

        # Single header row
        if len(thead_rows) == 1:
            return self._extract_row_cells(thead_rows[0])

        # Multiple header rows - need to handle rowspan/colspan
        # For simplicity, collapse all header rows into one
        all_headers = []
        for row in thead_rows:
            cells = self._extract_row_cells(row)
            all_headers.extend(cells)

        # Remove duplicates while preserving order
        seen = set()
        unique_headers = []
        for h in all_headers:
            if h not in seen:
                seen.add(h)
                unique_headers.append(h)

        return unique_headers if unique_headers else all_headers

    def _parse_table_body(self, tbody_rows: list, num_cols: int = None) -> list:
        """
        Parse table body rows, handling rowspan/colspan.

        Args:
            tbody_rows: List of <tr> elements from <tbody>
            num_cols: Expected number of columns (from header)

        Returns:
            List of rows, each row is a list of cell values
        """
        body_data = []

        for row in tbody_rows:
            cells = self._extract_row_cells(row)
            if cells:
                body_data.append(cells)

        return body_data

    def _extract_row_cells(self, row_elem: ET.Element) -> list:
        """
        Extract cells from a table row, handling special characters.

        Args:
            row_elem: <tr> element

        Returns:
            List of cell values
        """
        cells = []

        for cell in row_elem.findall(".//th") + row_elem.findall(".//td"):
            # Extract text from cell
            cell_text = " ".join(cell.itertext()).strip()

            # Handle special characters (NO-BREAK space, EN space, EM space)
            cell_text = cell_text.replace("\u00A0", " ")  # NO-BREAK space
            cell_text = cell_text.replace("\u2002", " ")  # EN space
            cell_text = cell_text.replace("\u2003", " ")  # EM space
            cell_text = cell_text.replace("\n", " ")      # Newlines
            cell_text = cell_text.replace("\t", " ")      # Tabs

            # Collapse multiple spaces
            cell_text = " ".join(cell_text.split())

            cells.append(cell_text)

        return cells

    def _is_valid_table(self, table_content: str, label: str) -> bool:
        """
        Validate that extracted table has proper structure.

        A valid table must have:
        - At least one data row
        - Multiple columns (not just text)
        - Markdown table format (with |)

        Args:
            table_content: Markdown formatted table
            label: Table label for logging

        Returns:
            True if table is valid, False otherwise
        """
        if not table_content or len(table_content.strip()) < 10:
            return False

        # Check for markdown table structure
        lines = table_content.strip().split("\n")

        # Need at least 2 lines: header/data and separator OR just data rows
        if len(lines) < 2:
            logger.debug(f"    {label}: Too few lines ({len(lines)})")
            return False

        # Check for markdown table markers (|)
        has_pipes = all("|" in line for line in lines)

        if not has_pipes:
            logger.debug(f"    {label}: Missing markdown table markers (|)")
            return False

        # Check that it has multiple columns
        first_row_cells = lines[0].split("|")
        num_columns = len([c for c in first_row_cells if c.strip()])

        if num_columns < 2:
            logger.debug(f"    {label}: Too few columns ({num_columns})")
            return False

        # Check that we have data rows (at least 2 rows total)
        if len(lines) < 2:
            logger.debug(f"    {label}: No data rows")
            return False

        return True

    def _detect_sections_in_pmc_content(self, content: str) -> Dict[str, Dict[str, Any]]:
        """
        Detect sections in PMC content.

        Args:
            content: Full paper content

        Returns:
            Dictionary of detected sections
        """
        try:
            from src.utils.section_detector import SectionDetector

            detector = SectionDetector(client=None)  # Use pattern matching only
            sections_dict = detector.detect_sections(content, use_ai_fallback=False)

            # Convert to serializable format
            sections = {}
            for section_name, section_obj in sections_dict.items():
                section_content = content[section_obj.start_pos:section_obj.end_pos] if section_obj.end_pos else content[section_obj.start_pos:]
                sections[section_name] = {
                    "title": section_obj.title,
                    "start_pos": section_obj.start_pos,
                    "end_pos": section_obj.end_pos,
                    "content_length": len(section_content)
                }

            logger.debug(f"  Detected {len(sections)} sections: {list(sections.keys())}")
            return sections

        except Exception as e:
            logger.debug(f"  Section detection failed: {e}")
            return {}

    def _extract_keywords(self, root: ET.Element) -> List[str]:
        """Extract keywords from PMC XML"""
        keywords = []
        for kwd in root.findall(".//kwd"):
            kwd_text = " ".join(kwd.itertext()).strip()
            if kwd_text:
                keywords.append(kwd_text)
        return keywords

    def _extract_volume(self, root: ET.Element) -> Optional[str]:
        """Extract volume from PMC XML"""
        volume_elem = root.find(".//volume")
        return volume_elem.text if volume_elem is not None else None

    def _extract_issue(self, root: ET.Element) -> Optional[str]:
        """Extract issue from PMC XML"""
        issue_elem = root.find(".//issue")
        return issue_elem.text if issue_elem is not None else None

    def _extract_pages(self, root: ET.Element) -> Optional[str]:
        """Extract page numbers from PMC XML"""
        fpage = root.find(".//fpage")
        lpage = root.find(".//lpage")

        if fpage is not None and lpage is not None:
            return f"{fpage.text}-{lpage.text}"
        elif fpage is not None:
            return fpage.text
        elif lpage is not None:
            return lpage.text
        return None

    def _extract_article_type(self, root: ET.Element) -> Optional[str]:
        """Extract article type from PMC XML"""
        article = root.find(".//article")
        if article is not None:
            return article.get("article-type")
        return None

    def _extract_pub_date(self, root: ET.Element) -> Optional[str]:
        """Extract publication date from PMC XML"""
        pub_date = root.find(".//pub-date")
        if pub_date is not None:
            year = pub_date.find(".//year")
            month = pub_date.find(".//month")
            day = pub_date.find(".//day")

            date_parts = []
            if year is not None and year.text:
                date_parts.append(year.text)
            if month is not None and month.text:
                date_parts.append(month.text)
            if day is not None and day.text:
                date_parts.append(day.text)

            if date_parts:
                return "-".join(date_parts)
        return None

    def _extract_captions(self, root: ET.Element) -> Dict[str, List[Dict[str, Any]]]:
        """
        Extract figure, table and supplementary material captions from PMC XML.

        Based on tidypmc's pmc_caption approach:
        - Extracts captions from <fig>, <table-wrap>, and <supplementary-material>
        - Maintains association with parent element
        - Splits captions into sentences

        Args:
            root: XML root element

        Returns:
            Dictionary with 'figures', 'tables', 'supplementary' keys containing captions
        """
        captions = {
            'figures': [],
            'tables': [],
            'supplementary': []
        }

        # Extract figure captions
        for fig in root.findall(".//fig"):
            label_elem = fig.find(".//label")
            caption_elem = fig.find(".//caption")

            if caption_elem is not None:
                label = label_elem.text if label_elem is not None else "Figure"
                caption_text = " ".join(caption_elem.itertext()).strip()

                if caption_text:
                    captions['figures'].append({
                        'label': label,
                        'caption': caption_text
                    })

        # Extract table captions
        for table_wrap in root.findall(".//table-wrap"):
            label_elem = table_wrap.find(".//label")
            caption_elem = table_wrap.find(".//caption")

            if caption_elem is not None:
                label = label_elem.text if label_elem is not None else "Table"
                caption_text = " ".join(caption_elem.itertext()).strip()

                if caption_text:
                    captions['tables'].append({
                        'label': label,
                        'caption': caption_text
                    })

        # Extract supplementary material captions
        for supp in root.findall(".//supplementary-material"):
            label_elem = supp.find(".//label")
            caption_elem = supp.find(".//caption")

            if caption_elem is not None:
                label = label_elem.text if label_elem is not None else "Supplementary Material"
                caption_text = " ".join(caption_elem.itertext()).strip()

                if caption_text:
                    captions['supplementary'].append({
                        'label': label,
                        'caption': caption_text
                    })

        return captions

    def _extract_references(self, root: ET.Element) -> List[Dict[str, Any]]:
        """
        Extract references from PMC XML.

        Based on tidypmc's pmc_reference approach:
        - Extracts reference metadata from <back> section
        - Parses author, title, journal, year, DOI
        - Returns structured reference data

        Args:
            root: XML root element

        Returns:
            List of reference dictionaries
        """
        references = []

        # Find all references in back section
        for ref in root.findall(".//back/ref-list/ref"):
            ref_id = ref.get("id", "")

            # Extract mixed-citation or element-citation
            citation = ref.find(".//mixed-citation") or ref.find(".//element-citation")

            if citation is None:
                continue

            # Extract authors
            authors = []
            for person in citation.findall(".//person-group[@person-group-type='author']/name"):
                surname = person.find(".//surname")
                given_names = person.find(".//given-names")

                if surname is not None:
                    author = surname.text or ""
                    if given_names is not None:
                        author = f"{given_names.text} {author}"
                    authors.append(author)

            # Extract article title
            article_title_elem = citation.find(".//article-title")
            article_title = article_title_elem.text if article_title_elem is not None else ""

            # Extract source (journal)
            source_elem = citation.find(".//source")
            source = source_elem.text if source_elem is not None else ""

            # Extract year
            year_elem = citation.find(".//year")
            year = year_elem.text if year_elem is not None else ""

            # Extract volume
            volume_elem = citation.find(".//volume")
            volume = volume_elem.text if volume_elem is not None else ""

            # Extract pages
            fpage_elem = citation.find(".//fpage")
            lpage_elem = citation.find(".//lpage")
            pages = ""
            if fpage_elem is not None and lpage_elem is not None:
                pages = f"{fpage_elem.text}-{lpage_elem.text}"
            elif fpage_elem is not None:
                pages = fpage_elem.text

            # Extract DOI
            doi_elem = citation.find(".//pub-id[@pub-id-type='doi']")
            doi = doi_elem.text if doi_elem is not None else ""

            # Extract PMID
            pmid_elem = citation.find(".//pub-id[@pub-id-type='pmid']")
            pmid = pmid_elem.text if pmid_elem is not None else ""

            # Only add if we have meaningful content
            if article_title or source:
                references.append({
                    'ref_id': ref_id,
                    'authors': authors,
                    'title': article_title,
                    'journal': source,
                    'year': year,
                    'volume': volume,
                    'pages': pages,
                    'doi': doi,
                    'pmid': pmid
                })

        return references

    def _extract_sections_from_pmc_xml(self, root: ET.Element) -> Dict[str, Dict[str, Any]]:
        """
        Extract sections directly from PMC XML structure.

        Based on tidypmc's pmc_text function approach:
        - Extracts <sec> elements with <title> tags
        - Builds full path to subsection titles
        - Extracts all paragraphs within each section

        Args:
            root: XML root element

        Returns:
            Dictionary of sections with content
        """
        sections = {}

        # Find all top-level sections
        for sec in root.findall(".//sec"):
            # Get section title
            title_elem = sec.find(".//title")
            if title_elem is None:
                continue

            title = " ".join(title_elem.itertext()).strip()
            if not title:
                continue

            # Extract all paragraphs in this section
            paragraphs = []
            for p in sec.findall(".//p"):
                p_text = " ".join(p.itertext()).strip()
                if p_text:
                    paragraphs.append(p_text)

            # Extract subsections
            subsections = []
            for subsec in sec.findall(".//sec"):
                subsec_title_elem = subsec.find(".//title")
                if subsec_title_elem is not None:
                    subsec_title = " ".join(subsec_title_elem.itertext()).strip()
                    if subsec_title and subsec_title != title:
                        subsections.append(subsec_title)

            # Create section key (normalize title)
            section_key = title.lower().replace(" ", "_")

            # Store section
            if paragraphs or subsections:
                sections[section_key] = {
                    "title": title,
                    "content": "\n\n".join(paragraphs),
                    "subsections": subsections,
                    "paragraph_count": len(paragraphs)
                }

        logger.debug(f"  Extracted {len(sections)} sections from PMC XML: {list(sections.keys())}")
        return sections

    def close(self):
        """Close the HTTP session"""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_tool_definition() -> dict:
    """
    Get tool definition for Claude tool use.

    Returns:
        Tool definition dictionary
    """
    return {
        "name": "search_pubmed",
        "description": "Search PubMed biomedical literature for scientific publications about drugs, diseases, clinical trials, mechanisms of action, or therapeutic targets. Returns article titles, abstracts, and citations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (drug name, disease, mechanism, target protein, etc.)"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of articles to return (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    }
