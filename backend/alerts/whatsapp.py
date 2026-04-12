"""
WhatsApp Alerts via Twilio
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False


class WhatsAppAlerter:
    """Send WhatsApp alerts via Twilio."""

    def __init__(self):
        try:
            from config import TWILIO_SID, TWILIO_TOKEN, TWILIO_WA_FROM, WA_TO

            self.sid = TWILIO_SID
            self.token = TWILIO_TOKEN
            self.from_num = TWILIO_WA_FROM
            self.to_num = WA_TO

            if TWILIO_AVAILABLE and self.sid and self.token:
                self.client = Client(self.sid, self.token)
                self.enabled = True
            else:
                self.enabled = False
                logger.warning("WhatsApp alerts disabled (no Twilio credentials)")

        except Exception as e:
            logger.warning(f"WhatsApp init error: {e}")
            self.enabled = False

    def send_alert(self, ticker: str, action: str, score: float, reason: str) -> bool:
        """Send WhatsApp alert."""
        if not self.enabled:
            return False

        try:
            color = "🟢" if action == "BUY" else ("🔴" if action == "SELL" else "🟡")

            message = f"""{color} {ticker} {action}

Score: {score:.1f}/10
Reason: {reason}

NEXUS Stock Intelligence"""

            msg = self.client.messages.create(
                from_=f"whatsapp:{self.from_num}",
                to=f"whatsapp:{self.to_num}",
                body=message
            )

            logger.info(f"WhatsApp alert sent: {msg.sid}")
            return True

        except Exception as e:
            logger.error(f"WhatsApp error: {e}")
            return False

    def send_portfolio_summary(self, portfolio: Dict[str, Any]) -> bool:
        """Send portfolio summary."""
        if not self.enabled:
            return False

        try:
            buys = portfolio.get("buys", [])
            sells = portfolio.get("sells", [])
            holds = portfolio.get("holds", [])

            message = f"""📊 Portfolio Summary

🟢 BUY ({len(buys)}): {', '.join(buys)}
🔴 SELL ({len(sells)}): {', '.join(sells)}
🟡 HOLD ({len(holds)}): {', '.join(holds)}

Updated: {portfolio.get('timestamp', 'N/A')}"""

            msg = self.client.messages.create(
                from_=f"whatsapp:{self.from_num}",
                to=f"whatsapp:{self.to_num}",
                body=message
            )

            logger.info(f"Portfolio summary sent: {msg.sid}")
            return True

        except Exception as e:
            logger.error(f"Portfolio summary error: {e}")
            return False
