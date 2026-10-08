import config
from lbank_client import LBankClient
import json

def run_test():
    print("========== LBANK RAW BALANCE DEBUG ==========")
    
    print("\n[Account A - MM]")
    client_a = LBankClient(config.API_KEY, config.SECRET_KEY, getattr(config, "USE_RSA", False))
    print(f"API Key Fingerprint: ****{config.API_KEY[-4:]}")
    
    try:
        raw_a = client_a._post("/v2/user_info.do", {})
        print("\nEndpoint: /v2/user_info.do")
        print(f"Result: {raw_a.get('result')}")
        print(f"Error Code: {raw_a.get('error_code')}")
        
        info = raw_a.get("info", {})
        free = info.get("free", {})
        freeze = info.get("freeze", {})
        
        print(f"Free Keys: {list(free.keys())[:10]} ... (Total {len(free.keys())})")
        
        upper_keys = [k.upper() for k in free.keys()]
        print(f"USDT Entry Found: {'USDT' in upper_keys}")
        print(f"EXBT Entry Found: {'EXBT' in upper_keys}")
        
        usdt_free = free.get('usdt', 'NOT_FOUND')
        usdt_freeze = freeze.get('usdt', 'NOT_FOUND')
        exbt_free = free.get('exbt', 'NOT_FOUND')
        exbt_freeze = freeze.get('exbt', 'NOT_FOUND')
        
        print(f"\nUSDT:\nAvailable: {usdt_free}\nLocked: {usdt_freeze}")
        print(f"\nEXBT:\nAvailable: {exbt_free}\nLocked: {exbt_freeze}")
        
    except Exception as e:
        print(f"Error testing Account A: {e}")
        
    print("\n[Account B - Volume]")
    if hasattr(config, "API_KEY_B"):
        client_b = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, getattr(config, "USE_RSA", False))
        print(f"API Key Fingerprint: ****{config.API_KEY_B[-4:]}")
        try:
            raw_b = client_b._post("/v2/user_info.do", {})
            info_b = raw_b.get("info", {})
            free_b = info_b.get("free", {})
            print(f"USDT Free: {free_b.get('usdt', 'NOT_FOUND')}")
            print(f"EXBT Free: {free_b.get('exbt', 'NOT_FOUND')}")
        except Exception as e:
            print(f"Error testing Account B: {e}")

    print("\n=============================================")

if __name__ == "__main__":
    run_test()
