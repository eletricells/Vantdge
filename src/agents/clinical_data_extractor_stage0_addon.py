"""
Stage 0 Addition for Clinical Data Extractor Agent

This file contains the Stage 0 method and necessary modifications.
Integrate these changes into clinical_data_extractor.py
"""

# ============================================================================
# CHANGES TO extract_trial_data METHOD
# ============================================================================

# 1. Change return type from:
#    -> List[ClinicalTrialExtraction]
# To:
#    -> tuple[TrialDesignMetadata, List[ClinicalTrialExtraction]]

# 2. Add Stage 0 call after line "logger.info(f"Starting clinical data extraction for {nct_id}...")"
# Insert these lines:
"""
        # Stage 0: Extract trial design metadata
        logger.info("Stage 0: Extracting trial design metadata")
        trial_design = self._stage0_extract_trial_design(paper, nct_id, indication)
"""

# 3. Change the return statement at the end from:
#    return extractions
# To:
#    return trial_design, extractions


# ============================================================================
# STAGE 0 METHOD - ADD TO ClinicalDataExtractorAgent CLASS
# ============================================================================

def _stage0_extract_trial_design(
    self,
    paper: Dict[str, Any],
    nct_id: str,
    indication: str,
    trial_name: Optional[str] = None
) -> TrialDesignMetadata:
    """
    Stage 0: Extract trial design metadata.

    Extracts trial-level information including study design, enrollment criteria,
    and key trial parameters. This is extracted once per trial (not per arm).

    No extended thinking needed - straightforward extraction from methods section.

    Token budget: ~4,000 output tokens
    """
    prompt = self._get_stage0_prompt(paper, nct_id, indication)

    # Use higher token limit for comprehensive trial design
    original_max_tokens = self.max_tokens
    self.max_tokens = 4000

    response = self._call_claude(prompt)
    text = self._extract_text_response(response)

    # Restore token limit
    self.max_tokens = original_max_tokens

    # Parse JSON response
    try:
        data = json.loads(text)
        # Override trial_name if we extracted it
        if trial_name:
            data['trial_name'] = trial_name
        trial_design = TrialDesignMetadata(**data)
        return trial_design
    except json.JSONDecodeError:
        # Try to extract JSON from text
        logger.warning("Direct JSON parsing failed in Stage 0, attempting extraction")
        json_str = self._extract_json_from_text(text)
        if json_str:
            try:
                data = json.loads(json_str)
                # Override trial_name if we extracted it
                if trial_name:
                    data['trial_name'] = trial_name
                trial_design = TrialDesignMetadata(**data)
                return trial_design
            except:
                pass

        logger.error(f"Failed to parse Stage 0 response: {text[:500]}")
        # Return minimal trial design
        return TrialDesignMetadata(
            nct_id=nct_id,
            indication=indication,
            trial_design_summary="Failed to extract trial design",
            enrollment_summary="Failed to extract enrollment criteria",
            extraction_confidence=0.0,
            extraction_notes="Extraction parsing failed"
        )


def _get_stage0_prompt(self, paper: Dict[str, Any], nct_id: str, indication: str) -> str:
    """Generate Stage 0 prompt for trial design extraction."""
    return f"""Extract trial design metadata for {nct_id} ({indication}).

PAPER CONTENT:
Title: {paper.get('title', 'Unknown')}
Authors: {', '.join(paper.get('authors', ['Unknown']))}
{paper.get('content', '')[:30000]}

TASK: Extract comprehensive trial design information.

INSTRUCTIONS:
1. Study Design: Extract the study design classification
   - Example: "Randomized, double-blind, placebo-controlled, Phase 3 trial"

2. Trial Design Summary: Write a 2-3 sentence narrative summarizing:
   - Study design and objectives
   - Randomization approach
   - Blinding
   - Duration
   Example: "This was a 52-week, randomized, double-blind, placebo-controlled, Phase 3 trial. Patients were randomized 1:1:1 to receive dupilumab 300mg Q2W, dupilumab 300mg weekly, or placebo. The trial evaluated efficacy and safety in adult patients with moderate-to-severe atopic dermatitis inadequately controlled by topical therapies."

3. Enrollment Summary: Describe the enrolled patient population (2-3 sentences)
   - Key demographic characteristics
   - Disease severity requirements
   - Treatment history requirements
   Example: "Enrolled patients were adults aged 18 years or older with moderate-to-severe atopic dermatitis for at least 3 years. All patients had inadequate response to topical corticosteroids. The mean age was 38 years, 40% were female, and mean baseline EASI score was 32.5."

4. Inclusion Criteria: Extract as list of strings
   - Each criterion as a separate string
   - Keep exact wording from paper when possible

5. Exclusion Criteria: Extract as list of strings
   - Each criterion as a separate string

6. Primary Endpoint: Extract description of primary endpoint

7. Secondary Endpoints: Summarize secondary endpoints (1-2 sentences)

8. Trial Parameters:
   - sample_size_planned: Total planned sample size
   - sample_size_enrolled: Actual enrolled sample size
   - duration_weeks: Trial duration in weeks
   - randomization_ratio: e.g., "1:1:1", "2:1"
   - blinding: "Double-blind", "Open-label", "Single-blind"

OUTPUT FORMAT (JSON):
{{
  "nct_id": "{nct_id}",
  "indication": "{indication}",
  "study_design": "Randomized, double-blind, placebo-controlled, Phase 3 trial",
  "trial_design_summary": "2-3 sentence narrative summary...",
  "enrollment_summary": "2-3 sentence description of enrolled patients...",
  "inclusion_criteria": [
    "Age ≥18 years",
    "EASI ≥16",
    "Inadequate response to topical therapy"
  ],
  "exclusion_criteria": [
    "Prior biologic use within 8 weeks",
    "Active skin infection",
    "Immunosuppressive condition"
  ],
  "primary_endpoint_description": "Co-primary endpoints were...",
  "secondary_endpoints_summary": "Secondary endpoints included...",
  "sample_size_planned": 671,
  "sample_size_enrolled": 671,
  "duration_weeks": 16,
  "randomization_ratio": "1:1:1",
  "stratification_factors": "Stratified by baseline disease severity and region",
  "blinding": "Double-blind",
  "paper_pmid": "{paper.get('pmid', '')}",
  "paper_doi": "{paper.get('doi', '')}",
  "paper_title": "{paper.get('title', '')}",
  "extraction_confidence": 0.9
}}

IMPORTANT:
- Focus on the Methods section for design details
- Extract exact numbers when available
- Use null for fields not found in paper
- Aim for extraction_confidence of 0.8-1.0 for complete data

Output valid JSON only, no additional text."""
