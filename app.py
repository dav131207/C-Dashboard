"""
Instagram Analytics Dashboard - Editorial C& Design
Liest dynamisch alle Accounts aus dem data/-Ordner.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# --- Page setup ---
st.set_page_config(
    page_title="C& Analytics",
    layout="wide",
    page_icon="⬛",
    initial_sidebar_state="expanded",
)

# --- C& Custom CSS Styling ---
# Macht das Dashboard zu einer cleanen, markenkonformen Website
custom_css = """
<style>
    /* Verstecke das Streamlit Standard-Menü und Footer */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Mache Hauptüberschriften uppercase wie auf contemporaryand.com */
    h1, h2, h3 {
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 700 !important;
    }
    
    /* Minimalistische KPI Karten */
    [data-testid="stMetric"] {
        border-top: 2px solid #000;
        padding-top: 10px;
        background-color: #fff;
    }
    [data-testid="stMetricLabel"] {
        text-transform: uppercase;
        font-size: 0.85rem;
        letter-spacing: 0.5px;
        color: #666;
    }
    [data-testid="stMetricValue"] {
        font-size: 2rem !important;
        font-weight: 700;
        color: #000;
    }
    
    /* Cleane Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 0px;
        color: #666;
        text-transform: uppercase;
        font-weight: 600;
        font-size: 0.9rem;
        letter-spacing: 1px;
    }
    .stTabs [aria-selected="true"] {
        color: #000 !important;
        border-bottom: 2px solid #000 !important;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)


PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"

WEEKDAYS_DE = {
    "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag", "Sunday": "Sonntag",
}
WEEKDAY_ORDER = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# --- Helper Funktion für einheitliches Chart-Design ---
def apply_editorial_layout(fig):
    """Entfernt bunte Farben und Gitterlinien für den Editorial Look"""
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_family="sans-serif",
        font_color="#000000",
        margin=dict(t=30, b=20, l=0, r=0),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, title_text="")
    fig.update_yaxes(showgrid=True, gridcolor="#E5E5E5", zeroline=False, title_text="")
    return fig


# --- Data loading ---
@st.cache_data(ttl=300)
def load_data(file_path: Path) -> dict | None:
    if not file_path.exists():
        return None
    return json.loads(file_path.read_text(encoding="utf-8"))

@st.cache_data(ttl=300)
def load_follower_history(file_path: Path) -> pd.DataFrame:
    if not file_path.exists():
        return pd.DataFrame(columns=["date", "followers"])
    history = json.loads(file_path.read_text(encoding="utf-8"))
    df = pd.DataFrame(history)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df

def build_dataframe(data: dict) -> pd.DataFrame:
    rows = []
    for m in data.get("media", []):
        ins = m.get("insights", {}) or {}
        rows.append({
            "id": m["id"],
            "timestamp": pd.to_datetime(m["timestamp"]),
            "caption": (m.get("caption") or "").replace("\n", " ")[:120],
            "media_type": m.get("media_type", "UNKNOWN"),
            "product_type": m.get("media_product_type") or m.get("media_type", "UNKNOWN"),
            "permalink": m.get("permalink", ""),
            "reach": ins.get("reach", 0) or 0,
            "views": ins.get("views", 0) or 0,
            "likes": ins.get("likes", 0) or 0,
            "comments": ins.get("comments", 0) or 0,
            "saved": ins.get("saved", 0) or 0,
            "shares": ins.get("shares", 0) or 0,
            "total_interactions": ins.get("total_interactions", 0) or 0,
        })
    df = pd.DataFrame(rows)
    if df.empty: return df

    df["timestamp"] = df["timestamp"].dt.tz_convert("Europe/Vienna")
    df["date"] = df["timestamp"].dt.date
    df["year"] = df["timestamp"].dt.year
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)
    df["weekday"] = df["timestamp"].dt.day_name().map(WEEKDAYS_DE)
    df["hour"] = df["timestamp"].dt.hour
    df["engagement_rate"] = (df["total_interactions"] / df["reach"].replace(0, pd.NA) * 100).round(2)

    def fmt(row):
        if row["product_type"] == "REELS": return "Reel"
        if row["product_type"] == "CAROUSEL_ALBUM" or row["media_type"] == "CAROUSEL_ALBUM": return "Karussell"
        if row["media_type"] == "VIDEO": return "Video"
        return "Bild"
    df["format"] = df.apply(fmt, axis=1)
    return df

# --- Account Selection ---
if not DATA_DIR.exists():
    st.error("Der Ordner 'data' existiert nicht.")
    st.stop()

available_files = list(DATA_DIR.glob("instagram_data_*.json"))
if not available_files:
    st.error("Keine JSON-Dateien im Ordner gefunden.")
    st.stop()

account_names = [f.stem.replace("instagram_data_", "") for f in available_files]

# --- Sidebar ---
with st.sidebar:
    st.markdown("## C& ANALYTICS")
    selected_account = st.selectbox("ACCOUNT AUSWÄHLEN", sorted(account_names), label_visibility="collapsed")
    
    data_file = DATA_DIR / f"instagram_data_{selected_account}.json"
    history_file = DATA_DIR / f"follower_history_{selected_account}.json"
    
    data = load_data(data_file)
    if not data:
        st.stop()
        
    account = data.get("account", {})
    df_all = build_dataframe(data)
    follower_history = load_follower_history(history_file)

    st.divider()

    st.markdown(f"**@{account.get('username', selected_account)}**")
    col_a, col_b = st.columns(2)
    col_a.metric("Follower", f"{account.get('followers_count', 0):,}".replace(",", "."))
    col_b.metric("Posts", f"{account.get('media_count', 0):,}".replace(",", "."))
    
    st.markdown("<br><b>HEUTE (24H)</b>", unsafe_allow_html=True)
    col_c, col_d = st.columns(2)
    daily_insights = account.get("daily_insights", {})
    col_c.metric("Profilaufrufe", f"{daily_insights.get('profile_views', 0):,}".replace(",", "."))
    col_d.metric("Link-Klicks", f"{daily_insights.get('website_clicks', 0):,}".replace(",", "."))

    st.divider()

    st.markdown("<b>FILTER</b>", unsafe_allow_html=True)
    min_date = df_all["timestamp"].min().date() if not df_all.empty else date(2025, 1, 1)
    max_date = df_all["timestamp"].max().date() if not df_all.empty else date.today()

    date_range = st.date_input(
        "ZEITRAUM",
        value=(max(date(2025, 1, 1), min_date), min(date(2025, 12, 31), max_date)),
        min_value=min_date, max_value=max_date, format="DD.MM.YYYY",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date

    formats_available = sorted(df_all["format"].unique().tolist()) if not df_all.empty else []
    selected_formats = st.multiselect("FORMATE", formats_available, default=formats_available)

df = df_all[(df_all["timestamp"].dt.date >= start_date) & (df_all["timestamp"].dt.date <= end_date) & (df_all["format"].isin(selected_formats))].copy()

# --- Main Content ---
st.title("EDITORIAL DASHBOARD")
st.markdown(f"**Zeitraum:** {start_date.strftime('%d.%m.%Y')} – {end_date.strftime('%d.%m.%Y')} &nbsp;&nbsp;|&nbsp;&nbsp; **{len(df)} Posts**")

if df.empty:
    st.warning("Keine Daten im Filter.")
    st.stop()

st.write("") # Spacer

# --- KPI cards ---
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Posts", f"{len(df):,}".replace(",", "."))
k2.metric("Reichweite", f"{int(df['reach'].sum()):,}".replace(",", "."))
k3.metric("Ø Reichweite", f"{int(df['reach'].mean()):,}".replace(",", "."))
k4.metric("Interaktionen", f"{int(df['total_interactions'].sum()):,}".replace(",", "."))
mean_er = df["engagement_rate"].dropna().mean()
k5.metric("Ø Engagement", f"{mean_er:.2f}%" if pd.notna(mean_er) else "—")

st.markdown("<br>", unsafe_allow_html=True)

# --- Tabs ---
tab_overview, tab_posts, tab_formats, tab_timing, tab_followers = st.tabs(
    ["ÜBERSICHT", "TOP POSTS", "FORMATE", "TIMING", "FOLLOWER"]
)

# === ÜBERSICHT ===
with tab_overview:
    st.subheader("Reichweiten-Verlauf")
    daily = df.groupby("date")[["reach", "total_interactions"]].sum().reset_index()
    # Schwarze Linie mit grauem Area-Fill drunter
    fig = px.area(daily, x="date", y="reach", color_discrete_sequence=["#000000"])
    fig.update_traces(fillcolor='rgba(0,0,0,0.1)', line=dict(width=2))
    st.plotly_chart(apply_editorial_layout(fig), use_container_width=True)

# === TOP POSTS ===
with tab_posts:
    st.subheader("Beste Performance")
    top = df.nlargest(15, "reach")[["timestamp", "format", "caption", "reach", "engagement_rate", "permalink"]].copy()
    top["timestamp"] = top["timestamp"].dt.strftime("%d.%m.")
    top = top.rename(columns={"timestamp": "Datum", "format": "Format", "caption": "Text", "reach": "Reichweite", "engagement_rate": "ER %", "permalink": "Link"})
    st.dataframe(top, column_config={"Link": st.column_config.LinkColumn("Link", display_text="Ansehen")}, hide_index=True, use_container_width=True)

# === FORMATE ===
with tab_formats:
    st.subheader("Format Analyse")
    fmt_agg = df.groupby("format").agg(Posts=("id", "count"), Reichweite=("reach", "mean"), ER=("engagement_rate", "mean")).round(1).reset_index()
    
    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(fmt_agg, x="format", y="Reichweite", title="Ø REICHWEITE PRO FORMAT", color_discrete_sequence=["#000000"])
        st.plotly_chart(apply_editorial_layout(fig), use_container_width=True)
    with col2:
        fig = px.bar(fmt_agg, x="format", y="ER", title="Ø ENGAGEMENT PRO FORMAT", color_discrete_sequence=["#666666"])
        st.plotly_chart(apply_editorial_layout(fig), use_container_width=True)

# === TIMING ===
with tab_timing:
    st.subheader("Performance nach Zeit")
    pivot = df.pivot_table(values="reach", index="weekday", columns="hour", aggfunc="mean", fill_value=0)
    pivot = pivot.reindex([d for d in WEEKDAY_ORDER if d in pivot.index])
    
    # Monochromes (Graustufen) Mapping für die Heatmap
    fig = px.imshow(pivot, aspect="auto", color_continuous_scale="gray_r")
    fig = apply_editorial_layout(fig)
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, use_container_width=True)

# === FOLLOWER ===
with tab_followers:
    st.subheader("Community Wachstum")
    if len(follower_history) < 2:
        st.info("Daten werden ab heute gesammelt. Der Graph erscheint morgen.")
    else:
        fig = px.line(follower_history, x="date", y="followers", color_discrete_sequence=["#000000"], markers=True)
        st.plotly_chart(apply_editorial_layout(fig), use_container_width=True)
