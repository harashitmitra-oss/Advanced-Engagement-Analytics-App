import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="Engagement Analytics", layout="wide")


# ----------------------------- #
# 📥 LOAD AND PARSE SHEET
# ----------------------------- #
@st.cache_data
def load_group_sheet(uploaded_file, sheet_name):
    raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)

    # Row structure (0-based)
    event_header_row = 0
    event_date_row = 1
    main_header_row = 2
    data_start_row = 3

    # Main student info headers
    main_headers = raw.iloc[main_header_row].fillna("").astype(str)
    df = raw.iloc[data_start_row:].reset_index(drop=True)
    df.columns = main_headers

    # Build event metadata
    event_meta = []
    for col_idx, col_name in enumerate(raw.iloc[event_header_row]):
        if pd.notna(col_name) and str(col_name).strip() != "":
            event_name = str(col_name).strip()
            event_date = raw.iloc[event_date_row, col_idx]
            event_meta.append({
                "Column": main_headers[col_idx],
                "Event": event_name,
                "Date": pd.to_datetime(event_date, errors="coerce")
            })

    event_meta_df = pd.DataFrame(event_meta)
    event_cols = event_meta_df["Column"].tolist()

    return df, event_cols, event_meta_df


# ----------------------------- #
# 🔁 NORMALIZATION
# ----------------------------- #
def normalize_yes_no(series):
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .replace({
            "yes": 1, "y": 1, "true": 1, "1": 1,
            "no": 0, "n": 0, "false": 0, "0": 0,
            "nan": 0, "none": 0, "": 0
        })
        .fillna(0)
        .astype(int)
    )


# ----------------------------- #
# 📊 CORE ANALYSIS
# ----------------------------- #
def student_participation_analysis(df, event_cols, event_meta_df):
    df[event_cols] = df[event_cols].apply(normalize_yes_no)

    # Total participation per student
    df["Total Participation"] = df[event_cols].sum(axis=1)

    # Per-event participation
    event_participation = df[event_cols].sum().reset_index()
    event_participation.columns = ["Column", "Participants"]
    event_participation = event_participation.merge(event_meta_df, on="Column", how="left")

    # Participants list per event
    participants = {}
    for col in event_cols:
        participants[col] = df[df[col] == 1]["Student Name"].tolist()

    return df, event_participation, participants


# ----------------------------- #
# 💰 CONVERSION + RETENTION
# ----------------------------- #
def conversion_and_retention_analysis(df, event_cols, event_meta_df):
    df["Conversion Status"] = df["Conversion Status"].astype(str).str.strip().str.lower()

    paid_mask = df["Conversion Status"].str.contains("paid|admitted", na=False)
    will_pay_mask = df["Conversion Status"].str.contains("will pay", na=False)
    not_paid_mask = ~(paid_mask | will_pay_mask)

    paid_students = df[paid_mask]
    will_pay_students = df[will_pay_mask]
    not_paid_students = df[not_paid_mask]

    total_engaged = len(df[df["Total Participation"] > 0])
    total_converted = len(paid_students)
    conversion_rate = (total_converted / total_engaged * 100) if total_engaged > 0 else 0

    # --- RETENTION ---
    retained_students = []
    for _, row in paid_students.iterrows():
        payment_date = pd.to_datetime(row.get("Date of Payment"), errors="coerce")
        if pd.isna(payment_date):
            continue

        participated_after_payment = False
        for _, meta in event_meta_df.iterrows():
            if meta["Date"] and meta["Date"] > payment_date:
                if row[meta["Column"]] == 1:
                    participated_after_payment = True
                    break

        if participated_after_payment:
            retained_students.append(row["Student Name"])

    retention_rate = (len(retained_students) / total_converted * 100) if total_converted > 0 else 0

    return {
        "paid_students": paid_students,
        "will_pay_students": will_pay_students,
        "not_paid_students": not_paid_students,
        "conversion_rate": conversion_rate,
        "retained_students": retained_students,
        "retention_rate": retention_rate
    }


# ----------------------------- #
# 📈 PER-STUDENT TIMELINE
# ----------------------------- #
def plot_student_timeline(df, event_cols, event_meta_df, student_name):
    row = df[df["Student Name"] == student_name].iloc[0]
    dates = event_meta_df["Date"]
    values = [row[col] for col in event_meta_df["Column"]]

    plt.figure(figsize=(10, 4))
    plt.plot(dates, values, marker="o")
    plt.title(f"Participation Timeline: {student_name}")
    plt.xlabel("Date")
    plt.ylabel("Participation (1 = Yes, 0 = No)")
    plt.grid(True)

    # Payment marker
    payment_date = pd.to_datetime(row.get("Date of Payment"), errors="coerce")
    if not pd.isna(payment_date):
        plt.scatter(payment_date, 1, marker="v", color="green", s=120)
        plt.text(payment_date, 1.05, "✔ Paid", color="green")

    st.pyplot(plt)


# ----------------------------- #
# 🚀 STREAMLIT APP
# ----------------------------- #
def run_streamlit_app():
    st.title("🎯 Engagement Analytics Dashboard")

    uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel", type=["xlsx"])

    if not uploaded_file:
        st.warning("Please upload your Excel file.")
        return

    sheet_name = st.selectbox(
        "Select Group Sheet",
        ["PG engagement tracker B2"]  # focus only on this for now
    )

    df, event_cols, event_meta_df = load_group_sheet(uploaded_file, sheet_name)
    df, event_participation, participants = student_participation_analysis(df, event_cols, event_meta_df)
    conv_metrics = conversion_and_retention_analysis(df, event_cols, event_meta_df)

    # ----------------------------- #
    # 🏆 TOP PARTICIPATING STUDENTS
    # ----------------------------- #
    st.subheader("🏆 Top Participating Students")

    top_students = df.sort_values("Total Participation", ascending=False)[
        ["Student Name", "Total Participation", "Conversion Status"]
    ].head(20)

    st.dataframe(top_students, use_container_width=True)

    # ----------------------------- #
    # 💰 PAYMENT & CONVERSION
    # ----------------------------- #
    st.subheader("💰 Payment & Conversion Analysis")

    col1, col2, col3 = st.columns(3)
    col1.metric("✅ Paid / Admitted", len(conv_metrics["paid_students"]))
    col2.metric("🟡 Will Pay", len(conv_metrics["will_pay_students"]))
    col3.metric("🔴 Not Paid", len(conv_metrics["not_paid_students"]))

    st.metric("📈 Conversion Rate (%)", round(conv_metrics["conversion_rate"], 2))

    # ----------------------------- #
    # 🔁 RETENTION
    # ----------------------------- #
    st.subheader("🔁 Retention Analysis")

    st.metric("🔄 Retention Rate (%)", round(conv_metrics["retention_rate"], 2))

    if conv_metrics["retained_students"]:
        st.write("🎯 Retained Students (Participated after payment):")
        st.write(conv_metrics["retained_students"])
    else:
        st.info("No retained students detected yet.")

    # ----------------------------- #
    # 📊 EVENT PARTICIPATION CHART
    # ----------------------------- #
    st.subheader("📊 Event-wise Participation")

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(event_participation["Event"], event_participation["Participants"])
    ax.set_xticklabels(event_participation["Event"], rotation=45, ha="right")
    ax.set_ylabel("Participants")
    ax.set_title("Event Participation Count")
    st.pyplot(fig)

    # ----------------------------- #
    # 📈 PER-STUDENT TIMELINE
    # ----------------------------- #
    st.subheader("📈 Per-Student Participation Timeline")

    student_choice = st.selectbox("Select Student", df["Student Name"].dropna().unique())
    plot_student_timeline(df, event_cols, event_meta_df, student_choice)

    # ----------------------------- #
    # 📋 RAW DATA VIEW
    # ----------------------------- #
    with st.expander("📋 View Processed Data"):
        st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    run_streamlit_app()
