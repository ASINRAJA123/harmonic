"""
Forensic reconciliation script to verify:
1. Exact parameter execution (Gate 3: 1.25x ATR, 4.5x Spread; Gate 4: 3.0x PatternLen; Gate 6: 1.5% Risk).
2. Trade count reconciliation (858 standalone individual vs combined argmax run).
3. Profitable years calculation (14 of 17 = 82.4%).
4. Standalone Gold horizon vs Multi-Asset horizon.
"""

import os
import sys
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.config import HarmonicRatios, PATTERN_MAP
from core.pattern_scanner import _ratio_valid, HarmonicPattern
from core.engine import HarmonicV3Config, HarmonicV3Trade, resample_bars, compute_atr, compute_h1_trend_bias
from run_final_reconciliation import load_gold_data, run_fair_backtest

def main():
    gold_raw = load_gold_data()
    bars_m15 = resample_bars(gold_raw, 15)

    print("=" * 115)
    print("HARMONIC_EA_V3_CHAMPION -- RECONCILIATION AUDIT")
    print("=" * 115)

    # 1. Test Combined 3-Pattern Run with Frozen Parameters at 1.5% risk
    cfg_15 = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.015, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"],
        min_atr_stop_multiple=1.25,
        min_stop_to_spread_ratio=4.5,
        pattern_timeout_mult=3.0
    )
    res_15 = run_fair_backtest(bars_m15, cfg_15, min_score=0.80)
    trades_15 = res_15["trades"]
    sc_15 = res_15["scorecard"]

    # 2. Test Combined 3-Pattern Run at 2.0% risk
    cfg_20 = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"],
        min_atr_stop_multiple=1.25,
        min_stop_to_spread_ratio=4.5,
        pattern_timeout_mult=3.0
    )
    res_20 = run_fair_backtest(bars_m15, cfg_20, min_score=0.80)
    trades_20 = res_20["trades"]
    sc_20 = res_20["scorecard"]

    print(f"\n--- COMBINED 3-PATTERN TEST (FROZEN: Gate 3=1.25x/4.5x, Gate 4=3.0x, Score>=0.80) ---")
    print(f"1.5% Risk: Trades = {len(trades_15)} | Win Rate = {sc_15['win_rate_pct']:.1f}% | PF = {sc_15['profit_factor']:.2f} | Net PnL = ${sc_15['net_profit']:+,.2f} | Max DD = {sc_15['max_drawdown_pct']:.1f}%")
    print(f"2.0% Risk: Trades = {len(trades_20)} | Win Rate = {sc_20['win_rate_pct']:.1f}% | PF = {sc_20['profit_factor']:.2f} | Net PnL = ${sc_20['net_profit']:+,.2f} | Max DD = {sc_20['max_drawdown_pct']:.1f}%")

    # Check Standalone Pattern counts when run individually vs combined
    print(f"\n--- STANDALONE INDIVIDUAL RUNS (NO COLLISION / ISOLATED) ---")
    individual_counts = {}
    for pat in ["Shark", "Cypher", "Gartley", "Bat", "Butterfly", "Crab"]:
        cfg_p = HarmonicV3Config(
            symbol="XAUUSD", point_size=0.01, contract_size=100.0,
            spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
            risk_per_trade_pct=0.015, initial_equity=10_000.0,
            enabled_patterns=[pat],
            min_atr_stop_multiple=1.25,
            min_stop_to_spread_ratio=4.5,
            pattern_timeout_mult=3.0
        )
        res_p = run_fair_backtest(bars_m15, cfg_p, min_score=0.80)
        t_p = res_p["trades"]
        sc_p = res_p["scorecard"]
        individual_counts[pat] = len(t_p)
        print(f"  {pat:<10}: {len(t_p):>4} trades | Win Rate = {sc_p['win_rate_pct']:>5.1f}% | PF = {sc_p['profit_factor']:>5.2f} | Net PnL = ${sc_p['net_profit']:>10,.2f}")

    sum_3_ind = individual_counts["Shark"] + individual_counts["Cypher"] + individual_counts["Gartley"]
    print(f"\nSum of 3 Independent Runs: Shark ({individual_counts['Shark']}) + Cypher ({individual_counts['Cypher']}) + Gartley ({individual_counts['Gartley']}) = {sum_3_ind} trades")
    print(f"Combined Simultaneous Execution (with argmax pattern selection & Gate 7 Concurrency limit): {len(trades_15)} trades")
    print(f"Difference: {len(trades_15) - sum_3_ind:+d} trades")

    # Year-by-Year breakdown for 1.5% risk
    yearly_pnl = {}
    yearly_trades = {}
    yearly_wins = {}
    yearly_losses = {}
    for t in trades_15:
        ts = t.exit_time if t.exit_time else t.entry_time
        yr = ts.year
        yearly_pnl[yr] = yearly_pnl.get(yr, 0.0) + t.net_pnl
        yearly_trades[yr] = yearly_trades.get(yr, 0) + 1
        if t.net_pnl > 0: yearly_wins[yr] = yearly_wins.get(yr, 0) + 1
        elif t.net_pnl < 0: yearly_losses[yr] = yearly_losses.get(yr, 0) + 1

    print("\n--- EXACT YEAR-BY-YEAR SCORECARD (1.5% Risk) ---")
    pos_years = 0
    tot_years = len(yearly_pnl)
    for yr in sorted(yearly_pnl.keys()):
        pnl = yearly_pnl[yr]
        tr = yearly_trades[yr]
        w = yearly_wins.get(yr, 0)
        l = yearly_losses.get(yr, 0)
        wr = w / tr * 100 if tr > 0 else 0.0
        if pnl > 0: pos_years += 1
        print(f"  {yr}: {tr:>3} trades | {w:>2}W / {l:>2}L ({wr:>5.1f}%) | Net PnL = ${pnl:>10,.2f} | {'PROFIT' if pnl > 0 else 'LOSS'}")

    print(f"\nProfitable Calendar Years: {pos_years} of {tot_years} years ({pos_years/tot_years*100:.1f}%)")

if __name__ == "__main__":
    main()
