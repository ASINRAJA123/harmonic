"""
Standalone Runner — 2026 Multi-Pair Champion Portfolio.
Can be run directly on any machine: python run_2026_portfolio.py
"""

import os
import sys
import pandas as pd
import numpy as np

# Add local directory to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.engine import HarmonicV3Config, run_harmonic_v3_backtest, resample_bars

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

EQUITY = 10_000.0

INSTRUMENTS = {
    "XAUUSD": {"point_size": 0.01,    "contract_size": 100.0,    "spread_pts": 25.0, "slip_pts": 10.0, "category": "Precious Metals"},
    "XAGUSD": {"point_size": 0.001,   "contract_size": 5000.0,   "spread_pts": 20.0, "slip_pts": 10.0, "category": "Precious Metals"},
    "USDJPY": {"point_size": 0.001,   "contract_size": 100000.0, "spread_pts": 12.0, "slip_pts": 5.0,  "category": "Forex Major"},
    "GBPUSD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 12.0, "slip_pts": 5.0,  "category": "Forex Major"},
    "USDCAD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 14.0, "slip_pts": 5.0,  "category": "Forex Major"},
    "USDCHF": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 15.0, "slip_pts": 5.0,  "category": "Forex Major"},
    "AUDUSD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 12.0, "slip_pts": 5.0,  "category": "Forex Major"},
    "EURUSD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 10.0, "slip_pts": 5.0,  "category": "Forex Major"},
    "NZDUSD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 15.0, "slip_pts": 5.0,  "category": "Forex Major"},
}

def load_data(symbol: str):
    path = os.path.join(DATA_DIR, f"{symbol}_M5_max_history.csv")
    if not os.path.exists(path): return None
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    df = df[(df["time"] >= "2026-01-01") & (df["time"] <= "2026-08-25 23:59:59")].reset_index(drop=True)
    return df

def main():
    print("=" * 115)
    print("HARMONIC_EA_V3_CHAMPION -- 2026 MULTI-PAIR PORTFOLIO AUDIT")
    print("Period: Jan 1, 2026 to Aug 25, 2026 | Timeframe: M15")
    print("Strictly Post-Friction (Real ECN Spreads + $5.00/lot Commission + Slippage)")
    print("=" * 115)
    
    pair_summaries = []
    all_trades = []
    
    for sym, spec in INSTRUMENTS.items():
        raw_m5 = load_data(sym)
        if raw_m5 is None or len(raw_m5) < 50:
            continue
        bars_m15 = resample_bars(raw_m5, 15)
        
        cfg = HarmonicV3Config(
            symbol=sym,
            point_size=spec["point_size"],
            contract_size=spec["contract_size"],
            spread_points=spec["spread_pts"],
            slippage_points=spec["slip_pts"],
            commission_per_lot=5.00,
            risk_per_trade_pct=0.02,
            initial_equity=EQUITY
        )
        
        res = run_harmonic_v3_backtest(bars_m15, cfg)
        sc = res["scorecard"]
        trades = res["trades"]
        all_trades.extend(trades)
        
        pair_summaries.append({
            "Symbol": sym,
            "Category": spec["category"],
            "Trades": sc.get("trades", 0),
            "Win Rate %": f"{sc.get('win_rate_pct', 0):.1f}%",
            "Profit Factor": f"{sc.get('profit_factor', 0):.2f}",
            "Gross Alpha ($)": f"${sc.get('gross_profit', 0) - sc.get('gross_loss', 0):+,.2f}",
            "Friction Cost ($)": f"-${sc.get('total_friction', 0):,.2f}",
            "Net Profit ($)": f"${sc.get('net_profit', 0):+,.2f}",
            "Net Return %": f"{sc.get('total_return_pct', 0):+.2f}%",
            "Max DD %": f"{sc.get('max_drawdown_pct', 0):.1f}%",
            "Avg R": f"{sc.get('avg_r', 0):.2f}R"
        })
        
    df_pairs = pd.DataFrame(pair_summaries)
    print("\n" + "=" * 115)
    print("INDIVIDUAL INSTRUMENT POST-FRICTION PERFORMANCE (2026 YTD)")
    print("=" * 115)
    print(df_pairs.to_string(index=False))
    
    if all_trades:
        net_pnls = [t.net_pnl for t in all_trades]
        wins = sum(1 for p in net_pnls if p > 0)
        tot = len(all_trades)
        gross_win = sum(p for p in net_pnls if p > 0)
        gross_loss = abs(sum(p for p in net_pnls if p < 0))
        
        eq_curve = [EQUITY]
        for p in net_pnls: eq_curve.append(eq_curve[-1] + p)
        peak = EQUITY
        m_dd = 0
        for val in eq_curve:
            if val > peak: peak = val
            dd = (peak - val) / peak * 100
            if dd > m_dd: m_dd = dd
            
        print("\n--------------------------------------------------------------------------------------------------------------")
        print(f"2026 CONSOLIDATED CHAMPION PORTFOLIO:")
        print(f"  • Total Trades Executed:     {tot} (~{tot/33.0:.1f} trades/week across portfolio)")
        print(f"  • Portfolio Win Rate:        {wins/tot*100:.1f}% ({wins} Wins / {tot - wins} Losses)")
        print(f"  • Portfolio Profit Factor:   {gross_win/gross_loss:.2f}")
        print(f"  • Net Realized Return:       +{sum(net_pnls)/EQUITY*100:.2f}% ROI (+${sum(net_pnls):+,.2f} Net Cash Profit)")
        print(f"  • Maximum Portfolio DD:      {m_dd:.1f}%")
        print(f"  • Total Friction Paid:       -${sum(t.spread_cost + t.commission_cost + t.slippage_cost for t in all_trades):,.2f}")
        print("--------------------------------------------------------------------------------------------------------------")
        
        # Monthly breakdown
        rows_m = []
        for t in all_trades:
            ts = t.exit_time if t.exit_time is not None else t.entry_time
            m_str = ts.strftime("%Y-%m") if ts is not None else "Unknown"
            rows_m.append({"month": m_str, "pnl": t.net_pnl, "win": 1 if t.net_pnl > 0 else 0})
        df_m = pd.DataFrame(rows_m)
        
        monthly_table = []
        eq_run = EQUITY
        for m, g in df_m.groupby("month"):
            m_pnl = g["pnl"].sum()
            m_cnt = len(g)
            m_w = g["win"].sum()
            g_win = g[g["pnl"] > 0]["pnl"].sum()
            g_loss = abs(g[g["pnl"] < 0]["pnl"].sum())
            pf = g_win / g_loss if g_loss > 0 else 999.0
            monthly_table.append({
                "Month": m, "Trades": m_cnt, "Wins": m_w, "Losses": m_cnt - m_w, "Win Rate %": f"{m_w/m_cnt*100:.1f}%",
                "Profit Factor": f"{pf:.2f}" if pf != 999.0 else "INF",
                "Net PnL ($)": f"${m_pnl:+,.2f}", "Return %": f"{m_pnl/eq_run*100:+.2f}%"
            })
            eq_run += m_pnl
            
        print("\n" + "=" * 115)
        print("2026 MONTH-BY-MONTH POST-FRICTION PORTFOLIO AUDIT")
        print("=" * 115)
        print(pd.DataFrame(monthly_table).to_string(index=False))
        
        df_pairs.to_csv(os.path.join(OUTPUT_DIR, "2026_portfolio_pairs_summary.csv"), index=False)
        pd.DataFrame(monthly_table).to_csv(os.path.join(OUTPUT_DIR, "2026_portfolio_monthly.csv"), index=False)
        print(f"\n✅ Output CSVs saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
