"""BDS livelihood proposal appraisal tool (Streamlit)."""
from __future__ import annotations

import hmac
import json
import re
from dataclasses import asdict
from datetime import datetime

import pandas as pd
import streamlit as st

from appraisal.ai_review import DEFAULT_MODEL, merge_ai, run_ai_review
from appraisal.checks import appraise
from appraisal.config import BANDS, CRITERIA, NATIONAL_OPL, OPL_AS_OF, Settings
from appraisal.extract import extract
from appraisal.parse import parse
from appraisal.report import build_excel, build_html
from appraisal.sectors import options as sector_options
from appraisal.sharepoint import SharePointClient, SharePointError

st.set_page_config(page_title="BDS proposal appraisal", page_icon="🌱", layout="wide")

ROLES = {
    "writer": "Proposal writer (CDC)",
    "reviewer": "Reviewer / verifier (ARM)",
    "approver": "Approver",
}
DECISIONS = [b[1] for b in BANDS]
STATUS_MARK = {"pass": ("✓", "#3E6B48"), "partial": ("◐", "#B7791F"),
               "fail": ("✕", "#A5402D"), "na": ("–", "#7A8594"), "info": ("•", "#1F3A68")}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,700&display=swap');
:root{--ink:#1C2A3A;--navy:#1F3A68;--go:#3E6B48;--cond:#B7791F;--revise:#C4622D;--stop:#A5402D;--line:#D5DAE1;}
h1,h2,h3,.bds-serif{font-family:'Source Serif 4',Georgia,serif !important;letter-spacing:-0.01em;}
.bds-name{font-family:'Source Serif 4',Georgia,serif;font-size:1.9rem;font-weight:700;color:var(--navy);line-height:1.15;margin:0}
.bds-sub{color:#56657A;margin:.2rem 0 0}
.bds-score{font-family:'Source Serif 4',Georgia,serif;font-size:3.6rem;font-weight:700;line-height:1;color:var(--ink)}
.bds-score small{font-size:1.1rem;font-weight:500;color:#56657A}
.bds-decision{font-family:'Source Serif 4',Georgia,serif;font-size:1.45rem;font-weight:700;margin:.3rem 0 0}
.bds-ruler{position:relative;display:flex;height:12px;margin:1.6rem 0 .35rem;}
.bds-ruler div.seg{height:100%;opacity:.28}
.bds-ruler div.seg.on{opacity:1}
.bds-ruler .mark{position:absolute;top:-9px;width:3px;height:30px;background:var(--ink);transform:translateX(-50%)}
.bds-ruler .mark span{position:absolute;top:-1.35rem;left:50%;transform:translateX(-50%);font-size:.8rem;font-weight:600;white-space:nowrap}
.bds-ticks{position:relative;height:1.2rem;font-size:.75rem;color:#56657A}
.bds-ticks span{position:absolute;transform:translateX(-50%)}
.bds-check{padding:.45rem 0;border-bottom:1px solid var(--line)}
.bds-check .t{font-weight:600}
.bds-check .m{float:right;color:#56657A;font-variant-numeric:tabular-nums}
.bds-check .fix{color:#34506F;margin-top:.15rem}
.bds-flag{border-left:4px solid var(--stop);padding:.5rem .8rem;margin:.4rem 0;background:rgba(165,64,45,.06)}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# access
# ----------------------------------------------------------------------------
def access_codes() -> dict[str, str]:
    try:
        return dict(st.secrets.get("access", {}).get("codes", {}))
    except Exception:
        return {}


def sign_in() -> None:
    codes = access_codes()
    ss = st.session_state
    with st.sidebar:
        st.markdown("### Sign in")
        if ss.get("role"):
            st.write(f"**{ss.user}**  \n{ROLES[ss.role]}")
            if st.button("Sign out", width="stretch"):
                for k in ("role", "user"):
                    ss.pop(k, None)
                st.rerun()
            return
        name = st.text_input("Your name")
        if codes:
            code = st.text_input("Access code", type="password")
            if st.button("Sign in", type="primary", width="stretch"):
                role = next((r for r, c in codes.items() if c and hmac.compare_digest(str(c), code)), None)
                if not name.strip():
                    st.error("Enter your name so the appraisal record shows who did it.")
                elif role not in ROLES:
                    st.error("That access code is not valid. Ask the MLE unit for your code.")
                else:
                    ss.user, ss.role = name.strip(), role
                    st.rerun()
        else:
            st.warning("No access codes are configured, so anyone with the link can sign in. "
                       "Add codes to the app secrets before sharing the link.")
            role = st.selectbox("Role", list(ROLES), format_func=ROLES.get)
            if st.button("Continue", type="primary", width="stretch") and name.strip():
                ss.user, ss.role = name.strip(), role
                st.rerun()


def audit(action: str, detail: str = "") -> None:
    st.session_state.setdefault("audit", []).append({
        "when": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "who": st.session_state.get("user", ""), "role": st.session_state.get("role", ""),
        "action": action, "detail": detail})


# ----------------------------------------------------------------------------
# services
# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def sharepoint_client():
    try:
        sec = st.secrets.get("sharepoint")
    except Exception:
        sec = None
    if not sec:
        return None
    return SharePointClient.from_secrets(sec)


def anthropic_settings() -> tuple[str | None, str]:
    try:
        sec = st.secrets.get("anthropic", {})
        return sec.get("api_key"), sec.get("model", DEFAULT_MODEL)
    except Exception:
        return None, DEFAULT_MODEL


@st.cache_data(show_spinner=False, max_entries=30)
def load(file_name: str, data: bytes):
    ex = extract(file_name, data)
    return ex, parse(ex)


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s or "proposal").strip("_")[:60]


# ----------------------------------------------------------------------------
# sidebar settings
# ----------------------------------------------------------------------------
def sidebar_settings(role: str) -> tuple[Settings, bool, float]:
    api_key, model = anthropic_settings()
    with st.sidebar:
        st.divider()
        st.markdown("### Appraisal settings")
        use_ai = st.toggle("AI reviewer reads the full file", value=bool(api_key), disabled=not api_key,
                           help="Sends the proposal to the Claude API for a second opinion, "
                                "including photos and narrative quality.")
        if not api_key:
            st.caption("Add an Anthropic API key to the app secrets to enable the AI reviewer.")
        ai_weight = 0.5
        with st.expander("Thresholds", expanded=False):
            editable = role != "writer"
            sector_thresholds = st.checkbox(
                "Use thresholds for the detected sector", value=True, disabled=not editable,
                help="Growth and profit-margin bands differ by trade: a grocery shop cannot earn a "
                     "farm's margin, and a service can. Untick to apply the sliders below to every sector.")
            opl = st.number_input("Poverty line override, Rs. per person per month",
                                  min_value=0, value=0, step=100, disabled=not editable,
                                  help=f"0 uses the DCS district line ({OPL_AS_OF}) when the district is "
                                       f"recognised, otherwise the national line (Rs. {NATIONAL_OPL:,}).")
            share = st.slider("Minimum beneficiary contribution", 0, 60, 25, format="%d%%", disabled=not editable)
            ceiling = st.number_input("Grant ceiling per family (Rs., 0 = none)", min_value=0, value=0,
                                      step=5000, disabled=not editable)
            growth = st.slider("Sales growth treated as unrealistic above", 50, 300, 100, 10,
                               format="%d%%", disabled=not editable)
            margin = st.slider("Profit margin needing evidence above", 20, 80, 45, format="%d%%",
                               disabled=not editable)
            if use_ai:
                ai_weight = st.slider("Weight of AI scores in final mark", 0, 100, 50, 10,
                                      format="%d%%", disabled=not editable) / 100
        settings = Settings(
            poverty_line=float(opl) or None,
            min_beneficiary_share=share / 100, max_grant=float(ceiling) or None,
            sales_growth_limit=growth / 100, sales_growth_caution=min(0.5, growth / 200),
            margin_ok=margin / 100, margin_limit=min(0.95, margin / 100 + 0.15),
            extra={"sector_thresholds": sector_thresholds},
        )
        st.caption(f"Model: {model}" if use_ai else "Rule engine only")
        sp = sharepoint_client()
        st.divider()
        st.markdown("### SharePoint")
        if sp:
            st.caption(f"{sp.hostname}/{sp.site_path} › {sp.drive_name} › {sp.base}")
        else:
            st.caption("Not connected. Reports can still be downloaded.")
    return settings, use_ai, ai_weight


# ----------------------------------------------------------------------------
# rendering helpers
# ----------------------------------------------------------------------------
def ruler(total: float, key: str) -> str:
    segs = []
    bounds = sorted([(b[0], b[2]) for b in BANDS])
    for i, (lo, k) in enumerate(bounds):
        hi = bounds[i + 1][0] if i + 1 < len(bounds) else 100
        segs.append(f'<div class="seg{" on" if k == key else ""}" '
                    f'style="width:{hi - lo}%;background:var(--{k})"></div>')
    ticks = "".join(f'<span style="left:{b}%">{b}</span>' for b in (0, 45, 60, 75, 100))
    return (f'<div class="bds-ruler">{"".join(segs)}'
            f'<div class="mark" style="left:{min(max(total, 0.5), 99.5)}%"><span>{total:.1f}</span></div></div>'
            f'<div class="bds-ticks">{ticks}</div>')


def check_html(c) -> str:
    sym, col = STATUS_MARK.get(c.status, ("•", "#1F3A68"))
    marks = "" if c.status in {"na", "info"} else f"{c.earned:g} of {c.weight:g}"
    tag = " · AI" if c.source == "ai" else ""
    fix = f'<div class="fix">Fix: {c.suggestion}</div>' if c.suggestion and c.status != "pass" else ""
    return (f'<div class="bds-check"><span class="m">{marks}</span>'
            f'<span style="color:{col};font-weight:700">{sym}</span> '
            f'<span class="t">{c.title}{tag}</span><div>{c.finding}</div>{fix}</div>')


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
sign_in()
ss = st.session_state
if not ss.get("role"):
    st.title("Livelihood proposal appraisal")
    st.write("Sign in from the sidebar to appraise a proposal. Writers can check a draft before "
             "submitting it; reviewers and approvers record their decision against the same marks.")
    st.stop()

role = ss.role
settings, use_ai, ai_weight = sidebar_settings(role)
sp = sharepoint_client()

st.title("Livelihood proposal appraisal")

# ---- choose a proposal
src_tabs = st.tabs(["Upload a file", "Pick from SharePoint"])
with src_tabs[0]:
    up = st.file_uploader("Proposal file", type=["pdf", "xlsx", "xlsm", "csv"],
                          help="Use the BDS livelihood proposal template. PDF, Excel or CSV export.")
    if up is not None:
        ss.file = {"name": up.name, "data": up.getvalue(), "origin": "upload"}
with src_tabs[1]:
    if not sp:
        st.info("SharePoint is not configured for this app. See the README for setup.")
    else:
        try:
            items = sp.list_folder("Incoming")
            if not items:
                st.write("No proposals are waiting in the Incoming folder.")
            else:
                labels = {f"{i['name']}  ({i['lastModifiedDateTime'][:10]})": i for i in items}
                pick = st.selectbox("Proposal waiting for appraisal", list(labels))
                if st.button("Open this proposal"):
                    it = labels[pick]
                    ss.file = {"name": it["name"], "data": sp.download(it["id"]), "origin": "sharepoint"}
                    st.rerun()
        except SharePointError as exc:
            st.error(f"Could not read SharePoint: {exc}")

if not ss.get("file"):
    st.write("Upload a proposal to see its appraisal mark, the reasons behind it and how to raise it.")
    st.stop()

f = ss.file
try:
    ex, prop = load(f["name"], f["data"])
except Exception as exc:  # show a direct, fixable message
    st.error(f"This file could not be read: {exc}")
    st.stop()

if ss.get("loaded_sha") != ex.sha1:
    ss.loaded_sha = ex.sha1
    ss.overrides = {}
    ss.audit = []
    ss.reviewer = {}
    ss.approver = {}
    audit("Opened proposal", f"{f['name']} ({f['origin']}, sha1 {ex.sha1})")

appraisal = appraise(prop, settings, sector=ss.get(f"sector_{ex.sha1}"))
ai_key = f"ai_{ex.sha1}"
api_key, model = anthropic_settings()
if use_ai and api_key and ai_key not in ss:
    with st.status("AI reviewer is reading the whole proposal…", expanded=False) as s:
        try:
            ss[ai_key] = run_ai_review(ex, appraisal, api_key, model)
            audit("AI review", f"model {model}")
            s.update(label="AI review complete", state="complete")
        except Exception as exc:
            ss[ai_key] = {"_error": str(exc)}
            s.update(label="AI review failed; showing rule-based marks", state="error")
ai = ss.get(ai_key) if use_ai else None
if ai and "_error" not in ai:
    merge_ai(appraisal, ai, ai_weight)
elif ai and "_error" in ai:
    st.warning(f"AI review unavailable: {ai['_error']}")
for cid, (score, note) in ss.get("overrides", {}).items():
    appraisal.criteria[cid].final_score = score
    appraisal.criteria[cid].reviewer_note = note

for w in ex.warnings:
    st.warning(w)

dec = appraisal.decision()

# ---- headline
left, right = st.columns([1.1, 1])
with left:
    st.markdown(f'<div class="bds-name">{prop.name or f["name"]}</div>'
                f'<p class="bds-sub">{prop.livelihood or prop.product or "Livelihood not stated"} · '
                f'{prop.address or prop.district or "location not stated"} · '
                f'grant {("Rs. " + format(prop.equipment_total.get("bds") or 0, ",.0f"))}</p>',
                unsafe_allow_html=True)
    opts = sector_options()
    ids = [i for i, _ in opts]
    current = appraisal.context["sector"]
    auto = appraisal.context["sector_detected"]
    picked = st.selectbox(
        "Sector used for the checks", ids, index=ids.index(current),
        format_func=lambda i: dict(opts)[i] + (" (detected)" if auto and i == current else ""),
        help="Risks, market evidence, margin bands and item vocabulary come from this sector. "
             "Change it if the proposal was read as the wrong trade.")
    if picked != current:
        ss[f"sector_{ex.sha1}"] = picked
        audit("Sector changed", f"{current} -> {picked}")
        st.rerun()
    if appraisal.critical:
        st.markdown("".join(f'<div class="bds-flag"><b>Critical: {c.title}.</b> {c.finding}</div>'
                            for c in appraisal.critical), unsafe_allow_html=True)
    if ai and "summary" in ai:
        st.markdown(f"**AI reviewer:** {ai['summary']}")
with right:
    st.markdown(f'<div class="bds-score">{appraisal.total:.1f}<small> / 100</small></div>'
                f'<div class="bds-decision" style="color:var(--{dec["key"]})">{dec["label"]}</div>'
                f'<p class="bds-sub">{dec["guidance"]}</p>{ruler(appraisal.total, dec["key"])}',
                unsafe_allow_html=True)

tabs = st.tabs(["Findings", "Raise the mark", "Proposal data", "Review and approve", "Save and export"])

# ---- findings
with tabs[0]:
    for cid, cs in appraisal.criteria.items():
        checks = [c for c in appraisal.checks if c.criterion == cid]
        weak = any(c.status in {"fail", "partial"} for c in checks)
        ai_txt = f" · AI {cs.ai_score:g}" if cs.ai_score is not None else ""
        with st.expander(f"{cs.name}: {cs.score:.1f} of {cs.max:g}{ai_txt}", expanded=weak and cs.score < cs.max * 0.6):
            st.caption(CRITERIA[cid]["question"])
            st.progress(min(cs.score / cs.max, 1.0))
            st.markdown("".join(check_html(c) for c in checks), unsafe_allow_html=True)
            if cs.reviewer_note:
                st.info(f"Reviewer adjusted this mark: {cs.reviewer_note}")
    if ai and ai.get("disagreements"):
        st.subheader("Where the AI reviewer disagrees with the rules")
        for d in ai["disagreements"]:
            st.markdown(f"- **{d.get('check')}**: {d.get('comment')}")
    if ai and ai.get("photo_observations"):
        st.subheader("Photos")
        st.write(ai["photo_observations"])

# ---- improvement
with tabs[1]:
    def show_path(target: int, label: str) -> None:
        path = appraisal.path_to(target)
        gain = sum(r["mark_gain"] for r in path)
        st.write(f"The proposal needs {target - appraisal.total:.1f} more marks. "
                 f"These {len(path)} fixes recover about {gain:.1f}"
                 + (", including every critical finding" if appraisal.critical else "") + ":")
        for i, r in enumerate(path, 1):
            crit_tag = "critical · " if r["severity"] == "critical" else ""
            st.markdown(f"{i}. **{r['action']}** ({crit_tag}+{r['mark_gain']:.1f}, {r['criterion_name']})  \n"
                        f"   <span style='color:#56657A'>{r['issue']}</span>", unsafe_allow_html=True)

    nxt = next((b for b in reversed(BANDS) if b[0] > appraisal.total), None)
    if nxt:
        st.subheader(f"Reach {nxt[1].lower()} ({nxt[0]}+)")
        show_path(nxt[0], nxt[1])
        top = BANDS[0]
        if nxt[0] != top[0]:
            with st.expander(f"Path to {top[1].lower()} ({top[0]}+)"):
                show_path(top[0], top[1])
        if appraisal.critical:
            st.warning("Critical findings cap the decision at 'Revise and resubmit' until they are fixed, "
                       "whatever the mark.")
    else:
        st.success("The proposal is in the top band. Remaining suggestions are optional.")
    plan = appraisal.improvement_plan()
    if plan:
        st.subheader("Every suggestion, most serious first")
        df = pd.DataFrame(plan)[["severity", "criterion_name", "issue", "action", "mark_gain", "source"]]
        df.columns = ["Severity", "Criterion", "Issue", "Action", "Marks", "Source"]
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"Marks": st.column_config.NumberColumn(format="+%.1f")})

# ---- data
with tabs[2]:
    a, b = st.columns(2)
    with a:
        st.subheader("At a glance")
        st.dataframe(pd.DataFrame(prop.as_summary_rows(), columns=["Item", "Value"]),
                     hide_index=True, width="stretch")
        if prop.members:
            st.subheader("Family")
            st.dataframe(pd.DataFrame([asdict(m) for m in prop.members]), hide_index=True,
                         width="stretch")
    with b:
        st.subheader("Household budget per month")
        rows = []
        for label, bud in (("Current", prop.current), ("Expected", prop.expected)):
            for inc in bud.incomes:
                rows.append([label, "Income", inc.source, inc.amount])
            for k, v in bud.expenses.items():
                rows.append([label, "Expense", k, v])
        if rows:
            st.dataframe(pd.DataFrame(rows, columns=["Period", "Type", "Item", "Rs."]),
                         hide_index=True, width="stretch")
        if prop.annual:
            st.subheader("Livelihood, annual")
            st.dataframe(pd.DataFrame([[k, *(v + [None, None])[:2]] for k, v in prop.annual.items()],
                                      columns=["Line", "Current", "Year 1"]),
                         hide_index=True, width="stretch")
    if prop.equipment:
        st.subheader("Requested equipment and inputs")
        st.dataframe(pd.DataFrame([asdict(e) for e in prop.equipment]), hide_index=True,
                     width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Risks")
        st.dataframe(pd.DataFrame(prop.risks, columns=["Risk", "Mitigation"]), hide_index=True,
                     width="stretch")
    with c2:
        st.subheader("Training")
        st.dataframe(pd.DataFrame(prop.trainings, columns=["Training", "Details"]), hide_index=True,
                     width="stretch")
    photos = [im for im in ex.images if im.data and im.width >= 90 and im.height >= 90]
    if photos:
        st.subheader("Photos")
        st.image([im.data for im in photos], width=220)
    with st.expander("Everything read from the file"):
        st.text_area("Text", ex.full_text, height=260)
        st.text_area("Tables", ex.grid_as_text(), height=260)

# ---- review & approve
with tabs[3]:
    if role == "writer":
        st.write("Reviewers and approvers record their decisions here. As the writer, use "
                 "**Raise the mark** to fix issues before you submit.")
    else:
        st.subheader("Adjust marks")
        st.caption("Change a final mark only with a reason; the reason is saved in the report.")
        base = pd.DataFrame([{
            "ID": cs.id, "Criterion": cs.name, "Max": cs.max, "Rules": cs.rule_score,
            "AI": cs.ai_score, "Final": cs.score, "Reason for change": cs.reviewer_note,
        } for cs in appraisal.criteria.values()])
        if base["AI"].isna().all():
            base = base.drop(columns=["AI"])
        edited = st.data_editor(
            base, hide_index=True, width="stretch", key=f"editor_{ex.sha1}",
            disabled=["ID", "Criterion", "Max", "Rules", "AI"],
            column_config={
                "Rules": st.column_config.NumberColumn(format="%.2f"),
                "AI": st.column_config.NumberColumn(format="%.2f"),
                "Final": st.column_config.NumberColumn(min_value=0.0, step=0.25, format="%.2f")})
        if st.button("Apply mark changes"):
            new, problems = {}, []
            for _, r in edited.iterrows():
                cs = appraisal.criteria[r["ID"]]
                final = float(r["Final"])
                if final > cs.max:
                    problems.append(f"{r['ID']} cannot exceed {cs.max:g}.")
                    continue
                if abs(final - cs.score) > 1e-6 or (r["Reason for change"] or "") != cs.reviewer_note:
                    if not str(r["Reason for change"] or "").strip():
                        problems.append(f"Give a reason for changing {r['ID']}.")
                        continue
                    new[r["ID"]] = (final, str(r["Reason for change"]).strip())
            if problems:
                st.error(" ".join(problems))
            else:
                ss.overrides = {**ss.get("overrides", {}), **new}
                for k, (sc, note) in new.items():
                    audit("Mark changed", f"{k} -> {sc} ({note})")
                st.rerun()

        st.subheader("Reviewer recommendation")
        rv = ss.setdefault("reviewer", {})
        rv_dec = st.radio("Recommendation", DECISIONS, horizontal=True,
                          index=DECISIONS.index(rv.get("decision", dec["label"])),
                          disabled=role != "reviewer", key="rv_dec")
        rv_txt = st.text_area("Reviewer comments", rv.get("comment", ""), disabled=role != "reviewer")
        conditions = st.text_area("Conditions (one per line)", "\n".join(rv.get("conditions", [])) or
                                  "\n".join((ai or {}).get("conditions", [])),
                                  disabled=role != "reviewer")
        if role == "reviewer" and st.button("Record recommendation", type="primary"):
            ss.reviewer = {"decision": rv_dec, "comment": rv_txt, "by": ss.user,
                           "conditions": [c for c in conditions.splitlines() if c.strip()]}
            audit("Reviewer recommendation", f"{rv_dec}: {rv_txt}")
            st.success("Recommendation recorded. Save it to SharePoint from the next tab.")

        st.subheader("Approval")
        if role != "approver":
            st.caption("Only an approver can record the final decision.")
        else:
            if dec["capped"] or appraisal.critical:
                st.warning("Critical findings are open. Approving now needs a written justification.")
            ap_dec = st.radio("Final decision", DECISIONS, horizontal=True,
                              index=DECISIONS.index(ss.get("approver", {}).get("decision",
                                                    ss.get("reviewer", {}).get("decision", dec["label"]))))
            ap_txt = st.text_area("Approver comments", ss.get("approver", {}).get("comment", ""))
            if st.button("Record decision", type="primary"):
                if ap_dec.startswith("Approve") and appraisal.critical and len(ap_txt.strip()) < 20:
                    st.error("Explain why the proposal can be approved despite the critical findings.")
                else:
                    ss.approver = {"decision": ap_dec, "comment": ap_txt, "by": ss.user}
                    audit("Approver decision", f"{ap_dec}: {ap_txt}")
                    st.success("Decision recorded. Save it to SharePoint from the next tab.")

# ---- save & export
with tabs[4]:
    meta = {
        "file_name": f["name"], "user": ss.user, "role": ROLES[role],
        "ai_model": (ai or {}).get("_model") if ai and "_error" not in ai else None,
        "ai": ai if ai and "_error" not in ai else None,
        "reviewer_decision": ss.get("reviewer", {}).get("decision", ""),
        "reviewer_comment": ss.get("reviewer", {}).get("comment", ""),
        "approver_decision": ss.get("approver", {}).get("decision", ""),
        "approver_comment": ss.get("approver", {}).get("comment", ""),
        "conditions": ss.get("reviewer", {}).get("conditions", []),
        "audit": ss.get("audit", []),
    }
    stem = safe_name(prop.name or f["name"].rsplit(".", 1)[0])
    xlsx = build_excel(prop, appraisal, meta)
    html_page = build_html(prop, appraisal, meta)
    payload = {"file": f["name"], "sha1": ex.sha1, "meta": {k: v for k, v in meta.items() if k != "ai"},
               "ai": meta["ai"], "appraisal": appraisal.to_dict()}
    d1, d2, d3 = st.columns(3)
    d1.download_button("Download Excel report", xlsx, f"{stem}_appraisal.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       width="stretch")
    d2.download_button("Download printable report", html_page, f"{stem}_appraisal.html", "text/html",
                       width="stretch")
    d3.download_button("Download data (JSON)", json.dumps(payload, default=str, indent=2),
                       f"{stem}_appraisal.json", "application/json", width="stretch")

    st.divider()
    if not sp:
        st.info("Connect SharePoint in the app secrets to keep an official record of each appraisal.")
    elif role == "writer":
        st.write("Submit this proposal for review. It will appear in the reviewers' Incoming list.")
        if st.button("Submit to SharePoint for review", type="primary"):
            try:
                sp.upload(f"Incoming/{f['name']}", f["data"])
                sp.upload(f"Incoming/_prechecks/{stem}_precheck.json",
                          json.dumps(payload, default=str, indent=2).encode(), "application/json")
                audit("Submitted for review", f"Incoming/{f['name']}")
                st.success("Submitted. Reviewers can now open it from SharePoint.")
            except SharePointError as exc:
                st.error(f"Upload failed: {exc}")
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        folder = f"Appraised/{datetime.now():%Y}/{stem}_{stamp}"
        st.write(f"Saves the original file, both reports and the data to `{folder}` "
                 "and adds a row to the appraisal register.")
        if st.button("Save appraisal to SharePoint", type="primary"):
            try:
                with st.spinner("Saving…"):
                    sp.upload(f"{folder}/{f['name']}", f["data"])
                    sp.upload(f"{folder}/{stem}_appraisal.xlsx", xlsx,
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    sp.upload(f"{folder}/{stem}_appraisal.html", html_page.encode(), "text/html")
                    sp.upload(f"{folder}/{stem}_appraisal.json",
                              json.dumps(payload, default=str, indent=2).encode(), "application/json")
                    sp.append_register({
                        "saved_at": datetime.now().isoformat(timespec="seconds"),
                        "beneficiary": prop.name or "", "nic": prop.nic or "",
                        "district": prop.district or "", "livelihood": prop.livelihood or "",
                        "sector": appraisal.context.get("sector_name", ""),
                        "grant_rs": prop.equipment_total.get("bds") or "",
                        "total_mark": appraisal.total, "system_decision": dec["label"],
                        "critical_findings": ";".join(c.id for c in appraisal.critical),
                        "reviewer_decision": meta["reviewer_decision"],
                        "approver_decision": meta["approver_decision"],
                        "saved_by": ss.user, "role": role, "folder": folder, "file_sha1": ex.sha1,
                        "prepared_by": prop.prepared_by or "", "verified_by": prop.verified_by or "",
                        "failed_checks": ";".join(c.id for c in appraisal.checks if c.status == "fail"),
                        "partial_checks": ";".join(c.id for c in appraisal.checks if c.status == "partial"),
                        **{f"{cid}_score": round(cs.score, 2) for cid, cs in appraisal.criteria.items()},
                    })
                audit("Saved to SharePoint", folder)
                st.success(f"Saved to {folder}.")
            except SharePointError as exc:
                st.error(f"Save failed: {exc}")
        with st.expander("Appraisal register"):
            try:
                reg = sp.read_register()
                if reg:
                    st.dataframe(pd.DataFrame(reg), hide_index=True, width="stretch")
                else:
                    st.write("No appraisals saved yet.")
            except SharePointError as exc:
                st.error(f"Could not read the register: {exc}")
