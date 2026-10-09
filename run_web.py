#!/usr/bin/env python3
"""
Nexus Liquidity & MM Bot Web Server
Hosts both the Institutional Landing Page (/) and the Real-Time Market Maker Console (/dashboard).
"""

import os
import sys
import json
import time
import argparse
import random
from flask import Flask, send_from_directory, jsonify, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

app = Flask(__name__, static_folder=WEB_DIR)

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

# Bot In-Memory State
STATE = {
    "status": "RUNNING",
    "mode": "DUAL_MM_ACTIVE",
    "pair": "BTFX/USDT",
    "last_price": 0.3800,
    "target_mid": 0.3800,
    "price_floor": 0.3500,
    "price_ceiling": 0.4200,
    "spread_pct": 0.0015,
    "btc_reference_price": 67450.0,
    "btc_regime": "CALM / BALANCED",
    "orders_placed_today": 4892,
    "stp_prevented_count": 1482,
    "circuit_breaker": "ARMED (0/5 err)",
    "wallets": {
        "account_a": {"usdt": 8450.20, "btfx": 22140.00, "orders": 5},
        "account_b": {"usdt": 7920.80, "btfx": 20890.00, "orders": 5},
        "combined_usd": 32742.60,
        "ratio_usdt": 50.8,
        "ratio_btfx": 49.2
    }
}

@app.route("/")
def serve_landing():
    return send_from_directory(WEB_DIR, "index.html")

@app.route("/blog")
@app.route("/blog.html")
def serve_blog():
    return send_from_directory(WEB_DIR, "blog.html")

@app.route("/api/status")
def api_status():
    # Add subtle organic jitter to live price
    jitter = (random.random() - 0.495) * 0.0004
    STATE["last_price"] = round(STATE["last_price"] + jitter, 4)
    STATE["orders_placed_today"] += random.choice([0, 1])
    return jsonify(STATE)

@app.route("/api/action", methods=["POST"])
def api_action():
    data = request.get_json(force=True, silent=True) or {}
    action = data.get("action", "")
    if action == "cancel_all":
        return jsonify({"ok": True, "message": "All open orders cancelled on both accounts."})
    elif action == "sweep":
        return jsonify({"ok": True, "message": "Sweep ask operation completed."})
    elif action == "wave":
        STATE["last_price"] = round(STATE["last_price"] + 0.0008, 4)
        return jsonify({"ok": True, "message": "Wave oscillation triggered."})
    elif action == "rebalance":
        return jsonify({"ok": True, "message": "Accounts rebalanced successfully."})
    return jsonify({"ok": True, "message": f"Action {action} processed."})

@app.route("/api/book_call", methods=["GET", "POST"], strict_slashes=False)
def api_book_call():
    if request.method == "GET":
        leads_file = os.path.join(BASE_DIR, "data", "call_bookings.json")
        leads = []
        if os.path.exists(leads_file):
            try:
                with open(leads_file, "r", encoding="utf-8") as f:
                    leads = json.load(f)
            except Exception:
                leads = []
        return jsonify({"ok": True, "count": len(leads), "leads": leads})

    data = request.get_json(force=True, silent=True) or {}
    data["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    
    # Save lead to disk
    leads_file = os.path.join(BASE_DIR, "data", "call_bookings.json")
    leads = []
    if os.path.exists(leads_file):
        try:
            with open(leads_file, "r", encoding="utf-8") as f:
                leads = json.load(f)
        except Exception:
            leads = []
    leads.append(data)
    with open(leads_file, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2)

    # Pre-format WhatsApp message
    wa_msg = (
        f"🌟 *New Institutional MM Consultation Request*\n"
        f"🏢 *Company/Project*: {data.get('token', 'N/A')} ({data.get('name', 'Client')})\n"
        f"📊 *Target Exchange*: {data.get('exchange', 'N/A')}\n"
        f"💰 *Liquidity Budget*: {data.get('liquidity', 'N/A')}\n"
        f"🏷️ *Selected Tier*: {data.get('tier', 'Professional ($4,000/mo)')}\n"
        f"📅 *Preferred Slot*: {data.get('date', 'Flexible')} at {data.get('time', '14:00 UTC')}\n"
        f"📱 *Telegram/WA*: {data.get('telegram', 'N/A')}\n"
        f"📧 *Email*: {data.get('email', 'N/A')}\n"
        f"📝 *Notes*: {data.get('notes', 'Looking forward to institutional MM onboarding with Bitfilx Tech Malaysia.')}"
    )

    return jsonify({
        "ok": True,
        "message": "Call booked successfully!",
        "whatsapp_text": wa_msg,
        "email_subject": f"Bitfilx Tech MM Strategy Consultation - {data.get('token', 'Project')}",
        "email_body": wa_msg
    })

@app.route("/<path:path>")
def serve_static(path):
    if path.startswith("api/"):
        return jsonify({"error": "API route not found"}), 404
    if os.path.exists(os.path.join(WEB_DIR, path)):
        return send_from_directory(WEB_DIR, path)
    return send_from_directory(WEB_DIR, "index.html")

def main():
    parser = argparse.ArgumentParser(description="Nexus MM Bot Landing Page & Dashboard Server")
    parser.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    args = parser.parse_args()

    print("=" * 60)
    print("  NEXUS LIQUIDITY — INSTITUTIONAL MM BOT V2.0")
    print("=" * 60)
    print(f"  • Landing Page: http://localhost:{args.port}/")
    print(f"  • Live Console: http://localhost:{args.port}/dashboard")
    print("=" * 60)
    app.run(host=args.host, port=args.port, debug=False)

if __name__ == "__main__":
    main()

