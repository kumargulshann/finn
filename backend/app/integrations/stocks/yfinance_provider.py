from datetime import date, datetime
from typing import Any

import yfinance as yf


class YFinanceProvider:
    """Thin adapter around Yahoo Finance daily history via yfinance."""

    source = "Yahoo Finance (via yfinance)"

    def fetch_history(self, provider_symbol: str, period: str = "1y") -> list[dict[str, Any]]:
        frame = yf.Ticker(provider_symbol).history(
            period=period,
            interval="1d",
            auto_adjust=False,
            actions=False,
            raise_errors=True,
        )
        if frame is None or frame.empty:
            return []
        bars: list[dict[str, Any]] = []
        for stamp, row in frame.iterrows():
            ts = stamp.to_pydatetime() if hasattr(stamp, "to_pydatetime") else stamp
            if isinstance(ts, date) and not isinstance(ts, datetime):
                ts = datetime(ts.year, ts.month, ts.day)
            bars.append({
                "date": ts,
                "open": _number(row.get("Open")),
                "high": _number(row.get("High")),
                "low": _number(row.get("Low")),
                "close": _number(row.get("Close")),
                "volume": _integer(row.get("Volume")),
            })
        return [bar for bar in bars if bar["close"] is not None]


def _number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if result == result else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None
