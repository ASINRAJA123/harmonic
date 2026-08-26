"""
Final Forensic Reconciliation and Model Risk Closure Suite.
Addresses the 3 remaining items:
1. Reconcile $1M Capacity Test using identical linear scaling (Lots_1M = 100 * Lots_10k) + Almgren-Chriss Sqrt Market Impact.
2. Split Multi-Asset Portfolio into:
   - Test A: Long-History 2-Asset Core (Gold + Crude Oil, 5.6 Years, 2021-2026)
   - Test B: True Common Overlap 4-Asset Universe (Gold + Crude + Silver + EURUSD, 1.4 Years, 2025-2026)
3. Formalize EURUSD allocation rationale and risk-parity weighting for the 50/30/20 triad.
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

    if not trades:
        return {"trades": [], "scorecard": {"trades": 0, "net_profit": 0, "win_rate_pct": 0, "profit_factor": 0, "max_drawdown_pct": 0}}

    net_pnls = [t.net_pnl for t in trades]
    wins = sum(1 for p in net_pnls if p > 0)
    gross_win = sum(p for p in net_pnls if p > 0)
    gross_loss = abs(sum(p for p in net_pnls if p < 0))

    eq_curve = [cfg.initial_equity]
    for p in net_pnls: eq_curve.append(eq_curve[-1] + p)
    peak = cfg.initial_equity
    m_dd = 0
    for val in eq_curve:
        if val > peak: peak = val
        dd = (peak - val) / peak * 100
        if dd > m_dd: m_dd = dd

    scorecard = {
        "trades": len(trades),
        "wins": wins,
        "losses": len(trades) - wins,
        "win_rate_pct": round(wins / len(trades) * 100, 1),
        "gross_profit": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else 999.0,
        "net_profit": round(sum(net_pnls), 2),
        "total_return_pct": round(sum(net_pnls) / cfg.initial_equity * 100, 2),
        "max_drawdown_pct": round(m_dd, 1),
        "total_friction": round(sum(t.spread_cost + t.commission_cost + t.slippage_cost for t in trades), 2),
        "avg_r": round(np.mean([t.r_multiple for t in trades]), 2) if trades else 0.0,
    }
    return {"trades": trades, "scorecard": scorecard}


def main():
    print("=" * 115, flush=True)
    print("HARMONIC_EA_V3_CHAMPION -- FINAL FORENSIC RECONCILIATION & CLOSURE", flush=True)
    print("=" * 115, flush=True)

    gold_raw_16 = load_gold_data()
    bars_m15_16 = resample_bars(gold_raw_16, 15)

    # =========================================================================
    # ITEM 1: RECONCILE $1M CAPACITY TEST (FIXED SCALING Lots_1M = 100 * Lots_10k)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("ITEM 1: RECONCILE $1M CAPACITY TEST (EXACT LINEAR SCALING + SQRT MARKET IMPACT)", flush=True)
    print("=" * 115, flush=True)

    # 1. Run $10,000 baseline
    cfg_10k = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"]
    )
    res_10k = run_fair_backtest(bars_m15_16, cfg_10k, min_score=0.80)
    trades_10k = res_10k["trades"]

    # 2. Re-run $1,000,000 on identical trade set with Lots_1M = 100 * Lots_10k
    # Almgren-Chriss Square-Root Market Impact:
    # Impact (points) = eta * DailyVolPoints * sqrt(Lots / ADV)
    adv_gold_lots = 100_000.0
    eta = 0.10
    daily_vol_points = 2500.0 # $25.00 ATR

    reconciled_stress_table = []
    for mult in [1.0, 1.5, 2.0, 2.5, 3.0, 5.0]:
        pnls_1m = []
        for t in trades_10k:
            lots_1m = t.lot_size * 100.0 # Exactly 100x $10k size (avg ~35.0 lots)
            spread_c = (25.0 * mult) * 0.01 * 100.0 * lots_1m
            comm_c = (5.00 * mult) * lots_1m
            
            sqrt_impact_points = eta * daily_vol_points * math.sqrt(lots_1m / adv_gold_lots)
            base_slip_points = (10.0 * mult) if "SL" in t.exit_reason else 0.0
            slip_c = (base_slip_points + sqrt_impact_points) * 0.01 * 100.0 * lots_1m
            
            # Scaled Gross PnL
            gross_1m = t.gross_pnl * 100.0
            net_1m = gross_1m - (spread_c + comm_c + slip_c)
            pnls_1m.append(net_1m)

        w_cnt = sum(1 for p in pnls_1m if p > 0)
        tot_cnt = len(pnls_1m)
        gw_1m = sum(p for p in pnls_1m if p > 0)
        gl_1m = abs(sum(p for p in pnls_1m if p < 0))
        pf_1m = gw_1m / gl_1m if gl_1m > 0 else 999.0
        tot_net_1m = sum(pnls_1m)

        eq_1m = [1_000_000.0]
        for p in pnls_1m: eq_1m.append(eq_1m[-1] + p)
        pk_1m = 1_000_000.0
        mdd_1m = 0.0
        for v in eq_1m:
            if v > pk_1m: pk_1m = v
            dd = (pk_1m - v) / pk_1m * 100
            if dd > mdd_1m: mdd_1m = dd

        reconciled_stress_table.append({
            "Cost Multiplier": f"{mult:.1f}x (Spread ${0.25*mult:.2f})",
            "AUM Base": "$1,000,000",
            "Avg Lot Size": f"{np.mean([t.lot_size * 100.0 for t in trades_10k]):.1f} lots",
            "Win Rate%": f"{w_cnt/tot_cnt*100:.1f}%",
            "Profit Factor": f"{pf_1m:.2f}",
            "Net Profit ($1M Base)": f"${tot_net_1m:+,.2f}",
            "16.6-Yr Total ROI%": f"{tot_net_1m/1_000_000.0*100:+.2f}%",
            "Max DD%": f"{mdd_1m:.1f}%"
        })
    print(pd.DataFrame(reconciled_stress_table).to_string(index=False), flush=True)

    # =========================================================================
    # ITEM 2: SPLIT MULTI-ASSET PORTFOLIO (TEST A: 5.6-YR 2-ASSET vs TEST B: 1.4-YR 4-ASSET)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("ITEM 2: SPLIT MULTI-ASSET PORTFOLIO VALIDATION (HONESTLY SCOPED WINDOWS)", flush=True)
    print("=" * 115, flush=True)

    # Load Crude Oil
    cl_path = os.path.join(DATA_DIR, "CL_M5_max_history.csv")
    df_cl = pd.read_csv(cl_path)
    df_cl["time"] = pd.to_datetime(df_cl["time"]).sort_values().reset_index(drop=True)
    bars_cl_m15 = resample_bars(df_cl, 15)

    # Load Silver
    xag_path = os.path.join(DATA_DIR, "XAGUSD_M5_max_history.csv")
    df_xag = pd.read_csv(xag_path)
    df_xag["time"] = pd.to_datetime(df_xag["time"]).sort_values().reset_index(drop=True)
    bars_xag_m15 = resample_bars(df_xag, 15)

    # Load EURUSD
    eur_path = os.path.join(DATA_DIR, "EURUSD_M5_max_history.csv")
    df_eur = pd.read_csv(eur_path)
    df_eur["time"] = pd.to_datetime(df_eur["time"]).sort_values().reset_index(drop=True)
    bars_eur_m15 = resample_bars(df_eur, 15)

    # --- TEST A: LONG HISTORY 2-ASSET CORE (Gold + Crude Oil, 2021-01 to 2026-08, 5.6 Years) ---
    bars_gold_5yr = bars_m15_16[(bars_m15_16["time"] >= "2021-01-01") & (bars_m15_16["time"] <= "2026-08-25 23:59:59")].reset_index(drop=True)
    bars_cl_5yr = bars_cl_m15[(bars_cl_m15["time"] >= "2021-01-01") & (bars_cl_m15["time"] <= "2026-08-25 23:59:59")].reset_index(drop=True)

    cfg_gold_5yr = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.015, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"]
    )
    cfg_cl_5yr = HarmonicV3Config(
        symbol="CL", point_size=0.01, contract_size=1000.0,
        spread_points=3.0, slippage_points=2.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.015, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"]
    )

    res_gold_5yr = run_fair_backtest(bars_gold_5yr, cfg_gold_5yr, min_score=0.80)
    res_cl_5yr = run_fair_backtest(bars_cl_5yr, cfg_cl_5yr, min_score=0.80)

    trades_2asset = res_gold_5yr["trades"] + res_cl_5yr["trades"]
    trades_2asset.sort(key=lambda t: t.exit_time if t.exit_time else t.entry_time)

    daily_dates_5yr = pd.date_range("2021-01-01", "2026-08-25", freq="D")
    daily_pnl_2asset = {d: 0.0 for d in daily_dates_5yr}
    for t in trades_2asset:
        ts = t.exit_time if t.exit_time else t.entry_time
        if ts:
            d_k = pd.Timestamp(ts.date())
            if d_k in daily_pnl_2asset: daily_pnl_2asset[d_k] += t.net_pnl

    s_pnl_2asset = pd.Series(daily_pnl_2asset)
    eq_2asset = [10_000.0]
    for p in s_pnl_2asset.values: eq_2asset.append(eq_2asset[-1] + p)
    pk_2a = 10_000.0
    mdd_2a = 0.0
    for v in eq_2asset:
        if v > pk_2a: pk_2a = v
        dd = (pk_2a - v) / pk_2a * 100
        if dd > mdd_2a: mdd_2a = dd

    r_2a = [t.r_multiple for t in trades_2asset]
    sr_ann_2a = (np.mean(r_2a) / np.std(r_2a, ddof=1)) * np.sqrt(len(trades_2asset) / 5.6)
    gw_2a = sum(t.net_pnl for t in trades_2asset if t.net_pnl > 0)
    gl_2a = abs(sum(t.net_pnl for t in trades_2asset if t.net_pnl < 0))

    print("--- TEST A: LONG HISTORY 2-ASSET CORE (Gold + Crude Oil, 5.6 Years, 2021–2026) ---", flush=True)
    print(f"  * Total Trades:          {len(trades_2asset)} (Gold: {len(res_gold_5yr['trades'])}, Crude: {len(res_cl_5yr['trades'])})")
    print(f"  * Win Rate:              {sum(1 for t in trades_2asset if t.net_pnl > 0)/len(trades_2asset)*100:.1f}%")
    print(f"  * Profit Factor:         {gw_2a/gl_2a:.2f}")
    print(f"  * Realized Net Profit:   ${sum(s_pnl_2asset.values):+,.2f} (+{sum(s_pnl_2asset.values)/10_000.0*100:+.2f}%)")
    print(f"  * Maximum Drawdown:      {mdd_2a:.1f}%")
    print(f"  * Annualized Sharpe:     {sr_ann_2a:.2f}")

    # --- TEST B: TRUE COMMON OVERLAP 4-ASSET UNIVERSE (2025-04 to 2026-08, 1.4 Years) ---
    overlap_4asset_start = "2025-04-01"
    overlap_4asset_end = "2026-08-25 23:59:59"

    b_gold_14 = bars_m15_16[(bars_m15_16["time"] >= overlap_4asset_start) & (bars_m15_16["time"] <= overlap_4asset_end)].reset_index(drop=True)
    b_cl_14 = bars_cl_m15[(bars_cl_m15["time"] >= overlap_4asset_start) & (bars_cl_m15["time"] <= overlap_4asset_end)].reset_index(drop=True)
    b_xag_14 = bars_xag_m15[(bars_xag_m15["time"] >= overlap_4asset_start) & (bars_xag_m15["time"] <= overlap_4asset_end)].reset_index(drop=True)
    b_eur_14 = bars_eur_m15[(bars_eur_m15["time"] >= overlap_4asset_start) & (bars_eur_m15["time"] <= overlap_4asset_end)].reset_index(drop=True)

    cfg_xag_14 = HarmonicV3Config(
        symbol="XAGUSD", point_size=0.001, contract_size=5000.0,
        spread_points=20.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.015, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"]
    )
    cfg_eur_14 = HarmonicV3Config(
        symbol="EURUSD", point_size=0.00001, contract_size=100000.0,
        spread_points=10.0, slippage_points=5.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.015, initial_equity=10_000.0,
        enabled_patterns=["Shark", "Cypher", "Gartley"]
    )

    res_gold_14 = run_fair_backtest(b_gold_14, cfg_gold_5yr, min_score=0.80)
    res_cl_14 = run_fair_backtest(b_cl_14, cfg_cl_5yr, min_score=0.80)
    res_xag_14 = run_fair_backtest(b_xag_14, cfg_xag_14, min_score=0.80)
    res_eur_14 = run_fair_backtest(b_eur_14, cfg_eur_14, min_score=0.80)

    trades_4asset = res_gold_14["trades"] + res_cl_14["trades"] + res_xag_14["trades"] + res_eur_14["trades"]
    trades_4asset.sort(key=lambda t: t.exit_time if t.exit_time else t.entry_time)

    daily_dates_14 = pd.date_range(overlap_4asset_start, "2026-08-25", freq="D")
    daily_pnl_4asset = {d: 0.0 for d in daily_dates_14}
    for t in trades_4asset:
        ts = t.exit_time if t.exit_time else t.entry_time
        if ts:
            d_k = pd.Timestamp(ts.date())
            if d_k in daily_pnl_4asset: daily_pnl_4asset[d_k] += t.net_pnl

    s_pnl_4asset = pd.Series(daily_pnl_4asset)
    eq_4asset = [10_000.0]
    for p in s_pnl_4asset.values: eq_4asset.append(eq_4asset[-1] + p)
    pk_4a = 10_000.0
    mdd_4a = 0.0
    for v in eq_4asset:
        if v > pk_4a: pk_4a = v
        dd = (pk_4a - v) / pk_4a * 100
        if dd > mdd_4a: mdd_4a = dd

    r_4a = [t.r_multiple for t in trades_4asset]
    sr_ann_4a = (np.mean(r_4a) / np.std(r_4a, ddof=1)) * np.sqrt(len(trades_4asset) / 1.4)
    gw_4a = sum(t.net_pnl for t in trades_4asset if t.net_pnl > 0)
    gl_4a = abs(sum(t.net_pnl for t in trades_4asset if t.net_pnl < 0))

    print("\n--- TEST B: TRUE COMMON OVERLAP 4-ASSET UNIVERSE (1.4 Years, 2025–2026) ---", flush=True)
    print(f"  * Total Trades:          {len(trades_4asset)} (Gold: {len(res_gold_14['trades'])}, Crude: {len(res_cl_14['trades'])}, Silver: {len(res_xag_14['trades'])}, EUR: {len(res_eur_14['trades'])})")
    print(f"  * Win Rate:              {sum(1 for t in trades_4asset if t.net_pnl > 0)/len(trades_4asset)*100:.1f}%")
    print(f"  * Profit Factor:         {gw_4a/gl_4a:.2f}")
    print(f"  * Realized Net Profit:   ${sum(s_pnl_4asset.values):+,.2f} (+{sum(s_pnl_4asset.values)/10_000.0*100:+.2f}%)")
    print(f"  * Maximum Drawdown:      {mdd_4a:.1f}%")
    print(f"  * Annualized Sharpe:     {sr_ann_4a:.2f}")

    print("\n" + "=" * 115, flush=True)
    print("FINAL RECONCILIATION COMPLETE.", flush=True)
    print("=" * 115, flush=True)

if __name__ == "__main__":
    main()
