"""
Header Extractor for Clinical Trial Tables

Extracts and normalizes table headers to standard clinical terms.
Helps identify real data tables vs text extraction errors.
"""

import re
from typing import List, Dict, Optional


class HeaderExtractor:
    """
    Extract and normalize table headers.
    
    Maps diverse header formats to standard clinical terms.
    """
    
    # Standard header mappings
    HEADER_MAPPINGS = {
        'age': [
            'age', 'age (years)', 'age (y)', 'age (yrs)', 'age years',
            'mean age', 'median age', 'age range'
        ],
        'sex': [
            'sex', 'gender', 'male/female', 'm/f', 'male', 'female'
        ],
        'n': [
            'n', 'n (%)', 'number', 'count', 'sample size', 'n=',
            'total n', 'number of patients'
        ],
        'n_percent': [
            'n (%)', 'n(%)', 'n %', 'number (%)', 'count (%)',
            'n/total', 'n (percent)'
        ],
        'mean_sd': [
            'mean ± sd', 'mean (sd)', 'mean ± std', 'mean (std)',
            'mean ± sem', 'mean (sem)', 'mean ± se'
        ],
        'median_range': [
            'median (range)', 'median (min-max)', 'median (iqr)',
            'median (q1-q3)'
        ],
        'easi': [
            'easi', 'easi score', 'easi-75', 'easi response',
            'eczema area and severity index'
        ],
        'viga_ad': [
            'viga-ad', 'viga ad', 'validated investigator global assessment',
            'investigator global assessment'
        ],
        'bsa': [
            'bsa', 'bsa (%)', 'body surface area', 'body surface area (%)',
            '%bsa', 'percent bsa'
        ],
        'pruritus': [
            'pruritus', 'pruritus score', 'pp-nrs', 'peak pruritus nrs',
            'itch score'
        ],
        'teae': [
            'teae', 'adverse event', 'adverse events', 'ae', 'aes',
            'treatment-emergent adverse event'
        ],
        'sae': [
            'sae', 'serious adverse event', 'serious adverse events',
            'serious ae'
        ],
        'cmax': [
            'cmax', 'c_max', 'c max', 'maximum concentration',
            'peak concentration'
        ],
        'tmax': [
            'tmax', 't_max', 't max', 'time to maximum concentration',
            'time to peak'
        ],
        'auc': [
            'auc', 'auc0-inf', 'auc0-t', 'area under curve',
            'area under the curve'
        ],
        'race': [
            'race', 'ethnicity', 'ethnic', 'race/ethnicity',
            'racial/ethnic'
        ],
        'baseline': [
            'baseline', 'baseline characteristics', 'baseline value',
            'baseline score'
        ],
        'change': [
            'change', 'change from baseline', 'delta', 'Δ',
            'change (delta)', 'improvement'
        ],
        'percent_change': [
            '% change', 'percent change', '% change from baseline',
            'percent improvement'
        ]
    }
    
    def __init__(self):
        """Initialize HeaderExtractor."""
        # Build reverse mapping for faster lookup
        self.reverse_mapping = {}
        for standard_name, variants in self.HEADER_MAPPINGS.items():
            for variant in variants:
                self.reverse_mapping[variant.lower()] = standard_name
    
    def extract_headers(self, table_content: str) -> List[str]:
        """
        Extract headers from table content.
        
        Assumes first row is headers (common in markdown tables).
        
        Args:
            table_content: Table content string
            
        Returns:
            List of header strings
        """
        lines = table_content.split('\n')
        
        if not lines:
            return []
        
        # Get first line
        first_line = lines[0].strip()
        
        # Split by common delimiters
        if '|' in first_line:
            headers = [h.strip() for h in first_line.split('|')]
        elif '\t' in first_line:
            headers = [h.strip() for h in first_line.split('\t')]
        else:
            # Try splitting by multiple spaces
            headers = [h.strip() for h in re.split(r'\s{2,}', first_line)]
        
        # Remove empty headers
        headers = [h for h in headers if h]
        
        return headers
    
    def normalize_headers(self, headers: List[str]) -> List[str]:
        """
        Normalize headers to standard clinical terms.
        
        Args:
            headers: List of header strings
            
        Returns:
            List of normalized header names
        """
        normalized = []
        
        for header in headers:
            normalized_header = self._normalize_single(header)
            normalized.append(normalized_header)
        
        return normalized
    
    def _normalize_single(self, header: str) -> str:
        """
        Normalize a single header.
        
        Args:
            header: Header string
            
        Returns:
            Normalized header name
        """
        if not header:
            return 'unknown'
        
        # Clean up header
        header_clean = header.strip().lower()
        
        # Remove common suffixes
        header_clean = re.sub(r'\s*\(.*?\)\s*', '', header_clean)  # Remove parentheses
        header_clean = re.sub(r'\s*\[.*?\]\s*', '', header_clean)  # Remove brackets
        header_clean = header_clean.strip()
        
        # Check if it's a known variant
        if header_clean in self.reverse_mapping:
            return self.reverse_mapping[header_clean]
        
        # Try partial matching
        for variant, standard_name in self.reverse_mapping.items():
            if variant in header_clean or header_clean in variant:
                return standard_name
        
        # If no match, return cleaned header
        return header_clean.replace(' ', '_').lower()
    
    def is_valid_header_set(self, headers: List[str]) -> bool:
        """
        Check if headers are meaningful (not generic 0, 1, 2, etc.).
        
        Args:
            headers: List of headers
            
        Returns:
            True if headers are meaningful
        """
        if not headers:
            return False
        
        # Check if all headers are generic numbers
        if all(h.isdigit() for h in headers):
            return False
        
        # Check if headers are too short (likely generic)
        if all(len(h) <= 2 for h in headers):
            return False
        
        # Check if at least some headers are meaningful
        meaningful_count = 0
        for header in headers:
            normalized = self._normalize_single(header)
            # If normalized to something other than generic, it's meaningful
            if normalized not in ['unknown', '0', '1', '2', '3', '4', '5']:
                meaningful_count += 1
        
        # At least 50% of headers should be meaningful
        return meaningful_count >= len(headers) * 0.5
    
    def get_header_quality_score(self, headers: List[str]) -> float:
        """
        Score header quality (0-1).
        
        Args:
            headers: List of headers
            
        Returns:
            Quality score 0-1
        """
        if not headers:
            return 0.0
        
        score = 0.0
        
        # Check for meaningful headers
        meaningful_count = 0
        for header in headers:
            normalized = self._normalize_single(header)
            if normalized not in ['unknown', '0', '1', '2', '3', '4', '5']:
                meaningful_count += 1
        
        # 50% of score from meaningful headers
        score += (meaningful_count / len(headers)) * 0.5
        
        # 25% from header length (longer = better)
        avg_length = sum(len(h) for h in headers) / len(headers)
        score += min(avg_length / 20, 1.0) * 0.25
        
        # 25% from diversity (different headers = better)
        unique_headers = len(set(h.lower() for h in headers))
        score += (unique_headers / len(headers)) * 0.25
        
        return min(score, 1.0)
    
    def extract_and_validate_headers(self, table_content: str) -> Dict:
        """
        Extract headers and validate them.
        
        Args:
            table_content: Table content
            
        Returns:
            Dict with headers, normalized, is_valid, quality_score
        """
        headers = self.extract_headers(table_content)
        normalized = self.normalize_headers(headers)
        is_valid = self.is_valid_header_set(headers)
        quality_score = self.get_header_quality_score(headers)
        
        return {
            'headers': headers,
            'normalized': normalized,
            'is_valid': is_valid,
            'quality_score': quality_score
        }

