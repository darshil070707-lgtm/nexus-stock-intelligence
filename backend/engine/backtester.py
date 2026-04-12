"""
NEXUS Backtester
Tests how well the signal engine would have performed historically.
Outputs: Win rate · Sharpe · Max drawdown · Avg hold · Return vs Buy-and-Hold
"""
import pandas as pd
import numpy as np
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class Backtester:

    def run(self, df: pd.DataFrame, signals_fn, initial_capital: float = 100_000) -> Dict[str, Any]:
        """
        Run backtest using a signal-generating function.
        signals_fn: callable(df_slice) -> {"action": "BUY"/"SELL"/"HOLD", "score": float}
        """
        if df is None or len(df) < 60:
            return {"error": "Need ≥60 candles for backtest"}

        df = df.copy().reset_index()
        trades      = []
        position    = 0        # shares held
        cash        = initial_capital
        entry_price = None
        entry_date  = None
        portfolio_values = []

        # Generate signals on rolling windows (min 50 bars of history)
        for i in range(50, len(df)):
            window = df.iloc[:i]
            price  = float(df["Close"].iloc[i])
            date   = df.index[i] if "Date" not in df.columns else df["Date"].iloc[i]

            try:
                sig = signals_fn(window)
                action = sig.get("action", "HOLD")
                score  = sig.get("score", 0)
            except Exception:
                action, score = "HOLD", 0

            # Entry
            if action == "BUY" and position == 0 and cash > 0:
                shares       = (cash * 0.95) // price    # 95% of cash, full position
                if shares > 0:
                    position    = shares
                    cash        -= shares * price
                    entry_price = price
                    entry_date  = date

            # Exit on SELL or score reversal
            elif (action == "SELL" or score < -3) and position > 0:
                proceeds    = position * price
                pnl         = proceeds - (position * entry_price)
                pnl_pct     = pnl / (position * entry_price) * 100
                hold_days   = (pd.Timestamp(date) - pd.Timestamp(entry_date)).days if entry_date else 0
                cash        += proceeds
                trades.append({
                    "entry_date":  str(entry_date),
                    "exit_date":   str(date),
                    "entry_price": round(entry_price, 2),
                    "exit_price":  round(price, 2),
                    "pnl_pct":     round(pnl_pct, 2),
                    "pnl_abs":     round(pnl, 2),
                    "hold_days":   hold_days,
                    "result":      "WIN" if pnl > 0 else "LOSS",
                })
                position    = 0
                entry_price = None
                entry_date  = None

            # Portfolio value
            portfolio_values.append(cash + position * price)

        # Close any open position at last price
        if position > 0:
            last_price  = float(df["Close"].iloc[-1])
            proceeds    = position * last_price
            pnl         = proceeds - (position * entry_price)
            pnl_pct     = pnl / (position * entry_price) * 100
            hold_days   = (pd.Timestamp(df.index[-1] if "Date" not in df.columns else df["Date"].iloc[-1])
                           - pd.Timestamp(entry_date)).days if entry_date else 0
            trades.append({
                "entry_date":  str(entry_date),
                "exit_date":   "OPEN",
                "entry_price": round(entry_price, 2),
                "exit_price":  round(last_price, 2),
                "pnl_pct":     round(pnl_pct, 2),
                "pnl_abs":     round(pnl, 2),
                "hold_days":   hold_days,
                "result":      "WIN" if pnl > 0 else "LOSS",
            })
            cash += proceeds

        # ── Metrics ───────────────────────────────────────────────────────────
        if not trades:
            return {"error": "No trades generated", "trades": [], "total_trades": 0}

        total_trades = len(trades)
        wins         = [t for t in trades if t["result"] == "WIN"]
        losses       = [t for t in trades if t["result"] == "LOSS"]
        win_rate     = len(wins) / total_trades

        pnls         = [t["pnl_pct"] for t in trades]
        avg_win      = np.mean([t["pnl_pct"] for t in wins])  if wins   else 0
        avg_loss     = np.mean([t["pnl_pct"] for t in losses]) if losses else 0
        profit_factor= abs(sum(t["pnl_pct"] for t in wins) / (sum(abs(t["pnl_pct"]) for t in losses) + 1e-9))

        # Portfolio performance
        final_capital   = cash
        total_return    = (final_capital - initial_capital) / initial_capital * 100
        bah_return      = (float(df["Close"].iloc[-1]) - float(df["Close"].iloc[50])) / float(df["Close"].iloc[50]) * 100

        # Sharpe ratio (annualised, assuming daily)
        if portfolio_values and len(portfolio_values) > 1:
            pv         = np.array(portfolio_values)
            pv_returns = np.diff(pv) / pv[:-1]
            sharpe     = np.mean(pv_returns) / (np.std(pv_returns) + 1e-9) * np.sqrt(252)
        else:
            sharpe = 0.0

        # Max drawdown
        if portfolio_values:
            pv   = np.array(portfolio_values)
            peak = np.maximum.accumulate(pv)
            dd   = (pv - peak) / peak
            max_dd = float(np.min(dd)) * 100
        else:
            max_dd = 0.0

        avg_hold = np.mean([t["hold_days"] for t in trades if t["hold_days"] > 0])
        expectancy = win_rate * avg_win + (1 - win_rate) * avg_loss

        return {
            "total_trades":    total_trades,
            "win_rate":        round(win_rate * 100, 1),
            "total_return":    round(total_return, 2),
            "bah_return":      round(bah_return, 2),
            "alpha":           round(total_return - bah_return, 2),
            "sharpe_ratio":    round(sharpe, 3),
            "max_drawdown":    round(max_dd, 2),
            "avg_hold_days":   round(avg_hold, 1),
            "avg_win_pct":     round(avg_win, 2),
            "avg_loss_pct":    round(avg_loss, 2),
            "profit_factor":   round(profit_factor, 2),
            "expectancy_pct":  round(expectancy, 2),
            "final_capital":   round(final_capital, 2),
            "initial_capital": initial_capital,
            "trades":          trades[-20:],    # last 20 trades
        }
