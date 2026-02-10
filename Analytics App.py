import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# =====================
# CONFIG
# =====================
st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")

EVENT_HEADER_ROW = 0
EVENT_DATE_ROW = 1
MAIN_HEADER_ROW = 2
DATA_START_ROW = 3

# =====================
# DATA LOADING
# =====================
def load_group_sheet(uploaded_file, sheet_name):
    raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)

    event_names = raw.iloc[EVENT_HEADER_ROW]
    event_dates = raw.iloc[EVENT_DATE_ROW]
    main_headers = raw.iloc[MAIN_HEADER_ROW]

    df = raw.iloc[DATA_START_ROW:].copy()
    df.columns = main_headers
    df = df.reset_index(drop=True)

    event_cols = []
    event_meta = []

    for col in df.columns:
        if col not in ["Student Name", "Phone Number", "Conversion Status", "Community Status", "Payment Date"]:
            event_name = event_names[df.columns.get_loc(col)]
            event_date = event_dates[df.columns.get_loc(col)]
            event_cols.append(col)
            event_meta.append({
                "column": col,
                "event_name": str(event_name),
                "event_date": pd.to_datetime(event_date, errors="coerce")
            })

    event_meta_df = pd.DataFrame(event_meta)

    return df, event_cols, event_meta_df

# =====================
# HELPERS
# =====================
def normalize_yes_no(series):
    return (
        series.fillna(0)
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({"yes": 1, "y": 1, "true": 1, "1": 1})
        .replace({"no": 0, "n": 0, "false": 0, "0": 0, "nan": 0, "": 0})
        .astype(int)
    )


def get_safe_column(df, possible_names):
    for name in possible_names:
        if name in df.columns:
            return name
    return None


def categorize_event(name):
    name = str(name).lower()
    if "hackathon" in name:
        return "Startup Hackathon"
    elif "ama" in name:
        return "AMA"
    elif "masterclass" in name or "master class" in name:
        return "Masterclass"
    else:
        return "Other"

# =====================
# CORE ANALYTICS
# =====================
def student_participation_analysis(df, event_cols, event_meta_df):
    df[event_cols] = df[event_cols].apply(normalize_yes_no)

    student_participation = df[event_cols].sum(axis=1)
    event_participation = df[event_cols].sum()

    participants = df[df[event_cols].sum(axis=1) > 0]

    return student_participation, event_participation, participants


def payment_conversion_analysis(df, event_cols):
    conversion_col = get_safe_column(df, ["Conversion Status", "Conversion", "Status"])
    community_col = get_safe_column(df, ["Community Status", "Community", "Retention Status"])
    payment_date_col = get_safe_column(df, ["Payment Date", "Paid Date", "Date of Payment"])

    if conversion_col:
        conversion_series = df[conversion_col].astype(str).str.lower()
        paid_mask = conversion_series.str.contains("paid|admitted|will pay", regex=True, na=False)
    else:
        paid_mask = pd.Series([False] * len(df))

    paid_students = df[paid_mask]

    if community_col:
        retention_rate = (df[community_col].astype(str).str.lower() == "in").mean() * 100
    else:
        retention_rate = 0

    participation_rate_paid = paid_students[event_cols].sum(axis=1).gt(0).mean() * 100 if not paid_students.empty else 0
    conversion_rate = paid_mask.mean() * 100

    return paid_students, participation_rate_paid, conversion_rate, retention_rate


def event_category_analysis(df, event_cols, event_meta_df):
    event_meta_df["category"] = event_meta_df["event_name"].apply(categorize_event)

    category_results = {}

    for category in event_meta_df["category"].unique():
        cols = event_meta_df[event_meta_df["category"] == category]["column"].tolist()
        if cols:
            participants = df[df[cols].sum(axis=1) > 0]
            rate = participants.shape[0] / df.shape[0] * 100
        else:
            participants = pd.DataFrame()
            rate = 0
        category_results[category] = {
            "participants": participants,
            "rate": rate,
            "columns": cols
        }

    return category_results


def lead_scoring(df, event_cols, event_meta_df):
    df[event_cols] = df[event_cols].apply(normalize_yes_no)

    conversion_col = get_safe_column(df, ["Conversion Status", "Conversion", "Status"])
    community_col = get_safe_column(df, ["Community Status", "Community", "Retention Status"])

    event_meta_df["category"] = event_meta_df["event_name"].apply(categorize_event)

    df["lead_score"] = df[event_cols].sum(axis=1)

    if conversion_col:
        df["lead_score"] += df[conversion_col].astype(str).str.lower().str.contains("paid|admitted|will pay", regex=True, na=False) * 5

    if community_col:
        df["lead_score"] += (df[community_col].astype(str).str.lower() == "in") * 3

    return df

# =====================
# TIMELINE VISUALIZATION
# =====================
def student_timeline(df, event_cols, event_meta_df, student_name):
    student_row = df[df["Student Name"] == student_name]

    if student_row.empty:
        return None

    student_row = student_row.iloc[0]

    timeline_events = []

    for _, row in event_meta_df.iterrows():
        col = row["column"]
        if col in df.columns and student_row[col] == 1:
            timeline_events.append({
                "date": row["event_date"],
                "event": row["event_name"]
            })

    timeline_df = pd.DataFrame(timeline_events)

    fig = px.scatter(
        timeline_df,
        x="date",
        y=[1] * len(timeline_df),
        text="event",
        title=f"Engagement Timeline — {student_name}"
    )

    fig.update_traces(textposition="top center", marker=dict(size=12))
    fig.update_yaxes(visible=False)

    payment_date_col = get_safe_column(df, ["Payment Date", "Paid Date", "Date of Payment"])

    if payment_date_col and pd.notna(student_row[payment_date_col]):
        try:
            pay_date = pd.to_datetime(student_row[payment_date_col], errors="coerce")
            if not pd.isna(pay_date):
                fig.add_trace(go.Scatter(
                    x=[pay_date],
                    y=[1],
                    mode="markers+text",
                    marker=dict(symbol="check", size=16, color="green"),
                    text=["Paid ✔"],
                    textposition="bottom center",
                    name="Payment"
                ))
        except:
            pass

    return fig

# =====================
# STREAMLIT APP
# =====================
def run_streamlit_app():
    st.title("📊 Advanced Engagement Analytics & Timelines")

    uploaded_file = st.file_uploader("Upload your Master Engagement Tracker Excel file", type=["xlsx"])

    if not uploaded_file:
        st.info("Please upload your Excel file to continue.")
        return

    xl = pd.ExcelFile(uploaded_file)
    sheet_names = xl.sheet_names

    group_tabs = st.tabs(sheet_names)

    for i, sheet in enumerate(sheet_names):
        with group_tabs[i]:
            st.subheader(f"📁 Group: {sheet}")

            df, event_cols, event_meta_df = load_group_sheet(uploaded_file, sheet)

            # =====================
            # STUDENT PARTICIPATION
            # =====================
            st.markdown("## 🎯 Student Participation Analysis")

            student_participation, event_participation, participants = student_participation_analysis(df, event_cols, event_meta_df)

            col1, col2, col3 = st.columns(3)
            col1.metric("Total Participants", participants.shape[0])
            col2.metric("Total Students", df.shape[0])
            col3.metric("Participation Rate (%)", round(participants.shape[0] / df.shape[0] * 100, 2))

            st.dataframe(participants[["Student Name", "Phone Number"] + event_cols])

            fig_student = px.bar(
                x=df["Student Name"],
                y=student_participation,
                labels={"x": "Student", "y": "Events Participated"},
                title="Student-wise Participation"
            )
            st.plotly_chart(fig_student, use_container_width=True)

            fig_event = px.bar(
                x=event_participation.index,
                y=event_participation.values,
                labels={"x": "Event", "y": "Participants"},
                title="Event-wise Participation"
            )
            st.plotly_chart(fig_event, use_container_width=True)

            fig_pie = px.pie(
                names=["Participated", "Did Not Participate"],
                values=[participants.shape[0], df.shape[0] - participants.shape[0]],
                title="Participation Percentage"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

            # =====================
            # PAYMENT & CONVERSION
            # =====================
            st.markdown("## 💰 Payment & Conversion Analysis")

            paid_students, participation_rate_paid, conversion_rate, retention_rate = payment_conversion_analysis(df, event_cols)

            col1, col2, col3 = st.columns(3)
            col1.metric("Paid / Admitted Students", paid_students.shape[0])
            col2.metric("Participation Rate of Paid (%)", round(participation_rate_paid, 2))
            col3.metric("Conversion Rate (%)", round(conversion_rate, 2))

            st.metric("Retention Rate (%)", round(retention_rate, 2))

            if not paid_students.empty:
                st.dataframe(paid_students[["Student Name", "Phone Number"]])

            st.info("🏆 Winners-who-paid logic ready (will activate when winner data is added).")

            # =====================
            # EVENT CATEGORY ANALYSIS
            # =====================
            st.markdown("## 🗂️ Event Category Analysis")

            category_results = event_category_analysis(df, event_cols, event_meta_df)

            for category, result in category_results.items():
                st.subheader(category)
                st.metric("Participation Rate (%)", round(result["rate"], 2))
                if not result["participants"].empty:
                    st.dataframe(result["participants"][["Student Name", "Phone Number"]])

            # =====================
            # LEAD SCORING
            # =====================
            st.markdown("## 🧠 Lead Scoring System")

            scored_df = lead_scoring(df.copy(), event_cols, event_meta_df)

            leaderboard = scored_df.sort_values(by="lead_score", ascending=False)

            st.subheader("🏅 Top Students by Lead Score")
            st.dataframe(leaderboard[["Student Name", "Phone Number", "lead_score"]].head(20))

            fig_lead_dist = px.histogram(
                leaderboard,
                x="lead_score",
                nbins=20,
                title="Lead Score Distribution"
            )
            st.plotly_chart(fig_lead_dist, use_container_width=True)

            # =====================
            # STUDENT TIMELINE
            # =====================
            st.markdown("## 🕒 Per-Student Engagement Timeline")

            student_list = df["Student Name"].dropna().unique().tolist()
            selected_student = st.selectbox("Select a student", student_list)

            timeline_fig = student_timeline(df, event_cols, event_meta_df, selected_student)

            if timeline_fig:
                st.plotly_chart(timeline_fig, use_container_width=True)


if __name__ == "__main__":
    run_streamlit_app()
