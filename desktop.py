"""德语词典的桌面入口（打包后就是 德语词典.exe）。

  无参数     后台启动词典程序（若未运行），就绪后用独立窗口打开
  --server   运行词典服务（由上面的模式在后台调用，无窗口）
  --stop     停止后台运行的词典服务
  --uninstall  运行安装文件夹里的卸载程序（安装版）
"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

PORT = 8765
URL = f"http://localhost:{PORT}"
FROZEN = getattr(sys, "frozen", False)
NO_WINDOW = subprocess.CREATE_NO_WINDOW


def running() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/status", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def server_command() -> list[str]:
    if FROZEN:
        return [sys.executable, "--server"]
    # 开发时用无控制台的 pythonw.exe，避免弹出黑色窗口
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return [str(pythonw if pythonw.exists() else sys.executable), str(Path(__file__).resolve()), "--server"]


def open_window():
    candidates = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
    ]
    edge = next((p for p in candidates if p.exists()), None)
    if edge:
        # --app 打开没有地址栏的独立窗口，看起来像一个桌面应用
        subprocess.Popen([str(edge), f"--app={URL}", "--window-size=1100,860"])
    else:
        webbrowser.open(URL)


def message(text: str):
    import ctypes
    ctypes.windll.user32.MessageBoxW(0, text, "德语词典", 0x10)


def launch():
    if not running():
        subprocess.Popen(server_command(), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        for _ in range(120):  # 最多等 30 秒（电脑刚开机时首次启动较慢）
            time.sleep(0.25)
            if running():
                break
        else:
            from app.paths import DATA_DIR
            message(f"词典程序没能启动，详情见：\n{DATA_DIR / 'server.log'}")
            return
    open_window()


def serve():
    from app.paths import DATA_DIR
    # 无窗口程序没有标准输出，日志写到用户数据文件夹
    log = open(DATA_DIR / "server.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log
    # 独占端口：uvicorn 默认的 SO_REUSEADDR 在 Windows 上允许第二个进程绑定同一端口，
    # 会出现两个词典程序同时运行、请求被随机分配的问题（例如密钥看似保存了却又变回旧的）
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(("127.0.0.1", PORT))
    except OSError:
        print(f"端口 {PORT} 已被占用，词典程序可能已在运行，本次不再启动", flush=True)
        return
    import uvicorn
    from app import ai
    from app.main import app
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 启动，DeepSeek 密钥：{ai.masked_key() or '未设置'}", flush=True)
    uvicorn.Server(uvicorn.Config(app, log_config=None)).run(sockets=[sock])


def stop():
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    pids = {line.split()[-1] for line in out.splitlines()
            if f":{PORT} " in line and "LISTENING" in line}
    for pid in pids:
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, creationflags=NO_WINDOW)


def uninstall():
    script = Path(sys.executable).resolve().parent / "uninstall.ps1"
    if not FROZEN or not script.exists():
        message("只有安装版可以这样卸载。")
        return
    # 注意不能加 DETACHED_PROCESS：PowerShell 会在弹出对话框前直接退出
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                     creationflags=NO_WINDOW)


if __name__ == "__main__":
    if not FROZEN:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    {"--server": serve, "--stop": stop, "--uninstall": uninstall}.get(arg, launch)()
