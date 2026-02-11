import re
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Engagement Analytics Dashboard", layout="wide")

# ----------------------------
# CONFIG
# ----------------------------
IGNORE_FIRST_SHEET = True
DEFAULT_FILE_LABEL = "Master Engagement Tracker"

META_KEYWORDS = {
    "name": ["student name", "student names", "name", "full name"],
    "email": ["e-mail", "email", "e mail"],
    "phone": ["phone", "mobile", "mobile no", "mobile no.", "phone number"],
    "country": ["country"],
    "batch": ["batch"],
    "conversion": ["conversion status", "conversion"],
    "payment_date": ["payment date", "paid date", "date of payment"],
    "engagement_score": ["overall engagement score", "overall engagement", "engagement score"],
    "community_status": ["community status"],
    "date_of_exit": ["date of exit"],
}

# ----------------------------
# UTILITIES
# ----------------------------
def _clean_text(x) -> str:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return (
        str(x)
        .replace("\n", " ")
        .replace("\r", " ")
        .replace("\u00a0", " ")
        .strip()
    )

def _make_unique(cols):
    seen = {}
    out = []
    for c in cols:
        c = _clean_text(c)
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
    # must NEVER crash
    try:
        if x is None:
            return 0
        if isinstance(x, float) and np.isnan(x):
            return 0
        s = str(x).strip().lower()
        if s in {"yes", "y", "true", "1", "attended", "present"}:
            return 1
        return 0
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
    Returns a Timestamp or NaT.
    """
    try:
        ts = pd.to_datetime(val, errors="coerce")
        if pd.notna(ts):
            return ts.normalize()
    except Exception:
        pass

    s = _clean_text(val)
    if not s:
        return pd.NaT

    # find first date-ish chunk: dd[.-/]mm[.-/]yyyy OR dd.mm.yyyy hidden in range formats
    # examples:
    # 28-30.01.2026 -> take 28.01.2026
    # 28-01 to 30.01.2026 -> take 28.01.2026
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
    If multiple columns match (duplicate 'Conversion Status', etc.),
    pick the one with the most non-null values.
    """
    matches = []
    for c in df.columns:
        cl = _clean_text(c).lower()
        if any(k in cl for k in keywords):
            matches.append(c)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # choose by non-null count
    nn = [(c, df[c].notna().sum()) for c in matches]
    nn.sort(key=lambda x: x[1], reverse=True)
    return nn[0][0]

def drop_summary_rows(df: pd.DataFrame) -> pd.DataFrame:
    # remove fully empty rows
    df = df.dropna(how="all")
    # remove numeric-only rows / totals
    def _row_is_numeric_only(r):
        vals = [str(v).strip() for v in r.tolist() if str(v).strip() != "" and str(v).lower() != "nan"]
        if not vals:
            return True
        return all(re.fullmatch(r"\d+(\.\d+)?", v) for v in vals)
    mask = df.apply(_row_is_numeric_only, axis=1)
    return df.loc[~mask].copy()

def detect_header_row(raw: pd.DataFrame, max_scan=12):
    """
    Pick the row (within top max_scan) that looks most like a metadata header:
    has Name/Email/Phone/Country/Batch/Conversion/Payment keywords.
    """
    best_i, best_score = None, -1
    for i in range(min(max_scan, len(raw))):
        row = raw.iloc[i, :].tolist()
        texts = [_clean_text(x).lower() for x in row]
        score = 0
        for t in texts:
            if "student" in t and "name" in t:
                score += 3
            if re.search(r"\bname\b", t):
                score += 2
            if "email" in t or "e-mail" in t or "e mail" in t:
                score += 2
            if "phone" in t or "mobile" in t:
                score += 2
            if "conversion" in t:
                score += 2
            if "payment" in t and "date" in t:
                score += 2
            if "country" in t:
                score += 1
            if "batch" in t:
                score += 1
        if score > best_score:
            best_score = score
            best_i = i
    return best_i if best_score >= 3 else None

def detect_event_row(raw: pd.DataFrame, header_row: int):
    """
    For your workbook, event names live ABOVE header row.
    We choose the row above header_row that has the most non-empty cells,
    and is NOT itself a metadata header.
    """
    if header_row is None or header_row == 0:
        return None
    candidates = list(range(max(0, header_row - 4), header_row))
    best_i, best_non_empty = None, -1
    for i in candidates:
        row = raw.iloc[i, :].tolist()
        texts = [_clean_text(x) for x in row]
        non_empty = sum(1 for t in texts if t != "")
        # skip if it looks like a header row
        low = " ".join([t.lower() for t in texts])
        if "student" in low and "name" in low:
            continue
        if non_empty > best_non_empty:
            best_non_empty = non_empty
            best_i = i
    return best_i

def detect_date_row(raw: pd.DataFrame, header_row: int, event_row: int):
    """
    Usually date row is directly below event_row.
    We'll take event_row+1 if it's above header_row.
    """
    if event_row is None:
        return None
    dr = event_row + 1
    if dr < header_row:
        return dr
    return None

def build_dataframe_for_sheet(raw: pd.DataFrame):
    header_row = detect_header_row(raw)
    if header_row is None:
        return None, "Could not detect header row."

    event_row = detect_event_row(raw, header_row)
    date_row = detect_date_row(raw, header_row, event_row)

    header_cells = raw.iloc[header_row, :].tolist()
    header_cells = [_clean_text(x) for x in header_cells]

    event_cells = raw.iloc[event_row, :].tolist() if event_row is not None else ["" for _ in header_cells]
    event_cells = [_clean_text(x) for x in event_cells]

    # Build final column names:
    # - use header cell if present
    # - else use event name cell if present
    # - else fallback Unnamed_{i}
    cols = []
    for i, h in enumerate(header_cells):
        if h != "" and h.lower() != "nan":
            cols.append(h)
        elif i < len(event_cells) and event_cells[i] != "":
            cols.append(event_cells[i])
        else:
            cols.append(f"Unnamed_{i}")
    cols = _make_unique(cols)

    df = raw.iloc[header_row + 1:, :].copy()
    df.columns = cols
    df = df.reset_index(drop=True)
    df = drop_summary_rows(df)

    # event date mapping (optional)
    event_dates = {}
    if date_row is not None:
        date_cells = raw.iloc[date_row, :].tolist()
        for i, col in enumerate(cols):
            if i < len(date_cells):
                dt = parse_event_date(date_cells[i])
                if pd.notna(dt):
                    event_dates[col] = dt

    return (df, {"header_row": header_row, "event_row": event_row, "date_row": date_row, "event_dates": event_dates}), None

# ----------------------------
# APP
# ----------------------------
st.title("📊 Engagement Analytics Dashboard")

uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel File", type=["xlsx"], accept_multiple_files=False)
if not uploaded_file:
    st.info("Upload the Excel file to begin.")
    st.stop()

xls = pd.ExcelFile(uploaded_file)
all_sheets = xls.sheet_names
sheets = all_sheets[1:] if (IGNORE_FIRST_SHEET and len(all_sheets) > 1) else all_sheets

st.sidebar.header("Sheet Selector")
selected_sheet = st.sidebar.selectbox("Select a sheet", sheets)

raw = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=None).dropna(how="all")

df_pack, err = None, None
df, meta, err = (None, None, None)
built = build_dataframe_for_sheet(raw)
if built[0] is None:
    st.error(f"❌ {built[1]}")
    st.stop()
df, meta, _ = built

# Detect metadata columns (best-of matches)
name_col = best_matching_col(df, META_KEYWORDS["name"])
email_col = best_matching_col(df, META_KEYWORDS["email"])
phone_col = best_matching_col(df, META_KEYWORDS["phone"])
country_col = best_matching_col(df, META_KEYWORDS["country"])
batch_col = best_matching_col(df, META_KEYWORDS["batch"])
conversion_col = best_matching_col(df, META_KEYWORDS["conversion"])
payment_col = best_matching_col(df, META_KEYWORDS["payment_date"])
engagement_score_col = best_matching_col(df, META_KEYWORDS["engagement_score"])
community_col = best_matching_col(df, META_KEYWORDS["community_status"])
exit_col = best_matching_col(df, META_KEYWORDS["date_of_exit"])

if not name_col:
    st.error("❌ Student Name column not detected in this sheet after parsing.")
    st.stop()

# Event columns are those NOT in metadata columns
metadata_cols = {c for c in [name_col, email_col, phone_col, country_col, batch_col, conversion_col,
                            payment_col, engagement_score_col, community_col, exit_col] if c}

event_cols = [c for c in df.columns if c not in metadata_cols]

# Clean/normalize event cols
for c in event_cols:
    df[c] = df[c].apply(normalize_binary)

# Participation
df["participation_count"] = df[event_cols].sum(axis=1) if event_cols else 0

# Payment date parse
if payment_col:
    df[payment_col] = df[payment_col].apply(parse_date_safe)

# Conversion: choose categories; your rule:
# Paid/Admitted if payment date present OR conversion contains admitted
if not conversion_col:
    df["Conversion Status"] = ""
    conversion_col = "Conversion Status"
df[conversion_col] = df[conversion_col].astype(str).map(lambda x: _clean_text(x).lower())

def conversion_category_row(r):
    if payment_col and pd.notna(r.get(payment_col, pd.NaT)):
        return "Paid / Admitted"
    v = str(r.get(conversion_col, "")).lower()
    if "admitted" in v or "paid" in v:
        return "Paid / Admitted"
    if "will" in v:
        return "Will Pay"
    return "Not Paid"

df["conversion_category"] = df.apply(conversion_category_row, axis=1)

# Retention: paid + participated in events AFTER payment date (using event_dates mapping)
event_dates = meta.get("event_dates", {}) if meta else {}
def retention_flag(r):
    if not payment_col:
        return np.nan
    pay = r.get(payment_col, pd.NaT)
    if pd.isna(pay):
        return 0
    # if we don't have event dates parsed, fallback to any participation
    if not event_dates:
        return 1 if r["participation_count"] > 0 else 0
    for ev in event_cols:
        if r.get(ev, 0) == 1:
            dt = event_dates.get(ev, pd.NaT)
            if pd.notna(dt) and dt > pay.normalize():
                return 1
    return 0

df["retained"] = df.apply(retention_flag, axis=1)
retention_rate = float(df["retained"].mean() * 100) if payment_col else None

# Lead score (from your notebook logic)
def lead_score(r):
    score = int(r["participation_count"]) * 10
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

# ----------------------------
# TOP METRICS
# ----------------------------
total_students = int(df[name_col].notna().sum())
active_students = int((df["participation_count"] > 0).sum())
paid_count = int((df["conversion_category"] == "Paid / Admitted").sum())
will_pay_count = int((df["conversion_category"] == "Will Pay").sum())
not_paid_count = int((df["conversion_category"] == "Not Paid").sum())
participants = int((df["participation_count"] > 0).sum())
conversion_rate = (paid_count / participants * 100) if participants else 0.0

st.caption(f"Parsed rows using: header_row={meta['header_row']}, event_row={meta['event_row']}, date_row={meta['date_row']}")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Students", total_students)
m2.metric("Active Students", active_students)
m3.metric("Paid / Admitted", paid_count)
m4.metric("Conversion Rate", f"{conversion_rate:.1f}%")
if payment_col:
    m5.metric("Retention Rate", f"{(retention_rate or 0):.1f}%")
else:
    m5.metric("Retention Rate", "N/A")

st.divider()

# ----------------------------
# 1️⃣ TOP PARTICIPATING STUDENTS
# ----------------------------
st.header("1️⃣ Top Participating Students")
top_cols = [name_col, "participation_count", "conversion_category", "lead_score"]
st.dataframe(
    df.sort_values("participation_count", ascending=False)[top_cols].head(100),
    use_container_width=True,
    height=360
)

# ----------------------------
# 2️⃣ PAYMENT & CONVERSION ANALYSIS
# ----------------------------
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

st.subheader("Conversion Status Categories (Raw)")
raw_conv_counts = df[conversion_col].replace({"": np.nan}).dropna().value_counts().reset_index()
raw_conv_counts.columns = ["Conversion Status Value", "Count"]
st.dataframe(raw_conv_counts, use_container_width=True, height=240)

# ----------------------------
# 3️⃣ RETENTION ANALYSIS (PG only)
# ----------------------------
st.header("3️⃣ Retention Analysis")
if payment_col:
    st.metric("Overall Retention Rate", f"{(retention_rate or 0):.2f}%")
    retained = df[df["retained"] == 1][[name_col, payment_col, "participation_count"]].copy()
    st.subheader("Retained Students (paid + attended after payment)")
    st.dataframe(retained, use_container_width=True, height=280)
else:
    st.info("Retention analysis not available for this sheet (no Payment Date column detected).")

# ----------------------------
# 4️⃣ STUDENTS WITH NO EVENT PARTICIPATION
# ----------------------------
st.header("4️⃣ Students With NO Event Participation")
no_part = df[df["participation_count"] == 0].copy()
cols_no = [name_col, conversion_col]
if payment_col:
    cols_no.append(payment_col)
st.dataframe(no_part[cols_no], use_container_width=True, height=320)

# ----------------------------
# 5️⃣ PAID STUDENTS WITH LOW / NO ENGAGEMENT
# ----------------------------
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

# ----------------------------
# 6️⃣ EVENT-WISE PARTICIPATION
# ----------------------------
st.header("6️⃣ Event-wise Participation")

if event_cols:
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

    # Pie of top N to avoid unreadable pies
    top_n = st.slider("Pie chart: number of top events", 5, min(25, len(event_table)), min(12, len(event_table)))
    pie_df = event_table.head(top_n).copy()
    fig_pie = px.pie(pie_df, names="Event", values="Participants", hole=0.35)
    fig_pie.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig_pie, use_container_width=True)
else:
    st.info("No event columns detected after parsing.")

# ----------------------------
# 7️⃣ PER-STUDENT PARTICIPATION TIMELINE
# ----------------------------
st.header("7️⃣ Per-Student Participation Timeline")

student_list = df[name_col].dropna().astype(str).unique().tolist()
if student_list:
    selected_student = st.selectbox("Select Student", student_list)
    row = df[df[name_col].astype(str) == str(selected_student)].iloc[0]

    # Build timeline ordering:
    # If we have event dates, sort by date; otherwise keep column order
    events_for_timeline = event_cols.copy()
    if event_dates:
        dated = [(ev, event_dates.get(ev, pd.NaT)) for ev in events_for_timeline]
        dated.sort(key=lambda x: (pd.isna(x[1]), x[1]))  # NaT at end
        events_for_timeline = [x[0] for x in dated]

    # X axis:
    # use dates if available; otherwise sequence index
    use_dates = bool(event_dates)
    x_vals = []
    x_labels = []
    for i, ev in enumerate(events_for_timeline, start=1):
        if use_dates and pd.notna(event_dates.get(ev, pd.NaT)):
            x_vals.append(event_dates[ev])
        else:
            x_vals.append(i)
        x_labels.append(ev)

    attended = [int(row.get(ev, 0)) for ev in events_for_timeline]

    # line breaks for missed: y_line has None where missed to break the line
    y_line = [1 if a == 1 else None for a in attended]
    y_missed = [0 if a == 0 else None for a in attended]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=x_vals, y=y_line, mode="lines+markers",
        name="Attended", connectgaps=False
    ))

    fig.add_trace(go.Scatter(
        x=x_vals, y=y_missed, mode="markers",
        name="Missed", marker=dict(symbol="x", size=9)
    ))

    # Payment marker
    if payment_col and pd.notna(row.get(payment_col, pd.NaT)):
        pay_dt = row[payment_col]
        # place at date or after sequence
        if use_dates:
            fig.add_trace(go.Scatter(
                x=[pay_dt], y=[1.15], mode="markers+text",
                text=["✔ Payment"], textposition="top center",
                name="Payment Date", marker=dict(symbol="star", size=14)
            ))
        else:
            fig.add_trace(go.Scatter(
                x=[len(events_for_timeline) + 1], y=[1.15], mode="markers+text",
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
            tickvals=list(range(1, len(events_for_timeline) + 1)),
            ticktext=x_labels,
            tickangle=-45
        )

    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No students detected in this sheet.")

# ----------------------------
# LEAD SCORE LEADERBOARD
# ----------------------------
st.header("🏆 Lead Score Leaderboard")
st.dataframe(
    df.sort_values("lead_score", ascending=False)[[name_col, "lead_score", "participation_count", "conversion_category"]].head(100),
    use_container_width=True,
    height=360
)
