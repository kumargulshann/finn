from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.domain.models import Company
from app.services.guidance_actual import guidance_vs_actual

router = APIRouter(tags=["research"])


class ResearchAnswerRequest(BaseModel):
    company_id: int
    question: str = Field(min_length=3, max_length=1200)
    lens: Literal["business overview", "financial performance", "balance sheet", "cash flow", "management guidance", "bull vs bear analysis", "guidance vs actual"]


@router.post("/research/documents/refresh")
def refresh_documents(request: Request, limit: int = Query(5, ge=1, le=10), include_transcripts: bool = True, symbols: str | None = None, transcripts_per_company: int = Query(1, ge=1, le=4)) -> dict:
    with request.app.state.session_factory() as session:
        try:
            selected = [item.strip().upper() for item in symbols.split(",") if item.strip()] if symbols else None
            return request.app.state.research_documents.refresh(session, limit=limit, include_transcripts=include_transcripts, symbols=selected, transcripts_per_company=transcripts_per_company)
        except Exception as exc:
            session.rollback()
            raise HTTPException(status_code=502, detail=f"Research document refresh failed: {str(exc).splitlines()[0][:200]}") from exc


@router.get("/companies/{company_id}/research/documents")
def list_company_documents(company_id: int, request: Request) -> dict:
    with request.app.state.session_factory() as session:
        if not session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
        return request.app.state.research_documents.list_documents(session, company_id)


@router.post("/research/answer")
def answer_research_question(payload: ResearchAnswerRequest, request: Request) -> dict:
    with request.app.state.session_factory() as session:
        if not session.get(Company, payload.company_id):
            raise HTTPException(status_code=404, detail="Company not found")
        return request.app.state.research_documents.answer(session, payload.company_id, payload.question, payload.lens)


@router.post("/research/guidance-vs-actual")
def compare_guidance_actual(payload: dict, request: Request) -> dict:
    company_id = payload.get("company_id")
    if not isinstance(company_id, int):
        raise HTTPException(status_code=422, detail="company_id must be an integer")
    with request.app.state.session_factory() as session:
        if not session.get(Company, company_id):
            raise HTTPException(status_code=404, detail="Company not found")
        return guidance_vs_actual(session, company_id)
