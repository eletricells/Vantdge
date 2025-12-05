"""
Constants for Clinical Data Extraction Agent.

Centralizes magic numbers and configuration values for maintainability.
"""

# ==================== CONTENT TRUNCATION LIMITS ====================
# Paper content truncation for different stages
CONTENT_TRUNCATION_SHORT = 30_000  # Used in most stages
CONTENT_TRUNCATION_LONG = 50_000   # Used in complex stages
CONTENT_TRUNCATION_MAX = 80_000    # Maximum content length

# ==================== FIGURE EXTRACTION THRESHOLDS ====================
# Minimum dimensions for figure extraction
MIN_FIGURE_WIDTH = 200   # Pixels
MIN_FIGURE_HEIGHT = 200  # Pixels

# ==================== THINKING BUDGETS BY STAGE ====================
# Token budgets for extended thinking in each stage
THINKING_BUDGET_SECTIONS = 5_000      # Stage 1: Section identification
THINKING_BUDGET_MEDICATIONS = 3_000   # Stage 3: Prior medications
THINKING_BUDGET_DISEASE = 3_000       # Stage 4: Disease-specific baseline
THINKING_BUDGET_EFFICACY = 5_000      # Stage 5: Efficacy endpoints
THINKING_BUDGET_VALIDATION = 2_000    # Stage 7: Validation

# ==================== OUTPUT TOKEN LIMITS ====================
# Maximum output tokens for different stages (reduced for cost optimization)
MAX_TOKENS_DEFAULT = 12_000          # Default for most stages (reduced from 16k)
MAX_TOKENS_TRIAL_DESIGN = 3_000      # Stage 0: Trial design (reduced from 4k)
MAX_TOKENS_DEMOGRAPHICS = 6_000      # Stage 2: Demographics (reduced from 8k)
MAX_TOKENS_EFFICACY = 12_000         # Stage 5: Efficacy endpoints (reduced from 16k)
MAX_TOKENS_SAFETY = 8_000            # Stage 6: Safety endpoints (reduced from 12k)
MAX_TOKENS_FIGURE = 3_000            # Stage 5b: Figure extraction (reduced from 4k)

# ==================== RETRY CONFIGURATION ====================
# API retry settings
MAX_RETRIES = 3                      # Maximum number of retry attempts
RETRY_BASE_DELAY = 5.0               # Base delay in seconds (multiplied by attempt number)
RETRYABLE_STATUS_CODES = (500, 502, 503, 504)  # HTTP status codes that trigger retry

# ==================== SIMILARITY THRESHOLDS ====================
# Fuzzy matching thresholds
ARM_MATCH_SIMILARITY_THRESHOLD = 0.8  # Minimum similarity for arm name matching

# ==================== SAFETY TABLE SCORING ====================
# Safety table detection parameters
SAFETY_TABLE_MIN_SCORE = 15                    # Minimum score to consider a table as safety table
SAFETY_TABLE_SIZE_PENALTY_THRESHOLD = 50       # Row count threshold for size penalty
SAFETY_TABLE_SIZE_PENALTY = 5                  # Points deducted for oversized tables

# Safety keywords with weights for table scoring
SAFETY_KEYWORDS = {
    'adverse event': 3,
    'serious adverse': 4,
    'treatment-emergent': 3,
    'discontinuation': 2,
    'herpes zoster': 2,
    'infection': 1,
    'nasopharyngitis': 1,
    'death': 3,
    'teae': 3,  # Treatment-emergent adverse event
    'sae': 4,   # Serious adverse event
}

# ==================== VALIDATION THRESHOLDS ====================
# Extraction quality thresholds
MIN_BASELINE_COMPLETENESS_PCT = 50.0   # Minimum baseline data completeness
MIN_EFFICACY_ENDPOINT_COUNT = 1        # Minimum efficacy endpoints expected
MIN_SAFETY_ENDPOINT_COUNT = 1          # Minimum safety endpoints expected

# ==================== TABLE VALIDATION ====================
# Table validation scoring
TABLE_VALIDATION_MIN_CONFIDENCE = 0.5  # Minimum confidence to keep a table

