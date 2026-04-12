"""
Multi-Source Sentiment Analysis
Sources: yfinance news · NewsAPI · Google News RSS · feedparser
NLP: VADER (vaderSentiment) primary, FinBERT fallback, graceful degradation
Score: -5 to +5
"""
import feedparser
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    logger.warning("vaderSentiment not available — using keyword-based sentiment")

try:
    from transformers import pipeline
    FINBERT_AVAILABLE = True
except ImportError:
    FINBERT_AVAILABLE = False


class SentimentAnalyzer:

    def __init__(self):
        self.vader = SentimentIntensityAnalyzer() if VADER_AVAILABLE else None
        self.finbert = None
        if FINBERT_AVAILABLE:
            try:
                self.finbert = pipeline("sentiment-analysis",
                                       model="ProsusAI/finbert",
                                       framework="pt")
            except Exception as e:
                logger.debug(f"FinBERT loading failed: {e}")

    def analyze(self, ticker: str, company_name: str = "") -> dict:
        """Run multi-source sentiment analysis."""
        try:
            sources = {}
            all_sentiment_scores = []

            # ── 1. Google News RSS ─────────────────────────────────────────
            google_news = self._get_google_news(ticker, company_name)
            if google_news["articles"]:
                sources["google_news"] = google_news
                all_sentiment_scores.append(google_news["avg_sentiment"])

            # ── 2. NewsAPI ────────────────────────────────────────────────
            # Requires API key — skip if not configured
            try:
                newsapi = self._get_newsapi_sentiment(ticker)
                if newsapi["articles"]:
                    sources["newsapi"] = newsapi
                    all_sentiment_scores.append(newsapi["avg_sentiment"])
            except Exception as e:
                logger.debug(f"NewsAPI error: {e}")

            # ── 3. Yahoo Finance News ─────────────────────────────────────
            try:
                import yfinance as yf
                yahoo_news = self._get_yahoo_news(ticker)
                if yahoo_news["articles"]:
                    sources["yahoo_news"] = yahoo_news
                    all_sentiment_scores.append(yahoo_news["avg_sentiment"])
            except Exception as e:
                logger.debug(f"Yahoo news error: {e}")

            # ── Aggregate sentiment ────────────────────────────────────────
            if all_sentiment_scores:
                avg_sentiment = np.mean(all_sentiment_scores)
            else:
                avg_sentiment = 0.0

            # Convert to -5 to +5 scale
            signal_score = avg_sentiment * 5

            sentiment_label = (
                "VERY_POSITIVE" if avg_sentiment > 0.6 else (
                "POSITIVE" if avg_sentiment > 0.2 else (
                "NEUTRAL" if avg_sentiment > -0.2 else (
                "NEGATIVE" if avg_sentiment > -0.6 else
                "VERY_NEGATIVE"
            ))))

            action = (
                "BUY" if signal_score >= 2.5 else (
                "SELL" if signal_score <= -2.5 else
                "HOLD"
            ))

            reasons = []
            if avg_sentiment > 0.5:
                reasons.append(f"Overwhelmingly positive news sentiment ({avg_sentiment:.2f})")
            elif avg_sentiment > 0.2:
                reasons.append(f"Positive news tone ({avg_sentiment:.2f})")
            elif avg_sentiment < -0.5:
                reasons.append(f"Overwhelmingly negative news ({avg_sentiment:.2f})")
            elif avg_sentiment < -0.2:
                reasons.append(f"Negative news tone ({avg_sentiment:.2f})")

            article_count = sum(s["count"] for s in sources.values())
            if article_count > 20:
                reasons.append(f"High volume of coverage ({article_count} articles)")

            return {
                "signal_score": round(signal_score, 2),
                "action": action,
                "avg_sentiment": round(avg_sentiment, 3),
                "sentiment_label": sentiment_label,
                "sources": sources,
                "article_count": article_count,
                "reasons": reasons,
            }

        except Exception as e:
            logger.error(f"Sentiment analysis error [{ticker}]: {e}")
            return {
                "signal_score": 0,
                "action": "HOLD",
                "sentiment_label": "NEUTRAL",
                "error": str(e),
                "sources": {}
            }

    def _get_google_news(self, ticker: str, company_name: str = "") -> dict:
        """Fetch news from Google News RSS (no API key)."""
        articles = []
        sentiments = []

        try:
            # Google News search RSS
            query = company_name if company_name else ticker
            q = query.replace(" ", "+")
            url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"

            feed = feedparser.parse(url)

            for entry in feed.entries[:10]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                published = entry.get("published", "")

                # Only include recent news (last 7 days)
                try:
                    pub_date = pd.Timestamp(published)
                    if (datetime.now(pub_date.tzinfo) - pub_date).days > 7:
                        continue
                except Exception:
                    pass

                article_text = title + " " + summary
                sentiment = self._sentiment_score(article_text)
                sentiments.append(sentiment)

                articles.append({
                    "title": title[:100],
                    "source": entry.get("source", {}).get("title", "Google News"),
                    "published": published,
                    "sentiment": round(sentiment, 3),
                })

        except Exception as e:
            logger.debug(f"Google News error: {e}")

        avg_sentiment = np.mean(sentiments) if sentiments else 0.0

        return {
            "source": "Google News",
            "articles": articles,
            "count": len(articles),
            "avg_sentiment": round(avg_sentiment, 3),
        }

    def _get_newsapi_sentiment(self, ticker: str) -> dict:
        """Fetch news from NewsAPI (requires API key)."""
        from config import NEWS_API_KEY

        if not NEWS_API_KEY or NEWS_API_KEY == "":
            return {"source": "NewsAPI", "articles": [], "count": 0, "avg_sentiment": 0}

        articles = []
        sentiments = []

        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": ticker,
                "sortBy": "publishedAt",
                "language": "en",
                "apiKey": NEWS_API_KEY,
                "pageSize": 10,
            }

            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                for article in data.get("articles", [])[:10]:
                    title = article.get("title", "")
                    description = article.get("description", "")
                    published_at = article.get("publishedAt", "")

                    article_text = title + " " + description
                    sentiment = self._sentiment_score(article_text)
                    sentiments.append(sentiment)

                    articles.append({
                        "title": title[:100],
                        "source": article.get("source", {}).get("name", "NewsAPI"),
                        "published": published_at,
                        "sentiment": round(sentiment, 3),
                    })

        except Exception as e:
            logger.debug(f"NewsAPI error: {e}")

        avg_sentiment = np.mean(sentiments) if sentiments else 0.0

        return {
            "source": "NewsAPI",
            "articles": articles,
            "count": len(articles),
            "avg_sentiment": round(avg_sentiment, 3),
        }

    def _get_yahoo_news(self, ticker: str) -> dict:
        """Fetch news from Yahoo Finance."""
        articles = []
        sentiments = []

        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            news = stock.news or []

            for item in news[:10]:
                title = item.get("title", "")
                summary = item.get("summary", "")
                published = item.get("providerPublishTime", 0)

                article_text = title + " " + summary
                sentiment = self._sentiment_score(article_text)
                sentiments.append(sentiment)

                articles.append({
                    "title": title[:100],
                    "source": item.get("publisher", "Yahoo Finance"),
                    "published": str(published),
                    "sentiment": round(sentiment, 3),
                })

        except Exception as e:
            logger.debug(f"Yahoo Finance news error: {e}")

        avg_sentiment = np.mean(sentiments) if sentiments else 0.0

        return {
            "source": "Yahoo Finance",
            "articles": articles,
            "count": len(articles),
            "avg_sentiment": round(avg_sentiment, 3),
        }

    def _sentiment_score(self, text: str) -> float:
        """
        Analyze sentiment of text.
        Returns: -1 to +1 (negative to positive)
        """
        # Try FinBERT first
        if self.finbert:
            try:
                result = self.finbert(text[:512])  # Truncate to 512 tokens
                label = result[0]["label"].lower()
                score = result[0]["score"]

                if "positive" in label:
                    return min(1.0, score)
                elif "negative" in label:
                    return max(-1.0, -score)
                else:
                    return 0.0
            except Exception as e:
                logger.debug(f"FinBERT error: {e}")

        # Fall back to VADER
        if self.vader:
            try:
                scores = self.vader.polarity_scores(text)
                return scores["compound"]  # -1 to +1
            except Exception as e:
                logger.debug(f"VADER error: {e}")

        # Fallback: keyword-based simple sentiment
        return self._keyword_sentiment(text)

    def _keyword_sentiment(self, text: str) -> float:
        """Simple keyword-based sentiment (fallback)."""
        text_lower = text.lower()

        bullish = ["buy", "bullish", "strong buy", "outperform", "upside",
                   "breakout", "rise", "gain", "profit", "growth",
                   "positive", "upgrade", "beat", "exceed", "rally"]
        bearish = ["sell", "bearish", "sell", "underperform", "downside",
                   "breakdown", "decline", "loss", "drop", "negative",
                   "downgrade", "miss", "fail", "crash", "recession"]

        bull_count = sum(1 for w in bullish if w in text_lower)
        bear_count = sum(1 for w in bearish if w in text_lower)

        total = bull_count + bear_count
        if total == 0:
            return 0.0

        return (bull_count - bear_count) / total
