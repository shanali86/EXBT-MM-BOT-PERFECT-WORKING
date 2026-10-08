import sys
sys.path.insert(0, '/root/exbt_mm_bot')
import config
from lbank_client import LBankClient
import datetime

cA = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
cB = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)

def get_all_deals(client):
    deals = []
    page = 1
    while page <= 30:
        res = client._post('/v2/transaction_history.do', {
            'symbol': config.SYMBOL,
            'current_page': str(page),
            'page_length': '100'
        })
        batch = res.get('data', [])
        if not batch:
            break
        deals.extend(batch)
        page += 1
    return deals

print("Fetching transaction history from both accounts...")
deals_a = get_all_deals(cA)
deals_b = get_all_deals(cB)
print(f"Fetched {len(deals_a)} deals for Account A, {len(deals_b)} deals for Account B.")

# Index Account B deals by dealTime and dealQuantity to detect cross-account matches
b_deal_keys = set()
for d in deals_b:
    ts = d.get('dealTime', 0)
    qty = round(float(d.get('dealQuantity', 0)), 2)
    # LBank internal match has identical or near-identical timestamp (+- 500ms)
    b_deal_keys.add((ts // 1000, qty))

external_trades = []
for d in deals_a:
    ts = d.get('dealTime', 0)
    sec = ts // 1000
    qty = round(float(d.get('dealQuantity', 0)), 2)
    price = float(d.get('dealPrice', 0))
    trade_type = d.get('tradeType', '')
    
    # Check if this deal was matched by Account B
    matched = False
    for s_offset in (-1, 0, 1):
        if (sec + s_offset, qty) in b_deal_keys:
            matched = True
            break
            
    if not matched:
        dt = datetime.datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S UTC')
        vol = float(d.get('dealVolumePrice', 0))
        external_trades.append({
            'time': dt,
            'type': trade_type,
            'price': price,
            'qty': qty,
            'vol': vol,
            'order_id': d.get('orderUuid', d.get('orderId', 'N/A'))
        })

print(f"\nFound {len(external_trades)} probable EXTERNAL TRADES on Account A (not matched with Account B):")
total_ext_buy_exbt = 0.0  # External user bought (Bot sold)
total_ext_sell_exbt = 0.0 # External user sold (Bot bought)
total_ext_vol_usdt = 0.0

for t in external_trades[:30]:
    # If bot was 'buy_maker', external user sold to bot
    # If bot was 'sell_maker', external user bought from bot
    action = "External User SOLD to Bot" if "buy" in t['type'] else "External User BOUGHT from Bot"
    print(f"[{t['time']}] {action} | Qty: {t['qty']:,.2f} EXBT @ {t['price']:.4f} USDT (= ${t['vol']:.2f}) | Order: {t['order_id']}")

for t in external_trades:
    if "buy" in t['type']:
        total_ext_sell_exbt += t['qty']
    else:
        total_ext_buy_exbt += t['qty']
    total_ext_vol_usdt += t['vol']

print(f"\n--- EXTERNAL ACTIVITY TOTALS ---")
print(f"Total External Sells (dumped on bot) : {total_ext_sell_exbt:,.2f} EXBT")
print(f"Total External Buys (taken from bot) : {total_ext_buy_exbt:,.2f} EXBT")
print(f"Net EXBT added to bot from external : {total_ext_sell_exbt - total_ext_buy_exbt:+,.2f} EXBT")
print(f"Total External Volume               : ${total_ext_vol_usdt:,.2f} USDT")
