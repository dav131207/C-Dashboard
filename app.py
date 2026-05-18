"""
Instagram Analytics Dashboard
Liest dynamisch alle Accounts aus dem data/-Ordner und
visualisiert Reichweite, Engagement, Format-Performance & Follower-Wachstum.
"""

import json
from datetime import date
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# --- Page setup ---
st.set_page_config(
    page_title="Instagram Dashboard",
    layout="wide",
    page_icon="📊",
    initial_sidebar_state="expanded",
)

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"

WEEKDAYS_DE = {
    "Monday": "Montag", "Tuesday": "Dienstag", "Wednesday": "Mittwoch",
    "Thursday": "Donnerstag", "Friday": "Freitag", "Saturday": "Samstag", "Sunday": "Sonntag",
}
WEEKDAY_ORDER = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


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
            "thumbnail": m.get("thumbnail_url") or m.get("media_url", ""),
            "reach": ins.get("reach", 0) or 0,
            "views": ins.get("views", 0) or 0,
            "likes": ins.get("likes", 0) or 0,
            "comments": ins.get("comments", 0) or 0,
            "saved": ins.get("saved", 0) or 0,
            "shares": ins.get("shares", 0) or 0,
            "total_interactions": ins.get("total_interactions", 0) or 0,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["timestamp"] = df["timestamp"].dt.tz_convert("Europe/Vienna")
    df["date"] = df["timestamp"].dt.date
    df["year"] = df["timestamp"].dt.year
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)
    df["weekday"] = df["timestamp"].dt.day_name().map(WEEKDAYS_DE)
    df["hour"] = df["timestamp"].dt.hour
    df["engagement_rate"] = (
        df["total_interactions"] / df["reach"].replace(0, pd.NA) * 100
    ).round(2)

    def fmt(row):
        if row["product_type"] == "REELS":
            return "Reel"
        if row["product_type"] == "CAROUSEL_ALBUM" or row["media_type"] == "CAROUSEL_ALBUM":
            return "Karussell"
        if row["media_type"] == "VIDEO":
            return "Video"
        return "Bild"
    df["format"] = df.apply(fmt, axis=1)
    return df


# --- Account Selection ---
if not DATA_DIR.exists():
    st.error("Der Ordner 'data' existiert nicht. Bitte führe zuerst `python fetch_data.py` aus.")
    st.stop()

# Finde alle verfügbaren Accounts basierend auf den Dateinamen
available_files = list(DATA_DIR.glob("instagram_data_*.json"))
if not available_files:
    st.error("Keine JSON-Dateien im Ordner 'data' gefunden.")
    st.stop()

account_names = [f.stem.replace("instagram_data_", "") for f in available_files]

# --- Sidebar ---
with st.sidebar:
    st.title("⚙️ Einstellungen")
    
    # Dropdown zur Account-Auswahl
    selected_account = st.selectbox("Instagram Account auswählen", sorted(account_names))
    
    data_file = DATA_DIR / f"instagram_data_{selected_account}.json"
    history_file = DATA_DIR / f"follower_history_{selected_account}.json"
    
    data = load_data(data_file)
    if not data:
        st.error("Fehler beim Laden der Datei.")
        st.stop()
        
    account = data.get("account", {})
    df_all = build_dataframe(data)
    follower_history = load_follower_history(history_file)

    st.divider()

    # Profil-Infos
    if account.get("profile_picture_url"):
        st.image(account["profile_picture_url"], width=80)
    st.markdown(f"### @{account.get('username', selected_account)}")

    col_a, col_b = st.columns(2)
    col_a.metric("Follower", f"{account.get('followers_count', 0):,}".replace(",", "."))
    col_b.metric("Posts", f"{account.get('media_count', 0):,}".replace(",", "."))
    
    # NEU: Tagesaktuelle Insights
    st.markdown("#### Heute (Letzte 24h)")
    col_c, col_d = st.columns(2)
    daily_insights = account.get("daily_insights", {})
    col_c.metric("Profilaufrufe", f"{daily_insights.get('profile_views', 0):,}".replace(",", "."))
    col_d.metric("Link-Klicks", f"{daily_insights.get('website_clicks', 0):,}".replace(",", "."))

    fetched = data.get("fetched_at", "")[:16].replace("T", " ")
    st.caption(f"🔄 Letztes API-Update: {fetched} UTC")

    st.divider()

    # Zeitraum-Filter
    st.markdown("### 📅 Filter")
    min_date = df_all["timestamp"].min().date() if not df_all.empty else date(2025, 1, 1)
    max_date = df_all["timestamp"].max().date() if not df_all.empty else date.today()
    default_start = max(date(2025, 1, 1), min_date)
    default_end = min(date(2025, 12, 31), max_date)

    date_range = st.date_input(
        "Zeitraum",
        value=(default_start, default_end),
        min_value=min_date,
        max_value=max_date,
        format="DD.MM.YYYY",
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = default_start, default_end

    formats_available = sorted(df_all["format"].unique().tolist()) if not df_all.empty else []
    selected_formats = st.multiselect(
        "Formate",
        formats_available,
        default=formats_available,
    )

# --- Filter anwenden ---
df = df_all[
    (df_all["timestamp"].dt.date >= start_date)
    & (df_all["timestamp"].dt.date <= end_date)
    & (df_all["format"].isin(selected_formats))
].copy()

# --- Main Content ---
st.title("Instagram Analytics Dashboard")
st.caption(f"Aktueller Filter: **{start_date.strftime('%d.%m.%Y')} – {end_date.strftime('%d.%m.%Y')}**  ·  "
           f"{len(df)} Posts einbezogen")

if df.empty:
    st.warning("Keine Posts im gewählten Zeitraum oder für die gewählten Formate gefunden.")
    st.stop()

# --- KPI cards ---
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Posts", f"{len(df):,}".replace(",", "."))
k2.metric("Gesamtreichweite", f"{int(df['reach'].sum()):,}".replace(",", "."))
k3.metric("Ø Reichweite/Post", f"{int(df['reach'].mean()):,}".replace(",", "."))
k4.metric("Gesamt-Interaktionen", f"{int(df['total_interactions'].sum()):,}".replace(",", "."))
mean_er = df["engagement_rate"].dropna().mean()
k5.metric("Ø Engagement-Rate", f"{mean_er:.2f}%" if pd.notna(mean_er) else "—")

st.divider()

# --- Tabs ---
tab_overview, tab_posts, tab_formats, tab_timing, tab_followers = st.tabs(
    ["📈 Übersicht", "🏆 Top Posts", "🎨 Formate", "🕐 Posting-Zeiten", "👥 Follower"]
)

# === ÜBERSICHT ===
with tab_overview:
    st.subheader("Reichweite über Zeit")
    daily = (
        df.groupby("date")[["reach", "total_interactions"]].sum().reset_index()
    )
    daily["date"] = pd.to_datetime(daily["date"])
    fig = px.area(daily, x="date", y="reach", labels={"date": "Datum", "reach": "Reichweite"})
    fig.update_layout(height=350, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Posts pro Monat")
    monthly = df.groupby("month").size().reset_index(name="Anzahl Posts")
    fig2 = px.bar(monthly, x="month", y="Anzahl Posts", labels={"month": "Monat"})
    fig2.update_layout(height=300, margin=dict(t=20, b=20))
    st.plotly_chart(fig2, use_container_width=True)

# === TOP POSTS ===
with tab_posts:
    st.subheader("Top Posts nach Reichweite")
    top_n = st.slider("Anzahl Posts anzeigen", 5, 50, 15)
    top = df.nlargest(top_n, "reach")[
        ["timestamp", "format", "caption", "reach", "likes", "comments", "saved", "shares", "engagement_rate", "permalink"]
    ].copy()
    top["timestamp"] = top["timestamp"].dt.strftime("%d.%m.%Y %H:%M")
    top = top.rename(columns={
        "timestamp": "Datum",
        "format": "Format",
        "caption": "Text",
        "reach": "Reichweite",
        "likes": "Likes",
        "comments": "Komm.",
        "saved": "Speicher.",
        "shares": "Shares",
        "engagement_rate": "ER %",
        "permalink": "Link",
    })
    st.dataframe(
        top,
        column_config={"Link": st.column_config.LinkColumn("Link", display_text="↗ ansehen")},
        hide_index=True,
        use_container_width=True,
    )

# === FORMATE ===
with tab_formats:
    st.subheader("Welches Format funktioniert am besten?")
    fmt_agg = df.groupby("format").agg(
        Posts=("id", "count"),
        Reichweite_Summe=("reach", "sum"),
        Reichweite_Schnitt=("reach", "mean"),
        Interaktionen_Schnitt=("total_interactions", "mean"),
        ER_Schnitt=("engagement_rate", "mean"),
    ).round(1).reset_index()
    st.dataframe(fmt_agg, hide_index=True, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(fmt_agg, x="format", y="Reichweite_Schnitt",
                     title="Ø Reichweite pro Format", labels={"format": "Format"})
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.bar(fmt_agg, x="format", y="ER_Schnitt",
                     title="Ø Engagement-Rate pro Format", labels={"format": "Format"})
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

# === TIMING ===
with tab_timing:
    st.subheader("Wann ist die beste Zeit zum Posten?")

    pivot = df.pivot_table(values="reach", index="weekday", columns="hour",
                           aggfunc="mean", fill_value=0)
    pivot = pivot.reindex([d for d in WEEKDAY_ORDER if d in pivot.index])

    fig = px.imshow(
        pivot,
        labels=dict(x="Uhrzeit", y="Wochentag", color="Ø Reichweite"),
        aspect="auto",
        color_continuous_scale="Viridis",
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Heatmap: Zeigt die durchschnittliche Reichweite je Wochentag und Uhrzeit. "
               "Dunkle Felder bedeuten, dass in diesem Slot kaum oder gar nicht gepostet wurde.")

# === FOLLOWER ===
with tab_followers:
    st.subheader("Follower-Wachstum")
    if follower_history.empty or len(follower_history) < 2:
        st.info(
            "Der Follower-Verlauf wird ab jetzt jeden Tag um 04:00 Uhr gespeichert. "
            "Sobald morgen der zweite Datenpunkt generiert wurde, siehst du hier den Wachstums-Graphen."
        )
    else:
        fig = px.line(
            follower_history, x="date", y="followers",
            labels={"date": "Datum", "followers": "Follower"},
            markers=True,
        )
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

        first, last = follower_history.iloc[0], follower_history.iloc[-1]
        delta = last["followers"] - first["followers"]
        days = (last["date"] - first["date"]).days or 1
        
        st.markdown("### Entwicklung")
        c1, c2, c3 = st.columns(3)
        c1.metric("Aktueller Stand", f"{last['followers']:,}".replace(",", "."))
        c2.metric("Wachstum im Zeitraum", f"{delta:+,}".replace(",", "."))
        c3.metric("Ø Wachstum pro Tag", f"{delta/days:+.1f}".replace(".", ","))

st.divider()
st.caption(
    "Dashboard basierend auf der offiziellen Instagram Graph API · "
    f"API-Version {data.get('api_version', '?')} · "
    "Daten werden automatisch täglich via GitHub Actions aktualisiert."
)
