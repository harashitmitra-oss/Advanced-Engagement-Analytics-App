# === Advanced Engagement Analytics App (Robust, Single-File, Production-Ready) ===

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Advanced Engagement Analytics", layout="wide")

# -------------------------------------------------------------------
# -------------------------- HELPER FUNCTIONS ------------------------
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
# -------------------------- DATA LOADING ---------------------------
# -------------------------------------------------------------------

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

    # Normalize event columns
    for col in event_cols:
        if col in df.columns:
            df[col] = normalize_yes_no(df[col])

    df["Total Events Participated"] = df[event_cols].sum(axis=1)

    student_participation = df[["Student Name", "Total Events Participated"]].sort_values(
        "Total Events Participated", ascending=False
    )

    event_participation = (
        df[event_cols]
        .sum()
        .reset_index()
        .rename(columns={"index": "Column", 0: "Participants"})
        .merge(event_meta_df, on="Column", how="left")
        .sort_values("Participants", ascending=False)
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
    st.title("📊 Advanced Engagement Analytics Dashboard")

    uploaded_file = st.file_uploader("Upload your Master Engagement Tracker Excel file", type=["xlsx"])

    if not uploaded_file:
        st.info("Please upload your Excel file to continue.")
        return

    xls = pd.ExcelFile(uploaded_file)
    sheet_names = xls.sheet_names

    selected_sheet = st.sidebar.selectbox("Select Group / Sheet", sheet_names)

    df, event_cols, event_meta_df = load_group_sheet(uploaded_file, selected_sheet)

    # ------------------- SAFE COLUMN DETECTION -------------------
    student_col = find_column(df, ["student name", "name"])
    conversion_col = find_column(df, ["conversion status", "conversion"])
    community_col = find_column(df, ["community status", "community"])
    payment_date_col = find_column(df, ["payment date", "payment"])

    if student_col != "Student Name":
        df = df.rename(columns={student_col: "Student Name"})

    st.subheader("📄 Raw Data Preview")
    st.dataframe(df.head())

    # Normalize event columns once globally
    for col in event_cols:
        if col in df.columns:
            df[col] = normalize_yes_no(df[col])

    # ------------------- 💰 PAYMENT & CONVERSION ANALYSIS -------------------
    st.header("💰 Payment & Conversion Analysis")

    if conversion_col:
        conv_series = df[conversion_col]
        if isinstance(conv_series, pd.DataFrame):
            conv_series = conv_series.iloc[:, 0]

        conv_series = conv_series.astype(str).str.lower()

        paid_mask = conv_series.str.contains("paid|admitted", na=False)
        will_pay_mask = conv_series.str.contains("will pay", na=False)
        not_paid_mask = ~paid_mask & ~will_pay_mask

        paid_students = df.loc[paid_mask]
        will_pay_students = df.loc[will_pay_mask]
        not_paid_students = df.loc[not_paid_mask]

        col1, col2, col3 = st.columns(3)
        col1.metric("Converted / Paid", paid_mask.sum())
        col2.metric("Will Pay", will_pay_mask.sum())
        col3.metric("Not Paid", not_paid_mask.sum())

        total_students = len(df)
        conversion_rate = round((paid_mask.sum() / total_students) * 100, 2) if total_students else 0
        intent_rate = round(((paid_mask.sum() + will_pay_mask.sum()) / total_students) * 100, 2) if total_students else 0

        st.metric("Conversion Rate (%)", conversion_rate)
        st.metric("High-Intent Rate (Paid + Will Pay) (%)", intent_rate)

        st.subheader("✅ Converted / Paid Students")
        st.dataframe(paid_students[["Student Name", conversion_col]].sort_values(by=conversion_col))

        st.subheader("🟡 Will Pay Students")
        st.dataframe(will_pay_students[["Student Name", conversion_col]].sort_values(by=conversion_col))

        st.subheader("🔴 Participated but Not Paid")
        st.dataframe(not_paid_students[["Student Name", conversion_col]].sort_values(by=conversion_col))

    else:
        st.warning("⚠️ Conversion Status column not found.")

    # ------------------- 🔁 RETENTION ANALYSIS -------------------
    st.header("🔁 Retention Analysis")

    # Retention definition:
    # A student is retained if they participated in at least one event AFTER their payment date

    if payment_date_col:
        df["_PaymentDateParsed"] = pd.to_datetime(df[payment_date_col], errors="coerce")
    else:
        df["_PaymentDateParsed"] = pd.NaT

    # Parse event dates
    event_meta_df["Event Date Parsed"] = pd.to_datetime(event_meta_df["Event Date"], errors="coerce")

    retained_mask = []
    individual_retention = []

    for idx, row in df.iterrows():
        payment_date = row.get("_PaymentDateParsed")
        retained = False

        if pd.notna(payment_date):
            for _, ev in event_meta_df.iterrows():
                col = ev["Column"]
                event_date = ev["Event Date Parsed"]
                if col in df.columns and pd.notna(event_date):
                    if row[col] == 1 and event_date > payment_date:
                        retained = True
                        break

        retained_mask.append(retained)
        individual_retention.append({
            "Student Name": row["Student Name"],
            "Payment Date": payment_date,
            "Retained After Payment": retained
        })

    df_retention = pd.DataFrame(individual_retention)

    total_paid_students = df["_PaymentDateParsed"].notna().sum()
    retained_students = df_retention["Retained After Payment"].sum()

    retention_rate = round((retained_students / total_paid_students) * 100, 2) if total_paid_students else 0

    st.metric("Total Paid Students", total_paid_students)
    st.metric("Retained After Payment", retained_students)
    st.metric("Retention Rate (%)", retention_rate)

    st.subheader("📋 Individual Retention Status")
    st.dataframe(df_retention.sort_values("Retained After Payment", ascending=False))

    # ------------------- 📈 PARTICIPATION ANALYSIS -------------------
    st.header("📈 Participation Analysis")

    student_participation, event_participation, participants = student_participation_analysis(
        df, event_cols, event_meta_df
    )

    st.subheader("🏅 Highest to Lowest Participating Students")

    # ------------------- 🏆 LEAD SCORING SYSTEM -------------------
    df_scoring = df.copy()

    df_scoring["Event Points"] = df_scoring[event_cols].sum(axis=1)

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

    leaderboard = df_scoring[[
        "Student Name",
        "Total Events Participated",
        "Lead Score",
        conversion_col if conversion_col else "Student Name"
    ]].copy()

    if conversion_col:
        leaderboard = leaderboard.rename(columns={conversion_col: "Conversion Status"})
    else:
        leaderboard["Conversion Status"] = "Unknown"

    leaderboard = leaderboard.sort_values("Lead Score", ascending=False)

    st.dataframe(leaderboard)

    fig_lead = px.histogram(df_scoring, x="Lead Score", title="Lead Score Distribution")
    st.plotly_chart(fig_lead, use_container_width=True)

    # ------------------- 📊 EVENT-WISE PARTICIPATION -------------------
    st.subheader("📊 Event-wise Participation")
    st.dataframe(event_participation)

    fig_event = px.bar(event_participation, x="Event Name", y="Participants",
                        title="Event-wise Participation Count")
    st.plotly_chart(fig_event, use_container_width=True)

    total_participants = (student_participation["Total Events Participated"] > 0).sum()
    non_participants = len(df) - total_participants

    fig_pie = px.pie(
        names=["Participated", "Did Not Participate"],
        values=[total_participants, non_participants],
        title="Participation Percentage"
    )
    st.plotly_chart(fig_pie, use_container_width=True)

    # ------------------- 🗂 EVENT CATEGORY ANALYSIS -------------------
    st.header("🗂 Event Category Analysis")

    for category in event_meta_df["Category"].unique():
        st.subheader(f"{category}")
        cat_events = event_meta_df[event_meta_df["Category"] == category]["Column"].tolist()

        if cat_events:
            cat_students = df.loc[df[cat_events].sum(axis=1) > 0, "Student Name"].tolist()
            cat_participations = df[cat_events].sum().sum()
        else:
            cat_students = []
            cat_participations = 0

        st.metric("Total Participations", int(cat_participations))
        st.write("Students:", cat_students)

    # ------------------- 🕒 PER-STUDENT TIMELINE (CLEAR + CONNECTED) -------------------
    st.header("🕒 Per-Student Timeline")

    selected_student = st.selectbox("Select Student", df["Student Name"].dropna().unique())

    student_row = df[df["Student Name"] == selected_student].iloc[0]

    timeline_data = []

    for _, ev in event_meta_df.iterrows():
        col = ev["Column"]
        event_name = ev["Event Name"]
        event_date = ev["Event Date Parsed"]

        if col in df.columns and pd.notna(event_date):
            if student_row[col] == 1:
                timeline_data.append({
                    "Date": event_date,
                    "Event": event_name,
                    "Type": "Event"
                })

    # Add payment marker
    if payment_date_col:
        payment_val = student_row.get("_PaymentDateParsed")
        if pd.notna(payment_val):
            timeline_data.append({
                "Date": payment_val,
                "Event": "Payment",
                "Type": "Payment"
            })

    timeline_df = pd.DataFrame(timeline_data).dropna(subset=["Date"]).sort_values("Date")

    if not timeline_df.empty:
        fig = go.Figure()

        # Event points and lines
        event_df = timeline_df[timeline_df["Type"] == "Event"]
        fig.add_trace(go.Scatter(
            x=event_df["Date"],
            y=[1] * len(event_df),
            mode="lines+markers+text",
            line=dict(color="blue"),
            marker=dict(size=10),
            text=event_df["Event"],
            textposition="top center",
            name="Events"
        ))

        # Payment point (green tick)
        payment_df = timeline_df[timeline_df["Type"] == "Payment"]
        if not payment_df.empty:
            fig.add_trace(go.Scatter(
                x=payment_df["Date"],
                y=[1] * len(payment_df),
                mode="markers+text",
                marker=dict(size=18, color="green", symbol="check"),
                text=["✔ Payment"],
                textposition="top center",
                name="Payment"
            ))

        fig.update_layout(
            title=f"Timeline for {selected_student}",
            yaxis=dict(visible=False),
            xaxis_title="Date",
            showlegend=True,
            height=450
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No timeline data available for this student.")


if __name__ == "__main__":
    run_streamlit_app()
