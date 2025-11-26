import streamlit as st
import pandas as pd
import json
import base64
import os
import plotly.express as px

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

    # Position map
    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    df["Position"] = df["element_type"].map(pos_map)

    # Pricing
    df["Current Price"] = df["now_cost"] / 10
    df["Points Per Million"] = df["total_points"] / df["Current Price"]

    # Selection %
    df["Selected By (Decimal)"] = pd.to_numeric(df["selected_by_percent"], errors="coerce") / 100
    df["Selected By %"] = df["Selected By (Decimal)"] * 100

    # Template & differential (season-level, for base table)
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
# FPL BREAKDOWN LOGIC (per GW, with DC + penalties + cards + OG)
# -----------------------------------------
def calculate_fpl_breakdown(df_match: pd.DataFrame, position: str):
    """
    Compute FPL points by category over a set of matches (df_match),
    using official scoring rules and respecting gameweek range.
    """
    totals = {
        "Goals": 0,
        "Assists": 0,
        "Clean Sheets": 0,
        "Minutes ≥60": 0,
        "Minutes <60": 0,
        "Saves": 0,
        "Penalties Saved": 0,
        "Penalties Missed": 0,
        "Goals Conceded": 0,
        "Bonus": 0,
        "Yellow Cards": 0,
        "Red Cards": 0,
        "Own Goals": 0,
        "Defensive Contributions": 0,
    }

    goal_values = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}

    for _, row in df_match.iterrows():
        minutes = row.get("minutes", 0) or 0
        goals = row.get("goals_scored", 0) or 0
        assists = row.get("assists", 0) or 0
        clean_sheets = row.get("clean_sheets", 0) or 0
        goals_conceded = row.get("goals_conceded", 0) or 0
        saves = row.get("saves", 0) or 0
        pens_saved = row.get("penalties_saved", 0) or 0
        pens_missed = row.get("penalties_missed", 0) or 0
        yc = row.get("yellow_cards", 0) or 0
        rc = row.get("red_cards", 0) or 0
        own_goals = row.get("own_goals", 0) or 0
        bonus = row.get("bonus", 0) or 0
        dc = row.get("defensive_contribution", 0) or 0

        # Minutes
        if minutes >= 60:
            totals["Minutes ≥60"] += 2
        elif 0 < minutes < 60:
            totals["Minutes <60"] += 1

        # Goals
        if goals:
            value = goal_values.get(position, 0)
            totals["Goals"] += goals * value

        # Assists
        if assists:
            totals["Assists"] += assists * 3

        # Clean sheets: need 60+ mins for CS points
        if minutes >= 60 and clean_sheets > 0:
            if position in ["GK", "DEF"]:
                totals["Clean Sheets"] += 4
            elif position == "MID":
                totals["Clean Sheets"] += 1

        # Saves (GK only)
        if position == "GK" and saves:
            totals["Saves"] += (saves // 3) * 1

        # Penalties saved (GK only)
        if position == "GK" and pens_saved:
            totals["Penalties Saved"] += pens_saved * 5

        # Penalties missed (any position)
        if pens_missed:
            totals["Penalties Missed"] += pens_missed * -2

        # Goals conceded (GK/DEF, per 2 conceded)
        if position in ["GK", "DEF"] and goals_conceded and minutes > 0:
            totals["Goals Conceded"] += -1 * (goals_conceded // 2)

        # Bonus
        if bonus:
            totals["Bonus"] += bonus

        # Cards
        if yc:
            totals["Yellow Cards"] += -1 * yc
        if rc:
            totals["Red Cards"] += -3 * rc

        # Own goals
        if own_goals:
            totals["Own Goals"] += -2 * own_goals

        # Defensive contributions: capped at +2 per match
        if position == "DEF" and dc >= 10:
            totals["Defensive Contributions"] += 2
        elif position in ["MID", "FWD"] and dc >= 12:
            totals["Defensive Contributions"] += 2
        # GK gets 0 from DC

    # Compare with actual total_points
    real_total = df_match["total_points"].sum()
    calc_total = sum(totals.values())
    diff = real_total - calc_total

    if abs(diff) != 0:
        totals["Other / Uncaptured"] = diff

    return totals, real_total


def build_player_view(player_name: str, gw_start: int, gw_end: int):
    """
    Build the per-player data needed for the modal:
    - Season meta
    - GW-range history
    - FPL contribution breakdown
    """
    player_row = players[players["web_name"] == player_name].iloc[0]
    pid = int(player_row["id"])
    position = player_row["Position"]

    history = weekly.get(str(pid), [])
    df_hist = pd.DataFrame(history)

    df_range_raw = df_hist[(df_hist["round"] >= gw_start) & (df_hist["round"] <= gw_end)].copy()

    if df_range_raw.empty:
        return {
            "name": player_name,
            "position": position,
            "team": player_row["Team"],
            "price": player_row["Current Price"],
            "selected": player_row["Selected By %"],
            "has_data": False,
        }

    breakdown_points, total_points = calculate_fpl_breakdown(df_range_raw, position)
    breakdown_df = pd.DataFrame({
        "Category": list(breakdown_points.keys()),
        "Total Points": list(breakdown_points.values()),
    })
    breakdown_df["Percent %"] = [
        round((v / total_points) * 100, 1) if total_points != 0 else 0
        for v in breakdown_df["Total Points"]
    ]

    # Build display GW-range df
    df_range = df_range_raw.copy()
    df_range = df_range.drop(columns=[
        "expected_goals",
        "expected_assists",
        "expected_goal_involvements",
    ], errors="ignore")

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

    # Conditional display columns
    if position != "GK":
        df_range = df_range.drop(columns=["Saves"], errors="ignore")
    if position not in ["GK", "DEF"]:
        df_range = df_range.drop(columns=["Goals Conceded"], errors="ignore")
    if position == "FWD":
        df_range = df_range.drop(columns=["Clean Sheets"], errors="ignore")

    return {
        "name": player_name,
        "position": position,
        "team": player_row["Team"],
        "price": player_row["Current Price"],
        "selected": player_row["Selected By %"],
        "has_data": True,
        "total_points": total_points,
        "breakdown_df": breakdown_df,
        "gw_df": df_range.sort_values("Gameweek"),
        "raw_hist": df_range_raw.sort_values("round"),
    }


# -----------------------------------------
# PLAYER MODAL (Option 3)
# -----------------------------------------
@st.dialog("Player Analysis", width="large")
def player_modal(player_a_name: str, player_b_name: str | None, gw_start: int, gw_end: int):
    col_title1, col_title2 = st.columns(2)
    with col_title1:
        st.markdown(f"### 🎯 {player_a_name} (GW {gw_start}-{gw_end})")
    if player_b_name:
        with col_title2:
            st.markdown(f"### ⚔️ {player_b_name} (GW {gw_start}-{gw_end})")

    # Build data
    a_data = build_player_view(player_a_name, gw_start, gw_end)
    b_data = build_player_view(player_b_name, gw_start, gw_end) if player_b_name else None

    # === Summary cards ===
    cols = st.columns(2 if b_data else 1)

    with cols[0]:
        st.markdown(f"#### {a_data['name']} — {a_data['team']} ({a_data['position']})")
        st.metric("Price (£m)", value=round(a_data["price"], 1))
        st.metric("Selected By %", value=f"{a_data['selected']:.1f}%")
        if a_data.get("has_data", False):
            st.metric("Total Points (GW range)", value=int(a_data["total_points"]))

    if b_data:
        with cols[1]:
            if not b_data.get("has_data", False):
                st.markdown(f"#### {b_data['name']} — {b_data['team']} ({b_data['position']})")
                st.write("No match data in this gameweek range.")
            else:
                st.markdown(f"#### {b_data['name']} — {b_data['team']} ({b_data['position']})")
                st.metric("Price (£m)", value=round(b_data["price"], 1))
                st.metric("Selected By %", value=f"{b_data['selected']:.1f}%")
                st.metric("Total Points (GW range)", value=int(b_data["total_points"]))

    st.markdown("---")

    # === Points Contribution tables ===
    st.markdown("### 🧮 FPL Points Contribution (by category)")

    cols2 = st.columns(2 if b_data else 1)

    if a_data.get("has_data", False):
        with cols2[0]:
            st.markdown(f"**{a_data['name']}**")
            st.dataframe(
                a_data["breakdown_df"],
                hide_index=True,
                use_container_width=True,
            )
    else:
        with cols2[0]:
            st.write("No match data for this player in the selected range.")

    if b_data and b_data.get("has_data", False):
        with cols2[1]:
            st.markdown(f"**{b_data['name']}**")
            st.dataframe(
                b_data["breakdown_df"],
                hide_index=True,
                use_container_width=True,
            )

    st.markdown("---")

    # === Line charts of points per GW ===
    st.markdown("### 📈 Points per Gameweek")

    cols3 = st.columns(2 if b_data else 1)

    if a_data.get("has_data", False):
        with cols3[0]:
            fig_a = px.line(
                a_data["raw_hist"],
                x="round",
                y="total_points",
                markers=True,
                title=f"Points per GW — {a_data['name']}",
            )
            st.plotly_chart(fig_a, use_container_width=True)

    if b_data and b_data.get("has_data", False):
        with cols3[1]:
            fig_b = px.line(
                b_data["raw_hist"],
                x="round",
                y="total_points",
                markers=True,
                title=f"Points per GW — {b_data['name']}",
            )
            st.plotly_chart(fig_b, use_container_width=True)

    st.markdown("---")

    # === GW breakdown tables ===
    st.markdown("### 📊 Points Breakdown by Gameweek")

    cols4 = st.columns(2 if b_data else 1)

    if a_data.get("has_data", False):
        with cols4[0]:
            st.markdown(f"**{a_data['name']}** — GW breakdown")
            st.dataframe(a_data["gw_df"], hide_index=True, use_container_width=True)

    if b_data and b_data.get("has_data", False):
        with cols4[1]:
            st.markdown(f"**{b_data['name']}** — GW breakdown")
            st.dataframe(b_data["gw_df"], hide_index=True, use_container_width=True)


# -----------------------------------------
# SIDEBAR FILTERS
# -----------------------------------------
st.sidebar.title("🔍 Filters")

# Reset-all button FIRST
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

# Player A + optional comparison player
player_a = st.sidebar.selectbox(
    "Player A (Primary)",
    ["None"] + sorted(players["web_name"].unique()),
    key="player_a"
)

compare_toggle = st.sidebar.checkbox(
    "Compare with another player",
    value=False,
    key="compare_toggle"
)

player_b = None
if compare_toggle:
    player_b = st.sidebar.selectbox(
        "Player B (Comparison)",
        ["None"] + sorted(players["web_name"].unique()),
        key="player_b"
    )
    if player_b == "None":
        player_b = None

# Button to open the modal
if st.sidebar.button("Open Player View"):
    if player_a != "None":
        player_modal(player_a, player_b, gw_start, gw_end)
    else:
        st.sidebar.warning("Please select at least Player A before opening the view.")


# -----------------------------------------
# FILTER DATA FOR MAIN TABLE
# -----------------------------------------
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]


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
