"""Build a fictional appraisal register to preview the dashboard.

    python samples/make_demo_register.py   ->  samples/demo_register.csv
All people and figures are invented.
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from appraisal.config import CRITERIA, band_for  # noqa: E402

random.seed(7)
DISTRICTS = ["Nuwara Eliya", "Badulla", "Monaragala", "Kandy", "Kegalle", "Ratnapura"]
LIVELIHOODS = ["Vegetable cultivation", "Poultry", "Dairy", "Tailoring", "Grocery shop", "Mushroom"]
PREPARERS = ["A.Perera - CDC", "S.Kumar - CDC", "N.Fernando - CDC", "R.Silva - CDC", "T.Raj - CDC"]
WEAK = ["C3.1", "C3.2", "C3.3", "C4.3", "C4.4", "C5.2", "C5.5", "C7.2", "C8.2", "C2.2", "C2.3", "C9.2"]
CRIT = ["C2.4", "C4.1", "C2.1"]


def main() -> None:
    rows = []
    start = datetime(2026, 3, 1)
    for i in range(60):
        skill = random.gauss(0.68, 0.14)
        scores = {cid: round(max(0, min(1, random.gauss(skill, 0.12))) * m["max"], 2)
                  for cid, m in CRITERIA.items()}
        total = round(sum(scores.values()), 1)
        fails = random.sample(WEAK, k=max(0, int((1 - skill) * 10)))
        crit = random.sample(CRIT, 1) if random.random() < 0.15 else []
        label = band_for(total)[0]
        if crit and label.startswith("Approve"):
            label = "Revise and resubmit"
        final = label if random.random() < 0.8 else random.choice(["Approve with conditions", "Revise and resubmit"])
        rows.append({
            "saved_at": (start + timedelta(days=random.randint(0, 190))).isoformat(timespec="seconds"),
            "beneficiary": f"Demo beneficiary {i + 1:02d}", "nic": "",
            "district": random.choice(DISTRICTS), "livelihood": random.choice(LIVELIHOODS),
            "grant_rs": random.choice([45000, 60000, 75000, 95900, 110000]),
            "total_mark": total, "system_decision": label,
            "critical_findings": ";".join(crit), "reviewer_decision": label,
            "approver_decision": final if random.random() < 0.7 else "",
            "saved_by": "Demo", "role": "approver", "folder": "", "file_sha1": f"demo{i:04d}",
            "prepared_by": random.choice(PREPARERS) + " - 2026.05.01", "verified_by": "",
            "failed_checks": ";".join(fails + crit), "partial_checks": "",
            **{f"{cid}_score": v for cid, v in scores.items()},
        })
    out = Path(__file__).parent / "demo_register.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
