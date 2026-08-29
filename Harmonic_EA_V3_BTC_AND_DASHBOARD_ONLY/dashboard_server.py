"""
===================================================================================
HARMONIC EA V3 — REAL-TIME MONGODB LIVE WEB DASHBOARD SERVER
===================================================================================
Backend: FastAPI / Uvicorn
Database: MongoDB Atlas (cluster0.tt1v1.mongodb.net / harmonic_trading)
URL: http://localhost:5000
===================================================================================
"""

import os
import sys
import datetime
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import pymongo
from bson import json_util
import json

MONGO_URI = "mongodb+srv://student:student@cluster0.tt1v1.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "harmonic_trading"

app = FastAPI(title="Harmonic EA V3 Live Command Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to MongoDB
client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client[DB_NAME]

def parse_json(data):
    return json.loads(json_util.dumps(data))


@app.get("/api/status")
def get_status(portfolio: str = "FOREX"):
    try:
        if portfolio == "ALL":
            state_forex = db["bot_state"].find_one({"state_id": "current_live_state_forex"}, {"_id": 0})
            state_btc = db["bot_state"].find_one({"state_id": "current_live_state_btc"}, {"_id": 0})
            
            if not state_forex:
                state_forex = db["bot_state"].find_one({"state_id": "current_live_state"}, {"_id": 0})
                
            f_online = False
            b_online = False
            
            now = datetime.datetime.now(datetime.timezone.utc)
            if state_forex and state_forex.get("last_heartbeat"):
                lh = state_forex["last_heartbeat"]
                if (now - lh.replace(tzinfo=datetime.timezone.utc if lh.tzinfo is None else lh.tzinfo)).total_seconds() <= 45:
                    f_online = state_forex.get("is_online", False)
            if state_btc and state_btc.get("last_heartbeat"):
                lh = state_btc["last_heartbeat"]
                if (now - lh.replace(tzinfo=datetime.timezone.utc if lh.tzinfo is None else lh.tzinfo)).total_seconds() <= 45:
                    b_online = state_btc.get("is_online", False)
                    
            combined = {
                "is_online": f_online or b_online,
                "forex_online": f_online,
                "btc_online": b_online,
                "balance": (state_forex.get("balance", 500.0) if state_forex else 500.0) + (state_btc.get("balance", 20000.0) if state_btc else 20000.0),
                "equity": (state_forex.get("equity", 500.0) if state_forex else 500.0) + (state_btc.get("equity", 20000.0) if state_btc else 20000.0),
                "margin_free": (state_forex.get("margin_free", 500.0) if state_forex else 500.0) + (state_btc.get("margin_free", 20000.0) if state_btc else 20000.0),
                "open_positions": (state_forex.get("open_positions", 0) if state_forex else 0) + (state_btc.get("open_positions", 0) if state_btc else 0),
                "account_login": "Combined Accounts",
                "account_server": "Exness-MT5Trial15 & 16",
                "in_session": f_online or b_online,
                "last_heartbeat": now
            }
            return parse_json(combined)
            
        else:
            state_id = f"current_live_state_{portfolio.lower()}"
            state = db["bot_state"].find_one({"state_id": state_id}, {"_id": 0})
            if not state and portfolio.upper() == "FOREX":
                state = db["bot_state"].find_one({"state_id": "current_live_state"}, {"_id": 0})
                
            if not state:
                default_balance = 500.0 if portfolio == "FOREX" else 20000.0
                state = {
                    "is_online": False,
                    "balance": default_balance,
                    "equity": default_balance,
                    "margin_free": default_balance,
                    "open_positions": 0,
                    "account_login": 474471944 if portfolio == "FOREX" else 472637125,
                    "account_server": "Exness-MT5Trial15" if portfolio == "FOREX" else "Exness-MT5Trial16",
                    "in_session": False,
                    "last_heartbeat": None
                }
            
            if state.get("last_heartbeat"):
                last_hb = state["last_heartbeat"]
                if isinstance(last_hb, datetime.datetime):
                    now = datetime.datetime.now(datetime.timezone.utc)
                    if (now - last_hb.replace(tzinfo=datetime.timezone.utc if last_hb.tzinfo is None else last_hb.tzinfo)).total_seconds() > 45:
                        state["is_online"] = False
                        
            return parse_json(state)
    except Exception as e:
        return {"error": str(e), "is_online": False}


@app.get("/api/logs")
def get_logs(portfolio: str = "ALL", limit: int = 150, level: Optional[str] = None, search: Optional[str] = None):
    try:
        one_hour_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        query = {"timestamp": {"$gte": one_hour_ago}}
        
        if level and level != "ALL":
            query["level"] = level.upper()
            
        if portfolio.upper() == "BTC":
            query["message"] = {"$regex": r"^\[BTC\]", "$options": "i"}
        elif portfolio.upper() == "FOREX":
            query["message"] = {"$regex": r"^(?!\[BTC\])", "$options": "i"}
            
        if search:
            query["message"] = {"$regex": search, "$options": "i"}
            
        logs_cursor = db["logs"].find(query).sort("timestamp", -1).limit(limit)
        logs_list = list(logs_cursor)
        logs_list.reverse()
        return parse_json(logs_list)
    except Exception as e:
        return {"error": str(e), "logs": []}


@app.get("/api/trades")
def get_trades(portfolio: str = "ALL", limit: int = 100):
    try:
        query = {}
        if portfolio.upper() == "BTC":
            query["portfolio"] = "BTC"
        elif portfolio.upper() == "FOREX":
            query = {"$or": [{"portfolio": "FOREX"}, {"portfolio": {"$exists": False}}]}
            
        trades_cursor = db["trades"].find(query).sort("open_time", -1).limit(limit)
        trades_list = list(trades_cursor)
        return parse_json(trades_list)
    except Exception as e:
        return {"error": str(e), "trades": []}


@app.get("/api/patterns")
def get_patterns(portfolio: str = "ALL", limit: int = 20):
    try:
        query = {}
        if portfolio.upper() == "BTC":
            query["portfolio"] = "BTC"
        elif portfolio.upper() == "FOREX":
            query = {"$or": [{"portfolio": "FOREX"}, {"portfolio": {"$exists": False}}]}
            
        patterns_cursor = db["patterns"].find(query).sort("timestamp", -1).limit(limit)
        patterns_list = list(patterns_cursor)
        return parse_json(patterns_list)
    except Exception as e:
        return {"error": str(e), "patterns": []}


@app.get("/api/metrics")
def get_metrics(portfolio: str = "ALL"):
    try:
        query = {}
        if portfolio.upper() == "BTC":
            query["portfolio"] = "BTC"
        elif portfolio.upper() == "FOREX":
            query = {"$or": [{"portfolio": "FOREX"}, {"portfolio": {"$exists": False}}]}
            
        trades = list(db["trades"].find(query))
        total_trades = len(trades)
        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        losses = sum(1 for t in trades if t.get("pnl", 0) < 0)
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        
        return {
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2)
        }
    except Exception as e:
        return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}


# ==============================================================================
# EMBEDDED REAL-TIME WEB DASHBOARD (HTML5 + CSS3 + JS)
# ==============================================================================
HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Harmonic EA V3 — Live Mission Control</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-base: #070B12;
            --bg-card: rgba(15, 23, 42, 0.75);
            --bg-card-hover: rgba(30, 41, 59, 0.85);
            --border-glow: rgba(99, 102, 241, 0.25);
            --border-subtle: rgba(255, 255, 255, 0.08);
            --primary: #6366F1;
            --primary-glow: rgba(99, 102, 241, 0.4);
            --success: #10B981;
            --success-glow: rgba(16, 185, 129, 0.3);
            --danger: #F43F5E;
            --warning: #F59E0B;
            --cyan: #06B6D4;
            --text-main: #F8FAFC;
            --text-muted: #94A3B8;
            --font-main: 'Outfit', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            background-color: var(--bg-base);
            background-image: 
                radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.08) 0px, transparent 50%);
            color: var(--text-main);
            font-family: var(--font-main);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1440px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* Top Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 18px 24px;
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glow);
            border-radius: 16px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-icon {
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, var(--primary), var(--cyan));
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 0 20px var(--primary-glow);
        }

        .brand-title h1 {
            font-size: 20px;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(to right, #FFFFFF, #CBD5E1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .brand-title p {
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 400;
        }

        .header-actions {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .status-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 7px 16px;
            border-radius: 999px;
            font-size: 13px;
            font-weight: 600;
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: var(--success);
        }

        .status-pill.offline {
            background: rgba(244, 63, 94, 0.12);
            border-color: rgba(244, 63, 94, 0.3);
            color: var(--danger);
        }

        .pulse-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 10px var(--success);
            animation: pulse 2s infinite;
        }

        .status-pill.offline .pulse-dot {
            background: var(--danger);
            box-shadow: 0 0 10px var(--danger);
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.3); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }

        /* Metrics Top Banner Grid */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 16px;
        }

        .card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-subtle);
            border-radius: 16px;
            padding: 20px;
            position: relative;
            overflow: hidden;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .card:hover {
            border-color: var(--border-glow);
            background: var(--bg-card-hover);
            transform: translateY(-2px);
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.4);
        }

        .card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 3px;
            background: linear-gradient(90deg, var(--primary), var(--cyan));
            opacity: 0;
            transition: opacity 0.3s ease;
        }

        .card:hover::before { opacity: 1; }

        .card-label {
            font-size: 12px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-muted);
            margin-bottom: 8px;
        }

        .card-value {
            font-size: 26px;
            font-weight: 700;
            letter-spacing: -0.5px;
            color: #FFFFFF;
            font-family: var(--font-mono);
        }

        .card-sub {
            font-size: 11px;
            color: var(--text-muted);
            margin-top: 6px;
        }

        /* Main Workspace: 2-Column Split */
        .main-layout {
            display: grid;
            grid-template-columns: 1.4fr 1.6fr;
            gap: 20px;
        }

        .filter-toolbar {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }

        .filter-row-1 {
            display: flex;
            gap: 6px;
            align-items: center;
        }

        .filter-row-2 {
            display: flex;
            gap: 6px;
            align-items: center;
        }

        .date-select-dropdown {
            font-size: 11px;
            padding: 5px 8px;
            cursor: pointer;
            min-width: 140px;
        }

        .calendar-btn {
            padding: 5px 10px;
        }

        @media (max-width: 1024px) {
            .main-layout { grid-template-columns: 1fr; }
        }

        /* Mobile Phone Optimization (iPhone / Android) */
        @media (max-width: 768px) {
            body { padding: 8px; }
            .container { gap: 12px; }
            header {
                flex-direction: column;
                align-items: flex-start;
                gap: 12px;
                padding: 12px 14px;
            }
            .header-actions {
                width: 100%;
                justify-content: space-between;
            }
            .brand-title h1 { font-size: 16px; }
            .brand-title p { font-size: 11px; }
            
            .metrics-grid {
                grid-template-columns: repeat(2, 1fr);
                gap: 8px;
            }
            .metrics-grid .card:last-child {
                grid-column: span 2;
            }
            .card { padding: 12px; border-radius: 12px; }
            .card-label { font-size: 10px; margin-bottom: 4px; }
            .card-value { font-size: 18px; }
            .card-sub { font-size: 10px; margin-top: 4px; }
            
            .main-layout { 
                display: flex;
                flex-direction: column-reverse; /* Puts Active Trades on top so you see trades first on phone! */
                gap: 14px; 
            }
            
            .side-panels { gap: 14px; }
            .panel { padding: 12px; border-radius: 14px; }
            
            .panel-header {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }
            
            .filter-toolbar {
                width: 100%;
                flex-direction: column;
                gap: 8px;
            }
            .filter-row-1 {
                width: 100%;
            }
            .filter-row-1 .filter-btn {
                flex: 1;
                text-align: center;
                padding: 8px 4px;
                font-size: 12px;
            }
            .filter-row-2 {
                width: 100%;
            }
            .filter-row-2 .date-select-dropdown {
                flex: 1;
                padding: 8px 10px;
                font-size: 12px;
            }
            .filter-row-2 .calendar-btn {
                padding: 8px 12px;
                font-size: 12px;
            }
            
            .table-wrap { 
                max-height: 380px; 
                -webkit-overflow-scrolling: touch; 
                border-radius: 8px;
            }
            
            table { 
                min-width: 620px; 
                font-size: 11px;
            }
            th, td {
                padding: 8px 8px;
            }
            
            .terminal-panel { border-radius: 14px; }
            .terminal-header { padding: 10px 14px; flex-direction: column; align-items: flex-start; gap: 8px; }
            .terminal-controls { width: 100%; }
            .ctrl-select, .ctrl-input { width: 100%; }
            .terminal-body { height: 240px; padding: 12px; font-size: 11px; }
        }

        /* Live Terminal Box */
        .terminal-panel {
            background: rgba(10, 15, 29, 0.95);
            border: 1px solid var(--border-glow);
            border-radius: 16px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6);
        }

        .terminal-header {
            background: rgba(15, 23, 42, 0.9);
            padding: 12px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-subtle);
        }

        .terminal-title {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 13px;
            font-weight: 600;
            color: #E2E8F0;
        }

        .terminal-controls {
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .ctrl-select, .ctrl-input {
            background: rgba(2, 6, 23, 0.7);
            border: 1px solid var(--border-subtle);
            color: var(--text-main);
            padding: 5px 10px;
            border-radius: 8px;
            font-size: 12px;
            font-family: var(--font-main);
            outline: none;
        }

        .ctrl-select:focus, .ctrl-input:focus {
            border-color: var(--primary);
        }

        .filter-btn {
            background: rgba(2, 6, 23, 0.7);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 11px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .filter-btn:hover {
            color: var(--text-main);
            border-color: var(--primary);
        }

        .filter-btn.active {
            background: var(--primary);
            color: #FFFFFF;
            border-color: var(--primary);
            box-shadow: 0 0 10px var(--primary-glow);
        }

        .terminal-body {
            height: 480px;
            overflow-y: auto;
            padding: 16px;
            font-family: var(--font-mono);
            font-size: 12px;
            line-height: 1.6;
            color: #CBD5E1;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .terminal-body::-webkit-scrollbar { width: 6px; }
        .terminal-body::-webkit-scrollbar-thumb { background: rgba(255, 255, 255, 0.15); border-radius: 4px; }

        .log-row {
            display: flex;
            gap: 8px;
            word-break: break-all;
        }

        .log-time { color: #64748B; min-width: 75px; }
        .log-lvl { font-weight: 600; min-width: 55px; }
        .log-lvl.INFO { color: #38BDF8; }
        .log-lvl.TRADE { color: #34D399; }
        .log-lvl.WARNING { color: #FBBF24; }
        .log-lvl.ERROR { color: #F87171; }
        .log-msg { color: #E2E8F0; flex: 1; }

        /* Right Column Panels */
        .side-panels {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* Trades Table */
        .panel {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-subtle);
            border-radius: 16px;
            padding: 18px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .panel-title {
            font-size: 14px;
            font-weight: 700;
            color: #FFFFFF;
            letter-spacing: -0.2px;
        }

        .table-wrap {
            max-height: 230px;
            overflow-y: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }

        th {
            text-align: left;
            padding: 8px 10px;
            color: var(--text-muted);
            font-weight: 500;
            border-bottom: 1px solid var(--border-subtle);
        }

        td {
            padding: 10px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            font-family: var(--font-mono);
        }

        .tag {
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
        }

        .tag.BUY { background: rgba(16, 185, 129, 0.15); color: var(--success); border: 1px solid rgba(16, 185, 129, 0.3); }
        .tag.SELL { background: rgba(244, 63, 94, 0.15); color: var(--danger); border: 1px solid rgba(244, 63, 94, 0.3); }

        /* Patterns Feed */
        .pattern-card {
            background: rgba(2, 6, 23, 0.6);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 12px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            transition: all 0.2s;
        }

        .pattern-card:hover { border-color: var(--primary); }

        .btn {
            background: var(--primary);
            color: #FFF;
            border: none;
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn:hover { background: #4F46E5; box-shadow: 0 0 14px var(--primary-glow); }

        /* Portfolio Switcher Styles */
        .portfolio-switcher-bar {
            display: flex;
            background: rgba(15, 23, 42, 0.4);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 4px;
            gap: 4px;
            margin-top: -10px;
            margin-bottom: 15px;
        }

        .portfolio-btn {
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 10px 16px;
            border-radius: 10px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease-in-out;
        }

        .portfolio-btn:hover {
            color: var(--text-main);
            background: rgba(255, 255, 255, 0.05);
        }

        .portfolio-btn.active {
            background: var(--primary);
            color: #FFFFFF;
            box-shadow: 0 4px 14px var(--primary-glow);
        }

        .portfolio-btn .btn-icon {
            font-size: 14px;
        }

        @media (max-width: 768px) {
            .portfolio-switcher-bar {
                flex-direction: column;
                padding: 6px;
                margin-top: 0;
            }
            .portfolio-btn {
                padding: 12px;
                font-size: 12px;
                justify-content: flex-start;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Top Header -->
        <header>
            <div class="brand">
                <div class="brand-icon">⚡</div>
                <div class="brand-title">
                    <h1>HARMONIC EA V3 — MISSION CONTROL</h1>
                    <p>Live Exness MT5 Engine • Connected to MongoDB Atlas Cloud</p>
                </div>
            </div>
            <div class="header-actions">
                <div id="statusPill" class="status-pill">
                    <span class="pulse-dot"></span>
                    <span id="statusText">CONNECTING...</span>
                </div>
                <button class="btn" onclick="fetchData()">Refresh</button>
            </div>
        </header>

        <!-- Portfolio Switcher Toolbar -->
        <div class="portfolio-switcher-bar">
            <button id="portForex" class="portfolio-btn active" onclick="switchPortfolio('FOREX')">
                <span class="btn-icon">💼</span>
                <span class="btn-label">6-Pair Forex & Gold (#474471944)</span>
            </button>
            <button id="portBtc" class="portfolio-btn" onclick="switchPortfolio('BTC')">
                <span class="btn-icon">🪙</span>
                <span class="btn-label">Bitcoin Dedicated (#472637125)</span>
            </button>
            <button id="portAll" class="portfolio-btn" onclick="switchPortfolio('ALL')">
                <span class="btn-icon">📊</span>
                <span class="btn-label">Combined Overview</span>
            </button>
        </div>

        <!-- Metric Cards -->
        <div class="metrics-grid">
            <div class="card">
                <div class="card-label">Live Equity</div>
                <div id="valEquity" class="card-value">$500.00</div>
                <div id="subEquity" class="card-sub">Account #474471944</div>
            </div>
            <div class="card">
                <div class="card-label">Balance</div>
                <div id="valBalance" class="card-value">$500.00</div>
                <div id="subBalance" class="card-sub">Exness-MT5Trial15</div>
            </div>
            <div class="card">
                <div class="card-label">Free Margin</div>
                <div id="valMargin" class="card-value">$500.00</div>
                <div id="subMargin" class="card-sub">Leverage 1:100</div>
            </div>
            <div class="card">
                <div class="card-label">Golden Window (13-20 UTC)</div>
                <div id="valSession" class="card-value" style="font-size: 20px;">WAITING</div>
                <div id="subSession" class="card-sub">London / NY Overlap Gate</div>
            </div>
            <div class="card">
                <div class="card-label">Open Positions</div>
                <div id="valOpenPositions" class="card-value" style="color: var(--cyan);">0</div>
                <div class="card-sub">Active Magic #888333</div>
            </div>
        </div>

        <!-- Main Workspace -->
        <div class="main-layout">
            <!-- Left: Streaming Live Terminal -->
            <div class="terminal-panel">
                <div class="terminal-header">
                    <div class="terminal-title">
                        <span>📟</span>
                        <span>LIVE MONGODB STREAMING LOGS</span>
                    </div>
                    <div class="terminal-controls">
                        <select id="logLevel" class="ctrl-select" onchange="fetchData()">
                            <option value="ALL">All Levels</option>
                            <option value="TRADE">Trade Only</option>
                            <option value="INFO">Info</option>
                            <option value="WARNING">Warning</option>
                            <option value="ERROR">Error</option>
                        </select>
                        <input type="text" id="logSearch" class="ctrl-input" placeholder="Search logs..." oninput="fetchData()" />
                    </div>
                </div>
                <div id="terminalBody" class="terminal-body">
                    <!-- Logs injected dynamically -->
                </div>
            </div>

            <!-- Right: Trades & Pattern Feeds -->
            <div class="side-panels">
                <!-- Live Trades Table -->
                <div class="panel">
                    <div class="panel-header" style="flex-wrap: wrap; gap: 8px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <div class="panel-title">Active & Recent Trades</div>
                            <span id="tradesSummaryBadge" style="font-size: 11px; padding: 2px 8px; border-radius: 6px; background: rgba(99, 102, 241, 0.15); color: var(--cyan); font-weight: 600;">Loading...</span>
                        </div>
                        <div class="terminal-controls filter-toolbar">
                            <div class="filter-row-1">
                                <button id="btnToday" class="filter-btn active" onclick="setTradeFilter('TODAY')">⚡ Today</button>
                                <button id="btnYesterday" class="filter-btn" onclick="setTradeFilter('YESTERDAY')">📅 Yesterday</button>
                                <button id="btnAll" class="filter-btn" onclick="setTradeFilter('ALL')">🌐 All</button>
                            </div>
                            <div class="filter-row-2">
                                <select id="tradeDateDropdown" class="ctrl-select date-select-dropdown" onchange="onDateDropdownChange(this.value)">
                                    <option value="" disabled selected>📅 Pick Date...</option>
                                </select>
                                <button id="btnCalendar" class="filter-btn calendar-btn" onclick="openCalendarPicker()" title="Open Interactive Calendar">🗓️ Calendar</button>
                                <input type="date" id="tradeCustomDate" style="position: absolute; opacity: 0; pointer-events: none; width: 0; height: 0;" onchange="onCalendarDatePicked(this.value)" />
                            </div>
                        </div>
                    </div>
                    <div class="table-wrap">
                        <table>
                            <thead>
                                <tr>
                                    <th>Ticket</th>
                                    <th>Symbol</th>
                                    <th>Type</th>
                                    <th>Pattern</th>
                                    <th>Lot</th>
                                    <th>Entry Time (IST)</th>
                                    <th>Exit Time (IST)</th>
                                    <th>PnL ($)</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody id="tradesTableBody">
                                <tr><td colspan="9" style="text-align: center; color: var(--text-muted);">No active trades currently open</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Patterns Feed -->
                <div class="panel">
                    <div class="panel-header">
                        <div class="panel-title">Recently Detected Harmonic Patterns</div>
                    </div>
                    <div id="patternsFeed" class="table-wrap">
                        <div style="text-align: center; color: var(--text-muted); padding: 20px;">Scanning M15 price geometry...</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let currentPortfolio = 'FOREX';
        let currentFilterMode = 'TODAY';
        let customSelectedDate = '';
        let allTradesCache = [];

        function switchPortfolio(pCode) {
            currentPortfolio = pCode;
            document.querySelectorAll('.portfolio-btn').forEach(b => b.classList.remove('active'));
            if (pCode === 'FOREX') {
                document.getElementById('portForex').classList.add('active');
                document.getElementById('subEquity').innerText = 'Account #474471944';
                document.getElementById('subBalance').innerText = 'Exness-MT5Trial15';
            } else if (pCode === 'BTC') {
                document.getElementById('portBtc').classList.add('active');
                document.getElementById('subEquity').innerText = 'Account #472637125';
                document.getElementById('subBalance').innerText = 'Exness-MT5Trial16';
            } else {
                document.getElementById('portAll').classList.add('active');
                document.getElementById('subEquity').innerText = 'Combined Equity';
                document.getElementById('subBalance').innerText = 'All Terminals Active';
            }
            // Reset cache to avoid mixing data
            allTradesCache = [];
            
            // Immediately render empty and fetch fresh
            renderTrades([]);
            fetchData();
        }

        function setTradeFilter(mode, specificDate = '') {
            currentFilterMode = mode;
            if (specificDate) customSelectedDate = specificDate;
            
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            if (mode === 'TODAY') document.getElementById('btnToday').classList.add('active');
            else if (mode === 'YESTERDAY') document.getElementById('btnYesterday').classList.add('active');
            else if (mode === 'ALL') document.getElementById('btnAll').classList.add('active');
            else if (mode === 'CUSTOM') document.getElementById('btnCalendar').classList.add('active');
            
            renderTrades(allTradesCache);
        }

        function onDateDropdownChange(val) {
            if (!val) return;
            setTradeFilter('CUSTOM', val);
        }

        function openCalendarPicker() {
            const input = document.getElementById('tradeCustomDate');
            if (input) {
                if (input.showPicker) {
                    try { input.showPicker(); } catch (e) { input.focus(); input.click(); }
                } else {
                    input.focus();
                    input.click();
                }
            }
        }

        function onCalendarDatePicked(val) {
            if (!val) return;
            // Also sync dropdown if matching
            const select = document.getElementById('tradeDateDropdown');
            if (select) select.value = val;
            setTradeFilter('CUSTOM', val);
        }

        function updateDateDropdown(trades) {
            const select = document.getElementById('tradeDateDropdown');
            if (!select || !Array.isArray(trades)) return;
            
            const datesSet = new Set();
            trades.forEach(tr => {
                if (tr.open_time && tr.open_time.$date) {
                    datesSet.add(new Date(tr.open_time.$date).toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'}));
                }
            });
            
            const dates = Array.from(datesSet).sort().reverse();
            const currentVal = select.value || customSelectedDate;
            
            let html = `<option value="" disabled ${!currentVal ? 'selected' : ''}>📅 Pick Date...</option>`;
            dates.forEach(d => {
                const parts = d.split('-');
                const dObj = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                const formatted = dObj.toLocaleDateString('en-IN', {day: '2-digit', month: 'short'});
                const count = trades.filter(tr => tr.open_time && tr.open_time.$date && new Date(tr.open_time.$date).toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'}) === d).length;
                html += `<option value="${d}" ${currentVal === d ? 'selected' : ''}>${formatted} (${count} Trades)</option>`;
            });
            select.innerHTML = html;
        }

        function renderTrades(rawTrades) {
            const tradesBody = document.getElementById('tradesTableBody');
            if (!tradesBody) return;
            
            if (!Array.isArray(rawTrades) || rawTrades.length === 0) {
                const badgeEl = document.getElementById('tradesSummaryBadge');
                if (badgeEl) badgeEl.innerText = '0 Trades';
                tradesBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 14px;">No trades recorded</td></tr>`;
                return;
            }

            const now = new Date();
            const todayIST = now.toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'}); // YYYY-MM-DD
            const yesterdayDate = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            const yesterdayIST = yesterdayDate.toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'});

            // Filter trades strictly by Entry / Session Date (IST)
            let filtered = rawTrades.filter(tr => {
                const isActive = ['OPEN', 'BREAK_EVEN', 'RISK_REDUCED', 'PARTIAL_PROFIT'].includes(tr.status);
                if (isActive) return true; // Always keep active positions visible
                
                if (currentFilterMode === 'ALL') return true;
                
                const openDateIST = tr.open_time && tr.open_time.$date ? new Date(tr.open_time.$date).toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'}) : '';
                
                if (currentFilterMode === 'TODAY') {
                    return openDateIST === todayIST;
                } else if (currentFilterMode === 'YESTERDAY') {
                    return openDateIST === yesterdayIST;
                } else if (currentFilterMode === 'CUSTOM' && customSelectedDate) {
                    return openDateIST === customSelectedDate;
                }
                return true;
            });

            // Sort active trades to top, then newest to oldest
            filtered.sort((a, b) => {
                const aActive = ['OPEN', 'BREAK_EVEN', 'RISK_REDUCED', 'PARTIAL_PROFIT'].includes(a.status);
                const bActive = ['OPEN', 'BREAK_EVEN', 'RISK_REDUCED', 'PARTIAL_PROFIT'].includes(b.status);
                if (aActive && !bActive) return -1;
                if (!aActive && bActive) return 1;
                return 0;
            });

            // Calculate & update summary badge
            const totalDayPnL = filtered.reduce((acc, t) => acc + (t.pnl || 0), 0);
            const pnlSign = totalDayPnL >= 0 ? '+' : '';
            const summaryText = `${filtered.length} Trade${filtered.length === 1 ? '' : 's'} | PnL: ${pnlSign}$${totalDayPnL.toFixed(2)}`;
            const badgeEl = document.getElementById('tradesSummaryBadge');
            if (badgeEl) {
                badgeEl.innerText = summaryText;
                badgeEl.style.color = totalDayPnL > 0 ? 'var(--success)' : (totalDayPnL < 0 ? 'var(--danger)' : 'var(--cyan)');
            }

            if (filtered.length === 0) {
                tradesBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 14px;">No trades found for selected filter (${currentFilterMode})</td></tr>`;
            } else {
                tradesBody.innerHTML = filtered.map(tr => {
                    const isActive = ['OPEN', 'BREAK_EVEN', 'RISK_REDUCED', 'PARTIAL_PROFIT'].includes(tr.status);
                    const rowStyle = isActive ? 'background: rgba(99, 102, 241, 0.1);' : '';
                    const statusColor = isActive ? 'var(--cyan)' : (tr.pnl > 0 ? 'var(--success)' : (tr.pnl < 0 ? 'var(--danger)' : '#FFF'));
                    
                    const formatIST = (dObj) => {
                        if (!dObj || !dObj.$date) return '-';
                        const d = new Date(dObj.$date);
                        const dStr = d.toLocaleDateString('en-IN', {timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short'});
                        const tStr = d.toLocaleTimeString('en-IN', {timeZone: 'Asia/Kolkata', hour: '2-digit', minute:'2-digit', second:'2-digit', hour12: true});
                        return `${dStr} ${tStr}`;
                    };
                    
                    const openTimeIST = formatIST(tr.open_time);
                    const closeTimeIST = formatIST(tr.close_time);

                    return `
                    <tr style="${rowStyle}">
                        <td>#${tr.ticket || '-'}</td>
                        <td style="font-weight: 600;">${tr.symbol}</td>
                        <td><span class="tag ${tr.direction}">${tr.direction}</span></td>
                        <td>${tr.pattern}</td>
                        <td>${tr.lot_size}</td>
                        <td style="font-size: 11px; color: var(--text-muted);">${openTimeIST}</td>
                        <td style="font-size: 11px; color: var(--text-muted);">${closeTimeIST}</td>
                        <td style="color: ${tr.pnl > 0 ? 'var(--success)' : (tr.pnl < 0 ? 'var(--danger)' : '#FFF')}">$${(tr.pnl || 0).toFixed(2)}</td>
                        <td><span class="tag" style="background: rgba(255,255,255,0.1); color: ${statusColor}; font-weight: bold;">${isActive ? '🟢 ' : ''}${tr.status}</span></td>
                    </tr>
                    `;
                }).join('');
            }
        }

        async function fetchData() {
            try {
                // 1. Fetch Status with portfolio param
                const resStatus = await fetch(`/api/status?portfolio=${currentPortfolio}`);
                const st = await resStatus.json();
                
                const pill = document.getElementById('statusPill');
                const stText = document.getElementById('statusText');
                if (st.is_online) {
                    pill.className = 'status-pill';
                    stText.innerText = 'BOT ONLINE & SCANNING';
                } else {
                    pill.className = 'status-pill offline';
                    stText.innerText = 'BOT STANDBY / OFFLINE';
                }

                document.getElementById('valEquity').innerText = '$' + (st.equity ? st.equity.toFixed(2) : '0.00');
                document.getElementById('valBalance').innerText = '$' + (st.balance ? st.balance.toFixed(2) : '0.00');
                document.getElementById('valMargin').innerText = '$' + (st.margin_free ? st.margin_free.toFixed(2) : '0.00');
                document.getElementById('valOpenPositions').innerText = st.open_positions !== undefined ? st.open_positions : '0';
                
                const sessVal = document.getElementById('valSession');
                if (st.in_session) {
                    sessVal.innerText = 'ACTIVE 🟢';
                    sessVal.style.color = 'var(--success)';
                } else {
                    sessVal.innerText = 'OUTSIDE GATE ⏳';
                    sessVal.style.color = 'var(--warning)';
                }

                // 2. Fetch Logs with portfolio param
                const level = document.getElementById('logLevel').value;
                const search = document.getElementById('logSearch').value;
                let logUrl = `/api/logs?portfolio=${currentPortfolio}&limit=150`;
                if (level !== 'ALL') logUrl += `&level=${level}`;
                if (search) logUrl += `&search=${encodeURIComponent(search)}`;

                const resLogs = await fetch(logUrl);
                const logs = await resLogs.json();
                const termBody = document.getElementById('terminalBody');
                
                if (Array.isArray(logs) && logs.length > 0) {
                    termBody.innerHTML = logs.map(l => {
                        const t = l.timestamp && l.timestamp.$date ? new Date(l.timestamp.$date).toLocaleTimeString() : new Date().toLocaleTimeString();
                        const lvl = l.level || 'INFO';
                        return `<div class="log-row">
                            <span class="log-time">[${t}]</span>
                            <span class="log-lvl ${lvl}">[${lvl}]</span>
                            <span class="log-msg">${l.message}</span>
                        </div>`;
                    }).join('');
                    termBody.scrollTop = termBody.scrollHeight;
                } else {
                    termBody.innerHTML = `<div style="color: var(--text-muted); font-size: 11px; padding: 10px;">Waiting for logs...</div>`;
                }

                // 3. Fetch Trades with portfolio param
                const resTrades = await fetch(`/api/trades?portfolio=${currentPortfolio}`);
                allTradesCache = await resTrades.json();
                updateDateDropdown(allTradesCache);
                renderTrades(allTradesCache);

                // 4. Fetch Patterns with portfolio param
                const resPats = await fetch(`/api/patterns?portfolio=${currentPortfolio}`);
                const pats = await resPats.json();
                const patFeed = document.getElementById('patternsFeed');
                if (Array.isArray(pats) && pats.length > 0) {
                    patFeed.innerHTML = pats.map(p => `
                        <div class="pattern-card">
                            <div>
                                <div style="font-weight: 700; font-size: 13px;">${p.symbol} • ${p.pattern} (${p.bull ? 'BULLISH' : 'BEARISH'})</div>
                                <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Entry: ${p.entry_price} | SL: ${p.stop_price} | TP1: ${p.t1_price}</div>
                            </div>
                            <span class="tag" style="background: rgba(99, 102, 241, 0.2); color: var(--primary);">${(p.score * 100).toFixed(0)}% SCORE</span>
                        </div>
                    `).join('');
                } else {
                    patFeed.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 20px;">Scanning price geometry...</div>`;
                }

            } catch (err) {
                console.error('Error polling dashboard API:', err);
            }
        }

        // Auto-refresh every 2.5 seconds
        setInterval(fetchData, 2500);
        fetchData();
    </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return HTMLResponse(content=HTML_CONTENT)


if __name__ == "__main__":
    print("=" * 80)
    print(">>> STARTING HARMONIC EA V3 LIVE DASHBOARD SERVER...")
    print(">>> URL: http://localhost:13000")
    print(">>> Connected to MongoDB Atlas: cluster0.tt1v1.mongodb.net / harmonic_trading")
    print("=" * 80)
    uvicorn.run(app, host="0.0.0.0", port=13000, log_level="info")
