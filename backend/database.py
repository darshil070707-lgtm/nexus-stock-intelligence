"""
NEXUS Database — SQLAlchemy models
Stores: signals · portfolio · alerts · backtest_results
"""
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text, Boolean, JSON
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os
from config import DATABASE_URL

# Fix Render's postgres:// → postgresql://
_url = DATABASE_URL.replace("postgres://", "postgresql://", 1)
engine = create_engine(_url, pool_pre_ping=True, connect_args={} if "postgresql" in _url else {"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class SignalRecord(Base):
    __tablename__ = "signals"
    id          = Column(Integer, primary_key=True, index=True)
    ticker      = Column(String(20), index=True)
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)
    action      = Column(String(10))   # BUY / SELL / HOLD
    score       = Column(Float)
    confidence  = Column(String(10))
    price       = Column(Float)
    hold_period = Column(String(100))
    stop_loss   = Column(Float)
    reasons     = Column(JSON)
    layer_scores= Column(JSON)         # per-layer breakdown


class PortfolioItem(Base):
    __tablename__ = "portfolio"
    id          = Column(Integer, primary_key=True, index=True)
    ticker      = Column(String(20), unique=True, index=True)
    added_at    = Column(DateTime, default=datetime.utcnow)
    buy_price   = Column(Float, nullable=True)
    quantity    = Column(Float, nullable=True)
    asset_type  = Column(String(20), default="stock")  # stock / mf / crypto
    market      = Column(String(10), default="US")      # US / India


class BacktestResult(Base):
    __tablename__ = "backtests"
    id              = Column(Integer, primary_key=True, index=True)
    ticker          = Column(String(20), index=True)
    run_at          = Column(DateTime, default=datetime.utcnow)
    period          = Column(String(20))
    total_trades    = Column(Integer)
    win_rate        = Column(Float)
    total_return    = Column(Float)
    sharpe_ratio    = Column(Float)
    max_drawdown    = Column(Float)
    avg_hold_days   = Column(Float)
    details         = Column(JSON)


class AlertLog(Base):
    __tablename__ = "alerts"
    id          = Column(Integer, primary_key=True, index=True)
    ticker      = Column(String(20))
    action      = Column(String(10))
    score       = Column(Float)
    sent_at     = Column(DateTime, default=datetime.utcnow)
    channel     = Column(String(20))  # telegram / whatsapp
    delivered   = Column(Boolean, default=False)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
