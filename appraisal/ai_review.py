"""AI second opinion using the Claude API.

The whole uploaded file goes to the model: PDFs as native documents (text,
tables and photos), spreadsheets and CSVs as a full cell dump plus any
embedded pictures. The model scores the same rubric, adds findings the
rules cannot see (language, plausibility of prices, photo content,
contradictions in prose) and proposes improvements.
"""
from __future__ import annotations

import base64
import json
import re

from .checks import Appraisal, Check
from .config import CRITERIA
from .extract import Extracted

DEFAULT_MODEL = "claude-sonnet-5"

SYSTEM = """You are a senior livelihood programme appraiser for Berendina Development
Services (BDS), a Sri Lankan NGO. You appraise household livelihood grant proposals
written by field officers (CDCs), verified by area managers (ARMs) and approved by
programme management. Be fair, specific and practical. Quote the proposal's own
figures. Never invent facts that are not in the file. Plantation estate households in
Nuwara Eliya are a core target group, so judge realism against upcountry smallholder
conditions. Respond with JSON only."""

PROMPT = """Appraise the attached livelihood proposal.

RUBRIC (100 marks):
{rubric}

AUTOMATED CHECK RESULTS (rule engine; you may disagree, and say why):
{rules}

TASKS
1. Read every part of the file, including narrative text, all tables and photos.
2. Score each criterion out of its maximum.
3. List findings the rule engine missed or got wrong (typos that change meaning,
   copied text, unrealistic prices, what the photos do or do not show, missing
   evidence, contradictions).
4. Give concrete improvement actions, each with the marks it would recover.
5. Recommend one decision: "Approve", "Approve with conditions",
   "Revise and resubmit" or "Not recommended", with conditions if any.

Return exactly this JSON shape:
{{
  "summary": "3-4 sentence plain-English assessment",
  "criteria": [{{"id": "C1", "score": 0.0, "rationale": "..."}}],
  "findings": [{{"criterion": "C2", "severity": "critical|major|minor",
                 "finding": "...", "suggestion": "...", "mark_gain": 0.0}}],
  "disagreements": [{{"check": "C4.3", "comment": "..."}}],
  "photo_observations": "...",
  "recommended_decision": "...",
  "conditions": ["..."]
}}"""


def _rubric_text() -> str:
    return "\n".join(f"{k} {v['name']} ({v['max']}): {v['question']}" for k, v in CRITERIA.items())


def _rules_text(appraisal: Appraisal) -> str:
    rows = []
    for c in appraisal.checks:
        rows.append(f"{c.id} [{c.status}/{c.severity}] {c.title}: {c.finding}")
    rows.append(f"Rule-engine total: {appraisal.total}/100")
    return "\n".join(rows)


def _content_blocks(ex: Extracted, max_images: int = 6) -> list[dict]:
    if ex.file_type == "pdf":
        return [{
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf",
                       "data": base64.standard_b64encode(ex.raw_bytes).decode()},
            "title": ex.file_name,
        }]
    blocks = [{"type": "text",
               "text": f"FILE: {ex.file_name} ({ex.file_type.upper()})\n"
                       f"Sheets: {', '.join(ex.sheet_names) or 'n/a'}\n"
                       "FULL CELL CONTENT (row by row, cells separated by |):\n"
                       + ex.grid_as_text()}]
    for im in [i for i in ex.images if i.data][:max_images]:
        blocks.append({"type": "image", "source": {
            "type": "base64", "media_type": im.media_type,
            "data": base64.standard_b64encode(im.data).decode()}})
    return blocks


def _parse_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("The AI response did not contain JSON.")
    return json.loads(text[start:end + 1])


def run_ai_review(ex: Extracted, appraisal: Appraisal, api_key: str,
                  model: str = DEFAULT_MODEL, max_tokens: int = 6000) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    content = _content_blocks(ex) + [{
        "type": "text",
        "text": PROMPT.format(rubric=_rubric_text(), rules=_rules_text(appraisal)),
    }]
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    data = _parse_json(text)
    data["_model"] = model
    data["_usage"] = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    return data


def merge_ai(appraisal: Appraisal, ai: dict, ai_weight: float = 0.5) -> None:
    """Blend AI criterion scores into the appraisal and add AI findings as checks."""
    for row in ai.get("criteria", []):
        cid = row.get("id")
        if cid in appraisal.criteria:
            cs = appraisal.criteria[cid]
            try:
                score = max(0.0, min(float(row.get("score", 0)), cs.max))
            except (TypeError, ValueError):
                continue
            cs.ai_score = round(score, 2)
            if cs.final_score is None or cs.reviewer_note == "":
                cs.final_score = round((1 - ai_weight) * cs.rule_score + ai_weight * score, 2)
    existing = {c.id for c in appraisal.checks}
    for i, f in enumerate(ai.get("findings", []), start=1):
        cid = f.get("criterion") if f.get("criterion") in CRITERIA else "C2"
        chk_id = f"AI.{i}"
        if chk_id in existing:
            continue
        sev = f.get("severity", "minor") if f.get("severity") in {"critical", "major", "minor"} else "minor"
        try:
            gain = float(f.get("mark_gain") or 0)
        except (TypeError, ValueError):
            gain = 0.0
        chk = Check(chk_id, cid, "AI reviewer finding", weight=0, status="info", severity=sev,
                    finding=f.get("finding", ""), suggestion=f.get("suggestion", ""), source="ai")
        chk.ai_mark_gain = gain  # type: ignore[attr-defined]
        appraisal.checks.append(chk)
        if sev == "critical":
            appraisal.critical.append(chk)
