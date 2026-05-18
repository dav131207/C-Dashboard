#!/usr/bin/env python3
"""
Instagram Business Account Data Fetcher
Zieht Account-Daten, tagesaktuelle Insights und Medien-Statistiken via Graph API.
Ausgelegt auf Multi-Account-Betrieb via GitHub Actions Matrix.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# --- Systemkonfiguration ---
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
IG_USER_ID = os.environ.get("INSTAGRAM_USER_ID")
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# --- Filter-Parameter ---
MAX_POSTS_TO_PROCESS = 500
MAX_AGE_YEARS = 2

# --- Pfade ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"

# --- Metrik-Definitionen ---
# Dynamische Anpassung nach Alter und Typ, um API-Fehler zu vermeiden
# WICHTIG: 'impressions' wurde entfernt, da ab v22.0 nicht mehr unterstützt
METRICS_RECENT = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions"]
METRICS_OLD = ["reach", "likes", "comments", "saved", "shares"]
REELS_EXTRA = ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]


def die(msg: str) -> None:
    """Bricht das Skript mit einer Fehlermeldung ab."""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def check_env() -> None:
    """Prüft, ob alle notwendigen Umgebungsvariablen gesetzt sind."""
    if not ACCESS_TOKEN:
        die("INSTAGRAM_ACCESS_TOKEN env var not set")
    if not IG_USER_ID:
        die("INSTAGRAM_USER_ID env var not set")


def get_json(url: str, params: dict | None = None) -> dict:
    """Führt einen GET-Request aus inklusive Retry-Logik bei Rate-Limits."""
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"   Netzwerkfehler (Versuch {attempt + 1}): {e}")
            time.sleep(2 ** attempt)
            continue
        
        if r.status_code == 200:
            return r.json()
        
        if r.status_code in (429, 503):
            wait = 5 * (attempt + 1)
            print(f"   Rate-Limit erreicht, warte {wait} Sekunden...")
            time.sleep(wait)
            continue
            
        print(f"   HTTP {r.status_code}: {r.text[:200]}")
        return {}
    return {}


def check_token_expiry() -> None:
    """Prüft die verbleibende Gültigkeit des Access Tokens."""
    url = f"{BASE_URL}/debug_token"
    params = {"input_token": ACCESS_TOKEN, "access_token": ACCESS_TOKEN}
    data = get_json(url, params).get("data", {})
    expires_at = data.get("expires_at")
    
    if expires_at:
        days_left = (datetime.fromtimestamp(expires_at, timezone.utc) - datetime.now(timezone.utc)).days
        print(f"Token laeuft ab in {days_left} Tagen (am {datetime.fromtimestamp(expires_at).date()})")
        if days_left < 10:
            print("WARNUNG: Token laeuft bald ab. Bitte zeitnah erneuern.")


def get_account_info() -> dict:
    """Zieht allgemeine Account-Informationen sowie tagesaktuelle Profil-Insights."""
    # 1. Basis-Informationen (Follower, Biografie, etc.)
    base_url = f"{BASE_URL}/{IG_USER_ID}"
    params_base = {
        "fields": "id,username,followers_count,follows_count,media_count,profile_picture_url,name",
        "access_token": ACCESS_TOKEN,
    }
    account_data = get_json(base_url, params_base)

    # 2. Account Insights (Website-Klicks, Profilaufrufe der letzten 24h)
    insights_url = f"{BASE_URL}/{IG_USER_ID}/insights"
    params_insights = {
        "metric": "profile_views,website_clicks",
        "period": "day",
        "metric_type": "total_value",  # Zwingend erforderlich für neuere API Versionen
        "access_token": ACCESS_TOKEN,
    }
    insights_data = get_json(insights_url, params_insights)
    
    # Insights in die Account-Daten mergen
    account_data["daily_insights"] = {}
    for item in insights_data.get("data", []):
        name = item.get("name")
        values = item.get("values", [])
        if values:
            account_data["daily_insights"][name] = values[0].get("value", 0)

    return account_data


def get_all_media() -> list[dict]:
    """Zieht Medien-Beitraege bis zum definierten Limit (Anzahl oder Alter)."""
    media: list[dict] = []
    url = f"{BASE_URL}/{IG_USER_ID}/media"
    params: dict | None = {
        "fields": "id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,timestamp",
        "limit": 100,
        "access_token": ACCESS_TOKEN,
    }
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_YEARS * 365)

    while url and len(media) < MAX_POSTS_TO_PROCESS:
        data = get_json(url, params)
        items = data.get("data", [])
        
        if not items:
            break

        for item in items:
            if len(media) >= MAX_POSTS_TO_PROCESS:
                break
                
            if item.get("timestamp"):
                post_date = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                if post_date < cutoff_date:
                    url = ""
                    break
            
            media.append(item)

        if url:
            url = data.get("paging", {}).get("next", "")
            params = None
            
    return media


def get_media_insights(media_id: str, media_type: str, product_type: str | None, timestamp: str) -> dict:
    """Zieht detaillierte Insights fuer einen einzelnen Beitrag (angepasst an Typ und Alter)."""
    post_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - post_date).days

    if age_days < 30:
        metrics = list(METRICS_RECENT)
    else:
        metrics = list(METRICS_OLD)

    if product_type == "REELS" or media_type == "VIDEO":
        metrics.extend(REELS_EXTRA)

    url = f"{BASE_URL}/{media_id}/insights"
    params = {"metric": ",".join(metrics), "access_token": ACCESS_TOKEN}
    data = get_json(url, params)

    insights: dict = {}
    for item in data.get("data", []):
        name = item["name"]
        values = item.get("values", [])
        if values:
            insights[name] = values[0].get("value")
    return insights


def update_follower_history(account: dict, history_file: Path) -> None:
    """Aktualisiert die Historien-Datei fuer das taegliche Follower-Wachstum."""
    history: list[dict] = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text())
        except json.JSONDecodeError:
            history = []

    today = datetime.now(timezone.utc).date().isoformat()
    followers = account.get("followers_count")

    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "followers": followers})
    history.sort(key=lambda h: h["date"])

    history_file.write_text(json.dumps(history, indent=2))


def main() -> None:
    check_env()
    DATA_DIR.mkdir(exist_ok=True)

    print("Pruefe Token-Status...")
    check_token_expiry()

    print("\nLade Account-Informationen...")
    account = get_account_info()
    username = account.get("username")
    
    if not username:
        die("Account-Informationen konnten nicht geladen werden. Bitte Token und USER_ID pruefen.")
        
    print(f"   @{username} | {account.get('followers_count'):,} Follower | {account.get('media_count'):,} Posts")
    print(f"   Profilaufrufe (24h): {account.get('daily_insights', {}).get('profile_views', 0)}")
    print(f"   Website-Klicks (24h): {account.get('daily_insights', {}).get('website_clicks', 0)}")

    # Dynamische Dateipfade basierend auf dem Username
    data_file = DATA_DIR / f"instagram_data_{username}.json"
    history_file = DATA_DIR / f"follower_history_{username}.json"

    print(f"\nLade Medien (Max: {MAX_POSTS_TO_PROCESS} Posts / Max Alter: {MAX_AGE_YEARS} Jahre)...")
    media = get_all_media()
    print(f"   {len(media)} relevante Beitraege gefunden.")

    print("\nLade detaillierte Insights pro Beitrag...")
    enriched: list[dict] = []
    for i, item in enumerate(media, 1):
        if i % 10 == 0 or i == len(media):
            print(f"   Fortschritt: {i}/{len(media)}")
            
        item["insights"] = get_media_insights(
            item["id"],
            item.get("media_type", ""),
            item.get("media_product_type"),
            item.get("timestamp", "")
        )
        enriched.append(item)
        time.sleep(0.1)

    update_follower_history(account, history_file)

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "api_version": API_VERSION,
        "account": account,
        "media": enriched,
    }

    data_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\nErfolgreich abgeschlossen.")
    print(f" - Daten gespeichert unter: {data_file.relative_to(PROJECT_ROOT)}")
    print(f" - Historie aktualisiert: {history_file.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
