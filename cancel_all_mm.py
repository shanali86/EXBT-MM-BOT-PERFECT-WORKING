#!/usr/bin/env python3
"""Cancel ALL mm_ prefixed orders from both Account A and Account B."""
import sys
sys.path.insert(0, '/root/exbt_mm_bot')

import config
from lbank_client import LBankClient
import time

clients = [
    ("Account A", LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)),
    ("Account B", LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)),
]

total_cancelled = 0

for label, client in clients:
    try:
        orders = client.get_open_orders(config.SYMBOL)
        print(f"\n{label}: {len(orders)} open orders found")
        for o in orders:
            oid = o.get('order_id') or o.get('orderId') or o.get('id')
            cid = str(o.get('custom_id') or o.get('customId') or '')
            price = o.get('price', '?')
            side = o.get('type', o.get('side', '?'))
            # Cancel ALL orders (bot + any stale)
            try:
                client.cancel_order(config.SYMBOL, oid)
                print(f"  ✓ Cancelled [{label}] {side} @ {price}  cid={cid}  id={oid}")
                total_cancelled += 1
                time.sleep(0.15)  # small delay to avoid rate limit
            except Exception as e:
                print(f"  ✗ Failed to cancel {oid}: {e}")
    except Exception as e:
        print(f"  ERROR getting orders for {label}: {e}")

print(f"\n=== Done. Total cancelled: {total_cancelled} orders ===")
