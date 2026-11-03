"""生成输入联想用的词表 data/words.tsv（每行：单词<TAB>词频，按词频从高到低）。

- 词频与排序：hermitdave/FrequencyWords 德语 50k 词表（OpenSubtitles，CC BY-SA 4.0），全小写
- 大小写：Leipzig Wortschatz 德语新闻语料（CC BY 4.0），取每个词最常见的写法（如 haus -> Haus）

运行：.venv\\Scripts\\python tools\\build_wordlist.py
"""
import io
import re
import tarfile
from collections import defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
FREQ_URL = "https://raw.githubusercontent.com/hermitdave/FrequencyWords/master/content/2018/de/de_50k.txt"
CASE_URL = "https://downloads.wortschatz-leipzig.de/corpora/deu_news_2023_100K.tar.gz"
WORD = re.compile(r"^[a-zäöüß]{2,}$")
TOKEN = re.compile(r"[A-Za-zÄÖÜäöüß]+|[.!?:;\"„“»«]")
SENT_END = set('.!?:;"„“»«')


def main():
    print("下载词频表……")
    freq = []
    for line in httpx.get(FREQ_URL, timeout=60, follow_redirects=True).text.splitlines():
        parts = line.split()
        if len(parts) == 2 and WORD.match(parts[0]):
            freq.append((parts[0], int(parts[1])))

    print("下载大小写语料……")
    data = httpx.get(CASE_URL, timeout=120, follow_redirects=True).content
    # 只统计句中的词（跳过句首和标点后的词），因为句首无论什么词都会大写
    cap_count, low_count = defaultdict(int), defaultdict(int)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        member = next(m for m in tar.getmembers() if m.name.endswith("-sentences.txt"))
        for line in io.TextIOWrapper(tar.extractfile(member), encoding="utf-8"):
            sentence = line.rstrip("\n").split("\t", 1)[-1]
            after_break = True
            for tok in TOKEN.findall(sentence):
                if tok in SENT_END:
                    after_break = True
                    continue
                if not after_break:
                    if tok[0].isupper() and tok[1:].islower():
                        cap_count[tok.lower()] += 1
                    elif tok.islower():
                        low_count[tok] += 1
                after_break = False

    def is_noun(w):
        return cap_count[w] > low_count[w] and cap_count[w] >= 2

    known = {w for w in cap_count if is_noun(w)}
    out = []
    for w, n in freq:
        if w in cap_count or w in low_count:
            noun = cap_count[w] > low_count[w]
        else:
            # 语料里没有的复合词：最后一部分是名词（如 apfel+kuchen）则视为名词
            noun = any(w[i:] in known and len(w) - i >= 4 for i in range(3, len(w) - 3))
        out.append(f"{w[:1].upper() + w[1:] if noun else w}\t{n}")

    path = ROOT / "data" / "words.tsv"
    path.parent.mkdir(exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"完成：{len(out)} 个词 -> {path}")


if __name__ == "__main__":
    main()
