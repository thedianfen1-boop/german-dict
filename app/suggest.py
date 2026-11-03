"""输入联想：在本地词表 data/words.tsv（按词频排序）中做前缀匹配，查过的词优先。"""
from . import store
from .paths import WORDS_PATH

_words: list[tuple[str, str]] | None = None  # (折叠后的写法, 原词)，按词频从高到低


def fold(s: str) -> str:
    """统一大小写和变音写法，使 schoe / schö / SCHÖ 都能匹配 schön。"""
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    return s


def _load():
    global _words
    if _words is None:
        _words = []
        if WORDS_PATH.exists():
            for line in WORDS_PATH.read_text(encoding="utf-8").splitlines():
                w = line.split("\t", 1)[0]
                if w:
                    _words.append((fold(w), w))
    return _words


def suggest(q: str, limit: int = 8) -> list[str]:
    q = q.strip()
    if not q or " " in q or not q.isalpha():
        return []
    fq = fold(q)
    out, seen = [], set()

    def add(w):
        key = w.lower()
        if w == q:  # 和输入完全一样的不用再提示
            return
        if key not in seen:
            seen.add(key)
            out.append(w)

    for h in store.list_history(100):
        if fold(h["word"]).startswith(fq):
            add(h["word"])
    exact = [w for f, w in _load() if f == fq]
    for w in exact[:1]:
        add(w)
    for f, w in _load():
        if len(out) >= limit:
            break
        if f.startswith(fq):
            add(w)
    return out[:limit]
