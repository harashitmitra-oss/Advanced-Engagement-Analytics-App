"""
Advanced Engagement Analytics Streamlit App
------------------------------------------
Upload your Excel file and analyze student engagement, participation,
conversions, lead scores, and per-student timelines.

This version is built specifically to work with your uploaded file
structure (multiple header rows, mixed Yes/No event columns, multiple sheets).

Run with:
    streamlit run app.py

Dependencies:
    pip install streamlit pandas numpy plotly openpyxl
"""

# -----------------------------
# Imports
# -----------------------------

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime
import re

# -----------------------------
# Configuration
# -----------------------------

EVENT_HEADER_ROW = 0   # Row with event names
MAIN_HEADER_ROW = 2    # Row with main column headers
DATA_START_ROW = 3     # First row of actual data

BASE_COLUMNS = [
    "Student Name",
    "Phone Number",
    "Conversion Status",
    "Community Status",
    "Payment Date",
]

# -----------------------------
# Utility Functions
# -----------------------------

def normalize_yes_no(series):
    """
    Safely normalize any Yes/No style column to 0/1.
    Handles NaN, blanks, Yes/No, True/False, 1/0, random text.
    """
    return (
        series
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({
            "yes": 1, "y": 1, "true": 1, "1": 1,
            "no": 0, "n": 0, "false": 0, "0": 0,
            "nan": 0, "": 0, "none": 0
        })
        .apply(lambda x: 1 if x == 1 else 0)
    )


def parse_event_name_and_date(col_name):
    """
    Extract event name and date from column header like:
    "Startup Hackathon (12-01-2024)"
    """
    match = re.search(r"(.*)\((\d{2}-\d{2}-\d{4})\)", str(col_name))
    if match:
        event_name = match.group(1).strip()
        event_date = datetime.strptime(match.group(2), "%d-%m-%Y")
    else:
        event_name = str(col_name)
        event_date = None
    return event_name, event_date


def load_group_sheet(file, sheet_name,
                     event_header_row=EVENT_HEADER_ROW,
                     main_header_row=MAIN_HEADER_ROW,
                     data_start_row=DATA_START_ROW):
    """
    Load one sheet with messy multi-row headers and return:
    - Clean dataframe
    - Event columns
    - Event metadata dataframe
    """
    raw = pd.read_excel(file, sheet_name=sheet_name, header=None)

    event_headers = raw.iloc[event_header_row].tolist()
    main_headers = raw.iloc[main_header_row].tolist()

    df = raw.iloc[data_start_row:].copy()
    df.columns = main_headers
    df = df.reset_index(drop=True)

    # Replace unnamed columns with event headers
    for i, col in enumerate(df.columns):
        if pd.isna(col) or str(col).lower().startswith("unnamed"):
            if i < len(event_headers):
                df.columns.values[i] = event_headers[i]

    # Identify event columns (everything except base columns)
    event_cols = [col for col in df.columns if col not in BASE_COLUMNS]

    # Build event metadata
    meta_rows = []
    for col in event_cols:
        name, date = parse_event_name_and_date(col)
        meta_rows.append({
            "Column": col,
            "Event": name,
            "Event Date": date
        })

    event_meta_df = pd.DataFrame(meta_rows)

    return df, event_cols, event_meta_df


def build_events_long_df(df, event_cols, event_meta_df):
    """
    Convert wide Yes/No event columns into long event participation table.
    """
    df_events = df.copy()
    df_events[event_cols] = df_events[event_cols].apply(normalize_yes_no)

    long_df = df_events.melt(
        id_vars=["Student Name", "Phone Number"],
        value_vars=event_cols,
        var_name="Column",
        value_name="Participated",
    )

    long_df = long_df[long_df["Participated"] == 1]

    long_df = long_df.merge(event_meta_df, on="Column", how="left")

    return long_df[["Student Name", "Phone Number", "Event", "Event Date"]]


def categorize_event(event_name):
    name = str(event_name).lower()
    if "hackathon" in name:
        return "Startup Hackathon"
    elif "ama" in name:
        return "AMA"
    elif "masterclass" in name:
        return "Masterclass"
    else:
        return "Other"


def calculate_lead_scores(df, events_long_df):
    scores = []

    for _, row in df.iterrows():
        student = row.get("Student Name")
        student_events = events_long_df[events_long_df["Student Name"] == student]

        event_points = len(student_events)
        hackathon_points = student_events[student_events["Event"].str.contains("hackathon", case=False, na=False)].shape[0] * 3
        ama_points = student_events[student_events["Event"].str.contains("ama", case=False, na=False)].shape[0] * 2
        masterclass_points = student_events[student_events["Event"].str.contains("masterclass", case=False, na=False)].shape[0] * 2

        conversion_points = 5 if str(row.get("Conversion Status", "")).lower() in ["paid", "admitted", "will pay"] else 0
        retention_points = 3 if str(row.get("Community Status", "")).lower() == "in" else 0

        total_score = (
            event_points
            + hackathon_points
            + ama_points
            + masterclass_points
            + conversion_points
            + retention_points
        )

        scores.append({
            "Student Name": student,
            "Lead Score": total_score,
        })

    return pd.DataFrame(scores)

# -----------------------------
# Streamlit App
# -----------------------------

def run_streamlit_app():
    st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")
    st.title("🎓 Advanced Engagement Analytics & Timelines")

    uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])

    if not uploaded_file:
        st.info("Please upload your engagement tracker Excel file to continue.")
        return

    xls = pd.ExcelFile(uploaded_file)
    sheet_names = xls.sheet_names

    st.sidebar.title("📂 Groups")
    selected_sheet = st.sidebar.selectbox("Select a group", sheet_names)

    df, event_cols, event_meta_df = load_group_sheet(uploaded_file, selected_sheet)

    events_long_df = build_events_long_df(df, event_cols, event_meta_df)

    # -----------------------------
    # Student Participation Analysis
    # -----------------------------
    st.header("📊 Student Participation Analysis")

    total_participants = events_long_df["Student Name"].nunique()
    st.metric("Total Participants", total_participants)

    st.subheader("List of Participating Students")
    st.dataframe(events_long_df[["Student Name", "Phone Number"]].drop_duplicates())

    st.subheader("Student-wise Participation")
    student_counts = events_long_df["Student Name"].value_counts().reset_index()
    student_counts.columns = ["Student Name", "Participation Count"]
    fig1 = px.bar(student_counts, x="Student Name", y="Participation Count")
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("Event-wise Participation")
    event_counts = events_long_df["Event"].value_counts().reset_index()
    event_counts.columns = ["Event", "Participants"]
    fig2 = px.bar(event_counts, x="Event", y="Participants")
    st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Participation Percentage")
    fig3 = px.pie(event_counts, names="Event", values="Participants")
    st.plotly_chart(fig3, use_container_width=True)

    # -----------------------------
    # Payment & Conversion Analysis
    # -----------------------------
    st.header("💳 Payment & Conversion Analysis")

    paid_mask = df["Conversion Status"].astype(str).str.lower().str.contains("paid|admitted|will pay", na=False)
    paid_students = df[paid_mask]

    st.subheader("Students Who Paid / Will Pay / Admitted")
    st.dataframe(paid_students[["Student Name", "Phone Number", "Conversion Status", "Payment Date"]])

    paid_participants = events_long_df[events_long_df["Student Name"].isin(paid_students["Student Name"])]

    participation_rate_paid = (
        paid_participants["Student Name"].nunique() / paid_students.shape[0]
        if paid_students.shape[0] > 0 else 0
    )

    conversion_rate = paid_students.shape[0] / df.shape[0] if df.shape[0] > 0 else 0
    retention_rate = df[df["Community Status"].astype(str).str.lower() == "in"].shape[0] / df.shape[0] if df.shape[0] > 0 else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Participation Rate (Paid)", f"{participation_rate_paid:.2%}")
    col2.metric("Conversion Rate", f"{conversion_rate:.2%}")
    col3.metric("Retention Rate", f"{retention_rate:.2%}")

    st.info("🏆 Winners who paid logic is future-ready and can be added when winner data is available.")

    # -----------------------------
    # Event Category Analysis
    # -----------------------------
    st.header("🗂 Event Category Analysis")

    events_long_df["Category"] = events_long_df["Event"].apply(categorize_event)

    for category in ["Startup Hackathon", "AMA", "Masterclass"]:
        st.subheader(category)
        cat_df = events_long_df[events_long_df["Category"] == category]

        participation_rate = cat_df["Student Name"].nunique() / df.shape[0] if df.shape[0] > 0 else 0
        st.metric("Participation Rate", f"{participation_rate:.2%}")
        st.dataframe(cat_df[["Student Name", "Phone Number", "Event"]].drop_duplicates())

    # -----------------------------
    # Lead Scoring System
    # -----------------------------
    st.header("🏅 Lead Scoring System")

    lead_scores_df = calculate_lead_scores(df, events_long_df)
    leaderboard = lead_scores_df.sort_values(by="Lead Score", ascending=False)

    st.subheader("Top Students by Lead Score")
    st.dataframe(leaderboard)

    st.subheader("Lead Score Distribution")
    fig4 = px.histogram(lead_scores_df, x="Lead Score", nbins=20)
    st.plotly_chart(fig4, use_container_width=True)

    # -----------------------------
    # Per-Student Timeline Visualization
    # -----------------------------
    st.header("🕒 Per-Student Timeline Visualization")

    student_list = sorted(df["Student Name"].dropna().unique())
    selected_student = st.selectbox("Select a student", student_list)

    student_events = events_long_df[events_long_df["Student Name"] == selected_student].copy()

    if not student_events.empty:
        student_events = student_events.sort_values(by="Event Date")

        fig = px.scatter(
            student_events,
            x="Event Date",
            y=[1] * len(student_events),
            text="Event",
        )
        fig.update_traces(textposition="top center")
        fig.update_yaxes(visible=False)

        # Payment marker
        payment_row = df[df["Student Name"] == selected_student]
        if not payment_row.empty and pd.notna(payment_row.iloc[0].get("Payment Date")):
            try:
                payment_date = pd.to_datetime(payment_row.iloc[0].get("Payment Date"))
                fig.add_scatter(
                    x=[payment_date],
                    y=[1],
                    mode="markers+text",
                    text=["✔ Paid"],
                    textposition="bottom center",
                    marker=dict(size=14, color="green"),
                )
            except Exception:
                pass

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No event participation found for this student.")


# -----------------------------
# Run App
# -----------------------------

if __name__ == "__main__":
    run_streamlit_app()
