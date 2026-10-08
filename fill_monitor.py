"""
fill_monitor.py — Execution and Fill Monitor
Tracks active orders, verifies fills against exchange orderbook reconciliations,
and aggregates genuine executed trading metrics.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("fill_monitor")


@dataclass
class TrackedOrder:
    account: str
    order_id: str
    side: str
    price: float
    size: float
    custom_id: str
    placed_at: float = field(default_factory=time.time)


class FillMonitor:
    def __init__(self):
        self.tracked_orders: Dict[str, TrackedOrder] = {}
        self.stats = {
            "total_fills": 0,
            "buy_fills": 0,
            "sell_fills": 0,
            "buy_volume_exbt": 0.0,
            "sell_volume_exbt": 0.0,
            "usdt_spent": 0.0,
            "usdt_received": 0.0
        }

    def track_order(
        self,
        account: str,
        order_id: str,
        side: str,
        price: float,
        size: float,
        custom_id: str = ""
    ) -> None:
        """Add an active order to fill tracking."""
        oid = str(order_id)
        self.tracked_orders[oid] = TrackedOrder(
            account=account.upper(),
            order_id=oid,
            side=side.lower(),
            price=float(price),
            size=float(size),
            custom_id=custom_id
        )

    def untrack_order(self, order_id: str) -> Optional[TrackedOrder]:
        """Remove order when cancelled intentionally."""
        oid = str(order_id)
        return self.tracked_orders.pop(oid, None)

    def reconcile_open_orders(self, account: str, current_open_orders: List[dict]) -> List[TrackedOrder]:
        """
        Compares tracked orders against currently open exchange orders.
        If a tracked order disappeared without an intentional cancel, it was filled!
        """
        acct = account.upper()
        current_open_ids = {str(o.get("order_id")) for o in current_open_orders if o.get("order_id")}

        filled_orders = []
        # Find orders that were tracked for this account but are no longer in open orders
        for oid, order in list(self.tracked_orders.items()):
            if order.account == acct and oid not in current_open_ids:
                # Order executed!
                filled_orders.append(order)
                del self.tracked_orders[oid]

                self.stats["total_fills"] += 1
                notional = order.price * order.size
                if order.side == "buy":
                    self.stats["buy_fills"] += 1
                    self.stats["buy_volume_exbt"] += order.size
                    self.stats["usdt_spent"] += notional
                    logger.info(
                        f"[{acct}] 🎯 MM BUY FILLED: {order.size:.2f} EXBT @ {order.price:.4f} "
                        f"(${notional:.2f} USDT) | ID: {oid}"
                    )
                else:
                    self.stats["sell_fills"] += 1
                    self.stats["sell_volume_exbt"] += order.size
                    self.stats["usdt_received"] += notional
                    logger.info(
                        f"[{acct}] 🎯 MM SELL FILLED: {order.size:.2f} EXBT @ {order.price:.4f} "
                        f"(${notional:.2f} USDT) | ID: {oid}"
                    )

        return filled_orders

    def get_stats(self) -> dict:
        """Returns cumulative fill statistics formatted for status display."""
        tot_vol = self.stats["buy_volume_exbt"] + self.stats["sell_volume_exbt"]
        tot_usdt = self.stats["usdt_spent"] + self.stats["usdt_received"]
        return {
            "completed_fills": self.stats["total_fills"],
            "partial_fills": 0,
            "total_filled_exbt": tot_vol,
            "total_filled_usdt": tot_usdt,
            "buy_volume_exbt": self.stats["buy_volume_exbt"],
            "sell_volume_exbt": self.stats["sell_volume_exbt"],
            "usdt_spent": self.stats["usdt_spent"],
            "usdt_received": self.stats["usdt_received"]
        }

    def reset(self) -> None:
        """Reset monitor state."""
        self.tracked_orders.clear()
        for k in self.stats:
            self.stats[k] = 0 if isinstance(self.stats[k], int) else 0.0
