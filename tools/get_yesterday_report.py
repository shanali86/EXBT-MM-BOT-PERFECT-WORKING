import json
import sys
import datetime
from collections import defaultdict

sys.path.append("/root/exbt_mm_bot")
import config
from lbank_client import LBankClient

def main():
    print("==================================================")
    print("YESTERDAY'S TRADING REPORT (DATE: 2026-10-05)")
    print("==================================================")

    cA = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
    cB = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)

    # 1. Fetch trades for 2026-10-05
    # Target date: 2026-10-05 (UTC)
    target_date = "2026-10-05"

    account_stats = {}
    for name, c in [("Account A", cA), ("Account B", cB)]:
        page = 1
        trades_yesterday = []
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
                    dt = datetime.datetime.utcfromtimestamp(ts)
                    d_str = dt.strftime("%Y-%m-%d")
                    if d_str == target_date:
                        trades_yesterday.append(t)
                    elif d_str < target_date:
                        reached_earlier = True
                
                if reached_earlier:
                    break
                page += 1
            except Exception as e:
                print(f"Error fetching page {page} for {name}: {e}")
                break

        # Analyze trades_yesterday
        buys = [t for t in trades_yesterday if "buy" in str(t.get("tradeType")).lower()]
        sells = [t for t in trades_yesterday if "sell" in str(t.get("tradeType")).lower()]

        buy_qty = sum(float(t.get("dealQuantity", 0)) for t in buys)
        buy_usdt = sum(float(t.get("dealVolumePrice", 0)) for t in buys)
        sell_qty = sum(float(t.get("dealQuantity", 0)) for t in sells)
        sell_usdt = sum(float(t.get("dealVolumePrice", 0)) for t in sells)
        fees = sum(float(t.get("tradeFee", 0)) for t in trades_yesterday)

        prices = [float(t.get("dealPrice", 0)) for t in trades_yesterday if float(t.get("dealPrice", 0)) > 0]
        high_p = max(prices) if prices else 0.0
        low_p = min(prices) if prices else 0.0
        avg_buy_p = buy_usdt / buy_qty if buy_qty > 0 else 0.0
        avg_sell_p = sell_usdt / sell_qty if sell_qty > 0 else 0.0

        account_stats[name] = {
            "total_trades": len(trades_yesterday),
            "buys_count": len(buys),
            "sells_count": len(sells),
            "buy_qty": buy_qty,
            "buy_usdt": buy_usdt,
            "sell_qty": sell_qty,
            "sell_usdt": sell_usdt,
            "fees": fees,
            "high": high_p,
            "low": low_p,
            "avg_buy_price": avg_buy_p,
            "avg_sell_price": avg_sell_p,
            "net_exbt": buy_qty - sell_qty,
            "net_usdt": sell_usdt - buy_usdt
        }

    print("\n--- Account A (Main MM) Yesterday ---")
    stA = account_stats["Account A"]
    print(f"Trades: {stA['total_trades']} ({stA['buys_count']} buys, {stA['sells_count']} sells)")
    print(f"Bought : {stA['buy_qty']:,.2f} EXBT for ${stA['buy_usdt']:,.2f} USDT (Avg: {stA['avg_buy_price']:.4f})")
    print(f"Sold   : {stA['sell_qty']:,.2f} EXBT for ${stA['sell_usdt']:,.2f} USDT (Avg: {stA['avg_sell_price']:.4f})")
    print(f"Net EXBT Change : {stA['net_exbt']:+,.2f} EXBT")
    print(f"Net USDT Change : ${stA['net_usdt']:+,.2f} USDT")
    print(f"Fees Paid       : ${stA['fees']:.4f} USDT")

    print("\n--- Account B (Volume/Candle) Yesterday ---")
    stB = account_stats["Account B"]
    print(f"Trades: {stB['total_trades']} ({stB['buys_count']} buys, {stB['sells_count']} sells)")
    print(f"Bought : {stB['buy_qty']:,.2f} EXBT for ${stB['buy_usdt']:,.2f} USDT (Avg: {stB['avg_buy_price']:.4f})")
    print(f"Sold   : {stB['sell_qty']:,.2f} EXBT for ${stB['sell_usdt']:,.2f} USDT (Avg: {stB['avg_sell_price']:.4f})")
    print(f"Net EXBT Change : {stB['net_exbt']:+,.2f} EXBT")
    print(f"Net USDT Change : ${stB['net_usdt']:+,.2f} USDT")
    print(f"Fees Paid       : ${stB['fees']:.4f} USDT")

    # Combined Totals
    comb_trades = stA['total_trades'] + stB['total_trades']
    comb_volume_exbt = (stA['buy_qty'] + stA['sell_qty'] + stB['buy_qty'] + stB['sell_qty']) / 2.0
    comb_turnover_usdt = (stA['buy_usdt'] + stA['sell_usdt'] + stB['buy_usdt'] + stB['sell_usdt']) / 2.0
    comb_net_exbt = stA['net_exbt'] + stB['net_exbt']
    comb_net_usdt = stA['net_usdt'] + stB['net_usdt']
    comb_fees = stA['fees'] + stB['fees']
    all_prices = [p for p in [stA['high'], stB['high'], stA['low'], stB['low']] if p > 0]
    high_all = max(all_prices) if all_prices else 0.27
    low_all = min(all_prices) if all_prices else 0.26

    print("\n==================================================")
    print("COMBINED PORTFOLIO YESTERDAY (2026-10-05 TOTALS):")
    print("==================================================")
    print(f"Total Combined Trades : {comb_trades}")
    print(f"Total Executed Volume : {comb_volume_exbt:,.2f} EXBT")
    print(f"Total Market Turnover : ${comb_turnover_usdt:,.2f} USDT")
    print(f"Price Corridor Bounds : Low {low_all:.4f} - High {high_all:.4f} USDT")
    print(f"Net EXBT Added to Bot : {comb_net_exbt:+,.2f} EXBT")
    print(f"Net USDT Cash Change  : ${comb_net_usdt:+,.2f} USDT")
    print(f"Total Trading Fees    : ${comb_fees:.4f} USDT")

if __name__ == "__main__":
    main()
