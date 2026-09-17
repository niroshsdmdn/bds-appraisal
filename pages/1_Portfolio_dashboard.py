"""Portfolio dashboard: charts over the SharePoint appraisal register."""
from __future__ import annotations

import io

import altair as alt
import pandas as pd
import streamlit as st

from appraisal.config import BANDS, CRITERIA
from appraisal.sharepoint import SharePointClient, SharePointError

st.set_page_config(page_title="Appraisal dashboard", page_icon="🌱", layout="wide")

NAVY, INK = "#1F3A68", "#1C2A3A"
DECISION_COLOURS = {"Approve": "#3E6B48", "Approve with conditions": "#B7791F",
                    "Revise and resubmit": "#C4622D", "Not recommended": "#A5402D"}
CHECK_TITLES = {  # short labels for the most common checks
    "C1.1": "Per-capita vs poverty line", "C1.2": "Economic stress evidence",
    "C1.3": "Family profile", "C1.4": "Household size", "C2.1": "NIC match",
    "C2.2": "Age consistency", "C2.3": "Pronouns", "C2.4": "Location consistency",
    "C2.5": "Contact number", "C2.6": "Key fields", "C3.1": "Specific overview",
    "C3.2": "Market linkage", "C3.3": "Sales build-up", "C3.4": "Goals vs projections",
    "C4.1": "Arithmetic", "C4.2": "Tables agree", "C4.3": "Sales growth",
    "C4.4": "Costs vs production", "C4.5": "Profit margin", "C4.6": "Household budget",
    "C5.1": "Request matches list", "C5.2": "Items justified", "C5.3": "List numbering",
    "C5.4": "Grant reconciles", "C5.5": "Quotations", "C6.1": "Own contribution",
    "C6.2": "Own items listed", "C6.3": "Savings plan", "C6.4": "Depreciation",
    "C7.1": "Number of risks", "C7.2": "Risk coverage", "C7.3": "Mitigation ownership",
    "C8.1": "Technical training", "C8.2": "Business training", "C9.1": "Preparer sign-off",
    "C9.2": "Verifier sign-off", "C9.3": "Photos", "C9.4": "Approval",
}

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,500;8..60,700&display=swap');
h1,h2,h3{font-family:'Source Serif 4',Georgia,serif !important;letter-spacing:-0.01em;}
</style>""", unsafe_allow_html=True)

ss = st.session_state
if ss.get("role") not in {"reviewer", "approver"}:
    st.title("Appraisal dashboard")
    st.write("Sign in as a reviewer or approver on the Appraisal page to see the portfolio dashboard.")
    st.stop()


@st.cache_resource(show_spinner=False)
def client():
    try:
        sec = st.secrets.get("sharepoint")
    except Exception:
        sec = None
    return SharePointClient.from_secrets(sec) if sec else None


@st.cache_data(ttl=300, show_spinner="Reading the appraisal register…")
def load_register() -> list[dict]:
    sp = client()
    return sp.read_register() if sp else []


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["saved_at", "district", "livelihood", "prepared_by", "system_decision", "reviewer_decision",
                "approver_decision", "critical_findings", "failed_checks", "file_sha1", "grant_rs"]:
        if col not in df:
            df[col] = ""
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            df[c] = df[c].fillna("").astype(str).replace("nan", "")
    df["saved_at"] = pd.to_datetime(df["saved_at"], errors="coerce")
    for col in ["total_mark", "grant_rs", *[f"{c}_score" for c in CRITERIA]]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # keep only the latest record for each proposal file
    has_sha = df["file_sha1"].astype(str) != ""
    df = pd.concat([df[has_sha].sort_values("saved_at").groupby("file_sha1").tail(1), df[~has_sha]])

    def final(r):
        for k in ("approver_decision", "reviewer_decision", "system_decision"):
            v = str(r.get(k) or "").strip()
            if v and v.lower() != "nan":
                return v
        return "Unknown"

    df["final_decision"] = df.apply(final, axis=1)
    df["district"] = df["district"].astype(str).replace({"": "Unknown", "nan": "Unknown"})
    df["livelihood"] = df["livelihood"].astype(str).replace({"": "Unknown", "nan": "Unknown"})
    df["preparer"] = (df["prepared_by"].astype(str).str.split(" - ").str[0].str.strip()
                      .replace({"": "Unknown", "nan": "Unknown"}))
    df["critical_findings"] = df["critical_findings"].astype(str).replace("nan", "")
    df["month"] = df["saved_at"].dt.to_period("M").dt.to_timestamp()
    return df


st.title("Appraisal dashboard")
rows = []
try:
    rows = load_register()
except SharePointError as exc:
    st.error(f"Could not read the register from SharePoint: {exc}")
with st.expander("Use a register file instead", expanded=not rows):
    up = st.file_uploader("appraisal_register.csv", type=["csv"])
    if up is not None:
        rows = pd.read_csv(io.BytesIO(up.getvalue())).to_dict("records")
if not rows:
    st.write("No appraisals yet. Save appraisals to SharePoint from the main page, or upload a register CSV above.")
    st.stop()

df = prepare(pd.DataFrame(rows))

# ---- filters
with st.sidebar:
    st.markdown("### Filters")
    districts = sorted(df["district"].unique())
    pick_d = st.multiselect("District", districts, default=districts)
    livelihoods = sorted(df["livelihood"].unique())
    pick_l = st.multiselect("Livelihood", livelihoods, default=livelihoods)
    dmin, dmax = df["saved_at"].min(), df["saved_at"].max()
    period = st.date_input("Saved between", (dmin.date(), dmax.date())) if pd.notna(dmin) else None
view = df[df["district"].isin(pick_d)]
view = view[view["livelihood"].isin(pick_l)]
if period and len(period) == 2:
    view = view[(view["saved_at"].dt.date >= period[0]) & (view["saved_at"].dt.date <= period[1])]
if view.empty:
    st.warning("No appraisals match these filters. Widen the district, livelihood or date range.")
    st.stop()

# ---- headline numbers
approved = view["final_decision"].isin(["Approve", "Approve with conditions"])
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Proposals appraised", len(view))
k2.metric("Average mark", f"{view['total_mark'].mean():.1f}")
k3.metric("Approved (incl. conditions)", f"{approved.mean():.0%}")
k4.metric("With critical findings", int((view["critical_findings"] != "").sum()))
k5.metric("Grant approved, Rs.", f"{view.loc[approved, 'grant_rs'].sum():,.0f}")

band_rules = pd.DataFrame({"mark": [b[0] for b in BANDS if b[0] > 0]})

# ---- row 1: mark distribution + decisions by district
c1, c2 = st.columns(2)
with c1:
    st.subheader("Marks")
    hist = alt.Chart(view).mark_bar(color=NAVY).encode(
        alt.X("total_mark:Q", bin=alt.Bin(step=5), title="Appraisal mark", scale=alt.Scale(domain=[0, 100])),
        alt.Y("count():Q", title="Proposals"))
    rules = alt.Chart(band_rules).mark_rule(strokeDash=[4, 3], color=INK).encode(x="mark:Q")
    st.altair_chart(hist + rules, width="stretch")
    st.caption("Dashed lines mark the decision bands at 45, 60 and 75.")
with c2:
    st.subheader("Decisions by district")
    order = list(DECISION_COLOURS)
    st.altair_chart(alt.Chart(view).mark_bar().encode(
        alt.Y("district:N", title=None, sort="-x"),
        alt.X("count():Q", title="Proposals"),
        alt.Color("final_decision:N", title="Decision",
                  scale=alt.Scale(domain=order, range=list(DECISION_COLOURS.values()))),
        alt.Order("final_decision:N"),
        tooltip=["district", "final_decision", "count()"]), width="stretch")

# ---- row 2: criterion strength + most common failures
c3, c4 = st.columns(2)
with c3:
    st.subheader("Where proposals lose marks")
    crit = []
    for cid, meta in CRITERIA.items():
        col = f"{cid}_score"
        if col in view and view[col].notna().any():
            crit.append({"criterion": f"{cid} {meta['name']}",
                         "achieved": view[col].mean() / meta["max"]})
    if crit:
        cdf = pd.DataFrame(crit)
        st.altair_chart(alt.Chart(cdf).mark_bar().encode(
            alt.Y("criterion:N", sort="x", title=None, axis=alt.Axis(labelLimit=320)),
            alt.X("achieved:Q", title="Average share of marks achieved", axis=alt.Axis(format="%"),
                  scale=alt.Scale(domain=[0, 1])),
            color=alt.condition(alt.datum.achieved < 0.6, alt.value("#A5402D"), alt.value(NAVY)),
            tooltip=["criterion", alt.Tooltip("achieved:Q", format=".0%")]), width="stretch")
        st.caption("Red bars (below 60%) show what to cover in CDC proposal-writing training.")
    else:
        st.write("Criterion scores appear once appraisals are saved with this version of the tool.")
with c4:
    st.subheader("Most frequent failed checks")
    if True:
        fails = view["failed_checks"].astype(str).str.split(";").explode().str.strip()
        fails = fails[(fails != "") & (fails != "nan")]
        if not fails.empty:
            fdf = fails.value_counts().rename_axis("check").reset_index(name="proposals")
            fdf["label"] = fdf["check"] + " " + fdf["check"].map(CHECK_TITLES).fillna("")
            fdf["share"] = fdf["proposals"] / len(view)
            st.altair_chart(alt.Chart(fdf.head(10)).mark_bar(color="#A5402D").encode(
                alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=320)),
                alt.X("share:Q", title="Share of proposals failing", axis=alt.Axis(format="%")),
                tooltip=["label", "proposals", alt.Tooltip("share:Q", format=".0%")]), width="stretch")
        else:
            st.write("No failed checks in this selection.")

# ---- row 3: trend + preparer
c5, c6 = st.columns(2)
with c5:
    st.subheader("Average mark by month")
    trend = view.groupby("month", as_index=False).agg(mark=("total_mark", "mean"), n=("total_mark", "size"))
    st.altair_chart(alt.Chart(trend).mark_line(point=True, color=NAVY).encode(
        alt.X("month:T", title=None), alt.Y("mark:Q", title="Average mark", scale=alt.Scale(domain=[0, 100])),
        tooltip=[alt.Tooltip("month:T", format="%b %Y"), alt.Tooltip("mark:Q", format=".1f"), "n"]),
        width="stretch")
with c6:
    st.subheader("Average mark by preparer")
    prep = view.groupby("preparer", as_index=False).agg(mark=("total_mark", "mean"), n=("total_mark", "size"))
    st.altair_chart(alt.Chart(prep).mark_bar(color=NAVY).encode(
        alt.Y("preparer:N", sort="-x", title=None),
        alt.X("mark:Q", title="Average mark", scale=alt.Scale(domain=[0, 100])),
        tooltip=["preparer", alt.Tooltip("mark:Q", format=".1f"), "n"]), width="stretch")
    st.caption("Use for coaching, not ranking: a CDC with few proposals can swing widely.")

# ---- table
st.subheader("Appraisals")
cols = [c for c in ["saved_at", "beneficiary", "district", "livelihood", "grant_rs", "total_mark",
                    "system_decision", "final_decision", "critical_findings", "preparer", "folder"] if c in view]
st.dataframe(view[cols].sort_values("saved_at", ascending=False), hide_index=True, width="stretch",
             column_config={"total_mark": st.column_config.ProgressColumn("Mark", min_value=0, max_value=100,
                                                                          format="%.1f"),
                            "grant_rs": st.column_config.NumberColumn("Grant (Rs.)", format="%,.0f"),
                            "saved_at": st.column_config.DatetimeColumn("Saved", format="YYYY-MM-DD")})
st.download_button("Download filtered register", view[cols].to_csv(index=False), "appraisal_register_filtered.csv",
                   "text/csv")
