import httpx
from dotenv import load_dotenv

from .paths import ENV_FILE, STATIC_DIR  # noqa: E402

load_dotenv(ENV_FILE)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from . import ai, dictionary, images, scraper, store, suggest  # noqa: E402
from .version import VERSION  # noqa: E402

app = FastAPI(title="德语词典")


@app.middleware("http")
async def revalidate_static(request, call_next):
    # 让浏览器每次都确认页面文件是否更新（没变时只返回 304，很快），改版后不用强制刷新
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/api/status")
def status():
    return {"ai": ai.enabled(), "key": ai.masked_key(), "version": VERSION}


class KeyIn(BaseModel):
    api_key: str


@app.post("/api/settings/key")
def set_key(body: KeyIn):
    if not body.api_key.strip():
        raise HTTPException(400, "请粘贴密钥")
    try:
        ai.save_key(body.api_key)
    except ai.AIError as e:
        raise HTTPException(400, str(e))
    return {"ai": True, "key": ai.masked_key()}


def prefetch_picture(res: dict) -> dict:
    """查到完整词条后立刻在后台开始找配图，前端请求时通常已经准备好了。"""
    d = res.get("result", {})
    if d.get("type") == "detail":
        images.picture({"lemma": scraper.strip_article(d["lemma"]), "kind": d["kind"],
                        "english": d.get("english", [])[:6]}, wait=False)
    return res


@app.get("/api/lookup")
def lookup(q: str, lang: str = ""):
    if not q.strip():
        raise HTTPException(400, "请输入单词")
    try:
        return prefetch_picture(dictionary.lookup(q, lang))
    except ai.AIError as e:
        raise HTTPException(503, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"无法连接 verbformen.net：{e}")


@app.get("/api/suggest")
def suggestions(q: str):
    return suggest.suggest(q)


@app.get("/api/open")
def open_path(path: str):
    try:
        return prefetch_picture(dictionary.open_path(path))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"无法连接 verbformen.net：{e}")


class GlossIn(BaseModel):
    lemma: str
    kind: str = ""
    tags: list[str] = []
    english: list[str] = []
    definitions: list[str] = []
    definition: str = ""


@app.post("/api/gloss")
def gloss(info: GlossIn):
    try:
        return ai.gloss(info.model_dump())
    except (ai.AIError, ValueError) as e:
        raise HTTPException(503, str(e))


@app.post("/api/image")
def image(info: GlossIn):
    return images.picture(info.model_dump())


@app.get("/api/thumb")
def thumb(url: str):
    if not images.allowed(url):
        raise HTTPException(400, "不支持的图片地址")
    try:
        return Response(images.thumbnail(url), media_type="image/jpeg",
                        headers={"Cache-Control": "max-age=604800"})
    except httpx.HTTPError:
        raise HTTPException(502, "无法获取图片")


class TranslateIn(BaseModel):
    text: str


@app.post("/api/translate")
def translate(body: TranslateIn):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "请输入要翻译的内容")
    if len(text) > 2000:
        raise HTTPException(400, "一次最多翻译 2000 个字符")
    try:
        return ai.translate(text)
    except (ai.AIError, ValueError) as e:
        raise HTTPException(503, str(e))


@app.get("/api/audio")
def audio(url: str):
    if not url.startswith("https://www.verbformen.de/") or not url.endswith(".mp3"):
        raise HTTPException(400, "不支持的音频地址")
    data = store.get_audio(url)
    if data is None:
        try:
            r = httpx.get(url, headers={"User-Agent": scraper.UA,
                                        "Referer": "https://zh.verbformen.net/"},
                          timeout=20, follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError:
            raise HTTPException(502, "无法获取发音")
        data = r.content
        store.put_audio(url, data)
    return Response(data, media_type="audio/mpeg")


@app.get("/api/history")
def history():
    return store.list_history()


@app.delete("/api/history")
def clear_history():
    store.clear_history()
    return {"ok": True}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
