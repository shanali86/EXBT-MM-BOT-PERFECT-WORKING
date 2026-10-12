# ==============================================================================
#  EXBT BTC-Style Institutional Market Regime Engine
#  Simulates authentic crypto price action (BTC/ETH-style organic waves):
#  - Multi-candle trend runs (higher highs & higher lows)
#  - Realistic resting shelves / consolidations (20-45 mins)
#  - Controlled 38%-50% Fibonacci pullbacks (never crashing to fixed bounds)
#  - Non-repeating incommensurate fractal noise
#  Strictly safeguarded by [PRICE_FLOOR, PRICE_CEILING].
# ==============================================================================

import math
import time
import random
import json
import os
import threading
import logging

try:
    import config
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    import config

logger = logging.getLogger("wave_engine")

_engine_lock = threading.Lock()
_engine_instance = None


class MarketRegimeEngine:
    """
    BTC-Style Institutional Market Regime Engine.
    Breaks artificial rectangular box ping-pong and generates organic multi-hour wave cycles:
    1. Higher highs and higher lows structure (ascending wave trends).
    2. Consolidation shelves that hold support for 20-50 minutes.
    3. Shallow healthy pullbacks (38.2% - 50% retracements).
    4. Non-periodic fractal micro-noise for continuous organic life.
    """

    def __init__(self):
        self.state_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data",
            "regime_state.json"
        )
        self.safe_floor = float(getattr(config, "PRICE_FLOOR", 0.3500))
        # Cap ceiling strictly below external sell wall (0.4060) so candles never get squashed
        self.safe_ceiling = min(float(getattr(config, "CANDLE_MAX_PRICE", 0.4085)), 0.4055)

        # Recent swing anchor points to maintain higher lows / higher highs
        self.recent_swing_low = max(self.safe_floor, 0.3960)
        self.recent_swing_high = min(self.safe_ceiling, 0.4050)

        # Incommensurate prime-period waves for continuous non-repeating fractal noise
        self.primes = [
            {"period": 317.0, "amp": 0.00035, "phase": 1.14},
            {"period": 139.0, "amp": 0.00028, "phase": 2.71},
            {"period": 53.0,  "amp": 0.00018, "phase": 0.88},
            {"period": 19.0,  "amp": 0.00012, "phase": 3.42},
        ]

        self.state = self._load_or_init_state()

    def _load_or_init_state(self) -> dict:
        now = time.time()
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                    if data.get("end_time", 0) > now:
                        logger.info(f"Loaded active regime state: {data.get('regime')} (ends in {int(data['end_time'] - now)}s)")
                        return data
                    else:
                        last_p = float(data.get("target_price", 0.4080))
                        last_p = max(self.safe_floor, min(self.safe_ceiling, last_p))
                        logger.info(f"Transitioning cleanly from {last_p:.4f} into organic wave cycle")
                        self.state = self._create_new_state("ZONE_CONSOLIDATION", now, last_p, last_p, duration=1500.0)
                        self._save_state()
                        return self.state
        except Exception as e:
            logger.warning(f"Could not load regime state: {e}. Initializing fresh.")

        self.state = self._create_new_state("ZONE_CONSOLIDATION", now, 0.4080, 0.4080, duration=1500.0)
        self._save_state()
        return self.state

    def _save_state(self):
        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist regime state: {e}")

    def _quintic_ease(self, t: float) -> float:
        """C2 continuous smoothstep: 6t^5 - 15t^4 + 10t^3. Velocity & acceleration = 0 at bounds."""
        t = max(0.0, min(1.0, t))
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

    def _create_new_state(self, regime: str, start_time: float, start_price: float, target_price: float, duration: float = 1800.0) -> dict:
        state = {
            "regime": regime,
            "start_time": start_time,
            "end_time": start_time + duration,
            "start_price": round(start_price, 4),
            "target_price": round(target_price, 4),
            "shelf_price": round(target_price, 4),
            "shelf_amp": round(random.uniform(0.0007, 0.0012), 4),
            "prev_regime": getattr(self, "state", {}).get("regime", None) if hasattr(self, "state") else None
        }
        return state

    def _get_effective_bounds(self) -> Tuple[float, float]:
        """
        Dynamically computes effective floor and ceiling:
        - Hard floor: 0.3700
        - Hard ceiling: 0.4085 (strictly sub-0.41)
        - If Trap Flush is active: ceiling is locked to trap ceiling below buyer's entry
        """
        floor = float(getattr(config, "PRICE_FLOOR", 0.3700))
        ceil = float(getattr(config, "CANDLE_MAX_PRICE", 0.4085))

        trap_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "trap_state.json")
        try:
            if os.path.exists(trap_file):
                with open(trap_file, "r") as f:
                    trap = json.load(f)
                    if trap.get("trap_active") and time.time() < trap.get("expires_at", 0):
                        locked_c = float(trap.get("locked_ceiling", ceil))
                        ceil = min(ceil, locked_c)
        except Exception:
            pass

        return floor, ceil

    def _check_trap_active(self, now: float) -> Tuple[bool, dict]:
        trap_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "trap_state.json")
        try:
            if os.path.exists(trap_file):
                with open(trap_file, "r") as f:
                    trap = json.load(f)
                    if trap.get("trap_active") and now < trap.get("expires_at", 0):
                        return True, trap
        except Exception:
            pass
        return False, {}

    def _transition_next_regime(self, now: float, current_price: float):
        prev = self.state.get("regime", "ZONE_CONSOLIDATION")
        r = random.random()

        # Update swing boundaries
        self.recent_swing_high = max(self.recent_swing_high, current_price)
        self.recent_swing_low = min(self.recent_swing_low, current_price)

        safe_floor, safe_ceiling = self._get_effective_bounds()

        # ─── PREDATORY TRAP FLUSH OVERRIDE ───────────────────────────────────
        # If an external user bought >= $100 USDT, lock ceiling and force immediate panic dump!
        trap_active, trap_data = self._check_trap_active(now)
        if trap_active:
            regime = "RETRACEMENT"
            duration = random.uniform(600, 1500)  # 10 to 25 mins
            flush_drop = random.uniform(0.0020, 0.0040)
            target = round(max(safe_floor, trap_data["buyer_fill_price"] - flush_drop), 4)
            self.last_target_price = target
            self.state = self._create_new_state(regime, now, current_price, target, duration)
            self._save_state()
            logger.warning(
                f"🚨 PREDATORY FLUSH ACTIVE: External user bought @ {trap_data['buyer_fill_price']:.4f}! "
                f"Dumping price down to {target:.4f} (Ceiling locked <= {safe_ceiling:.4f})"
            )
            return

        # ─── 1. MACRO DRIFT (8-Hour Smooth Baseline Wave) ────────────────────
        macro_period = 28800.0  # 8 hours
        macro_drift = 0.0038 * math.sin((now / macro_period) * 2.0 * math.pi)
        macro_baseline = 0.3995 + macro_drift

        # ─── 2. ASYMMETRIC ORGANIC REGIME TRANSITIONS ────────────────────────
        if prev == "IMPULSIVE_UP" or current_price >= (safe_ceiling - 0.0035):
            # After an impulsive upward drive:
            if r < 0.55:
                regime = "ZONE_CONSOLIDATION"
                duration = random.uniform(600, 1300)   # 10 to 22 mins
                target = round(current_price + random.uniform(-0.0012, 0.0008), 4)
            else:
                regime = "RETRACEMENT"
                duration = random.uniform(480, 960)    # 8 to 16 mins
                retrace_amt = random.uniform(0.0030, 0.0068)
                target = round(max(safe_floor + 0.0050, current_price - retrace_amt), 4)

        elif prev == "RETRACEMENT" or current_price <= (macro_baseline - 0.0050):
            # After a pullback / near macro low:
            # 65% chance of an upward recovery rally
            # 35% chance of accumulation base
            if r < 0.65:
                regime = "ZONE_EXPANSION"
                duration = random.uniform(700, 1400)   # 11 to 23 mins
                push_amt = random.uniform(0.0035, 0.0075)
                target = round(min(safe_ceiling, current_price + push_amt), 4)
            else:
                regime = "ZONE_CONSOLIDATION"
                duration = random.uniform(600, 1100)   # 10 to 18 mins
                target = round(current_price + random.uniform(-0.0008, 0.0014), 4)

        elif prev in ("ZONE_CONSOLIDATION", "CONSOLIDATION"):
            # From a resting shelf:
            if macro_drift >= 0:
                up_prob = 0.65
            else:
                up_prob = 0.45

            if r < up_prob:
                regime = "IMPULSIVE_UP"
                duration = random.uniform(600, 1200)   # 10 to 20 mins
                push_amt = random.uniform(0.0030, 0.0070)
                target = round(min(safe_ceiling, current_price + push_amt), 4)
            else:
                regime = "RETRACEMENT"
                duration = random.uniform(480, 900)    # 8 to 15 mins
                target = round(max(safe_floor + 0.0050, current_price - random.uniform(0.0025, 0.0055)), 4)

        else: # ZONE_EXPANSION or other
            if r < 0.55:
                regime = "ZONE_CONSOLIDATION"
                duration = random.uniform(600, 1200)   # 10 to 20 mins
                target = round(current_price + random.uniform(-0.0010, 0.0010), 4)
            else:
                regime = "RETRACEMENT"
                duration = random.uniform(480, 900)    # 8 to 15 mins
                target = round(max(safe_floor + 0.0050, current_price - random.uniform(0.0030, 0.0060)), 4)

        # ─── 3. ANTI-SNIPER & ANTI-REPEAT PATTERN RULE ───────────────────────
        last_target = getattr(self, "last_target_price", None)
        if last_target is not None and abs(target - last_target) < 0.0016:
            shift = random.choice([-0.0025, 0.0025])
            target += shift

        # Strictly enforce safety envelope: [safe_floor, safe_ceiling]
        target = round(max(safe_floor, min(safe_ceiling, target)), 4)
        self.last_target_price = target

        self.state = self._create_new_state(regime, now, current_price, target, duration)
        self._save_state()
        logger.info(
            f"🌊 Anti-Sniper Market Wave Transition: {prev} -> {regime} | "
            f"Start: {current_price:.4f} -> Target: {target:.4f} (Macro: {macro_baseline:.4f}) | "
            f"Duration: {int(duration / 60)} min"
        )

    def _eval_base_price(self, t: float) -> float:
        st = self.state["start_time"]
        et = self.state["end_time"]
        regime = self.state["regime"]
        sp = self.state["start_price"]
        tp = self.state["target_price"]

        if et <= st:
            return sp

        progress = max(0.0, min(1.0, (t - st) / (et - st)))

        if regime in ("IMPULSIVE_UP", "ZONE_EXPANSION", "RETRACEMENT"):
            eased = self._quintic_ease(progress)
            return sp + (tp - sp) * eased
        elif regime in ("ZONE_CONSOLIDATION", "CONSOLIDATION"):
            shelf = self.state.get("shelf_price", tp)
            amp = self.state.get("shelf_amp", 0.0009)
            drift_wave = amp * math.sin(progress * math.pi * 4.0)
            return shelf + drift_wave
        else:
            eased = self._quintic_ease(progress)
            shelf = sp + (tp - sp) * eased
            amp = self.state.get("shelf_amp", 0.0006)
            drift_wave = amp * math.sin(progress * math.pi * 3.0)
            return shelf + drift_wave

    def get_anti_sniper_wave(self, now: float = None):
        if now is None:
            now = time.time()

        with _engine_lock:
            # Check if current regime expired
            if now >= self.state.get("end_time", 0):
                curr_base = self._eval_base_price(self.state.get("end_time", now))
                self._transition_next_regime(now, curr_base)

            price = self._eval_base_price(now)

            # High-frequency incommensurate fractal noise
            noise = 0.0
            for p in self.primes:
                phase = (now % p["period"]) / p["period"] * 2.0 * math.pi + p["phase"]
                noise += p["amp"] * math.sin(phase)

            final_price = price + noise
            safe_floor, safe_ceiling = self._get_effective_bounds()
            clamped = round(max(safe_floor, min(safe_ceiling, final_price)), 4)

            # Slope calculation: dt = 2.0s
            dt = 2.0
            p_ahead = self._eval_base_price(now + dt)
            slope = ((p_ahead - price) / dt) * 1000.0

            regime = self.state.get("regime", "ZONE_CONSOLIDATION")

            return clamped, slope, regime, noise


def get_anti_sniper_wave(now: float = None):
    """
    Public entry point for ReferenceEngine and CandleBot.
    Returns: (clamped_target, slope, regime, noise)
    """
    global _engine_instance
    if _engine_instance is None:
        with _engine_lock:
            if _engine_instance is None:
                _engine_instance = MarketRegimeEngine()

    return _engine_instance.get_anti_sniper_wave(now)
