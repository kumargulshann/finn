from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.models import DailyPrice, Instrument, MarketSnapshot, utc_now
from app.integrations.stocks.yfinance_provider import YFinanceProvider


class MarketDataService:
    """Refreshes and caches daily market data without falling back to demo prices."""

    source = YFinanceProvider.source

    def __init__(self, provider: Any | None = None, cache_ttl_seconds: int = 900):
        self.provider = provider or YFinanceProvider()
        self.cache_ttl = timedelta(seconds=max(30, cache_ttl_seconds))
        self._lock_guard = Lock()
        self._instrument_locks: dict[int, Lock] = {}

    def refresh_many(self, session: Session, instruments: list[Instrument], period: str = "3mo") -> None:
        """Warm snapshots + daily bars for many instruments in one batched request when stale.

        Pulls ~3 months so EOD triggers have a 20-day volume baseline. Falls back to per-ticker
        history when the provider has no batch API. Failures leave existing cache untouched.
        """
        now = utc_now()
        stale = []
        for instrument in instruments:
            snapshot = session.get(MarketSnapshot, instrument.id)
            bars = session.scalar(select(func.count(DailyPrice.id)).where(DailyPrice.instrument_id == instrument.id)) or 0
            if not snapshot or snapshot.close is None or _aware(snapshot.fetched_at) + self.cache_ttl <= now or bars < 25:
                stale.append(instrument)
        if not stale:
            return
        symbols = {(i.provider_symbol or f"{i.symbol}.NS"): i for i in stale}
        try:
            if hasattr(self.provider, "fetch_many"):
                fetched = self.provider.fetch_many(list(symbols), period)
            else:
                fetched = {sym: self.provider.fetch_history(sym, period) for sym in symbols}
        except Exception:
            session.rollback()
            return
        for sym, bars in fetched.items():
            instrument = symbols.get(sym)
            if not instrument or not bars:
                continue
            bars.sort(key=lambda bar: bar["date"])
            self._save_bars(session, instrument.id, bars)
            latest, previous = bars[-1], (bars[-2] if len(bars) > 1 else None)
            snapshot = session.get(MarketSnapshot, instrument.id) or MarketSnapshot(instrument_id=instrument.id)
            session.add(snapshot)
            snapshot.close = latest["close"]
            snapshot.previous_close = previous["close"] if previous else None
            snapshot.change_percent = ((latest["close"] / previous["close"]) - 1) * 100 if previous and previous["close"] else None
            snapshot.volume = latest.get("volume")
            snapshot.market_as_of = _aware(latest["date"])
            snapshot.fetched_at = now
            snapshot.error_message = None
        session.commit()

    def quote(self, session: Session, instrument: Instrument) -> dict[str, Any]:
        with self._lock_guard:
            lock = self._instrument_locks.setdefault(instrument.id, Lock())
        with lock:
            return self._load_quote(session, instrument)

    def _load_quote(self, session: Session, instrument: Instrument) -> dict[str, Any]:
        snapshot = session.get(MarketSnapshot, instrument.id)
        now = utc_now()
        if snapshot and _aware(snapshot.fetched_at) + self.cache_ttl > now and snapshot.close is not None:
            return self._quote_payload(snapshot, "cached")

        try:
            bars = self.provider.fetch_history(instrument.provider_symbol or f"{instrument.symbol}.NS", "5d")
            if not bars:
                raise ValueError("Yahoo Finance returned no daily price data for this ticker.")
            bars.sort(key=lambda bar: bar["date"])
            latest = bars[-1]
            previous = bars[-2] if len(bars) > 1 else None
            previous_close = previous["close"] if previous else None
            change = ((latest["close"] / previous_close) - 1) * 100 if previous_close else None
            if snapshot is None:
                snapshot = MarketSnapshot(instrument_id=instrument.id)
                session.add(snapshot)
            snapshot.close = latest["close"]
            snapshot.previous_close = previous_close
            snapshot.change_percent = change
            snapshot.volume = latest.get("volume")
            snapshot.market_as_of = _aware(latest["date"])
            snapshot.fetched_at = now
            snapshot.error_message = None
            self._save_bars(session, instrument.id, bars)
            session.commit()
            session.refresh(snapshot)
            return self._quote_payload(snapshot, "fresh")
        except Exception as exc:
            session.rollback()
            snapshot = session.get(MarketSnapshot, instrument.id)
            if snapshot:
                snapshot.error_message = _error_text(exc)
                session.commit()
                return self._quote_payload(snapshot, "stale") if snapshot.close is not None else self._unavailable(exc)
            return self._unavailable(exc)

    def history(self, session: Session, instrument: Instrument, period: str = "1y") -> dict[str, Any]:
        allowed = {"5d", "1mo", "3mo", "6mo", "1y", "2y"}
        period = period if period in allowed else "1y"
        quote = self.quote(session, instrument)
        rows = session.scalars(
            select(DailyPrice).where(DailyPrice.instrument_id == instrument.id).order_by(DailyPrice.trading_date)
        ).all()
        requested = _period_start(period)
        cache_is_fresh = bool(rows) and rows[0].trading_date <= requested.date() + timedelta(days=5) and max(
            _aware(row.fetched_at) for row in rows
        ) + self.cache_ttl > utc_now()
        fetch_error = None
        if not cache_is_fresh:
            try:
                fetched_bars = self.provider.fetch_history(instrument.provider_symbol or f"{instrument.symbol}.NS", period)
                if fetched_bars:
                    self._save_bars(session, instrument.id, fetched_bars)
                    session.commit()
                    rows = session.scalars(
                        select(DailyPrice).where(DailyPrice.instrument_id == instrument.id).order_by(DailyPrice.trading_date)
                    ).all()
            except Exception as exc:
                session.rollback()
                fetch_error = _error_text(exc)
        complete_history = bool(rows) and rows[0].trading_date <= requested.date() + timedelta(days=5)
        bars = [
            {"date": row.trading_date.isoformat(), "open": row.open, "high": row.high,
             "low": row.low, "close": row.close, "volume": row.volume}
            for row in rows if row.trading_date >= requested.date()
        ]
        if not bars or not complete_history and quote["status"] == "unavailable":
            return {"symbol": instrument.symbol, "source": self.source, "status": "unavailable", "market_as_of": None,
                    "fetched_at": utc_now().isoformat(), "error": fetch_error or quote["error"] or "No daily history is available for the requested period.", "items": []}
        history_status = quote["status"] if complete_history else "stale"
        return {"symbol": instrument.symbol, "source": self.source, "status": history_status,
                "market_as_of": quote["market_as_of"], "fetched_at": quote["fetched_at"],
                "error": fetch_error or quote.get("error") or (None if complete_history else "Cached bars do not cover the requested period."), "items": bars}

    def _save_bars(self, session: Session, instrument_id: int, bars: list[dict[str, Any]]) -> None:
        fetched_at = utc_now()
        for bar in bars:
            bar_date = _trading_date(bar["date"])
            exists = session.scalar(select(DailyPrice.id).where(
                DailyPrice.instrument_id == instrument_id, DailyPrice.trading_date == bar_date
            ))
            if exists:
                row = session.get(DailyPrice, exists)
            else:
                row = DailyPrice(instrument_id=instrument_id, trading_date=bar_date)
                session.add(row)
            row.open = bar.get("open")
            row.high = bar.get("high")
            row.low = bar.get("low")
            row.close = bar["close"]
            row.volume = bar.get("volume")
            row.fetched_at = fetched_at

    def _quote_payload(self, snapshot: MarketSnapshot, status: str) -> dict[str, Any]:
        return {"status": status, "source": self.source, "close": snapshot.close,
                "previous_close": snapshot.previous_close, "change_percent": snapshot.change_percent,
                "volume": snapshot.volume,
                "market_as_of": _aware(snapshot.market_as_of).isoformat() if snapshot.market_as_of else None,
                "fetched_at": _aware(snapshot.fetched_at).isoformat(), "error": snapshot.error_message,
                "is_demo": False}

    def _unavailable(self, exc: Exception) -> dict[str, Any]:
        return {"status": "unavailable", "source": self.source, "close": None, "previous_close": None,
                "change_percent": None, "volume": None, "market_as_of": None,
                "fetched_at": utc_now().isoformat(), "error": _error_text(exc), "is_demo": False}


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _trading_date(value: datetime) -> Any:
    return value.date() if isinstance(value, datetime) else value


def _period_start(period: str) -> datetime:
    days = {"5d": 7, "1mo": 32, "3mo": 93, "6mo": 186, "1y": 367, "2y": 733}[period]
    return datetime.now(timezone.utc) - timedelta(days=days)


def _error_text(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    return message[:300]
