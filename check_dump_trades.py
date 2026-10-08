import requests
import datetime

resp = requests.get('https://api.lbkex.com/v2/trades.do?symbol=exbt_usdt&size=100').json()
data = resp.get('data', [])

print("=" * 75)
print("--- ALL RECENT TRADES ON LBANK (SORTED FROM LATEST TO EARLIEST) ---")
print("=" * 75)

large_trades = []

for t in data:
    ts = datetime.datetime.fromtimestamp(t['date_ms'] / 1000.0)
    price = float(t['price'])
    amount = float(t['amount'])
    vol = price * amount
    side = str(t['type']).upper()
    time_str = ts.strftime('%H:%M:%S')
    
    is_big = "[DUMP]" if (amount > 500 or price < 0.20 or vol > 100) else "      "
    print(time_str + " | " + is_big + " | " + side.ljust(12) + " | Price: " + f"{price:.4f}" + " | Qty: " + f"{amount:9.2f}" + " EXBT | Value: " + f"{vol:8.2f}" + " USDT")
    if amount > 300 or price < 0.20:
        large_trades.append((time_str, side, price, amount, vol))

print("\n" + "=" * 75)
print("--- SUMMARY OF ABNORMAL / DUMP TRADES ---")
print("=" * 75)
for lt in large_trades:
    print(lt[0] + " | " + lt[1] + " | Price: " + f"{lt[2]:.4f}" + " | Qty: " + f"{lt[3]:.2f}" + " EXBT | Value: " + f"{lt[4]:.2f}" + " USDT")
