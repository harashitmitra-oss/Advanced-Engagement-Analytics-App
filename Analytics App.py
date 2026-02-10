import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="Engagement Analytics", layout="wide")


# ----------------------------- #
# 🔧 UTILS
# ----------------------------- #
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
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
    )


def find_column(df, keywords):
    for col in df.columns:
        col_l = str(col).lower()
        for kw in keywords:
            if kw in col_l:
                return col
    return None


# ----------------------------- #
# 📥 LOAD & PARSE SHEET
# ----------------------------- #
@st.cache_data
def load_group_sheet(uploaded_file, sheet_name):
    raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)

    # Find header row
    header_row = None
    for i in range(6):
        if raw.iloc[i].astype(str).str.contains("student", case=False).any():
            header_row = i
            break

    if header_row is None:
        raise ValueError("Could not detect header row.")

    headers = raw.iloc[header_row].fillna("").astype(str)
    headers = make_columns_unique(headers)

    df = raw.iloc[header_row + 1:].reset_index(drop=True)
    df.columns = headers

    # Detect event columns (Yes/No heavy columns)
    event_cols = []
    for col in df.columns:
        try:
            series = df[col]
            if isinstance(series, pd.DataFrame):
                series = series.iloc[:, 0]
            sample = series.dropna().astype(str).str.lower()
            if len(sample) > 0 and sample.isin(["yes", "no", "y", "n", "1", "0"]).mean() > 0.5:
                event_cols.append(col)
        except:
            continue

    event_meta_df = pd.DataFrame({"Column": event_cols, "Event": event_cols})

    return df, event_cols, event_meta_df


# ----------------------------- #
# 📊 PARTICIPATION ANALYSIS
# ----------------------------- #
def student_participation_analysis(df, event_cols):
    df = df.copy()

    if not event_cols:
        df["Total Participation"] = 0
        return df, pd.DataFrame(), {}

    for col in event_cols:
        series = df[col]
        if isinstance(series, pd.DataFrame):
            series = series.iloc[:, 0]
        df[col] = normalize_yes_no(series)

    df["Total Participation"] = df[event_cols].sum(axis=1)

    event_participation = df[event_cols].sum().reset_index()
    event_participation.columns = ["Event", "Participants"]

    participants = {}
    for col in event_cols:
        participants[col] = df.loc[df[col] == 1, "Student Name"].tolist() if "Student Name" in df.columns else []

    return df, event_participation, participants


# ----------------------------- #
# 💰 CONVERSION & RETENTION
# ----------------------------- #
def conversion_and_retention_analysis(df, event_cols, payment_date_col, conversion_col):
    df = df.copy()

    if conversion_col:
        conv_series = df[conversion_col]
        if isinstance(conv_series, pd.DataFrame):
            conv_series = conv_series.iloc[:, 0]
        df["Conversion Status Clean"] = conv_series.astype(str).str.strip().str.lower()
    else:
        df["Conversion Status Clean"] = ""

    paid_mask = df["Conversion Status Clean"].str.contains("paid|admitted", na=False)
    will_pay_mask = df["Conversion Status Clean"].str.contains("will pay", na=False)
    not_paid_mask = ~(paid_mask | will_pay_mask)

    paid_students = df[paid_mask]
    will_pay_students = df[will_pay_mask]
    not_paid_students = df[not_paid_mask]

    engaged_students = df[df["Total Participation"] > 0]
    conversion_rate = (len(paid_students) / len(engaged_students) * 100) if len(engaged_students) > 0 else 0

    # Retention = Paid students who participated AFTER payment date
    retained_students = []
    retention_rate = 0

    if payment_date_col:
        for _, row in paid_students.iterrows():
            payment_date = pd.to_datetime(row.get(payment_date_col), errors="coerce")
            if pd.isna(payment_date):
                continue

            # If participated in ANY event (future-ready placeholder)
            if row["Total Participation"] > 0:
                retained_students.append(row["Student Name"])

        retention_rate = (len(retained_students) / len(paid_students) * 100) if len(paid_students) > 0 else 0

    return {
        "paid_students": paid_students,
        "will_pay_students": will_pay_students,
        "not_paid_students": not_paid_students,
        "conversion_rate": conversion_rate,
        "retained_students": retained_students,
        "retention_rate": retention_rate
    }


# ----------------------------- #
# 📈 STUDENT TIMELINE
# ----------------------------- #
def plot_student_timeline(df, event_cols, student_name, payment_date_col):
    row = df[df["Student Name"] == student_name].iloc[0]

    x = list(range(1, len(event_cols) + 1))
    y = [row[col] if col in df.columns else 0 for col in event_cols]

    plt.figure(figsize=(12, 4))
    plt.plot(x, y, marker="o", linestyle="-")
    plt.xticks(x, event_cols, rotation=45, ha="right")
    plt.ylabel("Participation (1 = Yes, 0 = No)")
    plt.title(f"Participation Timeline: {student_name}")
    plt.grid(True)

    # Green tick for payment
    if payment_date_col:
        payment_val = row.get(payment_date_col)
        payment_date = pd.to_datetime(payment_val, errors="coerce")
        if not pd.isna(payment_date):
            plt.scatter(x[-1], 1, marker="v", color="green", s=140)
            plt.text(x[-1], 1.1, "✔ Paid", color="green", ha="center")

    st.pyplot(plt)


# ----------------------------- #
# 🚀 STREAMLIT APP
# ----------------------------- #
def run_streamlit_app():
    st.title("🎯 Advanced Engagement Analytics Dashboard")

    uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel", type=["xlsx"])
    if not uploaded_file:
        st.warning("Please upload your Excel file.")
        return

    xls = pd.ExcelFile(uploaded_file)
    sheet_name = st.selectbox("Select Sheet / Group", xls.sheet_names)

    df, event_cols, event_meta_df = load_group_sheet(uploaded_file, sheet_name)
    df, event_participation, participants = student_participation_analysis(df, event_cols)

    # Detect key columns
    conversion_col = find_column(df, ["conversion status", "conversion"])
    payment_date_col = find_column(df, ["payment date", "date of payment", "payment"])
    community_col = find_column(df, ["community status", "community"])

    conv_metrics = conversion_and_retention_analysis(df, event_cols, payment_date_col, conversion_col)

    # ----------------------------- #
    # 🏆 TOP PARTICIPATING STUDENTS
    # ----------------------------- #
    st.subheader("🏆 Top Participating Students")

    if "Student Name" in df.columns:
        top_students = df.sort_values("Total Participation", ascending=False)[
            ["Student Name", "Total Participation"] + ([conversion_col] if conversion_col else [])
        ].head(20)
        st.dataframe(top_students, use_container_width=True)
    else:
        st.warning("Student Name column not found.")

    # ----------------------------- #
    # 💰 PAYMENT & CONVERSION
    # ----------------------------- #
    st.subheader("💰 Payment & Conversion Analysis")

    col1, col2, col3 = st.columns(3)
    col1.metric("✅ Paid / Admitted", len(conv_metrics["paid_students"]))
    col2.metric("🟡 Will Pay", len(conv_metrics["will_pay_students"]))
    col3.metric("🔴 Not Paid", len(conv_metrics["not_paid_students"]))
    st.metric("📈 Conversion Rate (%)", round(conv_metrics["conversion_rate"], 2))

    if not conv_metrics["paid_students"].empty:
        st.write("✅ Paid / Admitted Students")
        st.dataframe(conv_metrics["paid_students"][["Student Name"] + ([conversion_col] if conversion_col else [])],
                     use_container_width=True)

    if not conv_metrics["will_pay_students"].empty:
        st.write("🟡 Will Pay Students")
        st.dataframe(conv_metrics["will_pay_students"][["Student Name"] + ([conversion_col] if conversion_col else [])],
                     use_container_width=True)

    # ----------------------------- #
    # 🔁 RETENTION
    # ----------------------------- #
    st.subheader("🔁 Retention Analysis")

    if payment_date_col:
        st.metric("🔄 Retention Rate (%)", round(conv_metrics["retention_rate"], 2))
        if conv_metrics["retained_students"]:
            st.write("🎯 Retained Students:")
            st.write(conv_metrics["retained_students"])
        else:
            st.info("No retained students detected yet.")
    else:
        st.info("Retention not calculated for this sheet (no payment date column).")

    # ----------------------------- #
    # ❌ NO PARTICIPATION STUDENTS
    # ----------------------------- #
    st.subheader("❌ Students With NO Event Participation")

    no_participants = df[df["Total Participation"] == 0]
    if not no_participants.empty:
        cols = ["Student Name"]
        if conversion_col:
            cols.append(conversion_col)
        if payment_date_col:
            cols.append(payment_date_col)
        st.dataframe(no_participants[cols], use_container_width=True)
    else:
        st.success("🎉 All students have participated in at least one event.")

    # ----------------------------- #
    # ⚠️ PAID BUT LOW ENGAGEMENT
    # ----------------------------- #
    st.subheader("⚠️ Paid Students With Low / No Engagement")

    low_engagement_paid = conv_metrics["paid_students"][
        conv_metrics["paid_students"]["Total Participation"] <= 1
    ]

    if not low_engagement_paid.empty:
        cols = ["Student Name", "Total Participation"]
        if payment_date_col:
            cols.append(payment_date_col)
        st.dataframe(low_engagement_paid[cols], use_container_width=True)
    else:
        st.success("👏 No paid students with low engagement!")

    # ----------------------------- #
    # 📊 EVENT PARTICIPATION
    # ----------------------------- #
    st.subheader("📊 Event-wise Participation")

    if not event_participation.empty:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(event_participation["Event"], event_participation["Participants"])
        ax.set_xticklabels(event_participation["Event"], rotation=45, ha="right")
        ax.set_ylabel("Participants")
        ax.set_title("Event Participation Count")
        st.pyplot(fig)
    else:
        st.info("No event participation data detected.")

    # ----------------------------- #
    # 📈 PER-STUDENT TIMELINE
    # ----------------------------- #
    st.subheader("📈 Per-Student Participation Timeline")

    if "Student Name" in df.columns and event_cols:
        student_choice = st.selectbox("Select Student", df["Student Name"].dropna().unique())
        plot_student_timeline(df, event_cols, student_choice, payment_date_col)
    else:
        st.info("Timeline not available for this sheet.")

    # ----------------------------- #
    # 📋 RAW DATA VIEW
    # ----------------------------- #
    with st.expander("📋 View Processed Data"):
        st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    run_streamlit_app()
