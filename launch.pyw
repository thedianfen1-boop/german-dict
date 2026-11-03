"""开发版桌面快捷方式的入口，逻辑都在 desktop.py。"""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("desktop.py")), run_name="__main__")
