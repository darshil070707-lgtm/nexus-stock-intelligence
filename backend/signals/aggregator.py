"""
NEXUS Master Aggregator — 10-Layer Signal Fusion
Combines: Technical · ML · Fundamental · Sentiment · Options Flow · Insider ·
          Macro · Patterns · Social · Regime Adjustment

Weighted ensemble with regime-adaptive multipliers.
"""
import pandas as pd
import numpy as np
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from config import SIGNAL_WEIGHTS, DEFAULT_PORTFOLIO
    from signals.technical import TechnicalAnalyzer
    from signals.fundamental import FundamentalAnalyzer
    from signals.sentiment import SentimentAnalyzer
    from signals.ml_model import MLModel
    from signals.options_flow import OptionsFlowAnalyzer
    from signals.insider import InsiderAnalyzer
    from signals.patterns import PatternRecognizer
    from signals.social import SocialSentimentAnalyzer
    from signals.macro import MacroAnalyzer
    from signals.regime import RegimeDetector
    from engine.backtester import Backtester
    from engine.risk_manager import RiskManager
except ImportError:
    # Try with absolute imports
    import sys
    sys.path.insert(0, "/app/backend")
    from config import SIGNAL_WEIGHTS, DEFAULT_PORTFOLIO
    from signals.technical import TechnicalAnalyzer
    from signals.fundamental import FundamentalAnalyzer
    from signals.sentiment import SentimentAnalyzer
    from signals.ml_model import MLModel
    from signals.options_flow import OptionsFlowAnalyzer
    from signals.insider import InsiderAnalyzer
    from signals.patterns import PatternRecognizer
    from signals.social import SocialSentimentAnalyzer
    from signals.macro import MacroAnalyzer
    from signals.regime import RegimeDetector
    from engine.backtester import Backtester
    from engine.risk_manager import RiskManager


class SignalAggregator:
    """Master signal orchestrator."""

    def __init__(self):
        self.tech = TechnicalAnalyzer()
        self.fund = FundamentalAnalyzer()
        self.sentiment = SentimentAnalyzer()
        self.ml = MLModel()
        self.options = OptionsFlowAnalyzer()
        self.insider = InsiderAnalyzer()
        self.patterns = PatternRecognizer()
        self.social = SocialSentimentAnalyzer()
        self.macro = MacroAnalyzer()
        self.regime = RegimeDetector()
        self.backtester = Backtester()
        self.risk = RiskManager()
        self.weights = SIGNAL_WEIGHTS

    def analyze(self, ticker: str, df: pd.DataFrame = None, company_name: str = "") -> Dict[str, Any]:
        """
        Comprehensive 10-layer analysis.
        Runs all layers in parallel, aggregates with weighted ensemble.
        """
        try:
            price = None
            if df is not None and len(df) > 0:
                price = float(df["Close"].iloc[-1])

            # If no dataframe provided, fetch it
            if df is None:
                df = self._fetch_data(ticker)

            if df is None or len(df) < 20:
                return {
                    "ticker": ticker,
                    "error": "Insufficient historical data",
                    "composite": {
                        "score": 0,
                        "action": "HOLD",
                        "confidence": "VERY_LOW",
                    }
                }

            price = price or float(df["Close"].iloc[-1])

            # ── Regime Detection ───────────────────────────────────────────
            regime_result = self.regime.detect(df)
            regime = regime_result.get("regime", "UNKNOWN")
            multipliers = regime_result.get("signal_multipliers", {})

            # ── Run all layers in parallel ─────────────────────────────────
            layer_results = {}
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = {
                    executor.submit(self.tech.analyze, df): "technical",
                    executor.submit(self.fund.analyze, ticker): "fundamental",
                    executor.submit(self.sentiment.analyze, ticker, company_name): "sentiment",
                    executor.submit(self.ml.predict, df): "ml",
                    executor.submit(self.options.analyze, ticker): "options_flow",
                    executor.submit(self.insider.analyze, ticker): "insider",
                    executor.submit(self.patterns.analyze, df): "patterns",
                    executor.submit(self.social.get_mentions, ticker, company_name): "social",
                    executor.submit(self.macro.analyze, ticker, df): "macro",
                }

                for future in as_completed(futures):
                    layer_name = futures[future]
                    try:
                        layer_results[layer_name] = future.result()
                    except Exception as e:
                        logger.error(f"Layer {layer_name} error: {e}")
                        layer_results[layer_name] = {
                            "signal_score": 0,
                            "action": "HOLD",
                            "error": str(e)
                        }

            # ── Normalize scores to -10 to +10 ────────────────────────────
            normalized = {}
            for layer, result in layer_results.items():
                score = result.get("signal_score", 0)

                # Normalize to -10 to +10
                if layer == "sentiment":
                    # Already -5 to +5, scale to -10 to +10
                    normalized[layer] = score * 2
                elif layer == "insider":
                    # -5 to +5, scale to -10 to +10
                    normalized[layer] = score * 2
                elif layer == "macro":
                    # -5 to +5, scale to -10 to +10
                    normalized[layer] = score * 2
                elif layer == "social":
                    # -5 to +5, scale to -10 to +10
                    normalized[layer] = score * 2
                else:
                    # Already -10 to +10
                    normalized[layer] = score

            # ── Apply regime multipliers ───────────────────────────────────
            adjusted = {}
            for layer, score in normalized.items():
                multiplier = multipliers.get(layer, 1.0)
                adjusted[layer] = score * multiplier

            # ── Weighted ensemble ──────────────────────────────────────────
            composite_score = 0.0
            total_weight = 0.0

            for layer, weight in self.weights.items():
                if layer in adjusted:
                    composite_score += adjusted[layer] * weight
                    total_weight += weight

            # If not all layers present, scale to remaining weight
            if total_weight > 0:
                composite_score = composite_score / total_weight
            else:
                composite_score = 0.0

            composite_score = max(-10, min(10, composite_score))

            # ── Determine action & confidence ──────────────────────────────
            abs_score = abs(composite_score)
            if   abs_score >= 7:  confidence = "VERY_HIGH"
            elif abs_score >= 5:  confidence = "HIGH"
            elif abs_score >= 3:  confidence = "MEDIUM"
            else:                 confidence = "LOW"

            action = "BUY" if composite_score >= 2.5 else (
                "SELL" if composite_score <= -2.5 else "HOLD"
            )

            # ── Hold period recommendation ─────────────────────────────────
            if action == "BUY":
                if composite_score >= 6:
                    hold_period = "7-14 days"
                elif composite_score >= 4:
                    hold_period = "5-10 days"
                else:
                    hold_period = "3-5 days"
            elif action == "SELL":
                if composite_score <= -6:
                    hold_period = "7-14 days to cover"
                else:
                    hold_period = "3-7 days to cover"
            else:
                hold_period = "N/A (hold)"

            # ── Compile top reasons (from best signals) ────────────────────
            all_reasons = []
            for layer in ["technical", "ml", "fundamental", "sentiment", "macro"]:
                if layer in layer_results:
                    reasons = layer_results[layer].get("reasons", [])
                    if reasons:
                        all_reasons.append({
                            "layer": layer,
                            "reason": reasons[0],
                            "score": adjusted.get(layer, 0)
                        })

            # Sort by abs score and take top 5
            all_reasons = sorted(all_reasons, key=lambda x: abs(x["score"]), reverse=True)[:5]
            top_reasons = [r["reason"] for r in all_reasons]

            # ── Risk assessment ───────────────────────────────────────────
            risk_assessment = self.risk.assess_full_risk(
                ticker, df, composite_score,
                layer_results.get("fundamental", {}).get("metrics", {})
            )

            # ── Stop loss calculation ─────────────────────────────────────
            try:
                sl_result = self.risk.dynamic_stop_loss(df, price, action)
                stop_loss = sl_result.get("stop_loss")
            except Exception:
                stop_loss = price * 0.95 if action == "BUY" else price * 1.05

            # ── Backtest summary (1Y) ─────────────────────────────────────
            backtest_summary = {}
            try:
                if len(df) >= 252:
                    def signal_fn(window):
                        tech_result = self.tech.analyze(window)
                        return {
                            "action": tech_result["action"],
                            "score": tech_result["signal_score"]
                        }

                    backtest = self.backtester.run(df, signal_fn)
                    if "error" not in backtest:
                        backtest_summary = {
                            "total_trades": backtest.get("total_trades"),
                            "win_rate": backtest.get("win_rate"),
                            "sharpe_ratio": backtest.get("sharpe_ratio"),
                            "alpha": backtest.get("alpha"),
                        }
            except Exception as e:
                logger.debug(f"Backtest error: {e}")

            # ── Kelly sizing ──────────────────────────────────────────────
            kelly = {}
            if backtest_summary and "win_rate" in backtest_summary:
                kelly = self.risk.kelly_position_size(
                    win_rate=backtest_summary.get("win_rate", 50) / 100,
                    avg_win_pct=backtest_summary.get("alpha", 2),
                    avg_loss_pct=-2.0,
                    capital=100000,
                    price=price,
                )

            # ── Final result ───────────────────────────────────────────────
            return {
                "ticker": ticker,
                "price": round(price, 2),
                "timestamp": datetime.now().isoformat(),
                "composite": {
                    "score": round(composite_score, 2),
                    "action": action,
                    "confidence": confidence,
                    "hold_period": hold_period,
                    "top_reasons": top_reasons,
                },
                "layer_scores": {
                    "technical": round(adjusted.get("technical", 0), 2),
                    "ml": round(adjusted.get("ml", 0), 2),
                    "fundamental": round(adjusted.get("fundamental", 0), 2),
                    "sentiment": round(adjusted.get("sentiment", 0), 2),
                    "options_flow": round(adjusted.get("options_flow", 0), 2),
                    "insider": round(adjusted.get("insider", 0), 2),
                    "macro": round(adjusted.get("macro", 0), 2),
                    "patterns": round(adjusted.get("patterns", 0), 2),
                    "social": round(adjusted.get("social", 0), 2),
                },
                "regime": {
                    "regime": regime,
                    "description": regime_result.get("description", ""),
                    "volatility": regime_result.get("volatility_ann"),
                },
                "risk": risk_assessment,
                "stop_loss": round(stop_loss, 2),
                "backtest": backtest_summary,
                "kelly": kelly,
                "layer_results": {
                    k: {
                        "score": v.get("signal_score"),
                        "action": v.get("action"),
                        "confidence": v.get("confidence", "N/A"),
                    }
                    for k, v in layer_results.items()
                },
            }

        except Exception as e:
            logger.error(f"Aggregator error [{ticker}]: {e}")
            return {
                "ticker": ticker,
                "error": str(e),
                "composite": {
                    "score": 0,
                    "action": "HOLD",
                    "confidence": "VERY_LOW",
                }
            }

    def _fetch_data(self, ticker: str) -> Optional[pd.DataFrame]:
        """Fetch historical data."""
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            df = stock.history(period="1y")
            if df is not None and len(df) > 20:
                return df
        except Exception as e:
            logger.error(f"Data fetch error [{ticker}]: {e}")
        return None

    def analyze_mutual_fund(self, mf_code: str) -> Dict[str, Any]:
        """Analyze mutual fund using AMFI + mfapi.in data."""
        try:
            import requests

            # Fetch from mfapi.in
            resp = requests.get(f"https://api.mfapi.in/mf/{mf_code}", timeout=10)
            if resp.status_code != 200:
                return {"error": f"MF {mf_code} not found"}

            data = resp.json()
            meta = data.get("meta", {})
            nav_data = data.get("data", [])

            if not nav_data:
                return {"error": "No NAV data"}

            latest_nav = float(nav_data[0]["nav"])
            prev_nav = float(nav_data[1]["nav"]) if len(nav_data) > 1 else latest_nav

            nav_change_pct = (latest_nav - prev_nav) / prev_nav * 100 if prev_nav else 0

            # Get 1Y, 3Y returns (simple approximation)
            returns_1y = 0
            returns_3y = 0
            if len(nav_data) > 252:
                nav_1y_ago = float(nav_data[252]["nav"]) if len(nav_data) > 252 else latest_nav
                returns_1y = (latest_nav - nav_1y_ago) / nav_1y_ago * 100

            scheme_name = meta.get("scheme_name", "Unknown")
            category = meta.get("category", "Unknown")

            score = 0.0
            reasons = []

            if nav_change_pct > 1.0:
                score += 1; reasons.append(f"NAV up {nav_change_pct:.2f}% recently")
            elif nav_change_pct < -1.0:
                score -= 1; reasons.append(f"NAV down {nav_change_pct:.2f}%")

            if returns_1y > 15:
                score += 2; reasons.append(f"1Y return {returns_1y:.1f}% — strong")
            elif returns_1y < 0:
                score -= 1; reasons.append(f"1Y negative {returns_1y:.1f}%")

            action = "BUY" if score > 1 else ("SELL" if score < -1 else "HOLD")

            return {
                "mf_code": mf_code,
                "scheme_name": scheme_name,
                "category": category,
                "latest_nav": round(latest_nav, 2),
                "nav_change_1d": round(nav_change_pct, 3),
                "returns_1y": round(returns_1y, 2),
                "signal_score": round(score, 2),
                "action": action,
                "reasons": reasons,
            }

        except Exception as e:
            logger.error(f"MF analysis error [{mf_code}]: {e}")
            return {"error": str(e), "mf_code": mf_code}
