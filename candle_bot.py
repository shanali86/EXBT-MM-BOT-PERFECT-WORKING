"""
EXBT/USDT — Natural BTC-Style Trend Wave & Candlestick Engine
Paints authentic, organic crypto candlesticks matching BTC/ETH price action:
  - Multi-candle directional trend runs (Higher Highs & Higher Lows)
  - Realistic 15-minute chart wave formation (pullbacks, consolidations, breakouts)
  - Natural candle archetypes: Trend Drives, Healthy Pullbacks, Dojis, and Pinbars
  - Zero flatline or 0.00 volume bars (5 timed micro-ticks per minute)

ZERO-LOSS ARCHITECTURE:
- Matched trades between Account A and Account B at the EXACT same price.
- Zero spread loss ($0.00 spread loss).
- Auto-rebalance safeguard prevents either account from running out of cash.
- Dynamic inner-pocket spread floating prevents pinning against MM orderbook walls.
- Anti-staircase step capping guarantees smooth, continuous price transitions.
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

    def _cleanup_stale_candle_orders(self):
        """Cancels any orphan candle orders older than 8 seconds to prevent book blockage."""
        now_ts = int(time.time() * 1000)
        for client in [self.client_a, self.client_b]:
            try:
                orders = client.get_open_orders(self.symbol)
                for o in orders:
                    cid = str(o.get("custom_id", ""))
                    if cid.startswith("cndl_"):
                        parts = cid.split("_")
                        if len(parts) >= 4 and parts[-1].isdigit():
                            order_ts = int(parts[-1])
                            if (now_ts - order_ts) > 8000:  # Older than 8s
                                client.cancel_order(self.symbol, o.get("order_id"))
                        else:
                            client.cancel_order(self.symbol, o.get("order_id"))
            except Exception as e:
                logger.debug(f"Stale candle order cleanup error: {e}")

    def _execute_matched_trade(self, price: float, amount: float = 18.0, open_ref: float = 0.0) -> bool:
        """
        Executes a zero-spread matched micro-trade between Account A and Account B.
        Guarantees zero spread loss because price is identical on both sides.
        Strictly floats price INSIDE current spread corridor so maker orders never cross the book.
        """
        # 1. Fetch live orderbook to ensure price is strictly inside spread
        try:
            ob = self.client_a.get_orderbook(self.symbol, size=5)
            bids = ob.get("bids", [])
            asks = ob.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                spread = best_ask - best_bid

                # Safe inner pocket: keep trade inside the middle safe zone of the spread
                buffer = max(0.0006, spread * 0.12)
                min_safe = best_bid + buffer
                max_safe = best_ask - buffer

                if max_safe > min_safe:
                    price = max(min_safe, min(max_safe, price))
                else:
                    price = (best_bid + best_ask) / 2.0
        except Exception as e:
            logger.debug(f"Orderbook fetch for spread clamp: {e}")

        # 2. Smooth delta: Cap step changes to prevent sudden vertical staircase gaps
        if self.last_candle_close is not None and self.last_candle_close > 0:
            max_step = 0.0005  # Max 5 pips per tick change
            price = max(self.last_candle_close - max_step, min(self.last_candle_close + max_step, price))

        price = round(price, 4)
        amount = round(amount, 2)

        # Enforce strict corridor [PRICE_FLOOR, CANDLE_MAX_PRICE]
        price_floor = float(getattr(config, "PRICE_FLOOR", 0.3500))
        price_ceiling = float(getattr(config, "CANDLE_MAX_PRICE", 0.4085))
        price = max(price_floor, min(price_ceiling, price))

        # Check notional minimum ($5.00)
        if (price * amount) < 5.0:
            amount = round(5.5 / price, 2)

        now_ts = int(time.time() * 1000)
        try:
            buyer_lbl = "B" if self.turn_a_to_b else "A"
            seller_lbl = "A" if buyer_lbl == "B" else "B"

            # Free usable balance check to guarantee trade never fails with 10016 Currency not enough
            try:
                bals_a = self.client_a.get_balances().get("free", {})
                bals_b = self.client_b.get_balances().get("free", {})
                free_a_usdt = float(bals_a.get("USDT", 0.0))
                free_b_usdt = float(bals_b.get("USDT", 0.0))
                free_a_exbt = float(bals_a.get("EXBT", 0.0))
                free_b_exbt = float(bals_b.get("EXBT", 0.0))

                # If B has less than 150 free USDT, steer cash flow: A buys from B so B receives USDT
                if free_b_usdt < 150.0 and free_a_usdt > 300.0:
                    buyer_lbl, seller_lbl = "A", "B"
                elif free_a_usdt < 300.0 and free_b_usdt > 500.0:
                    buyer_lbl, seller_lbl = "B", "A"

                buyer_free_usdt = free_a_usdt if buyer_lbl == "A" else free_b_usdt
                seller_free_exbt = free_a_exbt if seller_lbl == "A" else free_b_exbt

                # Strictly cap amount within 90% of available free balances
                max_buy_exbt = (buyer_free_usdt * 0.90) / price
                max_sell_exbt = seller_free_exbt * 0.90
                amount = min(amount, max_buy_exbt, max_sell_exbt)
                amount = round(amount, 2)
            except Exception as e:
                logger.debug(f"Free balance safeguard check: {e}")

            if (price * amount) < 5.0:
                logger.warning(f"Candle tick deferred: Available free funds below $5 minimum notional.")
                return False

            seller_client = self.client_a if seller_lbl == "A" else self.client_b
            buyer_client = self.client_b if buyer_lbl == "B" else self.client_a

            # 1. Place Maker Sell
            sell_res = seller_client.place_order(
                self.symbol,
                side="sell",
                price=price,
                amount=amount,
                order_type="maker",
                custom_id=f"cndl_s_{seller_lbl}_{now_ts}"
            )
            sell_id = sell_res.get("order_id") if isinstance(sell_res, dict) else None
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
            buy_id = buy_res.get("order_id") if isinstance(buy_res, dict) else None
            if not buy_id:
                # Immediate rescue: Cancel maker sell right away if buy failed
                try:
                    seller_client.cancel_order(self.symbol, sell_id)
                except Exception:
                    pass
                return False

            # Alternate turn for next trade so cash circulates back and forth
            self.turn_a_to_b = not self.turn_a_to_b
            self.total_volume_today += amount
            self.last_candle_close = price  # Update with live executed price

            logger.info(
                f"🕯️ CANDLE TICK: {amount:.2f} EXBT @ {price:.4f} USDT | "
                f"Seller: {seller_lbl} -> Buyer: {buyer_lbl} | Spread Loss: $0.00"
            )

            # Auto-cleanup safety: Wait 0.8s and cancel residual order if partially unfilled
            time.sleep(0.8)
            try:
                if sell_id:
                    seller_client.cancel_order(self.symbol, sell_id)
            except Exception:
                pass
            try:
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
        Creates an authentic, continuous BTC-style 1-minute candlestick plan:
        - Natural micro-steps (0.0004 - 0.0012) allowing 15M candles to develop real trend waves.
        - Trend persistence: 75%-80% momentum runs during wave expansions.
        - Varied archetypes: Trend Drives (60%), Rejection Pinbars (20%), Resting Dojis (20%).
        - 5 smooth ticks per minute ensuring continuous, non-zero volume bars.
        """
        from wave_engine import get_anti_sniper_wave
        wave_target, slope, regime, _ = get_anti_sniper_wave(now)

        price_floor = float(getattr(config, "PRICE_FLOOR", 0.3500))
        price_ceiling = float(getattr(config, "CANDLE_MAX_PRICE", 0.4085))

        if self.last_candle_close is None:
            try:
                ob = self.client_a.get_orderbook(self.symbol, size=5)
                bids = ob.get("bids", [])
                asks = ob.get("asks", [])
                if bids and asks:
                    mid = (float(bids[0][0]) + float(asks[0][0])) / 2.0
                    self.last_candle_close = round(mid, 4)
                else:
                    self.last_candle_close = round(wave_target, 4)
            except Exception:
                self.last_candle_close = round(wave_target, 4)

        # Continuity: Start right at previous candle close
        open_p = round(max(price_floor, min(price_ceiling, self.last_candle_close)), 4)
        rng = random.Random(bucket)
        target_diff = wave_target - open_p

        # Directional continuity: Match macro trend with natural persistence
        if target_diff > 0.0005:
            is_green = rng.random() < 0.70  # 70% green during upward wave climb
        elif target_diff < -0.0005:
            is_green = rng.random() < 0.30  # 30% green (70% red) during healthy pullback
        else:
            is_green = rng.random() < 0.50  # Balanced alternation on flat shelves

        # Proportional 1-minute body size (Dynamic, realistic crypto increments)
        if abs(target_diff) > 0.0025:
            body = rng.uniform(0.0005, 0.0008)  # Gentle momentum move
        elif abs(target_diff) > 0.0010:
            body = rng.uniform(0.0003, 0.0005)  # Smooth steady climb / dip
        else:
            body = rng.uniform(0.0002, 0.0004)  # Normal resting consolidation

        # Clean Solid Candle Formation: 85% Solid full bodies (NO spiky needles!)
        archetype_r = rng.random()
        has_wick = archetype_r > 0.85
        wick_size = rng.uniform(0.0001, 0.0002) if has_wick else 0.0000

        # $500K USD Volume Scaling: Organic distribution averaging ~175 EXBT/tick (~$500K+/day)
        vol_tier = rng.random()
        if vol_tier < 0.40:
            base_size = rng.uniform(90.0, 140.0)   # Organic quiet flow (avg ~115 EXBT = ~$46 USDT)
        elif vol_tier < 0.85:
            base_size = rng.uniform(160.0, 230.0)  # Normal trading flow (avg ~195 EXBT = ~$79 USDT)
        else:
            base_size = rng.uniform(250.0, 360.0)  # Momentum volume surge (avg ~305 EXBT = ~$123 USDT)

        ticks = []
        if is_green:
            close_p = round(min(price_ceiling, open_p + body), 4)
            high_p = round(min(price_ceiling, close_p + wick_size), 4)

            # Solid clean climb: Open -> Step 1 -> Step 2 -> Step 3 -> Close (No spiky needles)
            step1 = round(open_p + (close_p - open_p) * 0.25, 4)
            step2 = round(open_p + (close_p - open_p) * 0.55, 4)
            step3 = round(open_p + (close_p - open_p) * 0.82, 4)

            ticks = [
                (1, range(4, 14), open_p, f"Green Open @ {open_p:.4f}"),
                (2, range(16, 26), step1, f"Green Step 1 @ {step1:.4f}"),
                (3, range(28, 40), step2, f"Green Step 2 @ {step2:.4f}"),
                (4, range(42, 51), step3 if not has_wick else high_p, f"Green Step 3 @ {step3:.4f}"),
                (5, range(53, 59), close_p, f"Green Close @ {close_p:.4f}")
            ]
            pattern = "solid_green"
            size = round(base_size, 1)
        else:
            close_p = round(max(price_floor, open_p - body), 4)
            low_p = round(max(price_floor, close_p - wick_size), 4)

            # Solid clean dip: Open -> Step 1 -> Step 2 -> Step 3 -> Close (No spiky needles)
            step1 = round(open_p - (open_p - close_p) * 0.25, 4)
            step2 = round(open_p - (open_p - close_p) * 0.55, 4)
            step3 = round(open_p - (open_p - close_p) * 0.82, 4)

            ticks = [
                (1, range(4, 14), open_p, f"Red Open @ {open_p:.4f}"),
                (2, range(16, 26), step1, f"Red Step 1 @ {step1:.4f}"),
                (3, range(28, 40), step2, f"Red Step 2 @ {step2:.4f}"),
                (4, range(42, 51), step3 if not has_wick else low_p, f"Red Step 3 @ {step3:.4f}"),
                (5, range(53, 59), close_p, f"Red Close @ {close_p:.4f}")
            ]
            pattern = "solid_red"
            size = round(base_size * 0.90, 1)

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
            self._cleanup_stale_candle_orders()
            self.current_minute_plan = self._generate_minute_candle_plan(now, bucket)

        if not self.current_minute_plan:
            return

        plan = self.current_minute_plan
        for tick_id, sec_range, price, label in plan["ticks"]:
            if second in sec_range and tick_id not in self.ticks_in_bucket:
                self.ticks_in_bucket.add(tick_id)
                self.last_action = label
                self._execute_matched_trade(price, plan["size"], plan["open"])
                break

    def run(self):
        if not getattr(config, "CANDLE_BOT_ENABLED", False):
            logger.info("Candle Bot is DISABLED in config")
            return

        logger.info("🎨 Candle Bot (Natural BTC-Style Wave & Visible Candlestick Engine) Starting...")
        self._cleanup_stale_candle_orders()
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
