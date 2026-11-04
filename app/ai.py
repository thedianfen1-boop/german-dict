"""DeepSeek：中文释义、用法说明、句子翻译、词形还原。结果都缓存在本地。"""
import hashlib
import json
import os

import httpx

from . import settings, store


def _config():
    return (os.getenv("DEEPSEEK_API_KEY", "").strip(),
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
            os.getenv("DEEPSEEK_MODEL", "deepseek-flash"))


def enabled() -> bool:
    key = _config()[0]
    return bool(key) and not key.startswith("在这里")


class AIError(Exception):
    pass


def masked_key() -> str:
    return settings.mask(_config()[0]) if enabled() else ""


def save_key(key: str):
    """先向 DeepSeek 验证密钥，有效才写入 .env 并立即生效。"""
    key = key.strip()
    base = _config()[1]
    try:
        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    except httpx.HTTPError as e:
        raise AIError(f"无法连接 DeepSeek，请检查网络：{e}") from e
    if r.status_code == 401:
        raise AIError("密钥无效，请确认复制完整")
    if r.status_code != 200:
        raise AIError(f"DeepSeek 返回错误 {r.status_code}")
    try:
        settings.save("DEEPSEEK_API_KEY", key)
    except OSError as e:
        raise AIError(str(e)) from e


def _chat(system: str, user: str, as_json: bool) -> str:
    key, base, model = _config()
    if not enabled():
        raise AIError("还没有设置 DeepSeek 密钥，请点击右上角的设置按钮添加")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.3,
    }
    if as_json:
        body["response_format"] = {"type": "json_object"}
    try:
        r = httpx.post(f"{base}/chat/completions", json=body, timeout=60,
                       headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as e:
        raise AIError(f"无法连接 DeepSeek：{e}") from e
    _check_status(r.status_code, r.text)
    return r.json()["choices"][0]["message"]["content"]


def _check_status(status: int, text: str):
    if status == 401:
        raise AIError("DeepSeek 密钥无效，请在右上角的设置里重新填写")
    if status == 402:
        raise AIError("DeepSeek 账户余额不足")
    if status != 200:
        raise AIError(f"DeepSeek 返回错误 {status}：{text[:200]}")


ASK_SYSTEM = """你是一位耐心、严谨的德语老师，正在回答中国学习者关于德语语法、词汇、用法和德语国家知识的问题。
- 用简体中文回答，先直接给出结论，再简要说明原因；
- 每个要点配一两个简短的德语例句，并附中文翻译；
- 使用 Markdown 排版：要点用列表，变格、变位等对比内容用表格，德语关键词加粗；
- 不确定的内容要明确说明，不要编造规则；
- 如果问题与德语学习无关，简短回应后引导回德语学习。"""

ASK_MAX_MESSAGES = 20  # 只把最近的对话发给 DeepSeek，避免越聊越贵


def ask_model() -> str:
    """问 AI 使用的模型：用户选过的优先，否则用默认模型。"""
    return os.getenv("DEEPSEEK_ASK_MODEL", "").strip() or _config()[2]


def list_models() -> list[str]:
    """向 DeepSeek 查询当前账户可用的模型（不写死，模型更新后自动跟上）。"""
    key, base, _ = _config()
    if not enabled():
        raise AIError("还没有设置 DeepSeek 密钥，请点击右上角的设置按钮添加")
    try:
        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"}, timeout=20)
    except httpx.HTTPError as e:
        raise AIError(f"无法连接 DeepSeek：{e}") from e
    _check_status(r.status_code, r.text)
    return [m["id"] for m in r.json().get("data", []) if m.get("id")]


def set_ask_model(model: str):
    if model not in list_models():
        raise AIError(f"DeepSeek 目前没有 {model} 这个模型")
    try:
        settings.save("DEEPSEEK_ASK_MODEL", model)
    except OSError as e:
        raise AIError(str(e)) from e


def ask_stream(messages: list[dict]):
    """流式回答问题，逐段产出文字。出错时抛出 AIError。"""
    key, base, _ = _config()
    model = ask_model()
    if not enabled():
        raise AIError("还没有设置 DeepSeek 密钥，请点击右上角的设置按钮添加")
    body = {
        "model": model,
        "messages": [{"role": "system", "content": ASK_SYSTEM}, *messages[-ASK_MAX_MESSAGES:]],
        "temperature": 0.5,
        "stream": True,
    }
    try:
        with httpx.stream("POST", f"{base}/chat/completions", json=body,
                          headers={"Authorization": f"Bearer {key}"},
                          timeout=httpx.Timeout(60, connect=15)) as r:
            if r.status_code != 200:
                r.read()
                _check_status(r.status_code, r.text)
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                choices = json.loads(data).get("choices") or [{}]
                text = choices[0].get("delta", {}).get("content")
                if text:
                    yield text
    except httpx.HTTPError as e:
        raise AIError(f"无法连接 DeepSeek：{e}") from e


def _cached(key, fn):
    hit = store.get_ai(key)
    if hit is not None:
        return hit
    value = fn()
    store.put_ai(key, value)
    return value


GLOSS_SYSTEM = """你是一位面向中国学习者的德语老师。根据给出的德语词条信息，用简体中文输出 JSON：
{
  "senses": ["义项1", "义项2", ...],          // 最多 5 条，按常用程度排序，每条简短（如“去；走”）
  "usage": ["用法说明1", ...],                 // 2-4 条：常见搭配、支配的格、语序或易错点，简洁
  "examples": [{"de": "德语例句", "zh": "中文翻译"}, ...]   // 2 条贴近日常、A1-B1 难度的例句
}
只输出 JSON。"""


def gloss(info: dict) -> dict:
    lemma = info.get("lemma", "")
    kind = info.get("kind", "")
    key = "gloss:" + lemma + ":" + kind
    payload = {k: info.get(k) for k in ("lemma", "kind", "tags", "english", "definitions", "definition")}
    return _cached(key, lambda: json.loads(
        _chat(GLOSS_SYSTEM, json.dumps(payload, ensure_ascii=False), as_json=True)))


TRANSLATE_SYSTEM = """你是专业的德汉翻译。判断用户文本的语言：
- 如果是德语，翻译成自然流畅的简体中文；
- 如果是中文或其他语言，翻译成自然地道的德语。
输出 JSON：{"source": "de|zh|其他语言代码", "target": "zh|de", "translation": "译文",
"notes": ["可选：1-3 条值得注意的语法点或词汇，没有则为空数组"]}
只输出 JSON。"""


def translate(text: str) -> dict:
    key = "tr:" + hashlib.sha1(text.encode("utf-8")).hexdigest()
    return _cached(key, lambda: json.loads(_chat(TRANSLATE_SYSTEM, text, as_json=True)))


TO_DE_SYSTEM = """用户输入一个中文或英文的词语，请给出对应的德语单词，供中国学习者查词典用。输出 JSON：
{"candidates": [{"de": "德语原形（名词带定冠词，如 das Haus；动词用不定式）",
                 "pos": "词性（名词/动词/形容词/副词/介词/连词等）",
                 "zh": "这个德语词的中文意思，简短",
                 "note": "和其他候选词的区别，一句话，可为空"}]}
按常用程度排序，给 1-5 个；只给单个词，不要词组（除非输入本身是固定说法，如 good morning → Guten Morgen）。只输出 JSON。"""


def to_german(text: str, src: str) -> dict:
    """src 为 'zh' 或 'en'"""
    key = ("zh2de:" if src == "zh" else "en2de:") + text.lower()
    return _cached(key, lambda: json.loads(_chat(TO_DE_SYSTEM, text, as_json=True)))


PHRASE_SYSTEM = """用户输入一个德语短语、固定搭配或短句，请为中国学习者讲解。输出 JSON：
{
  "translation": "中文意思（简短）",
  "level": "大致难度 A1/A2/B1/B2/C1/C2",
  "usage": ["使用场合、语气或语法说明，2-3 条"],
  "words": [{"de": "短语中每个实词的词典原形（名词不带冠词）", "form": "在短语中的实际形式", "zh": "中文意思", "note": "形式说明，如“gut 的阳性宾格”，可为空"}],
  "examples": [{"de": "德语例句", "zh": "中文翻译"}]   // 2 条
}
如果输入有拼写错误，按最可能的正确写法讲解，并在 usage 第一条指出。只输出 JSON。"""


def phrase(text: str) -> dict:
    return _cached("phrase:" + text.lower(), lambda: json.loads(_chat(PHRASE_SYSTEM, text, as_json=True)))


LEMMA_SYSTEM = """用户在德语词典里输入了一个词，但词典没有直接查到。判断它是什么，输出 JSON：
{"lang": "de|en|unknown", "lemma": "...", "note": "..."}
- 若是德语单词的变形、拼写错误，或把 ä/ö/ü/ß 写成 ae/oe/ue/ss：lang 为 de，lemma 为词典原形（名词不带冠词，首字母大写），
  note 用一句中文说明，如“Haus 的复数”。可分动词的变形（如 stehe auf）要还原成一个词（aufstehen）。
- 若是德语固定短语或习语（如 guten Tag、zum Beispiel）：lang 为 de，lemma 为空字符串。
- 若是英语单词或短语（如 house、good morning）：lang 为 en，lemma 为空字符串。
- 无法识别：lang 为 unknown，lemma 为空字符串。
只输出 JSON。"""


def lemma(word: str) -> dict:
    return _cached("lemma3:" + word, lambda: json.loads(_chat(LEMMA_SYSTEM, word, as_json=True)))


VISUAL_SYSTEM = """为德语词典的单词配一张帮助理解的图片。根据词条信息输出 JSON：
{"emoji": "最能代表该词最常用含义的 1 个 emoji",
 "query": "在维基共享资源（Wikimedia Commons）搜图用的英文关键词，1-3 个最常见、最简单的英文单词，
           必须是该词最常用含义对应的具体、可拍照的物体或场景，就像照片文件名里会出现的词。
           英文词有歧义时（可能是地名、人名或其他意思），加一个限定词让它只指这个物体
           （如 Heft→school notebook、Brille→eyeglasses、Gabel→table fork、Schlüssel→door key、
           laufen→person running、Frau→woman portrait、Kind→child playing）；
           如果该词是抽象词、功能词（如 weil、und、schön 这类难以用照片表达的），
           或与人体部位、疾病医疗、死亡、性、暴力相关，则为空字符串（只显示 emoji）"}
只输出 JSON。"""


def visual(info: dict) -> dict:
    key = "visual5:" + info.get("lemma", "") + ":" + info.get("kind", "")
    payload = {k: info.get(k) for k in ("lemma", "kind", "english")}
    return _cached(key, lambda: json.loads(
        _chat(VISUAL_SYSTEM, json.dumps(payload, ensure_ascii=False), as_json=True)))


PICK_SYSTEM = """你在为面向所有年龄的德语学习词典挑选配图。用户给出单词、搜索词和候选图片的文件名（带序号）。
只根据文件名判断，挑出最能让学习者一眼理解这个词最常用含义的日常、清晰、有代表性的照片。
必须排除：
- 裸露、性相关；尸体、木乃伊、死亡；疾病、医疗、解剖、X 光；暴力、战争、灾难、武器；
- 童工、贫困、苦难等令人不适的内容；政治或宗教争议内容；
- 与词义无关的（同名的地名、人名、乐队、公司、船只等）；图表、地图、徽标、文档扫描、历史绘画。
拿不准的宁可不选。输出 JSON：{"keep": [序号, ...]}，按合适程度从高到低，最多 6 个；都不合适就输出空数组。只输出 JSON。"""


def pick_images(info: dict, query: str, titles: list[str]) -> list[int]:
    key = "pick:" + info.get("lemma", "") + ":" + info.get("kind", "") + ":" + query.lower()
    payload = {"word": info.get("lemma"), "english": (info.get("english") or [])[:4], "query": query,
               "candidates": [{"i": i, "file": t} for i, t in enumerate(titles)]}
    return _cached(key, lambda: json.loads(
        _chat(PICK_SYSTEM, json.dumps(payload, ensure_ascii=False), as_json=True)))["keep"]
