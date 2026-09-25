# BDS livelihood proposal appraisal tool

A web app that appraises Berendina Development Services (BDS) household livelihood
proposals written on the standard template. Writers, reviewers and approvers upload a
proposal (PDF, XLSX or CSV), get a mark out of 100 with a recommended decision, see every
finding behind the mark, and get a ranked list of fixes that would raise it. Decisions
and reports are saved to SharePoint.

```
 Browser (anyone with the link + an access code)
    │
    ▼
 Streamlit app  ── Appraisal.py (+ pages/1_Portfolio_dashboard.py)
    ├─ extract.py    PDF / XLSX / CSV  →  tables + text + photos
    ├─ parse.py      template sections →  structured proposal
    ├─ sectors.py    11 sector profiles →  what to expect from each trade
    ├─ checks.py     38 rule checks    →  9 criteria, 100 marks, decision, fixes
    ├─ ai_review.py  Claude API reads the whole file → second-opinion marks + findings
    ├─ report.py     Excel report, printable HTML, JSON
    └─ sharepoint.py Microsoft Graph → Incoming / Appraised / Register
    │
 GitHub (code, tests in Actions)  →  Streamlit Community Cloud (hosting, secrets)
```

## How a proposal moves through the tool

| Role | Can do |
|---|---|
| Writer (CDC) | Upload a draft, see the mark and fixes, download the report, submit to SharePoint `Incoming/` |
| Reviewer (ARM) | Open from `Incoming/`, change criterion marks with a reason, record a recommendation and conditions, save the record |
| Approver | Everything a reviewer sees, plus the final decision. Approving with open critical findings requires a written justification |

Every action is written to the report's audit trail.

## Portfolio dashboard

The **Portfolio dashboard** page (reviewers and approvers only) charts every appraisal saved
to the SharePoint register: mark distribution against the decision bands, decisions by
district, the criteria where proposals lose most marks, the most frequently failed checks,
the monthly trend and average marks by preparer, with district, livelihood and date filters.
Only the latest save of each proposal file is counted. To preview it without SharePoint, run
`python samples/make_demo_register.py` and upload `samples/demo_register.csv` on the page.

The register is a plain CSV in SharePoint, so Power BI or Excel can also connect to it
(Get Data → SharePoint folder) for board-level reporting.

## Sectors

The tool appraises any micro-enterprise, not only farming. It reads the livelihood name,
product, narrative, overview and equipment list, picks the closest sector profile, and shows
which one it used above the mark. A reviewer can correct it from that dropdown, and the choice
is saved with the appraisal.

| Sector | Covers |
|---|---|
| Crop cultivation | Vegetables, paddy, tea, fruit, nursery, floriculture, mushrooms |
| Livestock and animal husbandry | Dairy, poultry, goats, piggery, bee keeping |
| Fisheries and aquaculture | Fishing, ornamental fish, dried fish, tank culture |
| Food processing and catering | Bakery, short eats, catering, spices, pickles, dairy products |
| Retail and trading | Grocery, boutique, stall, mobile vending, communication shop |
| Tailoring, garments and handicraft | Sewing, uniforms, batik, handloom, coir, craft |
| Workshop and light manufacturing | Carpentry, welding, fabrication, block making |
| Personal and professional services | Salon, laundry, tuition, photography, printing |
| Transport and hiring | Three wheeler, van, lorry, delivery |
| Repair and technical services | Vehicle, appliance, phone and electrical repair |
| Other micro-enterprise | Anything the detector cannot place |

Each profile sets what a specific overview must contain, what counts as market evidence and as
a sales build-up, which reasons justify a jump in sales, which cost rows must rise with
production, the plausible profit-margin and growth bands, the risks that matter, the item
vocabulary used to match the request to the equipment list, and the licences the business needs
(PHI certificate for food, revenue licence and insurance for transport, trade licence for a
shop). Sector thresholds apply automatically; untick "Use thresholds for the detected sector"
in the sidebar to apply your own sliders to every proposal instead.

**To add or change a sector**, edit `appraisal/sectors.py` only. Copy an entry, change the
words, and the whole rubric follows. No other file needs to change.

## Appraisal rubric (100 marks)

| Criterion | Marks | What is tested |
|---|---|---|
| C1 Eligibility and vulnerability | 15 | Per-capita income vs DCS district poverty line; evidence of deficit/debt; family table complete; household size consistent |
| C2 Completeness and data accuracy | 15 | NIC decoded and matched to age and gender; age consistent across sections; pronouns match the beneficiary; one location throughout; valid phone; key fields filled |
| C3 Livelihood viability and market | 15 | Overview carries this trade's specifics and real figures; named buyers and prices; sales built from volume x price; measurable goals that match projections; licences and permits the trade needs |
| C4 Financial soundness | 20 | 15–20 arithmetic checks; household tables agree with section 6 and the equipment list; realistic sales growth; costs rise with production; plausible margin; household budget balances |
| C5 Relevance of requested support | 10 | Equipment list matches the stated request; each item justified; list numbered in sequence; grant reconciles (and ceiling, if set); quotations referenced |
| C6 Contribution and sustainability | 10 | Beneficiary share of total investment; own contribution itemised; quantified savings; depreciation included |
| C7 Risk analysis | 7 | At least four risks; covers the risks that matter for this trade (weather and wildlife for farming, credit sales and competition for a shop, fuel and accidents for transport); mitigations say who and when |
| C8 Capacity building | 3 | Technical and business/financial training |
| C9 Verification trail | 5 | Preparer and verifier name, designation, date; photos of family and site; approval (not scored while pending) |

**Decision bands:** 75+ Approve · 60–74 Approve with conditions · 45–59 Revise and resubmit · below 45 Not recommended.
Any **critical** finding (identity mismatch, conflicting locations, material arithmetic error,
grant mismatch, missing equipment list) caps the decision at *Revise and resubmit*.

When the AI reviewer is on, its criterion marks are blended with the rule marks (50/50 by
default, adjustable) and its extra findings appear with an "AI" tag. Reviewers can then
override any criterion mark, with a reason.

All thresholds live in `appraisal/config.py`; reviewers can also adjust them in the sidebar.
**Update `DISTRICT_OPL` monthly** from the Department of Census and Statistics
(statistics.gov.lk → Poverty) and add the other BDS districts.

---

## Deploy

### 1. GitHub

```bash
git init bds-appraisal && cd bds-appraisal     # or unzip this folder
git add . && git commit -m "Proposal appraisal tool"
gh repo create berendina/bds-appraisal --private --source . --push
```

GitHub Actions (`.github/workflows/tests.yml`) runs the test suite on every push.
Never commit real proposals or `.streamlit/secrets.toml`; `.gitignore` blocks both.

### 2. SharePoint (Microsoft Graph app registration)

1. In the Microsoft Entra admin centre: **App registrations → New registration**
   (name: `BDS Appraisal Tool`, single tenant). Note the tenant ID and client ID.
2. **Certificates & secrets → New client secret.** Copy the value.
3. **API permissions → Microsoft Graph → Application permissions**, add **Sites.Selected**,
   then **Grant admin consent**.
4. Give the app write access to the one site it needs. A SharePoint admin can run, for example:
   ```powershell
   Grant-PnPAzureADAppSitePermission -AppId <client-id> -DisplayName "BDS Appraisal Tool" `
     -Site https://<tenant>.sharepoint.com/sites/<site> -Permissions Write
   ```
   (or `POST /sites/{site-id}/permissions` through Graph). If your admin prefers, use
   `Sites.ReadWrite.All` instead of steps 3–4, at the cost of tenant-wide access.
5. In the site's document library create a folder named as in `base_folder`
   (default `Livelihood Appraisals`). The app creates `Incoming`, `Appraised/<year>` and
   `Register/appraisal_register.csv` on first use.

### 3. Anthropic API (optional AI reviewer)

Create an API key in the Claude Console (console.anthropic.com) and add it to the secrets.
PDFs are sent as documents so the model reads text, tables and photos; spreadsheets are sent
as a full cell dump plus embedded images. Confirm with management that sending beneficiary
data (names, NIC numbers, photos) to the API is acceptable under BDS data-protection policy;
the tool runs fully without it.

### 4. Streamlit Community Cloud

1. Sign in at share.streamlit.io with GitHub and choose **Create app → from repo**.
2. Repository `berendina/bds-appraisal`, branch `main`, main file `Appraisal.py`.
   Under **Advanced settings** choose Python 3.12 and paste the secrets
   (template: `.streamlit/secrets.toml.example`).
3. Deploy, then share the app URL. People with the link sign in with their role's access code.
   Use the app's sharing settings to restrict viewers to invited email addresses if you want
   a second layer of control. Rotate the codes whenever staff change.

**Alternative hosting.** Because proposals contain personal data, BDS may prefer to host inside
its own Microsoft tenant: the same code runs on Azure App Service
(`streamlit run Appraisal.py --server.port 8000 --server.address 0.0.0.0`) with secrets in
`.streamlit/secrets.toml` or environment variables, and Microsoft Entra sign-in configured
on the App Service.

### Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # edit values
streamlit run Appraisal.py
pytest                                   # PROPOSAL_PDF=path/to/real.pdf pytest to test a real PDF
```

## File formats

* **PDF**: exports of the Excel template. Scanned PDFs have little text; turn on the AI
  reviewer so pages are read visually.
* **XLSX/XLSM**: the template workbook itself. Save it in Excel first so formula results
  are stored; the app warns if they are missing.
* **CSV**: a CSV export of the template sheet (any delimiter). Photos cannot travel in CSV,
  so attach them in SharePoint.

`samples/make_sample.py` builds a fictional, well-prepared crop proposal in XLSX and CSV.
`samples/make_sector_samples.py` builds four more in `samples/sectors/` (grocery shop,
tailoring unit, three wheeler, home bakery) to test the non-farm sectors. All are invented;
never commit a real proposal. `samples/make_demo_register.py` builds a fictional register of 60
appraisals for the dashboard.

## Extending

* Add or reweight checks in `appraisal/checks.py`; each `Check` carries its finding and the fix.
* Different template? Adjust the section patterns in `appraisal/parse.py` (`SECTION_PATTERNS`,
  `ANNUAL_KEYS`, `INVEST_KEYS`).
* For a register in a SharePoint list instead of CSV, replace `append_register` with a
  `POST /sites/{site-id}/lists/{list-id}/items` call.
