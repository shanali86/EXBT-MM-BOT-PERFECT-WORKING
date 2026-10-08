import json
import sys
from collections import defaultdict

sys.path.append("/root/exbt_mm_bot")
import config
from lbank_client import LBankClient

def main():
    print("==================================================")
    print("EXBT/USDT ORDERBOOK DEPTH AUDIT: USER SELLING ORDERS")
    print("==================================================")

    cA = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
    cB = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)

    # 1. Fetch Open Orders for Account A & B
    orders_a = cA.get_open_orders(config.SYMBOL)
    orders_b = cB.get_open_orders(config.SYMBOL)

    bot_sell_prices = defaultdict(float)
    bot_buy_prices = defaultdict(float)

    for o in orders_a:
        side = str(o.get("type", o.get("side", ""))).lower()
        price = round(float(o.get("price", 0)), 4)
        amt = float(o.get("amount", o.get("origQty", 0)))
        if "sell" in side:
            bot_sell_prices[price] += amt
        elif "buy" in side:
            bot_buy_prices[price] += amt

    for o in orders_b:
        side = str(o.get("type", o.get("side", ""))).lower()
        price = round(float(o.get("price", 0)), 4)
        amt = float(o.get("amount", o.get("origQty", 0)))
        if "sell" in side:
            bot_sell_prices[price] += amt
        elif "buy" in side:
            bot_buy_prices[price] += amt

    tot_bot_sells = sum(bot_sell_prices.values())
    tot_bot_buys = sum(bot_buy_prices.values())

    print(f"\n[1] BOT'S OWN ORDERS ON THE BOOK:")
    print(f"Bot Active SELL Orders: {tot_bot_sells:,.2f} EXBT across {len(bot_sell_prices)} price levels")
    print(f"Bot Active BUY Orders : {tot_bot_buys:,.2f} EXBT across {len(bot_buy_prices)} price levels")

    # 2. Fetch Full Public Orderbook Depth (Up to 100 levels)
    ob = cA.get_orderbook(config.SYMBOL, size=100)
    raw_asks = ob.get("asks", [])
    raw_bids = ob.get("bids", [])

    print(f"\n[2] FULL PUBLIC ORDERBOOK DEPTH:")
    print(f"Total Ask Levels: {len(raw_asks)} | Total Bid Levels: {len(raw_bids)}")

    # 3. Analyze Sell Side (Asks)
    user_sells = []
    tot_user_sell_exbt = 0.0
    tot_user_sell_usdt = 0.0

    # Categorize by price ranges
    ranges = {
        "0.26 - 0.28": {"exbt": 0.0, "usdt": 0.0, "count": 0},
        "0.28 - 0.30": {"exbt": 0.0, "usdt": 0.0, "count": 0},
        "0.30 - 0.35": {"exbt": 0.0, "usdt": 0.0, "count": 0},
        "0.35 - 0.40": {"exbt": 0.0, "usdt": 0.0, "count": 0},
        "0.40 - 0.50": {"exbt": 0.0, "usdt": 0.0, "count": 0},
        "0.50+":       {"exbt": 0.0, "usdt": 0.0, "count": 0},
    }

    for a in raw_asks:
        price = float(a[0])
        amt = float(a[1])
        pr_round = round(price, 4)

        # Check how much of this level belongs to bot
        bot_amt = bot_sell_prices.get(pr_round, 0.0)
        user_amt = max(0.0, amt - bot_amt)

        if user_amt > 1e-4:
            val_usdt = user_amt * price
            tot_user_sell_exbt += user_amt
            tot_user_sell_usdt += val_usdt
            user_sells.append((price, user_amt, val_usdt))

            if price < 0.28:
                r_key = "0.26 - 0.28"
            elif price < 0.30:
                r_key = "0.28 - 0.30"
            elif price < 0.35:
                r_key = "0.30 - 0.35"
            elif price < 0.40:
                r_key = "0.35 - 0.40"
            elif price < 0.50:
                r_key = "0.40 - 0.50"
            else:
                r_key = "0.50+"

            ranges[r_key]["exbt"] += user_amt
            ranges[r_key]["usdt"] += val_usdt
            ranges[r_key]["count"] += 1

    print(f"\n[3] EXTERNAL USERS SELLING ORDERS SUMMARY:")
    print(f"Total External Users Selling EXBT: {tot_user_sell_exbt:,.2f} EXBT")
    print(f"Total USDT Required to Buy Them All: ${tot_user_sell_usdt:,.2f} USDT")

    print("\n--- Price Range Breakdown of Users' Sell Orders ---")
    for r_name, r_data in ranges.items():
        if r_data["exbt"] > 0:
            print(f"  Range [{r_name}]: {r_data['exbt']:>10,.2f} EXBT (~${r_data['usdt']:>8,.2f} USDT) across {r_data['count']} orders")

    print("\n--- Individual User Sell Orders (Top 25 Closest to Market) ---")
    for p, amt, val in user_sells[:25]:
        print(f"  Price: {p:.4f} USDT | Amount: {amt:>9,.2f} EXBT | Value: ${val:>8,.2f} USDT")

if __name__ == "__main__":
    main()
