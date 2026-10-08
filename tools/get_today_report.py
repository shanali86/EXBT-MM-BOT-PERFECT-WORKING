import json
import sys
import datetime

sys.path.append("/root/exbt_mm_bot")
import config
from lbank_client import LBankClient

def main():
    print("==================================================")
    print("TODAY'S TRADING REPORT & SELLS AUDIT (2026-10-06)")
    print("==================================================")

    cA = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
    cB = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)

    # 1. Fetch public trade tape (/v2/trades.do)
    print("\n[1] LATEST MARKET TRADES ON THE TAPE (WHO TRADED RECENTLY):")
    try:
        tape_res = cA._get(f"/v2/trades.do?symbol={config.SYMBOL}&size=30")
        tape = tape_res.get("data", [])
        if tape:
            for t in tape[:15]:
                dt = datetime.datetime.fromtimestamp(t['date_ms']/1000.0).strftime('%Y-%m-%d %H:%M:%S')
                ttype = t.get('type', '').upper()
                amt = float(t.get('amount', 0))
                p = float(t.get('price', 0))
                val = amt * p
                print(f"  {dt} | {ttype:<4} {amt:>8,.2f} EXBT @ {p:.4f} USDT (${val:>6.2f}) | TID: {t.get('tid')}")
        else:
            print("  No recent public trades on tape.")
    except Exception as e:
        print(f"  Error fetching public tape: {e}")

    # 2. Fetch Account A & B deals for Today (2026-10-06)
    target_date = "2026-10-06"
    account_stats = {}
    today_sells_against_bot = [] # someone sold to bot (bot bought)
    today_buys_from_bot = []     # someone bought from bot (bot sold)

    for name, c in [("Account A", cA), ("Account B", cB)]:
        page = 1
        trades_today = []
        while page <= 50:
            try:
                res = c._post("/v2/transaction_history.do", {
                    "symbol": config.SYMBOL,
                    "current_page": str(page),
                    "page_length": "100"
                })
                data = res.get("data", [])
                if not data:
                    break
                
                reached_earlier = False
                for t in data:
                    ts = t.get("dealTime", 0) / 1000.0
                    dt = datetime.datetime.fromtimestamp(ts)
                    d_str = dt.strftime("%Y-%m-%d")
                    if d_str == target_date:
                        trades_today.append(t)
                        # Check trade details
                        ttype = str(t.get("tradeType", "")).lower()
                        qty = float(t.get("dealQuantity", 0))
                        price = float(t.get("dealPrice", 0))
                        vol = float(t.get("dealVolumePrice", 0))
                        dt_full = dt.strftime('%Y-%m-%d %H:%M:%S')
                        
                        if "buy" in ttype:
                            # Bot was buyer -> external user sold to bot
                            today_sells_against_bot.append({
                                "account": name,
                                "time": dt_full,
                                "price": price,
                                "amount": qty,
                                "usdt": vol
                            })
                        else:
                            # Bot was seller -> external user bought from bot
                            today_buys_from_bot.append({
                                "account": name,
                                "time": dt_full,
                                "price": price,
                                "amount": qty,
                                "usdt": vol
                            })
                    elif d_str < target_date:
                        reached_earlier = True
                
                if reached_earlier:
                    break
                page += 1
            except Exception as e:
                print(f"Error fetching page {page} for {name}: {e}")
                break

        buys = [t for t in trades_today if "buy" in str(t.get("tradeType")).lower()]
        sells = [t for t in trades_today if "sell" in str(t.get("tradeType")).lower()]

        buy_qty = sum(float(t.get("dealQuantity", 0)) for t in buys)
        buy_usdt = sum(float(t.get("dealVolumePrice", 0)) for t in buys)
        sell_qty = sum(float(t.get("dealQuantity", 0)) for t in sells)
        sell_usdt = sum(float(t.get("dealVolumePrice", 0)) for t in sells)
        fees = sum(float(t.get("tradeFee", 0)) for t in trades_today)

        account_stats[name] = {
            "total_trades": len(trades_today),
            "buys_count": len(buys),
            "sells_count": len(sells),
            "buy_qty": buy_qty,
            "buy_usdt": buy_usdt,
            "sell_qty": sell_qty,
            "sell_usdt": sell_usdt,
            "fees": fees,
            "net_exbt": buy_qty - sell_qty,
            "net_usdt": sell_usdt - buy_usdt
        }

    # Summary
    stA = account_stats["Account A"]
    stB = account_stats["Account B"]
    comb_trades = stA['total_trades'] + stB['total_trades']
    comb_vol_exbt = (stA['buy_qty'] + stA['sell_qty'] + stB['buy_qty'] + stB['sell_qty']) / 2.0
    comb_to_usdt = (stA['buy_usdt'] + stA['sell_usdt'] + stB['buy_usdt'] + stB['sell_usdt']) / 2.0
    comb_net_exbt = stA['net_exbt'] + stB['net_exbt']
    comb_net_usdt = stA['net_usdt'] + stB['net_usdt']

    print("\n[2] TODAY'S TOTALS (2026-10-06):")
    print(f"Total Trades Today: {comb_trades}")
    print(f"Total Executed Volume Today: {comb_vol_exbt:,.2f} EXBT (~${comb_to_usdt:,.2f} USDT)")
    print(f"Net EXBT Change Today : {comb_net_exbt:+,.2f} EXBT")
    print(f"Net USDT Cash Change  : ${comb_net_usdt:+,.2f} USDT")

    # Detail of sells against bot today
    print(f"\n[3] WHO SOLD TO THE BOT TODAY (USER SELLS INTO BOT BIDS):")
    print(f"Total Selling Events Against Bot Today: {len(today_sells_against_bot)}")
    tot_sold_by_users = sum(s['amount'] for s in today_sells_against_bot)
    tot_usdt_taken_by_users = sum(s['usdt'] for s in today_sells_against_bot)
    print(f"Total EXBT Dumped/Sold by Users Today: {tot_sold_by_users:,.2f} EXBT (${tot_usdt_taken_by_users:,.2f} USDT)")

    if today_sells_against_bot:
        print("\nLast 15 User Sell Trades Against Bot Today:")
        for s in today_sells_against_bot[:15]:
            print(f"  {s['time']} | {s['account']} bought {s['amount']:>8,.2f} EXBT @ {s['price']:.4f} (User took ${s['usdt']:>6.2f} USDT)")
    else:
        print("  NO users sold into bot bids today!")

    # 4. Current Live Balances
    bal_a = cA.get_balances()
    bal_b = cB.get_balances()
    print("\n[4] CURRENT LIVE BALANCES RIGHT NOW:")
    print(f"Account A: {bal_a.get('free', {}).get('USDT', 0):,.2f} Free USDT | {bal_a.get('free', {}).get('EXBT', 0):,.2f} Free EXBT")
    print(f"Account B: {bal_b.get('free', {}).get('USDT', 0):,.2f} Free USDT | {bal_b.get('free', {}).get('EXBT', 0):,.2f} Free EXBT")

if __name__ == "__main__":
    main()
