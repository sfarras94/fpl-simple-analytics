import streamlit as st
import pandas as pd
import json
import requests
import base64
import os

# =========================================================
# BACKGROUND IMAGE
# =========================================================
def set_background(image_file):
    with open(image_file, "rb") as f:
        data = f.read()
        base64_image = base64.b64encode(data).decode()

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{base64_image}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }}

        .main-container {{
            background: rgba(255,255,255,0.85);
            padding: 20px;
            border-radius: 15px;
        }}

        .block-container {{
            padding-left: 3rem !important;
            padding-right: 3rem !important;
            max-width: 2000px !important;
        }}

        /* Hide table index */
        .row_heading.level0 {{display:none}}
        .blank {{display:none}}
        </style>
        """,
        unsafe_allow_html=True
    )

IMAGE_PATH = r"C:\Users\samfa\Documents\fpl-analytics-project\bg1.png"
set_background(IMAGE_PATH)

# =========================================================
# LOAD LOCAL CACHE FILES
# =========================================================
CACHE_DIR = "cache"
PLAYERS_FILE = os.path.join(CACHE_DIR, "players.json")
WEEKLY_FILE = os.path.join(CACHE_DIR, "weekly.json")


@st.cache_data
def load_players():
    """Load players.json (bootstrap-static format)."""
    with open(PLAYERS_FILE, "r") as f:
        data = json.load(f)

    df = pd.DataFrame(data["elements"])
    teams = pd.DataFrame(data["teams"])[["id", "name"]].rename(
        columns={"id": "team", "name": "Team"}
    )

    df = df.merge(teams, on="team", how="left")

    # Map positions
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["Position"] = df["element_type"].map(pos_map)

    # Convert cost to real price
    df["Current Price"] = df["now_cost"] / 10

    # Points per million
    df["Points Per Million"] = df["total_points"] / df["Current Price"]

    # Convert selected %
    df["Selected By (Decimal)"] = pd.to_numeric(df["selected_by_percent"], errors="coerce") / 100
    df["Selected By %"] = df["Selected By (Decimal)"] * 100  # For display

    # Template & Differential values
    df["Template Value"] = df["Points Per Million"] * df["Selected By (Decimal)"]
    df["Differential Value"] = df["Points Per Million"] * (1 - df["Selected By (Decimal)"])

    return df


@st.cache_data
def load_weekly():
    with open(WEEKLY_FILE, "r") as f:
        return json.load(f)


players = load_players()
weekly = load_weekly()

# =========================================================
# SIDEBAR FILTERS
# =========================================================
st.sidebar.title("🔍 Filters")

team_filter = st.sidebar.selectbox(
    "Team",
    ["All Teams"] + sorted(players["Team"].unique())
)

position_filter = st.sidebar.selectbox(
    "Position",
    ["All", "GK", "DEF", "MID", "FWD"]
)

# Gameweek slider
weekly_df = pd.concat(
    [pd.DataFrame(v) for v in weekly.values()],
    ignore_index=True
)

min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())

gw_start, gw_end = st.sidebar.slider(
    "Gameweek Range",
    min_value=min_gw,
    max_value=max_gw,
    value=(min_gw, max_gw),
)

# Sorting dropdown
sort_column = st.sidebar.selectbox(
    "Sort Table By",
    [
        "Points (GW Range)",
        "Current Price",
        "Points Per Million",
        "Selected By %",
        "Template Value",
        "Differential Value"
    ]
)

sort_order = st.sidebar.radio("Sort Order", ["Descending", "Ascending"])

# =========================================================
# FILTER DATA
# =========================================================
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]

# =========================================================
# GW RANGE POINT CALCULATION
# =========================================================
def get_points_for_range(player_id, gw1, gw2):
    history = weekly.get(str(player_id), [])
    if not history:
        return 0
    df = pd.DataFrame(history)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
    return df["total_points"].sum()


filtered["Points (GW Range)"] = filtered.apply(
    lambda row: get_points_for_range(row["id"], gw_start, gw_end),
    axis=1
)

# =========================================================
# FINAL TABLE FORMAT
# =========================================================
table = filtered[[
    "web_name",
    "Team",
    "Position",
    "Points (GW Range)",
    "Current Price",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value"
]]

table = table.rename(columns={"web_name": "Player"})

# Round values
round_cols = [
    "Current Price",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value"
]

for col in round_cols:
    table[col] = table[col].round(2)

# Sort the table
ascending = (sort_order == "Ascending")
table = table.sort_values(by=sort_column, ascending=ascending)

# =========================================================
# PAGE CONTENT
# =========================================================
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Analytics Dashboard")
st.write("Using cached local data for instant loading.")

st.subheader("📊 Player Value Table")
st.dataframe(table, use_container_width=True, hide_index=True)

st.markdown("</div>", unsafe_allow_html=True)
