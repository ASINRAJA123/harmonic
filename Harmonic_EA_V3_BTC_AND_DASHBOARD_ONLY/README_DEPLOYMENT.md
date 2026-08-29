# Harmonic EA V3 - Bitcoin & Dashboard Package

## 🚀 Overview
This package contains the isolated Bitcoin trading bot (`harmonic_live_btc.py`) and the Web Dashboard (`dashboard_server.py`). It is fully compatible with the Forex version and can be run simultaneously without any conflicts.

## 🛠️ Deployment Instructions

### 0. ⚠️ CRITICAL PREREQUISITE: MT5 Multi-Account Setup
MetaTrader 5 natively only allows one active login per terminal executable. To run the Forex bot and the BTC bot on two *different* accounts simultaneously, you **MUST** install a second instance of the MT5 terminal.

**Instructions for the Antigravity Agent on the target server:**
1. Navigate to `C:\Program Files\`.
2. Copy the entire `MetaTrader 5 EXNESS` folder.
3. Paste it and rename the copy to exactly: **`MetaTrader 5 EXNESS BTC`**
   *(The BTC bot is hardcoded to look for `C:\Program Files\MetaTrader 5 EXNESS BTC\terminal64.exe`).*
4. When `START_BTC_BOT_BACKGROUND.vbs` runs, it will launch this isolated `terminal64.exe` instance, allowing both accounts to trade simultaneously without fighting over the connection!

### 1. Database & Dashboard Sync (Render)
Yes! Because both the Forex bot and the Bitcoin bot write to the exact same MongoDB Atlas Database (`cluster0.tt1v1.mongodb.net / harmonic_trading`), **your single Render dashboard will automatically display both bots at the same time.**
You do not need to host two dashboards on Render. The existing one will seamlessly show Forex trades and Bitcoin trades together in the same UI!

### 2. Magic Number Isolation
- **Forex Bot Magic:** `888333`
- **Bitcoin Bot Magic:** `888444`
Because they use different Magic Numbers and filter by `active_symbols`, they will never accidentally close each other's trades.

### 3. How to Start (Windows Server)
You do not need to touch the terminal. Inside this folder, simply double-click the following files:

1. **`START_BTC_BOT_BACKGROUND.vbs`** 
   - This starts the Bitcoin bot completely invisibly in the background. It is already pre-configured with your `Asinraja123##` password and will automatically log into the dedicated `Exness-MT5Trial16` account.
2. **`START_DASHBOARD.bat`** (Optional)
   - If you want to view the dashboard locally on the server (instead of Render), double click this. It will launch on `http://localhost:13000` to avoid conflicting with any Forex dashboard running on `12000`.

### 4. How to Stop
If you ever need to kill the hidden background Bitcoin bot, simply double click the **`STOP_ALL_INCLUDING_BTC.bat`** file. It will safely terminate all Python processes.

---
*Verified and configured for live execution. Golden Window Session Gate (13:00 - 20:00) is fully active.*
