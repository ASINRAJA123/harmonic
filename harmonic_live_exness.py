"""
===================================================================================
HARMONIC EA V3 CHAMPION — LIVE EXNESS MT5 TRADING ENGINE (WITH MONGODB CLOUD LOGS)
===================================================================================
Account: #474471944 | Server: Exness-MT5Trial15
Strategy: Institutional Harmonic Pattern Engine (Cypher, Gartley, Crab, Shark)
Timeframe: M15 Execution | H1 Trend Filter (EMA 50/200)
Risk Management: Exact USD Broker Sizing (mt5.order_calc_profit) | Progressive 3-Stage Trailing
Telemetry: MongoDB Cloud Sync (cluster0.tt1v1.mongodb.net / harmonic_trading) + Local File
===================================================================================
"""

import os
import sys
import time
import datetime
import math
import logging
import numpy as np
import pandas as pd
import MetaTrader5 as mt5

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Ensure logs directory exists
LOGS_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOGS_DIR, "harmonic_live.log")

# Setup Logging
logger = logging.getLogger("HarmonicLiveBot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s UTC] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

# Console Handler
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# File Handler (Continuous Append)
fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
logger.addHandler(fh)

from core.mongo_logger import mongo_logger
from core.config import HarmonicRatios, PATTERN_MAP, PATTERN_TARGETS, compute_target_price
from core.pattern_scanner import HarmonicPattern, validate_pattern

def log_msg(msg, level="INFO", log_type="SYSTEM", metadata=None):
    logger.info(msg)
    # Stream to MongoDB
    mongo_logger.log(level, msg, log_type=log_type, metadata=metadata)

# ==============================================================================
# CONFIGURATION
# ==============================================================================
EXNESS_TERMINAL_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"
DEMO_LOGIN = 474471944
DEMO_SERVER = "Exness-MT5Trial15"

MAGIC_NUMBER = 888333
TRADE_COMMENT_PREFIX = "HarmonicV3"

# Upgraded 6-Asset Alpha Universe (Gold, Crude Oil, Silver, GBP/USD, EUR/USD, USD/JPY)
SYMBOLS = [
    "XAUUSDm",   # 1. Gold (Spot) - Primary Alpha Champion
    "USOILm",    # 2. Crude Oil (WTI) - Orthogonal Commodity Diversifier
    "XAGUSDm",   # 3. Silver (Spot) - Precious Metals High-Beta Engine
    "GBPUSDm",   # 4. GBP/USD - Top Forex Alpha Pair
    "EURUSDm",   # 5. EUR/USD - High Liquidity / Low Spread Trend Engine
    "USDJPYm"    # 6. USD/JPY - Safe Low-Drawdown Diversifier
]

TIMEFRAME_M15 = mt5.TIMEFRAME_M15
TIMEFRAME_H1 = mt5.TIMEFRAME_H1
LOOKBACK_BARS = 350

ENABLED_PATTERNS = ["Shark", "Cypher", "Gartley"]
MIN_SCORE = 0.80
PIVOT_LENGTHS = [3, 5, 8]
RISK_PER_TRADE_PCT = 0.015        # 1.5% Risk per trade (Institutional Sizing)
MAX_CONCURRENT_POSITIONS = 2      # Max open trades per symbol
MIN_ATR_STOP_MULT = 0.50          # Stop distance >= 0.50x ATR(14) (Model A Pure Harmonic Stop)
MIN_STOP_TO_SPREAD_RATIO = 4.5    # Stop distance >= 4.5x Spread

SESSION_FILTER_ENABLED = True
SESSION_START_HOUR_UTC = 13
SESSION_END_HOUR_UTC = 20

TRADE_COMMENT_PREFIX = "HEAV3"
MAGIC_NUMBER = 888333
POLL_INTERVAL_SECONDS = 2  # Reduced to 2s to minimize execution gap at candle close


# ==============================================================================
# MT5 CONNECTION & INITIALIZATION
# ==============================================================================
def connect_mt5(terminal_path=EXNESS_TERMINAL_PATH, login=DEMO_LOGIN, server=DEMO_SERVER):
    log_msg("=" * 80)
    log_msg(">>> INITIALIZING EXNESS MT5 CONNECTION...")
    log_msg(f"  Target Account : #{login}")
    log_msg(f"  Target Server  : {server}")
    log_msg("=" * 80)

    initialized = False
    if os.path.exists(terminal_path):
        if mt5.initialize(path=terminal_path):
            initialized = True
            log_msg(f"  [OK] Connected via direct path: {terminal_path}")

    if not initialized:
        if mt5.initialize():
            initialized = True
            log_msg("  [OK] Connected via system default MT5 terminal")
        else:
            log_msg(f"  [ERROR] MT5 Initialize Failed: {mt5.last_error()}", level="ERROR")
            return False

    account_info = mt5.account_info()
    if account_info is None:
        log_msg(f"  [ERROR] Failed to fetch account info: {mt5.last_error()}", level="ERROR")
        return False

    if account_info.login != login:
        log_msg(f"  Switching login to #{login} on {server}...")
        logged_in = mt5.login(login=login, server=server)
        if not logged_in:
            log_msg(f"  [ERROR] Login failed for #{login} on {server}. Error: {mt5.last_error()}", level="ERROR")
            return False
        account_info = mt5.account_info()

    algo_status = "[ENABLED]" if account_info.trade_expert else "[DISABLED] (Please toggle 'Algo Trading' ON in MT5)"

    log_msg("=" * 80)
    log_msg(">>> EXNESS MT5 LIVE CONNECTION ESTABLISHED")
    log_msg(f"  Account Number : #{account_info.login}")
    log_msg(f"  Account Name   : {account_info.name}")
    log_msg(f"  Server         : {account_info.server}")
    log_msg(f"  Currency       : {account_info.currency}")
    log_msg(f"  Balance        : ${account_info.balance:,.2f}")
    log_msg(f"  Equity         : ${account_info.equity:,.2f}")
    log_msg(f"  Free Margin    : ${account_info.margin_free:,.2f}")
    log_msg(f"  Leverage       : 1:{account_info.leverage}")
    log_msg(f"  Algo Trading   : {algo_status}")
    log_msg("=" * 80)

    # Sync bot state with MongoDB
    mongo_logger.update_bot_state({
        "account_login": account_info.login,
        "account_server": account_info.server,
        "account_name": account_info.name,
        "balance": account_info.balance,
        "equity": account_info.equity,
        "margin_free": account_info.margin_free,
        "leverage": account_info.leverage,
        "algo_enabled": bool(account_info.trade_expert),
        "is_online": True
    })

    return True


def resolve_symbol_names(symbol_list):
    valid_symbols = []
    log_msg("Active Trading Universe:")
    for sym in symbol_list:
        info = mt5.symbol_info(sym)
        if info is None:
            alt = sym[:-1] if sym.endswith("m") else (sym + "m")
            info = mt5.symbol_info(alt)
            if info is not None:
                sym = alt

        if info is not None:
            if not info.visible:
                mt5.symbol_select(sym, True)
            valid_symbols.append(sym)
            log_msg(f"  [+] {sym:10s} | Spread: {info.spread:4d} pts | Min Lot: {info.volume_min} | Step: {info.volume_step}")
        else:
            log_msg(f"  [!] Warning: Symbol {sym} not found on broker.", level="WARNING")
    return valid_symbols


# ==============================================================================
# INDICATORS & CALCULATIONS
# ==============================================================================
def fetch_rates_df(symbol, timeframe, n_bars=350):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
    if rates is None or len(rates) == 0:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def compute_ema(series, span):
    return pd.Series(series).ewm(span=span, adjust=False).mean().values


def compute_atr(highs, lows, closes, period=14):
    n = len(highs)
    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    return pd.Series(tr).rolling(window=period, min_periods=1).mean().values


def get_h1_trend_bias(symbol):
    df_h1 = fetch_rates_df(symbol, TIMEFRAME_H1, n_bars=250)
    if df_h1 is None or len(df_h1) < 200:
        return 0
        
    # Trade on Close logic for H1: Drop the actively forming H1 candle
    df_h1 = df_h1.iloc[:-1].reset_index(drop=True)
        
    closes = df_h1["close"].values
    ema50 = compute_ema(closes, 50)
    ema200 = compute_ema(closes, 200)

    last_close = closes[-1]
    last_ema50 = ema50[-1]
    last_ema200 = ema200[-1]

    if last_close > last_ema50 and last_ema50 >= last_ema200:
        return 1
    elif last_close < last_ema50 and last_ema50 <= last_ema200:
        return -1
    return 0


# ==============================================================================
# HARMONIC PATTERN DETECTION
# ==============================================================================
def scan_harmonic_patterns(df_m15, symbol=""):
    n = len(df_m15)
    if n < 50:
        return []

    highs = df_m15["high"].values
    lows = df_m15["low"].values

    known_highs = []
    known_lows = []
    pivots_at = [[] for _ in range(n)]

    for R in PIVOT_LENGTHS:
        for p in range(R, n - R):
            is_high = True
            for j in range(1, R + 1):
                if highs[p - j] > highs[p] or highs[p + j] > highs[p]:
                    is_high = False
                    break
            if is_high:
                conf_bar = p + R
                if conf_bar < n:
                    pivots_at[conf_bar].append((p, highs[p], "high"))

            is_low = True
            for j in range(1, R + 1):
                if lows[p - j] < lows[p] or lows[p + j] < lows[p]:
                    is_low = False
                    break
            if is_low:
                conf_bar = p + R
                if conf_bar < n:
                    pivots_at[conf_bar].append((p, lows[p], "low"))

    for i in range(n):
        for (p_idx, p_price, p_type) in pivots_at[i]:
            if p_type == "high":
                known_highs.append((p_idx, p_price))
            else:
                known_lows.append((p_idx, p_price))

    known_highs = sorted(list({p[0]: p for p in known_highs}.values()), key=lambda x: x[0])[-35:]
    known_lows = sorted(list({p[0]: p for p in known_lows}.values()), key=lambda x: x[0])[-35:]

    recent_patterns = []
    for check_bar in range(max(0, n - 3), n):
        new_pivots = pivots_at[check_bar]
        for (dI, dP, dType) in new_pivots:
            bull = (dType == "low")

            c_cands = [p for p in (known_highs if bull else known_lows) if p[0] < dI]
            b_cands = [p for p in (known_lows if bull else known_highs) if p[0] < dI]
            a_cands = [p for p in (known_highs if bull else known_lows) if p[0] < dI]
            x_cands = [p for p in (known_lows if bull else known_highs) if p[0] < dI]

            c_cands.sort(key=lambda x: x[0], reverse=True)
            b_cands.sort(key=lambda x: x[0], reverse=True)
            a_cands.sort(key=lambda x: x[0], reverse=True)
            x_cands.sort(key=lambda x: x[0], reverse=True)

            class Cfg:
                fib_error_pct = 15.0
                leg_asymmetry_pct = 250.0
                w_ratio_accuracy = 4.0
                w_prz_confluence = 2.0
                w_d_confluence = 3.0
                stop_pct = 75.0

            cfg_obj = Cfg()

            found_pat = None
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

                            for pat_name in ENABLED_PATTERNS:
                                r_def = PATTERN_MAP.get(pat_name)
                                if r_def is None: continue
                                pat = validate_pattern(xP, aP, bP, cP, dP, xI, aI, bI, cI, dI, r_def, cfg_obj, bull)
                                if pat is not None and pat.score >= MIN_SCORE:
                                    found_pat = pat
                                    break
                            if found_pat: break
                        if found_pat: break
                    if found_pat: break
                if found_pat: break

            if found_pat is not None:
                recent_patterns.append(found_pat)
                # Record to MongoDB
                mongo_logger.record_pattern({
                    "symbol": symbol,
                    "pattern": found_pat.pattern_type,
                    "bull": found_pat.bull,
                    "score": round(found_pat.score, 4),
                    "entry_price": found_pat.entry_price,
                    "stop_price": found_pat.stop_price,
                    "t1_price": found_pat.t1_price,
                    "t2_price": found_pat.t2_price
                })

    return recent_patterns


# ==============================================================================
# EXACT NATIVE BROKER RISK & LOT SIZING
# ==============================================================================
def calculate_lot_size(symbol, is_buy, entry_price, stop_price, risk_pct=RISK_PER_TRADE_PCT):
    account_info = mt5.account_info()
    sym_info = mt5.symbol_info(symbol)

    if account_info is None or sym_info is None:
        return 0.01

    equity = account_info.equity
    target_risk_usd = equity * risk_pct

    order_action = mt5.ORDER_TYPE_BUY if is_buy else mt5.ORDER_TYPE_SELL
    loss_for_1_lot = mt5.order_calc_profit(order_action, symbol, 1.0, entry_price, stop_price)

    if loss_for_1_lot is not None and loss_for_1_lot < 0:
        loss_per_1_lot_usd = abs(loss_for_1_lot)
    else:
        stop_dist = abs(entry_price - stop_price)
        loss_per_1_lot_usd = stop_dist * sym_info.trade_contract_size

    if loss_per_1_lot_usd <= 0:
        return sym_info.volume_min

    raw_lot = target_risk_usd / loss_per_1_lot_usd

    step = sym_info.volume_step if sym_info.volume_step > 0 else 0.01
    lots = math.floor(raw_lot / step) * step
    lots = max(sym_info.volume_min, min(sym_info.volume_max, round(lots, 2)))

    return lots


# ==============================================================================
# ORDER EXECUTION & TRADE LIFECYCLE
# ==============================================================================
def open_harmonic_trade(symbol, pattern, current_bid, current_ask):
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return False

    order_type = mt5.ORDER_TYPE_BUY if pattern.bull else mt5.ORDER_TYPE_SELL
    entry_price = current_ask if pattern.bull else current_bid

    # RIGID INSTITUTIONAL TARGETS
    sl_price = round(pattern.stop_price, sym_info.digits)
    tp1_price = round(pattern.t1_price, sym_info.digits)
    tp2_price = round(pattern.t2_price, sym_info.digits)

    # LATE ENTRY GATE PROTECTION
    if pattern.bull and entry_price >= tp1_price:
        log_msg(f"[{symbol}] Trade skipped: Late Entry ({entry_price}) already breached geometric TP1 ({tp1_price}).", level="TRADE")
        return False
    if not pattern.bull and entry_price <= tp1_price:
        log_msg(f"[{symbol}] Trade skipped: Late Entry ({entry_price}) already breached geometric TP1 ({tp1_price}).", level="TRADE")
        return False

    lot_size = calculate_lot_size(symbol, pattern.bull, entry_price, sl_price)

    comment = f"{TRADE_COMMENT_PREFIX}_{pattern.pattern_type[:3]}_{'B' if pattern.bull else 'S'}"

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": entry_price,
        "sl": sl_price,
        "tp": tp2_price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    dir_str = "BULLISH LONG [BUY]" if pattern.bull else "BEARISH SHORT [SELL]"
    expected_loss = mt5.order_calc_profit(order_type, symbol, lot_size, entry_price, sl_price)
    expected_loss_str = f"${abs(expected_loss):.2f}" if expected_loss else "N/A"

    log_msg(f"\n>>> PLACING LIVE ORDER FOR {symbol}...", level="TRADE", log_type="ORDER_SEND")
    log_msg(f"  Pattern    : {pattern.pattern_type} ({dir_str}) | Score: {pattern.score*100:.1f}%")
    log_msg(f"  Price      : {entry_price}")
    log_msg(f"  Lot Size   : {lot_size}")
    log_msg(f"  Stop Loss  : {sl_price} (Max Risk: {expected_loss_str})")
    log_msg(f"  TP1 Target : {tp1_price} (50% Partial + Move to BE)")
    log_msg(f"  TP2 Target : {tp2_price}")

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        err = mt5.last_error() if result is None else result.comment
        log_msg(f"  [ERROR] Order Failed: {err} (Retcode: {getattr(result, 'retcode', 'None')})", level="ERROR", log_type="ORDER_FAIL")
        return False

    log_msg(f"  [SUCCESS] ORDER EXECUTED! Ticket #{result.order} | Deal #{result.deal}\n", level="TRADE", log_type="ORDER_SUCCESS")

    # Cache Timeout
    pattern_len = pattern.d_idx - pattern.x_idx
    timeout_minutes = int(pattern_len * 3.0 * 15)
    timeout_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=timeout_minutes)
    ACTIVE_TRADE_TIMEOUTS[result.order] = timeout_time
    if getattr(result, "deal", None):
        ACTIVE_TRADE_TIMEOUTS[result.deal] = timeout_time

    # Record to MongoDB
    mongo_logger.record_trade_open({
        "ticket": result.order,
        "deal": result.deal,
        "symbol": symbol,
        "pattern": pattern.pattern_type,
        "direction": "BUY" if pattern.bull else "SELL",
        "lot_size": lot_size,
        "entry_price": entry_price,
        "sl_price": sl_price,
        "tp1_price": tp1_price,
        "tp2_price": tp2_price,
        "score": round(pattern.score, 4)
    })

    return True


def sync_closed_mongo_trades():
    """Polls MongoDB for open trades and verifies their closed status against MT5 history."""
    if not mongo_logger.connected or mongo_logger.db is None: return
    try:
        active_mongo = mongo_logger.db["trades"].find({"status": {"$in": ["OPEN", "BREAK_EVEN", "RISK_REDUCED", "PARTIAL_PROFIT"]}})
        
        from_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
        to_date = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        all_deals = mt5.history_deals_get(from_date, to_date)
        if not all_deals: return
        
        for t in active_mongo:
            ticket = t.get("ticket")
            if not ticket: continue
            
            # Check if position still exists in live MT5
            live_pos = mt5.positions_get(ticket=ticket)
            if live_pos and len(live_pos) > 0:
                continue  # Position is still active, do not mark as closed!
                
            # Position is fully closed, calculate final PnL from all OUT deals
            pos_deals = [d for d in all_deals if d.position_id == ticket and d.entry == mt5.DEAL_ENTRY_OUT]
            
            if pos_deals:
                total_pnl = sum(d.profit for d in pos_deals)
                status = "CLOSED" if total_pnl > 0 else "STOP_LOSS"
                if abs(total_pnl) < 1.0: status = "BREAK_EVEN_CLOSED"
                
                close_time_utc = datetime.datetime.now(datetime.timezone.utc)
                mongo_logger.record_trade_update(ticket, {"status": status, "pnl": total_pnl, "close_time": close_time_utc})
                log_msg(f">>> [DASHBOARD AUTO-SYNC] Updated Ticket #{ticket} -> {status} (Final PnL: ${total_pnl:.2f})")
    except Exception as e:
        pass


def manage_active_positions(active_symbols):
    """Monitors open positions, manages Partial Close, Break-Even, and Timeouts."""
    global ACTIVE_TRADE_TIMEOUTS, PARTIALLY_CLOSED_TICKETS
    positions = mt5.positions_get()
    if positions is None or len(positions) == 0:
        return

    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue

        sym = pos.symbol
        ticket = pos.ticket
        pos_id = getattr(pos, 'identifier', pos.ticket)  # Use persistent identifier for caches
        sym_info = mt5.symbol_info(sym)
        if sym_info is None:
            continue

        is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
        curr_price = sym_info.bid if is_buy else sym_info.ask
        open_price = pos.price_open
        curr_sl = pos.sl

        entry_to_sl = abs(open_price - curr_sl) if curr_sl > 0 else 0
        profit_dist = (curr_price - open_price) if is_buy else (open_price - curr_price)

        # Sync live floating PnL and current Lot Size to Dashboard
        mongo_logger.record_trade_update(ticket, {"pnl": pos.profit, "lot_size": pos.volume})

        # Stage 1: Move SL to Break-Even and Partial Close 50% when trade achieves 1.0R / TP1
        if entry_to_sl > 0 and profit_dist >= entry_to_sl:
            be_price = round(open_price + (sym_info.point * 2 if is_buy else -sym_info.point * 2), sym_info.digits)
            needs_sl_move = (curr_sl < open_price) if is_buy else (curr_sl > open_price)

            if needs_sl_move:
                log_msg(f"\n>>> [TP1 / BE TRIGGER] Ticket #{ticket} ({sym}) achieved 1.0R target!", level="TRADE", log_type="BREAK_EVEN")
                log_msg(f"  Trailing Stop Loss to Break-Even: {be_price}...")

                modify_request = {
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": ticket,
                    "symbol": sym,
                    "sl": be_price,
                    "tp": pos.tp,
                }
                res = mt5.order_send(modify_request)
                if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                    log_msg(f"  [OK] Stop Loss successfully updated to Break-Even for #{ticket}")
                    mongo_logger.record_trade_update(ticket, {"sl_price": be_price, "status": "BREAK_EVEN"})
            
            # Partial Close 50%
            if pos_id not in PARTIALLY_CLOSED_TICKETS:
                step = sym_info.volume_step if sym_info.volume_step > 0 else 0.01
                half_vol = math.floor((pos.volume / 2.0) / step) * step
                if half_vol >= sym_info.volume_min:
                    log_msg(f"  [PARTIAL CLOSE] Scaling out 50% ({half_vol} lots) for #{ticket}...", level="TRADE")
                    close_req = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": sym,
                        "volume": half_vol,
                        "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                        "position": ticket,
                        "price": sym_info.bid if is_buy else sym_info.ask,
                        "deviation": 20,
                        "magic": MAGIC_NUMBER,
                        "comment": "TP1_PARTIAL",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    p_res = mt5.order_send(close_req)
                    if p_res and p_res.retcode == mt5.TRADE_RETCODE_DONE:
                        log_msg(f"  [OK] Successfully closed 50% of #{ticket}")
                        PARTIALLY_CLOSED_TICKETS.add(pos_id)
                        mongo_logger.record_trade_update(ticket, {"status": "PARTIAL_PROFIT"})

        # Stage 2: Timeout Exit (Wait exactly 3x the pattern formation time)
        timeout_deadline = ACTIVE_TRADE_TIMEOUTS.get(pos_id) or ACTIVE_TRADE_TIMEOUTS.get(ticket)
        if timeout_deadline:
            if datetime.datetime.now(datetime.timezone.utc) > timeout_deadline:
                log_msg(f"\n>>> [TIMEOUT EXIT] Position #{ticket} (ID #{pos_id}, {sym}) exceeded 3x pattern length! Closing at market.", level="TRADE")
                close_req = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": sym,
                    "volume": pos.volume,
                    "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                    "position": ticket,
                    "price": sym_info.bid if is_buy else sym_info.ask,
                    "deviation": 20,
                    "magic": MAGIC_NUMBER,
                    "comment": "TIMEOUT",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                t_res = mt5.order_send(close_req)
                if t_res and t_res.retcode == mt5.TRADE_RETCODE_DONE:
                    ACTIVE_TRADE_TIMEOUTS.pop(pos_id, None)
                    ACTIVE_TRADE_TIMEOUTS.pop(ticket, None)
                    mongo_logger.record_trade_update(ticket, {"status": "TIMEOUT_CLOSED"})


# ==============================================================================
# MAIN TRADING ENGINE LOOP
# ==============================================================================
def run_live_bot(session_filter=SESSION_FILTER_ENABLED):
    if not connect_mt5():
        sys.exit(1)

    active_symbols = resolve_symbol_names(SYMBOLS)
    if not active_symbols:
        log_msg("[ERROR] No valid active symbols found to trade. Exiting.", level="ERROR")
        sys.exit(1)

    session_desc = "13:00 - 20:00 UTC (London/NY Overlap)" if session_filter else "All Sessions (24/5 Live Scanner)"
    
    iteration = 0
    traded_patterns_cache = set()
    global ACTIVE_TRADE_TIMEOUTS, PARTIALLY_CLOSED_TICKETS
    ACTIVE_TRADE_TIMEOUTS = {}
    PARTIALLY_CLOSED_TICKETS = set()
    
    log_msg("=" * 80)
    log_msg(">>> HARMONIC EA V3 ENGINE IS LIVE AND SCANNING...")
    log_msg(f"  Timeframe          : M15")
    log_msg(f"  H1 Filter          : EMA 50 / 200 Trend Alignment")
    log_msg(f"  Session Window     : {session_desc}")
    log_msg(f"  Patterns Enabled   : {', '.join(ENABLED_PATTERNS)}")
    log_msg(f"  Min Pattern Score  : {MIN_SCORE*100:.0f}%")
    log_msg(f"  Risk Engine        : Broker Native Profit Sizing (mt5.order_calc_profit)")
    log_msg(f"  Cloud Telemetry    : MongoDB Cloud Active (cluster0.tt1v1.mongodb.net)")
    log_msg(f"  Local Log File     : {LOG_FILE}")
    log_msg("=" * 80)

    iteration = 0
    traded_patterns_cache = set()  # Prevent duplicate re-entries on the same harmonic pattern swing

    while True:
        try:
            iteration += 1
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            hour_utc = now_utc.hour

            in_session = True
            if session_filter:
                in_session = (SESSION_START_HOUR_UTC <= hour_utc < SESSION_END_HOUR_UTC)

            acct = mt5.account_info()
            positions = mt5.positions_get()
            bot_positions = [p for p in positions if p.magic == MAGIC_NUMBER] if positions else []

            status_str = f"Equity: ${acct.equity:,.2f} | Balance: ${acct.balance:,.2f} | Open Positions: {len(bot_positions)}"
            if not in_session:
                status_str += " | [Outside Golden Session Window - Waiting]"
            else:
                status_str += " | [Active Scanning - Golden Window]"

            log_msg(status_str, level="INFO", log_type="HEARTBEAT")

            # Update live bot telemetry state in MongoDB
            mongo_logger.publish_bot_status({
                "balance": acct.balance,
                "equity": acct.equity,
                "margin_free": acct.margin_free,
                "open_positions": len(bot_positions),
                "in_session": in_session,
                "iteration": iteration,
                "is_online": True,
                "portfolio": "FOREX",
                "account": 474471944,
                "server": "Exness-MT5Trial15"
            })

            manage_active_positions(active_symbols)
            sync_closed_mongo_trades()

            if in_session:
                for sym in active_symbols:
                    sym_open = [p for p in bot_positions if p.symbol == sym]
                    if len(sym_open) >= MAX_CONCURRENT_POSITIONS:
                        continue

                    h1_bias = get_h1_trend_bias(sym)

                    df_m15 = fetch_rates_df(sym, TIMEFRAME_M15, n_bars=LOOKBACK_BARS)
                    if df_m15 is None or len(df_m15) < 60:
                        continue

                    # CRITICAL FIX: "Trade on Close Only" (Matches Backtest Engine exactly)
                    # The last row is the actively forming candle. We must drop it so the bot 
                    # only scans fully completed and closed 15-minute candles to avoid intrabar fakeouts.
                    df_m15 = df_m15.iloc[:-1].reset_index(drop=True)

                    highs = df_m15["high"].values
                    lows = df_m15["low"].values
                    closes = df_m15["close"].values
                    atr = compute_atr(highs, lows, closes, 14)
                    curr_atr = atr[-1]

                    sym_info = mt5.symbol_info(sym)
                    if sym_info is None:
                        continue

                    spread_price = sym_info.spread * sym_info.point

                    patterns = scan_harmonic_patterns(df_m15, symbol=sym)
                    for pat in patterns:
                        # 1. Unique Pattern Signature Check (Matches backtest 1-entry rule)
                        pat_signature = f"{sym}_{pat.pattern_type}_{pat.bull}_{pat.d_price:.5f}_{pat.x_price:.5f}"
                        if pat_signature in traded_patterns_cache:
                            continue

                        # 2. H1 Trend Gate
                        if pat.bull and h1_bias < 0:
                            continue
                        if not pat.bull and h1_bias > 0:
                            continue

                        # 3. Stop Floor
                        stop_dist = abs(pat.entry_price - pat.stop_price)
                        min_stop_atr = curr_atr * MIN_ATR_STOP_MULT
                        min_stop_spread = spread_price * MIN_STOP_TO_SPREAD_RATIO

                        if stop_dist < max(min_stop_atr, min_stop_spread):
                            continue

                        success = open_harmonic_trade(sym, pat, sym_info.bid, sym_info.ask)
                        if success:
                            traded_patterns_cache.add(pat_signature)
                            if len(traded_patterns_cache) > 200:
                                traded_patterns_cache.pop()
                        break

            # ==========================================
            # DYNAMIC HYPER-POLLING FOR ZERO-GAP ENTRY
            # ==========================================
            now = datetime.datetime.now(datetime.timezone.utc)
            seconds_to_15 = 900 - ((now.minute % 15) * 60 + now.second)
            
            # If we are within 5 seconds of the 15-minute candle close, poll every 100ms
            if seconds_to_15 <= 5 or seconds_to_15 == 900:
                time.sleep(0.1)
            else:
                time.sleep(POLL_INTERVAL_SECONDS)  # Normal 2s polling for active position trailing

        except KeyboardInterrupt:
            log_msg("\n>>> Bot shutdown requested by user. Exiting cleanly...")
            mongo_logger.publish_bot_status({"is_online": False, "portfolio": "FOREX"})
            mt5.shutdown()
            break
        except Exception as e:
            log_msg(f"[!] Exception in main loop: {e}", level="ERROR", log_type="EXCEPTION")
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Harmonic EA V3 Live Exness Bot")
    parser.add_argument("--all-sessions", action="store_true", help="Disable the 13:00-20:00 UTC session filter and scan 24/5")
    args = parser.parse_args()

    run_live_bot(session_filter=not args.all_sessions)
