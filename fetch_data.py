#!/usr/bin/env python3
"""
Instagram Business Account & Marketing API Data Fetcher - C& Editorial & Ads Edition
Zieht Account-Daten, Insights, Demografie, archiviert Stories, lädt Thumbnails
UND integriert Facebook Marketing API (Ads Spend, ROI & Collab-Detection).
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
AD_ACCOUNT_ID = os.environ.get("AD_ACCOUNT_ID")  # Format: nur die Zahl (ohne "act_")
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# --- Filter-Parameter ---
MAX_POSTS_TO_PROCESS = 1500
CUTOFF_DATE = datetime(2023, 1, 1, tzinfo=timezone.utc)
THUMBNAIL_LIMIT = 30  # Thumbnails für die N neuesten Posts herunterladen

# --- Pfade ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"

# --- Metrik-Definitionen ---
METRICS_RECENT = ["reach", "impressions", "views", "likes", "comments", "saved", "shares", "total_interactions"]
METRICS_OLD = ["reach", "impressions", "likes", "comments", "saved", "shares"]
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
    """Holt Follower-Demografie (Alter, Geschlecht, Land, Stadt)."""
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

    print("\nLade Demografie-Daten...")
    account_data["demographics"] = get_demographics()

    return account_data


def get_all_media() -> list[dict]:
    media = []
    url = f"{BASE_URL}/{IG_USER_ID}/media"
    params = {
        # 'owner' hinzugefügt für Collab-Detection
        "fields": "id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,timestamp,owner",
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
                    return media
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


# --- NEU: MARKETING API LOGIKEN ---

def get_ads_marketing_data() -> tuple[dict, dict]:
    """Holt Ad-Insights und Ad-Creatives aus dem Werbekonto."""
    if not AD_ACCOUNT_ID:
        print("\n⚠️ AD_ACCOUNT_ID nicht gesetzt. Überspringe Ads-Integration.")
        return {}, {}

    print(f"\nVerbinde mit Marketing API für Ad Account: act_{AD_ACCOUNT_ID}...")
    ads_url = f"{BASE_URL}/act_{AD_ACCOUNT_ID}"
    
    # 1. Insights holen (Spend, Impressions, Clicks)
    insights_params = {
        "access_token": ACCESS_TOKEN,
        "fields": "ad_id,spend,impressions,inline_link_clicks",
        "date_preset": "maximum",
        "level": "ad",
        "limit": 500
    }
    insights_data = get_json(f"{ads_url}/insights", insights_params)
    
    ad_mapping = {}
    for insight in insights_data.get("data", []):
        ad_mapping[insight["ad_id"]] = {
            "spend": float(insight.get("spend", 0.0)),
            "impressions": int(insight.get("impressions", 0)),
            "clicks": int(insight.get("inline_link_clicks", 0))
        }

    # 2. Creatives holen, um Ads auf IG Media-IDs zu mappen
    creative_params = {
        "access_token": ACCESS_TOKEN,
        "fields": "id,effective_object_story_id",
        "limit": 500
    }
    creatives_data = get_json(f"{ads_url}/adcreatives", creative_params)
    
    creative_to_media = {}
    for creative in creatives_data.get("data", []):
        story_id = creative.get("effective_object_story_id", "")
        # Falls vorhanden, extrahiert effective_object_story_id die IG Media ID (oft nach dem Unterstrich)
        if "_" in story_id:
            media_id = story_id.split("_")[1]
            creative_to_media[creative["id"]] = media_id

    # 3. Ad-Struktur auflösen (Welches Creative gehört zu welcher Ad-ID)
    ads_structure_params = {
        "access_token": ACCESS_TOKEN,
        "fields": "id,creative",
        "limit": 500
    }
    ads_structure = get_json(f"{ads_url}/ads", ads_structure_params)
    
    media_ads_map = {}
    for ad in ads_structure.get("data", []):
        ad_id = ad["id"]
        creative_id = ad.get("creative", {}).get("id")
        
        if creative_id and creative_id in creative_to_media:
            media_id = creative_to_media[creative_id]
            if ad_id in ad_mapping:
                if media_id not in media_ads_map:
                    media_ads_map[media_id] = {"spend": 0.0, "impressions": 0, "clicks": 0}
                
                # Werte aufaddieren, falls ein Post in mehreren Ads verwendet wird
                media_ads_map[media_id]["spend"] += ad_mapping[ad_id]["spend"]
                media_ads_map[media_id]["impressions"] += ad_mapping[ad_id]["impressions"]
                media_ads_map[media_id]["clicks"] += ad_mapping[ad_id]["clicks"]

    print(f"   Ads-Mapping: {len(media_ads_map)} Instagram Posts mit Paid-Aktivitäten verknüpft.")
    return media_ads_map


def download_thumbnail(url: str, target_path: Path) -> bool:
    try:
        r = requests.get(url, timeout=30, stream=True)
        if r.status_code != 200:
            return False
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return target_path.stat().st_size > 100
    except Exception as e:
        print(f"   Download-Fehler: {e}")
        return False


def download_thumbnails(media_list: list[dict], username: str) -> int:
    thumb_dir = DATA_DIR / "thumbnails" / username
    thumb_dir.mkdir(parents=True, exist_ok=True)

    sorted_media = sorted(media_list, key=lambda m: m.get("timestamp", ""), reverse=True)
    top_media = sorted_media[:THUMBNAIL_LIMIT]

    print(f"\nLade Thumbnails (Top {len(top_media)})...")
    success = 0
    new_downloads = 0
    for m in top_media:
        media_id = m["id"]
        target = thumb_dir / f"{media_id}.jpg"

        if target.exists() and target.stat().st_size > 100:
            success += 1
            continue

        url = m.get("thumbnail_url") or m.get("media_url")
        if not url:
            continue

        if download_thumbnail(url, target):
            success += 1
            new_downloads += 1
        time.sleep(0.05)

    print(f"   {success}/{len(top_media)} Thumbnails verfügbar ({new_downloads} neu heruntergeladen).")
    return success


def get_and_archive_stories(username: str) -> None:
    print("\nSichere aktuelle Stories (24h-Archivierung)...")
    url = f"{BASE_URL}/{IG_USER_ID}/stories"
    params = {"fields": "id,caption,media_type,media_url,timestamp", "access_token": ACCESS_TOKEN}
    data = get_json(url, params)

    active_stories = data.get("data", [])
    if not active_stories:
        print("   Keine aktiven Stories gefunden.")
        return

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

    # 3. ADS & MARKETING DATA VORAB LASSEN (falls konfiguriert)
    media_ads_map = get_ads_marketing_data()

    # 4. BEITRÄGE SEIT 2023 LADEN
    print(f"\nLade Medien (Limit: {MAX_POSTS_TO_PROCESS} Posts / Ab: {CUTOFF_DATE.strftime('%d.%m.%Y')})...")
    media = get_all_media()
    print(f"   {len(media)} Beiträge aus dem Zeitraum gefunden.")

    enriched = []
    for i, item in enumerate(media, 1):
        if i % 25 == 0 or i == len(media):
            print(f"   Fortschritt: {i}/{len(media)}")
        
        media_id = item["id"]
        
        # Normale organische Insights holen
        organic_insights = get_media_insights(
            media_id,
            item.get("media_type", ""),
            item.get("media_product_type"),
            item.get("timestamp", ""),
        )
        
        # --- NEU: COLLAB DETECTION ---
        owner_id = item.get("owner", {}).get("id")
        owner_name = item.get("owner", {}).get("username")
        
        is_collab = False
        if owner_id and owner_id != IG_USER_ID:
            is_collab = True

        # --- NEU: ORGANIC VS PAID SPLIT & ROI ---
        ads_info = media_ads_map.get(media_id, {"spend": 0.0, "impressions": 0, "clicks": 0})
        
        total_impressions = int(organic_insights.get("impressions", 0) or 0)
        paid_impressions = ads_info["impressions"]
        
        # Organische Reichweite bereinigen (Total minus Bezahlte Impressions)
        clean_organic_impressions = max(0, total_impressions - paid_impressions)
        
        # Neue Struktur direkt in das Element injizieren
        item["ads_integration"] = {
            "is_collab": is_collab,
            "collab_partner_username": owner_name if is_collab else None,
            "spend_eur": ads_info["spend"],
            "paid_impressions": paid_impressions,
            "organic_impressions_clean": clean_organic_impressions,
            "roi_link_clicks": ads_info["clicks"],
            "has_active_ads": ads_info["spend"] > 0
        }
        
        item["insights"] = organic_insights
        enriched.append(item)
        time.sleep(0.1)

    # 5. THUMBNAILS HERUNTERLADEN
    download_thumbnails(enriched, username)

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
