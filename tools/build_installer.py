"""生成安装程序 release/德语词典安装程序.exe。

步骤：PyInstaller 打包 → 放入网页文件和词表 → 检查没有包含 API 密钥 → 压缩 → IExpress 生成安装程序
运行：.venv\\Scripts\\python tools\\build_installer.py
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = BUILD / "dist" / "GermanDict"
STAGE = BUILD / "installer"
RELEASE = ROOT / "release"
VERSION = {}
exec((ROOT / "app" / "version.py").read_text(encoding="utf-8"), VERSION)
VERSION = VERSION["VERSION"]


def step(msg):
    print(f"\n== {msg}", flush=True)


def write_bom(src: Path, dst: Path):
    # Windows PowerShell 5.1 需要带 BOM 的 UTF-8 才能正确读取中文；同时填入版本号
    dst.write_text(src.read_text(encoding="utf-8").replace("__VERSION__", VERSION), encoding="utf-8-sig")


def version_file() -> Path:
    """exe 文件属性里显示的版本信息。"""
    nums = tuple(int(x) for x in (VERSION.split(".") + ["0"] * 4)[:4])
    path = BUILD / "version_info.txt"
    path.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[StringFileInfo([StringTable('080404b0', [
    StringStruct('CompanyName', '淀粉'),
    StringStruct('FileDescription', '德语词典'),
    StringStruct('FileVersion', '{VERSION}'),
    StringStruct('ProductName', '德语词典'),
    StringStruct('ProductVersion', '{VERSION}'),
    StringStruct('LegalCopyright', '作者：淀粉')])]),
  VarFileInfo([VarStruct('Translation', [2052, 1200])])])
""", encoding="utf-8")
    return path


def check_powershell(script: Path):
    """用 PowerShell 自己的解析器检查语法（例如中文弯引号会被当成字符串结束符）。"""
    cmd = ("$e=$null; [System.Management.Automation.Language.Parser]::ParseFile("
           f"'{script}', [ref]$null, [ref]$e) | Out-Null; "
           "$e | ForEach-Object { \"$($_.Extent.StartLineNumber): $($_.Message)\" }")
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                         capture_output=True, text=True, encoding="mbcs").stdout.strip()
    if out:
        sys.exit(f"错误：{script.name} 有语法问题：\n{out}")


def main():
    step("检查安装脚本语法")
    for name in ("install.ps1", "uninstall.ps1"):
        tmp = BUILD.parent / "installer" / f".check-{name}"
        write_bom(ROOT / "installer" / name, tmp)
        try:
            check_powershell(tmp)
        finally:
            tmp.unlink()
    print("通过")

    step(f"PyInstaller 打包（v{VERSION}）")
    shutil.rmtree(BUILD, ignore_errors=True)
    BUILD.mkdir()
    subprocess.run([
        sys.executable, "-m", "PyInstaller", str(ROOT / "desktop.py"),
        "--name", "GermanDict", "--windowed", "--onedir", "--noconfirm",
        "--icon", str(ROOT / "icon.ico"), "--version-file", str(version_file()),
        "--collect-submodules", "uvicorn", "--hidden-import", "app.main",
        "--paths", str(ROOT),
        "--distpath", str(BUILD / "dist"), "--workpath", str(BUILD / "work"), "--specpath", str(BUILD),
    ], check=True)

    step("放入网页文件、词表和卸载脚本")
    shutil.copytree(ROOT / "static", DIST / "static")
    shutil.copy2(ROOT / "data" / "words.tsv", DIST / "words.tsv")
    write_bom(ROOT / "installer" / "uninstall.ps1", DIST / "uninstall.ps1")

    step("检查安装包中没有 API 密钥和个人数据")
    keys = []
    for env in (ROOT / ".env", Path(os.environ.get("LOCALAPPDATA", "")) / "GermanDict" / ".env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8").splitlines():
                name, _, value = line.partition("=")
                if name.strip().endswith("_API_KEY") and len(value.strip()) >= 16:
                    keys.append(value.strip())
    for f in DIST.rglob("*"):
        if f.name in (".env", "dict.db", "server.log"):
            sys.exit(f"错误：安装包里包含了 {f}")
        if f.is_file() and keys:
            data = f.read_bytes()
            if any(k.encode() in data for k in keys):
                sys.exit(f"错误：安装包里发现了 API 密钥（{f}）")
    print(f"通过（检查了 {len(keys)} 个本机密钥）")

    step("压缩")
    STAGE.mkdir(parents=True)
    with zipfile.ZipFile(STAGE / "payload.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in DIST.rglob("*"):
            z.write(f, f.relative_to(DIST))
    write_bom(ROOT / "installer" / "install.ps1", STAGE / "install.ps1")
    shutil.copy2(ROOT / "icon.ico", STAGE / "icon.ico")  # 安装窗口的图标

    step("IExpress 生成安装程序")
    target = STAGE / "GermanDict-Setup.exe"
    sed = STAGE / "setup.sed"
    sed.write_text(f"""[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=1
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=
DisplayLicense=
FinishMessage=
TargetName={target}
FriendlyName=German Dictionary Setup
AppLaunched=powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File install.ps1
PostInstallCmd=<None>
AdminQuietInstCmd=
UserQuietInstCmd=
SourceFiles=SourceFiles
[Strings]
FILE0="install.ps1"
FILE1="payload.zip"
FILE2="icon.ico"
[SourceFiles]
SourceFiles0={STAGE}\\
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
""", encoding="mbcs")
    subprocess.run(["iexpress.exe", "/N", "/Q", str(sed)], check=True)

    RELEASE.mkdir(exist_ok=True)
    out = RELEASE / "德语词典安装程序.exe"
    shutil.copy2(target, out)
    print(f"\n完成：{out}（{out.stat().st_size / 1024 / 1024:.1f} MB）")


if __name__ == "__main__":
    main()
