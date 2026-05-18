"""
Instagram Analytics Dashboard - Editorial C& Design (Premium Visuals)
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="C& Analytics", layout="wide", page_icon="⬛", initial_sidebar_state="expanded")

# --- Custom CSS (Magazin-Look & saubere KPIs) ---
custom_css = """
<style>
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
    h1, h2, h3 { text-transform: uppercase; letter-spacing: 1.5px; font-weight: 700 !important; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; }
    [data-testid="stMetric"] { border-top: 2px solid #000; padding-top: 15px; background-color: #fff; }
    [data-testid="stMetricLabel"] { text-transform: uppercase; font-size: 0.8rem; letter-spacing: 1px; color: #888; font-weight: 600; }
    [data-testid="stMetricValue"] { font-size: 2.2rem !important; font-weight: 700; color: #000; letter-spacing: -0.5px; }
    .stTabs [data-baseweb="tab-list"] { gap: 30px; border-bottom: 1px solid #E5E5E5; }
    .stTabs [data-baseweb="tab"] { height: 50px; white-space: pre-wrap; background-color: transparent; border-radius: 0px; color: #888; text-transform: uppercase; font-weight: 600; font-size: 0.85rem; letter-spacing: 1px; }
    .stTabs [aria-selected="true"] { color: #000 !important; border-bottom: 3px solid #000 !important; }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"

# --- Premium Editorial Chart Layout ---
def apply_editorial_layout(fig):
    """Verpasst allen Diagrammen den edlen C& Magazin-Look"""
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font_family="'Helvetica Neue', Helvetica, Arial, sans-serif",
        font_color="#000000",
        margin=dict(t=40, b=30, l=0, r=0),
        # Elegante Hover-Effekte (Tooltips)
        hoverlabel=dict(
            bgcolor="#ffffff",
            font_size=13,
            font_family="'Helvetica Neue', Helvetica, Arial, sans-serif",
            bordercolor="#cccccc"
        ),
        hovermode="x unified" # Zieht eine schöne vertikale Linie über alle Datenpunkte beim Drüberfahren
    )
    fig.update_xaxes(
        showgrid=False, zeroline=False, title_text="", 
        tickfont=dict(color="#888888", size=11), tickpadding=10
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="#F0F0F0", zeroline=False, title_text="", 
        tickfont=dict(color="#888888", size=11), tickpadding=10
    )
    return fig

# --- Lade-Funktionen ---
@st.cache_data(ttl=300)
def load_json(file_path: Path):
    return json.loads(file_path.read_text(encoding="utf-8")) if file_path.exists() else None

@st.cache_data(ttl=300)
def load_history(file_path: Path) -> pd.DataFrame:
    data = load_json(file_path) or []
    df = pd.DataFrame(data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        if "website_clicks" not in df.columns: df["website_clicks"] = 0
        if "profile_views" not in df.columns: df["profile_views"] = 0
    return df

@st.cache_data(ttl=300)
def build_stories_df(file_path: Path) -> pd.DataFrame:
    data = load_json(file_path) or []
    rows = []
    for s in data:
        ins = s.get("insights", {})
        rows.append({
            "timestamp": pd.to_datetime(s.get("timestamp", "")),
            "reach": ins.get("reach", 0) or 0,
            "impressions": ins.get("impressions", 0) or 0,
            "replies": ins.get("replies", 0) or 0,
            "exits": ins.get("exits", 0) or 0,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = df["timestamp"].dt.tz_convert("Europe/Vienna")
        df["date"] = df["timestamp"].dt.date
    return df

@st.cache_data(ttl=300)
def build_dataframe(data: dict) -> pd.DataFrame:
    rows = []
    for m in data.get("media", []):
        ins = m.get("insights", {}) or {}
        rows.append({
            "id": m["id"], "timestamp": pd.to_datetime(m["timestamp"]),
            "caption": (m.get("caption") or "").replace("\n", " ")[:120],
            "type": m.get("media_product_type") or m.get("media_type", "UNKNOWN"),
            "permalink": m.get("permalink", ""),
            "reach": ins.get("reach", 0) or 0, "total_interactions": ins.get("total_interactions", 0) or 0,
        })
    df = pd.DataFrame(rows)
    if df.empty: return df
    df["timestamp"] = df["timestamp"].dt.tz_convert("Europe/Vienna")
    df["date"] = df["timestamp"].dt.date
    
    # Absolute crash-sichere Berechnung der Engagement Rate (behebt den Runden-Fehler vollständig)
    def calc_er(row):
        if row["reach"] > 0:
            return round((row["total_interactions"] / row["reach"]) * 100, 2)
        return float("nan")
        
    df["engagement_rate"] = df.apply(calc_er, axis=1)
    
    df["format"] = df["type"].apply(lambda x: "Reel" if x == "REELS" else "Karussell" if "CAROUSEL" in x else "Video" if x == "VIDEO" else "Bild")
    return df

# --- Init & Sidebar ---
if not DATA_DIR.exists(): st.stop()
available_files = list(DATA_DIR.glob("instagram_data_*.json"))
if not available_files: st.stop()
account_names = [f.stem.replace("instagram_data_", "") for f in available_files]

with st.sidebar:
    # 1. LOGO INTEGRATION (Prüft ob logo.png oder logo.jpg existiert)
    logo_png = PROJECT_ROOT / "logo.png"
    logo_jpg = PROJECT_ROOT / "logo.jpg"
    
    if logo_png.exists():
        st.image(str(logo_png), use_container_width=True)
    elif logo_jpg.exists():
        st.image(str(logo_jpg), use_container_width=True)
    else:
        st.markdown("## C& ANALYTICS") # Fallback, falls noch kein Logo hochgeladen wurde
        
    st.markdown("<br>", unsafe_allow_html=True)
        
    selected_account = st.selectbox("ACCOUNT", sorted(account_names), label_visibility="collapsed")
    
    data = load_json(DATA_DIR / f"instagram_data_{selected_account}.json")
    if not data: st.stop()
    
    account = data.get("account", {})
    df_all = build_dataframe(data)
    df_history = load_history(DATA_DIR / f"follower_history_{selected_account}.json")
    df_stories = build_stories_df(DATA_DIR / f"stories_history_{selected_account}.json")

    st.divider()
    st.markdown(f"**@{account.get('username', selected_account)}**")
    st.metric("Follower", f"{account.get('followers_count', 0):,}".replace(",", "."))
    
    st.markdown("<br><b>TRAFFIC HEUTE (24H)</b>", unsafe_allow_html=True)
    col_c, col_d = st.columns(2)
    col_c.metric("Profilaufrufe", f"{account.get('daily_insights', {}).get('profile_views', 0):,}".replace(",", "."))
    col_d.metric("Link-Klicks", f"{account.get('daily_insights', {}).get('website_clicks', 0):,}".replace(",", "."))
    st.divider()
    
    start_date, end_date = st.date_input("ZEITRAUM", value=(date(2023, 1, 1), date.today()), format="DD.MM.YYYY")

df = df_all[(df_all["timestamp"].dt.date >= start_date) & (df_all["timestamp"].dt.date <= end_date)].copy()

st.title("EDITORIAL DASHBOARD")
st.markdown(f"<span style='color:#666; font-size:1.1rem; letter-spacing:0.5px;'><b>ZEITRAUM:</b> {start_date.strftime('%d.%m.%Y')} – {end_date.strftime('%d.%m.%Y')} &nbsp;&nbsp;|&nbsp;&nbsp; <b>{len(df)} BEITRÄGE</b></span>", unsafe_allow_html=True)
if df.empty: st.stop()

st.markdown("<br>", unsafe_allow_html=True)

# --- KPIs ---
k1, k2, k3, k4 = st.columns(4)
k1.metric("Ø Reichweite pro Post", f"{int(df['reach'].mean()):,}".replace(",", "."))
k2.metric("Max. Reichweite (Peak)", f"{int(df['reach'].max()):,}".replace(",", "."))
k3.metric("Total Interaktionen", f"{int(df['total_interactions'].sum()):,}".replace(",", "."))
mean_er = df["engagement_rate"].dropna().mean()
k4.metric("Ø Engagement-Rate", f"{mean_er:.2f}%" if pd.notna(mean_er) else "—")
st.markdown("<br><br>", unsafe_allow_html=True)

# --- Tabs ---
tab_posts, tab_formats, tab_stories, tab_traffic = st.tabs(["MAIN FEED", "FORMATE", "STORIES ARCHIV", "TRAFFIC & COMMUNITY"])

with tab_posts:
    st.markdown("### REICHWEITEN-VERLAUF FEED")
    daily = df.groupby("date")[["reach", "total_interactions"]].sum().reset_index()
    
    # Premium Line-Chart für Reichweite
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["reach"],
        mode='lines',
        line=dict(color='#000000', width=2),
        fill='tozeroy', # Sanfte Schattierung nach unten
        fillcolor='rgba(0,0,0,0.04)',
        name="Reichweite",
        hovertemplate="<b>%{x|%d.%m.%Y}</b><br>Reichweite: %{y:,.0f}<extra></extra>"
    ))
    st.plotly_chart(apply_editorial_layout(fig), use_container_width=True)

    st.markdown("<br>### TOP BEITRÄGE", unsafe_allow_html=True)
    st.dataframe(
        df.nlargest(10, "reach")[["date", "format", "caption", "reach", "engagement_rate", "permalink"]].rename(
            columns={"date": "Datum", "format": "Format", "caption": "Text", "reach": "Reichweite", "engagement_rate": "ER %", "permalink": "Link"}
        ),
        column_config={"Link": st.column_config.LinkColumn("Link", display_text="↗ Ansehen")}, hide_index=True, use_container_width=True
    )

with tab_formats:
    st.markdown("### FORMAT-PERFORMANCE")
    fmt_agg = df.groupby("format").agg(Posts=("id", "count"), Reichweite=("reach", "mean"), ER=("engagement_rate", "mean")).round(1).reset_index()
    
    col1, col2 = st.columns(2)
    with col1:
        # Premium Bar-Chart
        fig1 = go.Figure(data=[go.Bar(
            x=fmt_agg["format"], y=fmt_agg["Reichweite"],
            marker_color="#000000",
            text=fmt_agg["Reichweite"].apply(lambda x: f"{x:,.0f}"), # Zahlen direkt über den Balken
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Ø Reichweite: %{y:,.0f}<extra></extra>"
        )])
        fig1.update_layout(title="Ø REICHWEITE PRO FORMAT", bargap=0.3)
        st.plotly_chart(apply_editorial_layout(fig1), use_container_width=True)
        
    with col2:
        fig2 = go.Figure(data=[go.Bar(
            x=fmt_agg["format"], y=fmt_agg["ER"],
            marker_color="#888888",
            text=fmt_agg["ER"].apply(lambda x: f"{x}%"),
            textposition="outside",
            hovertemplate="<b>%{x}</b><br>Ø Engagement: %{y}%<extra></extra>"
        )])
        fig2.update_layout(title="Ø ENGAGEMENT PRO FORMAT", bargap=0.3)
        st.plotly_chart(apply_editorial_layout(fig2), use_container_width=True)

with tab_stories:
    st.markdown("### STORY PERFORMANCE")
    if df_stories.empty:
        st.info("Das Story-Archiv füllt sich ab dem nächsten automatischen Lauf.")
    else:
        df_st = df_stories[(df_stories["date"] >= start_date) & (df_stories["date"] <= end_date)]
        c1, c2, c3 = st.columns(3)
        c1.metric("Gespeicherte Stories", len(df_st))
        c2.metric("Ø Story Reichweite", f"{int(df_st['reach'].mean()):,}".replace(",", ".") if not df_st.empty else 0)
        c3.metric("Ø Antworten (Replies)", f"{int(df_st['replies'].mean())}" if not df_st.empty else 0)
        
        daily_st = df_st.groupby("date")["reach"].mean().reset_index()
        fig_st = go.Figure(data=[go.Bar(
            x=daily_st["date"], y=daily_st["reach"],
            marker_color="#000000",
            hovertemplate="<b>%{x|%d.%m.%Y}</b><br>Ø Reichweite: %{y:,.0f}<extra></extra>"
        )])
        fig_st.update_layout(title="Ø STORY-REICHWEITE PRO TAG", bargap=0.1)
        st.plotly_chart(apply_editorial_layout(fig_st), use_container_width=True)

with tab_traffic:
    st.markdown("### TRAFFIC TIMELINE")
    if len(df_history) < 2:
        st.info("Der Traffic-Tracker wurde aktiviert. Die Timeline baut sich ab morgen auf.")
    else:
        # Premium Multi-Line Chart für Traffic
        fig_traf = go.Figure()
        fig_traf.add_trace(go.Scatter(
            x=df_history["date"], y=df_history["profile_views"],
            mode="lines+markers",
            name="Profilaufrufe",
            line=dict(color="#000000", width=3),
            marker=dict(size=6, color="#000000"),
            hovertemplate="Aufrufe: %{y:,.0f}<extra></extra>"
        ))
        fig_traf.add_trace(go.Scatter(
            x=df_history["date"], y=df_history["website_clicks"],
            mode="lines+markers",
            name="Website Klicks",
            line=dict(color="#aaaaaa", width=3, dash='dot'),
            marker=dict(size=6, color="#aaaaaa"),
            hovertemplate="Klicks: %{y:,.0f}<extra></extra>"
        ))
        fig_traf = apply_editorial_layout(fig_traf)
        fig_traf.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
        st.plotly_chart(fig_traf, use_container_width=True)

# --- Footer ---
st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="text-align: center; padding-top: 20px; border-top: 1px solid #E5E5E5; color: #888888; font-size: 0.75rem; letter-spacing: 1.5px; font-weight: 600; text-transform: uppercase;">
        Built with love ❤️
    </div>
    """,
    unsafe_allow_html=True
)
