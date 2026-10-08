import sys
import time
from lbank_client import LBankClient
import config

client = LBankClient(config.API_KEY, config.SECRET_KEY)

print('===============================')
print('BALANCE RECONCILIATION')
print('===============================')

balances = client.get_balances()
free = balances.get('free', {})
freeze = balances.get('freeze', {})

usdt_free = free.get('USDT', 0.0)
usdt_locked = freeze.get('USDT', 0.0)
usdt_total = usdt_free + usdt_locked

exbt_free = free.get('EXBT', 0.0)
exbt_locked = freeze.get('EXBT', 0.0)
exbt_total = exbt_free + exbt_locked

print(f'\nUSDT Total: {usdt_total}')
print(f'USDT Free: {usdt_free}')
print(f'USDT Locked: {usdt_locked}')

print(f'\nEXBT Total: {exbt_total}')
print(f'EXBT Free: {exbt_free}')
print(f'EXBT Locked: {exbt_locked}')

print('\nLBank EXBT_USDT Open Orders:')
try:
    orders = client.get_open_orders('exbt_usdt')
except Exception as e:
    print(f'Error fetching orders: {e}')
    orders = []

usdt_locked_by_orders = 0.0
exbt_locked_by_orders = 0.0

for o in orders:
    side = o.get('type', 'unknown')
    price = float(o.get('price', 0))
    amount = float(o.get('amount', 0))
    print(f"Order ID: {o.get('order_id')}")
    print(f"Side: {side}")
    print(f"Price: {price}")
    print(f"Amount: {amount}")
    
    if side == 'buy':
        locked_usdt = price * amount
        usdt_locked_by_orders += locked_usdt
        print(f"Estimated Locked Asset: USDT")
        print(f"Estimated Locked Amount: {locked_usdt}")
    elif side == 'sell':
        locked_exbt = amount
        exbt_locked_by_orders += locked_exbt
        print(f"Estimated Locked Asset: EXBT")
        print(f"Estimated Locked Amount: {locked_exbt}")
    print('---')

print(f'\nUSDT locked by identified orders: {usdt_locked_by_orders}')
print(f'EXBT locked by identified orders: {exbt_locked_by_orders}')
print(f'Unexplained USDT lock: {usdt_locked - usdt_locked_by_orders}')
print(f'Unexplained EXBT lock: {exbt_locked - exbt_locked_by_orders}')
print('===============================')
