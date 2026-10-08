import sys
sys.path.insert(0, '/root/exbt_mm_bot')
import config
from lbank_client import LBankClient

client = LBankClient(config.API_KEY, config.SECRET_KEY)
ob = client.get_orderbook(config.SYMBOL, size=30)
bids = ob.get('bids', [])
asks = ob.get('asks', [])

print(f"Total Bids: {len(bids)}, Total Asks: {len(asks)}")
print("\n=== TOP 20 ASKS ===")
for a in asks[:20]:
    print(f"  Price: {float(a[0]):.4f} USDT | Size: {float(a[1]):,.0f} EXBT")

print("\n=== TOP 20 BIDS ===")
for b in bids[:20]:
    print(f"  Price: {float(b[0]):.4f} USDT | Size: {float(b[1]):,.0f} EXBT")
