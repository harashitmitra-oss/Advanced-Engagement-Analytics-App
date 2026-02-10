"""
Advanced Engagement Analytics App
---------------------------------
This script is intended to be run as a Streamlit app:

    streamlit run advanced_engagement_analytics_app.py

If you see `ModuleNotFoundError: No module named 'streamlit'`,
install dependencies first:

    pip install streamlit pandas numpy matplotlib plotly openpyxl

This file also supports running in a non-Streamlit environment for
basic data-processing tests (see __main__ section).
"""

# -----------------------------
# Safe Imports
# -----------------------------

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
from datetime import datetime
import re

# -----------------------------
# Utility & Preprocessing
# -----------------------------

def load_excel_sheet(file, sheet_name, event_header_row, main_header_row, data_start_row):
    """
    Loads an Excel sheet where:
    - event_header_row: row containing event names
    - main_header_row: row containing main column headers
    - data_start_row: row where student data begins
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
            df.columns.values[i] = event_headers[i]

    return df


def extract_event_columns(df):
    base_cols = [
        "Student Name",
        "Phone Number",
        "Conversion Status",
        "Community Status",
        "Payment Date",
    ]
    event_cols = [col for col in df.columns if col not in base_cols]
    return event_cols


def parse_event_name_and_date(col_name):
    match = re.search(r"(.*)\((\d{2}-\d{2}-\d{4})\)", str(col_name))
    if match:
        event_name = match.group(1).strip()
        event_date = datetime.strptime(match.group(2), "%d-%m-%Y")
    else:
        event_name = str(col_name)
        event_date = None
    return event_name, event_date


def preprocess_events(df, event_cols):
    records = []
    for _, row in df.iterrows():
        student = row.get("Student Name")
        phone = row.get("Phone Number")
        for col in event_cols:
            val = str(row[col]).strip().lower()
            if val in ["yes", "y", "true", "1"]:
                event_name, event_date = parse_event_name_and_date(col)
                records.append({
                    "Student Name": student,
                    "Phone Number": phone,
                    "Event": event_name,
                    "Event Date": event_date,
                })
    return pd.DataFrame(records)


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


def calculate_lead_score(df, events_df):
    scores = []
    for _, row in df.iterrows():
        student = row.get("Student Name")
        student_events = events_df[events_df["Student Name"] == student]

        event_points = len(student_events)
        hackathon_points = sum(student_events["Event"].str.contains("hackathon", case=False, na=False)) * 3
        ama_points = sum(student_events["Event"].str.contains("ama", case=False, na=False)) * 2
        masterclass_points = sum(student_events["Event"].str.contains("masterclass", case=False, na=False)) * 2

        conversion_points = 5 if str(row.get("Conversion Status")).lower() in ["paid", "admitted", "will pay"] else 0
        retention_points = 3 if str(row.get("Community Status")).lower() == "in" else 0

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
# Streamlit App Layout
# -----------------------------

def run_streamlit_app():
    if st is None:
        raise RuntimeError(
            "Streamlit is not installed. Install it with: pip install streamlit"
        )

    st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")
    st.title("🎓 Advanced Student Engagement & Timeline Analytics")

    uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])

    if uploaded_file:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names

        st.subheader("Select Group / Sheet")
        selected_sheet = st.selectbox("Choose a group", sheet_names)

        # Header row configuration (can later be customized per sheet)
        event_header_row = 0   # row 1 in Excel
        main_header_row = 2    # row 4 in Excel
        data_start_row = 3     # row 5 in Excel

        df = load_excel_sheet(uploaded_file, selected_sheet, event_header_row, main_header_row, data_start_row)
        event_cols = extract_event_columns(df)
        events_df = preprocess_events(df, event_cols)

        # -----------------------------
        # Student Participation Analysis
        # -----------------------------
        st.header("📊 Student Participation Analysis")

        total_participants = events_df["Student Name"].nunique()
        st.metric("Total Participants", total_participants)

        st.subheader("List of Participating Students")
        st.dataframe(events_df[["Student Name", "Phone Number"]].drop_duplicates())

        st.subheader("Student-wise Participation")
        student_counts = events_df["Student Name"].value_counts().reset_index()
        student_counts.columns = ["Student Name", "Participation Count"]
        fig1 = px.bar(student_counts, x="Student Name", y="Participation Count")
        st.plotly_chart(fig1, use_container_width=True)

        st.subheader("Event-wise Participation")
        event_counts = events_df["Event"].value_counts().reset_index()
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

        paid_students = df[df["Conversion Status"].astype(str).str.lower().isin(["paid", "admitted", "will pay"])]
        st.subheader("Students Who Paid / Will Pay / Admitted")
        st.dataframe(paid_students[["Student Name", "Phone Number", "Conversion Status", "Payment Date"]])

        paid_participants = events_df[events_df["Student Name"].isin(paid_students["Student Name"])]
        participation_rate_paid = (
            paid_participants["Student Name"].nunique() / paid_students.shape[0]
            if paid_students.shape[0] > 0 else 0
        )

        conversion_rate = paid_students.shape[0] / df.shape[0]
        retention_rate = df[df["Community Status"].astype(str).str.lower() == "in"].shape[0] / df.shape[0]

        col1, col2, col3 = st.columns(3)
        col1.metric("Participation Rate (Paid)", f"{participation_rate_paid:.2%}")
        col2.metric("Conversion Rate", f"{conversion_rate:.2%}")
        col3.metric("Retention Rate", f"{retention_rate:.2%}")

        st.info("🏆 Winners who paid logic is future-ready and can be integrated when winner data becomes available.")

        # -----------------------------
        # Event Category Analysis
        # -----------------------------
        st.header("🗂 Event Category Analysis")

        events_df["Category"] = events_df["Event"].apply(categorize_event)
        categories = ["Startup Hackathon", "AMA", "Masterclass"]

        for cat in categories:
            st.subheader(cat)
            cat_events = events_df[events_df["Category"] == cat]
            st.metric("Participation Rate", f"{cat_events['Student Name'].nunique() / df.shape[0]:.2%}")
            st.dataframe(cat_events[["Student Name", "Phone Number", "Event"]].drop_duplicates())

        # -----------------------------
        # Lead Scoring System
        # -----------------------------
        st.header("🏅 Lead Scoring System")

        lead_scores_df = calculate_lead_score(df, events_df)
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

        student_events = events_df[events_df["Student Name"] == selected_student].copy()

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

    else:
        st.info("Please upload an Excel file to begin analysis.")


# -----------------------------
# Basic Tests (Non-Streamlit)
# -----------------------------

def _test_parse_event_name_and_date():
    name, date = parse_event_name_and_date("Startup Hackathon (12-01-2024)")
    assert name == "Startup Hackathon"
    assert date == datetime(2024, 1, 12)

    name, date = parse_event_name_and_date("AMA Session")
    assert name == "AMA Session"
    assert date is None


def _test_extract_event_columns():
    df = pd.DataFrame({
        "Student Name": ["A"],
        "Phone Number": [123],
        "Conversion Status": ["paid"],
        "Community Status": ["in"],
        "Payment Date": ["2024-01-01"],
        "Startup Hackathon (12-01-2024)": ["Yes"],
        "AMA (15-01-2024)": ["No"],
    })
    events = extract_event_columns(df)
    assert "Startup Hackathon (12-01-2024)" in events
    assert "AMA (15-01-2024)" in events
    assert "Student Name" not in events


def _test_preprocess_events():
    df = pd.DataFrame({
        "Student Name": ["A", "B"],
        "Phone Number": [111, 222],
        "Startup Hackathon (12-01-2024)": ["Yes", "No"],
        "AMA (15-01-2024)": ["Yes", "Yes"],
    })
    events = extract_event_columns(df)
    events_df = preprocess_events(df, events)
    assert len(events_df) == 3
    assert set(events_df["Student Name"]) == {"A", "B"}


if __name__ == "__main__":
    # Run basic tests
    _test_parse_event_name_and_date()
    _test_extract_event_columns()
    _test_preprocess_events()

    # Only run Streamlit app if streamlit is available
    if st is not None:
        run_streamlit_app()
    else:
        print("Streamlit is not installed. Install it with: pip install streamlit")

