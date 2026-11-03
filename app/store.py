"""本地 SQLite 存储：网页缓存、AI 结果缓存、查询历史。"""
import json
import sqlite3
import threading
import time
import zlib

from .paths import DATA_DIR

DB_PATH = DATA_DIR / "dict.db"

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.executescript("""
CREATE TABLE IF NOT EXISTS pages (path TEXT PRIMARY KEY, html BLOB, fetched_at REAL);
CREATE TABLE IF NOT EXISTS ai (key TEXT PRIMARY KEY, value TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS audio (url TEXT PRIMARY KEY, data BLOB);
CREATE TABLE IF NOT EXISTS history (word TEXT PRIMARY KEY, level TEXT, kind TEXT, looked_at REAL);
""")


def get_page(path):
    with _lock:
        row = _conn.execute("SELECT html FROM pages WHERE path=?", (path,)).fetchone()
    return zlib.decompress(row[0]).decode("utf-8") if row else None


def put_page(path, html):
    with _lock:
        _conn.execute("REPLACE INTO pages VALUES (?,?,?)",
                      (path, zlib.compress(html.encode("utf-8")), time.time()))
        _conn.commit()


def get_ai(key):
    with _lock:
        row = _conn.execute("SELECT value FROM ai WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def put_ai(key, value):
    with _lock:
        _conn.execute("REPLACE INTO ai VALUES (?,?,?)",
                      (key, json.dumps(value, ensure_ascii=False), time.time()))
        _conn.commit()


def get_audio(url):
    with _lock:
        row = _conn.execute("SELECT data FROM audio WHERE url=?", (url,)).fetchone()
    return row[0] if row else None


def put_audio(url, data):
    with _lock:
        _conn.execute("REPLACE INTO audio VALUES (?,?)", (url, data))
        _conn.commit()


def add_history(word, level, kind):
    with _lock:
        _conn.execute("REPLACE INTO history VALUES (?,?,?,?)", (word, level, kind, time.time()))
        _conn.commit()


def list_history(limit=30):
    with _lock:
        rows = _conn.execute("SELECT word, level, kind FROM history ORDER BY looked_at DESC LIMIT ?",
                             (limit,)).fetchall()
    return [{"word": w, "level": l, "kind": k} for w, l, k in rows]


def clear_history():
    with _lock:
        _conn.execute("DELETE FROM history")
        _conn.commit()
