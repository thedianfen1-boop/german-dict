"""保存在 .env 文件里的设置（API 密钥等）。"""
import os
import time

from dotenv import dotenv_values

from .paths import ENV_FILE


def mask(value: str) -> str:
    return f"{value[:3]}…{value[-4:]}" if len(value) > 8 else ""


def save(name: str, value: str):
    """写入 .env 并读回确认，成功后立即生效。失败时抛出 OSError。"""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.strip().lstrip("﻿").startswith(name)]
    lines.insert(0, f"{name}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 读回确认真的写进了文件，避免“显示已保存、重启后却变回旧值”
    if (dotenv_values(ENV_FILE).get(name) or "").strip() != value:
        raise OSError(f"没能写入 {ENV_FILE}，请检查文件权限")
    os.environ[name] = value
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 已保存 {name}（{mask(value)}）到 {ENV_FILE}", flush=True)
