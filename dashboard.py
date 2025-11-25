import streamlit as st
import pandas as pd
import json
import base64
import os
import plotly.express as px

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

    # Template & differential (season-based baseline)
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
# SIDEBAR FILTERS + RESET LOGIC
# -----------------------------------------
st.sidebar.title("🔍 Filters")

# Reset flag in session state
if "reset_triggered" not in st.session_state:
    st.session_state.reset_triggered = False

# 🔄 Reset button FIRST, before widgets
if st.sidebar.button("🔄 Reset All Filters"):
    st.session_state.reset_triggered = True
    st.rerun()

# If reset was triggered, reset all filter-related state and rerun
if st.session_state.reset_triggered:
    st.session_state.team_filter = "All Teams"
    st.session_state.position_filter = "All"
    st.session_state.gw_slider = (min_gw, max_gw)
    st.session_state.sort_column = "Points (GW Range)"
    st.session_state.sort_order = "Descending"
    st.session_state.selected_player = "None"
    st.session_state.reset_triggered = False
    st.rerun()

# Now safely create all widgets
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
# PLAYER DETAIL PANEL (GW-RANGE BREAKDOWN)
# -----------------------------------------
if selected_player != "None":

    player_name = selected_player
    st.subheader(f"📌 Detailed FPL Breakdown — {player_name} (GW {gw_start}–{gw_end})")

    # Get player row & ID
    player_row = players[players["web_name"] == player_name].iloc[0]
    pid = int(player_row["id"])
    position = player_row["Position"]

    history = weekly.get(str(pid), [])

    if history:
        df_hist = pd.DataFrame(history)

        # Restrict to GW range
        df_range = df_hist[
            (df_hist["round"] >= gw_start) & (df_hist["round"] <= gw_end)
        ].copy()

        if df_range.empty:
            st.info(f"No games for {player_name} between GW {gw_start} and {gw_end}.")
        else:
            # ---- Aggregate Stats for GW Range ----
            total_points_range = df_range["total_points"].sum()

            goals = df_range["goals_scored"].sum()
            assists = df_range["assists"].sum()
            clean_sheets = df_range["clean_sheets"].sum()
            goals_conceded = df_range["goals_conceded"].sum()
            own_goals = df_range["own_goals"].sum()
            pens_saved = df_range["penalties_saved"].sum()
            pens_missed = df_range["penalties_missed"].sum()
            yellow_cards = df_range["yellow_cards"].sum()
            red_cards = df_range["red_cards"].sum()
            saves = df_range["saves"].sum()
            bonus = df_range["bonus"].sum()
            def_contrib = df_range["defensive_contribution"].sum()
            minutes_series = df_range["minutes"]

            apps_60 = ((minutes_series >= 60)).sum()
            apps_sub = ((minutes_series > 0) & (minutes_series < 60)).sum()

            # ---- FPL Scoring Rules ----
            # Goals
            if position == "GK":
                goal_points_per = 10
            elif position == "DEF":
                goal_points_per = 6
            elif position == "MID":
                goal_points_per = 5
            else:  # FWD
                goal_points_per = 4

            # Clean sheet points
            if position in ["GK", "DEF"]:
                cs_points_per = 4
            elif position == "MID":
                cs_points_per = 1
            else:
                cs_points_per = 0

            # Goals conceded
            if position in ["GK", "DEF"]:
                gc_points = -1 * (goals_conceded // 2)
            else:
                gc_points = 0

            # Defensive contributions
            def calculate_def_contribution_points(df, position):
            """Calculate defensive contribution points match-by-match (capped at 2 per match)."""

            def_points = 0

            for _, row in df.iterrows():
                dc = row.get("defensive_contribution", 0)

                if position == "DEF":
                    if dc >= 10:
                        def_points += 2
                elif position in ["MID", "FWD"]:
                    if dc >= 12:
                        def_points += 2
                # GK gets no defensive contribution bonus

            return def_points


            assists_points_per = 3
            minutes_points = apps_60 * 2 + apps_sub * 1
            goals_points = goals * goal_points_per
            assists_points = assists * assists_points_per
            cs_points = clean_sheets * cs_points_per

            if position == "GK":
                saves_points = (saves // 3) * 1
            else:
                saves_points = 0

            yc_points = -1 * yellow_cards
            rc_points = -3 * red_cards
            og_points = -2 * own_goals
            ps_points = 5 * pens_saved
            pm_points = -2 * pens_missed
            bonus_points = bonus

            # Build breakdown table with internal detail
            rows = []

            rows.append({
                "Category": "Goals",
                "Count": int(goals),
                "Points per Event": goal_points_per,
                "Total Points": int(goals_points),
            })
            rows.append({
                "Category": "Assists",
                "Count": int(assists),
                "Points per Event": assists_points_per,
                "Total Points": int(assists_points),
            })
            rows.append({
                "Category": "Clean Sheets",
                "Count": int(clean_sheets),
                "Points per Event": cs_points_per,
                "Total Points": int(cs_points),
            })
            rows.append({
                "Category": "Minutes (60+)",
                "Count": int(apps_60),
                "Points per Event": 2,
                "Total Points": int(apps_60 * 2),
            })
            rows.append({
                "Category": "Minutes (<60)",
                "Count": int(apps_sub),
                "Points per Event": 1,
                "Total Points": int(apps_sub * 1),
            })

            if position == "GK":
                rows.append({
                    "Category": "Saves",
                    "Count": int(saves),
                    "Points per Event": "1 per 3",
                    "Total Points": int(saves_points),
                })

            if position in ["GK", "DEF"]:
                rows.append({
                    "Category": "Goals Conceded",
                    "Count": int(goals_conceded),
                    "Points per Event": "-1 per 2",
                    "Total Points": int(gc_points),
                })

            # Defensive contributions row
            rows.append({
                "Category": "Defensive Contributions",
                "Count": int(def_contrib),
                "Points per Event": (
                    "2 per 10" if position == "DEF" else
                    ("2 per 12" if position in ["MID", "FWD"] else "0")
                ),
                "Total Points": int(def_points),
            })

            rows.append({
                "Category": "Bonus",
                "Count": int(bonus),
                "Points per Event": 1,
                "Total Points": int(bonus_points),
            })
            rows.append({
                "Category": "Yellow Cards",
                "Count": int(yellow_cards),
                "Points per Event": -1,
                "Total Points": int(yc_points),
            })
            rows.append({
                "Category": "Red Cards",
                "Count": int(red_cards),
                "Points per Event": -3,
                "Total Points": int(rc_points),
            })
            rows.append({
                "Category": "Own Goals",
                "Count": int(own_goals),
                "Points per Event": -2,
                "Total Points": int(og_points),
            })
            rows.append({
                "Category": "Penalties Saved",
                "Count": int(pens_saved),
                "Points per Event": 5,
                "Total Points": int(ps_points),
            })
            rows.append({
                "Category": "Penalties Missed",
                "Count": int(pens_missed),
                "Points per Event": -2,
                "Total Points": int(pm_points),
            })

            breakdown_df = pd.DataFrame(rows)

            # Keep categories that actually contributed points or had non-zero counts
            breakdown_df = breakdown_df[
                (breakdown_df["Total Points"] != 0) | (breakdown_df["Count"] != 0)
            ].reset_index(drop=True)

            calc_total = breakdown_df["Total Points"].sum()

            # ---- FPL Points Contribution (moved ABOVE GW breakdown) ----
            st.markdown(f"### 🧮 FPL Points Contribution (GW {gw_start}–{gw_end})")

            # Build display version without Count / Points per Event
            if total_points_range > 0:
                display_df = breakdown_df[["Category", "Total Points"]].copy()
                display_df["Percentage"] = (
                    display_df["Total Points"] / total_points_range * 100
                ).round(1)
            else:
                display_df = breakdown_df[["Category", "Total Points"]].copy()
                display_df["Percentage"] = 0.0

            st.write(
                f"**Total from breakdown:** {int(calc_total)} points &nbsp;&nbsp;|&nbsp;&nbsp; "
                f"**Total from API (sum of total_points):** {int(total_points_range)} points"
            )

            st.dataframe(
                display_df,
                use_container_width=True,
                hide_index=True,
            )

            # ---- Bar Chart: Points by Category ----
            st.markdown("### 📈 Points Contribution by Category")
            if not display_df.empty:
                fig_bar = px.bar(
                    display_df,
                    x="Category",
                    y="Total Points",
                    title=f"Points Contribution (GW {gw_start}–{gw_end}) — {player_name}",
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            # ---- GW-Range Summary (no blank index) ----
            st.markdown("### 🔍 GW-Range Summary")
            summary_df = pd.DataFrame(
                {
                    "Team": [player_row["Team"]],
                    "Position": [position],
                    "Current Price": [round(player_row["Current Price"], 2)],
                    "Selected By %": [round(player_row["Selected By %"], 2)],
                    f"Total Points (GW {gw_start}-{gw_end})": [int(total_points_range)],
                }
            )
            st.dataframe(summary_df, hide_index=True, use_container_width=True)

            # ---- Points Breakdown by Gameweek (GW range only) ----
            st.markdown(f"### 📊 Points Breakdown by Gameweek (GW {gw_start}–{gw_end})")

            # Base columns
            base_cols = [
                "round",
                "total_points",
                "goals_scored",
                "assists",
                "clean_sheets",
                "goals_conceded",
                "bonus",
                "minutes",
                "yellow_cards",
                "red_cards",
                "saves",
            ]

            # Filter to available columns (defensive safety)
            base_cols = [c for c in base_cols if c in df_range.columns]
            breakdown_view = df_range[base_cols].copy()

            # Conditional column visibility
            if position != "GK" and "saves" in breakdown_view.columns:
                breakdown_view = breakdown_view.drop(columns=["saves"])

            if position not in ["GK", "DEF", "MID"]:
                # FWD: remove defensive clean sheet & GC columns
                for c in ["clean_sheets", "goals_conceded"]:
                    if c in breakdown_view.columns:
                        breakdown_view = breakdown_view.drop(columns=[c])
            else:
                # MID: no goals_conceded penalties, but you wanted column visible;
                # keep as is for GK/DEF/MID
                pass

            # Rename columns
            rename_map = {
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
            }
            breakdown_view = breakdown_view.rename(columns=rename_map)

            st.dataframe(
                breakdown_view.sort_values("Gameweek"),
                use_container_width=True,
                hide_index=True,
            )

            # ---- Line Chart: Points per GW (range only) ----
            st.markdown("### 📉 Points per Gameweek (GW Range)")
            fig_line = px.line(
                df_range.sort_values("round"),
                x="round",
                y="total_points",
                markers=True,
                title=f"Points per GW — {player_name} (GW {gw_start}–{gw_end})",
            )
            st.plotly_chart(fig_line, use_container_width=True)

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

