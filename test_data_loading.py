import sys
sys.path.insert(0, '.')
import pandas as pd
from pathlib import Path

# Test all master files exist and have data
for fname in ['shareholding_all.parquet', 'financials_all.parquet', 'cashflow_all.parquet', 'snapshot_all.parquet']:
    path = Path(f'data/{fname}')
    if path.exists():
        df = pd.read_parquet(path)
        print(f'✓ {fname}: {len(df)} rows, {len(df.columns)} columns')
        print(f'  Columns: {list(df.columns)[:5]}...')
    else:
        print(f'✗ {fname}: NOT FOUND')

# Simulate what dashboard does
print('\nTesting dashboard load functions:')
MASTER_CSV_SH = Path('data/shareholding_all.parquet')
if MASTER_CSV_SH.exists():
    try:
        df = pd.read_parquet(MASTER_CSV_SH)
        print(f'✓ Dashboard can load shareholding: {len(df)} rows')
        unique_syms = df['symbol'].nunique()
        print(f'  Unique symbols: {unique_syms}')
    except Exception as e:
        print(f'✗ Dashboard load failed: {e}')
