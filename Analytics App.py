# engagement_dashboard.py
# Fully robust, multi-sheet Engagement Analytics Dashboard (UG & PG compatible)
# Based on user's working notebook logic + production-grade error handling

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from collections import Counter

st.set_page_config(page_title="Engagement Analytics Dashboard", layout="wide")

# -----------------------------
# Utility Functions
# -----------------------------

def normalize_binary(val):
    try:
        if pd.isna(val):
            return 0
        val = str(val).strip().lower()
        if val in ["yes", "y", "true", "1", "attended", "present", "done", "completed"]:
            return 1
        elif val in ["no", "n", "false", "0", "", "nan", "none"]:
            return 0
        else:
            return 0
    except:
        return 0


def make_unique(columns):
    counts = Counter()
    new_cols = []
    for col in columns:
        col = str(col).strip()
        if counts[col] == 0:
            new_cols.append(col)
        else:
            new_cols.append(f"{col}_{counts[col]}")
        counts[col] += 1
    return new_cols


def detect_metadata_columns(df):
    cols = [str(c).lower() for c in df.columns]
    col_map = {}

    def find_col(keywords):
        for i, c in enumerate(cols):
            for kw in keywords:
                if kw in c:
                    return df.columns[i]
        return None

    col_map["name"] = find_col(["name", "student"])
    col_map["email"] = find_col(["email"])
    col_map["phone"] = find_col(["phone", "mobile", "contact"])
    col_map["conversion"] = find_col(["conversion", "status"])
    col_map["payment_date"] = find_col(["payment date", "paid on", "date of payment", "deposit"])
    col_map["community_status"] = find_col(["community", "retention", "active"])
    col_map["lead_score"] = find_col(["lead score", "score"])

    return col_map


def safe_to_datetime(series):
    try:
        return pd.to_datetime(series, errors="coerce")
    except:
        return pd.Series([pd.NaT] * len(series))


# -----------------------------
# Sheet Cleaning Logic (Aligned to User's Working Code)
# -----------------------------

def clean_sheet(df_raw):
    """
    Excel Structure Assumption (based on uploaded file):
    - Row 1 (index 0): Event headers (from column 12 onwards)
    - Row 3 (index 2): Main headers (metadata)
    - Data starts from Row 4 (index 3)
    """

    df_raw = df_raw.copy()

    # Rows
    event_header_row = 0
    main_header_row = 2
    data_start_row = 3

    # Extract headers safely
    main_headers = df_raw.iloc[main_header_row, :12].astype(str)
    event_headers = df_raw.iloc[event_header_row, 12:].astype(str)

    columns = list(main_headers) + list(event_headers)

    df = df_raw.iloc[data_start_row:].reset_index(drop=True)
    df.columns = columns

    # Clean column names
    df.columns = (
        df.columns.astype(str)
        .str.replace("\n", " ", regex=True)
        .str.replace("\r", " ", regex=True)
        .str.replace("\u00a0", " ", regex=True)
        .str.strip()
    )

    # Make column names unique
    df.columns = make_unique(df.columns)

    # Drop fully empty rows
    df = df.dropna(how="all")

    # Drop numeric-only rows (totals / aggregates)
    def is_numeric_row(row):
        vals = [str(x).strip() for x in row if pd.notna(x)]
        if len(vals) == 0:
            return False
        return all(v.replace(".", "", 1).isdigit() for v in vals)

    df = df[~df.apply(is_numeric_row, axis=1)]

    return df


def get_event_columns(df, metadata_cols):
    meta_cols = [v for v in metadata_cols.values() if v and v in df.columns]
    event_cols = [c for c in df.columns if c not in meta_cols]
    return event_cols


def compute_lead_score(df, event_cols, metadata_cols):
    df = df.copy()
    df["_event_count"] = df[event_cols].sum(axis=1)

    score = df["_event_count"] * 10

    if metadata_cols.get("conversion"):
        conv_col = metadata_cols["conversion"]
        score += df[conv_col].astype(str).str.lower().apply(
            lambda x: 50 if "paid" in x or "admitted" in x else 30 if "will" in x else 0
        )

    if metadata_cols.get("community_status"):
        comm_col = metadata_cols["community_status"]
        score += df[comm_col].astype(str).str.lower().apply(lambda x: 20 if "in" in x or "active" in x else 0)

    df["Lead Score"] = score
    return df


# -----------------------------
# App Layout
# -----------------------------

st.title("📊 Engagement Analytics Dashboard")
st.write("Upload your Master Engagement Tracker Excel file.")

uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    xls = pd.ExcelFile(uploaded_file)
    sheet_names = xls.sheet_names

    selected_sheet = st.selectbox("Select Sheet", sheet_names)

    df_raw = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=None)
    df = clean_sheet(df_raw)

    metadata_cols = detect_metadata_columns(df)
    event_cols = get_event_columns(df, metadata_cols)

    # Normalize event columns safely
    clean_event_cols = []
    for col in event_cols:
        if col in df.columns:
            df[col] = df[col].apply(normalize_binary)
            clean_event_cols.append(col)
    event_cols = clean_event_cols

    # Participation count
    df["Total Participations"] = df[event_cols].sum(axis=1) if event_cols else 0

    # Lead scoring
    df = compute_lead_score(df, event_cols, metadata_cols)

    # Extract key columns
    name_col = metadata_cols.get("name")
    conversion_col = metadata_cols.get("conversion")
    payment_col = metadata_cols.get("payment_date")

    if payment_col and payment_col in df.columns:
        df[payment_col] = safe_to_datetime(df[payment_col])
    else:
        payment_col = None

    # -----------------------------
    # METRICS
    # -----------------------------

    total_students = len(df)
    active_students = (df["Total Participations"] > 0).sum()

    paid_students = 0
    if conversion_col and conversion_col in df.columns:
        paid_students = df[conversion_col].astype(str).str.lower().str.contains("paid|admitted", na=False).sum()

    conversion_rate = (paid_students / active_students * 100) if active_students > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Students", total_students)
    col2.metric("Active Students", active_students)
    col3.metric("Paid / Admitted", paid_students)
    col4.metric("Conversion Rate", f"{conversion_rate:.1f}%")

    st.divider()

    # -----------------------------
    # 1️⃣ Top Participating Students
    # -----------------------------

    st.header("1️⃣ Top Participating Students")

    top_participants = df.sort_values("Total Participations", ascending=False)
    display_cols = [c for c in [name_col, "Total Participations", conversion_col, "Lead Score"] if c and c in df.columns]

    st.dataframe(top_participants[display_cols], use_container_width=True, height=300)

    st.divider()

    # -----------------------------
    # 2️⃣ Payment & Conversion Analysis
    # -----------------------------

    st.header("2️⃣ Payment & Conversion Analysis")

    if conversion_col and conversion_col in df.columns:
        conv_series = df[conversion_col].astype(str).str.lower()

        paid_df = df[conv_series.str.contains("paid|admitted", na=False)]
        will_pay_df = df[conv_series.str.contains("will", na=False)]
        not_paid_df = df[~(conv_series.str.contains("paid|admitted|will", na=False))]

        st.subheader("✅ Paid / Admitted")
        st.dataframe(paid_df[display_cols], use_container_width=True, height=200)

        st.subheader("🟡 Will Pay")
        st.dataframe(will_pay_df[display_cols], use_container_width=True, height=200)

        st.subheader("🔴 Not Paid")
        st.dataframe(not_paid_df[display_cols], use_container_width=True, height=200)

    else:
        st.info("Conversion Status column not found in this sheet.")

    st.divider()

    # -----------------------------
    # 3️⃣ Retention Analysis (PG Sheets Only)
    # -----------------------------

    st.header("3️⃣ Retention Analysis")

    if payment_col and conversion_col and conversion_col in df.columns:
        retention_flags = []

        for idx, row in df.iterrows():
            pay_date = row[payment_col]
            if pd.isna(pay_date):
                retention_flags.append(False)
                continue

            participated_after = row[event_cols].sum() > 0 if event_cols else False
            retention_flags.append(participated_after)

        df["Retained"] = retention_flags

        retained_students = df[df["Retained"]]
        retention_rate = (len(retained_students) / paid_students * 100) if paid_students > 0 else 0

        st.metric("Retention Rate", f"{retention_rate:.1f}%")
        st.subheader("Retained Students")
        display_cols_ret = [c for c in [name_col, conversion_col, payment_col, "Retained"] if c and c in df.columns]
        st.dataframe(retained_students[display_cols_ret], use_container_width=True, height=300)

    else:
        st.info("Payment Date or Conversion Status column not found — Retention analysis skipped (UG sheet).")

    st.divider()

    # -----------------------------
    # 4️⃣ Students With NO Event Participation
    # -----------------------------

    st.header("4️⃣ Students With NO Event Participation")

    no_participation_df = df[df["Total Participations"] == 0]
    display_cols_no = [c for c in [name_col, conversion_col, payment_col] if c and c in df.columns]

    st.dataframe(no_participation_df[display_cols_no], use_container_width=True, height=300)

    st.divider()

    # -----------------------------
    # 5️⃣ Paid Students With Low / No Engagement
    # -----------------------------

    st.header("5️⃣ Paid Students With Low / No Engagement")

    if conversion_col and conversion_col in df.columns:
        conv_series = df[conversion_col].astype(str).str.lower()
        paid_df = df[conv_series.str.contains("paid|admitted", na=False)]
        paid_low_engagement = paid_df[paid_df["Total Participations"] <= 1]
        st.dataframe(paid_low_engagement[display_cols], use_container_width=True, height=300)
    else:
        st.info("Conversion Status column not found.")

    st.divider()

    # -----------------------------
    # 6️⃣ Event-wise Participation
    # -----------------------------

    st.header("6️⃣ Event-wise Participation")

    if event_cols:
        event_participation = df[event_cols].sum().reset_index()
        event_participation.columns = ["Event", "Participants"]

        fig = px.bar(event_participation, x="Event", y="Participants", title="Event-wise Participation")
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(event_participation, use_container_width=True, height=300)
    else:
        st.info("No event columns detected in this sheet.")

    st.divider()

    # -----------------------------
    # 7️⃣ Per-Student Participation Timeline
    # -----------------------------

    st.header("7️⃣ Per-Student Participation Timeline")

    if name_col and name_col in df.columns and event_cols:
        student_names = df[name_col].dropna().astype(str).unique().tolist()
        selected_student = st.selectbox("Select Student", student_names)

        student_row = df[df[name_col] == selected_student].iloc[0]

        participation_values = []
        for col in event_cols:
            val = student_row[col]
            try:
                participation_values.append(int(val))
            except:
                participation_values.append(0)

        timeline_df = pd.DataFrame({
            "Event": event_cols,
            "Participation": participation_values
        })

        # Break lines for non-participation
        timeline_df["PlotValue"] = timeline_df["Participation"].replace({0: np.nan})

        fig2 = px.line(timeline_df, x="Event", y="PlotValue", markers=True,
                       title=f"Participation Timeline — {selected_student}")

        # Mark payment date if available
        if payment_col and not pd.isna(student_row[payment_col]):
            fig2.add_annotation(x=timeline_df["Event"].iloc[0], y=1,
                                text="✔ Payment",
                                showarrow=False,
                                font=dict(color="green", size=14))

        st.plotly_chart(fig2, use_container_width=True)

    else:
        st.info("Student Name or Event columns not found — Timeline view unavailable.")

    st.divider()

    # -----------------------------
    # 🏆 Lead Score Leaderboard
    # -----------------------------

    st.header("🏆 Lead Score Leaderboard")

    lead_leaderboard = df.sort_values("Lead Score", ascending=False)
    st.dataframe(lead_leaderboard[display_cols], use_container_width=True, height=300)

else:
    st.info("Please upload an Excel file to begin.")
