import sys
import time

sys.path.append('/root/exbt_mm_bot')

import config
from lbank_client import LBankClient


MM_PREFIX = "mm_"


def get_custom_id(order):
    return (
        order.get("custom_id")
        or order.get("customer_id")
        or ""
    )


print("--- Account A: MM-Owned Cleanup Only ---")

client = LBankClient(
    config.API_KEY,
    config.SECRET_KEY,
    config.USE_RSA
)

orders = client.get_open_orders(config.SYMBOL)

owned = [
    order for order in orders
    if str(get_custom_id(order)).startswith(MM_PREFIX)
]

unknown = [
    order for order in orders
    if not str(get_custom_id(order)).startswith(MM_PREFIX)
]

print(f"Total open orders: {len(orders)}")
print(f"MM-owned orders: {len(owned)}")
print(f"Untouched non-MM/unknown orders: {len(unknown)}")

cancelled = 0
failed = 0

for order in owned:
    order_id = order.get("order_id")

    if not order_id:
        print("SKIP: MM-owned order missing order_id")
        failed += 1
        continue

    if client.cancel_order(config.SYMBOL, order_id):
        cancelled += 1
    else:
        failed += 1

    time.sleep(0.1)


# Verify from exchange after cancellation.
time.sleep(1)

remaining = client.get_open_orders(config.SYMBOL)

remaining_owned = [
    order for order in remaining
    if str(get_custom_id(order)).startswith(MM_PREFIX)
]

remaining_other = [
    order for order in remaining
    if not str(get_custom_id(order)).startswith(MM_PREFIX)
]


print()
print("===== CLEANUP RESULT =====")
print(f"MM-owned cancelled: {cancelled}")
print(f"Cancellation failures: {failed}")
print(f"MM-owned still open: {len(remaining_owned)}")
print(f"Non-MM/unknown still untouched: {len(remaining_other)}")

if remaining_owned:
    print("FAIL: some MM-owned orders remain open")
    sys.exit(1)

if failed:
    print("FAIL: one or more MM cancellation attempts failed")
    sys.exit(1)

print("PASS: MM-owned cleanup verified")
print("PASS: non-MM/unknown orders were not targeted")
print("PASS: Account B was not touched")
