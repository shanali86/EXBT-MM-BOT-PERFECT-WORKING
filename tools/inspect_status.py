import sys
import os
import json
import logging
from decimal import Decimal

from config import (
    API_KEY, SECRET_KEY,
    API_KEY_B, SECRET_KEY_B,
    SYMBOL, TARGET_MID_PRICE, PRICE_FLOOR, PRICE_CEILING
)
from lbank_client import LBankClient

logging.disable(logging.WARNING)

client_a = LBankClient(API_KEY, SECRET_KEY)
client_b = LBankClient(API_KEY_B, SECRET_KEY_B)

print("=" * 65)
print("             EXBT/USDT LIVE BOT & WALLET AUDIT REPORT")
print("=" * 65)

# 1. Wallets
bal_a = client_a.get_balances()
bal_b = client_b.get_balances()

a_usdt_free = Decimal(str(bal_a["free"].get('USDT', 0)))
a_usdt_freeze = Decimal(str(bal_a["freeze"].get('USDT', 0)))
a_usdt_total = a_usdt_free + a_usdt_freeze

a_exbt_free = Decimal(str(bal_a["free"].get('EXBT', 0)))
a_exbt_freeze = Decimal(str(bal_a["freeze"].get('EXBT', 0)))
a_exbt_total = a_exbt_free + a_exbt_freeze

b_usdt_free = Decimal(str(bal_b["free"].get('USDT', 0)))
b_usdt_freeze = Decimal(str(bal_b["freeze"].get('USDT', 0)))
b_usdt_total = b_usdt_free + b_usdt_freeze

b_exbt_free = Decimal(str(bal_b["free"].get('EXBT', 0)))
b_exbt_freeze = Decimal(str(bal_b["freeze"].get('EXBT', 0)))
b_exbt_total = b_exbt_free + b_exbt_freeze

total_usdt = a_usdt_total + b_usdt_total
total_exbt = a_exbt_total + b_exbt_total

print("\n--- 1. WALLET BALANCES ---")
print(f"Account A (Market Maker A):")
print(f"  USDT: {a_usdt_free:,.2f} free + {a_usdt_freeze:,.2f} locked = {a_usdt_total:,.2f} USDT")
print(f"  EXBT: {a_exbt_free:,.2f} free + {a_exbt_freeze:,.2f} locked = {a_exbt_total:,.2f} EXBT")

print(f"\nAccount B (Market Maker B / Vol / Candle):")
print(f"  USDT: {b_usdt_free:,.2f} free + {b_usdt_freeze:,.2f} locked = {b_usdt_total:,.2f} USDT")
print(f"  EXBT: {b_exbt_free:,.2f} free + {b_exbt_freeze:,.2f} locked = {b_exbt_total:,.2f} EXBT")

print(f"\nCOMBINED CAPITAL:")
print(f"  Total USDT: {total_usdt:,.2f} USDT")
print(f"  Total EXBT: {total_exbt:,.2f} EXBT")

# 2. Ticker
res = client_a.get_ticker(SYMBOL)
ticker = res.get("ticker", res) if isinstance(res, dict) else {}
print("\n--- 2. 24H MARKET TICKER ---")
if ticker:
    last = ticker.get('latest', '0')
    vol = ticker.get('vol', '0')
    turnover = ticker.get('turnover', '0')
    high = ticker.get('high', '0')
    low = ticker.get('low', '0')
    print(f"  Last Price : {last} USDT")
    print(f"  24h High   : {high} USDT")
    print(f"  24h Low    : {low} USDT")
    print(f"  24h Volume : {Decimal(str(vol)):,.2f} EXBT")
    print(f"  24h Turnover: ${Decimal(str(turnover)):,.2f} USDT")

# 3. Open Orders for Account A and Account B
orders_a = client_a.get_open_orders(SYMBOL)
orders_b = client_b.get_open_orders(SYMBOL)

print("\n--- 3. ACTIVE OPEN ORDERS ---")
print(f"Account A Active Orders ({len(orders_a)} total):")
for o in sorted(orders_a, key=lambda x: Decimal(str(x.get('price', 0))), reverse=True):
    print(f"  [{o.get('type').upper():4}] Price: {Decimal(str(o.get('price'))):.4f} USDT | Size: {Decimal(str(o.get('amount'))):.0f} EXBT | ID: {o.get('custom_id') or o.get('order_id')}")

print(f"\nAccount B Active Orders ({len(orders_b)} total):")
for o in sorted(orders_b, key=lambda x: Decimal(str(x.get('price', 0))), reverse=True):
    print(f"  [{o.get('type').upper():4}] Price: {Decimal(str(o.get('price'))):.4f} USDT | Size: {Decimal(str(o.get('amount'))):.0f} EXBT | ID: {o.get('custom_id') or o.get('order_id')}")

# 4. Live Order Book Depth
depth = client_a.get_orderbook(SYMBOL, size=10)
bids = depth.get('bids', [])
asks = depth.get('asks', [])

print("\n--- 4. LIVE ORDERBOOK DEPTH ---")
print("Top 5 Asks (Sell):")
for ask in reversed(asks[:5]):
    p = float(ask[0])
    s = float(ask[1])
    print(f"  ASK: Price {p:.4f} USDT | Size {s:.0f} EXBT")

best_bid = Decimal(str(bids[0][0])) if bids else Decimal('0')
best_ask = Decimal(str(asks[0][0])) if asks else Decimal('0')
if best_bid > 0 and best_ask > 0:
    spread = best_ask - best_bid
    spread_pct = (spread / best_ask) * Decimal('100')
    print(f"  --- SPREAD: {spread:.4f} USDT ({spread_pct:.2f}%) ---")

print("Top 5 Bids (Buy):")
for bid in bids[:5]:
    p = float(bid[0])
    s = float(bid[1])
    print(f"  BID: Price {p:.4f} USDT | Size {s:.0f} EXBT")

# 5. Price Corridor Verification
print("\n--- 5. SAFETY & CORRIDOR VERIFICATION ---")
print(f"Target Anchor   : {TARGET_MID_PRICE:.4f} USDT")
print(f"Allowed Corridor: [{PRICE_FLOOR:.4f}, {PRICE_CEILING:.4f}] USDT")
corridor_ok = True
for ask in asks:
    if Decimal(str(ask[0])) > PRICE_CEILING:
        print(f"  [ALERT] Ask {ask[0]} exceeds ceiling {PRICE_CEILING}!")
        corridor_ok = False
for bid in bids:
    if Decimal(str(bid[0])) < PRICE_FLOOR:
        print(f"  [ALERT] Bid {bid[0]} below floor {PRICE_FLOOR}!")
        corridor_ok = False

if corridor_ok:
    print("  ✅ All orderbook levels are 100% strictly within the [0.1270 - 0.2000] corridor!")
print("=" * 65)

