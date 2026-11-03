"""查词流程：缓存 → verbformen → 搜索列表 → 变音替换 → AI 词形还原。"""
import re
from urllib.parse import quote

from . import ai, scraper, store

DETAIL_PREFIXES = ("/conjugation/", "/declension/")


def load(path: str) -> dict:
    page = store.get_page(path)
    if page is None:
        page = scraper.fetch(path)
        store.put_page(path, page)
    return scraper.parse(page)


def umlaut_variants(q: str) -> list[str]:
    out = []
    v = q.replace("ae", "ä").replace("oe", "ö").replace("ue", "ü")
    v = v.replace("Ae", "Ä").replace("Oe", "Ö").replace("Ue", "Ü")
    if v != q:
        out.append(v)
    if "ss" in v:
        out.append(v.replace("ss", "ß"))
    return out


def _resolve(q: str):
    """返回 (data, related) 或 None。"""
    data = load("/?w=" + quote(q))
    if data["type"] == "detail" and scraper.matches(q, data):
        return data, []
    if data["type"] != "list":
        data = load("/search/?w=" + quote(q))
    if data["type"] != "list":
        return None
    scraper.rank_entries(q, data)
    best = data["entries"][0]["score"]
    if best == 0:
        return None
    # 只有原形完全一致的词条算作主结果；仅变形里包含查询词的放到相关词
    matched = [e for e in data["entries"] if e["score"] == best]
    rest = [e for e in data["entries"] if e["score"] != best][:8]
    # 最匹配的词条有详情页（动词/名词/形容词）时直接打开，其余作为相关词
    if matched[0]["link"].startswith(DETAIL_PREFIXES):
        return load(matched[0]["link"]), matched[1:] + rest
    return {"type": "list", "entries": matched}, rest


LEVEL_RANK = {lv: i for i, lv in enumerate(["A1", "A2", "B1", "B2", "C1", "C2"])}


def _level(found) -> int:
    data = found[0]
    lv = data.get("level") if data["type"] == "detail" else (data["entries"][0].get("level"))
    return LEVEL_RANK.get(lv or "", 9)


def lookup(query: str, lang: str = "") -> dict:
    q = re.sub(r"\s+", " ", query).strip()
    if re.search(r"[一-鿿]", q):
        return lookup_foreign(q, "zh")
    if lang == "en":
        return lookup_foreign(q, "en")
    q = re.sub(r"^(der|die|das)\s+(?=\S)", "", q, flags=re.I)
    note = ""
    found = _resolve(q)
    # 输入里有 ae/oe/ue/ss 时，也试试变音字母写法，取更常用（等级更低）的那个
    for v in umlaut_variants(q):
        alt = _resolve(v)
        if alt and (found is None or _level(alt) < _level(found)):
            found, note = alt, f"按 “{v}” 查询"
    if found is None and ai.enabled():
        try:
            guess = ai.lemma(q)
        except ai.AIError:
            guess = {}
        if guess.get("lang") == "en":
            return lookup_foreign(q, "en")
        lem = (guess.get("lemma") or "").strip()
        if lem and lem.lower() != q.lower():
            found = _resolve(lem)
            if found:
                note = guess.get("note") or f"原形：{lem}"
    if found is None and " " in q and ai.enabled():
        # 词典只收单词；短语和固定搭配交给 AI 讲解，并拆出每个单词供点击查询
        return {"query": q, "result": {"type": "phrase", **ai.phrase(q)}, "related": [], "note": ""}
    if found is None:
        return {"query": q, "result": {"type": "notfound"}, "related": [], "note": ""}

    data, related = found
    if not note and data["type"] == "detail":
        lemma = scraper.strip_article(data["lemma"]).replace("·", "")
        if lemma.lower() != q.lower():
            note = f"“{q}” 是 {data['lemma'].replace('·', '')} 的变化形式"
    _record(data)
    return {"query": q, "result": data, "related": related, "note": note}


def lookup_foreign(q: str, src: str) -> dict:
    """中文/英语查德语：由 DeepSeek 给出候选德语词，用户点选后再查完整词条。"""
    if not ai.enabled():
        raise ai.AIError(("中文" if src == "zh" else "英语") + "查词需要 DeepSeek，请点击右上角的设置按钮添加密钥")
    cands = ai.to_german(q, src).get("candidates") or []
    result = {"type": "foreign", "src": src, "candidates": cands} if cands else {"type": "notfound"}
    return {"query": q, "result": result, "related": [], "note": ""}


def open_path(path: str) -> dict:
    if not path.startswith(DETAIL_PREFIXES) or ".." in path:
        raise ValueError("不支持的路径")
    data = load(path)
    _record(data)
    return {"query": data.get("lemma", ""), "result": data, "related": [], "note": ""}


def _record(data):
    if data["type"] == "detail":
        store.add_history(scraper.strip_article(data["lemma"]), data.get("level", ""), data["kind"])
    elif data["type"] == "list" and data["entries"]:
        e = data["entries"][0]
        store.add_history(scraper.strip_article(e["lemma"]), e.get("level", ""), e["kind"])
