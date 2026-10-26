"""Auth, API access and data shaping for the YouTube Analytics connector."""
import csv
import datetime as dt
import io
import json
import logging
import os
import re
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

CHANNEL_ID = "UCTFtCTVdZgeVFPPyE9fzjog"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "youtube-analytics-mcp"
CLIENT_SECRET = APP_DIR / "client_secret.json"
TOKEN = APP_DIR / "token.json"
STATE = APP_DIR / "state.json"
REPORTS = APP_DIR / "reports"
LOG = APP_DIR / "server.log"

NOT_SIGNED_IN = "Not signed in to YouTube. Run `ytmcp auth` on this computer."
LAG_NOTE = "YouTube Analytics runs 2–3 days behind; very new videos may be missing."

APP_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(LOG), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ytmcp")


class ToolFailure(Exception):
    """Error whose message is shown to Tom verbatim."""


# ---------- auth ----------

def run_auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not CLIENT_SECRET.exists():
        raise ToolFailure(f"Missing {CLIENT_SECRET}. Copy client_secret.json there first.")
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    TOKEN.write_text(creds.to_json())
    return creds


def get_creds():
    if not TOKEN.exists():
        raise ToolFailure(NOT_SIGNED_IN)
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if not creds.valid:
        if creds.refresh_token:
            try:
                creds.refresh(Request())
                TOKEN.write_text(creds.to_json())
            except RefreshError:
                log.warning("token refresh failed")
                raise ToolFailure(NOT_SIGNED_IN)
        else:
            raise ToolFailure(NOT_SIGNED_IN)
    return creds


_verified = False


def _services():
    global _verified
    creds = get_creds()
    data = build("youtube", "v3", credentials=creds, cache_discovery=False)
    ana = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
    if not _verified:
        res = _call(data.channels().list(part="id,snippet", mine=True))
        ids = {c["id"]: c["snippet"]["title"] for c in res.get("items", [])}
        if CHANNEL_ID not in ids:
            found = ", ".join(f"{t} ({i})" for i, t in ids.items()) or "no channel"
            raise ToolFailure(f"Signed in to the wrong Google account: found {found}, "
                              f"expected channel {CHANNEL_ID}. Run `ytmcp auth` with the owning account.")
        _verified = True
    return creds, data, ana


def _call(req):
    try:
        return req.execute()
    except HttpError as e:
        status = e.resp.status
        text = str(e)
        log.error("API error %s: %s", status, text[:300])
        if "quotaExceeded" in text or "rateLimitExceeded" in text:
            raise ToolFailure("YouTube API quota exceeded. Try again after midnight Pacific time.")
        if "accessNotConfigured" in text or "has not been used in project" in text:
            raise ToolFailure("A required API is not enabled in the Google Cloud project. "
                              "Enable YouTube Data API v3, YouTube Analytics API and YouTube Reporting API.")
        if status in (401, 403):
            raise ToolFailure(f"{NOT_SIGNED_IN} (Google returned {status}.)")
        raise ToolFailure(f"YouTube API error {status}: {e._get_reason()}")


# ---------- helpers ----------

def _today():
    return dt.date.today().isoformat()


def _rows(resp):
    heads = [h["name"] for h in resp.get("columnHeaders", [])]
    return [dict(zip(heads, r)) for r in resp.get("rows", [])]


def _iso_duration(s):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


# ---------- tools ----------

def get_channel():
    _, data, _ = _services()
    res = _call(data.channels().list(part="snippet,statistics", id=CHANNEL_ID))
    c = res["items"][0]
    st = c["statistics"]
    return {"channelId": CHANNEL_ID, "title": c["snippet"]["title"],
            "handle": c["snippet"].get("customUrl", "@rupertsaidiaries"),
            "subscribers": int(st.get("subscriberCount", 0)),
            "views": int(st.get("viewCount", 0)),
            "videoCount": int(st.get("videoCount", 0))}


def _content_types(ana):
    """videoId -> 'short'|'long' via Analytics creatorContentType, or {} if unsupported."""
    try:
        resp = ana.reports().query(ids="channel==MINE", startDate="2005-04-23", endDate=_today(),
                                   metrics="views", dimensions="video,creatorContentType",
                                   sort="-views", maxResults=200).execute()
    except HttpError as e:
        log.info("creatorContentType+video unsupported: %s", str(e)[:200])
        return {}
    out = {}
    for r in _rows(resp):
        out[r["video"]] = "short" if str(r["creatorContentType"]).upper().startswith("SHORT") else "long"
    return out


def _is_short_by_url(vid):
    import requests
    try:
        r = requests.get(f"https://www.youtube.com/shorts/{vid}", allow_redirects=False, timeout=10)
        if r.status_code == 200:
            return True
        if r.status_code in (301, 302, 303, 307, 308):
            return False
    except requests.RequestException:
        pass
    return None


def list_videos(limit=50):
    limit = max(1, min(int(limit or 50), 200))
    _, data, ana = _services()
    ch = _call(data.channels().list(part="contentDetails", id=CHANNEL_ID))
    uploads = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while len(ids) < limit:
        res = _call(data.playlistItems().list(part="contentDetails", playlistId=uploads,
                                              maxResults=50, pageToken=token))
        ids += [i["contentDetails"]["videoId"] for i in res.get("items", [])]
        token = res.get("nextPageToken")
        if not token:
            break
    ids = ids[:limit]
    vids = []
    for i in range(0, len(ids), 50):
        res = _call(data.videos().list(part="snippet,contentDetails,statistics", id=",".join(ids[i:i + 50])))
        vids += res.get("items", [])
    ctypes = _content_types(ana)
    out = []
    for v in vids:
        vid = v["id"]
        dur = _iso_duration(v["contentDetails"]["duration"])
        t = ctypes.get(vid)
        if t is None:
            s = _is_short_by_url(vid)
            t = ("short" if s else "long") if s is not None else ("short" if dur <= 180 else "long")
        st = v.get("statistics", {})
        out.append({"videoId": vid, "title": v["snippet"]["title"],
                    "publishedAt": v["snippet"]["publishedAt"], "type": t, "durationSec": dur,
                    "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0))})
    out.sort(key=lambda x: x["publishedAt"], reverse=True)
    return {"videos": out}


def video_stats(startDate=None, endDate=None):
    _, _, ana = _services()
    start = startDate or "2005-04-23"
    if not startDate:
        vs = list_videos(200)["videos"]
        if vs:
            start = min(v["publishedAt"] for v in vs)[:10]
    end = endDate or _today()
    resp = _call(ana.reports().query(
        ids="channel==MINE", startDate=start, endDate=end, dimensions="video",
        metrics="views,engagedViews,estimatedMinutesWatched,averageViewDuration,"
                "averageViewPercentage,subscribersGained,likes,comments,shares",
        sort="-views", maxResults=200))
    rows = [{"videoId": r["video"], "views": r["views"], "engagedViews": r["engagedViews"],
             "estimatedMinutesWatched": r["estimatedMinutesWatched"],
             "averageViewDurationSec": r["averageViewDuration"],
             "averageViewPercentage": r["averageViewPercentage"],
             "subscribersGained": r["subscribersGained"], "likes": r["likes"],
             "comments": r["comments"], "shares": r["shares"]} for r in _rows(resp)]
    return {"startDate": start, "endDate": end, "rows": rows, "note": LAG_NOTE}


def retention(videoId):
    _, _, ana = _services()
    resp = _call(ana.reports().query(
        ids="channel==MINE", startDate="2005-04-23", endDate=_today(),
        dimensions="elapsedVideoTimeRatio", filters=f"video=={videoId}",
        metrics="audienceWatchRatio,relativeRetentionPerformance"))
    return {"videoId": videoId,
            "points": [{"ratio": r["elapsedVideoTimeRatio"], "audienceWatchRatio": r["audienceWatchRatio"],
                        "relativeRetentionPerformance": r["relativeRetentionPerformance"]}
                       for r in _rows(resp)]}


def traffic_sources(videoId=None, startDate=None, endDate=None):
    _, _, ana = _services()
    kw = {"filters": f"video=={videoId}"} if videoId else {}
    resp = _call(ana.reports().query(
        ids="channel==MINE", startDate=startDate or "2005-04-23", endDate=endDate or _today(),
        dimensions="insightTrafficSourceType", metrics="views,estimatedMinutesWatched",
        sort="-views", **kw))
    return {"rows": [{"source": r["insightTrafficSourceType"], "views": r["views"],
                      "estimatedMinutesWatched": r["estimatedMinutesWatched"]} for r in _rows(resp)]}


# ---------- reach (Reporting API) ----------

def _load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def reach(startDate=None, endDate=None):
    creds, _, _ = _services()
    rep = build("youtubereporting", "v1", credentials=creds, cache_discovery=False)
    state = _load_state()
    job_id = state.get("reachJobId")
    if not job_id:
        jobs = _call(rep.jobs().list()).get("jobs", [])
        job = next((j for j in jobs if j["reportTypeId"] == "channel_reach_basic_a1"), None)
        if not job:
            job = _call(rep.jobs().create(body={"reportTypeId": "channel_reach_basic_a1",
                                                "name": "ytmcp reach"}))
            state["reachJobCreated"] = _today()
        job_id = job["id"]
        state["reachJobId"] = job_id
        STATE.write_text(json.dumps(state))
    reports = _call(rep.jobs().reports().list(jobId=job_id)).get("reports", [])
    if not reports:
        return {"rows": [], "latestReportDate": None,
                "note": "No reach reports yet. YouTube generates the first one about a day after the "
                        "job is created; try again tomorrow."}
    REPORTS.mkdir(parents=True, exist_ok=True)
    session = AuthorizedSession(creds)
    agg, latest = {}, None
    for r in reports:
        f = REPORTS / f"{r['id']}.csv"
        if not f.exists():
            resp = session.get(r["downloadUrl"], timeout=60)
            if resp.status_code != 200:
                raise ToolFailure(f"Could not download a reach report (HTTP {resp.status_code}).")
            f.write_bytes(resp.content)
        for row in csv.DictReader(io.StringIO(f.read_text(encoding="utf-8"))):
            d = row.get("date", "")
            d = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if d.isdigit() and len(d) == 8 else d
            if (startDate and d < startDate) or (endDate and d > endDate):
                continue
            latest = max(latest, d) if latest else d
            imp = float(row.get("video_thumbnail_impressions") or 0)
            ctr = float(row.get("video_thumbnail_impressions_ctr") or 0)
            a = agg.setdefault(row["video_id"], [0.0, 0.0])
            a[0] += imp
            a[1] += imp * ctr
    # The Reporting API gives CTR as a fraction (0.054); convert to a percentage.
    rows = [{"videoId": v, "impressions": int(a[0]),
             "ctr": round(a[1] / a[0] * 100, 2) if a[0] else None} for v, a in agg.items()]
    return {"rows": rows, "latestReportDate": latest, "note": "Reach data lags about 2 days."}


# ---------- snapshot ----------

def sync_snapshot():
    ch = get_channel()
    vids = list_videos(200)["videos"]
    notes = []
    stats = {r["videoId"]: r for r in video_stats()["rows"]}
    try:
        rr = reach()
        rch = {r["videoId"]: r for r in rr["rows"]}
        if not rr["rows"]:
            notes.append(rr["note"])
    except ToolFailure as e:
        rch = {}
        notes.append(f"Reach unavailable: {e}")
    missing = 0
    out = []
    for v in vids:
        s, r = stats.get(v["videoId"]), rch.get(v["videoId"])
        if s is None:
            missing += 1
        out.append({"videoId": v["videoId"], "title": v["title"], "publishedAt": v["publishedAt"],
                    "type": v["type"], "views": v["views"],
                    "avdSec": s["averageViewDurationSec"] if s else None,
                    "avp": s["averageViewPercentage"] if s else None,
                    "subs": s["subscribersGained"] if s else None,
                    "impressions": r["impressions"] if r else None,
                    "ctr": r["ctr"] if r else None})
    if missing:
        notes.append(f"Analytics not processed yet for {missing} video(s).")
    if rch and any(v["impressions"] is None for v in out):
        notes.append("Reach data missing for some videos (not reported yet).")
    return {"syncedAt": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "channel": {"title": ch["title"], "subscribers": ch["subscribers"], "views": ch["views"]},
            "videos": out, "notes": notes}
