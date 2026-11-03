import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import sqlite3
import re
from pathlib import Path
from app.services.guidance_actual import METRICS

db_path = Path(__file__).resolve().parents[1] / "data" / "finn.db"
con = sqlite3.connect(str(db_path))
cur = con.cursor()

docs = cur.execute('SELECT d.id, c.name, d.title, d.fiscal_period FROM research_documents d JOIN companies c ON d.company_id = c.id WHERE d.document_type="earnings_transcript"').fetchall()

for doc_id, comp_name, title, period in docs:
    chunks = cur.execute('SELECT page_number, text FROM research_chunks WHERE document_id=? ORDER BY page_number ASC', (doc_id,)).fetchall()
    print(f"\n=======================================================")
    print(f"{comp_name} - {title} ({period})")
    for p, text in chunks:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) >= 20]
        for s in sentences:
            for m_name, m_pat in METRICS.items():
                m = re.search(m_pat, s, re.I)
                if m:
                    # check if guide or actual
                    is_guide = bool(re.search(r"\b(guid(?:e|ed|ance)|expect(?:s|ed)?|outlook|target|forecast|aim(?:s|ed)?)\b", s, re.I))
                    is_actual = bool(re.search(r"\b(reported|recorded|delivered|achieved|stood at|was|were|grew|declined|increased|decreased|actual(?:ly)?)\b", s, re.I))
                    if is_guide or is_actual:
                        kind = "GUIDE" if is_guide else "ACTUAL"
                        if re.search(r"\d", s):
                            print(f"  [p.{p}][{m_name}][{kind}]: {s[:140]}...")
                            break
