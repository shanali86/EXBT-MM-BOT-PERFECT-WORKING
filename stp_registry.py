"""
stp_registry.py — Central Self-Trade Prevention Registry
Singleton registry tracking all active orders for controlled accounts (A and B).
Validates every prospective order against counterparties to strictly prevent
self-matching, wash-trading, and spread-crossing.
"""

import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("stp_registry")


@dataclass
class RegisteredOrder:
    order_id: str
    account: str
    side: str        # 'buy' or 'sell'
    price: float
    size: float
    custom_id: str = ""
    timestamp: float = field(default_factory=lambda: 0.0)


class STPRegistry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(STPRegistry, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.orders: Dict[str, RegisteredOrder] = {}  # order_id -> RegisteredOrder
        self.order_lock = threading.RLock()
        self.prevented_count = 0
        self._initialized = True
        logger.info("Self-Trade Prevention (STP) Central Registry initialized.")

    def register_order(
        self,
        account: str,
        order_id: str,
        side: str,
        price: float,
        size: float,
        custom_id: str = ""
    ) -> None:
        """Register an active exchange order in the STP ledger."""
        with self.order_lock:
            self.orders[str(order_id)] = RegisteredOrder(
                order_id=str(order_id),
                account=account.upper(),
                side=side.lower(),
                price=float(price),
                size=float(size),
                custom_id=custom_id
            )

    def remove_order(self, order_id: str) -> bool:
        """Remove a cancelled or filled order from the STP ledger."""
        with self.order_lock:
            oid = str(order_id)
            if oid in self.orders:
                del self.orders[oid]
                return True
            return False

    def unregister_order(self, order_id: str) -> bool:
        """Alias for remove_order."""
        return self.remove_order(order_id)

    def check_self_trade(
        self,
        account: str,
        side: str,
        price: float,
        size: float
    ) -> Tuple[bool, str]:
        """
        Validates if an order would cross any resting order placed by another controlled account.
        Returns: (is_safe, reason)
        """
        acct = account.upper()
        s = side.lower()
        p = float(price)

        with self.order_lock:
            for oid, o in self.orders.items():
                # Only check counterparty accounts (do not block same account replaces)
                if o.account == acct:
                    continue

                if s == "buy" and o.side == "sell":
                    # Buy crosses if proposed price >= resting sell price
                    if p >= o.price:
                        self.prevented_count += 1
                        reason = (
                            f"STP BLOCKED: {acct} BUY @ {p:.6f} crosses "
                            f"{o.account} resting SELL @ {o.price:.6f} (Order {oid})"
                        )
                        return False, reason

                elif s == "sell" and o.side == "buy":
                    # Sell crosses if proposed price <= resting buy price
                    if p <= o.price:
                        self.prevented_count += 1
                        reason = (
                            f"STP BLOCKED: {acct} SELL @ {p:.6f} crosses "
                            f"{o.account} resting BUY @ {o.price:.6f} (Order {oid})"
                        )
                        return False, reason

        return True, "STP Validation PASSED"

    def validate_order(self, account: str, side: str, price: float, size: float) -> Tuple[bool, str]:
        """Alias for check_self_trade."""
        return self.check_self_trade(account, side, price, size)

    def sync_account_orders(self, account: str, open_orders: List[dict]) -> None:
        """Synchronize active orders with exchange ground truth for an account."""
        acct = account.upper()
        active_ids = {str(o.get("order_id")) for o in open_orders if o.get("order_id")}
        with self.order_lock:
            to_remove = [
                oid for oid, o in self.orders.items()
                if o.account == acct and oid not in active_ids
            ]
            for oid in to_remove:
                del self.orders[oid]

            for o in open_orders:
                oid = str(o.get("order_id"))
                if oid:
                    self.orders[oid] = RegisteredOrder(
                        order_id=oid,
                        account=acct,
                        side=str(o.get("type", "buy")).lower(),
                        price=float(o.get("price", 0.0)),
                        size=float(o.get("amount", 0.0)),
                        custom_id=str(o.get("custom_id", ""))
                    )

    def clear_account_orders(self, account: str) -> int:
        """Clear all active orders for a specific account."""
        acct = account.upper()
        cleared = 0
        with self.order_lock:
            to_remove = [oid for oid, o in self.orders.items() if o.account == acct]
            for oid in to_remove:
                del self.orders[oid]
                cleared += 1
        return cleared

    def get_active_orders(self, account: Optional[str] = None) -> List[RegisteredOrder]:
        """Get all active registered orders, optionally filtered by account."""
        with self.order_lock:
            if account:
                acct = account.upper()
                return [o for o in self.orders.values() if o.account == acct]
            return list(self.orders.values())

    def reset(self) -> None:
        """Reset the registry (useful for unit testing)."""
        with self.order_lock:
            self.orders.clear()
