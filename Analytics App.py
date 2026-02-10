import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

st.set_page_config(page_title="Engagement Analytics", layout="wide")


# ----------------------------- #
# 🔧 HELPERS
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
        .apply(pd.to_numeric, errors="coerce")
        .fillna(0)
        .astype(int)
    )


def find_column(df, keywords):
    for col in df.columns:
        col_l = str(col).lower()
        for kw in keywords:
            if kw in col_l:
                return col
    return None


def make_unique_columns(cols):
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


# ----------------------------- #
# 📥 LOAD SHEET (YOUR FORMAT)
# ----------------------------- #
@st.cache_data
def load_group_sheet(uploaded_file, sheet_name):
    raw = pd.read_excel(uploaded_file, sheet_name=sheet_name, header=None)

    # Row 0 → Event names
    # Row 1 → Event dates
    # Row 2 → Actual column headers
    event_names = raw.iloc[0].fillna("").astype(str)
    header_row = 2

    headers = raw.iloc[header_row].fillna("").astype(str)
    headers = make_unique_columns(headers)

    df = raw.iloc[header_row + 1:].reset_index(drop=True)
    df.columns = headers

    # Drop completely empty rows
    df = df.dropna(how="all")

    # Drop summary numeric rows at bottom
    df = df[df["Student Name"].astype(str).str.strip().ne("0")]

    # Detect event columns = columns between Comments and first student event column
    metadata_cols = [
        "Student Name", "E mail", "Phone Number", "Country", "Income", "Batch",
        "Data Added to the community", "Community Status", "Date of Exit",
        "Conversion Status", "Overall Engagement Score", "Conversion Status_1",
        "Payment Date", "Comments"
    ]

    event_cols = [col for col in df.columns if col not in metadata_cols]

    # Clean event columns
    for col in event_cols:
        df[col] = normalize_yes_no(df[col])

    return df, event_cols, event_names[event_names != ""].tolist()


# ----------------------------- #
# 📊 PARTICIPATION ANALYSIS
# ----------------------------- #
def student_participation_analysis(df, event_cols):
    df = df.copy()
    df["Total Participation"] = df[event_cols].sum(axis=1)

    event_participation = df[event_cols].sum().reset_index()
    event_participation.columns = ["Event", "Participants"]

    return df, event_participation


# ----------------------------- #
# 💰 CONVERSION & RETENTION
# ----------------------------- #
def conversion_and_retention_analysis(df, conversion_col, payment_date_col):
    df = df.copy()

    if conversion_col:
        df["Conversion Status Clean"] = df[conversion_col].astype(str).str.strip()
    else:
        df["Conversion Status Clean"] = ""

    paid_mask = df["Conversion Status Clean"].str.contains("paid|admitted", case=False, na=False)
    will_pay_mask = df["Conversion Status Clean"].str.contains("will pay", case=False, na=False)
    not_paid_mask = ~(paid_mask | will_pay_mask)

    paid_students = df[paid_mask]
    will_pay_students = df[will_pay_mask]
    not_paid_students = df[not_paid_mask]

    engaged_students = df[df["Total Participation"] > 0]
    conversion_rate = (len(paid_students) / len(engaged_students) * 100) if len(engaged_students) > 0 else 0

    retained_students = []
    retention_rate = 0

    if payment_date_col:
        for _, row in paid_students.iterrows():
            payment_date = pd.to_datetime(row.get(payment_date_col), errors="coerce")
            if not pd.isna(payment_date) and row["Total Participation"] > 0:
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
def plot_student_timeline(df, event_cols, event_names, student_name, payment_date_col):
    row = df[df["Student Name"] == student_name].iloc[0]

    x = list(range(1, len(event_cols) + 1))
    y = [row[col] for col in event_cols]

    labels = event_names[:len(event_cols)]

    plt.figure(figsize=(12, 4))
    plt.plot(x, y, marker="o")
    plt.xticks(x, labels, rotation=45, ha="right")
    plt.ylabel("Participation (1 = Yes, 0 = No)")
    plt.title(f"Participation Timeline: {student_name}")
    plt.grid(True)

    if payment_date_col:
        payment_val = row.get(payment_date_col)
        payment_date = pd.to_datetime(payment_val, errors="coerce")
        if not pd.isna(payment_date):
            plt.scatter(x[-1], 1, marker="v", color="green", s=150)
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

    df, event_cols, event_names = load_group_sheet(uploaded_file, sheet_name)
    df, event_participation = student_participation_analysis(df, event_cols)

    conversion_col = find_column(df, ["conversion status"])
    payment_date_col = find_column(df, ["payment date"])

    conv_metrics = conversion_and_retention_analysis(df, conversion_col, payment_date_col)

    # ----------------------------- #
    # 🏆 TOP PARTICIPATING STUDENTS
    # ----------------------------- #
    st.subheader("🏆 Top Participating Students")

    cols = ["Student Name", "Total Participation"]
    if conversion_col:
        cols.append(conversion_col)

    top_students = df.sort_values("Total Participation", ascending=False)[cols].head(25)
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

    if not conv_metrics["paid_students"].empty:
        st.write("✅ Paid / Admitted Students")
        st.dataframe(conv_metrics["paid_students"][["Student Name", "Conversion Status Clean"]],
                     use_container_width=True)

    if not conv_metrics["will_pay_students"].empty:
        st.write("🟡 Will Pay Students")
        st.dataframe(conv_metrics["will_pay_students"][["Student Name", "Conversion Status Clean"]],
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
    cols = ["Student Name"]
    if conversion_col:
        cols.append(conversion_col)
    if payment_date_col:
        cols.append(payment_date_col)

    if not no_participants.empty:
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

    cols = ["Student Name", "Total Participation"]
    if payment_date_col:
        cols.append(payment_date_col)

    if not low_engagement_paid.empty:
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

    student_choice = st.selectbox("Select Student", df["Student Name"].dropna().unique())
    plot_student_timeline(df, event_cols, event_names, student_choice, payment_date_col)

    # ----------------------------- #
    # 📋 RAW DATA VIEW
    # ----------------------------- #
    with st.expander("📋 View Cleaned Data"):
        st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    run_streamlit_app()
