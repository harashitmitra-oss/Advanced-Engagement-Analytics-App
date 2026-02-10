# Advanced Engagement Analytics Streamlit App
# Compatible with existing Streamlit deployments

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
from datetime import datetime

# --------------------------- CONFIG ---------------------------
FILE_PATH = "Master_Engagement_Tracker.xlsx"
DEFAULT_SHEET = "PG engagement tracker B2"

# Header layout (0-based indices)
EVENT_HEADER_ROW = 0   # event names
EVENT_DATE_ROW = 1     # event dates
MAIN_HEADER_ROW = 2    # main column headers
DATA_START_ROW = 3     # student data starts

# --------------------------- UTILS ---------------------------

def normalize_binary(val):
    if pd.isna(val):
        return 0
    val = str(val).strip().lower()
    return 1 if val in ["yes", "y", "true", "1"] else 0


def parse_date_safe(x):
    try:
        return pd.to_datetime(x, dayfirst=True)
    except Exception:
        return pd.NaT

# --------------------------- DATA LOADER ---------------------------

def load_group_sheet(file_path, sheet_name):
    raw = pd.read_excel(file_path, sheet_name=sheet_name, header=None)

    # Extract headers
    event_names = raw.iloc[EVENT_HEADER_ROW]
    event_dates = raw.iloc[EVENT_DATE_ROW]
    main_headers = raw.iloc[MAIN_HEADER_ROW]

    # Build final headers
    final_headers = []
    for i, h in enumerate(main_headers):
        if pd.notna(h):
            final_headers.append(str(h).strip())
        elif pd.notna(event_names.iloc[i]):
            final_headers.append(str(event_names.iloc[i]).strip())
        else:
            final_headers.append(f"Unnamed_{i}")

    df = raw.iloc[DATA_START_ROW:].copy()
    df.columns = final_headers

    # Identify event columns
    event_cols = [col for col in df.columns if col not in [
        "Student Name", "E mail", "Phone Number", "Country", "Income",
        "Batch", "Data Added to the community", "Community Status",
        "Date of Exit", "Conversion Status", "Overall Engagement Score",
        "Payment Date", "Comments"
    ]]

    # Normalize event participation
    for col in event_cols:
        df[col] = df[col].apply(normalize_binary)

    # Build event metadata
    event_meta = []
    for col in event_cols:
        col_idx = list(df.columns).index(col)
        date_raw = event_dates.iloc[col_idx]
        event_meta.append({
            "event_name": col,
            "event_date": parse_date_safe(date_raw),
            "category": categorize_event(col)
        })

    event_meta_df = pd.DataFrame(event_meta)

    # Parse payment date
    if "Payment Date" in df.columns:
        df["Payment Date"] = df["Payment Date"].apply(parse_date_safe)

    return df, event_cols, event_meta_df

# --------------------------- EVENT CATEGORIZATION ---------------------------

def categorize_event(name):
    name_lower = name.lower()
    if "hackathon" in name_lower:
        return "Startup Hackathon"
    elif "ama" in name_lower:
        return "AMA"
    elif "masterclass" in name_lower:
        return "Masterclass"
    else:
        return "Other"

# --------------------------- ANALYTICS FUNCTIONS ---------------------------

def get_participation_summary(df, event_cols):
    participation_counts = df[event_cols].sum()
    total_participants = (df[event_cols].sum(axis=1) > 0).sum()
    participating_students = df[df[event_cols].sum(axis=1) > 0]["Student Name"].tolist()

    student_wise = df[["Student Name"] + event_cols].set_index("Student Name").sum(axis=1)
    event_wise = participation_counts

    return total_participants, participating_students, student_wise, event_wise


def get_payment_conversion_stats(df, event_cols):
    paid_students = df[df["Payment Date"].notna()]["Student Name"].tolist()
    total_students = len(df)
    paid_count = len(paid_students)

    paid_participation_rate = (
        df[df["Payment Date"].notna()][event_cols].sum(axis=1).gt(0).mean() * 100
        if paid_count > 0 else 0
    )

    conversion_rate = paid_count / total_students * 100 if total_students > 0 else 0

    retention_rate = (
        (df["Community Status"].str.lower() == "in").mean() * 100
        if "Community Status" in df.columns else 0
    )

    return paid_students, paid_participation_rate, conversion_rate, retention_rate


def get_category_analysis(df, event_cols, event_meta_df):
    results = {}
    for category in event_meta_df["category"].unique():
        cols = event_meta_df[event_meta_df["category"] == category]["event_name"].tolist()
        if not cols:
            continue
        students = df[df[cols].sum(axis=1) > 0]["Student Name"].tolist()
        rate = (df[cols].sum(axis=1) > 0).mean() * 100
        results[category] = {"students": students, "rate": rate}
    return results


def compute_lead_scores(df, event_cols, event_meta_df,
                        event_weight=1,
                        hackathon_weight=3,
                        ama_weight=2,
                        masterclass_weight=2,
                        paid_weight=5,
                        retained_weight=2):

    scores = []
    for _, row in df.iterrows():
        score = 0

        # Base event participation
        score += row[event_cols].sum() * event_weight

        # Category bonuses
        for category, weight in {
            "Startup Hackathon": hackathon_weight,
            "AMA": ama_weight,
            "Masterclass": masterclass_weight
        }.items():
            cat_events = event_meta_df[event_meta_df["category"] == category]["event_name"].tolist()
            if row[cat_events].sum() > 0:
                score += weight

        # Paid bonus
        if pd.notna(row.get("Payment Date")):
            score += paid_weight

        # Retention bonus
        if str(row.get("Community Status", "")).lower() == "in":
            score += retained_weight

        scores.append(score)

    df["Lead Score"] = scores
    return df

# --------------------------- TIMELINE BUILDER ---------------------------

def build_student_timeline(df, event_cols, event_meta_df, student_name):
    student_row = df[df["Student Name"] == student_name].iloc[0]

    timeline_events = []
    for col in event_cols:
        if student_row[col] == 1:
            meta = event_meta_df[event_meta_df["event_name"] == col].iloc[0]
            if pd.notna(meta["event_date"]):
                timeline_events.append({
                    "date": meta["event_date"],
                    "event": col,
                    "category": meta["category"]
                })

    # Payment event
    if pd.notna(student_row.get("Payment Date")):
        timeline_events.append({
            "date": student_row["Payment Date"],
            "event": "Payment",
            "category": "Payment"
        })

    timeline_df = pd.DataFrame(timeline_events).sort_values("date")
    return timeline_df

# --------------------------- STREAMLIT UI ---------------------------

def run_streamlit_app():
    st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")
    st.title("📊 Advanced Student Engagement & Timeline Analytics")

    # Placeholder for multiple groups
    group_tabs = st.tabs([
        "PG engagement tracker B2",
        "Group 2 (Coming Soon)",
        "Group 3 (Coming Soon)",
        "Group 4 (Coming Soon)",
        "Group 5 (Coming Soon)",
        "Group 6 (Coming Soon)",
    ])

    with group_tabs[0]:
        df, event_cols, event_meta_df = load_group_sheet(FILE_PATH, DEFAULT_SHEET)

        # ---------------- Student Participation Analysis ----------------
        st.header("🎯 Student Participation Analysis")

        total_participants, participating_students, student_wise, event_wise = get_participation_summary(df, event_cols)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Participants", total_participants)
            st.write("Participating Students:")
            st.dataframe(pd.DataFrame({"Student Name": participating_students}))

        with col2:
            fig1 = px.bar(student_wise.sort_values(ascending=False).reset_index(),
                          x="Student Name", y=0,
                          title="Student-wise Participation Count")
            fig1.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig1, use_container_width=True)

        fig2 = px.bar(event_wise.sort_values(ascending=False).reset_index(),
                      x="index", y=0,
                      title="Event-wise Participation Count")
        fig2.update_layout(xaxis_title="Event", yaxis_title="Participants", xaxis_tickangle=-45)
        st.plotly_chart(fig2, use_container_width=True)

        participation_percentage = total_participants / len(df) * 100 if len(df) > 0 else 0
        fig3 = px.pie(values=[participation_percentage, 100 - participation_percentage],
                      names=["Participated", "Did Not Participate"],
                      title="Participation Percentage")
        st.plotly_chart(fig3, use_container_width=True)

        # ---------------- Payment & Conversion Analysis ----------------
        st.header("💰 Payment & Conversion Analysis")

        paid_students, paid_participation_rate, conversion_rate, retention_rate = get_payment_conversion_stats(df, event_cols)

        col3, col4, col5 = st.columns(3)
        col3.metric("Paid Students", len(paid_students))
        col4.metric("Paid Participation Rate", f"{paid_participation_rate:.1f}%")
        col5.metric("Conversion Rate", f"{conversion_rate:.1f}%")

        st.metric("Retention Rate", f"{retention_rate:.1f}%")

        st.write("List of Paid Students:")
        st.dataframe(pd.DataFrame({"Student Name": paid_students}))

        st.info("🏆 Winners who paid logic is future-ready and can be added once winner data is available.")

        # ---------------- Event Category Analysis ----------------
        st.header("🧩 Event Category Analysis")

        category_results = get_category_analysis(df, event_cols, event_meta_df)

        for category, data in category_results.items():
            st.subheader(category)
            st.write(f"Participation Rate: {data['rate']:.1f}%")
            st.dataframe(pd.DataFrame({"Student Name": data["students"]}))

        # ---------------- Lead Scoring System ----------------
        st.header("📈 Lead Scoring System")

        df = compute_lead_scores(df, event_cols, event_meta_df)

        leaderboard = df[["Student Name", "Lead Score"]].sort_values(by="Lead Score", ascending=False)
        st.subheader("🏆 Top Students by Lead Score")
        st.dataframe(leaderboard.head(20))

        fig4 = px.histogram(df, x="Lead Score", nbins=20, title="Lead Score Distribution")
        st.plotly_chart(fig4, use_container_width=True)

        # ---------------- Per-Student Timeline Visualization ----------------
        st.header("🕒 Per-Student Timeline Visualization")

        student_names = sorted(df["Student Name"].dropna().unique())
        selected_student = st.selectbox("Select a student", student_names)

        timeline_df = build_student_timeline(df, event_cols, event_meta_df, selected_student)

        if not timeline_df.empty:
            fig5 = px.scatter(timeline_df,
                              x="date",
                              y=[1] * len(timeline_df),
                              text="event",
                              color="category",
                              title=f"Engagement Timeline for {selected_student}")
            fig5.update_traces(marker=dict(size=12), textposition="top center")
            fig5.update_yaxes(visible=False)
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.warning("No events found for this student.")


# --------------------------- ENTRY POINT ---------------------------
if __name__ == "__main__":
    run_streamlit_app()
