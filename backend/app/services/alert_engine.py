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


def enrichment_of(event: Announcement) -> dict[str, Any]:
    try:
        return json.loads(event.enrichment_json) if event.enrichment_json else {}
    except (TypeError, ValueError):
        return {}


def should_include_alert(
    event: Announcement,
    rules_by_category: dict[str, AlertRule],
    facts: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Apply the user's category toggles and thresholds.

    EOD "Price move" events pass if *either* enabled rule fires: volume ≥ N× its 20-day average
    ("Price move" rule) or |daily move| ≥ N% ("Price change" rule).
    """
    if event.category == "Price move":
        data = enrichment_of(event)
        vm, mv = data.get("volume_multiple"), data.get("change_pct")
        if not data:  # legacy rows without structured metrics
            metrics = extract_alert_metrics(f"{event.title} {event.summary} {' '.join(facts or [])}")
            vm, mv = metrics.get("volume_multiple"), metrics.get("price_change_pct")
        vol_rule, move_rule = rules_by_category.get("Price move"), rules_by_category.get("Price change")
        vol_hit = bool(vol_rule and vol_rule.enabled and vm is not None and vm >= (vol_rule.threshold or 2.0))
        move_hit = bool(move_rule and move_rule.enabled and mv is not None and abs(mv) >= (move_rule.threshold or 4.0))
        if vol_hit or move_hit:
            return True, None
        return False, "Below your volume / price-move thresholds"

    rule = rules_by_category.get(event.category)
    if not rule or not rule.enabled:
        return False, f"Category '{event.category}' is disabled by user alert preferences"
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
        "Price move": 18.0,
        "Order wins": 25.0,
        "Fundraising": 25.0,
        "Management changes": 20.0,
        "Corporate actions": 15.0,
        "Corporate action": 15.0,
        "Capex": 22.0,
        "Credit rating": 22.0,
        "Pledging": 22.0,
        "Insider trading": 12.0,
        "Earnings call": 5.0,
        "Investor meetings": 5.0,
        "Routine": 0.0,
    }
    score += category_weights.get(event.category, 15.0)

    # 3. Market Movement Magnitude (today's tape adds urgency to material filings, not routine ones)
    if market_data and event.category not in ("Routine", "Earnings call", "Investor meetings", "Price move"):
        change_pct = market_data.get("change_percent")
        if change_pct is not None:
            abs_change = abs(change_pct)
            score += min(abs_change * 3.0, 15.0)

    if event.category == "Price move":
        data = enrichment_of(event)
        vol = data.get("volume_multiple") or extract_alert_metrics(f"{event.title} {event.summary}").get("volume_multiple")
        if vol:
            score += min(vol * 6.0, 25.0)
        move = data.get("change_pct")
        if move is not None:
            score += min(abs(move) * 3.0, 20.0)
    elif event.category == "Results" and enrichment_of(event).get("status") == "parsed":
        pat = next((m for m in enrichment_of(event)["metrics"] if m["metric"] == "PAT"), {})
        if pat.get("yoy_pct") is not None:
            score += min(abs(pat["yoy_pct"]) / 2.0, 20.0)   # bigger surprises rank higher

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
        pass  # facts and "why" are written by the EOD trigger engine from the actual bars
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

        if cat == "Results":
            res_key = (company_id, f"results:{published_day}")
            if res_key in topic_map:
                existing = topic_map[res_key]
                if alert.get("enrichment", {}).get("status") == "parsed" and existing.get("enrichment", {}).get("status") != "parsed":
                    deduped[deduped.index(existing)] = alert
                    topic_map[res_key] = alert
                continue
            topic_map[res_key] = alert

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
