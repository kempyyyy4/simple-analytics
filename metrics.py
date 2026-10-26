"""Turns the raw pull into colour statuses, drop-offs, a verdict and a diagnosis.

The rules and numbers live here. The plain-English wording lives in diagnosis.json.
"""
import datetime as dt
import statistics

MIN_IMPRESSIONS = 500     # CTR isn't judged below this
MIN_VIEWS = 100           # view-based ratios aren't judged below this
TOO_EARLY_HOURS = 48
DROP_FLAG_PP = 5          # one drop this big (percentage points of the audience) counts as big
ONE_SOURCE_SHARE = 70     # % of views from one traffic source
JUDGED = ("red", "amber", "green")

METRIC_KEYS = {
    "long": ["ctr", "avp", "first30", "subsPer1k"],
    "short": ["engaged", "avp", "subsPer1k"],
}
SOURCE_NAMES = {
    "YT_SEARCH": "YouTube search",
    "BROWSE_FEATURES": "browse features",
    "SUGGESTED_VIDEO": "suggested videos",
    "EXT_URL": "external websites",
    "NOTIFICATION": "notifications",
    "CHANNEL_PAGE": "the channel page",
    "PLAYLIST": "playlists",
    "SHORTS": "the Shorts feed",
    "SUBSCRIBER": "the subscriptions feed",
    "NO_LINK_OTHER": "direct or unknown",
    "YT_OTHER_PAGE": "other YouTube pages",
}


class _Blank(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def _fill(text, params):
    return text.format_map(_Blank(params))


def _hours_since(iso, now):
    published = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return (now - published).total_seconds() / 3600


def _median(values):
    vals = [v for v in values if v is not None]
    return statistics.median(vals) if vals else None


def _band_status(value, band):
    if value < band["red_below"]:
        return "red"
    if value > band["green_above"]:
        return "green"
    return "amber"


def _judge(value, band, blocked=None):
    """blocked: why this number can't be judged yet. Shows the value, but no colour."""
    if blocked:
        return {"value": value, "status": "early", "note": blocked}
    if value is None:
        return {"value": None, "status": "na", "note": "Not available yet"}
    if band is None:
        return {"value": value, "status": "none", "note": ""}
    return {"value": value, "status": _band_status(value, band), "note": ""}


def fmt_time(seconds):
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def first_30(points, duration):
    """Share of viewers still watching at 30 seconds, interpolated between the curve's points."""
    if not duration or duration <= 30:
        return None
    target = 30 / duration
    prev = None
    for ratio, watch in points:
        if ratio >= target:
            if prev is None or ratio == prev[0]:
                return round(watch * 100, 2)
            r0, w0 = prev
            f = (target - r0) / (ratio - r0)
            return round((w0 + f * (watch - w0)) * 100, 2)
        prev = (ratio, watch)
    return None


def dropoffs(points, duration, window=5, count=3):
    """The biggest falls in the retention curve, as the time they end and the points lost."""
    if len(points) <= window or not duration:
        return []
    drop = {i: (points[i - window][1] - points[i][1]) * 100 for i in range(window, len(points))}
    chosen = []
    for i in sorted(drop, key=lambda k: -drop[k]):
        if drop[i] < 1:
            break
        if all(abs(i - j) > window for j in chosen):
            chosen.append(i)
        if len(chosen) == count:
            break
    out = []
    for i in chosen:
        sec = points[i][0] * duration
        out.append({"sec": round(sec), "time": fmt_time(sec), "lost": round(drop[i], 1)})
    return sorted(out, key=lambda d: d["sec"])


def traffic_shares(rows):
    total = sum(r["views"] for r in rows)
    out = []
    for r in sorted(rows, key=lambda r: -r["views"]):
        share = r["views"] / total * 100 if total else 0
        out.append({"source": r["source"],
                    "name": SOURCE_NAMES.get(r["source"], r["source"].replace("_", " ").lower()),
                    "views": r["views"], "share": round(share, 1)})
    return out


def video_view(v, targets, ctx, texts, now):
    kind = v["type"]
    bands = targets.get(kind, {})
    a = v.get("analytics") or {}
    views = a["views"] if a.get("views") is not None else v.get("views", 0)
    impressions, ctr = v.get("impressions"), v.get("ctr")
    avp, subs, engaged = a.get("avp"), a.get("subs"), a.get("engagedViews")
    hours = _hours_since(v["publishedAt"], now)
    too_early = hours < TOO_EARLY_HOURS
    duration = v.get("durationSec") or 0
    retention = sorted(v.get("retention") or [])

    subs_per_1k = round(subs / views * 1000, 2) if views and subs is not None else None
    engaged_rate = round(engaged / views * 100, 2) if views and engaged is not None else None
    first30_value = first_30(retention, duration) if kind == "long" else None
    drops = dropoffs(retention, duration)
    shares = traffic_shares(v.get("traffic") or [])

    early_why = "Too early to judge (under 48 hours old)" if too_early else None
    ratio_block = early_why or (None if views >= MIN_VIEWS else f"Only {views} views so far (needs {MIN_VIEWS})")
    if early_why:
        ctr_block = early_why
    elif impressions is None:
        ctr_block = "Impressions and CTR lag about 2 days"
    elif impressions < MIN_IMPRESSIONS:
        ctr_block = f"Only {impressions} impressions so far (needs {MIN_IMPRESSIONS})"
    else:
        ctr_block = None

    m = {
        "ctr": _judge(ctr, bands.get("ctr") if kind == "long" else None, ctr_block),
        "avp": _judge(avp, bands.get("avp"), ratio_block),
        "subsPer1k": _judge(subs_per_1k, bands.get("subsPer1k"), ratio_block),
    }
    if kind == "long":
        m["first30"] = _judge(first30_value, bands.get("first30"),
                              early_why or (None if first30_value is not None else "Needs a video over 30 seconds"))
    else:
        m["engaged"] = _judge(engaged_rate, bands.get("engaged"), ratio_block)

    def flagged(key):
        return m.get(key, {}).get("status") in ("red", "amber")

    median_impr = ctx["median_impr"]
    normal_impr = impressions is not None and impressions >= MIN_IMPRESSIONS and (
        median_impr is None or impressions >= 0.5 * median_impr)
    low_impr = (not too_early and impressions is not None and (
        impressions < MIN_IMPRESSIONS or (median_impr is not None and impressions < 0.5 * median_impr)))

    hits = []  # (rule id, metric, template values)
    if flagged("ctr") and normal_impr:
        hits.append(("packaging_clicks", "ctr", {}))
    if low_impr:
        hits.append(("low_impressions", "impressions", {}))
    if kind == "long" and m["ctr"]["status"] == "green" and flagged("avp"):
        hits.append(("ctr_good_avp_low", "avp", {}))
    if kind == "long" and flagged("first30"):
        hits.append(("weak_hook", "first30", {}))
    if drops and not too_early:
        big = max(drops, key=lambda d: d["lost"])
        if big["lost"] >= DROP_FLAG_PP:
            hits.append(("big_drop", "avp", {"time": big["time"], "lost": round(big["lost"])}))
    if flagged("subsPer1k"):
        hits.append(("no_return", "subsPer1k", {}))
    if kind == "short" and flagged("engaged"):
        hits.append(("short_hook", "engaged", {}))
    if kind == "short" and flagged("avp"):
        hits.append(("short_end", "avp", {}))
    if shares and shares[0]["share"] >= ONE_SOURCE_SHARE and not too_early:
        hits.append(("one_source", "traffic", {"source": shares[0]["name"], "share": round(shares[0]["share"])}))

    diagnosis = []
    covered = set()
    for rid, metric, params in hits:
        item = texts.get("problems", {}).get(rid)
        if not item:
            continue
        covered.add(metric)
        diagnosis.append({"id": rid, "metric": metric, "status": m.get(metric, {}).get("status"),
                          "title": _fill(item["title"], params), "why": _fill(item["why"], params),
                          "try": _fill(item["try"], params)})
    for key in m:
        if m[key]["status"] in JUDGED and key not in covered:
            generic = texts.get("generic", {}).get(key)
            if generic:
                diagnosis.append({"id": f"generic_{key}", "metric": key, "status": m[key]["status"],
                                  "title": _generic_title(key),
                                  "why": generic["why"], "try": generic["try"]})

    def has(rid):
        return any(h[0] == rid for h in hits)

    any_flagged = any(flagged(k) for k in m)
    any_missing = any(m[k]["status"] in ("early", "na") for k in METRIC_KEYS[kind])
    if too_early:
        verdict = "too_early"
    elif kind == "long":
        content_ok = m["avp"]["status"] != "red" and m.get("first30", {}).get("status") != "red"
        if has("packaging_clicks"):
            verdict = "packaging" if content_ok else "packaging_and_delivery"
        elif has("low_impressions"):
            verdict = "distribution"
        elif has("ctr_good_avp_low"):
            verdict = "delivery"
        elif has("weak_hook") or has("big_drop"):
            verdict = "retention"
        elif has("no_return"):
            verdict = "no_return"
        elif any_flagged:
            verdict = "mixed"
        elif any_missing:
            verdict = "not_enough"
        else:
            verdict = "working"
    else:
        if has("short_hook"):
            verdict = "short_hook"
        elif has("low_impressions"):
            verdict = "distribution"
        elif has("short_end"):
            verdict = "short_end"
        elif has("no_return"):
            verdict = "no_return"
        elif any_flagged:
            verdict = "mixed"
        elif any_missing:
            verdict = "not_enough"
        else:
            verdict = "short_working"

    return {
        "videoId": v["videoId"], "title": v["title"], "publishedAt": v["publishedAt"],
        "type": kind, "durationSec": duration, "views": views,
        "impressions": impressions, "ctr": ctr, "avdSec": a.get("avdSec"), "avp": avp,
        "subs": subs, "subsPer1k": subs_per_1k, "engagedRate": engaged_rate,
        "first30": first30_value, "hoursOld": round(hours, 1),
        "metrics": m,
        "verdict": {"id": verdict, "text": texts.get("verdicts", {}).get(verdict, verdict)},
        "diagnosis": diagnosis,
        "drops": drops,
        "retention": [[round(r * duration, 1), round(w * 100, 2)] for r, w in retention] if duration else [],
        "traffic": shares,
        "first7": {**v.get("first7", {}), "median": ctx["median_first7"]},
    }


def _generic_title(key):
    return {"ctr": "Click-through is below target", "avp": "Viewers watch a small share",
            "first30": "Early drop-off", "engaged": "Swiped away too early",
            "subsPer1k": "Not converting into subscribers"}.get(key, key)


def channel_averages(videos, targets):
    out = {}
    for kind, keys in METRIC_KEYS.items():
        items = []
        for key in keys:
            band = targets.get(kind, {}).get(key)
            if not band:
                continue
            vals = [v["metrics"][key]["value"] for v in videos
                    if v["type"] == kind and v["metrics"][key]["status"] in JUDGED]
            dec = band.get("decimals", 1)
            unit = band.get("unit", "")
            item = {"key": key, "label": band["label"], "unit": unit, "n": len(vals),
                    "red_below": band["red_below"], "green_above": band["green_above"]}
            if vals:
                avg = round(statistics.mean(vals), dec)
                status = _band_status(avg, band)
                zone = {"red": "red", "amber": "amber", "green": "green"}[status]
                item.update(avg=avg, status=status,
                            summary=(f"Averages {avg:.{dec}f}{unit} across {len(vals)} video(s): "
                                     f"{zone} zone. Green is above {band['green_above']}{unit}."))
            else:
                item.update(avg=None, status="none",
                            summary="No videos are old enough and big enough to judge yet.")
            items.append(item)
        out[kind] = items
    return out


def build_view(raw, targets, texts):
    now = dt.datetime.now(dt.timezone.utc)
    vids = raw["videos"]
    eligible = [v for v in vids if _hours_since(v["publishedAt"], now) >= TOO_EARLY_HOURS]
    ctx = {
        "median_impr": _median(v.get("impressions") for v in eligible),
        "median_first7": _median(v["first7"]["views"] for v in vids if v.get("first7", {}).get("complete")),
    }
    videos = [video_view(v, targets, ctx, texts, now) for v in vids]
    videos.sort(key=lambda x: x["publishedAt"], reverse=True)
    last, prev, ch = raw["totals"]["last28"], raw["totals"]["prev28"], raw["channel"]
    return {
        "pulledAt": raw.get("pulledAt"),
        "channel": ch,
        "totals": {
            "subscribers": ch["subscribers"], "channelViews": ch["views"],
            "views28": last["views"], "views28prev": prev["views"],
            "watchHours28": last["watchHours"], "watchHours28prev": prev["watchHours"],
            "subsGained28": last["subsGained"], "subsGained28prev": prev["subsGained"],
        },
        "reachLatest": raw.get("reachLatest"),
        "notes": raw.get("notes", []),
        "videos": videos,
        "averages": channel_averages(videos, targets),
        "targets": targets,
    }
