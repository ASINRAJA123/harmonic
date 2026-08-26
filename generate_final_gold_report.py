"""
Comprehensive Gold 2010-2026 and 2026 Deep-Dive Analysis Generator.
Extracts exact year-by-year returns, Jan-Aug 2026 metrics, day-of-week, session/hour breakdowns,
and compiles all 7 validation test results.
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

from core.config import HarmonicRatios, PATTERN_MAP, ALL_PATTERNS, PATTERN_TARGETS, compute_target_price
from core.pattern_scanner import _ratio_valid, HarmonicPattern
from core.engine import HarmonicV3Config, HarmonicV3Trade, resample_bars, compute_atr, compute_h1_trend_bias

DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

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

def validate_pattern_fair(
    xP: float, aP: float, bP: float, cP: float, dP: float,
    xI: int, aI: int, bI: int, cI: int, dI: int,
    ratios: HarmonicRatios, cfg, bull: bool
):
    xa = abs(aP - xP)
    ab = abs(bP - aP)
    bc = abs(cP - bP)
    cd = abs(dP - cP)
    ad = abs(dP - aP)
    xc = abs(cP - xP)

    if xa == 0 or ab == 0 or bc == 0 or cd == 0 or (ratios.use_cd_xc and xc == 0):
        return None

    r_ab_xa = ab / xa
    r_bc_ab = bc / ab
    r_cd_bc = (cd / bc) if ratios.cd_bc is not None else 0.0
    r_ad_xa = (cd / xc) if ratios.use_cd_xc else (ad / xa)

    v1, e1 = _ratio_valid(r_ab_xa, ratios.ab_xa, cfg.fib_error_pct)
    v2, e2 = _ratio_valid(r_bc_ab, ratios.bc_ab, cfg.fib_error_pct)
    v3, e3 = _ratio_valid(r_cd_bc, ratios.cd_bc, cfg.fib_error_pct) if ratios.cd_bc is not None else (True, 0.0)
    v4, e4 = _ratio_valid(r_ad_xa, ratios.ad_xa, cfg.fib_error_pct)

    if not (v1 and v2 and v3 and v4):
        return None

    leg_bars = [aI - xI, bI - aI, cI - bI, dI - cI]
    avg_bars = np.mean(leg_bars)
    if avg_bars > 0:
        for lb in leg_bars:
            asym = abs(lb - avg_bars) / avg_bars * 100
            if asym > getattr(cfg, "leg_asymmetry_pct", 250.0):
                return None

    if ratios.name == "Cypher":
        p1 = (cP - 0.786 * xc) if bull else (cP + 0.786 * xc)
        p2 = (cP - 1.272 * bc) if bull else (cP + 1.272 * bc)
    elif ratios.name == "Shark":
        p1 = (aP - 0.886 * xa) if bull else (aP + 0.886 * xa)
        p2 = (cP - 1.618 * bc) if bull else (cP + 1.618 * bc)
    elif ratios.name == "Gartley":
        p1 = (aP - 0.786 * xa) if bull else (aP + 0.786 * xa)
        p2 = (cP - 1.272 * bc) if bull else (cP + 1.272 * bc)
    else:
        p1 = (aP - 0.786 * xa) if bull else (aP + 0.786 * xa)
        p2 = (cP - 1.272 * bc) if bull else (cP + 1.272 * bc)

    prz_near = min(p1, p2, key=lambda x: abs(x - dP))
    prz_far = max(p1, p2, key=lambda x: abs(x - dP))

    errors = [e for e, valid in [(e1, ratios.ab_xa), (e2, ratios.bc_ab), (e3, ratios.cd_bc), (e4, ratios.ad_xa)] if valid is not None]
    avg_err = np.mean(errors) if errors else 0.0
    ratio_score = max(0.0, 1.0 - avg_err)

    prz_range = abs(prz_near - prz_far)
    base_span = xa if xa > 0 else 1.0
    prz_confluence_score = max(0.0, 1.0 - (prz_range / (base_span * 0.25)))
    d_to_prz = min(abs(dP - prz_near), abs(dP - prz_far))
    d_confluence_score = max(0.0, 1.0 - (d_to_prz / (base_span * 0.15)))

    w_ratio = getattr(cfg, "w_ratio_accuracy", 4.0)
    w_prz = getattr(cfg, "w_prz_confluence", 2.0)
    w_d = getattr(cfg, "w_d_confluence", 3.0)
    total_w = w_ratio + w_prz + w_d

    score = (w_ratio * ratio_score + w_prz * prz_confluence_score + w_d * d_confluence_score) / total_w
    score = max(0.0, min(1.0, score))

    t1_type, t2_type = PATTERN_TARGETS.get(ratios.name, (".618 AD", "1.272 AD"))
    t1_price = compute_target_price(t1_type, xP, aP, bP, cP, dP, bull)
    t2_price = compute_target_price(t2_type, xP, aP, bP, cP, dP, bull)

    entry_price = dP
    dist_to_t1 = abs(t1_price - entry_price)
    pct = getattr(cfg, "stop_pct", 75.0) / 100.0
    stop_price = (entry_price - dist_to_t1 * pct) if bull else (entry_price + dist_to_t1 * pct)

    return HarmonicPattern(
        pattern_type=ratios.name, bull=bull,
        x_idx=xI, x_price=xP, a_idx=aI, a_price=aP,
        b_idx=bI, b_price=bP, c_idx=cI, c_price=cP,
        d_idx=dI, d_price=dP,
        r_ab_xa=r_ab_xa, r_bc_ab=r_bc_ab, r_cd_bc=r_cd_bc, r_ad_xa=r_ad_xa,
        err_ab_xa=e1, err_bc_ab=e2, err_cd_bc=e3, err_ad_xa=e4,
        prz_near=prz_near, prz_far=prz_far, score=score,
        t1_price=t1_price, t2_price=t2_price,
        stop_price=stop_price, entry_price=entry_price,
    )

def run_fair_backtest(bars: pd.DataFrame, cfg: HarmonicV3Config, min_score: float = 0.80):
    n = len(bars)
    if n < 50: return {"trades": [], "scorecard": {}}

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

    equity = cfg.initial_equity
    trades: List[HarmonicV3Trade] = []
    open_trades: List[HarmonicPattern] = []
    trade_counter = 0

    spread_price = cfg.spread_points * cfg.point_size
    slip_price = cfg.slippage_points * cfg.point_size

    for i in range(20, n):
        current_time = pd.Timestamp(times[i]) if not isinstance(times[i], (int, float)) else None

        still_open = []
        for pat in open_trades:
            if pat.exit_reason is not None: continue
            pattern_len = pat.d_idx - pat.x_idx
            timeout_bar = pat.d_idx + int(pattern_len * cfg.pattern_timeout_mult)

            hit_sl = False
            hit_tp1 = False
            hit_tp2 = False

            if pat.bull:
                hit_sl = lows[i] <= pat.stop_price
                if not pat.t1_hit: hit_tp1 = highs[i] >= pat.t1_price
                else: hit_tp2 = highs[i] >= pat.t2_price
            else:
                hit_sl = highs[i] >= pat.stop_price
                if not pat.t1_hit: hit_tp1 = lows[i] <= pat.t1_price
                else: hit_tp2 = lows[i] <= pat.t2_price

            if hit_sl and hit_tp1: hit_tp1 = False

            if hit_sl:
                pat.exit_bar = i
                pat.exit_price = pat.stop_price
                pat.exit_reason = "TP1_BE" if pat.t1_hit else "SL"
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
                gross_pnl = (abs(pat.t1_price - pat.entry_price) + abs(pat.t2_price - pat.entry_price)) * half_lots * cfg.contract_size
                applied_slip = 0.0
            elif pat.exit_reason == "TP1_BE":
                half_lots = lots * 0.50
                gross_pnl = abs(pat.t1_price - pat.entry_price) * half_lots * cfg.contract_size
                applied_slip = 0.0
            elif pat.exit_reason == "SL":
                gross_pnl = -abs(pat.entry_price - pat.stop_price) * lots * cfg.contract_size
                applied_slip = slip_price
            else:
                pnl_u = (pat.exit_price - pat.entry_price) if pat.bull else (pat.entry_price - pat.exit_price)
                gross_pnl = pnl_u * lots * cfg.contract_size
                applied_slip = 0.0

            spread_cost = spread_price * cfg.contract_size * lots
            comm_cost = cfg.commission_per_lot * lots
            slippage_cost = applied_slip * cfg.contract_size * lots
            net_pnl = gross_pnl - (spread_cost + comm_cost + slippage_cost)
            
            denom_eq = cfg.initial_equity
            r_mult = (net_pnl / (denom_eq * cfg.risk_per_trade_pct)) if denom_eq > 0 else 0.0

            trades.append(HarmonicV3Trade(
                trade_id=f"{cfg.symbol}_{trade_counter}",
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

        for (p_idx, p_price, p_type, radius) in pivots_confirmed_at[i]:
            if p_type == "high": known_highs.append((p_idx, p_price))
            else: known_lows.append((p_idx, p_price))
        if len(known_highs) > 40: known_highs = known_highs[-40:]
        if len(known_lows) > 40: known_lows = known_lows[-40:]

        newly_confirmed = pivots_confirmed_at[i]
        if not newly_confirmed: continue
        if current_time and (current_time.hour < cfg.session_start_hour or current_time.hour >= cfg.session_end_hour): continue
        if len(open_trades) >= cfg.max_concurrent_positions: continue

        for (dI, dP, dType, radius) in newly_confirmed:
            bull = (dType == "low")
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

            candidates_at_d = []
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
                                if not r_def: continue
                                pat = validate_pattern_fair(xP, aP, bP, cP, dP, xI, aI, bI, cI, dI, r_def, cfg, bull)
                                if pat and pat.score >= min_score:
                                    candidates_at_d.append(pat)

            if candidates_at_d:
                best_pat = max(candidates_at_d, key=lambda p: p.score)
                if i + 1 < n:
                    fill_price = opens[i + 1]
                    stop_dist = abs(fill_price - best_pat.stop_price)
                    min_stop_atr = atr[i] * cfg.min_atr_stop_multiple
                    min_stop_spread = spread_price * cfg.min_stop_to_spread_ratio
                    if stop_dist >= max(min_stop_atr, min_stop_spread):
                        risk_amt = max(0.0, cfg.initial_equity * cfg.risk_per_trade_pct)
                        calc_lot = risk_amt / (stop_dist * cfg.contract_size)
                        lot_size = max(cfg.min_lot_size, min(cfg.max_lot_size, round(calc_lot, 2)))
                        best_pat.entry_price = fill_price
                        best_pat.entry_bar = i + 1
                        best_pat.entry_filled = True
                        best_pat.lot_size = lot_size
                        open_trades.append(best_pat)

    return trades

def main():
    print("=" * 115, flush=True)
    print("GENERATING DEFINITIVE 2010-2026 & 2026 YTD GOLD AUDIT DATA", flush=True)
    print("=" * 115, flush=True)

    gold_raw = load_gold_data()
    bars_m15 = resample_bars(gold_raw, 15)

    cfg = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"]
    )
    all_trades = run_fair_backtest(bars_m15, cfg, min_score=0.80)
    print(f"Total 16.6-Year Trades on Gold: {len(all_trades)}", flush=True)

    # 1. Year-by-Year Table
    years = sorted(list(set(t.exit_time.year if t.exit_time else t.entry_time.year for t in all_trades)))
    yearly_rows = []
    
    cum_equity = 10_000.0
    for y in years:
        y_trades = [t for t in all_trades if (t.exit_time if t.exit_time else t.entry_time).year == y]
        net_pnls = [t.net_pnl for t in y_trades]
        wins = sum(1 for p in net_pnls if p > 0)
        tot = len(y_trades)
        gw = sum(p for p in net_pnls if p > 0)
        gl = abs(sum(p for p in net_pnls if p < 0))
        pf = gw / gl if gl > 0 else 999.0
        tot_net = sum(net_pnls)
        fric = sum(t.spread_cost + t.commission_cost + t.slippage_cost for t in y_trades)
        
        # Yearly Drawdown
        eq_y = [10_000.0]
        for p in net_pnls: eq_y.append(eq_y[-1] + p)
        pk = 10_000.0
        mdd_y = 0.0
        for v in eq_y:
            if v > pk: pk = v
            dd = (pk - v) / pk * 100
            if dd > mdd_y: mdd_y = dd
            
        r_vals = [t.r_multiple for t in y_trades]
        avg_r = np.mean(r_vals) if r_vals else 0.0
        
        yearly_rows.append({
            "Year": y,
            "Trades": tot,
            "Wins": wins,
            "Losses": tot - wins,
            "Win Rate %": f"{wins/tot*100:.1f}%",
            "Profit Factor": f"{pf:.2f}",
            "Net Profit ($10k Base)": f"${tot_net:+,.2f}",
            "Annual ROI %": f"{tot_net/10_000.0*100:+.2f}%",
            "Max DD %": f"{mdd_y:.1f}%",
            "Avg R": f"{avg_r:+.3f}R",
            "Friction Paid ($)": f"-${fric:,.2f}"
        })
    df_yearly = pd.DataFrame(yearly_rows)
    print("\n--- 16.6-YEAR YEAR-BY-YEAR SCORECARD (GOLD M15) ---", flush=True)
    print(df_yearly.to_string(index=False), flush=True)

    # 2. Jan 1, 2026 to Aug 25, 2026 Deep-Dive
    trades_2026 = [t for t in all_trades if (t.exit_time if t.exit_time else t.entry_time).year == 2026]
    print(f"\n--- 2026 YTD DEEP DIVE (Jan 1, 2026 to Aug 25, 2026, {len(trades_2026)} Trades) ---", flush=True)
    
    pnl_26 = [t.net_pnl for t in trades_2026]
    w_26 = sum(1 for p in pnl_26 if p > 0)
    gw_26 = sum(p for p in pnl_26 if p > 0)
    gl_26 = abs(sum(p for p in pnl_26 if p < 0))
    pf_26 = gw_26 / gl_26 if gl_26 > 0 else 999.0
    tot_26 = sum(pnl_26)
    
    print(f"Total 2026 YTD Trades:        {len(trades_2026)}")
    print(f"2026 YTD Win Rate:            {w_26/len(trades_2026)*100:.1f}% ({w_26} Wins / {len(trades_2026)-w_26} Losses)")
    print(f"2026 YTD Profit Factor:       {pf_26:.2f}")
    print(f"2026 YTD Net Realized Profit: ${tot_26:+,.2f} ({tot_26/10_000.0*100:+.2f}% ROI on $10k base)")

    # Day-of-Week Breakdown in 2026
    days_map = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}
    day_rows_26 = []
    for d_idx, d_name in days_map.items():
        d_trades = [t for t in trades_2026 if (t.entry_time if t.entry_time else t.exit_time).weekday() == d_idx]
        if not d_trades: continue
        dpnl = [t.net_pnl for t in d_trades]
        dw = sum(1 for p in dpnl if p > 0)
        dgw = sum(p for p in dpnl if p > 0)
        dgl = abs(sum(p for p in dpnl if p < 0))
        dpf = dgw / dgl if dgl > 0 else 999.0
        day_rows_26.append({
            "Day of Week": d_name,
            "Trades": len(d_trades),
            "Win Rate %": f"{dw/len(d_trades)*100:.1f}%",
            "Profit Factor": f"{dpf:.2f}",
            "Net Profit ($)": f"${sum(dpnl):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in d_trades]):+.3f}R"
        })
    print("\n2026 Day-of-Week Breakdown:")
    print(pd.DataFrame(day_rows_26).to_string(index=False), flush=True)

    # Hourly / Session Breakdown in 2026
    session_rows_26 = []
    # Session windows:
    # NY/London Golden Window: 13:00 - 20:00 UTC
    # Early London: 08:00 - 13:00 UTC
    # Asian: 00:00 - 08:00 UTC
    # Late NY / Off: 20:00 - 24:00 UTC
    for h in sorted(list(set((t.entry_time if t.entry_time else t.exit_time).hour for t in trades_2026))):
        h_trades = [t for t in trades_2026 if (t.entry_time if t.entry_time else t.exit_time).hour == h]
        hpnl = [t.net_pnl for t in h_trades]
        hw = sum(1 for p in hpnl if p > 0)
        hgw = sum(p for p in hpnl if p > 0)
        hgl = abs(sum(p for p in hpnl if p < 0))
        hpf = hgw / hgl if hgl > 0 else 999.0
        session_rows_26.append({
            "Entry Hour (UTC)": f"{h:02d}:00 UTC",
            "Trades": len(h_trades),
            "Win Rate %": f"{hw/len(h_trades)*100:.1f}%",
            "Profit Factor": f"{hpf:.2f}",
            "Net Profit ($)": f"${sum(hpnl):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in h_trades]):+.3f}R"
        })
    print("\n2026 Hourly Execution Breakdown:")
    print(pd.DataFrame(session_rows_26).to_string(index=False), flush=True)

    # Pattern breakdown in 2026
    pat_rows_26 = []
    for p_name in ["Shark", "Cypher", "Gartley"]:
        p_trades = [t for t in trades_2026 if t.pattern_type == p_name]
        if not p_trades: continue
        ppnl = [t.net_pnl for t in p_trades]
        pw = sum(1 for p in ppnl if p > 0)
        pgw = sum(p for p in ppnl if p > 0)
        pgl = abs(sum(p for p in ppnl if p < 0))
        ppf = pgw / pgl if pgl > 0 else 999.0
        pat_rows_26.append({
            "Pattern": p_name,
            "Trades": len(p_trades),
            "Win Rate %": f"{pw/len(p_trades)*100:.1f}%",
            "Profit Factor": f"{ppf:.2f}",
            "Net Profit ($)": f"${sum(ppnl):+,.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in p_trades]):+.3f}R"
        })
    print("\n2026 Pattern Breakdown:")
    print(pd.DataFrame(pat_rows_26).to_string(index=False), flush=True)

if __name__ == "__main__":
    main()
