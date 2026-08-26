"""
Standalone Runner — 16-Year Historical Gold (XAUUSD) Master Audit (2010 - August 25, 2026).
Can be run directly on any machine: python run_gold_16year.py
"""

import os
import glob
import sys
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.engine import HarmonicV3Config, run_harmonic_v3_backtest, resample_bars

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

EQUITY = 10_000.0

def load_gold_history():
    print("  Loading 16-year XAUUSD historical dataset (2010 - 2026)...", flush=True)
    frames = []
    
    # Load years from data/years/
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
    print(f"  Dataset Loaded: {len(df_all):,} M5 bars from {df_all['time'].min()} to {df_all['time'].max()}", flush=True)
    return df_all

def main():
    print("=" * 115)
    print("HARMONIC_EA_V3_CHAMPION -- 16-YEAR HISTORICAL GOLD AUDIT (2010 - 2026)")
    print("Strictly Post-Friction (Spread $0.25/oz, Commission $5.00/lot, Slippage)")
    print("=" * 115)
    
    df_raw = load_gold_history()
    bars_m15 = resample_bars(df_raw, 15)
    print(f"  Resampled to M15: {len(bars_m15):,} bars.", flush=True)
    
    cfg = HarmonicV3Config(
        symbol="XAUUSD",
        point_size=0.01,
        contract_size=100.0,
        spread_points=25.0,
        slippage_points=10.0,
        commission_per_lot=5.00,
        risk_per_trade_pct=0.02,
        initial_equity=EQUITY
    )
    
    print("\n  Executing 16-Year Backtest...", flush=True)
    res = run_harmonic_v3_backtest(bars_m15, cfg)
    sc = res["scorecard"]
    trades = res["trades"]
    
    span_years = (df_raw["time"].max() - df_raw["time"].min()).days / 365.25
    cagr = (( (EQUITY + sc["net_profit"]) / EQUITY ) ** (1.0 / span_years) - 1.0) * 100
    
    print("\n" + "=" * 115)
    print("16-YEAR POST-FRICTION PERFORMANCE SCORECARD (2010 - 2026)")
    print("=" * 115)
    print(f"  • Total Duration:            {df_raw['time'].min().strftime('%Y-%m-%d')} to {df_raw['time'].max().strftime('%Y-%m-%d')} ({span_years:.1f} Years)")
    print(f"  • Starting Capital:          ${EQUITY:,.2f}")
    print(f"  • Ending Net Capital:        ${EQUITY + sc['net_profit']:,.2f}")
    print(f"  • Net Realized Profit:       ${sc['net_profit']:+,.2f} ({sc['total_return_pct']:+.2f}% Total ROI)")
    print(f"  • Compound Annual CAGR:      {cagr:.2f}% / year")
    print(f"  • Total Trades Executed:     {sc['trades']:,} (~{sc['trades']/span_years:.1f} trades/year | ~{sc['trades']/(span_years*52):.1f} trades/week)")
    print(f"  • 16-Year Win Rate:          {sc['win_rate_pct']:.1f}% ({sc['wins']} Wins / {sc['losses']} Losses)")
    print(f"  • Profit Factor:             {sc['profit_factor']:.2f}")
    print(f"  • Maximum Drawdown:          {sc['max_drawdown_pct']:.1f}%")
    print(f"  • Total Friction Absorbed:   -${sc['total_friction']:,.2f}")
    print("=" * 115)
    
    rows_y = []
    for t in trades:
        ts = t.exit_time if t.exit_time is not None else t.entry_time
        y_str = str(ts.year) if ts is not None else "Unknown"
        rows_y.append({
            "year": y_str, "net_pnl": t.net_pnl, "gross_pnl": t.gross_pnl,
            "friction": t.spread_cost + t.commission_cost + t.slippage_cost,
            "win": 1 if t.net_pnl > 0 else 0, "r": t.r_multiple
        })
    df_y_t = pd.DataFrame(rows_y)
    
    yearly_table = []
    eq_gold_run = EQUITY
    for y, g in df_y_t.groupby("year"):
        y_pnl = g["net_pnl"].sum()
        y_cnt = len(g)
        y_w = g["win"].sum()
        g_w = g[g["net_pnl"] > 0]["net_pnl"].sum()
        g_l = abs(g[g["net_pnl"] < 0]["net_pnl"].sum())
        pf = g_w / g_l if g_l > 0 else 999.0
        
        eq_c = [eq_gold_run]
        for p in g["net_pnl"].values: eq_c.append(eq_c[-1] + p)
        pk = eq_gold_run
        m_dd_y = 0
        for v in eq_c:
            if v > pk: pk = v
            dd = (pk - v) / pk * 100
            if dd > m_dd_y: m_dd_y = dd
            
        yearly_table.append({
            "Year": y, "Trades": y_cnt, "Wins": y_w, "Losses": y_cnt - y_w, "Win Rate %": f"{y_w/y_cnt*100:.1f}%",
            "Gross Alpha ($)": f"${g['gross_pnl'].sum():+,.2f}", "Friction Cost ($)": f"-${g['friction'].sum():,.2f}",
            "Net Profit ($)": f"${y_pnl:+,.2f}", "Profit Factor": f"{pf:.2f}" if pf != 999.0 else "INF",
            "Annual Return %": f"{y_pnl/eq_gold_run*100:+.2f}%", "Max DD %": f"{m_dd_y:.1f}%",
            "Ending Equity ($)": f"${eq_gold_run + y_pnl:,.2f}"
        })
        eq_gold_run += y_pnl
        
    print("\n" + "=" * 115)
    print("YEAR-BY-YEAR 16-YEAR POST-FRICTION GOLD AUDIT TABLE (2010 - 2026)")
    print("=" * 115)
    print(pd.DataFrame(yearly_table).to_string(index=False))
    
    pd.DataFrame(yearly_table).to_csv(os.path.join(OUTPUT_DIR, "gold_16yr_yearly_audit.csv"), index=False)
    
    df_trades = pd.DataFrame([{
        "Trade ID": t.trade_id, "Symbol": t.symbol, "Pattern": t.pattern_type, "Direction": t.direction,
        "Entry Time": str(t.entry_time), "Entry Price": t.entry_price, "Exit Time": str(t.exit_time),
        "Exit Price": t.exit_price, "Exit Reason": t.exit_reason, "Lot Size": t.lot_size,
        "Gross PnL ($)": round(t.gross_pnl, 2), "Spread Cost ($)": round(t.spread_cost, 2),
        "Comm Cost ($)": round(t.commission_cost, 2), "Net PnL ($)": round(t.net_pnl, 2), "R": round(t.r_multiple, 2)
    } for t in trades])
    df_trades.to_csv(os.path.join(OUTPUT_DIR, "gold_16yr_all_trades.csv"), index=False)
    print(f"\n✅ Output CSVs saved to: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
