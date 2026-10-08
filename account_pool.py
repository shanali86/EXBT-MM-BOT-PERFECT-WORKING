# ==============================================================================
#  EXBT Multi-Account Worker Pool
#  Allows rotating trades dynamically across 4, 5, or up to 14 LBank accounts.
#  Ensures 100% decentralized tape appearance with zero self-trade crossings.
# ==============================================================================

import random
import logging
from typing import List, Dict, Tuple, Optional
from lbank_client import LBankClient
import config

logger = logging.getLogger("account_pool")

# ──────────────────────────────────────────────────────────────────────────────
# ACCOUNT POOL CONFIGURATION
# Add Account C, D, E, etc. as they become available.
# ──────────────────────────────────────────────────────────────────────────────
POOL_ACCOUNTS_CONFIG = [
    {
        "id": "A",
        "name": "Account A (Primary MM)",
        "api_key": config.API_KEY,
        "secret_key": config.SECRET_KEY,
        "enabled": True,
    },
    {
        "id": "B",
        "name": "Account B (Secondary MM / Flow)",
        "api_key": config.API_KEY_B,
        "secret_key": config.SECRET_KEY_B,
        "enabled": True,
    },
    {
        "id": "C",
        "name": "Account C",
        "api_key": "YOUR_LBANK_API_KEY_C",
        "secret_key": "YOUR_LBANK_SECRET_KEY_C",
        "enabled": False,  # Set True when keys are pasted
    },
    {
        "id": "D",
        "name": "Account D",
        "api_key": "YOUR_LBANK_API_KEY_D",
        "secret_key": "YOUR_LBANK_SECRET_KEY_D",
        "enabled": False,  # Set True when keys are pasted
    },
    {
        "id": "E",
        "name": "Account E",
        "api_key": "YOUR_LBANK_API_KEY_E",
        "secret_key": "YOUR_LBANK_SECRET_KEY_E",
        "enabled": False,  # Set True when keys are pasted
    },
]


class AccountPool:
    def __init__(self, accounts_cfg: Optional[List[Dict]] = None):
        self.raw_configs = accounts_cfg or POOL_ACCOUNTS_CONFIG
        self.clients: Dict[str, LBankClient] = {}
        self.active_ids: List[str] = []
        self._initialize_clients()

    def _initialize_clients(self):
        for acc in self.raw_configs:
            acc_id = acc["id"]
            key = acc.get("api_key", "")
            sec = acc.get("secret_key", "")
            enabled = acc.get("enabled", False)

            if enabled and key and not key.startswith("YOUR_LBANK"):
                try:
                    client = LBankClient(key, sec, getattr(config, "USE_RSA", False))
                    self.clients[acc_id] = client
                    self.active_ids.append(acc_id)
                    logger.info(f"✅ Initialized Account [{acc_id}]: {acc.get('name')}")
                except Exception as e:
                    logger.error(f"Failed to initialize Account [{acc_id}]: {e}")

        logger.info(f"AccountPool ready with {len(self.active_ids)} active accounts: {self.active_ids}")

    def get_random_pair(self) -> Optional[Tuple[LBankClient, LBankClient, str, str]]:
        """
        Picks two distinct accounts from the pool for a matched trade.
        Returns: (seller_client, buyer_client, seller_id, buyer_id)
        Guarantees: seller_id != buyer_id
        """
        if len(self.active_ids) < 2:
            logger.warning("AccountPool requires at least 2 active accounts to match trades.")
            return None

        seller_id, buyer_id = random.sample(self.active_ids, 2)
        return self.clients[seller_id], self.clients[buyer_id], seller_id, buyer_id

    def get_all_balances(self) -> Dict[str, Dict[str, float]]:
        """Queries and returns USDT and EXBT balances for all active accounts."""
        balances = {}
        for acc_id, client in self.clients.items():
            try:
                u = client.get_balance("usdt")
                e = client.get_balance("exbt")
                balances[acc_id] = {"usdt": u, "exbt": e}
            except Exception as err:
                logger.error(f"Error fetching balance for {acc_id}: {err}")
                balances[acc_id] = {"usdt": 0.0, "exbt": 0.0}
        return balances


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pool = AccountPool()
    print("Active Account IDs:", pool.active_ids)
    if len(pool.active_ids) >= 2:
        s_c, b_c, s_id, b_id = pool.get_random_pair()
        print(f"Sample Random Pair: Seller = {s_id} | Buyer = {b_id}")
        print("Balances:", pool.get_all_balances())
