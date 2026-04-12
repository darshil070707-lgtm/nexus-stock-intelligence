"""
Ensemble ML Model for Stock Direction Prediction
3-model ensemble: GradientBoostingClassifier + RandomForestClassifier + ExtraTreesClassifier
Features: 20+ from OHLCV · RSI · MACD · Bollinger Bands · EMAs · Volume ratios · ATR · Stochastic
Target: 5-day forward return direction (+1 if >2%, -1 if <-2%, 0 otherwise)
Score: -10 to +10 based on buy/sell/neutral probabilities
"""
import pandas as pd
import numpy as np
import joblib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier, ExtraTreesClassifier
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available — ML model disabled")


MLSignalEngine = None  # alias defined at bottom of file

class MLModel:
    """Ensemble ML for directional prediction."""

    def __init__(self, model_dir: str = "/tmp/nexus_models"):
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.scaler = None
        self.models = {
            "gb": None,
            "rf": None,
            "et": None,
        }
        self.load_models()

    def load_models(self):
        """Load pre-trained models or create if missing."""
        if not SKLEARN_AVAILABLE:
            return

        for name in self.models:
            try:
                path = self.model_dir / f"{name}_model.pkl"
                if path.exists():
                    self.models[name] = joblib.load(path)
                    logger.info(f"Loaded {name} model from {path}")
            except Exception as e:
                logger.warning(f"Failed to load {name} model: {e}")

        try:
            scaler_path = self.model_dir / "scaler.pkl"
            if scaler_path.exists():
                self.scaler = joblib.load(scaler_path)
        except Exception as e:
            logger.warning(f"Failed to load scaler: {e}")

    def train(self, df: pd.DataFrame, label_col: str = "target") -> dict:
        """
        Train ensemble on OHLCV data.
        label_col expected to be -1, 0, or +1 for down/hold/up.
        """
        if not SKLEARN_AVAILABLE or len(df) < 100:
            return {"error": "Insufficient data or sklearn unavailable", "trained": False}

        try:
            # ── Feature engineering ────────────────────────────────────────
            features_df = self._engineer_features(df)

            # Drop rows with NaN
            valid = features_df.dropna()
            if len(valid) < 50:
                return {"error": "Not enough valid data after feature engineering", "trained": False}

            X = valid.drop(columns=[label_col] if label_col in valid.columns else [])
            y = valid[label_col] if label_col in valid.columns else valid.iloc[:, -1]

            # ── Standardize ────────────────────────────────────────────────
            self.scaler = StandardScaler()
            X_scaled = self.scaler.fit_transform(X)

            # ── Train ensemble ─────────────────────────────────────────────
            self.models["gb"] = GradientBoostingClassifier(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=5,
                random_state=42,
                verbose=0
            )
            self.models["gb"].fit(X_scaled, y)
            logger.info("Trained GradientBoostingClassifier")

            self.models["rf"] = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
            self.models["rf"].fit(X_scaled, y)
            logger.info("Trained RandomForestClassifier")

            self.models["et"] = ExtraTreesClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )
            self.models["et"].fit(X_scaled, y)
            logger.info("Trained ExtraTreesClassifier")

            # ── Save models ────────────────────────────────────────────────
            self._save_models()

            return {
                "trained": True,
                "samples": len(valid),
                "features": X.shape[1],
                "classes": list(np.unique(y)),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"ML training error: {e}")
            return {"error": str(e), "trained": False}

    def predict(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Predict direction for latest bar."""
        if not SKLEARN_AVAILABLE or not all(self.models.values()):
            return {
                "signal_score": 0,
                "action": "HOLD",
                "error": "Model not available",
            }

        try:
            # ── Engineer features for latest bar ───────────────────────────
            features_df = self._engineer_features(df)
            if features_df.empty:
                return {"signal_score": 0, "action": "HOLD", "error": "Feature engineering failed"}

            latest = features_df.iloc[-1:].dropna()
            if latest.empty:
                return {"signal_score": 0, "action": "HOLD", "error": "NaN values in features"}

            X = latest.values

            # Scale
            if self.scaler is None:
                return {"signal_score": 0, "action": "HOLD", "error": "Scaler not initialized"}

            X_scaled = self.scaler.transform(X)

            # ── Ensemble predictions ───────────────────────────────────────
            probs_gb = self.models["gb"].predict_proba(X_scaled)[0]  # shape: (3,) for -1, 0, +1
            probs_rf = self.models["rf"].predict_proba(X_scaled)[0]
            probs_et = self.models["et"].predict_proba(X_scaled)[0]

            # Average ensemble probabilities
            avg_probs = (probs_gb + probs_rf + probs_et) / 3

            # Map classes
            classes = sorted(self.models["gb"].classes_)  # [-1, 0, 1]
            class_idx_map = {c: i for i, c in enumerate(classes)}

            sell_prob = avg_probs[class_idx_map.get(-1, 0)]
            hold_prob = avg_probs[class_idx_map.get(0, 1)]
            buy_prob = avg_probs[class_idx_map.get(1, 2)]

            # ── Convert to score ───────────────────────────────────────────
            # Score = buy_prob - sell_prob, scaled to -10 to +10
            signal_score = (buy_prob - sell_prob) * 10

            # Confidence
            max_prob = max(avg_probs)
            confidence_pct = round(max_prob * 100, 1)
            confidence_level = (
                "VERY_HIGH" if max_prob > 0.70 else (
                "HIGH" if max_prob > 0.60 else (
                "MEDIUM" if max_prob > 0.45 else
                "LOW"
            )))

            # Action
            if buy_prob > 0.60:
                action = "BUY"
            elif sell_prob > 0.60:
                action = "SELL"
            else:
                action = "HOLD"

            reasons = []
            if buy_prob > 0.55:
                reasons.append(f"ML model bullish ({buy_prob*100:.0f}% buy probability)")
            if sell_prob > 0.55:
                reasons.append(f"ML model bearish ({sell_prob*100:.0f}% sell probability)")
            if confidence_level in ("VERY_HIGH", "HIGH"):
                reasons.append(f"High model confidence ({confidence_pct:.0f}%)")

            return {
                "signal_score": round(signal_score, 2),
                "action": action,
                "confidence": confidence_level,
                "confidence_pct": confidence_pct,
                "probabilities": {
                    "buy": round(buy_prob, 3),
                    "hold": round(hold_prob, 3),
                    "sell": round(sell_prob, 3),
                },
                "reasons": reasons,
            }

        except Exception as e:
            logger.error(f"ML prediction error: {e}")
            return {
                "signal_score": 0,
                "action": "HOLD",
                "error": str(e),
            }

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create 20+ ML features from OHLCV."""
        try:
            df = df.copy()
            df = df.sort_index()

            # ── Price-based features ───────────────────────────────────────
            df["returns"] = df["Close"].pct_change()
            df["log_returns"] = np.log(df["Close"] / df["Close"].shift(1))
            df["high_low_ratio"] = df["High"] / df["Low"]
            df["close_high_ratio"] = df["Close"] / df["High"]
            df["close_low_ratio"] = df["Close"] / df["Low"]

            # ── RSI ────────────────────────────────────────────────────────
            delta = df["Close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / (loss + 1e-9)
            df["rsi"] = 100 - (100 / (1 + rs))

            # ── MACD ───────────────────────────────────────────────────────
            ema12 = df["Close"].ewm(span=12, adjust=False).mean()
            ema26 = df["Close"].ewm(span=26, adjust=False).mean()
            df["macd"] = ema12 - ema26
            df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
            df["macd_hist"] = df["macd"] - df["macd_signal"]

            # ── Bollinger Bands ────────────────────────────────────────────
            sma20 = df["Close"].rolling(20).mean()
            std20 = df["Close"].rolling(20).std()
            df["bb_upper"] = sma20 + (std20 * 2)
            df["bb_lower"] = sma20 - (std20 * 2)
            df["bb_width"] = df["bb_upper"] - df["bb_lower"]
            df["bb_position"] = (df["Close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

            # ── EMAs ───────────────────────────────────────────────────────
            df["ema9"] = df["Close"].ewm(span=9, adjust=False).mean()
            df["ema21"] = df["Close"].ewm(span=21, adjust=False).mean()
            df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
            df["ema_ratio"] = df["ema9"] / df["ema21"]

            # ── Volume features ───────────────────────────────────────────
            df["volume_sma"] = df["Volume"].rolling(20).mean()
            df["volume_ratio"] = df["Volume"] / (df["volume_sma"] + 1e-9)
            df["price_volume"] = df["Close"] * df["Volume"]

            # ── Volatility ────────────────────────────────────────────────
            df["volatility"] = df["returns"].rolling(20).std()

            # ── ATR ────────────────────────────────────────────────────────
            tr = pd.concat([
                df["High"] - df["Low"],
                (df["High"] - df["Close"].shift()).abs(),
                (df["Low"] - df["Close"].shift()).abs()
            ], axis=1).max(axis=1)
            df["atr"] = tr.rolling(14).mean()

            # ── Stochastic ────────────────────────────────────────────────
            low_min = df["Low"].rolling(14).min()
            high_max = df["High"].rolling(14).max()
            df["stochastic"] = 100 * (df["Close"] - low_min) / (high_max - low_min + 1e-9)

            # ── Target (5-day forward return direction) ──────────────────
            df["forward_return"] = df["Close"].shift(-5) / df["Close"] - 1
            df["target"] = pd.cut(df["forward_return"], bins=[-np.inf, -0.02, 0.02, np.inf],
                                   labels=[-1, 0, 1])
            df["target"] = df["target"].astype(int)

            # Keep only numeric features
            feature_cols = [
                "returns", "log_returns", "high_low_ratio", "close_high_ratio", "close_low_ratio",
                "rsi", "macd", "macd_signal", "macd_hist",
                "bb_upper", "bb_lower", "bb_width", "bb_position",
                "ema9", "ema21", "ema50", "ema_ratio",
                "volume_sma", "volume_ratio", "price_volume",
                "volatility", "atr", "stochastic", "target"
            ]

            return df[feature_cols].copy()

        except Exception as e:
            logger.error(f"Feature engineering error: {e}")
            return pd.DataFrame()

    def _save_models(self):
        """Persist trained models."""
        try:
            for name, model in self.models.items():
                if model:
                    path = self.model_dir / f"{name}_model.pkl"
                    joblib.dump(model, path)
                    logger.info(f"Saved {name} model to {path}")

            if self.scaler:
                scaler_path = self.model_dir / "scaler.pkl"
                joblib.dump(self.scaler, scaler_path)
                logger.info(f"Saved scaler to {scaler_path}")
        except Exception as e:
            logger.error(f"Model save error: {e}")

MLSignalEngine = MLModel  # backward-compatible alias
