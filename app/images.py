"""通过维基共享资源（Wikimedia Commons）的官方 API 为单词配图，不需要密钥。

DeepSeek 先给出简单的英文关键词，再在 Commons 搜索图片；图片下载到本地缓存后显示，
并注明作者和授权（Commons 的图片都是 CC BY / CC BY-SA / 公有领域等自由授权）。
整个过程在查词完成时就在后台开始（prefetch），前端请求配图时通常已经准备好了。
"""
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from html import unescape
from urllib.parse import urlparse

import httpx

from . import ai, store
from .version import PROJECT_URL, VERSION

API = "https://commons.wikimedia.org/w/api.php"
# 维基媒体要求程序在 User-Agent 里写明身份和联系方式：https://w.wiki/4wJS
HEADERS = {"User-Agent": f"german-dict/{VERSION} ({PROJECT_URL}; open-source German learning dictionary)"}

_pool = ThreadPoolExecutor(max_workers=4)
_jobs: dict[str, Future] = {}
_lock = threading.Lock()


def allowed(url: str) -> bool:
    # 缩略图现在多由 thumb.wikimedia.org 提供，原图和部分缩略图在 upload.wikimedia.org
    return url.startswith("https://") and urlparse(url).netloc in ("upload.wikimedia.org", "thumb.wikimedia.org")


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", html or ""))).strip()


def search(query: str) -> list[dict]:
    key = "commons:" + query.lower()
    hit = store.get_ai(key)
    if hit:
        return hit
    params = {
        "action": "query", "format": "json", "generator": "search",
        "gsrsearch": f"{query} filetype:bitmap", "gsrnamespace": 6, "gsrlimit": 10,
        "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 400,
        "iiextmetadatafilter": "Artist|LicenseShortName"}
    pages = []
    for _ in range(2):  # Commons 偶尔会返回空结果，重试一次
        r = httpx.get(API, headers=HEADERS, timeout=15, params=params)
        r.raise_for_status()
        pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 0))
        if pages:
            break
    words = [w for w in query.lower().split() if len(w) > 2]
    results = []
    for p in pages:
        info = (p.get("imageinfo") or [{}])[0]
        url = info.get("thumburl")
        if not url or not allowed(url) or info.get("mime") not in ("image/jpeg", "image/png", "image/webp"):
            continue
        meta = info.get("extmetadata", {})
        title = p["title"].removeprefix("File:")
        results.append({
            "thumb": url,
            "title": title,
            "creator": _text(meta.get("Artist", {}).get("value", ""))[:40] or "Wikimedia Commons",
            "license": meta.get("LicenseShortName", {}).get("value", ""),
            "link": info.get("descriptionurl") or "https://commons.wikimedia.org/",
            # 文件名里含有关键词的通常更贴切，排在前面；所有关键词都出现的最优先
            "_score": sum(w in title.lower() for w in words) + (len(words) if all(w in title.lower() for w in words) else 0),
        })
    results.sort(key=lambda x: -x.pop("_score"))
    results = results[:6]
    if results:  # 空结果不缓存，下次再试
        store.put_ai(key, results)
    return results


def thumbnail(url: str) -> bytes:
    data = store.get_audio(url)  # 和发音共用二进制缓存表
    if data is None:
        r = httpx.get(url, headers=HEADERS, timeout=15, follow_redirects=True)
        r.raise_for_status()
        data = r.content
        store.put_audio(url, data)
    return data


def _build(info: dict) -> dict:
    emoji, query = "", ""
    if ai.enabled():
        try:
            v = ai.visual(info)
            emoji, query = v.get("emoji", ""), (v.get("query") or "").strip()
        except (ai.AIError, ValueError):
            pass
    queries = [query] if query else []
    if not query and not emoji and info.get("kind") == "noun":
        queries = list(info.get("english") or [])[:3]  # DeepSeek 不可用时，名词退而用英文释义搜索
    found = []
    for q in queries:
        try:
            found = search(q)
        except (httpx.HTTPError, ValueError):
            found = []
        if found:
            query = q
            try:
                thumbnail(found[0]["thumb"])  # 顺便把第一张图下载好
            except httpx.HTTPError:
                pass
            break
    return {"emoji": emoji, "query": query, "images": found}


def picture(info: dict, wait: bool = True):
    """取配图。同一个词同时只会处理一次：查词时的后台预取和前端请求共用同一个任务。"""
    key = f"{info.get('lemma', '')}:{info.get('kind', '')}"
    with _lock:
        job = _jobs.get(key)
        # 上次失败或什么都没找到的，重新来过
        if job is None or (job.done() and (job.exception() or not (job.result()["images"] or job.result()["emoji"]))):
            job = _jobs[key] = _pool.submit(_build, info)
    return job.result(timeout=60) if wait else None
