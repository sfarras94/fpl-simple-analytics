import streamlit as st
import pandas as pd
import requests
import base64
import os
import plotly.graph_objects as go

# ======================================================
# PAGE CONFIG
# ======================================================
st.set_page_config(page_title="FPL Simple Analytics", layout="wide")

ROW_HEIGHT = 35
HEADER_HEIGHT = 40

FPL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_ELEMENT = "https://fantasy.premierleague.com/api/element-summary/{}"

# ======================================================
# SESSION STATE DEFAULTS
# ======================================================
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "main"  # main | single | compare

if "reset_flag" not in st.session_state:
    st.session_state.reset_flag = False

# Filter widget keys
for k, v in {
    "team_filter": "All Teams",
    "position_filter": "All",
    "gw_slider": (1, 1),
    "sort_column": "Points (GW Range)",
    "sort_order": "Descending",
    "primary_player_display": "None",
    "secondary_player_display": "None",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ======================================================
# BACKGROUND IMAGE
# ======================================================
def set_background(image_file: str):
    if not os.path.exists(image_file):
        return
    with open(image_file, "rb") as f:
        data = f.read()
        b64 = base64.b64encode(data).decode()

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{b64}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
            background-repeat: no-repeat;
        }}

        .main-container {{
            background: rgba(255,255,255,0.88);
            padding: 20px;
            border-radius: 15px;
        }}

        .block-container {{
            padding-left: 3rem !important;
            padding-right: 3rem !important;
            max-width: 2000px !important;
        }}

        /* Hide dataframe index column */
        .row_heading.level0 {{display:none}}
        .blank {{display:none}}
        </style>
        """,
        unsafe_allow_html=True,
    )

set_background("bg1.png")

# ======================================================
# LIVE DATA LOADERS
# ======================================================
@st.cache_data(ttl=3600)
def load_bootstrap():
    return requests.get(FPL_BOOTSTRAP, timeout=30).json()

@st.cache_data(ttl=3600)
def load_element_summary(player_id: int):
    return requests.get(FPL_ELEMENT.format(player_id), timeout=30).json()

bootstrap = load_bootstrap()

players = pd.DataFrame(bootstrap["elements"])
teams = pd.DataFrame(bootstrap["teams"])[["id", "name", "short_name"]]
events = pd.DataFrame(bootstrap["events"])[["id", "is_current", "finished"]]

# Current GW bounds
min_gw = int(events["id"].min())
max_gw = int(events["id"].max())
# Default slider to current season span if unset/invalid
if not isinstance(st.session_state.gw_slider, (tuple, list)) or len(st.session_state.gw_slider) != 2:
    st.session_state.gw_slider = (min_gw, max_gw)

# Merge team names
players = players.merge(
    teams.rename(columns={"id": "team", "name": "Team", "short_name": "Team Short"}),
    on="team",
    how="left",
)

# Position
pos_map = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
players["Position"] = players["element_type"].map(pos_map)

# Core metrics
players["Current Price"] = players["now_cost"] / 10.0
players["Selected By (Decimal)"] = pd.to_numeric(players["selected_by_percent"], errors="coerce") / 100.0
players["Selected By %"] = players["Selected By (Decimal)"] * 100.0

# ✅ Unique display label to prevent Barnes/Barnes collisions
players["full_name"] = players["first_name"] + " " + players["second_name"]
players["display_name"] = players["full_name"] + " (" + players["Team"] + ")"

DISPLAY_TO_ID = dict(zip(players["display_name"], players["id"]))
ID_TO_DISPLAY = dict(zip(players["id"], players["display_name"]))
TEAM_ID_TO_SHORT = dict(zip(teams["id"], teams["short_name"]))

# ======================================================
# RESET LOGIC (SAFE)
# ======================================================
def trigger_reset():
    st.session_state.reset_flag = True

def apply_reset():
    st.session_state.team_filter = "All Teams"
    st.session_state.position_filter = "All"
    st.session_state.gw_slider = (min_gw, max_gw)
    st.session_state.sort_column = "Points (GW Range)"
    st.session_state.sort_order = "Descending"
    st.session_state.primary_player_display = "None"
    st.session_state.secondary_player_display = "None"
    st.session_state.view_mode = "main"

if st.session_state.reset_flag:
    apply_reset()
    st.session_state.reset_flag = False

# ======================================================
# SIDEBAR FILTERS
# ======================================================
st.sidebar.title("🔍 Filters")

team_filter = st.sidebar.selectbox(
    "Team",
    ["All Teams"] + sorted(players["Team"].dropna().unique()),
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
    value=st.session_state.gw_slider,
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

sort_order = st.sidebar.radio(
    "Sort Order",
    ["Descending", "Ascending"],
    key="sort_order",
)

st.sidebar.markdown("---")
st.sidebar.subheader("👤 Player Analysis / Comparison")

primary_display = st.sidebar.selectbox(
    "Primary Player",
    ["None"] + sorted(players["display_name"].unique()),
    key="primary_player_display",
)

# Constrain comparison to same position as primary
if primary_display != "None":
    primary_id = int(DISPLAY_TO_ID[primary_display])
    primary_pos = players.loc[players["id"] == primary_id, "Position"].iloc[0]
    compare_options = ["None"] + sorted(
        players.loc[players["Position"] == primary_pos, "display_name"].unique()
    )
else:
    compare_options = ["None"]

secondary_display = st.sidebar.selectbox(
    "Second Player (same position)",
    compare_options,
    key="secondary_player_display",
)

col_btn1, col_btn2 = st.sidebar.columns(2)

with col_btn1:
    if st.button("View Player"):
        if st.session_state.primary_player_display != "None":
            st.session_state.view_mode = "single"

with col_btn2:
    if st.button("Compare Players"):
        if (
            st.session_state.primary_player_display != "None"
            and st.session_state.secondary_player_display != "None"
        ):
            st.session_state.view_mode = "compare"

st.sidebar.markdown("---")
st.sidebar.button("🔄 Reset All Filters", on_click=trigger_reset)

# ======================================================
# GW RANGE POINTS (LIVE via element-summary history)
# ======================================================
@st.cache_data(ttl=3600)
def get_points_for_range(player_id: int, gw1: int, gw2: int) -> int:
    data = load_element_summary(player_id)
    hist = pd.DataFrame(data.get("history", []))
    if hist.empty:
        return 0
    hist["round"] = pd.to_numeric(hist["round"], errors="coerce")
    hist = hist[(hist["round"] >= gw1) & (hist["round"] <= gw2)]
    return int(hist["total_points"].sum()) if not hist.empty else 0

# ======================================================
# MAIN TABLE BUILD (RESTORED)
# ======================================================
filtered = players.copy()

if team_filter != "All Teams":
    filtered = filtered[filtered["Team"] == team_filter]

if position_filter != "All":
    filtered = filtered[filtered["Position"] == position_filter]

# Compute GW range points for filtered players (cached per player per GW range)
# NOTE: This can be heavy if filtered is huge; caching makes subsequent runs fast.
with st.spinner("Calculating GW-range points (live)…"):
    filtered["Points (GW Range)"] = filtered["id"].apply(lambda pid: get_points_for_range(int(pid), gw_start, gw_end))

table = filtered[
    [
        "display_name",
        "Team",
        "Position",
        "Points (GW Range)",
        "Current Price",
        "Selected By %",
    ]
].rename(columns={"display_name": "Player"})

table["Points Per Million"] = table["Points (GW Range)"] / table["Current Price"]

sel_decimal = table["Selected By %"] / 100.0
table["Template Value"] = table["Points Per Million"] * sel_decimal
table["Differential Value"] = table["Points Per Million"] * (1 - sel_decimal)

round_cols = [
    "Current Price",
    "Points (GW Range)",
    "Points Per Million",
    "Selected By %",
    "Template Value",
    "Differential Value",
]
table[round_cols] = table[round_cols].round(2)

ascending = (sort_order == "Ascending")
table = table.sort_values(by=sort_column, ascending=ascending)

# ======================================================
# CONTRIBUTION CALC (POSITION-AWARE + SEPARATE PEN ROUTES)
# ======================================================
def build_points_contribution(df_hist: pd.DataFrame, position: str):
    allowed = ["Minutes", "Goals", "Assists", "Bonus", "Cards", "Own Goals", "Penalty Misses"]

    if position == "GK":
        allowed += ["Clean Sheets", "Goals Conceded", "Saves", "Penalty Saves"]
    elif position == "DEF":
        allowed += ["Clean Sheets", "Goals Conceded", "Defensive Contribution"]
    elif position == "MID":
        allowed += ["Clean Sheets", "Defensive Contribution"]
    elif position == "FWD":
        allowed += ["Defensive Contribution"]

    if df_hist.empty:
        df = pd.DataFrame({"Category": allowed, "Points": [0]*len(allowed)})
        df["% of Total"] = 0.0
        return df, 0.0

    total = float(df_hist["total_points"].sum())

    mins = df_hist["minutes"].fillna(0)
    goals = df_hist["goals_scored"].fillna(0)
    assists = df_hist["assists"].fillna(0)
    cs = df_hist["clean_sheets"].fillna(0)
    gc = df_hist["goals_conceded"].fillna(0)
    saves = df_hist["saves"].fillna(0)
    pen_saved = df_hist["penalties_saved"].fillna(0)
    pen_missed = df_hist["penalties_missed"].fillna(0)
    bonus = df_hist["bonus"].fillna(0)
    yc = df_hist["yellow_cards"].fillna(0)
    rc = df_hist["red_cards"].fillna(0)
    og = df_hist["own_goals"].fillna(0)
    dc = df_hist.get("defensive_contribution", pd.Series(0, index=df_hist.index)).fillna(0)

    minutes_points = (((mins > 0) & (mins < 60)) * 1 + (mins >= 60) * 2)
    goal_points_map = {"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}
    goals_points = goals * goal_points_map.get(position, 0)
    assist_points = assists * 3

    cs_mask = (mins >= 60) & (cs > 0)
    if position in ["GK", "DEF"]:
        cs_points = cs_mask * 4
    elif position == "MID":
        cs_points = cs_mask * 1
    else:
        cs_points = cs_mask * 0

    if position in ["GK", "DEF"]:
        gc_points = -(gc // 2)
    else:
        gc_points = pd.Series(0, index=df_hist.index)

    save_points = (saves // 3) * 1
    pen_save_points = pen_saved * 5
    pen_miss_points = pen_missed * -2

    card_points = yc * -1 + rc * -3
    og_points = og * -2

    if position == "DEF":
        dc_points = ((dc // 10).clip(upper=1)) * 2
    elif position in ["MID", "FWD"]:
        dc_points = ((dc // 12).clip(upper=1)) * 2
    else:
        dc_points = 0 * dc

    raw = {
        "Minutes": minutes_points.sum(),
        "Goals": goals_points.sum(),
        "Assists": assist_points.sum(),
        "Clean Sheets": cs_points.sum(),
        "Goals Conceded": gc_points.sum(),
        "Saves": save_points.sum(),
        "Penalty Saves": pen_save_points.sum(),
        "Penalty Misses": pen_miss_points.sum(),
        "Bonus": bonus.sum(),
        "Cards": card_points.sum(),
        "Own Goals": og_points.sum(),
        "Defensive Contribution": dc_points.sum(),
    }

    filtered = {k: raw.get(k, 0) for k in allowed}
    df = pd.DataFrame({"Category": list(filtered.keys()), "Points": list(filtered.values())})
    df["Points"] = df["Points"].round(0).astype(int)
    df["% of Total"] = ((df["Points"] / total) * 100).round(1) if total else 0.0
    return df, total

# ======================================================
# CONTRIBUTION BAR CHART (MIRRORS TABLE CATEGORIES)
# ======================================================
def build_contrib_bar(dfs, names):
    # union of categories in order of first df
    categories = dfs[0]["Category"].tolist()

    fig = go.Figure()
    for name, dfc in zip(names, dfs):
        d = dfc.set_index("Category")
        vals = [int(d.loc[c, "Points"]) if c in d.index else 0 for c in categories]
        fig.add_bar(x=categories, y=vals, name=name)

    fig.update_layout(
        barmode="group",
        xaxis_title="Category",
        yaxis_title="Points",
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h"),
    )
    return fig

# ======================================================
# GW BREAKDOWN (POINTS LEFT + OPPONENT + H/A + AVG %)
# ======================================================
def build_gw_breakdown(df_hist: pd.DataFrame, gw1: int, gw2: int):
    df = df_hist[(df_hist["round"] >= gw1) & (df_hist["round"] <= gw2)].copy()
    if df.empty:
        return None, None, None

    df = df.sort_values("round")
    df["Points"] = df["total_points"].fillna(0).astype(int)

    total = df["Points"].sum()
    avg_pct = (100.0 / len(df)) if len(df) else 0.0

    pct = (df["Points"] / total * 100.0).fillna(0) if total else pd.Series(0, index=df.index)
    pct_round = pct.round(1)

    # Outliers (HIGH only)
    if df["Points"].std(ddof=0) != 0:
        z = (df["Points"] - df["Points"].mean()) / df["Points"].std(ddof=0)
    else:
        z = pd.Series(0, index=df.index)

    pct_str = []
    for v, zval in zip(pct_round, z):
        if zval >= 1.5:
            pct_str.append(f"{v:.1f}% ❗")
        else:
            pct_str.append(f"{v:.1f}%")

    # Opponent + H/A (from element-summary history)
    # opponent_team is team id; was_home is bool
    opp = df["opponent_team"].map(TEAM_ID_TO_SHORT).fillna("UNK")
    ha = df["was_home"].apply(lambda x: "H" if bool(x) else "A")

    df["Gameweek"] = df["round"].astype(int).astype(str) + " vs " + opp + " (" + ha + ")"

    df_view = df[["Points", "Gameweek",]].copy()
    df_view["% Contribution"] = pct_str

    spark_points = df["Points"].tolist()
    return df_view, spark_points, avg_pct

def render_gw_breakdown(title: str, df_hist: pd.DataFrame, gw1: int, gw2: int):
    df_view, spark, avg_pct = build_gw_breakdown(df_hist, gw1, gw2)
    if df_view is None:
        st.info(f"No GW data in range for {title}.")
        return

    st.markdown(f"#### GW Breakdown — {title}")
    st.caption(f"Average per-week share in this range: **{avg_pct:.1f}%**")

    # Height to show ALL rows (no scroll)
    n_rows = len(df_view)
    height = HEADER_HEIGHT + n_rows * ROW_HEIGHT

    st.dataframe(df_view, width="stretch", hide_index=True, height=height)

    # Sparkline
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(range(1, len(spark) + 1)), y=spark, mode="lines+markers"))
    fig.update_layout(
        height=170,
        margin=dict(l=10, r=10, t=20, b=10),
        showlegend=False,
        xaxis=dict(showticklabels=False, title=""),
        yaxis=dict(title="Pts"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ======================================================
# OVERLAY VIEW (SINGLE/COMPARE)
# ======================================================
def dataframe_height_for_rows(n_rows: int) -> int:
    return HEADER_HEIGHT + n_rows * ROW_HEIGHT

def show_overlay(player_ids: list[int], gw1: int, gw2: int):
    st.markdown(
        "<div style='background: rgba(0,0,0,0.05); padding: 15px; border-radius: 12px; margin-bottom: 16px;'>",
        unsafe_allow_html=True,
    )

    col_back, _ = st.columns([1, 4])
    with col_back:
        if st.button("⬅ Back to main dashboard & reset filters"):
            trigger_reset()
            st.rerun()

    contrib_dfs = []
    totals = []
    meta_rows = []

    per_player_hist = {}

    for pid in player_ids:
        p_row = players.loc[players["id"] == pid].iloc[0]
        pos = p_row["Position"]

        data = load_element_summary(int(pid))
        hist = pd.DataFrame(data.get("history", []))
        if hist.empty:
            st.info(f"No weekly data available for **{ID_TO_DISPLAY[int(pid)]}**.")
            continue

        # Keep full hist for GW breakdown (we filter inside)
        per_player_hist[int(pid)] = hist.copy()

        hist_range = hist[(hist["round"] >= gw1) & (hist["round"] <= gw2)].copy()

        contrib_df, total_pts = build_points_contribution(hist_range, pos)
        contrib_dfs.append(contrib_df)
        totals.append(total_pts)

        meta_rows.append(
            {
                "Player": ID_TO_DISPLAY[int(pid)],
                "Team": p_row["Team"],
                "Position": pos,
                "Price (£m)": round(float(p_row["Current Price"]), 1),
                "Selected %": round(float(p_row["Selected By %"]), 2),
                f"Points (GW {gw1}-{gw2})": int(total_pts),
            }
        )

    if not contrib_dfs:
        st.info("No contribution data found for the selected players in this range.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # Summary
    st.markdown("### 🔍 GW-Range Summary")
    meta_df = pd.DataFrame(meta_rows)
    st.dataframe(meta_df, width="stretch", hide_index=True, height=dataframe_height_for_rows(len(meta_df)))

    # FPL Points Contribution
    st.markdown("### 📊 FPL Points Contribution")

    if len(player_ids) == 1:
        df_single = contrib_dfs[0].copy()
        df_single["% of Total"] = df_single["% of Total"].map(lambda x: f"{x:.1f}%")
        h = dataframe_height_for_rows(len(df_single))
        st.dataframe(df_single, width="stretch", hide_index=True, height=h)

    else:
        # Comparison table with "points (xx.x%) ⭐"
        pnames = [ID_TO_DISPLAY[int(pid)] for pid in player_ids]
        cats = contrib_dfs[0]["Category"].tolist()

        # Ensure both tables share same categories/order (they should, by same position constraint)
        points_matrix = []
        for row_i in range(len(cats)):
            points_matrix.append([int(contrib_dfs[j]["Points"].iloc[row_i]) for j in range(len(pnames))])
        row_max = [max(r) for r in points_matrix]

        comp = pd.DataFrame({"Category": cats})
        for j, (name, dfc, tot) in enumerate(zip(pnames, contrib_dfs, totals)):
            cells = []
            for i in range(len(cats)):
                pts = int(dfc["Points"].iloc[i])
                pct = (pts / tot * 100.0) if tot else 0.0
                cell = f"{pts} ({pct:.1f}%)"
                if pts == row_max[i] and pts != 0:
                    cell += " ⭐"
                cells.append(cell)
            comp[name] = cells

        h = dataframe_height_for_rows(len(comp))
        st.dataframe(comp, width="stretch", hide_index=True, height=h)

    # Contribution bar chart (mirrors same categories)
    st.markdown("### 📊 Contribution by Category")
    bar = build_contrib_bar(contrib_dfs, [ID_TO_DISPLAY[int(pid)] for pid in player_ids])
    st.plotly_chart(bar, use_container_width=True)

    # GW breakdowns
    st.markdown("### 📅 Points Breakdown by Gameweek")
    if len(player_ids) == 1:
        pid = int(player_ids[0])
        render_gw_breakdown(ID_TO_DISPLAY[pid], per_player_hist[pid], gw1, gw2)
    else:
        cols = st.columns(2)
        for col, pid in zip(cols, player_ids[:2]):
            pid = int(pid)
            with col:
                render_gw_breakdown(ID_TO_DISPLAY[pid], per_player_hist[pid], gw1, gw2)

    st.markdown("</div>", unsafe_allow_html=True)

# ======================================================
# PAGE CONTENT
# ======================================================
st.markdown("<div class='main-container'>", unsafe_allow_html=True)
st.title("🔥 FPL Simple Analytics")
st.write("Live FPL data (cached) with GW-range value metrics and player analysis.")

# Overlay logic
if st.session_state.view_mode == "single" and st.session_state.primary_player_display != "None":
    pid = int(DISPLAY_TO_ID[st.session_state.primary_player_display])
    show_overlay([pid], gw_start, gw_end)

elif (
    st.session_state.view_mode == "compare"
    and st.session_state.primary_player_display != "None"
    and st.session_state.secondary_player_display != "None"
):
    pid1 = int(DISPLAY_TO_ID[st.session_state.primary_player_display])
    pid2 = int(DISPLAY_TO_ID[st.session_state.secondary_player_display])
    show_overlay([pid1, pid2], gw_start, gw_end)

# Main table hidden when in overlay view
if st.session_state.view_mode == "main":
    st.subheader("📊 Player Value Table")

    st.dataframe(
        table,
        width="stretch",
        hide_index=True,
        column_config={
            "Player": st.column_config.TextColumn("Player"),
            "Team": st.column_config.TextColumn("Team"),
            "Position": st.column_config.TextColumn("Pos"),
            "Points (GW Range)": st.column_config.NumberColumn(
                f"Points (GW {gw_start}-{gw_end})"
            ),
            "Current Price": st.column_config.NumberColumn("Price (£m)", format="£%.1f"),
            "Points Per Million": st.column_config.NumberColumn("PPM", format="%.2f"),
            "Selected By %": st.column_config.NumberColumn("Selected %", format="%.2f"),
            "Template Value": st.column_config.NumberColumn("Template Value", format="%.2f"),
            "Differential Value": st.column_config.NumberColumn("Differential Value", format="%.2f"),
        },
    )

st.markdown("</div>", unsafe_allow_html=True)
