"""
Social Sentiment — Reddit (r/stocks, r/IndiaInvestments, r/wallstreetbets)
Via: Pushshift-compatible endpoints + Reddit RSS (no API key needed)
"""
import requests
import feedparser
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class SocialSentimentAnalyzer:

    SUBREDDITS = ["stocks", "investing", "wallstreetbets", "IndiaInvestments", "StockMarket"]
    HEADERS    = {"User-Agent": "NEXUS:StockIntelligence:v2.0 (research bot)"}

    def _reddit_rss(self, subreddit: str, query: str) -> list:
        """Reddit search RSS — no API key needed."""
        posts = []
        try:
            q   = query.replace(" ", "+")
            url = f"https://www.reddit.com/r/{subreddit}/search.rss?q={q}&sort=new&limit=10"
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                title   = entry.get("title", "")
                summary = entry.get("summary", "")
                posts.append({"title": title, "text": summary[:200], "subreddit": subreddit})
        except Exception as e:
            logger.debug(f"Reddit RSS error [{subreddit}]: {e}")
        return posts

    def _score_text(self, text: str) -> float:
        """Simple financial keyword scoring (VADER-like, custom)."""
        text_lower = text.lower()

        bullish = ["buy", "bullish", "moon", "breakout", "undervalued", "strong buy",
                   "accumulate", "target", "upside", "long", "calls", "rally", "rocket",
                   "squeeze", "massive", "huge", "underpriced", "cheap"]
        bearish = ["sell", "bearish", "short", "dump", "crash", "overvalued", "puts",
                   "weak", "decline", "breakdown", "avoid", "trash", "falling", "drop",
                   "bankruptcy", "fraud", "scam", "overpriced", "expensive"]

        bull_count = sum(1 for w in bullish if w in text_lower)
        bear_count = sum(1 for w in bearish if w in text_lower)

        total = bull_count + bear_count
        if total == 0: return 0.0
        return (bull_count - bear_count) / total

    def get_mentions(self, ticker: str, company: str = "") -> dict:
        """Count ticker mentions + sentiment across subreddits."""
        clean_ticker = ticker.replace(".NS", "").replace(".BO", "")
        queries      = [clean_ticker]
        if company:
            # Use first word of company name
            first_word = company.split()[0] if company else ""
            if first_word and len(first_word) > 3:
                queries.append(first_word)

        all_posts = []
        for sub in self.SUBREDDITS[:3]:    # limit to 3 subreddits
            for q in queries[:1]:
                all_posts.extend(self._reddit_rss(sub, q))

        if not all_posts:
            return {"mention_count": 0, "signal_score": 0, "action": "HOLD",
                    "sentiment": "NEUTRAL", "posts": []}

        # Score each post
        scores = []
        for post in all_posts:
            combined = post["title"] + " " + post.get("text", "")
            # Only count if ticker actually mentioned
            if clean_ticker.lower() in combined.lower() or (company and company.split()[0].lower() in combined.lower()):
                scores.append(self._score_text(combined))

        if not scores:
            return {"mention_count": len(all_posts), "signal_score": 0,
                    "action": "HOLD", "sentiment": "NEUTRAL", "posts": []}

        avg_score = sum(scores) / len(scores)
        mention_count = len(scores)

        # High mention count itself is bullish (attention = momentum)
        mention_bonus = min(1.0, mention_count / 10)

        signal = avg_score * 5 + (mention_bonus if avg_score > 0 else -mention_bonus)
        signal = max(-5, min(5, signal))

        sentiment = "POSITIVE" if avg_score > 0.1 else ("NEGATIVE" if avg_score < -0.1 else "NEUTRAL")
        action    = "BUY" if signal > 1.5 else ("SELL" if signal < -1.5 else "HOLD")

        sample_titles = [p["title"][:80] for p in all_posts[:3]]

        return {
            "mention_count":   mention_count,
            "avg_sentiment":   round(avg_score, 3),
            "sentiment":       sentiment,
            "signal_score":    round(signal, 2),
            "action":          action,
            "sample_posts":    sample_titles,
            "subreddits_checked": self.SUBREDDITS[:3],
        }
