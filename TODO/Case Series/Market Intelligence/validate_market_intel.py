"""
Validation Script for Market Intelligence Improvements
======================================================

Run this script to validate that the ClinicalTrials.gov API integration is working
and to compare results against known ground truth data.

Usage:
    python validate_market_intel.py
"""

import requests
import json
from typing import List, Dict

# Ground truth data for validation
GROUND_TRUTH = {
    "Primary Sjogren's syndrome": {
        "approved_count": 0,  # No FDA-approved disease-modifying treatments
        "min_phase_3_count": 5,  # At least 5 Phase 3 drugs known
        "min_phase_2_count": 3,  # At least 3 Phase 2 drugs known
        "expected_drugs": [
            "ianalumab", "telitacicept", "nipocalimab", 
            "dazodalibep", "efgartigimod", "RSLV-132"
        ]
    },
    "Atopic Dermatitis": {
        "approved_count": 7,  # Dupixent, Adbry, Cibinqo, Rinvoq, Opzelura, etc.
        "min_phase_3_count": 3,
        "min_phase_2_count": 2,
        "expected_drugs": ["dupilumab", "tralokinumab", "abrocitinib", "upadacitinib"]
    },
    "Giant Cell Arteritis": {
        "approved_count": 1,  # Actemra (tocilizumab)
        "min_phase_3_count": 1,
        "min_phase_2_count": 1,
        "expected_drugs": ["tocilizumab"]
    },
    "Myasthenia Gravis": {
        "approved_count": 5,  # Vyvgart, Ultomiris, Soliris, etc.
        "min_phase_3_count": 2,
        "min_phase_2_count": 2,
        "expected_drugs": ["efgartigimod", "ravulizumab", "eculizumab"]
    }
}


def fetch_clinicaltrials_gov(disease: str, phases: List[str] = None) -> List[Dict]:
    """Test the ClinicalTrials.gov API integration."""
    if phases is None:
        phases = ["PHASE2", "PHASE3"]
    
    base_url = "https://clinicaltrials.gov/api/v2/studies"
    
    all_trials = []
    statuses = ["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION", "NOT_YET_RECRUITING"]
    
    for phase in phases:
        params = {
            "query.cond": disease,
            "filter.overallStatus": ",".join(statuses),
            "filter.phase": phase,
            "pageSize": 50,
            "fields": "NCTId,BriefTitle,Phase,OverallStatus,InterventionName,LeadSponsorName"
        }
        
        try:
            response = requests.get(base_url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                studies = data.get('studies', [])
                all_trials.extend(studies)
                print(f"  {phase}: Found {len(studies)} trials")
        except Exception as e:
            print(f"  Error fetching {phase}: {e}")
    
    return all_trials


def parse_trials(trials: List[Dict]) -> List[Dict]:
    """Parse trial data into simplified format."""
    parsed = []
    seen_ncts = set()
    
    for trial in trials:
        protocol = trial.get('protocolSection', {})
        identification = protocol.get('identificationModule', {})
        status = protocol.get('statusModule', {})
        design = protocol.get('designModule', {})
        sponsor = protocol.get('sponsorCollaboratorsModule', {})
        arms = protocol.get('armsInterventionsModule', {})
        
        nct_id = identification.get('nctId')
        if nct_id in seen_ncts:
            continue
        seen_ncts.add(nct_id)
        
        # Extract drug names
        interventions = arms.get('interventions', [])
        drug_names = []
        for intervention in interventions:
            if intervention.get('type') in ['DRUG', 'BIOLOGICAL']:
                drug_names.append(intervention.get('name', 'Unknown'))
        
        phases = design.get('phases', [])
        phase_str = ", ".join(phases).replace("PHASE", "Phase ")
        
        parsed.append({
            'nct_id': nct_id,
            'title': identification.get('briefTitle'),
            'phase': phase_str,
            'status': status.get('overallStatus'),
            'drugs': drug_names,
            'sponsor': sponsor.get('leadSponsor', {}).get('name')
        })
    
    return parsed


def validate_disease(disease: str, ground_truth: Dict):
    """Validate pipeline data for a single disease."""
    print(f"\n{'='*60}")
    print(f"Validating: {disease}")
    print('='*60)
    
    # Fetch from API
    trials = fetch_clinicaltrials_gov(disease)
    parsed = parse_trials(trials)
    
    # Count phases
    phase_3_count = sum(1 for t in parsed if 'Phase 3' in t['phase'])
    phase_2_count = sum(1 for t in parsed if 'Phase 2' in t['phase'] and 'Phase 3' not in t['phase'])
    
    print(f"\nResults:")
    print(f"  Total unique trials: {len(parsed)}")
    print(f"  Phase 3 count: {phase_3_count}")
    print(f"  Phase 2 count: {phase_2_count}")
    
    # Check against ground truth
    print(f"\nValidation:")
    
    min_p3 = ground_truth['min_phase_3_count']
    if phase_3_count >= min_p3:
        print(f"  ✓ Phase 3 count ({phase_3_count}) >= expected minimum ({min_p3})")
    else:
        print(f"  ✗ Phase 3 count ({phase_3_count}) < expected minimum ({min_p3})")
    
    min_p2 = ground_truth['min_phase_2_count']
    if phase_2_count >= min_p2:
        print(f"  ✓ Phase 2 count ({phase_2_count}) >= expected minimum ({min_p2})")
    else:
        print(f"  ✗ Phase 2 count ({phase_2_count}) < expected minimum ({min_p2})")
    
    # Check for expected drugs
    all_drugs = set()
    for t in parsed:
        for drug in t['drugs']:
            all_drugs.add(drug.lower())
    
    found_expected = []
    missing_expected = []
    for expected in ground_truth['expected_drugs']:
        if any(expected.lower() in d for d in all_drugs):
            found_expected.append(expected)
        else:
            missing_expected.append(expected)
    
    print(f"\n  Expected drugs found: {found_expected}")
    if missing_expected:
        print(f"  Expected drugs missing: {missing_expected}")
    
    # List all trials found
    print(f"\nTrials found:")
    for t in parsed[:10]:  # First 10
        drugs_str = ", ".join(t['drugs'][:3]) if t['drugs'] else "N/A"
        print(f"  - {t['nct_id']}: {t['phase']} | {t['sponsor'][:30] if t['sponsor'] else 'Unknown'} | Drugs: {drugs_str}")
    
    if len(parsed) > 10:
        print(f"  ... and {len(parsed) - 10} more")
    
    return {
        'disease': disease,
        'total_trials': len(parsed),
        'phase_3_count': phase_3_count,
        'phase_2_count': phase_2_count,
        'passed': phase_3_count >= min_p3 and phase_2_count >= min_p2
    }


def run_validation():
    """Run validation for all ground truth diseases."""
    print("Market Intelligence Validation Script")
    print("=====================================")
    print("Testing ClinicalTrials.gov API integration...\n")
    
    results = []
    for disease, truth in GROUND_TRUTH.items():
        result = validate_disease(disease, truth)
        results.append(result)
    
    # Summary
    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print('='*60)
    
    passed = sum(1 for r in results if r['passed'])
    total = len(results)
    
    for r in results:
        status = "✓ PASS" if r['passed'] else "✗ FAIL"
        print(f"  {status}: {r['disease']} (P3: {r['phase_3_count']}, P2: {r['phase_2_count']})")
    
    print(f"\nOverall: {passed}/{total} diseases passed validation")
    
    if passed == total:
        print("\n✓ All validations passed! ClinicalTrials.gov API integration is working correctly.")
    else:
        print("\n✗ Some validations failed. Check the disease variants or API query parameters.")


if __name__ == "__main__":
    run_validation()
