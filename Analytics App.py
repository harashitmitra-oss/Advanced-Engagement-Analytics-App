import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from collections import Counter

st.set_page_config(page_title="Engagement Analytics Dashboard", layout="wide")
st.title("📊 Engagement Analytics Dashboard")

uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel File", type=["xlsx"])

# -------------------- Utility Functions --------------------
def make_unique(columns):
    counts = Counter()
    new_cols = []
    for col in columns:
        col = str(col).strip()
        if counts[col] == 0:
            new_cols.append(col)
        else:
            new_cols.append(f"{col}_{counts[col]}")
        counts[col] += 1
    return new_cols


def normalize_binary(x):
    if pd.isna(x):
        return 0
    x = str(x).strip().lower()
    if x in ["yes", "y", "true", "1"]:
        return 1
    return 0


def detect_header_rows(raw):
    """Dynamically detect main header row by searching for 'Student Name' or similar."""
    for i in range(0, 8):
        row = raw.iloc[i].astype(str).str.lower()
        if any("student" in cell and "name" in cell for cell in row):
            return i
    return 2  # fallback


def detect_event_header_row(raw):
    """Detect event header row by finding the first row with many non-null text values."""
    for i in range(0, 8):
        row = raw.iloc[i]
        non_null = row.notna().sum()
        if non_null > 10:
            return i
    return 0


if uploaded_file:
    xl = pd.ExcelFile(uploaded_file)
    sheet_name = st.selectbox("Select Sheet", xl.sheet_names)

    raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)

    # -------------------- Dynamic Header Detection --------------------
    main_header_row = detect_header_rows(raw)
    event_header_row = detect_event_header_row(raw)
    data_start_row = main_header_row + 1

    # Build columns
    main_headers = raw.iloc[main_header_row, :12].astype(str)
    event_headers = raw.iloc[event_header_row, 12:].astype(str)
    columns = list(main_headers) + list(event_headers)

    df = raw.iloc[data_start_row:].reset_index(drop=True)
    df.columns = columns

    # Clean column names
    df.columns = (
        df.columns.astype(str)
        .str.replace("\n", " ", regex=True)
        .str.replace("\r", " ", regex=True)
        .str.replace("\u00a0", " ", regex=True)
        .str.strip()
    )

    df.columns = make_unique(df.columns)

    # Drop empty rows
    df = df.dropna(how="all")

    # Remove summary / numeric-only rows
    df = df[~df.apply(lambda row: all(str(x).replace('.', '', 1).isdigit() for x in row if pd.notna(x)), axis=1)]

    # -------------------- Column Detection --------------------
    student_col = next((c for c in df.columns if "student" in c.lower() and "name" in c.lower()), None)
    conversion_col = next((c for c in df.columns if "conversion" in c.lower()), None)
    payment_date_col = next((c for c in df.columns if "payment" in c.lower() and "date" in c.lower()), None)

    if not student_col:
        st.error("❌ Could not detect Student Name column. Please check sheet structure.")
        st.stop()

    # Event columns = everything after the first 12 metadata columns
    event_columns = df.columns[12:].tolist()

    # Normalize event values safely
    for col in event_columns:
        df[col] = df[col].apply(normalize_binary)

    # Total participation
    df["Total Participations"] = df[event_columns].sum(axis=1)

    # -------------------- Metrics --------------------
    total_students = len(df)
    active_students = (df["Total Participations"] > 0).sum()

    paid_students = pd.DataFrame()
    will_pay_students = pd.DataFrame()
    not_paid_students = pd.DataFrame()

    if conversion_col:
        conv_series = df[conversion_col].astype(str).str.lower().str.strip()
        paid_students = df[conv_series.isin(["admitted", "paid", "yes"])]
        will_pay_students = df[conv_series.str.contains("will", na=False)]
        not_paid_students = df[~df.index.isin(paid_students.index) & ~df.index.isin(will_pay_students.index)]

    conversion_rate = (len(paid_students) / active_students * 100) if active_students > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Students", total_students)
    col2.metric("Active Students", active_students)
    col3.metric("Paid / Admitted", len(paid_students))
    col4.metric("Conversion Rate", f"{conversion_rate:.1f}%")

    # -------------------- 1️⃣ Top Participating Students --------------------
    st.header("1️⃣ Top Participating Students")
    leaderboard = df[[student_col, "Total Participations"]].sort_values(by="Total Participations", ascending=False)
    if conversion_col:
        leaderboard["Conversion Status"] = df[conversion_col]
    st.dataframe(leaderboard, use_container_width=True)

    # -------------------- 2️⃣ Payment & Conversion Analysis --------------------
    st.header("2️⃣ Payment & Conversion Analysis")

    colA, colB, colC = st.columns(3)

    with colA:
        st.subheader("✅ Paid / Admitted")
        if not paid_students.empty:
            st.dataframe(paid_students[[student_col, conversion_col]], use_container_width=True)
        else:
            st.warning("No paid/admitted students found.")

    with colB:
        st.subheader("🟡 Will Pay")
        if not will_pay_students.empty:
            st.dataframe(will_pay_students[[student_col, conversion_col]], use_container_width=True)
        else:
            st.warning("No will-pay students found.")

    with colC:
        st.subheader("🔴 Not Paid")
        if not not_paid_students.empty:
            st.dataframe(not_paid_students[[student_col, conversion_col]], use_container_width=True)
        else:
            st.warning("No not-paid students found.")

    # -------------------- 3️⃣ Retention Analysis (PG Only) --------------------
    st.header("3️⃣ Retention Analysis")

    if payment_date_col:
        df[payment_date_col] = pd.to_datetime(df[payment_date_col], errors="coerce")

        retained_flags = []
        for idx, row in df.iterrows():
            pay_date = row[payment_date_col]
            if pd.isna(pay_date):
                retained_flags.append(0)
            else:
                retained_flags.append(1 if row[event_columns].sum() > 0 else 0)

        df["Retained"] = retained_flags
        retention_rate = df["Retained"].mean() * 100

        col1, col2 = st.columns(2)
        col1.metric("Retention Rate", f"{retention_rate:.1f}%")
        retained_students = df[df["Retained"] == 1]
        col2.dataframe(retained_students[[student_col, payment_date_col, "Retained"]], use_container_width=True)
    else:
        st.error("❌ Payment Date column not detected — retention analysis skipped.")

    # -------------------- 4️⃣ Students With NO Event Participation --------------------
    st.header("4️⃣ Students With NO Event Participation")
    zero_participants = df[df["Total Participations"] == 0]
    zero_cols = [student_col]
    if conversion_col:
        zero_cols.append(conversion_col)
    if payment_date_col:
        zero_cols.append(payment_date_col)
    st.dataframe(zero_participants[zero_cols], use_container_width=True)

    # -------------------- 5️⃣ Paid Students With Low / No Engagement --------------------
    st.header("5️⃣ Paid Students With Low / No Engagement")
    if not paid_students.empty:
        paid_low_engagement = paid_students[paid_students["Total Participations"] <= 1]
        st.dataframe(paid_low_engagement[[student_col, "Total Participations", conversion_col]], use_container_width=True)
    else:
        st.warning("No paid/admitted students found.")

    # -------------------- 6️⃣ Event-wise Participation --------------------
    st.header("6️⃣ Event-wise Participation")
    event_participation = df[event_columns].sum().sort_values(ascending=False)
    event_df = event_participation.reset_index()
    event_df.columns = ["Event", "Participants"]

    fig_event = px.bar(event_df, x="Event", y="Participants", title="Event Participation Count")
    st.plotly_chart(fig_event, use_container_width=True)
    st.dataframe(event_df, use_container_width=True)

    # -------------------- Heatmap --------------------
    st.subheader("🔥 Student Participation Heatmap")
    heatmap_df = df[df["Total Participations"] > 0][event_columns]
    if not heatmap_df.empty:
        fig_heatmap = px.imshow(
            heatmap_df,
            labels=dict(x="Events", y="Students", color="Participation"),
            aspect="auto",
            title="Student Participation Heatmap (Rows = Students, Columns = Events)",
        )
        st.plotly_chart(fig_heatmap, use_container_width=True)
    else:
        st.info("No participation data available for heatmap.")

    # -------------------- 7️⃣ Per-Student Participation Timeline (DATE-AWARE) --------------------
    st.header("7️⃣ Per-Student Participation Timeline")

    selected_student = st.selectbox("Select Student", df[student_col].dropna().unique())
    student_row = df[df[student_col] == selected_student].iloc[0]

    timeline_df = pd.DataFrame({
        "Event": event_columns,
        "Participation": [int(student_row[col]) for col in event_columns]
    })

    # Attempt to extract event dates from event headers
    def extract_date(text):
        try:
            return pd.to_datetime(text, errors="coerce")
        except:
            return pd.NaT

    timeline_df["Event Date"] = timeline_df["Event"].apply(extract_date)

    # Use event dates if available, otherwise use sequence
    if timeline_df["Event Date"].notna().sum() > 0:
        timeline_df = timeline_df.sort_values(by="Event Date")
        x_axis = "Event Date"
    else:
        timeline_df["Sequence"] = range(1, len(timeline_df) + 1)
        x_axis = "Sequence"

    fig_timeline = px.line(
        timeline_df[timeline_df["Participation"] == 1],
        x=x_axis,
        y="Participation",
        markers=True,
        title=f"Participation Timeline – {selected_student}",
    )

    # Add payment date marker
    if payment_date_col and not pd.isna(student_row[payment_date_col]):
        fig_timeline.add_scatter(
            x=[student_row[payment_date_col]],
            y=[1],
            mode="markers+text",
            marker=dict(color="green", size=12),
            text=["✔ Admitted"],
            textposition="top center",
            name="Payment Date",
        )

    st.plotly_chart(fig_timeline, use_container_width=True)

    # -------------------- 🏆 Lead Scoring --------------------
    st.header("🏆 Lead Scoring")

    hackathon_cols = [c for c in event_columns if "hackathon" in c.lower()]
    ama_cols = [c for c in event_columns if "ama" in c.lower()]
    masterclass_cols = [c for c in event_columns if "masterclass" in c.lower()]

    df["Hackathon Participation Count"] = df[hackathon_cols].sum(axis=1) if hackathon_cols else 0
    df["AMA Participation Count"] = df[ama_cols].sum(axis=1) if ama_cols else 0
    df["Masterclass Participation Count"] = df[masterclass_cols].sum(axis=1) if masterclass_cols else 0

    df["Lead Score"] = 0
    df["Lead Score"] += df["Total Participations"] * 10
    df["Lead Score"] += df["Hackathon Participation Count"] * 20
    df["Lead Score"] += df["AMA Participation Count"] * 15
    df["Lead Score"] += df["Masterclass Participation Count"] * 15

    if conversion_col:
        df["Lead Score"] += df[conversion_col].astype(str).str.lower().isin(["admitted", "paid", "yes"]) * 30

    top_leads = df[[student_col, "Lead Score", "Total Participations"]].sort_values(by="Lead Score", ascending=False)
    st.dataframe(top_leads, use_container_width=True)

    fig_score = px.histogram(df, x="Lead Score", nbins=20, title="Lead Score Distribution")
    st.plotly_chart(fig_score, use_container_width=True)
