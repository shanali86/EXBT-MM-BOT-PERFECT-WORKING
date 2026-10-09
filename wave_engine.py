# ==============================================================================
#  EXBT BTC-Style Institutional Market Regime Engine
#  Replaces periodic harmonic sine-waves with realistic Markov state machine:
#  - CONSOLIDATION (Sideways accumulation / support building)
#  - IMPULSIVE_UP (Multi-candle bullish momentum run)
#  - IMPULSIVE_DOWN (Controlled bearish distribution)
#  - RETRACEMENT (Healthy 38%-50% Fibonacci pullback)
#  - ORGANIC_DRIFT (Brownian-style wandering drift)
#  Strictly bounded inside [0.2800, 0.3500] corridor.
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
    Simulates authentic crypto price action:
    1. Hours of consolidation/resting on key shelves.
    2. Multi-candle impulsive breakouts with momentum.
    3. Natural 38%-50% Fibonacci retracements.
    4. Non-periodic fractal noise with irrational frequencies.
    """

    def __init__(self):
        self.state_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data",
            "regime_state.json"
        )
        self.center_price = float(getattr(config, "WAVE_CENTER_PRICE", 0.3800))
        self.safe_floor = float(getattr(config, "PRICE_FLOOR", 0.3000))
        self.safe_ceiling = float(getattr(config, "PRICE_CEILING", 0.4200)) - 0.0075 # ~0.4125 safe ceiling

        # Incommensurate prime-period waves for continuous non-repeating fractal noise
        self.primes = [
            {"period": 317.0, "amp": 0.00045, "phase": 1.14},
            {"period": 139.0, "amp": 0.00035, "phase": 2.71},
            {"period": 53.0,  "amp": 0.00025, "phase": 0.88},
            {"period": 19.0,  "amp": 0.00018, "phase": 3.42},
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
                        last_p = float(data.get("target_price", 0.3720))
                        last_p = max(self.safe_floor, min(self.safe_ceiling, last_p))
                        logger.info(f"Transitioning cleanly from {last_p:.4f} into Bullish Target Climb Phase")
                        self.state = self._create_new_state("IMPULSIVE_UP", now, last_p, 0.4020, duration=1800.0)
                        self._save_state()
                        return self.state
        except Exception as e:
            logger.warning(f"Could not load regime state: {e}. Initializing fresh.")

        self.state = self._create_new_state("IMPULSIVE_UP", now, 0.3720, 0.4020, duration=1800.0)
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
            "shelf_amp": round(random.uniform(0.0015, 0.0032), 4),
            "prev_regime": getattr(self, "state", {}).get("regime", None) if hasattr(self, "state") else None
        }
        return state

    def _transition_next_regime(self, now: float, current_price: float):
        prev = self.state.get("regime", "CONSOLIDATION")
        r = random.random()

        # Enforce 0.3500 floor as soon as price crosses it
        if current_price >= 0.3500:
            self.safe_floor = max(self.safe_floor, 0.3500)
            logger.info(f"🛡️ HARD FLOOR LOCKED AT 0.3500 USDT (Current: {current_price:.4f})")

        # ─── 3-STAGE STRATEGIC CLIMB TO 0.4000 TARGET ───────────────────────
        if current_price < 0.3520:
            # PHASE 1: Climb to 0.3550 Breakout
            if prev != "IMPULSIVE_UP":
                regime = "IMPULSIVE_UP"
                duration = random.uniform(1200, 1800)  # 20 to 30 mins
                target = round(min(0.3550, current_price + random.uniform(0.0060, 0.0120)), 4)
            else:
                # Brief consolidation pause to let 15M candles form nice bases
                regime = "CONSOLIDATION"
                duration = random.uniform(450, 750)    # 7 to 12 mins
                target = current_price

        elif current_price < 0.3800:
            # PHASE 2: Build 0.3650-0.3700 Support Base, Then Push to 0.3850
            self.safe_floor = max(self.safe_floor, 0.3500)
            if prev == "IMPULSIVE_UP" and r < 0.50:
                # Shallow healthy retracement (never dropping below 0.3660)
                regime = "RETRACEMENT"
                duration = random.uniform(360, 600)    # 6 to 10 mins
                target = max(0.3660, current_price - 0.0025)
            elif prev in ("RETRACEMENT", "CONSOLIDATION"):
                regime = "IMPULSIVE_UP"
                duration = random.uniform(900, 1500)   # 15 to 25 mins
                target = round(min(0.3850, current_price + random.uniform(0.0060, 0.0120)), 4)
            else:
                regime = "CONSOLIDATION"
                duration = random.uniform(600, 1200)   # 10 to 20 mins
                target = current_price

        elif current_price < 0.4020:
            # PHASE 3: The Target Sprint to 0.4020+
            self.safe_floor = max(self.safe_floor, 0.3500)
            if prev != "IMPULSIVE_UP":
                regime = "IMPULSIVE_UP"
                duration = random.uniform(1200, 1800)  # 20 to 30 mins
                target = 0.4025  # Touch user's target!
            else:
                regime = "CONSOLIDATION"
                duration = random.uniform(600, 1200)   # 10 to 20 mins
                target = current_price

        else:
            # ─── MULTI-TIER ORGANIC CYCLE (0.3800 <-> 0.4180 CORRIDOR) ───
            # Permanently safeguards 0.3500 floor & 0.4200 ceiling.
            # Breaks rigid ping-pong cage into 3 dynamic shifting zones with random drift.
            self.safe_floor = max(self.safe_floor, 0.3500)

            # Choice between 3 rotating macro zones:
            # 1. ZONE_BREAKOUT: Tests upper highs (0.4080 - 0.4180)
            # 2. ZONE_CONSOLIDATION: Sideways resting (0.3980 - 0.4080)
            # 3. ZONE_PULLBACK: Healthy retest of support (0.3820 - 0.3960)

            if prev in ("ZONE_BREAKOUT", "IMPULSIVE_UP") or current_price > 0.4120:
                # After a push to highs, initiate natural healthy retracement or resting shelf
                if r < 0.55:
                    regime = "ZONE_CONSOLIDATION"
                    duration = random.uniform(900, 1800)  # 15 to 30 mins
                    target = round(random.uniform(0.4010, 0.4075), 4)
                else:
                    regime = "ZONE_PULLBACK"
                    duration = random.uniform(1200, 2400) # 20 to 40 mins
                    target = round(random.uniform(0.3840, 0.3950), 4)

            elif prev == "ZONE_PULLBACK" or current_price < 0.3920:
                # After a healthy dip/pullback, initiate a strong bullish expansion rally
                if r < 0.70:
                    regime = "ZONE_EXPANSION"
                    duration = random.uniform(1200, 2400) # 20 to 40 mins
                    target = round(random.uniform(0.4060, 0.4160), 4)
                else:
                    regime = "ZONE_CONSOLIDATION"
                    duration = random.uniform(900, 1500)  # 15 to 25 mins
                    target = round(random.uniform(0.3930, 0.4020), 4)

            else:
                # In middle zone (0.3920 - 0.4120) - randomly select next directional phase
                if r < 0.40:
                    regime = "ZONE_BREAKOUT"
                    duration = random.uniform(900, 1800)  # 15 to 30 mins
                    target = round(random.uniform(0.4090, 0.4175), 4)
                elif r < 0.75:
                    regime = "ZONE_PULLBACK"
                    duration = random.uniform(1200, 2100) # 20 to 35 mins
                    target = round(random.uniform(0.3850, 0.3960), 4)
                else:
                    regime = "ZONE_CONSOLIDATION"
                    duration = random.uniform(1200, 2400) # 20 to 40 mins
                    target = round(random.uniform(0.3980, 0.4060), 4)


        self.state = self._create_new_state(regime, now, current_price, target, duration)
        self._save_state()
        logger.info(
            f"🔄 Market Regime Transition: {prev} -> {regime} | "
            f"Start: {current_price:.4f} -> Target: {target:.4f} | "
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

        if regime in ("IMPULSIVE_UP", "IMPULSIVE_DOWN", "RETRACEMENT", "ZONE_EXPANSION", "ZONE_BREAKOUT", "ZONE_PULLBACK"):
            eased = self._quintic_ease(progress)
            return sp + (tp - sp) * eased
        elif regime in ("CONSOLIDATION", "ZONE_CONSOLIDATION"):
            shelf = self.state.get("shelf_price", tp)
            amp = self.state.get("shelf_amp", 0.0018)
            drift_wave = amp * math.sin(progress * math.pi * 3.0)
            return shelf + drift_wave
        else: # ORGANIC_DRIFT
            eased = self._quintic_ease(progress)
            shelf = sp + (tp - sp) * eased
            amp = self.state.get("shelf_amp", 0.0008)
            drift_wave = amp * math.sin(progress * math.pi * 2.0)
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
            clamped = round(max(self.safe_floor, min(self.safe_ceiling, final_price)), 4)

            # Slope calculation: dt = 2.0s
            dt = 2.0
            p_ahead = self._eval_base_price(now + dt)
            slope = ((p_ahead - price) / dt) * 1000.0

            regime = self.state.get("regime", "CONSOLIDATION")

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
