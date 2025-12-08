import json
import os

# Load old results
with open('data/case_series/baricitinib_full_20251205_001011.json') as f:
    old = json.load(f)
old_diseases = set([o['extraction']['disease'] for o in old.get('opportunities', [])])

# Load new results  
test_files = [f for f in os.listdir('data/case_series_test') if f.startswith('baricitinib_enhanced')]
latest = sorted(test_files)[-1]
with open(f'data/case_series_test/{latest}') as f:
    new = json.load(f)
new_diseases = set(new.get('diseases_found', []))

print('='*70)
print('COMPARISON: OLD vs NEW SEARCH RESULTS')
print('='*70)
print(f'\nOLD Search: {len(old_diseases)} diseases from {len(old.get("opportunities", []))} papers')
print(f'NEW Search: {len(new_diseases)} diseases from {new.get("total_papers", 0)} papers')

# What's new
new_only = new_diseases - old_diseases
print(f'\n' + '='*70)
print(f'NEW DISEASES FOUND ({len(new_only)}):')
print('='*70)
for d in sorted(new_only):
    print(f'  + {d}')

# What's in both
both = old_diseases & new_diseases
print(f'\n' + '='*70)
print(f'DISEASES IN BOTH ({len(both)}):')
print('='*70)
for d in sorted(both):
    print(f'  = {d}')

# JDM specific check
jdm_old = [d for d in old_diseases if 'dermatomyositis' in d.lower() or 'jdm' in d.lower() or 'myositis' in d.lower()]
jdm_new = [d for d in new_diseases if 'dermatomyositis' in d.lower() or 'jdm' in d.lower() or 'myositis' in d.lower()]
print(f'\n' + '='*70)
print('JDM/DERMATOMYOSITIS COMPARISON:')
print('='*70)
print(f'OLD: {jdm_old if jdm_old else "NONE FOUND"}')
print(f'NEW: {jdm_new if jdm_new else "NONE FOUND"}')

