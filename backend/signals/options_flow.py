"""
Options Flow Analyzer — FREE via yfinance
Detects: unusual volume · put/call ratio · gamma exposure · big bet tracking
This is what hedge funds pay thousands for — here it's free.
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class OptionsFlowAnalyzer:

    def analyze(self, ticker: str) -> dict:
        try:
            stock = yf.Ticker(ticker)
            expirations = stock.options
            if not expirations:
                return {"error": "No options data", "signal_score": 0, "action": "HOLD"}

            # Get nearest 3 expirations
            exp_dates = expirations[:3]
            all_calls = []
            all_puts  = []

            for exp in exp_dates:
                try:
                    chain = stock.option_chain(exp)
                    calls = chain.calls.copy(); calls["expiry"] = exp; calls["type"] = "call"
                    puts  = chain.puts.copy();  puts["expiry"]  = exp; puts["type"]  = "put"
                    all_calls.append(calls)
                    all_puts.append(puts)
                except Exception:
                    pass

            if not all_calls:
                return {"error": "Options chain empty", "signal_score": 0, "action": "HOLD"}

            calls_df = pd.concat(all_calls, ignore_index=True)
            puts_df  = pd.concat(all_puts,  ignore_index=True)

            current_price = stock.fast_info.last_price

            # ── Key Metrics ───────────────────────────────────────────────────

            # 1. Put/Call Ratio (volume-based) — < 0.7 bullish, > 1.3 bearish
            total_call_vol = calls_df["volume"].fillna(0).sum()
            total_put_vol  = puts_df["volume"].fillna(0).sum()
            pcr_volume     = total_put_vol / (total_call_vol + 1e-9)

            # 2. Put/Call Ratio (OI-based) — sentiment indicator
            total_call_oi  = calls_df["openInterest"].fillna(0).sum()
            total_put_oi   = puts_df["openInterest"].fillna(0).sum()
            pcr_oi         = total_put_oi / (total_call_oi + 1e-9)

            # 3. Unusual Volume — options trading > 3x average OI
            calls_df["vol_oi_ratio"] = calls_df["volume"].fillna(0) / (calls_df["openInterest"].fillna(1) + 1)
            puts_df["vol_oi_ratio"]  = puts_df["volume"].fillna(0)  / (puts_df["openInterest"].fillna(1) + 1)

            unusual_calls = calls_df[calls_df["vol_oi_ratio"] > 3].nlargest(3, "volume")
            unusual_puts  = puts_df[puts_df["vol_oi_ratio"] > 3].nlargest(3, "volume")

            # 4. Gamma Exposure proxy — strikes with highest OI near ATM
            atm_calls = calls_df[
                (calls_df["strike"] >= current_price * 0.95) &
                (calls_df["strike"] <= current_price * 1.05)
            ]
            atm_puts = puts_df[
                (puts_df["strike"]  >= current_price * 0.95) &
                (puts_df["strike"]  <= current_price * 1.05)
            ]

            atm_call_oi  = atm_calls["openInterest"].fillna(0).sum()
            atm_put_oi   = atm_puts["openInterest"].fillna(0).sum()
            gamma_skew   = (atm_call_oi - atm_put_oi) / (atm_call_oi + atm_put_oi + 1e-9)

            # 5. IV Rank proxy — current avg IV vs recent range
            try:
                avg_iv_calls = calls_df["impliedVolatility"].dropna().mean()
                avg_iv_puts  = puts_df["impliedVolatility"].dropna().mean()
                avg_iv       = (avg_iv_calls + avg_iv_puts) / 2
            except Exception:
                avg_iv = 0.3

            # 6. Big sweeps — large single orders (volume > 1000, premium > $50k)
            calls_df["est_premium"] = calls_df["volume"].fillna(0) * calls_df["lastPrice"].fillna(0) * 100
            puts_df["est_premium"]  = puts_df["volume"].fillna(0)  * puts_df["lastPrice"].fillna(0)  * 100

            big_call_sweeps = calls_df[calls_df["est_premium"] > 50_000].nlargest(3, "est_premium")
            big_put_sweeps  = puts_df[puts_df["est_premium"]   > 50_000].nlargest(3, "est_premium")

            total_call_premium = calls_df["est_premium"].sum()
            total_put_premium  = puts_df["est_premium"].sum()
            premium_ratio      = total_call_premium / (total_put_premium + 1e-9)

            # ── Signal Scoring ────────────────────────────────────────────────
            score   = 0.0
            reasons = []

            # PCR Volume
            if   pcr_volume < 0.5:  score += 2.5; reasons.append(f"Bullish PCR {pcr_volume:.2f} — heavy call buying")
            elif pcr_volume < 0.7:  score += 1.5; reasons.append(f"Bullish PCR {pcr_volume:.2f}")
            elif pcr_volume > 1.5:  score -= 2.5; reasons.append(f"Bearish PCR {pcr_volume:.2f} — heavy put buying")
            elif pcr_volume > 1.0:  score -= 1.5; reasons.append(f"Elevated PCR {pcr_volume:.2f}")

            # Unusual call activity
            if len(unusual_calls) > 0:
                score += 2.0
                strikes = unusual_calls["strike"].tolist()
                reasons.append(f"Unusual call volume at strikes {strikes} — smart money buying")

            # Unusual put activity
            if len(unusual_puts) > 0:
                score -= 2.0
                strikes = unusual_puts["strike"].tolist()
                reasons.append(f"Unusual put volume at strikes {strikes} — hedging or shorting")

            # Gamma skew
            if   gamma_skew >  0.3: score += 1.5; reasons.append(f"ATM gamma skewed bullish ({gamma_skew:.2f})")
            elif gamma_skew < -0.3: score -= 1.5; reasons.append(f"ATM gamma skewed bearish ({gamma_skew:.2f})")

            # Big call sweeps
            if len(big_call_sweeps) > 0:
                total = big_call_sweeps["est_premium"].sum() / 1_000_000
                score += 2.0
                reasons.append(f"Big call sweeps ${total:.1f}M — institutional bullish bet")

            # Big put sweeps
            if len(big_put_sweeps) > 0:
                total = big_put_sweeps["est_premium"].sum() / 1_000_000
                score -= 2.0
                reasons.append(f"Big put sweeps ${total:.1f}M — institutional hedging/shorting")

            # Premium flow
            if   premium_ratio > 2.0: score += 1.0; reasons.append(f"Call premium 2x puts — smart money positioning long")
            elif premium_ratio < 0.5: score -= 1.0; reasons.append(f"Put premium dominates — defensive positioning")

            # High IV — avoid; low IV — buy options cheap
            if avg_iv > 0.6: reasons.append(f"High IV {avg_iv:.0%} — options expensive, risk elevated")
            elif avg_iv < 0.2: reasons.append(f"Low IV {avg_iv:.0%} — cheap options, calm market")

            score  = max(-10, min(10, score))
            action = "BUY" if score >= 2.5 else ("SELL" if score <= -2.5 else "HOLD")

            return {
                "signal_score":     round(score, 2),
                "action":           action,
                "pcr_volume":       round(pcr_volume, 3),
                "pcr_oi":           round(pcr_oi, 3),
                "gamma_skew":       round(gamma_skew, 3),
                "avg_iv":           round(avg_iv, 3),
                "total_call_vol":   int(total_call_vol),
                "total_put_vol":    int(total_put_vol),
                "call_premium_M":   round(total_call_premium / 1e6, 2),
                "put_premium_M":    round(total_put_premium  / 1e6, 2),
                "unusual_calls":    len(unusual_calls),
                "unusual_puts":     len(unusual_puts),
                "big_call_sweeps":  len(big_call_sweeps),
                "big_put_sweeps":   len(big_put_sweeps),
                "reasons":          reasons,
            }

        except Exception as e:
            logger.error(f"Options flow error [{ticker}]: {e}")
            return {"signal_score": 0, "action": "HOLD", "error": str(e)}
