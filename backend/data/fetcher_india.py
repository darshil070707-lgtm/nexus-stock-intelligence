"""
India Stock Data Fetcher (NSE)
Primary: NSE API (via yfinance .NS)
Fallback: yfinance
FII/DII: NSE public data
"""
import yfinance as yf
import requests
import pandas as pd
import logging
from typing import Optional, Dict, Any
import time

logger = logging.getLogger(__name__)


class IndiaDataFetcher:
    """Fetch India (NSE) stock data."""

    NSE_BASE = "https://www.nseindia.com"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.nseindia.com",
        })

    def get_historical(self, ticker: str, period: str = "1y") -> Optional[pd.DataFrame]:
        """Fetch OHLCV for NSE stock."""
        try:
            # Ensure ticker has .NS suffix
            if not ticker.endswith(".NS"):
                ticker = ticker + ".NS"

            stock = yf.Ticker(ticker)
            df = stock.history(period=period)

            if df is None or len(df) == 0:
                logger.error(f"No data for {ticker}")
                return None

            df = df[["Open", "High", "Low", "Close", "Volume"]]
            return df

        except Exception as e:
            logger.error(f"India data error [{ticker}]: {e}")
            return None

    def get_info(self, ticker: str) -> Dict[str, Any]:
        """Get NSE company info."""
        try:
            if not ticker.endswith(".NS"):
                ticker = ticker + ".NS"

            stock = yf.Ticker(ticker)
            info = stock.info or {}

            return {
                "ticker": ticker,
                "name": info.get("longName", ""),
                "sector": info.get("sector", ""),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
            }

        except Exception as e:
            logger.error(f"Info fetch error [{ticker}]: {e}")
            return {"ticker": ticker, "error": str(e)}

    def get_real_time(self, ticker: str) -> Dict[str, Any]:
        """Get real-time NSE price."""
        try:
            if not ticker.endswith(".NS"):
                ticker = ticker + ".NS"

            stock = yf.Ticker(ticker)
            info = stock.fast_info

            return {
                "ticker": ticker,
                "price": info.last_price,
                "change": info.last_price - (info.previous_close or info.last_price),
                "change_pct": ((info.last_price - (info.previous_close or info.last_price)) /
                              (info.previous_close or info.last_price)) * 100 if info.previous_close else 0,
                "timestamp": pd.Timestamp.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Real-time fetch error [{ticker}]: {e}")
            return {"ticker": ticker, "error": str(e)}

    def get_fii_dii_flows(self) -> Dict[str, Any]:
        """Fetch FII/DII flows from NSE."""
        try:
            self.session.get(self.NSE_BASE, timeout=10)
            time.sleep(0.5)

            url = f"{self.NSE_BASE}/api/fii-fiigain"
            resp = self.session.get(url, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                latest = data.get("data", [{}])[0]

                return {
                    "fii_net": float(latest.get("FIINet", 0)),
                    "dii_net": float(latest.get("DIINet", 0)),
                    "date": latest.get("DateVal", ""),
                    "timestamp": pd.Timestamp.now().isoformat(),
                }

            return {"error": "Failed to fetch FII/DII"}

        except Exception as e:
            logger.error(f"FII/DII error: {e}")
            return {"error": str(e)}

    def get_market_status(self) -> Dict[str, Any]:
        """Get current NSE market status."""
        try:
            self.session.get(self.NSE_BASE, timeout=10)
            time.sleep(0.5)

            url = f"{self.NSE_BASE}/api/marketStatus"
            resp = self.session.get(url, timeout=8)

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "status": data.get("status", "unknown"),
                    "open": data.get("marketStatus", [{}])[0].get("market", "closed") == "open",
                    "timestamp": pd.Timestamp.now().isoformat(),
                }

        except Exception as e:
            logger.debug(f"Market status error: {e}")

        return {"status": "unknown"}
