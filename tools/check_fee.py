import sys
sys.path.append('/root/exbt_mm_bot')
from lbank_client import LBankClient
import config

cb = LBankClient(config.API_KEY_B, config.SECRET_KEY_B)
# Get transaction history / order status
orders = cb.get_open_orders(config.SYMBOL)
# Let's check user info or restrictions to see fee rate
info = cb._post("/v2/user_info.do", {})
print("Account B User Info / Fees:")
print(info)
