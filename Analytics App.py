import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Engagement Analytics Dashboard", layout="wide")

# =========================
# Helpers
# =========================
def clean_text(x) -> str:
    if x is None:
        return ""
    if isinstance(x, float) and np.isnan(x):
        return ""
    return (
        str(x)
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\u00a0", " ")
        .strip()
    )


def make_unique(cols):
    seen = {}
    out = []
    for c in cols:
        c = clean_text(c)
        if c == "":
            c = "Unnamed"
        if c not in seen:
            seen[c] = 0
            out.append(c)
        else:
            seen[c] += 1
            out.append(f"{c}_{seen[c]}")
    return out


def normalize_binary(x) -> int:
    try:
        if x is None:
            return 0
        if isinstance(x, float) and np.isnan(x):
            return 0
        s = str(x).strip().lower()
        return 1 if s in {"yes", "y", "true", "1", "attended", "present"} else 0
    except Exception:
        return 0


def parse_date_safe(x):
    try:
        return pd.to_datetime(x, errors="coerce")
    except Exception:
        return pd.NaT


def parse_event_date(val):
    """
    Handles:
      - Timestamp-like
      - '2026-01-24 00:00:00'
      - '28-30.01.2026'  (takes start date)
      - '28.01 to 30.01.2026' (takes start date)
    Returns Timestamp (normalized) or NaT.
    """
    try:
        ts = pd.to_datetime(val, errors="coerce")
        if pd.notna(ts):
            return ts.normalize()
    except Exception:
        pass

    s = clean_text(val)
    if not s:
        return pd.NaT

    m = re.search(r"(\d{1,2})\D+(\d{1,2})\D+(\d{4})", s)
    if not m:
        return pd.NaT

    dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
    try:
        return pd.Timestamp(int(yyyy), int(mm), int(dd))
    except Exception:
        return pd.NaT


def best_matching_col(df: pd.DataFrame, keywords, hard_excludes=None):
    hard_excludes = hard_excludes or []
    scored = []
    for c in df.columns:
        cl = clean_text(c).lower()
        if any(ex in cl for ex in hard_excludes):
            continue

        hit_strength = 0
        for k in keywords:
            if k in cl:
                hit_strength = max(hit_strength, len(k))
        if hit_strength > 0:
            scored.append((c, hit_strength, df[c].notna().sum()))

    if not scored:
        return None

    scored.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return scored[0][0]


def row_is_numeric_only(r):
    vals = [str(v).strip() for v in r.tolist() if str(v).strip() not in ("", "nan", "NaN")]
    if not vals:
        return True
    return all(re.fullmatch(r"\d+(\.\d+)?", v) for v in vals)


def is_probably_event_col(series: pd.Series) -> bool:
    s = series.dropna().astype(str).str.strip().str.lower()
    if s.empty:
        return False
    allowed = {"yes", "no", "y", "n", "true", "false", "1", "0", "attended", "present", "absent", ""}
    frac = (s.isin(allowed)).mean()
    return frac >= 0.5


def safe_datetime_range_with_padding(dates, pad_days=2):
    """
    Ensures all points are visible on plotly date axes by adding padding on both ends.
    Handles edge cases where min==max.
    """
    dates = [d for d in dates if pd.notna(d)]
    if not dates:
        return None
    mn = min(dates)
    mx = max(dates)
    if mn == mx:
        mn = mn - pd.Timedelta(days=pad_days)
        mx = mx + pd.Timedelta(days=pad_days)
    else:
        mn = mn - pd.Timedelta(days=pad_days)
        mx = mx + pd.Timedelta(days=pad_days)
    return [mn, mx]


# =========================
# Sheet-aware loader (ROBUST)
# =========================
def load_sheet_structured(raw: pd.DataFrame):
    """
    Robust across your workbook (including PG - B3 & B4):
    - Header row = first row (top ~40) containing 'Student Name' or 'Student Names'
    - Date row   = the row ABOVE header with the MOST parseable dates (search up to 6 rows)
    - Event row  = date_row - 1 (event names)
    """
    header_row = None
    for i in range(min(40, len(raw))):
        row_text = " | ".join([clean_text(v).lower() for v in raw.iloc[i, :].tolist()])
        if "student name" in row_text or "student names" in row_text:
            header_row = i
            break

    if header_row is None:
        return None, None, "Could not find 'Student Name(s)' header row in top rows."

    candidate_rows = list(range(max(0, header_row - 6), header_row))
    best_date_row = None
    best_date_hits = -1

    for r in candidate_rows:
        cells = raw.iloc[r, :].tolist()
        hits = 0
        for v in cells:
            if pd.notna(parse_event_date(v)):
                hits += 1
        if hits > best_date_hits:
            best_date_hits = hits
            best_date_row = r

    if best_date_row is not None and best_date_hits >= 3:
        date_row = best_date_row
        event_row = date_row - 1 if date_row - 1 >= 0 else None
    else:
        date_row = header_row - 1 if header_row - 1 >= 0 else None
        event_row = header_row - 2 if header_row - 2 >= 0 else None

    header_cells = [clean_text(x) for x in raw.iloc[header_row, :].tolist()]
    event_cells = (
        [clean_text(x) for x in raw.iloc[event_row, :].tolist()]
        if event_row is not None
        else [""] * len(header_cells)
    )

    cols = []
    for j, h in enumerate(header_cells):
        if h:
            cols.append(h)
        elif j < len(event_cells) and event_cells[j]:
            cols.append(event_cells[j])
        else:
            cols.append(f"Unnamed_{j}")
    cols = make_unique(cols)

    df = raw.iloc[header_row + 1 :, :].copy()
    df.columns = cols
    df = df.reset_index(drop=True)
    df = df.dropna(how="all")

    event_dates = {}
    if date_row is not None:
        date_cells = raw.iloc[date_row, :].tolist()
        for j, col in enumerate(cols):
            if j < len(date_cells):
                dt = parse_event_date(date_cells[j])
                if pd.notna(dt):
                    event_dates[col] = dt

    meta = {
        "header_row": header_row,
        "event_row": event_row,
        "date_row": date_row,
        "event_dates": event_dates,
        "date_hits": best_date_hits if best_date_hits >= 0 else None,
    }
    return df, meta, None


@st.cache_data(show_spinner=False)
def get_sheet_names(file_bytes):
    xls = pd.ExcelFile(file_bytes)
    return xls.sheet_names


@st.cache_data(show_spinner=False)
def read_raw_sheet(file_bytes, sheet_name):
    return pd.read_excel(file_bytes, sheet_name=sheet_name, header=None).dropna(how="all")


# =========================
# App
# =========================
st.title("📊 Engagement Analytics Dashboard")

uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel File", type=["xlsx"])
if not uploaded_file:
    st.stop()

file_bytes = uploaded_file.getvalue()
all_sheets = get_sheet_names(file_bytes)

# ✅ Ignore first 2 sheets
sheets = all_sheets[2:] if len(all_sheets) > 2 else all_sheets
selected_sheet = st.sidebar.selectbox("Select Sheet (first 2 sheets ignored)", sheets)

raw = read_raw_sheet(file_bytes, selected_sheet)
df, meta, err = load_sheet_structured(raw)
if err:
    st.error(f"❌ {err}")
    st.stop()

# Keyword maps for metadata
KW = {
    "name_strict": ["student name", "student names", "full name", "learner name"],
    "name_fallback": ["name"],
    "email": ["email", "e mail", "e-mail"],
    "phone": ["phone", "mobile", "mobile no", "phone number"],
    "country": ["country"],
    "batch": ["batch"],
    "conversion": ["conversion status", "conversion"],
    "payment_date": ["payment date", "payment", "paid date", "date of payment"],
    "engagement_score": ["overall engagement score", "overall engagement", "engagement score"],
    "community_status": ["community status"],
    "date_of_exit": ["date of exit"],
}

# Detect metadata columns
name_col = best_matching_col(df, KW["name_strict"])
if not name_col:
    name_col = best_matching_col(
        df, KW["name_fallback"],
        hard_excludes=["batch", "program", "session", "event", "country", "status"]
    )

email_col = best_matching_col(df, KW["email"])
phone_col = best_matching_col(df, KW["phone"])
country_col = best_matching_col(df, KW["country"])
batch_col = best_matching_col(df, KW["batch"])
conversion_col = best_matching_col(df, KW["conversion"])
payment_col = best_matching_col(df, KW["payment_date"])
engagement_col = best_matching_col(df, KW["engagement_score"])
community_col = best_matching_col(df, KW["community_status"])
exit_col = best_matching_col(df, KW["date_of_exit"])

if not name_col:
    st.error("❌ Student Name column not detected after parsing.")
    st.stop()

# Safer summary-row dropping: only drop numeric-only rows when name is blank
name_series = df[name_col].astype(str).map(clean_text)
numeric_mask = df.apply(row_is_numeric_only, axis=1)
blank_name_mask = name_series.map(lambda x: x == "" or x.lower() == "nan")
df = df.loc[~(numeric_mask & blank_name_mask)].copy()

# Event columns = everything except metadata columns
metadata_cols = {
    c
    for c in [
        name_col, email_col, phone_col, country_col, batch_col,
        conversion_col, payment_col, engagement_col, community_col, exit_col
    ]
    if c
}
event_cols = [c for c in df.columns if c not in metadata_cols]

# Keep only columns that look like attendance
event_cols = [c for c in event_cols if is_probably_event_col(df[c])]

# Normalize event columns
for c in event_cols:
    df[c] = df[c].apply(normalize_binary)

# Participation count
df["participation_count"] = df[event_cols].sum(axis=1) if event_cols else 0

# Payment parse
if payment_col:
    df[payment_col] = df[payment_col].apply(parse_date_safe)

# Conversion parse
if not conversion_col:
    df["Conversion Status"] = ""
    conversion_col = "Conversion Status"
df[conversion_col] = df[conversion_col].astype(str).map(lambda x: clean_text(x).lower())

# Paid definition
def conv_category(r):
    if payment_col and pd.notna(r.get(payment_col, pd.NaT)):
        return "Paid / Admitted"
    v = str(r.get(conversion_col, "")).lower()
    if "admitted" in v or "paid" in v:
        return "Paid / Admitted"
    if "will" in v:
        return "Will Pay"
    return "Not Paid"

df["conversion_category"] = df.apply(conv_category, axis=1)

# Retention
event_dates = meta.get("event_dates", {}) or {}

def retained_flag(r):
    if not payment_col:
        return np.nan
    pay = r.get(payment_col, pd.NaT)
    if pd.isna(pay):
        return 0

    if not event_dates:
        return 1 if r.get("participation_count", 0) > 0 else 0

    pay_d = pay.normalize()
    for ev in event_cols:
        if r.get(ev, 0) == 1:
            dt = event_dates.get(ev, pd.NaT)
            if pd.notna(dt) and dt > pay_d:
                return 1
    return 0

df["retained"] = df.apply(retained_flag, axis=1)
retention_rate = float(df["retained"].mean() * 100) if payment_col else None

# Lead scoring
def lead_score(r):
    score = int(r.get("participation_count", 0)) * 10
    for ev in event_cols:
        if r.get(ev, 0) == 1:
            evl = ev.lower()
            if "hackathon" in evl:
                score += 20
            elif "ama" in evl:
                score += 15
            elif "masterclass" in evl:
                score += 15
    cat = r.get("conversion_category", "Not Paid")
    if cat == "Paid / Admitted":
        score += 30
    elif cat == "Will Pay":
        score += 15
    if payment_col and r.get("retained", 0) == 1:
        score += 10
    return score

df["lead_score"] = df.apply(lead_score, axis=1)

# =========================
# Sidebar filters
# =========================
st.sidebar.markdown("### Filters")

conv_filter = st.sidebar.multiselect(
    "Conversion category",
    ["Paid / Admitted", "Will Pay", "Not Paid"],
    default=["Paid / Admitted", "Will Pay", "Not Paid"],
)

min_part = st.sidebar.slider(
    "Minimum participation count",
    0,
    int(df["participation_count"].max() or 0),
    0
)

batch_filter = None
if batch_col:
    batches = sorted([b for b in df[batch_col].dropna().astype(str).map(clean_text).unique().tolist() if b])
    batch_filter = st.sidebar.multiselect("Batch", batches, default=batches)

country_filter = None
if country_col:
    countries = sorted([c for c in df[country_col].dropna().astype(str).map(clean_text).unique().tolist() if c])
    country_filter = st.sidebar.multiselect("Country", countries, default=countries)

search_text = st.sidebar.text_input("Search student (contains)", "")

fdf = df.copy()
fdf = fdf[fdf["conversion_category"].isin(conv_filter)]
fdf = fdf[fdf["participation_count"] >= min_part]
if batch_col and batch_filter is not None:
    fdf = fdf[fdf[batch_col].astype(str).map(clean_text).isin(set(batch_filter))]
if country_col and country_filter is not None:
    fdf = fdf[fdf[country_col].astype(str).map(clean_text).isin(set(country_filter))]
if search_text.strip():
    q = search_text.strip().lower()
    fdf = fdf[fdf[name_col].astype(str).str.lower().str.contains(q, na=False)]

# =========================
# Top metrics
# =========================
total_students = int(df[name_col].notna().sum())
active_students = int((df["participation_count"] > 0).sum())
paid_count = int((df["conversion_category"] == "Paid / Admitted").sum())
participants = int((df["participation_count"] > 0).sum())
conversion_rate = (paid_count / participants * 100) if participants else 0.0

f_total = int(fdf[name_col].notna().sum())
f_active = int((fdf["participation_count"] > 0).sum())
f_paid = int((fdf["conversion_category"] == "Paid / Admitted").sum())
f_participants = int((fdf["participation_count"] > 0).sum())
f_conv_rate = (f_paid / f_participants * 100) if f_participants else 0.0

st.caption(
    f"Parsed '{selected_sheet}' using: header_row={meta['header_row']}, "
    f"event_row={meta['event_row']}, date_row={meta['date_row']} | "
    f"Detected events: {len(event_cols)} | Rows: {len(df)}"
)

if payment_col and not event_dates:
    st.warning("Retention: Payment Date exists but event dates were not parsed → retention falls back to “any participation”.")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Students (All)", total_students, f"Filtered: {f_total}")
m2.metric("Active Students (All)", active_students, f"Filtered: {f_active}")
m3.metric("Paid / Admitted (All)", paid_count, f"Filtered: {f_paid}")
m4.metric("Conversion Rate (All)", f"{conversion_rate:.1f}%", f"Filtered: {f_conv_rate:.1f}%")
m5.metric("Retention Rate", f"{(retention_rate or 0):.1f}%" if payment_col else "N/A")

csv = fdf.to_csv(index=False).encode("utf-8")
st.download_button(
    "⬇️ Download filtered data (CSV)",
    data=csv,
    file_name=f"{selected_sheet}_filtered.csv",
    mime="text/csv",
)

st.divider()

# =========================
# 1️⃣ Top participating
# =========================
st.header("1️⃣ Top Participating Students (Filtered)")
st.dataframe(
    fdf.sort_values("participation_count", ascending=False)[
        [name_col, "participation_count", "conversion_category", "lead_score"]
    ].head(100),
    use_container_width=True,
    height=360,
)

# =========================
# 2️⃣ Payment & Conversion
# =========================
st.header("2️⃣ Payment & Conversion Analysis (Filtered)")

paid_df = fdf[fdf["conversion_category"] == "Paid / Admitted"].copy()
will_df = fdf[fdf["conversion_category"] == "Will Pay"].copy()
not_df = fdf[fdf["conversion_category"] == "Not Paid"].copy()

cols_paid = [name_col, conversion_col, "participation_count"]
if payment_col:
    cols_paid.insert(2, payment_col)

c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("✅ Paid / Admitted")
    st.dataframe(paid_df[cols_paid], use_container_width=True, height=280)
with c2:
    st.subheader("🟡 Will Pay")
    st.dataframe(will_df[[name_col, conversion_col, "participation_count"]], use_container_width=True, height=280)
with c3:
    st.subheader("🔴 Not Paid")
    st.dataframe(not_df[[name_col, conversion_col, "participation_count"]], use_container_width=True, height=280)

st.subheader("Conversion Status Values (Raw, Filtered)")
raw_conv = fdf[conversion_col].replace({"": np.nan, "nan": np.nan}).dropna()
raw_conv_counts = raw_conv.value_counts().reset_index()
raw_conv_counts.columns = ["Conversion Status", "Count"]
st.dataframe(raw_conv_counts, use_container_width=True, height=240)

# =========================
# 3️⃣ Retention
# =========================
st.header("3️⃣ Retention Analysis (Filtered)")
if payment_col:
    f_ret = float(fdf["retained"].mean() * 100) if len(fdf) else 0.0
    st.metric("Retention Rate (Filtered)", f"{f_ret:.2f}%")
    retained = fdf[fdf["retained"] == 1][[name_col, payment_col, "participation_count"]].copy()
    st.subheader("Retained Students (paid + attended after payment date)")
    st.dataframe(retained, use_container_width=True, height=280)
else:
    st.info("Retention analysis not available (no Payment Date column detected).")

st.divider()

# =========================
# 📈 Upgrades: Payment & Participation Insights
# =========================
st.header("📈 Payment & Participation Insights")

# A) Participation vs Lead Score (colored by conversion)
if len(fdf) > 0:
    st.subheader("A) Participation vs Lead Score (Filtered)")
    fig_sc = px.scatter(
        fdf,
        x="participation_count",
        y="lead_score",
        color="conversion_category",
        hover_data=[name_col] + ([payment_col] if payment_col else []),
        title="Lead Score vs Participation (color = conversion category)",
    )
    fig_sc.update_layout(height=420, margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(fig_sc, use_container_width=True)
else:
    st.info("No rows available in the filtered view for plotting.")

# B) Engagement around Payment Date (before/after), requires payment_col + event_dates
if payment_col and event_dates and event_cols and len(fdf) > 0:
    st.subheader("B) Engagement Before vs After Payment Date (Filtered)")

    rows = []
    for _, r in fdf.iterrows():
        pay = r.get(payment_col, pd.NaT)
        if pd.isna(pay):
            continue
        pay = pay.normalize()
        for ev in event_cols:
            ev_dt = event_dates.get(ev, pd.NaT)
            if pd.isna(ev_dt):
                continue
            rows.append(
                {
                    "Student": str(r.get(name_col, "")),
                    "Payment Date": pay,
                    "Event": ev,
                    "Event Date": ev_dt,
                    "Attended": int(r.get(ev, 0)),
                    "Days From Payment": int((ev_dt - pay).days),
                }
            )

    long_df = pd.DataFrame(rows)
    if long_df.empty:
        st.info("Not enough data to compute engagement around payment date for this sheet.")
    else:
        min_d, max_d = int(long_df["Days From Payment"].min()), int(long_df["Days From Payment"].max())
        left = max(-60, min_d)
        right = min(60, max_d)

        window = st.slider(
            "Window (days relative to payment date)",
            min_value=left,
            max_value=right,
            value=(-14, 30),
        )

        wdf = long_df[(long_df["Days From Payment"] >= window[0]) & (long_df["Days From Payment"] <= window[1])]

        agg = (
            wdf.groupby("Days From Payment", as_index=False)
            .agg(Attended=("Attended", "sum"), Events=("Attended", "count"))
        )
        agg["Attendance Rate"] = (agg["Attended"] / agg["Events"]).fillna(0.0)

        fig_pay = px.line(
            agg,
            x="Days From Payment",
            y="Attendance Rate",
            markers=True,
            hover_data=["Attended", "Events"],
            title="Attendance Rate vs Days From Payment Date",
        )
        fig_pay.add_vline(x=0, line_dash="dash")
        fig_pay.update_layout(height=420, margin=dict(l=10, r=10, t=60, b=10))
        st.plotly_chart(fig_pay, use_container_width=True)

        st.caption("Day 0 = payment date. Positive days = events after payment.")
else:
    st.info("Engagement around payment date requires both Payment Date and Event Dates for this sheet.")

# C) Quick action lists
if len(fdf) > 0:
    st.subheader("C) Quick Action Lists (Filtered)")
    colA, colB = st.columns(2)

    with colA:
        st.markdown("**High engagement but not paid** (best conversion targets)")
        targets = (
            fdf[(fdf["conversion_category"] != "Paid / Admitted") & (fdf["participation_count"] >= 3)]
            .sort_values(["participation_count", "lead_score"], ascending=False)
            [[name_col, "participation_count", "lead_score", "conversion_category"]]
            .head(15)
        )
        st.dataframe(targets, use_container_width=True, height=320)

    with colB:
        st.markdown("**Paid but low engagement** (retention risk)")
        risks = (
            fdf[(fdf["conversion_category"] == "Paid / Admitted") & (fdf["participation_count"] <= 1)]
            .sort_values(["participation_count", "lead_score"], ascending=True)
            [[name_col, "participation_count", "lead_score"]]
            .head(15)
        )
        st.dataframe(risks, use_container_width=True, height=320)

st.divider()

# =========================
# 4️⃣ No participation
# =========================
st.header("4️⃣ Students With NO Event Participation (Filtered)")
cols_no = [name_col, conversion_col]
if payment_col:
    cols_no.append(payment_col)
st.dataframe(fdf[fdf["participation_count"] == 0][cols_no], use_container_width=True, height=320)

# =========================
# 5️⃣ Paid low/no engagement
# =========================
st.header("5️⃣ Paid Students With Low / No Engagement (Filtered)")
low_paid = fdf[(fdf["conversion_category"] == "Paid / Admitted") & (fdf["participation_count"] <= 1)].copy()
if low_paid.empty:
    st.success("No paid students with 0–1 participation found.")
else:
    st.warning("⚠️ Paid students with low engagement (0–1 events):")
    cols_lp = [name_col, "participation_count"]
    if payment_col:
        cols_lp.insert(1, payment_col)
    st.dataframe(low_paid[cols_lp], use_container_width=True, height=320)

# =========================
# 6️⃣ Event-wise participation
# =========================
st.header("6️⃣ Event-wise Participation (Filtered)")

if not event_cols:
    st.info("No event columns detected after parsing.")
else:
    event_counts = fdf[event_cols].sum().sort_values(ascending=False)
    event_pct = (event_counts / max(len(fdf), 1) * 100).round(1)

    event_table = pd.DataFrame(
        {
            "Event": event_counts.index,
            "Participants": event_counts.values.astype(int),
            "Participation %": event_pct.values,
        }
    )
    st.dataframe(event_table, use_container_width=True, height=320)

    fig_bar = px.bar(event_table, x="Event", y="Participants", hover_data=["Participation %"])
    fig_bar.update_layout(xaxis_tickangle=-45, height=420, margin=dict(l=10, r=10, t=40, b=120))
    st.plotly_chart(fig_bar, use_container_width=True)

    # Slider safe even for small #events
    n_events = len(event_table)
    min_n = 1 if n_events < 5 else 5
    max_n = max(min(25, n_events), min_n)
    default_n = min(12, max_n)
    top_n = st.slider("Pie chart: number of top events", min_n, max_n, default_n)

    pie_df = event_table.head(top_n).copy()
    fig_pie = px.pie(pie_df, names="Event", values="Participants", hole=0.35)
    fig_pie.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)

# =========================
# 6b️⃣ Participation trend over time (if event dates exist)
# =========================
st.header("6b️⃣ Participation Trend Over Time")
if event_dates and event_cols:
    dated_events = [(ev, event_dates.get(ev, pd.NaT)) for ev in event_cols]
    dated_events = [(ev, dt) for ev, dt in dated_events if pd.notna(dt)]
    if dated_events:
        trend = [(dt, int(fdf[ev].sum())) for ev, dt in dated_events]
        trend_df = pd.DataFrame(trend, columns=["Event Date", "Participants"]).groupby("Event Date", as_index=False).sum()
        trend_df = trend_df.sort_values("Event Date")

        fig_tr = px.line(trend_df, x="Event Date", y="Participants", markers=True)
        # Force full range visible
        rng = safe_datetime_range_with_padding(trend_df["Event Date"].tolist(), pad_days=2)
        if rng:
            fig_tr.update_xaxes(range=rng)
        fig_tr.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig_tr, use_container_width=True)
    else:
        st.info("Event dates exist but none mapped to detected event columns.")
else:
    st.info("No event dates detected in this sheet.")

# =========================
# 7️⃣ Per-student timeline (better visibility + bold green payment marker)
# =========================
st.header("7️⃣ Per-Student Participation Timeline (Filtered)")

students = fdf[name_col].dropna().astype(str).unique().tolist()
if not students:
    st.info("No students detected in this filtered view.")
else:
    selected_student = st.selectbox("Select Student", students)
    row = fdf[fdf[name_col].astype(str) == str(selected_student)].iloc[0]

    timeline_events = event_cols[:]
    use_dates = bool(event_dates)

    if use_dates:
        timeline_events = sorted(
            timeline_events,
            key=lambda ev: (pd.isna(event_dates.get(ev, pd.NaT)), event_dates.get(ev, pd.NaT)),
        )

    x_vals, x_labels, attended = [], [], []
    event_dt_list = []
    for i, ev in enumerate(timeline_events, start=1):
        if use_dates and pd.notna(event_dates.get(ev, pd.NaT)):
            dt = event_dates[ev]
            x_vals.append(dt)
            event_dt_list.append(dt)
        else:
            x_vals.append(i)
        x_labels.append(ev)
        attended.append(int(row.get(ev, 0)))

    # Better visibility: split attended/missed markers so nothing "looks missing"
    attended_x = []
    attended_y = []
    missed_x = []
    missed_y = []

    for xv, a in zip(x_vals, attended):
        if a == 1:
            attended_x.append(xv)
            attended_y.append(1)
        else:
            missed_x.append(xv)
            missed_y.append(0)

    fig = go.Figure()

    # Draw a faint baseline to make reading easier
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=[0.5] * len(x_vals),
        mode="lines",
        name="",
        hoverinfo="skip",
        showlegend=False,
        line=dict(width=1, dash="dot"),
        opacity=0.25,
    ))

    # Attended markers (with connecting line through attended points only)
    fig.add_trace(go.Scatter(
        x=attended_x, y=attended_y,
        mode="lines+markers",
        name="Attended",
        connectgaps=False
    ))

    # Missed markers
    fig.add_trace(go.Scatter(
        x=missed_x, y=missed_y,
        mode="markers",
        name="Missed",
        marker=dict(symbol="x", size=10)
    ))

    # Payment marker: bold + green
    if payment_col and pd.notna(row.get(payment_col, pd.NaT)):
        pay_dt = row[payment_col]
        if use_dates:
            fig.add_trace(go.Scatter(
                x=[pay_dt], y=[1.18], mode="markers+text",
                text=["<b>✔ Payment</b>"],
                textposition="top center",
                name="Payment Date",
                marker=dict(symbol="star", size=16, color="green"),
                textfont=dict(size=14, color="green"),
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[len(timeline_events) + 1], y=[1.18], mode="markers+text",
                text=["<b>✔ Payment</b>"],
                textposition="top center",
                name="Payment Date",
                marker=dict(symbol="star", size=16, color="green"),
                textfont=dict(size=14, color="green"),
            ))

    fig.update_yaxes(range=[-0.2, 1.3], tickvals=[0, 1], title="Participation (1=Attended, 0=Missed)")
    fig.update_layout(
        height=560,
        margin=dict(l=10, r=10, t=60, b=90),
        title=f"Timeline — {selected_student}",
        xaxis_title="Event Date" if use_dates else "Event Sequence",
        showlegend=True
    )

    # ✅ Make sure start/end events never get clipped (padding on both ends)
    if use_dates and event_dt_list:
        rng = safe_datetime_range_with_padding(event_dt_list, pad_days=3)
        if rng:
            fig.update_xaxes(range=rng)

    if not use_dates:
        fig.update_xaxes(
            tickmode="array",
            tickvals=list(range(1, len(timeline_events) + 1)),
            ticktext=x_labels,
            tickangle=-45
        )

    st.plotly_chart(fig, use_container_width=True)

# =========================
# Lead leaderboard
# =========================
st.header("🏆 Lead Score Leaderboard (Filtered)")
st.dataframe(
    fdf.sort_values("lead_score", ascending=False)[
        [name_col, "lead_score", "participation_count", "conversion_category"]
    ].head(100),
    use_container_width=True,
    height=360,
)
