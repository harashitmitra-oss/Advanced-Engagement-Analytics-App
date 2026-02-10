"""
Advanced Engagement Analytics App
---------------------------------
Streamlit app for advanced engagement analytics with timeline visualization.

Deployment Notes:
- This app is designed for Streamlit Cloud.
- It does NOT assume any local file path.
- Users must upload an Excel file via the UI.

If you see `ModuleNotFoundError: No module named 'streamlit'`,
install dependencies first:

    pip install streamlit pandas numpy matplotlib plotly openpyxl
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

def load_group_sheet(file, sheet_name, event_header_row=0, event_date_row=1, main_header_row=2, data_start_row=3):
    """
    Loads a group sheet where:
    - event_header_row: row containing event names
    - event_date_row: row containing event dates
    - main_header_row: row containing main column headers
    - data_start_row: row where student data begins
    """
    raw = pd.read_excel(file, sheet_name=sheet_name, header=None)

    event_headers = raw.iloc[event_header_row].tolist()
    event_dates = raw.iloc[event_date_row].tolist()
    main_headers = raw.iloc[main_header_row].tolist()

    df = raw.iloc[data_start_row:].copy()
    df.columns = main_headers
    df = df.reset_index(drop=True)

    # Replace unnamed columns with event headers
    for i, col in enumerate(df.columns):
        if pd.isna(col) or str(col).lower().startswith("unnamed"):
            df.columns.values[i] = event_headers[i]

    # Build event metadata
    event_meta = []
    for name, date in zip(event_headers, event_dates):
        if pd.notna(name) and pd.notna(date):
            try:
                parsed_date = pd.to_datetime(date, dayfirst=True)
            except Exception:
                parsed_date = None
            event_meta.append({"Event Column": name, "Event": str(name).strip(), "Event Date": parsed_date})

    event_meta_df = pd.DataFrame(event_meta)

    return df, event_meta_df


def extract_event_columns(df):
    base_cols = [
        "Student Name",
        "E mail",
        "Phone Number",
        "Country",
        "Income",
        "Batch",
        "Data Added to the community",
        "Community Status",
        "Date of Exit",
        "Conversion Status",
        "Overall Engagement Score",
        "Payment Date",
        "Comments",
    ]
    return [col for col in df.columns if col not in base_cols]


def preprocess_events(df, event_cols, event_meta_df):
    records = []
    event_date_map = dict(zip(event_meta_df["Event Column"], event_meta_df["Event Date"]))

    for _, row in df.iterrows():
        student = row.get("Student Name")
        phone = row.get("Phone Number")
        for col in event_cols:
            val = str(row.get(col)).strip().lower()
            if val in ["yes", "y", "true", "1"]:
                records.append({
                    "Student Name": student,
                    "Phone Number": phone,
                    "Event": col,
                    "Event Date": event_date_map.get(col),
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

        conversion_points = 5 if str(row.get("Conversion Status")).lower() in ["paid", "admitted", "will pay", "will pay - high", "will pay - medium", "will pay - low"] else 0
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
        raise RuntimeError("Streamlit is not installed. Install it with: pip install streamlit")

    st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")
    st.title("🎓 Advanced Student Engagement & Timeline Analytics")

    uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])

    if not uploaded_file:
        st.info("Please upload an Excel file to begin analysis.")
        return

    xls = pd.ExcelFile(uploaded_file)
    sheet_names = xls.sheet_names

    st.subheader("Select Group / Sheet")
    selected_sheet = st.selectbox("Choose a group", sheet_names)

    # Header row configuration (matches your dataset)
    event_header_row = 0   # row 1 in Excel
    event_date_row = 1     # row 2 in Excel
    main_header_row = 2    # row 3 in Excel
    data_start_row = 3     # row 4 in Excel

    df, event_meta_df = load_group_sheet(
        uploaded_file,
        selected_sheet,
        event_header_row=event_header_row,
        event_date_row=event_date_row,
        main_header_row=main_header_row,
        data_start_row=data_start_row,
    )

    event_cols = extract_event_columns(df)
    events_df = preprocess_events(df, event_cols, event_meta_df)

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

    paid_students = df[df["Conversion Status"].astype(str).str.lower().str.contains("paid|admitted|will pay")]
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
                payment_date = pd.to_datetime(payment_row.iloc[0].get("Payment Date"), dayfirst=True)
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
# Entry Point
# -----------------------------

if __name__ == "__main__":
    if st is not None:
        run_streamlit_app()
    else:
        print("Streamlit is not installed. Install it with: pip install streamlit")
