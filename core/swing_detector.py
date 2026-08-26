"""
Swing / Pivot Point Detection for Harmonic Pattern Assembly.
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional


def detect_pivots(bars: pd.DataFrame, pivot_len: int) -> Tuple[pd.Series, pd.Series]:
    """Detect pivot highs and pivot lows using fractal logic."""
    n = len(bars)
    highs = bars["high"].values
    lows = bars["low"].values
    
    pivot_highs = np.zeros(n, dtype=bool)
    pivot_lows = np.zeros(n, dtype=bool)
    
    for i in range(pivot_len, n - pivot_len):
        is_high = True
        for j in range(1, pivot_len + 1):
            if highs[i - j] > highs[i] or highs[i + j] > highs[i]:
                is_high = False
                break
        pivot_highs[i] = is_high
        
        is_low = True
        for j in range(1, pivot_len + 1):
            if lows[i - j] < lows[i] or lows[i + j] < lows[i]:
                is_low = False
                break
        pivot_lows[i] = is_low
    
    return pd.Series(pivot_highs, index=bars.index), pd.Series(pivot_lows, index=bars.index)


def collect_swings(bars: pd.DataFrame, pivot_len: int) -> List[dict]:
    """Collect all swing points sorted by bar index."""
    ph, pl = detect_pivots(bars, pivot_len)
    swings = []
    highs = bars["high"].values
    lows = bars["low"].values
    
    for i in range(len(bars)):
        if ph.iloc[i]:
            swings.append({"bar_idx": i, "price": highs[i], "type": "high"})
        if pl.iloc[i]:
            swings.append({"bar_idx": i, "price": lows[i], "type": "low"})
    
    swings.sort(key=lambda s: s["bar_idx"])
    return swings
