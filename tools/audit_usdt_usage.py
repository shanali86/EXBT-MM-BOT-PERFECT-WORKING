import json
import os
import sys
import datetime

sys.path.append("/root/exbt_mm_bot")
import config
from lbank_client import LBankClient

def main():
    print("==================================================")
    print("FORENSIC USDT USAGE AUDIT")
    print("==================================================")

    # 1. Check external_trades.json
    ext_file = "/root/exbt_mm_bot/data/external_trades.json"
    if os.path.exists(ext_file):
        try:
            with open(ext_file, "r") as f:
                ext_trades = json.load(f)
            print(f"External Trades File: {len(ext_trades)} recorded entries.")
            
            total_ext_bought_exbt = sum(float(t.get("amount", t.get("dealQuantity", 0))) for t in ext_trades if "buy" in str(t.get("type", t.get("tradeType", ""))).lower())
            total_ext_spent_usdt = sum(float(t.get("volume", t.get("dealVolumePrice", 0))) for t in ext_trades if "buy" in str(t.get("type", t.get("tradeType", ""))).lower())

            total_ext_sold_exbt = sum(float(t.get("amount", t.get("dealQuantity", 0))) for t in ext_trades if "sell" in str(t.get("type", t.get("tradeType", ""))).lower())
            total_ext_recv_usdt = sum(float(t.get("volume", t.get("dealVolumePrice", 0))) for t in ext_trades if "sell" in str(t.get("type", t.get("tradeType", ""))).lower())

            print(f"External Tokens Bought by Bot: {total_ext_bought_exbt:,.2f} EXBT")
            print(f"USDT Paid to External Sellers: ${total_ext_spent_usdt:,.2f} USDT")
            print(f"External Tokens Sold by Bot  : {total_ext_sold_exbt:,.2f} EXBT")
            print(f"USDT Received from Buyers    : ${total_ext_recv_usdt:,.2f} USDT")
            print(f"Net USDT Paid to Outside     : ${total_ext_spent_usdt - total_ext_recv_usdt:,.2f} USDT")
        except Exception as e:
            print("Error reading external_trades.json:", e)

    # 2. Check Daily Reports Breakdown
    rep_file = "/root/exbt_mm_bot/data/daily_reports.json"
    if os.path.exists(rep_file):
        try:
            with open(rep_file, "r") as f:
                reps = json.load(f)
            print("\n--- Daily Reports Day-by-Day USDT Flow ---")
            for r in reps:
                d = r.get("date")
                comb = r.get("combined", {})
                start_u = comb.get("starting_usdt", 0)
                end_u = comb.get("ending_usdt", 0)
                net_u = comb.get("net_usdt", 0)
                net_e = comb.get("net_exbt", 0)
                notes = r.get("notes", "")
                perf = r.get("performance", {})
                dumped = perf.get("external_sells_dumped", 0)
                print(f"Date: {d} | Start USDT: ${start_u:,.2f} -> End USDT: ${end_u:,.2f} | Net USDT: ${net_u:+,.2f} | Net EXBT: {net_e:+,.2f}")
                print(f"   Notes: {notes}")
                if dumped:
                    print(f"   External Sellers Dumped: {dumped:,.2f} EXBT")
        except Exception as e:
            print("Error reading daily_reports.json:", e)

    # 3. Live balances and active locked USDT
    cA = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
    cB = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)
    bal_a = cA.get_balances()
    bal_b = cB.get_balances()

    free_a_u = bal_a.get("free", {}).get("USDT", 0.0)
    frz_a_u = bal_a.get("freeze", {}).get("USDT", 0.0)
    free_b_u = bal_b.get("free", {}).get("USDT", 0.0)
    frz_b_u = bal_b.get("freeze", {}).get("USDT", 0.0)

    print("\n--- Current USDT Balances ---")
    print(f"Account A Free USDT  : ${free_a_u:,.2f}")
    print(f"Account A Locked USDT: ${frz_a_u:,.2f} (in open buy orders)")
    print(f"Account B Free USDT  : ${free_b_u:,.2f}")
    print(f"Account B Locked USDT: ${frz_b_u:,.2f} (in open buy orders)")
    print(f"Total USDT Cash      : ${free_a_u + frz_a_u + free_b_u + frz_b_u:,.2f}")

if __name__ == "__main__":
    main()
