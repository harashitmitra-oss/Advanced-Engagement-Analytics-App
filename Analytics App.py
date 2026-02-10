"""
Advanced Engagement Analytics App
---------------------------------
Streamlit-ready analytics dashboard for multi-cohort engagement tracking.
Designed for Excel files where:
- Row 0 = Event Names
- Row 1 = Event Dates
- Row 2 = Main Column Headers
- Row 3+ = Student Data
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
import plotly.express as px
from datetime import datetime
import re

# -----------------------------
# Utility & Preprocessing
# -----------------------------

def normalize_yes_no(series):
    return (
        series
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({
            "yes": 1, "y": 1, "true": 1, "1": 1,
            "no": 0, "n": 0, "false": 0, "0": 0,
            "nan": 0, "none": 0, "": 0
        })
        .fillna(0)
        .apply(lambda x: 1 if str(x) == "1" else 0)
    )


def parse_event_name_and_date(name, date_val):
    event_name = str(name).strip()
    try:
        event_date = pd.to_datetime(date_val, errors="coerce")
    except Exception:
        event_date = None
    return event_name, event_date


def load_group_sheet(file, sheet_name, event_header_row=0, date_header_row=1, main_header_row=2, data_start_row=3):
    raw = pd.read_excel(file, sheet_name=sheet_name, header=None)

    event_names = raw.iloc[event_header_row]
    event_dates = raw.iloc[date_header_row]
    main_headers = raw.iloc[main_header_row]

    df = raw.iloc[data_start_row:].copy()
    df.columns = main_headers
    df = df.reset_index(drop=True)

    # Identify event columns: columns beyond core student info
    base_cols = [
        "Student Name", "E mail", "Phone Number", "Country",
        "Income", "Batch", "Data Added to the community",
        "Community Status", "Date of Exit", "Conversion Status",
        "Overall Engagement Score", "Payment Date", "Comments"
    ]

    event_cols = [col for col in df.columns if col not in base_cols]

    # Build event metadata safely
    event_meta_records = []
    for col in event_cols:
        idx = list(df.columns).index(col)
        name = event_names.iloc[idx] if idx < len(event_names) else col
        date = event_dates.iloc[idx] if idx < len(event_dates) else None
        event_name, event_date = parse_event_name_and_date(name, date)
        event_meta_records.append({
            "Column": col,
            "Event": event_name,
            "Event Date": event_date
        })

    event_meta_df = pd.DataFrame(event_meta_records)

    return df, event_cols, event_meta_df


# -----------------------------
# Analysis Functions
# -----------------------------

def student_participation_analysis(df, event_cols, event_meta_df):
    """
    Computes:
    1. Student-wise participation count
    2. Event-wise participation count
    3. Detailed participant mapping
    """

    df = df.copy()

    # Ensure event_cols exists in df
    event_cols = [col for col in event_cols if col in df.columns]

    # Normalize Yes/No columns safely (column-wise)
    df.loc[:, event_cols] = df[event_cols].apply(normalize_yes_no, axis=0)

    # Student participation count
    df["Total Events Participated"] = df[event_cols].sum(axis=1)
    student_participation = df[["Student Name", "Total Events Participated"]]

    # Event participation count
    event_participation = (
        df[event_cols]
        .sum()
        .reset_index()
        .rename(columns={"index": "Column", 0: "Participants"})
        .merge(event_meta_df, on="Column", how="left")
    )

    # Participant mapping
    participants = []
    for col in event_cols:
        participating_students = df.loc[df[col] == 1, "Student Name"].tolist()
        participants.append({
            "Column": col,
            "Participants": participating_students
        })

    participants = pd.DataFrame(participants).merge(event_meta_df, on="Column", how="left")

    return student_participation, event_participation, participants


# -----------------------------
# Streamlit App Layout
# -----------------------------

def run_streamlit_app():
    if st is None:
        raise RuntimeError("Streamlit is not installed. Install it with: pip install streamlit")

    st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")
    st.title("🎓 Advanced Student Engagement & Timeline Analytics")

    uploaded_file = st.file_uploader("Upload your Excel file", type=["xlsx"])

    if uploaded_file:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names

        st.subheader("Select Group / Sheet")
        selected_sheet = st.selectbox("Choose a group", sheet_names)

        # Header row configuration
        event_header_row = 0
        date_header_row = 1
        main_header_row = 2
        data_start_row = 3

        df, event_cols, event_meta_df = load_group_sheet(
            uploaded_file,
            selected_sheet,
            event_header_row=event_header_row,
            date_header_row=date_header_row,
            main_header_row=main_header_row,
            data_start_row=data_start_row,
        )

        # -----------------------------
        # Student Participation Analysis
        # -----------------------------
        st.header("📊 Student Participation Analysis")

        student_participation, event_participation, participants = student_participation_analysis(
            df, event_cols, event_meta_df
        )

        total_participants = participants["Student Name"].nunique()
        st.metric("Total Participants", total_participants)

        st.subheader("List of Participating Students")
        st.dataframe(participants[["Student Name", "Phone Number"]].drop_duplicates())

        st.subheader("Student-wise Participation")
        fig1 = px.bar(student_participation, x="Student Name", y="Events Attended")
        st.plotly_chart(fig1, use_container_width=True)

        st.subheader("Event-wise Participation")
        fig2 = px.bar(event_participation, x="Event", y="Participants")
        st.plotly_chart(fig2, use_container_width=True)

        st.subheader("Participation Percentage")
        fig3 = px.pie(event_participation, names="Event", values="Participants")
        st.plotly_chart(fig3, use_container_width=True)

        # -----------------------------
        # Payment & Conversion Analysis
        # -----------------------------
        st.header("💳 Payment & Conversion Analysis")

        conv_col = "Conversion Status"
        paid_students = df[
            df[conv_col]
            .astype(str)
            .str.lower()
            .str.contains("paid|admitted|will pay", na=False)
        ]

        st.subheader("Students Who Paid / Will Pay / Admitted")
        st.dataframe(paid_students[["Student Name", "Phone Number", conv_col, "Payment Date"]])

        paid_participants = participants[participants["Student Name"].isin(paid_students["Student Name"])]

        participation_rate_paid = (
            paid_participants["Student Name"].nunique() / paid_students.shape[0]
            if paid_students.shape[0] > 0 else 0
        )

        conversion_rate = paid_students.shape[0] / df.shape[0]
        retention_rate = (
            df[df["Community Status"].astype(str).str.lower() == "in"].shape[0] / df.shape[0]
        )

        col1, col2, col3 = st.columns(3)
        col1.metric("Participation Rate (Paid)", f"{participation_rate_paid:.2%}")
        col2.metric("Conversion Rate", f"{conversion_rate:.2%}")
        col3.metric("Retention Rate", f"{retention_rate:.2%}")

        # -----------------------------
        # Per-Student Timeline Visualization
        # -----------------------------
        st.header("🕒 Per-Student Timeline Visualization")

        student_list = sorted(df["Student Name"].dropna().unique())
        selected_student = st.selectbox("Select a student", student_list)

        student_events = participants[participants["Student Name"] == selected_student].copy()

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

def _test_normalize_yes_no():
    s = pd.Series(["Yes", "No", "", None, "TRUE", "0", "random"])
    out = normalize_yes_no(s)
    assert out.tolist() == [1, 0, 0, 0, 1, 0, 0]


def _test_parse_event_name_and_date():
    name, date = parse_event_name_and_date("Hackathon", "2026-01-24")
    assert name == "Hackathon"
    assert date == pd.Timestamp("2026-01-24")


if __name__ == "__main__":
    _test_normalize_yes_no()
    _test_parse_event_name_and_date()

    if st is not None:
        run_streamlit_app()
    else:
        print("Streamlit is not installed. Install it with: pip install streamlit")
