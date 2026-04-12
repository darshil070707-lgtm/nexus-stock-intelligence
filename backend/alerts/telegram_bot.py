"""
Telegram Bot for NEXUS
Commands: /analyze, /portfolio, /mf, /backtest, /macro, /feargreed, /help
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import sys

sys.path.insert(0, "/app/backend")
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from signals.aggregator import SignalAggregator

logger = logging.getLogger(__name__)
aggregator = SignalAggregator()


class TelegramBot:
    """NEXUS Telegram Bot."""

    def __init__(self):
        if not TELEGRAM_BOT_TOKEN:
            logger.warning("TELEGRAM_BOT_TOKEN not set")
            return

        self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Commands
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("analyze", self.analyze_command))
        self.app.add_handler(CommandHandler("portfolio", self.portfolio_command))
        self.app.add_handler(CommandHandler("macro", self.macro_command))
        self.app.add_handler(CommandHandler("feargreed", self.feargreed_command))

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Start command."""
        text = """
Welcome to <b>NEXUS</b> 🚀
Advanced AI-powered stock intelligence

Available commands:
/analyze &lt;TICKER&gt; - Full 10-layer analysis
/portfolio - Your current portfolio
/macro - Global macro conditions
/feargreed - Fear & Greed gauge
/help - Show this message
        """
        await update.message.reply_html(text)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Help command."""
        text = """
<b>NEXUS Commands</b>

<code>/analyze AAPL</code> - Analyze Apple stock
Runs: Technical · ML · Fundamental · Sentiment · Options · Insider · Macro · Patterns

<code>/portfolio</code> - Show your portfolio holdings with latest signals

<code>/macro</code> - Global market conditions
Risk-on/off regime, sector rotation, Fear & Greed

<code>/feargreed</code> - Current Fear & Greed index (0-100)

Made with ❤️ by NEXUS
        """
        await update.message.reply_html(text)

    async def analyze_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Analyze ticker command."""
        if not context.args or len(context.args) == 0:
            await update.message.reply_html("Usage: /analyze &lt;TICKER&gt;")
            return

        ticker = context.args[0].upper()
        await update.message.reply_text(f"Analyzing {ticker}... ⏳")

        try:
            result = aggregator.analyze(ticker)

            if "error" in result:
                await update.message.reply_html(f"❌ {result['error']}")
                return

            composite = result.get("composite", {})
            layers = result.get("layer_scores", {})

            # Format response
            score = composite.get("score", 0)
            action = composite.get("action", "HOLD")
            confidence = composite.get("confidence", "N/A")
            price = result.get("price", "N/A")

            color = "🟢" if action == "BUY" else ("🔴" if action == "SELL" else "🟡")

            text = f"""
<b>{ticker}</b> {color}

<b>Price:</b> ${price}
<b>Signal:</b> {action}
<b>Score:</b> {score}/10
<b>Confidence:</b> {confidence}

<b>Layer Scores:</b>
• Technical: {layers.get("technical", 0):.1f}
• ML: {layers.get("ml", 0):.1f}
• Fundamental: {layers.get("fundamental", 0):.1f}
• Sentiment: {layers.get("sentiment", 0):.1f}
• Macro: {layers.get("macro", 0):.1f}

<b>Top Reasons:</b>
            """

            for reason in composite.get("top_reasons", [])[:3]:
                text += f"\n• {reason}"

            risk = result.get("risk", {})
            if risk:
                text += f"\n\n<b>Risk Level:</b> {risk.get('level', 'N/A')}"

            await update.message.reply_html(text)

        except Exception as e:
            logger.error(f"Analyze error: {e}")
            await update.message.reply_html(f"❌ Error: {str(e)}")

    async def portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Portfolio command."""
        try:
            from database import SessionLocal, PortfolioItem, SignalRecord
            from datetime import datetime

            db = SessionLocal()
            items = db.query(PortfolioItem).all()

            if not items:
                await update.message.reply_html("Your portfolio is empty. Add stocks with /analyze!")
                return

            text = "<b>📊 Your Portfolio</b>\n\n"

            for item in items:
                latest_signal = (
                    db.query(SignalRecord)
                    .filter_by(ticker=item.ticker)
                    .order_by(SignalRecord.timestamp.desc())
                    .first()
                )

                if latest_signal:
                    action = latest_signal.action
                    score = latest_signal.score
                    color = "🟢" if action == "BUY" else ("🔴" if action == "SELL" else "🟡")
                    text += f"{color} <b>{item.ticker}</b> {action} ({score:.1f}/10)\n"
                else:
                    text += f"🟡 <b>{item.ticker}</b> No signal yet\n"

            db.close()
            await update.message.reply_html(text)

        except Exception as e:
            logger.error(f"Portfolio error: {e}")
            await update.message.reply_html(f"❌ Error loading portfolio")

    async def macro_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Macro conditions."""
        try:
            macro = aggregator.macro.fetcher.get_all_macro()
            regime = aggregator.macro.fetcher.get_macro_regime()

            vix = macro.get("^VIX", {}).get("price", 0)
            spy = macro.get("SPY", {}).get("change_pct", 0)

            text = f"""
<b>🌍 Global Macro</b>

<b>Regime:</b> {regime.get("label", "Unknown")}
<b>VIX:</b> {vix:.1f}
<b>S&P 500:</b> {spy:+.2f}%

<b>Top movers:</b>
• Gold: {macro.get('GC=F', {}).get('change_pct', 0):+.2f}%
• DXY: {macro.get('DX-Y.NYB', {}).get('change_pct', 0):+.2f}%
            """

            await update.message.reply_html(text)

        except Exception as e:
            logger.error(f"Macro error: {e}")
            await update.message.reply_html(f"❌ Error loading macro data")

    async def feargreed_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Fear & Greed gauge."""
        try:
            fg = aggregator.macro.fetcher.get_fear_greed_proxy()

            score = fg.get("score", 50)
            label = fg.get("label", "Neutral")

            # Emoji gauge
            if score >= 75:
                gauge = "😱😱😱😱😱 Extreme Greed"
            elif score >= 55:
                gauge = "😊😊😊😊 Greed"
            elif score >= 45:
                gauge = "😐😐😐 Neutral"
            elif score >= 25:
                gauge = "😨😨 Fear"
            else:
                gauge = "😱😱😱😱😱 Extreme Fear"

            text = f"""
<b>📊 Fear & Greed Index</b>

<b>Score:</b> {score:.0f}/100

{gauge}

<b>Interpretation:</b>
When extreme fear rules the market, wise investors start buying.
When extreme greed dominates, wise investors start selling.
            """

            await update.message.reply_html(text)

        except Exception as e:
            logger.error(f"Fear/Greed error: {e}")
            await update.message.reply_html(f"❌ Error")

    async def send_alert(self, ticker: str, action: str, score: float, reason: str):
        """Send alert to configured chat."""
        if not TELEGRAM_CHAT_ID:
            return

        try:
            color = "🟢" if action == "BUY" else ("🔴" if action == "SELL" else "🟡")

            text = f"""
{color} <b>{ticker}</b> {action}

<b>Score:</b> {score:.1f}/10
<b>Reason:</b> {reason}
            """

            await self.app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Alert error: {e}")

    def run(self):
        """Start bot."""
        if not TELEGRAM_BOT_TOKEN:
            logger.warning("Telegram bot disabled (no token)")
            return

        logger.info("Starting Telegram bot...")
        self.app.run_polling()


if __name__ == "__main__":
    bot = TelegramBot()
    bot.run()
