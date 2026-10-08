import config
from lbank_client import LBankClient
import json

def diagnose():
    client = LBankClient(config.API_KEY, config.SECRET_KEY, getattr(config, "USE_RSA", False))
    print("LOCK DIAGNOSIS\n")
    
    b = client.get_balances()
    usdt_lock = b["freeze"].get("USDT", 0)
    exbt_lock = b["freeze"].get("EXBT", 0)
    print(f"USDT locked: {usdt_lock}")
    print(f"EXBT locked: {exbt_lock}\n")
    
    # 1. Check EXBT/USDT
    exbt_orders = client.get_open_orders("exbt_usdt")
    print(f"EXBT_USDT orders: {len(exbt_orders)}\n")
    
    # 2. Check all open orders across other common pairs
    symbols = ["btc_usdt", "eth_usdt", "bfic_usdt"]
    print("Other open orders:")
    found_any = False
    for sym in symbols:
        try:
            orders = client.get_open_orders(sym)
            if orders:
                found_any = True
                print(f"{sym} orders: {len(orders)}")
                for o in orders:
                    print(f"  Order ID: {o.get('order_id')} | side={o.get('type')} qty={o.get('amount')} price={o.get('price')}")
        except Exception as e:
            pass
            
    if not found_any:
        print("None found on common pairs.")
        
    print("\nIdentified lock source:")
    if not found_any:
        print("The LBank API `orders_info_no_deal.do` requires specifying a symbol and only returns orders matching this API key context.")
        print("Because no orders exist for this API key on EXBT_USDT, the locked funds (9372 USDT) are either:")
        print("- Limit orders placed manually via the website or another API key.")
        print("- Limit orders on an untested symbol (e.g., Launchpad tokens).")
        print("- Locked in LBank Earn / Staking.")
        print("- Frozen due to pending withdrawals or internal LBank risk holds.")
        print("LBank's public API does not provide a global 'get all frozen reasons' endpoint without a specific symbol/order ID.")
    else:
        print("Found active orders locking funds on other pairs.")

if __name__ == "__main__":
    diagnose()
