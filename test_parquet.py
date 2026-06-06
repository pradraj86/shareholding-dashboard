import pandas as pd
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

sh_dir = Path('data/shareholding_screener')
sh_files = sorted(list(sh_dir.glob('shareholding_*.parquet')))

print(f"Found {len(sh_files)} shareholding parquet files")
print(f"First file: {sh_files[0].name}")

# Test 1
print("\nTEST 1: Reading first file...")
try:
    df = pd.read_parquet(sh_files[0])
    print(f"✓ Success: {len(df)} rows, {len(df.columns)} columns")
except Exception as e:
    print(f"✗ Failed: {e}")
    exit(1)

# Test 2
print("\nTEST 2: Concatenating first 3 files...")
frames = [pd.read_parquet(fpath) for fpath in sh_files[:3]]
combined = pd.concat(frames, ignore_index=True)
print(f"✓ Success: {len(frames)} files → {len(combined)} total rows")
print("\n✓ All tests passed!")
