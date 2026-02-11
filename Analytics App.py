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
    # crash-proof for any weird cell values
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
      - '28-30.01.2026'
      - '28-01 to 30.01.2026'
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


def best_matching_col(df: pd.DataFrame, keywords):
    """
    If multiple columns match (e.g., duplicate 'Conversion Status'),
    pick the one with the most non-null values.
    """
    matches = []
    for c in df.columns:
        cl = clean_text(c).lower()
        if any(k in cl for k in keywords):
            matches.append(c)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    nn = [(c, df[c].notna().sum()) for c in matches]
    nn.sort(key=lambda x: x[1], reverse=True)
    return nn[0][0]


def drop_summary_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df.dropna(how="all")
    def row_is_numeric_only(r):
        vals = [str(v).strip() for v in r.tolist() if str(v).strip() not in ("", "nan", "NaN")]
        if not vals:
            return True
        return all(re.fullmatch(r"\d+(\.\d+)?", v) for v in vals)
    mask = df.apply(row_is_numeric_only, axis=1)
    return df.loc[~mask].copy()


# =========================
# Sheet-aware loader
# =========================
def load_sheet_structured(raw: pd.DataFrame):
    """
    Deterministic for YOUR workbook:
    - Header row = first row (top ~12) containing 'Student Name' or 'Student Names'
    - Date row   = header_row - 1
    - Event row  = header_row - 2
    """
    header_row = None
    for i in range(min(12, len(raw))):
        row_text = " | ".join([clean_text(v).lower() for v in raw.iloc[i, :].tolist()])
        if "student name" in row_text or "student names" in row_text:
            header_row = i
            break

    if header_row is None:
        return None, None, "Could not find 'Student Name(s)' header row in top 12 rows."

    date_row = header_row - 1 if header_row - 1 >= 0 else None
    event_row = header_row - 2 if header_row - 2 >= 0 else None

    header_cells = [clean_text(x) for x in raw.iloc[header_row, :].tolist()]
    event_cells = [clean_text(x) for x in raw.iloc[event_row, :].tolist()] if event_row is not None else [""] * len(header_cells)

    # Build columns:
    # - use header cell if present
    # - else use event name cell if present
    # - else fallback Unnamed_i
    cols = []
    for j, h in enumerate(header_cells):
        if h:
            cols.append(h)
        elif j < len(event_cells) and event_cells[j]:
            cols.append(event_cells[j])
        else:
            cols.append(f"Unnamed_{j}")
    cols = make_unique(cols)

    df = raw.iloc[header_row + 1:, :].copy()
    df.columns = cols
    df = df.reset_index(drop=True)
    df = drop_summary_rows(df)

    # Event-date mapping from date_row
    event_dates = {}
    if date_row is not None:
        date_cells = raw.iloc[date_row, :].tolist()
        for j, col in enumerate(cols):
            if j < len(date_cells):
                dt = parse_event_date(date_cells[j])
                if pd.notna(dt):
                    event_dates[col] = dt

    meta = {"header_row": header_row, "event_row": event_row, "date_row": date_row, "event_dates": event_dates}
    return df, meta, None


# =========================
# App
# =========================
st.title("📊 Engagement Analytics Dashboard")

uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel File", type=["xlsx"])
if not uploaded_file:
    st.stop()

xls = pd.ExcelFile(uploaded_file)
all_sheets = xls.sheet_names

# Ignore first sheet as requested
sheets = all_sheets[1:] if len(all_sheets) > 1 else all_sheets

selected_sheet = st.sidebar.selectbox("Select Sheet (first sheet ignored)", sheets)

raw = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=None).dropna(how="all")

df, meta, err = load_sheet_structured(raw)
if err:
    st.error(f"❌ {err}")
    st.stop()

# Keyword maps for metadata
KW = {
    "name": ["student name", "student names", "name", "full name"],
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

# Detect metadata columns (choose best if duplicates exist)
name_col = best_matching_col(df, KW["name"])
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
    st.error("❌ Student Name column not detected after parsing (unexpected).")
    st.stop()

# Event columns = everything except metadata columns
metadata_cols = {c for c in [name_col, email_col, phone_col, country_col, batch_col,
                             conversion_col, payment_col, engagement_col, community_col, exit_col] if c}
event_cols = [c for c in df.columns if c not in metadata_cols]

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

# Paid definition per your rule:
# Paid/Admitted if payment date exists OR conversion contains admitted/paid
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

# Retention: paid + attended an event whose date > payment date
event_dates = meta.get("event_dates", {}) or {}

def retained_flag(r):
    if not payment_col:
        return np.nan
    pay = r.get(payment_col, pd.NaT)
    if pd.isna(pay):
        return 0
    # If we have no event dates for this sheet, fallback to any participation
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

# Lead scoring (your notebook-style)
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
# Top metrics
# =========================
total_students = int(df[name_col].notna().sum())
active_students = int((df["participation_count"] > 0).sum())
paid_count = int((df["conversion_category"] == "Paid / Admitted").sum())
will_pay_count = int((df["conversion_category"] == "Will Pay").sum())
not_paid_count = int((df["conversion_category"] == "Not Paid").sum())
participants = int((df["participation_count"] > 0).sum())
conversion_rate = (paid_count / participants * 100) if participants else 0.0

st.caption(
    f"Parsed '{selected_sheet}' using: header_row={meta['header_row']}, event_row={meta['event_row']}, date_row={meta['date_row']} | "
    f"Detected events: {len(event_cols)}"
)

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Students", total_students)
m2.metric("Active Students", active_students)
m3.metric("Paid / Admitted", paid_count)
m4.metric("Conversion Rate", f"{conversion_rate:.1f}%")
m5.metric("Retention Rate", f"{(retention_rate or 0):.1f}%" if payment_col else "N/A")

st.divider()

# =========================
# 1️⃣ Top participating
# =========================
st.header("1️⃣ Top Participating Students")
st.dataframe(
    df.sort_values("participation_count", ascending=False)[
        [name_col, "participation_count", "conversion_category", "lead_score"]
    ].head(100),
    use_container_width=True,
    height=360
)

# =========================
# 2️⃣ Payment & Conversion
# =========================
st.header("2️⃣ Payment & Conversion Analysis")

paid_df = df[df["conversion_category"] == "Paid / Admitted"].copy()
will_df = df[df["conversion_category"] == "Will Pay"].copy()
not_df = df[df["conversion_category"] == "Not Paid"].copy()

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

st.subheader("Conversion Status Values (Raw)")
raw_conv = df[conversion_col].replace({"": np.nan, "nan": np.nan}).dropna()
raw_conv_counts = raw_conv.value_counts().reset_index()
raw_conv_counts.columns = ["Conversion Status", "Count"]
st.dataframe(raw_conv_counts, use_container_width=True, height=240)

# =========================
# 3️⃣ Retention
# =========================
st.header("3️⃣ Retention Analysis (PG sheets)")
if payment_col:
    st.metric("Overall Retention Rate", f"{(retention_rate or 0):.2f}%")
    retained = df[df["retained"] == 1][[name_col, payment_col, "participation_count"]].copy()
    st.subheader("Retained Students (paid + attended after payment date)")
    st.dataframe(retained, use_container_width=True, height=280)
else:
    st.info("Retention analysis not available for this sheet (no Payment Date column detected).")

# =========================
# 4️⃣ No participation
# =========================
st.header("4️⃣ Students With NO Event Participation")
cols_no = [name_col, conversion_col]
if payment_col:
    cols_no.append(payment_col)
st.dataframe(df[df["participation_count"] == 0][cols_no], use_container_width=True, height=320)

# =========================
# 5️⃣ Paid low/no engagement
# =========================
st.header("5️⃣ Paid Students With Low / No Engagement")
low_paid = df[(df["conversion_category"] == "Paid / Admitted") & (df["participation_count"] <= 1)].copy()
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
st.header("6️⃣ Event-wise Participation")

if not event_cols:
    st.info("No event columns detected after parsing.")
else:
    event_counts = df[event_cols].sum().sort_values(ascending=False)
    event_pct = (event_counts / max(len(df), 1) * 100).round(1)

    event_table = pd.DataFrame({
        "Event": event_counts.index,
        "Participants": event_counts.values.astype(int),
        "Participation %": event_pct.values
    })
    st.dataframe(event_table, use_container_width=True, height=320)

    fig_bar = px.bar(event_table, x="Event", y="Participants", hover_data=["Participation %"])
    fig_bar.update_layout(xaxis_tickangle=-45, height=420, margin=dict(l=10, r=10, t=40, b=120))
    st.plotly_chart(fig_bar, use_container_width=True)

    top_n = st.slider("Pie chart: number of top events", 5, min(25, len(event_table)), min(12, len(event_table)))
    pie_df = event_table.head(top_n).copy()
    fig_pie = px.pie(pie_df, names="Event", values="Participants", hole=0.35)
    fig_pie.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)

# =========================
# 7️⃣ Per-student timeline
# =========================
st.header("7️⃣ Per-Student Participation Timeline")

students = df[name_col].dropna().astype(str).unique().tolist()
if not students:
    st.info("No students detected in this sheet.")
else:
    selected_student = st.selectbox("Select Student", students)
    row = df[df[name_col].astype(str) == str(selected_student)].iloc[0]

    # Sort events by date if available, else keep order
    timeline_events = event_cols[:]
    if event_dates:
        timeline_events = sorted(timeline_events, key=lambda ev: (pd.isna(event_dates.get(ev, pd.NaT)), event_dates.get(ev, pd.NaT)))

    use_dates = bool(event_dates)
    x_vals, x_labels, attended = [], [], []
    for i, ev in enumerate(timeline_events, start=1):
        if use_dates and pd.notna(event_dates.get(ev, pd.NaT)):
            x_vals.append(event_dates[ev])
        else:
            x_vals.append(i)
        x_labels.append(ev)
        attended.append(int(row.get(ev, 0)))

    y_line = [1 if a == 1 else None for a in attended]  # breaks on misses
    y_miss = [0 if a == 0 else None for a in attended]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x_vals, y=y_line, mode="lines+markers", name="Attended", connectgaps=False))
    fig.add_trace(go.Scatter(x=x_vals, y=y_miss, mode="markers", name="Missed", marker=dict(symbol="x", size=9)))

    # Payment marker
    if payment_col and pd.notna(row.get(payment_col, pd.NaT)):
        pay_dt = row[payment_col]
        if use_dates:
            fig.add_trace(go.Scatter(
                x=[pay_dt], y=[1.15], mode="markers+text",
                text=["✔ Payment"], textposition="top center",
                name="Payment Date", marker=dict(symbol="star", size=14)
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[len(timeline_events) + 1], y=[1.15], mode="markers+text",
                text=["✔ Payment"], textposition="top center",
                name="Payment Date", marker=dict(symbol="star", size=14)
            ))

    fig.update_yaxes(range=[-0.2, 1.3], tickvals=[0, 1], title="Participation (1=Attended, 0=Missed)")
    fig.update_layout(
        height=520,
        margin=dict(l=10, r=10, t=50, b=80),
        title=f"Timeline — {selected_student}",
        xaxis_title="Event Date" if use_dates else "Event Sequence",
        showlegend=True
    )

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
st.header("🏆 Lead Score Leaderboard")
st.dataframe(
    df.sort_values("lead_score", ascending=False)[
        [name_col, "lead_score", "participation_count", "conversion_category"]
    ].head(100),
    use_container_width=True,
    height=360
)
