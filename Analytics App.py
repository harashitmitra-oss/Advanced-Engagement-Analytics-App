"""
Advanced Engagement Analytics App
---------------------------------
Streamlit app for advanced student engagement, conversion, and timeline analytics.
Designed to work on Streamlit Cloud with uploaded Excel files.
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

def load_group_sheet(file, sheet_name, event_header_row=0, main_header_row=2, data_start_row=3):
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

    # Build event metadata (name + date)
    event_meta = []
    for col in df.columns:
        name, date = parse_event_name_and_date(col)
        if date is not None:
            event_meta.append({"Column": col, "Event": name, "Event Date": date})

    event_meta_df = pd.DataFrame(event_meta)
    event_cols = event_meta_df["Column"].tolist()

    return df, event_cols, event_meta_df



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



def normalize_yes_no(series):
    """
    Safely normalize Yes/No-like values to 1/0 without crashing.
    Handles NaN, blanks, numbers, and unexpected text gracefully.
    """
    return (
        series.fillna(0)
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({
            "yes": 1, "y": 1, "true": 1, "1": 1,
            "no": 0, "n": 0, "false": 0, "0": 0,
            "nan": 0, "none": 0, "": 0
        })
        .apply(lambda x: 1 if str(x) == "1" else 0)
    )



def preprocess_events(df, event_cols, event_meta_df):
    records = []
    df[event_cols] = df[event_cols].apply(normalize_yes_no)

    for _, row in df.iterrows():
        student = row.get("Student Name")
        phone = row.get("Phone Number")
        for _, meta in event_meta_df.iterrows():
            col = meta["Column"]
            if col in df.columns and row.get(col) == 1:
                records.append({
                    "Student Name": student,
                    "Phone Number": phone,
                    "Event": meta["Event"],
                    "Event Date": meta["Event Date"],
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

        conversion_status = str(row.get("Conversion Status", "")).lower()
        conversion_points = 5 if any(k in conversion_status for k in ["paid", "admitted", "will pay"]) else 0

        community_status = str(row.get("Community Status", "")).lower()
        retention_points = 3 if community_status == "in" else 0

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
# Analytics Functions
# -----------------------------

def student_participation_analysis(df, event_cols, event_meta_df):
    df[event_cols] = df[event_cols].apply(normalize_yes_no)

    events_df = preprocess_events(df, event_cols, event_meta_df)

    student_participation = (
        events_df.groupby("Student Name")
        .size()
        .reset_index(name="Participation Count")
        .sort_values(by="Participation Count", ascending=False)
    )

    event_participation = (
        events_df.groupby("Event")
        .size()
        .reset_index(name="Participants")
        .sort_values(by="Participants", ascending=False)
    )

    participants = events_df[["Student Name", "Phone Number"]].drop_duplicates()

    return student_participation, event_participation, participants, events_df



def payment_and_conversion_analysis(df, events_df):
    conversion_col = next((c for c in df.columns if "conversion" in str(c).lower()), None)
    community_col = next((c for c in df.columns if "community" in str(c).lower()), None)

    if conversion_col:
        paid_mask = df[conversion_col].astype(str).str.lower().str.contains("paid|admitted|will pay", na=False)
        paid_students = df[paid_mask]
    else:
        paid_students = pd.DataFrame(columns=df.columns)

    paid_participants = events_df[events_df["Student Name"].isin(paid_students.get("Student Name", []))]

    participation_rate_paid = (
        paid_participants["Student Name"].nunique() / paid_students.shape[0]
        if paid_students.shape[0] > 0 else 0
    )

    conversion_rate = paid_students.shape[0] / df.shape[0] if df.shape[0] > 0 else 0

    if community_col:
        retention_rate = (
            df[df[community_col].astype(str).str.lower() == "in"].shape[0] / df.shape[0]
            if df.shape[0] > 0 else 0
        )
    else:
        retention_rate = 0

    return paid_students, participation_rate_paid, conversion_rate, retention_rate


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
        main_header_row = 2
        data_start_row = 3

        df, event_cols, event_meta_df = load_group_sheet(
            uploaded_file,
            selected_sheet,
            event_header_row=event_header_row,
            main_header_row=main_header_row,
            data_start_row=data_start_row,
        )

        student_participation, event_participation, participants, events_df = student_participation_analysis(
            df, event_cols, event_meta_df
        )

        # -----------------------------
        # Student Participation Analysis
        # -----------------------------
        st.header("📊 Student Participation Analysis")

        total_participants = participants["Student Name"].nunique()
        st.metric("Total Participants", total_participants)

        st.subheader("List of Participating Students")
        st.dataframe(participants)

        st.subheader("Student-wise Participation")
        fig1 = px.bar(student_participation, x="Student Name", y="Participation Count")
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

        paid_students, participation_rate_paid, conversion_rate, retention_rate = payment_and_conversion_analysis(
            df, events_df
        )

        st.subheader("Students Who Paid / Will Pay / Admitted")
        st.dataframe(paid_students)

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

            payment_col = next((c for c in df.columns if "payment" in str(c).lower()), None)
            payment_row = df[df["Student Name"] == selected_student]

            if payment_col and not payment_row.empty and pd.notna(payment_row.iloc[0].get(payment_col)):
                try:
                    payment_date = pd.to_datetime(payment_row.iloc[0].get(payment_col))
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
    event_meta_df = pd.DataFrame({
        "Column": ["Startup Hackathon (12-01-2024)", "AMA (15-01-2024)"],
        "Event": ["Startup Hackathon", "AMA"],
        "Event Date": [datetime(2024, 1, 12), datetime(2024, 1, 15)],
    })
    events = event_meta_df["Column"].tolist()
    events_df = preprocess_events(df, events, event_meta_df)
    assert len(events_df) == 3
    assert set(events_df["Student Name"]) == {"A", "B"}


def _test_normalize_yes_no():
    s = pd.Series(["Yes", "No", "", None, "TRUE", "0", "random"])
    normalized = normalize_yes_no(s)
    assert normalized.tolist() == [1, 0, 0, 0, 1, 0, 0]


if __name__ == "__main__":
    _test_parse_event_name_and_date()
    _test_extract_event_columns()
    _test_preprocess_events()
    _test_normalize_yes_no()

    if st is not None:
        run_streamlit_app()
    else:
        print("Streamlit is not installed. Install it with: pip install streamlit")
