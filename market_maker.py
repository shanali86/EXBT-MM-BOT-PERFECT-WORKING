"""
EXBT/USDT — Professional Market Maker Engine
Dynamic quoting with responsive spread, genuine depth curve,
Self-Trade Prevention (STP), inventory rebalancing, circuit breakers,
and exchange fill verification.
"""

import time
import logging
import datetime
import uuid
from typing import List, Dict, Optional, Tuple

from lbank_client import LBankClient, LBankAPIError
from reference_engine import MarketReferenceEngine, ReferencePriceResult
from quoting_engine import QuotingEngine, QuotePlan, QuoteLevel
from inventory_manager import InventoryManager, InventoryState
from stp_registry import STPRegistry
from fill_monitor import FillMonitor
from circuit_breaker import CircuitBreaker, CircuitBreakerStatus
import config

logger = logging.getLogger("market_maker")


class MarketMaker:
    def __init__(
        self,
        budget_manager,
        account_label: str = "A",
        offset_pct: float = 0.0,
        startup_stagger_sec: float = 0.0,
        dry_run: bool = False
    ):
        self.bm = budget_manager
        self.client = budget_manager.client
        self.symbol = config.SYMBOL
        self.account_label = account_label.upper()
        self.id_prefix = f"mm_{account_label.lower()}_"
        self.offset_pct = offset_pct
        self.startup_stagger_sec = startup_stagger_sec
        self.dry_run = dry_run or getattr(config, "DRY_RUN", False)

        self.active_orders: List[dict] = []
        self.last_refresh = 0
        self.start_time = datetime.datetime.now()
        self.is_running = False

        # Phase 2: Market Reference Engine
        price_floor = float(getattr(config, "PRICE_FLOOR", 0.2612))
        price_ceiling = float(getattr(config, "PRICE_CEILING", 0.3100))
        target_mid = float(getattr(config, "TARGET_MID_PRICE", 0.2700))
        max_book_spread = float(getattr(config, "MAX_BOOK_SPREAD_PCT", 25.0))
        max_last_dev = float(getattr(config, "MAX_LAST_PRICE_DEVIATION_PCT", 5.0))
        max_staleness = float(getattr(config, "MAX_DATA_STALENESS_SEC", 25.0))

        self.ref_engine = MarketReferenceEngine(
            client=self.client,
            symbol=self.symbol,
            price_floor=price_floor,
            price_ceiling=price_ceiling,
            fallback_target_mid=target_mid,
            max_book_spread_pct=max_book_spread,
            max_last_price_deviation_pct=max_last_dev,
            max_staleness_sec=max_staleness
        )

        # Phase 3 & 9: Dynamic MM Quoting Engine
        base_spread = float(getattr(config, "BASE_SPREAD_PCT", getattr(config, "SPREAD_PCT", 1.2)))
        min_spread = float(getattr(config, "MIN_SPREAD_PCT", 0.3))
        max_spread = float(getattr(config, "MAX_SPREAD_PCT", 5.0))
        num_levels = int(getattr(config, "ORDER_LEVELS", 5))
        level_spacing = float(getattr(config, "LEVEL_SPACING_PCT", 0.4))
        min_order_sz = float(getattr(config, "MIN_ORDER_SIZE_EXBT", 100.0))
        max_order_sz = float(getattr(config, "MAX_ORDER_SIZE_EXBT", 300.0))

        self.quoting_engine = QuotingEngine(
            price_floor=price_floor,
            price_ceiling=price_ceiling,
            base_spread_pct=base_spread,
            min_spread_pct=min_spread,
            max_spread_pct=max_spread,
            num_levels=num_levels,
            level_spacing_pct=level_spacing,
            min_order_size=min_order_sz,
            max_order_size=max_order_sz
        )

        # Phase 4: Inventory Manager
        self.inventory_manager = InventoryManager(
            target_inventory_ratio=float(getattr(config, "TARGET_INVENTORY_RATIO", 0.50)),
            ratio_tolerance=float(getattr(config, "INVENTORY_TOLERANCE", 0.15)),
            max_exbt_inventory=float(getattr(config, "MAX_EXBT_INVENTORY", 250000.0)),
            max_usdt_exposure=float(getattr(config, "MAX_USDT_EXPOSURE", 25000.0)),
            max_open_order_notional=float(getattr(config, "MAX_OPEN_ORDER_NOTIONAL", 35000.0))
        )

        # Phase 5: Self-Trade Prevention Registry
        self.stp = STPRegistry()

        # Phase 7: Fill Monitor
        self.fill_monitor = FillMonitor()

        # Phase 8: Circuit Breaker
        self.circuit_breaker = CircuitBreaker(
            max_consecutive_errors=int(getattr(config, "CIRCUIT_BREAKER_MAX_ERRORS", 5)),
            cooldown_seconds=float(getattr(config, "CIRCUIT_BREAKER_COOLDOWN_SEC", 30.0)),
            max_allowed_spread_pct=max_book_spread
        )

        # Stats
        self.stats = {
            "orders_placed": 0,
            "orders_cancelled": 0,
            "errors": 0,
            "loops": 0,
            "stp_prevented": 0
        }

        mode_str = "DRY-RUN (PAPER)" if self.dry_run else "LIVE TRADING"
        logger.info(f"MarketMaker [{self.account_label}] initialized in {mode_str} mode.")

    # ─── Reference Price ─────────────────────────────────────────────────────

    def get_reference_price(self) -> Optional[float]:
        """
        Derives validated reference price from live market depth.
        Fails closed on crossed books, abnormal spreads, or corridor breaches.
        """
        try:
            res = self.ref_engine.compute_reference_price()
            if not res.is_valid:
                logger.error(f"[{self.account_label}] Reference price rejected: {res.reason}")
                self.circuit_breaker.trip(f"Invalid reference price: {res.reason}")
                return None

            self.circuit_breaker.record_success()
            logger.info(
                f"[{self.account_label}] Ref Price: {res.price:.4f} USDT "
                f"({res.source} | Bid:{res.best_bid:.4f} Ask:{res.best_ask:.4f} Spread:{res.spread_pct:.2f}%)"
            )
            return res.price
        except Exception as e:
            logger.error(f"[{self.account_label}] Error computing reference price: {e}", exc_info=True)
            self.circuit_breaker.record_api_error(str(e))
            return None

    # ─── Inventory & Balance Management ──────────────────────────────────────

    def check_inventory(self, mid_price: float) -> Tuple[bool, bool]:
        """
        Sync balances, evaluate portfolio inventory ratio, and verify circuit breaker state.
        Returns (can_buy, can_sell).
        """
        try:
            alloc_usdt = self.bm.get_allocation("USDT")
            alloc_exbt = self.bm.get_allocation("EXBT")

            usdt_free = float(alloc_usdt.get("FREE_ACTUAL", 0.0))
            usdt_locked = float(alloc_usdt.get("LOCKED_ACTUAL", 0.0))
            exbt_free = float(alloc_exbt.get("FREE_ACTUAL", 0.0))
            exbt_locked = float(alloc_exbt.get("LOCKED_ACTUAL", 0.0))

            mm_usdt = float(alloc_usdt.get("MM", 0.0))
            mm_exbt = float(alloc_exbt.get("MM", 0.0))

            # Fetch open orders from exchange to sync STP and FillMonitor
            open_orders = []
            if not self.dry_run:
                try:
                    open_orders = self.client.get_open_orders(self.symbol)
                    self.stp.sync_account_orders(self.account_label, open_orders)
                    self.fill_monitor.reconcile_open_orders(self.account_label, open_orders)
                except Exception as e:
                    logger.warning(f"[{self.account_label}] Open orders sync failed: {e}")

            # Update inventory manager
            inv_state = self.inventory_manager.update_inventory(
                usdt_free=usdt_free,
                usdt_locked=usdt_locked,
                exbt_free=exbt_free,
                exbt_locked=exbt_locked,
                reference_price=mid_price,
                open_orders=open_orders
            )

            # Circuit Breaker Evaluation
            ref_res = self.ref_engine.last_valid_result
            best_bid = ref_res.best_bid if ref_res else 0.0
            best_ask = ref_res.best_ask if ref_res else 0.0
            spread_pct = ref_res.spread_pct if ref_res else 0.0

            can_quote, cb_reason = self.circuit_breaker.evaluate(
                ref_price_valid=(ref_res is not None and ref_res.is_valid),
                ref_price_reason=ref_res.reason if ref_res else "No market data",
                best_bid=best_bid,
                best_ask=best_ask,
                spread_pct=spread_pct,
                price_floor=self.ref_engine.price_floor,
                price_ceiling=self.ref_engine.price_ceiling,
                current_price=mid_price,
                balances_verified=True,
                inventory_reason=inv_state.reason
            )

            if not can_quote:
                logger.warning(f"[{self.account_label}] Circuit breaker halted quoting: {cb_reason}")
                return False, False

            min_order_exbt = self.quoting_engine.min_order_size
            min_buy_usdt = min_order_exbt * mid_price

            can_buy = inv_state.can_quote_buy and (mm_usdt >= min_buy_usdt) and getattr(config, "MM_BUY_ENABLED", True)
            can_sell = inv_state.can_quote_sell and (mm_exbt >= min_order_exbt) and getattr(config, "MM_SELL_ENABLED", True)

            logger.info(
                f"[{self.account_label}] 💼 Inv Ratio: {inv_state.inventory_ratio*100:.1f}% "
                f"(Target: {self.inventory_manager.target_ratio*100:.1f}%) | "
                f"Skew Buy: {inv_state.buy_skew:.2f}x, Sell: {inv_state.sell_skew:.2f}x | "
                f"Can BUY: {can_buy}, Can SELL: {can_sell}"
            )
            return can_buy, can_sell

        except Exception as e:
            logger.error(f"[{self.account_label}] Inventory check failed: {e}", exc_info=True)
            self.circuit_breaker.record_api_error(str(e))
            return False, False

    # ─── Dynamic Grid Generation ─────────────────────────────────────────────

    def calculate_order_grid(self, mid_price: float) -> Tuple[List[Tuple[float, float]], List[Tuple[float, float]]]:
        """
        Generate multi-level quoting grid with realistic liquidity curve and inventory skewing.
        """
        alloc_usdt = self.bm.get_allocation("USDT")
        alloc_exbt = self.bm.get_allocation("EXBT")
        mm_usdt = float(alloc_usdt.get("MM", 0.0))
        mm_exbt = float(alloc_exbt.get("MM", 0.0))

        inv = self.inventory_manager.current_state

        plan = self.quoting_engine.generate_quote_plan(
            reference_price=mid_price,
            allocated_usdt=mm_usdt,
            allocated_exbt=mm_exbt,
            volatility_pct=0.0,
            buy_skew=inv.buy_skew,
            sell_skew=inv.sell_skew,
            can_quote_buy=inv.can_quote_buy,
            can_quote_sell=inv.can_quote_sell
        )

        if not plan.is_valid:
            logger.error(f"[{self.account_label}] Quote plan invalid: {plan.reason}")
            return [], []

        # Apply secondary account stagger offset if applicable
        buy_orders = []
        ref_res = self.ref_engine.last_valid_result
        current_best_ask = ref_res.best_ask if (ref_res and ref_res.best_ask > 0) else 999.0
        for b in plan.bids:
            p = b.price * (1.0 - self.offset_pct)
            if p >= current_best_ask:
                p = current_best_ask - 0.0004
            p = round(max(self.ref_engine.price_floor, p), self.quoting_engine.price_precision)
            if p < current_best_ask:
                buy_orders.append((p, b.amount))

        min_sell_price = float(getattr(config, "MIN_SELL_PRICE", 0.0))
        sell_orders = []
        for a in plan.asks:
            p = a.price * (1.0 + self.offset_pct)
            if min_sell_price > 0 and p < min_sell_price:
                continue  # Exclude any sell orders below minimum sell threshold
            p = round(min(self.ref_engine.price_ceiling, p), self.quoting_engine.price_precision)
            sell_orders.append((p, a.amount))

        return buy_orders, sell_orders

    # ─── Order Placement with STP ────────────────────────────────────────────

    def place_grid_orders(
        self,
        buy_orders: List[Tuple[float, float]],
        sell_orders: List[Tuple[float, float]],
        mid_price: float,
        can_buy: bool,
        can_sell: bool
    ) -> bool:
        """
        Submits ladder orders, enforcing Self-Trade Prevention (STP) and Fill Tracking.
        """
        new_orders = []
        placement_failed = False
        min_notional = float(getattr(config, "MIN_ORDER_USDT", 5.0))

        # 1. Place BUY orders
        if can_buy:
            for price, size in buy_orders:
                size = round(float(size), self.quoting_engine.amount_precision)
                if (price * size) < min_notional:
                    continue

                # SELF-TRADE PREVENTION CHECK
                is_safe, stp_reason = self.stp.check_self_trade(self.account_label, "buy", price, size)
                if not is_safe:
                    logger.warning(f"[{self.account_label}] 🚫 Order skipped: {stp_reason}")
                    self.stats["stp_prevented"] += 1
                    continue

                custom_id = f"{self.id_prefix}buy_{uuid.uuid4().hex[:10]}"

                if self.dry_run:
                    sim_id = f"sim_{custom_id}"
                    order = {"order_id": sim_id, "side": "buy", "price": price, "amount": size, "custom_id": custom_id}
                    logger.info(f"[{self.account_label}] [DRY-RUN] Simulating BUY: {size:.2f} EXBT @ {price:.4f}")
                else:
                    try:
                        order = self.client.place_order(
                            self.symbol,
                            "buy",
                            price,
                            size,
                            order_type="maker",
                            custom_id=custom_id
                        )
                    except LBankAPIError as e:
                        logger.error(f"[{self.account_label}] Buy order failed @ {price:.4f}: {e}")
                        self.circuit_breaker.record_api_error(str(e))
                        self.stats["errors"] += 1
                        placement_failed = True
                        break
                    except Exception as e:
                        logger.error(f"[{self.account_label}] Unexpected buy error: {e}")
                        self.stats["errors"] += 1
                        placement_failed = True
                        break

                oid = str(order.get("order_id"))
                self.stp.register_order(self.account_label, oid, "buy", price, size, custom_id)
                self.fill_monitor.track_order(self.account_label, oid, "buy", price, size, custom_id)
                new_orders.append(order)
                self.stats["orders_placed"] += 1
                time.sleep(0.01)

        # 2. Place SELL orders
        if can_sell and not placement_failed:
            for price, size in sell_orders:
                size = round(float(size), self.quoting_engine.amount_precision)
                if (price * size) < min_notional:
                    continue

                # SELF-TRADE PREVENTION CHECK
                is_safe, stp_reason = self.stp.check_self_trade(self.account_label, "sell", price, size)
                if not is_safe:
                    logger.warning(f"[{self.account_label}] 🚫 Order skipped: {stp_reason}")
                    self.stats["stp_prevented"] += 1
                    continue

                custom_id = f"{self.id_prefix}sell_{uuid.uuid4().hex[:10]}"

                if self.dry_run:
                    sim_id = f"sim_{custom_id}"
                    order = {"order_id": sim_id, "side": "sell", "price": price, "amount": size, "custom_id": custom_id}
                    logger.info(f"[{self.account_label}] [DRY-RUN] Simulating SELL: {size:.2f} EXBT @ {price:.4f}")
                else:
                    try:
                        order = self.client.place_order(
                            self.symbol,
                            "sell",
                            price,
                            size,
                            order_type="maker",
                            custom_id=custom_id
                        )
                    except LBankAPIError as e:
                        logger.error(f"[{self.account_label}] Sell order failed @ {price:.4f}: {e}")
                        self.circuit_breaker.record_api_error(str(e))
                        self.stats["errors"] += 1
                        placement_failed = True
                        break
                    except Exception as e:
                        logger.error(f"[{self.account_label}] Unexpected sell error: {e}")
                        self.stats["errors"] += 1
                        placement_failed = True
                        break

                oid = str(order.get("order_id"))
                self.stp.register_order(self.account_label, oid, "sell", price, size, custom_id)
                self.fill_monitor.track_order(self.account_label, oid, "sell", price, size, custom_id)
                new_orders.append(order)
                self.stats["orders_placed"] += 1
                time.sleep(0.01)

        if placement_failed:
            if new_orders:
                self.active_orders = new_orders
                return True
            return False

        if not new_orders and (can_buy or can_sell):
            logger.warning(f"[{self.account_label}] Zero orders placed in this cycle.")
            return False

        self.active_orders = new_orders
        b_cnt = len([o for o in new_orders if o.get("side") == "buy"])
        s_cnt = len([o for o in new_orders if o.get("side") == "sell"])
        logger.info(f"[{self.account_label}] ✅ Grid active: {b_cnt} Bids + {s_cnt} Asks")
        return True

    # ─── Order Cancellation & Reconciliation ─────────────────────────────────

    def cancel_stale_orders(self) -> bool:
        """Cancel only bot-owned orders for this account."""
        if self.dry_run:
            for o in self.active_orders:
                oid = str(o.get("order_id"))
                self.stp.remove_order(oid)
                self.fill_monitor.untrack_order(oid)
            self.active_orders = []
            return True

        try:
            exchange_orders = self.client.get_open_orders(self.symbol)
            owned_orders = [
                o for o in exchange_orders
                if str(o.get("custom_id") or "").startswith(self.id_prefix)
                or (self.account_label == "A" and (str(o.get("custom_id") or "").startswith("mm_buy_") or str(o.get("custom_id") or "").startswith("mm_sell_")))
            ]

            if not owned_orders:
                self.active_orders = []
                return True

            cancelled = 0
            for order in owned_orders:
                order_id = str(order.get("order_id") or "")
                if not order_id:
                    continue
                try:
                    if self.client.cancel_order(self.symbol, order_id):
                        cancelled += 1
                        self.stp.remove_order(order_id)
                        self.fill_monitor.untrack_order(order_id)
                except Exception as e:
                    logger.warning(f"[{self.account_label}] Cancel order {order_id} failed: {e}")
                time.sleep(0.01)

            self.active_orders = []
            logger.info(f"[{self.account_label}] Cancelled {cancelled}/{len(owned_orders)} owned order(s).")
            return True

        except Exception as e:
            logger.error(f"[{self.account_label}] cancel_stale_orders error: {e}", exc_info=True)
            self.circuit_breaker.record_api_error(str(e))
            return False

    def should_refresh(self, mid_price: float = 0.0) -> bool:
        time_elapsed = (time.time() - self.last_refresh) >= getattr(config, "ORDER_REFRESH_SEC", 45)
        if not time_elapsed:
            return False
        # If any of the 10 grid orders are missing, refresh immediately
        if len(self.active_orders) < 10:
            return True
        # If mid price has shifted significantly (>= 0.0006), refresh to track price wave
        if mid_price > 0 and abs(mid_price - getattr(self, "last_refresh_mid", 0.0)) >= 0.0006:
            return True
        # Keep resting orders steady and rock-solid for up to 120s if price hasn't moved
        return (time.time() - self.last_refresh) >= 120.0

    def print_status(self, mid_price: float):
        uptime = datetime.datetime.now() - self.start_time
        inv = self.inventory_manager.current_state
        fills = self.fill_monitor.get_stats()
        cb = self.circuit_breaker.get_status()

        logger.info(
            f"\n{'='*60}\n"
            f"  EXBT/USDT Market Maker [{self.account_label}] — {datetime.datetime.now().strftime('%H:%M:%S')}\n"
            f"  Uptime:             {str(uptime).split('.')[0]}\n"
            f"  Reference Mid:      {mid_price:.6f} USDT\n"
            f"  Inventory Ratio:    {inv.inventory_ratio*100:.1f}% (Skew: B {inv.buy_skew:.2f}x / S {inv.sell_skew:.2f}x)\n"
            f"  Active MM Orders:   {len(self.active_orders)}\n"
            f"  STP Prevented:      {self.stp.prevented_count}\n"
            f"  Genuine Fills:      {fills['completed_fills']} full, {fills['partial_fills']} partial "
            f"({fills['total_filled_exbt']:.1f} EXBT / ${fills['total_filled_usdt']:.1f})\n"
            f"  Circuit Breaker:    {cb['status']}\n"
            f"{'='*60}"
        )

    # ─── Main Lifecycle Loop ─────────────────────────────────────────────────

    def run(self):
        logger.info(f"🚀 EXBT/USDT Market Maker [{self.account_label}] Starting...")

        if not self.dry_run and not self.client.ping():
            logger.error(f"[{self.account_label}] ❌ Cannot connect to LBank API. Check API keys.")
            return

        # Startup reconciliation
        logger.info(f"[{self.account_label}] Startup reconciliation...")
        if not self.cancel_stale_orders():
            logger.error(f"[{self.account_label}] Startup reconciliation FAILED. Halting.")
            return

        time.sleep(getattr(config, "STARTUP_DELAY_SEC", 5))

        if self.startup_stagger_sec > 0:
            logger.info(f"[{self.account_label}] Stagger timing: waiting {self.startup_stagger_sec}s...")
            time.sleep(self.startup_stagger_sec)

        self.is_running = True
        loop_count = 0

        while self.is_running:
            try:
                loop_count += 1
                self.stats["loops"] = loop_count

                if getattr(config, "EMERGENCY_STOP", False):
                    logger.warning(f"[{self.account_label}] 🛑 EMERGENCY STOP triggered.")
                    self.cancel_stale_orders()
                    break

                mid_price = self.get_reference_price()
                if mid_price is None:
                    time.sleep(getattr(config, "LOOP_INTERVAL_SEC", 8))
                    continue

                if self.should_refresh(mid_price):
                    logger.info(f"\n[{self.account_label}] 🔄 Refreshing grid @ {mid_price:.6f} USDT")

                    old_orders = list(self.active_orders)

                    if not self.dry_run:
                        self.bm.refresh_balances()

                    can_buy, can_sell = self.check_inventory(mid_price)
                    buy_orders, sell_orders = self.calculate_order_grid(mid_price)

                    placement_ok = self.place_grid_orders(
                        buy_orders,
                        sell_orders,
                        mid_price,
                        can_buy,
                        can_sell
                    )

                    if placement_ok:
                        # Cancel previous grid AFTER new orders are already live (True Zero Gap)
                        if old_orders:
                            for old_o in old_orders:
                                oid = old_o.get("order_id")
                                if oid:
                                    if not self.dry_run:
                                        try:
                                            self.client.cancel_order(self.symbol, oid)
                                        except Exception:
                                            pass
                                    self.stp.remove_order(oid)
                                    self.fill_monitor.untrack_order(oid)
                                    time.sleep(0.01)
                        self.last_refresh = time.time()
                        self.last_refresh_mid = mid_price
                    else:
                        logger.error(f"[{self.account_label}] Refresh failed; keeping existing orders.")

                if loop_count % 5 == 0:
                    self.print_status(mid_price)

                time.sleep(getattr(config, "LOOP_INTERVAL_SEC", 8))

            except KeyboardInterrupt:
                logger.info(f"[{self.account_label}] Interrupted by user.")
                break
            except Exception as e:
                logger.error(f"[{self.account_label}] Loop error: {e}", exc_info=True)
                self.circuit_breaker.record_api_error(str(e))
                time.sleep(getattr(config, "LOOP_INTERVAL_SEC", 8))

        logger.info(f"[{self.account_label}] Stopping and cleaning up owned orders...")
        self.cancel_stale_orders()
        logger.info(f"[{self.account_label}] Bot stopped.")
