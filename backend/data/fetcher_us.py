"""
US Stock Data Fetcher
Primary: yfinance
Optional: Polygon.io for real-time
"""
import yfinance as yf
import pandas as pd
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class USDataFetcher:
    """Fetch US stock data."""

    def __init__(self):
        try:
            from config import FMP_API_KEY
            self.fmp_key = FMP_API_KEY
        except Exception:
            self.fmp_key = ""

    def get_historical(self, ticker: str, period: str = "1y") -> Optional[pd.DataFrame]:
        """Fetch OHLCV from yfinance."""
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)

            if df is None or len(df) == 0:
                logger.error(f"No data for {ticker}")
                return None

            # Rename columns to standard format
            df = df[["Open", "High", "Low", "Close", "Volume"]]
            return df

        except Exception as e:
            logger.error(f"yfinance error [{ticker}]: {e}")
            return None

    def get_info(self, ticker: str) -> Dict[str, Any]:
        """Get company info."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}

            return {
                "ticker": ticker,
                "name": info.get("longName", ""),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "dividend_yield": info.get("dividendYield"),
                "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
            }

        except Exception as e:
            logger.error(f"Info fetch error [{ticker}]: {e}")
            return {"ticker": ticker, "error": str(e)}

    def get_real_time(self, ticker: str) -> Dict[str, Any]:
        """Get real-time price."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info

            return {
                "ticker": ticker,
                "price": info.last_price,
                "change": info.last_price - (info.previous_close or info.last_price),
                "change_pct": ((info.last_price - (info.previous_close or info.last_price)) /
                              (info.previous_close or info.last_price)) * 100,
                "timestamp": pd.Timestamp.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Real-time fetch error [{ticker}]: {e}")
            return {"ticker": ticker, "error": str(e)}
