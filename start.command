#!/bin/bash
# 德语词典 macOS 启动脚本（在 Finder 里双击即可运行），对应 Windows 的 start.bat
# 关闭这个终端窗口即可停止词典。
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
    PY="$c"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "未找到 Python 3.10 以上版本。"
  echo "请先安装（任选其一）："
  echo "  1. 终端执行：brew install python"
  echo "  2. 从 https://www.python.org/downloads/ 下载安装包"
  echo ""
  echo "按回车键关闭窗口……"
  read
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "首次运行，正在创建运行环境并安装依赖（需要联网，几分钟后自动完成）……"
  "$PY" -m venv .venv || { echo "创建虚拟环境失败，请把本窗口截图反馈。"; read; exit 1; }
  .venv/bin/python -m pip install -q -r requirements.txt || { echo "依赖安装失败，请检查网络后重试（删除 .venv 文件夹可重新初始化）。"; read; exit 1; }
fi
if [ ! -f ".env" ]; then cp .env.example .env; fi

echo "德语词典已启动：http://localhost:8765"
echo "使用时请保持本窗口开着，关闭窗口即退出词典。"
open http://localhost:8765
.venv/bin/python -m uvicorn app.main:app --port 8765
