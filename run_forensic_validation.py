"""
Forensic Validation Script for Harmonic_EA_V3_Champion.
Answers all 17 specific questions across the 5 forensic audit categories:
1. WFE / Fold Instability (Q1 to Q4)
2. Correlation Matrix & Sparsity (Q5 to Q7)
3. Cost-Stress Fixed-Trades vs Adaptive Gate 3 (Q8 & Q9)
4. Pattern Scanner Candidate Audit (Crab/Shark/Cypher/Gartley) (Q10 to Q12)
5. DSR Formula, Granularity, & N-Sensitivity (Q13 to Q15)
6. Expectancy Breakdown & Yearly Trend (Q16 & Q17)
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

from core.config import HarmonicRatios, PATTERN_MAP, ALL_PATTERNS
from core.pattern_scanner import HarmonicPattern, validate_pattern
from core.engine import HarmonicV3Config, run_harmonic_v3_backtest, resample_bars, compute_atr, compute_h1_trend_bias

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

def main():
    print("=" * 115, flush=True)
    print("HARMONIC_EA_V3_CHAMPION -- FORENSIC AUDIT SUITE (17-POINT DEEP DIVE)", flush=True)
    print("=" * 115, flush=True)

    gold_raw = load_gold_data()
    gold_m15 = resample_bars(gold_raw, 15)
    
    cfg_base = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=EQUITY
    )
    res_base = run_harmonic_v3_backtest(gold_m15, cfg_base)
    trades_base = res_base["trades"]

    # =========================================================================
    # PART 1: WFE / FOLD INSTABILITY (Q1 - Q4)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("PART 1: WFE & FOLD INSTABILITY (Q1 to Q4)", flush=True)
    print("=" * 115, flush=True)

    df_wfe = pd.read_csv(os.path.join(OUTPUT_DIR, "validation_walk_forward_efficiency.csv"))
    df_wfe["OOS_Num"] = df_wfe["OOS_AnnRet%"].str.replace("%","").astype(float)
    df_wfe_sorted = df_wfe.sort_values("OOS_Num", ascending=False).reset_index(drop=True)
    
    print("\n--- Q1: Fold-by-Fold Table Sorted by OOS Return ---", flush=True)
    print(df_wfe_sorted[["Fold", "IS_Trades", "IS_Win%", "IS_PF", "IS_AnnRet%", "OOS_Trades", "OOS_Win%", "OOS_PF", "OOS_AnnRet%", "WFE"]].to_string(index=False), flush=True)
    
    median_wfe = float(np.median(df_wfe["WFE"]))
    mean_wfe = float(np.mean(df_wfe["WFE"]))
    print(f"\n>> Mean WFE:   {mean_wfe:.2f}", flush=True)
    print(f">> Median WFE: {median_wfe:.2f}", flush=True)

    # Q2: Characterize negative OOS folds (2014, 2017, 2018)
    print("\n--- Q2: Characteristics of Negative OOS Folds (2014, 2017, 2018) ---", flush=True)
    neg_years = ["2014", "2017", "2018"]
    gold_raw["year"] = gold_raw["time"].dt.year
    for y in neg_years:
        df_y = gold_raw[gold_raw["year"] == int(y)].copy()
        highs = df_y["high"].values
        lows = df_y["low"].values
        closes = df_y["close"].values
        tr = np.maximum(highs - lows, np.maximum(abs(highs - np.roll(closes, 1)), abs(lows - np.roll(closes, 1))))[1:]
        mean_atr_m5 = np.mean(tr)
        df_daily = df_y.set_index("time").resample("D").agg({"close": "last"}).dropna()
        daily_returns = df_daily["close"].pct_change().dropna()
        ann_vol = np.std(daily_returns) * np.sqrt(252) * 100
        y_trades = [t for t in trades_base if (t.exit_time if t.exit_time else t.entry_time).year == int(y)]
        net_pnl = sum(t.net_pnl for t in y_trades)
        win_rate = sum(1 for t in y_trades if t.net_pnl > 0) / len(y_trades) * 100 if y_trades else 0
        
        print(f"Year {y}: M5 Mean ATR: ${mean_atr_m5:.2f} | Annualized Vol: {ann_vol:.1f}% | Trades: {len(y_trades)} | Win Rate: {win_rate:.1f}% | Net PnL: ${net_pnl:+,.2f}", flush=True)
        print(f"        Macro Regime: {'Low-Volatility Bear Drift' if y=='2014' else ('Ultra-Low Vol Trend Compression' if y=='2017' else 'Fed QT Balance Sheet Runoff')}", flush=True)

    # Q3 & Q4: Outlier Fold Check (2018-2020 -> 2021)
    print("\n--- Q3 & Q4: Outlier Fold Check (2018-2020 -> 2021) ---", flush=True)
    fold_2021 = df_wfe[df_wfe["Fold"].str.contains("2021")].iloc[0]
    print(f"Fold 2018-2020 -> 2021: IS Ann Return = {fold_2021['IS_AnnRet%']}, OOS Ann Return = {fold_2021['OOS_AnnRet%']}, WFE = {fold_2021['WFE']}", flush=True)
    print(f"Explanation: IS was +3.45%/yr (due to 2018 drag), while OOS 2021 was +22.61%/yr. Ratio = 22.61 / 3.45 = 6.55.", flush=True)
    
    df_wfe_no_outlier = df_wfe[~df_wfe["Fold"].str.contains("2021")]
    mean_wfe_no_outlier = float(np.mean(df_wfe_no_outlier["WFE"]))
    median_wfe_no_outlier = float(np.median(df_wfe_no_outlier["WFE"]))
    print(f">> Mean WFE (Excluding 2021 Outlier):   {mean_wfe_no_outlier:.2f} (Pass Threshold: >= 0.60)", flush=True)
    print(f">> Median WFE (Excluding 2021 Outlier): {median_wfe_no_outlier:.2f}", flush=True)

    # =========================================================================
    # PART 2: CORRELATION MATRIX & SPARSITY (Q5 - Q7)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("PART 2: CORRELATION MATRIX & SPARSITY AUDIT (Q5 to Q7)", flush=True)
    print("=" * 115, flush=True)

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

    all_dates_2026 = pd.date_range("2026-01-01", "2026-08-25", freq="D")
    pair_trades = {}
    pair_daily_pnl = pd.DataFrame(index=all_dates_2026)

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
        pair_trades[sym] = r_s["trades"]
        
        daily_s = {d: 0.0 for d in all_dates_2026}
        for t in r_s["trades"]:
            ts = t.exit_time if t.exit_time else t.entry_time
            if ts:
                d_key = pd.Timestamp(ts.date())
                if d_key in daily_s:
                    daily_s[d_key] += t.net_pnl
        pair_daily_pnl[sym] = [daily_s[d] for d in all_dates_2026]

    total_calendar_days = len(all_dates_2026)
    non_zero_per_day = (pair_daily_pnl != 0).sum(axis=1)
    all_zero_days = (non_zero_per_day == 0).sum()
    days_with_1_trade = (non_zero_per_day == 1).sum()
    days_with_2plus_trades = (non_zero_per_day >= 2).sum()
    
    print("\n--- Q5: Day Sparsity Audit in 2026 Daily Return Series ---", flush=True)
    print(f"Total Calendar Days Evaluated (2026 YTD):   {total_calendar_days}", flush=True)
    print(f"Days With ZERO Trades Across ALL 9 Pairs:   {all_zero_days} ({all_zero_days/total_calendar_days*100:.1f}%)", flush=True)
    print(f"Days With Exactly 1 Active Pair:            {days_with_1_trade} ({days_with_1_trade/total_calendar_days*100:.1f}%)", flush=True)
    print(f"Days With >= 2 Pairs Simultaneously Active: {days_with_2plus_trades} ({days_with_2plus_trades/total_calendar_days*100:.1f}%)", flush=True)

    print("\n--- Q6: Trade-Level Overlap & Co-Movement Matrix (On Active Overlap Days Only) ---", flush=True)
    sym_list = list(instruments.keys())
    overlap_report = []
    
    for i in range(len(sym_list)):
        for j in range(i + 1, len(sym_list)):
            s1, s2 = sym_list[i], sym_list[j]
            active_both = pair_daily_pnl[(pair_daily_pnl[s1] != 0) & (pair_daily_pnl[s2] != 0)]
            n_overlap_days = len(active_both)
            if n_overlap_days >= 3:
                corr_sub = float(np.corrcoef(active_both[s1], active_both[s2])[0, 1])
                both_win = len(active_both[(active_both[s1] > 0) & (active_both[s2] > 0)])
                both_loss = len(active_both[(active_both[s1] < 0) & (active_both[s2] < 0)])
                divergent = n_overlap_days - both_win - both_loss
                co_move_pct = (both_win + both_loss) / n_overlap_days * 100
            else:
                corr_sub = np.nan
                both_win = len(active_both[(active_both[s1] > 0) & (active_both[s2] > 0)]) if n_overlap_days > 0 else 0
                both_loss = len(active_both[(active_both[s1] < 0) & (active_both[s2] < 0)]) if n_overlap_days > 0 else 0
                divergent = n_overlap_days - both_win - both_loss
                co_move_pct = (both_win + both_loss) / n_overlap_days * 100 if n_overlap_days > 0 else 0.0
                
            overlap_report.append({
                "Pair": f"{s1} / {s2}",
                "Overlap Days": n_overlap_days,
                "Both Win": both_win,
                "Both Loss": both_loss,
                "Divergent": divergent,
                "Co-Movement%": f"{co_move_pct:.1f}%",
                "Overlap Corr": f"{corr_sub:.2f}" if not np.isnan(corr_sub) else "N/A (<3 days)"
            })
    df_overlap = pd.DataFrame(overlap_report)
    print(df_overlap[df_overlap["Overlap Days"] > 0].to_string(index=False), flush=True)

    # Q7: Multi-Year Gold + Crude Oil Overlap (2021–2025)
    print("\n--- Q7: Multi-Year Gold + Crude Oil Overlap Correlation (2021–2025) ---", flush=True)
    p_cl = os.path.join(DATA_DIR, "CL_M5_max_history.csv")
    if os.path.exists(p_cl):
        df_cl = pd.read_csv(p_cl)
        df_cl["time"] = pd.to_datetime(df_cl["time"])
        df_cl_2125 = df_cl[(df_cl["time"] >= "2021-01-01") & (df_cl["time"] <= "2025-12-31 23:59:59")].reset_index(drop=True)
        bars_cl_m15 = resample_bars(df_cl_2125, 15)
        
        cfg_cl = HarmonicV3Config(
            symbol="CL", point_size=0.01, contract_size=1000.0,
            spread_points=3.0, slippage_points=2.0, commission_per_lot=5.00,
            risk_per_trade_pct=0.02, initial_equity=EQUITY
        )
        r_cl = run_harmonic_v3_backtest(bars_cl_m15, cfg_cl)
        
        df_gold_2125 = gold_m15[(gold_m15["time"] >= "2021-01-01") & (gold_m15["time"] <= "2025-12-31 23:59:59")].reset_index(drop=True)
        r_gold = run_harmonic_v3_backtest(df_gold_2125, cfg_base)
        
        dates_2125 = pd.date_range("2021-01-01", "2025-12-31", freq="D")
        pnl_cl_d = {d: 0.0 for d in dates_2125}
        pnl_gold_d = {d: 0.0 for d in dates_2125}
        
        for t in r_cl["trades"]:
            ts = t.exit_time if t.exit_time else t.entry_time
            if ts and pd.Timestamp(ts.date()) in pnl_cl_d: pnl_cl_d[pd.Timestamp(ts.date())] += t.net_pnl
            
        for t in r_gold["trades"]:
            ts = t.exit_time if t.exit_time else t.entry_time
            if ts and pd.Timestamp(ts.date()) in pnl_gold_d: pnl_gold_d[pd.Timestamp(ts.date())] += t.net_pnl
            
        df_overlap_2125 = pd.DataFrame({"CL": [pnl_cl_d[d] for d in dates_2125], "Gold": [pnl_gold_d[d] for d in dates_2125]}, index=dates_2125)
        full_corr_2125 = df_overlap_2125.corr().iloc[0, 1]
        
        active_both_2125 = df_overlap_2125[(df_overlap_2125["CL"] != 0) & (df_overlap_2125["Gold"] != 0)]
        active_corr_2125 = active_both_2125.corr().iloc[0, 1] if len(active_both_2125) > 1 else 0.0
        
        print(f"5-Year CL Trades: {len(r_cl['trades'])} | Gold Trades: {len(r_gold['trades'])}", flush=True)
        print(f"Full 5-Year Daily Strategy Correlation:        {full_corr_2125:+.3f}", flush=True)
        print(f"Simultaneous Active Overlap Days ({len(active_both_2125)} days) Corr: {active_corr_2125:+.3f}", flush=True)

    # =========================================================================
    # PART 3: COST-STRESS AUDIT (Q8 & Q9)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("PART 3: COST-STRESS AUDIT -- FIXED TRADES VS ADAPTIVE GATE 3 (Q8 & Q9)", flush=True)
    print("=" * 115, flush=True)

    print("\n--- Q8: Scenario A (Fixed Trade Set = Exactly 985 Trades) ---", flush=True)
    fixed_stress = []
    
    for mult in [1.0, 2.0, 3.0, 5.0]:
        net_pnls_mult = []
        for t in trades_base:
            lots = t.lot_size
            spread_c = (cfg_base.spread_points * mult) * cfg_base.point_size * cfg_base.contract_size * lots
            comm_c = (cfg_base.commission_per_lot * mult) * lots
            slip_points = (cfg_base.slippage_points * mult) if "SL" in t.exit_reason else 0.0
            slip_c = slip_points * cfg_base.point_size * cfg_base.contract_size * lots
            fric = spread_c + comm_c + slip_c
            net_pnls_mult.append(t.gross_pnl - fric)
            
        wins_m = sum(1 for p in net_pnls_mult if p > 0)
        gwin_m = sum(p for p in net_pnls_mult if p > 0)
        gloss_m = abs(sum(p for p in net_pnls_mult if p < 0))
        pf_m = gwin_m / gloss_m if gloss_m > 0 else 999.0
        tot_net_m = sum(net_pnls_mult)
        
        eq_m = [EQUITY]
        for p in net_pnls_mult: eq_m.append(eq_m[-1] + p)
        pk_m = EQUITY
        mdd_m = 0.0
        for v in eq_m:
            if v > pk_m: pk_m = v
            dd = (pk_m - v) / pk_m * 100
            if dd > mdd_m: mdd_m = dd
            
        fixed_stress.append({
            "Multiplier": f"{mult:.1f}x (Spread ${0.25*mult:.2f}, Comm ${5*mult:.1f}/lot)",
            "Trades": len(trades_base),
            "Win Rate%": f"{wins_m/len(trades_base)*100:.1f}%",
            "Profit Factor": f"{pf_m:.2f}",
            "Net Profit ($)": f"${tot_net_m:+,.2f}",
            "ROI%": f"{tot_net_m/EQUITY*100:+.2f}%",
            "Max DD%": f"{mdd_m:.1f}%"
        })
    print(pd.DataFrame(fixed_stress).to_string(index=False), flush=True)

    print("\n--- Q9: Scenario B (Adaptive Gate 3 -- Entry Filter Expands with Spread) ---", flush=True)
    adaptive_stress = []
    for mult in [1.0, 2.0, 3.0, 5.0]:
        cfg_str = HarmonicV3Config(
            symbol="XAUUSD", point_size=0.01, contract_size=100.0,
            spread_points=25.0 * mult, slippage_points=10.0 * mult, commission_per_lot=5.00 * mult,
            risk_per_trade_pct=0.02, initial_equity=EQUITY
        )
        r_str = run_harmonic_v3_backtest(gold_m15, cfg_str)
        sc_str = r_str["scorecard"]
        adaptive_stress.append({
            "Multiplier": f"{mult:.1f}x (Spread ${0.25*mult:.2f}, Comm ${5*mult:.1f}/lot)",
            "Trades Passed": sc_str["trades"],
            "Trades Rejected by Floor": len(trades_base) - sc_str["trades"],
            "Win Rate%": f"{sc_str['win_rate_pct']:.1f}%",
            "Profit Factor": f"{sc_str['profit_factor']:.2f}",
            "Net Profit ($)": f"${sc_str['net_profit']:+,.2f}",
            "ROI%": f"{sc_str['total_return_pct']:+.2f}%",
            "Max DD%": f"{sc_str['max_drawdown_pct']:.1f}%"
        })
    print(pd.DataFrame(adaptive_stress).to_string(index=False), flush=True)

    # =========================================================================
    # PART 4: PATTERN ATTRIBUTION & SCANNER AUDIT (Q10 - Q12)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("PART 4: PATTERN SCANNER CANDIDATE AUDIT & RATIO VERIFICATION (Q10 to Q12)", flush=True)
    print("=" * 115, flush=True)

    n = len(gold_m15)
    highs = gold_m15["high"].values
    lows = gold_m15["low"].values
    times = gold_m15["time"].values
    
    pivots_confirmed_at = [[] for _ in range(n)]
    for R in cfg_base.pivot_lengths:
        for p in range(R, n - R):
            is_high = True
            for j in range(1, R + 1):
                if highs[p - j] > highs[p] or highs[p + j] > highs[p]:
                    is_high = False
                    break
            if is_high:
                conf_bar = p + R
                if conf_bar < n: pivots_confirmed_at[conf_bar].append((p, highs[p], "high", R))
                
            is_low = True
            for j in range(1, R + 1):
                if lows[p - j] < lows[p] or lows[p + j] < lows[p]:
                    is_low = False
                    break
            if is_low:
                conf_bar = p + R
                if conf_bar < n: pivots_confirmed_at[conf_bar].append((p, lows[p], "low", R))
                
    known_highs = []
    known_lows = []
    
    all_candidates = {p.name: [] for p in ALL_PATTERNS}
    
    for i in range(20, n):
        current_time = pd.Timestamp(times[i])
        for (p_idx, p_price, p_type, radius) in pivots_confirmed_at[i]:
            if p_type == "high": known_highs.append((p_idx, p_price))
            else: known_lows.append((p_idx, p_price))
        if len(known_highs) > 40: known_highs = known_highs[-40:]
        if len(known_lows) > 40: known_lows = known_lows[-40:]
        
        # Session gate filter
        if current_time.hour < cfg_base.session_start_hour or current_time.hour >= cfg_base.session_end_hour:
            continue
            
        for (dI, dP, dType, radius) in pivots_confirmed_at[i]:
            bull = (dType == "low")
            c_cands = [p for p in (known_highs if bull else known_lows) if p[0] < dI]
            b_cands = [p for p in (known_lows if bull else known_highs) if p[0] < dI]
            a_cands = [p for p in (known_highs if bull else known_lows) if p[0] < dI]
            x_cands = [p for p in (known_lows if bull else known_highs) if p[0] < dI]
            
            c_cands.sort(key=lambda x: x[0], reverse=True)
            b_cands.sort(key=lambda x: x[0], reverse=True)
            a_cands.sort(key=lambda x: x[0], reverse=True)
            x_cands.sort(key=lambda x: x[0], reverse=True)
            
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
                            
                            for p_def in ALL_PATTERNS:
                                pat = validate_pattern(xP, aP, bP, cP, dP, xI, aI, bI, cI, dI, p_def, cfg_base, bull)
                                if pat is not None:
                                    all_candidates[p_def.name].append(pat)

    print("\n--- Q10 & Q12: Raw Candidate Formation vs Score Threshold Audit (13:00-20:00 UTC) ---", flush=True)
    candidate_summary = []
    for p_name, p_list in all_candidates.items():
        scores = [p.score for p in p_list]
        passed_85 = sum(1 for s in scores if s >= 0.85)
        passed_80 = sum(1 for s in scores if s >= 0.80)
        passed_70 = sum(1 for s in scores if s >= 0.70)
        mean_s = np.mean(scores) if scores else 0.0
        
        candidate_summary.append({
            "Pattern": p_name,
            "Total Formations Found": len(p_list),
            "Score >= 0.85 (Champion)": passed_85,
            "Score >= 0.80": passed_80,
            "Score >= 0.70": passed_70,
            "Mean Candidate Score": f"{mean_s:.3f}",
            "Score Range [Min, Max]": f"[{min(scores):.2f}, {max(scores):.2f}]" if scores else "N/A"
        })
    print(pd.DataFrame(candidate_summary).to_string(index=False), flush=True)

    print("\n--- Q11: Exact Code Ratio Definitions vs Classical Literature Check ---", flush=True)
    for p in ALL_PATTERNS:
        print(f"Pattern {p.name:<10}: AB/XA: {str(p.ab_xa):<14} | BC/AB: {str(p.bc_ab):<14} | CD/BC: {str(p.cd_bc):<14} | AD/XA (or CD/XC): {str(p.ad_xa):<14}", flush=True)

    # =========================================================================
    # PART 5: DSR FORMULA, GRANULARITY & N-SENSITIVITY (Q13 - Q15)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("PART 5: DSR FORMULA, GRANULARITY & N-SENSITIVITY (Q13 to Q15)", flush=True)
    print("=" * 115, flush=True)

    r_multiples = [t.r_multiple for t in trades_base]
    n_trades = len(r_multiples)
    mean_r = float(np.mean(r_multiples))
    std_r = float(np.std(r_multiples, ddof=1))
    sr_trade = mean_r / std_r
    skew = float(stats.skew(r_multiples))
    kurt = float(stats.kurtosis(r_multiples, fisher=False))
    
    print("\n--- Q13 & Q15: López de Prado (2014) DSR Formulation & Inputs ---", flush=True)
    print("Formula Implementation:", flush=True)
    print("  SR_0_trade = ( (1 - gamma_E) * Z(1 - 1/N) + gamma_E * Z(1 - 1/(N*e)) )", flush=True)
    print("  DSR_Z = [ (SR_trade - SR_0_trade) * sqrt(n - 1) ] / sqrt(1 - skew*SR_trade + ((kurt - 1)/4)*SR_trade^2)", flush=True)
    print("  DSR = Phi(DSR_Z)", flush=True)
    print(f"\nInputs Used:", flush=True)
    print(f"  Granularity:                   Per-Trade R-Multiples (n = {n_trades} trades)", flush=True)
    print(f"  Mean R:                        {mean_r:+.4f}R", flush=True)
    print(f"  Std R:                         {std_r:.4f}R", flush=True)
    print(f"  Per-Trade Sharpe (SR_trade):   {sr_trade:.4f}", flush=True)
    print(f"  Skewness (gamma_3):            {skew:.4f}", flush=True)
    print(f"  Kurtosis (gamma_4, Pearson):   {kurt:.4f}", flush=True)

    print("\n--- Q14: Sensitivity Table of DSR across N Trials (1 to 200) ---", flush=True)
    dsr_sensitivity = []
    euler_mascheroni = 0.5772156649
    denom = np.sqrt(1.0 - skew * sr_trade + ((kurt - 1.0) / 4.0) * (sr_trade ** 2))
    
    for N in [1, 2, 5, 10, 20, 50, 100, 200]:
        if N == 1:
            sr_0_t = 0.0
        else:
            sr_0_t = ((1.0 - euler_mascheroni) * stats.norm.ppf(1.0 - 1.0 / N) +
                      euler_mascheroni * stats.norm.ppf(1.0 - 1.0 / (N * math.e)))
        
        dsr_z_trade = ((sr_trade - sr_0_t) * np.sqrt(n_trades - 1)) / denom if denom > 0 else 0.0
        dsr_val_trade = float(stats.norm.cdf(dsr_z_trade))
        
        sr_ann = sr_trade * np.sqrt(59.2)
        sr_0_ann = sr_0_t
        dsr_z_ann = ((sr_ann - sr_0_ann) * np.sqrt(16.6 - 1)) / denom if denom > 0 else 0.0
        dsr_val_ann = float(stats.norm.cdf(dsr_z_ann))
        
        dsr_sensitivity.append({
            "Trials (N)": N,
            "Null Hurdle SR_0 (Trade)": f"{sr_0_t:.3f}",
            "DSR (Trade-Level)": f"{dsr_val_trade:.4f}",
            "p-value (Trade)": f"{1-dsr_val_trade:.4e}",
            "DSR Status (Trade)": "PASS (>0.95)" if dsr_val_trade > 0.95 else "FAIL",
            "DSR (Annualized Eq)": f"{dsr_val_ann:.4f}"
        })
    print(pd.DataFrame(dsr_sensitivity).to_string(index=False), flush=True)

    # =========================================================================
    # PART 6: EXPECTANCY & DRIFT (Q16 & Q17)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("PART 6: EXPECTANCY DECOMPOSITION & TEMPORAL STABILITY (Q16 & Q17)", flush=True)
    print("=" * 115, flush=True)

    cypher_trades = [t for t in trades_base if t.pattern_type == "Cypher"]
    non_cypher_trades = [t for t in trades_base if t.pattern_type != "Cypher"]
    
    def calc_exp_details(t_list, name="Group"):
        wins = [t for t in t_list if t.net_pnl > 0]
        losses = [t for t in t_list if t.net_pnl <= 0]
        w_pct = len(wins) / len(t_list) if t_list else 0
        l_pct = len(losses) / len(t_list) if t_list else 0
        avg_w = np.mean([t.r_multiple for t in wins]) if wins else 0
        avg_l = abs(np.mean([t.r_multiple for t in losses])) if losses else 0
        exp = (w_pct * avg_w) - (l_pct * avg_l)
        return {
            "Group": name, "Trades": len(t_list), "Win%": f"{w_pct*100:.1f}%",
            "Avg Win R": f"+{avg_w:.3f}R", "Avg Loss R": f"-{avg_l:.3f}R",
            "Mathematical Expectancy": f"+{exp:.4f}R"
        }
        
    exp_comparison = [
        calc_exp_details(trades_base, "Blended Mix (All 4 Patterns)"),
        calc_exp_details(cypher_trades, "Cypher Solo (94.3% of trades)"),
        calc_exp_details(non_cypher_trades, "Gartley + Shark + Crab Combined")
    ]
    print("\n--- Q16: Cypher Solo Expectancy vs Blended Portfolio Mix ---", flush=True)
    print(pd.DataFrame(exp_comparison).to_string(index=False), flush=True)

    print("\n--- Q17: Yearly Expectancy Trend (2010 to 2026) ---", flush=True)
    yearly_exp = []
    for y in sorted(list(set(t.exit_time.year if t.exit_time else t.entry_time.year for t in trades_base))):
        y_ts = [t for t in trades_base if (t.exit_time if t.exit_time else t.entry_time).year == y]
        st = calc_exp_details(y_ts, str(y))
        st["Net PnL"] = f"${sum(t.net_pnl for t in y_ts):+,.2f}"
        yearly_exp.append(st)
    df_y_exp = pd.DataFrame(yearly_exp)
    print(df_y_exp[["Group", "Trades", "Win%", "Avg Win R", "Avg Loss R", "Mathematical Expectancy", "Net PnL"]].to_string(index=False), flush=True)

    print("\n" + "=" * 115, flush=True)
    print("FORENSIC VALIDATION RUN COMPLETE.", flush=True)
    print("=" * 115, flush=True)

if __name__ == "__main__":
    main()
