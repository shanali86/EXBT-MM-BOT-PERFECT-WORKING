import json
import sys
import datetime
from collections import defaultdict

sys.path.append("/root/exbt_mm_bot")
import config
from lbank_client import LBankClient

def fetch_all_trades(client, symbol, max_pages=100):
    all_trades = []
    page = 1
    while page <= max_pages:
        try:
            res = client._post("/v2/transaction_history.do", {
                "symbol": symbol,
                "current_page": str(page),
                "page_length": "100"
            })
            batch = res.get("data", [])
            if not batch:
                break
            all_trades.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
    return all_trades

def main():
    print("==================================================")
    print("DEEP LEDGER AUDIT: EXBT & USDT FULL FLOW")
    print("==================================================")

    cA = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
    cB = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)

    # 1. Current Live Balances
    bal_a = cA.get_balances()
    bal_b = cB.get_balances()

    free_a_u = bal_a.get("free", {}).get("USDT", 0.0)
    frz_a_u = bal_a.get("freeze", {}).get("USDT", 0.0)
    free_a_e = bal_a.get("free", {}).get("EXBT", 0.0)
    frz_a_e = bal_a.get("freeze", {}).get("EXBT", 0.0)

    free_b_u = bal_b.get("free", {}).get("USDT", 0.0)
    frz_b_u = bal_b.get("freeze", {}).get("USDT", 0.0)
    free_b_e = bal_b.get("free", {}).get("EXBT", 0.0)
    frz_b_e = bal_b.get("freeze", {}).get("EXBT", 0.0)

    tot_a_u = free_a_u + frz_a_u
    tot_a_e = free_a_e + frz_a_e
    tot_b_u = free_b_u + frz_b_u
    tot_b_e = free_b_e + frz_b_e

    tot_comb_u = tot_a_u + tot_b_u
    tot_comb_e = tot_a_e + tot_b_e

    print("\n[1] CURRENT LIVE EXCHANGE BALANCES (RIGHT NOW):")
    print(f"Account A: {tot_a_u:,.2f} USDT (Free: {free_a_u:,.2f}, Locked: {frz_a_u:,.2f}) | {tot_a_e:,.2f} EXBT")
    print(f"Account B: {tot_b_u:,.2f} USDT (Free: {free_b_u:,.2f}, Locked: {frz_b_u:,.2f}) | {tot_b_e:,.2f} EXBT")
    print(f"Combined : {tot_comb_u:,.2f} USDT | {tot_comb_e:,.2f} EXBT")

    # 2. Deposits from On-Chain History
    print("\n[2] VERIFIED ON-CHAIN DEPOSITS:")
    dep_a = cA._post("/v2/supplement/deposit_history.do", {"page_length": "100", "current_page": "1"}).get("data", {}).get("depositOrders", [])
    dep_b = cB._post("/v2/supplement/deposit_history.do", {"page_length": "100", "current_page": "1"}).get("data", {}).get("depositOrders", [])

    print("Account A Deposits:")
    for d in dep_a:
        ts = datetime.datetime.fromtimestamp(d['insertTime']/1000.0).strftime('%Y-%m-%d %H:%M')
        print(f"  {ts} | {d['amount']} {d['coin'].upper()} ({d['networkName']}) | Tx: {d['txId'][:20]}...")

    print("Account B Deposits:")
    for d in dep_b:
        ts = datetime.datetime.fromtimestamp(d['insertTime']/1000.0).strftime('%Y-%m-%d %H:%M')
        print(f"  {ts} | {d['amount']} {d['coin'].upper()} ({d['networkName']}) | Tx: {d['txId'][:20]}...")

    # 3. Transaction History Analysis
    print("\n[3] FETCHING FULL TRADING HISTORY...")
    trades_a = fetch_all_trades(cA, config.SYMBOL)
    trades_b = fetch_all_trades(cB, config.SYMBOL)
    print(f"Fetched {len(trades_a)} trades for Account A, {len(trades_b)} trades for Account B.")

    # Pair matches to separate internal vs external
    # Account B trade key -> trade
    b_by_time_qty = defaultdict(list)
    for tb in trades_b:
        ts = tb.get("dealTime", 0) // 1000  # second resolution
        qty = round(float(tb.get("dealQuantity", 0)), 2)
        b_by_time_qty[(ts, qty)].append(tb)

    internal_count = 0
    external_buys_by_bot = []  # bot bought from outside (USDT OUT, EXBT IN)
    external_sells_by_bot = [] # bot sold to outside (EXBT OUT, USDT IN)

    for ta in trades_a:
        ts = ta.get("dealTime", 0) // 1000
        qty = round(float(ta.get("dealQuantity", 0)), 2)
        price = float(ta.get("dealPrice", 0))
        vol = float(ta.get("dealVolumePrice", 0))
        ttype = str(ta.get("tradeType", "")).lower()

        # Check if matched with Account B
        # E.g. A buy matches B sell, or A sell matches B buy
        matched_b = False
        candidates = b_by_time_qty.get((ts, qty), [])
        for cb in candidates:
            cb_ttype = str(cb.get("tradeType", "")).lower()
            if ("buy" in ttype and "sell" in cb_ttype) or ("sell" in ttype and "buy" in cb_ttype):
                matched_b = True
                candidates.remove(cb)
                break

        if matched_b:
            internal_count += 1
        else:
            # External trade on Account A!
            dt_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
            if "buy" in ttype:
                # Bot bought from external seller
                external_buys_by_bot.append({
                    "time": dt_str,
                    "account": "A",
                    "price": price,
                    "amount": qty,
                    "usdt_spent": vol
                })
            else:
                # Bot sold to external buyer
                external_sells_by_bot.append({
                    "time": dt_str,
                    "account": "A",
                    "price": price,
                    "amount": qty,
                    "usdt_received": vol
                })

    # Any remaining in B that did not match A
    for (ts, qty), rem_list in b_by_time_qty.items():
        for tb in rem_list:
            dt_str = datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M')
            price = float(tb.get("dealPrice", 0))
            vol = float(tb.get("dealVolumePrice", 0))
            ttype = str(tb.get("tradeType", "")).lower()
            if "buy" in ttype:
                external_buys_by_bot.append({
                    "time": dt_str,
                    "account": "B",
                    "price": price,
                    "amount": qty,
                    "usdt_spent": vol
                })
            else:
                external_sells_by_bot.append({
                    "time": dt_str,
                    "account": "B",
                    "price": price,
                    "amount": qty,
                    "usdt_received": vol
                })

    total_usdt_spent_on_buys = sum(x["usdt_spent"] for x in external_buys_by_bot)
    total_tokens_bought = sum(x["amount"] for x in external_buys_by_bot)

    total_usdt_received_from_sells = sum(x["usdt_received"] for x in external_sells_by_bot)
    total_tokens_sold = sum(x["amount"] for x in external_sells_by_bot)

    print("\n[4] EXTERNAL MARKET TRADES (WHERE REAL DOLLARS MOVED):")
    print(f"Total Internal Trades between A & B (Self-matching): {internal_count}")
    print(f"External Trades with Outside Users: {len(external_buys_by_bot) + len(external_sells_by_bot)}")
    print(f"  -> Outside Users SOLD to Bot: {len(external_buys_by_bot)} trades | {total_tokens_bought:,.2f} EXBT bought by bot")
    print(f"  -> Total USDT paid to outside sellers: ${total_usdt_spent_on_buys:,.2f} USDT")
    print(f"  -> Outside Users BOUGHT from Bot: {len(external_sells_by_bot)} trades | {total_tokens_sold:,.2f} EXBT sold by bot")
    print(f"  -> Total USDT collected from outside buyers: ${total_usdt_received_from_sells:,.2f} USDT")
    print(f"  -> NET CASH SPENT ABSORBING EXTERNAL SELLERS: ${total_usdt_spent_on_buys - total_usdt_received_from_sells:,.2f} USDT")

    # Date-wise breakdown of external buying
    by_date_spent = defaultdict(lambda: {"usdt": 0.0, "exbt": 0.0, "count": 0})
    for b in external_buys_by_bot:
        d = b["time"].split()[0]
        by_date_spent[d]["usdt"] += b["usdt_spent"]
        by_date_spent[d]["exbt"] += b["amount"]
        by_date_spent[d]["count"] += 1

    print("\n[5] DATE-BY-DATE EXACT BREAKDOWN OF WHERE DOLLARS WENT:")
    for d, stats in sorted(by_date_spent.items()):
        print(f"  Date {d}: Bot bought {stats['exbt']:,.2f} EXBT from outside users | Spent: ${stats['usdt']:,.2f} USDT ({stats['count']} trades)")

if __name__ == "__main__":
    main()

