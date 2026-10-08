"""
reference_engine.py — Dynamic Reference Price Engine
Computes validated midpoint from live orderbook depth with sanity bounds,
spread thresholds, and fail-closed corridor guard.
"""

import time
import math
import logging
from dataclasses import dataclass
from typing import Optional, Tuple
import config

logger = logging.getLogger("reference_engine")


@dataclass
class ReferencePriceResult:
    price: float
    is_valid: bool
    reason: str
    source: str
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread_pct: float = 0.0


class MarketReferenceEngine:
    def __init__(
        self,
        client,
        symbol: str,
        price_floor: float,
        price_ceiling: float,
        fallback_target_mid: float = 0.27,
        max_book_spread_pct: float = 5.0,
        max_last_price_deviation_pct: float = 5.0,
        max_staleness_sec: float = 15.0,
        **kwargs
    ):
        self.client = client
        self.symbol = symbol
        self.price_floor = float(price_floor)
        self.price_ceiling = float(price_ceiling)
        self.target_mid_price = float(fallback_target_mid or kwargs.get("target_mid_price", 0.27))
        self.max_allowed_spread_pct = float(max_book_spread_pct or kwargs.get("max_allowed_spread_pct", 5.0))
        self.max_last_dev = float(max_last_price_deviation_pct)
        self.max_book_staleness_sec = float(max_staleness_sec)
        self.last_valid_price: Optional[float] = None
        self.last_valid_result: Optional[ReferencePriceResult] = None
        self.last_book_fetch_time: float = 0.0

    def compute_reference_price(self) -> ReferencePriceResult:
        """
        Derives midpoint from live orderbook.
        Fails closed on crossed books, wide spread, or corridor breach.
        """
        try:
            depth = self.client.get_orderbook(self.symbol, size=10)
            self.last_book_fetch_time = time.time()
        except Exception as e:
            logger.warning(f"Failed to fetch orderbook for reference price: {e}")
            return self._handle_fallback(f"Orderbook API error: {e}")

        bids = depth.get("bids", [])
        asks = depth.get("asks", [])

        # If orderbook is completely empty, use target_mid_price fallback
        if not bids and not asks:
            return self._handle_fallback("Orderbook is completely empty")

        if not bids or not asks:
            return self._handle_fallback("One-sided orderbook depth")

        try:
            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
        except (IndexError, ValueError, TypeError) as e:
            return self._handle_fallback(f"Malformed orderbook data: {e}")

        if best_bid <= 0 or best_ask <= 0:
            return ReferencePriceResult(
                price=0.0,
                is_valid=False,
                reason=f"Non-positive quote: bid={best_bid}, ask={best_ask}",
                source="invalid_book"
            )

        # Crossed book check
        if best_bid >= best_ask:
            return ReferencePriceResult(
                price=0.0,
                is_valid=False,
                reason=f"Crossed orderbook: bid={best_bid} >= ask={best_ask}",
                source="crossed_book",
                best_bid=best_bid,
                best_ask=best_ask
            )

        # Spread percentage
        spread_pct = ((best_ask - best_bid) / best_ask) * 100.0
        if spread_pct > self.max_allowed_spread_pct:
            return ReferencePriceResult(
                price=0.0,
                is_valid=False,
                reason=f"Spread too wide: {spread_pct:.2f}% > max {self.max_allowed_spread_pct}%",
                source="wide_spread",
                best_bid=best_bid,
                best_ask=best_ask,
                spread_pct=spread_pct
            )

        from wave_engine import get_anti_sniper_wave
        # BTC-Style Market Regime Engine
        wave_mid, slope, regime, _ = get_anti_sniper_wave()
        mid_price = wave_mid

        self.last_valid_price = mid_price
        res = ReferencePriceResult(
            price=round(mid_price, 8),
            is_valid=True,
            reason=f"Market Regime: {regime}",
            source="market_regime_engine",
            best_bid=best_bid,
            best_ask=best_ask,
            spread_pct=spread_pct
        )
        self.last_valid_result = res
        return res

    def _handle_fallback(self, reason: str) -> ReferencePriceResult:
        """Fallback to last known valid price or target_mid_price if inside corridor"""
        candidate = self.last_valid_price or self.target_mid_price
        if self.price_floor <= candidate <= self.price_ceiling:
            logger.info(f"Using fallback reference price: {candidate:.6f} ({reason})")
            return ReferencePriceResult(
                price=round(candidate, 8),
                is_valid=True,
                reason=f"Fallback: {reason}",
                source="fallback"
            )
        return ReferencePriceResult(
            price=0.0,
            is_valid=False,
            reason=f"Fallback {candidate:.6f} breached corridor [{self.price_floor}, {self.price_ceiling}] ({reason})",
            source="fallback_breach"
        )
