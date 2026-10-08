import threading
import logging

logger = logging.getLogger("budget_manager")

class BudgetManager:
    def __init__(self, client):
        self.client = client
        self.lock = threading.Lock()
        self.balances = {"free": {}, "freeze": {}}
        self.reservations = {
            "MM": {"USDT": 0.0, "EXBT": 0.0},
            "VOLUME": {"USDT": 0.0, "EXBT": 0.0},
            "CANDLE": {"USDT": 0.0, "EXBT": 0.0}
        }

    def refresh_balances(self):
        with self.lock:
            try:
                self.balances = self.client.get_balances()
                
                logger.info("LBank response status: SUCCESS")
                usdt_f = self.balances["free"].get("USDT", 0.0)
                usdt_l = self.balances["freeze"].get("USDT", 0.0)
                exbt_f = self.balances["free"].get("EXBT", 0.0)
                exbt_l = self.balances["freeze"].get("EXBT", 0.0)
                
                self.balances["status"] = "SUCCESS"
                
            except Exception as e:
                logger.error(f"LBank Balance API: FAILED ({e})")
                self.balances = {"free": {}, "freeze": {}, "status": "BALANCE_UNKNOWN"}

    def reconcile_reservations(self, mm_active_buys_usdt, mm_active_sells_exbt):
        """
        Reconcile internal reservations with actual open orders.
        Call this after fetching open orders from exchange.
        """
        with self.lock:
            self.reservations["MM"]["USDT"] = float(mm_active_buys_usdt)
            self.reservations["MM"]["EXBT"] = float(mm_active_sells_exbt)
            logger.info(f"Reconciled MM Reservations: {self.reservations['MM']['USDT']} USDT | {self.reservations['MM']['EXBT']} EXBT")

    def reserve_budget(self, bot_name: str, asset: str, amount: float) -> bool:
        """Attempt to reserve budget for an order before placement."""
        with self.lock:
            alloc = self._calculate_allocation_nolock(asset)
            available = alloc[bot_name]
            if amount <= available:
                self.reservations[bot_name][asset] += amount
                logger.debug(f"{bot_name} reserved {amount} {asset}")
                return True
            return False

    def release_budget(self, bot_name: str, asset: str, amount: float):
        """Release budget after order cancel or fill."""
        with self.lock:
            self.reservations[bot_name][asset] = max(0.0, self.reservations[bot_name][asset] - amount)
            logger.debug(f"{bot_name} released {amount} {asset}")

    def _calculate_allocation_nolock(self, asset: str) -> dict:
        if self.balances.get("status") == "BALANCE_UNKNOWN":
            return {"MM": 0.0, "VOLUME": 0.0, "CANDLE": 0.0, "RESERVE": 0.0, "TOTAL": 0.0, "FREE_ACTUAL": 0.0, "MODE": "NORMAL", "LOCKED_PCT": 0.0}

        free = self.balances.get("free", {}).get(asset, 0.0)
        freeze = self.balances.get("freeze", {}).get(asset, 0.0)
        total = free + freeze

        if total <= 0:
            return {"MM": 0.0, "VOLUME": 0.0, "CANDLE": 0.0, "RESERVE": 0.0, "TOTAL": 0.0, "FREE_ACTUAL": 0.0, "MODE": "NORMAL", "LOCKED_PCT": 0.0}

        # Internally reserved by our active orders
        mm_res = self.reservations["MM"][asset]
        vol_res = self.reservations["VOLUME"][asset]
        candle_res = self.reservations["CANDLE"][asset]

        # Our "real" free universe is the actual free balance PLUS the funds currently locked by OUR bot's orders.
        # This prevents the budget from recursively shrinking when we place orders, 
        # while strictly ignoring the 9372 USDT external manual freeze.
        usable_balance = free + mm_res + vol_res + candle_res

        mm_limit = usable_balance * 0.50
        vol_limit = usable_balance * 0.35
        candle_limit = usable_balance * 0.15

        mm_rem_cap = max(0.0, mm_limit - mm_res)
        vol_rem_cap = max(0.0, vol_limit - vol_res)
        candle_rem_cap = max(0.0, candle_limit - candle_res)

        # Distribute actual free balance safely
        available_to_allocate = free
        
        # Candle gets priority for its share of the free balance
        res_alloc = min(candle_rem_cap, available_to_allocate)
        available_to_allocate -= res_alloc
        
        vol_alloc = min(vol_rem_cap, available_to_allocate)
        available_to_allocate -= vol_alloc
        
        mm_alloc = min(mm_rem_cap, available_to_allocate)

        return {
            "MM": mm_alloc,
            "VOLUME": vol_alloc,
            "CANDLE": res_alloc,
            "RESERVE": res_alloc,
            "MM_USED": mm_res,
            "VOLUME_USED": vol_res,
            "CANDLE_USED": candle_res,
            "TOTAL": total,
            "FREE_ACTUAL": free,
            "MODE": "NORMAL",
            "LOCKED_PCT": 0.0
        }

    def get_allocation(self, asset: str) -> dict:
        with self.lock:
            return self._calculate_allocation_nolock(asset)
