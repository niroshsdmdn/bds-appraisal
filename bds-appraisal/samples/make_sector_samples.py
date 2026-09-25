"""Build fictional sample proposals for several sectors, in the BDS template layout.

    python samples/make_sector_samples.py

Writes one XLSX and one CSV per sector into samples/sectors/. Every name, NIC and
phone number is invented. All totals are computed here, so the arithmetic checks
always tie; use these files to test the tool, not as pricing guidance.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font  # noqa: E402

OUT = Path(__file__).parent / "sectors"


def build_rows(c: dict) -> list[list]:
    """Turn a proposal description into template rows, computing every total."""
    eq = c["equipment"]                                   # (name, qty, unit, bds_share)
    eq_rows, eq_total, eq_bds = [], 0.0, 0.0
    for i, (name, qty, unit, bds) in enumerate(eq, start=1):
        total = qty * unit
        eq_total += total
        eq_bds += bds
        eq_rows.append([i, name, qty, unit, total, bds, total - bds if total > bds else "-"])
    own_assets = c.get("own_assets", 0)
    dep = round(eq_total / c.get("asset_life", 5), 2)

    exp_rows = list(c["annual_expenses"])                  # (label, current, year 1)
    exp_rows.append(["Depriciations", "-", dep])
    te0 = sum(r[1] for r in exp_rows if isinstance(r[1], (int, float)))
    te1 = sum(r[2] for r in exp_rows if isinstance(r[2], (int, float)))
    s0, s1 = c["sales_current"], c["sales_year1"]
    profit0, profit1 = s0 - te0, s1 - te1

    biz0, biz1 = round(profit0 / 12, 2), round(profit1 / 12, 2)
    inc0 = [(c["business_line"], c["name"], biz0)] + c.get("other_income", [])
    inc1 = [(c["business_line"], c["name"], biz1)] + c.get("other_income", [])
    ti0, ti1 = sum(x[2] for x in inc0), sum(x[2] for x in inc1)
    e0, e1 = c["household_expenses"], c["household_expenses_after"]
    n = len(c["members"])
    pc0, pc1 = round(ti0 / n, 2), round(ti1 / n, 2)

    working = c.get("working_capital", [])
    wc_total = sum(a for _, a in working)
    own_col = own_assets + (eq_total - eq_bds)
    fixed_total = eq_total + own_assets
    inv_total = fixed_total + wc_total
    pct = lambda v: round(v / inv_total * 100, 2)  # noqa: E731

    r: list[list] = [
        ["BERENDINA DEVELOPMENT SERVICES (GTE) LTD"],
        ["1 Name of the Livelihood and Period Involve"],
        [c["livelihood"]],
        ["2) Overview of the Family and Livelihood and their Goal"],
        [c["narrative"]],
        ["Family Details"],
        ["Name", "Age", "Relationship", "Health Condition"],
    ]
    r += [list(m) for m in c["members"]]
    r += [["2.2 Current Income and Expenditure of the family"],
          ["Income", "", "", "Expenditure", ""],
          ["Source", "Earner", "Gain Rs", "Description", "Cost Rs"]]
    pairs = max(len(inc0), len(e0))
    for i in range(pairs):
        src = list(inc0[i]) if i < len(inc0) else ["", "", ""]
        exp = list(e0.items())[i] if i < len(e0) else ["", ""]
        r.append([src[0], src[1], src[2], exp[0], exp[1]])
    r += [["Total", "", ti0, "", sum(e0.values())],
          ["No of Family Members", "", n],
          ["Percapita Income", "", pc0],
          ["2.3 Expected Income and Expenditure of the family after Livelihood Support"],
          ["Income", "", "", "Expenditure", ""],
          ["Source", "Earner", "Gain Rs", "Description", "Cost Rs"]]
    pairs = max(len(inc1), len(e1))
    for i in range(pairs):
        src = list(inc1[i]) if i < len(inc1) else ["", "", ""]
        exp = list(e1.items())[i] if i < len(e1) else ["", ""]
        r.append([src[0], src[1], src[2], exp[0], exp[1]])
    r += [["Total", "", ti1, "", sum(e1.values())],
          ["No of Family Members", "", n],
          ["Percapita Income", "", pc1],
          ["Change of Percapita income", "", round(pc1 - pc0, 2)],
          ["2.4 Overview of the Livelihood"],
          [c["overview"]],
          ["The support she/he required for the LH)", "", "", c["requested"]]]
    for i, g in enumerate(c["goals"], start=1):
        r.append(["Goal" if i == 1 else "", i, g])
    r += [["3 Personal Detail"],
          ["1.Name", c["name"]],
          ["2.Address", c["address"]],
          ["3.NIC No.", c["nic"]],
          ["4.Contact No", c["contact"]],
          ["5. Age", c["age"]],
          ["4 Livelihood Detail"],
          ["Reg. No", c.get("reg_no", "Nil")],
          ["Business Address", c["address"]],
          ["Product/Service", c["product"]],
          ["Market", c["market"]],
          ["Annual Sale", ":", s1],
          ["Annual profit", ":", profit1],
          ["5 Investment"],
          ["", "Description", "", "Total", "Own", "", "Expectation Loan/Grant Rs."],
          ["", "", "", "", "Invested", "Proposed", ""],
          ["", "Fixed Asset", "Land", "-", "", "", ""],
          ["", "", "Equipment", fixed_total, own_col or "-", "", eq_bds],
          ["", "", "Total", fixed_total, own_col or "-", "-", eq_bds]]
    for label, amount in working:
        r.append(["", "Working Capital" if label == working[0][0] else "", label, amount, "", amount, ""])
    r += [["", "", "Total", wc_total, "", wc_total, "-"],
          ["", "Total - Investment", "", inv_total, own_col or "-", wc_total, eq_bds],
          ["", "Percentage Contribution", "", 100, pct(own_col), pct(wc_total), pct(eq_bds)],
          ["6 Expenditure & Income Annual"],
          ["", "", "Current", "", "1st Year Expectation", ""],
          ["", "Description", "Expenditure", "Income", "Expenditure", "Income"],
          ["", "Sales income", "", s0, "", s1]]
    for label, a, b in exp_rows:
        r.append(["", label, a, "", b, ""])
    r += [["", "Total Expenditure", te0, "", te1, ""],
          ["", "Total Income", "", s0, "", s1],
          ["", "Profit/Loss", "", profit0, "", profit1],
          ["7 Detail of Needed Equipment & Inputs"],
          ["No", "Equipment & Inputs Needed", "Qty", "Unit price", "Total",
           "BDS contribution", "Other's Contribution"]]
    r += eq_rows
    r += [["", "", "", "", eq_total, eq_bds, "-"],
          ["8 Possible Risk to the Livelihood and Mitigation Mechanism"],
          ["", "Possible Risks", "Mitigation Mechanism"]]
    for i, (risk, mit) in enumerate(c["risks"], start=1):
        r.append([i, risk, mit])
    r += [["9 Detail of Needed Trainings"], ["No.", "Traineed Needed", "Additional information"]]
    for i, (t, info) in enumerate(c["trainings"], start=1):
        r.append([i, t, info])
    r += [["10 Pictures of Beneficiary or Location"],
          ["11 Prepared by (Name, Designation and Date):", c["prepared_by"]],
          ["12 Varified officer (Name, Desigantion and Date):", c["verified_by"]],
          ["13 Approved by (Name, Designation and Date):", ""]]
    return r


# ---------------------------------------------------------------------------
# the samples
# ---------------------------------------------------------------------------
SAMPLES: dict[str, dict] = {}

SAMPLES["retail_grocery"] = {
    "livelihood": "Village grocery shop - 6 years of experience",
    "name": "P.Kamala", "age": 41, "nic": "855121234V", "contact": "0761234567",
    "address": "Weragala junction, Badulla",
    "product": "Grocery retail", "market": "Weragala village and estate line rooms",
    "business_line": "Grocery shop", "reg_no": "BR/BD/2021/4412",
    "narrative": ("Family background :- Mrs.P.Kamala is 41 years old and runs a small grocery shop at "
                  "Weragala junction, Badulla. Four members live in this family: she, her husband and two "
                  "children. She has run the shop for 6 years. Household income is Rs. 34,000 a month "
                  "against spending of Rs. 36,500, and the family takes goods on credit from the wholesaler "
                  "to cover the gap. She already owns shop shelving worth Rs. 12,000. The shop serves about "
                  "45 customers per day but often runs out of stock by the third day after buying, and "
                  "customers walk to the next village for cold drinks and yoghurt, which she cannot keep."),
    "overview": ("The shop sells rice, dhal, sugar, vegetables, stationery and snacks at Weragala junction, "
                 "beside the school and the bus halt, serving about 45 customers per day with average daily "
                 "sales of Rs. 9,500 and a mark up of about 14%. Stock is bought twice a week from a "
                 "wholesale supplier in Badulla town. With a display freezer and more stock she will add "
                 "cold drinks, yoghurt and ice cream, which neighbours now buy 2 km away, and expects daily "
                 "sales of about Rs. 12,300. The business is registered and holds a local authority trade "
                 "licence. Quotations from two Badulla suppliers are attached."),
    "requested": "Display freezer / shop display rack / stock for the shop",
    "goals": ["Increase monthly business income by 45% within 12 months",
              "Save Rs. 3,000 per month in a bank account for stock and repairs",
              "Reduce credit sales to below 10% of daily sales"],
    "members": [["P.Kamala", 41, "HHH", "Good"], ["K.Sunil", 45, "Husband", "Good"],
                ["K.Dilani", 14, "Daughter", "Good"], ["K.Ravindu", 8, "Son", "Good"]],
    "other_income": [("Estate work", "K.Sunil", 12000)],
    "household_expenses": {"Food": 18000, "Electricity": 2000, "Education": 4000, "Health": 2500},
    "household_expenses_after": {"Food": 18500, "Electricity": 2800, "Education": 4000, "Health": 2200},
    "sales_current": 2_160_000, "sales_year1": 2_808_000,
    "annual_expenses": [["Purchase of goods", 1_872_000, 2_359_000],
                        ["Transport", 42_000, 60_000],
                        ["Electricity", 30_000, 48_000],
                        ["Shop rent", 96_000, 96_000],
                        ["Marketing Expenses", 3_000, 9_000]],
    "equipment": [("Display freezer 200L", 1, 118000, 118000),
                  ("Shop display rack", 2, 16500, 33000),
                  ("Opening stock - drinks and dairy", 1, 45000, 45000)],
    "own_assets": 12000,
    "working_capital": [("Stock purchases", 120000), ("Transport", 15000)],
    "risks": [("Customers not settling credit sales",
               "Limit credit to a written list, settle weekly; family reviews the list every Sunday"),
              ("A new shop opening nearby",
               "Keep drinks and dairy in stock and open early; CDC to review sales monthly"),
              ("Stock expiry and spoilage",
               "Buy dairy in small lots twice a week and check expiry dates before each purchase"),
              ("Power cut damaging frozen stock",
               "Keep the freezer full, and move stock to a neighbour's freezer during long cuts"),
              ("Price increases from the supplier",
               "Compare two wholesale suppliers in Badulla before each purchase")],
    "trainings": [("Technical training on stock and display management",
                   "Purchasing, fast and slow moving items, expiry control"),
                  ("Record keeping and costing", "Daily sales book, credit register, margin calculation")],
    "prepared_by": "S.Kumar - CDC - 2026.06.12", "verified_by": "P.Rajan - ARM - 2026.06.16",
}

SAMPLES["tailoring"] = {
    "livelihood": "Tailoring unit - 9 years of experience",
    "name": "T.Sujatha", "age": 38, "nic": "886201234V", "contact": "0714567890",
    "address": "Mahawela road, Kegalle",
    "product": "Tailoring and school uniforms", "market": "Two schools, a boutique in Kegalle town and village orders",
    "business_line": "Tailoring",
    "narrative": ("Family background :- Mrs.T.Sujatha is 38 years old and sews from home on Mahawela road, "
                  "Kegalle. Five members live in this family: she, her husband, two children and her mother. "
                  "She has sewn for 9 years and completed a tailoring course. Household income is Rs. 31,000 "
                  "a month against spending of Rs. 33,000, and the gap is covered by borrowing from a "
                  "relative. She already owns one old sewing machine worth Rs. 10,000. She turns away school "
                  "uniform orders because finishing each piece by hand takes too long, and returned pieces "
                  "with frayed edges cost her two boutique orders last year."),
    "overview": ("She stitches school uniforms, frocks, blouses and curtains, making about 95 pieces a month "
                 "at an average Rs. 950 per piece, and takes orders from two schools, a boutique in Kegalle "
                 "town and village customers. Cutting on the floor wastes fabric and time, so a cutting table is "
                 "needed, and with an overlock machine and a second sewing machine she can "
                 "finish edges properly and take the 40 extra uniform pieces per month the schools have "
                 "offered, raising output to about 135 pieces per month at the same price. Her daughter "
                 "helps after school. Quotations from two Kegalle suppliers are attached."),
    "requested": "Overlock machine / sewing machine / cutting table",
    "goals": ["Increase monthly business income by 40% within 12 months",
              "Save Rs. 2,500 per month towards machine servicing and fabric",
              "Take at least two regular school uniform contracts"],
    "members": [["T.Sujatha", 38, "HHH", "Good"], ["S.Nimal", 42, "Husband", "Good"],
                ["S.Hiruni", 16, "Daughter", "Good"], ["S.Kavindu", 11, "Son", "Good"],
                ["W.Premawathie", 66, "Mother", "Good"]],
    "other_income": [("Mason work", "S.Nimal", 14000)],
    "household_expenses": {"Food": 18000, "Electricity": 1800, "Education": 4200, "Health": 3000},
    "household_expenses_after": {"Food": 21000, "Electricity": 2200, "Education": 5000, "Health": 3500},
    "sales_current": 912_000, "sales_year1": 1_296_000,
    "annual_expenses": [["Materials and thread", 690_000, 936_000],
                        ["Electricity", 24_000, 33_000],
                        ["Transport", 36_000, 48_000],
                        ["Machine maintenance", 12_000, 18_000],
                        ["Marketing Expenses", 6_000, 12_000]],
    "equipment": [("Overlock machine", 1, 78000, 78000),
                  ("Sewing machine (electric)", 1, 52000, 52000),
                  ("Cutting table", 1, 18000, 18000)],
    "own_assets": 10000,
    "working_capital": [("Fabric and thread", 45000), ("Transport", 9000)],
    "risks": [("Orders dropping between school terms",
               "Take curtain and bridal work in the off season; CDC reviews the order book each quarter"),
              ("Fabric price increases",
               "Buy fabric in bulk with two other tailors before each school term"),
              ("Machine breakdown stopping work",
               "Service both machines every six months and keep Rs. 2,000 aside for repairs"),
              ("Rejected pieces from poor finishing",
               "Check each piece against a sample before delivery"),
              ("Illness stopping work for a period",
               "Train her daughter on the second machine to cover short absences")],
    "trainings": [("Technical training on pattern cutting and finishing", "Overlock use, sizing, quality checks"),
                  ("Record keeping and pricing", "Cost per piece, order book, savings plan")],
    "prepared_by": "N.Fernando - CDC - 2026.06.10", "verified_by": "R.Silva - ARM - 2026.06.15",
}

SAMPLES["transport_threewheeler"] = {
    "livelihood": "Three wheeler hire - 5 years of experience",
    "name": "A.Ranjith", "age": 34, "nic": "921051234V", "contact": "0723456789",
    "address": "Kotikawatta road, Monaragala",
    "product": "Three wheeler passenger and goods hire", "market": "Monaragala town stand, school run and village hires",
    "business_line": "Three wheeler hire",
    "narrative": ("Family background :- Mr.A.Ranjith is 34 years old and drives a rented three wheeler in "
                  "Monaragala. Four members live in this family: he, his wife and two children. He has "
                  "driven for 5 years and holds a valid driving licence. Household income is Rs. 29,000 a "
                  "month against spending of Rs. 31,000, and the gap is met with credit at the village shop. "
                  "He pays Rs. 1,200 a day to rent the vehicle, which takes most of his earnings, and on days "
                  "the owner takes the vehicle back he has no income at all."),
    "overview": ("He works the Monaragala town stand and a morning school run, making about 14 hires a day "
                 "over 26 days a month at an average Rs. 420 per hire, plus two goods trips a week. With his "
                 "own registered three wheeler he stops paying the Rs. 1,200 daily rent, can work the school "
                 "run every day and take evening hires, and a meter ends the fare disputes passengers raise at "
                 "the stand, raising this to about 11 hires a day at the same "
                 "rate. The vehicle will carry a revenue licence, insurance and an emission certificate. "
                 "Quotations from two Monaragala dealers are attached."),
    "requested": "Reconditioned three wheeler / meter / seat cover and carrier",
    "goals": ["Increase monthly business income by about 180% within 12 months by ending the vehicle rent",
              "Save Rs. 4,000 per month for servicing, tyres and insurance renewal",
              "Secure a daily school run contract for the full year"],
    "members": [["A.Ranjith", 34, "HHH", "Good"], ["R.Chamila", 31, "Wife", "Good"],
                ["R.Sanuth", 9, "Son", "Good"], ["R.Nethmi", 5, "Daughter", "Good"]],
    "other_income": [("Home garden and labour", "R.Chamila", 8000)],
    "household_expenses": {"Food": 20000, "Electricity": 2000, "Education": 5000, "Health": 4000},
    "household_expenses_after": {"Food": 22000, "Electricity": 2500, "Education": 6000, "Health": 4500},
    "sales_current": 842_400, "sales_year1": 1_029_600,
    "annual_expenses": [["Vehicle rent", 374_400, "-"],
                        ["Fuel", 280_800, 405_600],
                        ["Maintenance and spares", 60_000, 84_000],
                        ["Insurance", "-", 42_000],
                        ["Revenue licence and emission", "-", 12_000]],
    "equipment": [("Reconditioned three wheeler", 1, 585000, 95000),
                  ("Taxi meter", 1, 18000, 18000),
                  ("Seat covers and rear carrier", 1, 22000, 22000)],
    "own_assets": 0,
    "working_capital": [("Fuel float", 30000), ("Insurance and licence", 54000)],
    "risks": [("Fuel price increases or shortage",
               "Revise the hire rate with the stand committee and keep a full tank before each shortage"),
              ("Accident or breakdown stopping income",
               "Full insurance, service every 5,000 km, and Rs. 4,000 saved monthly for repairs"),
              ("Fewer hires during school holidays",
               "Take goods trips and estate hires in holiday weeks"),
              ("Revenue licence or insurance lapsing",
               "Renew from the savings account one month before expiry; CDC checks the dates at the quarterly visit"),
              ("Another driver taking the school run",
               "Sign a written agreement with the parents before the term starts")],
    "trainings": [("Technical training on vehicle maintenance and road safety",
                   "Daily checks, defensive driving, fuel efficiency"),
                  ("Record keeping and costing", "Daily trip sheet, cost per km, savings for renewals")],
    "prepared_by": "T.Raj - CDC - 2026.06.08", "verified_by": "P.Rajan - ARM - 2026.06.14",
}

SAMPLES["food_bakery"] = {
    "livelihood": "Home bakery and short eats - 4 years of experience",
    "name": "M.Farzana", "age": 36, "nic": "905301234V", "contact": "0779876543",
    "address": "Palliya road, Kalutara",
    "product": "Short eats, buns and cake", "market": "Three tea shops, a school canteen and home orders",
    "business_line": "Home bakery",
    "narrative": ("Family background :- Mrs.M.Farzana is 36 years old and bakes at home on Palliya road, "
                  "Kalutara. Four members live in this family: she, her husband and two children. She has "
                  "baked for 4 years and holds a food handling certificate. Household income is Rs. 32,000 a "
                  "month against spending of Rs. 34,500, and the gap is met on shop credit. She already owns "
                  "baking trays and vessels worth Rs. 9,000. Her single gas cooker takes three hours per "
                  "batch, so she can supply only three tea shops and has refused a school canteen order, and "
                  "unsold items spoil by the next morning without cold storage."),
    "overview": ("She makes rolls, patties, buns and cake, about 420 pieces a day at an average Rs. 55 per "
                 "piece, supplied to three tea shops, a school canteen and home orders in Kalutara town. A "
                 "gas oven bakes a batch in 40 minutes instead of three hours, letting her supply the school "
                 "canteen order of 150 pieces a day, a dough mixer ends the hour she spends kneading each batch by hand, and a chiller keeps fillings overnight, so production "
                 "rises to about 560 pieces a day at the same price. She holds a PHI food handling "
                 "certificate and a local authority trade licence, and packs with printed labels showing the "
                 "batch date. Quotations from two Kalutara suppliers are attached."),
    "requested": "Gas oven / chiller / dough mixer",
    "goals": ["Increase monthly business income by 45% within 12 months",
              "Save Rs. 3,000 per month for gas, repairs and ingredient stock",
              "Supply the school canteen order of 150 pieces every school day"],
    "members": [["M.Farzana", 36, "HHH", "Good"], ["M.Rizwan", 40, "Husband", "Good"],
                ["R.Aisha", 12, "Daughter", "Good"], ["R.Imran", 7, "Son", "Good"]],
    "other_income": [("Carpentry work", "M.Rizwan", 13000)],
    "household_expenses": {"Food": 20000, "Electricity": 2800, "Education": 4700, "Health": 3000},
    "household_expenses_after": {"Food": 20000, "Electricity": 3200, "Education": 5200, "Health": 3200},
    "sales_current": 3_300_000, "sales_year1": 4_400_000,
    "annual_expenses": [["Ingredients", 2_310_000, 2_970_000],
                        ["Packaging and labels", 96_000, 150_000],
                        ["Gas and firewood", 216_000, 276_000],
                        ["Transport", 96_000, 144_000],
                        ["Staff salaries - Additional Family Labour", 384_000, 504_000],
                        ["Marketing Expenses", 12_000, 24_000]],
    "equipment": [("Gas oven (3 tray)", 1, 165000, 165000),
                  ("Chiller 300L", 1, 96000, 96000),
                  ("Dough mixer 10kg", 1, 72000, 72000)],
    "own_assets": 9000,
    "working_capital": [("Ingredients", 90000), ("Packaging", 18000), ("Gas", 12000)],
    "risks": [("Flour and sugar price increases",
               "Buy monthly from a wholesale supplier and adjust the piece price with the tea shops"),
              ("Items spoiling before sale",
               "Bake to confirmed orders, keep fillings chilled and check dates daily"),
              ("Gas shortage or power cut stopping baking",
               "Keep one spare cylinder and firewood as a backup"),
              ("Oven breakdown",
               "Service the oven every six months and keep Rs. 3,000 aside for repairs"),
              ("Losing the school canteen order",
               "Written supply agreement each term and delivery before 7 am")],
    "trainings": [("Technical training on baking and food hygiene", "Batch production, oven use, GMP and storage"),
                  ("Record keeping and costing", "Cost per piece, order book, savings plan")],
    "prepared_by": "A.Perera - CDC - 2026.06.05", "verified_by": "R.Silva - ARM - 2026.06.11",
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for key, cfg in SAMPLES.items():
        rows = build_rows(cfg)
        wb = Workbook()
        ws = wb.active
        ws.title = "Proposal"
        for row in rows:
            ws.append(row)
        for r in ws.iter_rows():
            for cell in r:
                cell.font = Font(name="Arial")
        ws.column_dimensions["A"].width = 48
        wb.save(OUT / f"{key}.xlsx")
        with open(OUT / f"{key}.csv", "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(rows)
        print(f"Wrote {key}.xlsx and {key}.csv")


if __name__ == "__main__":
    main()
