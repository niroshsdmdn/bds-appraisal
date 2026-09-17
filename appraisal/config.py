"""Appraisal rubric, decision bands and tunable thresholds.

Everything a programme team may want to adjust lives here, so the scoring
logic in checks.py never hard-codes policy numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Rubric: nine criteria, 100 marks in total
# --------------------------------------------------------------------------
CRITERIA: dict[str, dict] = {
    "C1": {"name": "Eligibility and vulnerability", "max": 15,
           "question": "Is this the right family to support?"},
    "C2": {"name": "Completeness and data accuracy", "max": 15,
           "question": "Can the facts in the proposal be trusted?"},
    "C3": {"name": "Livelihood viability and market", "max": 15,
           "question": "Is the livelihood specific, marketable and goal-driven?"},
    "C4": {"name": "Financial soundness", "max": 20,
           "question": "Do the numbers add up and are projections realistic?"},
    "C5": {"name": "Relevance and value of requested support", "max": 10,
           "question": "Is each item needed, justified and correctly costed?"},
    "C6": {"name": "Contribution and sustainability", "max": 10,
           "question": "Will the family sustain the livelihood after support?"},
    "C7": {"name": "Risk analysis and mitigation", "max": 7,
           "question": "Are the real risks identified with workable responses?"},
    "C8": {"name": "Capacity building", "max": 3,
           "question": "Does training cover production and business skills?"},
    "C9": {"name": "Verification and approval trail", "max": 5,
           "question": "Has the proposal been properly prepared and verified?"},
}

# Decision bands, highest first: (minimum mark, label, colour key, guidance)
BANDS = [
    (75, "Approve", "go",
     "Proceed. Address minor suggestions during implementation."),
    (60, "Approve with conditions", "cond",
     "Proceed once the listed conditions are met and recorded."),
    (45, "Revise and resubmit", "revise",
     "Return to the writer. Fix the flagged issues and re-appraise."),
    (0, "Not recommended", "stop",
     "Do not proceed in the current form."),
]

# A critical finding caps the decision at this band regardless of marks.
CRITICAL_CAP = "Revise and resubmit"

# --------------------------------------------------------------------------
# Official poverty lines (Rs. per person per month)
# Source: Department of Census and Statistics, July 2026 release
# (statistics.gov.lk > Poverty). Update monthly or override in the sidebar.
# --------------------------------------------------------------------------
OPL_AS_OF = "July 2026"
NATIONAL_OPL = 17_679
DISTRICT_OPL = {
    "Batticaloa": 17_775,
    "Trincomalee": 17_226,
       "Mullaitivu": 18_963,
       "Anuradhapura": 17_253,
       "Kegalle": 18_484,
    "Nuwara Eliya": 18_592,
}

SRI_LANKA_DISTRICTS = [
    "Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo", "Galle",
    "Gampaha", "Hambantota", "Jaffna", "Kalutara", "Kandy", "Kegalle",
    "Kilinochchi", "Kurunegala", "Mannar", "Matale", "Matara", "Monaragala",
    "Mullaitivu", "Nuwara Eliya", "Polonnaruwa", "Puttalam", "Ratnapura",
    "Trincomalee", "Vavuniya",
]


@dataclass
class Settings:
    """Thresholds a reviewer can tune from the sidebar."""
    poverty_line: float | None = None          # None = use district / national
    min_beneficiary_share: float = 0.25        # own contribution / total investment
    max_grant: float | None = None             # per-beneficiary grant ceiling
    sales_growth_ok: float = 0.25              # growth that needs no justification
    sales_growth_caution: float = 0.50
    sales_growth_limit: float = 1.00           # above this is treated as unrealistic
    margin_ok: float = 0.45                    # profit / sales
    margin_limit: float = 0.60
    material_error_ratio: float = 0.05         # arithmetic gap that is "critical"
    extra: dict = field(default_factory=dict)


def band_for(score: float) -> tuple[str, str, str]:
    for minimum, label, key, guidance in BANDS:
        if score >= minimum:
            return label, key, guidance
    return BANDS[-1][1], BANDS[-1][2], BANDS[-1][3]


def band_rank(label: str) -> int:
    """0 = best band. Used to apply the critical-finding cap."""
    for i, (_, lab, _, _) in enumerate(BANDS):
        if lab == label:
            return i
    return len(BANDS) - 1
