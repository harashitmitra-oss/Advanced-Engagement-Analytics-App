import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="Engagement Analytics Dashboard", layout="wide")

# ============================
# CONFIGURATION PER SHEET TYPE
# ============================

SHEET_CONFIG = {
    "PG Engagement Tracker B2": {"event_row": 0, "header_row": 2, "data_row": 3},
    "PG Engagement Tracker B3": {"event_row": 1, "header_row": 3, "data_row": 4},
}

# Default fallback for UG sheets
DEFAULT_CONFIG = {"event_row": None, "header_row": 0, "data_row": 1}

# ============================
# HELPER FUNCTIONS
# ============================

def normalize_binary(x):
    if pd.isna(x):
        return 0
    x = str(x).strip().lower()
    return 1 if x in ["yes", "y", "true", "1", "attended", "present"] else 0

def parse_date_safe(x):
    try:
        return pd.to_datetime(x)
    except:
        return pd.NaT

def categorize_conversion(row, conversion_col, payment_col):
    payment_date = row.get(payment_col, pd.NaT) if payment_col else pd.NaT
    conversion_val = str(row.get(conversion_col, "")).lower().strip() if conversion_col else ""

    if pd.notna(payment_date):
        return "Paid / Admitted"
    if "admitted" in conversion_val or "paid" in conversion_val:
        return "Paid / Admitted"
    elif "will" in conversion_val:
        return "Will Pay"
    else:
        return "Not Paid"

def make_unique(columns):
    seen = {}
    new_cols = []
    for col in columns:
        if col not in seen:
            seen[col] = 0
            new_cols.append(col)
        else:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
    return new_cols

# ============================
# LOAD FILE
# ============================

uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel File", type=["xlsx"])
if not uploaded_file:
    st.stop()

xls = pd.ExcelFile(uploaded_file)
sheet_names = xls.sheet_names

st.sidebar.header("Sheet Selector")
selected_sheet = st.sidebar.selectbox("Select a sheet", sheet_names)

raw = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=None)

# ============================
# APPLY SHEET CONFIG
# ============================

config = SHEET_CONFIG.get(selected_sheet, DEFAULT_CONFIG)
event_row = config["event_row"]
header_row = config["header_row"]
data_row = config["data_row"]

# ============================
# BUILD DATAFRAME
# ============================

if event_row is not None:
    event_headers = raw.iloc[event_row, :].astype(str)
else:
    event_headers = []

main_headers = raw.iloc[header_row, :].astype(str)
columns = main_headers.tolist()

df = raw.iloc[data_row:].copy()
df.columns = columns
df.columns = make_unique(df.columns)
df = df.dropna(how="all")

# ============================
# CLEAN COLUMN NAMES
# ============================

df.columns = (
    df.columns.astype(str)
    .str.replace("\n", " ", regex=True)
    .str.replace("\r", " ", regex=True)
    .str.replace("\u00a0", " ", regex=True)
    .str.strip()
)

# ============================
# DETECT METADATA COLUMNS
# ============================

def detect_metadata_columns(columns):
    meta = {}
    for col in columns:
        cl = col.lower()
        if "name" in cl:
            meta["name"] = col
        elif "email" in cl:
            meta["email"] = col
        elif "country" in cl:
            meta["country"] = col
        elif "batch" in cl:
            meta["batch"] = col
        elif "conversion" in cl:
            meta["conversion"] = col
        elif "payment" in cl and "date" in cl:
            meta["payment_date"] = col
        elif "overall engagement" in cl or "engagement score" in cl:
            meta["engagement_score"] = col
    return meta

meta_cols = detect_metadata_columns(df.columns)

name_col = meta_cols.get("name")
conversion_col = meta_cols.get("conversion")
payment_col = meta_cols.get("payment_date")
engagement_score_col = meta_cols.get("engagement_score")

if not name_col:
    st.error("❌ Student Name column not detected.")
    st.stop()

# ============================
# DETECT EVENT COLUMNS (EXPLICIT LOGIC)
# ============================

metadata_cols = set(meta_cols.values())
event_columns = [col for col in df.columns if col not in metadata_cols]

if not event_columns:
    st.error("❌ No event columns detected. Please verify sheet format.")
    st.stop()

# Normalize event columns
for col in event_columns:
    df[col] = df[col].apply(normalize_binary)

# ============================
# PAYMENT DATE PROCESSING
# ============================

if payment_col:
    df[payment_col] = df[payment_col].apply(parse_date_safe)

# ============================
# CONVERSION STATUS PROCESSING
# ============================

if not conversion_col:
    df["Conversion Status"] = ""
    conversion_col = "Conversion Status"

df["conversion_category"] = df.apply(
    lambda r: categorize_conversion(r, conversion_col, payment_col),
    axis=1
)

# ============================
# PARTICIPATION COUNT
# ============================

df["participation_count"] = df[event_columns].sum(axis=1)

# ============================
# RETENTION LOGIC (PG ONLY)
# ============================

if payment_col:
    df["retained"] = df.apply(
        lambda r: 1 if (pd.notna(r[payment_col]) and r["participation_count"] > 0) else 0,
        axis=1
    )
    retention_rate = df["retained"].mean() * 100
else:
    df["retained"] = np.nan
    retention_rate = None

# ============================
# LEAD SCORING
# ============================

def calculate_lead_score(row):
    score = row["participation_count"] * 10

    for col in event_columns:
        col_l = col.lower()
        if row[col] == 1:
            if "hackathon" in col_l:
                score += 20
            elif "ama" in col_l:
                score += 15
            elif "masterclass" in col_l:
                score += 15

    if row["conversion_category"] == "Paid / Admitted":
        score += 30
    elif row["conversion_category"] == "Will Pay":
        score += 15

    if payment_col and row.get("retained") == 1:
        score += 10

    return score

df["lead_score"] = df.apply(calculate_lead_score, axis=1)

# ============================
# DASHBOARD
# ============================

st.title("📊 Engagement Analytics Dashboard")

# ============================
# TOP METRICS
# ============================

paid_count = (df["conversion_category"] == "Paid / Admitted").sum()
will_pay_count = (df["conversion_category"] == "Will Pay").sum()
not_paid_count = (df["conversion_category"] == "Not Paid").sum()
participants = (df["participation_count"] > 0).sum()
conversion_rate = (paid_count / participants * 100) if participants > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Paid / Admitted", paid_count)
col2.metric("Will Pay", will_pay_count)
col3.metric("Not Paid", not_paid_count)
col4.metric("Conversion Rate", f"{conversion_rate:.2f}%")

# ============================
# 1️⃣ Top Participating Students
# ============================

st.header("1️⃣ Top Participating Students")
top_participants = df.sort_values("participation_count", ascending=False)[
    [name_col, "participation_count", conversion_col, "lead_score"]
]
st.dataframe(top_participants.head(50), use_container_width=True)

# ============================
# 2️⃣ Payment & Conversion Analysis
# ============================

st.header("2️⃣ Payment & Conversion Analysis")

paid_df = df[df["conversion_category"] == "Paid / Admitted"]
will_pay_df = df[df["conversion_category"] == "Will Pay"]
not_paid_df = df[df["conversion_category"] == "Not Paid"]

st.subheader("✅ Paid / Admitted")
cols_paid = [name_col, conversion_col]
if payment_col:
    cols_paid.append(payment_col)
st.dataframe(paid_df[cols_paid], use_container_width=True)

st.subheader("🟡 Will Pay")
st.dataframe(will_pay_df[[name_col, conversion_col]], use_container_width=True)

st.subheader("🔴 Not Paid")
st.dataframe(not_paid_df[[name_col, conversion_col]], use_container_width=True)

# ============================
# 3️⃣ Retention Analysis
# ============================

st.header("3️⃣ Retention Analysis")

if payment_col:
    st.metric("Overall Retention Rate", f"{retention_rate:.2f}%")
    retained_students = df[df["retained"] == 1]
    st.subheader("Retained Students")
    st.dataframe(retained_students[[name_col, payment_col, "participation_count"]], use_container_width=True)
else:
    st.info("Retention analysis not available for this sheet (no Payment Date column).")

# ============================
# 4️⃣ Students With NO Event Participation
# ============================

st.header("4️⃣ Students With NO Event Participation")
no_participants = df[df["participation_count"] == 0]
cols_to_show = [name_col, conversion_col]
if payment_col:
    cols_to_show.append(payment_col)
st.dataframe(no_participants[cols_to_show], use_container_width=True)

# ============================
# 5️⃣ Paid Students With Low / No Engagement
# ============================

st.header("5️⃣ Paid Students With Low / No Engagement")
low_engaged_paid = df[
    (df["conversion_category"] == "Paid / Admitted") &
    (df["participation_count"] <= 1)
]

if not low_engaged_paid.empty:
    st.warning("These students have paid but show low or no engagement:")
    cols_low = [name_col, "participation_count"]
    if payment_col:
        cols_low.append(payment_col)
    st.dataframe(low_engaged_paid[cols_low], use_container_width=True)
else:
    st.success("No low-engagement paid students found.")

# ============================
# 6️⃣ Event-wise Participation (Counts + Percent + Pie)
# ============================

st.header("6️⃣ Event-wise Participation")

event_participation = df[event_columns].sum().sort_values(ascending=False)
total_students = len(df)
event_percentages = (event_participation / total_students * 100).round(2)

event_table = pd.DataFrame({
    "Event Name": event_participation.index,
    "Participation Count": event_participation.values,
    "Participation %": event_percentages.values
})
st.dataframe(event_table, use_container_width=True)

# Bar Chart
fig1, ax1 = plt.subplots(figsize=(10, 5))
event_participation.plot(kind="bar", ax=ax1)
ax1.set_title("Event-wise Participation Count")
ax1.set_ylabel("Number of Students")
ax1.set_xlabel("Events")
plt.xticks(rotation=45, ha="right")
st.pyplot(fig1)

# Pie Chart
fig_pie, ax_pie = plt.subplots(figsize=(7, 7))
ax_pie.pie(event_participation, labels=event_participation.index, autopct="%1.1f%%", startangle=140)
ax_pie.set_title("Event Participation Distribution")
st.pyplot(fig_pie)

# ============================
# 7️⃣ Per-Student Participation Timeline (with Payment Marker)
# ============================

st.header("7️⃣ Per-Student Participation Timeline")

student_name = st.selectbox("Select a student", df[name_col].dropna().unique())
student_row = df[df[name_col] == student_name].iloc[0]

timeline_data = []
for i, col in enumerate(event_columns, start=1):
    timeline_data.append({"sequence": i, "event": col, "participated": student_row[col]})

timeline_df = pd.DataFrame(timeline_data)

fig2, ax2 = plt.subplots(figsize=(12, 5))
participated_df = timeline_df[timeline_df["participated"] == 1]
ax2.plot(participated_df["sequence"], participated_df["participated"], marker="o", linestyle="-", label="Participated")

non_participated_df = timeline_df[timeline_df["participated"] == 0]
ax2.scatter(non_participated_df["sequence"], non_participated_df["participated"], marker="x", label="Missed")

if payment_col and pd.notna(student_row[payment_col]):
    payment_seq = len(timeline_df) + 0.5
    ax2.scatter(payment_seq, 1, marker="*", s=200, label="Payment Date ✔")
    ax2.text(payment_seq, 1.05, "Payment", ha="center")

ax2.set_title(f"Participation Timeline: {student_name}")
ax2.set_xlabel("Event Sequence")
ax2.set_ylabel("Participation (1 = Attended, 0 = Not Attended)")
ax2.set_yticks([0, 1])
ax2.set_xticks(timeline_df["sequence"])
ax2.set_xticklabels(timeline_df["event"], rotation=45, ha="right")
ax2.legend()
st.pyplot(fig2)

# ============================
# 8️⃣ Lead Score Leaderboard
# ============================

st.header("🏆 Lead Score Leaderboard")
leaderboard = df.sort_values("lead_score", ascending=False)[
    [name_col, "lead_score", conversion_col, "participation_count"]
]
st.dataframe(leaderboard.head(50), use_container_width=True)

# ============================
# 9️⃣ Conversion Status Breakdown
# ============================

st.header("9️⃣ Conversion Status Category Breakdown")
conversion_summary = df["conversion_category"].value_counts().reset_index()
conversion_summary.columns = ["Category", "Count"]
st.dataframe(conversion_summary, use_container_width=True)

fig_conv, ax_conv = plt.subplots(figsize=(6, 6))
ax_conv.pie(conversion_summary["Count"], labels=conversion_summary["Category"], autopct="%1.1f%%", startangle=140)
ax_conv.set_title("Conversion Status Distribution")
st.pyplot(fig_conv)
