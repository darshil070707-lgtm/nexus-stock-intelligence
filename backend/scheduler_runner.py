"""
Background Scheduler for NEXUS
Polls portfolio every 60s during market hours
Alerts on signal changes
Daily summaries at 9 AM
"""
import logging
import schedule
import time
from datetime import datetime, timedelta
import sys

sys.path.insert(0, "/app/backend")

from config import DEFAULT_PORTFOLIO, POLL_INTERVAL_SEC
from database import SessionLocal, PortfolioItem, SignalRecord
from signals.aggregator import SignalAggregator
from alerts.telegram_bot import TelegramBot
from alerts.whatsapp import WhatsAppAlerter

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

aggregator = SignalAggregator()
telegram = TelegramBot()
whatsapp = WhatsAppAlerter()


def is_market_hours() -> bool:
    """Check if market is open."""
    now = datetime.now()
    weekday = now.weekday()

    # Skip weekends
    if weekday >= 5:
        return False

    hour = now.hour
    minute = now.minute

    # US: 9:30-16:00 ET (simplified: 14:00-21:00 UTC)
    # India: 9:15-15:30 IST (simplified: 3:45-10:00 UTC)
    # Allow both markets
    return (3 <= hour <= 21)


def poll_portfolio():
    """Poll portfolio every 60s during market hours."""
    if not is_market_hours():
        return

    try:
        db = SessionLocal()
        items = db.query(PortfolioItem).all()

        if not items:
            db.close()
            return

        logger.info(f"Polling {len(items)} holdings...")

        for item in items[:10]:  # Limit to 10 per cycle to avoid rate limits
            try:
                # Get latest signal
                result = aggregator.analyze(item.ticker)

                if "error" in result:
                    logger.warning(f"Skipping {item.ticker}: {result['error']}")
                    continue

                composite = result.get("composite", {})
                new_action = composite.get("action")
                new_score = composite.get("score")

                # Check previous signal
                prev_signal = (
                    db.query(SignalRecord)
                    .filter_by(ticker=item.ticker)
                    .order_by(SignalRecord.timestamp.desc())
                    .first()
                )

                # Alert if signal changed
                if prev_signal:
                    if (prev_signal.action != new_action and
                        composite.get("confidence") in ["HIGH", "VERY_HIGH"]):

                        reason = composite.get("top_reasons", [""])[0]
                        logger.info(f"Signal change: {item.ticker} {prev_signal.action} → {new_action}")

                        # Send alerts
                        try:
                            telegram.app.run_async(
                                telegram.send_alert(item.ticker, new_action, new_score, reason)
                            )
                        except Exception as e:
                            logger.debug(f"Telegram alert error: {e}")

                        whatsapp.send_alert(item.ticker, new_action, new_score, reason)

            except Exception as e:
                logger.error(f"Poll error [{item.ticker}]: {e}")

        db.close()
        logger.info("Portfolio poll completed")

    except Exception as e:
        logger.error(f"Poll cycle error: {e}")


def daily_summary():
    """Send daily portfolio summary at 9 AM."""
    try:
        logger.info("Generating daily summary...")

        db = SessionLocal()
        items = db.query(PortfolioItem).all()

        buys = []
        sells = []
        holds = []

        for item in items:
            signal = (
                db.query(SignalRecord)
                .filter_by(ticker=item.ticker)
                .order_by(SignalRecord.timestamp.desc())
                .first()
            )

            if signal:
                if signal.action == "BUY":
                    buys.append(item.ticker)
                elif signal.action == "SELL":
                    sells.append(item.ticker)
                else:
                    holds.append(item.ticker)

        db.close()

        portfolio_summary = {
            "buys": buys,
            "sells": sells,
            "holds": holds,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

        logger.info(f"Daily summary: {portfolio_summary}")

        # Send via WhatsApp
        whatsapp.send_portfolio_summary(portfolio_summary)

    except Exception as e:
        logger.error(f"Daily summary error: {e}")


def weekly_backtest():
    """Run weekly backtest on key holdings (Sundays 10 AM)."""
    try:
        logger.info("Running weekly backtest...")

        db = SessionLocal()
        items = db.query(PortfolioItem).limit(5).all()
        db.close()

        for item in items:
            try:
                import yfinance as yf
                df = yf.Ticker(item.ticker).history(period="2y")

                if len(df) >= 252:
                    def signal_fn(window):
                        result = aggregator.tech.analyze(window)
                        return {"action": result["action"], "score": result["signal_score"]}

                    backtest = aggregator.backtester.run(df, signal_fn)

                    logger.info(f"{item.ticker} backtest: "
                              f"{backtest.get('win_rate', 0):.0f}% win rate, "
                              f"{backtest.get('sharpe_ratio', 0):.2f} Sharpe")

            except Exception as e:
                logger.debug(f"Backtest error [{item.ticker}]: {e}")

    except Exception as e:
        logger.error(f"Weekly backtest error: {e}")


def retrain_ml():
    """Retrain ML models every 24 hours."""
    try:
        logger.info("Retraining ML models...")

        db = SessionLocal()
        items = db.query(PortfolioItem).limit(3).all()
        db.close()

        for item in items:
            try:
                import yfinance as yf
                df = yf.Ticker(item.ticker).history(period="2y")

                if len(df) >= 100:
                    result = aggregator.ml.train(df)
                    if result.get("trained"):
                        logger.info(f"ML trained on {item.ticker}")

            except Exception as e:
                logger.debug(f"ML train error [{item.ticker}]: {e}")

    except Exception as e:
        logger.error(f"ML retrain error: {e}")


def main():
    """Run scheduler."""
    logger.info("NEXUS Scheduler started")

    # Schedule jobs
    schedule.every(POLL_INTERVAL_SEC).seconds.do(poll_portfolio)
    schedule.every().day.at("09:00").do(daily_summary)
    schedule.every().sunday.at("10:00").do(weekly_backtest)
    schedule.every(24).hours.do(retrain_ml)

    # Run scheduler loop
    while True:
        try:
            schedule.run_pending()
            time.sleep(10)
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
