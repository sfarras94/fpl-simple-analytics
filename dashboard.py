import streamlit as st
import pandas as pd
import json
import base64
import os
import plotly.express as px
import plotly.graph_objects as go

# =====================================
# Session State Defaults
# =====================================
if "selected_player" not in st.session_state:
    st.session_state.selected_player = "None"

# =====================================
# Background Image
# =====================================
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

        .row_heading.level0 {{display:none}}
        .blank {{display:none}}
        </style>
        """,
        unsafe_allow_html=True
    )


IMAGE_PATH = "bg1.png"
set_background(IMAGE_PATH)


# =====================================
# Load Local Cache
# =====================================
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

    # Template & differential
    df["Template Value"] = df["Points Per Million"] * df["Selected By (Decimal)"]
    df["Differential Value"] = df["Points Per Million"] * (1 - df["Selected By (Decimal)"])

    return df


@st.cache_data
def load_weekly():
    with open(WEEKLY_FILE, "r") as f:
        return json.load(f)


players = load_players()
weekly = load_weekly()

# =====================================
# Weekly DF for slider limits
# =====================================
weekly_df = pd.concat([pd.DataFrame(v) for v in weekly.values()], ignore_index=True)
min_gw = int(weekly_df["round"].min())
max_gw = int(weekly_df["round"].max())

# =====================================
# Sidebar Filters — inside a form
# =====================================
with st.sidebar.form("filters_form", clear_on_submit=False):

    st.header("🔍 Filters")

    team_filter = st.selectbox(
        "Team",
        ["All Teams"] + sorted(players["Team"].unique()),
        key="team_filter"
    )

    position_filter = st.selectbox(
        "Position",
        ["All", "GK", "DEF", "MID", "FWD"],
        key="position_filter"
    )

    gw_start, gw_end = st.slider(
        "Gameweek Range",
        min_value=min_gw,
        max_value=max_gw,
        value=(min_gw, max_gw),
        key="gw_slider"
    )

    sort_column = st.selectbox(
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

    sort_order = st.radio(
        "Sort Order",
        ["Descending", "Ascending"],
        key="sort_order"
    )

    selected_player = st.selectbox(
        "View Player Details / Compare Players",
        ["None"] + sorted(players["web_name"].unique()),
        key="selected_player"
    )

    selected_player2 = st.selectbox(
        "Compare With (Optional)",
        ["None"] + sorted(players["web_name"].unique()),
        key="selected_player2"
    )

    reset_clicked = st.form_submit_button("🔄 Reset All Filters")

# Reset state
if reset_clicked:
    st.session_state.clear()
    st.session_state.selected_player = "None"
    st.experimental_rerun()

# =====================================
# Filtering
# =====================================
filtered = players.copy()

if st.session_state.team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == st.session_state.team_filter]

if st.session_state.position_filter != "All":
    filtered = filtered[filtered["Position"] == st.session_state.position_filter]

# =====================================
# GW Range Calculation
# =====================================
def get_points_for_range(player_id, gw1, gw2):
    hist = weekly.get(str(player_id), [])
    if not hist:
        return 0
    df = pd.DataFrame(hist)
    df = df[(df["round"] >= gw1) & (df["round"] <= gw2)]
    return df["total_points"].sum()


filtered["Points (GW Range)"] = filtered.apply(
    lambda r: get_points_for_range(r["id"], st.session_state.gw_slider[0], st.session_state.gw_slider[1]),
    axis=1
)

# =====================================
# Table Build
# =====================================
table = filtered[[
    "web_name",
    "Team",
    "Position",
    "Points (GW Range)",
    "Current Price",
    "Selected By %"
]].rename(columns={"web_name": "Player"})

# Dynamic metrics
table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]

sel_dec = table["Selected By %"] / 100
table["Template Value"] = table["Points Per Million"] * sel_dec
table["Differential Value"] = table["Points Per Million"] * (1 - sel_dec)

# Rounding
cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value"
]
table[cols] = table[cols].round(2)

# Sorting
ascending = (st.session_state.sort_order == "Ascending")
table = table.sort_values(by=st.session_state.sort_column, ascending=ascending)

# =====================================
# PLAYER DETAIL SECTION
# =====================================
def player_breakdown(name):
    pid = int(players[players["web_name"] == name]["id"].iloc[0])
    hist = weekly.get(str(pid), [])
    if not hist:
        return None

    df = pd.DataFrame(hist)
    df = df[(df["round"] >= st.session_state.gw_slider[0]) &
            (df["round"] <= st.session_state.gw_slider[1])]

    # Compute points breakdown per FPL Rules
    total_minutes = df["minutes"].sum()

    goals = df["goals_scored"].sum()
    assists = df["assists"].sum()
    clean_sheets = df["clean_sheets"].sum()
    bonus = df["bonus"].sum()
    saves = df["saves"].sum()
    yc = df["yellow_cards"].sum()
    rc = df["red_cards"].sum()
    og = df["own_goals"].sum()
    pens_missed = df["penalties_missed"].sum()
    pens_saved = df["penalties_saved"].sum()

    # Defensive contributions
    position = players.loc[players["web_name"] == name, "Position"].iloc[0]
    dc_raw = df["defensive_contribution"].sum()

    if position == "DEF":
        dc_points = 2 if dc_raw >= 10 else 0
    elif position == "MID":
        dc_points = 2 if dc_raw >= 12 else 0
    elif position == "FWD":
        dc_points = 2 if dc_raw >= 12 else 0
    else:
        dc_points = 0

    total_points = df["total_points"].sum()

    breakdown = pd.DataFrame([
        ["Minutes", total_minutes],
        ["Goals", goals],
        ["Assists", assists],
        ["Clean Sheets", clean_sheets],
        ["Bonus", bonus],
        ["Saves", saves if position == "GK" else 0],
        ["Defensive Contributions", dc_points],
        ["Yellow Cards", -yc],
        ["Red Cards", -3 * rc],
        ["Own Goals", -2 * og],
        ["Penalties Missed", -2 * pens_missed],
        ["Penalties Saved", 5 * pens_saved],
        ["Total Points", total_points],
    ], columns=["Category", "Total Points"])

    return df, breakdown


# =====================================
# PLAYER DETAIL PAGE
# =====================================
if st.session_state.selected_player != "None":

    p1 = st.session_state.selected_player
    p2 = st.session_state.selected_player2 if st.session_state.selected_player2 != "None" else None

    df1, bd1 = player_breakdown(p1)
    if p2:
        df2, bd2 = player_breakdown(p2)

    st.title(f"📌 Player Analysis — {p1}" + (f" vs {p2}" if p2 else ""))

    # RADAR CHART (Comparison Only)
    if p2:
        categories = [
            "Goals", "Assists", "Clean Sheets",
            "Bonus", "Saves", "Defensive Contributions",
            "Minutes", "Total Points"
        ]

        radar1 = bd1.set_index("Category").reindex(categories)["Total Points"].tolist()
        radar2 = bd2.set_index("Category").reindex(categories)["Total Points"].tolist()

        fig_radar = go.Figure()

        fig_radar.add_trace(go.Scatterpolar(
            r=radar1,
            theta=categories,
            fill='toself',
            name=p1
        ))
        fig_radar.add_trace(go.Scatterpolar(
            r=radar2,
            theta=categories,
            fill='toself',
            name=p2
        ))

        fig_radar.update_layout(
            polar=dict(radialaxis=dict(visible=True)),
            showlegend=True,
            title="Player Comparison Radar"
        )

        st.plotly_chart(fig_radar, use_container_width=True)

    # FPL POINTS CONTRIBUTION TABLE
    st.markdown("### 🧮 FPL Points Contribution")

    if p2:
        comp = bd1.merge(bd2, on="Category", suffixes=(" A", " B"))

        # Highlight winners
        def highlight(row):
            a = row["Total Points A"]
            b = row["Total Points B"]
            if a > b:
                return ["background-color:#c7f7c7", ""]
            elif b > a:
                return ["", "background-color:#c7f7c7"]
            return ["", ""]

        styled = comp.style.apply(
            lambda r: highlight(r),
            axis=1,
            subset=["Total Points A", "Total Points B"]
        )

        st.dataframe(
            styled,
            hide_index=True,
            use_container_width=True,
            height=min(700, (len(comp)+2)*40),
        )

    else:
        st.dataframe(
            bd1,
            hide_index=True,
            use_container_width=True,
            height=min(600, (len(bd1)+1)*40)
        )

    # BREAKDOWN BY GAMEWEEK
    st.markdown(f"### 📊 Points Breakdown by Gameweek (GW {gw_start}-{gw_end})")

    show_cols = [
        ("round", "Gameweek"),
        ("total_points", "Points"),
        ("goals_scored", "Goals"),
        ("assists", "Assists"),
        ("clean_sheets", "Clean Sheets"),
        ("goals_conceded", "Goals Conceded"),
        ("bonus", "Bonus"),
        ("minutes", "Minutes"),
        ("yellow_cards", "Yellow Cards"),
        ("red_cards", "Red Cards"),
    ]

    pos = players.loc[players["web_name"] == p1, "Position"].iloc[0]
    if pos == "GK":
        show_cols.append(("saves", "Saves"))

    df_disp = df1[[c[0] for c in show_cols]].rename(columns={a: b for a, b in show_cols})
    st.dataframe(df_disp, hide_index=True, use_container_width=True)


# =====================================
# MAIN PAGE TABLE
# =====================================
st.markdown("<div class='main-container'>", unsafe_allow_html=True)

st.title("🔥 FPL Analytics Dashboard")
st.write("Using cached data.")

st.subheader("📊 Player Value Table")
st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
)

st.markdown("</div>", unsafe_allow_html=True)
