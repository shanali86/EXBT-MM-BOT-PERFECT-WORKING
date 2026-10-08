"""
inventory_manager.py — Dynamic Inventory Rebalancer
Evaluates USDT/EXBT portfolio balance, calculates inventory skewing multipliers,
and enforces hard inventory caps to protect capital.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("inventory_manager")


@dataclass
class InventoryState:
    inventory_ratio: float
    buy_skew: float
    sell_skew: float
    can_quote_buy: bool
    can_quote_sell: bool
    reason: str
    total_usdt: float = 0.0
    total_exbt: float = 0.0
    portfolio_value_usd: float = 0.0


class InventoryManager:
    def __init__(
        self,
        target_inventory_ratio: float = 0.50,
        ratio_tolerance: float = 0.15,
        max_exbt_inventory: float = 250000.0,
        max_usdt_exposure: float = 25000.0,
        max_open_order_notional: float = 35000.0
    ):
        self.target_ratio = float(target_inventory_ratio)
        self.tolerance = float(ratio_tolerance)
        self.max_exbt = float(max_exbt_inventory)
        self.max_usdt = float(max_usdt_exposure)
        self.max_open_notional = float(max_open_order_notional)

        self.current_state = InventoryState(
            inventory_ratio=self.target_ratio,
            buy_skew=1.0,
            sell_skew=1.0,
            can_quote_buy=True,
            can_quote_sell=True,
            reason="Initialized baseline"
        )

    def update_inventory(
        self,
        usdt_free: float,
        usdt_locked: float,
        exbt_free: float,
        exbt_locked: float,
        reference_price: float,
        open_orders: Optional[List[dict]] = None
    ) -> InventoryState:
        """
        Calculates inventory ratio and dynamically skews quoting multipliers.
        """
        tot_usdt = float(usdt_free) + float(usdt_locked)
        tot_exbt = float(exbt_free) + float(exbt_locked)
        ref_p = max(0.0001, float(reference_price))

        exbt_val = tot_exbt * ref_p
        port_val = tot_usdt + exbt_val

        ratio = (exbt_val / port_val) if port_val > 0 else self.target_ratio

        can_buy = True
        can_sell = True
        buy_skew = 1.0
        sell_skew = 1.0
        reasons = []

        # 1. Hard Exposure Caps
        if tot_exbt >= self.max_exbt:
            can_buy = False
            reasons.append(f"EXBT inventory ({tot_exbt:.0f}) >= cap ({self.max_exbt:.0f})")

        if tot_usdt >= self.max_usdt:
            can_sell = False
            reasons.append(f"USDT exposure (${tot_usdt:.1f}) >= cap (${self.max_usdt:.1f})")

        # 2. Skewing based on Inventory Imbalance
        upper_bound = self.target_ratio + self.tolerance
        lower_bound = self.target_ratio - self.tolerance

        if ratio > upper_bound:
            # Long EXBT: shrink buy sizes, increase sell sizes to recover USDT
            excess_factor = min(1.0, (ratio - upper_bound) / (1.0 - upper_bound + 1e-6))
            buy_skew = max(0.20, 1.0 - (0.80 * excess_factor))
            sell_skew = min(2.50, 1.0 + (1.50 * excess_factor))
            reasons.append(f"Heavy EXBT inventory ({ratio*100:.1f}% > {upper_bound*100:.1f}%), skewing towards SELL")

        elif ratio < lower_bound:
            # Long USDT: shrink sell sizes, increase buy sizes to accumulate EXBT
            deficit_factor = min(1.0, (lower_bound - ratio) / (lower_bound + 1e-6))
            buy_skew = min(2.50, 1.0 + (1.50 * deficit_factor))
            sell_skew = max(0.20, 1.0 - (0.80 * deficit_factor))
            reasons.append(f"Heavy USDT reserve ({ratio*100:.1f}% < {lower_bound*100:.1f}%), skewing towards BUY")
        else:
            reasons.append(f"Balanced inventory ({ratio*100:.1f}%) within tolerance")

        reason_str = "; ".join(reasons)
        self.current_state = InventoryState(
            inventory_ratio=round(ratio, 4),
            buy_skew=round(buy_skew, 2),
            sell_skew=round(sell_skew, 2),
            can_quote_buy=can_buy,
            can_quote_sell=can_sell,
            reason=reason_str,
            total_usdt=round(tot_usdt, 2),
            total_exbt=round(tot_exbt, 2),
            portfolio_value_usd=round(port_val, 2)
        )
        return self.current_state

