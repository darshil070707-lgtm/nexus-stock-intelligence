"""
Fundamental Analysis Engine
Metrics: P/E · PEG · ROE · D/E · EPS growth · Revenue growth · FCF · P/B ·
         Analyst consensus · Insider ownership % · Institutional ownership % ·
         Dividend yield · Earnings surprise
Score: -10 to +10
"""
import yfinance as yf
import requests
import pandas as pd
import numpy as np
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class FundamentalAnalyzer:

    def analyze(self, ticker: str) -> Dict[str, Any]:
        """Run full fundamental analysis."""
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}

            score = 0.0
            reasons = []
            metrics = {}

            # ── 1. P/E Ratio ──────────────────────────────────────────────
            pe_ratio = info.get("trailingPE")
            if pe_ratio and pe_ratio > 0:
                metrics["pe_ratio"] = round(pe_ratio, 2)
                # Industry median ~20
                if   pe_ratio < 12: score += 2.0; reasons.append(f"P/E {pe_ratio:.1f} — undervalued")
                elif pe_ratio < 18: score += 1.0; reasons.append(f"P/E {pe_ratio:.1f} — fair value")
                elif pe_ratio > 50: score -= 2.0; reasons.append(f"P/E {pe_ratio:.1f} — overvalued")
                elif pe_ratio > 30: score -= 1.0; reasons.append(f"P/E {pe_ratio:.1f} — expensive")

            # ── 2. PEG Ratio (P/E to Growth) ──────────────────────────────
            # Estimated from analyst growth rates
            peg = self._calculate_peg(ticker, pe_ratio, info)
            if peg:
                metrics["peg_ratio"] = round(peg, 2)
                if   peg < 1.0: score += 1.5; reasons.append(f"PEG {peg:.2f} — good value for growth")
                elif peg > 3.0: score -= 1.5; reasons.append(f"PEG {peg:.2f} — expensive for growth")

            # ── 3. Debt-to-Equity Ratio ───────────────────────────────────
            de_ratio = info.get("debtToEquity")
            if de_ratio:
                metrics["debt_to_equity"] = round(de_ratio, 2)
                if   de_ratio < 0.5: score += 1.5; reasons.append(f"D/E {de_ratio:.2f} — strong balance sheet")
                elif de_ratio < 1.5: score += 0.5; reasons.append(f"D/E {de_ratio:.2f} — moderate leverage")
                elif de_ratio > 3.0: score -= 2.0; reasons.append(f"D/E {de_ratio:.2f} — highly leveraged (risky)")
                elif de_ratio > 2.0: score -= 1.0; reasons.append(f"D/E {de_ratio:.2f} — elevated leverage")

            # ── 4. ROE (Return on Equity) ─────────────────────────────────
            roe = info.get("returnOnEquity")
            if roe:
                metrics["roe"] = round(roe * 100, 2)
                if   roe > 0.15: score += 2.0; reasons.append(f"ROE {roe*100:.1f}% — excellent management")
                elif roe > 0.10: score += 1.0; reasons.append(f"ROE {roe*100:.1f}% — good returns")
                elif roe > 0.05: score += 0.5
                elif roe < 0:    score -= 2.0; reasons.append(f"ROE {roe*100:.1f}% — negative (warning)")

            # ── 5. EPS Growth ─────────────────────────────────────────────
            eps_growth = self._get_eps_growth(ticker, info)
            if eps_growth is not None:
                metrics["eps_growth_ttm"] = round(eps_growth, 2)
                if   eps_growth > 0.25: score += 1.8; reasons.append(f"EPS growth {eps_growth*100:.0f}% YoY — strong")
                elif eps_growth > 0.10: score += 1.0; reasons.append(f"EPS growth {eps_growth*100:.0f}%")
                elif eps_growth < 0:    score -= 1.5; reasons.append(f"EPS declining {eps_growth*100:.0f}%")

            # ── 6. Revenue Growth ─────────────────────────────────────────
            revenue_growth = self._get_revenue_growth(ticker, info)
            if revenue_growth is not None:
                metrics["revenue_growth"] = round(revenue_growth, 2)
                if   revenue_growth > 0.20: score += 1.5; reasons.append(f"Revenue growth {revenue_growth*100:.0f}%")
                elif revenue_growth > 0.05: score += 0.5
                elif revenue_growth < 0:    score -= 1.0; reasons.append(f"Revenue declining {revenue_growth*100:.0f}%")

            # ── 7. Free Cash Flow ─────────────────────────────────────────
            fcf = info.get("freeCashflow")
            if fcf and fcf > 0:
                metrics["fcf"] = round(fcf / 1e9, 2)
                score += 1.0; reasons.append(f"Positive FCF ${fcf/1e9:.2f}B")
            elif fcf and fcf < 0:
                score -= 1.0; reasons.append(f"Negative FCF ${fcf/1e9:.2f}B — cash burn")

            # ── 8. Price-to-Book Ratio ────────────────────────────────────
            pb = info.get("priceToBook")
            if pb and pb > 0:
                metrics["price_to_book"] = round(pb, 2)
                if   pb < 1.5: score += 1.0; reasons.append(f"P/B {pb:.2f} — below book value")
                elif pb > 4.0: score -= 1.0; reasons.append(f"P/B {pb:.2f} — expensive")

            # ── 9. Dividend Yield ─────────────────────────────────────────
            div_yield = info.get("dividendYield")
            if div_yield:
                metrics["dividend_yield"] = round(div_yield * 100, 2)
                if   div_yield > 0.04: score += 1.0; reasons.append(f"Div yield {div_yield*100:.2f}% — attractive")
                elif div_yield > 0.02: score += 0.5
                if div_yield == 0:     reasons.append("No dividend — growth focused")

            # ── 10. Analyst Consensus ─────────────────────────────────────
            analyst_score = self._get_analyst_consensus(ticker, info)
            if analyst_score is not None:
                metrics["analyst_consensus"] = analyst_score
                if   analyst_score >= 4.5: score += 1.5; reasons.append("Strong Buy consensus")
                elif analyst_score >= 3.5: score += 1.0; reasons.append("Buy consensus")
                elif analyst_score <= 2.0: score -= 1.5; reasons.append("Sell consensus")
                elif analyst_score <= 2.5: score -= 1.0; reasons.append("Reduce consensus")

            # ── 11. Insider Ownership ─────────────────────────────────────
            insider_own = info.get("heldPercentInsiders")
            if insider_own:
                metrics["insider_ownership"] = round(insider_own * 100, 2)
                if   insider_own > 0.20: score += 1.2; reasons.append(f"Insiders own {insider_own*100:.1f}% — skin in game")
                elif insider_own < 0.01: score -= 0.5; reasons.append("Minimal insider ownership")

            # ── 12. Institutional Ownership ────────────────────────────────
            inst_own = info.get("heldPercentInstitutions")
            if inst_own:
                metrics["institutional_ownership"] = round(inst_own * 100, 2)
                if   inst_own > 0.70: score += 0.8; reasons.append(f"Institutions own {inst_own*100:.0f}%")
                elif inst_own < 0.20: score -= 0.5; reasons.append("Low institutional ownership")

            # ── 13. Current Ratio (Liquidity) ──────────────────────────────
            current_ratio = info.get("currentRatio")
            if current_ratio:
                metrics["current_ratio"] = round(current_ratio, 2)
                if   current_ratio > 2.0: score += 0.8; reasons.append(f"Strong liquidity (CR {current_ratio:.2f})")
                elif current_ratio < 1.0: score -= 1.0; reasons.append(f"Weak liquidity (CR {current_ratio:.2f})")

            # ── 14. Margin Analysis ───────────────────────────────────────
            gross_margin = info.get("grossMargins")
            operating_margin = info.get("operatingMargins")
            profit_margin = info.get("profitMargins")

            if gross_margin:
                metrics["gross_margin"] = round(gross_margin * 100, 2)
                if gross_margin > 0.40: score += 0.5; reasons.append(f"Strong gross margin {gross_margin*100:.1f}%")

            if profit_margin:
                metrics["profit_margin"] = round(profit_margin * 100, 2)
                if   profit_margin > 0.15: score += 0.8; reasons.append(f"Excellent net margin {profit_margin*100:.1f}%")
                elif profit_margin < 0:    score -= 1.0; reasons.append(f"Negative profit margin {profit_margin*100:.1f}%")

            # ── Final Score ────────────────────────────────────────────────
            score = max(-10, min(10, score))
            action = "BUY" if score >= 3 else ("SELL" if score <= -3 else "HOLD")

            return {
                "signal_score": round(score, 2),
                "action": action,
                "metrics": metrics,
                "reasons": reasons,
            }

        except Exception as e:
            logger.error(f"Fundamental analysis error [{ticker}]: {e}")
            return {
                "signal_score": 0,
                "action": "HOLD",
                "error": str(e),
                "metrics": {}
            }

    def _calculate_peg(self, ticker: str, pe_ratio, info: dict):
        """Calculate PEG ratio = P/E / Growth Rate"""
        try:
            growth = info.get("earningsGrowth") or info.get("revenuePerShare")
            if growth and pe_ratio and growth > 0:
                peg = pe_ratio / (growth * 100)
                return peg
        except Exception:
            pass
        return None

    def _get_eps_growth(self, ticker: str, info: dict):
        """Get EPS growth rate"""
        try:
            # Try earnings growth directly
            growth = info.get("earningsGrowth")
            if growth:
                return float(growth)

            # Try to estimate from trailing vs forward EPS
            trailing = info.get("trailingEps")
            forward = info.get("forwardEps")
            if trailing and forward and trailing > 0:
                return (forward - trailing) / trailing

        except Exception:
            pass
        return None

    def _get_revenue_growth(self, ticker: str, info: dict):
        """Get revenue growth rate"""
        try:
            # Try revenue growth directly
            growth = info.get("revenueGrowth")
            if growth:
                return float(growth)

            # Yahoo typically shows TTM metrics
            # Fallback: estimate from quarterly data
            return None
        except Exception:
            pass
        return None

    def _get_analyst_consensus(self, ticker: str, info: dict):
        """Get analyst recommendation score (1=strong buy, 5=strong sell)"""
        try:
            # Yahoo's rating: 1-5 scale
            rec = info.get("recommendationKey")
            score_map = {
                "strong_buy": 1.0,
                "buy": 2.0,
                "hold": 3.0,
                "sell": 4.0,
                "strong_sell": 5.0,
            }

            if rec and rec in score_map:
                # Return inverted (1-5) so 5 is bullish
                return 6 - score_map[rec]

            # Fallback to rating score
            rating = info.get("overallRating")
            if rating:
                return float(rating)

        except Exception:
            pass
        return None
