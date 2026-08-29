"""
===================================================================================
HARMONIC EA V3 — ASYNC MONGODB LOGGER & TELEMETRY MODULE
===================================================================================
Database: cluster0.tt1v1.mongodb.net / harmonic_trading
Collections: logs, trades, bot_state, patterns, account_snapshots
Non-blocking background queue worker ensures zero latency on MT5 trading ticks.
===================================================================================
"""

import os
import sys
import time
import datetime
import threading
import queue
import pymongo

MONGO_URI = "mongodb+srv://student:student@cluster0.tt1v1.mongodb.net/?retryWrites=true&w=majority"
DB_NAME = "harmonic_trading"


class MongoTelemetryLogger:
    def __init__(self, uri=MONGO_URI, db_name=DB_NAME):
        self.uri = uri
        self.db_name = db_name
        self.client = None
        self.db = None
        self.connected = False
        self.queue = queue.Queue(maxsize=10000)
        self.worker_thread = None
        self._init_connection()
        self._start_worker()

    def _init_connection(self):
        try:
            self.client = pymongo.MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.db_name]
            # Ping database
            self.client.admin.command('ping')
            # 1-Hour Auto-Purge TTL Index on logs collection
            self.db["logs"].create_index("timestamp", expireAfterSeconds=3600)
            self.connected = True
            print(f"[MongoLogger] Connected successfully to MongoDB: {self.db_name} (1-Hr Log TTL Active)")
        except Exception as e:
            self.connected = False
            print(f"[MongoLogger] MongoDB connection warning: {e}. Running in buffered mode.")

    def _start_worker(self):
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        while True:
            try:
                task = self.queue.get()
                if task is None:
                    break

                action_type, collection_name, data = task

                if not self.connected:
                    self._init_connection()

                if self.connected and self.db is not None:
                    col = self.db[collection_name]
                    if action_type == "insert":
                        col.insert_one(data)
                    elif action_type == "update":
                        query, update_data, upsert = data
                        col.update_one(query, update_data, upsert=upsert)
                self.queue.task_done()
            except Exception as e:
                # Silently catch to prevent crashing trading thread
                time.sleep(0.5)

    def log(self, level, message, log_type="SYSTEM", metadata=None):
        doc = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
            "level": level.upper(),
            "type": log_type.upper(),
            "message": str(message),
            "metadata": metadata or {}
        }
        try:
            self.queue.put_nowait(("insert", "logs", doc))
        except queue.Full:
            pass




    def record_trade_open(self, trade_doc):
        doc = {
            "ticket": trade_doc.get("ticket"),
            "deal": trade_doc.get("deal"),
            "symbol": trade_doc.get("symbol"),
            "pattern": trade_doc.get("pattern"),
            "direction": trade_doc.get("direction"),
            "lot_size": trade_doc.get("lot_size"),
            "entry_price": trade_doc.get("entry_price"),
            "sl_price": trade_doc.get("sl_price"),
            "tp1_price": trade_doc.get("tp1_price"),
            "tp2_price": trade_doc.get("tp2_price"),
            "score": trade_doc.get("score"),
            "open_time": datetime.datetime.now(datetime.timezone.utc),
            "close_time": None,
            "status": "OPEN",
            "exit_price": None,
            "exit_reason": None,
            "pnl": 0.0,
            "portfolio": trade_doc.get("portfolio", "FOREX"),
            "account": trade_doc.get("account", 474471944)
        }
        self.log("TRADE", f"OPENED {doc['direction']} on {doc['symbol']} ({doc['pattern']}) @ {doc['entry_price']} | Lot: {doc['lot_size']}", log_type="TRADE", metadata=doc)
        try:
            self.queue.put_nowait(("insert", "trades", doc))
        except queue.Full:
            pass

    def record_trade_update(self, ticket, update_fields):
        query = {"ticket": ticket}
        update_data = {"$set": update_fields}
        try:
            self.queue.put_nowait(("update", "trades", (query, update_data, False)))
        except queue.Full:
            pass

    def record_pattern(self, pattern_doc):
        doc = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
            "symbol": pattern_doc.get("symbol"),
            "pattern": pattern_doc.get("pattern"),
            "bull": pattern_doc.get("bull"),
            "score": pattern_doc.get("score"),
            "entry_price": pattern_doc.get("entry_price"),
            "stop_price": pattern_doc.get("stop_price"),
            "t1_price": pattern_doc.get("t1_price"),
            "t2_price": pattern_doc.get("t2_price"),
            "portfolio": pattern_doc.get("portfolio", "FOREX"),
            "account": pattern_doc.get("account", 474471944)
        }
        try:
            self.queue.put_nowait(("insert", "patterns", doc))
        except queue.Full:
            pass

    def update_bot_state(self, state_dict):
        state_dict["last_heartbeat"] = datetime.datetime.now(datetime.timezone.utc)
        query = {"state_id": "current_live_state"}
        update_data = {"$set": state_dict}
        try:
            self.queue.put_nowait(("update", "bot_state", (query, update_data, True)))
        except queue.Full:
            pass

    def publish_bot_status(self, status_dict):
        portfolio = status_dict.get("portfolio", "FOREX")
        status_dict["last_heartbeat"] = datetime.datetime.now(datetime.timezone.utc)
        query = {"state_id": f"current_live_state_{portfolio.lower()}"}
        update_data = {"$set": status_dict}
        try:
            self.queue.put_nowait(("update", "bot_state", (query, update_data, True)))
        except queue.Full:
            pass


# Global singleton instance
mongo_logger = MongoTelemetryLogger()
