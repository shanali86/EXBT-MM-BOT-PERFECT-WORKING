import time
import config
from lbank_client import LBankClient

def print_balance(client, title):
    b = client.get_balances()
    usdt_free = b["free"].get("USDT", 0)
    usdt_lock = b["freeze"].get("USDT", 0)
    exbt_free = b["free"].get("EXBT", 0)
    exbt_lock = b["freeze"].get("EXBT", 0)
    print(f"\n{title}")
    print(f"USDT:\nAvailable: {usdt_free}\nLocked: {usdt_lock}\nTotal: {usdt_free + usdt_lock}")
    print(f"EXBT:\nAvailable: {exbt_free}\nLocked: {exbt_lock}\nTotal: {exbt_free + exbt_lock}")
    return usdt_free, usdt_lock, exbt_free, exbt_lock

def main():
    print("OPEN ORDER CLEANUP\n")
    client = LBankClient(config.API_KEY, config.SECRET_KEY, getattr(config, "USE_RSA", False))
    
    usdt_free, usdt_lock, exbt_free, exbt_lock = print_balance(client, "WALLET BEFORE CANCELLATION")
    
    print("\nFetching open orders...")
    orders = client.get_open_orders(config.SYMBOL)
    total_orders = len(orders)
    
    buys = sum(1 for o in orders if o.get('type') == 'buy')
    sells = sum(1 for o in orders if o.get('type') == 'sell')
    
    print(f"Total open orders: {total_orders}")
    print(f"BUY orders: {buys}")
    print(f"SELL orders: {sells}")
    
    print("\n🧹 Cancelling old EXBT/USDT orders...")
    cancelled = 0
    failed = 0
    
    for o in orders:
        order_id = o.get("order_id")
        if client.cancel_order(config.SYMBOL, order_id):
            cancelled += 1
        else:
            failed += 1
        time.sleep(0.2)
        
    print(f"Cancelled: {cancelled}")
    print(f"Failed: {failed}")
    
    remaining = len(client.get_open_orders(config.SYMBOL))
    print(f"Remaining: {remaining}")
    
    print("\nRefreshing wallet after cancellation... waiting for release...")
    for _ in range(5):
        time.sleep(2)
        print_balance(client, "POLLING...")
        
    print_balance(client, "WALLET AFTER CLEANUP")

if __name__ == "__main__":
    main()
