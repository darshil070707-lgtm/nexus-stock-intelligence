"""
Global Macro Signal Generator
Uses GlobalDataFetcher for:
- Macro regime (risk-on/off)
- Sector performance
- Currency strength
- Interest rates
- VIX/volatility

For India stocks: rupee strength · FII/DII flows · India VIX
For US stocks: DXY · 10Y yield · VIX · credit spreads

Score: -5 to +5 based on tailwinds/headwinds for specific ticker
"""
import yfinance as yf
import requests
import pandas as pd
import numpy as np
from typing import Dict, Any
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

try:
    from data.fetcher_global import GlobalDataFetcher
except ImportError:
    try:
        from backend.data.fetcher_global import GlobalDataFetcher
    except ImportError:
        GlobalDataFetcher = None


class MacroAnalyzer:

    def __init__(self):
        self.fetcher = GlobalDataFetcher() if GlobalDataFetcher else None

    def analyze(self, ticker: str, df: pd.DataFrame = None) -> Dict[str, Any]:
        """Analyze macro tailwinds/headwinds for specific ticker."""
        try:
            is_india = ticker.endswith((".NS", ".BO"))
            is_us = not is_india

            if is_india:
                return self._analyze_india(ticker, df)
            else:
                return self._analyze_us(ticker, df)

        except Exception as e:
            logger.error(f"Macro analysis error [{ticker}]: {e}")
            return {
                "signal_score": 0,
                "action": "HOLD",
                "error": str(e),
            }

    def _analyze_india(self, ticker: str, df: pd.DataFrame = None) -> Dict[str, Any]:
        """India stock macro analysis: rupee, FII, VIX."""
        score = 0.0
        reasons = []
        metrics = {}

        try:
            # ── 1. Rupee strength (USDINR) ────────────────────────────────
            usdinr = yf.Ticker("USDINR=X").fast_info
            usdinr_price = usdinr.last_price or 84
            usdinr_prev = usdinr.previous_close or 84
            usdinr_change = (usdinr_price - usdinr_prev) / usdinr_prev * 100
            metrics["usdinr"] = round(usdinr_price, 2)
            metrics["usdinr_change_pct"] = round(usdinr_change, 2)

            # Stronger rupee (lower USDINR) = tailwind for Indian stocks
            if usdinr_change < -0.5:
                score += 1.5; reasons.append(f"Rupee strengthening ({usdinr_change:.2f}%) — tailwind")
            elif usdinr_change > 0.5:
                score -= 1.5; reasons.append(f"Rupee weakening (+{usdinr_change:.2f}%) — headwind")

            # ── 2. India VIX (INDIAVIX) ───────────────────────────────────
            try:
                indiavix = yf.Ticker("^INDIAVIX").fast_info
                indiavix_val = indiavix.last_price or 20
                metrics["india_vix"] = round(indiavix_val, 2)

                if indiavix_val < 15:
                    score += 1.2; reasons.append(f"India VIX {indiavix_val:.1f} — low fear, risk-on")
                elif indiavix_val > 30:
                    score -= 1.5; reasons.append(f"India VIX {indiavix_val:.1f} — elevated fear")
            except Exception:
                indiavix_val = 20

            # ── 3. FII/DII flows (from NSE) ────────────────────────────────
            fii_dii = self._get_fii_dii_flows()
            if fii_dii:
                metrics["fii_flows"] = fii_dii.get("fii_net", 0)
                metrics["dii_flows"] = fii_dii.get("dii_net", 0)

                if fii_dii.get("fii_net", 0) > 100:
                    score += 1.5; reasons.append(f"FII buying ₹{fii_dii['fii_net']:.0f}Cr (bullish)")
                elif fii_dii.get("fii_net", 0) < -100:
                    score -= 1.5; reasons.append(f"FII selling ₹{fii_dii['fii_net']:.0f}Cr (bearish)")

            # ── 4. Global risk sentiment (VIX as proxy) ───────────────────
            try:
                vix = yf.Ticker("^VIX").fast_info
                vix_val = vix.last_price or 20
                metrics["vix"] = round(vix_val, 2)

                if vix_val < 15:
                    score += 1.0; reasons.append(f"VIX {vix_val:.1f} — global risk-on")
                elif vix_val > 25:
                    score -= 1.0; reasons.append(f"VIX {vix_val:.1f} — global risk-off")
            except Exception:
                pass

            # ── 5. NIFTY 50 trend ────────────────────────────────────────
            try:
                nifty = yf.Ticker("^NSEI")
                hist = nifty.history(period="3mo")
                if len(hist) > 50:
                    nifty_ma50 = hist["Close"].rolling(50).mean().iloc[-1]
                    nifty_price = hist["Close"].iloc[-1]

                    if nifty_price > nifty_ma50 * 1.05:
                        score += 1.0; reasons.append("NIFTY above 50-day MA — uptrend")
                    elif nifty_price < nifty_ma50 * 0.95:
                        score -= 1.0; reasons.append("NIFTY below 50-day MA — downtrend")
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"India macro error: {e}")

        score = max(-5, min(5, score))
        action = "BUY" if score >= 1.5 else ("SELL" if score <= -1.5 else "HOLD")

        return {
            "signal_score": round(score, 2),
            "action": action,
            "market": "India",
            "metrics": metrics,
            "reasons": reasons,
        }

    def _analyze_us(self, ticker: str, df: pd.DataFrame = None) -> Dict[str, Any]:
        """US stock macro analysis: DXY, 10Y, VIX, sectors."""
        score = 0.0
        reasons = []
        metrics = {}

        try:
            # ── 1. US Dollar Index (DXY) ──────────────────────────────────
            dxy = yf.Ticker("DX-Y.NYB").fast_info
            dxy_price = dxy.last_price or 105
            dxy_prev = dxy.previous_close or 105
            dxy_change = (dxy_price - dxy_prev) / dxy_prev * 100
            metrics["dxy"] = round(dxy_price, 2)
            metrics["dxy_change_pct"] = round(dxy_change, 2)

            # Strong dollar generally headwind for exporters, tailwind for importers
            if dxy_change > 0.5:
                score -= 0.8; reasons.append(f"DXY strengthening (+{dxy_change:.2f}%) — EM headwind")
            elif dxy_change < -0.5:
                score += 0.8; reasons.append(f"DXY weakening ({dxy_change:.2f}%) — EM tailwind")

            # ── 2. US 10-Year Yield (TNX) ──────────────────────────────────
            tnx = yf.Ticker("^TNX").fast_info
            tnx_yield = tnx.last_price or 4.0
            metrics["us_10y_yield"] = round(tnx_yield, 2)

            # High yields = headwind for growth stocks, tailwind for value
            if tnx_yield > 4.5:
                score -= 1.2; reasons.append(f"10Y yield {tnx_yield:.2f}% — growth headwind")
            elif tnx_yield < 3.5:
                score += 1.2; reasons.append(f"10Y yield {tnx_yield:.2f}% — growth tailwind")

            # ── 3. VIX (Volatility Index) ──────────────────────────────────
            vix = yf.Ticker("^VIX").fast_info
            vix_val = vix.last_price or 20
            metrics["vix"] = round(vix_val, 2)

            if   vix_val < 12: score += 2.0; reasons.append(f"VIX {vix_val:.1f} — complacency, risk-on")
            elif vix_val < 18: score += 1.0; reasons.append(f"VIX {vix_val:.1f} — low fear")
            elif vix_val > 30: score -= 2.0; reasons.append(f"VIX {vix_val:.1f} — elevated fear")
            elif vix_val > 24: score -= 1.0; reasons.append(f"VIX {vix_val:.1f} — moderate fear")

            # ── 4. S&P 500 trend ──────────────────────────────────────────
            try:
                spy = yf.Ticker("SPY")
                hist = spy.history(period="3mo")
                if len(hist) > 50:
                    spy_ma50 = hist["Close"].rolling(50).mean().iloc[-1]
                    spy_price = hist["Close"].iloc[-1]
                    spy_change_20d = (spy_price / hist["Close"].iloc[-20] - 1) * 100

                    metrics["spy_20d_change"] = round(spy_change_20d, 2)

                    if spy_price > spy_ma50 * 1.05:
                        score += 1.2; reasons.append("S&P 500 above 50-day MA — strong uptrend")
                    elif spy_change_20d > 2:
                        score += 0.8; reasons.append(f"S&P 500 up {spy_change_20d:.1f}% in 20d — momentum")
                    elif spy_price < spy_ma50 * 0.95:
                        score -= 1.2; reasons.append("S&P 500 below 50-day MA — downtrend")
            except Exception:
                pass

            # ── 5. Sector rotation ────────────────────────────────────────
            if self.fetcher:
                sector_perf = self.fetcher.get_sector_performance()
                if sector_perf:
                    metrics["top_sector"] = list(sector_perf.items())[0] if sector_perf else None
                    top_perf = list(sector_perf.values())[0] if sector_perf else 0

                    if top_perf > 1.0:
                        score += 0.8; reasons.append(f"Sector rotation: {list(sector_perf.keys())[0]} leading")

            # ── 6. Credit spreads (HYG vs LQD proxy) ────────────────────
            try:
                hyg = yf.Ticker("HYG").fast_info  # Junk bonds
                lqd = yf.Ticker("LQD").fast_info  # Investment grade
                hyg_ret = (hyg.last_price - hyg.previous_close) / hyg.previous_close * 100 if hyg.previous_close else 0
                lqd_ret = (lqd.last_price - lqd.previous_close) / lqd.previous_close * 100 if lqd.previous_close else 0
                spread_move = hyg_ret - lqd_ret

                metrics["credit_spread_move"] = round(spread_move, 2)

                if spread_move > 0.3:
                    score += 1.0; reasons.append("Credit spreads widening — risk-off")
                elif spread_move < -0.3:
                    score += 1.0; reasons.append("Credit spreads tightening — risk-on")
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"US macro error: {e}")

        score = max(-5, min(5, score))
        action = "BUY" if score >= 1.5 else ("SELL" if score <= -1.5 else "HOLD")

        return {
            "signal_score": round(score, 2),
            "action": action,
            "market": "US",
            "metrics": metrics,
            "reasons": reasons,
        }

    def _get_fii_dii_flows(self) -> dict:
        """Fetch FII/DII flows from NSE (free public data)."""
        try:
            import requests
            import time
            import json

            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.nseindia.com",
            })

            # Hit NSE homepage first to get cookies
            session.get("https://www.nseindia.com", timeout=10)
            time.sleep(0.5)

            # FII/DII data endpoint
            url = "https://www.nseindia.com/api/fii-fiigain"
            resp = session.get(url, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("data", [{}])[0]

                return {
                    "fii_net": float(latest.get("FIINet", 0)),
                    "dii_net": float(latest.get("DIINet", 0)),
                    "timestamp": latest.get("DateVal", ""),
                }
        except Exception as e:
            logger.debug(f"FII/DII fetch error: {e}")

        return None

MacroSignalAnalyzer = MacroAnalyzer  # alias
