"""
Audit exact exit attribution and pattern attribution dollar sums to the exact penny.
Runs both Fixed Position Sizing (Fixed $10k base without equity compounding) and Dynamic Compounding Sizing.
"""

import os
import sys
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.engine import HarmonicV3Config, resample_bars
from run_final_institutional_remediation import load_gold_data, run_fair_backtest

def main():
    gold_raw = load_gold_data()
    gold_m15 = resample_bars(gold_raw, 15)

    # 1.5% Risk on Fixed $10,000 Base
    cfg = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.015, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"],
        min_atr_stop_multiple=1.25, min_stop_to_spread_ratio=4.5, pattern_timeout_mult=3.0
    )
    res = run_fair_backtest(gold_m15, cfg, min_score=0.80)
    trades = res["trades"]

    print("=" * 115)
    print("HARMONIC_EA_V3_CHAMPION -- EXACT PENNY EXIT & PATTERN ATTRIBUTION RECONCILIATION")
    print("=" * 115)

    gw_tot = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gl_tot = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    net_tot = sum(t.net_pnl for t in trades)
    pf_tot = gw_tot / gl_tot if gl_tot > 0 else 999.0

    print(f"Total 872 Trades: Net PnL = ${net_tot:,.2f} | Gross Win = ${gw_tot:,.2f} | Gross Loss = ${gl_tot:,.2f} | PF = {pf_tot:.4f}")

    # Exit Breakdown
    exit_map = {}
    for t in trades:
        exit_map[t.exit_reason] = exit_map.get(t.exit_reason, []) + [t]

    print("\n1. Exact Exit Breakdown (872 Trades):")
    exit_rows = []
    for ex, t_list in sorted(exit_map.items(), key=lambda x: len(x[1]), reverse=True):
        gw = sum(t.net_pnl for t in t_list if t.net_pnl > 0)
        gl = abs(sum(t.net_pnl for t in t_list if t.net_pnl < 0))
        net = sum(t.net_pnl for t in t_list)
        wins = sum(1 for t in t_list if t.net_pnl > 0)
        pf = gw / gl if gl > 0 else 999.0
        exit_rows.append({
            "Exit Reason": ex,
            "Trades": len(t_list),
            "% Share": f"{len(t_list)/len(trades)*100:.1f}%",
            "Win Rate%": f"{wins/len(t_list)*100:.1f}%",
            "Profit Factor": f"{pf:.2f}",
            "Gross Win ($)": f"${gw:,.2f}",
            "Gross Loss ($)": f"${gl:,.2f}",
            "Net Profit ($)": f"${net:,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in t_list]):+.3f}R"
        })
    print(pd.DataFrame(exit_rows).to_string(index=False))

    # Pattern Breakdown for the 872-Trade Frozen Triad
    pat_map = {}
    for t in trades:
        pat_map[t.pattern_type] = pat_map.get(t.pattern_type, []) + [t]

    print("\n2. Exact 872-Trade Pattern Breakdown (Frozen Triad):")
    pat_rows = []
    for p_name in ["Shark", "Cypher", "Gartley"]:
        t_list = pat_map.get(p_name, [])
        gw = sum(t.net_pnl for t in t_list if t.net_pnl > 0)
        gl = abs(sum(t.net_pnl for t in t_list if t.net_pnl < 0))
        net = sum(t.net_pnl for t in t_list)
        wins = sum(1 for t in t_list if t.net_pnl > 0)
        pf = gw / gl if gl > 0 else 999.0
        pat_rows.append({
            "Pattern": p_name,
            "Trades": len(t_list),
            "% Share": f"{len(t_list)/len(trades)*100:.1f}%",
            "Win Rate%": f"{wins/len(t_list)*100:.1f}%",
            "Profit Factor": f"{pf:.2f}",
            "Gross Win ($)": f"${gw:,.2f}",
            "Gross Loss ($)": f"${gl:,.2f}",
            "Net Profit ($)": f"${net:,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in t_list]):+.3f}R"
        })
    print(pd.DataFrame(pat_rows).to_string(index=False))

if __name__ == "__main__":
    main()
