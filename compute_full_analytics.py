"""
Comprehensive quantitative data analytics generator for Harmonic_EA_V3_Champion.
Computes:
1. Master Institutional Metrics: Sharpe, Sortino, Calmar, Payoff, Recovery Factor, Skewness, Kurtosis.
2. 16.6-Year Day-of-Week Distribution (Mon-Fri).
3. 16.6-Year Hourly Execution Distribution (13:00 to 20:00 UTC).
4. Directional Long vs Short Performance.
5. Exit Reason Attribution and Holding Time Statistics.
6. Trade Velocity: Avg trades per week, per month, per year.
"""

import os
import sys
import math
import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.engine import HarmonicV3Config, resample_bars
from run_final_reconciliation import load_gold_data, run_fair_backtest

def main():
    gold_raw = load_gold_data()
    bars_m15 = resample_bars(gold_raw, 15)

    cfg = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"]
    )
    res = run_fair_backtest(bars_m15, cfg, min_score=0.80)
    trades = res["trades"]
    sc = res["scorecard"]

    print("=" * 115)
    print("HARMONIC_EA_V3_CHAMPION -- INSTITUTIONAL DATA ANALYTICS & METRICS SUITE")
    print("=" * 115)

    net_pnls = [t.net_pnl for t in trades]
    r_multiples = [t.r_multiple for t in trades]
    wins = [p for p in net_pnls if p > 0]
    losses = [p for p in net_pnls if p < 0]

    # Master Metrics
    tot_trades = len(trades)
    tot_net = sum(net_pnls)
    tot_gw = sum(wins)
    tot_gl = abs(sum(losses))
    pf = tot_gw / tot_gl if tot_gl > 0 else 999.0
    win_rate = len(wins) / tot_trades * 100
    avg_win = np.mean(wins) if wins else 0.0
    avg_loss = abs(np.mean(losses)) if losses else 0.0
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 999.0
    avg_r = np.mean(r_multiples)

    # Sharpe, Sortino, Calmar
    mean_r = np.mean(r_multiples)
    std_r = np.std(r_multiples, ddof=1)
    sr_trade = mean_r / std_r
    sr_ann = sr_trade * np.sqrt(tot_trades / 16.6)

    downside_r = [min(0.0, r) for r in r_multiples]
    downside_dev = np.sqrt(np.mean(np.array(downside_r) ** 2))
    sortino_trade = mean_r / downside_dev if downside_dev > 0 else 0.0
    sortino_ann = sortino_trade * np.sqrt(tot_trades / 16.6)

    mdd_pct = sc["max_drawdown_pct"]
    ann_roi_pct = (tot_net / 10_000.0 * 100) / 16.6
    calmar_ratio = ann_roi_pct / mdd_pct if mdd_pct > 0 else 0.0
    recovery_factor = tot_net / (10_000.0 * (mdd_pct / 100.0)) if mdd_pct > 0 else 0.0

    skew_val = float(stats.skew(r_multiples))
    kurt_val = float(stats.kurtosis(r_multiples, fisher=False))

    # Consecutive Wins & Losses
    max_cw = 0
    max_cl = 0
    cur_cw = 0
    cur_cl = 0
    for p in net_pnls:
        if p > 0:
            cur_cw += 1
            cur_cl = 0
            if cur_cw > max_cw: max_cw = cur_cw
        elif p < 0:
            cur_cl += 1
            cur_cw = 0
            if cur_cl > max_cl: max_cl = cur_cl

    # Trade Duration in Bars & Hours
    durations_bars = [(t.exit_bar - t.entry_bar) for t in trades if t.exit_bar and t.entry_bar]
    avg_dur_bars = np.mean(durations_bars)
    avg_dur_hours = avg_dur_bars * 15 / 60.0

    print(f"\n1. MASTER QUANTITATIVE & RISK METRICS (16.6 Years, n = {tot_trades} trades):")
    print(f"  • Annualized Sharpe Ratio:    {sr_ann:.2f} (Per-Trade Sharpe: {sr_trade:.4f})")
    print(f"  • Annualized Sortino Ratio:   {sortino_ann:.2f} (Downside Dev: {downside_dev:.4f})")
    print(f"  • Calmar Ratio:               {calmar_ratio:.2f} (Annual ROI {ann_roi_pct:.2f}% / Max DD {mdd_pct:.1f}%)")
    print(f"  • Recovery Factor:            {recovery_factor:.2f}")
    print(f"  • Profit Factor:              {pf:.2f} (Gross Win: ${tot_gw:,.2f} / Gross Loss: ${tot_gl:,.2f})")
    print(f"  • Win Rate:                   {win_rate:.1f}% ({len(wins)} Wins / {len(losses)} Losses)")
    print(f"  • Payoff Ratio:               {payoff_ratio:.2f} (Avg Win: ${avg_win:.2f} / Avg Loss: ${avg_loss:.2f})")
    print(f"  • Average Expectancy / Trade: {avg_r:+.4f}R (+${tot_net/tot_trades:.2f})")
    print(f"  • Distribution Skewness:      {skew_val:+.4f}")
    print(f"  • Pearson Kurtosis:           {kurt_val:.4f}")
    print(f"  • Max Consecutive Wins:       {max_cw} trades")
    print(f"  • Max Consecutive Losses:     {max_cl} trades")
    print(f"  • Avg Trade Duration:         {avg_dur_bars:.1f} M15 bars ({avg_dur_hours:.1f} hours)")
    print(f"  • Trade Velocity:             ~{tot_trades/16.6:.1f} trades/yr (~{tot_trades/(16.6*52):.2f} trades/week, ~{tot_trades/(16.6*12):.1f} trades/month)")

    # 2. 16.6-Year Day-of-Week Breakdown
    days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}
    dow_analytics = []
    for d_idx, d_name in days_map.items():
        d_trades = [t for t in trades if (t.entry_time if t.entry_time else t.exit_time).weekday() == d_idx]
        if not d_trades: continue
        dpnls = [t.net_pnl for t in d_trades]
        dw = sum(1 for p in dpnls if p > 0)
        dl = sum(1 for p in dpnls if p < 0)
        dgw = sum(p for p in dpnls if p > 0)
        dgl = abs(sum(p for p in dpnls if p < 0))
        dpf = dgw / dgl if dgl > 0 else 999.0
        dow_analytics.append({
            "Day of Week": d_name,
            "Trades": len(d_trades),
            "% Share": f"{len(d_trades)/tot_trades*100:.1f}%",
            "Win Rate %": f"{dw/len(d_trades)*100:.1f}%",
            "Profit Factor": f"{dpf:.2f}",
            "Net Profit ($)": f"${sum(dpnls):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in d_trades]):+.3f}R"
        })
    print("\n2. 16.6-YEAR DAY-OF-WEEK PERFORMANCE ANALYTICS:")
    print(pd.DataFrame(dow_analytics).to_string(index=False))

    # 3. 16.6-Year Hourly Session Breakdown (13:00 to 20:00 UTC)
    hourly_analytics = []
    for h in sorted(list(set((t.entry_time if t.entry_time else t.exit_time).hour for t in trades))):
        h_trades = [t for t in trades if (t.entry_time if t.entry_time else t.exit_time).hour == h]
        hpnls = [t.net_pnl for t in h_trades]
        hw = sum(1 for p in hpnls if p > 0)
        hgw = sum(p for p in hpnls if p > 0)
        hgl = abs(sum(p for p in hpnls if p < 0))
        hpf = hgw / hgl if hgl > 0 else 999.0
        hourly_analytics.append({
            "Entry Hour (UTC)": f"{h:02d}:00 UTC",
            "Session Phase": "NY Cash Open" if h in [13, 14] else ("London/NY Overlap" if h in [15, 16] else "NY Afternoon Trend"),
            "Trades": len(h_trades),
            "% Share": f"{len(h_trades)/tot_trades*100:.1f}%",
            "Win Rate %": f"{hw/len(h_trades)*100:.1f}%",
            "Profit Factor": f"{hpf:.2f}",
            "Net Profit ($)": f"${sum(hpnls):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in h_trades]):+.3f}R"
        })
    print("\n3. 16.6-YEAR HOURLY SESSION ANALYTICS (GOLDEN WINDOW):")
    print(pd.DataFrame(hourly_analytics).to_string(index=False))

    # 4. Long vs Short Directional Alpha
    long_trades = [t for t in trades if t.bull]
    short_trades = [t for t in trades if not t.bull]
    dir_analytics = []
    for d_name, d_list in [("LONG (Bullish)", long_trades), ("SHORT (Bearish)", short_trades)]:
        dpnls = [t.net_pnl for t in d_list]
        dw = sum(1 for p in dpnls if p > 0)
        dgw = sum(p for p in dpnls if p > 0)
        dgl = abs(sum(p for p in dpnls if p < 0))
        dpf = dgw / dgl if dgl > 0 else 999.0
        dir_analytics.append({
            "Direction": d_name,
            "Trades": len(d_list),
            "% Share": f"{len(d_list)/tot_trades*100:.1f}%",
            "Win Rate %": f"{dw/len(d_list)*100:.1f}%",
            "Profit Factor": f"{dpf:.2f}",
            "Net Profit ($)": f"${sum(dpnls):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in d_list]):+.3f}R"
        })
    print("\n4. LONG VS SHORT DIRECTIONAL ALPHA BREAKDOWN:")
    print(pd.DataFrame(dir_analytics).to_string(index=False))

    # 5. Exit Reason Attribution
    exit_map = {}
    for t in trades:
        exit_map[t.exit_reason] = exit_map.get(t.exit_reason, []) + [t]
    exit_analytics = []
    for ex_name, ex_list in sorted(exit_map.items(), key=lambda x: len(x[1]), reverse=True):
        epnls = [t.net_pnl for t in ex_list]
        ew = sum(1 for p in epnls if p > 0)
        egw = sum(p for p in epnls if p > 0)
        egl = abs(sum(p for p in epnls if p < 0))
        epf = egw / egl if egl > 0 else 999.0
        exit_analytics.append({
            "Exit Type": ex_name,
            "Trades": len(ex_list),
            "% Share": f"{len(ex_list)/tot_trades*100:.1f}%",
            "Win Rate %": f"{ew/len(ex_list)*100:.1f}%",
            "Profit Factor": f"{epf:.2f}",
            "Net Profit ($)": f"${sum(epnls):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in ex_list]):+.3f}R"
        })
    print("\n5. TRADE EXIT ATTRIBUTION ANALYTICS:")
    print(pd.DataFrame(exit_analytics).to_string(index=False))

if __name__ == "__main__":
    main()
