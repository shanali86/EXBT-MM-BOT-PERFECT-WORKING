from main import get_order_side

orders = [
    {"order_id": "1", "side": "buy"},
    {"order_id": "2", "type": "sell"},
    {"order_id": "3", "price": 0.5},
    {"order_id": "4", "side": "BUY"},
    {}
]

print("Schema Test Results:")
for o in orders:
    print(f"Order: {o} -> Side: '{get_order_side(o)}'")

class DummyBot:
    def __init__(self, active_orders):
        self.active_orders = active_orders
        self.stats = {}
        self.symbol = "EXBT_USDT"
        self.total_volume_today = 0
    def get_reference_price(self): return 0.18
    def get_next_trade_delay(self): return 10

class DummyBM:
    def get_allocation(self, asset):
        return {}

class DummyClient:
    def get_mid_price(self, symbol): return 0.18

from main import print_health_monitor
print("\nTesting empty orders:")
print_health_monitor(DummyBM(), DummyBot([]), DummyBot([]), DummyBot([]), DummyClient())
print("Empty orders completed successfully!")

print("\nTesting mixed orders:")
print_health_monitor(DummyBM(), DummyBot(orders), DummyBot([]), DummyBot([]), DummyClient())
print("Mixed orders completed successfully!")
