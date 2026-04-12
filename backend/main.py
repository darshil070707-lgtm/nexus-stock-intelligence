"""
NEXUS FastAPI Application
REST API · WebSocket streams · Background scheduler
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn
import pandas as pd
import yfinance as yf

# Import components
try:
    from config import APP_NAME, APP_VERSION, DATABASE_URL, DEFAULT_PORTFOLIO, POLL_INTERVAL_SEC
    from database import init_db, SessionLocal, SignalRecord, PortfolioItem, get_db
    from signals.aggregator import SignalAggregator
    from data.fetcher_us import USDataFetcher
    from data.fetcher_india import IndiaDataFetcher
    from data.fetcher_mf import MutualFundFetcher
    from data.fetcher_global import GlobalDataFetcher
except ImportError:
    # Setup path
    import sys
    sys.path.insert(0, "/app/backend")
    from config import APP_NAME, APP_VERSION, DATABASE_URL, DEFAULT_PORTFOLIO, POLL_INTERVAL_SEC
    from database import init_db, SessionLocal, SignalRecord, PortfolioItem, get_db
    from signals.aggregator import SignalAggregator
    from data.fetcher_us import USDataFetcher
    from data.fetcher_india import IndiaDataFetcher
    from data.fetcher_mf import MutualFundFetcher
    from data.fetcher_global import GlobalDataFetcher

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ── FastAPI App ────────────────────────────────────────────────────────────
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Advanced stock intelligence platform with ML ensemble signals",
)

# ── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Cloudflare Pages will handle origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Initialize components ──────────────────────────────────────────────────
init_db()
aggregator = SignalAggregator()
us_fetcher = USDataFetcher()
india_fetcher = IndiaDataFetcher()
mf_fetcher = MutualFundFetcher()
global_fetcher = GlobalDataFetcher()

# WebSocket manager
connected_clients = {}


# ── REST API Endpoints ─────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """On app startup: train ML models, warm cache."""
    logger.info(f"NEXUS {APP_VERSION} starting...")
    try:
        # Warm up models by analyzing default portfolio
        for ticker in DEFAULT_PORTFOLIO["stocks"][:3]:
            try:
                df = yf.Ticker(ticker).history(period="1y")
                if df is not None and len(df) > 50:
                    aggregator.ml.train(df)
                    logger.info(f"Trained ML model on {ticker}")
                    break
            except Exception as e:
                logger.debug(f"ML warmup error: {e}")
    except Exception as e:
        logger.warning(f"Startup warmup error: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": APP_NAME,
        "version": APP_VERSION,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/analyze/{ticker}")
async def analyze_ticker(ticker: str, db=Depends(get_db)):
    """
    Comprehensive 10-layer analysis for a ticker.
    Returns: composite score, all layer scores, risk assessment, backtest, etc.
    """
    try:
        # Fetch data
        is_india = ticker.endswith((".NS", ".BO"))
        fetcher = india_fetcher if is_india else us_fetcher
        df = fetcher.get_historical(ticker, period="2y")

        if df is None or len(df) < 20:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {ticker}")

        # Get company name
        info = fetcher.get_info(ticker)
        company_name = info.get("name", "")

        # Run aggregated analysis
        result = aggregator.analyze(ticker, df, company_name)

        # Save to database
        if result.get("composite", {}).get("score") is not None:
            signal = SignalRecord(
                ticker=ticker,
                timestamp=datetime.utcnow(),
                action=result["composite"]["action"],
                score=result["composite"]["score"],
                confidence=result["composite"]["confidence"],
                price=result.get("price"),
                hold_period=result["composite"].get("hold_period"),
                stop_loss=result.get("stop_loss"),
                reasons=result["composite"].get("top_reasons", []),
                layer_scores=result.get("layer_scores", {}),
            )
            db.add(signal)
            db.commit()
            logger.info(f"Saved signal for {ticker}: {result['composite']['action']}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analysis error [{ticker}]: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/portfolio")
async def manage_portfolio(portfolio: Dict[str, List[str]]):
    """
    Add/remove portfolio holdings.
    Expects: {"add": ["AAPL", "RELIANCE.NS"], "remove": ["TSLA"]}
    """
    try:
        db = SessionLocal()

        # Add new items
        for ticker in portfolio.get("add", []):
            existing = db.query(PortfolioItem).filter_by(ticker=ticker).first()
            if not existing:
                item = PortfolioItem(ticker=ticker, market="India" if ticker.endswith(".NS") else "US")
                db.add(item)

        # Remove items
        for ticker in portfolio.get("remove", []):
            db.query(PortfolioItem).filter_by(ticker=ticker).delete()

        db.commit()
        db.close()

        return {"status": "updated", "portfolio": portfolio}

    except Exception as e:
        logger.error(f"Portfolio error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/portfolio")
async def get_portfolio(db=Depends(get_db)):
    """Get current portfolio with latest signals."""
    try:
        items = db.query(PortfolioItem).all()
        portfolio = []

        for item in items:
            latest_signal = (
                db.query(SignalRecord)
                .filter_by(ticker=item.ticker)
                .order_by(SignalRecord.timestamp.desc())
                .first()
            )

            portfolio.append({
                "ticker": item.ticker,
                "added_at": item.added_at.isoformat(),
                "market": item.market,
                "latest_signal": {
                    "action": latest_signal.action if latest_signal else "N/A",
                    "score": latest_signal.score if latest_signal else 0,
                    "confidence": latest_signal.confidence if latest_signal else "N/A",
                    "timestamp": latest_signal.timestamp.isoformat() if latest_signal else None,
                } if latest_signal else None,
            })

        return {"portfolio": portfolio, "count": len(portfolio)}

    except Exception as e:
        logger.error(f"Portfolio fetch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/indices")
async def get_indices():
    """Get major indices (S&P, NIFTY, Sensex, etc.)."""
    try:
        indices = {
            "SPY": "S&P 500",
            "^NSEI": "NIFTY 50",
            "^BSESN": "SENSEX",
            "^VIX": "VIX Fear Index",
            "BTC-USD": "Bitcoin",
        }

        result = {}
        for ticker, name in indices.items():
            try:
                info = yf.Ticker(ticker).fast_info
                result[name] = {
                    "price": round(info.last_price, 2),
                    "change": round(info.last_price - (info.previous_close or info.last_price), 4),
                    "change_pct": round(
                        ((info.last_price - (info.previous_close or info.last_price)) /
                         (info.previous_close or info.last_price)) * 100, 2
                    ) if info.previous_close else 0,
                }
            except Exception:
                pass

        return result

    except Exception as e:
        logger.error(f"Indices error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mf/{code}")
async def get_mutual_fund(code: str):
    """Get mutual fund performance."""
    try:
        perf = mf_fetcher.get_scheme_performance(code)
        if not perf:
            raise HTTPException(status_code=404, detail=f"MF {code} not found")
        return perf
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/mf/search/{q}")
async def search_mutual_funds(q: str):
    """Search mutual funds."""
    try:
        results = mf_fetcher.search_mf(q)
        return {"query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/backtest/{ticker}")
async def backtest_ticker(ticker: str):
    """Run 1-year backtest on ticker."""
    try:
        df = yf.Ticker(ticker).history(period="2y")
        if df is None or len(df) < 252:
            raise HTTPException(status_code=400, detail="Need 1+ year of data")

        # Simple backtest using technical signals
        def signal_fn(window):
            result = aggregator.tech.analyze(window)
            return {"action": result["action"], "score": result["signal_score"]}

        backtest = aggregator.backtester.run(df, signal_fn)
        return backtest

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/macro")
async def get_macro_data():
    """Get global macro data and regime."""
    try:
        macro = global_fetcher.get_all_macro()
        regime = global_fetcher.get_macro_regime()
        sectors = global_fetcher.get_sector_performance()
        fear_greed = global_fetcher.get_fear_greed_proxy()

        return {
            "macro": macro,
            "regime": regime,
            "sectors": sectors,
            "fear_greed": fear_greed,
        }

    except Exception as e:
        logger.error(f"Macro error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/fear-greed")
async def get_fear_greed():
    """Get Fear & Greed gauge."""
    try:
        fg = global_fetcher.get_fear_greed_proxy()
        return fg
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sectors")
async def get_sector_performance():
    """Get sector rotation."""
    try:
        sectors = global_fetcher.get_sector_performance()
        return {"sectors": sectors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket Endpoints ────────────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_live_prices(websocket: WebSocket):
    """
    Real-time price & signal stream.
    Client sends: {"action": "subscribe", "tickers": ["AAPL", "RELIANCE.NS"]}
    Server sends: {price, signal_score, action} every 30s
    """
    await websocket.accept()
    client_id = id(websocket)
    tickers = []

    try:
        while True:
            # Receive message (non-blocking)
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=60)
                action = data.get("action")

                if action == "subscribe":
                    tickers = data.get("tickers", [])
                    await websocket.send_json({"status": "subscribed", "tickers": tickers})

                elif action == "unsubscribe":
                    tickers = []
                    await websocket.send_json({"status": "unsubscribed"})

            except asyncio.TimeoutError:
                pass  # Just continue
            except Exception:
                break

            # Send updates
            if tickers:
                updates = {}
                for ticker in tickers:
                    try:
                        # Quick price update + latest signal
                        info = yf.Ticker(ticker).fast_info
                        db = SessionLocal()
                        signal = (
                            db.query(SignalRecord)
                            .filter_by(ticker=ticker)
                            .order_by(SignalRecord.timestamp.desc())
                            .first()
                        )
                        db.close()

                        updates[ticker] = {
                            "price": round(info.last_price, 2),
                            "change_pct": round(
                                ((info.last_price - (info.previous_close or info.last_price)) /
                                 (info.previous_close or info.last_price)) * 100, 2
                            ) if info.previous_close else 0,
                            "signal": {
                                "action": signal.action if signal else "N/A",
                                "score": signal.score if signal else 0,
                            } if signal else None,
                        }
                    except Exception as e:
                        logger.debug(f"WS update error [{ticker}]: {e}")

                await websocket.send_json({"type": "update", "data": updates})

            await asyncio.sleep(30)

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if client_id in connected_clients:
            del connected_clients[client_id]


@app.websocket("/ws/portfolio")
async def websocket_portfolio(websocket: WebSocket):
    """Portfolio real-time updates."""
    await websocket.accept()

    try:
        while True:
            db = SessionLocal()
            items = db.query(PortfolioItem).all()
            db.close()

            portfolio_data = []
            for item in items:
                try:
                    info = yf.Ticker(item.ticker).fast_info
                    portfolio_data.append({
                        "ticker": item.ticker,
                        "price": round(info.last_price, 2),
                    })
                except Exception:
                    pass

            await websocket.send_json({"portfolio": portfolio_data})
            await asyncio.sleep(30)

    except Exception as e:
        logger.error(f"Portfolio WS error: {e}")


# ── Run ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
        log_level="info",
    )
