# 德语词典 Wörterbuch
因为没找到好用的词典，我就自己做了个德语词典......

我在以Netzverb 词典作为词库的基础上，优化了ui界面。接入deepseek api密钥即可解锁满血版，实现中文释义、用法、句子翻译、配图和中英文查词。

支持 Windows 10/11 和 macOS（Apple 芯片，目前为测试版）。使用安装包不需要安装 Python；从源码运行需要 Python 3.10 以上。

神秘小动画宣传片https://www.bilibili.com/video/BV1j3xm6hE2T/?spm_id_from=333.1387.homepage.video_card.click&vd_source=9550160a6efcab58f1e57cbed5332119

Claude我们真厉害😂

- **动词**：完整变位表（现在时、过去时、完成时、虚拟式、命令式……），不规则变化标红，显示助动词 haben/sein
- **名词**：冠词按颜色区分（der 粉 / die 蓝 / das 绿），单复数变格表
- **形容词**：比较级、最高级，强/弱/混合变格
- **其他词性**：介词支配的格、用法、例句
- **难度**：每个词标注 A1–C2 等级
- **释义**：中英对照，AI 补充中文义项、用法说明和例句
- **配图**：按词义自动配图（来自维基共享资源 Wikimedia Commons，无需注册），抽象词显示 emoji
- **查词方式**：德语（含变形词，如 ging → gehen、Häuser → Haus）、中文、英语、短语（如 guten Tag）
- **输入联想**：按常用程度提示单词；可用 ae/oe/ue/ss 代替 ä/ö/ü/ß
- **翻译**：德语 ⇄ 中文句子翻译
- **问 AI**：随时提问语法、用法和知识点，可以连续追问
- **发音**：真人朗读
- **注意**：需要接入deepseek api 才能解锁满血版

## 安装（Windows 10/11）

1. 在 [Releases](../../releases) 下载最新版本的 `GermanDict-Setup` 安装程序，双击运行，选择安装位置。不需要安装 Python，也不需要管理员权限。
   - 安装包没有数字签名，Windows 可能提示“已保护你的电脑”，点“更多信息 → 仍要运行”。
2. 打开后点击页面右上角的 ⚙ 设置，填写 **DeepSeek API 密钥**（[获取](https://platform.deepseek.com/api_keys)）：
   用于中文释义、用法、翻译、配图关键词和中英文查词。不填也能查德语词条。

密钥只保存在你自己的电脑上（`%LOCALAPPDATA%\GermanDict\.env`）。卸载：开始菜单 → 德语词典 → 卸载德语词典。

## 安装（macOS 测试版）

目前的 Mac 安装包是测试版，只支持 Apple 芯片（M 系列），不支持 Intel Mac。它的功能比 Windows v2.0 少：没有问 AI、模型切换、复制按钮和 × 清空，冠词颜色也是旧版（der 蓝 / die 粉）。需要完整功能可以[从源码运行](#从源码运行)。

1. 在 [macOS 测试版](../../releases/tag/mac-beta1)下载 `GermanDict-macOS.zip`，解压后把 `GermanDict.app` 拖进「应用程序」文件夹，双击打开。
   - 应用没有签名。如果打不开，请到“系统设置 → 隐私与安全性”点“仍要打开”；如果提示应用已损坏，请在终端执行 `xattr -cr /Applications/GermanDict.app`。
2. 打开后点击页面右上角的 ⚙ 设置，填写 **DeepSeek API 密钥**（[获取](https://platform.deepseek.com/api_keys)）：用于中文释义、用法、翻译、配图关键词和中英文查词。不填也能查德语词条。

密钥保存在 `~/Library/Application Support/GermanDict/.env`。

## 从源码运行

需要 Python 3.10 以上。也可以不配环境直接双击 `start.bat`（Windows）/ `start.command`（macOS，首次需在终端执行 `chmod +x start.command`）。

Windows：

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
.venv\Scripts\python -m uvicorn app.main:app --port 8765
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m uvicorn app.main:app --port 8765
```

然后打开 http://localhost:8765 。

生成安装包（构建脚本会检查包里没有本机的 API 密钥和个人数据，结果在 `release/` 文件夹）：

Windows（需要系统自带的 IExpress）：

```bat
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python tools\build_installer.py
```

macOS（用 PyInstaller 打包成 GermanDict.app）：

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python tools/build_app.py
```

## 项目结构

```
app/            后端（FastAPI）
  scraper.py    从 Netzverb 获取并解析词条
  dictionary.py 查词流程（变形词、变音字母、中英文查词、短语）
  ai.py         DeepSeek：中文释义、翻译、关键词
  images.py     Wikimedia Commons 配图
  suggest.py    输入联想
static/         前端页面
desktop.py      桌面启动器（打包后的 GermanDict.exe / GermanDict.app）
installer/      Windows 安装 / 卸载脚本
tools/          生成词表、生成安装包（Windows）/ 应用包（macOS）
```

## 数据来源与许可

- 源代码：[MIT](LICENSE)
- 词条数据：按需从 [Netzverb（zh.verbformen.net）](https://zh.verbformen.net/) 获取，内容采用 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)。程序只在查词时获取单个词条，两次请求至少间隔 1.5 秒，并在本地缓存，不批量下载。
- 输入联想词表 `data/words.tsv`：CC BY-SA 4.0，来源见 [data/LICENSE-words.md](data/LICENSE-words.md)
- 配图：[Wikimedia Commons](https://commons.wikimedia.org/)（通过官方 API，图片为 CC BY / CC BY-SA / 公有领域等自由授权，每张图下方注明作者和授权，点击可查看原图页面）。图片由 AI 按文件名筛选，无法保证完全过滤
- 中文释义、用法、例句和翻译由 [DeepSeek](https://www.deepseek.com/) 生成，可能有错误，请以词典原文为准

