# === PG Engagement Analytics App (Error-Free, Sheet-Specific) ===

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="PG Engagement Analytics", layout="wide")

# ----------------------------- HELPERS -----------------------------

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

# ----------------------------- DATA LOADING -----------------------------

def load_pg_sheet(file):
    raw = pd.read_excel(file, sheet_name="PG engagement tracker B2", header=None)

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

    for i, base_col in enumerate(main_headers):
        event_name = event_headers[i]
        event_date = date_headers[i]

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

# ----------------------------- ANALYTICS -----------------------------

def student_participation_analysis(df, event_cols):
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
        .sum()
        .reset_index()
        .rename(columns={"index": "Event", 0: "Participants"})
        .sort_values("Participants", ascending=False)
    )

    return student_participation, event_participation

# ----------------------------- STREAMLIT APP -----------------------------

def run_app():
    st.title("📊 PG Engagement Tracker — B2")

    uploaded_file = st.file_uploader("Upload Master Engagement Tracker Excel", type=["xlsx"])

    if not uploaded_file:
        st.info("Please upload your Excel file.")
        return

    df, event_cols, event_meta_df = load_pg_sheet(uploaded_file)

    st.subheader("📄 Data Preview")
    st.dataframe(df.head())

    # -------- Column Detection --------
    name_col = find_column(df, ["student name", "name"])
    conversion_col = find_column(df, ["conversion status", "conversion"])
    community_col = find_column(df, ["community status", "community"])
    payment_date_col = find_column(df, ["payment date", "payment"])

    # Ensure Student Name exists
    if not name_col:
        st.error("❌ Student Name column not found.")
        return

    # ---------------- PAYMENT & CONVERSION ----------------
    st.header("💰 Payment & Conversion Analysis")

    if conversion_col:
        conv_series = df[conversion_col].astype(str).str.lower()

        paid_mask = conv_series.str.contains("paid|admitted", na=False)
        will_pay_mask = conv_series.str.contains("will pay|will-pay|likely", na=False)
        not_paid_mask = ~(paid_mask | will_pay_mask)

        paid_students = df.loc[paid_mask, [name_col, conversion_col]]
        will_pay_students = df.loc[will_pay_mask, [name_col, conversion_col]]
        not_paid_students = df.loc[not_paid_mask, [name_col, conversion_col]]

        total_students = len(df)
        total_paid = paid_mask.sum()
        total_will_pay = will_pay_mask.sum()
        conversion_rate = round((total_paid / total_students) * 100, 2) if total_students else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Students", total_students)
        col2.metric("Paid / Admitted",
