"""
NEXUS — Global Stock Intelligence Platform
Configuration
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── App ───────────────────────────────────────────────────────────────────────
APP_NAME    = "NEXUS"
APP_VERSION = "2.0.0"
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR   = os.environ.get("MODEL_DIR", os.path.join(BASE_DIR, "models"))

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{BASE_DIR}/nexus.db")
# Render gives you DATABASE_URL automatically — no change needed

# ── Free API Keys ─────────────────────────────────────────────────────────────
ALPHA_VANTAGE_KEY  = os.environ.get("ALPHA_VANTAGE_KEY", "demo")
NEWS_API_KEY       = os.environ.get("NEWS_API_KEY", "")
FMP_API_KEY        = os.environ.get("FMP_API_KEY", "")        # financialmodelingprep.com free
FRED_API_KEY       = os.environ.get("FRED_API_KEY", "")       # fred.stlouisfed.org free

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── WhatsApp (Twilio) ─────────────────────────────────────────────────────────
TWILIO_SID         = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN       = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WA_FROM     = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
WA_TO              = os.environ.get("WHATSAPP_TO", "")

# ── Cloudflare ────────────────────────────────────────────────────────────────
CF_ACCOUNT_ID      = os.environ.get("CF_ACCOUNT_ID", "")
CF_KV_NAMESPACE_ID = os.environ.get("CF_KV_NAMESPACE_ID", "")
CF_API_TOKEN       = os.environ.get("CF_API_TOKEN", "")

# ── Scheduler ─────────────────────────────────────────────────────────────────
POLL_INTERVAL_SEC  = int(os.environ.get("POLL_INTERVAL_SEC", "60"))
ML_RETRAIN_HOURS   = int(os.environ.get("ML_RETRAIN_HOURS", "24"))
MAX_WORKERS        = int(os.environ.get("MAX_WORKERS", "4"))

# ── Signal weights (must sum to 1.0) ─────────────────────────────────────────
SIGNAL_WEIGHTS = {
    "technical":    0.22,
    "ml":           0.20,
    "fundamental":  0.15,
    "sentiment":    0.08,
    "options_flow": 0.10,
    "insider":      0.08,
    "macro":        0.07,
    "patterns":     0.05,
    "social":       0.03,
    "regime_adj":   0.02,   # regime multiplier
}

# ── Default Portfolio ─────────────────────────────────────────────────────────
DEFAULT_PORTFOLIO = {
    "stocks": [
        # India (NSE)
        "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
        # US
        "AAPL", "MSFT", "NVDA", "TSLA", "GOOGL",
    ],
    "mutual_funds": ["120503", "119551", "118989"],
    "watchlist":    ["ZOMATO.NS", "PAYTM.NS", "NAUKRI.NS", "META", "AMZN"],
}

# ── Sector benchmark P/E ──────────────────────────────────────────────────────
SECTOR_PE = {
    "Technology": 28, "Financial Services": 15, "Healthcare": 22,
    "Consumer Cyclical": 20, "Energy": 12, "Utilities": 16,
    "Consumer Defensive": 20, "Communication Services": 22,
    "Industrials": 20, "Basic Materials": 14, "Real Estate": 32,
    "default": 20,
}
