"""从 zh.verbformen.net（Netzverb 词典，CC BY-SA 4.0）获取并解析词条页面。"""
import html as htmlmod
import re
import threading
import time
from urllib.parse import quote

import httpx
from lxml import html

BASE = "https://zh.verbformen.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
MIN_INTERVAL = 1.5  # 两次请求之间至少间隔的秒数，避免给网站造成压力

_lock = threading.Lock()
_last_request = 0.0


def fetch(path: str) -> str:
    """path 形如 '/?w=gehen'、'/search/?w=Häuser' 或 '/declension/nouns/Haus.htm'"""
    global _last_request
    with _lock:
        wait = MIN_INTERVAL - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            r = httpx.get(BASE + path, headers={"User-Agent": UA},
                          follow_redirects=True, timeout=20)
        finally:
            _last_request = time.time()
    r.raise_for_status()
    return r.text


# ---------- 文本工具 ----------

def clean(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\s+([,.;:!?)])", r"\1", s)


def text(el) -> str:
    return clean(el.text_content()) if el is not None else ""


def rich(el) -> str:
    """把元素转成安全的 HTML：只保留 <u>（不规则变化部分），其余全部转为纯文本。"""
    out = []

    def walk(e):
        if not isinstance(e.tag, str):
            return
        if e.tag in ("img", "script", "style") or (e.tag == "a" and not e.text_content().strip()):
            if e.tail:
                out.append(htmlmod.escape(e.tail))
            return
        is_u = e.tag == "u"
        if is_u:
            out.append("<u>")
        if e.text:
            out.append(htmlmod.escape(e.text))
        for c in e:
            walk(c)
        if is_u:
            out.append("</u>")
        if e.tail:
            out.append(htmlmod.escape(e.tail))

    if el is None:
        return ""
    if el.text:
        out.append(htmlmod.escape(el.text))
    for c in el:
        walk(c)
    s = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", "".join(out))  # 去掉脚注标记
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def first(el, xp):
    r = el.xpath(xp)
    return r[0] if r else None


def strip_article(w: str) -> str:
    return re.sub(r"^(der|die|das|am)\s+", "", w.strip(), flags=re.I)


# ---------- 解析 ----------

KIND_MAP = [("动词", "verb"), ("名词", "noun"), ("形容词", "adjective"), ("副词", "adverb"),
            ("介词", "preposition"), ("连词", "conjunction"), ("代词", "pronoun"),
            ("冠词", "article"), ("粒子", "particle"), ("数词", "numeral")]


def kind_of(label: str) -> str:
    for zh, k in KIND_MAP:
        if zh in label:
            return k
    return "other"


def parse_tags(p):
    """'A1 · 名词 · 中性 · 不规则的' -> (level, [tags])"""
    if p is None:
        return "", []
    parts = [clean(re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", x)) for x in text(p).split("·")]
    parts = [x for x in parts if x]
    level = parts[0] if parts and re.fullmatch(r"[ABC][12]", parts[0]) else ""
    return level, parts[1:] if level else parts


def english_of(el):
    en = first(el, ".//span[@lang='en']")
    if en is None:
        return []
    return [w for w in (clean(x) for x in text(en).split(",")) if w]


def parse_example_li(li):
    img = first(li, ".//img[contains(@src,'/en.svg')]")
    if img is not None and img.getparent() is li:
        # 英文直接跟在 <img> 后面（不在单独的 span 里）
        en = clean(img.tail or "")
        img.tail = ""
        return {"de": clean(text(li).lstrip("»")), "en": en}
    en_span = img.getparent() if img is not None else None
    en = text(en_span) if en_span is not None else ""
    de_parts = []
    if li.text:
        de_parts.append(li.text)
    for c in li:
        if c is en_span or c.tag == "br":
            if c.tail and c is not en_span:
                de_parts.append(c.tail)
            if c is en_span:
                break
            continue
        if c.tag == "a" and not c.text_content().strip():
            de_parts.append(c.tail or "")
            continue
        de_parts.append(c.text_content() + (c.tail or ""))
    de = clean("".join(de_parts))
    if en and de.endswith(en):
        de = clean(de[: -len(en)])
    return {"de": de, "en": en}


def parse_header(box):
    tag_p = first(box, ".//p[.//span[contains(@class,'bZrt')]]")
    if tag_p is None:
        tag_p = first(box, ".//p[contains(@class,'rInf')][1]")
    level, tags = parse_tags(tag_p)
    grund = first(box, ".//*[contains(@class,'vGrnd')]")
    lemma = text(grund)
    audio = first(grund, ".//a[contains(@href,'.mp3')]/@href") if grund is not None else None
    stm = first(box, ".//p[contains(@class,'vStm')]")
    info = {
        "level": level,
        "tags": tags,
        "lemma": lemma,
        "audio": audio,
        "forms": rich(stm) if stm is not None else "",
        "notes": "",
        "english": english_of(box),
        "ipa": "",
        "definition": "",
        "valency": "",
        "example": None,
    }
    note = first(box, ".//p[contains(@class,'rCntr') and contains(@class,'rInf')]")
    if note is not None:
        parts = [clean(t) for t in note.itertext()]
        info["notes"] = " · ".join(t for t in parts if t)
    for p in box.xpath(".//p"):
        t = text(p)
        if not info["ipa"] and t.startswith("/"):
            info["ipa"] = t
        elif not info["valency"] and p.xpath(".//span[contains(@class,'bKas')]"):
            info["valency"] = t
        elif t.startswith("»") and info["example"] is None:
            li_like = parse_example_li(p)
            info["example"] = {"de": clean(li_like["de"].lstrip("»")), "en": li_like["en"]}
        elif (not info["definition"] and p.xpath("./i") and not t.startswith("»")
              and "vStm" not in p.get("class", "")):
            info["definition"] = t
    return info


def section_title(sec):
    h2 = first(sec, "./header//h2")
    if h2 is not None:
        return text(h2)
    sub = first(sec, "./header//span[contains(@class,'rInf')]")
    return text(sub)


def parse_tables(sec):
    tables = []
    for tbl in sec.xpath(".//div[contains(@class,'vTbl')]"):
        rows = []
        for tr in tbl.xpath(".//tr"):
            cells = [rich(td) for td in tr.xpath("./td|./th")]
            if any(c and c != "-" for c in cells):
                rows.append(cells)
        if rows:
            tables.append({"title": text(first(tbl, ".//h2")) or text(first(tbl, ".//h3")),
                           "rows": rows})
    return tables


def parse_detail(art, doc):
    sections = art.xpath(".//section[contains(@class,'rBox')]")
    header = parse_header(sections[0]) if sections else {}
    intro_p = first(art, "./div/p[1]")
    summary = ""
    if intro_p is not None:
        for hidden in intro_p.xpath(".//*[contains(@class,'rZu') or contains(@class,'kLnk') or contains(@class,'rInf')]"):
            hidden.drop_tree()
        summary = text(intro_p)

    h1 = text(first(art, ".//h1"))
    kind = kind_of(h1)
    groups, examples, definitions, usages = [], [], [], []
    for i, sec in enumerate(sections[1:], start=1):
        title = section_title(sec)
        if title == "例子":
            examples = [parse_example_li(li) for li in sec.xpath(".//ul/li")]
            continue
        if title == "定义":
            definitions = [text(li) for li in sec.xpath(".//ul/li")]
            continue
        if title == "介词":
            usages = [text(li) for li in sec.xpath(".//ul/li")]
            continue
        tables = parse_tables(sec)
        if not tables:
            continue
        # 动词页面的第一个表格区块是后面各区块的摘要，跳过避免重复
        if kind == "verb" and i == 1 and not sec.xpath("./header//h2"):
            continue
        groups.append({"title": title, "tables": tables})

    trans_zh = text(first(doc, "//dd[@lang='zh']"))
    return {
        "type": "detail",
        "kind": kind,
        "heading": h1,
        "summary": summary,
        **header,
        "groups": groups,
        "examples": examples,
        "definitions": definitions,
        "usages": usages,
        "chinese_site": [w for w in (clean(x) for x in trans_zh.split(",")) if w],
    }


def parse_list_entry(div):
    level, tags = parse_tags(first(div, ".//p[contains(@class,'rKln')]"))
    word_el = first(div, ".//div[contains(@style,'flex')]//span[contains(@style,'1.44em')]")
    if word_el is None:
        word_el = first(div, ".//div[contains(@style,'flex')]/div")
    link = first(div, ".//a[contains(@class,'rKnpf')]/@href") or ""
    ps = div.xpath(".//p")
    entry = {
        "level": level,
        "tags": tags,
        "kind": kind_of(" ".join(tags[:1])),
        "lemma": re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", "", text(word_el)),
        "forms": "",
        "english": english_of(div),
        "ipa": "",
        "definition": "",
        "example": None,
        "link": link,
    }
    for p in ps:
        t = text(p)
        cls = p.get("class", "")
        if "rKln" in cls or not t:
            continue
        if t.startswith("/"):
            entry["ipa"] = t
        elif t.startswith("»"):
            ex = parse_example_li(p)
            entry["example"] = {"de": clean(ex["de"].lstrip("»")), "en": ex["en"]}
        elif "rNt" in cls and p.xpath("./i"):
            entry["definition"] = t
        elif not p.xpath(".//span[@lang]") and not entry["forms"] and "·" in t:
            entry["forms"] = rich(p)
    return entry


def parse(page: str) -> dict:
    doc = html.fromstring(page)
    for bad in doc.xpath("//script|//style|//svg|//nav|//footer|//aside|//*[contains(@class,'aAnz')]"):
        bad.drop_tree()
    arts = doc.xpath("//article")
    if not arts:
        return {"type": "notfound"}
    art = arts[0]
    entries = art.xpath(".//div[contains(@class,'bTrf')]")
    h1 = text(first(art, ".//h1"))
    if h1.startswith("包含") or entries:
        items = [parse_list_entry(e) for e in entries]
        items = [e for e in items if e["lemma"]]
        return {"type": "list", "entries": items} if items else {"type": "notfound"}
    return parse_detail(art, doc)


# ---------- 判断结果是否和查询词对得上 ----------

def all_forms(data: dict) -> set[str]:
    words = set()

    def add(s):
        s = re.sub(r"<[^>]+>", "", s or "").replace("·", "")
        for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", s):
            words.add(w.lower())

    add(data.get("lemma"))
    add(data.get("forms"))
    for g in data.get("groups", []):
        for t in g["tables"]:
            for row in t["rows"]:
                for c in row:
                    add(c)
    for e in data.get("entries", []):
        add(e["lemma"])
    return words


def matches(query: str, data: dict) -> bool:
    if data.get("type") == "notfound":
        return False
    q = query.strip().lower()
    forms = all_forms(data)
    return all(w.lower() in forms for w in re.findall(r"[A-Za-zÄÖÜäöüß]+", q))


def entry_score(query: str, e: dict) -> int:
    """搜索列表中每个词条和查询词的相关度：原形完全一致 > 变形中包含 > 其他。"""
    q = query.strip().lower()
    lemma = strip_article(e["lemma"]).replace("·", "").lower()
    if lemma == q:
        return 3
    if q in all_forms({"lemma": "", "forms": e.get("forms", "")}):
        return 2
    return 0


def rank_entries(query: str, data: dict) -> dict:
    if data.get("type") == "list":
        data["entries"].sort(key=lambda e: -entry_score(query, e))
        for e in data["entries"]:
            e["score"] = entry_score(query, e)
            e["match"] = e["score"] > 0
    return data
