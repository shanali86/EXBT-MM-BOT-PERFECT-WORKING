import sys
import os
import json
import time
import datetime
import requests

sys.path.insert(0, '/root/exbt_mm_bot')

from lbank_client import LBankClient
import config

def get_full_report():
    ca = LBankClient(config.API_KEY, config.SECRET_KEY)
    cb = LBankClient(config.API_KEY_B, config.SECRET_KEY_B)
    
    # 1. Balances
    bal_a_u = ca.get_balance("usdt")
    bal_a_e = ca.get_balance("exbt")
    bal_b_u = cb.get_balance("usdt")
    bal_b_e = cb.get_balance("exbt")
    
    # 2. Open orders
    oa = ca.get_open_orders(config.SYMBOL) or []
    ob = cb.get_open_orders(config.SYMBOL) or []
    
    locked_a_u = sum(float(o.get('price', 0)) * float(o.get('amount', 0)) for o in oa if 'buy' in str(o.get('type','')).lower())
    locked_a_e = sum(float(o.get('amount', 0)) for o in oa if 'sell' in str(o.get('type','')).lower())
    
    locked_b_u = sum(float(o.get('price', 0)) * float(o.get('amount', 0)) for o in ob if 'buy' in str(o.get('type','')).lower())
    locked_b_e = sum(float(o.get('amount', 0)) for o in ob if 'sell' in str(o.get('type','')).lower())
    
    total_usdt = bal_a_u + bal_b_u + locked_a_u + locked_b_u
    total_exbt = bal_a_e + bal_b_e + locked_a_e + locked_b_e
    
    # 3. Market Ticker
    ticker = {}
    try:
        r = requests.get('https://api.lbkex.com/v2/ticker.do?symbol=exbt_usdt', timeout=8).json()
        ticker = r.get('data', [{}])[0].get('ticker', {})
    except Exception as e:
        ticker = {"error": str(e)}

    # Baseline yesterday (Oct 7, 2026 ~15:23 UTC / 20:23 PST)
    yesterday_usdt = 10690.10
    yesterday_exbt = 177530.18
    yesterday_vol_exbt = 16002.46
    yesterday_vol_usdt = 4725.54
    yesterday_price = 0.3272
    
    diff_usdt = total_usdt - yesterday_usdt
    diff_exbt = total_exbt - yesterday_exbt

    report = {
        "server_time_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "server_time_pst": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5)).strftime("%Y-%m-%d %I:%M:%S %p PST"),
        "yesterday_baseline": {
            "total_usdt": yesterday_usdt,
            "total_exbt": yesterday_exbt,
            "price": yesterday_price,
            "vol_exbt": yesterday_vol_exbt,
            "vol_usdt": yesterday_vol_usdt
        },
        "today_current": {
            "account_a": {
                "usdt_free": round(bal_a_u, 4),
                "usdt_locked": round(locked_a_u, 4),
                "exbt_free": round(bal_a_e, 4),
                "exbt_locked": round(locked_a_e, 4),
                "open_orders": len(oa)
            },
            "account_b": {
                "usdt_free": round(bal_b_u, 4),
                "usdt_locked": round(locked_b_u, 4),
                "exbt_free": round(bal_b_e, 4),
                "exbt_locked": round(locked_b_e, 4),
                "open_orders": len(ob)
            },
            "total_usdt": round(total_usdt, 4),
            "total_exbt": round(total_exbt, 4),
            "diff_usdt": round(diff_usdt, 4),
            "diff_exbt": round(diff_exbt, 4)
        },
        "market": {
            "latest_price": ticker.get('latest'),
            "high": ticker.get('high'),
            "low": ticker.get('low'),
            "change_pct": ticker.get('change'),
            "vol_exbt_24h": ticker.get('vol'),
            "turnover_usdt_24h": ticker.get('turnover')
        }
    }
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    get_full_report()

