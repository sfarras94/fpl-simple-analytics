import streamlit as st
import pandas as pd
import json
import base64
import os
import requests
import plotly.graph_objects as go

# =========================================
# SESSION STATE DEFAULTS
# =========================================
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "main"  # "main", "single", "compare"

if "selected_player" not in st.session_state:
    st.session_state.selected_player = "None"

if "compare_players" not in st.session_state:
    st.session_state.compare_players = []

if "compare_dropdown" not in st.session_state:
    st.session_state.compare_dropdown = "None"

if "reset_flag" not in st.session_state:
    st.session_state.reset_flag = False


# =========================================
# BACKGROUND IMAGE
# =========================================
def set_background(image_file: str):
    if not os.path.exists(image_file):
        return
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

        .row_heading.level0 {{display:none}}
        .blank {{display:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )


IMAGE_PATH = "bg1.png"
set_background(IMAGE_PATH)


# =========================================
# LOAD LIVE DATA
# =========================================
@st.cache_data(ttl=3600)
def load_players_live():
    """Loads live players + team data from the official FPL API."""
    static = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/").json()

    players_df = pd.DataFrame(static["elements"])
    teams_df = pd.DataFrame(static["teams"])[["id", "name"]].rename(
        columns={"id": "team", "name": "Team"}
    )
    players_df = players_df.merge(teams_df, on="team", how="left")

    pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
    players_df["Position"] = players_df["element_type"].map(pos_map)

    players_df["Current Price"] = players_df["now_cost"] / 10
    players_df["Points Per Million (Season)"] = players_df["total_points"] / players_df["Current Price"]

    players_df["Selected By (Decimal)"] = (
        pd.to_numeric(players_df["selected_by_percent"], errors="coerce") / 100
    )
    players_df["Selected By %"] = players_df["Selected By (Decimal)"] * 100

    players_df["Template Value (Season)"] = (
        players_df["Points Per Million (Season)"] * players_df["Selected By (Decimal)"]
    )
    players_df["Differential Value (Season)"] = (
        players_df["Points Per Million (Season)"] * (1 - players_df["Selected By (Decimal)"])
    )

    return players_df, static


@st.cache_data(ttl=3600)
def load_weekly_live(players_df):
    """Loads weekly history for all players using element-summary."""
    weekly_data = {}
    for pid in players_df["id"]:
        url = f"https://fantasy.premierleague.com/api/element-summary/{pid}/"
        try:
            data = requests.get(url).json().get("history", [])
        except Exception:
            data = []
        weekly_data[str(pid)] = data

    return weekly_data


players, static_data = load_players_live()
weekly = load_weekly_live(players)

# Build GW range from all history
weekly_df = pd.concat([pd.DataFrame(v) for v in weekly.values()], ignore_index=True)
min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())

# Team lookup for Opponent
team_lookup = {
    int(row["id"]): row["name"]
    for _, row in pd.DataFrame(static_data["teams"]).iterrows()
}


# =========================================
# RESET LOGIC
# =========================================
def trigger_reset():
    st.session_state.reset_flag = True

def apply_reset():
    st.session_state.team_filter = "All Teams"
    st.session_state.position_filter = "All"
    st.session_state.gw_slider = (min_gw, max_gw)
    st.session_state.sort_column = "Points (GW Range)"
    st.session_state.sort_order = "Descending"
    st.session_state.selected_player = "None"
    st.session_state.compare_dropdown = "None"
    st.session_state.compare_players = []
    st.session_state.view_mode = "main"


if st.session_state.reset_flag:
    apply_reset()
    st.session_state.reset_flag = False


# =========================================
# SIDEBAR FILTERS
# =========================================
st.sidebar.title("🔍 Filters")

team_filter = st.sidebar.selectbox(
    "Team",
    ["All Teams"] + sorted(players["Team"].unique()),
    key="team_filter",
)

position_filter = st.sidebar.selectbox(
    "Position",
    ["All", "GK", "DEF", "MID", "FWD"],
    key="position_filter",
)

gw_start, gw_end = st.sidebar.slider(
    "Gameweek Range",
    min_value=min_gw,
    max_value=max_gw,
    value=st.session_state.get("gw_slider", (min_gw, max_gw)),
    key="gw_slider",
)

sort_column = st.sidebar.selectbox(
    "Sort Table By",
    [
        "Points (GW Range)",
        "Current Price",
        "Points Per Million",
        "Selected By %",
        "Template Value",
        "Differential Value",
    ],
    key="sort_column",
)

sort_order = st.sidebar.radio("Sort Order", ["Descending", "Ascending"], key="sort_order")

st.sidebar.markdown("---")
st.sidebar.subheader("👤 Player Analysis / Comparison")


# Primary
primary_select = st.sidebar.selectbox(
    "Primary Player",
    ["None"] + sorted(players["web_name"].unique()),
    key="selected_player",
)

# Restrict comparison to same position
if primary_select != "None":
    pos = players.loc[players["web_name"] == primary_select, "Position"].iloc[0]
    compare_options = ["None"] + sorted(
        players[players["Position"] == pos]["web_name"].unique()
    )
else:
    compare_options = ["None"] + sorted(players["web_name"].unique())

compare_select = st.sidebar.selectbox(
    "Second Player (same position)",
    compare_options,
    key="compare_dropdown",
)

col_btn1, col_btn2 = st.sidebar.columns(2)

with col_btn1:
    if st.button("View Player"):
        if st.session_state.selected_player != "None":
            st.session_state.view_mode = "single"
            st.session_state.compare_players = [st.session_state.selected_player]

with col_btn2:
    if st.button("Compare Players"):
        chosen = []
        if st.session_state.selected_player != "None":
            chosen.append(st.session_state.selected_player)
        if st.session_state.compare_dropdown != "None":
            chosen.append(st.session_state.compare_dropdown)
        chosen = list(dict.fromkeys(chosen))
        if len(chosen) >= 2:
            st.session_state.compare_players = chosen[:2]
            st.session_state.view_mode = "compare"

st.sidebar.markdown("---")
st.sidebar.button("🔄 Reset All Filters", on_click=trigger_reset)


# =========================================
# GW RANGE CALC
# =========================================
def get_points_for_range(pid, gw1, gw2):
    hist = weekly.get(str(pid), [])
    if not hist:
        return 0
    df = pd.DataFrame(hist)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
    return int(df["total_points"].sum())


# =========================================
# MAIN TABLE BUILD
# =========================================
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]

filtered["Points (GW Range)"] = filtered.apply(
    lambda r: get_points_for_range(r["id"], gw_start, gw_end),
    axis=1,
)

table = filtered[
    [
        "web_name",
        "Team",
        "Position",
        "Points (GW Range)",
        "Current Price",
        "Selected By %",
    ]
].rename(columns={"web_name": "Player"})

table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]

sel_decimal = table["Selected By %"] / 100
table["Template Value"] = table["Points Per Million"] * sel_decimal
table["Differential Value"] = table["Points Per Million"] * (1 - sel_decimal)

for c in [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value",
]:
    table[c] = table[c].round(2)

ascending = sort_order == "Ascending"
table = table.sort_values(by=sort_column, ascending=ascending)
# =========================================
# CONTRIBUTION CALCULATION
# =========================================
def build_points_contribution(df_hist: pd.DataFrame, position: str):
    """
    df_hist: weekly history for a single player filtered to GW range.
    position: "GK", "DEF", "MID", or "FWD".
    Returns (DataFrame[Category, Points, % of Total], total_points).
    """

    # Base categories always shown
    allowed_categories = ["Minutes", "Goals", "Assists", "Bonus", "Cards", "Own Goals"]

    # Position-specific categories
    if position == "GK":
        allowed_categories += [
            "Clean Sheets",
            "Goals Conceded",
            "Saves",
            "Penalty Saves",
            "Penalty Misses",
        ]
    elif position == "DEF":
        allowed_categories += [
            "Clean Sheets",
            "Goals Conceded",
            "Penalty Misses",
            "Defensive Contribution",
        ]
    elif position == "MID":
        allowed_categories += [
            "Clean Sheets",
            "Penalty Misses",
            "Defensive Contribution",
        ]
    elif position == "FWD":
        allowed_categories += [
            "Penalty Misses",
            "Defensive Contribution",
        ]

    # No history => zero row for each allowed category
    if df_hist.empty:
        contrib = {cat: 0 for cat in allowed_categories}
        df = pd.DataFrame({"Category": list(contrib.keys()), "Points": list(contrib.values())})
        df["% of Total"] = 0.0
        return df, 0.0

    total_points = df_hist["total_points"].sum()

    # Raw stats
    mins = df_hist["minutes"].fillna(0)
    goals_scored = df_hist["goals_scored"].fillna(0)
    assists = df_hist["assists"].fillna(0)
    clean_sheets = df_hist["clean_sheets"].fillna(0)
    goals_conceded = df_hist["goals_conceded"].fillna(0)
    yc = df_hist["yellow_cards"].fillna(0)
    rc = df_hist["red_cards"].fillna(0)
    own_goals = df_hist["own_goals"].fillna(0)
    saves = df_hist["saves"].fillna(0)
    pen_saved = df_hist["penalties_saved"].fillna(0)
    pen_missed = df_hist["penalties_missed"].fillna(0)
    bonus = df_hist["bonus"].fillna(0)
    dc = df_hist.get("defensive_contribution", pd.Series(0, index=df_hist.index)).fillna(0)

    # Minutes
    minutes_points = ((mins > 0) & (mins < 60)) * 1 + (mins >= 60) * 2

    # Goals
    goal_points_map = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
    goals_points = goals_scored * goal_points_map.get(position, 0)

    # Assists
    assist_points = assists * 3

    # Clean sheets
    cs_mask = (mins >= 60) & (clean_sheets > 0)
    if position in ["GK", "DEF"]:
        cs_points = cs_mask * 4
    elif position == "MID":
        cs_points = cs_mask * 1
    else:
        cs_points = 0 * cs_mask

    # Goals conceded
    if position in ["GK", "DEF"]:
        gc_points = -((goals_conceded // 2))
    else:
        gc_points = pd.Series(0, index=df_hist.index)

    # Saves & penalties — all separate
    save_points = (saves // 3) * 1                 # normal shots saved only
    pen_save_points = pen_saved * 5                # each penalty save
    pen_miss_points = pen_missed * -2              # each penalty missed (by teammate)

    # Cards
    card_points = yc * -1 + rc * -3

    # Own goals
    og_points = own_goals * -2

    # Defensive contribution – max 2 pts
    if position == "DEF":
        dc_points = ((dc // 10).clip(upper=1)) * 2
    elif position in ["MID", "FWD"]:
        dc_points = ((dc // 12).clip(upper=1)) * 2
    else:
        dc_points = 0 * dc

    # Full contribution map
    raw_contrib = {
        "Minutes": minutes_points.sum(),
        "Goals": goals_points.sum(),
        "Assists": assist_points.sum(),
        "Clean Sheets": cs_points.sum(),
        "Goals Conceded": gc_points.sum(),
        "Defensive Contribution": dc_points.sum(),
        "Cards": card_points.sum(),
        "Saves": save_points.sum(),              # shots saved only
        "Penalty Saves": pen_save_points.sum(),  # separate route
        "Penalty Misses": pen_miss_points.sum(), # separate route
        "Own Goals": og_points.sum(),
        "Bonus": bonus.sum(),
    }

    # Only keep categories relevant for this position
    filtered_contrib = {cat: raw_contrib[cat] for cat in allowed_categories}

    df = pd.DataFrame(
        {"Category": list(filtered_contrib.keys()), "Points": list(filtered_contrib.values())}
    )

    if total_points > 0:
        df["% of Total"] = (df["Points"] / total_points * 100).round(1)
    else:
        df["% of Total"] = 0.0

    return df, float(total_points)


# =========================================
# CONTRIBUTION BAR CHART (points)
# =========================================
def build_contrib_bar(contrib_dfs, names):
    """
    Bar chart now mirrors the exact categories shown in the FPL Contribution Table.
    It dynamically shows only the relevant categories based on player positions.
    """

    # Determine union of all categories across all players in comparison
    categories = []
    for df in contrib_dfs:
        cats = df["Category"].tolist()
        for c in cats:
            if c not in categories:
                categories.append(c)

    fig = go.Figure()

    for name, df_c in zip(names, contrib_dfs):
        d = df_c.set_index("Category")
        values = [float(d.loc[c, "Points"]) if c in d.index else 0.0 for c in categories]

        fig.add_trace(
            go.Bar(
                x=categories,
                y=values,
                name=name,
            )
        )

    fig.update_layout(
        barmode="group",
        xaxis_title="Category",
        yaxis_title="Points",
        margin=dict(l=40, r=40, t=40, b=40),
        showlegend=True,
    )

    return fig



# =========================================
# GW BREAKDOWN + OUTLIER ❗ + SPARKLINE
# Now includes Opponent with (H)/(A)
# =========================================
def build_gw_breakdown(df_hist: pd.DataFrame, gw1: int, gw2: int):
    df = df_hist[(df_hist["round"] >= gw1) & (df_hist["round"] <= gw2)].copy()
    if df.empty:
        return None, None

    df = df.sort_values("round")

    # Basic stats
    df["Gameweek"] = df["round"].astype(int)
    df["Points"] = df["total_points"].fillna(0).astype(int)

    # Opponent with home/away indicator
    # Uses team_lookup built from bootstrap-static
    def get_opp_label(row):
        opp_id = row.get("opponent_team", None)
        if pd.isna(opp_id):
            return ""
        opp_id = int(opp_id)
        opp_name = team_lookup.get(opp_id, f"Team {opp_id}")
        is_home = bool(row.get("was_home", False))
        suffix = "(H)" if is_home else "(A)"
        return f"{opp_name} {suffix}"

    df["Opponent"] = df.apply(get_opp_label, axis=1)

    total = df["Points"].sum()
    if total > 0:
        pct_vals = df["Points"] / total * 100
    else:
        pct_vals = pd.Series(0, index=df.index)

    pct_str = pct_vals.round(1).astype(str) + "%"

    # Outliers: high weeks only (z >= 1.5)
    if df["Points"].std(ddof=0) != 0:
        z = (df["Points"] - df["Points"].mean()) / df["Points"].std(ddof=0)
    else:
        z = pd.Series(0, index=df.index)

    pct_with_icon = []
    for val, z_val in zip(pct_str, z):
        if z_val >= 1.5:
            pct_with_icon.append(f"{val} ❗")
        else:
            pct_with_icon.append(val)

    df["% Contribution"] = pct_with_icon

    df_view = df[["Gameweek", "Opponent", "Points", "% Contribution"]].copy()
    spark_data = df["Points"].tolist()
    return df_view, spark_data


def render_gw_breakdown(name: str, df_hist: pd.DataFrame, gw1: int, gw2: int):
    df_view, spark = build_gw_breakdown(df_hist, gw1, gw2)
    if df_view is None:
        st.info(f"No GW data in range for {name}.")
        return

    st.markdown(f"#### GW Breakdown — {name}")

    # Height so all rows are visible (no scrolling)
    n_rows = len(df_view)
    row_height = 35
    header_height = 40
    height = header_height + n_rows * row_height

    st.dataframe(
        df_view,
        width="stretch",
        hide_index=True,
        height=height,
    )

    # Sparkline
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df_view["Gameweek"],
            y=df_view["Points"],
            mode="lines+markers",
        )
    )
    fig.update_layout(
        height=180,
        margin=dict(l=20, r=20, t=20, b=20),
        showlegend=False,
        xaxis=dict(title="GW"),
        yaxis=dict(title="Pts"),
    )
    st.plotly_chart(fig, use_container_width=True)
# =========================================
# OVERLAY (SINGLE & COMPARE)
# =========================================
def show_overlay(player_names, gw1, gw2):
    st.markdown(
        """
        <div style="background-color: rgba(0,0,0,0.05); padding: 15px; border-radius: 10px; margin-bottom: 20px;">
        """,
        unsafe_allow_html=True,
    )

    col_back, _ = st.columns([1, 3])
    with col_back:
        if st.button("⬅ Back to main dashboard & reset filters"):
            trigger_reset()
            st.rerun()

    contrib_dfs = []
    totals = []
    meta_rows = []

    for name in player_names:
        p_row = players[players["web_name"] == name].iloc[0]
        pid = int(p_row["id"])
        pos = p_row["Position"]
        team = p_row["Team"]
        price = float(p_row["Current Price"])
        selected_pct = float(p_row["Selected By %"].round(2))

        history = weekly.get(str(pid), [])
        if not history:
            st.info(f"No weekly data available for **{name}**.")
            continue

        df_hist = pd.DataFrame(history)
        df_hist_range = df_hist[(df_hist["round"] >= gw1) & (df_hist["round"] <= gw2)]

        contrib_df, total_pts = build_points_contribution(df_hist_range, pos)
        contrib_dfs.append(contrib_df)
        totals.append(total_pts)
        meta_rows.append(
            {
                "Player": name,
                "Team": team,
                "Position": pos,
                "Price (£m)": round(price, 1),
                "Selected %": round(selected_pct, 2),
                f"Points (GW {gw1}-{gw2})": int(total_pts),
            }
        )

    if not contrib_dfs:
        st.info("No contribution data found for the selected players in this range.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # GW-range summary
    st.markdown("### 🔍 GW-Range Summary")
    meta_df = pd.DataFrame(meta_rows)
    st.dataframe(meta_df, width="stretch", hide_index=True)

    # FPL Points Contribution
    st.markdown("### 📊 FPL Points Contribution")

    if len(player_names) == 1:
        # Single player
        df_single = contrib_dfs[0].copy()
        df_single["Points"] = df_single["Points"].astype(int)

        n_rows = len(df_single)
        row_height = 35
        header_height = 40
        height = header_height + n_rows * row_height

        st.dataframe(df_single, width="stretch", hide_index=True, height=height)

    else:
        # Comparison table with "points (xx.x%)" and ⭐ for winner
        cats = contrib_dfs[0]["Category"].tolist()
        comp_display = pd.DataFrame({"Category": cats})

        num_players = len(player_names)
        points_matrix = [
            [contrib_dfs[i]["Points"].iloc[row_i] for i in range(num_players)]
            for row_i in range(len(cats))
        ]
        row_max = [max(row) for row in points_matrix]

        for i, (name, contrib_df, total_pts) in enumerate(
            zip(player_names, contrib_dfs, totals)
        ):
            formatted_cells = []
            pts_series = contrib_df["Points"].tolist()
            for row_i, pts in enumerate(pts_series):
                pts_int = int(pts)
                if total_pts > 0:
                    pct = pts / total_pts * 100
                else:
                    pct = 0.0

                cell_text = f"{pts_int} ({pct:.1f}%)"
                if pts == row_max[row_i] and pts != 0:
                    cell_text += " ⭐"
                formatted_cells.append(cell_text)
            comp_display[name] = formatted_cells

        n_rows = len(comp_display)
        row_height = 35
        header_height = 40
        height = header_height + n_rows * row_height

        st.dataframe(comp_display, width="stretch", hide_index=True, height=height)

    # Contribution bar chart
    st.markdown("### 📊 Contribution by Category")
    bar_fig = build_contrib_bar(contrib_dfs, player_names)
    st.plotly_chart(bar_fig, use_container_width=True)

    # GW breakdowns
    st.markdown("### 📅 Points Breakdown by Gameweek")
    if len(player_names) == 1:
        name = player_names[0]
        p_row = players[players["web_name"] == name].iloc[0]
        pid = int(p_row["id"])
        history = weekly.get(str(pid), [])
        if history:
            df_hist = pd.DataFrame(history)
            render_gw_breakdown(name, df_hist, gw1, gw2)
    else:
        cols = st.columns(len(player_names))
        for col, name in zip(cols, player_names):
            with col:
                p_row = players[players["web_name"] == name].iloc[0]
                pid = int(p_row["id"])
                history = weekly.get(str(pid), [])
                if not history:
                    st.info(f"No data for {name}.")
                    continue
                df_hist = pd.DataFrame(history)
                render_gw_breakdown(name, df_hist, gw1, gw2)

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================
# PAGE CONTENT
# =========================================
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Simple Analytics")
st.write("Using live FPL data with GW-range value metrics and player analysis.")

# Overlay for view / comparison
if st.session_state.view_mode == "single" and st.session_state.selected_player != "None":
    show_overlay([st.session_state.selected_player], gw_start, gw_end)
elif (
    st.session_state.view_mode == "compare"
    and len(st.session_state.compare_players) >= 2
):
    show_overlay(st.session_state.compare_players[:2], gw_start, gw_end)

# Main table (hide when in overlay mode)
if st.session_state.view_mode == "main":
    st.subheader("📊 Player Value Table")

    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "Player": st.column_config.TextColumn(
                "Player",
                help="Player’s short name (web_name from FPL API)",
            ),
            "Team": st.column_config.TextColumn(
                "Team",
                help="Premier League team",
            ),
            "Position": st.column_config.TextColumn(
                "Pos",
                help="GK, DEF, MID, or FWD",
            ),
            "Points (GW Range)": st.column_config.NumberColumn(
                f"Points (GW {gw_start}-{gw_end})",
                help="Total FPL points between selected gameweeks",
            ),
            "Current Price": st.column_config.NumberColumn(
                "Price (£m)",
                help="Current FPL price (now_cost / 10)",
                format="£%.1f",
            ),
            "Points Per Million": st.column_config.NumberColumn(
                "PPM",
                help="Points (GW Range) divided by current price",
                format="%.2f",
            ),
            "Selected By %": st.column_config.NumberColumn(
                "Selected %",
                help="Percentage of FPL managers who own this player",
                format="%.2f",
            ),
            "Template Value": st.column_config.NumberColumn(
                "Template Value",
                help="PPM × Selected %. Higher = template pick",
                format="%.2f",
            ),
            "Differential Value": st.column_config.NumberColumn(
                "Differential Value",
                help="PPM × (1 – Selected %). Higher = differential pick",
                format="%.2f",
            ),
        },
    )

st.markdown("</div>", unsafe_allow_html=True)

