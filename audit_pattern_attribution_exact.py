"""
Exact Pattern Attribution Audit Script.
Runs both:
1. 6-Pattern Simultaneous Run (to see exact Butterfly, Crab, Bat, Shark, Cypher, Gartley stats).
2. 3-Pattern Frozen Triad Simultaneous Run (Shark, Cypher, Gartley).
3. 6 Standalone Isolated Runs (each pattern alone).
Logs all trade counts, win rates, PF, Net PnL, gross wins, and gross losses at both 1.5% and 2.0% risk.
"""

import os
import sys
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.config import HarmonicRatios, PATTERN_MAP
from core.engine import HarmonicV3Config, resample_bars
from run_final_institutional_remediation import load_gold_data, run_fair_backtest

def main():
    gold_raw = load_gold_data()
    gold_m15 = resample_bars(gold_raw, 15)

    print("=" * 115)
    print("HARMONIC_EA_V3_CHAMPION -- EXACT PATTERN ATTRIBUTION FORENSIC RECONCILIATION")
    print("=" * 115)

    # 1. 6-Pattern Simultaneous Run (Shark, Cypher, Gartley, Bat, Butterfly, Crab) at 2.0% Risk
    cfg_6_pat_20 = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=10_000.0,
        enabled_patterns=["Cypher", "Gartley", "Crab", "Shark", "Bat", "Butterfly"],
        min_atr_stop_multiple=1.25, min_stop_to_spread_ratio=4.5, pattern_timeout_mult=3.0
    )
    res_6_20 = run_fair_backtest(gold_m15, cfg_6_pat_20, min_score=0.80)
    t_6_20 = res_6_20["trades"]
    sc_6_20 = res_6_20["scorecard"]

    print("\n--- 1. 6-PATTERN SIMULTANEOUS RUN (2.0% Risk, min_score=0.80) ---")
    print(f"Total Trades: {sc_6_20['trades']} | Win Rate: {sc_6_20['win_rate_pct']}% | PF: {sc_6_20['profit_factor']} | Net: ${sc_6_20['net_profit']:+,.2f} | Max DD: {sc_6_20['max_drawdown_pct']}%")

    pat_map_6 = {}
    for t in t_6_20:
        pat_map_6[t.pattern_type] = pat_map_6.get(t.pattern_type, []) + [t]

    pat_6_rows = []
    for p_name in ["Shark", "Cypher", "Gartley", "Bat", "Butterfly", "Crab"]:
        p_list = pat_map_6.get(p_name, [])
        if not p_list:
            pat_6_rows.append({"Pattern": p_name, "Trades": 0, "% Share": "0.0%", "Win Rate%": "0.0%", "Profit Factor": "0.00", "Gross Win ($)": "$0.00", "Gross Loss ($)": "$0.00", "Net Profit ($)": "$0.00", "Avg R": "0.00R"})
            continue
        net_pnls = [t.net_pnl for t in p_list]
        wins = sum(1 for p in net_pnls if p > 0)
        tot = len(p_list)
        gw = sum(p for p in net_pnls if p > 0)
        gl = abs(sum(p for p in net_pnls if p < 0))
        pf = gw / gl if gl > 0 else 999.0
        pat_6_rows.append({
            "Pattern": p_name,
            "Trades": tot,
            "% Share": f"{tot/len(t_6_20)*100:.1f}%",
            "Win Rate%": f"{wins/tot*100:.1f}%",
            "Profit Factor": f"{pf:.2f}",
            "Gross Win ($)": f"${gw:,.2f}",
            "Gross Loss ($)": f"${gl:,.2f}",
            "Net Profit ($)": f"${sum(net_pnls):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in p_list]):+.3f}R"
        })
    print(pd.DataFrame(pat_6_rows).to_string(index=False))

    # 2. 3-Pattern Frozen Triad Simultaneous Run (Shark, Cypher, Gartley) at 1.5% Risk
    cfg_3_pat_15 = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.015, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"],
        min_atr_stop_multiple=1.25, min_stop_to_spread_ratio=4.5, pattern_timeout_mult=3.0
    )
    res_3_15 = run_fair_backtest(gold_m15, cfg_3_pat_15, min_score=0.80)
    t_3_15 = res_3_15["trades"]
    sc_3_15 = res_3_15["scorecard"]

    print("\n--- 2. 3-PATTERN FROZEN TRIAD SIMULTANEOUS RUN (1.5% Risk, min_score=0.80) ---")
    print(f"Total Trades: {sc_3_15['trades']} | Win Rate: {sc_3_15['win_rate_pct']}% | PF: {sc_3_15['profit_factor']} | Net: ${sc_3_15['net_profit']:+,.2f} | Max DD: {sc_3_15['max_drawdown_pct']}%")

    pat_map_3 = {}
    for t in t_3_15:
        pat_map_3[t.pattern_type] = pat_map_3.get(t.pattern_type, []) + [t]

    pat_3_rows = []
    for p_name in ["Shark", "Cypher", "Gartley"]:
        p_list = pat_map_3.get(p_name, [])
        if not p_list: continue
        net_pnls = [t.net_pnl for t in p_list]
        wins = sum(1 for p in net_pnls if p > 0)
        tot = len(p_list)
        gw = sum(p for p in net_pnls if p > 0)
        gl = abs(sum(p for p in net_pnls if p < 0))
        pf = gw / gl if gl > 0 else 999.0
        pat_3_rows.append({
            "Pattern": p_name,
            "Trades": tot,
            "% Share": f"{tot/len(t_3_15)*100:.1f}%",
            "Win Rate%": f"{wins/tot*100:.1f}%",
            "Profit Factor": f"{pf:.2f}",
            "Gross Win ($)": f"${gw:,.2f}",
            "Gross Loss ($)": f"${gl:,.2f}",
            "Net Profit ($)": f"${sum(net_pnls):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in p_list]):+.3f}R"
        })
    print(pd.DataFrame(pat_3_rows).to_string(index=False))

    # 3. 3-Pattern Frozen Triad at 2.0% Risk
    cfg_3_pat_20 = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"],
        min_atr_stop_multiple=1.25, min_stop_to_spread_ratio=4.5, pattern_timeout_mult=3.0
    )
    res_3_20 = run_fair_backtest(gold_m15, cfg_3_pat_20, min_score=0.80)
    t_3_20 = res_3_20["trades"]
    sc_3_20 = res_3_20["scorecard"]

    print("\n--- 3. 3-PATTERN FROZEN TRIAD SIMULTANEOUS RUN (2.0% Risk, min_score=0.80) ---")
    print(f"Total Trades: {sc_3_20['trades']} | Win Rate: {sc_3_20['win_rate_pct']}% | PF: {sc_3_20['profit_factor']} | Net: ${sc_3_20['net_profit']:+,.2f} | Max DD: {sc_3_20['max_drawdown_pct']}%")

    pat_map_3_20 = {}
    for t in t_3_20:
        pat_map_3_20[t.pattern_type] = pat_map_3_20.get(t.pattern_type, []) + [t]

    pat_3_20_rows = []
    for p_name in ["Shark", "Cypher", "Gartley"]:
        p_list = pat_map_3_20.get(p_name, [])
        if not p_list: continue
        net_pnls = [t.net_pnl for t in p_list]
        wins = sum(1 for p in net_pnls if p > 0)
        tot = len(p_list)
        gw = sum(p for p in net_pnls if p > 0)
        gl = abs(sum(p for p in net_pnls if p < 0))
        pf = gw / gl if gl > 0 else 999.0
        pat_3_20_rows.append({
            "Pattern": p_name,
            "Trades": tot,
            "% Share": f"{tot/len(t_3_20)*100:.1f}%",
            "Win Rate%": f"{wins/tot*100:.1f}%",
            "Profit Factor": f"{pf:.2f}",
            "Gross Win ($)": f"${gw:,.2f}",
            "Gross Loss ($)": f"${gl:,.2f}",
            "Net Profit ($)": f"${sum(net_pnls):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in p_list]):+.3f}R"
        })
    print(pd.DataFrame(pat_3_20_rows).to_string(index=False))

if __name__ == "__main__":
    main()
