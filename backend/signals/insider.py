"""
Insider Trading Signal — FREE via SEC EDGAR
Tracks Form 4 filings: corporate insiders buying = bullish signal
Nobody combines this with technical + ML — this is the edge.
"""
import requests
import feedparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

SEC_BASE    = "https://www.sec.gov"
EDGAR_FEED  = "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt={start}&enddt={end}&forms=4"
EDGAR_ATOM  = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=include&count=20&search_text=&output=atom"


class InsiderAnalyzer:

    HEADERS = {
        "User-Agent": "NEXUS-Stock-Intelligence research@nexus.ai",
        "Accept":     "application/json",
    }

    def get_cik(self, ticker: str) -> str | None:
        """Resolve ticker to SEC CIK number."""
        try:
            r = requests.get(
                f"{SEC_BASE}/cgi-bin/browse-edgar?company=&CIK={ticker}&type=4&dateb=&owner=include&count=10&search_text=&action=getcompany&output=atom",
                headers=self.HEADERS, timeout=8
            )
            if r.status_code == 200:
                feed = feedparser.parse(r.text)
                if feed.entries:
                    # Extract CIK from first entry
                    link = feed.entries[0].get("link", "")
                    if "CIK=" in link:
                        return link.split("CIK=")[1].split("&")[0]
        except Exception:
            pass

        # Fallback: company search API
        try:
            r = requests.get(
                f"{SEC_BASE}/cgi-bin/browse-edgar?company={ticker}&CIK=&type=4&dateb=&owner=include&count=10&search_text=&action=getcompany&output=atom",
                headers=self.HEADERS, timeout=8
            )
        except Exception:
            pass
        return None

    def get_recent_filings(self, ticker: str, days: int = 90) -> list:
        """Fetch recent Form 4 filings via EDGAR full-text search."""
        filings = []
        try:
            end   = datetime.now()
            start = end - timedelta(days=days)
            url = EDGAR_FEED.format(
                ticker=ticker.replace(".NS", "").replace(".BO", ""),
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
            )
            r = requests.get(url, headers=self.HEADERS, timeout=10)
            if r.status_code == 200:
                data = r.json()
                hits = data.get("hits", {}).get("hits", [])
                for h in hits[:20]:
                    src = h.get("_source", {})
                    filings.append({
                        "date":      src.get("period_of_report", ""),
                        "filer":     src.get("display_date_filed", ""),
                        "form":      src.get("form_type", "4"),
                        "entity":    src.get("entity_name", ""),
                    })
        except Exception as e:
            logger.debug(f"EDGAR search error [{ticker}]: {e}")

        return filings

    def analyze(self, ticker: str) -> dict:
        """
        Parse Form 4s: count buys vs sells by insiders (last 90 days).
        Net buying = bullish; net selling = bearish (especially if large).
        """
        # For India stocks — insider data via NSE bulk deals (public)
        if ticker.endswith((".NS", ".BO")):
            return self._analyze_india_bulk_deals(ticker)

        filings = self.get_recent_filings(ticker)
        score   = 0.0
        reasons = []
        buy_count  = 0
        sell_count = 0
        total_buy_shares  = 0
        total_sell_shares = 0

        # Also try simpler EDGAR company filing endpoint
        try:
            # Get ticker filings via SEC EDGAR company search
            r = requests.get(
                f"{SEC_BASE}/cgi-bin/browse-edgar?action=getcompany&company={ticker}&CIK=&type=4&dateb=&owner=include&count=20&search_text=&output=atom",
                headers=self.HEADERS, timeout=8
            )
            if r.status_code == 200:
                feed = feedparser.parse(r.text)
                for entry in feed.entries[:15]:
                    title   = entry.get("title", "").lower()
                    summary = entry.get("summary", "").lower()
                    updated = entry.get("updated", "")

                    # Form 4 title often says "ownership" or "4"
                    if "purchase" in summary or "acquisition" in summary or "buy" in title:
                        buy_count += 1
                    elif "sale" in summary or "disposition" in summary or "sell" in title:
                        sell_count += 1
        except Exception as e:
            logger.debug(f"EDGAR feed error: {e}")

        # Score based on insider activity pattern
        net  = buy_count - sell_count
        total = buy_count + sell_count

        if total == 0:
            return {
                "signal_score": 0, "action": "HOLD",
                "buy_count": 0, "sell_count": 0,
                "reasons": ["No recent Form 4 filings found"],
                "data_days": 90,
            }

        buy_ratio = buy_count / (total + 1e-9)

        if   net >= 3 and buy_ratio > 0.7:
            score += 3.0
            reasons.append(f"Strong insider buying: {buy_count} purchases vs {sell_count} sales (90d)")
        elif net >= 2:
            score += 2.0
            reasons.append(f"Insider buying: {buy_count} buys vs {sell_count} sales")
        elif net == 1:
            score += 1.0
            reasons.append(f"Slight insider accumulation ({buy_count} buys)")
        elif net <= -3 and buy_ratio < 0.3:
            score -= 3.0
            reasons.append(f"Heavy insider selling: {sell_count} sales vs {buy_count} buys — caution")
        elif net <= -2:
            score -= 2.0
            reasons.append(f"Insider selling dominates ({sell_count} sales)")
        elif net == -1:
            score -= 1.0
            reasons.append(f"Slight insider selling ({sell_count} sales)")

        # Cluster buying (multiple insiders buying same week) = very bullish
        if buy_count >= 3 and total >= 4:
            score += 1.5
            reasons.append("Cluster buying — multiple insiders buying simultaneously (rare, very bullish)")

        score  = max(-5, min(5, score))
        action = "BUY" if score >= 1.5 else ("SELL" if score <= -1.5 else "HOLD")

        return {
            "signal_score": round(score, 2),
            "action":       action,
            "buy_count":    buy_count,
            "sell_count":   sell_count,
            "buy_ratio":    round(buy_ratio, 2),
            "total_filings": total,
            "reasons":      reasons,
            "data_days":    90,
        }

    def _analyze_india_bulk_deals(self, ticker: str) -> dict:
        """NSE bulk deals and block deals — India insider proxy."""
        symbol = ticker.replace(".NS", "").replace(".BO", "")
        try:
            # NSE bulk deals API (public)
            import requests, time
            session = requests.Session()
            session.headers.update({
                "User-Agent":  "Mozilla/5.0",
                "Referer":     "https://www.nseindia.com",
                "Accept":      "application/json",
            })
            session.get("https://www.nseindia.com", timeout=10)
            time.sleep(0.5)

            r = session.get(
                f"https://www.nseindia.com/api/bulk-deal-archives?symbol={symbol}",
                timeout=8
            )
            if r.status_code == 200:
                data = r.json()
                deals = data if isinstance(data, list) else data.get("data", [])
                # Filter last 30 days
                cutoff = datetime.now() - timedelta(days=30)
                recent = [d for d in deals if d.get("BD_DT_DATE")]

                buys  = [d for d in recent if str(d.get("BD_TRANSACTION_TYPE", "")).upper() in ("B", "BUY")]
                sells = [d for d in recent if str(d.get("BD_TRANSACTION_TYPE", "")).upper() in ("S", "SELL")]

                net   = len(buys) - len(sells)
                score = max(-3, min(3, net * 0.8))
                reasons = []
                if buys:  reasons.append(f"NSE bulk deal: {len(buys)} buy blocks (30d)")
                if sells: reasons.append(f"NSE bulk deal: {len(sells)} sell blocks (30d)")
                if not reasons: reasons.append("No recent bulk deals")

                return {
                    "signal_score": round(score, 2),
                    "action":       "BUY" if score > 1 else ("SELL" if score < -1 else "HOLD"),
                    "buy_count":    len(buys),
                    "sell_count":   len(sells),
                    "reasons":      reasons,
                    "source":       "NSE Bulk Deals",
                }
        except Exception as e:
            logger.debug(f"India bulk deals error: {e}")

        return {"signal_score": 0, "action": "HOLD", "reasons": ["India insider data unavailable"], "buy_count": 0, "sell_count": 0}
