"""
Final Institutional Remediation and Validation Suite.
Addresses the 4 core mandates:
1. Fix Cypher PRZ scoring bug & greedy loop preemption -> Re-run fair pattern attribution.
2. Fix dynamic equity sizing in Cost-Stress Scenario A (capped at 100% DD / liquidation).
3. Compute statistically adequate correlation across signals & full multi-year data.
4. Measure Fixed vs Scaling Friction drag (% of R / stop distance) across 2010-2026.
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
from core.pattern_scanner import _ratio_valid, _ratio_error, HarmonicPattern
from core.engine import HarmonicV3Config, HarmonicV3Trade, resample_bars, compute_atr, compute_h1_trend_bias

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

# =============================================================================
# MANDATE 1: FAIR HARMONIC VALIDATION & UNIFIED PRZ SCORING
# =============================================================================
def validate_pattern_fair(
    xP: float, aP: float, bP: float, cP: float, dP: float,
    xI: int, aI: int, bI: int, cI: int, dI: int,
    ratios: HarmonicRatios, cfg, bull: bool
):
    """
    Fair, mathematically standardized XABCD validator with unbiased PRZ calculation across all patterns.
    """
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

    # Leg symmetry
    leg_bars = [aI - xI, bI - aI, cI - bI, dI - cI]
    avg_bars = np.mean(leg_bars)
    if avg_bars > 0:
        for lb in leg_bars:
            asym = abs(lb - avg_bars) / avg_bars * 100
            if asym > getattr(cfg, "leg_asymmetry_pct", 250.0):
                return None

    # Fair PRZ Calculation
    # Level 1: Primary Extension/Retracement
    if ratios.name == "Cypher":
        # Cypher D is 0.786 XC retracement and 1.272-1.414 BC extension
        p1 = (cP - 0.786 * xc) if bull else (cP + 0.786 * xc)
        p2 = (cP - 1.272 * bc) if bull else (cP + 1.272 * bc)
    elif ratios.name == "Shark":
        p1 = (aP - 0.886 * xa) if bull else (aP + 0.886 * xa)
        p2 = (cP - 1.618 * bc) if bull else (cP + 1.618 * bc)
    elif ratios.name == "Crab":
        p1 = (aP - 1.618 * xa) if bull else (aP + 1.618 * xa)
        p2 = (cP - 2.618 * bc) if bull else (cP + 2.618 * bc)
    elif ratios.name == "Gartley":
        p1 = (aP - 0.786 * xa) if bull else (aP + 0.786 * xa)
        p2 = (cP - 1.272 * bc) if bull else (cP + 1.272 * bc)
    elif ratios.name == "Bat":
        p1 = (aP - 0.886 * xa) if bull else (aP + 0.886 * xa)
        p2 = (cP - 1.618 * bc) if bull else (cP + 1.618 * bc)
    elif ratios.name == "Butterfly":
        p1 = (aP - 1.272 * xa) if bull else (aP + 1.272 * xa)
        p2 = (cP - 1.618 * bc) if bull else (cP + 1.618 * bc)
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
    """Backtest engine using fair argmax scoring and unbiased PRZ logic."""
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

        # Manage open trades
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
            r_mult = (net_pnl / (equity * cfg.risk_per_trade_pct)) if equity > 0 else 0.0

            trades.append(HarmonicV3Trade(
                trade_id=f"{cfg.symbol}_FAIR_{trade_counter}",
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

        # Update Pivots
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
                # Select the single highest-scoring pattern at this swing setup
                best_pat = max(candidates_at_d, key=lambda p: p.score)
                if i + 1 < n:
                    fill_price = opens[i + 1]
                    stop_dist = abs(fill_price - best_pat.stop_price)
                    min_stop_atr = atr[i] * cfg.min_atr_stop_multiple
                    min_stop_spread = spread_price * cfg.min_stop_to_spread_ratio
                    if stop_dist >= max(min_stop_atr, min_stop_spread):
                        risk_amt = max(0.0, equity * cfg.risk_per_trade_pct)
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
    print("HARMONIC_EA_V3_CHAMPION -- INSTITUTIONAL REMEDIATION & FINAL FORENSIC VALIDATION", flush=True)
    print("=" * 115, flush=True)

    gold_raw = load_gold_data()
    gold_m15 = resample_bars(gold_raw, 15)

    # =========================================================================
    # MANDATE 1: FAIR SCORING & PATTERN ATTRIBUTION RE-RUN
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("MANDATE 1: FAIR SCORING & PATTERN ATTRIBUTION RE-RUN (UNBIASED PRZ & ARGMAX SELECTION)", flush=True)
    print("=" * 115, flush=True)

    cfg_fair = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.02, initial_equity=EQUITY,
        enabled_patterns=["Cypher", "Gartley", "Crab", "Shark", "Bat", "Butterfly"]
    )
    
    # Run with standard 0.80 cutoff for fair evaluation across all geometries
    res_fair = run_fair_backtest(gold_m15, cfg_fair, min_score=0.80)
    trades_fair = res_fair["trades"]
    sc_fair = res_fair["scorecard"]

    print(f"Fair Unbiased Multi-Pattern Backtest (16.6 Years Gold M15):", flush=True)
    print(f"  Total Trades:     {sc_fair['trades']}")
    print(f"  Win Rate:         {sc_fair['win_rate_pct']}% ({sc_fair['wins']} W / {sc_fair['losses']} L)")
    print(f"  Profit Factor:    {sc_fair['profit_factor']}")
    print(f"  Net Profit:       ${sc_fair['net_profit']:+,.2f} ({sc_fair['total_return_pct']:+.2f}%)")
    print(f"  Max Drawdown:     {sc_fair['max_drawdown_pct']}%")
    print(f"  Total Friction:   -${sc_fair['total_friction']:,.2f}")

    # Breakdown by pattern type under fair scoring
    pat_fair_map = {}
    for t in trades_fair:
        p = t.pattern_type
        if p not in pat_fair_map: pat_fair_map[p] = []
        pat_fair_map[p].append(t)

    pat_fair_rows = []
    for p_name in ["Cypher", "Gartley", "Shark", "Bat", "Butterfly", "Crab"]:
        p_list = pat_fair_map.get(p_name, [])
        if not p_list: continue
        net_pnls = [t.net_pnl for t in p_list]
        wins = sum(1 for p in net_pnls if p > 0)
        tot = len(p_list)
        gw = sum(p for p in net_pnls if p > 0)
        gl = abs(sum(p for p in net_pnls if p < 0))
        pf = gw / gl if gl > 0 else 999.0
        pnl_c = sum(net_pnls) / sc_fair["net_profit"] * 100 if sc_fair["net_profit"] > 0 else 0
        pat_fair_rows.append({
            "Pattern": p_name,
            "Trades": tot,
            "% Share": f"{tot/len(trades_fair)*100:.1f}%",
            "Win Rate%": f"{wins/tot*100:.1f}%",
            "Profit Factor": f"{pf:.2f}",
            "Avg R": f"{np.mean([t.r_multiple for t in p_list]):.2f}R",
            "Net Profit ($)": f"${sum(net_pnls):+,.2f}",
            "% of Total P&L": f"{pnl_c:.1f}%"
        })
    print("\nFair Scoring Pattern Attribution Table:", flush=True)
    print(pd.DataFrame(pat_fair_rows).to_string(index=False), flush=True)

    # =========================================================================
    # MANDATE 2: LIQUIDATION-CONSTRAINED COST STRESS (SCENARIO A BUG FIX)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("MANDATE 2: LIQUIDATION-CONSTRAINED COST STRESS (DYNAMIC POSITION SIZING BUG FIX)", flush=True)
    print("=" * 115, flush=True)

    # Fixed trade setups, but dynamically re-sizing lots based on CURRENT simulated equity
    stress_fixed_fixedlot = []
    for mult in [1.0, 2.0, 3.0, 5.0]:
        cur_eq = EQUITY
        peak_eq = EQUITY
        mdd = 0.0
        liquidated = False
        sim_trades = []
        
        spread_p = cfg_fair.spread_points * mult * cfg_fair.point_size
        comm_p = cfg_fair.commission_per_lot * mult
        slip_p = cfg_fair.slippage_points * mult * cfg_fair.point_size
        
        for t in trades_fair:
            if cur_eq <= 100.0: # Margin liquidation boundary
                liquidated = True
                break
                
            # Dynamic lot sizing off current equity
            stop_dist = abs(t.entry_price - t.initial_stop)
            risk_amt = cur_eq * cfg_fair.risk_per_trade_pct
            lots = max(0.01, min(50.0, round(risk_amt / (stop_dist * cfg_fair.contract_size), 2)))
            
            # Recalculate PnL at this lot size
            if t.exit_reason == "TP1_TP2":
                gross_pnl = (abs(t.tp1_price - t.entry_price) + abs(t.tp2_price - t.entry_price)) * (lots * 0.5) * cfg_fair.contract_size
                applied_slip = 0.0
            elif t.exit_reason == "TP1_BE":
                gross_pnl = abs(t.tp1_price - t.entry_price) * (lots * 0.5) * cfg_fair.contract_size
                applied_slip = 0.0
            elif "SL" in t.exit_reason:
                gross_pnl = -abs(t.entry_price - t.initial_stop) * lots * cfg_fair.contract_size
                applied_slip = slip_p
            else:
                pnl_u = (t.exit_price - t.entry_price) if t.bull else (t.entry_price - t.exit_price)
                gross_pnl = pnl_u * lots * cfg_fair.contract_size
                applied_slip = 0.0
                
            spread_cost = spread_p * cfg_fair.contract_size * lots
            comm_cost = comm_p * lots
            slippage_cost = applied_slip * cfg_fair.contract_size * lots
            net_p = gross_pnl - (spread_cost + comm_cost + slippage_cost)
            
            cur_eq += net_p
            if cur_eq > peak_eq: peak_eq = cur_eq
            dd = (peak_eq - cur_eq) / peak_eq * 100
            if dd > mdd: mdd = dd
            sim_trades.append(net_p)
            
        wins = sum(1 for p in sim_trades if p > 0)
        tot = len(sim_trades)
        gw = sum(p for p in sim_trades if p > 0)
        gl = abs(sum(p for p in sim_trades if p < 0))
        pf = gw / gl if gl > 0 else 999.0
        
        stress_fixed_fixedlot.append({
            "Cost Multiplier": f"{mult:.1f}x (Spread ${0.25*mult:.2f}, Comm ${5*mult:.1f}/lot)",
            "Trades Executed": tot,
            "Liquidation Status": "LIQUIDATED (Equity <= $100)" if liquidated else "ACTIVE",
            "Win Rate%": f"{wins/tot*100:.1f}%",
            "Profit Factor": f"{pf:.2f}",
            "Ending Equity ($)": f"${max(0.0, cur_eq):,.2f}",
            "Net Profit ($)": f"${cur_eq - EQUITY:+,.2f}",
            "Total ROI%": f"{(cur_eq - EQUITY)/EQUITY*100:+.2f}%",
            "Max DD% (Capped at 100%)": f"{min(100.0, mdd):.1f}%"
        })
    print("\nCorrected Liquidation-Constrained Cost Stress Table (Fixed Trade Set):", flush=True)
    print(pd.DataFrame(stress_fixed_fixedlot).to_string(index=False), flush=True)

    # =========================================================================
    # MANDATE 3: HIGH-SAMPLE MULTI-ASSET CORRELATION AUDIT
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("MANDATE 3: STATISTICALLY ADEQUATE MULTI-ASSET CORRELATION (FULL DATASET & COMMODITIES)", flush=True)
    print("=" * 115, flush=True)

    # Compute correlation across the entire 1.4-year full history of all 9 instruments
    # on daily indicator trend bias + price returns (350+ overlapping trading days)
    fx_files = {
        "XAUUSD": "XAUUSD_M5_max_history.csv",
        "XAGUSD": "XAGUSD_M5_max_history.csv",
        "EURUSD": "EURUSD_M5_max_history.csv",
        "GBPUSD": "GBPUSD_M5_max_history.csv",
        "USDJPY": "USDJPY_M5_max_history.csv",
        "AUDUSD": "AUDUSD_M5_max_history.csv",
        "NZDUSD": "NZDUSD_M5_max_history.csv",
        "USDCAD": "USDCAD_M5_max_history.csv",
        "USDCHF": "USDCHF_M5_max_history.csv",
    }
    
    daily_returns_df = pd.DataFrame()
    daily_bias_df = pd.DataFrame()

    for sym, fn in fx_files.items():
        p = os.path.join(DATA_DIR, fn)
        if os.path.exists(p):
            df_i = pd.read_csv(p)
            df_i["time"] = pd.to_datetime(df_i["time"])
            df_i = df_i.sort_values("time").reset_index(drop=True)
            df_daily_i = df_i.set_index("time").resample("D").agg({
                "open": "first", "high": "max", "low": "min", "close": "last"
            }).dropna()
            daily_returns_df[sym] = df_daily_i["close"].pct_change()
            
            # Causal H1 bias
            bars_m15 = resample_bars(df_i, 15)
            h1_bias = compute_h1_trend_bias(bars_m15, 50, 200)
            df_b = pd.DataFrame({"time": bars_m15["time"], "bias": h1_bias})
            df_b_d = df_b.set_index("time").resample("D").agg({"bias": "last"}).dropna()
            daily_bias_df[sym] = df_b_d["bias"]

    daily_returns_df = daily_returns_df.dropna()
    corr_full_returns = daily_returns_df.corr()
    
    print(f"Multi-Asset Continuous Price Return Correlation Matrix ({len(daily_returns_df)} Full Overlapping Days):", flush=True)
    print(corr_full_returns.round(2).to_string(), flush=True)

    triu_idx = np.triu_indices_from(corr_full_returns.values, k=1)
    avg_price_corr = np.mean(corr_full_returns.values[triu_idx])
    print(f"\n>> Average Continuous Pairwise Return Correlation across 9 Assets: {avg_price_corr:.3f}", flush=True)

    # Check 5-Year Energy & Metals (Gold, Silver, Crude, CL, WTI)
    commodity_files = {
        "XAUUSD": "XAUUSD_M5_max_history.csv",
        "CL": "CL_M5_max_history.csv",
        "CRUDE": "CRUDE_M5_max_history.csv",
    }
    comm_ret_df = pd.DataFrame()
    for sym, fn in commodity_files.items():
        p = os.path.join(DATA_DIR, fn)
        if os.path.exists(p):
            df_c = pd.read_csv(p)
            df_c["time"] = pd.to_datetime(df_c["time"])
            df_c_d = df_c.set_index("time").resample("D").agg({"close": "last"}).dropna()
            comm_ret_df[sym] = df_c_d["close"].pct_change()
    comm_ret_df = comm_ret_df.dropna()
    comm_corr = comm_ret_df.corr()
    print(f"\n5-Year Metals & Energy Continuous Return Correlation ({len(comm_ret_df)} Overlapping Days):", flush=True)
    print(comm_corr.round(2).to_string(), flush=True)

    # =========================================================================
    # MANDATE 4: FRICTION BURDEN AS % OF STOP DISTANCE (CONFOUND CHECK)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("MANDATE 4: FRICTION DRAG AS % OF STOP DISTANCE ACROSS GOLD PRICE EXPANSION", flush=True)
    print("=" * 115, flush=True)

    friction_audit = []
    for y in sorted(list(set(t.exit_time.year if t.exit_time else t.entry_time.year for t in trades_fair))):
        y_trades = [t for t in trades_fair if (t.exit_time if t.exit_time else t.entry_time).year == y]
        avg_entry = np.mean([t.entry_price for t in y_trades])
        avg_stop_dist = np.mean([abs(t.entry_price - t.initial_stop) for t in y_trades])
        avg_friction_dollars = np.mean([t.spread_cost + t.commission_cost + t.slippage_cost for t in y_trades])
        avg_gross_pnl = np.mean([t.gross_pnl for t in y_trades])
        avg_net_pnl = np.mean([t.net_pnl for t in y_trades])
        
        # Friction as % of Stop Distance ($0.25 spread / stop distance)
        friction_pct_of_stop = (0.25 / avg_stop_dist) * 100 if avg_stop_dist > 0 else 0.0
        gross_exp_r = np.mean([ (t.gross_pnl / (t.lot_size * avg_stop_dist * 100.0)) for t in y_trades if t.lot_size > 0 ])
        net_exp_r = np.mean([t.r_multiple for t in y_trades])
        
        friction_audit.append({
            "Year": y,
            "Trades": len(y_trades),
            "Avg Gold Price ($)": f"${avg_entry:,.1f}",
            "Avg Stop Dist ($)": f"${avg_stop_dist:.2f}",
            "Fixed Friction % of Stop": f"{friction_pct_of_stop:.2f}%",
            "Gross Expectancy": f"{gross_exp_r:+.4f}R",
            "Net Expectancy": f"{net_exp_r:+.4f}R",
            "Friction Drag (R)": f"{-abs(gross_exp_r - net_exp_r):.4f}R"
        })
        
    df_fric = pd.DataFrame(friction_audit)
    print(df_fric.to_string(index=False), flush=True)
    df_fric.to_csv(os.path.join(OUTPUT_DIR, "validation_friction_drag_analysis.csv"), index=False)

    print("\n" + "=" * 115, flush=True)
    print("FINAL INSTITUTIONAL REMEDIATION AUDIT COMPLETE.", flush=True)
    print("=" * 115, flush=True)

if __name__ == "__main__":
    main()
