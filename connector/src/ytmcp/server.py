from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import core

mcp = FastMCP("youtube-analytics")
RO = ToolAnnotations(readOnlyHint=True)


def _wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except core.ToolFailure as e:
        raise ValueError(str(e))
    except Exception:
        core.log.exception("tool failed")
        raise ValueError("Unexpected error; see server.log in %APPDATA%\\youtube-analytics-mcp.")


@mcp.tool(annotations=RO)
def get_channel() -> dict:
    """Channel title, handle, subscribers, total views and video count."""
    return _wrap(core.get_channel)


@mcp.tool(annotations=RO)
def list_videos(limit: int = 50) -> dict:
    """Public uploads, newest first (limit max 200)."""
    return _wrap(core.list_videos, limit)


@mcp.tool(annotations=RO)
def video_stats(startDate: str | None = None, endDate: str | None = None) -> dict:
    """Per-video Analytics metrics (YYYY-MM-DD dates; default all time)."""
    return _wrap(core.video_stats, startDate, endDate)


@mcp.tool(annotations=RO)
def retention(videoId: str) -> dict:
    """Audience retention curve (100 points) for one video."""
    return _wrap(core.retention, videoId)


@mcp.tool(annotations=RO)
def traffic_sources(videoId: str | None = None, startDate: str | None = None,
                    endDate: str | None = None) -> dict:
    """Views by traffic source type, for one video or the whole channel."""
    return _wrap(core.traffic_sources, videoId, startDate, endDate)


@mcp.tool(annotations=RO)
def reach(startDate: str | None = None, endDate: str | None = None) -> dict:
    """Thumbnail impressions and CTR (%) per video from the Reporting API."""
    return _wrap(core.reach, startDate, endDate)


@mcp.tool(annotations=RO)
def sync_snapshot() -> dict:
    """Channel + all videos merged with Analytics and reach data; unavailable metrics are null."""
    return _wrap(core.sync_snapshot)
