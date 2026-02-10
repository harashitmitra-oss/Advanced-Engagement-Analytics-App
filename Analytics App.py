import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import re

st.set_page_config(page_title="Engagement Analytics Dashboard", layout="wide")

# -------------------------------
# Utility Functions
# -------------------------------

def normalize_binary(x):
    if pd.isna(x):
        return 0
    x = str(x).strip().lower()
    if x in ["yes", "y", "true", "1", "attended", "present"]:
        return 1
    return 0

def find_header_row(df):
    for i in range(len(df)):
        row = df.iloc[i].astype(str).str.lower()
        if row.str.contains("student").any():
            return i
    return None

def find_event_row(df):
    # First row that contains multiple non-null and non-metadata values
    for i in range(len(df)):
        row = df.iloc[i]
        non_null = row.notna().sum()
        if non_null > 5:
            return i
    return None

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
        elif "community" in cl or "retention" in cl:
            meta["retention"] = col
        elif "overall engagement" in cl or "engagement score" in cl:
            meta["engagement_score"] = col
    return meta

def extract_events(event_row):
    events = []
    for val in event_row:
        if pd.isna(val):
            continue
        v = str(val).strip()
        if v == "" or re.search(r"(total|summary)", v.lower()):
            continue
        events.append(v)
    return events

def parse_date_safe(x):
    try:
        return pd.to_datetime(x)
    except:
        return pd.NaT

# -------------------------------
# Load File
# -------------------------------

uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel File", type=["xlsx"])

if not uploaded_file:
    st.warning("Please upload the Excel file to proceed.")
    st.stop()

xls = pd.ExcelFile(uploaded_file)
sheet_names = xls.sheet_names

st.sidebar.header("Sheet Selector")
selected_sheet = st.sidebar.selectbox("Select a sheet", sheet_names)

raw_df = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=None)

# -------------------------------
# Detect Rows
# -------------------------------

header_row = find_header_row(raw_df)
event_row = find_event_row(raw_df)

if header_row is None:
    st.error("Could not detect header row (Student Name).")
    st.stop()

if event_row is None:
    st.error("Could not detect event row.")
    st.stop()

# Build DataFrame
headers = raw_df.iloc[header_row].astype(str)
df = raw_df.iloc[header_row + 1:].copy()
df.columns = headers
df.reset_index(drop=True, inplace=True)

# Remove fully empty rows
df = df.dropna(how="all")

# Remove numeric-only rows (totals/summaries)
df = df[~df.apply(lambda r: r.astype(str).str.match(r"^\d+(\.\d+)?$").all(), axis=1)]

# -------------------------------
# Detect Metadata Columns
# -------------------------------

meta_cols = detect_metadata_columns(df.columns)

name_col = meta_cols.get("name")
conversion_col = meta_cols.get("conversion")
payment_col = meta_cols.get("payment_date")
retention_col = meta_cols.get("retention")
engagement_score_col = meta_cols.get("engagement_score")

if not name_col:
    st.error("Student Name column not detected.")
    st.stop()

# -------------------------------
# Detect Event Columns
# -------------------------------

event_row_values = raw_df.iloc[event_row]
event_names = extract_events(event_row_values)

event_columns = [col for col in df.columns if str(col) in event_names]

# Normalize event columns
for col in event_columns:
    df[col] = df[col].apply(normalize_binary)

# -------------------------------
# Conversion Status Processing
# -------------------------------

if conversion_col:
    df[conversion_col] = df[conversion_col].astype(str).str.lower().str.strip()
else:
    df["conversion_status_temp"] = "not paid"
    conversion_col = "conversion_status_temp"

def categorize_conversion(x):
    if "admitted" in x or "paid" in x:
        return "Paid / Admitted"
    elif "will" in x:
        return "Will Pay"
    else:
        return "Not Paid"

df["conversion_category"] = df[conversion_col].apply(categorize_conversion)

# -------------------------------
# Payment Date Processing
# -------------------------------

if payment_col:
    df[payment_col] = df[payment_col].apply(parse_date_safe)

# -------------------------------
# Participation Count
# -------------------------------

df["participation_count"] = df[event_columns].sum(axis=1)

# -------------------------------
# Retention Logic (PG Only)
# -------------------------------

if payment_col:
    df["retained"] = df.apply(
        lambda r: 1 if (pd.notna(r[payment_col]) and r["participation_count"] > 0) else 0,
        axis=1
    )
    retention_rate = df["retained"].mean() * 100
else:
    df["retained"] = np.nan
    retention_rate = None

# -------------------------------
# Lead Scoring
# -------------------------------

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

    if "retained" in row and row.get("retained") == 1:
        score += 10

    return score

df["lead_score"] = df.apply(calculate_lead_score, axis=1)

# -------------------------------
# Dashboard Layout
# -------------------------------

st.title("📊 Engagement Analytics Dashboard")

# -------------------------------
# Top Metrics
# -------------------------------

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

# -------------------------------
# 1️⃣ Top Participating Students
# -------------------------------

st.header("1️⃣ Top Participating Students")

top_participants = df.sort_values("participation_count", ascending=False)[
    [name_col, "participation_count", conversion_col, "lead_score"]
]

st.dataframe(top_participants.head(50), use_container_width=True)

# -------------------------------
# 2️⃣ Payment & Conversion Analysis
# -------------------------------

st.header("2️⃣ Payment & Conversion Analysis")

paid_df = df[df["conversion_category"] == "Paid / Admitted"]
will_pay_df = df[df["conversion_category"] == "Will Pay"]
not_paid_df = df[df["conversion_category"] == "Not Paid"]

st.subheader("✅ Paid / Admitted")
st.dataframe(paid_df[[name_col, conversion_col, payment_col]] if payment_col else paid_df[[name_col, conversion_col]])

st.subheader("🟡 Will Pay")
st.dataframe(will_pay_df[[name_col, conversion_col]])

st.subheader("🔴 Not Paid")
st.dataframe(not_paid_df[[name_col, conversion_col]])

# -------------------------------
# 3️⃣ Retention Analysis
# -------------------------------

st.header("3️⃣ Retention Analysis")

if payment_col:
    st.metric("Overall Retention Rate", f"{retention_rate:.2f}%")
    retained_students = df[df["retained"] == 1]
    st.subheader("Retained Students")
    st.dataframe(retained_students[[name_col, payment_col, "participation_count"]])
else:
    st.info("Retention analysis not available for this sheet (no Payment Date column).")

# -------------------------------
# 4️⃣ Students With NO Event Participation
# -------------------------------

st.header("4️⃣ Students With NO Event Participation")

no_participants = df[df["participation_count"] == 0]
cols_to_show = [name_col, conversion_col]
if payment_col:
    cols_to_show.append(payment_col)

st.dataframe(no_participants[cols_to_show], use_container_width=True)

# -------------------------------
# 5️⃣ Paid Students With Low / No Engagement
# -------------------------------

st.header("5️⃣ Paid Students With Low / No Engagement")

low_engaged_paid = df[
    (df["conversion_category"] == "Paid / Admitted") &
    (df["participation_count"] <= 1)
]

if not low_engaged_paid.empty:
    st.warning("These students have paid but show low or no engagement:")
    st.dataframe(low_engaged_paid[[name_col, "participation_count", payment_col]] if payment_col else low_engaged_paid[[name_col, "participation_count"]])
else:
    st.success("No low-engagement paid students found.")

# -------------------------------
# 6️⃣ Event-wise Participation
# -------------------------------

st.header("6️⃣ Event-wise Participation")

event_participation = df[event_columns].sum().sort_values(ascending=False)

fig1, ax1 = plt.subplots(figsize=(10, 5))
event_participation.plot(kind="bar", ax=ax1)
ax1.set_title("Event-wise Participation")
ax1.set_ylabel("Number of Students")
ax1.set_xlabel("Events")
plt.xticks(rotation=45, ha="right")
st.pyplot(fig1)

event_table = event_participation.reset_index()
event_table.columns = ["Event Name", "Participation Count"]
st.dataframe(event_table, use_container_width=True)

# -------------------------------
# 7️⃣ Per-Student Participation Timeline
# -------------------------------

st.header("7️⃣ Per-Student Participation Timeline")

student_name = st.selectbox("Select a student", df[name_col].dropna().unique())

student_row = df[df[name_col] == student_name].iloc[0]

# Build timeline
timeline_data = []

for col in event_columns:
    val = student_row[col]
    timeline_data.append({"event": col, "participated": val})

timeline_df = pd.DataFrame(timeline_data)
timeline_df["sequence"] = range(1, len(timeline_df) + 1)

fig2, ax2 = plt.subplots(figsize=(12, 5))

# Plot participation
participated_df = timeline_df[timeline_df["participated"] == 1]
ax2.plot(participated_df["sequence"], participated_df["participated"], marker="o", linestyle="-", label="Participated")

# Plot non-participation as gaps (no line)
non_participated_df = timeline_df[timeline_df["participated"] == 0]
ax2.scatter(non_participated_df["sequence"], non_participated_df["participated"], marker="x", color="gray", label="Missed")

# Payment marker
if payment_col and pd.notna(student_row[payment_col]):
    payment_seq = len(timeline_df) + 0.5
    ax2.scatter(payment_seq, 1, marker="*", s=200, color="green", label="Payment Date ✔")
    ax2.text(payment_seq, 1.05, "Payment", ha="center", color="green")

ax2.set_title(f"Participation Timeline: {student_name}")
ax2.set_xlabel("Event Sequence")
ax2.set_ylabel("Participation (1 = Attended, 0 = Not Attended)")
ax2.set_yticks([0, 1])
ax2.set_xticks(timeline_df["sequence"])
ax2.set_xticklabels(timeline_df["event"], rotation=45, ha="right")
ax2.legend()
st.pyplot(fig2)

# -------------------------------
# Lead Score Leaderboard
# -------------------------------

st.header("🏆 Lead Score Leaderboard")

leaderboard = df.sort_values("lead_score", ascending=False)[[name_col, "lead_score", conversion_col, "participation_count"]]
st.dataframe(leaderboard.head(50), use_container_width=True)
