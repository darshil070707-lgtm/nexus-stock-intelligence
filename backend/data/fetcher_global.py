"""
Global Market Data Fetcher
Fetches: Forex · Commodities · Bonds · Global Indices · Fear & Greed · Economic data
All FREE sources — yfinance, FRED, St. Louis Fed
"""
import yfinance as yf
import requests
import pandas as pd
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class GlobalDataFetcher:

    # ── Macro Assets ──────────────────────────────────────────────────────────
    MACRO_TICKERS = {
        # Equities / Risk
        "SPY":   "S&P 500 ETF",
        "^VIX":  "VIX Fear Index",
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ",
        "^NSEI": "NIFTY 50",
        "^BSESN":"SENSEX",
        # Bonds
        "^TNX":  "US 10Y Yield",
        "^TYX":  "US 30Y Yield",
        "^IRX":  "US 3M T-Bill",
        # Commodities
        "GC=F":  "Gold Futures",
        "SI=F":  "Silver Futures",
        "CL=F":  "Crude Oil WTI",
        "NG=F":  "Natural Gas",
        # Forex
        "DX-Y.NYB": "US Dollar Index (DXY)",
        "USDINR=X":  "USD/INR",
        "EURUSD=X":  "EUR/USD",
        "USDJPY=X":  "USD/JPY",
        # Crypto as risk proxy
        "BTC-USD": "Bitcoin",
    }

    def get_all_macro(self) -> dict:
        results = {}
        for sym, name in self.MACRO_TICKERS.items():
            try:
                info = yf.Ticker(sym).fast_info
                prev = info.previous_close or 1
                results[sym] = {
                    "name":       name,
                    "price":      round(info.last_price, 4),
                    "change_pct": round((info.last_price - prev) / prev * 100, 3),
                }
            except Exception:
                pass
        return results

    def get_macro_regime(self) -> dict:
        """
        Determine market regime from macro data.
        Returns: risk_on/risk_off/transition + sub-regime
        """
        macro = self.get_all_macro()

        vix   = macro.get("^VIX",  {}).get("price", 20)
        spy   = macro.get("SPY",   {}).get("change_pct", 0)
        gold  = macro.get("GC=F",  {}).get("change_pct", 0)
        oil   = macro.get("CL=F",  {}).get("change_pct", 0)
        dxy   = macro.get("DX-Y.NYB", {}).get("change_pct", 0)
        tnx   = macro.get("^TNX", {}).get("price", 4)
        btc   = macro.get("BTC-USD", {}).get("change_pct", 0)

        regime_score = 0
        signals = []

        # VIX: < 15 risk-on, > 25 risk-off, > 35 extreme fear
        if   vix < 15: regime_score += 2;  signals.append(f"VIX {vix:.1f} — extreme complacency")
        elif vix < 20: regime_score += 1;  signals.append(f"VIX {vix:.1f} — low fear")
        elif vix > 35: regime_score -= 3;  signals.append(f"VIX {vix:.1f} — extreme fear")
        elif vix > 25: regime_score -= 2;  signals.append(f"VIX {vix:.1f} — elevated fear")
        else:          regime_score -= 0.5

        # SPY direction
        if spy >  0.5: regime_score += 1.5; signals.append(f"S&P 500 up {spy:.1f}%")
        if spy < -0.5: regime_score -= 1.5; signals.append(f"S&P 500 down {spy:.1f}%")

        # DXY: strong dollar = risk-off for EM / India
        if   dxy >  0.5: regime_score -= 0.5; signals.append(f"DXY strong +{dxy:.1f}% (EM headwind)")
        elif dxy < -0.5: regime_score += 0.5; signals.append(f"DXY weak {dxy:.1f}% (EM tailwind)")

        # Gold: rising gold = risk-off hedge
        if   gold >  1: regime_score -= 0.5; signals.append(f"Gold rising +{gold:.1f}% (defensive)")
        elif gold < -1: regime_score += 0.3

        # 10Y yield: rising = headwind for growth stocks
        if   tnx > 4.5: regime_score -= 0.5; signals.append(f"10Y yield {tnx:.2f}% — high (growth headwind)")
        elif tnx < 3.5: regime_score += 0.5; signals.append(f"10Y yield {tnx:.2f}% — low (growth tailwind)")

        # BTC as risk proxy
        if   btc >  3: regime_score += 0.5; signals.append(f"BTC +{btc:.1f}% — risk-on mood")
        elif btc < -3: regime_score -= 0.5

        regime_score = max(-10, min(10, regime_score))

        if   regime_score >= 3:  regime = "RISK_ON";     regime_label = "🟢 Risk-On"
        elif regime_score <= -3: regime = "RISK_OFF";    regime_label = "🔴 Risk-Off"
        else:                    regime = "TRANSITION";  regime_label = "🟡 Transition"

        # Sub-regime
        if vix > 35:             sub = "EXTREME_FEAR"
        elif vix > 25 and spy < -0.5: sub = "BEAR"
        elif vix < 15 and spy > 0.5:  sub = "BULL_COMPLACENCY"
        elif tnx > 4.5:          sub = "RATE_SHOCK"
        else:                    sub = "NEUTRAL"

        return {
            "regime":        regime,
            "label":         regime_label,
            "sub_regime":    sub,
            "score":         round(regime_score, 2),
            "signals":       signals,
            "vix":           vix,
            "spy_change":    spy,
            "dxy_change":    dxy,
            "tnx_yield":     tnx,
            "gold_change":   gold,
            "btc_change":    btc,
        }

    def get_sector_performance(self) -> dict:
        """US Sector ETF performance — for rotation detection"""
        sector_etfs = {
            "XLK": "Technology",     "XLF": "Financials",
            "XLV": "Healthcare",     "XLE": "Energy",
            "XLY": "Consumer Disc",  "XLP": "Consumer Staples",
            "XLI": "Industrials",    "XLB": "Materials",
            "XLU": "Utilities",      "XLRE": "Real Estate",
            "XLC": "Communication",
        }
        perf = {}
        for sym, name in sector_etfs.items():
            try:
                info = yf.Ticker(sym).fast_info
                prev = info.previous_close or 1
                perf[name] = round((info.last_price - prev) / prev * 100, 2)
            except Exception:
                pass
        return dict(sorted(perf.items(), key=lambda x: x[1], reverse=True))

    def get_fear_greed_proxy(self) -> dict:
        """
        Compute Fear & Greed index proxy from public data.
        Components: VIX · SPY momentum · Junk bond demand · Market breadth
        """
        try:
            macro = self.get_all_macro()
            vix   = macro.get("^VIX", {}).get("price", 20)

            # SPY 20-day momentum
            spy_df = yf.Ticker("SPY").history(period="1mo")
            spy_mom = 0
            if not spy_df.empty and len(spy_df) >= 2:
                spy_mom = (spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[0] - 1) * 100

            # HYG (junk bonds) vs LQD (investment grade) spread proxy
            hyg = yf.Ticker("HYG").fast_info
            lqd = yf.Ticker("LQD").fast_info
            junk_vs_ig = 0
            try:
                hyg_chg = (hyg.last_price - hyg.previous_close) / hyg.previous_close * 100
                lqd_chg = (lqd.last_price - lqd.previous_close) / lqd.previous_close * 100
                junk_vs_ig = hyg_chg - lqd_chg
            except Exception:
                pass

            # Score 0-100
            score = 50
            if vix < 12: score += 20
            elif vix < 15: score += 10
            elif vix > 30: score -= 20
            elif vix > 25: score -= 10

            score += min(20, max(-20, spy_mom * 2))
            score += min(10, max(-10, junk_vs_ig * 5))
            score = max(0, min(100, score))

            if score >= 75: label = "Extreme Greed"
            elif score >= 55: label = "Greed"
            elif score >= 45: label = "Neutral"
            elif score >= 25: label = "Fear"
            else: label = "Extreme Fear"

            return {"score": round(score, 1), "label": label, "components": {
                "vix": vix, "spy_momentum_1m": round(spy_mom, 2), "junk_vs_ig": round(junk_vs_ig, 3)
            }}
        except Exception as e:
            logger.error(f"Fear/Greed error: {e}")
            return {"score": 50, "label": "Neutral"}
