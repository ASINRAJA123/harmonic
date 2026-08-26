"""
Run full 2026 YTD backtest (Jan 1, 2026 to Aug 25, 2026) across all available assets.
Calculates exact monthly returns, total portfolio PnL, Win Rate, and Drawdown.
"""

import os
import sys
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.config import HarmonicRatios, PATTERN_MAP, ALL_PATTERNS, PATTERN_TARGETS, compute_target_price
from core.pattern_scanner import _ratio_valid, HarmonicPattern
from core.engine import HarmonicV3Config, HarmonicV3Trade, resample_bars, compute_atr, compute_h1_trend_bias

DATA_DIR = os.path.join(BASE_DIR, "data")

INSTRUMENTS_2026 = {
    "XAUUSD": {"file": "years/xauusd_2026.csv", "pt": 0.01,    "ct": 100.0,    "sp": 25.0, "sl": 10.0, "name": "Gold (Spot)"},
    "XAGUSD": {"file": "XAGUSD_M5_max_history.csv", "pt": 0.001,   "ct": 5000.0,   "sp": 20.0, "sl": 10.0, "name": "Silver (Spot)"},
    "CL":     {"file": "CL_M5_max_history.csv",     "pt": 0.01,    "ct": 1000.0,   "sp": 3.0,  "sl": 2.0,  "name": "Crude Oil"},
    "EURUSD": {"file": "EURUSD_M5_max_history.csv", "pt": 0.00001, "ct": 100000.0, "sp": 10.0, "sl": 5.0,  "name": "EUR/USD"},
    "GBPUSD": {"file": "GBPUSD_M5_max_history.csv", "pt": 0.00001, "ct": 100000.0, "sp": 12.0, "sl": 5.0,  "name": "GBP/USD"},
    "USDJPY": {"file": "USDJPY_M5_max_history.csv", "pt": 0.001,   "ct": 100000.0, "sp": 12.0, "sl": 5.0,  "name": "USD/JPY"},
    "AUDUSD": {"file": "AUDUSD_M5_max_history.csv", "pt": 0.00001, "ct": 100000.0, "sp": 12.0, "sl": 5.0,  "name": "AUD/USD"},
    "USDCAD": {"file": "USDCAD_M5_max_history.csv", "pt": 0.00001, "ct": 100000.0, "sp": 14.0, "sl": 5.0,  "name": "USD/CAD"},
    "USDCHF": {"file": "USDCHF_M5_max_history.csv", "pt": 0.00001, "ct": 100000.0, "sp": 15.0, "sl": 5.0,  "name": "USD/CHF"},
}

from run_final_reconciliation import validate_pattern_fair, run_fair_backtest

def main():
    print("=" * 115)
    print("HARMONIC_EA_V3_CHAMPION -- FULL 2026 YTD AUDIT (JAN 1, 2026 TO AUG 25, 2026)")
    print("=" * 115)

    asset_trades_2026 = {}
    summaries_2026 = []
    all_trades_2026 = []

    for sym, spec in INSTRUMENTS_2026.items():
        p = os.path.join(DATA_DIR, spec["file"])
        if not os.path.exists(p): continue
        df = pd.read_csv(p)
        df["time"] = pd.to_datetime(df["time"]).sort_values().reset_index(drop=True)
        df_26 = df[(df["time"] >= "2026-01-01") & (df["time"] <= "2026-08-25 23:59:59")].reset_index(drop=True)
        if len(df_26) < 50: continue
        bars_m15 = resample_bars(df_26, 15)

        cfg = HarmonicV3Config(
            symbol=sym, point_size=spec["pt"], contract_size=spec["ct"],
            spread_points=spec["sp"], slippage_points=spec["sl"], commission_per_lot=5.00,
            risk_per_trade_pct=0.015, initial_equity=10_000.0,
            enabled_patterns=["Shark", "Cypher", "Gartley"]
        )
        res = run_fair_backtest(bars_m15, cfg, min_score=0.80)
        t_list = res["trades"]
        asset_trades_2026[sym] = t_list
        all_trades_2026.extend(t_list)

        sc = res["scorecard"]
        summaries_2026.append({
            "Asset": sym,
            "Name": spec["name"],
            "Bars M5": len(df_26),
            "Date Range": f"{df_26['time'].min().strftime('%Y-%m-%d')} to {df_26['time'].max().strftime('%Y-%m-%d')}",
            "Trades": sc.get("trades", 0),
            "Win Rate%": f"{sc.get('win_rate_pct', 0):.1f}%",
            "Profit Factor": f"{sc.get('profit_factor', 0):.2f}",
            "Net Profit ($10k Base)": f"${sc.get('net_profit', 0):+,.2f}",
            "ROI %": f"{sc.get('total_return_pct', 0):+.2f}%",
            "Max DD%": f"{sc.get('max_drawdown_pct', 0):.1f}%"
        })

    print(pd.DataFrame(summaries_2026).to_string(index=False))

    # Combined 2026 Portfolio
    all_trades_2026.sort(key=lambda t: t.exit_time if t.exit_time else t.entry_time)
    daily_dates_26 = pd.date_range("2026-01-01", "2026-08-25", freq="D")
    daily_pnl_26 = {d: 0.0 for d in daily_dates_26}
    for t in all_trades_2026:
        ts = t.exit_time if t.exit_time else t.entry_time
        if ts:
            d_k = pd.Timestamp(ts.date())
            if d_k in daily_pnl_26: daily_pnl_26[d_k] += t.net_pnl

    s_pnl_26 = pd.Series(daily_pnl_26)
    eq_26 = [10_000.0]
    for p in s_pnl_26.values: eq_26.append(eq_26[-1] + p)
    pk_26 = 10_000.0
    mdd_26 = 0.0
    for v in eq_26:
        if v > pk_26: pk_26 = v
        dd = (pk_26 - v) / pk_26 * 100
        if dd > mdd_26: mdd_26 = dd

    tot_comb_net = sum(s_pnl_26.values)
    comb_trades = len(all_trades_2026)
    comb_wins = sum(1 for t in all_trades_2026 if t.net_pnl > 0)
    comb_gw = sum(t.net_pnl for t in all_trades_2026 if t.net_pnl > 0)
    comb_gl = abs(sum(t.net_pnl for t in all_trades_2026 if t.net_pnl < 0))
    comb_pf = comb_gw / comb_gl if comb_gl > 0 else 999.0

    print("\n--- COMBINED 2026 YTD MULTI-ASSET PORTFOLIO RESULTS (JAN 1 TO AUG 25, 2026) ---")
    print(f"  Total Trades Across 2026 Portfolio: {comb_trades}")
    print(f"  Portfolio Win Rate:                 {comb_wins/comb_trades*100:.1f}% ({comb_wins} Wins / {comb_trades-comb_wins} Losses)")
    print(f"  Portfolio Profit Factor:            {comb_pf:.2f}")
    print(f"  Portfolio Realized Net Profit:      ${tot_comb_net:+,.2f} (+{tot_comb_net/10_000.0*100:+.2f}% ROI on $10k base)")
    print(f"  Portfolio Maximum Drawdown:         {mdd_26:.1f}%")

    # Monthly breakdown for 2026
    monthly_pnl_26 = {}
    for d, p in daily_pnl_26.items():
        m_k = d.strftime('%Y-%m')
        monthly_pnl_26[m_k] = monthly_pnl_26.get(m_k, 0.0) + p

    print("\n2026 Month-by-Month Combined Portfolio Returns (Jan to Aug 2026):")
    month_rows = []
    for m_k, pnl in sorted(monthly_pnl_26.items()):
        month_rows.append({
            "Month": m_k,
            "Net Profit ($10k Base)": f"${pnl:+,.2f}",
            "Monthly ROI %": f"{pnl/10_000.0*100:+.2f}%"
        })
    print(pd.DataFrame(month_rows).to_string(index=False))

if __name__ == "__main__":
    main()
