"""程序文件和用户数据的位置。

- 开发时：都在项目文件夹里（static/、data/、.env）
- 安装版（PyInstaller 打包后）：程序文件在 Windows 的 exe 所在文件夹 / macOS 的 GermanDict.app 内；
  用户数据（缓存、历史、API 密钥）在 Windows 的 %LOCALAPPDATA%\\GermanDict /
  macOS 的 ~/Library/Application Support/GermanDict，重装或升级不会丢失
"""
import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    if sys.platform == "darwin":
        # .app 内的静态资源由 PyInstaller 解包到 _MEIPASS（Contents/Frameworks）
        bundle = getattr(sys, "_MEIPASS", None)
        APP_DIR = Path(bundle) if bundle else Path(sys.executable).resolve().parent
        DATA_DIR = Path.home() / "Library/Application Support/GermanDict"
    else:
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
