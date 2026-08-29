"""
===================================================================================
HARMONIC EA V3 CHAMPION — STANDALONE BITCOIN (BTCUSDm) DEDICATED ENGINE
===================================================================================
Dedicated Account: #472637125 ($20,000 USD Wallet) | Server: Exness-MT5Trial16
Strategy: Institutional Harmonic Pattern Engine (Cypher, Gartley, Crab, Shark)
Timeframe: M15 Execution | H1 Trend Filter (EMA 50/200)
Risk Management: Exact USD Broker Sizing (1.5% Risk) | 1.0R Partial Scale + BE
Magic Number: 888444 (Isolated Dedicated Partition)
Telemetry: MongoDB Cloud Sync (cluster0.tt1v1.mongodb.net / harmonic_trading)
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
LOG_FILE = os.path.join(LOGS_DIR, "harmonic_btc_live.log")

# Setup Logging
logger = logging.getLogger("HarmonicBTCBot")
logger.setLevel(logging.INFO)
formatter = logging.Formatter("[%(asctime)s UTC] [BTC] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
logger.addHandler(fh)

from core.mongo_logger import mongo_logger
from core.config import HarmonicRatios, PATTERN_MAP, PATTERN_TARGETS, compute_target_price
from core.pattern_scanner import HarmonicPattern, validate_pattern

def log_msg(msg, level="INFO", log_type="SYSTEM", metadata=None):
    logger.info(msg)
    meta = metadata or {}
    meta["portfolio"] = "BTC"
    meta["account"] = 472637125
    mongo_logger.log(level, f"[BTC] {msg}", log_type=log_type, metadata=meta)

# ==============================================================================
# CONFIGURATION — DEDICATED BITCOIN WALLET
# ==============================================================================
# Dual Terminal Paths: checks BTC folder first, falls back to default MT5
EXNESS_BTC_TERMINAL_PATH = r"C:\Program Files\MetaTrader 5 EXNESS BTC\terminal64.exe"
EXNESS_DEFAULT_TERMINAL_PATH = r"C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe"

DEMO_LOGIN = 472637125
DEMO_SERVER = "Exness-MT5Trial16"

MAGIC_NUMBER = 888444
TRADE_COMMENT_PREFIX = "HBTCV3"

# Dedicated Bitcoin Universe
SYMBOLS = [
    "BTCUSDm",   # Bitcoin / USD Spot Crypto Engine
]

TIMEFRAME_M15 = mt5.TIMEFRAME_M15
TIMEFRAME_H1 = mt5.TIMEFRAME_H1
LOOKBACK_BARS = 350

ENABLED_PATTERNS = ["Shark", "Cypher", "Gartley"]
MIN_SCORE = 0.80
PIVOT_LENGTHS = [3, 5, 8]
RISK_PER_TRADE_PCT = 0.015        # 1.5% Risk per trade ($300 on $20,000 wallet)
MAX_CONCURRENT_POSITIONS = 2      # Max open trades on Bitcoin
MIN_ATR_STOP_MULT = 0.50          # Stop distance >= 0.50x ATR(14)
MIN_STOP_TO_SPREAD_RATIO = 3.5

SESSION_FILTER_ENABLED = True
SESSION_START_HOUR_UTC = 13
SESSION_END_HOUR_UTC = 20
POLL_INTERVAL_SECONDS = 2


# ==============================================================================
# MT5 CONNECTION & INITIALIZATION
# ==============================================================================
def connect_mt5():
    term_path = EXNESS_BTC_TERMINAL_PATH if os.path.exists(EXNESS_BTC_TERMINAL_PATH) else EXNESS_DEFAULT_TERMINAL_PATH
    log_msg(f"Initializing MetaTrader 5 for Bitcoin Dedicated Wallet (Path: {term_path})...")
    
    if os.path.exists(term_path):
        initialized = mt5.initialize(path=term_path)
    else:
        initialized = mt5.initialize()

    if not initialized:
        log_msg(f"[ERROR] MT5 Initialization failed: {mt5.last_error()}", level="ERROR")
        return False

    acc_info = mt5.account_info()
    if acc_info is None or acc_info.login != DEMO_LOGIN:
        log_msg(f"Logging in to Dedicated Account #{DEMO_LOGIN} on {DEMO_SERVER}...")
        authorized = mt5.login(login=DEMO_LOGIN, server=DEMO_SERVER)
        if not authorized:
            log_msg(f"[ERROR] MT5 Login failed for #{DEMO_LOGIN}: {mt5.last_error()}", level="ERROR")
            return False

    acc_info = mt5.account_info()
    log_msg(f"[SUCCESS] Connected to Account #{acc_info.login} ({acc_info.name})", level="INFO")
    log_msg(f"  Server   : {acc_info.server}")
    log_msg(f"  Balance  : ${acc_info.balance:.2f} {acc_info.currency}")
    log_msg(f"  Equity   : ${acc_info.equity:.2f} {acc_info.currency}")
    log_msg(f"  Leverage : 1:{acc_info.leverage}")
    return True


def resolve_symbol_names(symbols):
    available = [s.name for s in mt5.symbols_get()]
    resolved = []
    for sym in symbols:
        if sym in available:
            mt5.symbol_select(sym, True)
            resolved.append(sym)
        else:
            candidates = [s for s in available if sym.replace("m", "").replace("c", "") in s]
            if candidates:
                chosen = candidates[0]
                mt5.symbol_select(chosen, True)
                resolved.append(chosen)
                log_msg(f"Mapped {sym} -> {chosen}")
            else:
                log_msg(f"[WARN] Symbol {sym} not found in MT5 broker feed.", level="WARNING")
    return resolved


# ==============================================================================
# TECHNICAL INDICATORS & TREND GATES
# ==============================================================================
def calculate_atr(df, period=14):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    n = len(df)
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    return pd.Series(tr).rolling(window=period, min_periods=1).mean().values


def compute_h1_trend_bias(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME_H1, 0, 250)
    if rates is None or len(rates) < 200:
        return 0
    df = pd.DataFrame(rates)
    closes = df['close'].values
    ema50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values
    ema200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values
    last_close = closes[-1]
    last_50 = ema50[-1]
    last_200 = ema200[-1]
    if last_close > last_50 and last_50 >= last_200:
        return 1
    elif last_close < last_50 and last_50 <= last_200:
        return -1
    return 0


def detect_pivots(highs, lows, R):
    n = len(highs)
    pivot_highs = []
    pivot_lows = []
    for p in range(R, n - R):
        is_high = True
        for j in range(1, R + 1):
            if highs[p - j] > highs[p] or highs[p + j] > highs[p]:
                is_high = False
                break
        if is_high:
            pivot_highs.append((p, highs[p]))

        is_low = True
        for j in range(1, R + 1):
            if lows[p - j] < lows[p] or lows[p + j] < lows[p]:
                is_low = False
                break
        if is_low:
            pivot_lows.append((p, lows[p]))
    return pivot_highs, pivot_lows


# ==============================================================================
# PATTERN SCANNING ENGINE (M15 BAR CLOSE ONLY)
# ==============================================================================
class ConfigProxy:
    def __init__(self):
        self.fib_error_pct = 15.0
        self.min_score = MIN_SCORE
        self.enabled_patterns = ENABLED_PATTERNS


def scan_live_patterns(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME_M15, 0, LOOKBACK_BARS)
    if rates is None or len(rates) < 50:
        return []

    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    highs = df['high'].values
    lows = df['low'].values
    
    atr_vals = calculate_atr(df, 14)
    current_atr = atr_vals[-2] if len(atr_vals) >= 2 else atr_vals[-1]

    h1_bias = compute_h1_trend_bias(symbol)
    cfg = ConfigProxy()

    all_piv_highs = []
    all_piv_lows = []
    for R in PIVOT_LENGTHS:
        ph, pl = detect_pivots(highs, lows, R)
        all_piv_highs.extend(ph)
        all_piv_lows.extend(pl)

    all_piv_highs = sorted(list(set(all_piv_highs)), key=lambda x: x[0])
    all_piv_lows = sorted(list(set(all_piv_lows)), key=lambda x: x[0])

    eval_bar_idx = len(df) - 2
    matched_patterns = []

    for R in PIVOT_LENGTHS:
        d_cand_idx = eval_bar_idx - R
        if d_cand_idx < 0: continue

        is_d_low = True
        for j in range(1, R + 1):
            if lows[d_cand_idx - j] < lows[d_cand_idx] or lows[d_cand_idx + j] < lows[d_cand_idx]:
                is_d_low = False
                break

        is_d_high = True
        for j in range(1, R + 1):
            if highs[d_cand_idx - j] > highs[d_cand_idx] or highs[d_cand_idx + j] > highs[d_cand_idx]:
                is_d_high = False
                break

        if is_d_low:
            dP = lows[d_cand_idx]
            dI = d_cand_idx
            bull = True
            if h1_bias < 0: continue

            c_cands = [p for p in all_piv_highs if p[0] < dI]
            b_cands = [p for p in all_piv_lows if p[0] < dI]
            a_cands = [p for p in all_piv_highs if p[0] < dI]
            x_cands = [p for p in all_piv_lows if p[0] < dI]

            for cI, cP in c_cands[-4:]:
                if cP <= dP: continue
                for bI, bP in b_cands[-4:]:
                    if bI >= cI or bP >= cP: continue
                    for aI, aP in a_cands[-4:]:
                        if aI >= bI or aP <= bP: continue
                        for xI, xP in x_cands[-4:]:
                            if xI >= aI or xP >= aP: continue
                            for pat_name in ENABLED_PATTERNS:
                                r_def = PATTERN_MAP.get(pat_name)
                                if not r_def: continue
                                pat = validate_pattern(xP, aP, bP, cP, dP, xI, aI, bI, cI, dI, r_def, cfg, bull)
                                if pat and pat.score >= MIN_SCORE:
                                    pat.atr = current_atr
                                    matched_patterns.append(pat)

        if is_d_high:
            dP = highs[d_cand_idx]
            dI = d_cand_idx
            bull = False
            if h1_bias > 0: continue

            c_cands = [p for p in all_piv_lows if p[0] < dI]
            b_cands = [p for p in all_piv_highs if p[0] < dI]
            a_cands = [p for p in all_piv_lows if p[0] < dI]
            x_cands = [p for p in all_piv_highs if p[0] < dI]

            for cI, cP in c_cands[-4:]:
                if cP >= dP: continue
                for bI, bP in b_cands[-4:]:
                    if bI >= cI or bP <= cP: continue
                    for aI, aP in a_cands[-4:]:
                        if aI >= bI or aP >= bP: continue
                        for xI, xP in x_cands[-4:]:
                            if xI >= aI or xP <= aP: continue
                            for pat_name in ENABLED_PATTERNS:
                                r_def = PATTERN_MAP.get(pat_name)
                                if not r_def: continue
                                pat = validate_pattern(xP, aP, bP, cP, dP, xI, aI, bI, cI, dI, r_def, cfg, bull)
                                if pat and pat.score >= MIN_SCORE:
                                    pat.atr = current_atr
                                    matched_patterns.append(pat)

    if matched_patterns:
        matched_patterns.sort(key=lambda x: x.score, reverse=True)
        best = matched_patterns[0]
        # Publish pattern detection to MongoDB
        mongo_logger.record_pattern({
            "symbol": symbol,
            "pattern": best.pattern_type,
            "bull": best.bull,
            "score": round(best.score, 4),
            "entry_price": best.entry_price,
            "stop_price": best.stop_price,
            "t1_price": best.t1_price,
            "t2_price": best.t2_price,
            "portfolio": "BTC"
        })
        return [best]

    return []


# ==============================================================================
# POSITION SIZING & RISK ARCHITECTURE
# ==============================================================================
def calculate_lot_size(symbol, bull, entry_price, sl_price):
    acc_info = mt5.account_info()
    sym_info = mt5.symbol_info(symbol)
    if not acc_info or not sym_info:
        return 0.01

    equity = acc_info.equity
    risk_amount = equity * RISK_PER_TRADE_PCT

    stop_dist = abs(entry_price - sl_price)
    if stop_dist <= 0:
        return sym_info.volume_min

    order_type = mt5.ORDER_TYPE_BUY if bull else mt5.ORDER_TYPE_SELL
    loss_1_lot = mt5.order_calc_profit(order_type, symbol, 1.0, entry_price, sl_price)
    
    if loss_1_lot is not None and abs(loss_1_lot) > 0:
        loss_per_lot = abs(loss_1_lot)
        calc_lots = risk_amount / loss_per_lot
    else:
        tick_val = sym_info.trade_tick_value or 1.0
        tick_size = sym_info.trade_tick_size or sym_info.point
        loss_per_lot = (stop_dist / tick_size) * tick_val
        calc_lots = risk_amount / loss_per_lot if loss_per_lot > 0 else sym_info.volume_min

    step = sym_info.volume_step or 0.01
    lots = math.floor(calc_lots / step) * step
    lots = max(sym_info.volume_min, min(lots, sym_info.volume_max))
    return round(lots, 2)


# ==============================================================================
# TRADE EXECUTION & MANAGEMENT
# ==============================================================================
ACTIVE_TRADE_TIMEOUTS = {}
PARTIALLY_CLOSED_TICKETS = set()

def open_harmonic_trade(symbol, pattern, current_bid, current_ask):
    sym_info = mt5.symbol_info(symbol)
    if not sym_info: return False

    order_type = mt5.ORDER_TYPE_BUY if pattern.bull else mt5.ORDER_TYPE_SELL
    entry_price = current_ask if pattern.bull else current_bid

    t1_dist = abs(pattern.t1_price - pattern.entry_price)
    t2_dist = abs(pattern.t2_price - pattern.entry_price)
    sl_dist = abs(pattern.stop_price - pattern.entry_price)

    if pattern.bull:
        sl_price = round(entry_price - sl_dist, sym_info.digits)
        tp1_price = round(entry_price + t1_dist, sym_info.digits)
        tp2_price = round(entry_price + t2_dist, sym_info.digits)
    else:
        sl_price = round(entry_price + sl_dist, sym_info.digits)
        tp1_price = round(entry_price - t1_dist, sym_info.digits)
        tp2_price = round(entry_price - t2_dist, sym_info.digits)

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
        "deviation": 30,
        "magic": MAGIC_NUMBER,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    dir_str = "BULLISH LONG [BUY]" if pattern.bull else "BEARISH SHORT [SELL]"
    expected_loss = mt5.order_calc_profit(order_type, symbol, lot_size, entry_price, sl_price)
    expected_loss_str = f"${abs(expected_loss):.2f}" if expected_loss else "N/A"

    log_msg(f"\n>>> [BTC] PLACING LIVE ORDER FOR {symbol}...", level="TRADE", log_type="ORDER_SEND")
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

    log_msg(f"  [SUCCESS] BTC ORDER EXECUTED! Ticket #{result.order} | Deal #{result.deal}\n", level="TRADE", log_type="ORDER_SUCCESS")

    # Cache Timeout with dual indexing
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
        "score": round(pattern.score, 4),
        "portfolio": "BTC",
        "account": DEMO_LOGIN
    })

    return True


def sync_closed_mongo_trades():
    """Polls MongoDB for open BTC trades and syncs closure status against MT5 history."""
    if not mongo_logger.connected or mongo_logger.db is None: return
    try:
        active_mongo = mongo_logger.db["trades"].find({
            "portfolio": "BTC",
            "status": {"$in": ["OPEN", "BREAK_EVEN", "RISK_REDUCED", "PARTIAL_PROFIT"]}
        })
        
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
                continue
                
            pos_deals = [d for d in all_deals if d.position_id == ticket and d.entry == mt5.DEAL_ENTRY_OUT]
            if pos_deals:
                total_pnl = sum(d.profit for d in pos_deals)
                status = "CLOSED" if total_pnl > 0 else "STOP_LOSS"
                if abs(total_pnl) < 1.0: status = "BREAK_EVEN_CLOSED"
                
                close_time_utc = datetime.datetime.now(datetime.timezone.utc)
                mongo_logger.record_trade_update(ticket, {"status": status, "pnl": total_pnl, "close_time": close_time_utc})
                log_msg(f">>> [BTC AUTO-SYNC] Updated Ticket #{ticket} -> {status} (Final PnL: ${total_pnl:.2f})")
    except Exception:
        pass


def manage_active_positions(active_symbols):
    global ACTIVE_TRADE_TIMEOUTS, PARTIALLY_CLOSED_TICKETS
    positions = mt5.positions_get()
    if positions is None: return

    for pos in positions:
        if pos.magic != MAGIC_NUMBER:
            continue
        if pos.symbol not in active_symbols:
            continue

        ticket = pos.ticket
        pos_id = getattr(pos, 'identifier', pos.ticket)
        sym = pos.symbol
        sym_info = mt5.symbol_info(sym)
        if not sym_info: continue

        is_buy = (pos.type == mt5.ORDER_TYPE_BUY)
        current_price = sym_info.bid if is_buy else sym_info.ask
        open_price = pos.price_open
        sl = pos.sl
        tp = pos.tp

        # Update Live PnL in MongoDB
        mongo_logger.record_trade_update(ticket, {"pnl": round(pos.profit, 2)})

        # Stage 1: 50% Partial Close at 1.0R (TP1)
        if pos.comment and "HEAV3" in pos.comment:
            tp1_target = None
            if is_buy and tp > open_price and sl < open_price:
                r_dist = open_price - sl
                tp1_target = open_price + r_dist
            elif not is_buy and tp < open_price and sl > open_price:
                r_dist = sl - open_price
                tp1_target = open_price - r_dist

            if tp1_target is not None:
                reached_tp1 = (current_price >= tp1_target) if is_buy else (current_price <= tp1_target)
                if reached_tp1 and sl != open_price and pos_id not in PARTIALLY_CLOSED_TICKETS:
                    be_price = round(open_price + (sym_info.point * 2 if is_buy else -sym_info.point * 2), sym_info.digits)
                    log_msg(f"\n>>> [1.0R TARGET HIT] Position #{ticket} ({sym}) reached TP1!", level="TRADE")
                    log_msg(f"  Trailing Stop Loss to Break-Even: {be_price}...")
                    mod_req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "symbol": sym,
                        "position": ticket,
                        "sl": be_price,
                        "tp": tp,
                        "magic": MAGIC_NUMBER,
                    }
                    mt5.order_send(mod_req)
                    mongo_logger.record_trade_update(ticket, {"sl_price": be_price, "status": "BREAK_EVEN"})

                    step = sym_info.volume_step or 0.01
                    half_vol = math.floor((pos.volume * 0.5) / step) * step
                    half_vol = max(sym_info.volume_min, round(half_vol, 2))
                    if half_vol < pos.volume:
                        log_msg(f"  [PARTIAL CLOSE] Scaling out 50% ({half_vol} lots) for #{ticket}...", level="TRADE")
                        close_req = {
                            "action": mt5.TRADE_ACTION_DEAL,
                            "symbol": sym,
                            "volume": half_vol,
                            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                            "position": ticket,
                            "price": sym_info.bid if is_buy else sym_info.ask,
                            "deviation": 30,
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

        # Stage 2: Timeout Exit (3x Pattern Length)
        timeout_deadline = ACTIVE_TRADE_TIMEOUTS.get(pos_id) or ACTIVE_TRADE_TIMEOUTS.get(ticket)
        if timeout_deadline and datetime.datetime.now(datetime.timezone.utc) > timeout_deadline:
            log_msg(f"\n>>> [TIMEOUT EXIT] Position #{ticket} (ID #{pos_id}, {sym}) exceeded 3x pattern length! Closing at market.", level="TRADE")
            close_req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": sym,
                "volume": pos.volume,
                "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
                "position": ticket,
                "price": sym_info.bid if is_buy else sym_info.ask,
                "deviation": 30,
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
def run_live_btc_bot(session_filter=SESSION_FILTER_ENABLED):
    if not connect_mt5():
        sys.exit(1)

    active_symbols = resolve_symbol_names(SYMBOLS)
    if not active_symbols:
        log_msg("[ERROR] No valid active BTC symbols found to trade. Exiting.", level="ERROR")
        sys.exit(1)

    log_msg("================================================================================")
    log_msg("  HARMONIC EA V3 — BITCOIN DEDICATED ENGINE ACTIVE")
    log_msg(f"  Account     : #{DEMO_LOGIN} ($20,000 Wallet)")
    log_msg(f"  Symbol      : {active_symbols}")
    log_msg(f"  Timeframe   : M15 (Confirmation at Candle Close)")
    log_msg(f"  Session     : 13:00 - 20:00 UTC (7 Days a Week)")
    log_msg(f"  Risk Profile: {RISK_PER_TRADE_PCT*100:.1f}% per trade | Min Score: {MIN_SCORE*100:.0f}%")
    log_msg("================================================================================")

    last_eval_minute = -1
    last_sync_time = 0
    consecutive_errors = 0

    while True:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            in_session = (SESSION_START_HOUR_UTC <= now_utc.hour < SESSION_END_HOUR_UTC) if session_filter else True

            # Publish Bot Telemetry Heartbeat to MongoDB
            acc = mt5.account_info()
            if acc:
                open_pos_count = len([p for p in (mt5.positions_get() or []) if p.magic == MAGIC_NUMBER])
                mongo_logger.publish_bot_status({
                    "is_online": True,
                    "portfolio": "BTC",
                    "account": DEMO_LOGIN,
                    "server": DEMO_SERVER,
                    "balance": acc.balance,
                    "equity": acc.equity,
                    "margin_free": acc.margin_free,
                    "open_positions": open_pos_count,
                    "in_session": in_session,
                    "timestamp": now_utc
                })

            # Sync closed trades every 10 seconds
            if time.time() - last_sync_time > 10:
                sync_closed_mongo_trades()
                last_sync_time = time.time()

            # Manage active trailing stops & timeouts
            manage_active_positions(active_symbols)

            # Candle-close detection
            minute_mod = now_utc.minute % 15
            sec = now_utc.second

            if in_session:
                if minute_mod == 0 and sec < 20 and last_eval_minute != now_utc.minute:
                    last_eval_minute = now_utc.minute
                    log_msg(f"\n[M15 CANDLE CLOSE] [{now_utc.strftime('%H:%M:%S UTC')}] Scanning BTC price geometry...")

                    for sym in active_symbols:
                        patterns = scan_live_patterns(sym)
                        if patterns:
                            best_pat = patterns[0]
                            tick = mt5.symbol_info_tick(sym)
                            if tick:
                                open_harmonic_trade(sym, best_pat, tick.bid, tick.ask)

            consecutive_errors = 0

            # Dynamic hyper-polling at candle close boundary
            if minute_mod == 14 and sec >= 55:
                time.sleep(0.1)
            elif minute_mod == 0 and sec < 5:
                time.sleep(0.1)
            else:
                time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            log_msg("\n[SHUTDOWN] Bot stopped manually by user.")
            break
        except Exception as e:
            consecutive_errors += 1
            log_msg(f"[RUNTIME ERROR] {e}", level="ERROR")
            if consecutive_errors > 5:
                connect_mt5()
                consecutive_errors = 0
            time.sleep(5)

    mt5.shutdown()


if __name__ == "__main__":
    run_live_btc_bot()
