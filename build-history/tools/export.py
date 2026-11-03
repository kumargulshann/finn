"""Export Codex / Antigravity / Claude Code sessions to readable Markdown transcripts."""
import datetime as dt
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(__file__))
from pb import parse, strings, varint  # noqa: E402

TOOL_ARG_MAX = 1200
TOOL_OUT_MAX = 700
NOTE_MAX = 400

SECRET_PATTERNS = [
    (re.compile(r"sk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"), "sk-[REDACTED]"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "AIza[REDACTED]"),
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "gh_[REDACTED]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{30,}"), "github_pat_[REDACTED]"),
    (re.compile(r"hf_[A-Za-z0-9]{30,}"), "hf_[REDACTED]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{20,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:api[_-]?key|secret|token|password)\s*[=:]\s*['\"]?)[^\s'\"]{12,}"), r"\1[REDACTED]"),
    (re.compile(r"(?<![\\w.%+\-])[A-Za-z0-9._%+\-]{2,}@(?!anthropic\.com|enam\.com)[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[a-z]{2,}\b(?!\()"), "[email redacted]"),
]


def scrub(text: str) -> str:
    for pat, rep in SECRET_PATTERNS:
        text = pat.sub(rep, text)
    return text


def trunc(text: str, n: int) -> str:
    text = text.strip()
    if len(text) <= n:
        return text
    return text[:n].rstrip() + f"\n… [truncated {len(text) - n:,} chars]"


def fence(text: str, lang: str = "") -> str:
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{lang}\n{text}\n{ticks}"


def details(summary: str, body: str) -> str:
    return f"<details><summary>{summary}</summary>\n\n{body}\n\n</details>\n"


class Doc:
    def __init__(self, title: str, meta: list[str]):
        self.parts = [f"# {title}\n", *[f"- {m}" for m in meta], ""]
        self.stats = {"user": 0, "assistant": 0, "tool": 0}

    def user(self, ts, text):
        self.stats["user"] += 1
        quoted = "\n".join("> " + ln for ln in text.strip().splitlines())
        self.parts.append(f"\n---\n\n## 🧑 User · {ts}\n\n{quoted}\n")

    def assistant(self, ts, text):
        self.stats["assistant"] += 1
        self.parts.append(f"\n### 🤖 Assistant · {ts}\n\n{text.strip()}\n")

    def thinking(self, text):
        self.parts.append(details("💭 reasoning summary", text.strip()))

    def tool(self, name, args, output=None):
        self.stats["tool"] += 1
        body = fence(trunc(args, TOOL_ARG_MAX))
        if output:
            body += "\n\n**Result:**\n\n" + fence(trunc(output, TOOL_OUT_MAX))
        self.parts.append(details(f"🔧 <code>{name}</code>", body))

    def note(self, text):
        self.parts.append(f"\n> ℹ️ _{trunc(text, NOTE_MAX)}_\n")

    def render(self) -> str:
        return scrub("\n".join(self.parts))


def fmt_ts(iso_or_epoch) -> str:
    if isinstance(iso_or_epoch, (int, float)):
        d = dt.datetime.fromtimestamp(iso_or_epoch, dt.timezone.utc)
    else:
        d = dt.datetime.fromisoformat(iso_or_epoch.replace("Z", "+00:00"))
    return d.astimezone(dt.timezone(dt.timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d %H:%M IST")


# ---------------------------------------------------------------- Codex
def export_codex(path, title, meta):
    doc = Doc(title, meta)
    pending = {}  # call_id -> (name, args)
    order = []
    def flush_calls():
        for cid in order:
            if cid in pending:
                n, a = pending.pop(cid)
                doc.tool(n, a)
        order.clear()
    for line in open(path, encoding="utf-8"):
        o = json.loads(line)
        p = o.get("payload") or {}
        ts = fmt_ts(o["timestamp"])
        if o["type"] == "compacted":
            doc.note("Context window compacted by Codex — earlier turns summarised.")
            continue
        if o["type"] != "response_item":
            continue
        t = p.get("type")
        if t == "message" and p.get("role") in ("user", "assistant"):
            text = "".join(c.get("text", "") for c in p.get("content", []))
            if p["role"] == "user":
                if text.lstrip().startswith("<"):
                    continue  # injected environment context
                flush_calls(); doc.user(ts, text)
            else:
                flush_calls(); doc.assistant(ts, text)
        elif t == "reasoning":
            s = "\n\n".join(x.get("text", "") for x in p.get("summary", []) if x.get("text"))
            if s:
                doc.thinking(s)
        elif t in ("custom_tool_call", "function_call"):
            args = p.get("input") if t == "custom_tool_call" else p.get("arguments", "")
            pending[p["call_id"]] = (p.get("name", "tool"), args or "")
            order.append(p["call_id"])
        elif t in ("custom_tool_call_output", "function_call_output"):
            out = p.get("output")
            if isinstance(out, list):
                out = "\n".join(x.get("text", "") for x in out if isinstance(x, dict))
            cid = p.get("call_id")
            if cid in pending:
                n, a = pending.pop(cid)
                doc.tool(n, a, out or "")
    flush_calls()
    return doc


# ---------------------------------------------------------- Antigravity
def step_time(payload):
    try:
        for f, w, v in parse(payload) or []:
            if f == 5 and w == "b":
                for f2, w2, v2 in parse(v) or []:
                    if f2 == 1 and w2 == "b":
                        for f3, w3, v3 in parse(v2) or []:
                            if f3 == 1 and w3 == "v":
                                return fmt_ts(v3)
    except Exception:
        pass
    return ""


def export_antigravity(path, title, meta):
    doc = Doc(title, meta)
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    last_ts = ""
    for idx, stype, payload in c.execute("select idx, step_type, step_payload from steps order by idx"):
        payload = payload or b""
        ts = step_time(payload) or last_ts
        last_ts = ts
        fields = [(p, s) for p, s in strings(payload) if p[0] != 5]
        if stype == 14:
            text = next((s for p, s in fields if p == (19, 2)), "")
            if text:
                doc.user(ts, text)
        elif stype == 15:
            for p, s in fields:
                if p == (20, 3) and s.strip():
                    doc.thinking(s)
            text = next((s for p, s in fields if p == (20, 1)), "")
            if text.strip():
                doc.assistant(ts, text)
            name = None
            for p, s in fields:
                if p == (20, 7, 2):
                    name = s
                elif p == (20, 7, 3) and name:
                    doc.tool(name, s)
                    name = None
        elif stype == 132:
            cands = [s for p, s in fields
                     if len(s) > 20 and not s.startswith(("type.googleapis", "file:///", "toolu_"))]
            if cands:
                out = max(cands, key=len)
                doc.parts.append(details("↳ tool result", fence(trunc(out, TOOL_OUT_MAX))))
        elif stype == 101:
            text = next((s for p, s in fields if p == (114, 4, 4)), "")
            if text:
                doc.note("Background task notification: " + text.replace("\n", " "))
        elif stype == 17:
            text = next((s for p, s in fields if p == (24, 3, 2)), "")
            if text:
                doc.note("Model error: " + text.replace("\n", " "))
    return doc


# ---------------------------------------------------------- Claude Code
def export_claude(path, title, meta):
    doc = Doc(title, meta)
    pending = {}
    for line in open(path, encoding="utf-8"):
        o = json.loads(line)
        if o.get("type") not in ("user", "assistant") or o.get("isMeta"):
            continue
        ts = fmt_ts(o["timestamp"]) if o.get("timestamp") else ""
        content = o["message"]["content"]
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for block in content:
            bt = block.get("type")
            if bt == "text" and block["text"].strip():
                txt = block["text"]
                if o["type"] == "user":
                    if txt.lstrip().startswith(("<system-reminder", "<ide_", "<command-", "<local-command")):
                        txt = re.sub(r"<system-reminder>.*?</system-reminder>", "", txt, flags=re.S).strip()
                        if not txt or txt.startswith("<"):
                            continue
                    doc.user(ts, txt)
                else:
                    doc.assistant(ts, txt)
            elif bt == "tool_use":
                inp = block.get("input", {})
                args = inp.get("command") or inp.get("content") or json.dumps(inp, indent=1)
                pending[block["id"]] = (block["name"], args)
            elif bt == "tool_result":
                n, a = pending.pop(block.get("tool_use_id"), ("tool", ""))
                out = block.get("content")
                if isinstance(out, list):
                    out = "\n".join(x.get("text", "") for x in out if isinstance(x, dict))
                doc.tool(n, a, out or "")
    return doc


if __name__ == "__main__":
    cfg = json.load(open(sys.argv[1], encoding="utf-8"))
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    for s in cfg:
        fn = {"codex": export_codex, "antigravity": export_antigravity, "claude": export_claude}[s["kind"]]
        doc = fn(s["src"], s["title"], s["meta"])
        out = os.path.join(outdir, s["out"])
        open(out, "w", encoding="utf-8").write(doc.render())
        print(s["out"], doc.stats, f"{os.path.getsize(out)/1024:.0f} KB")
