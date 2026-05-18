#!/usr/bin/env python3
"""
Instagram Business Account Data Fetcher - C& Editorial Edition
Zieht Account-Daten, tagesaktuelle Insights, Traffic, Demografie,
Posts (seit 2023) und sichert Stories.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Systemkonfiguration ---
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
IG_USER_ID = os.environ.get("INSTAGRAM_USER_ID")
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# --- Filter-Parameter ---
MAX_POSTS_TO_PROCESS = 1500  # Erhöht für Daten bis 2023
CUTOFF_DATE = datetime(2023, 1, 1, tzinfo=timezone.utc)  # Zieht alles ab 01.01.2023

# --- Pfade ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"

# --- Metrik-Definitionen ---
METRICS_RECENT = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions"]
METRICS_OLD = ["reach", "likes", "comments", "saved", "shares"]
REELS_EXTRA = ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
STORY_METRICS = ["reach", "impressions", "replies", "taps_forward", "taps_back", "exits"]
DEMOGRAPHIC_BREAKDOWNS = ["age", "gender", "country", "city"]


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def get_json(url: str, params: dict | None = None) -> dict:
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 503):
            time.sleep(5 * (attempt + 1))
            continue
        print(f"   HTTP {r.status_code}: {r.text[:200]}")
        return {}
    return {}


def get_demographics() -> dict:
    """Holt Follower-Demografie (Alter, Geschlecht, Land, Stadt).
    Verwendet den neuen `follower_demographics`-Endpoint (Meta 2024+).
    Benötigt min. 100 Follower; bei kleinen Subgruppen filtert Meta aus
    Privacy-Gründen — solche Breakdowns kommen dann leer zurück.
    """
    demo = {}
    insights_url = f"{BASE_URL}/{IG_USER_ID}/insights"

    for breakdown in DEMOGRAPHIC_BREAKDOWNS:
        params = {
            "metric": "follower_demographics",
            "period": "lifetime",
            "timeframe": "this_month",
            "breakdown": breakdown,
            "metric_type": "total_value",
            "access_token": ACCESS_TOKEN,
        }
        data = get_json(insights_url, params)

        entries = []
        for item in data.get("data", []):
            breakdowns = item.get("total_value", {}).get("breakdowns", [])
            for b in breakdowns:
                for r in b.get("results", []):
                    dim_values = r.get("dimension_values", [])
                    if dim_values:
                        entries.append({"label": dim_values[0], "value": r.get("value", 0)})

        # Sort by value descending for nicer display
        entries.sort(key=lambda x: x["value"], reverse=True)
        demo[breakdown] = entries
        print(f"   Demografie · {breakdown}: {len(entries)} Einträge")

    return demo


def get_account_info() -> dict:
    base_url = f"{BASE_URL}/{IG_USER_ID}"
    params_base = {
        "fields": "id,username,followers_count,follows_count,media_count,profile_picture_url,name",
        "access_token": ACCESS_TOKEN,
    }
    account_data = get_json(base_url, params_base)

    # Daily traffic insights
    insights_url = f"{BASE_URL}/{IG_USER_ID}/insights"
    params_insights = {
        "metric": "profile_views,website_clicks",
        "period": "day",
        "metric_type": "total_value",
        "access_token": ACCESS_TOKEN,
    }
    insights_data = get_json(insights_url, params_insights)

    account_data["daily_insights"] = {}
    for item in insights_data.get("data", []):
        if item.get("values"):
            account_data["daily_insights"][item["name"]] = item["values"][0].get("value", 0)

    # Demographics (Alter, Geschlecht, Land, Stadt)
    print("\nLade Demografie-Daten...")
    account_data["demographics"] = get_demographics()

    return account_data


def get_all_media() -> list[dict]:
    media = []
    url = f"{BASE_URL}/{IG_USER_ID}/media"
    params = {
        "fields": "id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,timestamp",
        "limit": 100,
        "access_token": ACCESS_TOKEN,
    }

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
                if post_date < CUTOFF_DATE:
                    return media  # Stoppt exakt am 01.01.2023
            media.append(item)

        url = data.get("paging", {}).get("next", "") if data.get("paging") else ""
        params = None
    return media


def get_media_insights(media_id: str, media_type: str, product_type: str | None, timestamp: str) -> dict:
    post_date = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    age_days = (datetime.now(timezone.utc) - post_date).days

    metrics = list(METRICS_RECENT) if age_days < 30 else list(METRICS_OLD)
    if product_type == "REELS" or media_type == "VIDEO":
        metrics.extend(REELS_EXTRA)

    url = f"{BASE_URL}/{media_id}/insights"
    data = get_json(url, {"metric": ",".join(metrics), "access_token": ACCESS_TOKEN})

    insights = {}
    for item in data.get("data", []):
        if item.get("values"):
            insights[item["name"]] = item["values"][0].get("value")
    return insights


def get_and_archive_stories(username: str) -> None:
    print("\nSichere aktuelle Stories (24h-Archivierung)...")
    url = f"{BASE_URL}/{IG_USER_ID}/stories"
    params = {"fields": "id,caption,media_type,media_url,timestamp", "access_token": ACCESS_TOKEN}
    data = get_json(url, params)

    active_stories = data.get("data", [])
    if not active_stories:
        print("   Keine aktiven Stories gefunden.")
        return

    # Insights für jede Story laden
    enriched_stories = []
    for story in active_stories:
        insights_url = f"{BASE_URL}/{story['id']}/insights"
        i_data = get_json(insights_url, {"metric": ",".join(STORY_METRICS), "access_token": ACCESS_TOKEN})
        story_insights = {}
        for item in i_data.get("data", []):
            if item.get("values"):
                story_insights[item["name"]] = item["values"][0].get("value")
        story["insights"] = story_insights
        enriched_stories.append(story)

    # In die ewige Archiv-Datei einfügen (Duplikate anhand der ID vermeiden)
    stories_file = DATA_DIR / f"stories_history_{username}.json"
    archive = json.loads(stories_file.read_text()) if stories_file.exists() else []

    existing_ids = {s["id"] for s in archive}
    new_count = 0
    for s in enriched_stories:
        if s["id"] not in existing_ids:
            archive.append(s)
            new_count += 1

    stories_file.write_text(json.dumps(archive, indent=2))
    print(f"   {new_count} NEUE Stories dauerhaft archiviert.")


def update_history(account: dict, history_file: Path) -> None:
    history = json.loads(history_file.read_text()) if history_file.exists() else []
    today = datetime.now(timezone.utc).date().isoformat()

    # Alte Einträge für heute löschen, damit es sauber überschrieben wird
    history = [h for h in history if h.get("date") != today]

    history.append({
        "date": today,
        "followers": account.get("followers_count"),
        "profile_views": account.get("daily_insights", {}).get("profile_views", 0),
        "website_clicks": account.get("daily_insights", {}).get("website_clicks", 0),
    })
    history.sort(key=lambda h: h["date"])
    history_file.write_text(json.dumps(history, indent=2))


def main() -> None:
    if not ACCESS_TOKEN or not IG_USER_ID:
        die("Umgebungsvariablen fehlen.")
    DATA_DIR.mkdir(exist_ok=True)

    print("Lade Account, Traffic & Demografie-Daten...")
    account = get_account_info()
    username = account.get("username", "unknown")

    # 1. STORIES SPEICHERN
    get_and_archive_stories(username)

    # 2. HISTORIE & TRAFFIC SPEICHERN
    history_file = DATA_DIR / f"follower_history_{username}.json"
    update_history(account, history_file)

    # 3. BEITRÄGE SEIT 2023 LADEN
    print(f"\nLade Medien (Limit: {MAX_POSTS_TO_PROCESS} Posts / Ab: {CUTOFF_DATE.strftime('%d.%m.%Y')})...")
    media = get_all_media()
    print(f"   {len(media)} Beiträge aus dem Zeitraum gefunden.")

    enriched = []
    for i, item in enumerate(media, 1):
        if i % 25 == 0 or i == len(media):
            print(f"   Fortschritt: {i}/{len(media)}")
        item["insights"] = get_media_insights(
            item["id"],
            item.get("media_type", ""),
            item.get("media_product_type"),
            item.get("timestamp", ""),
        )
        enriched.append(item)
        time.sleep(0.1)  # Verhindert API-Blockaden bei vielen Posts

    data_file = DATA_DIR / f"instagram_data_{username}.json"
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "api_version": API_VERSION,
        "account": account,
        "media": enriched,
    }
    data_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print("\nErfolgreich abgeschlossen.")


if __name__ == "__main__":
    main()
