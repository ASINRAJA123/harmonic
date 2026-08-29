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
def get_status():
    try:
        state = db["bot_state"].find_one({"state_id": "current_live_state"}, {"_id": 0})
        if not state:
            state = {
                "is_online": False,
                "balance": 500.0,
                "equity": 500.0,
                "margin_free": 500.0,
                "open_positions": 0,
                "account_login": 474471944,
                "account_server": "Exness-MT5Trial15",
                "in_session": False,
                "last_heartbeat": None
            }
        
        # Check freshness of heartbeat (within 45s)
        if state.get("last_heartbeat"):
            # calculate diff
            last_hb = state["last_heartbeat"]
            if isinstance(last_hb, datetime.datetime):
                now = datetime.datetime.now(datetime.timezone.utc)
                if (now - last_hb.replace(tzinfo=datetime.timezone.utc if last_hb.tzinfo is None else last_hb.tzinfo)).total_seconds() > 45:
                    state["is_online"] = False
                    
        return parse_json(state)
    except Exception as e:
        return {"error": str(e), "is_online": False}


@app.get("/api/logs")
def get_logs(limit: int = 150, level: Optional[str] = None, search: Optional[str] = None):
    try:
        # Only fetch logs from the last 1 hour
        one_hour_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        query = {"timestamp": {"$gte": one_hour_ago}}
        
        if level and level != "ALL":
            query["level"] = level.upper()
        if search:
            query["message"] = {"$regex": search, "$options": "i"}
            
        logs_cursor = db["logs"].find(query).sort("timestamp", -1).limit(limit)
        logs_list = list(logs_cursor)
        logs_list.reverse() # chronological order
        return parse_json(logs_list)
    except Exception as e:
        return {"error": str(e), "logs": []}


@app.get("/api/trades")
def get_trades(limit: int = 100):
    try:
        trades_cursor = db["trades"].find().sort("open_time", -1).limit(limit)
        trades_list = list(trades_cursor)
        return parse_json(trades_list)
    except Exception as e:
        return {"error": str(e), "trades": []}


@app.get("/api/patterns")
def get_patterns(limit: int = 20):
    try:
        patterns_cursor = db["patterns"].find().sort("timestamp", -1).limit(limit)
        patterns_list = list(patterns_cursor)
        return parse_json(patterns_list)
    except Exception as e:
        return {"error": str(e), "patterns": []}


@app.get("/api/metrics")
def get_metrics():
    try:
        trades = list(db["trades"].find())
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

        /* Metric Cards Grid */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
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
            transition: all 0.3s ease;
        }

        .card:hover {
            border-color: var(--border-glow);
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
            grid-template-columns: 1.6fr 1fr;
            gap: 20px;
        }

        @media (max-width: 1024px) {
            .main-layout { grid-template-columns: 1fr; }
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
                    <div class="panel-header">
                        <div class="panel-title">Active & Recent Trades</div>
                        <div class="terminal-controls">
                            <select id="tradeDateFilter" class="ctrl-select" onchange="toggleCustomDate(); fetchData();">
                                <option value="TODAY" selected>Today (IST)</option>
                                <option value="ALL">All Time</option>
                                <option value="CUSTOM">Pick Date...</option>
                            </select>
                            <input type="date" id="tradeCustomDate" class="ctrl-input" style="display:none;" onchange="fetchData()" />
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
        function toggleCustomDate() {
            const filterVal = document.getElementById('tradeDateFilter').value;
            const customDateInput = document.getElementById('tradeCustomDate');
            if (filterVal === 'CUSTOM') {
                customDateInput.style.display = 'inline-block';
                if (!customDateInput.value) {
                    customDateInput.value = new Date().toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'});
                }
            } else {
                customDateInput.style.display = 'none';
            }
        }

        async function fetchData() {
            try {
                // 1. Fetch Status
                const resStatus = await fetch('/api/status');
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

                document.getElementById('valEquity').innerText = '$' + (st.equity ? st.equity.toFixed(2) : '500.00');
                document.getElementById('valBalance').innerText = '$' + (st.balance ? st.balance.toFixed(2) : '500.00');
                document.getElementById('valMargin').innerText = '$' + (st.margin_free ? st.margin_free.toFixed(2) : '500.00');
                document.getElementById('valOpenPositions').innerText = st.open_positions !== undefined ? st.open_positions : '0';
                
                const sessVal = document.getElementById('valSession');
                if (st.in_session) {
                    sessVal.innerText = 'ACTIVE 🟢';
                    sessVal.style.color = 'var(--success)';
                } else {
                    sessVal.innerText = 'OUTSIDE GATE ⏳';
                    sessVal.style.color = 'var(--warning)';
                }

                // 2. Fetch Logs from MongoDB
                const level = document.getElementById('logLevel').value;
                const search = document.getElementById('logSearch').value;
                let logUrl = '/api/logs?limit=150';
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
                }

                // 3. Fetch Trades
                const resTrades = await fetch('/api/trades');
                let trades = await resTrades.json();
                const tradesBody = document.getElementById('tradesTableBody');
                
                if (Array.isArray(trades) && trades.length > 0) {
                    const filterMode = document.getElementById('tradeDateFilter').value;
                    const todayIST = new Date().toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'}); // YYYY-MM-DD
                    const customDateVal = document.getElementById('tradeCustomDate').value;
                    
                    // Filter trades by date
                    trades = trades.filter(tr => {
                        const isActive = ['OPEN', 'BREAK_EVEN', 'RISK_REDUCED', 'PARTIAL_PROFIT'].includes(tr.status);
                        if (isActive) return true; // Always show active trades
                        
                        if (filterMode === 'ALL') return true;
                        
                        let tradeDateIST = '';
                        if (tr.open_time && tr.open_time.$date) {
                            tradeDateIST = new Date(tr.open_time.$date).toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'});
                        } else if (tr.close_time && tr.close_time.$date) {
                            tradeDateIST = new Date(tr.close_time.$date).toLocaleDateString('en-CA', {timeZone: 'Asia/Kolkata'});
                        }
                        
                        if (filterMode === 'TODAY') {
                            return tradeDateIST === todayIST;
                        } else if (filterMode === 'CUSTOM' && customDateVal) {
                            return tradeDateIST === customDateVal;
                        }
                        return true;
                    });

                    // Sort active trades to top
                    trades.sort((a, b) => {
                        const aActive = ['OPEN', 'BREAK_EVEN', 'RISK_REDUCED', 'PARTIAL_PROFIT'].includes(a.status);
                        const bActive = ['OPEN', 'BREAK_EVEN', 'RISK_REDUCED', 'PARTIAL_PROFIT'].includes(b.status);
                        if (aActive && !bActive) return -1;
                        if (!aActive && bActive) return 1;
                        return 0;
                    });

                    if (trades.length === 0) {
                        tradesBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 14px;">No trades found for selected date filter (${filterMode})</td></tr>`;
                    } else {
                        tradesBody.innerHTML = trades.map(tr => {
                            const isActive = ['OPEN', 'BREAK_EVEN', 'RISK_REDUCED', 'PARTIAL_PROFIT'].includes(tr.status);
                            const rowStyle = isActive ? 'background: rgba(99, 102, 241, 0.1);' : '';
                            const statusColor = isActive ? 'var(--cyan)' : (tr.pnl > 0 ? 'var(--success)' : (tr.pnl < 0 ? 'var(--danger)' : '#FFF'));
                            
                            const formatIST = (dObj) => {
                                if (!dObj || !dObj.$date) return '-';
                                const d = new Date(dObj.$date);
                                const dStr = d.toLocaleDateString('en-IN', {timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short'});
                                const tStr = d.toLocaleTimeString('en-IN', {timeZone: 'Asia/Kolkata', hour: '2-digit', minute:'2-digit', second:'2-digit', hour12: true});
                                return filterMode === 'TODAY' ? tStr : `${dStr} ${tStr}`;
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
                } else {
                    tradesBody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 14px;">No trades recorded</td></tr>`;
                }

                // 4. Fetch Patterns
                const resPats = await fetch('/api/patterns');
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
    print("🚀 STARTING HARMONIC EA V3 LIVE DASHBOARD SERVER...")
    print("🌐 URL: http://localhost:12000")
    print("☁️ Connected to MongoDB Atlas: cluster0.tt1v1.mongodb.net / harmonic_trading")
    print("=" * 80)
    uvicorn.run(app, host="0.0.0.0", port=12000, log_level="info")
