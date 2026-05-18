#!/usr/bin/env python3
"""
Fetches Instagram Business Account data via the Graph API.

Outputs:
- data/instagram_data.json   (full snapshot: account + all media + insights)
- data/follower_history.json (rolling daily follower count)

Required env vars:
- INSTAGRAM_ACCESS_TOKEN : Long-lived access token (60 days)
- INSTAGRAM_USER_ID      : The IG Business Account ID (NOT your username)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# --- Config ---
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
IG_USER_ID = os.environ.get("INSTAGRAM_USER_ID")
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_FILE = DATA_DIR / "instagram_data.json"
FOLLOWER_HISTORY_FILE = DATA_DIR / "follower_history.json"

# Metrics available per media type (as of Graph API v21.0, late 2025)
# "impressions" was deprecated in 2024 -> use "views" instead
COMMON_METRICS = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions"]
REELS_EXTRA = ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def check_env() -> None:
    if not ACCESS_TOKEN:
        die("INSTAGRAM_ACCESS_TOKEN env var not set")
    if not IG_USER_ID:
        die("INSTAGRAM_USER_ID env var not set")


def get_json(url: str, params: dict | None = None) -> dict:
    """GET with retries on rate-limit / transient errors."""
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  network error (attempt {attempt + 1}): {e}")
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 503):
            wait = 5 * (attempt + 1)
            print(f"  rate-limited, waiting {wait}s...")
            time.sleep(wait)
            continue
        # 4xx -> log and bail out for this call
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        return {}
    return {}


def check_token_expiry() -> None:
    """Print days remaining until access token expiry."""
    url = f"{BASE_URL}/debug_token"
    params = {"input_token": ACCESS_TOKEN, "access_token": ACCESS_TOKEN}
    data = get_json(url, params).get("data", {})
    expires_at = data.get("expires_at")
    if expires_at:
        days_left = (datetime.fromtimestamp(expires_at, timezone.utc) - datetime.now(timezone.utc)).days
        print(f"Token expires in {days_left} days (on {datetime.fromtimestamp(expires_at).date()})")
        if days_left < 10:
            print("⚠️  WARNING: Token expires soon. Refresh it via the Graph API Explorer "
                  "or run scripts/refresh_token.py")


def get_account_info() -> dict:
    """Fetch account-level info."""
    url = f"{BASE_URL}/{IG_USER_ID}"
    params = {
        "fields": "id,username,followers_count,follows_count,media_count,profile_picture_url,name,biography,website",
        "access_token": ACCESS_TOKEN,
    }
    return get_json(url, params)


def get_all_media() -> list[dict]:
    """Fetch all media items, paginating through results."""
    media: list[dict] = []
    url = f"{BASE_URL}/{IG_USER_ID}/media"
    params: dict | None = {
        "fields": "id,caption,media_type,media_product_type,media_url,permalink,thumbnail_url,timestamp",
        "limit": 100,
        "access_token": ACCESS_TOKEN,
    }
    while url:
        data = get_json(url, params)
        media.extend(data.get("data", []))
        url = data.get("paging", {}).get("next", "")
        params = None  # next URL already includes params
    return media


def get_media_insights(media_id: str, media_type: str, product_type: str | None) -> dict:
    """Fetch insights for a single media item."""
    metrics = list(COMMON_METRICS)
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


def update_follower_history(account: dict) -> None:
    """Append today's follower count to a rolling history file."""
    history: list[dict] = []
    if FOLLOWER_HISTORY_FILE.exists():
        try:
            history = json.loads(FOLLOWER_HISTORY_FILE.read_text())
        except json.JSONDecodeError:
            history = []

    today = datetime.now(timezone.utc).date().isoformat()
    followers = account.get("followers_count")

    # Replace today's entry if it already exists, else append
    history = [h for h in history if h.get("date") != today]
    history.append({"date": today, "followers": followers})
    history.sort(key=lambda h: h["date"])

    FOLLOWER_HISTORY_FILE.write_text(json.dumps(history, indent=2))


def main() -> None:
    check_env()
    DATA_DIR.mkdir(exist_ok=True)

    print("Checking token...")
    check_token_expiry()

    print("\nFetching account info...")
    account = get_account_info()
    if not account.get("username"):
        die("Could not fetch account info. Check token + IG_USER_ID.")
    print(f"  @{account['username']} | {account.get('followers_count'):,} followers "
          f"| {account.get('media_count'):,} total posts")

    print("\nFetching all media...")
    media = get_all_media()
    print(f"  Found {len(media)} media items.")

    print("\nFetching insights per post...")
    enriched: list[dict] = []
    for i, item in enumerate(media, 1):
        if i % 10 == 0 or i == len(media):
            print(f"  {i}/{len(media)}")
        item["insights"] = get_media_insights(
            item["id"],
            item.get("media_type", ""),
            item.get("media_product_type"),
        )
        enriched.append(item)
        time.sleep(0.05)  # polite throttling

    update_follower_history(account)

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "api_version": API_VERSION,
        "account": account,
        "media": enriched,
    }

    DATA_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"\n✓ Saved {len(enriched)} posts to {DATA_FILE.relative_to(PROJECT_ROOT)}")
    print(f"✓ Updated follower history -> {FOLLOWER_HISTORY_FILE.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
