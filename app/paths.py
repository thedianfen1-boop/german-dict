"""程序文件和用户数据的位置。

- 开发时：都在项目文件夹里（static/、data/、.env）
- 安装版（PyInstaller 打包后）：程序文件在 exe 所在文件夹；
  用户数据（缓存、历史、API 密钥）在 %LOCALAPPDATA%\\GermanDict，重装或升级不会丢失
"""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "GermanDict"
    ENV_FILE = DATA_DIR / ".env"
    WORDS_PATH = APP_DIR / "words.tsv"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = APP_DIR / "data"
    ENV_FILE = APP_DIR / ".env"
    WORDS_PATH = DATA_DIR / "words.tsv"

STATIC_DIR = APP_DIR / "static"
DATA_DIR.mkdir(parents=True, exist_ok=True)
