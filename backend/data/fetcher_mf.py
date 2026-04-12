"""
Mutual Fund Data Fetcher
Free APIs: AMFI + mfapi.in
"""
import requests
import pandas as pd
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class MutualFundFetcher:
    """Fetch mutual fund data from free sources."""

    MFAPI_BASE = "https://api.mfapi.in/mf"

    def get_fund_info(self, code: str) -> Optional[Dict[str, Any]]:
        """Get MF info and NAV."""
        try:
            resp = requests.get(f"{self.MFAPI_BASE}/{code}", timeout=10)

            if resp.status_code != 200:
                logger.error(f"MF {code} not found")
                return None

            data = resp.json()
            meta = data.get("meta", {})
            nav_data = data.get("data", [])

            if not nav_data:
                return None

            latest_nav = float(nav_data[0]["nav"])
            latest_date = nav_data[0]["date"]

            return {
                "code": code,
                "name": meta.get("scheme_name", ""),
                "isin": meta.get("scheme_isin", ""),
                "category": meta.get("category", ""),
                "latest_nav": latest_nav,
                "nav_date": latest_date,
            }

        except Exception as e:
            logger.error(f"MF info error [{code}]: {e}")
            return None

    def get_nav_history(self, code: str, days: int = 365) -> Optional[pd.DataFrame]:
        """Get NAV history."""
        try:
            resp = requests.get(f"{self.MFAPI_BASE}/{code}", timeout=10)

            if resp.status_code != 200:
                return None

            data = resp.json()
            nav_data = data.get("data", [])

            if not nav_data:
                return None

            # Convert to DataFrame
            df = pd.DataFrame(nav_data)
            df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y")
            df["nav"] = df["nav"].astype(float)
            df = df.sort_values("date")

            # Limit to requested days
            cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
            df = df[df["date"] >= cutoff]

            return df[["date", "nav"]]

        except Exception as e:
            logger.error(f"NAV history error [{code}]: {e}")
            return None

    def calculate_returns(self, code: str) -> Dict[str, float]:
        """Calculate returns at different intervals."""
        try:
            hist = self.get_nav_history(code, days=1095)

            if hist is None or len(hist) < 2:
                return {"error": "Insufficient data"}

            latest_nav = float(hist["nav"].iloc[-1])

            returns = {}

            # 1-month
            if len(hist) >= 30:
                nav_1m_ago = float(hist["nav"].iloc[-30])
                returns["1m"] = (latest_nav - nav_1m_ago) / nav_1m_ago * 100

            # 3-month
            if len(hist) >= 90:
                nav_3m_ago = float(hist["nav"].iloc[-90])
                returns["3m"] = (latest_nav - nav_3m_ago) / nav_3m_ago * 100

            # 6-month
            if len(hist) >= 180:
                nav_6m_ago = float(hist["nav"].iloc[-180])
                returns["6m"] = (latest_nav - nav_6m_ago) / nav_6m_ago * 100

            # 1-year
            if len(hist) >= 252:
                nav_1y_ago = float(hist["nav"].iloc[-252])
                returns["1y"] = (latest_nav - nav_1y_ago) / nav_1y_ago * 100

            # 3-year
            if len(hist) >= 756:
                nav_3y_ago = float(hist["nav"].iloc[-756])
                returns["3y"] = (latest_nav - nav_3y_ago) / nav_3y_ago * 100

            return returns

        except Exception as e:
            logger.error(f"Returns calculation error [{code}]: {e}")
            return {"error": str(e)}

    def search_mf(self, query: str) -> List[Dict[str, Any]]:
        """Search for mutual funds by name."""
        try:
            # Get all MF codes
            resp = requests.get(f"{self.MFAPI_BASE}/", timeout=10)

            if resp.status_code != 200:
                return []

            # The endpoint returns a list of codes
            # Format: "AMFI_CODE|SCHEME_NAME|ISIN_CODE"
            all_mfs = []

            # Try parsing if it's JSON
            try:
                data = resp.json()
                if isinstance(data, dict):
                    for code, name in data.items():
                        if query.lower() in name.lower():
                            all_mfs.append({"code": code, "name": name})
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and query.lower() in item.get("name", "").lower():
                            all_mfs.append(item)
            except Exception:
                pass

            return all_mfs[:10]

        except Exception as e:
            logger.error(f"MF search error: {e}")
            return []

    def get_scheme_performance(self, code: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive scheme performance metrics."""
        try:
            info = self.get_fund_info(code)
            if not info:
                return None

            returns = self.calculate_returns(code)

            return {
                **info,
                "returns": returns,
            }

        except Exception as e:
            logger.error(f"Scheme performance error [{code}]: {e}")
            return None
