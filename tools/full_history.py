import sys
sys.path.insert(0, '/root/exbt_mm_bot')
import config
from lbank_client import LBankClient
import datetime

cA = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
cB = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)

def analyze_all(client, name):
    print(f"=== {name} COMPLETE TRANSACTION HISTORY ===")
    page = 1
    total_bought_exbt = 0.0
    total_spent_usdt = 0.0
    total_sold_exbt = 0.0
    total_recv_usdt = 0.0
    total_fee_usdt = 0.0
    total_trades = 0
    earliest_time = None
    latest_time = None

    while True:
        try:
            data = client._post('/v2/transaction_history.do', {
                'symbol': config.SYMBOL,
                'current_page': str(page),
                'page_length': '100'
            })
        except Exception as e:
            print(f"Error on page {page}: {e}")
            break

        trades = data.get('data', [])
        if not trades:
            break
        
        for t in trades:
            total_trades += 1
            ts = t.get('dealTime', 0)
            if ts:
                dt = datetime.datetime.fromtimestamp(ts / 1000.0)
                if latest_time is None:
                    latest_time = dt
                earliest_time = dt

            tt = t.get('tradeType', '')
            qty = float(t.get('dealQuantity', 0))
            vol = float(t.get('dealVolumePrice', 0))
            fee = float(t.get('tradeFee', 0))
            total_fee_usdt += fee
            if 'buy' in tt:
                total_bought_exbt += qty
                total_spent_usdt += vol
            else:
                total_sold_exbt += qty
                total_recv_usdt += vol
        page += 1
        if page > 50:  # safety break
            break

    print(f"Total Trades Processed: {total_trades} across {page-1} pages")
    if earliest_time and latest_time:
        print(f"Time Range: {earliest_time} to {latest_time}")
    print(f"Total Bought EXBT: {total_bought_exbt:,.2f} for {total_spent_usdt:,.2f} USDT (Avg Buy: {total_spent_usdt/total_bought_exbt if total_bought_exbt else 0:.4f})")
    print(f"Total Sold EXBT  : {total_sold_exbt:,.2f} for {total_recv_usdt:,.2f} USDT (Avg Sell: {total_recv_usdt/total_sold_exbt if total_sold_exbt else 0:.4f})")
    print(f"Net EXBT Change  : {total_bought_exbt - total_sold_exbt:+,.2f} EXBT")
    print(f"Net USDT Change  : {total_recv_usdt - total_spent_usdt:+,.2f} USDT")
    print(f"Total Fees Paid  : {total_fee_usdt:.4f} USDT\n")
    return {
        "bought_exbt": total_bought_exbt,
        "sold_exbt": total_sold_exbt,
        "spent_usdt": total_spent_usdt,
        "recv_usdt": total_recv_usdt,
        "fees": total_fee_usdt,
        "trades": total_trades
    }

res_a = analyze_all(cA, "ACCOUNT A (MM)")
res_b = analyze_all(cB, "ACCOUNT B (MM / Volume / Candle)")

print("=== COMBINED TOTALS (ACCOUNT A + B) ===")
net_exbt = (res_a["bought_exbt"] - res_a["sold_exbt"]) + (res_b["bought_exbt"] - res_b["sold_exbt"])
net_usdt = (res_a["recv_usdt"] - res_a["spent_usdt"]) + (res_b["recv_usdt"] - res_b["spent_usdt"])
total_fees = res_a["fees"] + res_b["fees"]
total_trades = res_a["trades"] + res_b["trades"]

print(f"Total Trades: {total_trades}")
print(f"Net EXBT Change across all trades: {net_exbt:+,.2f} EXBT")
print(f"Net USDT Change across all trades: {net_usdt:+,.2f} USDT")
print(f"Total Trading Fees Paid: {total_fees:,.4f} USDT")
