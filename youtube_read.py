from __future__ import annotations

import datetime
import inspect
from typing import Dict, List

from youtubesearchpython import VideosSearch
import httpx


def _patch_youtube_httpx() -> None:
    try:
        from youtubesearchpython.core import requests as yts_requests
    except Exception:
        return

    supports_proxies = "proxies" in inspect.signature(httpx.post).parameters

    def sync_post(self):
        kwargs = {
            "headers": {"User-Agent": yts_requests.userAgent},
            "json": self.data,
            "timeout": self.timeout,
        }
        if supports_proxies:
            kwargs["proxies"] = self.proxy
        return httpx.post(self.url, **kwargs)

    def sync_get(self):
        kwargs = {
            "headers": {"User-Agent": yts_requests.userAgent},
            "timeout": self.timeout,
            "cookies": {"CONSENT": "YES+1"},
        }
        if supports_proxies:
            kwargs["proxies"] = self.proxy
        return httpx.get(self.url, **kwargs)

    async def async_post(self):
        client_kwargs = {"timeout": self.timeout}
        if supports_proxies:
            client_kwargs["proxies"] = self.proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            return await client.post(self.url, headers={"User-Agent": yts_requests.userAgent}, json=self.data)

    async def async_get(self):
        client_kwargs = {"timeout": self.timeout}
        if supports_proxies:
            client_kwargs["proxies"] = self.proxy
        async with httpx.AsyncClient(**client_kwargs) as client:
            return await client.get(
                self.url,
                headers={"User-Agent": yts_requests.userAgent},
                cookies={"CONSENT": "YES+1"},
            )

    yts_requests.RequestCore.syncPostRequest = sync_post
    yts_requests.RequestCore.syncGetRequest = sync_get
    yts_requests.RequestCore.asyncPostRequest = async_post
    yts_requests.RequestCore.asyncGetRequest = async_get


_patch_youtube_httpx()


DEFAULT_CATEGORIES = {
    "Sports": ["cricket", "football", "kabaddi", "sports", "match", "tournament"],
    "Cinema": ["movie", "film", "trailer", "cinema", "actor", "actress", "kollywood", "teaser"],
    "Politics": ["politics", "election", "government", "minister", "assembly"],
}


def get_categorized_videos(
    *,
    queries: List[str],
    max_results: int = 50,
    days: int = 2,
    categories: Dict[str, List[str]] | None = None,
) -> Dict[str, List[dict]]:
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
    categorized: Dict[str, List[dict]] = {k: [] for k in (categories or DEFAULT_CATEGORIES)}
    categorized.setdefault("Other", [])

    for q in queries:
        results = VideosSearch(q, limit=max_results).result().get("result", [])
        for video in results:
            _parse_video(video, categorized, cutoff_date, categories or DEFAULT_CATEGORIES)

    return categorized


def _parse_video(
    video: dict,
    categorized: Dict[str, List[dict]],
    cutoff_date: datetime.datetime,
    categories: Dict[str, List[str]],
) -> None:
    title = video.get("title", "") or ""
    description = video.get("description", "") or ""
    publish_time = video.get("publishedTime", "")
    video_id = video.get("id", "") or video.get("link", "")
    channel = ""
    if isinstance(video.get("channel"), dict):
        channel = video.get("channel", {}).get("name", "") or ""
    thumbnail = ""
    thumbnails = video.get("thumbnails") or []
    if thumbnails and isinstance(thumbnails, list):
        thumbnail = thumbnails[0].get("url", "") if isinstance(thumbnails[0], dict) else thumbnails[0]

    published_dt = datetime.datetime.now()
    if isinstance(video.get("publishedTime"), str) and video.get("publishedTime"):
        published_dt = datetime.datetime.now()

    if published_dt < cutoff_date:
        return

    text = f"{title.lower()} {description.lower()}".strip()
    assigned_category = "Other"
    for category, keywords in categories.items():
        if any(keyword in text for keyword in keywords):
            assigned_category = category
            break

    categorized.setdefault(assigned_category, []).append(
        {
            "id": video_id,
            "title": title,
            "thumbnail_url": thumbnail,
            "channel_title": channel,
            "published_at": published_dt.isoformat(),
            "description": description,
            "tags": [],
        }
    )
