"""
Audit data files in data/ and data/years/ to detect file mislabeling.
"""

import os
import pandas as pd
import glob

DATA_DIR = r"e:\break-and-retest-ea\harmonic\data"

print("--- DATA/YEARS/ FILES ---")
for f in sorted(glob.glob(os.path.join(DATA_DIR, "years", "*.csv"))):
    df = pd.read_csv(f, nrows=5)
    df_tail = pd.read_csv(f).tail(5)
    print(f"{os.path.basename(f)}: len={len(pd.read_csv(f))} | Head close={df['close'].iloc[0]} | Tail close={df_tail['close'].iloc[-1]} | Dates={df['time'].iloc[0]} to {df_tail['time'].iloc[-1]}")

print("\n--- ROOT DATA/ FILES ---")
for f in sorted(glob.glob(os.path.join(DATA_DIR, "*.csv"))):
    df = pd.read_csv(f, nrows=5)
    df_tail = pd.read_csv(f).tail(5)
    print(f"{os.path.basename(f)}: len={len(pd.read_csv(f))} | Head close={df['close'].iloc[0]} | Tail close={df_tail['close'].iloc[-1]} | Dates={df['time'].iloc[0]} to {df_tail['time'].iloc[-1]}")
