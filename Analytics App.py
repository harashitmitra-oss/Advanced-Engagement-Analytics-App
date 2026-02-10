# === Advanced Engagement Analytics App (Robust, Multi-Sheet, Production-Ready) ===

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")

# -------------------------------------------------------------------
# -------------------------- DATA LOADING ---------------------------
# -------------------------------------------------------------------

def normalize_yes_no(series):
    """Safely normalize Yes/No/Blank/NaN values to 1/0."""
    return (
        series
        .fillna(0)
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({
            "yes": 1, "y": 1, "true": 1, "1": 1,
            "no": 0, "n": 0, "false": 0, "0": 0,
            "nan": 0, "none": 0, "": 0
        })
        .apply(lambda x: 1 if str(x).isdigit() and int(x) > 0 else 0)
        .astype(int)
    )


def make_columns_unique(cols):
    """Ensure no duplicate column names."""
    seen = {}
    new_cols = []
    for col in cols:
        col = str(col).strip()
        if col in seen:
            seen[col] += 1
            new_cols.append(f"{col}_{seen[col]}")
        else:
            seen[col] = 0
            new_cols.append(col)
    return new_cols


def find_column(df, keywords):
    """Find first column that contains any keyword (case-insensitive)."""
    for col in df.columns:
        col_l = str(col).lower()
        for kw in keywords:
            if kw in col_l:
                return col
    return None


def load_group_sheet(file, sheet_name):
    """
    Expected structure per sheet:
    Row 0 -> Event names
    Row 1 -> Event dates
    Row 2 -> Main headers
    Row 3+ -> Data
    """

    raw = pd.read_excel(file, sheet_name=sheet_name, header=None)

    event_header_row = 0
    date_header_row = 1
    main_header_row = 2
    data_start_row = 3

    event_headers = raw.iloc[event_header_row]
    date_headers = raw.iloc[date_header_row]
    main_headers = raw.iloc[main_header_row]

    final_headers = []
    event_cols = []
    event_meta = []

    for col_idx, base_col in enumerate(main_headers):
        event_name = event_headers[col_idx]
        event_date = date_headers[col_idx]

        if pd.notna(event_name) and str(event_name).strip() != "":
            col_name = str(event_name).strip()
            final_headers.append(col_name)
            event_cols.append(col_name)
            event_meta.append({
                "Column": col_name,
                "Event Name": col_name,
                "Event Date": event_date
            })
        else:
            final_headers.append(str(base_col).strip())

    final_headers = make_columns_unique(final_headers)

    df = raw.iloc[data_start_row:].reset_index(drop=True)
    df.columns = final_headers

    event_meta_df = pd.DataFrame(event_meta)

    return df, event_cols, event_meta_df


# -------------------------------------------------------------------
# ----------------------- ANALYTICS FUNCTIONS ------------------------
# -------------------------------------------------------------------

def student_participation_analysis(df, event_cols, event_meta_df):
    df = df.copy()

    for col in event_cols:
        if col in df.columns:
            df[col] = normalize_yes_no(df[col])

    df["Total Events Participated"] = df[event_cols].sum(axis=1)

    student_participation = df[["Student Name", "Total Events Participated"]]

    event_participation = (
        df[event_cols]
        .sum()
        .reset_index()
        .rename(columns={"index": "Column", 0: "Participants"})
        .merge(event_meta_df, on="Column", how="left")
    )

    participants = []
    for col in event_cols:
        if col in df.columns:
            participating_students = df.loc[df[col] == 1, "Student Name"].tolist()
            participants.append({
                "Column": col,
                "Participants": participating_students
            })

    participants = pd.DataFrame(participants).merge(event_meta_df, on="Column", how="left")

    return student_participation, event_participation, participants


def categorize_event(name):
    name_l = str(name).lower()
    if "hackathon" in name_l:
        return "Startup Hackathon"
    elif "ama" in name_l:
        return "AMA"
    elif "masterclass" in name_l:
        return "Masterclass"
    else:
        return "Other"


# -------------------------------------------------------------------
# ----------------------- STREAMLIT APP ------------------------------
# -------------------------------------------------------------------

def run_streamlit_app():
    st.title("📊 Advanced Engagement Analytics Dashboard")

    uploaded_file = st.file_uploader("Upload your Master Engagement Tracker Excel file", type=["xlsx"])

    if not uploaded_file:
        st.info("Please upload your Excel file to continue.")
        return

    xls = pd.ExcelFile(uploaded_file)
    sheet_names = xls.sheet_names

    selected_sheet = st.sidebar.selectbox("Select Group / Sheet", sheet_names)

    df, event_cols, event_meta_df = load_group_sheet(uploaded_file, selected_sheet)

    # ------------------- SAFE COLUMN DETECTION -------------------
    name_col = find_column(df, ["student name", "name"])
    conversion_col = find_column(df, ["conversion status", "conversion"])
    community_col = find_column(df, ["community status", "community"])
    payment_date_col = find_column(df, ["payment date", "payment"])

    if not name_col:
        st.error("❌ Student Name column not found. Please check your sheet.")
        return

    df = df.rename(columns={name_col: "Student Name"})

    st.subheader("🔍 Raw Data Preview")
    st.dataframe(df.head())

    # ------------------- NORMALIZE EVENTS -------------------
    for col in event_cols:
        if col in df.columns:
            df[col] = normalize_yes_no(df[col])

    df["Total Events Participated"] = df[event_cols].sum(axis=1)

    # ------------------- CONVERSION & RETENTION -------------------
    if conversion_col:
        conv_series = df[conversion_col]
        if isinstance(conv_series, pd.DataFrame):
            conv_series = conv_series.iloc[:, 0]
        conv_series = conv_series.astype(str).str.lower()
        df["Converted"] = conv_series.str.contains("paid|admitted|will pay", na=False)
        df["Conversion Status Clean"] = df[conversion_col].astype(str)
    else:
        df["Converted"] = False
        df["Conversion Status Clean"] = "Unknown"

    if community_col:
        comm_series = df[community_col]
        if isinstance(comm_series, pd.DataFrame):
            comm_series = comm_series.iloc[:, 0]
        comm_series = comm_series.astype(str).str.lower()
        df["Retained"] = comm_series.str.contains("in|retained", na=False)
    else:
        df["Retained"] = False

    # ------------------- KPI SECTION -------------------
    st.subheader("📌 Key Performance Indicators")

    total_students = len(df)
    active_students = (df["Total Events Participated"] > 0).sum()
    converted_students = df["Converted"].sum()
    retention_rate = round((df["Retained"].sum() / total_students) * 100, 2) if total_students else 0

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Students", total_students)
    k2.metric("Active Students", active_students)
    k3.metric("Converted / Will Pay", converted_students)
    k4.metric("Retention Rate (%)", retention_rate)

    # ------------------- 🏆 LEADERBOARD SECTION -------------------
    st.header("🏆 Student Participation Leaderboard")

    df_scoring = df.copy()

    # Event points
    df_scoring["Event Points"] = df_scoring[event_cols].sum(axis=1)

    # Category points
    event_meta_df["Category"] = event_meta_df["Event Name"].apply(categorize_event)
    df_scoring["Category Points"] = 0

    for _, row in event_meta_df.iterrows():
        col = row["Column"]
        category = row["Category"]
        if col in df_scoring.columns:
            if category == "Startup Hackathon":
                df_scoring["Category Points"] += df_scoring[col] * 3
            elif category in ["AMA", "Masterclass"]:
                df_scoring["Category Points"] += df_scoring[col] * 2
            else:
                df_scoring["Category Points"] += df_scoring[col] * 1

    # Conversion points
    df_scoring["Conversion Points"] = np.where(
        df_scoring["Converted"], 10, 0
    )

    # Retention points
    df_scoring["Retention Points"] = np.where(
        df_scoring["Retained"], 5, 0
    )

    df_scoring["Lead Score"] = (
        df_scoring["Event Points"] +
        df_scoring["Category Points"] +
        df_scoring["Conversion Points"] +
        df_scoring["Retention Points"]
    )

    leaderboard = df_scoring[[
        "Student Name",
        "Total Events Participated",
        "Lead Score",
        "Conversion Status Clean"
    ]].sort_values(by=["Total Events Participated", "Lead Score"], ascending=False)

    st.dataframe(leaderboard, use_container_width=True)

    # ------------------- 📈 PARTICIPATION ANALYSIS -------------------
    st.header("📈 Participation Analysis")

    student_participation, event_participation, participants = student_participation_analysis(
        df, event_cols, event_meta_df
    )

    fig1 = px.bar(
        student_participation.sort_values("Total Events Participated", ascending=False),
        x="Student Name",
        y="Total Events Participated",
        title="Student-wise Participation Count"
    )
    st.plotly_chart(fig1, use_container_width=True)

    fig2 = px.bar(
        event_participation.sort_values("Participants", ascending=False),
        x="Event Name",
        y="Participants",
        title="Event-wise Participation Count"
    )
    st.plotly_chart(fig2, use_container_width=True)

    total_participants = (df["Total Events Participated"] > 0).sum()
    non_participants = len(df) - total_participants

    fig3 = px.pie(
        names=["Participated", "Did Not Participate"],
        values=[total_participants, non_participants],
        title="Participation Percentage"
    )
    st.plotly_chart(fig3, use_container_width=True)

    # ------------------- 🗂 EVENT CATEGORY ANALYSIS -------------------
    st.header("🗂 Event Category Analysis")

    for category in event_meta_df["Category"].unique():
        st.subheader(category)
        cat_events = event_meta_df[event_meta_df["Category"] == category]["Column"].tolist()

        if not cat_events:
            st.info("No events in this category.")
            continue

        cat_participations = df[cat_events].sum().sum()
        cat_students = df.loc[df[cat_events].sum(axis=1) > 0, "Student Name"].tolist()

        st.metric("Total Participations", int(cat_participations))
        st.write("Students:")
        st.write(cat_students)

    # ------------------- 💰 PAYMENT & CONVERSION ANALYSIS -------------------
    st.header("💰 Payment & Conversion Analysis")

    if conversion_col:
        paid_students = df.loc[df["Converted"]]
        st.subheader("Students Who Paid / High Intent")
        st.dataframe(paid_students[["Student Name", "Conversion Status Clean"]])

        conversion_rate = round((converted_students / total_students) * 100, 2) if total_students else 0
        st.metric("Conversion Rate (%)", conversion_rate)
    else:
        st.warning("⚠️ Conversion Status column not found.")

    # ------------------- 🕒 PER-STUDENT TIMELINE -------------------
    st.header("🕒 Per-Student Timeline")

    selected_student = st.selectbox("Select Student", df["Student Name"].dropna().unique())

    student_row = df[df["Student Name"] == selected_student].iloc[0]

    timeline_data = []

    for _, row in event_meta_df.iterrows():
        col = row["Column"]
        event_name = row["Event Name"]
        event_date = row["Event Date"]

        if col in df.columns:
            value = student_row[col]
            value_norm = normalize_yes_no(pd.Series([value])).iloc[0]

            if value_norm == 1:
                event_date_parsed = pd.to_datetime(event_date, errors="coerce")
                timeline_data.append({
                    "Date": event_date_parsed,
                    "Event": event_name,
                    "Type": "Event"
                })

    if payment_date_col:
        payment_val = student_row[payment_date_col]
        payment_date = pd.to_datetime(payment_val, errors="coerce")

        if pd.notna(payment_date):
            timeline_data.append({
                "Date": payment_date,
                "Event": "Payment ✔",
                "Type": "Payment"
            })

    timeline_df = pd.DataFrame(timeline_data).dropna(subset=["Date"])

    if not timeline_df.empty:
        fig4 = px.scatter(
            timeline_df,
            x="Date",
            y=[1] * len(timeline_df),
            color="Type",
            text="Event",
            title=f"Timeline for {selected_student}"
        )
        fig4.update_traces(textposition="top center")
        fig4.update_yaxes(visible=False)
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("No timeline data available for this student.")


if __name__ == "__main__":
    run_streamlit_app()
