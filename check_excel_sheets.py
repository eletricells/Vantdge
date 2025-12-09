import pandas as pd

xl = pd.ExcelFile('data/case_series/baricitinib_20251208_123821.xlsx')
print('All sheets:', xl.sheet_names)

if 'Score Breakdown' in xl.sheet_names:
    df_scores = pd.read_excel(xl, 'Score Breakdown')
    print(f'\n=== Score Breakdown Sheet ===')
    print(f'Found {len(df_scores)} rows')
    print(f'\nTotal columns: {len(df_scores.columns)}')
    print('\nNew clinical detail columns:')
    clinical_cols = [c for c in df_scores.columns if 'Clinical -' in c]
    for col in clinical_cols:
        print(f'  - {col}')
    print('\nFirst row clinical details:')
    print(df_scores.iloc[0][['Disease', 'Clinical - Safety Categories', 'Clinical - Regulatory Flags', 'Clinical - Response Rate Detail']])
else:
    print('\nScore Breakdown sheet NOT FOUND')

if 'Market Intelligence' in xl.sheet_names:
    df_mi = pd.read_excel(xl, 'Market Intelligence')
    print(f'\n=== Market Intelligence Sheet ===')
    print(f'Found {len(df_mi)} rows')
else:
    print('\nMarket Intelligence sheet NOT FOUND')

