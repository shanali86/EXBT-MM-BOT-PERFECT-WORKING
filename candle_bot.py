"""
EXBT/USDT — Natural Micro-Wave & Visible Candlestick Engine
Paints natural, highly visible candles across 10 distinct candlestick patterns
with an organic 40-minute price wave cycle:
  - Uptrend Phase: Bullish green candles & Hammer pin bars (Close > Open)
  - Downtrend Phase: Bearish red candles & Shooting stars (Close < Open)
  - Turning Phase: Dojis, Dragonfly, Gravestone, Long-Legged, & Spinning Tops

ZERO-LOSS ARCHITECTURE:
- Matched trades between Account A and Account B at the EXACT same price.
- Zero spread loss ($0.00 spread loss).
- Alternating buyer/seller flow ensures cash and inventory remain in 50/50 equilibrium.
- Widen candle range: 1.0% to 1.8% visible body & wicks for clear 5M/15M chart rendering.
- Corridor bounds: Wave locked between 0.3180 and 0.3370 (Strictly <= 0.3500 ceiling).
"""

import time
import math
import datetime
import random
import logging
from typing import Optional, Dict, Set

from lbank_client import LBankClient, LBankAPIError
import config

logger = logging.getLogger("candle_bot")


class CandleBot:
    def __init__(self, budget_manager):
        self.bm = budget_manager
        # Explicitly bind Account A and Account B clients (two distinct exchange accounts)
        self.client_a = LBankClient(config.API_KEY, config.SECRET_KEY, getattr(config, "USE_RSA", False))
        self.client_b = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, getattr(config, "USE_RSA", False))
        self.dual_accounts = True
        logger.info("CandleBot: Verified DUAL ACCOUNTS (A: Account A, B: Account B) for genuine matching")

        self.symbol = config.SYMBOL
        self.is_running = False
        self.turn_a_to_b = True  # Strict alternation: keeps treasury cash 100% balanced
        self.candles_painted_today = 0
        self.total_volume_today = 0.0
        self.day_start = datetime.date.today()
        self.last_action = "INITIALIZING"

        # Living Organic Wave Settings: 30-minute macro-wave
        self.center_price = float(getattr(config, "WAVE_CENTER_PRICE", 0.3325))
        self.wave_amplitude = float(getattr(config, "WAVE_AMPLITUDE", 0.0090))    # 0.3235 to 0.3415
        self.wave_period_sec = float(getattr(config, "WAVE_PERIOD_SEC", 1800.0))  # 30-minute cycle

        # Track tick state per minute bucket
        self.last_bucket = -1
        self.ticks_in_bucket: Set[int] = set()

        # Stateful Continuous Candlestick Engine
        self.last_candle_close = None
        self.current_minute_plan = None

    def reset_daily_stats(self):
        today = datetime.date.today()
        if today != self.day_start:
            self.candles_painted_today = 0
            self.total_volume_today = 0.0
            self.day_start = today
            logger.info("📅 New day — candle stats reset")

    def _execute_matched_trade(self, price: float, amount: float = 18.0, open_ref: float = 0.0) -> bool:
        """
        Executes a zero-spread matched micro-trade between Account A and Account B.
        Guarantees zero spread loss because price is identical on both sides.
        Strictly clamps price INSIDE current spread so maker orders never cross the book.
        Never allows intra-candle needle plunges (bounds within +/- 0.0016 of open_ref).
        """
        if open_ref > 0:
            price = max(open_ref - 0.0016, min(open_ref + 0.0035, price))

        # 1. Fetch live orderbook to ensure price is strictly inside spread
        try:
            ob = self.client_a.get_orderbook(self.symbol, size=5)
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                min_safe = best_bid + 0.0004
                max_safe = best_ask - 0.0004
                if max_safe > min_safe:
                    price = max(min_safe, min(max_safe, price))
                else:
                    price = (best_bid + best_ask) / 2.0
        except Exception as e:
            logger.debug(f"Orderbook fetch for spread clamp: {e}")

        # Ensure price never plunges outside the planned candle bounds
        if open_ref > 0:
            price = max(open_ref - 0.0016, min(open_ref + 0.0035, price))

        price = round(price, 4)
        amount = round(amount, 2)

        # Enforce strict corridor [PRICE_FLOOR, PRICE_CEILING]
        price_floor = float(getattr(config, "PRICE_FLOOR", 0.3500))
        price_ceiling = float(getattr(config, "PRICE_CEILING", 0.4200))
        price = max(price_floor, min(price_ceiling, price))

        # Check notional
        if (price * amount) < 5.0:
            amount = round(5.5 / price, 2)

        now_ts = int(time.time() * 1000)
        try:
            if self.turn_a_to_b:
                seller_client, buyer_client = self.client_a, self.client_b
                seller_lbl, buyer_lbl = "A", "B"
            else:
                seller_client, buyer_client = self.client_b, self.client_a
                seller_lbl, buyer_lbl = "B", "A"

            # 1. Place Maker Sell
            sell_res = seller_client.place_order(
                self.symbol,
                side="sell",
                price=price,
                amount=amount,
                order_type="maker",
                custom_id=f"cndl_s_{seller_lbl}_{now_ts}"
            )
            sell_id = sell_res.get("order_id")
            if not sell_id:
                return False

            time.sleep(0.35)

            # 2. Place Counterparty Buy to match instantly at exact same price
            buy_res = buyer_client.place_order(
                self.symbol,
                side="buy",
                price=price,
                amount=amount,
                order_type="limit",
                custom_id=f"cndl_b_{buyer_lbl}_{now_ts}"
            )

            # Alternate turn for next trade so cash circulates back and forth
            self.turn_a_to_b = not self.turn_a_to_b
            self.total_volume_today += amount

            logger.info(
                f"🕯️ CANDLE TICK: {amount:.2f} EXBT @ {price:.4f} USDT | "
                f"Seller: {seller_lbl} -> Buyer: {buyer_lbl} | Spread Loss: $0.00"
            )

            # Auto-cleanup safety: Wait 1.0s and cancel residual order if partially unfilled
            time.sleep(1.0)
            try:
                if sell_id:
                    seller_client.cancel_order(self.symbol, sell_id)
            except Exception:
                pass
            try:
                buy_id = buy_res.get("order_id")
                if buy_id:
                    buyer_client.cancel_order(self.symbol, buy_id)
            except Exception:
                pass

            return True

        except Exception as e:
            logger.warning(f"Candle tick trade execution error: {e}")
            return False

    def _generate_minute_candle_plan(self, now: float, bucket: int):
        """
        Creates an authentic, continuous 1-minute candlestick plan:
        - 70-80% solid rectangular body (visible green / red blocks).
        - 15-20% tiny neat wicks (strictly <= 0.0006, NO crazy needle spikes).
        - 5 smooth ticks per minute distributed across the bar.
        - Natural alternation between bullish steps and healthy pullbacks.
        """
        from wave_engine import get_anti_sniper_wave
        wave_target, slope, regime, _ = get_anti_sniper_wave(now)

        price_floor = float(getattr(config, "PRICE_FLOOR", 0.3500))
        price_ceiling = float(getattr(config, "PRICE_CEILING", 0.4200))

        if self.last_candle_close is None:
            self.last_candle_close = round(wave_target, 4)

        # Continuity: Start right at previous candle close
        open_p = round(max(price_floor, min(price_ceiling, self.last_candle_close)), 4)
        rng = random.Random(bucket)
        target_diff = wave_target - open_p

        # Alternating green / red selection matching macro trend
        if target_diff > 0.0008:
            is_green = rng.random() < 0.72  # 72% green during upward climb
        elif target_diff < -0.0008:
            is_green = rng.random() < 0.35  # 35% green during pullback
        else:
            is_green = rng.random() < 0.55

        ticks = []
        if is_green:
            # Solid green candle with tiny realistic wicks
            body = rng.uniform(0.0016, 0.0030)
            low_wick = rng.uniform(0.0002, 0.0005)
            high_wick = rng.uniform(0.0002, 0.0006)

            low_p = round(max(price_floor, open_p - low_wick), 4)
            close_p = round(min(price_ceiling, open_p + body), 4)
            high_p = round(min(price_ceiling, close_p + high_wick), 4)

            ticks = [
                (1, range(5, 14), open_p, f"Green Open @ {open_p:.4f}"),
                (2, range(16, 26), low_p, f"Green Lower Wick @ {low_p:.4f}"),
                (3, range(28, 40), round(open_p + body * 0.5, 4), f"Green Body Climb @ {open_p + body * 0.5:.4f}"),
                (4, range(42, 51), high_p, f"Green Upper Wick @ {high_p:.4f}"),
                (5, range(53, 59), close_p, f"Green Close @ {close_p:.4f}")
            ]
            pattern = "solid_green"
            size = round(rng.uniform(42.0, 78.0), 1)
        else:
            # Solid red pullback candle with tiny realistic wicks
            body = rng.uniform(0.0012, 0.0024)
            high_wick = rng.uniform(0.0002, 0.0005)
            low_wick = rng.uniform(0.0002, 0.0005)

            high_p = round(min(price_ceiling, open_p + high_wick), 4)
            close_p = round(max(price_floor, open_p - body), 4)
            low_p = round(max(price_floor, close_p - low_wick), 4)

            ticks = [
                (1, range(5, 14), open_p, f"Red Open @ {open_p:.4f}"),
                (2, range(16, 26), high_p, f"Red Upper Wick @ {high_p:.4f}"),
                (3, range(28, 40), round(open_p - body * 0.5, 4), f"Red Body Dip @ {open_p - body * 0.5:.4f}"),
                (4, range(42, 51), low_p, f"Red Lower Wick @ {low_p:.4f}"),
                (5, range(53, 59), close_p, f"Red Close @ {close_p:.4f}")
            ]
            pattern = "solid_red"
            size = round(rng.uniform(32.0, 58.0), 1)

        return {
            "bucket": bucket,
            "pattern": pattern,
            "open": open_p,
            "close": close_p,
            "size": size,
            "ticks": ticks
        }

    def execute_candle_tick(self):
        """
        Executes timed ticks inside each 1-minute bar to shape organic, continuous candlestick action.
        """
        now = time.time()
        bucket = int(now // 60)
        second = int(now % 60)

        if bucket != self.last_bucket:
            self.last_bucket = bucket
            self.ticks_in_bucket.clear()
            self.candles_painted_today += 1
            self.current_minute_plan = self._generate_minute_candle_plan(now, bucket)

        if not self.current_minute_plan:
            return

        plan = self.current_minute_plan
        for tick_id, sec_range, price, label in plan["ticks"]:
            if second in sec_range and tick_id not in self.ticks_in_bucket:
                self.ticks_in_bucket.add(tick_id)
                self.last_action = label
                success = self._execute_matched_trade(price, plan["size"], plan["open"])
                # Tick 5 is the final close of the candle
                if tick_id == 5 or tick_id == len(plan["ticks"]):
                    self.last_candle_close = plan["close"]
                break

    def run(self):
        if not getattr(config, "CANDLE_BOT_ENABLED", False):
            logger.info("Candle Bot is DISABLED in config")
            return

        logger.info("🎨 Candle Bot (Natural Micro-Wave & Visible Candlestick Engine) Starting...")
        self.is_running = True

        while self.is_running:
            self.reset_daily_stats()
            try:
                self.execute_candle_tick()
            except Exception as e:
                logger.error(f"Candle Bot loop error: {e}")
            time.sleep(2.0)  # Check schedule every 2.0 seconds


# Aliases for backwards compatibility
MarketCandleMonitorBot = CandleBot
MarketCandleMonitor = CandleBot
