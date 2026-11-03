from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from app.domain.models import AlertRule

router = APIRouter(tags=["alert rules"])

@router.get("/alert-rules")
def list_rules(request: Request) -> dict:
    with request.app.state.session_factory() as session:
        rules = session.scalars(select(AlertRule).order_by(AlertRule.id)).all()
        return {"items": [{"id": r.id, "name": r.name, "category": r.category, "enabled": r.enabled, "threshold": r.threshold} for r in rules], "is_demo": True}

@router.patch("/alert-rules/{rule_id}")
def update_rule(rule_id: int, request: Request, enabled: bool | None = None, threshold: float | None = None) -> dict:
    with request.app.state.session_factory() as session:
        rule = session.get(AlertRule, rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        if enabled is not None:
            rule.enabled = enabled
        if threshold is not None:
            if threshold < 1 or threshold > 10:
                raise HTTPException(status_code=422, detail="Threshold must be between 1 and 10")
            rule.threshold = threshold
        session.commit()
        return {"id": rule.id, "name": rule.name, "category": rule.category, "enabled": rule.enabled, "threshold": rule.threshold}
