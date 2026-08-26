"""
Institutional Multi-Asset Realized Portfolio, Square-Root Market Impact, and DSR Validation Suite.
Addresses all 5 mandates from the Model Risk Review:
1. Realized Multi-Asset Portfolio Backtest: Runs Shark+Cypher+Gartley on Gold, Silver, Crude Oil, and EURUSD across full overlapping history.
2. Combines actual daily P&Ls into a true multi-asset portfolio equity curve -> Computes true realized Portfolio Sharpe, PF, and Max DD.
3. Correct DSR Application: Penalizes the actual realized portfolio Sharpe across honest trial counts N_trials in [10, 20, 50, 100].
4. Out-of-Sample Shark Fat-Tail Check (65 trades): Loss breakdown and PF with Top 1, Top 3, and Top 5 trades removed.
5. Institutional Scale Cost-Stress ($1,000,000 AUM) with Square-Root Market Impact Model:
   Impact = eta * DailyVol * sqrt(OrderSize / ADV).
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

def run_fair_backtest(bars: pd.DataFrame, cfg: HarmonicV3Config, min_score: float = 0.80, fixed_capital_mode: bool = True):
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
            
            denom_eq = cfg.initial_equity if fixed_capital_mode else equity
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
                        sizing_eq = cfg.initial_equity if fixed_capital_mode else equity
                        risk_amt = max(0.0, sizing_eq * cfg.risk_per_trade_pct)
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
    print("HARMONIC_EA_V3_CHAMPION -- REALIZED MULTI-ASSET PORTFOLIO & INSTITUTIONAL DSR SUITE", flush=True)
    print("=" * 115, flush=True)

    # =========================================================================
    # MANDATE 1 & 2: REALIZED MULTI-ASSET PORTFOLIO BACKTEST & DIRECT EQUITY CURVE
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("MANDATE 1 & 2: REALIZED MULTI-ASSET PORTFOLIO BACKTEST (ACTUAL REALIZED P&L COMBINATION)", flush=True)
    print("=" * 115, flush=True)

    portfolio_specs = {
        "XAUUSD": {"file": "XAUUSD_M5_max_history.csv", "pt": 0.01,    "ct": 100.0,    "sp": 25.0, "sl": 10.0, "use_years": True},
        "XAGUSD": {"file": "XAGUSD_M5_max_history.csv", "pt": 0.001,   "ct": 5000.0,   "sp": 20.0, "sl": 10.0, "use_years": False},
        "CL":     {"file": "CL_M5_max_history.csv",     "pt": 0.01,    "ct": 1000.0,   "sp": 3.0,  "sl": 2.0,  "use_years": False},
        "EURUSD": {"file": "EURUSD_M5_max_history.csv", "pt": 0.00001, "ct": 100000.0, "sp": 10.0, "sl": 5.0,  "use_years": False},
    }

    asset_trades = {}
    asset_summaries = []
    all_trade_objects = []

    # Common multi-year overlapping window for direct portfolio combination: 2021-01-01 to 2026-08-25
    overlap_start = "2021-01-01"
    overlap_end = "2026-08-25 23:59:59"

    for sym, spec in portfolio_specs.items():
        if spec["use_years"]:
            df_raw = load_gold_data()
        else:
            p = os.path.join(DATA_DIR, spec["file"])
            if not os.path.exists(p): continue
            df_raw = pd.read_csv(p)
            df_raw["time"] = pd.to_datetime(df_raw["time"])
            df_raw = df_raw.sort_values("time").reset_index(drop=True)

        # Filter to overlapping multi-year period
        df_sub = df_raw[(df_raw["time"] >= overlap_start) & (df_raw["time"] <= overlap_end)].reset_index(drop=True)
        if len(df_sub) < 100: continue
        bars_m15 = resample_bars(df_sub, 15)

        cfg_asset = HarmonicV3Config(
            symbol=sym, point_size=spec["pt"], contract_size=spec["ct"],
            spread_points=spec["sp"], slippage_points=spec["sl"], commission_per_lot=5.00,
            risk_per_trade_pct=0.015, # 1.5% institutional risk
            initial_equity=10_000.0,
            enabled_patterns=["Shark", "Cypher", "Gartley"]
        )
        res = run_fair_backtest(bars_m15, cfg_asset, min_score=0.80, fixed_capital_mode=True)
        t_list = res["trades"]
        sc = res["scorecard"]
        asset_trades[sym] = t_list
        all_trade_objects.extend(t_list)

        r_vals = [t.r_multiple for t in t_list]
        sr_asset = (np.mean(r_vals) / np.std(r_vals, ddof=1) * np.sqrt(len(t_list) / 5.6)) if len(r_vals) > 1 else 0.0

        asset_summaries.append({
            "Asset": sym,
            "History Period": f"{df_sub['time'].min().strftime('%Y-%m')} to {df_sub['time'].max().strftime('%Y-%m')}",
            "Trades": sc.get("trades", 0),
            "Win Rate%": f"{sc.get('win_rate_pct', 0):.1f}%",
            "Profit Factor": f"{sc.get('profit_factor', 0):.2f}",
            "Net Profit ($10k Base)": f"${sc.get('net_profit', 0):+,.2f}",
            "Max DD%": f"{sc.get('max_drawdown_pct', 0):.1f}%",
            "Annualized Sharpe": f"{sr_asset:.2f}"
        })

    print("Individual Asset Measured Performance (5.6-Year Multi-Asset Overlap 2021–2026):", flush=True)
    print(pd.DataFrame(asset_summaries).to_string(index=False), flush=True)

    # Construct True Combined Multi-Asset Daily Equity Curve
    all_trade_objects.sort(key=lambda t: t.exit_time if t.exit_time else t.entry_time)
    daily_dates = pd.date_range(overlap_start, "2026-08-25", freq="D")
    daily_combined_pnl = {d: 0.0 for d in daily_dates}

    for t in all_trade_objects:
        ts = t.exit_time if t.exit_time else t.entry_time
        if ts:
            d_key = pd.Timestamp(ts.date())
            if d_key in daily_combined_pnl:
                daily_combined_pnl[d_key] += t.net_pnl

    daily_pnl_series = pd.Series(daily_combined_pnl)
    comb_eq_curve = [10_000.0]
    for p in daily_pnl_series.values:
        comb_eq_curve.append(comb_eq_curve[-1] + p)

    comb_peak = 10_000.0
    comb_mdd = 0.0
    for v in comb_eq_curve:
        if v > comb_peak: comb_peak = v
        dd = (comb_peak - v) / comb_peak * 100
        if dd > comb_mdd: comb_mdd = dd

    tot_comb_net = sum(daily_pnl_series.values)
    comb_trades = len(all_trade_objects)
    comb_wins = sum(1 for t in all_trade_objects if t.net_pnl > 0)
    comb_gw = sum(t.net_pnl for t in all_trade_objects if t.net_pnl > 0)
    comb_gl = abs(sum(t.net_pnl for t in all_trade_objects if t.net_pnl < 0))
    comb_pf = comb_gw / comb_gl if comb_gl > 0 else 999.0

    # Realized Combined Daily Sharpe
    active_daily_returns = daily_pnl_series / 10_000.0
    realized_daily_sr = (active_daily_returns.mean() / active_daily_returns.std(ddof=1) * np.sqrt(252)) if active_daily_returns.std(ddof=1) > 0 else 0.0

    # Realized Combined Trade Sharpe
    comb_rs = [t.r_multiple for t in all_trade_objects]
    realized_trade_sr = (np.mean(comb_rs) / np.std(comb_rs, ddof=1)) if np.std(comb_rs, ddof=1) > 0 else 0.0
    realized_ann_sr = realized_trade_sr * np.sqrt(comb_trades / 5.6)

    print("\n--- ACTUAL REALIZED COMBINED PORTFOLIO PERFORMANCE (5.6 Years, 2021–2026) ---", flush=True)
    print(f"  Total Trades Across Portfolio:   {comb_trades} (~{comb_trades/5.6:.1f} trades/year)")
    print(f"  Portfolio Win Rate:              {comb_wins/comb_trades*100:.1f}% ({comb_wins} Wins / {comb_trades - comb_wins} Losses)")
    print(f"  Portfolio Profit Factor:         {comb_pf:.2f}")
    print(f"  Portfolio Realized Net Profit:   ${tot_comb_net:+,.2f} (+{tot_comb_net/10_000.0*100:.2f}% ROI on $10k base)")
    print(f"  Portfolio Maximum Drawdown:      {comb_mdd:.1f}%")
    print(f"  Realized Annualized Daily Sharpe: {realized_daily_sr:.2f}")
    print(f"  Realized Trade-Based Ann. Sharpe: {realized_ann_sr:.2f}")

    # =========================================================================
    # MANDATE 3: HONEST DSR ON REALIZED PORTFOLIO SHARPE (N_trials = 10, 20, 50, 100)
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("MANDATE 3: HONEST DSR ON REALIZED COMBINED PORTFOLIO (N_trials in [5, 10, 20, 50, 100])", flush=True)
    print("=" * 115, flush=True)

    skew_port = float(stats.skew(comb_rs))
    kurt_port = float(stats.kurtosis(comb_rs, fisher=False))
    euler_mascheroni = 0.5772156649
    denom_port = np.sqrt(1.0 - skew_port * realized_trade_sr + ((kurt_port - 1.0) / 4.0) * (realized_trade_sr ** 2))

    print(f"Combined Portfolio Distribution Inputs (n = {comb_trades} trades):")
    print(f"  Mean R:                          {np.mean(comb_rs):+.4f}R")
    print(f"  Std R:                           {np.std(comb_rs):.4f}R")
    print(f"  Per-Trade Sharpe (SR_trade):     {realized_trade_sr:.4f}")
    print(f"  Realized Annualized Sharpe:      {realized_ann_sr:.2f} (Daily Sharpe: {realized_daily_sr:.2f})")
    print(f"  Skewness:                        {skew_port:.4f}")
    print(f"  Kurtosis (Pearson):              {kurt_port:.4f}")

    dsr_port_table = []
    for N in [1, 2, 5, 10, 20, 50, 100]:
        if N == 1: sr_0_t = 0.0
        else:
            sr_0_t = ((1.0 - euler_mascheroni) * stats.norm.ppf(1.0 - 1.0 / N) +
                      euler_mascheroni * stats.norm.ppf(1.0 - 1.0 / (N * math.e)))

        dsr_z_ann = ((realized_ann_sr - sr_0_t) * np.sqrt(5.6 - 1)) / denom_port if denom_port > 0 else 0.0
        dsr_val_ann = float(stats.norm.cdf(dsr_z_ann))

        dsr_port_table.append({
            "Research Trials (N_trials)": N,
            "Null Hurdle SR_0": f"{sr_0_t:.3f}",
            "Portfolio Realized Sharpe": f"{realized_ann_sr:.2f}",
            "Annualized DSR": f"{dsr_val_ann:.4f}",
            "p-value": f"{1-dsr_val_ann:.4e}",
            "DSR Status (>0.9500)": "PASS" if dsr_val_ann > 0.95 else "FAIL"
        })
    print("\nHonest DSR Table on Realized Multi-Asset Portfolio (Penalizing for Research Trials):", flush=True)
    print(pd.DataFrame(dsr_port_table).to_string(index=False), flush=True)

    # =========================================================================
    # MANDATE 4: OUT-OF-SAMPLE SHARK (65 TRADES) FAT-TAIL & SENSITIVITY CHECK
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("MANDATE 4: OUT-OF-SAMPLE SHARK FAT-TAIL & SENSITIVITY AUDIT (2021–2026, 65 TRADES)", flush=True)
    print("=" * 115, flush=True)

    gold_trades_oos = asset_trades.get("XAUUSD", [])
    shark_oos_trades = [t for t in gold_trades_oos if t.pattern_type == "Shark"]
    shark_oos_pnls = [t.net_pnl for t in shark_oos_trades]
    shark_oos_rs = [t.r_multiple for t in shark_oos_trades]
    
    # Loss count & exit breakdown
    shark_oos_exits = {}
    for t in shark_oos_trades:
        shark_oos_exits[t.exit_reason] = shark_oos_exits.get(t.exit_reason, 0) + 1

    wins_oos = sum(1 for p in shark_oos_pnls if p > 0)
    losses_oos = sum(1 for p in shark_oos_pnls if p <= 0)
    tot_pnl_oos = sum(shark_oos_pnls)
    gw_oos = sum(p for p in shark_oos_pnls if p > 0)
    gl_oos = abs(sum(p for p in shark_oos_pnls if p < 0))
    raw_pf_oos = gw_oos / gl_oos if gl_oos > 0 else 999.0

    print(f"Total Shark OOS Trades:       {len(shark_oos_trades)}")
    print(f"Wins / Losses:                {wins_oos} Wins / {losses_oos} Losses (Win Rate: {wins_oos/len(shark_oos_trades)*100:.1f}%)")
    print(f"Total Net Cash Profit:        ${tot_pnl_oos:+,.2f}")
    print(f"Gross Win / Gross Loss:       +${gw_oos:,.2f} / -${gl_oos:,.2f}")
    print(f"Raw Profit Factor:            {raw_pf_oos:.2f}")
    print(f"Exit Reason Breakdown:")
    for ex, cnt in sorted(shark_oos_exits.items(), key=lambda x: x[1], reverse=True):
        print(f"  * {ex:<12}: {cnt:>2} trades ({cnt/len(shark_oos_trades)*100:5.1f}%)")

    # Remove Top 1, Top 3, Top 5 trades
    sorted_shark_oos = sorted(shark_oos_pnls, reverse=True)
    
    def calc_trimmed_pf(pnls, n_trim):
        trimmed = pnls[n_trim:]
        gw = sum(p for p in trimmed if p > 0)
        gl = abs(sum(p for p in trimmed if p < 0))
        pf = gw / gl if gl > 0 else 999.0
        return pf, sum(trimmed)

    pf_no_top1, pnl_no_top1 = calc_trimmed_pf(sorted_shark_oos, 1)
    pf_no_top3, pnl_no_top3 = calc_trimmed_pf(sorted_shark_oos, 3)
    pf_no_top5, pnl_no_top5 = calc_trimmed_pf(sorted_shark_oos, 5)

    print(f"\nShark OOS Sensitivity to Outliers:")
    print(f"  * Baseline (All 65 Trades):               PF = {raw_pf_oos:.2f} | Net = ${tot_pnl_oos:+,.2f}")
    print(f"  * Excluding Single Best Trade (Top 1):    PF = {pf_no_top1:.2f} | Net = ${pnl_no_top1:+,.2f} (Top 1 = ${sorted_shark_oos[0]:.2f})")
    print(f"  * Excluding Top 3 Best Trades:            PF = {pf_no_top3:.2f} | Net = ${pnl_no_top3:+,.2f}")
    print(f"  * Excluding Top 5 Best Trades:            PF = {pf_no_top5:.2f} | Net = ${pnl_no_top5:+,.2f}")

    # =========================================================================
    # MANDATE 5: INSTITUTIONAL CAPACITY STRESS ($1,000,000 AUM) WITH SQUARE-ROOT IMPACT
    # =========================================================================
    print("\n" + "=" * 115, flush=True)
    print("MANDATE 5: INSTITUTIONAL CAPACITY STRESS ($1,000,000 AUM) WITH SQUARE-ROOT IMPACT", flush=True)
    print("=" * 115, flush=True)

    # Square-Root Market Impact Formulation (Almgren-Chriss / Barra microstructure):
    # Impact (points) = eta * DailyVolPoints * sqrt(OrderSize / ADV)
    # For Gold: ADV ~ 100,000 lots/day ($25B+), Daily ATR ~ $25.00 (2,500 points), eta ~ 0.10
    aum = 1_000_000.0
    adv_gold_lots = 100_000.0
    eta = 0.10
    daily_vol_points = 2500.0 # 25.00 dollars on Gold

    scale_stress_table = []
    gold_raw_16 = load_gold_data()
    bars_m15_16 = resample_bars(gold_raw_16, 15)
    
    cfg_scale = HarmonicV3Config(
        symbol="XAUUSD", point_size=0.01, contract_size=100.0,
        spread_points=25.0, slippage_points=10.0, commission_per_lot=5.00,
        risk_per_trade_pct=0.015, initial_equity=aum,
        enabled_patterns=["Shark", "Cypher", "Gartley"]
    )
    res_scale_base = run_fair_backtest(bars_m15_16, cfg_scale, min_score=0.80, fixed_capital_mode=True)
    trades_scale = res_scale_base["trades"]

    for mult in [1.0, 1.5, 2.0, 2.5, 3.0, 5.0]:
        pnls_aum = []
        lots_list = []
        for t in trades_scale:
            # Scaled lot size on $1M AUM ($15,000 risk per trade)
            stop_dist = abs(t.entry_price - t.initial_stop)
            lots = max(0.1, min(50.0, round((aum * 0.015) / (stop_dist * 100.0), 1)))
            lots_list.append(lots)
            
            spread_c = (25.0 * mult) * 0.01 * 100.0 * lots
            comm_c = (5.00 * mult) * lots
            
            # Square-root market impact
            sqrt_impact_points = eta * daily_vol_points * math.sqrt(lots / adv_gold_lots)
            base_slip_points = (10.0 * mult) if "SL" in t.exit_reason else 0.0
            total_slip_points = base_slip_points + sqrt_impact_points
            slip_c = total_slip_points * 0.01 * 100.0 * lots
            
            # Scaled gross PnL
            if t.exit_reason == "TP1_TP2":
                gross = (abs(t.tp1_price - t.entry_price) + abs(t.tp2_price - t.entry_price)) * (lots * 0.5) * 100.0
            elif t.exit_reason == "TP1_BE":
                gross = abs(t.tp1_price - t.entry_price) * (lots * 0.5) * 100.0
            elif "SL" in t.exit_reason:
                gross = -abs(t.entry_price - t.initial_stop) * lots * 100.0
            else:
                pnl_u = (t.exit_price - t.entry_price) if t.bull else (t.entry_price - t.exit_price)
                gross = pnl_u * lots * 100.0
                
            net_t = gross - (spread_c + comm_c + slip_c)
            pnls_aum.append(net_t)
            
        w_cnt = sum(1 for p in pnls_aum if p > 0)
        tot_cnt = len(pnls_aum)
        gw_aum = sum(p for p in pnls_aum if p > 0)
        gl_aum = abs(sum(p for p in pnls_aum if p < 0))
        pf_aum = gw_aum / gl_aum if gl_aum > 0 else 999.0
        tot_net_aum = sum(pnls_aum)
        
        eq_aum = [aum]
        for p in pnls_aum: eq_aum.append(eq_aum[-1] + p)
        pk_aum = aum
        mdd_aum = 0.0
        for v in eq_aum:
            if v > pk_aum: pk_aum = v
            dd = (pk_aum - v) / pk_aum * 100
            if dd > mdd_aum: mdd_aum = dd
            
        scale_stress_table.append({
            "Cost Multiplier": f"{mult:.1f}x (Spread ${0.25*mult:.2f})",
            "AUM Base": f"${aum:,.0f}",
            "Avg Lot Size": f"{np.mean(lots_list):.1f} lots",
            "Win Rate%": f"{w_cnt/tot_cnt*100:.1f}%",
            "Profit Factor": f"{pf_aum:.2f}",
            "Net Profit ($1M Base)": f"${tot_net_aum:+,.2f}",
            "16.6-Yr Total ROI%": f"{tot_net_aum/aum*100:+.2f}%",
            "Max DD%": f"{mdd_aum:.1f}%"
        })
    print("Institutional $1,000,000 AUM Stress Table (with Square-Root Market Impact):", flush=True)
    print(pd.DataFrame(scale_stress_table).to_string(index=False), flush=True)

    print("\n" + "=" * 115, flush=True)
    print("ALL 5 INSTITUTIONAL MANDATES COMPLETE.", flush=True)
    print("=" * 115, flush=True)

if __name__ == "__main__":
    main()
