# === Advanced Engagement Analytics App (Robust, Production-Ready) ===

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Engagement Analytics", layout="wide")

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
            "nan": 0, "": 0
        })
        .apply(lambda x: 1 if str(x).isdigit() and int(x) > 0 else int(x) if str(x).isdigit() else 0)
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
    Expected structure:
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

    # Make columns unique to avoid pandas returning DataFrame instead of Series
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

    # Normalize events
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


# -------------------------------------------------------------------
# ----------------------- STREAMLIT APP ------------------------------
# -------------------------------------------------------------------

def run_streamlit_app():
    st.title("📊 Advanced Engagement Analytics")

    uploaded_file = st.file_uploader("Upload your Master Engagement Tracker Excel file", type=["xlsx"])

    if not uploaded_file:
        st.info("Please upload your Excel file to continue.")
        return

    xls = pd.ExcelFile(uploaded_file)
    sheet_names = xls.sheet_names

    selected_sheet = st.sidebar.selectbox("Select Group / Sheet", sheet_names)

    df, event_cols, event_meta_df = load_group_sheet(uploaded_file, selected_sheet)

    st.subheader("Raw Data Preview")
    st.dataframe(df.head())

    # ------------------- SAFE COLUMN DETECTION -------------------
    conversion_col = find_column(df, ["conversion status", "conversion"]) 
    community_col = find_column(df, ["community status", "community"]) 
    payment_date_col = find_column(df, ["payment date", "payment"]) 

    # ------------------- PAYMENT & CONVERSION -------------------
    st.header("💰 Payment & Conversion Analysis")

    if conversion_col:
        conv_series = df[conversion_col]
        if isinstance(conv_series, pd.DataFrame):
            conv_series = conv_series.iloc[:, 0]

        conv_series = conv_series.astype(str).str.lower()
        paid_mask = conv_series.str.contains("paid|admitted|will pay", na=False)
        paid_students = df.loc[paid_mask]

        st.subheader("Students Who Paid / High Intent")
        st.dataframe(paid_students[["Student Name", conversion_col]])

        total_students = len(df)
        total_paid = paid_mask.sum()
        conversion_rate = round((total_paid / total_students) * 100, 2) if total_students else 0

        st.metric("Total Students", total_students)
        st.metric("Paid / High Intent", total_paid)
        st.metric("Conversion Rate (%)", conversion_rate)
    else:
        st.warning("⚠️ Conversion Status column not found.")

    if community_col:
        community_series = df[community_col]
        if isinstance(community_series, pd.DataFrame):
            community_series = community_series.iloc[:, 0]

        retained_mask = community_series.astype(str).str.lower().str.contains("in|retained", na=False)
        retention_rate = round((retained_mask.sum() / len(df)) * 100, 2) if len(df) else 0
        st.metric("Retention Rate (%)", retention_rate)
    else:
        st.warning("⚠️ Community Status column not found.")

    # ------------------- PARTICIPATION ANALYSIS -------------------
    st.header("📈 Participation Analysis")

    student_participation, event_participation, participants = student_participation_analysis(
        df, event_cols, event_meta_df
    )

    st.subheader("Student-wise Participation")
    st.dataframe(student_participation.sort_values("Total Events Participated", ascending=False))

    fig1 = px.bar(student_participation, x="Student Name", y="Total Events Participated",
                  title="Student-wise Participation Count")
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("Event-wise Participation")
    st.dataframe(event_participation.sort_values("Participants", ascending=False))

    fig2 = px.bar(event_participation, x="Event Name", y="Participants",
                  title="Event-wise Participation Count")
    st.plotly_chart(fig2, use_container_width=True)

    total_participants = (student_participation["Total Events Participated"] > 0).sum()
    non_participants = len(df) - total_participants

    fig3 = px.pie(
        names=["Participated", "Did Not Participate"],
        values=[total_participants, non_participants],
        title="Participation Percentage"
    )
    st.plotly_chart(fig3, use_container_width=True)

    # ------------------- EVENT CATEGORY ANALYSIS -------------------
    st.header("🗂 Event Category Analysis")

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

    event_meta_df["Category"] = event_meta_df["Event Name"].apply(categorize_event)

    for category in event_meta_df["Category"].unique():
        st.subheader(f"{category}")
        cat_events = event_meta_df[event_meta_df["Category"] == category]["Column"].tolist()

        cat_participants = df[cat_events].sum().sum() if cat_events else 0
        cat_students = df.loc[df[cat_events].sum(axis=1) > 0, "Student Name"].tolist() if cat_events else []

        st.metric("Total Participations", cat_participants)
        st.write("Students:")
        st.write(cat_students)

    # ------------------- LEAD SCORING SYSTEM -------------------
    st.header("🏆 Lead Scoring System")

    df_scoring = df.copy()

    for col in event_cols:
        if col in df_scoring.columns:
            df_scoring[col] = normalize_yes_no(df_scoring[col])

    df_scoring["Event Points"] = df_scoring[event_cols].sum(axis=1)

    df_scoring["Category Points"] = 0
    for _, row in event_meta_df.iterrows():
        col = row["Column"]
        category = row["Category"]
        if col in df_scoring.columns:
            if category == "Startup Hackathon":
                df_scoring["Category Points"] += df_scoring[col] * 3
            elif category == "AMA":
                df_scoring["Category Points"] += df_scoring[col] * 2
            elif category == "Masterclass":
                df_scoring["Category Points"] += df_scoring[col] * 2
            else:
                df_scoring["Category Points"] += df_scoring[col] * 1

    if conversion_col:
        conv_series = df_scoring[conversion_col]
        if isinstance(conv_series, pd.DataFrame):
            conv_series = conv_series.iloc[:, 0]

        conv_series = conv_series.astype(str).str.lower()
        df_scoring["Conversion Points"] = np.where(
            conv_series.str.contains("paid|admitted", na=False), 10,
            np.where(conv_series.str.contains("will pay", na=False), 5, 0)
        )
    else:
        df_scoring["Conversion Points"] = 0

    if community_col:
        comm_series = df_scoring[community_col]
        if isinstance(comm_series, pd.DataFrame):
            comm_series = comm_series.iloc[:, 0]

        comm_series = comm_series.astype(str).str.lower()
        df_scoring["Retention Points"] = np.where(comm_series.str.contains("in|retained", na=False), 5, 0)
    else:
        df_scoring["Retention Points"] = 0

    df_scoring["Lead Score"] = (
        df_scoring["Event Points"] +
        df_scoring["Category Points"] +
        df_scoring["Conversion Points"] +
        df_scoring["Retention Points"]
    )

    leaderboard = df_scoring[["Student Name", "Lead Score"]].sort_values("Lead Score", ascending=False)

    st.subheader("Top Leads")
    st.dataframe(leaderboard.head(20))

    fig4 = px.histogram(df_scoring, x="Lead Score", title="Lead Score Distribution")
    st.plotly_chart(fig4, use_container_width=True)

    # ------------------- STUDENT TIMELINE -------------------
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
                try:
                    event_date_parsed = pd.to_datetime(event_date, errors="coerce")
                except:
                    event_date_parsed = None

                timeline_data.append({
                    "Date": event_date_parsed,
                    "Event": event_name,
                    "Type": "Event"
                })

    if payment_date_col:
        payment_val = student_row[payment_date_col]
        try:
            payment_date = pd.to_datetime(payment_val, errors="coerce")
        except:
            payment_date = None

        if pd.notna(payment_date):
            timeline_data.append({
                "Date": payment_date,
                "Event": "Payment ✔",
                "Type": "Payment"
            })

    timeline_df = pd.DataFrame(timeline_data)
    timeline_df = timeline_df.dropna(subset=["Date"])

    if not timeline_df.empty:
        fig5 = px.scatter(
            timeline_df,
            x="Date",
            y=[1]*len(timeline_df),
            color="Type",
            text="Event",
            title=f"Timeline for {selected_student}"
        )
        fig5.update_traces(textposition="top center")
        fig5.update_yaxes(visible=False)
        st.plotly_chart(fig5, use_container_width=True)
    else:
        st.info("No timeline data available for this student.")


if __name__ == "__main__":
    run_streamlit_app()
