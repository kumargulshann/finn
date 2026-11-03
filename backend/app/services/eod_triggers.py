"""End-of-day triggered alerts computed from real daily bars.

For every holding and every recent trading day we compute
  * volume multiple  = that day's volume ÷ mean volume of the previous 20 sessions
  * daily move       = close ÷ previous close − 1
and store a "Price move" event when either crosses the *lowest* selectable threshold
(1.5× volume or ±2 %). The user's own thresholds are applied when the digest is read, so changing
a threshold in Settings re-filters instantly without recomputing anything.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domain.models import Announcement, DailyPrice, Instrument

IST = ZoneInfo("Asia/Kolkata")
MIN_VOLUME_MULTIPLE = 1.5
MIN_MOVE_PCT = 2.0
BASELINE_SESSIONS = 20
LOOKBACK_DAYS = 31


def day_signals(bars: list[DailyPrice]) -> list[dict[str, Any]]:
    """bars sorted ascending by trading_date → per-day signal metrics (needs ≥ 6 prior sessions)."""
    out = []
    for i in range(1, len(bars)):
        bar, prev = bars[i], bars[i - 1]
        base = [b.volume for b in bars[max(0, i - BASELINE_SESSIONS):i] if b.volume]
        avg = sum(base) / len(base) if len(base) >= 6 else None
        multiple = round(bar.volume / avg, 2) if avg and bar.volume else None
        move = round((bar.close / prev.close - 1) * 100, 2) if prev.close else None
        out.append({"trading_date": bar.trading_date, "close": bar.close, "volume": bar.volume,
                    "avg_volume_20d": round(avg) if avg else None, "volume_multiple": multiple, "change_pct": move})
    return out


def latest_signal(session: Session, instrument: Instrument) -> dict[str, Any] | None:
    bars = _bars(session, instrument.id, days=60)
    signals = day_signals(bars)
    return signals[-1] if signals else None


def _bars(session: Session, instrument_id: int, days: int) -> list[DailyPrice]:
    since = date.today() - timedelta(days=days)
    return list(session.scalars(select(DailyPrice).where(DailyPrice.instrument_id == instrument_id, DailyPrice.trading_date >= since)
                                .order_by(DailyPrice.trading_date)))


def _published_at(trading_day: date) -> datetime:
    close_ist = datetime.combine(trading_day, time(15, 45), tzinfo=IST).astimezone(timezone.utc)
    return min(close_ist, datetime.now(timezone.utc))


def sync_triggers(session: Session, instruments: list[Instrument]) -> int:
    """Upsert EOD trigger events for the given instruments. Returns number of live trigger rows."""
    total = 0
    window_start = date.today() - timedelta(days=LOOKBACK_DAYS)
    for instrument in instruments:
        bars = _bars(session, instrument.id, days=LOOKBACK_DAYS + 45)
        keep: set[str] = set()
        for sig in day_signals(bars):
            if sig["trading_date"] < window_start:
                continue
            vm, mv = sig["volume_multiple"], sig["change_pct"]
            if not ((vm is not None and vm >= MIN_VOLUME_MULTIPLE) or (mv is not None and abs(mv) >= MIN_MOVE_PCT)):
                continue
            slug = f"eod-{instrument.symbol.lower()}-{sig['trading_date'].isoformat()}"
            keep.add(slug)
            _upsert(session, instrument, slug, sig)
            total += 1
        stale = select(Announcement.id).where(Announcement.company_id == instrument.company_id, Announcement.slug.like(f"eod-{instrument.symbol.lower()}-%"))
        if keep:
            stale = stale.where(Announcement.slug.not_in(keep))
        session.execute(delete(Announcement).where(Announcement.id.in_(stale)))
    session.commit()
    return total


def _same_day_filing(session: Session, company_id: int, trading_day: date) -> Announcement | None:
    start = datetime.combine(trading_day - timedelta(days=1), time(16, 0), tzinfo=IST).astimezone(timezone.utc)
    end = datetime.combine(trading_day, time(15, 30), tzinfo=IST).astimezone(timezone.utc)
    return session.scalar(select(Announcement).where(
        Announcement.company_id == company_id, Announcement.is_demo.is_(False), Announcement.category.not_in(("Price move", "Routine")),
        Announcement.published_at >= start, Announcement.published_at <= end).order_by(Announcement.published_at.desc()).limit(1))


def _upsert(session: Session, instrument: Instrument, slug: str, sig: dict[str, Any]) -> None:
    vm, mv = sig["volume_multiple"], sig["change_pct"]
    parts = []
    if vm is not None and vm >= MIN_VOLUME_MULTIPLE:
        parts.append(f"Volume {vm:.1f}× its 20-day average")
    if mv is not None:
        parts.append(f"shares {'+' if mv >= 0 else '−'}{abs(mv):.1f}%" if parts else f"Shares {'+' if mv >= 0 else '−'}{abs(mv):.1f}% on the day")
    title = "; ".join(parts)
    match = _same_day_filing(session, instrument.company_id, sig["trading_date"])
    summary = (f"Coincides with a filing: “{match.title}” ({match.category})." if match
               else "No exchange filing from the company in the preceding session — the move has no disclosed catalyst.")
    severity = "High" if ((vm or 0) >= 3 and abs(mv or 0) >= 3) or abs(mv or 0) >= 6 or (vm or 0) >= 5 else "Medium"
    facts = [
        f"Trading date: {sig['trading_date'].strftime('%d %b %Y')}",
        f"Close: ₹{sig['close']:,.2f}",
        f"Daily move: {mv:+.2f}%" if mv is not None else "Daily move: unavailable",
        f"Volume: {sig['volume']:,}" if sig["volume"] else "Volume: unavailable",
        f"20-day average volume: {sig['avg_volume_20d']:,}" if sig["avg_volume_20d"] else "20-day average volume: unavailable",
        f"Volume multiple: {vm:.2f}×" if vm is not None else "Volume multiple: unavailable",
    ]
    enrichment = {"kind": "eod", **{k: (v.isoformat() if isinstance(v, date) else v) for k, v in sig.items()},
                  "matched_filing": match.slug if match else None, "matched_filing_title": match.title if match else None}
    event = session.scalar(select(Announcement).where(Announcement.slug == slug))
    if event is None:
        event = Announcement(slug=slug, company_id=instrument.company_id, is_demo=False, is_read=False, is_saved=False)
        session.add(event)
    event.category = "Price move"
    event.title = title[:300]
    event.summary = summary
    event.why_it_matters = ("Volume and price moved together with a same-day disclosure — the market is reacting to news; read the filing."
                            if match else "An unusual move without a company disclosure can mean news not yet filed, sector flows or block trades. Worth a check before the next session.")
    event.severity = severity
    event.positive = (mv or 0) >= 0
    event.published_at = _published_at(sig["trading_date"])
    event.source_name = "Yahoo Finance EOD (via yfinance)"
    event.source_url = f"https://finance.yahoo.com/quote/{instrument.provider_symbol or instrument.symbol + '.NS'}/history"
    event.source_date = sig["trading_date"].strftime("%d %b %Y") + " · end of day"
    event.source_exchange = "EOD"
    event.facts_json = json.dumps(facts, ensure_ascii=False)
    event.enrichment_json = json.dumps(enrichment, ensure_ascii=False)
