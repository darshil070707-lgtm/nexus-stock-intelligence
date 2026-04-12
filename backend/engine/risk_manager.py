"""
NEXUS Risk Manager
- Kelly Criterion: mathematically optimal position sizing
- Portfolio correlation: avoid over-concentration
- Stop-loss levels: dynamic ATR-based
- Risk/Reward calculator
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class RiskManager:

    def kelly_position_size(
        self,
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        capital: float,
        price: float,
        max_kelly_fraction: float = 0.25,   # never bet more than 25% on one trade
    ) -> dict:
        """
        Full Kelly: f* = (p*b - q) / b
        where p=win_rate, q=1-p, b=avg_win/avg_loss
        Half-Kelly recommended for safety.
        """
        try:
            p = win_rate
            q = 1 - p
            b = abs(avg_win_pct) / (abs(avg_loss_pct) + 1e-9)

            kelly_full = (p * b - q) / (b + 1e-9)
            kelly_half = kelly_full / 2     # half-Kelly for safety

            # Cap at max fraction
            kelly_capped = max(0, min(max_kelly_fraction, kelly_half))

            allocation_usd = capital * kelly_capped
            shares         = int(allocation_usd // price) if price > 0 else 0

            return {
                "kelly_full":      round(kelly_full * 100, 2),
                "kelly_half":      round(kelly_half * 100, 2),
                "kelly_capped":    round(kelly_capped * 100, 2),
                "allocation_pct":  round(kelly_capped * 100, 1),
                "allocation_usd":  round(allocation_usd, 2),
                "shares":          shares,
                "description":     f"Risk {kelly_capped*100:.1f}% of capital ({allocation_usd:,.0f})",
            }
        except Exception as e:
            logger.error(f"Kelly error: {e}")
            return {"kelly_capped": 5.0, "allocation_pct": 5.0, "shares": 0}

    def dynamic_stop_loss(
        self,
        df: pd.DataFrame,
        entry_price: float,
        action: str = "BUY",
        atr_multiplier: float = 2.0,
    ) -> dict:
        """ATR-based dynamic stop loss — adapts to volatility."""
        try:
            c = df["Close"]; h = df["High"]; l = df["Low"]
            tr  = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])

            if action == "BUY":
                stop        = entry_price - (atr * atr_multiplier)
                target_1r   = entry_price + (atr * atr_multiplier)       # 1:1 R/R
                target_2r   = entry_price + (atr * atr_multiplier * 2)   # 1:2 R/R
                target_3r   = entry_price + (atr * atr_multiplier * 3)   # 1:3 R/R
            else:
                stop        = entry_price + (atr * atr_multiplier)
                target_1r   = entry_price - (atr * atr_multiplier)
                target_2r   = entry_price - (atr * atr_multiplier * 2)
                target_3r   = entry_price - (atr * atr_multiplier * 3)

            stop_pct  = abs(entry_price - stop) / entry_price * 100
            rr_ratio  = atr_multiplier

            return {
                "stop_loss":      round(stop, 2),
                "stop_loss_pct":  round(stop_pct, 2),
                "target_1r":      round(target_1r, 2),
                "target_2r":      round(target_2r, 2),
                "target_3r":      round(target_3r, 2),
                "atr":            round(atr, 2),
                "atr_pct":        round(atr / entry_price * 100, 2),
                "rr_ratio":       rr_ratio,
                "description":    f"Stop: {stop:.2f} ({stop_pct:.1f}% risk) | T1: {target_1r:.2f} | T2: {target_2r:.2f}",
            }
        except Exception as e:
            logger.error(f"Stop loss error: {e}")
            stop_pct = 5.0
            return {
                "stop_loss":      round(entry_price * (0.95 if action == "BUY" else 1.05), 2),
                "stop_loss_pct":  stop_pct,
            }

    def portfolio_correlation(self, price_dict: dict) -> dict:
        """
        Compute correlation matrix for portfolio holdings.
        High correlation = concentrated risk = dangerous.
        """
        try:
            returns = {}
            for ticker, prices in price_dict.items():
                if len(prices) > 30:
                    ret = pd.Series(prices).pct_change().dropna()
                    returns[ticker] = ret

            if len(returns) < 2:
                return {"matrix": {}, "warning": "Need ≥2 tickers for correlation"}

            df     = pd.DataFrame(returns).dropna()
            corr   = df.corr().round(3)
            matrix = corr.to_dict()

            # Find highly correlated pairs (> 0.8)
            warnings = []
            tickers  = list(returns.keys())
            for i in range(len(tickers)):
                for j in range(i+1, len(tickers)):
                    c = corr.loc[tickers[i], tickers[j]]
                    if c > 0.8:
                        warnings.append(f"{tickers[i]} ↔ {tickers[j]}: {c:.2f} (very high — consider reducing)")
                    elif c > 0.6:
                        warnings.append(f"{tickers[i]} ↔ {tickers[j]}: {c:.2f} (moderate concentration)")

            return {
                "matrix":   matrix,
                "warnings": warnings,
                "note":     "Pairs with correlation > 0.8 are essentially the same bet",
            }
        except Exception as e:
            logger.error(f"Correlation error: {e}")
            return {"matrix": {}, "error": str(e)}

    def assess_full_risk(
        self,
        ticker: str,
        df: pd.DataFrame,
        composite_score: float,
        fundamentals: dict,
        backtest: dict = None,
    ) -> dict:
        """Full risk assessment combining all factors."""
        factors = []
        risk_score = 0   # 0 = low, higher = more risky

        # Volatility
        if df is not None and len(df) > 20:
            returns = df["Close"].pct_change().dropna()
            ann_vol = float(returns.std() * np.sqrt(252) * 100)
            if   ann_vol > 60: risk_score += 3; factors.append(f"Annualised vol {ann_vol:.0f}% — very high")
            elif ann_vol > 35: risk_score += 2; factors.append(f"Annualised vol {ann_vol:.0f}% — elevated")
            elif ann_vol > 20: risk_score += 1
        else:
            ann_vol = 30

        # Leverage
        de = (fundamentals or {}).get("debt_to_equity", 0) or 0
        if   de > 3: risk_score += 3; factors.append(f"High D/E ratio {de:.1f} — leveraged")
        elif de > 2: risk_score += 2; factors.append(f"Elevated D/E {de:.1f}")
        elif de > 1: risk_score += 1

        # Signal conviction
        if abs(composite_score) < 2.5: risk_score += 1; factors.append("Low-conviction signal")
        if abs(composite_score) >= 7:  risk_score -= 1  # high conviction = lower risk

        # Backtest quality
        if backtest and "win_rate" in backtest:
            wr = backtest["win_rate"]
            if wr < 40: risk_score += 2; factors.append(f"Signal win rate only {wr:.0f}% historically")
            elif wr > 60: risk_score -= 1

        risk_level = "LOW" if risk_score <= 1 else ("MEDIUM" if risk_score <= 3 else "HIGH")
        stop_pcts  = {"LOW": 4, "MEDIUM": 7, "HIGH": 12}

        return {
            "level":          risk_level,
            "score":          risk_score,
            "factors":        factors,
            "stop_loss_pct":  stop_pcts[risk_level],
            "ann_volatility": round(ann_vol, 1),
            "max_position":   "20%" if risk_level == "LOW" else ("12%" if risk_level == "MEDIUM" else "5%"),
        }
