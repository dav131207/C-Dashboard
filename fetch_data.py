#!/usr/bin/env python3
"""
Instagram Business Account Data Fetcher - C& Editorial Edition
Zieht Account-Daten, tagesaktuelle Insights, Traffic, Demografie,
Posts (seit 2023), Thumbnails, Stories — sowie Ads-Daten (Marketing API)
und Collab-Status pro Post.
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
AD_ACCOUNT_ID = os.environ.get("AD_ACCOUNT_ID")  # optional; ohne wird Ads-Fetch übersprungen
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# --- Filter-Parameter ---
MAX_POSTS_TO_PROCESS = 1500
CUTOFF_DATE = datetime(2023, 1, 1, tzinfo=timezone.utc)
THUMBNAIL_LIMIT = 30

# --- Pfade ---
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"

# --- Metrik-Definitionen ---
METRICS_RECENT = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions"]
METRICS_OLD = ["reach", "likes", "comments", "saved", "shares"]
REELS_EXTRA = ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
STORY_METRICS = ["reach", "impressions", "replies", "taps_forward", "taps_back", "exits"]
DEMOGRAPHIC_BREAKDOWNS = ["age", "gender", "country", "city"]
AD_INSIGHT_FIELDS = "spend,reach,impressions,clicks,frequency,cpm,cpc,ctr,actions"


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
        # Don't print collaborators 404s (most posts aren't collabs)
        if "collaborators" not in url:
            print(f"   HTTP {r.status_code}: {r.text[:200]}")
        return {}
    return {}


# --- Demographics ---
def get_demographics() -> dict:
    demo = {}
    insights_url = f"{BASE_URL}/{IG_USER_ID}/insights"
    for breakdown in DEMOGRAPHIC_BREAKDOWNS:
        params = {
            "metric": "follower_demographics", "period": "lifetime", "timeframe": "this_month",
            "breakdown": breakdown, "metric_type": "total_value", "access_token": ACCESS_TOKEN,
        }
        data = get_json(insights_url, params)
        entries = []
        for item in data.get("data", []):
            for b in item.get("total_value", {}).get("breakdowns", []):
                for r in b.get("results", []):
                    dv = r.get("dimension_values", [])
                    if dv:
                        entries.append({"label": dv[0], "value": r.get("value", 0)})
        entries.sort(key=lambda x: x["value"], reverse=True)
        demo[breakdown] = entries
        print(f"   Demografie · {breakdown}: {len(entries)} Einträge")
    return demo


def get_account_info() -> dict:
    params_base = {
        "fields": "id,username,followers_count,follows_count,media_count,profile_picture_url,name",
        "access_token": ACCESS_TOKEN,
    }
    account_data = get_json(f"{BASE_URL}/{IG_USER_ID}", params_base)

    insights_url = f"{BASE_URL}/{IG_USER_ID}/insights"
    insights_data = get_json(insights_url, {
        "metric": "profile_views,website_clicks", "period": "day",
        "metric_type": "total_value", "access_token": ACCESS_TOKEN,
    })
    account_data["daily_insights"] = {}
    for item in insights_data.get("data", []):
        if item.get("values"):
            account_data["daily_insights"][item["name"]] = item["values"][0].get("value", 0)

    print("\nLade Demografie-Daten...")
    account_data["demographics"] = get_demographics()
    return account_data


# --- Media ---
def get_all_media() -> list[dict]:
    media = []
    url = f"{BASE_URL}/{IG_USER_ID}/media"
    params = {
        "fields": "id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,timestamp",
        "limit": 100, "access_token": ACCESS_TOKEN,
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
    data = get_json(f"{BASE_URL}/{media_id}/insights",
                    {"metric": ",".join(metrics), "access_token": ACCESS_TOKEN})
    insights = {}
    for item in data.get("data", []):
        if item.get("values"):
            insights[item["name"]] = item["values"][0].get("value")
    return insights


# --- NEW: Collab detection ---
def detect_collab(media_id: str) -> dict:
    """Check if media is a collab post and return collaborator usernames."""
    data = get_json(f"{BASE_URL}/{media_id}/collaborators",
                    {"access_token": ACCESS_TOKEN})
    collaborators = data.get("data", [])
    if collaborators:
        usernames = [c.get("username") for c in collaborators if c.get("username")]
        return {"is_collab": True, "collaborators": usernames}
    return {"is_collab": False, "collaborators": []}


# --- NEW: Ads from Marketing API ---
def get_ads_with_insights() -> list[dict]:
    """Fetch all ads from the ad account with their insights and creative info."""
    if not AD_ACCOUNT_ID:
        print("\n[Ads] AD_ACCOUNT_ID nicht gesetzt — Ads werden übersprungen.")
        return []

    print(f"\nLade Ads aus Ad-Account act_{AD_ACCOUNT_ID}...")
    ads = []
    url = f"{BASE_URL}/act_{AD_ACCOUNT_ID}/ads"
    params = {
        "fields": "id,name,effective_status,created_time,"
                  "creative{id,effective_instagram_media_id,instagram_permalink_url,object_story_id}",
        "limit": 100, "access_token": ACCESS_TOKEN,
    }
    while url:
        data = get_json(url, params)
        ads.extend(data.get("data", []))
        url = data.get("paging", {}).get("next", "") if data.get("paging") else ""
        params = None
    print(f"   {len(ads)} Ads gefunden.")

    if not ads:
        return []

    print(f"   Lade Lifetime-Insights pro Ad...")
    for i, ad in enumerate(ads, 1):
        if i % 25 == 0 or i == len(ads):
            print(f"      Fortschritt: {i}/{len(ads)}")
        insights_data = get_json(f"{BASE_URL}/{ad['id']}/insights", {
            "fields": AD_INSIGHT_FIELDS,
            "date_preset": "maximum",
            "access_token": ACCESS_TOKEN,
        })
        rows = insights_data.get("data", [])
        ad["insights_data"] = rows[0] if rows else {}
        time.sleep(0.05)

    return ads


def build_ads_index(ads: list[dict]) -> dict:
    """Build map: instagram_media_id → list of ads on that post."""
    index = {}
    for ad in ads:
        creative = ad.get("creative") or {}
        ig_media_id = creative.get("effective_instagram_media_id")
        if ig_media_id:
            index.setdefault(ig_media_id, []).append(ad)
    return index


def enrich_media_with_ads(media: list[dict], ads_index: dict) -> int:
    """For each media item, attach ad_data if boosted. Returns count of boosted posts."""
    boosted_count = 0
    for m in media:
        ads_for_post = ads_index.get(m["id"], [])
        if not ads_for_post:
            m["ad_data"] = {"is_boosted": False}
            continue

        boosted_count += 1
        spend = sum(float(a.get("insights_data", {}).get("spend") or 0) for a in ads_for_post)
        paid_reach = sum(int(a.get("insights_data", {}).get("reach") or 0) for a in ads_for_post)
        paid_imp = sum(int(a.get("insights_data", {}).get("impressions") or 0) for a in ads_for_post)
        paid_clicks = sum(int(a.get("insights_data", {}).get("clicks") or 0) for a in ads_for_post)

        # Total reach from organic insights endpoint is combined (organic + paid).
        # Derive organic by subtracting paid reach (best-effort; Meta doesn't dedupe perfectly).
        total_reach = m.get("insights", {}).get("reach") or 0
        organic_reach = max(0, total_reach - paid_reach)

        m["ad_data"] = {
            "is_boosted": True,
            "ad_count": len(ads_for_post),
            "spend": round(spend, 2),
            "paid_reach": paid_reach,
            "paid_impressions": paid_imp,
            "paid_clicks": paid_clicks,
            "organic_reach": organic_reach,
            "total_reach": total_reach,
            "cpm": round((spend / paid_imp * 1000), 2) if paid_imp else 0,
            "cost_per_paid_reach": round(spend / paid_reach, 4) if paid_reach else 0,
            "ad_ids": [a["id"] for a in ads_for_post],
            "ad_names": [a.get("name", "") for a in ads_for_post],
        }
    return boosted_count


def get_dark_ads(media: list[dict], ads: list[dict]) -> list[dict]:
    """Return ads that DON'T match an organic post (dark posts / ads-only creatives)."""
    media_ids = {m["id"] for m in media}
    dark = []
    for ad in ads:
        creative = ad.get("creative") or {}
        ig_media_id = creative.get("effective_instagram_media_id")
        # Either no IG media at all (story ads, etc.) OR an IG media that we don't have on the feed
        if ig_media_id and ig_media_id not in media_ids:
            dark.append(ad)
        elif not ig_media_id and ad.get("insights_data", {}).get("spend"):
            dark.append(ad)
    return dark


# --- Thumbnails ---
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
    success = new_downloads = 0
    for m in top_media:
        target = thumb_dir / f"{m['id']}.jpg"
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
    print(f"   {success}/{len(top_media)} Thumbnails verfügbar ({new_downloads} neu).")
    return success


# --- Stories ---
def get_and_archive_stories(username: str) -> None:
    print("\nSichere aktuelle Stories...")
    data = get_json(f"{BASE_URL}/{IG_USER_ID}/stories", {
        "fields": "id,caption,media_type,media_url,timestamp", "access_token": ACCESS_TOKEN,
    })
    active = data.get("data", [])
    if not active:
        print("   Keine aktiven Stories.")
        return
    for story in active:
        i_data = get_json(f"{BASE_URL}/{story['id']}/insights",
                         {"metric": ",".join(STORY_METRICS), "access_token": ACCESS_TOKEN})
        si = {}
        for item in i_data.get("data", []):
            if item.get("values"):
                si[item["name"]] = item["values"][0].get("value")
        story["insights"] = si

    stories_file = DATA_DIR / f"stories_history_{username}.json"
    archive = json.loads(stories_file.read_text()) if stories_file.exists() else []
    existing = {s["id"] for s in archive}
    new = 0
    for s in active:
        if s["id"] not in existing:
            archive.append(s)
            new += 1
    stories_file.write_text(json.dumps(archive, indent=2))
    print(f"   {new} neue Stories archiviert.")


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


# --- Main ---
def main() -> None:
    if not ACCESS_TOKEN or not IG_USER_ID:
        die("Umgebungsvariablen fehlen.")
    DATA_DIR.mkdir(exist_ok=True)

    print("Lade Account, Traffic & Demografie...")
    account = get_account_info()
    username = account.get("username", "unknown")

    get_and_archive_stories(username)

    history_file = DATA_DIR / f"follower_history_{username}.json"
    update_history(account, history_file)

    print(f"\nLade Medien (Limit: {MAX_POSTS_TO_PROCESS} / Ab: {CUTOFF_DATE.strftime('%d.%m.%Y')})...")
    media = get_all_media()
    print(f"   {len(media)} Beiträge gefunden.")

    enriched = []
    for i, item in enumerate(media, 1):
        if i % 25 == 0 or i == len(media):
            print(f"   Insights {i}/{len(media)}")
        item["insights"] = get_media_insights(
            item["id"], item.get("media_type", ""),
            item.get("media_product_type"), item.get("timestamp", ""),
        )
        enriched.append(item)
        time.sleep(0.1)

    # NEW: Collab-Detection für alle Posts
    print(f"\nPrüfe Collab-Status für {len(enriched)} Posts...")
    collab_count = 0
    for i, item in enumerate(enriched, 1):
        if i % 50 == 0 or i == len(enriched):
            print(f"   Collab-Check {i}/{len(enriched)}")
        collab_info = detect_collab(item["id"])
        item.update(collab_info)
        if collab_info["is_collab"]:
            collab_count += 1
        time.sleep(0.05)
    print(f"   {collab_count} Collab-Posts erkannt.")

    # NEW: Ads via Marketing API
    ads = get_ads_with_insights()
    ads_index = build_ads_index(ads)
    boosted_count = enrich_media_with_ads(enriched, ads_index)
    dark_ads = get_dark_ads(enriched, ads)
    print(f"\n   {boosted_count} Posts wurden geboostet.")
    print(f"   {len(dark_ads)} Dark Ads / Ads-only Creatives (kein organischer Post).")

    download_thumbnails(enriched, username)

    data_file = DATA_DIR / f"instagram_data_{username}.json"
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "api_version": API_VERSION,
        "account": account,
        "media": enriched,
        "dark_ads": dark_ads,  # Ads ohne organischen Feed-Post
        "ads_summary": {
            "total_ads": len(ads),
            "boosted_posts": boosted_count,
            "dark_ads": len(dark_ads),
            "total_spend": round(sum(float(a.get("insights_data", {}).get("spend") or 0) for a in ads), 2),
        },
    }
    data_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print("\nErfolgreich abgeschlossen.")


if __name__ == "__main__":
    main()
