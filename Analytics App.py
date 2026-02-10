# === Advanced Engagement Analytics App (PG Sheets Stable, Error-Free) ===

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="Engagement Analytics", layout="wide")

# -------------------------------------------------------------------
# -------------------------- UTILITIES -------------------------------
# -------------------------------------------------------------------

def normalize_yes_no(series):
    return (
        series.fillna(0)
        .astype(str)
        .str.strip()
        .str.lower()
        .replace({
            "yes": 1, "y": 1, "true": 1, "1": 1,
            "no": 0, "n": 0, "false": 0, "0": 0,
            "nan": 0, "": 0
        })
        .apply(lambda x: 1 if str(x).isdigit() and int(x) > 0 else 0)
    )

def make_columns_unique(cols):
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
    for col in df.columns:
        col_l = str(col).lower()
        for kw in keywords:
            if kw in col_l:
                return col
    return None

# -------------------------------------------------------------------
# -------------------------- DATA LOADING ----------------------------
# -------------------------------------------------------------------

def load_group_sheet(file, sheet_name):
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
    df = df.dropna(how="all")

    event_meta_df = pd.DataFrame(event_meta)

    return df, event_cols, event_meta_df

# -------------------------------------------------------------------
# -------------------------- ANALYTICS -------------------------------
# -------------------------------------------------------------------

def student_participation_analysis(df, event_cols, event_meta_df):
    df = df.copy()

    for col in event_cols:
        if col in df.columns:
            df[col] = normalize_yes_no(df[col])

    df["Total Events Participated"] = df[event_cols].sum(axis=1)

    student_participation = df[["Student Name", "Total Events Participated"]].sort_values(
        "Total Events Participated", ascending=False
    )

    event_participation = (
        df[event_cols]
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .sum()
        .reset_index()
        .rename(columns={"index": "Column", 0: "Participants"})
        .merge(event_meta_df, on="Column", how="left")
        .sort_values("Participants", ascending=False)
    )

    return student_participation, event_participation

# -------------------------------------------------------------------
# -------------------------- STREAMLIT APP ---------------------------
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
    name_col = find_column(df, ["student name", "name"])
    conversion_col = find_column(df, ["conversion status", "conversion"])
    community_col = find_column(df, ["community status", "community"])
    payment_date_col = find_column(df, ["payment date", "payment"])

    if not name_col:
        st.error("❌ Student Name column not found. Please fix the sheet headers.")
        return

    # ------------------- PAYMENT & CONVERSION -------------------
    st.header("💰 Payment & Conversion Analysis")

    if conversion_col:
        conv_series = df[conversion_col].astype(str).str.lower().fillna("")

        paid_mask = conv_series.str.contains("paid|admitted|enrolled", na=False)
        will_pay_mask = conv_series.str.contains("will pay|likely|intent", na=False)
        not_paid_mask = ~(paid_mask | will_pay_mask)

        paid_students = df.loc[paid_mask, [name_col, conversion_col]]
        will_pay_students = df.loc[will_pay_mask, [name_col, conversion_col]]
        not_paid_students = df.loc[not_paid_mask, [name_col, conversion_col]]

        total_students = len(df)
        total_paid = int(paid_mask.sum())
        total_will_pay = int(will_pay_mask.sum())
        conversion_rate = round((total_paid / total_students) * 100, 2) if total_students else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Students", total_students)
        col2.metric("Paid / Admitted", total_paid)
        col3.metric("Will Pay", total_will_pay)
        col4.metric("Conversion Rate (%)", conversion_rate)

        st.subheader("✅ Paid / Admitted Students")
        st.dataframe(paid_students.reset_index(drop=True))

        st.subheader("🟡 Will Pay Students")
        st.dataframe(will_pay_students.reset_index(drop=True))

        st.subheader("🔴 Not Paid Students")
        st.dataframe(not_paid_students.reset_index(drop=True))
    else:
        st.warning("⚠️ Conversion Status column not found.")

    # ------------------- RETENTION ANALYSIS -------------------
    st.header("🔁 Retention Analysis")

    if community_col and payment_date_col:
        community_series = df[community_col].astype(str).str.lower().fillna("")
        payment_series = pd.to_datetime(df[payment_date_col], errors="coerce")

        retained_mask = community_series.str.contains("in|retained|active", na=False)
        paid_mask = payment_series.notna()

        retained_after_payment = retained_mask & paid_mask
        retention_rate = round((retained_after_payment.sum() / paid_mask.sum()) * 100, 2) if paid_mask.sum() else 0

        st.metric("Overall Retention Rate (%)", retention_rate)

        retained_students = df.loc[retained_after_payment, [name_col, community_col, payment_date_col]]
        st.subheader("Students Retained After Payment")
        st.dataframe(retained_students.reset_index(drop=True))
    else:
        st.warning("⚠️ Community Status or Payment Date column not found.")

    # ------------------- PARTICIPATION ANALYSIS -------------------
    st.header("📈 Participation Analysis")

    student_participation, event_participation = student_participation_analysis(
        df, event_cols, event_meta_df
    )

    st.subheader("Student-wise Participation")
    st.dataframe(student_participation.reset_index(drop=True))

    fig1 = px.bar(
        student_participation.head(30),
        x=name_col,
        y="Total Events Participated",
        title="Top 30 Students by Participation"
    )
    st.plotly_chart(fig1, use_container_width=True)

    st.subheader("Event-wise Participation")
    st.dataframe(event_participation.reset_index(drop=True))

    fig2 = px.bar(
        event_participation,
        x="Event Name",
        y="Participants",
        title="Event-wise Participation"
    )
    st.plotly_chart(fig2, use_container_width=True)

    total_participants = int((student_participation["Total Events Participated"] > 0).sum())
    non_participants = len(df) - total_participants

    fig3 = px.pie(
        names=["Participated", "Did Not Participate"],
        values=[total_participants, non_participants],
        title="Participation Distribution"
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

    category_summary = []
    for category in event_meta_df["Category"].unique():
        cat_events = event_meta_df[event_meta_df["Category"] == category]["Column"].tolist()

        if cat_events:
            cat_df = df[cat_events].apply(pd.to_numeric, errors="coerce").fillna(0)
            cat_participations = int(cat_df.sum().sum())
            cat_students = int((cat_df.sum(axis=1) > 0).sum())
        else:
            cat_participations = 0
            cat_students = 0

        category_summary.append({
            "Category": category,
            "Total Participations": cat_participations,
            "Unique Students": cat_students
        })

    cat_df = pd.DataFrame(category_summary)
    st.dataframe(cat_df)

    fig_cat = px.bar(cat_df, x="Category", y="Total Participations", title="Participation by Category")
    st.plotly_chart(fig_cat, use_container_width=True)

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
            elif category in ["AMA", "Masterclass"]:
                df_scoring["Category Points"] += df_scoring[col] * 2
            else:
                df_scoring["Category Points"] += df_scoring[col] * 1

    if conversion_col:
        conv_series = df_scoring[conversion_col].astype(str).str.lower().fillna("")
        df_scoring["Conversion Points"] = np.where(
            conv_series.str.contains("paid|admitted|enrolled", na=False), 10,
            np.where(conv_series.str.contains("will pay|likely|intent", na=False), 5, 0)
        )
    else:
        df_scoring["Conversion Points"] = 0

    if community_col:
        comm_series = df_scoring[community_col].astype(str).str.lower().fillna("")
        df_scoring["Retention Points"] = np.where(comm_series.str.contains("in|retained|active", na=False), 5, 0)
    else:
        df_scoring["Retention Points"] = 0

    df_scoring["Lead Score"] = (
        df_scoring["Event Points"] +
        df_scoring["Category Points"] +
        df_scoring["Conversion Points"] +
        df_scoring["Retention Points"]
    )

    leaderboard_cols = [name_col, "Lead Score"]
    if conversion_col:
        leaderboard_cols.append(conversion_col)

    leaderboard = df_scoring[leaderboard_cols].sort_values("Lead Score", ascending=False)

    st.subheader("Top Leads")
    st.dataframe(leaderboard.reset_index(drop=True).head(30))

    fig4 = px.histogram(df_scoring, x="Lead Score", title="Lead Score Distribution")
    st.plotly_chart(fig4, use_container_width=True)

    # ------------------- PER-STUDENT TIMELINE -------------------
    st.header("🕒 Per-Student Engagement Timeline")

    selected_student = st.selectbox("Select Student", df[name_col].dropna().unique())

    student_row = df[df[name_col] == selected_student].iloc[0]

    timeline_data = []

    for _, row in event_meta_df.iterrows():
        col = row["Column"]
        event_name = row["Event Name"]
        event_date = row["Event Date"]

        if col in df.columns:
            value_norm = normalize_yes_no(pd.Series([student_row[col]])).iloc[0]
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

    timeline_df = pd.DataFrame(timeline_data).dropna(subset=["Date"]).sort_values("Date")

    if not timeline_df.empty:
        fig5 = px.line(
            timeline_df,
            x="Date",
            y=[1] * len(timeline_df),
            color="Type",
            markers=True,
            text="Event",
            title=f"Timeline for {selected_student}"
        )
        fig5.update_traces(textposition="top center")
        fig5.update_yaxes(visible=False)
        st.plotly_chart(fig5, use_container_width=True)
    else:
        st.info("No participation or payment data available for this student.")

if __name__ == "__main__":
    run_streamlit_app()
