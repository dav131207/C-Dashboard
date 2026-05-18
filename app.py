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

# --- Custom CSS (C& Magazin-Look) ---
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
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        font_family="'Helvetica Neue', Helvetica, Arial, sans-serif", font_color="#000000",
        margin=dict(t=40, b=30, l=0, r=0),
        hoverlabel=dict(bgcolor="#ffffff", font_size=13, bordercolor="#cccccc"),
        hovermode="x unified"
    )
    fig.update_xaxes(showgrid=False, zeroline=False, title_text="", tickfont=dict(color="#888888", size=11), tickpadding=10)
    fig.update_yaxes(showgrid=True, gridcolor="#F0F0F0", zeroline=False, title_text="", tickfont=dict(color="#888888", size=11), tickpadding=10)
    return fig

# --- Lade-Funktionen ---
def load_json(file_path: Path):
    return json.loads(file_path.read_text(encoding="utf-8")) if file_path.exists() else None

# --- Main App Logic ---
if not DATA_DIR.exists():
    st.error("Der Ordner 'data' wurde nicht gefunden.")
    st.stop()

available_files = list(DATA_DIR.glob("instagram_data_*.json"))
if not available_files:
    st.error("Keine Profildaten im Ordner 'data' gefunden.")
    st.stop()

account_names = [f.stem.replace("instagram_data_", "") for f in available_files]

with st.sidebar:
    logo_png = PROJECT_ROOT / "logo.png"
    logo_jpg = PROJECT_ROOT / "logo.jpg"
    if logo_png.exists(): st.image(str(logo_png), use_container_width=True)
    elif logo_jpg.exists(): st.image(str(logo_jpg), use_container_width=True)
    else: st.markdown("## C& ANALYTICS")
        
    st.markdown("<br>", unsafe_allow_html=True)
    selected_account = st.selectbox("ACCOUNT", sorted(account_names), label_visibility="collapsed")
    
    raw_data = load_json(DATA_DIR / f"instagram_data_{selected_account}.json")
    if not raw_data or "media" not in raw_data:
        st.error(f"Die Datei für @{selected_account} enthält keine gültigen Daten.")
        st.stop()
        
    account = raw_data.get("account", {})
    
    st.divider()
    st.markdown(f"**@{account.get('username', selected_account)}**")
    st.metric("Follower", f"{account.get('followers_count', 0):,}".replace(",", "."))
    
    daily_insights = account.get("daily_insights", {})
    st.markdown("<br><b>TRAFFIC HEUTE (24H)</b>", unsafe_allow_html=True)
    col_c, col_d = st.columns(2)
    col_c.metric("Profilaufrufe", f"{daily_insights.get('profile_views', 0):,}".replace(",", "."))
    col_d.metric("Link-Klicks", f"{daily_insights.get('website_clicks', 0):,}".replace(",", "."))
    st.divider()
    
    start_date, end_date = st.date_input("ZEITRAUM", value=(date(2023, 1, 1), date.today()), format="DD.MM.YYYY")

# --- Datenaufbereitung ---
posts_list = []
for m in raw_data.get("media", []):
    ins = m.get("insights", {}) or {}
    
    try:
        dt = pd.to_datetime(m["timestamp"]).tz_convert("Europe/Vienna").date()
    except:
        continue
        
    if dt < start_date or dt > end_date:
        continue
        
    reach = int(ins.get("reach", 0) or 0)
    interactions = int(ins.get("total_interactions", 0) or 0)
    
    er = 0.0
    if reach > 0:
        er = round((interactions / reach) * 100, 2)
        
    prod_type = m.get("media_product_type") or m.get("media_type", "UNKNOWN")
    fmt = "Bild"
    if prod_type == "REELS": fmt = "Reel"
    elif "CAROUSEL" in prod_type: fmt = "Karussell"
    elif prod_type == "VIDEO": fmt = "Video"
    
    posts_list.append({
        "Datum": dt,
        "Format": fmt,
        "Text": (m.get("caption") or "").replace("\n", " ")[:120],
        "Reichweite": reach,
        "Interaktionen": interactions,
        "ER %": er,
        "Link": m.get("permalink", "")
    })

if not posts_list:
    st.warning("Keine Beiträge im gewählten Zeitraum gefunden.")
    st.stop()

df = pd.DataFrame(posts_list)

avg_reach = int(df["Reichweite"].mean())
max_reach = int(df["Reichweite"].max())
total_interactions = int(df["Interaktionen"].sum())
avg_er = df["ER %"].mean()

st.title("EDITORIAL DASHBOARD")
st.markdown(f"<span style='color:#666; font-size:1.1rem; letter-spacing:0.5px;'><b>ZEITRAUM:</b> {start_date.strftime('%d.%m.%Y')} – {end_date.strftime('%d.%m.%Y')} &nbsp;&nbsp;|&nbsp;&nbsp; <b>{len(df)} BEITRÄGE</b></span>", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Ø Reichweite pro Post", f"{avg_reach:,}".replace(",", "."))
k2.metric("Max. Reichweite (Peak)", f"{max_reach:,}".replace(",", "."))
k3.metric("Total Interaktionen", f"{total_interactions:,}".replace(",", "."))
k4.metric("Ø Engagement-Rate", f"{avg_er:.2f}%")

st.markdown("<br><br>", unsafe_allow_html=True)

# --- Tabs ---
tab_posts, tab_formats, tab_stories, tab_traffic = st.tabs(["MAIN FEED", "FORMATE", "STORIES ARCHIV", "TRAFFIC & COMMUNITY"])

with tab_posts:
    st.markdown("### REICHWEITEN-VERLAUF FEED")
    daily_chart_data = df.groupby("Datum")["Reichweite"].sum().reset_index()
    daily_chart_data["Datum"] = pd.to_datetime(daily_chart_data["Datum"])
    
    fig = px.area(daily_chart_data, x="Datum", y="Reichweite", color_discrete_sequence=["#000000"])
    fig.update_traces(fillcolor='rgba(0,0,0,0.04)', line=dict(width=2), hovertemplate="Reichweite: %{y:,.0f}<extra></extra>")
    fig.update_xaxes(tickformat="%d.%m.%Y")
    st.plotly_chart(apply_editorial_layout(fig), use_container_width=True)

    st.markdown("<br>### TOP BEITRÄGE", unsafe_allow_html=True)
    st.dataframe(
        df.nlargest(10, "Reichweite")[["Datum", "Format", "Text", "Reichweite", "ER %", "Link"]],
        column_config={"Link": st.column_config.LinkColumn("Link", display_text="↗ Ansehen"), "Datum": st.column_config.DateColumn(format="DD.MM.YYYY")},
        hide_index=True, use_container_width=True
    )

with tab_formats:
    st.markdown("### FORMAT-PERFORMANCE")
    
    format_stats = {}
    for p in posts_list:
        f = p["Format"]
        if f not in format_stats:
            format_stats[f] = {"count": 0, "reach_sum": 0, "er_sum": 0}
        format_stats[f]["count"] += 1
        format_stats[f]["reach_sum"] += p["Reichweite"]
        format_stats[f]["er_sum"] += p["ER %"]
        
    fmt_data_list = []
    for f, stats in format_stats.items():
        fmt_data_list.append({
            "Format": f,
            "Ø Reichweite": int(stats["reach_sum"] / stats["count"]),
            "Ø Engagement %": round(stats["er_sum"] / stats["count"], 2)
        })
        
    # Hier erstellen wir den expliziten DataFrame für Plotly, damit die Achsen sofort da sind!
    df_fmt = pd.DataFrame(fmt_data_list)

    col1, col2 = st.columns(2)
    with col1:
        fig1 = px.bar(df_fmt, x="Format", y="Ø Reichweite", color_discrete_sequence=["#000000"])
        fig1.update_traces(
            text=df_fmt["Ø Reichweite"].apply(lambda x: f"{x:,}".replace(",", ".")), 
            textposition="outside", 
            hovertemplate="Ø Reichweite: %{y:,.0f}<extra></extra>"
        )
        fig1.update_layout(title="Ø REICHWEITE PRO FORMAT", bargap=0.3)
        st.plotly_chart(apply_editorial_layout(fig1), use_container_width=True)
        
    with col2:
        fig2 = px.bar(df_fmt, x="Format", y="Ø Engagement %", color_discrete_sequence=["#888888"])
        fig2.update_traces(
            text=df_fmt["Ø Engagement %"].apply(lambda x: f"{x}%"), 
            textposition="outside", 
            hovertemplate="Ø Engagement: %{y}%<extra></extra>"
        )
        fig2.update_layout(title="Ø ENGAGEMENT PRO FORMAT", bargap=0.3)
        st.plotly_chart(apply_editorial_layout(fig2), use_container_width=True)

with tab_stories:
    st.markdown("### STORY PERFORMANCE")
    stories_file = DATA_DIR / f"stories_history_{selected_account}.json"
    stories_data = load_json(stories_file) or []
    
    if not stories_data:
        st.info("Das Story-Archiv füllt sich ab dem nächsten automatischen API-Lauf morgen um 04:00 Uhr.")
    else:
        st.success(f"{len(stories_data)} archivierte Stories im System gefunden.")

with tab_traffic:
    st.markdown("### TRAFFIC TIMELINE")
    history_file = DATA_DIR / f"follower_history_{selected_account}.json"
    history_data = load_json(history_file) or []
    
    if len(history_data) < 2:
        st.info("Der Traffic-Verlauf baut sich ab dem nächsten automatischen Lauf morgen auf.")
    else:
        hist_df = pd.DataFrame(history_data)
        
        # Traffic-Meldung auch via sauberem DataFrame-px-Befehl
        fig_traf = px.line(hist_df, x="date", y=["profile_views", "website_clicks"], color_discrete_sequence=["#000000", "#aaaaaa"])
        fig_traf.update_traces(mode="lines+markers", marker=dict(size=6))
        st.plotly_chart(apply_editorial_layout(fig_traf), use_container_width=True)

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
