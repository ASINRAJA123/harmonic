"""
Statistical Validation Protocol Script for Harmonic_EA_V3_Champion.
Executes all 9 sections of the Model Risk Validation Protocol:
0. 2026 vs Pre-2026 Discrepancy & Multi-Asset Pre-2025/2026 Audit
1. Walk-Forward Efficiency (WFE) (16-year rolling 3yr IS / 1yr OOS)
2. Deflated Sharpe Ratio (DSR) (Lopez de Prado formulation)
3. Monte Carlo Trade Resampling (10,000 block bootstrap iterations)
4. Portfolio Daily Strategy Return Correlation Matrix
5. 16-Year Regime Decomposition & Return Concentration Check
6. Cost-Stress Capacity Sensitivity (1x, 2x, 3x, 5x friction)
7. Per-Pattern Attribution (Cypher, Gartley, Crab, Shark)
8. Win-Rate Quality, R-Distribution & Expectancy Decomposition
9. Master Institutional Pass/Fail Scorecard
"""

import os
import sys
import glob
import math
import numpy as np
import pandas as pd
from scipy import stats

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from core.engine import HarmonicV3Config, run_harmonic_v3_backtest, resample_bars

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

EQUITY = 10_000.0

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

def calc_quick_stats(trade_list, initial_eq=EQUITY):
    if not trade_list:
        return {"trades": 0, "win_rate": 0.0, "pf": 0.0, "net_pnl": 0.0, "max_dd": 0.0, "avg_r": 0.0}
    net_pnls = [t.net_pnl for t in trade_list]
    wins = sum(1 for p in net_pnls if p > 0)
    tot = len(trade_list)
    gwin = sum(p for p in net_pnls if p > 0)
    gloss = abs(sum(p for p in net_pnls if p < 0))
    pf = gwin / gloss if gloss > 0 else 999.0
    
    eq = [initial_eq]
    for p in net_pnls: eq.append(eq[-1] + p)
    pk = initial_eq
    mdd = 0.0
    for v in eq:
        if v > pk: pk = v
        dd = (pk - v) / pk * 100
        if dd > mdd: mdd = dd
        
    return {
        "trades": tot,
        "win_rate": wins / tot * 100,
        "pf": pf,
        "net_pnl": sum(net_pnls),
        "max_dd": mdd,
        "avg_r": np.mean([t.r_multiple for t in trade_list])
    }

def main():
    print("=" * 115)
    print("HARMONIC_EA_V3_CHAMPION -- INSTITUTIONAL STATISTICAL VALIDATION SUITE")
    print("=" * 115)

    gold_raw = load_gold_data()
    gold_m15 = resample_bars(gold_raw, 15)
    print(f"Loaded Gold 16-Year M15: {len(gold_m15):,} bars ({gold_raw['time'].min()} to {gold_raw['time'].max()})")

    # Baseline 16-yr Gold Run
    cfg_base = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=EQUITY
    )
    res_base = run_harmonic_v3_backtest(gold_m15, cfg_base)
    trades_base = res_base["trades"]
    sc_base = res_base["scorecard"]
    print(f"Base 16-Yr Gold: {len(trades_base)} trades | Net Profit: ${sc_base['net_profit']:+,.2f} | Win Rate: {sc_base['win_rate_pct']}% | PF: {sc_base['profit_factor']} | Max DD: {sc_base['max_drawdown_pct']}%\n")

    # =========================================================================
    # SECTION 0: DISCREPANCY ANALYSIS (2026 vs Pre-2026)
    # =========================================================================
    print("-" * 115)
    print("SECTION 0: DISCREPANCY ANALYSIS (2026 PORTFOLIO VS PRE-2026 DATA)")
    print("-" * 115)
    
    trades_gold_pre2026 = [t for t in trades_base if (t.exit_time if t.exit_time else t.entry_time) < pd.Timestamp("2026-01-01")]
    trades_gold_2026 = [t for t in trades_base if (t.exit_time if t.exit_time else t.entry_time) >= pd.Timestamp("2026-01-01")]
    
    st_pre26 = calc_quick_stats(trades_gold_pre2026)
    st_26 = calc_quick_stats(trades_gold_2026)
    print(f"Gold 2010-2025 (Pre-2026): {st_pre26['trades']} Trades | Win Rate: {st_pre26['win_rate']:.1f}% | PF: {st_pre26['pf']:.2f} | Net: ${st_pre26['net_pnl']:+,.2f} | Max DD: {st_pre26['max_dd']:.1f}% | Avg R: {st_pre26['avg_r']:.2f}R")
    print(f"Gold 2026 (YTD):           {st_26['trades']} Trades  | Win Rate: {st_26['win_rate']:.1f}% | PF: {st_26['pf']:.2f} | Net: ${st_26['net_pnl']:+,.2f} | Max DD: {st_26['max_dd']:.1f}% | Avg R: {st_26['avg_r']:.2f}R")

    # Check CL and CRUDE (2021-2025)
    for sym_c, pt, ct, sp, sl in [("CL", 0.01, 1000.0, 3.0, 2.0), ("CRUDE", 0.01, 1000.0, 3.0, 2.0)]:
        p_c = os.path.join(DATA_DIR, f"{sym_c}_M5_max_history.csv")
        if os.path.exists(p_c):
            df_c = pd.read_csv(p_c)
            df_c["time"] = pd.to_datetime(df_c["time"])
            df_c = df_c.sort_values("time").reset_index(drop=True)
            df_c_hist = df_c[df_c["time"] < "2026-01-01"].reset_index(drop=True)
            if len(df_c_hist) > 50:
                b_c_m15 = resample_bars(df_c_hist, 15)
                cfg_c = HarmonicV3Config(
                    symbol=sym_c, point_size=pt, contract_size=ct,
                    spread_points=sp, slippage_points=sl, commission_per_lot=5.00,
                    risk_per_trade_pct=0.02, initial_equity=EQUITY
                )
                r_c = run_harmonic_v3_backtest(b_c_m15, cfg_c)
                sc_c = r_c["scorecard"]
                print(f"{sym_c} 2021-2025 (4.5 Years Pre-2026): {sc_c['trades']} Trades | Win Rate: {sc_c['win_rate_pct']:.1f}% | PF: {sc_c['profit_factor']:.2f} | Net: ${sc_c['net_profit']:+,.2f} | Max DD: {sc_c['max_drawdown_pct']:.1f}%")

    # =========================================================================
    # SECTION 1: WALK-FORWARD EFFICIENCY (WFE)
    # =========================================================================
    print("\n" + "-" * 115)
    print("SECTION 1: WALK-FORWARD EFFICIENCY (WFE) ANALYSIS (3-Year IS / 1-Year OOS)")
    print("-" * 115)
    
    start_year = 2010
    end_year = 2026
    is_window = 3
    oos_window = 1
    
    wf_folds = []
    for cur_y in range(start_year, end_year - is_window + 1):
        is_start = f"{cur_y}-01-01"
        is_end = f"{cur_y + is_window - 1}-12-31 23:59:59"
        oos_start = f"{cur_y + is_window}-01-01"
        oos_end = f"{cur_y + is_window + oos_window - 1}-12-31 23:59:59" if cur_y + is_window < end_year else "2026-08-25 23:59:59"
        
        df_is = gold_m15[(gold_m15["time"] >= is_start) & (gold_m15["time"] <= is_end)].reset_index(drop=True)
        df_oos = gold_m15[(gold_m15["time"] >= oos_start) & (gold_m15["time"] <= oos_end)].reset_index(drop=True)
        
        if len(df_is) < 100 or len(df_oos) < 50:
            continue
            
        r_is = run_harmonic_v3_backtest(df_is, cfg_base)
        r_oos = run_harmonic_v3_backtest(df_oos, cfg_base)
        
        sc_is = r_is["scorecard"]
        sc_oos = r_oos["scorecard"]
        
        is_ann_ret = (sc_is["total_return_pct"] / is_window)
        oos_dur = max(0.5, (pd.to_datetime(oos_end) - pd.to_datetime(oos_start)).days / 365.25)
        oos_ann_ret = (sc_oos["total_return_pct"] / oos_dur)
        
        wfe = oos_ann_ret / is_ann_ret if is_ann_ret > 0 else (1.0 if oos_ann_ret > 0 else 0.0)
        
        wf_folds.append({
            "Fold": f"{cur_y}-{cur_y+is_window-1} -> {cur_y+is_window}",
            "IS_Trades": sc_is["trades"],
            "IS_Win%": f"{sc_is['win_rate_pct']:.1f}%",
            "IS_PF": f"{sc_is['profit_factor']:.2f}",
            "IS_AnnRet%": f"{is_ann_ret:+.2f}%",
            "OOS_Trades": sc_oos["trades"],
            "OOS_Win%": f"{sc_oos['win_rate_pct']:.1f}%",
            "OOS_PF": f"{sc_oos['profit_factor']:.2f}",
            "OOS_AnnRet%": f"{oos_ann_ret:+.2f}%",
            "WFE": round(wfe, 2)
        })
        
    df_wf = pd.DataFrame(wf_folds)
    print(df_wf.to_string(index=False))
    avg_wfe = np.mean([f["WFE"] for f in wf_folds])
    print(f"\n>> Mean Walk-Forward Efficiency (WFE): {avg_wfe:.2f} (Threshold: >= 0.60)")
    df_wf.to_csv(os.path.join(OUTPUT_DIR, "validation_walk_forward_efficiency.csv"), index=False)

    # =========================================================================
    # SECTION 2: DEFLATED SHARPE RATIO (DSR) (Lopez de Prado)
    # =========================================================================
    print("\n" + "-" * 115)
    print("SECTION 2: DEFLATED SHARPE RATIO (DSR) (LOPEZ DE PRADO)")
    print("-" * 115)
    
    r_multiples = [t.r_multiple for t in trades_base]
    n_trades = len(r_multiples)
    mean_r = np.mean(r_multiples)
    std_r = np.std(r_multiples, ddof=1)
    
    sr_trade = mean_r / std_r if std_r > 0 else 0.0
    trades_per_year = n_trades / 16.6
    sr_ann = sr_trade * np.sqrt(trades_per_year)
    
    skew = float(stats.skew(r_multiples))
    kurt = float(stats.kurtosis(r_multiples, fisher=False))
    
    N_trials = 50
    euler_mascheroni = 0.5772156649
    
    sr_0_trade = ((1.0 - euler_mascheroni) * stats.norm.ppf(1.0 - 1.0 / N_trials) +
                  euler_mascheroni * stats.norm.ppf(1.0 - 1.0 / (N_trials * math.e)))
    sr_0_ann = sr_0_trade * np.sqrt(trades_per_year)
    
    denom = np.sqrt(1.0 - skew * sr_trade + ((kurt - 1.0) / 4.0) * (sr_trade ** 2))
    dsr_z = ((sr_trade - (sr_0_trade / np.sqrt(trades_per_year))) * np.sqrt(n_trades - 1)) / denom if denom > 0 else 0.0
    dsr_prob = float(stats.norm.cdf(dsr_z))
    
    dsr_z_trade = ((sr_trade - 0.0) * np.sqrt(n_trades - 1)) / denom if denom > 0 else 0.0
    psr_prob = float(stats.norm.cdf(dsr_z_trade))
    
    print(f"Sample Size (Gold Trades):          {n_trades}")
    print(f"Trade Return Skewness:              {skew:.3f}")
    print(f"Trade Return Kurtosis (Pearson):    {kurt:.3f}")
    print(f"Annualized Sharpe Ratio (Est):      {sr_ann:.2f} (Per-Trade Sharpe: {sr_trade:.3f})")
    print(f"Assumed Exploration Trials (N):     {N_trials}")
    print(f"Probabilistic Sharpe Ratio (PSR):   {psr_prob:.4f} (p = {1-psr_prob:.4e})")
    print(f"Deflated Sharpe Ratio (DSR):        {dsr_prob:.4f} (p = {1-dsr_prob:.4e}) (Threshold: > 0.9500)")

    # =========================================================================
    # SECTION 3: MONTE CARLO TRADE RESAMPLING (10,000 Block Bootstrap)
    # =========================================================================
    print("\n" + "-" * 115)
    print("SECTION 3: MONTE CARLO RESAMPLING (10,000 ITERATIONS, BLOCK BOOTSTRAP)")
    print("-" * 115)
    
    mc_iterations = 10_000
    block_size = 15
    n_blocks = math.ceil(n_trades / block_size)
    trade_pnls = [t.net_pnl for t in trades_base]
    
    mc_max_dds = []
    mc_end_equities = []
    mc_40_dd_count = 0
    mc_ruin_count = 0
    
    np.random.seed(42)
    blocks = []
    for b_start in range(0, n_trades - block_size + 1):
        blocks.append(trade_pnls[b_start : b_start + block_size])
        
    for _ in range(mc_iterations):
        sampled_blocks = [blocks[idx] for idx in np.random.randint(0, len(blocks), size=n_blocks)]
        sim_pnls = [p for blk in sampled_blocks for p in blk][:n_trades]
        
        sim_eq = [EQUITY]
        for p in sim_pnls:
            sim_eq.append(sim_eq[-1] + p)
            
        pk = EQUITY
        cur_mdd = 0.0
        hit_40 = False
        hit_ruin = False
        
        for val in sim_eq:
            if val > pk: pk = val
            dd = (pk - val) / pk * 100
            if dd > cur_mdd: cur_mdd = dd
            if dd >= 40.0: hit_40 = True
            if dd >= 50.0: hit_ruin = True
            
        mc_max_dds.append(cur_mdd)
        mc_end_equities.append(sim_eq[-1])
        if hit_40: mc_40_dd_count += 1
        if hit_ruin: mc_ruin_count += 1
        
    mc_dd_50 = np.percentile(mc_max_dds, 50)
    mc_dd_95 = np.percentile(mc_max_dds, 95)
    mc_dd_99 = np.percentile(mc_max_dds, 99)
    p_dd_40 = (mc_40_dd_count / mc_iterations) * 100
    p_ruin = (mc_ruin_count / mc_iterations) * 100
    
    print(f"Historical Realized Max Drawdown:    {sc_base['max_drawdown_pct']:.1f}%")
    print(f"Monte Carlo Median (50th %ile) DD:   {mc_dd_50:.1f}%")
    print(f"Monte Carlo 95th Percentile DD:      {mc_dd_95:.1f}%")
    print(f"Monte Carlo 99th Percentile DD:      {mc_dd_99:.1f}%")
    print(f"Probability of Max DD >= 40%:        {p_dd_40:.2f}% (Threshold: < 5.0% - 10.0%)")
    print(f"Probability of Ruin (DD >= 50%):     {p_ruin:.2f}%")

    # =========================================================================
    # SECTION 4: PORTFOLIO STRATEGY RETURN CORRELATION
    # =========================================================================
    print("\n" + "-" * 115)
    print("SECTION 4: PORTFOLIO STRATEGY RETURN CORRELATION MATRIX (2026)")
    print("-" * 115)
    
    instruments = {
        "XAUUSD": {"point_size": 0.01,    "contract_size": 100.0,    "spread_pts": 25.0, "slip_pts": 10.0},
        "XAGUSD": {"point_size": 0.001,   "contract_size": 5000.0,   "spread_pts": 20.0, "slip_pts": 10.0},
        "USDJPY": {"point_size": 0.001,   "contract_size": 100000.0, "spread_pts": 12.0, "slip_pts": 5.0},
        "GBPUSD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 12.0, "slip_pts": 5.0},
        "USDCAD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 14.0, "slip_pts": 5.0},
        "USDCHF": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 15.0, "slip_pts": 5.0},
        "AUDUSD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 12.0, "slip_pts": 5.0},
        "EURUSD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 10.0, "slip_pts": 5.0},
        "NZDUSD": {"point_size": 0.00001, "contract_size": 100000.0, "spread_pts": 15.0, "slip_pts": 5.0},
    }
    
    all_dates = pd.date_range("2026-01-01", "2026-08-25", freq="D")
    df_daily_pnl = pd.DataFrame(index=all_dates)
    
    for sym, spec in instruments.items():
        p_sym = os.path.join(DATA_DIR, f"{sym}_M5_max_history.csv")
        if not os.path.exists(p_sym): continue
        df_s = pd.read_csv(p_sym)
        df_s["time"] = pd.to_datetime(df_s["time"])
        df_s = df_s[(df_s["time"] >= "2026-01-01") & (df_s["time"] <= "2026-08-25 23:59:59")].reset_index(drop=True)
        if len(df_s) < 50: continue
        bars_s_m15 = resample_bars(df_s, 15)
        
        cfg_s = HarmonicV3Config(
            symbol=sym, point_size=spec["point_size"], contract_size=spec["contract_size"],
            spread_points=spec["spread_pts"], slippage_points=spec["slip_pts"], commission_per_lot=5.00,
            risk_per_trade_pct=0.02, initial_equity=EQUITY
        )
        r_s = run_harmonic_v3_backtest(bars_s_m15, cfg_s)
        
        daily_s = {d: 0.0 for d in all_dates}
        for t in r_s["trades"]:
            ts = t.exit_time if t.exit_time else t.entry_time
            if ts:
                d_key = pd.Timestamp(ts.date())
                if d_key in daily_s:
                    daily_s[d_key] += t.net_pnl
        df_daily_pnl[sym] = [daily_s[d] for d in all_dates]
        
    corr_matrix = df_daily_pnl.corr()
    print("Strategy Daily Return Correlation Matrix (2026 YTD):")
    print(corr_matrix.round(2).to_string())
    
    triu_indices = np.triu_indices_from(corr_matrix.values, k=1)
    pairwise_corrs = corr_matrix.values[triu_indices]
    pairwise_corrs_clean = pairwise_corrs[~np.isnan(pairwise_corrs)]
    avg_corr = np.mean(pairwise_corrs_clean) if len(pairwise_corrs_clean) > 0 else 0.0
    print(f"\n>> Average Pairwise Strategy Return Correlation: {avg_corr:.3f} (Threshold: < 0.40)")

    # =========================================================================
    # SECTION 5: 16-YEAR REGIME DECOMPOSITION & RETURN CONCENTRATION
    # =========================================================================
    print("\n" + "-" * 115)
    print("SECTION 5: 16-YEAR REGIME DECOMPOSITION & RETURN CONCENTRATION (2010-2026)")
    print("-" * 115)
    
    regime_tags = {
        "2010": "Post-GFC Recovery / Quantitative Easing 1",
        "2011": "Historical Gold All-Time High Volatility ($1,920 Peak)",
        "2012": "Macro Range Consolidation & QE3",
        "2013": "Fed Taper Tantrum / Massive Gold Bear Crash (-28%)",
        "2014": "Low-Volatility Bear Drift",
        "2015": "Fed Rate Hike Cycle Begins / Bear Bottom ($1,050)",
        "2016": "Brexit / US Election Volatility Rebound",
        "2017": "Ultra-Low Volatility Trend / Subdued Range",
        "2018": "Fed Balance Sheet Runoff / Quantitative Tightening",
        "2019": "Fed Pivot / Rate Cuts & Gold Breakout ($1,500)",
        "2020": "COVID-19 Global Liquidity Shock / Record Gold ATH ($2,075)",
        "2021": "Post-COVID Reopening / Range Whipsaw",
        "2022": "Aggressive Global Rate Hikes (+500 bps) / High Inflation",
        "2023": "Banking Crisis (SVB) / Geopolitical Turmoil ($2,140 ATH)",
        "2024": "Fed Rate Cut Expectations / Historic Commodity Rally ($2,700)",
        "2025": "Sustained High-Price Gold Regime",
        "2026": "2026 Current Year-To-Date",
    }
    
    yearly_rows = []
    trade_years = {}
    for t in trades_base:
        ts = t.exit_time if t.exit_time else t.entry_time
        y = str(ts.year) if ts else "Unknown"
        if y not in trade_years: trade_years[y] = []
        trade_years[y].append(t)
        
    sorted_years = sorted(trade_years.keys())
    running_equity = EQUITY
    
    for y in sorted_years:
        y_trades = trade_years[y]
        st = calc_quick_stats(y_trades, initial_eq=running_equity)
        ret_pct = (st["net_pnl"] / running_equity) * 100
        
        y_rs = [t.r_multiple for t in y_trades]
        y_sr = (np.mean(y_rs) / np.std(y_rs, ddof=1) * np.sqrt(len(y_rs))) if len(y_rs) > 1 and np.std(y_rs, ddof=1) > 0 else 0.0
        
        yearly_rows.append({
            "Year": y,
            "Trades": st["trades"],
            "Win%": f"{st['win_rate']:.1f}%",
            "PF": f"{st['pf']:.2f}" if st['pf'] < 999 else "INF",
            "Sharpe": f"{y_sr:.2f}",
            "Net PnL ($)": f"${st['net_pnl']:+,.2f}",
            "Return%": f"{ret_pct:+.2f}%",
            "Max DD%": f"{st['max_dd']:.1f}%",
            "Regime Description": regime_tags.get(y, "Macro Regime")
        })
        running_equity += st["net_pnl"]
        
    df_yearly = pd.DataFrame(yearly_rows)
    print(df_yearly.to_string(index=False))
    
    profitable_years = sum(1 for r in yearly_rows if float(r["Net PnL ($)"].replace("$","").replace(",","").replace("+","")) > 0)
    pct_profitable_years = (profitable_years / len(yearly_rows)) * 100
    print(f"\n>> Profitable Calendar Years: {profitable_years} / {len(yearly_rows)} ({pct_profitable_years:.1f}%) (Threshold: >= 75.0%)")
    
    yearly_pnls = [float(r["Net PnL ($)"].replace("$","").replace(",","").replace("+","")) for r in yearly_rows]
    best_year_idx = np.argmax(yearly_pnls)
    best_year_name = yearly_rows[best_year_idx]["Year"]
    best_year_val = yearly_pnls[best_year_idx]
    tot_profit = sum(yearly_pnls)
    pnl_without_best = tot_profit - best_year_val
    ret_without_best = (pnl_without_best / EQUITY) * 100
    
    print(f">> Total 16-Year Net PnL:             ${tot_profit:+,.2f} (+{tot_profit/EQUITY*100:.2f}%)")
    print(f">> Best Single Year ({best_year_name}):         ${best_year_val:+,.2f} ({best_year_val/tot_profit*100:.1f}% of total profit)")
    print(f">> Total PnL With Best Year Removed:  ${pnl_without_best:+,.2f} ({ret_without_best:+.2f}% ROI) (Pass if positive)")
    df_yearly.to_csv(os.path.join(OUTPUT_DIR, "validation_regime_decomposition.csv"), index=False)

    # =========================================================================
    # SECTION 6: COST-STRESS & CAPACITY SENSITIVITY TEST
    # =========================================================================
    print("\n" + "-" * 115)
    print("SECTION 6: COST-STRESS & CAPACITY SENSITIVITY (1x, 2x, 3x, 5x FRICTION)")
    print("-" * 115)
    
    cost_multipliers = [1.0, 2.0, 3.0, 5.0]
    stress_results = []
    
    for mult in cost_multipliers:
        cfg_stress = HarmonicV3Config(
            symbol="XAUUSD", point_size=0.01, contract_size=100.0,
            spread_points=25.0 * mult,
            slippage_points=10.0 * mult,
            commission_per_lot=5.00 * mult,
            risk_per_trade_pct=0.02, initial_equity=EQUITY
        )
        r_str = run_harmonic_v3_backtest(gold_m15, cfg_stress)
        sc_str = r_str["scorecard"]
        
        stress_results.append({
            "Cost Multiplier": f"{mult:.1f}x (Spread ${0.25*mult:.2f}, Comm ${5*mult:.1f}/lot)",
            "Trades": sc_str["trades"],
            "Win Rate%": f"{sc_str['win_rate_pct']:.1f}%",
            "Profit Factor": f"{sc_str['profit_factor']:.2f}",
            "Net Profit ($)": f"${sc_str['net_profit']:+,.2f}",
            "Total ROI%": f"{sc_str['total_return_pct']:+.2f}%",
            "Max DD%": f"{sc_str['max_drawdown_pct']:.1f}%",
            "Total Friction Paid": f"${sc_str['total_friction']:,.2f}"
        })
        
    df_stress = pd.DataFrame(stress_results)
    print(df_stress.to_string(index=False))
    df_stress.to_csv(os.path.join(OUTPUT_DIR, "validation_cost_stress_sensitivity.csv"), index=False)

    # =========================================================================
    # SECTION 7: PER-PATTERN ATTRIBUTION
    # =========================================================================
    print("\n" + "-" * 115)
    print("SECTION 7: PER-PATTERN ALPHA ATTRIBUTION (CYPHER, GARTLEY, CRAB, SHARK)")
    print("-" * 115)
    
    pattern_trades = {}
    for t in trades_base:
        p_type = t.pattern_type
        if p_type not in pattern_trades: pattern_trades[p_type] = []
        pattern_trades[p_type].append(t)
        
    pat_rows = []
    for p_name in ["Cypher", "Gartley", "Crab", "Shark"]:
        p_list = pattern_trades.get(p_name, [])
        if not p_list: continue
        st_p = calc_quick_stats(p_list)
        pnl_contrib = (st_p["net_pnl"] / sc_base["net_profit"]) * 100 if sc_base["net_profit"] > 0 else 0
        
        pat_rows.append({
            "Pattern": p_name,
            "Trades": st_p["trades"],
            "% of Universe": f"{st_p['trades']/len(trades_base)*100:.1f}%",
            "Win Rate%": f"{st_p['win_rate']:.1f}%",
            "Profit Factor": f"{st_p['pf']:.2f}",
            "Avg R": f"{st_p['avg_r']:.2f}R",
            "Net PnL ($)": f"${st_p['net_pnl']:+,.2f}",
            "P&L Contribution%": f"{pnl_contrib:.1f}%"
        })
        
    df_pat = pd.DataFrame(pat_rows)
    print(df_pat.to_string(index=False))
    df_pat.to_csv(os.path.join(OUTPUT_DIR, "validation_pattern_attribution.csv"), index=False)

    # =========================================================================
    # SECTION 8: WIN-RATE QUALITY, R-DISTRIBUTION & EXPECTANCY
    # =========================================================================
    print("\n" + "-" * 115)
    print("SECTION 8: WIN-RATE QUALITY, R-DISTRIBUTION & EXPECTANCY DECOMPOSITION")
    print("-" * 115)
    
    exit_reasons = {}
    for t in trades_base:
        exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1
        
    print(f"Trade Exit Reason Breakdown ({len(trades_base)} Trades):")
    for reason, cnt in sorted(exit_reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  * {reason:<12}: {cnt:>4} trades ({cnt/len(trades_base)*100:5.1f}%)")
        
    win_trades = [t for t in trades_base if t.net_pnl > 0]
    loss_trades = [t for t in trades_base if t.net_pnl <= 0]
    
    avg_win_r = np.mean([t.r_multiple for t in win_trades]) if win_trades else 0.0
    avg_loss_r = abs(np.mean([t.r_multiple for t in loss_trades])) if loss_trades else 0.0
    win_pct_dec = len(win_trades) / len(trades_base)
    loss_pct_dec = len(loss_trades) / len(trades_base)
    
    expectancy_r = (win_pct_dec * avg_win_r) - (loss_pct_dec * avg_loss_r)
    
    print(f"\nExpectancy Metrics:")
    print(f"  * Average Win R-Multiple:     +{avg_win_r:.2f}R")
    print(f"  * Average Loss R-Multiple:    -{avg_loss_r:.2f}R")
    print(f"  * Win Rate:                   {win_pct_dec*100:.1f}%")
    print(f"  * Mathematical Expectancy (E): +{expectancy_r:.3f}R / trade (Threshold: > 0.15R)")

    # =========================================================================
    # SECTION 9: MASTER INSTITUTIONAL VALIDATION SCORECARD
    # =========================================================================
    print("\n" + "=" * 115)
    print("MASTER INSTITUTIONAL VALIDATION SCORECARD SUMMARY")
    print("=" * 115)
    
    scorecard_items = [
        ("Walk-Forward Efficiency", f"{avg_wfe:.2f}", ">= 0.60", "PASS" if avg_wfe >= 0.60 else "FAIL"),
        ("Deflated Sharpe Ratio (DSR)", f"{dsr_prob:.4f}", "> 0.9500", "PASS" if dsr_prob > 0.95 else "FAIL"),
        ("Monte Carlo P(DD > 40%)", f"{p_dd_40:.2f}%", "< 5.0% - 10.0%", "PASS" if p_dd_40 < 10.0 else "FAIL"),
        ("Portfolio Return Correlation", f"{avg_corr:.3f}", "< 0.40", "PASS" if avg_corr < 0.40 else "FAIL"),
        ("Regime Consistency (16-Yr)", f"{pct_profitable_years:.1f}% ({profitable_years}/17 yrs)", ">= 75.0%", "PASS" if pct_profitable_years >= 75.0 else "FAIL"),
        ("Cost Stress (PF @ 2x Costs)", f"{stress_results[1]['Profit Factor']}", "> 1.20", "PASS" if float(stress_results[1]['Profit Factor']) > 1.20 else "FAIL"),
        ("Return Concentration", f"${pnl_without_best:+,.2f} ({ret_without_best:+.1f}%)", "Clearly Positive", "PASS" if pnl_without_best > 0 else "FAIL"),
        ("Mathematical Expectancy", f"+{expectancy_r:.3f}R", "> +0.15R", "PASS" if expectancy_r > 0.15 else "FAIL"),
    ]
    
    df_final = pd.DataFrame(scorecard_items, columns=["Validation Test", "Realized Metric", "Pass Threshold", "Final Status"])
    print(df_final.to_string(index=False))
    df_final.to_csv(os.path.join(OUTPUT_DIR, "master_validation_scorecard.csv"), index=False)
    print(f"\nAll statistical validation reports successfully exported to: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
