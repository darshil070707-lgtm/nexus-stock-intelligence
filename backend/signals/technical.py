"""
Advanced Technical Analysis Engine
Indicators: RSI · MACD · Bollinger Bands · EMA (9/21/50/200) · Stochastic · ADX · OBV ·
            Ichimoku Cloud · Pivot Points · VWAP · Fibonacci · Williams %R · CCI · MFI ·
            Volume Profile · ATR
Composite score: -10 to +10
"""
import pandas as pd
import numpy as np
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class TechnicalAnalyzer:

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Run full technical suite."""
        if df is None or len(df) < 50:
            return {
                "signal_score": 0, "action": "HOLD",
                "error": "Insufficient data for technical analysis"
            }

        df = df.copy()
        score = 0.0
        reasons = []
        indicators = {}

        # ── 1. RSI (14-period) ────────────────────────────────────────────
        rsi_val = self._rsi(df["Close"], 14)
        indicators["rsi"] = round(rsi_val, 2)
        if   rsi_val > 70: score -= 1.5; reasons.append(f"RSI {rsi_val:.0f} — overbought")
        elif rsi_val < 30: score += 1.5; reasons.append(f"RSI {rsi_val:.0f} — oversold (bullish)")
        elif rsi_val > 60: score += 0.5
        elif rsi_val < 40: score -= 0.5

        # ── 2. MACD (12/26/9) ────────────────────────────────────────────
        macd_line, signal_line, histogram = self._macd(df["Close"])
        indicators["macd"] = round(macd_line, 4)
        indicators["macd_signal"] = round(signal_line, 4)
        indicators["macd_histogram"] = round(histogram, 4)
        if histogram > 0 and macd_line > signal_line:
            score += 1.5; reasons.append("MACD bullish crossover")
        elif histogram < 0 and macd_line < signal_line:
            score -= 1.5; reasons.append("MACD bearish crossover")
        if histogram > 0:
            score += 0.5

        # ── 3. Bollinger Bands (20, 2) ────────────────────────────────────
        bb_upper, bb_mid, bb_lower, bb_width = self._bollinger_bands(df["Close"], 20, 2)
        current = df["Close"].iloc[-1]
        indicators["bb_upper"] = round(bb_upper, 2)
        indicators["bb_lower"] = round(bb_lower, 2)
        indicators["bb_width"] = round(bb_width, 2)
        if current < bb_lower:
            score += 1.8; reasons.append(f"Price {current:.2f} below BB lower {bb_lower:.2f} — oversold")
        elif current > bb_upper:
            score -= 1.8; reasons.append(f"Price {current:.2f} above BB upper {bb_upper:.2f} — overbought")
        if bb_width < np.percentile(df["Close"].rolling(50).std(), 25):
            score += 0.5; reasons.append("Bollinger Band squeeze — volatility breakout likely")

        # ── 4. EMAs (9, 21, 50, 200) ─────────────────────────────────────
        ema9 = self._ema(df["Close"], 9)
        ema21 = self._ema(df["Close"], 21)
        ema50 = self._ema(df["Close"], 50)
        ema200 = self._ema(df["Close"], 200)
        indicators["ema9"] = round(ema9, 2)
        indicators["ema21"] = round(ema21, 2)
        indicators["ema50"] = round(ema50, 2)
        indicators["ema200"] = round(ema200, 2)

        # EMA alignment (all bullish or all bearish)
        if ema9 > ema21 > ema50 > ema200:
            score += 2.0; reasons.append("EMA stack bullish (9>21>50>200)")
        elif ema9 < ema21 < ema50 < ema200:
            score -= 2.0; reasons.append("EMA stack bearish (9<21<50<200)")
        else:
            # Check price position vs key EMAs
            if current > ema200: score += 0.8
            if current < ema200: score -= 0.8

        # ── 5. Stochastic (14, 3, 3) ─────────────────────────────────────
        k_val, d_val = self._stochastic(df, 14, 3, 3)
        indicators["stochastic_k"] = round(k_val, 2)
        indicators["stochastic_d"] = round(d_val, 2)
        if   k_val > 80: score -= 1.0; reasons.append(f"Stochastic {k_val:.0f} — overbought")
        elif k_val < 20: score += 1.0; reasons.append(f"Stochastic {k_val:.0f} — oversold")
        if k_val > d_val and k_val < 50: score += 0.5  # bullish divergence potential

        # ── 6. ADX (Average Directional Index) ────────────────────────────
        adx_val = self._adx(df, 14)
        indicators["adx"] = round(adx_val, 2)
        if adx_val > 25:
            score += 1.2; reasons.append(f"ADX {adx_val:.1f} — strong trend")
        elif adx_val < 20:
            score -= 0.5; reasons.append(f"ADX {adx_val:.1f} — weak/ranging")

        # ── 7. OBV (On-Balance Volume) ────────────────────────────────────
        obv_val = self._obv(df)
        obv_trend = self._obv_trend(df)
        indicators["obv"] = round(obv_val, 0)
        indicators["obv_trend"] = obv_trend
        if obv_trend == "bullish":
            score += 1.0; reasons.append("OBV bullish accumulation")
        elif obv_trend == "bearish":
            score -= 1.0; reasons.append("OBV bearish distribution")

        # ── 8. Ichimoku Cloud ─────────────────────────────────────────────
        tenkan, kijun, senkou_a, senkou_b, chikou = self._ichimoku(df)
        indicators["ichimoku_tenkan"] = round(tenkan, 2)
        indicators["ichimoku_kijun"] = round(kijun, 2)
        ichimoku_signal = self._ichimoku_signal(current, tenkan, kijun, senkou_a, senkou_b)
        if ichimoku_signal == "STRONG_BULL":
            score += 1.8; reasons.append("Ichimoku strong bullish (price above cloud, tenkan>kijun)")
        elif ichimoku_signal == "BULL":
            score += 1.0; reasons.append("Ichimoku bullish (price in/above cloud)")
        elif ichimoku_signal == "STRONG_BEAR":
            score -= 1.8; reasons.append("Ichimoku strong bearish (price below cloud)")
        elif ichimoku_signal == "BEAR":
            score -= 1.0; reasons.append("Ichimoku bearish (price in cloud)")

        # ── 9. Pivot Points (Daily) ───────────────────────────────────────
        try:
            high, low, close = df["High"].iloc[-1], df["Low"].iloc[-1], df["Close"].iloc[-1]
            pivot = (high + low + close) / 3
            r1 = 2 * pivot - low
            r2 = pivot + (high - low)
            s1 = 2 * pivot - high
            s2 = pivot - (high - low)
            indicators["pivot"] = round(pivot, 2)
            indicators["resistance_1"] = round(r1, 2)
            indicators["resistance_2"] = round(r2, 2)
            indicators["support_1"] = round(s1, 2)
            indicators["support_2"] = round(s2, 2)

            if current > r2: score += 1.0; reasons.append(f"Price {current:.2f} > R2 {r2:.2f}")
            elif current < s2: score -= 1.0; reasons.append(f"Price {current:.2f} < S2 {s2:.2f}")
        except Exception:
            pass

        # ── 10. VWAP (Volume Weighted Avg Price) ──────────────────────────
        vwap = self._vwap(df)
        indicators["vwap"] = round(vwap, 2)
        if current > vwap:
            score += 0.7; reasons.append(f"Price {current:.2f} > VWAP {vwap:.2f}")
        else:
            score -= 0.7

        # ── 11. Fibonacci Retracements ────────────────────────────────────
        fib_levels = self._fibonacci_levels(df)
        indicators["fib_levels"] = {k: round(v, 2) for k, v in fib_levels.items()}
        fib_signal = self._fibonacci_signal(current, fib_levels)
        if fib_signal == "support_bounce":
            score += 0.8; reasons.append("Price at Fibonacci support — bounce likely")
        elif fib_signal == "resistance_rejection":
            score -= 0.8; reasons.append("Price at Fibonacci resistance — rejection likely")

        # ── 12. Williams %R ───────────────────────────────────────────────
        williams_r = self._williams_r(df, 14)
        indicators["williams_r"] = round(williams_r, 2)
        if   williams_r < -80: score += 0.8; reasons.append(f"Williams %R {williams_r:.0f} — oversold")
        elif williams_r > -20: score -= 0.8; reasons.append(f"Williams %R {williams_r:.0f} — overbought")

        # ── 13. CCI (Commodity Channel Index) ─────────────────────────────
        cci = self._cci(df, 20)
        indicators["cci"] = round(cci, 2)
        if   cci > 100: score -= 0.7; reasons.append(f"CCI {cci:.0f} — overbought")
        elif cci < -100: score += 0.7; reasons.append(f"CCI {cci:.0f} — oversold")

        # ── 14. Money Flow Index (MFI) ────────────────────────────────────
        mfi = self._mfi(df, 14)
        indicators["mfi"] = round(mfi, 2)
        if   mfi > 80: score -= 0.7; reasons.append(f"MFI {mfi:.0f} — overbought")
        elif mfi < 20: score += 0.7; reasons.append(f"MFI {mfi:.0f} — oversold")

        # ── 15. ATR (Average True Range) ──────────────────────────────────
        atr = self._atr(df, 14)
        indicators["atr"] = round(atr, 2)
        atr_pct = (atr / current) * 100
        indicators["atr_pct"] = round(atr_pct, 2)

        # ── 16. Volume Analysis ───────────────────────────────────────────
        vol_signal = self._volume_signal(df)
        if vol_signal == "increasing_bullish":
            score += 1.0; reasons.append("Volume increasing with price rise — strong")
        elif vol_signal == "decreasing_bearish":
            score -= 1.0; reasons.append("Volume increasing with price decline — weak")

        # ── Final Score ────────────────────────────────────────────────────
        score = max(-10, min(10, score))
        action = "BUY" if score >= 3 else ("SELL" if score <= -3 else "HOLD")

        return {
            "signal_score": round(score, 2),
            "action": action,
            "indicators": indicators,
            "reasons": reasons,
        }

    # ── Indicator implementations ──────────────────────────────────────────

    def _ema(self, close, period):
        """Exponential Moving Average"""
        return float(close.ewm(span=period, adjust=False).mean().iloc[-1])

    def _rsi(self, close, period=14):
        """Relative Strength Index (14)"""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50

    def _macd(self, close, fast=12, slow=26, signal=9):
        """MACD (12, 26, 9)"""
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return (
            float(macd_line.iloc[-1]),
            float(signal_line.iloc[-1]),
            float(histogram.iloc[-1])
        )

    def _bollinger_bands(self, close, period=20, num_std=2):
        """Bollinger Bands (20, 2)"""
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        width = upper - lower
        return (
            float(upper.iloc[-1]),
            float(sma.iloc[-1]),
            float(lower.iloc[-1]),
            float(width.iloc[-1])
        )

    def _stochastic(self, df, period=14, smooth_k=3, smooth_d=3):
        """Stochastic Oscillator (14, 3, 3)"""
        low_min = df["Low"].rolling(period).min()
        high_max = df["High"].rolling(period).max()
        k_raw = 100 * (df["Close"] - low_min) / (high_max - low_min + 1e-9)
        k = k_raw.rolling(smooth_k).mean()
        d = k.rolling(smooth_d).mean()
        return float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else 50, float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else 50

    def _adx(self, df, period=14):
        """Average Directional Index (14)"""
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        plus_dm = high.diff().where(high.diff() > low.diff().abs(), 0)
        minus_dm = low.diff().abs().where(low.diff().abs() > high.diff(), 0)

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        plus_di = 100 * plus_dm.rolling(period).mean() / (atr + 1e-9)
        minus_di = 100 * minus_dm.rolling(period).mean() / (atr + 1e-9)

        di_diff = (plus_di - minus_di).abs()
        di_sum = plus_di + minus_di + 1e-9
        dx = 100 * di_diff / di_sum
        adx_val = dx.rolling(period).mean()

        return float(adx_val.iloc[-1]) if not pd.isna(adx_val.iloc[-1]) else 20

    def _obv(self, df):
        """On-Balance Volume"""
        obv = pd.Series(0.0, index=df.index)
        obv.iloc[0] = 0
        for i in range(1, len(df)):
            if df["Close"].iloc[i] > df["Close"].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + df["Volume"].iloc[i]
            elif df["Close"].iloc[i] < df["Close"].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - df["Volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        return float(obv.iloc[-1])

    def _obv_trend(self, df):
        """OBV trend (bullish/bearish)"""
        obv = pd.Series(0.0, index=df.index)
        obv.iloc[0] = 0
        for i in range(1, len(df)):
            if df["Close"].iloc[i] > df["Close"].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + df["Volume"].iloc[i]
            elif df["Close"].iloc[i] < df["Close"].iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - df["Volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]

        if len(obv) > 20:
            recent = obv.iloc[-20:].values
            if recent[-1] > np.mean(recent[:-5]):
                return "bullish"
            else:
                return "bearish"
        return "neutral"

    def _ichimoku(self, df):
        """Ichimoku Cloud components"""
        high9 = df["High"].rolling(9).max()
        low9 = df["Low"].rolling(9).min()
        tenkan = (high9 + low9) / 2

        high26 = df["High"].rolling(26).max()
        low26 = df["Low"].rolling(26).min()
        kijun = (high26 + low26) / 2

        senkou_a = ((tenkan + kijun) / 2).shift(26)

        high52 = df["High"].rolling(52).max()
        low52 = df["Low"].rolling(52).min()
        senkou_b = ((high52 + low52) / 2).shift(26)

        chikou = df["Close"].shift(-26)

        return (
            float(tenkan.iloc[-1]) if not pd.isna(tenkan.iloc[-1]) else 0,
            float(kijun.iloc[-1]) if not pd.isna(kijun.iloc[-1]) else 0,
            float(senkou_a.iloc[-1]) if not pd.isna(senkou_a.iloc[-1]) else 0,
            float(senkou_b.iloc[-1]) if not pd.isna(senkou_b.iloc[-1]) else 0,
            float(chikou.iloc[-1]) if not pd.isna(chikou.iloc[-1]) else 0
        )

    def _ichimoku_signal(self, price, tenkan, kijun, senkou_a, senkou_b):
        """Ichimoku signal interpretation"""
        cloud_mid = (senkou_a + senkou_b) / 2 if senkou_a and senkou_b else price
        above_cloud = price > max(senkou_a, senkou_b) if senkou_a and senkou_b else False
        below_cloud = price < min(senkou_a, senkou_b) if senkou_a and senkou_b else False
        tenkan_above_kijun = tenkan > kijun if tenkan and kijun else False

        if above_cloud and tenkan_above_kijun:
            return "STRONG_BULL"
        elif above_cloud or tenkan_above_kijun:
            return "BULL"
        elif below_cloud and not tenkan_above_kijun:
            return "STRONG_BEAR"
        elif below_cloud:
            return "BEAR"
        return "NEUTRAL"

    def _vwap(self, df):
        """Volume Weighted Average Price"""
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        vwap = (tp * df["Volume"]).rolling(len(df)).sum() / df["Volume"].rolling(len(df)).sum()
        return float(vwap.iloc[-1]) if not pd.isna(vwap.iloc[-1]) else float(df["Close"].iloc[-1])

    def _fibonacci_levels(self, df):
        """Fibonacci retracement levels"""
        high = df["High"].max()
        low = df["Low"].min()
        diff = high - low

        return {
            "0%": high,
            "23.6%": high - (diff * 0.236),
            "38.2%": high - (diff * 0.382),
            "50%": high - (diff * 0.5),
            "61.8%": high - (diff * 0.618),
            "100%": low,
        }

    def _fibonacci_signal(self, price, fib_levels):
        """Check if price is near Fibonacci levels"""
        tolerance = (fib_levels["0%"] - fib_levels["100%"]) * 0.02

        if abs(price - fib_levels["38.2%"]) < tolerance or abs(price - fib_levels["61.8%"]) < tolerance:
            if price > fib_levels["50%"]:
                return "support_bounce"
            else:
                return "resistance_rejection"
        return "neutral"

    def _williams_r(self, df, period=14):
        """Williams %R oscillator"""
        high_max = df["High"].rolling(period).max()
        low_min = df["Low"].rolling(period).min()
        williams_r = -100 * (high_max - df["Close"]) / (high_max - low_min + 1e-9)
        return float(williams_r.iloc[-1]) if not pd.isna(williams_r.iloc[-1]) else -50

    def _cci(self, df, period=20):
        """Commodity Channel Index"""
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        sma = tp.rolling(period).mean()
        mad = tp.rolling(period).apply(lambda x: (x - x.mean()).abs().mean())
        cci = (tp - sma) / (0.015 * mad + 1e-9)
        return float(cci.iloc[-1]) if not pd.isna(cci.iloc[-1]) else 0

    def _mfi(self, df, period=14):
        """Money Flow Index"""
        tp = (df["High"] + df["Low"] + df["Close"]) / 3
        mf = tp * df["Volume"]

        positive_mf = pd.Series(0.0, index=df.index)
        negative_mf = pd.Series(0.0, index=df.index)

        for i in range(1, len(df)):
            if tp.iloc[i] > tp.iloc[i-1]:
                positive_mf.iloc[i] = mf.iloc[i]
            elif tp.iloc[i] < tp.iloc[i-1]:
                negative_mf.iloc[i] = mf.iloc[i]

        pmf = positive_mf.rolling(period).sum()
        nmf = negative_mf.rolling(period).sum()
        mfi = 100 - (100 / (1 + (pmf / (nmf + 1e-9))))

        return float(mfi.iloc[-1]) if not pd.isna(mfi.iloc[-1]) else 50

    def _atr(self, df, period=14):
        """Average True Range"""
        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 0

    def _volume_signal(self, df):
        """Volume trend analysis"""
        if len(df) < 10:
            return "neutral"

        recent_closes = df["Close"].iloc[-10:].values
        recent_vols = df["Volume"].iloc[-10:].values

        price_trend = recent_closes[-1] > np.mean(recent_closes[:-3])
        vol_trend = recent_vols[-1] > np.mean(recent_vols[:-3])

        if price_trend and vol_trend:
            return "increasing_bullish"
        elif not price_trend and vol_trend:
            return "decreasing_bearish"
        return "neutral"
