"""Alert Engine: Prioritization, threshold evaluation, reason synthesis, and deduplication for FINN PUSH."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from app.domain.models import AlertRule, Announcement, Company, Instrument, PortfolioHolding


def extract_alert_metrics(text: str) -> dict[str, float]:
    """Extract volume multiplier, price percentage, and financial values from alert text."""
    metrics: dict[str, float] = {}

    vol_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:[xX\u00d7]|times)(?!\w)", text, re.IGNORECASE)
    if vol_match:
        try:
            metrics["volume_multiple"] = float(vol_match.group(1))
        except ValueError:
            pass

    pct_match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
    if pct_match:
        try:
            metrics["price_change_pct"] = float(pct_match.group(1))
        except ValueError:
            pass

    return metrics


def should_include_alert(
    event: Announcement,
    rules_by_category: dict[str, AlertRule],
    facts: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Verify if the alert's category is enabled and its metrics satisfy configured thresholds."""
    rule = rules_by_category.get(event.category)
    if not rule or not rule.enabled:
        return False, f"Category '{event.category}' is disabled by user alert preferences"

    if rule.threshold is not None:
        combined_text = f"{event.title} {event.summary} {' '.join(facts or [])}"
        metrics = extract_alert_metrics(combined_text)

        if event.category == "Price move":
            vol = metrics.get("volume_multiple")
            if vol is not None:
                if vol < rule.threshold:
                    return False, f"Volume multiple {vol:.1f}x is below user configured threshold {rule.threshold:.1f}x"
                return True, None

            price_pct = metrics.get("price_change_pct")
            if price_pct is not None:
                if abs(price_pct) < rule.threshold:
                    return False, f"Price change {price_pct:+.1f}% is below user configured threshold {rule.threshold:.1f}%"
                return True, None

    return True, None


def calculate_priority_score(
    event: Announcement,
    holding: PortfolioHolding | None = None,
    market_data: dict[str, Any] | None = None,
) -> float:
    """Calculate deterministic multi-factor priority score for Today digest ranking.

    Factors:
    - Financial Impact / Severity (High=50, Medium=25, Low=10)
    - Event Type Materiality (Results/Earnings=40, Acquisitions=35, Price move=30, etc.)
    - Unusual Market Movement Magnitude (Price change and volume surge magnitude)
    - Portfolio Exposure (Holding weight in user's portfolio)
    - Freshness Decay (Bonus for fresh breaking updates, gentle decay over 24h)
    """
    score = 0.0

    # 1. Financial Impact / Severity
    severity = (event.severity or "Medium").capitalize()
    if severity == "High":
        score += 50.0
    elif severity == "Medium":
        score += 25.0
    else:
        score += 10.0

    # 2. Event Type Materiality
    category_weights = {
        "Results": 40.0,
        "Earnings": 40.0,
        "Acquisitions": 35.0,
        "Regulatory updates": 30.0,
        "Price move": 30.0,
        "Order wins": 25.0,
        "Fundraising": 25.0,
        "Management changes": 20.0,
        "Corporate actions": 15.0,
        "Corporate action": 15.0,
        "Macro": 10.0,
    }
    score += category_weights.get(event.category, 15.0)

    # 3. Market Movement Magnitude
    if market_data:
        change_pct = market_data.get("change_percent")
        if change_pct is not None:
            abs_change = abs(change_pct)
            score += min(abs_change * 5.0, 25.0)
            if abs_change >= 3.0:
                score += 10.0

    if event.category == "Price move":
        metrics = extract_alert_metrics(f"{event.title} {event.summary}")
        vol = metrics.get("volume_multiple")
        if vol:
            score += min(vol * 8.0, 30.0)

    # 4. Portfolio Weight
    if holding and holding.weight:
        score += min(holding.weight * 1.2, 15.0)

    # 5. Freshness
    published = event.published_at
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age_hours = max(0.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600.0)
    freshness = max(0.0, 15.0 - (age_hours * 0.5))
    score += freshness

    return round(score, 2)


def enrich_alert_reasons(
    event: Announcement,
    company: Company,
    instrument: Instrument,
    holding: PortfolioHolding | None,
    market_data: dict[str, Any] | None,
    rule: AlertRule | None,
) -> tuple[str, list[str]]:
    """Synthesize explicit, transparent 'why_it_matters' and structured 'facts' for the alert."""
    try:
        facts: list[str] = json.loads(event.facts_json) if event.facts_json else []
    except Exception:
        facts = []

    why = (event.why_it_matters or "").strip()
    category = event.category
    severity = event.severity or "Medium"

    if not facts:
        facts = [
            f"Event category: {category}",
            f"Impact classification: {severity} priority",
            f"Source: {event.source_name}",
        ]
        money_matches = re.findall(
            r"(?:₹|Rs\.?|INR|USD|\$)\s*[\d,]+(?:\.\d+)?\s*(?:cr(?:ore)?s?|lakhs?|mn|bn|billion|million)?",
            f"{event.title} {event.summary}",
            re.IGNORECASE,
        )
        if money_matches:
            facts.append(f"Financial figure: {money_matches[0]}")
        pct_matches = re.findall(r"[\d,]+(?:\.\d+)?\s*%", f"{event.title} {event.summary}")
        if pct_matches:
            facts.append(f"Disclosed percentage: {pct_matches[0]}")

    if category == "Price move":
        metrics = extract_alert_metrics(f"{event.title} {event.summary} {' '.join(facts)}")
        vol = metrics.get("volume_multiple")
        pct = metrics.get("price_change_pct")
        threshold = rule.threshold if rule else 2.0

        has_rule_fact = any("threshold" in f.lower() or "alert rule" in f.lower() for f in facts)
        if not has_rule_fact and threshold:
            vol_info = f" (actual: {vol:.1f}×)" if vol else ""
            facts.append(f"Alert rule: volume threshold is {threshold:.1f}× average{vol_info}")

        if not why or why.startswith("Review the exchange filing"):
            vol_str = f"{vol:.1f}×" if vol else "unusual"
            pct_str = (
                f"{pct:+.2f}%"
                if pct is not None
                else (
                    f"{market_data.get('change_percent'):+.2f}%"
                    if market_data and market_data.get("change_percent") is not None
                    else "elevated volume"
                )
            )
            why = (
                f"Trading volume ran {vol_str} relative to typical levels with {pct_str} in share price. "
                f"Volume anomalies exceeding your {threshold:.1f}× threshold indicate elevated market interest. "
                "Monitor for follow-up company filings or sector-wide catalysts."
            )

    elif not why or why.startswith("Review the exchange filing"):
        enrichment_map = {
            "Results": f"{company.name}'s quarterly results establish the updated earnings run-rate. Compare reported revenue, operating margin, and PAT against historical quarters and stated management guidance.",
            "Order wins": f"New contract award enhances {company.name}'s revenue visibility. Assess the disclosed contract size, execution timeline, and margin expectations.",
            "Acquisitions": f"Strategic acquisition alters {company.name}'s capital allocation, growth trajectory, and integration risk profile. Evaluate purchase valuation and funding structure.",
            "Management changes": f"Leadership change at {company.name} affects operational oversight and strategic continuity. Note whether succession is internal or external.",
            "Fundraising": f"Capital raising impacts {company.name}'s capital structure and potential equity dilution. Review intended deployment for growth capex versus debt repayment.",
            "Regulatory updates": f"Regulatory communication requires compliance evaluation for {company.name}. Assess any operational restrictions or financial penalties disclosed.",
            "Corporate actions": f"Corporate action alters shareholder distribution or capital structure for {company.name}. Check the record date and eligibility criteria.",
        }
        why = enrichment_map.get(
            category,
            f"Review this {severity.lower()}-impact {category} filing from {company.name} for portfolio implications.",
        )

    return why, facts


def deduplicate_alerts(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate alerts across real exchange filings, demo events, and market moves."""
    seen_ids: set[str] = set()
    deduped: list[dict[str, Any]] = []
    topic_map: dict[tuple[int, str], dict[str, Any]] = {}

    for alert in alerts:
        alert_id = alert["id"]
        if alert_id in seen_ids:
            continue
        seen_ids.add(alert_id)

        company_id = alert.get("company_id") or 0
        cat = alert.get("type", "")
        published_day = (alert.get("published_at") or "")[:10]
        clean_words = tuple(sorted(re.findall(r"[a-z0-9]+", alert.get("title", "").lower())[:6]))
        topic_key = (company_id, f"{cat}:{published_day}:{clean_words}")

        if topic_key in topic_map:
            existing = topic_map[topic_key]
            if not alert.get("is_demo") and existing.get("is_demo"):
                idx = deduped.index(existing)
                deduped[idx] = alert
                topic_map[topic_key] = alert
            continue

        if cat == "Price move":
            move_key = (company_id, f"price-move:{published_day}")
            if move_key in topic_map:
                existing = topic_map[move_key]
                if not alert.get("is_demo") and existing.get("is_demo"):
                    idx = deduped.index(existing)
                    deduped[idx] = alert
                    topic_map[move_key] = alert
                continue
            topic_map[move_key] = alert

        topic_map[topic_key] = alert
        deduped.append(alert)

    return deduped
