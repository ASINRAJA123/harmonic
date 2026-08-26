"""
Run 2026 portfolio check on all data up to Aug 25, 2026.
"""

import os
import sys
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from run_2026_portfolio import INSTRUMENTS, load_data, resample_bars, HarmonicV3Config, run_harmonic_v3_backtest

print("=== 2026 MAX HISTORY DATA CHECK (JAN 1 TO AUG 25, 2026) ===")
for sym, spec in INSTRUMENTS.items():
    df = load_data(sym)
    if df is not None:
        print(f"{sym:<8}: {len(df):>6} M5 bars | Dates: {df['time'].min()} to {df['time'].max()} | Close: {df['close'].iloc[0]:.2f} to {df['close'].iloc[-1]:.2f}")
    else:
        print(f"{sym:<8}: NOT FOUND")
