"""Compare all test runs."""
import json
import os

test_dir = 'data/case_series_test'
files = sorted([f for f in os.listdir(test_dir) if f.startswith('baricitinib_enhanced_test')])

print('='*80)
print('COMPARISON OF ALL TEST RUNS')
print('='*80)

results = []
for f in files:
    with open(os.path.join(test_dir, f)) as fp:
        data = json.load(fp)

    papers = data.get('papers', [])
    diseases = {}
    for p in papers:
        d = p.get('extracted_disease')
        if d:
            diseases[d.lower()] = d

    timestamp = f.split('_')[-1].replace('.json', '')
    results.append({
        'file': f,
        'timestamp': timestamp,
        'papers': len(papers),
        'diseases': diseases,
        'disease_count': len(diseases)
    })

settings = [
    'Original (3+3x50)',
    'Optimized (2+2x30)',
    'Expanded no-ratelimit (4+4x75)',
    'Expanded WITH ratelimit (4+4x75)'
]

print()
for i, r in enumerate(results):
    if i >= len(settings):
        break
    ts = r['timestamp']
    pap = r['papers']
    dis = r['disease_count']
    print(f"{settings[i]:<35} Papers: {pap:>3}   Diseases: {dis:>3}   [{ts}]")

# Compare original vs new expanded (last run)
if len(results) >= 4:
    print()
    print('='*80)
    print('ORIGINAL vs NEW EXPANDED (with rate limiting)')
    print('='*80)

    orig = results[0]
    new_exp = results[3]

    orig_diseases = set(orig['diseases'].keys())
    new_diseases = set(new_exp['diseases'].keys())

    gained = new_diseases - orig_diseases
    lost = orig_diseases - new_diseases
    both = orig_diseases & new_diseases

    print(f'Diseases in BOTH: {len(both)}')
    print(f'Diseases GAINED: {len(gained)}')
    print(f'Diseases LOST: {len(lost)}')

    print()
    print('GAINED diseases (not in original):')
    for d in sorted(gained):
        print(f'  + {new_exp["diseases"][d]}')

    print()
    print('LOST diseases (were in original):')
    for d in sorted(lost):
        print(f'  - {orig["diseases"][d]}')

    # High value check
    print()
    print('='*80)
    print('HIGH-VALUE DISEASE COMPARISON')
    print('='*80)

    checks = [
        ('Dermatomyositis', ['dermatomyositis']),
        ('Juvenile (JDM/JIA)', ['juvenile']),
        ('Behcet', ['behcet', 'behçet']),
        ('Stills disease', ['still']),
        ('Lupus/SLE', ['lupus']),
        ('Arteritis (GCA/Takayasu)', ['arteritis']),
        ('MDA5', ['mda5']),
        ('Blau syndrome', ['blau']),
    ]

    print('Disease                   Original  NewExpanded')
    print('-'*50)
    for name, terms in checks:
        orig_count = len([d for d in orig_diseases if any(t in d for t in terms)])
        new_count = len([d for d in new_diseases if any(t in d for t in terms)])

        status = '+' if new_count > orig_count else ('=' if new_count == orig_count else '-')
        print(f'{name:<25} {orig_count:>5}     {new_count:>5}  {status}')

