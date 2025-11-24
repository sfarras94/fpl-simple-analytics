import streamlit as st
import pandas as pd
import json
import base64
import os

# =========================================================
# SESSION STATE DEFAULTS
# =========================================================
if "selected_player" not in st.session_state:
    st.session_state.selected_player = "None"

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

IMAGE_PATH = "bg1.png"
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

    # Points per million (season total – we’ll override per GW range later)
    df["Points Per Million"] = df["total_points"] / df["Current Price"]

    # Convert selected % to decimal and display %
    df["Selected By (Decimal)"] = pd.to_numeric(
        df["selected_by_percent"], errors="coerce"
    ) / 100
    df["Selected By %"] = df["Selected By (Decimal)"] * 100  # For display

    # Template & Differential values (season-based, overridden later for GW range)
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

# =========================================================
# PREP WEEKLY RANGE (for slider)
# =========================================================
weekly_df = pd.concat(
    [pd.DataFrame(v) for v in weekly.values()],
    ignore_index=True
)

min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())

# =========================================================
# SIDEBAR FILTERS
# =========================================================
st.sidebar.title("🔍 Filters")

# Team filter
team_filter = st.sidebar.selectbox(
    "Team",
    ["All Teams"] + sorted(players["Team"].unique()),
    key="team_filter"
)

# Position filter
position_filter = st.sidebar.selectbox(
    "Position",
    ["All", "GK", "DEF", "MID", "FWD"],
    key="position_filter"
)

# Gameweek slider
gw_start, gw_end = st.sidebar.slider(
    "Gameweek Range",
    min_value=min_gw,
    max_value=max_gw,
    value=(min_gw, max_gw),
    key="gw_slider"
)

# Sorting dropdowns
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

# Player selection
selected_player = st.sidebar.selectbox(
    "View Player Details",
    ["None"] + sorted(players["web_name"].unique()),
    key="selected_player"
)

# -----------------------------
# ✅ Reset button MUST come LAST
# -----------------------------
if st.sidebar.button("🔄 Reset All Filters"):
    st.session_state.team_filter = "All Teams"
    st.session_state.position_filter = "All"
    st.session_state.gw_slider = (min_gw, max_gw)
    st.session_state.sort_column = "Points (GW Range)"
    st.session_state.sort_order = "Descending"
    st.session_state.selected_player = "None"
    st.rerun()


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
# FINAL TABLE FORMAT (GW RANGE-BASED METRICS)
# =========================================================
table = filtered[[
    "web_name",
    "Team",
    "Position",
    "Points (GW Range)",
    "Current Price",
    "Selected By %"
]].rename(columns={"web_name": "Player"})

# Recalculate all value metrics based on GW-range points
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

# Sort the table
ascending = (sort_order == "Ascending")
table = table.sort_values(by=sort_column, ascending=ascending)

# =========================================================
# PLAYER DETAIL PANEL
# =========================================================
if selected_player != "None":

    st.subheader(f"📌 Detailed FPL Breakdown — {selected_player}")

    # Get player ID
    pid = int(players[players["web_name"] == selected_player]["id"].iloc[0])
    history = weekly.get(str(pid), [])

    if history:
        df_hist = pd.DataFrame(history)

        # Season summary
        st.markdown("### 🔍 Season Summary")
        st.write(
            players[players["web_name"] == selected_player][[
                "Team", "Position", "Current Price", "Selected By %"
            ]]
        )

        # Points breakdown table
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

        # Points per GW chart
        import plotly.express as px
        fig = px.line(
            df_hist,
            x="round",
            y="total_points",
            markers=True,
            title=f"Points per GW — {selected_player}",
        )
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No weekly data available for this player.")

# =========================================================
# PAGE CONTENT
# =========================================================
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Analytics Dashboard")
st.write("Using cached local data for instant loading.")

st.subheader("📊 Player Value Table")
st.dataframe(
    table,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Player": st.column_config.TextColumn(
            "Player",
            help="Player’s short name (web_name from FPL API)"
        ),
        "Team": st.column_config.TextColumn(
            "Team",
            help="Premier League team"
        ),
        "Position": st.column_config.TextColumn(
            "Pos",
            help="GK, DEF, MID, or FWD"
        ),
        "Points (GW Range)": st.column_config.NumberColumn(
            "Points (GW Range)",
            help="Total FPL points earned by the player between selected gameweeks"
        ),
        "Current Price": st.column_config.NumberColumn(
            "Price (£m)",
            help="Player’s cost in millions (FPL now_cost / 10)"
        ),
        "Points Per Million": st.column_config.NumberColumn(
            "PPM",
            help="Points (GW Range) divided by current price. A key measure of value."
        ),
        "Selected By %": st.column_config.NumberColumn(
            "Selected %",
            help="Percentage of FPL managers who own this player"
        ),
        "Template Value": st.column_config.NumberColumn(
            "Template Value",
            help="PPM × Selected %. Higher = template pick"
        ),
        "Differential Value": st.column_config.NumberColumn(
            "Differential Value",
            help="PPM × (1 – Selected %). Higher = differential pick"
        ),
    }
)

st.markdown("</div>", unsafe_allow_html=True)

