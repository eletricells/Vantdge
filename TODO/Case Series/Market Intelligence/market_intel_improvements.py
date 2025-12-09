"""
Market Intelligence Improvements - Code Changes
================================================

This file contains all the code changes needed to improve pipeline and 
approved treatment extraction. Copy these into drug_repurposing_case_series_agent.py

Changes are organized by section with clear markers for where to add/modify code.
"""

# =============================================================================
# SECTION 1: NEW IMPORTS (add at top of file)
# =============================================================================

import requests
from typing import List, Dict, Any, Optional, Tuple
from functools import lru_cache

# =============================================================================
# SECTION 2: NEW CONSTANTS (add after existing constants)
# =============================================================================

# Disease name variations for better search coverage
DISEASE_NAME_VARIANTS = {
    "Primary Sjogren's syndrome": [
        "Sjogren syndrome",
        "Sjögren's disease", 
        "Sjögren syndrome",
        "sicca syndrome",
        "primary Sjögren's"
    ],
    "Systemic Lupus Erythematosus": [
        "SLE",
        "lupus erythematosus",
        "systemic lupus"
    ],
    "Rheumatoid Arthritis": [
        "RA",
        "rheumatoid"
    ],
    "Atopic Dermatitis": [
        "AD",
        "atopic eczema",
        "eczema"
    ],
    "Dermatomyositis": [
        "DM",
        "inflammatory myopathy"
    ],
    "Alopecia Areata": [
        "AA",
        "alopecia totalis",
        "alopecia universalis"
    ],
    "Giant Cell Arteritis": [
        "GCA",
        "temporal arteritis"
    ],
    "Takayasu arteritis": [
        "TAK",
        "Takayasu's arteritis",
        "large vessel vasculitis"
    ],
    "Juvenile Idiopathic Arthritis": [
        "JIA",
        "juvenile arthritis",
        "juvenile rheumatoid arthritis"
    ],
    "Adult-onset Still's Disease": [
        "AOSD",
        "Still's disease",
        "adult Still disease"
    ],
    "Graft-versus-Host Disease": [
        "GVHD",
        "graft versus host",
        "GvHD"
    ],
    "Inflammatory Bowel Disease": [
        "IBD",
        "Crohn's disease",
        "ulcerative colitis"
    ],
    "Psoriatic Arthritis": [
        "PsA",
        "psoriatic"
    ],
    "Ankylosing Spondylitis": [
        "AS",
        "axial spondyloarthritis",
        "axSpA"
    ],
    "Myasthenia Gravis": [
        "MG",
        "myasthenia"
    ],
    "Immune Thrombocytopenia": [
        "ITP",
        "immune thrombocytopenic purpura",
        "idiopathic thrombocytopenic purpura"
    ],
}

# Map overly specific diseases to parent indications for market intel lookup
DISEASE_PARENT_MAPPING = {
    # SLE variants
    "Systemic Lupus Erythematosus with alopecia universalis and arthritis": "Systemic Lupus Erythematosus",
    "SLE with cutaneous manifestations": "Systemic Lupus Erythematosus",
    "refractory systemic lupus erythematosus": "Systemic Lupus Erythematosus",
    
    # Alopecia variants
    "severe alopecia areata with atopic dermatitis in children": "Alopecia Areata",
    "pediatric alopecia universalis": "Alopecia Areata",
    "alopecia totalis": "Alopecia Areata",
    
    # Dermatomyositis variants
    "refractory dermatomyositis": "Dermatomyositis",
    "anti-MDA5 antibody-positive dermatomyositis": "Dermatomyositis",
    "Juvenile dermatomyositis-associated calcinosis": "Juvenile Dermatomyositis",
    "refractory or severe juvenile dermatomyositis": "Juvenile Dermatomyositis",
    
    # JIA variants
    "juvenile idiopathic arthritis associated uveitis": "Juvenile Idiopathic Arthritis",
    "Systemic juvenile idiopathic arthritis with lung disease": "Systemic Juvenile Idiopathic Arthritis",
    
    # Vasculitis variants
    "Takayasu arteritis refractory to TNF-α inhibitors": "Takayasu arteritis",
    
    # Uveitis variants
    "Uveitis associated with rheumatoid arthritis": "Uveitis",
    "isolated noninfectious uveitis": "Uveitis",
    "non-infectious inflammatory ocular diseases": "Uveitis",
    
    # AOSD variants
    "Adult-onset Still's disease (AOSD) and undifferentiated systemic autoinflammatory disease": "Adult-onset Still's Disease",
    
    # Atopic Dermatitis variants (normalize case)
    "atopic dermatitis": "Atopic Dermatitis",
    "moderate-to-severe atopic dermatitis": "Atopic Dermatitis",
    "moderate and severe atopic dermatitis": "Atopic Dermatitis",
    
    # ITP variants
    "immune thrombocytopenia (ITP)": "Immune Thrombocytopenia",
    
    # Lupus variants
    "refractory subacute cutaneous lupus erythematosus": "Cutaneous Lupus Erythematosus",
    "Familial chilblain lupus with TREX1 mutation": "Cutaneous Lupus Erythematosus",
    "Lupus erythematosus panniculitis": "Cutaneous Lupus Erythematosus",
}


# =============================================================================
# SECTION 3: NEW HELPER FUNCTIONS (add as new methods in the class)
# =============================================================================

def _get_disease_name_variants(self, disease: str) -> List[str]:
    """Get alternative names/spellings for a disease to improve search coverage."""
    variants = [disease]
    
    # Check exact match first
    if disease in DISEASE_NAME_VARIANTS:
        variants.extend(DISEASE_NAME_VARIANTS[disease])
        return list(set(variants))
    
    # Check case-insensitive partial matches
    disease_lower = disease.lower()
    for canonical, alts in DISEASE_NAME_VARIANTS.items():
        if canonical.lower() in disease_lower or disease_lower in canonical.lower():
            variants.extend(alts)
            variants.append(canonical)
            break
    
    return list(set(variants))


def _get_parent_disease(self, disease: str) -> Optional[str]:
    """Get the parent/canonical disease name for market intelligence lookup."""
    # Direct mapping
    if disease in DISEASE_PARENT_MAPPING:
        return DISEASE_PARENT_MAPPING[disease]
    
    # Case-insensitive check
    disease_lower = disease.lower()
    for specific, parent in DISEASE_PARENT_MAPPING.items():
        if specific.lower() == disease_lower:
            return parent
    
    return None


def _fetch_clinicaltrials_gov(
    self, 
    disease: str, 
    phases: List[str] = None,
    statuses: List[str] = None
) -> List[Dict]:
    """
    Query ClinicalTrials.gov API v2 directly for comprehensive trial data.
    
    API Documentation: https://clinicaltrials.gov/api/v2/studies
    
    Args:
        disease: Disease name to search
        phases: List of phases to include (default: ["PHASE2", "PHASE3"])
        statuses: List of statuses to include (default: active/recruiting)
    
    Returns:
        List of study records with structured data
    """
    if phases is None:
        phases = ["PHASE2", "PHASE3"]
    
    if statuses is None:
        statuses = [
            "RECRUITING",
            "ACTIVE_NOT_RECRUITING", 
            "ENROLLING_BY_INVITATION",
            "NOT_YET_RECRUITING"
        ]
    
    base_url = "https://clinicaltrials.gov/api/v2/studies"
    
    all_trials = []
    disease_variants = self._get_disease_name_variants(disease)
    
    for variant in disease_variants[:3]:  # Limit to avoid too many API calls
        for phase in phases:
            params = {
                "query.cond": variant,
                "filter.overallStatus": ",".join(statuses),
                "filter.phase": phase,
                "pageSize": 50,
                "fields": ",".join([
                    "NCTId",
                    "BriefTitle", 
                    "OfficialTitle",
                    "Phase",
                    "OverallStatus",
                    "InterventionName",
                    "InterventionType",
                    "LeadSponsorName",
                    "StartDate",
                    "PrimaryCompletionDate",
                    "StudyType",
                    "EnrollmentCount",
                    "Condition"
                ])
            }
            
            try:
                response = requests.get(base_url, params=params, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    studies = data.get('studies', [])
                    all_trials.extend(studies)
                elif response.status_code == 429:
                    # Rate limited - wait and retry once
                    import time
                    time.sleep(2)
                    response = requests.get(base_url, params=params, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        studies = data.get('studies', [])
                        all_trials.extend(studies)
            except requests.exceptions.RequestException as e:
                logger.warning(f"ClinicalTrials.gov API error for {variant}: {e}")
                continue
    
    # Deduplicate by NCT ID
    seen_ncts = set()
    unique_trials = []
    for trial in all_trials:
        nct_id = trial.get('protocolSection', {}).get('identificationModule', {}).get('nctId')
        if nct_id and nct_id not in seen_ncts:
            seen_ncts.add(nct_id)
            unique_trials.append(trial)
    
    logger.info(f"ClinicalTrials.gov API: Found {len(unique_trials)} unique trials for {disease}")
    return unique_trials


def _parse_ct_gov_trial(self, trial: Dict) -> Dict:
    """Parse a ClinicalTrials.gov API response into a simplified format."""
    protocol = trial.get('protocolSection', {})
    identification = protocol.get('identificationModule', {})
    status = protocol.get('statusModule', {})
    design = protocol.get('designModule', {})
    sponsor = protocol.get('sponsorCollaboratorsModule', {})
    arms = protocol.get('armsInterventionsModule', {})
    
    # Extract intervention/drug names
    interventions = arms.get('interventions', [])
    drug_names = []
    for intervention in interventions:
        if intervention.get('type') in ['DRUG', 'BIOLOGICAL']:
            drug_names.append(intervention.get('name', 'Unknown'))
    
    # Get phase
    phases = design.get('phases', [])
    phase_str = ", ".join(phases) if phases else "Unknown"
    phase_str = phase_str.replace("PHASE", "Phase ")
    
    return {
        'nct_id': identification.get('nctId'),
        'title': identification.get('briefTitle'),
        'official_title': identification.get('officialTitle'),
        'phase': phase_str,
        'status': status.get('overallStatus'),
        'drug_names': drug_names,
        'sponsor': sponsor.get('leadSponsor', {}).get('name'),
        'start_date': status.get('startDateStruct', {}).get('date'),
        'completion_date': status.get('primaryCompletionDateStruct', {}).get('date'),
        'enrollment': design.get('enrollmentInfo', {}).get('count')
    }


def _deduplicate_diseases(self, diseases: List[str]) -> List[str]:
    """
    Deduplicate disease list by normalizing names and keeping canonical versions.
    
    Returns list of unique canonical disease names.
    """
    seen_normalized = {}
    result = []
    
    for disease in diseases:
        # Normalize: lowercase, remove extra whitespace
        normalized = ' '.join(disease.lower().split())
        
        # Check if we've seen this or a parent disease
        parent = self._get_parent_disease(disease)
        check_key = normalized
        
        if parent:
            parent_normalized = ' '.join(parent.lower().split())
            # If parent exists, use parent as the key
            if parent_normalized in seen_normalized:
                continue  # Skip this variant, we have the parent
            check_key = parent_normalized
        
        if check_key not in seen_normalized:
            seen_normalized[check_key] = disease
            result.append(disease)
    
    return result


# =============================================================================
# SECTION 4: UPDATED _get_market_intelligence METHOD
# Replace the existing method with this version
# =============================================================================

def _get_market_intelligence(self, disease: str) -> MarketIntelligence:
    """Get comprehensive market intelligence for a disease."""
    from src.models.case_series_schemas import AttributedSource

    # Check cache for fresh market intelligence
    if self.cs_db:
        cached = self.cs_db.check_market_intel_fresh(disease)
        if cached:
            logger.info(f"Using cached market intelligence for: {disease}")
            self._cache_stats['market_intel_from_cache'] += 1
            self._cache_stats['tokens_saved_by_cache'] += 3000
            return cached

    market_intel = MarketIntelligence(disease=disease)
    attributed_sources = []

    if not self.web_search:
        return market_intel

    # Check if we should use a parent disease for market intel
    parent_disease = self._get_parent_disease(disease)
    search_disease = parent_disease if parent_disease else disease
    
    if parent_disease:
        logger.info(f"Using parent disease '{parent_disease}' for market intel lookup (original: '{disease}')")
        market_intel.parent_disease = parent_disease

    # Get disease name variants for better search coverage
    disease_variants = self._get_disease_name_variants(search_disease)

    # 1. Get epidemiology data
    self.search_count += 1
    epi_results = self.web_search.search(
        f"{search_disease} prevalence United States epidemiology patients",
        max_results=8  # Increased from 5
    )

    if epi_results:
        epi_data = self._extract_epidemiology(search_disease, epi_results)
        market_intel.epidemiology = epi_data
        for r in epi_results[:2]:
            if r.get('url'):
                attributed_sources.append(AttributedSource(
                    url=r.get('url'),
                    title=r.get('title', 'Unknown'),
                    attribution='Epidemiology'
                ))

    # 2. Get FDA approved drugs - ENHANCED with multiple searches
    all_fda_results = []
    
    # Primary FDA search
    self.search_count += 1
    fda_results_1 = self.web_search.search(
        f'"{search_disease}" FDA approved drugs treatments biologics site:fda.gov OR site:drugs.com',
        max_results=10  # Increased from 5
    )
    all_fda_results.extend(fda_results_1 or [])
    
    # Secondary search with variant names
    if len(disease_variants) > 1:
        self.search_count += 1
        fda_results_2 = self.web_search.search(
            f'"{disease_variants[1]}" FDA approved treatment biologic site:medscape.com OR site:uptodate.com',
            max_results=5
        )
        all_fda_results.extend(fda_results_2 or [])

    # 3. Get standard of care
    self.search_count += 1
    soc_results = self.web_search.search(
        f"{search_disease} standard of care treatment guidelines first line second line therapy",
        max_results=8  # Increased from 5
    )

    # Combine results for SOC extraction
    all_treatment_results = all_fda_results + (soc_results or [])
    if all_treatment_results:
        soc_data = self._extract_standard_of_care(
            search_disease, 
            all_treatment_results,
            parent_disease=parent_disease
        )
        market_intel.standard_of_care = soc_data
        
        for r in (all_fda_results or [])[:2]:
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

    # 4. Get pipeline data - ENHANCED with ClinicalTrials.gov API
    
    # 4a. Query ClinicalTrials.gov API directly (primary source)
    ct_gov_trials = self._fetch_clinicaltrials_gov(search_disease)
    ct_gov_parsed = [self._parse_ct_gov_trial(t) for t in ct_gov_trials]
    
    # 4b. Supplementary web search for additional context
    all_pipeline_results = []
    
    self.search_count += 1
    pipeline_results_1 = self.web_search.search(
        f'"{search_disease}" clinical trial Phase 2 OR Phase 3 site:clinicaltrials.gov',
        max_results=10  # Increased from 5
    )
    all_pipeline_results.extend(pipeline_results_1 or [])
    
    # Search for pipeline news/press releases
    self.search_count += 1
    pipeline_results_2 = self.web_search.search(
        f'"{search_disease}" Phase 2 Phase 3 trial drug pipeline 2024 OR 2025',
        max_results=8
    )
    all_pipeline_results.extend(pipeline_results_2 or [])
    
    # Search BioPharma pipeline databases
    self.search_count += 1
    pipeline_results_3 = self.web_search.search(
        f'"{search_disease}" pipeline drug development site:biopharmcatalyst.com OR site:evaluate.com',
        max_results=5
    )
    all_pipeline_results.extend(pipeline_results_3 or [])

    if ct_gov_parsed or all_pipeline_results:
        pipeline_data = self._extract_pipeline_data(
            search_disease, 
            all_pipeline_results,
            ct_gov_data=ct_gov_parsed
        )
        # Merge pipeline data into SOC
        market_intel.standard_of_care.pipeline_therapies = pipeline_data.get('therapies', [])
        market_intel.standard_of_care.num_pipeline_therapies = len(pipeline_data.get('therapies', []))
        market_intel.standard_of_care.phase_3_count = pipeline_data.get('phase_3_count', 0)
        market_intel.standard_of_care.phase_2_count = pipeline_data.get('phase_2_count', 0)
        if pipeline_data.get('details'):
            market_intel.standard_of_care.pipeline_details = pipeline_data['details']
        if pipeline_data.get('key_catalysts'):
            market_intel.standard_of_care.key_catalysts = pipeline_data['key_catalysts']
        market_intel.standard_of_care.pipeline_data_quality = pipeline_data.get('data_completeness', 'Unknown')
        
        # Track pipeline sources
        market_intel.pipeline_sources = [r.get('url') for r in all_pipeline_results if r.get('url')][:5]
        for r in all_pipeline_results[:3]:
            if r.get('url'):
                attributed_sources.append(AttributedSource(
                    url=r.get('url'),
                    title=r.get('title', 'Unknown'),
                    attribution='Pipeline/Clinical Trials'
                ))

    # 5. Get TAM analysis data
    self.search_count += 1
    tam_results = self.web_search.search(
        f'"{search_disease}" market size TAM treatment penetration addressable market forecast',
        max_results=8
    )

    # Calculate simple market sizing
    market_intel = self._calculate_market_sizing(market_intel)

    # 6. Extract TAM with rationale
    if tam_results or all_treatment_results:
        tam_data = self._extract_tam_analysis(
            search_disease,
            tam_results or [],
            market_intel.epidemiology,
            market_intel.standard_of_care
        )
        if tam_data:
            market_intel.tam_estimate = tam_data.get('tam_estimate')
            market_intel.tam_usd = tam_data.get('tam_usd')
            market_intel.tam_rationale = tam_data.get('tam_rationale')

    # Store attributed sources
    market_intel.attributed_sources = attributed_sources

    # Cache the result
    if self.cs_db:
        self.cs_db.cache_market_intel(market_intel)

    return market_intel


# =============================================================================
# SECTION 5: UPDATED _extract_pipeline_data METHOD
# Replace the existing method with this version
# =============================================================================

def _extract_pipeline_data(
    self, 
    disease: str, 
    results: List[Dict],
    ct_gov_data: List[Dict] = None
) -> Dict[str, Any]:
    """
    Extract comprehensive pipeline data from multiple sources.
    
    Args:
        disease: Disease name
        results: Web search results
        ct_gov_data: Parsed ClinicalTrials.gov API data (optional but preferred)
    """
    results_with_urls = []
    for r in results:
        results_with_urls.append({
            'title': r.get('title'),
            'content': r.get('content') or r.get('snippet'),
            'url': r.get('url')
        })

    prompt = self._prompts.render(
        "case_series/extract_pipeline",
        disease=disease,
        search_results=results_with_urls[:6000],
        ct_gov_data=ct_gov_data  # Pass structured API data to prompt
    )

    try:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2500,  # Increased for more comprehensive output
            messages=[{"role": "user", "content": prompt}]
        )
        self._track_tokens(response.usage)

        content = self._clean_json_response(response.content[0].text.strip())
        data = json.loads(content)

        # Build pipeline therapy objects
        therapies = []
        phase_3_count = 0
        phase_2_count = 0
        
        for t in data.get('pipeline_therapies', []):
            phase = t.get('phase', 'Unknown')
            
            # Count by phase
            if 'Phase 3' in phase or 'Phase3' in phase:
                phase_3_count += 1
            elif 'Phase 2' in phase or 'Phase2' in phase:
                phase_2_count += 1
            
            therapies.append(PipelineTherapy(
                drug_name=t.get('drug_name', 'Unknown'),
                company=t.get('company'),
                mechanism=t.get('mechanism'),
                phase=phase,
                trial_id=t.get('trial_id'),
                trial_name=t.get('trial_name'),
                status=t.get('status'),
                expected_completion=t.get('expected_completion'),
                regulatory_designations=t.get('regulatory_designations'),
                notes=t.get('notes')
            ))

        return {
            'therapies': therapies,
            'phase_3_count': data.get('phase_3_count', phase_3_count),
            'phase_2_count': data.get('phase_2_count', phase_2_count),
            'details': data.get('pipeline_summary'),
            'key_catalysts': data.get('key_catalysts'),
            'data_completeness': data.get('data_completeness', 'Unknown'),
            'data_completeness_notes': data.get('data_completeness_notes')
        }
    except Exception as e:
        logger.error(f"Error extracting pipeline data: {e}")
        return {
            'therapies': [], 
            'phase_3_count': 0,
            'phase_2_count': 0,
            'details': None,
            'data_completeness': 'Low'
        }


# =============================================================================
# SECTION 6: UPDATED _extract_standard_of_care METHOD
# Replace the existing method with this version
# =============================================================================

def _extract_standard_of_care(
    self, 
    disease: str, 
    results: List[Dict],
    parent_disease: str = None
) -> StandardOfCareData:
    """Extract standard of care with enhanced confidence scoring."""
    results_with_urls = []
    for r in results:
        results_with_urls.append({
            'title': r.get('title'),
            'content': r.get('content') or r.get('snippet'),
            'url': r.get('url')
        })

    prompt = self._prompts.render(
        "case_series/extract_treatments",
        disease=disease,
        parent_disease=parent_disease,
        search_results=results_with_urls[:8000]  # Increased context
    )

    try:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2500,  # Increased for more comprehensive output
            messages=[{"role": "user", "content": prompt}]
        )
        self._track_tokens(response.usage)

        content = self._clean_json_response(response.content[0].text.strip())
        data = json.loads(content)

        # Build treatments with enhanced fields
        treatments = []
        approved_innovative_count = 0
        approved_innovative_names = []

        for t in data.get('top_treatments', []):
            is_branded = t.get('is_branded_innovative', False)
            is_approved = t.get('fda_approved', False)
            fda_indication = t.get('fda_approved_indication')
            approval_confidence = t.get('approval_confidence', 'Medium')

            treatments.append(StandardOfCareTreatment(
                drug_name=t.get('drug_name', 'Unknown'),
                drug_class=t.get('drug_class'),
                is_branded_innovative=is_branded,
                fda_approved=is_approved,
                fda_approved_indication=fda_indication,
                approval_year=t.get('approval_year'),
                line_of_therapy=t.get('line_of_therapy'),
                efficacy_range=t.get('efficacy_range'),
                annual_cost_usd=t.get('annual_cost_usd'),
                approval_confidence=approval_confidence,
                approval_evidence=t.get('approval_evidence'),
                notes=t.get('notes')
            ))

            # Count branded innovative drugs that are FDA approved with High/Medium confidence
            if is_branded and is_approved and approval_confidence in ['High', 'Medium']:
                approved_innovative_count += 1
                approved_innovative_names.append(t.get('drug_name', 'Unknown'))

        # Use validated count from top_treatments
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
            recent_approvals=data.get('recent_approvals'),
            soc_source=data.get('soc_source'),
            data_quality=data.get('data_quality', 'Unknown'),
            data_quality_notes=data.get('data_quality_notes')
        )
    except Exception as e:
        logger.error(f"Error extracting SOC: {e}")
        return StandardOfCareData()


# =============================================================================
# SECTION 7: UPDATED SCHEMA CLASSES
# Add these new fields to existing dataclasses in case_series_schemas.py
# =============================================================================

"""
Add these fields to the PipelineTherapy dataclass:

@dataclass
class PipelineTherapy:
    drug_name: str = ""
    company: Optional[str] = None
    mechanism: Optional[str] = None
    phase: str = "Unknown"
    trial_id: Optional[str] = None
    trial_name: Optional[str] = None  # NEW: Trial acronym (e.g., "NEPTUNUS")
    status: Optional[str] = None  # NEW: "Recruiting", "Active", etc.
    expected_completion: Optional[str] = None
    regulatory_designations: Optional[str] = None  # NEW: "BTD, Fast Track", etc.
    notes: Optional[str] = None  # NEW: Additional context


Add these fields to the StandardOfCareData dataclass:

@dataclass
class StandardOfCareData:
    # ... existing fields ...
    phase_3_count: int = 0  # NEW
    phase_2_count: int = 0  # NEW
    key_catalysts: Optional[str] = None  # NEW
    pipeline_data_quality: str = "Unknown"  # NEW
    recent_approvals: Optional[str] = None  # NEW
    data_quality: str = "Unknown"  # NEW
    data_quality_notes: Optional[str] = None  # NEW


Add these fields to the StandardOfCareTreatment dataclass:

@dataclass
class StandardOfCareTreatment:
    # ... existing fields ...
    approval_year: Optional[int] = None  # NEW
    approval_confidence: str = "Medium"  # NEW: "High", "Medium", "Low"
    approval_evidence: Optional[str] = None  # NEW: Source citation


Add this field to the MarketIntelligence dataclass:

@dataclass
class MarketIntelligence:
    # ... existing fields ...
    parent_disease: Optional[str] = None  # NEW: If this is a subtype
"""


# =============================================================================
# SECTION 8: UPDATED EXCEL EXPORT
# Modify the Market Intelligence sheet columns
# =============================================================================

def _write_market_intelligence_enhanced(self, ws, market_data: Dict[str, MarketIntelligence]):
    """Enhanced Market Intelligence sheet with new columns."""
    
    headers = [
        'Disease',
        'Parent Disease',  # NEW
        'US Prevalence',
        'US Incidence', 
        'Patient Population',
        'Prevalence Trend',
        'Approved Treatments (Count)',
        'Approved Drug Names',
        'Approval Data Quality',  # NEW
        'Phase 3 Count',  # NEW (split from Pipeline)
        'Phase 2 Count',  # NEW (split from Pipeline)
        'Total Pipeline',
        'Pipeline Details',
        'Key Catalysts',  # NEW
        'Pipeline Data Quality',  # NEW
        'Treatment Paradigm',
        'Top Treatments',
        'Unmet Need',
        'Unmet Need Description',
        'Avg Annual Cost (USD)',
        'Market Size Estimate',
        'Market Size (USD)',
        'Market Growth Rate',
        'TAM (Total Addressable Market)',
        'TAM (USD)',
        'TAM Rationale',
        'Competitive Landscape',
        'Recent Approvals',  # NEW
        'Sources - Epidemiology',
        'Sources - Approved Drugs',
        'Sources - Treatment',
        'Sources - Pipeline',
        'Sources - TAM/Market'
    ]
    
    # Write headers
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    
    # Write data rows
    row = 2
    for disease, mi in market_data.items():
        soc = mi.standard_of_care if mi.standard_of_care else StandardOfCareData()
        epi = mi.epidemiology if mi.epidemiology else EpidemiologyData()
        
        # Format pipeline details
        pipeline_details_formatted = None
        if soc.pipeline_therapies:
            pipeline_items = []
            for pt in soc.pipeline_therapies:
                item = f"{pt.drug_name} ({pt.phase})"
                if pt.company:
                    item += f" - {pt.company}"
                if pt.trial_id:
                    item += f" [{pt.trial_id}]"
                if pt.status:
                    item += f" ({pt.status})"
                pipeline_items.append(item)
            pipeline_details_formatted = "; ".join(pipeline_items)
        elif soc.pipeline_details:
            pipeline_details_formatted = soc.pipeline_details
        
        # Build row data
        row_data = [
            disease,
            mi.parent_disease,  # NEW
            epi.us_prevalence_estimate,
            epi.us_incidence_estimate,
            epi.patient_population_size,
            epi.trend,
            soc.num_approved_drugs,
            ', '.join(soc.approved_drug_names) if soc.approved_drug_names else None,
            soc.data_quality,  # NEW
            soc.phase_3_count,  # NEW
            soc.phase_2_count,  # NEW
            soc.num_pipeline_therapies,
            pipeline_details_formatted,
            soc.key_catalysts,  # NEW
            soc.pipeline_data_quality,  # NEW
            soc.treatment_paradigm,
            # ... continue with remaining fields
        ]
        
        for col, value in enumerate(row_data, 1):
            ws.cell(row=row, column=col, value=value)
        
        row += 1
