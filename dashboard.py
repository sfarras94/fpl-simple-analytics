import streamlit as st
import pandas as pd
import json
import base64
import os

# -----------------------------------------
# Session State Defaults
# -----------------------------------------
if "selected_player" not in st.session_state:
    st.session_state.selected_player = "None"


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


IMAGE_PATH = "bg1.png"
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

    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["Position"] = df["element_type"].map(pos_map)

    df["Current Price"] = df["now_cost"] / 10
    df["Points Per Million"] = df["total_points"] / df["Current Price"]

    df["Selected By (Decimal)"] = pd.to_numeric(df["selected_by_percent"], errors="coerce") / 100
    df["Selected By %"] = df["Selected By (Decimal)"] * 100

    df["Template Value"] = df["Points Per Million"] * df["Selected By (Decimal)"]
    df["Differential Value"] = df["Points Per Million"] * (1 - df["Selected By (Decimal)"])

    return df


@st.cache_data
def load_weekly():
    with open(WEEKLY_FILE, "r") as f:
        return json.load(f)


players = load_players()
weekly = load_weekly()

# -----------------------------------------
# WEEKLY RANGE LIMIT BUILD
# -----------------------------------------
weekly_df = pd.concat(
    [pd.DataFrame(v) for v in weekly.values()],
    ignore_index=True
)

min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())


# -----------------------------------------
# SIDEBAR FILTERS
# -----------------------------------------
st.sidebar.title("🔍 Filters")

# Reset-all button BEFORE widgets so rerun doesn't break keys
if st.sidebar.button("🔄 Reset All Filters"):
    st.session_state.clear()
    st.session_state.selected_player = "None"
    st.rerun()

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


# -----------------------------------------
# FILTER DATA
# -----------------------------------------
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]


# -----------------------------------------
# GW RANGE POINT CALCULATION
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
# FINAL TABLE FORMAT
# -----------------------------------------
table = filtered[[
    "web_name",
    "Team",
    "Position",
    "Points (GW Range)",
    "Current Price",
    "Selected By %"
]].rename(columns={"web_name": "Player"})

table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]

sel_decimal = table["Selected By %"] / 100
table["Template Value"] = table["Points Per Million"] * sel_decimal
table["Differential Value"] = table["Points Per Million"] * (1 - sel_decimal)

round_cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value"
]

table[round_cols] = table[round_cols].round(2)

ascending = (sort_order == "Ascending")
table = table.sort_values(by=sort_column, ascending=ascending)


# -----------------------------------------
# DEFENSIVE CONTRIBUTION LOGIC (FPL ACCURATE)
# -----------------------------------------
def calculate_def_contribution_points(df, position):
    """Apply official FPL defensive contribution rules."""
    total = 0

    for _, row in df.iterrows():
        dc = row.get("defensive_contribution", 0)

        if position == "DEF" and dc >= 10:
            total += 2
        elif position in ["MID", "FWD"] and dc >= 12:
            total += 2
        # GK always 0

    return total


# -----------------------------------------
# PLAYER DETAIL VIEW
# -----------------------------------------
if selected_player != "None":

    player_name = selected_player
    position = players.loc[players["web_name"] == player_name, "Position"].iloc[0]
    pid = int(players.loc[players["web_name"] == player_name, "id"].iloc[0])

    history = weekly.get(str(pid), [])
    df_hist = pd.DataFrame(history)
    df_range = df_hist[(df_hist["round"] >= gw_start) & (df_hist["round"] <= gw_end)]

    # Drop expected stats
    df_range = df_range.drop(columns=[
        "expected_goals",
        "expected_assists",
        "expected_goal_involvements",
    ], errors="ignore")

    # Rename columns
    df_range = df_range.rename(columns={
        "round": "Gameweek",
        "total_points": "Points",
        "goals_scored": "Goals",
        "assists": "Assists",
        "clean_sheets": "Clean Sheets",
        "goals_conceded": "Goals Conceded",
        "bonus": "Bonus",
        "minutes": "Minutes",
        "yellow_cards": "Yellow Cards",
        "red_cards": "Red Cards",
        "saves": "Saves",
    })

    # Conditional defensive/saves visibility
    if position != "GK":
        df_range = df_range.drop(columns=["Saves"], errors="ignore")

    if position not in ["GK", "DEF"]:
        df_range = df_range.drop(columns=["Goals Conceded"], errors="ignore")

    if position == "FWD":
        df_range = df_range.drop(columns=["Clean Sheets"], errors="ignore")

    # -----------------------------------------
    # FPL POINTS BREAKDOWN
    # -----------------------------------------
    # Minutes logic
    mins = df_range["Minutes"]
    mins_60 = (mins >= 60).sum()
    mins_sub = ((mins > 0) & (mins < 60)).sum()

    # Goal values by position
    goal_values = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}

    # Goals/Assists
    goals = df_range["Goals"].sum() if "Goals" in df_range else 0
    assists = df_range["Assists"].sum() if "Assists" in df_range else 0

    # Clean sheets
    if position == "GK":
        clean_sheet_points = (df_range["Clean Sheets"] >= 1).sum() * 4
    elif position == "DEF":
        clean_sheet_points = (df_range["Clean Sheets"] >= 1).sum() * 4
    elif position == "MID":
        clean_sheet_points = (df_range["Clean Sheets"] >= 1).sum() * 1
    else:
        clean_sheet_points = 0

    # Saves
    saves_points = 0
    if position == "GK" and "Saves" in df_range:
        saves_points = (df_range["Saves"].sum() // 3) * 1

    # Goals conceded (GK/DEF)
    conceded_points = 0
    if position in ["GK", "DEF"] and "Goals Conceded" in df_range:
        conceded_points = -1 * (df_range["Goals Conceded"].sum() // 2)

    # Cards
    yc_points = -1 * df_range["Yellow Cards"].sum() if "Yellow Cards" in df_range else 0
    rc_points = -3 * df_range["Red Cards"].sum() if "Red Cards" in df_range else 0

    # Bonus
    bonus_points = df_range["Bonus"].sum() if "Bonus" in df_range else 0

    # Defensive contributions
    def_points = calculate_def_contribution_points(df_hist, position)

    # Total points per category
    breakdown_points = {
        "Goals": goals * goal_values[position],
        "Assists": assists * 3,
        "Clean Sheets": clean_sheet_points,
        "Minutes ≥60": mins_60 * 2,
        "Minutes <60": mins_sub * 1,
        "Saves": saves_points,
        "Goals Conceded": conceded_points,
        "Bonus": bonus_points,
        "Yellow Cards": yc_points,
        "Red Cards": rc_points,
        "Defensive Contributions": def_points,
    }

    total_points = sum(breakdown_points.values())

    # Convert to DataFrame
    breakdown_df = pd.DataFrame({
        "Category": breakdown_points.keys(),
        "Total Points": breakdown_points.values(),
        "Percent %": [round((v / total_points) * 100, 1) if total_points != 0 else 0
                      for v in breakdown_points.values()]
    })

    st.subheader(f"📌 FPL Points Contribution (GW {gw_start}-{gw_end}) — {player_name}")
    st.dataframe(breakdown_df, hide_index=True, use_container_width=True)

    # -----------------------------------------
    # GAMEWEEK BREAKDOWN TABLE
    # -----------------------------------------
    st.subheader(f"📊 Points Breakdown by Gameweek (GW {gw_start}-{gw_end})")
    st.dataframe(df_range, hide_index=True, use_container_width=True)


# -----------------------------------------
# PAGE CONTENT
# -----------------------------------------
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Analytics Dashboard")
st.write("Using cached local data for instant loading.")

st.subheader("📊 Player Value Table")
st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
)

st.markdown("</div>", unsafe_allow_html=True)
