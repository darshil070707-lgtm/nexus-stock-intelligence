import os, json, asyncio, logging
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf
import pandas as pd
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncpg

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("nexus")

app = FastAPI(title="NEXUS Stock Intelligence", version="3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATABASE_URL = os.getenv("DATABASE_URL", "")
scheduler = AsyncIOScheduler(timezone="UTC")
db_pool: Optional[asyncpg.Pool] = None

# ── Stock Universe ─────────────────────────────────────────────────────────────
US_STOCKS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AMD",
    "NFLX", "JPM", "BAC", "GS", "V", "MA", "UNH", "XOM", "CVX",
    "LLY", "JNJ", "PG", "KO", "WMT", "HD", "DIS", "INTC",
    "CRM", "ORCL", "ADBE", "PYPL", "QCOM"
]
INDIA_STOCKS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "BHARTIARTL.NS", "SBIN.NS", "WIPRO.NS", "LT.NS", "AXISBANK.NS",
    "ADANIENT.NS", "TATAMOTORS.NS", "MARUTI.NS", "SUNPHARMA.NS", "HINDUNILVR.NS",
    "BAJFINANCE.NS", "KOTAKBANK.NS", "ASIANPAINT.NS", "TITAN.NS", "NESTLEIND.NS"
]
ALL_TICKERS = US_STOCKS + INDIA_STOCKS

# ── DB Setup ───────────────────────────────────────────────────────────────────
async def init_db():
    global db_pool
    if not DATABASE_URL:
        log.warning("No DATABASE_URL — running in memory mode")
        return
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id SERIAL PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    market TEXT NOT NULL,
                    price FLOAT,
                    change_pct FLOAT,
                    rsi FLOAT,
                    ma20 FLOAT,
                    ma50 FLOAT,
                    volume_ratio FLOAT,
                    momentum_1w FLOAT,
                    momentum_1m FLOAT,
                    score FLOAT,
                    action TEXT,
                    confidence TEXT,
                    details JSONB,
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE UNIQUE INDEX IF NOT EXISTS signals_ticker_idx ON signals(ticker);
            """)
        log.info("DB initialized")
    except Exception as e:
        log.error(f"DB init failed: {e}")

# In-memory cache when DB not available
signal_cache: dict = {}
connected_clients: list[WebSocket] = []

# ── Signal Engine ──────────────────────────────────────────────────────────────
def compute_rsi(prices: pd.Series, period=14) -> float:
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not rsi.empty else 50.0

def analyze_ticker(ticker: str) -> Optional[dict]:
    try:
        market = "India" if ticker.endswith(".NS") else "US"
        tf = yf.Ticker(ticker)
        hist = tf.history(period="3mo", interval="1d", auto_adjust=True)
        if hist.empty or len(hist) < 22:
            return None

        close = hist["Close"]
        volume = hist["Volume"]
        price = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        change_pct = ((price - prev_close) / prev_close) * 100

        rsi = compute_rsi(close)
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else ma20
        vol_avg = float(volume.rolling(20).mean().iloc[-1])
        vol_current = float(volume.iloc[-1])
        volume_ratio = vol_current / (vol_avg + 1e-10)

        # Momentum
        price_1w = float(close.iloc[-6]) if len(close) >= 6 else price
        price_1m = float(close.iloc[-22]) if len(close) >= 22 else price
        momentum_1w = ((price - price_1w) / price_1w) * 100
        momentum_1m = ((price - price_1m) / price_1m) * 100

        # ── Scoring (10 factors, each ±1) ─────────────────────────────────
        score = 0.0
        details = {}

        # 1. RSI
        if rsi < 30:
            score += 2; details["rsi"] = f"Oversold {rsi:.0f} (+2)"
        elif rsi < 45:
            score += 1; details["rsi"] = f"Bullish {rsi:.0f} (+1)"
        elif rsi > 70:
            score -= 2; details["rsi"] = f"Overbought {rsi:.0f} (-2)"
        elif rsi > 60:
            score -= 1; details["rsi"] = f"High {rsi:.0f} (-1)"
        else:
            details["rsi"] = f"Neutral {rsi:.0f} (0)"

        # 2. Price vs MA20
        if price > ma20 * 1.02:
            score += 1; details["ma20"] = "Above MA20 (+1)"
        elif price < ma20 * 0.98:
            score -= 1; details["ma20"] = "Below MA20 (-1)"
        else:
            details["ma20"] = "Near MA20 (0)"

        # 3. Price vs MA50
        if price > ma50 * 1.03:
            score += 1; details["ma50"] = "Above MA50 (+1)"
        elif price < ma50 * 0.97:
            score -= 1; details["ma50"] = "Below MA50 (-1)"
        else:
            details["ma50"] = "Near MA50 (0)"

        # 4. MA20 vs MA50 (Golden/Death cross)
        if ma20 > ma50 * 1.01:
            score += 1; details["cross"] = "Golden cross (+1)"
        elif ma20 < ma50 * 0.99:
            score -= 1; details["cross"] = "Death cross (-1)"
        else:
            details["cross"] = "No cross (0)"

        # 5. Momentum 1W
        if momentum_1w > 3:
            score += 1; details["mom_1w"] = f"+{momentum_1w:.1f}% week (+1)"
        elif momentum_1w < -3:
            score -= 1; details["mom_1w"] = f"{momentum_1w:.1f}% week (-1)"
        else:
            details["mom_1w"] = f"{momentum_1w:.1f}% week (0)"

        # 6. Momentum 1M
        if momentum_1m > 8:
            score += 1; details["mom_1m"] = f"+{momentum_1m:.1f}% month (+1)"
        elif momentum_1m < -8:
            score -= 1; details["mom_1m"] = f"{momentum_1m:.1f}% month (-1)"
        else:
            details["mom_1m"] = f"{momentum_1m:.1f}% month (0)"

        # 7. Volume surge
        if volume_ratio > 1.5:
            score += 1; details["volume"] = f"Volume surge {volume_ratio:.1f}x (+1)"
        elif volume_ratio < 0.5:
            score -= 0.5; details["volume"] = f"Low volume {volume_ratio:.1f}x (-0.5)"
        else:
            details["volume"] = f"Normal volume {volume_ratio:.1f}x (0)"

        # 8. Daily change
        if change_pct > 2:
            score += 0.5; details["daily"] = f"+{change_pct:.1f}% today (+0.5)"
        elif change_pct < -2:
            score -= 0.5; details["daily"] = f"{change_pct:.1f}% today (-0.5)"
        else:
            details["daily"] = f"{change_pct:.1f}% today (0)"

        # ── Action ────────────────────────────────────────────────────────
        if score >= 3:
            action = "BUY"
            confidence = "High" if score >= 5 else "Medium"
        elif score <= -2:
            action = "SELL"
            confidence = "High" if score <= -4 else "Medium"
        else:
            action = "HOLD"
            confidence = "Low"

        currency = "₹" if market == "India" else "$"
        return {
            "ticker": ticker,
            "market": market,
            "price": round(price, 2),
            "currency": currency,
            "change_pct": round(change_pct, 2),
            "rsi": round(rsi, 1),
            "ma20": round(ma20, 2),
            "ma50": round(ma50, 2),
            "volume_ratio": round(volume_ratio, 2),
            "momentum_1w": round(momentum_1w, 2),
            "momentum_1m": round(momentum_1m, 2),
            "score": round(score, 1),
            "action": action,
            "confidence": confidence,
            "details": details,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        log.warning(f"Failed to analyze {ticker}: {e}")
        return None

async def upsert_signal(sig: dict):
    signal_cache[sig["ticker"]] = sig
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO signals (ticker, market, price, change_pct, rsi, ma20, ma50,
                        volume_ratio, momentum_1w, momentum_1m, score, action, confidence, details, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                    ON CONFLICT (ticker) DO UPDATE SET
                        price=EXCLUDED.price, change_pct=EXCLUDED.change_pct,
                        rsi=EXCLUDED.rsi, ma20=EXCLUDED.ma20, ma50=EXCLUDED.ma50,
                        volume_ratio=EXCLUDED.volume_ratio, momentum_1w=EXCLUDED.momentum_1w,
                        momentum_1m=EXCLUDED.momentum_1m, score=EXCLUDED.score,
                        action=EXCLUDED.action, confidence=EXCLUDED.confidence,
                        details=EXCLUDED.details, updated_at=EXCLUDED.updated_at
                """,
                sig["ticker"], sig["market"], sig["price"], sig["change_pct"],
                sig["rsi"], sig["ma20"], sig["ma50"], sig["volume_ratio"],
                sig["momentum_1w"], sig["momentum_1m"], sig["score"],
                sig["action"], sig["confidence"], json.dumps(sig["details"]),
                datetime.now(timezone.utc))
        except Exception as e:
            log.error(f"DB upsert failed for {sig['ticker']}: {e}")

async def broadcast(data: dict):
    dead = []
    for ws in connected_clients:
        try:
            await ws.send_json(data)
        except:
            dead.append(ws)
    for ws in dead:
        connected_clients.remove(ws)

async def ingest_batch(tickers: list[str]):
    loop = asyncio.get_event_loop()
    for ticker in tickers:
        sig = await loop.run_in_executor(None, analyze_ticker, ticker)
        if sig:
            await upsert_signal(sig)
            await broadcast({"type": "signal_update", "data": sig})
            log.info(f"✓ {ticker} {sig['action']} score={sig['score']}")
        await asyncio.sleep(0.3)  # rate limit

async def run_ingestion():
    log.info(f"🔄 Ingestion started at {datetime.now(timezone.utc).isoformat()}")
    await ingest_batch(ALL_TICKERS)
    log.info("✅ Ingestion complete")

# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    await init_db()
    # Run immediately on startup
    asyncio.create_task(run_ingestion())
    # Then every 5 minutes during market hours (UTC)
    # US market: 13:30-20:00 UTC | India: 03:45-10:00 UTC
    scheduler.add_job(run_ingestion, CronTrigger(minute="*/5", hour="3-10,13-20"), id="ingest_market")
    # Off-hours: once per 30 min to stay fresh
    scheduler.add_job(run_ingestion, CronTrigger(minute="0,30", hour="0-3,10-13,20-23"), id="ingest_offhours")
    scheduler.start()
    log.info("🚀 NEXUS v3.0 started — scheduler running")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()
    if db_pool:
        await db_pool.close()

# ── REST Endpoints ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "3.0",
        "tickers_tracked": len(ALL_TICKERS),
        "cached_signals": len(signal_cache),
        "scheduler_running": scheduler.running,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/signals")
async def get_signals():
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM signals ORDER BY score DESC")
                return {"signals": [dict(r) for r in rows], "count": len(rows)}
        except Exception as e:
            log.error(f"DB fetch failed: {e}")
    return {"signals": list(signal_cache.values()), "count": len(signal_cache)}

@app.get("/signals/top")
async def top_signals(action: str = "BUY", limit: int = 10):
    sigs = list(signal_cache.values())
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM signals WHERE action=$1 ORDER BY score DESC LIMIT $2",
                    action.upper(), limit
                )
                sigs = [dict(r) for r in rows]
        except:
            pass
    filtered = [s for s in sigs if s.get("action") == action.upper()]
    filtered.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"signals": filtered[:limit], "action": action}

@app.get("/signals/{ticker}")
async def get_signal(ticker: str):
    t = ticker.upper()
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM signals WHERE ticker=$1", t)
                if row:
                    return dict(row)
        except:
            pass
    cached = signal_cache.get(t)
    if cached:
        return cached
    # Live fetch on demand
    loop = asyncio.get_event_loop()
    sig = await loop.run_in_executor(None, analyze_ticker, t)
    if sig:
        await upsert_signal(sig)
        return sig
    return {"error": f"Could not analyze {t}"}

@app.get("/portfolio")
async def get_portfolio():
    sigs = list(signal_cache.values())
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM signals ORDER BY score DESC")
                sigs = [dict(r) for r in rows]
        except:
            pass
    return {"portfolio": sigs, "count": len(sigs)}

@app.get("/indices")
async def get_indices():
    index_tickers = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Dow Jones": "^DJI",
                     "NIFTY 50": "^NSEI", "SENSEX": "^BSESN"}
    result = {}
    loop = asyncio.get_event_loop()

    async def fetch_index(name, sym):
        try:
            def _get():
                t = yf.Ticker(sym)
                h = t.history(period="2d", interval="1d")
                if len(h) >= 2:
                    p = float(h["Close"].iloc[-1])
                    prev = float(h["Close"].iloc[-2])
                    return {"price": round(p, 2), "change_pct": round(((p-prev)/prev)*100, 2)}
                return None
            r = await loop.run_in_executor(None, _get)
            if r:
                result[name] = r
        except:
            pass

    await asyncio.gather(*[fetch_index(n, s) for n, s in index_tickers.items()])
    return result

@app.get("/fear-greed")
async def fear_greed():
    # Compute from VIX
    try:
        loop = asyncio.get_event_loop()
        def _vix():
            v = yf.Ticker("^VIX")
            h = v.history(period="5d")
            return float(h["Close"].iloc[-1]) if not h.empty else 20.0
        vix = await loop.run_in_executor(None, _vix)
        # VIX 10=extreme greed(90), 20=neutral(50), 40=extreme fear(10)
        score = max(5, min(95, 100 - ((vix - 10) / 30 * 80)))
        label = "Extreme Greed" if score > 75 else "Greed" if score > 55 else \
                "Neutral" if score > 45 else "Fear" if score > 25 else "Extreme Fear"
        return {"score": round(score, 1), "label": label, "vix": round(vix, 2)}
    except:
        return {"score": 50, "label": "Neutral", "vix": 20}

@app.post("/refresh/{ticker}")
async def refresh_ticker(ticker: str):
    loop = asyncio.get_event_loop()
    sig = await loop.run_in_executor(None, analyze_ticker, ticker.upper())
    if sig:
        await upsert_signal(sig)
        await broadcast({"type": "signal_update", "data": sig})
        return sig
    return {"error": f"Failed to refresh {ticker}"}

# ── WebSocket ──────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.append(ws)
    log.info(f"WS client connected. Total: {len(connected_clients)}")
    # Send current snapshot
    await ws.send_json({"type": "snapshot", "data": list(signal_cache.values())})
    try:
        while True:
            await ws.receive_text()  # keep alive
    except WebSocketDisconnect:
        connected_clients.remove(ws)
        log.info(f"WS client disconnected. Total: {len(connected_clients)}")
