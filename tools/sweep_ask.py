import sys
sys.path.insert(0, "/root/exbt_mm_bot")
from lbank_client import LBankClient
import config
import time

client_b = LBankClient(config.API_KEY_B, config.SECRET_KEY_B)
depth = client_b.get_orderbook("exbt_usdt", size=10)
asks = depth.get("asks", [])
print("Current top 5 asks:", asks[:5])

# Find the order at 0.3420 or lowest external ask <= 0.3450
target_ask = None
for a in asks:
    p = float(a[0])
    qty = float(a[1])
    if p <= 0.3450:
        target_ask = (p, qty)
        break

if target_ask:
    p, qty = target_ask
    print(f"Executing clean sweep of ask @ {p:.4f}, qty: {qty:.2f} EXBT (cost: ${p*qty:.2f} USDT)")
    res = client_b.place_order(
        symbol="exbt_usdt",
        side="buy",
        price=p,
        amount=qty,
        order_type="limit",
        custom_id=f"sweep_{int(time.time())}"
    )
    print("Order result:", res)
    time.sleep(1.0)
    print("New orderbook after sweep:")
    new_depth = client_b.get_orderbook("exbt_usdt", size=5)
    print("New asks:", new_depth.get("asks", [])[:5])
    print("New bids:", new_depth.get("bids", [])[:5])
else:
    print("No ask <= 0.3450 found.")
