"""德语词典的桌面入口（打包后就是 德语词典.exe / GermanDict.app）。

  无参数     后台启动词典程序（若未运行），就绪后用独立窗口打开
  --server   运行词典服务（由上面的模式在后台调用，无窗口）
  --stop     停止后台运行的词典服务
  --uninstall  运行安装文件夹里的卸载程序（Windows 安装版）
"""
import os
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
PORT = 8765
URL = f"http://localhost:{PORT}"
FROZEN = getattr(sys, "frozen", False)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # 仅 Windows 有这个常量


def running() -> bool:
    try:
        with urllib.request.urlopen(URL + "/api/status", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def server_command() -> list[str]:
    if FROZEN:
        return [sys.executable, "--server"]
    if IS_WIN:
        # 开发时用无控制台的 pythonw.exe，避免弹出黑色窗口
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        return [str(pythonw if pythonw.exists() else sys.executable), str(Path(__file__).resolve()), "--server"]
    return [sys.executable, str(Path(__file__).resolve()), "--server"]


def popen(args: list[str]):
    """后台拉起进程：Windows 不弹黑窗，macOS/Linux 脱离当前终端会话。"""
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if IS_WIN:
        kwargs["creationflags"] = NO_WINDOW | subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(args, **kwargs)


def open_window():
    if IS_MAC:
        # 优先用 Chrome/Edge 等 Chromium 系浏览器的应用模式窗口；没有就用默认浏览器
        for name in ("Google Chrome", "Microsoft Edge", "Chromium", "Brave Browser"):
            if Path(f"/Applications/{name}.app").exists():
                # --app 打开没有地址栏的独立窗口，看起来像一个桌面应用
                subprocess.Popen(["open", "-na", name, "--args", f"--app={URL}", "--window-size=1100,860"])
                return
    else:
        candidates = [
            Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        edge = next((p for p in candidates if p.exists()), None)
        if edge:
            # --app 打开没有地址栏的独立窗口，看起来像一个桌面应用
            subprocess.Popen([str(edge), f"--app={URL}", "--window-size=1100,860"])
            return
    webbrowser.open(URL)


def message(text: str):
    if IS_MAC:
        apple = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        subprocess.Popen(["osascript", "-e",
                          f'display dialog "{apple}" with title "德语词典" buttons {{"好"}} default button 1'])
    elif IS_WIN:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, "德语词典", 0x10)
    else:
        print(text)


def launch():
    if not running():
        popen(server_command())
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
    # 会出现两个词典程序同时运行、请求被随机分配的问题（例如密钥看似保存了却又变回旧的）；
    # macOS 上 SO_REUSEADDR 只会放行残留 TIME_WAIT 的旧连接，两个活动监听仍会冲突，
    # 所以防双开的效果一样，但能让"停止后马上重新打开"不报错
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if IS_WIN:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows 专用选项
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
    if IS_MAC:
        out = subprocess.run(["lsof", "-ti", f"tcp:{PORT}"], capture_output=True, text=True).stdout
        for pid in {int(p) for p in out.split()}:
            os.kill(pid, signal.SIGTERM)
        return
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    pids = {line.split()[-1] for line in out.splitlines()
            if f":{PORT} " in line and "LISTENING" in line}
    for pid in pids:
        subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, creationflags=NO_WINDOW)


def uninstall():
    if not IS_WIN:
        message("只有 Windows 安装版可以这样卸载。")
        return
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
