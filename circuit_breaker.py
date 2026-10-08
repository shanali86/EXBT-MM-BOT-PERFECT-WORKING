"""
circuit_breaker.py — Circuit Breaker Sentinel
Monitors system health, consecutive error streaks, abnormal spreads,
and corridor breaches. Fails-closed immediately if market integrity is compromised.
"""

import time
import logging
from dataclasses import dataclass
from typing import Tuple

logger = logging.getLogger("circuit_breaker")


@dataclass
class CircuitBreakerStatus:
    status: str
    consecutive_errors: int
    trip_reason: str
    last_trip_time: float
    is_healthy: bool


class CircuitBreaker:
    def __init__(
        self,
        max_consecutive_errors: int = 5,
        cooldown_seconds: float = 30.0,
        max_allowed_spread_pct: float = 5.0
    ):
        self.max_errors = int(max_consecutive_errors)
        self.cooldown_sec = float(cooldown_seconds)
        self.max_spread = float(max_allowed_spread_pct)

        self.consecutive_errors = 0
        self.is_tripped = False
        self.trip_reason = ""
        self.last_trip_time = 0.0

    def trip(self, reason: str) -> None:
        """Immediately trip the circuit breaker and halt quoting."""
        self.is_tripped = True
        self.trip_reason = str(reason)
        self.last_trip_time = time.time()
        logger.error(f"🚨 CIRCUIT BREAKER TRIPPED: {self.trip_reason}")

    def reset(self) -> None:
        """Reset the circuit breaker to healthy state."""
        self.is_tripped = False
        self.trip_reason = ""
        self.consecutive_errors = 0
        logger.info("✅ Circuit breaker reset to HEALTHY.")

    def record_success(self) -> None:
        """Record successful operation, resetting consecutive error count."""
        self.consecutive_errors = 0
        # If in cooldown and timer elapsed, automatically recover
        if self.is_tripped and (time.time() - self.last_trip_time) >= self.cooldown_sec:
            self.reset()

    def record_api_error(self, error: str) -> None:
        """Record an API error and trip if threshold reached."""
        self.consecutive_errors += 1
        logger.warning(f"API Error recorded ({self.consecutive_errors}/{self.max_errors}): {error}")
        if self.consecutive_errors >= self.max_errors:
            self.trip(f"API error streak reached threshold ({self.consecutive_errors}/{self.max_errors}): {error}")

    def evaluate(
        self,
        ref_price_valid: bool,
        ref_price_reason: str,
        best_bid: float,
        best_ask: float,
        spread_pct: float,
        price_floor: float,
        price_ceiling: float,
        current_price: float,
        balances_verified: bool = True,
        inventory_reason: str = ""
    ) -> Tuple[bool, str]:
        """
        Evaluates full system health before quoting.
        Returns: (can_quote, reason)
        """
        # 1. Check if currently tripped
        if self.is_tripped:
            elapsed = time.time() - self.last_trip_time
            if elapsed < self.cooldown_sec:
                remaining = self.cooldown_sec - elapsed
                return False, f"Circuit breaker in cooldown ({remaining:.1f}s remaining): {self.trip_reason}"
            else:
                # Cooldown expired, attempt probe recovery
                logger.info(f"Cooldown expired ({self.cooldown_sec}s). Attempting health re-evaluation.")
                self.is_tripped = False

        # 2. Check reference price validity
        if not ref_price_valid:
            self.trip(f"Invalid reference price: {ref_price_reason}")
            return False, self.trip_reason

        # 3. Check corridor bounds
        if current_price < price_floor or current_price > price_ceiling:
            self.trip(f"Corridor breach: mid {current_price:.6f} outside [{price_floor}, {price_ceiling}]")
            return False, self.trip_reason

        # 4. Check book spread anomaly
        if spread_pct > self.max_spread:
            self.trip(f"Abnormal book spread: {spread_pct:.2f}% > {self.max_spread}%")
            return False, self.trip_reason

        # 5. Check balances verified
        if not balances_verified:
            self.trip("Account balances could not be verified")
            return False, self.trip_reason

        return True, "HEALTHY"

    def get_status(self) -> dict:
        """Returns status dictionary for status printing and web dashboard."""
        if self.is_tripped:
            status_str = f"TRIPPED ({self.trip_reason})"
        elif self.consecutive_errors > 0:
            status_str = f"WARNING ({self.consecutive_errors}/{self.max_errors} errors)"
        else:
            status_str = "HEALTHY"

        return {
            "status": status_str,
            "is_tripped": self.is_tripped,
            "consecutive_errors": self.consecutive_errors,
            "trip_reason": self.trip_reason,
            "last_trip_time": self.last_trip_time
        }

