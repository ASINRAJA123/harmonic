"""
Diagnostic audit of 2026 performance and trade frequency on Gold.
Investigates:
1. Bar count & date coverage in 2026 dataset.
2. Candidate pattern formations in 2026 vs 2024/2025.
3. Rejection reasons across the 7 Institutional Gates in 2026.
4. Detailed trade-by-trade breakdown of the 10 trades executed in 2026.
"""

import os
import sys
import glob
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.config import HarmonicRatios, PATTERN_MAP
from core.pattern_scanner import _ratio_valid, HarmonicPattern
from core.engine import HarmonicV3Config, resample_bars, compute_atr, compute_h1_trend_bias

DATA_DIR = os.path.join(BASE_DIR, "data")

def load_gold_data():
    frames = []
    year_files = sorted(glob.glob(os.path.join(DATA_DIR, "years", "xauusd_20*.csv")))
    for f in year_files:
        df_y = pd.read_csv(f)
        df_y["time"] = df_y["time"].astype(str).str.replace(".", "-", regex=False)
        df_y["time"] = pd.to_datetime(df_y["time"])
        frames.append(df_y[["time", "open", "high", "low", "close"]])
        
    paid_path = os.path.join(DATA_DIR, "XAUUSD_M5_max_history.csv")
    if os.path.exists(paid_path):
        df_p = pd.read_csv(paid_path)
        df_p["time"] = pd.to_datetime(df_p["time"])
        frames.append(df_p[["time", "open", "high", "low", "close"]])
        
    df_all = pd.concat(frames, ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
    df_all = df_all[(df_all["time"] >= "2010-01-01") & (df_all["time"] <= "2026-08-25 23:59:59")].reset_index(drop=True)
    return df_all

def main():
    df_gold = load_gold_data()
    print("Gold total dataset range:", df_gold["time"].min(), "to", df_gold["time"].max())
    
    # 2026 subset
    df_2026 = df_gold[df_gold["time"] >= "2026-01-01"].reset_index(drop=True)
    df_2025 = df_gold[(df_gold["time"] >= "2025-01-01") & (df_gold["time"] <= "2025-12-31 23:59:59")].reset_index(drop=True)
    df_2024 = df_gold[(df_gold["time"] >= "2024-01-01") & (df_gold["time"] <= "2024-12-31 23:59:59")].reset_index(drop=True)
    
    print(f"\nM5 Bar Counts:")
    print(f"  2024: {len(df_2024)} M5 bars ({df_2024['time'].min()} to {df_2024['time'].max()})")
    print(f"  2025: {len(df_2025)} M5 bars ({df_2025['time'].min()} to {df_2025['time'].max()})")
    print(f"  2026: {len(df_2026)} M5 bars ({df_2026['time'].min()} to {df_2026['time'].max()})")
    
    # Check monthly distribution in 2026
    df_2026["month"] = df_2026["time"].dt.to_period("M")
    print("\n2026 M5 Bar Distribution by Month:")
    print(df_2026["month"].value_counts().sort_index())
    
    # Check Price & Volatility level in 2026 vs 2024/2025
    print("\nAverage Gold Price & M5 ATR:")
    for yr, df_y in [("2024", df_2024), ("2025", df_2025), ("2026", df_2026)]:
        avg_p = df_y["close"].mean()
        high_low_span = (df_y["high"] - df_y["low"]).mean()
        print(f"  {yr}: Avg Price = ${avg_p:,.1f} | Avg M5 Bar Range = ${high_low_span:.2f}")

if __name__ == "__main__":
    main()
