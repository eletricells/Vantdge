"""
Trial Name Extractor for PaperScope 2.0

Sophisticated trial name extraction with validation, confidence scoring,
and false positive filtering.
"""

import re
import logging
from dataclasses import dataclass
from collections import defaultdict
from typing import Set, Dict, List

logger = logging.getLogger(__name__)


@dataclass
class TrialNameCandidate:
    """Candidate trial name with metadata"""
    name: str
    count: int
    contexts: List[str]
    confidence: float
    pattern_matched: str


class TrialNameExtractor:
    """
    Sophisticated trial name extraction with validation.
    
    Features:
    - Multiple pattern types
    - Context-aware validation
    - Confidence scoring
    - False positive filtering
    """
    
    # Comprehensive pattern dictionary
    PATTERNS = {
        'standard': r'\b([A-Z]{3,}-\d+[A-Z]?)\b',              # TULIP-1, EXTEND-2A
        'word_number': r'\b([A-Z]{3,}\d+[A-Z]?)\b',            # MUSE2, REACH3
        'delivery_method': r'\b([A-Z]{3,}-(?:SC|IV|PO|IM|TD|SubQ))\b',  # TRIAL-SC
        'extension': r'\b([A-Z]{3,}-(?:LTE|OLE|EXTEND|EXT))\b',  # TRIAL-LTE
        'multi_word': r'\b([A-Z]{2,}\s+[A-Z]{2,}(?:-\d+)?)\b',  # CLEAR OUTCOMES, CARE MS-1
        'phase_suffix': r'\b([A-Z]{3,}-[23][AB]?)\b',          # TRIAL-2A, TRIAL-3B
    }
    
    # Comprehensive exclusion lists
    EXCLUSIONS = {
        'generic_terms': {
            'STUDY', 'TRIAL', 'PHASE', 'OPEN', 'LABEL', 'EXTENSION',
            'FOLLOWUP', 'CONTINUATION', 'LONG', 'TERM', 'DOUBLE',
            'BLIND', 'PLACEBO', 'CONTROLLED', 'RANDOMIZED', 'WEEKS'
        },
        'medical_abbrev': {
            'SLE', 'RA', 'MS', 'COPD', 'CHF', 'CAD', 'CKD', 'ESRD',
            'NSCLC', 'SCLC', 'NHL', 'CLL', 'AML', 'ALL', 'CML'
        },
        'regulatory': {
            'FDA', 'EMA', 'ICH', 'IRB', 'IND', 'NDA', 'BLA', 'REMS',
            'CDER', 'PDUFA', 'ANDA'
        },
        'journals': {
            'NEJM', 'JAMA', 'BMJ', 'LANCET', 'NATURE', 'SCIENCE'
        },
        'statistical': {
            'ITT', 'PP', 'MITT', 'FAS', 'PPS', 'CI', 'HR', 'OR', 'RR'
        },
        'adverse_events': {
            'AE', 'SAE', 'TEAE', 'AESI', 'SUSAR'
        }
    }
    
    # Context patterns that suggest real trial names
    POSITIVE_CONTEXTS = [
        r'the\s+\w+\s+trial',
        r'the\s+\w+\s+study',
        r'\w+\s+\(NCT\d+\)',
        r'results?\s+from\s+\w+',
        r'data\s+from\s+\w+',
        r'in\s+the\s+\w+\s+trial',
        r'phase\s+[123]\s+\w+',
    ]
    
    @classmethod
    def extract_from_text(
        cls,
        text: str,
        min_confidence: float = 0.6
    ) -> Set[str]:
        """
        Extract validated trial names from text.
        
        Args:
            text: Text to search
            min_confidence: Minimum confidence threshold (0.0-1.0)
            
        Returns:
            Set of validated trial names
        """
        # Stage 1: Extract all candidates
        candidates = cls._extract_candidates(text)
        
        # Stage 2: Score candidates
        scored_candidates = cls._score_candidates(candidates, text)
        
        # Stage 3: Filter by confidence
        validated = {
            name for name, candidate in scored_candidates.items()
            if candidate.confidence >= min_confidence
        }
        
        return validated
    
    @classmethod
    def _extract_candidates(cls, text: str) -> Dict[str, TrialNameCandidate]:
        """Extract all potential trial names"""
        text_upper = text.upper()
        candidates = defaultdict(lambda: {
            'count': 0,
            'contexts': [],
            'pattern': None
        })
        
        for pattern_name, pattern in cls.PATTERNS.items():
            for match in re.finditer(pattern, text_upper):
                name = match.group(1)
                
                # Skip if in exclusion lists
                if cls._is_excluded(name):
                    continue
                
                # Extract context (50 chars before and after)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]
                
                candidates[name]['count'] += 1
                candidates[name]['contexts'].append(context)
                candidates[name]['pattern'] = pattern_name

        # Convert to TrialNameCandidate objects
        return {
            name: TrialNameCandidate(
                name=name,
                count=data['count'],
                contexts=data['contexts'],
                confidence=0.0,  # Will be set in scoring
                pattern_matched=data['pattern']
            )
            for name, data in candidates.items()
        }

    @classmethod
    def _score_candidates(
        cls,
        candidates: Dict[str, TrialNameCandidate],
        full_text: str
    ) -> Dict[str, TrialNameCandidate]:
        """
        Score candidates based on multiple factors.

        Scoring factors:
        - Frequency of occurrence (0-0.3)
        - Positive context patterns (0-0.4)
        - Pattern type reliability (0-0.2)
        - Length and format (0-0.1)
        """
        for name, candidate in candidates.items():
            score = 0.0

            # Factor 1: Frequency (0-0.3)
            # More mentions = higher confidence
            freq_score = min(candidate.count / 5.0, 1.0) * 0.3
            score += freq_score

            # Factor 2: Positive contexts (0-0.4)
            # Check if appears in trial-suggesting contexts
            context_score = 0.0
            for context in candidate.contexts:
                for pattern in cls.POSITIVE_CONTEXTS:
                    if re.search(pattern, context, re.IGNORECASE):
                        context_score = 0.4
                        break
                if context_score > 0:
                    break
            score += context_score

            # Factor 3: Pattern reliability (0-0.2)
            # Some patterns are more reliable than others
            pattern_scores = {
                'standard': 0.2,       # TULIP-1 is very reliable
                'extension': 0.2,      # TRIAL-LTE is very reliable
                'multi_word': 0.15,    # CLEAR OUTCOMES fairly reliable
                'delivery_method': 0.15,  # TRIAL-SC fairly reliable
                'word_number': 0.1,    # MUSE2 less reliable
                'phase_suffix': 0.1,   # TRIAL-2A less reliable
            }
            score += pattern_scores.get(candidate.pattern_matched, 0.0)

            # Factor 4: Format quality (0-0.1)
            # Length and structure affect confidence
            if 3 <= len(name) <= 15:  # Reasonable length
                score += 0.05
            if re.search(r'\d', name):  # Contains number
                score += 0.05

            candidate.confidence = min(score, 1.0)

        return candidates

    @classmethod
    def _is_excluded(cls, name: str) -> bool:
        """Check if name should be excluded"""
        # Check all exclusion lists
        for exclusion_set in cls.EXCLUSIONS.values():
            if name in exclusion_set:
                return True

        # Additional checks
        if len(name) < 3:  # Too short
            return True
        if name.isdigit():  # Pure numbers
            return True

        return False

