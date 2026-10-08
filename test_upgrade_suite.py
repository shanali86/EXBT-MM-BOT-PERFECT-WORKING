"""
test_upgrade_suite.py — Comprehensive MM Upgrade Verification Suite
Tests all 14 market scenarios for the upgraded Market Maker components:
ReferenceEngine, QuotingEngine, InventoryManager, STPRegistry,
CircuitBreaker, FillMonitor, and CandleMonitor.
"""

import unittest
from unittest.mock import MagicMock
import time

from reference_engine import MarketReferenceEngine, ReferencePriceResult
from quoting_engine import QuotingEngine
from inventory_manager import InventoryManager
from stp_registry import STPRegistry
from circuit_breaker import CircuitBreaker
from fill_monitor import FillMonitor
from candle_monitor import MarketCandleMonitor


class TestUpgradeSuite(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        # Reset STP singleton
        self.stp = STPRegistry()
        self.stp.reset()

    # 1. Dynamic Midpoint Tracking
    def test_01_dynamic_midpoint(self):
        self.mock_client.get_orderbook.return_value = {
            "bids": [["0.2680", "500"]],
            "asks": [["0.2720", "500"]]
        }
        engine = MarketReferenceEngine(self.mock_client, "exbt_usdt", 0.20, 0.35, 0.27)
        res = engine.compute_reference_price()
        self.assertTrue(res.is_valid)
        self.assertAlmostEqual(res.price, 0.2700, places=4)
        self.assertEqual(res.source, "orderbook_mid")

    # 2. Crossed Book Detection & Failsafe
    def test_02_crossed_book(self):
        self.mock_client.get_orderbook.return_value = {
            "bids": [["0.2750", "500"]],
            "asks": [["0.2700", "500"]]
        }
        engine = MarketReferenceEngine(self.mock_client, "exbt_usdt", 0.20, 0.35, 0.27)
        res = engine.compute_reference_price()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.source, "crossed_book")

    # 3. Spread Boundary Rejection
    def test_03_wide_spread_rejection(self):
        self.mock_client.get_orderbook.return_value = {
            "bids": [["0.2500", "500"]],
            "asks": [["0.2800", "500"]]  # ~10.7% spread > 5.0%
        }
        engine = MarketReferenceEngine(self.mock_client, "exbt_usdt", 0.20, 0.35, 0.27, max_allowed_spread_pct=5.0)
        res = engine.compute_reference_price()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.source, "wide_spread")

    # 4. Fail-Closed Corridor Guard (Floor Breach)
    def test_04_corridor_floor_breach(self):
        self.mock_client.get_orderbook.return_value = {
            "bids": [["0.1840", "500"]],
            "asks": [["0.1860", "500"]]  # Mid 0.1850 < floor 0.20, spread ~1.07%
        }
        engine = MarketReferenceEngine(self.mock_client, "exbt_usdt", 0.20, 0.35, 0.27)
        res = engine.compute_reference_price()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.source, "corridor_breach_floor")

    # 5. Fail-Closed Corridor Guard (Ceiling Breach)
    def test_05_corridor_ceiling_breach(self):
        self.mock_client.get_orderbook.return_value = {
            "bids": [["0.3600", "500"]],
            "asks": [["0.3700", "500"]]  # Mid 0.3650 > ceiling 0.35
        }
        engine = MarketReferenceEngine(self.mock_client, "exbt_usdt", 0.20, 0.35, 0.27)
        res = engine.compute_reference_price()
        self.assertFalse(res.is_valid)
        self.assertEqual(res.source, "corridor_breach_ceiling")

    # 6. Non-Uniform Depth Curve Generation
    def test_06_non_uniform_depth_curve(self):
        q_engine = QuotingEngine(base_spread_pct=1.0, num_levels=5, min_order_size=50, max_order_size=500)
        plan = q_engine.generate_quote_plan(reference_price=0.2700, allocated_usdt=500, allocated_exbt=2000)
        self.assertTrue(plan.is_valid)
        self.assertEqual(len(plan.bids), 5)
        self.assertEqual(len(plan.asks), 5)
        # Check ascending spacing on bids
        for i in range(len(plan.bids) - 1):
            self.assertGreater(plan.bids[i].price, plan.bids[i+1].price)

    # 7. Inventory Sizing Multiplier (Excess EXBT Skew)
    def test_07_inventory_excess_exbt(self):
        inv = InventoryManager(target_inventory_ratio=0.50, ratio_tolerance=0.10)
        # 1000 USDT cash + 10,000 EXBT @ 0.27 = $2,700 EXBT -> total $3,700 -> ratio 73% > 60%
        state = inv.update_inventory(usdt_free=1000, usdt_locked=0, exbt_free=10000, exbt_locked=0, reference_price=0.27)
        self.assertGreater(state.inventory_ratio, 0.60)
        self.assertLess(state.buy_skew, 1.0)
        self.assertGreater(state.sell_skew, 1.0)

    # 8. Inventory Sizing Multiplier (Excess USDT Skew)
    def test_08_inventory_excess_usdt(self):
        inv = InventoryManager(target_inventory_ratio=0.50, ratio_tolerance=0.10)
        # 5000 USDT cash + 1,000 EXBT @ 0.27 = $270 EXBT -> ratio 5% < 40%
        state = inv.update_inventory(usdt_free=5000, usdt_locked=0, exbt_free=1000, exbt_locked=0, reference_price=0.27)
        self.assertLess(state.inventory_ratio, 0.40)
        self.assertGreater(state.buy_skew, 1.0)
        self.assertLess(state.sell_skew, 1.0)

    # 9. Hard Inventory Cap Enforcement
    def test_09_hard_inventory_caps(self):
        inv = InventoryManager(max_exbt_inventory=150000)
        state = inv.update_inventory(usdt_free=5000, usdt_locked=0, exbt_free=160000, exbt_locked=0, reference_price=0.27)
        self.assertFalse(state.can_quote_buy)

    # 10. STP Registry Buy-into-Sell Block
    def test_10_stp_buy_into_sell_block(self):
        self.stp.register_order(account="A", order_id="ord_a_sell", side="sell", price=0.2710, size=100)
        # Account B tries to BUY at 0.2710 or higher -> MUST BE BLOCKED
        is_safe, reason = self.stp.check_self_trade(account="B", side="buy", price=0.2710, size=100)
        self.assertFalse(is_safe)
        self.assertIn("STP BLOCKED", reason)

    # 11. STP Registry Sell-into-Buy Block
    def test_11_stp_sell_into_buy_block(self):
        self.stp.register_order(account="A", order_id="ord_a_buy", side="buy", price=0.2680, size=100)
        # Account B tries to SELL at 0.2680 or lower -> MUST BE BLOCKED
        is_safe, reason = self.stp.check_self_trade(account="B", side="sell", price=0.2680, size=100)
        self.assertFalse(is_safe)
        self.assertIn("STP BLOCKED", reason)

    # 12. STP Independent Counterparty Acceptance
    def test_12_stp_safe_orders(self):
        self.stp.register_order(account="A", order_id="ord_a_buy", side="buy", price=0.2680, size=100)
        self.stp.register_order(account="A", order_id="ord_a_sell", side="sell", price=0.2720, size=100)
        # Account B buys strictly below resting sell (e.g. 0.2700) and sells strictly above resting buy (0.2700)
        is_safe, _ = self.stp.check_self_trade(account="B", side="buy", price=0.2700, size=100)
        self.assertTrue(is_safe)

    # 13. Circuit Breaker API Error Streak Trip
    def test_13_circuit_breaker_error_trip(self):
        cb = CircuitBreaker(max_consecutive_errors=3, cooldown_seconds=10)
        cb.record_api_error("Err 1")
        cb.record_api_error("Err 2")
        self.assertFalse(cb.is_tripped)
        cb.record_api_error("Err 3")
        self.assertTrue(cb.is_tripped)
        can_quote, _ = cb.evaluate(True, "OK", 0.268, 0.272, 1.5, 0.20, 0.35, 0.27)
        self.assertFalse(can_quote)

    # 14. Passive Candle Monitor 1m OHLCV Aggregation
    def test_14_candle_monitor(self):
        now_ms = int(time.time() * 1000)
        self.mock_client._get.return_value = {
            "data": [
                {"tid": "t1", "price": "0.2700", "amount": "100", "date_ms": now_ms},
                {"tid": "t2", "price": "0.2750", "amount": "200", "date_ms": now_ms + 1000},
                {"tid": "t3", "price": "0.2690", "amount": "150", "date_ms": now_ms + 2000},
            ]
        }
        monitor = MarketCandleMonitor(self.mock_client, "exbt_usdt")
        new_trades = monitor.poll_recent_trades()
        self.assertEqual(len(new_trades), 3)
        candle = monitor.get_latest_candle()
        self.assertIsNotNone(candle)
        self.assertEqual(candle["open"], 0.2700)
        self.assertEqual(candle["high"], 0.2750)
        self.assertEqual(candle["low"], 0.2690)
        self.assertEqual(candle["volume"], 450.0)


if __name__ == "__main__":
    unittest.main()
