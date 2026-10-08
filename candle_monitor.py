"""
candle_monitor.py — Passive Market Candle Monitor
Ingests public trades from LBank (/v2/trades.do), constructs genuine 1-minute OHLCV candles,
and detects barcode / artificial trade patterns without executing any orders.
"""

import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Optional

logger = logging.getLogger("candle_monitor")


@dataclass
class Candle1m:
    minute_timestamp: int  # Epoch minute (e.g. ts // 60 * 60)
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int = 0


class MarketCandleMonitor:
    def __init__(self, client, symbol: str):
        self.client = client
        self.symbol = symbol
        self.candles: Dict[int, Candle1m] = {}  # minute_ts -> Candle1m
        self.seen_trade_ids = set()
        self.daily_real_volume = 0.0
        self.daily_trade_count = 0
        self.last_poll_time = 0.0

    def poll_recent_trades(self) -> List[dict]:
        """Fetch latest public trades tape from LBank and build 1-minute OHLCV candles."""
        try:
            res = self.client._get(f"/v2/trades.do?symbol={self.symbol}&size=50")
            trades = res.get("data", [])
        except Exception as e:
            logger.warning(f"Failed to poll public trades: {e}")
            return []

        self.last_poll_time = time.time()
        new_trades = []

        for t in trades:
            tid = str(t.get("tid") or t.get("date_ms"))
            if tid in self.seen_trade_ids:
                continue
            self.seen_trade_ids.add(tid)
            new_trades.append(t)

            try:
                price = float(t.get("price", 0.0))
                amount = float(t.get("amount", 0.0))
                ts_ms = int(t.get("date_ms", time.time() * 1000))
                sec = ts_ms // 1000
                minute_ts = (sec // 60) * 60

                self.daily_real_volume += amount
                self.daily_trade_count += 1

                if minute_ts not in self.candles:
                    self.candles[minute_ts] = Candle1m(
                        minute_timestamp=minute_ts,
                        open=price,
                        high=price,
                        low=price,
                        close=price,
                        volume=amount,
                        trade_count=1
                    )
                else:
                    c = self.candles[minute_ts]
                    c.high = max(c.high, price)
                    c.low = min(c.low, price)
                    c.close = price
                    c.volume += amount
                    c.trade_count += 1

            except Exception as e:
                logger.debug(f"Trade parsing error: {e}")

        # Keep cache bounded to last 60 minutes
        if len(self.candles) > 60:
            oldest_keys = sorted(self.candles.keys())[:-60]
            for k in oldest_keys:
                del self.candles[k]

        if len(self.seen_trade_ids) > 1000:
            self.seen_trade_ids = set(list(self.seen_trade_ids)[-500:])

        return new_trades

    def get_latest_candle(self) -> Optional[dict]:
        """Returns the most recent 1-minute OHLCV candle as a dictionary."""
        if not self.candles:
            return None
        latest_ts = max(self.candles.keys())
        c = self.candles[latest_ts]
        return {
            "timestamp": c.minute_timestamp,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": c.volume,
            "trades": c.trade_count
        }

    def detect_barcode_pattern(self, window_candles: int = 5) -> bool:
        """
        Detects if consecutive candles have identical artificial flat highs and lows (barcode).
        """
        if len(self.candles) < window_candles:
            return False

        sorted_candles = [self.candles[k] for k in sorted(self.candles.keys())[-window_candles:]]
        highs = [round(c.high, 4) for c in sorted_candles]
        lows = [round(c.low, 4) for c in sorted_candles]

        # If all highs and all lows in the window are identical, it is a barcode
        if len(set(highs)) == 1 and len(set(lows)) == 1:
            return True
        return False

