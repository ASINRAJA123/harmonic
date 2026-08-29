"""
Harmonic_EA_V3_Champion — Standalone Institutional Execution Engine.
"""

import os
import sys
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

from .config import HarmonicRatios, PATTERN_MAP, compute_target_price
from .pattern_scanner import HarmonicPattern, validate_pattern


@dataclass
class HarmonicV3Config:
    """Champion Institutional Configuration."""
    name: str = "Harmonic_EA_V3_Champion"
    
    # 1. Golden Session Filter (Empirically Proven Peak Alpha Window)
    session_start_hour: int = 13              # NY Open & London Overlap
    session_end_hour: int = 20                # NY Afternoon Close
    allowed_days: Optional[List[int]] = None  # Mon-Fri
    
    # 2. Frictional Protection Floor
    min_atr_stop_multiple: float = 0.50       # 0.50x ATR (Allows natural Point X stops)
    min_stop_to_spread_ratio: float = 4.5     # Stop distance must be >= 4.5x Spread
    
    # 3. H1 Institutional Trend Filter
    use_h1_trend_filter: bool = True
    h1_fast_ema: int = 50
    h1_slow_ema: int = 200
    
    # 4. High-Alpha Pattern Selection
    min_score: float = 0.80                   # 80% minimum Fibonacci accuracy score
    enabled_patterns: List[str] = field(default_factory=lambda: ["Shark", "Cypher", "Gartley"])
    fib_error_pct: float = 15.0
    leg_asymmetry_pct: float = 250.0
    pivot_lengths: List[int] = field(default_factory=lambda: [3, 5, 8])
    
    # 5. Dual Targets & Trailing
    stop_pct: float = 75.0
    stop_mode: str = "pct_of_t1"
    tp1_partial_pct: float = 0.50             # 50% partial profit at TP1
    move_to_be_at_tp1: bool = True            # Trailing stop to entry upon TP1 fill
    pattern_timeout_mult: float = 3.0         # Expiry in pattern-lengths
    entry_limit_pct: float = 1.0
    
    # 6. Risk Management
    risk_per_trade_pct: float = 0.015         # 1.5% Institutional Risk per Trade
    max_concurrent_positions: int = 2         # Max concurrent trades per asset
    initial_equity: float = 10_000.0
    max_lot_size: float = 50.0
    min_lot_size: float = 0.01
    
    # 7. Broker Microstructure & Friction
    spread_points: float = 25.0               # Points
    commission_per_lot: float = 5.00          # $5.00/lot ECN round-turn
    slippage_points: float = 10.0             # Slippage points on stops
    contract_size: float = 100.0
    point_size: float = 0.01
    quote_currency: str = "USD"
    symbol: str = "XAUUSD"


@dataclass
class HarmonicV3Trade:
    """Champion Trade Record."""
    trade_id: str
    symbol: str
    pattern_type: str
    direction: str
    bull: bool
    score: float
    
    entry_bar: int
    entry_price: float
    exit_bar: int
    exit_price: float
    exit_reason: str
    
    initial_stop: float
    tp1_price: float
    tp2_price: float
    lot_size: float
    
    gross_pnl: float
    spread_cost: float
    commission_cost: float
    slippage_cost: float
    net_pnl: float
    r_multiple: float
    
    entry_time: Optional[pd.Timestamp] = None
    exit_time: Optional[pd.Timestamp] = None


def resample_bars(m5_bars: pd.DataFrame, target_tf_minutes: int) -> pd.DataFrame:
    """Resample M5 bars to higher timeframe."""
    if target_tf_minutes <= 5:
        return m5_bars.copy()
    df = m5_bars.copy()
    df = df.set_index("time")
    resampled = df.resample(f"{target_tf_minutes}min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last",
    }).dropna().reset_index()
    return resampled


def compute_ema(series: np.ndarray, span: int) -> np.ndarray:
    return pd.Series(series).ewm(span=span, adjust=False).mean().values


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> np.ndarray:
    n = len(highs)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    return pd.Series(tr).rolling(window=period, min_periods=1).mean().values


def compute_h1_trend_bias(m15_bars: pd.DataFrame, fast_period=50, slow_period=200) -> np.ndarray:
    df = m15_bars.copy()
    df_h1 = df.set_index("time").resample("60min").agg({
        "open": "first", "high": "max", "low": "min", "close": "last"
    }).dropna()
    
    h1_closes = df_h1["close"].values
    h1_fast = compute_ema(h1_closes, fast_period)
    h1_slow = compute_ema(h1_closes, slow_period)
    
    h1_bias = np.zeros(len(df_h1), dtype=int)
    for k in range(len(df_h1)):
        if h1_closes[k] > h1_fast[k] and h1_fast[k] >= h1_slow[k]:
            h1_bias[k] = 1
        elif h1_closes[k] < h1_fast[k] and h1_fast[k] <= h1_slow[k]:
            h1_bias[k] = -1
        else:
            h1_bias[k] = 0
            
    df_h1["bias"] = h1_bias
    df_h1["causal_bias"] = df_h1["bias"].shift(1).fillna(0)
    
    merged = pd.merge_asof(
        df[["time"]].sort_values("time"),
        df_h1[["causal_bias"]].reset_index().sort_values("time"),
        on="time", direction="backward"
    )
    return merged["causal_bias"].fillna(0).values.astype(int)


def run_harmonic_v3_backtest(bars: pd.DataFrame, cfg: HarmonicV3Config) -> Dict:
    n = len(bars)
    if n < 50:
        return {"trades": [], "scorecard": {}}
        
    highs = bars["high"].values
    lows = bars["low"].values
    opens = bars["open"].values
    closes = bars["close"].values
    times = bars["time"].values if "time" in bars.columns else np.arange(n)
    
    atr = compute_atr(highs, lows, closes, period=14)
    h1_bias = compute_h1_trend_bias(bars, cfg.h1_fast_ema, cfg.h1_slow_ema) if cfg.use_h1_trend_filter else np.zeros(n)
    
    pivots_confirmed_at = [[] for _ in range(n)]
    for R in cfg.pivot_lengths:
        for p in range(R, n - R):
            is_high = True
            for j in range(1, R + 1):
                if highs[p - j] > highs[p] or highs[p + j] > highs[p]:
                    is_high = False
                    break
            if is_high:
                conf_bar = p + R
                if conf_bar < n:
                    pivots_confirmed_at[conf_bar].append((p, highs[p], "high", R))
                    
            is_low = True
            for j in range(1, R + 1):
                if lows[p - j] < lows[p] or lows[p + j] < lows[p]:
                    is_low = False
                    break
            if is_low:
                conf_bar = p + R
                if conf_bar < n:
                    pivots_confirmed_at[conf_bar].append((p, lows[p], "low", R))
                    
    known_highs = []
    known_lows = []
    
    equity = cfg.initial_equity
    trades: List[HarmonicV3Trade] = []
    open_trades: List[HarmonicPattern] = []
    trade_counter = 0
    
    spread_price = cfg.spread_points * cfg.point_size
    slip_price = cfg.slippage_points * cfg.point_size
    
    for i in range(20, n):
        current_time = pd.Timestamp(times[i]) if not isinstance(times[i], (int, float)) else None
        
        # 1. Manage Active Positions
        still_open = []
        for pat in open_trades:
            if pat.exit_reason is not None:
                continue
                
            pattern_len = pat.d_idx - pat.x_idx
            timeout_bar = pat.d_idx + int(pattern_len * cfg.pattern_timeout_mult)
            
            hit_sl = False
            hit_tp1 = False
            hit_tp2 = False
            
            if pat.bull:
                hit_sl = lows[i] <= pat.stop_price
                if not pat.t1_hit:
                    hit_tp1 = highs[i] >= pat.t1_price
                else:
                    hit_tp2 = highs[i] >= pat.t2_price
            else:
                hit_sl = highs[i] >= pat.stop_price
                if not pat.t1_hit:
                    hit_tp1 = lows[i] <= pat.t1_price
                else:
                    hit_tp2 = lows[i] <= pat.t2_price
                    
            if hit_sl and hit_tp1:
                hit_tp1 = False
                
            if hit_sl:
                exit_price = pat.stop_price
                exit_reason = "TP1_BE" if pat.t1_hit else "SL"
                pat.exit_bar = i
                pat.exit_price = exit_price
                pat.exit_reason = exit_reason
            elif hit_tp1 and not pat.t1_hit:
                pat.t1_hit = True
                pat.stop_price = pat.entry_price
                still_open.append(pat)
                continue
            elif hit_tp2:
                pat.exit_bar = i
                pat.exit_price = pat.t2_price
                pat.exit_reason = "TP1_TP2"
            elif i >= timeout_bar:
                pat.exit_bar = i
                pat.exit_price = closes[i]
                pat.exit_reason = "TIMEOUT"
            else:
                still_open.append(pat)
                continue
                
            lots = pat.lot_size
            if pat.exit_reason == "TP1_TP2":
                half_lots = lots * 0.50
                pnl_tp1 = (abs(pat.t1_price - pat.entry_price)) * half_lots * cfg.contract_size
                pnl_tp2 = (abs(pat.t2_price - pat.entry_price)) * half_lots * cfg.contract_size
                gross_pnl = pnl_tp1 + pnl_tp2
                applied_slip = 0.0
            elif pat.exit_reason == "TP1_BE":
                half_lots = lots * 0.50
                gross_pnl = (abs(pat.t1_price - pat.entry_price)) * half_lots * cfg.contract_size
                applied_slip = 0.0
            elif pat.exit_reason == "SL":
                gross_pnl = -abs(pat.entry_price - pat.stop_price) * lots * cfg.contract_size
                applied_slip = slip_price
            else:
                pnl_per_unit = (pat.exit_price - pat.entry_price) if pat.bull else (pat.entry_price - pat.exit_price)
                gross_pnl = pnl_per_unit * lots * cfg.contract_size
                applied_slip = 0.0
                
            fx_rate = pat.exit_price if getattr(cfg, "quote_currency", "USD") != "USD" and getattr(pat, "exit_price", 0) > 0 else 1.0
            gross_pnl = gross_pnl / fx_rate
            spread_cost = (spread_price * cfg.contract_size * lots) / fx_rate
            comm_cost = cfg.commission_per_lot * lots
            slippage_cost = (applied_slip * cfg.contract_size * lots) / fx_rate
            total_friction = spread_cost + comm_cost + slippage_cost
            net_pnl = gross_pnl - total_friction
            
            r_mult = (net_pnl / (equity * cfg.risk_per_trade_pct)) if equity > 0 else 0.0
            
            trades.append(HarmonicV3Trade(
                trade_id=f"{cfg.symbol}_V3_{trade_counter}",
                symbol=cfg.symbol,
                pattern_type=pat.pattern_type,
                direction="LONG" if pat.bull else "SHORT",
                bull=pat.bull,
                score=pat.score,
                entry_bar=pat.entry_bar,
                entry_price=pat.entry_price,
                exit_bar=pat.exit_bar,
                exit_price=pat.exit_price,
                exit_reason=pat.exit_reason,
                initial_stop=pat.stop_price,
                tp1_price=pat.t1_price,
                tp2_price=pat.t2_price,
                lot_size=pat.lot_size,
                gross_pnl=gross_pnl,
                spread_cost=spread_cost,
                commission_cost=comm_cost,
                slippage_cost=slippage_cost,
                net_pnl=net_pnl,
                r_multiple=r_mult,
                entry_time=pd.Timestamp(times[pat.entry_bar]) if pat.entry_bar and "time" in bars.columns else None,
                exit_time=pd.Timestamp(times[i]) if "time" in bars.columns else None,
            ))
            equity += net_pnl
            trade_counter += 1
            
        open_trades = still_open
        
        # 2. Update Pivots
        for (p_idx, p_price, p_type, radius) in pivots_confirmed_at[i]:
            if p_type == "high":
                known_highs.append((p_idx, p_price))
            else:
                known_lows.append((p_idx, p_price))
                
        if len(known_highs) > 40: known_highs = known_highs[-40:]
        if len(known_lows) > 40: known_lows = known_lows[-40:]
        
        # 3. Golden Window Session Gate (13:00 - 20:00 UTC)
        newly_confirmed = pivots_confirmed_at[i]
        if not newly_confirmed:
            continue
            
        if current_time is not None:
            if current_time.hour < cfg.session_start_hour or current_time.hour >= cfg.session_end_hour:
                continue
                
        if len(open_trades) >= cfg.max_concurrent_positions:
            continue
            
        for (dI, dP, dType, radius) in newly_confirmed:
            bull = (dType == "low")
            
            # H1 Trend Gate
            if cfg.use_h1_trend_filter:
                current_bias = h1_bias[i]
                if bull and current_bias < 0: continue
                if not bull and current_bias > 0: continue
                
            c_cands = [p for p in (known_highs if bull else known_lows) if p[0] < dI]
            b_cands = [p for p in (known_lows if bull else known_highs) if p[0] < dI]
            a_cands = [p for p in (known_highs if bull else known_lows) if p[0] < dI]
            x_cands = [p for p in (known_lows if bull else known_highs) if p[0] < dI]
            
            c_cands.sort(key=lambda x: x[0], reverse=True)
            b_cands.sort(key=lambda x: x[0], reverse=True)
            a_cands.sort(key=lambda x: x[0], reverse=True)
            x_cands.sort(key=lambda x: x[0], reverse=True)
            
            found_pat = None
            for cI, cP in c_cands[:5]:
                if bull and cP <= dP: continue
                if not bull and cP >= dP: continue
                for bI, bP in b_cands[:5]:
                    if bI >= cI: continue
                    if bull and bP >= cP: continue
                    if not bull and bP <= cP: continue
                    for aI, aP in a_cands[:5]:
                        if aI >= bI: continue
                        if bull and aP <= bP: continue
                        if not bull and aP >= bP: continue
                        for xI, xP in x_cands[:5]:
                            if xI >= aI: continue
                            if bull and xP >= aP: continue
                            if not bull and xP <= aP: continue
                            
                            for pat_name in cfg.enabled_patterns:
                                r_def = PATTERN_MAP.get(pat_name)
                                if r_def is None: continue
                                pat = validate_pattern(xP, aP, bP, cP, dP, xI, aI, bI, cI, dI, r_def, cfg, bull)
                                if pat is not None and pat.score >= cfg.min_score:
                                    if found_pat is None or pat.score > found_pat.score:
                                        found_pat = pat
                
            if found_pat is not None:
                if i + 1 >= n: continue
                
                fill_price = opens[i + 1]
                stop_dist = abs(fill_price - found_pat.stop_price)
                
                # Frictional Floor Gate
                min_stop_atr = atr[i] * cfg.min_atr_stop_multiple
                min_stop_spread = spread_price * cfg.min_stop_to_spread_ratio
                if stop_dist < max(min_stop_atr, min_stop_spread):
                    continue
                    
                risk_amt = equity * cfg.risk_per_trade_pct
                fx_rate_entry = fill_price if getattr(cfg, "quote_currency", "USD") != "USD" and fill_price > 0 else 1.0
                calc_lot = risk_amt / ((stop_dist / fx_rate_entry) * cfg.contract_size)
                lot_size = max(cfg.min_lot_size, min(cfg.max_lot_size, round(calc_lot, 2)))
                
                found_pat.entry_price = fill_price
                found_pat.entry_bar = i + 1
                found_pat.entry_filled = True
                found_pat.lot_size = lot_size
                open_trades.append(found_pat)
                
    if not trades:
        return {"trades": [], "scorecard": {"trades": 0, "net_profit": 0, "win_rate_pct": 0, "profit_factor": 0, "max_drawdown_pct": 0}}
        
    net_pnls = [t.net_pnl for t in trades]
    wins = sum(1 for p in net_pnls if p > 0)
    losses = sum(1 for p in net_pnls if p <= 0)
    gross_win = sum(p for p in net_pnls if p > 0)
    gross_loss = abs(sum(p for p in net_pnls if p < 0))
    
    eq_curve = [cfg.initial_equity]
    for p in net_pnls: eq_curve.append(eq_curve[-1] + p)
    peak = cfg.initial_equity
    m_dd = 0
    for val in eq_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak * 100
        if dd > m_dd: m_dd = dd
        
    scorecard = {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(wins / len(trades) * 100, 1),
        "gross_profit": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else 999.0,
        "net_profit": round(sum(net_pnls), 2),
        "total_return_pct": round(sum(net_pnls) / cfg.initial_equity * 100, 2),
        "max_drawdown_pct": round(m_dd, 1),
        "total_friction": round(sum(t.spread_cost + t.commission_cost + t.slippage_cost for t in trades), 2),
        "avg_r": round(np.mean([t.r_multiple for t in trades]), 2) if trades else 0.0,
    }
    
    return {"trades": trades, "scorecard": scorecard}
