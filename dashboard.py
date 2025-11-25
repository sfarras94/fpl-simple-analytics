import streamlit as st
import pandas as pd
import json
import base64
import os

# -----------------------------------------
# BACKGROUND IMAGE
# -----------------------------------------
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

IMAGE_PATH = "bg1.png"   # Ensure bg1.png exists in repo root
set_background(IMAGE_PATH)


# -----------------------------------------
# LOAD LOCAL CACHE FILES
# -----------------------------------------
CACHE_DIR = "cache"
PLAYERS_FILE = os.path.join(CACHE_DIR, "players.json")
WEEKLY_FILE = os.path.join(CACHE_DIR, "weekly.json")


@st.cache_data
def load_players():
    with open(PLAYERS_FILE, "r") as f:
        data = json.load(f)

    df = pd.DataFrame(data["elements"])
    teams = pd.DataFrame(data["teams"])[["id", "name"]].rename(
        columns={"id": "team", "name": "Team"}
    )

    df = df.merge(teams, on="team", how="left")

    # Position map
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["Position"] = df["element_type"].map(pos_map)

    # Pricing
    df["Current Price"] = df["now_cost"] / 10

    # Season-long PPM (we override with GW-range later)
    df["Points Per Million"] = df["total_points"] / df["Current Price"]

    # Selection %
    df["Selected By (Decimal)"] = pd.to_numeric(
        df["selected_by_percent"], errors="coerce"
    ) / 100
    df["Selected By %"] = df["Selected By (Decimal)"] * 100

    # Template & differential (season-based)
    df["Template Value"] = df["Points Per Million"] * df["Selected By (Decimal)"]
    df["Differential Value"] = df["Points Per Million"] * (
        1 - df["Selected By (Decimal)"]
    )

    return df


@st.cache_data
def load_weekly():
    with open(WEEKLY_FILE, "r") as f:
        return json.load(f)


players = load_players()
weekly = load_weekly()

# -----------------------------------------
# BUILD WEEKLY DF FOR SLIDER LIMITS
# -----------------------------------------
weekly_df = pd.concat(
    [pd.DataFrame(v) for v in weekly.values()],
    ignore_index=True
)

min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())


# -----------------------------------------
# SIDEBAR FILTERS + RESET BUTTON
# -----------------------------------------
st.sidebar.title("🔍 Filters")

# 🔄 Reset button at the very top of sidebar
reset_clicked = st.sidebar.button("🔄 Reset All Filters")

# Filters (values also stored in st.session_state via keys)
team_filter = st.sidebar.selectbox(
    "Team",
    ["All Teams"] + sorted(players["Team"].unique()),
    key="team_filter"
)

position_filter = st.sidebar.selectbox(
    "Position",
    ["All", "GK", "DEF", "MID", "FWD"],
    key="position_filter"
)

gw_start, gw_end = st.sidebar.slider(
    "Gameweek Range",
    min_value=min_gw,
    max_value=max_gw,
    value=(min_gw, max_gw),
    key="gw_slider"
)

sort_column = st.sidebar.selectbox(
    "Sort Table By",
    [
        "Points (GW Range)",
        "Current Price",
        "Points Per Million",
        "Selected By %",
        "Template Value",
        "Differential Value"
    ],
    key="sort_column"
)

sort_order = st.sidebar.radio(
    "Sort Order",
    ["Descending", "Ascending"],
    key="sort_order"
)

selected_player = st.sidebar.selectbox(
    "View Player Details",
    ["None"] + sorted(players["web_name"].unique()),
    key="selected_player"
)

# If reset is clicked, overwrite session_state and rerun
if reset_clicked:
    st.session_state.team_filter = "All Teams"
    st.session_state.position_filter = "All"
    st.session_state.gw_slider = (min_gw, max_gw)
    st.session_state.sort_column = "Points (GW Range)"
    st.session_state.sort_order = "Descending"
    st.session_state.selected_player = "None"
    st.experimental_rerun()


# -----------------------------------------
# FILTER BASE TABLE
# -----------------------------------------
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]


# -----------------------------------------
# GAMEWEEK-RANGE POINT CALCULATION
# -----------------------------------------
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


# -----------------------------------------
# FINAL TABLE
# -----------------------------------------
table = filtered[[
    "web_name",
    "Team",
    "Position",
    "Points (GW Range)",
    "Current Price",
    "Selected By %"
]].rename(columns={"web_name": "Player"})

# Recalculate dynamic metrics based on GW-range points
table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]

sel_decimal = table["Selected By %"] / 100
table["Template Value"] = table["Points Per Million"] * sel_decimal
table["Differential Value"] = table["Points Per Million"] * (1 - sel_decimal)

# Round numbers
round_cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value"
]

table[round_cols] = table[round_cols].round(2)

# Sorting
ascending = (sort_order == "Ascending")
table = table.sort_values(by=sort_column, ascending=ascending)


# -----------------------------------------
# PLAYER DETAIL PANEL
# -----------------------------------------
if selected_player != "None":

    player_name = selected_player
    st.subheader(f"📌 Detailed FPL Breakdown — {player_name}")

    pid = int(players[players["web_name"] == player_name]["id"].iloc[0])
    history = weekly.get(str(pid), [])

    if history:
        df_hist = pd.DataFrame(history)

        st.markdown("### 🔍 Season Summary")
        st.write(players[players["web_name"] == player_name][[
            "Team", "Position", "Current Price", "Selected By %"
        ]])

        st.markdown("### 📊 Points Breakdown by Gameweek")
        st.dataframe(
            df_hist[[
                "round",
                "total_points",
                "goals_scored",
                "assists",
                "clean_sheets",
                "bonus",
                "minutes",
                "expected_goals",
                "expected_assists",
                "expected_goal_involvements"
            ]].sort_values("round"),
            use_container_width=True
        )

        import plotly.express as px
        fig = px.line(
            df_hist,
            x="round",
            y="total_points",
            markers=True,
            title=f"Points per GW — {player_name}",
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No weekly data available for this player.")


# -----------------------------------------
# PAGE CONTENT
# -----------------------------------------
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Analytics Dashboard")
st.write("Using cached local data for instant loading.")

st.subheader("📊 Player Value Table")
st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Player": st.column_config.TextColumn("Player"),
        "Team": st.column_config.TextColumn("Team"),
        "Position": st.column_config.TextColumn("Position"),
        "Points (GW Range)": st.column_config.NumberColumn("Points (GW Range)"),
        "Current Price": st.column_config.NumberColumn("Price (£m)"),
        "Points Per Million": st.column_config.NumberColumn("PPM"),
        "Selected By %": st.column_config.NumberColumn("Selected %"),
        "Template Value": st.column_config.NumberColumn("Template Value"),
        "Differential Value": st.column_config.NumberColumn("Differential Value"),
    }
)

st.markdown("</div>", unsafe_allow_html=True)
