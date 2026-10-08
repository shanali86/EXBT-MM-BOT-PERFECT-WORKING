import config
import datetime
from lbank_client import LBankClient

client_a = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
client_b = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)

def summarize_account(name, client):
    print("=" * 60)
    print("=== " + name + " RECENT TRADES ===")
    print("=" * 60)
    try:
        resp = client._post('/v2/transaction_history.do', {'symbol': config.SYMBOL, 'current_page': '1', 'page_length': '50'})
        trades = resp.get('data', [])
        print("Total trades in batch: " + str(len(trades)))
        total_bought_exbt = 0.0
        total_spent_usdt = 0.0
        total_sold_exbt = 0.0
        total_recv_usdt = 0.0
        
        for t in trades[:15]:
            ts = datetime.datetime.fromtimestamp(t.get('dealTime', 0) / 1000.0)
            trade_type = t.get('tradeType', '')
            qty = float(t.get('dealQuantity', 0))
            price = float(t.get('dealPrice', 0))
            vol_price = float(t.get('dealVolumePrice', 0))
            fee = float(t.get('tradeFee', 0))
            time_str = ts.strftime('%H:%M:%S')
            print(time_str + " | " + trade_type.ljust(10) + " | Qty: " + f"{qty:8.2f}" + " EXBT @ " + f"{price:.4f}" + " (= " + f"{vol_price:7.2f}" + " USDT) | Fee: " + str(fee))
            
        for t in trades:
            trade_type = t.get('tradeType', '')
            qty = float(t.get('dealQuantity', 0))
            vol_price = float(t.get('dealVolumePrice', 0))
            if 'buy' in trade_type:
                total_bought_exbt += qty
                total_spent_usdt += vol_price
            else:
                total_sold_exbt += qty
                total_recv_usdt += vol_price
                
        print("\nBatch Summary:")
        print("  Total Bought: " + f"{total_bought_exbt:.2f}" + " EXBT for " + f"{total_spent_usdt:.2f}" + " USDT")
        print("  Total Sold:   " + f"{total_sold_exbt:.2f}" + " EXBT for " + f"{total_recv_usdt:.2f}" + " USDT")
        print("  Net EXBT:     " + f"{total_bought_exbt - total_sold_exbt:+.2f}" + " EXBT")
        print("  Net USDT:     " + f"{total_recv_usdt - total_spent_usdt:+.2f}" + " USDT\n")
    except Exception as e:
        print("Error for " + name + ": " + str(e))

summarize_account('ACCOUNT A (Market Maker)', client_a)
summarize_account('ACCOUNT B (Volume / Candle)', client_b)
