import config
from lbank_client import LBankClient

def run_test():
    client = LBankClient(config.API_KEY, config.SECRET_KEY, getattr(config, "USE_RSA", False))
    print("========== LBANK RAW BALANCE DEBUG ==========")
    print("Endpoint: /v2/supplement/user_info.do")
    
    try:
        balances = client.get_balances()
        free = balances.get("free", {})
        freeze = balances.get("freeze", {})
        
        print("\nLBANK AUTH: OK")
        
        usdt_free = free.get("USDT", "NOT_FOUND")
        usdt_locked = freeze.get("USDT", "NOT_FOUND")
        exbt_free = free.get("EXBT", "NOT_FOUND")
        exbt_locked = freeze.get("EXBT", "NOT_FOUND")
        
        print("\nUSDT:")
        print(f"Available: {usdt_free}")
        print(f"Locked: {usdt_locked}")
        
        print("\nEXBT:")
        print(f"Available: {exbt_free}")
        print(f"Locked: {exbt_locked}")
        
        if usdt_free != "NOT_FOUND" or exbt_free != "NOT_FOUND":
            print("\nBALANCE TEST: PASS")
        else:
            print("\nBALANCE TEST: FAIL")
            
    except Exception as e:
        print(f"Error: {e}")
        print("\nBALANCE TEST: FAIL")

if __name__ == "__main__":
    run_test()
