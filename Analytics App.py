import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------------
# Utility Functions
# ---------------------------------

def make_columns_unique(df):
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique():
        dup_idx = cols[cols == dup].index.tolist()
        for i, idx in enumerate(dup_idx):
            if i == 0:
                continue
            cols[idx] = f"{dup}_{i}"
    df.columns = cols
    return df


def normalize_yes_no(series):
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


def find_column(df, keywords):
    for col in df.columns:
        for kw in keywords:
            if kw in col.lower():
                return col
    return None


# ---------------------------------
# Streamlit App
# ---------------------------------

def run_streamlit_app():
    st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")
    st.title("📊 Advanced Engagement Analytics Dashboard")

    uploaded_file = st.file_uploader("Upload Engagement Excel File", type=["xlsx"])

    if uploaded_file is None:
        st.info("Please upload your Excel file to continue.")
        return

    # Load file
    df = pd.read_excel(uploaded_file, sheet_name=0)
    df = make_columns_unique(df)

    st.success("File uploaded successfully!")

    # Preview
    with st.expander("🔍 Preview Raw Data"):
        st.dataframe(df.head(20))

    # ---------------------------------
    # Column Detection
    # ---------------------------------

    name_col = find_column(df, ["name"])
    lead_score_col = find_column(df, ["lead score", "score", "engagement score"])
    conversion_col = find_column(df, ["conversion", "status", "admitted", "paid"])
    batch_col = find_column(df, ["batch"])
    country_col = find_column(df, ["country"])

    if not name_col:
        st.error("❌ No student name column detected.")
        return

    df = df.rename(columns={name_col: "Student Name"})

    # ---------------------------------
    # Event Columns Detection
    # ---------------------------------

    exclude_keywords = [
        "name", "email", "mobile", "country", "income", "batch",
        "status", "exit", "engagement", "conversion", "lead", "score", "added"
    ]

    event_cols = [
        col for col in df.columns
        if not any(k in col.lower() for k in exclude_keywords)
    ]

    if not event_cols:
        st.error("❌ No event/participation columns detected.")
        return

    # Normalize event participation
    df[event_cols] = df[event_cols].apply(normalize_yes_no)

    # Total participation score
    df["Total Participation"] = df[event_cols].sum(axis=1)

    # ---------------------------------
    # Lead Score + Conversion Handling
    # ---------------------------------

    if lead_score_col:
        df["Lead Score"] = pd.to_numeric(df[lead_score_col], errors="coerce").fillna(0).astype(int)
    else:
        df["Lead Score"] = 0

    if conversion_col:
        df["Conversion Status"] = df[conversion_col].astype(str)
    else:
        df["Conversion Status"] = "Unknown"

    paid_mask = df["Conversion Status"].str.lower().str.contains("paid|admitted|will pay", na=False)
    df["Converted"] = paid_mask

    # ---------------------------------
    # KPI SECTION
    # ---------------------------------

    st.subheader("📌 Key Performance Indicators")

    total_students = len(df)
    active_students = (df["Total Participation"] > 0).sum()
    converted_students = df["Converted"].sum()
    avg_participation = round(df["Total Participation"].mean(), 2)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Students", total_students)
    col2.metric("Active Students", active_students)
    col3.metric("Converted / Will Pay", converted_students)
    col4.metric("Avg Participation Score", avg_participation)

    # ---------------------------------
    # 🔥 SECTION 1 — Top → Bottom Participating Students
    # ---------------------------------

    st.subheader("🏆 Student Participation Leaderboard")

    leaderboard_cols = ["Student Name", "Total Participation", "Lead Score", "Conversion Status"]
    leaderboard_df = df[leaderboard_cols].sort_values(by="Total Participation", ascending=False)

    st.dataframe(leaderboard_df, use_container_width=True)

    # ---------------------------------
    # 📊 SECTION 2 — Event Participation Summary
    # ---------------------------------

    st.subheader("📅 Event Participation Summary")

    event_participation = (
        df[event_cols]
        .sum()
        .reset_index()
        .rename(columns={"index": "Event", 0: "Participants"})
        .sort_values(by="Participants", ascending=False)
    )

    st.dataframe(event_participation, use_container_width=True)

    # Bar Chart
    fig1, ax1 = plt.subplots()
    ax1.bar(event_participation["Event"], event_participation["Participants"])
    ax1.set_title("Event-wise Participation Count")
    ax1.set_xlabel("Event")
    ax1.set_ylabel("Participants")
    plt.xticks(rotation=45, ha="right")
    st.pyplot(fig1)

    # ---------------------------------
    # 📈 SECTION 3 — Participation Distribution
    # ---------------------------------

    st.subheader("📈 Participation Distribution")

    fig2, ax2 = plt.subplots()
    ax2.hist(df["Total Participation"], bins=10)
    ax2.set_title("Distribution of Student Participation Scores")
    ax2.set_xlabel("Participation Score")
    ax2.set_ylabel("Number of Students")
    st.pyplot(fig2)

    # ---------------------------------
    # 🎯 SECTION 4 — Conversion Analysis
    # ---------------------------------

    st.subheader("🎯 Conversion Analysis")

    conversion_summary = (
        df.groupby("Converted")["Student Name"]
        .count()
        .reset_index()
        .replace({True: "Converted / Will Pay", False: "Not Converted"})
        .rename(columns={"Student Name": "Students"})
    )

    st.dataframe(conversion_summary, use_container_width=True)

    fig3, ax3 = plt.subplots()
    ax3.bar(conversion_summary["Converted"], conversion_summary["Students"])
    ax3.set_title("Conversion Status Distribution")
    ax3.set_xlabel("Status")
    ax3.set_ylabel("Students")
    st.pyplot(fig3)

    # ---------------------------------
    # 🧠 SECTION 5 — Participation vs Conversion
    # ---------------------------------

    st.subheader("🧠 Participation vs Conversion Insight")

    conversion_by_participation = (
        df.groupby("Total Participation")["Converted"]
        .mean()
        .reset_index()
        .rename(columns={"Converted": "Conversion Rate"})
    )

    fig4, ax4 = plt.subplots()
    ax4.plot(conversion_by_participation["Total Participation"],
             conversion_by_participation["Conversion Rate"], marker="o")
    ax4.set_title("Conversion Rate vs Participation Score")
    ax4.set_xlabel("Participation Score")
    ax4.set_ylabel("Conversion Rate")
    st.pyplot(fig4)

    # ---------------------------------
    # 🌍 SECTION 6 — Country-wise Engagement (if available)
    # ---------------------------------

    if country_col:
        st.subheader("🌍 Country-wise Engagement")

        country_engagement = (
            df.groupby(country_col)["Total Participation"]
            .mean()
            .reset_index()
            .rename(columns={country_col: "Country", "Total Participation": "Avg Participation"})
            .sort_values(by="Avg Participation", ascending=False)
        )

        st.dataframe(country_engagement, use_container_width=True)

        fig5, ax5 = plt.subplots()
        ax5.bar(country_engagement["Country"], country_engagement["Avg Participation"])
        ax5.set_title("Average Participation by Country")
        ax5.set_xlabel("Country")
        ax5.set_ylabel("Avg Participation")
        plt.xticks(rotation=45, ha="right")
        st.pyplot(fig5)

    # ---------------------------------
    # 📦 SECTION 7 — Downloads
    # ---------------------------------

    st.subheader("⬇️ Download Reports")

    st.download_button(
        "Download Student Leaderboard",
        leaderboard_df.to_csv(index=False),
        file_name="student_participation_leaderboard.csv",
        mime="text/csv"
    )

    st.download_button(
        "Download Event Participation Report",
        event_participation.to_csv(index=False),
        file_name="event_participation_report.csv",
        mime="text/csv"
    )

    st.download_button(
        "Download Full Processed Dataset",
        df.to_csv(index=False),
        file_name="processed_engagement_dataset.csv",
        mime="text/csv"
    )


if __name__ == "__main__":
    run_streamlit_app()
