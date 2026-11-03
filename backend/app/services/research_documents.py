"""Fetch official company documents, extract page text, and retrieve source evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

import pymupdf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import Company, Instrument, ResearchChunk, ResearchDocument
from app.integrations.documents.nse_provider import NSEResearchDocumentProvider
from app.services.research_synthesis import clean_tokens, is_boilerplate, synthesize_grounded_answer, topic_tokens

LENS_TERMS = {
    "business overview": "business company segment product service customer market strategy geography",
    "financial performance": "financial revenue sales growth profit EBITDA PAT margin earnings quarter year",
    "balance sheet": "balance sheet asset liability debt borrowings leverage liquidity capital working capital",
    "cash flow": "cash flow operating investing financing free cash flow capex cash generation",
    "management guidance": "management guidance outlook expect forecast target anticipate plan demand",
    "bull vs bear analysis": "growth demand margin opportunity strength risk challenge weakness decline debt uncertainty",
}
METRIC_TERMS = re.compile(r"\b(revenue|sales|profit|ebitda|ebit|pat|margin|cash flow|capex|assets|liabilit(?:y|ies)|borrowings|debt|order book|arpu|subscribers?|growth|net interest income|npa|capital adequacy)\b", re.I)
NUMBER_TERMS = re.compile(r"(?:₹|\bINR\b|\bRs\.?\s*)?\s*\d[\d,]*(?:\.\d+)?\s*(?:%|crores?|cr\b|million|billion|lakh|lakhs|basis points|bps)?", re.I)
GUIDANCE_TERMS = re.compile(r"\b(guidance|outlook|expect(?:ed|s)?|forecast|target|aim(?:s|ed)?|anticipat(?:e|es|ed)|plan(?:s|ned)?|we see|likely to)\b", re.I)
UPDATE_TERMS = re.compile(r"\b(segment|business|product|service|customer|market|geograph|launch|capacity|expansion|investment|order|pipeline|strategy|acquisition|digital|manufacturing|subscriber|distribution)\w*\b", re.I)
TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?", re.I)
STOP_WORDS = {"about", "after", "also", "among", "and", "are", "because", "been", "being", "but", "can", "could", "does", "during", "each", "for", "from", "had", "has", "have", "into", "its", "may", "more", "most", "not", "our", "over", "per", "said", "such", "than", "that", "the", "their", "them", "there", "these", "this", "those", "through", "under", "was", "were", "what", "when", "where", "which", "while", "will", "with", "would", "you", "your"}


def _tokens(value: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(value) if len(token) > 1 and token.lower() not in STOP_WORDS]


def _split_chunks(text: str, max_chars: int = 1400, overlap: int = 180) -> list[str]:
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind(". ", start, end), text.rfind("; ", start, end), text.rfind(" ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _extract_facts(text: str) -> tuple[list[str], list[str], list[str]]:
    sentences = [part.strip(" •\t-\r\n") for part in re.split(r"(?<=[.!?])\s+|\n+", text) if len(part.strip()) >= 24]
    metrics = list(dict.fromkeys(sentence[:500] for sentence in sentences if METRIC_TERMS.search(sentence) and NUMBER_TERMS.search(sentence)))[:12]
    guidance = list(dict.fromkeys(sentence[:500] for sentence in sentences if GUIDANCE_TERMS.search(sentence)))[:12]
    updates = list(dict.fromkeys(sentence[:500] for sentence in sentences if UPDATE_TERMS.search(sentence)))[:12]
    return metrics, guidance, updates


def extract_pdf_pages(pdf_bytes: bytes) -> tuple[int, list[tuple[int, str]]]:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        pages = [(page_number, page.get_text("text", sort=True).strip()) for page_number, page in enumerate(pdf, start=1)]
        readable = [(number, text) for number, text in pages if len(text) >= 40]
        if not readable:
            raise ValueError("PDF has no extractable text (it may be scanned or image-only).")
        return len(pdf), readable


def _bm25(query: list[str], texts: list[str]) -> list[float]:
    tokenized = [_tokens(text) for text in texts]
    if not query or not tokenized:
        return [0.0] * len(texts)
    doc_freq: Counter[str] = Counter()
    for words in tokenized:
        doc_freq.update(set(query).intersection(words))
    average_length = sum(map(len, tokenized)) / max(1, len(tokenized))
    n = len(tokenized)
    scores = []
    for words in tokenized:
        frequencies = Counter(words)
        score = 0.0
        for term in query:
            freq = frequencies[term]
            if not freq:
                continue
            idf = math.log(1 + (n - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            score += idf * (freq * 2.2) / (freq + 1.2 * (0.25 + 0.75 * len(words) / max(1, average_length)))
        scores.append(score)
    return scores


class ResearchDocumentService:
    def __init__(self, provider: NSEResearchDocumentProvider | None = None) -> None:
        self.provider = provider or NSEResearchDocumentProvider()

    def refresh(self, session: Session, limit: int = 5, include_transcripts: bool = True, symbols: list[str] | None = None, transcripts_per_company: int = 1) -> dict[str, Any]:
        if symbols:
            from app.services.company_discovery import ensure_company
            for s in symbols:
                if s.strip():
                    ensure_company(session, s.strip().upper())
            instruments = session.scalars(select(Instrument).where(Instrument.exchange == "NSE", Instrument.symbol.in_([s.strip().upper() for s in symbols if s.strip()])).order_by(Instrument.symbol)).all()
        else:
            instruments = session.scalars(select(Instrument).where(Instrument.exchange == "NSE").order_by(Instrument.symbol).limit(limit)).all()
        result: dict[str, Any] = {"companies": [], "catalogued": 0, "indexed": 0, "unchanged": 0, "errors": []}
        for instrument in instruments:
            company = session.get(Company, instrument.company_id)
            if company is None:
                continue
            result["companies"].append(instrument.symbol)
            sources, errors = self.provider.catalog(instrument.symbol, include_transcripts, transcripts_per_company)
            result["errors"].extend(errors)
            result["catalogued"] += len(sources)
            for source in sources:
                current = session.scalar(select(ResearchDocument).where(ResearchDocument.company_id == company.id, ResearchDocument.source_key == source["source_key"]))
                if current and current.source_url == source["source_url"]:
                    current.title = source["title"]
                    current.document_type = source["document_type"]
                    current.fiscal_period = source["fiscal_period"] or current.fiscal_period
                    current.published_at = source["published_at"] or current.published_at
                    result["unchanged"] += 1
                    continue
                try:
                    pdf = self.provider.download_pdf(source["source_url"])
                    content_hash = hashlib.sha256(pdf).hexdigest()
                    if current and current.content_hash == content_hash:
                        current.title = source["title"]
                        current.published_at = source["published_at"]
                        current.fiscal_period = source["fiscal_period"] or current.fiscal_period
                        current.fetched_at = datetime.now(timezone.utc)
                        result["unchanged"] += 1
                        continue
                    page_count, pages = extract_pdf_pages(pdf)
                    if source["document_type"] == "earnings_transcript" and not source.get("fiscal_period"):
                        early_text = "\n".join(text for _, text in pages[:5])
                        detected_period = NSEResearchDocumentProvider.extract_fiscal_period(
                            text=source.get("title", ""),
                            title=source.get("title", ""),
                            filename=source["source_url"],
                            pdf_text=early_text,
                            published_at=source.get("published_at"),
                        )
                        if detected_period:
                            source["fiscal_period"] = detected_period
                    if current:
                        session.query(ResearchChunk).filter(ResearchChunk.document_id == current.id).delete(synchronize_session=False)
                        document = current
                    else:
                        document = ResearchDocument(company_id=company.id, source_key=source["source_key"], title=source["title"], document_type=source["document_type"], fiscal_period=source["fiscal_period"], published_at=source["published_at"], source_name=source["source_name"], source_url=source["source_url"], content_hash=content_hash, page_count=page_count, is_demo=False)
                        session.add(document)
                        session.flush()
                    document.title = source["title"]
                    document.document_type = source["document_type"]
                    document.fiscal_period = source["fiscal_period"]
                    document.published_at = source["published_at"]
                    document.source_name = source["source_name"]
                    document.source_url = source["source_url"]
                    document.content_hash = content_hash
                    document.page_count = page_count
                    document.is_demo = False
                    for page_number, page_text in pages:
                        for chunk_index, chunk_text in enumerate(_split_chunks(page_text)):
                            metrics, guidance, updates = _extract_facts(chunk_text)
                            session.add(ResearchChunk(document_id=document.id, page_number=page_number, chunk_index=chunk_index, text=chunk_text, financial_metrics_json=json.dumps(metrics, ensure_ascii=False), guidance_json=json.dumps(guidance, ensure_ascii=False), business_updates_json=json.dumps(updates, ensure_ascii=False)))
                    session.flush()
                    result["indexed"] += 1
                except Exception as exc:
                    result["errors"].append(f"{instrument.symbol} {source['document_type']}: {str(exc).splitlines()[0][:180]}")
            session.commit()
        return result

    @staticmethod
    def list_documents(session: Session, company_id: int) -> dict[str, Any]:
        rows = session.execute(select(ResearchDocument, Company).join(Company, Company.id == ResearchDocument.company_id).where(ResearchDocument.company_id == company_id, ResearchDocument.is_demo.is_(False)).order_by(ResearchDocument.published_at.desc())).all()
        items = [{"id": doc.id, "title": doc.title, "document_type": doc.document_type, "fiscal_period": doc.fiscal_period, "published_at": doc.published_at.isoformat() if doc.published_at else None, "source_name": doc.source_name, "source_url": doc.source_url, "page_count": doc.page_count, "fetched_at": doc.fetched_at.isoformat(), "is_demo": doc.is_demo} for doc, _ in rows]
        return {"items": items, "count": len(items), "company_id": company_id}

    @staticmethod
    def answer(session: Session, company_id: int, question: str, lens: str, limit: int = 6) -> dict[str, Any]:
        lens = lens if lens in LENS_TERMS else "financial performance"
        company = session.get(Company, company_id)
        docs = session.scalars(select(ResearchDocument).where(ResearchDocument.company_id == company_id, ResearchDocument.is_demo.is_(False))).all()
        rows = session.execute(select(ResearchChunk, ResearchDocument).join(ResearchDocument, ResearchDocument.id == ResearchChunk.document_id).where(ResearchDocument.company_id == company_id, ResearchDocument.is_demo.is_(False))).all()

        lens_query = LENS_TERMS[lens]
        if lens == "bull vs bear analysis":
            lens_query += " growth strength demand margin opportunity risk challenge decline debt uncertain pressure"

        q_toks = clean_tokens(question)
        q_topics = topic_tokens(q_toks)
        lens_toks = clean_tokens(lens_query)
        # Weight user question topic tokens significantly higher than broad lens context
        query_terms = list(dict.fromkeys(q_topics * 4 + q_toks * 2 + lens_toks))

        texts = [chunk.text for chunk, _ in rows]
        tokenized_chunks = [clean_tokens(t) for t in texts]
        raw_scores = _bm25(query_terms, texts)

        scored_rows = []
        q_lower = question.lower()
        is_quarterly_or_guidance = any(k in q_lower for k in ["guidance", "outlook", "quarter", "q1", "q2", "q3", "q4", "nim", "call", "transcript"]) or lens == "management guidance"

        for i, (score, (chunk, doc)) in enumerate(zip(raw_scores, rows)):
            if is_boilerplate(chunk.text):
                continue
            if score <= 0:
                continue
            # Require at least one substantive topic token match when question has topic tokens
            if q_topics and not any(t in tokenized_chunks[i] for t in q_topics):
                continue
            final_score = score
            # Prioritize conference call transcripts for guidance and quarterly questions
            if doc.document_type == "earnings_transcript" and is_quarterly_or_guidance:
                final_score *= 1.35
            scored_rows.append((final_score, chunk, doc))

        ranked = sorted(scored_rows, key=lambda item: item[0], reverse=True)[:limit]

        citations = []
        all_metrics: list[str] = []
        all_guidance: list[str] = []
        all_updates: list[str] = []
        for _, chunk, doc in ranked:
            citation_url = f"{doc.source_url}#page={chunk.page_number}"
            citations.append({
                "document_id": doc.id,
                "document_title": doc.title,
                "document_type": doc.document_type,
                "fiscal_period": doc.fiscal_period,
                "page": chunk.page_number,
                "excerpt": chunk.text[:900],
                "source_url": citation_url,
                "source_name": doc.source_name,
            })
            all_metrics.extend(json.loads(chunk.financial_metrics_json))
            all_guidance.extend(json.loads(chunk.guidance_json))
            all_updates.extend(json.loads(chunk.business_updates_json))

        unique = lambda values: list(dict.fromkeys(values))[:8]

        # Calculate document frequency of query topic terms across this company's corpus
        q_doc_freq = {t: sum(1 for words in tokenized_chunks if t in words) for t in q_topics}

        # Synthesize clear, structured answer with grounded claims, conflict analysis, and sufficiency evaluation
        synthesis = synthesize_grounded_answer(company, question, lens, ranked, docs, doc_freq=q_doc_freq)

        supportive, risks = [], []
        for citation in citations:
            excerpt = citation["excerpt"]
            terms = excerpt.lower()
            entry = {"excerpt": excerpt[:500], "document_title": citation["document_title"], "page": citation["page"], "source_url": citation["source_url"]}
            if any(word in terms for word in ("growth", "increase", "improved", "strong", "higher", "opportunity", "demand", "expansion", "profitability")):
                supportive.append(entry)
            if any(word in terms for word in ("risk", "decline", "lower", "pressure", "uncertain", "weak", "debt", "challenge", "decrease", "regulatory")):
                risks.append(entry)

        return {
            "company_id": company_id,
            "lens": lens,
            "question": question,
            "answer": synthesis["answer"],
            "evidence_gap": synthesis["evidence_gap"],
            "key_claims": synthesis["key_claims"],
            "conflicting_info": synthesis["conflicting_info"],
            "evidence_sufficiency": synthesis["evidence_sufficiency"],
            "citations": citations,
            "financial_metrics": unique(all_metrics),
            "management_guidance": unique(all_guidance),
            "business_updates": unique(all_updates),
            "bull_evidence": supportive[:4],
            "bear_evidence": risks[:4],
            "document_count": len(docs),
            "is_demo": False,
        }
