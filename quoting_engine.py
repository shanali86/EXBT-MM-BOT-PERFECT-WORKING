"""
quoting_engine.py — Dynamic Quoting Engine
Generates multi-level ladder orders with liquidity depth curves,
adaptive spreads, inventory skewing, and precise price/size quantizing.
"""

import math
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger("quoting_engine")


@dataclass
class QuoteLevel:
    level: int
    side: str
    price: float
    amount: float
    notional: float


@dataclass
class QuotePlan:
    is_valid: bool
    reason: str
    reference_price: float
    bids: List[QuoteLevel] = field(default_factory=list)
    asks: List[QuoteLevel] = field(default_factory=list)
    total_buy_notional: float = 0.0
    total_sell_qty: float = 0.0


class QuotingEngine:
    def __init__(
        self,
        base_spread_pct: float = 1.2,
        min_spread_pct: float = 0.6,
        max_spread_pct: float = 3.0,
        num_levels: int = 5,
        level_spacing_pct: float = 0.4,
        min_order_size: float = 100.0,
        max_order_size: float = 300.0,
        price_precision: int = 4,
        amount_precision: int = 2,
        price_floor: float = 0.0,
        price_ceiling: float = 999999.0,
        **kwargs
    ):
        self.price_floor = float(price_floor)
        self.price_ceiling = float(price_ceiling)
        self.base_spread_pct = float(base_spread_pct)
        self.min_spread_pct = float(min_spread_pct)
        self.max_spread_pct = float(max_spread_pct)
        self.num_levels = max(1, int(num_levels))
        self.level_spacing_pct = float(level_spacing_pct)
        self.min_order_size = float(min_order_size)
        self.max_order_size = float(max_order_size)
        self.price_precision = int(price_precision)
        self.amount_precision = int(amount_precision)

        # Non-uniform liquidity distribution across levels (more dense near top of book)
        # For 5 levels: e.g. [0.28, 0.24, 0.20, 0.16, 0.12]
        weights = [1.0 / (1.0 + (i * 0.3)) for i in range(self.num_levels)]
        total_w = sum(weights)
        self.level_weights = [w / total_w for w in weights]

    def generate_quote_plan(
        self,
        reference_price: float,
        allocated_usdt: float,
        allocated_exbt: float,
        volatility_pct: float = 0.0,
        buy_skew: float = 1.0,
        sell_skew: float = 1.0,
        can_quote_buy: bool = True,
        can_quote_sell: bool = True
    ) -> QuotePlan:
        """
        Builds a QuotePlan containing laddered bids and asks.
        """
        ref_p = float(reference_price)
        if ref_p <= 0:
            return QuotePlan(is_valid=False, reason="Reference price must be positive", reference_price=0.0)

        # Dynamic spread based on volatility
        effective_spread = self.base_spread_pct + (volatility_pct * 0.5)
        effective_spread = max(self.min_spread_pct, min(self.max_spread_pct, effective_spread))
        half_spread_pct = effective_spread / 2.0

        bids = []
        asks = []
        tot_buy_notional = 0.0
        tot_sell_qty = 0.0

        import random
        # 1. Generate BIDS
        if can_quote_buy and allocated_usdt > 0:
            usable_usdt = allocated_usdt * 0.95  # 5% safety buffer
            # Non-uniform realistic crypto order size profiles with natural noise
            size_templates = [78.4, 114.2, 92.5, 131.7, 85.3]
            for i in range(self.num_levels):
                offset_pct = half_spread_pct + (i * self.level_spacing_pct)
                price = ref_p * (1.0 - (offset_pct / 100.0))
                price = round(price, self.price_precision)
                if price <= 0:
                    continue

                base_sz = size_templates[i % len(size_templates)]
                jitter = random.uniform(-6.0, 8.0) + random.choice([0.13, 0.47, 0.72, 0.89, 0.25, 0.61])
                target_qty = (base_sz + jitter) * float(buy_skew)
                qty = max(self.min_order_size, min(self.max_order_size, target_qty))
                qty = round(qty, self.amount_precision)

                notional = price * qty
                if notional <= usable_usdt:
                    bids.append(QuoteLevel(level=i+1, side="buy", price=price, amount=qty, notional=notional))
                    tot_buy_notional += notional

        # 2. Generate ASKS
        if can_quote_sell and allocated_exbt > 0:
            usable_exbt = allocated_exbt * 0.95
            size_templates = [82.6, 126.4, 73.8, 118.5, 96.2]
            for i in range(self.num_levels):
                offset_pct = half_spread_pct + (i * self.level_spacing_pct)
                price = ref_p * (1.0 + (offset_pct / 100.0))
                price = round(price, self.price_precision)

                base_sz = size_templates[i % len(size_templates)]
                jitter = random.uniform(-6.0, 8.0) + random.choice([0.18, 0.35, 0.64, 0.81, 0.42, 0.77])
                target_qty = (base_sz + jitter) * float(sell_skew)
                qty = max(self.min_order_size, min(self.max_order_size, target_qty))
                qty = round(qty, self.amount_precision)

                notional = price * qty
                if qty <= usable_exbt:
                    asks.append(QuoteLevel(level=i+1, side="sell", price=price, amount=qty, notional=notional))
                    tot_sell_qty += qty

        is_valid = bool(bids or asks)
        reason = "OK" if is_valid else "Insufficient balance or disabled quotes on both sides"

        return QuotePlan(
            is_valid=is_valid,
            reason=reason,
            reference_price=ref_p,
            bids=bids,
            asks=asks,
            total_buy_notional=round(tot_buy_notional, 2),
            total_sell_qty=round(tot_sell_qty, 2)
        )
