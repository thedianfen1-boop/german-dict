"""生成 macOS 应用 release/GermanDict-macOS.zip（内含 GermanDict.app）。

对应 Windows 的 tools/build_installer.py。步骤：
生成 .icns 图标 → PyInstaller 打包 → 检查没有包含 API 密钥和个人数据 → 压缩。

运行（需要 macOS）：
  .venv/bin/python -m pip install -r requirements-dev.txt   # 只需一次
  .venv/bin/python tools/build_app.py
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = BUILD / "dist"
RELEASE = ROOT / "release"

VERSION = {}
exec((ROOT / "app" / "version.py").read_text(encoding="utf-8"), VERSION)
VERSION = VERSION["VERSION"]


def step(msg):
    print(f"\n== {msg}", flush=True)


def make_icns() -> Path:
    """用 macOS 自带的 sips + iconutil 把 static/icon.png 转成 icon.icns。"""
    iconset = BUILD / "icon.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir(parents=True)
    png = ROOT / "static" / "icon.png"
    for size in (16, 32, 64, 128, 256, 512):
        for s, name in ((size, f"icon_{size}x{size}.png"), (size * 2, f"icon_{size}x{size}@2x.png")):
            subprocess.run(["sips", "-z", str(s), str(s), str(png), "--out", str(iconset / name)],
                           check=True, capture_output=True)
    out = BUILD / "icon.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    return out


def check_secrets():
    step("检查应用包中没有 API 密钥和个人数据")
    keys = []
    for env in (ROOT / ".env", Path.home() / "Library/Application Support/GermanDict/.env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                name, _, value = line.partition("=")
                if name.strip().endswith("_API_KEY") and len(value.strip()) >= 16:
                    keys.append(value.strip())
    for f in DIST.rglob("*"):
        if f.name in (".env", "dict.db", "server.log"):
            sys.exit(f"错误：应用包里包含了个人数据 {f}")
        if f.is_file() and keys:
            if any(k.encode() in f.read_bytes() for k in keys):
                sys.exit(f"错误：应用包里发现了 API 密钥（{f}）")
    print(f"通过（检查了 {len(keys)} 个本机密钥）")


def main():
    if sys.platform != "darwin":
        sys.exit("请在 macOS 上运行本脚本")

    step("清理旧的构建产物")
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir(parents=True)

    step("生成图标 icon.icns")
    icns = make_icns()

    step(f"PyInstaller 打包（v{VERSION}）")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", str(ROOT / "desktop.py"),
        "--name", "GermanDict",
        "--windowed", "--onedir", "--noconfirm",
        "--icon", str(icns),
        "--osx-bundle-identifier", "com.dianfen.germandict",
        "--collect-submodules", "uvicorn",
        "--hidden-import", "app.main",
        "--paths", str(ROOT),
        "--add-data", f"{ROOT / 'static'}:static",
        "--add-data", f"{ROOT / 'data' / 'words.tsv'}:.",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
    ], check=True)

    check_secrets()

    step("压缩为 release/GermanDict-macOS.zip")
    RELEASE.mkdir(exist_ok=True)
    out = RELEASE / "GermanDict-macOS.zip"
    if out.exists():
        out.unlink()
    subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent",
                    str(DIST / "GermanDict.app"), str(out)], check=True)
    print(f"\n完成：{out}（{out.stat().st_size / 1024 / 1024:.1f} MB）")
    print("提示：应用未签名，首次打开若被系统拦截：右键点击 GermanDict.app → 打开；"
          "或在终端执行 xattr -cr 解除隔离。")
    print("提示：应用把数据（缓存、历史、API 密钥）保存在 ~/Library/Application Support/GermanDict。")


if __name__ == "__main__":
    main()
