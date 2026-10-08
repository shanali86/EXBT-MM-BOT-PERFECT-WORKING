import json
import sys
import datetime

sys.path.append("/root/exbt_mm_bot")
import config
from lbank_client import LBankClient

def main():
    cA = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
    cB = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)

    # Let's inspect trade history with all prices
    for name, c in [("Account A", cA), ("Account B", cB)]:
        print(f"\n=================== {name} ===================")
        page = 1
        trades = []
        while page <= 25:
            try:
                res = c._post("/v2/transaction_history.do", {
                    "symbol": config.SYMBOL,
                    "current_page": str(page),
                    "page_length": "100"
                })
                b = res.get("data", [])
                if not b:
                    break
                trades.extend(b)
                page += 1
            except Exception as e:
                break
        
        print(f"Total trades fetched: {len(trades)}")
        if not trades:
            continue
        
        # Breakdown by trade type
        buys = [t for t in trades if "buy" in str(t.get("tradeType")).lower()]
        sells = [t for t in trades if "sell" in str(t.get("tradeType")).lower()]

        tot_buy_qty = sum(float(t.get("dealQuantity", 0)) for t in buys)
        tot_buy_vol = sum(float(t.get("dealVolumePrice", 0)) for t in buys)
        avg_buy_p = tot_buy_vol / tot_buy_qty if tot_buy_qty else 0

        tot_sell_qty = sum(float(t.get("dealQuantity", 0)) for t in sells)
        tot_sell_vol = sum(float(t.get("dealVolumePrice", 0)) for t in sells)
        avg_sell_p = tot_sell_vol / tot_sell_qty if tot_sell_qty else 0

        print(f"BUYS : {tot_buy_qty:,.2f} EXBT for ${tot_buy_vol:,.2f} USDT | Avg Price: {avg_buy_p:.4f} USDT")
        print(f"SELLS: {tot_sell_qty:,.2f} EXBT for ${tot_sell_vol:,.2f} USDT | Avg Price: {avg_sell_p:.4f} USDT")

if __name__ == "__main__":
    main()

