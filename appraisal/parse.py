"""Map the BDS livelihood proposal template onto structured fields.

The parser walks the grid (tables) with a small section state machine and
uses the text lines for key/value fields. It is deliberately tolerant: a
missing field is recorded as None and becomes a finding, never a crash.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from .config import SRI_LANKA_DISTRICTS
from .extract import Extracted, fix_split_numbers, to_number

NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10}


@dataclass
class Member:
    name: str
    age: float | None
    relationship: str
    health: str


@dataclass
class IncomeLine:
    source: str
    earner: str
    amount: float | None


@dataclass
class FamilyBudget:
    incomes: list[IncomeLine] = field(default_factory=list)
    expenses: dict[str, float] = field(default_factory=dict)
    total_income: float | None = None
    total_expense: float | None = None
    members: float | None = None
    per_capita: float | None = None
    per_capita_change: float | None = None


@dataclass
class EquipmentItem:
    no: str
    name: str
    qty: float | None
    unit_price: float | None
    total: float | None
    bds: float | None
    other: float | None


@dataclass
class Proposal:
    livelihood: str | None = None
    period_involved: str | None = None
    narrative: str = ""
    overview: str = ""
    requested_support: str | None = None
    goals: list[str] = field(default_factory=list)
    # personal
    name: str | None = None
    address: str | None = None
    nic: str | None = None
    contact: str | None = None
    age_personal: float | None = None
    age_narrative: float | None = None
    title: str | None = None
    members_narrative: int | None = None
    # livelihood detail
    reg_no: str | None = None
    business_address: str | None = None
    product: str | None = None
    market: str | None = None
    annual_sale: float | None = None
    annual_profit: float | None = None
    # tables
    members: list[Member] = field(default_factory=list)
    current: FamilyBudget = field(default_factory=FamilyBudget)
    expected: FamilyBudget = field(default_factory=FamilyBudget)
    investment: dict[str, dict[str, float | None]] = field(default_factory=dict)
    annual: dict[str, list[float]] = field(default_factory=dict)
    net_impact_monthly: float | None = None
    equipment: list[EquipmentItem] = field(default_factory=list)
    equipment_total: dict[str, float | None] = field(default_factory=dict)
    risks: list[tuple[str, str]] = field(default_factory=list)
    trainings: list[tuple[str, str]] = field(default_factory=list)
    # sign-off
    prepared_by: str | None = None
    verified_by: str | None = None
    approved_by: str | None = None
    prepared_date: date | None = None
    # context
    district: str | None = None
    locations: dict[str, set[str]] = field(default_factory=dict)
    photo_count: int = 0
    full_text: str = ""
    notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ helpers
    def annual_value(self, key: str, idx: int) -> float | None:
        vals = self.annual.get(key)
        if vals and len(vals) > idx:
            return vals[idx]
        return None

    def as_summary_rows(self) -> list[tuple[str, str]]:
        def money(v):
            return "-" if v is None else f"Rs. {v:,.2f}"
        rows = [
            ("Beneficiary", self.name or "-"),
            ("NIC", self.nic or "-"),
            ("Contact", self.contact or "-"),
            ("Address", self.address or "-"),
            ("District", self.district or "-"),
            ("Livelihood", self.livelihood or self.product or "-"),
            ("Market", self.market or "-"),
            ("Household members", str(len(self.members)) if self.members else "-"),
            ("Current household income / month", money(self.current.total_income)),
            ("Current household expenditure / month", money(self.current.total_expense)),
            ("Current per-capita income / month", money(self.current.per_capita)),
            ("Expected household income / month", money(self.expected.total_income)),
            ("Expected per-capita income / month", money(self.expected.per_capita)),
            ("Current annual sales", money(self.annual_value("sales", 0))),
            ("Year-1 annual sales", money(self.annual_value("sales", 1))),
            ("Year-1 annual profit", money(self.annual_value("profit", 1))),
            ("Grant requested (BDS)", money(self.equipment_total.get("bds"))),
            ("Requested support (narrative)", self.requested_support or "-"),
            ("Prepared by", self.prepared_by or "-"),
            ("Verified by", self.verified_by or "-"),
            ("Approved by", self.approved_by or "(pending)"),
        ]
        return rows


# ----------------------------------------------------------------------------
# section detection
# ----------------------------------------------------------------------------
SECTION_PATTERNS = [
    ("family_details", r"^family details"),
    ("investment", r"^\d*\s*investment\b"),
    ("annual", r"expenditure\s*&?\s*(and)?\s*income\s*annual"),
    ("equipment", r"needed equipment"),
    ("risks", r"possible risk"),
    ("trainings", r"needed training"),
    ("pictures", r"pictures of"),
    ("personal", r"personal detail"),
    ("livelihood_detail", r"livelihood detail"),
    ("overview", r"overview of the livelihood"),
    ("signoff", r"prepared by"),
    ("family_income_pre", r"income and expenditure of the family"),
]

ANNUAL_KEYS = [
    ("sales", r"^sales income"),
    ("seeds", r"^seeds?"),
    ("raw_material", r"^raw material"),
    ("labour", r"^manpower"),
    ("labour_group", r"^labou?r cost"),
    ("land_prep", r"^land prepar"),
    ("fertilizer", r"^fertili[sz]er"),
    ("chemicals", r"^chemical"),
    ("machine_rent", r"^machine rent"),
    ("purchases", r"\b(purchase|cost of (goods|sales)|stock purchase|trading|buying)"),
    ("feed", r"\b(feed|fodder|ration|concentrate)\b"),
    ("veterinary", r"\b(veterinar|medicine|vaccin|drugs)"),
    ("ingredients", r"\b(ingredient|flour|provision|grocer)"),
    ("materials", r"\b(material|fabric|cloth|thread|timber|cement|sand|steel|consumable)"),
    ("packaging", r"\b(packag|packing|label|bottle|wrapp|carton)"),
    ("fuel", r"\b(fuel|petrol|diesel|gas\b|firewood|kerosene)"),
    ("rent", r"\b(rent|lease)\b"),
    ("transport", r"\b(transport|delivery|freight|travel|fare)"),
    ("utilities", r"\b(electricity|water (bill|charge)|utilit|telephone|internet)"),
    ("maintenance", r"\b(maintenance|repairs?|servicing|service charge)"),
    ("spares", r"\b(spare)"),
    ("salaries", r"\b(salar|wages)"),
    ("insurance", r"\binsurance\b"),
    ("licence", r"\b(licen[cs]e|permit)\b"),
    ("depreciation", r"^depr[ie]*ciation"),
    ("marketing", r"^marketing"),
    ("administration", r"^administration"),
    ("overhead", r"^overhead"),
    ("total_expense", r"^total expenditure"),
    ("total_income", r"^total income"),
    ("profit", r"^profit"),
    ("per_capita", r"^per\s*capita"),
    ("daily_income", r"^daily income"),
]

NON_EXPENSE_KEYS = {"sales", "total_expense", "total_income", "profit", "per_capita",
                    "daily_income", "labour_group"}
EXPENSE_KEYS = [k for k, _ in ANNUAL_KEYS if k not in NON_EXPENSE_KEYS]

INVEST_KEYS = [
    ("land", r"^land$"), ("buildings", r"^buildings?$"), ("machinery", r"^machinery"),
    ("equipment", r"^equipment$"), ("furniture", r"^furniture"),
    ("working_capital_total", r"^__never__"),
    ("total_investment", r"^total\s*-\s*investment"),
    ("percentage", r"^percentage"),
]


def _detect_section(text: str) -> str | None:
    t = re.sub(r"^\s*\d+(\.\d+)?\)?\s*", "", text.strip().lower())
    for key, pat in SECTION_PATTERNS:
        if re.search(pat, t) or re.search(pat, text.strip().lower()):
            return key
    return None


def _nums(cells: list[str]) -> list[float]:
    out = []
    for c in cells:
        v = to_number(c)
        if v is not None:
            out.append(v)
    return out


def _first_text(cells: list[str]) -> str:
    for c in cells:
        if c and to_number(c) is None:
            return c
    return ""


def _idx(cells: list[str], pattern: str) -> int | None:
    for i, c in enumerate(cells):
        if c and re.search(pattern, c, re.I):
            return i
    return None


def _at(cells: list[str], i: int | None) -> str:
    if i is None or i >= len(cells):
        return ""
    return cells[i] or ""


def _num_at(cells: list[str], i: int | None) -> float | None:
    return to_number(_at(cells, i)) if _at(cells, i) else None


# ----------------------------------------------------------------------------
# grid walker
# ----------------------------------------------------------------------------
def _walk_grid(p: Proposal, grid: list[list[str]]) -> None:
    state = None
    fam_block = 0
    fam_cols: dict[str, int | None] = {}
    fam_cols_by_width: dict[int, dict[str, int | None]] = {}
    inv_cols: dict[str, int | None] = {}
    eq_cols: dict[str, int | None] = {}
    member_cols: dict[str, int | None] = {}

    for raw in grid:
        cells = [(c or "").strip() for c in raw]
        ne = [c for c in cells if c]
        if not ne:
            continue
        low_cells = [c.lower() for c in ne]
        first = ne[0]

        # --- requested support row can sit anywhere
        joined = " ".join(ne)
        if re.search(r"support.*required", joined, re.I) and p.requested_support is None:
            rest = [c for c in ne if not re.search(r"support.*required", c, re.I)]
            if rest:
                p.requested_support = " ".join(rest)
            continue

        # --- family income header (Source / Earner / Gain / Description / Cost)
        if any(c == "source" for c in low_cells) and any("earner" in c for c in low_cells):
            state = "family_income"
            fam_block += 1
            fam_cols = {
                "source": _idx(cells, r"^source$"), "earner": _idx(cells, r"earner"),
                "gain": _idx(cells, r"gain|amount|income"), "desc": _idx(cells, r"description"),
                "cost": _idx(cells, r"cost"),
            }
            fam_cols_by_width[len(cells)] = fam_cols
            continue

        if len(first) > 250:  # a narrative paragraph closes any open table
            if state == "family_income":
                state = "overview"
            if not p.narrative and re.search(r"family background|years old|members", first, re.I):
                p.narrative = re.sub(r"^family background\s*:?-?\s*", "", first, flags=re.I)
            elif not p.overview:
                p.overview = first
            continue

        # header rows whose section title lives only in the text layer
        if low_cells[:2] == ["income", "expenditure"]:
            state = "family_income_pre"
            continue
        if any(re.search(r"^possible risks?$", c) for c in low_cells):
            state = "risks"
            continue
        if any(re.search(r"trainee?d?s? needed|training needed", c) for c in low_cells):
            state = "trainings"
            continue
        if any("equipment" in c for c in low_cells) and any(re.search(r"qty|quantity", c) for c in low_cells):
            state = "equipment"

        sec = _detect_section(first)
        if sec:
            state = sec
            if len(ne) == 1:  # a heading row carries no data
                continue
        if first.lower() == "goal" or (state == "goals" and not sec):
            if first.lower() == "goal":
                state = "goals"
            text = max((c for c in ne if to_number(c) is None and c.lower() != "goal"),
                       key=len, default="")
            if text:
                p.goals.append(text)
            continue

        # ------------------------------------------------------------- family
        if state == "family_details":
            if "name" in low_cells and any("age" == c for c in low_cells):
                member_cols = {"name": _idx(cells, r"^name$"), "age": _idx(cells, r"^age$"),
                               "rel": _idx(cells, r"relation"), "health": _idx(cells, r"health")}
                continue
            if member_cols and _at(cells, member_cols["name"]):
                p.members.append(Member(
                    _at(cells, member_cols["name"]),
                    _num_at(cells, member_cols["age"]),
                    _at(cells, member_cols["rel"]),
                    _at(cells, member_cols["health"]),
                ))
            continue

        if state == "family_income":
            budget = p.current if fam_block <= 1 else p.expected
            cols = fam_cols_by_width.get(len(cells), fam_cols)
            label = first.lower()
            if label.startswith("total"):
                nums = _nums(cells[1:])
                if nums:
                    budget.total_income = nums[0]
                    if len(nums) > 1:
                        budget.total_expense = nums[-1]
                continue
            if label.startswith("no of family") or label.startswith("number of family"):
                n = _nums(cells[1:])
                budget.members = n[0] if n else None
                continue
            if label.startswith("change of per"):
                n = _nums(cells[1:])
                budget.per_capita_change = n[0] if n else None
                continue
            if re.match(r"per\s*capita", label):
                n = _nums(cells[1:])
                budget.per_capita = n[0] if n else None
                continue
            if label in {"income", "expenditure"}:
                continue
            src = _at(cells, cols.get("source"))
            if src and to_number(src) is None:
                budget.incomes.append(IncomeLine(src, _at(cells, cols.get("earner")),
                                                 _num_at(cells, cols.get("gain"))))
            desc = _at(cells, cols.get("desc"))
            cost = _num_at(cells, cols.get("cost"))
            if desc and to_number(desc) is None:
                budget.expenses[desc] = cost if cost is not None else 0.0
            continue

        # --------------------------------------------------------- investment
        if state == "investment":
            if _idx(cells, r"^total$") is not None and _idx(cells, r"^own$") is not None:
                inv_cols = {"total": _idx(cells, r"^total$"), "own": _idx(cells, r"^own$"),
                            "grant": _idx(cells, r"loan|grant|expectation")}
                continue
            if _idx(cells, r"^invested$") is not None:
                inv_cols["own"] = _idx(cells, r"^invested$")
                inv_cols["own_proposed"] = _idx(cells, r"^proposed$")
                continue
            # the label is the right-most text cell (group labels sit to its left)
            texts = [c for c in cells if c and to_number(c) is None]
            label = texts[-1] if texts else ""
            if label.lower() == "total" and "working capital" not in joined.lower():
                pass
            key = None
            for k, pat in INVEST_KEYS:
                if re.search(pat, label.strip().lower()) or re.search(pat, first.strip().lower()):
                    key = k
                    break
            if key is None and label.lower() == "total":
                # first "Total" = fixed assets, later = working capital
                key = "fixed_total" if "fixed_total" not in p.investment else (
                    "prior_total" if "prior_total" not in p.investment else "working_capital_total")
            if key is None:
                key = re.sub(r"\W+", "_", label.lower()).strip("_") or None
            if key and inv_cols:
                p.investment[key] = {
                    "total": _num_at(cells, inv_cols.get("total")),
                    "own": _num_at(cells, inv_cols.get("own")),
                    "own_proposed": _num_at(cells, inv_cols.get("own_proposed")),
                    "grant": _num_at(cells, inv_cols.get("grant")),
                }
            continue

        # ------------------------------------------------------------- annual
        if state == "annual":
            if first.lower().startswith("net impact"):
                m = re.search(r"monthly\s*([\d,\s.]+)", fix_split_numbers(joined), re.I)
                if m:
                    p.net_impact_monthly = to_number(m.group(1).split()[0])
                continue
            label = first.lower()
            for k, pat in ANNUAL_KEYS:
                if re.search(pat, label):
                    nums = _nums(cells[cells.index(first) + 1:])
                    if nums and (k not in p.annual or not any(p.annual[k])):
                        p.annual[k] = nums
                    break
            continue

        # ---------------------------------------------------------- equipment
        if state == "equipment":
            if _idx(cells, r"qty|quantity") is not None:
                eq_cols = {"no": _idx(cells, r"^no\.?$"), "name": _idx(cells, r"equipment|input|item"),
                           "qty": _idx(cells, r"qty|quantity"), "unit": _idx(cells, r"unit"),
                           "total": _idx(cells, r"^total"), "bds": _idx(cells, r"bds"),
                           "other": _idx(cells, r"other")}
                continue
            if not eq_cols:
                continue
            name = _at(cells, eq_cols["name"])
            if name and to_number(name) is None and not _detect_section(name):
                p.equipment.append(EquipmentItem(
                    _at(cells, eq_cols["no"]), name, _num_at(cells, eq_cols["qty"]),
                    _num_at(cells, eq_cols["unit"]), _num_at(cells, eq_cols["total"]),
                    _num_at(cells, eq_cols["bds"]), _num_at(cells, eq_cols["other"])))
            elif _num_at(cells, eq_cols["total"]) is not None:
                p.equipment_total = {"total": _num_at(cells, eq_cols["total"]),
                                     "bds": _num_at(cells, eq_cols["bds"]),
                                     "other": _num_at(cells, eq_cols["other"])}
            continue

        # -------------------------------------------------------------- risks
        if state == "risks":
            texts = [c for c in cells if c and to_number(c) is None]
            if any(re.search(r"possible risk|mitigation mech", t, re.I) for t in texts):
                continue
            if texts:
                p.risks.append((texts[0], texts[1] if len(texts) > 1 else ""))
            continue

        if state == "trainings":
            texts = [c for c in cells if c and to_number(c) is None]
            if any(re.search(r"trainee?d? needed|additional information", t, re.I) for t in texts):
                continue
            if texts and not re.match(r"^no\.?$", texts[0], re.I):
                p.trainings.append((texts[0], texts[1] if len(texts) > 1 else ""))
            continue


# ----------------------------------------------------------------------------
# line-based fields
# ----------------------------------------------------------------------------
def _after(pattern: str, lines: list[str]) -> str | None:
    rx = re.compile(pattern, re.I)
    for ln in lines:
        m = rx.search(ln)
        if m:
            val = ln[m.end():].strip(" :-\t")
            return val or ""
    return None


def _between(lines: list[str], start: str, stops: list[str]) -> str:
    out, on = [], False
    for ln in lines:
        if not on and re.search(start, ln, re.I):
            on = True
            rest = re.split(start, ln, flags=re.I, maxsplit=1)[-1].strip(" :-")
            if rest:
                out.append(rest)
            continue
        if on:
            if any(re.search(s, ln, re.I) for s in stops):
                break
            out.append(ln)
    return " ".join(out).strip()


def _parse_date(text: str | None) -> date | None:
    if not text:
        return None
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](20\d{2})", text)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _locations(text: str) -> dict[str, set[str]]:
    """Distinct division / estate names, de-duplicated on a normalised key."""
    flat = re.sub(r"\s+", " ", text)

    def dedupe(names):
        seen = {}
        for n in names:
            k = _norm(n)
            if k and k not in seen:
                seen[k] = n.strip()
        return set(seen.values())

    divisions = re.findall(r"\b((?:No\.?\s*\d+)|[A-Z][A-Za-z]+)\s+Division\b", flat)
    estates = re.findall(r"\b(?!Division\b)([A-Z][A-Za-z]+)\s+Estate\b", flat)
    estates += re.findall(r"Division\s+([A-Z][A-Za-z]+)(?:\s+Estate)?", flat)
    return {"division": dedupe(divisions), "estate": dedupe(estates)}


def parse(ex: Extracted) -> Proposal:
    p = Proposal()
    lines = ex.lines
    _walk_grid(p, ex.grid)

    # livelihood name / period
    for i, ln in enumerate(lines):
        if re.search(r"name of the livelihood", ln, re.I):
            tail = re.split(r"involved?", ln, flags=re.I)[-1].strip(" :-")
            if tail and not re.search(r"name of the livelihood", tail, re.I):
                p.livelihood = tail
            elif i + 1 < len(lines):
                p.livelihood = lines[i + 1].strip()
            break
    per = re.search(r"(\d+)\s*(years?|months?)\s*(of\s*experience|involved|in this)", ex.full_text, re.I)
    if per:
        p.period_involved = per.group(0)

    if not p.narrative:
        p.narrative = _between(lines, r"family background\s*:?-?", [r"^family details", r"^name\s+age"])
    if not p.overview:
        p.overview = _between(lines, r"overview of the livelihood",
                              [r"support she/he required", r"^goal", r"personal detail"])
    if not p.goals:
        m = [ln for ln in lines if re.match(r"^\d\s*[A-Z].*", ln) and re.search(r"income|saving|production", ln, re.I)]
        p.goals = [re.sub(r"^\d\s*", "", g) for g in m[:5]]

    # personal detail
    p.name = _after(r"^\s*1\.\s*name\b", lines)
    p.address = _after(r"^\s*2\.\s*address\b", lines)
    nic = re.search(r"\b(\d{9}[VvXx]|\d{12})\b", _after(r"nic\s*no\.?", lines) or ex.full_text)
    p.nic = nic.group(1).upper() if nic else None
    contact = _after(r"contact\s*no\.?", lines)
    p.contact = re.sub(r"[^\d+]", "", contact) if contact else None
    age = _after(r"^\s*5\.\s*age\b", lines)
    p.age_personal = to_number(age.split()[0]) if age else None

    narr = p.narrative
    m = re.search(r"(\d{1,2})\s*years?\s*old", narr, re.I)
    p.age_narrative = float(m.group(1)) if m else None
    m = re.search(r"\b(Mrs|Ms|Miss|Mr)\b\.?", narr)
    p.title = m.group(1) if m else None
    m = re.search(r"\b(\w+)\s+members?\b", narr, re.I)
    if m:
        w = m.group(1).lower()
        p.members_narrative = WORD_NUMBERS.get(w) or (int(w) if w.isdigit() else None)

    # livelihood detail
    p.reg_no = _after(r"^reg\.?\s*no\.?", lines)
    p.business_address = _after(r"^business address", lines)
    p.product = _after(r"^product\s*/\s*service", lines)
    p.market = _after(r"^market\b", lines)
    sale = _after(r"^annual sales?\b", lines)
    p.annual_sale = to_number(NUM_RE.search(sale).group(0)) if sale and NUM_RE.search(sale) else None
    prof = _after(r"^annual profit\b", lines)
    p.annual_profit = to_number(NUM_RE.search(prof).group(0)) if prof and NUM_RE.search(prof) else None

    # sign-offs
    p.prepared_by = _after(r"prepared by\s*\([^)]*\)\s*:?", lines)
    p.verified_by = _after(r"(?:verified|varified)\s*(?:officer|by)?\s*\([^)]*\)\s*:?", lines)
    p.approved_by = _after(r"approved by\s*\([^)]*\)\s*:?", lines)
    for attr in ("prepared_by", "verified_by", "approved_by"):
        v = getattr(p, attr)
        if v is not None and not re.search(r"[A-Za-z]{2,}", v):
            setattr(p, attr, "")
    p.prepared_date = _parse_date(p.prepared_by)

    # context
    flat = _norm(ex.full_text)
    for d in SRI_LANKA_DISTRICTS:
        if _norm(d) in flat:
            p.district = d
            break
    p.locations = _locations(ex.full_text)
    p.photo_count = ex.photo_count
    p.full_text = ex.full_text + "\n" + ex.grid_as_text()
    return p
