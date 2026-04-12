"""
Chart Pattern Recognition Engine
Detects: Head & Shoulders · Double Top/Bottom · Cup & Handle ·
         Bull/Bear Flag · Ascending/Descending Triangle · Wedge ·
         Breakout · Support/Resistance bounce
All computed algorithmically on OHLCV data — no external API needed.
"""
import pandas as pd
import numpy as np
from scipy.signal import argrelextrema
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class PatternRecognizer:

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        if df is None or len(df) < 60:
            return {"patterns": [], "signal_score": 0, "action": "HOLD"}

        df = df.copy().reset_index(drop=True)
        close  = df["Close"].values
        high   = df["High"].values
        low    = df["Low"].values
        volume = df["Volume"].values

        patterns = []
        score    = 0.0

        # ── Find local extrema ─────────────────────────────────────────────
        order = max(3, len(df) // 20)
        local_max_idx = argrelextrema(close, np.greater, order=order)[0]
        local_min_idx = argrelextrema(close, np.less,    order=order)[0]

        current = close[-1]

        # ── 1. Double Top ─────────────────────────────────────────────────
        dt = self._double_top(close, high, local_max_idx)
        if dt["detected"]:
            patterns.append(dt)
            score -= 3.0

        # ── 2. Double Bottom ──────────────────────────────────────────────
        db = self._double_bottom(close, low, local_min_idx)
        if db["detected"]:
            patterns.append(db)
            score += 3.0

        # ── 3. Head & Shoulders ───────────────────────────────────────────
        hs = self._head_shoulders(close, high, local_max_idx)
        if hs["detected"]:
            patterns.append(hs)
            score -= 4.0

        # ── 4. Inverse H&S ────────────────────────────────────────────────
        ihs = self._inverse_head_shoulders(close, low, local_min_idx)
        if ihs["detected"]:
            patterns.append(ihs)
            score += 4.0

        # ── 5. Bull Flag ──────────────────────────────────────────────────
        bf = self._bull_flag(df)
        if bf["detected"]:
            patterns.append(bf)
            score += 2.5

        # ── 6. Bear Flag ──────────────────────────────────────────────────
        bef = self._bear_flag(df)
        if bef["detected"]:
            patterns.append(bef)
            score -= 2.5

        # ── 7. Ascending Triangle ─────────────────────────────────────────
        at = self._ascending_triangle(close, high, low, local_min_idx, local_max_idx)
        if at["detected"]:
            patterns.append(at)
            score += 2.0

        # ── 8. Descending Triangle ────────────────────────────────────────
        dt2 = self._descending_triangle(close, high, low, local_min_idx, local_max_idx)
        if dt2["detected"]:
            patterns.append(dt2)
            score -= 2.0

        # ── 9. Cup & Handle ───────────────────────────────────────────────
        cup = self._cup_handle(close, volume)
        if cup["detected"]:
            patterns.append(cup)
            score += 3.5

        # ── 10. Breakout ──────────────────────────────────────────────────
        bo = self._breakout(close, volume)
        if bo["detected"]:
            patterns.append(bo)
            score += bo.get("strength", 1.5)

        # ── 11. Support bounce ────────────────────────────────────────────
        sb = self._support_bounce(close, low)
        if sb["detected"]:
            patterns.append(sb)
            score += 1.5

        # ── 12. Resistance rejection ──────────────────────────────────────
        rr = self._resistance_rejection(close, high)
        if rr["detected"]:
            patterns.append(rr)
            score -= 1.5

        score  = max(-10, min(10, score))
        action = "BUY" if score >= 2 else ("SELL" if score <= -2 else "HOLD")

        return {
            "patterns":     patterns,
            "pattern_count": len(patterns),
            "signal_score": round(score, 2),
            "action":       action,
        }

    # ── Pattern implementations ───────────────────────────────────────────────

    def _double_top(self, close, high, peaks):
        try:
            if len(peaks) < 2: return {"detected": False}
            p1, p2 = peaks[-2], peaks[-1]
            if abs(p2 - p1) < 5: return {"detected": False}  # too close
            h1, h2 = high[p1], high[p2]
            if abs(h1 - h2) / h1 < 0.02 and h1 > np.mean(close) * 1.05:
                trough = close[p1:p2].min()
                if close[-1] < trough * 1.01:
                    return {"detected": True, "name": "Double Top 🔴",
                            "price1": round(h1, 2), "price2": round(h2, 2),
                            "description": "Double top confirmed — bearish reversal pattern",
                            "bias": "SELL"}
        except Exception: pass
        return {"detected": False}

    def _double_bottom(self, close, low, troughs):
        try:
            if len(troughs) < 2: return {"detected": False}
            t1, t2 = troughs[-2], troughs[-1]
            if abs(t2 - t1) < 5: return {"detected": False}
            l1, l2 = low[t1], low[t2]
            if abs(l1 - l2) / l1 < 0.02 and l1 < np.mean(close) * 0.95:
                peak = close[t1:t2].max()
                if close[-1] > peak * 0.99:
                    return {"detected": True, "name": "Double Bottom 🟢",
                            "price1": round(l1, 2), "price2": round(l2, 2),
                            "description": "Double bottom confirmed — bullish reversal pattern",
                            "bias": "BUY"}
        except Exception: pass
        return {"detected": False}

    def _head_shoulders(self, close, high, peaks):
        try:
            if len(peaks) < 3: return {"detected": False}
            l, h, r = peaks[-3], peaks[-2], peaks[-1]
            lh, hh, rh = high[l], high[h], high[r]
            # Head higher than both shoulders
            if hh > lh * 1.02 and hh > rh * 1.02 and abs(lh - rh) / lh < 0.05:
                neckline = (close[l:h].min() + close[h:r].min()) / 2
                if close[-1] < neckline * 1.01:
                    target = neckline - (hh - neckline)
                    return {"detected": True, "name": "Head & Shoulders 🔴",
                            "neckline": round(neckline, 2), "target": round(target, 2),
                            "description": f"H&S — bearish. Neckline break. Target: {target:.2f}",
                            "bias": "SELL"}
        except Exception: pass
        return {"detected": False}

    def _inverse_head_shoulders(self, close, low, troughs):
        try:
            if len(troughs) < 3: return {"detected": False}
            l, h, r = troughs[-3], troughs[-2], troughs[-1]
            ll, hl, rl = low[l], low[h], low[r]
            if hl < ll * 0.98 and hl < rl * 0.98 and abs(ll - rl) / ll < 0.05:
                neckline = (close[l:h].max() + close[h:r].max()) / 2
                if close[-1] > neckline * 0.99:
                    target = neckline + (neckline - hl)
                    return {"detected": True, "name": "Inverse H&S 🟢",
                            "neckline": round(neckline, 2), "target": round(target, 2),
                            "description": f"Inverse H&S — bullish. Neckline: {neckline:.2f}. Target: {target:.2f}",
                            "bias": "BUY"}
        except Exception: pass
        return {"detected": False}

    def _bull_flag(self, df):
        try:
            close, vol = df["Close"].values, df["Volume"].values
            if len(close) < 30: return {"detected": False}
            # Pole: sharp rise in last 10 bars
            pole_start, pole_end = -20, -10
            pole_rise = (close[pole_end] - close[pole_start]) / close[pole_start]
            # Consolidation: slight downtrend last 10 bars
            consol = np.polyfit(range(10), close[-10:], 1)[0]
            # Volume: declining during consolidation
            vol_trend = np.polyfit(range(10), vol[-10:], 1)[0]
            if pole_rise > 0.05 and consol < 0 and vol_trend < 0:
                return {"detected": True, "name": "Bull Flag 🟢",
                        "pole_rise_pct": round(pole_rise * 100, 1),
                        "description": f"Bull flag — {pole_rise*100:.1f}% pole, consolidating. Breakout imminent.",
                        "bias": "BUY"}
        except Exception: pass
        return {"detected": False}

    def _bear_flag(self, df):
        try:
            close, vol = df["Close"].values, df["Volume"].values
            if len(close) < 30: return {"detected": False}
            pole_start, pole_end = -20, -10
            pole_drop = (close[pole_start] - close[pole_end]) / close[pole_start]
            consol = np.polyfit(range(10), close[-10:], 1)[0]
            vol_trend = np.polyfit(range(10), vol[-10:], 1)[0]
            if pole_drop > 0.05 and consol > 0 and vol_trend < 0:
                return {"detected": True, "name": "Bear Flag 🔴",
                        "pole_drop_pct": round(pole_drop * 100, 1),
                        "description": f"Bear flag — {pole_drop*100:.1f}% drop, bouncing weakly. Breakdown imminent.",
                        "bias": "SELL"}
        except Exception: pass
        return {"detected": False}

    def _ascending_triangle(self, close, high, low, mins, maxs):
        try:
            if len(maxs) < 2 or len(mins) < 2: return {"detected": False}
            recent_highs = high[maxs[-3:]] if len(maxs) >= 3 else high[maxs]
            recent_lows  = [low[m] for m in mins[-3:]] if len(mins) >= 3 else []
            flat_top     = np.std(recent_highs) / np.mean(recent_highs) < 0.015
            rising_lows  = len(recent_lows) >= 2 and recent_lows[-1] > recent_lows[-2]
            if flat_top and rising_lows:
                resistance = np.mean(recent_highs)
                return {"detected": True, "name": "Ascending Triangle 🟢",
                        "resistance": round(resistance, 2),
                        "description": f"Ascending triangle — flat resistance at {resistance:.2f}, rising lows. Bullish.",
                        "bias": "BUY"}
        except Exception: pass
        return {"detected": False}

    def _descending_triangle(self, close, high, low, mins, maxs):
        try:
            if len(maxs) < 2 or len(mins) < 2: return {"detected": False}
            recent_lows  = low[mins[-3:]] if len(mins) >= 3 else low[mins]
            recent_highs = [high[m] for m in maxs[-3:]] if len(maxs) >= 3 else []
            flat_bottom  = np.std(recent_lows) / np.mean(recent_lows) < 0.015
            lower_highs  = len(recent_highs) >= 2 and recent_highs[-1] < recent_highs[-2]
            if flat_bottom and lower_highs:
                support = np.mean(recent_lows)
                return {"detected": True, "name": "Descending Triangle 🔴",
                        "support": round(support, 2),
                        "description": f"Descending triangle — flat support at {support:.2f}, lower highs. Bearish.",
                        "bias": "SELL"}
        except Exception: pass
        return {"detected": False}

    def _cup_handle(self, close, volume):
        try:
            if len(close) < 60: return {"detected": False}
            segment = close[-60:]
            left    = segment[0]
            bottom  = np.min(segment[10:50])
            right   = segment[-10]
            handle  = np.min(segment[-10:])
            if (bottom < left * 0.88 and right > left * 0.95 and
                    handle > bottom * 1.02 and handle < left * 0.97):
                target = left + (left - bottom)
                vol_trend = np.polyfit(range(10), volume[-10:], 1)[0]
                if vol_trend < 0:   # volume declining in handle = healthy
                    return {"detected": True, "name": "Cup & Handle 🟢",
                            "target": round(target, 2),
                            "description": f"Cup & Handle — classic bullish continuation. Target: {target:.2f}",
                            "bias": "BUY"}
        except Exception: pass
        return {"detected": False}

    def _breakout(self, close, volume):
        try:
            if len(close) < 30: return {"detected": False}
            resistance  = np.max(close[-30:-3])
            current     = close[-1]
            avg_vol     = np.mean(volume[-20:-3])
            curr_vol    = volume[-1]
            above       = (current - resistance) / resistance
            vol_confirm = curr_vol > avg_vol * 1.3
            if above > 0.01 and vol_confirm:
                strength = min(3.0, above * 50 + (1.5 if vol_confirm else 0))
                return {"detected": True, "name": "Breakout 🚀",
                        "resistance": round(resistance, 2), "breakout_pct": round(above * 100, 2),
                        "volume_confirmation": vol_confirm,
                        "description": f"Breakout above {resistance:.2f} (+{above*100:.1f}%) with volume. Strong buy.",
                        "bias": "BUY", "strength": strength}
        except Exception: pass
        return {"detected": False}

    def _support_bounce(self, close, low):
        try:
            support = np.percentile(close[-30:], 10)
            current = close[-1]
            prev    = close[-3]
            if prev < support * 1.01 and current > prev * 1.005:
                return {"detected": True, "name": "Support Bounce 🟢",
                        "support": round(support, 2),
                        "description": f"Price bouncing off support {support:.2f}",
                        "bias": "BUY"}
        except Exception: pass
        return {"detected": False}

    def _resistance_rejection(self, close, high):
        try:
            resistance = np.percentile(close[-30:], 90)
            current    = close[-1]
            prev       = close[-3]
            if prev > resistance * 0.99 and current < prev * 0.995:
                return {"detected": True, "name": "Resistance Rejection 🔴",
                        "resistance": round(resistance, 2),
                        "description": f"Price rejected at resistance {resistance:.2f}",
                        "bias": "SELL"}
        except Exception: pass
        return {"detected": False}
