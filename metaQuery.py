#!/usr/bin/env python

import streamlit as st            # Streamlit for web app
import pandas as pd               # Pandas for data manipulation
import io                         # IO for in-memory file operations
import re                         # Regular expressions for text processing
import base64                     # Base64 for encoding files for download

# Helper functions
@st.cache_data
def load_file(file) -> pd.DataFrame:
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
    elif file.name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(file)
    else:
        raise ValueError("Unsupported file format. Please upload CSV or Excel.")
    df["Source_File"] = file.name
    return df

# Text normalization function for deduplication
def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return text 
    text = text.lower().strip()              # Lowercase and trim
    text = re.sub(r"[_\-]+", " ", text)      # Replace underscores/hyphens with space
    text = re.sub(r"\s+", " ", text)         # Collapse multiple spaces
    text = re.sub(r"[^\w\s()/]", "", text)   # Remove special characters except parentheses and slashes
    return text

# Global text search across all string columns
def text_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if not query:
        return df
    mask = pd.Series(False, index=df.index)
    for col in df.select_dtypes(include=["object", "string"]):
        mask |= df[col].astype(str).str.contains(query, case=False, na=False)
    return df[mask]

# Cell formatting with search term highlighting
def format_cell(value, search_term=None) -> str:
    if pd.isna(value) or str(value).strip().lower() in ["", "nan", "na", "none"]:
        return "<span style='color:red;'>No Definition</span>"
    text = str(value)
    if search_term:
        pattern = re.compile(re.escape(search_term), re.IGNORECASE)
        text = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", text)
    return text

# Redesigned HTML table
def generate_parent_grouped_html(df: pd.DataFrame, search_term=None) -> str:
    parent_col = df.columns[0]
    child_cols = df.columns[1:]

    html = "<table border='1' style='border-collapse:collapse; width:100%; text-align:left;'>"
    html += "<tr>"

    # Table headers with custom widths
    for i, c in enumerate([parent_col] + list(child_cols)):
        if i == 0:
            html += f"<th style='width:20%'>{c}</th>"
        elif i == 1:
            html += f"<th style='width:30%'>{c}</th>"
        elif i == 3:
            html += f"<th style='width:50%'>{c}</th>"
        else:
            html += f"<th>{c}</th>"
    html += "</tr>"

    # Case-insensitive grouping
    df["_group_key"] = df[parent_col].astype(str).str.lower()
    grouped = df.groupby("_group_key", sort=False)

    for _, group in grouped:
        rowspan = group.shape[0]
        original_parent = group.iloc[0][parent_col]
        for i, (_, row) in enumerate(group.iterrows()):
            html += "<tr>"
            if i == 0:
                parent_value = format_cell(original_parent, search_term)
                html += f"<td rowspan='{rowspan}' style='vertical-align: top; font-weight:bold;'>{parent_value}</td>"
            for j, c in enumerate(child_cols):
                cell_value = format_cell(row[c], search_term)
                if j == 0:
                    html += f"<td style='width:30%'>{cell_value}</td>"
                elif j == 2:  # 4th column (0-indexed)
                    html += f"<td style='width:50%'>{cell_value}</td>"
                else:
                    html += f"<td>{cell_value}</td>"
            html += "</tr>"
    html += "</table>"

    df.drop(columns=["_group_key"], inplace=True)
    return html

# Streamlit App
st.set_page_config(page_title="MetaQuery: Grouped Preview", layout="wide")
st.title("MetaQuery: For Metadata Schema Exploration")

uploaded_files = st.file_uploader(
    "Upload one or more files", type=["csv", "xlsx", "xls"], accept_multiple_files=True
)

if uploaded_files:
    dfs = [load_file(file) for file in uploaded_files]
    df_original = pd.concat(dfs, ignore_index=True)
    df_working = df_original.copy()
    total_before = df_working.shape[0]

    # Deduplication
    normalized_df = df_working.copy()
    for col in normalized_df.select_dtypes(include=["object", "string"]).columns:
        normalized_df[col] = normalized_df[col].astype(str).apply(normalize_text)

    if normalized_df.shape[1] > 1:
        second_col = normalized_df.columns[1]
        duplicates_mask = normalized_df.duplicated(subset=[second_col], keep="first")
        keep_mask = ~duplicates_mask
        df = df_working[keep_mask].copy()
        removed_df = df_working[duplicates_mask].copy()
    else:
        st.warning("Dataset has only one column; skipping second-column deduplication.")
        df = df_working.copy()
        removed_df = pd.DataFrame()

    total_after = df.shape[0]
    st.info(f"Total rows before deduplication: {total_before}")
    st.success(f"Total rows after deduplication: {total_after}")
    st.write(f"Rows removed: {total_before - total_after}")

    # Removed Rows Expander
    if not removed_df.empty:
        st.subheader("🗑️ Removed (Deduplicated) Rows")
        with st.expander(f"Show all removed rows (Total: {len(removed_df)})", expanded=False):
            removed_df["_group_key"] = removed_df.iloc[:, 0].astype(str).str.lower()
            grouped_removed = removed_df.groupby("_group_key", sort=False)
            for _, group in grouped_removed:
                display_key = group.iloc[0, 0]
                with st.expander(f"{group.columns[0]}: {display_key} (Count: {len(group)})", expanded=False):
                    st.dataframe(group.drop(columns=["_group_key"]), use_container_width=True)
            removed_df.drop(columns=["_group_key"], inplace=True)

    # Global Search
    st.subheader("Global Search")
    global_search = st.text_input("Search across all text columns:")
    filtered_df = df.copy()
    if global_search:
        filtered_df = text_search(filtered_df, global_search)
    display_cols = [c for c in filtered_df.columns if c not in ["Source_File"]]
    filtered_df = filtered_df[display_cols]

    # Grouped Table Preview
    st.subheader("Filtered Data Preview")
    grouped_html = generate_parent_grouped_html(filtered_df, search_term=global_search)
    st.markdown(grouped_html, unsafe_allow_html=True)

    # Master Expander for Remaining Rows with Checkboxes
    st.markdown("---")
    editable_table = pd.DataFrame()
    if not filtered_df.empty:
        parent_col = filtered_df.columns[0]
        filtered_df["_group_key"] = filtered_df[parent_col].astype(str).str.lower()
        grouped_remaining = filtered_df.groupby("_group_key", sort=False)

        editable_rows = []

        with st.expander(f"Show all grouped data (Total Groups: {len(grouped_remaining)})", expanded=True):
            for _, group in grouped_remaining:
                original_parent = group.iloc[0][parent_col]
                cols_to_hide = [parent_col] + [c for c in group.columns if "definition" in c.lower()]
                display_group = group.drop(columns=cols_to_hide + ["_group_key"], errors="ignore").copy()

                with st.expander(f"{parent_col}: {original_parent} (Count: {len(group)})", expanded=False):
                    display_group["Select"] = False
                    for i, (_, row) in enumerate(display_group.iterrows()):
                        key = f"{original_parent}_{i}"
                        display_group.at[row.name, "Select"] = st.checkbox(str(row.iloc[0]), key=key)
                    editable_rows.append(display_group)

        if editable_rows:
            editable_table = pd.concat(editable_rows, ignore_index=True)

    # Export Section
    st.subheader("Export")
    if not editable_table.empty:
        final_filtered = editable_table[editable_table["Select"] == True].drop(columns=["Select"])
    else:
        final_filtered = pd.DataFrame()

    column_to_export = None
    if not final_filtered.empty:
        for c in final_filtered.columns:
            if c != "Source_File":
                column_to_export = c
                break
    elif not filtered_df.empty:
        for c in filtered_df.columns:
            if c != "Source_File":
                column_to_export = c
                break

    if column_to_export:
        col_data = pd.DataFrame([final_filtered[column_to_export].dropna().tolist()]) if not final_filtered.empty else pd.DataFrame([[]])
    else:
        col_data = pd.DataFrame([[]])

    towrite = io.BytesIO()
    with pd.ExcelWriter(towrite, engine="openpyxl") as writer:
        col_data.to_excel(writer, sheet_name="SelectedColumn", index=False, header=False)
    towrite.seek(0)

    b64 = base64.b64encode(towrite.read()).decode()               
    st.markdown(
        f'''
        <a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" 
           download="new_meta_schema.xlsx" 
           style="text-decoration:none; background-color:#1E90FF; color:white; padding:8px 16px; border-radius:4px;">
           Download
        </a>
        ''',
        unsafe_allow_html=True
    )

else:
    st.info("Please upload at least one CSV or Excel file to get started.")
metaQuery.app README.md
