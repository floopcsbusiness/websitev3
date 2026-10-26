"""Daily social stats fetcher for YouTube, Instagram and TikTok.

Writes stats.json (latest numbers plus daily history) for the dashboard.
If a platform fails, its previous numbers are kept and flagged as stale,
so the site never goes blank.

Engagement rate = (likes + comments + shares) / views over the most recent
posts. YouTube doesn't expose shares through the API, so it uses likes and
comments only.

Platforms with no credentials set are skipped.
"""
import json
import os
import sys
from datetime import datetime, timezone

import requests

TIMEOUT = 30
STATS_FILE = "stats.json"
ROTATED_FILE = "rotated_tokens.json"
HISTORY_DAYS = 180
RECENT_POSTS = 20

# Tokens that changed during this run (Instagram and TikTok rotate them).
_rotated = {}


def env(name):
    value = os.environ.get(name, "").strip()
    return value or None


def rate(interactions, views):
    return round(interactions / views * 100, 2) if views else None


def safe_err(e):
    # Never use str(e) for request errors: the message can contain the full
    # URL, including API keys, and this ends up in a public JSON file.
    if isinstance(e, requests.HTTPError) and e.response is not None:
        return f"HTTP {e.response.status_code}"
    if isinstance(e, RuntimeError):
        return str(e)  # our own messages, written to be safe
    return type(e).__name__


def get_json(url, **kwargs):
    r = requests.get(url, timeout=TIMEOUT, **kwargs)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------- YouTube

def youtube():
    key, channel = env("YT_API_KEY"), env("YT_CHANNEL_ID")
    if not (key and channel):
        return None
    base = "https://www.googleapis.com/youtube/v3"

    data = get_json(f"{base}/channels", params={
        "part": "statistics,contentDetails", "id": channel, "key": key})
    items = data.get("items", [])
    if not items:
        raise RuntimeError("YouTube channel not found, check YT_CHANNEL_ID")
    ch = items[0]
    followers = int(ch["statistics"].get("subscriberCount", 0))
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]

    data = get_json(f"{base}/playlistItems", params={
        "part": "contentDetails", "playlistId": uploads,
        "maxResults": RECENT_POSTS, "key": key})
    ids = [i["contentDetails"]["videoId"] for i in data.get("items", [])]

    views = interactions = 0
    if ids:
        data = get_json(f"{base}/videos", params={
            "part": "statistics", "id": ",".join(ids), "key": key})
        for v in data.get("items", []):
            s = v["statistics"]
            views += int(s.get("viewCount", 0))
            interactions += int(s.get("likeCount", 0)) + int(s.get("commentCount", 0))

    return {
        "followers": followers,
        "recent_views": views,
        "recent_interactions": interactions,
        "engagement_rate": rate(interactions, views),
        "posts_counted": len(ids),
    }


# -------------------------------------------------------------- Instagram

def _ig_value(entry):
    values = entry.get("values")
    if values:
        return values[0].get("value")
    return entry.get("total_value", {}).get("value")


def _ig_media_insights(base, media_id, token):
    """Returns (views, shares). Either can be None if Instagram refuses."""
    try:
        data = get_json(f"{base}/{media_id}/insights", params={
            "metric": "views,shares", "access_token": token}).get("data", [])
    except requests.RequestException:
        return None, None
    vals = {d["name"]: _ig_value(d) for d in data}
    return vals.get("views"), vals.get("shares")


def instagram():
    token = env("IG_ACCESS_TOKEN")
    if not token:
        return None
    base = "https://graph.instagram.com"

    # Long-lived tokens last 60 days. Refreshing daily keeps it alive.
    try:
        refreshed = get_json(f"{base}/refresh_access_token", params={
            "grant_type": "ig_refresh_token", "access_token": token})
        new = refreshed.get("access_token")
        if new and new != token:
            _rotated["IG_ACCESS_TOKEN"] = new
            token = new
    except requests.RequestException as e:
        print(f"[instagram] token refresh failed: {safe_err(e)}", file=sys.stderr)

    me = get_json(f"{base}/me", params={
        "fields": "followers_count,media_count", "access_token": token})
    media = get_json(f"{base}/me/media", params={
        "fields": "id,like_count,comments_count",
        "limit": RECENT_POSTS, "access_token": token}).get("data", [])

    views = interactions = counted = 0
    for m in media:
        v, shares = _ig_media_insights(base, m["id"], token)
        if v is None:
            continue  # skip posts with no view data so the rate stays honest
        counted += 1
        views += v
        interactions += m.get("like_count", 0) + m.get("comments_count", 0) + (shares or 0)

    return {
        "followers": me.get("followers_count"),
        "recent_views": views,
        "recent_interactions": interactions,
        "engagement_rate": rate(interactions, views),
        "posts_counted": counted,
    }


# ----------------------------------------------------------------- TikTok

def tiktok():
    client_key = env("TIKTOK_CLIENT_KEY")
    client_secret = env("TIKTOK_CLIENT_SECRET")
    refresh = env("TIKTOK_REFRESH_TOKEN")
    if not (client_key and client_secret and refresh):
        return None

    r = requests.post("https://open.tiktokapis.com/v2/oauth/token/", data={
        "client_key": client_key, "client_secret": client_secret,
        "grant_type": "refresh_token", "refresh_token": refresh,
    }, timeout=TIMEOUT)
    tok = r.json()
    if "access_token" not in tok:
        raise RuntimeError("TikTok token refresh failed, re-authorize and update TIKTOK_REFRESH_TOKEN")
    if tok.get("refresh_token") and tok["refresh_token"] != refresh:
        _rotated["TIKTOK_REFRESH_TOKEN"] = tok["refresh_token"]
    headers = {"Authorization": f"Bearer {tok['access_token']}"}

    r = requests.get("https://open.tiktokapis.com/v2/user/info/",
                     params={"fields": "follower_count,likes_count,video_count"},
                     headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    user = r.json().get("data", {}).get("user", {})
    followers = user.get("follower_count")  # None if user.info.stats isn't granted
    if followers is None:
        print("[tiktok] no follower_count returned, check the user.info.stats scope",
              file=sys.stderr)

    r = requests.post("https://open.tiktokapis.com/v2/video/list/",
                      params={"fields": "id,view_count,like_count,comment_count,share_count"},
                      json={"max_count": RECENT_POSTS}, headers=headers, timeout=TIMEOUT)
    r.raise_for_status()
    videos = r.json().get("data", {}).get("videos", [])

    views = sum(v.get("view_count", 0) for v in videos)
    interactions = sum(v.get("like_count", 0) + v.get("comment_count", 0)
                       + v.get("share_count", 0) for v in videos)

    return {
        "followers": followers,
        "recent_views": views,
        "recent_interactions": interactions,
        "engagement_rate": rate(interactions, views),
        "posts_counted": len(videos),
    }


# ------------------------------------------------------------------- main

SOURCES = {"youtube": youtube, "instagram": instagram, "tiktok": tiktok}


def totals(platforms):
    followers = sum(p.get("followers") or 0 for p in platforms.values())
    views = sum(p.get("recent_views") or 0 for p in platforms.values())
    inter = sum(p.get("recent_interactions") or 0 for p in platforms.values())
    return {"followers": followers, "recent_views": views,
            "engagement_rate": rate(inter, views)}


def main():
    now = datetime.now(timezone.utc)
    try:
        with open(STATS_FILE) as f:
            prev = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        prev = {}

    out = {"updated": now.isoformat(timespec="seconds"), "platforms": {}}
    failed = []

    for name, fn in SOURCES.items():
        try:
            data = fn()
        except Exception as e:  # keep going, one bad platform shouldn't kill the rest
            reason = safe_err(e)
            print(f"[{name}] FAILED: {reason}", file=sys.stderr)
            failed.append(name)
            old = prev.get("platforms", {}).get(name)
            if old:
                old["stale"] = True
                old["error"] = reason
                out["platforms"][name] = old
            continue
        if data is None:
            print(f"[{name}] skipped, no credentials set")
            continue
        data["stale"] = False
        data["fetched"] = now.isoformat(timespec="seconds")
        out["platforms"][name] = data
        print(f"[{name}] ok")

    out["totals"] = totals(out["platforms"])

    today = now.date().isoformat()
    history = [h for h in prev.get("history", []) if h.get("date") != today]
    history.append({"date": today, **out["totals"]})
    out["history"] = history[-HISTORY_DAYS:]

    with open(STATS_FILE, "w") as f:
        json.dump(out, f, indent=2)

    if _rotated:
        with open(ROTATED_FILE, "w") as f:
            json.dump(_rotated, f)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
