"""
Market Regime Detector
Uses Hidden Markov Model (HMM) proxy via sklearn GMM + volatility clustering
Regimes: BULL_TRENDING · BEAR_TRENDING · HIGH_VOL · LOW_VOL · SIDEWAYS
Adapts signal weights based on current regime — nobody else does this.
"""
import numpy as np
import pandas as pd
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
import logging

logger = logging.getLogger(__name__)


class RegimeDetector:

    def detect(self, df: pd.DataFrame) -> dict:
        """Detect current market regime from price history."""
        if df is None or len(df) < 60:
            return {"regime": "UNKNOWN", "regime_score": 1.0, "description": "Insufficient data"}

        try:
            close  = df["Close"].values
            volume = df["Volume"].values

            # Features for regime detection
            returns   = np.diff(np.log(close + 1e-9))
            volatility= pd.Series(returns).rolling(10).std().fillna(0).values[:-1] * np.sqrt(252)
            momentum  = pd.Series(close).pct_change(20).fillna(0).values
            vol_ratio = volume / (pd.Series(volume).rolling(20).mean().fillna(1).values)

            # Use last 100 candles
            n = min(100, len(returns))
            feats = np.column_stack([
                returns[-n:],
                volatility[-n:] if len(volatility) >= n else np.zeros(n),
                momentum[-n:] if len(momentum) >= n else np.zeros(n),
                vol_ratio[-n:] if len(vol_ratio) >= n else np.ones(n),
            ])

            scaler  = StandardScaler()
            X       = scaler.fit_transform(feats)

            # Fit GMM to detect 3 regimes
            gmm = GaussianMixture(n_components=3, covariance_type="full",
                                   random_state=42, max_iter=200)
            labels  = gmm.fit_predict(X)
            current = int(labels[-1])

            # Characterize each regime cluster
            regime_stats = {}
            for i in range(3):
                mask = labels == i
                if mask.sum() > 0:
                    regime_stats[i] = {
                        "mean_return":  float(np.mean(returns[-n:][mask])),
                        "mean_vol":     float(np.mean(volatility[-n:][mask] if len(volatility) >= n else [0])),
                        "count":        int(mask.sum()),
                    }

            # Classify current regime
            cur_stats    = regime_stats.get(current, {})
            cur_ret      = cur_stats.get("mean_return", 0)
            cur_vol      = cur_stats.get("mean_vol", 0.2)

            # Recent 20-day trend
            recent_trend = (close[-1] - close[-20]) / close[-20] if len(close) >= 20 else 0
            recent_vol   = float(pd.Series(returns[-20:]).std() * np.sqrt(252)) if len(returns) >= 20 else 0.2

            # Classify
            if   recent_trend > 0.05 and recent_vol < 0.30: regime = "BULL_TRENDING"
            elif recent_trend < -0.05 and recent_vol < 0.30: regime = "BEAR_TRENDING"
            elif recent_vol > 0.50:                          regime = "HIGH_VOLATILITY"
            elif abs(recent_trend) < 0.02 and recent_vol < 0.20: regime = "SIDEWAYS"
            elif recent_vol < 0.15:                          regime = "LOW_VOLATILITY"
            else:                                            regime = "TRANSITIONING"

            # Signal multipliers per regime (how much to trust each signal)
            multipliers = {
                "BULL_TRENDING":   {"technical": 1.3, "ml": 1.2, "sentiment": 1.1, "fundamental": 0.9},
                "BEAR_TRENDING":   {"technical": 1.2, "ml": 1.1, "sentiment": 0.8, "fundamental": 1.1},
                "HIGH_VOLATILITY": {"technical": 0.7, "ml": 0.8, "sentiment": 0.6, "fundamental": 1.2},
                "SIDEWAYS":        {"technical": 0.8, "ml": 0.9, "sentiment": 0.7, "fundamental": 1.3},
                "LOW_VOLATILITY":  {"technical": 1.1, "ml": 1.0, "sentiment": 1.0, "fundamental": 1.0},
                "TRANSITIONING":   {"technical": 0.9, "ml": 0.9, "sentiment": 0.8, "fundamental": 1.1},
            }

            mults = multipliers.get(regime, {k: 1.0 for k in ["technical","ml","sentiment","fundamental"]})

            descriptions = {
                "BULL_TRENDING":   "🟢 Strong uptrend — technicals and momentum signals carry extra weight",
                "BEAR_TRENDING":   "🔴 Downtrend — fundamentals matter more; technical sell signals stronger",
                "HIGH_VOLATILITY": "⚠️ High volatility — reduce position sizes; signals less reliable",
                "SIDEWAYS":        "🟡 Range-bound — fundamentals dominate; avoid momentum plays",
                "LOW_VOLATILITY":  "🔵 Calm market — normal signal weighting",
                "TRANSITIONING":   "🔄 Regime changing — caution, mixed signals expected",
            }

            return {
                "regime":          regime,
                "description":     descriptions.get(regime, ""),
                "trend_20d":       round(recent_trend * 100, 2),
                "volatility_ann":  round(recent_vol * 100, 1),
                "signal_multipliers": mults,
                "gmm_cluster":     current,
                "cluster_stats":   regime_stats,
            }

        except Exception as e:
            logger.error(f"Regime detection error: {e}")
            return {"regime": "UNKNOWN", "signal_multipliers": {},
                    "description": f"Regime detection failed: {e}"}
