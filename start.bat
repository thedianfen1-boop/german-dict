@echo off
cd /d "%~dp0"
title 德语词典

if not exist ".venv\Scripts\python.exe" (
  echo 首次运行，正在创建环境并安装依赖……
  python -m venv .venv || (echo 未找到 Python，请先安装 Python 3.10 以上版本 & pause & exit /b 1)
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || (pause & exit /b 1)
)
if not exist ".env" copy ".env.example" ".env" >nul

echo 德语词典已启动：http://localhost:8765
echo 关闭这个窗口即可停止。
start "" http://localhost:8765
".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8765
pause
