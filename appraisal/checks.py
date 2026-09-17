"""Rule-based appraisal.

Each check awards part of a criterion's marks and, when it falls short,
explains what was found and exactly how the writer can recover the marks.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date

from .config import (CRITERIA, CRITICAL_CAP, DISTRICT_OPL, NATIONAL_OPL, OPL_AS_OF,
                     Settings, band_for, band_rank)
from .parse import Proposal

# --------------------------------------------------------------------------
# data classes
# --------------------------------------------------------------------------


@dataclass
class Check:
    id: str
    criterion: str
    title: str
    weight: float
    earned: float = 0.0
    status: str = "pass"          # pass | partial | fail | na | info
    severity: str = "minor"       # critical | major | minor | info
    finding: str = ""
    suggestion: str = ""
    source: str = "rules"

    @property
    def shortfall(self) -> float:
        return 0.0 if self.status in {"na", "info"} else max(self.weight - self.earned, 0.0)


@dataclass
class CriterionScore:
    id: str
    name: str
    max: float
    rule_score: float
    ai_score: float | None = None
    final_score: float | None = None
    reviewer_note: str = ""

    @property
    def score(self) -> float:
        if self.final_score is not None:
            return self.final_score
        return self.rule_score


@dataclass
class Appraisal:
    checks: list[Check]
    criteria: dict[str, CriterionScore]
    critical: list[Check] = field(default_factory=list)
    context: dict = field(default_factory=dict)

    @property
    def total(self) -> float:
        return round(sum(c.score for c in self.criteria.values()), 1)

    def decision(self) -> dict:
        label, key, guidance = band_for(self.total)
        capped = False
        if self.critical and band_rank(label) < band_rank(CRITICAL_CAP):
            label, capped = CRITICAL_CAP, True
            key = "revise"
            guidance = ("Marks alone would allow approval, but critical findings must "
                        "be resolved first.")
        return {"label": label, "key": key, "guidance": guidance, "capped": capped}

    def improvement_plan(self) -> list[dict]:
        """Every shortfall, converted to overall marks, largest first."""
        plan = []
        weights = self._criterion_weights()
        for c in self.checks:
            if not c.suggestion:
                continue
            crit = CRITERIA[c.criterion]
            if c.source == "ai":
                gain = float(getattr(c, "ai_mark_gain", 0) or 0)
            elif c.shortfall > 0:
                gain = c.shortfall / (weights.get(c.criterion) or 1) * crit["max"]
            else:
                continue
            plan.append({"check": c.id, "criterion": c.criterion, "criterion_name": crit["name"],
                         "severity": c.severity, "issue": c.finding, "action": c.suggestion,
                         "mark_gain": round(gain, 2), "source": c.source})
        sev = {"critical": 0, "major": 1, "minor": 2, "info": 3}
        plan.sort(key=lambda r: (sev.get(r["severity"], 3), -r["mark_gain"]))
        return plan

    def path_to(self, target: float) -> list[dict]:
        need = target - self.total
        if need <= 0:
            return []
        out, acc = [], 0.0
        rule_rows = [r for r in self.improvement_plan() if r["source"] == "rules"]
        critical = [r for r in rule_rows if r["severity"] == "critical"]
        others = sorted((r for r in rule_rows if r["severity"] != "critical"), key=lambda r: -r["mark_gain"])
        for row in critical:          # always required, whatever their marks
            out.append(row)
            acc += row["mark_gain"]
        for row in others:
            if acc >= need:
                break
            out.append(row)
            acc += row["mark_gain"]
        return out

    def _criterion_weights(self) -> dict[str, float]:
        w: dict[str, float] = {}
        for c in self.checks:
            if c.status not in {"na", "info"}:
                w[c.criterion] = w.get(c.criterion, 0) + c.weight
        return w

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "decision": self.decision(),
            "criteria": {k: {**asdict(v), "score": v.score} for k, v in self.criteria.items()},
            "checks": [asdict(c) for c in self.checks],
            "critical": [c.id for c in self.critical],
            "improvement_plan": self.improvement_plan(),
            "context": self.context,
        }


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def rs(v: float | None) -> str:
    return "not stated" if v is None else f"Rs. {v:,.0f}"


def close(a: float | None, b: float | None, tol: float = 1.0) -> bool:
    if a is None or b is None:
        return False
    return abs(a - b) <= max(tol, abs(b) * 0.001)


def decode_nic(nic: str | None, ref: date) -> dict | None:
    """Sri Lankan NIC: old 9 digits + V/X, new 12 digits."""
    if not nic:
        return None
    nic = nic.strip().upper()
    if re.fullmatch(r"\d{9}[VX]", nic):
        year, days = 1900 + int(nic[:2]), int(nic[2:5])
    elif re.fullmatch(r"\d{12}", nic):
        year, days = int(nic[:4]), int(nic[4:7])
    else:
        return {"valid": False}
    female = days > 500
    if female:
        days -= 500
    if not 1 <= days <= 366:
        return {"valid": False}
    # NIC day numbers assume every year has 29 February
    month_len = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    m, d = 0, days
    while d > month_len[m]:
        d -= month_len[m]
        m += 1
    if m == 1 and d == 29:
        try:
            date(year, 2, 29)
        except ValueError:
            m, d = 2, 1
    born = date(year, m + 1, d)
    age = ref.year - born.year - ((ref.month, ref.day) < (born.month, born.day))
    return {"valid": True, "born": born, "age": age, "gender": "female" if female else "male"}


KEY_NOUNS = {
    "spray": ["spray", "sprayer", "spary", "sprey"],
    "hose": ["hose", "tube", "pipe"],
    "motor": ["motor", "pump", "water pump"],
    "fence": ["fence", "fencing"],
    "tank": ["tank", "barrel"],
    "sprinkler": ["sprinkler", "drip", "irrigation"],
    "tiller": ["tiller", "tractor"],
    "polytunnel": ["polytunnel", "poly tunnel", "greenhouse", "net house"],
    "tools": ["mammoty", "fork", "knife", "tools", "hoe"],
}


def nouns_in(text: str) -> set[str]:
    t = (text or "").lower()
    return {k for k, syns in KEY_NOUNS.items() if any(s in t for s in syns)}


def word_count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text or "", re.I))


# --------------------------------------------------------------------------
# the appraisal
# --------------------------------------------------------------------------
def appraise(p: Proposal, settings: Settings | None = None, today: date | None = None) -> Appraisal:
    s = settings or Settings()
    ref = p.prepared_date or today or date.today()
    checks: list[Check] = []
    add = checks.append
    text_all = " ".join([p.narrative, p.overview, " ".join(p.goals),
                         " ".join(r + " " + m for r, m in p.risks)])

    cur, exp = p.current, p.expected
    members = len(p.members) or cur.members

    # ======================= C1 eligibility and vulnerability ===============
    opl = s.poverty_line or DISTRICT_OPL.get(p.district or "", NATIONAL_OPL)
    opl_src = ("reviewer setting" if s.poverty_line else
               f"{p.district} district OPL, {OPL_AS_OF}" if p.district in DISTRICT_OPL
               else f"national OPL, {OPL_AS_OF}")
    pc = cur.per_capita or (cur.total_income / members if cur.total_income and members else None)
    c = Check("C1.1", "C1", "Per-capita income against the poverty line", 6)
    if pc is None:
        c.status, c.severity = "fail", "major"
        c.finding = "Current per-capita income could not be established."
        c.suggestion = "Complete section 2.2 with every income source, amounts and household size."
    else:
        ratio = pc / opl
        c.earned = 6 if ratio <= 0.5 else 4.5 if ratio <= 1 else 2 if ratio <= 1.5 else 0
        c.status = "pass" if c.earned == 6 else "partial" if c.earned else "fail"
        c.finding = (f"Per-capita income {rs(pc)} is {ratio:.0%} of the poverty line "
                     f"({rs(opl)}, {opl_src}).")
        if c.earned < 6:
            c.severity = "major" if ratio > 1 else "minor"
            c.suggestion = ("Confirm the household is within the programme's target group; "
                            "document any hidden vulnerability (debt, disability, female-headed "
                            "household) if income is above the line.")
    add(c)

    c = Check("C1.2", "C1", "Evidence of economic stress", 3)
    if cur.total_income is not None and cur.total_expense is not None:
        gap = cur.total_expense - cur.total_income
        if gap > 0:
            c.earned = 3
            c.finding = (f"Monthly spending exceeds income by {rs(gap)}. The proposal does not "
                         "say how this gap is financed." if not re.search(r"debt|loan|borrow|pawn|credit", text_all, re.I)
                         else f"Monthly deficit of {rs(gap)} is explained.")
            if "not say" in c.finding:
                c.status, c.earned = "partial", 2
                c.suggestion = ("State how the monthly deficit is covered (loans, pawning, "
                                "credit at shops) - this also strengthens the case for support.")
        else:
            c.earned = 2
            c.status = "partial"
            c.finding = f"Household reports a monthly surplus of {rs(-gap)}."
            c.suggestion = "Explain the vulnerability that justifies support despite the surplus."
    else:
        c.status, c.finding = "fail", "Household income or expenditure totals are missing."
        c.suggestion = "Fill in the totals in section 2.2."
    add(c)

    c = Check("C1.3", "C1", "Family profile complete", 3)
    if p.members:
        filled = sum(1 for m in p.members if m.name and m.age is not None and m.relationship and m.health)
        c.earned = 3 * filled / len(p.members)
        c.status = "pass" if filled == len(p.members) else "partial"
        c.finding = f"{filled} of {len(p.members)} household members have name, age, relationship and health recorded."
        if c.status != "pass":
            c.suggestion = "Record age, relationship and health status for every household member."
    else:
        c.status, c.severity = "fail", "major"
        c.finding = "No family member table was found."
        c.suggestion = "Complete the family details table."
    add(c)

    c = Check("C1.4", "C1", "Household size consistent", 3)
    counts = {k: v for k, v in {"family table": len(p.members) or None,
                                "income table": cur.members,
                                "narrative": p.members_narrative}.items() if v}
    if len(counts) >= 2:
        if len({int(v) for v in counts.values()}) == 1:
            c.earned, c.finding = 3, f"Household size is {int(next(iter(counts.values())))} everywhere it is stated."
        else:
            c.status, c.severity = "fail", "major"
            c.finding = "Household size differs: " + ", ".join(f"{k} {int(v)}" for k, v in counts.items()) + "."
            c.suggestion = "Use one verified household size throughout; per-capita figures depend on it."
    else:
        c.status, c.earned = "partial", 1.5
        c.finding = "Household size is stated in only one place."
        c.suggestion = "State household size in the narrative and the income table."
    add(c)

    # ======================= C2 completeness and data accuracy ==============
    nic = decode_nic(p.nic, ref)
    c = Check("C2.1", "C2", "NIC matches stated age and gender", 4)
    female_title = (p.title or "").lower() in {"ms", "mrs", "miss"}
    if not nic:
        c.status, c.severity = "fail", "major"
        c.finding = "No NIC number found."
        c.suggestion = "Record the beneficiary's NIC number in Personal Detail."
    elif not nic["valid"]:
        c.status, c.severity = "fail", "critical"
        c.finding = f"NIC '{p.nic}' is not a valid Sri Lankan NIC format."
        c.suggestion = "Re-check the NIC against the card and correct it."
    else:
        c.earned = 1
        notes = [f"NIC indicates a {nic['gender']} born {nic['born']:%d %b %Y} (age {nic['age']} on {ref:%d %b %Y})."]
        if p.title:
            if (nic["gender"] == "female") == female_title:
                c.earned += 1
            else:
                notes.append(f"The title '{p.title}.' does not match the NIC gender.")
        else:
            c.earned += 0.5
        if p.age_personal is not None:
            if abs(p.age_personal - nic["age"]) <= 1:
                c.earned += 2
            else:
                notes.append(f"Personal Detail age {int(p.age_personal)} does not match the NIC.")
                c.severity = "critical"
        c.status = "pass" if c.earned >= 4 else "fail" if c.severity == "critical" else "partial"
        c.finding = " ".join(notes)
        if c.status != "pass":
            c.suggestion = "Verify identity details against the NIC card and correct the mismatch."
    add(c)

    c = Check("C2.2", "C2", "Age consistent across sections", 3)
    ages = {k: v for k, v in {
        "narrative": p.age_narrative, "personal detail": p.age_personal,
        "family table": p.members[0].age if p.members else None,
        "NIC": float(nic["age"]) if nic and nic.get("valid") else None}.items() if v is not None}
    if len(ages) >= 2:
        if max(ages.values()) - min(ages.values()) <= 1:
            c.earned, c.finding = 3, f"Beneficiary age is consistent ({int(min(ages.values()))})."
        else:
            c.status, c.severity = "fail", "major"
            c.finding = "Beneficiary age differs: " + ", ".join(f"{k} {int(v)}" for k, v in ages.items()) + "."
            c.suggestion = ("Correct the age in every section to match the NIC"
                            + (f" ({nic['age']})" if nic and nic.get("valid") else "") + ".")
    else:
        c.status, c.earned = "partial", 1.5
        c.finding = "Age is stated in fewer than two places, so it could not be cross-checked."
        c.suggestion = "State the age in the narrative and Personal Detail."
    add(c)

    c = Check("C2.3", "C2", "Consistent gender references", 2)
    he = word_count(p.narrative, r"\b(he|his|him)\b")
    she = word_count(p.narrative, r"\b(she|her|hers)\b")
    target_female = female_title or (nic and nic.get("gender") == "female")
    wrong = he if target_female else she
    if not p.narrative:
        c.status, c.finding = "na", "No narrative to check."
    elif wrong == 0:
        c.earned, c.finding = 2, "Pronouns in the narrative match the beneficiary."
    else:
        c.status = "fail"
        c.finding = (f"The narrative refers to a {'female' if target_female else 'male'} beneficiary "
                     f"but uses '{'he/his' if target_female else 'she/her'}' {wrong} time(s). "
                     "This often signals text copied from another proposal.")
        c.suggestion = "Rewrite the narrative for this beneficiary and correct every pronoun."
    add(c)

    c = Check("C2.4", "C2", "Location consistent throughout", 3)
    div, est = p.locations.get("division", set()), p.locations.get("estate", set())
    problems = []
    if len(div) > 1:
        problems.append("divisions " + ", ".join(sorted(div)))
    if len(est) > 1:
        problems.append("estates " + ", ".join(sorted(est)))
    if not div and not est and not p.address:
        c.status, c.earned = "partial", 1
        c.finding = "No estate, division or village could be identified."
        c.suggestion = "State the full address with GN division or estate division."
    elif problems:
        c.status, c.severity = "fail", "critical"
        c.finding = ("The proposal names more than one location (" + "; ".join(problems) +
                     "). Part of the text may belong to a different beneficiary.")
        c.suggestion = ("Confirm the correct location and rewrite every section that names "
                        "another estate or division.")
    else:
        c.earned, c.finding = 3, "All location references agree."
    add(c)

    c = Check("C2.5", "C2", "Contact number valid", 1)
    digits = re.sub(r"\D", "", p.contact or "")
    if not digits:
        c.status, c.finding = "fail", "No contact number."
        c.suggestion = "Add a working contact number."
    elif (len(digits) == 10 and digits.startswith("0")) or (len(digits) == 11 and digits.startswith("94")):
        c.earned, c.finding = 1, "Contact number format is valid."
    else:
        c.status = "fail"
        hint = " It looks like the leading 0 is missing." if len(digits) == 9 else ""
        c.finding = f"Contact number '{p.contact}' is not a valid 10-digit Sri Lankan number.{hint}"
        c.suggestion = "Correct the phone number (10 digits, e.g. 07X XXX XXXX)."
    add(c)

    c = Check("C2.6", "C2", "Key fields filled", 2)
    missing = [label for label, v in {
        "period involved / experience": p.period_involved,
        "market": p.market, "product/service": p.product or p.livelihood,
        "business address": p.business_address, "requested support": p.requested_support,
    }.items() if not v]
    c.earned = max(0.0, 2 - 0.5 * len(missing))
    if missing:
        c.status = "partial" if c.earned else "fail"
        c.finding = "Missing: " + ", ".join(missing) + "."
        c.suggestion = ("Fill in " + ", ".join(missing) +
                        " (section 1 asks how long the family has been in this livelihood).")
    else:
        c.finding = "All key fields are filled."
    add(c)

    # ======================= C3 livelihood viability and market =============
    ov = p.overview or ""
    c = Check("C3.1", "C3", "Livelihood overview is specific to this family", 5)
    crops = re.findall(r"\b(carrot|leeks?|cabbage|potato|beans?|beetroot|radish|knol ?khol|lettuce|"
                       r"cauliflower|broccoli|tomato|capsicum|strawberr\w*|pepper|pumpkin|onion|"
                       r"garlic|chilli|brinjal|okra|cucumber|paddy|tea|mushroom|poultry|goat|cow|milk)\b",
                       ov + " " + p.narrative, re.I)
    land = re.search(r"\b(acres?|perch(es)?|hectares?|\bha\b|sq\.?\s*ft)\b", ov + p.narrative, re.I)
    exp_yrs = re.search(r"\d+\s*years?\s*(of\s*)?(experience|in (this|cultivation|farming))", text_all, re.I)
    prod = re.search(r"\b(kg|yield|harvest|season|maha|yala|per month|per week)\b", ov, re.I)
    parts = {"crops named": bool(crops), "land extent": bool(land),
             "years of experience": bool(exp_yrs), "production or season detail": bool(prod)}
    c.earned = 1.5 * parts["crops named"] + 1.5 * parts["land extent"] + parts["years of experience"] + parts["production or season detail"]
    generic = len(ov) > 600 and not any(parts.values())
    c.status = "pass" if c.earned >= 5 else "partial" if c.earned else "fail"
    c.severity = "major" if c.earned < 2.5 else "minor"
    miss = [k for k, v in parts.items() if not v]
    c.finding = ("The overview is general text about cultivation and says little about this family's farm. "
                 if generic else "") + (("Missing: " + ", ".join(miss) + ".") if miss else "Overview is specific.")
    if miss:
        c.suggestion = ("Replace generic text with facts about this farm: crops grown, land extent "
                        "(perches/acres), years farming, seasons and expected yields.")
    add(c)

    c = Check("C3.2", "C3", "Market linkage is specific", 4)
    mk = re.findall(r"\b(buyer|collector|wholesale|economic cent(er|re)|dambulla|keppetipola|welimada|"
                    r"supermarket|cargills|keells|contract|middleman|pola|fair|per kg|/kg|rs\.? ?\d+ ?per)\b",
                    text_all, re.I)
    c.earned = 1 if p.market else 0
    c.earned += 3 if len(mk) >= 2 else 1.5 if mk else 0
    c.status = "pass" if c.earned >= 4 else "partial" if c.earned else "fail"
    c.severity = "major" if c.earned <= 1 else "minor"
    c.finding = (f"Market is given as '{p.market}'" if p.market else "No market stated") + (
        " with no named buyer, sales channel or price." if not mk else f"; market evidence: {', '.join(sorted({m[0].lower() for m in mk}))}.")
    if c.earned < 4:
        c.suggestion = ("Name where and to whom produce is sold (e.g. economic centre, collector, "
                        "supermarket), how often, and the current farm-gate price per kg.")
    add(c)

    sales_cur, sales_fy = p.annual_value("sales", 0), p.annual_value("sales", 1)
    c = Check("C3.3", "C3", "Sales projection is built up from volume and price", 3)
    basis = re.search(r"\b(kg|yield|price per|per kg|harvests?)\b", p.full_text or text_all, re.I)
    c.earned = 2 if basis else 0
    if p.annual_sale is not None and sales_fy is not None:
        c.earned += 1 if close(p.annual_sale, sales_fy) else 0
    c.status = "pass" if c.earned >= 3 else "partial" if c.earned else "fail"
    c.finding = ("Annual sales are stated as a lump sum with no quantity, price or season breakdown."
                 if not basis else "Sales are supported by volume/price detail.")
    if p.annual_sale is not None and sales_fy is not None and not close(p.annual_sale, sales_fy):
        c.finding += f" Livelihood Detail sales ({rs(p.annual_sale)}) differ from section 6 ({rs(sales_fy)})."
    if c.earned < 3:
        c.suggestion = ("Add a small table: crop, extent, harvests per year, yield per harvest (kg), "
                        "price per kg, and resulting sales.")
    add(c)

    c = Check("C3.4", "C3", "Goals are measurable and match the projections", 3)
    pct_goal = None
    for g in p.goals:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", g)
        if m and re.search(r"income", g, re.I):
            pct_goal = float(m.group(1)) / 100
    culti_cur = next((i.amount for i in cur.incomes if i.amount and re.search(r"cultiv|farm|livelihood", i.source, re.I)), None)
    culti_exp = next((i.amount for i in exp.incomes if i.amount and re.search(r"cultiv|farm|livelihood", i.source, re.I)), None)
    proj_livelihood = (culti_exp / culti_cur - 1) if culti_cur and culti_exp else None
    proj_house = (exp.total_income / cur.total_income - 1) if cur.total_income and exp.total_income else None
    if not p.goals:
        c.status, c.severity = "fail", "major"
        c.finding = "No goals stated."
        c.suggestion = "Add 2-3 measurable goals (income, savings, production) with target dates."
    elif pct_goal is None:
        c.status, c.earned = "partial", 1.5
        c.finding = "Goals are stated but none sets a measurable income target."
        c.suggestion = "Make at least one goal measurable, e.g. 'raise monthly livelihood income to Rs. X by month 12'."
    else:
        proj = proj_livelihood if proj_livelihood is not None else proj_house
        if proj is not None and (proj > pct_goal * 2 + 0.1 or proj < pct_goal / 2):
            c.status, c.severity = "fail", "major"
            c.finding = (f"The goal is a {pct_goal:.0%} income increase, but the projections show "
                         + (f"livelihood income rising {proj_livelihood:.0%}" if proj_livelihood is not None else "")
                         + (f" and household income rising {proj_house:.0%}" if proj_house is not None else "") + ".")
            c.suggestion = ("Align the goal and the projections: either justify the larger increase "
                            "or revise the projections to the stated target.")
        else:
            c.earned, c.finding = 3, "Goals are measurable and consistent with the projections."
    add(c)

    # ======================= C4 financial soundness =========================
    arith = []  # (label, stated, computed)
    for label, b in (("current", cur), ("expected", exp)):
        if b.incomes and b.total_income is not None:
            arith.append((f"{label} household income total", b.total_income, sum(i.amount or 0 for i in b.incomes)))
        if b.expenses and b.total_expense is not None:
            arith.append((f"{label} household expenditure total", b.total_expense, sum(b.expenses.values())))
        n = b.members or members
        if b.per_capita is not None and b.total_income and n:
            arith.append((f"{label} per-capita income", b.per_capita, b.total_income / n))
    if exp.per_capita_change is not None and exp.per_capita and cur.per_capita:
        arith.append(("change in per-capita income", exp.per_capita_change, exp.per_capita - cur.per_capita))
    expense_keys = ["seeds", "raw_material", "labour", "land_prep", "fertilizer", "chemicals",
                    "machine_rent", "depreciation", "marketing", "administration", "overhead"]
    for i, lab in ((0, "current"), (1, "year-1")):
        items = [p.annual_value(k, i) for k in expense_keys if p.annual_value(k, i) is not None]
        te, ti, pr = (p.annual_value("total_expense", i), p.annual_value("total_income", i),
                      p.annual_value("profit", i))
        if items and te is not None:
            arith.append((f"{lab} annual expenditure total", te, sum(items)))
        if te is not None and ti is not None and pr is not None:
            arith.append((f"{lab} annual profit", pr, ti - te))
    for it in p.equipment:
        if it.qty and it.unit_price and it.total is not None:
            arith.append((f"{it.name} line total", it.total, it.qty * it.unit_price))
    if p.equipment and p.equipment_total.get("total") is not None:
        arith.append(("equipment list total", p.equipment_total["total"], sum(i.total or 0 for i in p.equipment)))
    if p.equipment and p.equipment_total.get("bds") is not None:
        arith.append(("BDS contribution total", p.equipment_total["bds"], sum(i.bds or 0 for i in p.equipment)))
    ti = p.investment.get("total_investment", {})
    fx, wc = p.investment.get("fixed_total", {}), p.investment.get("working_capital_total", {})
    if ti.get("total") and fx.get("total") is not None and wc.get("total") is not None:
        arith.append(("total investment", ti["total"], fx["total"] + wc["total"] + (p.investment.get("prior_total", {}).get("total") or 0)))
    pct = p.investment.get("percentage", {})
    if ti.get("total") and ti.get("grant") is not None and pct.get("grant") is not None:
        arith.append(("grant share %", pct["grant"], ti["grant"] / ti["total"] * 100))

    errors = [(l, st, co) for l, st, co in arith if not close(st, co, tol=1.0)]
    c = Check("C4.1", "C4", "Arithmetic is correct", 5)
    if not arith:
        c.status, c.severity = "fail", "major"
        c.finding = "No totals could be verified."
        c.suggestion = "Complete totals in sections 2, 5, 6 and 7."
    else:
        c.earned = 5 * (len(arith) - len(errors)) / len(arith)
        if errors:
            material = [e for e in errors if abs(e[1] - e[2]) > max(abs(e[2]) * s.material_error_ratio, 1000)]
            c.status = "fail" if material else "partial"
            c.severity = "critical" if material else "minor"
            c.finding = f"{len(errors)} of {len(arith)} totals do not add up: " + "; ".join(
                f"{l} stated {st:,.2f} vs computed {co:,.2f}" for l, st, co in errors[:6]) + "."
            c.suggestion = "Recalculate and correct the listed totals (use the Excel template's formulas)."
        else:
            c.finding = f"All {len(arith)} verifiable totals add up."
    add(c)

    c = Check("C4.2", "C4", "Household and business tables agree", 4)
    links = []
    pr0, pr1 = p.annual_value("profit", 0), p.annual_value("profit", 1)
    if culti_cur is not None and pr0 is not None:
        links.append(("current livelihood income x 12 = current annual profit", culti_cur * 12, pr0))
    if culti_exp is not None and pr1 is not None:
        links.append(("expected livelihood income x 12 = year-1 annual profit", culti_exp * 12, pr1))
    if p.annual_profit is not None and pr1 is not None:
        links.append(("Livelihood Detail profit = section 6 year-1 profit", p.annual_profit, pr1))
    grant_eq = p.equipment_total.get("bds")
    if grant_eq is not None and ti.get("grant") is not None:
        links.append(("equipment list BDS total = investment grant", grant_eq, ti["grant"]))
    bad = [l for l in links if not close(l[1], l[2], tol=12)]
    if not links:
        c.status, c.earned = "partial", 2
        c.finding = "Tables could not be cross-checked."
        c.suggestion = "Make sure sections 2, 5, 6 and 7 are all completed."
    else:
        c.earned = 4 * (len(links) - len(bad)) / len(links)
        c.status = "pass" if not bad else "partial"
        c.finding = (f"All {len(links)} cross-table links agree." if not bad else
                     "Mismatch: " + "; ".join(f"{l[0]} ({l[1]:,.0f} vs {l[2]:,.0f})" for l in bad) + ".")
        if bad:
            c.severity = "major"
            c.suggestion = "Make the household income tables, section 6 and the equipment list tell the same story."
    pc_lab = p.annual_value("per_capita", 1)
    if pc_lab and exp.per_capita and not close(pc_lab, exp.per_capita, tol=5):
        c.finding += (f" Note: section 6 shows 'per-capita income' {pc_lab:,.2f} (livelihood profit only) "
                      f"while section 2.3 shows {exp.per_capita:,.2f}; relabel to avoid confusion.")
    add(c)

    growth = (sales_fy / sales_cur - 1) if sales_cur and sales_fy is not None else None
    justified = bool(re.search(r"\b(extend|expan|additional land|new land|more land|acre|perch|yield|"
                               r"irrigat|second season|two seasons|reduce (loss|damage))", text_all, re.I))
    c = Check("C4.3", "C4", "Sales growth is realistic", 4)
    if growth is None:
        c.status = "na" if sales_cur == 0 else "partial"
        c.earned = 2
        c.finding = ("New livelihood: no current sales to compare." if sales_cur == 0
                     else "Current or year-1 sales are missing.")
        c.suggestion = "" if sales_cur == 0 else "Complete current and year-1 sales in section 6."
    else:
        if growth <= s.sales_growth_ok:
            c.earned = 4
        elif growth <= s.sales_growth_caution:
            c.earned = 3
        elif growth <= s.sales_growth_limit:
            c.earned = 1.5
        else:
            c.earned = 0
        if justified and c.earned < 4:
            c.earned = min(4, c.earned + 1)
        c.status = "pass" if c.earned == 4 else "partial" if c.earned else "fail"
        c.finding = f"Sales rise {growth:.0%} in year 1 ({rs(sales_cur)} to {rs(sales_fy)})" + (
            "." if c.earned == 4 else ", without an explanation of what drives the increase." if not justified
            else "; drivers are mentioned but not quantified.")
        if c.earned < 4:
            c.severity = "major" if growth > s.sales_growth_limit else "minor"
            c.suggestion = ("Explain and quantify the growth (extra extent, extra season, reduced crop "
                            f"loss, better price) or reduce year-1 sales to a growth of about {s.sales_growth_caution:.0%} or less.")
    add(c)

    te0, te1 = p.annual_value("total_expense", 0), p.annual_value("total_expense", 1)
    c = Check("C4.4", "C4", "Costs move with production", 3)
    if growth is None or te0 is None or te1 is None or te0 == 0:
        c.status, c.earned, c.finding = "partial", 1.5, "Cost trend could not be tested."
        c.suggestion = "Complete current and year-1 expenditure in section 6."
    else:
        cost_growth = te1 / te0 - 1
        notes = []
        if growth > 0.10 and cost_growth < 0:
            c.earned = 0
            notes.append(f"Sales rise {growth:.0%} while total costs fall {abs(cost_growth):.0%}.")
        elif growth > 0.10 and cost_growth < growth / 2:
            c.earned = 1.5
            notes.append(f"Costs rise only {cost_growth:.0%} against {growth:.0%} sales growth.")
        else:
            c.earned = 3
        flat_inputs = [label for key, label in (("seeds", "seeds"), ("fertilizer", "fertilizer"),
                                                 ("chemicals", "chemicals"))
                       if growth > 0.25 and p.annual_value(key, 0)
                       and p.annual_value(key, 1) is not None
                       and p.annual_value(key, 1) <= p.annual_value(key, 0)]
        if flat_inputs:
            notes.append(", ".join(flat_inputs) + " costs do not increase with production")
        if p.annual_value("marketing", 1) in (0, None) and growth > 0.25:
            notes.append("no marketing or transport cost is budgeted")
        lp0, lp1 = p.annual_value("land_prep", 0), p.annual_value("land_prep", 1)
        if lp0 and lp1 is not None and lp1 < lp0 * 0.75:
            notes.append(f"land preparation drops from {rs(lp0)} to {rs(lp1)} without explanation")
        c.status = "pass" if c.earned == 3 and len(notes) == 0 else "partial" if c.earned else "fail"
        if c.earned == 3 and notes:
            c.earned = 2
        c.severity = "major" if c.earned == 0 else "minor"
        c.finding = " ".join([notes[0]] + ([("Also: " + "; ".join(notes[1:]) + ".")] if len(notes) > 1 else [])) if notes else "Costs scale sensibly with production."
        if c.status != "pass":
            c.suggestion = ("Scale input, labour and transport/marketing costs to the higher production, "
                            "and explain any cost that falls.")
    add(c)

    c = Check("C4.5", "C4", "Profit margin is plausible", 2)
    if sales_fy and pr1 is not None:
        m1 = pr1 / sales_fy
        m0 = (pr0 / sales_cur) if sales_cur and pr0 is not None else None
        c.earned = 2 if m1 <= s.margin_ok else 1 if m1 <= s.margin_limit else 0
        c.status = "pass" if c.earned == 2 else "partial" if c.earned else "fail"
        c.finding = f"Year-1 margin is {m1:.0%}" + (f" (current {m0:.0%})." if m0 is not None else ".")
        if c.earned < 2:
            c.severity = "major" if c.earned == 0 else "minor"
            c.suggestion = (f"A margin above {s.margin_ok:.0%} needs evidence; show the cost build-up "
                            "or use a more conservative profit.")
    else:
        c.status, c.earned, c.finding = "fail", 0, "Year-1 sales or profit missing."
        c.suggestion = "Complete section 6."
    add(c)

    c = Check("C4.6", "C4", "Household budget balances after support", 2)
    if exp.total_income is not None and exp.total_expense is not None:
        surplus = exp.total_income - exp.total_expense
        c.earned = 2 if surplus >= 0 else 0
        c.status = "pass" if surplus >= 0 else "fail"
        c.finding = f"Expected monthly {'surplus' if surplus >= 0 else 'deficit'} of {rs(abs(surplus))}."
        if surplus < 0:
            c.severity, c.suggestion = "major", "Show how the household will cover the remaining deficit."
    else:
        c.status, c.finding = "fail", "Expected household income or expenditure missing."
        c.suggestion = "Complete section 2.3."
    add(c)

    # ======================= C5 relevance of requested support ==============
    req = nouns_in(p.requested_support or "")
    eq_nouns = {it.name: nouns_in(it.name) for it in p.equipment}
    c = Check("C5.1", "C5", "Equipment list matches the stated need", 3)
    if not p.equipment:
        c.status, c.severity = "fail", "critical"
        c.finding = "No equipment or input list found."
        c.suggestion = "List every item with quantity, unit price and contribution."
    elif not req:
        c.status, c.earned = "partial", 1.5
        c.finding = "The requested-support line is empty or unclear, so the list could not be matched."
        c.suggestion = "State in section 2.4 exactly what support the family asked for."
    else:
        matched = [n for n, ns in eq_nouns.items() if ns & req]
        unrequested = [n for n, ns in eq_nouns.items() if not ns & req]
        dropped = req - set().union(*eq_nouns.values()) if eq_nouns else req
        c.earned = 3 * len(matched) / len(p.equipment)
        c.status = "pass" if not unrequested and not dropped else "partial"
        bits = []
        if unrequested:
            bits.append("not in the stated request: " + ", ".join(unrequested))
        if dropped:
            bits.append("requested but not provided: " + ", ".join(sorted(dropped)))
        c.finding = (f"Stated request: '{p.requested_support}'. " + ("; ".join(bits).capitalize() + "." if bits else "All items match."))
        if bits:
            c.severity = "major"
            c.suggestion = ("Update section 2.4 so the request and the equipment list agree, and explain "
                            "why any item was added or dropped.")
    add(c)

    c = Check("C5.2", "C5", "Each item is justified", 3)
    story = " ".join([p.narrative, p.overview, " ".join(p.goals), " ".join(m for _, m in p.risks), " ".join(r for r, _ in p.risks)])
    story_n = nouns_in(story)
    if re.search(r"wild|animal|elephant|boar|pig|monkey|porcupine|cattle|theft", story, re.I):
        story_n.add("fence")
    if re.search(r"water|irrigat|dry|drought", story, re.I):
        story_n |= {"hose", "motor", "sprinkler"}
    if re.search(r"pest|disease", story, re.I):
        story_n.add("spray")
    if p.equipment:
        justified_items = [n for n, ns in eq_nouns.items() if ns & story_n]
        c.earned = 3 * len(justified_items) / len(p.equipment)
        unjust = [n for n in eq_nouns if n not in justified_items]
        c.status = "pass" if not unjust else "partial" if justified_items else "fail"
        c.finding = ("Every item is linked to a need in the text." if not unjust else
                     "No explanation of how these items raise income or reduce loss: " + ", ".join(unjust) + ".")
        if unjust:
            c.severity = "major" if len(unjust) == len(p.equipment) else "minor"
            c.suggestion = ("For each item, add one sentence on the problem it solves (e.g. animal damage, "
                            "manual watering time, pest loss) and its effect on yield or cost.")
    else:
        c.status, c.finding = "na", "No items to justify."
    add(c)

    c = Check("C5.3", "C5", "Item list is complete and orderly", 1)
    nos = [it.no for it in p.equipment if it.no and it.no.isdigit()]
    if nos and [int(n) for n in nos] != list(range(1, len(nos) + 1)):
        c.status = "fail"
        c.finding = f"Item numbers run {', '.join(nos)}; an item may have been removed without updating the proposal."
        c.suggestion = "Renumber the list and confirm nothing was dropped unintentionally."
    else:
        c.earned, c.finding = 1, "Item list is numbered in sequence."
    add(c)

    c = Check("C5.4", "C5", "Grant amount reconciles", 2)
    if grant_eq is not None and ti.get("grant") is not None:
        c.earned = 2 if close(grant_eq, ti["grant"]) else 0
        c.status = "pass" if c.earned else "fail"
        c.finding = f"Grant requested {rs(grant_eq)}" + ("" if c.earned else f" but investment table shows {rs(ti['grant'])}") + "."
        if not c.earned:
            c.severity, c.suggestion = "critical", "Reconcile the grant amount between sections 5 and 7."
        if s.max_grant and grant_eq > s.max_grant:
            c.earned, c.status, c.severity = 0, "fail", "critical"
            c.finding += f" This exceeds the grant ceiling of {rs(s.max_grant)}."
            c.suggestion = "Reduce the request to within the ceiling or obtain a documented exception."
    else:
        c.status, c.earned = "partial", 1
        c.finding = "Grant amount could not be reconciled."
        c.suggestion = "Complete the BDS contribution column and the investment table."
    add(c)

    c = Check("C5.5", "C5", "Prices are backed by quotations", 1)
    if re.search(r"quotation|quote|invoice|price list", " ".join([story, p.requested_support or ""]), re.I):
        c.earned, c.finding = 1, "Quotations are referenced."
    else:
        c.status = "fail"
        c.finding = "No quotations are referenced for the equipment prices."
        c.suggestion = "Attach or reference at least one supplier quotation per item (three for items above the procurement threshold)."
    add(c)

    # ======================= C6 contribution and sustainability =============
    own = (ti.get("own") or 0) + (ti.get("own_proposed") or 0)
    c = Check("C6.1", "C6", "Beneficiary contribution is sufficient", 4)
    if ti.get("total"):
        share = own / ti["total"]
        c.earned = 4 if share >= s.min_beneficiary_share else 2 if share >= s.min_beneficiary_share * 0.6 else 0
        c.status = "pass" if c.earned == 4 else "partial" if c.earned else "fail"
        c.finding = f"Beneficiary contributes {rs(own)} ({share:.0%}) of {rs(ti['total'])} total investment."
        if c.earned < 4:
            c.suggestion = f"Raise the family's contribution (cash, land preparation, labour) to at least {s.min_beneficiary_share:.0%}."
    else:
        c.status, c.finding = "fail", "Total investment not stated."
        c.suggestion = "Complete section 5."
    add(c)

    c = Check("C6.2", "C6", "Own contribution is itemised", 2)
    other_total = sum(it.other or 0 for it in p.equipment)
    if ti.get("own"):
        if other_total >= ti["own"] - 1 or re.search(r"own (equipment|tools)|already (has|owns)", story, re.I):
            c.earned, c.finding = 2, "Own asset contribution is itemised."
        else:
            c.status = "fail"
            c.finding = (f"Section 5 counts {rs(ti['own'])} of own equipment, but the equipment list "
                         "shows no beneficiary contribution and the text does not say what it is.")
            c.suggestion = "Name the equipment the family already owns and its value, or remove it from section 5."
    else:
        c.earned, c.finding = 2, "No own fixed-asset contribution claimed."
    add(c)

    c = Check("C6.3", "C6", "Savings plan is quantified", 2)
    save_goal = [g for g in p.goals if re.search(r"sav", g, re.I)]
    if save_goal and any(re.search(r"\d", g) for g in save_goal):
        c.earned, c.finding = 2, "Savings goal has a target."
    elif save_goal:
        c.status, c.earned = "partial", 1
        surplus = (exp.total_income or 0) - (exp.total_expense or 0)
        c.finding = "Savings is a goal, but no amount or frequency is set" + (
            f" (projected surplus {rs(surplus)} a month)." if surplus > 0 else ".")
        c.suggestion = "Set a monthly savings amount and where it will be kept (e.g. Rs. X per month in a Samurdhi/bank account)."
    else:
        c.status = "fail"
        c.finding = "No savings plan."
        c.suggestion = "Add a savings goal with a monthly amount to fund repairs and next-season inputs."
    add(c)

    c = Check("C6.4", "C6", "Asset replacement is provided for", 2)
    dep = p.annual_value("depreciation", 1)
    if dep:
        c.earned, c.finding = 2, f"Year-1 depreciation of {rs(dep)} is included."
    else:
        c.status = "fail"
        c.finding = "No depreciation is included for the new assets."
        c.suggestion = "Include depreciation (asset cost / useful life) in section 6."
    add(c)

    # ======================= C7 risk ========================================
    c = Check("C7.1", "C7", "Enough risks identified", 2)
    n = len(p.risks)
    c.earned = 2 * min(n, 4) / 4
    c.status = "pass" if n >= 4 else "partial" if n else "fail"
    c.finding = f"{n} risk(s) listed."
    if n < 4:
        c.suggestion = "List at least four material risks."
    add(c)

    cats = {
        "market price": r"price|market|demand|buyer",
        "weather": r"flood|drought|rain|frost|landslide|weather|climat",
        "pest or disease": r"pest|disease|insect|fung",
        "wildlife or theft": r"wild|animal|boar|monkey|porcupine|theft|stray",
        "equipment failure": r"equipment|breakdown|repair|maintenance|motor|machine",
        "soil or water": r"soil|fertility|water|irrigation",
        "health or labour": r"health|illness|labou?r",
    }
    rtxt = " ".join(r for r, _ in p.risks)
    covered = [k for k, pat in cats.items() if re.search(pat, rtxt, re.I)]
    expected_missing = [k for k in ("market price", "weather", "wildlife or theft", "equipment failure") if k not in covered]
    c = Check("C7.2", "C7", "Risks fit this livelihood", 3)
    c.earned = 3 * min(len(covered), 4) / 4
    c.status = "pass" if len(covered) >= 4 else "partial" if covered else "fail"
    c.finding = "Covers: " + (", ".join(covered) or "none") + "." + (
        f" Not covered: {', '.join(expected_missing)}." if expected_missing else "")
    if "fence" in {x for ns in eq_nouns.values() for x in ns} and "wildlife or theft" not in covered:
        c.finding += " An electric fence is requested but animal damage is not listed as a risk."
    if expected_missing:
        c.suggestion = "Add " + ", ".join(expected_missing) + " with a practical mitigation for each."
    add(c)

    c = Check("C7.3", "C7", "Mitigations are practical and owned", 2)
    mits = [m for _, m in p.risks if m]
    if mits:
        c.earned = 1
        if re.search(r"insurance|cdc|officer|bds|weekly|monthly|before|each season|responsible|agri(culture)? instructor", " ".join(mits), re.I):
            c.earned = 2
        c.status = "pass" if c.earned == 2 else "partial"
        c.finding = "Mitigations are listed" + ("." if c.earned == 2 else " but do not say who acts, when, or at what cost.")
        if c.earned < 2:
            c.suggestion = "For each mitigation add who is responsible and when (e.g. 'CDC to link with Agriculture Instructor before Maha season')."
    else:
        c.status, c.finding = "fail", "No mitigations."
        c.suggestion = "Add a mitigation for each risk."
    add(c)

    # ======================= C8 capacity building ===========================
    ttxt = " ".join(a + " " + b for a, b in p.trainings)
    c = Check("C8.1", "C8", "Technical training planned", 1.5)
    if re.search(r"technical|cultivation|production|farming|husbandry|gap|agronom", ttxt, re.I):
        c.earned, c.finding = 1.5, "Technical training is planned."
    else:
        c.status, c.finding = "fail", "No technical training listed."
        c.suggestion = "Add technical training linked to the livelihood."
    add(c)
    c = Check("C8.2", "C8", "Business and financial skills planned", 1.5)
    if re.search(r"book ?keeping|record|financial|business|marketing|saving|costing|entrepreneur", ttxt, re.I):
        c.earned, c.finding = 1.5, "Business or financial training is planned."
    else:
        c.status = "fail"
        c.finding = "Training covers production only."
        c.suggestion = "Add record keeping, costing and marketing training so the family can manage the larger income."
    add(c)

    # ======================= C9 verification ================================
    def signoff(txt: str | None) -> tuple[bool, bool, bool]:
        t = txt or ""
        return (bool(re.search(r"[A-Z]\.?\s?[A-Za-z]{3,}", t)),
                bool(re.search(r"\b(CDC|ARM|RM|DM|officer|manager|coordinator|PM|FO)\b", t, re.I)),
                bool(re.search(r"\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}|\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4}", t)))

    c = Check("C9.1", "C9", "Prepared by: name, designation, date", 1)
    nm, dg, dt = signoff(p.prepared_by)
    c.earned = (nm + dg + dt) / 3
    c.status = "pass" if c.earned == 1 else "partial" if c.earned else "fail"
    c.finding = f"Prepared by: {p.prepared_by or 'blank'}."
    if c.earned < 1:
        c.suggestion = "Complete preparer name, designation and date."
    add(c)

    c = Check("C9.2", "C9", "Verified by: name, designation, date", 2)
    nm, dg, dt = signoff(p.verified_by)
    c.earned = 0.75 * nm + 0.5 * dg + 0.75 * dt
    c.status = "pass" if c.earned >= 2 else "partial" if c.earned else "fail"
    c.finding = f"Verified by: {p.verified_by or 'blank'}." + ("" if dt else " No verification date.")
    if c.earned < 2:
        c.severity = "major" if not nm else "minor"
        c.suggestion = "The verifying officer should add their designation and the date of the field verification."
    add(c)

    c = Check("C9.3", "C9", "Photos of beneficiary and site", 1)
    if p.photo_count >= 2:
        c.earned, c.finding = 1, f"{p.photo_count} photos attached."
    elif p.photo_count == 1:
        c.status, c.earned, c.finding = "partial", 0.5, "Only one photo attached."
        c.suggestion = "Attach photos of both the beneficiary family and the livelihood site."
    else:
        c.status = "fail"
        c.finding = "No photos found in the file."
        c.suggestion = "Attach photos of the family and the site (for CSV uploads, attach them in SharePoint)."
    add(c)

    c = Check("C9.4", "C9", "Approval recorded", 1)
    if p.approved_by:
        nm, _, dt = signoff(p.approved_by)
        c.earned = (nm + dt) / 2
        c.finding = f"Approved by: {p.approved_by}."
    else:
        c.status = "na"
        c.finding = "Approval is pending (expected at this stage)."
    add(c)

    # ======================= roll-up ========================================
    criteria: dict[str, CriterionScore] = {}
    for cid, meta in CRITERIA.items():
        cs = [x for x in checks if x.criterion == cid and x.status not in {"na", "info"}]
        w = sum(x.weight for x in cs)
        e = sum(x.earned for x in cs)
        score = round(meta["max"] * e / w, 2) if w else 0.0
        criteria[cid] = CriterionScore(cid, meta["name"], meta["max"], score)
    for x in checks:
        x.earned = round(x.earned, 2)
        if x.status == "pass" and x.earned < x.weight:
            x.status = "partial"
        if x.status == "pass":
            x.severity = "info"
    critical = [x for x in checks if x.severity == "critical" and x.status in {"fail", "partial"}]
    ctx = {"poverty_line": opl, "poverty_line_source": opl_src, "reference_date": str(ref),
           "nic": {k: str(v) for k, v in (nic or {}).items()}, "sales_growth": growth,
           "arithmetic_checked": len(arith), "arithmetic_errors": len(errors)}
    return Appraisal(checks, criteria, critical, ctx)
