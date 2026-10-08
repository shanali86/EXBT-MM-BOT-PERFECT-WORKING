import os
import sys
import time
import logging
import threading
import argparse
from pathlib import Path

def setup_logging():
    import config
    Path("logs").mkdir(exist_ok=True)
    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    level = getattr(logging, getattr(config, "LOG_LEVEL", "INFO").upper(), logging.INFO)
    handlers = []
    if getattr(config, "LOG_TO_CONSOLE", True):
        handlers.append(logging.StreamHandler())
    handlers.append(logging.FileHandler(getattr(config, "LOG_FILE", "logs/bot.log"), encoding="utf-8"))
    logging.basicConfig(level=level, format=log_format, handlers=handlers)

setup_logging()
logger = logging.getLogger("main")

from lbank_client import LBankClient
from market_maker import MarketMaker
from volume_bot import VolumeBot
from candle_bot import CandleBot
from budget_manager import BudgetManager
from stp_registry import STPRegistry
from fill_monitor import FillMonitor
import config

try:
    import fcntl
except ImportError:
    fcntl = None


def run_market_maker(bm, mm_bot):
    try:
        mm_bot.run()
    except Exception as e:
        logger.error(f"Market Maker [{mm_bot.account_label}] crashed: {e}", exc_info=True)


def run_volume_bot(bm, vol_bot):
    try:
        vol_bot.run()
    except Exception as e:
        logger.error(f"Volume Bot crashed: {e}", exc_info=True)


def run_candle_bot(bm, candle_bot):
    try:
        candle_bot.run()
    except Exception as e:
        logger.error(f"Candle Monitor crashed: {e}", exc_info=True)


def get_order_side(order: dict) -> str:
    """Safely extract the side from various potential order schemas."""
    return str(order.get('side', order.get('type', 'unknown'))).lower()


def print_health_monitor(bm_a, bm_b=None, mm_bot_a=None, mm_bot_b=None, vol_bot=None, candle_bot=None):
    try:
        alloc_usdt_a = bm_a.get_allocation("USDT") if bm_a else {}
        alloc_exbt_a = bm_a.get_allocation("EXBT") if bm_a else {}
        alloc_usdt_b = bm_b.get_allocation("USDT") if bm_b else {}
        alloc_exbt_b = bm_b.get_allocation("EXBT") if bm_b else {}

        mid_price = mm_bot_a.get_reference_price() if mm_bot_a else 0.0
        stp = STPRegistry()
        fills = FillMonitor().get_stats()

        logger.info("=================================================")
        logger.info("LIVE DUAL-ACCOUNT TRADING STATUS (COMPLIANT MM)")
        logger.info("=================================================\n")

        # Account A MM
        if mm_bot_a:
            buys_a = sum(1 for o in mm_bot_a.active_orders if get_order_side(o) == 'buy')
            sells_a = sum(1 for o in mm_bot_a.active_orders if get_order_side(o) == 'sell')
            inv_a = mm_bot_a.inventory_manager.current_state
            logger.info("Market Maker [Account A]:")
            logger.info(f"Status: {'DRY-RUN' if mm_bot_a.dry_run else 'LIVE TRADING'}")
            logger.info(f"Active BUY: {buys_a} | Active SELL: {sells_a}")
            logger.info(f"Inventory Ratio: {inv_a.inventory_ratio*100:.1f}% (Skew: B {inv_a.buy_skew:.2f}x / S {inv_a.sell_skew:.2f}x)")
            logger.info(f"Free: {alloc_usdt_a.get('FREE_ACTUAL', 0.0):.2f} USDT | {alloc_exbt_a.get('FREE_ACTUAL', 0.0):.2f} EXBT\n")

        # Account B MM
        if mm_bot_b:
            buys_b = sum(1 for o in mm_bot_b.active_orders if get_order_side(o) == 'buy')
            sells_b = sum(1 for o in mm_bot_b.active_orders if get_order_side(o) == 'sell')
            inv_b = mm_bot_b.inventory_manager.current_state
            logger.info("Market Maker [Account B]:")
            logger.info(f"Status: {'DRY-RUN' if mm_bot_b.dry_run else 'LIVE TRADING'} (Staggered Zero-Gap)")
            logger.info(f"Active BUY: {buys_b} | Active SELL: {sells_b}")
            logger.info(f"Inventory Ratio: {inv_b.inventory_ratio*100:.1f}% (Skew: B {inv_b.buy_skew:.2f}x / S {inv_b.sell_skew:.2f}x)")
            logger.info(f"Free: {alloc_usdt_b.get('FREE_ACTUAL', 0.0):.2f} USDT | {alloc_exbt_b.get('FREE_ACTUAL', 0.0):.2f} EXBT\n")

        # Self-Trade Prevention & Fill Metrics
        logger.info(f"STP Status: ACTIVE | Blocked Crossings: {stp.prevented_count}")
        logger.info(
            f"Genuine Fills: {fills['completed_fills']} full, {fills['partial_fills']} partial | "
            f"Filled: {fills['total_filled_exbt']:.1f} EXBT (${fills['total_filled_usdt']:.1f})\n"
        )

        # Market Candle Monitor
        logger.info("Market Candle Monitor:")
        if candle_bot is not None:
            logger.info(f"Status: ACTIVE (4-Pattern Zero-Loss) | Last Action: {getattr(candle_bot, 'last_action', 'Running')}")
            logger.info(f"Volume Painted Today: {candle_bot.total_volume_today:.1f} EXBT | Candles: {candle_bot.candles_painted_today}\n")
        else:
            logger.info("Status: DISABLED\n")

        logger.info(f"Reference Mid: {mid_price:.6f} USDT" if mid_price else "Reference Mid: AWAITING VALIDATION")
        logger.info("=================================================")
    except Exception as e:
        logger.exception(f"Health monitor error: {e}")


_INSTANCE_LOCK_FILE = "/tmp/exbt_mm_bot.lock"
_instance_lock_handle = None


def acquire_single_instance_lock():
    """
    Prevent more than one instance of this bot from running.
    The OS automatically releases the lock when the process exits.
    """
    global _instance_lock_handle

    if fcntl is None:
        # Windows development environment fallback
        return

    try:
        _instance_lock_handle = open(_INSTANCE_LOCK_FILE, "w")
        fcntl.flock(
            _instance_lock_handle.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB
        )
    except (BlockingIOError, IOError):
        logger.error(
            "Another EXBT bot instance is already running. "
            "Refusing to start duplicate process."
        )
        sys.exit(2)

    _instance_lock_handle.seek(0)
    _instance_lock_handle.truncate()
    _instance_lock_handle.write(str(os.getpid()))
    _instance_lock_handle.flush()

    logger.info(
        f"Single-instance lock acquired. PID={os.getpid()} "
        f"Lock={_INSTANCE_LOCK_FILE}"
    )


def main():
    parser = argparse.ArgumentParser(description="EXBT/USDT Compliant Market Maker")
    parser.add_argument("--dry-run", action="store_true", help="Run in paper/dry-run mode without placing live orders")
    args = parser.parse_args()

    acquire_single_instance_lock()

    dry_run_mode = args.dry_run or getattr(config, "DRY_RUN", False)
    if dry_run_mode:
        logger.info("🛡️ RUNNING IN DRY-RUN (PAPER) MODE — No live orders will be sent to exchange.")

    if config.API_KEY == "YOUR_LBANK_API_KEY_HERE" and not dry_run_mode:
        logger.error("Please set your API_KEY in config.py before running!")
        sys.exit(1)

    logger.info("Starting up compliant trading system...")

    # 1. LBank API/clients for Account A and Account B
    client_a = LBankClient(config.API_KEY, config.SECRET_KEY, config.USE_RSA)
    if not dry_run_mode and not client_a.ping():
        logger.error("Account A API connection FAILED. DO NOT START LIVE TRADING.")
        sys.exit(1)

    client_b = LBankClient(config.API_KEY_B, config.SECRET_KEY_B, config.USE_RSA)
    if not dry_run_mode and not client_b.ping():
        logger.error("Account B API connection FAILED. DO NOT START LIVE TRADING.")
        sys.exit(1)

    # 2. Budget Managers for both accounts
    bm_a = BudgetManager(client_a)
    bm_b = BudgetManager(client_b)

    # 3. Balance verification
    if not dry_run_mode:
        bm_a.refresh_balances()
        bm_b.refresh_balances()
        if bm_a.balances.get("status") == "BALANCE_UNKNOWN":
            logger.error("Account A balance verification FAILED.")
            sys.exit(1)
        if bm_b.balances.get("status") == "BALANCE_UNKNOWN":
            logger.error("Account B balance verification FAILED.")
            sys.exit(1)

    # 4. Initialize Dual Market Maker bots (Account A + Account B)
    step_offset = (config.LEVEL_STEP_PCT / 100.0) / 2.0
    stagger_sec = float(getattr(config, "MM_STAGGER_DELAY_SEC", 20.0))

    mm_bot_a = MarketMaker(bm_a, account_label="A", offset_pct=0.0, startup_stagger_sec=0.0, dry_run=dry_run_mode)
    mm_bot_b = MarketMaker(bm_b, account_label="B", offset_pct=step_offset, startup_stagger_sec=stagger_sec, dry_run=dry_run_mode)

    # 5. Market data validation — fail closed.
    mid_price = mm_bot_a.get_reference_price()

    if (mid_price is None or float(mid_price) <= 0) and not dry_run_mode:
        logger.error(
            "Market data validation BLOCKED: unsafe/invalid order-book "
            "reference. DO NOT START LIVE TRADING."
        )
        sys.exit(1)

    if mid_price:
        logger.info(f"Market data validation PASSED: {config.SYMBOL.upper()}={float(mid_price):.4f}")

    # Initialize Volume Bot (Account B) - compliant
    vol_bot = (
        VolumeBot(bm_b)
        if getattr(config, "VOLUME_BOT_ENABLED", False) and not dry_run_mode
        else None
    )

    # Initialize Candle Monitor (Account B) - passive
    candle_bot = (
        CandleBot(bm_b)
        if getattr(config, "CANDLE_BOT_ENABLED", False)
        else None
    )

    # Print initial health monitor
    print_health_monitor(bm_a, bm_b, mm_bot_a, mm_bot_b, vol_bot, candle_bot)

    threads = []

    # 6. Order Book Bots (Account A + Account B)
    mm_thread_a = threading.Thread(target=run_market_maker, args=(bm_a, mm_bot_a), name="MarketMaker_A", daemon=True)
    threads.append(mm_thread_a)

    mm_thread_b = threading.Thread(target=run_market_maker, args=(bm_b, mm_bot_b), name="MarketMaker_B", daemon=True)
    threads.append(mm_thread_b)

    # 7. Volume Bot
    if getattr(config, "VOLUME_BOT_ENABLED", False) and vol_bot:
        vb_thread = threading.Thread(target=run_volume_bot, args=(bm_b, vol_bot), name="VolumeBot", daemon=True)
        threads.append(vb_thread)

    # 8. Candle Monitor
    if getattr(config, "CANDLE_BOT_ENABLED", False) and candle_bot:
        cb_thread = threading.Thread(
            target=run_candle_bot,
            args=(bm_b, candle_bot),
            name="CandleMonitor",
            daemon=True
        )
        threads.append(cb_thread)

    for t in threads:
        t.start()

    # 9. Health monitor loop
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(60)
            print_health_monitor(bm_a, bm_b, mm_bot_a, mm_bot_b, vol_bot, candle_bot)
    except KeyboardInterrupt:
        logger.info("\nShutdown signal received. Stopping bots...")
        mm_bot_a.is_running = False
        mm_bot_b.is_running = False

        if vol_bot is not None:
            vol_bot.is_running = False

        if candle_bot is not None:
            candle_bot.is_running = False

    logger.info("All bots stopped.")


if __name__ == "__main__":
    main()
