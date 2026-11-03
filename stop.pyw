"""停止在后台运行的词典程序，逻辑在 desktop.py。"""
import runpy
import sys
from pathlib import Path

sys.argv = [sys.argv[0], "--stop"]
runpy.run_path(str(Path(__file__).with_name("desktop.py")), run_name="__main__")
