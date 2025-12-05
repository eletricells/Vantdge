"""
Drugs.com Web Scraper for FDA Approval Dates

Scrapes drug approval timeline from Drugs.com history pages.
Includes rate limiting and caching to be respectful to the website.

Example URL: https://www.drugs.com/history/humira.html
"""
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from typing import List, Dict, Optional
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)


class DrugsComScraper:
    """
    Web scraper for Drugs.com FDA approval timeline.

    Features:
    - Rate limiting (1 request per second)
    - Caching (saves raw HTML and parsed data)
    - Graceful error handling
    - Fuzzy indication matching
    """

    def __init__(self, cache_dir: str = "./data/drugs_com_cache"):
        """
        Initialize Drugs.com scraper.

        Args:
            cache_dir: Directory to store cached HTML and parsed data
        """
        self.base_url = "https://www.drugs.com/history"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.last_request_time = 0
        self.rate_limit_seconds = 1.0  # 1 request per second

        # User agent to identify ourselves
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; PharmaPipelineBot/1.0; Research purposes)"
        }

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_seconds:
            sleep_time = self.rate_limit_seconds - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def _get_cache_path(self, drug_name: str, cache_type: str = "html") -> Path:
        """
        Get cache file path for a drug.

        Args:
            drug_name: Drug name
            cache_type: "html" or "parsed"

        Returns:
            Path to cache file
        """
        safe_name = re.sub(r'[^\w\-]', '_', drug_name.lower())
        extension = "html" if cache_type == "html" else "json"
        return self.cache_dir / f"{safe_name}.{extension}"

    def _load_from_cache(self, drug_name: str) -> Optional[List[Dict]]:
        """
        Load parsed approval timeline from cache.

        Args:
            drug_name: Drug name

        Returns:
            Cached data or None
        """
        cache_file = self._get_cache_path(drug_name, cache_type="parsed")

        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                logger.info(f"Loaded cached approval data for {drug_name}")
                return data
            except Exception as e:
                logger.warning(f"Failed to load cache for {drug_name}: {e}")

        return None

    def _save_to_cache(self, drug_name: str, data: List[Dict]):
        """
        Save parsed approval timeline to cache.

        Args:
            drug_name: Drug name
            data: Parsed approval timeline
        """
        cache_file = self._get_cache_path(drug_name, cache_type="parsed")

        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            logger.debug(f"Saved approval data to cache for {drug_name}")
        except Exception as e:
            logger.warning(f"Failed to save cache for {drug_name}: {e}")

    def _fetch_html(self, drug_name: str) -> Optional[str]:
        """
        Fetch HTML from Drugs.com or cache.

        Args:
            drug_name: Drug name (will be URL-encoded)

        Returns:
            HTML content or None
        """
        # Check HTML cache first
        html_cache = self._get_cache_path(drug_name, cache_type="html")

        if html_cache.exists():
            try:
                with open(html_cache, 'r', encoding='utf-8') as f:
                    html = f.read()
                logger.info(f"Loaded HTML from cache for {drug_name}")
                return html
            except Exception as e:
                logger.warning(f"Failed to load HTML cache: {e}")

        # Fetch from web
        url_name = drug_name.lower().replace(' ', '-')
        url = f"{self.base_url}/{url_name}.html"

        logger.info(f"Fetching {url}")

        self._rate_limit()

        try:
            response = requests.get(url, headers=self.headers, timeout=10)

            if response.status_code == 404:
                logger.warning(f"Page not found for {drug_name}: {url}")
                return None

            response.raise_for_status()

            html = response.text

            # Save to cache
            try:
                with open(html_cache, 'w', encoding='utf-8') as f:
                    f.write(html)
                logger.debug(f"Saved HTML to cache for {drug_name}")
            except Exception as e:
                logger.warning(f"Failed to save HTML cache: {e}")

            return html

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def _parse_approval_timeline(self, html: str, drug_name: str) -> List[Dict]:
        """
        Parse approval timeline from Drugs.com HTML.

        Args:
            html: HTML content
            drug_name: Drug name (for logging)

        Returns:
            List of approval events
        """
        soup = BeautifulSoup(html, 'html.parser')

        approvals = []

        # Pattern 1: Find approval table (most common format)
        # Look for tables with approval rows
        tables = soup.find_all('table')

        for table in tables:
            rows = table.find_all('tr')

            for row in rows:
                cells = row.find_all('td')

                # Skip header rows
                if len(cells) < 2:
                    continue

                # First cell should have date
                date_cell = cells[0]
                date_text = date_cell.get_text().strip()

                # Second cell should have approval info
                info_cell = cells[1]
                info_text = info_cell.get_text()

                # Check if this row is about an approval
                if not re.search(r'approval', info_text, re.IGNORECASE):
                    continue

                # Try to parse the date
                # Format examples: "Feb 24, 2021", "Dec 31, 2002"
                date_patterns = [
                    r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # "Feb 24, 2021"
                    r'(\w+)\s+(\d{4})',  # "Feb 2021"
                ]

                date_obj = None
                for pattern in date_patterns:
                    date_match = re.search(pattern, date_text)
                    if date_match:
                        try:
                            if len(date_match.groups()) == 3:
                                # Has day
                                month, day, year = date_match.groups()
                                date_str = f"{month} {day}, {year}"
                                date_obj = datetime.strptime(date_str, '%b %d, %Y')
                            else:
                                # No day, just month and year
                                month, year = date_match.groups()
                                date_str = f"{month} 1, {year}"  # Default to 1st
                                date_obj = datetime.strptime(date_str, '%b %d, %Y')
                            break
                        except ValueError:
                            try:
                                # Try full month name
                                if len(date_match.groups()) == 3:
                                    month, day, year = date_match.groups()
                                    date_str = f"{month} {day}, {year}"
                                    date_obj = datetime.strptime(date_str, '%B %d, %Y')
                                else:
                                    month, year = date_match.groups()
                                    date_str = f"{month} 1, {year}"
                                    date_obj = datetime.strptime(date_str, '%B %d, %Y')
                                break
                            except ValueError:
                                continue

                if not date_obj:
                    logger.debug(f"Could not parse date: {date_text}")
                    continue

                # Extract indication from link text or info text
                link = info_cell.find('a')
                if link:
                    link_text = link.get_text()
                else:
                    link_text = info_text

                # Extract indication using common patterns
                indication = None
                patterns = [
                    r'(?:for|to treat|in)\s+(?:the treatment of\s+)?(?:patients? (?:with|living with)\s+)?([^.]+?)(?:\s+receiving|\s+who|\.|$)',
                    r'(?:Pediatric Patients|Adults) (?:with|Living with)\s+([^.]+)',
                    r'([\w\s]+arthritis)',
                    r'([\w\s]+disease)',
                    r'(psoriasis)',
                    r'(uveitis)',
                    r'(hidradenitis suppurativa)',
                ]

                for pattern in patterns:
                    match = re.search(pattern, link_text, re.IGNORECASE)
                    if match:
                        indication = match.group(1).strip()
                        # Clean up indication
                        indication = re.sub(r'\s+', ' ', indication)
                        indication = indication.lower()
                        break

                if not indication:
                    # Extract first capitalized phrase as indication
                    cap_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)', link_text)
                    if cap_match:
                        indication = cap_match.group(1).lower()
                    else:
                        indication = "unknown indication"

                approvals.append({
                    'indication': indication,
                    'approval_date': date_obj.strftime('%Y-%m-%d'),
                    'year': date_obj.year,
                    'confidence': 'high',
                    'source_text': link_text[:100]  # Keep for debugging
                })

        # Pattern 2: Fallback - look for approval mentions in text
        if not approvals:
            all_text = soup.get_text()
            approval_pattern = r'(\w+ \d{1,2}, \d{4})[:\s\-]+.*?FDA.*?approv.*?(?:for|to treat)\s+([^.]+)'
            matches = re.findall(approval_pattern, all_text, re.IGNORECASE)

            for date_str, indication in matches:
                try:
                    date_obj = datetime.strptime(date_str, '%B %d, %Y')
                    approvals.append({
                        'indication': indication.strip().lower(),
                        'approval_date': date_obj.strftime('%Y-%m-%d'),
                        'year': date_obj.year,
                        'confidence': 'medium'
                    })
                except ValueError:
                    continue

            if approvals:
                logger.info(f"Found {len(approvals)} approvals via text search for {drug_name}")

        logger.info(f"Parsed {len(approvals)} approval events for {drug_name}")
        return approvals

    def get_approval_timeline(self, drug_name: str, use_cache: bool = True) -> List[Dict]:
        """
        Get FDA approval timeline for a drug.

        Args:
            drug_name: Drug name (brand or generic)
            use_cache: Use cached data if available

        Returns:
            List of approval events:
            [
                {
                    'indication': 'rheumatoid arthritis',
                    'approval_date': '2002-12-31',
                    'year': 2002,
                    'confidence': 'high'
                },
                ...
            ]

        Example:
            >>> scraper = DrugsComScraper()
            >>> timeline = scraper.get_approval_timeline("Humira")
            >>> print(f"Found {len(timeline)} approvals")
        """
        # Check cache
        if use_cache:
            cached = self._load_from_cache(drug_name)
            if cached is not None:
                return cached

        # Fetch HTML
        html = self._fetch_html(drug_name)

        if not html:
            logger.warning(f"No HTML content for {drug_name}")
            return []

        # Parse timeline
        approvals = self._parse_approval_timeline(html, drug_name)

        # Save to cache
        if approvals:
            self._save_to_cache(drug_name, approvals)

        return approvals

    def clear_cache(self, drug_name: Optional[str] = None):
        """
        Clear cache for a specific drug or all drugs.

        Args:
            drug_name: Drug name (clears all if None)
        """
        if drug_name:
            html_cache = self._get_cache_path(drug_name, cache_type="html")
            parsed_cache = self._get_cache_path(drug_name, cache_type="parsed")

            html_cache.unlink(missing_ok=True)
            parsed_cache.unlink(missing_ok=True)

            logger.info(f"Cleared cache for {drug_name}")
        else:
            # Clear all
            for file in self.cache_dir.iterdir():
                file.unlink()
            logger.info("Cleared all cache")


# Convenience function
def get_drug_approvals(drug_name: str) -> List[Dict]:
    """
    Convenience function to get approval timeline for a drug.

    Args:
        drug_name: Drug name

    Returns:
        List of approval events
    """
    scraper = DrugsComScraper()
    return scraper.get_approval_timeline(drug_name)
