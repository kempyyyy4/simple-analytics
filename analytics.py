"""Pulls everything the app shows.

Signs in through the YouTube connector (ytmcp.core), so there is one Google sign-in for both.
Read-only: the connector only asks for read scopes.
"""
import datetime as dt

from ytmcp import core

ALL_TIME = "2005-04-23"  # before YouTube existed, so this means "everything"


def _totals(ana, start, end):
    rows = core._rows(core._call(ana.reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
        metrics="views,estimatedMinutesWatched,subscribersGained")))
    r = rows[0] if rows else {}
    return {"views": r.get("views", 0),
            "watchHours": round(r.get("estimatedMinutesWatched", 0) / 60, 1),
            "subsGained": r.get("subscribersGained", 0)}


def _first_week(ana, video_id, published, today):
    start = dt.date.fromisoformat(published[:10])
    end = start + dt.timedelta(days=6)
    rows = core._rows(core._call(ana.reports().query(
        ids="channel==MINE", startDate=start.isoformat(), endDate=min(end, today).isoformat(),
        dimensions="video", metrics="views", filters=f"video=={video_id}")))
    # Analytics runs 2-3 days behind, so the first week is only final once that has passed.
    return {"views": rows[0]["views"] if rows else 0,
            "complete": end <= today - dt.timedelta(days=3)}


def _retention(ana, video_id, today):
    rows = core._rows(core._call(ana.reports().query(
        ids="channel==MINE", startDate=ALL_TIME, endDate=today.isoformat(),
        dimensions="elapsedVideoTimeRatio", filters=f"video=={video_id}",
        metrics="audienceWatchRatio")))
    return [[r["elapsedVideoTimeRatio"], r["audienceWatchRatio"]] for r in rows]


def _traffic(ana, video_id, today):
    rows = core._rows(core._call(ana.reports().query(
        ids="channel==MINE", startDate=ALL_TIME, endDate=today.isoformat(),
        dimensions="insightTrafficSourceType", metrics="views", sort="-views",
        filters=f"video=={video_id}")))
    return [{"source": r["insightTrafficSourceType"], "views": r["views"]} for r in rows]


def _safe(fn, default, notes, what, title):
    try:
        return fn()
    except core.ToolFailure as e:
        notes.append(f"No {what} for '{title}': {e}")
        return default


def pull():
    today = dt.date.today()
    _, _, ana = core._services()
    notes = []

    channel = core.get_channel()
    stats = {r["videoId"]: r for r in core.video_stats(ALL_TIME)["rows"]}

    try:
        reach = core.reach()
        reach_rows = {r["videoId"]: r for r in reach["rows"]}
        reach_latest = reach.get("latestReportDate")
        if not reach_rows and reach.get("note"):
            notes.append(reach["note"])
    except Exception as e:  # reach is optional; keep the rest of the pull
        reach_rows, reach_latest = {}, None
        notes.append(f"Impressions and CTR unavailable: {e}")

    videos = []
    for v in core.list_videos(200)["videos"]:
        vid, title = v["videoId"], v["title"]
        s = stats.get(vid, {})
        r = reach_rows.get(vid, {})
        if not s:
            notes.append(f"Analytics not processed yet for '{title}'.")
        videos.append({
            "videoId": vid, "title": title, "publishedAt": v["publishedAt"], "type": v["type"],
            "durationSec": v["durationSec"], "views": v["views"],
            "analytics": {"views": s.get("views"), "engagedViews": s.get("engagedViews"),
                          "avdSec": s.get("averageViewDurationSec"),
                          "avp": s.get("averageViewPercentage"),
                          "subs": s.get("subscribersGained")},
            "impressions": r.get("impressions"), "ctr": r.get("ctr"),
            "first7": _safe(lambda: _first_week(ana, vid, v["publishedAt"], today),
                            {"views": 0, "complete": False}, notes, "first-week data", title),
            "retention": _safe(lambda: _retention(ana, vid, today), [], notes, "retention curve", title),
            "traffic": _safe(lambda: _traffic(ana, vid, today), [], notes, "traffic sources", title),
        })

    last28 = (today - dt.timedelta(days=27), today)
    prev28 = (today - dt.timedelta(days=55), today - dt.timedelta(days=28))
    return {
        "pulledAt": dt.datetime.now().isoformat(timespec="seconds"),
        "channel": channel,
        "totals": {"last28": _totals(ana, *last28), "prev28": _totals(ana, *prev28)},
        "reachLatest": reach_latest,
        "videos": videos,
        "notes": notes,
    }
