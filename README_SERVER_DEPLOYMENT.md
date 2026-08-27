# 🚀 Harmonic EA V3 Champion — Server / VPS Deployment Guide

This package allows you to deploy and run the **Harmonic EA V3 Champion** live trading engine on any Windows Server or VPS completely in the background without needing any visible terminal or command prompt window open.

---

## 📦 What's Included in This Package:

1. **`START_BOT_BACKGROUND.bat`**: Double-click to run the bot silently in the background (hidden process).
2. **`VIEW_LIVE_LOGS.bat`**: Double-click anytime to open a live streaming dashboard of the trading logs. Closing this window will NOT stop the bot!
3. **`STATUS_BOT.bat`**: Double-click to check if the bot is running, its process ID, and the last 10 log messages.
4. **`STOP_BOT.bat`**: Double-click to safely stop the background bot.
5. **`INSTALL_DEPENDENCIES.bat`**: 1-click installer for `MetaTrader5`, `pandas`, and `numpy`.
6. **`core/`**: The institutional Harmonic pattern detection & execution engine.
7. **`harmonic_live_exness.py`**: The main live trading script connected to Exness MT5.

---

## ⚡ 3-Step Setup on Your Server / VPS:

### Step 1: Install Exness MT5
1. Install **MetaTrader 5 Exness** on your server.
2. Log into your Demo account (**#474471944** on server **Exness-MT5Trial15**).
3. Ensure **"Algo Trading"** is turned ON in the MT5 top toolbar.

### Step 2: Install Python & Dependencies
1. Ensure **Python 3.10+** is installed on your server with **"Add Python to PATH"** checked during installation.
2. Double-click **`INSTALL_DEPENDENCIES.bat`** (or run `pip install MetaTrader5 pandas numpy`).

### Step 3: Run the Bot in the Background!
1. Double-click **`START_BOT_BACKGROUND.bat`**.
2. That's it! The bot is now running 24/7 silently in the background.

---

## 🔍 How to Monitor Logs & Trades:

* **To see live streaming logs**: Double-click **`VIEW_LIVE_LOGS.bat`**. You can close the log window anytime; the bot keeps running in the background.
* **To check bot status**: Double-click **`STATUS_BOT.bat`**.
* **Log file location**: `logs/harmonic_live.log` (stores every order, pattern detection, and account balance update).
