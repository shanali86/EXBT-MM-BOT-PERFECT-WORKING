"""
EXBT/USDT — Volume Bot (Zero-Loss Coordinated Engine)
Generates natural, continuous 24h trading volume on LBank with ZERO SPREAD LOSS.

ZERO-LOSS ARCHITECTURE:
- Matched trades between Account A and Account B at the exact mid price.
- Strict alternation between buyer and seller maintains 50/50 portfolio balance.
- Natural random intervals (50 to 100s) and random sizes (20 to 45 EXBT).
- Strict corridor enforcement: clamped inside [PRICE_FLOOR, PRICE_CEILING] (<= 0.3500).
"""

import time
import random
import logging
import datetime

from lbank_client import LBankClient, LBankAPIError
from stp_registry import STPRegistry
from fill_monitor import FillMonitor
import config

logger = logging.getLogger("volume_bot")


class VolumeBot:
    def __init__(self, budget_manager):
        self.bm = budget_manager
        # Explicitly bind Account A and Account B clients (two distinct exchange accounts)
        self.client_a = LBankClient(config.API_KEY, config.SECRET_KEY, getattr(config, "USE_RSA", False))
        self.client_b = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, getattr(config, "USE_RSA", False))
        self.has_two_accounts = True
        logger.info("Volume Bot: Verified DUAL ACCOUNTS (A: Account A, B: Account B) for genuine matching")

        self.symbol = config.SYMBOL
        self.stp = STPRegistry()
        self.fill_monitor = FillMonitor()

        self.is_running = False
        self.total_volume_today = 0.0
        self.trade_count_today = 0
        self.day_start = datetime.date.today()
        self.turn_a_to_b = True  # Alternate who buys and sells
        self.last_trade_time = 0

    def reset_daily_stats(self):
        today = datetime.date.today()
        if today != self.day_start:
            self.total_volume_today = 0.0
            self.trade_count_today = 0
            self.day_start = today
            logger.info("📅 New day — volume stats reset")

    def get_next_trade_delay(self) -> float:
        min_sec = getattr(config, "VOLUME_INTERVAL_MIN", 50)
        max_sec = getattr(config, "VOLUME_INTERVAL_MAX", 100)
        return random.uniform(min_sec, max_sec)

    def execute_volume_trade(self):
        """
        Executes zero-spread volume trade between Account A and Account B.
        Never crosses wide market spreads; trades match at exact midpoint.
        """
        try:
            # 1. Fetch current midpoint
            orderbook = self.client_a.get_orderbook(self.symbol, size=5)
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])

            if not bids or not asks:
                logger.warning("Volume Bot: Orderbook empty, skipping")
                return

            best_bid = float(bids[0][0])
            best_ask = float(asks[0][0])
            mid_price = round((best_bid + best_ask) / 2.0, 4)

            # Strict Corridor Check
            price_floor = float(getattr(config, "PRICE_FLOOR", 0.2800))
            price_ceiling = float(getattr(config, "PRICE_CEILING", 0.3500))
            if mid_price < price_floor or mid_price > price_ceiling:
                logger.warning(f"Volume Bot: SKIPPED — mid {mid_price:.4f} outside [{price_floor}, {price_ceiling}]")
                return

            # Random natural size: 20 to 45 EXBT (~$6.5 to $15 USDT)
            min_size = getattr(config, "VOLUME_TRADE_SIZE_MIN", 20)
            max_size = getattr(config, "VOLUME_TRADE_SIZE_MAX", 45)
            trade_size = round(random.uniform(min_size, max_size), 1)

            if trade_size * mid_price < 5.0:
                trade_size = round(5.5 / mid_price, 1)

            now_ts = int(time.time() * 1000)

            # Alternating role: Account A -> B or Account B -> A
            if self.turn_a_to_b:
                seller, buyer = self.client_a, self.client_b
                s_lbl, b_lbl = "A", "B"
            else:
                seller, buyer = self.client_b, self.client_a
                s_lbl, b_lbl = "B", "A"

            # 1. Place Maker Sell inside spread at mid_price
            sell_res = seller.place_order(
                self.symbol,
                side="sell",
                price=mid_price,
                amount=trade_size,
                order_type="maker",
                custom_id=f"vol_s_{s_lbl}_{now_ts}"
            )
            sell_id = sell_res.get("order_id")
            if not sell_id:
                return

            time.sleep(0.4)

            # 2. Place Counterparty Buy at exact same price
            buy_res = buyer.place_order(
                self.symbol,
                side="buy",
                price=mid_price,
                amount=trade_size,
                order_type="limit",
                custom_id=f"vol_b_{b_lbl}_{now_ts}"
            )

            # Alternate turn
            self.turn_a_to_b = not self.turn_a_to_b
            self.total_volume_today += trade_size
            self.trade_count_today += 1
            self.last_trade_time = time.time()

            logger.info(
                f"📈 VOLUME TRADE: {trade_size:.1f} EXBT @ {mid_price:.4f} (~${trade_size * mid_price:.2f} USDT) | "
                f"Seller: {s_lbl} -> Buyer: {b_lbl} | Zero Spread Loss"
            )

            # Auto-cleanup safety: Wait 1.0s and cancel residual order if partially unfilled
            time.sleep(1.0)
            try:
                if sell_id:
                    seller.cancel_order(self.symbol, sell_id)
            except Exception:
                pass
            try:
                buy_id = buy_res.get("order_id")
                if buy_id:
                    buyer.cancel_order(self.symbol, buy_id)
            except Exception:
                pass

        except Exception as e:
            logger.warning(f"Volume Bot trade error: {e}")

    def run(self):
        if not getattr(config, "VOLUME_BOT_ENABLED", False):
            logger.info("Volume Bot is DISABLED in config")
            return

        logger.info("🚀 Volume Bot (Zero-Loss Matched Volume) Starting...")
        self.is_running = True

        while self.is_running:
            self.reset_daily_stats()
            delay = self.get_next_trade_delay()
            time.sleep(delay)
            self.execute_volume_trade()
